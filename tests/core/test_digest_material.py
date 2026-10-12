"""`core/digest/material.py` 的**引擎侧**判据（P2, 2026-10-07）。

这里测的不是"她写了什么", 而是"引擎摆了什么"—— 两件都是**纯计算**（零 LLM）:
L1 的「现有经历（候选）」（按 `topics` 相交摆）与「候选对象」（≤10 个真 id + 命中提示）。
端到端那两条在 `test_wiki_digest.py`（`test_l1_akin_reaches_an_older_episode` 等）;
这里钉的是**挑法与上限**这类单看料才看得出的性质。
"""
from core.brain import WikiStoreV2, make_node
from core.brain.entities import ensure_entities, object_lines
from core.digest.material import (
    DIGEST_L2_MEMBERS,
    DIGEST_RELATE_CAND_K,
    _axes_field,
    _episode_candidates,
    _group_block,
    _groups_for_l2,
    _l2_material,
)


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


# ---------------------------------------------------------------------------
# ⭐⭐ L2（`cognize`）的料 —— P8（2026-10-08 用户定的形状）
# ---------------------------------------------------------------------------

class _Ctx:
    """`_l2_material` 只用到三样东西（store / episode_ids / now_ts）—— 鸭子类型就够。"""

    def __init__(self, store, episode_ids, now_ts="2026-10-05T10:00:00+08:00"):
        self.store, self.episode_ids, self.now_ts = store, episode_ids, now_ts


def _new_ep(st, text, *, title="", topics=(), ts="2026-10-04T10:00:00+08:00", sig=0.5):
    return st.add(make_node("episode", text=text, title=title, topics=list(topics),
                            ts=ts, significance=sig, event_seq=[3]))


def test_l2_linked_episodes_only_takes_the_connected_ones(tmp_path):
    """⭐ P8: 【被连过的经历】只收**图上有边**的那些 —— 孤立经历不进（天然的归纳门槛）。

    ⚠️ 一条都没连过 ⇒ 印一句"**为什么空**"（P6 的口径: 空串会被 `_join_sections`
    连抬头一起吞掉, 她既看不见这一格、也不知道那个结论）。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    a = _new_ep(st, "又去看苔藓", title="苔藓", topics=["苔藓"])
    b = _new_ep(st, "老师夸我", title="被夸")
    lonely = _new_ep(st, "一个人发呆", title="发呆")
    old = _new_ep(st, "更早的苔藓", title="旧苔藓", topics=["苔藓"],
                  ts="2026-09-01T10:00:00+08:00")
    st.save()
    st.add_edge("akin", a, old)
    st.add_edge("akin", b, old)

    _grp, linked, _ev = _l2_material(_Ctx(st, [a, b, lonely]))
    assert f"〔{a}｜" in linked and f"〔{b}｜" in linked
    assert lonely not in linked, "孤立经历不进 L2"
    assert "一个人发呆" not in linked, "正文也不许漏进来"
    assert "轴 苔藓" in linked, "行头带轴（与 L1 同一印法）"

    _g2, only_lonely, _ev2 = _l2_material(_Ctx(st, [lonely]))
    assert "（这一段没有被连过的经历" in only_lonely, only_lonely


def test_l2_picks_the_group_with_the_most_new_members(tmp_path):
    """⭐ P8: 旋钮 = 1 时挑**本段新归入最多**的那一组（"这一段刚给它添了最多东西"）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    g1 = st.add(make_node("experience", title="吃饭"))
    g2 = st.add(make_node("experience", title="苔藓"))
    e1 = _new_ep(st, "一起吃饭", title="吃饭")
    e2 = _new_ep(st, "又见苔藓", title="苔藓一")
    e3 = _new_ep(st, "再见到苔藓", title="苔藓二")
    st.save()
    st.add_edge("member_of", e1, g1)                     # g1 收 1 条
    st.add_edge("member_of", e2, g2)                     # g2 收 2 条
    st.add_edge("member_of", e3, g2)

    ctx = _Ctx(st, [e1, e2, e3])
    # ⚠️ 缺省 = `DIGEST_L2_GROUPS`（2026-10-08 用户抬到 3）⇒ **两组都出**
    grp, _linked, _ev = _l2_material(ctx)
    assert f"群 {g2}《苔藓》" in grp and f"群 {g1}《" in grp, grp
    assert "这一类现在有 2 条经历 · 本段新归入 2 条" in grp, grp
    # 排序: 新归入多的在前
    assert [g for g, _new in _groups_for_l2(ctx, cap=2)] == [g2, g1]
    # 旋钮给 1 ⇒ 只出最该更新的那一组
    assert [g for g, _new in _groups_for_l2(ctx, cap=1)] == [g2]


def test_l2_group_pick_prefers_the_unsoaked_when_tied(tmp_path):
    """⭐ 平手时**还没写过沉淀的类**优先 —— ⛔ 否则"从没写过"的类会永远排在队尾。

    一段只摆 `DIGEST_L2_GROUPS` 组 ⇒ 若平手时只按 id 排, 那个 id 大的新类**永远轮不到**,
    它的沉淀就"**永远不写**"了。用户 2026-10-08 把旋钮抬到 2~3, 这条排序是另一半解药。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    g1 = st.add(make_node("experience", title="早写过沉淀的", text="早有的一句话"))
    g2 = st.add(make_node("experience", title="这一段添得最多的"))
    g3 = st.add(make_node("experience", title="从没写过沉淀的"))     # id 最大 ⇒ 旧排序会漏它
    e1 = _new_ep(st, "a", title="a")
    e2 = _new_ep(st, "b", title="b")
    e3 = _new_ep(st, "c", title="c")
    e4 = _new_ep(st, "d", title="d")
    st.save()
    st.add_edge("member_of", e1, g1)                    # g1: 1 条新归入 + **有**沉淀
    st.add_edge("member_of", e2, g2)                    # g2: 2 条新归入
    st.add_edge("member_of", e3, g2)
    st.add_edge("member_of", e4, g3)                    # g3: 1 条新归入 + **无**沉淀

    picked = [g for g, _new in _groups_for_l2(_Ctx(st, [e1, e2, e3, e4]), cap=2)]
    assert picked == [g2, g3], picked
    assert g1 not in picked, "有沉淀的那个该给'从没写过'的让位"
    print("    挑组: 新归入多的先; 平手时**还没写过沉淀的**先（不再只看 id）")


def test_l2_group_block_caps_members_and_says_how_many_left(tmp_path):
    """⭐ P8: 已有成员截到 `DIGEST_L2_MEMBERS`（4）并**明说还有几条没印**（不静默截断）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    gid = st.add(make_node("experience", title="一类事"))
    members = [_new_ep(st, f"第 {i} 件事", title=f"第{i}件",
                       ts=f"2026-09-{i + 1:02d}T10:00:00+08:00") for i in range(6)]
    st.save()
    for m in members:
        st.add_edge("member_of", m, gid)

    block, printed = _group_block(st, gid, new_ids=[], linked_ids=set(),
                                  cap=DIGEST_L2_MEMBERS)
    heads = [ln for ln in block.splitlines() if ln.strip().startswith("〔")]
    assert len(heads) == DIGEST_L2_MEMBERS, block
    assert f"已有成员（按难忘排, 最多印 {DIGEST_L2_MEMBERS} 条; 还有 2 条没印）:" in block, block
    # 难忘降序 → 同分时**时间新的在前**（第 6 件在最上面）
    assert "第5件" in heads[0], heads
    # 不超上限 ⇒ 不印"还有 N 条"
    small, _p2 = _group_block(st, gid, new_ids=[], linked_ids=set(), cap=6)
    assert "没印" not in small, small


def test_l2_body_text_appears_exactly_once(tmp_path):
    """⭐ P8: 同一段正文在一份料里**只出现一次**。

    既"本段新归入"又"被连过" ⇒ 群块印**把手**、正文在【被连过的经历】里（全文一处）;
    只"新归入"、**没被连过** ⇒ 群块印全文（⛔ 不许丢 —— 那是写沉淀的素材）。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    gid = st.add(make_node("experience", title="一类事"))
    linked_ep = _new_ep(st, "既归了类又被连过的那条", title="连过的")
    only_group = _new_ep(st, "只归了类没被连过的那条", title="只归类的")
    old = _new_ep(st, "更早的一条", title="旧的", ts="2026-09-01T10:00:00+08:00")
    st.save()
    st.add_edge("member_of", linked_ep, gid)
    st.add_edge("member_of", only_group, gid)
    st.add_edge("akin", linked_ep, old)

    grp, linked, evidence = _l2_material(_Ctx(st, [linked_ep, only_group]))
    assert f"〔{linked_ep}｜《连过的》〕（正文见下）" in grp, grp
    assert "既归了类又被连过的那条" not in grp, "正文只在被连块里印"
    assert "既归了类又被连过的那条" in linked
    assert "只归了类没被连过的那条" in grp, "没在别处印过的照印全文（不许丢）"
    # ⭐ P10: 第三个返回值 = **料里印出来过的全部经历**（她被允许引用的就这一批）
    assert evidence == [linked_ep, only_group], evidence
    all_text = grp + linked
    assert all_text.count("既归了类又被连过的那条") == 1


def test_l2_about_line_follows_the_edge_and_prints_the_object(tmp_path):
    """⭐ P8: `↳ 关于:` 只在**真有 `about` 边**时出现; 印法走 `entities.entity_label`
    （与 L1 的对象候选**同一处实现** —— 同一张图两处长得一样）。

    ⛔ 同一块的 `↳ 印证` / `↳ 同类` **不印**（用户 2026-10-08: 那是"已有成分之间的关系",
    契约明写着"上一趟已经判过了"）。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",), sensei_name="老师")
    with_about = _new_ep(st, "老师又帮我搬了东西", title="老师帮忙")
    without = _new_ep(st, "一个人在屋顶坐着", title="屋顶")
    st.save()
    st.add_edge("about", with_about, "x0001")
    st.add_edge("akin", without, with_about)              # 有边（但**没有** about）

    _grp, linked, _ev3 = _l2_material(_Ctx(st, [with_about, without]))
    assert "   ↳ 关于: x0001 老师" in linked, linked       # 别名由 entity_label 决定
    assert "↳ 印证" not in linked and "↳ 同类" not in linked, linked
    # 没有 about 的那条**不该**有这一行: 全文里只出现一次「↳ 关于」
    assert linked.count("↳ 关于") == 1, linked
