# -*- coding: utf-8 -*-
"""webgui 羁绊剧情驱动 — CLI run_bond_story_vn（core/ui/vn_cli.py）的异步化状态机。

CLI 是同步循环（send_vn_scene → 渲染 → 玩家输入 → 下一场）; webgui 拆成
请求驱动的状态机（与 chat.py 的后台线程 + 轮询模式一致）:

    bond_start    → 构造 BondStoryEngine（复用引擎 llm + director + brain 注入）
                    + 落 vn_enter marker + 首场 seed → 后台生成首场
    bond_turn     → 玩家裁决（选项/自由输入）→ 补录上一场事件（append-only:
                    本场事件在玩家裁决时落库, 带 picked）→ 后台生成下一场
    bond_status   → 轮询: busy / scene / error / completed
    bond_finish   → 补录最后一场（is_end, picked=None）+ vn_exit + session_end
                    + wrapup 收尾（agent_turn 收尾话, 落 mmt 事件）→ async_digest
                    （digest 唯一触发点: bond 闭环）

与 CLI 对齐的语义:
    - 双层收尾兜底（remind/end 系统注记 + 超限强制 closing——剧情必须终结）
    - 纪念子模式（in_memorial → 注入 exit schema; 无生图 → 纯文字, 剧情照走）
    - 失败降级（SceneLoopError → closing 场景落库 + completed, 宁缺勿错）
    - 事件流: bond 事件 {input, picked, ...scene} + memorial/vn_state marker
      （与 CLI 落库格式一致, 回放兼容）

注意: BondStoryEngine 实例在内存（单用户本机, 同 chat.py 引擎管理）;
重启服务丢内存态, 事件流在——中断的 VN 通过 vn_state marker 可重建（M3 回放）。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError
from core.session.events import (
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_VN_EXIT,
    M_VN_STATE,
    make_event,
)
from core.ui.vn_cli import _build_director, _trigger_reason
from webgui import chat

logger = logging.getLogger(__name__)

#: 双层收尾兜底（与 CLI 默认一致——剧情必须终结, 宁缺勿错）
_REMIND_ROUNDS = 30
_END_ROUNDS = 50
#: 超限强制收尾（CLI force_after = end_rounds + 2）
_FORCE_AFTER = _END_ROUNDS + 2
#: 程序兜底 closing 文案（错误收场 / 超限收场）
_CLOSING_TEXT = "（夜色渐深，这一章的羁绊剧情就此落下帷幕。）"


@dataclass
class BondState:
    """一场羁绊剧情的驱动状态（per (char_id, session_id) 内存态）。"""

    vn: BondStoryEngine | None = None
    round: int = 0                      # 已生成场景数（系统注记 / 前端轮询去重）
    busy: bool = False                  # 场景生成中（LLM 秒级, 后台线程）
    scene_obj: BondScene | None = None  # 当前展示场景（运行时对象, 含 memorial 标记）
    scene: dict | None = None           # scene_obj.to_dict()（前端消费）
    scene_input: str = ""               # 生成 scene 用的输入（落库 input 字段）
    scene_logged: bool = True           # scene 是否已落事件流（append-only: 玩家裁决时补录）
    error: str = ""
    completed: bool = False             # 剧情已终结（is_end / 致命错误）→ 前端调 finish
    reason: str = ""


_bonds: dict[tuple[str, str], BondState] = {}


def _state(char_id: str, session_id: str) -> BondState:
    """懒创建 bond 状态（每 (char, session) 一场剧情）。"""
    key = (char_id, session_id)
    if key not in _bonds:
        _bonds[key] = BondState()
    return _bonds[key]


def _store():
    return chat._store


# ---------------------------------------------------------------------------
# 公开 API（路由层调用）
# ---------------------------------------------------------------------------

def bond_start(char_id: str, session_id: str) -> dict:
    """进入羁绊剧情: 构造引擎 + vn_enter marker + 后台生成首场。

    幂等: 已有进行中的 bond 状态 → 返回现状（前端重进不重建）。
    """
    state = _state(char_id, session_id)
    if state.vn is not None:
        return {"accepted": True, "busy": state.busy, "resumed": True}
    if state.busy:
        return {"accepted": False, "busy": True, "error": "正在生成首场"}

    engine = chat._engine(char_id)
    char = engine.current_character
    if char is None:
        return {"accepted": False, "error": "会话未打开"}
    reason = _trigger_reason(engine)

    # brain 注入（DESIGN_BRAIN.md）: 世界线 wiki 第一人称——VN 中角色记得前面的事
    brain_segment = ""
    try:
        from core.brain.hippocampus import WikiStore
        from core.brain.recall import build_brain_injection
        wiki = WikiStore(_store().data_root).load(char.character_id, session_id)
        brain_segment = build_brain_injection(wiki, char_name=char.display_name)
    except Exception:                                # noqa: BLE001 — 注入失败静默跳过
        brain_segment = ""

    vn = BondStoryEngine(
        engine.char_loader.root, engine.llm,
        director=_build_director(char, reason), brain_segment=brain_segment)
    vn.start_session(char.character_id)

    state.vn = vn
    state.reason = reason
    # 事件流: vn_enter marker（单事件流; 中断恢复依赖它推导 in_vn）
    try:
        _store().enter_vn(char_id, session_id, reason)
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断 VN
        logger.warning("事件流 vn_enter 写入失败: %s", e)

    seed = f"（旁白）基于「{reason}」……" if reason else "（旁白）故事开始了……"
    _generate(state, char_id, session_id, seed)
    return {"accepted": True, "busy": True, "resumed": False}


def bond_turn(char_id: str, session_id: str, text: str) -> dict:
    """玩家裁决（选项文本 / 自由输入）→ 补录上一场事件 → 后台生成下一场。"""
    state = _state(char_id, session_id)
    if state.vn is None:
        return {"accepted": False, "error": "剧情未开始"}
    if state.busy:
        return {"accepted": False, "busy": True, "error": "剧情生成中"}
    if state.completed:
        return {"accepted": False, "completed": True, "error": "剧情已结束"}
    text = (text or "").strip()
    if not text:
        return {"accepted": False, "error": "输入不能为空"}

    # append-only 事件流: 当前展示场景在玩家裁决时落库（带 picked）
    _log_scene(state, char_id, session_id, picked=text)
    _generate(state, char_id, session_id, text)
    return {"accepted": True, "busy": True}


def bond_status(char_id: str, session_id: str) -> dict:
    """轮询: 生成状态 + 最新场景（前端按 round 去重）+ 终结标记。"""
    state = _state(char_id, session_id)
    return {
        "busy": state.busy,
        "round": state.round,
        "scene": state.scene,
        "error": state.error,
        "completed": state.completed,
    }


def bond_finish(char_id: str, session_id: str) -> dict:
    """剧情终结收尾: 补录最后场景 + vn_exit + session_end + wrapup + digest。"""
    state = _state(char_id, session_id)
    if state.vn is None:
        return {"completed": False, "error": "剧情未开始"}
    if state.busy:
        return {"completed": False, "busy": True, "error": "剧情生成中"}

    # 最后场景（is_end / closing）: 玩家无裁决 → picked=None
    _log_scene(state, char_id, session_id, picked=None)
    try:
        _store().append_marker(char_id, session_id, M_VN_EXIT)
        _store().finish(char_id, session_id, ended=True)
    except Exception as e:                           # noqa: BLE001 — 收尾写失败降级
        logger.warning("事件流收尾失败: %s", e)
    # 清任务状态（bond_story 标记）——否则 events_after 一直返回 True,
    # 前端 VN 结束后重启轮询会再次误入剧情视图（wrapup 的 mmt 任务随后覆盖）
    chat._tasks.pop((char_id, session_id), None)

    # wrapup 收尾（agent_turn 收尾话 → mmt 事件, 前端轮询拉到）→ async_digest
    # （digest 唯一触发点: bond 闭环——后台线程, 不阻塞响应）
    reason = state.reason
    threading.Thread(target=_wrapup, args=(char_id, session_id, reason),
                     daemon=True).start()
    return {"completed": True}


# ---------------------------------------------------------------------------
# 内部: 生成 / 落库 / 收尾
# ---------------------------------------------------------------------------

def _generate(state: BondState, char_id: str, session_id: str, user_input: str) -> None:
    """后台线程: send_vn_scene 生成下一场 → 更新 state（场景/事件/兜底）。"""
    state.busy = True
    state.error = ""

    def run():
        try:
            with chat._lock(char_id):
                state.round += 1
                scene = state.vn.send_vn_scene(
                    user_input, system_note=_system_note(state))
                if state.round > _FORCE_AFTER and not scene.is_end:
                    # 超限强制收尾（CLI force_after 语义——剧情必须终结）
                    scene = BondScene(
                        paragraphs=[{"text": _CLOSING_TEXT}], is_end=True)
                state.scene_obj = scene
                state.scene = scene.to_dict()
                state.scene_input = user_input
                state.scene_logged = False
                if scene.is_end:
                    state.completed = True
                _log_scene_meta(state, char_id, session_id, scene)
        except (SceneLoopError, ValueError) as e:
            # 模型连语义校验都过不了 → 中断收场（宁缺勿错, 剧情必须终结）
            logger.warning("bond 场景生成失败 (%s/%s): %s", char_id, session_id, e)
            state.error = str(e)
            closing = BondScene(paragraphs=[{"text": _CLOSING_TEXT}], is_end=True)
            state.scene_obj = closing
            state.scene = closing.to_dict()
            state.scene_logged = False
            state.completed = True
        finally:
            state.busy = False

    threading.Thread(target=run, daemon=True).start()


def _log_scene(state: BondState, char_id: str, session_id: str, picked) -> None:
    """补录当前场景事件（append-only: 玩家裁决/收尾时落, 带 picked）。

    与 CLI 落库格式一致: {**scene.to_dict(), "input": 本场输入, "picked": 玩家裁决}
    ——回放兼容（filter_bond → BondScene.from_dict + input/picked）。
    """
    if state.scene_logged or state.scene_obj is None:
        return
    scene = state.scene_obj
    if scene.memorial_exit:
        sub = "memorial_exit"
    elif scene.memorial_prompt:
        sub = "memorial_enter"
    else:
        sub = "story_end" if scene.is_end else "story_scene"
    try:
        _store().append_event(char_id, session_id, make_event(
            "bond", sub,
            {**scene.to_dict(), "input": state.scene_input, "picked": picked}))
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断
        logger.warning("事件流 bond 写入失败: %s", e)
    state.scene_logged = True


def _log_scene_meta(state: BondState, char_id: str, session_id: str,
                    scene: BondScene) -> None:
    """每场 marker 落库: 纪念子模式 + vn_state 恢复点（与 CLI 对齐）。"""
    try:
        if scene.memorial_prompt:
            _store().append_marker(char_id, session_id, M_MEMORIAL_ENTER,
                                   {"reason": state.reason})
        elif scene.memorial_exit:
            _store().append_marker(char_id, session_id, M_MEMORIAL_EXIT)
        vn = state.vn
        visual = vn.director.state.to_dict() if vn.director is not None else {}
        _store().append_marker(char_id, session_id, M_VN_STATE, {
            "round": state.round, "seed": state.scene_input, "visual": visual})
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断
        logger.warning("事件流 marker 写入失败: %s", e)


def _system_note(state: BondState) -> str | None:
    """本轮系统注记（只进 context 不入历史）: 纪念模式 / 收尾提醒 / 上限建议。"""
    vn = state.vn
    if vn.in_memorial:
        return (
            "（系统）当前处于**纪念模式**——纪念场景已结束, 本场请输出"
            " memorial_exit 动作回到 bond（可选过渡文字, 不要输出其他动作）。\n"
            f"可用动作 schema:\n{vn.memorial_exit_schema()}"
        )
    if state.round == _REMIND_ROUNDS:
        return (
            f"（系统）剧情已推进 {state.round} 轮，剩余约 {_END_ROUNDS - state.round} 轮。"
            "请开始把剧情向结尾收束——感情到位、约定达成、道别告别的时刻"
            "就改用 story_end 动作收尾结束剧情，不要再开新场景"
            "不过也谨记这只是中段提示，你并不需要匆匆结尾，但是建议开始铺垫"
        )
    if state.round == _END_ROUNDS:
        return (
            "（系统）已达剧情篇幅上限。本轮请改用 story_end 动作收尾"
            "结束剧情——收尾场景只有 paragraphs，不再输出选项。"
        )
    return None


def _wrapup(char_id: str, session_id: str, reason: str) -> None:
    """剧情【完】后的手机收尾: 自动触发一轮, AI 就这段剧情回几段话 + digest。

    收尾话 = agent_turn（system_note 注入, record_input=False——不落假 player 事件,
    只落 assistant 回复）; 前端轮询 events_after 自然拉到收尾气泡。
    收尾结束后 async_digest（bond 闭环, 提炼 + 好感结算）。
    """
    engine = chat._engine(char_id)
    char = engine.current_character
    if char is None:
        engine.async_digest()
        return
    reason_suffix = f"（起因: {reason}）" if reason else ""
    note = (
        "（系统）羁绊剧情刚刚结束，你们回到了 MomoTalk 手机聊天。"
        f"请以{char.display_name}的身份，就刚才这段羁绊剧情{reason_suffix}，"
        "在手机上回复老师几句话作为收尾——自然、简短、像真实的手机消息。"
        "只使用 mmt_chat 动作，不要再次触发羁绊剧情。"
    )
    try:
        with chat._lock(char_id):
            engine.agent_turn("（自动收尾）", system_note=note, record_input=False)
    except Exception as e:                           # noqa: BLE001 — 收尾失败不阻塞
        logger.warning("羁绊剧情收尾回复失败: %s", e)
    engine.async_digest()                 # 收尾成功与否都消化（bond 已闭环）
