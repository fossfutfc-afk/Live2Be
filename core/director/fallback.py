# -*- coding: utf-8 -*-
"""导演降级兜底 — 正则表情推断 + 默认值。

宁缺勿错: 正则猜不中 → None（上层走状态保持/默认），不硬造。
背景**无正则**（文本→地点太模糊, ~600 场景靠关键词必翻车, DESIGN_VISUAL §3）。
"""

from __future__ import annotations

import re

# 冷启动默认（渲染面无资产时映射为"无背景/纯色"）
DEFAULT_SPRITE = "nomal"
DEFAULT_BACKGROUND = "neutral"

# 情绪关键词表（按"最有区分度优先"排序, 第一个命中的胜出）。
# 值 = 正则 pattern, 只对白名单内的情绪生效（上层过滤）。
_SPRITE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("shout",    r"喊|吼|咆哮|怒吼|怒喝|炸毛|气急败坏|暴怒|音量.{0,4}(提高|增大|顶|爆)|绷不住|发作"),
    ("embarass", r"脸红|涨红|羞|窘|不好意思|难为情|扭捏|尴尬|掩面|支支吾吾|结巴"),
    ("serious",  r"严肃|认真|板着脸|眉头(紧锁|皱)|正色|郑重|冷静|正经|神情专注"),
    ("smile",    r"笑|微笑|开心|高兴|雀跃|愉快|得意|眉眼弯弯|忍俊不禁|轻哼"),
    ("respond",  r"点头|应声|应答|附和|回应|嗯嗯|低声应答"),
)


def infer_sprite(text: str, emotions: list[str] | set[str] | None = None) -> str | None:
    """从段落文本正则推断情绪（只返回白名单内的值）。

    Args:
        text:     本场段落拼接文本。
        emotions: 角色情绪白名单（catalog.sprite_emotions）; None → 不过滤。

    Returns:
        推断到的情绪名; 猜不中 / 猜中但不在白名单 → None（宁缺勿错）。
    """
    if not text:
        return None
    whitelist = set(emotions) if emotions else None
    for emotion, pattern in _SPRITE_PATTERNS:
        if whitelist is not None and emotion not in whitelist:
            continue
        if re.search(pattern, text):
            return emotion
    return None
