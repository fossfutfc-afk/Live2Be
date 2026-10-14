"""③ L1「判关系」的**观测账**（P6, 2026-10-08）—— 一行日志要看出"孤立经历"。

## 为什么有它

L1 判完关系，"这一段有几条经历**一条边都没连上**"这件事谁都不知道 —— 而孤立经历
**不进 L2**（`docs/DESIGN_DIGEST_TWO_PASSES.md` §3 的**天然归纳门槛**）⇒ 这一格正是
下一趟（造看法 / 写正文）**收料的实际范围**。没有这行账, L2 的料摆几组只能靠猜。

## 这一行里最容易读错的两格

  · `rels` = **边表真的长了几条**（`store.edges()` 的增量）—— ⛔ **不是 `rows`**。
    `add_edge` **幂等**（同 `(rel, src, dst)` 只留一条）⇒ 她写重复行时 `rows > rels`。
    （我第一版把 `rels` 写成 `len(rows)`, 那一格就是假的。）
  · `sim` = **这一段有没有语义那一路**（`1` = embedder 在）—— **前提读数**。
    `cands=0` 有两种相反的解释: "这一段真没有像的旧经历"（结论）vs "语义那一路没起来"
    （**能力问题**: `[embed]` 服务不在 ⇒ `like` 自动降级）。有 `sim` 才分得开。

⏸ **2026-10-14 换了一格**（用户裁"先把 `topics` 退役掉"）: 从前记的是 `pool`
（库里 **标了 `轴`** 的条数）—— 那个数在真机上恒等于 3/21, 而候选**恒 0 条**
（有轴的三条互相不共轴）⇒ 它解释不了任何事。现在候选由 `like(spec="digest")` 排,
`sim` 才是"cands=0 的解释器"。
⚠️ 用户 2026-10-08 裁: **只观测**, 不写补数据的维护脚本
（*"反正以后也要测试新的 digest，之后就删掉数据重来了，现在不急"*）。
"""
import logging
import sys
from pathlib import Path

from core.brain import WikiStoreV2, make_node
from core.digest.pipeline import digest_segment
from core.session import make_event
from llm import task_labels as T
from tests import stub_tasks

CHAR = "c"
NOW = "2026-10-05T10:00:00+08:00"
#: L1 的日志 logger（`relate.py` 的 `__name__`）
LOGGER = "core.digest.rounds.relate"
#: 本段那一条切片（seq 3 = 那条 mmt）
SPLIT = {"segments": [{"span": [3, 3], "abstract": "又见苔藓"}]}


def _store(tmp_path, *, old_text="天台上的苔藓旁", old_tags=("苔藓",)) -> WikiStoreV2:
    """预置: `m0001` = 一条**旧经历** + `m0002` = 看法（`u0001`）+ `m0009` = 看法（`u0002`）。

    ⏸ 第二条认知原来是 `profile`（玩家画像 `e0001`）—— 2026-10-14 那个 kind 删格式 ⇒
    改成 belief（**今天唯一的认知 kind**）, id 钉成 `m0009`（"m0003 = 本段新建的经历"
    是本文件几十条用例的公共前提, 别让它被挤掉）。

    ⚠️ 旧经历那段正文**故意跟本段的新经历撞词**（`苔藓`）—— ⭐ 2026-10-14 起候选由
    `like(spec="digest")` 的**字面路**排出来（测试里没有 embedder ⇒ 语义那一路不在）,
    所以"摆得出候选"= 两条**真的有字面重叠**。想验"摆不出", 就把 `old_text` 换成不搭界
    的句子（`tags` 也要换掉 —— tags 命中是最强的那一路）。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    st.add(make_node("episode", text=old_text, title="夜谈", tags=list(old_tags),
                     event_seq=[2], ts="2026-09-01T10:00:00+08:00"))
    st.add(make_node("belief", text="老师是第一个不会嫌弃我的人", subject="sensei",
                     significance=0.9, event_seq=[2]))
    second = make_node("belief", text="老师总是很忙", subject="sensei",
                       significance=0.85, event_seq=[2])
    # ⚠️ **钉死 id = `m0000`**（比 m0002 小）—— 本文件十几条断言的前提是
    # "本段新建的那条经历 = m0003"; `next_id("m")` 取**最大序号 +1** ⇒ 只有钉在 m0003
    # 以下的 id 才不会把它挤成 m0004。
    second.id = "m0000"
    st.add(second)
    st.save()
    return st


def _mmt(seq=3, player="老师", reply="苔藓还在那儿", ts=NOW):
    return make_event("mmt", "chat", {"player": player, "reply": reply}, seq=seq, ts=ts)


def _record(*, text="又去看了那片苔藓", title="又见苔藓", tags=("苔藓",)):
    """R1 的应答（本段新建 `m0003`）。"""
    return {"episodes": [{"text": text, "title": title, "tags": list(tags)}]}


def _line(caplog) -> str:
    lines = [r.getMessage() for r in caplog.records if r.name == LOGGER]
    assert lines, "L1 那一轮**一行日志都没有**（P6 的观测账没落）"
    return lines[-1]


def _fields(line: str) -> dict:
    assert line.split()[0] == "digest_relate", f"日志第一段必须是轮名: {line!r}"
    out = {}
    for tok in line.split()[1:]:
        k, _, v = tok.partition("=")
        out[k] = v
    return out


class _Stub:
    """按 `task` 分派（⛔ 不按中文关键字分派）—— L1 那一轮用预置应答, 其余走标准包。"""

    def __init__(self, *, relate, record=None, split=SPLIT):
        self._relate, self._record, self._split = relate, record or _record(), split
        #: L1 那一轮的 user 串（料摆了什么, 从调用点看）
        self.users: list[str] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        if task == T.DIGEST_RELATE:
            self.users.append("\n".join(str(m.get("content") or "") for m in messages
                                        if m.get("role") == "user"))
            return self._relate
        if task == T.DIGEST_RECORD and self._record is not None:
            return self._record
        reply = stub_tasks.annotation_reply(task, messages, split=self._split)
        if reply is None:
            raise AssertionError(f"桩不认识 task={task!r}")
        return reply


def _run(tmp_path, caplog, *, relate, record=None, old_text="天台上的苔藓旁",
         old_tags=("苔藓",)):
    """跑一段 digest; 回 `(store, 那一行的字段表, L1 那轮的 user 串)`。"""
    st = _store(tmp_path, old_text=old_text, old_tags=old_tags)
    llm = _Stub(relate=relate, record=record)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        res = digest_segment(st, llm, [_mmt()])
    assert res.ok, res.errors
    return st, _fields(_line(caplog)), llm.users[-1]


# ---------------------------------------------------------------------------
# ① 七个字段逐一钉住（`rels` = 真边数, ⛔ 不是行数）
# ---------------------------------------------------------------------------

def test_relate_log_counts_real_edges_not_rows(tmp_path, caplog):
    """⭐ `rows` vs `rels`: 她写两条**一模一样**的 `akin` ⇒ 行 2 **边 1**。

    同一对节点只留一条边（`add_edge` 幂等）—— 所以 `rels` 必须是**边表增量**。
    这一格写成 `len(rows)` 的话, 这段的账就永远比真相多一条（我第一版正是那样写的）。
    """
    dup = {"episode": "m0003", "akin": "m0001"}
    _st, f, _user = _run(tmp_path, caplog, relate={"relations": [dup, dict(dup)]})

    assert f == {"rows": "2", "rels": "1", "alone": "0", "lone": "-",
                 "cands": "1", "sim": "0", "dropped": "0"}, f


def test_lone_episode_is_named_in_the_log(tmp_path, caplog):
    """"什么关系都没看出来"（✅ 合法答案）⇒ 本段那条经历是**孤立的**, 且**点名**。

    点名的意义: 孤立经历不进 L2 ⇒ 下一趟的范围要能**照着 id 去对**。
    """
    st, f, _user = _run(tmp_path, caplog, relate={"relations": []})

    assert f["rows"] == "0" and f["rels"] == "0"
    assert f["alone"] == "1" and f["lone"] == "m0003", f
    assert f["cands"] == "1", "旧经历（m0001）跟本段有字面重叠 ⇒ 摆得出候选"
    assert not [e for e in st.graph().edges if "m0003" in (e.src, e.dst)], \
        "一行关系都没连上 ⇒ 图上没有它的边"


def test_dropped_row_leaves_the_episode_lone(tmp_path, caplog):
    """两端**类型不对** ⇒ **丢那一行**（不毁整段）: `dropped=1` 且那条经历仍孤立。

    ⚠️ 这一格也是"契约层说过的话"落到账上的那一格（`call._round_call` 记进
    `result.contract_drops`）—— 计数取的是**这一轮调用前后**的差, 不靠中文子串匹配。
    ⏸ 2026-10-14 之前这里用的是另一条丢行路径（`on` 不在两端 `topics` 交集里）——
    那条判据随 `topics` 退役了, 换成"`akin` 指向一条**看法**"（`kind_of` 那一关）。
    """
    _st, f, _user = _run(tmp_path, caplog,
                         relate={"relations": [{"episode": "m0003", "akin": "u0001"}]})

    assert f["dropped"] == "1" and f["rows"] == "0" and f["rels"] == "0", f
    assert f["alone"] == "1" and f["lone"] == "m0003", f


def test_cognition_side_local_id_lands_on_the_real_node(tmp_path, caplog):
    """认知那一端写**本地号**（`u0001`）—— 边要落到**真身**上, 且算"连上了"。

    这一条钉的是 `apply_relations` 的 `id_map` 翻译（`u0001 → m0002`）。
    ⚠️ 它**不是**在钉 `_lone_episodes` 的翻译 —— 那里根本不需要翻译（经历的 id
    永远是真身, 见那个函数的 docstring; 变异验红证明过）。
    """
    st, f, _user = _run(tmp_path, caplog,
                        relate={"relations": [{"episode": "m0003", "supports": "u0001"}]})

    assert f["rows"] == "1" and f["rels"] == "1", f
    assert f["alone"] == "0" and f["lone"] == "-", f
    assert st.graph().targets("m0003", "supports") == ["m0002"], "u0001 → m0002"


def test_row_between_two_cognitions_does_not_connect_the_episode(tmp_path, caplog):
    """⛔ **有行 ≠ 这条经历被连上**: 两端都是认知的行照样是一行, 经历一条都没沾。

    （就是"能写出来的边"与"本段经历被连上了"这两件事的分界 —— 把 `alone` 写成
    "没有行就没有孤立"的实现会在这里红。）
    """
    _st, f, _user = _run(tmp_path, caplog,
                         relate={"relations": [{"belief": "u0001", "contradicts": "u0002"}]})

    assert f["rows"] == "1" and f["rels"] == "1", f
    assert f["alone"] == "1" and f["lone"] == "m0003", f


# ---------------------------------------------------------------------------
# ② 摆不出候选时, 抬头要留着并**说清为什么空**
# ---------------------------------------------------------------------------

def test_empty_candidate_section_says_why(tmp_path, caplog):
    """召回摆不出候选 ⇒ 她看得见【现有经历（候选）】+ 一句"为什么没有"。

    ⚠️ 空串会被 `_join_sections` 的 `if body` **连抬头一起吞掉** ⇒ 她既看不到这一格,
    也不知道"候选是空的"（而"没有可接的旧事"本身是信息: 那就不该硬写 `akin`）。
    ⏸ 2026-10-14: 从前这里是**两个**空（"本段没标轴" ≠ "没有一条同轴"）——`topics`
    退役后只剩一个（召回没找到）, 文案也跟着收成一句。
    """
    _st, f, user = _run(tmp_path, caplog, relate={"relations": []},
                        old_text="一个人坐在屋顶上", old_tags=("屋顶",))

    assert f["cands"] == "0" and f["sim"] == "0", f
    assert "【现有经历（候选）】" in user, user
    assert "（无 —— 召回没找到跟这一段像的旧经历）" in user, user


def test_candidates_come_from_like_with_a_reason(tmp_path, caplog):
    """⭐ 2026-10-14: 候选 = `like(spec="digest")` 排出来的 —— **带分与为什么**。

    判据（"看不见就写不出来"那条）: 每行有 `候选 0.xx` 那一格, 下面一行 `→ 为什么: …`
    —— 她据此判"是不是同一类事", 而分数**不是闸门**（同一个人的经历天然都像）。
    """
    _st, f, user = _run(tmp_path, caplog, relate={"relations": []})

    assert f["cands"] == "1", f
    line = next(ln for ln in user.splitlines() if "m0001" in ln)
    assert "候选 0." in line, line
    assert any(ln.strip().startswith("→ 为什么:") for ln in user.splitlines()), user
    assert "轴" not in user, "`topics` 退役后不该再有 `轴 …` 那一格"
