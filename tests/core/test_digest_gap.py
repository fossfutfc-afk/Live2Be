# -*- coding: utf-8 -*-
"""D1 —— **L1 的缺口账**（2026-09-29）: 这一段跑成了, 但什么东西没进记忆。

## 它解决什么

在它之前, "这段丢了东西"只有**一行日志**, 而三类丢点里有两类**连日志都没有**:
`digest_record span=… 未认领=…`（数）· `digest_record contract=bond …`（一章一条丢的）·
`_find_duplicate` 命中（**完全静默**）。更要命的是**契约层**——它写了 25 种 warning,
而 `call._round_call` 只看 `errors` ⇒ `vr.warnings` **一个字都没落**（其中
"`{label} 的端点 … 不在本段时间线里——丢弃`" 会**直接制造未认领**: 区间作废 ⇒
那几句没挂在任何事上）。

## 四条判据（都在 `pipeline._note_gap` 的 docstring 里）

  ① **只收不可重算的**: 契约层当场说的 + 条目面（一章一条丢的 / 判重复复用的）。
     ⛔ 未认领的内容事件、章内覆盖**可重算**（节点 `event_seq` + 章 marker +
     `affection/digest` 的段界都在盘上）⇒ 它们进**日志**, 不进账。
  ② **一段一行, 只在真有缺口时写**（全认领 + 无丢点 ⇒ 一行都不写）。
  ③ **`skeptical` 只在真的掉了内容时填** —— 形状建议与"丢掉一条冗余总结"都不是
     "她少了什么"; 闲聊没成记忆本来就合设计（MMT 一轮 = 0~5 条）。
  ④ ⭐ **回滚过的段没有"缺"可言**: 账只在**提交之后**造 ⇒ 整段失败时一个字都不留。

运行: python -m pytest tests/core/test_digest_gap.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain import WikiStoreV2
from core.brain.entities import ensure_entities
from core.creep import KIND_DIGEST_GAP, TYPE_CREEP, read_raw
from core.digest.pipeline import digest_segment
from core.session import SessionStore, make_event
from core.session.io import read_jsonl
from llm import task_labels as T

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
CHAR = "c"


# ---------------------------------------------------------------------------
# 桩: R1 的条目由每个用例自己给（其余轮走空包）
# ---------------------------------------------------------------------------

def _episode_ids(messages) -> list[str]:
    """从 R2 的 user 消息里认出**本轮新经历的 id**（`〔m0001｜《标题》〕`）。

    ⚠️ R2 的契约要求"覆盖全部 episode"（漏一条 ⇒ 整包拒）⇒ 桩必须按**实际** id 逐条给
    决策, 不能写死 `m0001`（本文件好几个用例是两条）。
    """
    text = messages[-1].get("content", "") if messages else ""
    return list(dict.fromkeys(re.findall(r"m\d{4}", str(text))))


class OneRound:
    """R1 返回给定 episodes; 其余轮空包（R2 自动覆盖全部 episode）。"""

    def __init__(self, episodes, *, on_mind=None):
        self.episodes = episodes
        self.on_mind = on_mind
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_RECORD:
            raw = {"episodes": self.episodes}
            if self.on_mind is not None:
                raw["on_mind"] = self.on_mind
            return raw
        if task in (T.DIGEST_UNDERSTAND, T.DIGEST):
            return {"decisions": [{"episode": i, "decision": "add", "kind": "belief",
                                   "subject": f"关于 {i}", "text": f"关于 {i} 的看法"}
                                  for i in _episode_ids(messages)],
                    "affection_exp_delta": 0}
        if task == T.DIGEST_CLOSE:
            return {"add": [], "close": []}
        if task == T.DIGEST_ATTRIBUTE:
            return {"attributions": []}
        raise RuntimeError(f"意外调用 task={task!r}")


class FailAfterRecord(OneRound):
    """R1 好、R2 整包坏 ⇒ 整段失败（验"回滚过的段不留账"）。"""

    def chat(self, messages, **kw):
        if kw.get("task") in (T.DIGEST_UNDERSTAND, T.DIGEST):
            return {"decisions": "这不是数组"}
        return super().chat(messages, **kw)


def _wiki(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    ensure_entities(st, char_name="伊草 遥香", sensei_name="老师")
    st.save()
    return st


def _events(n: int = 4):
    out = []
    for i in range(n):
        e = make_event("mmt", "mmt_chat", {"player": "老师", "reply": f"第 {i} 句"})
        e.seq = i + 1
        out.append(e)
    return out


def _gaps(res) -> list[dict]:
    return [r for r in res.creep_rows if r.get("kind") == KIND_DIGEST_GAP]


# ---------------------------------------------------------------------------
# ② 一段一行: 干净段不写, 有缺口才写
# ---------------------------------------------------------------------------

def test_clean_segment_writes_no_row(tmp_path):
    """⭐ 全认领 + 无丢点 ⇒ **一行都不写**（账不是流水）。"""
    st = _wiki(tmp_path)
    llm = OneRound([{"text": "四句都记下了", "title": "全都记得", "span": [1, 4],
                     "tags": ["闲聊"], "significance": 0.6}])
    res = digest_segment(st, llm, _events(4))

    assert res.ok, res.errors
    assert res.contract_warnings == [], res.contract_warnings
    assert _gaps(res) == [], f"干净段不该有账: {_gaps(res)}"
    print("    干净段: 无账 ✓")


def test_health_warnings_alone_do_not_write_a_row(tmp_path):
    """⭐ 收窄（2026-09-29）: **契约层说建议类的话不写账**（它是健康度, 不是缺口）。

    判据: 缺 title/tags 这种"建议"既不丢内容也不丢条目 ⇒ 只有日志, 没有账行。
    """
    st = _wiki(tmp_path)
    # 位置合法（覆盖 1~4）、但缺 title / 缺 tags / significance 非数字
    llm = OneRound([{"text": "四句都记下了", "span": [1, 4], "significance": "??"}])
    res = digest_segment(st, llm, _events(4))

    assert res.ok, res.errors
    assert len(res.contract_warnings) >= 3, res.contract_warnings   # 契约层确实说了话
    assert res.contract_drops == [], res.contract_drops
    assert _gaps(res) == [], f"建议类 warning 不该写账: {_gaps(res)}"
    print(f"    健康度 {len(res.contract_warnings)} 句 ⇒ 只进日志, 不写账 ✓")


def test_gap_row_carries_the_three_faces(tmp_path):
    """缺口段的账: 契约面（只装**真丢**的）+ 条目面（in / kept / no_pos / dropped / reused）。"""
    st = _wiki(tmp_path)
    # span 端点抄到时间线外 ⇒ 契约层丢弃整个区间（真丢）⇒ 这条没有位置
    llm = OneRound([{"text": "端点抄错了", "title": "抄错", "span": [1, 99],
                     "tags": ["x"]}])
    res = digest_segment(st, llm, _events(4))

    assert res.ok, res.errors
    rows = _gaps(res)
    assert len(rows) == 1, rows
    ev = rows[0]["evidence"]
    assert set(ev) == {"contract", "items"}, ev
    assert ev["contract"]["by_round"] == {"record": len(ev["contract"]["lost"])} 
    assert any("99" in x for x in ev["contract"]["lost"])
    assert "n" not in ev["contract"] and "other" not in ev["contract"], \
        "健康度不进账（只在日志）"
    assert ev["items"] == {"in": 1, "kept": 1, "no_pos": 1, "dropped": [], "reused": []}, \
        ev["items"]
    print(f"    缺口段: 真丢 {len(ev['contract']['lost'])} 处 · items={ev['items']}")


def test_no_position_entry_still_gets_the_segment_pointer(tmp_path):
    """⭐ span 被丢 ⇒ **兜底行为不变**（段级指针, 文档化的有意设计）+ 账里记 `no_pos`。

    判据（用户 2026-09-29 裁决"只改可见性"）: 兜底保住了 `_find_duplicate` 的幂等,
    而段级指针是**真的**（那条记忆确实产生于这一段）—— 所以会计上要**把两种口径说清**,
    不是改行为。⚠️ 按条目算的"未认领" ≠ 按节点算的（兜底那条 seq 看起来已认领）。
    """
    st = _wiki(tmp_path)
    llm = OneRound([{"text": "端点抄错了", "title": "抄错", "span": [1, 99],
                     "tags": ["x"]}])
    res = digest_segment(st, llm, _events(4))

    assert res.ok, res.errors
    node = st.get(res.created[0])
    assert node.event_seq == [4], f"兜底到段级指针（interact_max=4）: {node.event_seq}"
    assert _gaps(res)[0]["evidence"]["items"]["no_pos"] == 1
    print(f"    无位置: 兜底 {node.event_seq}（行为不变）+ 账里 no_pos=1 ✓")


# ---------------------------------------------------------------------------
# ③ skeptical 只在**真的掉了内容**时才有话
# ---------------------------------------------------------------------------

def test_skeptical_only_when_something_was_lost(tmp_path):
    """建议类（缺 title/tags）⇒ **连账都不写**; 区间作废（真丢）⇒ 有账且有那句话。

    ⚠️ 判据不是文案匹配: 契约层在**源头**声明 `ValidationResult.drops`
    （`_drop()` 那几处 = 背后真有一个内容离开过库）。
    """
    # ① 只有形状建议（位置合法, 但缺 title/tags）⇒ 不写账
    st = _wiki(tmp_path)
    res = digest_segment(st, OneRound([{"text": "四句", "span": [1, 4]},
                                       {"text": "又一条", "span": [1, 4]}]), _events(4))
    assert res.contract_warnings, "这一段契约层确实说了话"
    assert _gaps(res) == [], "建议类不写账"

    # ② 区间端点抄到时间线外 ⇒ 契约层**丢弃整个区间**（`drops`）⇒ 真丢
    st2 = _wiki(tmp_path / "b")
    res2 = digest_segment(st2, OneRound([{"text": "端点抄错了", "title": "抄错",
                                          "span": [1, 99], "tags": ["x"]}]), _events(4))
    row2 = _gaps(res2)[0]
    assert row2["evidence"]["contract"]["lost"], row2["evidence"]
    assert row2.get("skeptical"), "真丢了内容 ⇒ 该有一句存疑"
    assert "99" in " ".join(row2["evidence"]["contract"]["lost"])
    print(f"    真丢: {row2['skeptical']!r}")


def test_on_mind_dropped_is_a_loss(tmp_path):
    """`on_mind` 不是字符串 ⇒ 契约层丢弃它（`drops`）⇒ 也算真丢。"""
    st = _wiki(tmp_path)
    llm = OneRound([{"text": "四句都记下了", "title": "全都记得", "span": [1, 4],
                     "tags": ["闲聊"]}], on_mind=123)
    res = digest_segment(st, llm, _events(4))

    row = _gaps(res)[0]
    assert any("on_mind" in d for d in row["evidence"]["contract"]["lost"]), row
    assert row.get("skeptical")
    print("    on_mind 被丢 ⇒ 真丢 ✓")


# ---------------------------------------------------------------------------
# 条目面: 一章一条丢的 / 判重复复用的（两者都不可重算）
# ---------------------------------------------------------------------------

def _chapter_events(title: str = "苔藓"):
    """一章: vn_enter → 两条 bond → vn_exit（章块 = 那两条 bond 的 seq）。

    ⚠️ marker 的 `type` 就是 `"marker"`（`Event.is_marker` 是只读 property）。
    """
    evs = []
    enter = make_event("marker", "vn_enter", {"chapter_title": title})
    enter.seq = 1
    evs.append(enter)
    for i, seq in enumerate((2, 3)):
        b = make_event("bond", "story_scene", {"paragraphs": [{"text": f"第 {i} 句"}]})
        b.seq = seq
        evs.append(b)
    ex = make_event("marker", "vn_exit", {"completed": True})
    ex.seq = 4
    evs.append(ex)
    return evs


def test_collapsed_entries_are_recorded(tmp_path):
    """⭐ 一章两条 ⇒ 丢掉的那条**进账**（它只在这一刻存在）。"""
    st = _wiki(tmp_path)
    llm = OneRound([{"text": "第一种写法", "title": "写法甲", "span": [2, 3],
                     "tags": ["苔藓"], "significance": 0.3},
                    {"text": "第二种写法", "title": "写法乙", "span": [2, 3],
                     "tags": ["苔藓"], "significance": 0.9}])
    res = digest_segment(st, llm, _chapter_events())

    assert res.ok, res.errors
    dropped = _gaps(res)[0]["evidence"]["items"]["dropped"]
    assert len(dropped) == 1, dropped
    assert dropped[0]["chapter"] == "苔藓"
    assert dropped[0]["keep"] == "写法乙"          # sig 高的留下
    assert dropped[0]["lost"] == ["写法甲"]        # sig 低的被丢
    # ⚠️ 丢的是"她多写的一条总结", 内容仍被保留那条覆盖 ⇒ **不是**"她少了什么"
    assert "skeptical" not in _gaps(res)[0]
    print(f"    一章一条: 丢 {dropped[0]['lost']}（留 {dropped[0]['keep']}）✓")


def test_reused_node_is_recorded(tmp_path):
    """⭐ 判重复而复用旧节点 ⇒ 进账（从前这一处**完全静默**, 而 `created` 里躺着复用 id）。"""
    st = _wiki(tmp_path)
    eps = [{"text": "同一段经历", "title": "同一件", "span": [1, 3], "tags": ["x"]}]

    res1 = digest_segment(st, OneRound(list(eps)), _events(3))
    assert res1.ok and _gaps(res1) == [], "第一次是干净段（没有缺口 ⇒ 不写账）"

    st.meta["digested_seq"] = 0                    # 回退水位 = 崩溃窗口重跑
    st.save_meta()
    res2 = digest_segment(st, OneRound(list(eps)), _events(3))
    assert res2.ok, res2.errors
    reused = _gaps(res2)[0]["evidence"]["items"]["reused"]
    assert reused == res1.created, f"该复用第一段建的那个节点: {reused} vs {res1.created}"
    print(f"    重跑: 复用 {reused}（没建第二个节点）✓")


# ---------------------------------------------------------------------------
# ④ 回滚过的段没有"缺"可言
# ---------------------------------------------------------------------------

def test_rollback_leaves_no_gap_row(tmp_path):
    """⭐ 整段失败 ⇒ **一个字都不留**: 账只在提交之后造, 字段也被 `reset_result` 清掉。"""
    st = _wiki(tmp_path)
    llm = FailAfterRecord([{"text": "只记了前两句", "span": [1, 2]}])
    res = digest_segment(st, llm, _events(4))

    assert not res.ok
    assert _gaps(res) == [], "回滚过的段不该留下缺口账"
    assert res.contract_warnings == [] and res.record_gaps == {}, \
        "回滚要把契约话与条目面一起清掉（表推导的 reset_result）"
    print("    整段失败: 账 + 契约话一起作废 ✓")


# ---------------------------------------------------------------------------
# 端到端: 账落进真源, 而她/任何解析器都看不见它
# ---------------------------------------------------------------------------

def test_engine_writes_the_gap_row_into_the_truth(tmp_path):
    """引擎级: 真源里多一行 `type=creep, kind=digest_gap`, **没有 `seq`**。"""
    from core.mmt.engine import MomoTalkEngine

    st = SessionStore(tmp_path)
    engine = MomoTalkEngine(ROOT / "config" / "characters",
                            OneRound([{"text": "只记了前两句", "span": [1, 2]}]),
                            store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    for e in _events(4):
        st.append_event(CHARACTER, root.session_id, e)

    engine._run_digest(CHARACTER, engine._session_id)      # 同步跑（不经后台线程）

    rows = read_jsonl(st.events_path(CHARACTER, engine._session_id))
    gap = [r for r in rows if isinstance(r, dict) and r.get("kind") == KIND_DIGEST_GAP]
    assert len(gap) == 1, f"真源里该有 1 条缺口账: {gap}"
    assert gap[0]["type"] == TYPE_CREEP and "seq" not in gap[0]
    # 而 creep 自己的读侧看得见它
    assert [r["kind"] for r in read_raw(st, CHARACTER, session_id=engine._session_id)] \
        == [KIND_DIGEST_GAP]
    # 事件流解析器看不见它（结构性隐身）
    assert all(getattr(e, "type", "") != TYPE_CREEP for e in st.events(CHARACTER))
    print("    端到端: 账落真源 · 无 seq · 只有 creep 读侧看得见 ✓")


if __name__ == "__main__":
    import tempfile

    for fn in (test_clean_segment_writes_no_row, test_health_warnings_alone_do_not_write_a_row,
               test_gap_row_carries_the_three_faces,
               test_no_position_entry_still_gets_the_segment_pointer,
               test_skeptical_only_when_something_was_lost, test_on_mind_dropped_is_a_loss,
               test_collapsed_entries_are_recorded, test_reused_node_is_recorded,
               test_rollback_leaves_no_gap_row):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_engine_writes_the_gap_row_into_the_truth(Path(d))
    print("all digest gap tests passed")
