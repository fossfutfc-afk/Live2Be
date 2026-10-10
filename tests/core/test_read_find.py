# -*- coding: utf-8 -*-
"""`read/find.py` —— **定向寻找**（锚 → 全量集合查询）。

守门五条（每条都经**变异验红**: `.testtmp/verify_find_red.py`）:

  ① ⭐ **不漏** —— 车道上 10 条就必须出 10 条（⛔ 不是 top-k; 这是 `find` 的**唯一**不变量）
  ② **AND 是收窄** —— 两条锚的交集 ⊆ 单条锚; 空锚 = 该面上的全部
  ③ **时间**: `when` **闭区间两端都含**; 无 / 坏 `ts` 既不中 `when`, 也**垫底**
     （不许冒充"最新"）; 同输入两次**同序**
  ④ **当场炸** —— 未知锚名 `KeyError`; 值不合格 `ValueError`（不许静默少一格）
  ⑤ **零 `re` / 零后端 / 不碰旧件** —— 线索是**字面布尔树**（AST 扫）
"""
from __future__ import annotations

import ast
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brain import WikiStoreV2, make_node                     # noqa: E402
from core.brain.read.find import (ANCHORS, Clue, ClueError,        # noqa: E402
                                  compile_clue, find)

ROOT = Path(__file__).resolve().parents[2]
FIND_PY = ROOT / "core" / "brain" / "read" / "find.py"

#: 固定的"现在"（**现实日**轴; 与 `age_days` / `freshness` 同一套时区）
NOW = datetime(2026, 10, 8, 21, 0, tzinfo=timezone(timedelta(hours=8)))


def _ts(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")


def _day(days_ago: int) -> date:
    return (NOW - timedelta(days=days_ago)).date()


def _ep(nid, text, *, title="", ts="", verbatim="", tags=()):
    return make_node("episode", id=nid, text=text, title=title, ts=ts,
                     verbatim=verbatim, tags=list(tags))


def _store(tmp_path, nodes, *, edges=(), entities=(("老师", ("sensei",)),
                                                   ("杂草屋", ("秘密基地",)))):
    """小档 = 两个对象（`x0000` / `x0001`）+ 若干节点 + 边。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    for i, (name, aliases) in enumerate(entities):
        st.add(make_node("entity", id=f"x{i:04d}", name=name, aliases=list(aliases)))
    for n in nodes:
        st.add(n)
    for rel, src, dst in edges:
        st.add_edge(rel, src, dst)
    return st


def _ids(cands):
    return [c.node.id for c in cands]


# ---------------------------------------------------------------------------
# ① 不漏（find 的唯一不变量）
# ---------------------------------------------------------------------------

def test_find_returns_the_whole_lane_not_top_k(tmp_path):
    """⭐ 车道上 10 条 ⇒ **10 条全出**（`like` 会给 top-3, `find` 一条都不许漏）。"""
    nodes = [_ep(f"m{i:04d}", f"第 {i} 件事", ts=_ts(i)) for i in range(1, 11)]
    nodes += [_ep("m0011", "不在车道上的一件"), _ep("m0012", "另一件不在车道上的")]
    st = _store(tmp_path, nodes,
                edges=[("about", f"m{i:04d}", "x0000") for i in range(1, 11)])
    got = find(st, {"entity": "x0000"})
    assert len(got) == 10, _ids(got)                     # ⛔ 不是 3 条
    assert "m0011" not in _ids(got) and "m0012" not in _ids(got)
    # `find` 没有分: 恒 0（⛔ 不拿 significance 冒充）; 台账靠 `why`
    assert {c.score for c in got} == {0.0}
    assert got[0].why == "对象 x0000 老师（sensei）", got[0].why


def test_anchors_are_anded_and_empty_lane_is_empty(tmp_path):
    """两条锚 = AND（收窄）; 空车道 ⇒ `[]`（**不拿"最近的"来凑**）。"""
    st = _store(tmp_path, [
        _ep("m0001", "苔藓长在瓦片缝里", title="瓦片缝里的苔藓", ts=_ts(3)),
        _ep("m0002", "杂草屋的下午", title="杂草屋", ts=_ts(2)),
    ], edges=[("about", "m0001", "x0000"), ("about", "m0002", "x0000")])
    assert _ids(find(st, {"entity": "x0000"})) == ["m0002", "m0001"]      # 时间倒序
    assert _ids(find(st, {"entity": "x0000", "title": "杂草屋"})) == ["m0002"]
    assert find(st, {"entity": "x0001"}) == []                            # 车道是空的
    assert find(st, {"entity": "x0000", "title": "没有这条"}) == []


def test_empty_anchors_mean_the_whole_face(tmp_path):
    """空锚合法 = 该 `kinds` 面上的全部（"至少要有一个"由 `look` 那一层判）。"""
    st = _store(tmp_path, [_ep("m0001", "一件经历"),
                           make_node("belief", id="m0002", text="一个看法")])
    assert _ids(find(st, {})) == ["m0001"]                        # 缺省面 = episode
    assert _ids(find(st, {}, kinds=("belief",))) == ["m0002"]
    # `()` = **真的不过滤**（连 entity 都进）—— 由调用方负责给面
    assert _ids(find(st, {}, kinds=())) == ["m0001", "m0002", "x0000", "x0001"]


# ---------------------------------------------------------------------------
# ② 名字 / 类 / 正文
# ---------------------------------------------------------------------------

def test_title_anchor_normalizes_both_sides(tmp_path):
    """她抄回来的形式（带书名号 / 带整段元信息）都要认 —— 归一那一步是唯一的。"""
    st = _store(tmp_path, [_ep("m0001", "x", title="瓦片缝里的苔藓", ts=_ts(1))])
    for raw in ("瓦片缝里的苔藓", "《瓦片缝里的苔藓》",
                "〔《瓦片缝里的苔藓》｜3 天前｜10/5〕"):
        assert _ids(find(st, {"title": raw})) == ["m0001"], raw


def test_group_anchor_returns_all_members(tmp_path):
    """类（`experience`）⇒ **全部**成员（`member_of`: node → 类）。"""
    st = _store(tmp_path, [
        make_node("experience", id="g0001", title="和老师吃饭的日子"),
        _ep("m0001", "咖啡厅的甜点真好吃", ts=_ts(1)),
        _ep("m0002", "在家煮了面", ts=_ts(2)),
        _ep("m0003", "没进这个类", ts=_ts(3)),
    ], edges=[("member_of", "m0001", "g0001"), ("member_of", "m0002", "g0001")])
    got = find(st, {"group": "g0001"})
    assert _ids(got) == ["m0001", "m0002"], _ids(got)
    assert got[0].why == "类 《和老师吃饭的日子》", got[0].why


def test_text_anchor_sees_the_body_face(tmp_path):
    """正文面 = `pack.body_of`（主文本 + `verbatim` + **标题**）—— 与 `like` **同一份**。"""
    st = _store(tmp_path, [
        _ep("m0001", "正文里没有那两个词", title="苔藓的约定", ts=_ts(1)),
        _ep("m0002", "原话在别处", verbatim="屋顶的苔藓", ts=_ts(2)),
        _ep("m0003", "两条都不沾", ts=_ts(3)),
    ])
    assert _ids(find(st, {"text": compile_clue("苔藓")})) == ["m0001", "m0002"]


# ---------------------------------------------------------------------------
# ③ 时间与顺序
# ---------------------------------------------------------------------------

def test_when_is_closed_on_both_ends_and_skips_missing_ts(tmp_path):
    """`when` = **闭区间**（两端都含, 粒度 day）; 无 / 坏 `ts` 一概不中。"""
    st = _store(tmp_path, [
        _ep("m0001", "起点那天", ts=_ts(7)),
        _ep("m0002", "终点那天", ts=_ts(3)),
        _ep("m0003", "早一天", ts=_ts(8)),
        _ep("m0004", "晚一天", ts=_ts(2)),
        _ep("m0005", "不知道是哪天"),
        _ep("m0006", "坏 ts", ts="坏值"),
    ])
    got = _ids(find(st, {"when": (_day(7), _day(3))}))
    assert got == ["m0002", "m0001"], got          # 两端都含; 早一天/晚一天都不进


def test_order_is_time_desc_and_missing_ts_last(tmp_path):
    """**新→旧**; ⚠️ 无 `ts` 的**垫底**（时间未知不许冒充最新）; 同刻按 id。"""
    st = _store(tmp_path, [
        _ep("m0001", "不知道是哪天"),
        _ep("m0002", "前天", ts=_ts(2)),
        _ep("m0003", "今天", ts=NOW.isoformat()),
        _ep("m0004", "也是今天", ts=NOW.isoformat()),
    ])
    ids = _ids(find(st, {}))
    assert ids == ["m0003", "m0004", "m0002", "m0001"], ids
    assert ids == _ids(find(st, {}))               # 两次同序（无 rng）


# ---------------------------------------------------------------------------
# ④ 当场炸（拼错 / 值不合格不许静默少一格）
# ---------------------------------------------------------------------------

def test_unknown_anchor_and_bad_values_blow_up(tmp_path):
    st = _store(tmp_path, [_ep("m0001", "x", ts=_ts(1))])
    with pytest.raises(KeyError):
        find(st, {"titel": "x"})                   # 锚名拼错
    bad_values = [
        {"entity": "x9999"},                       # 没有这个 id
        {"entity": "m0001"},                       # 有, 但不是 entity
        {"group": "m0001"},                        # 同上（不是 experience）
        {"when": "上周"},                          # 不是 (date, date)
        {"when": (_day(1),)},                      # 少一端
        {"when": (_day(1), _day(3))},              # 端点反了（不自动交换）
        {"when": (NOW, NOW)},                      # datetime 不算（粒度只到 day）
        {"text": "苔藓"},                          # ⛔ 裸串（要 compile_clue 的产物）
        {"title": "   "},                          # 归一后为空
        {"entity": ""},
    ]
    for bad in bad_values:
        with pytest.raises(ValueError):
            find(st, bad)
    print("    锚名拼错 → KeyError; %d 种坏值 → ValueError" % len(bad_values))


# ---------------------------------------------------------------------------
# ⑤ 线索（`Clue`）—— 字面布尔树, 零 `re`
# ---------------------------------------------------------------------------

def test_clue_operators_word_forms_and_precedence():
    """四个运算符（`&&` `&` `||` `|`）都认 · 词形容错 · 空白 = AND · `&` 紧于 `|`。"""
    for raw in ("苔藓 && 杂草", "苔藓 & 杂草", "苔藓 and 杂草", "苔藓  杂草"):
        c = compile_clue(raw)
        assert c.op == "and", (raw, c.op)
        assert c.matches("苔藓和杂草") and not c.matches("只有苔藓"), raw
    for raw in ("苔藓 || 杂草", "苔藓 | 杂草", "苔藓 or 杂草"):
        c = compile_clue(raw)
        assert c.op == "or", (raw, c.op)
        assert c.matches("只有苔藓") and c.matches("只有杂草"), raw
    mix = compile_clue("苔藓 || 杂草 & 老师")       # & 紧于 | ⇒ 苔藓 OR (杂草 AND 老师)
    assert mix.matches("只有苔藓") and mix.matches("杂草和老师")
    assert not mix.matches("只有杂草")
    assert str(compile_clue("(苔藓 || 杂草) && 老师")) == "((苔藓 OR 杂草) AND 老师)"
    assert compile_clue("苔藓（屋顶）").op == "lit"   # 全角括号 = **内容**（实测正文里有）
    assert compile_clue("苔藓(屋顶)").op == "and"     # 半角括号 = 分组 ⇒ 隐式 AND


def test_clue_refuses_regex_flavoured_input():
    """⭐ 她写正则味的字符 ⇒ **明确拒**（不是静默 0 命中）—— 可归因才有救。"""
    for bad in ("", "   ", "苔藓 &", "(苔藓", "苔藓)", "苔藓 \\d", "苔藓{2}", "a[bc]*",
                "苔藓$", "^苔藓", "苔藓.*杂草"):
        with pytest.raises(ClueError):
            compile_clue(bad)


def test_clue_is_a_plain_literal_tree(tmp_path):
    """`Clue` 的判据只有 `in` —— 求值不碰 `re`（模块里也没 import 它）。"""
    src = FIND_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    mods: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0:
            mods.add((n.module or "").split(".")[0])
    assert "re" not in mods and "regex" not in mods, mods
    assert isinstance(compile_clue("苔藓"), Clue)
    assert ANCHORS["text"] is not None


# ---------------------------------------------------------------------------
# 台账（可 grep; find 印标签与标题, **不印分数**）
# ---------------------------------------------------------------------------

def test_find_writes_a_ledger_line_without_scores(tmp_path, caplog):
    st = _store(tmp_path, [_ep("m0001", "苔藓", title="苔藓的约定", ts=_ts(1))],
                edges=[("about", "m0001", "x0000")])
    with caplog.at_level("INFO", logger="core.brain.read.find"):
        find(st, {"entity": "x0000"})
    line = next(r.getMessage() for r in caplog.records if "recall_find" in r.getMessage())
    assert "spec=entity" in line and "pool=1" in line and "cand=1" in line, line
    assert "m0001←对象 x0000 老师（sensei）" in line, line
    assert ":0.000" not in line, line            # ⛔ find 没有分
    assert " k=" not in line, line               # ⛔ find 没有"要几条"
    print("    台账:", line)
