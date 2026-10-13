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
| `name` | set | 「你想着「阿露」——浮上来的是这些」= 老师这句**提到了一个名字** ⇒ 那个对象**车道上全部**（`about` 入边） | `engine._recall_notes`（P19 第一段） |
| `turn` | rank | 「你想起的事」——每轮的兜底形式（六路，权重在 `like.SPECS["turn"]`） | `engine._recall_notes`（P19 第二段） |

⭐ **P19 两段都从这张表出**（顺序 = `engine._recall_notes` 里的注入顺序: 先确定命中, 后模糊）。
⚠️ **`name` 不许被保留号触发**（`RESERVED_TRIGGERS`）—— 见那一行的注释。

## ⭐ 钥匙与空手（2026-10-12, 用户: *"这是你在思索（词语）的时候回忆起来的事情"*）

- **钥匙** = 这次触发召回的那个**词**（`recall_with_keys()` 的第二项；`{key}` 槽）——
  段头把它印出来，"一个词 → 一批记忆"才在她眼前成立（`look` 的语义, 顺带演示）。
- **空手**（`Mode.empty`）= 钥匙扫到了、一条也没命中时**印一句话**而不是沉默 ——
  沉默有歧义（"没查" vs "查了没有"）, 而"想了一下没想起来"是她**能拿来说话的事实**。
  ⛔ 没有钥匙就不印（闲聊不摆）；⛔ 措辞不许"一片空白"（她的 system 里就有整条河）。

⏭ 下一批形式（`when` 时间窗 / `echo` 既视感 / `mood` 情绪 / `near` 图上相邻）——
**落一个加一行**；没接线的**不许先写进表**（空行 = 假承诺）。
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from contract.slots import render_template
from core.brain.entities import SELF_ID, SENSEI_ID
from core.brain.read.find import ANCHORS, find
from core.brain.read.find import _order as _newest_key
from core.brain.read.like import SPECS, RecallCtx, build_ctx, like
from core.brain.read.pack import Candidate
from core.brain.read.render import RECALL_ACTION_HINT, RECALL_HEADER, render_candidates

#: 形状 —— 两种执行器（见模块 docstring 的对照表）
SHAPE_RANK = "rank"
SHAPE_SET = "set"
SHAPES: tuple[str, ...] = (SHAPE_RANK, SHAPE_SET)

#: `payload_from` 的**闭集** —— `set` 型的锚载荷从 `RecallCtx` 的哪份**派生料**取：
#: · `named` = `{entity_id: 她在 query 里被叫到的那个写法}`（由 `like.build_ctx` 算）
#: · `when` = **在 query 里扫到的时间窗**（`(词, (start, end))`, 由 `when.scan_when` 扫）
PAYLOAD_NAMED = "named"
PAYLOAD_WHEN = "when"

#: `set` 型的载荷里**不许触发**的保留号（真源 = `core.brain.entities` 的 `SELF_ID`/`SENSEI_ID`）。
#: ⛔ **她自己（`x0000`）与老师（`x0001`）的名字不算"提到了谁"**:
#: 那两条车道 ≈ **全部事件**（哪一件事不连着老师、不连着她自己?）—— 一提到就糊一整面,
#: 而且抬头写着"你想着某个人", 摆出来却是一整条河。它们各自的分身**另有住处**
#: （她自己 → brain 段那张表里**她那一行**, 表尾; 老师 → 「老师的事」/ 河本身）。
RESERVED_TRIGGERS: tuple[str, ...] = (SELF_ID, SENSEI_ID)
PAYLOADS: tuple[str, ...] = (PAYLOAD_NAMED, PAYLOAD_WHEN)


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
    #: 她看到的那一段的**抬头** / **尾注**（`render_section` 用；空 = 该形式不摆字）。
    #: ⭐ 两者都可以带**一个 `{key}` 槽** —— 填的是"这次用的那把钥匙"（老师用的那个写法 /
    #: 扫到的那段时间的原话）。`set` 型的抬头**应该**带它: "一个词 → 一批记忆"要印在她眼前。
    #: ⛔ 带槽而没算出钥匙 ⇒ **当场炸**（见 `_fill`）——不许把 `{key}` 四个字符印给她看。
    header: str = ""
    hint: str = ""
    #: ⭐ **钥匙扫到了、但那批候选一条都没有**时印的那句话（`{key}` 槽；空 = 什么都不印）。
    #: ⚠️ 与 `hint` 分工: `hint` 是"**有货**时的尾注", 这一格是"**空手**时的正文"。
    #: 为什么空手也要说话（2026-10-12 用户）: 沉默**有歧义** —— LLM 分不清"引擎没查"与
    #: "查了、没有"; 而"想了一下没想起来"是她**可以拿来说话的事实**（同 `look` 的三档空手）。
    #: ⚠️ ⛔ 措辞两条纪律（写这一格时别犯）:
    #:   · **限定在这把钥匙上** —— ⛔ 不许写"一片空白/什么都想不起来": 她的 system 里就摆着
    #:     「我记得的事」整条河, 同一份上下文里自相矛盾, 还会诱发她答得出来也说想不起来;
    #:   · **瞬时**（"一时"/"这一下"）—— ⛔ 不写"良久/努力思索"那种**时间**词, 那会诱使她演
    #:     "唔……我想想……"那段戏。
    empty: str = ""


#: ⭐ **形式表**（唯一注册点）—— 加形式 = 加一行
MODES: dict[str, Mode] = {
    # 「你想着「X」」：老师这句点到了某个名字 ⇒ 他**车道上全部**（含正文没写他名字的那些）
    # ⚠️ 保留号不许触发（`skip_ids`）—— 她自己/老师的车道≈全部事件, 见 `RESERVED_TRIGGERS`。
    "name": Mode(shape=SHAPE_SET, anchors=("entity",), payload_from=PAYLOAD_NAMED,
                 skip_ids=RESERVED_TRIGGERS,
                 # ⭐ 抬头 = "这是**你想着那个词**的时候浮上来的"（不是"引擎给你一段资料"）——
                 # 顺带把 `look` 的语义（一个词 → 一批记忆）在她眼前演示一遍。
                 header="【你想着「{{key}}」——浮上来的是这些（用不用由你判断）】",
                 empty="【你想着「{{key}}」——跟它有关的事，一时没想起来】"),
    # 「你想着「上周」那阵子」：老师这句里有**时间词** ⇒ 那段时间里**全部** episode。
    # ⚠️ **只查 `exact`, 不放宽**（用户 2026-10-12: *"可以让 LLM 干脆自己多开区间搜"*）——
    # `When.wide` 是 `look` 的第二跳（那里会如实报告"那阵子没有；前后那阵子…"）,
    # 而 P19 是**引擎主动摆**: 放宽 = 替她猜, 她会把"前后几天"的事当成"那阵子"的说出口。
    # 时间矫正那条路 = 她自己多翻几次 `look`（`MAX_STEPS` 内随便翻）。
    "when": Mode(shape=SHAPE_SET, anchors=("when",), payload_from=PAYLOAD_WHEN,
                 header="【你想着「{{key}}」那阵子——浮上来的是这些（用不用由你判断）】",
                 empty="【你想着「{{key}}」那阵子——那几天的事，一时没想起来】"),
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


def _scan(base: RecallCtx) -> tuple[str, Any] | None:
    """在**老师这一句**里扫到的时间窗: `(那个词, (start, end))`; 扫不到 ⇒ `None`。

    ⭐ **解析整份借用** `worldtime.when.scan_when`（词表 = `when._PHRASES` 本身）——
    ⛔ 这里不写第二份短语表, 也不碰 `_AGO`/`_RECENT` 那条参数化路线（见它的 docstring）。
    ⚠️ `scan_when` 已经把"未过完的窗口"（今天/本周/本月/今年）挡掉了 —— 那些不是"旧事"。
    """
    from core.worldtime.when import scan_when  # 函数内: 只有这一条载荷要 worldtime
    got = scan_when(base.query, now=base.now)
    return (got[0], got[1].exact) if got else None


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
    if m.payload_from == PAYLOAD_WHEN:
        got = _scan(base)
        return [got[1]] if got else []
    raise KeyError(f"形式 {m.spec or m.anchors} 的 payload_from={m.payload_from!r} "
                   f"不在闭集里（可用: {PAYLOADS}）")


def _keys(base: RecallCtx, m: Mode) -> list[str]:
    """载荷的**人话形式** —— 段头要印的那把**钥匙**（「你想着「阿露」…」）。

    ⚠️ 与 `_payloads` **同派生料、同一套规则**（直接调它）—— ⛔ 别在这儿重算一遍,
    更不许把 id 印出去（编号永不进她的视图）。
    """
    if m.payload_from == PAYLOAD_NAMED:
        return [base.named[eid] for eid in _payloads(base, m) if eid in base.named]
    if m.payload_from == PAYLOAD_WHEN:
        got = _scan(base)
        return [got[0]] if got else []
    raise KeyError(f"形式 {m.spec or m.anchors} 的 payload_from={m.payload_from!r} "
                   f"还没有对应的「人话形式」（见 `_keys`）")


def recall(store, ctx: RecallCtx, *, mode: Any = DEFAULT_MODE,
           k: int | None = None, weights: dict[str, float] | None = None,
           ) -> list[Candidate]:
    """⭐ **唯一对外前门**：一次召回 = 一种**形式**（`mode`，见 `MODES`）。

    = `recall_with_keys()` 丢掉第二项（⛔ 不是第二份实现 —— 形式一多, 两份实现必漂）。

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
    return recall_with_keys(store, ctx, mode=mode, k=k, weights=weights)[0]


def recall_with_keys(store, ctx: RecallCtx, *, mode: Any = DEFAULT_MODE,
                     k: int | None = None, weights: dict[str, float] | None = None,
                     ) -> tuple[list[Candidate], list[str]]:
    """⭐ 前门的**带钥匙版本** —— 候选与 `recall()` **逐条相同**, 另给"这次用的钥匙"。

    钥匙 = **载荷的人话形式**（`set` 型: 老师用的那个写法 / 扫到的那段时间的原话）。
    为什么要它（2026-10-12 用户）: 段头要写成「**你想着「阿露」**——浮上来的是这些」,
    这样"**一个词 → 一批记忆**"就在她眼前成立 —— 那正是 `look` 的语义,
    P19 每轮顺带演示一遍（她下次自己写 `clue` / `when` 时心里有数）。

    ⚠️ 钥匙与候选出自**同一次** `_payloads`（同一份派生料、同一套剔除规则）——
    ⛔ 不重算、不抄第二份。
    ⛔ `rank` 型**没有**钥匙（"问哪个面"是六路加权, 没有单一钥匙）⇒ 返 `[]`。
    """
    m = mode_of(mode)
    if m.shape == SHAPE_RANK:
        return like(store, ctx, spec=m.spec, k=k, weights=weights), []
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
    return out, _keys(base, m)


def _sort_set(cands: list[Candidate], m: Mode) -> None:
    """`set` 型的排序（口径 = `find._order` —— **同一条规则, 不抄第二份**）。"""
    if m.order == "newest":
        cands.sort(key=lambda c: _newest_key(c.node))
    elif m.order:
        raise KeyError(f"形式 {m.spec or m.anchors} 的 order={m.order!r} 不认识"
                       f"（`set` 型只有 'newest'）")


def _fill(template: str, key: Any, *, mode: Any) -> str:
    """把文案里的 `{{key}}` 槽填上 —— ⛔ **没钥匙就不许印**。

    ⚠️ 本函数从前是 `str.replace` 的**第三份**手写填槽实现（另两份在
    `contract/digest/` 与 `llm/prompts/` 的调用方）—— 2026-10-12 收口到
    `contract.slots.render_template`（**一个实现，三处用**）。当初不用 `str.format`
    的理由照旧成立: 文案里还有 JSON（`{"noticed": …}`）, `format` 会把那对花括号
    当占位符炸掉。
    ⛔ 带槽而钥匙为空 ⇒ **当场炸**（不静默印 `{{key}}` 四个字符给她看）——
    这条纪律是**本层**的（`render_template` 只管"槽与值对得上"）, 所以留在调用侧。
    """
    if "{{key}}" not in template:
        return template
    text = str(key or "").strip()
    if not text:
        raise ValueError(f"形式 {mode!r} 的文案带 {{{{key}}}} 槽, 但这次**没算出钥匙** —— "
                         f"⛔ 不印半成品（宁可不摆这一段）")
    return render_template(template, {"key": text}, where=f"形式 {mode!r} 的文案")


def render_section(cands: Iterable[Candidate], *, mode: Any = DEFAULT_MODE,
                   key: Any = "", empty_ok: bool = True, **kwargs) -> str:
    """⭐ **形式 → 她看到的那一段字**：文案（含钥匙）从表里取, 其余**原样透传**。

    = `render.render_candidates` 的一层薄壳（⛔ 这里不印字、不筛面、不截断 ——
    那些都在渲染层; 本函数只负责"用这个形式的文案"）。三件事按顺序:

    1. **填钥匙**：`Mode.header` / `Mode.hint` 里的 `{key}` 槽 ← `key`（老师用的那个词）;
    2. **有货** ⇒ 照旧交给 `render_candidates`（段头 + 逐条记忆行 + 段尾）;
    3. ⭐ **空手**（`cands` 空 且 钥匙非空 且 表里有 `Mode.empty`）⇒ 印**空手那句话**
       —— 沉默是有歧义的（"没查" vs "查了没有"）, 而"想了一下没想起来"是她能拿来
       说话的事实（同 `look` 的三档空手）。
       ⛔ **没有钥匙 ⇒ 空手也不印**（普通闲聊每轮来一句"你什么也没想起来"是噪声）;
       ⛔ 空手那句话**不占字符预算**（就一行字, 走不到 `render_candidates` 的累积里）。

    ⚠️ `empty_ok=False` = **这次的"空"不是因为没想起来** —— 是命中的那几条已经在**别的段**里
    摆过了（engine 的跨段去重掏空的）。那种情况印空手就是**假话**（"想起来了, 只是摆在前一段"）
    ⇒ ⛔ 一个字都不印。判据只有 engine 有（它知道去重前后各几条）⇒ 由它传。
    """
    m = mode_of(mode)
    picked = list(cands)
    if not picked:
        # ⛔ **没有钥匙 ⇒ 空手也不印**（闲聊每轮来一句"你什么也没想起来"是噪声）。
        # ⚠️ 顺序要紧: 先看钥匙**再看 `empty`**, 而且**别在空手分支之前填抬头** ——
        #    空钥匙去填 `{key}` 槽会当场炸（`name` 没被触发的那些轮正是"空手 + 无钥匙"）。
        if not m.empty or not empty_ok or not str(key or "").strip():
            return ""
        return _fill(m.empty, key, mode=mode)
    return render_candidates(picked, header=_fill(m.header, key, mode=mode),
                             hint=_fill(m.hint, key, mode=mode), **kwargs)


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
