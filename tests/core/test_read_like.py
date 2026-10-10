# -*- coding: utf-8 -*-
"""`read/like.py` —— **相似召回**第一笔（M1 字面 / M5 时间 / M6 先验）。

守门五条（每条都经**变异验红**: `.testtmp/verify_like_red.py`）:

  ① **无后端也出结果** —— 没有 embedder、没有网络、连 `ts` 都没有的裸档,
     只要字面重合就必须给结果（旧件 `recommend_candidates(embed_fn=None)` 在真机上四查询全空）
  ② **字面三路各自可命中** —— tags / 标题 / 正文覆盖（名字那一路是**加成**, 见 ④）
  ③ **时间衰减 + `floor` 不归零** —— 老记忆留一份, 绝不掉到 0
  ④ ⭐ **准入只认内容轴** —— 零重合时, 时间+先验+名字**拉满也不摆**; 且加成翻不了大盘
  ⑤ **不 import 旧召回件** —— `compose` / `recall` / `channels` / `channel_impl`（AST 扫）
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.brain import WikiStoreV2, make_node
from core.brain.read.like import (EVIDENCE, GATE, PARTS, SPECS, Part, RecallCtx, Spec,
                                  build_ctx, like, part_lexical, part_name, part_prior,
                                  part_struct, part_temporal, plan)
from core.brain.read.pack import Candidate, ledger_line

#: 固定的"现在"（**现实日**轴; 与 `age_days` / `freshness` 同一套时区）
NOW = datetime(2026, 10, 8, 21, 0, tzinfo=timezone(timedelta(hours=8)))

ROOT = Path(__file__).resolve().parents[2]
LIKE_PY = ROOT / "core" / "brain" / "read" / "like.py"
PACK_PY = ROOT / "core" / "brain" / "read" / "pack.py"
#: ⭐ `find` 与 `like` 是**同一个新召回栈**的两半（2026-10-08）⇒ 一起守:
#: 它也不许 import 旧件 / 不许够得着后端（`Clue` 是纯字面布尔树, 连 `re` 都不 import）。
FIND_PY = ROOT / "core" / "brain" / "read" / "find.py"


@pytest.fixture(autouse=True)
def _pin_knobs(monkeypatch):
    """把旋钮钉死（本机 `settings.toml` 里有什么都不影响这些断言）。"""
    from core.brain.read import recall_config as rc
    monkeypatch.setattr(rc, "_cache",
                        {"like_k": 3.0, "time_half_life_days": 5.0,
                         "time_freshness_floor": 0.25}, raising=False)


def _ts(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _ctx(query: str = "", **kw) -> RecallCtx:
    """输入契约（调用方那一侧）—— 只填输入字段, 派生料由 `build_ctx` 现算。"""
    return RecallCtx(now=NOW, query=query, **kw)


def _mat(st, query: str = "", **kw) -> RecallCtx:
    """建料（= `like()` 内部那一步: 种子只从 `lexical` 出）。"""
    return build_ctx(st, _ctx(query, **kw), active=["lexical", "struct"])


def _like(st, query: str = "", *, spec: str = "turn", **kw):
    return like(st, _ctx(query, **{k: v for k, v in kw.items()
                                   if k in ("emo_now", "place_now", "aff_now")}),
                spec=spec, **{k: v for k, v in kw.items()
                              if k in ("k", "weights")})


def _ep(nid, text, *, title="", tags=(), sig=0.5, ts="", emo=None):
    kw = dict(id=nid, text=text, title=title, tags=list(tags), significance=sig, ts=ts)
    if emo:
        kw["emo_span"], kw["emo_int"] = emo
    return make_node("episode", **kw)


def _store(tmp_path, nodes, *, edges=(), entities=(("老师", ("sensei",)),
                                                   ("杂草屋", ("秘密基地",)))):
    """小档 = 两个对象 + 若干 episode（名额自己给, 断言里要按 id 点名）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    for i, (name, aliases) in enumerate(entities):
        st.add(make_node("entity", id=f"x{i:04d}", name=name, aliases=list(aliases)))
    for n in nodes:
        st.add(n)
    for rel, src, dst in edges:
        st.add_edge(rel, src, dst)
    return st


#: 结构一跳那组用例的档：一个"类" g0001 下挂三条经历, 外加一条 **2 跳** 和一条 **共对象**
def _cluster_store(tmp_path, *, class_title="和老师一起吃饭的那些日子"):
    st = _store(tmp_path, [
        make_node("experience", id="g0001", title=class_title),
        _ep("m0001", "x", tags=["团子"], ts=_ts(0)),          # 种子（tags 命中）
        _ep("m0002", "那天也一起吃了点心", tags=["点心"]),      # akin 邻居（内容分 0）
        _ep("m0003", "另一件同类的事", tags=["别的事"]),        # 同类兄弟（内容分 0）
        _ep("m0004", "离得很远的另一件", tags=["远"]),          # 种子 → m0002 → m0004（**两跳**）
        _ep("m0005", "同一栋房子里的另一件事", tags=["房子"]),   # 与 m0001 共一个对象（**不是相似**）
    ], edges=[
        ("akin", "m0001", "m0002"),
        ("akin", "m0002", "m0004"),
        ("member_of", "m0001", "g0001"),
        ("member_of", "m0003", "g0001"),
        ("about", "m0001", "x0001"),
        ("about", "m0002", "x0001"),                          # m0002 也在「杂草屋」车道上
        ("about", "m0005", "x0001"),
    ])
    return st


# ---------------------------------------------------------------------------
# ② 字面三路（单测打分函数本身 —— 这就是拆函数的好处）
# ---------------------------------------------------------------------------

def test_lexical_three_routes():
    """tags / 标题 / 正文覆盖 —— 三路取最大, 且 `why` 说得出是哪一路赢的。"""
    ctx = _ctx("那盆苔藓长得怎么样了？")
    got = part_lexical(_ep("m0001", "瓦片缝里长出一小丛苔藓", tags=["苔藓"]), ctx)
    assert got == (0.60, "tags[苔藓]"), got                    # tags 基分

    multi = part_lexical(_ep("m0001", "x", tags=["苔藓", "杂草屋", "热茶"]),
                         _ctx("苔藓和杂草屋，还有热茶"))
    assert multi == (0.80, "tags[苔藓,杂草屋,热茶]"), multi     # 每多命中一个 +0.10

    titled = part_lexical(_ep("m0001", "x", title="瓦片缝里的苔藓"),
                          _ctx("你还记得瓦片缝里的苔藓那件事吗"))
    assert titled == (0.85, "标题点名"), titled                 # 标题（剥壳后）整体在 query 里

    cov = part_lexical(_ep("m0001", "我把一小株苔藓分给了夏莱的果酱瓶"),
                       _ctx("分给夏莱的一小株苔藓"))
    assert cov[0] > 0.35 and cov[1].startswith("覆盖"), cov

    assert part_lexical(_ep("m0001", "x", tags=["苔藓"]), _ctx("")) == (0.0, "")


def test_coverage_route_uses_the_shared_body_face():
    """⭐ 覆盖路与 `find` 的 `text` 锚**同一份正文面**（`pack.body_of`, 含**标题**）。

    2026-10-08: `_body` 从本模块搬去 `pack.body_of` —— 两处各写一份必然漂,
    而漂了就是"同一句话在两个召回器里命中面不同"（**静默**）。
    """
    titled = _ep("m0001", "别的", title="瓦片缝里的苔藓")
    q = _ctx("苔藓长在瓦片缝里")          # ⚠️ 标题整串**不在** query 里 ⇒ 走的不是"标题点名"
    score, why = part_lexical(titled, q)
    assert why.startswith("覆盖"), (score, why)        # 面里有标题 ⇒ 覆盖路命中
    bare = _ep("m0002", "别的")
    assert part_lexical(bare, q) == (0.0, "")          # 同一句话, 没有标题 ⇒ 零


def test_marker_tags_are_not_search_words():
    """`#` 开头的是**标记空间**（`#entity:` / `#pinned`）, 不是检索词。"""
    node = _ep("m0001", "x", tags=["#entity:老师", "#pinned"])
    assert part_lexical(node, _ctx("老师今晚有空吗")) == (0.0, "")


# ---------------------------------------------------------------------------
# ① 无后端也出结果（旧件的病根）
# ---------------------------------------------------------------------------

def test_like_works_without_any_backend(tmp_path):
    """① 裸档（无 embedder / 无网络 / 连 `ts` 都没有）—— 字面重合就必须出结果。

    真机依据: `recommend_candidates(embed_fn=None)` 在四个查询上**全空/最多一条**。
    """
    st = _store(tmp_path, [
        _ep("m0001", "瓦片缝里长出一小丛苔藓", title="瓦片缝里的苔藓", tags=["苔藓"]),
        _ep("m0002", "在甜品店吃了草莓蛋糕", title="甜品店", tags=["甜点"], sig=0.95),
    ])
    out = _like(st, "那盆苔藓长得怎么样了？")
    assert [c.node.id for c in out] == ["m0001"], out
    assert out[0].score > 0
    assert "tags[苔藓]" in out[0].why
    assert "无 ts" in out[0].why                               # 时间那一份**降级**, 不是编一个 0 天
    assert all(isinstance(c, Candidate) for c in out)


def test_like_returns_empty_when_nothing_matches(tmp_path):
    """宁缺勿错: 一条都不像 ⇒ **[]**（不拿"最近一条/最高 sig 那条"来凑）。"""
    st = _store(tmp_path, [_ep("m0001", "在甜品店吃了草莓蛋糕", tags=["甜点"], sig=0.95)])
    assert _like(st, "今天天气不错") == []
    assert _like(st, "") == []


def test_sorted_by_score_and_ties_by_id(tmp_path):
    """降序 + **同分按 id**（不信任输入顺序, 自己排 —— 顺序就是答案）。"""
    st = _store(tmp_path, [
        _ep("m0002", "苔藓甲", tags=["苔藓"], ts=_ts(3)),
        _ep("m0001", "苔藓乙", tags=["苔藓"], ts=_ts(3)),       # 故意后加, 分与前一条相同
        _ep("m0003", "苔藓丙", tags=["苔藓"], ts=_ts(0)),        # 今天的 ⇒ 分最高
    ])
    assert [c.node.id for c in _like(st, "苔藓")] == ["m0003", "m0001", "m0002"]
    assert [c.node.id for c in _like(st, "苔藓")] == ["m0003", "m0001", "m0002"]


# ---------------------------------------------------------------------------
# ③ 时间衰减 + floor 不归零
# ---------------------------------------------------------------------------

def test_temporal_decay_and_floor_never_zero():
    """`freshness`: 今天 = 1.0; 很久以前 → **逼近 `floor`（0.25）而不是 0**。"""
    assert part_temporal(_ep("m1", "x", ts=_ts(0)), RecallCtx(now=NOW))[0] == 1.0
    old = part_temporal(_ep("m1", "x", ts=_ts(400)), RecallCtx(now=NOW))
    assert 0.0 < old[0] < 0.30, old
    assert abs(old[0] - 0.25) < 0.01, old                      # 80 个半衰期 ⇒ 就是 floor
    assert old[1].endswith("前")                                # 一句话是她的口吻（虚化短语）
    missing = part_temporal(_ep("m1", "x"), RecallCtx(now=NOW))
    assert missing == (0.0, "无 ts")                            # 缺 ts **不出分**, 不折成"刚发生"


def test_newer_wins_when_content_is_equal(tmp_path):
    st = _store(tmp_path, [
        _ep("m0001", "苔藓甲", tags=["苔藓"], ts=_ts(30)),
        _ep("m0002", "苔藓乙", tags=["苔藓"], ts=_ts(0)),
    ])
    assert [c.node.id for c in _like(st, "苔藓")] == ["m0002", "m0001"]


# ---------------------------------------------------------------------------
# ②′ 结构一跳（⭐ 窄门准入）
# ---------------------------------------------------------------------------

def test_struct_reaches_akin_and_class_siblings(tmp_path):
    """窄门就两条: `akin`（她认过的相似, 1.0）与 `member_of` 的**同类兄弟**（0.8）。"""
    ctx = _mat(_cluster_store(tmp_path), "团子")
    assert ctx.seeds == {"m0001": 0.60}, ctx.seeds
    assert ctx.reach["m0002"] == (0.60, "认过的相似"), ctx.reach
    assert ctx.reach["m0003"] == (0.48, "同类兄弟"), ctx.reach


def test_a_seed_gets_no_struct_bonus(tmp_path):
    """⭐ 种子不吃结构分（同一个理由不重复计）—— 类自己命中时也只当种子。"""
    st = _cluster_store(tmp_path, class_title="和老师吃饭送团子")   # 类名带"团子" ⇒ 它也命中
    ctx = _mat(st, "团子")
    assert set(ctx.seeds) == {"g0001", "m0001"}, ctx.seeds          # 类也可以是内容命中
    assert "g0001" not in ctx.reach and "m0001" not in ctx.reach    # 但种子不当"被够到的人"
    assert ctx.reach["m0003"] == (0.80, "同类兄弟")                  # 由类的 1.00 够到
    assert "g0001" not in {c.node.id for c in _like(st, "团子")}   # 类不进结果（选面）


def test_struct_does_not_expand_about_nor_two_hops(tmp_path):
    """⛔ 不扩 `about`（归属≠相似）、⛔ 不传递闭包、⛔ 不许把别的选面摆出来。"""
    st = _cluster_store(tmp_path)
    ctx = _mat(st, "团子")
    assert "m0004" not in ctx.reach            # 两跳（邻居的邻居）
    assert "m0005" not in ctx.reach            # 与种子**共一个对象**（`about` 刻意不在窄门里）
    assert "x0001" not in ctx.reach            # 对象本身也不该被结构够到（`about` 不在门里）
    # 类会被够到（"一类的兄弟"就是从它那儿数的）, 但**选面**把它挡在打分之外
    assert [c.node.id for c in _like(st, "团子")] == ["m0001", "m0002", "m0003"]


def test_struct_never_exceeds_its_seed_and_seed_outranks_it(tmp_path):
    """不变量: **结构分 ≤ 它的种子**; 排序上种子也在它前面。"""
    st = _cluster_store(tmp_path)
    ctx = _mat(st, "团子")
    seed_lex = part_lexical(st.get("m0001"), ctx)[0]
    assert part_struct(st.get("m0002"), ctx)[0] <= seed_lex
    assert part_struct(st.get("m0003"), ctx)[0] <= seed_lex
    out = _like(st, "团子")
    assert [c.node.id for c in out] == ["m0001", "m0002", "m0003"], out
    assert out[0].why.startswith("tags[团子]")
    assert out[1].why.startswith("认过的相似 0.60")
    assert out[2].why.startswith("同类兄弟 0.48")


def test_struct_admits_through_the_narrow_gate(tmp_path):
    """⭐ 窄门**能带新节点进来**（它们自己的内容分是 0）—— 这正是结构一跳的意义。"""
    st = _cluster_store(tmp_path)
    ctx = _mat(st, "团子")
    for nid in ("m0002", "m0003"):
        assert part_lexical(st.get(nid), ctx)[0] == 0.0     # 内容: 零
        assert part_struct(st.get(nid), ctx)[0] > 0.0       # 结构: 有 ⇒ 准入过
    assert {c.node.id for c in _like(st, "团子")} == {"m0001", "m0002", "m0003"}


def test_struct_does_not_double_count_the_name_lane(tmp_path):
    """一条理由只算一次: 已经靠"名字"进来的节点, 结构不再给分。"""
    st = _cluster_store(tmp_path)
    ctx = _mat(st, "杂草屋的团子")
    assert part_name(st.get("m0002"), ctx)[0] == 1.0        # 名字那条还写着（m0002 在车道上）
    assert part_struct(st.get("m0002"), ctx) == (0.0, "")   # 结构不再重复给


# ---------------------------------------------------------------------------
# ④ ⭐ 准入只认内容轴 + 窄门
# ---------------------------------------------------------------------------

def test_admission_needs_content_evidence(tmp_path):
    """⭐ 零字面重合 ⇒ **一条都不摆**（时间/先验/名字拉满也不行）。

    反例是真机实测的: 「老师，你今天有空吗」会让「老师」车道上的 10 条并列进池,
    排序全交给先验 ⇒ 退化成"关于老师最重要的事", 且**每轮同样两条**。
    """
    node = _ep("m0001", "和老师在杂草屋说了很久的话", title="杂草屋的下午",
               tags=["杂草屋"], sig=0.95, ts=_ts(0))
    st = _store(tmp_path, [node], edges=[("about", "m0001", "x0000")])
    ctx = _mat(st, "老师，你今天有空吗？")   # 走真路建料（车道在里面）
    assert part_lexical(node, ctx)[0] == 0.0                   # 内容轴: 零
    assert part_temporal(node, ctx)[0] == 1.0                  # 时间: 满
    assert part_prior(node, ctx)[0] >= 0.9                     # 先验: 满
    assert part_name(node, ctx) == (1.0, "名字[老师]")          # 名字: 满（老师车道）
    assert _like(st, "老师，你今天有空吗？") == []       # ⇒ 仍然一条都不摆


def test_name_hit_is_a_bonus_not_an_admission(tmp_path):
    """名字命中**只加成**: 同内容分的两条, 车道上那条被顶上来（而不是凭空准入）。"""
    st = _store(tmp_path, [
        _ep("m0001", "在屋顶看了很久的月亮", title="屋顶的夜", tags=["月亮"]),
        _ep("m0002", "那天和老师一起走去杂草屋", title="走过去的那段路", tags=["月亮"]),
        # m0003 也在「杂草屋」车道上, 但**正文里没有那三个字** ⇒ 名字单独救不了它
        _ep("m0003", "那次我们一起走夜路回家", title="夜路", tags=["夜路"]),
    ], edges=[("about", "m0002", "x0001"), ("about", "m0003", "x0001")])
    out = _like(st, "今晚的月亮真好看（杂草屋）")
    assert [c.node.id for c in out] == ["m0002", "m0001"], out  # 内容分相同 ⇒ 名字加成决胜
    assert "名字[杂草屋]" in out[0].why
    # 名字单独**不能**让人进池（m0002 是靠正文里的"杂草屋"三个字进来的, 不是靠车道）
    assert "m0003" not in [c.node.id for c in _like(st, "杂草屋")]


def test_prior_is_just_significance(tmp_path):
    """先验轴 = **一个参量**（`sig`）: 不带时间、不带情绪（2026-10-08 从 `det` 拆干净）。

    真档依据: `pearson(sig, span·int) = 0.879`、`span` 与 `int` 平均只差 0.063、
    按 `sig` 排 vs 按 `det` 排前 8 名 8/8 重合 ⇒ 留着那两项就是同一个 L1 判断数两次。
    """
    base = _ep("m0001", "x", sig=0.85)
    fresh = _ep("m0002", "x", sig=0.85, ts=_ts(0), emo=(1.0, 1.0))     # 今天 + 情绪拉满
    old = _ep("m0003", "x", sig=0.85, ts=_ts(400), emo=(0.1, 0.1))     # 去年 + 情绪接近零
    assert part_prior(base, RecallCtx(now=NOW)) == (0.85, "重要 0.85")
    assert part_prior(fresh, RecallCtx(now=NOW))[0] == 0.85              # `ts` 不影响它
    assert part_prior(old, RecallCtx(now=NOW))[0] == 0.85                # 情绪不影响它
    assert part_prior(fresh, RecallCtx(now=NOW))[0] <= 1.0               # 不用夹（sig 本来就 ≤1）


def test_bonus_cannot_outrank_a_clear_content_gap(tmp_path):
    """⭐ 不变量: 内容分差 > **加成总权重**时, 加成拉满也翻不了盘（内容永远是多数派）。

    组里两条都**真的进了池**: A 靠标题（0.85 起）+ 覆盖率 1.00 ⇒ 内容满分、加成零;
    B 靠覆盖率 0.375（刚过线）⇒ 内容最低、加成拉满（今天 + sig 1.0 + 情绪 0.5 + 名字命中）。
    """
    pl = [p for p in plan("turn") if p[2] > 0]                     # **这次真调的**那几路
    weights = [w for _n, _p, w in pl]
    admit = [w for _n, p, w in pl if p.axis == EVIDENCE]
    bonus = [w for _n, p, w in pl if p.axis != EVIDENCE]
    assert sum(weights) == sum(admit) + sum(bonus)
    assert sum(bonus) < sum(admit), (sum(bonus), sum(admit))       # 加成永远是少数派
    assert max(bonus) < min(admit)                                 # 且单条也不及最小的准入门
    assert max(bonus) * len(pl) < max(admit)

    q = "苔藓月亮团子中秋月饼甜点杂草屋里的热茶"                      # 19 字 ⇒ 18 个 2-gram
    body = "苔藓月亮团子中秋"                                        # 8 字 ⇒ 7 个都在 q 里
    st = _store(tmp_path, [
        _ep("m0001", "x", title=q),                                # 加成零: 无 ts、不在车道上
        _ep("m0002", body, sig=1.0, ts=_ts(0), emo=(1.0, 0.5)),    # 加成拉满
    ], edges=[("about", "m0002", "x0001")])
    ctx = _mat(st, q)
    node_b = st.get("m0002")
    got = part_lexical(node_b, ctx)                                # 用例把 B 钉在"刚过线"那一档
    assert got[1] == "覆盖 0.39" and 0.35 < got[0] < 0.40, (q, body, got)
    assert part_name(node_b, ctx)[0] == 1.0 and part_temporal(node_b, ctx)[0] == 1.0
    out = _like(st, q)
    assert [c.node.id for c in out] == ["m0001", "m0002"], out


# ---------------------------------------------------------------------------
# ⑥ 三张表的形状（注册表 / 档位 / 输入契约）—— 这一笔的"语义守门"
# ---------------------------------------------------------------------------

def test_every_spec_row_points_at_a_registered_part():
    """档位里写的路名必须真在注册表里（表写错了当场炸, 不许静默少一路）。"""
    for spec_name, sp in SPECS.items():
        for name, w in sp.parts:
            assert name in PARTS, (spec_name, name)
            assert isinstance(w, (int, float)) and w >= 0.0, (spec_name, name, w)
        assert sp.kinds, spec_name


def test_turn_spec_owns_the_selection_surface():
    """⭐ **选面归档位, 不归渲染层**（2026-10-08 用户裁）。

    P19 从前靠 `render_recall_block` 里一句 `kind == "episode"` 兜底 —— 那是**第二个
    真源**, 而且会把将来 `look` 想摆的 belief / entity **静默吃掉**。现在判据只有这一格:
    "这一段要连的是旧事" ⇒ `episode`; "本段新经历 + 认知" ⇒ `digest` 那一档。
    """
    assert SPECS["turn"].kinds == ("episode",)
    assert set(SPECS["digest"].kinds) > {"episode"}, "digest 档是认知面也进池的那一档"


def test_every_spec_has_at_least_one_admitting_part():
    """每个档位至少要有一条**证据轴**有权重 —— 否则该档恒返空（准入过不去）。"""
    for spec_name, sp in SPECS.items():
        assert any(PARTS[n].axis == EVIDENCE and w > 0 for n, w in sp.parts), spec_name


def test_part_needs_must_exist_on_the_contract():
    """`needs` 里写的字段必须在 `RecallCtx` 上真存在（防拼错 ⇒ 那一路静默永不参与）。"""
    fields = set(RecallCtx.__dataclass_fields__)
    for name, part in PARTS.items():
        for need in part.needs:
            assert need in fields, (name, need, sorted(fields))


def test_plan_rejects_unknown_names_and_adds_no_parts():
    """覆盖只能**改本档已有那几路的权重**, 不能靠覆盖加一路（档位决定调哪几路）。"""
    with pytest.raises(KeyError):
        plan("turn", {"emotion": 0.5})                  # 本档没有这一路
    with pytest.raises(KeyError):
        plan("nosuch")
    with pytest.raises(KeyError):
        plan("turn", {"lexcial": 0.0})                  # 拼错
    assert [n for n, _p, _w in plan("turn", {"struct": 0.0})] == \
           [n for n, _p, _w in plan("turn")]            # 只改权重, 不增不减


def test_weight_zero_drops_the_part_entirely(tmp_path):
    """⭐ `0` = 这一路**完全不参与**（连准入也不算）; 且内容路关掉 ⇒ 结构也没了种子。

    ⚠️ 最后那条是**消融的正确性**: 种子只从 `Part.seeds` 为真的路（= `lexical`）出,
    所以"关掉字面证据"时结构路不会偷偷吃着字面证据 —— 否则那个消融是假的。
    """
    st = _cluster_store(tmp_path)
    # 关掉结构 ⇒ 只剩内容种子自己（邻居不再被带进来）
    assert [c.node.id for c in _like(st, "团子", weights={"struct": 0.0})] == ["m0001"]
    # 关掉内容 ⇒ 没有种子 ⇒ 结构无从扩散 ⇒ **没有东西能准入**
    assert _like(st, "团子", weights={"lexical": 0.0}) == []
    # 两路准入都关 ⇒ 同样空（不是"全池都进"）
    assert _like(st, "团子", weights={"lexical": 0.0, "struct": 0.0}) == []


def test_missing_input_drops_the_part_and_says_so(tmp_path, caplog):
    """`needs` 缺输入 ⇒ 那一路自动不参与 + 台账记 `skip=`（不靠人记得配 0）。"""
    st = _cluster_store(tmp_path)
    SPECS["_probe"] = Spec(kinds=("episode",), parts=(("lexical", 1.0), ("name", 0.15)))
    try:
        with caplog.at_level("INFO", logger="core.brain.read.like"):
            out = like(st, _ctx(""), spec="_probe")       # query 空 ⇒ 两路都缺输入
        line = _ledger(caplog)
        assert "skip=lexical(无query),name(无query)" in line, line
        assert out == []                                  # 唯一证据路被跳过 ⇒ 没有准入
    finally:
        SPECS.pop("_probe", None)


def test_ledger_prints_spec_skip_and_overrides(tmp_path, caplog):
    """台账要能复盘"这次为什么不同": 档位 · 没参与的路 · 一次性覆盖。"""
    st = _cluster_store(tmp_path)
    with caplog.at_level("INFO", logger="core.brain.read.like"):
        _like(st, "团子", weights={"struct": 0.0})
    line = _ledger(caplog)
    assert "spec=turn" in line and "w=struct0.00" in line
    assert "struct(权重0)" in line                       # 被覆盖关掉的那一路
    assert "semantic(权重0)" in line                     # ⭐ 实时路径不跑后端（2026-10-08 裁）


# ---------------------------------------------------------------------------
# ⑦ 语义轴（M2）—— 后端在就用, 不在就自动退, **绝不返空**
# ---------------------------------------------------------------------------

def _ledger(caplog) -> str:
    """台账那一行（`spec=` 那行; 别的 info 行也可能带 `recall_like` 前缀）。"""
    return [r.getMessage() for r in caplog.records
            if "recall_like" in r.getMessage() and " spec=" in r.getMessage()][-1]


def _bag_embed(texts):
    """假后端: 词袋向量（命中即相似）—— 用它才测得出"语义召回"本身。"""
    vocab = ["绿绿", "苔藓", "甜点", "团子", "杂草", "月"]
    return [[1.0 if v in (t or "") else 0.0 for v in vocab] + [0.01] for t in texts]


def test_semantic_recalls_a_paraphrase_that_lexical_misses(tmp_path):
    """⭐ 语义轴的**存在理由**: 改写句（字面一个词都不重合）也要能召回到。"""
    st = _store(tmp_path, [
        _ep("m0001", "瓦片缝里长出一小丛绿绿的东西", title="瓦缝", tags=["苔藓"]),
        _ep("m0002", "在店里吃了蛋糕", title="甜品", tags=["甜点"]),
    ])
    # 字面: 既不命中 tags 也不命中标题（覆盖率也过不了线）⇒ 只有语义能救
    assert _like(st, "那片绿绿的小东西还在吗") == []
    out = like(st, _ctx("那片绿绿的小东西还在吗", embed_fn=_bag_embed),
               weights={"semantic": 1.0})   # turn 档默认关语义（实时路径）⇒ 用例自己打开
    assert [c.node.id for c in out] == ["m0001"], out
    assert "语义" in out[0].why


def test_backend_missing_degrades_but_still_returns(tmp_path, caplog):
    """⭐ **旧件病根的反面**: 后端不在 ⇒ 那一路自动不参与, 其余照常出结果（不是返空）。

    ⚠️ `turn` 档默认就把 `semantic` 关着（实时路径, 2026-10-08 裁）⇒ 这里**用覆盖把它打开**,
    测的才是"要它、但后端不在"那条路（否则测到的是"压根不要它"）。
    """
    st = _store(tmp_path, [_ep("m0001", "瓦片缝里的苔藓", tags=["苔藓"])])
    with caplog.at_level("INFO", logger="core.brain.read.like"):
        out = _like(st, "苔藓", weights={"semantic": 1.0})       # 没有 embed_fn
    assert [c.node.id for c in out] == ["m0001"]                 # 字面照常给结果
    line = _ledger(caplog)
    assert "semantic(无embed_fn)" in line


def test_backend_blows_up_degrades_not_raises(tmp_path, caplog):
    """后端抛异常 ⇒ 记进台账的 `skip=`, 其余几路照常（宁缺勿错, 不阻断剧情）。"""
    def boom(_texts):
        raise RuntimeError("模型未加载")
    st = _store(tmp_path, [_ep("m0001", "瓦片缝里的苔藓", tags=["苔藓"])])
    with caplog.at_level("INFO", logger="core.brain.read.like"):
        out = like(st, _ctx("苔藓", embed_fn=boom), weights={"semantic": 1.0})
    assert [c.node.id for c in out] == ["m0001"]
    line = _ledger(caplog)
    assert "语义(后端故障:RuntimeError)" in line


def test_semantic_is_pool_normalized_and_rank_gated(tmp_path):
    """`scale=COSINE` 的两条语义: **池内 min-max**（池里最高的归一到 1.0, 不是"raw cos 直接用"）
    + **名次门槛**（只有原始分前 `[recall].sim_k` 名算命中; cos 恒正 ⇒ "> 0" 在它上面没有意义）。

    ⚠️ 断言必须落在**最终分**上: `ctx.sim` 里存的是**原始 cos**（归一由合成层第二趟做）——
    只断言 `part_semantic` 的输出**测不出归一有没有生效**（这支变异就是这么假绿过一次）。
    """
    from core.brain.read.like import PARTS, build_ctx, part_semantic
    st = _store(tmp_path, [
        _ep("m0001", "苔藓甲", tags=["苔藓"]), _ep("m0002", "苔藓乙", tags=["苔藓"]),
        _ep("m0003", "苔藓丙", tags=["苔藓"]), _ep("m0004", "苔藓丁", tags=["别的"]),
    ])
    # query → [1,0]; 每条按**指定的 cos** 造向量（cos = 第一分量）⇒ 池内最高是 0.9, 不是 1.0
    cos = {"甲": 0.9, "乙": 0.5, "丙": 0.0, "丁": 0.2}

    def fixed(texts):
        if len(texts) == 1 and texts[0] == "苔藓":           # query 那一次调用
            return [[1.0, 0.0]]
        out = []
        for t in texts:
            c = next((v for k, v in cos.items() if k in (t or "")), 0.0)
            out.append([c, (1.0 - c * c) ** 0.5])
        return out

    ctx = build_ctx(st, _ctx("苔藓", embed_fn=fixed), active=["semantic"])
    assert PARTS["semantic"].scale == "cosine"               # 池内归一是它这一路的语义
    assert round(ctx.sim["m0001"], 3) == 0.9                 # 派生料里是**原始 cos**
    assert part_semantic(st.get("m0001"), ctx) == (0.9, "语义 0.90")

    # 只留语义（其余三路先验照常: temporal 无 ts = 0 · prior = sig 0.5 · name 无名字 = 0）
    # ⇒ 归一后 m0001 拿 1.0; 若没归一则是 0.9（分数对不上）
    out = like(st, _ctx("苔藓", embed_fn=fixed),
               weights={"semantic": 1.0, "lexical": 0.0, "struct": 0.0})
    want = (1.0 + 0.15 * 0.5) / (1.00 + 0.15 + 0.15 + 0.15)
    assert out[0].node.id == "m0001" and abs(out[0].score - want) < 1e-9, out

    # 名次门槛: 把 sim_k 压到 1 ⇒ 只有原始 cos 最高的那条算命中, 其余**从这一路拿 0**
    from core.brain.read import recall_config as rc
    rc._cache = dict(rc.DEFAULTS, sim_k=1.0)
    try:
        out2 = like(st, _ctx("苔藓", embed_fn=fixed),
                weights={"semantic": 1.0, "lexical": 0.0, "struct": 0.0})
        assert [c.node.id for c in out2] == ["m0001"], out2
    finally:
        rc._cache = None


def test_gate_axis_is_not_implemented_and_says_so(tmp_path):
    """⛔ `axis=GATE` 的路配了权重就**当场炸** —— 合成器只有加权平均那条路径,
    把它当加数会静默算错（乘性闸门 vs 加数, 完全是两回事）。"""
    PARTS["_gate"] = Part(part_prior, axis=GATE)
    SPECS["_g"] = Spec(kinds=("episode",), parts=(("lexical", 1.0), ("_gate", 0.5)))
    try:
        with pytest.raises(NotImplementedError) as e:
            plan("_g")
        assert "GATE" in str(e.value)
        # 权重 0 = 不参与 ⇒ 不炸（配了权重才算"要用它"）
        assert [n for n, _p, _w in plan("_g", {"_gate": 0.0})] == ["lexical", "_gate"]
    finally:
        SPECS.pop("_g", None)
        PARTS.pop("_gate", None)


# ---------------------------------------------------------------------------
# ⑤ 不 import 旧召回件（把"不复用资源"落成可执行约束）
# ---------------------------------------------------------------------------

#: 旧召回整族（**零调用待删**）——新件一律不许 import
BANNED = ("core.brain.read.compose", "core.brain.read.recall",
          "core.brain.read.channels", "core.brain.read.channel_impl")
#: "无后端"那条的代码形态: 召回模块**够不着**任何网络/LLM 客户端
NO_BACKEND = ("httpx", "requests", "urllib", "openai", "core.rag", "core.llm")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.append(node.module or "")
        elif isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
    return out


def test_new_recall_does_not_import_the_old_stack():
    """⑤ 新件不许吊在旧召回件上（那正是"复用资源"要避免的）。"""
    for path in (LIKE_PY, PACK_PY, FIND_PY):
        mods = _imports(path)
        bad = [m for m in mods
               if any(m == b or m.startswith(b + ".") for b in BANNED)]
        assert not bad, (path.name, bad)


def test_like_has_no_backend_at_all():
    """① 的代码形态: `like` 连"能出网的东西"都不 import（不是"没传 embed_fn"）。"""
    for path in (LIKE_PY, PACK_PY, FIND_PY):
        bad = [m for m in _imports(path)
               if any(m == b or m.startswith(b + ".") for b in NO_BACKEND)]
        assert not bad, (path.name, bad)


# ---------------------------------------------------------------------------
# 台账（`why` 的唯一消费者 —— 不然它就是个没人读的字段）
# ---------------------------------------------------------------------------

def test_ledger_line_shape():
    line = ledger_line([Candidate(node=_ep("m0001", "x"), score=0.7537, why="tags[苔藓]")],
                       query="那盆\n苔藓呢", pool=21, k=3)
    assert line.startswith("recall_like q=「那盆 苔藓呢」 pool=21 cand=1 k=3 top=")
    assert "m0001:0.754←tags[苔藓]" in line
    assert "\n" not in line
    assert ledger_line([], query="x", pool=0, k=3).endswith("top=-")


def test_like_writes_the_ledger_line(tmp_path, caplog):
    st = _store(tmp_path, [_ep("m0001", "苔藓", tags=["苔藓"], ts=_ts(0))])
    with caplog.at_level("INFO", logger="core.brain.read.like"):
        _like(st, "苔藓")
    hits = [r.getMessage() for r in caplog.records if "recall_like" in r.getMessage()]
    assert len(hits) == 1, hits
    assert "pool=1" in hits[0] and "cand=1" in hits[0] and "top=m0001" in hits[0]
