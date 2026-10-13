"""`revise.py` 三趟执行器的落地测试（AGENT_BRAIN.md §5 / M2b）。

覆盖: L1 判关系（`apply_relations`）· L2 造认知（`apply_cognitions`）·
R3 认人（`apply_entities`）· 引用 → `about` 边（`link_entity_refs`）。

⏸ v1 的**万能修订包执行器** `apply_revision_package`（`create`/`update`/`merge`/
`link`/`unlink`/`contradict`/`resolve`/`accrue` 一张大动作表）连同它的 11 条用例
已于 2026-10-12 删除：它的能力被**拆成上面三趟**顶掉了（见 `revise.py` 模块
docstring）。死掉的不是"能力", 是那个**装在同一个函数里的箱子**。
"""
import pytest

from core.brain import WikiStoreV2, make_node
from core.brain.entities import ensure_entities
from core.brain.evolution import EvolutionLog
from core.brain.revise import (
    apply_cognitions,
    apply_entities,
    link_entity_refs,
)


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    # 固定子图: m0001 episode(拆炸弹) + m0002 belief(信任) + m0003 episode(天台) + m0004 belief(旧结论)
    st.add(make_node("episode", text="拆炸弹初遇", event_seq=[1], ts="2026-08-01T00:00:00"))
    st.add(make_node("belief", text="老师是第一个不会嫌弃我的人", subject="sensei",
                     significance=0.9, event_seq=[1]))
    st.add(make_node("episode", text="天台夜谈", event_seq=[2], ts="2026-08-02T00:00:00"))
    # 第 4 条是**另一条看法**: `contradicts` 在真机上两端都是"认知本地号"（看法 ↔ 看法）,
    # ⛔ 不是"看法 ↔ 画像" —— 后者只是 `_COGNITION` 表恰好也认, 不是真实形状。
    st.add(make_node("belief", text="我这样的人不该麻烦别人", subject="sensei",
                     significance=0.6, event_seq=[2]))
    # 真实流程同款: **显式 rel** 走边表（旧的无向 shim `add_link` 已删 —— 它只会靠
    # kind 猜 rel, 而"这两条挨着"本来就不是作者说过的话）。
    st.add_edge("supports", "m0001", "m0002")
    st.add_edge("supports", "m0003", "m0002")
    st.add_edge("supports", "m0003", "m0004")
    return st


def _log(st) -> EvolutionLog:
    return EvolutionLog.for_store(st)


# ============================================================================
# 板块 4b: L2 造认知 + R3 认人
# ============================================================================

def _ctx_kw():
    """执行器的引擎字段（`apply_cognitions` 的 ts/event_seq）。"""
    return {"ts": "2026-09-02T12:00:00", "event_seq": [3]}


def _episode(st, text="老师请我吃甜品"):
    """决策行引用的 episode 已由 Round A 建好（本测试直接预置）。"""
    st.add(make_node("episode", text=text, event_seq=[3],
                     ts="2026-09-02T12:00:00"))

def test_apply_cognitions_birth_edges_have_the_right_direction(tmp_path):
    """⭐ P9: 造看法 = 节点 + **出生自带的三条边**, 方向由两端类型定死。

    `supports`（**经历 → 新看法**）· `evolved_from`（**新看法 → 旧看法**）·
    `contradicts`（对称 —— 写哪边都一样）。
    ⚠️ 两套 id 空间（同 L1）: `supports` 收**经历真身**（`m…`）;
    `evolved_from` / `contradicts` 收**认知本地号**（`u…`）⇒ 过 `id_map` 翻真身。
    """
    st = _store(tmp_path)
    st.save()
    old_belief = "m0002"                                   # 已有的看法
    res = apply_cognitions(st, [{
        "action": "belief", "text": "老师会把我说的话记在心上", "subject": "sensei",
        "significance": 0.7,
        "supports": ["m0001", "m0003"],                    # 两条经历
        "evolved_from": "u0007",                           # 本地号 → m0002
        "contradicts": ["u0008"],                          # 本地号 → m0004
    }], id_map={"u0007": old_belief, "u0008": "m0004"},
        event_seq=[2], ts="2026-10-08T21:00:00+08:00")

    assert len(res.created) == 1 and not res.reused
    new = res.created[0]
    g = st.graph()
    # ⚠️ fixture 自己已经连过几条（`_store` 的 `add_edge`）⇒ 判据按**新节点**数, 不按总数
    assert new in g.targets("m0001", "supports"), "经历 → 新看法"
    assert new in g.targets("m0003", "supports"), "经历 → 新看法"
    assert g.targets(new, "evolved_from") == [old_belief], "新看法 → 旧看法"
    assert new in g.neighbors("m0004"), "contradicts 是对称边"
    assert [e.rel for e in g.edges if new in (e.src, e.dst)].count("supports") == 2
    node = st.get(new)
    assert node.kind == "belief" and node.subject == "sensei"
    assert node.significance == 0.7 and node.event_seq == [2]
    assert node.ts == "2026-10-08T21:00:00+08:00"
    # 账: create 一条 + relate 四条（2 supports + 1 evolved_from + 1 contradicts）
    acts = [e["action"] for e in _log(st).read()]
    assert acts == ["create", "relate", "relate", "relate", "relate"], acts


def test_apply_cognitions_is_idempotent_within_the_same_segment(tmp_path):
    """⭐ P9 幂等: 同一段（`event_seq` 相交）**正文又一样** ⇒ **复用**旧节点, 不双写。

    这是**崩溃窗口重跑**那条路（落盘成功但水位没推进 ⇒ 整段重跑）——
    判据与实现都走 `_find_duplicate`（与 R1 的 episode 同一个）。
    ⚠️ 正文**不同** ⇒ 那是另一条结论, 照造（先例的判据里就带着"主文本相同"）。
    """
    st = _store(tmp_path)
    st.save()
    row = {"action": "belief", "text": "老师会把我说的话记在心上",
           "supports": ["m0001"]}
    kw = dict(event_seq=[2], ts="2026-10-08T21:00:00+08:00")
    first = apply_cognitions(st, [dict(row)], **kw)
    n_before = len([n for n in st.all() if n.kind == "belief"])

    again = apply_cognitions(st, [dict(row)], **kw)
    assert again.created == [] and again.reused == first.created, again
    assert len([n for n in st.all() if n.kind == "belief"]) == n_before, "不得双写"
    assert [e for e in st.graph().edges
            if e.rel == "supports" and e.dst == first.created[0]], "边也不重复"
    assert len([e for e in st.graph().edges
                if e.rel == "supports" and e.dst == first.created[0]]) == 1

    other = apply_cognitions(st, [dict(row, text="换了一个说法")], **kw)
    assert len(other.created) == 1, "正文不同 ⇒ 另一条结论（先例的判据如此）"


def test_apply_cognitions_soak_rewrites_and_leaves_a_trail(tmp_path):
    """⭐ P9 覆写沉淀: 改正文 + **留痕**（`changed.text = [旧, 新]`）; ⛔ 名字与 ts 不动。

    一字未变 ⇒ **不写盘、不留账**（避免"每段都记一次没变的事"）。
    """
    st = _store(tmp_path)
    gid = st.add(make_node("experience", title="和老师吃饭送团子",
                           ts="2026-09-20T10:00:00+08:00"))
    st.save()
    entry = {"action": "experience", "group": gid, "text": "和老师吃饭的时候，我总先说自己不值得。"}

    res = apply_cognitions(st, [dict(entry)], ts="2026-10-08T21:00:00+08:00")
    assert res.soaked == [gid]
    node = st.get(gid)
    assert node.text == entry["text"]
    assert node.title == "和老师吃饭送团子", "⛔ 名字是地址, 这一趟不许动"
    assert node.ts == "2026-09-20T10:00:00+08:00", "⛔ ts 是'这一类事'的时间, 不是改写时间"
    last = _log(st).read()[-1]
    assert last["action"] == "rewrite" and last["id"] == gid
    assert last["changed"]["text"] == ["", entry["text"]], last

    # 一字未变 ⇒ **照记一笔**, 但 `changed` 为空（口径写在 `_soak` 的 docstring:
    # "崩溃窗口重跑落在日志里就是一个空 dict, 一眼可判这次没改任何东西"）
    n_entries = len(_log(st).read())
    res2 = apply_cognitions(st, [dict(entry)], ts="2026-10-09T21:00:00+08:00")
    assert res2.soaked == [], "没真改 ⇒ 不算覆写"
    entries = _log(st).read()
    assert len(entries) == n_entries + 1 and entries[-1]["changed"] == {}, entries[-1]

    # 要写的类不存在 ⇒ **抛**（执行器不吞错; 回滚是编排层的事）
    with pytest.raises(ValueError, match="类不存在"):
        apply_cognitions(st, [{"action": "experience", "group": "g0099", "text": "x"}])


def test_apply_cognitions_keeps_its_hands_off_everything_else(tmp_path):
    """⭐ P9: 这一趟**只做三件事** —— 不改已有正文、不建类、不删任何东西。"""
    st = _store(tmp_path)
    st.save()
    nodes_before = {n.id: n.text for n in st.all()}
    edges_before = len(st.graph().edges)
    apply_cognitions(st, [{"action": "belief", "text": "一条新结论",
                           "supports": ["m0001"]}],
                     event_seq=[2], ts="2026-10-08T21:00:00+08:00")
    after = {n.id: n.text for n in st.all()}
    assert all(after[k] == v for k, v in nodes_before.items()), "已有节点一个字都不许改"
    assert len(st.graph().edges) == edges_before + 1, "只多了那一条证据边"
    assert [n.id for n in st.all() if n.kind == "experience"] == [], "⛔ 不建类"


# ---------------------------------------------------------------------------
# E4（2026-10-08）—— R3 的执行器: **只认人**（`apply_entities`）+ 落边的唯一实现
# ---------------------------------------------------------------------------

def test_apply_entities_creates_and_refuses_duplicates(tmp_path):
    """⭐ 建对象: `name` + `aliases` 落成 `entity`; **重名不重复建**（留痕 `new_entity.dup`）。"""
    st = _store(tmp_path)
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",),
                    sensei_name="老师", sensei_aliases=("sensei",))
    st.save()
    made = apply_entities(st, [{"name": "小玉", "aliases": ["tama"], "reason": "第一次出场"}],
                          ts="2026-10-08T21:00:00+08:00", event_seq=[3])
    assert len(made) == 1 and st.get(made[0]).name == "小玉"
    assert st.get(made[0]).aliases == ["tama"] and st.get(made[0]).event_seq == [3]
    again = apply_entities(st, [{"name": "小玉", "reason": "又提了一次"}],
                           ts="2026-10-08T21:10:00+08:00")
    assert again == [], "同名不该再建一个"
    kinds = [e["action"] for e in EvolutionLog.for_store(st).read()]
    assert kinds == ["new_entity", "new_entity.dup"], kinds
    print(f"    建对象: {made} · 重名跳过（账里有 dup）")


def test_apply_entities_needs_a_reason(tmp_path):
    """`reason` 是**准入门槛**（建对象是永久成本）—— 契约层已挡, 执行层再挡一次。"""
    st = _store(tmp_path)
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",),
                    sensei_name="老师", sensei_aliases=("sensei",))
    st.save()
    try:
        apply_entities(st, [{"name": "小玉"}], ts="2026-10-08T21:00:00+08:00")
    except ValueError as e:
        assert "理由" in str(e), e
    else:
        raise AssertionError("没给 reason 也建出来了")


def test_link_entity_refs_lands_edges_and_normalizes(tmp_path):
    """⭐ **落边的唯一实现**: 节点 `entity` 里的引用 ⇒ `about` + 引用归一成主名。"""
    st = _store(tmp_path)
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",),
                    sensei_name="老师", sensei_aliases=("sensei",))
    st.save()
    nid = st.add(make_node("episode", text="老师约我去公园", title="公园",
                           tags=["公园"], entity=["sensei"],
                           ts="2026-10-08T10:00:00+08:00", event_seq=[3]))
    targets, strangers = link_entity_refs(st, nid, ts="2026-10-08T21:00:00+08:00")
    assert targets == ["x0001"] and strangers == [], (targets, strangers)
    assert st.graph().targets(nid, "about") == ["x0001"]
    assert st.get(nid).entity == ["老师"], st.get(nid).entity
    assert st.get(nid).tags == ["公园"], "tags 一个字都不该被碰"
    # 幂等: 再跑一遍不变、不重复落边
    link_entity_refs(st, nid, ts="2026-10-08T21:00:00+08:00")
    assert len(st.graph().targets(nid, "about")) == 1
    # 陌生人: 原样留着 + 报上来 + 不落边
    nid2 = st.add(make_node("episode", text="第一次见到小玉", title="相遇",
                            entity=["小玉"], ts="2026-10-08T11:00:00+08:00"))
    t2, s2 = link_entity_refs(st, nid2)
    assert t2 == [] and s2 == ["小玉"], (t2, s2)
    assert st.get(nid2).entity == ["小玉"]
    print("    落边: 归一 + 幂等 + 陌生人留档 ✓")
