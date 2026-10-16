# -*- coding: utf-8 -*-
"""真实 LLM 对话冒烟 — 火宫千夏（长文本） + 伊草遥香（紧张短句）断句效果。

每角色一轮对话, 打印 agent_turn 返回的气泡（断句结果）。
用法: python experiments/mmt_two_chars.py   （项目根环境, .env 有 LLM_API_KEY）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from llm.client import LLMClient
from core.mmt.engine import MomoTalkEngine
from core.text import strip_name_prefix

PAIRS = [
    ("hinomiya_chinatsu", ["老师想听听你对『风纪』的看法，请详细说说。"]),
    ("igusa_haruka", ["嘿，小遥香～你今天怎么有点紧张的样子？"]),
]


def run(char_id: str, prompts: list[str]) -> None:
    client = LLMClient()
    engine = MomoTalkEngine("config/characters", client)
    engine.start_session(char_id)
    name = engine.current_character.display_name
    print(f"\n{'=' * 44}")
    print(f"  角色: {name} ({char_id})")
    print("=" * 44)
    for p in prompts:
        print(f"\n  You: {p}")
        result = engine.agent_turn(p)
        print(f"  [action={result.action}] 气泡:")
        for s in result.steps:
            if not s.typing:
                text = strip_name_prefix(s.text, name)
                if text:
                    print(f"    「{text}」")
    client.close()


def main() -> None:
    for char_id, prompts in PAIRS:
        try:
            run(char_id, prompts)
        except Exception as e:  # noqa: BLE001
            print(f"\n[!] {char_id} 失败: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
