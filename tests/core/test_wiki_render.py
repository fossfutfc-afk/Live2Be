"""render.py 渲染视图测试（AGENT_BRAIN.md §4 / M2）。

组织视图的节点必须带 id（真实流程由 store.add 分配）——测试用 _ids 助手分配。
角色视图不依赖 id（渲染中从不出现）。
"""
from datetime import datetime, timedelta

from core.brain.wiki_v2 import make_node
from core.brain.wiki_v2.render import render_character_view, render_organize_view


def _ids(nodes):
    """按序分配 id（m0001, m0002, …）——模拟 store.add 的分配。"""
    for i, n in enumerate(nodes, 1):
        n.id = f"m{i:04d}"
    return nodes


def _ep(narration, sig=0.5, ts="", verbatim="", links=None, epistemic="observed_fact",
        event_seq=None, observer="igusa_haruka"):
    kw = dict(narration=narration, significance=sig, ts=ts, observer=observer,
              epistemic=epistemic)
    if verbatim:
        kw["verbatim"] = verbatim
    if links:
        kw["links"] = links
    if event_seq:
        kw["event_seq"] = event_seq
    return make_node("episode", **kw)


# ---------------------------------------------------------------------------
# 组织视图
# ---------------------------------------------------------------------------

def test_organize_view_episode_line():
    n = _ep("天台夜谈", sig=0.8, verbatim="地砖里长出的苔藓也可以是花",
            links=["m0009"], event_seq=[42])
    out = render_organize_view(_ids([n]))
    assert "m0001 [episode, sig 0.80, links: m0009] 天台夜谈" in out
    assert "〝「地砖里长出的苔藓也可以是花」〞" in out
    assert not out.lstrip().startswith("#")        # 决策 #7: 无 # 前缀


def test_organize_view_experience_and_player():
    exp = make_node("experience", pattern="提到工作繁忙", subject="sensei",
                    significance=0.7, examples=["「这周又忙成狗了」"],
                    links=["m0011", "m0015", "m0020"], event_seq=[61])
    pe = make_node("experience", pattern="总说「摸鱼」", subject="player",
                   significance=0.75, examples=["今天也摸鱼"],
                   links=["m0030", "m0033"], event_seq=[70])
    out = render_organize_view(_ids([exp, pe]))
    # count 由引擎归一 = len(links)（normalize 不变量）
    assert "m0001 [experience, sig 0.70, count 3, links: m0011 m0015 m0020] 提到工作繁忙" in out
    assert "〝「「这周又忙成狗了」」〞" not in out            # 已带「」不重复包裹
    assert "〝「「今天也摸鱼」」〞" not in out
    assert "〝「今天也摸鱼」〞" in out
    assert "m0002 [experience·关于老师, sig 0.75, count 2" in out        # §4.4 标记


def test_organize_view_episode_belief():
    ep = make_node("episode", narration="遥香曾因拆炸弹事件对 sensei 建立信任",
                   significance=0.95)
    belief = make_node("belief", content="老师是第一个不会嫌弃我的人", subject="sensei",
                       epistemic="inferred_belief", significance=0.9,
                       links=["m0001"], event_seq=[42])
    out = render_organize_view(_ids([ep, belief]))
    assert "[episode, sig 0.95]" in out
    assert "[belief, sig 0.90, links: m0001]" in out
    # ⏸ 原 "canon 只读" 标记 2026-09-21 删（is_seed()/source 退役）——不该再出现
    assert "canon" not in out


def test_organize_view_contradiction_marker():
    a = _ep("雨天散步", event_seq=[1])
    b = _ep("讨厌下雨", event_seq=[2])
    b.contradictions = ["m0001"]
    out = render_organize_view(_ids([a, b]))
    assert "c: m0001" in out


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
    nodes = [
        _ep("和老师拆炸弹那次，老师没有苛责我", sig=0.95, ts="2026-08-01T10:00:00",
            verbatim="没关系，我陪你拆完。", event_seq=[1]),
        _ep("老师带我去吃甜品", sig=0.6, ts="2026-09-01T20:00:00", event_seq=[2]),
        make_node("belief", content="伊草遥香开始相信自己被需要", subject="sensei",
                  epistemic="inferred_belief", significance=0.9,
                  growth="从自卑到被需要", links=["m0001"], event_seq=[1]),
        make_node("experience", pattern="总说「摸鱼」", subject="player",
                  significance=0.75, links=["m0002", "m0003", "m0004"], event_seq=[2]),
    ]
    out = render_character_view(nodes, char_name="伊草遥香",
                                summary="天台夜谈后，伊草遥香开始相信自己被需要")
    assert out.startswith("【角色记忆（brain）】")
    assert "我记得那段日子：天台夜谈后，我开始相信自己被需要" in out
    assert "我记得的事（珍贵的）：" in out
    assert "和老师拆炸弹那次，老师没有苛责我（「没关系，我陪你拆完。」）" in out
    assert "最近的事：\n- 老师带我去吃甜品" in out
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
            epistemic="reported_fact", observer="asagi_mutsuki"),
        *(_ep(f"日常{i}", sig=0.4, ts=f"2026-09-0{1 + i % 9}T12:00:00",
              event_seq=[10 + i]) for i in range(12)),
    ]
    out = render_character_view(nodes)
    assert "我听说的：\n- 听睦月说阿露昨天又翻车了（听asagi_mutsuki说的）" in out
    assert "最近的事：" in out
    assert out.count("\n- 日常") == 12         # 12 条 observed 全部注入（旧 cap 6/10 会截断）
    # 空段省略
    out2 = render_character_view([])
    assert out2 == "【角色记忆（brain）】"
    assert "我心里渐渐觉得" not in out2


def test_character_view_belief_and_player_all_rendered():
    """belief / player 两桶同样全量（旧 cap_beliefs / cap_player 默认 5）。"""
    beliefs = [make_node("belief", content=f"信念{i}", subject="sensei",
                         epistemic="inferred_belief", significance=0.9 - i * 0.1,
                         links=["m0001"], event_seq=[1]) for i in range(7)]
    players = [make_node("experience", pattern=f"口癖{i}", subject="player",
                         significance=0.6, count=7 - i, links=["m0001"],
                         event_seq=[1]) for i in range(7)]
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


def test_time_phrase_prefixed_and_vague():
    """★ 短语挂在**最前**（先看到远近再读内容），且**绝不出现精确值**。

    2026-09-17（`ESSAY_TIME_MODEL §10`）: 年龄按**现实日**算（`node.ts`）。
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
    assert "（今天）今天刚发生的事" in out, out
    assert "（2 天前）前几天的事" in out, out
    assert "（3 周前）三周前的事" in out, out
    # I-c: 不得出现精确日/周数以外的刻度、不得出现日期
    for bad in ("格", "分钟", "小时", "0 天", "年-", "sim_day"):
        assert bad not in out, f"短语里出现了精确形态: {bad}"
    print("    T3: 短语前置且虚化（今天/2 天前/3 周前）")


def test_time_phrase_absent_without_now():
    """不给 `now` → **完全不出现短语**（与本改动前逐字节相同）。"""
    nodes = [_ep("老师带我去吃甜品", sig=0.6, event_seq=[1])]
    nodes[0].ts = _ts(0)
    out = render_character_view(nodes)
    assert out == ("【角色记忆（brain）】\n\n最近的事：\n- 老师带我去吃甜品"), out
    print("    T3: 无 now → 零变化（旧调用方不受影响）")


def test_time_phrase_absent_for_unstamped_old_nodes():
    """★ 无 `ts`（空串，未采集）→ **不加短语**，不编"很久以前"。
    否则「未采集」与「真的很旧」混为一谈（哨兵纪律）。"""
    nodes = [_ep("旧档记忆", sig=0.6, event_seq=[1])]      # ts 缺省 = ""
    out = render_character_view(nodes, now=_NOW)
    assert "- 旧档记忆" in out
    assert "很久以前" not in out and "（" not in out.split("最近的事：")[1]
    print("    T3: 缺 ts 的节点不加短语（不编'很久以前'）")


def test_time_phrase_survives_bad_values():
    """坏 `ts` / 坏 `now` → 静默跳过，**渲染绝不因时间炸**。"""
    nodes = [_ep("坏值节点", sig=0.6, event_seq=[1])]
    nodes[0].ts = "坏值"                                   # 解析不出 → None
    assert "- 坏值节点" in render_character_view(nodes, now=_NOW)
    nodes[0].ts = _ts(0)
    assert "- 坏值节点" in render_character_view(nodes, now={"nope": 1})
    print("    T3: 坏 ts / 坏 now → 跳过短语, 不抛")
