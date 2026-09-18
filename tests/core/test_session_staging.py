# -*- coding: utf-8 -*-
"""章暂存区单测（B0，2026-09-17）—— 「章内不进真源，`vn_exit` 才整段提交」。

钉住的是**不变量**，不是实现：
  1. 章内写入 → **真源零变化**
  2. commit → 整段进真源、**`ts` 原样保留**、`seq` 由真源重算、暂存删除
  3. 丢弃 = 「删除」的全部（无 marker、无区间、无需过滤）
  4. **commit 前先收尾真源里的未闭合段**（原子性由这条不变量兜底）
  5. 半截 commit（模拟中断）→ 暂存保留、可重试
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.session import staging                                   # noqa: E402
from core.session.events import make_event, marker                 # noqa: E402
from core.session.store import SessionStore                        # noqa: E402

CHAR = "igusa_haruka"


def _st(tmp_path) -> SessionStore:
    return SessionStore(tmp_path, world_id="w1")


def _stage(store, char=CHAR, sid="", *, title="测试章"):
    """章内写入口（bond 侧将来用的就是它）。"""
    return staging.staging_store(store)


def _do_chapter(store, *, boards=2, complete=True, seq_offset=0):
    """模拟一章：enter_vn → N 块板 → vn_exit（可选）。"""
    sg = staging.staging_store(store)
    sg.enter_vn(CHAR, "", title="测试章")
    for i in range(boards):
        sg.append_event(CHAR, "", make_event(
            "bond", "story_scene", {"i": i + seq_offset}))
    if complete:
        sg.append_marker(CHAR, "", "vn_exit", {"completed": True})
    return sg


# ---------------------------------------------------------------------------
# 1. 章内不进真源
# ---------------------------------------------------------------------------

def test_chapter_stays_out_of_truth_source(tmp_path):
    """★ 核心不变量: 章内的一切（含 vn_enter）**不进真源**。"""
    st = _st(tmp_path)
    st.append_event(CHAR, "", make_event("mmt", "mmt_chat", {"text": "触发前"}))

    _do_chapter(st, boards=3, complete=False)      # 中断: 只有 vn_enter + 3 块板

    truth = st.events(CHAR)
    assert [e.type for e in truth] == ["mmt"], [e.type for e in truth]
    assert staging.staging_open(st, CHAR) is True
    assert len(staging.staging_events(st, CHAR)) == 4      # vn_enter + 3 板
    print(f"    真源仍只有 {len(truth)} 条; 暂存 {len(staging.staging_events(st, CHAR))} 条 ✓")


# ---------------------------------------------------------------------------
# 2. commit: 整段搬迁
# ---------------------------------------------------------------------------

def test_commit_moves_whole_chapter(tmp_path):
    """★ commit → 整段进真源、`ts` 保留、`seq` 重算、暂存删除。"""
    st = _st(tmp_path)
    st.append_event(CHAR, "", make_event("mmt", "mmt_chat", {"text": "前置"}))
    _do_chapter(st, boards=2, complete=True)

    staged = staging.staging_events(st, CHAR)
    staged_ts = [e.ts for e in staged]
    # ★ 暂存的 seq **接续真源**（真源已有 1 条 → 暂存从 2 起）—— 见 StagingStore docstring
    assert [e.seq for e in staged] == [2, 3, 4, 5], [e.seq for e in staged]

    n = staging.commit_staging(st, CHAR, "", completed=True)
    assert n == 4

    truth = st.events(CHAR)
    assert len(truth) == 5
    assert [e.seq for e in truth] == [1, 2, 3, 4, 5]       # 搬过去后仍是连续空间
    assert [e.ts for e in truth[-4:]] == staged_ts         # ★ ts **原样保留**
    assert [e.subtype for e in truth[-4:]] == [
        "vn_enter", "story_scene", "story_scene", "vn_exit"]
    assert staging.staging_events(st, CHAR) == []          # 暂存已删
    assert staging.staging_open(st, CHAR) is False
    print(f"    commit: 4 条整段搬入, ts 保留, seq 重算 {[e.seq for e in truth]}")


def test_commit_empty_is_noop(tmp_path):
    st = _st(tmp_path)
    assert staging.commit_staging(st, CHAR, "") == 0
    assert st.events(CHAR) == []
    print("    空暂存 → commit 零副作用")


# ---------------------------------------------------------------------------
# 3. 丢弃 = 删除的全部
# ---------------------------------------------------------------------------

def test_discard_is_the_whole_delete(tmp_path):
    """★ 「拒绝 / 从未进入」→ 丢缓存。**真源零变化, 没有任何 marker。**"""
    st = _st(tmp_path)
    st.append_event(CHAR, "", make_event("mmt", "mmt_chat", {"text": "前置"}))
    _do_chapter(st, boards=5, complete=False)

    assert staging.discard_staging(st, CHAR) is True

    truth = st.events(CHAR)
    assert len(truth) == 1                                  # 前置那条不动
    assert staging.staging_events(st, CHAR) == []
    # 关键: **真源里没有留下任何"宣告它没发生"的痕迹**
    assert not any(e.subtype in ("vn_abandon", "vn_exit") for e in truth)
    print("    丢弃: 真源零变化, 且无 abandon 痕迹（无任何读路径需要过滤）✓")


# ---------------------------------------------------------------------------
# 4. 不变量: commit 前收尾真源里的未闭合段
# ---------------------------------------------------------------------------

def test_close_open_attempts_before_commit(tmp_path):
    """★ 真源里若已有未闭合段（旧档 / 上次 commit 中断）→ 先补 `vn_exit completed=False`。"""
    st = _st(tmp_path)
    # 手工造一个未闭合段（模拟旧档 / 半截 commit）
    st.enter_vn(CHAR, "", "旧章")
    st.append_event(CHAR, "", make_event("bond", "story_scene", {"i": 0}))
    assert staging.open_attempt(st.events(CHAR)) is not None

    _do_chapter(st, boards=1, complete=True)
    staging.commit_staging(st, CHAR, "", completed=True)

    truth = st.events(CHAR)
    exits = [e for e in truth if e.subtype == "vn_exit"]
    assert len(exits) == 2, [e.subtype for e in truth]
    # 旧段被收尾为 completed=False（**不是 vn_abandon 的"没发生过"**）
    assert truth[2].subtype == "vn_exit" and truth[2].payload["completed"] is False
    assert truth[-1].payload["completed"] is True
    assert staging.open_attempt(truth) is None               # 不变量成立
    print("    收尾: 旧未闭合段 → vn_exit completed=False（语义 = 发生过但没读完）")


def test_close_open_attempts_is_idempotent(tmp_path):
    st = _st(tmp_path)
    assert staging.close_open_attempts(st, CHAR, "") == 0    # 无未闭合段
    st.enter_vn(CHAR, "", "A")
    assert staging.close_open_attempts(st, CHAR, "") == 1
    assert staging.close_open_attempts(st, CHAR, "") == 0    # 幂等
    print("    收尾幂等: 1 → 0")


# ---------------------------------------------------------------------------
# 5. 半截 commit 可重试
# ---------------------------------------------------------------------------

def test_partial_commit_keeps_staging_for_retry(tmp_path, monkeypatch):
    """★ 第 2 条 append 炸掉 → 真源留半截（语义正确）,**暂存保留可重试**。"""
    st = _st(tmp_path)
    _do_chapter(st, boards=3, complete=True)
    staged = staging.staging_events(st, CHAR)

    real = SessionStore.append_event
    calls = {"n": 0}

    def _boom(self, char_id, session_id="", event=None, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("模拟写盘失败")
        return real(self, char_id, session_id, event=event, **kw)

    monkeypatch.setattr(SessionStore, "append_event", _boom)
    try:
        staging.commit_staging(st, CHAR, "")
    except OSError:
        pass
    monkeypatch.setattr(SessionStore, "append_event", real)

    assert len(st.events(CHAR)) == 1                        # 半截
    assert staging.staging_events(st, CHAR) == staged       # ★ 暂存保留
    # 重试: 先收尾那半截, 再搬
    n = staging.commit_staging(st, CHAR, "")
    assert n == len(staged)
    truth = st.events(CHAR)
    assert staging.open_attempt(truth) is None              # 不变量恢复
    assert staging.staging_events(st, CHAR) == []
    print(f"    半截 commit: 真源留 1 条 → 重试后 {len(truth)} 条且闭合 ✓")


# ---------------------------------------------------------------------------
# 6. 路径与继承
# ---------------------------------------------------------------------------

def test_commit_without_vn_enter_does_not_close_current(tmp_path):
    """★ 收尾**是有条件的**：暂存不带 `vn_enter`（B-2 之前的过渡期 = 只装本章尾巴）
    → **不收尾真源** —— 否则真源里冒出两个 `vn_exit`, 而本章会被判成"没读完"。"""
    st = _st(tmp_path)
    st.enter_vn(CHAR, "", "本章")                        # 真源里**本章**在押
    st.append_event(CHAR, "", make_event("bond", "story_scene", {"i": 0}))
    sg = staging.staging_store(st)
    sg.append_marker(CHAR, "", "vn_exit", {"completed": True})    # 暂存只装尾巴

    staging.commit_staging(st, CHAR, "", completed=True)

    truth = st.events(CHAR)
    assert [e.subtype for e in truth] == ["vn_enter", "story_scene", "vn_exit"], \
        [e.subtype for e in truth]
    assert truth[-1].payload["completed"] is True        # 没被误判成 False
    print(f"    条件收尾: 暂存无 vn_enter → 不收尾（{len(truth)} 条, 闭合正确）")


def test_staging_store_shares_everything_but_path(tmp_path):
    """★ `StagingStore` 只覆盖 `events_path()` —— 其余与 `SessionStore` 同源。"""
    st = _st(tmp_path)
    sg = staging.staging_store(st)
    assert isinstance(sg, SessionStore)
    assert sg.data_root == st.data_root and sg.world_id == st.world_id
    assert staging.source_events_path(sg, CHAR) == st.events_path(CHAR)   # 不递归
    assert staging.staging_path(sg, CHAR) != st.events_path(CHAR)
    assert staging.staging_path(sg, CHAR).name == "events.jsonl"
    assert staging.staging_path(sg, CHAR).parent.name == "staging"
    print(f"    路径: {staging.staging_path(st, CHAR).relative_to(tmp_path)}")


# ---------------------------------------------------------------------------
# 7. overlay 语义（seq 接续 / 合并有序 / commit 写真源 / 线程）
# ---------------------------------------------------------------------------

def test_staging_seq_continues_truth(tmp_path):
    """★ 暂存 seq **接续真源** —— 章内不会出现两个撞号的 seq 空间。"""
    st = _st(tmp_path)
    for i in range(3):
        st.append_event(CHAR, "", make_event("mmt", "mmt_chat", {"i": i}))
    sg = staging.staging_store(st)
    sg.enter_vn(CHAR, "", "章")
    sg.append_event(CHAR, "", make_event("bond", "story_scene", {"i": 0}))
    assert [e.seq for e in staging.staging_events(st, CHAR)] == [4, 5]
    print("    暂存 seq 接续: 真源 1-3 → 暂存 4,5")


def test_overlay_is_ordered_union(tmp_path):
    """★ `StagingStore.events()` = 真源 + 暂存, 且**有序**; 章外 ≡ 真源。"""
    st = _st(tmp_path)
    sg = staging.staging_store(st)
    assert sg.events(CHAR) == []                       # 章外（暂存空）≡ 真源
    st.append_event(CHAR, "", make_event("mmt", "mmt_chat", {"i": 0}))
    assert [e.seq for e in sg.events(CHAR)] == [1]
    sg.enter_vn(CHAR, "", "章")
    sg.append_event(CHAR, "", make_event("bond", "story_scene", {"i": 0}))
    merged = sg.events(CHAR)
    assert [e.seq for e in merged] == [1, 2, 3]        # **连续** → 天然有序
    assert [e.type for e in merged] == ["mmt", "marker", "bond"]
    print("    合并视图: seq [1,2,3] 连续有序; 章外 ≡ 真源 ✓")


def test_commit_accepts_overlay_and_writes_truth(tmp_path):
    """★ `commit_staging(overlay)` 也必须**写真源** —— 否则写回暂存 = 死循环。"""
    st = _st(tmp_path)
    sg = staging.staging_store(st)
    sg.enter_vn(CHAR, "", "章")
    sg.append_event(CHAR, "", make_event("bond", "story_scene", {"i": 0}))
    sg.append_marker(CHAR, "", "vn_exit", {"completed": True})

    n = staging.commit_staging(sg, CHAR, "", completed=True)      # 传 **overlay**
    assert n == 3
    assert [e.type for e in st.events(CHAR)] == ["marker", "bond", "marker"]
    assert staging.staging_events(st, CHAR) == []                 # 暂存清空
    assert len(sg.events(CHAR)) == 3                              # 章外 ≡ 真源
    assert staging.truth_store(sg).data_root == st.data_root
    print("    commit(overlay): 写真源 / 清暂存 / 不死循环 ✓")


def test_thread_safe_seq_allocation(tmp_path):
    """★ 并发写暂存 → seq **不重复**（与 `SessionStore` 同一把进程级写锁）。"""
    import threading
    st = _st(tmp_path)
    sg = staging.staging_store(st)
    errs: list = []

    def _w(i):
        try:
            sg.append_event(CHAR, "", make_event("bond", "story_scene", {"i": i}))
        except Exception as e:                     # noqa: BLE001
            errs.append(e)

    ts = [threading.Thread(target=_w, args=(i,)) for i in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    seqs = sorted(e.seq for e in staging.staging_events(st, CHAR))
    assert not errs, errs
    assert len(seqs) == 12 and len(set(seqs)) == 12, seqs
    print(f"    并发写 12 条 → seq {seqs} 无重复 ✓")


# ---------------------------------------------------------------------------
# 8. 语义修正: 收尾是 vn_exit(False)，不是 vn_abandon
# ---------------------------------------------------------------------------

def test_supersede_semantics_is_exit_false_not_abandon(tmp_path):
    """★ 新章触发时旧在押段的收尾 = **`vn_exit completed=False`**（发生过但没读完）,
    **不是 `vn_abandon`**（"没发生过" —— 那会删掉她真实经历过的那半段）。

    复刻 `webgui.bond.bond_start` 的两步（顺序同代码）。
    """
    st = _st(tmp_path)
    st.enter_vn(CHAR, "", "旧章")                      # 真源里的未闭合段
    st.append_event(CHAR, "", make_event("bond", "story_scene", {"i": 0}))

    sg = staging.staging_store(st)                     # 暂存里的未闭合章
    sg.enter_vn(CHAR, "", "新章")
    sg.append_event(CHAR, "", make_event("bond", "story_scene", {"i": 1}))
    sg.append_marker(CHAR, "", "vn_exit", {"completed": False})

    staging.commit_staging(st, CHAR, "", completed=False)
    staging.close_open_attempts(st, CHAR, "")

    truth = st.events(CHAR)
    assert not any(e.subtype == "vn_abandon" for e in truth), "不应再写 vn_abandon"
    assert staging.open_attempt(truth) is None, "真源里不留未闭合段"
    exits = [e for e in truth if e.subtype == "vn_exit"]
    assert len(exits) == 2, [e.subtype for e in truth]
    assert all(e.payload["completed"] is False for e in exits)
    print(f"    收尾语义: vn_exit(False)×{len(exits)}、零 vn_abandon ✓")


def test_new_data_has_no_abandon_marker(tmp_path):
    """★ B0 之后 `vn_abandon` 不再产生 ⇒ `exclude_abandoned` 对新数据**空转**
    （它只为旧档保留）。"""
    from core.session.maintenance import exclude_abandoned
    st = _st(tmp_path)
    _do_chapter(st, boards=2, complete=True)
    staging.commit_staging(st, CHAR, "")
    staging.close_open_attempts(st, CHAR, "")

    truth = st.events(CHAR)
    assert len(truth) == 4
    assert not any(e.subtype == "vn_abandon" for e in truth)
    assert exclude_abandoned(truth) == truth           # 空转
    print("    新数据零 vn_abandon；exclude_abandoned 空转 ✓")


if __name__ == "__main__":
    import tempfile

    for fn in (test_chapter_stays_out_of_truth_source,
               test_commit_moves_whole_chapter,
               test_commit_empty_is_noop,
               test_discard_is_the_whole_delete,
               test_close_open_attempts_before_commit,
               test_close_open_attempts_is_idempotent,
               test_staging_store_shares_everything_but_path):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("all staging tests passed")
