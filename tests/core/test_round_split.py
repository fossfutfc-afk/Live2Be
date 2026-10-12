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


def _note(text, *, due="", refs=("m9001",), seq=1, ts="2026-09-28T10:00:00+08:00"):
    """一条**还开着**的约定（`note/add` 事件 —— 真源是事件流, 见 `test_round_close`）。

    ⚠️ `refs` **不能空**（写侧硬门槛: 每条约定都要能指回一段经历）; 默认那个 `m9001`
    在这个库里**不存在** ⇒ 它的两条"提到"判据都不中 = 稳定地算"没提到"
    （用 `m0001` 会与本段新建的 episode **撞号**, 让"提到"的判据随重跑改变 —— 踩过一次）。
    """
    e = notes.note_event(notes.add_op(text, list(refs), due=due))
    e.seq, e.ts = seq, ts
    return e


def _relate(n: int = 0, *, ids=None) -> dict:
    """L1 的应答 —— 缺省"什么关系都没看出来"（✅ 合法答案）。

    ⚠️ **P1b-2（2026-10-07）**: 从前这里按"每条 episode 一条 `add`"造 belief
    （"必须覆盖全部 episode"是当时的硬要求）; L1 不建节点、也没有覆盖要求
    ⇒ `n` / `ids` 只剩"让调用点读得通"的作用（要落边的用例自己写 `relations`）。
    """
    return {"relations": []}


class _Stub:
    """按 `task` 记下每次调用的 user 串; 应答走 `stub_tasks.annotation_reply` 的标准包。

    ⚠️ **不按中文关键字分派**（`tests/core/test_stub_dispatch_guard.py` 会扫）。
    """

    def __init__(self, *, split=None, record=None, relate=None, **kw):
        self._split, self._record, self._relate = split, record, relate
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
        if task == T.DIGEST_RELATE and self._relate is not None:
            return self._relate
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
    res = digest_segment(st, _Stub(split=_SPAN_NULL, relate=_relate(1)),
                         [_note("生日蛋糕", due="2026-10-01"), _mmt(3)])
    assert res.ok, res.errors
    assert not [w for w in res.contract_warnings if "资格位没发" in w], res.contract_warnings

    # ② 本段**提到它**了（它的出生经历就在这一段里）⇒ 不发资格位 ⇒ 丢弃
    st2 = _store(tmp_path / "b")
    st2.add(make_node("episode", text="生日蛋糕", event_seq=[3], ts=_NOW))
    res2 = digest_segment(st2, _Stub(split=_SPAN_NULL, relate=_relate(1)),
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
    relate = {"relations": []}          # L1: 两条经历都不接（本用例测的是去重）
    st = _store(tmp_path)
    res = digest_segment(st, _Stub(split=split, record=record, relate=relate),
                         [_note("团子的事"), _mmt(3)])
    assert res.ok, res.errors
    eps = [n for n in (st.get(i) for i in res.created) if n.kind == "episode"]
    assert len(eps) == 2, f"同一个 span 的两行必须是两条记忆: {res.created}"
    assert sorted(tuple(n.event_seq) for n in eps) == [(3,), (3,)]
    print("    同 span 两行: 两条 episode 都在（没被当重复合掉）✓")


# ---------------------------------------------------------------------------
# ⑦ L5: 【本段骨架】只印有区间的行（无区间那行不派活）+ 对位不许错
# ---------------------------------------------------------------------------

_MIXED = {"segments": [
    {"span": [3, 3], "abstract": "老师邀请我去咖啡厅"},
    {"span": None, "state": "close", "id": "n1", "abstract": "生日那天, 老师没有来",
     "title": "生日那天", "significance": 0.9},
    {"span": [4, 4], "state": "open", "abstract": "我把团子带来了"},
    {"span": [5, 5], "state": "close", "id": "n2", "abstract": "苔藓那件事了了"},
]}


def test_skeleton_prints_only_rows_with_a_position():
    """⭐ 无区间那一行**不派活**（没有事件可写 —— 正文是 R0 给的 `abstract`）, 编号重编。

    ⚠️ 而 `close`（有区间的）**照旧派活** —— 它是一条记忆（"我把团子带来了"）,
    只是它也带账 ⇒ 和 `open` 一样打 ⭐（**不许 drop**）。
    """
    from core.digest.material import _skeleton_rows, _skeleton_text
    from core.digest.rounds import ROUNDS

    segs = [dict(r) for r in _MIXED["segments"]]
    assert [i for i, _seg in _skeleton_rows(segs)] == [0, 2, 3]
    assert _skeleton_text(segs).splitlines() == [
        "第 1 件｜3-3｜老师邀请我去咖啡厅",
        "第 2 件｜4-4｜⭐ 我把团子带来了",
        "第 3 件｜5-5｜⭐ 苔藓那件事了了",
    ]
    # 印的和说的同源: 提示只解释 ⭐ 一个含义（不许 drop）
    spec = next(s for s in ROUNDS if s.key == "record")
    assert "没有能填的骨架行" in spec.skip
    print("    骨架: 无区间行不派活 + 重编 + close 也打 ⭐ ✓")


def test_r1_is_skipped_when_there_is_nothing_to_fill(tmp_path):
    """整段只有"没有那一刻" ⇒ 骨架为空 ⇒ **R1 一次都不发**（0 次调用, 账目照走）。"""
    split = {"segments": [{"span": None, "state": "close", "id": "n1",
                           "abstract": "生日那天, 老师没有来",
                           "title": "生日那天", "significance": 0.9}]}
    llm = _Stub(split=split, relate=_relate(1))
    res = digest_segment(_store(tmp_path), llm, [_note("生日蛋糕", due="2026-10-01"),
                                                 _mmt(3)])
    assert res.ok, res.errors
    assert T.DIGEST_SPLIT in llm.tasks and T.DIGEST_RECORD not in llm.tasks, llm.tasks
    print(f"    R1 跳过: 只发了 {[t for t in llm.tasks if t]} ✓")


def test_the_spanless_row_does_not_shift_the_alignment(tmp_path):
    """端到端: 无区间那行不派活 —— 而**对位不许错**。

    ⭐ 这是这一笔最容易静默错的地方: 过滤之后"第 i 条条目 → 哪条切片"必须重新对上,
    否则 note 的**出生地址**（`refs`）会挂到别条经历上 —— 那种错不报错, 只会让
    "这条约定是从哪件事长出来的"变成另一件事。
    """
    record = {"episodes": [{"text": "老师邀请我去咖啡厅", "title": "咖啡厅",
                            "tags": ["咖啡"]},
                           {"text": "我把团子带来了", "title": "团子", "tags": ["团子"]}]}
    st = _store(tmp_path)
    llm = _Stub(split={"segments": [dict(r) for r in _MIXED["segments"][:3]]},
                record=record, relate=_relate(3))
    res = digest_segment(st, llm, [_note("生日蛋糕", due="2026-10-01"),
                                   _mmt(3), _mmt(4, reply="我把团子带来了")])
    assert res.ok, res.errors

    r1 = llm.user_of(T.DIGEST_RECORD)
    bones = [ln for ln in r1.splitlines() if ln.startswith("第 ")]
    assert bones == ["第 1 件｜3-3｜老师邀请我去咖啡厅",
                     "第 2 件｜4-4｜⭐ 我把团子带来了"], bones
    assert "生日那天" not in r1, "无区间那一行不该出现在骨架里"
    # ⭐ 对位: note 的出生地址 = **open 那一行**长出来的 episode（`event_seq == [4]`）
    ep4 = next(n.id for n in st.all()
               if n.kind == "episode" and list(n.event_seq) == [4])
    adds = [op for op in res.notes_ops if op["action"] == "add"]
    assert [op["refs"] for op in adds] == [[ep4]], res.notes_ops
    assert [op["text"] for op in adds] == ["我把团子带来了"]
    print(f"    对位: 骨架 2 行（无区间那行没派活）, note 挂在 {ep4} ✓")


# ---------------------------------------------------------------------------
# ⑧ L7: 按 R0 那张表产 op（add / update / close + `#pinned`）+ 无区间那段经历
# ---------------------------------------------------------------------------

_SPANLESS = {"span": None, "state": "close", "id": "n1",
             "abstract": "生日那天, 老师没有来",
             "title": "生日那天", "significance": 0.9}


def test_open_row_makes_the_note_and_marks_the_birth_episode(tmp_path):
    """`state=open` ⇒ `note/add`（`refs` = **它自己那条** episode）+ 出生那条打 `#pinned`。"""
    split = {"segments": [{"span": [3, 3], "abstract": "我把团子带来了", "state": "open"}]}
    record = {"episodes": [{"text": "我把团子带来了", "title": "团子", "tags": ["团子"]}]}
    st = _store(tmp_path)
    res = digest_segment(st, _Stub(split=split, record=record, relate=_relate(1)),
                         [_mmt(3, reply="我把团子带来了")])
    assert res.ok, res.errors
    op, = res.notes_ops
    assert op["action"] == "add" and op["text"] == "我把团子带来了"
    assert op["refs"] == [op["src"]], op
    birth = st.get(op["refs"][0])
    assert notes.PINNED_TAG in (birth.tags or []), birth.tags
    print(f"    open ⇒ add（refs={op['refs']}）· 出生那条打了 {notes.PINNED_TAG} ✓")


def test_update_row_corrects_the_note_and_keeps_the_audit(tmp_path):
    """`open` + `id` = **更正** —— 补上"后来才知道的日期", op 带 `before`/`after`。"""
    split = {"segments": [{"span": [4, 4], "state": "open", "id": "n1",
                           "abstract": "老师生日是 5/10, 那天一起吃蛋糕",
                           "due": "2027-05-10"}]}
    record = {"episodes": [{"text": "我知道了老师的生日", "title": "生日", "tags": ["生日"]}]}
    st = _store(tmp_path)
    res = digest_segment(st, _Stub(split=split, record=record, relate=_relate(1)),
                         [_note("老师生日那天一起过, 我还不知道是哪天"), _mmt(4)])
    assert res.ok, res.errors
    upd, = [o for o in res.notes_ops if o["action"] == "update"]
    assert upd["id"] == "n1" and upd["due"] == "2027-05-10"
    assert upd["before"] == {"text": "老师生日那天一起过, 我还不知道是哪天", "due": ""}, upd
    assert upd["after"] == {"text": "老师生日是 5/10, 那天一起吃蛋糕",
                            "due": "2027-05-10"}, upd
    print("    更正: update（due + text, 带 before/after）✓")


def test_update_row_that_changes_nothing_writes_no_op(tmp_path):
    """白跑一行不许: `before == after` ⇒ **不写 op**（"不能假装变了"）。"""
    text, due = "周六去模型店", "2026-10-09"
    split = {"segments": [{"span": [4, 4], "state": "open", "id": "n1",
                           "abstract": text, "due": due}]}
    record = {"episodes": [{"text": "又提了一次模型店", "title": "模型店", "tags": ["模型店"]}]}
    st = _store(tmp_path)
    res = digest_segment(st, _Stub(split=split, record=record, relate=_relate(1)),
                         [_note(text, due=due), _mmt(4)])
    assert res.ok, res.errors
    assert res.notes_ops == [], res.notes_ops
    print("    更正行什么都没改 ⇒ 一条 op 都不写 ✓")


def test_close_row_scratches_the_note(tmp_path):
    """`state=close` ⇒ `close` op（划掉即移除 —— 兑现/失约/被盖过**一律**）。"""
    split = {"segments": [{"span": [4, 4], "state": "close", "id": "n1",
                           "abstract": "我把团子带来了"}]}
    record = {"episodes": [{"text": "我把团子带来了", "title": "团子", "tags": ["团子"]}]}
    st = _store(tmp_path)
    res = digest_segment(st, _Stub(split=split, record=record, relate=_relate(1)),
                         [_note("把团子带去夏莱"), _mmt(4)])
    assert res.ok, res.errors
    assert [o["action"] for o in res.notes_ops] == ["close"], res.notes_ops
    assert res.notes_ops[0]["id"] == "n1"
    print("    close ⇒ 从本子划掉 ✓")


def test_spanless_row_becomes_a_dated_episode(tmp_path):
    """`span: null` + close ⇒ 一条**无区间经历**: 正文 = R0 的 `abstract`, `ts` = **期限日**。

    （R1 跳过 ⇒ 这一段只有它一条 episode; 它**照样**要 R2 覆盖。）
    """
    st = _store(tmp_path)
    llm = _Stub(split={"segments": [dict(_SPANLESS)]}, relate=_relate(1))
    res = digest_segment(st, llm, [_note("生日蛋糕", due="2026-10-01"), _mmt(3)])
    assert res.ok, res.errors
    assert T.DIGEST_RECORD not in llm.tasks, llm.tasks
    ep = st.get(res.spanless_ids[0])
    assert ep.text == "生日那天, 老师没有来" and ep.title == "生日那天"
    assert ep.significance == 0.9
    assert list(ep.event_seq) == [3], ep.event_seq            # 账的指针（本段上界）
    assert ep.ts.startswith("2026-10-01T"), ep.ts             # 记忆属于**那天**, 不是消化那刻
    assert ep.verbatim == "" and not ep.tags                  # 没有事件 ⇒ 绝不编
    assert [o["action"] for o in res.notes_ops] == ["close"]
    print(f"    无区间经历: ts={ep.ts} · event_seq={ep.event_seq} ✓")


def test_spanless_episode_is_not_written_twice_on_rerun(tmp_path):
    """崩溃窗口重跑 ⇒ 图上仍**只有一条**"生日那天, 老师没有来"（§4.3 那个已验的洞）。

    ⚠️ 夹具里那条约定**指向一段真的出生经历**（`m0001`, 早先那一段, seq=1）——
    这样"本段有没有提到它"的判据不会随重跑改变（`m0001` 与新建的 episode 撞号过一次）。
    """
    events = [_note("生日蛋糕", due="2026-10-01", refs=["m0001"]), _mmt(3)]
    st = _store(tmp_path)
    st.add(make_node("episode", text="约好生日一起吃蛋糕", event_seq=[1],
                     ts="2026-09-20T10:00:00+08:00"))
    res1 = digest_segment(st, _Stub(split={"segments": [dict(_SPANLESS)]},
                                    relate=_relate(ids=["m0002"])), events)
    assert res1.ok, res1.errors
    ep1 = res1.spanless_ids[0]
    n_before = len(st.all())
    st.meta["digested_seq"] = 0                        # 模拟崩溃窗口: 落盘但水位没推进
    res2 = digest_segment(st, _Stub(split={"segments": [dict(_SPANLESS)]},
                                    relate=_relate(ids=["m0002"])), events)
    assert res2.ok, res2.errors
    assert len(st.all()) == n_before, "无区间经历重跑不得双写"
    assert res2.spanless_ids == [ep1], "复用旧节点"
    print(f"    无区间经历幂等: 重跑后仍是 {n_before} 条（复用 {ep1}）✓")


def test_spanless_episode_does_not_push_the_watermark(tmp_path):
    """⛔ 那格 `event_seq=[interact_max]` 是**账的指针** —— 不许把欠着的尾巴推过水位。"""
    split = {"segments": [{"span": [3, 3], "abstract": "路过模型店"},
                          dict(_SPANLESS)]}
    record = {"episodes": [{"text": "路过模型店", "title": "模型店", "tags": ["模型店"]}]}
    st = _store(tmp_path)
    res = digest_segment(st, _Stub(split=split, record=record, relate=_relate(2)),
                         [_note("生日蛋糕", due="2026-10-01"),
                          _mmt(3), _mmt(4), _mmt(5)])
    assert res.ok, res.errors
    assert st.digested_seq == 3, "尾巴（4/5）必须留在水位之上等下一段重喂"
    print(f"    水位: 无区间经历没把它推过尾巴（digested_seq={st.digested_seq}）✓")


# ---------------------------------------------------------------------------
# ⑨ L9: 账单 —— 超期未决**逐条**可 grep（体检账, 不是判决）+ 开着的条数只记数
# ---------------------------------------------------------------------------

def test_overdue_detail_names_the_items_and_reaches_the_log(tmp_path, caplog):
    """⭐ "超期未决"要看得见**是哪几条**（用户裁: **不进 creep 账**, 日志够）。

    ⚠️ 它是**体检账, 不是判决**: 引擎只摆事实（"这条过期了、这一段没提到它"）,
    判不判在 R0 —— 所以它出现在 `digest_split` 那行 INFO 里, 而不是一条台账。
    """
    import logging

    from core.digest.material import _overdue_detail

    items = [notes.NoteItem(id="n3", text="生日蛋糕", refs=["m1"], due="2026-10-01"),
             notes.NoteItem(id="n7", text="模型店", refs=["m2"], due="2026-10-04"),
             notes.NoteItem(id="n1", text="永远开着", refs=["m3"])]
    assert _overdue_detail(items, {"n3", "n7"}, today=date(2026, 10, 5)) == \
        "n3（已过 4 天） · n7（已过 1 天）"
    assert _overdue_detail(items, set(), today=date(2026, 10, 5)) == "-"      # 没有就说没有
    assert _overdue_detail(items, {"n3"}, today=None) == "-"                 # 算不出不编

    # 端到端: 那段日志真的把编号写出来了（可 grep）
    split = {"segments": [{"span": [3, 3], "abstract": "路过模型店"}]}
    record = {"episodes": [{"text": "路过模型店", "title": "模型店", "tags": ["模型店"]}]}
    st = _store(tmp_path)
    with caplog.at_level(logging.INFO, logger="core.digest.rounds.split"):
        res = digest_segment(st, _Stub(split=split, record=record, relate=_relate(1)),
                             [_note("生日蛋糕", due="2026-10-01"), _mmt(3)])
    assert res.ok, res.errors
    line = " ".join(r.getMessage() for r in caplog.records
                    if r.name == "core.digest.rounds.split")
    assert "名单=1" in line and "超期=n1（已过 4 天）" in line, line
    print(f"    账单: {line.split('超期=')[1].split(' 认领')[0]} ✓")


# ---------------------------------------------------------------------------
# ⑩ M1: 好感归 R1（不再归 R2）· "不必都写"不是硬双射
# ---------------------------------------------------------------------------

def test_affection_belongs_to_r1_only(tmp_path):
    """⭐ **M1（2026-10-05）**: 好感是"这一段她对老师的亲近感净变化" —— 与 `significance`
    同族（都是打分）⇒ 归 **R1**。判据（不只是位置）: **别的轮给的那个数会被丢掉**。

    ⚠️ P1b-2（2026-10-07）: "别的轮"从 R2 换成了 **L1（`relate`）** —— 判据一字不变,
    只是那个旧位置的占位者换了名字（它照样不读 delta）。
    """
    split = {"segments": [{"span": [3, 3], "abstract": "老师约我去公园"}]}
    record = {"episodes": [{"text": "老师约我去公园", "title": "公园", "tags": ["公园"]}],
              "affection_exp_delta": 42}
    # L1 那一份里塞一个**旧位置**的 delta（它现在不该被读）
    relate = {"relations": [], "affection_exp_delta": -99}

    res = digest_segment(_store(tmp_path), _Stub(split=split, record=record,
                                                 relate=relate),
                         [_mmt(3)])
    assert res.ok, res.errors
    assert res.affection_delta == 42, "好感要取 **R1** 的那个数（旧位置已退役）"

    # 反过来: 只有 L1 给 ⇒ 读到的是 0（它不再有任何话语权）
    split2 = {"segments": [{"span": [3, 3], "abstract": "老师约我去公园"}]}
    record2 = {"episodes": [{"text": "老师约我去公园", "title": "公园", "tags": ["公园"]}]}
    res2 = digest_segment(_store(tmp_path / "b"),
                          _Stub(split=split2, record=record2, relate=relate),
                          [_mmt(3)])
    assert res2.ok, res2.errors
    assert res2.affection_delta == 0, "那一格已经不是好感的家了"
    print("    好感: R1 的 42 生效 / R2 的 -99 被忽略 ✓")


def test_r1_may_write_fewer_rows_than_slices(tmp_path):
    """⭐ **不必都写**: 骨架三件、R1 只写一件 ⇒ **不拒**（这不是违约, 是她的取舍）。

    引擎侧只**记一笔账**（`items.dropped` —— "那两条没人记"）, 不是失败。
    """
    split = {"segments": [{"span": [3, 3], "abstract": "前厅闲聊"},
                          {"span": [4, 4], "abstract": "老师约我去公园"},
                          {"span": [5, 5], "abstract": "回去的路上"}]}
    record = {"episodes": [{"text": "老师约我去公园", "title": "公园", "tags": ["公园"]}]}
    res = digest_segment(_store(tmp_path),
                         _Stub(split=split, record=record, relate=_relate(1)),
                         [_mmt(3), _mmt(4), _mmt(5)])
    assert res.ok, res.errors
    assert res.record_gaps["items"]["kept"] == 1
    assert res.record_gaps["items"]["dropped"], "没人填的那两条要进账（可见, 但不拦）"
    print(f"    不必都写: 三件只写一件 ⇒ ok, 账里记了 {len(res.record_gaps['items']['dropped'])} 条")
