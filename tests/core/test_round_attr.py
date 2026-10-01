# -*- coding: utf-8 -*-
"""R3 归属轮（第 3 步）的**编排**测试 —— DESIGN_GRAPH_V4 §8 / §8.3。

三件事在这里被钉住:
    ① 它排在**最后**（R1 → R4 → R2 → **R3**）—— 它要挂的是本轮**全部**新节点;
    ② 它的输入 = 候选表（只有身份）+ 命中集的载荷 + 本轮新节点（本地 id）;
    ③ 没挂上不是错（**判不出来就别挂**），但**挂错**要能在 `evolution.jsonl` 里看见。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from contract.digest_registry import PHASE_ATTRIBUTE, digest_registry
from core.brain.wiki_v2 import WikiStoreV2, make_node
from core.brain.wiki_v2.digest import digest_segment
from core.brain.wiki_v2.entities import ensure_entities, hit_set, new_nodes_block
from core.session import make_event
from llm import task_labels as T

ROOT = Path(__file__).resolve().parent.parent.parent
CHAR = "c"


class AttrLLM:
    """四轮可控: A / R4（默认空包）/ B / R3。"""

    def __init__(self, a, b, attr=None, close=None):
        self.a, self.b = a, b
        self.attr = {"attributions": []} if attr is None else attr
        self.close = {"add": [], "close": []} if close is None else close
        self.tasks: list[str | None] = []
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_A:
            return self.a
        if task == T.DIGEST_CLOSE:
            return self.close
        if task in (T.DIGEST_B, T.DIGEST):
            return self.b
        if task == T.DIGEST_ATTR:
            return self.attr
        raise RuntimeError(f"意外调用 task={task!r}")

    def user_of(self, task: str | None) -> str:
        idx = self.tasks.index(task)
        return self.calls[idx][-1]["content"]


def _store(tmp_path, *, entities=True) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    if entities:
        ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",),
                        sensei_name="老师")
        st.save()
    return st


def _events(*items):
    out = []
    for typ, sub, payload, seq in items:
        e = make_event(typ, sub, payload)
        e.seq = seq
        out.append(e)
    return out


def _mmt(seq, player="老师", reply="嗯"):
    return ("mmt", "chat", {"player": player, "reply": reply}, seq)


def _a(text="模型店门口", hint="老师"):
    """R1: 一条带 `about_hint` 的 episode（归属轮就是靠它做映射的）。"""
    ep = {"text": text, "title": text[:8], "tags": ["模型店"]}
    if hint:
        ep["about_hint"] = hint
    return {"episodes": [ep]}


def _b(episode_ids, text="老师会等我"):
    return {"decisions": [{"episode": i, "decision": "add", "kind": "belief",
                           "subject": "sensei", "text": text} for i in episode_ids],
            "evidence": [], "affection_exp_delta": 0}


# ---------------------------------------------------------------------------
# 契约: 三种行 + 拒整包
# ---------------------------------------------------------------------------

def test_parse_attribution_three_shapes():
    raw = {"attributions": [
        {"action": "attach", "entity": "c0001", "hint": "老师", "nodes": ["u0001"]},
        {"action": "new_entity", "name": "小玉", "aliases": ["tama"],
         "reason": "第一次出场, 之后还会来", "nodes": ["u0002"]},
        {"action": "rewrite", "entity": "c0001", "text": "他是第一个不嫌弃我的人。",
         "state": ["今天戴了眼镜", "  "]},
    ]}
    rows, result = digest_registry.parse_attribution(
        raw, entity_ids={"c0001"}, node_ids={"u0001", "u0002"})
    assert result.is_valid, result.errors
    assert rows == [
        {"action": "attach", "entity": "c0001", "hint": "老师", "nodes": ["u0001"]},
        {"action": "new_entity", "name": "小玉", "aliases": ["tama"],
         "reason": "第一次出场, 之后还会来", "nodes": ["u0002"]},
        {"action": "rewrite", "entity": "c0001", "text": "他是第一个不嫌弃我的人。",
         "state": ["今天戴了眼镜"]}]                      # 空串的行被剔掉


def test_parse_attribution_rejections():
    """形状错与引用错都**拒整包**（这里的 id 是引擎渲染出来的闭集）。"""
    def _p(rows, entities={"c0001"}, nodes={"u0001"}):
        return digest_registry.parse_attribution(
            {"attributions": rows}, entity_ids=entities, node_ids=nodes)

    _, r = _p([{"action": "attach", "entity": "c0009", "nodes": ["u0001"]}])
    assert not r.is_valid and any("不在候选表内" in e for e in r.errors)
    _, r = _p([{"action": "attach", "entity": "c0001", "nodes": ["u0009"]}])
    assert not r.is_valid and any("不在本轮新节点里" in e for e in r.errors)
    _, r = _p([{"action": "attach", "entity": "c0001"}])
    assert not r.is_valid and any("nodes 必须是数组" in e for e in r.errors)
    _, r = _p([{"action": "attach", "entity": "c0001", "nodes": []}])
    assert not r.is_valid and any("不能是空的" in e for e in r.errors)
    _, r = _p([{"action": "new_entity", "name": "小玉", "nodes": ["u0001"]}])
    assert not r.is_valid and any("必须填 reason" in e for e in r.errors)
    _, r = _p([{"action": "new_entity", "reason": "r", "nodes": ["u0001"]}])
    assert not r.is_valid and any("必须填 name" in e for e in r.errors)
    _, r = _p([{"action": "rewrite", "entity": "c0001"}])
    assert not r.is_valid and any("至少要给 text 或 state" in e for e in r.errors)
    _, r = _p([{"action": "detach", "entity": "c0001"}])
    assert not r.is_valid and any("action 非法" in e for e in r.errors)
    _, r = _p([])                                        # 空包合法
    assert r.is_valid
    _, r = digest_registry.parse_attribution({}, entity_ids=set(), node_ids=set())
    assert not r.is_valid and any("缺键" in e for e in r.errors)


def test_schema_renders_the_three_actions():
    text = digest_registry.build_schema(PHASE_ATTRIBUTE)
    for token in ('"attributions"', "attach", "new_entity", "rewrite", "reason"):
        assert token in text, token
    assert "c0001" in text and "u0001" in text          # 本地 id 的形状要看得见


# ---------------------------------------------------------------------------
# 输入侧: 本轮新节点（本地 id）
# ---------------------------------------------------------------------------

def test_new_nodes_block_render(tmp_path):
    st = _store(tmp_path)
    st.add(make_node("episode", text="模型店门口", title="模型店", event_seq=[3],
                     ts="2026-09-25T10:00:00"))
    pid = st.add(make_node("promise", text="周六模型店 —— 真的去了",
                           outcome="kept", event_seq=[3], ts="2026-09-25T10:00:00"))
    text, local_of = new_nodes_block(st, ["m0001", pid, "m9999"])
    # ⭐ 2026-09-29 形状: 类型与名字**都进头**（`marks.head`）—— 原来 `u0001 [episode] 「模型店」 正文`
    assert "〔u0001｜《模型店》｜episode〕模型店门口" in text, text
    assert "〔u0002｜promise·已兑现〕" in text, text
    assert local_of == {"m0001": "u0001", pid: "u0002"}      # 不存在的 id 跳过
    assert new_nodes_block(st, [])[0] == ""


def test_hit_set_reads_hints_and_bodies(tmp_path):
    """命中集是**确定性**的（§8.3）: hint 精确/包含 ∪ 称呼命中正文（≥2 字）。"""
    st = _store(tmp_path)
    assert hit_set(st, hints=["老师"]) == ["x0001"]          # hint 通道
    assert hit_set(st, hints=["老"]) == []                   # 单字 hint: 既不精确也不够长
    assert hit_set(st, texts=["今天老师夸了我"]) == ["x0001"]  # 正文通道
    assert hit_set(st, texts=["遥香在店里"]) == ["x0000"]     # 角色自己的名字 → self


# ---------------------------------------------------------------------------
# 编排: 位置 / 料 / 产出
# ---------------------------------------------------------------------------

def test_r3_attaches_by_hint_and_writes_alias(tmp_path):
    """⭐ 端到端: R1 的 `about_hint` → R3 映射到候选表里的对象 → `about` 边 + 顺手写别名。"""
    st = _store(tmp_path)
    attr = {"attributions": [
        {"action": "attach", "entity": "c0002", "hint": "老师", "nodes": ["u0001"]},
    ]}
    llm = AttrLLM(_a("模型店门口", hint="老师"), _b(["m0001"]), attr)

    res = digest_segment(st, llm, _events(_mmt(3)))
    assert res.ok, res.errors

    # 四轮的顺序: **A → R4 → B → R3**（§8 的批内顺序 —— 每段四步真的都跑了）
    assert llm.tasks == [T.DIGEST_A, T.DIGEST_CLOSE, T.DIGEST_B, T.DIGEST_ATTR], llm.tasks
    # ⭐ 料: 候选表（只有身份）+ 本轮新节点（本地 id）
    r3 = llm.user_of(T.DIGEST_ATTR)
    assert "c0001" in r3 and "c0002" in r3 and "u0001" in r3
    assert "模型店门口" in r3
    # ⭐ 产出: 那条新 episode 挂到了 sensei（x0001）上
    ep = res.created[0]
    assert st.graph().targets(ep, "about") == ["x0001"]
    # hint 顺手写回别名（"老师"已在别名里 → 不动; 换一个自造称呼才写）
    attr2 = {"attributions": [
        {"action": "attach", "entity": "c0002", "hint": "那个大人", "nodes": ["u0001"]},
    ]}
    llm2 = AttrLLM(_a("又路过那家店", hint="那个大人"), _b(["m0003"]), attr2)
    res2 = digest_segment(st, llm2, _events(_mmt(4)))
    assert res2.ok, res2.errors
    assert "那个大人" in st.get("x0001").aliases


def test_r3_new_entity_and_rewrite_load(tmp_path):
    """`new_entity`（带理由）+ `rewrite`（改载荷）—— 一次调用里两种行都落地。"""
    st = _store(tmp_path)
    attr = {"attributions": [
        {"action": "new_entity", "name": "小玉", "aliases": ["tama"],
         "reason": "她第一次出场, 之后还会来", "nodes": ["u0002"]},
        {"action": "rewrite", "entity": "c0002",
         "text": "他是第一个不嫌弃我的人。", "state": ["今天戴了眼镜"]},
    ]}
    llm = AttrLLM(_a("遇到小玉"), _b(["m0001"]), attr)

    res = digest_segment(st, llm, _events(_mmt(3)))
    assert res.ok, res.errors
    assert len(res.created_entities) == 1
    xin = res.created_entities[0]
    node = st.get(xin)
    assert node.kind == "entity" and node.name == "小玉" and node.aliases == ["tama"]
    # 新对象挂上那条 episode（u0002 = R2 新建的 belief）
    belief = [n for n in st.all() if n.kind == "belief"][0]
    assert st.graph().targets(belief.id, "about") == [xin]
    # 载荷改写（立场 + 现状）
    sensei = st.get("x0001")
    assert sensei.text == "他是第一个不嫌弃我的人。"
    assert sensei.state == ["今天戴了眼镜"]
    assert st.audit() == []


def test_r3_skipped_without_new_nodes(tmp_path):
    """本段没有新节点 ⇒ 没有可归属的对象 ⇒ **不发这次调用**（0 次）。"""
    st = _store(tmp_path)
    llm = AttrLLM({"episodes": []},
                  {"decisions": [], "evidence": [], "affection_exp_delta": 0})
    res = digest_segment(st, llm, _events(_mmt(3)))
    assert res.ok, res.errors
    assert T.DIGEST_ATTR not in llm.tasks
    assert res.created_entities == []


def test_r3_failure_rolls_back_the_batch(tmp_path):
    """R3 的形状错 ⇒ 拒整包 + 反馈重试; 耗尽 ⇒ **整批失败**, 前面几轮的节点也回滚。"""
    st = _store(tmp_path)
    attr = {"attributions": [{"action": "attach", "entity": "c0009", "nodes": ["u0001"]}]}
    llm = AttrLLM(_a("模型店门口"), _b(["m0001"]), attr)

    res = digest_segment(st, llm, _events(_mmt(3)))
    assert not res.ok
    assert any("不在候选表内" in e for e in res.errors)
    assert [n.id for n in st.all() if n.kind != "entity"] == []   # 全回滚
    assert res.created_entities == [] and res.created == []
