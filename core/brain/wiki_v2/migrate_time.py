# -*- coding: utf-8 -*-
"""旧档迁移（T10）: 给没有 `story_time` 的旧节点做**单调外插**（§4.10 / Q8）。

## 为什么外插而不是 `null`

`§4.10` / Q8 已裁: **置 `null` 会让全部旧记忆退化成"很久以前", 丢掉相对顺序
这个最值钱的信息**。所以按 `event_seq` 单调外插。

## 落点: 一律 `< LEGACY_EPOCH`

`store.LEGACY_EPOCH = 5000` 的理由（见 store docstring）: 新节点从 5000 起算,
旧档迁移后必须落在 `< 5000`, 两个区间天然分离、**事后可分辨**。

外插公式（`§4.10` "按 event_seq 单调外插到游标"）::

    t(n) = min(seq(n), S) / S × (LEGACY_EPOCH − 1)

`seq(n)` = 节点 `event_seq` 的最小值（`segment_id` 是段标识, 单调性靠它保证）。
`S` = 本次迁移集合里最大的 `seq`。于是:

- **相对顺序严格保持**（`seq` 小 → `sim_day` 小）
- 全部落在 `[0, 4999]`, 与新区间不重叠
- `seq` 缺失 → 用集合内序号兜底（仍单调）

## 幂等

**只动 `story_time is None` 的节点**。已 stamp 的（T2 之后建的新记忆）永不重定位
—— 否则一次迁移就会把新记忆拉回旧纪元, 且**不可逆**。

## 一次性

这是**迁移**, 不是常驻逻辑。跑完即止; 若要重跑, 因为只动未采集的节点, 天然幂等。
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

#: 独立运行（`python core/brain/wiki_v2/migrate_time.py`）时把项目根放进 path ——
#: 必须在 `from core...` 之前。作为模块被 import 时无副作用（根已在 path 里）。
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.brain.wiki_v2.store import WikiStoreV2                 # noqa: E402
from core.worldtime.story import StoryTime                       # noqa: E402

#: 旧档窗口与新区间之间的**分离间隙**（格）—— 保证 `max(旧) < min(新)`
GAP = 5

#: 窗口下限（格）—— 全新世界也要有个非零起点, 免得与"未采集"混淆
MIN_EPOCH = 50

logger = logging.getLogger(__name__)

#: 迁移窗口上界 —— 由 `epoch_for()` 按**数据自己**的 seq 算出, 不再是固定常数
__all__ = ["plan", "apply", "migrate_data_root", "epoch_for", "GAP", "MIN_EPOCH"]


#: 迁移窗口上界 —— 由 `epoch_for()` 按**数据自己**的 seq 算出, 不再是固定常数
__all__ = ["plan", "apply", "migrate_data_root", "epoch_for", "GAP", "MIN_EPOCH"]


def epoch_for(nodes: list) -> int:
    """本世界线的纪元位置 —— **按数据自己的 `event_seq` 比例算**。

    ## 为什么不再用固定常数（2026-09-13 实测修正）

    初版取 `LEGACY_EPOCH = 5000` 常量, 把"旧档窗口"和"与新区间的分离带"混成一个数。
    真机实测后果: 旧节点落在 `sim_day ∈ [0, 4999]`, 而游标在 5000 ——
    **一份刚发生没几天的记忆被算成"3 年前"**（`§4.10` 的"相对顺序"保住了,
    但绝对年龄失真）。

    ## 正确口径: `一个事件 seq ≈ 一场互动 ≈ 1 时相 ≈ 1 格`

    于是旧档窗口 = `max(event_seq)` 格（`seq 60` → 60 格 = 12 叙事日）,
    加上一小段 `GAP` 就是纪元。**新节点从纪元起算, 与旧档天然不重叠。**
    全新世界（无 seq）→ `MIN_EPOCH`。
    """
    seqs = [min(n.event_seq) for n in nodes if n.event_seq]
    top = max(seqs) if seqs else 0
    return max(MIN_EPOCH, top + GAP)


def plan(nodes: list, *, epoch: int | None = None) -> dict[str, int]:
    """算出每个待迁移节点的目标 `sim_day`（**纯函数, 不落盘**）。

    顺序键 = `(位次估计, 插入序)` —— **双键保证全序**:
    `event_seq` 是引擎已知的精确位次; 缺它时用插入序兜底
    （`store.all()` 的顺序就是创建序）, 而不是把所有缺 seq 的塞到窗口最底。

    `epoch` 缺省 → `epoch_for(nodes)`。窗口 = `[0, epoch − GAP]`。

    Returns: `{node_id: sim_day}`（只含 `story_time is None` 的节点）。
    """
    pending = [n for n in nodes if n.story_time is None]
    if not pending:
        return {}
    epoch = epoch_for(nodes) if epoch is None else int(epoch)
    window_max = max(0, epoch - GAP)
    ranked: list[tuple[tuple, object]] = []
    for i, n in enumerate(pending):
        s = min(n.event_seq) if n.event_seq else None
        pos = s if isinstance(s, int) else i
        ranked.append(((pos, i), n))
    ranked.sort(key=lambda t: t[0])
    total = len(ranked)
    out: dict[str, int] = {}
    for rank, (_, n) in enumerate(ranked):
        out[n.id] = int(rank / max(1, total - 1) * window_max) if total > 1 else 0
    return out


def apply(store: WikiStoreV2, *, dry_run: bool = True,
          force: bool = False) -> dict:
    """执行迁移。`dry_run=True` → 只算不写（默认——宁缺勿错）。

    `force=True` → **先把 `story_time` 清零再重迁**（修正历史迁移错误用）。
    默认 False: 只动未采集的节点, 故天然幂等（已 stamp 的永不重定位）。

    ⚠️ **游标也要对齐**（`store.clock()` 初始化到本世界线的 `epoch_for`）:
    否则旧档落在 `[0, epoch)` 而新区间从别处起算, 两个区间可能重叠。

    Returns: `{migrated, would_migrate, skipped, epoch, samples, saved}`。
    """
    nodes = store.all()
    epoch = epoch_for(nodes)
    if force:
        for n in nodes:
            n.story_time = None
    targets = plan(nodes, epoch=epoch)
    skipped = sum(1 for n in nodes if n.story_time is not None)
    samples = [(nid, sim) for nid, sim in
               sorted(targets.items(), key=lambda kv: kv[1])[:5]]
    if dry_run or not targets:
        return {"migrated": 0, "would_migrate": len(targets),
                "skipped": skipped, "epoch": epoch, "samples": samples,
                "saved": False}
    for nid, sim in targets.items():
        node = store.get(nid)
        if node is None:
            continue
        node.story_time = StoryTime.from_sim_day(sim).to_dict()
    store.save()
    # 游标对齐到本世界线的纪元（**只增不减**——I6）
    # ⚠️ **无条件落盘**: 若只在"游标 < 纪元"时才写, 而它正好等于纪元（常见),
    #    文件就永远不会被创建 —— 每次新建 store 都会在内存里重新初始化,
    #    磁盘上查不到时间线（真机实测踩到）。
    clk = store.clock()
    if clk.cursor.sim_day < epoch:
        clk.cursor = StoryTime.from_sim_day(epoch, anchor=clk.anchor)
    store.save_clock()
    logger.info("旧档迁移: %d 条 → [0, %d); 纪元 %d", len(targets), epoch - GAP, epoch)
    return {"migrated": len(targets), "would_migrate": len(targets),
            "skipped": skipped, "epoch": epoch, "samples": samples, "saved": True}


def migrate_data_root(data_root: str | Path = "data", *,
                      world_id: str = "world1",
                      char_id: str = "", dry_run: bool = True,
                      force: bool = False) -> dict:
    """按角色跑一次（CLI / 脚本入口）。`char_id=""` → 该世界全部角色。"""
    root = Path(data_root) / "worlds" / world_id / "characters"
    chars = [char_id] if char_id else sorted(
        p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    out: dict[str, dict] = {}
    for cid in chars:
        store = WikiStoreV2(data_root, world_id=world_id, char_id=cid)
        if not store.all():
            continue
        out[cid] = apply(store, dry_run=dry_run, force=force)
    return out


if __name__ == "__main__":                        # pragma: no cover — CLI
    dry = "--apply" not in sys.argv
    res = migrate_data_root("data", world_id="world1", dry_run=dry,
                            force="--force" in sys.argv)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    print("\n（干跑默认；真跑加 --apply；修正历史迁移加 --force）"
          if dry else "\n（已落盘）")
