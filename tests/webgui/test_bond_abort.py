# -*- coding: utf-8 -*-
"""webgui 中止语义（2026-09-09 用户拍板: 中断/异常 ≠ 失败/完成）— N_a 测试。

覆盖:
    生成连续失败超限 → 中止态（completed 保持 False, 不落任何结束事件）,
    玩家可重试成功续写;
    _system_note 超限后每轮强制 story_end 注记（取代旧 FORCE_AFTER 伪收场）;
    自然 story_end 仍 completed（回归由 test_bond.py 全流程覆盖）。
"""

import time
from pathlib import Path

from webgui import bond, chat
from core.session.store import SessionStore
from core.momotalk import MomoTalkEngine

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

SCENE = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "她轻轻点了点头，夜色里声音也软了下来。"}]}}


class FailThenOK:
    """前 fail_calls 次 LLM 调用抛异常（模拟 send 内每 attempt 一次）,
    之后按队列返回场景。标注类调用自动应答不消耗计数（本测试 annotate=False,
    实际不会触发）。"""

    def __init__(self, fail_calls: int, *ok_scripts):
        self._left = fail_calls
        self._ok = list(ok_scripts)

    def chat(self, messages, **kw):
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last or "变更句数组" in last:
            return []
        if self._left > 0:
            self._left -= 1
            raise RuntimeError("api down")
        if not self._ok:
            raise RuntimeError("脚本耗尽")
        return self._ok.pop(0)


def _setup(tmp_path, *scripts):
    st = SessionStore(tmp_path)
    llm = FailThenOK(*scripts) if scripts and isinstance(scripts[0], int) \
        else scripts[0]
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine
    chat._store = st
    return engine, st, root.session_id, llm


def _wait_idle(char_id, sid, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = bond.bond_status(char_id, sid)
        if not st["busy"]:
            return st
        time.sleep(0.05)
    raise AssertionError("等待生成超时")


def _cleanup():
    chat._engines.pop(CHARACTER, None)


# ----------------------------------------------------------------------------
# N_a: 失败超限 = 中止态（不伪收场）
# ----------------------------------------------------------------------------

def test_fail_abort_no_closing_and_retry(tmp_path):
    """连续失败超限 → completed 保持 False + 零结束事件; 玩家重试成功续写。"""
    # send 内每轮 3 attempts → 4 轮全败 = 12 次失败调用, 第 13 次起成功
    engine, st, sid, llm = _setup(tmp_path, 13, SCENE)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_idle(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        assert state.error, "应有错误提示"
        assert not state.completed, "中止态绝不可 completed"
        # 重试（同输入重新 submit）直到成功出场景（13 次失败 = 4 轮耗尽 + 1 次
        # 成功; 期间会看到"暂缓"中止文案——不以此为退出, 继续重试直到出场景）
        deadline = time.time() + 25.0
        while time.time() < deadline:
            s = bond.bond_status(CHARACTER, sid)
            if (s.get("scene") or {}).get("paragraphs"):
                break
            bond.bond_turn(CHARACTER, sid, "（开场）")
            _wait_idle(CHARACTER, sid, timeout=10.0)
        assert state.scene_obj is not None, "重试后应成功续写"
        assert state.error == ""
        assert not state.completed
        # 事件流: 从未裁决 → 无任何 bond 场景事件、无 vn_exit（零伪收场）
        evs = st.events(CHARACTER, sid)
        assert not any(e.type == "bond" for e in evs), \
            [e.subtype for e in evs if e.type == "bond"]
        assert not any(e.is_marker and e.subtype == "vn_exit" for e in evs)
        print("    中止态: 超限不伪收场（completed False/零结束事件）, 重试成功续写")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# N_a: 超限后 _system_note 强制收尾注记（取代伪收场）
# ----------------------------------------------------------------------------

def test_system_note_force_end_after_limit():
    from webgui.bond import BondState, _END_ROUNDS

    st50 = BondState(round=_END_ROUNDS)
    note50 = bond._system_note(st50)
    assert note50 and "本轮请改用 story_end" in note50
    st60 = BondState(round=_END_ROUNDS + 10)
    note60 = bond._system_note(st60)
    assert note60 and "必须" in note60 and "story_end" in note60, note60
    # 平时（未到提醒轮）→ 无收尾注记
    st5 = BondState(round=5)
    note5 = bond._system_note(st5)
    assert note5 is None or "story_end" not in note5
    print("    system_note: 超限后每轮强制 story_end 注记（无伪收场）")


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_fail_abort_no_closing_and_retry(d)
    test_system_note_force_end_after_limit()
