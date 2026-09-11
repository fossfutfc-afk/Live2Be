# -*- coding: utf-8 -*-
"""webgui 候选支池（DESIGN_CHOICE_PREGEN, N2a）— spawn 触发/就绪/失败/跳过。

覆盖:
    choices 板落地 → spawn N 候选（fork 引擎后台预生成, 不占 busy）;
    就绪后 scene_obj 可消费（内容来自对应脚本）;
    脚本不足 → failed 态（不 raise）;
    纯叙事板/收尾板 → 不 spawn（池空）;
    标注调用自动应答（情绪/place 不消耗脚本）。
"""

import json
import re
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

from webgui import bond, chat  # noqa: E402
from core.session.store import SessionStore  # noqa: E402
from core.momotalk import MomoTalkEngine  # noqa: E402

CHARACTER = "igusa_haruka"

BOARD = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "她低着头站在窗边，指尖捏着衣角。"}],
    "choices": ["选A", "选B"],
    "branches": {"选A": [{"text": "她怔了一下，点点头。"}],
                 "选B": [{"text": "她抿抿嘴没说话。"}]}}}
# 三选项板（契约上限 1~3, 用户 2026-09-09 疑虑: "三个选项时 fork 能否 handle"）
BOARD3 = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "「那、那个……老师觉得哪个好？」她捧着铁盒, 眼神躲闪。"}],
    "choices": ["选一", "选二", "选三"],
    "branches": {"选一": [{"text": "（反应一）"}],
                 "选二": [{"text": "（反应二）"}],
                 "选三": [{"text": "（反应三）"}]}}}
NEXT = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "（同一内容——候选线程并发取脚本, 顺序不定, 内容一致断言）"}]}}
NARRATIVE = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "纯叙事场, 无选项。"}]}}
END = {"action": "story_end", "payload": {
    "paragraphs": [{"text": "（收尾。）"}]}}
# N2b 链式 spawn 用: 候选下一板自身带 choices（读板期再 spawn 一层）
NEXT_C = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "（第二层候选板, 又带选项。）"}],
    "choices": ["再选1", "再选2"],
    "branches": {"再选1": [{"text": "（反应1）"}],
                 "再选2": [{"text": "（反应2）"}]}}}
N1 = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "（第三层内容。）"}]}}


class ScriptedLLM:
    """场景脚本按序弹出; 标注调用按 user 声明句数自动应答（不消耗脚本）。"""

    def __init__(self, *scripts):
        self._s = list(scripts)
        self._lock = threading.Lock()

    def chat(self, messages, **kw):
        last = messages[-1]["content"] if len(messages) > 1 else ""
        head = messages[0]["content"]
        if "情绪标签" in last:
            m = re.search(r"恰 (\d+) 项", last)
            n = int(m.group(1)) if m else 1
            return ["nomal"] * n
        if "变更句数组" in last:
            return []
        if "记录员" in head or "整理者" in head:
            return {"episodes": []}
        with self._lock:                     # 候选线程并发取脚本（同内容安全）
            if not self._s:
                raise RuntimeError("ScriptedLLM 脚本耗尽")
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
    return engine, st, root.session_id


def _wait_status(char_id, sid, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = bond.bond_status(char_id, sid)
        if not st["busy"]:
            return st
        time.sleep(0.05)
    raise AssertionError("等待生成超时")


def _wait_candidates(state, n, status="ready", timeout=15.0):
    """轮询候选池: n 个候选全部进入指定状态。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with state._lock:
            cands = list(state.choice_candidates)
        if len(cands) >= n and all(c.status == status for c in cands):
            return cands
        time.sleep(0.05)
    raise AssertionError(
        f"候选未就绪: {[(c.picked, c.status) for c in cands]}")


def _cleanup():
    try:
        chat._engines.pop(CHARACTER, None)
    except Exception:                            # noqa: BLE001
        pass


# ----------------------------------------------------------------------------
# N2a: spawn / ready / skip
# ----------------------------------------------------------------------------

def test_spawn_two_candidates_and_ready(tmp_path):
    """choices 板落地 → 两个候选 spawn 且就绪（各自 fork 生成, 不占 busy）。"""
    engine, st, sid = _setup(tmp_path, BOARD, NEXT, NEXT)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        cands = _wait_candidates(state, 2)
        picks = sorted(c.picked for c in cands)
        assert picks == ["选A", "选B"]
        for c in cands:
            assert c.scene_obj is not None and c.scene_obj.paragraphs
            text = "".join(p.get("text", "") for p in c.scene_obj.paragraphs)
            assert "同一内容" in text, text
        assert not state.busy                    # 候选不占 busy（玩家可推进）
        # N2c: status 暴露候选诊断（picked+status）
        s = bond.bond_status(CHARACTER, sid)
        assert sorted((c["picked"], c["status"]) for c in s["candidates"]) == \
            sorted((c.picked, c.status) for c in cands)
        # 中断审计: 候选就绪但玩家从未裁决 → 事件流零草稿（候选不落库,
        # 事件只可能来自 _log_scene——首场未裁决不落 bond 场景）
        blob = "".join(json.dumps(e.payload, ensure_ascii=False)
                       for e in st.events(CHARACTER, sid))
        assert "同一内容" not in blob, "候选草稿泄漏进事件流!"
        assert not any(e.type == "bond" and e.subtype == "story_scene"
                       for e in st.events(CHARACTER, sid))
        print("    spawn: 2 候选就绪（fork 引擎独立生成, busy 不被占用）")
    finally:
        _cleanup()


def test_candidate_failed_no_raise(tmp_path):
    """脚本不足 → 未拿到脚本的候选 failed（不 raise, 消费端降级老路）。"""
    engine, st, sid = _setup(tmp_path, BOARD, NEXT)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        # 两个候选并发: 一个成功一个失败（脚本只有 1 份 NEXT）
        deadline = time.time() + 15.0
        while time.time() < deadline:
            with state._lock:
                statuses = {c.picked: c.status for c in state.choice_candidates}
            if len(statuses) == 2 and "generating" not in statuses.values():
                break
            time.sleep(0.05)
        assert set(statuses.values()) == {"ready", "failed"}, statuses
        assert not state.busy
        print(f"    spawn 失败态: {statuses}（不 raise, 可降级老路）")
    finally:
        _cleanup()


def test_no_spawn_for_narrative_and_end(tmp_path):
    """纯叙事板 / 收尾板 → 不 spawn（池空, 只有真实 choices 板才 spawn）。"""
    # 纯叙事场（独立子目录——SessionStore 同目录会复用旧会话）
    engine, st, sid = _setup(tmp_path / "a", NARRATIVE)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        assert state.choice_candidates == []
    finally:
        _cleanup()
    # 收尾板
    engine2, st2, sid2 = _setup(tmp_path / "b", END)
    try:
        bond.bond_start(CHARACTER, sid2)
        _wait_status(CHARACTER, sid2)
        state = bond._state(CHARACTER, sid2)
        assert state.choice_candidates == []
        assert state.completed
    finally:
        _cleanup()
    print("    spawn 跳过: 纯叙事/收尾板不 spawn")


# ----------------------------------------------------------------------------
# N2b: 裁决命中切换 / 老路回退 / 链式 spawn
# ----------------------------------------------------------------------------

def test_pick_hits_candidate_switch_engine(tmp_path):
    """裁决命中就绪候选 → 切主引擎 + pregen 通道就绪 + 池清空;
    （继续）消费零 LLM（候选即下一板）。"""
    engine, st, sid = _setup(tmp_path / "h", BOARD, NEXT, NEXT)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        cands = _wait_candidates(state, 2)
        cand_a = next(c for c in cands if c.picked == "选A")
        live_before = state.vn

        r = bond.bond_turn(CHARACTER, sid, "选A")
        assert r["accepted"] and r.get("candidate") is True, r
        # 主引擎切换为候选 fork（历史已内嵌裁决行——无重复回录）
        assert state.vn is cand_a.engine
        assert state.vn is not live_before
        assert state.pregen_obj is cand_a.scene_obj
        assert state.choice_candidates == []          # 未选候选作废 GC
        # N2c: status 候选诊断清空（裁决后无残留）
        assert bond.bond_status(CHARACTER, sid)["candidates"] == []
        assert state.scene_logged                     # 主线已落库（分支展示中）
        # （继续）→ 消费 pregen 零 LLM（无脚本可耗 = 若走生成会抛, 此处应成功）
        deadline = time.time() + 10.0
        r2 = None
        while time.time() < deadline:
            r2 = bond.bond_turn(CHARACTER, sid, "（继续）")
            if r2["accepted"]:
                break
            time.sleep(0.05)
        assert r2 is not None and r2["accepted"], r2
        # 链式预生成（无脚本 → 降级失败）结束后 busy 复位
        deadline = time.time() + 10.0
        while time.time() < deadline and bond.bond_status(
                CHARACTER, sid)["busy"]:
            time.sleep(0.05)
        assert state.scene_obj is cand_a.scene_obj
        assert state.round == 2
        text = "".join(p.get("text", "") for p in state.scene_obj.paragraphs)
        assert "同一内容" in text
        print("    pick-hit: 引擎切换 / pregen 通道 / 零 LLM 消费 / 池清空")
    finally:
        _cleanup()


def test_three_choices_fork_pick_middle(tmp_path):
    """三选项板 → 三个候选全 spawn/就绪; 命中第二个照样切引擎+零 LLM 消费。

    用户疑虑（2026-09-09）: "出三个选项时 fork 程序能否 handle"——
    契约上限 3, spawn 按 choices 逐个 fork（≤3 全支持）, 命中任意一个都等价。
    """
    engine, st, sid = _setup(tmp_path / "t3",
                             BOARD3, NEXT, NEXT, NEXT)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        # 三候选全就绪（各自独立 fork 生成, busy 不被占用）
        cands = _wait_candidates(state, 3)
        assert {c.picked for c in cands} == {"选一", "选二", "选三"}
        assert not state.busy
        for c in cands:
            assert c.status == "ready" and c.scene_obj is not None
            text = "".join(p.get("text", "") for p in c.scene_obj.paragraphs)
            assert "同一内容" in text, text
        # 命中第二个（非首尾）→ 切主引擎 + pregen 通道 + 池清空
        live_before = state.vn
        cand_two = next(c for c in cands if c.picked == "选二")
        r = bond.bond_turn(CHARACTER, sid, "选二")
        assert r["accepted"] and r.get("candidate") is True, r
        assert state.vn is cand_two.engine and state.vn is not live_before
        assert state.pregen_obj is cand_two.scene_obj
        assert state.choice_candidates == []
        assert bond.bond_status(CHARACTER, sid)["candidates"] == []
        # （继续）→ 消费 pregen 零 LLM（无脚本可耗 = 若走生成会抛, 此处应成功）
        deadline = time.time() + 10.0
        r2 = None
        while time.time() < deadline:
            r2 = bond.bond_turn(CHARACTER, sid, "（继续）")
            if r2["accepted"]:
                break
            time.sleep(0.05)
        assert r2 is not None and r2["accepted"], r2
        deadline = time.time() + 10.0
        while time.time() < deadline and bond.bond_status(
                CHARACTER, sid)["busy"]:
            time.sleep(0.05)
        assert state.scene_obj is cand_two.scene_obj
        assert state.round == 2
        print("    three-choice fork: 3 候选就绪 / 命中第二支切引擎 / 池清空")
    finally:
        _cleanup()


def test_pick_fallback_when_no_ready(tmp_path):
    """候选未就绪（failed）→ 走老路: record_picked + 单路预生成, 不 raise。"""
    engine, st, sid = _setup(tmp_path / "f", BOARD, NEXT)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        # 1 ready 1 failed（脚本只有 1 份）→ 对 failed 候选裁决
        deadline = time.time() + 15.0
        while time.time() < deadline:
            with state._lock:
                statuses = {c.picked: c.status for c in state.choice_candidates}
            if len(statuses) == 2 and "generating" not in statuses.values():
                break
            time.sleep(0.05)
        bad_pick = next(p for p, s in statuses.items() if s == "failed")
        live_before = state.vn
        r = bond.bond_turn(CHARACTER, sid, bad_pick)
        assert r["accepted"] and not r.get("candidate"), r
        assert state.vn is live_before                 # 老路不切引擎
        assert state.choice_candidates == []
        # record_picked 生效（老路回录）
        assert "（选择了: %s）" % bad_pick in state.vn.history[-1]["content"]
        print(f"    pick-fallback: failed 候选走老路（回录 {bad_pick}, 不 raise）")
    finally:
        _cleanup()


def test_chain_spawn_after_pregen_consume(tmp_path):
    """候选下一板自身带 choices → （继续）消费后链式再 spawn（N2a 缺口）。"""
    engine, st, sid = _setup(tmp_path / "c", BOARD, NEXT_C, NEXT_C, N1, N1)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        cands = _wait_candidates(state, 2)             # 第一层候选
        r = bond.bond_turn(CHARACTER, sid, "选A")
        assert r["accepted"] and r.get("candidate") is True
        # 消费（继续）→ 提升候选板（带 choices）→ 链式 spawn 第二层
        deadline = time.time() + 10.0
        r2 = None
        while time.time() < deadline:
            r2 = bond.bond_turn(CHARACTER, sid, "（继续）")
            if r2["accepted"]:
                break
            time.sleep(0.05)
        assert r2 is not None and r2["accepted"], r2
        assert state.scene_obj.choices == ["再选1", "再选2"]
        cands2 = _wait_candidates(state, 2)
        assert sorted(c.picked for c in cands2) == ["再选1", "再选2"]
        for c in cands2:
            text = "".join(p.get("text", "") for p in c.scene_obj.paragraphs)
            assert "第三层" in text, text
        print("    chain-spawn: 候选板消费后链式再 spawn（带 choices 场景）")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# N2d: choice_pregen 开关（settings.toml [bond]）
# ----------------------------------------------------------------------------

def test_choice_pregen_switch(monkeypatch, tmp_path):
    from webgui import bond as bond_mod

    cfg = tmp_path / "settings.toml"
    monkeypatch.setattr(bond_mod, "_CAND_SETTINGS_PATH", cfg)
    assert bond_mod._choice_pregen_enabled() is True      # 缺省开（sibling）
    cfg.write_text("[bond]\nchoice_pregen = \"off\"\n", encoding="utf-8")
    assert bond_mod._choice_pregen_enabled() is False
    cfg.write_text("[bond]\nchoice_pregen = \"sibling\"\n", encoding="utf-8")
    assert bond_mod._choice_pregen_enabled() is True
    cfg.write_text("[bond]\nchoice_pregen = \"tree\"\n", encoding="utf-8")
    assert bond_mod._choice_pregen_enabled() is True       # tree 暂同 sibling
    cfg.write_text("broken[[", encoding="utf-8")
    assert bond_mod._choice_pregen_enabled() is True       # 异常 → 缺省开
    print("    choice_pregen 开关: off/sibling/tree/缺省/异常语义")


def test_choice_pregen_off_no_spawn(monkeypatch, tmp_path):
    """开关 off → choices 板不 spawn（走老路单路 pregen）。"""
    from webgui import bond as bond_mod

    cfg = tmp_path / "s.toml"
    cfg.write_text("[bond]\nchoice_pregen = \"off\"\n", encoding="utf-8")
    monkeypatch.setattr(bond_mod, "_CAND_SETTINGS_PATH", cfg)
    engine, st, sid = _setup(tmp_path / "o", BOARD)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        assert state.choice_candidates == []
        assert state.scene_obj is not None and state.scene_obj.choices
    finally:
        _cleanup()
    print("    choice_pregen=off: choices 板不 spawn")


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_spawn_two_candidates_and_ready(d)
    with tempfile.TemporaryDirectory() as d:
        test_candidate_failed_no_raise(d)
    with tempfile.TemporaryDirectory() as d:
        test_no_spawn_for_narrative_and_end(d)
