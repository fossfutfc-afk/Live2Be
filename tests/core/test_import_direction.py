# -*- coding: utf-8 -*-
"""守门: **分层依赖方向**（C0, 2026-09-21）——拆分/搬家前先把"谁能 import 谁"钉住。

## 规则（`docs/EXEC_SPLIT.md` §2）

    contract/  最底层: 不得依赖 core / llm / webgui / renderer / tests / experiments
    llm/       传输层: 不得依赖 webgui / renderer / tests / experiments;
                       对 core 只允许薄横切 core.paths / core.common（见 ALLOWED）
    core/      引擎层: 不得依赖 webgui / renderer / tests / experiments
    renderer/  表现层: 不得依赖 webgui / tests / experiments
    webgui/    壳    : 不得依赖 tests / experiments

## 为什么用自写守门而不是 import-linter / tach

仓库先例是 `tests/core/test_paths.py`（源码扫描守门）: 零新依赖、随全量测试跑、
能写项目特有的规则。规则涨到十条以上再换声明式工具（都能 `uvx` 一试）。

## 白名单纪律

`ALLOWED` 里每一条都是**今天的既存违规 + 归宿节点**; 第二条用例反向检查
"白名单是不是已经过期"——搬完就该删条目, 忘了删会红。

运行: python -m pytest tests/core/test_import_direction.py
"""
import ast
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

#: 被扫描的包 → 它**禁止**依赖的顶层包
RULES: dict[str, frozenset[str]] = {
    "contract": frozenset({"core", "llm", "webgui", "renderer", "tests", "experiments"}),
    "llm": frozenset({"webgui", "renderer", "tests", "experiments"}),
    "core": frozenset({"webgui", "renderer", "tests", "experiments"}),
    "renderer": frozenset({"webgui", "tests", "experiments"}),
    "webgui": frozenset({"tests", "experiments"}),
}

#: `llm/` 对 `core` 的**薄横切**豁免（`core.paths` = 固定路径宏, `core.common` = err）
LLM_CORE_ALLOWED = frozenset({"core.paths", "core.common"})

#: 既存违规白名单: (相对路径, 被 import 的顶层包) → 归宿（`docs/EXEC_SPLIT.md` 节点）
#: ✅ C10 清掉 4 条: 错误原语下沉 `contract/errors.py`（3 条 contract→core）、
#: `json_cleaner` 搬到 `contract/`（1 条 contract→llm）。剩最后 1 条等 C11。
ALLOWED: dict[tuple[str, str], str] = {
    ("core/ui/vn_cli.py", "renderer"):
        "vn_cli 是 CLI **应用**不是引擎（C12 搬 apps/ 时这条规则消失）。"
        "⚠️ C11 实测修正: 原计划写\"C11 减 1 条\"做不到——真正用 renderer 的是 vn_cli 自己的"
        "显示路径（`simulate_vn_scene`/`run_bond_story_vn`）, 而 C11 上提的 "
        "`_build_director`/`_trigger_title` 只依赖 core.director; C11 解掉的是"
        "**webgui → CLI** 的反向耦合",
}


def _package_of(path: pathlib.Path) -> str:
    """文件所属包（用于还原相对 import）: core/bond/x.py → core.bond。"""
    rel_parent = path.parent.relative_to(ROOT).as_posix().replace("/", ".")
    return rel_parent if rel_parent != "." else path.stem


def _imports(path: pathlib.Path) -> list[tuple[int, str]]:
    """[(行号, 绝对模块名)]——相对 import 归一成绝对名。"""
    src = path.read_text(encoding="utf-8")
    pkg = _package_of(path)
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:                       # 相对: 从文件所在包往上退 level-1 层
                parts = pkg.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1]) if node.level > 1 else pkg
                name = f"{base}.{node.module}" if node.module else base
            else:
                name = node.module or ""
            out.append((node.lineno, name))
    return out


def _scan() -> list[tuple[str, str, int, str]]:
    """→ [(相对路径, 被依赖顶层, 行号, 绝对模块名)]（**全部**违规, 未过滤白名单）。"""
    found: list[tuple[str, str, int, str]] = []
    for pkg, banned in RULES.items():
        for path in sorted((ROOT / pkg).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(ROOT).as_posix()
            for line, name in _imports(path):
                top = name.split(".")[0] if name else ""
                if top not in banned:
                    continue
                if pkg == "llm" and top == "core" and \
                        any(name == a or name.startswith(a + ".") for a in LLM_CORE_ALLOWED):
                    continue                     # 薄横切豁免
                found.append((rel, top, line, name))
    return found


def test_no_new_layering_violations():
    """除白名单外, 不得出现新的反向依赖。"""
    new = [f"{rel}:{line}  import {name}（{pkg} 不得依赖 {top}）"
           for rel, top, line, name in _scan()
           if (rel, top) not in ALLOWED]
    assert not new, (
        "出现新的分层违规（引擎/契约层反向依赖壳或表现层）:\n  " + "\n  ".join(new)
        + "\n修法: 把共用件下移到 contract/（或薄横切 core.common）, "
          "或——若是**新发现的既存违规**——登记进 ALLOWED 并注明归宿节点。")


def test_whitelist_is_not_stale():
    """反向判据: 白名单里每条都必须**仍然是违规**（搬完就该删, 忘了删 → 红）。"""
    live = {(rel, top) for rel, top, _l, _n in _scan()}
    stale = [f"{rel} → {top}（{why}）" for (rel, top), why in ALLOWED.items()
             if (rel, top) not in live]
    assert not stale, (
        "白名单已过期（这些依赖关系已经不存在了, 请删条目）:\n  " + "\n  ".join(stale))


def test_scan_can_actually_fail():
    """自测: 扫描器必须真的会红——喂一段违规源码。"""
    tmp = ROOT / ".testtmp" / "_layering_probe"
    tmp.mkdir(parents=True, exist_ok=True)
    probe = tmp / "probe.py"
    probe.write_text("import webgui\nfrom core import paths\n", encoding="utf-8")
    try:
        hits = _imports(probe)
        assert (1, "webgui") in hits and (2, "core") in hits, hits
    finally:
        probe.unlink(missing_ok=True)
    print(f"    layering: 规则 {len(RULES)} 条 / 白名单 {len(ALLOWED)} 条 / 扫描可失败")
