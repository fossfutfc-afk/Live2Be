"""`core/affection` 数值层单测 —— **带符号累计**（2026-09-13 立项，§3.3.3）。

背景: 旧契约是"经验只增不减（BA 无降好感机制）"。该契约已推翻——现有全部召回信号
都是单调累积量, **没有一个能表达"关系变坏"**; 带符号之后才有
`mood_congruence = 1 − |aff_now − aff_at_encoding| / 量程` 这个同频召回轴。

本文件钉住四条不变量:
  1. `exp` 带符号累计, 地板 MIN_EXP=0（不出现负经验）
  2. 恶化到地板 → 等级同步回 MIN_LEVEL（不能出现"级别高但经验 0"）
  3. `to_scalar()` 保号 + 有界 (−1, 1) + `exp=0 → 0.0`
  4. `load_affection_from_events`: **无事件 → None**（无数据）与
     **净变化 ≤0 → {1, 0}**（真实状态）是两件事
"""
from __future__ import annotations

import sys
from pathlib import Path


from core.affection.affection_calc import (          # noqa: E402
    MAX_LEVEL,
    MIN_EXP,
    MIN_LEVEL,
    SCALAR_SCALE,
    Affection,
    load_affection_from_events,
    load_affection_table,
)

TABLE = load_affection_table()          # lv1→[15,0] lv2→[30,15] lv3→[30,45] lv4→[35,75]


def _ev(seq, delta, covered=None):
    """最小 affection 事件替身（只用 .type/.payload/.seq 三个属性）。"""
    class _E:
        type = "affection"
        payload = {"delta": delta,
                   "digested_seq": seq if covered is None else covered}
    e = _E()
    e.seq = seq
    return e


# ---------------------------------------------------------------------------
# 1. 带符号累计 + 地板
# ---------------------------------------------------------------------------

def test_add_exp_negative_accumulates():
    # 表: lv1 门槛 total=0 / lv2 门槛 total=15 / lv3 门槛 total=45
    a = Affection(exp=40, table=TABLE)          # 40 ≥ 45? 否 → level 2
    assert (a.level, a.exp) == (2, 40)
    a.add_exp(-10)
    assert (a.level, a.exp) == (2, 30)          # 30 仍 ≥ 15 → 还是 2 级（只减经验）
    a.add_exp(-20)
    assert (a.level, a.exp) == (1, 10)          # 10 < 15 → 掉回 1 级
    print("    Affection: 负 delta 真的减累计（40 → 30 → 10, 2 级 → 2 级 → 1 级）")


def test_add_exp_clamps_at_floor_and_resets_level():
    a = Affection(exp=40, table=TABLE)
    a.add_exp(-999)                             # 恶化到底
    assert a.exp == MIN_EXP == 0, f"地板应为 0, 实得 {a.exp}"
    assert a.level == MIN_LEVEL, "恶化到底必须同步回 1 级（不能留高级别配 0 经验）"
    print("    Affection: 恶化到底 → exp=0 且等级回 1（无负经验、无等级残留）")


def test_ctor_negative_exp_clamps():
    a = Affection(exp=-500, table=TABLE)
    assert (a.level, a.exp) == (MIN_LEVEL, 0)
    print("    Affection: 构造器吃负 exp → 地板 0")


def test_add_exp_zero_is_noop():
    a = Affection(exp=40, table=TABLE)
    a.add_exp(0)
    assert (a.level, a.exp) == (2, 40)
    print("    Affection: delta=0 早退（无变化不重算）")


def test_positive_path_unchanged():
    """回归: 正向路径必须与旧行为逐位一致（本次改动不许碰它）。"""
    a = Affection(table=TABLE)
    a.add_exp(50)
    assert (a.level, a.exp) == (3, 50)          # 50 累计门槛 = 45
    a.add_exp(999999)
    assert a.exp == 50 + 999999 and a.level == MAX_LEVEL   # 满级后经验仍累计
    print("    Affection: 正向路径与旧行为一致（含满级后仍累计）")


# ---------------------------------------------------------------------------
# 2. to_scalar —— 同频召回用的带符号标量
# ---------------------------------------------------------------------------

def test_to_scalar_sign_and_bounds():
    assert Affection(exp=0, table=TABLE).to_scalar() == 0.0
    # 渐近饱和: 极小值 >0, 极大值夹在 1.0（tanh 在 exp/SCALE 大时会浮点到 1.0）
    v_small = Affection(exp=10, table=TABLE).to_scalar()
    assert 0.0 < v_small < 1.0
    assert Affection(exp=12000, table=TABLE).to_scalar() <= 1.0
    # 地板保证不出现负标量——"关系变坏"= 标量趋 0, 不是趋负
    assert Affection(exp=-9999, table=TABLE).to_scalar() == 0.0
    print("    to_scalar: 保号 + 上界 1.0 + exp=0 → 0.0 + 地板不产负值")


def test_to_scalar_real_scale_anchor():
    """★ 尺度锚点按**真机量级**定, 不是拍的（2026-09-13 修正）。

    真机实测: 一个完整章节的 digest delta = **75 exp**。
    初版拍 5000 → tanh(75/5000) = 0.015（几乎为 0, 同频信号等于没有）。
    取 300 → 0.245（有区分度的量级）。
    """
    one_chapter = Affection(exp=75, table=TABLE).to_scalar()
    assert 0.2 < one_chapter < 0.3, f"一章好感标量 {one_chapter:.3f} 不在可分辨区间"
    assert SCALAR_SCALE == 300.0, "SCALAR_SCALE 改动必须同时改文档 §3.3.3"
    print(f"    to_scalar: 真机锚点 一章75exp → {one_chapter:+.3f}"
          f"（SCALAR_SCALE={SCALAR_SCALE:.0f}）")


def test_to_scalar_monotone():
    xs = [0, 10, 75, 300, 1500, 20000]
    ys = [Affection(exp=x, table=TABLE).to_scalar() for x in xs]
    assert all(b > a for a, b in zip(ys, ys[1:])), f"非单调: {ys}"
    assert ys[0] == 0.0 and ys[-1] > 0.99
    print(f"    to_scalar: 单调（0→0.0, 75→{ys[2]:.3f}, 20000→{ys[-1]:.3f}）")


# ---------------------------------------------------------------------------
# 3. load_affection_from_events —— "无数据" vs "真实状态"
# ---------------------------------------------------------------------------

def test_no_affection_events_returns_none():
    assert load_affection_from_events([]) is None
    assert load_affection_from_events([_ev(3, 5)][:0]) is None
    print("    load: 无 affection 事件 → None（无数据）")


def test_net_zero_or_negative_returns_neutral_dict():
    """★ 语义变更: 事件存在但净变化 ≤0 → {1, 0}（参与比较）, 不再折成 None。"""
    zero = load_affection_from_events([_ev(3, 50), _ev(5, -50)])
    assert zero == {"level": MIN_LEVEL, "exp": 0}, zero
    worse = load_affection_from_events([_ev(3, 20), _ev(5, -120)])
    assert worse == {"level": MIN_LEVEL, "exp": 0}, worse
    print("    load: 净变化 ≤0 → {level:1, exp:0}（是状态, 不是 None）")


def test_up_to_seq_replay():
    """按 seq 回放: 只看 covered ≤ 回退点的事件（rewind 用）。"""
    evs = [_ev(3, 100), _ev(9, -30)]
    assert load_affection_from_events(evs)["exp"] == 70
    assert load_affection_from_events(evs, up_to_seq=3)["exp"] == 100
    assert load_affection_from_events(evs, up_to_seq=0) is None      # 无覆盖事件
    print("    load: up_to_seq 回放正确（100 → 70）")


if __name__ == "__main__":
    for fn in (test_add_exp_negative_accumulates,
               test_add_exp_clamps_at_floor_and_resets_level,
               test_ctor_negative_exp_clamps,
               test_add_exp_zero_is_noop,
               test_positive_path_unchanged,
               test_to_scalar_sign_and_bounds,
               test_to_scalar_real_scale_anchor,
               test_to_scalar_monotone,
               test_no_affection_events_returns_none,
               test_net_zero_or_negative_returns_neutral_dict,
               test_up_to_seq_replay):
        fn()
    print("all affection tests passed")
