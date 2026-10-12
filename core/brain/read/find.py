"""find — **定向寻找**（读路径的集合查询, 2026-10-08）。

「一个包、两个类」里的**定向**那一类 —— 与 `like` 的分工是**问题类型不同**:

| | `like` | `find` |
|---|---|---|
| 问什么 | 哪几条**最像** | 符合这几条的**有哪几条** |
| 不变量 | **排序就是答案** | ⭐ **漏一条就是错** |
| 判据 | 打分（连续、可比） | **命中 / 不命中**（没有中间态） |
| 输出 | top-k | **全部** |

## ⭐ 那条不变量决定了其余一切

只要判据里混进"相似", "全部"就失去意义 ⇒ **锚表里不许有打分函数**。
所以这里全是**确定的判据**（相等 / 集合成员 / 闭区间 / 字面子串布尔式）:
⛔ 没有阈值 · ⛔ 没有 top-k · ⛔ 不要后端 · ⛔ 本模块**不截断**。
（"不漏"是**检索层**的不变量; "摆几条给她看"是 `look` 那一层的事 ——
两个不同的问题, 别把 cap 塞进来。）

## 输入契约: 锚 = `{键: 已解析的载荷}`（AND）

    find(store, {"title": "屋顶的苔藓"})                     # 名字 → 那一条
    find(store, {"entity": "x0001"})                        # 「老师」车道上**全部**
    find(store, {"group": "g0001"})                         # 那个类里的**全部**成员
    find(store, {"entity": "x0001", "when": (d0, d1)})      # AND: 两条都要满足
    find(store, {}, kinds=("belief",))                      # 空锚 = 这个面上的全部

⚠️ **值不是她的原话** —— "名字 → 谁" 是 `address.find_episode` / `entities.find_entity`
/ `address.find_group` 的活（三件都已存在）; "时间那句话 → 区间" 是
`core/worldtime/parse_when` 的活。⇒ 解析失败（`miss` / `ambiguous` / 时间认不出）
**不在本模块的返回里**, 也不该在这里: 那是调用方手里的事实, "怎么跟她说"也是
调用方的事。

三种"空"的分工（一句话记住）:
* **没这条**（名字解析不到）—— 解析层, 调用方知道;
* **没想起来**（锚解析成功但一条都不符）—— 本模块返 `[]`;
* **那段时间没有、前后有**—— 调用方把 `when` 拿掉**再调一次**
  （⛔ 本模块不猜"该放宽多少": 放宽的幅度是产品口径）。

⛔ 未知锚名 ⇒ `KeyError`; 值不合格（不存在的 entity / 不是 `(date, date)` /
不是编译好的 `Clue`）⇒ `ValueError`。两处都**当场炸**, 不许静默少一格
（同 `like.plan()` 与 `recall_config.get` 的纪律）。

## 五条锚（`ANCHORS` 表; 每条 1:1 对应一个**已有**原语 —— 零新匹配逻辑）

| 键 | 判据 | 复用什么 |
|---|---|---|
| `title` | `normalize_title(n.title) == normalize_title(值)` | `address.normalize_title` |
| `entity` | `n.id ∈ graph.lane(值)`（`about` 入边, 方向已固定） | `graph.Graph.lane` |
| `group` | 值 ∈ `graph.targets(n.id, REL_MEMBER_OF)` | `graph`（node → experience） |
| `when` | `start ≤ date_of(n.ts) ≤ end`（**闭区间**, 粒度 day） | `worldtime.age.date_of` |
| `text` | `Clue` 在**正文面**（`pack.body_of`）上成立 | `Clue` + `body_of` |

⛔ **`tag` / `kind` / `edge` 故意不落**: 今天没有消费者（判据①: 没读者不写）。
加一条 = 表里一行 + 一条守门, 等 `look` / digest 真要用时加。

## 排序 = 展示顺序（`find` 的"分"只是它）

**时间倒序（新→旧）**; ⚠️ **无 `ts` 的垫底** —— 时间未知**不许冒充最新**
（哨兵纪律: `date_of` 给 `None` 时既不编时间, 也不参与"最新"）。
同刻按 id ⇒ **逐字节确定**（无 rng、不依赖字典序）。
⇒ `Candidate.score` **恒 `0.0`**: `find` 没有分, ⛔ 不拿 `significance` 冒充
（那是 `like` 的 prior 路）; 台账走 `scores=False`（印 `m0014←对象 …` 而不是 `:0.000`）。
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from core.brain import marks
from core.brain.address import normalize_title
from core.brain.entities import entity_label
from core.brain.graph import REL_MEMBER_OF, graph_of
from core.brain.read.pack import Candidate, body_of, ledger_line
from core.worldtime.age import date_of

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 一、检索线索（`Clue`）—— 她写**字面 + 运算符**, 引擎编译成树
# ---------------------------------------------------------------------------

class ClueError(ValueError):
    """线索写歪了（不是"没找到"）—— 调用方拿它说人话（"看不懂, 换个说法"）。

    ⚠️ **两条路别混**: "线索看不懂" 与 "看懂了但没想起来" 是**两句不同的话**;
    混成一句, 她永远学不会怎么写。
    """


#: AND / OR 的两种写法 —— ⚠️ **四个都认**（`&&` `&` `||` `|`）
_AND = ("&&", "&")
_OR = ("||", "|")
#: 词形运算符（容错; 大小写不敏感）—— LLM 写 "苔藓 and 杂草" 也认
_WORD = {"and": "&&", "or": "||"}
#: ⛔ **正则味的字符** —— 她写这些说明她在写正则, 而本引擎只认**字面** + `&`/`|`/括号。
#: 逐个**明确拒**（可归因）, 不会变成"她以为在写模式、引擎当字面、静默 0 命中"。
#: （`\` 尤其致命: `\d` 在 JSON 字符串里是**非法转义** ⇒ 直接打掉整行。）
_FORBIDDEN = "\\{}[]*+?^$"

#: ⭐ **全角运算符兜底**（2026-10-08）: 中文输入法很容易吐全角 `＆` —— 不归一的后果是
#: 整串被当**一个字面**（`苔藓＆＆杂草` 一个词也匹配不到 ⇒ **静默 0 命中**）。
#: ⚠️ **只收 `＆`**，另外两个"看起来也像运算符"的全角字符**故意不归一**:
#:   · `｜` —— 它是**地址空间里的字段分隔符**（`marks.FIELD_SEP`）。她很可能把整段
#:     元信息（`《名》｜5 天前｜9/26`）抄进线索; 归一成 `|` 就变成"三段的 OR",
#:     会给出**错的**结果（比"空"更坏）。而那个场景 **①级标题查**已经救得住
#:     （`address.normalize_title` 正是取 `｜` 第一段）。
#:   · `（）` —— 真档 30 节点的正文里**出现过**（插入语）; 当归组会让"照抄正文片段"
#:     的线索被误解析。实测: `& | ＆ ｜ ＼ ＋ ( )` 与全角空格在真档**全部零出现**,
#:     只有 `（）` 有 1 处。
_FULLWIDTH_OPS = {"＆": "&"}


@dataclass(frozen=True)
class Clue:
    """一条**字面**布尔表达式（她写的检索线索 → 引擎编译的树）。

    ## 为什么**不给她 `re`**（2026-10-08 用户裁: 用 `&`/`|` 而不是正则）

    1. ⛔ **JSON 非法转义**: `\\d` / `\\w` / `\\.` 在 JSON 字符串里**非法**
       （合法转义只有 `\\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX`）⇒ **整行解析失败**
       —— 那不是"精度差一点", 是把行协议打掉;
    2. ⛔ `{}` 与引号: 写错了就把这一行弄坏（一形一义也被破）;
    3. ⛔ **回溯**: Python `re` 没有超时, `(a+)+b` 能卡死同步链;
    4. ⛔ **不需要**: 中文里"短子串"已经覆盖了 `苔.` 想干的事（`苔` 一条就收了
       苔藓/苔痕/青苔）; 而 agent 用 grep 时那个 `.*` 想表达的**"同一条里同时含"**
       正是 `&&` —— 而"同一条"由记忆的粒度天然给。

    ⇒ 规范 = **字面 + `&&`/`&` + `||`/`|` + 半角括号**; 转义 / 量词 / 字符类
    **一律拒**（`_FORBIDDEN`）。半角 `( )` 当分组是**实测安全**的: 真档 30 节点的
    正文里 `& | ( )` **零出现**, 而全角 `（）` 出现过（正文插入语）⇒ **全角一律当字面**。

    `matches()` 是求值的**唯一实现**: 字面用 `in` —— ⛔ **零 `re`**（连 import 都没有）。
    """

    op: str = "lit"
    text: str = ""
    args: tuple[Clue, ...] = field(default_factory=tuple)

    def matches(self, text: str) -> bool:
        if self.op == "lit":
            return self.text in (text or "")
        if self.op == "and":
            return all(a.matches(text) for a in self.args)
        return any(a.matches(text) for a in self.args)

    def __str__(self) -> str:
        """台账里那一眼: `(苔藓 AND (杂草 OR 屋顶))` —— **引擎的理解**, 可复盘。"""
        if self.op == "lit":
            return self.text
        return "(" + f" {self.op.upper()} ".join(str(a) for a in self.args) + ")"


def _is_op(tok: str) -> bool:
    return tok in _AND or tok in _OR


def _ends_operand(tok: str) -> bool:
    return tok == ")" or (not _is_op(tok) and tok != "(")


def _starts_operand(tok: str) -> bool:
    return tok == "(" or (not _is_op(tok) and tok != ")")


def _tokenize(raw: str) -> list[str]:
    """字面 / 运算符 / 括号（**空白 = 分隔** ⇒ 后面补隐式 AND）。

    ⚠️ 开头先做**全角运算符兜底**（`_FULLWIDTH_OPS`）—— `＆` 不归一就是"静默 0 命中"。
    """
    for full, half in _FULLWIDTH_OPS.items():
        raw = raw.replace(full, half)
    toks: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            word = "".join(buf)
            toks.append(_WORD.get(word.casefold(), word))
            buf.clear()

    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch.isspace():                     # 空白 = 分隔（`苔藓 杂草` ⇒ 隐式 AND）
            flush()
            i += 1
            continue
        if ch in "&|()":
            flush()
            pair = raw[i:i + 2]
            if pair in _AND or pair in _OR:
                toks.append(pair)
                i += 2
            else:
                toks.append(ch)
                i += 1
            continue
        buf.append(ch)
        i += 1
    flush()
    out: list[str] = []
    for tok in toks:                         # 相邻两个操作数 ⇒ 隐式 AND（`(a)(b)` 同理）
        if out and _ends_operand(out[-1]) and _starts_operand(tok):
            out.append("&&")
        out.append(tok)
    return out


def _parse_expr(toks: list[str], i: int) -> tuple[Clue, int]:
    """`|` 层（优先级低）—— 与 Rust/C/Python 同款: `&` 紧于 `|`。"""
    node, i = _parse_term(toks, i)
    args = [node]
    while i < len(toks) and toks[i] in _OR:
        node, i = _parse_term(toks, i + 1)
        args.append(node)
    return (args[0] if len(args) == 1 else Clue("or", args=tuple(args))), i


def _parse_term(toks: list[str], i: int) -> tuple[Clue, int]:
    """`&` 层。"""
    node, i = _parse_atom(toks, i)
    args = [node]
    while i < len(toks) and toks[i] in _AND:
        node, i = _parse_atom(toks, i + 1)
        args.append(node)
    return (args[0] if len(args) == 1 else Clue("and", args=tuple(args))), i


def _parse_atom(toks: list[str], i: int) -> tuple[Clue, int]:
    if i >= len(toks):
        raise ClueError("检索线索在运算符之后就断了（`&` / `|` 后面要有词）")
    tok = toks[i]
    if tok == "(":
        node, i = _parse_expr(toks, i + 1)
        if i >= len(toks) or toks[i] != ")":
            raise ClueError("检索线索里的括号没有闭合（分组请用**半角**括号）")
        return node, i + 1
    if tok == ")" or _is_op(tok):
        raise ClueError(f"检索线索里的 {tok!r} 位置不对（缺一个词?）")
    return Clue("lit", text=tok), i + 1


def compile_clue(raw: object) -> Clue:
    """她写的线索串 → `Clue`（⛔ 只认字面与运算符, 认不出就 `ClueError`）。

    ⚠️ **编译住在检索层**（而不是 mmt 那一侧）: 它描述的是"**怎么匹配正文**",
    与被谁调用无关; 而 `core/brain/` 不许 import `core/mmt/`（分层守门）。
    调用方（`look` 的 parse 层）只负责**捕获 `ClueError` 并说人话**。

    形态::

        苔藓                    一个字面
        苔藓 && 杂草             两个都要有（`&` / `and` 同义）
        苔藓 || 屋顶             任一有（`|` / `or` 同义）
        (苔藓 || 杂草) && 老师    混合（`&` 紧于 `|`; 建议带括号）
        苔藓 杂草                空白 = 隐式 AND
    """
    text = str(raw or "").strip()
    if not text:
        raise ClueError("空的检索线索")
    toks = _tokenize(text)
    if not toks:
        raise ClueError("空的检索线索")
    for tok in toks:
        if _is_op(tok) or tok in ("(", ")"):
            continue
        bad = sorted({c for c in tok if c in _FORBIDDEN})
        if bad:
            raise ClueError(
                f"检索线索里有正则味的字符 {' '.join(bad)} —— 这里只认字面"
                "（要「或」写 `|`, 要「且」写 `&`; 转义 / 量词 / 字符类都不支持）")
    node, i = _parse_expr(toks, 0)
    if i != len(toks):
        raise ClueError(f"检索线索在 {toks[i]!r} 处看不懂（多了一个词? 少了一个运算符?）")
    return node


# ---------------------------------------------------------------------------
# 二、锚表（`ANCHORS`）—— 每条都是**确定的**判据
# ---------------------------------------------------------------------------

#: 一个锚 = `(store, 值) -> (谓词, 台账里那一句)`。
#: ⚠️ 值**已经解析好**（见模块 docstring）; 不合格 ⇒ `ValueError`（当场炸）。
Anchor = Callable[[Any, Any], "tuple[Callable[[Any], bool], str]"]


def _as_date(value: object, what: str) -> date:
    """值必须是一个 `date`（⛔ `datetime` 不算 —— 它带时刻, 而粒度只到 day）。"""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    raise ValueError(f"{what} 要一个 `date`（粒度只到 day）, 实得 {value!r}")


def _a_title(store, value) -> tuple[Callable[[Any], bool], str]:
    """名字 → 那一条（**归一后逐字相等**）。"""
    want = normalize_title(value)
    if not want:
        raise ValueError(f"title 锚的名字归一后为空: {value!r}")
    return (lambda n: normalize_title(getattr(n, "title", "")) == want), \
        f"名字{marks.name(want)}"


def _a_entity(store, value) -> tuple[Callable[[Any], bool], str]:
    """对象 → 它**车道上全部**（`about` 入边; 含 episode / belief / …）。"""
    eid = str(value or "").strip()
    node = store.get(eid) if eid else None
    if node is None or getattr(node, "kind", "") != "entity":
        raise ValueError(f"entity 锚要一个存在的 entity id, 实得 {value!r}")
    lane = set(graph_of(store).lane(eid))
    return (lambda n: getattr(n, "id", "") in lane), f"对象 {entity_label(node)}"


def _a_group(store, value) -> tuple[Callable[[Any], bool], str]:
    """类（`experience`）→ 它**全部**成员（`member_of`: node → 类）。"""
    gid = str(value or "").strip()
    node = store.get(gid) if gid else None
    if node is None or getattr(node, "kind", "") != "experience":
        raise ValueError(f"group 锚要一个存在的 experience id, 实得 {value!r}")
    members = set(graph_of(store).sources(gid, REL_MEMBER_OF))
    return (lambda n: getattr(n, "id", "") in members), f"类 {marks.name(node.title)}"


def _a_when(store, value) -> tuple[Callable[[Any], bool], str]:
    """时间 → **闭区间** `[start, end]`（两端都含, 粒度 day）。

    ⚠️ 无 `ts` / 坏 `ts` 的节点**不命中** —— 哨兵纪律: 不知道是哪天的,
    不许冒充"落在这段时间里"（同 `age_days` 的"绝不折成 0"）。
    """
    try:
        start, end = value                       # type: ignore[misc]
    except (TypeError, ValueError):
        raise ValueError(f"when 锚要 `(start, end)` 两个日期, 实得 {value!r}") from None
    start = _as_date(start, "when 的起点")
    end = _as_date(end, "when 的终点")
    if start > end:
        raise ValueError(f"when 的起点晚于终点: {start} > {end}")

    def pred(n) -> bool:
        d = date_of(getattr(n, "ts", ""))
        return d is not None and start <= d <= end

    return pred, f"时间 {start.isoformat()}..={end.isoformat()}"


def _a_text(store, value) -> tuple[Callable[[Any], bool], str]:
    """正文 → `Clue` 成立（面 = `pack.body_of`, 含标题）。

    ⛔ **不收裸串**: 编译与校验归调用方（`compile_clue` 就在本模块, 一行）——
    这样"她写歪了"在**编译那一刻**就明确拒, 而不是在这里静默 0 命中。
    """
    if not isinstance(value, Clue):
        raise ValueError(f"text 锚要 compile_clue() 的产物, 实得 {value!r}")
    return (lambda n: value.matches(body_of(n))), f"正文 {value}"


#: ⭐ **锚表**（照 `like.PARTS` 的形态: 一个场景一块, 自包含、好审）。
#: 表里的**顺序 = 台账里印的顺序**（与调用方给的 dict 顺序无关 ⇒ 台账确定）。
ANCHORS: dict[str, Anchor] = {
    "title": _a_title,
    "entity": _a_entity,
    "group": _a_group,
    "when": _a_when,
    "text": _a_text,
}


# ---------------------------------------------------------------------------
# 三、find
# ---------------------------------------------------------------------------

def _order(node) -> tuple:
    """排序键: **新→旧**, ⚠️ **无 `ts` 的垫底**, 同刻按 id（逐字节确定）。"""
    d = date_of(getattr(node, "ts", ""))
    return (d is None, -(d.toordinal() if d is not None else 0),
            str(getattr(node, "id", "")))


def find(store, anchors: dict, *, kinds: tuple[str, ...] = ("episode",),
         ) -> list[Candidate]:
    """一组**确定的**判据 → **全部**符合的节点（时间倒序; 空 = `[]`）。

    Args:
        store: `WikiStoreV2`（**只读**）。
        anchors: `{锚名: 已解析的载荷}`（AND; `{}` = 该面上的全部）。
            ⛔ 未知锚名 ⇒ `KeyError`; 值不合格 ⇒ `ValueError`（都当场炸）。
        kinds: 选面（节点 kind 白名单）—— 语义与 `like.Spec.kinds` **同一套**:
            `()` = 不过滤。"她指的是哪一类"由**调用方选哪个解析器**决定
            （episode → `find_episode` / 对象 → `find_entity` / 类 → `find_group`）。

    Returns: 全部命中（已排序）; 一条都不符 ⇒ `[]`（**不拿"最近的"来凑** ——
    那会让"没想起来"永远不出现, 而那句话正是"该去问老师了"的触发器）。
    """
    unknown = sorted(set(anchors) - set(ANCHORS))
    if unknown:
        raise KeyError(f"未知的锚: {unknown}（可用: {sorted(ANCHORS)}）")
    preds: list[Callable[[Any], bool]] = []
    labels: list[str] = []
    used: list[str] = []
    for name, build in ANCHORS.items():           # 表的顺序 = 台账的顺序（确定）
        if name not in anchors:
            continue
        pred, label = build(store, anchors[name])
        preds.append(pred)
        labels.append(label)
        used.append(name)
    nodes = [n for n in store.all()
             if not kinds or getattr(n, "kind", "") in kinds]
    hits = [n for n in nodes if all(p(n) for p in preds)]
    hits.sort(key=_order)
    why = " · ".join(labels)
    out = [Candidate(node=n, score=0.0, why=why) for n in hits]
    # 台账（可 grep）: 用哪几条锚 / 池多大 / 命中几条 / 摆的是谁（**标题她看得见,
    # 编号只有排查时才有用**）; ⛔ `k=` 不印（find 没有"要几条"这个概念）。
    logger.info(ledger_line(out, name="recall_find", scores=False,
                            query=why or "（空锚 = 全量）",
                            pool=len(nodes), spec=",".join(used)))
    return out


__all__ = ["ANCHORS", "Clue", "ClueError", "compile_clue", "find"]
