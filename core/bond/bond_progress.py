"""羁绊进度系统 — 轮数门槛（对话轮数, 客观计数）。

决策（2026-08-21, 用户确认）:
    - 不用「好感度」概念——它是情绪数值, 暗示角色「喜欢你多少分」,
      每角色初始值不同、会随剧情波动, 很脆。
    - 用「对话轮数」: 与该角色的累计对话轮数（每完成一轮可见回复 +1）,
      客观可数, 每角色天然从 0 起, 不存在初始值差异。
    - 数据落盘 data/{char_id}/progress.json = {"rounds": N, "updated_at": …},
      按角色分文件（DESIGN_SAVE.md §三, 2026-08-23 布局升级）。
      缺失/损坏降级为空进度（宁缺勿错, 不崩）。
    - 软门槛（2026-08-21 用户确认）: 轮数只是参考——每轮注入 LLM context
      （「羁绊进度参考」注记）, AI 有最终裁决权, 剧情需要（如老师有急事）可
      提前触发; 程序只在首条消息（0 轮）兜底拒绝。

迁移: 旧全局聚合 data/basic/bond_progress.json（{char_id: rounds}, 已归档
    bond_progress.legacy.json）——rounds() 读不到角色文件时回退旧全局（一次性）,
    record_turn 写角色文件后自然完成迁移。

用法:
    from core.bond.bond_progress import BondProgress
    progress = BondProgress()
    progress.record_turn("igusa_haruka")     # 每完成一轮对话
    progress.rounds("igusa_haruka")          # → 该角色累计轮数
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# 数据根（cwd 相对项目根, 与 player.json 同惯例; 角色目录 = data/{char_id}/）
DEFAULT_DATA_ROOT = Path("data")
# 旧全局聚合（迁移期回退; 已归档 .legacy.json 仍可读）
_LEGACY_GLOBAL_PATH = Path("data/basic/bond_progress.json")


class BondProgress:
    """羁绊进度 = 与该角色的累计对话轮数（按角色分文件）。

    读写 data/{char_id}/progress.json（{"rounds": N, "updated_at": iso}）。
    缺失/损坏 → 当作空进度（降级不崩）; record_turn 会重建落盘。
    rounds() 查不到角色文件 → 回退旧全局聚合（迁移期兼容）。
    """

    def __init__(self, data_root: str | Path = DEFAULT_DATA_ROOT):
        self.data_root = Path(data_root)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def rounds(self, char_id: str) -> int:
        """该角色累计对话轮数; 缺失/损坏/无记录 → 0。"""
        data = self._load_char(char_id)
        if data is not None:
            return data.get("rounds", 0)
        # 迁移期回退: 角色文件不存在 → 旧全局聚合（data/basic/bond_progress.json）
        legacy = self._load_legacy()
        value = legacy.get(char_id)
        return value if isinstance(value, int) and value >= 0 else 0

    def record_turn(self, char_id: str) -> int:
        """该角色完成一轮对话, 轮数 +1 并落盘（写角色文件）。返回更新后的轮数。"""
        current = self.rounds(char_id)
        self._save_char(char_id, current + 1)
        return current + 1

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _char_path(self, char_id: str) -> Path:
        return self.data_root / char_id / "progress.json"

    def _load_char(self, char_id: str) -> dict | None:
        """读角色 progress.json → {"rounds", "updated_at"}; 缺失/损坏 → None。"""
        path = self._char_path(char_id)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        rounds = data.get("rounds")
        if not isinstance(rounds, int) or rounds < 0:
            return None
        return {"rounds": rounds, "updated_at": data.get("updated_at", "")}

    def _load_legacy(self) -> dict[str, int]:
        """旧全局聚合（{char_id: rounds}）; 缺失/损坏 → {}（宁缺勿错）。"""
        try:
            raw = _LEGACY_GLOBAL_PATH.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except ValueError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items()
                if isinstance(k, str) and isinstance(v, int) and v >= 0}

    def _save_char(self, char_id: str, rounds: int) -> None:
        """写角色 progress.json（父目录自动创建, 原子替换）。"""
        from core.session.io import atomic_write_json

        path = self._char_path(char_id)
        atomic_write_json(path, {
            "rounds": rounds,
            "updated_at": datetime.now().isoformat(),
        })
