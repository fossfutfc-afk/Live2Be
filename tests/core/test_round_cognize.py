"""L2-b 造看法 / 写沉淀（`cognize`, P10 接线 · 2026-10-08）—— 一段的**最后一步**。

钉六件事:
    ① **接上了**: 有立足点 ⇒ 发一次 `digest.cognize`, 料里两段都在（群块 + 被连过的经历）;
    ② ⭐ **顺序**: 它排在 `group` **之后**（沉淀要写给本段刚归好类的那些类）;
    ③ **产落对**: 新 belief 节点 + `supports` 边 + 覆写 `experience.text`;
    ④ ⭐ **证据名单 = 料里印过的全部**（引用群块里的成员**不该**被判成编造 id）;
    ⑤ **没有立足点 ⇒ 0 次调用**（孤立经历不进 L2 —— 天然的归纳门槛）;
    ⑥ ⭐ **失败不连累整段**: 整包拒两次后放弃 ⇒ 只丢这一步, episode 照常落。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain import WikiStoreV2, make_node
from core.brain.entities import ensure_entities
from core.brain.evolution import EvolutionLog
from core.brain.graph import REL_AKIN, REL_MEMBER_OF, REL_SUPPORTS
from core.digest.pipeline import digest_segment
from core.session import make_event
from llm import task_labels as T
from tests import stub_tasks

CHAR = "c"
_NOW = "2026-10-08T21:00:00+08:00"


class RoundLLM:
    """六轮可控（不关心哪一轮的给空包）—— `cognize` 缺省"什么都不写"。"""

    def __init__(self, a=None, b=None, group=None, cognize=None, *, split=None):
        self.a = {"episodes": []} if a is None else a
        self.split = split
        self.b = {"relations": []} if b is None else b
        self.group = ({"attach": [], "new": [], "merge": []} if group is None else group)
        self.cognize = {"cognitions": []} if cognize is None else cognize
        self.calls: list[list[dict]] = []
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_SPLIT:            # R0: 缺省照搬 R1 那份应答里的区间
            return (self.split if self.split is not None
                    else stub_tasks.split_for_scripted(messages, self.a))
        if task == T.DIGEST_ATTRIBUTE:
            return {"attributions": []}
        return {T.DIGEST_RECORD: self.a, T.DIGEST_RELATE: self.b, T.DIGEST: self.b,
                T.DIGEST_GROUP: self.group, T.DIGEST_COGNIZE: self.cognize}[task]

    def user_of(self, task: str) -> str:
        return self.calls[self.tasks.index(task)][-1]["content"]


def _one_slice() -> dict:
    """一条覆盖全窗的骨架 —— 不显式给的话链条在 R0 就停（空骨架 ⇒ 收工）。"""
    return {"segments": [{"span": [3, 3], "abstract": "这一段"}]}


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    ensure_entities(st, char_name="伊草 遥香", sensei_name="老师")
    st.save()
    return st


def _ep(st, text, title, ts="2026-10-08T10:00:00+08:00"):
    return st.add(make_node("episode", text=text, title=title, ts=ts, event_seq=[3]))


def _mmt(seq, reply="嗯"):
    e = make_event("mmt", "chat", {"player": "老师", "reply": reply})
    e.seq = seq
    e.ts = _NOW
    return e


def _linked_pair(st):
    """摆一条**被 L1 连过**的本段经历（`akin` = 她连的; 这里直接造）。"""
    a = _ep(st, "老师约我去咖啡厅吃甜点", "咖啡厅的甜点")
    old = _ep(st, "更早的一次甜点", "上次的甜点", ts="2026-09-20T10:00:00+08:00")
    st.add_edge(REL_AKIN, a, old, ts=_NOW)
    st.save()
    return a, old


def test_digest_runs_cognize_after_group(tmp_path):
    """⭐ P10: 有立足点 ⇒ 发一次 `digest.cognize`; **它排在 `group` 之后**; 料里两段都在。"""
    st = _store(tmp_path)
    a, _old = _linked_pair(st)
    llm = RoundLLM(a={"episodes": [{"text": "老师约我去咖啡厅吃甜点", "title": "咖啡厅的甜点",
                                    "tags": ["咖啡厅"], "topics": ["咖啡厅"]}]},
                   group={"attach": [], "new": [{"block": "b1", "title": "甜点的那些事"}],
                          "merge": []},
                   cognize={"cognitions": [
                       {"belief": {"text": "老师会把我随口说的话记住", "subject": "sensei",
                                   "significance": 0.8},
                        "supports": [a]}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)], character_prompt="（人设：伊草 遥香）")

    assert res.ok, res.errors
    assert T.DIGEST_COGNIZE in llm.tasks, llm.tasks
    assert llm.tasks.index(T.DIGEST_GROUP) < llm.tasks.index(T.DIGEST_COGNIZE), \
        "L2 必须排在 group 之后（沉淀要写给本段刚归好类的那些类）"
    user = llm.user_of(T.DIGEST_COGNIZE)
    # ⭐ E1b: L2 写 `#entity:` 之前也要看得到【已有的对象】（同 R1）
    for title in ("【本段归类的群】", "【被连过的经历】", "【现有认知】",
                  "【已有的对象】", "【角色人设（锚点）】"):
        assert title in user, (title, user)
    # 产出落对了
    assert len(res.created_beliefs) == 1, res.created_beliefs
    new = res.created_beliefs[0]
    assert st.get(new).kind == "belief" and st.get(new).subject == "sensei"
    assert new in st.graph().targets(a, REL_SUPPORTS), "经历 → 新看法"
    print(f"    digest 接线: {res.created_beliefs} 条看法; 料里群块与经历块都在")


def test_cognize_soaks_the_group_and_leaves_a_trail(tmp_path):
    """⭐ P10: 段末那一步能**覆写沉淀** —— `soaked_groups` + `evolution.jsonl` 留痕。"""
    st = _store(tmp_path)
    a, _old = _linked_pair(st)
    gid = st.add(make_node("experience", title="和老师吃饭送团子", ts="2026-09-20T10:00:00"))
    st.add_edge(REL_MEMBER_OF, a, gid, ts=_NOW)
    st.save()
    text = "和老师一起吃饭的时候，我总先说自己不值得，他却每次都把话接住。"
    llm = RoundLLM(a={"episodes": [{"text": "老师约我去咖啡厅吃甜点", "title": "咖啡厅的甜点",
                                    "tags": ["咖啡厅"]}]},
                   cognize={"cognitions": [{"experience": {"id": gid, "text": text}}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert res.soaked_groups == [gid], res.soaked_groups
    assert st.get(gid).text == text
    assert st.get(gid).title == "和老师吃饭送团子", "⛔ 名字是地址, 这一趟不许动"
    # 群块把"本段新归入"摆出来了（沉淀的理由）
    user = llm.user_of(T.DIGEST_COGNIZE)
    assert f"群 {gid}《和老师吃饭送团子》" in user and "本段新归入 1 条" in user, user
    entries = [e["action"] for e in EvolutionLog.for_store(st).read()]
    assert "rewrite" in entries and "create" not in entries, entries
    print(f"    沉淀: 覆写 {res.soaked_groups}（账里有一笔 rewrite）")


def test_cognize_evidence_covers_both_blocks(tmp_path):
    """⭐ P10: **证据名单 = 料里印过的全部** —— 引用【群块】里的成员**不该**被判成编造 id。

    （L1 的教训: `target_ids` 少收一类 ⇒ 合法行被判"编造 id" ⇒ 整包拒 ⇒ 白跑一次重试。）
    """
    st = _store(tmp_path)
    a, old = _linked_pair(st)
    gid = st.add(make_node("experience", title="甜点的那些事", ts="2026-09-20T10:00:00"))
    st.add_edge(REL_MEMBER_OF, old, gid, ts="2026-09-21T10:00:00")   # 老成员（在群块里印）
    st.add_edge(REL_MEMBER_OF, a, gid, ts=_NOW)                      # 本段新归入
    st.save()
    llm = RoundLLM(a={"episodes": [{"text": "老师约我去咖啡厅吃甜点", "title": "咖啡厅的甜点",
                                    "tags": ["咖啡厅"], "topics": ["咖啡厅"]}]},
                   cognize={"cognitions": [
                       {"belief": {"text": "甜点这件事她记了很久"}, "supports": [old]}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert len(res.created_beliefs) == 1, (res.created_beliefs, res.errors)
    assert res.contract_drops == [], res.contract_drops      # 没被判"编造 id"
    assert res.created_beliefs[0] in st.graph().targets(old, REL_SUPPORTS)
    print("    证据名单: 群块里的老成员也能当证据（没被整包拒）")


def test_no_basis_no_call(tmp_path):
    """⭐ **孤立经历不进 L2** ⇒ 没有立足点时**一次都不发**（这一步不为空料付钱）。"""
    st = _store(tmp_path)
    _ep(st, "一个人坐在屋顶", "屋顶")                     # 没连过、也没归过类
    st.save()
    llm = RoundLLM(split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])
    assert res.ok, res.errors
    assert T.DIGEST_COGNIZE not in llm.tasks, llm.tasks
    assert res.created_beliefs == [] and res.soaked_groups == []
    print("    0 调用: 没有立足点就一次都不发")


def test_cognize_failure_does_not_rollback_the_batch(tmp_path):
    """⭐ P10: L2 失败 ⇒ **只丢这一步**: episode 照常落, `errors` 干净, 记账进 `cognize_warnings`。"""
    st = _store(tmp_path)
    a, _old = _linked_pair(st)
    llm = RoundLLM(a={"episodes": [{"text": "老师约我去咖啡厅吃甜点", "title": "咖啡厅的甜点",
                                    "tags": ["咖啡厅"]}]},
                   cognize={"cognitions": [                       # 编造 id ⇒ 整包拒
                       {"belief": {"text": "编的"}, "supports": ["m9999"]}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors                       # ⭐ 整段没被连累
    assert res.errors == [], res.errors
    assert res.created, res.created                 # R1 的 episode 落住了
    assert res.created_beliefs == [] and res.soaked_groups == []
    assert res.cognize_warnings, res.cognize_warnings
    assert llm.tasks.count(T.DIGEST_COGNIZE) == 2, "打回一次（feedback 重试）"
    assert [n.id for n in st.all() if n.kind == "belief"] == [], "一条看法都不该留下"
    print(f"    失败隔离: 打回 {llm.tasks.count(T.DIGEST_COGNIZE)} 次后放弃, 整段照常提交")
