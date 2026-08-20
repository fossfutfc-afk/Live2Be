# -*- coding: utf-8 -*-
"""fetch/ 只读查看动作（view_character / view_interperson）回归测试。

覆盖:
    契约解析     registry.parse 结构白名单（非法 id/file 拒绝）
    执行层       清单/单目标两种输出 + 完整度 + merge 复用（execute 传回 plan）
    agent 链路   LLM 先查看现状 → 补写缺失 → done

用法: python fetch/_view_test.py   （项目根环境, 推荐 live2be env）
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contract import (
    ContractError, AgentAction, DOMAIN_IDE, APPROVAL_NEVER, APPROVAL_REQUIRED,
)
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


def _interperson_action(char_id: str | None = None) -> AgentAction:
    payload: dict[str, str] = {}
    if char_id:
        payload["character_id"] = char_id
    return AgentAction(action="view_interperson", domain=DOMAIN_IDE,
                       approval=APPROVAL_NEVER, payload=payload)


def _seed_interperson(root: Path, data: dict) -> Path:
    p = root / "config" / "settings" / "relation" / "interperson.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


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


# ============================================================================
# view_interperson: 契约解析 + 执行层 + agent 链路
# ============================================================================

def test_parse_view_interperson():
    reg = build_ide_registry()

    act, result = reg.parse({"action": "view_interperson", "reply": "看看关系。",
                             "payload": {}})
    assert result.is_valid and act is not None
    assert act.action == "view_interperson" and act.approval == "never"
    assert act.payload == {} and act.reply == "看看关系。"

    act2, r2 = reg.parse({"action": "view_interperson",
                          "payload": {"character_id": "stub"}})
    assert r2.is_valid and act2.payload == {"character_id": "stub"}

    _, bad = reg.parse({"action": "view_interperson",
                        "payload": {"character_id": "伊草 遥香"}})
    assert not bad.is_valid and any("character_id" in e for e in bad.errors)
    print("view_interperson 契约解析 PASS")


def test_exec_view_interperson_list():
    root = Path(tempfile.mkdtemp())
    _seed_interperson(root, {
        "stub": {"player": 2, "asagi_mutsuki": 3},
        "other": {"player": 1},
    })
    res = Executor(root).execute(_interperson_action())
    assert res.ok
    assert "2 个角色有记录" in res.message
    assert "stub (2)" in res.message and "asagi_mutsuki(3)" in res.message
    assert "other (1)" in res.message and "player(1)" in res.message
    print("view_interperson 清单模式 PASS")


def test_exec_view_interperson_single():
    root = Path(tempfile.mkdtemp())
    _seed_interperson(root, {"stub": {"player": 2, "asagi_mutsuki": 3}})
    res = Executor(root).execute(_interperson_action("stub"))
    assert res.ok
    assert "asagi_mutsuki: 3" in res.message
    assert "player: 2" in res.message
    assert "全量快照替换" in res.message
    print("view_interperson 单角色模式 PASS")


def test_exec_view_interperson_missing():
    """无记录角色 → 空状态提示（供直接写全量快照）, 不再报错。"""
    root = Path(tempfile.mkdtemp())
    _seed_interperson(root, {"stub": {}})
    res = Executor(root).execute(_interperson_action("nobody"))
    assert res.ok
    assert "暂无关系记录" in res.message
    assert "全量快照" in res.message
    print("view_interperson 无记录→空状态 PASS")


def test_exec_merge_reuse():
    """plan 算好的 merge 最终内容, execute 传回 plan 复用, 不重算。"""
    root = Path(tempfile.mkdtemp())
    _seed(root)
    ex = Executor(root)
    u = AgentAction(action="update_character", domain=DOMAIN_IDE,
                    approval=APPROVAL_REQUIRED,
                    payload={"character_id": "stub", "mode": "merge",
                             "files": {"profile.yml": "SIG~birthday: 5/13\n"}})

    calls = {"n": 0}
    orig = Executor._resolve_update_files
    def counting(self, action, char_dir):
        calls["n"] += 1
        return orig(self, action, char_dir)
    Executor._resolve_update_files = counting
    try:
        plan = ex.plan(u)
        assert calls["n"] == 1
        res = ex.execute(u, plan=plan)
        assert res.ok and "stub" in res.message
        assert calls["n"] == 1, "execute 复用 plan, 不应重算 merge"
        # 幂等兜底: 不带 plan 仍能正常执行（重新计算）
        res2 = ex.execute(u)
        assert res2.ok and calls["n"] == 2
    finally:
        Executor._resolve_update_files = orig

    text = (root / "config" / "characters" / "stub" / "profile.yml").read_text(encoding="utf-8")
    assert "SIG~birthday: 5/13" in text
    assert "REQ~most_called_name: 伊草 遥香" in text   # merge 保留原有字段
    print("executor merge 复用 PASS")


def test_agent_view_interperson_then_update():
    """LLM 先 view_interperson 摸清现状 → 带上现状补新关系 → done。"""
    root = Path(tempfile.mkdtemp())
    _seed(root)
    _seed_interperson(root, {"stub": {"asagi_mutsuki": 2}})

    rec = Recorder(["approve"])
    from fetch.agent import IDEAgent

    ui = {
        "action": "update_interperson", "summary": "补 player 关系",
        "reply": "现状看清了, 补一个 player。",
        "payload": {"character_id": "stub",
                    "relations": {"asagi_mutsuki": 2, "player": 2}},  # 全量快照
        "basis": ["用户要求"],
    }
    # 注意: update_interperson 不在范例门(_WRITE_ACTIONS)里, 不会被弹掉重生成
    agent = IDEAgent(StubLLM([
        {"action": "view_interperson", "reply": "让我看看现状。", "payload": {}},
        ui, {"action": "done", "summary": "已补关系", "reply": "补完了。",
             "payload": {"message": "已补关系"}},
    ]), root=root, emit=rec.emit, ask=rec.ask)
    agent.agent_turn("给 stub 补一个 player 的关系")

    kinds = rec.kinds()
    assert "TOOL_START" in kinds and "TOOL_RESULT" in kinds, kinds
    ts = rec.find("TOOL_START")[0]
    assert ts.data["name"] == "view_interperson"
    assert kinds[-1] == "DONE" and kinds.count("DONE") == 1
    assert any(t.get("event") == "view_interperson" for t in agent.trace)

    cur = json.loads(
        (root / "config" / "settings" / "relation" / "interperson.json")
        .read_text(encoding="utf-8"))
    assert cur["stub"] == {"asagi_mutsuki": 2, "player": 2}
    print("agent 链路(查看关系→补关系) PASS")


def main() -> None:
    tests = [
        test_parse,
        test_exec_list, test_exec_list_missing_sig, test_exec_single_file,
        test_exec_errors,
        test_agent_view_then_complete,
        test_parse_view_interperson,
        test_exec_view_interperson_list, test_exec_view_interperson_single,
        test_exec_view_interperson_missing, test_exec_merge_reuse,
        test_agent_view_interperson_then_update,
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
