# -*- coding: utf-8 -*-
"""bond 回放接口单测（2026-09-07）: 事件流 → 按 vn_enter 分段的回放列表。

原料即终态（裁决时落库 + 门控保证标注就绪）——0 LLM 纯读; 场景 dict 去掉
input/picked（渲染字段与 live 同构）, picked/input 单独带回（自动跟随/未来
handoff 用）。覆盖: 完整段 / 中断段 / 多段连续 / 空会话。
运行: python -m pytest tests/webgui/test_bond_replay.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.session import SessionStore
from core.session.events import make_event
from webgui import bond, chat

CHARACTER = "igusa_haruka"
TITLE_A = "放学后的约定"
TITLE_B = "雨天的杂草"


def _with_store(tmp_path):
    """SessionStore(tmp) + chat._store 注入（bond._store 读 chat._store）。"""
    old = chat._store
    st = SessionStore(tmp_path)
    chat._store = st
    return st, old


def _sid(st, char_id=CHARACTER):
    return st.create(char_id).session_id


def _scene_event(st, sid, seq_text, *, choices=None, picked=None,
                 input_="（继续）"):
    payload = {"paragraphs": [{"text": seq_text, "emotion": "nomal"}],
               "is_end": False}
    if choices:
        payload["choices"] = choices
        payload["branches"] = {c: [{"text": f"分支：{c}", "emotion": "nomal"}]
                               for c in choices}
    if picked is not None:
        payload["picked"] = picked
    payload["input"] = input_
    return st.append_event(CHARACTER, sid, make_event(
        "bond", "story_scene", payload))


def test_replay_completed_attempt(tmp_path):
    """完整走完: 一段 vn_enter → 2 场 → vn_exit(completed) → 单段完成。"""
    st, old = _with_store(tmp_path)
    try:
        sid = _sid(st)
        st.enter_vn(CHARACTER, sid, TITLE_A)
        e1 = _scene_event(st, sid, "第一场。", choices=["看杂草", "问名字"],
                          picked="看杂草", input_="（旁白）种子……")
        e2 = _scene_event(st, sid, "第二场。", picked=None)
        st.append_marker(CHARACTER, sid, "vn_exit", {"completed": True})

        ats = bond.replay_attempts(CHARACTER, sid)
        assert len(ats) == 1
        at = ats[0]
        assert at["title"] == TITLE_A
        assert at["completed"] is True and at["interrupted"] is False
        assert [s["seq"] for s in at["scenes"]] == [e1.seq, e2.seq]
        # 场景 = payload 去 input/picked（渲染同构）; picked/input 单独带回
        s1 = at["scenes"][0]
        assert s1["scene"]["paragraphs"][0]["text"] == "第一场。"
        assert "input" not in s1["scene"] and "picked" not in s1["scene"]
        assert s1["scene"]["branches"]["看杂草"]
        assert s1["picked"] == "看杂草"
        assert s1["input"] == "（旁白）种子……"
        assert at["scenes"][1]["picked"] is None
        print("    replay: 完整段单段 2 场, scene 去 input/picked, picked 单独带")
    finally:
        chat._store = old


def test_replay_interrupted_then_second_attempt(tmp_path):
    """中断（无 vn_exit）后第二次进入: 两段, 前段中断, 后段进行中。"""
    st, old = _with_store(tmp_path)
    try:
        sid = _sid(st)
        st.enter_vn(CHARACTER, sid, TITLE_A)
        _scene_event(st, sid, "第一场。", choices=["A", "B"], picked="A")
        # 无 vn_exit——中断; 直接第二次 vn_enter
        st.enter_vn(CHARACTER, sid, TITLE_B)
        e2 = _scene_event(st, sid, "第二段首场。")
        # 流尾未关段

        ats = bond.replay_attempts(CHARACTER, sid)
        assert len(ats) == 2
        a1, a2 = ats
        assert a1["title"] == TITLE_A
        assert a1["completed"] is False and a1["interrupted"] is True
        assert len(a1["scenes"]) == 1
        assert a2["title"] == TITLE_B
        assert a2["interrupted"] is True               # 流尾未关 → 中断
        assert [s["seq"] for s in a2["scenes"]] == [e2.seq]
        assert a2["from_seq"] > a1["from_seq"]
        print("    replay: 中断段 → 新段开; 流尾未关段 = 中断")
    finally:
        chat._store = old


def test_replay_graceful_midquit_is_interrupted(tmp_path):
    """主动中途退出（vn_exit completed=False）→ 该段 completed=False。"""
    st, old = _with_store(tmp_path)
    try:
        sid = _sid(st)
        st.enter_vn(CHARACTER, sid, TITLE_A)
        _scene_event(st, sid, "第一场。")
        st.append_marker(CHARACTER, sid, "vn_exit", {"completed": False})

        ats = bond.replay_attempts(CHARACTER, sid)
        assert len(ats) == 1
        assert ats[0]["completed"] is False
        assert ats[0]["interrupted"] is True
        print("    replay: 中途退出段 completed=False")
    finally:
        chat._store = old


def test_replay_empty_session(tmp_path):
    """空会话 / 无剧情角色 → 空列表（不抛）。"""
    st, old = _with_store(tmp_path)
    try:
        st.create(CHARACTER)                       # 空会话（只有 session_start）
        assert bond.replay_attempts(CHARACTER) == []
        assert bond.replay_attempts("no_such_char") == []
        print("    replay: 空会话 → []")
    finally:
        chat._store = old
