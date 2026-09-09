# -*- coding: utf-8 -*-
"""叙事文本切分器（2026-09-02 方案定稿: 断句权从 LLM 移交程序）。

背景: LLM 自切段落会产生格式幻觉（（… 与 ）拆段、段内多句、孤符号）——
"该程序做的"（切分/配对/合并）不该让 LLM 背。story-LLM 只输出自然段文本
（可含多句）; 本模块按规则切句:

  1. 孤符号清洗: 不成对的全角 （）「」『』 移除（防裸符号渲染; 半角留给
     ASCII/表情/编号语境, 不动）
  2. 块保护: 「」『』 与 （） 成对区间 → 占位符（块内句末标点不切, 整块成句）;
     :) :( =) 表情与 "2)" 列表编号不误判为括号对; 嵌套/重叠区间联合
  3. 标点切句: 。！？； 全角 + 半角 !? + "." ; 连续句末标点吞并;
     半角 "." 两侧为 ASCII 字母/数字 → 不切（3.14 / v2.0 / e.g.）;
     半角 "..." 点区整体跳过（不切）; 省略号 … 不算句末
  4. 碎句合并（jieba 正式辅助, merge_short_chunks）: 段内**裸旁白短句**
     （可见字 ≤6, 非引号块, 非 !？ 结尾）→ 并入后句; 后句以粘连虚词开头
     （jieba 首词 ∈ 表; 无 jieba → 内置前缀表降级）→ 并入前句;
     合并结果可见字 ≤ 30（防整段糊成一团）
  5. 自然段 = 强边界: 调用方逐段调用 split_paragraph, 绝不跨段合并

渲染单位 = 切出的句段（emotion 标注层逐句回填）。
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("live2be.bond")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 句末标点（全角 + 半角 !?; "." 单独处理——数字/缩写特判）
_SENT_END = "。！？；!?"

#: 全角括号对（孤符号清洗 + 块保护扫描用; 半角 () 仅块保护, 不参与清洗）
#: 2026-09-09: 补入弯引号 ‘’“”（LLM 对白常偏离「」规范）——右引号否则被
#: 单独切成孤句（事件流曾现 {"text":"’"}）
_FULL_PAIRS = [("（", "）"), ("「", "」"), ("『", "』"),
               ("‘", "’"), ("“", "”")]
_BLOCK_PAIRS = _FULL_PAIRS + [("(", ")")]

#: 半角闭括号前驱 ∈ 此集 → 表情/颜文字（:) :( =) ;) 等）——不配对
_EMOTICON_PRE = ":;=8"

#: 碎句合并参数（2026-09-02 用户拍板: 阈值 6, 合并总长 ≤30）
MERGE_MIN = 6          # 短句可见字数阈值（≤ → 视为碎句）
MERGE_MAX = 30         # 合并后可见字数上限

#: 粘连虚词（B 句开头命中 → 弱句界, 并入前句; jieba 首词判定, 前缀表兜底）
_CONNECTIVES = (
    "然后", "接着", "随即", "于是", "随后", "之后", "这时", "此时",
    "又", "便", "就", "才", "却", "而", "可", "但", "但是", "可是", "然而",
    "不过", "再说", "其实", "反正", "毕竟", "结果", "最后", "终于", "突然",
    "忽然", "只见", "原来", "所以", "因此", "因为", "竟", "幸好", "好在",
    "没想到", "谁知", "怎料",
)

#: 占位符（私用区, 中文/英文文本不可能出现）——块替换后做纯标点切分
_PH_L = "\ue000"
_PH_R = "\ue001"
#: 块断点标记: 块原文以句末标点收尾（完整句意）→ 占位符后跟此标记,
#: 切分器把它当句界（块自成句, 不与后续普通文本粘连）; 归位后移除
_PH_END = "\ue002"

#: 可见字数: 中英文/数字字符（标点、空白、省略号不计）
_VISIBLE = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]")

#: jieba 懒加载缓存（词典首次加载 ~1s, 只做一次）
_jieba = None


def _jieba_first(text: str) -> str:
    """jieba 取首词（无 jieba → 空串, 走前缀表）。"""
    global _jieba
    try:
        if _jieba is None:
            import jieba          # 正式依赖（2026-09-02）; 缺失则降级前缀表
            _jieba = jieba
        return next(iter(_jieba.cut(text))).strip()
    except Exception:             # noqa: BLE001 — 任何异常降级前缀表
        return ""


def _starts_with_connective(text: str) -> bool:
    """后句是否以粘连虚词开头（jieba 首词命中 → True; 否则内置前缀表兜底）。"""
    head = text.lstrip("「『（( \t\n")
    if not head:
        return False
    w = _jieba_first(head)
    if w and any(w.startswith(c) or c.startswith(w) for c in _CONNECTIVES):
        return True
    return any(head.startswith(c) for c in _CONNECTIVES)


def visible_len(text: str) -> int:
    """可见字数 = 中英文/数字字符数（标点/空白/省略号不计）。"""
    return len(_VISIBLE.sub("", text))


# ---------------------------------------------------------------------------
# 1. 孤符号清洗（全角括号不成对 → 移除）
# ---------------------------------------------------------------------------

def _sanitize_orphans(text: str) -> str:
    """移除不成对的全角括号/引号字符（防渲染出现裸 （ 或单独 ） 字符）。

    半角 ( ) 不处理——ASCII 语境（表情/编号/缩写）由块保护的特判规则兜底。
    """
    matched: set[int] = set()
    for opener, closer in _FULL_PAIRS:
        stack: list[int] = []
        for i, ch in enumerate(text):
            if ch == opener:
                stack.append(i)
            elif ch == closer and stack:
                matched.add(stack.pop())
                matched.add(i)
    drop = {
        i for i, ch in enumerate(text)
        if any(ch == o or ch == c for o, c in _FULL_PAIRS) and i not in matched
    }
    if not drop:
        return text
    return "".join(ch for i, ch in enumerate(text) if i not in drop)


# ---------------------------------------------------------------------------
# 2. 块保护（成对区间 → 占位符）
# ---------------------------------------------------------------------------

def _scan_blocks(text: str) -> list[tuple[int, int]]:
    """成对括号区间（含字符跨度）; 表情/编号排除; 重叠区间联合。

    半角 ")" 的前驱 ∈ {:;=8} 或数字 → 表情/编号, 不参与配对;
    半角 "(" 由匹配决定（":(" 的 "(" 无配对 → 自然不成区间）。
    """
    raw: list[tuple[int, int]] = []
    for opener, closer in _BLOCK_PAIRS:
        stack: list[int] = []
        for i, ch in enumerate(text):
            if ch == opener:
                stack.append(i)
            elif ch == closer and stack:
                if closer == ")" and i > 0 and text[i - 1] in _EMOTICON_PRE + "0123456789":
                    continue                 # :) 表情 / 2) 编号 → 不配对
                raw.append((stack.pop(), i + 1))
    if not raw:
        return []
    raw.sort()
    merged: list[tuple[int, int]] = [raw[0]]
    for s, e in raw[1:]:
        ps, pe = merged[-1]
        if s < pe:                             # 真重叠（嵌套）→ 联合;
            merged[-1] = (ps, max(pe, e))      # 相邻（s == pe）各自独立（各自断句）
        else:
            merged.append((s, e))
    return merged


def _to_placeholder(text: str, blocks: list[tuple[int, int]]
                    ) -> tuple[str, dict[str, str]]:
    """区间 → 占位符; 返回 (占位文本, {占位: 原文})。

    块原文含句末标点/省略号（完整句意, 如 （…说。） 「…！」 （…是真的吗……））
    → 占位符后带断点标记（块自成句——"她走近。（她犹豫。然后说。）她开口了。"
    三段分明）; 短语块（如 （声音很小） （笑））不带断点, 并入所在句。
    """
    lookup: dict[str, str] = {}
    parts: list[str] = []
    last = 0
    for i, (s, e) in enumerate(blocks):
        parts.append(text[last:s])
        key = f"{_PH_L}{i}{_PH_R}"
        lookup[key] = text[s:e]
        inner = text[s + 1:e - 1] if e - s >= 2 else text[s:e]
        if any(c in inner for c in "。！？；!?") or "…" in inner or "..." in inner:
            parts.append(key + _PH_END)          # 完整句意 → 块后断句
        else:
            parts.append(key)                    # 短语 → 不断, 并入所在句
        last = e
    parts.append(text[last:])
    return "".join(parts), lookup


def _restore(paragraphs: list[str], lookup: dict[str, str]) -> list[str]:
    out = []
    for p in paragraphs:
        for key, raw in lookup.items():
            if key in p:
                p = p.replace(key, raw)
        p = p.replace(_PH_END, "")
        p = p.strip()
        if p:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# 3. 纯标点切句（无块文本; 占位符不参与标点判定）
# ---------------------------------------------------------------------------

def _cut_plain(text: str) -> list[str]:
    """按句末标点切分（保留标点; 连续标点吞并; 块断点标记为界; "." 特判）。"""
    n = len(text)
    out: list[str] = []
    start = 0
    i = 0
    while i < n:
        ch = text[i]
        if ch == _PH_END:                            # 块断点（完整句意块之后）
            out.append(text[start:i + 1])
            start = i + 1
            i += 1
            continue
        if ch in _SENT_END:
            j = i + 1
            while j < n and text[j] in _SENT_END:    # 连续句末标点整体收尾
                j += 1
            out.append(text[start:j])
            start = j
            i = j
            continue
        if ch == ".":
            j = i
            while j < n and text[j] == ".":          # 半角点区
                j += 1
            if j - i >= 2:                           # "..." 省略号 → 永不切
                i = j
                continue
            # 单点 ".": 两侧均为 ASCII 字母/数字 → 数字/缩写内部（3.14 v2.0）不切;
            # 其余（点前中文/空格 或 点后中文/空白/行尾）→ 句末点
            prev = text[i - 1] if i > 0 else ""
            nxt = text[j] if j < n else ""
            prev_an = prev.isascii() and prev.isalnum()
            nxt_an = nxt.isascii() and nxt.isalnum()
            if prev_an and nxt_an:
                i = j                                # 小数/版本号/缩写 → 不切
                continue
            out.append(text[start:j])
            start = j
            i = j
            continue
        i += 1
    if start < n:
        out.append(text[start:])
    return [s.strip() for s in out if s.strip()]


# ---------------------------------------------------------------------------
# 4. 碎句合并（jieba 辅助）
# ---------------------------------------------------------------------------

def _should_merge(a: str, b: str) -> bool:
    """a 与 b 相邻是否合并（组视角——链式累计后 a 可能已超阈值）:

    1. a 或 b 含引号/括号块（「」『』（））→ 不并（对白/动作块是独立呈现单元）
    2. a 或 b 以 !？ 结尾 → 不并（强情绪句独立）
    3. a 可见字 ≤ MERGE_MIN → 并（碎句开组）
    4. b 可见字 ≤ MERGE_MIN（链式续组——累计 a 变长后靠这条继续吞并）
    5. b 以粘连虚词开头（弱句界）→ 并
    总长始终受 MERGE_MAX 约束。
    """
    if visible_len(a) + visible_len(b) > MERGE_MAX:
        return False
    if any(q in a + b for q in ("「", "」", "『", "』", "（", "）")):
        return False
    if a.endswith(("！", "？", "!", "?")) or b.endswith(("！", "？", "!", "?")):
        return False
    if visible_len(a) <= MERGE_MIN:
        return True
    if visible_len(b) <= MERGE_MIN:
        return True
    return _starts_with_connective(b)


def _merge_short(paragraphs: list[str]) -> list[str]:
    """段内碎句合并（自然段内单向扫描; 结果仍 ≤ MERGE_MAX 可见字）。"""
    if len(paragraphs) < 2:
        return paragraphs
    out: list[str] = []
    for p in paragraphs:
        if out and _should_merge(out[-1], p):
            out[-1] = out[-1] + p
        else:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------

def split_paragraph(text: str) -> list[str]:
    """自然段文本 → 句段列表（渲染单位; 每句一个 emotion 槽）。

    管线: 孤符号清洗 → 块保护占位 → 标点切句 → 占位归位 → 碎句合并。
    已是单句/句段的输入幂等（无句末标点 → 原样单段返回）。
    """
    if not text or not text.strip():
        return []
    cleaned = _sanitize_orphans(text.strip())
    if not cleaned:
        return []
    blocks = _scan_blocks(cleaned)
    if not blocks:
        cuts = _cut_plain(cleaned)
    else:
        placeholder, lookup = _to_placeholder(cleaned, blocks)
        cuts = _cut_plain(placeholder)
        cuts = _restore(cuts, lookup)
    return _merge_short([c for c in cuts if c])
