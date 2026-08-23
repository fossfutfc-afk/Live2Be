# -*- coding: utf-8 -*-
"""STORY 契约/执行层单测 — 三动作 story_scene/story_end/memorial_enter + StoryExecutor。

parse_story_scene : 段落 {text, emotion?}（2026-08-23 情绪内联, 删 beats）/ 单串容错 /
                    choices 截断 / 残留 is_end 静默丢弃 / 空段落 ContractError
parse_story_end   : 非空 choices 硬拒绝（结构「收尾无选项」落点, nudge 改用 story_scene）
parse_memorial_enter : prompt 必填 + 场景内容（§4.7, 纪念子模式进入动作, 属 story 域）
build_story_registry : 三动作, 全 APPROVAL_AUTO, 无 validate, prompt_fields={action,payload}
StoryExecutor     : 域分派 / mmt 域拒绝 / 未知动作拒绝
BondScene.from_action : is_end 由动作类型推导; paragraphs 结构兼容
para_emotions     : 逐段 emotion, 缺省延续（纯确定性, 零语义判断）

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
# parse_story_scene: 段落 {text, emotion?} + 机器侧容错 + 残留 is_end 静默丢弃
# ----------------------------------------------------------------------------

def test_parse_story_scene_paragraphs_inline_emotion():
    a, r = _parse("story_scene", {
        "paragraphs": [
            {"text": "啊...我是不是又做错什么了", "emotion": "panic"},
            {"text": "对不起..."},
            {"text": "啊..没关系吗..欸嘿嘿", "emotion": "smile"},
        ],
    })
    assert r.is_valid and a is not None
    assert a.payload["paragraphs"] == [
        {"text": "啊...我是不是又做错什么了", "emotion": "panic"},
        {"text": "对不起..."},
        {"text": "啊..没关系吗..欸嘿嘿", "emotion": "smile"},
    ]
    # 旧习惯模型: 裸字符串段落 → 包成 {"text": ...}（兼容）
    a, r = _parse("story_scene", {"paragraphs": "单段", "choices": "单选"})
    assert r.is_valid
    assert a.payload["paragraphs"] == [{"text": "单段"}]
    assert a.payload["choices"] == ["单选"]
    print("    parse_story_scene: 段落 {text, emotion?} 内联 + 单串容错")


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
    # 段落结构错误（text 非 str）→ ContractError; emotion 非 str → 宽容忽略
    with pytest.raises(ContractError):
        parse_story_scene({"paragraphs": [{"text": 42}]})
    a, r = _parse("story_scene", {"paragraphs": [{"text": "x", "emotion": 42}]})
    assert r.is_valid and a.payload["paragraphs"] == [{"text": "x"}]
    # registry 层: ContractError 被收集为解析错误, 不 raise
    a, r = _parse("story_scene", {"paragraphs": []})
    assert a is None and not r.is_valid and "paragraphs" in r.errors[0]
    print("    parse_story_scene: 空段落/坏结构/坏 choices → ContractError")


# ----------------------------------------------------------------------------
# parse_story_end: 收尾无选项结构性保证
# ----------------------------------------------------------------------------

def test_parse_story_end_rejects_nonempty_choices():
    a, r = _parse("story_end", {"paragraphs": ["收尾了。"], "choices": ["继续"]})
    assert a is None and not r.is_valid
    assert "story_scene" in r.errors[0], "拒绝理由应 nudge 改用 story_scene"
    with pytest.raises(ContractError):
        parse_story_end({"paragraphs": ["收尾了。"], "choices": ["继续"]})
    print("    parse_story_end: 非空 choices 硬拒绝（nudge 改用 story_scene）")


def test_parse_story_end_empty_or_missing_choices_ok():
    a, r = _parse("story_end", {"paragraphs": ["收尾了。"]})
    assert r.is_valid and a.payload == {"paragraphs": [{"text": "收尾了。"}]}
    a, r = _parse("story_end", {"paragraphs": ["收尾了。"], "choices": []})
    assert r.is_valid and a.payload == {"paragraphs": [{"text": "收尾了。"}]}
    print("    parse_story_end: 空/缺省 choices 静默忽略, payload 干净")


# ----------------------------------------------------------------------------
# build_story_registry: 双动作 AUTO / 无 validate / prompt_fields
# ----------------------------------------------------------------------------

def test_registry_actions_auto_no_validate():
    reg = build_story_registry()
    assert reg.action_names() == ["memorial_enter", "story_end", "story_scene"], reg.action_names()
    for name in ("story_scene", "story_end", "memorial_enter"):
        spec = reg.spec(name)
        assert spec.approval == APPROVAL_AUTO, name
        assert spec.validate is None, f"{name} 不应有 validate 钩子（结构性保证）"
        assert spec.prompt_fields == frozenset({"action", "payload"}), name
        assert spec.payload_schema, f"{name} 应有 payload_schema"
    print("    registry: 三动作 AUTO / 无 validate / prompt_fields={action,payload}")


# ----------------------------------------------------------------------------
# StoryExecutor: 域分派 / 拒绝
# ----------------------------------------------------------------------------

def test_executor_dispatch_and_reject():
    ex = StoryExecutor()
    assert ex.execute(_action("story_scene", {})).ok
    assert ex.execute(_action("story_end", {})).message == "收尾场景已就绪, 剧情将结束"
    with pytest.raises(StoryExecError):
        ex.execute(AgentAction(action="mmt_chat", domain=DOMAIN_MMT))
    with pytest.raises(StoryExecError):
        ex.execute(_action("story_reflect", {}))
    print("    executor: 域分派 / mmt 域拒绝 / 未知动作拒绝")


# ----------------------------------------------------------------------------
# BondScene.from_action: is_end 推导 + paragraphs 结构 + place
# ----------------------------------------------------------------------------

def test_from_action_derives_is_end():
    scene = BondScene.from_action(
        _action("story_scene", {"paragraphs": [{"text": "中段"}], "choices": ["A"]}))
    assert not scene.is_end and scene.choices == ["A"]
    end = BondScene.from_action(_action("story_end", {"paragraphs": [{"text": "收尾"}]}))
    assert end.is_end and not end.choices
    # 坏段落（非 dict / 空 text）→ 滤掉（宁缺勿错）
    robust = BondScene.from_action(
        _action("story_end", {"paragraphs": [{"text": "好"}, 42, {"text": ""}]}))
    assert robust.paragraphs == [{"text": "好"}] and robust.is_end
    print("    from_action: is_end 推导 + 坏段落滤除")


def test_story_end_place_and_scene_carry():
    # story_end 也支持 place; paragraphs emotion 内联携带
    a, r = _parse("story_end", {
        "paragraphs": [{"text": "她笑了", "emotion": "smile"}],
        "place": "rooftop",
    })
    assert r.is_valid
    assert a.payload["paragraphs"] == [{"text": "她笑了", "emotion": "smile"}]
    assert a.payload["place"] == "rooftop"
    # BondScene 携带（含 to_dict/from_dict 往返）
    scene = BondScene.from_action(a)
    assert scene.paragraphs == [{"text": "她笑了", "emotion": "smile"}]
    assert scene.place == "rooftop"
    rt = BondScene.from_dict(scene.to_dict())
    assert rt.paragraphs == scene.paragraphs and rt.place == scene.place
    # 纯文本（无 emotion/place）→ to_dict 省略 place（旧档兼容）
    plain = BondScene.from_action(_action("story_scene", {"paragraphs": [{"text": "p"}]}))
    assert "place" not in plain.to_dict()
    print("    story_end place + BondScene paragraphs 携带/往返")


# ----------------------------------------------------------------------------
# para_emotions: 逐段 emotion, 缺省延续（纯确定性, 零语义判断）
# ----------------------------------------------------------------------------

def test_para_emotions_inherit():
    # 无 emotion → 每段默认
    s = BondScene.from_action(_action("story_scene", {
        "paragraphs": [{"text": "a"}, {"text": "b"}]}))
    assert s.para_emotions() == ["nomal", "nomal"]
    # 段1 标 emotion → 后续缺省延续（慌乱 → 开心 例子）
    s = BondScene.from_action(_action("story_scene", {
        "paragraphs": [
            {"text": "啊...我是不是又做错什么了", "emotion": "panic"},
            {"text": "对不起..."},
            {"text": "啊..没关系吗..欸嘿嘿", "emotion": "smile"},
        ]}))
    assert s.para_emotions() == ["panic", "panic", "smile"]
    # 中途变化 + 尾段缺省延续
    s = BondScene.from_action(_action("story_scene", {
        "paragraphs": [
            {"text": "a", "emotion": "embarrass"},
            {"text": "b", "emotion": "giggle"},
            {"text": "c"},
        ]}))
    assert s.para_emotions() == ["embarrass", "giggle", "giggle"]
    # 旧 str 段落（兼容）→ 默认
    s = BondScene.from_dict({"paragraphs": ["x", "y"]})
    assert s.para_emotions() == ["nomal", "nomal"]
    print("    para_emotions: 显式 emotion + 缺省延续（零语义判断）")
