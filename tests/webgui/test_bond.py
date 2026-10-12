"""webgui bond 驱动单测 — 羁绊剧情状态机（start/turn/status/finish 全流程）。

ScriptedLLM（不碰 API）:
    bond_start → 首场（story_scene 带选项）→ bond_turn("选A") → 收尾场（story_end）
    → bond_finish → 事件流断言: vn_enter / bond(story_scene+story_end, input/picked)
    / vn_state / vn_exit / session_end + wrapup 收尾 mmt 事件。

与 CLI（test_vn_cli.py）同构的落库格式; 后台线程用轮询等待（sleep 小量）。
运行: python -m pytest tests/webgui/test_bond.py
"""
import json
import logging
import sys
import threading
import time
from pathlib import Path

import pytest

from core.mmt.engine import MomoTalkEngine
from core.session import SessionStore
from llm import task_labels as T
from tests import stub_tasks
from tests.vn_fixtures import from_v1_scene as _rec
from tests.vn_fixtures import scene
from webgui import bond, chat, deps

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

#: 模块级 store 快照（2026-09-09 审计）: cleanup 一律恢复此值（= 真实 data 默认,
#: import 发生在任何测试运行前）——**禁止硬编码另建 SessionStore**（曾导致
#: wrapup daemon 线程把兜底话写进真实 data/events.jsonl, 测试污染真源）
_ORIG_STORE = deps.store()


@pytest.fixture(autouse=True)
def _no_choice_pregen(monkeypatch):
    """本文件脚本队列按"分支播放期单路预生成"老路设计（DESIGN_CHOICE_PREGEN
    N2d: 候选 spawn 默认开）——候选 fork 会消耗 ScriptedLLM 脚本打乱断言;
    关闭候选（老路回归语义由 test_bond_candidates 的 off 用例与回退用例覆盖）。
    """
    monkeypatch.setattr(deps, "choice_pregen_enabled", lambda: False)

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
# 空消化桩: R1 回空 episodes（⇒ 桩派生出空骨架 ⇒ 链条在 R0 就收工）;
# ⚠️ **M1（2026-10-05）起好感归 R1**, 而 L1（`digest.relate`）**只判关系**
#    —— 旧写法把 `affection_exp_delta` 留在第二支上（那一支早就不读它了）。
def _digest_stub(task):
    """digest 的假响应（**按 task 分轮次**, 节点 5b——不再认 prompt 文案）。"""
    if task == T.DIGEST_RECORD:                     # digest_record（① 记）
        return {"episodes": []}
    return {"relations": []}                        # digest.relate（③ 接 · L1 没看出关系）


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
        if task in (T.DIGEST_RECORD, T.DIGEST_RELATE):
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


def _setup(tmp_path, *scripts, llm=None):
    """引擎 + 事件流会话（tmp_path）+ 引擎/store 注入（bond 落库走 deps.store()）。

    `llm=`（○C8c）: 换掉桩（如带闸门的 `_GatedLLM`）——用于把"丢弃插在生成在途"
    这种时序变成确定性的。
    """
    st = SessionStore(tmp_path)
    llm = llm or ScriptedLLM(*scripts)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine          # 注入（wrapup 复用引擎）
    deps.set_store(st)                         # 注入（bond 落库到 tmp_path, 不污染 data/）
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
    deps.set_store(_ORIG_STORE)    # 恢复模块快照（禁硬编码真 data）


def _scene_calls(llm) -> list:
    """桩里**主生成**调用（按 `task` 过滤：标注/换场翻译/选图/digest 都是廉价旁路）。

    节点 5b: 判据从"user 里有没有中文关键字"换成调用身份——**文案改了也不影响**。
    """
    main = T.MAIN | {T.DIGEST, T.DIGEST_RECORD, T.DIGEST_RELATE}
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
            if task in (T.DIGEST_RECORD, T.DIGEST_RELATE):     # digest 照常应答（收尾链要用）
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
    from core.bond.bond_story import BondScene
    from webgui.bond import BondState, _scene_obj_visual_ready

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
    deps.set_store(st)
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
        deps.set_store(_ORIG_STORE)


# ----------------------------------------------------------------------------
# 入口预热（EXEC_BOND_LATENCY P1）: staged 首场 + adopt + 过期守卫
# ----------------------------------------------------------------------------





def test_bond_warm_render_deps(tmp_path):
    """P2: 渲染依赖预热幂等——MediaCatalog/特效表构造一次不抛, 资产缺失降级。"""
    from webgui.routers.bond import _catalog, warm_render
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


def test_memorial_gallery_records_prompt_source(tmp_path, monkeypatch):
    """★ `gallery json.prompt_source` 必须取自**触发那一次的 BondStoryEngine**。

    回归（2026-09-27 真机发现）: `_memorial_gen` 原先读 `chat._engine(char_id)`
    = **MomoTalkEngine**（另一个类, 从没这个属性）⇒ `getattr` 恒落默认 `""`
    ⇒ `GalleryStore.write` 的"缺省不写"分支生效 ⇒ **字段从来没进过 gallery json**
    （真机 6 张图 + 冒烟世界全部缺）⇒ `art` 配对命中率这个唯一代理指标无法统计。
    写者其实是 `state.vn`（`bond_story/engine.py::_fire_memorial_image`）。

    守门方式: 两个对象上放**不同的值**（MMT 上放错值）——写错源就会立刻红。
    """
    from types import SimpleNamespace

    monkeypatch.setenv("LIVE2BE_IMAGE", "on")     # 会话级 autouse 默认 off
    engine, _st, sid, _llm = _setup(tmp_path, STORY_END)
    try:
        png = tmp_path / "gen.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n")     # write() 只 copy 字节, 不解析

        class _Gen:
            api_model = "stub-model"

            def generate(self, prompt, **kw):
                return SimpleNamespace(path=png, width=512, height=768,
                                       elapsed_s=0.25)

        monkeypatch.setattr(deps, "image_generator", lambda: _Gen())
        state = bond._state(CHARACTER, sid)
        state.vn = SimpleNamespace(in_memorial=True, memorial_prompt_source="art")
        engine.memorial_prompt_source = "错的值（MMT engine 上的）"
        bond._memorial_gen(state, CHARACTER, sid, "画面意向")

        metas = list((tmp_path / "worlds").glob("*/characters/*/gallery/*.json"))
        assert len(metas) == 1, f"应恰好落一张画廊图: {metas}"
        meta = json.loads(metas[0].read_text(encoding="utf-8"))
        assert meta.get("prompt_source") == "art", (
            f"prompt_source 必须取 state.vn（BondStoryEngine）的那个: {meta}")
        assert state.memorial_img, "图 URL 应写回 state（前端淡入用）"
        print("    memorial: prompt_source 归因取自 state.vn ✓")
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


def test_quit_on_unpicked_board_then_pick_is_recorded(tmp_path):
    """★★ 退出时那一板**还没裁决** → 重进后补的那次裁决**必须进事件流**（2026-09-21）。

    修前（探针实测的系统性漏记）: `bond_finish` 把未裁决的选项板以 `picked=None`
    补录进真源并置 COMMITTED（板 = 演出, 事实正确）→ 重进后玩家点选项 → `_log_scene`
    被 COMMITTED 守卫挡下（append-only, 正文不可改）⇒ 那次选择**哪里都进不去**:
    模型窗口缺裁决行、digest 看不见, 而且那板永远"未裁决"（每次重进都能再选一次
    → 同一份日志下会长出两条互斥的后续）。
    修后: 板事件照旧; 补一条 `bond/story_pick {picked, board_seq}`（归属按 `records`
    逐字定位, 不靠"顺序相邻"）; 读侧 `pick_supplements` 把它并回"板 + 老师那句"。
    """
    engine, st, sid, llm = _setup(tmp_path, RECORD_BLOCK, STORY_END)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        board = bond.bond_status(CHARACTER, sid)["scene"]
        assert board["choices"] and not board.get("picked"), board
        bond.bond_finish(CHARACTER, sid)                 # ← 玩家点"结束剧情"（未裁决）
        overlay = bond._flow_store(bond._state(CHARACTER, sid))
        boards = [e for e in overlay.events(CHARACTER, sid) if e.type == "bond"]
        assert len(boards) == 1 and not (boards[0].payload.get("picked") or ""), boards
        board_seq = boards[0].seq

        r = bond.bond_start(CHARACTER, sid)              # ← 重进
        assert r["accepted"], r
        back = bond.bond_status(CHARACTER, sid)["scene"]
        assert back["choices"] == board["choices"] and not back.get("picked"), back
        resp = _turn_until_accepted(CHARACTER, sid, RECORD_PICK)    # ← 补裁决
        assert resp.get("picked") == RECORD_PICK, resp
        time.sleep(0.5)

        picks = [e for e in overlay.events(CHARACTER, sid) if e.subtype == "story_pick"]
        assert len(picks) == 1, [e.subtype for e in overlay.events(CHARACTER, sid)]
        assert picks[0].payload == {"picked": RECORD_PICK, "board_seq": board_seq}
        # 读侧: 补录 + 板 → 回放/窗口看到的就是"板 + 老师那句"
        from core.session.events import pick_supplements
        assert pick_supplements(overlay.events(CHARACTER, sid)) == {board_seq: RECORD_PICK}
        print("    退出于未裁决板 → 重进补裁决: 落成 bond/story_pick（板事件不动）✓")
    finally:
        _cleanup()


def test_restart_replay_then_pick_materializes_into_history(tmp_path):
    """★★ 服务端重启后（走 resume 型回放）在同一板上补裁决: 事件流 + **引擎历史**都要有。

    `record_picked`（A1 物化 `老师：X`）靠 `_last_payload` 重渲历史尾部 —— 回放的板
    不是本引擎生成的, 不设基准时它就是**空转**（下一轮生成看不到裁决行）。
    修法: `BondStoryEngine.adopt_replayed`（回放交棒处设基准）。
    """
    engine, st, sid, llm = _setup(tmp_path, RECORD_BLOCK, STORY_END)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        bond.bond_finish(CHARACTER, sid)                 # 退出（未裁决）
        bond._bonds.pop((CHARACTER, sid), None)          # ← 模拟服务端重启（丢内存态）

        r = bond.bond_start(CHARACTER, sid)              # ← 重进（回放前缀）
        assert r["accepted"] and r.get("replay") is True, r
        state = bond._state(CHARACTER, sid)
        assert state.scene.get("choices") and not state.scene.get("picked"), state.scene
        _turn_until_accepted(CHARACTER, sid, RECORD_PICK)
        time.sleep(0.5)
        evs = bond._flow_store(state).events(CHARACTER, sid)
        assert [e for e in evs if e.subtype == "story_pick"], [e.subtype for e in evs]
        hist = "\n".join(str(m.get("content", "")) for m in state.vn._history)
        assert RECORD_PICK in hist, "补的裁决必须物化进引擎历史（否则下一轮看不到）"
        print("    重启回放末板补裁决: 事件流有 story_pick + 引擎历史已物化 ✓")
    finally:
        _cleanup()


def test_live_pick_writes_no_story_pick(tmp_path):
    """对照: **正常**裁决（板还没落库）仍走 `_log_scene`, 不产生任何补录事件。"""
    engine, st, sid, llm = _setup(tmp_path, RECORD_BLOCK, STORY_END)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        resp = _turn_until_accepted(CHARACTER, sid, RECORD_PICK)
        assert resp.get("picked") == RECORD_PICK, resp
        time.sleep(0.5)
        evs = bond._flow_store(bond._state(CHARACTER, sid)).events(CHARACTER, sid)
        assert not [e for e in evs if e.subtype == "story_pick"], evs
        logged = [e for e in evs if e.type == "bond"]
        assert len(logged) == 1 and logged[0].payload["picked"] == RECORD_PICK, logged
        print("    正常裁决: 零新增事件类型（仍是一条板事件带 picked）✓")
    finally:
        _cleanup()


def test_log_pick_without_logged_board_writes_nothing(tmp_path):
    """守门（宁缺勿错）: 板**还没落库**时 `_log_pick` 不写任何东西。

    正常裁决的板此刻不在事件流里（裁决才落库）——补录事件只服务于"已落库但未裁决"的板;
    定位判据（`records` 逐字相同）拿不到归属时**宁可什么都不写**, 绝不把裁决挂错板。
    """
    engine, st, sid, llm = _setup(tmp_path, RECORD_BLOCK, STORY_END)
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        before = len(bond._flow_store(state).events(CHARACTER, sid))
        assert bond._log_pick(state, CHARACTER, sid, "选A") == 0
        assert len(bond._flow_store(state).events(CHARACTER, sid)) == before
        print("    补录归属拿不到 → 一个事件都不写（不猜、不挂错板）✓")
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








def test_draft_queue_survives_restart_after_prewarm(tmp_path, caplog):
    """⭐ **中断章 + 预热缓存进场 ⇒ 后继板必须从草稿恢复**（2026-10-08 真机丢板的那条路径）。

    真机时序（haruka `被感谢的人`）: 预热一次写了 6 板 40 条 → 玩家只看了首板就杀了进程
    （等代码更新）→ 重启进章: 首板由 `soul/prewarm.json` 给出（`src=prewarm`, 0 LLM）,
    **余下 5 板（含纪念那板）却重新生成了一遍**（`src=gen dur=20531ms`）—— 草稿里明明
    躺着它们。

    根因: 恢复闸门写的是 `_last_bond_seq(...) == 0`（"全库一条 bond 事件都没有"）,而
    长线角色真源里早有前几章的板 ⇒ **闸门恒 False**; 注释里那句"已有已落库板（将被回放）
    的交给回放交棒处"只覆盖"走回放进场", 而这里是**走预热缓存进场**（`entry.py` 命中即
    return）⇒ 两边都不接。

    ⇒ 判据: 闸门必须看**当前在押章**有没有已落库板（`_open_chapter_board_seq`），
    而不是全库。
    """
    engine, st, sid, llm = _setup(tmp_path, RECORD_BLOCK, STORY_END)
    try:
        # ① 前几章: **已闭合**的段 + 真源里**已经有** bond 板事件
        #    （长线角色的常态 —— 旧闸门 `_last_bond_seq == 0` 就死在这）
        st.append_marker(CHARACTER, sid, "vn_enter", {"chapter_title": "上一章"})
        st.append_event(CHARACTER, sid, type="bond", subtype="story_scene",
                        payload={"records": [{"character": CHARACTER,
                                              "text": "上一章的板。"}],
                                 "input": "（继续）", "picked": None})
        st.append_marker(CHARACTER, sid, "vn_exit", {"completed": True})
        # ①b **更新的触发轮**（被感谢的人 的入口）—— 缺了它 `_entry_already_done`
        #     会以"倒序先遇到 vn_exit completed"为由**拒绝重进**（只看真源的兜底闸）
        st.append_event(CHARACTER, sid, type="mmt", subtype="mmt_trigger_bond_story",
                        payload={"chapter_title": "被感谢的人", "player": "在吗"})
        # ② 当前章: 只有 vn_enter（中断在这一章, **零已落库板**）
        #    ⇒ `_interrupted_replay_queue` 返回 None（没有回放前缀）⇒ 走**预热缓存支路**,
        #      与真机 01:33 那次完全同形（日志 `src=prewarm` + `bond_gen ok … cache`）
        st.append_marker(CHARACTER, sid, "vn_enter", {"chapter_title": "被感谢的人"})
        # ③ 草稿 = 上一次生成留下的"已生成未播放": 首板 + 后继两块
        nxt1 = bond.BondScene.from_dict(
            {"paragraphs": [{"text": "（草稿后继一）她抬起头。", "emotion": "nomal"}],
             "records": [{"character": CHARACTER, "text": "（草稿后继一）她抬起头。"}],
             "is_end": False})
        nxt2 = bond.BondScene.from_dict(
            {"paragraphs": [{"text": "（草稿后继二）她笑了。", "emotion": "smile"}],
             "records": [{"character": CHARACTER, "text": "（草稿后继二）她笑了。"}],
             "is_end": False})
        first = {"paragraphs": [{"text": "（首板）老师, 你来了。", "emotion": "nomal"}],
                 "records": [{"character": CHARACTER, "text": "（首板）老师, 你来了。"}],
                 "is_end": False}
        draft_file = Path(bond._draft_path(CHARACTER))
        draft_file.parent.mkdir(parents=True, exist_ok=True)
        draft_file.write_text(json.dumps({
            "boards": [first, nxt1.to_dict(), nxt2.to_dict()],
            "input": "（继续）",
            "base_seq": bond._last_bond_seq(CHARACTER, sid, st),
            "vn_enter_seq": bond._open_vn_seq(CHARACTER, sid, st),
            "round": 1, "ts": time.time(),
        }, ensure_ascii=False), encoding="utf-8")
        # ④ 预热缓存 = 首板（重启后 entry 的 `src=prewarm` 分支就吃它）
        bond._prewarm_cache_save(CHARACTER, sid, first, "（继续）", "被感谢的人",
                                 store=st)
        # ⑤ 进场
        with caplog.at_level(logging.INFO, logger="webgui.bond"):
            bond.bond_start(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        got = [p["text"] for sc in (state.vn._pending_boards or [])
               for p in (sc.paragraphs or [])]
        assert got == ["（草稿后继一）她抬起头。", "（草稿后继二）她笑了。"], (
            "中断章的后继板没从草稿恢复 ⇒ 会白烧一次生成（真机 20s）: " + repr(got))
        assert [p["text"] for p in (state.scene_obj.paragraphs or [])] == \
            ["（首板）老师, 你来了。"], "首板应由预热缓存给出"
        assert "bond_draft_q" in caplog.text or "bond_draft_queued" in caplog.text, \
            [r.getMessage() for r in caplog.records]
        # ⑥ 推进一次: 必须**领队列**（0 LLM），不是重新生成
        calls_before = len(_scene_calls(llm))
        _wait_status(CHARACTER, sid)
        r = _turn_until_accepted(CHARACTER, sid, "（继续）")
        assert r.get("accepted"), r
        state2 = bond._state(CHARACTER, sid)
        assert [p["text"] for p in (state2.scene_obj.paragraphs or [])] == \
            ["（草稿后继一）她抬起头。"], "推进应先播草稿的后继板"
        assert len(_scene_calls(llm)) == calls_before, \
            "领队列不该产生新的主生成调用（0 LLM）"
        print("    v2 草稿旁路: 中断章 + 预热缓存进场 → 后继板恢复并用 0 LLM 领出 ✓")
    finally:
        _cleanup()


def test_draft_queue_not_restored_when_chapter_has_boards(tmp_path, caplog):
    """反例: **当前章已有已落库板** ⇒ 不走"草稿后继板"那条路（交给回放交棒处）。

    为什么必须钉: 两条恢复路径各管一段 ——
      · 当前章**零**板 → `_draft_pending`（只补后继, 首板由预热缓存给）
      · 当前章**有**板 → 回放交棒处 `_draft_queue`（全量, 因为屏上正在放已落库前缀）
    判据不同 ⇒ 判据写错就会"同一块板被注入两次"（真机表现: 重进后同一段戏讲两遍）。
    这里断言: 有板时走**回放支路**, 且**没有** `bond_draft_q`（= 后继-only 那条没被触发）。
    """
    engine, st, sid, llm = _setup(tmp_path, RECORD_BLOCK, STORY_END)
    try:
        # ① 当前章: vn_enter + **一块已落库板**（中断在这一章的中间）
        st.append_marker(CHARACTER, sid, "vn_enter", {"chapter_title": "被感谢的人"})
        st.append_event(CHARACTER, sid, type="bond", subtype="story_scene",
                        payload={"records": [{"character": CHARACTER,
                                              "text": "（已落库）她抬起头。"}],
                                 "paragraphs": [{"text": "（已落库）她抬起头。",
                                                 "emotion": "nomal"}],
                                 "input": "（继续）", "picked": None})
        # ② 草稿: 首板 + 一块后继（都由上一次生成留下）
        first = {"paragraphs": [{"text": "（草稿首板）", "emotion": "nomal"}],
                 "records": [{"character": CHARACTER, "text": "（草稿首板）"}],
                 "is_end": False}
        nxt = {"paragraphs": [{"text": "（草稿后继）", "emotion": "nomal"}],
               "records": [{"character": CHARACTER, "text": "（草稿后继）"}],
               "is_end": False}
        p = Path(bond._draft_path(CHARACTER))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "boards": [first, nxt], "input": "（继续）",
            "base_seq": bond._last_bond_seq(CHARACTER, sid, st),
            "vn_enter_seq": bond._open_vn_seq(CHARACTER, sid, st),
            "round": 1, "ts": time.time()}, ensure_ascii=False), encoding="utf-8")
        with caplog.at_level(logging.INFO, logger="webgui.bond"):
            r = bond.bond_start(CHARACTER, sid)
        assert r.get("replay") is True, f"有落库板时应走回放支路: {r}"
        assert "bond_draft_q " not in caplog.text, \
            "后继-only 那条路不该在有落库板时触发（会与回放交棒处重复注入）: " \
            + caplog.text
        print("    v2 草稿旁路: 当前章有板 → 只走回放交棒（后继-only 那条不触发）✓")
    finally:
        _cleanup()


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
        # ⭐ 2026-09-23 真机报障的回归: 前端那个值必须来自**板自己的窗口快照**,
        # 而不是引擎"解析到哪了"的活标志。预热/预生成会提前解析后面的块 ⇒ 交付纪念板时
        # 活标志早被翻回 False ⇒ 前端不黑屏、不淡入图（真机症状: "纪念图没给我放"）。
        # 这里手工把活标志打回 False 来复现那个时刻, 前端信号必须**不受影响**。
        state.vn._in_memorial = False
        assert sc.in_memorial is True, "板自带窗口快照"
        assert bond.bond_status(CHARACTER, sid)["in_memorial"] is True, \
            "活标志被提前翻掉时, 前端信号仍必须为真（板级快照说了算）"
        state.vn._in_memorial = True
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

    monkeypatch.setattr(deps, "ImageGenerator", FakeGen)
    monkeypatch.setattr(deps, "_image_gen", None)

    monkeypatch.setenv(ENV_SWITCH, "off")
    assert deps.image_generator() is None
    assert made == [], "关闭时不得构造生图器"
    st = bond.BondState()
    bond._make_memorial_cb(st, CHARACTER, "sid")("（纪念）她站在夕阳里。")
    time.sleep(0.1)
    assert st.memorial_img_busy is False, "关闭时不得开生图线程"
    assert st.memorial_img == "", "关闭时不得留下图 URL"

    monkeypatch.setenv(ENV_SWITCH, "on")
    assert deps.image_generator() is not None
    assert made == [1], "打开后应恰好构造一次"
    assert deps.image_generator() is not None and made == [1], "第二次走缓存, 不重复构造"
    print("    switch: 关=不构造/不开线程, 开=构造一次并复用")


def test_session_switch_blocks_configured_key():
    """证据用例: 本机 settings.toml **配着真 key**（单独构造 available=True）,
    但 tests/conftest.py 的会话级开关是关的 → 纪念路径的 `_image_generator()`
    仍是 None —— 也就是说"跑测试不会真出图"靠的是开关, 不是"没配 key"。
    """
    from llm.image_gen import ImageGenerator
    if not ImageGenerator().is_api_mode:
        pytest.skip("本机未配 IMAGE_API_KEY——本用例无出图风险可证")
    assert deps.image_generator() is None, "会话级生图开关必须压过已配置的 key"
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


def test_emo_lane_actually_publishes(tmp_path, caplog):
    """标注 lane **真的把结果写回状态**（不只是"门控就绪"）。

    为什么单开这条（○C8b 实测抓到的真 bug）: C4 把 `_ms_since` 搬进 `util.py` 时漏了
    `lanes.py` 的 import ⇒ 标注 worker 在**写回那块之前**抛 `NameError`, 被
    `except Exception`（保活）吞成一行 WARNING; 而门控靠 `_fallback_fill` 照样"就绪"
    —— 于是 **功能静默失效 + 测试全绿**（`emo_version` 永不递增, 前端永远拿不到标注）。
    这里钉两件: ① `emo_version` 至少涨 1（= 走完了写回块）② 日志里没有"标注处理异常"。
    """
    engine, st, sid, llm = _setup(tmp_path, _PLAIN_BLOCK, _PLAIN_BLOCK_2)
    try:
        with caplog.at_level(logging.WARNING):
            bond.bond_start(CHARACTER, sid)
            deadline = time.time() + 10.0
            while time.time() < deadline and bond._state(CHARACTER, sid).emo_version < 1:
                time.sleep(0.05)
        state = bond._state(CHARACTER, sid)
        assert state.emo_version >= 1, (
            f"emo lane 没写回: emo_version={state.emo_version}（写回块被异常跳过了?）"
            f"\n日志: {caplog.text[-800:]}")
        assert "标注处理异常" not in caplog.text, (
            "标注 worker 抛异常（宽 except 会把它吞成 WARNING）:\n" + caplog.text[-800:])
        assert state.scene is not None and state.scene["paragraphs"][0].get("emotion"), \
            "写回的板应带标注好的 emotion"
        print(f"    lane 写回: emo_version={state.emo_version}, 首段 emotion="
              f"{state.scene['paragraphs'][0].get('emotion')}")
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
    monkeypatch.setattr(deps, "enqueue_annotate", lambda state, scene: None)

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


# ----------------------------------------------------------------------------
# 丢弃世代（○C8c, 2026-09-21）: `_discard_boards` 之后, 在途的落地一律作废
# ----------------------------------------------------------------------------


class _GatedLLM(ScriptedLLM):
    """在第 `block_main` 次**主生成**调用上阻塞（放行由测试决定）。

    ○C8c 的竞态只在"丢弃发生在预生成**在途**"时出现 —— 靠 sleep 撞时序必然 flake,
    所以把闸门装进桩里: 主生成一进 LLM 调用就 `entered.set()`, 测试做完丢弃再
    `gate.set()`。标注类调用（`place`/`emotion`）不在 `T.MAIN` 里, 不受影响。
    """

    def __init__(self, *scripts, block_main: int = 2):
        super().__init__(*scripts)
        self.entered = threading.Event()      # 第 block_main 次主生成已进入调用
        self.gate = threading.Event()         # 测试放行
        self._block_main = block_main
        self._n_main = 0

    def chat(self, messages, temperature=0.8, max_tokens=4096,
             response_format="text", **kw):
        if kw.get("task") in T.MAIN:
            self._n_main += 1
            if self._n_main == self._block_main:
                self.entered.set()
                assert self.gate.wait(10.0), "测试没放行（闸门超时）"
        return super().chat(messages, temperature=temperature,
                            max_tokens=max_tokens,
                            response_format=response_format, **kw)


def test_stale_pregen_landing_is_dropped(tmp_path, caplog):
    """○C8c: **丢弃之后在途落地的预生成板不许复活**（`board_epoch` 世代复核）。

    形态: 首板落地 → `_generate` 的 finally 开始预生成（busy=True）→ 丢弃这时插进来
    （`_discard_boards` 是唯一丢弃入口; `DESIGN_RESEND` 的重发/拒绝邀约就是这么调的）
    → 预生成线程随后跑完。**没有世代复核时**它会把 `pregen_scene` 与草稿文件原样写回:
    板在玩家眼前复活, 而 `bond_boards_discarded` 那行"唯一痕迹"白打。

    后半段还钉住反向: 世代只作废**更早出生**的落地, **不封禁**后续生成。
    """
    caplog.set_level(logging.INFO)
    engine, st, sid, llm = _setup(
        tmp_path, llm=_GatedLLM(_PLAIN_BLOCK, _PLAIN_BLOCK_2, _PLAIN_BLOCK_3))
    try:
        bond.bond_start(CHARACTER, sid)
        assert llm.entered.wait(10.0), "第二块（预生成）应进入 LLM 调用"
        state = bond._state(CHARACTER, sid)
        epoch0 = state.board_epoch
        assert state.pregen_scene is None, "预生成还没落地"

        bond._discard_boards(state, CHARACTER, reason="test-stale")
        assert state.board_epoch == epoch0 + 1, "丢弃必须推进世代（board_epoch）"
        llm.gate.set()

        deadline = time.time() + 10.0
        while time.time() < deadline and state.busy:
            time.sleep(0.05)
        assert not state.busy, "预生成线程应已结束"
        assert state.pregen_obj is None and state.pregen_scene is None, \
            f"陈旧落地复活了预生成板: {state.pregen_scene}"
        assert not bond._draft_load(CHARACTER, sid, bond._flow_store(state)), \
            "陈旧落地把草稿旁路写回来了"
        assert "bond_board_stale" in caplog.text, \
            f"陈旧落地必须留一行痕迹（可 grep）: {caplog.text}"

        # 反向: 丢弃之后的**新**生成照常落地（世代不是永久封禁）
        bond._pregenerate(state, CHARACTER, sid)
        deadline = time.time() + 10.0
        while time.time() < deadline and state.pregen_scene is None:
            time.sleep(0.05)
        assert state.pregen_scene is not None, "丢弃只作废更早的落地, 不该封禁后续生成"
        print("    ○C8c: 丢弃后陈旧预生成被拦（无残留）; 新一代预生成照常落地")
    finally:
        _cleanup()


def test_discard_inside_pregen_landing_window(tmp_path, caplog, monkeypatch):
    """○C8c 细窗口: 板**已写进** `pregen_scene`、草稿**还没落** → 丢弃插在中间。

    这就是 `test_discard_boards_is_traceless` 全量跑偶发红的精确形态: 它轮询到
    `pregen_scene` 非 None 就立刻丢弃, 而预生成线程还剩一次 `_draft_save` 没做 ——
    于是草稿文件在丢弃**之后**被写回来（旧板复活, 单跑常绿/全量偶发红 = 典型时序 flake）。

    把它钉成确定性的: 在预生成那次 `_draft_save` 入口先丢弃, 再让它照常执行 ——
    世代复核（与丢弃同一把 `state._lock`）必须让它写不进去。
    """
    from webgui.bond import pregen as pregen_mod

    caplog.set_level(logging.INFO)
    engine, st, sid, llm = _setup(tmp_path, _PLAIN_BLOCK, _PLAIN_BLOCK_2)
    real = pregen_mod._draft_save
    fired: list[int] = []

    def gated_draft_save(state, char_id, session_id, *, epoch=None):
        # **只对预生成落地**那次动手: 那时 `pregen_obj` 已经被写进去; 首板落地时
        # （`_scene_landed`）它还是 None —— 那条路不是本用例要模拟的窗口。
        if epoch is not None and state.pregen_obj is not None:
            fired.append(state.board_epoch)
            bond._discard_boards(state, char_id, reason="window")
        return real(state, char_id, session_id, epoch=epoch)

    monkeypatch.setattr(pregen_mod, "_draft_save", gated_draft_save)
    try:
        bond.bond_start(CHARACTER, sid)
        state = bond._state(CHARACTER, sid)
        deadline = time.time() + 10.0
        while time.time() < deadline and (state.busy or not fired):
            time.sleep(0.05)
        assert fired, "预生成落地那次 `_draft_save` 应被触发（用例前提）"
        assert state.pregen_obj is None and state.pregen_scene is None, \
            "丢弃后的落盘窗口里不许留下预生成引用"
        assert not bond._draft_load(CHARACTER, sid, bond._flow_store(state)), \
            "草稿文件不许被「写完状态、再落草稿」的窗口复活"
        assert "bond_draft_stale" in caplog.text, \
            f"被拦下的落盘要留痕: {caplog.text}"
        print("    ○C8c: 'pregen_scene 已可见、草稿未落' 的窗口里丢弃 → 草稿不复活")
    finally:
        _cleanup()


def test_draft_helpers_are_not_called_holding_state_lock():
    """○C8c 静态守门: `_draft_save` / `_discard_boards` 自己取 `BondState._lock`。

    任何**已经持有同一把锁**的调用点都是同线程死锁（`threading.Lock` 不可重入）。
    为什么值得钉: 这两个函数的"复核 + 写盘/清引用"临界区, 正是"丢弃与落地互斥"
    的**唯一**依据（○C8c 修的就是这个窗口）——而"顺手把 `_draft_save` 挪进某个
    `with state._lock:` 块"读起来无害, 跑起来直接挂死, 且只在特定路径上出现。
    """
    import ast

    bad: list[str] = []
    for path in sorted((ROOT / "webgui").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.With):
                    continue
                if not any(isinstance(it.context_expr, ast.Attribute)
                           and it.context_expr.attr == "_lock"
                           for it in node.items):
                    continue
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                            and sub.func.id in ("_draft_save", "_discard_boards"):
                        bad.append(f"{path.relative_to(ROOT).as_posix()}:{sub.lineno}"
                                   f"（{fn.name} 的 with _lock 块内）")
    assert not bad, (
        "这些地方在**已持有** `state._lock` 时又去取它（threading.Lock 不可重入 → "
        "死锁）:\n  " + "\n  ".join(bad))
    print("    ○C8c: 草稿/丢弃助手没有「持锁再取锁」的调用点")
