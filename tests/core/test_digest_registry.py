"""digest_registry 测试（AGENT_BRAIN.md §3 重构 / 板块 2）——LLM 契约层单源。"""
from contract.digest_registry import (
    PHASE_RECORD,
    PHASE_UNDERSTAND,
    digest_registry,
)
from contract.model import ValidationResult


# ---------------------------------------------------------------------------
# schema 渲染
# ---------------------------------------------------------------------------

def test_schema_record_phase():
    text = digest_registry.build_schema(PHASE_RECORD)
    assert '"episodes": [' in text
    assert "narration" in text and "内联约束" in text or "必填" in text
    assert "title" in text and "verbatim" in text and "tags" in text
    assert "significance" in text
    # 内联约束注释（A-MEM 式: 规则贴字段）
    assert "检索导向" in text
    assert "行为锚点" in text
    # 语义与范例
    assert "【record_episode 释义】" in text
    assert "【范例】" in text


def test_schema_understand_phase():
    text = digest_registry.build_schema(PHASE_UNDERSTAND)
    assert '"decisions": [' in text
    for name in ("touch", "update", "add"):
        assert f"【{name} 释义】" in text
    assert "evidence" in text and "affection_exp_delta" in text
    assert "编造 id → 整包拒" in text
    assert "疑似印证" in text


def test_actions_by_phase():
    assert {a.name for a in digest_registry.actions(PHASE_RECORD)} == {"record_episode"}
    assert {a.name for a in digest_registry.actions(PHASE_UNDERSTAND)} == {
        "touch", "update", "add"}
    assert digest_registry.actions()  # 全量非空


def test_unknown_phase_rejected():
    import pytest
    with pytest.raises(ValueError):
        digest_registry.build_schema("deep")     # deep 未注册动作 → 暂不支持


# ---------------------------------------------------------------------------
# Round A parse
# ---------------------------------------------------------------------------

def test_round_a_valid_entries():
    raw = {"episodes": [
        {"narration": "老师约我去公园散步, 我紧张但努力答应了。", "title": "公园散步",
         "tags": ["公园"], "significance": 0.8},
        {"narration": "听睦月说阿露昨天又翻车了", "title": "阿露翻车",
         "tags": ["睦月", "阿露"], "epistemic": "reported_fact",
         "observer": "asagi_mutsuki", "significance": 0.6},
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert result.is_valid, result.errors
    assert len(items) == 2
    assert items[0]["narration"].startswith("老师约我")
    assert items[1]["epistemic"] == "reported_fact"
    assert items[1]["observer"] == "asagi_mutsuki"


def test_round_a_rejects_bad_entries():
    raw = {"episodes": [
        {"title": "没有正文"},                       # 缺 narration
        {"narration": "x" * 400},                    # 超长
        {"narration": "转述却没写转述者", "epistemic": "reported_fact"},
        {"narration": "ok", "title": "t", "id": "m9999"},   # 引擎字段应被忽略(警告)
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert not result.is_valid
    assert any("narration" in e for e in result.errors)          # 缺正文
    assert any("300 字" in e for e in result.errors)             # 超长
    assert any("observer" in e for e in result.errors)           # reported 缺转述者
    assert any("引擎字段" in w for w in result.warnings)         # id 忽略
    # 坏条目丢弃, 好的保留
    assert len(items) == 1 and items[0]["narration"] == "ok"


def test_round_a_caps_and_defaults():
    raw = {"episodes": [{"narration": f"e{i}", "title": f"t{i}"} for i in range(7)]}
    items, result = digest_registry.parse_round_a(raw)
    assert len(items) == 5                       # MAX_EPISODES 截断
    assert items[0]["significance"] == 0.5       # 缺省
    assert items[0]["epistemic"] == "observed_fact"
    assert any("5 条" in e for e in result.errors)


def test_round_a_not_dict():
    items, result = digest_registry.parse_round_a(["nope"])
    assert items == [] and not result.is_valid


def test_round_a_player_portrait_entry():
    """MMT 专则: kind=experience（玩家画像）条目——pattern 必填, subject 引擎固定。"""
    raw = {"episodes": [
        {"kind": "experience", "pattern": "玩家的生日是 5 月 20 日",
         "verbatim": "我生日是 5 月 20 日哦", "tags": ["玩家"], "significance": 0.7},
        {"kind": "experience", "title": "忘了 pattern"},       # 缺 pattern → 拒
    ]}
    items, result = digest_registry.parse_round_a(raw)
    assert not result.is_valid
    assert any("pattern" in e for e in result.errors)
    assert len(items) == 1
    assert items[0]["kind"] == "experience"
    assert items[0]["subject"] == "player"          # 引擎固定, 不信任 LLM
    assert items[0]["pattern"].startswith("玩家的生日")


def test_round_a_bad_kind_rejected():
    items, result = digest_registry.parse_round_a({"episodes": [
        {"kind": "belief", "content": "不是合法形态"},
    ]})
    assert not result.is_valid
    assert any("kind 非法" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Round B parse
# ---------------------------------------------------------------------------

def test_round_b_valid_decisions():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "touch", "target": "u0001"},
        {"episode": "m0002", "decision": "update", "target": "u0002",
         "patch": {"content": "新表述", "significance": 0.9}},
        {"episode": "m0003", "decision": "add", "kind": "belief",
         "subject": "我对老师的信任", "content": "老师是第一个不嫌弃我的人",
         "tags": ["信任"], "significance": 0.85},
    ], "evidence": [{"function": "fe", "confidence": 0.9,
                     "quote": "老师把猫抱到我腿边"}],
       "affection_exp_delta": 30}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002", "m0003"},
        target_ids={"u0001", "u0002", "u0003"})
    assert result.is_valid, result.errors
    assert len(rows) == 3
    assert rows[0] == {"episode": "m0001", "decision": "touch", "target": "u0001"}
    assert rows[1]["patch"]["content"] == "新表述"
    assert rows[2]["kind"] == "belief" and rows[2]["content"]


def test_round_b_coverage_required():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "touch", "target": "u0001"},
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002"}, target_ids={"u0001"})
    assert not result.is_valid
    assert any("未覆盖" in e and "m0002" in e for e in result.errors)


def test_round_b_id_discipline():
    raw = {"decisions": [
        {"episode": "ghost001", "decision": "touch", "target": "u0001"},  # 编造 episode
        {"episode": "m0001", "decision": "touch", "target": "u0099"},      # 编造 target
        {"episode": "m0002", "decision": "add", "kind": "belief",
         "subject": "s", "content": "c"},
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002"}, target_ids={"u0001"})
    assert not result.is_valid
    assert any("episode 不在本轮" in e for e in result.errors)
    assert any("target 不在渲染列表" in e for e in result.errors)


def test_round_b_update_guards():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "update", "target": "u0001",
         "patch": {"epistemic": "canon_fact"}},          # epistemic 禁改
        {"episode": "m0002", "decision": "update", "target": "u0001",
         "patch": {}},                                     # 空 patch
        {"episode": "m0003", "decision": "add", "kind": "experience",
         "pattern": "老师总说摸鱼"},                        # experience 无 content 可
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002", "m0003"}, target_ids={"u0001"})
    assert not result.is_valid
    assert any("epistemic" in e for e in result.errors)
    assert any("patch" in e for e in result.errors)
    assert len(rows) == 1 and rows[0]["kind"] == "experience"


def test_round_b_bad_decision_kind():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "delete"},       # 非法决策
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001"}, target_ids={"u0001"})
    assert not result.is_valid
    assert any("decision 非法" in e for e in result.errors)


# ---------------------------------------------------------------------------
# must_touch（板块 5: 引擎疑似同主题标注 → 结构强制 touch/update）
# ---------------------------------------------------------------------------

def test_round_b_must_touch_forbids_add():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "add", "kind": "belief",
         "subject": "s", "content": "又一条同主题认知"},
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001"}, target_ids={"u0001"},
        must_touch={"m0001": "u0001"})
    assert not result.is_valid
    assert any("疑似同主题" in e and "touch/update" in e for e in result.errors)
    assert rows == []                                  # 违规行被拒


def test_round_b_must_touch_allows_touch_and_update():
    raw = {"decisions": [
        {"episode": "m0001", "decision": "touch", "target": "u0001"},
        {"episode": "m0002", "decision": "update", "target": "u0001",
         "patch": {"content": "深化后的表述"}},
    ]}
    rows, result = digest_registry.parse_round_b(
        raw, episode_ids={"m0001", "m0002"}, target_ids={"u0001"},
        must_touch={"m0001": "u0001", "m0002": "u0001"})
    assert result.is_valid, result.errors
    assert len(rows) == 2
