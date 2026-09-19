# -*- coding: utf-8 -*-
"""`place_table` 单测（C1, 2026-09-19）——地点语义键表 + 层1 精确命中。

这张表是**标注层唯一的语料**（`docs/DESIGN_PLACE.md §6`），所以这里钉五件事:

  ① **动态读入真的动态**（用户硬要求）——按 mtime 失效, 改表即生效
  ② **层1 只做"确定无疑"**——歧义照实返回多条（不猜）、表外返回空（不硬凑）
  ③ **`dir`/`sdir` 不进别名**——它们是"一族/一大类", 不是"一个地点"
  ④ **`note` 一定在词表文本里**——它是"表外也能落位"的唯一依据
  ⑤ **缺/坏表 → 空表降级**, 绝不抛（宁缺勿错）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.media import place_table as pt                          # noqa: E402


def _table() -> pt.PlaceTable:
    t = pt.load_table()
    assert t.ok, f"真表读不出来: {t.error} ({t.path})"
    return t


def test_load_real_table():
    """真表读得出来（168 条; 字段齐全度）。"""
    t = _table()
    s = t.stats()
    assert s["n"] >= 150, s
    assert s["keywords"] >= 200, s
    assert s["no_region"] > 0, "region 本来就没填满——这条会随作者补全而变"
    assert s["writing"] >= 3, s
    e = t.get("view_sky")
    assert e is not None and "星空" in e.keywords, e
    print(f"    table: {s['n']} 条 / 别名 {s['keywords']} / 写作用词 {s['writing']} 条 / "
          f"sdir {len(s['sdirs'])} 类")


def test_outer_key_equals_place():
    """★ A1 不变量: 导出外层键 == 行内 `place`（168/168）。

    工具侧 `api_export` 一旦退回按 `root` 建键, 这条立刻红。
    """
    raw = json.loads(pt.DEFAULT_TABLE_PATH.read_text(encoding="utf-8"))
    bad = [k for k, v in raw.items()
           if not isinstance(v, dict) or k != str(v.get("place") or "").strip()]
    assert not bad, f"外层键 ≠ place: {bad[:5]}"
    print(f"    A1: 外层键 == place  {len(raw)}/{len(raw)}")


def test_aliases_exclude_dir_and_sdir():
    """★ `dir`/`sdir` **不是**别名——拿它们当针会一针指一片。

    实测教训（2026-09-19）: `DIR_Z` 派生单字别名 `z` → 一口气指向 13 个 place。
    """
    t = _table()
    for text in ("DIR_Z", "z", "DIR_ViewSora", "viewsora", "SDIR_Inner", "sdirstreets"):
        got = t.resolve_exact(text)
        assert got == [], f"{text!r} 不该被层1 命中 → {got}"
    print("    layer1: dir/sdir 一律不作别名（z/viewsora 均不命中）")


def test_resolve_exact_whole_then_substring():
    """层1: 整串优先, 子串兜底（命中就是 0 调用）。"""
    t = _table()
    assert t.resolve_exact("星空") == ["view_sky"]              # 整串 = keyword
    assert t.resolve_exact("view_sky") == ["view_sky"]          # 整串 = place
    assert t.resolve_exact("black") == ["black"]
    assert t.resolve_exact("教室") == ["classroom"]
    # 子串（地点话里裹着别名）
    assert t.resolve_exact("学校天台") == ["school_rooftop"]
    assert t.resolve_exact("深夜的学校天台") == ["school_rooftop"]
    assert t.resolve_exact("  ") == [] and t.resolve_exact("") == []
    assert t.resolve_exact(None) == []
    print("    layer1: 整串/子串命中; 空/None → []")


def test_resolve_exact_returns_ambiguity_instead_of_guessing():
    """★ 歧义**照实返回多条**——层1 不猜（下沉层2 或按 current/region 消歧）。"""
    t = _table()
    got = t.resolve_exact("天台")
    assert len(got) >= 2, f"「天台」应当是多义词 → {got}"
    assert "school_rooftop" in got
    got2 = t.resolve_exact("放学后的天台")
    assert len(got2) >= 2, got2
    print(f"    layer1: 歧义不猜 → 「天台」{sorted(got)}")


def test_resolve_exact_leaves_out_of_table_alone():
    """★ 表外地名 → `[]`（**层1 不该硬凑**）。

    这在设计里是**正常情况**（writer 自由写）——由层2 读 `note` 就近推测。
    真机 `杂草屋 → school_rooftop` 就是"层1 时代只有 31 条裸 slug"的产物。
    """
    t = _table()
    for text in ("深夜的杂草屋", "校舍后面的杂草屋", "某个不知名的地方", "傍晚的杂草坡道"):
        assert t.resolve_exact(text) == [], f"{text!r} 不该被层1 命中"
    print("    layer1: 表外 → []（交层2 读 note 推测, 不硬凑）")


def test_asset_day_night_and_fallback():
    """`files` 取图: 夜景优先, **缺夜景降级 day**（宁缺勿错）; 都没有 → None。"""
    t = _table()
    e = t.get("view_sky")
    assert e is not None and e.day and e.night
    assert e.asset() == e.day[0]
    assert e.asset(night=True) == e.night[0]
    only_day = [x for x in t.all() if x.day and not x.night]
    assert only_day, "真表里应当有只有 day 的条目"
    assert only_day[0].asset(night=True) == only_day[0].day[0], "缺夜景要降级 day"
    night_only = [x for x in t.all() if x.night and not x.day]
    for x in night_only:
        assert x.asset() == x.night[0], "只有夜景时 day 也要给得出图"
    empty = pt.PlaceEntry(place="x")
    assert empty.asset() is None and empty.asset(night=True) is None
    print(f"    files: 夜景缺 → 降级 day; 只有 day 的 {len(only_day)} 条, "
          f"只有夜景的 {len(night_only)} 条")


def test_lexicon_text_groups_by_sdir_and_carries_note():
    """★ 层2 的词表文本: 按 `sdir` 分组（**中文头**）+ **必须带 `note`**。

    分组头 2026-09-19（PL6）从 `【SDIR_Clubs】` 换成 `【社团】`——用户裁决
    *"直接换中文，不用对比了，保证一致性"*。⚠️ 换的只是**显示名**, `sdir` 本身
    仍是英文（判据 + 资产路径都靠它）。
    """
    t = _table()
    text = t.lexicon_text()
    assert text and text.startswith("【")
    e = t.get("view_sky")
    assert e is not None and e.note
    assert e.note in text, "note 没进词表文本 → 层2 只能瞎猜"
    assert "view_sky（" in text and "星空" in text
    assert "【气氛镜头】" in text and "【社团】" in text, "分组头该是中文"
    assert "SDIR_" not in text, "英文资产组织名不该出现在给 LLM 的文本里"
    # 限定分组（给"只要写作用词"一类子集用）
    only = t.lexicon_text(sdirs=(pt.WRITING_SDIR,))
    assert "view_sky" in only and "classroom" not in only
    assert "【社团】" not in only, "限定分组后不该出现别的组"
    # 不带 note 的渲染也不能崩
    assert "view_sky" in t.lexicon_text(with_note=False)
    print(f"    lexicon_text: {len(text)} 字符（含 note）, 分组头中文, 可限定 sdir")


def test_sdir_labels_cover_the_real_table():
    """★ 镜像: 表里出现的每个 `sdir` 都得有中文标签（新加一族 → 这里红）。

    红了怎么修: 在 `place_table.SDIR_LABELS` 里给它加个中文名（**别改 `sdir` 本身**）。
    """
    t = _table()
    missing = sorted({e.sdir for e in t.all() if e.sdir} - set(pt.SDIR_LABELS))
    assert not missing, f"这些 sdir 没有中文标签: {missing}"
    assert pt.sdir_label("SDIR_新族") == "SDIR_新族", "没登记的该原样回落, 不该抛"
    print(f"    sdir 标签: {len(pt.SDIR_LABELS)} 个, 覆盖真表全部 {len({e.sdir for e in t.all() if e.sdir})} 类")


def test_writing_words_judged_by_sdir():
    """写作用词 = `sdir == SDIR_Atmosphere`（**判据在表里, 不另立名单**）。"""
    t = _table()
    words = t.writing_words()
    places = [e.place for e in words]
    assert "view_sky" in places and "black" in places, places
    assert all(e.sdir == pt.WRITING_SDIR for e in words)
    assert "classroom" not in places, "普通地点不该混进写作用词"
    print(f"    writing_words: {sorted(places)}")


def test_by_region_only_nonempty():
    """`region` 轴: 只收非空（空 region 是"未知", 不是"某个区域"）。"""
    t = _table()
    by = t.by_region()
    assert by, "真表里已有 region 标注"
    assert all(k for k in by)
    total = sum(len(v) for v in by.values())
    assert total == sum(1 for e in t.all() if e.region)
    print(f"    region: {len(by)} 个区域 / {total} 个 place")


def test_scene_id_translates_table_key_to_asset_key():
    """★ 表键 ≠ 资产 scene_id——下游（导演/URL）吃的是后者（C5, 2026-09-19）。

    `classroom`（作者手写语义键）vs `class_room`（文件名派生）;
    `68office` → `kohshinjo_room` 是作者重命名过的条目, 靠 `files` 才对得上。
    """
    t = _table()
    cases = {
        "classroom": "class_room",
        "moderncafe": "modern_cafe",
        "68office": "kohshinjo_room",
        "hyakkayouran_tatamiroom": "hyakkayouran_tatami_room",
        "school_rooftop": "school_rooftop",      # slug 型键本来就是 scene_id
    }
    for key, want in cases.items():
        got = t.scene_id(key)
        assert got == want, f"{key} → {got}（期望 {want}）"
    # 未知键 → 原样返回（调用方按老口径再试一次）; 空 → None
    assert t.scene_id("不存在的键") == "不存在的键"
    assert t.scene_id("") is None
    # 派生必须与 catalog 同源（同一个 derive_background, 不会漂）
    from core.media.background import derive_background
    e = t.get("classroom")
    assert e is not None and e.scene_id() == derive_background("BG_ClassRoom")[0]
    assert pt.PlaceEntry(place="x").scene_id() is None, "没有 files → None"
    print(f"    scene_id: {len(cases)} 条表键 → 资产键（含重命名条目）")


def test_scene_id_all_entries_resolvable():
    """真表里**每条**都翻得出 scene_id（否则那条永远切不出图）。"""
    t = _table()
    bad = [e.place for e in t.all() if not e.scene_id()]
    assert not bad, f"这些条目翻不出 scene_id: {bad}"
    print(f"    scene_id: 全表 {len(t)} 条都能翻到资产键")


def test_mtime_cache_makes_it_truly_dynamic(tmp_path):
    """★ 用户硬要求: **动态读入**——改表即生效, 不重启进程。"""
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"a": {"place": "a", "keywords": ["甲"]}},
                            ensure_ascii=False), encoding="utf-8")
    t1 = pt.load_table(p)
    assert t1.ok and t1.keys() == ["a"] and t1.resolve_exact("甲") == ["a"]
    # 改表（同时改大小 → mtime/size 双保险）
    p.write_text(json.dumps({"a": {"place": "a", "keywords": ["甲"]},
                             "bb": {"place": "bb", "keywords": ["乙"]}},
                            ensure_ascii=False), encoding="utf-8")
    t2 = pt.load_table(p)
    assert t2.keys() == ["a", "bb"], "表变了没重读 —— 动态读入失效"
    assert t2.resolve_exact("乙") == ["bb"]
    assert t1.keys() == ["a"], "旧表对象被就地改掉了（缓存应当是快照）"
    pt.reset_cache()
    print("    cache: 改表 → 重读生效（旧快照不被污染）; reset_cache 可用")


def test_missing_or_broken_degrades_never_raises(tmp_path):
    """**绝不抛**: 缺文件 / 坏 JSON / 顶层不是对象 → 空表（调用方回落不标注）。"""
    miss = pt.load_table(tmp_path / "nope.json")
    assert not miss and not miss.ok and miss.error
    assert miss.keys() == [] and miss.resolve_exact("教室") == []
    assert miss.lexicon_text() == "" and miss.writing_words() == []
    assert miss.stats()["n"] == 0
    bad = tmp_path / "bad.json"
    bad.write_text("{不是 json", encoding="utf-8")
    assert pt.load_table(bad).keys() == []
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    assert pt.load_table(bad).keys() == []
    bad.write_text("null", encoding="utf-8")
    assert pt.load_table(bad).keys() == []
    # 逐条容错: 坏条目丢弃, 好条目留下（不因一条废整表）
    bad.write_text(json.dumps({"good": {"place": "good"}, "bad": 42,
                               "noplace": {"keywords": ["x"]}},
                              ensure_ascii=False), encoding="utf-8")
    t = pt.load_table(bad)
    assert t.ok and "good" in t.keys() and "noplace" in t.keys()
    assert "noplace" in t.keys(), "缺 place 字段 → 用外层键兜底"
    print("    degrade: 缺/坏表 → 空表; 坏条目逐条丢弃, 不抛")


if __name__ == "__main__":
    test_load_real_table()
    test_outer_key_equals_place()
    test_aliases_exclude_dir_and_sdir()
    test_resolve_exact_whole_then_substring()
    test_resolve_exact_returns_ambiguity_instead_of_guessing()
    test_resolve_exact_leaves_out_of_table_alone()
    test_asset_day_night_and_fallback()
    test_lexicon_text_groups_by_sdir_and_carries_note()
    test_sdir_labels_cover_the_real_table()
    test_writing_words_judged_by_sdir()
    test_by_region_only_nonempty()
    print("all place_table tests passed")
