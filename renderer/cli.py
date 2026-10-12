"""CLI 输出 — RenderOutput → 终端渲染（DESIGN_RENDERER.md §八, 迁移自 `apps/vn_cli.py`）。

消费 RenderOutput（平台无关）——背景标签 / per-para 表情标注 / 特效符号 / 打字机 / 选项:
    - 背景变化 → `[背景 xxx]` 标签（CLI 无动画, 只标注; transition 忽略）
    - 段落带 emotion（显式标注的）→ `[表情 xxx]`; 延续的段静默
    - 段落带 inner（A 版内心戏）→ 分隔线 + 变暗近似（· 分隔）
    - 特效 → `[✨ 特效名]` 符号标注（文本流不破坏）
    - 打字机: 逐字输出, 任意键跳过; char_ms=0 直接全文（测试）
    - 选项: 编号 1..N 打印 + b 退出; 输入回传选择文本

本模块只管"怎么显示"——不做剧情决策; 选项交互的结果由调用方喂回引擎。
"""
from __future__ import annotations

import sys
import time

from renderer.core import RenderOutput

#: 打字节奏（毫秒/字）; 测试传 char_ms=0 跳过动画（公开——vn_cli 签名默认引用）
PARA_CHAR_MS = 40

#: 特效符号（CLI 降级——文本流不破坏; 未知特效 → ✨ 通用符号）
_FX_SYMBOLS = {
    "sparkle": "✨",
    "blush": "🌸",
    "notes": "♪",
    "anger": "💢",
    "raindrop": "💧",
    "bang": "❗",
    "heart": "💗",
    "sweat": "💦",
}
_FX_FALLBACK = "✨"


def _kbhit() -> bool:
    """是否有点击任意键（Windows 用 msvcrt; 其他平台无法阻塞探测 → False）。"""
    try:
        import msvcrt
        return bool(msvcrt.kbhit())
    except ImportError:
        return False


def _drain_input() -> None:
    """清空键盘缓冲——跳过动画时按下的 Enter 不能污染下一个 input()。"""
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    except ImportError:
        pass


def type_paragraph(text: str, char_ms: int = PARA_CHAR_MS) -> None:
    """逐字打字渲染一段; char_ms<=0 直接全文, 打字期间任意键跳过。"""
    if char_ms <= 0:
        print(text, end="", flush=True)
        print()
        return
    printed = 0
    for ch in text:
        print(ch, end="", flush=True)
        printed += 1
        if _kbhit():                      # 跳过动画 → 补全剩余文本
            _drain_input()
            print(text[printed:], end="", flush=True)
            break
        time.sleep(char_ms / 1000.0)
    print()  # 段落结束换行


def _fx_symbol(effects: list[str]) -> str:
    """特效列表 → 符号串（多特效叠加; 空 → ""）。"""
    if not effects:
        return ""
    return "".join(_FX_SYMBOLS.get(fx, _FX_FALLBACK) for fx in effects)


def _print_visual(output: RenderOutput) -> None:
    """场景级视觉标签（背景切换; 纯文本模式无变化 → 不打印）。"""
    bg = output.background
    if bg.changed and bg.scene_id:
        print(f"[背景 {bg.scene_id}]")


def render_scene(output: RenderOutput, *, char_ms: int = PARA_CHAR_MS) -> None:
    """渲染一个场景到终端（视觉标签 + 段落 + 特效 + 选项/收尾）。

    选项与输入交互不在本函数——调用方按 output.choices 自行决定交互方式
    （live 等玩家选 / replay 只展示 picked）。此处只渲染。
    """
    _print_visual(output)
    for i, para in enumerate(output.paragraphs):
        if isinstance(para, dict):
            inner = para.get("inner")
            if isinstance(inner, str) and inner.strip():
                print("\n" + "·" * 36 + "  (内心)  " + "·" * 36)
                type_paragraph(inner.strip(), char_ms)
                print("\n" + "·" * 36 + "  (回到现实)  " + "·" * 36)
            emotion = para.get("emotion")
            # 段落显式带 emotion 才标注; 延续的段静默（渲染端默认/继承表情）
            if isinstance(emotion, str) and emotion.strip():
                print(f"[表情 {emotion}]")
            # 说话人（记录流 v2 最小形态）: speaker_name 优先（后端映射的显示名）,
            # 退而用记录原值（角色 id / sensei）; 旁白无名字行
            name = para.get("speaker_name")
            if not (isinstance(name, str) and name.strip()):
                raw_speaker = para.get("speaker")
                name = raw_speaker if isinstance(raw_speaker, str) else ""
            if isinstance(name, str) and name.strip():
                print(f"— {name.strip()} —")
            text = para.get("text", "")
        else:
            text = str(para)
        fx = _fx_symbol(output.effects[i]) if i < len(output.effects) else ""
        if fx:
            print(f"[{fx}]")
        type_paragraph(text, char_ms)

    if output.is_end:
        print("\n── 羁绊剧情结束 ──")


def render_choices(choices: list[str], *, picked: str | None = None) -> None:
    """渲染选项列表。picked（回放）→ 高亮标注玩家当时的选择, 不可重选。"""
    if not choices:
        return
    print("\n")
    for i, choice in enumerate(choices, 1):
        mark = "  ←（当时的选择）" if picked is not None and choice == picked else ""
        print(f"  [{i}] {choice}{mark}")
    if picked is None:
        print("  [b] 退出")


def read_choice(choices: list[str], input_fn=input) -> str | None:
    """live 选项交互: 编号选择 → 选项文本; b/Ctrl-D → None（退出 VN）。"""
    while True:
        try:
            raw = input_fn("选择: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if raw.lower() == "b":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        print("  无效选择, 请再试")


def read_free_input(input_fn=input) -> str | None:
    """live 无选项推进: 玩家自由输入一句话; b/Ctrl-D → None（退出 VN）。"""
    try:
        raw = input_fn("（输入一句话推进剧情, b 退出）: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return None if raw.lower() == "b" else raw
