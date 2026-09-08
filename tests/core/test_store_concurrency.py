# -*- coding: utf-8 -*-
"""SessionStore 并发写测试（2026-09-08）: seq 分配在写锁内原子化——
wrapup 线程与 chat worker 并发落库不得撞出重复 seq（前端按 seq 推进游标,
重复行会被吞掉 → MMT 回复不渲染的元凶之一）。"""
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.session.events import make_event
from core.session.store import SessionStore


def test_append_seq_unique_under_concurrency(tmp_path):
    """30 线程并发 append 同一角色线 → seq 恰好 1..30 无重复无空洞。"""
    st = SessionStore(tmp_path)

    def w(i: int) -> None:
        st.append_event("ch", "s", make_event("mmt", "mmt_chat", {"i": i}))

    ts = [threading.Thread(target=w, args=(i,)) for i in range(30)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    evs = st.events("ch", "s")
    seqs = sorted(e.seq for e in evs)
    assert len(evs) == 30, f"丢事件: {len(evs)}"
    assert len(set(seqs)) == 30, f"重复 seq: {seqs}"
    assert seqs == list(range(1, 31)), f"seq 空洞/乱序: {seqs}"
