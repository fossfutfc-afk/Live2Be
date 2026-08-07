"""临时测试：JSON 清洗管道的 6 个边缘场景。"""
import sys
sys.path.insert(0, ".")

from llm.client import extract_json

tests = []

def test(name):
    def decorator(fn):
        tests.append((name, fn))
        return fn
    return decorator

@test("markdown fence")
def test_fence():
    r = extract_json('```json\n{"key": "value"}\n```')
    assert r == {"key": "value"}, r

@test("extra text around JSON")
def test_extra_text():
    r = extract_json('好的，这是结果：{"score": 85, "reason": "很好"}希望对你有帮助')
    assert r == {"score": 85, "reason": "很好"}, r

@test("trailing comma")
def test_trailing_comma():
    r = extract_json('{"a": 1, "b": 2,}')
    assert r == {"a": 1, "b": 2}, r

@test("nested JSON")
def test_nested():
    r = extract_json('```json\n{"trigger": true, "data": {"name": "test", "items": [1,2,3]}}\n```')
    assert r == {"trigger": True, "data": {"name": "test", "items": [1, 2, 3]}}, r

@test("inline comment")
def test_comment():
    r = extract_json('{\n"a": 1, // comment\n"b": 2\n}')
    assert r == {"a": 1, "b": 2}, r

@test("Chinese keys")
def test_chinese():
    r = extract_json('```json\n{"羁绊触发": true, "理由": "好感度足够"}\n```')
    assert r == {"羁绊触发": True, "理由": "好感度足够"}, r

# --- run ---
passed = 0
for name, fn in tests:
    try:
        fn()
        print(f"  OK  {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL  {name}: {e}")

print(f"\n=== {passed}/{len(tests)} passed ===")
