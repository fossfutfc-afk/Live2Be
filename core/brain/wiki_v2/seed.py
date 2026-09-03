"""seed.py — 出厂 digest pass（AGENT_BRAIN.md §3 Step 0 / M1c）。

世界线创建时执行一次: 读 config/characters/{char}/experience.yml + beliefs.yml
**原文（只读, 不做副本）**——2026-09-02 决策:
    - digest 产物本身就是该世界线的出厂快照, 无需再拷 yml;
      config 是作者真源, 运行时零写入
    - 作者改 config → 只影响新世界线; 旧世界线出厂记忆保持出厂时状态
    - 修复传播走显式 re-seed 维护命令（后续工具, 不自动同步）

v3（2026-09-02 定稿: 出厂 wiki = **纯记忆**, 出厂与运行时 digest 产物同构）:
    - experience.yml → **episode**（observed_fact, narration 原文, sig 0.9 出厂锚,
      immutable——is_seed = episode(source=experience)）
    - beliefs.yml（可选, guidance/beliefs.md 教学）→ **belief**（inferred_belief,
      subject/content/links 校验 source_key → 真实 episode id; sig 默认 0.85;
      出厂 belief **不 immutable**——认知种子, 运行时 digest 的 touch/update 演化）
    - knowledge.yml **不再出厂化**（fact 退役, 2026-09-02 用户拍板: "我知道的事"
      是世界观知识 = overview.yml common 语义——config 档案职责: system prompt
      注入 + interperson 读取; wiki 只存记忆, 世界观知识库中期另立）
    - 旧库 fact（v1 experience-fact / v2 knowledge-fact）: 加载层自动过滤
      （kind=fact 已不在 KINDS → validate 拒 → 跳过）, 下次整写 save 自动清除

v4（2026-09-04 定稿: **brain_seed 定稿制**——出厂经历一次定稿, seed 确定性复制）:
    - config/characters/{c}/brain_seed.yml（tools/seed_digest.py 生成 + 作者 review
      手改）存在 → 出厂 episode **从定稿复制**（narration 第一人称记忆 +
      title/verbatim/significance 逐条入档, source/source_key 与原文分支同键判重）
    - 无 brain_seed.yml → 原文兜底（上方 v3 逻辑——角色可玩性永不阻塞）
    - 世界线创建时把定稿输入**快照进世界线**（seed_snapshot/）——回退/重建与
      config 后续修改解耦（作者改卡只影响之后创建的世界线）

幂等: experience/brain_seed episode 以 (source, source_key) 判重; belief 以
(source, source_key=belief.N) 判重——重复 seed 零新增零日志重复。
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


def _load_yaml_any(path: Path):
    """通用 yaml 读（beliefs.yml 顶层是 list——load_yaml_file 只收 dict）。"""
    import yaml
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)

#: 默认显著性（出厂记忆是角色记忆的锚; LLM 重估后置）
SIG_EXPERIENCE = 0.9       # 预设经历（episode, 珍贵档保底）
SIG_BELIEF = 0.85          # 出厂认知（belief 种子; 运行时 touch/update 演化）

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
    """出厂消化: 出厂 episode（定稿 brain_seed.yml 优先 / 原文兜底）+ beliefs.yml →
    belief（幂等, 落 evolution_log; 创建时快照定稿输入进世界线）。

    Args:
        store: 目标世界线的 wiki（空库或已有出厂条目的库——后者按 source_key 跳过）
        char_dir: config/characters/{char_id}/ 目录

    Returns:
        SeedResult: 新条目 id / 跳过的 source_key / 错误
    """
    result = SeedResult()
    char_dir = Path(char_dir)
    log = EvolutionLog.for_store(store)
    now = datetime.now().isoformat(timespec="seconds")

    # ── 出厂 episode: brain_seed.yml 定稿优先; 缺失 → experience.yml 原文兜底 ──
    seed_file = char_dir / "brain_seed.yml"
    if seed_file.exists():
        _seed_from_brain_seed(store, char_dir, seed_file, log, now, result)
    else:
        _seed_from_experience_yml(store, char_dir, log, now, result)

    # ── beliefs.yml → belief（可选; links 校验 source_key → 真实 episode id）──
    _seed_beliefs(store, char_dir, log, now, result)

    # ── 世界线创建快照: 定稿输入复制进世界线（回退/重建与 config 解耦）──
    if result.created:
        _snapshot_seed_inputs(store, char_dir)

    # 落盘（2026-09-02 根因修复: seed 是自含写入口——有变更立即 save, 否则
    # add 只进内存 → 下次触发重 seed + evolution 重复 append）
    if result.created:
        try:
            store.save()
        except Exception as e:                            # noqa: BLE001 — 落盘失败降级
            result.errors.append(f"wiki 落盘失败: {e}")
    return result


def _seed_from_experience_yml(store: WikiStoreV2, char_dir: Path,
                              log: EvolutionLog, now: str,
                              result: SeedResult) -> None:
    """v3 原文兜底: experience.yml 叶子 → episode（narration 原文, sig 0.9）。"""
    exp_existing = {
        (n.source, n.source_key)
        for n in store.all() if n.kind == "episode" and n.source == "experience"
    }
    exp_path = char_dir / "experience.yml"
    if not exp_path.exists():
        result.errors.append("experience.yml 缺失（跳过）")
        return
    try:
        data = load_yaml_file(exp_path)
    except Exception as e:                                # noqa: BLE001
        result.errors.append(f"experience.yml 解析失败: {e}")
        return
    for source_key, text in _collect_leaves(data):
        result.total += 1
        if ("experience", source_key) in exp_existing:
            result.skipped.append(f"experience:{source_key}")
            continue
        node = make_node(
            "episode",
            narration=text,
            epistemic="observed_fact",
            source="experience",
            source_key=source_key,
            significance=SIG_EXPERIENCE,
            ts=now,
        )
        nid = store.add(node)
        result.created.append(nid)
        log.append({"pkg": "seed", "action": "create",
                    "id": nid, "kind": "episode",
                    "detail": f"experience:{source_key}"})


def _seed_from_brain_seed(store: WikiStoreV2, char_dir: Path, seed_file: Path,
                          log: EvolutionLog, now: str,
                          result: SeedResult) -> None:
    """v4 定稿复制: brain_seed.yml episodes[] → episode（第一人称记忆成品,
    title/verbatim/significance 逐条入档; review_notes 是 beliefs 素材, 不落库）。

    判重键与原文分支一致 (source=experience, source_key)——中途补 brain_seed 的
    角色: 已有世界线保持原文（世界线语义）, 新世界线用定稿。
    """
    existing = {
        (n.source, n.source_key)
        for n in store.all() if n.kind == "episode" and n.source == "experience"
    }
    try:
        data = load_yaml_file(seed_file)
    except Exception as e:                                # noqa: BLE001
        result.errors.append(
            f"brain_seed.yml 解析失败: {e}——定稿文件损坏是作者侧问题; "
            f"请修复或删除后重跑 tools/seed_digest.py")
        return
    entries = data.get("episodes") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        result.errors.append("brain_seed.yml 缺 episodes 列表")
        return
    for e in entries:
        if not isinstance(e, dict):
            result.errors.append("brain_seed.yml episodes 含非对象条目（跳过）")
            continue
        sk = str(e.get("source_key") or "").strip()
        if not sk:
            result.errors.append("brain_seed.yml 有条目缺 source_key（跳过）")
            continue
        result.total += 1
        if ("experience", sk) in existing:
            result.skipped.append(f"experience:{sk}")
            continue
        narration = str(e.get("narration") or "").strip()
        if not narration:
            result.errors.append(f"brain_seed.yml {sk} 缺 narration（跳过——--only 重跑）")
            continue
        sig = e.get("significance")
        try:
            sig = float(sig) if sig is not None else SIG_EXPERIENCE
            if not 0 <= sig <= 1:
                raise ValueError
        except (TypeError, ValueError):
            result.errors.append(f"brain_seed.yml {sk} significance 非法: {sig!r}（跳过）")
            continue
        node = make_node(
            "episode",
            narration=narration,
            title=str(e.get("title") or "").strip() or None,
            verbatim=str(e.get("verbatim") or "").strip() or None,
            epistemic="observed_fact",
            source="experience",
            source_key=sk,
            significance=sig,
            ts=now,
        )
        nid = store.add(node)
        result.created.append(nid)
        log.append({"pkg": "seed", "action": "create",
                    "id": nid, "kind": "episode",
                    "detail": f"brain_seed:{sk}"})


def _snapshot_seed_inputs(store: WikiStoreV2, char_dir: Path) -> None:
    """世界线创建快照: 定稿输入（brain_seed.yml 或 experience.yml/beliefs.yml）
    复制进世界线 seed_snapshot/——回退/重建用世界线内快照, 与 config 解耦。

    幂等: 快照已存在同名文件 → 跳过（世界线内快照一旦写入不再更新——
    config 定稿的后续修改只影响之后创建的世界线）。快照失败不阻断 seed。
    """
    target = store.path.parent / "seed_snapshot"
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    names: list[str] = []
    if (char_dir / "brain_seed.yml").exists():
        names.append("brain_seed.yml")
    else:
        names.append("experience.yml")
    if (char_dir / "beliefs.yml").exists():
        names.append("beliefs.yml")
    for name in names:
        dst = target / name
        if dst.exists():
            continue
        try:
            dst.write_text((char_dir / name).read_text(encoding="utf-8"),
                           encoding="utf-8")
        except OSError:
            pass


def _seed_beliefs(store: WikiStoreV2, char_dir: Path, log: EvolutionLog,
                  now: str, result: SeedResult) -> None:
    """beliefs.yml（可选, guidance/beliefs.md）→ belief 节点。

    links 语义引用 experience.yml 的 source_key → 解析为真实 episode id;
    孤儿引用报错（列出可用键, 不静默）。幂等: source_key=belief.N。
    出厂 belief 不 immutable——认知种子, 运行时 touch/update 演化（见 nodes.is_seed）。
    """
    path = char_dir / "beliefs.yml"
    if not path.exists():
        return
    try:
        rows = _load_yaml_any(path)          # 顶层是 list（每个 - 一条 belief）
    except Exception as e:                   # noqa: BLE001
        result.errors.append(f"beliefs.yml 解析失败: {e}")
        return
    if not isinstance(rows, list):
        result.errors.append("beliefs.yml 必须是列表（每个 - 一条 belief）")
        return

    episodes = {n.source_key: n for n in store.all()
                if n.kind == "episode" and n.source == "experience"}
    existing = {n.source_key for n in store.all()
                if n.kind == "belief" and n.source == "beliefs"}

    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            result.errors.append(f"beliefs.yml 第 {i} 条不是对象（跳过）")
            continue
        sk = f"belief.{i}"
        if sk in existing:
            result.skipped.append(f"beliefs:{sk}")
            continue
        subject = str(row.get("subject") or "").strip()
        content = str(row.get("content") or "").strip()
        links_raw = row.get("links")
        if not subject or not content:
            result.errors.append(f"beliefs.yml 第 {i} 条缺 subject/content（跳过）")
            continue
        if not isinstance(links_raw, list) or not links_raw:
            result.errors.append(
                f"beliefs.yml 第 {i} 条 links 必须是数组（≥1 条支撑经历）（跳过）")
            continue
        links: list[str] = []
        bad: list[str] = []
        for ref in links_raw:
            ref = str(ref).strip()
            ep = episodes.get(ref)
            if ep is None:
                bad.append(ref)
            elif ep.id not in links:
                links.append(ep.id)
        if bad:
            result.errors.append(
                f"beliefs.yml 第 {i} 条 links 引用了不存在的经历: {bad}——"
                f"可用: {sorted(episodes) or '（无——experience.yml 为空）'}")
            continue
        sig = row.get("significance")
        try:
            sig = float(sig) if sig is not None else SIG_BELIEF
        except (TypeError, ValueError):
            sig = SIG_BELIEF
        node = make_node(
            "belief",
            content=content,
            subject=subject,
            epistemic="inferred_belief",
            source="beliefs",
            source_key=sk,
            links=links,
            significance=sig,
            ts=now,
        )
        nid = store.add(node)
        result.created.append(nid)
        result.total += 1
        log.append({"pkg": "seed", "action": "create",
                    "id": nid, "kind": "belief",
                    "detail": f"beliefs:{sk}"})


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
