"""mmt 会话窗口 digest 测试（蓝图 §3.1: N=25 触发 + in_vn/in_memorial 保护）。

覆盖 momotalk 引擎的运行时 digest 接线（wiki_v2, 2026-09-02 切换）:
    - _maybe_mmt_digest: 25 轮触发 → 后台 digest 闭环（seed+提炼+好感事件落库）
    - 剧情中（in_vn）不触发
    - digest 增量: 无新增事件 → 0 次 LLM 调用（空跑无害）
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.momotalk import MMT_DIGEST_INTERVAL, MomoTalkEngine
from core.session import SessionStore

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


class ScriptedLLM:
    """chat 记录调用; 两轮 digest 返回空包（与 test_bond 同构）。"""

    def __init__(self):
        self.snapshots: list[list[dict]] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        self.snapshots.append([dict(m) for m in messages])
        head = messages[0]["content"]
        if "记录员" in head:
            return {"episodes": []}
        if "整理者" in head:
            return {"decisions": [], "evidence": [], "affection_exp_delta": 5}
        raise RuntimeError("非 digest 调用不应发生")

    @property
    def llm_calls(self) -> int:
        return len(self.snapshots)


def _engine(tmp_path):
    st = SessionStore(tmp_path)
    llm = ScriptedLLM()
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    return engine, st, llm


def _wait(pred, timeout=10.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return False


def _mmt_event(st, char_id, seq_base):
    """补一段 mmt 互动事件（digest 有输入可提炼——空包下也推进水位）。"""
    from core.session.events import make_event
    st.append_event(char_id, "", make_event(
        "mmt", "chat", {"player": f"消息{seq_base}", "reply": "回复"}))


def test_mmt_window_trigger_digests(tmp_path):
    """_session_rounds=25 → _maybe_mmt_digest → 后台 digest 完成:
    seed（出厂基座）+ 水位推进 + 好感事件落库。"""
    engine, st, llm = _engine(tmp_path)
    _mmt_event(st, CHARACTER, 1)                # 有事件可消化
    engine._session_rounds = MMT_DIGEST_INTERVAL  # 模拟 25 轮已记录

    assert engine._maybe_mmt_digest() is None   # 仅触发（返回 None）
    # 后台 digest: seed（0 LLM）+ A/B 两轮空包 → 好感 5 落 affection 事件
    assert _wait(lambda: any(
        e.type == "affection" and e.subtype == "digest"
        for e in st.events(CHARACTER))), "25 轮触发后应有好感事件"
    assert llm.llm_calls == 2                   # 恰好 A+B 两轮
    # 出厂基座落库（soul/ = 记忆层——wiki 与 events 同居, 2026-09-04）
    wiki = (Path(tmp_path) / "worlds" / "world1" / "characters" / CHARACTER
            / "soul" / "wiki.jsonl")
    assert wiki.exists() and wiki.stat().st_size > 0
    # 注入段已刷新（下一轮自动生效）
    assert "【角色记忆" in engine._brain_injection
    assert "老师" in engine._brain_injection or "遥香" in engine._brain_injection


def test_mmt_window_skipped_in_vn(tmp_path):
    """剧情中（vn_enter 无 vn_exit）→ 不触发（bond 闭环自会消化）。"""
    engine, st, llm = _engine(tmp_path)
    st.enter_vn(CHARACTER)                      # in_vn = True
    engine._session_rounds = MMT_DIGEST_INTERVAL
    engine._maybe_mmt_digest()
    time.sleep(0.3)                             # 留窗口——误触发应已落库
    assert not any(e.type == "affection" for e in st.events(CHARACTER))
    assert llm.llm_calls == 0


def test_window_below_interval_no_trigger(tmp_path):
    """未到 25 轮 → 不触发。"""
    engine, st, llm = _engine(tmp_path)
    _mmt_event(st, CHARACTER, 1)
    engine._session_rounds = MMT_DIGEST_INTERVAL - 1
    engine._maybe_mmt_digest()
    time.sleep(0.3)
    assert not any(e.type == "affection" for e in st.events(CHARACTER))
    assert llm.llm_calls == 0


def test_digest_idempotent_no_new_events(tmp_path):
    """第二次 digest（水位已推进）→ 0 次 LLM 调用（0 新增短路）。"""
    engine, st, llm = _engine(tmp_path)
    _mmt_event(st, CHARACTER, 1)
    engine._session_rounds = MMT_DIGEST_INTERVAL
    engine._maybe_mmt_digest()
    assert _wait(lambda: llm.llm_calls == 2), "首次 digest 应 A+B 两轮"
    calls_after_first = llm.llm_calls
    # 同水位再触发 → digest_segment 无新增 → 0 调用
    engine._session_rounds = MMT_DIGEST_INTERVAL * 2
    engine._maybe_mmt_digest()
    assert _wait(lambda: engine._brain_injection != ""), "注入段应存在"
    time.sleep(0.5)
    assert llm.llm_calls == calls_after_first   # 空跑无害
