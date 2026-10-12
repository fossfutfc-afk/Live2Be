"""D0 —— **段的推进规则**（2026-09-29 用户裁决）。

> 用户原话：*"固定每个角色说 40 轮（1/3 个 window）开始 digest 以及章闭环即可；
> 下一段的 slice start = 上一段中 slice 出的所有段中 span 右端点的最大值 + 1"*
> · 补一句裁决：**只救尾巴**（中间空洞不重喂 —— 那些多是闲聊）。

四条判据:

  ① **触发** = MMT 每 `MMT_DIGEST_INTERVAL`(=40) 轮 或 章闭环（40 ≈ 1/3 个
     `window_messages(max_units=120)`）。
  ② ⭐ **水位 = 她这次实际覆盖到的最大 seq**（不是触发点）⇒ 没覆盖的**尾巴**留在水位
     之上, 并进下一段**再喂一次**（"未认领"从"永久丢"变成"欠着"）。
  ③ ⭐ **章块的覆盖由引擎兜到整章**（`segment._collapse_bond_episodes` 的并集）——
     这是 ② 的必要配套: 章的 episode 划窄了会让章尾被重喂, 而重喂的窗口里没有
     `vn_enter` ⇒ 会被当成**孤儿章** ⇒ 可能重复记一条。
  ④ 两条兜底: **零覆盖 ⇒ 推到窗口上界**（否则死循环）· **窗口超限 ⇒ 丢最老的**
     （否则窗口单调变长）。

运行: python -m pytest tests/core/test_digest_window.py
"""
import sys
from pathlib import Path


from core.brain import WikiStoreV2
from core.brain.entities import ensure_entities
from core.digest import pipeline
from core.digest.pipeline import digest_segment
from core.session import make_event
from llm import task_labels as T
from tests import stub_tasks

CHAR = "c"


class Stub:
    """按 task 分派: R1 给 `episodes`（可带 span）, 其余轮空包。

    ⚠️ R2 的契约要求"覆盖全部 episode"（漏一条整包拒）⇒ 决策行按**实际** id 生成
    （从 user 消息里认 `〔m0001｜《标题》〕`）—— 不能写死 `m0001`。
    """

    def __init__(self, episodes):
        self.episodes = episodes
        self.users: list[str] = []
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.tasks.append(task)
        user = str(messages[-1].get("content", ""))
        self.users.append(user)
        if task == T.DIGEST_SPLIT:            # ⭐ R0: 照搬 R1 那份应答里的区间
            return stub_tasks.split_for_scripted(messages, self.episodes)
        if task == T.DIGEST_RECORD:
            return {"episodes": self.episodes}
        if task in (T.DIGEST_RELATE, T.DIGEST):
            return {"relations": []}          # L1: 料照收, 一行关系都不判
        if task == T.DIGEST_ATTRIBUTE:
            return {"attributions": []}
        if task == T.DIGEST_COGNIZE:      # L2-b（P10）: 不测它 ⇒ 空包
            return {"cognitions": []}
        raise RuntimeError(f"意外调用 task={task!r}")


def _wiki(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    ensure_entities(st, char_name="伊草 遥香", sensei_name="老师")
    st.save()
    return st


def _mmt(seq: int, text: str = ""):
    e = make_event("mmt", "mmt_chat", {"player": "老师", "reply": text or f"第 {seq} 句"})
    e.seq = seq
    return e


def _events(*seqs):
    return [_mmt(s) for s in seqs]


# ---------------------------------------------------------------------------
# ② 水位 = 她覆盖到的地方（不是触发点）
# ---------------------------------------------------------------------------

def test_watermark_stops_at_her_coverage(tmp_path):
    """⭐ 她只覆盖 1–2 而窗口有 4 条 ⇒ 水位停在 **2**（不是 4）⇒ 3、4 欠到下一段。"""
    st = _wiki(tmp_path)
    llm = Stub([{"text": "只记了前两句", "title": "前两句", "span": [1, 2],
                 "tags": ["x"]}])
    res = digest_segment(st, llm, _events(1, 2, 3, 4))

    assert res.ok, res.errors
    assert st.digested_seq == 2, f"水位该停在她覆盖到的地方: {st.digested_seq}"
    # 下一段的窗口**从 3 起**（欠着的尾巴并进来）
    llm2 = Stub([{"text": "这回记 3、4", "title": "后半", "span": [3, 4],
                  "tags": ["x"]}])
    res2 = digest_segment(st, llm2, _events(1, 2, 3, 4))
    assert res2.ok, res2.errors
    assert st.digested_seq == 4
    user2 = llm2.users[0]
    assert "[3]" in user2 and "[4]" in user2, "尾巴该被重喂"
    assert "[1]" not in user2.split("【")[1] if "【" in user2 else True
    print(f"    覆盖率决定水位: 2 → 4（尾巴 3、4 被重喂）✓")


def test_watermark_swallows_trailing_non_content_events(tmp_path):
    """覆盖点**之后紧邻**的 marker / 账目一起吞掉（它们本来就属于这一段）。"""
    st = _wiki(tmp_path)
    evs = _events(1, 2)
    aff = make_event("affection", "digest", {"delta": 1, "digested_seq": 2})
    aff.seq = 3
    evs.append(aff)
    llm = Stub([{"text": "两句都记", "title": "两句", "span": [1, 2], "tags": ["x"]}])
    res = digest_segment(st, llm, evs)

    assert res.ok, res.errors
    assert st.digested_seq == 3, f"尾部账目该一起吞掉: {st.digested_seq}"
    print("    尾部非内容事件一起吞 ✓")


def test_watermark_advances_when_nothing_is_covered(tmp_path):
    """⭐ 兜底: 零覆盖（MMT 碎聊允许 0 条）⇒ 推到**窗口上界**, 否则水位永远不动。"""
    st = _wiki(tmp_path)
    res = digest_segment(st, Stub([]), _events(1, 2, 3))

    assert res.ok, res.errors
    assert st.digested_seq == 3, f"零覆盖必须推进（否则死循环）: {st.digested_seq}"
    print("    零覆盖 ⇒ 推到窗口上界 ✓")


def test_middle_hole_is_not_re_fed(tmp_path):
    """⛔ **只救尾巴**: 她记了 1–2 与 5–6, 而 3、4 空着 ⇒ 水位一次推过 6, 3、4 不重喂。"""
    st = _wiki(tmp_path)
    llm = Stub([{"text": "头和尾", "title": "头和尾", "span": [1, 2], "tags": ["x"]},
                {"text": "又一件事", "title": "又一件事", "span": [5, 6],
                 "tags": ["x"]}])
    res = digest_segment(st, llm, _events(1, 2, 3, 4, 5, 6))

    assert res.ok, res.errors
    assert st.digested_seq == 6, st.digested_seq
    llm2 = Stub([])
    res2 = digest_segment(st, llm2, _events(1, 2, 3, 4, 5, 6))
    assert res2.ok and res2.llm_calls == 0, "没有新事件 ⇒ 一次调用都不该发"
    print("    中间空洞不重喂（只救尾巴）✓")


# ---------------------------------------------------------------------------
# ③ 章块的覆盖由引擎兜到整章（② 的必要配套）
# ---------------------------------------------------------------------------

def _chapter(enter=10, bonds=(11, 12, 13, 14), exit_=15, title="苔藓"):
    evs = []
    m = make_event("marker", "vn_enter", {"chapter_title": title})
    m.seq = enter
    evs.append(m)
    for s in bonds:
        b = make_event("bond", "story_scene", {"paragraphs": [{"text": f"第 {s} 句"}]})
        b.seq = s
        evs.append(b)
    x = make_event("marker", "vn_exit", {"completed": True})
    x.seq = exit_
    evs.append(x)
    return evs


def test_collapse_keeps_one_slice_per_chapter():
    """⭐ 3b-1: **一章切成几件** ⇒ 收口留一件（`state=open` 优先, 否则跨度最长）。

    ⚠️ 收口吃的是 **R0 的切片**（切分权归切分员 ⇒ "一章切成几件"是切分违约）;
    判据也从 `significance` 换成 `state=open` / 跨度 —— R0 **不打分**（打分是 R1 的活）。

    这条用例是**直接单测那个函数**（不跑管线）: 它才是 3b-1 真正新写的判定,
    而管线级的用例会被桩的应答队列纠缠（一次反馈重试就吃掉一条应答, 表现成
    "少了半段料", 与收口无关）。
    """
    from core.digest.segment import _collapse_bond_episodes

    dropped: list[dict] = []
    segs = [
        {"span": [4, 4], "abstract": "甲", "seqs": [4]},
        {"span": [5, 5], "state": "open", "abstract": "乙", "seqs": [5]},
        {"span": [6, 6], "abstract": "丙", "seqs": [6]},
    ]
    chapters = [{"title": "苔藓", "seqs": frozenset({4, 5, 6})}]
    out = _collapse_bond_episodes(segs, chapters, dropped_out=dropped)

    assert [s["abstract"] for s in out] == ["乙"], "一章一件（state=open 优先）"
    assert dropped[0]["chapter"] == "苔藓"
    assert dropped[0]["lost"] == ["甲", "丙"]
    # ⭐ **区间并回**: 保留那条的覆盖 = 整章（含被丢那两条的 [4,4] / [6,6]）
    assert out[0]["seqs"] == [4, 5, 6], out[0]["seqs"]
    # ⚠️ 章**外**的切片一条都不动（聊天那些不属于这一章, 不能被一起压掉）
    outside = [{"span": [1, 2], "abstract": "聊天", "seqs": [1, 2]}]
    out2 = _collapse_bond_episodes(outside + segs, chapters)
    assert sorted(s["abstract"] for s in out2) == ["乙", "聊天"], out2
    print("    收口: 一章一件（open 优先）+ 区间并回 + 章外不动 ✓")


def test_collapse_prefers_the_widest_when_no_open():
    """没有 `state=open` 时按**跨度**取（`span` 的宽度, 不是"覆盖了多少 seq"）。"""
    from core.digest.segment import _collapse_bond_episodes

    segs = [{"span": [4, 4], "abstract": "窄", "seqs": [4]},
            {"span": [4, 6], "abstract": "宽", "seqs": [4, 5, 6]}]
    out = _collapse_bond_episodes(segs, [{"title": "章", "seqs": frozenset({4, 5, 6})}])
    assert [s["abstract"] for s in out] == ["宽"], out
    print("    收口: 没 open 时留跨度最长的那条 ✓")


def test_collapse_never_drops_a_ledger_row():
    """⭐ **账目行不参与收口**（L4, 2026-10-05）—— 丢一条 `close` = 那条约定永远开着。

    ⚠️ 判据不是"哪条更该活", 是"哪条不许死": 一章切成几件时, 无账目的行照旧收口,
    带 `state` 的那些**整条留下**（一行只装得下一个 `state`/`id`, 并不过去）。
    """
    from core.digest.segment import _collapse_bond_episodes

    dropped: list[dict] = []
    segs = [{"span": [4, 4], "abstract": "甲", "seqs": [4]},
            {"span": [5, 5], "state": "close", "id": "n3", "abstract": "丁", "seqs": [5]},
            {"span": [6, 6], "abstract": "丙", "seqs": [6]}]
    chapters = [{"title": "苔藓", "seqs": frozenset({4, 5, 6})}]
    out = _collapse_bond_episodes(segs, chapters, dropped_out=dropped)

    kept = {s["abstract"]: s for s in out}
    assert "丁" in kept, f"close 那一行被收口丢了（账不平）: {out}"
    assert kept["丁"]["state"] == "close" and kept["丁"]["id"] == "n3", kept["丁"]
    # 无账目的那两条照旧收口（留第一条）, 而且**丢的账里没有丁**
    assert sorted(kept) == ["丁", "甲"], out
    assert dropped[0]["lost"] == ["丙"], dropped
    # 保留那条照样兜满整章（位置不因为收口而丢）
    assert kept["甲"]["seqs"] == [4, 5, 6], kept["甲"]["seqs"]
    print(f"    收口: 账目行留下 {kept['丁']['id']}, 无账目的照旧并成一条 ✓")


def test_collapse_keeps_two_open_rows_as_two_promises():
    """同一章里**两条 `open`** = 两条约定 —— 收口不许把其中一条吃掉。"""
    from core.digest.segment import _collapse_bond_episodes

    segs = [{"span": [4, 4], "state": "open", "abstract": "约了模型店", "seqs": [4]},
            {"span": [5, 5], "state": "open", "abstract": "约了看苔藓", "seqs": [5]}]
    out = _collapse_bond_episodes(segs, [{"title": "章", "seqs": frozenset({4, 5})}])
    assert sorted(s["abstract"] for s in out) == ["约了模型店", "约了看苔藓"], out
    print("    收口: 两条 open 都留着（两条约定）✓")


def test_null_span_row_claims_no_position_and_is_never_collapsed():
    """⭐ 无区间行（`span: null` = "没有那一刻"）**一个 seq 都不认领**, 也不被章收口吃掉。

    ⚠️ 它的 `event_seq`（L7 建节点时才落 `[interact_max]`）是**账的指针, 不是覆盖声明** ——
    在这里认领了, 日志就会说"这一段全被它记下了"。
    """
    from core.digest.segment import (_collapse_bond_episodes, _coverage, _expand_spans,
                                     _seqs_of)

    segs = [{"span": None, "state": "close", "id": "n3",
             "abstract": "生日那天, 老师没有来"}]
    unclaimed, shared = _expand_spans(segs, {4, 5, 6})
    assert "seqs" not in segs[0], "无区间行不许拿到 seqs"
    assert _seqs_of(segs[0]) == []
    assert unclaimed == [4, 5, 6] and shared == 0, (unclaimed, shared)
    # 章收口也吞不掉它（它不属于任何章 —— 没有位置）
    chapters = [{"title": "章", "seqs": frozenset({4, 5, 6})}]
    out = _collapse_bond_episodes(segs, chapters)
    assert [s["abstract"] for s in out] == ["生日那天, 老师没有来"], out
    # 覆盖账: 整章都还欠着（它是"没有那一刻", 不顶任何位置）
    assert _coverage(segs, {4, 5, 6}, chapters) == ([4, 5, 6], [4, 5, 6])
    print("    span:null: 不认领位置 / 不被收口 / 不算章内覆盖 ✓")


def test_chapter_tail_is_covered_by_the_engine(tmp_path):
    """⭐ 她只划了 11–12 而章是 11–14 ⇒ 节点的 `event_seq` = **整章**。"""
    st = _wiki(tmp_path)
    llm = Stub([{"text": "这一章的总结", "title": "苔藓", "span": [11, 12],
                 "tags": ["苔藓"]}])
    res = digest_segment(st, llm, _chapter())

    assert res.ok, res.errors
    node = st.get(res.created[0])
    assert node.event_seq == [11, 12, 13, 14], f"章块覆盖该由引擎兜满: {node.event_seq}"
    assert st.digested_seq == 15, "水位要能推过整章 + 章尾 marker"
    print(f"    章覆盖由引擎兜满: {node.event_seq}（水位 {st.digested_seq}）✓")


def test_chapter_cover_keeps_watermark_moving(tmp_path):
    """②+③ 合起来: 章若没兜满, 章尾会被重喂 ⇒ 重喂的窗口里没有 `vn_enter` ⇒ 孤儿章。"""
    st = _wiki(tmp_path)
    llm = Stub([{"text": "总结", "title": "苔藓", "span": [11, 12], "tags": ["苔藓"]}])
    digest_segment(st, llm, _chapter())
    llm2 = Stub([])
    res2 = digest_segment(st, llm2, _chapter())
    assert res2.llm_calls == 0, "章已整块消化 ⇒ 不该再有新事件可喂"
    print("    整章消化完 ⇒ 下一段没有欠账 ✓")


# ---------------------------------------------------------------------------
# ④ 窗口超限的保险丝
# ---------------------------------------------------------------------------

def test_window_cap_drops_the_oldest(tmp_path, monkeypatch):
    """⭐ 窗口超限 ⇒ 丢掉**最老的**未认领（只在"水位长期追不上"时才炸）。"""
    monkeypatch.setattr(pipeline, "DIGEST_WINDOW_EVENTS_CAP", 2)
    st = _wiki(tmp_path)
    llm = Stub([{"text": "只记最后两条", "title": "最后两条", "span": [3, 4],
                 "tags": ["x"]}])
    res = digest_segment(st, llm, _events(1, 2, 3, 4))

    assert res.ok, res.errors
    user = llm.users[0]
    assert "[1]" not in user and "[3]" in user, f"该丢掉最老的: {user[:200]}"
    assert st.digested_seq == 4
    print("    窗口超限: 丢最老的 1、2 ✓")


if __name__ == "__main__":
    import tempfile

    for fn in (test_watermark_stops_at_her_coverage,
               test_watermark_swallows_trailing_non_content_events,
               test_watermark_advances_when_nothing_is_covered,
               test_middle_hole_is_not_re_fed,
               test_chapter_tail_is_covered_by_the_engine,
               test_chapter_cover_keeps_watermark_moving):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("all digest window tests passed（窗口超限那条要 monkeypatch, 只在 pytest 下跑）")
