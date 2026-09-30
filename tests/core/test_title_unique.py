# -*- coding: utf-8 -*-
"""⭐ N2b —— episode 标题的**写入时唯一**（2026-09-29）。

落的是 `PROCEED §2 #10` 那条已裁（"编号退回引擎内部；唯一性**写入时强制**，
冲突加数字，**只增不重排**"）。

为什么需要它（判据链）: 引擎与她之间唯一的地址空间就是标题；而 `address.find_episode`
遇到同名 ≥2 时**一律不猜**（丢）⇒ 重名**不会出错, 只会漏**（命中率）。
⇒ 唯一性是命中率的地基, 今天它靠"LLM 起名恰好不撞"。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brain.wiki_v2 import WikiStoreV2, make_node          # noqa: E402
from core.brain.wiki_v2.address import find_episode, unique_title   # noqa: E402
from core.brain.wiki_v2.digest import digest_segment           # noqa: E402
from core.session.events import make_event                     # noqa: E402
from llm import task_labels as T                               # noqa: E402

CLOSE_EMPTY = {"add": [], "close": []}


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)

    def chat(self, messages, **kw):
        task = kw.get("task")
        if task == T.DIGEST_CLOSE:
            return CLOSE_EMPTY
        if task == T.DIGEST_ATTR:
            return {"attributions": []}
        if self.responses:
            return self.responses.pop(0)
        raise RuntimeError("responses 耗尽")


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", text="旧的那条", title="中秋的杂草屋",
                     event_seq=[1], ts="2026-09-27T10:00:00", significance=0.7))
    return st


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------

def test_unique_title_passes_through_when_free(tmp_path):
    st = _store(tmp_path)
    assert unique_title(st, "全新的名字") == "全新的名字"
    assert unique_title(st, "  ") == ""                # 空标题跳过（不替她起名）
    assert unique_title(st, "") == ""


def test_unique_title_appends_number(tmp_path):
    st = _store(tmp_path)
    assert unique_title(st, "中秋的杂草屋") == "中秋的杂草屋 2"
    st.add(make_node("episode", text="第三条", title="中秋的杂草屋 2", event_seq=[2]))
    assert unique_title(st, "中秋的杂草屋") == "中秋的杂草屋 3"


def test_existing_nodes_are_never_touched(tmp_path):
    """⭐ **只增不重排** —— 既有节点一个都不动（否则她昨天抄的名字今天就指不到）。"""
    st = _store(tmp_path)
    before = [(n.id, n.title) for n in st.all()]
    unique_title(st, "中秋的杂草屋")
    assert [(n.id, n.title) for n in st.all()] == before
    assert st.get("m0001").title == "中秋的杂草屋"


# ---------------------------------------------------------------------------
# 端到端: 撞名 ⇒ 两条都可解析
# ---------------------------------------------------------------------------

def test_digest_dedupes_and_both_titles_resolve(tmp_path):
    """⭐ 写入时强制之后: 两个名字**各自唯一解析**（在此之前是 `ambiguous` ⇒ 她那笔直接丢）。"""
    st = _store(tmp_path)                                # m0001「中秋的杂草屋」
    same_title = {"episodes": [{"text": "又过了一次中秋", "title": "中秋的杂草屋",
                                "span": [3, 3], "tags": [], "significance": 0.6}]}
    b = {"decisions": [{"episode": "m0002", "decision": "add", "kind": "belief",
                        "text": "中秋总是让我想起杂草屋", "subject": "中秋",
                        "significance": 0.6}],
         "evidence": [], "affection_exp_delta": 0}
    events = [make_event("mmt", "chat", {"player": "老师", "reply": "又到中秋了"})]
    events[0].seq = 3
    res = digest_segment(st, FakeLLM(same_title, b), events)
    assert res.ok, res.errors
    assert res.created == ["m0002"]
    assert st.get("m0002").title == "中秋的杂草屋 2"       # 新来那条改名
    assert st.get("m0001").title == "中秋的杂草屋"         # 旧的**一个字节没动**
    # ⇒ 两个名字都指得准（这正是"唯一性保的是命中率"）
    assert find_episode(st, "中秋的杂草屋")[1] == "ok"
    assert find_episode(st, "中秋的杂草屋 2")[1] == "ok"
    print("    N2b: 撞名 ⇒ 新的加数字, 旧的不动, 两个名字都指得准")
