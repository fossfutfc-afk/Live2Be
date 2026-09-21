# -*- coding: utf-8 -*-
"""`webgui.bond` 的**落库层**（C3, `docs/EXEC_SPLIT.md`）—— 事件流读写的唯一出口。

## 放什么

· **store 入口**: `_store()`（转发 `webgui.deps`）、`_flow_store()`（真源+暂存 overlay）、
  `_stage_store()`（章内写入口, B0 整章暂存）
· **板落库**: `_log_scene()`（正文 + picked）、`_log_scene_meta()`（每场 marker）、
  `_close_memorial_window()`（补写 `memorial_exit`）
· **草稿旁路**（`soul/bond_draft.json`, 决策 #28）: `_draft_*`
· **入口预热缓存**（`soul/prewarm.json`）: `_prewarm_cache_*`
· **事件流读点**: `_last_bond_seq` / `_last_mmt_seq` / `_open_vn_seq`

## 纪律

· 依赖方向: 本模块 → `webgui.bond.state`（`BondState` / `BoardLifecycle`）+ `webgui.deps`,
  **不反向** import `_impl`（那会成环; 见 `EXEC_SPLIT` §5 陷阱 10）;
· ⚠️ **不是接缝**: 换 store 一律 `deps.store()` / `deps.set_store()` —— 子模块读的是
  自己的全局, 打**包属性**（`monkeypatch.setattr(webgui.bond, …)`）会静默失效（C1a）;
· 搬进来的代码**逐字未改**。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from core.bond.bond_story import BondScene
from core.common.atomic import replace_with_retry
from core.session.events import (
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_VN_STATE,
    make_event,
)
from core.session.staging import staging_store
from webgui import deps
from webgui.bond.state import BoardLifecycle, BondState

logger = logging.getLogger(__name__)


def _store():
    """当前会话存储（接缝转发——测试换 store 请 `deps.set_store()`/patch `deps._store`）。

    保留这个名字只为**可读性**（bond 里到处 `_store()`）; 真实来源在 `webgui/deps.py`。
    """
    return deps.store()


def _flow_store(state: "BondState | None"):
    """**章内的统一读写口** —— 真源 + 暂存（2026-09-17, B0 整章暂存）。

    | 读 / 写 | 落到哪 |
    |---|---|
    | `events()` | **真源 + 暂存**（合并；暂存 `seq` **接续真源** → 天然有序） |
    | `append_event` / `append_marker` / `enter_vn` | **暂存**（章内的一切**不进真源**） |

    ★ **章外（暂存为空）逐字节等价于真源** —— 所以这里**无条件**返回 overlay:
    调用方不需要判断"章在不在进行中"，也就不会有"漏改一个读点"的幽灵。

    缺省回落到全局 `deps.store()`（`BondState.store` 优先——决策 #31）。
    """
    return staging_store(getattr(state, "store", None) or _store())


def _stage_store(state: "BondState | None"):
    """**章内写入口** —— 章进行中返回**暂存** store（B0 整章暂存, 2026-09-17）。

    章内的一切（`vn_enter` / 板 / `vn_state` / memorial 标记）先落
    `soul/staging/events.jsonl`；见到 `vn_exit` 才由 `commit_staging` 整段
    append 进真源。**「拒绝」= 丢暂存**，真源里连"宣告它没发生"的痕迹都没有。

    ⚠️ **只用于写**。读（回放 / `in_vn` 推导 / 恢复窗口）仍走 `_flow_store` ——
    因为真源里躺着的才是**已发生的事**。
    """
    return _flow_store(state)


def _last_bond_seq(char_id: str, session_id: str, store=None) -> int:
    """最后一个 type=bond 事件的 seq（无 → 0）——草稿新鲜判据基准。"""
    try:
        evs = [e for e in (store or staging_store(_store())).events(char_id, session_id)
               if e.type == "bond"]
        return evs[-1].seq if evs else 0
    except Exception:                              # noqa: BLE001 — 读失败按不新鲜
        return -1


def _last_mmt_seq(char_id: str, session_id: str, store=None) -> int:
    """事件流中最后一条 **mmt 事件** 的 seq（预热新鲜度基准）。

    只计 mmt 事件（玩家对白/触发轮）——staged 预热自身的后续写入
    （vn_state 等 marker / bond 事件, 产生于快照之后）不参与判定, 否则
    自生成标记会把预热误判为过期而丢弃重建。
    """
    try:
        last = 0
        for e in (store or _store()).events(char_id, session_id):
            if getattr(e, "type", None) == "mmt":
                last = e.seq
        return last
    except Exception:                                # noqa: BLE001 — 读失败保守
        return 0


def _open_vn_seq(char_id: str, session_id: str, store=None) -> int:
    """最近一个 `vn_enter` marker 的 seq（无 → 0）——草稿归属哪一次在押段。

    ⚠️ 2026-09-17（B0）: 缺省改走 **overlay**（真源 + 暂存）—— 章内的 `vn_enter`
    在暂存里，只读真源会返回 0 → 草稿归属判定失效。
    """
    try:
        seq = 0
        for e in (store or staging_store(_store())).events(char_id, session_id):
            if e.is_marker and e.subtype == "vn_enter":
                seq = e.seq
        return seq
    except Exception:                              # noqa: BLE001 — 读失败 → 0（不 adopt）
        return 0


_DRAFT_FILE = "bond_draft.json"


def _draft_path(char_id: str, store=None) -> Path | None:
    try:
        st = store or _store()
        return Path(st.char_dir(char_id)) / "soul" / _DRAFT_FILE
    except Exception:                              # noqa: BLE001 — 缓存不可用降级
        return None


def _draft_boards(state: "BondState") -> list[dict]:
    """当前草稿 = [未落库的当前板?] + 引擎待发板队列（播放顺序）。"""
    boards: list[dict] = []
    if state.scene_obj is not None and not state.scene_state.committed:
        boards.append(state.scene_obj.to_dict())
    vn = state.vn
    for sc in list(getattr(vn, "_pending_boards", []) or []):
        boards.append(sc.to_dict() if hasattr(sc, "to_dict") else dict(sc))
    if state.pregen_obj is not None and state.pregen_scene is not None:
        # 预生成板（已生成待消费）也算"已生成未播放"——但它在引擎待发队列之外,
        # 只有引擎队列已空时它才是唯一后继（避免与队列重复计数）
        if not getattr(vn, "_pending_boards", None):
            boards.append(dict(state.pregen_scene))
    return boards


def _draft_save(state: "BondState", char_id: str, session_id: str) -> None:
    """落草稿旁路（原子写）。无可存内容 → 删旧档（宁缺勿错, 不留过期草稿）。"""
    try:
        store = _flow_store(state)
        path = _draft_path(char_id, store)
        if path is None:
            return
        boards = _draft_boards(state)
        if not boards:
            if path.is_file():
                path.unlink()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "boards": boards,
            "input": state.scene_input,
            "base_seq": _last_bond_seq(char_id, session_id, store),
            "vn_enter_seq": _open_vn_seq(char_id, session_id, store),
            "round": state.round,
            "ts": time.time(),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        replace_with_retry(tmp, path)
    except Exception as e:                         # noqa: BLE001 — 缓存失败降级
        logger.warning("草稿旁路写失败（降级, 不影响剧情）: %s", e)


def _draft_delete(char_id: str, store=None) -> None:
    try:
        path = _draft_path(char_id, store)
        if path is not None and path.is_file():
            path.unlink()
    except Exception:                              # noqa: BLE001
        pass


def _draft_load(char_id: str, session_id: str, store=None) -> list[dict] | None:
    """读草稿 → 板 payload 列表 | None（新鲜判据不过 → None + 顺手删档）。"""
    try:
        path = _draft_path(char_id, store)
        if path is None or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        boards = payload.get("boards")
        fresh = (isinstance(boards, list) and boards
                 and int(payload.get("base_seq", -1)) == _last_bond_seq(char_id, session_id, store)
                 and int(payload.get("vn_enter_seq", -1)) == _open_vn_seq(char_id, session_id, store))
        if not fresh:
            _draft_delete(char_id, store)                 # 过期/坏档 → 清掉, 别留矛盾数据
            return None
        out = [b for b in boards if isinstance(b, dict)]
        return out or None
    except Exception:                              # noqa: BLE001 — 坏档当 miss
        _draft_delete(char_id, store)
        return None


def _draft_pending(char_id: str, session_id: str, store=None) -> list[dict]:
    """只取草稿的**后继板**（boards[1:]）——进剧情时若首板由 prewarm 首场缓存给出,
    这一份用于恢复引擎待发队列（后续点击 0 LLM）。过期/坏档 → []。"""
    boards = _draft_load(char_id, session_id, store)
    return boards[1:] if boards and len(boards) > 1 else []


def _draft_queue(state: "BondState", char_id: str, session_id: str) -> int:
    """把草稿旁路的板**灌进引擎待发队列**（不动屏上场景）——回放交棒用。

    与旧 `_draft_adopt` 的区别（2026-09-12 修正）: 后者把草稿首板当"当前板"上屏;
    但回放路径屏上**已经有一场**（刚回放的那场）——草稿的板全是**后继**, 只能排队,
    否则要么顶掉刚回放的场景（`_advance_replay` 老行为: 最后一场回放被跳过）, 要么
    在进场时就丢掉它们（`_start_replay` 老行为: 直接 `_pregenerate` → 已生成的后继板
    被丢弃、重新生成一份, 真机/冒烟实测 `bond_pregen src=gen` 紧跟 `src=replay`）。

    Returns: 灌入的板数（0 = 无草稿/过期/引擎未就绪）。
    """
    if state.vn is None:
        return 0
    boards = _draft_load(char_id, session_id, _flow_store(state))
    if not boards:
        return 0
    try:
        rest = [BondScene.from_dict(b) for b in boards]
        for sc in rest:                              # 台账来源标记（决策 #35）
            sc._from_draft = True
        state.vn._pending_boards = rest          # 后续点击 0 LLM 领出（与正常完全同构）
        logger.info("bond_draft_queued %s/%s boards=%d", char_id, session_id, len(rest))
        return len(rest)
    except Exception as e:                         # noqa: BLE001 — 注入失败 → 走正常生成
        logger.warning("草稿排队失败（降级为正常生成）: %s", e)
        state.vn._pending_boards = []
        return 0


_PREWARM_FILE = "prewarm.json"


def _prewarm_cache_path(char_id: str, store=None) -> Path | None:
    """缓存文件路径（char_dir/soul/prewarm.json）; 拿不到 → None（跳过缓存）。"""
    try:
        st = store or _store()
        return Path(st.char_dir(char_id)) / "soul" / _PREWARM_FILE
    except Exception:                              # noqa: BLE001 — 缓存不可用降级
        return None


def _prewarm_cache_save(char_id: str, session_id: str, scene_dict: dict,
                        scene_input: str, chapter_title: str, store=None) -> None:
    """首场落地即写缓存（round==1 真实引擎; 原子写 tmp+rename 防半写）。"""
    try:
        path = _prewarm_cache_path(char_id, store)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "anchor_seq": _last_mmt_seq(char_id, session_id, store),
            "chapter_title": chapter_title,
            "scene": scene_dict,
            "input": scene_input,
            "ts": time.time(),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False),
                       encoding="utf-8")
        replace_with_retry(tmp, path)
    except Exception as e:                         # noqa: BLE001 — 缓存失败降级
        logger.warning("prewarm 缓存写失败（降级, 不影响剧情）: %s", e)


def _prewarm_cache_load(char_id: str, session_id: str, store=None):
    """读缓存 → (scene, scene_input, chapter_title) | None。

    新鲜判据: anchor_seq == 当前最新 mmt seq——期间玩家又聊/新触发轮 →
    上下文过期（与内存 staged_seq 同判据）→ miss; 坏文件/缺字段 → miss。
    """
    try:
        path = _prewarm_cache_path(char_id, store)
        if path is None or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("anchor_seq", -1)) != \
                _last_mmt_seq(char_id, session_id, store):
            return None                                  # 触发后又聊过 → 过期
        scene = BondScene.from_dict(payload.get("scene"))
        if not scene.paragraphs:
            return None
        return scene, str(payload.get("input") or ""), \
            str(payload.get("chapter_title") or "")
    except Exception:                                # noqa: BLE001 — 坏缓存当 miss
        return None


def _prewarm_cache_delete(char_id: str, store=None) -> None:
    """缓存失效（adopt 消费 / finish / 命中使用后）——旧首场不得与后续段混淆。"""
    try:
        path = _prewarm_cache_path(char_id, store)
        if path is not None and path.is_file():
            path.unlink()
    except Exception:                                # noqa: BLE001 — 删除失败无碍
        pass


def _log_scene(state: BondState, char_id: str, session_id: str, picked) -> None:
    """补录当前场景事件（append-only: 玩家裁决/收尾时落, 带 picked）。

    与 CLI 落库格式一致: {**scene.to_dict(), "input": 本场输入, "picked": 玩家裁决}
    ——回放兼容（filter_bond → BondScene.from_dict + input/picked）。

    2026-09-13 修正（审计 B6）: 置位 `scene_logged = True` 原先在 `try` **之外**，
    写失败（磁盘/权限/序列化）时仍置位 → 该板**永远不会再尝试落库**：
    回忆册/回放缺这一板, 草稿旁路（只收 `not committed` 的板）也不再含它。
    现在只在 append 真正成功后置位（`scene_state → COMMITTED`）——失败保持
    DELIVERED, 让下一次 `_log_scene`（下一次裁决/收尾/finish）重试。重复调用安全:
    `_log_scene_meta` 只播 marker 不播板正文, 重试不会重复写板。
    """
    if state.scene_state.committed or state.scene_obj is None:
        return
    scene = state.scene_obj
    sub = "story_end" if scene.is_end else "story_scene"
    try:
        _flow_store(state).append_event(char_id, session_id, make_event(
            "bond", sub,
            {**scene.to_dict(), "input": state.scene_input, "picked": picked}))
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断
        logger.warning("事件流 bond 写入失败（该板保持未落库, 下次裁决/收尾重试）: %s", e)
        return                                       # ← 不置位: 留一次重试机会
    state.scene_state = BoardLifecycle.COMMITTED


def _log_scene_meta(state: BondState, char_id: str, session_id: str,
                    scene: BondScene) -> None:
    """每场 marker 落库: 纪念子模式 + vn_state 恢复点（与 CLI 对齐）。"""
    store = _flow_store(state)
    try:
        if scene.memorial:
            # v2: 板含 `stage:memorial`（区间 = 本块内）
            store.append_marker(char_id, session_id, M_MEMORIAL_ENTER,
                                {"chapter_title": state.chapter_title, "v2": True})
            state.memorial_logged = True
        else:
            # v2 窗口结束（新生成一块 = 区间到块尾）: 补一条 exit —— marker 栈
            # （`session_status.in_memorial`）与现实一致（mmt_preset 的"纪念中"标签、
            # MMT digest 跳过判定都读它）。跨重启也成立: 创建 state 时已从流里初始化。
            # 2026-09-13: 抽成 `_close_memorial_window`——同一语义 bond_finish 也要用
            # （玩家在纪念板读完就收尾时, 这条路径永不发生 → marker 栈悬空, 审计 B5）。
            _close_memorial_window(state, char_id, session_id)
        vn = state.vn
        visual = (vn.director.state.to_dict()
                  if vn is not None and vn.director is not None else {})
        store.append_marker(char_id, session_id, M_VN_STATE, {
            "round": state.round, "seed": state.scene_input, "visual": visual})
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断
        logger.warning("事件流 marker 写入失败: %s", e)


def _close_memorial_window(state: BondState, char_id: str, session_id: str,
                           *, force: bool = False) -> bool:
    """v2 纪念窗口收尾: 有未闭合的 `memorial_enter` → 补一条 `memorial_exit`。

    2026-09-13 新增（审计 B5）: v2 的纪念区间 = 触发后到**本块块尾**, 没有 exit
    动作, 所以窗口闭合原先只挂在"下一板落地"那条路径上（`_log_scene_meta`）。
    玩家**在纪念板读完就收尾**时那条路径永不发生 → 事件流里留下一条未闭合的
    `memorial_enter`; 下一章同 `(char, session)` 首板会被 `_memorial_no_visuals`
    判成"纪念窗口内" → **整块跳过 emo/place 标注**（表情恒 nomal、背景不切、
    门控恒放行）。正常路径下 `vn_exit`/`session_end` 也会闭合该窗口, 这条 exit
    是**第二道保障**——两个 marker 写在同一个 try 里, 一起失败时才有区别。

    Args:
        force: `bond_finish` 用。收尾时引擎 `vn.in_memorial` **仍可能为 True**
            （玩家从未推进过任何一板 → 没有任何"新块解析成功"来复位它）, 而章已经
            结束, 此时必须强闭合; 非 force 路径（`_log_scene_meta`, 剧情进行中）
            保留该守卫——引擎还在纪念区间里时不是闭合时机。

    幂等: 无未闭合 enter → 不写。Returns: 是否补写了 exit。
    """
    if not state.memorial_logged:
        return False
    vn = state.vn
    if not force and vn is not None and vn.in_memorial:
        return False             # 引擎仍认为在窗口内（本块未解析完）→ 不是收尾时机
    try:
        _flow_store(state).append_marker(char_id, session_id, M_MEMORIAL_EXIT,
                                        {"v2": True, "auto": True})
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断
        logger.warning("纪念窗口闭合失败（marker 栈会停在 in_memorial）: %s", e)
        return False
    state.memorial_logged = False
    return True
