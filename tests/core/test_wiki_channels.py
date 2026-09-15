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


def test_intensity_prior_reports_time_gap(tmp_path):
    """★ A 链路: 四格已就绪但 TIME 未设计 → 不出分, 且 knobs 要说明差什么。"""
    st = _store(tmp_path)
    r = get_channel("A_intensity").gather(st, _ctx())
    assert r.degraded and "TIME" in r.note
    assert r.knobs.get("time_ready") is False
    assert r.knobs.get("sig_ready") and r.knobs.get("int_ready")
    assert not r.hits
    print(f"    A: 降级并说明只差时间 → {r.note[:56]}")


def test_emotion_rag_reports_link_gap(tmp_path):
    st = _store(tmp_path)
    r = get_channel("B_emotion_rag").gather(st, _ctx())
    assert r.degraded and "event_seq" in r.note
    assert "needs" in r.knobs
    print(f"    B: 降级并说明缺连接键 → {r.note[:56]}")


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
                   test_intensity_prior_reports_time_gap,
                   test_emotion_rag_reports_link_gap,
                   test_place_gate_needs_place_field,
                   test_unconscious_is_declared_not_implemented,
                   test_deja_vu_is_the_only_scoring_channel,
                   test_deja_vu_degrades_without_embed,
                   test_channel_is_read_only):
            fn(p)
    print("all channel tests passed")
