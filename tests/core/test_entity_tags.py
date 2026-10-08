# -*- coding: utf-8 -*-
"""E1（2026-10-08）—— `#entity:<名字>`：**她写的 tag → 引擎落的边**。

钉五件事:
    ① **语法分栏**: `#entity:` 不占检索词的 1~4 个额度; 空名字 ⇒ 丢项 + 记账;
    ② **名字解析**（`entities.find_entity`）: `name` + `aliases` + 大小写都认;
       命中 0 / 多条 ⇒ **不猜**（与 `address.find_episode` 同一套纪律）;
    ③ ⭐ **归一 + 落边**: `#entity:sensei` ⇒ 节点上是 `#entity:老师`（主名）+
       `about(m0001 → x0001)` 真的落了（**边由引擎派生, 零 LLM**）;
    ④ ⭐ **陌生人**: `#entity:小玉`（库里没有）⇒ tag **原样留着** + 报上去 + ⛔ **不落边**
       （那正是"认人"那一轮的线索 —— 她本来没有语法说"这条关于一个我还不知道的人"）;
    ⑤ **契约文案**: 渲出来的 `record` schema 与示例里都有它（示例才是形状的来源）。

⛔ 本文件只测 E1 的三面（契约分栏 / 引擎解析 / 落边），不测 R3 认人（那是 E4）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from contract.digest_registry import (ENTITY_TAG_PREFIX, ENTITY_TAGS_MAX,
                                      MAX_TAGS, PHASE_RECORD, _split_tags,
                                      digest_registry)
from core.brain import WikiStoreV2, make_node
from core.brain.entities import (ensure_entities, find_entity,
                                 normalize_entity_tags, surface_forms)
from core.digest.episodes import _create_a_nodes

CHAR = "c"


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",),
                    sensei_name="老师", sensei_aliases=("sensei",))
    st.save()
    return st


def _ep(text, title, tags):
    return {"text": text, "title": title, "tags": tags, "significance": 0.5}


# ---------------------------------------------------------------------------
# ① 语法分栏（契约层, 纯字符串）
# ---------------------------------------------------------------------------

def test_entity_tag_does_not_eat_the_search_word_quota():
    """⭐ `#entity:` **不占** 1~4 个检索词的额度（`#` 开头 = 标记, 不是词）。"""
    warnings: list[str] = []
    drops: list[str] = []
    words, marks = _split_tags(["公园", "流浪猫", "热茶", "长椅", "#entity:老师"],
                               0, warnings, drops)
    assert words == ["公园", "流浪猫", "热茶", "长椅"], words      # 4 个检索词**全收**
    assert marks == [f"{ENTITY_TAG_PREFIX}老师"], marks
    assert warnings == [] and drops == [], (warnings, drops)


def test_over_quota_is_trimmed_and_said_out_loud():
    """两栏各自的上限**都**要看得见（不静默截断）。"""
    warnings: list[str] = []
    words, marks = _split_tags(["a1", "a2", "a3", "a4", "a5",
                                "#entity:x1", "#entity:x2", "#entity:x3"],
                               3, warnings, [])
    assert words == ["a1", "a2", "a3", "a4"], words               # MAX_TAGS = 4
    assert len(marks) == ENTITY_TAGS_MAX, marks
    assert any("检索词" in w for w in warnings), warnings
    assert any("#entity:" in w for w in warnings), warnings


def test_empty_entity_tag_is_dropped_not_kept():
    """`#entity:` 后面没名字 ⇒ **丢那一项** + 记账（没有名字就没有对象可指）。"""
    drops: list[str] = []
    words, marks = _split_tags(["公园", ENTITY_TAG_PREFIX, f"{ENTITY_TAG_PREFIX}   "],
                               7, [], drops)
    assert words == ["公园"] and marks == [], (words, marks)
    assert len(drops) == 2, drops


def test_contract_text_and_example_carry_the_syntax():
    """⭐ **示例才是形状的来源** —— 契约正文与示例都必须有 `#entity:`。"""
    text = digest_registry.build_schema(PHASE_RECORD)
    assert ENTITY_TAG_PREFIX in text, "契约正文里没有 `#entity:` 那一行"
    assert f'"{ENTITY_TAG_PREFIX}老师"' in text, "示例里没有 `#entity:老师`（她只照抄示例）"
    assert "不占" in text, "没写清它不占检索词额度"


# ---------------------------------------------------------------------------
# ② 名字解析（`find_entity`）
# ---------------------------------------------------------------------------

def test_find_entity_accepts_name_aliases_and_case(tmp_path):
    st = _store(tmp_path)
    for raw, want in (("老师", "x0001"), ("sensei", "x0001"), ("SENSEI", "x0001"),
                      (" 老师 ", "x0001"), ("遥香", "x0000"), ("伊草 遥香", "x0000")):
        node, reason = find_entity(st, raw)
        assert node is not None and node.id == want, (raw, reason)
    print(f"    解析: {surface_forms(st.get('x0001'))} 的各种写法都命中")


def test_find_entity_never_guesses(tmp_path):
    """命中 0 / 多条 / 空 ⇒ **不猜**（与 `address` 同一套三条纪律）。"""
    st = _store(tmp_path)
    assert find_entity(st, "小玉") == (None, "miss")
    assert find_entity(st, "") == (None, "empty")
    st.add(make_node("entity", name="老师", aliases=[], ts="2026-10-08T10:00:00+08:00"))
    st.save()
    assert find_entity(st, "老师") == (None, "ambiguous")


# ---------------------------------------------------------------------------
# ③④ 归一 + 落边（执行层）
# ---------------------------------------------------------------------------

def test_tag_lands_as_an_about_edge_and_normalizes_to_the_main_name(tmp_path):
    """⭐ 她写 `#entity:sensei` ⇒ 节点上是主名, 图上多一条 `about` 边。"""
    st = _store(tmp_path)
    out: list[str] = []
    ids, _players = _create_a_nodes(
        st, [_ep("老师约我去公园", "和老师的公园散步", ["公园", "#entity:sensei"])],
        ts="2026-10-08T21:00:00+08:00", event_seq=[3], strangers_out=out)
    ep = st.get(ids[0])
    assert f"{ENTITY_TAG_PREFIX}老师" in ep.tags, ep.tags          # 归一成主名
    assert "#entity:sensei" not in ep.tags, ep.tags
    assert ep.tags[:1] == ["公园"], "检索词要排在前面（`#entity:` 在后）"
    assert st.graph().targets(ep.id, "about") == ["x0001"], "边没落上"
    assert out == [], out
    print(f"    {ep.id} → about → x0001（tag 归一成 `#entity:老师`）")


def test_stranger_tag_stays_and_leaves_no_dangling_edge(tmp_path):
    """⭐ 陌生人: tag **原样留着** · **不落边** · 名字报上去（认人那一轮的线索）。"""
    st = _store(tmp_path)
    out: list[str] = []
    ids, _players = _create_a_nodes(
        st, [_ep("第一次见到小玉", "转角的相遇", ["公园", "#entity:小玉"])],
        ts="2026-10-08T21:00:00+08:00", event_seq=[3], strangers_out=out)
    ep = st.get(ids[0])
    assert f"{ENTITY_TAG_PREFIX}小玉" in ep.tags, ep.tags          # 原样（不丢）
    assert st.graph().targets(ep.id, "about") == [], "陌生人**不该**落边（会悬空）"
    assert out == ["小玉"], out
    assert list(st.edges()) == [], "图上一条新边都不该有"
    print(f"    陌生人: tag 留着 · 0 条边 · 报账 {out}")


def test_profile_entries_can_carry_entity_tags_too(tmp_path):
    """画像条目（`kind=profile`）走同一套语法 —— 同一件事不留两个写法。"""
    st = _store(tmp_path)
    _eps, player_ids = _create_a_nodes(
        st, [{"kind": "profile", "text": "老师总忘带伞", "tags": ["雨天", "#entity:老师"],
              "significance": 0.6}],
        ts="2026-10-08T21:00:00+08:00", event_seq=[3], strangers_out=[])
    pf = st.get(player_ids[0])
    assert pf.kind == "profile" and f"{ENTITY_TAG_PREFIX}老师" in pf.tags, pf.tags
    assert st.graph().targets(pf.id, "about") == ["x0001"]
    print(f"    画像条目也认: {pf.id} → about → x0001")


def test_plain_tags_are_untouched(tmp_path):
    """没有 `#entity:` 的节点**一个字都不变**（这是加法）。"""
    st = _store(tmp_path)
    ids, _players = _create_a_nodes(
        st, [_ep("一个人在屋顶", "屋顶", ["屋顶", "傍晚"])],
        ts="2026-10-08T21:00:00+08:00", event_seq=[3], strangers_out=[])
    assert st.get(ids[0]).tags == ["屋顶", "傍晚"]
    assert list(st.edges()) == []
    assert MAX_TAGS == 4, "`MAX_TAGS` 是既有约定, E1 不该动它"


def test_normalize_dedupes_the_same_person_written_two_ways(tmp_path):
    """她写了两种叫法 ⇒ 归一后**只留一条**（去重**保序**）, 边也只有一条。

    ⚠️ 分工: **保序是这一层的语义**（它只做"把叫法换成主名"）——
    "检索词排在 `#entity:` 前面"是**契约层**（`_split_tags` 的 `tags + ent_tags`）的事。
    """
    st = _store(tmp_path)
    tags, targets, strangers = normalize_entity_tags(
        st, ["#entity:sensei", "公园", "#entity:老师"])
    assert tags == [f"{ENTITY_TAG_PREFIX}老师", "公园"], tags
    assert targets == ["x0001"] and strangers == [], (targets, strangers)
