"""羁绊进度系统 — 轮数门槛（对话轮数, 客观计数）。

决策（2026-08-21, 用户确认）:
    - 不用「好感度」概念——它是情绪数值, 暗示角色「喜欢你多少分」,
      每角色初始值不同、会随剧情波动, 很脆。
    - 用「对话轮数」: 与该角色的累计对话轮数（每完成一轮可见回复 +1）,
      客观可数, 每角色天然从 0 起, 不存在初始值差异。
    - 数据落盘 data/basic/bond_progress.json = {char_id: rounds},
      跨会话累计。缺失/损坏降级为空 dict（宁缺勿错, 不崩）。
    - 软门槛（2026-08-21 用户确认）: 轮数只是参考——每轮注入 LLM context
      （「羁绊进度参考」注记）, AI 有最终裁决权, 剧情需要（如老师有急事）可
      提前触发; 程序只在首条消息（0 轮）兜底拒绝。

用法:
    from core.bond_progress import BondProgress
    progress = BondProgress()
    progress.record_turn("igusa_haruka")     # 每完成一轮对话
    progress.rounds("igusa_haruka")          # → 该角色累计轮数
"""

from __future__ import annotations

import json
from pathlib import Path

# 羁绊进度存储（cwd 相对项目根, 与 player.json / SESSION_DIR 同惯例）
DEFAULT_BOND_PROGRESS_PATH = Path("data/basic/bond_progress.json")


class BondProgress:
    """羁绊进度 = 与该角色的累计对话轮数。

    读写 data/basic/bond_progress.json（{char_id: rounds}）。
    缺失/损坏 → 当作空进度（降级不崩）; record_turn 会重建落盘。
    """

    def __init__(self, path: str | Path = DEFAULT_BOND_PROGRESS_PATH):
        self.path = Path(path)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def rounds(self, char_id: str) -> int:
        """该角色累计对话轮数; 缺失/损坏/无记录 → 0。"""
        data = self._load()
        value = data.get(char_id)
        return value if isinstance(value, int) and value >= 0 else 0

    def record_turn(self, char_id: str) -> int:
        """该角色完成一轮对话, 轮数 +1 并落盘。返回更新后的轮数。"""
        data = self._load()
        current = data.get(char_id)
        if not isinstance(current, int) or current < 0:
            current = 0
        data[char_id] = current + 1
        self._save(data)
        return current + 1

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, int]:
        """读 JSON; 缺失/损坏 → {}（宁缺勿错, 不抛错阻塞对话流程）。"""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except ValueError:
            return {}
        if not isinstance(data, dict):
            return {}
        # 只保留合法条目（键=str, 值=非负 int）; 其余静默丢弃
        cleaned: dict[str, int] = {}
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, int) and v >= 0:
                cleaned[k] = v
        return cleaned

    def _save(self, data: dict[str, int]) -> None:
        """写 JSON（父目录自动创建）。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
