"""「沉淀」（`settle`）—— 认人（建长期对象）+ 改名 / 写看法（2026-10-13 从"只认人"扩职）。

钉这些事:
    ① ⭐ **事件驱动**: 本段**谁也没提到**（没有引用、也没有陌生人）⇒ **一次调用都不发**;
    ② ⭐ **料**: 【这一段认下的对象】+【她写了、但库里还没有的名字】+【已有的对象】+ 人设;
    ③ ⭐ **闭环**: 建出对象之后, 引擎**回头补边**（`about` 落上 + tag/引用归一成主名）;
    ④ **准入门槛**: `reason` 必填 · `name` 空 ⇒ 丢行（不建）;
    ⑤ **不重复建**: 提案一个【已有的对象】里有的名字 ⇒ 丢行（同一个人只有一个对象）;
    ⑥ ⭐ **空 = 不改**: `"text": ""` 是"没话可说", ⛔ 不是"把看法清空"（零留痕、零丢账）;
    ⑦ ⭐ **改名**: 旧名降级成别名（两个叫法从此都指它）; **撞车只丢那一格**（⛔ 绝不合并）;
    ⑧ ⭐ **编造的 id ⇒ 丢行**（同包别的行照收 —— 这个相位**没有整包拒档**）;
    ⑨ ⭐ **名单是提示不是笼子**: 名单外的名字照样建（名单只扫本段新节点）;
    ⑩ ⭐ **水位**: 写看法时把"这一段的上界"落在 `text_seq` 上（防段级重算折两遍）;
    ⑪ **顺序**: 它排在**最后**（要看到本段全部新节点）。
"""
import sys
from pathlib import Path

from core.brain import WikiStoreV2, make_node
from core.brain.entities import ensure_entities
from core.brain.evolution import EvolutionLog
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
            }


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
    for title in ("【她写了、但库里还没有的名字】", "【已有的对象】", "【角色人设（锚点）】"):
        assert title in user, (title, user)
    assert "小玉" in user and res.created[0] in user, user      # 名字 + 它出现在哪一条
    # ⭐ 建出来了
    assert len(res.created_entities) == 1, res.created_entities
    new_id = res.created_entities[0]
    assert st.get(new_id).kind == "entity" and st.get(new_id).name == "小玉"
    assert st.get(new_id).aliases == ["tama"]
    # ⭐ **闭环**: 那条经历现在挂到了新对象上, 而且引用归一成了主名
    ep = st.get(res.created[0])
    assert st.graph().targets(ep.id, "about") == [new_id], "补边没落上"
    assert ep.entity == ["小玉"] and ep.tags == ["转角"], (ep.entity, ep.tags)
    print(f"    认人: {res.created_entities} · {ep.id} → about → {new_id}")


def test_the_baseline_makes_it_run_every_segment(tmp_path):
    """⭐ **每一段都跑**（2026-10-18 改口径）: 她自己的那一格**无条件**摆上桌 ——
    "成长基线"要有机会长, 就不能只在"本段提到过谁"时才开会。

    ⚠️ **旧口径是"没有陌生人、也没有引用 ⇒ 一次调用都不发"**（2026-10-13）——
    那是省调用的决定, 代价是基线**永远不更新**（真机 `x0000.text_seq` 至今是 None,
    而 5 条 `about → x0000` 全是 2026-09-26 的老边）。
    代价 = 每段多一次 settle 调用; 原本多数段已经在跑（本段的经历几乎都带引用）。
    """
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [{"text": "一个人在屋顶坐着, 天很蓝。", "title": "屋顶",
                                    "tags": ["屋顶"]}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert T.DIGEST_SETTLE in llm.tasks, llm.tasks
    user = llm.user_of(T.DIGEST_SETTLE)
    assert "【你自己】" in user and "x0000" in user, user
    assert res.created_entities == [] and res.rewritten_entities == []
    print("    基线: 这一段没有活干也照发（【你自己】无条件在料里）")


def test_the_baseline_is_writable(tmp_path):
    """⭐ 她自己那一格**可改**（2026-10-18）: `id=x0000` 的 `text` 走 `apply_stances`,
    水位照落 —— 这是成长基线**唯一**的写入口。"""
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:老师"])]},
                   attr={"entities": [{"id": "x0000",
                                       "text": "我不再只是躲在没人经过的那一面了"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert res.rewritten_entities == ["x0000"], res.rewritten_entities
    assert st.get("x0000").text == "我不再只是躲在没人经过的那一面了"
    assert st.get("x0000").text_seq == 3, "水位 = 本段 `interact_max`（防重跑折两遍）"
    print(f"    基线: 改了（水位 {st.get('x0000').text_seq}）")


def test_a_referenced_object_makes_it_run(tmp_path):
    """⭐ 新口径的另一半: **本段提到过谁就发**（哪怕没有新名字）——
    那才有对象可**改名 / 写看法**; 顺便钉住**水位**（`text_seq` = 本段上界）。"""
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:老师"])]},
                   attr={"entities": [{"id": "x0001",
                                       "text": "老师是第一个不会嫌弃我的人"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert T.DIGEST_SETTLE in llm.tasks, llm.tasks
    assert res.rewritten_entities == ["x0001"], res.rewritten_entities
    assert st.get("x0001").text == "老师是第一个不会嫌弃我的人"
    assert st.get("x0001").text_seq == 3, "水位 = 本段 `interact_max`"
    print(f"    写看法: {res.rewritten_entities} · 水位 {st.get('x0001').text_seq}")


def test_empty_text_means_no_change_not_clear(tmp_path):
    """⭐ **空 = 不改, 不是清空**（用户 2026-10-13 裁）—— 钉死这一条, 别让它退回"覆盖成空"。"""
    st = _store(tmp_path)
    st.get("x0001").text = "老师是第一个不会嫌弃我的人"
    st.save()
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:老师"])]},
                   attr={"entities": [{"id": "x0001", "text": ""}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert st.get("x0001").text == "老师是第一个不会嫌弃我的人", "空 text 把看法抹掉了"
    assert res.rewritten_entities == [], res.rewritten_entities
    assert res.contract_drops == [], "空值不是「丢了东西」—— ⛔ 别记丢账"
    entries = [e.get("action") for e in EvolutionLog.for_store(st).read()]
    assert "rewrite" not in entries, entries
    print("    空 = 不改: 看法原样、零留痕、零丢账")


def test_rename_lands_and_old_name_becomes_an_alias(tmp_path):
    """⭐ 改名: 新名上任、**旧名降级成别名**（两个叫法从此都指它）+ 账里一笔 `rename`。"""
    st = _store(tmp_path)
    old = st.add(make_node("entity", name="那个女生", ts="2026-10-01T10:00:00+08:00"))
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:那个女生"])]},
                   attr={"entities": [{"id": old, "name": "小玉"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert res.renamed_entities == [old], res.renamed_entities
    node = st.get(old)
    assert node.name == "小玉" and "那个女生" in node.aliases, (node.name, node.aliases)
    # ⭐ 改名之后**两个叫法都命中同一个对象**（`find_entity` 走 name + aliases）
    from core.brain.entities import find_entity
    assert find_entity(st, "那个女生")[0].id == old
    assert find_entity(st, "小玉")[0].id == old
    entries = [e for e in EvolutionLog.for_store(st).read() if e.get("action") == "rename"]
    assert entries and entries[-1]["changed"]["name"] == ["那个女生", "小玉"], entries
    print(f"    改名: {old} 那个女生 → 小玉（旧名成别名, 两个叫法都命中）")


def test_rename_collision_drops_only_that_field(tmp_path):
    """⛔ **撞车绝不合并**: 新名已经属于**别的**对象 ⇒ 只丢 `name` 那一格（`text` 照收）。"""
    st = _store(tmp_path)
    other = st.add(make_node("entity", name="小玉", ts="2026-10-01T10:00:00+08:00"))
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:老师"])]},
                   attr={"entities": [{"id": "x0001", "name": "小玉",
                                       "text": "老师是第一个不会嫌弃我的人"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert res.renamed_entities == [], "撞车还改了名"
    assert st.get("x0001").name == "老师", "把自己的名字改成了别人的"
    assert st.get(other).name == "小玉", "另一个对象被并掉了"
    assert res.rewritten_entities == ["x0001"], "撞车那一行里的 text 该照收"
    print("    撞车: 只丢 name 那一格, text 照收, 两个对象各自安好")


def test_fabricated_id_is_dropped(tmp_path):
    """⭐ **编造的 id ⇒ 丢行**（2026-10-13 用户裁; 同包别的行照收 —— 这个相位没有整包拒档）。"""
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:老师"])]},
                   attr={"entities": [{"id": "x0009", "text": "她其实很温柔"},
                                      {"id": "x0001", "text": "老师是第一个不会嫌弃我的人"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert res.errors == [], "⛔ 这一档不该是整包拒"
    assert res.rewritten_entities == ["x0001"], "坏行连累了同包的好行"
    assert any("不在【你自己】/【这一段认下的对象】里" in d for d in res.contract_drops), \
        res.contract_drops
    print("    编造 id: 丢那一行, 同包的行照收（没白花一次重试）")


def test_offlist_name_is_still_created(tmp_path):
    """⭐ **名单是提示, 不是笼子**（用户 2026-10-13 裁）: 名单外的名字**照样建** ——
    名单只扫**本段新节点**, 而"这一段让我想记住的人"完全可能没标引用。"""
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:小玉"])]},
                   attr={"entities": [{"name": "便利店的店员", "reason": "她帮过我"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert len(res.created_entities) == 1, res.created_entities
    assert st.get(res.created_entities[0]).name == "便利店的店员"
    assert res.contract_drops == [], "名单外的名字不该被丢"
    print("    名单外: 照样建（引擎只拦能判定的: 已在库里 / 超长 / 空）")


def test_a_new_object_can_carry_its_first_view(tmp_path):
    """⭐ **刚认识就有话说**: `text` 写在**没有 `id`** 的那一行里（不用等下一段）。"""
    st = _store(tmp_path)
    llm = RoundLLM(a={"episodes": [_episode(["转角", "#entity:小玉"])]},
                   attr={"entities": [{"name": "小玉", "reason": "这一段来了三次",
                                       "text": "她抱着一摞书, 说社团忙不过来"}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    node = st.get(res.created_entities[0])
    assert node.name == "小玉" and node.text == "她抱着一摞书, 说社团忙不过来"
    assert node.text_seq == 3, "建的时候也该落水位（这条 text 是哪一段写下的）"
    print(f"    顺手装上第一句看法: {node.id} · 水位 {node.text_seq}")


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
