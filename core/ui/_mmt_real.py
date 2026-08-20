# -*- coding: utf-8 -*-
"""真实 LLM 对话冒烟 — 验证全 JSON loop 端到端像之前一样正常聊天。

两轮普通对话 + 保存会话 + 探针提问（角色能否感知"会话已保存"这类系统消息）。
观察:
  - agent_turn 返回的显示步骤 / 对白 / 历史
  - save_session 前后 history 是否变化（不变 = 系统消息不进 LLM context）

用法: python core/ui/_mmt_real.py   （需项目根环境, .env 有 LLM_API_KEY）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from llm.client import LLMClient
from core.momotalk import MomoTalkEngine
from core.ui.streaming import simulate_steps

CHARACTER = "igusa_haruka"


def main() -> None:
    client = LLMClient()
    engine = MomoTalkEngine("config/characters", client)
    engine.start_session(CHARACTER)

    for prompt in ["你好呀，今天过得怎么样？", "我们去天台走走吧！"]:
        print(f"\n────────── You: {prompt} ──────────")
        result = engine.agent_turn(prompt)
        simulate_steps(result.steps)
        print()
        print(f"  [action] {result.action}  bond_story={result.bond_story}")
        print(f"  [history] {engine.history_length} 条")
        for i, t in enumerate(engine.trace):
            print(f"  [trace {i}] {t.get('action')} ok={t.get('exec_ok')}")

    # 系统消息可见性: 保存会话, 检查 history 是否被注入
    before = engine.history_length
    engine.save_session()
    after = engine.history_length
    print(f"\n  save_session 前后历史: {before} → {after} 条"
          f"（{'不变 = LLM 看不到『会话已保存』' if before == after else '注入 = 变了'}）")

    print("\n────────── You: 我们刚才是不是保存过会话？你知不知道？ ──────────")
    result = engine.agent_turn("我们刚才是不是保存过会话？你知不知道？")
    simulate_steps(result.steps)
    print()

    client.close()


if __name__ == "__main__":
    main()
