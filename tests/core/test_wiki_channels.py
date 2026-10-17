"""召回链路接口单测（V3-3 前置）。

钉住的不是"打分对不对"（公式还没定），而是**形态契约**：
  1. 五条链路都登记、元数据齐全、种类合法
  2. **缺数据 → raw=None + degraded=True + 有 note**, 绝不编分
  3. 接口是纯的、只读 store
  4. 唯一的 pairwise 链路（D）不把"关系量"写成节点属性
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

from core.brain import (
    CHANNELS,
    KIND_GATE,
    KIND_PRIOR,
    KIND_SIMILARITY,
    PLANNED,
    Channel,
    RecallContext,
    WikiStoreV2,
    describe_channels,
    get_channel,
    make_node,
)
from core.brain.read.channels import KINDS
from core.brain.read.scale import SCALES


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="w1", char_id="c")
    st.add(make_node("episode", text="老师陪我在杂草屋看苔藓",
                     significance=0.9, emo_span=0.9, emo_int=0.85,
                     event_seq=[14]))
    st.add(make_node("episode", text="误发短信把老师叫到现场",
                     significance=0.6, emo_span=0.5, emo_int=0.8,
                     event_seq=[30]))
    return st


def _ctx(**kw) -> RecallContext:
    base = dict(now=None, query="她又想起那天的杂草屋", aff_now=None,
                place_now="", embed_fn=None, char_id="c")
    base.update(kw)
    return RecallContext(**base)


# ---------------------------------------------------------------------------
# 1. 登记与元数据
# ---------------------------------------------------------------------------

def test_all_channels_registered_with_valid_meta():
    rows = describe_channels()
    names = [r["name"] for r in rows]
    assert names == list(CHANNELS), f"登记表与实现不一致: {names} vs {CHANNELS}"
    for r in rows:
        assert r["kind"] in KINDS, f"{r['name']} 非法 kind {r['kind']}"
        assert r["scale"] in SCALES, f"{r['name']} 非法 scale {r['scale']}"
        assert r["unit"], f"{r['name']} 缺 unit（台账要可读）"
    print(f"    channels: {len(rows)} 条链路元数据齐全")
    for r in rows:
        print(f"      {r['name']:<16} {r['kind']:<11} {r['scale']:<7} "
              f"{r['unit']:<10} {r['status']}")


def test_channel_protocol_conformance():
    for name in CHANNELS:
        ch = get_channel(name)
        assert isinstance(ch, Channel), f"{name} 不满足 Channel 协议"
    print("    channels: 全部满足 Channel 协议")


def test_get_unknown_channel_raises():
    try:
        get_channel("Z_not_a_channel")
    except KeyError as e:
        assert "未知召回链路" in str(e)
        print("    channels: 未知链路 → KeyError（不静默返回空）")
        return
    raise AssertionError("未知链路应 KeyError")


def test_kind_taxonomy_covers_five():
    """三类 kind 各有归属——A 是 PRIOR, C 是 GATE, B/D/E 是 SIMILARITY。"""
    kinds = {r["name"]: r["kind"] for r in describe_channels()}
    assert kinds["A_intensity"] == KIND_PRIOR
    assert kinds["C_place"] == KIND_GATE
    for n in ("B_emotion_rag", "D_deja_vu", "E_unconscious"):
        assert kinds[n] == KIND_SIMILARITY, n
    print("    channels: kind 分类正确（A=PRIOR / C=GATE / B,D,E=SIMILARITY）")


# ---------------------------------------------------------------------------
# 2. ★ 缺数据必须"诚实的空"——绝不编分
# ---------------------------------------------------------------------------

def test_missing_data_degrades_never_fabricates(tmp_path):
    """★ 本阶段的核心契约: 没有数据的链路必须 degraded + note, **不给分**。"""
    st = _store(tmp_path)
    ctx = _ctx()
    for name in CHANNELS:
        r = get_channel(name).gather(st, ctx)
        assert r.channel == name
        if r.degraded:
            assert r.note, f"{name} 降级了却没写原因"
            assert not r.hits, f"{name} 降级了却仍有命中（编分？）"
        print(f"    {name:<16} degraded={r.degraded!s:<5} hits={len(r.hits):<2} "
              f"note={r.note[:52]}")


def test_intensity_prior_scores_when_time_available(tmp_path):
    """★ A 出分: `det = SIG·TIME + span·int`, TIME 走 freshness(age, half_life)。

    2026-09-17（`ESSAY_TIME_MODEL §10`）: `age` 按**现实日**算（`node.ts`）。
    """
    now = datetime(2026, 9, 17, 12, 0)
    st = _store(tmp_path)
    # 两条 episode 都落在"今天" → age=0 → freshness=1
    for n in st.all():
        n.ts = now.isoformat(timespec="seconds")
    r = get_channel("A_intensity").gather(st, _ctx(now=now))
    assert not r.degraded, r.note
    assert len(r.hits) == 2 and all(h.raw is not None for h in r.hits)
    raws = [h.raw for h in r.hits]
    assert raws == sorted(raws, reverse=True) and [h.rank for h in r.hits] == [1, 2]
    # age=0 → TIME=1 → det = SIG + span*int
    for h in r.hits:
        d = h.detail
        assert abs(h.raw - (d["sig"] * d["time"] + d["span"] * d["int"])) < 1e-9
        assert d["time"] == 1.0 and d["age"] == 0
    print(f"    A: 出分 {len(r.hits)} 条 raws={[round(x, 3) for x in raws]} "
          f"knobs={r.knobs}")


def test_intensity_prior_decays_with_age(tmp_path):
    """★ 新鲜度真的衰减: 同一节点, now 越晚 det 越小（单位 = 现实日）。"""
    base = datetime(2026, 9, 17, 12, 0)
    st = _store(tmp_path)
    for n in st.all():
        n.ts = base.isoformat(timespec="seconds")
    vals = []
    for day in (0, 5, 15, 60):
        now = base + timedelta(days=day)               # age = day 现实日
        r = get_channel("A_intensity").gather(st, _ctx(now=now))
        vals.append(max(h.raw for h in r.hits))
    assert all(b < a for a, b in zip(vals, vals[1:])), vals
    print(f"    A: 新鲜度衰减 age=0/5/15/60 现实日 → {[round(v, 3) for v in vals]}")


def test_intensity_prior_degrades_without_clocks(tmp_path):
    """缺 now → 整条链路降级; 缺 `node.ts` → **该节点**降级, 其余照常。"""
    now = datetime(2026, 9, 17, 12, 0)
    st = _store(tmp_path)
    r0 = get_channel("A_intensity").gather(st, _ctx())
    assert r0.degraded and not r0.hits and "now" in r0.note
    # 只给其中一条 stamp
    nodes = list(st.all())
    nodes[0].ts = now.isoformat(timespec="seconds")
    r1 = get_channel("A_intensity").gather(st, _ctx(now=now))
    assert not r1.degraded
    assert len(r1.hits) == 2
    assert sum(1 for h in r1.hits if h.raw is None) == 1     # 缺 ts 那条
    assert r1.knobs["no_ts"] == 1
    print(f"    A: 缺 now → 整链降级; 缺 node.ts → 单条降级（{r1.knobs}）")


def test_intensity_prior_all_old_archive_degrades(tmp_path):
    """全部缺 `ts` → 降级而不是给一堆 0 分。"""
    st = _store(tmp_path)
    r = get_channel("A_intensity").gather(
        st, _ctx(now=datetime(2026, 9, 17, 12, 0)))
    assert r.degraded and not [h for h in r.hits if h.raw is not None]
    assert "ts" in r.note
    print(f"    A: 全部缺 ts → 降级（{r.note[:48]}）")


def test_emotion_rag_degrades_without_query_or_shape(tmp_path):
    """B 的三种降级理由（T15 起它**能出分**了, 但缺料仍必须诚实降级）。"""
    st = _store(tmp_path)
    # ① 没有当前情绪键序列
    r1 = get_channel("B_emotion_rag").gather(st, _ctx())
    assert r1.degraded and "emo_now" in r1.note
    # ② 有 emo_now, 但节点没有 emo_shape（旧档未物化）
    r2 = get_channel("B_emotion_rag").gather(
        st, _ctx(emo_now=("tease", "smile")))
    assert r2.degraded and "emo_shape" in r2.note
    assert r2.knobs["no_emo_shape"] == 2
    # ③ 有料但没向量后端
    st.get("m0001").emo_shape = ["tease", "smile"]
    st.get("m0002").emo_shape = ["outburst", "shout"]
    r3 = get_channel("B_emotion_rag").gather(
        st, _ctx(emo_now=("tease", "smile")))
    assert r3.degraded and "embed_fn" in r3.note
    print(f"    B: 三种降级分别说明 → ①{r1.note[:22]} ②{r2.note[:22]} ③{r3.note[:22]}")


def test_emotion_rag_scores_by_key_sequence(tmp_path):
    """★ B 出分: **键序列**的 cos（不是情绪数值, 不需要「键→唤醒度」表）。"""
    st = _store(tmp_path)
    st.get("m0001").emo_shape = ["tease", "smile", "smile"]
    st.get("m0002").emo_shape = ["outburst", "shout", "strive"]
    # 假向量: 键序列 → 三维（只按键的字符和, 与叙述内容无关）
    def emb(texts):
        out = []
        for t in texts:
            h = sum(ord(c) for c in t if c not in "情绪序列: ")
            out.append([float(h % 7), float(h % 11), 1.0])
        return out
    r = get_channel("B_emotion_rag").gather(
        st, _ctx(emo_now=("tease", "smile", "smile"), embed_fn=emb))
    assert not r.degraded and len(r.hits) == 2
    assert all(h.raw is not None for h in r.hits)
    # 自己跟自己那一板必须排第一（键序列完全相同 → cos=1）
    assert r.hits[0].node.id == "m0001" and abs(r.hits[0].raw - 1.0) < 1e-9
    assert r.hits[0].rank == 1 and r.hits[1].rank == 2
    # 只读键序列: 叙述/verbatim 不进向量文本（§2.3.1 撤回框: 混正文会塌陷空间）
    seen = []
    get_channel("B_emotion_rag").gather(
        st, _ctx(emo_now=("tease",), embed_fn=lambda ts: (seen.extend(ts), emb(ts))[1]))
    assert all("杂草屋" not in t for t in seen), seen
    assert all(t.startswith("情绪序列: ") for t in seen), seen
    print(f"    B: 键序列 cos 出分 → {[(h.node.id, round(h.raw, 3)) for h in r.hits]}")


def test_recall_side_fields_never_reach_llm(tmp_path):
    """★★ 用户 2026-09-15 裁决: `emo_shape` / `place_now` **不进 LLM 上下文**。

    它们是**召回侧信号**——参与排序与筛选, 不参与写作。这里钉死的是
    「节点级」那一半: `render_*`（唯一往 prompt 里塞节点文本的地方）
    不许输出这些字段, 哪怕它们是满的。

    2026-09-19 扩到**地点两轴**: 用户问 *"我为什么要把 key 字段给到 LLM 的记忆？
    喂给 llm 的时候我直接丢掉这个字段不就行了？"* —— 对, 而且**架构里已经这么做了**
    （`render.py` 的四个视图只读 text/verbatim/
    subject/growth/count/links/contradictions/significance/ts/observer）。
    ⏸ `examples` 2026-10-14 随 `profile` 删 —— 那一格已经不在节点上了。
    本用例把"已经这么做"从**假设**变成**被钉住的事实**。
    """
    from core.brain.read.render import render_character_view, render_cognition_list, render_organize_view
    st = _store(tmp_path)
    for n in st.all():
        n.emo_shape = ["outburst", "shout"]
        n.place = ["ruinschoolcorridor"]
        n.place_raw = ["WRITER_ORIGINAL_PHRASE"]
    view = render_character_view(st.all(), char_name="遥香")
    org = render_organize_view(st.all())
    cog = render_cognition_list(st)
    for text in (view, org, cog):
        assert "outburst" not in text and "shout" not in text, text
        for leak in ("emo_shape", "place_raw", "ruinschoolcorridor",
                     "WRITER_ORIGINAL_PHRASE"):
            assert leak not in text, f"{leak} 漏进了 LLM 上下文:\n{text}"
    # 反向确认: 这些视图确实渲染了节点（不是空串让断言假通过）
    assert "杂草屋" in view and "杂草屋" in org
    print("    ★ 召回侧字段隔离: emo_shape / place / place_raw 都不进三个渲染视图")


def test_place_gate_groups_by_place_key(tmp_path):
    """★ C 链路（M3, 2026-09-19）: 节点有了 `place` → **真的能分组了**。

    此前必然降级（*"BrainNode 无 place 字段…链路未通因为背景系统没搞好"*）。
    准入 = **键相等**（等值, 无阈值）。⚠️ 它只声称"**同一张图**"——
    键不是地名的双射（见 `test_place_gate_semantic_score_is_not_a_gate`）。

    （原先还有 `region` 轴 —— 2026-09-19 用户澄清 region *"基本没有太多作用，
    也不必落库"*, 已撤。）
    """
    st = _store(tmp_path)
    # ① 没给当前地点 → 降级
    r1 = get_channel("C_place").gather(st, _ctx())
    assert r1.degraded and "place_now" in r1.note
    # ② 给了 place_now, 但节点是 M3 之前物化的（没有 place/place_raw）→ 降级
    r2 = get_channel("C_place").gather(st, _ctx(place_now="classroom"))
    assert r2.degraded and "旧档" in r2.note
    assert r2.knobs.get("place_now") == "classroom"
    # ③ 节点带上地点 → 键相等命中
    ep = make_node("episode", text="在天台上看星星", significance=0.8,
                   place=["classroom", "school_rooftop"],
                   place_raw=["放学后的教室", "傍晚的学校天台"], event_seq=[40])
    st.add(ep)
    r3 = get_channel("C_place").gather(st, _ctx(place_now="school_rooftop"))
    assert not r3.degraded and [h.node.id for h in r3.hits] == [ep.id]
    assert r3.hits[0].detail["by"] == "same_image"
    # ④ 键不等 → **空手而归**（不编）
    r4 = get_channel("C_place").gather(st, _ctx(place_now="onsen"))
    assert not r4.hits and "无相关命中" in r4.note
    print("    C: 无坐标/旧档→降级; 键命中; 不沾→空手")


def test_place_gate_two_axis_fusion(tmp_path):
    """★ C 链路 = **两轴融合**（2026-09-20 用户定: *"混合策略…magic function，
    在 writer 词和 key 相似度都高的时候值高，反之一般"*）。

    形状 = 调和平均（`core/media/place_fuse.py`）: 一轴为零 ⇒ 分为 0。于是四条语义:

    | 情形 | 结果 |
    |---|---|
    | 同键 + 说法像 | 最高（`same_image`, `axes=2`） |
    | 同键 + 说法**字面完全不像** | **分 0 → 不出现在候选里**（形状自带, 不是闸门） |
    | **不同键 + 别名相交**（`天台` 家族）+ 说法像 | **捞回来了** ← 修掉的那条反向假阴性 |
    | 不同键 + 毫无字面关系 + 说法像 | 仍然不进（**语义轴不许单独放宽准入**） |
    """
    st = _store(tmp_path)
    # 两条记忆都用同一张图（`ruinschoolcorridor`）, 但叙事上是两个地方 ——
    # 表里那条 note 自己写着"也可以用做老屋子或者某种杂草秘密基地"
    st.add(make_node("episode", text="她在走廊废墟里找到我", significance=0.7,
                     place=["ruinschoolcorridor"], place_raw=["学校走廊废墟"],
                     event_seq=[50]))
    st.add(make_node("episode", text="杂草屋里的那盏灯", significance=0.8,
                     place=["ruinschoolcorridor"], place_raw=["深夜的杂草屋"],
                     event_seq=[52]))
    # 同地不同键: `rooftop` 与 `school_rooftop` **别名相交**（都叫"天台"）
    st.add(make_node("episode", text="天台上的风", significance=0.6,
                     place=["rooftop"], place_raw=["学校天台"], event_seq=[54]))

    def fake_embed(texts):                      # 字符集袋（确定性, 无需后端）
        vocab = sorted({ch for t in texts for ch in t})
        return [[1.0 if ch in t else 0.0 for ch in vocab] for t in texts]

    # ① 同键 + 同话 → 顶格; 同键但**一个字都不共** → 融合为 0（形状语义）
    r = get_channel("C_place").gather(
        st, _ctx(place_now="ruinschoolcorridor",
                 place_raw_now="学校走廊废墟", embed_fn=fake_embed))
    ids = [h.node.id for h in r.hits]
    assert len(ids) == 1, ids
    assert r.hits[0].node.place_raw == ["学校走廊废墟"], "同话的那条该在"
    assert r.hits[0].detail["same_image"] is True and r.hits[0].detail["axes"] == 2
    assert r.hits[0].raw == 1.0, r.hits[0].raw          # 两轴都满 → 1.0
    two = get_channel("C_place").gather(
        st, _ctx(place_now="ruinschoolcorridor",
                 place_raw_now="学校走廊废墟", embed_fn=fake_embed))
    weeds = [h for h in two.hits if h.node.place_raw == ["深夜的杂草屋"]]
    assert not weeds, ("同键但说法字面零重叠 → 调和平均给 0（'一轴为零 ⇒ 没关系'）"
                       "—— 这是**形状**的结果, 不是闸门: 真 embedder 下几乎是 0.x, 会留下")

    # ② 不同键但**字面同族** + 说法像 → 现在能捞回来（2026-09-19 记的那条假阴性）
    r2 = get_channel("C_place").gather(
        st, _ctx(place_now="school_rooftop", place_raw_now="学校天台",
                 embed_fn=fake_embed))
    ids2 = [h.node.id for h in r2.hits]
    assert ids2, "同地不同键该被召回 —— 2026-09-19 记的那条假阴性"
    h2 = r2.hits[0]
    assert h2.node.place == ["rooftop"] and h2.detail["same_image"] is False
    # ⚠️ 满分有两种来源: `rooftop` ⊆ `school_rooftop` 走 **token** 规则（不是 alias）
    assert h2.detail["key_sim_by"] == "token" and h2.detail["key_sim"] == 1.0, h2.detail

    # ②b 另一种来源: `building_roof_top` 与 `school_rooftop` **只有别名相交**（天台）
    st.add(make_node("episode", text="摩天大楼的楼顶", significance=0.5,
                     place=["building_roof_top"], place_raw=["学校天台"],
                     event_seq=[55]))
    r2b = get_channel("C_place").gather(
        st, _ctx(place_now="school_rooftop", place_raw_now="学校天台",
                 embed_fn=fake_embed))
    h2b = next(h for h in r2b.hits if h.node.place == ["building_roof_top"])
    assert h2b.detail["key_sim_by"] == "alias" and 0.3 <= h2b.detail["key_sim"] <= 0.4
    assert h2b.detail["same_image"] is False, "别名相交只声称'同族', 不是同一张图"

    # ③ 语义像但**键毫无字面关系** → 不进（语义轴不许单独放宽准入）
    st.add(make_node("episode", text="温泉里的雾", significance=0.5,
                     place=["onsen"], place_raw=["学校天台"], event_seq=[56]))
    r3 = get_channel("C_place").gather(
        st, _ctx(place_now="school_rooftop", place_raw_now="学校天台",
                 embed_fn=fake_embed))
    assert "onsen" not in [h.node.place[0] for h in r3.hits], r3.hits

    # ④ 无 embed_fn → 叙事轴缺席, `raw` 退回素材轴那一半（准入不受影响）
    r4 = get_channel("C_place").gather(
        st, _ctx(place_now="school_rooftop", place_raw_now="学校天台"))
    assert r4.hits and all(h.detail["axes"] == 1 for h in r4.hits)
    assert r4.hits[0].raw == 1.0, "同键在小轴缺席时 = 素材轴满分"
    assert "无 embed_fn" in r4.knobs["sem"]

    # ⑤ ⭐ **键未知 ≠ 键不符**（用户 2026-09-20: *"还是走单轴"*）——
    #    没有 `place` 键 = 素材轴**不可算** → `raw = sw`（`narrative_only`）,
    #    而不是被 `magic(s, 0) == 0` 判死。真档实测 `place` 键 0 条、只有
    #    `place_hint` ⇒ 不修这条路, C 在真档上**恒空手**。
    st.add(make_node("episode", text="杂草屋的第一次", significance=0.8,
                     place_raw=["深夜的杂草屋"], event_seq=[58]))   # **故意不给 place**
    r5 = get_channel("C_place").gather(
        st, _ctx(place_now="school_rooftop", place_raw_now="深夜的杂草屋",
                 embed_fn=fake_embed))
    h5 = next(h for h in r5.hits if h.node.event_seq == [58])
    assert h5.detail["by"] == "no_key" and h5.detail["axes"] == 1, h5.detail
    assert h5.raw > 0.0 and abs(h5.raw - 1.0) < 1e-9, h5.detail   # sem 满分（同一句话）
    assert h5.detail["same_image"] is False, "没有键就绝不能声称'同一张图'"
    assert r5.knobs["no_key"] >= 1, r5.knobs
    # 反向确认: **有键但不符**（③ 的 `onsen`）仍进不来 —— 防线没被这次放宽拆掉
    assert "onsen" not in [p for h in r5.hits for p in (h.node.place or [])], r5.hits
    print("    C 融合: 同键同话=1.0; 同键异话→0（形状）; 别名相交的异键捞回; "
          "无语义轴→只用素材轴; **无键→叙事轴单轴**")


def test_unconscious_is_declared_not_implemented(tmp_path):
    st = _store(tmp_path)
    r = get_channel("E_unconscious").gather(st, _ctx())
    assert r.degraded and r.note == PLANNED["E_unconscious"]
    print(f"    E: 未立项, 显式声明 → {r.note[:56]}")


# ---------------------------------------------------------------------------
# 3. D 是唯一能出分的链路 —— 且必须真的能出
# ---------------------------------------------------------------------------

def _fake_embed(texts: list[str]) -> list[list[float]]:
    """确定性假向量: 按字符做 hash → 三维（够测排序, 零依赖）。"""
    out = []
    for t in texts:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(t))
        out.append([float((h % 97) / 97), float((h % 89) / 89),
                    float((h % 83) / 83)])
    return out


def test_deja_vu_is_the_only_scoring_channel(tmp_path):
    st = _store(tmp_path)
    r = get_channel("D_deja_vu").gather(st, _ctx(embed_fn=_fake_embed))
    assert not r.degraded, f"D 应能出分: {r.note}"
    assert len(r.hits) == 2
    assert all(h.raw is not None for h in r.hits)
    # rank 从 1 起且按 raw 降序
    raws = [h.raw for h in r.hits]
    assert raws == sorted(raws, reverse=True)
    assert [h.rank for h in r.hits] == [1, 2]
    print(f"    D: 出分 {len(r.hits)} 条, 降序 rank 正确, "
          f"raws={[round(x, 3) for x in raws]}")


def test_deja_vu_degrades_without_embed(tmp_path):
    st = _store(tmp_path)
    r = get_channel("D_deja_vu").gather(st, _ctx())          # 无 embed_fn
    assert r.degraded and "embed_fn" in r.note and not r.hits
    print("    D: 无向量后端 → 降级（不词面兜底——那是 recall.py 的活）")


def test_channel_is_read_only(tmp_path):
    """链路只读 store: 召回前后节点序列化逐字节相同。"""
    st = _store(tmp_path)
    before = [n.to_json_line() for n in st.all()]
    for name in CHANNELS:
        get_channel(name).gather(st, _ctx(embed_fn=_fake_embed))
    after = [n.to_json_line() for n in st.all()]
    assert before == after, "链路改了节点（应只读）"
    print("    channels: 全部只读（召回前后节点逐字节相同）")


if __name__ == "__main__":
    import tempfile

    for fn in (test_all_channels_registered_with_valid_meta,
               test_channel_protocol_conformance,
               test_get_unknown_channel_raises,
               test_kind_taxonomy_covers_five,
               test_unconscious_is_declared_not_implemented):
        fn()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        for fn in (test_missing_data_degrades_never_fabricates,
                   test_intensity_prior_scores_when_time_available,
                   test_intensity_prior_decays_with_age,
                   test_intensity_prior_degrades_without_clocks,
                   test_intensity_prior_all_old_archive_degrades,
                   test_emotion_rag_reports_link_gap,
                   test_place_gate_needs_place_field,
                   test_unconscious_is_declared_not_implemented,
                   test_deja_vu_is_the_only_scoring_channel,
                   test_deja_vu_degrades_without_embed,
                   test_channel_is_read_only):
            fn(p)
    print("all channel tests passed")
