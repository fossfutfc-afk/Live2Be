"""守门: **包之间的私有名访问**（2026-10-23）—— 让"接口"从习惯变成可执行规则。

## 为什么要有这条（和 `test_import_direction.py` 是两件事）

`test_import_direction.py` 管**方向**: 谁能 import 谁。它管不了**面**:
`webgui/bond` 直接读 `vn._history` / `engine._session_id` —— 方向完全合法，但那是
"两个模块共享同一个对象的内部"，任何一方改字段都会在另一方静默失效。

建这条守门时的实测: `BondStoryEngine` 对外 12 个公开名，而壳与调试入口直接读引擎/板上的
**13 个私有名**（按"文件 + 名字"去重 = 24 个访问点）。这些不是疏忽 —— **此前没有任何规则禁止过**。

## 三条规则

1. **跨包 import 私有名**: `from core.x import _y`（x 不属于当前包）⇒ 违规。
   私有名是模块自己的实现细节；要跨包用，就该在门面上给它一个公开名。
2. **跨包读模块的私有名**: `bond._state`（`bond` 是 `webgui.bond` 这个**模块**的别名）
   ⇒ 违规。模块别名下的私有名是"私有的门面"，同样不该被外面当接口。
3. **跨包读对象的私有成员**: `vn._pending_boards` ⇒ 违规。
   归属不靠类型推断，靠**声明处**反推: `self._x = …` / 类字段 `_x: T` / `def _x` /
   模块级 `_x = …` 出现在哪个包，那个包就是它的归属。访问点所在包 ∉ 归属包 ⇒ 违规。
   多归属（两个包都声明了同名私有名）照判: 只要访问包不在归属集合里就是违规。

## 白名单纪律

`_IMPORT_DEBT` / `_ATTR_DEBT` 每一条都是**既存违规 + 一句归宿**;
`test_debt_tables_are_not_stale` 反向检查"表是不是已经过期"—— 收口完就该删条目。
**只许缩短**: 新代码不许往表里加，修法是在拥有方加公开的读写口。

## 已知盲区（写下来，免得以后以为它管得比实际宽）

- **动态属性读不到**: `getattr(x, "_foo")` 不经过 AST 属性节点。`BondScene` 的
  `_place_done` / `_call_id` / `_from_draft` 之所以能被判到，是因为它们已被显式声明成
  字段；没声明的那天，读它们的地方会从表里静默消失。
- **同包不管**: `webgui/bond/lanes.py` 读 `BondState._anno_queue` 是同包内部分工。
- **只扫七个源码包**: `tests/` 与 `experiments/` 不扫（它们本来就该伸进去看内部）。

运行: python -m pytest tests/core/test_interface_guard.py
"""
from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

#: 被扫描的包（与 `test_import_direction.py` 同一份名单）
PKGS = ("contract", "infra", "llm", "core", "tui", "webgui", "cli")

#: 接收者是这些名字时跳过 —— stdlib 模块/常用局部名，不属于本项目
_EXTERNAL = frozenset({
    "sys", "os", "re", "json", "logging", "time", "math", "datetime", "itertools",
    "threading", "queue", "random", "textwrap", "subprocess", "shutil", "typing",
    "dataclasses", "enum", "functools", "collections", "asyncio", "urllib",
    "hashlib", "socket", "pathlib", "Path", "logger",
})

#: 跨包 import 私有名的既存债务: `文件:名字` → 归宿。
#: 8 处全是同一件事: **公开接缝的名字还带着下划线**。修法是一次命名统一
#: （`core/text.py` 的四件"公开 API" + `core/director/wiring.py` 的两个接线函数），
#: 不是逐处绕开 —— 所以先记账。
_IMPORT_DEBT: dict[str, str] = {
    "cli/vn_cli.py:_build_director": "wiring 的公开接缝，名字待改成 build_director",
    "cli/vn_cli.py:_trigger_title": "wiring 的公开接缝，名字待改成 trigger_title",
    "webgui/bond/__init__.py:_build_director": "门面再导出（同一条命名债）",
    "webgui/bond/__init__.py:_trigger_title": "门面再导出（同一条命名债）",
    "webgui/bond/entry.py:_build_director": "wiring 的公开接缝（同一条命名债）",
    "webgui/bond/entry.py:_trigger_title": "wiring 的公开接缝（同一条命名债）",
    "webgui/bond/replay.py:_trigger_title": "wiring 的公开接缝（同一条命名债）",
    "webgui/chat.py:_strip_action_brackets": "core/text.py 的公开 API 带着下划线（同一条命名债）",
}

#: 每个"被跨包读的私有名"归到哪个归宿 —— **收口的方向**，一条一句。
_ATTR_HOME: dict[str, str] = {
    "_history": "读引擎历史 → 等 snapshot()/公开的 history 出口",
    "_pending_boards": "读引擎待发队列 → 等 feed() 的返回值",
    "_in_memorial": "读纪念窗口活标志 → 等公开属性",
    "_last_payload": "读上一轮 payload → 等公开访问器",
    "_lexicon_keys": "读标注词表键 → 等 Annotator 的注入面",
    "_place_keys": "读地点键表 → 等 Annotator 的注入面",
    "_place_done": "板上运行期标记 → 等公开读写口（已声明成字段, 先记债）",
    "_from_draft": "板上运行期标记 → 等公开读写口",
    "_session_id": "读会话 id → 等公开属性",
    "_store": "读引擎绑定的 store → 等公开属性",
    "_memorial_image_prompt": "调生图 prompt 构造 → 等公开方法",
    "_current_char": "读当前角色 → 等现成的 current_character 属性",
    "_inject_brain": "读注入段 → 等公开属性",
}

#: **既存访问点**（文件, 私有名）—— 表只许缩短: 收口一处就删一行,
#: 删漏了 `test_debt_tables_are_not_stale` 会红。
_ATTR_SITES: tuple[tuple[str, str], ...] = (
    ("cli/main.py", "_store"),
    ("cli/vn_cli.py", "_history"),
    ("cli/vn_cli.py", "_memorial_image_prompt"),
    ("cli/vn_cli.py", "_session_id"),
    ("cli/vn_cli.py", "_store"),
    ("webgui/bond/api.py", "_history"),
    ("webgui/bond/api.py", "_in_memorial"),
    ("webgui/bond/api.py", "_place_done"),
    ("webgui/bond/entry.py", "_history"),
    ("webgui/bond/entry.py", "_in_memorial"),
    ("webgui/bond/entry.py", "_last_payload"),
    ("webgui/bond/entry.py", "_pending_boards"),
    ("webgui/bond/entry.py", "_place_done"),
    ("webgui/bond/lanes.py", "_lexicon_keys"),
    ("webgui/bond/lanes.py", "_place_done"),
    ("webgui/bond/lanes.py", "_place_keys"),
    ("webgui/bond/pregen.py", "_in_memorial"),
    ("webgui/bond/pregen.py", "_pending_boards"),
    ("webgui/bond/stores.py", "_from_draft"),
    ("webgui/bond/stores.py", "_pending_boards"),
    ("webgui/bond/watchdog.py", "_place_done"),
    ("webgui/chat.py", "_current_char"),
    ("webgui/chat.py", "_inject_brain"),
    ("webgui/chat.py", "_session_id"),
)

_ATTR_DEBT: dict[str, str] = {f"{f}:.{a}": _ATTR_HOME[a] for f, a in _ATTR_SITES}


def _files(root: pathlib.Path, pkgs: tuple[str, ...]) -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for pkg in pkgs:
        out.extend(sorted((root / pkg).rglob("*.py")))
    return [p for p in out if "__pycache__" not in p.parts]


def _pkg_of(path: pathlib.Path, root: pathlib.Path) -> str:
    return path.relative_to(root).parts[0]


def _is_private(name: str) -> bool:
    return name.startswith("_") and not name.startswith("__")


def _declared_owners(trees: dict[pathlib.Path, ast.AST],
                     root: pathlib.Path) -> dict[str, set[str]]:
    """私有名 → 声明它的包集合（`self._x =` / 类字段 `_x: T` / `def _x` / 模块级 `_x =`）。"""
    owners: dict[str, set[str]] = {}

    def note(name: str, path: pathlib.Path) -> None:
        if _is_private(name):
            owners.setdefault(name, set()).add(_pkg_of(path, root))

    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                note(node.name, path)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        note(target.id, path)                     # 模块级常量
                    elif isinstance(target, ast.Attribute) and isinstance(
                            target.value, ast.Name) and target.value.id == "self":
                        note(target.attr, path)                   # self._x = …
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                note(node.target.id, path)                        # 类字段 / 带注解常量
            elif isinstance(node, ast.AnnAssign) and isinstance(
                    node.target, ast.Attribute) and isinstance(
                    node.target.value, ast.Name) and node.target.value.id == "self":
                note(node.target.attr, path)
    return owners


def _module_aliases(tree: ast.AST) -> dict[str, str]:
    """本文件里 `import a.b as c` / `from a import b` 的别名 → 被 import 的绝对模块名。"""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    out[a.asname] = a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for a in node.names:
                if a.name == "*":
                    continue
                out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def _scan(root: pathlib.Path | None = None,
          pkgs: tuple[str, ...] | None = None) -> tuple[list[str], list[str]]:
    """→ (跨包 import 私有名, 跨包访问私有成员)。两项都是 `文件:名字` 形状、已去重排序。"""
    root = root or ROOT
    pkgs = pkgs or PKGS
    trees = {p: ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
             for p in _files(root, pkgs)}
    owners = _declared_owners(trees, root)
    bad_imports: list[str] = []
    bad_attrs: list[str] = []

    for path, tree in trees.items():
        pkg = _pkg_of(path, root)
        rel = path.relative_to(root).as_posix()
        aliases = _module_aliases(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                top = node.module.split(".")[0]
                if top in pkgs and top != pkg:
                    for a in node.names:
                        if _is_private(a.name):
                            bad_imports.append(f"{rel}:{a.name}")
            elif isinstance(node, ast.Attribute) and _is_private(node.attr):
                recv = ""
                if isinstance(node.value, ast.Name):
                    recv = node.value.id
                elif isinstance(node.value, ast.Attribute):
                    recv = node.value.attr
                if not recv or recv in ("self", "cls", "_"):
                    continue
                if recv in aliases:                       # 规则 2: 模块别名下的私有名
                    target = aliases[recv].split(".")[0]
                    if target in pkgs and target != pkg:
                        bad_attrs.append(f"{rel}:.{node.attr}")
                    continue
                if recv in _EXTERNAL:                     # 规则 3: 对象私有成员
                    continue
                own = owners.get(node.attr)
                if own and pkg not in own:
                    bad_attrs.append(f"{rel}:.{node.attr}")

    return sorted(set(bad_imports)), sorted(set(bad_attrs))


def test_no_cross_package_private_names():
    """除债务表外, 不许出现新的跨包私有名访问。"""
    bad_imports, bad_attrs = _scan()
    new = [f"{k}    ← import 私有名" for k in bad_imports if k not in _IMPORT_DEBT]
    new += [f"{k}    ← 读私有成员" for k in bad_attrs if k not in _ATTR_DEBT]
    assert not new, (
        "出现新的跨包私有名访问（包之间只能通过公开面打交道）:\n  " + "\n  ".join(new)
        + "\n修法: 在拥有方加一个公开的读写口/方法（或把那个名字改成公开）, "
          "\n      而不是把对方的内部字段当接口 —— 见本文件顶部三条规则。")


def test_debt_tables_are_not_stale():
    """反向判据: 债务表里每一条都必须**仍然是违规**（收口完就该删, 忘了删 → 红）。"""
    bad_imports, bad_attrs = _scan()
    stale = [f"{k}（{why}）" for k, why in _IMPORT_DEBT.items() if k not in bad_imports]
    stale += [f"{k}（{why}）" for k, why in _ATTR_DEBT.items() if k not in bad_attrs]
    assert not stale, (
        "债务表已过期（这些访问已经不存在了, 请删条目 —— 表只许缩短）:\n  "
        + "\n  ".join(stale))


def test_scan_can_actually_fail():
    """自测: 扫描器必须真的会红 —— 三类违规各喂一条。"""
    probe = ROOT / ".testtmp" / "_iface_probe"
    (probe / "core").mkdir(parents=True, exist_ok=True)
    (probe / "webgui").mkdir(parents=True, exist_ok=True)
    (probe / "core" / "__init__.py").write_text("", encoding="utf-8")
    (probe / "webgui" / "__init__.py").write_text("", encoding="utf-8")
    (probe / "core" / "mod.py").write_text(
        "class Holder:\n"
        "    def __init__(self):\n"
        "        self._secret = 1\n"
        "    def _hidden(self):\n"
        "        return 2\n"
        "_module_private = 3\n", encoding="utf-8")
    (probe / "webgui" / "mod.py").write_text(
        "from core.mod import _module_private\n"          # 规则 1
        "from core import mod\n"                          # 规则 2（模块别名）
        "from core.mod import Holder\n"
        "h = Holder()\n"
        "a = h._secret\n"                                 # 规则 3（对象成员）
        "b = mod._module_private\n", encoding="utf-8")
    try:
        bad_imports, bad_attrs = _scan(root=probe, pkgs=("core", "webgui"))
    finally:
        (probe / "core" / "mod.py").unlink(missing_ok=True)
        (probe / "webgui" / "mod.py").unlink(missing_ok=True)

    assert "webgui/mod.py:_module_private" in bad_imports, bad_imports
    assert "webgui/mod.py:._module_private" in bad_attrs, "规则 2/3 一条都没抓到"
    assert "webgui/mod.py:._secret" in bad_attrs, "规则 3（对象成员）没抓到"
    print(f"    interface: 探针抓到 import {len(bad_imports)} / 成员 {len(bad_attrs)}")


def test_scan_is_not_vacuous():
    """主扫描必须真抓到东西（否则"全绿"只说明判据失效）。"""
    bad_imports, bad_attrs = _scan()
    assert bad_imports, "一条跨包 import 私有名都没扫到 —— 判据失效了"
    assert bad_attrs, "一条跨包私有成员访问都没扫到 —— 判据失效了"
    print(f"    interface: 既存 import {len(bad_imports)} 处 / "
          f"成员访问 {len(bad_attrs)} 处（全在债务表里）")
