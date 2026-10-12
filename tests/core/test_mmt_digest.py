"""mmt 会话窗口 digest 测试（蓝图 §3.1: N=40 轮触发 + in_vn/in_memorial 保护）。

覆盖 momotalk 引擎的运行时 digest 接线（brain, 2026-09-02 切换）:
    - _maybe_mmt_digest: 40 轮触发 → 后台 digest 闭环（seed+提炼+好感事件落库）
    - 剧情中（in_vn）不触发
    - digest 增量: 无新增事件 → 0 次 LLM 调用（空跑无害）
    - **第一次 digest 前建 self/sensei 两个 entity**（§3.0 / §9-7, 2026-09-23）
"""
import sys
import time
from pathlib import Path

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
        # ⭐ `digest_segments=True`: 这一段要真的建 episode（否则链条在 R0 就收工了 ——
        # 缺省的空骨架是"这一段没有值得记的", 那正是 `test_digest_*` 之外用不到的行为）
        reply = stub_tasks.annotation_reply(task, messages, digest_delta=5,
                                           digest_segments=True)
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
    """_session_rounds=40 → _maybe_mmt_digest → 后台 digest 完成:
    水位推进 + 好感事件落库（2026-09-05 解耦: 出厂基座不再 seed 进 wiki——
    出厂背景 = experience.yml 原文直注, wiki 只存 digest 产物）。"""
    engine, st, llm = _engine(tmp_path)
    _mmt_event(st, CHARACTER, 1)                # 有事件可消化
    engine._session_rounds = MMT_DIGEST_INTERVAL  # 模拟 40 轮已记录

    assert engine._maybe_mmt_digest() is None   # 仅触发（返回 None）
    # 后台 digest: A/B 两轮空包 → 好感 5 落 affection 事件
    assert _wait(lambda: any(
        e.type == "affection" and e.subtype == "digest"
        for e in st.events(CHARACTER))), "40 轮触发后应有好感事件"
    assert llm.llm_calls == 3                   # R0 + A + B 三轮
    # 注入段已刷新: 出厂背景（yml 直注）+ 无出厂节点落 wiki（空包 digest 零产物）。
    # ⚠️ 注入是**后台线程**的最后一步 —— 好感事件落地 ≠ 注入已重建（2026-09-25:
    # 写卡计数器那一次落盘把两者拉开了几毫秒, 这条断言就红了）。等它, 别赌时序。
    assert _wait(lambda: "【背景经历" in engine._brain_injection), "digest 完成后应重建注入段"
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
    """未到 40 轮 → 不触发。"""
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
    assert _wait(lambda: llm.llm_calls == 3), "首次 digest 应 R0+A+B 三轮"
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
    `_inject_brain(digest=True)` ⇒ bond 闭环与 mmt 每 40 轮**两个触发点都覆盖**。

    ⚠️ 顺序是**正确性**问题（不是风格）: 表里没有 entity 时 `next_id("x")` 返回的是
    **x0001** —— sensei 的保留号。谁先建谁占坑; 漏了的话第 3 轮 `new_entity` 建的第一个人
    会顶掉 sensei, 而 `ensure_entities` 按 id 判幂等 ⇒ **sensei 永远不再被建**。
    """
    from core.brain.entities import SELF_ID, SENSEI_ID
    from core.brain.store import WikiStoreV2
    from core.mmt import mmt_preset
    from core.parsing.names import names_of
    from core.parsing.player_profile import player_names

    monkeypatch.setattr(mmt_preset, "load_player_name", lambda: "阿宅")
    engine, st, llm = _engine(tmp_path)
    char = engine._current_char
    player = player_names()                                   # 主名/别名来自 config
    _mmt_event(st, CHARACTER, 1)
    engine._session_rounds = MMT_DIGEST_INTERVAL
    engine._maybe_mmt_digest()
    assert _wait(lambda: llm.llm_calls == 3), "首次 digest 应 R0+A+B 三轮"

    # 重新载入 = 断言"真的写回盘上了"（内存里建过不算）
    ws = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
    # ⭐ 2026-10-08（B/C 笔）: **表里写了立场的对象也在这里出厂**（"她认识的人"）——
    #    保留号仍占前两位, 其余按 id 升序（haruka 的表: aru/mutsuki/kayoko/saori）。
    ids = [n.id for n in ws.all() if n.kind == "entity"]
    assert ids[:2] == [SELF_ID, SENSEI_ID], ids
    assert ids[2:] == ["x0002", "x0003", "x0004", "x0005"], ids
    assert ws.get(SELF_ID).name == names_of(char).display        # 角色自己的显示名
    assert set(names_of(char).aliases) <= set(ws.get(SELF_ID).aliases)
    # ⭐ `self` 的立场来自 `interperson.yml` 的**保留键 `self`**（2026-10-12 作者写上;
    #    在此之前这一格一直空着, 只有 digest 长出来的那一份）
    assert ws.get(SELF_ID).text.startswith("我总感觉"), ws.get(SELF_ID).text
    assert ws.get(SENSEI_ID).name == player.display              # 玩家主名: config/player
    assert set(player.aliases) <= set(ws.get(SENSEI_ID).aliases)  # 作者别名
    assert "阿宅" in ws.get(SENSEI_ID).aliases                    # 玩家自取名（player.json）
    # ⭐ sensei 的**立场**来自 `interperson.yml`（B 笔之前这一格一直是空的）
    assert ws.get(SENSEI_ID).text.startswith("sensei非常照顾我"), ws.get(SENSEI_ID).text
    assert ws.next_id("x") == "x0006"                            # 保留号挡住了 0/1

    # 幂等: 再触发一次（水位已推进 → 0 新增早退）不重复建、不删
    engine._session_rounds = MMT_DIGEST_INTERVAL * 2
    engine._maybe_mmt_digest()
    time.sleep(0.3)
    again = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
    assert [n.id for n in again.all() if n.kind == "entity"] == ids


# ---------------------------------------------------------------------------
# 2026-09-13（审计 E11）: 轮数必须**跨重连恢复**, 不能因前端刷新归零
# ---------------------------------------------------------------------------

def test_session_rounds_restored_across_reattach(tmp_path):
    """`attach_session` 重入（= 前端刷新/切页走 `open_session`）不得把轮数清零。

    `_session_rounds` 有两个身份: ① mmt 窗口 digest 的触发计数（>=40 且 %40==0）;
    ② `want_to_speak` 的冷却键（`core/random_events` 拿它当"当前轮号"）。
    原先 `attach_session` 无条件 `= 0` → **页面每刷新一次, 40 轮窗口就从头再数**,
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


def test_vn_close_digest_resets_the_mmt_round_counter(tmp_path):
    """⭐ S3（2026-10-06）: **VN 闭环那次消化要把 mmt 轮数计数清零**。

    病根（真机 haruka）: 章4 在 seq 200 闭环消化一次, 轮数**照数** ⇒ 紧接着到
    `MMT_DIGEST_INTERVAL` 的整数倍**又消化一次** —— `m0015`(22:47) / `m0016`(22:45)
    **相隔 2 分钟**, 同一段聊天被劈成两条 episode。
    修法 = 那条路径清零 ⇒ 语义变成"**VN 之后重新数 40 轮**"。
    """
    engine, st, _llm = _engine(tmp_path)
    _mmt_event(st, CHARACTER, 1)

    fired: list[int] = []
    engine.async_digest = lambda: fired.append(1)     # 记"还会不会再消化一次"

    # 到点之前 VN 闭环 ⇒ 计数清零（且它自己消化一次）
    engine._session_rounds = MMT_DIGEST_INTERVAL - 1
    engine.async_digest_after_vn()
    assert engine._session_rounds == 0, engine._session_rounds
    assert fired == [1], "VN 闭环本身要消化一次"

    # 之后 39 轮**不该**再消化（这正是修复的行为: 从前它会立刻到点）
    for _ in range(MMT_DIGEST_INTERVAL - 1):
        engine._session_rounds += 1
        engine._maybe_mmt_digest()
    assert fired == [1], f"清零之后不该马上又消化: {len(fired)} 次"

    # 数满 40 ⇒ 照常触发
    engine._session_rounds += 1
    engine._maybe_mmt_digest()
    assert fired == [1, 1], "数满 40 轮必须照常触发"


def test_mmt_side_digest_does_not_reset_the_counter(tmp_path):
    """⚠️ S3 的另一半: **纯 MMT 那侧不清零**（清了就与重启恢复的语义打架）。"""
    engine, st, _llm = _engine(tmp_path)
    _mmt_event(st, CHARACTER, 1)
    engine.async_digest = lambda: None
    engine._session_rounds = MMT_DIGEST_INTERVAL
    engine._maybe_mmt_digest()
    assert engine._session_rounds == MMT_DIGEST_INTERVAL, \
        "纯 MMT 触发后计数照走（下次数满 80 再触发）"


def test_vn_close_paths_only_use_the_resetting_entry():
    """⚠️ **结构性守门**: 两条 VN 收尾路径**只许**调 `async_digest_after_vn()`。

    漏一处 = 那条路径又不清零了 —— 而 S3 的病根正是"VN 侧不清零"。
    只扫这两个产品文件（`experiments/` 那些不是产品路径）。
    """
    for rel in ("webgui/bond/api.py", "apps/vn_cli.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "engine.async_digest_after_vn()" in src, f"{rel}: VN 收尾没走清零入口"
        assert "engine.async_digest()" not in src, \
            f"{rel}: 还在直呼 async_digest —— 那条路径不清零"
    print("    结构: 两条 VN 收尾路径都走 async_digest_after_vn ✓")
