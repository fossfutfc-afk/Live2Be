"""MomoTalk 文本处理器 — 去动作括号 + 断句 + 格式化。

纯函数组，不依赖 LLM / 角色 / 会话状态。
可直接用于 MomoTalk，也可被羁绊剧情复用（仅 _strip_action_brackets）。

以下所有方法几乎都服从于中文文本，英文文本需要另给逻辑。

公开 API:
    _strip_action_brackets(text)          → str
    _split_for_momotalk(text, max_chars)  → list[str]
    _process_for_momotalk(text)           → list[str]
    strip_name_prefix(text, name)         → str
"""

from __future__ import annotations

import re

# MomoTalk 消息长度阈值（字符数）
MMT_MAX_CHUNK_CHARS = 25
MMT_MIN_CHUNK_CHARS = 5


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def _strip_action_brackets(text: str) -> str:
    """去除括号内的动作描写。

    MomoTalk 是手机聊天——没有"（低头）（小声）"这种舞台指示。
    循环去除最内层括号，正确处理嵌套。

    假如之后有那种喜欢在聊天里发括号的人设...那等我改逻辑吧...
    """
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"（[^（）]*）", "", text)
        text = re.sub(r"\([^()]*\)", "", text)
    return text.strip()


def _split_for_momotalk(text: str, max_chars: int = MMT_MAX_CHUNK_CHARS) -> list[str]:
    """按标点断句，模拟手机聊天气泡。

    强断点: 。！？!?
    弱断点: ，、,;；
    省略号不参与断句。
    """
    text = text.strip()
    if not text:
        return [text]

    # 英文句尾标点 → 中文（先归一化，再合并省略号）
    text = text.replace(".", "。").replace("!", "！").replace("?", "？")
    # 合并连续句点为省略号，防止切碎
    text = re.sub(r"[。．]{2,}", "…", text)
    text = re.sub(r"…{2,}", "…", text)

    strong = _strong_split(text)
    if len(strong) <= 1 and len(text) <= max_chars:
        return [text if text else strong]

    strong = _merge_punct_segments(strong)
    if not strong:
        return [text]

    chunks: list[str] = []
    for segment in strong:
        if len(segment) <= max_chars:
            chunks.append(segment)
        else:
            chunks.extend(_split_at_weak_breaks(segment, max_chars))

    return _merge_short_chunks(chunks, max_chars)


def _process_for_momotalk(text: str) -> list[str]:
    """MomoTalk 纯文本处理器: 去括号 + 断句 → 气泡列表。"""
    return _split_for_momotalk(_strip_action_brackets(text))


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------

def _strong_split(text: str) -> list[str]:
    """在强断点（。！？!?…）处切分。

    连续强标点（！！、？！、…）看成一个整体块——只在块的最后一位
    标点后切分，保证 "你好！！" 不被拆成 ["你好！", "！"]。
    纯标点段（段首标点块）不在这里丢弃，留给 _merge_punct_segments 处理。
    """
    segments: list[str] = []
    buf = ""
    prev_strong = False
    for ch in text:
        if ch in "。！？!?…":
            buf += ch
            prev_strong = True
        else:
            if prev_strong:  # 标点块刚结束 → 结算上一段
                if buf.strip() and buf.strip() not in (".", ":"):
                    segments.append(buf.strip())
                buf = ""
            prev_strong = False
            buf += ch
    if buf.strip() and buf.strip() not in (".", ":"):
        segments.append(buf.strip())
    return segments


def _merge_punct_segments(segments: list[str]) -> list[str]:
    """把纯标点段合并进相邻文本段，宁缺勿错——不丢字符。

    仅在标点块位于段首时出现（如 "！！我们一起去天台吧。" →
    _strong_split 产出 ["！！", "我们一起去天台吧。"]）。
    旧逻辑用 _has_content 过滤会直接丢掉 "！！"，这里改为贴回下一个文本段。
    """
    out: list[str] = []
    pending = ""
    for seg in segments:
        if _has_content(seg):
            out.append(pending + seg)
            pending = ""
        else:
            pending += seg
    if pending:
        if out:
            out[-1] += pending  # 尾部纯标点（理论上少见）贴回上一段
        else:
            out.append(pending)  # 全文本都是标点
    return out


def _split_at_weak_breaks(text: str, max_chars: int) -> list[str]:
    """在逗号/分号等弱标点处拆分超长句。"""
    parts = re.split(r"(?<=[，、,;；；])", text)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return [text]

    out: list[str] = []
    buf = ""
    for part in parts:
        if len(part) <= MMT_MIN_CHUNK_CHARS:
            if buf:
                out.append(buf.strip())
                buf = ""
            out.append(part)
            continue

        if len(buf) + len(part) <= max_chars:
            buf += part
        else:
            if buf:
                out.append(buf.strip())
            if len(part) > max_chars:
                out.append(part[:max_chars])
            else:
                buf = part
    if buf:
        out.append(buf.strip())
    return out if out else [text]


def _merge_short_chunks(chunks: list[str], max_chars: int) -> list[str]:
    """合并过短 chunk，但保留独立短音节（≤4字）。"""
    if len(chunks) <= 1:
        return chunks
    merged: list[str] = []
    buf = ""
    for c in chunks:
        if len(c) <= MMT_MIN_CHUNK_CHARS:
            if buf:
                merged.append(buf.strip())
                buf = ""
            merged.append(c)
            continue
        if len(buf) + len(c) <= max_chars:
            buf += c
        else:
            if buf:
                merged.append(buf.strip())
            buf = c
    if buf:
        merged.append(buf.strip())
    return merged if merged else chunks


def _has_content(text: str) -> bool:
    """检查片段是否有实际文字内容（非纯标点/空格）。"""
    cleaned = re.sub(r"[\s\.…。！？!?,，、;；：:（）()\"'\"\"]", "", text)
    return len(cleaned) > 0


# ============================================================================
# 名字前缀处理 — MomoTalk / 羁绊剧情 共用
#
#   strip_name_prefix()        去重 LLM 自发输出的角色名前缀     [通用]
#   format_momotalk_bubble()   单气泡格式化                      [MomoTalk]
#   format_momotalk_reply()    全文格式化（多气泡 join）           [MomoTalk]
# ============================================================================

def strip_name_prefix(text: str, name: str) -> str:
    """去掉文本开头可能存在的角色名前缀。

    LLM 偶尔会自发输出 "[角色名]: xxx" 或 "角色名: xxx"，
    调用方在用自己格式加前缀之前，应先调此函数去重。

    MomoTalk / 羁绊剧情 通用。
    """
    if not name:
        return text
    for pat in [
        rf"^{re.escape(name)}\s*[：:]\s*",
        rf"^\[{re.escape(name)}[：:\s\]]*\]?\s*",
        rf"^【{re.escape(name)}】\s*",
    ]:
        text = re.sub(pat, "", text)
    return text.strip()


def format_momotalk_bubble(text: str, name: str) -> str:
    """单气泡：去重名字前缀 + 加标准 [名字]: text 格式。

    MomoTalk 专用。
    """
    clean = strip_name_prefix(text, name)
    return f"[{name}]: {clean}" if clean else ""


def format_momotalk_reply(raw_text: str, name: str) -> str:
    """全文格式化：去括号 + 断句 + 去重前缀 + [名字]: 前缀 + 换行 join。

    MomoTalk 批次模式 / 历史存储专用。
    """
    bubbles = _process_for_momotalk(raw_text)
    if not name:
        return "\n".join(bubbles)
    clean: list[str] = []
    for b in bubbles:
        b = strip_name_prefix(b, name)
        if b:
            clean.append(f"[{name}]: {b}")
    return "\n".join(clean)
