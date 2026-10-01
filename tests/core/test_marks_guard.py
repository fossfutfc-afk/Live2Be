# -*- coding: utf-8 -*-
"""`marks.py` 守门 —— **括号与信息头只有一处实现**（用户 2026-09-29 裁决）。

> 用户原话：*"就是太散了……我希望有一个统一管理的地方，不然只会越来越乱。"*

**散在哪**（2026-09-29 之前）: 写侧**五份各拼各的 f-string**（她视图 / L2 认知 /
R2 新经历 / R4 新经历 / R3 新节点）—— 而读侧只有一份（`address.normalize_title`）。
名字在写侧有五个出处 ⇒ 任一处漂了, 她照抄回来的名字就**静默命中 0**；
这不是假想: N2 那次改了五处里的一处, 另外两处一直写着 `「标题」` 到今天。

所以这里钉五件事（都是"约定", 不钉就会烂掉）:

  ① **代码字面量里不许再出现 `《》〔〕｜`**（⚠️ docstring / 注释**不算** —— 文档必须
     能引用形状; 扫的是 `ast` 里的字符串常量, 不是源码文本）
  ② **她的视图永不印编号** —— `render._memory_line` 调 `marks.head` 时**不许给 `key`**
     （"编号绝不进她的视图"是地址地基那条; `render_recall_block` 走同一个函数 ⇒ 一并覆盖）
  ③ **格序固定 + 空字段不占位** —— `head` 出来的那一串逐字钉死（改形状要在这里改）
  ④ **印与剥同源** —— `marks.name()` 出来的串, `address.normalize_title()` 必须认回原名
  ⑤ **`marks` 运行时零依赖** —— 否则又会有人为了用它去加延迟 import（那正是它
     单独成一件的理由: `render` 与 `notes` 之间已经有环）
"""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

from core.brain.wiki_v2 import address, make_node, marks

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "core" / "brain" / "wiki_v2"
#: 唯一允许持有括号字面量的文件（它自己就是那个"一处"）
SKIP = {"marks.py"}
#: 信息头那一族（段头 `【】` 不在内 —— 它的构造已经在 `marks.section`, 而其余几处
#: 都是"整段就是它自己"的常量, 钉它只会把常量逼成函数调用）
FORBIDDEN = (marks.NAME_OPEN, marks.NAME_CLOSE,
             marks.HEAD_OPEN, marks.HEAD_CLOSE, marks.FIELD_SEP)

_NOW = datetime(2026, 9, 29, 12, 0, 0)


def _ep(text, *, title="", ts="", sig=0.5):
    kw = dict(text=text, significance=sig, ts=ts)
    if title:
        kw["title"] = title
    return make_node("episode", **kw)


def _code_strings(path: Path) -> list[tuple[int, str]]:
    """文件里**代码用到的**字符串常量（docstring 除外）。f-string 的字面段也在内。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None) or []
        first = body[0] if body else None
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            docs.add(id(first.value))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docs):
            out.append((node.lineno, node.value))
    return out


def test_no_stray_marks_in_code_literals():
    """① 除 `marks.py` 外, `core/brain/wiki_v2/` 的**代码**里不许再手写括号。"""
    bad: list[str] = []
    for p in sorted(PKG.rglob("*.py")):
        if p.name in SKIP or "__pycache__" in p.parts:
            continue
        for lineno, s in _code_strings(p):
            hit = [c for c in FORBIDDEN if c in s]
            if hit:
                bad.append(f"{p.relative_to(ROOT).as_posix()}:{lineno}: {s[:40]!r} 含 {hit}")
    assert not bad, ("还有手写的括号字面量（请改调 marks.head / marks.name / marks.section）:\n  "
                     + "\n  ".join(bad))
    n = len(list(PKG.glob("*.py"))) - len(SKIP)
    print(f"    {n} 个模块: 零手写括号（唯一实现 = marks.py）")


def test_her_view_never_prints_an_id():
    """② `_memory_line` 不许给 `key`（她的视图里**编号绝不出现**）。"""
    tree = ast.parse((PKG / "render.py").read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_memory_line":
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "head" and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == "marks"):
                    calls.append(sub)
    assert len(calls) == 1, f"_memory_line 里 marks.head 的调用点应恰好 1 个, 实得 {len(calls)}"
    call = calls[0]
    assert not [k for k in call.keywords if k.arg == "key"], \
        "她的视图里出现了 key=…（编号绝不进她的视图）"
    assert len(call.args) == 1, f"marks.head 只该收到 node, 实得 {len(call.args)} 个位置参数"
    print("    _memory_line: 只传 node（无编号）——召回段走同一函数, 一并覆盖")


def test_head_shape_is_pinned():
    """③ 格序固定 + 空字段不占位 + 一个字段都没有 ⇒ 整段不出现。"""
    bare = _ep("今天又去看了杂草")
    assert marks.head(bare) == "", marks.head(bare)          # 无钥匙/无名/不要时间 ⇒ 空串

    assert marks.head(_ep("…", title="看杂草"), key="m0002") == "〔m0002｜《看杂草》〕"
    full = _ep("…", title="看杂草", ts="2026-09-25T10:00:00")
    assert marks.head(full, key="m0002", kind=True, now=_NOW,
                      extra=["被引 3"]) == "〔m0002｜《看杂草》｜episode｜4 天前｜9/25｜被引 3〕"
    # 她那一路（无编号 · 无类型 · 有时间 · 珍贵档那一格由读者给说法）
    assert marks.head(full, now=_NOW, extra=["难忘"]) == "〔《看杂草》｜4 天前｜9/25｜难忘〕"
    # 哨兵纪律: 不给 now ⇒ 时间两格都不出现（不编一个"很久以前"）
    assert marks.head(full, key="m0002") == "〔m0002｜《看杂草》〕"
    # 没名字 ⇒ 只留钥匙（不印"（无题）"这种假名字）
    assert marks.head(bare, key="m0002") == "〔m0002〕"
    print("    head 形态: 钥匙→名字→类型→相对→绝对→读者字段; 空的不占位")


def test_name_roundtrips_through_address():
    """④ 印（`marks.name`）与剥（`address.normalize_title`）**同一份字符集**。"""
    for t in ("中秋的杂草屋", "模型店", "苔藓·约定", "看 杂草"):
        printed = marks.name(t)
        assert printed == f"《{t}》", printed
        assert address.normalize_title(printed) == t, printed
        # 她把整段元信息一起抄回来（`《名》｜4 天前｜9/26`）也要认得出
        assert address.normalize_title(f"{printed}{marks.FIELD_SEP}4 天前") == t
    assert marks.name("") == "" and marks.name(None) == ""
    print("    name: 印剥同源（含'整段抄回来'那条）")


def test_marks_is_runtime_dependency_free():
    """⑤ `marks.py` **import 期**零依赖（零 IO / 不碰 store / 不会有环）。

    ⚠️ 只看**模块级** import: 函数里的延迟 import 是允许的（`kind_tag` 借
    `notes.CLOSED_WORDS`、时间两格借 `worldtime.age` —— 都是"用到才拉", 不成环）。
    """
    tree = ast.parse((PKG / "marks.py").read_text(encoding="utf-8"))
    mods: set[str] = set()
    for n in tree.body:                       # ⚠️ tree.body = 模块级, 不 ast.walk
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0:
            mods.add((n.module or "").split(".")[0])
    assert mods <= {"__future__", "typing"}, mods
    print(f"    marks 的 import 期依赖: {sorted(mods)}（无环风险）")


if __name__ == "__main__":
    test_no_stray_marks_in_code_literals()
    test_her_view_never_prints_an_id()
    test_head_shape_is_pinned()
    test_name_roundtrips_through_address()
    test_marks_is_runtime_dependency_free()
    print("all marks guard tests passed")
