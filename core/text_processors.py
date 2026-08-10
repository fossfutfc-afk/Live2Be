"""MomoTalk 文本处理器 — 去动作括号 + 断句 + 格式化。

纯函数组，不依赖 LLM / 角色 / 会话状态。
可直接用于 MomoTalk，也可被羁绊剧情复用（仅 _strip_action_brackets）。

公开 API:
    _strip_action_brackets(text)          → str
    _split_for_momotalk(text, max_chars)  → list[str]
    _process_for_momotalk(text)           → list[str]
"""

from __future__ import annotations

import re

# MomoTalk 消息长度阈值（字符数）
MMT_MAX_CHUNK_CHARS = 30
MMT_MIN_CHUNK_CHARS = 4


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def _strip_action_brackets(text: str) -> str:
    """去除括号内的动作描写。

    MomoTalk 是手机聊天——没有"（低头）（小声）"这种舞台指示。
    循环去除最内层括号，正确处理嵌套。
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

    # 合并连续句点为省略号，防止切碎
    text = re.sub(r"[.．。]{2,}", "…", text)
    text = re.sub(r"…{2,}", "…", text)
    text = text.strip()
    if not text:
        return [text]

    strong = _strong_split(text)
    if len(strong) <= 1 and len(text) <= max_chars:
        return [text if text else strong]

    strong = [s for s in strong if _has_content(s)]
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
    """在强断点（。！？!?…）处切分。"""
    parts = re.split(r"(?<=[。！？!?…])", text)
    return [p.strip() for p in parts if p.strip() and p not in (".", ":")]


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
