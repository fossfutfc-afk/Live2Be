# -*- coding: utf-8 -*-
"""⛔ P16「羁绊进度注记」**已封印**的守门（2026-10-08 用户裁决"封印一下/删除"）。

封印的是什么: `MomoTalkEngine._bond_progress_note()` 从前按**轮次**对触发时机表态, 两档
都注入 LLM context —— `gap >= SUGGEST_BOND_ROUNDS(6)` 时是

    【剧情时机】距上次完整羁绊剧情已 N 轮, 铺垫足够: …可以主动发起羁绊剧情（mmt_trigger_bond_story）

= **依据轮次催她主动发起 VN 邀约**; `gap < 6` 那档是同一根绳的另一头（按轮次反向拉住她）。

封印后: 引擎对触发时机**彻底不表态** —— 触发只由规则书的**契机判据**（共处/同行/偶遇/
紧急救援…）+ LLM 的剧情与人设判断决定（执行侧本来就零闸门）。

⚠️ 本文件同时钉住**别把它顺手改回来**: 把旧实现塞回去 → 立即红。
运行: python -m pytest tests/core/test_mmt_trigger_note_sealed.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.mmt.engine import SUGGEST_BOND_ROUNDS, MomoTalkEngine   # noqa: E402
from core.session import SessionStore                             # noqa: E402

CHARACTER = "igusa_haruka"

#: 封印前那两档各自的抬头与关键词（一个都不许再出现在**注入面**里）。
#: ⚠️ **别把动作名 `mmt_trigger_bond_story` 放进黑名单** —— 规则书的【羁绊剧情触发】
#: 专段本来就要讲它（第一版守门就这么错过, 当场红: 那是**合法的规则书内容**, 不是注记）。
#: 下面这些词只在**那条注记**里出现过（已核: 规则书里 0 命中）。
_FORBIDDEN = ("【剧情时机】", "羁绊进度事实", "主动发起羁绊剧情",
              "还在沉淀期", "铺垫足够")


class _StubLLM:
    """只回一条消息行, 不消耗脚本。"""

    def __init__(self):
        self.snapshots = []

    def chat(self, messages, temperature=0.8, max_tokens=4096,
             response_format="text", **kw):
        self.snapshots.append([dict(m) for m in messages])
        return '{"text": "嗯……"}'


def _engine(tmp_path, gap: int):
    llm = _StubLLM()
    st = SessionStore(tmp_path)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    root = st.create(CHARACTER)
    engine.start_session(CHARACTER)
    engine.attach_session(root.session_id)
    engine._bond_gap = gap          # 直接摆计数器（判据就是它）
    return engine, llm


def _joined(llm) -> str:
    return "\n".join(m.get("content") or "" for m in llm.snapshots[-1])


def test_note_is_sealed_for_every_gap(tmp_path):
    """两档都没了: gap=0（沉淀期那档）与 gap=99（建议那档）都不许再出现那些字样。"""
    for gap in (0, 1, SUGGEST_BOND_ROUNDS, 99):
        engine, llm = _engine(tmp_path / f"g{gap}", gap)
        assert engine._bond_progress_note() == "", (
            f"gap={gap}: `_bond_progress_note()` 必须恒为空串（已封印）")
        engine.agent_turn("在吗")
        joined = _joined(llm)
        for bad in _FORBIDDEN:
            assert bad not in joined, (
                f"gap={gap}: 注射面里又出现了 {bad!r} —— P16 注记被改回来了?\n"
                + "\n".join(m.get("content", "")[:80]
                            for m in llm.snapshots[-1]))
    print("    P16 已封印: gap=0/1/6/99 都不再有轮次驱动的时机表态 ✓")


def test_trigger_criteria_still_live_in_rules(tmp_path):
    """封印的是**引擎的轮次表态**, 不是触发能力本身 —— 规则书的契机判据必须还在。

    防止"顺手删过头"（把触发专段一起删掉 = 她再也不会主动发起剧情）。
    """
    from llm.prompts import load_prompt
    rules = load_prompt("momotalk_rules")
    assert "mmt_trigger_bond_story" in rules
    assert "契机" in rules, "规则书的契机判据被删了 —— 封印注记不该动它"
    # 乙（2026-10-08）: 规则书里那句"要看 mmt 进行了几轮"也一并删了 ⇒ 轮次依据清零
    assert "进行了几轮" not in rules, "规则书里还留着按轮次判断的措辞"
    print("    规则书: 契机判据在 ✓ / 按轮次的措辞已清零 ✓")


def test_counters_are_kept_but_have_no_readers(tmp_path):
    """一笔账: 封印后 `_bond_gap` 仍会累计（客观事实留着）, 但它不再影响注入面。

    这条钉的是"别把计数器当活旋钮"——它现在只写不读（`BondProgress.rounds()` 同理）。
    """
    engine, llm = _engine(tmp_path, 0)
    engine.agent_turn("在吗")
    engine.agent_turn("那个……")
    assert engine._bond_gap == 2, engine._bond_gap      # 照常累计
    for bad in _FORBIDDEN:
        assert bad not in _joined(llm)
    print("    计数器照常累计（gap=2）但不驱动任何注记 ✓")
