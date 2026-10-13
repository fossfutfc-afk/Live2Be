"""R3「认人」（E4, 2026-10-08 重写）—— 她写下的**陌生名字** ⇒ 建一个 `entity` + **引擎补边**。

这一轮从"归属 + 载荷维护"（三动作）缩成**只认人**。钉六件事:
    ① ⭐ **事件驱动**: 本段**没有**解析不到的 `#entity:` ⇒ **一次调用都不发**;
    ② ⭐ **料**: 【要认的名字】（含它出现在哪几条）+【已有的对象】+ 人设 —— 没有本地号;
    ③ ⭐ **闭环**: 建出对象之后, 引擎**回头补边**（`about` 落上 + tag 归一成主名）;
    ④ **准入门槛**: `reason` 必填 · `name` 空 ⇒ 丢行（不建）;
    ⑤ **不重复建**: 提案一个【已有的对象】里有的名字 ⇒ 丢行（同一个人只有一个对象）;
    ⑥ **顺序**: 它排在**最后**（要看到 L2 的看法）。
"""
import sys
from pathlib import Path

from core.brain import WikiStoreV2, make_node
from core.brain.entities import ensure_entities
from core.digest.pipeline import digest_segment
from core.session import make_event
from llm import task_labels as T
from tests import stub_tasks

CHAR = "c"
_NOW = "2026-10-08T21:00:00+08:00"


class RoundLLM:
    """五轮可控（不关心哪一轮的给空包）—— `settle` 缺省"没有要认的"。"""

    def __init__(self, a=None, attr=None, *, split=None):
        self.a = {"episodes": []} if a is None else a
        self.attr = {"entities": []} if attr is None else attr
        self.split = split
        self.calls: list[list[dict]] = []
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_SPLIT:            # R0: 缺省照搬 R1 那份应答里的区间
            return (self.split if self.split is not None
                    else stub_tasks.split_for_scripted(messages, self.a))
        if task == T.DIGEST_RECORD:
            return self.a
        if task == T.DIGEST_RELATE:
            return {"relations": []}          # 这些用例不测 L1
        if task == T.DIGEST_SETTLE:
            return self.attr
        return {"cognitions": []}             # L2: 不造看法（本文件不测它）

    def user_of(self, task: str) -> str:
        return self.calls[self.tasks.index(task)][-1]["content"]


def _one_slice() -> dict:
    return {"segments": [{"span": [3, 3], "abstract": "这一段"}]}


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",),
                    sensei_name="老师", sensei_aliases=("sensei",))
    st.save()
    return st


def _episode(tags, text="第一次见到小玉", title="转角的相遇"):
    return {"text": text, "title": title, "tags": tags, "significance": 0.6,
            "topics": ["转角"]}


def _mmt(seq, reply="嗯"):
    e = make_event("mmt", "chat", {"player": "x", "reply": reply})
    e.seq = seq
    e.ts = _NOW
    return e


def test_stranger_tag_is_recognized_and_the_edge_is_backfilled(tmp_path):
    """⭐ E4 的主线: 陌生 tag ⇒ 发一次认人 ⇒ 建对象 ⇒ **引擎回头补边**（tag 也归一）。"""
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:小玉"])]},
                   attr={"entities": [{"name": "小玉", "aliases": ["tama"],
                                       "reason": "第一次出场, 之后还会来"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)], character_prompt="（人设）")

    assert res.ok, res.errors
    assert T.DIGEST_SETTLE in llm.tasks, llm.tasks
    assert llm.tasks[-1] == T.DIGEST_SETTLE, "它必须排在最后（要看到 L2 的看法）"
    # ⭐ E1b: **写 tag 的那一轮也要看得到【已有的对象】**（防自造 alias ⇒ 重复建对象）
    r1_user = llm.user_of(T.DIGEST_RECORD)
    assert "【已有的对象】" in r1_user and "x0001 老师" in r1_user, r1_user
    user = llm.user_of(T.DIGEST_SETTLE)
    for title in ("【要认的名字】", "【已有的对象】", "【角色人设（锚点）】"):
        assert title in user, (title, user)
    assert "小玉" in user and res.created[0] in user, user      # 名字 + 它出现在哪一条
    # ⭐ 建出来了
    assert len(res.created_entities) == 1, res.created_entities
    new_id = res.created_entities[0]
    assert st.get(new_id).kind == "entity" and st.get(new_id).name == "小玉"
    assert st.get(new_id).aliases == ["tama"]
    # ⭐ **闭环**: 那条经历现在挂到了新对象上, 而且 tag 归一成了主名
    ep = st.get(res.created[0])
    assert st.graph().targets(ep.id, "about") == [new_id], "补边没落上"
    assert "#entity:小玉" in ep.tags and "#entity:tama" not in ep.tags, ep.tags
    print(f"    认人: {res.created_entities} · {ep.id} → about → {new_id}")


def test_no_stranger_no_call(tmp_path):
    """⭐ **事件驱动**: 没有解析不到的名字 ⇒ 一次调用都不发（这一轮的成本判据）。"""
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:老师"])]}, split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert T.DIGEST_SETTLE not in llm.tasks, llm.tasks
    assert res.created_entities == []
    # ⚠️ 但 tag 照旧落了边（E1 的活, 不由这一轮负责）
    assert st.graph().targets(res.created[0], "about") == ["x0001"]
    print("    0 调用: 没有陌生人就不发（tag 的边照旧由引擎落）")


def test_reason_and_name_are_gates(tmp_path):
    """准入门槛: 没 `reason` / 没 `name` ⇒ **丢行**（不建对象）, 但整段照常提交。"""
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:小玉"])]},
                   attr={"entities": [{"name": "小玉"}, {"reason": "没名字"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert res.created_entities == [], "门槛没挡住"
    dropped = " ".join(res.contract_drops)
    assert "reason" in dropped and "name" in dropped, res.contract_drops
    assert [n.id for n in st.all() if n.kind == "entity"] == ["x0000", "x0001"]
    print(f"    门槛: 两条都被丢（{len(res.contract_drops)} 条记账）")


def test_known_name_is_not_created_again(tmp_path):
    """⭐ 不重复建: 提案一个【已有的对象】里有的名字（含别名）⇒ 丢行。"""
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:小玉"])]},
                   attr={"entities": [{"name": "sensei", "reason": "换个叫法"},
                                      {"name": "小玉", "reason": "真的新人"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert len(res.created_entities) == 1, res.created_entities     # 只建了"小玉"
    assert st.get(res.created_entities[0]).name == "小玉"
    assert any("已经在【已有的对象】里" in d for d in res.contract_drops), res.contract_drops
    print("    防重: `sensei` 被丢（它已经是 x0001 的别名）")
