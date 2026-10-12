"""webgui chat 会话生命周期单测 —— ★ P1: **会话打开必须装填 brain 段**（2026-09-21）。

症状（真机）: 跑完一章之后（或任何一次重启之后）打开 MMT，角色"完全不记得"——
`wiki.jsonl` 数据是对的，但注入段是空串。日志指纹: `新会话` 之后**没有** `recall_read`。

机制: `start_session` 不清空也不重读 `_brain_injection`（`engine.py:374` 只初始化 `""`），
而 `_inject_brain` 此前只有 **digest 完成** / **resume** 两个调用点 ⇒ 新世界线会话空记忆。
而 `bond_finish` 会 `finish(ended=True)` ⇒ **每完成一章该会话即"结束"** ⇒ 章后必走新分支。

覆盖: ① 全新世界线开会话 → 注入非空且含 wiki 文本; ② 章末（session_end）后 + 引擎重建
（= 重启）同样有; ③（对照）resume 路径照旧; ④ 空库时**不报错**（宁缺勿错）。

运行: python -m pytest tests/webgui/test_chat_session.py
"""
import sys
from pathlib import Path

from core.brain import WikiStoreV2
from core.brain.nodes import make_node
from core.session import SessionStore
from webgui import chat, deps

CHARACTER = "igusa_haruka"
#: 模块级 store 快照（禁止硬编码真 data —— 同 test_bond 的纪律）
_ORIG_STORE = deps.store()

#: 一条**运行时** episode（真档形状: observed_fact + 非出厂 source）
NARRATION = "（测试记忆）她把帽子上的土拍得很干净。"
TS = "2026-09-21T22:16:15+08:00"


def _store_with_wiki(tmp_path, narration=NARRATION):
    st = SessionStore(tmp_path)
    if narration:
        ws = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
        ws.add(make_node("episode", narration=narration, significance=0.9,
                         observer=CHARACTER, ts=TS))
        ws.save()                       # 落盘（引擎另开一个 WikiStoreV2 读同一个文件）
    return st


def _cleanup():
    chat._engines.pop(CHARACTER, None)
    deps.set_store(_ORIG_STORE)


def _brain() -> str:
    return chat._engines[CHARACTER]._brain_injection or ""


def test_new_world_line_injects_brain(tmp_path):
    """★ 主线: 新世界线会话的 brain 段必须非空（修前是空串 ⇒ 角色无记忆）。"""
    st = _store_with_wiki(tmp_path)
    deps.set_store(st)
    chat._engines.pop(CHARACTER, None)
    try:
        res = chat.open_session(CHARACTER)
        assert res["new"] is True, res
        seg = _brain()
        assert "【角色记忆（brain）】" in seg, seg
        assert "帽子上的土" in seg, seg
        print("    新世界线开会话: brain 段已装填（含 wiki 节点）✓")
    finally:
        _cleanup()


def test_after_chapter_end_and_restart_still_injects(tmp_path):
    """★ 真机触发路径: 章末 `finish(ended=True)` + 引擎重建（重启）→ 仍要装填。

    这正是"跑完一章 + 看到 digest + 但她一无所知"的复现: 章末会话结束
    （`bond/api.py:504`）⇒ 下次打开无未结束会话 ⇒ 走新分支。
    """
    st = _store_with_wiki(tmp_path)
    deps.set_store(st)
    chat._engines.pop(CHARACTER, None)
    try:
        first = chat.open_session(CHARACTER)
        st.finish(CHARACTER, first["session_id"], ended=True)   # 章末（bond_finish 同款）
        chat._engines.pop(CHARACTER, None)                      # 模拟进程重启: 引擎重建
        res = chat.open_session(CHARACTER)
        # `new is True` = 走的是"新世界线"分支（没有未结束会话可 resume）
        # ——别断言 sid 不同: sid 带秒级时间戳, 同秒内 create 会拿到同一个 id（与 P1 无关）
        assert res["new"] is True, res
        seg = _brain()
        assert "【角色记忆（brain）】" in seg and "帽子上的土" in seg, seg
        print("    章末 + 重启后开会话: brain 段照样装填 ✓")
    finally:
        _cleanup()


def test_resume_path_still_injects(tmp_path):
    """对照: 有未结束会话 → resume（本来就注入, 本次改动不得影响）。"""
    st = _store_with_wiki(tmp_path)
    deps.set_store(st)
    chat._engines.pop(CHARACTER, None)
    try:
        chat.open_session(CHARACTER)
        chat._engines.pop(CHARACTER, None)                      # 重启: 引擎重建
        res = chat.open_session(CHARACTER)                      # 会话还开着 → resume
        assert res["new"] is False, res
        assert "帽子上的土" in _brain()
        print("    resume 路径: 注入照旧 ✓")
    finally:
        _cleanup()


def test_empty_wiki_does_not_break_open_session(tmp_path):
    """宁缺勿错: 空 wiki（没有节点）也要能开会话 —— 不抛、不阻断。"""
    st = _store_with_wiki(tmp_path, narration="")
    deps.set_store(st)
    chat._engines.pop(CHARACTER, None)
    try:
        res = chat.open_session(CHARACTER)
        assert res["new"] is True and res["display_name"], res
        print("    空库: 开会话零阻断（brain 段可能只有出厂背景/为空）✓")
    finally:
        _cleanup()
