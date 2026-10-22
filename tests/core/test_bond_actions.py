"""动作词表（`core/bond/actions.py`）—— 闭合表 + 提示词块。

口径: 动作**不是第二种输出**, 而是那一行键的第二段（`"情绪键|动作键"`）——
所以本文件只管词表本身; 拆分与兜底在 `core/bond/emo_text.py::_split_value`
（用例在 `test_emotion_text.py`）。
"""
from __future__ import annotations

from core.bond.actions import (
    ACTION_NAMES,
    ACTIONS,
    MAX_ACTS_PER_BOARD,
    render_prompt_block,
)


def test_vocabulary_is_closed_lowercase_and_unique():
    """键 = 提示词照抄 = 前端 `ACT_SPECS` 的键: 恒小写, 不许重名。"""
    names = [a.name for a in ACTIONS]
    assert len(names) == len(set(names)), names
    assert names == [n.lower() for n in names], names
    assert all(n.isascii() and n.isalpha() for n in names), names
    assert set(names) == ACTION_NAMES
    assert MAX_ACTS_PER_BOARD >= 1


def test_prompt_block_lists_name_label_and_when():
    block = render_prompt_block()
    for a in ACTIONS:
        assert a.name in block, a.name
        assert a.label in block, a.label
        assert a.when in block, a.when


if __name__ == "__main__":
    for fn in sorted(k for k, v in globals().items() if k.startswith("test_")):
        fn()
    print("动作词表: 全部通过")
