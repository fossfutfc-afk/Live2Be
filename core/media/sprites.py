# -*- coding: utf-8 -*-
"""差分/spine 资源查库 — 语义情绪 → 静态 png / spine 导出。

角色资源布局（assets/illustration/{char}/{outfit}/）——标准外观格式（2026-09-12）:
    emotions.yml  ★必有（键 + 资源 ID, 双投影真源; 见 docs/EMOTIONS_CONFIG.md）
    portrait/     ★必有（该外观的 GUI 头像 / 其他界面渲染资产; MMT 列表读这里）
    spine/        ★必有（spine 导出目录: haruka_spr/{skel,atlas,png}; atlas 区名即语义）
    diff/         可选（静态差分 png, 文件名无语义, 情绪映射在 emotions.yml 词表）
    possession/   角色级物品图（不参与 sprite 查询）
    l2d/ other/   占位（空目录自然忽略）

spine 导出包: 目录内 {dir}/{dir}.skel + .atlas + .png 三件套齐全即识别为一包。
atlas 区名解析: 文本格式, 列 0 行 = 页名/区名, 缩进行 = 属性（页面属性带 ':' 跳过）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SpinePack:
    """一份 spine 导出（skel/atlas/png 三件套）。regions = atlas 区名序列。"""
    name: str
    folder: Path
    skel: Path
    atlas: Path
    png: Path
    regions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpriteMedia:
    """一条差分资源。static_path=静态 png（v1 CSS fade）, spine=可选 spine 导出（v2 渲染器）,
    anim=双投影派生的 spine 动画名（manifest 资源 ID → 动画; None = 纯静态图, 播放器降级 diff）。"""
    emotion: str
    static_path: Path | None = None
    spine: SpinePack | None = None
    anim: str | None = None


def atlas_regions(atlas_path: Path) -> tuple[str, ...]:
    """解析 spine .atlas 文本 → 区名序列（保持文件顺序, 跳过页名/页面属性）。

    读失败 → ()（宁缺勿错, 不崩）。格式:
        <页名.png>
        size: 1024,1024
        format: RGBA8888
        ...
        <区名1>
          xy: ...
          ...
    """
    try:
        lines = atlas_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    names: list[str] = []
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip() or line[0].isspace():
            continue
        s = line.strip()
        if ":" in s or s.endswith((".png", ".jpg")):
            continue  # 页面属性行 / 页名
        names.append(s)
    return tuple(names)


def find_spine_packs(spine_dir: Path) -> dict[str, SpinePack]:
    """扫描 spine/ 子目录 → {包名: SpinePack}。三件套齐全才算, 残缺跳过（宁缺勿错）。"""
    packs: dict[str, SpinePack] = {}
    if not spine_dir.is_dir():
        return packs
    for sd in sorted(spine_dir.iterdir()):
        if not sd.is_dir():
            continue
        skel = sd / f"{sd.name}.skel"
        atlas = sd / f"{sd.name}.atlas"
        png = sd / f"{sd.name}.png"
        if skel.is_file() and atlas.is_file() and png.is_file():
            packs[sd.name] = SpinePack(
                name=sd.name, folder=sd,
                skel=skel, atlas=atlas, png=png,
                regions=atlas_regions(atlas),
            )
    return packs
