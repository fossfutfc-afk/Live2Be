"""`contract/schema/` 的**文案守门** —— 三个方向: 名字 · 取值 · 结构。

## 为什么要有这三条

2026-10-14 把 `schema.py` 里的 2.6 KB 文案搬进了 `prompts/*.md`（人可改、可 diff）。
搬出去之后，**代码不再认识那些字** —— 于是"文案里说的东西"与"引擎里真有的东西"
之间只靠人记得对齐。这三条把对账自动化（与 `test_digest_contract_refs.py` 同一手法:
名字从真源 AST 取, 零维护）:

  ① **动作名**：文案里写到的 `mmt_*` 必须在注册表里；**被封印的（`in_prompt=False`）
     不许出现在契约里**（承诺一个不发的动作是假话）
  ② **取值**：记录流的取值表必须与 `contract.records` 的文法常量一致
  ③ **结构**：规则 md 是干净的 `- ` 列表（解析不会静默吞东西）+ 渲染出来的编号连续

⚠️ 三条都是"两边必须同时改"的守门: 只改一边 ⇒ 这里红。
"""
from __future__ import annotations

import re

from contract import records as R
from contract.registry import MMTActionRegistry
from contract.schema.prompts import load
from core.mmt.mmt_actions import build_mmt_registry

#: 行流的三份文案（外壳 / 规则 / 示例）—— 动作名可能在**任何**一份里
_LINE_MD = ("line", "line_rules", "line_examples")


def test_action_names_in_copy_exist_in_registry():
    """① 文案里的 `mmt_*` 名字必须在注册表里，且**封印的动作不许被承诺**。"""
    reg = build_mmt_registry()
    prompted = {name for name, _ in reg.prompt_specs()}
    sealed = {name for name, _ in reg.specs()} - prompted
    assert prompted, "注册表里一个可注入动作都没有 —— 取法过期了？"
    assert sealed == {"mmt_send_media"}, (
        f"被封印的动作集合变了: {sorted(sealed)}——'封印就不许出现在契约里'这条仍成立, "
        "但要确认这是有意的")

    text = "\n".join(load(n) for n in _LINE_MD)
    found = set(re.findall(r"\bmmt_[a-z_]+", text))
    assert found, "一个动作名都没扫到 —— 正则过期了？"
    unknown = sorted(found - prompted)
    assert not unknown, (
        f"这些动作名写在契约文案里, 注册表里却没有（改名了？删了？）: {unknown}\n"
        f"（在 prompt 里的动作: {sorted(prompted)}）")
    promised_sealed = sorted(found & sealed)
    assert not promised_sealed, (
        f"被封印的动作出现在契约里（⛔ 它不进 prompt, 契约不该承诺它）: {promised_sealed}")


def test_record_values_match_grammar():
    """② 记录流取值表 ↔ `contract.records` 文法常量对账（md 是**复述**, 不许自己走）。"""
    text = load("record")
    listed = set(re.findall(r'\{"(?:character|stage)": "([a-z_]+)"', text))

    # `exit` 是**解析层遗留值**（旧档回放要认）—— 按 A1 裁决**不注入**给 LLM
    # （见 docs/DESIGN_MEMORIAL.md）⇒ 期望值 = 文法常量 − 它。
    want_chars = {R.CHARACTER_NARRATOR, R.CHARACTER_SENSEI}
    want_stages = set(R.STAGE_VALUES) - {R.STAGE_EXIT}
    want = want_chars | want_stages
    assert listed == want, (
        "取值表与文法常量不一致（只改了一边？）:\n"
        f"  文案里多出: {sorted(listed - want)}\n"
        f"  文案里少了: {sorted(want - listed)}\n"
        "⚠️ 改取值就要**同改** `contract/records/grammar.py` 与 `prompts/record.md`")
    assert R.STAGE_EXIT not in listed, "`exit` 是遗留值, 不许进 prompt（A1 裁决）"

    # 每条取值都要真在值表里露面（不是只被正则扫到）
    for value in sorted(want):
        assert f'"{value}"' in text, f"值表里没有 {value!r} 那一行"


def test_rules_are_a_clean_bullet_list():
    """③ 规则 md = 干净的 `- ` 列表；渲染出来的编号连续（`_numbered` 的不变量）。"""
    from contract.schema.lines import build_line_schema
    from contract.schema.records import build_record_schema

    want_counts = {"line": 6, "record": 6}        # ⚠️ 改规则条数就改这里（有意的动作）
    for form, want in want_counts.items():
        raw = load(f"{form}_rules")
        rows = raw.split("\n")
        items = [ln for ln in rows if ln.startswith("- ")]
        assert len(items) == want, f"{form}_rules.md 有 {len(items)} 条, 期望 {want}"
        noise = [ln for ln in rows if ln.strip() and not ln.startswith("- ")]
        assert not noise, (
            f"{form}_rules.md 里有不是列表项的行（会被解析静默吞掉）: {noise}")
        assert all(len(it) > 3 for it in items), f"{form}_rules.md 有空条目"

    # 渲染后编号必须是 1..N 连续（`_numbered` 按位置算 —— 手写编号会在这里露馅）
    for form, text in (("line", build_line_schema(build_mmt_registry())),
                       ("record", build_record_schema())):
        ruled = [ln for ln in text.split("\n") if re.match(r"^\d+\. ", ln)]
        assert [ln.split(".", 1)[0] for ln in ruled] == \
            [str(i) for i in range(1, want_counts[form] + 1)], (
                f"{form} 的硬规则编号不连续: {[ln[:8] for ln in ruled]}")


def test_schema_module_is_a_package_and_path_is_stable():
    """`contract.schema` 的**名字**没变（module → package）⇒ 两种 import 写法都活着。"""
    import contract
    import contract.schema as pkg
    from contract.schema import build_line_schema, build_record_schema

    assert pkg.__file__.replace("\\", "/").endswith("contract/schema/__init__.py")
    assert callable(build_line_schema) and callable(build_record_schema)
    for name in ("build_line_schema", "build_record_schema"):
        assert hasattr(contract, name), f"门面 `contract` 少了 {name}（调用点会炸）"


def test_empty_registry_still_renders():
    """空注册表不炸（早退分支）——搬 md 时最容易丢掉的那条路。

    ⚠️ 判据只能看**动作表那一段**: 硬规则与示例里本来就会提到动作名
    （那是用法纪律, 不是清单）——第一版写成了"全文不含 mmt_look", 当场红。
    """
    from contract.schema import build_line_schema
    text = build_line_schema(MMTActionRegistry())
    assert "可用操作:" in text
    table = text.split("可用操作:", 1)[1].split("\n")
    assert not [ln for ln in table if ln.startswith("  - ")], "空注册表却列出了动作"


if __name__ == "__main__":
    test_action_names_in_copy_exist_in_registry()
    test_record_values_match_grammar()
    test_rules_are_a_clean_bullet_list()
    test_schema_module_is_a_package_and_path_is_stable()
    test_empty_registry_still_renders()
    print("schema 文案守门: 5/5")
