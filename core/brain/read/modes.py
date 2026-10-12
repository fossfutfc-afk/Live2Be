# -*- coding: utf-8 -*-
"""modes — 召回的**形式表** + **唯一对外前门**（2026-10-12, 用户裁"先把这个 API 接好"）。

## 一句话

一次召回 = 一种**形式**（"她为什么想起这件事"）。形式决定四件事：
**走哪个执行器 · 问哪个面 · 怎么排 · 她看到的那段字的抬头**。

## 两种形状（`Mode.shape`）—— ⛔ 两套判据**不许**混成一个分

| shape | 执行器 | 判据 | 输出 |
|---|---|---|---|
| `rank` | `like.like(spec=…)` | 六路打分 → 池内归一 → **证据轴至少一路命中** → 加权排序 | 最像的 ≤ k 条 |
| `set`  | `find.find(anchors=…)` | **确定的**判据（名字命中 / 时间区间 / 图上相邻）—— 与"像不像"无关 | 命中的**全部**（新→旧；裁不裁归渲染的预算） |

⭐ **为什么不混分**（2026-10-12 讨论的结论，用户: *"我总觉得这个加权很古怪"*）：
加权和只在 `rank` 形状**内部**成立 —— 六路量纲根本不齐（覆盖率 / **池内相对** cos /
0-1 命中 / 年龄 / 显著度），塞进一个平均之后**分数不再是这条记忆的属性**：
池里换一条别的事，它的分就变了。而"关于某人的全部"压根不是排序问题
（`find` 的不变量：**不漏即正确**）。
⇒ 形式之间**不竞争名额**、不互相平均；真要出一个总序就混**名次**（RRF），永远不混分数。

## 加一个形式 = **表里加一行**（⛔ 别在执行器里写 `if mode == "name"`）

判据同 `PARTS` / `SPECS` / `ROUNDS`：加一行不改执行器 ⇒ 台账 / 守门 / 规则书都只认表。
⚠️ **故意没加的两格**：`admit`（准入）与 `cap`（截断）—— 今天每种形状**只有一种**准入
规则（rank = 证据轴命中；set = 命中即准入），`cap` 归渲染层的预算管。
加要等真有第二种规则，否则就是"配了没人读"的**假旋钮**（`test_no_threshold_knobs_left`
那条纪律的同款）。
⭐ 相比之下 `skip_ids` **加了** —— 它不是旋钮而是**一行形式的固有属性**（"谁的叫法能触发
这一段"），而且**真的有第二种取值**（`turn` 行用它不到, `name` 行必须用）。

## 今天表里有什么

| mode | 形状 | 干什么 | 谁在用 |
|---|---|---|---|
| `name` | set | 「关于他们的」——老师这句**提到了一个名字** ⇒ 那个对象**车道上全部**（`about` 入边） | `engine._recall_notes`（P19 的第一段） |
| `turn` | rank | 「你想起的事」——每轮的兜底形式（六路，权重在 `like.SPECS["turn"]`） | `engine._recall_notes`（P19 的第二段） |

⭐ **P19 两段都从这张表出**（顺序 = `engine._recall_notes` 里的注入顺序: 先确定命中, 后模糊）。
⚠️ **`name` 不许被保留号触发**（`RESERVED_TRIGGERS`）—— 见那一行的注释。

⏭ 下一批形式（`when` 时间窗 / `echo` 既视感 / `mood` 情绪 / `near` 图上相邻）——
**落一个加一行**；没接线的**不许先写进表**（空行 = 假承诺）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.brain.entities import SELF_ID, SENSEI_ID
from core.brain.read.find import ANCHORS, _order as _newest_key, find
from core.brain.read.like import SPECS, RecallCtx, build_ctx, like
from core.brain.read.pack import Candidate
from core.brain.read.render import (RECALL_ACTION_HINT, RECALL_HEADER,
                                    render_candidates)

#: 形状 —— 两种执行器（见模块 docstring 的对照表）
SHAPE_RANK = "rank"
SHAPE_SET = "set"
SHAPES: tuple[str, ...] = (SHAPE_RANK, SHAPE_SET)

#: `payload_from` 的**闭集** —— `set` 型的锚载荷从 `RecallCtx` 的哪份**派生料**取
#: （`named` = `{entity_id: 她在 query 里被叫到的那个写法}`, 由 `like.build_ctx` 算）
PAYLOAD_NAMED = "named"

#: `set` 型的载荷里**不许触发**的保留号（真源 = `core.brain.entities` 的 `SELF_ID`/`SENSEI_ID`）。
#: ⛔ **她自己（`x0000`）与老师（`x0001`）的名字不算"提到了谁"**:
#: 那两条车道 ≈ **全部事件**（哪一件事不连着老师、不连着她自己?）—— 一提到就糊一整面,
#: 而且抬头写着"关于他们的", 摆出来却是一整条河。它们各自的分身**另有住处**
#: （她自己 → brain 段的「我是这样看自己的」; 老师 → 「老师的事」/ 河本身）。
RESERVED_TRIGGERS: tuple[str, ...] = (SELF_ID, SENSEI_ID)
PAYLOADS: tuple[str, ...] = (PAYLOAD_NAMED,)


@dataclass(frozen=True)
class Mode:
    """一种召回形式（表里的一行）。⚠️ 字段少是**故意的** —— 见模块 docstring 末条。"""

    #: `rank` | `set`
    shape: str = SHAPE_RANK
    #: `rank` 型：`like.SPECS` 的键（⭐ **权重住在那一行**, 不在这儿抄第二份）
    spec: str = ""
    #: `set` 型：`find.ANCHORS` 的键（判据确定 ⇒ 命中的全要）
    anchors: tuple[str, ...] = ()
    #: `set` 型：锚载荷从哪份派生料来（闭集 = `PAYLOADS`）
    payload_from: str = ""
    #: `set` 型：载荷里**不许触发**的 id（保留号 —— 见 `RESERVED_TRIGGERS`）
    skip_ids: tuple[str, ...] = ()
    #: 选面（`set` 型传给 `find`; `rank` 型的选面在 `SPECS[…].kinds`）
    kinds: tuple[str, ...] = ("episode",)
    #: `set` 型的排序：`newest`（口径 = `find._order`, 同一条规则不抄第二份）
    #: ⚠️ **`rank` 型留空**：排序是 `like` 的事（它有归一与加权，不该在这儿再排一次）
    order: str = "newest"
    #: 她看到的那一段的**抬头** / **尾注**（`render_section` 用；空 = 该形式不摆字）
    header: str = ""
    hint: str = ""


#: ⭐ **形式表**（唯一注册点）—— 加形式 = 加一行
MODES: dict[str, Mode] = {
    # 「关于他们的」：老师这句点到了某个名字 ⇒ 他**车道上全部**（含正文没写他名字的那些）
    # ⚠️ 保留号不许触发（`skip_ids`）—— 她自己/老师的车道≈全部事件, 见 `RESERVED_TRIGGERS`。
    "name": Mode(shape=SHAPE_SET, anchors=("entity",), payload_from=PAYLOAD_NAMED,
                 skip_ids=RESERVED_TRIGGERS,
                 header="【关于他们的（老师这句话里提到了一个名字——下面是你记得的、"
                        "跟那个名字有关的事，用不用由你判断）】"),
    # P19「你想起的事」：每轮的兜底形式 —— 六路打分（权重与选面都在 `like.SPECS`）
    "turn": Mode(shape=SHAPE_RANK, spec="turn", order="",
                 header=RECALL_HEADER, hint=RECALL_ACTION_HINT),
}

#: 缺省形式（P19 那条；⛔ 与"什么都不知道"区分开: 缺省 ≠ 空）
DEFAULT_MODE = "turn"


def mode_of(name: Any) -> Mode:
    """取一行形式（未知 ⇒ **KeyError**, ⛔ 不静默回落缺省 —— 拼错要当场看得见）。"""
    key = str(name or "").strip()
    m = MODES.get(key)
    if m is None:
        raise KeyError(f"未知的召回形式: {name!r}（可用: {sorted(MODES)}）")
    return m


def _payloads(base: RecallCtx, m: Mode) -> list[Any]:
    """`set` 型的锚载荷清单（可能 0 个 / 多个 —— 多个 = 并集）。

    ⚠️ 今天**所有锚共用同一个载荷**（`name` 只有 `entity` 一个锚）。
    要用"不同锚各自载荷"的形式 ⇒ 表里加一格（⛔ 别在这儿猜）。

    ⭐ 载荷一律**去掉 `Mode.skip_ids`**（保留号 —— 见 `RESERVED_TRIGGERS`）:
    这条只对"载荷是 entity id"的那份派生料有意义, 所以写在**这里**而不是 `recall()` 里
    （`when` / `near` 那类载荷不是 id, 不该被这条例外碰到）。
    """
    if m.payload_from == PAYLOAD_NAMED:
        skip = set(m.skip_ids)
        return [eid for eid in base.named if eid not in skip]
    raise KeyError(f"形式 {m.spec or m.anchors} 的 payload_from={m.payload_from!r} "
                   f"不在闭集里（可用: {PAYLOADS}）")


def recall(store, ctx: RecallCtx, *, mode: Any = DEFAULT_MODE,
           k: int | None = None, weights: dict[str, float] | None = None,
           ) -> list[Candidate]:
    """⭐ **唯一对外前门**：一次召回 = 一种**形式**（`mode`，见 `MODES`）。

    Args:
        store: `WikiStoreV2`（**只读**）。
        ctx: 输入契约（`RecallCtx`, 与 `like` 同款; `now` 必填）。
        mode: 形式名（`MODES` 的键）。⚠️ 未知名 ⇒ `KeyError`。
        k / weights: **只有 `rank` 型认识**（`like` 的两个旋钮）。给 `set` 型传 ⇒
            `ValueError`（⛔ 不静默忽略 —— 那是"以为设了却没生效"）。

    Returns:
        `pack.Candidate` 列表 —— **两种形状同一个返回类型**：
        · `rank` 型 ≤ k 条（降序, 见 `like`）；
        · `set` 型 = 命中的**全部**（新→旧；**不裁** —— 摆几条由 `render_candidates`
          的 `cap` / `budget` 管, 那是"她眼前有多长"的事, 不是"存不存在"的事）。
    """
    m = mode_of(mode)
    if m.shape == SHAPE_RANK:
        return like(store, ctx, spec=m.spec, k=k, weights=weights)
    if m.shape != SHAPE_SET:                       # 表写歪了 ⇒ 当场炸（不静默）
        raise KeyError(f"形式 {mode!r} 的 shape={m.shape!r} 不在 {SHAPES}")
    if k is not None or weights is not None:
        raise ValueError(f"形式 {mode!r} 是 set 形状（确定判据）——"
                         f"没有 k / weights 这两个旋钮")
    base = build_ctx(store, ctx, active=[])        # 只要派生料里的名字表（零额外成本）
    out: list[Candidate] = []
    seen: set[str] = set()
    for value in _payloads(base, m):
        for cand in find(store, {name: value for name in m.anchors}, kinds=m.kinds):
            if cand.node.id not in seen:
                seen.add(cand.node.id)
                out.append(cand)
    _sort_set(out, m)                              # 多锚并集 ⇒ 按 `find` 的同一口径重排
    return out


def _sort_set(cands: list[Candidate], m: Mode) -> None:
    """`set` 型的排序（口径 = `find._order` —— **同一条规则, 不抄第二份**）。"""
    if m.order == "newest":
        cands.sort(key=lambda c: _newest_key(c.node))
    elif m.order:
        raise KeyError(f"形式 {m.spec or m.anchors} 的 order={m.order!r} 不认识"
                       f"（`set` 型只有 'newest'）")


def render_section(cands: Iterable[Candidate], *, mode: Any = DEFAULT_MODE,
                   **kwargs) -> str:
    """⭐ **形式 → 她看到的那一段字**：抬头/尾注从表里取, 其余**原样透传**。

    = `render.render_candidates` 的一层薄壳（⛔ 这里不印字、不筛面、不截断 ——
    那些都在渲染层; 本函数只负责"用这个形式的文案"）。
    """
    m = mode_of(mode)
    return render_candidates(cands, header=m.header, hint=m.hint, **kwargs)


def describe() -> list[tuple[str, str, str]]:
    """台账/文档用的形式清单: `[(mode, shape, 判据说明), …]`（不触发任何召回）。"""
    out: list[tuple[str, str, str]] = []
    for name, m in MODES.items():
        if m.shape == SHAPE_RANK:
            spec = SPECS.get(m.spec)
            parts = ", ".join(f"{p}:{w:g}" for p, w in (spec.parts if spec else ()))
            out.append((name, m.shape, f"like(spec={m.spec!r}) kinds={spec.kinds if spec else '?'}"
                                       f" parts={parts}"))
        else:
            skip = f" skip={list(m.skip_ids)}" if m.skip_ids else ""
            out.append((name, m.shape,
                        f"find({list(m.anchors)} ⊆ {sorted(ANCHORS)}) "
                        f"payload={m.payload_from} kinds={m.kinds} order={m.order}{skip}"))
    return out
