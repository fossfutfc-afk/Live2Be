# -*- coding: utf-8 -*-
"""place_regions — 剧情地理词表（`config/settings/world/regions.yml`）。

> ⚠️ **本 docstring 2026-09-19 重写过**（旧版有几句话把 AI 和我自己都带偏了，
> 逐条改正见下面"旧说法纠正"）。给人看的正稿 = `docs/DESIGN_PLACE.md`;
> 给 AI 看的速查 = `docs/AI_BRIEF_PLACE.md`。

## 它现在只剩**一个**消费方：盒B 的【世界区域】块

**世界设定，不是菜单** —— `overview.yml` 里一个学院名都没有，writer 本来不知道
这个世界有哪些学院，会凭空发明。这与 persona/world 同性质（"你知道的事"）。

## 旧说法纠正（三句都曾是错的）

| 旧说法（已删） | 为什么错 | 现在的真相 |
|---|---|---|
| *"C 链路的'同地'判据默认不吃 `place` 键，**吃 `region`**"* | ① C 链路**根本不用 region**（2026-09-19 用户: region *"基本没有太多作用，也不必落库"*）② `region` 也答不了"同地"——它只到"哪个学院"这一级 | C 链路的准入 = **`place` 键相等**（只声称"同一张图"）; "是不是同一个地方"要靠 **writer 原文的语义**（`node.place_raw`），那与 region 无关 |
| *"地点解析的第一层 = `switch` 地点话 → region 别名归一"* | 第一层现在是**地点表的 `keywords` 别名命中**（0 调用） | `place_table.resolve_exact()` |
| *"`region` 是归一到官方中文主名的枚举，没有一键多义/一地多键的问题"* | 对，但**这个优点没被任何地方用上** —— 它太粗（整个阿拜多斯 = 一组），粗到不能当"同地"的判据 | 保留它只为【世界区域】块 + 将来的地点体系铺路 |

## 两轴仍然要分清（这条是对的）

| 轴 | 字段 | 回答 | 例 |
|---|---|---|---|
| **画面素材** | `place`（表的查表键） | "用哪张图" | `classroom` / `view_sky` |
| **剧情地理** | `region`（本文） | "哪个学院/哪片地方" | `阿拜多斯高级中学` / `夏莱` |

⚠️ **`place` 键不是地名的双射**（用户 2026-09-19 指出，实测两个方向都在表里活着）:
`ruinschoolcorridor` 的 note 自称"也可以用做杂草秘密基地"（一键多义）;
别名「天台」指向 3 个键（一地多键）。所以键相等只声称"同一张图"，
**不声称"同一个地方"** —— 详见 `core/media/place_table.py` 与
`core/brain/nodes.py::place_raw`。

## 哨兵纪律（同 `emo_*`）

`normalize()` 未命中 → `""`（**未知**），绝不返回原文——原文不是 region。
`""` 与"这段没有地点"在调用方看来是同一种"不参与判定"，但**不是**
"这段发生在别的地方"。

## 已知风险：短别名的子串误命中

`千年`（千年科技学院）在自由文本里也可能是时间词（"等了一千年"）。
缓解：本模块的输入是 **switch 的地点名词短语**（"深夜的杂草屋"），不是任意散文;
且 `region` 是**派生字段、不进 LLM 上下文**，误命中只影响注入块的内容。
真出现时按 `note`/别名的口径收紧即可（作者加新译名走 aliases，别新建条目）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from core import paths

logger = logging.getLogger(__name__)

#: 项目根（`core/paths.py` 的宏——绝对路径, cwd 无关, 与 `world_parser` 同规矩）
_PROJECT_ROOT = paths.ROOT

#: 默认路径（`config/settings/world/regions.yml`）
DEFAULT_REGIONS_PATH = paths.REGIONS_PATH

#: 参与子串匹配的最短别名长度（单字别名会疯狂误命中）
_MIN_NEEDLE = 2


@dataclass
class Region:
    """一条剧情地理（`id` 是不改的锚，`zh` 是注入/存储用的主名）。"""

    id: str
    zh: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class RegionTable:
    """`regions.yml` 的解析产物（**缺/坏 → 空表**，绝不抛）。"""

    regions: list[Region] = field(default_factory=list)
    #: 别名/主名 → `zh` 主名（子串匹配用；**不含 latin `id`**——防 `du`/`srt` 撞英文）
    _needles: dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.regions)

    def names(self) -> list[str]:
        """全部 `zh` 主名（注入顺序 = yml 顺序）。"""
        return [r.zh for r in self.regions]

    def normalize(self, text: str) -> str:
        """地点话 → `zh` 主名；**未命中 → `""`**（绝不返回原文）。

        长别名优先（`千年科技学院` 先于 `千年`），避免被短别名截胡。
        """
        t = (text or "").strip()
        if not t:
            return ""
        for needle in sorted(self._needles, key=len, reverse=True):
            if needle in t:
                return self._needles[needle]
        return ""


def load_regions(path: str | Path | None = None) -> RegionTable:
    """读 `regions.yml` → `RegionTable`。

    **宁缺勿错**：文件缺失/损坏/结构不符 → 空表 + 单行 WARNING（不抛）。
    与 `load_world` 的"抛"不同——那边是世界观主档、缺了该炸；这边是**派生视图**，
    缺了只该降级（注入块缺席、解析层返回 `""`）。
    """
    p = Path(path) if path else DEFAULT_REGIONS_PATH
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("[place_regions] 词表不存在: %s（region 层降级）", p)
        return RegionTable()
    except Exception as e:                           # noqa: BLE001 — 坏文件不阻断
        logger.warning("[place_regions] 词表读取失败: %s（region 层降级）", e)
        return RegionTable()

    raw = data.get("regions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        logger.warning("[place_regions] %s 缺 regions 列表（region 层降级）", p.name)
        return RegionTable()

    table = RegionTable()
    for item in raw:
        if not isinstance(item, dict):
            continue
        zh = item.get("zh")
        if not isinstance(zh, str) or not zh.strip():
            continue
        zh = zh.strip()
        aliases = [a.strip() for a in (item.get("aliases") or [])
                   if isinstance(a, str) and a.strip()]
        table.regions.append(Region(
            id=str(item.get("id") or "").strip(), zh=zh, aliases=aliases))
        # 主名与别名都进针表（含别名里的 latin 形式，如 Gehenna/SRT）
        for needle in (zh, *aliases):
            if len(needle) >= _MIN_NEEDLE:
                table._needles.setdefault(needle, zh)
    return table


__all__ = ["DEFAULT_REGIONS_PATH", "Region", "RegionTable", "load_regions"]
