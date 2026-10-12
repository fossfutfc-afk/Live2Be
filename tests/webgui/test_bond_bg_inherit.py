"""板级背景的**章内沿用**（2026-10-08 用户报障"第一个背景永远是默认教室兜底"）。

病因两半:
  ① **只有板首 `switch` 的板带 `place`** ⇒ 其余板的 `place` 是 None ⇒ 从前一律落到
     `_BG_FALLBACK_PRIORITY[0]` = `class_room`（教室）⇒ 整章底色都是教室;
  ② 板**先上屏**、place lane **~1s 后**才解析出地点 ⇒ 首板那一秒也是教室（补切在前端,
     见 `webgui/static/js/bond.js::syncBoardBg`, B 层冒烟覆盖）。

本文件钉 ①（展示层的 `_resolve_scene(inherit_place=…)`）: 走**真表真资产**
（`config/settings/world/place_entities.json` + `assets/`）, 判据 = 取到的是
**咖啡馆那张**而不是教室那张。

运行: python -m pytest tests/webgui/test_bond_bg_inherit.py
"""
import sys
from pathlib import Path

import pytest

from webgui.routers.bond import (  # noqa: E402
    _fallback_bg_url,
    _resolve_scene,
)

CHAR = "igusa_haruka"
#: 真表里的两个键（`place_entities.json`）: 咖啡馆 vs 教室
CAFE = "moderncafe"
CAFE_FILE = "BG_ModernCafe.jpg"
CLASS_FILE = "BG_ClassRoom.jpg"


def _board(**kw) -> dict:
    """一块**没有板级 place** 的板（= 后续板; `background` 恒 'neutral' 占位）。"""
    base = {"paragraphs": [{"speaker": CHAR, "text": "……"}], "background": "neutral"}
    base.update(kw)
    return base


def test_board_without_switch_falls_back_to_classroom():
    """**旧行为的现场**（先钉住, 免得"沿用"改坏了看不出对照）:

    没有 place 的板 → 兜底 = `_BG_FALLBACK_PRIORITY[0]` = 教室。
    """
    fb = _fallback_bg_url()
    assert fb and CLASS_FILE in fb, fb
    r = _resolve_scene(_board(), CHAR)
    assert r["background_url"] == fb
    assert "place_inherited" not in r


def test_board_without_switch_inherits_chapter_place():
    """⭐ 修好之后: 没 switch 的板**沿用本章当前地点**（咖啡馆那张）, 不再掉回教室。"""
    r = _resolve_scene(_board(), CHAR, inherit_place=CAFE)
    assert r["background_url"] and CAFE_FILE in r["background_url"], r
    assert CLASS_FILE not in r["background_url"]
    assert r["place_inherited"] == CAFE          # 留痕: 这张图是"沿用"来的


def test_own_switch_wins_over_inherit():
    """板级自己的地点优先于沿用（别把"沿用"写成"覆盖"）。"""
    r = _resolve_scene(_board(place="classroom"), CHAR, inherit_place=CAFE)
    assert CLASS_FILE in r["background_url"], r
    assert "place_inherited" not in r


def test_own_place_is_not_clobbered_by_placeholder_background():
    """⭐⭐ **主 bug 的守门**（2026-10-08 真机报障的根因）:

    有 `place` 的板, `background` 是 v2 占位 `neutral`（没有 catalog 资产）——
    从前 ① 取到地点图后**继续落到 ②**, 被 `_fallback_bg_url()`（教室）**覆盖**。
    判据: 最终背景必须是**地点那张**。

    变异验证: 把 ① 成功后的 `return` 去掉 → 立刻红（本用例就是为它写的）。
    """
    r = _resolve_scene(_board(place=CAFE), CHAR)
    assert r["background_url"] and CAFE_FILE in r["background_url"], r
    assert CLASS_FILE not in r["background_url"], (
        "地点图被 ② 的兜底覆盖了 —— `_resolve_scene` ① 成功之后必须当场 return")


@pytest.mark.parametrize("bad", ["", "no_such_place_key_xyz"])
def test_unresolvable_inherit_keeps_old_fallback(bad):
    """沿用不到（空串 / 表里没有的键）→ **照旧走兜底**, 绝不炸、也不黑屏。"""
    r = _resolve_scene(_board(), CHAR, inherit_place=bad)
    assert r["background_url"] == _fallback_bg_url()


def test_end_board_does_not_inherit():
    """收尾板**不沿用**: 它的黑屏余韵是官方结束样式, 糊一张地点图回去会破坏它。"""
    r = _resolve_scene(_board(is_end=True), CHAR, inherit_place=CAFE)
    assert not r.get("background_url"), r
