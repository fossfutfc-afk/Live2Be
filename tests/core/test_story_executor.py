# -*- coding: utf-8 -*-
"""STORY 契约/执行层单测 — 双动作 story_scene/story_end + StoryExecutor。

parse_story_scene : 单串容错 / choices 截断 / 残留 is_end 静默丢弃 / 空段落 ContractError
parse_story_end   : 非空 choices 硬拒绝（结构「收尾无选项」落点, nudge 改用 story_scene）
build_story_registry : 两动作, 全 APPROVAL_AUTO, 无 validate, prompt_fields={action,payload}
StoryExecutor     : 域分派 / mmt 域拒绝 / 未知动作拒绝
BondScene.from_action : is_end 由动作类型推导（story_scene False / story_end True）

运行: python -m pytest tests/core/test_story_executor.py
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from contract import AgentAction, APPROVAL_AUTO, ContractError, DOMAIN_MMT, DOMAIN_STORY
from core.bond.bond_story import BondScene
from core.bond.bond_actions import (
    MAX_SCENE_CHOICES,
    build_story_registry,
    parse_story_end,
    parse_story_scene,
)
from core.bond.bond_executor import StoryExecError, StoryExecutor


def _action(action: str, payload: dict) -> AgentAction:
    return AgentAction(
        action=action, domain=DOMAIN_STORY, approval=APPROVAL_AUTO, payload=payload,
    )


def _parse(action: str, payload: dict):
    return build_story_registry().parse({"action": action, "payload": payload})


# ----------------------------------------------------------------------------
# parse_story_scene: 机器侧容错 + 残留 is_end 静默丢弃
# ----------------------------------------------------------------------------

def test_parse_story_scene_single_string_tolerance():
    a, r = _parse("story_scene", {"paragraphs": "单段", "choices": "单选"})
    assert r.is_valid and a is not None
    assert a.payload["paragraphs"] == ["单段"]
    assert a.payload["choices"] == ["单选"]
    print("    parse_story_scene: 单串 → 单元素列表容错")


def test_parse_story_scene_truncate_and_is_end_dropped():
    a, r = _parse("story_scene", {
        "paragraphs": ["一段。"], "is_end": True,
        "choices": ["1", "2", "3", "4", "5"],
    })
    assert r.is_valid
    assert len(a.payload["choices"]) == MAX_SCENE_CHOICES, a.payload
    assert "is_end" not in a.payload, "story_scene 残留 is_end 应静默丢弃（迁移容错）"
    print("    parse_story_scene: choices 截断 + 残留 is_end 丢弃")


def test_parse_story_scene_contract_error():
    with pytest.raises(ContractError):
        parse_story_scene({"paragraphs": []})
    with pytest.raises(ContractError):
        parse_story_scene({"paragraphs": "   "})
    with pytest.raises(ContractError):
        parse_story_scene({"paragraphs": "一段。", "choices": 42})
    # registry 层: ContractError 被收集为解析错误, 不 raise
    a, r = _parse("story_scene", {"paragraphs": []})
    assert a is None and not r.is_valid and "paragraphs" in r.errors[0]
    print("    parse_story_scene: 空段落/坏 choices → ContractError（registry 收集为错误）")


# ----------------------------------------------------------------------------
# parse_story_end: 收尾无选项结构性保证
# ----------------------------------------------------------------------------

def test_parse_story_end_rejects_nonempty_choices():
    a, r = _parse("story_end", {"paragraphs": ["收尾了。"], "choices": ["继续"]})
    assert a is None and not r.is_valid
    assert "story_scene" in r.errors[0], "拒绝理由应 nudge 改用 story_scene"
    # 直接调 parse 函数也是 ContractError
    with pytest.raises(ContractError):
        parse_story_end({"paragraphs": ["收尾了。"], "choices": ["继续"]})
    print("    parse_story_end: 非空 choices 硬拒绝（nudge 改用 story_scene）")


def test_parse_story_end_empty_or_missing_choices_ok():
    a, r = _parse("story_end", {"paragraphs": ["收尾了。"]})
    assert r.is_valid and a.payload == {"paragraphs": ["收尾了。"]}
    a, r = _parse("story_end", {"paragraphs": ["收尾了。"], "choices": []})
    assert r.is_valid and a.payload == {"paragraphs": ["收尾了。"]}
    print("    parse_story_end: 空/缺省 choices 静默忽略, payload 干净")


# ----------------------------------------------------------------------------
# build_story_registry: 双动作 AUTO / 无 validate / prompt_fields
# ----------------------------------------------------------------------------

def test_registry_two_actions_auto_no_validate():
    reg = build_story_registry()
    assert reg.action_names() == ["story_end", "story_scene"], reg.action_names()
    for name in ("story_scene", "story_end"):
        spec = reg.spec(name)
        assert spec.approval == APPROVAL_AUTO, name
        assert spec.validate is None, f"{name} 不应有 validate 钩子（结构性保证）"
        assert spec.prompt_fields == frozenset({"action", "payload"}), name
        assert spec.payload_schema, f"{name} 应有 payload_schema"
    print("    registry: 两动作 AUTO / 无 validate / prompt_fields={action,payload}")


# ----------------------------------------------------------------------------
# StoryExecutor: 域分派 / 拒绝
# ----------------------------------------------------------------------------

def test_executor_dispatch_and_reject():
    ex = StoryExecutor()
    assert ex.execute(_action("story_scene", {})).ok
    assert ex.execute(_action("story_end", {})).message == "收尾场景已就绪, 剧情将结束"
    # mmt 域拒绝（域隔离）
    with pytest.raises(StoryExecError):
        ex.execute(AgentAction(action="mmt_chat", domain=DOMAIN_MMT))
    # 未知动作拒绝
    with pytest.raises(StoryExecError):
        ex.execute(_action("story_reflect", {}))
    print("    executor: 域分派 / mmt 域拒绝 / 未知动作拒绝")


# ----------------------------------------------------------------------------
# BondScene.from_action: is_end 由动作类型推导
# ----------------------------------------------------------------------------

def test_from_action_derives_is_end():
    scene = BondScene.from_action(
        _action("story_scene", {"paragraphs": ["中段"], "choices": ["A"]}))
    assert not scene.is_end and scene.choices == ["A"]
    end = BondScene.from_action(_action("story_end", {"paragraphs": ["收尾"]}))
    assert end.is_end and not end.choices
    # 滤非 str（宁缺勿错）
    robust = BondScene.from_action(
        _action("story_end", {"paragraphs": ["好", 42, None]}))
    assert robust.paragraphs == ["好"] and robust.is_end
    print("    from_action: is_end 由动作类型推导, 滤非 str")


# ----------------------------------------------------------------------------
# beats / place（视觉意图协议 §3/§5: 可选, 向后兼容）
# ----------------------------------------------------------------------------

def test_parse_beats_place_optional_and_clean():
    # 不带 beats/place → payload 干净（无该键, 向后兼容）
    a, r = _parse("story_scene", {"paragraphs": ["一段。"]})
    assert r.is_valid
    assert "beats" not in a.payload and "place" not in a.payload
    # 带 beats/place → 解析并保留
    a, r = _parse("story_scene", {
        "paragraphs": ["她脸红了。"],
        "beats": [{"text": "她脸红了，低下头", "emotion": "embarass"}],
        "place": "class_room",
    })
    assert r.is_valid
    assert a.payload["beats"] == [{"text": "她脸红了，低下头", "emotion": "embarass"}]
    assert a.payload["place"] == "class_room"
    print("    beats/place: 可选（缺省干净）/ 出现则解析")


def test_parse_beats_place_contract_errors():
    # beats 非数组 / 项非对象 / 字段非 str → ContractError（registry 收集为错误）
    for bad in (
        {"paragraphs": ["x"], "beats": "not-list"},
        {"paragraphs": ["x"], "beats": [42]},
        {"paragraphs": ["x"], "beats": [{"text": "t"}]},        # 缺 emotion
        {"paragraphs": ["x"], "beats": [{"emotion": "e"}]},     # 缺 text
        {"paragraphs": ["x"], "beats": [{"text": 42, "emotion": "e"}]},
        {"paragraphs": ["x"], "place": 42},
    ):
        a, r = _parse("story_scene", bad)
        assert a is None and not r.is_valid, bad
    # 空 emotion → 宽容保留（下游降级, 宁缺勿错不拒绝）
    a, r = _parse("story_scene", {
        "paragraphs": ["x"], "beats": [{"text": "t", "emotion": "  "}]})
    assert r.is_valid and a.payload["beats"] == [{"text": "t", "emotion": ""}]
    print("    beats/place: 结构错误 ContractError; 空 emotion 宽容保留")


def test_story_end_beats_place_and_scene_carry():
    # story_end 也支持 beats/place
    a, r = _parse("story_end", {
        "paragraphs": ["收尾了。"],
        "beats": [{"text": "她笑了", "emotion": "smile"}],
        "place": "rooftop",
    })
    assert r.is_valid
    assert a.payload["beats"] and a.payload["place"] == "rooftop"
    # BondScene.from_action 携带 beats/place（含 to_dict/from_dict 往返）
    scene = BondScene.from_action(a)
    assert scene.beats == [{"text": "她笑了", "emotion": "smile"}]
    assert scene.place == "rooftop"
    rt = BondScene.from_dict(scene.to_dict())
    assert rt.beats == scene.beats and rt.place == scene.place
    # 纯文本（无 beats/place）→ to_dict 省略（旧档兼容）
    plain = BondScene.from_action(_action("story_scene", {"paragraphs": ["p"]}))
    assert "beats" not in plain.to_dict() and "place" not in plain.to_dict()
    print("    story_end beats/place + BondScene 携带/往返/旧档省略")
