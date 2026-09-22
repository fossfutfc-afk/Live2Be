"""图式 wiki 节点（AGENT_BRAIN.md §1）。

三种 kind（2026-09-02 fact 退役——记忆 = 经历 + 认知）:
    episode    一次性经历（text 第一人称浓缩 + verbatim 原话; 质感优先不升华）
    experience 重复模式（text 写规律）; subject="player" = 玩家口癖/画像（R5）
    belief     抽象认知（text 写结论; links ≥1 支撑; 可选 growth 成长方向）

不变量（validate/normalize 强制）:
    - epistemic: belief 恒 inferred_belief; episode/experience 只能 observed/reported
    - belief 必须有 `supports` 入边 —— ⚠️ 2026-09-21（G3）**搬到 `store.audit()`**:
      支撑关系住在边表里, 字段级校验看不见它
    - experience.examples ≤ 3
    - significance ∈ 0~1, 珍贵档 ≥ PRECIOUS_THRESHOLD(0.8); 越界 clamp
    - 去重键 = (kind, event_seq 有交集, 主文本相同) —— `revise._find_duplicate`

⚠️ 2026-09-21 大化简（判据 = 生产者/消费者/真机数据三方核对）——**删过的别再捡回来**:
    source_key · observation · speculation · source（连同 is_seed/notes/seed 桶/不可变守卫）·
    count（→派生 len(links)）· segment_id · emo_valence · history（→evolution 的 before/after）·
    main_text（属性）; 三槽 narration/pattern/content → **text**。
    ⚠️ 为什么没给三种正文形态配 `nature`: 它与 kind 双射 = 换词不换信息; v3 的 nature 是
    **认知层第四轴**（管合并策略）, 需 2-kind 模型 ⇒ 批 3（DESIGN_WIKI_V3 §2.3–2.5）。
    旧档里的这些键由 `from_dict` 宽松忽略（无迁移脚本）。

id: 前缀 + 4 位零填充（e0002 / m0003）; 序列化: jsonl 一行一条。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: 节点类型（fact 已退役, 2026-09-02——出厂与 digest 同构: 记忆 = 经历 + 认知）
KINDS = ("episode", "experience", "belief")
#: 认知类型（canon_fact 随 fact 退役; speculation 2026-09-21 删——三值全由护栏强制）
EPISTEMICS = ("observed_fact", "reported_fact", "inferred_belief")
#: 珍贵档阈值（保底通道 / 对应 neuron 草稿的 memo 档）
PRECIOUS_THRESHOLD = 0.8
#: player experience 的 subject 固定值（玩家口癖/习惯, R5）
PLAYER_SUBJECT = "player"

#: 各 kind 的必填字段（validate 用; 正文统一叫 `text`）
_REQUIRED: dict[str, tuple[str, ...]] = {
    "episode": ("text",),
    "experience": ("text", "subject"),
    "belief": ("text",),
}


def format_id(prefix: str, seq: int) -> str:
    """id 格式: 前缀 + 4 位零填充（m0003 / c0002 / e0002）。"""
    return f"{prefix}{seq:04d}"


@dataclass
class BrainNode:
    """一条图式 wiki 节点（宽松 dataclass: 字段可缺省, 校验走 validate()）。

    字段分组:
        共用    id / kind / significance / text / epistemic / observer / tags /
                event_seq / ts / links / contradictions(休眠)
        episode title / verbatim / verbatim_seq / emo_shape / place / place_raw /
                aff_at_encoding / emo_int / emo_span
        认知     subject / examples / growth        （experience / belief）
    """

    # ── 共用（三种 kind 都有）──
    id: str = ""
    kind: str = "episode"
    significance: float = 0.5
    epistemic: str = "observed_fact"
    observer: str = ""          # 信息来源: 空 = 亲历; 非空 = 转述者（LLM 填, 渲染"听X说的"）
    tags: list[str] = field(default_factory=list)
    event_seq: list[int] = field(default_factory=list)
    ts: str = ""
    #: ⏸ **旧档读入专用**（2026-09-21 G3）: 边已搬到 `soul/edges.jsonl`（类型化 +
    #: 有向）, 本字段**不再被写出**（`to_dict` 不产它）; 只剩一个用途 —— 无边界表的
    #: 旧档**自举**时被 `graph.infer_edges` 读一次（读不出来的类型发 `unknown`）。
    links: list[str] = field(default_factory=list)
    #: ⏸ 同上（旧档读入专用）; 今天零生产者、真机零数据, 自举时映射成 `contradicts` 边。
    contradictions: list[str] = field(default_factory=list)
    #: **这条记忆的正文**（三种 kind 共用一槽; 原 `narration`/`pattern`/`content` 2026-09-21 合流）。
    #: 写作口径仍按 kind 分（episode=第一人称浓缩 / experience=规律 / belief=结论）——那是
    #: rules/schema 的语义, 不再由字段名承担。旧档的旧名由 `from_dict` 兼容读入。
    text: str = ""
    # ── episode 专属 ──
    verbatim: str = ""
    #: `verbatim` 的**索引通道**（地址如 `"28.3"`/`"20.p"`, 词表 = `contract/timeline_index.py`）。
    #: 上游: 引擎据此回填文本; 地址永久有效（`events.jsonl` append-only）⇒ 可重解析。
    #: ⚠️ 消费字段是 `verbatim`（文本）——索引解析不出时以文本兜底。
    verbatim_seq: list[str] = field(default_factory=list)
    #: **板级情绪键序列**（如 `["tease","smile"]`）——B 链路（情绪序列 RAG）唯一输入。
    #: 由 digest 按 `event_seq` 从真源物化（能重算 ⇒ 不是第二真源）。
    #: 🚫 **绝不进 LLM 上下文**（召回侧信号; `render_*` 一律不输出）。
    emo_shape: list[str] = field(default_factory=list)
    #: **地点键序列**（素材轴）——板首 switch 的键 + 句级锚点, 相邻去重保序; 由 digest
    #: 按 `event_seq` 从真源物化（能重算 ⇒ 不是第二真源）。
    #: ⚠️ 键相等只声称"**同一张图**", 不声称"同一个地方"（语义轴见 `place_raw`）。
    #: 🚫 **绝不进 LLM 上下文**（召回侧信号, 同 `emo_shape`）。
    place: list[str] = field(default_factory=list)
    #: **writer 原文序列**（叙事轴）——板首 `place_hint` 的名词短语, 由 digest 物化。
    #: 与 `place` 是两根**正交**轴: `place` 字面相等 = 同一张图（判回放画哪张）;
    #: 本字段走语义相似 = 同一个地方（判"是不是那儿"）。键**不是**地名的双射
    #: （一键多义 / 一地多键都实测存在）⇒ 两根轴不可互替。🚫 不进 LLM 上下文。
    place_raw: list[str] = field(default_factory=list)
    #: episode 可选短标题（Round A 必填, 承载本章标题）
    title: str = ""
    # ── 认知专属（experience / belief）──
    subject: str = ""
    examples: list[str] = field(default_factory=list)
    growth: str = ""
    # ── episode 数值（None = 未采集; 0.0 是合法值——两者不可合并）──
    #: 编码时好感标量 ∈ [−1, 1]（`Affection.to_scalar()`）——**快照**: 写入时定、永不改。
    #: 真源是 `affection` 事件流, 本字段只是省掉每次召回重放。
    aff_at_encoding: float | None = None
    #: 峰值情绪强度 ∈ [0, 1]（Round A 出值）——**峰值**不是均值。
    #: None = 未采集; **0.0 也是合法值**（确实毫无波澜）。
    emo_int: float | None = None
    #: 情绪**摆幅** ∈ [0, 1]（Round A 出值）——**非负**、无符号（方向在 emo_shape 的键里）。
    #: span 高 int 高 = 先炸后真心笑; span 高 int 低 = 缓慢起伏; int 高 span 低 = 一直很猛没转折。
    emo_span: float | None = None
    # ⏸ 已删/退役（旧档键由 from_dict 忽略）: emo_valence(2026-09-21) · story_time(2026-09-17)

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
        # epistemic 护栏（DESIGN_BRAIN.md §7; canon_fact 随 fact 退役 2026-09-02）
        if self.kind == "belief" and self.epistemic != "inferred_belief":
            errors.append("belief 节点 epistemic 必须是 inferred_belief（认知不伪装成事实）")
        # ⚠️ 原「belief 必须 links ≥1 条支撑」2026-09-21（G3）**搬走** —— 支撑关系现在
        # 住在边表（`edges.jsonl` 的 `supports` 入边）, 字段级校验看不见它。新家两处:
        # ① 写路径 `revise.apply_decisions` 建完节点立刻补 `supports` 边;
        # ② 全局兜底 `store.audit()`（"belief 无支撑"）。
        if self.kind in ("episode", "experience") \
                and self.epistemic not in ("observed_fact", "reported_fact"):
            errors.append(f"{self.kind} 节点 epistemic 只能是 observed_fact/reported_fact")
        # 数量边界
        if self.kind == "experience" and len(self.examples) > 3:
            errors.append("experience.examples 最多 3 条")
        # significance 边界（decimal 0~1）
        if not (0.0 <= self.significance <= 1.0):
            errors.append(f"significance 越界: {self.significance}（须 0~1）")
        return errors

    def normalize(self) -> "BrainNode":
        """引擎侧归一: significance clamp 0~1; examples 截断 3。"""
        self.significance = max(0.0, min(1.0, float(self.significance)))
        if self.kind == "experience":
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
    def is_player_experience(self) -> bool:
        """玩家口癖/习惯节点（R5 强调点, §4.4 去重豁免）。"""
        return self.kind == "experience" and self.subject == PLAYER_SUBJECT

    # ⏸ `count` 属性 2026-09-21（G3）**删** —— 它原是 `len(links)` 的派生属性, 而
    # `links` 已停止写入（边搬到 `edges.jsonl`）⇒ 留着它只会恒返回 0（静默假数据）。
    # 新家: `render._count_of(node, graph)` = `supports` **入边数**（边表的真事实）。

    def dedup_key(self) -> tuple:
        """去重键 = (kind, event_seq)——同事件重复消化去重; 不同事件同类走 accrue 不删。"""
        return (self.kind, tuple(self.event_seq))

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """→ dict（空/缺省字段省略以缩小行; count 派生不落库, 旧键由 from_dict 忽略）。

        ⚠️ `links` / `contradictions` **不写出**（2026-09-21 G3）: 边已搬到
        `soul/edges.jsonl`, 点表再写一份就是第二个真源。`from_dict` 仍然读它们
        （旧档自举要）, 所以是"读得进、写不出"的单向兼容。
        """
        d: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "significance": self.significance,
            "epistemic": self.epistemic,
        }
        for f in ("observer", "tags", "event_seq", "ts",
                  "text", "verbatim",
                  "verbatim_seq", "title", "emo_shape", "place",
                  "place_raw",
                  "subject", "examples", "growth"):
            v = getattr(self, f)
            if v in (None, "", [], 0):
                continue
            d[f] = v
        # 这三个用 None 当"未采集"哨兵, 而 0.0 是合法值 ⇒ 不进上面的空值省略
        for f in ("aff_at_encoding", "emo_int", "emo_span"):
            v = getattr(self, f)
            if v is not None:
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
        node.event_seq = _int_list(raw.get("event_seq"))
        node.ts = _str(raw.get("ts"))
        node.links = _str_list(raw.get("links"))
        node.contradictions = _str_list(raw.get("contradictions"))
        # 正文（三槽合流; 旧档兼容: 依次回落到 narration/pattern/content）
        node.text = (_str(raw.get("text")) or _str(raw.get("narration"))
                     or _str(raw.get("pattern")) or _str(raw.get("content")))
        node.verbatim = _str(raw.get("verbatim"))
        node.verbatim_seq = _str_list(raw.get("verbatim_seq"))
        node.emo_shape = _str_list(raw.get("emo_shape"))
        node.place = _str_list(raw.get("place"))
        node.place_raw = _str_list(raw.get("place_raw"))
        node.title = _str(raw.get("title"))
        node.subject = _str(raw.get("subject"))
        node.examples = _str_list(raw.get("examples"))
        node.growth = _str(raw.get("growth"))
        node.aff_at_encoding = _opt_clamp(raw.get("aff_at_encoding"), -1.0, 1.0)
        node.emo_int = _opt_clamp(raw.get("emo_int"), 0.0, 1.0)
        node.emo_span = _opt_clamp(raw.get("emo_span"), 0.0, 1.0)
        # 已退役的键在此直接忽略（旧档宽容, 不抛）: count/segment_id/emo_valence/history/story_time
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
    """构造 + 归一（引擎写入前用）。调用方负责 validate()（本函数不抛）。"""
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


def _clamp_sig(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, f))


def _opt_clamp(v: Any, lo: float, hi: float) -> float | None:
    """可选 [lo, hi] 标量 —— **缺/坏 → None, 不折成 0.0**。

    与 `_clamp_sig` 的差别: 后者的默认 0.5 是真实档位; 而这里 `None`（未采集）与
    `0.0`（中性/无波澜）是**两个不同的事实**——合并会让旧档冒充"当时关系中性"。
    """
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:                                  # NaN
        return None
    return max(lo, min(hi, f))
