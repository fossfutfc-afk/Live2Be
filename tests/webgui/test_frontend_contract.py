"""前端 ↔ 后端契约对齐守门（特效符号表 / 动作词表 / VN 视图的 DOM id）。

三处都是"后端说名字、前端负责画"，而前端对不认识的名字一律**静默不动**：
后端加一条、前端没跟上，网页上什么都不显示、也不报错 —— 只能靠这里钉。

    ① 情绪符号: 后端 `tui/effects.py::_GLOBAL_EFFECTS` 的值 → 前端 `FX_SYMBOLS`
    ② 角色动作: 后端 `core/bond/actions.py::ACTION_NAMES` → 前端 `ACT_SPECS`
    ③ VN 视图 id: `index.html` ↔ `bond-test.html`（演示页少一个元素 = 只在那页静默失效）

① ② 都是双向的（后端得都能画 / 前端不许有死条目）。

⚠️ 作者可以在 `assets/illustration/{char}/effects.yml` 里加**自定义**特效名 —— 那种前端
也不认识，同样会被静默丢弃。要显示就得同时往 `FX_SYMBOLS` 加一条（名字归后端、符号归
前端，这条分工没法自动化，只能靠这条注释提醒）。

前端两张表都住在 `webgui/static/js/effects.js`（装饰一类一处）。
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]

from core.bond.actions import ACTION_NAMES  # noqa: E402
from tui.effects import _GLOBAL_EFFECTS  # noqa: E402

_EFFECTS_JS = ROOT / "webgui" / "static" / "js" / "effects.js"
_INDEX_HTML = ROOT / "webgui" / "static" / "index.html"
_DEMO_HTML = ROOT / "webgui" / "static" / "bond-test.html"


def _backend_names() -> set[str]:
    """后端内置特效名（`_GLOBAL_EFFECTS` 的值 = 真源）。"""
    return {name for names in _GLOBAL_EFFECTS.values() for name in names}


def _frontend_symbols() -> set[str]:
    """前端 `FX_SYMBOLS` 的键（从 JS 源码取；按 `sym:` 属性认条目，不依赖缩进）。"""
    src = _EFFECTS_JS.read_text(encoding="utf-8")
    start = src.index("const FX_SYMBOLS = {")
    block = src[start:src.index("\n};", start)]
    keys = set(re.findall(r"([A-Za-z_][\w]*)\s*:\s*\{[^}]*sym:", block))
    assert keys, "没从 effects.js 解析出 FX_SYMBOLS 的键——解析方式要跟着改（别默默放过）"
    return keys


def _frontend_actions() -> set[str]:
    """前端 `ACT_SPECS` 的键（**两空格缩进 + `名: {`** —— 单行写法的条目也要认到）。"""
    src = _EFFECTS_JS.read_text(encoding="utf-8")
    start = src.index("export const ACT_SPECS = {")
    block = src[start:src.index("\n};", start)]
    keys = set(re.findall(r"^\s{2}([a-z][a-z0-9]*):\s*\{", block, re.M))
    assert keys, "没从 effects.js 解析出 ACT_SPECS 的键——解析方式要跟着改（别默默放过）"
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


def test_every_action_has_a_frontend_spec():
    """③ 后端能点名的动作，前端都得演得出来。"""
    missing = sorted(ACTION_NAMES - _frontend_actions())
    assert not missing, (
        f"`core/bond/actions.py` 能产出这些动作名，但 `effects.js` 的 ACT_SPECS 里没有: {missing}\n"
        "（前端会静默不动 —— 网页上不会跳，也不报错）")


def test_no_dead_frontend_actions():
    """④ 前端动作表里不该有后端点不出的名字。"""
    dead = sorted(_frontend_actions() - ACTION_NAMES)
    assert not dead, (
        f"`effects.js` 的 ACT_SPECS 里有后端点不出的动作名: {dead}\n"
        "（prompt 词表里没有它 ⇒ 标注永远不会给，白留一份关键帧）")


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
    print(f"   后端动作名:     {sorted(ACTION_NAMES)}")
    print(f"   前端动作表键:   {sorted(_frontend_actions())}")
    test_every_backend_fx_has_a_frontend_symbol()
    test_no_dead_frontend_symbols()
    test_every_action_has_a_frontend_spec()
    test_no_dead_frontend_actions()
    print("前端契约守门: 全部通过")
