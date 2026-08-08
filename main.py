"""
Live2Be — LLM驱动的角色互动故事生成器

CLI 入口: MomoTalk 角色选择 + 对话循环
"""

from __future__ import annotations

import logging
import sys
from enum import Enum
from pathlib import Path

from llm.client import LLMClient
from core.momotalk import MomoTalkEngine

# ---------------------------------------------------------------------------
# 对话循环结果
# ---------------------------------------------------------------------------

class LoopResult(Enum):
    EXIT = "exit"          # 退出程序
    BACK = "back"          # 返回角色选择


# ---------------------------------------------------------------------------
# 角色选择
# ---------------------------------------------------------------------------

def _select_character(engine: MomoTalkEngine) -> str | None:
    """展示角色列表并让用户选择。返回角色 ID 或 None（退出）。"""
    chars = engine.char_loader.list_characters()

    if not chars:
        print("\n[系统] 没有找到任何角色。")
        print("请在 config/characters/ 下添加角色文件夹（至少含 profile.yml）。")
        input("\n按 Enter 退出...")
        return None

    print("\n" + "═" * 40)
    print("          MomoTalk — 角色选择")
    print("═" * 40)

    ids = list(chars.keys())
    for i, char_id in enumerate(ids, 1):
        print(f"  [{i}] {chars[char_id]}")

    print(f"  [0] 退出")
    print()

    while True:
        choice = input("选择角色 (数字): ").strip()
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ids):
                return ids[idx]
            print(f"请输入 1-{len(ids)} 之间的数字，或 0 退出。")
        except ValueError:
            print("请输入数字。")


# ---------------------------------------------------------------------------
# 对话循环
# ---------------------------------------------------------------------------

def _chat_loop(engine: MomoTalkEngine) -> LoopResult:
    """对话循环。"""
    display_name = engine.current_character.display_name

    print("\n" + "═" * 40)
    print(f"  正在与 {display_name} 对话中")
    print("  输入 /help 查看命令")
    print("═" * 40)
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        if not user_input:
            continue

        # ── 命令分发 ──
        if user_input.startswith("/"):
            action = _handle_command(user_input, engine)
            if action is not None:
                return action
            continue

        # ── 正常对话 ──
        try:
            reply = engine.send_message(user_input)
            print(f"\n{display_name}: {reply}\n")
        except Exception as e:
            print(f"\n[系统] LLM 调用失败: {e}")
            print("[系统] 请检查网络连接和 API Key。输入 /exit 退出。\n")

    # 正常退出 → 自动保存
    engine.save_session()
    return LoopResult.EXIT


def _handle_command(raw: str, engine: MomoTalkEngine) -> LoopResult | None:
    """处理 /xxx 命令。返回 LoopResult 时退出循环，None 时继续。"""
    parts = raw[1:].lower().split()
    if not parts:
        return None
    cmd = parts[0]

    if cmd == "exit":
        engine.save_session()
        return LoopResult.EXIT

    if cmd == "save":
        path = engine.save_session()
        print(f"[系统] 会话已保存: {path}")
        return None

    if cmd == "back":
        engine.save_session()
        print("[系统] 已保存，返回角色选择...")
        return LoopResult.BACK

    if cmd == "help":
        print(HELP_TEXT)
        return None

    if cmd == "history":
        _print_history(engine)
        return None

    if cmd == "char":
        _print_char_info(engine)
        return None

    print(f"[系统] 未知命令: /{cmd}。输入 /help 查看可用命令。")
    return None


# ---------------------------------------------------------------------------
# 辅助显示
# ---------------------------------------------------------------------------

def _print_history(engine: MomoTalkEngine) -> None:
    h = engine.history
    if not h:
        print("[系统] 当前没有对话历史。")
        return
    print(f"\n{'─' * 30} 对话历史 ({len(h)} 条) {'─' * 30}")
    for msg in h:
        role = "You" if msg["role"] == "user" else engine.current_character.display_name
        content = msg["content"]
        print(f"  {role}: {content[:80]}{'...' if len(content) > 80 else ''}")
    print("─" * 60 + "\n")


def _print_char_info(engine: MomoTalkEngine) -> None:
    char = engine.current_character
    if char is None:
        return
    comp = char.completeness
    print(f"\n  ── 角色信息 ──")
    print(f"  名称: {char.display_name}")
    print(f"  官方角色: {'是' if char.is_official else '否'}")
    print(f"  信息完整度: {comp['score']}/{comp['total_sig']} ({comp['ratio']:.0%})")
    if comp["missing_sig"]:
        print(f"  缺失重要字段: {', '.join(comp['missing_sig'])}")
    print(f"  当前对话轮数: {engine.history_length // 2}")
    print()


HELP_TEXT = """
  ── MomoTalk 命令 ──
  /help     显示此帮助
  /save     保存当前对话
  /history  显示对话历史摘要
  /char     显示当前角色信息
  /back     保存并返回角色选择
  /exit     保存并退出程序
"""


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> None:
    print("═" * 50)
    print("  Live2Be — LLM 角色互动故事生成器")
    print("  MomoTalk v0.1")
    print("═" * 50)

    try:
        client = LLMClient()
    except ValueError as e:
        print(f"\n[错误] {e}")
        input("\n按 Enter 退出...")
        sys.exit(1)

    engine = MomoTalkEngine("config/characters", client)

    while True:
        char_id = _select_character(engine)
        if char_id is None:
            print("\n[系统] 再见，sensei。")
            break

        try:
            name = engine.start_session(char_id)
            print(f"\n[系统] 正在与 {name} 对话...")
            comp = engine.current_character.completeness
            print(f"[系统] 信息完整度: {comp['ratio']:.0%}")
        except Exception as e:
            print(f"\n[系统] 加载角色失败: {e}")
            input("\n按 Enter 继续...")
            continue

        result = _chat_loop(engine)
        if result == LoopResult.EXIT:
            print("\n[系统] 再见，sensei。")
            break
        # result == LoopResult.BACK → 回到角色选择继续循环

    engine.llm.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    main()
