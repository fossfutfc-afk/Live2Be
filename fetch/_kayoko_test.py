# -*- coding: utf-8 -*-
"""实验：推理模型 + 大 max_tokens 创建鬼方佳代子角色档案。

验证：v4-flash + max_tokens 16384 能否在 agent 里跑通
（fetch_url 查资料 → create_character 五件套 → 落盘）。
"""
import io
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# 无缓冲输出，便于后台查看进度
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

# 让 `python fetch/_kayoko_test.py` 也能 import 项目根下的包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetch.agent import IDEAgent
from llm.client import LLMClient

tmp = Path(tempfile.mkdtemp())
print(f"工作目录: {tmp}", flush=True)
agent = IDEAgent(LLMClient(), root=tmp)

task = (
    "帮我创建《蔚蓝档案》里鬼方佳代子（onikata_kayoko）的完整角色档案。"
    "她是格黑娜学园便利屋68的课长，喜欢摇滚乐，是社团里最年长的人，"
    "平时不多话但可靠。"
    "请先查萌娘百科的资料，然后创建完整的五件套配置"
    "（profile/personality/knowledge/experience/typical）。"
)
print(f"任务: {task[:60]}...", flush=True)

with patch("builtins.input", return_value="y"):
    agent.agent_turn(task)

print("=" * 50, flush=True)
kayoko = tmp / "config" / "characters" / "onikata_kayoko"
files = sorted(p.name for p in kayoko.glob("*.yml")) if kayoko.exists() else []
print("RESULT 落盘文件:", files, flush=True)
print("trace:", [(t.get("action"), t.get("event", ""), t.get("parse_valid")) for t in agent.trace], flush=True)
for t in agent.trace:
    if t.get("event") in ("fetch_url", "search"):
        print(f"  {t['event']}: {t['label']} → {t['chars']} 字符", flush=True)
    if t.get("event") == "decision":
        print(f"  审批: {t['choice']} exec_ok={t.get('exec_ok')}", flush=True)
    if t.get("event") in ("plan_error", "fetch_url_error", "search_error"):
        print(f"  ⚠️ {t['event']}: {t.get('error','')[:80]}", flush=True)

profile = kayoko / "profile.yml"
if profile.exists():
    print("--- profile.yml ---", flush=True)
    print(profile.read_text(encoding="utf-8"), flush=True)
