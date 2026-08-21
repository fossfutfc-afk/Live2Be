"""feedback() 回灌助手测试 — 追加 user 修正指令, 保留措辞原文。

运行: python -m pytest tests/llm/test_feedback.py
"""
from llm.feedback import feedback

tests = []

def _register(name):
    def decorator(fn):
        tests.append((name, fn))
        return fn
    return decorator


@_register("无 guidance: 原文完整入 user 消息")
def test_plain():
    msgs = []
    feedback(msgs, "无法执行: [ide/ide_executor.py][ExecError][文件不存在]")
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "无法执行: [ide/ide_executor.py][ExecError][文件不存在]"


@_register("有 guidance: 追加在正文下一行")
def test_guidance():
    msgs = []
    feedback(msgs, "动作无效: a; b", "请严格按 schema 重新输出单个动作 JSON。")
    assert msgs[0]["content"] == "动作无效: a; b\n请严格按 schema 重新输出单个动作 JSON。"


@_register("Exception 自动 str()（错误类已自格式化）")
def test_exception():
    msgs = []
    feedback(msgs, ValueError("动作无效: bad field"), "请修正后重试。")
    assert msgs[0]["content"] == "动作无效: bad field\n请修正后重试。"
    assert isinstance(msgs[0]["content"], str)


@_register("web/mock.py 依赖的原文保留（动作已执行 前缀）")
def test_mock_success():
    msgs = []
    feedback(msgs, "动作已执行: 已写入五件套")
    assert msgs[0]["content"].startswith("动作已执行"), msgs[0]["content"]


@_register("web/mock.py 依赖的原文保留（用户拒绝 子串）")
def test_mock_reject():
    msgs = []
    feedback(msgs, "用户拒绝了该动作。请按用户反馈调整后再输出。")
    assert "用户拒绝" in msgs[0]["content"]


@_register("guidance 缺省不拼接空行")
def test_no_trailing_newline():
    msgs = []
    feedback(msgs, "已执行")
    assert msgs[0]["content"] == "已执行"
    assert "\n" not in msgs[0]["content"]


if __name__ == "__main__":
    # --- run --- (pytest 收集 test_* 直接执行; 此处仅直接运行脚本时生效)
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  OK  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")

    print(f"\n=== {passed}/{len(tests)} passed ===")
    if passed != len(tests):
        sys.exit(1)