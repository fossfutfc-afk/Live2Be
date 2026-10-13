"""llm/prompts 回归 — load_prompt 从 md 加载 prompt。

运行: python -m pytest tests/llm/test_prompts.py
"""
import re
import sys
from pathlib import Path

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


def test_no_single_brace_slots_left():
    """⭐ **槽写法只有一种**（`{{名字}}`, 2026-10-12 统一）—— 谁改回 `{名字}` 这条先红。

    为什么要有这条: 单花括号的填法是 `.replace("{x}", v)` —— 两个方向**都静默**
    （模板没这个槽 ⇒ 什么也没发生; 有槽没给值 ⇒ `{x}` 原样进 system prompt）。
    这一刀在 `llm/prompts/` 里改掉了 9 份 md / 43 处槽; 顺便炸出两处**一直在空转**
    的替换（`bond_story_rules.md` 与 `bond_shots.md` 里的 `{char_name}`）。

    ⚠️ 判据只看**标识符形状**的 `{name}` —— JSON 示例里的 `{"key": …}`（`{` 后是
    引号）与已经双写的 `{{name}}` 都不算。
    """
    slot = re.compile(r"(?<!\{)\{([a-z_][a-z0-9_]*)\}")
    md_dir = Path(__file__).resolve().parents[2] / "llm" / "prompts"
    bad: list[str] = []
    for p in sorted(md_dir.glob("*.md")):
        for hit in slot.findall(p.read_text(encoding="utf-8")):
            bad.append(f"{p.name}: {{{hit}}}")
    assert not bad, f"还有单花括号槽（改成 {{{{名字}}}}）: {bad}"


if __name__ == "__main__":
    for fn in (
        test_load_momotalk_rules,
        test_load_behavior_rules,
        test_no_trailing_whitespace,
        test_missing_raises_with_list,
        test_no_single_brace_slots_left,
    ):
        check(fn.__name__, fn)
    print(f"\nllm/prompts 回归: {PASS}/{PASS + FAIL} 通过")
    sys.exit(1 if FAIL else 0)
