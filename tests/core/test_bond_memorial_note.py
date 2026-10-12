"""「本章纪念已用过」静态提示的守门（2026-10-08 用户裁决"加这条提示"）。

背景: `_memorial_used` 从前**只写不读** —— 章内第二次 `memorial` 由
`_demote_repeat_memorial` **静默丢弃**（有意不给反馈, 免得反馈回环）, 于是 writer
每一块都可能再写一次 `memorial`/`art` ⇒ **白写**（图与 marker 都不会出）。
真机 2026-10-08 就中过一次: `[vn][memorial] 章内第二次纪念 → 静默拒绝`。

判据: 用过之后, **下一块的 messages 里**必须出现那条静态提示; 没用过 ⇒ **不出现**。
（它是"事实"不是"纠偏" ⇒ 只进动态尾 notes, system 盒一字不动。）

运行: python -m pytest tests/core/test_bond_memorial_note.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

from core.bond.bond_story.engine import BondStoryEngine  # noqa: E402

CHAR = "igusa_haruka"
BLOCK = "\n".join([
    '{"stage": "switch", "text": "教室"}',
    f'{{"character": "{CHAR}", "text": "（第二块板。）"}}',
])


class _ScriptedLLM:
    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls = 0
        self.snapshots: list[list[dict]] = []

    def chat_full(self, messages, temperature=0.8, max_tokens=4096,
                  response_format="text", on_chunk=None, **kw):
        self.snapshots.append([dict(m) for m in (messages or [])])
        out = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if on_chunk is not None:
            for line in out.splitlines(keepends=True):
                on_chunk(line)
        return out

    def chat(self, *a, **k):                                # noqa: ANN002, ANN003
        return self.chat_full(None)

    def format_messages(self, *, system_prompt, user_message, history=None):
        return [{"role": "system", "content": system_prompt}]


def _engine(*replies: str):
    llm = _ScriptedLLM(*replies)
    eng = BondStoryEngine(ROOT / "config" / "characters", llm)
    eng.start_session(CHAR)
    eng._place_keys = []
    eng._task_on = False            # 只看注记, 不带场卡
    return eng, llm


def _joined(llm) -> str:
    return "\n".join(str(m.get("content") or "") for m in llm.snapshots[-1])


def test_note_appears_only_after_memorial_used():
    """⭐ 核心: `_memorial_used` → 提示出现; 未用过 → 不出现。

    变异验证: 把 `if self._memorial_used:` 那段删掉 ⇒ 本用例当场红。
    """
    eng, llm = _engine(BLOCK, BLOCK)
    eng.send_vn_scene("开场", annotate=False)
    assert "纪念插画**已经用过了**" not in _joined(llm), "还没用过就提示了"

    eng._memorial_used = True                     # 模拟"本章纪念已进入"
    eng.send_vn_scene("（继续）", annotate=False)
    joined = _joined(llm)
    assert "纪念插画**已经用过了**" in joined, joined[-400:]
    assert "不要再写 stage=art / stage=memorial" in joined, joined[-400:]
    print("    提示: 未用过不给 / 用过之后给 ✓")


def test_note_does_not_touch_system_box():
    """⚠️ 提示只进**动态尾**: system（盒B）必须逐字节稳定（前缀缓存基本盘）。"""
    eng, llm = _engine(BLOCK, BLOCK)
    eng.send_vn_scene("开场", annotate=False)
    sys_before = llm.snapshots[-1][0]["content"]
    eng._memorial_used = True
    eng.send_vn_scene("（继续）", annotate=False)
    sys_after = llm.snapshots[-1][0]["content"]
    assert sys_before == sys_after, "system 盒被注记改了（破前缀缓存）"
    print("    system 盒逐字节不变 ✓")
