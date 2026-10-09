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
from core.brain.read.like import (LikeCtx, build_ctx, like, part_lexical, part_name,
                                  part_prior, part_temporal)
from core.brain.read.pack import Candidate, ledger_line

#: 固定的"现在"（**现实日**轴; 与 `age_days` / `freshness` 同一套时区）
NOW = datetime(2026, 10, 8, 21, 0, tzinfo=timezone(timedelta(hours=8)))

ROOT = Path(__file__).resolve().parents[2]
LIKE_PY = ROOT / "core" / "brain" / "read" / "like.py"
PACK_PY = ROOT / "core" / "brain" / "read" / "pack.py"


@pytest.fixture(autouse=True)
def _pin_knobs(monkeypatch):
    """把旋钮钉死（本机 `settings.toml` 里有什么都不影响这些断言）。"""
    from core.brain.read import recall_config as rc
    monkeypatch.setattr(rc, "_cache",
                        {"like_k": 3.0, "time_half_life_days": 5.0,
                         "time_freshness_floor": 0.25}, raising=False)


def _ts(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")


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


# ---------------------------------------------------------------------------
# ② 字面三路（单测打分函数本身 —— 这就是拆函数的好处）
# ---------------------------------------------------------------------------

def test_lexical_three_routes():
    """tags / 标题 / 正文覆盖 —— 三路取最大, 且 `why` 说得出是哪一路赢的。"""
    ctx = LikeCtx(query="那盆苔藓长得怎么样了？")
    got = part_lexical(_ep("m0001", "瓦片缝里长出一小丛苔藓", tags=["苔藓"]), ctx)
    assert got == (0.60, "tags[苔藓]"), got                    # tags 基分

    multi = part_lexical(_ep("m0001", "x", tags=["苔藓", "杂草屋", "热茶"]),
                         LikeCtx(query="苔藓和杂草屋，还有热茶"))
    assert multi == (0.80, "tags[苔藓,杂草屋,热茶]"), multi     # 每多命中一个 +0.10

    titled = part_lexical(_ep("m0001", "x", title="瓦片缝里的苔藓"),
                          LikeCtx(query="你还记得瓦片缝里的苔藓那件事吗"))
    assert titled == (0.85, "标题点名"), titled                 # 标题（剥壳后）整体在 query 里

    cov = part_lexical(_ep("m0001", "我把一小株苔藓分给了夏莱的果酱瓶"),
                       LikeCtx(query="分给夏莱的一小株苔藓"))
    assert cov[0] > 0.35 and cov[1].startswith("覆盖"), cov

    assert part_lexical(_ep("m0001", "x", tags=["苔藓"]), LikeCtx(query="")) == (0.0, "")


def test_marker_tags_are_not_search_words():
    """`#` 开头的是**标记空间**（`#entity:` / `#pinned`）, 不是检索词。"""
    node = _ep("m0001", "x", tags=["#entity:老师", "#pinned"])
    assert part_lexical(node, LikeCtx(query="老师今晚有空吗")) == (0.0, "")


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
    out = like(st, "那盆苔藓长得怎么样了？", now=NOW)
    assert [c.node.id for c in out] == ["m0001"], out
    assert out[0].score > 0
    assert "tags[苔藓]" in out[0].why
    assert "无 ts" in out[0].why                               # 时间那一份**降级**, 不是编一个 0 天
    assert all(isinstance(c, Candidate) for c in out)


def test_like_returns_empty_when_nothing_matches(tmp_path):
    """宁缺勿错: 一条都不像 ⇒ **[]**（不拿"最近一条/最高 sig 那条"来凑）。"""
    st = _store(tmp_path, [_ep("m0001", "在甜品店吃了草莓蛋糕", tags=["甜点"], sig=0.95)])
    assert like(st, "今天天气不错", now=NOW) == []
    assert like(st, "", now=NOW) == []


def test_sorted_by_score_and_ties_by_id(tmp_path):
    """降序 + **同分按 id**（不信任输入顺序, 自己排 —— 顺序就是答案）。"""
    st = _store(tmp_path, [
        _ep("m0002", "苔藓甲", tags=["苔藓"], ts=_ts(3)),
        _ep("m0001", "苔藓乙", tags=["苔藓"], ts=_ts(3)),       # 故意后加, 分与前一条相同
        _ep("m0003", "苔藓丙", tags=["苔藓"], ts=_ts(0)),        # 今天的 ⇒ 分最高
    ])
    assert [c.node.id for c in like(st, "苔藓", now=NOW)] == ["m0003", "m0001", "m0002"]
    assert [c.node.id for c in like(st, "苔藓", now=NOW)] == ["m0003", "m0001", "m0002"]


# ---------------------------------------------------------------------------
# ③ 时间衰减 + floor 不归零
# ---------------------------------------------------------------------------

def test_temporal_decay_and_floor_never_zero():
    """`freshness`: 今天 = 1.0; 很久以前 → **逼近 `floor`（0.25）而不是 0**。"""
    assert part_temporal(_ep("m1", "x", ts=_ts(0)), LikeCtx(now=NOW))[0] == 1.0
    old = part_temporal(_ep("m1", "x", ts=_ts(400)), LikeCtx(now=NOW))
    assert 0.0 < old[0] < 0.30, old
    assert abs(old[0] - 0.25) < 0.01, old                      # 80 个半衰期 ⇒ 就是 floor
    assert old[1].endswith("前")                                # 一句话是她的口吻（虚化短语）
    missing = part_temporal(_ep("m1", "x"), LikeCtx(now=NOW))
    assert missing == (0.0, "无 ts")                            # 缺 ts **不出分**, 不折成"刚发生"


def test_newer_wins_when_content_is_equal(tmp_path):
    st = _store(tmp_path, [
        _ep("m0001", "苔藓甲", tags=["苔藓"], ts=_ts(30)),
        _ep("m0002", "苔藓乙", tags=["苔藓"], ts=_ts(0)),
    ])
    assert [c.node.id for c in like(st, "苔藓", now=NOW)] == ["m0002", "m0001"]


# ---------------------------------------------------------------------------
# ④ ⭐ 准入只认内容轴
# ---------------------------------------------------------------------------

def test_admission_needs_content_evidence(tmp_path):
    """⭐ 零字面重合 ⇒ **一条都不摆**（时间/先验/名字拉满也不行）。

    反例是真机实测的: 「老师，你今天有空吗」会让「老师」车道上的 10 条并列进池,
    排序全交给先验 ⇒ 退化成"关于老师最重要的事", 且**每轮同样两条**。
    """
    node = _ep("m0001", "和老师在杂草屋说了很久的话", title="杂草屋的下午",
               tags=["杂草屋"], sig=0.95, ts=_ts(0))
    st = _store(tmp_path, [node], edges=[("about", "m0001", "x0000")])
    ctx = build_ctx(st, query="老师，你今天有空吗？", now=NOW)   # 走真路建料（车道在里面）
    assert part_lexical(node, ctx)[0] == 0.0                   # 内容轴: 零
    assert part_temporal(node, ctx)[0] == 1.0                  # 时间: 满
    assert part_prior(node, ctx)[0] >= 0.9                     # 先验: 满
    assert part_name(node, ctx) == (1.0, "名字[老师]")          # 名字: 满（老师车道）
    assert like(st, "老师，你今天有空吗？", now=NOW) == []       # ⇒ 仍然一条都不摆


def test_name_hit_is_a_bonus_not_an_admission(tmp_path):
    """名字命中**只加成**: 同内容分的两条, 车道上那条被顶上来（而不是凭空准入）。"""
    st = _store(tmp_path, [
        _ep("m0001", "在屋顶看了很久的月亮", title="屋顶的夜", tags=["月亮"]),
        _ep("m0002", "那天和老师一起走去杂草屋", title="走过去的那段路", tags=["月亮"]),
        # m0003 也在「杂草屋」车道上, 但**正文里没有那三个字** ⇒ 名字单独救不了它
        _ep("m0003", "那次我们一起走夜路回家", title="夜路", tags=["夜路"]),
    ], edges=[("about", "m0002", "x0001"), ("about", "m0003", "x0001")])
    out = like(st, "今晚的月亮真好看（杂草屋）", now=NOW)
    assert [c.node.id for c in out] == ["m0002", "m0001"], out  # 内容分相同 ⇒ 名字加成决胜
    assert "名字[杂草屋]" in out[0].why
    # 名字单独**不能**让人进池（m0002 是靠正文里的"杂草屋"三个字进来的, 不是靠车道）
    assert "m0003" not in [c.node.id for c in like(st, "杂草屋", now=NOW)]


def test_prior_is_clamped_to_one(tmp_path):
    """先验**夹到 1**: 真档 det 跨 0.29~1.45 ⇒ 不夹的话同一权重下它的话语权会放大 1.45 倍。"""
    node = _ep("m0001", "x", sig=1.0, ts=_ts(0), emo=(1.0, 0.5))   # det = 1.0·1.0 + 0.5 = 1.5
    assert part_prior(node, LikeCtx(now=NOW))[0] == 1.0
    weak = _ep("m0002", "x", sig=0.5, ts=_ts(0))                   # det = 0.5
    assert part_prior(weak, LikeCtx(now=NOW))[0] == 0.5


def test_bonus_cannot_outrank_a_clear_content_gap(tmp_path):
    """⭐ 不变量: 内容分差 > **加成总权重**时, 加成拉满也翻不了盘（内容永远是多数派）。

    组里两条都**真的进了池**: A 靠标题（0.85 起）+ 覆盖率 1.00 ⇒ 内容满分、加成零;
    B 靠覆盖率 0.375（刚过线）⇒ 内容最低、加成拉满（今天 + sig 1.0 + 情绪 0.5 + 名字命中）。
    """
    from core.brain.read.like import PARTS, TOTAL_WEIGHT
    bonus_total = sum(p.weight for p in PARTS if not p.content)
    content_top = max(p.weight for p in PARTS if p.content)
    assert content_top > bonus_total, (content_top, bonus_total)   # 结构性: 内容是多数派
    assert TOTAL_WEIGHT == content_top + bonus_total

    q = "苔藓月亮团子中秋月饼甜点杂草屋里的热茶"                      # 19 字 ⇒ 18 个 2-gram
    body = "苔藓月亮团子中秋"                                        # 8 字 ⇒ 7 个都在 q 里
    st = _store(tmp_path, [
        _ep("m0001", "x", title=q),                                # 加成零: 无 ts、不在车道上
        _ep("m0002", body, sig=1.0, ts=_ts(0), emo=(1.0, 0.5)),    # 加成拉满
    ], edges=[("about", "m0002", "x0001")])
    ctx = build_ctx(st, query=q, now=NOW)
    node_b = st.get("m0002")
    got = part_lexical(node_b, ctx)                                # 用例把 B 钉在"刚过线"那一档
    assert got[1] == "覆盖 0.39" and 0.35 < got[0] < 0.40, (q, body, got)
    assert part_name(node_b, ctx)[0] == 1.0 and part_temporal(node_b, ctx)[0] == 1.0
    out = like(st, q, now=NOW)
    assert [c.node.id for c in out] == ["m0001", "m0002"], out


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
    for path in (LIKE_PY, PACK_PY):
        mods = _imports(path)
        bad = [m for m in mods
               if any(m == b or m.startswith(b + ".") for b in BANNED)]
        assert not bad, (path.name, bad)


def test_like_has_no_backend_at_all():
    """① 的代码形态: `like` 连"能出网的东西"都不 import（不是"没传 embed_fn"）。"""
    for path in (LIKE_PY, PACK_PY):
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
        like(st, "苔藓", now=NOW)
    hits = [r.getMessage() for r in caplog.records if "recall_like" in r.getMessage()]
    assert len(hits) == 1, hits
    assert "pool=1" in hits[0] and "cand=1" in hits[0] and "top=m0001" in hits[0]
