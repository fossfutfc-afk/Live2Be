"""两阶段提交 —— 点 / 边 / 水位三份文件要么全变、要么全不变。

为什么需要: 从前提交是"先 `save()` 图、后 `save_meta()`"两次原子替换, 中间被进程杀掉
（Ctrl+C / 崩溃 / 任务管理器）就留下"图新、水位旧"或"点新、边旧"。前者的后果是同一批
事件被再喂一遍（正文不同就多出一份记忆）。

现在的做法: 先把三份内容一次性原子写进 `wiki.txn.json`, 再逐份覆盖真文件, 最后删日志;
**加载时若发现日志残留就照它把三份补齐**（幂等, 重放结果不变）。

跑法: python -m pytest tests/core/test_wiki_commit.py
"""
from core.brain import WikiStoreV2
from core.brain import store as store_mod
from core.brain.entities import ensure_entities
from core.brain.nodes import make_node

CHAR = "c"


def _wiki(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    ensure_entities(st, char_name="伊草 遥香", sensei_name="老师")
    st.commit()
    return st


def _reopen(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)


def test_commit_writes_three_files_and_clears_the_journal(tmp_path):
    st = _wiki(tmp_path)
    st.add(make_node("episode", text="模型店门口", event_seq=[3], ts="2026-10-17"))
    st.meta["digested_seq"] = 3
    st.commit()

    assert not st.txn_path.exists(), "提交完日志必须删掉"
    again = _reopen(tmp_path)
    assert [n.text for n in again.all() if n.kind == "episode"] == ["模型店门口"]
    assert again.digested_seq == 3, "水位随同一个事务落盘"
    print("    提交: 点 / 边 / 水位一起落, 日志清掉")


def test_interrupted_commit_is_rolled_forward_on_load(tmp_path, monkeypatch):
    """日志写完之后被杀（应用阶段失败）⇒ 下次加载照日志补完, 三份一致。"""
    st = _wiki(tmp_path)
    st.add(make_node("episode", text="约好生日一起吃蛋糕", event_seq=[7], ts="2026-10-17"))
    st.meta["digested_seq"] = 7

    def _boom(*_a, **_kw):
        raise OSError("模拟断电")

    monkeypatch.setattr(store_mod, "atomic_write_lines", _boom)
    try:
        raised = False
        try:
            st.commit()
        except OSError:
            raised = True
        assert raised, "应用阶段失败必须抛出（不假装成功）"
        assert st.txn_path.exists(), "日志必须还在（下次加载靠它补完）"
        # 真文件还是旧的: 这条 episode 在磁盘上不存在
        assert "约好生日" not in st.path.read_text(encoding="utf-8")
    finally:
        monkeypatch.undo()

    healed = _reopen(tmp_path)
    assert [n.text for n in healed.all() if n.kind == "episode"] == ["约好生日一起吃蛋糕"]
    assert healed.digested_seq == 7, "水位也一起补上（否则同一批会被再喂一遍）"
    assert not healed.txn_path.exists(), "补完之后日志要删掉"
    print("    断电后被杀: 加载时补完点 / 边 / 水位, 日志清掉")


def test_broken_journal_is_discarded(tmp_path):
    """日志本身读不出来（半截 / 形状不对）⇒ 丢掉它, 以现有文件为准, 不许炸。"""
    st = _wiki(tmp_path)
    st.add(make_node("episode", text="留下的一条", event_seq=[1], ts="2026-10-17"))
    st.commit()
    st.txn_path.write_text("{ 这不是 json", encoding="utf-8")

    again = _reopen(tmp_path)
    assert not again.txn_path.exists(), "坏日志要清掉"
    assert [n.text for n in again.all() if n.kind == "episode"] == ["留下的一条"]
    print("    坏日志: 丢弃, 现有文件不受影响")


def test_save_is_a_commit(tmp_path):
    """`save()` 走同一个事务（否则还有第二条没保护的写路径）。"""
    st = _wiki(tmp_path)
    st.add(make_node("episode", text="走 save 的那条", event_seq=[2], ts="2026-10-17"))
    st.save()
    assert not st.txn_path.exists()
    assert any(n.text == "走 save 的那条" for n in _reopen(tmp_path).all())
