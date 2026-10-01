# -*- coding: utf-8 -*-
"""L2-a 分群（N7, 2026-09-29）—— 引擎切块 → 一轮起名 → 群节点 + `member_of` 边。

钉六件事:
    ① **切块是引擎的**: `akin` 连通块（≥2 条）成块, 落单的不进料, **已归群的出局**;
    ② **一轮起名**: `new` 建群 + 挂成员; `attach` 挂到已有的类（名字解析印剥同源）;
    ③ ⭐ **同名即并**（`new` 撞已有类名 ⇒ 挂过去, **不建新群、不加数字**）;
    ④ **覆盖是硬要求**: 漏一个块 ⇒ 整包拒（带反馈重试一次）;
    ⑤ ⭐ **失败不连累整段**: 分群这一步失败 ⇒ **只回滚它自己**, R1–R4 的活照常提交;
    ⑥ **没有块 ⇒ 0 次调用**（这一步只在"她连出来的块"上花钱）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain.wiki_v2 import WikiStoreV2, make_node
from core.brain.wiki_v2 import groups
from core.brain.wiki_v2.digest import digest_segment
from core.brain.wiki_v2.entities import ensure_entities
from core.brain.wiki_v2.graph import REL_AKIN, REL_MEMBER_OF
from core.session import make_event
from llm import task_labels as T

ROOT = Path(__file__).resolve().parent.parent.parent
CHAR = "c"

_NOW = "2026-09-29T20:00:00"


class RoundLLM:
    """五轮可控: A / close / B / attr / group（不关心哪轮的给空包）。"""

    def __init__(self, a=None, close=None, b=None, attr=None, group=None):
        self.a = {"episodes": []} if a is None else a
        self.close = {"add": [], "close": []} if close is None else close
        self.b = {"decisions": [], "evidence": [], "affection_exp_delta": 0} if b is None else b
        self.attr = {"attributions": []} if attr is None else attr
        self.group = ({"attach": [], "new": [], "merge": []} if group is None else group)
        self.calls: list[list[dict]] = []
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        task = kw.get("task")
        self.tasks.append(task)
        return {T.DIGEST_A: self.a, T.DIGEST_CLOSE: self.close,
                T.DIGEST_B: self.b, T.DIGEST: self.b,
                T.DIGEST_ATTR: self.attr, T.DIGEST_GROUP: self.group}[task]

    def user_of(self, task):
        """第一次该 task 调用的 user 消息（分群的料就在里面）。"""
        idx = self.tasks.index(task)
        return self.calls[idx][-1]["content"]


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    ensure_entities(st, char_name="伊草 遥香", sensei_name="老师")
    st.save()
    return st


def _ep(st, text, title, ts):
    return st.add(make_node("episode", text=text, title=title, ts=ts, event_seq=[3]))


def _mmt(seq, reply="嗯"):
    e = make_event("mmt", "chat", {"player": "老师", "reply": reply})
    e.seq = seq
    e.ts = _NOW
    return e


# ---------------------------------------------------------------------------
# ① 切块（0 LLM）
# ---------------------------------------------------------------------------

def test_blocks_are_akin_components(tmp_path):
    """`akin` 连通块成块（≥2 条, 按 ts 升序）; 落单的**不进块也不进料**。"""
    st = _store(tmp_path)
    a = _ep(st, "放学后又去了杂草屋", "今天的杂草屋", "2026-09-20T10:00:00")
    b = _ep(st, "给那盆苔藓浇了水", "给苔藓浇水", "2026-09-22T10:00:00")
    c = _ep(st, "天台上也有苔藓", "天台上的苔藓", "2026-09-25T10:00:00")
    lone = _ep(st, "在走廊上撞见她", "走廊上的模型盒", "2026-09-26T10:00:00")
    st.add_edge(REL_AKIN, c, a, ts="2026-09-25T10:00:00")          # 乱序连, 切块要自己排
    st.add_edge(REL_AKIN, a, b, ts="2026-09-22T10:00:00")
    st.save()

    assert groups.ungrouped(st) == [a, b, c, lone]                 # ts 升序
    blks = groups.build_blocks(st, groups.ungrouped(st))
    assert len(blks) == 1, blks
    assert blks[0].bid == "b1"
    assert list(blks[0].episodes) == [a, b, c]                     # 升序（不是连边的顺序）
    assert lone not in blks[0].episodes                            # 落单的被排除

    text = groups.render_blocks(st, blks)
    assert text.splitlines()[0] == "〔b1｜3 条〕", text
    assert f"- 〔{a}｜《今天的杂草屋》〕放学后又去了杂草屋" in text
    print(f"    切块: {len(blks)} 块 / {len(blks[0].episodes)} 条; 落单的没进料")


def test_grouped_and_capped(tmp_path):
    """已归群的出局（增量）; 超过 `max_blocks` 的块留着下段再说。"""
    st = _store(tmp_path)
    pairs = []
    for i in range(3):
        x = _ep(st, f"事 {i}A", f"甲{i}", f"2026-09-1{i}T10:00:00")
        y = _ep(st, f"事 {i}B", f"乙{i}", f"2026-09-1{i}T11:00:00")
        st.add_edge(REL_AKIN, x, y, ts="2026-09-25T10:00:00")
        pairs.append((x, y))
    st.save()
    blks = groups.build_blocks(st, groups.ungrouped(st))
    assert len(blks) == 3, blks
    assert len(groups.build_blocks(st, groups.ungrouped(st), max_blocks=1)) == 1

    # 归掉第一对（块按"最新成员"排, 所以先找到**装着它**的那个块, 别假设它是 b1）
    target = next(b for b in blks if b.episodes == tuple(pairs[0]))
    groups.apply_groups(st, [{"action": "new", "block": target.bid, "title": "甲类"}],
                        blks, ts=_NOW)
    st.save()
    left_ids = groups.ungrouped(st)
    assert pairs[0][0] not in left_ids and pairs[0][1] not in left_ids
    assert len(groups.build_blocks(st, left_ids)) == 2
    print("    出局: 归过群的真的不再进料; 上限外的块留着")


# ---------------------------------------------------------------------------
# ②③ 执行器（世界校验: 只剔不拒）
# ---------------------------------------------------------------------------

def test_apply_new_and_attach(tmp_path):
    """`new` 建群 + 挂成员; `attach` 挂到已有的类（不建新群）。"""
    st = _store(tmp_path)
    a = _ep(st, "A", "甲", "2026-09-20T10:00:00")
    b = _ep(st, "B", "乙", "2026-09-21T10:00:00")
    c = _ep(st, "C", "丙", "2026-09-22T10:00:00")
    d = _ep(st, "D", "丁", "2026-09-23T10:00:00")
    st.add_edge(REL_AKIN, a, b, ts="2026-09-21T10:00:00")
    st.add_edge(REL_AKIN, c, d, ts="2026-09-23T10:00:00")
    st.save()
    blks = groups.build_blocks(st, groups.ungrouped(st))
    assert [x.bid for x in blks] == ["b1", "b2"]
    assert list(blks[0].episodes) == [c, d]                        # ⭐ 新的块先发（b1 = 后连的那块）

    res = groups.apply_groups(st, [{"action": "new", "block": "b1", "title": "那片苔藓"}],
                              blks, ts=_NOW)
    assert len(res.nodes) == 1 and res.grouped == [c, d] and res.edges == 2
    gid = res.nodes[0]
    node = st.get(gid)
    assert node.kind == "group" and node.title == "那片苔藓" and gid.startswith("g")

    blks2 = groups.build_blocks(st, groups.ungrouped(st))
    assert [x.bid for x in blks2] == ["b1"] and list(blks2[0].episodes) == [a, b]
    res2 = groups.apply_groups(st, [{"action": "attach", "block": "b1", "group": "那片苔藓"}],
                               blks2, ts=_NOW)
    assert res2.nodes == []                                        # 没建新群
    g = st.graph()
    assert sorted(g.sources(gid, REL_MEMBER_OF)) == sorted([a, b, c, d])
    print(f"    new+attach: 群 {gid} 收了 4 条; attach 没建新群")


def test_same_name_merges_into_existing(tmp_path):
    """⭐ 同名即并: `new` 的名字撞上已有的类 ⇒ 挂过去, **不建新群、不加数字**。"""
    st = _store(tmp_path)
    a = _ep(st, "A", "甲", "2026-09-20T10:00:00")
    b = _ep(st, "B", "乙", "2026-09-21T10:00:00")
    c = _ep(st, "C", "丙", "2026-09-22T10:00:00")
    d = _ep(st, "D", "丁", "2026-09-23T10:00:00")
    st.add_edge(REL_AKIN, a, b, ts="2026-09-21T10:00:00")
    st.add_edge(REL_AKIN, c, d, ts="2026-09-23T10:00:00")
    st.save()
    first = groups.build_blocks(st, groups.ungrouped(st))
    gid = groups.apply_groups(st, [{"action": "new", "block": "b1", "title": "那片苔藓"}],
                              first, ts=_NOW).nodes[0]
    st.save()

    second = groups.build_blocks(st, groups.ungrouped(st))
    res = groups.apply_groups(st, [{"action": "new", "block": "b1", "title": "《那片苔藓》"}],
                              second, ts=_NOW)
    assert res.nodes == [], res.nodes                              # ⭐ 没建第二个群
    assert any("同名" in w for w in res.warnings), res.warnings
    assert [n.id for n in st.all() if n.kind == "group"] == [gid]
    assert sorted(st.graph().sources(gid, REL_MEMBER_OF)) == sorted([a, b, c, d])
    print(f"    同名即并: 第二个同名 new 被并进 {gid}（连书名号一起抄也认）")


def test_unknown_name_and_empty_title_drop_row(tmp_path):
    """类名找不到 / 新名字是空的 ⇒ **只记账、丢这一行**（那个块留着, 下段再来）。"""
    st = _store(tmp_path)
    a = _ep(st, "A", "甲", "2026-09-20T10:00:00")
    b = _ep(st, "B", "乙", "2026-09-21T10:00:00")
    st.add_edge(REL_AKIN, a, b, ts="2026-09-21T10:00:00")
    st.save()
    blks = groups.build_blocks(st, groups.ungrouped(st))
    res = groups.apply_groups(st, [{"action": "attach", "block": "b1", "group": "并不存在的类"}],
                              blks, ts=_NOW)
    assert res.nodes == [] and res.edges == 0 and res.grouped == []
    assert any("没找到" in w for w in res.warnings), res.warnings
    assert groups.ungrouped(st) == [a, b]                          # 一件事都没丢
    print("    世界校验: 找不到的类名只丢那一行, 块留到下段")


# ---------------------------------------------------------------------------
# ④⑤⑥ 接线（digest_segment 里的那一步）
# ---------------------------------------------------------------------------

def _seed_pair(st):
    """预先摆一对"她连过的"事 —— 分群的料就靠它（`akin` 是她的发现, 这里直接造）。"""
    a = _ep(st, "放学后又去了杂草屋", "今天的杂草屋", "2026-09-20T10:00:00")
    b = _ep(st, "给那盆苔藓浇了水", "给苔藓浇水", "2026-09-22T10:00:00")
    st.add_edge(REL_AKIN, a, b, ts="2026-09-22T10:00:00")
    st.save()
    return a, b


def test_digest_runs_group_round(tmp_path):
    """接上了: 有块 ⇒ 发一次 `digest.group`; 料里有块头, 产出落群节点 + 边。"""
    st = _store(tmp_path)
    a, b = _seed_pair(st)
    llm = RoundLLM(group={"attach": [], "new": [{"block": "b1", "title": "那片苔藓"}],
                          "merge": []})
    res = digest_segment(st, llm, [_mmt(3)])
    assert res.ok, res.errors
    assert T.DIGEST_GROUP in llm.tasks, llm.tasks
    assert llm.user_of(T.DIGEST_GROUP).startswith("【还没归类的块】")
    assert "〔b1｜2 条〕" in llm.user_of(T.DIGEST_GROUP)
    assert "（还没有任何类 —— 全部走 new）" in llm.user_of(T.DIGEST_GROUP)
    assert len(res.created_groups) == 1 and res.grouped_episodes == 2
    gid = res.created_groups[0]
    assert sorted(st.graph().sources(gid, REL_MEMBER_OF)) == sorted([a, b])
    print(f"    digest 接线: {res.created_groups} 群; 挂上 {res.grouped_episodes} 条")


def test_no_blocks_no_call(tmp_path):
    """没有未归群的块 ⇒ **0 次调用**（这一步不为空料付钱）。"""
    st = _store(tmp_path)
    _ep(st, "独自一件事", "孤零零", "2026-09-20T10:00:00")
    st.save()
    llm = RoundLLM()
    res = digest_segment(st, llm, [_mmt(3)])
    assert res.ok, res.errors
    assert T.DIGEST_GROUP not in llm.tasks, llm.tasks
    print("    0 调用: 没有块就一次都不发")


def test_group_failure_does_not_rollback_the_batch(tmp_path):
    """⭐ 分群失败 ⇒ 只回滚这一步: episode 照常落, `errors` 干净, 记账进 `group_warnings`。"""
    st = _store(tmp_path)
    _seed_pair(st)                                                # m0001 / m0002
    llm = RoundLLM(a={"episodes": [{"text": "今天在图书室待了很久", "title": "图书室的下午",
                                   "tags": ["日常"]}]},
                   b={"decisions": [{"episode": "m0003", "decision": "add",
                                     "kind": "belief", "subject": "sensei",
                                     "text": "在图书室待着也安心"}],
                      "evidence": [], "affection_exp_delta": 0},
                   group={"attach": [], "new": [], "merge": []})  # 漏块 ⇒ 拒 ⇒ 重试 ⇒ 仍漏
    res = digest_segment(st, llm, [_mmt(3)])
    assert res.ok, res.errors                                     # ⭐ 整段没被连累
    assert res.errors == [], res.errors
    assert res.created, res.created                               # R1 的 episode 落住了
    assert res.created_groups == [] and res.grouped_episodes == 0
    assert any("没有归属" in w for w in res.group_warnings), res.group_warnings
    assert llm.tasks.count(T.DIGEST_GROUP) == 2                   # 打回一次（feedback 重试）
    assert [n.kind for n in st.all() if n.kind == "group"] == []  # 一个群都没留下
    print(f"    失败隔离: 打回 {llm.tasks.count(T.DIGEST_GROUP)} 次后放弃, 整段照常提交")


# ---------------------------------------------------------------------------
# N7b 并群（merge）
# ---------------------------------------------------------------------------

def _two_groups(st):
    """摆出**两个本该是一个的类**: 各自两条同类, 然后**她跨类连了一条**（下一段才看得到）。

    返回 `(g1, g2, 跨类那两端的 episode)`。顺序就是真机里的顺序:
    先各自成类, 之后她才把两边连起来。
    """
    a = _ep(st, "A", "甲一", "2026-09-20T10:00:00")
    b = _ep(st, "B", "甲二", "2026-09-21T10:00:00")
    c = _ep(st, "C", "乙一", "2026-09-22T10:00:00")
    d = _ep(st, "D", "乙二", "2026-09-23T10:00:00")
    st.add_edge(REL_AKIN, a, b, ts="2026-09-21T10:00:00")
    st.add_edge(REL_AKIN, c, d, ts="2026-09-23T10:00:00")
    st.save()
    blks = groups.build_blocks(st, groups.ungrouped(st))
    res = groups.apply_groups(st, [
        {"action": "new", "block": blks[0].bid, "title": "甲类"},
        {"action": "new", "block": blks[1].bid, "title": "乙类"},
    ], blks, ts=_NOW)
    st.save()
    g = {st.get(n).title: n for n in res.nodes}
    st.add_edge(REL_AKIN, b, c, ts="2026-09-24T10:00:00")     # ⭐ 跨类的那条
    st.save()
    return g["甲类"], g["乙类"], b, c


def test_merge_candidates_from_crossing_akin(tmp_path):
    """⭐ 候选判据 = **跨群的 `akin` 边**; 同群内部的边不算。"""
    st = _store(tmp_path)
    g1, g2, b, c = _two_groups(st)
    cands = groups.merge_candidates(st)
    assert len(cands) == 1, cands
    one = cands[0]
    assert {one.left, one.right} == {g1, g2}
    assert sorted(one.pairs) == sorted([(b, c)])

    text = groups.render_merge_candidates(st, cands)
    assert text.startswith("1. 〔《甲类》｜2 条〕 与 〔《乙类》｜2 条〕 —— 她把这 1 对连过"), text
    assert f"- 〔{b}｜《甲二》〕" in text and f"- 〔{c}｜《乙一》〕" in text
    print(f"    候选: {len(cands)} 对（跨类的那条 akin 提的）")


def test_apply_merge_remaps_edges_and_retires_loser(tmp_path):
    """并群 = **端点 remap（`ts` 原样）+ 删输家 + 旧名进 `aliases`**。"""
    st = _store(tmp_path)
    g1, g2, _b, _c = _two_groups(st)
    before = {e.src: e.ts for e in st.edges()
              if e.rel == REL_MEMBER_OF and e.dst == g1}
    assert len(before) == 2
    cands = groups.merge_candidates(st)
    res = groups.apply_merges(st, [{"action": "merge", "from": "甲类", "into": "乙类"}],
                              cands, ts=_NOW)
    assert res.merged == [(g1, g2)] and res.moved == 2 and res.warnings == [], res
    assert st.get(g1) is None                                     # 输家没了
    g = st.graph()
    assert len(g.sources(g2, REL_MEMBER_OF)) == 4                 # 四条成员都在赢家名下
    after = {e.src: e.ts for e in st.edges()
             if e.rel == REL_MEMBER_OF and e.dst == g2}
    for src, ts in before.items():                                # ⭐ ts 原样（不是"现在"）
        assert after[src] == ts, (src, ts, after[src])
    assert st.get(g2).aliases == ["甲类"]                         # 旧名留住了
    assert groups.merge_candidates(st) == []                      # ⭐ 并完自清（下次不再问）
    print(f"    并群: {g1}(甲类) → {g2}(乙类), 搬了 {res.moved} 条边, ts 未动")


def test_merge_outside_candidates_is_dropped(tmp_path):
    """⚠️ 只并**引擎提过的那些对** —— 契约层管不到（名字要归一）, 所以闸在这里。"""
    st = _store(tmp_path)
    g1, g2, _b, _c = _two_groups(st)
    res = groups.apply_merges(st, [{"action": "merge", "from": "甲类", "into": "乙类"}],
                              [], ts=_NOW)                        # 候选是空的
    assert res.merged == [] and res.moved == 0
    assert any("不在本轮候选" in w for w in res.warnings), res.warnings
    assert st.get(g1) is not None and st.get(g2) is not None      # 一个都没动
    print("    闭集: 没提过的对不并（一个都没动）")


def test_digest_runs_merge(tmp_path):
    """接上了: 有候选 ⇒ 那一轮里能并; 结果进 `merged_groups`。"""
    st = _store(tmp_path)
    g1, g2, _b, _c = _two_groups(st)
    llm = RoundLLM(group={"attach": [], "new": [],
                          "merge": [{"from": "甲类", "into": "乙类"}]})
    res = digest_segment(st, llm, [_mmt(3)])
    assert res.ok, res.errors
    assert res.merged_groups == [(g1, g2)], res.merged_groups
    assert st.get(g1) is None and st.get(g2) is not None
    assert "【可能重复的类】" in llm.user_of(T.DIGEST_GROUP)
    print(f"    digest 接线: 并掉 {res.merged_groups}（料里出现了【可能重复的类】）")


# ---------------------------------------------------------------------------
# N7c 单条也能归已有的类
# ---------------------------------------------------------------------------

def _group_of_two(st):
    """先摆一个**已有的类**（两条）, 返回 `(群 id, 已归群的成员)`。"""
    a = _ep(st, "A", "甲一", "2026-09-20T10:00:00")
    b = _ep(st, "B", "甲二", "2026-09-21T10:00:00")
    st.add_edge(REL_AKIN, a, b, ts="2026-09-21T10:00:00")
    st.save()
    blks = groups.build_blocks(st, groups.ungrouped(st))
    gid = groups.apply_groups(st, [{"action": "new", "block": blks[0].bid, "title": "甲类"}],
                              blks, ts=_NOW).nodes[0]
    st.save()
    return gid, (a, b)


def test_single_linked_to_group_enters_material(tmp_path):
    """⭐ 一条新经历**只连到已归过类的那条** ⇒ 也能进料（以前被"≥2"扔掉）。"""
    st = _store(tmp_path)
    gid, _members = _group_of_two(st)
    solo = _ep(st, "S", "新来的那条", "2026-09-26T10:00:00")
    st.add_edge(REL_AKIN, solo, _members[0], ts="2026-09-26T10:00:00")
    st.save()

    blks = groups.build_blocks(st, groups.ungrouped(st))
    assert len(blks) == 1 and blks[0].episodes == (solo,), blks
    assert blks[0].linked == (gid,)
    text = groups.render_blocks(st, blks)
    assert text.splitlines()[0] == "〔b1｜1 条〕 与 〔《甲类》｜2 条〕 —— 她把它连到这一类", text
    print(f"    单条进料: {text.splitlines()[0]}")


def test_isolated_single_still_excluded(tmp_path):
    """⚠️ **完全孤立**的（一条 akin 都没有）仍然不进料 —— 没有任何依据, 不替她猜。"""
    st = _store(tmp_path)
    _group_of_two(st)
    _ep(st, "L", "没人连过它", "2026-09-26T10:00:00")
    st.save()
    assert groups.build_blocks(st, groups.ungrouped(st)) == []
    print("    孤立的单条: 不进料（等她自己连上谁）")


def test_single_linked_to_two_groups_shows_both(tmp_path):
    """单条同时连到两个类 ⇒ 两个类都摆出来（选哪个是 LLM 的活）。"""
    st = _store(tmp_path)
    g1, members = _group_of_two(st)
    c = _ep(st, "C", "乙一", "2026-09-22T10:00:00")
    d = _ep(st, "D", "乙二", "2026-09-23T10:00:00")
    st.add_edge(REL_AKIN, c, d, ts="2026-09-23T10:00:00")
    st.save()
    blks = groups.build_blocks(st, groups.ungrouped(st))
    g2 = groups.apply_groups(st, [{"action": "new", "block": blks[0].bid, "title": "乙类"}],
                             blks, ts=_NOW).nodes[0]
    st.save()
    solo = _ep(st, "S", "两边都像", "2026-09-26T10:00:00")
    st.add_edge(REL_AKIN, solo, members[0], ts="2026-09-26T10:00:00")
    st.add_edge(REL_AKIN, solo, d, ts="2026-09-26T10:00:00")
    st.save()

    blks2 = groups.build_blocks(st, groups.ungrouped(st))
    assert len(blks2) == 1 and sorted(blks2[0].linked) == sorted([g1, g2]), blks2
    line = groups.render_blocks(st, blks2).splitlines()[0]
    assert "〔《甲类》｜2 条〕" in line and "〔《乙类》｜2 条〕" in line
    assert line.endswith("—— 她把它连到这些类"), line
    print(f"    连到两个类: {line}")


def test_digest_attaches_single(tmp_path):
    """接上了: 单条块走 `attach` ⇒ 它挂到那个类上（她那条边终于有人读了）。"""
    st = _store(tmp_path)
    gid, members = _group_of_two(st)
    solo = _ep(st, "S", "新来的那条", "2026-09-26T10:00:00")
    st.add_edge(REL_AKIN, solo, members[0], ts="2026-09-26T10:00:00")
    st.save()

    llm = RoundLLM(group={"attach": [{"block": "b1", "group": "甲类"}], "new": [],
                          "merge": []})
    res = digest_segment(st, llm, [_mmt(3)])
    assert res.ok, res.errors
    assert res.created_groups == [] and res.grouped_episodes == 1
    assert solo in st.graph().sources(gid, REL_MEMBER_OF)
    assert "〔b1｜1 条〕 与 〔《甲类》｜2 条〕" in llm.user_of(T.DIGEST_GROUP)
    print(f"    digest 接线: 单条挂到了 {gid}")


if __name__ == "__main__":
    import tempfile

    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
    print("all round-group tests passed")