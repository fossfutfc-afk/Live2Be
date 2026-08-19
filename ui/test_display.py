# -*- coding: utf-8 -*-
"""ui/ 展示层回归测试 — 清理后的功能验证（everything works well）。

覆盖范围:
    streaming       LineBuffer 断句 / 不丢字符 / flush 遗留
                    TypingDelay 首句零延迟 / 实例独立 / reset
    display         MomoTalkOutput 气泡+延迟+去括号 / flush 遗留 / 实例独立
                    BondStoryOutput 段落分割
    text_processors 去括号 / 断句 / 前缀格式化
    集成            import ui + core.momotalk + core.bond_story

用法: python ui/test_display.py   （需项目根环境, 推荐 live2be env）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui import (
    BondStoryOutput,
    LineBuffer,
    MomoTalkOutput,
    TypingDelay,
    _process_for_momotalk,
    format_momotalk_reply,
    strip_name_prefix,
)

# ----------------------------------------------------------------------------
# 迷你测试框架: @check 注册, main() 统一执行
# ----------------------------------------------------------------------------

_TESTS: list[tuple[str, callable]] = []
_PASS = 0
_FAIL = 0
_FAILURES: list[tuple[str, Exception]] = []


def check(name: str):
    """装饰器: 只把 (名字, 函数) 注册进 _TESTS, 不在 import 时执行。"""
    def deco(fn):
        _TESTS.append((name, fn))
        return fn
    return deco


# ============================================================================
# LineBuffer
# ============================================================================

@check("LineBuffer 多句切分 + 标点贴回")
def _t_linebuffer_split():
    lb = LineBuffer()
    assert lb.feed("你好。今天好。明天好。") == ["你好。", "今天好。", "明天好。"]


@check("LineBuffer 连续标点不丢（你好！！）")
def _t_linebuffer_consecutive_punct():
    lb = LineBuffer()
    assert lb.feed("你好！！") == ["你好！！"]
    lb2 = LineBuffer()
    assert lb2.feed("你太过分了吧？？！！") == ["你太过分了吧？？！！"]


@check("LineBuffer 逐字符喂入不丢字符（全标点 chunk 边界）")
def _t_linebuffer_charbychar_lossless():
    s = "你太过分了吧？？！！我们慢慢来。明天见！"
    lb = LineBuffer()
    out: list[str] = []
    for ch in s:
        out.extend(lb.feed(ch))
    rem = lb.flush()
    if rem:
        out.append(rem)
    assert "".join(out) == s, f"丢字: 得 {''.join(out)!r}"


@check("LineBuffer 分块累积（跨 chunk 断句）")
def _t_linebuffer_chunked():
    lb = LineBuffer()
    assert lb.feed("你") == []
    assert lb.feed("好") == []
    assert lb.feed("。今天") == ["你好。"]
    assert lb.feed("好！") == ["今天好！"]
    assert lb.flush() is None


@check("LineBuffer 孤立标点 chunk 不丢")
def _t_linebuffer_isolated_punct():
    lb = LineBuffer()
    out: list[str] = []
    out.extend(lb.feed("你好"))
    out.extend(lb.feed("！"))
    out.extend(lb.feed("！"))
    out.extend(lb.feed("再见"))
    out.extend(lb.feed("。"))
    rem = lb.flush()
    if rem:
        out.append(rem)
    assert "".join(out) == "你好！！再见。", f"得 {''.join(out)!r}"


@check("LineBuffer flush 取回遗留")
def _t_linebuffer_flush():
    lb = LineBuffer()
    assert lb.feed("你好。今天") == ["你好。"]
    assert lb.flush() == "今天"


# ============================================================================
# TypingDelay
# ============================================================================

@check("TypingDelay 首句零延迟, 后续有延迟")
def _t_typing_first():
    d = TypingDelay()
    assert d.for_bubble("a") == 0.0
    assert d.for_bubble("b") > 0.0


@check("TypingDelay 实例独立（修复类属性共享）")
def _t_typing_independent():
    a = TypingDelay()
    b = TypingDelay()
    assert a.for_bubble("x") == 0.0
    assert b.for_bubble("y") == 0.0   # 修复前共享类属性, 这里会 >0
    assert a.for_bubble("z") > 0.0


@check("TypingDelay reset 后首句再零延迟")
def _t_typing_reset():
    d = TypingDelay()
    d.for_bubble("a")
    d.for_bubble("b")
    d.reset()
    assert d.for_bubble("c") == 0.0


# ============================================================================
# MomoTalkOutput
# ============================================================================

@check("MomoTalkOutput feed 气泡 + 去括号 + 延迟")
def _t_momotalk_feed():
    d = MomoTalkOutput(_process_for_momotalk, "遥花")
    out = list(d.feed("（轻笑）你好。今天天气不错呢！"))
    assert out[0][0] == "[遥花]: 你好。", f"得 {out[0][0]!r}"
    assert out[0][1] == 0.0
    assert out[1][0] == "[遥花]: 今天天气不错呢！", f"得 {out[1][0]!r}"
    assert out[1][1] > 0.0


@check("MomoTalkOutput flush 取回遗留")
def _t_momotalk_flush():
    d = MomoTalkOutput(_process_for_momotalk, "遥花")
    out = list(d.feed("你好。还没说完"))
    assert out == [("[遥花]: 你好。", 0.0)]
    out2 = list(d.flush())
    assert out2[0][0] == "[遥花]: 还没说完"


@check("MomoTalkOutput 实例独立（各自首句零延迟）")
def _t_momotalk_independent():
    a = MomoTalkOutput(_process_for_momotalk, "A")
    b = MomoTalkOutput(_process_for_momotalk, "B")
    aa = list(a.feed("甲。"))
    bb = list(b.feed("乙。"))
    assert aa[0][1] == 0.0
    assert bb[0][1] == 0.0   # 修复前 TypingDelay 类属性共享, 这里会 >0


# ============================================================================
# BondStoryOutput
# ============================================================================

@check("BondStoryOutput 段落分割 + 轮询")
def _t_bondstory():
    v = BondStoryOutput()
    for tok in ["（望向远方）", "\n\n我记得", "那年夏天。"]:
        v.feed(tok)
    assert v.get_current_text() == "（望向远方）\n\n我记得那年夏天。"
    assert v.flush() == ["（望向远方）", "我记得那年夏天。"]


# ============================================================================
# text_processors
# ============================================================================

@check("text_processors 去括号 + 断句 + 前缀")
def _t_text_processors():
    assert _process_for_momotalk("（轻笑）嗨。") == ["嗨。"]
    assert strip_name_prefix("[遥花]: 你好", "遥花") == "你好"
    assert format_momotalk_reply("你好。", "遥花") == "[遥花]: 你好。"


@check("text_processors 连续强标点不丢（！！ 引擎冒烟回归）")
def _t_text_strong_punct_block():
    # 修复前 _strong_split 拆成 ["...呢！", "！"]，_has_content 丢掉 "！"
    assert _process_for_momotalk(
        "今天天气真不错呢！！我们一起去天台吧。"
    ) == ["今天天气真不错呢！！我们一起去天台吧。"]


@check("text_processors 段首标点块不丢（！！我们...）")
def _t_text_leading_punct_block():
    assert _process_for_momotalk("！！我们一起去天台吧。") == ["！！我们一起去天台吧。"]


@check("text_processors 混合标点块不丢（？！）")
def _t_text_mixed_punct_block():
    assert _process_for_momotalk("你疯了吗？！") == ["你疯了吗？！"]


@check("text_processors 全标点文本兜底不丢（！！！）")
def _t_text_all_punct():
    assert _process_for_momotalk("！！！") == ["！！！"]


# ============================================================================
# 集成
# ============================================================================

@check("集成 import: ui + core.momotalk + core.bond_story")
def _t_integration_import():
    import core.bond_story  # noqa: F401
    import core.momotalk    # noqa: F401


def main() -> None:
    global _PASS, _FAIL
    total = len(_TESTS)
    print(f"ui/ 展示层回归测试 ({total} 用例)")
    print("=" * 46)
    for name, fn in _TESTS:
        try:
            fn()
            _PASS += 1
            print(f"  PASS {name}")
        except Exception as e:  # noqa: BLE001 — 测试要捕获一切
            _FAIL += 1
            _FAILURES.append((name, e))
            print(f"  FAIL {name}: {type(e).__name__}: {e}")
    print("=" * 46)
    if _FAILURES:
        print(f"结果: {_PASS} PASS / {_FAIL} FAIL")
        for name, err in _FAILURES:
            print(f"  - {name}: {err}")
        sys.exit(1)
    print(f"结果: {_PASS} PASS / 0 FAIL — 全部通过")


if __name__ == "__main__":
    main()
