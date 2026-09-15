# -*- coding: utf-8 -*-
"""place_regions — 剧情地理词表（`config/settings/world/regions.yml`）。

## 两根轴：`region` ≠ `place`

`DESIGN_PLACE` §1② 把地点拆成两层，本项目其余部分一直混着用：

| 轴 | 字段 | 回答的问题 | 例 |
|---|---|---|---|
| **画面素材** | `place`（资产键） | "用哪张图" | `school_rooftop` / `view_sky` |
| **剧情地理** | `region`（本文） | "哪片地方" | `阿拜多斯高级中学` / `夏莱` |

**为什么必须分开**（用户 2026-09-15 提醒）: `place` 字段里混着两类键——
`place_studio.default_place()` 派生的**文件名 slug**（描述资产）与作者手写的
**语义键**（描述地点），且**无从判别是哪一种**。后果两个方向都有:
一键多义（`class_room` 同时服务阿拜多斯/格黑娜教室 → 求交假阳性）与
一地多键（`DIR_ViewSora` 下三个 `view_*` → 求交假阴性）。
所以 **C 链路的"同地"判据默认不吃 `place` 键**，吃 `region`——
而 `region` 是**归一到官方中文主名的枚举**，没有这个问题。

## 两个消费方（都不是"给 LLM 看可选空间"）

1. **盒B 的【世界区域】块** —— **世界设定，不是菜单**。
   `overview.yml` 里**没有任何学院名**，writer 本来不知道这个世界有哪些学院，
   会凭空发明。这与 persona/world 同性质（"你知道的事"）。
2. **地点解析的第一层** —— `switch` 地点话 → `region` 别名归一，
   **纯字符串、0 调用、不依赖 embedding 后端**。
   在 tempo 语义键表接通之前，这是 C 链路**唯一现在就可靠**的一层。

## 哨兵纪律（同 `emo_*` / `story_time`）

`normalize()` 未命中 → `""`（**未知**），绝不返回原文——原文不是 region。
`""` 与"这段没有地点"在调用方看来是同一种"不参与判定"，但**不是**
"这段发生在别的地方"。

## 已知风险：短别名的子串误命中

`千年`（千年科技学院）在自由文本里也可能是时间词（"等了一千年"）。
缓解：本模块的输入是 **switch 的地点名词短语**（"深夜的杂草屋"），不是任意散文;
且 `region` 是**派生字段、不进 LLM 上下文**，误命中只影响召回分组，不污染创作。
真出现时按 `note`/别名的口径收紧即可（作者加新译名走 aliases，别新建条目）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

#: 项目根（绝对路径——cwd 无关，与 `world_parser` 同规矩）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

#: 默认路径（`config/settings/world/regions.yml`）
DEFAULT_REGIONS_PATH = _PROJECT_ROOT / "config" / "settings" / "world" / "regions.yml"

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
