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
from tests.vn_fixtures import from_v1_scene as _rec  # noqa: E402
from tests.vn_fixtures import scene  # noqa: E402
from llm.image_gen import GeneratedImage
from webgui import bond, chat

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

#: 模块级 store 快照（2026-09-09 审计）: cleanup 一律恢复此值（= 真实 data 默认,
#: import 发生在任何测试运行前）——**禁止硬编码另建 SessionStore**（曾导致
#: wrapup daemon 线程把兜底话写进真实 data/events.jsonl, 测试污染真源）
_ORIG_STORE = chat._store


@pytest.fixture(autouse=True)
def _no_choice_pregen(monkeypatch):
    """本文件脚本队列按"分支播放期单路预生成"老路设计（DESIGN_CHOICE_PREGEN
    N2d: 候选 spawn 默认开）——候选 fork 会消耗 ScriptedLLM 脚本打乱断言;
    关闭候选（老路回归语义由 test_bond_candidates 的 off 用例与回退用例覆盖）。
    """
    monkeypatch.setattr(bond, "_choice_pregen_enabled", lambda: False)

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
        if "情绪标签" in last:               # emotion 标注 → 全 nomal
            import re as _re
            m = _re.search(r"恰 (\d+) 项", last)
            n = int(m.group(1)) if m else 1
            return ["nomal"] * n
        if "变更句数组" in last:                  # place 标注（P3a）→ 无变更
            return []
        if "记录员" in head or "整理者" in head:
            return _digest_stub(messages)              # digest 调用 → 两轮空包
        if "地点 id JSON" in last:                # 换场翻译（P0-7）→ 不切背景
            return {"place": ""}
        if "选中的文件名" in last:                # 选图（第二遍）→ 保持默认图
            return {"image": ""}
        if not self._scripts:
            raise RuntimeError("ScriptedLLM 脚本耗尽")
        return _rec(self._scripts.pop(0))         # v1 桩 → 记录流（P0-7c 适配器）

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
    chat._store = _ORIG_STORE      # 恢复模块快照（禁硬编码真 data）


def _scene_calls(llm) -> list:
    """桩里**主生成**调用（排除 emotion/place 标注、换场翻译与选图——那些是廉价旁路）。"""
    out = []
    for snap in llm.snapshots:
        last = snap[-1]["content"] if snap else ""
        if ("情绪标签" in last or "变更句数组" in last or "地点 id JSON" in last
                or "选中的文件名" in last):
            continue
        out.append(snap)
    return out


# ----------------------------------------------------------------------------
# 全流程: start（首场选项）→ turn（选A）→ finish（收尾 + 事件流断言）
# ----------------------------------------------------------------------------



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

        # 剧情结束后 turn 被拒（应调 finish）——先裁决, 再继续到收尾场
        r2 = bond.bond_turn(CHARACTER, sid, "选A")         # 裁决（同响应就地物化展示）
        assert r2.get("branch")
        # 记录流 v2: 裁决后还有一板反应（待发队列 0 LLM）→ 继续到收尾场
        for _ in range(4):
            if bond.bond_status(CHARACTER, sid).get("completed"):
                break
            _turn_until_accepted(CHARACTER, sid, "（继续）")
            _wait_status(CHARACTER, sid)
        assert bond.bond_status(CHARACTER, sid).get("completed"), "应走到收尾"
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
# 失败降级（2026-09-09 语义修正: 中断/异常 ≠ 失败/完成）: LLM 一直坏 →
# 中止态（completed 保持 False, 不伪收场/不落 story_end）; 玩家可离开走
# 中断收尾（vn_exit completed=False + 中断兜底话, 非"完整剧情"话术）
# ----------------------------------------------------------------------------

def test_bond_scene_error_abort_no_closing(tmp_path):
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
        # 首败: 保留上一场 + error（可重试）, completed 恒 False
        assert stt["completed"] is False, stt
        assert stt["error"], "应有错误信息（前端显示重试按钮）"
        # 玩家连续重试仍失败 → 超限 = 中止态（旧语义在此 closing 伪收场, 已废）
        for _ in range(6):
            bond.bond_turn(CHARACTER, sid, "（继续）")
            stt = _wait_status(CHARACTER, sid)
            if "暂缓" in (stt["error"] or ""):
                break
        assert "暂缓" in (stt["error"] or ""), stt
        assert stt["completed"] is False, "中止态绝不可 completed（伪收场已废）"
        assert not (stt["scene"] or {}).get("is_end"), stt["scene"]
        # 事件流: 零伪收场——无 bond 事件/无 story_end
        evs0 = st.events(CHARACTER, sid)
        assert not any(e.type == "bond" for e in evs0), \
            [e.subtype for e in evs0 if e.type == "bond"]
        # 玩家离开 → 中断收尾: vn_exit completed=False + 中断兜底话
        # （不是"完整剧情"的"好好记住"版——异常/中断不再伪装完成）
        assert bond.bond_finish(CHARACTER, sid)["completed"] is True
        evs = st.events(CHARACTER, sid)
        exits = [e for e in evs if e.type == "marker" and e.subtype == "vn_exit"]
        assert exits and exits[-1].payload.get("completed") is False, \
            [e.payload for e in exits]
        assert not any(e.type == "bond" and e.subtype == "story_end" for e in evs)
        replies = "".join(json.dumps(e.payload, ensure_ascii=False)
                          for e in evs if e.type == "mmt")
        assert "好好记住" not in replies, "中止不应落完整剧情兜底话!"
        print("    bond 失败中止: 首败可重试 → 超限中止态（零伪收场）→ "
              "离开走中断收尾（completed=False + 中断话术）")
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



# ----------------------------------------------------------------------------
# _system_note: v2 下只剩"收尾节奏"类注记（配额 / 表情单调 均已退役）
# ----------------------------------------------------------------------------

def test_system_note_v2_only_pacing_hints():
    """记录流 v2: 选项配额 **与** 表情单调注记都已退役, 只剩篇幅/收尾注记。

    2026-09-13（审计 B8）: "上一场 emotion 全同 → 请切换 emotion 并切新单元"
    是写给 v1（emotion 由主 LLM 内联）的——v2 的 emotion 由标注层按记录给,
    写作者既看不见也没有该字段可写（schema 只有 character/stage + text）。
    那条注记在 v2 下每轮白喂 token, 还会诱导模型为"切换单元"碎化输出。
    """
    from types import SimpleNamespace
    from webgui.bond import BondState, _system_note

    vn = SimpleNamespace(in_memorial=False)
    # 旧的"整段 2~3 次选项配额"注记已退役 —— 无论用过几次都不再念配额
    for used in (1, 3, 9):
        note = _system_note(BondState(vn=vn, choices_used=used)) or ""
        assert "配额" not in note and "choices" not in note, note
    # 中段轮: 仍应有收尾节奏提示（这是 v2 合理的"目标层"注记）
    mid = _system_note(BondState(vn=vn, round=30)) or ""
    assert "收束" in mid or "结尾" in mid, mid
    # 干净状态（未到提醒轮）→ 无注记
    assert _system_note(BondState(vn=vn)) is None
    # 表情单调字段已删——不该再有任何 emotion 相关注记
    st = BondState(vn=vn)
    assert not hasattr(st, "prev_emotions"), "prev_emotions 应已随注记一并删除"
    print("    system_note: 配额/表情单调注记退役 + 收尾节奏保留")


# ----------------------------------------------------------------------------
# 两遍式 C 异步标注: 骨架先显示（emotion 解析挪出玩家等待）→ 标注队列补标 →
# emo_version++ → 前端补切表情; 竞态: 场景被推进 → 标注结果丢弃
def test_bond_interrupt_replay_keeps_place_anchors(tmp_path):
    """中断保护 + 事件回放保留句级 place 锚点（append-only 视觉键定格）:

    已落库事件（含锚点）→ 中断 → bond_start 回放该场 → 锚点随场景保留、
    双路门控就绪 → 点继续零 LLM 交棒续写。"""
    from core.media.emotion_lexicon import load_place_lexicon
    from core.session.events import make_event
    place_keys = load_place_lexicon()
    if not place_keys:                      # 无资产 → 跳过
        print("    (跳过: 无 _director_whitelist 资产)")
        return
    anchor = place_keys[0]
    engine, st, sid, _llm = _setup(tmp_path, STORY_END)
    try:
        st.enter_vn(CHARACTER, sid, "中断的约定")
        # 手工造一条 v2 形态事件: 句项带 place 锚点（模拟标注层已落库）
        st.append_event(CHARACTER, sid, make_event(
            "bond", "story_scene",
            {"paragraphs": [
                {"text": "她在教室里收拾着书包。", "emotion": "nomal"},
                {"text": "她带我穿过走廊，推开了天台的门。",
                 "emotion": "nomal", "place": anchor},
            ], "input": "（种子）……", "picked": None, "is_end": False}))

        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] and r.get("replay") is True, r
        st1 = _wait_status(CHARACTER, sid)
        assert st1["scene"]["paragraphs"][0]["text"] == "她在教室里收拾着书包。"
        # 锚点随回放场景保留（事件流 → narrativize → 场景对象）
        state = bond._state(CHARACTER, sid)
        assert state.scene_obj.paragraphs[-1].get("place") == anchor
        # 回放场景双路门控就绪（回放不占 lane, 标记置位）
        assert bond.bond_status(CHARACTER, sid)["gate_busy"] is False
        # 点继续 → 预生成交棒（story_end）, 零污染
        r2 = _turn_until_accepted(CHARACTER, sid, "（继续）")
        assert r2["accepted"], r2
        evs = st.events(CHARACTER, sid)
        assert len([e for e in evs if e.type == "bond"]) == 1   # 回放不重复落
        print("    interrupt: 事件锚点保留于回放场景 + 双路门控就绪 + 交棒续写")
    finally:
        _cleanup()


def test_promote_gate_blocks_until_pregen_annotated():
    """预生成消费门（2026-09-08）: 预生成场景自身 emotion/place 未就绪 → 不提升
    （busy, 前端轮询）; 就绪（含 place keep 标记）→ 放行——防"消费后标注被丢弃
    → 整板表情卡 nomal"。"""
    from webgui.bond import BondState, _scene_obj_visual_ready
    from core.bond.bond_story import BondScene

    class FakeVN:
        def __init__(self, emo_keys, place_keys):
            self._lexicon_keys = emo_keys
            self._place_keys = place_keys

    def _scene(paras, *, done=False):
        sc = BondScene.from_dict({"paragraphs": paras})
        if done:
            sc._place_done = True
        return sc

    # 无引擎/无场景 → 恒就绪（不阻塞）
    assert _scene_obj_visual_ready(BondState(), None) is True
    # 无词表（无标注能力）→ 恒就绪
    st = BondState()
    st.vn = FakeVN([], [])
    st.demo = None
    sc = _scene([{"text": "没有表情的骨架句。"}])
    assert _scene_obj_visual_ready(st, sc) is True
    # emotion 缺键 → 未就绪; place 标记缺 → 未就绪
    st.vn = FakeVN(["nomal"], ["class_room"])
    assert _scene_obj_visual_ready(st, sc) is False          # 骨架无 emotion
    emo_ok = _scene([{"text": "句一。", "emotion": "nomal"},
                     {"text": "句二。", "emotion": "smile"}])
    assert _scene_obj_visual_ready(st, emo_ok) is False      # place 未标记
    st2 = BondState()
    st2.vn = FakeVN(["nomal"], ["class_room"])
    assert _scene_obj_visual_ready(st2, _scene(
        [{"text": "句一。", "emotion": "nomal"}], done=True)) is True
    # 纪念退出无需标注 → 就绪
    exit_scene = BondScene.from_dict({"paragraphs": ["过渡。"]})
    exit_scene.memorial_exit = True
    st3 = BondState()
    st3.vn = FakeVN(["nomal"], ["class_room"])
    assert _scene_obj_visual_ready(st3, exit_scene) is True
    print("    预生成消费门: 双路未齐拦截 → 齐（含 place keep 标记）放行")


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
        chat._store = _ORIG_STORE


# ----------------------------------------------------------------------------
# 入口预热（EXEC_BOND_LATENCY P1）: staged 首场 + adopt + 过期守卫
# ----------------------------------------------------------------------------





def test_bond_warm_render_deps(tmp_path):
    """P2: 渲染依赖预热幂等——MediaCatalog/特效表构造一次不抛, 资产缺失降级。"""
    from webgui.routers.bond import warm_render, _catalog
    warm_render(CHARACTER)                # 首次: catalog 构造 + 角色特效表
    assert _catalog() is not None         # 单例已就绪（后续 status 不再现构造）
    warm_render(CHARACTER)                # 幂等
    print("    warm_render: catalog + fx 预热幂等")
    # 无 finally —— warm 不碰全局 store/引擎, 无残留


# ----------------------------------------------------------------------------
# 中断接入（2026-09-07）: 中断重进 = 回放已记录前缀 + LLM 后补
# ----------------------------------------------------------------------------

def _interrupt_scene(st, sid, text, *, choices=None, picked=None, title=""):
    """造一条已落库的 bond 场景事件（模拟中断前裁决落库的终态场景）。"""
    from core.session.events import make_event
    payload = {"paragraphs": [{"text": text, "emotion": "nomal"}],
               "is_end": False}
    if title:
        payload["title"] = title
    if choices:
        payload["choices"] = choices
        payload["branches"] = {
            c: [{"text": f"分支·{c}", "emotion": "nomal"}] for c in choices}
    if picked is not None:
        payload["picked"] = picked
    payload["input"] = "（种子）……"
    return st.append_event(CHARACTER, sid, make_event(
        "bond", "story_scene", payload))


def test_reentry_after_quit_is_silent(tmp_path):
    """★ 中途退出后再进 = **静默重进**（用户 2026-09-20 裁决）。

    用户原话: *"不用这样设计啊，不需要任何信息，直接静默重进就可以了，
    但这个 API 可以留着"* ——

    * **机制**: `vn_exit completed=False` 被判成 `interrupted` ⇒ 回放前缀 + 续同一章
      （不新开 `vn_enter`）——这就是"等于之后回来"那一半, 保留;
    * **不注任何信息**: `_system_note` 里那条「老师回来了」**已撤**（钉住: 不得再出现）;
    * **API 保留**: `_prev_chapter_quit()` / `BondState.quit_resume` 留着当事实查询。
    """
    engine, st, sid, _llm = _setup(tmp_path, STORY_END)
    try:
        st.enter_vn(CHARACTER, sid, "中断的约定")
        _interrupt_scene(st, sid, "第一场。", choices=["A", "B"], picked="A")
        try:
            st.exit_vn(CHARACTER, sid, completed=False)      # 若 store 有这个 API
        except AttributeError:
            st.append_marker(CHARACTER, sid, "vn_exit", {"completed": False})

        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] and r.get("replay") is True, r
        state = bond._state(CHARACTER, sid)
        # API: 判据成立 + 进入时打了标（当事实留着, 当前没人消费）
        assert bond._prev_chapter_quit(
            CHARACTER, sid, bond._flow_store(state)) is True
        assert state.quit_resume is True, "进入时应记录『上次是中途退出』这个事实"
        # 静默: 注记不得再出现（撤掉的那条）
        note = bond._system_note(state) or ""
        assert "回来" not in note and "中途离开" not in note, note
        print("    reentry: 中断续章（判据/标记保留）+ **静默重进**（无注记）✓")
    finally:
        _cleanup()


def test_bond_interrupt_replay_single_scene_handoff(tmp_path):
    """中断单场: 重进 → 回放该场（主段落 + 所选分支顺接 + **选项组只读重现**）→ 预生成交棒。"""
    engine, st, sid, _llm = _setup(tmp_path, STORY_END)
    try:
        st.enter_vn(CHARACTER, sid, "中断的约定")
        ev = _interrupt_scene(st, sid, "第一场。", choices=["A", "B"], picked="A")
        # 无 vn_exit——中断在押

        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] and r.get("replay") is True, r
        st1 = _wait_status(CHARACTER, sid)          # 回放首场（预生成在途, busy 等清）
        assert st1["round"] == 1
        paras = st1["scene"]["paragraphs"]
        assert paras[0]["text"] == "第一场。"        # 主段落
        assert paras[-1]["text"] == "分支·A"         # 所选分支顺接
        # 选项组**保留**（2026-09-12 用户反馈: 否则"选哪个选项都一样"）——
        # 前端画成锁定态 + 高亮 picked; 裁决句本身仍不进正文（决策 #37）
        assert st1["scene"]["choices"] == ["A", "B"], st1["scene"]
        assert st1["scene"]["picked"] == "A", st1["scene"]
        assert "A" not in [p["text"] for p in paras]     # 玩家那句不上屏

        # 交棒: 点继续 → 预生成已就绪 → promotion 到续写场（story_end）
        r2 = bond.bond_turn(CHARACTER, sid, "（继续）")
        assert r2["accepted"] and r2.get("pregen") is True, r2
        st2 = bond.bond_status(CHARACTER, sid)
        assert st2["scene"]["is_end"] is True and st2["completed"]
        # 事件流零污染: bond 事件仍只有回放源 1 条（回放不重复落）, vn_enter 无堆叠
        evs = st.events(CHARACTER, sid)
        assert len([e for e in evs if e.type == "bond"]) == 1
        assert len([e for e in evs
                    if (e.type, e.subtype) == ("marker", "vn_enter")]) == 1
        print("    interrupt: 单场回放(段落+分支顺接) → 预生成 promotion 交棒, 零重复落库")
    finally:
        _cleanup()


def test_bond_interrupt_replay_multi_scene_then_live(tmp_path):
    """中断多场: 逐场回放（本地推进）→ 队列尽 → LLM 续写后补。"""
    engine, st, sid, _llm = _setup(tmp_path, STORY_END)
    try:
        st.enter_vn(CHARACTER, sid, "中断的约定")
        _interrupt_scene(st, sid, "第一场。", choices=["A", "B"], picked="A")
        _interrupt_scene(st, sid, "第二场。")

        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] and r.get("replay") is True
        st1 = _wait_status(CHARACTER, sid)
        assert st1["scene"]["paragraphs"][0]["text"] == "第一场。"

        # 逐场回放推进（本地 0 LLM, 直达 scene）
        r2 = bond.bond_turn(CHARACTER, sid, "（继续）")
        assert r2["accepted"] and r2.get("replay") is True and not r2.get("busy")
        st2 = _wait_status(CHARACTER, sid)          # 最后一场（预生成在途）
        assert st2["round"] == 2
        assert st2["scene"]["paragraphs"][0]["text"] == "第二场。"

        # 队列尽 → 交棒: 预生成就绪 → promotion
        r3 = bond.bond_turn(CHARACTER, sid, "（继续）")
        assert r3["accepted"] and r3.get("pregen") is True, r3
        st3 = bond.bond_status(CHARACTER, sid)
        assert st3["scene"]["is_end"] is True and st3["completed"]
        print("    interrupt: 多场逐场回放 → 交棒 LLM 后补(story_end)")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# 记录流 v2（P0-7）: 一块多板 —— 点选项 = 物化展示, 点继续 = 0 LLM 领下一板
# ----------------------------------------------------------------------------

RECORD_BLOCK = "\n".join([
    '{"stage": "switch", "text": "深夜的杂草屋"}',
    '{"character": "igusa_haruka", "text": "……老师，你来了。"}',
    '{"character": "sensei", "text": "我来了。"}',
    '{"character": "sensei", "text": "路上买了点东西。"}',
    '{"character": "igusa_haruka", "text": "「不、不用这样的……」"}',
    '{"stage": "end", "text": "（夜风停了。）"}',
])
RECORD_PICK = "路上买了点东西。"








def test_bond_draft_sidecar_stale_and_finish(tmp_path):
    """草稿新鲜判据: 其后又落了新 bond 事件 / 换了在押段 → 作废; finish → 删除。"""
    engine, st, sid, llm = _setup(tmp_path, RECORD_BLOCK, STORY_END)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        draft_file = Path(bond._draft_path(CHARACTER))
        assert draft_file.is_file()
        # ① 期间又落了一个 bond 事件（模拟另一处推进）→ 草稿过期
        st.append_event(CHARACTER, sid, type="bond", subtype="story_scene",
                        payload={"records": [{"character": CHARACTER, "text": "别处的板。"}],
                                 "input": "（继续）", "picked": None})
        assert bond._draft_load(CHARACTER, sid) is None, "新事件后草稿应判过期"
        assert not draft_file.is_file(), "过期草稿应顺手清掉"
        # ② finish → 草稿删除
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        assert draft_file.is_file()
        bond.bond_finish(CHARACTER, sid)
        assert not draft_file.is_file(), "收尾应删除草稿旁路"
        print("    v2 草稿旁路: 过期作废 + 收尾删除")
    finally:
        _cleanup()




def test_bond_record_stream_prewarm_semantics(tmp_path):
    """记录流预热三层（P0-7c 修正后）:

    · 有槽板 → 不 fork 候选（后继板已在引擎待发队列, fork 只是白复制）;
    · 无槽板 → 预生成链照常（待发有货 0 LLM 领出; 队列空 → 后台真生成 = 块边界桥）;
    · 裁决后 → 立即预生成（必须在 record_picked 之后: 请求历史要含物化裁决行）。
    """
    # 无槽块（1 板）+ 收尾块: 首板落地即预生成收尾 → 点继续 0 LLM 消费
    narr = scene(lines=["（预生成源）她蹲下来看了看那些草。"])
    engine, st, sid, llm = _setup(tmp_path, narr, RECORD_BLOCK)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        assert state.choice_candidates == []                   # 无槽板不 fork
        deadline = time.time() + 10.0
        while time.time() < deadline and state.pregen_scene is None:
            time.sleep(0.05)
        assert state.pregen_scene is not None, "无槽记录流板应照常预生成下一场"
        assert state.pregen_obj.records, "预生成物应仍是记录流板"
        # 消费预生成 → 有槽板: 不 fork 候选
        r = _turn_until_accepted(CHARACTER, sid, "（继续）")
        assert r.get("pregen"), r
        _wait_status(CHARACTER, sid)
        assert bond.bond_status(CHARACTER, sid)["scene"]["choices"] == ["我来了。", RECORD_PICK]
        assert bond._state(CHARACTER, sid).choice_candidates == [], "记录流有槽板不 fork 候选"
        # 裁决 → 立即预生成（反应板 0 LLM 领出 / 或后台生成）
        r2 = bond.bond_turn(CHARACTER, sid, RECORD_PICK)
        assert r2.get("branch"), r2
        state2 = bond._state(CHARACTER, sid)
        deadline = time.time() + 10.0
        while time.time() < deadline and state2.pregen_scene is None and state2.busy:
            time.sleep(0.05)
        assert state2.pregen_scene is not None or state2.busy, "裁决后应立即备料"
        print("    v2 预热: 无槽板预生成链 + 记录流不 fork 候选 + 裁决后备料")
    finally:
        _cleanup()


def test_bond_stream_first_board_visible_before_block_done(tmp_path):
    """渐进渲染（P2-1 前置）: 块还没生成完, 首板已经能读——`busy=True` 时 status 就有场景。"""
    import threading as _th

    first = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "（首板）她抬起头。"}',
        '{"character": "sensei", "text": "选A"}',
        '{"character": "sensei", "text": "选B"}',
        '{"character": "igusa_haruka", "text": "（反应板）她笑了。"}',   # ← 首板在此闭合
    ])
    rest = "\n".join([
        '{"character": "sensei", "text": "选C"}',
        '{"stage": "end", "text": ""}',
    ])
    block = first + "\n" + rest
    gate = _th.Event()
    fed = _th.Event()

    class GatedStreamLLM:
        """前半喂完即等闸门（模拟"块还在写"）——期间 status 应已能读到首板。"""

        def chat(self, messages, **kw):
            return block

        def chat_full(self, messages, **kw):
            on_chunk = kw.get("on_chunk")
            if on_chunk:
                on_chunk(first + "\n")
                fed.set()
                gate.wait(timeout=10)
                on_chunk(rest)
            return block

    engine, st, sid, llm = _setup(tmp_path)
    engine.llm = llm = GatedStreamLLM()
    try:
        bond.bond_start(CHARACTER, sid)
        assert fed.wait(timeout=10), "流式桩未被喂入（渐进渲染未生效）"
        # 块未完成（busy=True）时首板已在 status 里
        early = bond.bond_status(CHARACTER, sid)
        assert early["busy"] is True, early
        assert early["scene"] and early["scene"]["choices"] == ["选A", "选B"], early
        assert [p["text"] for p in early["scene"]["paragraphs"]] == ["（首板）她抬起头。"]
        gate.set()
        stt = _wait_status(CHARACTER, sid)
        assert stt["round"] == 1 and not stt["completed"]
        # 首板只落地一次（流式落地 + 返回后不重复）; 待发板仍在引擎队列
        assert [p["text"] for p in stt["scene"]["paragraphs"]] == ["（首板）她抬起头。"]
        vn = bond._state(CHARACTER, sid).vn
        assert len(vn._pending_boards) == 2, "余下两板应进待发队列"
        assert [p["text"] for p in vn._pending_boards[0].paragraphs] == ["（反应板）她笑了。"]
        assert vn._pending_boards[0].choices == ["选C"]
        assert vn._pending_boards[1].is_end is True
        print("    v2 渐进渲染: 块未完成时首板已可读（busy=True 即有场景）")
    finally:
        gate.set()
        # 等生成线程落定**再**摘 store——否则线程后续落库会读到恢复后的全局
        # store（2026-09-11 事故: 曾把 vn_state 写进真实 data/events.jsonl）
        deadline = time.time() + 10.0
        while time.time() < deadline and bond.bond_status(CHARACTER, sid)["busy"]:
            time.sleep(0.05)
        time.sleep(0.2)
        _cleanup()






def test_memorial_board_skips_annotation_lane(tmp_path):
    """纪念窗口（v2, 2026-09-12）: 立绘隐藏 + 普通背景清空 → emo/place 不占 lane,
    门控**直接就绪**; 引擎 `in_memorial` 由"板含 memorial"置位。

    背景: v1 靠 `memorial_enter` 动作置 `_in_memorial`——记录流下那条路不存在,
    实测该标志永为 False, 于是纪念视觉整条链（隐藏立绘/黑屏/纪念图淡入）死掉,
    而 emo/place 标注却照跑（每次纪念白花 1~2 次调用 + 门控白等）。
    """
    block = scene(switch_to="黄昏的坡道",
                  art_hint="她在坡道尽头回头，夕阳打在脸上",
                  lines=["老师，你看。"],
                  memorial_text="（她抬起头，第一次直视我的眼睛。）",
                  after=["……这句话我想说很久了。"],
                  end_text="（夜色落下来了。）")
    engine, st, sid, _llm = _setup(tmp_path, block)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        sc = state.scene_obj
        assert sc.memorial is True and sc.art_hint, sc.to_dict()
        # ① 纪念区间置位（v1 路径死后曾永为 False）+ 前端信号
        assert state.vn.in_memorial is True
        assert bond.bond_status(CHARACTER, sid)["in_memorial"] is True
        # ② 无视觉键可标 → 判定"无需" + 门控直接就绪（不等标注）
        assert bond._memorial_no_visuals(state, sc) is True
        assert bond._scene_emotions_ready(state) is True
        assert bond._scene_places_ready(state) is True
        assert bond._scene_visual_ready(state) is True
        # ③ 没真发调用: 段落保持无 emotion, emo 队列没被建/没货
        assert all(not (p.get("emotion") or "") for p in sc.paragraphs)
        assert state._anno_queue is None or state._anno_queue.empty()
        print("    v2 纪念: in_memorial 置位 + 不占标注 lane（门控直接就绪）")
    finally:
        _cleanup()












def test_memorial_image_switch_gates_thread(monkeypatch):
    """生图总开关（2026-09-11）: 关 → **不构造生图器、不开生图线程**。

    跑测试默认就是关（tests/conftest.py 会话级 `LIVE2BE_IMAGE=off`）——本用例把
    两个方向都钉住: 关时纪念回调只置空、连线程都不开; 开时正常构造并可用。
    """
    from llm.image_gen import ENV_SWITCH

    made: list = []

    class FakeGen:
        """替身: 构造即记账（真 ImageGenerator 构造会读 settings.toml）。"""

        def __init__(self, *a, **kw):
            made.append(1)
            self.enabled = True
            self.available = True
            self.is_api_mode = True

    monkeypatch.setattr(bond, "ImageGenerator", FakeGen)
    monkeypatch.setattr(bond, "_image_gen", None)

    monkeypatch.setenv(ENV_SWITCH, "off")
    assert bond._image_generator() is None
    assert made == [], "关闭时不得构造生图器"
    st = bond.BondState()
    bond._make_memorial_cb(st, CHARACTER, "sid")("（纪念）她站在夕阳里。")
    time.sleep(0.1)
    assert st.memorial_img_busy is False, "关闭时不得开生图线程"
    assert st.memorial_img_ready is False and st.memorial_img == ""

    monkeypatch.setenv(ENV_SWITCH, "on")
    assert bond._image_generator() is not None
    assert made == [1], "打开后应恰好构造一次"
    assert bond._image_generator() is not None and made == [1], "第二次走缓存, 不重复构造"
    print("    switch: 关=不构造/不开线程, 开=构造一次并复用")


def test_session_switch_blocks_configured_key():
    """证据用例: 本机 settings.toml **配着真 key**（单独构造 available=True）,
    但 tests/conftest.py 的会话级开关是关的 → 纪念路径的 `_image_generator()`
    仍是 None —— 也就是说"跑测试不会真出图"靠的是开关, 不是"没配 key"。
    """
    from llm.image_gen import ImageGenerator
    if not ImageGenerator().is_api_mode:
        pytest.skip("本机未配 IMAGE_API_KEY——本用例无出图风险可证")
    assert bond._image_generator() is None, "会话级生图开关必须压过已配置的 key"
    print("    switch: 配了 key 也不出图（conftest 会话级硬关生效）")
