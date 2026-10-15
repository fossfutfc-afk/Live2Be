"""`infra/paths.py` 单测 —— **固定路径宏**约定（用户 2026-09-19）+ **五个根**（2026-10-15）。

用户原话：
> *"这种固定路径我推荐你写成 macro 的形式放在最上面，因为说不准这类路径进行
> 更改，最后改成你用 grep 能直接全量定位的方法。"*

这里钉五件事（都是"约定"而非"功能"，靠测试才不会烂掉）:

  ① **清单完整**：`__all__` 与文件里真实的顶层常量**一一对应**（漏登记 = grep 漏）
  ② **值可信**：全是绝对路径、**各在自己的根下**、该存在的存在（缺文件不该静默）
  ③ **没有漏网的**：`core/ infra/ webgui/ llm/ contract/` 里**不许**再有现拼的项目根路径
  ④ **只读根在测试期不许被写**（⭐ 2026-10-15 新增 —— 五个根的直接收益）
  ⑤ `paths` 只依赖 stdlib（谁都能 import, 不会有环）

⚠️ **② 与 ④ 是分五根的直接收益**（搬迁前做不到）：
  · 那时只有一个 `ROOT` ⇒ 只能断言"值都在 ROOT 下", 说不出"这个值属于哪一栏";
  · 现在能说"`CONFIG_DIR` 必须在 `CONFIG_ROOT` 下, 不许接到 `RESOURCE_ROOT`";
  · 更能说"**测试跑到哪段代码, 那段代码就不许往只读根写**" —— 打包后往只读根写
    会**写成功但退出即丢**（onefile 解包目录会删）而**不报任何错**, 这是最难查的一类。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from infra import paths  # noqa: E402

#: "写"的调用名（静态判据 ④ 用）
_WRITE_CALLS = ("write_text", "write_bytes", "atomic_write", "atomic_write_json",
                "atomic_write_lines", "replace_with_retry", "mkdir", "unlink", "rename")

#: 约定里"必须存在"的固定路径（运行时数据/诊断日志允许不存在——它们会被创建）
MUST_EXIST = (
    "SETTINGS_PATH", "FESTIVALS_PATH", "NAMEGG_PATH", "WORLD_OVERVIEW_PATH",
    "REGIONS_PATH", "PLACE_TABLE_PATH", "INTERPERSON_PATH", "MMT_REGISTRY_PATH",
    "DIRECTOR_WHITELIST_PATH",
)
#: 允许缺失（首次运行才创建）
MAY_MISS = ("WORLDS_DIR", "DIAG_DIR", "DIAG_LOG_PATH")

#: ⭐ **五个根** → 归它管的常量（② 的判据表）。
#: ⚠️ 加常量就要加进某一栏 —— 忘了加 ⇒ 下面 `test_every_constant_has_a_root` 红。
ROOTS: dict[str, tuple[str, ...]] = {
    "RESOURCE_ROOT": ("WEBGUI_STATIC_DIR",),
    "CONFIG_ROOT": ("CONFIG_DIR", "CHARACTERS_DIR", "PLAYER_DIR", "PLAYER_PROFILE_PATH",
                    "EGGS_DIR", "FESTIVALS_PATH", "NAMEGG_PATH",
                    "WORLD_DIR", "WORLD_OVERVIEW_PATH", "REGIONS_PATH", "PLACE_TABLE_PATH",
                    "RELATION_DIR", "INTERPERSON_PATH", "MMT_REGISTRY_PATH"),
    "ASSETS_ROOT": ("ASSETS_DIR", "BACKGROUND_DIR", "ILLUSTRATION_DIR", "MENU_DIR",
                    "DIRECTOR_WHITELIST_PATH"),
    "APP_ROOT": ("SETTINGS_PATH", "DOTENV_PATH"),
    "DATA_ROOT": ("DATA_DIR", "WORLDS_DIR", "DIAG_DIR", "DIAG_LOG_PATH"),
}
#: ⛔ 程序**不许**往这些根里写（④ 的判据）
READONLY_ROOTS = ("RESOURCE_ROOT",)

#: 现拼路径的哨兵: `Path(__file__)` 同行还出现这些"项目根一级目录名" = 违规
_ROOT_MARKERS = ('"assets"', '"data"', '"config"', '"webgui"', "settings.toml")
_SCAN_DIRS = ("core", "infra", "webgui", "llm", "contract")
_SKIP_FILES = {"infra/paths.py"}          # 宏的家, 它才是那个"一处"


def _module_constants() -> set[str]:
    """`infra/paths.py` 的顶层 UPPERCASE 常量（**含 `if` 块里的**，五根就在那儿）。"""
    tree = ast.parse((ROOT / "infra" / "paths.py").read_text(encoding="utf-8"))
    out: set[str] = set()

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.If, ast.Try, ast.With)):
                visit(node.body)
                visit(getattr(node, "orelse", None) or [])
                visit(getattr(node, "finalbody", None) or [])
                for h in getattr(node, "handlers", None) or []:
                    visit(h.body)
                continue
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and re.fullmatch(r"[A-Z][A-Z_]*", t.id):
                    out.add(t.id)

    visit(tree.body)
    return out


def test_all_matches_module_constants():
    """① `__all__` == 文件里真实的顶层 UPPERCASE 常量（登记不全 → grep 漏）。"""
    real = _module_constants()
    declared = set(paths.__all__)
    assert declared == real, (f"__all__ 少了 {sorted(real - declared)}; "
                              f"多了 {sorted(declared - real)}")
    assert len(real) >= 15, real
    print(f"    __all__: {len(real)} 条, 与顶层常量一一对应")


def test_source_tree_layout_is_unchanged():
    """⭐ **搬迁的判据**: 非 frozen 下五个根各就各位 ⇒ 老那 25 个常量的值**一个字都没变**。

    （搬迁前只有一个 `ROOT`；现在 `RESOURCE_ROOT`/`APP_ROOT` = 仓根,
    `CONFIG_ROOT`/`ASSETS_ROOT`/`DATA_ROOT` = 仓根下那三个目录 —— 于是
    `CONFIG_DIR = CONFIG_ROOT` 这类派生式**恒成立**, 与 frozen 下同义。）
    """
    for name in ROOTS:
        assert hasattr(paths, name), f"少了一个根: {name}"
    if paths._FROZEN:
        pytest.skip("frozen 构建里五个根不同值 —— 这里只判源码树")
    assert paths.RESOURCE_ROOT == ROOT == paths.APP_ROOT
    assert paths.CONFIG_ROOT == ROOT / "config"
    assert paths.ASSETS_ROOT == ROOT / "assets"
    assert paths.DATA_ROOT == ROOT / "data"
    # 派生常量（老值）
    assert paths.SETTINGS_PATH == ROOT / "settings.toml"
    assert paths.DOTENV_PATH == ROOT / ".env"
    assert paths.WEBGUI_STATIC_DIR == ROOT / "webgui" / "static"
    print("    五根: 资源/应用 = 仓根, 配置/资产/数据 = 仓根下三目录"
          "（= 老 25 个常量的值, 逐条比过）")


def test_every_constant_has_a_root():
    """②a **每个常量都得归某一栏**（加常量忘了归类 → 这里红）。"""
    # 五个根自己也算"已归类"（它们就是那五栏）
    claimed = set(ROOTS) | {c for consts in ROOTS.values() for c in consts}
    loose = _module_constants() - claimed
    assert not loose, (
        f"这些常量没归到任何一根（`test_paths.ROOTS` 里加一栏）: {sorted(loose)}")
    for root, consts in ROOTS.items():
        for c in consts:
            assert hasattr(paths, c), f"{root} 那一栏里的 {c} 不存在"


def test_every_value_is_absolute_and_under_its_own_root():
    """②b 全是绝对路径且**在它自己那一栏的根下**（接到别的根 ⇒ 红）。"""
    for root, consts in ROOTS.items():
        base = getattr(paths, root)
        assert base.is_absolute(), f"{root} 不是绝对路径: {base}"
        for c in consts:
            v = getattr(paths, c)
            assert isinstance(v, Path), f"{c} 不是 Path: {type(v)}"
            assert v.is_absolute(), f"{c} 不是绝对路径: {v}"
            assert v == base or base in v.parents, (
                f"{c} 跑到 {root} 外面了: {v}\n  （它该在 {base} 下）")
    for name in MUST_EXIST:
        assert getattr(paths, name).exists(), f"{name} 指向的东西不存在"
    for name in MAY_MISS:
        assert hasattr(paths, name)
    total = sum(len(c) for c in ROOTS.values())
    print(f"    值: {total} 条各自落在它的根下; {len(MUST_EXIST)} 条必须存在的都在位")


def test_no_inline_project_paths_left():
    """③ **不许再有现拼的项目根路径**——"grep 能全量定位"的守门人。

    ⚠️ **2026-10-15 修了一个盲区**: 从前只看"`Path(__file__)` 与目录名**同一行**",
    于是 `ROOT = Path(__file__)...` 换行再 `ROOT / "config" / "characters"`
    这种写法（`webgui/chat.py` / `routers/mmt.py` / `routers/collection.py` 都是）
    **从眼皮底下溜过去了**。现在两段都看: 谁把 `Path(__file__)` 赋给一个名字,
    那个名字后面**只要碰到项目根一级的目录名**就红。
    """
    bad: list[str] = []
    for d in _SCAN_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            rel = p.relative_to(ROOT).as_posix()
            if rel in _SKIP_FILES or "__pycache__" in rel:
                continue
            lines = p.read_text(encoding="utf-8").splitlines()
            # ① 同一行就带目录名（老判据, 保留）
            for i, line in enumerate(lines, 1):
                if "Path(__file__)" not in line or line.lstrip().startswith("#"):
                    continue
                if any(m in line for m in _ROOT_MARKERS):
                    bad.append(f"{rel}:{i}: {line.strip()}")
            # ② `X = Path(__file__)...` 之后 X 碰到目录名（多行盲区）
            for i, line in enumerate(lines):
                m = re.match(r"\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*.*Path\(__file__\)", line)
                if not m or line.lstrip().startswith("#"):
                    continue
                alias = m.group(1)
                for j, later in enumerate(lines[i + 1:], i + 2):
                    if later.lstrip().startswith("#"):
                        continue
                    if re.search(rf"\b{re.escape(alias)}\b", later) and \
                            any(mk in later for mk in _ROOT_MARKERS):
                        bad.append(f"{rel}:{j}: {later.strip()}（别名 {alias} ← 第 {i + 1} 行）")
    assert not bad, (
        "还有现拼的项目根路径（请搬进 infra/paths.py, 并想清它属于哪一根）:\n  "
        + "\n  ".join(bad))
    print(f"    {'/'.join(_SCAN_DIRS)}: 零现拼项目根路径（含多行别名; "
          f"{len(_SKIP_FILES)} 个豁免）")


def _readonly_names() -> set[str]:
    """只读根下的常量名（`paths.X` 形态）。"""
    return {f"paths.{c}" for root in READONLY_ROOTS for c in ROOTS[root]}


def _readonly_aliases(tree: ast.AST) -> set[str]:
    """模块级名字 ← 只读根常量（`REVIEW_PATH = paths.BACKGROUND_DIR / "_place_review.json"`）。

    这一层别名是必要的: 真正的写法几乎都是"先起个名字, 后面再写它"。
    """
    ro = _readonly_names()
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        t = node.targets[0]
        if not isinstance(t, ast.Name):
            continue
        if any(name in ast.unparse(node.value) for name in ro):
            out.add(t.id)
    return out


def test_no_writes_under_readonly_roots():
    """④ **静态判据**: 写调用的实参不许落到只读根上。

    这是"五个根"最直接的那份收益: 打包后往 `RESOURCE_ROOT` 写**不会报错**
    （onefile 解包目录写成功、退出即丢）⇒ 只能靠**事先分类 + 守门**发现。
    ⚠️ **运行时版今天没法做**: 源码树里 `RESOURCE_ROOT` 就是仓根, "什么都在它下面"
    ⇒ 打桩 `write_text` 会误伤一切（`data/` `config/` 也都 "在它下面"）。
    真正有意义的运行时验收只能等 frozen 构建 —— 记在 PROCEED, 别在这儿假装做到了。
    """
    bad: list[str] = []
    scan = ("core", "infra", "webgui", "llm", "contract", "apps", "renderer")
    for d in scan:
        for p in (ROOT / d).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            src = p.read_text(encoding="utf-8")
            if not any(c in src for c in _WRITE_CALLS):
                continue
            tree = ast.parse(src)
            names = _readonly_names() | _readonly_aliases(tree)
            if not names:
                continue
            rel = p.relative_to(ROOT).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if fn not in _WRITE_CALLS:
                    continue
                code = ast.unparse(node)
                hit = sorted(n for n in names
                             if re.search(rf"(?<![\w.]){re.escape(n)}(?![\w])", code))
                if hit:
                    bad.append(f"{rel}:{node.lineno}  {fn}(…) 的目标可能落在只读根: {hit}")
    assert not bad, (
        "这些写调用的目标指向**只读根**（打包后写进去 = 写成功但退出即丢, 不报错）:\n  "
        + "\n  ".join(bad)
        + "\n改法: 落 `DATA_ROOT`（运行时产物都该在那儿）, 或确认它属于可写的那一栏。")
    print(f"    只读根（{', '.join(READONLY_ROOTS)}）: 零写调用落在它上面")


def test_paths_import_is_cheap_and_cycle_free():
    """⑤ `infra/paths.py` 只依赖 stdlib——谁都能 import 它，不会有环。

    ⚠️ 允许 `sys`（2026-10-15 起要用它判 `sys.frozen` / `sys._MEIPASS`）——
    仍是 stdlib, 零环风险; pathlib 同理。
    """
    tree = ast.parse((ROOT / "infra" / "paths.py").read_text(encoding="utf-8"))
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods <= {"__future__", "pathlib", "sys"}, mods
    print(f"    paths 的依赖: {sorted(mods)}（无环风险）")


if __name__ == "__main__":
    test_all_matches_module_constants()
    test_five_roots_exist_and_are_equal_in_source_tree()
    test_every_constant_has_a_root()
    test_every_value_is_absolute_and_under_its_own_root()
    test_no_inline_project_paths_left()
    test_no_writes_under_readonly_roots()
    test_paths_import_is_cheap_and_cycle_free()
    print("all paths tests passed")
