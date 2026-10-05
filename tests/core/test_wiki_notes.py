# -*- coding: utf-8 -*-
"""`notes.py` —— 随身笔记的**折叠 / 校验 / 渲染**（链路 ①-第二步, 2026-09-23）。

覆盖**纯函数层**: 操作事件 → `NotesState` → 注入块。
（`soul/notes.json` 的落盘与引擎注入是后续步骤, 不在这里。）

纪律都钉在这里: **`close` = 划掉即移除**（2026-10-05 两段式合并）· `update` 只改
`due`/`text` · `id` 只增不复用 · `refs` 悬空只告警 · 上限只告警 · 频次不进注入。
⛔ N4e（2026-09-29）: `on_mind` 槽退役 ⇒ "`rewrite` 只碰 B 类槽"这条纪律连同
二分一起消失, 旧 `rewrite` 事件被**静默吞掉**（动作名留着, 见 `fold`）。
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain import notes
from core.session import make_event
from core.session.events import N_ADD, N_CLOSE, N_RETIRE, N_REWRITE, N_UPDATE, TYPE_NOTE

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


def test_close_removes_the_item_in_all_three_outcomes():
    """⭐ 2026-10-05: `close` = **划掉即移除**（两段式合并成一步）。

    三种结局（兑现 / 失约 / 被取代）**一律移除** —— 结局与"后来怎么了"改由
    **图里那条经历**承担; 本子只留"还开着的"（当前抽屉, 不是账簿）。
    """
    for outcome in ("kept", "broken", "superseded", ""):
        st = notes.fold([
            _add(1),                                                    # n1
            _ev(2, N_CLOSE, {"id": "n1", "state": outcome, "afterwards": "后来…"}),
        ])
        assert st.pinned == [], outcome
        assert st.next_n == 2                                    # 号照旧只增不复用
        assert "n1" not in notes.render_note_block(st, now=NOW)


def test_old_archive_retire_means_the_same_thing_as_close(caplog):
    """旧档里的 `retire` 与 `close` **同义**（2026-10-05 合并）—— 读侧必须照旧认它。"""
    st = notes.fold([_add(1), _ev(2, N_RETIRE, {"id": "n1"})])
    assert st.pinned == []
    # 指不到的 id（已划掉 / 根本不存在）⇒ 只告警, 不抛
    st2 = notes.fold([_add(1), _ev(2, N_RETIRE, {"id": "n99"})])
    assert [it.id for it in st2.pinned] == ["n1"]
    assert "指不到" in caplog.text


def test_close_of_a_gone_item_only_warns(caplog):
    """二次 close / 指不到的 id ⇒ 告警 + 跳过（不会复活, 也不会报错）。"""
    st = notes.fold([
        _add(1),
        _ev(2, N_CLOSE, {"id": "n1", "afterwards": "真的去了"}, ts=T1),
        _ev(3, N_CLOSE, {"id": "n1", "afterwards": "其实没去"}, ts=T1),
    ])
    assert st.pinned == []
    assert "指不到" in caplog.text


def test_close_op_only_needs_an_id():
    """`close` 只要 `id` —— `afterwards` / `state` **不再进 op**（2026-10-05）:
    结局由图里那条经历承担, 而"后来怎么了"仍进 evolution 日志（审计账）。"""
    assert notes.close_op("n1") == {"action": N_CLOSE, "id": "n1"}
    assert notes.add_op("周六模型店", ["m0009"])["action"] == N_ADD
    with pytest.raises(ValueError, match="close 缺 id"):
        notes.close_op("   ")
    # ⛔ `retire_op` 已删（写侧零写者, 且与 `close` 同义）
    assert not hasattr(notes, "retire_op")


def test_update_fixes_the_date_and_the_sentence():
    """`update` 只改两样: `due` 与 `text`（"日期后来才知道"的唯一出口）。"""
    st = notes.fold([_add(1)])                                   # n1, 无 due
    st = notes.fold([_ev(2, N_UPDATE, {"id": "n1", "due": "2026-05-13"})], base=st)
    assert st.pinned[0].due == "2026-05-13"
    assert st.pinned[0].text == "周六模型店"                     # 其余不动
    st = notes.fold([_ev(3, N_UPDATE, {"id": "n1", "text": "生日那天"})], base=st)
    assert (st.pinned[0].text, st.pinned[0].due) == ("生日那天", "2026-05-13")

    # 指不到 id ⇒ 只告警; "一样都没给" / 缺 id ⇒ 写侧直接拒
    st2 = notes.fold([_ev(4, N_UPDATE, {"id": "n99", "due": "2026-01-01"})], base=st)
    assert [it.id for it in st2.pinned] == ["n1"]
    with pytest.raises(ValueError, match="至少要改一样"):
        notes.update_op("n1")
    with pytest.raises(ValueError, match="update 缺 id"):
        notes.update_op("  ", due="2026-01-01")


def test_legacy_closed_item_in_the_cache_is_not_resurrected():
    """旧 `notes.json` 里带 `closed_at` 的条目 = **已经划掉的** ⇒ 不进状态。

    新口径下本子只留开着的; 放它进来, 它就会以"还开着"的样子重新出现
    （而派生缓存本该能从事件流重建出同样的结果）。
    """
    legacy = notes.NotesState.from_dict({
        "up_to_seq": 9, "next_n": 3,
        "pinned": [{"id": "n1", "text": "还开着的", "refs": ["m0009"], "since": T0},
                   {"id": "n2", "text": "早就划掉的", "refs": ["m0009"], "since": T0,
                    "closed_at": T1, "afterwards": "去过了", "state": "kept"}]})
    assert [it.id for it in legacy.pinned] == ["n1"]


def test_add_rejects_missing_refs_on_read_side(caplog):
    st = notes.fold([_ev(1, N_ADD, {"text": "没有引用的条目"})])
    assert st.pinned == []                           # 残缺操作不折进去（但记事）
    assert notes.check(notes.fold([_add(1)])) == []   # 正常条目零告警


# ---------------------------------------------------------------------------
# 折叠: rewrite（B 类整段替换）
# ---------------------------------------------------------------------------

def test_next_n_guard_prevents_id_reuse():
    """护栏: `next_n` 落后于现有 id（手工构造 / 旧档推错）时也不会发出重号。"""
    st = notes.NotesState(next_n=1, pinned=[notes.NoteItem(id="n7", text="老条目")])
    assert st.next_n == 8
    assert notes.fold([_ev(1, N_ADD, {"text": "新条目", "refs": ["m1"]})],
                      base=st).pinned[-1].id == "n8"


def test_rewrite_event_is_a_silent_noop_after_retirement():
    """⛔ N4e（2026-09-29）: `on_mind` 槽退役 ⇒ 旧 `rewrite` 事件**静默吞掉**。

    判据不是"零读者"而是**时间尺度**（用户: *"它太煽情了, 煽情的剧情过去了,
    就不必一直耿耿于怀了"*）。⚠️ 但**动作名不能删** —— 真机 seq 263 那条
    `note/rewrite` 躺在事件流里, 落到 else 分支会打一条永远修不掉的"未知操作"告警。
    """
    st = notes.fold([_ev(1, N_REWRITE, {"on_mind": {"text": "最近在想的那件事",
                                                    "refs": ["m2"]}}, ts=T0),
                     _ev(2, N_ADD, {"text": "周六模型店", "refs": ["m0009"]}, ts=T1)])
    assert not hasattr(st, "on_mind")                    # 状态里没有这个字段了
    assert [it.id for it in st.pinned] == ["n1"]          # 后面的 add 照常折进来
    assert st.up_to_seq == 2                              # 水位照样推进（吞 = 处理过了）


def test_rewrite_is_not_writable_anymore():
    """写侧: `rewrite` 与它的构造器一起退役（留着就是一条往空槽里写的静默写路）。"""
    assert not hasattr(notes, "rewrite_op")
    assert not hasattr(notes, "SLOT_ON_MIND")
    assert not hasattr(notes, "SNAPSHOT_SLOTS")
    with pytest.raises(ValueError):
        notes.validate_ops([{"action": N_REWRITE, "on_mind": "一句话"}])


def test_legacy_key_is_ignored_on_read():
    """旧档（`notes.json`）里的 `on_mind` 键**直接忽略** —— 不迁移、不报错、不留档。"""
    st = notes.NotesState.from_dict({
        "up_to_seq": 5, "next_n": 2,
        "pinned": [{"text": "周六模型店", "refs": ["m0009"], "id": "n1"}],
        "on_mind": {"text": "我给瓦片留了缝", "refs": ["m0014"]},
    })
    assert [it.id for it in st.pinned] == ["n1"]
    assert not hasattr(st, "on_mind")
    # 存回去时那个键**不再出现**（下次 save 自动把旧档改写掉）
    assert "on_mind" not in st.to_dict()


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
    st_bare = notes.NotesState(pinned=[notes.NoteItem(text="无引用", since=T0)])
    assert any("没有 refs" in p for p in notes.check(st_bare))

    # 总量上限（⭐ 2026-09-29 换判据: 条数不再是判据, 管的是**注入块多长**）
    long_block = notes.fold([_add(i, text=f"第{i}条" + "长" * 15, refs=("m0009",))
                             for i in range(1, 17)])
    assert len(long_block.pinned) == 16
    assert any("备忘录太长" in p for p in notes.check(long_block))
    # 也可以由调用方把已经渲过的长度传进来（省一次渲染）
    assert any("备忘录太长" in p for p in
               notes.check(st, block_chars=notes.MAX_NOTE_CHARS + 1))

    # ⛔ 正文长度**不再是**体检判据（2026-10-05 删）—— 它必然恒响（3b-3 起 note 正文 =
    #    切片的 abstract, 契约上限 60 > 20）, 只会制造噪音; 长度真源 = 契约层 `ABSTRACT_MAX`
    long_text = notes.fold([_add(1, text="约好" * 11)])          # 22 字
    assert not any("名词短语" in p for p in notes.check(long_text))

    # ⛔ ~~快照槽用自己的标尺~~ **N4e（2026-09-29）取消** —— `on_mind` 退役后
    # 槽收成一个, "按槽分标尺"那套机制一起删（判据: 没读者就删）。现在只有一个标尺。


def test_stats_is_a_ledger_not_a_warning():
    """⭐ **台账与告警是两件事**（L9, 2026-10-05）。

    `check()` 答"哪里不对"; `stats()` 答"现在多少" —— 后者**永远有值**,
    混进 `check()` 就会让每个正常段都多一条 WARNING（告警就没人看了）。
    设计 §9-5 的裁决: **先只记数、不拍上限**（开着的条数 = 每轮料的成本）。
    """
    empty = notes.NotesState()
    assert notes.stats(empty) == {"open": 0, "block_chars": 0}
    assert notes.check(empty) == []

    st = notes.fold([_add(1, text="周六模型店", refs=("m0009",)),
                     _add(2, text="还他笔记", refs=("m0009",), ts=T1)])
    assert notes.stats(st)["open"] == 2
    assert notes.stats(st)["block_chars"] == len(notes.render_note_block(st))
    # 开着的条目**本身不产生告警**（它不是问题 —— 本子就是装这个的）
    assert notes.check(st, known={"m0009"}) == []
    # 也可以由调用方把已经渲过的长度传进来（省一次渲染）
    assert notes.stats(st, block_chars=7)["block_chars"] == 7


def test_check_only_cares_about_the_total():
    """⭐ 2026-10-05: `check()` 只剩两条判据（总量 · refs）—— **划掉不再是它的活**。

    从前的"结清未退场积压"（`MAX_CLOSED_PENDING`）随两段式一起没了: 条目**划掉即消失**,
    本子上只有还开着的 ⇒ "积压"这个概念不存在。
    """
    st = notes.fold([_add(i, text=f"第{i}条", refs=("m0009",)) for i in range(1, 6)] +
                    [_ev(6, N_CLOSE, {"id": "n1"}), _ev(7, N_CLOSE, {"id": "n2"})])
    assert [it.id for it in st.pinned] == ["n3", "n4", "n5"]       # 划掉的两条没了
    assert notes.check(st) == []                                   # 也不报任何告警


# ---------------------------------------------------------------------------
# 渲染: 注入块
# ---------------------------------------------------------------------------

def test_render_skips_empty_slots_entirely():
    """空槽**不印抬头** —— 常驻预算的每一行都要有内容。

    ⛔ N4e（2026-09-29）: 空状态 + 只有 `on_mind` 的那种块**整个消失**
    （`render_note_block` → `""`）—— 常驻块从此只装约定, 心境不再占一行。
    """
    only_pinned = notes.render_note_block(notes.fold([_add(1)]), now=NOW)
    assert notes.GROUP_LEADS[notes.SLOT_PINNED] in only_pinned
    assert "最近在想" not in only_pinned
    # 一份只有退役键的旧状态 ⇒ 一个字都不印
    legacy = notes.NotesState.from_dict({"up_to_seq": 9, "next_n": 3,
                                         "on_mind": {"text": "只有这句"}})
    assert notes.render_note_block(legacy, now=NOW) == ""


def test_render_shows_only_open_items_newest_first():
    """⭐ 2026-10-05: 注入块**只印还开着的**（划掉的条目已经不在本子上）。

    排序 = `since` 降序（新的在上面）—— 这个块第一句要回答"我手上还开着什么"。
    """
    st = notes.fold([
        _add(1, text="周六模型店", refs=("m0009",)),
        _add(2, text="还他笔记", refs=("m0011",), ts=T1),
        _add(3, text="买花", refs=("m0014",)),                        # 更老的约定
        _ev(4, N_CLOSE, {"id": "n1", "afterwards": "那天我忘了", "state": "broken"}),
    ])
    lines = notes.render_note_block(st, now=NOW).splitlines()

    assert lines[1] == "  · 你自己记下的约定"
    assert lines[2] == "    n2 还他笔记  ← 记于 昨天"
    assert lines[3] == "    n3 买花  ← 记于 3 天前"
    assert len(lines) == 4, "划掉的行一行都不该占"
    assert "n1" not in "\n".join(lines)


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
    st = notes.NotesState(pinned=[notes.NoteItem(id="n1", text="条目",
                                                  refs=["m1"], since="不是时间")])
    assert notes.render_note_block(st, now=NOW).splitlines()[2] == "    n1 条目"
    with_titles = notes.render_note_block(st, now=NOW, titles={"m1": "模型店的午后"})
    assert with_titles.splitlines()[2] == "    n1 条目 (《模型店的午后》)"


# ---------------------------------------------------------------------------
# 序列化（`soul/notes.json` 的形状; 落盘在下一步）
# ---------------------------------------------------------------------------

def test_slots_and_constants_are_consistent():
    """**只有一个槽** —— A/B 二分（操作式 / 快照式）随 `on_mind` 一起退役。

    ⚠️ N4a（2026-09-29）: 第三槽 `habits` 已退役;
    ⛔ N4e（2026-09-29）: 第二槽 `on_mind` 退役（*"太煽情了"*）⇒ 只剩 `pinned`。
    ⚠️ 2026-09-29: 槽名 `promise` → **`pinned`**；两条**每槽上限**判据退役, 换
    **总量上限 `MAX_NOTE_CHARS`**（见 `check` 的 docstring）。
    """
    assert notes.SLOTS == (notes.SLOT_PINNED,)
    assert notes.OPSLOTS == (notes.SLOT_PINNED,)
    assert not hasattr(notes, "SNAPSHOT_SLOTS"), "一个槽谈不上二分"
    assert notes.MAX_NOTE_CHARS == 500, "总量上限（数值未标定, 真机看了再调）"
    assert not hasattr(notes, "MAX_PROMISE"), "每槽条数上限已退役（换总量上限）"
    assert not hasattr(notes, "MAX_HABITS") and not hasattr(notes, "SLOT_HABITS")
    # ⛔ 退役的就是退役: 常量留着"以防万一" = 还有一条静默的写路
    assert not hasattr(notes, "SLOT_ON_MIND")
    assert not hasattr(notes, "MAX_ON_MIND_TEXT")
    assert notes.GROUP_LEADS == {notes.SLOT_PINNED: "· 你自己记下的约定"}
    assert logging.getLogger("core.brain.notes") is not None
