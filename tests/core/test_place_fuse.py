"""地点两轴融合单测（`core/media/place_fuse.py`, 2026-09-20）。

用户口径: *"混合策略，一个特殊的 magic function，在 writer 词和 key 相似度都高的
时候值高，反之一般"* ⇒ 形状 = **调和平均**（用户选定）, 两根轴 = 叙事（语义）×
素材（**字面**）。

钉三件事:
  ① **形状**: 两轴都高 → 高; 一高一低 → 中（不塌也不顶格）; 一轴为零 → **0**
  ② **素材轴是字面**: 真表上的 `天台` 家族真的连得起来（`school_rooftop` /
     `building_roof_top` / `rooftop`）, 而 `dir` 连不起来（那是图族, 不是地点）
  ③ **无旋钮**: `mode` 是代码选项; 没有阈值参数
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.media import place_fuse as pf                    # noqa: E402
from core.media.place_table import load_table              # noqa: E402


# ---------------------------------------------------------------------------
# ① 形状
# ---------------------------------------------------------------------------

def test_harmonic_shape_matches_the_ask():
    """★ "都高时高、反之一般" —— 逐格对照（这是本模块存在的理由）。"""
    both_high = pf.magic(0.9, 0.9)
    one_high = pf.magic(0.9, 0.3)
    one_zero = pf.magic(0.9, 0.0)
    both_low = pf.magic(0.2, 0.2)
    assert both_high > 0.85, both_high                     # 双高 → 顶格附近
    assert 0.4 < one_high < 0.6, one_high                  # 一高一低 → **中**
    assert one_zero == 0.0, one_zero                        # 一轴为零 → 没关系（不是弱关系）
    assert both_low < one_high, (both_low, one_high)        # 双低最差
    # 对比: 加权和会让"单轴高"直接接近顶格（用户不要那个形状）
    assert (0.9 + 0.3) / 2 > one_high, "加权和与调和平均的差别正在这里"
    print(f"    形状: 双高={both_high:.3f} 一高一低={one_high:.3f} "
          f"一轴为零={one_zero:.3f} 双低={both_low:.3f}")


def test_modes_are_code_options_not_knobs():
    """三个形状都在, 默认调和; 未知 mode → 显式报错; **没有任何阈值参数**。"""
    assert pf.DEFAULT_MODE == "harmonic"
    assert set(pf.MODES) == {"harmonic", "geometric", "product"}
    # 同样的输入, 三种形状的松紧顺序: **product ≤ harmonic ≤ geometric**
    # （HM ≤ GM 是数学恒等式; product 最严）—— 用户选的调和平均落在中间偏严那侧
    a, b = 0.8, 0.4
    assert pf.product(a, b) < pf.harmonic(a, b) < pf.geometric(a, b), (
        pf.product(a, b), pf.harmonic(a, b), pf.geometric(a, b))
    with pytest.raises(ValueError, match="未知融合形状"):
        pf.magic(0.5, 0.5, mode="magic")
    # 负值/None 一律夹到 0（负相关不是"弱相关"）; cos 的浮点过冲夹到 1
    assert pf.magic(-0.5, 0.9) == 0.0 and pf.magic(None, 0.9) == 0.0
    assert pf.magic(1.0000000000000002, 1.0000000000000002) == 1.0
    import inspect
    sig = inspect.signature(pf.magic)
    assert "threshold" not in sig.parameters and "alpha" not in sig.parameters
    print("    形状表: product ≤ harmonic ≤ geometric; 无 threshold/alpha 参数")


# ---------------------------------------------------------------------------
# ② 素材轴（真表上的字面相似度）
# ---------------------------------------------------------------------------

def test_key_similarity_on_the_real_table():
    """真表实测: `天台` 家族连得起来; `dir` 不是判据（作者按图族组织目录）。"""
    t = load_table()
    assert t.ok, t.error
    # 同名 = 1
    assert pf.key_similarity("school_rooftop", "school_rooftop", table=t) == 1.0
    # 别名相交: 天台 → school_rooftop / building_roof_top / rooftop
    s_school = pf.key_similarity_by("school_rooftop", "building_roof_top", table=t)
    assert s_school[1] == "alias" and 0.3 <= s_school[0] <= 0.4, s_school
    # 键名 token: school_rooftop vs rooftop → 包含 → 满分
    s_token = pf.key_similarity_by("school_rooftop", "rooftop", table=t)
    assert s_token == (1.0, "token"), s_token
    # 无关: 教室 vs 温泉
    assert pf.key_similarity("classroom", "onsen", table=t) == 0.0
    # ⚠️ `dir` 不能当判据: 天台那三个键分属三个不同 DIR
    dirs = {k: t.get(k).dir for k in ("school_rooftop", "rooftop", "building_roof_top")}
    assert len(set(dirs.values())) == 3, dirs
    print(f"    素材轴: 别名={s_school[0]:.2f}({s_school[1]}) "
          f"键名={s_token[0]:.2f}({s_token[1]}); dir={dirs}")


def test_key_similarity_degrades_and_guards():
    """表读不出来 / 键不在表里 / 空串 / 单字 token —— 都不抛, 且不误命中。"""
    from core.media.place_table import PlaceTable
    empty = PlaceTable()
    # 表里没有的键 → 只按键名比（退化但不抛）
    assert pf.key_similarity("rooftop", "school_rooftop", table=empty) == 1.0
    assert pf.key_similarity("classroom", "onsen", table=empty) == 0.0
    # 空串
    assert pf.key_similarity("", "classroom") == 0.0
    assert pf.key_similarity("classroom", "   ") == 0.0
    # 集合形态: 取最大 + 报出命中的那个键
    s, by, key = pf.key_similarity_to_set(["classroom", "school_rooftop"],
                                          "building_roof_top")
    assert key == "school_rooftop" and by == "alias" and s > 0, (s, by, key)
    assert pf.key_similarity_to_set([], "classroom") == (0.0, "none", "")
    print("    退化: 空表按键名; 空串/空集合 → 0（不抛、不误命中）")


# ---------------------------------------------------------------------------
# ③ 融合进 C 链路（召回侧）——两轴怎么合、缺一轴怎么办
# ---------------------------------------------------------------------------

def _node(nid: str, *, place=None, place_raw=None, text="一"):
    from core.brain.nodes import BrainNode
    return BrainNode(id=nid, kind="episode",
                     significance=0.7, text=text,
                     place=place or [], place_raw=place_raw or [], event_seq=[1])


def _store_with(nodes, tmp_path):
    from core.brain.store import WikiStoreV2
    st = WikiStoreV2(path=tmp_path / "wiki.jsonl")
    for n in nodes:
        st.add(n)
    return st


def _char_bag(texts):
    """确定性假向量（字符集袋）——同字多的两条 cos 高, 零依赖。"""
    vocab = sorted({ch for t in texts for ch in t})
    return [[1.0 if ch in t else 0.0 for ch in vocab] for t in texts]


def test_c_link_fuses_both_axes(tmp_path):
    """★ C 链路: 两轴融合 —— 同键高分在前, 同地不同键（别名相交）也能捞回来。"""
    from core.brain.read.channels import RecallContext
    from core.brain.read.channel_impl import PlaceGate
    st = _store_with([
        _node("m1", place=["school_rooftop"], place_raw=["傍晚的学校天台"],
              text="天台上的风"),
        _node("m2", place=["building_roof_top"], place_raw=["学校天台"],
              text="另一栋楼的天台"),                      # 同地不同键（别名相交）
        _node("m3", place=["classroom"], place_raw=["傍晚的学校天台"],
              text="教室里的傍晚"),                        # 只像说法, 键不相干
    ], tmp_path)
    ctx = RecallContext(char_id="c", query="", now="2026-09-20",
                        place_now="school_rooftop", place_raw_now="傍晚的学校天台",
                        embed_fn=_char_bag)
    r = PlaceGate().gather(st, ctx)
    ids = [h.node.id for h in r.hits]
    assert ids[0] == "m1", f"同键 + 同说法该排第一: {[(h.node.id, h.raw) for h in r.hits]}"
    assert "m2" in ids, "同地不同键（别名相交）**该被捞回来** —— 这就是修掉的那条假阴性"
    assert "m3" not in ids, "键八竿子打不着 → 融合为 0（语义轴不许单独放宽准入）"
    d1 = r.hits[0].detail
    assert d1["same_image"] is True and d1["key_sim_by"] == "same" and d1["axes"] == 2
    d2 = [h for h in r.hits if h.node.id == "m2"][0].detail
    assert d2["same_image"] is False and d2["key_sim_by"] == "alias", d2
    assert r.knobs["same_image"] == 1 and r.knobs["hit"] == 2
    print(f"    C 融合: {[(h.node.id, round(h.raw, 3), h.detail['by']) for h in r.hits]}")


def test_c_link_without_embedder_uses_material_axis_only(tmp_path):
    """无 `embed_fn` / 无 `place_raw_now` → 叙事轴缺席, `raw` 退回素材轴那一半。"""
    from core.brain.read.channels import RecallContext
    from core.brain.read.channel_impl import PlaceGate
    st = _store_with([
        _node("m1", place=["school_rooftop"], place_raw=["傍晚的学校天台"]),
        _node("m2", place=["building_roof_top"], place_raw=["学校天台"]),
        _node("m3", place=["onsen"], place_raw=["温泉"]),
    ], tmp_path)
    ctx = RecallContext(char_id="c", query="", now="2026-09-20",
                        place_now="school_rooftop", place_raw_now="傍晚的学校天台")
    r = PlaceGate().gather(st, ctx)
    ids = [h.node.id for h in r.hits]
    assert ids[0] == "m1" and "m2" in ids and "m3" not in ids, ids
    assert all(h.detail["axes"] == 1 and h.detail["sem"] is None for h in r.hits)
    assert "无 embed_fn" in r.knobs["sem"]
    print(f"    无向量后端: 只用素材轴 {[(h.node.id, round(h.raw, 2)) for h in r.hits]}")


def test_c_link_still_degrades_honestly(tmp_path):
    """没坐标 / 旧档（无 place 字段）→ 照旧降级, 不编分。"""
    from core.brain.read.channels import RecallContext
    from core.brain.read.channel_impl import PlaceGate
    st = _store_with([_node("m1", text="没有地点字段")], tmp_path)
    r1 = PlaceGate().gather(st, RecallContext(char_id="c", query="", now="2026-09-20"))
    assert r1.degraded and "place_now" in r1.note
    r2 = PlaceGate().gather(st, RecallContext(char_id="c", query="", now="2026-09-20",
                                              place_now="classroom"))
    assert r2.degraded and "旧档" in r2.note
    print("    C 降级: 无坐标 / 旧档 → degraded（不编分）")


if __name__ == "__main__":
    import tempfile
    test_harmonic_shape_matches_the_ask()
    test_modes_are_code_options_not_knobs()
    test_key_similarity_on_the_real_table()
    test_key_similarity_degrades_and_guards()
    with tempfile.TemporaryDirectory() as td:
        test_c_link_fuses_both_axes(Path(td))
        test_c_link_without_embedder_uses_material_axis_only(Path(td))
        test_c_link_still_degrades_honestly(Path(td))
    print("all place_fuse tests passed")
