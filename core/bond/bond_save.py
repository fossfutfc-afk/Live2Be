"""羁绊剧情存档 — 逐场原子写 + 读档容错 + 列出可用存档。

存档是 JSON 契约化的副产物（DESIGN_BOND_STORY.md）:
    运行时每个 story_scene 场景解析后 append 进 scenes[], 连同本场景的
    输入（input）与玩家裁决（picked）一起落盘; 回放时同一份 scenes[] 被
    BondScene.from_dict 逐条解析渲染——**一解析器两用**。

设计:
    - 路径 data/saves/bond_story_{char_id}_{YYYY-MM-DD_HHMMSS}.json（沿用 sessions 命名）
    - **逐场 append + 原子写**（tempfile 同目录 + os.replace）——中途崩溃也保留下半段
    - finish(ended) 标收尾状态: 【完】/程序兜底 = ended true; b 提前退出 = ended false
    - 读档宁缺勿错: 坏文件/非 dict → {} 不 raise; scenes 只留 dict 项
    - 写失败不抛给调用方（VN 主循环 try 包裹, 降级为不记录）

用法:
    from core.bond.bond_save import BondStorySave, load_save, list_saves
    rec = BondStorySave(char_id, char_name, reason)
    rec.append(scene, picked="选项A", input_text="（旁白）……")
    rec.finish(ended=True)
    data = load_save(rec.path)
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from core.bond.bond_story import BondScene

DEFAULT_SAVE_DIR = Path("data/saves")


def _atomic_write_json(path: Path, data: dict) -> None:
    """原子写 JSON: temp 与目标同目录 → os.replace（Windows 同卷原子替换）。

    单写者假设; 异常清理 tmp 后 re-raise。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="._savetmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class BondStorySave:
    """一个羁绊剧情会话的存档记录器（逐场 append + 原子写）。"""

    def __init__(
        self,
        character_id: str,
        character_name: str = "",
        trigger_reason: str = "",
        save_dir: str | Path = DEFAULT_SAVE_DIR,
    ):
        self.character_id = character_id
        self._character_name = character_name
        self.path = Path(save_dir) / (
            f"bond_story_{character_id}_"
            f"{datetime.now():%Y-%m-%d_%H%M%S}.json"
        )
        self._started_at = datetime.now().isoformat()
        self._trigger_reason = trigger_reason
        self._records: list[dict] = []
        self._ended = False
        self._flush()                      # 构造即写骨架（崩溃也留痕）

    def append(self, scene: BondScene, picked: str | None, input_text: str) -> None:
        """记一场（picked = 玩家裁决: 选项文本 / 自由输入 / None）。

        视觉字段（导演层 background/audio）与意图字段（beats/place）一并落盘,
        回放可还原视觉/意图标签; 纯文本模式（None/空）→ 落 null/空, 与旧档兼容。
        """
        record = {
            "seq": len(self._records) + 1,
            "input": input_text,
            "paragraphs": list(scene.paragraphs),
            "choices": list(scene.choices),
            "picked": picked,
            "is_end": bool(scene.is_end),
            "background": scene.background,
            "audio": scene.audio,
        }
        if scene.beats:
            record["beats"] = [dict(b) for b in scene.beats]
        if scene.place is not None:
            record["place"] = scene.place
        self._records.append(record)
        self._flush()

    def finish(self, ended: bool = True) -> None:
        """标收尾状态（【完】/兜底 = True; b 提前退出 = False）。"""
        self._ended = bool(ended)
        self._flush()

    def _flush(self) -> None:
        _atomic_write_json(self.path, {
            "character_id": self.character_id,
            "character_name": self._character_name,
            "started_at": self._started_at,
            "trigger_reason": self._trigger_reason,
            "ended": self._ended,
            "scenes": self._records,
        })


def load_save(path: str | Path) -> dict:
    """读档（宁缺勿错: 坏文件/非 dict → {} 不 raise）。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    data["scenes"] = [r for r in data.get("scenes", []) if isinstance(r, dict)]
    return data


def list_saves(char_id: str | None = None, save_dir: str | Path = DEFAULT_SAVE_DIR) -> list[Path]:
    """列出可用存档（按文件名排序; char_id 过滤）。"""
    pattern = f"bond_story_{char_id}_*.json" if char_id else "bond_story_*.json"
    return sorted(Path(save_dir).glob(pattern))
