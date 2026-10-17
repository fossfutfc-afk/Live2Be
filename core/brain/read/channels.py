"""召回链路接口（V3-3 前置）—— **只声明形态, 不实现公式**（DESIGN_WIKI_V3 §3.9）。

## 为什么先写接口

> *"召回是最后的综合考虑, 先写接口, 等有了接口统一构造公式。"*

现有五条链路的**信号形态互不相同**，硬塞进一个 `score()` 会重演"散落的模块常量"那
个病（V3-0 之前 `recall.py` 的样子：阈值/权重写死在代码里、换模型即静默失效）。
所以先把"每条链路**能提供什么**"钉死，再谈怎么合。

## 五条链路

| 代号 | 链路 | 本模块的 kind | 状态 |
|---|---|---|---|
| **A** | 综合强度**行列式**（`SIG·TIME + emo_span·emo_int`） | `PRIOR` | 四格已落地（TIME 见下; 值域 **[0,2]**） |
| **B** | **情绪数组** RAG 相似度（键序列 embedding） | `SIMILARITY` | T15（真档暂无 `emo_shape` → 降级） |
| **C** | **地点**召回（两轴融合: 素材字面 × 叙事语义） | `GATE` | 2026-09-20（**也出分**, 见下） |
| **D** | **既视感**（`narration` 等 RAG 相似度） | `SIMILARITY` | 唯一在真档上出分的 |
| **E** | **无意识**（认知碎片 RAG）—— 扩展 | `SIMILARITY` | 未立项 |

**合成层已落**（2026-09-20）: `core/brain/read/compose.py` —— 四条道路
（剧情语义 D / 情绪 B / 正交矩阵 A / 地点 C）→ 最终分, 形状 = **参数可选的调和平均**
（`infra/fuse.py`, 与 C 链路的 `magic` 同一个函数）。见该模块的 docstring。

## 三条形态纪律（先定, 免得后面互相打架）

### 1. 链路分三类，不都返回"分数"

- **`SIMILARITY`**：query ↔ 候选的**关系量**（B/D/E）。**是 pairwise 的**，
  不能填进节点自己的标量格（§3.3.3 已论：`cos` 塞进单条记忆的格子量纲不成立）。
  合成层对它的处理 = **池内 min-max**（cos 的绝对值在本机模型/真档上不可分, 实测见
  `compose.py`; 与 §10 Q31 引的 AgentGal"各自 min-max 归一化, 全程无阈值"同口径）。
- **`PRIOR`**：候选**自己的属性**（A 的行列式）。**不依赖 query**。
  合成层**不归一它**（*"不必归一，这个矩阵携带的信息本身就比较重很合理"*）
  —— 所以它担当"强度轴", 而不是混进相关证据里。
- **`GATE`**：**过滤/分组**（C 的地点）。**2026-09-20 起它也出分**：C 的两轴融合
  （素材字面 × 叙事语义）产出 `magic ∈ (0,1]`, 既是**准入面**（一轴为零 ⇒ 不命中）
  又是**打分面**。所以合成层把 `GATE` 的 `raw` 当**证据**用（原样, 不再归一）。
  旧话"GATE 不是分数、产物是候选集合"**只对 2026-09-20 之前的 C 成立**。

### 2. 不给分数定死尺度，给**归一化声明**

不同链路的分数量纲天然不同（cos ∈ [−1,1]、行列式 ∈ [0, ~2]、地点是命中/不命中）。
所以每条链路声明自己的 `scale`，**由合成层统一归一**——而不是在链路里各自
"顺手"归一（那正是散落常量的来源）。

### 3. 位置参数携带**溯源**，不携带最终分

`ChannelHit` 只有 `node` + `raw`（本链路原始分）+ `rank`。
**最终分由合成层算**——链路不知道别的链路存在。

## TIME 已定（2026-09-17, `ESSAY_TIME_MODEL §10` 时间轴换代）

> 原「TIME 未设计」一节（*"我们根本就没有 time 设计呢"*）
> 已由时间轴换代结清。

```
age  = 今天 − date(node.ts)        （**整数, 单位 = 现实日**）
TIME = 0.5 ** (age / half_life_days)
```

- **时钟定了**：唯一日期轴 = **现实日期**（`ts`）。剧情日历（`story_time` / `sim_day`）
  **作废** —— 它是里程表冒充日期（ESSAY §2.5）。实现见 `core/worldtime/age.py`。
- **语义定了**：`half_life` 表达**新鲜度**（"最近发生的浮上来"），不是遗忘曲线。
- **`half_life_days` 数值待重标定**：量纲从"叙事日"换成"现实日"后衰减变慢，
  可能压不住旧记忆 → 注入体积上升。见 `TODO.md`「时间轴换代」。

**所以 `RecallContext.now` 设为必填且无默认值**——不是为了报错，
是为了**让任何一次把它当成"随便给个 now"的调用都显式可见**。

## 与既有 `recall.py` 的关系

`recall.py` 现有 3 通道（相似度 / 珍贵保底 / 随机摘段）+ 一跳扩展，是 **v2 的写路径
候选推荐**（`recommend_candidates` 有生产调用）。本模块是**读路径召回的新接口层**，
`recall.py` 的通道 1/2/3 **将来各是一个 `Channel`**（相似度 → B/D；珍贵保底 →
A 的退化形态；随机摘段 → 独立旁路，不是 query 驱动，故不进本协议）。

**本模块不替换 `recall.py`**——两者并存, 迁移在 V3-3。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from core.brain.nodes import BrainNode
from core.brain.read.context import RecallContext

#: 链路种类（决定合成层怎么用它, 见模块 docstring 的"三条形态纪律"）
KIND_PRIOR = "prior"            # 候选自身属性, 不依赖 query
KIND_SIMILARITY = "similarity"  # query ↔ 候选的关系量（pairwise）
KIND_GATE = "gate"              # 过滤/分组, 不是分数
KINDS = (KIND_PRIOR, KIND_SIMILARITY, KIND_GATE)

# 尺度常量与 `RecallContext` 都住中性件（新旧两条读路径共用）:
#   `scale.py`   —— `SCALE_*` / `SCALES` 与 `cosine` / `pool_minmax`
#   `context.py` —— 输入契约（`now` 必填无默认值: 不许模块偷偷读壁钟）


@dataclass
class ChannelHit:
    """一条链路对一条候选的命中。

    `raw` 是**本链路的原始分, 不归一**——归一由合成层做（尺度见 `Channel.scale`）。
    `raw=None` = 链路认为该候选"不适用"（如 A 在 TIME 未定时的降级）,
    **与 `raw=0.0` 语义不同**（0.0 是"算了, 就是 0 分"）。
    """

    node: BrainNode
    raw: float | None = None
    rank: int = 0                    # 本链路内的名次（1 起; 0 = 未参与排序）
    detail: dict = field(default_factory=dict)   # 台账用: 为什么给这个分

    @property
    def degraded(self) -> bool:
        """该命中是否来自降级路径（无 raw 分）。"""
        return self.raw is None


@dataclass
class ChannelResult:
    """一条链路的完整产出（含台账所需的元信息）。"""

    channel: str                     # 链路名（见 CHANNELS 的 name）
    kind: str                        # KIND_*
    #: 本链路声明的尺度（`SCALE_*`）——**2026-09-20 补**: 此前只有 `Channel`
    #: 类属性上有 `scale`, **结果对象不携带** → 合成层拿到 `ChannelResult` 却不知道
    #: 怎么归一（写 `compose.py` 时撞上的真缺口）。链路 `gather` 时把它填进来。
    scale: str = ""
    hits: list[ChannelHit] = field(default_factory=list)
    #: 本链路这次是否走了降级（无 embed_fn / TIME 未定 / 无数据…）
    degraded: bool = False
    #: 降级/异常原因（单行, 可 grep）
    note: str = ""
    #: 本次链路内部用掉的旋钮快照（可观测性: 同一次召回可复现）
    knobs: dict = field(default_factory=dict)


@runtime_checkable
class Channel(Protocol):
    """召回链路 —— **只读 store, 不改任何状态**。

    实现者必须声明四个类属性（合成层靠它们决定怎么用这条链路）:
        name  : 稳定短名（台账/配置键用）
        kind  : KIND_*
        scale : SCALE_*
        unit  : 该链路自己的计量单位（人读, 如 "cos" / "det" / "place_hit"）

    `gather` 的契约:
        - **纯函数式**: 同一 (store, ctx) 必得同一结果（除显式随机旁路）
        - **不归一**: 返回原始分
        - **不排序截断**: 返回全部命中, 由合成层统一排序取 top-k
          （V3-3 的"无阈值、取 top-k"口径——见 §10.1 Q31）
        - 失败**不抛**: 降级为 `ChannelResult(degraded=True, note=...)`
    """

    name: str
    kind: str
    scale: str
    unit: str

    def gather(self, store, ctx: RecallContext) -> ChannelResult:
        """→ 本链路对当前 query 的全部命中。"""
        ...


#: 链路清单（**唯一注册点**）—— 新增链路只在这里加一行, 合成层零改动
CHANNELS: tuple[str, ...] = ("A_intensity", "B_emotion_rag",
                             "C_place", "D_deja_vu", "E_unconscious")

#: 尚未实现的链路（显式列出来, 免得"以为它没接上"）
PLANNED: dict[str, str] = {
    "E_unconscious": "认知碎片 RAG（用户扩展项, 未立项; 素材来源 = §6.4 的 percepts）",
}


def describe() -> list[dict]:
    """链路清单的形态说明（台账/文档生成用; 不触发任何召回）。"""
    from core.brain.read.channel_impl import build_channels
    out: list[dict] = []
    for ch in build_channels():
        out.append({
            "name": ch.name, "kind": ch.kind, "scale": ch.scale, "unit": ch.unit,
            "status": "planned" if ch.name in PLANNED else "implemented",
        })
    return out


def get(name: str):
    """按名取链路实例（未知名 → KeyError, 防拼错静默走空）。"""
    from core.brain.read.channel_impl import build_channels
    for ch in build_channels():
        if ch.name == name:
            return ch
    raise KeyError(f"未知召回链路: {name!r}（可用: {list(CHANNELS)}）")
