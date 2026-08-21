"""llm/prompts 回归 — load_prompt 从 md 加载 prompt。

运行: python -m pytest tests/llm/test_prompts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.prompts import load_prompt

PASS = 0
FAIL = 0


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS {name}")
    except Exception as e:  # noqa: BLE001
        FAIL += 1
        print(f"  FAIL {name}: {type(e).__name__}: {e}")


def test_load_momotalk_rules():
    text = load_prompt("momotalk_rules")
    assert text.startswith("【MomoTalk 行为规则】"), text
    assert "简短自然" in text
    assert "聊天。" in text


def test_load_behavior_rules():
    text = load_prompt("behavior_rules")
    assert "【回复要求】" in text
    assert "OOC" in text
    assert "sensei 或 老师。" in text


def test_no_trailing_whitespace():
    text = load_prompt("momotalk_environment")
    assert not text.endswith("\n"), "load_prompt 应 strip 尾随空白"


def test_missing_raises_with_list():
    try:
        load_prompt("definitely_not_exist")
    except FileNotFoundError as e:
        assert "definitely_not_exist.md" in str(e)
        assert "可用" in str(e)
    else:
        raise AssertionError("缺失文件应抛 FileNotFoundError")


if __name__ == "__main__":
    for fn in (
        test_load_momotalk_rules,
        test_load_behavior_rules,
        test_no_trailing_whitespace,
        test_missing_raises_with_list,
    ):
        check(fn.__name__, fn)
    print(f"\nllm/prompts 回归: {PASS}/{PASS + FAIL} 通过")
    sys.exit(1 if FAIL else 0)
