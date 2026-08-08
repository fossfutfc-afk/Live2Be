"""10 场景测试：Config 解析层健壮性验证。"""
import sys, warnings, shutil
sys.path.insert(0, '.')
from parsing.character_parser import CharacterLoader, ConfigValidationError
from pathlib import Path

passed = 0
failed = []

def ok(msg):
    global passed; passed += 1
    print(f'  OK  {msg}')
def fail(msg):
    print(f'  FAIL  {msg}')
    failed.append(msg)

ROOT = Path('config/characters')
loader = CharacterLoader(ROOT)

# 1. Full Haruka
print('=== 1. 完整角色 (Haruka) ===')
h = loader.load('igusa_haruka')
assert h.profile.most_called_name == '伊草 遥香'
assert h.info_level == 'full'
ok('info_level=full')

# 2. Bare + LLM fallback
print('=== 2. Bare + LLM fallback ===')
d = ROOT / '_t2'; d.mkdir(parents=True, exist_ok=True)
(d/'profile.yml').write_text('is_official_character: true\nname:\n  - IMP_most_called_name: "test"\nintroduction: "x"\n', encoding='utf-8')
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    r = loader.load('_t2', strict=False)
    assert r.info_level == 'bare' and r.needs_llm_fallback
    p = r.build_system_prompt('momotalk')
    assert '知识库' in p
ok('bare mode enabled LLM fallback')
shutil.rmtree(d, ignore_errors=True)

# 3. Strict reject (missing introduction)
print('=== 3. Strict reject missing intro ===')
d = ROOT / '_t3'; d.mkdir(parents=True, exist_ok=True)
(d/'profile.yml').write_text('is_official_character: true\nname:\n  - IMP_most_called_name: "x"\n', encoding='utf-8')
try:
    loader.load('_t3', strict=True); fail('not rejected')
except ConfigValidationError: ok('rejected')
shutil.rmtree(d, ignore_errors=True)

# 4. Strict reject (missing name)
print('=== 4. Strict reject missing name ===')
d = ROOT / '_t4'; d.mkdir(parents=True, exist_ok=True)
(d/'profile.yml').write_text('is_official_character: true\nintroduction: "x"\n', encoding='utf-8')
try:
    loader.load('_t4', strict=True); fail('not rejected')
except ConfigValidationError: ok('rejected')
shutil.rmtree(d, ignore_errors=True)

# 5. YAML syntax error
print('=== 5. YAML syntax error ===')
d = ROOT / '_t5'; d.mkdir(parents=True, exist_ok=True)
(d/'profile.yml').write_text('name:\n  - IMP_most_called_name: "x"\n  bad: [broken', encoding='utf-8')
try:
    loader.load('_t5', strict=False); fail('not rejected')
except ConfigValidationError: ok('rejected')
shutil.rmtree(d, ignore_errors=True)

# 6. Null fields
print('=== 6. null fields -> safe defaults ===')
d = ROOT / '_t6'; d.mkdir(parents=True, exist_ok=True)
(d/'profile.yml').write_text('is_official_character: true\nname:\n  - IMP_most_called_name: "n"\nintroduction: "x"\ngender: null\nage: null\nheight: null\nschool: null\n', encoding='utf-8')
r = loader.load('_t6', strict=True)
assert r.profile.gender == '', repr(r.profile.gender)
assert r.profile.age == 0, str(r.profile.age)
assert r.profile.height == 0
ok('null fields handled')
shutil.rmtree(d, ignore_errors=True)

# 7. Non-official no fallback
print('=== 7. Non-official no fallback ===')
d = ROOT / '_t7'; d.mkdir(parents=True, exist_ok=True)
(d/'profile.yml').write_text('is_official_character: false\nname:\n  - IMP_most_called_name: "OC"\nintroduction: "x"\n', encoding='utf-8')
r = loader.load('_t7', strict=True)
assert not r.needs_llm_fallback
p = r.build_system_prompt('momotalk')
assert '知识库' not in p
ok('no fallback for OC')
shutil.rmtree(d, ignore_errors=True)

# 8. Optional files missing
print('=== 8. Optional files missing ===')
d = ROOT / '_t8'; d.mkdir(parents=True, exist_ok=True)
(d/'profile.yml').write_text('is_official_character: true\nname:\n  - IMP_most_called_name: "m"\nintroduction: "x"\n', encoding='utf-8')
r = loader.load('_t8', strict=True)
assert r.personality.brief_traits == []
assert r.knowledge.friends == {}
assert r.experience.self_stories == {}
assert r.typical.frequent_phrases == []
ok('empty defaults for all optional')
shutil.rmtree(d, ignore_errors=True)

# 9. Legacy key
print('=== 9. Legacy key is_official-character ===')
d = ROOT / '_t9'; d.mkdir(parents=True, exist_ok=True)
(d/'profile.yml').write_text('is_official-character: false\nname:\n  - IMP_most_called_name: "k"\nintroduction: "x"\n', encoding='utf-8')
r = loader.load('_t9', strict=True)
assert r.profile.is_official == False
ok('old key still works')
shutil.rmtree(d, ignore_errors=True)

# 10. Minimal level
print('=== 10. Minimal info level ===')
d = ROOT / '_t10'; d.mkdir(parents=True, exist_ok=True)
(d/'profile.yml').write_text('is_official_character: true\nname:\n  - IMP_most_called_name: "mid"\n  - en_name: "Mid"\nintroduction: "mid"\ngender: "女"\nage: 16\nschool: "某"\n', encoding='utf-8')
r = loader.load('_t10', strict=True)
assert r.info_level == 'minimal'
assert r.needs_llm_fallback
ok('info_level=minimal')
shutil.rmtree(d, ignore_errors=True)

print()
print(f'=== {passed}/10 passed ===')
if failed:
    for f in failed: print(f)
