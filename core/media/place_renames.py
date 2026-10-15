"""place_renames — 地点改名台账（`data/worlds/{world}/place_renames.jsonl`）。

## 为什么需要它

用户 2026-09-19: *"key 是不可改的"* —— 因为**回放**按 key 查表
（`_place_bg` → 表 → 资产），而事件流是 **append-only**（旧板里的 `place` 不许改）。
但现实里改名仍会发生（作者在 tempo 里重整命名、发现 key 拼错、两个 key 该合并）。
两者不冲突的做法 = **只改表 + 留台账**:

    表      = 当下的视图（新名）      ← `place_entities.json`
    台账    = 历史（旧名 → 新名 + 原因 + 影响面）  ← 本模块
    事件流  = **不动**（旧名还是旧名 —— 它记的是"当时按哪张图演"）

于是 `_place_bg("旧名")` 查不到图时**不是**笼统的"素材未找到"，而是
`key '旧名' 已改名为 '新名'` —— 那条黑屏 alert 直接告诉人该去改什么。
（用户 2026-09-19 裁决: *"允许留痕"* + *"独立 jsonl 台账 + 让它给『素材未找到』
当解释"*。）

## 形状（一行一条, **append-only**）

    {"ts": "2026-09-19T21:03:11", "from": "old_key", "to": "new_key",
     "reason": "作者改名：统一 xxx", "events": 12}

* `events` = **扫描时命中的事件条数**（不是"改了多少条"—— 事件流不动, 只做记账）
* 同一对改名重复登记是允许的（append-only 的代价, 无所谓）; 查表时**按链回溯**
  （`a→b`、`b→c` ⇒ `a` 的最新名是 `c`）。环由 `append` 挡住。
* 台账**不塞进表**: 表是"当下的视图", 不背历史（用户裁决）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from infra import paths

logger = logging.getLogger("live2be.place")

#: 台账文件名（每个世界线一份; 与事件流同卷, 可 grep）
LEDGER_NAME = "place_renames.jsonl"

#: `(path, mtime_ns, size)` → 已解析行（改台账即生效, 不重启）
_CACHE: dict[tuple[str, int, int], list[dict]] = {}
_CACHE_MAX = 8


def reset_cache() -> None:
    """清缓存（测试/排查用）。"""
    _CACHE.clear()


def ledger_path(world: str, *, worlds_dir: Path | str | None = None) -> Path:
    """`data/worlds/{world}/place_renames.jsonl`（`worlds_dir` 可覆盖——测试用）。"""
    root = Path(worlds_dir) if worlds_dir else paths.WORLDS_DIR
    return root / str(world) / LEDGER_NAME


def load(world: str, *, worlds_dir: Path | str | None = None) -> list[dict]:
    """读一个世界的台账（**按 mtime 缓存**）。缺失/坏行 → 跳过该行（宁缺勿错）。"""
    p = ledger_path(world, worlds_dir=worlds_dir)
    try:
        st = p.stat()
        ck = (str(p), st.st_mtime_ns, st.st_size)
    except OSError:
        return []
    hit = _CACHE.get(ck)
    if hit is not None:
        return hit
    rows: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("[place_renames] 台账读不出来（当空）: %s", e)
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("from") and obj.get("to"):
            rows.append(obj)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[ck] = rows
    return rows


def all_worlds(*, worlds_dir: Path | str | None = None) -> list[str]:
    """世界线 id 列表（目录名; 缺根 → `[]`）。"""
    root = Path(worlds_dir) if worlds_dir else paths.WORLDS_DIR
    try:
        return sorted(d.name for d in root.iterdir() if d.is_dir())
    except OSError:
        return []


def _chain(world: str, *, worlds_dir: Path | str | None = None) -> dict[str, str]:
    """`旧名 → 新名` 映射（同一条旧名重复登记时**后者胜** = 最新一次）。"""
    out: dict[str, str] = {}
    for row in load(world, worlds_dir=worlds_dir):
        out[str(row["from"])] = str(row["to"])
    return out


def resolve(key: str, *, world: str = "",
            worlds_dir: Path | str | None = None) -> str | None:
    """旧名 → **最新名**（沿链回溯）。没改过名 → `None`。

    `world=""` = 查所有世界线（WebGUI 的取图路径没有世界上下文, 而"改名"是
    作者对**表**做的事——消息里说出新名比说出"在哪个世界改的"有用）。
    环/自指 → 停在环上（返回当前值, 不无限转）。
    """
    key = (key or "").strip()
    if not key:
        return None
    worlds = [world] if world else all_worlds(worlds_dir=worlds_dir)
    for w in worlds:
        chain = _chain(w, worlds_dir=worlds_dir)
        if key not in chain:
            continue
        seen = {key}
        cur = chain[key]
        while cur in chain and cur not in seen:
            seen.add(cur)
            cur = chain[cur]
        if cur != key:
            return cur
    return None


def explain(key: str, *, world: str = "",
            worlds_dir: Path | str | None = None) -> str:
    """人话解释（没改过名 → `""`）——给"素材未找到"那条 alert 用。"""
    new = resolve(key, world=world, worlds_dir=worlds_dir)
    if not new:
        return ""
    reason = ""
    worlds = [world] if world else all_worlds(worlds_dir=worlds_dir)
    for w in worlds:
        for row in load(w, worlds_dir=worlds_dir):
            # 取**这一段**（`from == key`）的原因 —— 链上的原因各是各的,
            # 第一次改名的理由才是"为什么这个旧名不在了"
            if str(row.get("from")) == key and str(row.get("reason") or ""):
                reason = str(row["reason"])
    tail = f"（{reason}）" if reason else ""
    return f"key {key!r} 已改名为 {new!r}{tail} —— 旧事件按旧名回放, 素材请按新名找"


def append(old: str, new: str, *, world: str, reason: str = "", events: int = 0,
           worlds_dir: Path | str | None = None, ts: str | None = None) -> dict:
    """登记一条改名（**append**）。返回落盘的那一行。

    拒绝: 空名 / 同名 / 会成环（`new` 沿链走回 `old`）。目录不存在 → 创建。
    """
    old, new = (old or "").strip(), (new or "").strip()
    if not old or not new:
        raise ValueError("改名台账: from/to 不能为空")
    if old == new:
        raise ValueError("改名台账: from == to，没有变化")
    # 成环检查: 从 `new` 沿链走, 若最终走回 `old` ⇒ 这条登记会把两条名字接成环
    if resolve(new, world=world, worlds_dir=worlds_dir) == old:
        raise ValueError(f"改名台账: {old!r} → {new!r} 会成环"
                         f"（{new!r} 已（间接）指回 {old!r}）")
    row = {
        "ts": ts or datetime.now().isoformat(timespec="seconds"),
        "from": old,
        "to": new,
        "reason": reason,
        "events": int(events),
    }
    p = ledger_path(world, worlds_dir=worlds_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    reset_cache()
    return row


__all__ = [
    "LEDGER_NAME",
    "all_worlds",
    "append",
    "explain",
    "ledger_path",
    "load",
    "reset_cache",
    "resolve",
]
