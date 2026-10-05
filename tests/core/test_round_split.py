# -*- coding: utf-8 -*-
"""R0「切分员」的**料与资格位**（L3, 2026-10-05）—— "切片即账目"的第二笔。

L1 把契约换成五行之后, `close` / 更正 / `due` 三格一直是**锁着的**: 引擎没把那份名单
交给它, 也没告诉它"今天几号"。这一笔把两只手都接上, 三件事在这里被钉住:

    ① **料**: 【本段的时间】· 【日子】· 【还开着的约定】（逐条现状行 = 她备忘录那一行
       + 尾巴那格**期限**）—— 而 **R1 的料里一个日期都没有**（正文不走绝对日期）;
    ② **资格位**: 名单同时是 `parse_split` 的**闭集**; 只有「`due` 已过 ∧ 本段没提到它」
       的那些 `span: null` 才活得下来（"没有那一刻"）—— **引擎只摆事实, 判不判在她**;
    ③ **不许猜**: 生日认不出来 ⇒ 不印那一格; `due` 不是全日期 ⇒ 当没有期限。

⚠️ 这一笔**没有**动"产表"的下游: 无区间那一行怎么进图、R1 怎么只吃有区间的行, 归 L5/L7。
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain import WikiStoreV2, make_node, notes
from core.digest.material import (_ledger_ids, _open_pinned_text, _parse_month_day,
                                  _segment_days, _segment_time_text)
from core.digest.pipeline import digest_segment
from core.session import make_event
from llm import task_labels as T
from tests import stub_tasks

CHAR = "c"
#: 本段最后一天 = **引擎眼里的"今天"**（不是机器的挂钟 —— 补跑旧段不会全判超期）
DAY = "2026-10-05"
_NOW = f"{DAY}T10:00:00+08:00"


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)


def _mmt(seq, player="老师", reply="嗯", ts=_NOW):
    """一条 MMT 内容事件（时间线 + `seq_set` 的来源）。"""
    return make_event("mmt", "chat", {"player": player, "reply": reply}, seq=seq, ts=ts)


def _note(text, *, due="", refs=("m0001",), seq=1, ts="2026-09-28T10:00:00+08:00"):
    """一条**还开着**的约定（`note/add` 事件 —— 真源是事件流, 见 `test_round_close`）。

    ⚠️ `refs` **不能空**（写侧硬门槛: 每条约定都要能指回一段经历）; 默认那个 `m0001`
    在这个库里**不存在** ⇒ 它的两条"提到"判据都不中 = 算"没提到"（正是①要的形状）。
    """
    e = notes.note_event(notes.add_op(text, list(refs), due=due))
    e.seq, e.ts = seq, ts
    return e


class _Stub:
    """按 `task` 记下每次调用的 user 串; 应答走 `stub_tasks.annotation_reply` 的标准包。

    ⚠️ **不按中文关键字分派**（`tests/core/test_stub_dispatch_guard.py` 会扫）。
    """

    def __init__(self, *, split=None, record=None, understand=None, **kw):
        self._split, self._record, self._understand = split, record, understand
        self._kw = kw
        self.tasks: list[str | None] = []
        self.users: list[str] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.tasks.append(task)
        self.users.append("\n".join(str(m.get("content") or "") for m in messages
                                    if m.get("role") == "user"))
        if task == T.DIGEST_RECORD and self._record is not None:
            return self._record
        if task == T.DIGEST_UNDERSTAND and self._understand is not None:
            return self._understand
        reply = stub_tasks.annotation_reply(task, messages, split=self._split, **self._kw)
        if reply is None:
            raise AssertionError(f"桩不认识 task={task!r}")
        return reply

    def user_of(self, task: str) -> str:
        return self.users[self.tasks.index(task)]


# ---------------------------------------------------------------------------
# ① 料: 本段的时间 · 日子
# ---------------------------------------------------------------------------

def test_segment_time_is_a_range_and_a_single_day_is_one_date():
    """【本段的时间】= 段内事件 `ts` 的范围; 单日**只印一个**（不给单点范围）。"""
    two = [_mmt(1, ts="2026-10-03T09:00:00+08:00"), _mmt(2)]
    assert _segment_days(two) == [date(2026, 10, 3), date(2026, 10, 5)]
    assert _segment_time_text(_segment_days(two)) == "2026-10-03 ~ 2026-10-05"
    one = [_mmt(1)]
    assert _segment_days(one) == [date(2026, 10, 5)]
    assert _segment_time_text(_segment_days(one)) == "2026-10-05"
    assert _segment_time_text([]) == ""


def test_month_day_parser_eats_both_real_formats():
    """真机两种格式并存（`5/13` 与 `5月13日`）—— **一个解析器吃完**; 认不出 ⇒ None。

    ⚠️ 绝不猜: 猜错一天 = 误判一次失约（这是这条链上最坏的错）。
    """
    assert _parse_month_day("5/13") == (5, 13)
    assert _parse_month_day("5月13日") == (5, 13)
    assert _parse_month_day("05-13") == (5, 13)
    for bad in ("", "5/32", "2/30", "13/5/2026", "五月十三", "下周"):
        assert _parse_month_day(bad) is None, bad


# ---------------------------------------------------------------------------
# ② 料: 还开着的约定（行格式 + 期限那格三态）
# ---------------------------------------------------------------------------

def test_ledger_line_carries_the_deadline_in_three_wordings():
    """三种措辞说的是**三件事** —— 混成一件, 模型就会把"还没到"当成"已经黄了"。"""
    items = [
        notes.NoteItem(id="n3", text="生日那天一起去吃蛋糕", refs=["m0001"],
                       since="2026-10-02T10:00:00+08:00", due="2026-10-01"),
        notes.NoteItem(id="n7", text="周六去模型店", refs=[],
                       since="2026-10-04T10:00:00+08:00", due="2026-10-05"),
        notes.NoteItem(id="n1", text="带老师看瓦片缝的苔藓", refs=[],
                       since="2026-09-23T10:00:00+08:00"),
    ]
    lines = _open_pinned_text(items, now=_NOW, today=date(2026, 10, 5),
                              first_day=date(2026, 10, 3)).splitlines()
    assert len(lines) == 3
    # 陈年旧账（在段开始之前就到期了）
    assert lines[0].startswith("- n3 生日那天一起去吃蛋糕") and "记于 3 天前" in lines[0]
    assert "期限 2026-10-01（已过 4 天）" in lines[0], lines[0]
    # 本段期间到期（原文就在它手边 —— 判据与上面那条不同）
    assert "期限 2026-10-05（本段期间到期）" in lines[1], lines[1]
    # 没有期限 ⇒ 永不过期
    assert "期限 —（没有期限）" in lines[2], lines[2]
    # ⚠️ R4 那份（不给 today）**一个字都不多印** —— 它不看日期
    assert "期限" not in _open_pinned_text(items)


# ---------------------------------------------------------------------------
# ③ 资格位: 超期 ∧ 本段没提到它
# ---------------------------------------------------------------------------

def test_qualification_gate_needs_overdue_and_unmentioned(tmp_path):
    """闭集 = 名单里每一条; 资格位 = 其中**超期且本段没提到**的（宁可不判"提到"）。"""
    st = _store(tmp_path)
    # m0001 的 seq 在**本段**里（结构命中）; m0002 只有 tags 撞上时间线（词面命中）
    st.add(make_node("episode", text="模型店门口", event_seq=[3], tags=["模型店"],
                     ts=_NOW))
    st.add(make_node("episode", text="瓦片缝里的苔藓", event_seq=[9], tags=["苔藓"],
                     ts="2026-09-20T10:00:00+08:00"))
    items = [
        notes.NoteItem(id="n1", text="模型店那次", refs=["m0001"], due="2026-10-01"),
        notes.NoteItem(id="n2", text="苔藓的事", refs=["m0002"], due="2026-10-01"),
        notes.NoteItem(id="n3", text="生日蛋糕", refs=["m9999"], due="2026-10-01"),
        notes.NoteItem(id="n4", text="还没到的", refs=[], due="2026-12-01"),
        notes.NoteItem(id="n5", text="永远开着", refs=[]),
    ]
    note_ids, overdue = _ledger_ids(st, items, seq_set={3, 4},
                                    timeline="[3] 老师: 今天又路过那片苔藓了",
                                    today=date(2026, 10, 5))
    assert note_ids == {"n1", "n2", "n3", "n4", "n5"}, "闭集 = 名单每一条"
    # n1/n2 被本段提到 ⇒ 不发资格位; n4 没超期 / n5 没期限 ⇒ 也永远不发
    assert overdue == {"n3"}, overdue


# ---------------------------------------------------------------------------
# ④ 端到端: 料进了 R0 的 user 串（而 R1 一个字日期都没有）
# ---------------------------------------------------------------------------

def test_r0_material_carries_the_ledger_but_r1_gets_no_dates(tmp_path):
    """没有这一段, `close` / 更正 / `due` 三格全是死的（L1 之后一直锁着）。"""
    st = _store(tmp_path)
    llm = _Stub(split={"segments": [{"span": [3, 3], "abstract": "路过模型店"}]})
    res = digest_segment(st, llm, [_note("周六去模型店", due="2026-10-01"), _mmt(3)])
    assert res.ok, res.errors

    r0 = llm.user_of(T.DIGEST_SPLIT)
    assert "【本段的时间】" in r0 and DAY in r0, r0
    assert "【日子】" in r0 and "节日：" in r0, r0          # 节日表整张印
    assert "【还开着的约定】" in r0 and "- n1 周六去模型店" in r0, r0
    assert "期限 2026-10-01（已过 4 天）" in r0, r0

    # ⚠️ **日期只给 R0** —— R1 写正文, 正文里出现绝对日期会与"剧情里不走绝对日期"打架
    r1 = llm.user_of(T.DIGEST_RECORD)
    assert "【本段的时间】" not in r1 and DAY not in r1, r1
    assert "【本段骨架】" in r1, r1


# ---------------------------------------------------------------------------
# ⑤ 端到端: 资格位真的绑到了契约上（发 ⇒ 活; 不发 ⇒ 丢弃）
# ---------------------------------------------------------------------------

_SPAN_NULL = {"segments": [{"span": None, "abstract": "生日那天, 老师没有来",
                            "state": "close", "id": "n1", "title": "生日那天",
                            "significance": 0.9}]}


def test_span_null_survives_only_when_the_engine_sent_the_qualification(tmp_path):
    """引擎**只摆事实**: 资格位发了那条 `span: null` 才活得下来, 没发就当场丢。"""
    # ① 超期 + 本段没提到它 ⇒ 发资格位 ⇒ 活
    st = _store(tmp_path / "a")
    res = digest_segment(st, _Stub(split=_SPAN_NULL),
                         [_note("生日蛋糕", due="2026-10-01"), _mmt(3)])
    assert res.ok, res.errors
    assert not [w for w in res.contract_warnings if "资格位没发" in w], res.contract_warnings

    # ② 本段**提到它**了（它的出生经历就在这一段里）⇒ 不发资格位 ⇒ 丢弃
    st2 = _store(tmp_path / "b")
    st2.add(make_node("episode", text="生日蛋糕", event_seq=[3], ts=_NOW))
    res2 = digest_segment(st2, _Stub(split=_SPAN_NULL),
                          [_note("生日蛋糕", due="2026-10-01", refs=["m0001"]), _mmt(3)])
    assert res2.ok, res2.errors
    assert [w for w in res2.contract_warnings if "资格位没发" in w], res2.contract_warnings


def test_close_id_must_come_from_the_list_the_engine_printed(tmp_path):
    """**闭集 = 料里印出来的那份名单** —— 编一个编号写 `close` ⇒ 降级成普通一行。"""
    def _close(nid):
        return {"segments": [{"span": [3, 3], "abstract": "我把团子带来了",
                              "state": "close", "id": nid}]}

    ok = digest_segment(_store(tmp_path / "ok"), _Stub(split=_close("n1")),
                        [_note("团子的事"), _mmt(3)])
    assert ok.ok and not [w for w in ok.contract_warnings if "名单里" in w], \
        ok.contract_warnings

    bad = digest_segment(_store(tmp_path / "bad"), _Stub(split=_close("n9")),
                         [_note("团子的事"), _mmt(3)])
    assert bad.ok, bad.errors
    assert [w for w in bad.contract_warnings if "名单里" in w], bad.contract_warnings


# ---------------------------------------------------------------------------
# ⑥ 端到端: 同一个 span 两行 = 两条记忆（L4 —— 覆盖按集合, 不许误合）
# ---------------------------------------------------------------------------

def test_the_same_span_twice_is_two_memories(tmp_path):
    """⭐ §1.3 **出 + 进 = 两行 = 两条记忆** —— `_find_duplicate` 不许把它们合掉。

    （去重键 = kind + `event_seq` **相交** + **正文全等** ⇒ 正文不同就是两条。）
    """
    split = {"segments": [
        {"span": [3, 3], "abstract": "我把团子带来了", "state": "close", "id": "n1"},
        {"span": [3, 3], "abstract": "顺便又约了下周"}]}
    record = {"episodes": [{"text": "我把团子带来了", "title": "团子", "tags": ["团子"]},
                           {"text": "顺便又约了下周", "title": "又约了下周",
                            "tags": ["约定"]}]}
    understand = {"decisions": [{"episode": "m0001", "decision": "add", "kind": "belief",
                                 "subject": "sensei", "text": "团子这件事我记住了"},
                                {"episode": "m0002", "decision": "add", "kind": "belief",
                                 "subject": "sensei", "text": "下周那件事我记住了"}],
                  "evidence": [], "affection_exp_delta": 0}
    st = _store(tmp_path)
    res = digest_segment(st, _Stub(split=split, record=record, understand=understand),
                         [_note("团子的事"), _mmt(3)])
    assert res.ok, res.errors
    eps = [n for n in (st.get(i) for i in res.created) if n.kind == "episode"]
    assert len(eps) == 2, f"同一个 span 的两行必须是两条记忆: {res.created}"
    assert sorted(tuple(n.event_seq) for n in eps) == [(3,), (3,)]
    print("    同 span 两行: 两条 episode 都在（没被当重复合掉）✓")
