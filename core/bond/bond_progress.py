"""羁绊进度系统 — 轮数门槛（对话轮数, 客观计数）。

决策（2026-08-21, 用户确认）:
    - 不用「好感度」概念——它是情绪数值, 暗示角色「喜欢你多少分」,
      每角色初始值不同、会随剧情波动, 很脆。
    - 用「对话轮数」: 与该角色的累计对话轮数（每完成一轮可见回复 +1）,
      客观可数, 每角色天然从 0 起, 不存在初始值差异。
    - 软门槛（2026-08-21 用户确认）: 轮数只是参考——每轮注入 LLM context
      （「羁绊进度参考」注记）, AI 有最终裁决权, 剧情需要（如老师有急事）可
      提前触发; 程序只在首条消息（0 轮）兜底拒绝。

存储（2026-09-02 用户拍板: 合并单文件——每角色一个目录只放一个 progress.json
是目录碎片）:
    data/basic/bond_progress.json = {char_id: {"rounds": N, "updated_at": iso}}
    所有角色一个 json（data/basic 全局数据域: player.json/affection.json 同处）。
    缺失/损坏降级为空进度（宁缺勿错, 不崩）。

迁移链（读取时自动, 幂等）:
    新聚合 → v0 分文件 data/{char_id}/progress.json（一次性: 读入并入聚合后删除
    文件与空目录）→ 旧全局聚合（{char_id: rounds}, 早期格式兜底）。

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

from infra import paths

# 数据根（`infra/paths.py` 的宏——项目根绝对, cwd 无关）
DEFAULT_DATA_ROOT = paths.DATA_DIR
# 旧全局聚合（{char_id: rounds}, 更早期格式兜底——迁移期仍可读）
_LEGACY_GLOBAL_PATH = paths.DATA_DIR / "basic" / "bond_progress.legacy.json"


class BondProgress:
    """羁绊进度 = 与该角色的累计对话轮数（聚合单文件, 2026-09-02 合并）。

    读写 {data_root}/basic/bond_progress.json（{char_id: {rounds, updated_at}}）。
    缺失/损坏 → 当作空进度（降级不崩）; record_turn 会重建落盘。
    构造时自动迁移 v0 分文件（data/{char}/progress.json → 并入聚合, 清空壳目录）。
    """

    def __init__(self, data_root: str | Path | None = None):
        # 注: 默认值**在调用时**解析（不用 DEFAULT_DATA_ROOT 作默认参数——默认参数
        # 在函数定义时就绑定了, 测试/多世界重定向就会失效, 2026-09-11 教训）
        self.data_root = Path(data_root or DEFAULT_DATA_ROOT)
        self._migrated = False

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def rounds(self, char_id: str) -> int:
        """该角色累计对话轮数; 缺失/损坏/无记录 → 0。"""
        self._migrate_v0_if_needed()
        data = self._load_agg()
        entry = data.get(char_id)
        if isinstance(entry, dict):
            rounds = entry.get("rounds")
            if isinstance(rounds, int) and rounds >= 0:
                return rounds
        # 更早期全局聚合兜底（{char_id: rounds}）
        legacy = self._load_legacy()
        value = legacy.get(char_id)
        return value if isinstance(value, int) and value >= 0 else 0

    def record_turn(self, char_id: str) -> int:
        """该角色完成一轮对话, 轮数 +1 并落盘（写聚合文件）。返回更新后的轮数。"""
        self._migrate_v0_if_needed()
        current = self.rounds(char_id)
        self._save_agg(char_id, current + 1)
        return current + 1

    def path(self) -> Path:
        """聚合文件路径（实验/调试/清理用）。"""
        return self._agg_path()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _agg_path(self) -> Path:
        return self.data_root / "basic" / "bond_progress.json"

    def _load_agg(self) -> dict:
        """读聚合 → {char_id: {"rounds", "updated_at"}}; 缺失/损坏 → {}。"""
        path = self._agg_path()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except ValueError:
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict = {}
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, dict):
                rounds = v.get("rounds")
                if isinstance(rounds, int) and rounds >= 0:
                    out[k] = {"rounds": rounds,
                              "updated_at": v.get("updated_at", "")}
        return out

    def _save_agg(self, char_id: str, rounds: int) -> None:
        """整写聚合（原子替换）; 其他角色条目原样保留。"""
        from core.session.io import atomic_write_json

        data = self._load_agg()
        data[char_id] = {"rounds": rounds,
                         "updated_at": datetime.now().isoformat()}
        atomic_write_json(self._agg_path(), data)

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

    # ------------------------------------------------------------------
    # v0 分文件迁移（data/{char_id}/progress.json, 2026-09-02 合并单文件）
    # ------------------------------------------------------------------

    def _migrate_v0_if_needed(self) -> None:
        """幂等迁移: 扫 data_root/*/progress.json → 并入聚合 → 删文件与空目录。

        只扫一层（v0 布局就是角色目录直接放 progress.json）; 无 v0 文件 → 零操作。
        """
        if self._migrated:
            return
        self._migrated = True
        from core.session.io import atomic_write_json

        agg = self._load_agg()
        changed = False
        for d in self.data_root.iterdir():
            if not d.is_dir():
                continue
            f = d / "progress.json"
            if not f.is_file():
                continue
            try:
                raw = f.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            rounds = data.get("rounds")
            if not (isinstance(rounds, int) and rounds >= 0):
                continue
            if char_id := d.name:
                agg[char_id] = {"rounds": rounds,
                                "updated_at": data.get("updated_at", "")}
                changed = True
            try:
                f.unlink()                     # 已并入 → 删分文件
                d.rmdir()                      # 空壳目录一并清（非空则忽略）
            except OSError:
                pass
        if changed:
            atomic_write_json(self._agg_path(), agg)
