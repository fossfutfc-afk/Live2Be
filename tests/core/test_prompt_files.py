"""`contract.prompt_files.load_md` —— md 文案的**唯一读法**（`llm/prompts` 与契约层共用）。

从前两个消费方各写一份, 形状逐行相同（目录 + 名字 → strip 读 + 找不到时列清单），
连错误格式都不一样（一个走 `err("NotFound")`, 一个裸 `FileNotFoundError`）。
"""
from __future__ import annotations

import pytest

from contract.digest.prompts import load as load_contract
from contract.prompt_files import load_md
from llm.prompts import load_prompt


def test_reads_and_strips(tmp_path):
    (tmp_path / "a.md").write_text("\n 正文 \n\n", encoding="utf-8")
    assert load_md(tmp_path, "a", what="测试") == "正文"


def test_missing_lists_that_folder(tmp_path):
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "b.md").write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError) as e:
        load_md(tmp_path, "nope", what="测试")
    msg = str(e.value)
    assert "nope.md" in msg and "可用" in msg and "测试" in msg
    assert "a" in msg and "b" in msg


def test_missing_in_subdir_lists_that_subdir(tmp_path):
    """⚠️ 清单要列**它所在那一层** —— `parts/` 里缺一份时, 别把顶层相位文件列出来。"""
    sub = tmp_path / "parts"
    sub.mkdir()
    (sub / "row_fields.md").write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError) as e:
        load_md(tmp_path, "parts/nope", what="测试")
    msg = str(e.value)
    assert "row_fields" in msg and "parts/" in msg


def test_both_consumers_share_one_implementation():
    """两个真消费方都能读, 且**同一套报错形状**（一个实现, 不是两份）。"""
    assert load_prompt("momotalk_rules").startswith("【MomoTalk 行为规则】")
    assert load_contract("split").startswith("{{discipline}}")
    for fn, what in ((load_prompt, "prompt"), (load_contract, "digest 契约")):
        with pytest.raises(FileNotFoundError) as e:
            fn("definitely_not_exist")
        assert f"{what} md 不存在" in str(e.value)
        assert "可用" in str(e.value)


def test_error_names_the_loader_not_the_caller():
    """⚠️ 出错前缀是 `[prompt_files.py]` —— "文件找不到"发生在加载器里, 这是有意的。"""
    with pytest.raises(FileNotFoundError) as e:
        load_prompt("definitely_not_exist")
    assert "[prompt_files.py][NotFound]" in str(e.value)
