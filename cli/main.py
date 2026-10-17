"""
Live2Be — LLM驱动的角色互动故事生成器

CLI 入口: 玩家名引导 → MomoTalk 角色选择 + 对话循环

对话循环骨架, 其余（角色选择 / 命令模块 / 玩家名）在 core/mmt/mmt_preset.py。
"""

from __future__ import annotations

import logging
import sys

from cli.vn_cli import run_bond_story_vn, wrapup_after_vn
from core.mmt.engine import MomoTalkEngine
from core.mmt.mmt_preset import (
    LoopResult,
    ensure_player_name,
    handle_command,
    load_player_name,
    select_character,
)
from core.session import SessionStore
from core.streaming import simulate_steps
from llm.client import LLMClient
from llm.image_gen import ImageGenerator

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
            # 每次重读玩家名（/name 改完后下一行立刻生效）
            user_input = input(f"{load_player_name()}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        if not user_input:
            continue

        # ── 命令分发（mmt_preset 命令模块）──
        if user_input.startswith("/"):
            action = handle_command(user_input, engine)
            if action is not None:
                return action
            continue

        # ── 正常对话（全 JSON 动作 loop）──
        try:
            print()  # 换行，准备输出角色回复
            result = engine.agent_turn(user_input)
            simulate_steps(result.steps)          # …打字指示 + 气泡, 依序渲染
            if result.bond_story:
                print(f"\n[系统] 与 {display_name} 进入了羁绊剧情时刻……")
                # store 必须传: 不传则整章剧情不落事件流（收尾链全在 `if store is not None` 里）
                completed = run_bond_story_vn(
                    engine, image_gen=ImageGenerator(), store=engine._store)  # VN 循环; 【完】/b 退出后回到正常对话
                if completed:
                    wrapup_after_vn(engine, completed=True)   # 剧情走到【完】→ AI 就剧情在手机上回几段话
            print()  # 回复结束，额外空行
        except Exception as e:
            print(f"\n[系统] 对话失败: {e}")
            print("[系统] 请检查网络连接和 API Key。输入 /exit 退出。\n")

    # 正常退出 → 自动保存
    engine.save_session()
    return LoopResult.EXIT


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

    engine = MomoTalkEngine("config/characters", client, store=SessionStore())
    # 玩家名只系统显示（提示符/再见语都实时读 player.json, 不缓存局部变量——
    # 菜单 [N] 改名后即刻生效）, 不注入 system prompt——学生不会直呼自定义名
    ensure_player_name()                        # 首次运行询问玩家名（null → sensei）

    while True:
        char_id = select_character(engine)
        if char_id is None:
            print(f"\n[系统] 再见，{load_player_name()}。")
            break

        try:
            name = engine.start_session(char_id)
            # 事件流会话（保存/恢复, docs/archive/DESIGN_SAVE.md §4）: 每角色新对话 = 新会话
            root = engine._store.create(char_id, name)
            engine.attach_session(root.session_id)
            print(f"\n[系统] 正在与 {name} 对话...")
            comp = engine.current_character.completeness
            print(f"[系统] 信息完整度: {comp['ratio']:.0%}")
        except Exception as e:
            print(f"\n[系统] 加载角色失败: {e}")
            input("\n按 Enter 继续...")
            continue

        # 提示未结束会话（/resume 查看全部）
        try:
            opens = engine._store.list_open()
            if opens:
                print(f"[系统] 有 {len(opens)} 个未结束会话（输入 /resume 可恢复）")
        except Exception:
            pass

        result = _chat_loop(engine)
        if result == LoopResult.EXIT:
            print(f"\n[系统] 再见，{load_player_name()}。")
            break
        # result == LoopResult.BACK → 回到角色选择继续循环

    engine.llm.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    main()
