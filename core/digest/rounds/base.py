"""base.py — 每一轮的**公共载体**（2026-09-29 拆包乙-1 从 `pipeline.py` 分出）。

只有两样东西:

| 名字 | 是什么 |
|---|---|
| `Ctx` | **段级上下文**: 编排放进来的只读料 + 跨轮可变的那四样 + 六个薄转发方法 |
| `RoundOut` | **一轮跑完的交代**: 成没成 / 是不是跳过 / 挂了要不要连累整段 |

⚠️ **为什么是 `Ctx` 而不是继承**（`core/brain/DESIGN_GRAPH_V4.md §10` 已否决父子类, 本仓
也没有类型检查）: 六轮形状根本不统一 —— `akin` 不调 LLM、`group` 双执行器 + 失败自吞、
`settle` 两套本地号。继承会逼出一个"什么都有"的基类; 而 `Ctx` 只是**同一个段**这件
事实的载体 —— 谁读哪几段料仍由 `rounds.ROUNDS` 的 `material` 格说了算。

⚠️ **跨轮状态只有三样**（`episode_ids` / `r2_created` / `resp_a`）——
想加第四样之前先问一句: 它真是"跨轮的产物", 还是"某一轮自己的中间量"?
后者该留在那个轮的 `run()` 里（`record.py` 里那几个 `_no_pos` / `reused` 就是这么留的 ——
它们都是 R1 自己的手, 下一轮谁也不需要）。
⏸ 原来的第四样 `player_ids`（R1 建的玩家画像 id）**2026-10-14 随 `profile` 删** ——
它的唯一用途是让 R2/R3 的认知列表排除本段刚建的画像, 而那个 kind 已经不存在。

⚠️ **六个方法全是薄转发**（`call.py` / `material.py` 的实现）—— 这里不长业务:
料怎么拼在 `material.py`、这一轮怎么发在 `call.py`、写什么在轮次表。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.digest.call import _log_skip, _parse_for, _round_call, _system_for
from core.digest.material import _sections_for
from core.digest.rounds import Cursor, RoundSpec

if TYPE_CHECKING:                       # 仅注解求值期（避免与编排层循环 import）
    from core.brain.read.recall import EmbedFn
    from core.brain.store import WikiStoreV2
    from core.digest.pipeline import DigestResult


@dataclass
class Ctx:
    """这一段共享的一切 —— 编排建一次, 六轮各拿它干活。"""

    # ── 引擎四件 ──
    store: WikiStoreV2
    llm: Any
    result: DigestResult
    cursor: Cursor

    # ── 模型参数六件（六轮同一套; 每轮调用只差 system / user / parse）──
    model: str | None
    temperature: float
    max_tokens: int
    llm_timeout: float | None
    extra_body: dict | None
    hard_deadline: float

    # ── 本段的料（编排算好一次; 谁能读哪几段 = 表里的 `material` 格）──
    events: list
    """**全量**事件流（含 marker 与账目）—— R4 的 `notes_state` 要它。"""
    new_all: list
    """水位之后的**全部**事件（含 marker/账目）—— `akin` 的 `noticed` 账要它。"""
    domain: str
    """段类型 `bond` / `mmt` —— 从 marker 派生（`segment._segment_domain`）。"""
    chapters: list[dict]
    """窗口里的**每一章**（一章一块）—— R1 的章标题料 + 一章一条收口。"""
    timeline: str
    seq_set: set[int]
    by_seq: dict
    visuals: list[str]
    emotion_scale: str
    character_prompt: str
    interact_max: int
    """本段内容事件的**上界 seq** —— 段级 `event_seq` / 节点 `ts` 的兜底坐标。"""
    now_ts: str
    """段的日期 = **段内最后一条内容事件**的时刻（不是"写库时刻"）。"""

    embed_fn: EmbedFn | None = None
    aff_at_encoding: float | None = None

    # ── 跨轮产物（⭐ 只有这三样）──
    episode_ids: list[str] = field(default_factory=list)
    """R1 建的 episode id —— R2 的覆盖检查 / R3 的归属都要它。"""
    r2_created: list[str] = field(default_factory=list)
    """R2 新建的 belief id —— R3 要挂的就是"本轮全部新节点"。"""
    resp_a: dict | None = None
    """⭐ **R1 的原始 resp** —— 成功路径的 `affection_exp_delta` 在 `try` 之外取用它
    （最容易漏的一条跨轮依赖: 返回值只带"解析出的行"就取不到了）。

    ⭐ **2026-10-05（M1）从 R2 搬来**: 好感是"**这一段**她对老师的亲近感净变化",
    与 `significance` 同族（都是打分）—— 而打分归 R1（它手里还有情绪标尺）;
    R2 从此只剩图操作。⇒ 那条"最易漏的跨轮依赖"**没有消失, 只是换了持有人**
    （所以它仍留在这一格里, 别顺手删）。"""

    # ── 六个薄转发（见模块 docstring）──

    def enter(self, key: str) -> RoundSpec:
        """进这一轮 —— **越序当场炸**（顺序的真源是 `rounds.ROUNDS`）。"""
        return self.cursor.enter(key)

    def system_for(self, spec: RoundSpec, **schema_kw) -> str:
        """这一轮的 system = prompt 文件 + 该轮的产出契约（`call._system_for`）。"""
        return _system_for(spec, **schema_kw)

    def parse_for(self, spec: RoundSpec, **ctx) -> Callable[[dict], tuple[Any, Any]]:
        """把表里那个 parse 绑上**这一轮**的上下文（`call._parse_for`）。"""
        return _parse_for(spec, **ctx)

    def sections_for(self, spec: RoundSpec, sections: list[tuple[str, str]]) -> str:
        """按表**逐字校对**料的段标题再拼装（`material._sections_for`）—— 对不上当场炸。"""
        return _sections_for(spec, sections)

    def log_skip(self, spec: RoundSpec) -> None:
        """跳过这一轮 —— 那句日志的文案来自表里的 `skip` 格。"""
        _log_skip(spec)

    def call(self, spec: RoundSpec, system: str, user: str, *,
             parse_fn: Callable[[dict], tuple[Any, Any]]
             ) -> tuple[Any | None, dict | None]:
        """发这一轮 —— 模型参数从这里取, 每轮不再各写一遍那八个 kwargs。

        ⚠️ **本轮截止在 `call.py` 里折算**（`min(整段硬顶, 现在 + 本轮预算)`）——
        所以这里传的是**整段硬顶**（`hard_deadline`）, 不是折算过的那个。
        """
        return _round_call(self.llm, system, user, spec=spec, model=self.model,
                           temperature=self.temperature, max_tokens=self.max_tokens,
                           llm_timeout=self.llm_timeout, extra_body=self.extra_body,
                           hard_deadline=self.hard_deadline, parse_fn=parse_fn,
                           result=self.result)


@dataclass
class RoundOut:
    """一轮跑完的交代 —— 编排只要三件事（**多一件就是第二个真相**）。

    ⚠️ 为什么**不带** `rows` / `resp`: 各轮解析出来的行都在**各自文件里当场消费掉**
    （建节点 / `apply_decisions` / `apply_entities` / `apply_groups`）, 外面**零读者**;
    R1 那份原始 `resp` 有唯一读者（成功路径的 `affection_exp_delta`）而它走
    `Ctx.resp_a` —— 返回值里再带一份就是同一个事实的两条通道。

    ⚠️ 为什么**不用 `None` 表示失败**: 失败还要说"要不要连累整段"（`swallow`）与
    "errors 挪去哪"（`warnings_field`）—— 一个 `None` 说不出这两件事。
    """

    ok: bool = False
    """True = 这一轮跑成了（`skip=True` 也算跑成: 它是**按表跳过**, 不是失败）。"""
    skip: bool = False
    """True = 条件不满足, 这一轮没跑（日志文案来自表里的 `skip` 格）。"""
    swallow: bool = False
    """True = 我挂了, 但**别连累整段** —— 只允许表里 `own_snapshot=True` 的那一步
    （编排会为此当场核对, 不符即炸）。"""
    warnings_field: str = ""
    """`swallow` 时: 这一轮的 `errors` 挪进 `DigestResult` 的哪个字段 —— 由**这一轮**
    说（编排不去猜），且必须是表里 `result_fields` 声明过的字段（编排当场核对）。"""

    @classmethod
    def done(cls) -> RoundOut:
        """跑成了。"""
        return cls(ok=True)

    @classmethod
    def skipped(cls) -> RoundOut:
        """按表跳过 —— 不是失败。"""
        return cls(ok=True, skip=True)

    @classmethod
    def failed(cls) -> RoundOut:
        """挂了 ⇒ **整段回滚**（默认; 要自吞就得明说）。"""
        return cls()

    @classmethod
    def swallowed(cls, field: str) -> RoundOut:
        """挂了, 但只回滚自己（`field` = errors 挪去哪）—— 只有分群走这条。"""
        return cls(swallow=True, warnings_field=field)
