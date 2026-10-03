# -*- coding: utf-8 -*-
"""`core/creep` —— **世界线的账**（行形状 / 写 / 严格读）。

用户 2026-09-29 裁决（这一刀的范围）:
    ✅ 账行 + `append`（`SessionStore.append_raw_row`）+ kind→存疑文本 + 严格读
    ❌ 不做: 让她看见（注记注入）· 开关 `[creep]` · cval · 解锁 · digest 写者

四件事在这里被钉住:
  ① **账行没有 `seq`** ⇒ `store.events()` / 窗口 / digest / 回放**都看不见它**
     （`Event.from_dict` 第一道校验就是 seq）
  ② **它不干扰发号** ⇒ 写完账之后, 下一条事件的 seq 照旧 `+1`, 盘上无重复
  ③ **读侧严格** ⇒ 坏行从 `bad_out` 出去 + 打 warning, **不静默丢**
  ④ **`kind` ↔ 文本池一一对应** ⇒ 每个 kind 至少 3 句变体, 写时取一（可传 rng 复现）

运行: python -m pytest tests/core/test_creep.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.creep import (  # noqa: E402
    KIND_DIGEST_SKIP,
    KINDS,
    TYPE_CREEP,
    make_row,
    pick,
    read_raw,
    record,
)
from core.creep.skeptical import POOLS  # noqa: E402
from core.session import SessionStore, make_event  # noqa: E402
from core.session.io import append_jsonl, read_jsonl  # noqa: E402
from core.session.renderer import window_messages  # noqa: E402

CHAR = "haruka"


def _store(tmp_path) -> tuple[SessionStore, str]:
    """建一条世界线 → (store, session_id)。"""
    st = SessionStore(tmp_path)
    root = st.create(CHAR)
    return st, root.session_id


def _some_events(st: SessionStore, sid: str, n: int = 2):
    out = []
    for i in range(n):
        out.append(st.append_event(CHAR, sid, make_event(
            "mmt", "mmt_chat", {"player": "老师", "reply": f"{i}"})))
    return out


# ---------------------------------------------------------------------------
# ① 隐身: 谁也看不见它
# ---------------------------------------------------------------------------

def test_creep_row_is_invisible_to_every_reader(tmp_path):
    """⭐ 账行写进去了, 但 `store.events()` / 上下文窗口都看不见它。"""
    st, sid = _store(tmp_path)
    evs = _some_events(st, sid, 2)
    before = st.events(CHAR, sid)
    before_seq = [e.seq for e in before]

    row = record(st, CHAR, session_id=sid, kind=KIND_DIGEST_SKIP,
                 at_seq=evs[-1].seq, evidence={"from": 1, "to": 2, "attempts": 3})

    parsed = st.events(CHAR, sid)
    assert [e.seq for e in parsed] == before_seq, "账行混进事件列表了"
    assert all(e.type != TYPE_CREEP for e in parsed)
    # 上下文窗口也不该有它
    text = " ".join(m["content"] for m in window_messages(parsed))
    assert "淡下去" not in text and TYPE_CREEP not in text
    # 但盘上确实多了一行（账是落盘的）
    rows = read_jsonl(st.events_path(CHAR, sid))
    assert len(rows) == len(before) + 1
    assert rows[-1]["kind"] == KIND_DIGEST_SKIP and "seq" not in rows[-1]
    print(f"    隐身: 盘上 {len(rows)} 行 / 事件 {len(parsed)} 个; 账行的键 = {sorted(row)}")


# ---------------------------------------------------------------------------
# ② 不干扰发号（这一刀的地基, 探针验过才敢写）
# ---------------------------------------------------------------------------

def test_raw_row_does_not_disturb_seq_allocation(tmp_path):
    """⭐ 写完账之后, 下一条事件的 seq 照旧 `+1`（`append_event` 的 max 看不见账行）。"""
    st, sid = _store(tmp_path)
    evs = _some_events(st, sid, 3)
    before = evs[-1].seq

    record(st, CHAR, session_id=sid, kind=KIND_DIGEST_SKIP, at_seq=before)
    # 连写几条账也不该影响
    record(st, CHAR, session_id=sid, kind=KIND_DIGEST_SKIP, at_seq=before)

    nxt = st.append_event(CHAR, sid, make_event("mmt", "mmt_chat",
                                                {"player": "老师", "reply": "next"}))
    assert nxt.seq == before + 1, f"账行干扰了发号: {before} → {nxt.seq}"

    seqs = [r.get("seq") for r in read_jsonl(st.events_path(CHAR, sid)) if "seq" in r]
    assert len(seqs) == len(set(seqs)), f"盘上出现重复 seq: {seqs}"
    assert seqs == sorted(seqs), f"盘上 seq 乱序: {seqs}"
    print(f"    发号: 连写 2 条账后下一条事件 seq = {nxt.seq}（前一条 {before}）; 盘上无重复")


def test_append_raw_row_rejects_empty(tmp_path):
    """裸账行必须是非空 dict（防"写一行 `{}` 进去"这种手滑）。"""
    st, sid = _store(tmp_path)
    for bad in ({}, None, "x"):
        try:
            st.append_raw_row(CHAR, sid, bad)
        except ValueError:
            continue
        raise AssertionError(f"空/坏行没被拒: {bad!r}")
    print("    append_raw_row: 空行/非 dict 一律拒（不写脏行）")


# ---------------------------------------------------------------------------
# ③ 读侧严格
# ---------------------------------------------------------------------------

def test_read_raw_roundtrips_and_reports_bad_rows(tmp_path):
    """读回来逐字相等; **坏行要响**（不静默丢）—— 写给"后来者别沿用宽容丢"。"""
    st, sid = _store(tmp_path)
    evs = _some_events(st, sid, 1)
    rng = random.Random(7)
    written = record(st, CHAR, session_id=sid, kind=KIND_DIGEST_SKIP,
                     at_seq=evs[-1].seq, evidence={"attempts": 3}, rng=rng)

    p = st.events_path(CHAR, sid)
    append_jsonl(p, {"type": TYPE_CREEP, "kind": KIND_DIGEST_SKIP})       # 缺 ts
    append_jsonl(p, {"ts": "2026-09-29T00:00:00", "type": TYPE_CREEP})    # 缺 kind
    append_jsonl(p, {"ts": "2026-09-29T00:00:00", "type": TYPE_CREEP,
                     "kind": "未来才有的kind"})                            # kind 不在词表

    bad: list[str] = []
    rows = read_raw(st, CHAR, session_id=sid, bad_out=bad)

    # 缺必填 ⇒ **丢** + 报; kind 不在词表 ⇒ **收下** + 报（数据是好的, 是写侧超前/写错）
    assert rows[0] == written, "读回来的账与写下去的逐字不等"
    assert len(rows) == 2 and rows[1]["kind"] == "未来才有的kind"
    assert len(bad) == 3, bad
    assert any("缺 ts" in b for b in bad) and any("缺 kind" in b for b in bad)
    assert any("不在词表" in b for b in bad)
    print(f"    严格读: 好账逐字读回 / 缺字段 2 条丢掉 / {len(bad)} 条坏行全部上报")


def test_read_raw_ignores_other_rows(tmp_path):
    """别人的行（真事件 / 别的账）一律不碰 —— 它只挑自己的 type。"""
    st, sid = _store(tmp_path)
    _some_events(st, sid, 2)
    bad: list[str] = []
    assert read_raw(st, CHAR, session_id=sid, bad_out=bad) == []
    assert bad == []
    print("    无账时: 空列表 + 零坏行（不看别人的行）")


# ---------------------------------------------------------------------------
# ④ kind ↔ 文本池
# ---------------------------------------------------------------------------

def test_every_kind_has_a_pool_of_variants():
    """每个 kind 都要有池子, 且**至少 3 句**（少了会明显撞车）。"""
    missing = [k for k in KINDS if k not in POOLS]
    assert not missing, f"这些 kind 没有存疑文本池: {missing}"
    thin = [k for k in KINDS if len(POOLS[k]) < 3]
    assert not thin, f"这些 kind 的变体少于 3 句: {thin}"
    for k in KINDS:
        for line in POOLS[k]:
            assert line.strip() and len(line) <= 30, f"{k}: 太长或空: {line!r}"
            # 纪律: 不给归因、不点名机制（粗筛 —— 名词黑名单）
            for banned in ("记忆", "窗口", "系统", "存档", "回档", "约定", "删"):
                assert banned not in line, f"{k}: {line!r} 点到了 {banned!r}"
    print(f"    {len(KINDS)} 个 kind × ≥3 句变体: 长度/黑名单都过")


def test_pick_is_randomizable_and_never_fabricates():
    """固定 rng ⇒ 可复现; 未知 kind ⇒ `""`（**绝不替它编一句**）。"""
    a = pick(KIND_DIGEST_SKIP, rng=random.Random(1))
    b = pick(KIND_DIGEST_SKIP, rng=random.Random(1))
    assert a == b and a in POOLS[KIND_DIGEST_SKIP]
    seen = {pick(KIND_DIGEST_SKIP, rng=random.Random(i)) for i in range(30)}
    assert seen <= set(POOLS[KIND_DIGEST_SKIP]) and len(seen) == 3, seen
    assert pick("nope") == "" and pick("") == ""
    print(f"    取一: 池子 {len(POOLS[KIND_DIGEST_SKIP])} 句全可达; 未知 kind → 空串")


def test_skeptical_is_frozen_at_write_time(tmp_path):
    """⭐ **写时冻结**: 取出的那句进账行; 之后改池子也**不改历史**。"""
    st, sid = _store(tmp_path)
    first = record(st, CHAR, session_id=sid, kind=KIND_DIGEST_SKIP, at_seq=1,
                   rng=random.Random(1))
    orig = POOLS[KIND_DIGEST_SKIP]
    POOLS[KIND_DIGEST_SKIP] = ("池子被整个换掉了",)          # 模拟"以后改了措辞"
    try:
        assert pick(KIND_DIGEST_SKIP) == "池子被整个换掉了"   # 新写的会用新池子
        rows = read_raw(st, CHAR, session_id=sid)
    finally:
        POOLS[KIND_DIGEST_SKIP] = orig                        # ⚠️ 必须还原（否则污染后面的用例）
    assert rows[0]["skeptical"] == first["skeptical"], "老账的措辞被后改的池子改写了"
    print(f"    写时冻结: 账里仍是 {rows[0]['skeptical'][:12]!r}…（池子改了也不动它）")


# ---------------------------------------------------------------------------
# 行形状
# ---------------------------------------------------------------------------

def test_row_shape():
    """行形状: **没有 seq**, `type/kind/ts` 必在, 可选键空则**不占位**。"""
    row = make_row(KIND_DIGEST_SKIP, at_seq=314, skeptical="…", evidence={"a": 1})
    assert "seq" not in row and row["type"] == TYPE_CREEP
    assert row["kind"] == KIND_DIGEST_SKIP and row["ts"]
    assert row["at_seq"] == 314 and row["evidence"] == {"a": 1}
    thin = make_row(KIND_DIGEST_SKIP, at_seq=0)
    assert "at_seq" not in thin and "skeptical" not in thin and "evidence" not in thin
    assert "at_seq" not in make_row(KIND_DIGEST_SKIP, at_seq="坏值")   # 坏坐标 ⇒ 不占位
    print(f"    行形状: {sorted(row)}（无 seq; 空键不占位）")


if __name__ == "__main__":
    import tempfile

    test_every_kind_has_a_pool_of_variants()
    test_pick_is_randomizable_and_never_fabricates()
    test_row_shape()
    with tempfile.TemporaryDirectory() as d:
        test_creep_row_is_invisible_to_every_reader(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_raw_row_does_not_disturb_seq_allocation(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_append_raw_row_rejects_empty(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_read_raw_roundtrips_and_reports_bad_rows(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_read_raw_ignores_other_rows(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_skeptical_is_frozen_at_write_time(Path(d))
    print("all creep ledger tests passed")
