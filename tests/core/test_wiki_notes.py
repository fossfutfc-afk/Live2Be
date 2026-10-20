"""`notes.py` —— 随身笔记的**折叠 / 校验 / 渲染**（链路 ①-第二步, 2026-09-23）。

覆盖**纯函数层**: 操作事件 → `NotesState` → 注入块。
（`notes.fold` 每次现折 —— ⏸ 2026-10-18 退役了 `soul/notes.json` 那份缓存。）

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

def test_fold_is_deterministic_and_needs_no_cache():
    """全量重折是**确定性**的 —— 这就是"不需要缓存"的依据。

    ⏸ 2026-10-18 退役了 `soul/notes.json`: 它省下的那次折叠是 0.1 ms 级
    （真机 445 事件 / 5 条操作）, 而代价是一份会与真源不同步、**错了没人知道**的
    第二真相 —— 真机上它吞掉过一条笔记。
    """
    events = [_add(1), _mmt(2), _add(3, text="还他笔记", refs=("m0011",), ts=T1)]
    a, b = notes.fold(events), notes.fold(events)
    assert [(it.id, it.text) for it in a.items] == [(it.id, it.text) for it in b.items]
    assert a.next_n == b.next_n == 3
    # 没有增量折叠这回事了（`fold` 只收 events）
    assert "base" not in notes.fold.__code__.co_varnames


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
        assert st.items == [], outcome
        assert st.next_n == 2                                    # 号照旧只增不复用
        assert "n1" not in notes.render_note_block(st, now=NOW)


def test_old_archive_retire_means_the_same_thing_as_close(caplog):
    """旧档里的 `retire` 与 `close` **同义**（2026-10-05 合并）—— 读侧必须照旧认它。"""
    st = notes.fold([_add(1), _ev(2, N_RETIRE, {"id": "n1"})])
    assert st.items == []
    # 指不到的 id（已划掉 / 根本不存在）⇒ 只告警, 不抛
    st2 = notes.fold([_add(1), _ev(2, N_RETIRE, {"id": "n99"})])
    assert [it.id for it in st2.items] == ["n1"]
    assert "指不到" in caplog.text


def test_close_of_a_gone_item_only_warns(caplog):
    """二次 close / 指不到的 id ⇒ 告警 + 跳过（不会复活, 也不会报错）。"""
    st = notes.fold([
        _add(1),
        _ev(2, N_CLOSE, {"id": "n1", "afterwards": "真的去了"}, ts=T1),
        _ev(3, N_CLOSE, {"id": "n1", "afterwards": "其实没去"}, ts=T1),
    ])
    assert st.items == []
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
    base = [_add(1)]
    st = notes.fold([*base, _ev(2, N_UPDATE, {"id": "n1", "due": "2026-05-13"})])
    assert st.items[0].due == "2026-05-13"
    assert st.items[0].text == "周六模型店"                     # 其余不动
    st = notes.fold([*base,
                     _ev(2, N_UPDATE, {"id": "n1", "due": "2026-05-13"}),
                     _ev(3, N_UPDATE, {"id": "n1", "text": "生日那天"})])
    assert (st.items[0].text, st.items[0].due) == ("生日那天", "2026-05-13")

    # 指不到 id ⇒ 只告警; "一样都没给" / 缺 id ⇒ 写侧直接拒
    st2 = notes.fold([*base, _ev(4, N_UPDATE, {"id": "n99", "due": "2026-01-01"})])
    assert [it.id for it in st2.items] == ["n1"]
    with pytest.raises(ValueError, match="至少要改一样"):
        notes.update_op("n1")
    with pytest.raises(ValueError, match="update 缺 id"):
        notes.update_op("  ", due="2026-01-01")


def test_add_rejects_missing_refs_on_read_side(caplog):
    st = notes.fold([_ev(1, N_ADD, {"text": "没有引用的条目"})])
    assert st.items == []                           # 残缺操作不折进去（但记事）
    assert notes.check(notes.fold([_add(1)])) == []   # 正常条目零告警


def test_add_of_the_same_episode_is_skipped(caplog):
    """同一条经历（= `refs[0]`）长出的第二条笔记 ⇒ **跳过**（重跑幂等的第二道）。

    判据: 拿"指向哪条经历"比, **不拿正文比** —— 她两次可能把同一句话写得不一样。
    ⚠️ 副作用（现有语义）: 一条经历最多长一条笔记。真机做不到（每条 `state=open` 的
    切片各长一条 episode）, 所以先按"一条一条"处理。
    """
    caplog.set_level(logging.INFO)
    st = notes.fold([_add(1, text="周六模型店"),
                     _add(2, text="换个说法再说一遍", refs=("m0009",), ts=T1),
                     _add(3, text="还他笔记", refs=("m0011",), ts=T1)])
    assert [it.text for it in st.items] == ["周六模型店", "还他笔记"], \
        "同一条经历被钉了两次"
    assert "已经钉过" in caplog.text
    print("    同 refs[0] 只留一条 · 不同经历照常 ✓")


# ---------------------------------------------------------------------------
# 折叠: rewrite（B 类整段替换）
# ---------------------------------------------------------------------------

def test_next_n_guard_prevents_id_reuse():
    """护栏: `next_n` 落后于现有 id（手工构造的状态）时也不会发出重号。"""
    st = notes.NotesState(next_n=1, items=[notes.NoteItem(id="n7", text="老条目")])
    assert st.next_n == 8
    print("    手工构造 next_n=1 + n7 ⇒ 发号器被顶到 8 ✓")


def test_next_n_counts_referenced_ids_too():
    """⭐ `next_n` = **分配过 ∪ 被引用过**的最大号 + 1 —— 不是"活着的那几条"。

    为什么: 退役的槽（`habits` / `on_mind`）当年分配过号, 而事件流里还躺着
    `close n5` 这种引用。只按活着的推会**回退**（真机: 重折 3 / 缓存 6）⇒ 新笔记
    重新用上 n3/n4/n5, 而历史引用过这些号。
    """
    st = notes.fold([
        _add(1),                                        # n1
        _ev(2, N_CLOSE, {"id": "n1"}),                  # 划掉 n1
        _ev(3, N_CLOSE, {"id": "n5"}),                  # 引用一个从没分配过的号
    ])
    assert st.items == []
    assert st.next_n == 6, "被引用过的号没计入高水位"
    print("    分配过 n1 + 引用过 n5 ⇒ next_n=6 ✓")


def test_rewrite_event_is_a_silent_noop_after_retirement():
    """⛔ N4e（2026-09-29）: `on_mind` 槽退役 ⇒ 旧 `rewrite` 事件**静默吞掉**。

    判据不是"零读者"而是**时间尺度**（*"它太煽情了, 煽情的剧情过去了,
    就不必一直耿耿于怀了"*）。⚠️ 但**动作名不能删** —— 真机 seq 263 那条
    `note/rewrite` 躺在事件流里, 落到 else 分支会打一条永远修不掉的"未知操作"告警。
    """
    st = notes.fold([_ev(1, N_REWRITE, {"on_mind": {"text": "最近在想的那件事",
                                                    "refs": ["m2"]}}, ts=T0),
                     _ev(2, N_ADD, {"text": "周六模型店", "refs": ["m0009"]}, ts=T1)])
    assert not hasattr(st, "on_mind")                    # 状态里没有这个字段了
    assert [it.id for it in st.items] == ["n1"]          # 后面的 add 照常折进来


def test_rewrite_is_not_writable_anymore():
    """写侧: `rewrite` 与它的构造器一起退役（留着就是一条往空槽里写的静默写路）。"""
    assert not hasattr(notes, "rewrite_op")
    assert not hasattr(notes, "SLOT_ON_MIND")
    assert not hasattr(notes, "SNAPSHOT_SLOTS")
    with pytest.raises(ValueError):
        notes.validate_ops([{"action": N_REWRITE, "on_mind": "一句话"}])


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
    st_bare = notes.NotesState(items=[notes.NoteItem(text="无引用", since=T0)])
    assert any("没有 refs" in p for p in notes.check(st_bare))

    # 总量上限（⭐ 2026-09-29 换判据: 条数不再是判据, 管的是**注入块多长**）
    long_block = notes.fold([_add(i, text=f"第{i}条" + "长" * 15, refs=(f"m{i:04d}",))
                             for i in range(1, 17)])
    assert len(long_block.items) == 16
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
                     _add(2, text="还他笔记", refs=("m0011",), ts=T1)])
    assert notes.stats(st)["open"] == 2
    assert notes.stats(st)["block_chars"] == len(notes.render_note_block(st))
    # 开着的条目**本身不产生告警**（它不是问题 —— 本子就是装这个的）
    assert notes.check(st, known={"m0009", "m0011"}) == []
    # 也可以由调用方把已经渲过的长度传进来（省一次渲染）
    assert notes.stats(st, block_chars=7)["block_chars"] == 7


def test_check_only_cares_about_the_total():
    """⭐ 2026-10-05: `check()` 只剩两条判据（总量 · refs）—— **划掉不再是它的活**。

    从前的"结清未退场积压"（`MAX_CLOSED_PENDING`）随两段式一起没了: 条目**划掉即消失**,
    本子上只有还开着的 ⇒ "积压"这个概念不存在。
    """
    st = notes.fold([_add(i, text=f"第{i}条", refs=(f"m{i:04d}",)) for i in range(1, 6)] +
                    [_ev(6, N_CLOSE, {"id": "n1"}), _ev(7, N_CLOSE, {"id": "n2"})])
    assert [it.id for it in st.items] == ["n3", "n4", "n5"]       # 划掉的两条没了
    assert notes.check(st) == []                                   # 也不报任何告警


# ---------------------------------------------------------------------------
# 渲染: 注入块
# ---------------------------------------------------------------------------

def test_render_omits_the_block_when_empty():
    """空 ⟹ **整块消失**（连抬头都不印）—— 常驻预算的每一行都要有内容。

    ⏸ 从前这里还从 `notes.json` 读一份"只有 `on_mind` 的旧状态"来证明它不印;
    缓存退役之后没有那种输入了（`fold` 只认事件流, 而 `rewrite` 是空操作）。
    """
    only_pinned = notes.render_note_block(notes.fold([_add(1)]), now=NOW)
    assert notes.LEAD in only_pinned
    assert "最近在想" not in only_pinned
    assert notes.render_note_block(notes.NotesState(), now=NOW) == ""


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
    st = notes.NotesState(items=[notes.NoteItem(id="n1", text="条目",
                                                  refs=["m1"], since="不是时间")])
    assert notes.render_note_block(st, now=NOW).splitlines()[2] == "    n1 条目"
    with_titles = notes.render_note_block(st, now=NOW, titles={"m1": "模型店的午后"})
    assert with_titles.splitlines()[2] == "    n1 条目 (《模型店的午后》)"


# ---------------------------------------------------------------------------
# 常量与「退役的名字不许回来」
# ---------------------------------------------------------------------------

def test_no_slot_layer_and_retired_names_stay_gone():
    """**没有"槽"这一层**（2026-10-18 塌掉）, 退役的名字一个都不许回来。

    从前的 `SLOT_PINNED` / `SLOTS` / `OPSLOTS` / `GROUP_LEADS` 是「一个槽的表」: 只服务
    N=1, 却把一次赋值绕成了 `getattr`/`setattr` 加一个概念。现在只有 `items` 与 `LEAD`。
    常量留着"以防万一" = 还有一条静默的写路 —— 退役就是退役。
    """
    for gone in ("SLOT_PINNED", "SLOTS", "OPSLOTS", "GROUP_LEADS", "SNAPSHOT_SLOTS",
                 "MAX_PROMISE", "MAX_HABITS", "SLOT_HABITS", "SLOT_ON_MIND",
                 "MAX_ON_MIND_TEXT",
                 # ⏸ 2026-10-18 缓存退役: 这几个名字是"第二份真相"的入口
                 "_ITEMS_KEY", "_LEGACY_KEYS"):
        assert not hasattr(notes, gone), gone
    assert notes.LEAD == "· 你自己记下的约定"
    assert notes.MAX_NOTE_CHARS == 500, "总量上限（数值未标定, 真机看了再调）"


