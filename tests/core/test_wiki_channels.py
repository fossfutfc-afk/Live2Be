# -*- coding: utf-8 -*-
"""召回链路接口单测（V3-3 前置）。

钉住的不是"打分对不对"（公式还没定），而是**形态契约**：
  1. 五条链路都登记、元数据齐全、种类合法
  2. **缺数据 → raw=None + degraded=True + 有 note**, 绝不编分
  3. 接口是纯的、只读 store
  4. 唯一的 pairwise 链路（D）不把"关系量"写成节点属性
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brain.wiki_v2 import (                       # noqa: E402
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
from core.brain.wiki_v2.channels import KINDS, SCALES   # noqa: E402


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="w1", char_id="c")
    st.add(make_node("episode", narration="老师陪我在杂草屋看苔藓",
                     significance=0.9, emo_span=0.9, emo_int=0.85,
                     emo_valence=0.7, event_seq=[14]))
    st.add(make_node("episode", narration="误发短信把老师叫到现场",
                     significance=0.6, emo_span=0.5, emo_int=0.8,
                     emo_valence=-0.6, event_seq=[30]))
    return st


def _ctx(**kw) -> RecallContext:
    base = dict(story_now=None, query="她又想起那天的杂草屋", aff_now=None,
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
    """★ A 出分: `det = SIG·TIME + span·int`, TIME 走 freshness(age, half_life)。"""
    from core.worldtime import StoryTime
    st = _store(tmp_path)
    # 两条 episode 都 stamp 到 sim_day=0; now 推到 sim_day=0 → age=0 → freshness=1
    for n in st.all():
        n.story_time = StoryTime.from_sim_day(0).to_dict()
    now = StoryTime.from_sim_day(0)
    r = get_channel("A_intensity").gather(st, _ctx(story_now=now))
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
    """★ 新鲜度真的衰减: 同一节点, now 越晚 det 越小。"""
    from core.worldtime import StoryTime
    st = _store(tmp_path)
    for n in st.all():
        n.story_time = StoryTime.from_sim_day(0).to_dict()
    vals = []
    for day in (0, 5, 15, 60):
        now = StoryTime.from_sim_day(day * 5)          # day 叙事日 = 5*day 格
        r = get_channel("A_intensity").gather(st, _ctx(story_now=now))
        vals.append(max(h.raw for h in r.hits))
    assert all(b < a for a, b in zip(vals, vals[1:])), vals
    print(f"    A: 新鲜度衰减 age=0/5/15/60 日 → {[round(v, 3) for v in vals]}")


def test_intensity_prior_degrades_without_clocks(tmp_path):
    """缺 now → 整条链路降级; 缺 node.story_time → **该节点**降级, 其余照常。"""
    from core.worldtime import StoryTime
    st = _store(tmp_path)
    r0 = get_channel("A_intensity").gather(st, _ctx())
    assert r0.degraded and not r0.hits and "story_now" in r0.note
    # 只给其中一条 stamp
    nodes = list(st.all())
    nodes[0].story_time = StoryTime.from_sim_day(0).to_dict()
    r1 = get_channel("A_intensity").gather(
        st, _ctx(story_now=StoryTime.from_sim_day(0)))
    assert not r1.degraded
    assert len(r1.hits) == 2
    assert sum(1 for h in r1.hits if h.raw is None) == 1     # 旧档那条
    assert r1.knobs["no_story_time"] == 1
    print(f"    A: 缺 now → 整链降级; 缺 node.story_time → 单条降级 "
          f"（{r1.knobs}）")


def test_intensity_prior_all_old_archive_degrades(tmp_path):
    """全部旧档（无 story_time）→ 降级而不是给一堆 0 分。"""
    from core.worldtime import StoryTime
    st = _store(tmp_path)
    r = get_channel("A_intensity").gather(
        st, _ctx(story_now=StoryTime.from_sim_day(0)))
    assert r.degraded and not [h for h in r.hits if h.raw is not None]
    assert "story_time" in r.note
    print(f"    A: 全旧档 → 降级（{r.note[:48]}）")


def test_emotion_rag_degrades_without_query_or_shape(tmp_path):
    """B 的三种降级理由（T15 起它**能出分**了, 但缺料仍必须诚实降级）。"""
    st = _store(tmp_path)
    # ① 没有当前情绪键序列
    r1 = get_channel("B_emotion_rag").gather(st, _ctx())
    assert r1.degraded and "emo_now" in r1.note
    # ② 有 emo_now, 但节点没有 emo_shape（旧档未物化）
    r2 = get_channel("B_emotion_rag").gather(
        st, _ctx(emo_now=["tease", "smile"]))
    assert r2.degraded and "emo_shape" in r2.note
    assert r2.knobs["no_emo_shape"] == 2
    # ③ 有料但没向量后端
    st.get("m0001").emo_shape = ["tease", "smile"]
    st.get("m0002").emo_shape = ["outburst", "shout"]
    r3 = get_channel("B_emotion_rag").gather(
        st, _ctx(emo_now=["tease", "smile"]))
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
        st, _ctx(emo_now=["tease", "smile", "smile"], embed_fn=emb))
    assert not r.degraded and len(r.hits) == 2
    assert all(h.raw is not None for h in r.hits)
    # 自己跟自己那一板必须排第一（键序列完全相同 → cos=1）
    assert r.hits[0].node.id == "m0001" and abs(r.hits[0].raw - 1.0) < 1e-9
    assert r.hits[0].rank == 1 and r.hits[1].rank == 2
    # 只读键序列: 叙述/verbatim 不进向量文本（§2.3.1 撤回框: 混正文会塌陷空间）
    seen = []
    get_channel("B_emotion_rag").gather(
        st, _ctx(emo_now=["tease"], embed_fn=lambda ts: (seen.extend(ts), emb(ts))[1]))
    assert all("杂草屋" not in t for t in seen), seen
    assert all(t.startswith("情绪序列: ") for t in seen), seen
    print(f"    B: 键序列 cos 出分 → {[(h.node.id, round(h.raw, 3)) for h in r.hits]}")


def test_recall_side_fields_never_reach_llm(tmp_path):
    """★★ 用户 2026-09-15 裁决: `emo_shape` / `place_now` **不进 LLM 上下文**。

    它们是**召回侧信号**——参与排序与筛选, 不参与写作。这里钉死的是
    「节点级」那一半: `render_*`（唯一往 prompt 里塞节点文本的地方）
    不许输出 `emo_shape`, 哪怕它是满的。
    """
    from core.brain.wiki_v2.render import render_character_view, render_organize_view
    st = _store(tmp_path)
    for n in st.all():
        n.emo_shape = ["outburst", "shout"]
    view = render_character_view(st.all(), char_name="遥香")
    org = render_organize_view(st.all())
    for text in (view, org):
        assert "outburst" not in text and "shout" not in text, text
        assert "emo_shape" not in text
    # 反向确认: 这两个视图确实渲染了节点（不是空串让断言假通过）
    assert "杂草屋" in view and "杂草屋" in org
    print("    ★ 召回侧字段隔离: emo_shape 不进 render_character_view / organize_view")


def test_place_gate_needs_place_field(tmp_path):
    st = _store(tmp_path)
    # 没给 place_now → 另一条降级理由
    r1 = get_channel("C_place").gather(st, _ctx())
    assert r1.degraded and "place_now" in r1.note
    # 给了 place_now, 但节点无 place 字段
    r2 = get_channel("C_place").gather(st, _ctx(place_now="杂草屋"))
    assert r2.degraded and "place 字段" in r2.note
    assert r2.knobs.get("place_now") == "杂草屋"
    print("    C: 两种降级理由分别说明（无 place_now / 节点无 place 字段）")


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
