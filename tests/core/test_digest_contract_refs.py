"""契约 md 里的 `【X】` 守门 —— 每个都得说得出出处（2026-10-12, 任务 1f）。

## 为什么要有这条

`【】`在这个项目里是**有语义的**（她眼前的括号一形一义, 见
`docs/CONTEXT_MARKS.md` / `core/brain/marks.py`）: **段头 = 材料名或契约自造的小节**。
契约 md 里写一个 `【X】`，就等于对她说"下面这一段叫 X" ——
如果 X 是**已经不存在的材料名**（料名改过、小节删过），那句话就是**假话**,
而它**不会报错**（契约文案没人跑、也没人对账）。

⭐ 这就是 `understand.md` 里那个 `canon` 能烂掉一整族而没人发现的机制:
**没人跑的契约文本, 就是没人会发现它过期的文本**。
这条用例把"对账"自动化: 名字从**真源 AST 取**, 零维护。

## 三类合法出处

| 类 | 真源 | 取法 |
|---|---|---|
| **契约自造的小节** | 契约 md 自己（行首 `【X】…` 定义过） | 扫 `contract/digest/prompts/**/*.md` |
| **料名** | `ROUNDS[*].material` | `ast` 取每项（字符串, 或 `(名, 文本)` 对的第一项） |
| **时间线的板块标签** | `core/session/renderer.py::_LABELS` | 取 `【…】` 里的名字（`[28] 【羁绊剧情】` 那种引用） |

⚠️ **`【】` 不是强调号** —— 正文里想加粗请用 `**…**`（`row_fields.md` 原来写的
`【哪一段】` 就是这么一处误用, 2026-10-12 改掉了）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_MD = ROOT / "contract" / "digest" / "prompts"
LLM_MD = ROOT / "llm" / "prompts"
ROUNDS_PY = ROOT / "core" / "digest" / "rounds" / "__init__.py"
RENDERER_PY = ROOT / "core" / "session" / "renderer.py"

BRACKET = re.compile(r"【([^】\n]{1,60})】")
MULTI_SPACE = re.compile(r"\s+")
#: 名字尾巴上的**注解**（`角色人设（锚点）` / `本次新经历（含引擎候选标注）`）
ANNOTATION = re.compile(r"[（(][^）)]*[）)]")


def _norm(name: str) -> str:
    """去空白归一 —— 契约里抄名字时多打一个空格不算错。"""
    return MULTI_SPACE.sub("", name)


def _norm_loose(name: str) -> str:
    """归一 + **摘掉注解** —— 只用于"料名有没有被文案提到过"那个方向。"""
    return ANNOTATION.sub("", _norm(name))


def _material_names() -> set[str]:
    """`ROUNDS[*].material` 的每一项（AST —— 不执行代码, 不 grep 注释）。"""
    tree = ast.parse(ROUNDS_PY.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "material":
                continue
            for elt in getattr(kw.value, "elts", []):
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.add(_norm(elt.value))
                elif isinstance(elt, ast.Tuple) and elt.elts:
                    first = elt.elts[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        out.add(_norm(first.value))
    return out


def _timeline_labels() -> set[str]:
    """时间线板块标签（`[28] 【羁绊剧情】` 那种）。

    ⚠️ 从 `_LABELS` 的**值**取（`"【羁绊剧情】"` → `羁绊剧情`）——
    新增一种事件类型而忘改契约, 这条会告诉她"契约里那个名字还没跟上"。
    """
    tree = ast.parse(RENDERER_PY.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        # ⚠️ 它是**带注解**的赋值（`_LABELS: dict[str, str] = {…}`）⇒ `AnnAssign`,
        # 不是 `Assign` —— 只认 `Assign` 会静默取到空集（这条用例自己栽过一次）。
        targets: list[ast.expr] = []
        value = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if not any(isinstance(t, ast.Name) and t.id == "_LABELS" for t in targets):
            continue
        if not isinstance(value, ast.Dict):
            continue
        for val in value.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                out.update(BRACKET.findall(val.value) or [val.value])
    return {_norm(n) for n in out}


def _contract_md() -> list[Path]:
    return sorted(CONTRACT_MD.rglob("*.md"))


def _all_md() -> list[Path]:
    """她看得见的 **digest 文本家族** —— 契约侧全量 + llm 侧的 `digest_*.md`。

    ⚠️ **为什么排掉 mmt/bond 那几份规则书**（`momotalk_rules.md` /
    `bond_story_rules.md` / `bond_shots.md`）: 它们的段头**不是契约**
    （没有 `_sections_for` 那种"表必须与实际一致"的硬约束）, 而 `【】` 在那里
    还当三种别的东西用: 角色代称（`【你（当前角色）】`）、序数小节
    （`见上面【二】的组合拳`）、以及**短形式交叉引用**（`【回忆】专段`）。
    那几处要不要收, 是**另一件事**（记在 PROCEED, 等用户裁）——
    本守门只管"料名是契约"的那一族。
    """
    return sorted(list(CONTRACT_MD.rglob("*.md")) + list(LLM_MD.glob("digest_*.md")))


def _defined_sections() -> set[str]:
    """md 里**行首定义**的 `【X】…`（= 契约自己造的小节 / 段头标题）。"""
    out: set[str] = set()
    for p in _all_md():
        for line in p.read_text(encoding="utf-8").split("\n"):
            m = re.match(r"【([^】]{1,60})】", line)
            if m:
                out.add(_norm(m.group(1)))
    return out


def test_every_bracket_in_prompts_has_a_home():
    """**digest 家族的 md**（契约侧全量 + llm 侧 `digest_*.md`）里每个 `【X】` 都要有出处。

    三类合法出处: 自造小节（行首定义过）/ 料名（`ROUNDS[*].material`）/
    时间线板块标签（`core/session/renderer.py::_LABELS`）。

    ⭐ **为什么这份值钱**: 段头 `【X】` 是**引擎印的**（`marks.section(title)`），
    而 `_sections_for` 又拿 `ROUNDS[*].material` 跟实际段头**逐字对账** ⇒
    料名是一个**真契约**。而"文案里引用的那个名字"没有任何东西对账 ——
    2026-10-12 这条用例第一次跑就抓到 `digest_relate.md` 把
    `【本次新经历（含引擎候选标注）】` 写成了 `【本次新经历】`（同一个东西两个名字）。
    """
    materials = _material_names()
    labels = _timeline_labels()
    defined = _defined_sections()
    known = materials | labels | defined
    assert materials, "料名一个都没取到 —— AST 取法过期了？"
    assert labels, "时间线标签一个都没取到 —— `_LABELS` 改名了？"

    unknown: list[str] = []
    for p in _all_md():
        for i, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            for hit in BRACKET.findall(line):
                if _norm(hit) not in known:
                    unknown.append(f"{p.relative_to(ROOT)}:{i} 【{hit}】")
    if unknown:
        raise AssertionError(
            "这些 `【X】` 说不上出处（料/小节改名了？还是把 `【】` 当强调号用了？）:\n  "
            + "\n  ".join(unknown)
            + f"\n合法出处 {len(known)} 个: 料名 {len(materials)} · 时间线标签 {len(labels)}"
            f" · 自造小节 {len(defined)}")
    print(f"    {len(_all_md())} 份 md 的 `【X】` 全部有出处"
          f"（料名 {len(materials)} / 时间线标签 {len(labels)} / 自造小节 {len(defined)}）")


def test_material_names_are_not_dead():
    """⭐ 反向：**料名必须真的出现在某份"她看得见的" md 里** —— 否则是"料还在、没人提"。

    与上一条互补: 上一条防"文案提到不存在的东西", 这一条防"存在的东西没人讲"。
    ⚠️ 比较时**两边的 `（…）` 注解都摘掉** —— 段头带注解是本项目的常态
    （`【角色人设（锚点）】`/`【现有经历（候选）】`），料名表里也可能只写主名。
    """
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in _all_md())
    normalized = _norm_loose(corpus)
    missing = sorted(n for n in _material_names() if _norm_loose(n) not in normalized)
    # ⚠️ 白名单 = **有意的**不在 md 里点名的料（每个都要写为什么）。
    allowed: dict[str, str] = {}
    real = [n for n in missing if n not in allowed]
    assert not real, (
        "这些料名在契约 md 与 llm prompt md 里都没出现 —— 料加了/改了名而文案没跟上:\n  "
        + "\n  ".join(f"{n}" for n in real))
    print(f"    料名 {len(_material_names())} 个, 文案里全部点到过")


if __name__ == "__main__":
    test_every_bracket_in_prompts_has_a_home()
    test_material_names_are_not_dead()
