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


# ---------------------------------------------------------------------------
# ★ 序列化字段的三方一致（2026-09-17 补 —— 孤儿字段就是这么藏住的）
# ---------------------------------------------------------------------------

def test_every_serialized_field_is_parsed_back():
    """`to_dict` 里的字段必须也能被 `from_dict` 读回来。

    为什么单开一条: `to_dict` 是一个**手写字段名清单**, `from_dict` 是另一串
    **手写赋值行** —— 两处不同源。字段只写在 `to_dict` 里（= 落库）而没写在
    `from_dict` 里（= 读不回）时, 节点"写出去就变形", 而且**往返测试也抓不到**
    （往返用的是同一份内存对象）。

    2026-09-17 的孤儿字段审计正是从"三方缺两方"入手的（生产者/消费者/数据）。
    这条用例钉住"落库 ⇄ 读回"这一对; 另两方靠 grep 审。

    做法: 逐个把"清单里的字段"设成非空值 → 往返 → 看是否还在。
    """
    from dataclasses import fields as _dc_fields

    node = BrainNode(id="m0001", kind="belief", content="老师是值得信赖的大人",
                     links=["m0002"])
    # 每个可序列化字段都填一个非空值（哨兵值, 值本身不重要）
    probes = {
        "observer": "老师", "tags": ["x"], "segment_id": "seg-1",
        "event_seq": [1], "ts": "2026-09-01T20:00:00",
        "links": ["m0002"], "contradictions": ["m0003"],
        "narration": "n", "verbatim": "v", "verbatim_seq": ["1.1"],
        "title": "t", "emo_shape": ["smile"], "pattern": "p", "subject": "player",
        "count": 2, "examples": ["e"], "content": "c", "growth": "g",
        "history": [{"episode_id": "m0002", "content": "c", "ts": "t"}],
        "aff_at_encoding": 0.5, "emo_int": 0.5,
        "emo_span": 0.5, "emo_valence": 0.5,
    }
    declared = {f.name for f in _dc_fields(BrainNode)}
    unknown = set(probes) - declared
    assert not unknown, f"探针里有已不存在的字段（删字段时忘了改这里）: {unknown}"
    for k, v in probes.items():
        setattr(node, k, v)

    back = BrainNode.from_dict(node.to_dict())
    lost = [k for k, v in probes.items() if getattr(back, k) != v]
    assert not lost, f"这些字段落库后读不回来: {lost}"

    # 反向: `to_dict` 的清单里不该有"探针没覆盖"的字段（新增字段要一起补）
    serialized = set(node.to_dict())
    undeclared = serialized - set(probes) - {"id", "kind", "significance",
                                            "epistemic"}
    assert not undeclared, (
        f"`to_dict` 会落这些字段, 但探针没覆盖 → 无法确认它们读得回来: {undeclared}"
        "（往探针里补一个非空值）")
    print("    序列化字段: to_dict ⇄ from_dict 三方一致 ✓")


# ---------------------------------------------------------------------------
# aff_at_encoding —— 编码时好感快照（§3.3.3, 2026-09-13）
# ---------------------------------------------------------------------------

def test_aff_at_encoding_roundtrip():
    """★ 0.0（中性）必须真的落库——它不能和"未采集"一起被省略。"""
    node = make_node("episode", narration="那天她只是普通地打了个招呼",
                     aff_at_encoding=0.0)
    assert node.aff_at_encoding == 0.0
    line = node.to_json_line()
    assert '"aff_at_encoding":0.0' in line, f"0.0 中性值被省掉了: {line}"
    back = BrainNode.from_json_line(line)
    assert back.aff_at_encoding == 0.0
    print("    aff_at_encoding: 0.0（中性）落库且往返保真")


def test_aff_at_encoding_none_is_not_zero():
    """★ 未采集(None) 与 中性(0.0) 必须可区分——否则旧档冒充"当时关系中性"。"""
    node = make_node("episode", narration="旧档没有这个字段")
    assert node.aff_at_encoding is None
    assert "aff_at_encoding" not in node.to_dict()
    # 旧档行（无该字段）→ None, 不是 0.0
    old = BrainNode.from_dict({"id": "m0001", "kind": "episode", "narration": "旧"})
    assert old.aff_at_encoding is None
    print("    aff_at_encoding: None（未采集）≠ 0.0（中性）")


def test_aff_at_encoding_clamped_and_bad_to_none():
    assert make_node("episode", narration="x", aff_at_encoding=-1.0).aff_at_encoding == -1.0
    assert make_node("episode", narration="x", aff_at_encoding=1.0).aff_at_encoding == 1.0
    assert make_node("episode", narration="x", aff_at_encoding=-9).aff_at_encoding == -1.0
    assert make_node("episode", narration="x", aff_at_encoding=9).aff_at_encoding == 1.0
    # 坏值 → None（不是 0.0——坏值不等于"中性"）
    for bad in ("abc", None, True, float("nan"), [], {}):
        got = make_node("episode", narration="x", aff_at_encoding=bad).aff_at_encoding
        assert got is None, f"{bad!r} → {got!r}, 应为 None"
    print("    aff_at_encoding: 越界夹紧 + 坏值 → None")


def test_emo_span_roundtrip_and_bounds():
    """emo_span = 情绪摆幅, **声明非负**（是幅度不是方向）。"""
    node = make_node("episode", narration="先炸后真心笑", emo_span=0.9)
    assert node.emo_span == 0.9
    assert '"emo_span":0.9' in node.to_json_line()
    assert BrainNode.from_json_line(node.to_json_line()).emo_span == 0.9
    # 0.0 合法且必须落库
    z = make_node("episode", narration="全程一个调子", emo_span=0.0)
    assert '"emo_span":0.0' in z.to_json_line()
    # 负值夹到 0（非负声明）; 越上界夹到 1
    assert make_node("episode", narration="x", emo_span=-0.5).emo_span == 0.0
    assert make_node("episode", narration="x", emo_span=9).emo_span == 1.0
    # 缺/坏 → None
    assert make_node("episode", narration="x").emo_span is None
    for bad in ("abc", True, float("nan")):
        assert make_node("episode", narration="x", emo_span=bad).emo_span is None
    print("    emo_span: 往返保真 + 非负 + 0.0 落库 + 坏值 None")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_ST = {"year": 1, "month": 4, "week": 2, "phase": "夕", "sim_day": 47}










def test_episode_epistemic_guard():
    node = make_node("episode", narration="x", epistemic="inferred_belief")
    errs = node.validate()
    assert any("episode 节点 epistemic 只能是 observed_fact/reported_fact" in e for e in errs)


# ⏸ `is_seed()` / `source` / `notes` —— 2026-09-21 整族删除。原 `test_seed_episode_rules`
# 随之一并删（它钉的是"出厂基座 = episode(source=experience)"，而那个生产者已归档、
# 出厂记忆自 2026-09-05 起不进 wiki）。epistemic 护栏那一半并入上面的用例。


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


def test_relation_kind_removed():
    """relation kind 已砍（2026-09-02）——构造降级为 episode, 校验报缺 narration。"""
    node = make_node("relation", subject="igusa_haruka", object="sensei",
                     relation="信任加深", note="约定常来陪她", event_seq=[10])
    assert node.kind == "episode"      # 未知 kind 降级
    assert any("narration" in e for e in node.validate())


def test_title_and_history_fields():
    # episode.title 可选
    ep = make_node("episode", narration="公园散步", title="和老师的公园散步")
    assert ep.validate() == []
    assert ep.title == "和老师的公园散步"
    assert ep.main_text == "公园散步"
    # belief.history 改写溯源
    bel = make_node("belief", content="老师会认真听我说话", subject="sensei",
                    epistemic="inferred_belief", links=["m0001"],
                    history=[{"episode_id": "m0001", "content": "初版", "ts": "t1"}])
    assert bel.validate() == []
    assert bel.history[0]["episode_id"] == "m0001"
    # history 只属于 belief
    bad = make_node("episode", narration="x", history=[{"content": "y"}])
    assert any("history" in e for e in bad.validate())
    # main_text 收敛: episode→narration / experience→pattern / belief→content
    exp = make_node("experience", pattern="p", subject="s")
    assert exp.main_text == "p"
    bel = make_node("belief", content="出厂认知", epistemic="inferred_belief",
                    links=["m0001"])
    assert bel.main_text == "出厂认知"


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
