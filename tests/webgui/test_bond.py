# -*- coding: utf-8 -*-
"""webgui bond 驱动单测 — 羁绊剧情状态机（start/turn/status/finish 全流程）。

ScriptedLLM（不碰 API）:
    bond_start → 首场（story_scene 带选项）→ bond_turn("选A") → 收尾场（story_end）
    → bond_finish → 事件流断言: vn_enter / bond(story_scene+story_end, input/picked)
    / vn_state / vn_exit / session_end + wrapup 收尾 mmt 事件。

与 CLI（test_vn_cli.py）同构的落库格式; 后台线程用轮询等待（sleep 小量）。
运行: python -m pytest tests/webgui/test_bond.py
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.momotalk import MomoTalkEngine
from core.session import SessionStore
from webgui import bond, chat

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

# 契约动作（与 test_vn_cli.py 同构）
SCENE_A = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "段落一。"}, {"text": "段落二。", "emotion": "smile"}],
    "choices": ["选A", "选B"]}}
STORY_END = {"action": "story_end", "payload": {
    "paragraphs": [{"text": "收尾了。"}]}}
MMT_TRIGGER = {"actions": [{"action": "mmt_trigger_bond_story",
                            "reply": "嗯…我们走吧", "payload": {"reason": "邀约"}}]}
MMT_REPLY = {"actions": [{"action": "mmt_chat", "reply": "嗯，今晚很开心。", "payload": {}}]}
# 空消化桩: summary 非空（否则 consolidation 校验"无有效条目"跳过）;
# affection_exp_delta=5 → 触发好感事件落库（delta=0 不写事件——好感无变化无需记录）
EMPTY_DIGEST = {"summary": "（本段互动无特别重要内容）", "facts": [], "beliefs": [],
                "relations": [], "affection_exp_delta": 5}


class ScriptedLLM:
    """带 chat(json_object) 的脚本化 LLM——agent_turn / send_vn_scene / digest 都走它。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text"):
        self.snapshots.append([dict(m) for m in messages])
        if "记忆巩固" in messages[0]["content"]:       # digest 调用 → 空消化
            return dict(EMPTY_DIGEST)
        if not self._scripts:
            raise RuntimeError("ScriptedLLM 脚本耗尽")
        return self._scripts.pop(0)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


def _setup(tmp_path, *scripts):
    """引擎 + 事件流会话（tmp_path）+ chat 引擎/store 注入（bond 落库走 chat._store）。"""
    st = SessionStore(tmp_path)
    llm = ScriptedLLM(*scripts)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine          # 注入（wrapup 复用引擎）
    chat._store = st                           # 注入（bond 落库到 tmp_path, 不污染 data/）
    return engine, st, root.session_id, llm


def _wait_status(char_id, sid, timeout=10.0):
    """轮询 bond_status 直到 busy=False（后台生成线程完成）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = bond.bond_status(char_id, sid)
        if not st["busy"]:
            return st
        time.sleep(0.05)
    raise AssertionError(f"bond 生成超时: {bond.bond_status(char_id, sid)}")


def _cleanup():
    chat._engines.pop(CHARACTER, None)
    chat._store = SessionStore(Path("data"))   # 恢复真实 store（模块级默认）


# ----------------------------------------------------------------------------
# 全流程: start（首场选项）→ turn（选A）→ finish（收尾 + 事件流断言）
# ----------------------------------------------------------------------------

def test_bond_full_flow(tmp_path):
    engine, st, sid, llm = _setup(tmp_path, SCENE_A, STORY_END, MMT_REPLY)
    try:
        # start: 后台生成首场
        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] and r["busy"]
        st1 = _wait_status(CHARACTER, sid)
        assert st1["round"] == 1 and st1["scene"] is not None
        scene1 = st1["scene"]
        assert scene1["paragraphs"][0]["text"] == "段落一。"
        assert scene1["paragraphs"][1]["emotion"] == "smile"
        assert scene1["choices"] == ["选A", "选B"]
        assert not st1["completed"]

        # turn: 玩家选 A → 补录首场 + 生成收尾场
        r2 = bond.bond_turn(CHARACTER, sid, "选A")
        assert r2["accepted"] and r2["busy"]
        st2 = _wait_status(CHARACTER, sid)
        assert st2["round"] == 2
        assert st2["scene"]["paragraphs"][0]["text"] == "收尾了。"
        assert st2["scene"]["is_end"] is True
        assert st2["completed"] is True

        # finish: 补录收尾场 + vn_exit + session_end + wrapup（后台线程）
        r3 = bond.bond_finish(CHARACTER, sid)
        assert r3["completed"] is True

        # 事件流断言（等 wrapup 落库——后台线程, 轮询等待 mmt 收尾事件）
        evs = st.events(CHARACTER, sid)
        types = [(e.type, e.subtype) for e in evs]
        assert ("marker", "vn_enter") in types, types
        assert ("bond", "story_scene") in types, types
        assert ("bond", "story_end") in types, types
        assert ("marker", "vn_state") in types, types
        assert ("marker", "vn_exit") in types, types
        assert ("marker", "session_end") in types, types
        # 事件内容: 首场 input=旁白 seed, picked=选A; 收尾场 picked=None
        sc = [e for e in evs if (e.type, e.subtype) == ("bond", "story_scene")][0]
        assert sc.payload["picked"] == "选A", sc.payload
        assert "旁白" in sc.payload["input"], sc.payload
        assert sc.payload["paragraphs"][1]["emotion"] == "smile"
        en = [e for e in evs if (e.type, e.subtype) == ("bond", "story_end")][0]
        assert en.payload["picked"] is None, en.payload
        # 收尾 marker 顺序: vn_exit 在 session_end 前
        idx_exit = types.index(("marker", "vn_exit"))
        idx_end = types.index(("marker", "session_end"))
        assert idx_exit < idx_end
        # wrapup 收尾 mmt 事件（后台线程, 轮询等待; 收尾话 = MMT_REPLY 脚本回复）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            evs = st.events(CHARACTER, sid)
            if any(e.type == "mmt" and (e.payload.get("reply") or "").strip()
                   and "开心" in (e.payload.get("reply") or "")
                   for e in evs):
                break
            time.sleep(0.05)
        assert any(e.type == "mmt" and "开心" in (e.payload.get("reply") or "")
                   for e in st.events(CHARACTER, sid)), "wrapup 收尾话应落 mmt 事件"

        # digest 闭环（async_digest 后台线程, 轮询等待）: 好感事件落库
        # （delta=0 也落——幂等键 digested_seq 记录消化水位; digest 输入含收尾话）
        deadline = time.time() + 10.0
        aff = None
        while time.time() < deadline:
            affs = [e for e in st.events(CHARACTER, sid)
                    if e.type == "affection" and e.subtype == "digest"]
            if affs:
                aff = affs[-1]
                break
            time.sleep(0.05)
        assert aff is not None, "digest 后应落 affection 事件（好感结算）"
        assert int(aff.payload.get("digested_seq", 0)) > 0, aff.payload
        print(f"    bond digest: affection 事件落库 digested_seq={aff.payload.get('digested_seq')} "
              f"delta={aff.payload.get('delta')}")
        print("    bond 全流程: start→turn→finish, 事件流 vn_enter/bond×2/marker/vn_exit/session_end + wrapup 收尾 + digest 好感")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# 幂等 / 状态守卫
# ----------------------------------------------------------------------------

def test_bond_start_idempotent_and_guards(tmp_path):
    engine, st, sid, llm = _setup(tmp_path, SCENE_A, STORY_END, MMT_REPLY)
    try:
        # 幂等: 已开始 → resumed=True, 不重建
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] and r.get("resumed") is True

        # 剧情结束后 turn 被拒（应调 finish）
        bond.bond_turn(CHARACTER, sid, "选A")
        _wait_status(CHARACTER, sid)
        r3 = bond.bond_turn(CHARACTER, sid, "选A")   # 已 completed → 拒绝
        assert not r3["accepted"] and r3.get("completed") is True

        # 未开始: 另一个 session → turn/finish 拒绝
        # （st.create 对同角色幂等返回同一条线——用不存在的 session id 模拟未开始）
        assert not bond.bond_turn(CHARACTER, "no_such_session", "x")["accepted"]
        assert not bond.bond_finish(CHARACTER, "no_such_session")["completed"]
        print("    bond 守卫: start 幂等 / completed 后 turn 拒 / 未开始 turn+finish 拒")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# 演示模式: 预设剧本驱动（不调 LLM）——前端 VN 体验/联调用
# ----------------------------------------------------------------------------

def test_bond_demo_full_flow(tmp_path):
    """demo: start_demo → 3 场预设剧本（选项→选项→is_end）→ finish（预设收尾话）。"""
    engine, st, sid, llm = _setup(tmp_path, MMT_REPLY)   # 剧本不耗 LLM 脚本
    try:
        r = bond.bond_start_demo(CHARACTER, sid)
        assert r["accepted"] and r["busy"]
        st1 = _wait_status(CHARACTER, sid)
        assert st1["round"] == 1 and not st1["completed"]
        assert st1["scene"]["background"] == "class_room"
        assert st1["scene"]["paragraphs"][1]["emotion"] == "embarrassed"

        bond.bond_turn(CHARACTER, sid, "「当然可以。」")
        st2 = _wait_status(CHARACTER, sid)
        assert st2["round"] == 2 and st2["scene"]["background"] == "wildhunt_street"
        assert not st2["completed"]

        bond.bond_turn(CHARACTER, sid, "「嗯，约定好了。」")
        st3 = _wait_status(CHARACTER, sid)
        assert st3["round"] == 3 and st3["completed"]
        assert st3["scene"]["is_end"] is True
        assert st3["scene"]["paragraphs"][-1]["emotion"] == "pensive"
        assert "background" not in st3["scene"]      # 结束余韵无背景 → 黑屏

        assert bond.bond_finish(CHARACTER, sid)["completed"] is True

        # 事件流: 3 场 bond + 收尾 marker + 预设收尾话（无 digest——跳过 LLM）
        evs = st.events(CHARACTER, sid)
        subs = [e.subtype for e in evs if e.type == "bond"]
        assert subs == ["story_scene", "story_scene", "story_end"], subs
        assert ("marker", "vn_exit") in [(e.type, e.subtype) for e in evs]
        assert ("marker", "session_end") in [(e.type, e.subtype) for e in evs]
        # 玩家裁决落库（picked）
        scs = [e for e in evs if e.subtype == "story_scene"]
        assert scs[0].payload["picked"] == "「当然可以。」", scs[0].payload
        assert scs[1].payload["picked"] == "「嗯，约定好了。」"
        # 预设收尾话（后台线程, 轮询等待）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if any("演示收尾" in (e.payload.get("reply") or "")
                   for e in st.events(CHARACTER, sid)):
                break
            time.sleep(0.05)
        assert any("演示收尾" in (e.payload.get("reply") or "")
                   for e in st.events(CHARACTER, sid))
        print("    bond demo: 3 场预设剧本 → finish → 事件流完整 + 预设收尾话（零 LLM 调用）")
    finally:
        _cleanup()


def test_bond_demo_replay_resets(tmp_path):
    """demo 重玩: completed 后再次 start_demo → 重置重来（新剧情从第 1 场开始）。"""
    engine, st, sid, llm = _setup(tmp_path, MMT_REPLY)
    try:
        bond.bond_start_demo(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        bond.bond_turn(CHARACTER, sid, "x")
        _wait_status(CHARACTER, sid)
        bond.bond_turn(CHARACTER, sid, "x")
        st3 = _wait_status(CHARACTER, sid)
        assert st3["completed"]
        bond.bond_finish(CHARACTER, sid)

        # 重玩: 状态重置 → 首场 round=1（新剧情）
        r = bond.bond_start_demo(CHARACTER, sid)
        assert r["accepted"] and not r.get("resumed")
        st_new = _wait_status(CHARACTER, sid)
        assert st_new["round"] == 1 and not st_new["completed"]
        assert st_new["scene"]["background"] == "class_room"
        print("    bond demo: completed 后重玩 → 重置重来（round 归 1）")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# 失败降级: LLM 一直坏 → closing 场景 + completed（剧情必须终结）
# ----------------------------------------------------------------------------

def test_bond_scene_error_falls_back_to_closing(tmp_path):
    class BadLLM(ScriptedLLM):
        def chat(self, messages, **kw):
            self.snapshots.append([dict(m) for m in messages])
            if "记忆巩固" in messages[0]["content"]:
                return dict(EMPTY_DIGEST)
            raise RuntimeError("LLM 挂了")          # 每次调用都炸 → 重试耗尽
    engine, st, sid, _ = _setup(tmp_path, SCENE_A)  # 占位（BadLLM 覆盖）
    chat._engines[CHARACTER] = MomoTalkEngine(ROOT / "config" / "characters",
                                              BadLLM(), store=st)
    chat._engines[CHARACTER].start_session(CHARACTER)
    chat._engines[CHARACTER].attach_session(sid)
    try:
        bond.bond_start(CHARACTER, sid)
        stt = _wait_status(CHARACTER, sid)
        assert stt["completed"] is True, stt
        assert stt["scene"]["is_end"] is True, stt["scene"]
        assert "夜色渐深" in stt["scene"]["paragraphs"][0]["text"]
        assert stt["error"], "应有错误信息"
        # finish 收尾照常（事件流完整）
        assert bond.bond_finish(CHARACTER, sid)["completed"] is True
        evs = st.events(CHARACTER, sid)
        assert ("bond", "story_end") in [(e.type, e.subtype) for e in evs]
        assert ("marker", "session_end") in [(e.type, e.subtype) for e in evs]
        print("    bond 失败降级: LLM 全挂 → closing 场景 + completed + finish 收尾")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# 场景附带前端渲染信息: 段落 fx（emotion → 特效符号, EffectResolver 单源）
# ----------------------------------------------------------------------------

def test_bond_scene_fx_resolution():
    """_resolve_scene: 段落 emotion → fx 列表（角色表→全局表→空）; 无 emotion/坏数据跳过。"""
    from webgui.routers.bond import _resolve_scene

    scene = {
        "paragraphs": [
            {"text": "a", "emotion": "nomal"},                # nomal → 无特效
            {"text": "b", "emotion": "embarrassed"},          # 遥香键 → blush+notes
            {"text": "c", "emotion": "outburst"},             # 失控 → bang+anger
            {"text": "d"},                                    # 无 emotion → 无 fx
            "plain",                                          # 字符串段落 → 跳过
        ],
        "choices": [],
    }
    out = _resolve_scene(scene, CHARACTER)
    assert out["paragraphs"][0].get("fx") is None
    assert out["paragraphs"][1]["fx"] == ["blush", "notes"]
    assert out["paragraphs"][2]["fx"] == ["bang", "anger"]
    assert "fx" not in out["paragraphs"][3]
    assert "fx" not in out["paragraphs"][4]
    # 空/坏输入降级
    assert _resolve_scene(None, CHARACTER) is None
    print("    scene fx: emotion → 特效符号（embarrassed→blush+notes, outburst→bang+anger）")
