# -*- coding: utf-8 -*-
"""ui/ 展示层回归测试 — 清理后的功能验证（everything works well）。

覆盖范围:
    streaming       LineBuffer 断句 / 不丢字符 / flush 遗留
                    TypingDelay 首句零延迟 / 实例独立 / reset
    display         MomoTalkOutput 气泡+延迟+去括号 / flush 遗留 / 实例独立
                    BondStoryOutput 段落分割
                    IDEOutput 事件 → 显示单元 / CLI 文本复刻 / GUI no-op
    text_processors 去括号 / 断句 / 前缀格式化
                    字数+随机数切块 split_reply_chunks（宁缺勿错不丢字）
    streaming       非流式步骤 DisplayStep / chunk_typing_time / simulate_steps
    display         非流式 publish_reply（切块 + "…"等待指示 + 气泡交替）
    集成            import core.ui + core.momotalk + core.bond_story

用法: python core/ui/test_display.py   （需项目根环境, 推荐 live2be env）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.ui import (
    BondStoryOutput,
    IDEDisplayItem,
    IDEOutput,
    LineBuffer,
    MomoTalkOutput,
    TypingDelay,
    _process_for_momotalk,
    format_momotalk_reply,
    split_reply_chunks,
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
    # 尾部 "明天好。" 止于标点 → 扣住等 flush（运行可能继续）
    assert lb.feed("你好。今天好。明天好。") == ["你好。", "今天好。"]
    assert lb.flush() == "明天好。"


@check("LineBuffer 连续标点不丢（你好！！）")
def _t_linebuffer_consecutive_punct():
    lb = LineBuffer()
    assert lb.feed("你好！！") == []       # 尾部标点运行 → 扣住
    assert lb.flush() == "你好！！"
    lb2 = LineBuffer()
    assert lb2.feed("你太过分了吧？？！！") == []
    assert lb2.flush() == "你太过分了吧？？！！"


@check("LineBuffer 跨 chunk 连续标点整体一句（！！ 引擎冒烟回归）")
def _t_linebuffer_cross_chunk_punct():
    lb = LineBuffer()
    # 修前: 前一个 chunk 末尾的 "！" 触发切句 → "呢！" + "！我们..." 拦腰切断
    out: list[str] = []
    for ch in "今天天气真不错呢！！我们一起去天台吧？？":
        out.extend(lb.feed(ch))
    rem = lb.flush()
    if rem:
        out.append(rem)
    assert out == ["今天天气真不错呢！！", "我们一起去天台吧？？"], f"得 {out!r}"


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
    assert lb.feed("好！") == []          # 尾部 "！" 扣住, flush 才取回
    assert lb.flush() == "今天好！"


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
    d = MomoTalkOutput(_process_for_momotalk, "遥香")
    # "你好。" 有已确认句界 → 立即切出; 尾部 "今天天气不错呢！" 扣住, flush 取回
    out = list(d.feed("（轻笑）你好。今天天气不错呢！"))
    assert out == [("[遥香]: 你好。", 0.0)], f"得 {out!r}"
    out2 = list(d.flush())
    assert out2[0][0] == "[遥香]: 今天天气不错呢！", f"得 {out2[0][0]!r}"
    assert out2[0][1] > 0.0


@check("MomoTalkOutput flush 取回遗留")
def _t_momotalk_flush():
    d = MomoTalkOutput(_process_for_momotalk, "遥香")
    out = list(d.feed("你好。还没说完"))
    assert out == [("[遥香]: 你好。", 0.0)]
    out2 = list(d.flush())
    assert out2[0][0] == "[遥香]: 还没说完"


@check("MomoTalkOutput 实例独立（各自首句零延迟）")
def _t_momotalk_independent():
    a = MomoTalkOutput(_process_for_momotalk, "A")
    b = MomoTalkOutput(_process_for_momotalk, "B")
    aa = list(a.feed("甲。回"))   # 句号后接文本 → 立即切句
    bb = list(b.feed("乙。回"))
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
    assert strip_name_prefix("[遥香]: 你好", "遥香") == "你好"
    assert format_momotalk_reply("你好。", "遥香") == "[遥香]: 你好。"


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
# 字数+随机数切块（非流式回复）
# ============================================================================

import random  # noqa: E402

def _is_subsplit(text: str, chunks: list[str]) -> bool:
    """chunks 依次是 text 的连续子串、位置递增（跳过切分处被丢弃的逗号）。

    宁缺勿错的验证: 每个块必须原样出现在原文里、按顺序、不重排;
    切分处被丢弃的逗号允许出现在块与块之间的缝隙里。
    """
    pos = 0
    for c in chunks:
        i = text.find(c, pos)
        if i == -1:
            return False
        pos = i + len(c)
    return True


@check("split_reply_chunks 短句 → 单块")
def _t_chunks_short():
    assert split_reply_chunks("嗯嗯好的") == ["嗯嗯好的"]
    assert split_reply_chunks("") == []


@check("split_reply_chunks 宁缺勿错不丢字（含标点/括号/长无标点句）")
def _t_chunks_lossless():
    cases = [
        "（轻笑）你好。今天天气不错呢！",
        "今天谢谢你帮我！要不要一起去喝奶茶？",
        "今天天气很好我们一起去天台吧我想和你说说话明天见",
        "我们去天台吧，顺便买杯奶茶。今天心情真的很好呢！",
        "嗯。嗯。好！",
    ]
    for t in cases:
        rng = random.Random(7)
        chunks = split_reply_chunks(t, rng=rng)
        assert _is_subsplit(t, chunks), f"丢字/乱序: 输入={t!r} 得={chunks!r}"
        assert all(c for c in chunks), f"空块: {chunks!r}"


@check("split_reply_chunks 逗号处切分丢逗号（千夏长句场景）")
def _t_chunks_comma_drop():
    t = "我想先确认一下您的身体状况，最近看您似乎总是很忙的样子，没问题吗？"
    chunks = split_reply_chunks(t, rng=random.Random(1))
    assert chunks == [
        "我想先确认一下您的身体状况",     # 14字 ≥10 必切, 丢逗号
        "最近看您似乎总是很忙的样子",     # 14字 ≥10 必切, 丢逗号
        "没问题吗？",                     # 强断点必切
    ], chunks


@check("split_reply_chunks 短块不切, 逗号留在块内（老师，场景）")
def _t_chunks_short_keep():
    t = "老师，如果是有关于风纪委员会职权范围内的事务，您可以直说。"
    chunks = split_reply_chunks(t, rng=random.Random(1))
    assert chunks == [
        "老师，如果是有关于风纪委员会职权范围内的事务",  # "老师，"2字<6不切, 逗号保留
        "您可以直说。",                                 # 强断点必切
    ], chunks


@check("split_reply_chunks 长无标点句切成多块（字数+随机数）")
def _t_chunks_long_split():
    # 40 字无标点 > max_chars=30 → 必须切块; 硬切后尾部 10 字 > 4, 不会并回
    long = "今天天气真的很好我们一起去天台吹吹风散散心看看风景吧我想和你说说话明天见记得早点休息"
    for seed in range(5):
        rng = random.Random(seed)
        chunks = split_reply_chunks(long, rng=rng)
        assert len(chunks) >= 2, f"seed {seed}: 应切成多块 {chunks!r}"
        assert "".join(chunks) == long


@check("split_reply_chunks 同种子确定性")
def _t_chunks_deterministic():
    t = "今天天气真的很好我们一起去天台吹吹风散散心看看风景吧我想和你说说话明天见记得早点休息"
    a = split_reply_chunks(t, rng=random.Random(42))
    b = split_reply_chunks(t, rng=random.Random(42))
    assert a == b, f"{a!r} != {b!r}"


@check("split_reply_chunks 标点边界优先（完整短句不硬拆）")
def _t_chunks_punct_first():
    # 每条都是完整短句且 ≤ max_chars → 全部整块保留
    t = "今天谢谢你帮我！要不要一起去喝奶茶？"
    assert split_reply_chunks(t, rng=random.Random(1)) == [
        "今天谢谢你帮我！",
        "要不要一起去喝奶茶？",
    ]


@check("split_reply_chunks 换行视为消息边界")
def _t_chunks_newline():
    t = "第一句。\n第二句"
    chunks = split_reply_chunks(t)
    assert "".join(chunks) == "第一句。第二句", chunks


@check("split_reply_chunks 孤立强标点并入上一块（…？/！！/单独成行）")
def _t_chunks_orphan_punct():
    # 省略号切点后接 "？": 强标点不再孤立成一条 "？"
    assert split_reply_chunks("今晚能不能借我点钱买泡面…？") == \
        ["今晚能不能借我点钱买泡面…？"]
    # 连续强标点: 不再产出孤立的 "！"
    assert split_reply_chunks("今天天气真不错呢！！我们一起去天台吧？？") == [
        "今天天气真不错呢！！",
        "我们一起去天台吧？？",
    ]
    # LLM 把 "？" 单独成行: 纯标点行并入上一行（有内容的行仍是消息边界）
    assert split_reply_chunks("今晚能不能借我点钱买泡面…\n？") == \
        ["今晚能不能借我点钱买泡面…？"]
    assert split_reply_chunks("第一句。\n第二句") == ["第一句。", "第二句"]
    # 纯标点块仍是独立行: 并入前块后 join 不丢字
    t = "真的吗！？"
    assert "".join(split_reply_chunks(t)) == t, split_reply_chunks(t)


# ============================================================================
# 非流式显示步骤（DisplayStep / 打字时长 / publish_reply）
# ============================================================================

from core.ui.display import MomoTalkOutput  # noqa: E402
from core.ui.streaming import DisplayStep, chunk_typing_time  # noqa: E402

@check("chunk_typing_time 恒正 + 长句时长更长（字数+随机数）")
def _t_typing_time():
    rng = random.Random(3)
    assert chunk_typing_time("今天", rng) > 0
    assert chunk_typing_time("短", rng) < chunk_typing_time("今天天气很好我们一起去", rng)


@check("publish_reply 打字指示→气泡 交替, 首步 typing")
def _t_publish_reply_alternate():
    d = MomoTalkOutput(_process_for_momotalk, "遥香")
    steps = d.publish_reply("（轻笑）今天谢谢你！要不要一起喝奶茶？")
    assert steps and steps[0].typing and steps[0].text == "…"
    # typing 与真实气泡严格交替
    assert [s.typing for s in steps] == [True, False, True, False]
    # 气泡文本拼接(去前缀) == 去括号后的完整回复（宁缺勿错）
    bubbles = "".join(s.text.replace("[遥香]: ", "") for s in steps if not s.typing)
    assert bubbles == "今天谢谢你！要不要一起喝奶茶？", bubbles
    # 每个气泡都带前缀
    assert all(s.text.startswith("[遥香]: ") for s in steps if not s.typing)


@check("publish_reply 空回复 / 纯动作括号 → 空步骤")
def _t_publish_reply_empty():
    assert MomoTalkOutput(_process_for_momotalk, "A").publish_reply("") == []
    assert MomoTalkOutput(_process_for_momotalk, "A").publish_reply("（摇头）") == []
    assert MomoTalkOutput(_process_for_momotalk, "A").publish_reply("   ") == []


@check("simulate_steps 打字指示被气泡覆盖（CLI 渲染）")
def _t_simulate_steps():
    import io  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415
    from core.ui.streaming import simulate_steps  # noqa: PLC0415

    steps = [
        DisplayStep("…", 0.5, typing=True),
        DisplayStep("[遥香]: 你好", 0.0),
    ]
    buf = io.StringIO()
    with patch("time.sleep"), patch("sys.stdout", buf):
        simulate_steps(steps)
    out = buf.getvalue()
    assert "…" in out and "[遥香]: 你好" in out, out


# ============================================================================
# IDEOutput
# ============================================================================

@check("IDEOutput AI_MESSAGE → [AI] 前缀（复刻现有 print）")
def _t_ide_ai_message():
    out = IDEOutput()
    item = out.render({"kind": "AI_MESSAGE", "data": {"message": "查到了资料"}})
    assert item.kind == "AI_MESSAGE"
    assert item.text == "\n[AI] 查到了资料", f"得 {item.text!r}"
    assert item.data == {"message": "查到了资料"}


@check("IDEOutput PENDING_APPROVAL → 提议+diff+approval_id")
def _t_ide_proposal():
    out = IDEOutput()
    item = out.render({
        "kind": "PENDING_APPROVAL",
        "step": 3,
        "approval_id": "aid-1",
        "data": {"summary": "写 profile.yml", "diff": "- a\n+ b", "action": {"action": "write"}},
    })
    assert item.text == "\n[AI 提议] 写 profile.yml\n- a\n+ b", f"得 {item.text!r}"
    assert item.data["approval_id"] == "aid-1"
    assert item.data["diff"] == "- a\n+ b"
    assert item.data["action"] == {"action": "write"}


@check("IDEOutput DECISION reject/abort + ABORTED")
def _t_ide_decision():
    out = IDEOutput()
    assert out.render({"kind": "DECISION", "data": {"choice": "reject"}}).text == "[已拒绝]"
    assert out.render({"kind": "DECISION", "data": {"choice": "abort"}}).text == "[已中止本轮]"
    assert out.render({"kind": "ABORTED", "data": {}}).text == "[已中止本轮]"


@check("IDEOutput EXEC_RESULT ok/fail")
def _t_ide_exec():
    out = IDEOutput()
    assert out.render({"kind": "EXEC_RESULT", "data": {"ok": True, "message": "已写入"}}).text == "[已执行] 已写入"
    assert out.render({"kind": "EXEC_RESULT", "data": {"ok": False, "message": "文件不存在"}}).text == "[执行失败] 文件不存在"


@check("IDEOutput TOOL_RESULT / TOOL_ERROR")
def _t_ide_tool():
    out = IDEOutput()
    item = out.render({"kind": "TOOL_RESULT", "data": {"name": "search", "label": "伊草遥香", "chars": 321}})
    assert item.text == "[search 伊草遥香] 已获取 321 字符", f"得 {item.text!r}"
    item = out.render({"kind": "TOOL_ERROR", "data": {"name": "fetch_url", "label": "http://x", "error": "超时"}})
    assert item.text == "[fetch_url失败] 超时", f"得 {item.text!r}"


@check("IDEOutput DONE → [AI] 完成消息")
def _t_ide_done():
    out = IDEOutput()
    item = out.render({"kind": "DONE", "data": {"message": "五件套已写入"}})
    assert item.text == "\n[AI] 五件套已写入", f"得 {item.text!r}"


@check("IDEOutput CLI no-op 事件 text 为空但恒有返回")
def _t_ide_gui_only():
    out = IDEOutput()
    for kind in ("THINKING", "TOOL_START", "INVALID_ACTION", "LLM_ERROR", "PLAN_ERROR"):
        item = out.render({"kind": kind, "data": {}})
        assert item is not None and item.kind == kind
        assert item.text == "", f"{kind}: {item.text!r}"


@check("IDEOutput 未知 kind 不抛错")
def _t_ide_unknown():
    out = IDEOutput()
    item = out.render({"kind": "WEIRD", "data": {}})
    assert item.kind == "WEIRD" and item.text == ""
    assert isinstance(item, IDEDisplayItem)


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
