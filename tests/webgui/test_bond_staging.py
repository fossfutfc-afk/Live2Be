# -*- coding: utf-8 -*-
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.session.events import make_event                      # noqa: E402
from core.session.store import SessionStore                     # noqa: E402
from webgui import bond                                         # noqa: E402
from webgui.bond import BondState                               # noqa: E402

CHAR = "igusa_haruka"


def _mk(tmp_path, monkeypatch):
    """tmp 世界线 + 把 `bond._store()` 指过去（`_pending_in_vn` 用它兜底）。"""
    st = SessionStore(tmp_path, world_id="w1")
    monkeypatch.setattr(bond, "_store", lambda: st)
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
