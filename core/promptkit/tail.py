"""每轮动态尾装配（DESIGN_PROMPTKIT §2/§3 tail.py）——唯一每轮装配入口。

槽位协议:
    [system(盒 + brain 段)] + history + [约束注记们(system)] + [Task 卡] + [user]

不变式:
    · system 首串跨轮逐字节稳定（brain 段变化是唯一例外, digest 后下轮生效）
    · 动态一切发生在 history 之后
    · 注记/卡只进 LLM context, 不入历史（调用方自行保证——历史在调用前已定型）
"""
from __future__ import annotations

from typing import Iterable


def round_messages(
    *,
    system: str,
    user: str,
    history: list[dict] | None = None,
    notes: Iterable[str | None] = (),
    brain: str = "",
) -> list[dict]:
    """拼装一轮的完整 messages。

    Args:
        system: 会话级盒（build_box 输出）
        brain:  记忆注入段（动态拼装, 追加在 system 内容尾部; digest 后下轮生效）
        history: 历史（live 引擎自增或 resume 预灌窗口）——原样引用, 不改写
        notes:  约束注记们（P16 羁绊进度 / P17 系统注记 / P18 随机事件…按序）
        user:   本回合用户输入（最后的 user 消息）
    """
    messages: list[dict] = []
    content = system
    if brain and brain.strip():
        content += "\n\n" + brain.strip()
    messages.append({"role": "system", "content": content})
    if history:
        messages.extend(history)
    for note in notes:                      # 原样追加（不 strip）——与引擎旧内联行为一致
        if not note:
            continue
        messages.append({"role": "system", "content": str(note)})
    messages.append({"role": "user", "content": user})
    return messages
