"""seed.py — 出厂 digest pass（AGENT_BRAIN.md §3 Step 0 / M1c）。

世界线创建时执行一次: 读 config/characters/{char}/experience.yml + knowledge.yml
**原文（只读, 不做副本）**——2026-09-02 决策:
    - digest 产物（canon_fact 条目 + source_key 溯源）本身就是该世界线的出厂快照,
      无需再拷 yml; config 是作者真源, 运行时零写入
    - 作者改 config → 只影响新世界线; 旧世界线出厂记忆保持出厂时状态（immutable 语义）
    - 修复传播走显式 re-seed 维护命令（后续工具, 不自动同步）

v1: 确定性映射（无 LLM）——yml 每片叶子文本 → fact 节点:
    source_key = 剥离 SIG~/REQ~ 前缀后的字段路径（列表项 1-based 编号）,
    例: self.regular.1 / main.2 / valentine.sensei / friends.aru / technique.1 / places.杂草屋
    LLM 润色（tags/significance 重估）后置, 不阻塞主链。

幂等: 以 (source, source_key) 为键, 已存在则跳过——重复 seed 不产生双份。
出厂基座 immutable: 只允许 notes 追加（store.update 护栏）。
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
SIG_EXPERIENCE = 0.9      # 久远的记忆（预设经历）
SIG_KNOWLEDGE = 0.7       # 我知道的事（出厂认知）

_PREFIXES = ("SIG~", "REQ~")
_SKIP_LEAF = {"true", "false", "null", "none", "~", ""}


@dataclass
class SeedResult:
    """出厂 digest 结果。"""

    created: list[str] = field(default_factory=list)    # 新条目 id
    skipped: list[str] = field(default_factory=list)    # 已存在的 source_key（幂等跳过）
    errors: list[str] = field(default_factory=list)
    total: int = 0                                      # 本次扫描到的候选数


def seed_from_config(
    store: WikiStoreV2,
    char_dir: str | Path,
) -> SeedResult:
    """出厂消化: experience/knowledge → canon_fact 条目（幂等, 落 evolution_log）。

    Args:
        store: 目标世界线的 wiki（空库或已有出厂条目的库——后者按 source_key 跳过）
        char_dir: config/characters/{char_id}/ 目录

    Returns:
        SeedResult: 新条目 id / 跳过的 source_key / 错误
    """
    result = SeedResult()
    char_dir = Path(char_dir)
    log = EvolutionLog.for_store(store)
    existing = {
        (n.source, n.source_key)
        for n in store.all() if n.kind == "fact" and n.source_key
    }
    now = datetime.now().isoformat(timespec="seconds")

    for source, filename, significance in (
        ("experience", "experience.yml", SIG_EXPERIENCE),
        ("knowledge", "knowledge.yml", SIG_KNOWLEDGE),
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
                "fact",
                content=text,
                epistemic="canon_fact",
                source=source,
                source_key=source_key,
                significance=significance,
                ts=now,
            )
            nid = store.add(node)
            result.created.append(nid)
            log.append({"pkg": "seed", "action": "create",
                        "id": nid, "kind": "fact",
                        "detail": f"{source}:{source_key}"})
    return result


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
