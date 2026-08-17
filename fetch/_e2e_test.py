# -*- coding: utf-8 -*-
"""真实 LLM 端到端测试 → 生成 fetch/E2E_TEST.md

用 DeepSeek API + 隔离临时目录，跑两个代表性任务：
    任务 1: 创建原创角色 (OC) — 验证 create_character 写动作 + 审批 + 落盘
    任务 2: 查询角色资料     — 验证 fetch_url 抓取 + 回灌
"""
import io
import json
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 让 `python fetch/_e2e_test.py` 也能 import 项目根下的包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetch.agent import IDEAgent
from llm.client import LLMClient

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fetch" / "E2E_TEST.md"


def render_trace(agent: IDEAgent) -> list[str]:
    md: list[str] = []
    for t in agent.trace:
        md.append(f"### 步骤 {t.get('step', '?')} · {t.get('event', 'LLM 动作')}")
        md.append("")
        if t.get("action"):
            md.append(f"- 动作: **{t['action']}**  (审批: `{t['approval']}`)")
            md.append(f"- summary: {t['summary']}")
            if t.get("reply"):
                md.append(f"- reply: {t['reply']}")
            if t.get("payload"):
                md.append("- payload:")
                md.append("```json")
                md.append(json.dumps(t["payload"], ensure_ascii=False, indent=2))
                md.append("```")
        if "parse_valid" in t:
            md.append(f"- 契约解析: {'✅ 通过' if t['parse_valid'] else '❌ 无效'}")
            if t.get("parse_errors"):
                md.append(f"- 错误: {t['parse_errors']}")
            if t.get("parse_warnings"):
                md.append(f"- 警告: {t['parse_warnings']}")
        if t.get("diff") is not None:
            md.append("- diff (审批预览):")
            md.append("```diff")
            md.append(t["diff"])
            md.append("```")
        if t.get("choice"):
            md.append(f"- 审批决策: **{t['choice']}**")
            if t.get("exec_ok") is not None:
                md.append(f"- 执行结果: {'✅' if t['exec_ok'] else '❌'} {t.get('message', '')}")
        if t.get("event") == "fetch":
            md.append(f"- 抓取: `{t['url']}` → {t['chars']} 字符, 已回灌给 LLM")
        if t.get("event") in ("plan_error", "fetch_error"):
            md.append(f"- ⚠️ {t['event']}: {t['error']}")
        md.append("")
    return md


def conclusion(agent: IDEAgent) -> list[str]:
    actions = [t for t in agent.trace if t.get("action")]
    writes = [t for t in actions if t["approval"] == "required"]
    approved = [t for t in agent.trace if t.get("choice") == "approved"]
    md = [
        "- 动作总数: {}（写动作 {} 个, 其中批准执行 {} 个）".format(
            len(actions), len(writes), len(approved)
        ),
        "- 契约解析失败次数: {}（失败会回灌给 LLM 修正）".format(
            sum(1 for t in agent.trace if t.get("parse_valid") is False)
        ),
        "- 执行层拦截: {}".format(
            sum(1 for t in agent.trace if t.get("event") in ("plan_error", "exec_ok") and t.get("exec_ok") is False)
            + sum(1 for t in agent.trace if t.get("event") == "plan_error")
        ),
    ]
    return md


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="live2be_e2e_"))
    client = LLMClient()
    agent = IDEAgent(client, root=tmp)

    md = [
        "# Live2Be IDE Agent 端到端测试报告",
        "",
        f"- 日期: {datetime.now().isoformat(timespec='seconds')}",
        f"- LLM: `{client.model}` @ `{client.base_url}`",
        f"- 隔离工作目录: `{tmp}`（不污染真实 config）",
        "",
    ]

    # ---------------- 任务 1：创建 OC 角色 ----------------
    task1 = (
        "帮我创建一个原创角色(OC)，角色 id 用 'my_oc_test'，"
        "显示名叫'测试酱'，性格胆小但内心善良。"
        "这是用户自己构思的角色，不需要查网页资料，直接创建。"
    )
    md.append("## 任务 1：创建原创角色 (OC)")
    md.append("")
    md.append(f"**用户输入**: {task1}")
    md.append("")
    try:
        with patch("builtins.input", return_value="y"):  # 批准创建
            agent.agent_turn(task1)
    except Exception:
        md.append(f"**异常**:\n```\n{traceback.format_exc()}\n```\n")
    md.extend(render_trace(agent))

    profile = tmp / "config" / "characters" / "my_oc_test" / "profile.yml"
    if profile.exists():
        md.append("**落盘结果** ✅: 角色已创建，profile.yml 内容：")
        md.append("")
        md.append("```yaml")
        md.append(profile.read_text(encoding="utf-8").rstrip())
        md.append("```")
    else:
        md.append("**落盘结果** ⚠️: 未创建角色文件（见上方 trace）")
    md.append("")

    # ---------------- 任务 2：查询资料 ----------------
    task2 = "帮我查一下《蔚蓝档案》里伊草遥香这个角色在萌娘百科上的资料。"
    md.append("## 任务 2：查询角色资料")
    md.append("")
    md.append(f"**用户输入**: {task2}")
    md.append("")
    agent.trace = []  # trace 只记任务 2
    try:
        with patch("builtins.input", return_value="n"):  # 若有意外写动作则拒绝
            agent.agent_turn(task2)
    except Exception:
        md.append(f"**异常**:\n```\n{traceback.format_exc()}\n```\n")
    md.extend(render_trace(agent))
    md.append("")

    # ---------------- 结论 ----------------
    md.append("## 结论（任务 1+2 汇总）")
    md.append("")
    md.extend(conclusion(agent))
    md.append("")

    OUT.write_text("\n".join(md), encoding="utf-8")
    print("报告已写入:", OUT)
    client.close()


if __name__ == "__main__":
    main()
