# -*- coding: utf-8 -*-
"""webgui bond 驱动单测 — 羁绊剧情状态机（start/turn/status/finish 全流程）。

ScriptedLLM（不碰 API）:
    bond_start → 首场（story_scene 带选项）→ bond_turn("选A") → 收尾场（story_end）
    → bond_finish → 事件流断言: vn_enter / bond(story_scene+story_end, input/picked)
    / vn_state / vn_exit / session_end + wrapup 收尾 mmt 事件。

与 CLI（test_vn_cli.py）同构的落库格式; 后台线程用轮询等待（sleep 小量）。
运行: python -m pytest tests/webgui/test_bond.py
"""
import json
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

# 契约动作（与 test_vn_cli.py 同构; 2026-08-30 契约强化: emotion 必填 + 按句切分）
SCENE_A = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "段落一。", "emotion": "nomal"},
                   {"text": "段落二。", "emotion": "smile"}],
    "choices": ["选A", "选B"],
    "branches": {"选A": [{"text": "分支一。", "emotion": "nomal"}],
                 "选B": [{"text": "分支二。", "emotion": "smile"}]}}}
STORY_END = {"action": "story_end", "payload": {
    "paragraphs": [{"text": "收尾了。", "emotion": "nomal"}]}}
# 纯叙事场（无 choices）——2026-08-30: 契约语义改为"整段剧情 2~3 次选择,
# 其余场次纯叙事推进（无 choices, 前端点击继续, 后端预生成零等待衔接）"
NARRATIVE = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "纯叙事场。", "emotion": "nomal"}]}}
MMT_TRIGGER = {"actions": [{"action": "mmt_trigger_bond_story",
                            "reply": "嗯…我们走吧", "payload": {"reason": "邀约"}}]}
MMT_REPLY = {"actions": [{"action": "mmt_chat", "reply": "嗯，今晚很开心。", "payload": {}}]}
# 空消化桩（digest_v2 两轮）: Round A 空 episodes; Round B 空 decisions + 好感 5
# （affection_exp_delta=5 → 触发好感事件落库; delta=0 不写事件——好感无变化无需记录）
def _digest_stub(messages):
    """两轮 digest 的假响应（按 system 首行特征区分 A/B 轮）。"""
    head = messages[0]["content"]
    if "记录员" in head:                       # digest_v2_round_a
        return {"episodes": []}
    return {"decisions": [], "evidence": [], "affection_exp_delta": 5}   # round_b


class ScriptedLLM:
    """带 chat(json_object) 的脚本化 LLM——agent_turn / send_vn_scene / digest 都走它。
    emotion 标注调用（2026-09-02: 骨架 emotion 丢弃 → 异步标注全量回填）自动
    返回全 nomal 数组（从 system 编号行数推断句数）, 不消耗脚本。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        self.snapshots.append([dict(m) for m in messages])
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last:               # emotion 标注 → 全 nomal
            import re as _re
            n = len(_re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        if "记录员" in head or "整理者" in head:
            return _digest_stub(messages)              # digest 调用 → 两轮空包
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


def _turn_until_accepted(char_id, sid, text, timeout=10.0):
    """轮询 turn 直到 accepted（pregen 生成中 busy 拒绝 → 重试）。

    pregen 与玩家点击存在竞态: 分支消费后后台预生成下一场（busy=True）,
    玩家立刻点击会被拒——全量负载下更明显。轮询重试消除 flake。
    """
    deadline = time.time() + timeout
    r = {"accepted": False}
    while time.time() < deadline:
        r = bond.bond_turn(char_id, sid, text)
        if r.get("accepted"):
            return r
        time.sleep(0.05)
    raise AssertionError(f"turn 一直被拒: {r}")


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
        # 2026-09-02: 骨架 emotion 丢弃 → 异步标注回填（stub 返回 nomal）
        assert scene1["paragraphs"][1]["emotion"] == "nomal"
        assert scene1["choices"] == ["选A", "选B"]
        assert not st1["completed"]

        # turn: 玩家选 A → 分支消费（同响应, 零等待——分支已在场景里, 不占轮次）
        # → 点继续 → 生成收尾场
        r2 = bond.bond_turn(CHARACTER, sid, "选A")
        assert r2["accepted"] and r2.get("branch") and r2["scene"] is not None
        assert r2["scene"]["paragraphs"][0]["text"] == "分支一。"
        st1b = bond.bond_status(CHARACTER, sid)
        assert st1b["round"] == 1, "分支是场景一部分, 不占轮次"
        r2b = _turn_until_accepted(CHARACTER, sid, "（继续）")
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
        # vn_exit 带剧情完成标志（2026-09-01）: 完整剧情 → completed=True
        exit_ev = [e for e in evs if (e.type, e.subtype) == ("marker", "vn_exit")][0]
        assert exit_ev.payload.get("completed") is True, exit_ev.payload
        # 事件内容: 首场 input=旁白 seed, picked=选A; 收尾场 picked=None
        sc = [e for e in evs if (e.type, e.subtype) == ("bond", "story_scene")][0]
        assert sc.payload["picked"] == "选A", sc.payload
        assert "旁白" in sc.payload["input"], sc.payload
        # 落库场景 emotion = 标注回填值（推进门控保证落库前已就绪; stub = nomal）
        assert sc.payload["paragraphs"][1]["emotion"] == "nomal"
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

        # 剧情结束后 turn 被拒（应调 finish）——先分支消费, 再继续到收尾场
        r2 = bond.bond_turn(CHARACTER, sid, "选A")         # 分支消费（同响应）
        assert r2.get("branch")
        _turn_until_accepted(CHARACTER, sid, "（继续）")    # 分支播完 → 生成收尾场
        _wait_status(CHARACTER, sid)
        r3 = bond.bond_turn(CHARACTER, sid, "选A")         # 已 completed → 拒绝
        assert not r3["accepted"] and r3.get("completed") is True

        # 已完成剧情不可再进入（2026-09-01: 粉泡入口点击由后端裁决拒绝——
        # 中断可 resumed 续进, 已完成则不可再进）
        r4 = bond.bond_start(CHARACTER, sid)
        assert not r4["accepted"] and r4.get("completed") is True, r4

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
    """demo: start_demo → 3 场预设剧本（选项→纯叙事→is_end）→ finish（预设收尾话）。"""
    engine, st, sid, llm = _setup(tmp_path, MMT_REPLY)   # 剧本不耗 LLM 脚本
    try:
        r = bond.bond_start_demo(CHARACTER, sid)
        assert r["accepted"] and r["busy"]
        st1 = _wait_status(CHARACTER, sid)
        assert st1["round"] == 1 and not st1["completed"]
        assert st1["scene"]["background"] == "class_room"
        assert st1["scene"]["paragraphs"][1]["emotion"] == "embarrassed"
        assert st1["scene"]["choices"]                     # 场 1 有选项

        bond.bond_turn(CHARACTER, sid, "「当然可以。」")
        # 分支消费（同响应）: round 不变, scene = 分支内容（零等待展示）
        st1b = bond.bond_status(CHARACTER, sid)
        assert st1b["round"] == 1 and not st1b["completed"]
        assert "亮了起来" in st1b["scene"]["paragraphs"][0]["text"], st1b["scene"]
        # 分支播完 → 点继续 → 场 2（纯叙事, 无选项）
        bond.bond_turn(CHARACTER, sid, "（继续）")
        st2 = _wait_status(CHARACTER, sid)
        assert st2["round"] == 2 and st2["scene"]["background"] == "wildhunt_street"
        assert not st2["completed"]
        assert st2["scene"]["choices"] == []               # 场 2 纯叙事（无选项→继续按钮）

        # 纯叙事场点"（继续）"推进（demo 无预生成——即时弹出收尾场）
        bond.bond_turn(CHARACTER, sid, "（继续）")
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
        # 玩家裁决落库（picked）: 场 1 选项; 场 2 纯叙事 → picked=None
        scs = [e for e in evs if e.subtype == "story_scene"]
        assert scs[0].payload["picked"] == "「当然可以。」", scs[0].payload
        assert scs[1].payload["picked"] is None, scs[1].payload
        # 预设收尾话（后台线程, 轮询等待）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if any("演示收尾" in (e.payload.get("reply") or "")
                   for e in st.events(CHARACTER, sid)):
                break
            time.sleep(0.05)
        assert any("演示收尾" in (e.payload.get("reply") or "")
                   for e in st.events(CHARACTER, sid))
        print("    bond demo: 3 场预设剧本（选项→纯叙事→is_end）→ finish → 事件流完整 + 预设收尾话（零 LLM 调用）")
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
            if "记录员" in messages[0]["content"] or "整理者" in messages[0]["content"]:
                return _digest_stub(messages)
            raise RuntimeError("LLM 挂了")          # 每次调用都炸 → 重试耗尽
    engine, st, sid, _ = _setup(tmp_path, SCENE_A)  # 占位（BadLLM 覆盖）
    chat._engines[CHARACTER] = MomoTalkEngine(ROOT / "config" / "characters",
                                              BadLLM(), store=st)
    chat._engines[CHARACTER].start_session(CHARACTER)
    chat._engines[CHARACTER].attach_session(sid)
    try:
        bond.bond_start(CHARACTER, sid)
        stt = _wait_status(CHARACTER, sid)
        # 2026-09-02: 偶发失败不再一败就 closing——首败保留上一场 + error（可重试）
        assert stt["completed"] is False, stt
        assert stt["error"], "应有错误信息（前端显示重试按钮）"
        # 玩家连续重试（每次 turn 重新生成仍失败）→ 超限（MAX_GEN_FAILURES+1）才 closing
        for _ in range(6):
            bond.bond_turn(CHARACTER, sid, "（继续）")
            stt = _wait_status(CHARACTER, sid)
            if stt["completed"]:
                break
        assert stt["completed"] is True, stt
        assert stt["scene"]["is_end"] is True, stt["scene"]
        assert "夜色渐深" in stt["scene"]["paragraphs"][0]["text"]
        # finish 收尾照常（事件流完整）
        assert bond.bond_finish(CHARACTER, sid)["completed"] is True
        evs = st.events(CHARACTER, sid)
        assert ("bond", "story_end") in [(e.type, e.subtype) for e in evs]
        assert ("marker", "session_end") in [(e.type, e.subtype) for e in evs]
        print("    bond 失败降级: 首败可重试 → 连续超限才 closing + finish 收尾")
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


# ----------------------------------------------------------------------------
# Storyloom bridge 式预生成: 纯叙事场（无 choices）渲染完 → 后台预生成下一场;
# 玩家点"（继续）" → 直接消费（零等待, 不再调 LLM）
# ----------------------------------------------------------------------------

def test_bond_pregenerate_narrative_flow(tmp_path):
    from core.session.events import make_event
    engine, st, sid, llm = _setup(tmp_path, SCENE_A, NARRATIVE, STORY_END)
    try:
        bond.bond_start(CHARACTER, sid)
        st1 = _wait_status(CHARACTER, sid)
        assert st1["scene"]["choices"] == ["选A", "选B"]       # 首场带选项 → 不预生成

        # 选 A → 分支消费（同响应零等待）→ 点继续 → 第 2 场（纯叙事, 无选项）
        # ——生成完自动触发预生成（第 3 场"（继续）"）
        r2 = bond.bond_turn(CHARACTER, sid, "选A")
        assert r2["accepted"] and r2.get("branch"), r2
        assert bond.bond_turn(CHARACTER, sid, "（继续）")["accepted"]
        st2 = _wait_status(CHARACTER, sid)
        assert st2["scene"]["choices"] == []                    # 纯叙事场
        # 等预生成完成（后台线程）——脚本 STORY_END 已被预生成消费
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if not bond.bond_status(CHARACTER, sid)["busy"]:
                break
            time.sleep(0.05)
        assert not bond.bond_status(CHARACTER, sid)["busy"], "预生成应已完成"

        # 点继续 → 直接消费预生成（immediate: pregen=True, busy=False, 不调 LLM）
        r3 = bond.bond_turn(CHARACTER, sid, "（继续）")
        assert r3["accepted"] and r3.get("pregen") and not r3["busy"], r3
        st3 = bond.bond_status(CHARACTER, sid)
        assert st3["completed"] and st3["scene"]["is_end"], st3
        assert st3["scene"]["paragraphs"][0]["text"] == "收尾了。"

        # finish: 补录收尾场（第 3 场）+ wrapup——脚本已耗尽 → agent_turn 失败 →
        # 本地兜底收尾话落库（保证结束回 MMT 必见结语, 不再"强硬回 MMT"）
        r4 = bond.bond_finish(CHARACTER, sid)
        assert r4["completed"] is True
        deadline = time.time() + 10.0
        while time.time() < deadline:
            evs = st.events(CHARACTER, sid)
            if any(e.type == "mmt" and "今晚的事" in (e.payload.get("reply") or "")
                   for e in evs):
                break
            time.sleep(0.05)
        assert any(e.type == "mmt" and "今晚的事" in (e.payload.get("reply") or "")
                   for e in st.events(CHARACTER, sid)), "兜底收尾话应落库"

        # 事件流: 场1(picked=选A) + 场2(picked=None) + 场3(is_end, picked=None)
        evs = st.events(CHARACTER, sid)
        bond_evs = [e for e in evs if e.type == "bond"]
        assert len(bond_evs) == 3, [e.subtype for e in bond_evs]
        assert bond_evs[0].payload["picked"] == "选A", bond_evs[0].payload
        assert bond_evs[1].payload["picked"] is None, bond_evs[1].payload
        assert bond_evs[2].payload["picked"] is None and bond_evs[2].payload["is_end"]
        print("    bond 预生成: 纯叙事场渲染完 → 后台预生成下一场 → 继续零等待消费 + 兜底收尾")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# _system_note: 选项配额 + 表情单一提醒（LLM 每场给选项 / 整场一个表情的软约束）
# ----------------------------------------------------------------------------

def test_system_note_quota_and_emotion_hints():
    from types import SimpleNamespace
    from webgui.bond import BondState, _system_note

    vn = SimpleNamespace(in_memorial=False)
    # 配额: 已用 3/3 → 上限注记（后续场次省略 choices）
    st = BondState(vn=vn, choices_used=3)
    note = _system_note(st) or ""
    assert "配额上限" in note and "3/3" in note, note
    # 已用 1/3 → 少给提示
    st2 = BondState(vn=vn, choices_used=1)
    assert "2" in (_system_note(st2) or ""), _system_note(st2)
    # 表情单一: ≥3 个单元全同 → 提醒
    st3 = BondState(vn=vn, prev_emotions=["nomal", "nomal", "nomal"])
    assert "同一 emotion" in (_system_note(st3) or ""), _system_note(st3)
    # 有变化 → 不提醒; 干净状态 → 无注记
    st4 = BondState(vn=vn, prev_emotions=["nomal", "smile"])
    assert "同一 emotion" not in (_system_note(st4) or "")
    st5 = BondState(vn=vn)
    assert _system_note(st5) is None
    print("    system_note: 选项配额（3/3 上限 / 少给提示）+ 表情单一提醒")


# ----------------------------------------------------------------------------
# 两遍式 C 异步标注: 骨架先显示（emotion 解析挪出玩家等待）→ 标注队列补标 →
# emo_version++ → 前端补切表情; 竞态: 场景被推进 → 标注结果丢弃
# ----------------------------------------------------------------------------

def test_bond_async_annotate(tmp_path):
    """骨架（缺 emotion）→ 主生成立即返回（等待=骨架）→ 异步标注补标 → scene 更新。"""
    skeleton = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "她站在窗边。", "emotion": "nomal"},
                       {"text": "老师来了！"}],      # 缺 emotion → 触发标注
        "choices": ["选A", "选B"],
        "branches": {"选A": [{"text": "分支一。"}],
                     "选B": [{"text": "分支二。", "emotion": "smile"}]}}}
    engine, st, sid, llm = _setup(tmp_path, skeleton, '["smile"]',
                                  '["expectant"]')
    try:
        bond.bond_start(CHARACTER, sid)
        st1 = _wait_status(CHARACTER, sid)          # 主生成完成（骨架, busy=False）
        # 标注队列补标（后台线程）→ 轮询 emo_version 变化 + scene emotion 补齐
        # （桩标注即时完成, 不要求中间态; 中间态由竞态测试的 GatedLLM 覆盖）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            s = bond.bond_status(CHARACTER, sid)
            if s["emo_version"] > st1.get("emo_version", 0) \
                    and s["scene"]["paragraphs"][1].get("emotion"):
                break
            time.sleep(0.05)
        s2 = bond.bond_status(CHARACTER, sid)
        # 2026-09-02: 骨架 emotion 丢弃 → 标注 stub 全 nomal 回填（补标机制不变）
        assert s2["scene"]["paragraphs"][1]["emotion"] == "nomal", s2["scene"]
        # branches 补标（第二个标注调用）
        while time.time() < deadline:
            s = bond.bond_status(CHARACTER, sid)
            if s["scene"]["branches"]["选A"][0].get("emotion"):
                break
            time.sleep(0.05)
        assert bond.bond_status(CHARACTER, sid)["scene"]["branches"]["选A"][0]["emotion"] == "nomal"
        print("    bond 异步标注: 骨架先显示（等待=生成）→ 队列补标 emo_version++ → 正文/branches 补齐")
    finally:
        _cleanup()


def test_bond_annotate_gate_blocks_then_releases(tmp_path):
    """推进门控（2026-09-02, 用户拍板）: 情绪没到位不让点下一轮——标注未完成
    （闸门阻塞）→ turn 被 busy 拦（前端自动轮询）; 标注完成 → 放行推进。
    场景推进后的 worker 写回对象检查保留为防御（门控下竞态不可达, 不污染新场景）。"""
    import threading as _th

    gate = _th.Event()                             # 标注调用阻塞闸门
    released = {"n": 0}

    class GatedLLM:
        """骨架顺序输出; 标注调用（user 消息含'情绪标签'）阻塞等闸门。"""
        def __init__(self, *scripts):
            self._scripts = list(scripts)
        def chat(self, messages, **kw):
            user = messages[-1]["content"] if messages else ""
            if "情绪标签" in user:                    # 标注调用（识别 user 消息）
                gate.wait(timeout=10)
                released["n"] += 1
                return '["nomal", "smile"]'
            if not self._scripts:
                raise RuntimeError("脚本耗尽")
            return self._scripts.pop(0)
        def format_messages(self, *, system_prompt, user_message, history=None):
            msgs = [{"role": "system", "content": system_prompt}]
            msgs.extend(history or [])
            msgs.append({"role": "user", "content": user_message})
            return msgs

    sk1 = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "第一场。", "emotion": "nomal"}, {"text": "缺标。"}],
        "choices": ["继续走"],
        "branches": {"继续走": [{"text": "分支。", "emotion": "nomal"}]}}}
    sk2 = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "第二场。", "emotion": "smile"}]}}
    engine, st, sid, _llm = _setup(tmp_path)
    chat._engines[CHARACTER] = engine
    llm = GatedLLM(sk1, sk2)
    engine.llm = llm
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)               # 骨架1 就绪, 标注线程已阻塞在闸门
        # 等标注线程确实进入阻塞（gate 有等待者）
        deadline = time.time() + 5.0
        while time.time() < deadline and not gate._cond._waiters:
            time.sleep(0.02)
        # 推进门控（2026-09-02）: 标注未完成 → 分支选择也被拦（busy 语义,
        # 前端自动轮询重试）——情绪不到位不推进
        r = bond.bond_turn(CHARACTER, sid, "继续走")
        assert not r["accepted"] and r.get("busy") is True, r
        assert "情绪标注中" in r.get("error", ""), r
        # 释放标注 → 回填完成 → 重试放行（分支消费）
        gate.set()
        r2 = _turn_until_accepted(CHARACTER, sid, "继续走")
        assert r2.get("branch"), r2
        _wait_status(CHARACTER, sid)               # 分支触发的预生成完成（busy=False）
        # 场景推进后 worker 写回对象检查（防御: 丢弃不污染——门控下竞态不可达,
        # 防御保留）。消费预生成 → scene_obj = 骨架2 → 骨架2 自身标注完成
        r3 = _turn_until_accepted(CHARACTER, sid, "（继续）")
        assert r3.get("pregen") or r3.get("accepted"), r3
        deadline = time.time() + 5.0
        while time.time() < deadline:
            s = bond.bond_status(CHARACTER, sid)
            if s["scene"]["paragraphs"] and s["scene"]["paragraphs"][0].get("emotion"):
                break
            time.sleep(0.05)
        s = bond.bond_status(CHARACTER, sid)
        # 新场景段落未被骨架1 的标注污染（对象检查丢弃生效——文本仍是第二场）;
        # 2026-09-02: 骨架 emotion 丢弃 → 标注返回 2 标签 vs 1 句 → 清洗失败兜底 nomal
        assert s["scene"]["paragraphs"][0]["text"] == "第二场。", s["scene"]
        assert s["scene"]["paragraphs"][0]["emotion"] == "nomal", s["scene"]
        print("    bond 门控: 标注未完成 turn 被拦 → 释放后放行; 写回对象检查防御保留")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# 纪念立绘异步生成（方案 A 2026-09-01）: 流式嗅探到 memorial_enter 的 prompt
# 定稿 → 后台生图（与 LLM 剩余输出并行）→ 画廊落盘 → bond_status.memorial_img
# ----------------------------------------------------------------------------

MEMORIAL_ENTER = {"action": "memorial_enter", "payload": {
    "prompt": "湖边, 黑发少女含泪抬头, 月光",
    "paragraphs": [{"text": "（她终于抬起头）老师……我这种人……", "emotion": "embarrass"}],
    "choices": ["抱住她"]}}


class StreamLLM:
    """带 chat_full 的流式 mock（方案 A: chat_full 流式输出触发嗅探回调）。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.probe_chunks: list[str] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last:               # emotion 标注 → 全 nomal
            import re as _re
            n = len(_re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        if "记录员" in head or "整理者" in head:
            return _digest_stub(messages)              # digest 调用 → 两轮空包
        if not self._scripts:
            raise RuntimeError("StreamLLM 脚本耗尽")
        return self._scripts.pop(0)

    def chat_full(self, messages, temperature=0.8, max_tokens=4096,
                  response_format="text", extra_body=None, on_chunk=None):
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last:               # 标注调用（chat_full 路径兜底）
            import re as _re
            n = len(_re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        if "记录员" in head or "整理者" in head:
            return _digest_stub(messages)
        if not self._scripts:
            raise RuntimeError("StreamLLM 脚本耗尽")
        result = self._scripts.pop(0)
        raw = json.dumps(result, ensure_ascii=False)
        for i in range(0, len(raw), 11):               # 任意分块模拟 token 流
            chunk = raw[i:i + 11]
            if on_chunk is not None:
                self.probe_chunks.append(chunk)
                on_chunk(chunk)
        return result

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


class FakeImageGen:
    """fake 生图器: 记录 prompt + 返回假 png（不碰 API）。"""

    def __init__(self, tmp_path: Path):
        self.tmp = Path(tmp_path)
        self.prompts: list[str] = []

    @property
    def is_api_mode(self):
        return True

    def generate(self, prompt, ref_images=None, character_name="角色"):
        self.prompts.append(prompt)
        p = self.tmp / "fake.png"
        p.write_bytes(b"fake-png-bytes")
        return p


def test_bond_memorial_async_image(tmp_path, monkeypatch):
    from webgui import bond as bond_mod

    fake = FakeImageGen(tmp_path)
    monkeypatch.setattr(bond_mod, "_image_generator", lambda: fake)

    llm = StreamLLM(SCENE_A, MEMORIAL_ENTER)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    st = SessionStore(tmp_path)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine
    chat._store = st
    sid = root.session_id
    try:
        # 首场（带选项）→ 分支消费（同响应）→ 分支播放时 pregen 触发
        # → 生成 memorial_enter（流式嗅探）→ 后台生图
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        r = bond.bond_turn(CHARACTER, sid, "选A")
        assert r["accepted"] and r.get("branch"), r

        # 等 pregen（memorial_enter 生成）完成 → in_memorial=True（引擎状态机）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if not bond.bond_status(CHARACTER, sid)["busy"]:
                break
            time.sleep(0.05)
        st1 = bond.bond_status(CHARACTER, sid)
        assert st1["in_memorial"] is True, st1
        assert llm.probe_chunks, "流式嗅探应已观察到 token 流"

        # 等生图线程完成 → 图 URL 就绪（gallery 落盘在 tmp data_root）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if bond.bond_status(CHARACTER, sid)["memorial_img"]:
                break
            time.sleep(0.05)
        st2 = bond.bond_status(CHARACTER, sid)
        assert st2["memorial_img"].startswith(f"/gallery/world1/{CHARACTER}/"), \
            st2["memorial_img"]
        assert fake.prompts == ["湖边, 黑发少女含泪抬头, 月光"], fake.prompts
        # 画廊成对落盘（png + json, 2026-09-02: 世界线角色目录内）——list 只认成对
        gdir = (tmp_path / "worlds" / "world1" / "characters"
                / CHARACTER / "gallery")
        assert len(list(gdir.glob("*.png"))) == 1
        assert len(list(gdir.glob("*.json"))) == 1
        print("    bond 纪念立绘: 流式嗅探 prompt 定稿即生图 → 画廊落盘 → memorial_img 就绪")
    finally:
        chat._engines.pop(CHARACTER, None)
        chat._store = SessionStore(Path("data"))


class FailingImageGen:
    """生图失败 mock: generate 抛异常——纪念应降级纯文字, 剧情照走。"""

    @property
    def is_api_mode(self):
        return True

    def generate(self, prompt, ref_images=None, character_name="角色"):
        raise RuntimeError("生图 API 超时")


def test_bond_memorial_image_failure_degrades(tmp_path, monkeypatch):
    from webgui import bond as bond_mod

    monkeypatch.setattr(bond_mod, "_image_generator", lambda: FailingImageGen())

    llm = StreamLLM(SCENE_A, MEMORIAL_ENTER)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    st = SessionStore(tmp_path)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine
    chat._store = st
    sid = root.session_id
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        r = bond.bond_turn(CHARACTER, sid, "选A")
        assert r["accepted"] and r.get("branch"), r

        # pregen（memorial_enter）完成后: in_memorial=True 但图失败 → memorial_img None
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if not bond.bond_status(CHARACTER, sid)["busy"]:
                break
            time.sleep(0.05)
        deadline = time.time() + 5.0
        while time.time() < deadline:          # 等生图线程失败写回（busy 标志清除）
            if not bond.bond_status(CHARACTER, sid)["memorial_img_busy"]:
                break
            time.sleep(0.05)
        s = bond.bond_status(CHARACTER, sid)
        assert s["in_memorial"] is True, s
        assert s["memorial_img"] is None, s   # 失败 → 纯文字降级（前端无图）
        print("    bond 纪念立绘失败: 降级纯文字, 剧情照走（memorial_img=None）")
    finally:
        chat._engines.pop(CHARACTER, None)
        chat._store = SessionStore(Path("data"))


# ----------------------------------------------------------------------------
# 中途退出收尾（2026-09-01）: vn_exit 带 completed 标志; 中断剧情不 digest
# （实测 bug: 收尾链把未发生的剧情总结成"玩得很开心" + 写进 wiki——记忆污染）
# ----------------------------------------------------------------------------

def test_bond_midway_finish_no_digest(tmp_path):
    """中途退出（剧情未 completed）→ vn_exit completed=False + wrapup 收尾话 + 不 digest。"""
    llm = ScriptedLLM(SCENE_A, MMT_REPLY)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    st = SessionStore(tmp_path)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine
    chat._store = st
    sid = root.session_id
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)              # 首场生成（剧情未走完）
        assert not bond.bond_status(CHARACTER, sid)["completed"]

        # 玩家中途退出（没选选项）→ finish
        r = bond.bond_finish(CHARACTER, sid)
        assert r["completed"] is True

        # vn_exit 带 completed=False（收尾链据此分支）
        evs = st.events(CHARACTER, sid)
        exit_ev = [e for e in evs
                   if (e.type, e.subtype) == ("marker", "vn_exit")][0]
        assert exit_ev.payload.get("completed") is False, exit_ev.payload

        # wrapup 收尾话（MMT_REPLY 脚本）落库 + **无 digest**（无 affection 事件）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if any(e.type == "mmt" for e in st.events(CHARACTER, sid)):
                break
            time.sleep(0.05)
        time.sleep(1.5)                            # 留窗口——digest 若误触发应已落 affection
        affs = [e for e in st.events(CHARACTER, sid)
                if e.type == "affection" and e.subtype == "digest"]
        assert not affs, f"中途退出不应 digest（记忆污染）: {affs}"
        print("    bond 中途退出: vn_exit completed=False + wrapup 收尾话 + 不 digest")
    finally:
        chat._engines.pop(CHARACTER, None)
        chat._store = SessionStore(Path("data"))


# ----------------------------------------------------------------------------
# 入口预热（EXEC_BOND_LATENCY P1）: staged 首场 + adopt + 过期守卫
# ----------------------------------------------------------------------------

def test_bond_prewarm_staged_adopt(tmp_path):
    """staged 预热不落 vn_enter; 点击 adopt 补落 marker（幂等, 不重复）→ resumed。"""
    engine, st, sid, _llm = _setup(tmp_path, SCENE_A)
    try:
        # 触发轮结束 → chat worker 语义: staged=True 预热首场
        r = bond.bond_start(CHARACTER, sid, staged=True)
        assert r["accepted"] and r["busy"]
        st1 = _wait_status(CHARACTER, sid)            # 首场已就绪（阅读期重叠）
        assert st1["round"] == 1 and st1["scene"] is not None

        # staged 期间不落 vn_enter（未点击不得推导 in_vn——防自动拽入 VN）
        assert not [e for e in st.events(CHARACTER, sid)
                    if (e.type, e.subtype) == ("marker", "vn_enter")]

        # 点击（玩家没继续聊 → seq 一致）→ adopt: 补落 marker + resumed
        r2 = bond.bond_start(CHARACTER, sid)
        assert r2["accepted"] and r2.get("resumed") is True
        enters = [e for e in st.events(CHARACTER, sid)
                  if (e.type, e.subtype) == ("marker", "vn_enter")]
        assert len(enters) == 1

        # 再点 → 幂等 resumed, marker 不重复
        r3 = bond.bond_start(CHARACTER, sid)
        assert r3["accepted"] and r3.get("resumed") is True
        enters = [e for e in st.events(CHARACTER, sid)
                  if (e.type, e.subtype) == ("marker", "vn_enter")]
        assert len(enters) == 1
        print("    bond 预热: staged 不落 vn_enter → adopt 补落且幂等")
    finally:
        _cleanup()


def test_bond_prewarm_staged_stale_discard(tmp_path):
    """过期守卫: staged 后事件流前进（玩家又聊）→ 点击丢弃重建（非 resumed）。"""
    engine, st, sid, _llm = _setup(tmp_path, SCENE_A, SCENE_A)
    try:
        bond.bond_start(CHARACTER, sid, staged=True)
        _wait_status(CHARACTER, sid)
        assert not [e for e in st.events(CHARACTER, sid)
                    if (e.type, e.subtype) == ("marker", "vn_enter")]

        # 模拟点击前又发了一条消息（事件流 seq 前进 → 预热上下文过期）
        from core.session.events import make_event
        st.append_event(CHARACTER, sid, make_event(
            "mmt", "mmt_chat", {"player": "刚才说到哪了？", "reply": "（自然接续）"}))

        # 点击 → 丢弃重建（非 resumed; vn_enter 由首进路径落库）
        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] and r.get("resumed") is not True
        st1 = _wait_status(CHARACTER, sid)
        assert st1["round"] == 1 and st1["scene"] is not None
        enters = [e for e in st.events(CHARACTER, sid)
                  if (e.type, e.subtype) == ("marker", "vn_enter")]
        assert len(enters) == 1                       # 重建路径落 marker
        print("    bond 预热守卫: 点击前事件流前进 → 丢弃重建")
    finally:
        _cleanup()
