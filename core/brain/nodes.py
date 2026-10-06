"""图式 wiki 节点（AGENT_BRAIN.md §1）。

五种 kind（2026-09-02 fact 退役——记忆 = 经历 + 认知; 2026-10-06 经验/profile 定名）:
    episode    一次性经历（text 第一人称浓缩 + verbatim 原话; 质感优先不升华）
    experience 一类事（"经验"）; title = 类名, text = 这一类事的沉淀（允许空）; 成员走 member_of
    profile    玩家画像（"关于老师的事"）; subject="player"（2026-10-06 前叫 experience）
    belief     抽象认知（text 写结论; links ≥1 支撑; 可选 growth 成长方向）

不变量（validate/normalize 强制）:
    - `observer` 空 = 亲历; 非空 = 转述者（**它一个人说两件事**: 来源是谁 +
      这条是不是"听说的"）—— ⏸ `epistemic` 字段 2026-09-29 退役（见 `EPISTEMICS` 处）
    - belief **不许带 `observer`**（"认知不伪装成事实"在新词汇下的同一条护栏）
    - belief 必须有 `supports` 入边 —— ⚠️ 2026-09-21（G3）**搬到 `store.audit()`**:
      支撑关系住在边表里, 字段级校验看不见它
    - profile.examples ≤ 3
    - significance ∈ 0~1, 珍贵档 ≥ PRECIOUS_THRESHOLD(0.8); 越界 clamp
    - 去重键 = (kind, event_seq 有交集, 主文本相同) —— `revise._find_duplicate`

⚠️ 2026-09-21 大化简（判据 = 生产者/消费者/真机数据三方核对）——**删过的别再捡回来**:
    source_key · observation · speculation · source（连同 is_seed/notes/seed 桶/不可变守卫）·
    count（→派生 len(links)，后随边表再搬到 `render._count_of`）· segment_id · emo_valence ·
    history（→evolution 的 before/after）· main_text（属性）; 三槽 narration/pattern/content → **text**;
    **`links` / `contradictions`（G4 删——边整体搬到 `soul/edges.jsonl`，见 `graph.py`）**。
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
#: ⭐ **`experience` 2026-10-06 定名**（原 `group` · N1b · `DESIGN_MMT_NEW_ACTION §4.5`）: **经验**是 L2 归纳出来的
#: "一类事"，成员靠 `member_of` 边指过来（**不在节点上存列表** —— 成员会生长、各有自己的 `ts`）。
#: ⚠️ **它只装"名字 + 成员"，不装"关键信息"** —— "这一类说明了什么"是 **belief** 的活;
#: 两处都写就是双真源，L2 改了 belief 那份不会跟着改（必漂）。
#: ⭐ **`profile`（2026-10-06 从 `experience` 改名）** = **玩家画像专用**（"关于老师的事",
#: `subject` 恒 `player`）—— 名字让给了"经验"（见 `docs/DESIGN_MEMORY_MODES.md` §3）。
#: ⏸ **`promise` 2026-09-25 加入、2026-09-29 退役**（用户裁决: 承诺太轻, 不足以长期记录）——
#: 它**退出了图**（连同 `from`/`to`/`formed_by` 三条专属边），只留在 note 里当工作记忆
#: （`notes.SLOT_PINNED` = 她此刻还背着的事）; "这条经历涉及约定"由 `tags` 承担（只做筛选）。
KINDS = ("episode", "experience", "belief", "entity", "profile")
#: ⏸ `PROMISE_OUTCOMES`（`kept`/`broken`/`superseded`）**2026-09-29 退役** —— 它是 promise
#: 节点的 `outcome` 字段的枚举。结局本身没消失: 它留在 note 条目的 `state` 里
#: （真源 = `notes` 那一份词表）。
#: ⏸ `EPISTEMICS`（三值词表）**2026-09-29 退役** —— `epistemic` 字段整个删掉,
#: 只留 `observer`。两条判据（`REDUNDANCY.md` #3）:
#: ① **与 `observer` 互为函数**（非空 ⟺ reported ⇒ 同一件事两个字段说）;
#: ② **跨 kind 两个意思**（episode 上它是"来源", belief 上它是"别伪装成事实"——
#:    而 belief 那一半其实是 `kind` 已经说过的话）。
#: 旧档 `wiki.jsonl` 里的 `epistemic` 键由 `from_dict` **宽松忽略**（无迁移脚本）;
#: 信息不丢: "听说的"那一条本来就带 `observer`（真机 reported 1/20, 且带转述者）。
#: 珍贵档阈值（保底通道 / 对应 neuron 草稿的 memo 档）
PRECIOUS_THRESHOLD = 0.8
#: player profile 的 subject 固定值（玩家口癖/习惯, R5）
PLAYER_SUBJECT = "player"

#: 各 kind 的必填字段（validate 用; 正文统一叫 `text`）
_REQUIRED: dict[str, tuple[str, ...]] = {
    "episode": ("text",),
    "profile": ("text", "subject"),
    "belief": ("text",),
    # ⚠️ entity **只要求 `name`** —— `text`（立场/成长基线）允许空着出生:
    # `ensure_entities` 建 self/sensei 时还没有任何记忆, 立场是第 3 轮从记忆里长出来的。
    "entity": ("name",),
    # ⭐ experience（经验）: **只要 `title`（类名）** —— `text` 允许空（同 entity）:
    # 群上不放"关键信息"，判断归 belief（见 `KINDS` 的注释）。
    # ⚠️ `title` 的唯一性今天**还没强制**（契约未查）；`look` / `noticed` 命中歧义时
    # 一律"不猜"（落到检索 / 丢弃），所以缺唯一性只影响命中率，不影响正确性。
    "experience": ("title",),
}


def format_id(prefix: str, seq: int) -> str:
    """id 格式: 前缀 + 4 位零填充（m0003 / c0002 / e0002）。"""
    return f"{prefix}{seq:04d}"


@dataclass
class BrainNode:
    """一条图式 wiki 节点（宽松 dataclass: 字段可缺省, 校验走 validate()）。

    字段分组:
        共用    id / kind / significance / text / observer / tags /
                event_seq / ts
        episode title / verbatim / verbatim_seq / emo_shape / place / place_raw /
                aff_at_encoding / emo_int / emo_span
        认知     subject / examples / growth        （profile / belief）
        entity  name / aliases / state             （`text` = 立场/成长基线, 属共用槽）
        experience title                              （类名; `text` 允许空, 同 entity）
    """

    # ── 共用（三种 kind 都有）──
    id: str = ""
    kind: str = "episode"
    significance: float = 0.5
    #: 信息来源: **空 = 亲历; 非空 = 转述者**（LLM 只在"听别人说的"时填, 渲染"听X说的"）。
    #: ⏸ `epistemic` 字段 2026-09-29 退役（判据: 与 observer 互为函数 + 跨 kind 两个意思）
    #: ⇒ **"这条是不是听说的"就由这个字段判**（读侧只此一处判据, 不再有第二个真源）。
    observer: str = ""
    tags: list[str] = field(default_factory=list)
    event_seq: list[int] = field(default_factory=list)
    ts: str = ""
    # ⏸ `links` / `contradictions` 两个字段 2026-09-21（G4）**删** —— 边已整体搬到
    # `soul/edges.jsonl`（类型化 + 有向 + 三索引）。旧档盘上还留着这两个键,
    # 由 `graph.infer_edges(rows)` 在**文件格式层**读一次（自举）, 与节点对象无关。
    #: **这条记忆的正文**（三种 kind 共用一槽; 原 `narration`/`pattern`/`content` 2026-09-21 合流）。
    #: 写作口径仍按 kind 分（episode=第一人称浓缩 / profile=画像 / belief=结论）——那是
    #: rules/schema 的语义, 不再由字段名承担。旧档的旧名由 `from_dict` 兼容读入。
    #: ⭐ **entity 也用这一槽**：它的 `text` = **立场 / 成长基线**（原 `overview` 的语义,
    #: 2026-09-21 用户裁决"overview 就是 text"）—— 所以 entity 不新增字段、`text` 也不必
    #: 从"共用"里降级出去。
    text: str = ""
    # ── episode 专属 ──
    verbatim: str = ""
    #: `verbatim` 的**唯一来源**（地址如 `"28.3"`/`"20.p"`, 词表 = `contract/timeline_index.py`）。
    #: 上游: 引擎据此回填文本; 地址永久有效（`events.jsonl` append-only）⇒ 可重解析。
    #: ⚠️ 消费字段是 `verbatim`（文本）—— 解析不出就**留空**（绝不编; 文本通道 2026-09-29 退役）。
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
    #: ⏸ `items`（物品台账, §3.1）**2026-09-29 删** —— 它写给"这条记忆里的实物痕迹",
    #: 但**零活读者**（唯一读它的那个取料模块已于 2026-10-05 删）, 而根子上的问题是
    #: **写在 episode 里分不清"是不是同一个东西"**（夏天送的杂草 ≠ 冬天送的杂草,
    #: 而兔子玩偶 = 黑色兔子）⇒ 那件事该由专门的**物品面**（`inventory` 旁路）承担,
    #: 不该由一条自由文本承担。⚠️ 旧档里那两处值（haruka `m0009`/`m0017`）已随清理删掉。
    #: 别把字段加回来 —— 要物品面就起旁路, 那要**身份**（有 id、有增删、有当前持有）。
    # ── 认知专属（profile / belief）──
    subject: str = ""
    examples: list[str] = field(default_factory=list)
    growth: str = ""
    # ── entity 专属（§3.0; `text` 与 `state` 是它的两个载荷）──
    #: 主名字（"老师"）——**消解的目标**: 别名都归到它这里; 新 entity 必填。
    name: str = ""
    #: 别名（"sensei" / "他" / "遥香"）—— 第 3 轮映射 hint 时的查表入口。
    #: ⚠️ **不造自动维护机制**（2026-09-21 裁决: 那是效率优化不是能力）——初始化写死几个,
    #: 第 3 轮在它已经判定"hint 就是这个人"时**顺手**写进去。
    aliases: list[str] = field(default_factory=list)
    #: **物理状况句清单**（世界侧: 身体 / 外观 / 随身）——"手上多了道划痕" "今天戴了眼镜"。
    #: 与 `text`（立场/成长基线, 心智侧）分工; 会变、**会自愈**（谁判它过期 = §9-4 未定）。
    #: ⚠️ **这是 entity 专属、且是 list**；promise 那个 `outcome` 字段 2026-09-29 已随
    #: promise 退图一起删（当年就是为了躲这里的 `_str_list()` 静默丢结局才另开字段）。
    state: list[str] = field(default_factory=list)
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
        for f in _REQUIRED[self.kind]:
            if not str(getattr(self, f, "") or "").strip():
                errors.append(f"{self.kind} 缺少必填字段: {f}")
        # 来源护栏（原 `epistemic == "inferred_belief"` 那条的**新词汇版**,
        # 2026-09-29）: 非空 `observer` 的语义是"这条是**听说的**" ⇒ belief 不许带它,
        # 否则一条认知会被渲染进「我听说的」那一段（认知不伪装成事实）。
        if self.kind == "belief" and self.observer.strip():
            errors.append("belief 不许带 observer（认知不伪装成事实——那是听说的标记）")
        # ⚠️ 原「belief 必须 links ≥1 条支撑」2026-09-21（G3）**搬走** —— 支撑关系现在
        # 住在边表（`edges.jsonl` 的 `supports` 入边）, 字段级校验看不见它。新家两处:
        # ① 写路径 `revise.apply_decisions` 建完节点立刻补 `supports` 边;
        # ② 全局兜底 `store.audit()`（"belief 无支撑"）。
        # ⏸ 原「episode/profile 的 epistemic 只能是 observed/reported」2026-09-29 删 ——
        # 那一格今天由 `observer` 承担（空/非空两态 ⇒ 不存在"第三种值"要拒）。
        # 数量边界
        if self.kind == "profile" and len(self.examples) > 3:
            errors.append("profile.examples 最多 3 条")
        # ⏸ 原「promise.outcome 枚举校验」2026-09-29 删 —— promise 退图 ⇒ 节点上没有结局字段;
        # 结局今天住在 note 条目的 `state`（那里的枚举校验仍在 `notes`）。
        # significance 边界（decimal 0~1）
        if not (0.0 <= self.significance <= 1.0):
            errors.append(f"significance 越界: {self.significance}（须 0~1）")
        return errors

    def normalize(self) -> "BrainNode":
        """引擎侧归一: significance clamp 0~1; examples 截断 3。"""
        self.significance = max(0.0, min(1.0, float(self.significance)))
        if self.kind == "profile":
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
    def is_player_profile(self) -> bool:
        """玩家画像节点（"关于老师的事"）—— ⭐ **就是 `kind == "profile"`**（2026-10-06 前叫 `experience`）。

        ⚠️ **2026-09-25 改**（DESIGN_GRAPH_V4 §5.1）: 原先还要求 `subject == "player"`，
        而 `subject` 是**自由文本** ⇒ 真机 haruka 那条（`subject="关于 我道歉的习惯"`，
        R2 早期写的"她的模式"）**四个桶全不收**：内容写在盘上、却从来不进她的上下文
        （它还挂着 3 条 `supports`）。⇒ **可见性不许挂在一个自由文本字段上**；
        `subject` 由写侧强制成 `PLAYER_SUBJECT`（`digest._create_a_nodes`），
        但它不再决定"看不看得见"。
        """
        return self.kind == "profile"

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
        }
        for f in ("observer", "tags", "event_seq", "ts",
                  "text", "verbatim",
                  "verbatim_seq", "title", "emo_shape", "place",
                  "place_raw",
                  "subject", "examples", "growth",
                  "name", "aliases", "state"):
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
        # ⏸ 旧档的 `epistemic` 键**读不进来也不报错**（2026-09-29 退役; 信息在 `observer` 里）
        node.observer = _str(raw.get("observer"))
        node.tags = _str_list(raw.get("tags"))
        node.event_seq = _int_list(raw.get("event_seq"))
        node.ts = _str(raw.get("ts"))
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
        node.name = _str(raw.get("name"))
        node.aliases = _str_list(raw.get("aliases"))
        node.state = _str_list(raw.get("state"))
        # ⏸ 旧档的 `outcome` 键（promise 节点）**读不进来也不报错**（2026-09-29 退图）
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
