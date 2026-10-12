"""合成层单测（`core/brain/read/compose.py`, 2026-09-20）。

用户口径（四条道路 → 最终打分）:

  > *"现在有剧情语义 RAG，情绪相似度 RAG，正交矩阵，地点调和平均这四条道路，
  > 可以考虑最终打分了"*
  > *"做成一个参数可选的调和平均吧"*
  > *"（A 的 det）不必归一，这个矩阵携带的信息本身就比较重很合理"*

钉七件事:

  ① **形状**: `final = fuse(rel, prior, mode)` —— 与 C 链路**同一个函数**（只写一份）
  ② **A 不归一**: `det > 1` 原样进轴 → 最终分可以 > 1（用户裁决）
  ③ `cos` 那一轴**池内 min-max**（绝对值在本机模型/真档上不可分, 实测见 compose docstring）
  ④ **命中 = 进 top-k**（否则 D 出全量 ⇒ 收敛数恒等于链路条数, 判据退化成常数）
  ⑤ **降级链路缺席, 不置 0**（0.0 = "算了就是 0 分", 与"没数据"不同）
  ⑥ **A 不能单独准入**; 先验缺席 → `pending`（A 的 `raw=None`: 旧档无 `ts`）
  ⑦ **无阈值旋钮**: 合成层的参数只有"形状/名次/取几条"
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

from core.brain import (  # noqa: E402
    KIND_PRIOR,
    KIND_SIMILARITY,
    ChannelHit,
    ChannelResult,
    RecallContext,
    WikiStoreV2,
    compose,
    make_node,
    recall_ledger,  # noqa: E402
    recall_now,
)
from core.brain.read.channel_impl import build_channels  # noqa: E402
from core.brain.read.channels import KIND_GATE, SCALE_COSINE, SCALE_UNIT  # noqa: E402
from core.common import fuse as shapes  # noqa: E402
from core.media import place_fuse as pf  # noqa: E402

# ---------------------------------------------------------------------------
# 构造器
# ---------------------------------------------------------------------------

def _ep(nid: str, **kw):
    return make_node("episode", id=nid, text=f"第 {nid} 段记忆", **kw)


def _res(channel: str, kind: str, scale: str, pairs, *,
         degraded: bool = False, note: str = "") -> ChannelResult:
    """`pairs = [(node, raw), ...]`（`raw=None` = 该节点降级）。"""
    hits = [ChannelHit(node=n, raw=r, rank=i + 1)
            for i, (n, r) in enumerate(pairs)]
    return ChannelResult(channel=channel, kind=kind, scale=scale, hits=hits,
                         degraded=degraded, note=note)


def _prior(pairs, **kw) -> ChannelResult:
    return _res("A_intensity", KIND_PRIOR, SCALE_UNIT, pairs, **kw)


def _sim(pairs, name: str = "D_deja_vu", **kw) -> ChannelResult:
    return _res(name, KIND_SIMILARITY, SCALE_COSINE, pairs, **kw)


def _gate(pairs, **kw) -> ChannelResult:
    return _res("C_place", KIND_GATE, SCALE_UNIT, pairs, **kw)


# ---------------------------------------------------------------------------
# ① 形状只写一份 + 参数可选
# ---------------------------------------------------------------------------

def test_shapes_are_a_single_implementation():
    """★ 用户 *"函数只写一份"*: C 链路的 `magic` 与合成层用的是**同一个函数对象**。"""
    assert pf.harmonic is shapes.harmonic
    assert pf.geometric is shapes.geometric
    assert pf.product is shapes.product
    assert pf.magic is shapes.magic is shapes.fuse
    assert set(pf.MODES) == set(shapes.MODES) == {"harmonic", "geometric", "product"}
    assert shapes.DEFAULT_MODE == "harmonic"
    print("    shapes: place_fuse 与 core.common.fuse 是同一个函数（无第二份实现）")


def test_final_is_harmonic_of_rel_and_prior():
    """`final = 2·rel·prior/(rel+prior)`（两个轴都真起作用, 换形状可切）。"""
    n = _ep("m1")
    res = compose([_prior([(n, 0.6)]), _sim([(n, 0.9)])])
    assert len(res.items) == 1
    c = res.items[0]
    # 池内只有一个候选 → min-max 退化（有正值 → 1.0）
    assert c.rel == 1.0, c
    expect = 2 * 1.0 * 0.6 / (1.0 + 0.6)
    assert abs(c.final - expect) < 1e-9, (c.final, expect)
    print(f"    compose: rel={c.rel:.2f} prior={c.prior:.2f} → final={c.final:.4f}")


def test_mode_switch_is_a_code_option():
    """三个形状都在: **product ≤ harmonic ≤ geometric**（换形状 = 换一个参数）。"""
    n = _ep("m1")
    got = {m: compose([_prior([(n, 0.8)]), _sim([(n, 1.0)])], mode=m
                      ).items[0].final for m in ("product", "harmonic", "geometric")}
    assert got["product"] < got["harmonic"] < got["geometric"], got
    with pytest.raises(ValueError, match="未知融合形状"):
        compose([], mode="magic")
    print(f"    compose: 三形状 {[f'{k}={v:.3f}' for k, v in got.items()]}")


# ---------------------------------------------------------------------------
# ② A 不归一（用户裁决）
# ---------------------------------------------------------------------------

def test_prior_axis_is_not_normalized():
    """★ 用户: *"不必归一，这个矩阵携带的信息本身就比较重很合理"*。

    `det` 的上界是 **2**（`channel_impl.IntensityPrior`: 两格之和）——
    合成层**不夹它**, 所以 `prior=1.8` 必须原样进去, 最终分也因此可以 > 1。
    """
    n = _ep("m1")
    res = compose([_prior([(n, 1.8)]), _sim([(n, 1.0)])])
    c = res.items[0]
    assert c.prior == 1.8, c.prior
    assert c.final == pytest.approx(2 * 1.0 * 1.8 / 2.8), c.final
    assert c.final > 1.0, "上界被夹了 —— A 的裁决没落地"
    # 对照: `clamp=True`（解析侧 / 地点两轴）会把 1.8 夹成 1.0
    assert shapes.fuse(1.0, 1.8) == 1.0
    assert shapes.fuse(1.0, 1.8, clamp=False) == pytest.approx(c.final)
    print(f"    compose: prior=1.8 原样 → final={c.final:.3f}（>1 是对的）")


# ---------------------------------------------------------------------------
# ③ cos 那一轴池内 min-max
# ---------------------------------------------------------------------------

def test_similarity_axis_is_pool_minmax():
    """★ cos 的**绝对值不可分**（真档实测: 域外 query 能到 0.798 > 同角色 min 0.781）
    ⇒ 只在池内拉相对差距; 否则 `prior` 恒是两轴里小的那个, 融合退化成"只按 A 排序"。

    ⚠️ 附带语义（`compose.py` docstring 记了三条）: **池内最差那条 rel=0**
    → `fuse(0, prior)=0` → 该链路对它等于没命中 → 落进 `dropped_no_rel`。
    """
    a, b, c = _ep("m1"), _ep("m2"), _ep("m3")
    res = compose([_prior([(a, 0.4), (b, 0.4), (c, 0.4)]),
                   _sim([(a, 0.86), (b, 0.80), (c, 0.72)])])
    by_id = {x.node.id: x for x in res.items}
    assert by_id["m1"].rel == pytest.approx(1.0)
    assert by_id["m2"].rel == pytest.approx((0.80 - 0.72) / (0.86 - 0.72))
    assert "m3" not in by_id, "池内最差 → rel=0 → 不构成证据（不是'排在最后'）"
    assert res.dropped_no_rel == 1
    assert by_id["m1"].final > by_id["m2"].final > 0
    print(f"    compose: cos 池内 min-max → rel(m1)={by_id['m1'].rel:.3f} "
          f"rel(m2)={by_id['m2'].rel:.3f}; m3 rel=0 → 落选")


def test_unit_scale_channel_is_not_minmaxed():
    """`GATE`（C 的 `magic`）本来就是 [0,1] 绝对分 → **原样**, 不做池内 min-max
    （否则"池里最差的一定是 0"是凭空制造的）。"""
    a, b = _ep("m1"), _ep("m2")
    res = compose([_prior([(a, 0.5), (b, 0.5)]), _gate([(a, 0.33), (b, 0.20)])])
    by_id = {c.node.id: c for c in res.items}
    assert by_id["m1"].rel == pytest.approx(0.33)
    assert by_id["m2"].rel == pytest.approx(0.20)
    print("    compose: unit 轴（C 的 magic）原样使用, 未被 min-max 拉平")


# ---------------------------------------------------------------------------
# ④⑤⑥ 命中 / 降级 / 准入
# ---------------------------------------------------------------------------

def test_hit_requires_top_k_not_just_a_score(tmp_path):
    """★ **命中 = 进前 k 名**。D 会把池里每个节点都出分（含负 cos）,
    所以按"出了分"数收敛会**每个节点都满命中** ⇒ 收敛数恒等于链路条数。
    """
    a, b, c = _ep("m1"), _ep("m2"), _ep("m3")
    sim = _sim([(a, 0.95), (b, 0.85), (c, 0.70)])
    pri = _prior([(a, 0.5), (b, 0.5), (c, 0.5)])
    res = compose([pri, sim], hit_k=1)
    ids = [x.node.id for x in res.items]
    assert ids == ["m1"], ids                     # 只有第 1 名算命中
    assert res.dropped_no_rel == 2                # 另外两条: 有先验、无证据 → 不准入
    res3 = compose([pri, sim], hit_k=3)
    # k=3 时三条都"命中"; 但池内最差的 c 归一后 rel=0（见 docstring 的三条语义）
    assert [x.node.id for x in res3.items] == ["m1", "m2"]
    assert res3.dropped_no_rel == 1
    print(f"    compose: hit_k=1 → {ids}; hit_k=3 → "
          f"{[x.node.id for x in res3.items]}（c 池内最差 rel=0）")


def test_convergence_beats_a_single_chain():
    """★ 用户 2026-09-13: *"双链路都召回的节点是最重要的"* —— 同一先验下,
    被两条链路命中的节点必须排在只被一条命中的前面（noisy-OR, 无权重旋钮）。"""
    both, one, x = _ep("m_both"), _ep("m_one"), _ep("m_x")
    res = compose([
        _prior([(both, 0.5), (one, 0.5), (x, 0.5)]),
        _sim([(both, 0.95), (one, 0.90), (x, 0.70)], name="D_deja_vu"),
        _sim([(both, 0.80), (one, 0.40), (x, 0.20)], name="B_emotion_rag"),
    ])
    ranked = [c.node.id for c in res.items]
    by_id = {c.node.id: c for c in res.items}
    assert ranked[0] == "m_both", ranked
    assert by_id["m_both"].channels == ["D_deja_vu", "B_emotion_rag"]
    assert by_id["m_both"].rel > by_id["m_one"].rel, (
        by_id["m_both"].rel, by_id["m_one"].rel)
    assert by_id["m_both"].final > by_id["m_one"].final
    print(f"    compose: 收敛 {ranked} "
          f"(rel {by_id['m_both'].rel:.3f} > {by_id['m_one'].rel:.3f})")


def test_degraded_channel_is_absent_not_zero():
    """★ 降级链路**缺席**（不回退成 0）: 0.0 是"算了就是 0 分", 会把"没数据"变成反证据。"""
    a = _ep("m1")
    res = compose([_prior([(a, 0.5)]),
                   _sim([], degraded=True, note="无 embed_fn（无向量后端）"),
                   _gate([], degraded=True, note="无节点带 place/place_raw（旧档）")])
    assert set(res.degraded) == {"D_deja_vu", "C_place"}
    assert res.degraded["D_deja_vu"].startswith("无 embed_fn")
    assert res.items == [] and res.pending == []
    assert res.dropped_no_rel == 1                # 只有 A 命中 → 不准入
    print(f"    compose: 两条降级缺席 → {sorted(res.degraded)}; A 单独不足以准入")


def test_prior_missing_goes_to_pending():
    """A 的 `raw=None`（旧档无 `ts`）→ `pending` = **待补, 不参与排序**（A 的降级语义）。"""
    a, b, c = _ep("m1"), _ep("m2"), _ep("m3")
    res = compose([_prior([(a, 0.5), (b, None)]),
                   _sim([(b, 0.95), (a, 0.80), (c, 0.70)])])
    assert [x.node.id for x in res.items] == ["m1"]
    assert [x.node.id for x in res.pending] == ["m2"]
    assert res.pending[0].prior is None and res.pending[0].rel > 0
    fields = res.ledger_fields()
    assert fields["pending"] == 1 and fields["ranked"] == 1
    print(f"    compose: 无 ts 的节点进 pending（prior=None, rel={res.pending[0].rel:.3f}）")


def test_prior_zero_is_a_real_zero():
    """`raw=0.0` 与 `raw=None` 语义不同（`ChannelHit` 的契约）: 前者是"真 0 分"，
    融合后为 0 → `dropped_zero`（不是 pending）。"""
    a = _ep("m1")
    res = compose([_prior([(a, 0.0)]), _sim([(a, 0.9)])])
    assert res.items == [] and res.pending == [] and res.dropped_zero == 1
    print("    compose: prior=0.0（真 0 分）→ 融合为 0, 落选")


# ---------------------------------------------------------------------------
# ⑦ 无阈值旋钮 + 台账
# ---------------------------------------------------------------------------

def test_compose_has_no_threshold_parameters():
    """T17 的延伸: 合成层的参数里不许有"过线/不过线"的旋钮。"""
    params = set(inspect.signature(compose).parameters) - {"results"}
    assert params == {"mode", "hit_k", "top"}, params
    for bad in ("thr", "threshold", "min_score", "cut", "cutoff", "gate"):
        assert not any(bad in p for p in params), (bad, params)
    print(f"    compose: 参数 {sorted(params)} —— 无阈值（只有形状/名次/取几条）")


def test_ledger_line_is_writable(caplog):
    """台账一行能打出来（观测层; 纯函数不打点, 由消费方接）。"""
    a = _ep("m1")
    res = compose([_prior([(a, 0.42)]), _sim([(a, 0.9)])])
    with caplog.at_level("INFO", logger="live2be.brain"):
        recall_ledger.log_compose(char_id="haruka", **res.ledger_fields())
    line = " ".join(r.getMessage() for r in caplog.records)
    assert "recall_compose" in line and "char=haruka" in line
    assert "rel=[" in line and "prior=[0.42,0.42]" in line
    print(f"    台账: {line}")


# ---------------------------------------------------------------------------
# 端到端（真链路 + 桩节点/桩向量 → 合成）
# ---------------------------------------------------------------------------

def _stub_embed(texts):
    """按字符和散列成 3 维桩向量（与 tests/core/test_wiki_channels.py 同款思路）。"""
    out = []
    for t in texts:
        h = sum(ord(c) for c in t if c not in "情绪序列: ")
        out.append([float(h % 7), float(h % 11), 1.0])
    return out


def test_recall_now_end_to_end(tmp_path):
    """★ 读路径入口: 真链路（A/D 出分, B/C 真档缺字段 → 降级）→ 合成排序。

    同时钉一条**契约缺口修复**（写 `compose.py` 时撞上的）:
    `ChannelResult` 必须携带 `scale` —— 否则合成层拿到结果也不知道怎么归一。
    """
    st = WikiStoreV2(tmp_path, world_id="w1", char_id="c")
    st.add(make_node("episode", id="m1", text="老师陪我在杂草屋看苔藓",
                     significance=0.9, ts="2026-09-19T10:00:00", event_seq=[14]))
    st.add(make_node("episode", id="m2", text="误发短信把老师叫到现场",
                     significance=0.6, ts="2026-09-19T11:00:00", event_seq=[30]))
    ctx = RecallContext(now="2026-09-20", query="她又想起那天的杂草屋",
                        char_id="c", embed_fn=_stub_embed)
    for ch in build_channels():
        r = ch.gather(st, ctx)
        assert r.scale == ch.scale, f"{r.channel} 没把 scale 放进结果"
    res = recall_now(st, ctx)
    assert res.items, res
    finals = [c.final for c in res.items]
    assert finals == sorted(finals, reverse=True), finals
    assert all(c.channels for c in res.items), "证据轴为空却有最终分"
    assert set(res.degraded) >= {"B_emotion_rag", "C_place"}, res.degraded
    assert res.knobs["prior_axis"] == "det 原样（不归一）"
    print(f"    recall_now: ranked={[(c.node.id, round(c.final, 3), c.channels) for c in res.items]}")
    print(f"    recall_now: degraded={sorted(res.degraded)}")
