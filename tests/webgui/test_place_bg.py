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


def test_missing_asset_is_black_plus_notice():
    """★ 素材缺失 → **黑屏 `black` + 报出**（用户 2026-09-19 裁决）。

    > *"假如发现资源库里没有这张图，就用黑屏 black，且 alert/console.log
    > 素材未找到即可。"*

    此前是**静默换成别的图**（`_fallback_bg_url()` → `class_room`）—— 真机那
    20/20 板"每次 VN 都在显示教室"就是这么来的：看起来正常，其实错了。
    """
    from webgui.routers.bond import _black_bg_url, _place_bg
    black = _black_bg_url()
    assert black and "BG_Black" in black, black
    for key in ("不存在的键", "nope_room", "已被改名的旧键"):
        url, st = _place_bg(key)
        assert (url, st) == (None, "missing"), (key, url, st)
    print(f"    缺失 → 状态 missing; 黑屏占位 = {black.rsplit('/', 1)[-1]}")


def test_resolve_scene_missing_asset_goes_black():
    """板级: **有明确地点但没图** → 黑屏 + `missing_asset`（不再静默兜底）。"""
    scene = {
        "background": "neutral",          # 导演没换（缺资产时会保持）
        "place": "已被改名的旧键",          # 但**地点意图是明确的**
        "is_end": False,
        "paragraphs": [{"text": "她推开门。"}],
    }
    out = _resolve_scene(scene, "igusa_haruka")
    assert out["missing_asset"] == {"key": "已被改名的旧键"}, out.get("missing_asset")
    assert "BG_Black" in (out.get("background_url") or ""), out.get("background_url")
    print(f"    板级缺失 → missing_asset={out['missing_asset']} + 黑屏")


def test_resolve_scene_attaches_place_bg():
    """★ `_resolve_scene` 把锚点句的 `place` 变成 `place_bg`（前端据此切图）。"""
    scene = {
        "background": None,
        "is_end": False,
        "paragraphs": [
            {"text": "她推开门。", "place": "classroom"},
            {"text": "晚风迎面。", "place": "nope_room"},      # 缺素材 → 黑屏 + 报出
            {"text": "别的。"},                                  # 无 place → 不附
        ],
    }
    out = _resolve_scene(scene, "igusa_haruka")
    assert out is not None
    paras = out["paragraphs"]
    assert paras[0].get("place_bg", "").endswith("BG_ClassRoom.jpg"), paras[0]
    assert "BG_Black" in paras[1].get("place_bg", ""), paras[1]
    assert paras[1]["missing_asset"] == {"key": "nope_room"}, paras[1]
    assert "place_bg" not in paras[2], "没地点就不该附 URL"
    # 无地点意图时仍有展示兜底（防开场纯黑, 与 missing_asset 是两件事）
    assert out.get("background_url"), "缺地点意图时应有展示兜底"
    print(f"    _resolve_scene: 锚点 place → place_bg "
          f"({paras[0]['place_bg'].rsplit('/', 1)[-1]}) + 缺素材转黑屏")


if __name__ == "__main__":
    test_table_keys_resolve_to_real_urls()
    test_slug_keys_still_work()
    test_missing_asset_is_black_plus_notice()
    test_resolve_scene_missing_asset_goes_black()
    test_resolve_scene_attaches_place_bg()
    print("all place_bg tests passed")
