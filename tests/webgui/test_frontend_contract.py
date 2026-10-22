"""前端 ↔ 后端契约对齐守门（目前只有一条：特效符号表）。

`bond.js` 的 `FX_SYMBOLS` 是"特效名 → 符号 + 颜色"的前端表；特效名的真源在后端
（`tui/effects.py` 的 `_GLOBAL_EFFECTS`，它的**值**就是名字，`webgui/routers/bond.py:198`
把它们写进段落的 `fx`）。两边各写一份、靠注释维持一致，而前端的 `if (!def) return;`
会**静默丢弃**不认识的键：后端加一个特效名，网页上什么都不显示、也不报错。

钉两个方向：
    ① 后端内置表里出现的名字，前端都得有符号
    ② 前端表里不许有后端不产的名字（死符号）

⚠️ 作者可以在 `assets/illustration/{char}/effects.yml` 里加**自定义**特效名 —— 那种前端也不认识，
同样会被静默丢弃。要显示就得同时往 `FX_SYMBOLS` 加一条（名字归后端、符号归前端，这条分工
没法自动化，只能靠这条注释提醒）。
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

from tui.effects import _GLOBAL_EFFECTS  # noqa: E402

_BOND_JS = ROOT / "webgui" / "static" / "js" / "bond.js"
_INDEX_HTML = ROOT / "webgui" / "static" / "index.html"
_DEMO_HTML = ROOT / "webgui" / "static" / "bond-test.html"


def _backend_names() -> set[str]:
    """后端内置特效名（`_GLOBAL_EFFECTS` 的值 = 真源）。"""
    return {name for names in _GLOBAL_EFFECTS.values() for name in names}


def _frontend_symbols() -> set[str]:
    """前端 `FX_SYMBOLS` 的键（从 JS 源码取；按 `sym:` 属性认条目，不依赖缩进）。"""
    src = _BOND_JS.read_text(encoding="utf-8")
    start = src.index("const FX_SYMBOLS = {")
    block = src[start:src.index("\n};", start)]
    keys = set(re.findall(r"([A-Za-z_][\w]*)\s*:\s*\{[^}]*sym:", block))
    assert keys, "没从 bond.js 解析出 FX_SYMBOLS 的键——解析方式要跟着改（别默默放过）"
    return keys


def test_every_backend_fx_has_a_frontend_symbol():
    """① 后端会产出的名字，前端都得画得出来。"""
    missing = sorted(_backend_names() - _frontend_symbols())
    assert not missing, (
        f"`tui/effects.py` 会产出这些特效名，但 `bond.js` 的 FX_SYMBOLS 里没有: {missing}\n"
        "（前端会静默丢弃 —— 网页上看不到特效，也不报错）")


def test_no_dead_frontend_symbols():
    """② 前端表里不该有后端不产的名字。"""
    dead = sorted(_frontend_symbols() - _backend_names())
    assert not dead, (
        f"`bond.js` 的 FX_SYMBOLS 里有后端不产出的名字: {dead}\n"
        "（要么后端表漏了它，要么这是可以删的死符号）")


def _view_bond_ids(path: pathlib.Path) -> set[str]:
    """取 `#view-bond` 那一节里的所有 `id="…"`（VN 视图的 DOM 面）。"""
    src = path.read_text(encoding="utf-8")
    start = src.index('<section id="view-bond"')
    end = src.index("</section>", start)
    return set(re.findall(r'id="([^"]+)"', src[start:end]))


def test_bond_dom_ids_match_between_index_and_demo():
    """③ 演示页的 VN DOM 必须与真页面**同 id**（`bond-test.html` 靠一句注释宣称这件事）。

    `bond.js` 全按 id 取元素, 取不到就是 `null` —— 静默不生效, 而且只在演示页
    看得到（"这个特效在 demo 里没有"）, 真机排查会被带偏。往 VN 视图加元素必须
    两处一起加（换场幕布 `#bond-curtain` 就是一个候选漏点）。
    """
    real, demo = _view_bond_ids(_INDEX_HTML), _view_bond_ids(_DEMO_HTML)
    assert real, "没从 index.html 的 #view-bond 里解析出任何 id —— 解析方式要跟着改"
    assert sorted(real - demo) == [], (
        f"index.html 的 VN 视图有、演示页没有的 id: {sorted(real - demo)}")
    assert sorted(demo - real) == [], (
        f"演示页有、index.html 没有的 id: {sorted(demo - real)}")


if __name__ == "__main__":
    print(f"   后端内置特效名: {sorted(_backend_names())}")
    print(f"   前端符号表键:   {sorted(_frontend_symbols())}")
    test_every_backend_fx_has_a_frontend_symbol()
    test_no_dead_frontend_symbols()
    print("前端契约守门: 全部通过")
