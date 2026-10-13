"""`contract.slots.render_template` —— `{{名字}}` 填槽，两个方向都对不上就炸。

它替掉的是裸 `text.replace("{{x}}", v)`：那种写法下「模板没这个槽」与「有槽没给值」
**两种错都静默**，而后者会让 `{{x}}` 原样进 system prompt（她看得见字面量）。
"""
from __future__ import annotations

import pytest

from contract.slots import render_template


def test_fills_a_slot():
    assert render_template("A{{x}}B", {"x": "1"}) == "A1B"


def test_fills_every_occurrence():
    """同一槽出现多次 —— 全填（`sub` 单遍扫完，不是只替第一处）。"""
    assert render_template("{{x}}-{{x}}", {"x": "9"}) == "9-9"


def test_no_slots_and_no_values_is_a_noop():
    assert render_template("纯文本 {不碰}", {}) == "纯文本 {不碰}"


def test_value_is_not_rescanned():
    """值里的 `{{...}}` 不再被二次替换 —— 填进去的就是字面值。"""
    assert render_template("{{a}}", {"a": "{{b}}"}) == "{{b}}"


def test_template_has_a_slot_but_no_value_raises():
    with pytest.raises(ValueError) as e:
        render_template("这里有 {{digest_schema}}", {})
    assert "digest_schema" in str(e.value)


def test_value_given_for_a_slot_the_template_lacks_raises():
    """调用方以为填了、模板里其实没有 —— 从前这里的 `replace` 是静默 no-op。"""
    with pytest.raises(ValueError) as e:
        render_template("没有槽", {"digest_schema": "x"})
    assert "digest_schema" in str(e.value)


def test_where_is_printed_to_locate_the_call_site():
    with pytest.raises(ValueError) as e:
        render_template("{{a}}", {}, where="split.md")
    assert "split.md" in str(e.value)


@pytest.mark.parametrize("bad", ["{{}}", "{{9x}}", "{{ a }}", "{a}"])
def test_only_well_formed_slots_count_as_slots(bad):
    """`{{}}` / `{{9x}}` / `{{ a }}` / 单花括号都**不算槽** ⇒ 当字面量原样留下。"""
    assert render_template(bad, {}) == bad
