"""B0 整章暂存 —— **webgui 层接线**（2026-09-17）。

钉住的是"接线对了没有"，产品机制本身在 `tests/core/test_session_staging.py`。
旧的"章内内容落在真源里"的用例已随 B0 失效并摘除（断言前提不存在了）。

三件事：
  1. `_flow_store(state)` = **overlay**（章外逐字节等价于真源）
  2. **章内写 → 真源零变化**，而 overlay 看得见
  3. `_pending_in_vn` 章内为 True（章内的 `vn_enter` 在暂存里，只读真源会漏判）
"""
from __future__ import annotations

import sys
from pathlib import Path


from core.session.events import make_event                      # noqa: E402
from core.session.store import SessionStore                     # noqa: E402
from webgui import bond, deps                                   # noqa: E402
from webgui.bond import BondState                               # noqa: E402

CHAR = "igusa_haruka"


def _mk(tmp_path, monkeypatch):
    """tmp 世界线 + 把 `deps._store` 指过去（`_pending_in_vn` 用它兜底）。"""
    st = SessionStore(tmp_path, world_id="w1")
    monkeypatch.setattr(deps, "_store", st)
    return st, BondState(store=st)


def test_flow_store_is_overlay(tmp_path, monkeypatch):
    """★ `_flow_store` 返回 **overlay**；章外 ≡ 真源（所以无条件用它是对的）。"""
    st, state = _mk(tmp_path, monkeypatch)
    fs = bond._flow_store(state)
    assert fs is not st and fs.data_root == st.data_root
    assert fs.world_id == st.world_id

    st.append_event(CHAR, "", make_event("mmt", "mmt_chat", {"i": 0}))
    assert [e.seq for e in fs.events(CHAR)] == [1]              # 章外 ≡ 真源
    print("    _flow_store: overlay；章外 ≡ 真源 ✓")


def test_chapter_content_stays_out_of_truth(tmp_path, monkeypatch):
    """★ **核心**: 章内写经 `_flow_store` → 真源**零变化**，而 overlay 看得见。"""
    st, state = _mk(tmp_path, monkeypatch)
    st.append_event(CHAR, "", make_event("mmt", "mmt_chat", {"i": 0}))   # 章前

    fs = bond._flow_store(state)
    fs.enter_vn(CHAR, "", "测试章")
    fs.append_event(CHAR, "", make_event("bond", "story_scene", {"i": 0}))

    assert [e.type for e in st.events(CHAR)] == ["mmt"]         # ★ 真源零变化
    assert len(fs.events(CHAR)) == 3                            # overlay 看得见
    assert bond._pending_in_vn(CHAR, "") is True                # ★ 章内 = 在押
    print(f"    章内: 真源 {len(st.events(CHAR))} 条 / overlay {len(fs.events(CHAR))} 条 ✓")


def test_pending_in_vn_false_outside_chapter(tmp_path, monkeypatch):
    """章外（暂存空）→ `_pending_in_vn` 为 False（overlay ≡ 真源，不误判）。"""
    st, state = _mk(tmp_path, monkeypatch)
    st.append_event(CHAR, "", make_event("mmt", "mmt_chat", {"i": 0}))
    assert bond._pending_in_vn(CHAR, "") is False
    print("    章外: _pending_in_vn=False ✓")


# ---------------------------------------------------------------------------
# ⭐ 回归（2026-09-30）: staged 预热分支「本章刚提交后**不许**再无条件收尾」
#
# 真机 bug（事件流铁证见 327821c 的提交信息）:
#     moved = commit_staging(...)                 # 本章（含 vn_enter）进真源
#     close_open_attempts(truth)                  # ⚠️ 无条件 ⇒ 把【本章】判成"没读完"
#   ⇒ 真源里冒出第二个 vn_exit（reason=staging:superseded）
#   ⇒ `_bond_done_map` 顺序配对被提前关闭（MMT 完成淡行永不出现）
#      · `replayable_chapters` 认不出这一章（回忆册 0 章）
# ---------------------------------------------------------------------------

def test_commit_then_close_would_kill_the_chapter(tmp_path, monkeypatch):
    """⭐ `_close_stale_attempts` 在**搬过东西**时必须什么都不做（否则杀掉本章）。"""
    from core.session import staging as staging_mod
    from webgui.bond.entry import _close_stale_attempts

    st, state = _mk(tmp_path, monkeypatch)
    st.append_event(CHAR, "", make_event("mmt", "mmt_trigger_bond_story",
                                         {"chapter_title": "测试章"}))
    fs = bond._flow_store(state)
    fs.enter_vn(CHAR, "", "测试章")                       # 章内 ⇒ 落暂存
    fs.append_event(CHAR, "", make_event("bond", "story_scene", {"i": 0}))

    moved = staging_mod.commit_staging(fs, CHAR, "", completed=False)
    assert moved == 2                                    # vn_enter + 板 都搬进真源
    assert staging_mod.open_attempt(st.events(CHAR)) is not None   # 真源里那一段就是【本章】

    # ⭐ 修好的调用: 搬了东西 ⇒ **不碰**
    _close_stale_attempts(fs, CHAR, "", moved=moved)
    assert [e.subtype for e in st.events(CHAR) if e.is_marker] == ["vn_enter"]
    assert staging_mod.open_attempt(st.events(CHAR)) is not None

    # ⚠️ 反证: 无条件收尾（修之前那一行）会给【本章】补一条假的 vn_exit
    staging_mod.close_open_attempts(st, CHAR, "")
    exits = [e for e in st.events(CHAR)
             if e.is_marker and e.subtype == "vn_exit"]
    assert len(exits) == 1
    assert exits[0].payload.get("reason") == "staging:superseded"
    print("    搬过东西 ⇒ 不碰本章；无条件收尾 ⇒ 假 vn_exit（反证）✓")


def test_close_stale_attempts_fires_when_nothing_moved(tmp_path, monkeypatch):
    """暂存为空 + 真源里有陈旧未闭合段（崩溃半截）⇒ **要收**（这是它存在的理由）。"""
    from core.session import staging as staging_mod
    from webgui.bond.entry import _close_stale_attempts

    st, state = _mk(tmp_path, monkeypatch)
    st.enter_vn(CHAR, "", "上一章")                       # 真源: 未闭合的旧段
    assert staging_mod.open_attempt(st.events(CHAR)) is not None
    _close_stale_attempts(bond._flow_store(state), CHAR, "", moved=0)
    exits = [e for e in st.events(CHAR)
             if e.is_marker and e.subtype == "vn_exit"]
    assert len(exits) == 1 and exits[0].payload.get("completed") is False
    assert staging_mod.open_attempt(st.events(CHAR)) is None
    # 幂等: 再收一次无事发生
    _close_stale_attempts(bond._flow_store(state), CHAR, "", moved=0)
    assert len([e for e in st.events(CHAR)
                if e.is_marker and e.subtype == "vn_exit"]) == 1
    print("    暂存为空 ⇒ 收陈旧残留（且幂等）✓")
