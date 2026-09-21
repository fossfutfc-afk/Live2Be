# -*- coding: utf-8 -*-
"""MediaCatalog — assets/ 媒体查库总入口（纯数据, 背景全量 + 差分按角色懒加载）。

查询（宁缺勿错: 未知 id / 缺资产 → None / 空列表, 不抛异常; 仅构造时 assets 根缺失抛 MediaError）:
    background(scene_id, variant=None)  → 背景（命名派生, 变体白名单切分）
    sprite(char_id, emotion)            → 差分（manifest 情绪白名单 + 可选 spine 导出）
    sprite_emotions / background_scenes / background_variants / has_*  → 供 ② 导演/播放协议校验

## 目录组织（2026-09-19, PL0）

背景**递归**扫描, 且**剪掉点/下划线开头的目录**（`.thumbs/` 缩略图缓存、
`__pycache__`、作者预留的 `_unused/` —— 见 `_iter_background_images` 的 docstring）。
现行 `BG_*/BG_*.jpg` 与工作区导出的 `SDIR_*/DIR_*/BG_*.jpg` 两级布局**都支持** ——
scene_id 由**文件名**派生, 与目录层级无关（用户同步的是 `SDIR`/`DIR` + 地点表）。

⚠️ **`background_dirs()` / `background_scenes_in_dir()` 已删**（2026-09-19）:
它们是"② 导演背景分层选目录"时代的 API, **零消费方**, 且目录名换组织后本就失效 ——
留着就成了**说谎的接口**（"有哪些目录"答出 `SDIR_*`, 调用方以为拿到 `BG_*`）。
需要"某目录下有哪些 scene"用 `background_scenes()` 自行过滤。

架构: 背景=命名派生（零 manifest）; 差分=manifest 映射（情绪白名单真源）。
详见 docs/DESIGN_VISUAL.md §5-①。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from core import paths
from core.common.errors import Live2BeError
from core.media.background import BackgroundMedia, derive_background
from core.media.manifest import load_character_manifest
from core.media.sprites import SpriteMedia, find_spine_packs

# assets/ 默认根（`core/paths.py` 的宏）
_DEFAULT_ASSETS = paths.ASSETS_DIR

# 背景变体后缀（.py 等脚本残留自动排除）
_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

#: 遍历背景资产时**跳过的目录名前缀**（点 = 工具缓存如 `.thumbs/`;
#: 下划线 = `__pycache__` 与作者预留的 `_unused/`）
_SKIP_DIR_PREFIX = (".", "_")


def _iter_background_images(bg_root: Path) -> Iterator[Path]:
    """背景图全集（递归; **剪掉点/下划线开头的目录**）。

    为什么不用 `rglob("*")`（2026-09-19, PL0）:
    * `assets/background/.thumbs/` 是工作台（`place_studio.py`）的缩略图缓存 ——
      **239 张 480px JPEG 曾经全部进了 `background_scenes()`**
      （真图 1094 + 缩略图 239 = 1333）。今天没出事只是因为"同 scene 的首选图恰好先被
      扫到"——**顺序偶然, 不是设计**。
    * `__pycache__` 同理（当前没图, 但没理由靠这个）。
    * 下划线开头还留给作者: `DESIGN_PLACE §4` 的 `_unused/`（"确定用不到的"）——
      那些**不该进活跃索引**。当前无 `_` 开头的资产目录（除 `__pycache__`）。

    ## 目录组织

    既支持现在的 `BG_*/BG_*.jpg`, 也支持工作区导出的 **`SDIR_*/DIR_*/BG_*.jpg`**
    （用户 2026-09-19: tempo 是"带实体的 development 分支", 他同步 `SDIR`/`DIR` + 表
    进来）。**文件名不变 ⇒ `derive_background()` 结果不变 ⇒ 查库天然不受影响**,
    这里只负责"递归 + 剪枝"。
    """
    for dirpath, dirnames, filenames in os.walk(bg_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(_SKIP_DIR_PREFIX)]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in _IMAGE_EXTS:
                yield p



class MediaError(Live2BeError):
    """媒体查库构造错误（assets 根缺失等）。查询层不抛, 全部降级 None。"""


class MediaCatalog:
    """一次扫描 assets/ 建索引的纯数据查库。构造慢（~百 ms）但查询全 O(1)。"""

    def __init__(self, assets_root: Path | str | None = None) -> None:
        self.assets_root = Path(assets_root) if assets_root else _DEFAULT_ASSETS
        if not self.assets_root.is_dir():
            raise MediaError(f"assets 根不存在: {self.assets_root}")
        self._backgrounds: dict[str, list[BackgroundMedia]] = {}
        self._sprites: dict[tuple[str, str], dict[str, SpriteMedia]] = {}
        self._scanned_chars: set[tuple[str, str]] = set()
        # 背景全量（构造时）: 数据驱动必须扫才能知道有哪些场景, 且便宜（620 场景）;
        # 差分按角色×外观懒加载（VN 单角色, 首次 query 才扫该外观并缓存, 宁缺勿错）.
        self._scan_backgrounds()

    # ------------------------------------------------------------------
    # 查询: 背景
    # ------------------------------------------------------------------

    def background(self, scene_id: str, variant: str | None = None) -> BackgroundMedia | None:
        """查背景。variant 指定时刻（night/sunset/...）; None → 默认无变体版本优先, 无则任取。"""
        entries = self._backgrounds.get(scene_id)
        if not entries:
            return None
        if variant:
            v = variant.lower()
            for e in entries:
                if e.variant == v:
                    return e
            return None  # 该变体不存在 → 宁缺勿错
        for e in entries:
            if e.variant is None:
                return e
        return entries[0]  # 无默认版 → 任取其一（仍有可用背景）

    def background_scenes(self) -> list[str]:
        """全部已登记场景 id。"""
        return sorted(self._backgrounds)

    # ------------------------------------------------------------------
    # 查询: 差分（板块结构 2026-08-28: 每外观一个自包含目录 {char}/{outfit}/,
    # 有 emotions.yml 的目录 = 外观; 缺省 outfit="default"）
    # ------------------------------------------------------------------

    def sprite(self, char_id: str, emotion: str,
               outfit: str = "default") -> SpriteMedia | None:
        """查角色差分。emotion 白名单 = manifest sprites 键。查不到 → None。首次查该外观才扫描。"""
        self._ensure_character(char_id, outfit)
        return self._sprites.get((char_id, outfit), {}).get(emotion)

    def sprite_emotions(self, char_id: str,
                        outfit: str = "default") -> list[str]:
        """外观已登记情绪（给 ② 播放协议 parse 白名单 / 导演 prompt）。首次查该外观才扫描。"""
        self._ensure_character(char_id, outfit)
        return sorted(self._sprites.get((char_id, outfit), {}))

    # ------------------------------------------------------------------
    # 内部: 扫描
    # ------------------------------------------------------------------

    def _scan_backgrounds(self) -> None:
        bg_root = self.assets_root / "background"
        if not bg_root.is_dir():
            return
        for p in _iter_background_images(bg_root):
            scene, variant = derive_background(p.stem)
            self._backgrounds.setdefault(scene, []).append(
                BackgroundMedia(scene, p, variant)
            )

    def _ensure_character(self, char_id: str, outfit: str = "default") -> None:
        """外观懒加载: 首次 query 该角色外观才扫描, 之后 O(1)（含不存在外观的空缓存）。"""
        key = (char_id, outfit)
        if key in self._scanned_chars:
            return
        self._scan_character(char_id, outfit)
        self._scanned_chars.add(key)

    def _scan_character(self, char_id: str, outfit: str = "default") -> None:
        char_dir = self.assets_root / "illustration" / char_id / outfit
        if not char_dir.is_dir():
            return
        man = load_character_manifest(char_dir)
        packs = find_spine_packs(char_dir / "spine")
        pref = man["spine"]
        pack = packs.get(pref) or (packs.get(Path(pref).name) if pref else None)
        emotions: dict[str, SpriteMedia] = {}
        for emotion, rel in man["sprites"].items():
            static = char_dir / rel
            emotions[emotion] = SpriteMedia(
                emotion=emotion,
                static_path=static if static.is_file() else None,
                spine=pack,
                anim=man["animations"].get(emotion),
            )
        if emotions:
            self._sprites[(char_id, outfit)] = emotions
