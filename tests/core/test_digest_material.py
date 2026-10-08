# -*- coding: utf-8 -*-
"""`core/digest/material.py` 的**引擎侧**判据（P2, 2026-10-07）。

这里测的不是"她写了什么", 而是"引擎摆了什么"—— 两件都是**纯计算**（零 LLM）:
L1 的「现有经历（候选）」（按 `topics` 相交摆）与「候选对象」（≤5 个真 id + 命中提示）。
端到端那两条在 `test_wiki_digest.py`（`test_l1_akin_reaches_an_older_episode` 等）;
这里钉的是**挑法与上限**这类单看料才看得出的性质。
"""
from core.brain import WikiStoreV2, make_node
from core.brain.entities import ensure_entities, object_lines
from core.digest.material import DIGEST_RELATE_CAND_K, _axes_field, _episode_candidates


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",), sensei_name="老师")
    st.save()
    return st


def _ep(st, text, *, title="", topics=(), ts=""):
    return st.add(make_node("episode", text=text, title=title, topics=list(topics),
                            ts=ts, event_seq=[3]))


def test_episode_candidates_pick_by_shared_topics(tmp_path):
    """候选 = **`topics` 有交集**的旧经历; 排序按交集大小; 上限吃 `CAND_K`。

    ⭐ 判据与 `akin` 的校验**同源**（`on` ∈ 两端交集）—— 引擎不判"像不像", 它只摆
    "过得了校验的两端"。共享 2 个轴的排在共享 1 个的前面。
    """
    st = _store(tmp_path)
    old_two = _ep(st, "同两个轴", title="两条轴", topics=["苔藓", "天台"], ts="2026-09-01T10:00:00")
    old_one = _ep(st, "同一个轴", title="一条轴", topics=["苔藓"], ts="2026-09-05T10:00:00")
    _ep(st, "无关的那条", title="无关", topics=["甜品"], ts="2026-09-06T10:00:00")
    new = _ep(st, "这次又说苔藓", title="又说苔藓", topics=["苔藓", "天台"],
              ts="2026-09-09T10:00:00")
    st.save()

    text, ids = _episode_candidates(st, [new], now="2026-09-10T10:00:00")

    assert ids == [old_two, old_one], ids                       # 交集多的在前; 无关的不进
    assert "轴 苔藓·天台" in text                                # 印的是**交集**
    assert "无关" not in text                                   # 没有共同轴 ⇒ 不摆
    # ⭐ 时间两格（相对 + 日期）也在 —— 契约那句"时间上接着的不算同类"要她判得出来
    assert "1 周前" in text and "9/1" in text, text

    # 新的那条**自己没有轴** ⇒ 摆不出候选（交集恒空）—— 那也是结论, 不硬凑。
    # ⚠️ **P6（2026-10-08）**: 摆不出时**不是空串** —— 空串会被 `_join_sections` 的
    # `if body` 连抬头一起吞掉, 她看不见这个结论。而且两种"空"是**两件事**:
    # "本段没标轴"（没法比）≠ "没有一条同轴"（比过了, 真没有）。
    bare = _ep(st, "没有轴的一条", title="没轴", ts="2026-09-09T10:00:00")
    lonely = _ep(st, "谁都不认识的轴", title="沙漠", topics=["沙漠"], ts="2026-09-09T10:00:00")
    st.save()
    text_bare, ids_bare = _episode_candidates(st, [bare], now="")
    assert ids_bare == []
    assert text_bare == "（无 —— 本段经历没有标轴, 无法比对）", text_bare
    text_lone, ids_lone = _episode_candidates(st, [lonely], now="")
    assert ids_lone == []
    assert text_lone == "（无 —— 已有的经历里没有一条与本段同轴）", text_lone

    # 上限: 交集数一样时按 ts 新的在前, 且最多 `DIGEST_RELATE_CAND_K` 条
    st2 = _store(tmp_path / "b")
    for i in range(DIGEST_RELATE_CAND_K + 3):
        _ep(st2, f"旧事 {i}", title=f"旧事{i}", topics=["苔藓"],
            ts=f"2026-09-{i + 1:02d}T10:00:00")
    new2 = _ep(st2, "又来", title="又来", topics=["苔藓"], ts="2026-09-20T10:00:00")
    st2.save()
    _text2, ids2 = _episode_candidates(st2, [new2], now="2026-09-21T10:00:00")
    assert len(ids2) == DIGEST_RELATE_CAND_K, ids2
    assert ids2[0].endswith("0009"), f"ts 新的要排前面: {ids2}"


def test_object_lines_prints_real_ids_and_hit_hint(tmp_path):
    """对象候选 = **真实 id**（`x…`）+ 名字与别名 + 一行**字面命中**（引擎摆事实）。

    ⚠️ 与 R3 的 `candidate_table` **不共用**: 那边是本地号 `c0001`（执行侧要翻译）,
    L1 的契约印真身（设计 §9.1 的例子就是 `"about": "x0001"`）。
    """
    st = _store(tmp_path)

    text, ids = object_lines(st, texts=["今天老师说他会早点来"])
    assert ids == ["x0000", "x0001"], ids                     # 两个保留号, id 升序
    assert "x0001 老师" in text and "x0000 伊草 遥香（遥香）" in text
    assert "→ 候选: x0001（老师）（本段文本里出现了这个称呼）" in text
    assert "c0001" not in text, "L1 不印本地号（那是 R3 的）"

    # 一个都没提到 ⇒ 只有表, 没有命中那一行
    text2, _ids2 = object_lines(st, texts=["今天天气不错"])
    assert "→ 候选" not in text2
    # 空库 ⇒ 空串（调用方据此不注入这一段）
    from core.brain import WikiStoreV2 as S
    empty = S(tmp_path / "b", world_id="world1", char_id="c")
    assert object_lines(empty) == ("", [])


def test_axes_field_uses_the_parallel_mark_not_the_field_sep():
    """`轴` 一格用 `·` 并列 —— ⛔ 不能用 `｜`（那是信息头的字段分隔, 会把格子切坏）。"""
    from core.brain import marks

    assert _axes_field(["苔藓", "天台"]) == ["轴 苔藓·天台"]
    assert marks.FIELD_SEP not in _axes_field(["苔藓", "天台"])[0]
    assert _axes_field([]) == [] and _axes_field(None) == []
    assert _axes_field(["  ", ""]) == [], "空词不占格"
