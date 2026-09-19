# -*- coding: utf-8 -*-
"""`place_regions` 单测（T16）——剧情地理词表 + 盒B 的【世界区域】块。

region 是**两根轴里唯一现在就可靠的那根**（另一根 `place` 资产键在同键不同义
问题上还有未决，见 TODO）。所以这里钉三件事:
  ① 归一化正确（别名/主名 → `zh`；长别名优先）
  ② 哨兵纪律（未命中 → `""`，**绝不返回原文**）
  ③ 缺/坏文件 → 空表 + 降级，**绝不抛**（注入块随之缺席）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.parsing.place_regions import (                       # noqa: E402
    DEFAULT_REGIONS_PATH,
    load_regions,
)


def test_load_real_regions_yml():
    """真机词表读得出来（21 条, 顺序 = yml 顺序）。"""
    assert DEFAULT_REGIONS_PATH.is_file(), DEFAULT_REGIONS_PATH
    t = load_regions()
    names = t.names()
    assert len(names) >= 20, names
    assert names[0] == "格黑娜学院" and "夏莱" in names and "阿拜多斯高级中学" in names
    assert bool(t) is True
    print(f"    regions.yml: {len(names)} 条 → {names[:3]} …")


def test_normalize_alias_to_zh():
    """★ 别名/别译 → 官方中文主名（这就是"防 region 因译名裂开"的那一步）。"""
    t = load_regions()
    cases = {
        "阿拜多斯": "阿拜多斯高级中学",          # 短名 → 主名
        "阿比多斯": "阿拜多斯高级中学",          # 别译
        "Abydos": "阿拜多斯高级中学",            # latin
        "歌赫娜": "格黑娜学院",                  # 社区译名
        "Gehenna": "格黑娜学院",
        "沙勒": "夏莱",
        "千禧年": "千年科技学院",
        "深夜的阿拜多斯街道": "阿拜多斯高级中学",   # switch 地点话（子串命中）
        "格黑娜的教室": "格黑娜学院",
    }
    for raw, want in cases.items():
        got = t.normalize(raw)
        assert got == want, f"{raw!r} → {got!r}（期望 {want!r}）"
    print(f"    normalize: {len(cases)} 条别名/别译全部归一到主名")


def test_normalize_long_alias_first():
    """长别名优先——`千年科技学院` 不被 `千年` 截胡（两者同 zh, 但顺序要确定）。"""
    t = load_regions()
    assert t.normalize("千年科技学院") == "千年科技学院"
    assert t.normalize("千年") == "千年科技学院"
    # 短词误命中的已知风险（文档已记）: "一千年" 会被 `千年` 命中 —— 这是接受的行为,
    # 因为它只影响派生字段的召回分组, 不进 LLM 上下文
    assert t.normalize("一千年后的世界") == "千年科技学院"
    print("    normalize: 长别名优先（短词误命中是已知且已记录的边界）")


def test_normalize_sentinel_never_returns_raw():
    """★ 哨兵纪律: 未命中 → `""`（**未知**）, 绝不返回原文——原文不是 region。"""
    t = load_regions()
    for raw in ("深夜的杂草屋", "街角的咖啡馆，靠窗的位子", "学校天台", "", "   ", None):
        assert t.normalize(raw) == "", raw
    print("    normalize: 未命中 → ""（绝不把原文冒充 region）")


def test_load_regions_missing_or_broken_degrades():
    """**绝不抛**: 缺文件 / 坏 YAML / 结构不符 → 空表（块随之缺席, 解析返回 ""）。"""
    t = load_regions(ROOT / ".testtmp" / "__no_such_regions__.yml")
    assert t.names() == [] and not t
    assert t.normalize("阿拜多斯") == ""
    bad = ROOT / ".testtmp" / "regions_broken.yml"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("regions: [不是 dict, 42]\n", encoding="utf-8")
    assert load_regions(bad).names() == []
    bad.write_text("别的键: 1\n", encoding="utf-8")
    assert load_regions(bad).names() == []
    bad.write_text("regions: [[unclosed\n", encoding="utf-8")     # YAML 语法错
    assert load_regions(bad).names() == []
    print("    load_regions: 缺/坏/结构不符 → 空表（不抛; 块缺席）")


def test_place_world_block_and_box():
    """盒B 的【世界区域】块; `place_palette` 已退役。"""
    from core.promptkit.box import DOMAIN_BOXES
    from core.promptkit.blocks import BlockContext, render_block
    assert "place_palette" not in DOMAIN_BOXES["bond"], "旧菜单块未退出盒B"
    # PL2（2026-09-19）: `bond_shots`（镜头与手法）插在 rules_bond 与 schema 之间
    # ⇒ place_world 从 index 7 挪到 8 —— 断言按"位置关系"写, 免得再加块又红
    boxes = DOMAIN_BOXES["bond"]
    assert boxes.index("place_world") > boxes.index("schema"), boxes
    assert boxes[boxes.index("rules_bond") + 1] == "bond_shots", boxes
    text = render_block("place_world", BlockContext())
    assert text and text.startswith("【世界区域】")
    assert "格黑娜学院" in text and "夏莱" in text
    # 不给资产键（这正是本块存在的理由: 世界设定 ≠ 可选空间）
    for slug in ("school_rooftop", "class_room", "onsen", "ramen_ya"):
        assert slug not in text, f"世界区域块不该出现资产键 {slug}"
    # 词表缺失 → 块缺席（条件块, 不占位）
    assert render_block("place_world",
                        BlockContext(regions_path="/nope/regions.yml")) is None
    print(f"    box.B: place_world 在第 {boxes.index('place_world')} 块（世界区域）, "
          f"无资产键; 缺表 → 缺席")


if __name__ == "__main__":
    test_load_real_regions_yml()
    test_normalize_alias_to_zh()
    test_normalize_long_alias_first()
    test_normalize_sentinel_never_returns_raw()
    test_load_regions_missing_or_broken_degrades()
    test_place_world_block_and_box()
    print("all place_regions tests passed")
