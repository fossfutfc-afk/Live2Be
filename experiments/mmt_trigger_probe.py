# -*- coding: utf-8 -*-
"""本地模型触发探针 — 复刻真实 MMT flow: 6 轮历史 + 轮数注记 → 下一步动作。

用 LM Studio (localhost:1234) 的 qwen2.5-7b-instruct, 走 LLMClient(json_object)
真实清洗管道 + registry.parse + executor.execute, 判断:
  1) 模型是否知道/选择输出 mmt_trigger_bond_story
  2) 输出能否被正确解析
  3) 是模型能力问题还是 prompt/schema 问题

用法: python core/ui/_mmt_trigger_probe.py [trials]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.momotalk import MomoTalkEngine
from core.bond.bond_progress import BondProgress
from llm.client import LLMClient

from llm.json_cleaner import extract_json

ROOT = Path(__file__).resolve().parent.parent.parent
CHAR = "rikuhachima_aru"
MODEL = "qwen2.5-7b-instruct"
TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 4


class StubLLM:
    def format_messages(self, **kw):
        return []

    def chat_stream(self, *a, **kw):
        return iter(())


# 复刻用户 session 前 6 轮（阿露约出门）; 内容截断, 关键氛围保留
HISTORY = [
    {"role": "user", "content": "你好呀，最近有什么新鲜事吗"},
    {"role": "assistant", "content": "[mmt_chat] 哼哼，老师来得正好！本社长最近可是接了几个大委托……"},
    {"role": "user", "content": "是什么委托啊，是像之前一样帮别人救树上的小猫这种日常活动吗?"},
    {"role": "assistant", "content": "[mmt_chat] （有点心虚地别过脸）咳咳，怎么可能！……"},
    {"role": "user", "content": "你们便利屋最近资金状况还可以吗"},
    {"role": "assistant", "content": "[mmt_chat] （挺起胸膛）哼，本社长当然管得过来……话说回来，老师，今晚能不能借我点钱买泡面……？"},
    {"role": "user", "content": "当然可以，不过我有更好的主意，我们去拉面馆吃面吧，我来请客"},
    {"role": "assistant", "content": "[mmt_chat] 哼，既然老师这么诚心诚意要请客，本社长就勉为其难地赏光好了！"},
    {"role": "user", "content": "好的，那我们现在就出发吧"},
    {"role": "assistant", "content": "[mmt_chat] 既然老师诚心邀请，本社长就勉为其难地赏光走一趟吧！"},
]


def build_messages():
    engine = MomoTalkEngine(ROOT / "config" / "characters", StubLLM(),
                            bond_progress=BondProgress(ROOT / "data" / "basic" / "_probe_bp.json"))
    engine.start_session(CHAR)
    progress = engine.bond_progress
    for _ in range(6):            # 预积累 6 轮（对应真实 session）
        progress.record_turn(CHAR)

    messages = [{"role": "system", "content": engine._system_prompt}]
    messages.append({"role": "system", "content": engine._bond_progress_note()})
    messages.extend(HISTORY)
    messages.append({"role": "user", "content": (
        "那我们现在就走！我已经在店门口等你了\n\n"
        "（下一步请以单个 JSON 对象输出你的动作——直接以 { 开头, "
        "不要输出 [mmt_chat] 前缀或任何其他文字）"
    )})
    return engine, messages


def main() -> None:
    engine, messages = build_messages()
    client = LLMClient(base_url="http://localhost:1234/v1", api_key="lm-studio", model=MODEL)
    print(f"== 触发探针 == 角色={CHAR} 模型={MODEL} trials={TRIALS}", flush=True)
    print("（修复后 schema: 当面相见 + 软门槛 + 待实现标记）")
    counts: dict[str, int] = {}
    for i in range(TRIALS):
        # 本地 LM Studio 不认 response_format=json_object → 用 text + 本地提取
        raw_text = client.chat(messages, temperature=0.8, max_tokens=512,
                               response_format="text")
        print(f"\n=== trial #{i+1} raw ===")
        print(raw_text.strip()[:400])
        try:
            raw = extract_json(raw_text)   # 纯函数: direct/fence/extract, 不调 LLM
        except Exception as e:
            counts["EXTRACT_FAIL"] = counts.get("EXTRACT_FAIL", 0) + 1
            print(f"extract FAIL: {str(e)[:80]}")
            continue
        action, result = engine.registry.parse(raw)
        if action is None:
            tag = f"PARSE_FAIL: {'; '.join(result.errors)[:60]}"
            counts[tag] = counts.get(tag, 0) + 1
            print(f"\n#{i+1} {tag}")
            print(f"    raw: {json.dumps(raw, ensure_ascii=False)[:220]}")
            continue
        counts[action.action] = counts.get(action.action, 0) + 1
        try:
            exec_result = engine.executor.execute(action)
            exec_msg = f"exec OK: {exec_result.message[:60]}"
        except Exception as e:
            exec_msg = f"exec REJECT: {str(e)[:80]}"
        print(f"\n#{i+1} action={action.action} | reply={action.reply[:40]!r} | {exec_msg}")
        print(f"    payload={json.dumps(action.payload, ensure_ascii=False)}")
    print(f"\n== 汇总: {counts}")


if __name__ == "__main__":
    main()
