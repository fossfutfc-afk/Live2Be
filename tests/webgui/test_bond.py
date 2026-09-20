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
from llm import task_labels as T  # noqa: E402
from tests import stub_tasks  # noqa: E402
from tests.vn_fixtures import from_v1_scene as _rec  # noqa: E402
from tests.vn_fixtures import scene  # noqa: E402
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
def _digest_stub(task):
    """两轮 digest 的假响应（**按 task 区分 A/B 轮**, 节点 5b——不再认 prompt 文案）。"""
    if task == T.DIGEST_A:                     # digest_v2_round_a
        return {"episodes": []}
    return {"decisions": [], "evidence": [], "affection_exp_delta": 5}   # round_b


class ScriptedLLM:
    """带 chat(json_object) 的脚本化 LLM——agent_turn / send_vn_scene / digest 都走它。

    标注类调用（emotion / place / 换场翻译 / 选图 / digest 两轮）按 **`task` 身份**
    自动应答（节点 5b, 2026-09-21: 此前按中文关键字分派——改 prompt 文案就静默不命中）,
    不消耗脚本。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots = []
        self.tasks: list[str | None] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        task = kw.get("task")
        self.snapshots.append([dict(m) for m in messages])
        self.tasks.append(task)
        if task in (T.DIGEST_A, T.DIGEST_B):
            return _digest_stub(task)                  # digest → 两轮空包
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                          # 标注类 → 标准应答
            return reply
        if task in T.MAIN:
            if not self._scripts:
                raise RuntimeError("ScriptedLLM 脚本耗尽")
            return _rec(self._scripts.pop(0))          # v1 桩 → 记录流（P0-7c 适配器）
        raise stub_tasks.unknown_task(task)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs

    def chat_full(self, messages, temperature=0.8, max_tokens=4096,
                  response_format="text", on_chunk=None, **kw):
        """流式等价（**生产路径**）——节点 5（2026-09-21）。

        此前本桩只有 `chat()` ⇒ `send_vn_scene` 里 `chat_full is None` ⇒ `delivered`
        恒空 ⇒ **回退批式**, 于是 webgui 状态机测试系统性验证的是**生产不跑**的那条路径。
        这里把整块结果**按行喂** `on_chunk`: 板一闭合即交付（与真机 `LLMClient.chat_full`
        同语义）。标注/digest 调用不传 `on_chunk`, 走 `chat()` 原样（`task=` 也一并转交）。
        """
        out = self.chat(messages, temperature=temperature, max_tokens=max_tokens,
                        response_format=response_format, **kw)
        if on_chunk is not None and isinstance(out, str):
            for line in out.splitlines(keepends=True):
                on_chunk(line)
        return out


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
    """桩里**主生成**调用（按 `task` 过滤：标注/换场翻译/选图/digest 都是廉价旁路）。

    节点 5b: 判据从"user 里有没有中文关键字"换成调用身份——**文案改了也不影响**。
    """
    main = T.MAIN | {T.DIGEST, T.DIGEST_A, T.DIGEST_B}
    return [snap for snap, task in zip(llm.snapshots, llm.tasks) if task not in main]


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
            task = kw.get("task")
            self.snapshots.append([dict(m) for m in messages])
            self.tasks.append(task)
            if task in (T.DIGEST_A, T.DIGEST_B):     # digest 照常应答（收尾链要用）
                return _digest_stub(task)
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
    # 旧的"整段 2~3 次选项配额"注记已退役 —— 2026-09-21 连**计数器**也删了
    # （`choices_used` 只写不读）。与 `prev_emotions` 同款守门: 字段不许无声回来
    st_quota = BondState(vn=vn, round=30)
    assert not hasattr(st_quota, "choices_used"), \
        "choices_used 应已随配额注记一并删除（要恢复配额, 字段与注记得同批回来）"
    note = _system_note(st_quota) or ""
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
    # 纪念板（板级进入点 = `memorial_at` 缺省）无需标注 → 就绪
    mem_scene = BondScene.from_dict({"paragraphs": ["过渡。"], "memorial": True})
    st3 = BondState()
    st3.vn = FakeVN(["nomal"], ["class_room"])
    assert _scene_obj_visual_ready(st3, mem_scene) is True
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


def test_memorial_img_recovered_from_staging(tmp_path):
    """★ 章进行中恢复纪念图: **必须读 overlay（真源 + 暂存）**。

    真机报障（2026-09-20）: *"我才知道我跑的这一章生成了 memorial，但是我玩的时候
    没见过啊"* —— 现场是**图在预热时（14:53:28）就生成并写回执, 而纪念板是收尾板
    （14:58:45）**, 中间 5 分钟回执 marker 只在 `soul/staging/`（B0 整章暂存,
    `vn_exit` 才提交）。旧实现只读真源 ⇒ 查不到 URL ⇒ 前端
    `syncMemorial` 落在"in_memorial 但图为空"那一支 = 清背景 + 什么都不淡入 = **黑屏**。
    """
    engine, st, sid, _llm = _setup(tmp_path, STORY_END)
    try:
        from core.session.staging import staging_store
        sg = staging_store(st)
        # 章内暂存: 预热出的图回执 + 一场（真源此时**一条都没有**）
        sg.append_marker(CHARACTER, sid, "memorial_image",
                         {"url": "/gallery/w1/haruka/预热.png", "prompt": "p"})
        sg.append_marker(CHARACTER, sid, "vn_enter", {"chapter_title": "纪念测试章"})
        # 旧行为（只读真源）→ 空; 现状（读 overlay）→ 命中
        assert bond._persisted_memorial_img(
            CHARACTER, sid, st) == "/gallery/w1/haruka/预热.png"
        print("    memorial: 暂存区的图回执也能恢复（overlay 读）✓")
    finally:
        _cleanup()


def test_completed_entry_refuses_reentry(tmp_path):
    """★ 结局后粉泡翻转前的窗口里"手快重进" → **后端兜底拒绝**（用户 2026-09-20 报障）。

    用户原话: *"结束羁绊剧情后那个粉色气泡有小段延迟才消失，这个时间是足够手快的
    玩家直接重进，后果不堪设想"*。
    前端: `finish(completed=true)` 立刻调 `window.mmtLockBondEntries()` 锁掉点击;
    后端（本用例）: 只读事件流判定"这条入口已走完" → 绝不开新章。
    ⚠️ 中途退出（`completed=False`）**不算走完** —— 那种要允许重进（静默续章）。
    """
    engine, st, sid, _llm = _setup(tmp_path, STORY_END)
    try:
        st.enter_vn(CHARACTER, sid, "已完成的章")
        _interrupt_scene(st, sid, "唯一一场。")
        st.append_marker(CHARACTER, sid, "vn_exit", {"completed": True})
        assert bond._entry_already_done(CHARACTER, sid, st) is True
        r = bond.bond_start(CHARACTER, sid)
        assert r["accepted"] is False and "结束" in r.get("error", ""), r

        # 中断章（completed=False）→ 不算走完, 仍可重进（静默续章）
        st.append_marker(CHARACTER, sid, "vn_enter", {"chapter_title": "第二章"})
        st.append_marker(CHARACTER, sid, "vn_exit", {"completed": False})
        assert bond._entry_already_done(CHARACTER, sid, st) is False
        print("    guard: 已完成入口拒绝重进; 中断入口仍可进（静默续章）✓")
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
    """纪念窗口（v2, 2026-09-12; **2026-09-20 M3 改判据**）: 整板在纪念里 → emo/place
    不占 lane, 门控**直接就绪**; 引擎 `in_memorial` 由"板含 memorial"置位。

    背景: v1 靠 `memorial_enter` 动作置 `_in_memorial`——记录流下那条路不存在,
    实测该标志永为 False, 于是纪念视觉整条链（隐藏立绘/黑屏/纪念图淡入）死掉,
    而 emo/place 标注却照跑（每次纪念白花 1~2 次调用 + 门控白等）。

    ⚠️ **M3 之后"整板"不再等于"含 memorial 的板"**: 进入点是**记录级**
    （`memorial_at` = 触发记录在 paragraphs 里的下标）——触发记录**之前**的那几条
    是在正常视觉下播的（立绘显示着、背景还在）, 所以它们**需要**表情键。
    本用例钉住三条判据（缺一条就会退化成"立绘恒默认表情"）:
      · 触发记录在板中（memorial_at>0）→ **照常标注**;
      · 触发记录在板首（memorial_at==0 / 缺字段）→ 整板即窗口 → 跳过;
      · 窗口从上一板延续（vn.in_memorial, 本板不含纪念）→ 跳过。
    """
    from types import SimpleNamespace

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
        # ② **记录级进入点**: 触发记录之前还有一条正常对话 → 那一条要标
        assert sc.memorial_at == 2, sc.to_dict()
        assert bond._memorial_no_visuals(state, sc) is False
        # ③ 进入点落在板首（或旧档没这个字段）→ 整板即窗口 → 无需标注 + 门控直接就绪
        sc_head = SimpleNamespace(memorial=True, memorial_at=0)
        assert bond._memorial_no_visuals(state, sc_head) is True
        sc_legacy = SimpleNamespace(memorial=True, memorial_at=None)
        assert bond._memorial_no_visuals(state, sc_legacy) is True
        # ④ 窗口从上一板延续（本板不含纪念）→ 跳过
        sc_next = SimpleNamespace(memorial=False, memorial_at=None)
        assert bond._memorial_no_visuals(state, sc_next) is True
        print("    v2 纪念: in_memorial 置位 + 记录级进入点决定是否跳过标注")
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
    assert st.memorial_img == "", "关闭时不得留下图 URL"

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


# ----------------------------------------------------------------------------
# 测试桩 = 生产路径（节点 5, 2026-09-21）
# ----------------------------------------------------------------------------

def test_webgui_runs_on_streaming_production_path(tmp_path):
    """webgui 的生成走**流式（生产）路径**——把"测试 = 生产"变成可断言的事实。

    为什么单列一条: 桩此前没有 `chat_full`, 于是 webgui 状态机测试**系统性验证的是
    生产不跑的那条流水线**（`delivered` 恒空 → 回退批式 `_build_record_boards`）。
    节点 2′ 统一了两条路, 节点 5 把测试接到生产路上——这条用例钉住它别再漂回去。
    """
    engine, st, sid, llm = _setup(tmp_path, SCENE_A, STORY_END, MMT_REPLY)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        vn = bond._state(CHARACTER, sid).vn
        assert vn is not None
        traces = [t for t in vn.trace
                  if str(t.get("action", "")).startswith("record_stream")]
        assert traces, f"应有解析 trace: {vn.trace}"
        actions = [t["action"] for t in traces]
        assert "record_stream/streamed" in actions, \
            f"webgui 应走流式（生产路径）, 实际: {actions}"
        assert all(t.get("delivery_mode") == "stream" for t in traces), traces
        print(f"    node5: webgui 走生产路径（{actions} / delivery_mode=stream）")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# 板级 provisional 状态（节点 1, 2026-09-21）
# ----------------------------------------------------------------------------

def test_scene_logged_is_provisional_until_pick(tmp_path):
    """两层边界一起钉住（节点 1 建立 → 节点 2″ 改成显式生命周期）:

    · **板级**: `state.scene_state` = 板级生命周期 —— 板交付（上屏）后是 `DELIVERED`
      （未提交）, 裁决后 `COMMITTED`（= 旧 `scene_logged=True`）;
    · **章级**: 章内一切事件进 `soul/staging/events.jsonl`, **真源**要等 `vn_exit`
      才整段 append（B0 整章暂存）。

    ⚠️ 所以断言必须读 **overlay**（`staging_store(st)`）——真源看不到章内事件。
    这正是 ARCH_REVIEW P1-6 那条"读路径必须读 overlay"的隐性纪律在测试里的样子。
    """
    from core.session.staging import staging_store

    engine, st, sid, llm = _setup(tmp_path, SCENE_A, STORY_END, MMT_REPLY)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        overlay = staging_store(st)          # = 真源 + 章内暂存（读路径的唯一入口）

        def _bond_paras(store):
            return [e for e in store.events(CHARACTER, sid)
                    if e.type == "bond"
                    and (e.payload or {}).get("paragraphs")]

        # ① 板级: 已交付（板对象就位, 前端能读）但**未提交**
        assert state.scene_obj is not None and state.scene is not None
        assert state.scene_state is bond.BoardLifecycle.DELIVERED, \
            f"刚交付的板必须是 DELIVERED（未提交）, 实得 {state.scene_state}"
        assert bond.bond_status(CHARACTER, sid)["scene_state"] == "delivered"
        assert not _bond_paras(overlay), "provisional: overlay 里也不该有正文"
        # ② 章级: 连真源都不该有（章内一切进暂存）
        assert not _bond_paras(st), "章内不该有任何 bond 正文进真源"

        # 裁决 → 提交（`DELIVERED → COMMITTED`; 正文写进**暂存**）
        _turn_until_accepted(CHARACTER, sid, "选A")
        assert _bond_paras(overlay), "裁决后 overlay 里应有正文（已提交到暂存）"
        assert not _bond_paras(st), "但真源仍没有 —— 章内不进真源（B0 章暂存）"
        print("    lifecycle: DELIVERED（交付未提交）→ COMMITTED（裁决→暂存）；真源等 vn_exit")
    finally:
        _cleanup()


def test_discard_boards_is_traceless(tmp_path):
    """节点 2″: **统一丢弃入口** `_discard_boards` —— 丢 = 什么都不写。

    预生成板（PROVISIONAL）落在三处: `state.pregen_*`、草稿旁路、候选支池。
    §3.1 的不变量说"任何丢弃都不需要写标记到真源"——这条用例把它钉成可断言的事实:
    丢弃前后事件流（overlay = 真源 + 暂存）**一条不多一条不少**, 而三处引用都清了。
    """
    from core.session.staging import staging_store

    engine, st, sid, llm = _setup(tmp_path, _PLAIN_BLOCK, _PLAIN_BLOCK_2)
    try:
        bond.bond_start(CHARACTER, sid)
        deadline = time.time() + 10.0
        while time.time() < deadline and bond._state(CHARACTER, sid).pregen_scene is None:
            time.sleep(0.05)
        state = bond._state(CHARACTER, sid)
        overlay = staging_store(st)
        assert state.pregen_scene is not None, "第二场应被预生成（provisional）"
        assert bond._draft_boards(state), "provisional 板应在草稿旁路里"
        prov_text = [p["text"] for p in state.pregen_scene["paragraphs"]]
        assert bond._draft_load(CHARACTER, sid, bond._flow_store(state)), \
            "草稿旁路的**文件**里应有它（持久化的 provisional）"
        before = [e.seq for e in overlay.events(CHARACTER, sid)]
        cur_state = state.scene_state

        bond._discard_boards(state, CHARACTER, reason="test")

        after = [e.seq for e in overlay.events(CHARACTER, sid)]
        assert after == before, f"丢弃不该写任何事件: {before} → {after}"
        assert state.pregen_obj is None and state.pregen_scene is None
        assert state.pregen_input == ""
        assert state.choice_candidates == []
        # provisional 板从草稿旁路（文件 + 派生视图）里一起消失……
        assert not bond._draft_load(CHARACTER, sid, bond._flow_store(state)), \
            "草稿旁路的文件应被删掉"
        assert not [b for b in bond._draft_boards(state)
                    if [p.get("text") for p in b.get("paragraphs", [])] == prov_text], \
            "派生视图里也不该再有那张 provisional 板"
        # ……但当前板（已在玩家屏上）**不在丢弃范围**: 状态不动
        assert state.scene_obj is not None and state.scene_state is cur_state
        print("    node2″: 丢弃 = 清引用 + 不写任何标记（当前板不动）")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# 预生成与 live 同路径（节点 4′, 2026-09-21）
# ----------------------------------------------------------------------------

#: 一份**首板干净、后续板违规**的记录流（`end` 之后还有记录 = 板级硬违规）。
#: 用它当探针: 违规落在**已交付之后**——live 按 advisory 照常交付, 批式则整体打回。
_LATE_VIOLATION_BLOCK = "\n".join([
    '{"stage": "switch", "text": "教室"}',
    '{"character": "igusa_haruka", "text": "（首板）她抬起头。"}',
    '{"character": "sensei", "text": "选A"}',          # ← 板 1 在此闭合（干净, 已交付）
    '{"character": "igusa_haruka", "text": "（次板）她笑了。"}',
    '{"stage": "end", "text": ""}',
    '{"character": "igusa_haruka", "text": "（end 之后还有记录 = 违规）"}',
])
_PLAIN_BLOCK = "\n".join([
    '{"stage": "switch", "text": "走廊"}',
    '{"character": "igusa_haruka", "text": "（纯叙事板）她低头看鞋尖。"}',
])
_PLAIN_BLOCK_2 = "\n".join([
    '{"stage": "switch", "text": "天台"}',
    '{"character": "igusa_haruka", "text": "（第二板）夜风把她的头发吹起来。"}',
])
_PLAIN_BLOCK_3 = "\n".join([
    '{"stage": "switch", "text": "校门口"}',
    '{"character": "igusa_haruka", "text": "（第三板）她挥了挥手。"}',
])


def _boards_of(state, first=None) -> list:
    """"已生成未播放"的板（首板 + 引擎待发队列）→ payload 列表。

    `first` 缺省取 `state.scene_obj`; 预生成场景要显式传 `state.pregen_obj`
    （那时 `scene_obj` 还是上一场）。
    """
    obj = first if first is not None else state.scene_obj
    out = [obj.to_dict()] if obj is not None else []
    for sc in list(getattr(state.vn, "_pending_boards", None) or []):
        out.append(sc.to_dict())
    return out


def test_pregen_uses_live_delivery_path(tmp_path, monkeypatch):
    """节点 4′: **同一记录流, live 与 pregen 的板载荷逐字节一致**。

    历史分叉: `_pregenerate` 不传 `on_board` ⇒ 引擎走批式（`DeliveryMode.BLOCK`）,
    于是"首板已交付之后才出现的形状违规"在两侧结论相反 —— live（流式）advisory
    照常交付 2 板, 预生成却把整块打回 3 次 → `SceneLoopError` → **预生成失败**
    （玩家点继续时又得等一次完整生成）。预生成承诺的正是"玩家点继续时看到什么",
    所以必须与 live 同源。

    标注旁路被置空（`_enqueue_annotate`）: 它与本用例无关, 却是唯一会让两条路
    的 `to_dict()` 出现时间差（emotion 回填先后）的地方——掐掉才能严格逐字节比。
    """
    monkeypatch.setattr(bond, "_enqueue_annotate", lambda state, scene: None)

    # ① live: 同一块作为**首场**走 `_generate`（流式, 首板经 on_board 落地）
    engine, st, sid, llm = _setup(tmp_path / "live", _LATE_VIOLATION_BLOCK)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        live_state = bond._state(CHARACTER, sid)
        live_boards = _boards_of(live_state)
        live_trace = [dict(t) for t in (live_state.vn.trace or [])]
    finally:
        _cleanup()
    assert len(live_boards) == 2, f"live 应交付 2 板（后续板违规只 advisory）: {live_boards}"
    assert any(t.get("action") == "record_stream/streamed" for t in live_trace), live_trace

    # ② pregen: 同一块作为**第二场**（首场纯叙事无 choices → 落地即自动预生成）
    engine, st, sid, llm = _setup(tmp_path / "pregen", _PLAIN_BLOCK, _LATE_VIOLATION_BLOCK)
    try:
        bond.bond_start(CHARACTER, sid)
        deadline = time.time() + 10.0
        while time.time() < deadline and bond._state(CHARACTER, sid).pregen_scene is None:
            time.sleep(0.05)
        pg_state = bond._state(CHARACTER, sid)
        assert pg_state.pregen_scene is not None, \
            "预生成应成功（同一份输出在 live 侧只是 advisory, 不该把整块打回）"
        pregen_boards = _boards_of(pg_state, pg_state.pregen_obj)
        pregen_trace = [dict(t) for t in (pg_state.vn.trace or [])]

        # 同一交付路径: 预生成也走 STREAM（此前是 record_stream + delivery_mode=block）
        assert any(t.get("action") == "record_stream/streamed" for t in pregen_trace), \
            f"预生成应走流式: {pregen_trace}"
        assert all(t.get("delivery_mode") == "stream" for t in pregen_trace
                   if str(t.get("action", "")).startswith("record_stream")), pregen_trace
        # 逐字节一致（板载荷 = records/paragraphs/choices/is_end/…）
        assert pregen_boards == live_boards, \
            f"同一记录流两条路必须同板:\nlive={live_boards}\npregen={pregen_boards}"
        print(f"    node4′: 预生成 = live 同路径同板（{len(live_boards)} 板逐字节一致）")
    finally:
        _cleanup()


def test_pregen_board_is_provisional_until_adopted(tmp_path):
    """节点 4′: 预生成 = **provisional**（未 adopt 即丢弃）——不落库。

    · 预生成完成时: 板载荷已就绪（`pregen_scene`）、落在**草稿旁路**
      （"已生成未播放"的临时存储）, 但事件流（overlay = 真源 + 章内暂存）里
      **没有**这一板的正文;
    · 玩家消费（`bond_turn("（继续）")` 的提升分支）→ 它成为当前板, 但仍与 live
      交付的板**同一条规则**（`scene_state=DELIVERED`, 未提交）;
    · 再推进一次 → `_log_scene` 写进**暂存**（真源仍要等 `vn_exit`, B0）。

    这条把"丢弃 = 什么都不用清"（`EXEC_PIPELINE_UNIFY` §3.1 不变量）钉成可断言事实。
    """
    from core.session.staging import staging_store

    engine, st, sid, llm = _setup(tmp_path, _PLAIN_BLOCK, _PLAIN_BLOCK_2, _PLAIN_BLOCK_3)
    try:
        bond.bond_start(CHARACTER, sid)
        deadline = time.time() + 10.0
        while time.time() < deadline and bond._state(CHARACTER, sid).pregen_scene is None:
            time.sleep(0.05)
        state = bond._state(CHARACTER, sid)
        assert state.pregen_scene is not None, "第二场应被预生成"
        overlay = staging_store(st)

        def _texts(store):
            return [p["text"] for e in store.events(CHARACTER, sid)
                    if e.type == "bond"
                    for p in ((e.payload or {}).get("paragraphs") or [])]

        provisional_text = [p["text"] for p in state.pregen_scene["paragraphs"]]
        assert provisional_text and "走廊" not in provisional_text, state.pregen_scene
        assert not [t for t in _texts(overlay) if t in provisional_text], \
            f"provisional 板不该进事件流: {_texts(overlay)}"
        # 草稿旁路（临时存储）里**有**它 —— 这才是"已生成未播放"的落点
        drafts = [b for b in bond._draft_boards(state)
                  if [p.get("text") for p in b.get("paragraphs", [])] == provisional_text]
        assert drafts, "预生成板应在草稿旁路里（未 adopt 的临时存储）"

        # 消费（adopt）→ 成为当前板, 未提交（与 live 同规则）
        _turn_until_accepted(CHARACTER, sid, "（继续）")
        state2 = bond._state(CHARACTER, sid)
        assert state2.scene_obj is not None
        assert [p["text"] for p in state2.scene["paragraphs"]] == provisional_text, \
            state2.scene
        assert state2.scene_state is bond.BoardLifecycle.DELIVERED, "刚 adopt 的板仍是未提交"
        assert not [t for t in _texts(overlay) if t in provisional_text], \
            "adopt 只是提升, 还没提交"
        # 再推进一次 → 提交（写暂存; 真源仍无, B0 章内暂存）
        _turn_until_accepted(CHARACTER, sid, "（继续）")
        assert [t for t in _texts(overlay) if t in provisional_text], \
            "推进后应写进暂存（provisional → committed）"
        assert not [t for t in _texts(st) if t in provisional_text], \
            "章内仍不进真源（B0）"
        print("    node4′: 预生成 provisional（不落库）→ adopt → 推进才写暂存")
    finally:
        _cleanup()
