"""守门: **拆分安全网**（C0, 2026-09-21）——两件事, 都是"拆分时最容易静默出错"的。

## ① API 面快照（`tests/fixtures/api_surface.txt`）

记下 7 个"要拆/要搬"的模块 + 1 个接缝模块（`webgui.deps`）**今天**对外的每个名字 + 种类。
拆分时: **丢名字 / 种类变了 → 红**（搬家的名字只是 owner 变了, 不算丢）。
刷新: `SPLIT_API_UPDATE=1 pytest tests/core/test_split_safety.py`（刷完人工审 diff）。

## ② 禁止 patch 被拆包的属性

测试里原本 16 处 `monkeypatch.setattr(bond, …)`（`_store` / `_image_gen` /
`GATE_WATCHDOG_MS` …）是模块→包转换的**头号杀手**: 代码搬进 `webgui/bond/stores.py`
后, 子模块读的是自己的全局, patch **包属性会静默不生效**（测试照旧绿, 覆盖全丢）。
⇒ **C1a 已把这 16 处全部改成 patch `webgui.deps.*`**（接缝模块）, 故 `ALLOWED_PATCHES`
现在是空表——保持空表就是本节点之后的验收; 新增 patch 点必须打 `deps.*` 或登记理由。

运行: python -m pytest tests/core/test_split_safety.py
"""
import ast
import builtins
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
    "contract.streams",
    "contract.issues",
    "core.mmt.engine",
    "apps.vn_cli",
    "llm.client",
)

#: 快照里**额外**盯住的模块: 显式接缝模块 `webgui/deps.py`（C1a 起）。
#: 为什么不并进 `TARGETS`: `TARGETS` 同时是"被拆包"名单（patch 扫描按它认别名）,
#: 而 patch `deps.*` **正是**合法姿势——并进去会把守门变成反的。
#: 盯它的理由: 接缝名字被"顺手删掉"要留痕（虽会当场炸测试, 但快照 diff 更早更清楚）。
SNAPSHOT = TARGETS + ("webgui.deps",)

#: **待收敛** patch 点白名单: (相对路径, 目标模块, 属性) → 归宿。
#: ✅ C1a 已清空（16 处全部改成 patch `webgui.deps`）——保持空表是本节点的验收之一。
ALLOWED_PATCHES: dict[tuple[str, str, str], str] = {}

#: **无需收敛**的 patch 点（(相对路径, 目标模块, 属性) → 理由）。
#: 它们不构成"模块→包后静默失效"风险: 调用点在包**外**、按模块属性查找,
#: 或者被 patch 的名字本来就属于另一个尚未拆分的模块。
SAFE_PATCHES: dict[tuple[str, str, str], str] = {
    ("tests/webgui/test_settings_store.py", "webgui.chat", "reset_engines"):
        "调用点在包外（routers/settings.py 的 chat.reset_engines()）——patch 依然生效",
    ("tests/webgui/test_web_http.py", "webgui.chat", "reset_engines"):
        "同上",
    ("tests/llm/test_client_stream.py", "llm.client", "_settings_toml"):
        "llm/client.py 的拆分是 C14（可选）; 届时把它也搬进接缝模块即可",
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

    ⚠️ 不能直接用 `type(obj).__name__`: `core.mmt.engine._EMBED_REPORTED` 这类
    **运行期可变标志**在导入时是 `None`、跑过某用例后变 `bool` —— 快照会抖
    （2026-09-21 实测被守门抓出来）。三态足够表达"丢名字/种类变了"。

    ⚠️ **闭包不算 API**（2026-09-27 同类第二次；症状更重）: `core.mmt.engine._EMBED_FN`
    是"懒构造的 RAG 后端"缓存槽——导入时 `None`、跑过 digest 后变成 `make_embed_fn`
    里的**闭包** ⇒ `data` → `function`。这与 `_EMBED_REPORTED` 是同一种病，但**仅在
    本机 embedding 服务在跑时才发作**（服务不在时 `_get_embed_fn()` 恒 None，
    谁也翻不动它）⇒ 真机一起服务，守门就红。判据：`__qualname__` 带 `<locals>`
    （函数内定义的闭包）/ `lambda` ⇒ 它是**运行时缓存**，不是模块声明的接口面。
    """
    if inspect.isclass(obj):
        return "class"
    if callable(obj):
        qn = getattr(obj, "__qualname__", "") or ""
        if "<locals>" in qn or getattr(obj, "__name__", "") == "<lambda>":
            return "data"
        return "function"
    return "data"


def _owner_of(obj) -> str:
    """定义处（**只供审阅**, 不参与比对）——私有实现段一律并到父模块。

    两个理由:
    · `pathlib._local`（py3.13 起 `Path` 的实现模块）这类**解释器内部**路径会让
      owner 列在换解释器时整片抖动（实测: 3.12 的 `pathlib` → 3.13 的 `pathlib._local`）;
    · C1b 那种"模块 → 包 + `_impl.py`"的搬家, owner 从 `webgui.bond` 变成
      `webgui.bond._impl` —— 归一后**快照零 diff**, "纯搬家"这条验收才硬。
    """
    mod = getattr(obj, "__module__", "-") or "-"
    parts = [p for p in mod.split(".") if not p.startswith("_")]
    return ".".join(parts) or mod


def _surface(module_name: str) -> list[tuple[str, str, str]]:
    """模块**自有**对外面 → [(名字, 种类, 定义处)]（跳过 stdlib/第三方的借用名）。"""
    mod = importlib.import_module(module_name)
    own = _own_names(module_name)
    rows: list[tuple[str, str, str]] = []
    for name in sorted(own):
        obj = getattr(mod, name, _MISSING)
        if obj is _MISSING or inspect.ismodule(obj):
            continue
        rows.append((name, _kind_of(obj), _owner_of(obj)))
    return sorted(rows)


def _snapshot() -> dict[str, list[tuple[str, str, str]]]:
    return {m: _surface(m) for m in SNAPSHOT}


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
    for module in SNAPSHOT:
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
    for module in SNAPSHOT:
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
    print(f"    split-guard: {len(SNAPSHOT)} 个模块 / {total} 个对外名字与快照一致")


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


def _patch_points() -> list[tuple[str, str, str, int]]:
    """[(相对路径, 目标模块, 属性, 行号)]——`setattr(别名, "x", …)` 与 `别名.x = …`。"""
    hits: list[tuple[str, str, str, int]] = []
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
                        hits.append((rel, aliases[target.id], attr.value, node.lineno))
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) \
                            and t.value.id in aliases:
                        hits.append((rel, aliases[t.value.id], t.attr, node.lineno))
    return hits


def test_no_patching_split_targets_without_whitelist():
    """② 不得新增"patch 被拆包属性"的点（新增 → 红, 必须改 patch `webgui/deps.*`）。"""
    live = {(rel, module, attr) for rel, module, attr, _ln in _patch_points()}
    known = set(ALLOWED_PATCHES) | set(SAFE_PATCHES)
    new = [f"{rel}  patch {module}.{attr}"
           for rel, module, attr in sorted(live - known)]
    assert not new, (
        "新增了对被拆包的属性 patch —— 模块→包转换后它会**静默失效**:\n  "
        + "\n  ".join(new)
        + "\n修法: patch 目标改成显式接缝模块（`webgui/deps`）; 若确认调用点在包外"
          "（patch 依然生效）, 登记进 SAFE_PATCHES 并写明理由。")


def test_patch_whitelist_is_not_stale():
    """反向判据: 白名单里每条都必须仍然是真实 patch 点（搬完就该删, 忘了删 → 红）。"""
    live = {(rel, module, attr) for rel, module, attr, _ln in _patch_points()}
    stale = [f"{rel}  patch {module}.{attr}（{why}）"
             for (rel, module, attr), why in
             {**ALLOWED_PATCHES, **SAFE_PATCHES}.items()
             if (rel, module, attr) not in live]
    assert not stale, (
        "patch 白名单已过期（这些点已经不 patch 被拆包了, 请删条目）:\n  "
        + "\n  ".join(stale))
    print(f"    split-guard: 待收敛 {len(ALLOWED_PATCHES)} 处 / "
          f"确认安全 {len(SAFE_PATCHES)} 处")


# ---------------------------------------------------------------------------
# ③ 拆分后的**跨模块名字泄漏**（忘了 import）—— 2026-09-21 ○C8b 实测抓到的真 bug
# ---------------------------------------------------------------------------
#: 被拆出来的包（搬块时最容易漏 import 的地方）
#: ⭐ `core/digest/rounds`（2026-09-29 乙-1）就是"从 pipeline.py 按轮搬块"的产物 ——
#: 正是这条守门要盯的形状。
SPLIT_PKGS = ("webgui/bond", "core/bond/bond_story", "contract/records", "contract/streams",
              "core/digest/rounds")

#: 这些**项目模块名**如果被用到却没绑定, 一律报（`chat` 就是这么漏的:
#: 它不属于任何包内兄弟模块, 靠上面的兄弟名扫描抓不到）
KNOWN_MODULE_NAMES = frozenset({
    "chat", "deps", "paths", "store", "registry", "schema", "client",
    "state", "boards", "scene", "engine", "errors", "util",
})

_IMPLICIT = frozenset({
    "__name__", "__file__", "__doc__", "__package__", "__spec__", "__loader__",
    "__builtins__", "__debug__", "__class__", "__dict__", "self", "cls",
}) | frozenset(dir(builtins))          # `round` / `len` 这类内建名不算泄漏


def _names_in(path: pathlib.Path) -> tuple[set[str], set[str]]:
    """→ (本文件绑定的顶层名字, 运行期读取的裸名字)。

    `from __future__ import annotations` 下的**字符串注解**（`x: "Foo"`）是
    `ast.Constant`, 天然不计入"运行期读取"—— 这正是我们要的（那种写法的名字
    不评估, 不会 NameError; 见 `renderer/state.py` 的 `# noqa: F821` 先例）。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                bound.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.Global):
            bound |= set(node.names)
        elif isinstance(node, ast.Lambda):
            bound |= {a.arg for a in node.args.args}
    loaded = {n.id for n in ast.walk(tree)
              if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    return bound, loaded


def test_no_cross_module_name_leaks():
    """③ 搬块时"名字跟着走了、import 没跟"→ 运行期 `NameError`。

    为什么单开这条守门（○C8b 实测）: C4 把 `_ms_since` 搬进 `util.py` 时**漏了
    `lanes.py` 的 import**, C5 把 `chat` 从原 `bond.py` 搬走时也漏了一处 —— 两处都在
    `except Exception`（"宁缺勿错"保活）里面, 于是**测试全绿、功能静默失效**:
    标注 worker 每次都在写回状态前抛 NameError, `emo_version` 永不递增。

    判据: 包内某模块**运行期读了**一个裸名字, 而它既不绑定在本模块, 也不是内建/隐式名 ——
    却绑定在同一包的**兄弟模块**里（或名字命中 `KNOWN_MODULE_NAMES`）⇒ 报"八成漏了 import"。
    """
    problems: list[str] = []
    for pkg in SPLIT_PKGS:
        files = [p for p in sorted((ROOT / pkg).glob("*.py"))]
        per_file: dict[pathlib.Path, tuple[set[str], set[str]]] = {
            p: _names_in(p) for p in files}
        for p, (bound, loaded) in per_file.items():
            siblings: set[str] = set()
            for q, (qb, _ql) in per_file.items():
                if q != p:
                    siblings |= qb
            for name in sorted(loaded - bound - _IMPLICIT):
                if name in siblings or name in KNOWN_MODULE_NAMES:
                    problems.append(
                        f"{p.relative_to(ROOT).as_posix()}: 用了 `{name}` 但本模块没绑定"
                        f"（同包别的模块里有/是项目模块名）—— 漏 import?")
    assert not problems, (
        "拆分后疑似漏 import（运行期会 NameError, 而宽 except 会把它静默吞掉）:\n  "
        + "\n  ".join(problems))
    print("    split-guard: 拆分包内无跨模块名字泄漏（漏 import 守门）")
