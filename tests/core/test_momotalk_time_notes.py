"""时间注记接线单测（T13）—— 注记真的进了 MMT 的 messages。

与 `tests/core/test_mmt_round_protocol.py` 同一套桩口径（**脚本返回 dict, 不是 str**）。
VALUE: 这条测的是**接线**（`momotalk.agent_turn` 的 P17 槽位），
不是注记文本本身（那在 `test_worldtime_prompt.py`）。
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from core.mmt.engine import MomoTalkEngine
from core.session.store import SessionStore
from llm import task_labels as T
from tests import stub_tasks

ROOT = Path(__file__).resolve().parents[2]
CHARACTER = "igusa_haruka"


class ScriptedLLM:
    """捕获每次调用的 messages（digest 轮按 **task** 给空包, 主链给一句台词）。"""

    def __init__(self):
        self.snapshots: list[list[dict]] = []
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.snapshots.append([dict(m) for m in messages])
        self.tasks.append(task)
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                    # digest 两轮 → 空包
            return reply
        if task in T.MAIN:
            return '{"text": "嗯……早、早上好！"}'
        raise stub_tasks.unknown_task(task)


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
    # P16 羁绊进度注记**已封印**（2026-10-08）⇒ 现在断言它**不在**; task 卡照常
    assert "【剧情时机】" not in joined and "羁绊进度事实" not in joined
    assert "本回合任务" in joined
    print("    无 store: 时间注记跳过（P16 已封印 / 卡不受影响）")


def test_vn_brain_segment_carries_time_but_no_phone(tmp_path):
    """★ VN 侧（`load_brain_segment`）也得有**现实间隔**, 但**不给手机日期**。

    VN 无自由打字通道（产品决策, 见 `AGENTS.md`）→ 玩家问不出"今天几号" → 注了只污染创作。

    2026-09-17（时间轴换代）: 原断言"VN 有**剧情时间**注记"已作废 ——
    剧情时间注记整条删除; VN 现在只剩**现实间隔**（壁钟派生, 同源）。
    """
    from core.mmt.engine import load_brain_segment
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


# ---------------------------------------------------------------------------
# 特殊日期（现实日历②）的接线 —— 2026-09-17 接入
# ---------------------------------------------------------------------------

FESTIVE_DAY = date(2026, 9, 10)


def _pin_table(monkeypatch, tmp_path, *, day: int = 10,
               name: str = "教师节") -> None:
    """把默认节日表指向一个只含一个日子的临时表（**测试必须自带表**）。

    不指的话测试会读真表 `config/eggs/festivals.json` —— 那意味着
    **在 12/25 跑测试会看到圣诞注记**, 结果随日历而变。
    """
    import core.worldtime.realtime as rt
    p = tmp_path / "festivals.json"
    p.write_text(json.dumps({"festivals": [
        {"id": "x", "month": 9, "day": day, "name": name, "proactive": True},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(rt, "DEFAULT_TABLE_PATH", p)


def _at(day: date) -> datetime:
    """把"今天"变成一个**钉死的时刻**（正午, 带 `REAL_TZ`）。

    传给 `agent_turn(now=…)` —— 那一个值同时决定: 手机日期、现实间隔、节日判定、
    台账记下的日期。**不 patch 任何内部函数**（`agent_turn` 为此加了 `now` 形参,
    同 `age_days(*, now)` 的纪律）。
    """
    return datetime(day.year, day.month, day.day, 12, 0,
                    tzinfo=timezone(timedelta(hours=8)))


def test_realtime_note_reaches_mmt_messages(tmp_path, monkeypatch):
    """★ 节日注记进 messages, 且**与手机日期同源**、位于其后。"""
    _pin_table(monkeypatch, tmp_path)
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)

    eng.agent_turn("老师，早上好！", now=_at(FESTIVE_DAY))
    joined = _joined(llm)
    assert "手机日历上标着：教师节" in joined, joined[-500:]
    # 归因 + 许可半句（B: 主动发起祝福的入口）
    assert "手机日历上标着" in joined and "主动" in joined
    # ★ 同源: 手机日期显示的就是那个钉死的日子（不是壁钟的今天）
    assert "2026年9月10日" in joined, joined[-500:]
    # 次序: 手机日期在节日之前
    i_phone = joined.index("【手机上的日期】")
    i_fest = joined.index("手机日历上标着")
    assert i_phone < i_fest, (i_phone, i_fest)
    print('    接线: 节日注记进了 messages; 与手机日期同一个"现在" ✓')


def test_realtime_note_fires_once_then_never(tmp_path, monkeypatch):
    """★ **调用即记账**: 那天说过了就不再提, 第二天也不再提。

    表里放的是 9/12 的节日, 让"第一次说话"发生在它之前 ——
    否则新档的地板（今天−1 天）会把它挡掉, 测不到"说过了"这件事。
    """
    _pin_table(monkeypatch, tmp_path, day=12)
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)

    eng.agent_turn("早", now=_at(date(2026, 9, 10)))       # 还没到 → 不注
    assert "手机日历上标着" not in _joined(llm), "还没到的日子不该注"
    eng.agent_turn("老师？", now=_at(date(2026, 9, 12)))    # 当天 → 注一次
    assert "手机日历上标着" in _joined(llm)
    eng.agent_turn("在吗", now=_at(date(2026, 9, 12)))      # 同一天第二轮 → 不再注
    assert "手机日历上标着" not in _joined(llm), "同一天第二次不该再注"
    eng.agent_turn("老师——", now=_at(date(2026, 9, 13)))   # 第二天 → 不再注
    assert "手机日历上标着" not in _joined(llm), "第二天不该再注"

    # 台账真落了盘, 且按 **slug** 分桶（不是 display_name）
    import core.worldtime.realtime as rt
    clock = rt.load_clock(eng._store.world_dir())
    assert list(clock["fired"]) == [CHARACTER], clock["fired"]
    # ⚠️ 键 = `{id}:{那期的年}`; **值 = "说出口的那天"**, 不是节日那天
    #    （她的日历上没有"节日那天", 只有"我什么时候知道的"）
    assert clock["fired"][CHARACTER] == {"x:2026": "2026-09-12"}, clock["fired"]
    print(f"    台账: {clock['fired']} ✓")


def test_realtime_not_wired_into_vn(tmp_path, monkeypatch):
    """★ 边界 1: **VN 不注节日**（同"不注手机日期"的理由）。

    VN 没有自由打字通道 → 问不出"今天什么日子"; 注了会诱使 writer 写出
    "老师，今天是圣诞节呢"而场景里连圣诞树都没有。
    """
    _pin_table(monkeypatch, tmp_path)
    from core.mmt.engine import load_brain_segment
    store = SessionStore(data_root=tmp_path)
    root = store.create(CHARACTER, "测试")
    store.append_event(CHARACTER, root.session_id,
                       event=__import__("core.session.events", fromlist=["x"])
                       .make_event("mmt", "chat", {"player": "在吗", "reply": "在的"}))
    seg = load_brain_segment(store, CHARACTER, "伊草 遥香",
                             ROOT / "config" / "characters")
    assert "手机日历上标着" not in seg, seg[-300:]
    print("    VN: 不注节日（与不注手机日期同一条边界）✓")


def test_no_store_skips_realtime_notes(tmp_path, monkeypatch):
    """★ 无 store → 节日注记也整组跳过（**不去读表**, 更不该写台账）。

    与 `test_no_store_skips_time_notes` 同一条纪律: 壁钟派生的东西跟着 store 走。
    """
    _pin_table(monkeypatch, tmp_path)
    llm = ScriptedLLM()
    eng = MomoTalkEngine(ROOT / "config" / "characters", llm)   # ← 不传 store
    eng.start_session(CHARACTER)
    eng.agent_turn("早", now=_at(FESTIVE_DAY))
    assert "手机日历上标着" not in _joined(llm)
    print("    无 store: 节日注记跳过 ✓")


def test_notes_share_one_now(tmp_path, monkeypatch):
    """★ 手机日期与节日判定**同源** —— 钉死 12/25 就该看到 12/25 与圣诞。

    这是接线时探针抓到的: 两条注记各自读壁钟时, 会出现
    "【手机上的日期】9月19日" 与 "（手机日历上标着：圣诞节）" 同轮并存。
    """
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"festivals": [
        {"id": "christmas", "month": 12, "day": 25, "name": "圣诞节",
         "proactive": True},
    ]}, ensure_ascii=False), encoding="utf-8")
    import core.worldtime.realtime as rt
    monkeypatch.setattr(rt, "DEFAULT_TABLE_PATH", p)
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    eng.agent_turn("老师！", now=_at(date(2026, 12, 25)))
    joined = _joined(llm)
    assert "2026年12月25日" in joined, joined[-400:]
    assert "手机日历上标着：圣诞节" in joined, joined[-400:]
    print("    同源: 手机日期 12/25 与圣诞注记一致 ✓")


if __name__ == "__main__":
    import tempfile

    for fn in (test_time_notes_reach_mmt_messages,
               test_notes_before_task_card,
               test_no_store_skips_time_notes,
               test_vn_brain_segment_carries_time_but_no_phone):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("all time-note wiring tests passed")
