"""图式 wiki 节点数据结构测试（AGENT_BRAIN.md §1 / M1）。"""
import json

from core.brain.wiki_v2 import (
    PLAYER_SUBJECT,
    PRECIOUS_THRESHOLD,
    BrainNode,
    make_node,
)
from core.brain.wiki_v2.nodes import format_id


def test_format_id():
    assert format_id("m", 3) == "m0003"
    assert format_id("c", 2) == "c0002"
    assert format_id("e", 42) == "e0042"


def test_episode_roundtrip():
    node = make_node("episode", narration="那天傍晚老师陪我在杂草屋看苔藓",
                     verbatim="「地砖里长出的苔藓也可以是花」",
                     significance=0.8, tags=["老师", "杂草屋"],
                     observer="igusa_haruka", event_seq=[42, 58],
                     ts="2026-09-01T20:00:00", links=["m0009"])
    assert node.validate() == []
    assert node.is_precious is True
    assert node.dedup_key() == ("episode", (42, 58))
    # jsonl 行往返
    line = node.to_json_line()
    back = BrainNode.from_json_line(line)
    assert back.to_dict() == node.to_dict()
    # 完整 dict 往返（含空字段补齐）
    assert BrainNode.from_dict(node.to_dict()).to_dict() == node.to_dict()


def test_episode_required_narration():
    node = make_node("episode", verbatim="只有原话没有叙述")
    assert "episode 缺少必填字段: narration" in node.validate()


def test_episode_epistemic_guard():
    node = make_node("episode", narration="x", epistemic="inferred_belief")
    errs = node.validate()
    assert any("episode 节点 epistemic 只能是 observed_fact/reported_fact" in e for e in errs)


def test_fact_canon_rules():
    # 出厂基座: source=experience + source_key 溯源
    ok = make_node("fact", content="遥香曾因拆炸弹事件对 sensei 建立信任",
                   significance=0.95, epistemic="canon_fact",
                   source="experience", source_key="self.regular.1")
    assert ok.validate() == []
    assert ok.is_seed() is True
    # 护栏: fact 不能是 observed; source 必须是 experience/knowledge
    bad_epi = make_node("fact", content="x", epistemic="observed_fact",
                        source="experience", source_key="k")
    assert any("canon_fact" in e for e in bad_epi.validate())
    bad_src = make_node("fact", content="x", epistemic="canon_fact",
                        source="digest", source_key="k")
    assert any("fact 节点 source 必须" in e for e in bad_src.validate())
    # 缺 source_key
    no_key = make_node("fact", content="x", epistemic="canon_fact", source="knowledge")
    assert any("source_key" in e for e in no_key.validate())


def test_belief_requires_support():
    # 无支撑升华拒绝
    node = make_node("belief", content="老师是第一个不会嫌弃我的人", subject="sensei")
    assert any("links ≥1" in e for e in node.validate())
    # 有支撑通过 + epistemic 护栏
    ok = make_node("belief", content="老师是第一个不会嫌弃我的人", subject="sensei",
                   significance=0.9, epistemic="inferred_belief",
                   links=["m0003", "m0001"], growth="从自卑到被需要")
    assert ok.validate() == []
    bad = make_node("belief", content="x", epistemic="observed_fact", links=["m0001"])
    assert any("inferred_belief" in e for e in bad.validate())


def test_experience_and_player_emphasis():
    # 普通 experience: count 由引擎 = len(links)
    exp = make_node("experience", pattern="sensei 提到工作繁忙", subject="sensei",
                    examples=["「这周又忙成狗了」"], links=["m0011", "m0015", "m0020"])
    assert exp.validate() == []
    assert exp.count == 3          # normalize 后 count = len(links)
    assert exp.is_player_experience is False
    # player experience（R5 强调点）: subject=player
    pe = make_node("experience", pattern="摸鱼", subject=PLAYER_SUBJECT,
                   examples=["「今天也摸鱼」"], links=["m0030", "m0033"])
    assert pe.validate() == []
    assert pe.is_player_experience is True
    assert pe.dedup_key() == ("experience", tuple(pe.event_seq))  # 空 event_seq 不去重冲突
    # examples 超限截断
    many = make_node("experience", pattern="p", subject="s",
                     examples=["1", "2", "3", "4"], links=["m0001"])
    assert len(many.examples) == 3


def test_relation_node():
    node = make_node("relation", subject="igusa_haruka", object="sensei",
                     relation="信任加深", note="约定常来陪她", event_seq=[10])
    assert node.validate() == []
    assert node.dedup_key() == ("relation", (10,))
    missing = make_node("relation", subject="a", relation="b")
    assert any("object" in e for e in missing.validate())


def test_significance_clamp_and_precious():
    assert BrainNode.from_dict({"significance": 3.0}).significance == 1.0
    assert BrainNode.from_dict({"significance": -1}).significance == 0.0
    assert BrainNode.from_dict({"significance": "垃圾"}).significance == 0.5
    node = make_node("episode", narration="x", significance=PRECIOUS_THRESHOLD)
    assert node.is_precious is True
    node2 = make_node("episode", narration="x", significance=0.79)
    assert node2.is_precious is False


def test_loose_from_dict_bad_kind_epistemic():
    node = BrainNode.from_dict({"id": "m0001", "kind": "whatever", "epistemic": "nope"})
    assert node.kind == "episode"      # 坏 kind 降级
    assert node.epistemic == "observed_fact"
    assert node.validate()             # 校验会报未知 kind 错误
    assert BrainNode.from_dict(None).id == ""
    assert BrainNode.from_dict("junk") .kind == "episode"


def test_json_line_bad_input():
    assert BrainNode.from_json_line("{bad json").id == ""
    line = json.dumps({"id": "e0002", "kind": "experience", "pattern": "摸鱼",
                       "subject": "player", "significance": 0.75},
                      ensure_ascii=False)
    node = BrainNode.from_json_line(line)
    assert node.kind == "experience" and node.pattern == "摸鱼"
    assert node.subject == PLAYER_SUBJECT
