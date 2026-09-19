# -*- coding: utf-8 -*-
"""前端背景 URL 的地点解析（C5, 2026-09-19）。

**这条是玩家真正看见背景的那条路**（异步 lane 标出锚点 → 路由附 `place_bg` →
前端段首切）。它此前对表键**恒失配**：`_catalog().background("classroom")` 返回 None
（资产 scene_id 是 `class_room`）→ 锚点静默不切图。

钉四件事:
  ① 表键 → 资产 scene_id → 真 URL（含作者重命名过的条目）
  ② slug 型键（`school_rooftop`）仍走老口径
  ③ 未知名 → None（宁缺勿错, 前端保持上一背景）
  ④ `_resolve_scene` 把 `paragraphs[].place` 变成 `place_bg`
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from webgui.routers.bond import _place_bg_url, _resolve_scene      # noqa: E402


def test_table_keys_resolve_to_real_urls():
    """★ 表键（语义键）→ 资产 scene_id → 真 URL。"""
    cases = {
        "classroom": "BG_ClassRoom.jpg",              # classroom → class_room
        "moderncafe": "BG_ModernCafe.jpg",            # 旧 31 条白名单里没有这个键
        "68office": "BG_KohshinjoRoom.jpg",           # 作者重命名过: files 才对得上
        "view_sky": "BG_View_Sky",                    # 情景图（星空/黄昏）
        "black": "BG_Black.jpg",                      # 写作用词（纯色特效）
    }
    for key, want_part in cases.items():
        url = _place_bg_url(key)
        assert url is not None, f"{key} 没出 URL —— 表键又失配了"
        assert url.startswith("/assets/background/"), url
        assert want_part in url, f"{key} → {url}（期望含 {want_part}）"
    print(f"    表键 → URL: {len(cases)} 条全部命中真文件")


def test_slug_keys_still_work():
    """slug 型键（表键 == 资产键）走老口径, 不受影响。"""
    url = _place_bg_url("school_rooftop")
    assert url and "BG_SchoolRooftop.jpg" in url, url
    print(f"    slug 键: school_rooftop → {url.rsplit('/', 1)[-1]}")


def test_unknown_key_returns_none():
    """未知名 → None（调用方保持上一背景, 静默降级——宁缺勿错）。"""
    for key in ("不存在的键", "nope_room", ""):
        assert _place_bg_url(key) is None, key
    print("    未知名 → None（保持上一背景）")


def test_resolve_scene_attaches_place_bg():
    """★ `_resolve_scene` 把锚点句的 `place` 变成 `place_bg`（前端据此切图）。"""
    scene = {
        "background": None,
        "is_end": False,
        "paragraphs": [
            {"text": "她推开门。", "place": "classroom"},
            {"text": "晚风迎面。", "place": "nope_room"},      # 未知名 → 不附
            {"text": "别的。"},                                  # 无 place → 不附
        ],
    }
    out = _resolve_scene(scene, "igusa_haruka")
    assert out is not None
    paras = out["paragraphs"]
    assert paras[0].get("place_bg", "").endswith("BG_ClassRoom.jpg"), paras[0]
    assert "place_bg" not in paras[1], "未知名不该附 URL（该保持上一背景）"
    assert "place_bg" not in paras[2]
    # 未知名由占位兜底给出展示背景（防纯黑的老逻辑, 与 place_bg 无关）
    assert out.get("background_url"), "缺资产时应有展示兜底"
    print(f"    _resolve_scene: 锚点 place → place_bg "
          f"({paras[0]['place_bg'].rsplit('/', 1)[-1]})")


if __name__ == "__main__":
    test_table_keys_resolve_to_real_urls()
    test_slug_keys_still_work()
    test_unknown_key_returns_none()
    test_resolve_scene_attaches_place_bg()
    print("all place_bg tests passed")
