# -*- coding: utf-8 -*-
"""跨重启预热缓存（2026-09-09）— soul/prewarm.json 旁路非真源。

覆盖:
    首场 LLM 落地 → 缓存落盘（anchor=最新 mmt seq）;
    模拟重启（内存态清空）→ bond_start 命中缓存 → 0 LLM 直接出首场;
    触发后又聊（mmt seq 前进）→ 失配 miss → 现场 LLM 生成;
    缓存命中后删除 / finish 删除 / demo 不写;
    事件流零污染（缓存场景未裁决不落库, 直到玩家裁决）。
"""

import json
import time
from pathlib import Path

from webgui import bond, chat
from core.session.store import SessionStore
from core.momotalk import MomoTalkEngine

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

SCENE = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "（缓存首场）她站在窗边，夕阳把影子拉长。"}],
    "choices": ["过去", "静静等她"],
    "branches": {"过去": [{"text": "她回过头。"}],
                 "静静等她": [{"text": "她没发现我。"}]}}}
SCENE2 = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "（LLM 现场生成的首场）"}]}}


class ScriptedLLM:
    """计数 + 按序出场景; 标注/place 自动应答不消耗脚本。"""

    def __init__(self, *scripts):
        self._s = list(scripts)
        self.calls = 0
        self._lock = __import__("threading").Lock()

    def chat(self, messages, **kw):
        last = messages[-1]["content"] if len(messages) > 1 else ""
        head = messages[0]["content"]
        if "情绪标签数组" in last:
            import re
            m = re.search(r"句号从 1 到 (\d+)", last)
            return ["nomal"] * max(int(m.group(1)) if m else 1, 1)
        if "变更句数组" in last:
            return []
        if "记录员" in head or "整理者" in head:
            return {"episodes": []}
        with self._lock:
            self.calls += 1
            if not self._s:
                raise RuntimeError("脚本耗尽")
            return self._s.pop(0)


def _setup(tmp_path, *scripts):
    st = SessionStore(tmp_path)
    llm = ScriptedLLM(*scripts)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine
    chat._store = st
    # 制造"刚触发"上下文: 事件流一条 mmt + 引擎 trace 带 chapter_title
    from core.session.events import make_event
    st.append_event(CHARACTER, root.session_id, make_event(
        "mmt", "mmt_chat", {"player": "好呀", "reply": "嗯…"}))
    engine.trace.append({"action": "mmt_trigger_bond_story",
                         "payload": {"chapter_title": "测试章"}})
    return engine, st, root.session_id, llm


def _wait_idle(char_id, sid, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = bond.bond_status(char_id, sid)
        if not s["busy"]:
            return s
        time.sleep(0.05)
    raise AssertionError("等待生成超时")


def _cache_path(tmp_path, sid) -> Path:
    return Path(tmp_path) / "worlds" / "world1" / "characters" \
        / CHARACTER / "soul" / bond._PREWARM_FILE


def _cleanup():
    chat._engines.pop(CHARACTER, None)


# ----------------------------------------------------------------------------
# 缓存写 + 命中（模拟重启）
# ----------------------------------------------------------------------------

def test_cache_saved_on_first_scene_landed(tmp_path):
    engine, st, sid, llm = _setup(tmp_path, SCENE, SCENE2, SCENE2)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_idle(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        assert state.scene_obj is not None and not state.scene_obj.is_end
        # 首场落地 → 缓存文件存在, anchor = 最新 mmt seq
        p = _cache_path(tmp_path, sid)
        assert p.is_file(), "首场落地应写 prewarm 缓存"
        payload = json.loads(p.read_text(encoding="utf-8"))
        assert payload["anchor_seq"] == bond._last_mmt_seq(CHARACTER, sid)
        assert "缓存首场" in json.dumps(payload["scene"], ensure_ascii=False)
        # 事件流零污染: 首场未裁决 → 无 bond 场景事件
        evs = st.events(CHARACTER, sid)
        assert not any(e.type == "bond" for e in evs)
        print("    缓存写: 首场落地即落盘（anchor 正确 / 事件流零污染）")
    finally:
        _cleanup()


def test_cache_hit_after_restart_zero_llm(tmp_path):
    """模拟重启: 清内存态（_bonds）→ bond_start 命中缓存 → 0 LLM 出首场。"""
    engine, st, sid, llm = _setup(tmp_path, SCENE, SCENE2, SCENE2)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_idle(CHARACTER, sid)
        assert _cache_path(tmp_path, sid).is_file()
        gen_calls = llm.calls
        # 模拟进程重启: 内存态全丢（事件流/缓存保留——chat engine 会话在）
        bond._bonds.pop((CHARACTER, sid), None)
        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] and r.get("resumed") and not r["busy"], r
        # 命中 → 场景来自缓存（0 LLM 主生成调用）, 缓存已消费删除
        assert llm.calls == gen_calls, f"缓存命中不应再调 LLM: {llm.calls}"
        assert not _cache_path(tmp_path, sid).exists(), "命中即消费删除"
        stt = _wait_idle(CHARACTER, sid)
        text = "".join(p.get("text", "")
                       for p in (stt["scene"] or {}).get("paragraphs", []))
        assert "缓存首场" in text, text
        assert stt["scene"]["choices"] == ["过去", "静静等她"]
        print("    缓存命中: 重启后 0 LLM 直出首场（resumed, 消费即删）")
    finally:
        _cleanup()


def test_cache_miss_after_new_mmt(tmp_path):
    """触发后又聊（mmt seq 前进）→ anchor 失配 → miss → 现场 LLM 生成。"""
    from core.session.events import make_event
    engine, st, sid, llm = _setup(tmp_path, SCENE, SCENE2, SCENE2, SCENE2)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_idle(CHARACTER, sid)
        assert _cache_path(tmp_path, sid).is_file()
        gen_calls = llm.calls
        # 玩家又发了一条消息（失配）
        st.append_event(CHARACTER, sid, make_event(
            "mmt", "mmt_chat", {"player": "对了", "reply": "嗯嗯"}))
        bond._bonds.pop((CHARACTER, sid), None)     # 模拟重启
        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"]
        _wait_idle(CHARACTER, sid)
        assert llm.calls > gen_calls, "失配应现场 LLM 生成"
        state = bond._state(CHARACTER, sid)
        text = "".join(p.get("text", "") for p in state.scene_obj.paragraphs)
        assert "LLM 现场生成" in text, text
        # 新首场重新落盘（覆盖旧缓存, anchor 已更新）
        payload = json.loads(_cache_path(tmp_path, sid).read_text(
            encoding="utf-8"))
        assert payload["anchor_seq"] == bond._last_mmt_seq(CHARACTER, sid)
        print("    缓存失配: 又聊过 → miss 现场生成, 新首场重新落盘")
    finally:
        _cleanup()


def test_cache_deleted_on_finish_and_demo_skip(tmp_path):
    engine, st, sid, llm = _setup(tmp_path, SCENE, SCENE2, SCENE2)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_idle(CHARACTER, sid)
        assert _cache_path(tmp_path, sid).is_file()
        # finish → 缓存失效
        bond.bond_finish(CHARACTER, sid)
        assert not _cache_path(tmp_path, sid).exists(), "finish 应删缓存"
        print("    finish: 缓存失效删除")
    finally:
        _cleanup()


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_cache_saved_on_first_scene_landed(d)
    with tempfile.TemporaryDirectory() as d:
        test_cache_hit_after_restart_zero_llm(d)
    with tempfile.TemporaryDirectory() as d:
        test_cache_miss_after_new_mmt(d)
    with tempfile.TemporaryDirectory() as d:
        test_cache_deleted_on_finish_and_demo_skip(d)
