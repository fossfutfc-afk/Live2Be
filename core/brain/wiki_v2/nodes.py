"""图式 wiki 节点数据结构（AGENT_BRAIN.md §1）。

3 种节点（kind, 2026-09-02 fact 退役——出厂与运行时同构, 记忆 = 经历 + 认知）:
    episode    一次性经历（narration 第一人称浓缩 + verbatim 原话; 质感优先不升华）
    experience 重复模式（pattern + count 聚合; subject=player = 玩家口癖, R5 强调点）
    belief     抽象认知（inferred_belief, links 必须 ≥1 支撑; history 记录改写溯源）

通用字段: id / kind / significance / epistemic / observer / tags / segment_id /
          event_seq / ts / links / contradictions / aff_at_encoding /
          emo_int / emo_span / emo_valence
专属字段: episode.title(可选短标题) / belief.subject / belief.growth /
          belief.history[{episode_id, content, ts}]
observer 语义（2026-09-02 收敛）: 单视角世界线里 observed_fact 的观察者恒为
角色本人——引擎填 char_id, 不交给 LLM; reported_fact 的 observer = 转述者
（LLM 判断, 渲染为"听 X 说的"）。

⚠️ **`source` / `is_seed()` / `notes` 2026-09-21 整族删除**（"出厂基座"机制退役）:
出厂记忆自 2026-09-05 起**不进 wiki**（`render_background_experience` 直注 yml 原文），
唯一的生产者 `archive/factory_memory/seed_engine.py` 早已归档 ⇒ `source` 在活路径上
恒为 `"digest"` 这个常量，而它带出的 `is_seed()` 不可变守卫与 `notes` 追加通道
（全仓唯一读者）都是给一个不存在的生产者写的。真机 0 个 seed 节点。

关键规则（引擎侧强制, 此处提供 validate/normalize 支撑）:
    - epistemic: observed_fact | reported_fact | inferred_belief
      （canon_fact 随 fact 退役, 2026-09-02;
      **speculation 2026-09-21 删**——零生产者零消费者零真机数据, 见字段区）
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
#: 认知类型（DESIGN_BRAIN.md §7; canon_fact 随 fact 退役;
#: **speculation 2026-09-21 删**——零生产者/零消费者/零真机数据, 是 4 值枚举里
#: 唯一没人用的。belief 的 inferred_belief 与 episode/experience 的 observed/reported
#: 都由 validate 护栏强制, 所以 `speculation` 从来没被写进来过。）
EPISTEMICS = ("observed_fact", "reported_fact", "inferred_belief")
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
    #: ⏸ `source: str = "digest"` —— **已删（2026-09-21）**：活路径上它是常量。
    #: 唯一写入点曾有两个:`make_node` 的默认值（"digest"）与修订包的 `node.source =
    #: "digest"`;而"出厂基座"那一支（`source="experience"`）的生产者
    #: `archive/factory_memory/seed_engine.py` 已归档, 真机 0 个 seed 节点。
    #: 它带出的整族一起删: `is_seed()` · `render` 的 seed 桶与"canon 只读"标记 ·
    #: `store.update`/`revise` 的不可变守卫 · `notes`（唯一读者就是那条守卫）。
    #: 旧档里若还有这个键 → `from_dict` 宽松忽略。
    links: list[str] = field(default_factory=list)
    #: ⏸ **休眠字段 + 休眠路径（2026-09-21 用户裁决"接受整块休眠"）**。
    #:
    #: 三方核对（审计结论）:
    #: | 三方 | |
    #: |---|---|
    #: | 生产者 | ❌ **活路径上没有**：`DECISIONS = touch\|update\|add`（`contract/digest_registry.py`），写它的 `contradict`/`resolve`/`merge`/create-with-contradictions 全在 `apply_revision_package` 里，而那个函数**零生产调用者**（只有门面再导出与测试）；`phase=deep` 至今未注册 |
    #: | 消费者 | ✅ 有（`render.py` 组织视图的 `c:` 行 · `recall.py` 一跳扩展 · `store.py` 双向一致性 audit） |
    #: | 真机数据 | ❌ 零条（`wiki.jsonl` 全库无此键） |
    #:
    #: ## 为什么**不删**（别的死字段都删了, 它留）
    #:
    #: 它跟那些字段不是一类：`source_key`/`observation` 是**真死**（有活路径却不读 / 是常量 /
    #: 是派生），而 `contradictions` 是**整条路径休眠**——字段与执行器同生共死。删字段就得
    #: 同时改 `revise.py:282/430`（会给不存在的字段赋值 → AttributeError）、删 store 的三个
    #: 原语与 audit 规则、删 render/recall 的读取点，而那条路径**正是 `DESIGN_RESEND`
    #: （重发/更正）规划的执行器**（`merge` 将来要用于"水位之下更正"）⇒ 删它 = 替尚未立项的
    #: 深度整理**提前做一半设计**，将来还要再改一次。
    #:
    #: ⇒ 本期**整块休眠**：字段与路径都留，只在需要时一并重做。它体积 0 B、不进 LLM 上下文
    #: （`emo_shape`/`place` 那条纪律），代价只是 4 处 kind 判断。
    #: ⚠️ **重新立项深整理时走"带类型的边"**（矛盾是二元关系, 天然是边, 节点数组只是邻接表
    #: 实现）——见 `stores`/`DESIGN_WIKI_V3` 的 entity 中心模型; 不要回到"belief 上挂数组"。
    contradictions: list[str] = field(default_factory=list)
    #: ⏸ `notes: list[str]` —— **已删（2026-09-21）**：它唯一的存在理由是"出厂基座
    #: 只允许追加注记"（§5 规则 2），**全仓唯一的读者就是 `store.update` 里那条
    #: `is_seed()` 守卫**——渲染不输出、召回不读、真机零数据。出厂基座机制随
    #: `source` 一起退役 ⇒ 它没有任何读者了。
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
    #: **地点键序列**（M3, 2026-09-19）——`["classroom", "school_rooftop"]`。
    #: 由 `digest` 按 `event_seq`（板指针）从真源**物化**: 那几板的
    #: `payload.place`（板首 `switch` 解出的键）+ `payload.paragraphs[*].place`
    #: （句级锚点），**相邻去重保序** —— 于是它同时是"她这段去过哪些地方"的变化
    #: 序列（重复次数也留着: 同一个地点去了两次 = 两个元素）。
    #:
    #: ## 带的是**键**，不是 writer 的本名
    #:
    #: 用户 2026-09-19 问 *"带的是 key 还是 writer 的本名?"* —— 这里带**键**
    #: （C 链路的"同图"判据比的是相等，本名三个字符串同一张图，做不了等值分组）。
    #: writer 本名留在事件流里（`payload.place_hint` + 锚点句原文），
    #: `event_seq` 指得到。
    #:
    #: ⚠️ **但键不等于地名**（见上一条 `place` 的更正）——若要判"**同地**"
    #: 而不是"同图"，需要原文走语义（该字段尚未落，待裁决，见 TODO）。
    #:
    #: 🚫 **绝不进 LLM 上下文**（用户 2026-09-15 裁决同 `emo_shape`）——召回侧信号。
    place: list[str] = field(default_factory=list)
    #: ⚠️ **`place` 是「素材轴」，不是「地名」**（2026-09-19 用户指出后更正）。
    #:
    #: 用户: *"key 名不一定能代表实际含义？杂草屋和破房子两个地方可以对应同一个
    #: key；也就是真实地名和 key 大概率并不是一个双射。"* —— **实测证实，两个方向
    #: 都在表里活着**:
    #:
    #: | 方向 | 实例 | 后果 |
    #: |---|---|---|
    #: | **一键多义**（假阳性） | `ruinschoolcorridor` 的 note 自己写着 *"也可以用做老屋子或者某种杂草秘密基地"* —— 一个键**声明**服务多个叙事地点 | 真·走廊废墟与杂草屋两条记忆键相同 → 判成同地 |
    #: | **一地多键**（假阴性） | 别名 `天台` 指向 3 个键（`school_rooftop`/`rooftop`/`building_roof_top`） | 都在天台, 键不同 → 判成不同地 |
    #:
    #: 9 条 note 自称"通用/也可以用作"，其中 **8 条 region 未知** ⇒ 无从消歧;
    #: 而 `region` 本身只有 20/168 非空。
    #:
    #: ⇒ **键相等只声称「同一张图」，绝不声称「同一个地方」。**
    #: 判"同地"需要**叙事身份**，而那东西**推不出来**（一地多键的知识——两张不同的图
    #: 代表同一个叙事地点——不在资产结构里，只在语言侧）。两条路:
    #: ① 落**原文**走语义相似（同 `D` 链路拿 `narration` 做向量那一手）
    #: ② 作者打**地点实体表**（真实地名 → entity）——即 v3 的 entity 中心模型
    #: 未决，见 `TODO.md` 地点节。
    #:
    #: ⚠️ **原先这里有个 `region: str`，2026-09-19 撤掉了** —— 用户澄清:
    #: *"region 只是用于判定在哪个学院的，作用并不大，是为以后可能的地点体系
    #: 做铺垫的产物，现在其实基本没有太多作用，**也不必落库**。"*
    #: 它还是**派生视图**（`place_hint` 原文 → `regions.yml` 纯字符串归一）,
    #: 随时能从事件流重算 ⇒ 落库 = 冗余的第二真源。
    #: 真正的用处仍在**盒B【世界区域】块**（T16）与未来的地点体系。
    #: 旧档里若还有这个键 → `from_dict` 宽松忽略。
    #:
    #: **writer 原文序列**（叙事轴, 2026-09-19 用户指出后补落）。
    #:
    #: 用户: *"key 需要用于回放，而 writer 名则需要用于检索，**二者缺一不可**。
    #: 但是 writer 名不像键名可以直接 literal compare……会不会是用于检索的两个
    #: 维度？"* —— **正是**。两根轴回答的是不同问题, 不竞争:
    #:
    #: | 轴 | 字段 | 判据 | 声称 | 回答 |
    #: |---|---|---|---|---|
    #: | **素材** | `place` | 字面相等 | 同一张图 | **回放**画哪张图 |
    #: | **叙事** | `place_raw`（本字段） | **语义相似** | 同一个地方 | **检索**"是不是那儿" |
        #:
    #: 两根轴**信息上正交**（`same_image` 而无 `same_place` = 素材被两个叙事地点
    #: 共用; `same_place` 而无 `same_image` = 同一地点的两个镜头），所以
    #: **组合起来才是信号**——同 `emo_span × emo_int`、同"B/D 双链路都召回"那条判据。
    #:
    #: ⚠️ 为什么不能用键代替本字段: 键**不是地名的双射**（`ruinschoolcorridor`
    #: 的 note 自称"也可以用做杂草秘密基地" → 一键多义; 别名「天台」→ 3 个键 →
    #: 一地多键）。**语义轴只能由原文承担。**
    #:
    #: 来源: 板首 `switch` 的 `payload.place_hint`（writer 写的名词短语）。
    #: 句级锚点的原文要用 `paragraphs[i].text`, 在事件流里, 需要时按 `event_seq` 取。
    #: 🚫 **绝不进 LLM 上下文**（召回侧信号, 同 `emo_shape`）。
    place_raw: list[str] = field(default_factory=list)
    title: str = ""             # episode 可选短标题（渲染压缩/回放/决策表引用）
    pattern: str = ""
    subject: str = ""
    count: int = 0
    examples: list[str] = field(default_factory=list)
    content: str = ""
    growth: str = ""
    #: ⏸ `observation: list[str]` —— **已删（2026-09-21 用户裁决）**。
    #:
    #: 它 2026-09-17 被删过一次又恢复为"声明保留但不投产"的挂点（零生产者、零消费者、
    #: 不落库、零真机数据）。2026-09-21 复盘的裁决是**直接删**：
    #: *"observation(其实 narrator 只要写清楚，LLM 一定能懂，没必要)"*。
    #:
    #: ⇒ "对某对象的观察"这件事**不需要一个字段**：主 LLM 写清 narrator 就懂。真要做
    #: 多人模式的"谁观察到什么"，那是 v3 的实体模型（`about` 归堆 + `aspect` 分侧面 +
    #: `entity.overview`），到时候按实体落，**不要**回到 belief 上平移一个数组。
    #: 旧档里若还有这个键 → `from_dict` 宽松忽略。
    history: list[dict] = field(default_factory=list)   # belief 改写溯源（见 docstring）
    #: ⏸ `source_key: str` —— **已删（2026-09-21）**：零生产者零消费者零真机数据。
    #: 出厂链（`archive/factory_memory/seed_engine.py`）写它；`render.py` 里的那个
    #: `source_key` 是 yml 拍平的**局部变量名**（与字段无关）。出厂记忆自 2026-09-05
    #: 起不进 wiki（改走 `render_background_experience` 直注 yml 原文）⇒ 早已没人写它。
    #: 旧档里若还有这个键 → `from_dict` 宽松忽略。
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

    # ⏸ `is_seed()` —— **已删（2026-09-21）**: 判据是 `source == "experience"`, 随
    # `source` 一起退役（出厂基座机制: 出厂记忆自 2026-09-05 起不进 wiki）。
    # 它带走的两个守卫: `store.update` 的 SeedImmutable（只允许 notes 追加）与
    # `revise._apply_action` 的同款守卫——两者都对着一个不存在的生产者。
    # 若将来真要"作者写死的、运行时不可改"的记忆, 那条纪律应落在**配置层**
    # （`config/characters/*/experience.yml` 直注）, 不要回 wiki 里做不可变节点。

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
        for f in ("observer", "tags", "segment_id", "event_seq", "ts",
                  "links", "contradictions", "narration", "verbatim",
                  "verbatim_seq", "title", "emo_shape", "place",
                  "place_raw",
                  "pattern", "subject", "count", "examples", "content", "growth",
                  "history"):
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
        node.links = _str_list(raw.get("links"))
        node.contradictions = _str_list(raw.get("contradictions"))
        # kind 专属
        node.narration = _str(raw.get("narration"))
        node.verbatim = _str(raw.get("verbatim"))
        node.verbatim_seq = _str_list(raw.get("verbatim_seq"))
        node.emo_shape = _str_list(raw.get("emo_shape"))
        node.place = _str_list(raw.get("place"))
        node.place_raw = _str_list(raw.get("place_raw"))
        node.title = _str(raw.get("title"))
        node.pattern = _str(raw.get("pattern"))
        node.subject = _str(raw.get("subject"))
        node.count = _int(raw.get("count"))
        node.examples = _str_list(raw.get("examples"))
        node.content = _str(raw.get("content"))
        node.growth = _str(raw.get("growth"))
        node.history = _dict_list(raw.get("history"))
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
