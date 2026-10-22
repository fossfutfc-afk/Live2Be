"""动作词表（`core/bond/actions.py`）—— 闭合表 + 与情绪的拆分口径。

口径（与情绪同构）: 标注输出的每一格要么是情绪键, 要么是动作键; 写回时才拆成
`p["emotion"]`（恒为真情绪）与 `p["act"]`（可选）。本文件只管词表与拆分本身,
标注链路在 `test_emotion_text.py`。
"""
from __future__ import annotations

import logging

from core.bond.actions import (
    ACTION_NAMES,
    ACTIONS,
    MAX_ACTS_PER_BOARD,
    render_prompt_block,
    split_acts,
)

LEXICON = {"nomal", "smile", "outburst"}


def test_vocabulary_is_closed_lowercase_and_unique():
    """键 = 提示词照抄 = 前端 `ACT_SPECS` 的键: 恒小写, 不许重名。"""
    names = [a.name for a in ACTIONS]
    assert len(names) == len(set(names)), names
    assert names == [n.lower() for n in names], names
    assert all(n.isascii() and n.isalpha() for n in names), names
    assert set(names) == ACTION_NAMES


def test_prompt_block_lists_name_label_and_when():
    block = render_prompt_block()
    for a in ACTIONS:
        assert a.name in block, a.name
        assert a.label in block, a.label
        assert a.when in block, a.when


def test_split_acts_only_splits_action_keys():
    assert split_acts(["smile", "nomal"], LEXICON) == ["", ""]
    assert split_acts(["smile", "jump", "nomal"], LEXICON) == ["", "jump", ""]
    # 位置对齐: 拆出来的动作与原来的行号一一对应（写回按 id(p) 配对）
    assert split_acts(["jump", "smile", "hop"], LEXICON) == ["jump", "", "hop"]


def test_split_acts_emotion_wins_on_name_collision():
    """角色词表里真有同名键 → 当情绪（角色自己的表更有权威, 少一次跳不致命）。"""
    assert split_acts(["jump"], {"jump"}) == [""]


def test_split_acts_caps_per_board_and_leaves_a_grepable_log(caplog):
    """模型"每行都演" → 超上限的原地作废, 且留一条能 grep 的中文日志。"""
    keys = ["jump"] * (MAX_ACTS_PER_BOARD + 2)
    with caplog.at_level(logging.WARNING, logger="live2be.bond"):
        got = split_acts(keys, LEXICON)
    assert got.count("jump") == MAX_ACTS_PER_BOARD, got
    assert len(got) == len(keys)                       # 长度恒等于输入（不错位）
    assert any("act 超出每板上限" in r.message for r in caplog.records), \
        [r.message for r in caplog.records]


if __name__ == "__main__":
    for fn in sorted(k for k, v in globals().items() if k.startswith("test_")):
        fn()
    print("动作词表: 全部通过")
