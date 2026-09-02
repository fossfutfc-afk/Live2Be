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
            {"text": "对不起...", "emotion": "panic"},
            {"text": "啊..没关系吗..欸嘿嘿", "emotion": "smile"},
        ],
    })
    assert r.is_valid and a is not None
    # 2026-09-02 切分权移交定稿: 骨架 emotion 一律丢弃（标注层唯一真源,
    # 防双源/锚定——生成 LLM 不再背情绪负担）
    assert all("emotion" not in p for p in a.payload["paragraphs"])
    assert [p["text"] for p in a.payload["paragraphs"]] == [
        "啊...我是不是又做错什么了", "对不起...", "啊..没关系吗..欸嘿嘿"]
    # 骨架缺 emotion（旧两遍式 C 模式）→ 照常合法（标注层全量回填）
    a2, r2 = _parse("story_scene", {
        "paragraphs": [{"text": "我忘记标表情了", "emotion": "smile"},
                       {"text": "这行没标"}],
    })
    assert r2.is_valid and a2 is not None
    assert "emotion" not in a2.payload["paragraphs"][0]
    assert "emotion" not in a2.payload["paragraphs"][1]
    # 旧习惯模型: 裸字符串段落 → 当单自然段（兼容）;
    # 有 choices 时必须带 branches（板块契约）——单串 choices 也触发强制
    a, r = _parse("story_scene", {
        "paragraphs": "单段", "choices": "单选",
        "branches": {"单选": "分支段"}})
    assert r.is_valid
    assert a.payload["paragraphs"] == [{"text": "单段"}]
    assert a.payload["choices"] == ["单选"]
    assert a.payload["branches"] == {"单选": [{"text": "分支段"}]}
    print("    parse_story_scene: 骨架 emotion 丢弃（标注层唯一真源）+ 单串容错")


def test_parse_story_scene_sentence_split():
    """2026-09-02 切分权移交: 自然段 → sentence_splitter 切句（块保护/数字点/
    碎句合并）; 骨架 emotion 丢弃; 省略号是语气停顿不算句末。"""
    # 多句自然段 → 切分（碎句合并: 5 字首句并入后句）
    a, r = _parse("story_scene", {"paragraphs": [
        {"text": "她站在窗边。风把她的发梢吹起来。她回头看了你一眼。",
         "emotion": "smile"}]})
    assert r.is_valid
    assert [p["text"] for p in a.payload["paragraphs"]] == [
        "她站在窗边。风把她的发梢吹起来。", "她回头看了你一眼。"]
    # 省略号是语气停顿不是句末——"老师……我这种人……"不切（0 个句末标点）
    a2, r2 = _parse("story_scene", {"paragraphs": [
        {"text": "老师……我这种人……也可以吗？", "emotion": "embarrass"}]})
    assert r2.is_valid
    assert len(a2.payload["paragraphs"]) == 1
    # 感叹号/问号同样切; 逗号分句不切; 无标点原样单段
    a3, r3 = _parse("story_scene", {"paragraphs": [
        {"text": "好耶！我们出发吧？走走走。", "emotion": "happy"}]})
    assert r3.is_valid
    assert [p["text"] for p in a3.payload["paragraphs"]] == ["好耶！", "我们出发吧？", "走走走。"]
    a4, r4 = _parse("story_scene", {"paragraphs": [
        {"text": "她站在窗边，风把她的发梢吹起来。", "emotion": "smile"}]})
    assert r4.is_valid and len(a4.payload["paragraphs"]) == 1
    # 括号块保护（块内句号不切——LLM 长文本整段输出也能正确切句）
    a5, r5 = _parse("story_scene", {"paragraphs": [
        {"text": "（她站在门口，还能听到心跳。她深吸一口气。）「打扰了。」她轻声说。",
         "emotion": "nervous"}]})
    assert r5.is_valid
    assert [p["text"] for p in a5.payload["paragraphs"]] == [
        "（她站在门口，还能听到心跳。她深吸一口气。）", "「打扰了。」", "她轻声说。"]
    print("    parse_story_scene: 自然段切句（合并/块保护/数字点）+ 省略号不切")


def test_parse_story_scene_branches():
    """2026-08-30 板块契约: branches 同响应分支（有 choices 必带; 键对齐; 段落同校验）。"""
    # 有 choices 无 branches → ContractError（防 LLM 省略——memorial 教训）
    a, r = _parse("story_scene", {
        "paragraphs": [{"text": "x", "emotion": "nomal"}], "choices": ["A"]})
    assert a is None and not r.is_valid and "branches" in r.errors[0]
    # 正常: branches 解析 + 键对齐（只取 choices 的键）+ 段落同校验（切分）
    a, r = _parse("story_scene", {
        "paragraphs": [{"text": "正文。", "emotion": "nomal"}],
        "choices": ["A", "B"],
        "branches": {
            "A": [{"text": "分支A推开门走了进去。第二句也在这段里。", "emotion": "smile"}],
            "B": "单段分支",
            "C": [{"text": "非选项键被忽略", "emotion": "nomal"}],
        }})
    assert r.is_valid
    assert list(a.payload["branches"].keys()) == ["A", "B"], a.payload["branches"]
    assert a.payload["branches"]["A"] == [
        {"text": "分支A推开门走了进去。"},
        {"text": "第二句也在这段里。"},
    ]
    assert a.payload["branches"]["B"] == [{"text": "单段分支"}]
    # 分支段落同样切分（多句自然段 → 句段, emotion 丢弃——不打回）
    a, r = _parse("story_scene", {
        "paragraphs": [{"text": "正文。", "emotion": "nomal"}],
        "choices": ["A"],
        "branches": {"A": [{"text": "分支一的分支内容。分支二的分支内容。", "emotion": "smile"}]}})
    assert r.is_valid
    assert [p["text"] for p in a.payload["branches"]["A"]] == [
        "分支一的分支内容。", "分支二的分支内容。"]
    assert all("emotion" not in p for p in a.payload["branches"]["A"])
    # 无 choices（纯叙事板块）→ 不需要 branches
    a, r = _parse("story_scene", {"paragraphs": [{"text": "纯叙事。", "emotion": "nomal"}]})
    assert r.is_valid and "branches" not in a.payload
    # 分支段落缺 emotion → 通过（骨架模式, 标注层全量补标）
    a, r = _parse("story_scene", {
        "paragraphs": [{"text": "正文。", "emotion": "nomal"}],
        "choices": ["A"],
        "branches": {"A": [{"text": "分支忘了标表情。"}]}})
    assert r.is_valid
    assert "emotion" not in a.payload["branches"]["A"][0]
    # BondScene 往返（branches 序列化/回放）——用带 branches 的场景（不走契约解析）
    scene = BondScene.from_action(_action("story_scene", {
        "paragraphs": [{"text": "正文。", "emotion": "nomal"}],
        "choices": ["A", "B"],
        "branches": {"A": [{"text": "分支A。", "emotion": "smile"}]}}))
    assert "A" in scene.branches
    rt = BondScene.from_dict(scene.to_dict())
    assert rt.branches["A"] == [{"text": "分支A。", "emotion": "smile"}]
    print("    parse_story_scene: branches（有 choices 必带/键对齐/切分继承/往返）")


def test_parse_story_scene_truncate_and_is_end_dropped():
    a, r = _parse("story_scene", {
        "paragraphs": ["一段。"], "is_end": True,
        "choices": ["1", "2", "3", "4", "5"],
        "branches": {"1": [{"text": "b1", "emotion": "nomal"}],
                     "2": [{"text": "b2", "emotion": "nomal"}],
                     "3": [{"text": "b3", "emotion": "nomal"}],
                     "4": [{"text": "b4", "emotion": "nomal"}],
                     "5": [{"text": "b5", "emotion": "nomal"}]},
    })
    assert r.is_valid
    assert len(a.payload["choices"]) == MAX_SCENE_CHOICES, a.payload
    # branches 键与截断后的 choices 对齐（4/5 被丢弃）
    assert list(a.payload["branches"].keys()) == ["1", "2", "3"], a.payload["branches"]
    assert "is_end" not in a.payload, "story_scene 残留 is_end 应静默丢弃（迁移容错）"
    print("    parse_story_scene: choices 截断 + branches 键对齐 + 残留 is_end 丢弃")


def test_parse_story_scene_contract_error():
    with pytest.raises(ContractError):
        parse_story_scene({"paragraphs": []})
    with pytest.raises(ContractError):
        parse_story_scene({"paragraphs": "   "})
    with pytest.raises(ContractError):
        parse_story_scene({"paragraphs": "一段。", "choices": 42})
    # 段落结构错误（text 非 str）→ ContractError; 2026-08-31 两遍式 C:
    # emotion 可选（骨架模式）——非 str/缺失不再打回（标注层负责补标）
    with pytest.raises(ContractError):
        parse_story_scene({"paragraphs": [{"text": 42}]})
    a, r = _parse("story_scene", {"paragraphs": [{"text": "x", "emotion": 42}]})
    assert r.is_valid and "emotion" not in a.payload["paragraphs"][0]
    a, r = _parse("story_scene", {"paragraphs": [{"text": "x"}]})
    assert r.is_valid and "emotion" not in a.payload["paragraphs"][0]
    # registry 层: ContractError 被收集为解析错误, 不 raise
    a, r = _parse("story_scene", {"paragraphs": []})
    assert a is None and not r.is_valid and "paragraphs" in r.errors[0]
    print("    parse_story_scene: 空段落/坏结构/坏 choices → ContractError; emotion 可选")


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
    # story_end 也支持 place; 骨架 emotion 丢弃（标注层唯一真源）
    a, r = _parse("story_end", {
        "paragraphs": [{"text": "她笑了", "emotion": "smile"}],
        "place": "rooftop",
    })
    assert r.is_valid
    assert a.payload["paragraphs"] == [{"text": "她笑了"}]
    assert a.payload["place"] == "rooftop"
    # BondScene 携带（含 to_dict/from_dict 往返; 直接 from_action 不经 parse,
    # emotion 保留——demo/测试/标注回填场景用）
    scene = BondScene.from_action(a)
    assert scene.paragraphs == [{"text": "她笑了"}]
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
