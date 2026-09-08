# -*- coding: utf-8 -*-
"""SessionStore — 世界（周目）顶层 + 角色线存储（v2, docs/world_model_evolution.md）。

**v2 路径（平行世界顶层, 世界上限 WORLD_LIMIT 个槽位）**:
    data/worlds/{world_id}/world.json                      （世界 meta: created_at/active）
    data/worlds/{world_id}/characters/{char_id}/events.jsonl（角色线事件流, 唯一真源）
    data/worlds/{world_id}/characters/{char_id}/wiki.json   （digest 产物, brain 派生）
    data/worlds/{world_id}/characters/{char_id}/meta.json   （线状态: 轮数等）
    data/worlds/{world_id}/snapshots/s_xxx/…                （存档点 = 森林时点快照, 未来）

**与 v1 的关系（渐进迁移）**: 类名 SessionStore 与方法签名（char_id, session_id）
保留——调用方零改动; session_id 语义 = 世界内角色线 id, **不再参与路径**
（每角色一条事件流直接挂角色目录）。v1 旧数据已归档 data/archive/。

**世界管理**: 槽位 world1/world2/world3（固定编号, created_at 记录真实时间）;
创建第三个之后拒绝新建（数据安全优先, 玩家手动删/归档）。active 标记在
world.json——切换器（M2）读它; 默认 active_world() = world1（或唯一存在的世界）。

seq 分配: 每次 append 从文件重算 max **且持进程级全局写锁**（2026-09-08 修复:
锁若挂实例上, 多实例各持一把仍会撞重复——生产路径存在 chat 单例与 routers/mmt
每请求实例两个 SessionStore, 实测修复后仍现重复 seq）。全局锁覆盖同进程一切
写者（单实例运行前提; 多进程同写仍会重复——务必单实例）。

状态: 无状态机——ended/in_vn 由 events 的 marker 推导（renderer.session_status）。
"""

from __future__ import annotations

import json
import random
import string
import threading
from datetime import datetime
from pathlib import Path

from core.session.events import (
    M_SESSION_END,
    M_SESSION_START,
    M_VN_ENTER,
    Event,
    make_event,
    marker,
    parse_events,
)
from core.session.io import append_jsonl, atomic_write_json, read_jsonl
from core.session.models import TYPE_CONVERSATION, SessionMeta
from core.session.renderer import session_status

#: 数据根（项目根绝对, cwd 无关——uvicorn/IDE 从任意目录启动）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_ROOT = _PROJECT_ROOT / "data"

#: 平行世界上限（槽位数）
WORLD_LIMIT = 3

#: 默认世界（active_world 兜底）
DEFAULT_WORLD = "world1"

#: events.jsonl 写锁（进程级全局, 2026-09-08）: seq 计算+写行原子化——
#: 挂实例上会因多实例各持一把而失效（chat 单例 vs routers/mmt 每请求实例）
_GLOBAL_APPEND_LOCK = threading.Lock()


def _new_line_id() -> str:
    """角色线 id（v2: 每世界每角色一条线——保留时间戳风格, 兼容 v1 工具/测试）。"""
    rand4 = "".join(random.choice(string.hexdigits.lower()) for _ in range(4))
    return f"{datetime.now():%Y%m%d_%H%M%S}_{rand4}"


class SessionStore:
    """世界（周目）+ 角色线存储管理器（路径参数化 data_root, 默认 data/）。"""

    def __init__(self, data_root: str | Path = DEFAULT_DATA_ROOT,
                 world_id: str | None = None):
        self.data_root = Path(data_root)
        self.world_id = world_id or DEFAULT_WORLD  # 当前世界槽位（调用方可覆盖）

    # ------------------------------------------------------------------
    # 路径（v2: worlds/{world}/characters/{char}/…）
    # ------------------------------------------------------------------

    def worlds_root(self) -> Path:
        return self.data_root / "worlds"

    def world_dir(self, world_id: str | None = None) -> Path:
        return self.worlds_root() / (world_id or self.world_id)

    def world_meta_path(self, world_id: str | None = None) -> Path:
        return self.world_dir(world_id) / "world.json"

    def characters_dir(self, world_id: str | None = None) -> Path:
        return self.world_dir(world_id) / "characters"

    def char_dir(self, char_id: str, world_id: str | None = None) -> Path:
        return self.characters_dir(world_id) / char_id

    # v1 兼容路径方法（session_id 不再参与路径——每角色一条线）
    def sessions_dir(self, char_id: str) -> Path:
        return self.char_dir(char_id)

    def session_dir(self, char_id: str, session_id: str = "") -> Path:
        return self.char_dir(char_id)

    def meta_path(self, char_id: str, session_id: str = "") -> Path:
        return self.char_dir(char_id) / "meta.json"

    def events_path(self, char_id: str, session_id: str = "") -> Path:
        # soul/ = 记忆层（2026-09-04 拍板: events 原材料与 wiki 成品同居——
        # digest 读 events 写 wiki, 重算自包含; 写时父目录自动 mkdir）
        return self.char_dir(char_id) / "soul" / "events.jsonl"

    def progress_path(self, char_id: str, session_id: str = "") -> Path:
        return self.char_dir(char_id) / "progress.json"

    def snapshots_dir(self, world_id: str | None = None) -> Path:
        """存档点目录（v2: 森林时点快照, 阶段 8/10——全量复制, 节点自包含）。"""
        return self.world_dir(world_id) / "snapshots"

    # ------------------------------------------------------------------
    # 世界管理（周目, 上限 WORLD_LIMIT）
    # ------------------------------------------------------------------

    def list_worlds(self) -> list[str]:
        """枚举已有世界槽位（worlds/ 下含 world.json 的目录, 按槽位序）。"""
        root = self.worlds_root()
        if not root.is_dir():
            return []
        return sorted(
            (p.name for p in root.iterdir()
             if p.is_dir() and (p / "world.json").is_file()))

    def world_meta(self, world_id: str | None = None) -> dict:
        """读世界 meta（缺失 → {id, created_at: '', active: False}, 宁缺勿错）。"""
        p = self.world_meta_path(world_id)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            pass
        return {"id": world_id or self.world_id, "created_at": "", "active": False}

    def create_world(self, name: str = "") -> str:
        """新建平行世界（槽位 world1..world{N}, 上限 WORLD_LIMIT——满了拒绝）。

        槽位编号: 找最小可用空位（world1 优先）; created_at 记录真实创建时间。
        active 标记: 新世界默认非 active（切换由 M2 世界切换器负责）。
        """
        root = self.worlds_root()
        root.mkdir(parents=True, exist_ok=True)
        existing = {p.name for p in root.iterdir() if p.is_dir()}
        for i in range(1, WORLD_LIMIT + 1):
            wid = f"world{i}"
            if wid not in existing:
                meta = {
                    "id": wid,
                    "name": name,
                    "created_at": datetime.now().isoformat(),
                    "active": False,
                }
                d = root / wid
                d.mkdir(parents=True, exist_ok=True)
                (d / "characters").mkdir(exist_ok=True)
                atomic_write_json(self.world_meta_path(wid), meta)
                return wid
        raise RuntimeError(
            f"平行世界上限 {WORLD_LIMIT} 个已满——请先归档/删除一个世界再新建"
        )

    def active_world(self) -> str:
        """当前活跃世界（world.json active=True; 无 → 唯一世界; 无世界 → world1）。"""
        worlds = self.list_worlds()
        if not worlds:
            return DEFAULT_WORLD
        for wid in worlds:
            if self.world_meta(wid).get("active"):
                return wid
        return worlds[0]

    # ------------------------------------------------------------------
    # 角色线生命周期（方法签名保留 v1——session_id 不再参与路径）
    # ------------------------------------------------------------------

    def create(self, char_id: str, char_name: str = "") -> SessionMeta:
        """新建角色线（v2: 懒创建——世界/角色目录 + meta.json + session_start marker）。

        每世界每角色一条线——重复调用返回同一线（不建新目录, 事件流持续 append）。
        """
        d = self.char_dir(char_id)
        d.mkdir(parents=True, exist_ok=True)
        meta_path = self.meta_path(char_id)
        if meta_path.is_file():
            meta = SessionMeta.from_dict(self._read_json(meta_path))
            if meta.session_id:
                return meta
        line_id = _new_line_id()
        meta = SessionMeta(
            session_id=line_id,
            type=TYPE_CONVERSATION,
            character_id=char_id,
            character_name=char_name,
            created_at=datetime.now().isoformat(),
        )
        atomic_write_json(meta_path, meta.to_dict())
        self.append_marker(char_id, line_id, M_SESSION_START)
        return meta

    def enter_vn(self, char_id: str, session_id: str = "", title: str = "") -> str:
        """MMT → VN: 角色线 append vn_enter marker（单事件流, 无子会话）。

        title = 本章标题（trigger 的 chapter_title——2026-09-05 reason 退役;
        事件流持久化, 回放/章节列表消费; 旧事件 reason 键残留不读）。
        """
        payload = {"chapter_title": title} if title else None
        self.append_marker(char_id, session_id, M_VN_ENTER, payload)
        return session_id

    def finish(self, char_id: str, session_id: str = "", ended: bool = True) -> Event:
        """对话段收尾: append marker session_end{ended}（没写 = 中断, 零成本表达）。"""
        return self.append_marker(char_id, session_id, M_SESSION_END, {"ended": ended})

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def append_event(self, char_id: str, session_id: str = "", event: Event | None = None,
                     **kwargs) -> Event:
        """append 一个事件（seq 每次从文件重算 max——写锁内原子, 见模块 docstring）。"""
        if event is None:
            event = make_event(kwargs.pop("type", "mmt"), kwargs.pop("subtype", "mmt_chat"),
                               kwargs.pop("payload", {}))
        with _GLOBAL_APPEND_LOCK:               # 进程级: 跨实例也原子（见模块 docstring）
            evs = parse_events(read_jsonl(self.events_path(char_id, session_id)))
            seq = max((e.seq for e in evs), default=0) + 1
            ev = Event(
                seq=seq,
                ts=event.ts or datetime.now().isoformat(),
                type=event.type,
                subtype=event.subtype,
                payload=dict(event.payload),
            )
            p = self.events_path(char_id, session_id)
            p.parent.mkdir(parents=True, exist_ok=True)
            append_jsonl(p, ev.to_dict())
        return ev

    def append_marker(
        self, char_id: str, session_id: str = "", subtype: str = "",
        payload: dict | None = None,
    ) -> Event:
        """append 一个 marker 事件（状态标记）。"""
        return self.append_event(char_id, session_id, marker(subtype, payload))

    def update_session_progress(self, char_id: str, session_id: str = "", rounds: int = 0) -> None:
        """[废弃] 写角色线轮数——旧语义（最近会话轮数, 覆盖写, 无人读）。
        2026-09-02 起由 write_bond_gap 接管（决策字段 = 距上次完整 bond 剧情的
        MMT 轮数）。保留方法体 = 迁移写 rounds_since_bond（调用方已切新 API）。"""
        self.write_bond_gap(char_id, rounds)

    # ------------------------------------------------------------------
    # 距上次 bond 剧情的 MMT 轮数（2026-09-02 决策字段, 用户拍板）
    # ------------------------------------------------------------------

    def write_bond_gap(self, char_id: str, rounds: int = 0) -> None:
        """写角色线 progress.json: {rounds_since_bond, updated_at}。

        rounds_since_bond = 距上次**完整** bond 剧情（vn_exit completed=True）
        的 MMT 轮数——羁绊触发门槛 + 剧情后冷却的一体计数器（持久化,
        断线/重启继续累计; bond 完整结束清零）。
        """
        p = self.progress_path(char_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(p, {
            "rounds_since_bond": max(0, int(rounds)),
            "updated_at": datetime.now().isoformat(),
        })

    def read_bond_gap(self, char_id: str) -> int:
        """读角色线 progress.json 的 rounds_since_bond。

        旧版文件（仅 rounds 键, 最近会话轮数, 死数据）→ 视为 0（2026-09-02
        用户拍板: 旧值作废, 新语义从零起算——宁缺勿错）; 缺失/损坏 → 0。
        """
        data = self._read_json(self.progress_path(char_id))
        if not isinstance(data, dict):
            return 0
        raw = data.get("rounds_since_bond")
        if isinstance(raw, (int, float)):
            return max(0, int(raw))
        return 0

    # ------------------------------------------------------------------
    # 读路径
    # ------------------------------------------------------------------

    def meta(self, char_id: str, session_id: str = "") -> SessionMeta:
        """读角色线 meta.json（缺失 → 空 SessionMeta, 宁缺勿错）。"""
        return SessionMeta.from_dict(self._read_json(self.meta_path(char_id, session_id)))

    def events(self, char_id: str, session_id: str = "") -> list[Event]:
        """读角色线 events.jsonl（行级容错, 坏骨架事件丢弃）。"""
        return parse_events(read_jsonl(self.events_path(char_id, session_id)))

    def resume(self, char_id: str, session_id: str = "") -> dict:
        """恢复读路径: {meta, events, status}（调用方用 render_events + session_status 重建）。"""
        evs = self.events(char_id, session_id)
        return {
            "meta": self.meta(char_id, session_id),
            "events": evs,
            "status": session_status(evs),
        }

    def list_open(self) -> list[SessionMeta]:
        """列出当前世界全部未结束角色线（无 session_end marker, 按 created_at 倒序）。"""
        out: list[SessionMeta] = []
        chars = self.characters_dir()
        if not chars.is_dir():
            return []
        for meta_path in sorted(chars.glob("*/meta.json")):
            meta = SessionMeta.from_dict(self._read_json(meta_path))
            if not meta.session_id:
                continue
            char_id = meta.character_id
            status = session_status(
                parse_events(read_jsonl(self.events_path(char_id, meta.session_id))))
            if not status["ended"]:
                out.append(meta)
        out.sort(key=lambda m: m.created_at, reverse=True)
        return out

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _read_json(self, path: Path) -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}
