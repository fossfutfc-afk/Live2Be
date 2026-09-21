# -*- coding: utf-8 -*-
"""`webgui.bond` 的**看门狗**（C8, `docs/EXEC_SPLIT.md`）—— 把"卡住 = 永久卡住"变成"卡住 = 降级放行"。

## 放什么

`_watchdog`（`bond_status` 顺手调用, 前端在轮询 ⇒ 这是唯一稳定的检查点）· `_lanes_idle` ·
`_lane_writer_alive` · `_gate_stalled` · `_force_scene_ready` · `_thread_alive`。

三条门的兜底（阈值在 `webgui/deps.py`, 测试会把它们调小/调负来逼出兜底）:
① **忙态**（`busy` 卡住且生成线程都不在 → 复位, 防"点击永久无响应"）;
② **视觉门**（emo/place 双路未齐且无积压无在途 → 兜底放行）;
③ **预生成消费门**（同上）。

## 纪律

· 依赖方向: `watchdog` → `lanes`（就绪门控判定）+ `deps`（阈值/接缝）+ `util`; **单向** ——
  `api` 反过来 import 这里的 `_watchdog`, 这里**不许** import `api`;
· ⚠️ 阈值一律 `deps.*`（`monkeypatch.setattr(webgui.bond, …)` 是静默 no-op, 见 C1a）;
· 搬进来的代码**逐字未改**。
"""


from __future__ import annotations

import time
import logging
from webgui import deps
from webgui.bond.lanes import (
    _fallback_fill,
    _scene_obj_visual_ready,
    _scene_visual_ready,
)
from webgui.bond.util import _ms_since

logger = logging.getLogger(__name__)


def _thread_alive(th) -> bool:
    try:
        return bool(th is not None and th.is_alive())
    except Exception:                                # noqa: BLE001 — 判定失败按不活
        return False


def _lanes_idle(state: "BondState") -> bool:
    """标注 lane 是否**真的**空闲（无积压 且 无在途）。

    2026-09-13 修正（审计 A6）: 原先只看 `qsize()`——worker 一旦把场景从队列取走、
    正在 `await` 标注 LLM, `qsize()==0` 就返回 True。于是**一次健康的、只是慢
    （>25s）的标注调用期间**, 看门狗就会开火强推兜底（不需要 worker 卡死）。
    """
    if getattr(state, "_lane_inflight", 0) > 0:
        return False                                 # 有 worker 正在标注（在途）
    for q in (state._anno_queue, state._place_queue):
        try:
            if q is not None and q.qsize() > 0:
                return False
        except Exception:                            # noqa: BLE001
            continue
    return True


def _lane_writer_alive(state: "BondState") -> bool:
    """是否还有标注 worker 线程在跑（诊断/测试用, **不是**兜底判据）。

    ⚠️ 2026-09-13 复核: 这个信号在真实会话里**恒为 True**, 不能拿来做"没人会再来标"
    的判据。证据链: 两个 worker 只在收到 `None` 哨兵时 `break`
    （`_anno_worker`/`_place_worker` 的 `if scene is None`）, 而全仓 `.put(` 只有
    两处、都是投场景（`_anno_queue.put(scene)` / `_place_queue.put(scene)`）——
    **没有任何地方投 `None`**（`grep put(None)` 零命中）。所以 worker 一旦启动就
    阻塞在 `q.get()` 上活到进程结束, `_anno_started`/`_place_started` 永不复位。
    曾用它做 `_gate_stalled` 的合项 → ②③ 看门狗在稳态**永不触发**, 把真阳性
    （lane 再也不回来 = 真机"已等待 110s"那个形态）也一起关掉了。
    保留本函数仅作观测/测试。
    """
    if state._anno_started and _thread_alive(state._anno_thread):
        return True
    if state._place_started and _thread_alive(state._place_thread):
        return True
    return False


def _gate_stalled(state: "BondState") -> bool:
    """视觉门兜底的**前置条件**: 没有积压、也没有在途标注。

    `_lanes_idle` 本身已经是 A6 要的语义（2026-09-13 收紧: 队列深度 **且** 在途
    计数）——worker 把场景取走正在 `await` 时 `_lane_inflight > 0`, 不会被误判成
    空闲。所以这里**不再**叠加"线程死活"判据（那会让兜底在稳态永不触发, 见
    `_lane_writer_alive` 的说明）。

    代价评估: 若 lane 真的挂住（worker 死在 `await` 里, 线程对象仍"存活" →
    在途计数不归零）, 兜底不会开火 → `bond_turn` 被 `_scene_ready_or_busy` 一直拒
    → 玩家卡在"视觉标注中"。此时仍有 ①忙态看门狗、前端 90s 软上限与 8s 降级渲染
    兜着, 不至于全黑。更保守的做法是改判"**无进展 N 秒**"（如 90s）而不是"无线程"
    ——留作后续（需要给 lane 记最后进展时间戳）。
    """
    return _lanes_idle(state)


def _force_scene_ready(state: "BondState", scene) -> None:
    """强制把场景标成视觉就绪（兜底放行用）: 空 emotion 回填 + place 标记。"""
    if scene is None:
        return
    try:
        _fallback_fill(scene)
    except Exception:                                # noqa: BLE001 — 兜底失败也要放行
        pass
    try:
        scene._place_done = True
    except Exception:                                # noqa: BLE001
        pass


def _watchdog(state: "BondState", char_id: str, session_id: str) -> None:
    """看门狗（bond_status 顺手调用）: 把"卡住=永久卡住"变成"卡住=降级放行"。

    三类异常各有兜底:
      ① **忙态卡死**: busy 超 BUSY_WATCHDOG_MS 且生成/预生成线程都不在 → 复位
         （线程丢失/异常退出的兜底; 活着的线程不抢——它还在生成）。
      ② **视觉门卡死**: 当前场景 emotion/place 连续 GATE_WATCHDOG_MS 未就绪且
         **没有积压/没有在途标注**（见 `_gate_stalled`）→ 强制兜底就绪
         （表情精度损失换"能推进"）。
      ③ **预生成消费门卡死**: 同 ② 作用于 pregen 场景（否则"继续"键永久无响应）。

    **2026-09-13（审计 A6）**: ②③ 原先只判 `_lanes_idle`（= 队列深度为 0）——
    那在"worker 正把场景取走并 await 标注"时也成立, 于是**一次健康的慢调用
    （>25s）就会被强制兜底**; 而兜底产物会随 `_log_scene` 进 append-only 真源
    （假 `nomal`/假 `_place_done`）, 晚到的真标注再也回不去。
    修法 = 给 `_lanes_idle` 加**在途判据**（`_lane_inflight`）: 慢但在途 → 等它;
    积压/在途都没有 → 降级。**注意别再加"线程死活"合项**——那会让兜底在稳态
    永不触发（原因见 `_lane_writer_alive`）。
    """
    now = time.monotonic()
    # ① 忙态
    if state.busy:
        state.busy_since = state.busy_since or now
        if (_ms_since(state.busy_since) > deps.BUSY_WATCHDOG_MS
                and not _thread_alive(state._gen_thread)
                and not _thread_alive(state._pregen_thread)):
            logger.warning(
                "bond 看门狗: 忙态 %dms 且生成线程均不在 → 复位（防点击永久无响应） %s/%s",
                _ms_since(state.busy_since), char_id, session_id)
            state.busy = False
            state.busy_since = 0.0
    else:
        state.busy_since = 0.0
    # ② 视觉门
    if _scene_visual_ready(state):
        state.gate_since = 0.0
    else:
        state.gate_since = state.gate_since or now
        if (_ms_since(state.gate_since) > deps.GATE_WATCHDOG_MS and _gate_stalled(state)
                and not state.busy):
            logger.warning(
                "bond 看门狗: 视觉门 %dms 未就绪且无积压/无在途 → 兜底放行 %s/%s",
                _ms_since(state.gate_since), char_id, session_id)
            _force_scene_ready(state, state.scene_obj)
            state.gate_since = 0.0
    # ③ 预生成消费门
    pregen = getattr(state, "pregen_obj", None)
    if pregen is None or _scene_obj_visual_ready(state, pregen):
        state.pregen_gate_since = 0.0
    else:
        state.pregen_gate_since = state.pregen_gate_since or now
        if (_ms_since(state.pregen_gate_since) > deps.PREGEN_GATE_WATCHDOG_MS
                and _gate_stalled(state) and not state.busy):
            logger.warning(
                "bond 看门狗: 预生成消费门 %dms 未通过且无积压/无在途 → 兜底放行 %s/%s",
                _ms_since(state.pregen_gate_since), char_id, session_id)
            _force_scene_ready(state, pregen)
            state.pregen_gate_since = 0.0
