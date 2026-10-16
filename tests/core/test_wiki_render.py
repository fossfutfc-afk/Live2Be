"""render.py 渲染视图测试。

组织视图的节点必须带 id（真实流程由 store.add 分配）——测试用 _ids 助手分配。
角色视图不依赖 id（渲染中从不出现）。
"""
import re
from datetime import datetime, timedelta

from core.brain import make_node
from core.brain.graph import Edge, Graph
from core.brain.read.render import KNOWN_NAMES_HEADER, render_character_view, render_organize_view


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
    ])
    # count（G3 起）= supports 入边数: 两条经历印证过这条看法
    g = _g(("supports", "m0001", "m0003"), ("supports", "m0002", "m0003"))
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
    # ⏸ 原「老师的事」（`profile` 桶 + `（count N）`）2026-10-14 随那个 kind 删 ——
    # 判据: 那一块**永远空**（没有写者, 也没有 kind）。
    assert "老师的事" not in out
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


def test_character_view_belief_all_rendered():
    """belief 桶同样全量（旧 cap_beliefs 默认 5）。

    ⏸ 原来还并着 `player` 桶（7 条 `profile`）—— 2026-10-14 随那个 kind 删。
    """
    beliefs = [make_node("belief", text=f"信念{i}", subject="sensei",
                         epistemic="inferred_belief", significance=0.9 - i * 0.1,
                         event_seq=[1]) for i in range(7)]
    out = render_character_view(beliefs)
    assert out.count("\n- 对sensei：信念") == 7        # 7 条全在（旧 cap 5 会丢 2 条）
    assert "信念5" in out                             # 旧 cap 下这条正是被丢的


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
    """「你想起的事」: 段头 + 预算按行累积（**第一条永远留**）。

    ⚠️ 入参是**候选**（`pack.Candidate`, `like` 的产物）—— 2026-10-08 起渲染层收候选,
    不再收"摊平成一串的裸节点"（那个转手是旧件留下的）。
    """
    from core.brain.read.pack import Candidate
    from core.brain.read.render import RECALL_HEADER, render_recall_block

    e1 = _titled("她拉着我在杂草屋蹲了一下午", "苔藓的约定", event_seq=[1])
    e2 = _titled("屋顶的瓦片缝里也有", "屋顶的苔藓", event_seq=[2])
    e1.ts = e2.ts = _ts(7)
    c1, c2 = Candidate(node=e1), Candidate(node=e2)

    out = render_recall_block([c1, c2], now=_NOW, char_name="伊草 遥香")
    assert out.startswith(RECALL_HEADER)
    assert "《苔藓的约定》" in out and "《屋顶的苔藓》" in out
    assert "〔《苔藓的约定》｜7 天前｜9/10〕" in out    # 同一个 `_memory_line`（相对 + 绝对）

    # 预算是**装填停止条件**: 摆不下第二条 ⇒ 只摆第一条, 绝不截半条
    tight = render_recall_block([c1, c2], now=_NOW, budget=len(out.splitlines()[1]) + 2)
    assert "《苔藓的约定》" in tight and "《屋顶的苔藓》" not in tight
    # 一条都装不下（预算 0）→ 仍然给第一条（预算是闸门, 不是否决）
    assert "《苔藓的约定》" in render_recall_block([c1], now=_NOW, budget=0)

    # 空 → **不注入**（返回空串, 不返回一个空段头）
    assert render_recall_block([], now=_NOW) == ""


def test_render_candidates_does_not_pick_the_surface():
    """⭐ **渲染层不选面** —— 给什么印什么（选面归档位: `SPECS[…].kinds`, 见 `test_read_like`）。

    为什么单列一条: 从前这里有一句 `kind == "episode"`, 那是**第二个真源**; 将来 `look`
    想摆 belief / entity 时会被它**静默吃掉**（渲染器不报错, 只是那一条不出现 ——
    最难查的一类空）。
    """
    from core.brain.read.pack import Candidate
    from core.brain.read.render import render_candidates

    ep = _titled("她拉着我在杂草屋蹲了一下午", "苔藓的约定", event_seq=[1])
    belief = make_node("belief", text="我觉得老师很可靠", title="老师很可靠")
    out = render_candidates([Candidate(node=ep), Candidate(node=belief)],
                            header="【你查到的事】")
    assert "《苔藓的约定》" in out and "《老师很可靠》" in out


def test_render_candidates_takes_its_own_header_and_hint():
    """段头/段尾是**参数** —— 同一个身体, P19 与将来的 `look` 各说各的话。"""
    from core.brain.read.pack import Candidate
    from core.brain.read.render import RECALL_ACTION_HINT, render_candidates

    ep = _titled("她拉着我在杂草屋蹲了一下午", "苔藓的约定", event_seq=[1])
    c = Candidate(node=ep)
    body = render_candidates([c], header="【你查到的事】")
    assert body.startswith("【你查到的事】\n")
    assert not body.endswith("\n")                    # 没有段尾 ⇒ 不留一个尾换行
    assert RECALL_ACTION_HINT not in body             # 不套 P19 的文案
    with_hint = render_candidates([c], header="【你查到的事】", hint="（就这些。）")
    assert with_hint.endswith("\n（就这些。）")
    print("    render_candidates: 段头/段尾由调用方给（look 复用同一支）")


def test_render_cap_is_exclusive_with_the_char_budget():
    """⭐ `cap`（条数）与 `budget`（字符）**互斥, cap 优先**。

    叠加的后果是"说好 5 条却只给 2 条", 而调用方**数不出**"还有几条"（被预算砍掉的
    算不算"还有"? 没有答案）—— 所以两个都给时只认 `cap`。
    """
    from core.brain.read.pack import Candidate
    from core.brain.read.render import render_candidates

    cands = [Candidate(node=_titled(f"第 {i} 件事", f"标题{i}", event_seq=[i]))
             for i in range(1, 4)]
    assert render_candidates(cands, header="【x】", cap=2).count("\n- ") == 2
    # ⚠️ 字符预算小到"一条都装不下", 但 cap 在场 ⇒ 预算被跳过 ⇒ 三条都在
    assert render_candidates(cands, header="【x】", cap=3, budget=1).count("\n- ") == 3
    print("    render: cap 与 budget 互斥（cap 优先）")


def test_look_copy_is_her_own_words_not_engine_coordinates():
    """`look` 的段头/段尾: **回显她的原话**、⛔ 不印编号、⛔ 不印我们算的日期。

    ⚠️ **三个筛选轴都回显**（2026-10-12 加 `entity`）—— 且实参一律用**关键字**
    （它们全是字符串, 位置调用一旦顺序改了就是静默串位）。
    """
    from core.brain.read.render import look_header, look_hint

    head = look_header(clue="苔藓 && 杂草", when="上周", n=2)
    assert head == "【你翻到的（「苔藓 && 杂草」 · 上周 · 2 条）】", head
    assert "m00" not in head and "2026" not in head
    # ⭐ 人名**不加引号**（那不是"她引的原话", 是她要筛的人）
    with_who = look_header(entity="阿露", clue="便利屋", when="上周", n=2)
    assert with_who == "【你翻到的（阿露 · 「便利屋」 · 上周 · 2 条）】", with_who
    wide = look_header(clue="苔藓", when="上周", n=2, widened=True)
    assert "那阵子没有；前后那阵子有 2 条" in wide
    assert look_hint(5, 3).endswith("还有 3 条同类的事。）")
    assert look_hint(2) == "（就这些。）"
    print("    look 文案: 回显原话与要筛的人 / 如实报边界 / 不印编号与日期")


def test_known_names_block_prints_every_entity(tmp_path):
    """⭐ **我知道的名字**（2026-10-12, 用户裁"合并 + 保留号都收"）: **全体 entity 都上表**。

    2026-10-08 的口径是"`entity.text` 非空才印"（原「我眼里的他们」）⇒ 只有名字、
    还没长出看法的对象**不进任何桶**、在图里完全隐形（真机 `老师`/`杂草屋`/`夏莱`
    三条都看不见）。而这一格正是她的**键面**: `look(entity=…)` 与 P19 的 `name` 段
    用的都是同一张面（`entities.surface_forms`）。
    ⚠️ 位置: 紧接"我记得的事"之后、belief 之前（先发生了什么 → 他们是谁 → 我想明白了什么）。
    ⛔ **别名不上屏**（用户同日裁"臃肿"）—— 别名照旧在匹配面里, 只是不印。
    ⭐ **她自己在表尾**（原「我是这样看自己的」那一格并了进来 —— 见下一条用例）。
    """
    stances = make_node("entity", name="陆八魔 阿露", text="阿露大人是我所处社团的社长")
    stances.aliases = ["阿露"]
    blank = make_node("entity", name="杂草屋")            # 没立场 ⇒ 光一个名字, **照样上表**
    self_node = make_node("entity", name="伊草 遥香", text="我是一株植物")
    self_node.id = "x0000"
    ep = _ep("天台夜谈", event_seq=[1])

    txt = render_character_view([stances, blank, self_node, ep], char_name="伊草 遥香")
    assert "我知道的名字（想起谁、翻谁的事，都用这些叫法）：" in txt
    assert "- 陆八魔 阿露：阿露大人是我所处社团的社长" in txt
    assert "- 杂草屋" in txt                               # ⭐ 没立场的也上表（旧口径不印）
    assert "（阿露" not in txt                             # ⛔ 别名不上屏
    rows = txt.split("我知道的名字（想起谁、翻谁的事，都用这些叫法）：\n")[1].split("\n\n")[0]
    assert rows.splitlines()[-1].startswith("- 伊草 遥香：")   # ⭐ 她在表尾
    assert "我是这样看自己的" not in txt                    # 那一格已并进来, 不再单开
    # 位置: 河之后、belief 之前
    belief = make_node("belief", text="老师是值得信赖的")
    txt2 = render_character_view([stances, ep, belief], char_name="伊草 遥香")
    assert txt2.index("我记得的事") < txt2.index("我知道的名字") < txt2.index("我心里渐渐觉得")
    print("    C: 「我知道的名字」—— 全体上表（含只有名字的）/ 别名不上屏 / 她在表尾")


def test_known_names_rows_are_names_not_ids(tmp_path):
    """⭐ 名表每一行的形状 = `- 主名` 或 `- 主名：看法`（用户 2026-10-12 裁"只写主名"）。

    四条"不许"一次钉住（每条都能静默破坏这张表的用途 —— 它是**键面**, 她要照抄）:
      · ⛔ **别名不上屏**（同一份写法进两遍是臃肿; 别名照旧在匹配面里）;
      · ⛔ **编号不进她的视图**（`x0002` 是引擎内部地址, 抄了永远指不中）;
      · ⛔ **行里不许出现 `【】`**（段头只在块首, 混进行里会让"段"读不出来）;
      · ⛔ **不许空标题**（`- ：看法` 那种 —— 名字是这一行的全部意义）。
    """
    person = make_node("entity", name="陆八魔 阿露", text="社长")
    person.aliases = ["阿露", "Rikuhachima Aru"]
    blank = make_node("entity", name="杂草屋")             # 没看法 ⇒ 光名字
    me = make_node("entity", name="伊草 遥香", text="我是一株植物")
    me.id = "x0000"
    txt = render_character_view([person, blank, me], char_name="伊草 遥香")
    rows = txt.split(KNOWN_NAMES_HEADER + "\n")[1].split("\n\n")[0].splitlines()
    assert len(rows) == 3, rows
    for ln in rows:
        assert ln.startswith("- "), ln
        body = ln[2:]
        name = body.split("：")[0]
        assert name.strip(), ln                                # ⛔ 空标题
        assert not re.search(r"[emx]\d{4}", ln), ln            # ⛔ 编号
        assert "【" not in ln and "】" not in ln, ln            # ⛔ 段头混进行里
    # ⛔ 别名（主名之外的那些写法）一个字都不上屏
    assert "阿露" not in "".join(rows).replace("陆八魔 阿露", ""), rows
    assert "Rikuhachima" not in txt
    print("    C: 名表行 = `- 主名[：看法]`（无别名/无编号/无段头/无空标题）")


def test_self_row_is_the_last_line(tmp_path):
    """⭐ **她那一格在表尾**（用户 2026-10-12: *"她自己一格还是跟着放在这里吧"*）。

    原「我是这样看自己的」（2026-10-08 裁"单开一行"）**并进这张表** —— 同一份内容
    印两遍就是同一份东西两次进上下文。`x0000.text` = 她对自己的看法
    （出厂来自 `interperson.yml` 的 `self` 保留键, 之后 R3 继续演化）。
    """
    self_node = make_node("entity", name="伊草 遥香",
                          text="我也还是一株植物，可以一直长着，因为有人会来看我。")
    self_node.id = "x0000"
    other = make_node("entity", name="阿露", text="社长")

    txt = render_character_view([other, self_node], char_name="伊草 遥香")
    rows = txt.split("我知道的名字（想起谁、翻谁的事，都用这些叫法）：\n")[1].split("\n\n")[0]
    lines = rows.splitlines()
    assert lines[-1] == "- 伊草 遥香：我也还是一株植物，可以一直长着，因为有人会来看我。"
    assert lines[0] == "- 阿露：社长"                       # 别人按 id 序在前
    assert "我是这样看自己的" not in txt
    # 只有 self（没别人）⇒ 表里就她一行, 照样印
    only = render_character_view([self_node], char_name="伊草 遥香")
    assert "- 伊草 遥香：我也还是一株植物" in only
    # 连看法都没有 ⇒ 光名字一行（表里不出现空标题）
    blank_self = make_node("entity", name="伊草 遥香")
    blank_self.id = "x0000"
    txt3 = render_character_view([blank_self], char_name="遥香")
    assert txt3.splitlines()[-1] == "- 伊草 遥香"
    print("    C: 她那一格 = 表尾一行（有看法接 `：看法`, 没有就光名字）")


def test_known_bucket_lands_in_the_ledger(tmp_path):
    """台账: `known` 一格进账（与渲染同源 —— 台账要如实反映她看到了什么）。

    ⚠️ 判据是"**是 entity**"（不是"有立场"）⇒ 只有名字的对象也进账, 这才与上表一致;
    旧口径 `they` 只数有立场的, 于是"名单里有几条"在账上是看不见的。
    """
    from core.brain.read.render import take_last_view_account
    stances = make_node("entity", name="陆八魔 阿露", text="社长")
    blank = make_node("entity", name="杂草屋")
    self_node = make_node("entity", name="伊草 遥香", text="我是一株植物")
    self_node.id = "x0000"
    render_character_view([stances, blank, self_node], char_name="遥香")
    acct = take_last_view_account()
    assert acct["buckets"]["known"] == 3, acct["buckets"]
    assert "they" not in acct["buckets"] and "self_stance" not in acct["buckets"]
    print("    C: `known` 进账（含只有名字的 + 她自己）")


def test_recall_budget_reads_config_knob(recall_knobs):
    """预算的**真源**是 `[recall].turn_budget`（显式参数 > 配置 > 模块常量）。"""
    from core.brain import recall_config as rc
    from core.brain.read.pack import Candidate
    from core.brain.read.render import render_recall_block

    e1 = _titled("第一件事", "一号", event_seq=[1])
    e2 = _titled("第二件事", "二号", event_seq=[2])
    cands = [Candidate(node=e1), Candidate(node=e2)]
    # ⚠️ 旋钮值要挑在**两条之间**: 10 < 两条总长 ≈ 24 ⇒ 只摆第一条; 100 ⇒ 两条都摆。
    # 用 1.0/9999.0 这种极端值测不出"预算被放大"（两条在两边都摆不下 / 都摆得下）。
    recall_knobs({"turn_budget": 10.0})
    out = render_recall_block(cands)
    assert "《一号》" in out and "《二号》" not in out
    recall_knobs({"turn_budget": 100.0})
    out2 = render_recall_block(cands)
    assert "《一号》" in out2 and "《二号》" in out2
    print("    T3: 坏 ts / 坏 now → 跳过短语, 不抛")
