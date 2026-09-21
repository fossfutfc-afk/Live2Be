# -*- coding: utf-8 -*-
"""守门: **拆分安全网**（C0, 2026-09-21）——两件事, 都是"拆分时最容易静默出错"的。

## ① API 面快照（`tests/fixtures/api_surface.txt`）

记下 7 个"要拆/要搬"的模块**今天**对外的每个名字 + 种类。拆分时:
**丢名字 / 种类变了 → 红**（搬家的名字只是 owner 变了, 不算丢）。
刷新: `SPLIT_API_UPDATE=1 pytest tests/core/test_split_safety.py`（刷完人工审 diff）。

## ② 禁止 patch 被拆包的属性

测试里 7 处 `monkeypatch.setattr(bond, …)`（`_store` / `_image_gen` / `GATE_WATCHDOG_MS` …）
是模块→包转换的**头号杀手**: 代码搬进 `webgui/bond/stores.py` 后, 子模块读的是
自己的全局, patch **包属性会静默不生效**（测试照旧绿, 覆盖全丢）。⇒ 拆分第一步
（C1）要把这些接缝收进 `webgui/bond/deps.py` 并把测试改成 patch `deps.*`;
在那之前, 这条守门用 `ALLOWED_PATCHES` 把既存 7 处登记在案 + 反向检查白名单过期。

运行: python -m pytest tests/core/test_split_safety.py
"""
import ast
import importlib
import inspect
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "api_surface.txt"

#: 快照覆盖的模块（= `docs/EXEC_SPLIT.md` 的拆分/搬家目标）
TARGETS = (
    "webgui.bond",
    "webgui.chat",
    "core.bond.bond_story",
    "contract.records",
    "core.momotalk",
    "core.ui.vn_cli",
    "llm.client",
)

#: 既存 patch 点白名单: (相对路径, 属性) → C1/C12 里的归宿
#: （实测 16 处 / 8 个测试文件; 比"grep setattr(bond," 多——还有 `chat._store = st`
#:   这类直接赋值, 以及 `llm.client._settings_toml`）
ALLOWED_PATCHES: dict[tuple[str, str], str] = {
    # —— webgui.bond: 6 处 ——
    ("tests/webgui/test_bond.py", "_choice_pregen_enabled"): "C1 → 接缝 webgui/deps.py",
    ("tests/webgui/test_bond.py", "ImageGenerator"): "C1 → 接缝 webgui/deps.py",
    ("tests/webgui/test_bond.py", "_image_gen"): "C1 → 接缝 webgui/deps.py",
    ("tests/webgui/test_bond.py", "_enqueue_annotate"): "C1 → 接缝 webgui/deps.py",
    ("tests/webgui/test_web_http.py", "GATE_WATCHDOG_MS"): "C1 → 接缝 webgui/deps.py",
    ("tests/webgui/test_web_http.py", "BUSY_WATCHDOG_MS"): "C1 → 接缝 webgui/deps.py",
    # —— webgui.chat: 8 处（`chat._store = st` 直接赋值, 7 文件）+ reset_engines 2 处 ——
    ("tests/webgui/test_bond.py", "_store"): "C1/C12 → 接缝 webgui/deps.py（chat 同用）",
    ("tests/webgui/test_bond_abort.py", "_store"): "C1/C12 → 接缝 webgui/deps.py",
    ("tests/webgui/test_bond_replay.py", "_store"): "C1/C12 → 接缝 webgui/deps.py",
    ("tests/webgui/test_bond_staging.py", "_store"): "C1/C12 → 接缝 webgui/deps.py",
    ("tests/webgui/test_chat_events.py", "_store"): "C1/C12 → 接缝 webgui/deps.py",
    ("tests/webgui/test_prewarm_cache.py", "_store"): "C1/C12 → 接缝 webgui/deps.py",
    ("tests/webgui/test_web_http.py", "_store"): "C1/C12 → 接缝 webgui/deps.py",
    ("tests/webgui/test_settings_store.py", "reset_engines"): "C1/C12 → 接缝 webgui/deps.py",
    ("tests/webgui/test_web_http.py", "reset_engines"): "C1/C12 → 接缝 webgui/deps.py",
    # —— llm.client: 1 处 ——
    ("tests/llm/test_client_stream.py", "_settings_toml"):
        "C14（若拆 llm/client）: settings 读取接缝",
}

_MISSING = object()
#: 本项目自有的顶层包——只有"自己的名字"才进快照
OUR_PKGS = frozenset({"contract", "core", "llm", "renderer", "webgui"})


def _package_of(path: pathlib.Path) -> str:
    rel_parent = path.parent.relative_to(ROOT).as_posix().replace("/", ".")
    return rel_parent if rel_parent != "." else path.stem


def _own_names(module_name: str) -> set[str]:
    """**本项目自有**的对外名字: 本文件顶层定义 ∪ 从本项目其它模块 import 进来的。

    为什么不能直接 `dir()`: 那样会把 `Enum` / `dataclass` / `Path` 这些 stdlib 名字
    也钉进快照——拆分时清理一个不再用的 import 就会误报"丢了名字"。
    """
    path = ROOT.joinpath(*module_name.split(".")).with_suffix(".py")
    if not path.is_file():                       # 包形式（如已拆成包）
        path = ROOT.joinpath(*module_name.split("."), "__init__.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pkg = _package_of(path)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:                       # 相对: 用文件所在包还原
                parts = pkg.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1]) if node.level > 1 else pkg
                src = f"{base}.{node.module}" if node.module else base
            else:
                src = node.module or ""
            if src.split(".")[0] in OUR_PKGS:
                names |= {a.asname or a.name for a in node.names}
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.asname and a.name.split(".")[0] in OUR_PKGS:
                    names.add(a.asname)
    return names


def _kind_of(obj) -> str:
    """对外面的**稳定**种类: class / function / data。

    ⚠️ 不能直接用 `type(obj).__name__`: `core.momotalk._EMBED_REPORTED` 这类
    **运行期可变标志**在导入时是 `None`、跑过某用例后变 `bool` —— 快照会抖
    （2026-09-21 实测被守门抓出来）。三态足够表达"丢名字/种类变了"。
    """
    if inspect.isclass(obj):
        return "class"
    if callable(obj):
        return "function"
    return "data"


def _surface(module_name: str) -> list[tuple[str, str, str]]:
    """模块**自有**对外面 → [(名字, 种类, 定义处)]（跳过 stdlib/第三方的借用名）。"""
    mod = importlib.import_module(module_name)
    own = _own_names(module_name)
    rows: list[tuple[str, str, str]] = []
    for name in sorted(own):
        obj = getattr(mod, name, _MISSING)
        if obj is _MISSING or inspect.ismodule(obj):
            continue
        rows.append((name, _kind_of(obj), getattr(obj, "__module__", "-") or "-"))
    return sorted(rows)


def _snapshot() -> dict[str, list[tuple[str, str, str]]]:
    return {m: _surface(m) for m in TARGETS}


def _read_fixture() -> dict[str, list[tuple[str, str]]]:
    """夹具 → {模块: [(名字, 种类)]}（定义处只做参考, 不参与比对）。"""
    out: dict[str, list[tuple[str, str]]] = {}
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        module, name, kind, _owner = line.split("\t")
        out.setdefault(module, []).append((name, kind))
    return out


def _write_fixture(snap: dict[str, list[tuple[str, str, str]]]) -> None:
    lines = [
        "# API 面快照（C0 守门）——拆分时**丢名字/种类变了**会红; owner 仅供审阅。",
        "# 刷新: SPLIT_API_UPDATE=1 pytest tests/core/test_split_safety.py",
        "# 格式: 模块<TAB>名字<TAB>种类<TAB>定义处",
    ]
    for module in TARGETS:
        lines.append(f"# ---- {module} ----")
        lines += [f"{module}\t{n}\t{k}\t{o}" for n, k, o in snap[module]]
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_api_surface_matches_snapshot():
    """① 拆分不得悄悄丢名字（owner 变化 = 只是搬家, 允许）。"""
    snap = _snapshot()
    if os.environ.get("SPLIT_API_UPDATE"):
        _write_fixture(snap)
        print(f"    split-guard: 已刷新快照 → {FIXTURE.relative_to(ROOT).as_posix()}")
        return
    assert FIXTURE.is_file(), (
        f"缺快照 {FIXTURE.relative_to(ROOT).as_posix()} —— "
        "用 SPLIT_API_UPDATE=1 跑一次本文件生成。")
    want = _read_fixture()
    problems: list[str] = []
    total = 0
    for module in TARGETS:
        got = {(n, k) for n, k, _o in snap[module]}
        exp = set(want.get(module, []))
        total += len(exp)
        for name, kind in sorted(exp - got):
            problems.append(f"{module}: 丢了 {name}（原为 {kind}）")
        for name, kind in sorted(got - exp):
            problems.append(f"{module}: 多出 {name}（{kind}）—— 新 API? 若是, 刷新快照")
    assert not problems, (
        "API 面与快照不一致（拆分时最容易静默出错的地方）:\n  " + "\n  ".join(problems)
        + "\n确认是有意变更后: SPLIT_API_UPDATE=1 跑本文件刷新并人工审 git diff。")
    print(f"    split-guard: {len(TARGETS)} 个模块 / {total} 个对外名字与快照一致")


def _package_aliases(tree: ast.AST) -> dict[str, str]:
    """本文件里"指向被拆包"的别名 → 目标包名。"""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in TARGETS and a.asname:        # import x.y as b（无 asname 绑的是顶层）
                    out[a.asname] = a.name
        elif isinstance(node, ast.ImportFrom) and not node.level:
            base = node.module or ""
            for a in node.names:
                full = f"{base}.{a.name}"
                if full in TARGETS:                       # from webgui import bond
                    out[a.asname or a.name] = full
    return out


def _patch_points() -> list[tuple[str, str, int]]:
    """[(相对路径, 属性, 行号)]——`setattr(别名, "x", …)` 与 `别名.x = …`。"""
    hits: list[tuple[str, str, int]] = []
    for path in sorted((ROOT / "tests").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _package_aliases(tree)
        if not aliases:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            # 两种写法都算: top-level `setattr(x, "a", …)` 与 `monkeypatch.setattr(x, "a", …)`
            if isinstance(node, ast.Call) and len(node.args) >= 2:
                func = node.func
                is_setattr = (isinstance(func, ast.Name) and func.id == "setattr") or \
                    (isinstance(func, ast.Attribute) and func.attr == "setattr")
                if is_setattr:
                    target, attr = node.args[0], node.args[1]
                    if isinstance(target, ast.Name) and target.id in aliases \
                            and isinstance(attr, ast.Constant) and isinstance(attr.value, str):
                        hits.append((rel, attr.value, node.lineno))
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                            and t.value.id in aliases:
                        hits.append((rel, t.attr, node.lineno))
    return hits


def test_no_patching_split_targets_without_whitelist():
    """② 不得新增"patch 被拆包属性"的点（新增 → 红, 必须改 patch `deps.*`）。"""
    live = {(rel, attr) for rel, attr, _ln in _patch_points()}
    new = [f"{rel}  patch {attr}" for rel, attr in sorted(live - set(ALLOWED_PATCHES))]
    assert not new, (
        "新增了对被拆包的属性 patch —— 模块→包转换后它会**静默失效**:\n  "
        + "\n  ".join(new)
        + "\n修法: patch 目标改成显式接缝模块（C1 起是 `webgui.bond.deps`）。")


def test_patch_whitelist_is_not_stale():
    """反向判据: 白名单里每条都必须仍然是真实 patch 点（C1 改完后应清空）。"""
    live = {(rel, attr) for rel, attr, _ln in _patch_points()}
    stale = [f"{rel}  patch {attr}（{why}）" for (rel, attr), why in ALLOWED_PATCHES.items()
             if (rel, attr) not in live]
    assert not stale, (
        "patch 白名单已过期（这些点已经不 patch 被拆包了, 请删条目）:\n  "
        + "\n  ".join(stale))
    print(f"    split-guard: 既存 patch 点 {len(ALLOWED_PATCHES)} 处已登记（C1 逐个消）")
