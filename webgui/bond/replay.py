# -*- coding: utf-8 -*-
"""`webgui.bond` 的**回放层**（C5, `docs/EXEC_SPLIT.md`）—— 0 LLM 的两条读路径。

## 放什么

· **resume 型回放**（中断重进 → 回放已记录前缀 → LLM 续写）: `replay_attempts`（按
  `vn_enter` 分段取"已记录前缀"）· `_interrupted_replay_queue`（只读回放队列）
· **认章定位**: `_pending_in_vn`（在押段判定）· `_title_from_events`（章标题追溯）·
  `_enter_title`（进场标题）· `_prev_chapter_quit`（上次是中途退出）
· **只读回放**（回忆册，`docs/DESIGN_COLLECTION_BOOK.md`）: `chapter_replay`
· 叙事化: `_narrativize`（板 payload → 人看的正文序列）

⚠️ **两种回放不是一回事**（别混）: resume 型回放"播完即交棒 live 续写"; 只读回放
（`chapter_replay` / 前端 `BondVN.enterReadonly`）**播完即停、0 LLM、不碰 `BondState`、
不写事件流**。

## 纪律

· 依赖方向: `replay` → `stores`（读事件流）+ `state`（类型）+ `core.session.*`（渲染/认章）;
  不反向 import `_impl`; 编排入口 `_start_replay` 留在 C8 的 `api.py`（它同时抓
  pregen / memorial / payload / draft）;
· ⚠️ **回放读的是 overlay**（`stores._flow_store` = 真源 + 章内暂存）: B0 整章暂存后
  "章进行中重进"若只读真源会看不到任何段（2026-09-20 修）——搬动时别把读点换成真源;
· 搬进来的代码**逐字未改**。
"""

from __future__ import annotations

import json
import time
from contract import NON_PICKS
from core.session.chapters import replayable_chapters
from core.session.events import M_VN_EXIT
from core.session.maintenance import abandoned_ranges
from core.session.staging import staging_store
from core.director.wiring import _trigger_title      # C11: 接线层（此前借道 apps.vn_cli）
from webgui import chat, deps                        # chat: 取内存态章节标题（_enter_title）
from webgui.bond.state import (
    BondState,
    _state,
)
from webgui.bond.stores import (
    _flow_store,
    _store,
)


def _narrativize(scene: dict, picked) -> dict:
    """回放场景: 板正文 + **选项组**（锁定, 高亮所选）——前端据此还原"当时给了什么
    选项、我选了什么"。

    **玩家的话语永远只体现为选项（2026-09-12 用户核对 BA 后定稿）**: 裁决句
    **不物化进段落**——它一旦当正文上屏就会被读成角色台词（真机报障:
    "睦月/便利屋68 + 你还打算对我怎么恶作剧？"）。所以回放里:
      · `choices` **保留**（用户 2026-09-12 反馈: 续看重进时"选哪个选项都一样",
        看不出去别 → 恢复选项组, 由前端画成锁定态 + 高亮 `picked`）;
      · `picked` 随场景带回（`BondScene.picked`, 见 core/bond/bond_story/scene.py）;
      · v1 旧档的 branches 顺接保持不变（旧档冻结）——分支段落是**剧情内容**
        （角色的反应）, 不是玩家的话, 该留。
    """
    out = dict(scene or {})
    out.pop("branches", None)
    paras = [dict(p) for p in (out.get("paragraphs") or []) if isinstance(p, dict)]
    records = scene.get("records") if isinstance(scene, dict) else None
    pick_text = str(picked).strip() if isinstance(picked, str) else ""
    if pick_text in NON_PICKS:              # "（继续）"这类推进指令不是裁决
        pick_text = ""
    out.pop("picked", None)
    if pick_text:
        # 回放 API 把 picked 从 scene 里摘出来单带回（tests/webgui/test_bond_replay.py），
        # 这里按参数重新放回——前端据此把选项组画成"已裁决"（锁定 + 高亮所选）。
        out["picked"] = pick_text
    if not (isinstance(records, list) and records):
        br = (scene or {}).get("branches") or {}
        if pick_text and isinstance(br, dict) and pick_text in br:
            paras += [dict(p) for p in br[pick_text] if isinstance(p, dict)]
    out["paragraphs"] = paras
    return out


def replay_attempts(char_id: str, session_id: str = "") -> list[dict]:
    """事件流 → 按 vn_enter 分段的回放列表（纯读, 幂等, 不碰状态机）。

    返回: [{from_seq, title, completed, interrupted,
            scenes: [{seq, input, picked, scene}]}]
      scene = 事件 payload 去 input/picked 的渲染字段——与 live BondVN
      renderScene 消费的 scene 同构（背景/表情/分支齐全）。
    分段规则: vn_enter 开新段; vn_exit 关段（completed 取 payload——False 即
    主动中断）; 段未关即遇新 vn_enter / 流尾 → interrupted=True。

    ⚠️ **读 overlay（真源 + 章内暂存）**, 不是只读真源（2026-09-20 修）:
    B0 整章暂存（2026-09-17）之后, **进行中的章一条都不在真源里**（全在
    `soul/staging/events.jsonl`, 见到 `vn_exit` 才整段 append）⇒ 只读真源的版本
    在"章进行中重进"时看不到任何段 → `_interrupted_replay_queue` 返回 None →
    **回放整条断掉**, 直接掉进现场生成（B 层冒烟实测: 重进后屏上出现的是新生成的
    板, 而不是已记录的选项前缀）。`_pending_in_vn` 当时改对了, 这里漏了。
    """
    try:
        evs = staging_store(_store()).events(char_id, session_id)
    except Exception:                                # noqa: BLE001 — 读失败空列表
        return []
    attempts: list[dict] = []
    cur: dict | None = None

    def close_interrupted():
        nonlocal cur
        if cur is not None:
            cur["interrupted"] = True
            attempts.append(cur)
            cur = None

    def open_attempt(from_seq: int, title: str):
        nonlocal cur
        close_interrupted()                 # 新段开 = 旧段未收尾 → 中断
        cur = {"from_seq": from_seq, "title": title, "completed": False,
               "interrupted": False, "scenes": []}

    for e in evs:
        t = getattr(e, "type", None)
        if t == "marker":
            if e.subtype == "vn_enter":
                open_attempt(e.seq,
                             str((e.payload.get("chapter_title") or "").strip()))
            elif e.subtype == "vn_exit" and cur is not None:
                cur["completed"] = bool(e.payload.get("completed"))
                cur["interrupted"] = not cur["completed"]
                attempts.append(cur)
                cur = None
        elif t == "bond":
            if cur is None:                 # 兼容旧事件: 无 vn_enter 直接开段
                open_attempt(e.seq, "")
            payload = e.payload or {}
            scene = {k: v for k, v in payload.items()
                     if k not in ("input", "picked")}
            cur["scenes"].append({
                "seq": e.seq,
                "input": str(payload.get("input") or ""),
                "picked": payload.get("picked"),
                "scene": scene,
            })
    close_interrupted()                     # 流尾未关段 → 中断
    return attempts


def _interrupted_replay_queue(char_id: str, session_id: str) -> tuple[list[dict], int] | None:
    """最新一条"有内容的未完成段" → (narrative-ized 场景列表, 段 enter_seq)。

    从段尾向前找 interrupted 且有 scenes 的段; 空壳重启段（0 场景——旧 bug 的
    重复 vn_enter 产物）自动跳过, 回退到更早的有内容段（如 seq12 场景 + seq18/21
    空壳）; **废弃段（vn_abandon 宣告, 被新章压掉）跳过**——档案在回放列表,
    不再自动续。无 → None（现场生成路径）。enter_seq 供"保留本段、压掉其余
    open"的定向废弃（防续写事件归属到更新的空壳段）。
    """
    try:
        ranges = abandoned_ranges(staging_store(_store()).events(char_id, session_id))
    except Exception:                                # noqa: BLE001 — 读失败无区间
        ranges = []
    for at in reversed(replay_attempts(char_id, session_id)):
        if at["interrupted"] and at["scenes"] and not any(
                a <= at["from_seq"] <= b for a, b in ranges):
            return ([_narrativize(s["scene"], s["picked"]) for s in at["scenes"]],
                    at["from_seq"])
    return None


def chapter_replay(char_id: str, from_seq: int, session_id: str = "") -> dict | None:
    """某章的全部板（只读回放载荷）; 章不存在/未结束 → None（纯读, 幂等）。

    只认 `replayable_chapters` 里的章——**未完/中断/废弃的章这里也拿不到**
    （不是前端藏起来, 是后端根本没有）, 与"渲染都不渲染"的口径同源。
    """
    try:
        evs = _store().events(char_id, session_id)
    except Exception:                                # noqa: BLE001 — 读失败按无此章
        return None
    try:
        want = int(from_seq)
    except (TypeError, ValueError):
        return None
    for ch in replayable_chapters(evs):
        if ch["from_seq"] != want:
            continue
        scenes = [{"seq": s["seq"], "input": s["input"], "picked": s["picked"],
                   "scene": _narrativize(s["scene"], s["picked"])}
                  for s in ch["scenes"]]
        return {"from_seq": ch["from_seq"], "to_seq": ch["to_seq"], "title": ch["title"],
                "boards": ch["boards"], "images": ch["images"], "scenes": scenes}
    return None


def _pending_in_vn(char_id: str, session_id: str) -> bool:
    """事件流视角: 最近一个 vn_enter 之后没有 vn_exit/vn_abandon（中断在押, in_vn）。

    ⚠️ 2026-09-17（B0 整章暂存）: 改读 **overlay**（真源 + 暂存）——
    章内的 `vn_enter` 在**暂存**里，只读真源会把"章进行中"漏判成"无在押"。
    """
    try:
        last_enter = last_exit = -1
        for e in staging_store(_store()).events(char_id, session_id):
            if getattr(e, "type", None) == "marker":
                if e.subtype == "vn_enter":
                    last_enter = e.seq
                elif e.subtype in ("vn_exit", "vn_abandon"):
                    last_exit = e.seq
        return last_enter > last_exit
    except Exception:                                # noqa: BLE001 — 读失败按无在押
        return False


def _title_from_events(char_id: str, session_id: str, store=None) -> str:
    """从事件流取最近一次 `mmt_trigger_bond_story` 的 chapter_title。

    进程重启后 `engine.trace`（内存）没了, 但触发事件在流里——标题屏文案仍要能出。
    """
    try:
        for e in reversed((store or _store()).events(char_id, session_id)):
            if e.type == "mmt" and e.subtype == "mmt_trigger_bond_story":
                return str((e.payload or {}).get("chapter_title") or "").strip()
    except Exception:                                # noqa: BLE001 — 读失败按无标题
        return ""
    return ""


def _enter_title(state: BondState, char_id: str, session_id: str) -> str:
    """进入响应里的章节标题（前端标题屏文案）。

    2026-09-11 真机修复（用户报"标题就是四个大字『羁绊剧情』"）: 标题屏取的是
    `/api/bond_start` 的 `chapter_title`，而 **adopt 就绪 / busy_wait 等返回路径
    漏带该字段** → 前端兜底成"羁绊剧情"。这里统一兜底: state → 内存 trace →
    事件流（触发事件 payload），拿到就记住。
    """
    t = (state.chapter_title or "").strip()
    if t:
        return t
    try:
        # 只在**已有**引擎上查（不触发引擎构造/新会话——进入路径不该有副作用）
        eng = chat._engines.get(char_id)
        t = (_trigger_title(eng) or "").strip() if eng is not None else ""
    except Exception:                                # noqa: BLE001 — 内存查失败继续流查
        t = ""
    if not t:
        t = _title_from_events(char_id, session_id, _flow_store(state))
    if t:
        state.chapter_title = t
    return t


def _prev_chapter_quit(char_id: str, session_id: str, store=None) -> bool:
    """上一次羁绊剧情是不是**中途退出**的（`vn_exit completed=False`）？

    ⚠️ **当前没有消费者**（用户 2026-09-20 裁决: *"不需要任何信息，直接静默重进
    就可以了，但这个 API 可以留着"*）——曾经拿它给 writer 注过「老师回来了」,
    **已撤**。留着是因为这是个干净的**事实查询**（只看真源, 倒序找最近一条 `vn_exit`）,
    以后要用来做"续章标记 / 统计 / 回忆册分组"都直接能用。

    判据: 倒序找**最近一条 `vn_exit`**; `payload.completed is False` = 上次是中断。
    没有 `vn_exit`（全新触发）→ False。
    """
    try:
        evs = (store or _flow_store(_state(char_id, session_id))).events(char_id, session_id)
    except Exception:                                # noqa: BLE001 — 读失败按"非中断"
        return False
    for e in reversed(list(evs)):
        if e.is_marker and e.subtype == M_VN_EXIT:
            return (e.payload or {}).get("completed") is False
    return False
