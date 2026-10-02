"""render.py 渲染视图测试（AGENT_BRAIN.md §4 / M2）。

组织视图的节点必须带 id（真实流程由 store.add 分配）——测试用 _ids 助手分配。
角色视图不依赖 id（渲染中从不出现）。
"""
from datetime import datetime, timedelta

from core.brain import make_node
from core.brain.graph import Edge, Graph
from core.brain.render import render_character_view, render_organize_view


def _ids(nodes):
    """按序分配 id（m0001, m0002, …）——模拟 store.add 的分配。"""
    for i, n in enumerate(nodes, 1):
        n.id = f"m{i:04d}"
    return nodes


def _g(*triples) -> Graph:
    """手工边表（G3 起边住在 `edges.jsonl`，不在节点字段里）。

    三元组 = `(rel, src, dst)`；渲染只查邻居, 所以不给 nodes 也够用。
    """
    return Graph(edges=[Edge(rel=r, src=s, dst=d) for r, s, d in triples])


def _ep(text, sig=0.5, ts="", verbatim="", event_seq=None, observer=""):
    """⚠️ `observer` 默认**空** = 亲历（2026-09-29 起"是不是听说的"就靠它判 ——
    从前这里默认填角色自己的 id, 那是靠 `epistemic` 分桶时代留下的无害噪音）。"""
    kw = dict(text=text, significance=sig, ts=ts, observer=observer)
    if verbatim:
        kw["verbatim"] = verbatim
    if event_seq:
        kw["event_seq"] = event_seq
    return make_node("episode", **kw)


# ---------------------------------------------------------------------------
# 组织视图
# ---------------------------------------------------------------------------

def test_organize_view_episode_line():
    n = _ep("天台夜谈", sig=0.8, verbatim="地砖里长出的苔藓也可以是花",
            event_seq=[42])
    out = render_organize_view(_ids([n]), graph=_g(("supports", "m0001", "m0009")))
    assert "m0001 [episode, sig 0.80, edges: supports→m0009] 天台夜谈" in out
    assert "〝「地砖里长出的苔藓也可以是花」〞" in out
    assert not out.lstrip().startswith("#")        # 决策 #7: 无 # 前缀
    # 不给边表 → **不印边**（不是印一个空的 `edges:` —— 那会读成"这条没有邻居"）
    assert "edges:" not in render_organize_view(_ids([n]))


def test_organize_view_experience_and_player():
    exp = make_node("experience", text="提到工作繁忙", subject="sensei",
                    significance=0.7, examples=["「这周又忙成狗了」"], event_seq=[61])
    pe = make_node("experience", text="总说「摸鱼」", subject="player",
                   significance=0.75, examples=["今天也摸鱼"], event_seq=[70])
    nodes = _ids([exp, pe])
    # count（G3 起）= `supports` **入边数**，不再读节点字段
    g = _g(("supports", "m0011", "m0001"), ("supports", "m0015", "m0001"),
           ("supports", "m0020", "m0001"),
           ("supports", "m0030", "m0002"), ("supports", "m0033", "m0002"))
    out = render_organize_view(nodes, graph=g)
    # ⭐ 2026-09-25（§5.1）: 标记按 **kind** —— `experience` 就是"关于老师的事",
    # `subject` 写歪了也照印（旧口径按 subject 路由 ⇒ 真机 haruka e0001 静默消失）
    assert "m0001 [experience·关于老师, sig 0.70, count 3" in out
    assert "〝「「这周又忙成狗了」」〞" not in out            # 已带「」不重复包裹
    assert "〝「「今天也摸鱼」」〞" not in out
    assert "〝「今天也摸鱼」〞" in out
    assert "m0002 [experience·关于老师, sig 0.75, count 2" in out        # §4.4 标记


def test_organize_view_episode_belief():
    ep = make_node("episode", text="遥香曾因拆炸弹事件对 sensei 建立信任",
                   significance=0.95)
    belief = make_node("belief", text="老师是第一个不会嫌弃我的人", subject="sensei",
                       epistemic="inferred_belief", significance=0.9, event_seq=[42])
    nodes = _ids([ep, belief])
    out = render_organize_view(nodes, graph=_g(("supports", "m0001", "m0002")))
    assert "[episode, sig 0.95, edges: supports→m0002]" in out
    # 入边印成 `supports←m0001`（"这条看法是谁支撑的"一眼可读 —— 旧版只有无类型的 links:）
    assert "[belief, sig 0.90, edges: supports←m0001]" in out
    # ⏸ 原 "canon 只读" 标记 2026-09-21 删（is_seed()/source 退役）——不该再出现
    assert "canon" not in out


def test_organize_view_contradiction_marker():
    nodes = _ids([_ep("雨天散步", event_seq=[1]), _ep("讨厌下雨", event_seq=[2])])
    out = render_organize_view(nodes, graph=_g(("contradicts", "m0001", "m0002")))
    assert "contradicts→m0002" in out          # a 侧: 出边
    assert "contradicts←m0001" in out          # b 侧: 入边


def test_organize_view_timeline_and_empty():
    n = _ep("x", event_seq=[1])
    out = render_organize_view(_ids([n]), timeline="（旁白）放学后的教室。")
    assert out.startswith("【本次新经历】\n（旁白）放学后的教室。")
    assert "【相关旧记忆（供组织决策）】" in out
    # 无时间线 / 空节点
    assert "【本次新经历】" not in render_organize_view(_ids([n]))
    assert render_organize_view([]) == ""


# ---------------------------------------------------------------------------
# 角色视图
# ---------------------------------------------------------------------------

def test_character_view_sections_and_first_person():
    nodes = _ids([
        _ep("和老师拆炸弹那次，老师没有苛责我", sig=0.95, ts="2026-08-01T10:00:00",
            verbatim="没关系，我陪你拆完。", event_seq=[1]),
        _ep("老师带我去吃甜品", sig=0.6, ts="2026-09-01T20:00:00", event_seq=[2]),
        make_node("belief", text="伊草遥香开始相信自己被需要", subject="sensei",
                  epistemic="inferred_belief", significance=0.9,
                  growth="从自卑到被需要", event_seq=[1]),
        make_node("experience", text="总说「摸鱼」", subject="player",
                  significance=0.75, event_seq=[2]),
    ])
    # count（G3 起）= supports 入边数: 三条经历印证过这个口癖
    g = _g(("supports", "m0001", "m0004"), ("supports", "m0002", "m0004"),
           ("supports", "m0003", "m0004"))
    out = render_character_view(nodes, char_name="伊草遥香",
                                summary="天台夜谈后，伊草遥香开始相信自己被需要",
                                graph=g)
    assert out.startswith("【角色记忆（brain）】")
    assert "我记得那段日子：天台夜谈后，我开始相信自己被需要" in out
    # ⭐ **一条河（从早到晚）**（2026-09-25, 链路 ⑤）: 经历不再按"珍贵的/最近的"切两块;
    # `is_precious` 降级成**行内标记**（`（难忘）` / `（3 天前·难忘）`）。
    river = out.split("我记得的事（从早到晚）：\n")[1].split("\n\n")[0]
    assert "- 〔难忘〕和老师拆炸弹那次，老师没有苛责我（「没关系，我陪你拆完。」）" in river
    assert "- 老师带我去吃甜品" in river
    # 无 ts 的排河首、有 ts 的按时间在后（旧→新）
    assert river.index("拆炸弹") < river.index("吃甜品")
    assert "我心里渐渐觉得：\n- 对sensei：我开始相信自己被需要（——从自卑到被需要）" in out
    assert "老师的事：\n- 总说「摸鱼」（count 3）" in out
    # ⏸ 原"久远的记忆"段（出厂 episode）2026-09-21 删——出厂记忆不进 wiki;
    # knowledge 不再出厂化（无"我知道的事"段）
    assert "久远的记忆" not in out
    assert "我知道的事" not in out
    # 无 id / 无链接泄漏
    assert "m0001" not in out and "links" not in out


def test_character_view_no_caps_all_rendered():
    """2026-09-13 **cap 全删**：桶内全量注入（曾经 cap_recent 默认 6 / cap_beliefs 5）。

    这是"第 6 条 belief 永不出现 → 永不可能被 touch/update"那个冻结病的反面
    （DESIGN_WIKI_V3 §3.1/§3.7）——召回交给 v3 实体车道, 渲染不再先砍一刀。
    """
    nodes = [
        _ep("听睦月说阿露昨天又翻车了", sig=0.5, event_seq=[1],
            observer="asagi_mutsuki"),
        *(_ep(f"日常{i}", sig=0.4, ts=f"2026-09-0{1 + i % 9}T12:00:00",
              event_seq=[10 + i]) for i in range(12)),
    ]
    out = render_character_view(nodes)
    assert "我听说的：\n- 听睦月说阿露昨天又翻车了（听asagi_mutsuki说的）" in out
    assert "我记得的事（从早到晚）：" in out
    assert out.count("\n- 日常") == 12         # 12 条 observed 全部注入（旧 cap 6/10 会截断）
    # 空段省略
    out2 = render_character_view([])
    assert out2 == "【角色记忆（brain）】"
    assert "我心里渐渐觉得" not in out2


def test_character_view_belief_and_player_all_rendered():
    """belief / player 两桶同样全量（旧 cap_beliefs / cap_player 默认 5）。"""
    beliefs = [make_node("belief", text=f"信念{i}", subject="sensei",
                         epistemic="inferred_belief", significance=0.9 - i * 0.1,
                         event_seq=[1]) for i in range(7)]
    # 不给边表 ⇒ 计数恒 0（桶内排序退化为插入序）—— 那条轴不在这条用例的射程内,
    # 这条用例只管"桶内**全量**注入"（旧 cap 5 会丢两条）。
    players = [make_node("experience", text=f"口癖{i}", subject="player",
                         significance=0.6, event_seq=[1]) for i in range(7)]
    out = render_character_view([*beliefs, *players])
    assert out.count("\n- 对sensei：信念") == 7        # 7 条全在（旧 cap 5 会丢 2 条）
    assert out.count("（count ") == 7
    assert "信念5" in out and "口癖5" in out          # 旧 cap 下这两条正是被丢的


# ---------------------------------------------------------------------------
# 防失忆注记: episode 前置虚化时间短语（§3.8 / §4.11 的 T3）
# ---------------------------------------------------------------------------

#: 固定的"现在" —— 年龄全按**现实日**算（`ESSAY_TIME_MODEL §10`），
#: 故夹具不随真实日期漂。
_NOW = datetime(2026, 9, 17, 12, 0)


def _ts(days_ago: int) -> str:
    """`days_ago` 天前的 `ts`（现实日）。"""
    return (_NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")


def test_river_is_one_timeline_old_to_new():
    """⭐ 链路 ⑤（2026-09-25）: 经历是**一条河, 从早到晚**。

    从前按 `(珍贵, ts)` 降序 + 用 `is_precious` 切成「珍贵的」/「最近的事」两块 ⇒
    **同一个时刻的事被劈到两段里**, 读不出先后（真机 haruka: 「3 天前」既在珍贵的里
    又在最近的事里）。现在: 一条, 旧→新; 「难忘」只是**行内标记**。
    """
    nodes = [
        _ep("最早的事", sig=0.5, ts="2026-09-01T10:00:00", event_seq=[1]),
        _ep("中间的事（难忘）", sig=0.9, ts="2026-09-03T10:00:00", event_seq=[2]),
        _ep("最晚的事", sig=0.5, ts="2026-09-05T10:00:00", event_seq=[3]),
    ]
    out = render_character_view(nodes)
    river = out.split("我记得的事（从早到晚）：\n")[1]

    assert "珍贵的" not in out and "最近的事" not in out      # 两块合并了
    order = [river.index(t) for t in ("最早的事", "中间的事", "最晚的事")]
    assert order == sorted(order), river                      # 旧 → 新
    assert "- 〔难忘〕中间的事（难忘）" in river                # 无 now → 只剩标记
    assert "- 最早的事" in river and "- 最晚的事" in river


def test_river_marker_and_phrase_together():
    """`now` 给了 → 元信息段 = `《名》｜相对｜绝对｜难忘`（2026-09-29 定稿形态）。"""
    nodes = [_ep("难忘的那件", sig=0.9, event_seq=[1])]
    nodes[0].ts = _ts(3)
    out = render_character_view(nodes, now=_NOW)
    assert "- 〔3 天前｜9/14｜难忘〕难忘的那件" in out, out


def test_time_phrase_prefixed_and_vague():
    """★ 元信息段在**最前**（先看到远近再读内容），且**绝不出现精确值**。

    2026-09-17（`ESSAY_TIME_MODEL §10`）: 年龄按**现实日**算（`node.ts`）。
    2026-09-29（N5）: 旁边多一个**绝对日期**（引擎坐标）——两者都要（`PROCEED §2 #16`）。
    """
    nodes = [
        _ep("今天刚发生的事", sig=0.5, event_seq=[1]),
        _ep("前几天的事", sig=0.5, event_seq=[2]),
        _ep("三周前的事", sig=0.5, event_seq=[3]),
    ]
    nodes[0].ts = _ts(0)                    # age = 0 → 今天
    nodes[1].ts = _ts(2)                    # age = 2 → 2 天前
    nodes[2].ts = _ts(20)                   # age = 20 → 3 周前
    out = render_character_view(nodes, now=_NOW)
    assert "〔今天｜9/17〕今天刚发生的事" in out, out
    assert "〔2 天前｜9/15〕前几天的事" in out, out
    assert "〔3 周前｜8/28〕三周前的事" in out, out
    # I-c: **相对短语**里不得出现精确刻度/日期（绝对日期是引擎坐标, 不在此列）
    for bad in ("格", "分钟", "小时", "0 天", "sim_day"):
        assert bad not in out, f"短语里出现了精确形态: {bad}"
    assert "2026/9/17" not in out, "今年的日期不印年份（跨年才印）"
    print("    T3: 元信息前置 = 相对短语 + 绝对日期（虚化那条纪律不破）")


def test_time_phrase_absent_without_now():
    """不给 `now` → **完全不出现短语**（与本改动前逐字节相同）。"""
    nodes = [_ep("老师带我去吃甜品", sig=0.6, event_seq=[1])]
    nodes[0].ts = _ts(0)
    out = render_character_view(nodes)
    assert out == ("【角色记忆（brain）】\n\n我记得的事（从早到晚）：\n- 老师带我去吃甜品"), out
    print("    T3: 无 now → 零变化（旧调用方不受影响）")


def test_time_phrase_absent_for_unstamped_old_nodes():
    """★ 无 `ts`（空串，未采集）→ **不加短语**，不编"很久以前"。
    否则「未采集」与「真的很旧」混为一谈（哨兵纪律）。"""
    nodes = [_ep("旧档记忆", sig=0.6, event_seq=[1])]      # ts 缺省 = ""
    out = render_character_view(nodes, now=_NOW)
    assert "- 旧档记忆" in out
    assert "很久以前" not in out and "（" not in out.split("我记得的事（从早到晚）：")[1]
    print("    T3: 缺 ts 的节点不加短语（不编'很久以前'）")


def test_time_phrase_survives_bad_values():
    """坏 `ts` / 坏 `now` → 静默跳过，**渲染绝不因时间炸**。"""
    nodes = [_ep("坏值节点", sig=0.6, event_seq=[1])]
    nodes[0].ts = "坏值"                                   # 解析不出 → None
    assert "- 坏值节点" in render_character_view(nodes, now=_NOW)
    nodes[0].ts = _ts(0)
    assert "- 坏值节点" in render_character_view(nodes, now={"nope": 1})


# ---------------------------------------------------------------------------
# ⭐ N5: 标题进注入（地址地基）+「你想起的事」段（2026-09-29）
# ---------------------------------------------------------------------------

def _titled(text, title, **kw):
    return make_node("episode", text=text, title=title, **kw)


def test_episode_meta_head_shape():
    """⭐ 元信息段形态（2026-09-29 用户定稿）: `〔《事件名》｜多久以前｜日期｜难忘〕`。

    标题**第一个**（摘抄起点固定 —— `noticed` 与将来的 `look` 都从这一行抄名字）,
    字段之间是全角 `｜`（**不是 `·`**）、书名号标出事件名。
    """
    n = _titled("她拉着我在杂草屋蹲了一下午", "苔藓的约定", significance=0.6,
                event_seq=[1])
    n.ts = _ts(20)
    out = render_character_view([n], now=_NOW)
    assert "- 〔《苔藓的约定》｜3 周前｜8/28〕她拉着我在杂草屋蹲了一下午" in out, out
    # ⚠️ 分隔符纪律: 元信息里的字段分隔必须是 `｜` —— `·` 会出现在事件名里
    #（真机风格: "星空 · 夜空 · 黄昏"）, 用它当边界 ⇒ 她抄多抄少 ⇒ 查库静默落空
    head = out.splitlines()[-1].split("〕")[0]
    assert "·" not in head, f"元信息段里混进了 `·`: {head}"
    # 没标题的节点逐字不变（旧档/旧夹具零影响）
    assert "- 老师带我去吃甜品" in render_character_view([_ep("老师带我去吃甜品")])


def test_episode_meta_head_missing_fields():
    """⭐ **书名号在, 名字才在** —— 缺 `title` 的行不出名字段（`episode` 只必填 text）。

    所以规则是"照抄它的 `《…》`"（**按书名号找, 不按位置找**）:
    位置规则在缺字段的行上会让她把时间段当成事件名。
    """
    now = _NOW
    # 无标题 / 有时间
    n = _ep("无标题的一条", event_seq=[1])
    n.ts = _ts(2)
    assert "- 〔2 天前｜9/15〕无标题的一条" in render_character_view([n], now=now)
    # 只有标题（没 ts）→ 只剩名字那一段
    n2 = _titled("孤零零", "只剩名字", event_seq=[2])
    assert "- 〔《只剩名字》〕孤零零" in render_character_view([n2], now=now)
    # 一个字段都没有 → **整段不出现**（与本改动前逐字节相同）
    n3 = _ep("什么都没有", event_seq=[3])
    assert "- 什么都没有" in render_character_view([n3], now=now)
    assert "- 什么都没有" in render_character_view([n3])          # 无 now 同理


def test_episode_meta_head_absolute_date():
    """绝对日期 = **引擎坐标**（与相对短语两个都要, `PROCEED §2 #16`）; 跨年才印年份。"""
    n = _titled("去年的那天", "去年的事", event_seq=[1])
    n.ts = "2025-09-26T10:00:00"
    out = render_character_view([n], now=_NOW)
    assert "〔《去年的事》｜1 年前｜2025/9/26〕" in out, out
    # 坏 ts / 不给 now → 时间段不出现, 但**标题仍在**（地址不受时间影响）
    n2 = _titled("坏时间", "坏 ts 的那条", event_seq=[2])
    n2.ts = "坏值"
    assert "〔《坏 ts 的那条》〕坏时间" in render_character_view([n2], now=_NOW)
    n3 = _titled("没给 now", "没 now 的那条", event_seq=[3])
    n3.ts = _ts(1)
    assert "〔《没 now 的那条》〕没给 now" in render_character_view([n3])


def test_episode_title_is_never_first_person_converted():
    """⭐⭐ **标题是地址, 一律原样** —— 过了 `_me` 她就再也指不回库里那一条。

    这是本改动里最容易静默出错的一处: 正文转换（"遥香"→"我"）看起来"顺便也该
    转标题", 而后果是**每一次指认都落空**（她抄下来的串在库里不存在）。
    """
    n = _titled("遥香把伞留给了老师", "遥香的秘密", significance=0.6, event_seq=[1])
    out = render_character_view([n], char_name="伊草 遥香", char_aliases=("遥香",))
    assert "《遥香的秘密》" in out, out
    assert "《我的秘密》" not in out, out
    # 对照: 正文**照常**转换（别为了标题把正文那条纪律一起丢了）
    assert "我把伞留给了老师" in out, out


def test_recall_block_shape_and_budget():
    """「你想起的事」: 段头 + 只收 episode + 预算按行累积（**第一条永远留**）。"""
    from core.brain.render import RECALL_HEADER, render_recall_block

    e1 = _titled("她拉着我在杂草屋蹲了一下午", "苔藓的约定", event_seq=[1])
    e2 = _titled("屋顶的瓦片缝里也有", "屋顶的苔藓", event_seq=[2])
    e1.ts = e2.ts = _ts(7)
    belief = make_node("belief", text="我觉得老师很可靠", significance=0.9)

    out = render_recall_block([e1, e2, belief], now=_NOW, char_name="伊草 遥香")
    assert out.startswith(RECALL_HEADER)
    assert "《苔藓的约定》" in out and "《屋顶的苔藓》" in out
    assert "我觉得老师很可靠" not in out              # belief 不是"想起的事"
    assert "〔《苔藓的约定》｜7 天前｜9/10〕" in out    # 同一个 `_memory_line`（相对 + 绝对）

    # 预算是**装填停止条件**: 摆不下第二条 ⇒ 只摆第一条, 绝不截半条
    tight = render_recall_block([e1, e2], now=_NOW, budget=len(out.splitlines()[1]) + 2)
    assert "《苔藓的约定》" in tight and "《屋顶的苔藓》" not in tight
    # 一条都装不下（预算 0）→ 仍然给第一条（预算是闸门, 不是否决）
    assert "《苔藓的约定》" in render_recall_block([e1], now=_NOW, budget=0)

    # 空 / 只有非 episode → **不注入**（返回空串, 不返回一个空段头）
    assert render_recall_block([], now=_NOW) == ""
    assert render_recall_block([belief], now=_NOW) == ""


def test_recall_budget_reads_config_knob(monkeypatch):
    """预算的**真源**是 `[recall].turn_budget`（显式参数 > 配置 > 模块常量）。"""
    from core.brain import recall_config as rc
    from core.brain.render import render_recall_block

    e1 = _titled("第一件事", "一号", event_seq=[1])
    e2 = _titled("第二件事", "二号", event_seq=[2])
    monkeypatch.setattr(rc, "_cache", {"turn_budget": 1.0}, raising=False)
    out = render_recall_block([e1, e2])
    assert "《一号》" in out and "《二号》" not in out
    monkeypatch.setattr(rc, "_cache", {"turn_budget": 9999.0}, raising=False)
    out2 = render_recall_block([e1, e2])
    assert "《一号》" in out2 and "《二号》" in out2
    print("    T3: 坏 ts / 坏 now → 跳过短语, 不抛")
