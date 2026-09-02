"""图式 wiki 节点数据结构（AGENT_BRAIN.md §1）。

4 种节点（kind, 2026-09-02 砍 relation——两参考系统(A-MEM/AgentGal)均无此层,
信息落 tags/subject; 无生产数据, 窗口期移除）:
    fact       出厂基座（canon_fact, immutable）——experience/knowledge 出厂消化产出
    episode    一次性经历（narration 第一人称浓缩 + verbatim 原话; 质感优先不升华）
    experience 重复模式（pattern + count 聚合; subject=player = 玩家口癖, R5 强调点）
    belief     抽象认知（inferred_belief, links 必须 ≥1 支撑; history 记录改写溯源）

通用字段: id / kind / significance / epistemic / observer / tags / segment_id /
          event_seq / ts / source / links / contradictions
专属字段: episode.title(可选短标题) / belief.subject / belief.growth /
          belief.observation / belief.history[{episode_id, content, ts}]

observer 语义（2026-09-02 收敛）: 单视角世界线里 observed_fact 的观察者恒为
角色本人——引擎填 char_id, 不交给 LLM; reported_fact 的 observer = 转述者
（LLM 判断, 渲染为"听 X 说的"）。

关键规则（引擎侧强制, 此处提供 validate/normalize 支撑）:
    - epistemic: canon_fact | observed_fact | reported_fact | inferred_belief | speculation
    - fact.epistemic == canon_fact; belief.epistemic == inferred_belief（护栏）
    - belief.links 非空（无支撑升华拒绝, §5 校验规则 4）
    - significance: decimal 0~1, 珍贵档 ≥ PRECIOUS_THRESHOLD(0.8)（保底通道）
    - 去重键 = (kind, event_seq): 同事件重复消化 → 去重; 不同事件同类 → accrue（不删）
    - player experience（subject=player）永不被内容去重/合并掉（§4.4）

id 格式（决策 #7）: 前缀 + 4 位零填充, 无 # 无下划线 —— m0003 / c0002 / e0002。
序列化: jsonl 一行一条（to_json_line / from_json_line）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: 节点类型（relation 已砍, 2026-09-02）
KINDS = ("fact", "episode", "experience", "belief")
#: 认知类型（DESIGN_BRAIN.md §7）
EPISTEMICS = ("canon_fact", "observed_fact", "reported_fact", "inferred_belief", "speculation")
#: 珍贵档阈值（保底通道 / 对应 neuron 草稿的 memo 档）
PRECIOUS_THRESHOLD = 0.8
#: player experience 的 subject 固定值（玩家口癖/习惯, R5）
PLAYER_SUBJECT = "player"
#: 出厂基座 source 取值（fact 节点专用）
_SEED_SOURCES = ("experience", "knowledge")

#: 各 kind 的必填字段（validate 用）
_REQUIRED: dict[str, tuple[str, ...]] = {
    "fact": ("content", "source_key"),
    "episode": ("narration",),
    "experience": ("pattern", "subject"),
    "belief": ("content",),
}


def format_id(prefix: str, seq: int) -> str:
    """id 格式: 前缀 + 4 位零填充（m0003 / c0002 / e0002）。"""
    return f"{prefix}{seq:04d}"


@dataclass
class BrainNode:
    """一条图式 wiki 节点（宽松 dataclass: 全部字段可缺省, 校验走 validate()）。

    按 kind 取用的专属字段:
        episode:    narration(必填) / verbatim(可选原话) / title(可选短标题 8-16 字)
        experience: pattern(必填) / subject(必填) / count(引擎数 links) / examples(≤3)
        belief:     content(必填) / subject(认知对象, 可空) / growth / observation[]
                    / history[改写溯源]（2026-09-02: {episode_id, content, ts} 数组）
        fact:       content(必填) / source_key(必填, 溯源到 yml 字段)
    """

    id: str = ""
    kind: str = "episode"
    significance: float = 0.5
    epistemic: str = "observed_fact"
    observer: str = ""          # observed → 角色本人(引擎填); reported → 转述者(LLM)
    tags: list[str] = field(default_factory=list)
    segment_id: str | None = None
    event_seq: list[int] = field(default_factory=list)
    ts: str = ""
    source: str = "digest"
    links: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # 出厂基座只允许追加注记（§5 规则 2）
    # ── kind 专属 ──
    narration: str = ""
    verbatim: str = ""
    title: str = ""             # episode 可选短标题（渲染压缩/回放/决策表引用）
    pattern: str = ""
    subject: str = ""
    count: int = 0
    examples: list[str] = field(default_factory=list)
    content: str = ""
    growth: str = ""
    observation: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)   # belief 改写溯源（见 docstring）
    source_key: str = ""

    # ------------------------------------------------------------------
    # 校验（字段级; 契约层/组织 pass 在引擎侧再叠加引用级校验）
    # ------------------------------------------------------------------

    def validate(self) -> list[str]:
        """返回错误列表（空 = 通过）。宁缺勿错: 任何错误 → 引擎拒绝该条目。"""
        errors: list[str] = []
        if self.kind not in KINDS:
            errors.append(f"未知 kind: {self.kind!r}")
            return errors
        if self.epistemic not in EPISTEMICS:
            errors.append(f"非法 epistemic: {self.epistemic!r}（可用: {', '.join(EPISTEMICS)}）")
        for f in _REQUIRED[self.kind]:
            if not str(getattr(self, f, "") or "").strip():
                errors.append(f"{self.kind} 缺少必填字段: {f}")
        # epistemic 护栏（DESIGN_BRAIN.md §7）
        if self.kind == "fact" and self.epistemic != "canon_fact":
            errors.append("fact 节点 epistemic 必须是 canon_fact（出厂基座只读）")
        if self.kind == "fact" and self.source not in _SEED_SOURCES:
            errors.append(f"fact 节点 source 必须是 {'/'.join(_SEED_SOURCES)}（出厂 digest 产出）")
        if self.kind == "belief" and self.epistemic != "inferred_belief":
            errors.append("belief 节点 epistemic 必须是 inferred_belief（认知不伪装成事实）")
        if self.kind == "belief" and not self.links:
            errors.append("belief 必须 links ≥1 条支撑（episode|experience）——无支撑升华拒绝")
        if self.kind in ("episode", "experience") \
                and self.epistemic not in ("observed_fact", "reported_fact"):
            errors.append(f"{self.kind} 节点 epistemic 只能是 observed_fact/reported_fact")
        # history 只属于 belief（改写溯源, 引擎写入）
        if self.history and self.kind != "belief":
            errors.append("history 字段只属于 belief 节点（改写溯源）")
        # 数量边界
        if len(self.examples) > 3:
            errors.append("experience.examples 最多 3 条")
        if self.count < 0:
            errors.append("experience.count 不能为负")
        # significance 边界（decimal 0~1）
        if not (0.0 <= self.significance <= 1.0):
            errors.append(f"significance 越界: {self.significance}（须 0~1）")
        return errors

    def normalize(self) -> "BrainNode":
        """引擎侧归一（不校验, 只修不变量）:
        significance clamp 0~1; experience.count = len(links); examples 截断 3。
        """
        self.significance = max(0.0, min(1.0, float(self.significance)))
        if self.kind == "experience":
            self.count = len(self.links)
            self.examples = self.examples[:3]
        return self

    # ------------------------------------------------------------------
    # 派生属性
    # ------------------------------------------------------------------

    @property
    def is_precious(self) -> bool:
        """珍贵档（保底通道）: significance ≥ 0.8。"""
        return self.significance >= PRECIOUS_THRESHOLD

    @property
    def main_text(self) -> str:
        """节点主文本（渲染/检索/去重的主内容）: episode→narration, experience→pattern,
        其余→content。全模块经此取文本——不做逐处 kind 分支。"""
        if self.kind == "episode":
            return self.narration
        if self.kind == "experience":
            return self.pattern
        return self.content

    @property
    def is_player_experience(self) -> bool:
        """玩家口癖/习惯节点（R5 强调点, §4.4 去重豁免）。"""
        return self.kind == "experience" and self.subject == PLAYER_SUBJECT

    def dedup_key(self) -> tuple:
        """去重键 = (kind, event_seq)——同事件重复消化去重; 不同事件同类走 accrue 不删。"""
        return (self.kind, tuple(self.event_seq))

    def is_seed(self) -> bool:
        """出厂基座（immutable——update 只允许 notes 追加, 2026-09-02 v2 扩展）:
        knowledge → fact(canon_fact); experience → 出厂 episode(source=experience,
        与 bond digest 产物同构的预设记忆——同渲染段同护栏, 见 seed.py v2）。"""
        if self.kind == "fact" and self.epistemic == "canon_fact":
            return True
        return self.kind == "episode" and self.source == "experience"

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """→ dict（空/缺省可选字段省略——行小; id/kind/significance/epistemic 恒在）。"""
        d: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "significance": self.significance,
            "epistemic": self.epistemic,
        }
        for f in ("observer", "tags", "segment_id", "event_seq", "ts", "source",
                  "links", "contradictions", "notes", "narration", "verbatim", "title",
                  "pattern", "subject", "count", "examples", "content", "growth",
                  "observation", "history", "source_key"):
            v = getattr(self, f)
            if v in (None, "", [], 0):
                continue
            d[f] = v
        return d

    @classmethod
    def from_dict(cls, raw: dict | None) -> "BrainNode":
        """宽松解析（宁缺勿错: 坏字段取默认, 不 raise; 校验走 validate()）。"""
        if not isinstance(raw, dict):
            return cls()
        node = cls()
        node.id = _str(raw.get("id"))
        kind = _str(raw.get("kind"))
        node.kind = kind if kind in KINDS else "episode"
        node.significance = _clamp_sig(raw.get("significance"))
        epi = _str(raw.get("epistemic"))
        node.epistemic = epi if epi in EPISTEMICS else "observed_fact"
        node.observer = _str(raw.get("observer"))
        node.tags = _str_list(raw.get("tags"))
        node.segment_id = _str(raw.get("segment_id")) or None
        node.event_seq = _int_list(raw.get("event_seq"))
        node.ts = _str(raw.get("ts"))
        node.source = _str(raw.get("source")) or "digest"
        node.links = _str_list(raw.get("links"))
        node.contradictions = _str_list(raw.get("contradictions"))
        node.notes = _str_list(raw.get("notes"))
        # kind 专属
        node.narration = _str(raw.get("narration"))
        node.verbatim = _str(raw.get("verbatim"))
        node.title = _str(raw.get("title"))
        node.pattern = _str(raw.get("pattern"))
        node.subject = _str(raw.get("subject"))
        node.count = _int(raw.get("count"))
        node.examples = _str_list(raw.get("examples"))
        node.content = _str(raw.get("content"))
        node.growth = _str(raw.get("growth"))
        node.observation = _str_list(raw.get("observation"))
        node.history = _dict_list(raw.get("history"))
        node.source_key = _str(raw.get("source_key"))
        return node

    def to_json_line(self) -> str:
        """jsonl 一行（紧凑, 中文不转义）。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json_line(cls, line: str) -> "BrainNode":
        """jsonl 一行 → 节点（坏行 → 空节点, 宁缺勿错）。"""
        try:
            return cls.from_dict(json.loads(line))
        except (ValueError, TypeError):
            return cls()


def make_node(kind: str, **kw) -> BrainNode:
    """构造 + 归一（引擎写入前用）: normalize() 后返回。

    调用方负责 validate()（make_node 不抛——校验决策留给引擎/契约层）。
    """
    raw = dict(kw)
    raw["kind"] = kind
    node = BrainNode.from_dict(raw)
    return node.normalize()


# ---------------------------------------------------------------------------
# 内部: 宽松取值助手
# ---------------------------------------------------------------------------

def _str(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _str_list(v: Any) -> list[str]:
    if not isinstance(v, list):
        return []
    return [x.strip() for x in v if isinstance(x, str) and x.strip()]


def _dict_list(v: Any) -> list[dict]:
    """history 等 dict 数组的宽松读取（宁缺勿错: 只收 dict, 不收坏项）。"""
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, dict)]


def _int_list(v: Any) -> list[int]:
    if not isinstance(v, list):
        return []
    out: list[int] = []
    for x in v:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _clamp_sig(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, f))
