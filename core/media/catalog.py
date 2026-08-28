# -*- coding: utf-8 -*-
"""MediaCatalog — assets/ 媒体查库总入口（纯数据, 背景全量 + 差分按角色懒加载）。

查询（宁缺勿错: 未知 id / 缺资产 → None / 空列表, 不抛异常; 仅构造时 assets 根缺失抛 MediaError）:
    background(scene_id, variant=None)  → 背景（命名派生, 变体白名单切分）
    sprite(char_id, emotion)            → 差分（manifest 情绪白名单 + 可选 spine 导出）
    sprite_emotions / background_scenes / background_variants / has_*  → 供 ② 导演/播放协议校验

架构: 背景=命名派生（零 manifest）; 差分=manifest 映射（情绪白名单真源）。
详见 core/DESIGN_VISUAL.md §5-①。
"""
from __future__ import annotations

from pathlib import Path

from core.common.errors import Live2BeError
from core.media.background import BackgroundMedia, derive_background
from core.media.manifest import load_character_manifest
from core.media.sprites import SpriteMedia, find_spine_packs

# assets/ 默认根（core/media/catalog.py → ../../.. → 项目根/assets）
_DEFAULT_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"

# 背景变体后缀（.py 等脚本残留自动排除）
_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


class MediaError(Live2BeError):
    """媒体查库构造错误（assets 根缺失等）。查询层不抛, 全部降级 None。"""


class MediaCatalog:
    """一次扫描 assets/ 建索引的纯数据查库。构造慢（~百 ms）但查询全 O(1)。"""

    def __init__(self, assets_root: Path | str | None = None) -> None:
        self.assets_root = Path(assets_root) if assets_root else _DEFAULT_ASSETS
        if not self.assets_root.is_dir():
            raise MediaError(f"assets 根不存在: {self.assets_root}")
        self._backgrounds: dict[str, list[BackgroundMedia]] = {}
        self._sprites: dict[str, dict[str, SpriteMedia]] = {}
        self._scanned_chars: set[str] = set()
        # 背景全量（构造时）: 数据驱动必须扫才能知道有哪些场景, 且便宜（620 场景）;
        # 差分按角色懒加载（VN 单角色, 首次 query 才扫该角色并缓存, 宁缺勿错）.
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

    def background_variants(self, scene_id: str) -> list[str]:
        """某场景已有全部变体（供 ② prompt 白名单）。"""
        return sorted(e.variant for e in self._backgrounds.get(scene_id, []) if e.variant)

    def background_scenes(self) -> list[str]:
        """全部已登记场景 id。"""
        return sorted(self._backgrounds)

    def background_dirs(self) -> list[str]:
        """assets/background/ 下目录名清单（② 导演背景分层第一层: 目录粗选）。"""
        bg_root = self.assets_root / "background"
        if not bg_root.is_dir():
            return []
        return sorted(p.name for p in bg_root.iterdir() if p.is_dir())

    def background_scenes_in_dir(self, dir_name: str) -> list[str]:
        """某目录内已派生的 scene_id 清单（② 导演分层第二层: 目录内拍板）。

        懒扫描该目录（按需、便宜）; 目录不存在/无图 → []（宁缺勿错）。
        """
        d = self.assets_root / "background" / dir_name
        if not d.is_dir():
            return []
        seen: set[str] = set()
        for p in d.iterdir():
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS:
                scene, _ = derive_background(p.stem)
                seen.add(scene)
        return sorted(seen)

    # ------------------------------------------------------------------
    # 查询: 差分
    # ------------------------------------------------------------------

    def sprite(self, char_id: str, emotion: str) -> SpriteMedia | None:
        """查角色差分。emotion 白名单 = manifest sprites 键。查不到 → None。首次查该角色才扫描。"""
        self._ensure_character(char_id)
        return self._sprites.get(char_id, {}).get(emotion)

    def sprite_emotions(self, char_id: str) -> list[str]:
        """角色已登记情绪（给 ② 播放协议 parse 白名单 / 导演 prompt）。首次查该角色才扫描。"""
        self._ensure_character(char_id)
        return sorted(self._sprites.get(char_id, {}))

    def has_sprite(self, char_id: str, emotion: str) -> bool:
        self._ensure_character(char_id)
        return emotion in self._sprites.get(char_id, {})

    def has_background(self, scene_id: str, variant: str | None = None) -> bool:
        return self.background(scene_id, variant) is not None

    # ------------------------------------------------------------------
    # 内部: 扫描
    # ------------------------------------------------------------------

    def _scan_backgrounds(self) -> None:
        bg_root = self.assets_root / "background"
        if not bg_root.is_dir():
            return
        for p in bg_root.rglob("*"):
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS:
                scene, variant = derive_background(p.stem)
                self._backgrounds.setdefault(scene, []).append(
                    BackgroundMedia(scene, p, variant)
                )

    def _ensure_character(self, char_id: str) -> None:
        """角色差分懒加载: 首次 query 该角色才扫描, 之后 O(1)（含不存在角色的空缓存）。"""
        if char_id in self._scanned_chars:
            return
        self._scan_character(char_id)
        self._scanned_chars.add(char_id)

    def _scan_character(self, char_id: str) -> None:
        char_dir = self.assets_root / "illustration" / char_id
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
            self._sprites[char_id] = emotions
