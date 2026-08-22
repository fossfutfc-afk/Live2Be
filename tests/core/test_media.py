# -*- coding: utf-8 -*-
"""core/media 查库单测 — 命名派生 / manifest / catalog 全路径。

背景:  derive_background（BG_ 前缀 + 变体白名单 + camel→snake / 非 BG_ 防御）
sprites: atlas_regions / find_spine_packs（三件套识别, 残缺跳过）
manifest: load_character_manifest（合法/缺失/损坏 宁缺勿错）
catalog: background/sprite 查询 + 白名单 + 状态降级 + MediaError

运行: python -m pytest tests/core/test_media.py
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.media import MediaCatalog, MediaError
from core.media.background import derive_background
from core.media.manifest import load_character_manifest
from core.media.sprites import atlas_regions, find_spine_packs

# ----------------------------------------------------------------------------
# derive_background: 命名派生
# ----------------------------------------------------------------------------

def test_derive_background_variant_split():
    assert derive_background("BG_GehennaCampus_Night") == ("gehenna_campus", "night")
    assert derive_background("BG_ClassRoom_Night") == ("class_room", "night")
    print("    derive: 变体命中白名单 → 切分")


def test_derive_background_variant_not_scene_word():
    # WildhuntStreet 的 Street 是场景名, 不是变体
    assert derive_background("BG_WildhuntStreet") == ("wildhunt_street", None)
    assert derive_background("BG_ClassRoom") == ("class_room", None)
    print("    derive: 非变体后缀留在场景名")


def test_derive_background_camel_snake_and_digits():
    assert derive_background("BG_ClassRoom2_Night") == ("class_room_2", "night")
    assert derive_background("BG_AbydosCouncilRoom") == ("abydos_council_room", None)
    assert derive_background("BG_HQ_Erode") == ("hq", "erode")
    print("    derive: camel→snake + 数字边界 + 多段")


def test_derive_background_defensive():
    assert derive_background("foo") == ("foo", None)
    assert derive_background("BG_") == ("", None)  # 防御: 空名不崩
    print("    derive: 非 BG_ 前缀防御性原样")


def test_derive_background_case_variants():
    assert derive_background("BG_Class_Night") == ("class", "night")
    assert derive_background("BG_Class_NIGHT") == ("class", "night")  # 大小写归一
    print("    derive: 变体大小写归一")


# ----------------------------------------------------------------------------
# sprites: atlas 区名 / spine 包识别
# ----------------------------------------------------------------------------

_FAKE_ATLAS = (
    "\nharuka_spr.png\n"
    "size: 1024,1024\n"
    "format: RGBA8888\n"
    "filter: Linear,Linear\n"
    "repeat: none\n"
    "01_nomal\n"
    "  rotate: false\n"
    "  xy: 101, 947\n"
    "  size: 97, 69\n"
    "  offset: 0, 0\n"
    "02_respond\n"
    "  rotate: false\n"
    "  xy: 591, 943\n"
    "  size: 97, 73\n"
)


def test_atlas_regions_parses(tmp_path):
    p = tmp_path / "x.atlas"
    p.write_text(_FAKE_ATLAS, encoding="utf-8")
    assert atlas_regions(p) == ("01_nomal", "02_respond")
    print("    atlas_regions: 区名序列（跳过页名/页面属性）")


def test_atlas_regions_missing_file(tmp_path):
    assert atlas_regions(tmp_path / "nope.atlas") == ()
    print("    atlas_regions: 读失败 → ()")


def test_find_spine_packs_full_and_broken(tmp_path):
    pack = tmp_path / "haruka_spr"
    pack.mkdir()
    (pack / "haruka_spr.skel").write_bytes(b"x")
    (pack / "haruka_spr.atlas").write_text(_FAKE_ATLAS, encoding="utf-8")
    (pack / "haruka_spr.png").write_bytes(b"x")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "broken.skel").write_bytes(b"x")       # 缺 atlas/png → 跳过
    packs = find_spine_packs(tmp_path)
    assert set(packs) == {"haruka_spr"}
    assert packs["haruka_spr"].regions == ("01_nomal", "02_respond")
    print("    find_spine_packs: 三件套识别, 残缺跳过")


def test_find_spine_packs_empty(tmp_path):
    assert find_spine_packs(tmp_path / "nope") == {}
    print("    find_spine_packs: 目录不存在 → {}")


# ----------------------------------------------------------------------------
# manifest: 宁缺勿错
# ----------------------------------------------------------------------------

_VALID_MANIFEST = """
emotions:
  正常: diff/haruka_spr_01.png   # 默认态
  微笑: diff/haruka_spr_03.png   # 眯眼开心
spine: haruka_spr
"""


def test_load_manifest_valid(tmp_path):
    (tmp_path / "emotions.yml").write_text(_VALID_MANIFEST, encoding="utf-8")
    m = load_character_manifest(tmp_path)
    assert m["sprites"]["正常"] == "diff/haruka_spr_01.png"
    assert m["sprites"]["微笑"] == "diff/haruka_spr_03.png"
    assert m["spine"] == "haruka_spr"
    print("    manifest: 合法解析")


def test_load_manifest_missing_or_corrupt(tmp_path):
    assert load_character_manifest(tmp_path)["sprites"] == {}
    (tmp_path / "emotions.yml").write_text("emotions: [坏格式: [", encoding="utf-8")
    m = load_character_manifest(tmp_path)
    assert m["sprites"] == {} and m["spine"] is None
    print("    manifest: 缺失/损坏 → 空, 不崩")


# ----------------------------------------------------------------------------
# 假 assets 树
# ----------------------------------------------------------------------------

def _make_assets(tmp_path):
    root = tmp_path / "assets"
    bg = root / "background"
    for sub, files in {
        "BG_Class": ["BG_ClassRoom.jpg", "BG_ClassRoom_Night.jpg",
                     "BG_ClassRoom2_Night.jpg", "BG_ClassStairs_Sunset.jpg"],
        "BG_Gehenna": ["BG_GehennaCampus_Night.jpg"],
        "BG_Wildhunt": ["BG_WildhuntStreet.jpg"],
        "BG_Other": ["Event_Main_Shop_Bg_852.png"],
    }.items():
        d = bg / sub
        d.mkdir(parents=True)
        for f in files:
            (d / f).write_bytes(b"img")
    (bg / ".py").write_text("import os")  # 脚本残留 → 排除
    # 角色
    ch = root / "illustration" / "igusa_haruka"
    (ch / "diff").mkdir(parents=True)
    for i in range(1, 7):
        (ch / "diff" / f"haruka_spr_0{i}.png").write_bytes(b"png")
    sp = ch / "spine" / "haruka_spr"
    sp.mkdir(parents=True)
    (sp / "haruka_spr.skel").write_bytes(b"x")
    (sp / "haruka_spr.atlas").write_text(_FAKE_ATLAS, encoding="utf-8")
    (sp / "haruka_spr.png").write_bytes(b"x")
    (ch / "emotions.yml").write_text(
        "emotions:\n"
        "  nomal: diff/haruka_spr_01.png\n"
        "  respond: diff/haruka_spr_02.png\n"
        "  smile: diff/haruka_spr_03.png\n"
        "  embarass: diff/haruka_spr_04.png\n"
        "  serious: diff/haruka_spr_05.png\n"
        "  shout: diff/haruka_spr_06.png\n"
        "spine: haruka_spr\n",
        encoding="utf-8",
    )
    # 无 manifest 的角色 → 空
    (root / "illustration" / "no_man").mkdir()
    return root


def _catalog(tmp_path):
    return MediaCatalog(_make_assets(tmp_path))


# ----------------------------------------------------------------------------
# catalog: 背景查询
# ----------------------------------------------------------------------------

def test_background_lookup_default_and_variant(tmp_path):
    c = _catalog(tmp_path)
    assert c.background("class_room").path.name == "BG_ClassRoom.jpg"  # 默认无变体优先
    assert c.background("class_room", "night").path.name == "BG_ClassRoom_Night.jpg"
    assert c.background("gehenna_campus", "night") is not None
    assert c.background("gehenna_campus") is not None  # 无默认版 → 任取其一
    print("    background: 默认版优先 + 变体精确命中")


def test_background_unknown_and_variant_missing(tmp_path):
    c = _catalog(tmp_path)
    assert c.background("does_not_exist") is None
    assert c.background("class_room", "sunset") is None  # 变体不存在 → 宁缺勿错
    print("    background: 未知场景/变体 → None")


def test_background_wildhunt_street_not_variant(tmp_path):
    c = _catalog(tmp_path)
    e = c.background("wildhunt_street")
    assert e is not None and e.variant is None
    print("    background: Street 是场景名, 非变体")


def test_background_scenes_and_variants(tmp_path):
    c = _catalog(tmp_path)
    assert c.background_scenes() == sorted(c.background_scenes())  # 有序
    assert "class_room" in c.background_scenes()
    assert "class_room_2" in c.background_scenes()
    assert c.background_variants("class_room") == ["night"]
    # 脚本残留 .py 不进索引（派生出的空 id 不该出现）
    assert "" not in c.background_scenes()
    print("    background: 场景清单 + 变体清单 + 排除脚本残留")


def test_background_event_png_indexed(tmp_path):
    c = _catalog(tmp_path)
    assert c.background("event_main_shop_bg_852") is not None
    print("    background: event png 也进索引（派生同规则）")


# ----------------------------------------------------------------------------
# catalog: 差分查询
# ----------------------------------------------------------------------------

def test_sprite_lookup(tmp_path):
    c = _catalog(tmp_path)
    s = c.sprite("igusa_haruka", "smile")
    assert s is not None
    assert s.static_path.name == "haruka_spr_03.png"
    assert s.spine is not None and s.spine.regions == ("01_nomal", "02_respond")
    assert c.sprite("igusa_haruka", "unknown") is None
    assert c.sprite("no_man", "smile") is None
    print("    sprite: 情绪命中（静态+spine）/ 未知情绪 / 无 manifest 角色")


def test_sprite_emotions_whitelist(tmp_path):
    c = _catalog(tmp_path)
    assert c.sprite_emotions("igusa_haruka") == [
        "embarass", "nomal", "respond", "serious", "shout", "smile",
    ]
    assert c.sprite_emotions("no_man") == []
    print("    sprite_emotions: 情绪白名单（供 ② prompt/parse）")


def test_has_sprite_and_background(tmp_path):
    c = _catalog(tmp_path)
    assert c.has_sprite("igusa_haruka", "shout")
    assert not c.has_sprite("igusa_haruka", "angry")
    assert c.has_background("class_room")
    assert not c.has_background("class_room", "snow")
    print("    has_sprite / has_background: 布尔辅助")


def test_sprite_lazy_loads_on_first_query(tmp_path):
    root = _make_assets(tmp_path)
    c = MediaCatalog(root)                       # 构造时只扫背景, 不扫角色
    ch = root / "illustration" / "igusa_haruka"
    (ch / "emotions.yml").write_text(             # 构造后改词表
        "emotions:\n  smug: diff/haruka_spr_04.png\n", encoding="utf-8")
    assert c.sprite_emotions("igusa_haruka") == ["smug"]  # 首次 query 才扫 → 读到新 manifest
    print("    sprite: 懒加载——构造后改 manifest, 首次 query 生效")


def test_sprite_static_missing_still_registered(tmp_path):
    root = _make_assets(tmp_path)
    # 改 manifest 指向不存在的文件 → 仍登记, 但 static_path 降级 None
    ch = root / "illustration" / "igusa_haruka"
    (ch / "emotions.yml").write_text(
        "emotions:\n  smile: diff/missing.png\nspine: haruka_spr\n", encoding="utf-8")
    c = MediaCatalog(root)
    s = c.sprite("igusa_haruka", "smile")
    assert s is not None and s.static_path is None and s.spine is not None
    print("    sprite: 静态文件缺失 → 登记但 static None（宁缺勿错）")


def test_media_error_on_missing_root(tmp_path):
    with pytest.raises(MediaError):
        MediaCatalog(tmp_path / "nope")
    print("    MediaCatalog: assets 根缺失 → MediaError")
