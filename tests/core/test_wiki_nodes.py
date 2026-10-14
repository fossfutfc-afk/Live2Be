"""图式 wiki 节点数据结构测试（AGENT_BRAIN.md §1 / M1）。"""
import json

from core.brain import (
    KINDS,
    PRECIOUS_THRESHOLD,
    BrainNode,
    make_node,
)
from core.brain.nodes import format_id


def test_format_id():
    assert format_id("m", 3) == "m0003"
    assert format_id("c", 2) == "c0002"
    assert format_id("e", 42) == "e0042"


def test_episode_roundtrip():
    node = make_node("episode", text="那天傍晚老师陪我在杂草屋看苔藓",
                     verbatim="「地砖里长出的苔藓也可以是花」",
                     significance=0.8, tags=["老师", "杂草屋"],
                     observer="igusa_haruka", event_seq=[42, 58],
                     ts="2026-09-01T20:00:00")
    assert node.validate() == []
    assert node.is_precious is True
    assert node.dedup_key() == ("episode", (42, 58))
    # jsonl 行往返
    line = node.to_json_line()
    back = BrainNode.from_json_line(line)
    assert back.to_dict() == node.to_dict()
    # 完整 dict 往返（含空字段补齐）
    assert BrainNode.from_dict(node.to_dict()).to_dict() == node.to_dict()


def test_episode_required_text():
    """必填正文（`text`）缺失 → 拒绝。三槽合流后这条是唯一的"必填正文"用例。"""
    node = make_node("episode", verbatim="只有原话没有叙述")
    assert "episode 缺少必填字段: text" in node.validate()


def test_promise_is_no_longer_a_kind(tmp_path=None):
    """⏸ 原 `test_promise_node_needs_outcome_and_enum`（2026-09-29 承诺退图后作废）。

    退役的形状钉在这里:
      · `KINDS` 里没有 `promise`;
      · `PROMISE_OUTCOMES` 不再由节点层导出（结局词表搬去 `notes` —— 那里才是它的家）;
      · `make_node("promise", …)` **降级成 episode**（`from_dict` 对未知 kind 的兜底,
        与旧档兼容同一条路）—— 引擎不会再建出承诺节点;
      · 旧档的 `outcome` 键读不进来、也不抛。
    """
    from core.brain import nodes as N

    assert "promise" not in N.KINDS and "promise" not in N._REQUIRED
    assert not hasattr(N, "PROMISE_OUTCOMES"), "结局词表搬去 notes 了（别在节点层留副本）"

    degraded = make_node("promise", text="周六模型店", outcome="kept")
    assert degraded.kind == "episode"                    # 未知 kind 的兜底
    assert degraded.validate() == []                     # 它现在是一条合法 episode
    assert "outcome" not in degraded.to_dict()           # 那个字段已经不存在

    legacy = BrainNode.from_dict({"id": "p0001", "kind": "promise",
                                  "text": "周六模型店", "outcome": "kept"})
    assert legacy.kind == "episode" and not hasattr(legacy, "outcome")


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

    node = BrainNode(id="m0001", kind="belief", text="老师是值得信赖的大人")
    # 每个可序列化字段都填一个非空值（哨兵值, 值本身不重要）
    # ⚠️ `links`/`contradictions` **不在探针里**（2026-09-21 G3）: 边已搬到
    # `edges.jsonl`, 点表**读得进、写不出** —— 拿它们做往返断言会失败, 那是设计。
    probes = {
        "observer": "老师", "tags": ["x"],
        "event_seq": [1], "ts": "2026-09-01T20:00:00",
        "text": "n", "verbatim": "v", "verbatim_seq": ["1.1"],
        "title": "t", "emo_shape": ["smile"], "text": "p", "subject": "player",
        "text": "c", "growth": "g",
        "aff_at_encoding": 0.5, "emo_int": 0.5,
        "emo_span": 0.5,
    }
    declared = {f.name for f in _dc_fields(BrainNode)}
    unknown = set(probes) - declared
    assert not unknown, f"探针里有已不存在的字段（删字段时忘了改这里）: {unknown}"
    for k, v in probes.items():
        setattr(node, k, v)

    back = BrainNode.from_dict(node.to_dict())
    lost = [k for k, v in probes.items() if getattr(back, k) != v]
    assert not lost, f"这些字段落库后读不回来: {lost}"

    # 那两个已删的键（G4）: 旧档读得进 = **读不出来**（字段没了）, 但也不抛。
    # 真正的自举在**文件格式层**（`graph.infer_edges(rows)`）, 见 `test_wiki_graph.py`。
    assert "links" not in node.to_dict() and "contradictions" not in node.to_dict()
    legacy = BrainNode.from_dict({"id": "m0009", "kind": "belief",
                                  "links": ["m0001"], "contradictions": ["m0002"]})
    assert legacy.id == "m0009" and legacy.validate() != []   # 除旧键外照常解析
    assert not hasattr(legacy, "links") and not hasattr(legacy, "contradictions")

    # 反向: `to_dict` 的清单里不该有"探针没覆盖"的字段（新增字段要一起补）
    serialized = set(node.to_dict())
    undeclared = serialized - set(probes) - {"id", "kind", "significance"}
    assert not undeclared, (
        f"`to_dict` 会落这些字段, 但探针没覆盖 → 无法确认它们读得回来: {undeclared}"
        "（往探针里补一个非空值）")
    print("    序列化字段: to_dict ⇄ from_dict 三方一致 ✓")


# ---------------------------------------------------------------------------
# aff_at_encoding —— 编码时好感快照（§3.3.3, 2026-09-13）
# ---------------------------------------------------------------------------

def test_aff_at_encoding_roundtrip():
    """★ 0.0（中性）必须真的落库——它不能和"未采集"一起被省略。"""
    node = make_node("episode", text="那天她只是普通地打了个招呼",
                     aff_at_encoding=0.0)
    assert node.aff_at_encoding == 0.0
    line = node.to_json_line()
    assert '"aff_at_encoding":0.0' in line, f"0.0 中性值被省掉了: {line}"
    back = BrainNode.from_json_line(line)
    assert back.aff_at_encoding == 0.0
    print("    aff_at_encoding: 0.0（中性）落库且往返保真")


def test_aff_at_encoding_none_is_not_zero():
    """★ 未采集(None) 与 中性(0.0) 必须可区分——否则旧档冒充"当时关系中性"。"""
    node = make_node("episode", text="旧档没有这个字段")
    assert node.aff_at_encoding is None
    assert "aff_at_encoding" not in node.to_dict()
    # 旧档行（无该字段）→ None, 不是 0.0
    old = BrainNode.from_dict({"id": "m0001", "kind": "episode", "text": "旧"})
    assert old.aff_at_encoding is None
    print("    aff_at_encoding: None（未采集）≠ 0.0（中性）")


def test_aff_at_encoding_clamped_and_bad_to_none():
    assert make_node("episode", text="x", aff_at_encoding=-1.0).aff_at_encoding == -1.0
    assert make_node("episode", text="x", aff_at_encoding=1.0).aff_at_encoding == 1.0
    assert make_node("episode", text="x", aff_at_encoding=-9).aff_at_encoding == -1.0
    assert make_node("episode", text="x", aff_at_encoding=9).aff_at_encoding == 1.0
    # 坏值 → None（不是 0.0——坏值不等于"中性"）
    for bad in ("abc", None, True, float("nan"), [], {}):
        got = make_node("episode", text="x", aff_at_encoding=bad).aff_at_encoding
        assert got is None, f"{bad!r} → {got!r}, 应为 None"
    print("    aff_at_encoding: 越界夹紧 + 坏值 → None")


def test_emo_span_roundtrip_and_bounds():
    """emo_span = 情绪摆幅, **声明非负**（是幅度不是方向）。"""
    node = make_node("episode", text="先炸后真心笑", emo_span=0.9)
    assert node.emo_span == 0.9
    assert '"emo_span":0.9' in node.to_json_line()
    assert BrainNode.from_json_line(node.to_json_line()).emo_span == 0.9
    # 0.0 合法且必须落库
    z = make_node("episode", text="全程一个调子", emo_span=0.0)
    assert '"emo_span":0.0' in z.to_json_line()
    # 负值夹到 0（非负声明）; 越上界夹到 1
    assert make_node("episode", text="x", emo_span=-0.5).emo_span == 0.0
    assert make_node("episode", text="x", emo_span=9).emo_span == 1.0
    # 缺/坏 → None
    assert make_node("episode", text="x").emo_span is None
    for bad in ("abc", True, float("nan")):
        assert make_node("episode", text="x", emo_span=bad).emo_span is None
    print("    emo_span: 往返保真 + 非负 + 0.0 落库 + 坏值 None")


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

_ST = {"year": 1, "month": 4, "week": 2, "phase": "夕", "sim_day": 47}










def test_belief_source_guard_uses_observer():
    """⭐ 2026-09-29: 「认知不伪装成事实」那条护栏换成 `observer` 版（`epistemic` 退役）。

    非空 `observer` 的语义 = "这条是**听说的**" ⇒ belief 不许带它
    （否则一条认知会被渲染进「我听说的」那一段）。
    """
    node = make_node("belief", text="x", observer="asagi_mutsuki")
    assert any("belief 不许带 observer" in e for e in node.validate())
    assert make_node("belief", text="老师是第一个不会嫌弃我的人",
                     subject="sensei").validate() == []
    # episode 带 observer = 合法的"听说的"（它就是干这个的）
    assert make_node("episode", text="听阿露说老师昨天没睡好",
                     observer="asagi_mutsuki").validate() == []


# ⏸ `is_seed()` / `source` / `notes` —— 2026-09-21 整族删除。原 `test_seed_episode_rules`
# 随之一并删（它钉的是"出厂基座 = episode(source=experience)"，而那个生产者已归档、
# 出厂记忆自 2026-09-05 起不进 wiki）。来源护栏那一半并入上面的 `observer` 用例。


def test_belief_support_is_not_a_field_concern():
    """`belief 必须有支撑` 2026-09-21（G3）**搬出 `validate()`** —— 支撑住在边表里。

    原用例（`test_belief_requires_support`）钉的是字段级 `links ≥1`; 边搬到
    `edges.jsonl` 后字段校验看不见它。新家两处: 写路径
    （`revise.apply_decisions` 建完节点立刻补 `supports` 边）+ 全局兜底
    （`store.audit()` 的"belief 无支撑"—— `test_wiki_audit.py` 守着）。
    """
    node = make_node("belief", text="老师是第一个不会嫌弃我的人", subject="sensei")
    assert node.validate() == []            # 字段层不再判支撑


def test_profile_kind_is_gone_but_old_rows_still_load():
    """⭐ 2026-10-14: `profile`（玩家画像）**删格式** —— kind 与 `examples` 一起没了。

    两半判据, 缺一不可:
      ① **今天没有这个 kind** —— `KINDS` 里没有它, `make_node("profile")` 于是像任何
         未知 kind 一样**降级成 episode**。⚠️ 这正是 `episodes._create_a_nodes` 那一支
         必须**删干净**、不能只"停产"的原因: 留着它 = 埋一条"画像被静默写成经历"的路。
      ② **老档照样读得进、不炸** —— 那一行的 `text`/`subject` 还在（`subject` 字段
         留着, 今天的读者是 belief）, 而 `examples` 键**静默忽略**（字段没了, 不是
         "清空"⇒ 旧档不会因为多一个键而变脏）。
    """
    assert "profile" not in KINDS
    old = BrainNode.from_dict({"id": "e0001", "kind": "profile", "text": "摸鱼",
                               "subject": "sensei", "examples": ["「今天也摸鱼」"],
                               "significance": 0.75})
    assert old.kind == "episode" and old.text == "摸鱼"
    assert old.subject == "sensei"                  # `subject` 留着（belief 的主题句）
    assert not hasattr(old, "examples")             # 字段本身删了
    assert make_node("profile", text="p", subject="s").kind == "episode"


def test_relation_kind_removed():
    """relation kind 已砍（2026-09-02）——构造降级为 episode, 校验报缺 text。"""
    node = make_node("relation", subject="igusa_haruka", object="sensei",
                     relation="信任加深", note="约定常来陪她", event_seq=[10])
    assert node.kind == "episode"      # 未知 kind 降级
    assert any("text" in e for e in node.validate())


def test_title_and_text_are_shared_by_all_kinds():
    """`title` 只在 episode 上；`text` 是三种 kind **共用**的那一槽。

    原用例（`test_title_and_main_text_fields`）钉的是 `main_text` 的
    "episode→narration / experience→pattern / belief→content"分派——
    三槽合流后那层分派连同 `main_text` 一起删了, 所以这里只剩两件事:
    标题是 episode 的, 正文三个 kind 都读同一个字段。
    """
    ep = make_node("episode", text="公园散步", title="和老师的公园散步")
    assert ep.validate() == []
    assert ep.title == "和老师的公园散步" and ep.text == "公园散步"
    exp = make_node("profile", text="p", subject="s")
    bel = make_node("belief", text="出厂认知",
                    links=["m0001"])
    assert (ep.text, exp.text, bel.text) == ("公园散步", "p", "出厂认知")


# ⏸ `test_count_is_derived_not_stored` —— 2026-09-21（G3）**删**: `count` 这个派生属性
# 本身没了（它原是 `len(links)`, 而 `links` 已停止写入 ⇒ 留着只会恒返回 0）。
# 次数的新家 = `supports` **入边数**（`render._count_of(node, graph)`），由
# `test_wiki_render.py` 的角色视图用例守着（"老师的事（count N）"）。


def test_significance_clamp_and_precious():
    assert BrainNode.from_dict({"significance": 3.0}).significance == 1.0
    assert BrainNode.from_dict({"significance": -1}).significance == 0.0
    assert BrainNode.from_dict({"significance": "垃圾"}).significance == 0.5
    node = make_node("episode", text="x", significance=PRECIOUS_THRESHOLD)
    assert node.is_precious is True
    node2 = make_node("episode", text="x", significance=0.79)
    assert node2.is_precious is False


def test_loose_from_dict_bad_kind_and_legacy_epistemic():
    """坏 kind 降级; ⏸ 旧档的 `epistemic` 键**读不进来也不报错**（2026-09-29 退役）。"""
    node = BrainNode.from_dict({"id": "m0001", "kind": "whatever",
                                "epistemic": "reported_fact", "observer": "阿露"})
    assert node.kind == "episode"      # 坏 kind 降级
    assert not hasattr(node, "epistemic")
    assert node.observer == "阿露"      # 来源信息不丢（它本来就落在 observer 里）
    assert node.validate()             # 校验会报未知 kind 错误
    assert BrainNode.from_dict(None).id == ""
    assert BrainNode.from_dict("junk") .kind == "episode"


def test_json_line_bad_input():
    assert BrainNode.from_json_line("{bad json").id == ""
    line = json.dumps({"id": "m0002", "kind": "belief", "text": "老师会记得",
                       "subject": "sensei", "significance": 0.75},
                      ensure_ascii=False)
    node = BrainNode.from_json_line(line)
    assert node.kind == "belief" and node.text == "老师会记得"
    assert node.subject == "sensei"
