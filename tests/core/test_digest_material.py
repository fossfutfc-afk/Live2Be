"""`core/digest/material.py` 的**引擎侧**判据（P2, 2026-10-07）。

这里测的不是"她写了什么", 而是"引擎摆了什么"—— 两件都是**纯计算**（零 LLM）:
L1 的「现有经历（候选）」（⭐ 2026-10-14 起由 `like(spec="digest")` 排）
与「候选对象」（≤10 个真 id + 命中提示）。
端到端那两条在 `test_wiki_digest.py`（`test_l1_akin_reaches_an_older_episode` 等）;
这里钉的是**挑法与上限**这类单看料才看得出的性质。
"""
from core.brain import WikiStoreV2, make_node
from core.brain.entities import ensure_entities, object_lines
from core.digest import material
from core.digest.material import (
    DIGEST_L2_AKIN,
    DIGEST_RELATE_CAND_K,
    _episode_candidates,
    _l2_material,
)


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",), sensei_name="老师")
    st.save()
    return st


def _ep(st, text, *, title="", tags=(), ts=""):
    return st.add(make_node("episode", text=text, title=title, tags=list(tags),
                            ts=ts, event_seq=[3]))


def test_episode_candidates_come_from_like_with_score_and_reason(tmp_path):
    """候选 = **`like(spec="digest")` 排出来的最像的几条**（⭐ 2026-10-14 换源）。

    ⏸ **换源前**这里钉的是"`topics` 有交集、按交集大小排"—— `topics` 退役后那条判据
    没有载体了（真机上它也恒空: 21 条经历只有 3 条标了轴、互相还不共轴）。
    今天引擎**不判**"像不像"（那是她的活）: 它摆**最像的** + **为什么像**（`like` 的 `why`）。
    ⚠️ 测试里没有 embedder ⇒ `semantic` 那一路不在, 摆出来的靠**字面**（tags/标题/覆盖）。
    """
    st = _store(tmp_path)
    old_two = _ep(st, "天台上的苔藓", title="苔藓的事", tags=["苔藓", "天台"],
                  ts="2026-09-01T10:00:00")
    old_one = _ep(st, "苔藓长得好", title="苔藓", tags=["苔藓"],
                  ts="2026-09-05T10:00:00")
    _ep(st, "甜品店的新品", title="甜品", tags=["甜品"], ts="2026-09-06T10:00:00")
    new = _ep(st, "这次又说苔藓", title="又说苔藓", tags=["苔藓"],
              ts="2026-09-09T10:00:00")
    st.save()

    text, ids = _episode_candidates(st, [new], now="2026-09-10T10:00:00")

    assert set(ids) == {old_two, old_one}, ids           # 无关那条不进来
    assert "候选 0." in text, text                        # 带分（`like` 那一格）
    assert "→ 为什么: tags[苔藓]" in text, text            # 带理由（看不见就判不准）
    assert "甜品" not in text, "没被排上的不摆"
    # ⭐ 时间两格（相对 + 日期）也在 —— 契约那句"时间上接着的不算同类"要她判得出来
    assert "9/1" in text, text

    # 跟谁都不像 ⇒ 摆不出候选 —— 那也是结论, ⛔ 不许回空串（会被 `_join_sections`
    # 的 `if body` 连抬头一起吞掉, 她看不见这个结论）。
    lonely = _ep(st, "沙漠里的一粒沙", title="沙漠", tags=["沙漠"],
                 ts="2026-09-09T10:00:00")
    st.save()
    text_lone, ids_lone = _episode_candidates(st, [lonely], now="")
    assert ids_lone == []
    assert text_lone == "（无 —— 召回没找到跟这一段像的旧经历）", text_lone

    # 上限吃 `DIGEST_RELATE_CAND_K`（也是每次问 `like` 的 k）
    st2 = _store(tmp_path / "b")
    for i in range(DIGEST_RELATE_CAND_K + 3):
        _ep(st2, f"旧事 {i}", title=f"旧事{i}", tags=["苔藓"],
            ts=f"2026-09-{i + 1:02d}T10:00:00")
    new2 = _ep(st2, "又来看苔藓", title="又来", tags=["苔藓"], ts="2026-09-20T10:00:00")
    st2.save()
    _text2, ids2 = _episode_candidates(st2, [new2], now="2026-09-21T10:00:00")
    assert len(ids2) == DIGEST_RELATE_CAND_K, ids2


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


def test_topics_is_gone_from_the_material():
    """⏸ **2026-10-14**: `topics` 退役后料里**不再有 `轴 …` 那一格**（用户裁 C1）。

    ⛔ **别拿 `tags` 顶替**: 真机实测那些词大半是泛词（"约定 / 笔记"），一条经历能跟
    9 条相连 ⇒ 零区分力。判"像不像"的依据改成 `like` 的**分 + 为什么**。
    ⚠️ 信息头本身的形状（格序 / 空的不占位）仍由 `test_marks_guard.py` 钉着 ——
    这里只管"那一格没了"。
    """
    assert not hasattr(material, "_axes_field"), "那一格该随 topics 一起撤"
    assert not hasattr(material, "_likeness_axis"), "相似簇的轴也是同一格"


# ---------------------------------------------------------------------------
# ⭐⭐ L2（`cognize`）的料 —— P8（2026-10-08 用户定的形状）
# ---------------------------------------------------------------------------

class _Ctx:
    """`_l2_material` 只用到三样东西（store / episode_ids / now_ts）—— 鸭子类型就够。"""

    def __init__(self, store, episode_ids, now_ts="2026-10-05T10:00:00+08:00"):
        self.store, self.episode_ids, self.now_ts = store, episode_ids, now_ts


def _new_ep(st, text, *, title="", tags=(), ts="2026-10-04T10:00:00+08:00", sig=0.5):
    return st.add(make_node("episode", text=text, title=title, tags=list(tags),
                            ts=ts, significance=sig, event_seq=[3]))


def test_l2_linked_episodes_only_takes_the_connected_ones(tmp_path):
    """⭐ P8: 【被连过的经历】只收**图上有边**的那些 —— 孤立经历不进（天然的归纳门槛）。

    ⚠️ 一条都没连过 ⇒ 印一句"**为什么空**"（P6 的口径: 空串会被 `_join_sections`
    连抬头一起吞掉, 她既看不见这一格、也不知道那个结论）。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    a = _new_ep(st, "又去看苔藓", title="苔藓", tags=["苔藓"])
    b = _new_ep(st, "老师夸我", title="被夸")
    lonely = _new_ep(st, "一个人发呆", title="发呆")
    old = _new_ep(st, "更早的苔藓", title="旧苔藓", tags=["苔藓"],
                  ts="2026-09-01T10:00:00+08:00")
    st.save()
    st.add_edge("akin", a, old)
    st.add_edge("akin", b, old)

    linked, _ev = _l2_material(_Ctx(st, [a, b, lonely]))
    assert f"〔{a}｜" in linked and f"〔{b}｜" in linked
    assert lonely not in linked, "孤立经历不进 L2"
    assert "一个人发呆" not in linked, "正文也不许漏进来"
    assert "轴" not in linked, "⏸ 2026-10-14: `topics` 退役 ⇒ 行头不再有 `轴 …` 那一格"

    _only_lonely, _ev2 = _l2_material(_Ctx(st, [lonely]))
    assert "（这一段没有被连过的经历" in _only_lonely, _only_lonely


def test_akin_block_hangs_under_its_anchor(tmp_path):
    """⭐ **2026-10-13**: 相似簇**挂在每条经历下面**（⏸ 2026-10-14: `轴` 那一格随 `topics` 撤）。

    判据（用户裁 A 案）: 老块（【本段归类的群】）是给她**写沉淀**用的, 而沉淀已停产;
    新块是给她**写结论**用的 —— "这条看法不只被这一段那一条撑着, 还有她早先认过'像'的那些"。
    """
    st = _store(tmp_path)
    a = _ep(st, "老师约我去咖啡厅吃甜点", title="咖啡厅的甜点", tags=["甜点", "咖啡厅"],
            ts="2026-10-04T10:00:00+08:00")
    old = _ep(st, "更早的一次甜点", title="上次的甜点", tags=["甜点"],
              ts="2026-09-20T10:00:00+08:00")
    b = _ep(st, "天台上的事", title="天台", tags=["天台"])
    st.save()
    st.add_edge("akin", a, old)
    st.add_edge("akin", b, a)                       # 本段的另一条也能是"像的"

    text, evidence = _l2_material(_Ctx(st, [a, b]))
    assert "   ↳ 她认过跟它像的（这些也会算作这条看法的证据）:" in text, text
    # 邻居那一行: 钥匙 + 标题 + 时间（⛔ 没有 `轴 …` 那一格了）
    line = next(ln for ln in text.splitlines() if "上次的甜点" in ln)
    assert "〔m0002｜《上次的甜点》｜" in line, line
    assert "轴" not in line, line
    assert "周前" in line or "天前" in line, line
    # 挂在它自己那条 anchor **下面**（顺序: anchor 行 → 簇 → 下一条 anchor 行）
    assert text.index("〔m0001｜") < text.index("↳ 她认过跟它像的") < text.index("〔m0003｜"), text
    # ⭐ 印出来 ⇒ 能引用（老经历也算证据 —— 判它"编造 id"就是把她自己的簇锁在门外）
    assert evidence == [a, b, old], evidence


def test_akin_block_caps_and_says_how_many_left(tmp_path):
    """超 `DIGEST_L2_AKIN` 只印前几条 + **明说还有几条没印**（⛔ 不静默截断）。"""
    st = _store(tmp_path)
    a = _ep(st, "锚", title="锚")
    others = [_ep(st, f"第 {i} 件事", title=f"第{i}件", ts=f"2026-09-{i + 1:02d}T10:00:00+08:00")
              for i in range(DIGEST_L2_AKIN + 2)]
    st.save()
    for o in others:
        st.add_edge("akin", a, o)

    text, evidence = _l2_material(_Ctx(st, [a]))
    heads = [ln for ln in text.splitlines() if ln.strip().startswith("〔")]
    assert len(heads) == DIGEST_L2_AKIN + 1, text          # anchor 那一行 + 印出来的邻居
    assert "（还有 2 条没印 —— 先照印出来的这几条写）" in text, text
    assert evidence == [a, *others[:DIGEST_L2_AKIN]], evidence


def test_akin_block_never_prints_a_body_twice(tmp_path):
    """一份料里**同一段正文只印一次**: 本段的邻居只出信息头, 挂在两条 anchor 上的只印一次。"""
    st = _store(tmp_path)
    a = _ep(st, "本段第一条", title="甲")
    b = _ep(st, "本段第二条", title="乙")
    old = _ep(st, "很老的一条", title="旧", ts="2026-09-01T10:00:00+08:00")
    st.save()
    st.add_edge("akin", a, b)                        # 本段的 b 是 a 的同类
    st.add_edge("akin", b, old)                      # b 的簇里有 old
    st.add_edge("akin", a, old)                      # a 的簇里也有 old（先到先得）

    text, evidence = _l2_material(_Ctx(st, [a, b]))
    assert text.count("很老的一条") == 1, text        # 同一段正文只印一次
    assert text.count("本段第二条") == 1, text        # 本段那条: 只在簇里出信息头, 正文在它自己那行
    assert evidence == [a, b, old], evidence
    print("    相似簇: 正文一条只印一次（本段的只出钥匙, 重复的整个省掉）")


def test_akin_block_skips_a_neighbour_that_fights_the_anchor(tmp_path):
    """与 anchor 打架的邻居**不摆**（同写入侧: 打架的证据不共撑一个结论）—— 摆出来只会诱
    她写一条自己拆自己台的结论。"""
    st = _store(tmp_path)
    a = _ep(st, "锚", title="锚")
    bad = _ep(st, "跟它打架的那条", title="打架")
    good = _ep(st, "和平共处的那条", title="和平")
    st.save()
    st.add_edge("akin", a, bad)
    st.add_edge("akin", a, good)
    st.add_edge("contradicts", a, bad)

    text, _ev = _l2_material(_Ctx(st, [a]))
    assert "打架" not in text, text
    assert "和平" in text, text


def test_l2_evidence_is_exactly_what_the_block_printed(tmp_path):
    """⭐ P10: **料里印出来过的经历 = 她能引用的那批** —— 一个不多一个不少。

    ⚠️ **2026-10-13 改写（第二次）**: 群块随 `group` 退役撤掉之后, 这一条钉的是
    "印出来的经历就能引用"; 现在**相似簇印出来的老经历也算**（它们正是"这一类事"的
    另外几条, ⛔ 判它们"编造 id"就是把她自己的簇锁在门外）—— 判据本身一个字没变:
    `evidence_ids` 是**从渲染里带出来的**（⛔ 不另算一份）, 少收一条就是"合法行被判编造 id"
    ⇒ 整包拒 ⇒ 白跑一次重试（L1 的教训）。
    """
    st = _store(tmp_path)
    linked_ep = _ep(st, "被连过的那条", title="连过的")
    lonely = _ep(st, "没人连过的那条", title="没连的")
    old = _ep(st, "更早的一条", title="旧的", ts="2026-09-01T10:00:00+08:00")
    st.save()
    st.add_edge("akin", linked_ep, old)

    linked, evidence = _l2_material(_Ctx(st, [linked_ep, lonely]))
    assert evidence == [linked_ep, old], evidence      # ⛔ 没印过的不算（lonely 没被连过）
    assert "被连过的那条" in linked
    assert "没人连过的那条" not in linked, "孤立经历不进料 ⇒ 也不该进证据名单"
    assert linked.count("被连过的那条") == 1, linked   # 一条只印一次


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

    linked, _ev = _l2_material(_Ctx(st, [with_about, without]))
    assert "   ↳ 关于: x0001 老师" in linked, linked       # 别名由 entity_label 决定
    assert "↳ 印证" not in linked and "↳ 同类" not in linked, linked
    # 没有 about 的那条**不该**有这一行: 全文里只出现一次「↳ 关于」
    assert linked.count("↳ 关于") == 1, linked
