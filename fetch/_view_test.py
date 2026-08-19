# -*- coding: utf-8 -*-
"""fetch/ view_character（只读查看角色现状）回归测试。

覆盖:
    契约解析     registry.parse(view_character) 结构白名单（非法 id/file 拒绝）
    执行层       Executor._execute_view_character 清单/单文件两种输出 + 完整度
    agent 链路   LLM 先 view_character → 摸清缺失 → 补写缺失文件 → done

用法: python fetch/_view_test.py   （项目根环境, 推荐 live2be env）
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contract import ContractError, AgentAction, DOMAIN_IDE, APPROVAL_NEVER
from fetch.actions import build_ide_registry
from fetch.executor import ExecError, Executor


PROFILE = """REQ~most_called_name: 伊草 遥香
REQ~is_official_character: true
SIG~age: 15
SIG~club: 真相调查部
"""


def _seed(root: Path, char_id: str = "stub", profile: str = PROFILE) -> Path:
    char_dir = root / "config" / "characters" / char_id
    char_dir.mkdir(parents=True)
    (char_dir / "profile.yml").write_text(profile, encoding="utf-8")
    return char_dir


def _action(char_id: str = "stub", file: str | None = None) -> AgentAction:
    payload = {"character_id": char_id}
    if file:
        payload["file"] = file
    return AgentAction(action="view_character", domain=DOMAIN_IDE,
                       approval=APPROVAL_NEVER, payload=payload)


# ============================================================================
# 契约解析
# ============================================================================

def test_parse():
    reg = build_ide_registry()

    act, result = reg.parse({
        "action": "view_character", "reply": "看看现状。",
        "payload": {"character_id": "igusa_haruka"},
    })
    assert result.is_valid and act is not None
    assert act.action == "view_character" and act.approval == "never"
    assert act.payload == {"character_id": "igusa_haruka"}
    assert act.reply == "看看现状。"

    act2, result2 = reg.parse({
        "action": "view_character",
        "payload": {"character_id": "igusa_haruka", "file": "experience.yml"},
    })
    assert result2.is_valid and act2.payload["file"] == "experience.yml"

    # 非法: 非法 id / 非五件套文件
    _, bad1 = reg.parse({"action": "view_character", "payload": {"character_id": "伊草 遥香"}})
    assert not bad1.is_valid and any("character_id" in e for e in bad1.errors)
    _, bad2 = reg.parse({"action": "view_character",
                         "payload": {"character_id": "stub", "file": "notes.txt"}})
    assert not bad2.is_valid and any("file" in e for e in bad2.errors)
    print("view_character 契约解析 PASS")


# ============================================================================
# 执行层
# ============================================================================

def test_exec_list():
    root = Path(tempfile.mkdtemp())
    _seed(root)
    ex = Executor(root)
    res = ex.execute(_action())
    assert res.ok
    assert "五件套现状" in res.message
    assert "profile.yml: 已存在" in res.message
    for missing in ("personality.yml", "knowledge.yml", "experience.yml", "typical.yml"):
        assert f"{missing}: 缺失" in res.message, f"应列 {missing} 缺失: {res.message}"
    assert "显示名: 伊草 遥香" in res.message
    assert "完整度 2/2" in res.message
    assert "缺失 SIG" not in res.message       # 全部非空
    print("view_character 清单模式 PASS")


def test_exec_list_missing_sig():
    # 完整度只统计"已出现的 SIG 字段"——空值的 SIG 才会进 missing_sig
    root = Path(tempfile.mkdtemp())
    _seed(root, profile='REQ~most_called_name: 测试酱\nSIG~age: ""\n')
    res = Executor(root).execute(_action())
    assert res.ok and "缺失 SIG: SIG~age" in res.message
    assert "完整度 0/1" in res.message
    print("view_character 清单模式(缺 SIG) PASS")


def test_exec_single_file():
    root = Path(tempfile.mkdtemp())
    char_dir = _seed(root)
    (char_dir / "personality.yml").write_text(
        "SIG~brief_traits:\n  - 胆小敏感\n", encoding="utf-8"
    )
    ex = Executor(root)

    # 单文件: profile 全文 + 完整度
    res = ex.execute(_action(file="profile.yml"))
    assert "REQ~most_called_name: 伊草 遥香" in res.message   # 全文
    assert "完整度 2/2" in res.message

    # 单文件: 非 profile 不给完整度（只展示全文）
    res2 = ex.execute(_action(file="personality.yml"))
    assert "SIG~brief_traits" in res2.message
    assert "完整度" not in res2.message
    print("view_character 单文件模式 PASS")


def test_exec_errors():
    root = Path(tempfile.mkdtemp())
    ex = Executor(root)
    try:
        ex.execute(_action(char_id="nobody"))
    except ExecError as e:
        assert "角色不存在" in str(e)
    else:
        raise AssertionError("不存在的角色应抛 ExecError")

    char_dir = _seed(root)
    try:
        ex.execute(_action(file="knowledge.yml"))
    except ExecError as e:
        assert "文件不存在" in str(e)
    else:
        raise AssertionError("不存在的文件应抛 ExecError")
    _ = char_dir
    print("view_character 错误路径 PASS")


# ============================================================================
# agent 链路: view_character → 摸清缺失 → 补写 → done
# ============================================================================

class StubLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def chat(self, messages, **kw):
        assert self._responses, "stub LLM 响应用尽"
        return self._responses.pop(0)


class Recorder:
    def __init__(self, decisions):
        self.events = []
        self.decisions = list(decisions)

    def emit(self, evt):
        self.events.append(evt)

    def ask(self, approval_id, prompt):
        assert self.decisions, "stub ask 决策用尽"
        return self.decisions.pop(0)

    def kinds(self):
        return [e.kind.name for e in self.events]

    def find(self, name):
        return [e for e in self.events if e.kind.name == name]


def test_agent_view_then_complete():
    """LLM 先 view_character 摸清缺失 → 补写 personality.yml → done。"""
    root = Path(tempfile.mkdtemp())
    _seed(root)

    rec = Recorder(["approve", "approve"])       # [0]=范例询问, [1]=写审批
    from fetch.agent import IDEAgent

    uc = {
        "action": "update_character", "summary": "补 personality",
        "reply": "缺 personality, 我来补。",
        "payload": {"character_id": "stub", "mode": "merge",
                    "files": {"personality.yml": "SIG~brief_traits:\n  - 胆小敏感\n"}},
    }
    agent = IDEAgent(StubLLM([
        {"action": "view_character", "reply": "让我看看缺什么。",
         "payload": {"character_id": "stub"}},
        uc, uc, {"action": "done", "summary": "已补全", "reply": "补完了。",
                 "payload": {"message": "已补全"}},
    ]), root=root, emit=rec.emit, ask=rec.ask)
    agent.agent_turn("补全这个角色")

    kinds = rec.kinds()
    assert "TOOL_START" in kinds and "TOOL_RESULT" in kinds, kinds
    ts = rec.find("TOOL_START")[0]
    assert ts.data["name"] == "view_character"
    tr = rec.find("TOOL_RESULT")[0]
    assert tr.data["name"] == "view_character" and tr.data["chars"] > 0
    assert kinds[-1] == "DONE", kinds
    assert kinds.count("DONE") == 1

    # 补写的文件已落盘; 范例(profile)已读, 补的 personality 也读
    path = root / "config" / "characters" / "stub" / "personality.yml"
    assert path.exists() and "胆小敏感" in path.read_text(encoding="utf-8")
    assert agent._example_loaded == {"personality.yml"}

    # trace 记录了 view 工具调用
    assert any(t.get("event") == "view_character" for t in agent.trace)
    print("agent 链路(查看→补全) PASS")


def main() -> None:
    tests = [
        test_parse,
        test_exec_list, test_exec_list_missing_sig, test_exec_single_file,
        test_exec_errors,
        test_agent_view_then_complete,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\nfetch/ view_character 回归: {len(tests) - failed}/{len(tests)} 通过")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
