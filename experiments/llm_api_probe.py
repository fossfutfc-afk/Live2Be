"""LLM API 连通性测试 — 文本 + JSON 模式。"""
import sys
sys.path.insert(0, ".")

from llm.client import LLMClient

def test_text():
    """测试纯文本对话。"""
    print("=" * 50)
    print("[TEST 1] 纯文本对话")
    print("=" * 50)

    client = LLMClient()
    messages = client.format_messages(
        system_prompt="你是一个测试助手。用一句话简短回答。",
        user_message="请说'API连接成功，你好世界'",
    )

    reply = client.chat(messages, temperature=0.3, max_tokens=128)
    print(f"回复: {reply}")
    client.close()
    return True


def test_json():
    """测试 JSON 结构化输出。"""
    print()
    print("=" * 50)
    print("[TEST 2] JSON 结构化输出")
    print("=" * 50)

    client = LLMClient()
    messages = client.format_messages(
        system_prompt="你是一个情绪分析器。收到用户输入后，返回JSON格式的情绪分析结果。",
        user_message="我今天考试得了满分，太开心了！请分析我的情绪。",
    )

    data = client.chat(
        messages,
        temperature=0.3,
        max_tokens=256,
        response_format="json_object",
    )
    print(f"解析结果: {data}")
    print(f"类型: {type(data).__name__}")
    client.close()
    return True


def test_json_hard():
    """测试 JSON 修正重试 — 故意让 LLM 做复杂输出。"""
    print()
    print("=" * 50)
    print("[TEST 3] 复杂 JSON + 修正能力")
    print("=" * 50)

    client = LLMClient()
    messages = client.format_messages(
        system_prompt=(
            "你是一个角色对话触发器。"
            "根据用户输入，判断是否应该触发羁绊剧情。"
        ),
        user_message=(
            "遥香说她最近在杂草屋发现了一株从来没见过的花，"
            "想邀请sensei周末一起去看看。"
        ),
    )

    data = client.chat(
        messages,
        temperature=0.5,
        max_tokens=512,
        response_format="json_object",
    )
    print(f"解析结果: {data}")
    print(f"should_trigger 类型: {type(data).__name__}")
    client.close()
    return True


if __name__ == "__main__":
    passed = 0
    total = 3

    try:
        if test_text():
            passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")

    try:
        if test_json():
            passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")

    try:
        if test_json_hard():
            passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")

    print()
    print(f"=== {passed}/{total} 测试通过 ===")
