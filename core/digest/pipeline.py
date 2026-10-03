"""pipeline.py — digest 管线的**编排与事务**（设计见 `core/brain/AGENT_BRAIN.md §3` / 板块 4a）。

⭐ **2026-09-29 搬家**: `core/brain/digest.py` → **`core/digest/pipeline.py`**（代码管理节点 B）。
理由: `core/brain/` 是数据层（纯 stdlib 零 LLM）, 而本文件要 contract / llm / session ⇒
分开之后"数据层不 import LLM"才是包边界。⚠️ 本文以下凡写 `digest.py` 的旧路径
一律指**本文件**。

⭐ **2026-09-29 按轮拆包（乙-1）**: 每一轮的**正文**搬进 `core/digest/rounds/<轮>.py`,
本文件只剩编排与事务（**666 → 约 260 行**）::

    core/digest/rounds/__init__.py  轮次表（key/步序/LLM 身份/prompt/相位/parse/料/写什么/跳过/预算/快照）
    core/digest/rounds/base.py      Ctx（段级上下文）+ RoundOut（一轮跑完的交代）
    core/digest/rounds/record.py    ① 记        akin.py 补边（0 LLM）
    core/digest/rounds/close.py     ② 收口      understand.py ③ 接
    core/digest/rounds/attribute.py ④ 挂        group.py      ⑤ 分群 L2-a（自带快照）

**实际跑的步数**（一眼看全在 `core/digest/__init__.py`）: 记 → akin 补边 → 收口 → 接 → 挂 →
分群（共 5 次 LLM 调用 + 1 次零成本补边）。
⏸ 旧文档/旧注释里的 **`R1`/`R2`/`R3`/`R4`** 按这张表对: **R1=记(record) · R4=收口(close) ·
R2=接(understand) · R3=挂(attribute)** —— 轮次 key 就是契约相位名, 见 `rounds.RoundSpec`。

编排（`digest_segment`）::
    1. 增量: new_events = seq > store.digested_seq（无新增 → 0 次 LLM 调用）
    2. 段级料: 时间线(**记录级带行索引**, T14) + 视觉记忆 + 人设锚点 + 段类型/章分组
    3. 建 `Ctx` → **按表循环**: `for spec in ROUNDS: IMPL[spec.key](ctx)`
       ⭐ 每轮有自己的时间预算（表里那格）, 截止 = `min(整段硬顶, 本轮开始 + 预算)`
       ⭐ 任一轮失败 → `_rollback`（整批原子回滚 + 记账）
       ⭐ **例外**: 表里 `own_snapshot=True` 的那一步（分群）失败**只回滚它自己** ——
         取快照 / 回滚 / 把这一步的 errors 挪进它的 warnings 字段, **全在这里执行**
         （从前那 181 行样板散在那一步的调用体里; 现在表说了算）
    4. affection_exp_delta 返回（事件幂等写由调用方——运行时集成层）
    5. 成功 → store.save()（原子整写）+ 推进 meta.digested_seq + save_meta

⚠️ **"轮次表"是唯一真源**（**2026-09-29 节点 C**）: 顺序只由 `rounds.ROUNDS` 说了算 ——
本文件的循环**不再写死任何一步的名字**, 每轮进门前 `ctx.enter(key)`（越序当场炸）。
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
（旧实现重建 user 消息, 模型看不到被拒输出, 修正成功率低）。实现 = `call._round_call`。

失败: 静默降级（logger.warning + DigestResult(ok=False)——wiki 是派生视图,
events.jsonl 唯一真源, 可重算）。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from core.brain.read.recall import EmbedFn
from core.brain.store import WikiStoreV2
from core.creep import KIND_DIGEST_SKIP, build as creep_build
from core.digest.material import _collect_visual_prompts, _segment_emotion_keys
from core.digest.rounds import (
    ROUNDS,
    DIGEST_SEGMENT_HARD_CAP,
    Cursor,
    RoundSpec,
    reset_result,
)
from core.digest.rounds import akin, attribute, close, group, record, understand
from core.digest.rounds.base import Ctx, RoundOut
from core.digest.segment import _segment_domain
from core.session.events import is_content_event
from core.session.maintenance import exclude_abandoned
from core.session.renderer import render_timeline
from llm.task_levels import extra_body as _tl_extra
from llm.task_levels import max_tokens as _tl_max_tokens

logger = logging.getLogger(__name__)

#: ⭐ **表里的 key → 那一步的实现** —— 顺序由 `ROUNDS` 说了算, 这里只管"谁是谁"。
#: ⚠️ **必须与 `ROUNDS` 一一对应**（多一个/少一个/写错 key, `test_digest_rounds.py` 当场红）。
IMPL: dict[str, Callable[[Ctx], RoundOut]] = {
    "record": record.run,
    "akin": akin.run,
    "close": close.run,
    "understand": understand.run,
    "attribute": attribute.run,
    "group": group.run,
}

#: ⭐ **一段最多试几次**（2026-09-29 刀 2）—— 数到就**放弃**这一段（见 `_note_failure`）。
#: ⚠️ 它**不是"同一个进程里连试三次"**: digest 没有主动重试, 次数由**触发点**累加
#: （MMT 每 25 轮 / bond 闭环）⇒ 最坏要等 75 轮才放弃。不改成立刻重试的理由:
#: 同一段、同一模型、同一预算, 连撞三次是白花钱, 还占着 `_digest_lock`。
DIGEST_MAX_ATTEMPTS = 3
#: 好感 delta clamp 边界（**带符号: 下界 2026-09-13 由 0 放开**）。
#: 语义 = "**单段**内的好感净变化"，不是总量——上界 100 防一段暴涨,
#: 下界 -100 对称防一段暴跌; 累计地板在 `Affection` 层（MIN_EXP=0）。
#: 放开下界的理由见 docs/DESIGN_WIKI_V3.md §3.3.3: 关系能变坏是玩法语义,
#: 且同频召回需要 `aff_at_encoding` 的符号。
DIGEST_AFF_MIN, DIGEST_AFF_MAX = -100, 100


@dataclass
class DigestResult:
    """一次 digest 的结果。

    ⚠️ 字段分两类（`core/digest/rounds/__init__.py` 是判据）: **某轮的产出**（失败时由
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
    #: ⭐ **R4 收口的 note 操作**（`add` / `close`）+ ⭐ **R1 的那句 `on_mind`**（N4a）
    #: —— ⚠️ **调用方在整批 `ok` 之后才 append**（§8: 失败 = 整批回滚 ⇒ 那条约定原样开着;
    #: 事件 append 不可撤销, 提前写就回不去了）。
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
    deadline_seconds: float = DIGEST_SEGMENT_HARD_CAP,
    llm_timeout: float | None = None,
    extra_body: dict | None = None,
    aff_at_encoding: float | None = None,
    emotion_lexicon: dict | None = None,
    write_ledger: Callable[[dict], None] | None = None,
) -> DigestResult:
    """增量 digest: 新事件 → 依次跑 `rounds.ROUNDS` 那几步 → 原子落盘 → 推进水位。

    ⚠️ 从前这段写着"两轮"—— 那是 Round A/B 时代的名字。今天每段是
    **5 次 LLM 调用 + 1 次零成本补边**（步序见 `core/digest/rounds/__init__.py`）。

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
                    自己的预算（`rounds` 表里那格 / 默认 `DIGEST_ROUND_BUDGET_SECONDS`），本轮的
                    截止 = `min(整段硬顶, 本轮开始 + 本轮预算)`。撞上 → 判失败回滚,
                    水位不推进可重算。默认 = `rounds.DIGEST_SEGMENT_HARD_CAP`。
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
        write_ledger: ⭐ **可选的账写入器**（`(row) -> None`）—— 给了它, 放弃一段时
                   **先记账、再推水位**（见 `_note_failure`）。**为什么要有它**:
                   本函数只有 `WikiStoreV2`, 拿不到事件流; 而"水位推了但账没写成"
                   = 那条事实**永久丢掉**（账不可重算）。给了它 ⇒ 写失败就**不推水位**,
                   下次触发重来一次记账（自愈）。None ⇒ 退回"把行交出去"
                   （`DigestResult.creep_rows`, 调用方自己写）。
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

    def _fail() -> DigestResult:
        """**失败的唯一出口** —— 回滚 + 记账（见 `_rollback`）。"""
        return _rollback(store, snapshot, result, from_seq=digest_from,
                         upto_seq=interact_max, write_ledger=write_ledger)

    # 这一段共享的一切（六轮各拿它干活）—— 建一次, 只读的部分全在这里。
    ctx = Ctx(
        store=store, llm=llm, result=result, cursor=Cursor(),
        model=model, temperature=temperature, max_tokens=max_tokens,
        llm_timeout=llm_timeout, extra_body=extra_body,
        hard_deadline=hard_deadline,
        events=events, new_all=new_all, domain=domain, chapters=chapters,
        timeline=timeline, seq_set=seq_set, by_seq=by_seq, visuals=visuals,
        emotion_scale=emotion_scale, character_prompt=character_prompt,
        interact_max=interact_max, now_ts=now_ts,
        embed_fn=embed_fn, aff_at_encoding=aff_at_encoding,
    )

    try:
        # ⭐ **顺序只由表说了算**（`rounds.ROUNDS`）—— 本循环不写任何一步的名字。
        for spec in ROUNDS:
            # 自吞那一步（表里 `own_snapshot`）: 编排**先替它取快照**, 失败时只回滚它。
            snap = store.clone_state() if spec.own_snapshot else None
            err0 = len(result.errors)
            out = IMPL[spec.key](ctx)
            if out.ok:                                   # 跑成 / 按表跳过
                continue
            if not out.swallow:
                return _fail()                           # 整段回滚 + 记账
            _swallow(store, spec, result, out, snap, err0)
    except ValueError as e:                              # store 层拒绝 → 回滚
        result.errors.append(str(e))
        return _fail()

    # ── 成功: 提交（节点落盘 + 水位推进）──
    result.ok = True
    result.created = ctx.episode_ids
    result.affection_delta = _clamp_aff((ctx.resp_b or {}).get("affection_exp_delta"))
    store.save()
    # 游标提交：**已退役**（2026-09-17）—— 没有剧情游标可落盘。
    store.meta["digested_seq"] = max((e.seq for e in events), default=interact_max)
    # ⭐ 成功 ⇒ **失败计数清零**（这一段过去了; 留着它会让下一段白背两次"前科"）。
    store.meta.pop("digest_retry", None)
    store.save_meta()
    return result


# ---------------------------------------------------------------------------
# 各轮的正文已搬走（2026-09-29 乙-1）：
#   `rounds/record.py` R1 · `rounds/akin.py` 补边 · `rounds/close.py` R4 ·
#   `rounds/understand.py` R2 · `rounds/attribute.py` R3 · `rounds/group.py` L2-a
# 本文件只剩编排与事务。料的公共件在 `material.py`, 一轮调用的四件套在 `call.py`。
# ⏸ `_clean_evidence()` **2026-09-29 删** —— 随 `evidence` 字段一起退役（零消费者）。
# 它当年清洗的是 `function/quote/confidence/note` 四键, 而全仓没有一个产品读者:
# 契约每段要它 ≤5 条 + `quote` 逐字引用时间线 ⇒ 纯白付。别把它加回来。
# ---------------------------------------------------------------------------


def _swallow(store: WikiStoreV2, spec: RoundSpec, result: DigestResult,
             out: RoundOut, snapshot: dict | None, err0: int) -> None:
    """执行"**这一步自己吞掉失败**"（只有表里 `own_snapshot=True` 的那一步允许）。

    做三件事（从前散在那一步调用体里的样板）: 回滚这一步 · 把它的 errors 挪进它自己的
    warnings 字段 · 打一行可 grep 的告警。R1–R4 的活照常提交。

    ⚠️ **两处对不上就当场炸**（不静默放行）:
      · 表里 `own_snapshot=False` 却申请自吞 —— 那等于偷偷把"整段回滚"降级;
      · `warnings_field` 不在这一步的 `result_fields` 里 —— 那条 warnings 就**不归表管**,
        下一次整批回滚不会清它（`reset_result` 按表推导）。
    """
    if not spec.own_snapshot:
        raise AssertionError(
            f"digest {spec.key!r} 申请自吞失败, 但表里 `own_snapshot=False` —— "
            "「谁能不连累整段」的真源是 core/digest/rounds/__init__.py 的 ROUNDS")
    if out.warnings_field not in spec.result_fields:
        raise AssertionError(
            f"digest {spec.key!r} 把 errors 挪进 {out.warnings_field!r}, 而表里写着 "
            f"result_fields={spec.result_fields} —— 那条 warnings 不归表管, "
            "整批回滚时不会被清（`reset_result` 按表推导）")
    if snapshot is not None:
        store.restore_state(snapshot)                    # 只回滚这一步
    moved = result.errors[err0:]
    del result.errors[err0:]                             # ⚠️ ok=True 不许带 errors
    getattr(result, out.warnings_field).extend(moved)
    logger.warning("digest_%s 失败（只回滚这一步, 本段照常提交）: %s",
                   spec.key, "; ".join(moved[-3:]) or "(无)")


def _as_int(v: Any, default: int) -> int:
    """宽松取整数（坏值 → `default`）—— ⚠️ 别用 `v or default` 代替:
    `0` 是**合法值**（起点水位就是 0），而 `0 or -1` 会得到 -1。"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _clamp_aff(raw: Any) -> int:
    try:
        return max(DIGEST_AFF_MIN, min(DIGEST_AFF_MAX, int(raw)))
    except (TypeError, ValueError):
        return 0


def _rollback(store: WikiStoreV2, snapshot: dict,
              result: DigestResult, *,
              from_seq: int = 0, upto_seq: int = 0,
              write_ledger: Callable[[dict], None] | None = None) -> DigestResult:
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
    * ⭐ **2026-09-29（乙-1）**: 每一步的正文搬进 `rounds/`, 本函数仍是**整段**的出口;
      "只回滚那一步"走 `_swallow`（表里 `own_snapshot` 的那一步专用）。
    """
    store.restore_state(snapshot)
    reset_result(result)
    if upto_seq:
        _note_failure(store, result, from_seq=from_seq, upto_seq=upto_seq,
                      write_ledger=write_ledger)
    return result


def _note_failure(store: WikiStoreV2, result: DigestResult, *,
                  from_seq: int, upto_seq: int,
                  write_ledger: Callable[[dict], None] | None = None) -> None:
    """这一段又失败了一次: **记数**; 数到上限就**放弃**, 并留一条 creep 账。

    三个判据（都不是随手定的）:

    1. **计数的键 = 起点水位**（不是"窗口"）: 失败期间水位不动 ⇒ 键稳定;
       而窗口会随着新对话变长 ⇒ 拿窗口当键就**永远到不了上限**（每次都是"新的一段"）。
    2. **放弃时水位推到"第一次失败那一窗的上界"**: 第 2、3 次之间新攒的内容
       **不能跟着一起丢**（所以 `upto_seq` 只在第一次冻结, 之后不更新）。
    3. **同进程不连试**: 次数由触发点累加（见 `DIGEST_MAX_ATTEMPTS`）。

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

    if attempts < DIGEST_MAX_ATTEMPTS:
        store.meta["digest_retry"] = {"from_seq": from_seq, "upto_seq": first_upto,
                                      "attempts": attempts}
        store.save_meta()
        logger.warning("digest 第 %d/%d 次失败（水位不推进, 下次整段重来）: %s",
                       attempts, DIGEST_MAX_ATTEMPTS,
                       " | ".join(result.errors[-2:]) or "(无错误信息)")
        return

    # ── 放弃这一段 ──
    row = creep_build(
        KIND_DIGEST_SKIP, at_seq=first_upto,
        evidence={"from_seq": from_seq, "to_seq": first_upto,
                  "attempts": attempts, "errors": list(result.errors)[-5:]})
    # ⭐ **先记账、再推水位**（给了 `write_ledger` 时）—— 判据: 水位是"这段处理过了"的
    # 声明, 而账是"它怎么没的"的唯一证据。反过来（先推水位）一旦记账失败, 那条事实
    # 就**永久丢了**（账不可重算）; 现在的顺序最坏只是"记了账但水位没动"——
    # 下次触发会重跑一遍, 而**重复的账看得见, 丢掉的账看不见**（后者才是不可接受的）。
    if write_ledger is not None:
        try:
            write_ledger(row)
        except Exception as e:                       # noqa: BLE001
            logger.warning("creep 账写入失败 ⇒ **水位不推进**（下次触发再试一次记账, "
                           "这段内容不会因此消失）: %s", e)
            return                                   # 计数留着（attempts 已满 ⇒ 下次直接再放弃）
    else:
        result.creep_rows.append(row)                # 老路径: 把行交出去, 调用方自己写
    store.meta["digested_seq"] = first_upto          # ⚠️ 水位推进: 这段不再重来
    store.meta.pop("digest_retry", None)
    store.save_meta()
    logger.warning("digest 放弃这一段: 水位 %d → %d（试了 %d 次, 没消化的内容"
                   "**再也不会有节点**）—— 已留一条 creep 账",
                   from_seq, first_upto, attempts)
