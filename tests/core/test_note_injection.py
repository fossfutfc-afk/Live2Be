"""随身笔记的**注入接线**（链路 ①-第三步·下, 2026-09-23）。

两个注入点都得有它（**常驻层**, 每轮都在）:

    · `load_brain_segment`   —— bond 开场（`webgui.bond` / `cli.vn_cli` 共用）
    · `MmtEngine._inject_brain` —— MMT 会话（digest 完成 / resume / 开会话）

拼接顺序 = 出厂背景 → wiki 视图 → **笔记块**（放最后: 最贴近本轮对话的是"此刻"）→
时间注记（VN 侧那个每轮都在变的动态尾巴）。空笔记 → **一个字的块都不出现**。
"""
import sys
from pathlib import Path

from core.brain import WikiStoreV2, make_node, notes
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


def _titled_ref(st, node_id="m0009", title="模型店的午后"):
    """建一条**有名字**的 episode（refs 印名字需要它在图上）—— ⚠️ `store.add` 只改内存, 要 save。"""
    ws = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
    ws.add(make_node("episode", text="那天在模型店", title=title, event_seq=[1],
                     id=node_id))
    ws.save()


# ---------------------------------------------------------------------------
# bond 开场（load_brain_segment）
# ---------------------------------------------------------------------------

def test_bond_segment_carries_the_note_block_before_time_notes(tmp_path):
    st, _root = _session(tmp_path)
    _mmt_event(st)                                     # 时间注记要有内容事件可依
    _add_note(st)

    seg = load_brain_segment(st, CHARACTER, "伊草 遥香", CONFIG)

    assert notes.TITLE in seg
    assert "周六模型店" in seg

    # ⭐ N4a: refs 印**名字**（`m0009` 指不到就不印 —— 印一个她读不懂的编号是违规）
    _titled_ref(st)
    seg2 = load_brain_segment(st, CHARACTER, "伊草 遥香", CONFIG)
    assert "(《模型店的午后》)" in seg2 and "(m0009)" not in seg2
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
# 备忘录体检 / 台账: 必须量**真的那一块**
# ---------------------------------------------------------------------------

def test_health_check_measures_the_real_injected_block(tmp_path, caplog):
    """`check` / `stats` 的字数 = **真注入块**的长度, 不是"不带名字/时间"的那一版。

    两件事一起钉:
      · 引擎传进去的 `block_chars` 与 `load_note_segment` 的输出**同长**;
      · 那一块**确实比裸渲染长**（否则这条判据就是自欺 —— `titles` / `now` 白给了）。
    """
    import logging
    caplog.set_level(logging.INFO)

    engine, st = _engine(tmp_path)
    _titled_ref(st)                       # 有名字的 episode → 条目尾巴才带 (《…》)
    _add_note(st)
    events = st.events(CHARACTER)
    wstore = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)

    real = load_note_segment(st, CHARACTER, wstore=wstore, events=events)
    bare = notes.render_note_block(notes.fold(events))
    assert len(real) > len(bare), "裸渲染没短 —— 这条用例失去意义"

    engine._write_note_ops(st, wstore, CHARACTER, events, [])

    line = next(ln for ln in caplog.text.splitlines() if "note 台账" in ln)
    reported = int(line.rsplit("注入块 ", 1)[1].split(" 字", 1)[0])
    assert reported == len(real), (reported, len(real), line)
    print(f"    台账报 {reported} 字 = 真注入块（裸渲染只有 {len(bare)} 字）✓")


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
