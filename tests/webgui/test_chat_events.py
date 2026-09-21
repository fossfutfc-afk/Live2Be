# -*- coding: utf-8 -*-
"""webgui chat 事件渲染单测 — bond 入口气泡: 进行中=粉泡 / 已完成=淡行。

2026-09-07 气泡淡化: 完整走完的剧情（vn_exit completed=True）入口横幅
kind=bond_done 淡行（不可点）; 中断（completed=False）保持可点击续进。
覆盖: render_chat_events / _bond_done_map / events_after 的 bond_done 字段。
运行: python -m pytest tests/webgui/test_chat_events.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.session import SessionStore
from core.session.events import make_event
from webgui import chat, deps

CHARACTER = "igusa_haruka"
TITLE = "放学后的约定"


def _store_with(tmp_path):
    st = SessionStore(tmp_path)
    sid = st.create(CHARACTER).session_id
    return st, sid


def _trigger(st, sid, title=TITLE):
    ev = make_event("mmt", "mmt_trigger_bond_story",
                    {"player": "去逛逛吧", "reply": "嗯！好呀……",
                     "chapter_title": title})
    return st.append_event(CHARACTER, sid, ev)


def _enter(st, sid, title=TITLE):
    st.append_marker(CHARACTER, sid, "vn_enter", {"chapter_title": title})


def _exit(st, sid, completed=True):
    st.append_marker(CHARACTER, sid, "vn_exit", {"completed": completed})


def _entry_bubble(bubbles):
    got = [b for b in bubbles
           if b.get("kind") in ("bond_entry", "bond_done")]
    assert len(got) == 1, bubbles
    return got[0]


def test_bond_done_renders_dim_line(tmp_path):
    """完整走完 → 入口横幅淡化为 '已完成羁绊剧情：{标题}'（不可点）。"""
    st, sid = _store_with(tmp_path)
    trig = _trigger(st, sid)
    _enter(st, sid, TITLE)
    _exit(st, sid, completed=True)
    evs = st.events(CHARACTER, sid)
    done = chat._bond_done_map(evs, "遥香")
    b = _entry_bubble(chat.render_chat_events(
        evs, "遥香", bond_done=done))
    assert b["kind"] == "bond_done"
    assert b["text"] == f"已完成羁绊剧情：{TITLE}"
    assert b["seq"] == trig.seq                # seq 保留供前端去重/翻转
    # 无完成 map（增量早期视角）→ 仍是可点击入口（触发与收尾可能跨轮询）
    b2 = _entry_bubble(chat.render_chat_events(evs, "遥香"))
    assert b2["kind"] == "bond_entry"


def test_bond_interrupted_keeps_clickable(tmp_path):
    """中途退出（completed=False）→ 保持粉泡（resumed 续进语义）。"""
    st, sid = _store_with(tmp_path)
    trig = _trigger(st, sid)
    _enter(st, sid, TITLE)
    _exit(st, sid, completed=False)
    evs = st.events(CHARACTER, sid)
    done = chat._bond_done_map(evs, "遥香")
    assert trig.seq not in done
    b = _entry_bubble(chat.render_chat_events(evs, "遥香", bond_done=done))
    assert b["kind"] == "bond_entry"


def test_events_after_carries_bond_done_for_flip(tmp_path):
    """events_after: 完成态从全量事件流算——增量轮询也能拿到 [{seq,text}] 翻转粉泡。"""
    old_store = deps.store()
    st, sid = _store_with(tmp_path)
    deps.set_store(st)
    try:
        trig = _trigger(st, sid)                 # 只触发, 尚未走剧情
        r1 = chat.events_after(CHARACTER, sid, since=0, display_name="遥香")
        assert r1["bond_done"] == []
        entry = [b for b in r1["bubbles"]
                 if b.get("kind") == "bond_entry"]
        assert entry, r1["bubbles"]

        # 剧情走完（enter + exit 落库）→ 下一轮增量轮询携带完成信息（无新气泡）
        _enter(st, sid, TITLE)
        _exit(st, sid, completed=True)
        r2 = chat.events_after(CHARACTER, sid, since=trig.seq,
                               display_name="遥香")
        assert r2["bond_done"] == [{"seq": trig.seq,
                                    "text": f"已完成羁绊剧情：{TITLE}"}]
        # 历史全量视角: 气泡直接是淡行（kind=bond_done）
        rh = chat.events_after(CHARACTER, sid, since=0, display_name="遥香")
        kinds = {b.get("kind") for b in rh["bubbles"]
                 if b.get("kind") in ("bond_entry", "bond_done")}
        assert kinds == {"bond_done"}
    finally:
        deps.set_store(old_store)


def test_bond_done_title_fallback(tmp_path):
    """旧事件无 chapter_title → 标题回落 display_name（不落空）。"""
    st, sid = _store_with(tmp_path)
    trig = _trigger(st, sid, title="")
    _enter(st, sid, title="")
    _exit(st, sid, completed=True)
    done = chat._bond_done_map(st.events(CHARACTER, sid), "遥香")
    assert done[trig.seq] == "已完成羁绊剧情：遥香"


def test_reset_engines_keeps_per_char_lock():
    """设置变更重建引擎时**不得**清掉同角色串行锁（2026-09-13 审计 B17）。

    锁是并发保护而非引擎的一部分: 一次 `agent_turn` 可能正持着旧 Lock 在跑,
    清掉 `_locks` 后新调用者会拿到**另一个 Lock** → 同角色两个 turn 并行跑,
    串行不变量被打破（会话/事件流都可能写乱）。
    """
    old_engines = dict(chat._engines)
    old_locks = dict(chat._locks)
    try:
        chat._engines.clear()
        chat._locks.clear()
        lock = chat._lock(CHARACTER)
        lock.acquire()                            # 模拟"某次 turn 正持锁在跑"
        try:
            chat._engines[CHARACTER] = object()   # 有个旧引擎待清
            chat.reset_engines()
            assert not chat._engines, "引擎应被清空（下次按新配置重建）"
            assert chat._lock(CHARACTER) is lock, \
                "锁被换掉了 → 同一角色会出现两个并发 turn"
        finally:
            lock.release()
    finally:
        chat._engines.clear(); chat._engines.update(old_engines)
        chat._locks.clear(); chat._locks.update(old_locks)
    print("    reset_engines: 清引擎但保住串行锁（并发不变量不破）")
