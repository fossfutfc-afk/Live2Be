# -*- coding: utf-8 -*-
"""`core/paths.py` 单测 —— **固定路径宏**约定（用户 2026-09-19）。

用户原话：
> *"这种固定路径我推荐你写成 macro 的形式放在最上面，因为说不准这类路径进行
> 更改，最后改成你用 grep 能直接全量定位的方法。"*

所以这里钉三件事（都是"约定"而非"功能"，靠测试才不会烂掉）:

  ① **清单完整**：`__all__` 与文件里真实的顶层常量**一一对应**（漏登记 = grep 漏）
  ② **值可信**：全是绝对路径、全在项目根下、该存在的存在（缺文件不该静默）
  ③ **没有漏网的**：`core/ webgui/ llm/ contract/` 里**不许**再有现拼的项目根路径
     （`Path(__file__) / "assets"` 这种）—— 那就是"下次改目录找不到的东西"
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import paths                                           # noqa: E402

#: 约定里"必须存在"的固定路径（运行时数据/诊断日志允许不存在——它们会被创建）
MUST_EXIST = (
    "SETTINGS_PATH", "FESTIVALS_PATH", "WORLD_OVERVIEW_PATH", "REGIONS_PATH",
    "PLACES_PATH", "PLACE_TABLE_PATH", "INTERPERSON_PATH", "MMT_REGISTRY_PATH",
    "DIRECTOR_WHITELIST_PATH",
)
#: 允许缺失（首次运行才创建）
MAY_MISS = ("DIAG_DIR", "DIAG_LOG_PATH")

#: 现拼路径的哨兵: `Path(__file__)` 同行还出现这些"项目根一级目录名" = 违规
_ROOT_MARKERS = ('"assets"', '"data"', '"config"', '"webgui"', "settings.toml")
_SCAN_DIRS = ("core", "webgui", "llm", "contract")
_SKIP_FILES = {"core/paths.py"}          # 宏的家, 它才是那个"一处"


def test_all_matches_module_constants():
    """① `__all__` == 文件里真实的顶层 UPPERCASE 常量（登记不全 → grep 漏）。"""
    tree = ast.parse((ROOT / "core" / "paths.py").read_text(encoding="utf-8"))
    real: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name) and re.fullmatch(r"[A-Z][A-Z_]*", t.id):
                real.add(t.id)
    declared = set(paths.__all__)
    assert declared == real, (f"__all__ 少了 {sorted(real - declared)}; "
                              f"多了 {sorted(declared - real)}")
    assert len(real) >= 15, real
    print(f"    __all__: {len(real)} 条, 与顶层常量一一对应")


def test_every_value_is_absolute_under_root():
    """② 全是绝对路径且落在项目根下（相对路径会随 cwd 漂——`Path("data")` 的坑）。"""
    for name in paths.__all__:
        v = getattr(paths, name)
        if name == "ROOT":
            assert v == ROOT, (v, ROOT)
            continue
        assert isinstance(v, Path), f"{name} 不是 Path: {type(v)}"
        assert v.is_absolute(), f"{name} 不是绝对路径: {v}"
        assert ROOT in v.parents or v == ROOT, f"{name} 跑到项目根外面了: {v}"
    for name in MUST_EXIST:
        assert getattr(paths, name).exists(), f"{name} 指向的东西不存在"
    for name in MAY_MISS:
        assert hasattr(paths, name)
    print(f"    值: {len(paths.__all__)} 条全部绝对且位于根下; "
          f"{len(MUST_EXIST)} 条必须存在的都在位")


def test_no_inline_project_paths_left():
    """③ **不许再有现拼的项目根路径**——这是"grep 能全量定位"的守门人。

    命中 = `Path(__file__)` 同行还写了 `"assets"` / `"data"` / `"config"` /
    `settings.toml` 这类**项目根一级**的东西。包内相对资源（如 `llm/prompts/`
    找自己目录）不在此列——那不是固定路径，是包结构。
    """
    bad: list[str] = []
    for d in _SCAN_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if rel in _SKIP_FILES or "__pycache__" in rel:
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "Path(__file__)" not in line or line.lstrip().startswith("#"):
                    continue
                if any(m in line for m in _ROOT_MARKERS):
                    bad.append(f"{rel}:{i}: {line.strip()}")
    assert not bad, "还有现拼的项目根路径（请搬进 core/paths.py）:\n  " + "\n  ".join(bad)
    print(f"    {'/'.join(_SCAN_DIRS)}: 零现拼项目根路径（{len(_SKIP_FILES)} 个豁免）")


def test_paths_import_is_cheap_and_cycle_free():
    """`core/paths.py` 只依赖 pathlib——谁都能 import 它，不会有环。"""
    tree = ast.parse((ROOT / "core" / "paths.py").read_text(encoding="utf-8"))
    imports = [n for n in ast.walk(tree)
               if isinstance(n, (ast.Import, ast.ImportFrom))]
    mods: set[str] = set()
    for n in imports:
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        else:
            mods.add((n.module or "").split(".")[0])
    assert mods <= {"__future__", "pathlib"}, mods
    print(f"    paths 的依赖: {sorted(mods)}（无环风险）")


if __name__ == "__main__":
    test_all_matches_module_constants()
    test_every_value_is_absolute_under_root()
    test_no_inline_project_paths_left()
    test_paths_import_is_cheap_and_cycle_free()
    print("all paths tests passed")
