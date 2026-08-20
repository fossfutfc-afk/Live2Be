"""MomoTalk CLI 预设模块 — 角色选择 / 命令 / 玩家名。

从 main.py 拆出的 CLI 侧逻辑, 让 main.py 只留对话循环骨架:
    LoopResult / select_character   选择哪个角色参与对话（角色选择菜单）
    handle_command / print_history / print_char_info / HELP_TEXT
                                    命令指令模块（/save /back /help /history
                                    /char /name /exit）
    load_player_name / save_player_name / ensure_player_name / set_player_name
                                    玩家名系统

玩家名系统:
    data/basic/player.json = {"player_name": "<名字> | null"}
    player_name 为 null / 缺失 / 空 → 默认 "sensei"。
    ensure_player_name 只在首次（null/缺失）时询问并保存; 已设置则直接返回。
    菜单 [N] 或 /name 可随时查看/修改, 下次会话生效（system prompt 的玩家称呼
    在会话开始定）。

名字校验（避免 RP 崩 / 序列化混淆）:
    - 角色名冲突: 名字规范化（去空白）后与已建档角色显示名相等 → 拒绝
      （如 "陆八魔阿露"、"伊草遥香"——取角色名会把对话搞混）
    - 保留词: null / true / false → 拒绝（序列化语义混淆）
    - 超长: >20 字 → 拒绝
    即使绕开校验直接写 JSON（如手工改文件）, json.dumps 保证存储安全:
    null/true/引号/换行 都作为普通字符串存取, 不会崩掉 JSON。

用法:
    from core.mmt.mmt_preset import (
        LoopResult, select_character, handle_command, ensure_player_name,
    )
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from core.momotalk import MomoTalkEngine

# 玩家名存储（cwd 相对项目根, 与 SESSION_DIR 同惯例）
PLAYER_JSON = Path("data/basic/player.json")
DEFAULT_PLAYER_NAME = "sensei"
MAX_NAME_LEN = 20
# 序列化语义保留词: 直接禁用, 避免与 JSON null/布尔 混淆
RESERVED_WORDS = frozenset({"null", "true", "false"})


class LoopResult(Enum):
    EXIT = "exit"          # 退出程序
    BACK = "back"          # 返回角色选择


# ============================================================================
# 角色选择 — 哪个角色参与对话
# ============================================================================

def select_character(engine: MomoTalkEngine, input_fn=input) -> str | None:
    """展示角色列表并让用户选择。返回角色 ID 或 None（退出）。

    菜单含 [N] 玩家名入口（输入/更改, 改完重绘菜单）。
    Ctrl-D / Ctrl-C → 退出。
    """
    chars = engine.char_loader.list_characters()

    if not chars:
        print("\n[系统] 没有找到任何角色。")
        print("请在 config/characters/ 下添加角色文件夹（至少含 profile.yml）。")
        input("\n按 Enter 退出...")
        return None

    ids = list(chars.keys())
    while True:
        print("\n" + "═" * 40)
        print("          MomoTalk — 角色选择")
        print("═" * 40)
        for i, char_id in enumerate(ids, 1):
            print(f"  [{i}] {chars[char_id]}")
        print(f"  [N] 玩家名（当前: {load_player_name()}）")
        print(f"  [0] 退出")
        print()

        try:
            choice = input_fn("选择角色 (数字 / N=玩家名 / 0=退出): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[系统] 退出。")
            return None
        if choice == "0":
            return None
        if choice.lower() == "n":
            set_player_name(engine, input_fn=input_fn)
            continue                    # 名字可能已变, 重绘菜单
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ids):
                return ids[idx]
            print(f"请输入 1-{len(ids)} 之间的数字、N 或 0。")
        except ValueError:
            print("请输入数字、N 或 0。")


# ============================================================================
# 玩家名系统
# ============================================================================

def _read_player_data() -> dict:
    """读 data/basic/player.json; 缺失/损坏 → {}。"""
    try:
        data = json.loads(PLAYER_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_player_name() -> str:
    """玩家名; player_name 为 null/缺失/空 → 默认 sensei。

    字符串 "null"/"true"/引号 等照常返回（它们是名字, 不是 JSON 语义值）。
    """
    name = _read_player_data().get("player_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return DEFAULT_PLAYER_NAME


def has_player_name() -> bool:
    """是否已设置过玩家名（player_name 为非空字符串）。"""
    name = _read_player_data().get("player_name")
    return isinstance(name, str) and bool(name.strip())


def save_player_name(name: str) -> None:
    """写 data/basic/player.json。json.dumps 保证任意输入安全转义。"""
    PLAYER_JSON.parent.mkdir(parents=True, exist_ok=True)
    PLAYER_JSON.write_text(
        json.dumps({"player_name": name}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _norm_name(name: str) -> str:
    """规范化: 去全部空白（'伊草 遥香' → '伊草遥香'）。"""
    return "".join(str(name).split())


def _name_problem(name: str, engine: MomoTalkEngine) -> str | None:
    """名字校验: 返回问题描述; None = 可用。"""
    if len(name) > MAX_NAME_LEN:
        return f"名字太长（≤{MAX_NAME_LEN} 字）"
    if name in RESERVED_WORDS:
        return f"『{name}』是保留词, 不能用作名字"
    norm = _norm_name(name)
    if norm:
        for display in engine.char_loader.list_characters().values():
            if norm == _norm_name(display):
                return (f"『{display}』是已有角色的名字——"
                        "取角色名会把对话搞混")
    return None


def set_player_name(engine: MomoTalkEngine, input_fn=input) -> str:
    """交互式输入/更改玩家名（菜单 N 入口）。留空取消; 校验通过才保存。

    Ctrl-D / Ctrl-C → 取消（保持原名）。
    """
    while True:
        try:
            name = input_fn(
                f"你的名字（当前: {load_player_name()}，留空取消）: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[系统] 已取消。")
            return load_player_name()
        if not name:
            print("[系统] 未修改。")
            return load_player_name()
        problem = _name_problem(name, engine)
        if problem:
            print(f"[系统] {problem}，请换个名字。")
            continue
        save_player_name(name)
        print(f"[系统] 已保存，角色将称呼你为: {name}")
        return name


def ensure_player_name(engine: MomoTalkEngine, input_fn=input) -> str:
    """首次运行设置玩家名: 未设置时询问并保存, 已设置直接返回。

    留空 / Ctrl-D → 默认 sensei; 校验失败（角色名/保留词）→ 重新询问。
    """
    if has_player_name():
        return load_player_name()
    print("\n[系统] 首次对话——你希望角色怎么称呼你？（留空默认 sensei）")
    while True:
        try:
            name = input_fn("你的名字: ").strip()
        except (EOFError, KeyboardInterrupt):
            name = DEFAULT_PLAYER_NAME
            print(f"\n[系统] 已采用默认称呼: {DEFAULT_PLAYER_NAME}")
            break
        if not name:
            name = DEFAULT_PLAYER_NAME
            break
        problem = _name_problem(name, engine)
        if problem:
            print(f"[系统] {problem}，请换个名字。")
            continue
        break
    save_player_name(name)
    print(f"[系统] 已保存，角色将称呼你为: {name}\n")
    return name


# ============================================================================
# 命令指令模块
# ============================================================================

HELP_TEXT = """
  ── MomoTalk 命令 ──
  /help     显示此帮助
  /save     保存当前对话
  /history  显示对话历史摘要
  /char     显示当前角色信息
  /name     查看/修改你的称呼（下次会话生效）
  /back     保存并返回角色选择
  /exit     保存并退出程序
"""


def print_history(engine: MomoTalkEngine) -> None:
    """显示对话历史摘要。"""
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


def print_char_info(engine: MomoTalkEngine) -> None:
    """显示当前角色信息。"""
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


def handle_command(raw: str, engine: MomoTalkEngine) -> LoopResult | None:
    """处理 /xxx 命令。返回 LoopResult 时退出循环, None 时继续。"""
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
        print_history(engine)
        return None

    if cmd == "char":
        print_char_info(engine)
        return None

    if cmd == "name":
        rest = raw[1:].strip()
        new_name = rest[len(cmd):].strip()
        if not new_name:
            print(f"[系统] 当前称呼: {load_player_name()}。用法: /name 新名字")
            return None
        problem = _name_problem(new_name, engine)
        if problem:
            print(f"[系统] {problem}")
            return None
        save_player_name(new_name)
        print(f"[系统] 称呼已改为: {new_name}（下次会话生效）")
        return None

    print(f"[系统] 未知命令: /{cmd}。输入 /help 查看可用命令。")
    return None
