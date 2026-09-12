# -*- coding: utf-8 -*-
"""**已退役（2026-09-12, 决策 #39）：主链不再调用**，模块留档供考古/复活参考。

退役原因：它嗅的是 v1 动作 `"action":"memorial_enter"` 的 `prompt` 字段——记录流 v2
里不存在这种输出，于是**纪念生图永远不会触发**（真机实测：整章不出图）。
v2 的等价物 = 引擎在**一行 `stage:memorial` 解析出来时**就回调
（`BondStoryEngine._fire_memorial_image`，prompt = 块级 `art` 意向 → 缺省退化触发句，
且只在真出现 memorial 时才开画）。v2 行为的用例：
`tests/core/test_vn_records_engine.py::test_memorial_fires_image_hook_with_art_intent`
与 B 层冒烟"纪念链路"步骤；本模块自身的 v1 用例已归档到 `tests/archive/`。

---- 以下为原始说明（v1, 2026-09-01）----

MEMORIAL 流式嗅探探针（方案 A）— 流式输出中提前捕获生图 prompt。

目标: LLM 在输出 memorial_enter 动作时, `prompt` 字段一旦**定稿**（JSON 字符串
值引号闭合）就触发回调 → 生图与 LLM 剩余输出（paragraphs/choices）并行——
玩家看到纪念场景时图已就绪, 干等点消失。

正确性根基: JSON 字符串值闭合 = 该字段不会再变——"闭合即定稿"。

策略（不做完整 JSON 解析, 只扫两个字段）:
    1. 确认 action 字段值 == "memorial_enter"（防误触发——只在目标动作下关注 prompt）
    2. 找 prompt 字段值, 引号闭合 → 触发一次回调 → 之后不再触发

字段顺序约定（payload_schema/示例已天然如此）: action → payload → prompt →
paragraphs——prompt 紧跟 action, 触发点最早。LLM 乱序（prompt 先到）→ action
确认后立即触发（值已闭合, 不亏）; 乱序到 action 最后 → 退化为整段输出后触发
（等于现状, 无损失）。一切"找不全/值未闭合"状态都是等待, 永不误触发非目标动作。

失败语义: 触发后动作仍可能被契约校验拒绝（频率限制/坏 JSON → 重试）——已触发的
生图作废（接受浪费, 宁缺勿错）。空 prompt 值 → 动作必失败, 不触发。
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


def _find_key_string(buf: str, key: str) -> str | None:
    """在累积文本中找 `"key": "值"` 的字符串值。

    返回:
        值（值已闭合, 不含引号, 转义已还原）;
        None = 键未找到, 或值尚未闭合（调用方下次 feed 重扫, 幂等）。
    只特殊处理 \\" 与 \\\\ 转义; 其余 \\x 按字面保留（LLM 输出中罕见, 无害）。
    """
    idx = 0
    while True:
        pos = buf.find(f'"{key}"', idx)
        if pos == -1:
            return None
        j = pos + len(key) + 2
        while j < len(buf) and buf[j] in " \t\r\n":
            j += 1
        if j >= len(buf) or buf[j] != ":":
            idx = pos + len(key) + 2          # 同名键误匹配（罕见）→ 继续找
            continue
        j += 1
        while j < len(buf) and buf[j] in " \t\r\n":
            j += 1
        if j >= len(buf) or buf[j] != '"':
            idx = pos + len(key) + 2
            continue
        j += 1                               # 值首引号后

        # 扫描字符串值到闭合引号（处理转义）
        out: list[str] = []
        while j < len(buf):
            c = buf[j]
            if c == "\\":
                if j + 1 >= len(buf):
                    return None              # 反斜杠悬在末尾——值未闭合
                nxt = buf[j + 1]
                if nxt == '"' or nxt == "\\":
                    out.append(nxt)
                    j += 2
                    continue
                out.append(c)
                out.append(nxt)
                j += 2
                continue
            if c == '"':
                return "".join(out)
            out.append(c)
            j += 1
        return None                          # 流还没到闭合引号——继续等


class MemorialProbe:
    """流式嗅探器: feed(token 增量) → 检测到 memorial_enter 的 prompt 定稿即触发回调。

    用法（挂到 send_vn_scene 的流式收集）:
        probe = MemorialProbe(on_memorial_prompt=cb)
        for chunk in chat_full(..., on_chunk=probe.feed): ...
    """

    def __init__(self, on_memorial_prompt: Callable[[str], None]):
        self._cb = on_memorial_prompt
        self._buf = ""
        self._active = False       # True = 已确认目标是 memorial_enter, 继续找 prompt
        self._fired = False        # 已触发过（只触发一次）

    def feed(self, chunk: str) -> None:
        """喂一个 token 增量。触发回调时已捕获异常（回调异常不打断流式收集）。"""
        if self._fired or not chunk:
            return
        self._buf += chunk

        if not self._active:
            action = _find_key_string(self._buf, "action")
            if action is None:
                return                           # 未确认动作——继续等
            if action.strip() != "memorial_enter":
                self._active = True              # 已判定非目标——不再找（防误触发）
                self._fired = True               # 该动作不再触发, 永久静默
                return
            self._active = True

        prompt = _find_key_string(self._buf, "prompt")
        if prompt is None:
            return                               # prompt 未闭合——继续等
        if not prompt.strip():
            self._fired = True                   # 空 prompt → 动作必失败, 不触发
            return
        self._fired = True
        try:
            self._cb(prompt.strip())
        except Exception as e:                   # noqa: BLE001 — 回调异常不炸流
            logger.warning("memorial probe 回调异常（忽略, 生图降级）: %s", e)

    def reset(self) -> None:
        """清空状态（LLM 重试时复用——新输出重新嗅探）。"""
        self._buf = ""
        self._active = False
        self._fired = False

    @property
    def fired(self) -> bool:
        """是否已触发（测试断言用）。"""
        return self._fired
