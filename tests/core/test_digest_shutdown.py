"""digest 的**关停韧性** —— 水位自愈 + 中止不记账 + 在途登记。

两条判据:

① **水位自愈**（加载时）: 提交是"先写图、后写水位"两次原子替换, 中间被杀就成
   "图新、水位旧" ⇒ 同一批事件再喂一遍。图上的 `event_seq` 就是覆盖事实, 加载时取大者。
   只改内存（探针只读, 加载期落盘会污染真机数据）。
② **中止 ≠ 失败**: 被关停打断的 digest **不写盘、不计 `digest_retry`** —— 计数的后果是
   `DIGEST_MAX_ATTEMPTS` 满 3 次后**永久放弃**这一段（推水位 + 落 creep 账）。

跑法: python -m pytest tests/core/test_digest_shutdown.py
"""
import json

from core.brain import WikiStoreV2
from core.brain.entities import ensure_entities
from core.brain.nodes import make_node
from core.digest.pipeline import digest_segment
from core.session import make_event
from infra import runtime
from llm import task_labels as T
from tests import stub_tasks

CHAR = "c"


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


class _CountingLLM:
    """任何调用都记一笔（用来证明"闸在调用之前"）。"""

    def __init__(self, *, abort_on_first: bool = False):
        self.calls = 0
        self._abort = abort_on_first

    def chat(self, messages, **kw):
        self.calls += 1
        if self._abort:
            runtime.request_shutdown()          # 第一轮跑完之后才置信号
        return stub_tasks.split_for_scripted(
            messages, [{"text": "一段经历", "title": "经历"}])


# ---------------------------------------------------------------------------
# ① 水位自愈
# ---------------------------------------------------------------------------

def test_watermark_heals_from_the_graph_on_load(tmp_path):
    st = _wiki(tmp_path)
    st.add(make_node("episode", text="模型店门口", event_seq=[7, 8, 9], ts="2026-10-17"))
    st.save()
    st.meta["digested_seq"] = 0                # 模拟"图写了、水位没写"就被杀
    st.save_meta()

    healed = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    assert healed.digested_seq == 9, healed.digested_seq
    # 只改内存: 磁盘上那个落后的水位原样留着（探针加载不许写盘）
    raw = json.loads((tmp_path / "worlds" / "world1" / "characters" / CHAR
                      / "soul" / "wiki.meta.json").read_text(encoding="utf-8"))
    assert raw["digested_seq"] == 0, raw
    print("    水位自愈: meta 0 → 图上覆盖 9（内存）, 磁盘未动")


def test_watermark_stays_when_meta_is_ahead(tmp_path):
    """0 覆盖兜底那类水位**高于任何节点**（放弃一段时推的）—— 不许被"自愈"拉回去。"""
    st = _wiki(tmp_path)
    st.add(make_node("episode", text="只有一条", event_seq=[3], ts="2026-10-17"))
    st.save()
    st.meta["digested_seq"] = 40
    st.save_meta()

    again = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    assert again.digested_seq == 40, again.digested_seq


# ---------------------------------------------------------------------------
# ② 中止: 不写盘、不计失败
# ---------------------------------------------------------------------------

def test_shutdown_before_the_first_round_writes_nothing(tmp_path):
    st = _wiki(tmp_path)
    before = st.path.read_bytes()
    llm = _CountingLLM()
    runtime.request_shutdown()
    try:
        res = digest_segment(st, llm, _events(3))
    finally:
        runtime._reset_for_tests()

    assert res.aborted and not res.ok
    assert llm.calls == 0, "关停闸必须在第一轮 LLM 调用之前"
    assert st.path.read_bytes() == before, "图文件不许变"
    assert "digest_retry" not in st.meta, "中止不计失败次数"
    assert st.digested_seq == 0
    print("    关停闸: 0 次 LLM 调用、图未变、未记账")


def test_shutdown_between_rounds_rolls_back_and_keeps_no_trace(tmp_path):
    """第一轮跑完之后被杀: 内存回滚、不落盘、`digest_retry` 不出现。"""
    st = _wiki(tmp_path)
    before_ids = {n.id for n in st.all()}
    before = st.path.read_bytes()
    llm = _CountingLLM(abort_on_first=True)
    try:
        res = digest_segment(st, llm, _events(3))
    finally:
        runtime._reset_for_tests()

    assert res.aborted and not res.ok
    assert llm.calls >= 1, "第一轮应当真的跑过（否则测的不是'轮次之间'）"
    assert {n.id for n in st.all()} == before_ids, "内存要回滚到本段之前"
    assert st.path.read_bytes() == before
    assert "digest_retry" not in st.meta, "中止不许计失败次数（三次就永久放弃这一段）"
    assert res.creep_rows == [], "没提交的段没有'缺'可言"
    print(f"    轮次之间被杀: 跑了 {llm.calls} 次调用, 回滚干净、零记账")


# ---------------------------------------------------------------------------
# ③ 在途登记（前端"等它跑完"要读它）
# ---------------------------------------------------------------------------

def test_runtime_registry_reports_stage_and_idle():
    runtime._reset_for_tests()
    runtime.begin("digest", "start")
    runtime.stage("digest", "relate")
    snap = runtime.snapshot()
    assert snap["shutdown"] is False
    assert snap["busy"] == [{"name": "digest", "stage": "relate", "elapsed_s": 0.0}] \
        or snap["busy"][0]["stage"] == "relate", snap

    assert runtime.wait_idle(0.5) is False, "还有活在跑就不该说 idle"
    runtime.end("digest")
    assert runtime.wait_idle(0.5) is True
    assert runtime.snapshot()["busy"] == []
    # 没登记时 stage 不该凭空造出一个在途任务（直接调 digest_segment 的测试/探针）
    runtime.stage("digest", "split")
    assert runtime.snapshot()["busy"] == []
    print("    在途登记: begin/stage/snapshot/wait_idle/end 都对得上")
