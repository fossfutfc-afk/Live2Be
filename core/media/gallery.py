# -*- coding: utf-8 -*-
"""画廊 — AI 生成 2D 场景（图 + 文字信息成对, DESIGN_SAVE.md §4.5）。

路径（v2）: data/gallery/{char_id}/{scene_id}.png + {scene_id}.json
    —— 立绘是【画作资产】（跨世界保留, 索引 json 标注 source_world/source_session）;
    scene_id = {YYYYMMDD_HHMMSS}_{rand4}

骨架职责（memorial 管线接入前的最小可用面）:
    write(char_id, prompt, source_session, png, description=None) -> scene_id
        复制 png → gallery/{scene_id}.png + 原子写 {scene_id}.json
    list(char_id) -> list[dict]   只认 json+png 都存在的成对（半套 = 中断, 不进）
    get(char_id, scene_id) -> dict | None   {元数据 + png 绝对路径}

写入顺序: 先落 png 再原子写 json——list 只认成对, 半套视为写入中断（可重试）。
原子写复用 core/session/io.atomic_write_json（独立底层, 无依赖方向问题）。
"""

from __future__ import annotations

import json
import random
import shutil
import string
from datetime import datetime
from pathlib import Path

from core.session.io import atomic_write_json

DEFAULT_DATA_ROOT = Path("data")


def _new_scene_id() -> str:
    """角色目录内唯一: {YYYYMMDD_HHMMSS}_{rand4}。"""
    rand4 = "".join(random.choice(string.hexdigits.lower()) for _ in range(4))
    return f"{datetime.now():%Y%m%d_%H%M%S}_{rand4}"


class GalleryStore:
    """画廊存储（路径参数化 data_root, 默认 data/）。"""

    def __init__(self, data_root: str | Path = DEFAULT_DATA_ROOT):
        self.data_root = Path(data_root)

    # ------------------------------------------------------------------
    # 路径（v2: data/gallery/{char_id}/——跨世界资产）
    # ------------------------------------------------------------------

    def gallery_dir(self, char_id: str) -> Path:
        return self.data_root / "gallery" / char_id

    def png_path(self, char_id: str, scene_id: str) -> Path:
        return self.gallery_dir(char_id) / f"{scene_id}.png"

    def meta_path(self, char_id: str, scene_id: str) -> Path:
        return self.gallery_dir(char_id) / f"{scene_id}.json"

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def write(
        self,
        char_id: str,
        prompt: str,
        source_session: str,
        png: str | Path,
        *,
        description: str = "",
        scene_id: str | None = None,
    ) -> str:
        """落一张画廊图（png + json 成对, §4.5 格式）。

        顺序: 先复制 png → {scene_id}.png, 再原子写 {scene_id}.json
        （list 只认成对; 半套 = 中断, 可带 scene_id 重试补全）。返回 scene_id。
        """
        if not prompt or not prompt.strip():
            raise ValueError(f"[gallery.py][GalleryStore][prompt 不能为空]")
        sid = scene_id or _new_scene_id()
        gdir = self.gallery_dir(char_id)
        gdir.mkdir(parents=True, exist_ok=True)

        # 1) png 先落盘（复制失败 → 不写 json, 不成对）
        shutil.copy2(png, self.png_path(char_id, sid))

        # 2) json 原子写（元数据）
        meta: dict = {
            "scene_id": sid,
            "character_id": char_id,
            "prompt": prompt,
            "source_session": source_session,
            "created_at": datetime.now().isoformat(),
        }
        if description:
            meta["description"] = description
        atomic_write_json(self.meta_path(char_id, sid), meta)
        return sid

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------

    def list(self, char_id: str) -> list[dict]:
        """全部成对画廊条目（只认 json+png 都存在; 半套 = 写入中断, 跳过）。

        返回项附带 `png`（绝对路径）。按 scene_id 字典序（≈时间序）。
        """
        gdir = self.gallery_dir(char_id)
        if not gdir.is_dir():
            return []
        out: list[dict] = []
        for p in sorted(gdir.glob("*.json")):
            sid = p.stem
            png = gdir / f"{sid}.png"
            if not png.is_file():
                continue                    # 半套 → 中断, 不进列表
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue                    # 坏 json → 宁缺勿错
            if isinstance(meta, dict):
                meta["png"] = str(png)
                out.append(meta)
        return out

    def get(self, char_id: str, scene_id: str) -> dict | None:
        """读单个条目（成对才返回; 缺失/半套/坏 json → None）。"""
        png = self.png_path(char_id, scene_id)
        meta_p = self.meta_path(char_id, scene_id)
        if not png.is_file() or not meta_p.is_file():
            return None
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(meta, dict):
            return None
        meta["png"] = str(png)
        return meta
