# -*- coding: utf-8 -*-
"""旧档 `story_time` 外插迁移单测（T10 / §4.10 / Q8）。

钉住四条:
  1. **单调**: `event_seq` 小 → `sim_day` 小（相对顺序是最值钱的信息）
  2. **落点**: 全部 `< LEGACY_EPOCH`（与新区间不重叠）
  3. **幂等**: 已 stamp 的节点**永不重定位**（否则新记忆被拉回旧纪元, 不可逆）
  4. **缺 seq 兜底**: 不炸, 仍单调
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brain.wiki_v2 import WikiStoreV2, make_node          # noqa: E402
from core.brain.wiki_v2.migrate_time import (                  # noqa: E402
    GAP,
    MIN_EPOCH,
    apply as migrate_apply,
    epoch_for,
    plan as migrate_plan,
)
from core.worldtime import StoryTime                           # noqa: E402


def _mk(seq, narration):
    return make_node("episode", narration=narration, event_seq=[seq],
                     ts="2026-09-01T10:00:00")


def test_plan_is_monotone(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    for seq in (60, 20, 40, 10):
        st.add(_mk(seq, f"第 {seq} 段"))
    st.save()
    targets = migrate_plan(st.all())
    assert len(targets) == 4
    # 按 seq 排序后的 sim_day 必须同序
    order = sorted(st.all(), key=lambda n: min(n.event_seq))
    sims = [targets[n.id] for n in order]
    assert sims == sorted(sims), sims
    print(f"    plan: seq 10/20/40/60 → sim_day {sims}（严格单调）")


def test_plan_stays_below_epoch(tmp_path):
    """窗口 = `[0, epoch − GAP]`，且 `epoch` 按数据自己的 seq 算, 不是固定常数。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    for seq in range(1, 40, 3):
        st.add(_mk(seq, f"seq {seq}"))
    st.save()
    epoch = epoch_for(st.all())
    targets = migrate_plan(st.all(), epoch=epoch)
    window_max = epoch - GAP
    assert targets and max(targets.values()) <= window_max < epoch
    assert min(targets.values()) >= 0
    # 真机形态: seq 60 → epoch 65（不再是 5000 那种拍出来的数）
    assert epoch == max(1, 37) + GAP or epoch >= 37, epoch
    print(f"    plan: 全部落在 [0, {window_max}] < epoch({epoch})")


def test_epoch_scales_with_data(tmp_path):
    """★ 纪元**按数据比例**（真机修正）: 刚发生没几天的旧档不该被算成"3 年前"。"""
    small = WikiStoreV2(tmp_path / "a", world_id="world1", char_id="c")
    small.add(_mk(3, "少量事件"))
    big = WikiStoreV2(tmp_path / "b", world_id="world1", char_id="c")
    for seq in (10, 30, 60):
        big.add(_mk(seq, f"seq {seq}"))
    e_small, e_big = epoch_for(small.all()), epoch_for(big.all())
    assert e_small < e_big, (e_small, e_big)
    assert e_small >= MIN_EPOCH
    # 窗口 ≈ max_seq 格（1 事件 ≈ 1 时相 ≈ 1 格）
    assert e_big == 60 + GAP, e_big
    print(f"    epoch: seq3→{e_small}, seq60→{e_big}（按数据比例, 非固定常数）")


def test_apply_stamps_and_saves(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    for seq in (10, 30, 60):
        st.add(_mk(seq, f"seq {seq}"))
    st.save()
    res = migrate_apply(st, dry_run=False)
    assert res["migrated"] == 3 and res["saved"]
    for n in st.all():
        assert n.story_time is not None and n.story_time["sim_day"] <= epoch_for(st.all()) - GAP
    # 落盘往返（重开 store 仍在）
    st2 = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    assert all(n.story_time is not None for n in st2.all())
    print(f"    apply: 3 条落盘且往返保真（max sim_day="
          f"{max(n.story_time['sim_day'] for n in st2.all())}）")


def test_dry_run_writes_nothing(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(_mk(10, "x"))
    st.save()
    res = migrate_apply(st, dry_run=True)
    assert res["migrated"] == 0 and res["would_migrate"] == 1
    assert all(n.story_time is None for n in st.all())
    print("    dry_run: 只算不写（宁缺勿错默认）")


def test_already_stamped_never_moved(tmp_path):
    """★ 幂等: 已 stamp 的节点（T2 之后的新记忆）**永不重定位**。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(_mk(10, "旧档"))
    st.save()
    migrate_apply(st, dry_run=False)
    # 再建一条新节点, 模拟 T2 之后的记忆（sim_day 在纪元之上）
    new = _mk(90, "新记忆")
    new.story_time = StoryTime.from_sim_day(epoch_for(st.all()) + 7).to_dict()
    st.add(new)
    st.save()
    before = st.get(new.id).story_time["sim_day"]
    res = migrate_apply(st, dry_run=False)
    assert res["migrated"] == 0 and res["skipped"] == 2
    assert st.get(new.id).story_time["sim_day"] == before, "新记忆被重定位了"
    print(f"    幂等: 新记忆 sim_day 保持 {before}（未被拉回旧纪元）")


def test_missing_seq_falls_back(tmp_path):
    """缺 `event_seq` → 用**插入序**兜底（不是塞到窗口最底）, 全序仍单调。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", narration="无 seq（第 1 条插入）",
                     ts="2026-09-01T10:00:00"))
    st.add(_mk(50, "有 seq（第 2 条插入）"))
    st.save()
    targets = migrate_plan(st.all())
    nodes = st.all()
    assert len(targets) == 2
    assert all(0 <= v <= epoch_for(st.all()) - GAP for v in targets.values()), targets
    # 插入序在前的必须 ≤ 在后的
    assert targets[nodes[0].id] <= targets[nodes[1].id], targets
    print(f"    兜底: 缺 seq 用插入序 → {[targets[n.id] for n in nodes]}")


def test_seq_order_dominates_insert_order(tmp_path):
    """有 seq 时 **seq 说了算**（插入序倒着也按 seq 排）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    for seq in (60, 10, 30):                       # 插入序与 seq 相反
        st.add(_mk(seq, f"seq {seq}"))
    st.save()
    targets = migrate_plan(st.all())
    by_seq = {min(n.event_seq): targets[n.id] for n in st.all()}
    assert by_seq[10] < by_seq[30] < by_seq[60], by_seq
    print(f"    排序: seq 10/30/60 → {by_seq[10]}/{by_seq[30]}/{by_seq[60]}")


def test_world_epoch_is_world_level(tmp_path):
    """★ `world_clock.json` 是**世界级**文件, 纪元必须世界级。

    否则同一世界的 A/B 两角色各自初始化、**互相覆盖**（真机侥幸靠"最大者赢",
    但那是顺序侥幸, 不是设计）。
    """
    from core.brain.wiki_v2.migrate_time import migrate_data_root, world_epoch
    for cid, seq in (("a", 10), ("b", 60)):
        st = WikiStoreV2(tmp_path, world_id="world1", char_id=cid)
        st.add(_mk(seq, f"{cid} 的节点"))
        st.save()
    we = world_epoch(tmp_path, "world1")
    assert we == 60 + GAP, we                     # 取**最大**者, 不是某个角色的
    res = migrate_data_root(tmp_path, world_id="world1", dry_run=True)
    assert {v["epoch"] for v in res.values()} == {we}, res
    a_only = epoch_for(WikiStoreV2(tmp_path, world_id="world1",
                                   char_id="a").all())
    assert a_only != we, "逐角色各算会得到不同纪元（这正是要避免的）"
    print(f"    世界级纪元: {we}（两角色一致）; 逐角色各算会是 {a_only}")


def test_empty_store_is_noop(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    assert migrate_plan(st.all()) == {}
    res = migrate_apply(st, dry_run=False)
    assert res["migrated"] == 0 and not res["saved"]
    print("    空库: 零操作, 不落盘")


if __name__ == "__main__":
    import tempfile

    for fn in (test_plan_is_monotone, test_plan_stays_below_epoch,
               test_apply_stamps_and_saves, test_dry_run_writes_nothing,
               test_already_stamped_never_moved, test_missing_seq_falls_back,
               test_seq_order_dominates_insert_order,
               test_world_epoch_is_world_level,
               test_empty_store_is_noop):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("all migrate_time tests passed")
