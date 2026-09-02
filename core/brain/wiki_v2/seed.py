"""seed.py — 出厂 digest pass（AGENT_BRAIN.md §3 Step 0 / M1c）。

世界线创建时执行一次: 读 config/characters/{char}/experience.yml + knowledge.yml
**原文（只读, 不做副本）**——2026-09-02 决策:
    - digest 产物本身就是该世界线的出厂快照, 无需再拷 yml;
      config 是作者真源, 运行时零写入
    - 作者改 config → 只影响新世界线; 旧世界线出厂记忆保持出厂时状态（immutable 语义）
    - 修复传播走显式 re-seed 维护命令（后续工具, 不自动同步）

v2（2026-09-02 用户拍板: experience 应与 bond story 对等——预设记忆 = 角色
记得的经历, 不是"我知道的事"）:
    - experience.yml → **episode 节点**（与运行期 bond digest 产物同构）:
        kind=episode / epistemic=observed_fact / narration=原文（渲染层 _me()
        做第一人称转换）/ source=experience / significance 0.9（出厂锚）
      ——注入渲染进"我记得的事（珍贵的）"段, 与 bond 闭环消化出的记忆同段;
      belief 由运行期 digest 对真实互动自然组织（出厂单条经历不构成重复模式）
    - knowledge.yml → fact（canon_fact）不变（"我知道的事"确实是事实）
    - 出厂基座 immutable 扩展: is_seed = fact(canon_fact) | episode(source=experience)
    - 旧库迁移: kind=fact & source=experience（v1 残留）→ 删除重建为 episode
      （幂等判重键 (source, source_key) 不变——干净库直接建, 旧库先迁后建）
    - **落盘修复（2026-09-02）**: 此前 add 只进内存不 save → wiki.jsonl 恒空 →
      每次触发都重 seed → evolution.jsonl 重复 append; 现在有变更即 store.save()

幂等: 以 (source, source_key) 为键, 已存在则跳过——重复 seed 不产生双份。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.brain.wiki_v2.evolution import EvolutionLog
from core.brain.wiki_v2.nodes import make_node
from core.brain.wiki_v2.store import WikiStoreV2
from core.parsing.dynamic_character_parser import load_yaml_file

#: 默认显著性（出厂记忆是角色记忆的锚, 给高值; LLM 重估后置）
SIG_EXPERIENCE = 0.9      # 预设经历（episode, 珍贵档保底）
SIG_KNOWLEDGE = 0.7       # 我知道的事（出厂认知）

_PREFIXES = ("SIG~", "REQ~")
_SKIP_LEAF = {"true", "false", "null", "none", "~", ""}


@dataclass
class SeedResult:
    """出厂 digest 结果。"""

    created: list[str] = field(default_factory=list)    # 新条目 id
    skipped: list[str] = field(default_factory=list)    # 已存在的 source_key（幂等跳过）
    migrated: list[str] = field(default_factory=list)   # 旧 v1 fact 迁移删除的 source_key
    errors: list[str] = field(default_factory=list)
    total: int = 0                                      # 本次扫描到的候选数


def seed_from_config(
    store: WikiStoreV2,
    char_dir: str | Path,
) -> SeedResult:
    """出厂消化: experience → episode / knowledge → fact（幂等, 落 evolution_log）。

    Args:
        store: 目标世界线的 wiki（空库或已有出厂条目的库——后者按 source_key 跳过）
        char_dir: config/characters/{char_id}/ 目录

    Returns:
        SeedResult: 新条目 id / 跳过的 source_key / 迁移数 / 错误
    """
    result = SeedResult()
    char_dir = Path(char_dir)
    log = EvolutionLog.for_store(store)
    now = datetime.now().isoformat(timespec="seconds")

    # ── 旧库迁移（v1 残留: experience 曾建模为 fact——v2 语义 = 预设经历 episode）──
    migrated = _migrate_v1_experience_facts(store, log, now)
    result.migrated = migrated

    existing = {
        (n.source, n.source_key)
        for n in store.all() if n.source_key and (
            n.kind == "fact" or n.source == "experience")
    }

    for source, filename, significance, kind, in (
        ("experience", "experience.yml", SIG_EXPERIENCE, "episode"),
        ("knowledge", "knowledge.yml", SIG_KNOWLEDGE, "fact"),
    ):
        path = char_dir / filename
        if not path.exists():
            result.errors.append(f"{filename} 缺失（跳过）")
            continue
        try:
            data = load_yaml_file(path)
        except Exception as e:                            # noqa: BLE001
            result.errors.append(f"{filename} 解析失败: {e}")
            continue
        leaves = _collect_leaves(data)
        for source_key, text in leaves:
            result.total += 1
            if (source, source_key) in existing:
                result.skipped.append(source_key)
                continue
            node = make_node(
                kind,
                content=text if kind == "fact" else "",   # fact 存 content
                epistemic="canon_fact" if kind == "fact" else "observed_fact",
                narration=text if kind == "episode" else "",  # episode 存 narration
                source=source,
                source_key=source_key,
                significance=significance,
                ts=now,
            )
            nid = store.add(node)
            result.created.append(nid)
            log.append({"pkg": "seed", "action": "create",
                        "id": nid, "kind": kind,
                        "detail": f"{source}:{source_key}"})
    # 落盘修复（2026-09-02）: seed 是自含写入口——有变更立即 save,
    # 否则 add 只进内存 → 下次触发重 seed + 日志重复 append
    if result.created or result.migrated:
        try:
            store.save()
        except Exception as e:                            # noqa: BLE001 — 落盘失败降级
            result.errors.append(f"wiki 落盘失败: {e}")
    return result


def _migrate_v1_experience_facts(store: WikiStoreV2, log: EvolutionLog,
                                 now: str) -> list[str]:
    """迁移 v1 残留: experience 曾以 fact(canon_fact, source=experience) 建模——
    v2 语义预设经历 = episode。删除旧 fact（episode 化重建, 语义取代）; 干净库
    空操作。删的是出厂基座——迁移本身是引擎升级动作, 绕过 immutable 护栏直删。
    """
    removed: list[str] = []
    for n in store.all():
        if n.kind == "fact" and n.source == "experience":
            store.delete(n.id)
            removed.append(n.source_key or n.id)
            log.append({"pkg": "seed", "action": "migrate",
                        "id": n.id, "kind": "fact",
                        "detail": f"experience:{n.source_key}（v1 fact → v2 episode）",
                        "ts": now})
    return removed


# ---------------------------------------------------------------------------
# yml → 叶子（source_key, 文本）通用 walker
# ---------------------------------------------------------------------------

def _collect_leaves(data: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """递归拍平 yml 树 → [(source_key, 文本), …]。

    规则:
        - dict: 键路径拼接（剥离 SIG~/REQ~ 前缀; null 值跳过）
        - list: 单键 dict 项 → 用其键作路径段（numbered 条目, 如 {1: text}）;
                纯值项 → 1-based 序号（technique.1）
        - 叶子: 非空文本（bool/None 类占位跳过）
    """
    out: list[tuple[str, str]] = []
    _walk(data, prefix, out)
    return out


def _walk(node: Any, path: str, out: list[tuple[str, str]]) -> None:
    if node is None:
        return
    if isinstance(node, dict):
        for k, v in node.items():
            if not isinstance(k, str):
                continue
            _walk(v, _join(path, _strip_prefix(k)), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, dict) and len(v) == 1:
                (k, vv), = v.items()                      # numbered 条目 {1: text}
                _walk(vv, _join(path, str(k)), out)
            else:
                _walk(v, _join(path, str(i + 1)), out)    # 纯值项 1-based
    else:
        text = str(node).strip()
        if text.lower() not in _SKIP_LEAF and path:
            out.append((path, text))


def _join(path: str, seg: str) -> str:
    return f"{path}.{seg}" if path else seg


def _strip_prefix(key: str) -> str:
    for p in _PREFIXES:
        if key.startswith(p):
            return key[len(p):]
    return key
