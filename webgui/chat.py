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
import random
import threading
from pathlib import Path

from core.momotalk import MomoTalkEngine
from core.session import SessionStore
from core.session.events import make_event
from core.ui.text_processors import _strip_action_brackets, split_reply_chunks
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
# 后台任务状态 + 输入队列（排队连发）: (char_id, session_id) → ...
_tasks: dict[tuple[str, str], dict] = {}
_queues: dict[tuple[str, str], list[str]] = {}
_worker_running: dict[tuple[str, str], bool] = {}


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
    """发起一轮对话（入队, worker 串行消费, 立即返回）。

    排队语义: 玩家连发多条 → 依次入队, worker 逐条跑 agent_turn（同 char 锁串行）;
    后面的 agent_turn 会看到前一条的完整上下文（LLM 综合回复, 见 momotalk_rules
    的"连续消息/插嘴"提示——不必逐条机械回应）。
    Returns: {accepted: bool, queued: bool}
    """
    key = (char_id, session_id)
    _queues.setdefault(key, []).append(text)
    if _worker_running.get(key):
        return {"accepted": True, "queued": True}
    _worker_running[key] = True
    threading.Thread(target=_worker, args=(char_id, session_id), daemon=True).start()
    return {"accepted": True, "queued": False}


def _worker(char_id: str, session_id: str) -> None:
    """worker: 串行消费输入队列（同 char 锁 + 单 worker 保证串行）。

    单个 agent_turn 失败不退出 worker（队列剩余消息继续处理）; 失败时补落
    玩家消息（回复失败也存档玩家的话——重开不丢; reply 空 = 无假回复污染）。
    """
    key = (char_id, session_id)
    try:
        with _lock(char_id):
            while _queues.get(key):
                text = _queues[key].pop(0)
                try:
                    _tasks[key] = {"running": True, "error": ""}
                    engine = _engine(char_id)
                    result = engine.agent_turn(text)
                    # result.bond_story=True → vn_enter marker 已落; M3 阶段前端占位
                    _tasks[key] = {"running": False, "error": "",
                                   "bond_story": bool(result.bond_story)}
                except Exception as e:            # noqa: BLE001 — LLM 失败/循环超限
                    logger.warning("agent_turn 失败 (%s/%s): %s", char_id, session_id, e)
                    _tasks[key] = {"running": False, "error": str(e)}
                    # 补落玩家消息（本轮的 player 事件）——重开聊天窗不丢;
                    # reply 空串 = 没有假回复（存档不被污染）
                    try:
                        _store.append_event(char_id, session_id, make_event(
                            "mmt", "mmt_chat", {"player": text, "reply": ""}))
                    except Exception as e2:       # noqa: BLE001 — 补录失败静默
                        logger.warning("失败消息补录失败 (%s/%s): %s",
                                       char_id, session_id, e2)
    finally:
        _worker_running[key] = False


def task_status(char_id: str, session_id: str) -> dict:
    """查询后台任务状态（前端轮询: busy=还在处理 or 队列有 pending / 出错 / bond）。"""
    key = (char_id, session_id)
    st = dict(_tasks.get(key, {"running": False, "error": ""}))
    st["busy"] = bool(st.get("running")) or bool(_queues.get(key)) \
        or _worker_running.get(key, False)
    return st


# ---------------------------------------------------------------------------
# 事件查询（轮询）
# ---------------------------------------------------------------------------

def render_chat_events(events, display_name: str = "") -> list[dict]:
    """事件流 → 气泡列表 [{kind?, side, text, seq, subtype?}]。

    kind="bond_entry"（入口渲染）: mmt_trigger_bond_story 事件 → BA 风格粉色
    横幅"进入 xx 的羁绊剧情"（display_name 缺失用"羁绊"）。
    其余: 复用 CLI 的文本处理（core/ui/text_processors）——角色回复去动作括号 →
    split_reply_chunks 字数+随机切块（模拟真人一条条发消息）——每个 chunk 一个
    气泡。玩家消息不切（原样）。rng 用事件 seq 作种子（同一条回复每次切块一致,
    历史重放稳定; 不同事件切块不同, 保留"真人节奏"的随机感）。
    """
    bubbles: list[dict] = []
    for e in events:
        if getattr(e, "type", None) != "mmt":
            continue
        if e.subtype == "mmt_trigger_bond_story":
            name = display_name or "羁绊"
            bubbles.append({"kind": "bond_entry",
                            "text": f"进入 {name} 的羁绊剧情", "seq": e.seq})
            continue
        player = (e.payload.get("player") or "").strip()
        reply = (e.payload.get("reply") or "").strip()
        if player:
            bubbles.append({"side": "player", "text": player, "seq": e.seq})
        if reply:
            text = _strip_action_brackets(reply).strip()
            if text:
                rng = random.Random(e.seq)          # 确定性种子（历史重放稳定）
                for chunk in split_reply_chunks(text, rng=rng):
                    bubbles.append({"side": "char", "text": chunk,
                                    "seq": e.seq, "subtype": e.subtype})
    return bubbles


def events_after(char_id: str, session_id: str, since: int = 0,
                 display_name: str = "") -> dict:
    """轮询: seq > since 的 mmt 事件（渲染成气泡）+ 最新 seq + 任务状态。

    since=0 → 全量（打开聊天窗时拉历史）。display_name 供 bond_entry 横幅。
    """
    events = _store.events(char_id, session_id)
    new_events = [e for e in events if e.seq > since]
    status = task_status(char_id, session_id)
    return {
        "bubbles": render_chat_events(new_events, display_name),
        "last_seq": max((e.seq for e in events), default=0),
        "running": bool(status.get("busy")),   # busy = 正在跑 or 队列有 pending
        "error": status.get("error", ""),
        "bond_story": bool(status.get("bond_story")),
    }
