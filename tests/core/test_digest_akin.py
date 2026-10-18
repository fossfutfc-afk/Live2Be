"""⭐ N5c 端到端 —— 想起的账 → `akin` 边（2026-09-29）。

链路全貌（三件套）::

    MMT 那一刻（N5b）: 她写 {"noticed": "瓦片缝里的苔藓"} → `noticed` 事件 {title, hit}
    L1 这一段（N5c）  : 找到"她说话那一刻属于哪条新 episode" → akin{新 → 她指的}

判据（`TODO.md` N5c）: 同一条发现跑两次只出一条边（幂等）· 未认领可 grep。

⚠️ 归属判据 = "该账**之前**、最近的、被某条 episode 认领的内容事件" ——
所以本文件里最要紧的一条是 `test_akin_depends_on_account_after_speech`
（账写在话**之后** ⇒ 归属落回本轮; 写在之前就会落到上一轮）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from core.brain import WikiStoreV2, make_node
from core.digest.pipeline import digest_segment
from core.session.events import make_event
from llm import task_labels as T
from tests import stub_tasks

CLOSE_EMPTY = {"add": [], "close": []}


class FakeLLM:
    """按序吐 A/B; R4（close）与 R3（attr）短路成空包。"""

    def __init__(self, *responses):
        self.responses = list(responses)

    def chat(self, messages, **kw):
        task = kw.get("task")
        if task == T.DIGEST_SPLIT:
            # ⭐ R0: 照搬 R1 那份应答里的区间（**不进位置队列** —— 它是照着剧本念的一轮）
            return stub_tasks.split_for_scripted(messages, self.responses[0]
                                                 if self.responses else [])
            return CLOSE_EMPTY
        if task == T.DIGEST_SETTLE:
            return {"entities": []}
        if self.responses:
            return self.responses.pop(0)
        raise RuntimeError("responses 耗尽")


B_EMPTY = {"relations": []}


def _b_cover(episode="m0002"):
    """L1 的**最小合法**应答 —— "什么关系都没看出来"（✅ 合法答案）。

    ⚠️ **P1b-2（2026-10-07）**: 从前这里是 R2 的决策表, 而且必须**逐条覆盖**每条新
    episode（`parse_round_b` 的 `missing` 检查, 漏一条拒整包）—— L1 **没有**这条要求
    （"这条跟谁都没关系"本身就是结论）。`episode=` 留着只为让老调用点读得通。
    """
    return {"relations": []}


def _events(*items):
    """合成事件流: `(type, subtype, payload, seq)` 元组, 或已经造好的 `Event`。"""
    out = []
    for it in items:
        if isinstance(it, tuple):
            typ, sub, payload, seq = it
            e = make_event(typ, sub, payload)
            e.seq = seq
        else:
            e = it
        out.append(e)
    return out


def _mmt(seq, player, reply):
    return ("mmt", "chat", {"player": player, "reply": reply}, seq)


def _noticed(seq, title, hit, ts=""):
    e = make_event("noticed", "noticed", {"title": title, "hit": hit})
    e.seq = seq
    if ts:
        e.ts = ts
    return e


def _old_episode(tmp_path, title="瓦片缝里的苔藓", seq=1) -> WikiStoreV2:
    """库里先有一条旧 episode（她当年记下的那件事）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", text="我把秘密基地告诉了老师", title=title,
                     event_seq=[seq], ts="2026-09-26T10:00:00", significance=0.7))
    return st


def _a_claims(*seqs, title="今天的杂草屋", text="又去看了那盆苔藓"):
    """Round A 的应答: 一条 episode 认领给定的 seq（用 span 区间，N3 形状）。"""
    return {"episodes": [{"text": text, "title": title, "span": [min(seqs), max(seqs)],
                          "tags": ["苔藓"], "significance": 0.6}]}


def _akin(st: WikiStoreV2) -> list[tuple[str, str]]:
    """`akin` 边（**按对看** —— `akin` 对称, 存进去时被 `canonical_for` 归一了顺序,
    所以"新→旧"的方向**不体现在边表里**, 只在台账里）。"""
    return [tuple(sorted((e.src, e.dst))) for e in st.edges() if e.rel == "akin"]


# ---------------------------------------------------------------------------
# 命中 → 落边
# ---------------------------------------------------------------------------

def test_akin_edge_lands(tmp_path):
    """账 + 本段的新 episode ⇒ 一条 `akin`（新 ↔ 她指的）。"""
    st = _old_episode(tmp_path)                       # m0001
    llm = FakeLLM(_a_claims(3, 4), _b_cover())
    events = _events(_mmt(3, "老师", "我今天又去看了看那片苔藓"),
                     _mmt(4, "老师", "嗯，它还好吗"),
                     _noticed(5, "瓦片缝里的苔藓", "m0001"))
    res = digest_segment(st, llm, events)
    assert res.ok, res.errors
    assert res.created == ["m0002"]
    assert _akin(st) == [("m0001", "m0002")], _akin(st)
    print("    N5c: 想起的账 → akin{新 m0002 ↔ 旧 m0001}")


def test_akin_is_idempotent(tmp_path):
    """⭐ 同一条发现跑两次**只出一条边**（`add_edge` 同 (rel,src,dst) 跳过）。"""
    st = _old_episode(tmp_path)
    events = _events(_mmt(3, "老师", "又去看了苔藓"),
                     _noticed(4, "瓦片缝里的苔藓", "m0001"))
    digest_segment(st, FakeLLM(_a_claims(3), _b_cover()), events)
    assert len(_akin(st)) == 1
    # 重跑同一段（水位回退 = 崩溃窗口重跑的形状）—— Round A 会**去重命中** m0002
    st.meta["digested_seq"] = 0
    st.save_meta()
    res = digest_segment(st, FakeLLM(_a_claims(3), _b_cover()), events)
    assert res.ok, res.errors
    assert res.created == ["m0002"], res.created          # 去重命中（没双写）
    assert len(_akin(st)) == 1, _akin(st)
    print("    N5c: 重跑只出一条边（幂等）")


def test_akin_is_canonical_for_symmetric_rel(tmp_path):
    """`akin` 对称 ⇒ 反向写也是同一条（N1a 的 `canonical_for` 在这里生效）。"""
    st = _old_episode(tmp_path)
    events = _events(_mmt(3, "老师", "又去看了苔藓"),
                     _noticed(4, "瓦片缝里的苔藓", "m0001"))
    digest_segment(st, FakeLLM(_a_claims(3), _b_cover()), events)
    before = len(_akin(st))
    st.add_edge("akin", "m0001", "m0002")             # 反着再写一遍
    assert len(_akin(st)) == before == 1, _akin(st)
    print("    N5c: 对称边反着写不新增")


# ---------------------------------------------------------------------------
# 归属（本文件最重要的一条）
# ---------------------------------------------------------------------------

def test_akin_depends_on_account_after_speech(tmp_path):
    """⭐⭐ 账写在**话之后** ⇒ 归属落回**本轮**; 写在话之前 ⇒ 会落到上一轮。

    这就是 N5b 那条"落账时机"（`engine._log_notices` 在 `_finish_turn_lines` 里调）
    的下游意义 —— 它是**静默错归属**的唯一防线, 所以在这儿钉一条反证。
    """
    st = _old_episode(tmp_path)
    # 段里两轮: seq 3 是**上一轮**的话, seq 4 是本轮的话; 账落在 5（本轮之后）
    events = _events(_mmt(3, "老师", "今天天气不错"),
                     _mmt(4, "老师", "我又去看苔藓了"),
                     _noticed(5, "瓦片缝里的苔藓", "m0001"))
    # Round A 只认领 seq 4（= 本轮那段话）—— 若归属取错了就会连不到
    digest_segment(st, FakeLLM(_a_claims(4), _b_cover()), events)
    assert _akin(st) == [("m0001", "m0002")], _akin(st)

    # 反证: 账落在**本轮话之前**（seq 3.5 ⇒ 用 3）→ 归属落到"已被认领的最近前一条"
    st2 = _old_episode(tmp_path / "b")
    events2 = _events(_mmt(3, "老师", "今天天气不错"),
                      _mmt(4, "老师", "我又去看苔藓了"),
                      _noticed(3, "瓦片缝里的苔藓", "m0001"))   # 早于本轮的话
    digest_segment(st2, FakeLLM(_a_claims(4), _b_cover()), events2)
    assert _akin(st2) == [], "账早于所有被认领的内容 ⇒ 未认领（不猜）"
    print("    N5c: 归属按「账之前最近的有主内容」；账太早 ⇒ 未认领")


# ---------------------------------------------------------------------------
# 未认领 / 跳过
# ---------------------------------------------------------------------------

def test_akin_unclaimed_when_no_episode_claimed_it(tmp_path):
    """本段没产出 episode（Round A 空）⇒ **不落边**（待裁 #7: 先丢 + 让台账说话）。"""
    st = _old_episode(tmp_path)
    events = _events(_mmt(3, "老师", "在吗"),
                     _noticed(4, "瓦片缝里的苔藓", "m0001"))
    digest_segment(st, FakeLLM({"episodes": []}, _b_cover()), events)
    assert _akin(st) == []
    print("    N5c: 没产出 episode ⇒ 未认领（不落边）")


def test_akin_skips_missing_target(tmp_path):
    """她指的那条不在库里（旧档 / 被清）⇒ 跳过, 不抛（宁缺勿错）。"""
    st = _old_episode(tmp_path)
    events = _events(_mmt(3, "老师", "又去看了苔藓"),
                     _noticed(4, "早就没有的那条", "m0099"))
    res = digest_segment(st, FakeLLM(_a_claims(3), _b_cover()), events)
    assert res.ok and _akin(st) == []
    print("    N5c: 目标不存在 ⇒ 跳过（不抛）")


def test_akin_skips_self_edge(tmp_path):
    """本段那条 episode 就是她指的那条 ⇒ 不写自环（单测守卫: 真机上很罕见但可达）。"""
    from core.digest.rounds.akin import _link_akin
    st = _old_episode(tmp_path)
    e = _noticed(4, "瓦片缝里的苔藓", "m0001")
    edges, lost, self_skip = _link_akin(st, ["m0001"], [e], ts="2026-10-01T10:00:00")
    assert (edges, lost, self_skip) == (0, 0, 1)
    assert _akin(st) == []
    print("    N5c: 本段就是她指的那条 ⇒ 不写自环")


def test_no_noticed_no_edges(tmp_path):
    """没有账 ⇒ 一条边都不写（旧行为逐字节不变）。"""
    st = _old_episode(tmp_path)
    events = _events(_mmt(3, "老师", "又去看了苔藓"))
    digest_segment(st, FakeLLM(_a_claims(3), _b_cover()), events)
    assert _akin(st) == []
    print("    N5c: 没账 ⇒ 零影响")
