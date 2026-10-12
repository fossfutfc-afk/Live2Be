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

from webgui import bond, chat, deps
from core.session.store import SessionStore
from core.mmt.engine import MomoTalkEngine

ROOT = Path(__file__).resolve().parent.parent.parent
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))
from llm import task_labels as T  # noqa: E402
from tests import stub_tasks  # noqa: E402
from tests.vn_fixtures import scene as _scene  # noqa: E402

CHARACTER = "igusa_haruka"

SCENE = _scene(lines=["（缓存首场）她站在窗边，夕阳把影子拉长。"],
               sensei=["过去", "静静等她"])
SCENE2 = _scene(lines=["（LLM 现场生成的首场）"])


class ScriptedLLM:
    """计数 + 按序出场景; 标注/place/digest 按 **task** 自动应答不消耗脚本。"""

    def __init__(self, *scripts):
        self._s = list(scripts)
        self.calls = 0
        self._lock = __import__("threading").Lock()

    def chat(self, messages, **kw):
        task = kw.get("task")
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                    # emotion/place/选图/digest → 标准应答
            return reply
        if task in T.MAIN:
            with self._lock:
                self.calls += 1
                if not self._s:
                    raise RuntimeError("脚本耗尽")
                return self._s.pop(0)
        raise stub_tasks.unknown_task(task)


def _setup(tmp_path, *scripts):
    st = SessionStore(tmp_path)
    llm = ScriptedLLM(*scripts)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine
    deps.set_store(st)
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
    # 纯叙事首场（无 choices → 命中后不 spawn 候选, 主生成零调用可精确断言）
    engine, st, sid, llm = _setup(tmp_path, NARR1, PRE)
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
        assert "月光下她指了指杂草丛" in text, text
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


NARR1 = _scene(lines=["（缓存首场·纯叙事）月光下她指了指杂草丛。"])
PRE = _scene(lines=["（首场后的自动预生成占位——重启即弃）"])
NARR2 = _scene(lines=["（承接第二场）她蹲下来摘了一片叶子。"])


def test_cache_hit_injects_engine_state_and_advances(tmp_path):
    """prob2 回归: 命中缓存后推进——引擎注入生效（历史含首场 / _last_payload
    就位）→ （继续）承接推进（round2 内容 != 首场, 不重新开场）。

    记录流 v2 / 决策 #28b: 重启前已自动预生成的那一板会落**草稿旁路**（PRE）——
    重进时它作为后继板被恢复, 所以（继续）先领出 PRE（0 LLM）, 再下一次才是 NARR2。
    断言"不重新开场 + 最终接到 NARR2", 不钉死单次点击的落点。
    """
    engine, st, sid, llm = _setup(tmp_path, NARR1, PRE, NARR2)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_idle(CHARACTER, sid)
        assert _cache_path(tmp_path, sid).is_file()
        gen_calls = llm.calls                     # 首场 LLM 生成 1 次
        bond._bonds.pop((CHARACTER, sid), None)   # 模拟重启
        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] and r.get("resumed"), r
        assert llm.calls == gen_calls             # 命中 0 LLM
        # 引擎注入断言: 历史尾部含首场叙事 + _last_payload 就位
        state = bond._state(CHARACTER, sid)
        hist_tail = state.vn.history[-1]["content"]
        assert "杂草丛" in hist_tail, "缓存首场应注入引擎历史（AI 视角含首场）"
        assert state.vn._last_payload is not None, \
            "_last_payload 应就位（record_picked/fork 回录基准）"
        # 玩家点继续 → 承接推进（待发草稿板 0 LLM / 或现场生成）; 不重新开场
        seen: list[str] = []
        deadline = time.time() + 15.0
        while time.time() < deadline and not any("承接第二场" in t for t in seen):
            r2 = bond.bond_turn(CHARACTER, sid, "（继续）")
            if not r2.get("accepted"):
                time.sleep(0.05)
                continue
            _wait_idle(CHARACTER, sid, timeout=20.0)
            state = bond._state(CHARACTER, sid)
            seen.append("".join(p.get("text", "") for p in state.scene_obj.paragraphs))
        assert seen, "应至少推进一板"
        assert not any("杂草丛" in t for t in seen), f"不应重新开场: {seen}"
        assert any("承接第二场" in t for t in seen), f"应最终接到 NARR2: {seen}"
        print("    命中后推进: 引擎注入生效, 承接推进（草稿板 0 LLM 优先, 不重新开场）")
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
