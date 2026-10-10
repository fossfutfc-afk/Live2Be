# -*- coding: utf-8 -*-
"""`mmt_look` —— 第 1 件: **注册 + parse + 独占 + 接线 + 占位执行器**（2026-10-08）。

它一个一个落, 所以这个文件也**一节一节长**: 本件只有"她能不能用这个动作、用了会怎样"。
真检索（三级解析 + `find` + 放宽 + 三句话）在下一件。

守门:
  ① **注册与契约**: `mmt_look` 在注册表里、有 `payload_schema`、外壳字段与别的 MMT 动作一致
  ② **parse 只做结构白名单**: clue/when 至少一个; 线索编译不过 ⇒ 当场拒（可归因, 不静默）
  ③ ⭐ **payload 里只有字符串** —— 它会进 `TurnResult` / trace / 前端 JSON;
     塞一个编译好的 `Clue` 进去, 序列化那一层迟早出事（本件真 `json.dumps` 一次钉住）
  ④ **独占**: 静默轮只能有它一条行; ⚠️ 想起行**不算**（同 N5b 口径）
  ⑤ **接线**: `look` 在 `QUERY_ACTIONS` 里（查完回灌 + 继续这一轮）, ⛔ `trigger` 不在
  ⑥ ⭐ **占位执行器明说"未接线"**（注册表就是她的开关: 注册了她就能吐这一行,
     执行器缺席会走成"未知执行动作"⇒ 硬问题 + 整批不交付 —— 真机上表现为"她一句话没说"）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contract import (APPROVAL_AUTO, DOMAIN_MMT, AgentAction,   # noqa: E402
                      ContractError)
from core.mmt.mmt_actions import (MMT_RUNTIME_FIELDS,           # noqa: E402
                                  build_mmt_registry, parse_mmt_look)
from core.mmt.mmt_check import (ACTION_LOOK, ACTION_TRIGGER,    # noqa: E402
                                QUERY_ACTIONS, WHOLE_TURN_ACTIONS,
                                MmtIssueCode, check_turn)
from core.mmt.mmt_executor import MmtExecError, MmtExecutor     # noqa: E402
from core.mmt.mmt_lines import MmtLine                          # noqa: E402
from core.mmt.engine import MomoTalkEngine                      # noqa: E402
from core.session.store import SessionStore                     # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CHARACTER = "igusa_haruka"


def _text(s="话"):
    return MmtLine(kind="text", text=s)


def _look(**payload):
    return MmtLine(kind="action", action=ACTION_LOOK, payload=payload)


def _codes(issues):
    return [i.code for i in issues]


def _action(**payload) -> AgentAction:
    return AgentAction(action=ACTION_LOOK, domain=DOMAIN_MMT,
                       approval=APPROVAL_AUTO, payload=payload)


# ---------------------------------------------------------------------------
# ① 注册与契约
# ---------------------------------------------------------------------------

def test_registry_registers_look_with_its_field_doc():
    reg = build_mmt_registry()
    assert ACTION_LOOK in reg.action_names(), reg.action_names()
    spec = reg.spec(ACTION_LOOK)
    assert spec.prompt_fields == MMT_RUNTIME_FIELDS          # 外壳同其他 MMT 动作
    assert "clue" in spec.payload_schema and "when" in spec.payload_schema
    assert "&&" in spec.payload_schema                       # 运算符的形态要看见
    print("    注册: mmt_look 在表里, 字段说明含 clue / when / 运算符")


# ---------------------------------------------------------------------------
# ② parse（结构白名单）
# ---------------------------------------------------------------------------

def test_parse_accepts_clue_when_or_both_and_strips():
    assert parse_mmt_look({"clue": " 苔藓 && 杂草 "}) == {"clue": "苔藓 && 杂草", "when": ""}
    assert parse_mmt_look({"when": " 上周 "}) == {"clue": "", "when": "上周"}
    assert parse_mmt_look({"clue": "苔藓", "when": "last 1 week"}) == \
        {"clue": "苔藓", "when": "last 1 week"}
    print("    parse: clue / when / 两个都给 都收（并去首尾空白）")


def test_parse_output_is_json_safe_strings():
    """⭐ payload 里**只有字符串** —— 真序列化一次, 编译好的 `Clue` 会在这儿炸。"""
    out = parse_mmt_look({"clue": "(苔藓 || 杂草) && 老师", "when": "上周"})
    assert all(isinstance(v, str) for v in out.values()), out
    json.dumps(out, ensure_ascii=False)                      # 不抛 = 前端/TurnResult 安全
    print("    parse: 返回值 JSON 安全（⛔ 不塞自定义对象）")


def test_parse_rejects_bad_input():
    for bad in ({}, {"clue": "   "}, {"clue": "  ", "when": ""},
                {"clue": 123}, {"when": ["上周"]},
                {"clue": "苔藓 \\d"}, {"clue": "(苔藓"}, {"clue": "苔藓 &"}):
        with pytest.raises(ContractError):
            parse_mmt_look(bad)
    print("    parse: 空 / 非字符串 / 正则味线索 / 括号不闭合 ⇒ 当场拒")


# ---------------------------------------------------------------------------
# ④ 独占（静默轮）
# ---------------------------------------------------------------------------

def test_look_must_be_alone():
    alone = [_look(clue="苔藓")]
    assert check_turn(alone) == [], _codes(check_turn(alone))
    for bad in ([_text("我想想…"), *alone],
                [*alone, _text("哦哦")],
                [*alone, _look(when="上周")],
                [*alone, MmtLine(kind="action", action="mmt_send_media",
                                 payload={"image": "x"})]):
        issues = check_turn(bad)
        assert MmtIssueCode.EXCLUSIVE_VIOLATION in _codes(issues), issues
        assert issues[0].hard
    print("    check: look 静默轮 —— 夹消息/夹别的操作/重复 都判独占违规（硬）")


def test_noticed_row_does_not_break_look_exclusivity():
    """⚠️ 同 N5b 口径: **想起行是账目不是内容**, 不算"整轮只有它一条行"。"""
    rows = [_look(clue="苔藓"), MmtLine(kind="noticed", noticed="苔藓的约定")]
    assert check_turn(rows) == [], _codes(check_turn(rows))
    assert MmtIssueCode.EXCLUSIVE_VIOLATION in _codes(check_turn([*rows, _text("诶")]))


# ---------------------------------------------------------------------------
# ⑤ 接线
# ---------------------------------------------------------------------------

def test_query_actions_cover_look_but_never_trigger():
    """⭐ 查完**回灌 + 继续这一轮**的族; ⛔ `trigger` 是模式切换, 不在内。"""
    assert ACTION_LOOK in QUERY_ACTIONS
    assert ACTION_LOOK in WHOLE_TURN_ACTIONS          # 独占 ⇒ 必须整轮可见才判/执行
    assert ACTION_TRIGGER not in QUERY_ACTIONS


# ---------------------------------------------------------------------------
# ⑥ 占位执行器 + 端到端接线（一轮里两次主调用）
# ---------------------------------------------------------------------------

def test_placeholder_executor_says_not_wired(tmp_path):
    ex = MmtExecutor(tmp_path)
    ex.set_current_character(object())               # 占位只判"有没有会话"（类型无关）
    res = ex.execute(_action(clue="苔藓", when="上周"))
    assert res.ok and "未接线" in res.message
    assert "苔藓" in res.message                      # 回执带上她问的东西（可复盘）
    ex.set_current_character(None)
    with pytest.raises(MmtExecError):
        ex.execute(_action(clue="苔藓"))
    print("    占位: 明说未接线（不是静默成功）")


class _ScriptedLLM:
    """第一次调用给一条 `look` 行, 之后正常说话（模拟"查完接着说"）。"""

    def __init__(self):
        self.snapshots: list[list[dict]] = []
        self.replies = ['{"action": "mmt_look", "payload": {"clue": "苔藓"}}',
                        '{"text": "……嗯，我想起来了"}',
                        '{"text": "（备用）"}']

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        return self.replies[min(len(self.snapshots) - 1, len(self.replies) - 1)]


def test_look_round_is_fed_back_and_the_turn_continues(tmp_path):
    """⭐ **本件的核心接线**: 她发一条 `look` ⇒ 引擎回灌 + **同一轮接着要一次**。"""
    llm = _ScriptedLLM()
    store = SessionStore(data_root=tmp_path)
    eng = MomoTalkEngine(ROOT / "config" / "characters", llm, store=store)
    name = eng.start_session(CHARACTER)
    root = store.create(CHARACTER, name)
    eng.attach_session(root.session_id)

    result = eng.agent_turn("我们上次说的那件事，你还记得吗")
    assert len(llm.snapshots) == 2, [len(s) for s in llm.snapshots]   # 一轮两次主调用
    joined = "\n".join((m.get("content") or "") for m in llm.snapshots[-1])
    assert "未接线" in joined                        # 回执真的进了 messages
    assert llm.snapshots[-1][-1]["role"] == "user"   # `feedback()` 追加的是 **user**
    assert result.ok and "我想起来了" in result.reply  # 她接着说的话上了屏
    print("    look: ① 她发起 → ② 回执回灌 → ③ 同一轮接着说（两次主调用）")
