# -*- coding: utf-8 -*-
"""随身笔记的**注入接线**（链路 ①-第三步·下, 2026-09-23）。

两个注入点都得有它（**常驻层**, 每轮都在）:

    · `load_brain_segment`   —— bond 开场（`webgui.bond` / `apps.vn_cli` 共用）
    · `MmtEngine._inject_brain` —— MMT 会话（digest 完成 / resume / 开会话）

拼接顺序 = 出厂背景 → wiki 视图 → **笔记块**（放最后: 最贴近本轮对话的是"此刻"）→
时间注记（VN 侧那个每轮都在变的动态尾巴）。空笔记 → **一个字的块都不出现**。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain.wiki_v2 import notes
from core.mmt.engine import MomoTalkEngine, load_brain_segment, load_note_segment
from core.session import SessionStore, make_event

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "config" / "characters"
CHARACTER = "igusa_haruka"


class _NoLLM:
    """`digest=False` 不该有任何 LLM 调用 —— 一被调就炸。"""

    def chat(self, *a, **kw):                          # pragma: no cover
        raise AssertionError("注入路径不该调 LLM")


def _session(tmp_path):
    st = SessionStore(data_root=tmp_path)
    root = st.create(CHARACTER, "测试")
    return st, root


def _mmt_event(st):
    st.append_event(CHARACTER, "", make_event(
        "mmt", "chat", {"player": "在吗", "reply": "在的"}))


def _add_note(st, text="周六模型店", refs=("m0009",)):
    st.append_event(CHARACTER, "", notes.note_event(notes.add_op(text, refs)))


# ---------------------------------------------------------------------------
# bond 开场（load_brain_segment）
# ---------------------------------------------------------------------------

def test_bond_segment_carries_the_note_block_before_time_notes(tmp_path):
    st, _root = _session(tmp_path)
    _mmt_event(st)                                     # 时间注记要有内容事件可依
    _add_note(st)

    seg = load_brain_segment(st, CHARACTER, "伊草 遥香", CONFIG)

    assert notes.TITLE in seg
    assert "周六模型店" in seg and "(m0009)" in seg
    # 位置: 在**时间注记之前**（那是每轮都在变的动态尾巴, 一直在最后）
    assert seg.index(notes.TITLE) < seg.index("【她刚刚还在和老师说话】")


def test_bond_segment_has_no_block_when_there_is_no_note(tmp_path):
    st, _root = _session(tmp_path)
    _mmt_event(st)
    seg = load_brain_segment(st, CHARACTER, "伊草 遥香", CONFIG)

    assert notes.TITLE not in seg
    assert load_note_segment(st, CHARACTER) == ""


# ---------------------------------------------------------------------------
# MMT 会话（_inject_brain）
# ---------------------------------------------------------------------------

def _engine(tmp_path):
    st = SessionStore(data_root=tmp_path)
    engine = MomoTalkEngine(CONFIG, _NoLLM(), store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    return engine, st


def test_mmt_injection_carries_the_note_block_last(tmp_path):
    engine, st = _engine(tmp_path)
    engine._inject_brain(CHARACTER)
    assert notes.TITLE not in engine._brain_injection      # 还没记过东西 → 没有块

    _add_note(st)
    engine._inject_brain(CHARACTER)                        # ⚠️ 写完要重建（串是缓存的）
    inj = engine._brain_injection

    assert notes.TITLE in inj and "周六模型店" in inj
    # 最后一段（出厂背景在前; 笔记块是**收尾**的那一段）
    assert inj.index("【背景经历") < inj.index(notes.TITLE)
    assert inj.rstrip().endswith(load_note_segment(st, CHARACTER).rstrip())


# ---------------------------------------------------------------------------
# 宁缺勿错
# ---------------------------------------------------------------------------

def test_note_segment_degrades_silently_on_failure():
    class _Broken:
        data_root = "不存在的根"
        world_id = "world1"

        def events(self, char_id):
            raise RuntimeError("读不动")

    assert load_note_segment(_Broken(), CHARACTER) == ""
