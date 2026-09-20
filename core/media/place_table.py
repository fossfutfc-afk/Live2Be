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
import re
from dataclasses import dataclass, field
from pathlib import Path

from core import paths
from core.media.background import derive_background

logger = logging.getLogger(__name__)

#: 默认表路径 = `core/paths.py` 的宏（**值的来源只有那一处**，用户 2026-09-19）
DEFAULT_TABLE_PATH = paths.PLACE_TABLE_PATH

#: 写作用词的判据（表自带 `sdir`，**不许另立名单**——用户 2026-09-19）
WRITING_SDIR = "SDIR_Atmosphere"

#: 分组头的**中文标签**（只用于 `lexicon_text()` 给标注 LLM 的那份文本）。
#: 用户 2026-09-19 看过后裁决: *"直接换中文，不用对比了，保证一致性"* ——
#: `【SDIR_Clubs】` 这种英文资产组织名对 LLM 是噪声, 而整份 prompt 都是中文。
#: ⚠️ 这只是**显示名**, `sdir` 本身（判据 + 资产路径）仍是英文, 不许改。
#: 表里新加一族而这里没标签 → 回落原名（不报错）; `test_place_table` 有镜像断言盯着。
SDIR_LABELS: dict[str, str] = {
    "SDIR_Atmosphere": "气氛镜头",
    "SDIR_Clubs": "社团",
    "SDIR_Infrastructure": "基建",
    "SDIR_Inner": "室内",
    "SDIR_Nature": "自然",
    "SDIR_Outer": "室外",
    "SDIR_Public": "公共设施",
    "SDIR_Schools": "学校",
    "SDIR_Streets": "街道",
}


def sdir_label(sdir: str) -> str:
    """`SDIR_*` → 中文分组头（没登记 → 原样返回, 不抛）。"""
    return SDIR_LABELS.get(sdir, sdir)


#: **可选时刻/天气**（"这一场是白天还是夜里、下没下雨"）——从文件名后缀派生。
#: 用户 2026-09-19 裁决: 候选**从文件名自动派生**（不另立名单、不动导出 schema）。
#: ⚠️ 只放行"场面时刻/天气"这一类; `ruin`/`erode`/`off`/`party`/`fake`/`blur`/`dark`/
#: `fire`/`alert`/`tent`/`sky` 是**剧情状态**（侵蚀/停电/派对……）——现在**没有任何
#: 信号源**告诉标注层"这场戏停电了", 放进去只会变成瞎挑（TODO: 状态类另议）。
MOMENT_VARIANTS: tuple[str, ...] = (
    "night", "sunset", "dawn", "fineday", "cloudy", "rain", "fog",
)

#: 时刻 → 给标注 LLM 看的中文名（与 `sdir` 同一条纪律: 只换显示名, token 不变）
MOMENT_LABELS: dict[str, str] = {
    "night": "夜",
    "sunset": "夕",
    "dawn": "清晨",
    "fineday": "晴",
    "cloudy": "阴",
    "rain": "雨",
    "fog": "雾",
}

#: `moment=""` 在文本里的写法（= 用没有变体后缀的那张图）
BASE_LABEL = "默认"


def moment_label(moment: str) -> str:
    """`night` → `夜`（空/未知 → `默认`/原样）。"""
    if not moment:
        return BASE_LABEL
    return MOMENT_LABELS.get(moment, moment)


def moment_token(text: str) -> str:
    """标注层输出 → 变体 token（接受中文名/英文 token/空; 认不出 → `""`）。"""
    t = (text or "").strip().lower()
    if not t or t == BASE_LABEL:
        return ""
    if t in MOMENT_VARIANTS:
        return t
    for token, label in MOMENT_LABELS.items():
        if t == label.lower():
            return token
    return ""

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

    def moments(self) -> tuple[str, ...]:
        """本条**实际可选**的时刻/天气（从文件名后缀派生, 表里没写就推不出来）。

        判据 = `files` 里每个文件走 `derive_background` 得到的 `variant`, 与
        `MOMENT_VARIANTS` 取交集（保 `MOMENT_VARIANTS` 的顺序, 便于测试与日志）。
        **空 = 只有默认图** ⇒ 第二遍判定根本不用发（0 调用）。
        """
        found = set()
        for rel in self.day + self.night:
            _, variant = derive_background(Path(rel).stem)
            if variant in MOMENT_VARIANTS:
                found.add(variant)
        return tuple(v for v in MOMENT_VARIANTS if v in found)

    def moments_text(self) -> str:
        """给标注 LLM 的候选写法: `默认 / 夜(night) / 夕(sunset)`（无候选 → `默认`）。"""
        parts = [BASE_LABEL] + [f"{moment_label(v)}({v})" for v in self.moments()]
        return " / ".join(parts)

    def asset_for(self, moment: str = "") -> str | None:
        """某一时刻的图（相对路径）。**该时刻没有 → 回落默认图**（宁缺勿错）。

        ⚠️ **别用 `catalog.background(scene_id, variant)` 代替它**: 实测（2026-09-19）
        194 张时刻图里, 走 catalog 会漏 6 张（`BG_ClassRoom2_Night.jpg` 派生成
        `class_room_2` 这个**另一个 scene_id**, 而键的 scene_id 是 `class_room`),
        而表里的 `files` 路径是**逐字准确的（194/194）**——取图就走表。
        """
        want = moment_token(moment)
        if want:
            for rel in self.day + self.night:
                _, variant = derive_background(Path(rel).stem)
                if variant == want:
                    return rel
        return self.asset()

    def asset_url(self, moment: str = "") -> str | None:
        """`asset_for` → 前端 URL（`/assets/background/<rel>`）; 无图 → None。"""
        rel = self.asset_for(moment)
        return f"/assets/background/{rel}" if rel else None

    # ------------------------------------------------------------------
    # 候选图（给"选图"那一步: 同一地点常有好几张）
    # ------------------------------------------------------------------

    def image_label(self, rel: str) -> str:
        """候选图的人话标签（**机器派生, 只是提示**）: `夜` / `默认·差分2` / `雨`。

        "差分N" 的判据 = 派生出的 scene 以 `_数字` 结尾（`class_room_2` ⇒ 差分2）——
        作者在 note 里就是这么说这些图的（*"请使用差分2"*）。认不出 → 差分1。
        """
        scene, variant = derive_background(Path(rel).stem)
        m = re.search(r"_(\d+)$", scene)
        idx = int(m.group(1)) if m else 1
        head = moment_label(variant) if variant else BASE_LABEL
        if idx > 1:
            head += f"·差分{idx}"
        return head

    def image_candidates(self) -> list[tuple[str, str]]:
        """`[(相对路径, 标签)]` —— 这个键**实际有的每一张图**（去重保序）。

        ⚠️ 为什么不是"时刻 token 列表": 作者的表里同一地点往往有多张**无变体**的
        "差分"（`BG_X.jpg` / `BG_X2.jpg`——圣诞树/带家具/白墙 vs 铁墙…），它们的
        区别写在 `note` 里。只给时刻 token 会让这 45 个键的差分永远选不了。
        """
        out: list[tuple[str, str]] = []
        seen: set[str] = set()
        for rel in self.day + self.night:
            if rel and rel not in seen:
                seen.add(rel)
                out.append((rel, self.image_label(rel)))
        return out

    def image_candidate_lines(self) -> str:
        """候选图的 prompt 文本（每行一张, 带标签与文件名）。"""
        return "\n".join(f"  {i + 1}) {Path(rel).name}    （{label}）"
                         for i, (rel, label) in enumerate(self.image_candidates()))

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
        """标注 LLM 看到的一行（`place（别名）［时刻候选］: note`）。

        `［默认/夜(night)/夕(sunset)］` 只在**真有别的图**时出现（30 个键只有一张图
        → 不加噪声）。这是用户 2026-09-19 问的"Night/Sunset 这些让 LLM 知道了吗"的
        答案: 现在知道了（时刻本身由**第二遍**单独判, 见 `core/bond/moment_annotate.py`）。
        """
        kw = "/".join(self.keywords)
        head = f"{self.place}（{kw}）" if kw else self.place
        if self.moments():
            head += f"［{self.moments_text()}］"
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

    def moments(self, place: str) -> tuple[str, ...]:
        """某键的可选时刻（没有这个键 → 空）。**空 = 只有默认图, 不用问 LLM**。"""
        e = self.get(place)
        return e.moments() if e else ()

    def moments_text(self, place: str) -> str:
        """某键的候选写法（`默认 / 夜(night) / 夕(sunset)`）; 键不存在 → `默认`。"""
        e = self.get(place)
        return e.moments_text() if e else BASE_LABEL

    def asset_url(self, place: str, moment: str = "") -> str | None:
        """某键某一时刻的 URL（`/assets/background/<rel>`）; 键/图缺失 → None。"""
        e = self.get(place)
        return e.asset_url(moment) if e else None

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
            lines.append(f"【{sdir_label(sdir)}】")
            lines += [f"  {e.line(with_note=with_note)}" for e in groups[sdir]]
        return "\n".join(lines)

    def writing_words(self) -> list[PlaceEntry]:
        """**写作用词**（`sdir == SDIR_Atmosphere`）—— 主 LLM 唯一的内容词表。

        用户 2026-09-19: *"这个词表比较特殊，是某些特效比如说 black 或者星空
        这种词，这是因为这些词能让 LLM 更好的写作。"* 判据 = **表自带的 sdir**，
        不许另立名单（否则又是一处写死的地名）。
        """
        return [e for e in self.entries.values() if e.sdir == WRITING_SDIR]

    #: ⚠️ 2026-09-21 复核: 同批删掉了零消费者的 `by_region()`; **本法保留**——
    #: 它有真实消费者（`experiments/place_resolve_real.py` 打印表自查）。
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


def _loads_with_dup_check(text: str) -> tuple[object, list[str]]:
    """`json.loads` + **重复键检测**（返回 `(对象, 重复键名列表)`）。

    为什么需要: 手编 JSON 里同一个键写两遍, `json.loads` **不报错、静默保留最后
    一个**（`.testtmp/probe_json_dupkey.py` 实测）——生成侧安全（dict 构造 +
    tempo 的 A1 撞车保护）, 但**读取侧**可能被手编文件骗: 一个地点悄悄消失/被覆盖,
    而表看起来"读成功了"。这里把它变成一条 WARNING + `PlaceTable.error`。
    """
    dups: list[str] = []

    def _hook(pairs):
        out: dict = {}
        for k, v in pairs:
            if k in out:
                dups.append(str(k))
            out[k] = v
        return out

    return json.loads(text, object_pairs_hook=_hook), dups


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
        raw, dups = _loads_with_dup_check(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("[place_table] 表读取失败（地点标注降级）: %s", e)
        return PlaceTable(path=p, ok=False, error=f"读取失败: {e}")
    table = _parse(raw, p)
    if dups:
        # 手编 JSON 里写重复键 **不报错、静默保留最后一个**（探针实测）——
        # 生成侧安全（dict + A1 撞车保护）, 读取侧要自己看见（一行的事）。
        dup_msg = f"重复键 {dups}（json 只保留最后一个）"
        logger.warning("[place_table][DUPKEY] %s: %s", p, dup_msg)
        table.error = f"{table.error}; {dup_msg}" if table.error else dup_msg
    if len(_CACHE) >= _CACHE_MAX:                    # 简单 LRU: 满了清空
        _CACHE.clear()
    _CACHE[ck] = table
    return table


__all__ = [
    "DEFAULT_TABLE_PATH",
    "SDIR_LABELS",
    "WRITING_SDIR",
    "PlaceEntry",
    "PlaceTable",
    "load_table",
    "reset_cache",
    "sdir_label",
]
