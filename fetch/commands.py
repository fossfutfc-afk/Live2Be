"""fetch/commands.py — IDE 本地命令（/view /edit）: 确定性操作, 零 token。

设计原则: 本地命令与 AI 写动作走**同一条** executor 链——
    /edit 构造 update_character(mode=merge) 的 AgentAction → plan(diff) → 批准 → execute;
    /view 直接读文件 + get_completeness（SIG 完整度, 运行期依赖的可见化）。

本模块只含纯逻辑（不吃 input()/print()）: CLI(fetch/agent.py) 与
web(web/runner.py) 各做交互层, 命令逻辑共享, 两侧行为一致。

语法:
    /view <角色>[/<文件>]        列五件套清单 / 展示某文件全部字段 + SIG 完整度
    /edit <角色>/<文件> 键: 值   行内补丁; 或多行粘贴（CLI 空行结束, web 弹窗）
    （文件必须是五件套之一: profile/personality/knowledge/experience/typical.yml）
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from errors import Live2BeError
from contract import APPROVAL_REQUIRED, AgentAction, DOMAIN_IDE, is_valid_identifier
from fetch.actions.common import CHARACTER_FILE_SET, CHARACTER_FILES, MODE_MERGE
from fetch.executor import ExecError, Executor
from core.parsing.dynamic_character_parser import get_completeness, get_display_name

#: 命令可用动词（其余 /xxx 交给上层: /exit 退出, /clear 清屏等）
_COMMANDS = frozenset({"view", "edit"})


class CmdError(Live2BeError):
    """命令层拒绝/失败（直接给用户看原因, 不触发审批）。

    __str__ 自动产出 [commands.py][CmdError][message]。
    """


@dataclass(frozen=True)
class Cmd:
    """解析后的命令。file=None 时只对整角色操作（/view 列五件套清单）。"""

    verb: str
    char_id: str
    file: str | None = None
    snippet: str = ""   # edit 的行内/粘贴补丁（空 = 需另行输入）


# ============================================================================
# 解析
# ============================================================================

def parse_cmd(text: str) -> Cmd | None:
    """解析 /view /edit 命令。非命令/未知动词返回 None（调用方走 agent_turn）。"""
    text = text.strip()
    if not text.startswith("/"):
        return None
    verb, _, args = text[1:].strip().partition(" ")
    verb = verb.lower()
    if verb not in _COMMANDS:
        return None

    args = args.strip()
    if not args:
        raise CmdError(f"/{verb} 需要角色 id, 如 /{verb} igusa_haruka[/profile.yml]")

    # 路径 = 前 1-2 个 token; edit 的行内补丁 = 路径之后的全部文本。
    # 用 _split_path（按空格/换行任一分界）而非 partition(" "): 补丁在路径
    # **下一行**时（web 粘贴组装的多行命令串）, 第一个 \n 就是路径终点。
    tok1, tail = _split_path(args)
    if "/" in tok1:
        char_id, file = tok1.split("/", 1)
        snippet = tail.strip()
    else:
        char_id = tok1
        tok2, _, tail2 = tail.strip().partition(" ")
        if tok2 and tok2 in CHARACTER_FILE_SET:
            file = tok2
            snippet = tail2.strip()
        else:
            file = None
            snippet = tail.strip()

    if not is_valid_identifier(char_id):
        raise CmdError(f"角色 id 必须匹配 [a-z0-9_]+: {char_id!r}")
    if file is not None and file not in CHARACTER_FILE_SET:
        raise CmdError(
            f"文件必须是五件套之一: {', '.join(CHARACTER_FILES)} (得 {file!r})"
        )
    return Cmd(verb=verb, char_id=char_id, file=file, snippet=snippet)


def _split_path(text: str) -> tuple[str, str]:
    """按第一个空白(空格/换行)切开 → (路径, 其余)。

    行内补丁 `/edit a/b 键: 值` 的第一个空格是路径终点; 补丁在下一行的
    多行命令串 `/edit a/b\n键: 值` 则第一个换行是路径终点——两者都走这里。
    """
    for i, ch in enumerate(text):
        if ch in " \n":
            return text[:i], text[i:]
    return text, ""


# ============================================================================
# /view
# ============================================================================

def cmd_view(root: str | Path, cmd: Cmd) -> str:
    """/view 展示文本。file=None → 五件套清单 + 显示名; 指定文件 → 全文 + 完整度。"""
    char_dir = _char_dir(root, cmd.char_id)
    if not char_dir.is_dir():
        raise CmdError(f"角色不存在: {cmd.char_id}")
    if cmd.file is None:
        return _view_char(char_dir)
    path = char_dir / cmd.file
    if not path.exists():
        raise CmdError(f"文件不存在: {cmd.char_id}/{cmd.file}")
    return _view_file(char_dir, cmd.file, path)


def _view_char(char_dir: Path) -> str:
    lines = [f"=== {char_dir.name} 五件套 ==="]
    for name in CHARACTER_FILES:
        path = char_dir / name
        if path.exists():
            size = len(path.read_text(encoding="utf-8"))
            lines.append(f"  {name:<18} {size} 字符")
        else:
            lines.append(f"  {name:<18} (缺失)")
    profile = _safe_load(_read_opt(char_dir / "profile.yml"))
    if profile:
        lines.append(f"显示名: {get_display_name(profile)}")
    lines.append("用 /view <角色>/<文件> 查看具体内容;  /edit <角色>/<文件> 键: 值 修改")
    return "\n".join(lines)


def _view_file(char_dir: Path, file: str, path: Path) -> str:
    content = path.read_text(encoding="utf-8").rstrip("\n")
    lines = [f"=== {char_dir.name}/{file} ===", content or "(空文件)"]
    if file == "profile.yml":
        data = _safe_load(content)
        if data:
            comp = get_completeness(data)
            info = (
                f"--- 完整度 {comp['score']}/{comp['total_sig']} "
                f"({comp['ratio']:.0%})"
            )
            # get_completeness 的 missing_* 键已剥前缀 → 补回前缀字面量,
            # 让用户能直接照着键名去写（REQ~/SIG~ 是字面量, 见提示词约定）
            if comp["missing_sig"]:
                info += "  缺失 SIG: " + ", ".join(
                    "SIG~" + k for k in sorted(comp["missing_sig"])
                )
            if comp["missing_req"]:
                info += "  缺失 REQ: " + ", ".join(
                    "REQ~" + k for k in sorted(comp["missing_req"])
                )
            lines.append(info)
    return "\n".join(lines)


# ============================================================================
# /edit — plan(diff) → 批准 → execute（复用 update_character merge 链）
# ============================================================================

def cmd_edit_plan(root: str | Path, cmd: Cmd, snippet: str) -> tuple[str, AgentAction]:
    """/edit 写前预览: 校验补丁 → 构造 merge 动作 → executor.plan。

    Returns:
        (diff, action) — diff 给用户看; action 批准后传给 cmd_edit_execute。
    """
    snippet = snippet.strip()
    if not snippet:
        raise CmdError("补丁为空——输入要改的 YAML, 如 `SIG~age: 16`")
    if cmd.file is None:
        raise CmdError("/edit 需要指定文件, 如 /edit igusa_haruka/profile.yml SIG~age: 16")
    data = _safe_load(snippet)
    if not isinstance(data, dict):
        raise CmdError("补丁必须是合法的 YAML 对象（{键: 值}）")
    if not data:
        raise CmdError("补丁不能为空对象")

    char_dir = _char_dir(root, cmd.char_id)
    if not char_dir.is_dir():
        raise CmdError(f"角色不存在: {cmd.char_id}")
    if not (char_dir / cmd.file).exists():
        raise CmdError(
            f"文件不存在: {cmd.char_id}/{cmd.file}（/edit 只改已有文件, 新建请用 AI）"
        )

    action = AgentAction(
        action="update_character",
        domain=DOMAIN_IDE,
        approval=APPROVAL_REQUIRED,
        summary=f"本地编辑 {cmd.char_id}/{cmd.file}",
        payload={"character_id": cmd.char_id, "mode": MODE_MERGE,
                 "files": {cmd.file: snippet}},
    )
    try:
        plan = Executor(root).plan(action)
    except ExecError as e:
        raise CmdError(str(e)) from e
    return plan.diff, action


def cmd_edit_execute(root: str | Path, action: AgentAction) -> str:
    """/edit 落盘。返回结果消息。executor.execute 幂等。"""
    try:
        result = Executor(root).execute(action)
    except ExecError as e:
        raise CmdError(str(e)) from e
    return result.message


# ============================================================================
# 内部工具
# ============================================================================

def _char_dir(root: str | Path, char_id: str) -> Path:
    return Path(root) / "config" / "characters" / char_id


def _read_opt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _safe_load(text: str) -> Any:
    """YAML 解析失败返回 None（/view 里内容仍照常展示, 只是不算完整度）。"""
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None
