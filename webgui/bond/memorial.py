# -*- coding: utf-8 -*-
"""`webgui.bond` 的**纪念生图**（C6, `docs/EXEC_SPLIT.md`）—— 非 LLM 的那条支线。

## 放什么

· `_persisted_memorial_img` —— 从事件流捡回**异步落盘**的纪念图（`memorial_image`
  marker 是回执: 图比事件晚到, append-only 不能补写原事件）
· `_memorial_gen` —— 真正开画（prompt = 块级 `art` 画面意向 → 缺省 `memorial` 转场句;
  总开关/生图器一律走 `webgui.deps`, 见 C1a）
· `_make_memorial_cb` —— 生图回调工厂（落 marker + 写 `state.memorial_img`）
· `_ensure_memorial_img` —— 板上屏时确保图就绪（读回执 / 触发开画）

## 纪律

· 依赖方向: `memorial` → `stores`（写回执 marker）+ `state`（类型）+ `deps`（生图器接缝）;
  **对外边为空**（叶子）—— 所以它排在 `pregen` **之前**（`_generate`/`_pregenerate` 要用
  `_make_memorial_cb`, `_scene_landed` 要用 `_ensure_memorial_img`; 反过来先搬 pregen
  就会反向 import = 环, 见 `EXEC_SPLIT` §5 陷阱 10）;
· ⚠️ **生图总开关与替身一律走 `webgui.deps`**（`deps.image_generator()` /
  `deps.ImageGenerator`）—— 打**包属性**会静默失效（C1a）;
· 搬进来的代码**逐字未改**。
"""

from __future__ import annotations

import threading
import time
import logging
from core.media.gallery import GalleryStore
from core.session.events import (
    M_MEMORIAL_IMAGE,
    M_SESSION_END,
    M_VN_ABANDON,
    M_VN_EXIT,
)
from core.session.staging import staging_store
from llm.image_gen import collect_ref_images
from pathlib import Path
from webgui import chat, deps
from webgui.bond.state import BondState
from webgui.bond.stores import (
    _flow_store,
    _store,
)

logger = logging.getLogger(__name__)


def _persisted_memorial_img(char_id: str, session_id: str, store=None) -> str:
    """从事件流恢复纪念图 URL（2026-09-12）: 最近一条**仍属当前章**的
    `memorial_image` marker。

    为什么单开一条 marker: 图是异步生成完才有的, 不能补写进原 bond 事件
    （append-only 不可改）→ 生成成功即 append 回执（`_memorial_gen`）。

    **范围判据 = "其后没有本章结束"**（`vn_exit`/`vn_abandon`/`session_end`）:
    章内 ≤1 次纪念, 上一章的图不能错挂到新章 → 只看其后未闭合的那条。
    为什么**不**用"最近一次 `vn_enter` 之后"划范围: **预热会在 `vn_enter` 之前就出图**
    （触发轮结束即后台生成首场 → 板落地就写 marker; 玩家点进来才写 vn_enter）——
    B 层冒烟实测踩到: 按 vn_enter 划范围会把当前章自己的图排除掉。

    ⚠️⚠️ **2026-09-20 修（真机报障"这一章生成了 memorial，但我玩的时候没见过"）**:
    这里原先只读**真源**。而 B0 整章暂存下, 章内的 marker（含本条的 `memorial_image`）
    **还在 `soul/staging/`**, 直到 `vn_exit` 才整段提交 ⇒ 章进行中查这里**恒为空**
    → `_ensure_memorial_img` 填不上 `state.memorial_img` → 前端 `syncMemorial`
    落在"**in_memorial=true 但图为空**"那一支 = 清空背景 + **什么都不淡入** = **黑屏**。
    真机现场: 图 14:53:28（预热期间）生成入暂存, 纪念板 14:58:45（收尾板）,
    中间 5 分钟真源里查不到 → 玩家只看到黑屏, 没看到纪念图。
    **修法与 `replay_attempts` 同一条**: 读 **overlay**（真源 + 章内暂存）。
    """
    try:
        evs = staging_store(store or _store()).events(char_id, session_id)
    except Exception:                                # noqa: BLE001 — 读失败当没有
        return ""
    url = ""
    for e in evs:
        if not getattr(e, "is_marker", False):
            continue
        if e.subtype in (M_VN_EXIT, M_VN_ABANDON, M_SESSION_END):
            url = ""                                 # 本章结束 → 之前那张作废
        elif e.subtype == M_MEMORIAL_IMAGE:
            u = (e.payload or {}).get("url")
            if isinstance(u, str) and u.strip():
                url = u.strip()
    return url


def _memorial_gen(state: BondState, char_id: str, session_id: str,
                  prompt: str) -> None:
    """纪念立绘异步生成（方案 A）: generate → 画廊落盘 → 写回 state。

    触发早于契约校验——动作最终可能被拒（频率限制/坏 JSON → 图作废, 接受浪费）。
    失败降级: 不设置 memorial_img（前端纯文字, 剧情照走）。写回持短锁;
    场景已推进不影响（前端只在纪念场景显示图）。总开关关 → 调用方已不开线程。
    """
    try:
        gen = deps.image_generator()
        if gen is None:
            return                              # 未配 key → 降级纯文字
        eng = chat._engine(char_id)
        char = eng.current_character
        name = char.display_name if char is not None else "角色"
        hints = eng.char_loader.load_illustration(char_id)   # illustration.yml（可选）
        # 性格简卡（2026-09-20 D1）: 作者手写优先; 没写 → 从 personality.yml 的
        # SIG~brief_traits 自动摘。生图模型不知道人设就画不出神态。
        persona = (hints.get("character_hint") or "").strip() or (
            char.image_persona_brief() if char is not None else "")
        refs = collect_ref_images(char_id)
        img = gen.generate(prompt, ref_images=refs,
                           character_name=name,
                           character_hint=persona,
                           halo_hint=hints.get("halo_hint", ""))
        logger.info("纪念立绘: %dx%d %.1fs %s", img.width, img.height,
                    img.elapsed_s, img.path.name)
        # 可归因记账（2026-09-20 节点 C）: `prompt_source` = 这张图的 prompt 是
        # `art` 画面意向还是降级的触发句 —— art 配对命中率就靠它算。
        # ⚠️ 2026-09-27 修: 写者是**触发那一次的 `BondStoryEngine`**（`state.vn`，
        #    见 `bond_story/engine.py::_fire_memorial_image`），这里原先读的是
        #    `chat._engine(char_id)`（**MomoTalkEngine**——另一个类）⇒ `getattr`
        #    永远落到默认 `""` ⇒ **字段从来没写进 gallery json**（真机 6 张图 +
        #    冒烟世界全部缺该字段；art 命中率因此无法统计）。
        src = getattr(state.vn, "memorial_prompt_source", "") or ""
        sid = GalleryStore(_flow_store(state).data_root,
                           world_id=_flow_store(state).world_id).write(
            char_id, prompt, session_id, img.path, width=img.width, height=img.height,
            prompt_source=src,
            refs=[Path(p).name for p in refs],
            model=getattr(gen, "api_model", "") or "",
            elapsed_ms=int(round((img.elapsed_s or 0) * 1000)))
        with state._lock:
            state.memorial_img = (
                f"/gallery/{_flow_store(state).world_id}/{char_id}/{sid}.png")
        # 异步回执落真源（append-only: 图后到, 不能补写原 bond 事件）——
        # 回放/重启据此恢复纪念图（`_ensure_memorial_img`）。写失败只降级: 本进程
        # 内存里仍有图, 只是重启后回放看不到（宁缺勿错）。
        try:
            _flow_store(state).append_marker(
                char_id, session_id, M_MEMORIAL_IMAGE,
                {"url": f"/gallery/{_flow_store(state).world_id}/{char_id}/{sid}.png",
                 "prompt": str(prompt)[:200], "width": img.width, "height": img.height,
                 "scene_id": sid})
        except Exception as e:                       # noqa: BLE001 — 回执写失败不阻断
            logger.warning("纪念图回执 marker 写失败（回放将看不到这张图）: %s", e)
    except Exception as e:                       # noqa: BLE001 — 失败降级纯文字
        logger.warning("纪念立绘生成失败（降级纯文字）: %s", e)
        with state._lock:
            state.memorial_img = ""
    finally:
        with state._lock:
            state.memorial_img_busy = False


def board_in_memorial(state: BondState) -> bool:
    """前端要的 `in_memorial` = **当前这块板在不在纪念窗口里**。

    ⚠️ **不要**改用 `state.vn.in_memorial`（引擎的活标志 = "**解析**到哪了"）:
    预热/预生成会提前解析后面的块, 纪念板真正交付给玩家时它早被翻回 False ⇒
    前端不点亮纪念层（不黑屏、不淡入图）。真机 2026-09-23 报障即此。
    板自己带的快照（`BondScene.in_memorial`, 组装器造板时算好）与解析/交付顺序无关。

    兜底两处: 旧档/旧草稿没有该字段 → 看 `memorial`（"本板含触发"也算在窗口里）;
    还没有当前板（生成中 / 回放开始前）→ 退回活标志, 免得空窗期状态抖动。
    """
    sc = state.scene_obj
    if sc is not None:
        return bool(getattr(sc, "in_memorial", False) or getattr(sc, "memorial", False))
    return bool(state.vn is not None and state.vn.in_memorial)


def _make_memorial_cb(state: BondState, char_id: str, session_id: str):
    """流式嗅探回调: prompt 定稿 → 重置图状态 + 开生图线程（不阻塞 LLM 收集线程）。

    在 LLM 收集线程内被调用（持 chat._lock）——只开线程, 不做重活。
    防重复: memorial_img_busy 时跳过（重试 attempt 可能再次触发, 第一张作废）。
    """
    def cb(prompt: str) -> None:
        if state.demo is not None:
            return
        if deps.image_generator() is None:
            return                       # 总开关关 / 未配 key → 不开线程（纯文字降级）
        with state._lock:
            if state.memorial_img_busy:
                return
            state.memorial_img_busy = True
            state.memorial_img = ""
        threading.Thread(target=_memorial_gen,
                         args=(state, char_id, session_id, prompt),
                         daemon=True).start()
    return cb


def _ensure_memorial_img(state: BondState, char_id: str, session_id: str) -> None:
    """纪念窗口内还没有图 → 从事件流补一次（回放 / 重启 / 重进: 图由上一进程生成）。

    只在纪念窗口内 + 图为空时查（每次进板一次, 事件流很小）; 命中即写回 state,
    随后 `bond_status`/`_ready_scene_payload` 自然把它带给前端（前端 `syncMemorial`
    据此淡入）。查不到就什么都不做（纯文字降级, 宁缺勿错）。
    """
    if state.memorial_img or state.vn is None or not state.vn.in_memorial:
        return
    url = _persisted_memorial_img(char_id, session_id, _flow_store(state))
    if url:
        state.memorial_img = url
        logger.info("纪念立绘: 事件流恢复 %s", url)
