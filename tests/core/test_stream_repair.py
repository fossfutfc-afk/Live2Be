# -*- coding: utf-8 -*-
"""事件流维护单测（core/session/maintenance, 2026-09-07）: 废弃段自愈/压掉/过滤。

覆盖: 段扫描(attempt_spans) / 自愈(heal_plan——保留最新有内容 open 段, 只弃
有内容的其他段; 空壳由回放接入定向压掉) / 压掉(supersede_plan——含空壳, 作
关闭宣告) / 定向保留(close_other_opens_plan) / 区间过滤(exclude_abandoned)
/ store 应用幂等 / session_status 的 vn_abandon 关闭语义。
运行: python -m pytest tests/core/test_stream_repair.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.session import SessionStore
from core.session.events import make_event, marker
from core.session.maintenance import (
    abandon_open_attempts,
    abandon_opens_except,
    abandoned_ranges,
    attempt_spans,
    close_other_opens_plan,
    exclude_abandoned,
    heal_plan,
    supersede_plan,
)
from core.session.renderer import session_status

CHARACTER = "igusa_haruka"


def _real_like_events():
    """用户真实数据形态: 有内容段 A(12) 之后两个空壳重启段(18/21, 只有 marker)。"""
    return [
        marker("vn_enter", {}, seq=12),
        marker("vn_state", {"round": 1}, seq=13),
        make_event("bond", "story_scene",
                   {"paragraphs": [{"text": "x", "emotion": "nomal"}]}, seq=14),
        make_event("mmt", "mmt_chat", {"reply": "残留收尾"}, seq=15),
        marker("vn_enter", {}, seq=18),
        marker("vn_state", {}, seq=19),
        marker("vn_enter", {}, seq=21),
        marker("vn_state", {}, seq=22),
    ]


def test_attempt_spans_open_and_closed():
    evs = [
        marker("vn_enter", {"chapter_title": "A"}, seq=2),
        make_event("bond", "story_scene", {"paragraphs": []}, seq=4),
        marker("vn_exit", {"completed": True}, seq=9),
        marker("vn_enter", {"chapter_title": "B"}, seq=10),
    ]
    spans = attempt_spans(evs)
    assert len(spans) == 2
    assert spans[0]["close_kind"] == "exit" and spans[0]["completed"] is True
    assert spans[0]["scenes"] == 1 and spans[0]["title"] == "A"
    assert spans[0]["range_start"] == 2 and spans[0]["range_end"] == 4
    assert spans[1]["close_kind"] is None          # open(EOF)


def test_heal_plan_content_only_and_keeps_latest():
    """自愈: A 有内容 → 保留; 空壳段(无内容)不产生计划（由回放接入定向压掉）。"""
    plan = heal_plan(_real_like_events())
    assert plan == []
    # 有内容的其他段才产生计划
    evs = _real_like_events() + [
        marker("vn_enter", {}, seq=30),
        make_event("bond", "story_scene", {"paragraphs": [{"text": "y", "emotion": "nomal"}]}, seq=31),
    ]
    plan = heal_plan(evs)                         # 最新有内容 = 31 段 → 弃 A(12..15)
    assert [(s, e) for s, e, _ in plan] == [(12, 15)]


def test_supersede_plan_and_close_other_opens():
    evs = _real_like_events()
    assert sorted(s for s, _, _ in supersede_plan(evs)) == [12, 18, 21]
    # 定向: 保留 A(12) → 压 18/21（空壳也压——关闭宣告, 防续写归属错乱）
    plan = close_other_opens_plan(evs, keep_enter_seq=12)
    assert sorted(s for s, _, _ in plan) == [18, 21]


def test_exclude_abandoned_drops_bond_only_in_ranges():
    evs = _real_like_events() + [
        marker("vn_abandon", {"start_seq": 18, "end_seq": 21, "note": "x"}, seq=23),
    ]
    assert abandoned_ranges(evs) == [(18, 21)]
    # 区间内放一条 bond → 被滤; mmt 保留; 区间外 bond 保留
    evs2 = evs + [
        make_event("bond", "story_scene", {"paragraphs": []}, seq=20),
        make_event("bond", "story_scene", {"paragraphs": []}, seq=25),
    ]
    out = exclude_abandoned(evs2)
    assert not any(e.seq == 20 for e in out)       # 区间内 bond 滤
    assert any(e.seq == 25 for e in out)           # 区间外保留
    assert any(e.seq == 14 for e in out)           # A 的内容段保留（未废弃）
    assert any(e.seq == 15 for e in out)           # mmt 保留
    assert exclude_abandoned(_real_like_events()) == _real_like_events()


# ---------------------------------------------------------------------------
# store 集成: 应用幂等 + 定向废弃 + session_status 关闭语义
# ---------------------------------------------------------------------------

def test_abandon_supersede_store_and_idempotent(tmp_path):
    st = SessionStore(tmp_path)
    sid = st.create(CHARACTER).session_id
    st.enter_vn(CHARACTER, sid, "A")
    st.append_event(CHARACTER, sid, make_event(
        "bond", "story_scene",
        {"paragraphs": [{"text": "半截。", "emotion": "nomal"}]}))
    assert session_status(st.events(CHARACTER, sid))["in_vn"] is True

    n1 = abandon_open_attempts(st, CHARACTER, sid)   # 新章压掉全部在押
    assert n1 == 1
    evs = st.events(CHARACTER, sid)
    ab = [e for e in evs if e.subtype == "vn_abandon"]
    assert len(ab) == 1
    assert session_status(evs)["in_vn"] is False      # 关闭语义生效
    assert not any(e.type == "bond" for e in exclude_abandoned(evs))

    assert abandon_open_attempts(st, CHARACTER, sid) == 0   # 幂等


def test_abandon_opens_except_keeps_replayed_segment(tmp_path):
    """回放接入: A(内容) + 空壳 18/21 → 只压空壳, A 保持 open（续写归属正确）。"""
    st = SessionStore(tmp_path)
    sid = st.create(CHARACTER).session_id
    st.enter_vn(CHARACTER, sid, "")
    enter_a = st.events(CHARACTER, sid)[-1].seq      # A 段 vn_enter seq
    st.append_event(CHARACTER, sid, make_event(
        "bond", "story_scene",
        {"paragraphs": [{"text": "半截。", "emotion": "nomal"}]}))
    st.append_marker(CHARACTER, sid, "vn_enter", {})
    st.append_marker(CHARACTER, sid, "vn_enter", {})

    n = abandon_opens_except(st, CHARACTER, sid, keep_enter_seq=enter_a)
    assert n == 2                                     # 两个空壳被压
    evs = st.events(CHARACTER, sid)
    assert len([e for e in evs if e.subtype == "vn_abandon"]) == 2
    assert session_status(evs)["in_vn"] is True       # A 仍在押 → 可回放续写
    # A 的内容段保留（过滤只丢空壳区间——空壳本来无内容）
    out = exclude_abandoned(evs)
    assert any(e.type == "bond" for e in out)
