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


from contract.digest_registry import (ENTITY_TAG_PREFIX, ENTITY_TAGS_MAX,
                                      MAX_TAGS, PHASE_RECORD, _split_tags,
                                      digest_registry)
from core.brain import WikiStoreV2, make_node
from core.brain.entities import (ensure_entities, find_entity, hit_set,
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
                               warnings, drops, where="episodes[0]")
    assert words == ["公园", "流浪猫", "热茶", "长椅"], words      # 4 个检索词**全收**
    assert marks == [f"{ENTITY_TAG_PREFIX}老师"], marks
    assert warnings == [] and drops == [], (warnings, drops)


def test_over_quota_is_trimmed_and_said_out_loud():
    """两栏各自的上限**都**要看得见（不静默截断）。"""
    warnings: list[str] = []
    words, marks = _split_tags(["a1", "a2", "a3", "a4", "a5",
                                "#entity:x1", "#entity:x2", "#entity:x3"],
                               warnings, [], where="episodes[3]")
    assert words == ["a1", "a2", "a3", "a4"], words               # MAX_TAGS = 4
    assert len(marks) == ENTITY_TAGS_MAX, marks
    assert any("检索词" in w for w in warnings), warnings
    assert any("#entity:" in w for w in warnings), warnings


def test_empty_entity_tag_is_dropped_not_kept():
    """`#entity:` 后面没名字 ⇒ **丢那一项** + 记账（没有名字就没有对象可指）。"""
    drops: list[str] = []
    words, marks = _split_tags(["公园", ENTITY_TAG_PREFIX, f"{ENTITY_TAG_PREFIX}   "],
                               [], drops, where="episodes[7]")
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


def test_find_entity_ignores_whitespace(tmp_path):
    """⭐ **空白不敏感**（`entities.form_key`，2026-10-12）: `伊草遥香` ≡ `伊草 遥香`。

    为什么必须有（用户 2026-10-12: *"注意处理空格"*）: brain 段的「我知道的名字」
    **只印主名**，而卡上的主名中间就带一个空格（`伊草 遥香` / `陆八魔 阿露` / …）
    —— 她/他少打一个空格就 `miss`（`look` 会答"这个名字我对不上是谁"）。
    ⚠️ 归一 = **去所有空白**（含全角 U+3000）+ `casefold`; ⛔ 不是"近似匹配":
    多一个字、少一个字照旧 `miss`。
    """
    from core.brain.entities import form_key
    st = _store(tmp_path)
    aru = st.add(make_node("entity", name="陆八魔 阿露", aliases=["阿露"]))
    st.save()
    for raw in ("伊草遥香", "伊草  遥香", "伊草\t遥香", "伊草\u3000遥香", " 伊草遥香 "):
        node, reason = find_entity(st, raw)
        assert node is not None and node.id == "x0000", (raw, reason)
    for raw in ("陆八魔阿露", "陆八魔  阿露", "陆 八 魔 阿 露"):
        node, reason = find_entity(st, raw)
        assert node is not None and node.id == aru, (raw, reason)
    # ⛔ 归一不等于放宽: 多一个字还是 miss（那是"还没建的人", 不许猜）
    assert find_entity(st, "伊草 遥香香") == (None, "miss")
    assert form_key("伊草 遥香") == form_key("伊草遥香") == "伊草遥香"
    print("    解析: 空白不敏感（主名少打一个空格也命中）; 多字照旧 miss")


def test_hit_set_sees_a_name_written_without_the_space(tmp_path):
    """⭐ **正文扫描也走 `form_key`**（2026-10-12）: 名字带空格、正文不带 ⇒ 照样算"提到了他"。

    这条链是 **R3 的入口**（"这条经历挂谁" = `about` 边从 `hit_set` 来）—— 漏掉的后果是
    "这段明明写了她，那条却挂不上去"，而且**静默**（`hit_set` 只回 id 列表）。
    ⚠️ 长度按**归一后**算: `阿 `（带空白的单字）归一成单字 ⇒ 不扫（`MIN_HIT_LEN` 挡的
    正是"单字扫全文"）。
    """
    st = _store(tmp_path)
    assert st.get("x0000").name == "伊草 遥香"                 # 前提: 卡上主名带空格
    assert hit_set(st, texts=["今天伊草遥香来看杂草了"]) == ["x0000"]
    assert hit_set(st, texts=["伊草 遥香也来了"]) == ["x0000"]   # 正文带空格同样认
    assert hit_set(st, texts=["今天杂草很多"]) == []             # ⛔ 不是"谁都算"
    single = st.add(make_node("entity", name="阿", aliases=["阿 "]))
    st.save()
    assert single not in hit_set(st, texts=["阿今天来了"])        # ⛔ 归一后单字不扫
    print("    hit_set: 正文扫描空白不敏感（归一后短于 MIN_HIT_LEN 的不扫）")


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


# ---------------------------------------------------------------------------
# E2（2026-10-08）—— **看法也能带地址**: belief 的 `#entity:` ⇒ 归一 + 落边
# ---------------------------------------------------------------------------

def test_belief_can_carry_an_address_and_lands_an_edge(tmp_path):
    """⭐ E2: 看法带 `#entity:sensei` ⇒ 归一成主名 + 落 `about(belief → 对象)`。

    真机依据: belief 的 `subject` **实际用法已漂成"主题句"**（4/4 条解析不到 entity）
    ⇒ 它当不了地址; 这一格是看法的"关于谁"。
    """
    from core.brain.revise import apply_cognitions

    st = _store(tmp_path)
    res = apply_cognitions(st, [{"text": "老师会把我说的话记在心上",
                                 "subject": "老师对我的接纳",
                                 "tags": ["#entity:sensei"], "significance": 0.8}],
                           ts="2026-10-08T21:00:00+08:00", event_seq=[3])
    nid = res.created[0]
    node = st.get(nid)
    assert node.kind == "belief"
    assert node.tags == [f"{ENTITY_TAG_PREFIX}老师"], node.tags     # 归一成主名
    assert node.subject == "老师对我的接纳", "`subject`（主题句）原样留着, 两者分工"
    assert st.graph().targets(nid, "about") == ["x0001"], "看法 → 对象的边没落上"
    assert res.strangers == [], res.strangers
    print(f"    {nid} → about → x0001（`subject` 与地址各归各位）")


def test_belief_stranger_address_stays_and_is_reported(tmp_path):
    """看法指向还没建的人 ⇒ tag **原样留着** + 报上来 + ⛔ 不落边（不然会悬空）。"""
    from core.brain.revise import apply_cognitions

    st = _store(tmp_path)
    res = apply_cognitions(st, [{"text": "小玉好像不太喜欢说话",
                                 "tags": ["#entity:小玉"]}],
                           ts="2026-10-08T21:00:00+08:00", event_seq=[3])
    node = st.get(res.created[0])
    assert f"{ENTITY_TAG_PREFIX}小玉" in node.tags, node.tags
    assert st.graph().targets(node.id, "about") == []
    assert res.strangers == ["小玉"], res.strangers
    print(f"    陌生人: tag 留着 · 0 条边 · 报账 {res.strangers}")


def test_belief_contract_speaks_the_address_slot():
    """契约正文与示例都要有它, 并写清与 `subject` 的**分工**（不然她会写混）。"""
    from contract.digest_registry import PHASE_COGNIZE

    text = digest_registry.build_schema(PHASE_COGNIZE)
    assert ENTITY_TAG_PREFIX in text, "belief 的契约里没有 `#entity:`"
    assert f'"{ENTITY_TAG_PREFIX}老师"' in text, "示例里没有（她只照抄示例）"
    assert "subject" in text and "进图" in text, "没写清与 `subject` 的分工"


def test_parse_cognitions_carries_belief_tags():
    """⭐ 断链守门: **契约层**要能把 belief 的 `tags` 带到行里 ——

    上面那两条直接给 `apply_cognitions` 喂行（绕过 parse）⇒ "parse 忘了收 tags"
    这个断链它们抓不住（写侧永远收不到东西, 而图上什么都不缺的样子）。
    """
    items, vr = digest_registry.parse_cognitions(
        {"cognitions": [{"belief": {"text": "老师会记住我说的话",
                                    "tags": ["#entity:sensei"]},
                         "supports": ["m0001"]}]},
        evidence_ids={"m0001"}, cognition_ids=set(), group_ids=set(), kind_of={})
    assert not vr.errors, vr.errors
    assert len(items) == 1, (items, vr.drops)
    assert items[0].get("tags") == [f"{ENTITY_TAG_PREFIX}sensei"], items[0]


def test_parse_cognitions_drops_a_nameless_entity_tag():
    """空的 `#entity:`（没名字）在**看法**那条路上也要丢项 + 记账（文案不能自称 episodes）。"""
    items, vr = digest_registry.parse_cognitions(
        {"cognitions": [{"belief": {"text": "……", "tags": ["#entity:"]},
                         "supports": ["m0001"]}]},
        evidence_ids={"m0001"}, cognition_ids=set(), group_ids=set(), kind_of={})
    assert items[0].get("tags") is None, items[0]
    assert any("cognitions[0].belief" in d for d in vr.drops), vr.drops


# ---------------------------------------------------------------------------
# E1b（2026-10-08）—— 判据补全 + 防 alias（把【已有的对象】摆给写 tag 的那两轮）
# ---------------------------------------------------------------------------

def test_contract_spells_out_the_entity_tag_judgement():
    """⭐ 判据必须在**契约**里（用户 2026-10-08 逐条给的），三条一条都不能少。"""
    text = digest_registry.build_schema(PHASE_RECORD)
    assert "检索词本身别用" in text and "`#` 开头" in text, "缺「检索词别用 `#` 开头」那条禁令"
    assert "新认识的角色" in text and "必须写" in text, "缺「新认识的角色必须写」"
    assert "跨时间段" in text, "缺「跨时间段反复出现」的判据（与连续事件的同一个词区分开）"
    assert "抽象的" in text and "司空见惯" in text, "缺两条「不写」"
    assert "已有的对象" in text and "别自己造一个新叫法" in text, "缺防 alias 那条"


def test_hash_prefixed_search_word_is_reported_not_silently_dropped():
    """⭐ 静默 no-op 的入口: `#` 开头 = 标记空间（检索侧会跳过它）⇒ **必须记一笔**。"""
    warnings: list[str] = []
    words, marks = _split_tags(["公园", "#日常", "#entity:老师"], warnings, [],
                              where="episodes[0]")
    assert words == ["公园", "#日常"], words          # 词照收（不丢内容）
    assert marks == [f"{ENTITY_TAG_PREFIX}老师"], marks
    assert any("#日常" in w and "标记空间" in w for w in warnings), warnings
    # ⚠️ 而且**只有**它一条告警（`#entity:` 与普通词都不该告警）
    assert len(warnings) == 1, warnings


def test_existing_entities_line_prints_names_and_aliases(tmp_path):
    """⭐ 防 alias 靠这一栏: 印**真身 id + 名字（别名）**; 空表印一句"为什么空"。"""
    from core.digest.material import existing_entities_line

    st = _store(tmp_path)
    line = existing_entities_line(st, texts=["今天老师说他会早点来"])
    assert "x0001 老师" in line and "sensei" in line, line
    assert "x0000" in line, line
    empty = WikiStoreV2(tmp_path / "empty", world_id="world1", char_id="c")
    assert "还没有任何对象" in existing_entities_line(empty), "空表要有理由（不然整格被吞）"
