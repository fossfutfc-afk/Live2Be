"""`llm/client.py::llm_chat` —— 结构化调用的鲁棒层（重试 / deadline / 透传语义）。

2026-10-13 随函数一起从 `core/digest/llm_call.py` 搬来（那 85 行**零 digest 依赖**，
放 digest 里是位置错了; 它和 `client.py` 里的 `feedback` / `_classify` /
`llm/retry.py::call_with_feedback` 才是同一族）。
⚠️ 它**不是** `LLMClient` 的方法而是模块级函数 ——原因写在它的 docstring 里
（`llm` 是鸭子类型, 桩只实现 `.chat()`）。
"""
import time

from llm.client import llm_chat


class FakeLLM:
    """记录调用参数; 可注入失败次数与响应。"""

    def __init__(self, responses=None, fail_times=0):
        self.responses = list(responses or [])
        self.fail_times = fail_times
        self.calls: list[dict] = []

    def chat(self, messages, **kw):
        self.calls.append(kw)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("api down")
        if self.responses:
            return self.responses.pop(0)
        return {"ok": True}


def test_success_passthrough_and_extra_body_semantics():
    """extra_body=None 原样透传（默认档由客户端 settings 注入, llm_chat 不硬编码）;
    显式 dict 原样传给客户端。"""
    llm = FakeLLM(responses=[{"revisions": []}])
    resp, err = llm_chat(llm, "sys", "user")
    assert resp == {"revisions": []} and err is None
    kw = llm.calls[0]
    assert kw["response_format"] == "json_object"
    assert kw["extra_body"] is None                     # None 透传 → 客户端默认档
    assert kw["model"] is None and kw["max_tokens"] == 8192


def test_custom_extra_body_and_model():
    llm = FakeLLM()
    resp, err = llm_chat(llm, "sys", "user", model="deepseek-chat",
                         extra_body={}, max_tokens=4096, temperature=0.5)
    assert resp is not None and err is None
    kw = llm.calls[0]
    assert kw["model"] == "deepseek-chat"
    assert kw["extra_body"] == {}                     # 显式 {} 关闭默认（透传）
    assert kw["max_tokens"] == 4096 and kw["temperature"] == 0.5


def test_timeout_passthrough():
    llm = FakeLLM()
    resp, err = llm_chat(llm, "sys", "user", timeout=300.0)
    assert resp is not None and err is None
    assert llm.calls[0]["timeout"] == 300.0


def test_retry_until_success():
    llm = FakeLLM(responses=[{"ok": 1}], fail_times=2)
    resp, err = llm_chat(llm, "sys", "user")
    assert resp == {"ok": 1} and err is None
    assert len(llm.calls) == 3                        # 2 败 1 成


def test_retry_exhausted_returns_error():
    llm = FakeLLM(fail_times=99)
    resp, err = llm_chat(llm, "sys", "user", max_retries=2)
    assert resp is None and err is not None
    assert "重试耗尽" in err
    assert len(llm.calls) == 2


def test_deadline_cuts_retries():
    """deadline 已过 → 不再尝试调用。"""
    llm = FakeLLM(fail_times=99)
    deadline = time.monotonic() - 1                   # 已过期
    resp, err = llm_chat(llm, "sys", "user", deadline=deadline, max_retries=5)
    assert resp is None and "时间预算" in err
    assert len(llm.calls) == 0


def test_label_maps_to_task_tag():
    """`label`（轮次 key）→ task 标签: 测试桩据此分轮, 不认中文关键字。"""
    from llm.task_labels import digest_label
    llm = FakeLLM()
    llm_chat(llm, "sys", "user", label="record")
    assert llm.calls[0]["task"] == digest_label("record")
