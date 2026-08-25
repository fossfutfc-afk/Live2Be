# -*- coding: utf-8 -*-
"""MMT 聊天域 — 引擎管理 + 会话生命周期 + 后台任务 + 事件查询。

设计（core/DESIGN_MMT_CHAT.md）:
  - 每 char 一个独立引擎实例（并行多角色: 不同 char 各自线程跑 agent_turn,
    互不干扰; 同 char 串行锁防并发）——切换角色不取消后台任务, 回复落事件流,
    前端切回拉取补全。
  - agent_turn 在后台线程跑（真实 LLM 秒级耗时）, 结果由引擎落事件流
    （events.jsonl 唯一真源）, 前端轮询 events_after 拉新气泡。
  - 会话: 有进行中（未结束）会话 → resume（含 brain digest 注入世界线记忆）;
    无 → 新开世界线（平行世界语义, 见 DESIGN_WORLD.md）。

注意: 引擎实例在内存（单用户本机）; 重启服务丢内存状态但事件流在,
     重新 open_session = resume 重建。
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from core.momotalk import MomoTalkEngine
from core.session import SessionStore
from llm.client import LLMClient

logger = logging.getLogger(__name__)

# 项目根绝对路径（cwd 无关——uvicorn 从任意目录启动）
ROOT = Path(__file__).resolve().parent.parent
CHAR_ROOT = ROOT / "config" / "characters"
DATA_ROOT = ROOT / "data"
INTERPERSON_PATH = ROOT / "config" / "settings" / "relation" / "interperson.json"

# ---------------------------------------------------------------------------
# 引擎管理（每 char 独立实例 + 同 char 串行锁）
# ---------------------------------------------------------------------------

_store = SessionStore(DATA_ROOT)
_engines: dict[str, MomoTalkEngine] = {}
_locks: dict[str, threading.Lock] = {}
# 后台任务状态: (char_id, session_id) → {"running": bool, "error": str}
_tasks: dict[tuple[str, str], dict] = {}


def _engine(char_id: str) -> MomoTalkEngine:
    """某角色的引擎实例（懒创建, 每 char 独立——并行多角色的基础）。"""
    if char_id not in _engines:
        _engines[char_id] = MomoTalkEngine(
            CHAR_ROOT,
            LLMClient(),
            interperson_path=INTERPERSON_PATH,
            store=_store,
        )
    return _engines[char_id]


def _lock(char_id: str) -> threading.Lock:
    """同 char 串行锁（防同一角色双标签页并发 / 等待中重复发送）。"""
    if char_id not in _locks:
        _locks[char_id] = threading.Lock()
    return _locks[char_id]


# ---------------------------------------------------------------------------
# 会话生命周期
# ---------------------------------------------------------------------------

def open_session(char_id: str) -> dict:
    """打开某角色的会话: 有进行中 → resume; 无 → 新开世界线。

    Returns: {session_id, display_name, new: bool, in_vn: bool}
    """
    engine = _engine(char_id)
    # 找进行中会话（list_open 按 created_at 倒序, 取最近）
    open_meta = next(
        (m for m in _store.list_open() if m.character_id == char_id), None)
    if open_meta is not None:
        res = engine.resume_session(char_id, open_meta.session_id)  # 含 brain digest
        return {
            "session_id": open_meta.session_id,
            "display_name": res["display_name"],
            "new": False,
            "in_vn": res["status"].get("in_vn", False),
        }
    # 新世界线
    meta = _store.create(char_id)
    display_name = engine.start_session(char_id)
    engine.attach_session(meta.session_id)
    return {
        "session_id": meta.session_id,
        "display_name": display_name,
        "new": True,
        "in_vn": False,
    }


def new_world(char_id: str) -> dict:
    """显式开新世界线（平行世界语义: 旧线保留, 新线从零开始）。"""
    engine = _engine(char_id)
    meta = _store.create(char_id)
    display_name = engine.start_session(char_id)
    engine.attach_session(meta.session_id)
    return {"session_id": meta.session_id, "display_name": display_name, "new": True}


# ---------------------------------------------------------------------------
# 后台任务（agent_turn 线程）
# ---------------------------------------------------------------------------

def chat_async(char_id: str, session_id: str, text: str) -> dict:
    """发起一轮对话（后台线程跑 agent_turn, 立即返回）。

    同 char 串行锁: 若该角色正在回复中 → 拒绝（前端也应禁用输入）。
    Returns: {accepted: bool, reason?: str}
    """
    key = (char_id, session_id)
    if _tasks.get(key, {}).get("running"):
        return {"accepted": False, "reason": "正在回复中"}
    _tasks[key] = {"running": True, "error": ""}
    threading.Thread(
        target=_run_turn, args=(char_id, session_id, text), daemon=True,
    ).start()
    return {"accepted": True}


def _run_turn(char_id: str, session_id: str, text: str) -> None:
    """后台: agent_turn（锁内串行）→ 落事件流（引擎自动）→ 更新任务状态。"""
    key = (char_id, session_id)
    try:
        with _lock(char_id):
            engine = _engine(char_id)
            result = engine.agent_turn(text)
            # result.bond_story=True → vn_enter marker 已落（executor）; M3 阶段
            # 前端占位, 这里只标记（in_vn 状态由事件流 session_status 推导）
            _tasks[key] = {"running": False, "error": "",
                           "bond_story": bool(result.bond_story)}
    except Exception as e:                        # noqa: BLE001 — LLM 失败/循环超限
        logger.warning("agent_turn 失败 (%s/%s): %s", char_id, session_id, e)
        _tasks[key] = {"running": False, "error": str(e)}


def task_status(char_id: str, session_id: str) -> dict:
    """查询后台任务状态（前端轮询: 是否还在回复 / 是否出错 / 是否触发 bond）。"""
    return _tasks.get((char_id, session_id), {"running": False, "error": ""})


# ---------------------------------------------------------------------------
# 事件查询（轮询）
# ---------------------------------------------------------------------------

def render_chat_events(events) -> list[dict]:
    """事件流 → 气泡列表 [{side: player|char, text, seq, type?}]。

    mmt 事件 payload: player（同轮首条, 玩家消息）+ reply（角色回复）。
    一个事件可能同时有 player 和 reply（同轮）→ 各成一气泡。
    """
    bubbles: list[dict] = []
    for e in events:
        if getattr(e, "type", None) != "mmt":
            continue
        player = (e.payload.get("player") or "").strip()
        reply = (e.payload.get("reply") or "").strip()
        if player:
            bubbles.append({"side": "player", "text": player, "seq": e.seq})
        if reply:
            bubbles.append({"side": "char", "text": reply, "seq": e.seq,
                            "subtype": e.subtype})
    return bubbles


def events_after(char_id: str, session_id: str, since: int = 0) -> dict:
    """轮询: seq > since 的 mmt 事件（渲染成气泡）+ 最新 seq + 任务状态。

    since=0 → 全量（打开聊天窗时拉历史）。
    """
    events = _store.events(char_id, session_id)
    new_events = [e for e in events if e.seq > since]
    status = task_status(char_id, session_id)
    return {
        "bubbles": render_chat_events(new_events),
        "last_seq": max((e.seq for e in events), default=0),
        "running": bool(status.get("running")),
        "error": status.get("error", ""),
        "bond_story": bool(status.get("bond_story")),
    }
