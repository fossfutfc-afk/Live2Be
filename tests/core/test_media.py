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

from core.media import (
    MediaCatalog,
    MediaError,
    assets_root,
    build_emotion_injection,
    load_emotion_lexicon,
    load_place_lexicon,
    render_emotion_scale,
)
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
  nomal: diff/haruka_spr_01.png   # 默认态
  smile: diff/haruka_spr_03.png   # 眯眼开心
spine: haruka_spr
"""


def test_load_manifest_valid(tmp_path):
    (tmp_path / "emotions.yml").write_text(_VALID_MANIFEST, encoding="utf-8")
    m = load_character_manifest(tmp_path)
    assert m["sprites"]["nomal"] == "diff/haruka_spr_01.png"
    assert m["sprites"]["smile"] == "diff/haruka_spr_03.png"
    assert m["spine"] == "haruka_spr"
    print("    manifest: 合法解析")


def test_load_manifest_missing_or_corrupt(tmp_path):
    assert load_character_manifest(tmp_path)["sprites"] == {}
    (tmp_path / "emotions.yml").write_text("emotions: [坏格式: [", encoding="utf-8")
    m = load_character_manifest(tmp_path)
    assert m["sprites"] == {} and m["spine"] is None
    print("    manifest: 缺失/损坏 → 空, 不崩")


# ----------------------------------------------------------------------------
# manifest 双投影（2026-08-28）: 资源 ID ↔ diff 路径 + spine 动画名
# ----------------------------------------------------------------------------

def test_manifest_dual_projection_resource_id(tmp_path):
    """新格式: 值 = 资源 ID（无 / 无扩展名）→ diff 模板拼接 + 动画名 = ID。"""
    (tmp_path / "emotions.yml").write_text(
        "spine: haruka_spr\n"
        "emotions:\n"
        "  nomal: 01\n"
        "  giggle: 09\n"
        "  pensive: 99\n"
        "  custom: custom/my_own.png\n",   # 自绘图: 显式路径形态
        encoding="utf-8",
    )
    m = load_character_manifest(tmp_path)
    assert m["sprites"]["nomal"] == "diff/haruka_spr_01.png"
    assert m["sprites"]["giggle"] == "diff/haruka_spr_09.png"
    assert m["sprites"]["pensive"] == "diff/haruka_spr_99.png"
    assert m["animations"]["nomal"] == "01"
    assert m["animations"]["giggle"] == "09"
    assert m["animations"]["pensive"] == "99"
    # 显式路径: 原样 + 无 spine 投影（纯静态图）
    assert m["sprites"]["custom"] == "custom/my_own.png"
    assert m["animations"]["custom"] is None
    print("    manifest: 资源 ID 双投影（diff 拼接 + 动画名）")


def test_manifest_dual_projection_yaml_octal(tmp_path):
    """YAML 1.1 八进制坑: "01"→int 1 前导零丢失——必须补零回 2 位。"""
    (tmp_path / "emotions.yml").write_text(
        "spine: haruka_spr\n"
        "emotions:\n"
        "  nomal: 01\n"
        "  smile: 03\n"
        "  shout_2: 11\n",
        encoding="utf-8",
    )
    m = load_character_manifest(tmp_path)
    assert m["sprites"]["nomal"] == "diff/haruka_spr_01.png", m["sprites"]
    assert m["sprites"]["smile"] == "diff/haruka_spr_03.png"
    assert m["sprites"]["shout_2"] == "diff/haruka_spr_11.png"
    assert m["animations"]["nomal"] == "01"
    print("    manifest: YAML 八进制补零（01→'01'）")


def test_manifest_dual_projection_old_path(tmp_path):
    """旧格式兼容: 值 = diff 路径 → 原样 + stem 去前缀推导动画名。"""
    (tmp_path / "emotions.yml").write_text(
        "spine: haruka_spr\n"
        "emotions:\n"
        "  nomal: diff/haruka_spr_01.png\n"
        "  custom: custom/my_own.png\n",   # 无前缀 → 动画 None（纯静态图）
        encoding="utf-8",
    )
    m = load_character_manifest(tmp_path)
    assert m["sprites"]["nomal"] == "diff/haruka_spr_01.png"
    assert m["animations"]["nomal"] == "01"
    assert m["sprites"]["custom"] == "custom/my_own.png"
    assert m["animations"]["custom"] is None
    print("    manifest: 旧路径格式兼容（stem 推导动画名）")


def test_manifest_dual_projection_no_spine(tmp_path):
    """无 spine 字段（纯静态图角色）: 资源 ID 形态无模板可拼 → 原样 + 无动画。"""
    (tmp_path / "emotions.yml").write_text(
        "emotions:\n"
        "  nomal: 01\n"
        "  smile: diff/aru_spr_03.png\n",
        encoding="utf-8",
    )
    m = load_character_manifest(tmp_path)
    assert m["sprites"]["nomal"] == "01"      # 无 spine → 保留 ID（无资源, 渲染端静默）
    assert m["animations"]["nomal"] is None
    assert m["animations"]["smile"] is None   # 无 spine → 路径形态也不推导
    print("    manifest: 无 spine → 无模板/无动画（纯静态图降级）")


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
    # 角色（板块结构 2026-08-28: 每外观一个自包含目录 {char}/{outfit}/, 缺省 default）
    ch = root / "illustration" / "igusa_haruka" / "default"
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
        "  embarrass: diff/haruka_spr_04.png\n"
        "  serious: diff/haruka_spr_05.png\n"
        "  shout: diff/haruka_spr_06.png\n"
        "spine: haruka_spr\n",
        encoding="utf-8",
    )
    # 附加外观（板块: 独立目录 + 自己的 emotions.yml）
    extra = root / "illustration" / "igusa_haruka" / "newyear"
    (extra / "spine" / "ny_spr").mkdir(parents=True)
    (extra / "spine" / "ny_spr" / "ny_spr.skel").write_bytes(b"x")
    (extra / "spine" / "ny_spr" / "ny_spr.atlas").write_text(_FAKE_ATLAS, encoding="utf-8")
    (extra / "spine" / "ny_spr" / "ny_spr.png").write_bytes(b"x")
    (extra / "emotions.yml").write_text(
        "spine: ny_spr\n"
        "emotions:\n"
        "  nomal: 01\n"
        "  smile: 03\n",
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
    # 脚本残留 .py 不进索引（派生出的空 id 不该出现）
    assert "" not in c.background_scenes()
    print("    background: 场景清单 + 变体清单 + 排除脚本残留")


def test_background_event_png_indexed(tmp_path):
    c = _catalog(tmp_path)
    assert c.background("event_main_shop_bg_852") is not None
    print("    background: event png 也进索引（派生同规则）")


# ----------------------------------------------------------------------------
# PL0（2026-09-19）: 递归 + 剪枝 —— 支持 SDIR/DIR 两级组织, 排掉缓存目录
# ----------------------------------------------------------------------------

def _make_layout_assets(tmp_path):
    """一棵"既有旧布局又有新布局又有缓存"的假资产树。"""
    bg = tmp_path / "assets" / "background"
    # ① 现行布局: BG_*/BG_*.jpg
    (bg / "BG_Class").mkdir(parents=True)
    (bg / "BG_Class" / "BG_ClassRoom.jpg").write_bytes(b"real")
    # ② 工作区导出的两级布局: SDIR_*/DIR_*/BG_*.jpg（用户同步进来的形态）
    (bg / "SDIR_Inner" / "DIR_Class").mkdir(parents=True)
    (bg / "SDIR_Inner" / "DIR_Class" / "BG_ClassStairs.jpg").write_bytes(b"real")
    # ③ 工作台缩略图缓存 —— **不该进索引**（真机曾把 239 张扫进来）
    (bg / ".thumbs" / "BG_Class").mkdir(parents=True)
    (bg / ".thumbs" / "BG_Class" / "BG_ClassRoom.jpg").write_bytes(b"thumb")
    # ④ __pycache__ / 作者预留的 _unused/ —— 同样排除
    (bg / "__pycache__").mkdir(parents=True)
    (bg / "__pycache__" / "BG_Junk.jpg").write_bytes(b"junk")
    (bg / "_unused" / "BG_Old").mkdir(parents=True)
    (bg / "_unused" / "BG_Old" / "BG_OldThing.jpg").write_bytes(b"unused")
    return tmp_path / "assets"


def test_background_scan_recurses_sdir_dir_layout(tmp_path):
    """★ 两级组织（`SDIR_*/DIR_*`）照样扫得到 —— scene_id 由**文件名**派生, 与层级无关。"""
    c = MediaCatalog(_make_layout_assets(tmp_path))
    scenes = c.background_scenes()
    assert "class_room" in scenes and "class_stairs" in scenes, scenes
    # 新布局里那条真的指向 SDIR/DIR 路径
    p = c.background("class_stairs").path
    assert p.parent.name == "DIR_Class" and p.parent.parent.name == "SDIR_Inner", p
    print(f"    PL0: SDIR/DIR 两级可扫 → {sorted(scenes)}")


def test_background_scan_skips_cache_dirs(tmp_path):
    """★ **点/下划线开头的目录不进索引**（`.thumbs` 缩略图 / `__pycache__` / `_unused`）。

    真机实测: 改前 `rglob("*")` 会捞 **1333** 张（1094 真图 + 239 缩略图）,
    缩略图全部进了 `background_scenes()`; 改后只捞 **1094**。
    """
    c = MediaCatalog(_make_layout_assets(tmp_path))
    scenes = c.background_scenes()
    assert scenes == ["class_room", "class_stairs"], scenes
    # 首选图必须是真图, 不是 `.thumbs/` 里的缩略图（同 scene_id、同 variant=None）
    got = c.background("class_room").path
    assert ".thumbs" not in got.parts, got
    assert got.read_bytes() == b"real", "拿到缩略图了"
    print(f"    PL0: 缓存目录被剪掉; class_room → {got.parent.name}/{got.name}")


def test_background_dirs_apis_are_gone(tmp_path):
    """★ `background_dirs()` / `background_scenes_in_dir()` 已删（零消费方 + 换组织后失效）。

    它们是"② 导演背景分层选目录"时代的 API。留着的话, 目录名一变就成了**说谎的接口**
    （"有哪些目录"会答出 `SDIR_*`, 而调用方以为拿到的是 `BG_*`）。
    """
    c = MediaCatalog(_make_layout_assets(tmp_path))
    for gone in ("background_dirs", "background_scenes_in_dir"):
        assert not hasattr(c, gone), f"{gone} 该删掉了"
    print("    PL0: background_dirs / background_scenes_in_dir 已删（零消费方）")


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
        "embarrass", "nomal", "respond", "serious", "shout", "smile",
    ]
    assert c.sprite_emotions("no_man") == []
    print("    sprite_emotions: 情绪白名单（供 ② prompt/parse）")


def test_has_sprite_and_background(tmp_path):
    """（2026-09-21 删主体）只保留"消费面不存在即不该有 API"的守门。

    `has_sprite`/`has_background`/`background_variants` 三个布尔/清单辅助
    全仓零消费者（原断言只验证它们自己），已随 C 类对称性访问器一并删除。
    """
    c = _catalog(tmp_path)
    assert not hasattr(c, "has_sprite") and not hasattr(c, "has_background")
    assert not hasattr(c, "background_variants")
    print("    catalog: 零消费者的布尔/清单辅助已删（字段不许无声回来）")


def test_sprite_outfit_parallel_dirs(tmp_path):
    """板块结构（2026-08-28）: 外观 = 独立目录; default 缺省, 附加外观按 id 查。"""
    c = _catalog(tmp_path)
    # default 缺省
    s = c.sprite("igusa_haruka", "nomal")
    assert s is not None and s.spine.name == "haruka_spr"
    # 附加外观 newyear（资源 ID 双投影: diff/ny_spr_01.png 不存在 → static None, spine 有）
    s2 = c.sprite("igusa_haruka", "nomal", outfit="newyear")
    assert s2 is not None
    assert s2.spine is not None and s2.spine.name == "ny_spr"
    assert s2.anim == "01"
    assert s2.static_path is None            # 变体无 diff 图 → 播放器走 spine
    assert c.sprite("igusa_haruka", "giggle", outfit="newyear") is None  # 未声明键
    assert c.sprite_emotions("igusa_haruka", "newyear") == ["nomal", "smile"]
    # 不存在的外观 → 空（宁缺勿错）
    assert c.sprite("igusa_haruka", "nomal", outfit="nope") is None
    print("    sprite: 板块并行目录（default 缺省 / newyear 独立 / 未知外观空）")


def test_sprite_lazy_loads_on_first_query(tmp_path):
    root = _make_assets(tmp_path)
    c = MediaCatalog(root)                       # 构造时只扫背景, 不扫角色
    ch = root / "illustration" / "igusa_haruka" / "default"
    (ch / "emotions.yml").write_text(             # 构造后改词表
        "emotions:\n  smug: diff/haruka_spr_04.png\n", encoding="utf-8")
    assert c.sprite_emotions("igusa_haruka") == ["smug"]  # 首次 query 才扫 → 读到新 manifest
    print("    sprite: 懒加载——构造后改 manifest, 首次 query 生效")


def test_sprite_static_missing_still_registered(tmp_path):
    root = _make_assets(tmp_path)
    # 改 manifest 指向不存在的文件 → 仍登记, 但 static_path 降级 None
    ch = root / "illustration" / "igusa_haruka" / "default"
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


# ----------------------------------------------------------------------------
# emotion_lexicon: emotions.yml 逐行解析（键 + 示范注释 + eg[键] 例句）→ 注入文本
# ----------------------------------------------------------------------------

_LEXICON_YML = """# 情绪词表
emotions:
  nomal: diff/haruka_spr_00.png   # 默认态
  eyes_closed: diff/haruka_spr_10.png  # 闭眼认错
  # eg[eyes_closed]: 对不起...我又做错了...
  shout_2: diff/haruka_spr_11.png # 坚定喊话
  # eg[shout_2]: 老师说什么就是什么!
  # eg[幽灵键]: 应被忽略（键不存在）
"""


def test_lexicon_parses_keys_comment_and_eg(tmp_path):
    ch = tmp_path / "char"
    ch.mkdir()
    (ch / "emotions.yml").write_text(_LEXICON_YML, encoding="utf-8")
    lex = load_emotion_lexicon(ch)
    assert set(lex) == {"nomal", "eyes_closed", "shout_2"}, set(lex)
    assert lex["nomal"]["path"] == "diff/haruka_spr_00.png"
    assert lex["nomal"]["comment"] == "默认态"
    # eg[键名] 显式归键（不依赖位置）; 幽灵键忽略
    assert lex["eyes_closed"]["eg"] == "对不起...我又做错了..."
    assert lex["shout_2"]["eg"] == "老师说什么就是什么!"
    assert "幽灵键" not in lex
    print("    lexicon: 键/路径/注释/eg[键] 归属（eg 不依赖紧跟）")


def test_lexicon_missing_or_corrupt(tmp_path):
    assert load_emotion_lexicon(tmp_path) == {}
    ch = tmp_path / "c"
    ch.mkdir()
    (ch / "emotions.yml").write_text("emotions: [坏格式: [", encoding="utf-8")
    assert load_emotion_lexicon(ch) == {}
    print("    lexicon: 缺失/损坏 → {}（宁缺勿错）")


def test_emotion_injection_build(tmp_path):
    ch = tmp_path / "char"
    ch.mkdir()
    (ch / "emotions.yml").write_text(_LEXICON_YML, encoding="utf-8")
    inj = build_emotion_injection(ch)
    assert "【表情标注词表】" in inj and "词表外的情绪不要标" in inj
    assert "nomal: 默认态" in inj
    assert "eg: 老师说什么就是什么!" in inj
    # 无词表 → 空串（调用方跳过注入）
    assert build_emotion_injection(tmp_path / "nope") == ""
    print("    injection: 注入文本含键+示范+eg; 无词表 → 空串")


# ---------------------------------------------------------------------------
# render_emotion_scale —— digest Round A 的"只给出现的键"（§3.3.2, 2026-09-13）
# ---------------------------------------------------------------------------

def test_emotion_scale_only_given_keys(tmp_path):
    """★ 核心不变量: **只列传入的键**——全词表对这个段是噪声, 还会诱发凑强度。"""
    ch = tmp_path / "char"
    ch.mkdir()
    (ch / "emotions.yml").write_text(_LEXICON_YML, encoding="utf-8")
    lex = load_emotion_lexicon(ch)
    assert len(lex) >= 3, "夹具词表应该有多于 3 个键"
    keys = list(lex)[:2]
    scale = render_emotion_scale(lex, keys)
    assert "【本段情绪标尺】" in scale
    for k in keys:
        assert f"  {k}:" in scale, f"传入的键 {k} 未渲染"
    for k in list(lex)[2:]:
        assert f"  {k}:" not in scale, f"未传入的键 {k} 被注入了"
    print(f"    scale: 只渲染传入的 {len(keys)} 键（词表共 {len(lex)} 键）")


def test_emotion_scale_empty_and_unknown(tmp_path):
    ch = tmp_path / "char"
    ch.mkdir()
    (ch / "emotions.yml").write_text(_LEXICON_YML, encoding="utf-8")
    lex = load_emotion_lexicon(ch)
    assert render_emotion_scale(lex, []) == ""
    assert render_emotion_scale({}, ["smile"]) == ""
    assert render_emotion_scale(lex, [None, "", 3]) == ""
    # 键不在词表里**也照样列**（保持完整, 不静默丢）——只有键名, 无注释
    scale = render_emotion_scale(lex, ["not_a_key"])
    assert "not_a_key（作者未写注释）" in scale
    print("    scale: 空输入 → 空串; 词表外的键照样列（不静默丢）")


def test_emotion_scale_order_and_eg(tmp_path):
    ch = tmp_path / "char"
    ch.mkdir()
    (ch / "emotions.yml").write_text(_LEXICON_YML, encoding="utf-8")
    lex = load_emotion_lexicon(ch)
    # 按传入顺序, 且重复键去重
    keys = list(lex)
    scale = render_emotion_scale(lex, keys + keys)
    body = [ln for ln in scale.splitlines()[1:] if ln.strip()]
    assert len(body) == len(keys), f"重复键未去重: {len(body)} vs {len(keys)}"
    assert "eg:" in scale, "有 eg 的键应带例句"
    print("    scale: 保持传入顺序 + 去重 + 带 eg 例句")


def test_assets_root_resolves():
    """assets_root() 是唯一解析点（bond_story 与 digest 注入共用）。"""
    r = assets_root()
    assert r.name == "assets"
    assert (r / "illustration").is_dir()
    print(f"    assets_root: {r}")


def test_place_lexicon_from_whitelist():
    # 真实 _director_whitelist.json 的 common_scenes（31 条裸 slug）—— **降级兜底**
    places = load_place_lexicon()
    assert places and "class_room" in places and "ramen_ya" in places
    print(f"    place: 兜底键集 {len(places)} 条（来自 _director_whitelist.common_scenes）")


def test_place_injection_api_is_gone():
    """★ PL4（2026-09-19）删掉的 API 不许回来。

    `build_place_injection` 是"主 LLM 只从词表里选 place"时代的产物: 记录流 v2 +
    "主 LLM 零内容词表"裁决之后它**生产零调用**, 只有本测试在读它。
    """
    import core.media as media
    from core.media import emotion_lexicon as el
    assert not hasattr(el, "build_place_injection"), "已删的注入 API 又回来了"
    assert "build_place_injection" not in media.__all__
    print("    place: build_place_injection 已删（生产零调用）且不在导出面")
