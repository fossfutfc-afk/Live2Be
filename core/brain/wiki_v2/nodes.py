"""图式 wiki 节点数据结构（AGENT_BRAIN.md §1）。

3 种节点（kind, 2026-09-02 fact 退役——出厂与运行时同构, 记忆 = 经历 + 认知）:
    episode    一次性经历（narration 第一人称浓缩 + verbatim 原话; 质感优先不升华）;
               出厂基座（source=experience, immutable）+ 运行期 digest 双来源
    experience 重复模式（pattern + count 聚合; subject=player = 玩家口癖, R5 强调点）
    belief     抽象认知（inferred_belief, links 必须 ≥1 支撑; history 记录改写溯源）;
               出厂（beliefs.yml, 种子——不 immutable, 运行时 touch/update 演化）

通用字段: id / kind / significance / epistemic / observer / tags / segment_id /
          event_seq / ts / source / links / contradictions / aff_at_encoding /
          emo_int / emo_span / emo_valence
专属字段: episode.title(可选短标题) / belief.subject / belief.growth /
          belief.history[{episode_id, content, ts}]
observer 语义（2026-09-02 收敛）: 单视角世界线里 observed_fact 的观察者恒为
角色本人——引擎填 char_id, 不交给 LLM; reported_fact 的 observer = 转述者
（LLM 判断, 渲染为"听 X 说的"）。

关键规则（引擎侧强制, 此处提供 validate/normalize 支撑）:
    - epistemic: observed_fact | reported_fact | inferred_belief | speculation
      （canon_fact 随 fact 退役, 2026-09-02——出厂基座 = episode(source=experience)）
    - belief.epistemic == inferred_belief（护栏）
    - belief.links 非空（无支撑升华拒绝, §5 校验规则 4）
    - significance: decimal 0~1, 珍贵档 ≥ PRECIOUS_THRESHOLD(0.8)（保底通道）
    - 去重键 = (kind, event_seq): 同事件重复消化 → 去重; 不同事件同类 → accrue（不删）
    - player experience（subject=player）永不被内容去重/合并掉（§4.4）

id 格式（决策 #7）: 前缀 + 4 位零填充, 无 # 无下划线 —— e0002 / m0003 / m0003。
序列化: jsonl 一行一条（to_json_line / from_json_line）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: 节点类型（fact 已退役, 2026-09-02——出厂与 digest 同构: 记忆 = 经历 + 认知）
KINDS = ("episode", "experience", "belief")
#: 认知类型（DESIGN_BRAIN.md §7; canon_fact 随 fact 退役）
EPISTEMICS = ("observed_fact", "reported_fact", "inferred_belief", "speculation")
#: 珍贵档阈值（保底通道 / 对应 neuron 草稿的 memo 档）
PRECIOUS_THRESHOLD = 0.8
#: player experience 的 subject 固定值（玩家口癖/习惯, R5）
PLAYER_SUBJECT = "player"

#: 各 kind 的必填字段（validate 用）
_REQUIRED: dict[str, tuple[str, ...]] = {
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
        belief:     content(必填) / subject(认知对象, 可空) / growth
                    / history[改写溯源]（2026-09-02: {episode_id, content, ts} 数组）
                    （`observation` 已删 —— 见其在字段区的删除说明）
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
    #: `verbatim` 的**索引通道**（T14, 2026-09-15）——`["28.3", "20.p"]`。
    #: 语义: 这条 episode 的"关键几句"在**时间线上的地址**（词汇表见
    #: `contract/timeline_index.py`）。地址**永久有效**——`paragraphs` 落在
    #: append-only 的 `events.jsonl` 里, 永不改删, 所以索引能被无限次重新解析。
    #: `[]` = 未采集 / LLM 只给了文本通道。
    #: ⚠️ **`verbatim`（文本）才是消费字段**——`render.py`/`recall.py` 只拿到节点、
    #: 拿不到事件流, 解析不了索引。本字段服务的是**可追溯性 / 板归属 / 重解析**。
    verbatim_seq: list[str] = field(default_factory=list)
    #: **板级情绪键序列**（T15, 2026-09-15）——`["tease", "smile", "smile_2"]`。
    #: 由 `digest` 按 `event_seq`（板指针）从真源**物化**: 那几块的
    #: `payload.paragraphs[*].emotion` 按 seq 序拼接。B 链路（情绪序列 RAG）的唯一输入。
    #:
    #: 为什么物化而不是召回时现取: `Channel.gather(store, ctx)` **只拿得到节点,
    #: 拿不到事件流**——链路无法去翻板。而 §3.3/§3.9 本来就定了这一手
    #: （"板级 affect 物化缓存（一次算，索引表里存）…可从真源重建"）。
    #: 有 `event_seq` 就能重算, 所以它不是第二真源。
    #:
    #: 🚫 **绝不进 LLM 上下文**（用户 2026-09-15 裁决）——它是**召回侧信号**,
    #: 与 `place` 同类: 参与排序, 不参与写作。`render_*` 一律不输出它。
    emo_shape: list[str] = field(default_factory=list)
    title: str = ""             # episode 可选短标题（渲染压缩/回放/决策表引用）
    pattern: str = ""
    subject: str = ""
    count: int = 0
    examples: list[str] = field(default_factory=list)
    content: str = ""
    growth: str = ""
    #: ⚠️ **`observation: list[str]` 已于 2026-09-17 删除** —— 与 `time_span` 同一
    #: 形状的**孤儿字段**, 用同一把尺子办的（"有写入无消费"）:
    #:
    #: 1. **无生产者**: Round B 契约（`contract/digest_registry`）里**根本没有这个
    #:    字段**, 所以 LLM 输出不了它; `digest` / `revise` 也没有任何写入点
    #:    ⇒ 它**永远不可能被填上**（旧协议残留 —— `AGENT_BRAIN.md` 的 belief 范例
    #:    里还有一行, 那是 v1 的写法）
    #: 2. **无消费者**: 全库没有任何地方读它
    #: 3. **真机零节点**: `data/` 的 wiki.jsonl 里 grep 一条都没有
    #:
    #: 它当初的说明是"对该对象的观察（可承载玩家口癖等 R5 素材）"—— 而那件事现在
    #: **有专门的字段**: `experience` 节点 + `subject="player"` + `pattern`
    #: （契约里明写"玩家画像专用"）。所以不是"功能丢了", 是**路线改了、旧字段忘了删**。
    #:
    #: **为什么不留成"将来可能有用"**: 一个 LLM 永远不会输出的字段, 留着只会让读
    #: 节点的人以为"这里能装观察"。要装新东西时再加字段, 比留一个假接口便宜。
    #: （旧档里若还有这个键 → `from_dict` 宽松解析, **多余的键自动忽略**, 不抛。）
    history: list[dict] = field(default_factory=list)   # belief 改写溯源（见 docstring）
    source_key: str = ""
    #: 编码时好感标量 ∈ [−1, 1]（`Affection.to_scalar()`, §3.3.3）——**快照**:
    #: 写入时定、之后**永不改**（故与"节点 append-only"不冲突）。
    #: `None` = 旧档/未采集; `0.0` = 中性。两者**必须能区分**——否则旧档会被
    #: 误读成"当时关系中性", 同频召回会捞出一堆假匹配。
    #: 用途: `mood_congruence = 1 − |aff_now − aff_at_encoding| / 2`（值域宽 2）。
    #: 真源仍是 `affection` 事件流（`load_affection_from_events` 可按 seq 回放），
    #: 本字段只是省掉每次召回重放。
    aff_at_encoding: float | None = None
    #: 峰值情绪强度 ∈ [0, 1]（Round A 出值, §3.3.3 矩阵第二行）——**峰值**不是均值。
    #: 判据由 `【本段情绪标尺】`（作者注释, §3.3.2）提供。
    #: `None` = 未采集（旧档 / LLM 没给）; **`0.0` 也是合法值**（确实毫无波澜,
    #: 如纯事务性寒暄）。两者不可合并——故用 `None` 哨兵而非 `0` 当缺省。
    emo_int: float | None = None
    #: 情绪**摆幅** ∈ [0, 1]（Round A 出值, §3.3.3 矩阵第二格）——**非负**。
    #: "从最低摆到最高跨了多远"。与 `emo_int` 的区别:
    #:   span 高 int 高 = `outburst→smile`（先炸后真心笑）;
    #:   span 高 int 低 = 缓慢的起伏; int 高 span 低 = 一直很猛但没转折。
    #: ★ **不是**板级极差的聚合——板不是必需的粒度（2026-09-13 修正）:
    #:   Round A 看得到每条记录的 `(情绪键)`, 而它能读注释语义
    #:   （作者写 `sigh`「一看就知道是装可怜」——**字面极差读不出"装"**）。
    #:   故与 `emo_int`/`emo_valence`/`significance` 同为 episode 级 LLM 标量,
    #:   **不需要板链**（Q34 因此不阻塞任何字段）。
    emo_span: float | None = None
    #: 整体情绪色彩 ∈ [−1, 1]（带符号, Round A 出值）——**不进矩阵**。
    #: 矩阵第二格是 `emo_span`（无符号幅度）; 极性在这里, 供**情感召回的同频匹配**用
    #: （"现在难过" ↔ "这条记忆是难过的"）。
    #: 分级: 明显正面 → 0.5~1.0; 中性 → 0.0; 明显负面 → −0.5~−1.0。
    emo_valence: float | None = None
    # ── 剧情时间点（`story_time`）：**已整族退役**（2026-09-17, `ESSAY_TIME_MODEL §10`）──
    # 删掉的是 `story_time: dict | None` 字段、`_parse_story_time()` 与 `to_dict` 里的
    # 特例分支。它存的是**剧情日历**的快照（`{year,month,week,phase,sim_day}`），
    # 而唯一日期轴现在是**现实日期**（`ts`，由 `age.age_days` 算年龄）。
    # ⚠️ 旧档里仍可能有这个键 —— `from_dict` 宽松解析，**多余的键自动忽略**（不抛）。

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
        """出厂基座（immutable——update 只允许 notes 追加, 2026-09-02 定稿）:
        experience.yml 出厂 episode（source=experience, 预设记忆 = 角色记得的经历）。
        knowledge 不再出厂化（世界观知识 = config 档案职责——system prompt 注入 +
        interperson 读取, wiki 只存记忆）; beliefs.yml 出厂 belief **不 immutable**
        （认知种子, 运行时 digest 的 touch/update 挂新经历——认知基线演化）。
        """
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
                  "links", "contradictions", "notes", "narration", "verbatim",
                  "verbatim_seq", "title", "emo_shape",
                  "pattern", "subject", "count", "examples", "content", "growth",
                  "history", "source_key"):
            v = getattr(self, f)
            if v in (None, "", [], 0):
                continue
            d[f] = v
        # aff_at_encoding / emo_int / emo_span / emo_valence **不进上面那圈
        # "空值省略"** —— 它们用 None 当"未采集"哨兵, 而 0.0 是合法值
        # （中性好感 / 无波澜 / 中性色彩）。
        # 旧口径的 `v in (..., 0)` 会把合法的 0.0 一起省掉。
        for f in ("aff_at_encoding", "emo_int", "emo_valence", "emo_span"):
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
        node.verbatim_seq = _str_list(raw.get("verbatim_seq"))
        node.emo_shape = _str_list(raw.get("emo_shape"))
        node.title = _str(raw.get("title"))
        node.pattern = _str(raw.get("pattern"))
        node.subject = _str(raw.get("subject"))
        node.count = _int(raw.get("count"))
        node.examples = _str_list(raw.get("examples"))
        node.content = _str(raw.get("content"))
        node.growth = _str(raw.get("growth"))
        node.history = _dict_list(raw.get("history"))
        node.source_key = _str(raw.get("source_key"))
        node.aff_at_encoding = _opt_clamp(raw.get("aff_at_encoding"), -1.0, 1.0)
        node.emo_int = _opt_clamp(raw.get("emo_int"), 0.0, 1.0)
        node.emo_span = _opt_clamp(raw.get("emo_span"), 0.0, 1.0)
        node.emo_valence = _opt_clamp(raw.get("emo_valence"), -1.0, 1.0)
        # `story_time` 已退役（2026-09-17）——旧档里若还有这个键, **此处直接忽略** ✓
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


def _opt_clamp(v: Any, lo: float, hi: float) -> float | None:
    """可选 [lo, hi] 标量（`aff_at_encoding` / `emo_int` / `emo_span` / `emo_valence`）
    ——**缺/坏 → None, 不折成 0.0**。

    与 `_clamp_sig` 的关键差别: 后者的默认 0.5 是一个真实档位;
    而这里 `None`（未采集）与 `0.0`（中性/无波澜）是**两个不同的事实**,
    合并会让旧档在召回里冒充"当时关系中性 / 毫无波澜"。
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
