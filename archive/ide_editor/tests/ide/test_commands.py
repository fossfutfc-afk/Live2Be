# -*- coding: utf-8 -*-
"""ide/ 本地命令（/view /edit）回归测试。

命令层是纯逻辑（ide.ide_commands）, 不碰 input()/print()——CLI(agent.py) 与
web(runner.py) 共用同一实现, 这里测的就是共享核心。

运行: python -m pytest tests/ide/test_commands.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ide.ide_commands import (
    Cmd,
    CmdError,
    cmd_edit_execute,
    cmd_edit_plan,
    cmd_view,
    parse_cmd,
)
from ide.actions.common import MODE_MERGE


# ============================================================================
# 夹具: 临时根目录 + 一个 stub 角色
# ============================================================================

PROFILE = """REQ~most_called_name: 伊草 遥香
REQ~is_official_character: true
SIG~age: 15
SIG~club: 真相调查部
"""


def _mk_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="l2b_cmd_"))
    (root / "config" / "characters" / "stub").mkdir(parents=True)
    (root / "config" / "characters" / "stub" / "profile.yml").write_text(
        PROFILE, encoding="utf-8"
    )
    return root


# ============================================================================
# parse_cmd
# ============================================================================

def test_parse_forms():
    # /view 单 token → 角色
    c = parse_cmd("/view stub")
    assert (c.verb, c.char_id, c.file, c.snippet) == ("view", "stub", None, "")

    # /view 斜杠路径
    c = parse_cmd("/view stub/profile.yml")
    assert (c.verb, c.char_id, c.file) == ("view", "stub", "profile.yml")

    # /edit 行内补丁
    c = parse_cmd("/edit stub/profile.yml SIG~age: 16")
    assert (c.verb, c.char_id, c.file) == ("edit", "stub", "profile.yml")
    assert c.snippet == "SIG~age: 16"

    # /edit 双 token（文件 + 补丁）
    c = parse_cmd("/edit stub profile.yml SIG~age: 16")
    assert (c.verb, c.char_id, c.file) == ("edit", "stub", "profile.yml")
    assert c.snippet == "SIG~age: 16"

    # /edit 只有路径, 无补丁 → snippet 空（走粘贴模式）
    c = parse_cmd("/edit stub/profile.yml")
    assert c.file == "profile.yml" and c.snippet == ""

    # 多行补丁: 换行保留在 snippet 里（web 粘贴组装命令串后走这条）
    c = parse_cmd("/edit stub/profile.yml\nSIG~age: 16\nclub: 格黑娜")
    assert c.snippet == "SIG~age: 16\nclub: 格黑娜"

    # 非命令 / 未知动词 → None（交给 agent_turn）
    assert parse_cmd("为伊草遥香补齐 profile.yml") is None
    assert parse_cmd("/foo stub") is None

    print("parse_cmd 各形式 PASS")


def test_parse_errors():
    for bad, reason in [
        ("/view", "无参数"),
        ("/view 井草", "非法 id"),
        ("/view stub/other.yml", "非五件套文件"),
        ("/view stub/profile.txt", "非五件套文件"),
    ]:
        try:
            parse_cmd(bad)
        except CmdError as e:
            assert reason in str(e) or "五件套" in str(e) or "id" in str(e), \
                f"{bad!r}: {e}"
        else:
            raise AssertionError(f"{bad!r} 应抛 CmdError")
    print("parse_cmd 错误路径 PASS")


# ============================================================================
# cmd_view
# ============================================================================

def test_view_char():
    root = _mk_root()
    out = cmd_view(root, Cmd("view", "stub"))
    assert "五件套" in out and "profile.yml" in out
    assert "伊草 遥香" in out          # get_display_name 从 profile 提取
    assert "(缺失)" in out             # personality 等未创建

    try:
        cmd_view(root, Cmd("view", "nobody"))
    except CmdError as e:
        assert "角色不存在" in str(e)
    else:
        raise AssertionError("不存在的角色应报错")
    print("cmd_view 角色清单 PASS")


def test_view_file():
    root = _mk_root()
    out = cmd_view(root, Cmd("view", "stub", "profile.yml"))
    assert "REQ~most_called_name: 伊草 遥香" in out   # 全文展示
    assert "完整度 2/2" in out                          # SIG~age + SIG~club
    assert "缺失 SIG" not in out                        # 都非空

    # 缺失 REQ 字段的 profile → 完整度提示列出 REQ 缺失
    (root / "config" / "characters" / "stub" / "profile.yml").write_text(
        "SIG~age: 15\nREQ~most_called_name: \"\"\n", encoding="utf-8"
    )
    out2 = cmd_view(root, Cmd("view", "stub", "profile.yml"))
    assert "缺失 REQ: REQ~most_called_name" in out2

    try:
        cmd_view(root, Cmd("view", "stub", "knowledge.yml"))
    except CmdError as e:
        assert "文件不存在" in str(e)
    else:
        raise AssertionError("不存在的文件应报错")
    print("cmd_view 文件 + 完整度 PASS")


# ============================================================================
# cmd_edit_plan / cmd_edit_execute
# ============================================================================

def test_edit_plan_merge():
    root = _mk_root()
    cmd = Cmd("edit", "stub", "profile.yml", "SIG~age: 16\nSIG~club: 修女会")
    diff, action = cmd_edit_plan(root, cmd, cmd.snippet)
    assert "[更新]" in diff and "SIG~age: 15" in diff and "SIG~age: 16" in diff
    assert action.action == "update_character"
    assert action.payload["mode"] == MODE_MERGE
    assert action.payload["files"]["profile.yml"] == cmd.snippet

    # 无变化: 补丁与现有一致 → diff 只有 [无变化] 块
    cmd2 = Cmd("edit", "stub", "profile.yml", "REQ~most_called_name: 伊草 遥香")
    diff2, _ = cmd_edit_plan(root, cmd2, cmd2.snippet)
    assert "[无变化]" in diff2 and "[更新]" not in diff2

    # 多行补丁 → 顶层字段级合并, 未提及字段保留
    cmd3 = Cmd("edit", "stub", "profile.yml", "SIG~club: 格黑娜学园")
    _, action3 = cmd_edit_plan(root, cmd3, cmd3.snippet)
    text = cmd_edit_execute(root, action3)
    assert "已更新" in text
    merged = (root / "config" / "characters" / "stub" / "profile.yml").read_text(
        encoding="utf-8"
    )
    assert "SIG~club: 格黑娜学园" in merged and "伊草 遥香" in merged

    # execute 幂等: 重跑同一 action 仍是 merge, 不丢字段
    text2 = cmd_edit_execute(root, action3)
    assert "已更新" in text2
    merged2 = (root / "config" / "characters" / "stub" / "profile.yml").read_text(
        encoding="utf-8"
    )
    assert merged == merged2
    print("cmd_edit_plan/execute 合并 + 幂等 PASS")


def test_edit_errors():
    root = _mk_root()
    cases = [
        (Cmd("edit", "stub", "profile.yml", "   "), "补丁为空"),
        (Cmd("edit", "stub", None, "SIG~age: 16"), "需要指定文件"),
        (Cmd("edit", "stub", "profile.yml", "- a\n- b"), "YAML 对象"),
        (Cmd("edit", "stub", "profile.yml", "plain string"), "YAML 对象"),
        (Cmd("edit", "stub", "profile.yml", "# 只有注释"), "YAML 对象"),
        (Cmd("edit", "stub", "profile.yml", "{}"), "空对象"),
        (Cmd("edit", "nobody", "profile.yml", "SIG~age: 16"), "角色不存在"),
        (Cmd("edit", "stub", "knowledge.yml", "SIG~age: 16"), "文件不存在"),
    ]
    for cmd, want in cases:
        try:
            cmd_edit_plan(root, cmd, cmd.snippet)
        except CmdError as e:
            assert want in str(e), f"{want!r} 不在 {e}"
        else:
            raise AssertionError(f"{cmd} 应抛 CmdError({want})")
    print("cmd_edit_plan 错误路径 PASS")


def main() -> None:
    tests = [
        test_parse_forms,
        test_parse_errors,
        test_view_char,
        test_view_file,
        test_edit_plan_merge,
        test_edit_errors,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\nide/ 命令层回归: {len(tests) - failed}/{len(tests)} 通过")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
