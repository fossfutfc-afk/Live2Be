"""临时测试：JSON 清洗管道的 6 个边缘场景。"""
from llm.client import extract_json

tests = []

def _register(name):
    def decorator(fn):
        tests.append((name, fn))
        return fn
    return decorator

@_register("markdown fence")
def test_fence():
    r = extract_json('```json\n{"key": "value"}\n```')
    assert r == {"key": "value"}, r

@_register("extra text around JSON")
def test_extra_text():
    r = extract_json('好的，这是结果：{"score": 85, "reason": "很好"}希望对你有帮助')
    assert r == {"score": 85, "reason": "很好"}, r

@_register("trailing comma")
def test_trailing_comma():
    r = extract_json('{"a": 1, "b": 2,}')
    assert r == {"a": 1, "b": 2}, r

@_register("nested JSON")
def test_nested():
    r = extract_json('```json\n{"trigger": true, "data": {"name": "test", "items": [1,2,3]}}\n```')
    assert r == {"trigger": True, "data": {"name": "test", "items": [1, 2, 3]}}, r

@_register("inline comment")
def test_comment():
    r = extract_json('{\n"a": 1, // comment\n"b": 2\n}')
    assert r == {"a": 1, "b": 2}, r

@_register("Chinese keys")
def test_chinese():
    r = extract_json('```json\n{"羁绊触发": true, "理由": "好感度足够"}\n```')
    assert r == {"羁绊触发": True, "理由": "好感度足够"}, r

@_register("python dict literal (single quotes)")
def test_python_dict_literal():
    r = extract_json("{'action': 'done', 'payload': {'msg': '好'}, 'n': None, 'ok': True}")
    assert r == {"action": "done", "payload": {"msg": "好"}, "n": None, "ok": True}, r

@_register("python dict literal with escaped newlines")
def test_python_dict_literal_multiline():
    r = extract_json("{'action': 'update_character', 'payload': {'files': "
                     "{'experience.yml': 'SIG~self:\\n - regular:\\n - 1: >\\n 无月跑来玩'}}}")
    assert r["action"] == "update_character"
    assert "SIG~self:" in r["payload"]["files"]["experience.yml"], r

@_register("python dict literal with RAW newlines in string")
def test_python_dict_literal_raw_newlines():
    r = extract_json("{'action': 'update_character', 'payload': {'files': "
                     "{'experience.yml': 'SIG~self:\n - regular:\n - 1: >\n 无月跑来玩'}}}")
    assert r["action"] == "update_character"
    assert "SIG~self:" in r["payload"]["files"]["experience.yml"], r
    assert "\n" in r["payload"]["files"]["experience.yml"]   # 换行被还原成真实换行

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