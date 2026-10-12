"""待发队列**跨块累积**的守门（2026-10-08 链式读前的第一块地基）。

背景: `_pending_boards` 从前是**赋值**（`= list(boards[1:])`）—— 在"生成只在队列空时
发生"那条不变量下没错; 链式读前要求"提前生成的下一块**排在玩家还没读完的板后面**"
⇒ 改成 `extend`, 并给 `send_vn_scene` 加了 `readahead=True` 口子（跳过"领队列"早返回,
强制再写一块 —— 否则读前调用只会把队列里的板领出来, 根本不会生成）。

本文件钉两件最要命的事:
  ① 队列非空时读前生成 ⇒ **旧板一字不丢**且**排在新板前面**;
  ② 正常推进（`readahead=False`）仍然是"**先领队列、按先来后到**"且 **0 LLM**。

运行: python -m pytest tests/core/test_bond_pending_append.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

from core.bond.bond_story.engine import BondStoryEngine     # noqa: E402

CHAR = "igusa_haruka"


def _block(tag: str, second: str) -> str:
    """一块**两板**的记录流（老师群切板）: 首板带 tag, 尾板带 second。"""
    return "\n".join([
        '{"stage": "switch", "text": "教室"}',
        f'{{"character": "{CHAR}", "text": "{tag}"}}',
        '{"character": "sensei", "text": "（切板）"}',
        f'{{"character": "{CHAR}", "text": "{second}"}}',
    ])


class _ScriptedLLM:
    """按调用次序吐脚本; 记 `calls` 供"领队列不走 LLM"的判据用。"""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls = 0

    def chat_full(self, messages, temperature=0.8, max_tokens=4096,
                  response_format="text", on_chunk=None, **kw):
        out = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if on_chunk is not None:
            for line in out.splitlines(keepends=True):
                on_chunk(line)
        return out

    def chat(self, *a, **k):                                # noqa: ANN002, ANN003
        return self.chat_full(None)

    def format_messages(self, *, system_prompt, user_message, history=None):
        return [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}]


def _engine(*replies: str):
    llm = _ScriptedLLM(*replies)
    eng = BondStoryEngine(ROOT / "config" / "characters", llm)
    eng.start_session(CHAR)
    eng._place_keys = []          # 本文件只关心队列（place 关断, 少一次调用）
    return eng, llm


def _texts(boards) -> list[str]:
    """板的"第一句"（⚠️ `paragraphs[i]` 是 **dict**, 不是对象）。"""
    return [b.paragraphs[0]["text"] for b in boards]


def _first(scene) -> str:
    return scene.paragraphs[0]["text"]


def test_readahead_block_appends_behind_unread_boards():
    """⭐ 核心: 队列里还剩板时读前生成 ⇒ 旧板**一字不丢**且仍排在前面。

    变异验证: 把 `extend` 改回 `= list(...)` ⇒ 本用例当场红（旧板被冲掉）。
    """
    eng, _ = _engine(_block("甲", "乙"), _block("丙", "丁"))
    head1 = eng.send_vn_scene("开场")                     # 第一块: 首板交付, 尾板进队列
    assert _first(head1) == "甲"
    assert _texts(eng._pending_boards) == ["乙"], _texts(eng._pending_boards)

    head2 = eng.send_vn_scene("（继续）", annotate=False, readahead=True)
    assert _first(head2) == "丙"               # 新块首板交给调用方排
    assert _texts(eng._pending_boards) == ["乙", "丁"], (
        "读前生成的板没有**追加**在后面 —— 旧板被冲掉了（`=` 而不是 `extend`）: "
        f"{_texts(eng._pending_boards)}")
    print("    读前追加: 旧[乙] 仍在最前, 队列 = [乙, 丁] ✓")


def test_normal_advance_serves_queue_first_in_order_without_llm():
    """正常推进（`readahead=False`）: **先领队列、先来后到、0 LLM**。"""
    eng, llm = _engine(_block("甲", "乙"), _block("丙", "丁"))
    eng.send_vn_scene("开场")
    calls_after_first = llm.calls

    s = eng.send_vn_scene("（继续）", annotate=False)   # webgui 走异步标注; 这里关掉
    assert _first(s) == "乙", _first(s)
    assert llm.calls == calls_after_first, "领队列不该再调 LLM（生成 0 次）"
    assert not eng._pending_boards, _texts(eng._pending_boards)
    print("    领队列: 乙 ✓（0 LLM）")


def test_readahead_does_not_steal_pending():
    """读前生成**不许**把队列里的板当成"要发的那一块"发出去（`readahead` 跳过领队列分支）。

    变异验证: `if self._pending_boards and not readahead:` 里的 `and not readahead`
    删掉 ⇒ 这里拿到 "乙" 且 LLM 调用数不增 ⇒ 红。
    """
    eng, llm = _engine(_block("甲", "乙"), _block("丙", "丁"))
    eng.send_vn_scene("开场")
    calls = llm.calls

    got = eng.send_vn_scene("（继续）", annotate=False, readahead=True)
    assert llm.calls == calls + 1, "读前必须**真的生成一块**（不是领队列）"
    assert _first(got) == "丙", _first(got)
    assert "乙" in _texts(eng._pending_boards), "队列里的板被吃掉了"
    print("    读前真生成: 拿到的不是队列里的板 ✓")
