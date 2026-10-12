"""召回的**形式表 + 唯一前门**（`core/brain/read/modes.py`, 2026-10-12）。

判据（这一件是**接口**，所以守门盯的是"表与形状", 不是某条召回的分数）:
  ① **表结构合法**: 每行的字段组合自洽（rank ⇒ 有 `spec` 且在 `like.SPECS` 里;
     set ⇒ 有 `anchors` 且都在 `find.ANCHORS` 里; 每行有抬头; ⛔ rank 行不许写 `order`）
  ② ⭐ **`turn` 与从前逐字同**（`recall(mode="turn")` ≡ `like(spec="turn")`）—— 换前门
     **零行为变更**
  ③ **未知名当场炸**（`KeyError` + 可用清单; ⛔ 不静默回落缺省）
  ④ **形状的旋钮不许串**: 给 set 型传 `k` / `weights` ⇒ `ValueError`（不静默忽略）
  ⑤ ⭐ **set 形状的语义**（这是它存在的理由）: `name` 形式把"关于某人的**全部**"捞回来 ——
     含**正文里没写他名字**的那些, 且**不受"像不像"影响**（对比 `rank` 型捞不回来）
  ⑥ **没提名字 ⇒ 空**（不猜、不拿最近一条凑）
  ⑦ **多锚并集**: 提两个人 ⇒ 两条车道并集, **去重**且按同一口径**新→旧**排
  ⑧ **文案单源**: `render_section(mode="turn")` 与 `render_recall_block` **同字**
  ⑨ ⭐ **保留号不触发**（`skip_ids`）: 她自己（`x0000`）/ 老师（`x0001`）的名字
     在 query 里出现**不算"提到了谁"** —— 那两条车道≈全部事件
  ⑩ **名字段的预算与文案都归公共设施**: 抬头取自表, 字符预算读同一个
     `[recall].turn_budget`（不是"有多少摆多少"）
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brain import WikiStoreV2, make_node                     # noqa: E402
from core.brain.read import modes                                 # noqa: E402
from core.brain.read.find import ANCHORS                          # noqa: E402
from core.brain.read.like import SPECS, RecallCtx, like           # noqa: E402
from core.brain.read.render import render_recall_block            # noqa: E402

NOW = datetime(2026, 10, 12, 21, 0, tzinfo=timezone(timedelta(hours=8)))
CHAR = "igusa_haruka"


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id=CHAR)


def _ctx(query: str) -> RecallCtx:
    return RecallCtx(now=NOW, query=query, embed_fn=None, char_id=CHAR)


def _seed_aru(store) -> None:
    """一个对象（阿露）+ 三条挂她车道的经历（其中**正文里一个"阿露"都没有**）+ 一条无关。

    ⚠️ 阿露的 id **不能借 `x0001`**（那是 `entities.SENSEI_ID` = 老师的保留号）——
    名字段按 id 剔除保留号（`modes.RESERVED_TRIGGERS`）, 借号会让"她能不能被提起"
    这条用例**静默测错**。
    """
    aru = make_node("entity", name="陆八魔 阿露", text="我社长")
    aru.id = "x0002"
    aru.aliases = ["阿露", "社长"]
    store.add(aru)
    for title, text, ts, sig in (("搬箱子", "她让我把装炸弹的箱子搬去仓库", "2026-09-20T10:00:00", 0.6),
                                 ("清点仓库", "社团的人把炸弹清点了一遍", "2026-10-01T10:00:00", 0.2),
                                 ("挨骂那天", "我被骂了，她替我说了话", "2026-10-10T10:00:00", 0.05)):
        eid = store.add(make_node("episode", text=text, title=title, ts=ts,
                                  significance=sig, event_seq=[1]))
        store.add_edge("about", eid, "x0002", ts=ts)
    store.add(make_node("episode", text="在杂草屋蹲了一下午", title="苔藓的约定",
                        ts="2026-10-02T10:00:00", significance=0.9, event_seq=[2]))
    store.save()


def _seed_msk(store) -> None:
    """第二个对象（睦月 `x0003`）+ 一条挂她车道的经历 —— 用来验"两个人 = 两把钥匙"。"""
    msk = make_node("entity", name="浅黄 睦月", text="")
    msk.id = "x0003"
    msk.aliases = ["睦月"]
    store.add(msk)
    eid = store.add(make_node("episode", text="睦月请我吃了拉面", title="拉面",
                              ts="2026-10-12T09:00:00", significance=0.5, event_seq=[4]))
    store.add_edge("about", eid, "x0003", ts="2026-10-12T09:00:00")
    store.save()


def test_mode_table_is_well_formed():
    """① 表里每一行都自洽 —— 加形式 = 加一行, 所以**这一条就是给"加行"立的规矩**。"""
    assert modes.MODES and modes.DEFAULT_MODE in modes.MODES
    for name, m in modes.MODES.items():
        assert m.shape in modes.SHAPES, (name, m.shape)
        assert m.header.strip(), f"{name}: 形式必须有抬头（她总得看到「为什么想起」）"
        if m.shape == modes.SHAPE_RANK:
            assert m.spec in SPECS, (name, m.spec)
            assert not m.anchors and not m.payload_from, name
            assert not m.order, f"{name}: 排序是 like 的事（rank 行别写 order）"
        else:
            assert m.anchors and set(m.anchors) <= set(ANCHORS), (name, m.anchors)
            assert m.payload_from in modes.PAYLOADS, (name, m.payload_from)
            assert m.order == "newest", (name, m.order)
        # `describe()` 要给台账/文档用 ⇒ 每行都得说得出"判据是什么"
        assert any(row[0] == name and row[2] for row in modes.describe()), name
    print(f"    modes: 表结构合法（{len(modes.MODES)} 行: {sorted(modes.MODES)}）")


def test_turn_mode_is_byte_identical_to_the_old_entry(tmp_path):
    """② ⭐ 换前门**零行为变更**: `recall(mode="turn")` ≡ `like(spec="turn")`（逐条 id+分）。"""
    store = _store(tmp_path)
    _seed_aru(store)
    for query in ("阿露最近怎么样", "炸弹箱子搬去仓库", "苔藓"):
        got = modes.recall(store, _ctx(query), mode="turn")
        want = like(store, _ctx(query), spec="turn")
        assert [(c.node.id, c.score) for c in got] == [(c.node.id, c.score) for c in want], query
    print("    modes: `turn` 与 `like(spec='turn')` 逐条同（零行为变更）")


def test_unknown_mode_raises_with_the_list():
    """③ 未知名**当场炸**（拼错的名字不许静默走缺省 —— 那会让"我设了"变成谎话）。"""
    with pytest.raises(KeyError) as e:
        modes.mode_of("recall2")
    assert "可用" in str(e.value) and "name" in str(e.value)
    print("    modes: 未知形式 → KeyError + 可用清单")


def test_set_shape_refuses_rank_knobs(tmp_path):
    """④ 形状的旋钮不许串: set 型收到 `k` / `weights` ⇒ `ValueError`。"""
    store = _store(tmp_path)
    _seed_aru(store)
    for kw in ({"k": 2}, {"weights": {"lexical": 1.0}}):
        with pytest.raises(ValueError):
            modes.recall(store, _ctx("阿露"), mode="name", **kw)
    print("    modes: set 型没有 k / weights（给了就炸, 不静默忽略）")


def test_name_mode_returns_the_whole_lane_not_the_likeness(tmp_path):
    """⑤ ⭐ **set 形状的语义**: "关于某人的全部" —— 含正文没写他名字的那些, 且不看"像不像"。

    ⚠️ 判据必须落在"与 rank 型的**差别**"上: 挑一条**显著度极低、字面毫不沾边**的经历
    （`挨骂那天`, sig 0.05）—— `like` 那一档压根不会把它摆出来（没有证据轴命中），
    而 `name` 形式**必须**给它（它挂了 `about` 边 = 她记得这件事跟他有关）。
    """
    store = _store(tmp_path)
    _seed_aru(store)
    got = modes.recall(store, _ctx("阿露"), mode="name")
    titles = [c.node.title for c in got]
    assert titles == ["挨骂那天", "清点仓库", "搬箱子"], titles     # 新→旧, 全部三条
    assert "苔藓的约定" not in titles                              # 没挂她的车道 ⇒ 不进来
    # 对照: rank 型同一句 —— "像不像"当家, 那条 sig 0.05 且字面不沾边的捞不回来
    rank = {c.node.title for c in like(store, _ctx("阿露"), spec="turn")}
    assert "挨骂那天" not in rank, rank
    print("    modes: `name` = 车道全量（含正文没写名字的）; rank 型捞不回同一条")


def test_name_mode_is_empty_without_a_mentioned_name(tmp_path):
    """⑥ 没提名字 ⇒ 空（不猜、不拿最近一条凑 —— 同 `like` 的宁缺勿错）。"""
    store = _store(tmp_path)
    _seed_aru(store)
    assert modes.recall(store, _ctx("今天天气不错"), mode="name") == []
    print("    modes: 没提名字 ⇒ 空（不凑）")


def test_name_mode_unions_and_dedupes(tmp_path):
    """⑦ 提两个人 ⇒ 两条车道**并集**、去重, 且按 `find` 的同一口径**新→旧**。

    ⚠️ 两条车道各自**已经有序**（`find` 每次调用内部排好）⇒ 光看"第一条最新"验不出
    合并后有没有重排: 必须让**第二条车道**里有一条**比第一条车道全都新**的 ——
    那样"直接接起来"就会把它压在后面（串起来忘了排 ⇒ 这一条红）。
    """
    store = _store(tmp_path)
    _seed_aru(store)
    msk = make_node("entity", name="浅黄 睦月", text="")
    msk.id = "x0003"
    msk.aliases = ["睦月"]
    store.add(msk)                                                 # ⚠️ 必须入库（悬空边会被拒）
    both = store.add(make_node("episode", text="我和睦月还有社长一起去了仓库",
                               title="三个人", ts="2026-10-11T10:00:00",
                               significance=0.5, event_seq=[3]))
    store.add_edge("about", both, "x0002", ts="2026-10-11T10:00:00")
    store.add_edge("about", both, "x0003", ts="2026-10-11T10:00:00")
    newest = store.add(make_node("episode", text="睦月今天请我吃了拉面",
                                 title="拉面", ts="2026-10-12T09:00:00",
                                 significance=0.5, event_seq=[4]))
    store.add_edge("about", newest, "x0003", ts="2026-10-12T09:00:00")
    store.save()
    assert store.get("x0002") is not None and store.get("x0003") is not None
    got = [c.node.title for c in modes.recall(store, _ctx("阿露和睦月最近怎么样"), mode="name")]
    assert got.count("三个人") == 1, got                          # 两条车道都命中 ⇒ 只出现一次
    assert got[0] == "拉面", got                                  # ⭐ 第二条车道里最新的那条在最前
    assert "搬箱子" in got and "拉面" in got                      # 两条车道都在（并集）
    print(f"    modes: 多名字 ⇒ 并集去重 + 新→旧（{got}）")


def test_render_section_shares_the_copy_with_the_old_facade(tmp_path):
    """⑧ 文案单源: `render_section(mode="turn")` 与 `render_recall_block` **同一段字**。"""
    store = _store(tmp_path)
    _seed_aru(store)
    cands = like(store, _ctx("炸弹 搬去仓库"), spec="turn")
    assert cands, "先得有条候选, 否则两边都是空串（假绿）"
    a = modes.render_section(cands, mode="turn", char_name="伊草 遥香", now=NOW)
    b = render_recall_block(cands, char_name="伊草 遥香", now=NOW)
    assert a == b and a.strip(), (a[:60], b[:60])
    print("    modes: `render_section('turn')` ≡ `render_recall_block`（同字）")


def test_reserved_ids_never_trigger_the_name_form(tmp_path):
    """⑨ ⭐ **保留号不算"提到了谁"**（`skip_ids`）—— 她自己 / 老师的车道≈全部事件。

    没这一格的后果（真机尺度）: 老师出现在**几乎每一件事**上 ⇒ 玩家一句"老师你觉得呢"
    就能把整条河摆进动态尾, 还顶着"你想着「X」"这个抬头。
    """
    from core.brain.entities import SELF_ID, SENSEI_ID
    store = _store(tmp_path)
    _seed_aru(store)
    me = make_node("entity", name="伊草 遥香")
    me.id = SELF_ID
    me.aliases = ["遥香"]
    store.add(me)
    sen = make_node("entity", name="老师")
    sen.id = SENSEI_ID
    sen.aliases = ["sensei", "老师"]
    store.add(sen)
    for owner, title in ((SELF_ID, "我自己那天"), (SENSEI_ID, "跟老师那天")):
        eid = store.add(make_node("episode", text="流水账", title=title,
                                  ts="2026-10-09T10:00:00", significance=0.3,
                                  event_seq=[5]))
        store.add_edge("about", eid, owner, ts="2026-10-09T10:00:00")
    store.save()
    # 只提到保留号 ⇒ **一段都不摆**（不是"摆了再被预算裁掉"）
    assert modes.recall(store, _ctx("遥香和老师你们怎么看"), mode="name") == []
    # 保留号与真人**同时**出现 ⇒ 只有真人那条车道（保留号被剔, 真人照常）
    got = [c.node.title for c in modes.recall(store, _ctx("遥香、老师和阿露"), mode="name")]
    assert got == ["挨骂那天", "清点仓库", "搬箱子"], got
    print(f"    modes: 保留号（{SELF_ID}/{SENSEI_ID}）不触发名字形式")


def test_name_section_shares_the_budget_and_the_copy(tmp_path, monkeypatch):
    """⑩ 名字段**不是"有多少摆多少"**: 抬头取自形式表, 字符预算读同一个 `[recall].turn_budget`。

    两段（名字段 / 兜底段）**各自**读这一个数 —— 2026-10-12 用户: *"给 1000 字符吧先"*。
    """
    from core.brain.read import recall_config as rc
    store = _store(tmp_path)
    _seed_aru(store)
    cands = modes.recall(store, _ctx("阿露"), mode="name")
    assert len(cands) == 3, [c.node.title for c in cands]
    full = modes.render_section(cands, mode="name", key="阿露", now=NOW)
    assert full.startswith("【你想着「阿露」"), full          # 抬头 = 表里那一行 + 钥匙
    assert full.count("\n") == 3, full                        # 段头 + 三条（名字段无段尾提示）
    monkeypatch.setattr(rc, "_cache", {"turn_budget": 30.0}, raising=False)
    tight = modes.render_section(cands, mode="name", key="阿露", now=NOW)
    assert tight.count("\n") == 1, tight                      # 段头 + 第一条（第一条永远留）
    print("    modes: 名字段一样吃 `[recall].turn_budget`（不是有多少摆多少）")


def test_keys_come_from_the_same_payload_as_the_candidates(tmp_path):
    """⑪ ⭐ **钥匙**（段头印的那个词）= 老师用的写法, 与候选**同一次载荷**算出。

    ⛔ 印 id（`x0002`）或印她自己的叫法都不行: 要教的是"**老师说的那个词**就是钥匙"
    （`look` 的 `clue` 是同一件事）。
    """
    store = _store(tmp_path)
    _seed_aru(store)
    cands, keys = modes.recall_with_keys(store, _ctx("阿露今天怎么样"), mode="name")
    assert keys == ["阿露"], keys
    # 前门 = 薄壳（逐条同 id + 同分）
    plain = modes.recall(store, _ctx("阿露今天怎么样"), mode="name")
    assert [(c.node.id, c.score) for c in plain] == [(c.node.id, c.score) for c in cands]
    # 两个名字 ⇒ 两把钥匙（段头会印成「阿露、睦月」）
    _seed_msk(store)
    _cands2, keys2 = modes.recall_with_keys(store, _ctx("阿露和睦月"), mode="name")
    assert sorted(keys2) == ["睦月", "阿露"], keys2
    # rank 型**没有**钥匙（"问哪个面"是六路加权, 没有单一钥匙）
    assert modes.recall_with_keys(store, _ctx("阿露"), mode="turn")[1] == []
    print(f"    modes: 钥匙与候选同源（{keys2}）；rank 型无钥匙")


def test_when_mode_takes_the_whole_window_and_never_widens(tmp_path):
    """⑬ ⭐ `when` 形式: 老师说了个时间词 ⇒ **那段时间里全部**（新→旧）, 且**只查 exact**。

    三条判据:
      · **区间**当家（与 `turn` 的"像不像"无关）: 正文一个字都没提那段时间的照样进来;
      · **无 `ts` 的不命中**（时间锚的哨兵纪律: 不知道是哪天的不许冒充"落在这段时间里"）;
      · ⛔ **不放宽**（用户 2026-10-12: *"可以让 LLM 干脆自己多开区间搜"*）——
        「前天」的 `wide` 是 ±2 天, 那条 10/8 的经历**不许**被摆出来。
    """
    store = _store(tmp_path)
    for title, text, ts in (("上周的事", "我把箱子搬去了仓库", "2026-10-07T10:00:00"),
                            ("很久以前", "在杂草屋蹲了一下午", "2026-09-20T10:00:00"),
                            ("没日期的", "流水账", ""),
                            # ⚠️ 这条在**今天**（10/12）: 不属于上周, 但落在「前天」的 `wide`
                            # 里（10/10 ± 2 天 = 10/8..10/12 ⇒ 放宽的话它会被摆出来）。
                            ("今天的事", "搬箱子那天", "2026-10-12T09:00:00")):
        store.add(make_node("episode", text=text, title=title, ts=ts, significance=0.5))
    store.save()
    got = [c.node.title for c in modes.recall(store, _ctx("上周那个箱子呢"), mode="when")]
    assert got == ["上周的事"], got          # 10/12 那条不在上周里 ⇒ 不许混进来
    # 单日窗口（前天 = 10/10）: 今天那条**落在 `wide` 里** —— 不放宽 ⇒ 一条都没有
    assert modes.recall(store, _ctx("前天那个箱子呢"), mode="when") == []
    # 没时间词 ⇒ 空（不猜、不拿最近一条凑）
    assert modes.recall(store, _ctx("那个箱子呢"), mode="when") == []
    # 空手: 钥匙扫到了、那阵子真没有 ⇒ 印那句
    empty = modes.render_section([], mode="when", key="前天")
    assert empty.startswith("【你想着「前天」那阵子") and "一时没想起来" in empty, empty
    print("    modes: `when` = 区间全量（含正文无时间词的）· 不放宽 · 无 ts 不命中")


def test_emptied_by_dedup_is_not_a_blank_line(tmp_path):
    """⑭ ⛔ **"被别的段拿走了"不是"没想起来"** —— `empty_ok=False` 时一个字都不印。

    没有这一格就会说假话: 名字段先摆走了那条, 时间窗那段便空了 ⇒ 空手文案会说
    "那几天的事，一时没想起来" —— 可她**想起来了**, 就在上一段里。
    """
    store = _store(tmp_path)
    _seed_aru(store)
    cands = modes.recall(store, _ctx("阿露"), mode="name")
    assert cands, "先得有货, 否则两边都是空手（假绿）"
    assert modes.render_section([], mode="name", key="阿露")              # 真·空手 ⇒ 印
    assert modes.render_section([], mode="name", key="阿露", empty_ok=False) == ""
    print("    modes: 去重掏空 ≠ 空手（`empty_ok=False` 一个字都不印）")


def test_the_blank_line_needs_a_key(tmp_path):
    """⑫ ⭐ **空手**的收放: 有钥匙 ⇒ 印; 没钥匙 ⇒ 不印; 模板带槽而没钥匙 ⇒ **当场炸**。"""
    store = _store(tmp_path)
    _seed_aru(store)
    empty = modes.render_section([], mode="name", key="阿露")
    assert empty.startswith("【你想着「阿露」") and "一时没想起来" in empty, empty
    # 没钥匙（普通闲聊）⇒ 空手也不印
    assert modes.render_section([], mode="name") == ""
    # 有货但模板带槽、钥匙没给 ⇒ 不印半成品（`{key}` 四个字符不许进她的视图）
    cands = modes.recall(store, _ctx("阿露"), mode="name")
    with pytest.raises(ValueError):
        modes.render_section(cands, mode="name")
    print("    modes: 空手要钥匙; 带槽不填当场炸")
