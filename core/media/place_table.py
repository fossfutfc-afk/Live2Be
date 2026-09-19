# -*- coding: utf-8 -*-
"""place_table — 地点语义键表（`config/settings/world/place_entities.json`）。

## 这张表是什么

资产整理工具（`place_studio.py`，工作区 `D:\\myStuff\\tempo\\`）的导出产物：
**每条 = 一个可被剧情提到的地点**。它自带三样别处没有的东西:

    place     查表键（唯一标识 —— 导出外层键与这个字段**同值**，2026-09-19 收口）
    keywords  别名数组 —— **层1 精确命中**的语料（`, ， / | 、 ; ；` 已由工具拆好）
    note      作者写的用途说明 —— **层2"表外也能落位"的唯一依据**（见下）
    region    剧情地理（`regions.yml` 主名; 可空）
    sdir/dir  资产组织归属（三档分流的判据; `SDIR_Atmosphere` = 写作用词）
    files     {day, night} 资产路径（**相对 assets/background/**）

## 为什么不是一张写死的词表（用户 2026-09-19）

*"这个表因为官方地点的更新是会进行更新或者调整措辞的，所以最好是动态读入
而非写成死代码。"* ⇒ **按 mtime 缓存**：作者改完表重导，下一次调用即生效，
不重启进程; 路径可配（构造参数 > 默认路径），换表/换世界线不改代码。

## 两根轴，别混

* **层1（`resolve_exact`）**——`place` + `keywords` 的纯字符串命中，**0 调用**。
  ⚠️ **`dir`/`sdir` 不进别名**：`dir` 是**一族**不是一个地点
  （拿它当别名，`DIR_Z` 会变出一个单字别名 `z`，一口气指向 13 个 place——
  2026-09-19 探针实测）。
* **层2（`lexicon_text`）**——喂给**标注 LLM** 的整表文本（**含 `note`**）。
  🚫 **不给主 LLM**：主 LLM 只拿"写作用词"（`writing_words()`，见
  `docs/DESIGN_PLACE.md §6` 三档分流）。

## 表外地点不是缺陷路径

writer 自由写（含表里没有的，如"深夜的杂草屋"）。层1 miss 是**正常的**——
层1 不该猜; 层2 拿 `note` 就近推测。所以 **`note` 缺 = 这条路直接断**，
这正是它必须进导出的原因。

## 宁缺勿错

缺表/坏表/形状不符 → **空表**（`ok=False` + `error`），绝不抛。空表 = 调用方
回落"不标注地点"（画面保持）; 表内 `files` 缺项 → `asset()` 返回 None
（夜景缺 → **降级 day**），同一条纪律。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from core import paths
from core.media.background import derive_background

logger = logging.getLogger(__name__)

#: 默认表路径 = `core/paths.py` 的宏（**值的来源只有那一处**，用户 2026-09-19）
DEFAULT_TABLE_PATH = paths.PLACE_TABLE_PATH

#: 写作用词的判据（表自带 `sdir`，**不许另立名单**——用户 2026-09-19）
WRITING_SDIR = "SDIR_Atmosphere"

#: 层1 子串匹配的最短针长（单字别名只允许整串命中——否则"桥"满地误命中）
_MIN_NEEDLE = 2


def _str_list(raw: object) -> tuple[str, ...]:
    """宽松取字符串数组（标量也接受；非 str 丢）。"""
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for it in items:
        s = str(it).strip() if it is not None else ""
        if s and s not in out:
            out.append(s)
    return tuple(out)


@dataclass(frozen=True)
class PlaceEntry:
    """表里的一条（`place` 是唯一标识）。"""

    place: str
    region: str = ""
    sdir: str = ""
    dir: str = ""
    keywords: tuple[str, ...] = ()
    note: str = ""
    day: tuple[str, ...] = ()
    night: tuple[str, ...] = ()

    def aliases(self) -> tuple[str, ...]:
        """层1 的针 = `place` + `keywords`（去重保序）。

        🚫 不含 `dir`/`sdir`——它们是"一族/一大类"，不是"一个地点"。
        """
        out = [self.place, *self.keywords]
        seen: list[str] = []
        for s in out:
            s = s.strip()
            if s and s.lower() not in {x.lower() for x in seen}:
                seen.append(s)
        return tuple(seen)

    def asset(self, *, night: bool = False) -> str | None:
        """背景根相对路径。`night=True` 优先夜景，**没有就降级 day**（宁缺勿错）。"""
        if night:
            return (self.night or self.day or (None,))[0]
        return (self.day or self.night or (None,))[0]

    def scene_id(self) -> str | None:
        """本条 → **资产派生的 scene_id**（`MediaCatalog` 的键）。

        表键（`classroom`）与资产 scene_id（`class_room`）**不是一回事**——
        前者是作者手写的语义键，后者由文件名派生。下游（导演查库 / 前端 URL /
        `paragraphs[].place_bg`）吃的是后者，所以这里做一次翻译。
        取 `files` 里第一个文件的名字派生（与 `MediaCatalog` 同一函数，不会漂）。
        `files` 空 → None（调用方回落）。
        """
        for rel in (self.day + self.night):
            scene, _ = derive_background(Path(rel).stem)
            if scene:
                return scene
        return None

    def line(self, *, with_note: bool = True) -> str:
        """标注 LLM 看到的一行（`place（别名）: note`）。"""
        kw = "/".join(self.keywords)
        head = f"{self.place}（{kw}）" if kw else self.place
        if with_note and self.note:
            return f"{head}: {self.note}"
        return head


@dataclass
class PlaceTable:
    """`place_entities.json` 的解析产物（**缺/坏 → 空表**，绝不抛）。"""

    entries: dict[str, PlaceEntry] = field(default_factory=dict)
    path: Path | None = None
    ok: bool = False
    error: str = ""
    #: 惰性别名索引（一次构建, 之后 O(1)）——不参与 repr/比较
    _idx: dict[str, list[str]] | None = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # 基本查询
    # ------------------------------------------------------------------

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def keys(self) -> list[str]:
        """全部查表键（**插入序**——表是作者按 sdir 整理的，顺序即人读顺序）。"""
        return list(self.entries)

    def get(self, place: str) -> PlaceEntry | None:
        return self.entries.get((place or "").strip())

    def scene_id(self, place: str) -> str | None:
        """表键 → 资产 scene_id（下游查图用）; 表键本身也行（slug 型键两者相同）。"""
        e = self.get(place)
        return (e.scene_id() if e else None) or ((place or "").strip() or None)

    def all(self) -> list[PlaceEntry]:
        return list(self.entries.values())

    # ------------------------------------------------------------------
    # 层1：别名精确命中（0 调用）
    # ------------------------------------------------------------------

    def _needles(self) -> dict[str, list[str]]:
        """别名（小写）→ place 列表（惰性一次构建）。**歧义是正常结果**。"""
        if self._idx is None:
            idx: dict[str, list[str]] = {}
            for e in self.entries.values():
                for a in e.aliases():
                    lst = idx.setdefault(a.lower(), [])
                    if e.place not in lst:
                        lst.append(e.place)
            self._idx = idx
        return self._idx

    def resolve_exact(self, text: str) -> list[str]:
        """整串 → **最长别名**子串，两级精确命中; 返回候选 `place` 列表。

        * **整串命中**（文本 == 某个 `place`/别名）→ 只认这一层级的结果
        * 否则**子串**（别名出现在文本里，针长 ≥ 2）→ **取最长的那些针**
          （`长别名优先`，同 `place_regions.normalize` 的规矩）:
          `深夜的学校天台` 里 `学校天台`(4) 赢过 `天台`(2) → 唯一命中
          `放学后的天台` 里最长只有 `天台`(2) → 3 条候选 = **歧义照实返回**
        * 空文本/未命中 → `[]`

        ⚠️ **不做反向包含**（`text in 别名`）——2026-09-19 实测它会出事:
        `z` 命中 `big_plaza`（单字文本抓走长 latin 键）、短文本抓走长别名。
        层2 有 `note` 兜底, 不值得为这点召回率引入误命中。

        ⚠️ **歧义不猜**：调用方拿到 ≥2 条时必须下沉层2（或按 `current_place`/
        `region` 消歧）——层1 只负责"确定无疑的那部分"。
        """
        t = (text or "").strip().lower()
        if not t:
            return []
        idx = self._needles()
        if t in idx:
            return list(idx[t])
        hits: list[tuple[int, list[str]]] = []
        for needle, places in idx.items():
            if len(needle) >= _MIN_NEEDLE and needle in t:
                hits.append((len(needle), places))
        if not hits:
            return []
        longest = max(n for n, _ in hits)
        out: list[str] = []
        for n, places in hits:
            if n != longest:
                continue
            for p in places:
                if p not in out:
                    out.append(p)
        return out

    # ------------------------------------------------------------------
    # 层2：整表文本（给标注 LLM）
    # ------------------------------------------------------------------

    def lexicon_text(self, *, with_note: bool = True,
                     sdirs: tuple[str, ...] | None = None) -> str:
        """标注 LLM 的整表词表文本（按 `sdir` 分组，**含 `note`**）。

        `sdirs` 限定分组（`None` = 全部）——给"只想要写作用词"一类子集用。
        **空表 → `""`**（调用方据此回落到旧词表/不标注）。
        """
        groups: dict[str, list[PlaceEntry]] = {}
        for e in self.entries.values():
            if sdirs is not None and e.sdir not in sdirs:
                continue
            groups.setdefault(e.sdir or "（未分类）", []).append(e)
        if not groups:
            return ""
        lines: list[str] = []
        for sdir in sorted(groups):
            lines.append(f"【{sdir}】")
            lines += [f"  {e.line(with_note=with_note)}" for e in groups[sdir]]
        return "\n".join(lines)

    def writing_words(self) -> list[PlaceEntry]:
        """**写作用词**（`sdir == SDIR_Atmosphere`）—— 主 LLM 唯一的内容词表。

        用户 2026-09-19: *"这个词表比较特殊，是某些特效比如说 black 或者星空
        这种词，这是因为这些词能让 LLM 更好的写作。"* 判据 = **表自带的 sdir**，
        不许另立名单（否则又是一处写死的地名）。
        """
        return [e for e in self.entries.values() if e.sdir == WRITING_SDIR]

    def by_region(self) -> dict[str, list[str]]:
        """`region` → place 列表（只收**非空** region; 备 C 链路"同地"分组用）。"""
        out: dict[str, list[str]] = {}
        for e in self.entries.values():
            if e.region:
                out.setdefault(e.region, []).append(e.place)
        return out

    def stats(self) -> dict[str, object]:
        """一行可打的自查（`place_table` 日志用）。"""
        n_kw = sum(len(e.keywords) for e in self.entries.values())
        return {
            "n": len(self.entries),
            "keywords": n_kw,
            "no_note": sum(1 for e in self.entries.values() if not e.note),
            "no_region": sum(1 for e in self.entries.values() if not e.region),
            "no_day": sum(1 for e in self.entries.values() if not e.day),
            "writing": len(self.writing_words()),
            "sdirs": sorted({e.sdir for e in self.entries.values() if e.sdir}),
            "path": str(self.path) if self.path else "",
            "ok": self.ok,
        }


# ---------------------------------------------------------------------------
# 载入（mtime 缓存 —— 改表即生效，不重启进程）
# ---------------------------------------------------------------------------

#: `(path, mtime_ns, size)` → 已解析的表
_CACHE: dict[tuple[str, int, int], PlaceTable] = {}
_CACHE_MAX = 8


def reset_cache() -> None:
    """清缓存（测试/排查用；正常路径靠 mtime 自动失效）。"""
    _CACHE.clear()


def _parse(raw: object, path: Path) -> PlaceTable:
    """JSON 对象 → 表。**形状不符的条目逐条丢弃**（不因一条坏数据废掉整表）。"""
    if not isinstance(raw, dict):
        return PlaceTable(path=path, ok=False, error="顶层不是对象")
    entries: dict[str, PlaceEntry] = {}
    bad = 0
    for key, v in raw.items():
        if not isinstance(v, dict):
            bad += 1
            continue
        place = str(v.get("place") or key).strip()
        if not place:
            bad += 1
            continue
        files = v.get("files") if isinstance(v.get("files"), dict) else {}
        entries[place] = PlaceEntry(
            place=place,
            region=str(v.get("region") or "").strip(),
            sdir=str(v.get("sdir") or "").strip(),
            dir=str(v.get("dir") or "").strip(),
            keywords=_str_list(v.get("keywords")),
            note=str(v.get("note") or "").strip(),
            day=_str_list(files.get("day")),
            night=_str_list(files.get("night")),
        )
    err = f"{bad} 条形状不符已丢弃" if bad else ""
    return PlaceTable(entries=entries, path=path, ok=True, error=err)


def load_table(path: str | Path | None = None) -> PlaceTable:
    """读表（**mtime 缓存**）。缺/坏 → 空表 + `error`，绝不抛。

    路径解析: 显式 `path` > `DEFAULT_TABLE_PATH`。
    """
    p = Path(path) if path else DEFAULT_TABLE_PATH
    try:
        st = p.stat()
        ck = (str(p), st.st_mtime_ns, st.st_size)
    except OSError:
        return PlaceTable(path=p, ok=False, error=f"表不存在/不可读: {p}")
    hit = _CACHE.get(ck)
    if hit is not None:
        return hit
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("[place_table] 表读取失败（地点标注降级）: %s", e)
        return PlaceTable(path=p, ok=False, error=f"读取失败: {e}")
    table = _parse(raw, p)
    if len(_CACHE) >= _CACHE_MAX:                    # 简单 LRU: 满了清空
        _CACHE.clear()
    _CACHE[ck] = table
    return table


__all__ = [
    "DEFAULT_TABLE_PATH",
    "WRITING_SDIR",
    "PlaceEntry",
    "PlaceTable",
    "load_table",
    "reset_cache",
]
