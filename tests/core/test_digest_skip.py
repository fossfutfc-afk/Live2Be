"""刀 2 —— **digest 放弃那一刻**（2026-09-29）: 计数 / 放弃 / 落 creep 账。

背景（为什么要它）: 一段 digest 失败 ⇒ 水位不推进 ⇒ 下次触发**整段重来**。
在"没有上限"的旧世界里，一个**永远跑不完的段**会把后面所有段一起堵住:
窗口每 25 轮长大一次 ⇒ 越长越贵越难过 ⇒ **正反馈**，而它永远不会放弃。

四条判据（都在 `_note_failure` 的 docstring 里）:
  ① 计数的键 = **起点水位**（不是窗口 —— 窗口会长大, 拿它当键永远到不了上限）
  ② 放弃时水位推到**第一次失败那一窗的上界**（第 2/3 次之间新攒的内容不能跟着丢）
  ③ 上限 = **3 次**, 且次数由**触发点**累加（同进程不连试）
  ④ 放弃 = **真的丢记忆**（那段再也不会有节点）⇒ 必须留一条 `creep` 账

运行: python -m pytest tests/core/test_digest_skip.py
"""
import sys
from pathlib import Path

from core.brain import WikiStoreV2
from core.brain.entities import ensure_entities
from core.creep import KIND_DIGEST_SKIP, TYPE_CREEP, read_raw
from core.digest.pipeline import DIGEST_MAX_ATTEMPTS, digest_segment
from core.session import SessionStore, make_event
from core.session.io import read_jsonl
from llm import task_labels as T
from tests import stub_tasks

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
CHAR = "c"                         # wiki 侧 char_id（与事件流的 slug 分开, 与别的用例同款）


def _wiki(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    ensure_entities(st, char_name="伊草 遥香", sensei_name="老师")
    st.save()
    return st


def _events(n: int = 3):
    out = []
    for i in range(n):
        e = make_event("mmt", "mmt_chat", {"player": "老师", "reply": f"第 {i} 句"})
        e.seq = i + 1
        out.append(e)
    return out


class AlwaysFail:
    """每一次 digest 调用都坏（R1 就死在形状上 ⇒ 走反馈重试 ⇒ 整批失败）。"""

    def __init__(self):
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        self.tasks.append(kw.get("task"))
        return {"episodes": "这不是数组"}            # parse 层直接拒


class FlakyOnce:
    """第一次坏、第二次好（用来验"成功要清零"）。"""

    def __init__(self):
        self.n = 0

    def chat(self, messages, **kw):
        task = kw.get("task")
        if task == T.DIGEST_SPLIT:            # ⭐ R0: 照搬 R1 那份应答里的区间
            return stub_tasks.split_for_scripted(
                messages, [{"text": "一段经历", "title": "经历"}])
        if task == T.DIGEST_RECORD:
            self.n += 1
            if self.n == 1:
                return {"episodes": "坏"}
            return {"episodes": [{"text": "一段经历", "title": "经历"}]}
        if task in (T.DIGEST_RELATE, T.DIGEST):
            return {"relations": []}          # L1: 没看出关系（本用例测的是失败重试次数）
        if task == T.DIGEST_SETTLE:
            return {"attributions": []}
        if task == T.DIGEST_COGNIZE:      # L2-b（P10）: 不测它 ⇒ 空包
            return {"cognitions": []}
        raise RuntimeError(f"意外调用 task={task!r}")


# ---------------------------------------------------------------------------
# ① 计数: 键 = 起点水位
# ---------------------------------------------------------------------------

def test_first_failure_records_attempt_and_keeps_watermark(tmp_path):
    """第一次失败: 记 `attempts=1` + 本窗上界; **水位不动**、不落账。"""
    st = _wiki(tmp_path)
    res = digest_segment(st, AlwaysFail(), _events(3))

    assert not res.ok and res.creep_rows == []
    assert st.digested_seq == 0, "第一次失败不该推进水位"
    rec = st.meta.get("digest_retry")
    assert rec == {"from_seq": 0, "upto_seq": 3, "attempts": 1}, rec
    print(f"    第 1 次: {rec}（水位仍 {st.digested_seq}）")


def test_attempts_accumulate_across_a_growing_window(tmp_path):
    """⭐ 窗口长大**不重置计数** —— 键是起点水位, 不是窗口。"""
    st = _wiki(tmp_path)
    digest_segment(st, AlwaysFail(), _events(3))
    # 又来了 2 条新对话（窗口从 3 长到 5）
    digest_segment(st, AlwaysFail(), _events(5))

    rec = st.meta.get("digest_retry")
    assert rec["attempts"] == 2, rec
    assert rec["from_seq"] == 0 and rec["upto_seq"] == 3, \
        f"upto 必须停在**第一次**那一窗: {rec}"
    print(f"    第 2 次（窗口 3 → 5）: {rec}")


def test_switching_watermark_resets_the_counter(tmp_path):
    """换了起点水位 = 换了另一段 ⇒ 计数**自动重置**（不需要显式清零）。"""
    st = _wiki(tmp_path)
    st.meta["digest_retry"] = {"from_seq": 5, "upto_seq": 9, "attempts": 2}
    digest_segment(st, AlwaysFail(), _events(3))          # 当前水位是 0, 与键 5 不符

    assert st.meta["digest_retry"]["attempts"] == 1, st.meta["digest_retry"]
    print("    键不是本段 ⇒ 计数重置为 1（拿旧前科罚新段是不对的）")


# ---------------------------------------------------------------------------
# ② 第 3 次 ⇒ 放弃（推水位 + 落账）
# ---------------------------------------------------------------------------

def test_giving_up_advances_watermark_and_leaves_a_creep_row(tmp_path):
    """⭐ 数满 3 次 ⇒ 水位推到**第一窗的上界** + 一条 `digest_skip` 账 + 计数清空。"""
    st = _wiki(tmp_path)
    for _ in range(DIGEST_MAX_ATTEMPTS - 1):
        digest_segment(st, AlwaysFail(), _events(3))
    res = digest_segment(st, AlwaysFail(), _events(5))    # 第 3 次: 窗口已经长到 5

    assert not res.ok, "放弃仍然是一次失败（水位推进 ≠ 这批成了）"
    assert st.digested_seq == 3, "水位必须停在**第一次**那一窗的上界（不是 5）"
    assert "digest_retry" not in st.meta, "放弃之后计数要清掉"
    assert len(res.creep_rows) == 1
    row = res.creep_rows[0]
    assert row["type"] == TYPE_CREEP and row["kind"] == KIND_DIGEST_SKIP
    assert "seq" not in row, "账行不许有 seq（那是它结构性隐身的原因）"
    assert row["at_seq"] == 3 and row["skeptical"], row
    ev = row["evidence"]
    assert ev["from_seq"] == 0 and ev["to_seq"] == 3
    assert ev["attempts"] == DIGEST_MAX_ATTEMPTS and ev["errors"]
    print(f"    第 3 次（窗口已 5）: 水位 0 → 3; 账 = {row['skeptical'][:14]!r}…")


def test_giving_up_drops_only_the_first_window(tmp_path):
    """放弃丢的是**第一窗**那段; 其后新到的事件留给下一段（下次从这里继续）。"""
    st = _wiki(tmp_path)
    digest_segment(st, AlwaysFail(), _events(3))          # 第 1 次: 窗 = 1..3
    digest_segment(st, AlwaysFail(), _events(5))          # 第 2 次: 对话又来了, 窗长到 1..5
    res = digest_segment(st, AlwaysFail(), _events(5))    # 第 3 次: 放弃

    assert not res.ok and st.digested_seq == 3, "只该丢掉第一窗（1..3）"
    # 下一段从 3 之后继续 ⇒ 新窗 = 4/5（没被上一刀连带丢掉）
    nxt = digest_segment(st, AlwaysFail(), _events(5))
    assert not nxt.ok
    assert st.meta["digest_retry"] == {"from_seq": 3, "upto_seq": 5, "attempts": 1}, \
        st.meta["digest_retry"]
    print("    下一段从 3 继续: 新窗 = 4/5（没被上一刀连带丢掉）")


# ---------------------------------------------------------------------------
# ③ 成功 ⇒ 清零
# ---------------------------------------------------------------------------

def test_success_clears_the_counter(tmp_path):
    """成功之后计数必须清零 —— 否则下一段会白背上一段的前科。"""
    st = _wiki(tmp_path)
    digest_segment(st, AlwaysFail(), _events(3))
    assert st.meta.get("digest_retry")

    res = digest_segment(st, FlakyOnce(), _events(3))
    assert res.ok, res.errors
    assert "digest_retry" not in st.meta, "成功了还留着前科"
    # ⚠️ 判据收窄成"没有**放弃**那一种账"（2026-09-29 D1 起, 成功路径也可能留
    # `digest_gap` —— 那段跑成了但有东西没进记忆, 那是另一件事）
    assert [r for r in res.creep_rows if r.get("kind") == KIND_DIGEST_SKIP] == []
    print(f"    失败 1 次 → 成功: 计数已清（水位 {st.digested_seq}）")


# ---------------------------------------------------------------------------
# ④ 端到端: 引擎把账写进真源（而且她/任何解析器都看不见它）
# ---------------------------------------------------------------------------

class EngineLLM:
    """引擎级: digest 三轮全坏（其余旁路走标准桩）。"""

    def __init__(self):
        self.tasks: list[str | None] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_SPLIT:                # ⭐ R0: 正常（后面几轮才是要测的坏）
            return stub_tasks.split_reply(messages)
        if task in (T.DIGEST_RECORD, T.DIGEST_RELATE):
            return {"episodes": "坏"}                 # 一律形状错 → 整批失败
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:
            return reply
        raise RuntimeError(f"意外调用 task={task!r}")


def test_engine_writes_the_creep_row_into_the_truth(tmp_path):
    """端到端: 连续 3 次失败 ⇒ **真源里多一行 creep**（无 seq, 解析器看不见它）。"""
    from core.mmt.engine import MomoTalkEngine

    st = SessionStore(tmp_path)
    llm = EngineLLM()
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    st.append_event(CHARACTER, "", make_event("mmt", "mmt_chat",
                                              {"player": "老师", "reply": "嗯"}))

    for _ in range(DIGEST_MAX_ATTEMPTS):
        engine._session_rounds = 25
        engine._run_digest(CHARACTER, engine._session_id)      # 同步跑（不经后台线程）

    rows = read_jsonl(st.events_path(CHARACTER, engine._session_id))
    creep = [r for r in rows if isinstance(r, dict) and r.get("type") == TYPE_CREEP]
    assert len(creep) == 1, f"真源里该有 1 条账: {creep}"
    assert "seq" not in creep[0] and creep[0]["kind"] == KIND_DIGEST_SKIP
    # 她/任何解析器都看不见它
    assert all(e.type != TYPE_CREEP for e in st.events(CHARACTER, engine._session_id))
    # 而 creep 自己的读侧看得见
    assert len(read_raw(st, CHARACTER, session_id=engine._session_id)) == 1
    print(f"    端到端: 真源 {len(rows)} 行 / 事件 {len(st.events(CHARACTER))} 个 / "
          f"账 1 条（{creep[0]['skeptical'][:12]!r}…）")


def test_creep_write_failure_does_not_block(tmp_path, monkeypatch):
    """账写失败**不阻断**, 但**也不推水位** —— 那条事实不许悄没声地丢。

    判据（`_note_failure`）: 水位是"这段处理过了"的声明, 而账是"它怎么没的"的唯一证据;
    先推水位再记账 ⇒ 记账一失败, 事实永久丢。反过来最坏只是"记了账但水位没动"。
    """
    from core.mmt.engine import MomoTalkEngine

    st = SessionStore(tmp_path)
    engine = MomoTalkEngine(ROOT / "config" / "characters", EngineLLM(), store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    st.append_event(CHARACTER, "", make_event("mmt", "mmt_chat",
                                              {"player": "老师", "reply": "嗯"}))

    def boom(*a, **kw):
        raise OSError("盘被占用了")

    monkeypatch.setattr(st, "append_raw_row", boom)
    for _ in range(DIGEST_MAX_ATTEMPTS):
        engine._session_rounds = 25
        engine._run_digest(CHARACTER, engine._session_id)      # 不该抛

    from core.brain import WikiStoreV2
    ws = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
    assert ws.digested_seq == 0, "账没写成就别推水位（下次还要重试记账）"
    # 盘上停在"第 2 次"（放弃那一次的计数**故意没落盘**: 那一步正是失败的记账）
    # —— 不影响下次: 它会再判一次死刑, 再试一次记账。
    assert ws.meta.get("digest_retry", {}).get("attempts") == DIGEST_MAX_ATTEMPTS - 1, \
        ws.meta.get("digest_retry")

    # 盘好了 ⇒ 下一次触发把账补上并推进水位（**自愈**）
    monkeypatch.undo()
    engine._session_rounds = 25
    engine._run_digest(CHARACTER, engine._session_id)
    rows = read_jsonl(st.events_path(CHARACTER, engine._session_id))
    assert len([r for r in rows if isinstance(r, dict)
                and r.get("type") == TYPE_CREEP]) == 1
    ws2 = WikiStoreV2(st.data_root, world_id=st.world_id, char_id=CHARACTER)
    assert ws2.digested_seq > 0 and "digest_retry" not in ws2.meta
    print("    账写失败: 只告警 + **不推水位**; 盘好了下次自愈（补账 + 推水位）")


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_first_failure_records_attempt_and_keeps_watermark(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_attempts_accumulate_across_a_growing_window(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_switching_watermark_resets_the_counter(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_giving_up_advances_watermark_and_leaves_a_creep_row(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_giving_up_drops_only_the_first_window(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_success_clears_the_counter(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_engine_writes_the_creep_row_into_the_truth(Path(d))
    print("all digest-skip tests passed")
