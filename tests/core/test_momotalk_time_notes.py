# -*- coding: utf-8 -*-
"""时间注记接线单测（T13）—— 注记真的进了 MMT 的 messages。

与 `tests/core/test_mmt_round_protocol.py` 同一套桩口径（**脚本返回 dict, 不是 str**）。
VALUE: 这条测的是**接线**（`momotalk.agent_turn` 的 P17 槽位），
不是注记文本本身（那在 `test_worldtime_prompt.py`）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.momotalk import MomoTalkEngine        # noqa: E402
from core.session.store import SessionStore     # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CHARACTER = "igusa_haruka"


class ScriptedLLM:
    """捕获每次调用的 messages（digest 轮给空包, 其余给一句台词）。"""

    def __init__(self):
        self.snapshots: list[list[dict]] = []

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        head = messages[0]["content"]
        if "记录员" in head:
            return {"episodes": []}
        if "整理者" in head:
            return {"decisions": [], "evidence": [], "affection_exp_delta": 0}
        return {"messages": [{"text": "嗯……早、早上好！"}]}


def _engine(tmp_path, llm) -> MomoTalkEngine:
    store = SessionStore(data_root=tmp_path)
    eng = MomoTalkEngine(ROOT / "config" / "characters", llm, store=store)
    name = eng.start_session(CHARACTER)
    root = store.create(CHARACTER, name)
    eng.attach_session(root.session_id)
    return eng


def _joined(llm: ScriptedLLM) -> str:
    return "\n".join((m.get("content") or "") for m in llm.snapshots[-1])


def test_time_notes_reach_mmt_messages(tmp_path):
    """★ 时间注记必须出现在本轮 messages 里 —— 且**只剩现实口径**。

    2026-09-17（时间轴换代）: `【现在是】1年4月·春·白天`（剧情时间）**已删** ——
    它读的是作废的剧情游标，留着会让两个时间事实并排（`ESSAY §5.2` 的坑）。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    eng.agent_turn("老师，早上好！")
    joined = _joined(llm)
    assert "【手机上的日期】" in joined, joined[-400:]
    # 手机日期带归因 + 使用边界
    assert "这是你手机上显示的日期" in joined and "问起" in joined
    # ★ 核心断言: 剧情时间注记不再出现
    assert "【现在是】" not in joined, joined[-400:]
    print("    接线: 【手机上的日期】进了 messages; 【现在是】已删 ✓")


def test_notes_before_task_card(tmp_path):
    """注记在 task 卡**之前**（时间事实比目标层更基础）。"""
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    eng.agent_turn("早")
    msgs = llm.snapshots[-1]
    idx_note = next((i for i, m in enumerate(msgs)
                     if "【手机上的日期】" in (m.get("content") or "")), None)
    assert idx_note is not None
    # 时间注记之后仍应有内容（task 卡 / user）——即它不是最后一条
    assert idx_note < len(msgs) - 1, (idx_note, len(msgs))
    print(f"    注记在第 {idx_note + 1}/{len(msgs)} 条（后有 task 卡/user）")


def test_no_store_skips_time_notes(tmp_path):
    """★ 无 store（`self._store is None`）→ 时间注记**整组跳过**, 不炸。

    这是 `test_promptkit_baseline._mmt_engine` 的形态（不传 store）——
    钉住它, 免得以后有人以为"注记丢了"。
    """
    llm = ScriptedLLM()
    eng = MomoTalkEngine(ROOT / "config" / "characters", llm)   # ← 不传 store
    eng.start_session(CHARACTER)
    eng.agent_turn("早")
    joined = _joined(llm)
    if "【手机上的日期】" in joined:
        for i, m in enumerate(llm.snapshots[-1]):
            c = m.get("content") or ""
            if "【手机上的日期】" in c or "【现在是】" in c:
                print(f"      [消息 {i}/{len(llm.snapshots[-1])} role={m['role']}] {c[:70]}")
        print(f"      engine._store = {eng._store!r}")
    assert "【现在是】" not in joined
    assert "【手机上的日期】" not in joined
    # 但 P16 与 task 卡照常（不因缺 store 而整轮退化）
    assert "羁绊进度事实" in joined and "本回合任务" in joined
    print("    无 store: 时间注记跳过（P16/卡不受影响）")


def test_vn_brain_segment_carries_time_but_no_phone(tmp_path):
    """★ VN 侧（`load_brain_segment`）也得有**现实间隔**, 但**不给手机日期**。

    VN 无自由打字通道（`CLAUDE.md §6.3`）→ 玩家问不出"今天几号" → 注了只污染创作。

    2026-09-17（时间轴换代）: 原断言"VN 有**剧情时间**注记"已作废 ——
    剧情时间注记整条删除; VN 现在只剩**现实间隔**（壁钟派生, 同源）。
    """
    from core.momotalk import load_brain_segment
    store = SessionStore(data_root=tmp_path)
    root = store.create(CHARACTER, "测试")
    store.append_event(CHARACTER, root.session_id,
                       event=__import__("core.session.events", fromlist=["x"])
                       .make_event("mmt", "chat", {"player": "在吗", "reply": "在的"}))
    seg = load_brain_segment(store, CHARACTER, "伊草 遥香",
                             ROOT / "config" / "characters")
    assert "【手机上的日期】" not in seg, "VN 不该注手机日期"
    assert "【现在是】" not in seg, "剧情时间注记已删"
    # 现实间隔在（上一条事件就是刚才）—— 这是 VN 侧**唯一**的时间注记
    assert "【她刚刚还在和老师说话】" in seg, seg[-300:]
    print("    VN: 只有现实间隔注记; 无手机日期、无剧情时间 ✓")


if __name__ == "__main__":
    import tempfile

    for fn in (test_time_notes_reach_mmt_messages,
               test_notes_before_task_card,
               test_no_store_skips_time_notes,
               test_vn_brain_segment_carries_time_but_no_phone):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("all time-note wiring tests passed")
