# -*- coding: utf-8 -*-
"""`notes.py` —— 随身笔记的**折叠 / 校验 / 渲染**（链路 ①-第二步, 2026-09-23）。

覆盖**纯函数层**: 操作事件 → `NotesState` → 注入块。
（`soul/notes.json` 的落盘与引擎注入是后续步骤, 不在这里。）

纪律都钉在这里: `close` 必须给理由 · `id` 只增不复用 · `rewrite` 只碰 B 类槽 ·
`refs` 悬空只告警 · 上限只告警 · 频次不进注入。
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain import notes
from core.session import make_event
from core.session.events import N_ADD, N_CLOSE, N_RETIRE, N_REWRITE, TYPE_NOTE

NOW = datetime(2026, 9, 23, 12, 0, 0)
T0 = "2026-09-20T21:04:11+09:00"          # 3 天前
T1 = "2026-09-22T09:00:00+09:00"          # 昨天


def _ev(seq, sub, payload, ts=T0):
    return make_event(TYPE_NOTE, sub, payload, seq=seq, ts=ts)


def _add(seq, text="周六模型店", refs=("m0009",), ts=T0, due=""):
    p = {"text": text, "refs": list(refs)}
    if due:
        p["due"] = due
    return _ev(seq, N_ADD, p, ts=ts)


def _mmt(seq):
    """一条非 note 事件（折叠必须无视它）。"""
    return make_event("mmt", "chat", {"player": "在吗", "reply": "在的"}, seq=seq, ts=T0)


# ---------------------------------------------------------------------------
# 折叠: add / close
# ---------------------------------------------------------------------------

def test_incremental_fold_equals_full_fold():
    """增量折叠（给 base）与全量重折**结果相同** —— 这是"缓存可重建"的依据。"""
    events = [_add(1), _mmt(2), _add(3, text="还他笔记", refs=("m0011",), ts=T1)]

    full = notes.fold(events)
    half = notes.fold(events[:2])
    incr = notes.fold(events, base=half)

    assert incr.to_dict() == full.to_dict()
    # 已经折过的事件再折一次 = 不动（水位幂等）
    assert notes.fold(events, base=full).to_dict() == full.to_dict()


def test_close_keeps_the_item_and_retire_removes_it():
    """⭐ 两段式: **结清 ≠ 划掉** —— 结清后条目仍在块里, 图侧接住才 `retire`。"""
    st = notes.fold([
        _add(1),                                                    # n1
        _ev(2, N_CLOSE, {"id": "n1", "afterwards": "周六去了模型店"}, ts=T1),
    ])

    assert [it.id for it in st.promise] == ["n1"]        # **还在**（不变量: 至少一个可见面）
    assert st.promise[0].closed is True
    assert st.promise[0].afterwards == "周六去了模型店"
    assert st.promise[0].text == "周六模型店"             # 文本没丢 ⇒ 固化要用它
    assert "n1" in notes.render_note_block(st, now=NOW)  # 注入块里照旧看得见

    st = notes.fold([_ev(3, N_RETIRE, {"id": "n1"})], base=st)
    assert st.promise == []                              # 图里已经有了 ⇒ 这才划掉
    assert st.next_n == 2                                # 号照旧只增不复用


def test_retire_only_applies_to_closed_items(caplog):
    """退场一条**还开着**的承诺 = 把它从唯一落脚点删掉（图里根本没有它）⇒ 拒。"""
    st = notes.fold([_add(1), _ev(2, N_RETIRE, {"id": "n1"})])
    assert [it.id for it in st.promise] == ["n1"]
    assert "还开着" in caplog.text

    # 没结清过的 id / 根本不存在的 id → 只告警
    assert notes.fold([_ev(3, N_RETIRE, {"id": "n99"})], base=st).promise != []
    with pytest.raises(ValueError, match="retire 缺 id"):
        notes.retire_op("  ")


def test_second_close_does_not_overwrite_what_came_after(caplog):
    """块里印着 id ⇒ 必须防"二次 close 用幻觉理由覆盖真实理由"。"""
    st = notes.fold([
        _add(1),
        _ev(2, N_CLOSE, {"id": "n1", "afterwards": "真的去了"}, ts=T1),
        _ev(3, N_CLOSE, {"id": "n1", "afterwards": "其实没去"}, ts=T1),
    ])
    assert st.promise[0].afterwards == "真的去了"
    assert "不覆盖" in caplog.text


def test_close_without_afterwards_applies_but_is_loud(caplog):
    """**写侧拒, 读侧照做**: 事件说的就是"这条不再开着了", 不认它会让本子停在过去。"""
    st = notes.fold([_add(1), _ev(2, N_CLOSE, {"id": "n1"})])
    assert st.promise[0].closed is True and st.promise[0].afterwards == ""
    assert st.promise[0].state == ""                    # 旧事件没 state → 用中性兜底渲染

    # 写侧硬门槛（`close` 必须给理由 + 给结局; `add` / `retire` 不用）
    with pytest.raises(ValueError, match="缺 afterwards"):
        notes.close_op("n1", "   ", "kept")
    with pytest.raises(ValueError, match="state 非法"):
        notes.close_op("n1", "去了", "done")
    assert notes.add_op("周六模型店", ["m0009"])["action"] == N_ADD
    assert notes.retire_op("n1") == {"action": N_RETIRE, "id": "n1"}


def test_add_rejects_missing_refs_on_read_side(caplog):
    st = notes.fold([_ev(1, N_ADD, {"text": "没有引用的条目"})])
    assert st.promise == []                           # 残缺操作不折进去（但记事）
    assert notes.check(notes.fold([_add(1)])) == []   # 正常条目零告警


# ---------------------------------------------------------------------------
# 折叠: rewrite（B 类整段替换）
# ---------------------------------------------------------------------------

def test_next_n_guard_prevents_id_reuse():
    """护栏: `next_n` 落后于现有 id（手工构造 / 旧档推错）时也不会发出重号。"""
    st = notes.NotesState(next_n=1, promise=[notes.NoteItem(id="n7", text="老条目")])
    assert st.next_n == 8
    assert notes.fold([_ev(1, N_ADD, {"text": "新条目", "refs": ["m1"]})],
                      base=st).promise[-1].id == "n8"


def test_on_mind_is_one_idless_prose_line():
    st = notes.fold([_ev(1, N_REWRITE, {"on_mind": {"text": "最近在想的那件事",
                                                    "refs": ["m2"]}}, ts=T0)])
    assert st.on_mind is not None
    assert st.on_mind.id == ""                        # 单条散文: **不发号**（没人会 close 它）
    assert st.on_mind.since == T0

    # 正文没变 → 保住"第一次这么想"的时刻; 变了 → 重新计时
    st2 = notes.fold([_ev(2, N_REWRITE, {"on_mind": {"text": "最近在想的那件事",
                                                     "refs": ["m2"]}}, ts=T1)], base=st)
    assert st2.on_mind.since == T0
    st3 = notes.fold([_ev(3, N_REWRITE, {"on_mind": {"text": "换了一件事",
                                                     "refs": ["m3"]}}, ts=T1)], base=st2)
    assert st3.on_mind.since == T1 and st3.on_mind.id == ""


def test_rewrite_accepts_bare_string_on_mind():
    st = notes.fold([_ev(1, N_REWRITE, {"on_mind": "就写一句话"})])
    assert st.on_mind is not None and st.on_mind.text == "就写一句话"
    assert st.on_mind.refs == []                      # 缺 refs → 交给 check 告警（折叠不拒）


# ---------------------------------------------------------------------------
# 写侧: 唯一出口
# ---------------------------------------------------------------------------

def test_note_event_is_a_registered_event():
    from core.session.events import Event

    ev = notes.note_event(notes.add_op("周六模型店", ["m0009"], due="2026-09-26"))
    assert (ev.type, ev.subtype) == (TYPE_NOTE, N_ADD)
    assert ev.payload == {"text": "周六模型店", "refs": ["m0009"], "due": "2026-09-26"}
    assert "action" not in ev.payload                 # action 已抬成 subtype
    ev.seq = 7                                        # seq 由 store 分配（from_dict 要求 ≥1）
    assert Event.from_dict(ev.to_dict()) is not None  # 登记过的类型才读得回来

    ev2 = notes.note_event(notes.rewrite_op(on_mind="一句话"))
    assert ev2.subtype == N_REWRITE and ev2.payload == {"on_mind": "一句话"}


# ---------------------------------------------------------------------------
# 读侧: 告警（不阻断）
# ---------------------------------------------------------------------------

def test_check_reports_dangling_refs_missing_refs_and_caps():
    st = notes.fold([_add(1, text="第一条", refs=("m0009",)),
                     _add(2, text="第二条", refs=("m9999",), ts=T1)])

    assert notes.check(st, known={"m0009", "m9999"}) == []      # 都指得到
    problems = notes.check(st, known={"m0009"})
    assert len(problems) == 1 and "m9999" in problems[0]

    # 没有 known → 只查"有没有 refs"（不查世界）
    st_bare = notes.NotesState(promise=[notes.NoteItem(text="无引用", since=T0)])
    assert any("没有 refs" in p for p in notes.check(st_bare))

    # 上限: 只告警, 不截断
    many = notes.fold([_add(i, text=f"第{i}条", refs=("m0009",)) for i in range(1, 8)])
    assert len(many.promise) == 7
    assert any("超上限" in p for p in notes.check(many))

    # 正文超长: 该写名词短语, 不写陈述句
    long_text = notes.fold([_add(1, text="约好" * 11)])         # 22 字 > MAX_TEXT(20)
    assert any("名词短语" in p for p in notes.check(long_text))


def test_check_caps_count_only_open_items_and_flag_closed_backlog():
    """"结清未退场"是**正常态**（固化的待办队列）⇒ 不逐条报, 只在积压时报。"""
    # 5 条开着 + 2 条结清: 没超上限（上限只算开着的）, 积压也没到线
    st = notes.fold([_add(i, text=f"第{i}条", refs=("m0009",)) for i in range(1, 6)] +
                    [_ev(6, N_CLOSE, {"id": "n1", "afterwards": "做完了"}),
                     _ev(7, N_CLOSE, {"id": "n2", "afterwards": "不做了"})])
    assert notes.check(st) == []

    # 积压超过 MAX_CLOSED_PENDING → 报一句（说明收口/固化没跑到）
    st = notes.fold([_ev(8, N_CLOSE, {"id": "n3", "afterwards": "做完了"}),
                     _ev(9, N_CLOSE, {"id": "n4", "afterwards": "做完了"})], base=st)
    problems = notes.check(st)
    assert len(problems) == 1 and "结清未退场积压" in problems[0]


# ---------------------------------------------------------------------------
# 渲染: 注入块
# ---------------------------------------------------------------------------

def test_render_skips_empty_slots_entirely():
    """空槽**不印抬头** —— 常驻预算的每一行都要有内容。"""
    only_promise = notes.render_note_block(notes.fold([_add(1)]), now=NOW)
    assert notes.GROUP_LEADS[notes.SLOT_PROMISE] in only_promise
    assert notes.GROUP_LEADS[notes.SLOT_ON_MIND] not in only_promise

    only_mind = notes.render_note_block(
        notes.fold([_ev(1, N_REWRITE, {"on_mind": "只有这句"}, ts=T0)]), now=NOW)
    assert only_mind.splitlines()[1] == "  · 最近在想"


def test_render_closed_items_after_open_ones_with_neutral_word():
    """开着的在前（这个块先回答"我手上还开着什么"）; 结清行尾巴 = **中性状态词 + 理由**。"""
    st = notes.fold([
        _add(1, text="周六模型店", refs=("m0009",)),
        _add(2, text="还他笔记", refs=("m0011",), ts=T1),
        _add(3, text="买花", refs=("m0014",)),                        # 更老的约定
        _ev(4, N_CLOSE, {"id": "n3", "afterwards": "送出去了", "state": "kept"}, ts=T0),   # 早结清
        _ev(5, N_CLOSE, {"id": "n1", "afterwards": "那天我忘了", "state": "broken"}, ts=T1),
    ])
    lines = notes.render_note_block(st, now=NOW).splitlines()

    assert lines[1] == "  · 你自己记下的约定"
    assert lines[2] == "    n2 还他笔记  ← 记于 昨天"          # 开着的在前
    assert lines[3] == "    n1 周六模型店  ← 没做到（那天我忘了）"   # 结清组按结清时刻
    assert lines[4] == "    n3 买花  ← 已兑现（送出去了）"
    assert "已完成" not in "".join(lines)      # 光板"已完成"对失约是假话 ⇒ 按 state 分说法

    # 没理由 / 没 state（旧事件）→ 中性兜底, 不印空括号
    bare = notes.fold([_add(1), _ev(2, N_CLOSE, {"id": "n1"})])
    assert notes.render_note_block(bare).splitlines()[2] == "    n1 周六模型店  ← 已结清"


def test_render_superseded_tail():
    """被取代也算结清 —— 三种 state 各有说法（用户 2026-09-25 定）。"""
    st = notes.fold([_add(1),
                     _ev(2, N_CLOSE, {"id": "n1", "afterwards": "改成一起整理",
                                      "state": "superseded"}, ts=T1)])
    assert notes.render_note_block(st).splitlines()[2] \
        == "    n1 周六模型店  ← 被新的取代了（改成一起整理）"


def test_render_is_empty_when_nothing_is_noted():
    assert notes.render_note_block(notes.NotesState(), now=NOW) == ""
    assert notes.render_note_block(notes.fold([_mmt(1)]), now=NOW) == ""


def test_render_without_now_omits_time_phrase():
    """`now` 缺席 → 不编一个"很久以前"（哨兵纪律, 同 `marks.relative`）。"""
    st = notes.fold([_add(1)])
    assert notes.render_note_block(st, now=None).splitlines()[2] == "    n1 周六模型店"


def test_render_survives_broken_since():
    """坏 `since` → 时间短语整段不印；**没给 `titles` 就不印 refs**（N4a）。

    ⚠️ refs 从"印编号"改成"印名字"，而名字靠调用方从图上取好传进来
    （本模块纯函数零 IO）—— 拿不到映射时**整段不印**：印一个 `m1` 她读不懂，
    还违反"编号退回引擎内部"。
    """
    st = notes.NotesState(promise=[notes.NoteItem(id="n1", text="条目",
                                                  refs=["m1"], since="不是时间")])
    assert notes.render_note_block(st, now=NOW).splitlines()[2] == "    n1 条目"
    with_titles = notes.render_note_block(st, now=NOW, titles={"m1": "模型店的午后"})
    assert with_titles.splitlines()[2] == "    n1 条目 (《模型店的午后》)"


# ---------------------------------------------------------------------------
# 序列化（`soul/notes.json` 的形状; 落盘在下一步）
# ---------------------------------------------------------------------------

def test_slots_and_constants_are_consistent():
    """A/B 二分 = "同一段只有一个写者"的实现, 别让某个槽同时落在两边。

    ⚠️ N4a（2026-09-29）: 第三槽 `habits` 已退役 ⇒ 只剩 `promise`（A）与 `on_mind`（B）。
    """
    assert notes.SLOTS == (notes.SLOT_PROMISE, notes.SLOT_ON_MIND)
    assert set(notes.OPSLOTS) & set(notes.SNAPSHOT_SLOTS) == set()
    assert set(notes.OPSLOTS) | set(notes.SNAPSHOT_SLOTS) == set(notes.SLOTS)
    assert (notes.MAX_PROMISE, notes.MAX_ON_MIND) == (5, 1)
    assert not hasattr(notes, "MAX_HABITS") and not hasattr(notes, "SLOT_HABITS")
    assert logging.getLogger("core.brain.notes") is not None
