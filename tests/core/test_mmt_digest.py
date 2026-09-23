"""mmt 会话窗口 digest 测试（蓝图 §3.1: N=25 触发 + in_vn/in_memorial 保护）。

覆盖 momotalk 引擎的运行时 digest 接线（wiki_v2, 2026-09-02 切换）:
    - _maybe_mmt_digest: 25 轮触发 → 后台 digest 闭环（seed+提炼+好感事件落库）
    - 剧情中（in_vn）不触发
    - digest 增量: 无新增事件 → 0 次 LLM 调用（空跑无害）
    - **第一次 digest 前建 self/sensei 两个 entity**（§3.0 / §9-7, 2026-09-23）
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.mmt.engine import MMT_DIGEST_INTERVAL, MomoTalkEngine
from core.session import SessionStore
from tests import stub_tasks

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


class ScriptedLLM:
    """chat 记录调用; 两轮 digest 按 **task** 返回空包（与 test_bond 同构）。"""

    def __init__(self):
        self.snapshots: list[list[dict]] = []
        self.tasks: list[str | None] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        task = kw.get("task")
        self.snapshots.append([dict(m) for m in messages])
        self.tasks.append(task)
        reply = stub_tasks.annotation_reply(task, messages, digest_b_delta=5)
        if reply is not None:
            return reply
        raise RuntimeError(f"非 digest 调用不应发生（task={task!r}）")

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
    """补一段 mmt 互动事件（digest 有输入可提炼——空包下也推进水位）。

    subtype = `mmt_chat`（与生产一致: `_log_events` 落的是 registry 动作名, 真机
    events.jsonl 里就是 `mmt_chat`）。2026-09-13 修正: 此前写的是 `"chat"`——一个
    **生产里不存在的 subtype**, 而 E11 的轮数恢复正是按 `mmt_chat` 计数, 于是
    "事件条数 == 轮数"这条 invariant 在测试里失真（用例会假红/假绿）。
    """
    from core.session.events import make_event
    st.append_event(char_id, "", make_event(
        "mmt", "mmt_chat", {"player": f"消息{seq_base}", "reply": "回复"}))


def test_mmt_window_trigger_digests(tmp_path):
    """_session_rounds=25 → _maybe_mmt_digest → 后台 digest 完成:
    水位推进 + 好感事件落库（2026-09-05 解耦: 出厂基座不再 seed 进 wiki——
    出厂背景 = experience.yml 原文直注, wiki 只存 digest 产物）。"""
    engine, st, llm = _engine(tmp_path)
    _mmt_event(st, CHARACTER, 1)                # 有事件可消化
    engine._session_rounds = MMT_DIGEST_INTERVAL  # 模拟 25 轮已记录

    assert engine._maybe_mmt_digest() is None   # 仅触发（返回 None）
    # 后台 digest: A/B 两轮空包 → 好感 5 落 affection 事件
    assert _wait(lambda: any(
        e.type == "affection" and e.subtype == "digest"
        for e in st.events(CHARACTER))), "25 轮触发后应有好感事件"
    assert llm.llm_calls == 2                   # 恰好 A+B 两轮
    # 注入段已刷新: 出厂背景（yml 直注）+ 无出厂节点落 wiki（空包 digest 零产物）
    assert "【背景经历" in engine._brain_injection
    assert "遥香" in engine._brain_injection or "sensei" in engine._brain_injection


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


def test_first_digest_creates_char_entities(tmp_path, monkeypatch):
    """**第一次 digest 开始前**把 self(x0000) + sensei(x0001) 建出来并落盘（§3.0 / §9-7）。

    用户 2026-09-23 裁决的时刻 = vn_finish 之后、digest 的 LLM 调用之前; 接线点选在
    `_inject_brain(digest=True)` ⇒ bond 闭环与 mmt 每 25 轮**两个触发点都覆盖**。

    ⚠️ 顺序是**正确性**问题（不是风格）: 表里没有 entity 时 `next_id("x")` 返回的是
    **x0001** —— sensei 的保留号。谁先建谁占坑; 漏了的话第 3 轮 `new_entity` 建的第一个人
    会顶掉 sensei, 而 `ensure_entities` 按 id 判幂等 ⇒ **sensei 永远不再被建**。
    """
    from core.brain.wiki_v2.entities import SELF_ID, SENSEI_ID
    from core.brain.wiki_v2.store import WikiStoreV2
    from core.mmt import mmt_preset
    from core.parsing.names import names_of

    monkeypatch.setattr(mmt_preset, "load_player_name", lambda: "阿宅")
    engine, st, llm = _engine(tmp_path)
    char = engine._current_char
    _mmt_event(st, CHARACTER, 1)
    engine._session_rounds = MMT_DIGEST_INTERVAL
    engine._maybe_mmt_digest()
    assert _wait(lambda: llm.llm_calls == 2), "首次 digest 应 A+B 两轮"

    # 重新载入 = 断言"真的写回盘上了"（内存里建过不算）
    ws = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
    assert [n.id for n in ws.all() if n.kind == "entity"] == [SELF_ID, SENSEI_ID]
    assert ws.get(SELF_ID).name == names_of(char).display        # 角色自己的显示名
    assert set(names_of(char).aliases) <= set(ws.get(SELF_ID).aliases)
    assert ws.get(SELF_ID).text == ""                            # 立场留给第 3 轮
    assert ws.get(SENSEI_ID).name == "老师"
    assert {"sensei", "阿宅"} <= set(ws.get(SENSEI_ID).aliases)   # 玩家名进了别名
    assert ws.next_id("x") == "x0002"                            # 保留号挡住了 0/1

    # 幂等: 再触发一次（水位已推进 → 0 新增早退）不重复建、不删
    engine._session_rounds = MMT_DIGEST_INTERVAL * 2
    engine._maybe_mmt_digest()
    time.sleep(0.3)
    again = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
    assert [n.id for n in again.all() if n.kind == "entity"] == [SELF_ID, SENSEI_ID]


# ---------------------------------------------------------------------------
# 2026-09-13（审计 E11）: 轮数必须**跨重连恢复**, 不能因前端刷新归零
# ---------------------------------------------------------------------------

def test_session_rounds_restored_across_reattach(tmp_path):
    """`attach_session` 重入（= 前端刷新/切页走 `open_session`）不得把轮数清零。

    `_session_rounds` 有两个身份: ① mmt 窗口 digest 的触发计数（>=25 且 %25==0）;
    ② `want_to_speak` 的冷却键（`core/random_events` 拿它当"当前轮号"）。
    原先 `attach_session` 无条件 `= 0` → **页面每刷新一次, 25 轮窗口就从头再数**,
    常刷新时 digest 几乎永不触发; 冷却键同样退化成"冷却 >=6 次刷新"。

    恢复所依赖的 invariant = "**本会话 mmt_chat 事件条数 == 成功轮数**"
    （每成功一轮恰落一条, 见 `_log_events`/`_finish_turn_list`）——这里两半都钉住。
    """
    engine, st, llm = _engine(tmp_path)
    sid = engine._session_id

    # 造"本会话已经聊过 3 轮"的既成事实（事件流是唯一真源）
    for i in range(3):
        _mmt_event(st, CHARACTER, i)
    assert engine._session_rounds == 0, "前置: 内存计数此刻还是 0"

    # 重连（同会话）→ 从事件流恢复到 3, 而不是 0
    engine.attach_session(sid)
    assert engine._session_rounds == 3, \
        f"重连后轮数被清零（digest 窗口会从头再数）: {engine._session_rounds}"

    # 继续对话 → 在恢复值上递增（每轮恰好 +1, invariant 的另一半）
    engine._advance_round(CHARACTER)
    assert engine._session_rounds == 4, engine._session_rounds

    # 无 store → 0（宁缺勿错, 不抛）
    engine._store = None
    engine.attach_session(sid)
    assert engine._session_rounds == 0

    # 空会话（无任何 mmt_chat）→ 0
    engine._store = st
    empty = SessionStore(tmp_path / "empty")
    engine._store = empty
    engine.attach_session(sid)
    assert engine._session_rounds == 0
    print("    E11: 轮数跨重连恢复（3 → 重连 3 → 续聊 4）; 无 store/空会话降级 0")
