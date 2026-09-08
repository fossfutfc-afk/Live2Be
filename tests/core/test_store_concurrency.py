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


def test_append_seq_unique_across_instances(tmp_path):
    """多实例写同一文件（chat 单例 vs routers/mmt 每请求实例的生产形态）:
    锁必须进程级——实例级锁会各持一把仍撞重复（2026-09-08 实测修复前复现）。"""
    st_a = SessionStore(tmp_path)
    st_b = SessionStore(tmp_path)

    def w(store, i: int) -> None:
        store.append_event("ch", "s", make_event("mmt", "mmt_chat", {"i": i}))

    ts = []
    for i in range(15):
        ts.append(threading.Thread(target=w, args=(st_a, i)))
        ts.append(threading.Thread(target=w, args=(st_b, 100 + i)))
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    evs = st_a.events("ch", "s")
    seqs = sorted(e.seq for e in evs)
    assert len(evs) == 30, f"丢事件: {len(evs)}"
    assert len(set(seqs)) == 30, f"跨实例重复 seq: {seqs}"
    assert seqs == list(range(1, 31)), f"seq 空洞/乱序: {seqs}"
