"""L2-b 造看法（`cognize`, P10 接线 · 2026-10-08）—— 一段的**最后一步**。

钉七件事:
    ① **接上了**: 有立足点 ⇒ 发一次 `digest.cognize`, 料里那几段都在;
    ② ⏸ **`group` 退役**（2026-10-13）⇒ 那条"L2 必须排在分群之后"的断言换成
       "**它不再被调用**"（顺序保证由 `ROUNDS` 的元组序承担, 见 `test_digest_rounds`）;
    ③ **产落对**: 新 belief 节点 + `supports` 边;
    ④ ⭐ **证据名单 = 料里印过的全部**（印出来的经历**不该**被判成编造 id）;
    ⑤ **没有立足点 ⇒ 0 次调用**（孤立经历不进 L2 —— 天然的归纳门槛）;
    ⑥ ⭐ **失败不连累整段**: 整包拒两次后放弃 ⇒ 只丢这一步, episode 照常落;
    ⑦ ⏸ **停产的行不陪葬**（2026-10-13 止血）: 她写一行 `experience` ⇒ 丢那一行,
       同包的看法照落、⛔ 不整包拒（判据见 `contract.digest.tables.COGNIZE_RETIRED`）。
"""
import sys
from pathlib import Path

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
        if task == T.DIGEST_SETTLE:
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
    """⭐ P10: 有立足点 ⇒ 发一次 `digest.cognize`; ⏸ `group` 退役后**不再被调用**。"""
    st = _store(tmp_path)
    a, old = _linked_pair(st)
    llm = RoundLLM(a={"episodes": [{"text": "老师约我去咖啡厅吃甜点", "title": "咖啡厅的甜点",
                                    "tags": ["咖啡厅"]}]},
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
    # ⏸ 2026-10-13: `group`（L2-a 分群）退役 ⇒ 那条"L2 必须排在 group 之后"的断言
    #    换成"**它不再被调用**"（顺序保证由 `ROUNDS` 的元组序承担, 见 test_digest_rounds）。
    assert T.DIGEST_GROUP not in llm.tasks, llm.tasks
    user = llm.user_of(T.DIGEST_COGNIZE)
    # ⭐ E1b: L2 写引用名之前也要看得到【已有的对象】（同 R1）
    for title in ("【这次的事】", "【这一类事】", "【现有认知】",
                  "【已有的对象】", "【角色人设（锚点）】"):
        assert title in user, (title, user)
    # ⏸ 【本段归类的群】随 `group` 退役一起撤（料与契约两边同撤, 守门
    #    `test_material_names_are_not_dead` 看着）—— 它那一格由 `member_of` 喂, 恒空。
    assert "【本段归类的群】" not in user, user
    # ⭐ 2026-10-14 区域化: 她认过的同类收进【这一类事】那一区（`old` 是早先那次, 不属于这一段）
    assert "《上次的甜点》" in user, user
    assert "↳ 关于" not in user, "这一对没有 `about` 边 ⇒ 那一行不出现"
    # ⚠️ **顺序也是契约**（`_sections_for` 拿 `ROUNDS.material` 逐字对账）:
    #    立足点在前, "这一类"在后, 已有的看法再往后。
    assert user.index("【这次的事】") < user.index("【这一类事】") < user.index("【现有认知】"), user
    # 产出落对了
    assert len(res.created_beliefs) == 1, res.created_beliefs
    new = res.created_beliefs[0]
    assert st.get(new).kind == "belief" and st.get(new).subject == "sensei"
    assert new in st.graph().targets(a, REL_SUPPORTS), "经历 → 新看法"
    # ⭐ 她只点了这一条 ⇒ 引擎把它的同类（`old`）也并成了证据
    assert new in st.graph().targets(old, REL_SUPPORTS), "一跳 akin 并进证据（零 LLM）"
    print(f"    digest 接线: {res.created_beliefs} 条看法; 料里带相似簇 + 并边落住")


def test_cognize_drops_a_retired_soak_row_and_keeps_the_beliefs(tmp_path):
    """⏸ **2026-10-13**: 停产之后她写一行 `experience` ⇒ **丢那一行**, 同包的看法照常落。

    ⚠️ **这一条守的是一个真口子**（不是"顺手加的用例"）: `experience` 停产前是**锚点**,
    而 `group` 退役后 `_groups_for_l2` 恒空 ⇒ `cognize` 传下来的 `group_ids` 恒是**空集**
    ⇒ `_clean_soak` 判"不在名单里" ⇒ **整包拒** ⇒ 这一段的看法**全丢**（她能写得出来:
    【现有认知】渲染的 `u…` 含 `experience` 节点, 老契约又教了两版）。
    判据 = B 案第三档（停止生产 ≠ 判非法; 罚她重写整段不值）。
    """
    st = _store(tmp_path)
    a, _old = _linked_pair(st)
    gid = st.add(make_node("experience", title="和老师吃饭送团子", ts="2026-09-20T10:00:00"))
    st.add_edge(REL_MEMBER_OF, a, gid, ts=_NOW)
    st.save()
    before = st.get(gid).text
    llm = RoundLLM(a={"episodes": [{"text": "老师约我去咖啡厅吃甜点", "title": "咖啡厅的甜点",
                                    "tags": ["咖啡厅"]}]},
                   cognize={"cognitions": [
                       {"experience": {"id": gid, "text": "停产之后不该再被写进来"}},
                       {"belief": {"text": "老师会把我随口说的话记住"},
                        "supports": [a]}]},
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    # ⭐ 同包那条看法**照落**（停产的一行不许陪葬它）
    assert len(res.created_beliefs) == 1, (res.created_beliefs, res.errors)
    assert res.cognize_warnings == [], res.cognize_warnings
    assert llm.tasks.count(T.DIGEST_COGNIZE) == 1, "⛔ 不该打回重试（它不是非法, 只是停产）"
    # ⏸ 沉淀一行都没写; 名字与正文原样
    assert res.soaked_groups == [], res.soaked_groups
    assert st.get(gid).text == before, "停产的类不许被覆写"
    assert st.get(gid).title == "和老师吃饭送团子", "⛔ 名字是地址, 谁也不许动"
    assert any("已停产" in d for d in res.contract_drops), res.contract_drops
    entries = [e["action"] for e in EvolutionLog.for_store(st).read()]
    assert "create" in entries and "rewrite" not in entries, entries
    print(f"    ⏸ 停产: 丢 1 行沉淀（{res.contract_drops}）, 看法 {res.created_beliefs} 照落")


def test_cognize_evidence_is_what_the_material_printed(tmp_path):
    """⭐ P10: **证据名单 = 料里印过的全部** —— 印出来的经历就能当证据, ⛔ 不许判"编造 id"。

    （L1 的教训: `target_ids` 少收一类 ⇒ 合法行被判"编造 id" ⇒ 整包拒 ⇒ 白跑一次重试。）

    ⚠️ **2026-10-13 改写（第二次）**: 群块退役后这一条钉"料里印的 = 她能引用的";
    现在**相似簇印出来的老经历也算**（不认它 ⇒ 她引不了自己早先认过的同类, 而引擎
    偏偏会把它们并进证据 —— 两边对不上）。所以这一条让她**明确引用那条老经历**。
    """
    st = _store(tmp_path)
    a, old = _linked_pair(st)
    gid = st.add(make_node("experience", title="甜点的那些事", ts="2026-09-20T10:00:00"))
    st.add_edge(REL_MEMBER_OF, old, gid, ts="2026-09-21T10:00:00")
    st.add_edge(REL_MEMBER_OF, a, gid, ts=_NOW)
    st.save()
    llm = RoundLLM(a={"episodes": [{"text": "老师约我去咖啡厅吃甜点", "title": "咖啡厅的甜点",
                                    "tags": ["咖啡厅"]}]},
                   cognize={"cognitions": [
                       {"belief": {"text": "甜点这件事她记了很久"},
                        "supports": [a, old]}]},          # ⭐ 老经历照引
                   split=_one_slice())
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    user = llm.user_of(T.DIGEST_COGNIZE)
    assert "【本段归类的群】" not in user, "群块已随 group 退役撤掉"
    assert "《咖啡厅的甜点》" in user, user            # 印出来了 ⇒ 就该能引用
    assert "《上次的甜点》" in user, user              # 老经历也印出来了（相似簇那一行）
    assert len(res.created_beliefs) == 1, (res.created_beliefs, res.errors)
    assert res.contract_drops == [], res.contract_drops      # 没被判"编造 id"
    new = res.created_beliefs[0]
    assert new in st.graph().targets(a, REL_SUPPORTS)
    assert new in st.graph().targets(old, REL_SUPPORTS), "老经历也当得了证据"
    print("    证据名单: 料里印过的（含相似簇里的老经历）就能当证据; 群块已不在料里")


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
