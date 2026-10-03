"""pipeline.py — digest 管线（`core/digest/`；设计见 `core/brain/AGENT_BRAIN.md §3` / 板块 4a）。

⭐ **2026-09-29 搬家**: `core/brain/digest.py` → **`core/digest/pipeline.py`**（代码管理节点 B）。
理由: `core/brain/` 是数据层（纯 stdlib 零 LLM）, 而本文件要 contract / llm / session ⇒
分开之后"数据层不 import LLM"才是包边界。⚠️ 本文以下凡写 `digest.py` 的旧路径
一律指**本文件**。

**实际跑的步数（2026-09-29 现状, 不是"两轮"）**——一眼看全在 `core/digest/__init__.py`;
本文件的顺序是: R1 → akin 补边 → R4 → R2 → R3 → L2-a 分群（共 5 次 LLM 调用 + 1 次零成本补边）:
    R1「记录员」 `digest.round_a`: 只看新时间线 + 人设 + 视觉记忆 → episode / 玩家画像
    akin 补边    （0 LLM）         : 本段的 `noticed` 账 → `akin` 边
    R4「收口」   `digest.close`    : 开着的约定 + 本段经历 → note 操作（**不建节点**）
    R2「理解者」 `digest.round_b`  : 新经历 + 时间线 + 认知列表 → 决策表 decisions + `links`
    R3「归属」   `digest.attr`     : 候选表 + 命中集载荷 + 本轮新节点 → `about` 边 + entity 载荷
    L2-a 分群    `digest.group`    : 块 + 已有类 → 群节点 + `member_of`（**自带快照**）

（`decisions`: touch=印证 / update=深化改写 + evolution 留痕 / add=新建
 —— 由 `revise.apply_decisions` 执行 → 随整批原子提交。）

编排（digest_segment）::
    1. 增量: new_events = seq > store.digested_seq（无新增 → 0 次 LLM 调用）
    2. 公共输入: 时间线(**记录级带行索引**, T14) + 视觉记忆 + 人设锚点
    3. 依次跑上表那 5 轮（**顺序与跳过条件 = `rounds.ROUNDS`**; 每步吃哪几段料也在那）
       ⭐ **每轮有自己的时间预算**（表里那格）, 截止 = `min(整段硬顶, 本轮开始 + 预算)`
       —— 前几轮慢不再把后面几轮饿死; 撞了在 `errors` 里指明是哪一轮。
    4. affection_exp_delta 返回（事件幂等写由调用方——运行时集成层）
    5. 任一轮失败 → clone_state 快照回滚, 水位不推进（宁缺勿错, 可重算）
       ⚠️ 例外: **分群自带快照**（`own_snapshot`）, 失败只回滚它自己
       （那是加法, 块留到下段再来）
    6. 成功 → store.save()（原子整写）+ 推进 meta.digested_seq + save_meta

⚠️ **"轮次表"已立**（**2026-09-29 节点 C**）—— 每轮的步序 / LLM 身份 / 料 / 产出 /
跳过条件 / 是否自带快照全在 **`core/digest/rounds.py` 的 `ROUNDS`** 一张表里。
本文件是**执行体**: 调用点先 `cur.enter(key)` 拿 spec（越序当场炸）, 再用
`_system_for(spec)` / `_parse_for(spec, …)` / `_sections_for(spec, …)` 三件套 ——
prompt 名、契约相位、parse 函数、**料的段标题**都不在这里各写一份字面量。
⭐ **`_rollback` 的清空清单也由表推导**（`rounds.reset_result`）——
从前它是手抄的, 漏过 `notes_warnings`（见 `_rollback` 的 docstring）。

⚠️ **`evidence`（成长证据）2026-09-29 已删** —— 它**零产品消费者**（只有一条测试与一个
    归档脚本读过）, 契约却每段都要它 ≤5 条 + `quote` 逐字引用时间线 ⇒ 那是一笔白付的钱。
    删它的连带: R2 的料里那段"本段时间线"从此**没有存在的理由**（它当初就是为
    `evidence.quote` 逐字引用而喂的）—— 那段要不要一起去掉是**改行为**, 单独验。

⚠️ **全景轮（`run_panorama`）2026-09-29（N4a）已退役** —— note 的写者收成一个:
    `promise` 归 R4 收口、`on_mind` 归 **L1（Round A）**。取料逻辑留在 `panorama.py`
    （零产品调用者, 给 N6 的"切块"当原料）。退役理由: 它的两个槽一个被取消
    （`habits`）、一个换了写者 ⇒ **它没有输出了**。

⚠️ **`promise`（承诺）2026-09-29 退出图** —— 用户裁决: 这类东西"太轻, 不足以长期记录"
    （日常约定 ≈ 客套/安排）⇒ **不再有 promise 节点**, 也不再有 `from`/`to`/`formed_by`
    三条专属边。它留在 **note**（`notes.SLOT_PROMISE` = 她此刻还背着的事, 工作记忆）,
    "这条经历涉及约定"由 **`tags`** 承担（筛选用, 不承担路由）。⇒ R4 从"记账 + 固化"
    缩成**只记账**, §8 那条"R4 必须排在 R2/R3 之前"的理由随之消失（顺序照旧, 但不再是正确性要求）。

反馈回灌（2026-09-02 采纳 llm.client.feedback 语义）: 被拒轮把 LLM 自己的输出
追加为 assistant 位 + 引擎错误, 同一上下文重试 1 次——模型能看见自己错在哪
（旧实现重建 user 消息, 模型看不到被拒输出, 修正成功率低）。

失败: 静默降级（logger.warning + DigestResult(ok=False)——wiki 是派生视图,
events.jsonl 唯一真源, 可重算）。
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from contract.digest_registry import digest_registry
from core.brain import groups, marks
from core.brain.entities import candidate_table, hit_set, new_nodes_block, payload_block
from core.creep import KIND_DIGEST_SKIP, build as creep_build
from core.digest.llm_call import llm_chat
from core.digest.rounds import (
    SEGMENT_HARD_CAP_SECONDS,
    Cursor,
    RoundSpec,
    budget_of,
    reset_result,
)
from core.brain.nodes import PLAYER_SUBJECT, make_node
from core.brain.read.recall import (
    EmbedFn,
    recommend_candidates,
)
from core.brain.read.render import (
    render_cognition_line,
    render_cognition_list,
)
from core.brain.revise import (
    apply_attribution,
    apply_closures,
    apply_decisions,
)
from core.brain.address import unique_title
from core.brain.graph import REL_AKIN
from core.brain.notes import rewrite_op
from core.brain.store import WikiStoreV2
from core.session.events import TYPE_NOTICED, is_content_event
from core.session.maintenance import exclude_abandoned
from core.session.renderer import render_timeline
from llm.client import feedback
from llm.prompts import load_prompt
from llm.task_levels import extra_body as _tl_extra
from llm.task_levels import max_tokens as _tl_max_tokens

logger = logging.getLogger(__name__)

#: 反馈重试（parse/结构被拒 → 带 assistant 原文回灌重试 1 次）
MAX_FEEDBACK_RETRIES = 1
#: ⭐ **一段最多试几次**（2026-09-29 刀 2）—— 数到就**放弃**这一段（见 `_note_failure`）。
#: ⚠️ 它**不是"同一个进程里连试三次"**: digest 没有主动重试, 次数由**触发点**累加
#: （MMT 每 25 轮 / bond 闭环）⇒ 最坏要等 75 轮才放弃。不改成立刻重试的理由:
#: 同一段、同一模型、同一预算, 连撞三次是白花钱, 还占着 `_digest_lock`。
MAX_DIGEST_ATTEMPTS = 3
#: ⏸ `EVIDENCE_THRESHOLD = 0.7` **2026-09-29 删** —— `evidence` 字段退役（零消费者）。
#: B 轮认知渲染上限（本地 id 数量; 排序: 珍贵档先）
COGNITION_CAP = 12
#: 好感 delta clamp 边界（**带符号: 下界 2026-09-13 由 0 放开**）。
#: 语义 = "**单段**内的好感净变化"，不是总量——上界 100 防一段暴涨,
#: 下界 -100 对称防一段暴跌; 累计地板在 `Affection` 层（MIN_EXP=0）。
#: 放开下界的理由见 docs/DESIGN_WIKI_V3.md §3.3.3: 关系能变坏是玩法语义,
#: 且同频召回需要 `aff_at_encoding` 的符号。
_AFF_MIN, _AFF_MAX = -100, 100
@dataclass
class DigestResult:
    """一次 digest 的结果。

    ⚠️ 字段分两类（`core/digest/rounds.py` 是判据）: **某轮的产出**（失败时由
    `reset_result` 按表清空）与 **`COMMIT_ONLY`**（调用路径的记录 / 提交时才赋值 ——
    回滚不碰）。加字段必须归类, 否则 `tests/core/test_digest_rounds.py` 直接红。
    """

    ok: bool
    errors: list[str] = field(default_factory=list)
    #: Round A 建的 episode id —— ⚠️ **提交时才赋值**（任一轮失败 ⇒ 这个字段是空的）
    created: list[str] = field(default_factory=list)
    #: 本段的好感净变化（R2 给的）—— 同上, **提交时才赋值**
    affection_delta: int = 0
    #: 真正发出去的 LLM 调用次数（含被拒重试）—— 调用路径记账, 回滚不抹
    llm_calls: int = 0
    #: ⏸ ~~归属线索~~（`hints` = R1 的 `about_hint` → R3 的映射）**2026-09-29 删** ——
    #: `about_hint` 退役（与 R3 判两次）, 这条中间通道随之消失; R3 改为自己从正文里认称呼。
    #: ⭐ **R4 收口的 note 操作**（`add` / `close`）—— ⚠️ **调用方在整批 `ok` 之后才 append**
    #: （§8: 失败 = 整批回滚 ⇒ 那条约定原样开着; 事件 append 不可撤销, 提前写就回不去了）。
    notes_ops: list[dict] = field(default_factory=list)
    #: R4 的世界校验记账（剔掉的引用 / 丢掉的 close 行…）—— 不阻断, 但要看得见
    notes_warnings: list[str] = field(default_factory=list)
    #: ⏸ ~~R4 物化的 promise 节点 id~~ **2026-09-29 删** —— 承诺退图, R4 不再建节点
    #: （见 `revise.ClosureResult` 与 `nodes.KINDS`）。
    #: R3 新建的 entity id（`new_entity` 的产物; 归属边在那边一起写）
    created_entities: list[str] = field(default_factory=list)
    #: ⭐ **L2-a 分群（N7）**: 本段**新建的群节点** id
    created_groups: list[str] = field(default_factory=list)
    #: 分群这一步**挂上类**的 episode 数（产出的规模; 0 = 这一段的块都还没成类）
    grouped_episodes: int = 0
    #: ⭐ **N7b 并群**: 本段并掉的类 `[(输家 id, 赢家 id), …]`
    merged_groups: list[tuple[str, str]] = field(default_factory=list)
    #: 分群这一步的记账（同名并群 / 类名找不到 / 这一步整体失败…）—— **不阻断**
    group_warnings: list[str] = field(default_factory=list)
    #: ⭐ **要落进 creep 账的行**（`kind=digest_skip`）—— 见 `_note_failure`。
    #: ⚠️ **调用方不管 `ok` 都要写它**（失败也要留账: 账不是剧情, 不随事务回滚）;
    #: 写入路径 = `SessionStore.append_raw_row`（本函数拿不到事件流, 所以只"造行"）。
    creep_rows: list[dict] = field(default_factory=list)


def digest_segment(
    store: WikiStoreV2,
    llm,
    events: list,
    *,
    character_prompt: str = "",
    visuals: list[str] | None = None,
    model: str | None = None,
    embed_fn: EmbedFn | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    deadline_seconds: float = SEGMENT_HARD_CAP_SECONDS,
    llm_timeout: float | None = None,
    extra_body: dict | None = None,
    aff_at_encoding: float | None = None,
    emotion_lexicon: dict | None = None,
) -> DigestResult:
    """增量 digest: 新事件 → 依次跑 `rounds.ROUNDS` 那几步 → 原子落盘 → 推进水位。

    ⚠️ 从前这段写着"两轮"—— 那是 Round A/B 时代的名字。今天每段是
    **5 次 LLM 调用 + 1 次零成本补边**（步序见 `core/digest/rounds.py`）。

    Args:
        store: 目标世界线的图式 wiki（meta.digested_seq 是水位）
        llm: 兼容 llm.chat(messages, model=, temperature=, max_tokens=,
             response_format=, extra_body=) 的客户端
        events: 该世界线完整事件流（Event 列表; 增量由水位切）
        character_prompt: 人设锚点文本（性格+知识两层; 空 → 不注入）
        visuals: 视觉记忆 prompt 列表; None → 从事件流 l2d 事件自动收集
        model: 模型覆盖（None → 客户端默认）
        max_tokens: 输出上限（None → 真源 llm/task_levels.py 形态 "digest" = 8192,
            2026-09-02 集中管理）
        extra_body: 请求附加字段。None → 按真源形态 "digest" 注入（thinking=high——
            深度认知, 2026-09-02 拍板; 实验矩阵: low 5/5 合格但浅 / medium 1/3 死在
            规则校验 / high 2/2 认知深化与逐字校验最佳——不随 settings 全局漂移）;
            显式传（含 {}）→ 调用方覆盖
        deadline_seconds: ⭐ **整段硬顶**（秒）—— 五轮 + 各自的反馈重试加起来不许超过它。
                    ⚠️ 它**不再是每轮共享的那一份预算**（2026-09-29 刀 1）: 每轮另有
                    自己的预算（`rounds.ROUND_BUDGET_SECONDS` / 表里那格），本轮的
                    截止 = `min(整段硬顶, 本轮开始 + 本轮预算)`。撞上 → 判失败回滚,
                    水位不推进可重算。默认 = `rounds.SEGMENT_HARD_CAP_SECONDS`。
                    ⚠️ **它是"每次尝试前"的检查, 不掐断正在飞的那一次调用**
                    （`llm_call` 的既有语义; 单次请求仍受 `llm_timeout` 约束）——
                    所以"某轮用满预算"能保证的是**后面的轮不被它饿死**, 不是"这一段
                    总时长必然 ≤ 硬顶"。真机要收紧就得看 `task=digest.* ms=` 调数值。
        llm_timeout: per-call 超时覆盖（None = 客户端构造超时; 后台 digest
                   建议 ≥300s——high 档单次长考可超 60s 共享客户端默认）。
                   ⚠️ 它与每轮预算**不是一回事**: 这是单个 HTTP 请求的上限, 而每轮预算
                   是"**开下一次尝试之前**"的检查 ⇒ 真机上若 `task=digest.* ms=` 显示
                   单轮常常 120s+, 该调的是**表里的预算**, 不是这里。
        aff_at_encoding: 本段**开始之前**的好感标量 `Affection.to_scalar()` ∈ [−1,1]
                   （§3.3.3）——落进 episode 节点的**快照**, 写入后永不改。
                   None = 未采集 → 字段不落库（与 `0.0` 中性区分）。调用方算,
                   因为 brain 看不到事件流里的 affection 事件。
        emotion_lexicon: 角色情绪词表 `{键: {comment, eg, path}}`
                   （`core.media.load_emotion_lexicon(char_dir)`, §3.3.2）。
                   给了 → 只把**本段实际出现的键**的作者标尺注进 Round A,
                   LLM 才有依据判断"情绪摆幅多大 / 峰值多猛"。
                   None/空 → 不注入（Round A 照跑, 只是少一层依据）。
                   **为什么由调用方给**: 词表在 `assets/illustration/{char_id}/default/`,
                   brain 层不该知道资产布局——与 `aff_at_encoding` 同一分工。
    """
    if max_tokens is None:                       # 真源: task_levels 形态 digest
        max_tokens = _tl_max_tokens("digest")
    if extra_body is None:                       # 真源档位: digest = high（显式）
        extra_body = _tl_extra("digest")
    # 废弃段过滤（2026-09-07, maintenance）: 被压掉的中断段"未发生"——不进记忆
    events = exclude_abandoned(events)
    # 本窗口 = 水位之后**全部**事件（含 marker）——段类型要从 marker 派生, 见下。
    new_all = [e for e in events if e.seq > store.digested_seq]
    # 内容事件 = 非 marker 且非"账目"（affection / note）——判据收在
    # `events.is_content_event` 一处（note 落地前的 `type != "affection"` 已删）。
    new_events = [e for e in new_all if is_content_event(e)]
    if not new_events:
        return DigestResult(ok=True)                     # 无新增 → 0 次 LLM 调用
    # 段类型 + 章标题（2026-09-20）: **从 marker 派生, 不落库**。
    domain, chapters, _bond_seqs = _segment_domain(new_all)
    interact_max = max(e.seq for e in new_events)
    # ⭐ 刀 2 的两个坐标（失败时记数 / 放弃时推水位, 见 `_note_failure`）:
    #   `digest_from` = 这次尝试的**起点水位**（= 计数的键, 失败期间它不动）;
    #   `interact_max` = 这次窗口的内容上界（第一次失败时**冻结**成"放弃线的终点"）。
    digest_from = store.digested_seq
    result = DigestResult(ok=False)
    snapshot = store.clone_state()                       # 原子性: 失败 → 回滚

    timeline = render_timeline(new_events, indexed=True)
    # 本段**可寻址事件** —— `event_seq` / `verbatim` 索引的 ⊆ 校验基准（T14）。
    # 只收种子事件（marker/affection 不渲染进时间线, LLM 指不到它们）。
    seq_set = {e.seq for e in new_events}
    by_seq = {e.seq: e for e in new_events}
    if visuals is None:
        visuals = _collect_visual_prompts(new_events)
    # 本段出现的情绪键 → 只把这些键的作者标尺注进 Round A（§3.3.2）。
    # 为什么在这里算: `char_id` 只够定位词表,**哪个键该注**必须看本段实际标注
    # ——全词表对一个只出现 5 键的段是纯噪声, 还会诱使 LLM 拿没出现的键凑强度。
    emotion_scale = ""
    if emotion_lexicon:
        from core.media.emotion_lexicon import render_emotion_scale
        emotion_scale = render_emotion_scale(emotion_lexicon,
                                             _segment_emotion_keys(new_events))
    # 段的日期 = **段内最后一条内容事件**的时刻（2026-09-17, ESSAY §10 时间轴换代）。
    # ⚠️ **不是 `datetime.now()`** —— 那是"写库时刻 / 记账时刻"，而 `ts` 要的是
    #    "这段记忆是什么时候形成的"。
    # **为什么是"最后一条"**: 羁绊剧情期间玩家无法发消息、且每次进入都从头重放
    #    → **玩完（`vn_exit`）那一刻 = 玩家过完整段** → 那一刻才是记忆形成时刻。
    # **为什么用 `new_events` 而不是全部事件**: 后者会取到 digest 自己刚写的
    #    `affection/digest`（本次调用内生成）—— 循环依赖。
    from core.worldtime.age import now_ts as _now_ts      # 写侧单一真源（带时区）
    now_ts = ((new_events[-1].ts or "").strip()
              or _now_ts())
    # （原 `segment_id = f"seg-{interact_max}"` 2026-09-21 删——段边界本来就由 marker
    #   派生（`_segment_domain`），落库的那份零读者。）

    # 时间预算（⭐ 2026-09-29 刀 1）: 这里是**整段硬顶**, 每轮还有自己的预算 ——
    # 每轮的截止 = `min(硬顶, 本轮开始 + budget_of(spec))`, 在 `_round_call` 里算。
    # 判据: 只留硬顶 ⇒ 前几轮慢就把后面几轮饿死（改之前的病）; 只留每轮 ⇒ 段可以无限长。
    hard_deadline = time.monotonic() + deadline_seconds
    on_mind_box: list[str] = []          # ⭐ N4a: Round A 收下的那句心境（0/1 条）

    try:
        # ── ① R1 记 ──（步序 = `rounds.ROUNDS`; 每步先 `enter` 再干活）
        cur = Cursor()
        spec = cur.enter("round_a")
        system_a = _system_for(spec, domain=domain, chapter_count=len(chapters))
        user_a = _sections_for(spec, [
            ("本段新增互动", timeline),
            ("本章标题", " / ".join(c["title"] for c in chapters if c["title"])),  # 多章都列; 空 → 跳过
            ("画面记忆", "\n".join(f"- {v}" for v in visuals)),
            ("角色人设（锚点）", character_prompt),
            ("本段情绪标尺", emotion_scale),
        ])
        entries, resp_a = _round_call(
            llm, system_a, user_a, spec=spec,
            model=model, temperature=temperature, max_tokens=max_tokens,
            llm_timeout=llm_timeout,
            extra_body=extra_body, hard_deadline=hard_deadline,
            parse_fn=_parse_for(spec, seq_set=seq_set, on_mind_out=on_mind_box),
            result=result)
        if entries is None:
            return _rollback(store, snapshot, result,
                         from_seq=digest_from, upto_seq=interact_max)
        # ⭐ N4a: 她此刻那句心境 —— L1 产出, 与 promise（R4）一样走 `notes_ops`
        # （调用方**整批 ok 之后**才 append）。⚠️ 只有**她真写了**才产操作:
        # 缺键 = 不变（`rewrite_op(on_mind=None)` 本来就不动它）。
        if on_mind_box:
            result.notes_ops.append(rewrite_op(on_mind=on_mind_box[0]))
        # 索引 → 原文（T14）: parse 层拿不到事件流, 回填在这里做
        for ent in entries:
            _resolve_verbatim(ent, by_seq)
        # ⭐ N3（2026-09-29）: `span` → 区间内全部内容 seq。
        # ⚠️ **必须在 `_collapse_bond_episodes` 之前** —— 那一章的归属靠 `event_seq`
        #    与章块**相交**, 展开前只有两个端点, 章块夹在中间时会漏判。
        _unclaimed, _shared = _expand_spans(entries, seq_set)
        logger.info("digest_span eps=%d 认领=%d 未认领=%d 共享=%d（共享只记账, 不裁）",
                    len(entries), len(seq_set) - len(_unclaimed),
                    len(_unclaimed), _shared)
        # 一章一个 episode（2026-09-20）—— 引擎确定性收口 + 可观测告警
        entries = _collapse_bond_episodes(entries, chapters)
        # ── 时间推进：**已退役**（2026-09-17, `ESSAY_TIME_MODEL §10`）──
        # 旧实现读 Round A 的 `time_span` 推进 `WorldClock` 的**剧情游标**,
        # 再把新游标 stamp 到节点上（`story_time`）。整条链已废:
        # **唯一日期轴是现实日期**（`node.ts` —— 由下面的 `ts=now_ts` 落下），
        # 剧情内部的流逝自由但**不累积、不进账**。
        # 段的日期 = 段内最后一条内容事件的时刻（见上面 `now_ts` 的取法）。
        # ⚠️ 契约侧的 `time_span` 字段本身也已删（2026-09-17 用户裁决）—— 它当时
        #    "保留但不消费", 而**新衰减模型的输入是活跃日/会话, 不是它**;
        #    加上 parse 层从来没取过它（连落库都没有）, 留着就是白付 token。
        #    枚举定义仍留在 `core/worldtime/span.py`。详见 `contract/digest_registry.py`。
        episode_ids, player_ids = _create_a_nodes(
            store, entries, ts=now_ts,
            event_seq=[interact_max], aff_at_encoding=aff_at_encoding,
            by_seq=by_seq)

        # ⭐⭐ N5c: 把本段的「想起」账补成 `akin` 边（`DESIGN_MMT_NEW_ACTION §4.3 ④`）。
        # 位置: **建完 episode 之后的第一件事** —— 原设计的"边先落在 seq 上"走不通
        # （`add_edge` 拒悬空, 而"当下"是 seq 不是节点）, 所以账在 MMT 那一刻只记一笔,
        # 边**到这里才落**（两端都已是真节点）。
        noticed = [e for e in new_all if getattr(e, "type", "") == TYPE_NOTICED]
        if noticed:
            cur.enter("akin")                            # 零 LLM 的一步也占步序
            n_edge, n_lost, n_self = _link_akin(store, episode_ids, noticed, ts=now_ts)
            logger.info("digest_akin edges=%d unclaimed=%d self=%d", n_edge,
                        n_lost, n_self)

        # ── ② R4 记账（约定收口）—— 编排顺序照旧 R1 → **R4** → R2 → R3 ──
        # ⏸ 从前"必须夹在这里"的理由是 `close` 会物化 promise 节点、而它的边由后两轮写;
        # **2026-09-29 承诺退图之后这条理由消失**（R4 只产 note 操作, 不碰图）——
        # 顺序今天照旧（改了它没有收益, 却要重验一遍编排), 但不再是正确性要求。
        spec = cur.enter("close")
        note_state = store.notes_state(events)            # 本段之前的备忘录（缓存优先）
        open_promises = [it for it in note_state.promise if not it.closed]
        if episode_ids or open_promises:
            system_c = _system_for(spec)
            user_c = _sections_for(spec, [
                ("还开着的约定", _open_promises_text(open_promises)),
                ("本段新增的经历", _episode_lines(store, episode_ids)),
            ])
            rows_c, resp_c = _round_call(
                llm, system_c, user_c, spec=spec,
                model=model, temperature=temperature, max_tokens=max_tokens,
                llm_timeout=llm_timeout, extra_body=extra_body,
                hard_deadline=hard_deadline,
                parse_fn=_parse_for(spec), result=result)
            if rows_c is None:
                return _rollback(store, snapshot, result,
                         from_seq=digest_from, upto_seq=interact_max)
            closures = apply_closures(store, rows_c, note_state=note_state, ts=now_ts)
            # ⚠️ **append 不覆盖** —— `notes_ops` 里已经有 L1 交来的那句 `on_mind`（N4a）
            result.notes_ops.extend(closures.ops)          # ⚠️ 调用方等 ok 之后才 append
            result.notes_warnings = list(closures.warnings)
            for w in closures.warnings:
                logger.warning("digest_close: %s", w)
            logger.info("digest_close open=%d add=%d close=%d warn=%d",
                        len(open_promises),
                        sum(1 for o in closures.ops if o.get("action") == "add"),
                        sum(1 for o in closures.ops if o.get("action") == "close"),
                        len(closures.warnings))
        else:
            # 这一轮**必然空转**（`add` 没有可引用的经历、`close` 没有可翻篇的条目）
            _log_skip(spec)

        # ── ③ R2 接（理解者: 引擎候选推荐 + 决策表）──
        # ⏸ 原 `must_include`（本轮 R4 物化的 promise 必进列表）2026-09-29 随退图删 ——
        # 参数在 `render_cognition_list` 上一起摘掉（零调用方）。
        spec = cur.enter("round_b")
        cog_text, local_of = render_cognition_list(
            store, cap=COGNITION_CAP, exclude=set(player_ids))
        # ⚠️ `links` 认的 id 集今天 = 可 touch 的看法（承诺退图后不再有第二种端点）;
        # 那个"两个 id 空间故意不同"的口径见 `parse_round_b` 的 `link_ids`。
        target_ids = {local for real, local in local_of.items()
                      if getattr(store.get(real), "kind", "") in ("belief", "experience")}
        link_ids = set(local_of.values())
        ep_text = _round_b_material(store, episode_ids, local_of,
                                    embed_fn=embed_fn,
                                    char_id=getattr(store, "char_id", ""))
        system_b = _system_for(spec)
        user_b = _sections_for(spec, [
            ("本次新经历（含引擎候选标注）", ep_text),
            ("本段时间线", timeline),
            ("现有认知", cog_text),
            ("角色人设（锚点）", character_prompt),
        ])
        rows, resp_b = _round_call(
            llm, system_b, user_b, spec=spec,
            model=model, temperature=temperature, max_tokens=max_tokens,
            llm_timeout=llm_timeout,
            extra_body=extra_body, hard_deadline=hard_deadline,
            parse_fn=_parse_for(spec, episode_ids=set(episode_ids),
                                target_ids=target_ids, link_ids=link_ids),
            result=result)
        if rows is None:
            return _rollback(store, snapshot, result,
                         from_seq=digest_from, upto_seq=interact_max)
        r2_created = apply_decisions(store, rows,
                                     id_map={v: k for k, v in local_of.items()},  # local→real
                                     ts=now_ts,
                                     event_seq=[interact_max])

        # ── ④ R3 挂（归属 + entity 维护）──
        # 为什么在最后: 它要挂的是**本轮全部新节点**（R1 的经历/画像 +
        # R2 新建的认知）⇒ 前面几轮都落地了它才看得全（§8 的批内顺序 R1→R4→R2→R3）。
        spec = cur.enter("attr")
        new_ids = ([*episode_ids, *player_ids, *r2_created])
        node_text, node_local = new_nodes_block(store, new_ids)
        if not node_text:
            _log_skip(spec)
        else:
            table_text, ent_local = candidate_table(store)
            # ⭐ 2026-09-29: `about_hint`（R1 预判的名字）退役 ⇒ 这里只喂**正文通道**
            # （引擎从新节点的 text/title/verbatim 里认称呼, 确定性）。
            # ⚠️ **命中集只决定"给 R3 看哪些对象的当前载荷"** —— 候选表是全量的,
            # 所以命中变窄 = 少看一点载荷, **不是判不了挂谁**（`REDUNDANCY.md` #2）。
            hits = hit_set(store, texts=_node_texts(store, new_ids))
            payload = payload_block(store, hits, ent_local)
            logger.info("digest_hit eps=%d hit=%d", len(new_ids), len(hits))
            system_d = _system_for(spec)
            user_d = _sections_for(spec, [
                ("候选对象", table_text or "（还没有任何对象）"),
                ("这几个对象的当前情况", payload),
                ("本轮新节点", node_text),
                ("角色人设（锚点）", character_prompt),
            ])
            rows_d, resp_d = _round_call(
                llm, system_d, user_d, spec=spec,
                model=model, temperature=temperature, max_tokens=max_tokens,
                llm_timeout=llm_timeout, extra_body=extra_body,
                hard_deadline=hard_deadline,
                parse_fn=_parse_for(spec, entity_ids=set(ent_local.values()),
                                    node_ids=set(node_local.values())),
                result=result)
            if rows_d is None:
                return _rollback(store, snapshot, result,
                         from_seq=digest_from, upto_seq=interact_max)
            result.created_entities = apply_attribution(
                store, rows_d,
                id_map={v: k for k, v in node_local.items()},   # local→real
                local_of=ent_local, ts=now_ts, event_seq=[interact_max])
            logger.info("digest_attr table=%d hit=%d payload=%d rows=%d new=%d",
                        len(ent_local), len(hits), len(payload.splitlines()),
                        len(rows_d), len(result.created_entities))

        # ── ⑤ L2-a 分群（N7）: 每段的**最后一步**, 与 R1–R4 **不同层** ──
        # 料 = 引擎切好的块（`akin` 连通块, ⭐ **边不进视野**）+ 已有的类;
        # 产 = **群节点 + `member_of` 边**。⚠️ 它**只起名**, 不判"像不像"（那是她的活）。
        # ⚠️ **它失败不连累整段**: 分群是**加法**的（块留到下段再来 ⇒ 自愈）, 所以这一步
        #    自带快照（表里 `own_snapshot=True`）—— 失败只回滚它自己, R1–R4 的活照常提交
        #    （把"命名没成"升级成"整段记忆全丢"是拿真东西换装饰）。
        spec = cur.enter("group")
        blks = groups.build_blocks(store, groups.ungrouped(store))
        cands = groups.merge_candidates(store)
        if not blks and not cands:
            _log_skip(spec)
        else:
            grp_snap = store.clone_state()
            err0 = len(result.errors)
            system_e = _system_for(spec)
            user_e = _sections_for(spec, [
                ("还没归类的块",
                 groups.render_blocks(store, blks) or "（这一段没有新连出来的块）"),
                ("已有的类", groups.render_groups(store) or "（还没有任何类 —— 全部走 new）"),
                ("可能重复的类", groups.render_merge_candidates(store, cands)),
            ])
            rows_e, resp_e = _round_call(
                llm, system_e, user_e, spec=spec,
                model=model, temperature=temperature, max_tokens=max_tokens,
                llm_timeout=llm_timeout, extra_body=extra_body,
                hard_deadline=hard_deadline,
                parse_fn=_parse_for(spec, block_ids={b.bid for b in blks}),
                result=result)
            if rows_e is None:
                store.restore_state(grp_snap)
                result.group_warnings.extend(result.errors[err0:])
                del result.errors[err0:]                 # ⚠️ ok=True 不许带 errors
                logger.warning("digest_group 失败（只回滚这一步, 本段照常提交）: %s",
                               "; ".join(result.group_warnings[-3:]) or "(无)")
            else:
                # ⚠️ 顺序: **先归属, 后并群** —— 反过来那条 attach 会打在一个已经删掉的类上
                gres = groups.apply_groups(
                    store, [r for r in rows_e if r["action"] in ("attach", "new")],
                    blks, ts=now_ts, event_seq=[interact_max])
                mres = groups.apply_merges(
                    store, [r for r in rows_e if r["action"] == "merge"], cands, ts=now_ts)
                result.created_groups = list(gres.nodes)
                result.grouped_episodes = len(gres.grouped)
                result.merged_groups = list(mres.merged)
                result.group_warnings = list(gres.warnings) + list(mres.warnings)
                for w in result.group_warnings:
                    logger.warning("digest_group: %s", w)
                logger.info("digest_group blocks=%d cand=%d rows=%d new=%d grouped=%d "
                            "merged=%d moved=%d warn=%d",
                            len(blks), len(cands), len(rows_e), len(gres.nodes),
                            len(gres.grouped), len(mres.merged), mres.moved,
                            len(result.group_warnings))
    except ValueError as e:                              # store 层拒绝 → 回滚
        result.errors.append(str(e))
        return _rollback(store, snapshot, result,
                         from_seq=digest_from, upto_seq=interact_max)

    # ── 成功: 提交（节点落盘 + 水位推进）──
    result.ok = True
    result.created = episode_ids
    result.affection_delta = _clamp_aff(resp_b.get("affection_exp_delta"))
    store.save()
    # 游标提交：**已退役**（2026-09-17）—— 没有剧情游标可落盘。
    store.meta["digested_seq"] = max((e.seq for e in events), default=interact_max)
    # ⭐ 成功 ⇒ **失败计数清零**（这一段过去了; 留着它会让下一段白背两次"前科"）。
    store.meta.pop("digest_retry", None)
    store.save_meta()
    return result


# ---------------------------------------------------------------------------
# 轮次调用（调用 + parse + 反馈回灌, feedback 语义）
#
# ⚠️ 每轮"是谁 / 用哪份 prompt / 哪个契约相位 / 怎么解析 / 吃什么"全在
#    `core/digest/rounds.py` 的表里 —— 下面三件套只是把表里的声明**接上执行**,
#    调用点不再各写一份字面量（写了就会漂）。
# ---------------------------------------------------------------------------

def _system_for(spec: RoundSpec, **schema_kw) -> str:
    """这一轮的 system = 对应 prompt 文件 + 该轮的**产出契约**（`{{digest_schema}}`）。

    `schema_kw` 给 `build_schema` 的分域参数（只有 R1 需要: `domain` / `chapter_count`）。
    """
    return load_prompt(spec.prompt).replace(
        "{{digest_schema}}", digest_registry.build_schema(spec.phase, **schema_kw))


def _parse_for(spec: RoundSpec, **ctx) -> Callable[[dict], tuple[Any, Any]]:
    """把表里那个 parse 函数绑上**这一轮的上下文**（`seq_set` / `episode_ids` / `block_ids`…）。

    契约层的 parse 签名统一是 `(raw, **ctx)` ⇒ 表里存函数、调用点给上下文, 两不相欠。
    """
    return lambda raw: spec.parse(raw, **ctx)


def _sections_for(spec: RoundSpec, sections: list[tuple[str, str]]) -> str:
    """按表校对**料的段标题**再拼装 —— 表说这一轮吃什么, 这里就必须是那几段。

    ⚠️ 只校标题（"吃什么"的地图）, 不校正文（正文由各家现算）。对不上 = 表在骗人,
    所以**当场炸**而不是静默放行 —— 这正是"料跨 3~4 个文件"的解药:
    想知道 R2 吃什么, 看表一行就够, 而表**不可能**与实际不符。
    """
    got = tuple(title for title, _ in sections)
    if got != spec.material:
        raise AssertionError(
            f"digest {spec.key!r} 的料与轮次表不一致: 表={spec.material} 实际={got}"
            "（改料就要改 core/digest/rounds.py 的 ROUNDS）")
    return _join_sections(sections)


def _log_skip(spec: RoundSpec) -> None:
    """跳过这一轮 —— 那句日志的文案也来自表（`skip` 是唯一真源）。"""
    logger.info("digest_%s 跳过（%s）", spec.key, spec.skip)


def _round_call(
    llm,
    system: str,
    user: str,
    *,
    spec: RoundSpec,
    model: str | None,
    temperature: float,
    max_tokens: int,
    llm_timeout: float | None,
    extra_body: dict | None,
    hard_deadline: float,
    parse_fn: Callable[[dict], tuple[Any, Any]],
    result: DigestResult,
) -> tuple[Any | None, dict | None]:
    """一轮 LLM 调用: 调用 → parse → 结构被拒 → assistant 原文 + 错误回灌重试 1 次。

    ⭐ **本轮的截止在这里算**: `min(整段硬顶, 现在 + 本轮预算)`（预算取自轮次表）。
    从前全段共享一个 deadline ⇒ 前几轮一慢, 后面几轮**集体被饿死**, 而报错还看不出
    是哪一轮。现在单轮慢只影响它自己, 失败文案也带轮次。

    ⭐ 回灌走 `llm.client.feedback`（**唯一实现** —— 同 bond/mmt 的形状:
    "assistant 手写被拒原文 + user 走 helper"）; 措辞与从前逐字相同。

    `result` 只用到 `errors` / `llm_calls` 两个字段 ⇒ A/B 轮（`DigestResult`）与
    （全景轮退役前曾与它共用这条路径 —— N4a 起只剩 digest。）

    Returns:
        (parsed, last_resp): parsed None = 该轮失败（result.errors 已填, 调用方回滚）
    """
    round_deadline = _round_deadline(hard_deadline, budget_of(spec))
    label = spec.label
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": user}]
    for attempt in range(MAX_FEEDBACK_RETRIES + 1):
        resp, call_err = llm_chat(llm, system, "", messages=msgs, model=model,
                                  temperature=temperature, max_tokens=max_tokens,
                                  extra_body=extra_body, deadline=round_deadline,
                                  timeout=llm_timeout, label=label)
        if resp is None:
            result.errors.append(
                _call_failed(label, call_err, round_deadline, hard_deadline))
            return None, None
        result.llm_calls += 1
        if not isinstance(resp, dict):
            result.errors.append(f"digest 轮次 {label}: LLM 输出非 JSON 对象")
            return None, resp
        parsed, vr = parse_fn(resp)
        if vr.is_valid:
            return parsed, resp
        if attempt < MAX_FEEDBACK_RETRIES:
            # feedback 语义: 同一上下文——追加被拒输出 + 引擎错误（见 `llm.client.feedback`）
            msgs.append({"role": "assistant",
                         "content": json.dumps(resp, ensure_ascii=False)})
            feedback(msgs, "【引擎校验反馈（上一轮输出被整包拒绝,"
                           " 请修正后重新输出完整 JSON）】\n"
                           + "\n".join(f"- {e}" for e in vr.errors))
            continue
        result.errors.extend(vr.errors)
        return None, resp
    return None, None                                     # unreachable


def _round_deadline(hard_deadline: float | None, budget: float) -> float | None:
    """本轮的截止时刻 = `min(整段硬顶, 现在 + 本轮预算)` —— **判据在这一行**。

    两个都要: 只看本轮预算 ⇒ 段可以无限长（半小时那次事故）; 只看整段硬顶 ⇒
    前几轮一慢就把后面的轮饿死（刀 1 要修的那个病）。
    """
    if budget <= 0:
        return hard_deadline
    soft = time.monotonic() + budget
    if hard_deadline is None:
        return soft
    return min(hard_deadline, soft)


def _call_failed(label: str, call_err: str | None, round_deadline: float | None,
                 hard_deadline: float | None) -> str:
    """一轮调用失败的记账 —— **带上轮次**, 并说清是"本轮预算用完"还是"整段硬顶到了"。

    从前这句是裸的 `LLM 调用撞上时间预算`（`llm_call` 的原文）, grep 出来分不出
    是哪一轮、也分不出是哪种预算 ⇒ 事后无法定位"谁把时间吃掉了"。
    """
    msg = call_err or "LLM 调用失败"
    if round_deadline is None:
        return f"digest 轮次 {label}: {msg}"
    left = round_deadline - time.monotonic()
    hit_cap = hard_deadline is not None and round_deadline >= hard_deadline
    which = "整段硬顶到了" if hit_cap else "本轮预算用完"
    return f"digest 轮次 {label}: {msg}（{which}, 离本轮截止还剩 {max(left, 0.0):.0f}s）"


# ---------------------------------------------------------------------------
# 引擎侧: 建节点 / 渲染 / 清洗
# ---------------------------------------------------------------------------

def _segment_domain(events: list) -> tuple[str, list[dict], frozenset]:
    """本段类型、**每一章的分组**、章块并集（从 marker 与事件类型派生, 不落库）。

    用户原话: *"离散的是 mmt，但 bond story 不应该连续吗"* ⇒ **粒度跟着"作者单位"走**:
    一章羁绊剧情 → **恰好 1 条**; MMT 碎聊 → 0~5 条（**需要切分的是它**）。

    ⚠️ **窗口是"混的"—— 实测真档**（2026-09-20）: haruka 的窗口里 **13 条 MMT 聊天 +
    5 块羁绊剧情**; mutsuki 是 **26 + 13**。所以不能"整段按一个契约"。

    ⚠️⚠️ **窗口里还可能有"多章"** —— 水位被清 / 重跑时**必然**如此。
    所以"一章一条"必须**按章分组**收口; 拿全窗口的 bond 块当一个章, 会把两章压成一条。

    Returns: `(domain, chapters, bond_seqs)`
        domain: `"bond"`（窗口里有 `vn_enter`）/ `"mmt"`
        chapters: `[{"title": str, "seqs": frozenset[int]}]` —— **一章一块**
            （`vn_enter` … `vn_exit` 之间的 bond 事件）; 不在任何章里的 bond 块
            自成一组（旧档/异常, 标题为空）
        bond_seqs: 全部章块的并集（"这条条目属不属于某一章"的粗判用）
    """
    from core.session.events import M_VN_ENTER, M_VN_EXIT
    chapters: list[dict] = []
    cur: dict | None = None
    orphan: set = set()
    for e in events:
        if getattr(e, "is_marker", False):
            if e.subtype == M_VN_ENTER:
                cur = {"title": str((getattr(e, "payload", None) or {})
                                    .get("chapter_title") or "").strip(),
                       "seqs": set()}
                chapters.append(cur)
            elif e.subtype == M_VN_EXIT:
                cur = None
            continue
        if getattr(e, "type", "") == "bond":
            (cur["seqs"] if cur is not None else orphan).add(e.seq)
    if orphan:
        chapters.append({"title": "", "seqs": orphan})
    chapters = [{"title": c["title"], "seqs": frozenset(c["seqs"])} for c in chapters]
    union = (frozenset().union(*[c["seqs"] for c in chapters]) if chapters
             else frozenset())
    return ("bond" if chapters else "mmt"), chapters, union


def _in_seqs(e: dict, seqs: frozenset) -> bool:
    """条目声明的 `event_seq` 是否落在给的那组块里。"""
    return any(int(s) in seqs for s in (e.get("event_seq") or [])
               if isinstance(s, (int, str)) and str(s).lstrip("-").isdigit())


def _expand_spans(entries: list[dict], seq_set: set[int]) -> tuple[list[int], int]:
    """⭐ `span` → 区间内**全部**内容 seq（**N3**, 2026-09-29）—— 就地改写成 `event_seq`。

    ⚠️ **必须 `pop` 掉 `span`**: `_create_a_nodes` 走
    `make_node("episode", **{k: v for k, v in ent.items() if k != "kind"})` ——
    留在条目里的 `span` 会被 `from_dict` **静默忽略**（这个项目最恨的静默 no-op;
    `about_hint` 当年也是为这个专门 `pop` 的 —— 它 2026-09-29 已退役）。

    ⚠️ **必须在 `_collapse_bond_episodes` 之前跑**: 那一章的归属判据 `_in_seqs` 靠
    "条目的 `event_seq` 与章块的**相交**" —— 展开前只有两个端点, 章块夹在中间
    （span `[80, 100]` / 章 `86..97`）时**两个端点全在章外** ⇒ 那条会被误判成"不属于本章"。

    Returns: `(未认领的 seq 升序, 被 ≥2 条 episode 共享的 seq 数)`

    ⭐ **重叠如实报告、不裁**: 同一段事件本来就可以同时是两件事（真机 `m0015`
    「约老师来看苔藓」`[208..235]` 与 `m0016`「老师说我很重要」`[214..223]` **整段嵌套**;
    裁掉"先到先得"会让 `m0016` 丢掉它**唯一的位置证据**）。
    而"未认领"才是真病 —— 真机 218 条内容事件里 **70 条（32%）没进任何记忆**。
    """
    counts: dict[int, int] = {}
    for ent in entries:
        span = ent.pop("span", None)
        if span is None:
            # 旧形状（`event_seq` 逐点）或没给位置 —— 原样计入, **不展开**
            for s in ent.get("event_seq") or []:
                counts[s] = counts.get(s, 0) + 1
            continue
        lo, hi = int(span[0]), int(span[1])
        seqs = sorted(s for s in seq_set if lo <= s <= hi)
        if seqs:
            ent["event_seq"] = seqs
            for s in seqs:
                counts[s] = counts.get(s, 0) + 1
    unclaimed = sorted(seq_set - set(counts))
    shared = sum(1 for n in counts.values() if n > 1)
    return unclaimed, shared


def _collapse_bond_episodes(entries: list[dict], chapters: list[dict]) -> list[dict]:
    """**按章**收口: 每一章的 episode 只留 1 条 —— "一章一个 episode"的引擎侧兜底。

    契约在 `contract/digest_registry._DOMAIN_CONTRACT`（提示词侧）；这里是
    **确定性兜底**: 提示词没压住时留 `significance` 最高的那条, 其余丢弃, 并留一行
    `WARNING`（可 grep）—— 免得契约被违反是**静默**的。

    ⚠️ **逐章收口**, 不是"整段收口"（见 `_segment_domain` 的两条警告）:
    * 窗口常同时含 MomoTalk 聊天（真档实测 13 / 26 条）—— 那些条目**不属于任何章**,
      照 0~5 条留着（把整段压成 1 条会把聊天里的记忆一起丢掉）;
    * 窗口还可能有**多章**（水位清空后必然）—— **每章各留 1 条**。

    `experience`（玩家画像）不算 episode。为什么丢弃而不是合并文本: 合并是创作（要 LLM）,
    引擎只做判定; 而"一章一条"的前提是那条总结**本来就该覆盖全章**。
    """
    if not chapters:
        return entries
    dropped: set[int] = set()
    for ch in chapters:
        seqs = ch["seqs"]
        if not seqs:
            continue
        group = [e for e in entries
                 if e.get("kind") != "experience" and _in_seqs(e, seqs)]
        if len(group) <= 1:
            continue
        keep = max(group, key=lambda e: float(e.get("significance") or 0.0))
        logger.warning(
            "digest_a contract=bond chapter=%r entries=%d keep=%r（一章一条; 其余已丢。"
            "这行常出现 = 提示词没压住, 看 Round A 的【本段类型】产出契约）",
            ch["title"] or "-", len(group),
            keep.get("title") or str(keep.get("text", ""))[:12])
        dropped |= {id(e) for e in group if e is not keep}
    return [e for e in entries if id(e) not in dropped]


def _node_ts(seqs: Any, by_seq: dict | None, default: str) -> str:
    """一条节点的时刻 = **它自己指向的那些事件里最后一条**的 ts（取不到 → 传进来的段 ts）。

    ⭐ 2026-09-25（链路 ④-①）: 从前**整段一个 ts** —— 那批记忆共享同一天, 读不出先后。
    取"最后一条"的理由与"段 ts = 段内最后一条内容事件"**同源**: 那一刻才是这条记忆
    "到这儿为止"的样子。

    ⚠️ **只改第 1 轮产的节点**（episode / 玩家画像）: 它们手里有 LLM 指的**真事件指针**。
    第 2/4 轮产的节点（信念 / 承诺）指针本来就是段级的 `[interact_max]`, 且"她什么时候
    想明白的 = 消化那一刻"语义没错 ⇒ 继续用段 ts。
    ⚠️ **真机实测: 羁绊章内的跨度只有分钟级**（haruka 那批 75 条事件跨 12 分钟）⇒
    「（3 周前）」这类短语**不会变**（按日历日算）; 这条改动的收益在
    **① 批内排序**（从 id 序 → 真实时刻序）**② MMT 段**（一次消化覆盖 25 轮、可能横跨几天,
    从前全部被标成"最后那条消息那一天"）。
    """
    best, best_seq = "", -1
    for s in seqs or []:
        try:
            seq = int(s)
        except (TypeError, ValueError):
            continue
        ev = (by_seq or {}).get(seq)
        t = str(getattr(ev, "ts", "") or "").strip() if ev is not None else ""
        if t and seq >= best_seq:
            best, best_seq = t, seq
    return best or default


def _create_a_nodes(store: WikiStoreV2, entries: list[dict], *, ts: str,
                    event_seq: list[int],
                    aff_at_encoding: float | None = None,
                    by_seq: dict | None = None
                    ) -> tuple[list[str], list[str], list[dict]]:
    """Round A 条目 → 节点（引擎字段归属——确定性归引擎, 防幻觉）。

    kind=episode  → episode 节点
    kind=experience（玩家画像, MMT 专则）→ subject=player experience 节点:
        口癖/偏好/一次性个人信息——不进本轮 B（B 只组织 episode）, 下轮起参与认知层
    dedupe: (kind, event_seq, 主文本) 命中已有节点 → 复用 id（崩溃窗口重跑防双写）。

    event_seq（T14, 2026-09-15）: **条目自带就用条目自带的**（Round A 抄的行号,
    已在 parse 层校验 ⊆ 本段）, 否则回落到段级 `[interact_max]`。
    ⭐ **N3（2026-09-29）后, "条目自带的"是引擎展开好的区间**（`_expand_spans` 把
    `span` 换成区间内全部内容 seq）—— 本函数**一行没改**: 字段名与形状都没变,
    变的只是它的**来源**（从"她挑的点"变成"引擎算的区间"）。
    旧版**无条件覆写**成 `[interact_max]`——实测 mutsuki 全段 `[60]` 而板最大 55,
    它指向一条 MMT 消息、不指向任何一板, 于是板指针从来没存在过,
    而 `migrate_time` 的唯一排序信号也一起死掉（全部节点同键 → 退化成插入序）。

    aff_at_encoding（§3.3.3, 2026-09-13）: 本段**开始之前**的好感标量
    （`Affection.to_scalar()`, [−1,1]）——快照, 写入后永不改。
    调用方传 None = 未采集（旧档/CLI 路径）→ 字段不落库, 与 `0.0`（中性）区分。

    ⭐ D1（2026-09-22）:
      · ~~`items`（§3.1 物品台账）随条目自动落库~~ —— **2026-09-29 字段退役**（零活读者;
        物品面将来走 `inventory` 旁路）。
      · ~~`about_hint`（§8.2 归属线索）必须在这里摘掉~~ —— **2026-09-29 字段退役**:
        它和 R3 的"挂谁"**判两次**（还可能不一致）, 而 R3 本来就拿得到全量候选表 +
        新节点正文 ⇒ 引擎不必替它预判一个名字（`REDUNDANCY.md` #2）。

    Returns: `(episode_ids, player_ids)`——episode_ids 供 B 覆盖检查。
    """
    from core.brain.revise import _find_duplicate
    episode_ids: list[str] = []
    player_ids: list[str] = []
    for ent in entries:
        if ent.get("kind") == "experience":
            # ⚠️ `subject` **强制**成 `player`（§5.1）: `experience` 只有一个意思
            # （"关于老师的事"），而 `subject` 是自由文本 —— 契约层已经强制过一次,
            # 这里再强制一次是因为**可见性曾经挂在它上面**（真机 haruka e0001 就是
            # 被一个自造的 subject 藏起来的）。别再让它有第二个写者。
            node = make_node("experience",
                             text=ent["text"], subject=PLAYER_SUBJECT,
                             verbatim=ent.get("verbatim", ""),
                             verbatim_seq=ent.get("verbatim_seq", []),
                             tags=ent.get("tags", []),
                             significance=ent.get("significance", 0.5))
            node.event_seq = list(ent.get("event_seq") or event_seq)
            node.ts = _node_ts(node.event_seq, by_seq, ts)   # ⭐ 自己的时刻（④-①）
            dup = _find_duplicate(store, node)
            if dup is not None:
                player_ids.append(dup.id)
                continue
            player_ids.append(store.add(node))
            continue
        node = make_node("episode", **{k: v for k, v in ent.items() if k != "kind"})
        # ⭐ **N2b**: 标题唯一性**写入时强制**（冲突加数字; 只增不重排）——
        # 解析与写入都在 `address.py` 里（那边是"谁能被指到"的唯一约定）。
        node.title = unique_title(store, node.title)
        node.event_seq = list(ent.get("event_seq") or event_seq)
        node.ts = _node_ts(node.event_seq, by_seq, ts)       # ⭐ 自己的时刻（④-①）
        # 板级情绪键序列（T15）——召回侧物化, **不进 LLM 上下文**
        if by_seq is not None:
            node.emo_shape = _emotion_shape(node.event_seq, by_seq)
            # 地点键序列（M3, 2026-09-19）——同一手物化, 同一纪律
            node.place = _place_shape(node.event_seq, by_seq)
            # 叙事轴: writer 原文（键不是地名的双射, 判"同地"只能靠语义）
            node.place_raw = _place_raw(node.event_seq, by_seq)
        node.aff_at_encoding = aff_at_encoding
        dup = _find_duplicate(store, node)
        if dup is not None:
            episode_ids.append(dup.id)
            continue
        nid = store.add(node)
        episode_ids.append(nid)
    return episode_ids, player_ids


def _link_akin(store: WikiStoreV2, episode_ids: list[str], noticed: list, *,
               ts: str) -> tuple[int, int, int]:
    """⭐ **N5c** · 本段的「想起」账 → `akin` 边。返回 `(落了几条, 未认领, 自环跳过)`。

    链路（`DESIGN_MMT_NEW_ACTION §4.3/§4.4`，已裁 = **只记账 + L1 落地**）::

        她在 MMT 那一刻写 {"noticed": "名字"} → 引擎落一条 `noticed` 事件（N5b）
        → **本函数**: 找到"她说话那一刻属于哪条新 episode" → akin{新 → 她指的}

    ⚠️ **归属判据 = "该账之前、最近的、被某条 episode 认领的内容事件"**
    （`bisect` 在认领 seq 集合里取 `≤ noticed.seq` 的最大者）, 而不是"区间包含" ——
    `noticed` 是**非内容事件**, 它自己的 seq 不在任何 episode 的 `event_seq` 里
    （`digest.new_events` 按 `is_content_event` 过滤）⇒ 包含式判据永远落空。
    ⚠️ 这**依赖 N5b 的落账时机**（账写在那一轮她的话**之后**）: 否则"最近的前一条内容"
      会落到**上一轮**（静默错归属 —— 边连到了错误的那条记忆上）。

    ⚠️ **一跳都不猜**: 找不到归属（本段没产出 episode / 那笔落在所有内容之前）⇒
    **不落边 + 记账**（`unclaimed`）。⚠️ `PROCEED §3` 待裁 #7（"下次 L1 要不要重扫"）
    按 2026-09-29 用户裁决**先不做**: 先丢 + 看台账, 真机上 `unclaimed` 多起来再谈
    （重扫要新存一个"未认领水位", 而"零新存储"正是这条设计的好处之一）。

    幂等: `add_edge` 同 `(rel, src, dst)` 跳过（且 `akin` 对称 ⇒ `canonical_for` 归一）。
    ⚠️ **因此"新 → 旧"的方向不体现在边表里**（对称边被规范成固定顺序）——
    方向只在台账里（`digest_akin new= old=`）。这是**有意的**: `akin` 的语义就是
    "她觉得这两条像"（对称, 见 `DESIGN_MMT_NEW_ACTION §4.5.2`）, 方向不带信息。
    """
    import bisect

    # seq → 主人（本段产的 episode）。⚠️ **区间会交叠**（真机实测 1 对: m0015 ⊃ m0016,
    # 用户裁决"两条都保留"）⇒ 同一 seq 可能有两个主人。取**靠后**那条（其起点更大 =
    # 更"当下"的那件; 按 min(event_seq) 排序后后写覆盖, 结果与 id 顺序无关）。
    owner: dict[int, str] = {}
    for nid in sorted(episode_ids,
                      key=lambda i: min((store.get(i).event_seq or [10 ** 9]))):
        node = store.get(nid)
        if node is None:
            continue
        for s in node.event_seq or []:
            try:
                owner[int(s)] = nid
            except (TypeError, ValueError):
                continue
    claimed = sorted(owner)
    edges = lost = self_skip = 0
    for e in noticed:
        hit = str(((getattr(e, "payload", None) or {}).get("hit") or "")).strip()
        if not hit or store.get(hit) is None:            # 她指的那条不在库里（旧档/被清）
            lost += 1
            logger.info("digest_akin skip=no_target hit=%r", hit)
            continue
        i = bisect.bisect_right(claimed, e.seq) - 1      # 最近的前一条"有主"内容
        if i < 0:
            lost += 1
            logger.info("digest_akin skip=unclaimed seq=%d title=%r", e.seq,
                        (getattr(e, "payload", None) or {}).get("title"))
            continue
        src = owner[claimed[i]]
        if src == hit:                                   # 本段那条就是她指的那条
            self_skip += 1
            continue
        store.add_edge(REL_AKIN, src, hit, ts=(getattr(e, "ts", "") or ts))
        edges += 1
        logger.info("digest_akin new=%s old=%s", src, hit)
    return edges, lost, self_skip


def _node_texts(store: WikiStoreV2, ids: list[str]) -> list[str]:
    """本轮新节点的正文（喂 `entities.hit_set` 扫称呼用）。

    连 `title` / `verbatim` 一起给 —— 称呼常出现在这两处（"老师"多半在标题或原话里,
    而不在她自己那句总结里）。取不到 → 跳过（绝不编）。
    """
    out: list[str] = []
    for nid in ids:
        node = store.get(str(nid))
        if node is None:
            continue
        for t in (node.text, node.title, node.verbatim):
            if isinstance(t, str) and t.strip():
                out.append(t)
    return out


def _open_promises_text(items: list) -> str:
    """R4 输入之一: **还开着的约定**（带编号 —— 它要照着 `id` 写 `close`）。

    行格式复用注入块的 `notes.render_item`（`n3 周六模型店 (m0009)  ← 记于 3 天前`）——
    ⚠️ **一份行格式只有一个实现**（两个写者必然漂移）。
    """
    from core.brain.notes import render_item
    return "\n".join(f"- {render_item(it)}" for it in items)


def _episode_lines(store: WikiStoreV2, episode_ids: list[str]) -> str:
    """R4 输入之二: **本段新增的经历**（真 id —— `add`/`close` 的 `refs` 只能引它们）。

    ⭐ **2026-09-29**: 行首那一段从 `- m0021 「标题」 正文` 改成 **`- 〔m0021｜《标题》〕正文`**
    —— 与 R2 的新经历行（`_round_b_material`）**同一个头**, 由 `marks.head` 出
    （唯一实现）。⚠️ 原来标题写 `「」`, 而她那份视图里 `「」` 是**逐字原话**
    ⇒ 同形不同义; 而 `「」` 恰恰是会让她**抄错东西**的那种形状。
    ⚠️ **没起名就不出名字格**（不印"（无题）"这种假名字）—— 钥匙仍在, 她照样引得到。
    """
    lines: list[str] = []
    for nid in episode_ids:
        node = store.get(nid)
        if node is None:
            continue
        head = node.text if len(node.text) <= 120 else node.text[:120] + "…"
        lines.append(f"- {marks.head(node, key=node.id)}{head}")
    return "\n".join(lines)


def _round_b_material(store: WikiStoreV2, episode_ids: list[str],
                      local_of: dict[str, str],
                      embed_fn: EmbedFn | None,
                      *, char_id: str = "") -> str:
    """Round B 输入: 新经历摘要 + 每条引擎候选提示（板块 5）。

    每条 episode 用 text 走 recommend_candidates 与现有认知碰撞,
    把最像的几条**列出来给 LLM 参考**（⭐ N2 起: 带正文 + 被引 + 边 + 为什么）。

    ⭐ **N2（2026-09-29）两处形态变化**（都是"看不见就写不出来"那条）:
      · 新经历行: `m0025 「标题」 正文` → **`〔m0025｜《标题》〕正文`**
        （编号是钥匙、书名号里是 gist; 顺带修 `「」` 与她视图里"逐字原话"的同形不同义）
      · 候选行: `→ 候选(sim 0.72): u0001 u0003` → **每条候选一行**,
        带 `〔u0001｜belief｜被引 3〕正文` + 边续行 + `为什么: tags[…]/语义 …`
        （旧形态要求 LLM 自己去翻上面那张表, 而"为什么推荐"完全看不见）

    ⚠️ **候选只是提示, 不分档、不强制**（2026-09-15 T17）: 原先
    `≥CAND_HIGH` 会标【疑似同主题】并让 parse 层**结构强制**禁 `add`——
    而那个阈值从未标定过、实测两模型皆 6/6 全越线 → 新认知永远长不出来。
    现在排序取 top-k 无条件列出，判断全在 LLM（判 add 要在 note 里说明理由）。

    **2026-09-13 V3-0（DESIGN_WIKI_V3 §3.5）**: 末尾打一行**写路径召回台账**
    `recall_write char=… eps=… cands=… best=… mode=…`。

    Returns: episodes_text（含候选提示行）。
    """
    from core.brain.read import recall_ledger
    from core.brain.read.recall import _thr, CAND_K

    thr_k = int(_thr("cand_k", CAND_K))
    acc = recall_ledger.CollisionAccount(char_id)
    modes: list[str] = []

    lines: list[str] = []
    for nid in episode_ids:
        node = store.get(nid)
        if node is None:
            continue
        head = node.text
        if len(head) > 120:
            head = head[:120] + "…"
        # 头由 `marks.head` 出（**唯一实现**）—— `〔m0025｜《今天的杂草屋》〕正文`。
        # 编号是**钥匙**（R2 的 decisions 用它指 episode, 真实 id）；
        # 书名号里是**gist**（正文被截到 120 字, 8~16 字的名字是"这是哪件事"的压缩）。
        lines.append(f"{marks.head(node, key=node.id)}{head}")
        if node.verbatim:
            lines.append(f"    原话: {node.verbatim}")
        query = f"{node.text} {node.verbatim}".strip()
        why: list[str] = []
        cands = recommend_candidates(store, query, embed_fn=embed_fn,
                                     mode_out=modes, why_out=why)
        cands = [(c, s) for c, s in cands if c.id in local_of]   # 只标已渲染的
        acc.episode(n_cand=len(cands),
                    best_sim=(cands[0][1] if cands else 0.0))
        if cands:
            # ⭐ N2: 候选不再只给编号 —— **编号 + 正文 + 被引 + 边 + 为什么被推荐**。
            # 旧形态 `→ 候选(sim 0.72): u0001 u0003` 要求它自己去翻上面那张表,
            # 而"为什么推荐"（tags 命中 / 语义）今天完全看不见 —— 看不见就判不准。
            best = cands[0][1]
            reason = why[0] if why else ""
            lines.append(f"    → 候选 {best:.2f}（为什么: {reason}）:")
            graph = store.graph()
            for i, (c, _s) in enumerate(cands):
                rows = render_cognition_line(store, c, graph, local_of, max_body=60,
                                             indent="       ")
                # ⭐ 只有第一个候选带边续行（后面几个是备选, 印全了纯占地方）
                lines.extend(rows if i == 0 else rows[:1])
            lines.append("       （仅供参照, 同主题就 touch/update, 不同主题就 add）")

    # 通道口径: 全程 semantic / 全程 keyword / 混合（部分 episode 失败降级）
    if modes and all(m == "semantic" for m in modes):
        acc.mode = "semantic"
    elif modes and all(m == "keyword" for m in modes):
        acc.mode = "keyword"
    elif modes:
        acc.mode = "mixed"
    acc.log(thr_k=thr_k)
    return "\n".join(lines) or "（无）"


def _segment_emotion_keys(events) -> list[str]:
    """本段所有 bond 板里**出现过的**情绪键（按首次出现顺序, 去重）。

    来源 = `payload.paragraphs[i].emotion`（标注层产物, 真源在事件流里）。
    只读不写——用于决定"给 Round A 注哪些键的标尺"（§3.3.2）。
    缺字段/坏结构 → 跳过, 不抛（宁缺勿错: 少注一个键, 不阻断 digest）。
    """
    keys: list[str] = []
    seen: set[str] = set()
    for e in events:
        if getattr(e, "type", None) != "bond":
            continue
        payload = getattr(e, "payload", None) or {}
        for p in payload.get("paragraphs") or []:
            if not isinstance(p, dict):
                continue
            k = p.get("emotion")
            if isinstance(k, str) and k.strip() and k.strip() not in seen:
                seen.add(k.strip())
                keys.append(k.strip())
    return keys


def _join_sections(sections: list[tuple[str, str]]) -> str:
    """输入块拼装: 非空块才注入（省 token）; 空块跳过。

    ⚠️ 段头 `【】` 的构造在 `marks.section`（括号表唯一实现）—— 本函数只管"拼"。
    ⚠️ **LLM 轮的输入一律走 `_sections_for`**（它先拿轮次表校对段标题, 再调这里）——
    直接调本函数 = 绕过料校对, `test_sections_check_is_wired` 会红。
    """
    parts = [f"{marks.section(title)}\n{body}" for title, body in sections if body]
    return "\n\n".join(parts)


def _collect_visual_prompts(events) -> list[str]:
    """l2d 事件的 gallery png → 同名 json 的 prompt（视觉记忆）。"""
    prompts: list[str] = []
    for e in events:
        if e.type != "l2d":
            continue
        for img in e.payload.get("images", []) or []:
            if not isinstance(img, str) or not img:
                continue
            gjson = Path(img).with_suffix(".json")
            try:
                meta = json.loads(gjson.read_text(encoding="utf-8"))
                prompt = meta.get("prompt", "")
                if isinstance(prompt, str) and prompt.strip():
                    prompts.append(prompt.strip())
            except (OSError, ValueError):
                continue
    return prompts


def _resolve_verbatim(ent: dict, by_seq: dict) -> None:
    """`verbatim_seq`（记录行号）→ `verbatim`（逐字原文）——**索引是唯一来源**。

    ```
    LLM 只给行号  → 引擎解析出原文回填     ← 唯一的通道, 逐字且永久可重解析
    行号解析不出  → 留空（**绝不编**）      ← 宁缺勿错; 行号本身留在 `verbatim_seq` 里
    ```

    ## ⏸ 文本通道与"文本优先" **2026-09-29 退役**

    从前 LLM 也可以直接抄一句原话（`"verbatim": "…"` 字符串）, 且**两条都给时文本优先**
    —— 那是个**安全决定**: 用户把"错索引不可见"放进待办了, 而错的索引会解析出一句真文本、
    看起来完全正常, 错的原话至少一眼看得出不对。

    退役的理由（`REDUNDANCY.md` #6）: 两条通道说的是**同一件事**, 而正文里的原话本来就
    逐字躺在 append-only 的事件流里 —— 让模型再抄一遍, 等于给"静默换掉一句正确原话"
    开了一个口子, 换来的只是"抄得对"这一种情况下的冗余保险。今天行号是唯一入口,
    解析不出就**留空**: 宁可这条记忆没有原话, 也不放一句无法溯源的引文进去。
    """
    seqs = ent.get("verbatim_seq") or []
    if not seqs:
        return                                   # 无行号 → 留空
    from contract.timeline_index import parse_index
    picked: list[str] = []
    for idx in seqs:
        got = parse_index(idx)
        if got is None:
            continue
        ev = by_seq.get(got[0])
        if ev is None:
            continue
        text = _text_at(ev, got[1])
        if text:
            picked.append(text)
    if picked:
        # 多条关键句拼一行（`" / "` 与时间线的记录分隔同形）——`render.py` 的
        # `（「{verbatim}」）` 是单行渲染, 换行符会把视图打断。
        ent["verbatim"] = " / ".join(picked)


def _text_at(ev, rec) -> str:
    """事件 + 记录位 → 那一条记录的**逐字原文**（取不到 → `""`, 绝不编）。"""
    from contract.timeline_index import REC_PICKED
    if rec == REC_PICKED:
        pk = ev.payload.get("picked")
        return pk.strip() if isinstance(pk, str) else ""
    if ev.type == "mmt":
        key = {0: "player", 1: "reply"}.get(rec)
        v = ev.payload.get(key) if key else None
        return v.strip() if isinstance(v, str) and v.strip() else ""
    paras = ev.payload.get("paragraphs")
    if not isinstance(paras, list) or not isinstance(rec, int):
        return ""
    if not (0 <= rec < len(paras)):
        return ""
    p = paras[rec]
    t = p.get("text", "") if isinstance(p, dict) else str(p)
    return t.strip() if isinstance(t, str) else ""


def _emotion_shape(seqs: list, by_seq: dict) -> list[str]:
    """板指针 → **板级情绪键序列**（按 seq 序拼接; 取不到 → `[]`, 绝不编）。

    只收 bond 事件: 情绪键由**标注层**产出（每条记录一个键）, MMT 事件没有键。
    空键（`""`/None）跳过——标注失败与"真的无表情"在数据里不可分,
    所以只把**有值的键**按顺序连起来（保持弧的形状, 不补位）。

    🚫 返回值只进 `node.emo_shape`（召回侧）——**绝不进 LLM 上下文**。
    """
    out: list[str] = []
    for seq in sorted(seqs or []):
        ev = by_seq.get(seq)
        if ev is None or ev.type != "bond":
            continue
        paras = ev.payload.get("paragraphs")
        if not isinstance(paras, list):
            continue
        for p in paras:
            k = p.get("emotion") if isinstance(p, dict) else None
            if isinstance(k, str) and k.strip():
                out.append(k.strip())
    return out


def _place_shape(seqs: list, by_seq: dict) -> list[str]:
    """板指针 → **地点键序列**（M3, 2026-09-19）; 取不到 → `[]`, 绝不编。

    与 `_emotion_shape` 同一手（`digest` 按 `event_seq` 从真源物化，
    因为 `Channel.gather` 只拿得到节点、翻不了板）:

    * 每板取 `payload.place`（板首 `switch` 解出的**键**）
    * 再取 `payload.paragraphs[*].place`（句级锚点, 板内后续换场）
    * **相邻去重保序** —— 结果 = "这段去过哪些地方"的变化序列;
      同地反复去会留下多个元素（`school_rooftop, classroom, school_rooftop`）

    只收 bond 事件: 地点键由**标注层**产出, MMT 事件没有键。空键跳过
    （标注失败与"这段没换场"在数据里不可分, 不补位——同 `emo_shape` 的取舍）。

    ⚠️ **带的是键不是 writer 本名**（用户 2026-09-19 的疑问）:
    C 链路比的是相等, 而「放学后的教室」/「教室里」/「回到教室」是同一张图、
    三个字符串 —— 本名做等值分组是废的。本名留在事件流里
    （`payload.place_hint` + 锚点句原文）, `event_seq` 指得到, 要重解析时回捞即可。

    🚫 返回值只进 `node.place`（召回侧）——**绝不进 LLM 上下文**。
    """
    out: list[str] = []
    for seq in sorted(seqs or []):
        ev = by_seq.get(seq)
        if ev is None or ev.type != "bond":
            continue
        keys: list[str] = []
        board = ev.payload.get("place")
        if isinstance(board, str) and board.strip():
            keys.append(board.strip())
        paras = ev.payload.get("paragraphs")
        if isinstance(paras, list):
            for p in paras:
                k = p.get("place") if isinstance(p, dict) else None
                if isinstance(k, str) and k.strip():
                    keys.append(k.strip())
        for k in keys:
            if not out or out[-1] != k:              # 相邻去重（保留"再次到访"）
                out.append(k)
    return out


def _place_raw(seqs: list, by_seq: dict) -> list[str]:
    """板指针 → **writer 原文序列**（叙事轴, 2026-09-19 用户指出后补落）。

    取每板的 `payload.place_hint` —— **writer 自己写的那个名词短语**
    （「放学后的教室」「傍晚的学校天台」），相邻去重保序。

    为什么必须有它: 键**不是地名的双射**（一键多义 / 一地多键），所以判"**同地**"
    只能靠语义, 而语义的输入就是原话 —— 见 `nodes.BrainNode.place_raw` 的两轴表。

    ⚠️ 句级锚点的原文**不在这里**（锚点只存 `{sentence, place}`）——那条句子的
    原文在 `payload.paragraphs[i].text`，与 `verbatim_seq` 同一手:
    地址永久有效，要用时按 `event_seq` 回捞。

    🚫 只进 `node.place_raw`（召回侧）——**绝不进 LLM 上下文**。
    """
    out: list[str] = []
    for seq in sorted(seqs or []):
        ev = by_seq.get(seq)
        if ev is None or ev.type != "bond":
            continue
        hint = ev.payload.get("place_hint")
        if isinstance(hint, str) and hint.strip():
            h = hint.strip()
            if not out or out[-1] != h:
                out.append(h)
    return out


# ⏸ `_clean_evidence()` **2026-09-29 删** —— 随 `evidence` 字段一起退役（零消费者）。
# 它当年清洗的是 `function/quote/confidence/note` 四键, 而全仓没有一个产品读者:
# 契约每段要它 ≤5 条 + `quote` 逐字引用时间线 ⇒ 纯白付。别把它加回来。


def _as_int(v: Any, default: int) -> int:
    """宽松取整数（坏值 → `default`）—— ⚠️ 别用 `v or default` 代替:
    `0` 是**合法值**（起点水位就是 0），而 `0 or -1` 会得到 -1。"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _clamp_aff(raw: Any) -> int:
    try:
        return max(_AFF_MIN, min(_AFF_MAX, int(raw)))
    except (TypeError, ValueError):
        return 0


def _rollback(store: WikiStoreV2, snapshot: dict,
              result: DigestResult, *,
              from_seq: int = 0, upto_seq: int = 0) -> DigestResult:
    """**失败的唯一出口**: 回滚内存态 + 记账（这一段第几次 / 要不要放弃）。

    回滚语义（失败 → 零残留; 水位未推进, 磁盘未动）:

    * 2026-09-17（`ESSAY_TIME_MODEL §10`）: 原先还要还原 `WorldClock` 的**内存游标**
      （§4.11 I-a 的配套 —— 否则重试会二次推进时钟）。剧情游标整族退役后
      这一步没了, `snapshot_clock` 参数一并删除。
    * ⭐ 2026-09-25: **R4 的 note 操作一并作废**（§8: 失败 = 整批回滚 ⇒ 那条约定原样开着）。
      note 面必须一起清 —— 事件 append **不可撤销**, 调用方只要看到 `ok=False` 就不写,
      但结果对象里留着它就是一颗雷。
    * ⭐⭐ 2026-09-29（节点 C）: 清哪些字段**由轮次表推导**（`rounds.reset_result`）。
      从前这里是手抄清单, 而它**真的漏过** `notes_warnings`。加字段时表里不写就过不了
      `tests/core/test_digest_rounds.py`。
    * ⭐ **2026-09-29（刀 2）: 这里也是"计数 / 放弃"的入口**（`_note_failure`）——
      从前这一刀只回滚, 于是同一段会被**无限重试**（水位不动 ⇒ 窗口越滚越大 ⇒
      越难成功 ⇒ 正反馈）。`from_seq` / `upto_seq` 由调用点给（起点水位 / 本窗内容上界）。
    """
    store.restore_state(snapshot)
    reset_result(result)
    if upto_seq:
        _note_failure(store, result, from_seq=from_seq, upto_seq=upto_seq)
    return result


def _note_failure(store: WikiStoreV2, result: DigestResult, *,
                  from_seq: int, upto_seq: int) -> None:
    """这一段又失败了一次: **记数**; 数到上限就**放弃**, 并留一条 creep 账。

    三个判据（都不是随手定的）:

    1. **计数的键 = 起点水位**（不是"窗口"）: 失败期间水位不动 ⇒ 键稳定;
       而窗口会随着新对话变长 ⇒ 拿窗口当键就**永远到不了上限**（每次都是"新的一段"）。
    2. **放弃时水位推到"第一次失败那一窗的上界"**: 第 2、3 次之间新攒的内容
       **不能跟着一起丢**（所以 `upto_seq` 只在第一次冻结, 之后不更新）。
    3. **同进程不连试**: 次数由触发点累加（见 `MAX_DIGEST_ATTEMPTS`）。

    ⚠️ **放弃 = 真的丢记忆**: 那段事件**再也不会有节点** ⇒ 召不回（但事件流还在,
    玩家回放照样看得到）。这正是要记一条 creep 账的原因 —— 把"她少了什么"留成事实。
    ⚠️ 账由**调用方**写（`result.creep_rows`, 见 `DigestResult`）: 本函数拿不到事件流。
    """
    rec = store.meta.get("digest_retry")
    # ⚠️ **不能用 `x or 默认值`** 取这两个数: `from_seq` 合法地可以是 **0**（新世界线
    # 的起点水位）—— 而 `0 or -1` 会得到 -1 ⇒ 每次都被判成"换了一段" ⇒ 计数永远到不了上限
    # （这个坑当场踩过: `tests/core/test_digest_skip.py` 钉住）。
    raw_from = rec.get("from_seq") if isinstance(rec, dict) else None
    same = _as_int(raw_from, -1) == from_seq
    attempts = (_as_int(rec.get("attempts") if isinstance(rec, dict) else 0, 0)
                if same else 0) + 1
    first_upto = _as_int(rec.get("upto_seq") if isinstance(rec, dict) else 0, 0) \
        if same else int(upto_seq)

    if attempts < MAX_DIGEST_ATTEMPTS:
        store.meta["digest_retry"] = {"from_seq": from_seq, "upto_seq": first_upto,
                                      "attempts": attempts}
        store.save_meta()
        logger.warning("digest 第 %d/%d 次失败（水位不推进, 下次整段重来）: %s",
                       attempts, MAX_DIGEST_ATTEMPTS,
                       " | ".join(result.errors[-2:]) or "(无错误信息)")
        return

    # ── 放弃这一段 ──
    store.meta["digested_seq"] = first_upto          # ⚠️ 水位推进: 这段不再重来
    store.meta.pop("digest_retry", None)
    store.save_meta()
    result.creep_rows.append(creep_build(
        KIND_DIGEST_SKIP, at_seq=first_upto,
        evidence={"from_seq": from_seq, "to_seq": first_upto,
                  "attempts": attempts, "errors": list(result.errors)[-5:]}))
    logger.warning("digest 放弃这一段: 水位 %d → %d（试了 %d 次, 没消化的内容"
                   "**再也不会有节点**）—— 已留一条 creep 账",
                   from_seq, first_upto, attempts)
