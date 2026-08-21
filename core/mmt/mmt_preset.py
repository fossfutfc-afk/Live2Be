"""MomoTalk CLI 预设模块 — 角色选择 / 命令 / 玩家名。

从 main.py 拆出的 CLI 侧逻辑, 让 main.py 只留对话循环骨架:
    LoopResult / select_character   选择哪个角色参与对话（角色选择菜单）
    handle_command / print_history / print_char_info / HELP_TEXT
                                    命令指令模块（/save /back /help /history
                                    /char /name /exit）
    load_player_name / save_player_name / ensure_player_name / set_player_name
    name_confirm                         取名确认 / 角色名彩蛋
                                    玩家名系统

玩家名系统:
    data/basic/player.json = {"player_name": "<名字> | null"}
    player_name 为 null / 缺失 / 空 → 默认 "sensei"。
    ensure_player_name 只在首次（null/缺失）时询问并保存; 已设置则直接返回。
    菜单 [N] 或 /name 可随时查看/修改。名字只做系统显示（终端提示符 / 菜单 /
    存档标识）——不注入 system prompt, 学生不会直呼玩家自定义名, 一直称呼"老师"。

名字校验（防序列化混淆 / 显示异常）:
    - 保留词: null / true / false → 拒绝（序列化语义混淆）
    - 超长: >20 字 → 拒绝
    - 符号白名单: 只允许文字/数字/_·ー〜～/空格, 其余符号拒绝
      （引号/尖括号/方括号/emoji/零宽/控制符, 防气泡格式破坏与 prompt 污染）
    角色名不再禁止——LLM 不知道玩家自取的名字, 名字与角色相近反而像人类
    操作; 取角色名由 name_confirm 彩蛋兜住, 不是 RP 崩。
    即使绕开校验直接写 JSON（如手工改文件）, json.dumps 保证存储安全:
    null/true/引号/换行 都作为普通字符串存取, 不会崩掉 JSON。

取名确认 / 彩蛋（name_confirm）:
    校验通过后进入确认环节。config/eggs/namegg.json = {正则: [回复,...]},
    任一别名命中玩家名（如取了角色昵称"阿露"）→ 随机弹一条该角色彩蛋台词,
    然后常规 y/n 确认。回复可带前缀控制动作: RJ~ 玩笑式拒绝（只给 (n/n)
    选项, 无论选什么都拒绝）; AC~ 接受。英文别名整词匹配（koharu 不误命中
    aru）, 中文/假名子串匹配。未命中 → 常规确认「名字是『xx』吗?」。
    namegg.json 缺失/损坏 → 打印错误后降级为常规确认, 不阻塞改名。

用法:
    from core.mmt.mmt_preset import (
        LoopResult, select_character, handle_command, ensure_player_name,
    )
"""

from __future__ import annotations

import json
import random
import re
import unicodedata
from enum import Enum
from pathlib import Path

from core.momotalk import MomoTalkEngine
from errors import err

# 玩家名存储（cwd 相对项目根, 与 SESSION_DIR 同惯例）
PLAYER_JSON = Path("data/basic/player.json")
DEFAULT_PLAYER_NAME = "sensei"
MAX_NAME_LEN = 20
# 序列化语义保留词: 直接禁用, 避免与 JSON null/布尔 混淆
RESERVED_WORDS = frozenset({"null", "true", "false"})
# 名字彩蛋动作
ACCEPT_NAMING = "AC~"
REJECT_NAMING = "RJ~"
# 回复肯定列表
ACCEPT_REPLIES = ("y", "yes", "是", "", "t", "true", "1")

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
            set_player_name(input_fn=input_fn)
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


# 名字允许的字符: 文字/数字/下划线 + 少量昵称符号 + 空格（其余一律拒绝）。
# 白名单式（宁缺勿错）——奇形怪状的符号不用逐个列举, 白名单之外全拒。
_ALLOWED_CATEGORIES = frozenset({"Lu", "Ll", "Lt", "Lm", "Lo", "Nd", "Pc"})
#   Lu/Ll/Lt/Lm/Lo = 字母（含汉字/假名/谚文/注音）; Nd = 数字; Pc = 下划线
_ALLOWED_EXTRA = frozenset("·ー〜～ ")
#   · 间隔号（星野·爱） ー 长音符（アイシー） 〜～ 波形昵称符  空格（星野 爱）


def _bad_char(name: str) -> str | None:
    """返回第一个不允许的字符; 全合法则 None。

    被拒的典型: 引号/反斜杠（JSON 混淆）、尖括号/反引号（渲染解析）、
    方括号（[名字]: 气泡格式冲突）、emoji/特殊符号（奇形怪状）、
    零宽字符/控制符（显示异常、肉眼不可见）。
    """
    for ch in name:
        if ch in _ALLOWED_EXTRA:
            continue
        if unicodedata.category(ch) in _ALLOWED_CATEGORIES:
            continue
        return ch
    return None


def _name_problem(name: str) -> str | None:
    """名字校验: 返回问题描述; None = 可用。

    角色名不再禁止（曾用 engine 比对角色显示名, 已移除）——LLM 不知道
    玩家自取的名字, 名字与角色相近反而像人类操作; 取角色名由 name_confirm
    的正则彩蛋兜住（config/eggs/namegg.json）。
    """
    if len(name) > MAX_NAME_LEN:
        return f"名字太长（≤{MAX_NAME_LEN} 字）"
    if name in RESERVED_WORDS:
        return f"『{name}』是保留词, 不能用作名字"
    bad = _bad_char(name)
    if bad is not None:
        return f"名字含不允许的符号『{bad}』"
    return None


# ============================================================================
# 取名确认 / 角色名彩蛋（config/eggs/namegg.json）
# ============================================================================

def _load_namegg() -> dict:
    """读 config/eggs/namegg.json（角色名彩蛋数据）。缺失/损坏抛 err 异常。

    格式: {正则: [回复1, 回复2, ...]}; 任一正则命中玩家名 → 随机一条彩蛋。
    """
    path = Path("config/eggs/namegg.json")
    if not path.exists():
        raise FileNotFoundError(err("NotFound", f"档案不存在: {path}"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(err("InvalidJson", f"{path.name} 读取失败: {e}")) from e
    if not isinstance(data, dict):
        raise ValueError(err("InvalidJson", f"{path.name} 内容不是有效 Json dict"))
    return data


def _is_ascii(s: str) -> bool:
    """纯 ASCII 判定（英文 ID/昵称别名用整词匹配）。"""
    return all(ord(c) < 128 for c in s)


def _egg_pattern_matches(pattern: str, name: str) -> bool:
    """namegg 别名匹配: key 按 | 切分, 任一别名命中即 True。

    纯 ASCII 别名（英文 ID/昵称如 aru/haruka/igusa_haruka）**整词匹配**——
    防止短名误命中: aru 是 koharu 的子串（a-r-u）, 但玩家输入 koharu 想的是
    小春不是阿露; 边界用 ASCII 词字符 [A-Za-z0-9_]（**不用 \\w**——它含汉字,
    会让 "haruka酱" 里酱算词字符导致不命中）。
    中文/假名别名保持子串匹配: 「阿露」命中「陆八魔阿露」「阿露酱」。
    英文大小写不敏感（re.IGNORECASE）。
    """
    for alt in pattern.split("|"):
        alt = alt.strip()
        if not alt:
            continue
        if _is_ascii(alt):
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(alt)}(?![A-Za-z0-9_])",
                         name, re.IGNORECASE):
                return True
        elif alt in name:
            return True
    return False


def name_confirm(name: str, input_fn=input) -> bool:
    """取名确认/彩蛋环节。返回是否接受这个名字（True=调用方保存）。

    读 config/eggs/namegg.json: 任一别名命中玩家名 → 打印该角色的彩蛋台词。
    彩蛋回复可带前缀控制动作:
      RJ~  玩笑式拒绝 → 弹台词 + 只给 (n/n) 选项, 无论玩家选什么都拒绝
      AC~  该角色接受 → 弹台词后常规 y/n 确认
      无前缀  普通彩蛋 → 弹台词后常规 y/n 确认
    未命中 → 常规确认「名字是『xx』吗?」。
    英文别名整词匹配（koharu 不再误命中 aru）; 中文/假名子串匹配;
    英文大小写不敏感。多条命中只弹第一条。
    彩蛋配置缺失/损坏 → 打印错误后降级为常规确认（不阻塞改名流程）。
    """
    try:
        data = _load_namegg()
    except (FileNotFoundError, ValueError) as e:
        print(f"[系统] 彩蛋配置异常: {e}")
        data = {}
    for pattern, replies in data.items():
        if not _egg_pattern_matches(pattern, name):
            continue
        if not replies:
            break
        raw = random.choice(replies)
        sign, text = raw[:3], raw[3:]       # 前缀超出切片安全, 短回复走普通分支
        if sign == REJECT_NAMING:
            print(f"[???] {text}")
            try:
                input_fn(f"名字是『{name}』吗？(n/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                pass
            return False                    # 玩笑式拒绝: 只有否, 永远不接受
        print(f"[???] {text if sign == ACCEPT_NAMING else raw}")
        try:
            answer = input_fn(f"名字是『{name}』吗？(y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return True
        return answer in ACCEPT_REPLIES
    # 未命中彩蛋 → 常规确认
    try:
        answer = input_fn(f"名字是『{name}』吗？(y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return True
    return answer in ACCEPT_REPLIES




def set_player_name(input_fn=input) -> str:
    """交互式输入/更改玩家名（菜单 N 入口）。留空取消; 校验通过才保存。

    名字只存 data/basic/player.json 供系统显示（终端提示符/菜单/再见语）,
    不注入 system prompt——学生不会直呼玩家自定义名（一直称呼"老师"）。
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
        problem = _name_problem(name)
        if problem:
            print(f"[系统] {problem}，请换个名字。")
            continue
        if not name_confirm(name, input_fn=input_fn):
            print("[系统] 已取消，名字未修改。")
            continue
        save_player_name(name)
        print(f"[系统] 已保存，角色将称呼你为: {name}")
        return name


def ensure_player_name(input_fn=input) -> str:
    """首次运行设置玩家名: 未设置时询问并保存, 已设置直接返回。
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
        problem = _name_problem(name)
        if problem:
            print(f"[系统] {problem}，请换个名字。")
            continue
        if not name_confirm(name, input_fn=input_fn):
            print("[系统] 好的，重新取名。")
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
  /name     查看/修改你的称呼（仅系统显示, 不进对话）
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
        problem = _name_problem(new_name)
        if problem:
            print(f"[系统] {problem}")
            return None
        save_player_name(new_name)
        print(f"[系统] 称呼已改为: {new_name}（终端提示符即刻生效）")
        return None

    print(f"[系统] 未知命令: /{cmd}。输入 /help 查看可用命令。")
    return None