"""`llm.retry.call_with_feedback` —— 三个引擎共用的那个循环。

钉的是**循环本身的语义**（尝试次数、回灌的消息形状、回执），不是任何一个引擎的策略：
发什么、parse 什么、被拒怎么说都由调用方给。回灌本身走 `llm.client.feedback`。
"""
from __future__ import annotations

from contract.model import ValidationResult
from llm.retry import call_with_feedback


def _parse(reject_first: int):
    """前 `reject_first` 次拒（每次给不同错误文案），之后放行。"""
    state = {"n": 0}

    def parse(raw):
        state["n"] += 1
        if state["n"] <= reject_first:
            return None, ValidationResult(errors=(f"第 {state['n']} 次不行",))
        return {"ok": raw}, ValidationResult()

    return parse


def _reason(v: ValidationResult) -> str:
    return "【引擎校验反馈】" + "; ".join(v.errors)


def test_first_try_passes_without_touching_messages():
    """一次就过 ⇒ 只发一次，且**一个字都不往 messages 里塞**。"""
    msgs = [{"role": "user", "content": "hi"}]
    before = list(msgs)
    res = call_with_feedback(msgs, send=lambda m: "A", parse=_parse(0), reason=_reason)
    assert res.ok and res.payload == {"ok": "A"}
    assert len(res.attempts) == 1
    assert msgs == before


def test_reject_then_pass_appends_assistant_raw_then_user_feedback():
    """被拒 ⇒ 先塞 assistant 原文，再塞 `feedback()` 的 user 反馈，然后重试。"""
    msgs = [{"role": "user", "content": "hi"}]
    res = call_with_feedback(msgs, send=lambda m: "RAW", parse=_parse(1), reason=_reason)
    assert res.ok and len(res.attempts) == 2
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"] == "RAW"                     # 被拒原文原样回灌
    assert msgs[2]["content"].startswith("【引擎校验反馈】")
    assert "第 1 次不行" in msgs[2]["content"]


def test_dict_raw_is_reinjected_as_json_keeping_chinese():
    """dict 原文走 JSON（`ensure_ascii=False`）—— 回灌给她看，不是 `\\u5979`。"""
    msgs: list[dict] = []
    call_with_feedback(msgs, send=lambda m: {"text": "她笑了"}, parse=_parse(1),
                       reason=_reason)
    assert msgs[0]["role"] == "assistant"
    assert msgs[0]["content"] == '{"text": "她笑了"}'


def test_all_rejected_stops_at_max_feedback_and_reports_the_last_verdict():
    msgs: list[dict] = []
    res = call_with_feedback(msgs, send=lambda m: "X", parse=_parse(99),
                             reason=_reason, max_feedback=2)
    assert not res.ok and res.payload is None
    assert len(res.attempts) == 3                          # 1 + max_feedback
    assert res.verdict.errors == ("第 3 次不行",)           # 报的是**最后一次**
    assert len(msgs) == 4                                  # 只回灌"还会有下一次"的两轮


def test_max_feedback_zero_sends_once_and_never_reinjects():
    msgs: list[dict] = []
    res = call_with_feedback(msgs, send=lambda m: "X", parse=_parse(99),
                             reason=_reason, max_feedback=0)
    assert not res.ok and len(res.attempts) == 1
    assert msgs == []


def test_on_attempt_fires_once_per_attempt_in_order():
    seen: list = []
    call_with_feedback([], send=lambda m: "X", parse=_parse(2), reason=_reason,
                       max_feedback=3, on_attempt=seen.append)
    assert [a.index for a in seen] == [1, 2, 3]
    assert seen[-1].verdict.is_valid                       # 第三次成了


def test_guidance_lands_on_the_line_after_the_reason():
    msgs: list[dict] = []
    call_with_feedback(msgs, send=lambda m: "X", parse=_parse(1), reason=_reason,
                       guidance="下一行", max_feedback=1)
    assert msgs[1]["content"] == "【引擎校验反馈】第 1 次不行\n下一行"
