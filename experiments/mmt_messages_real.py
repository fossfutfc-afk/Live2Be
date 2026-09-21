# -*- coding: utf-8 -*-
"""真实模型实机测试 — 消息流协议 + 触发节奏 v2（引擎建议不拦截）。

验证对象（2026-09-02 最新协议）:
  1. 模型每轮是否输出合法消息流 {"messages": [{text|action}…]}
  2. 纯说话轮 / 自然节奏下 text 单元形态
  3. 话→图→话 交错（若模型自发发图——send_media 占位回灌也记录）
  4. trigger 新格式（text 邀约话 + 唯一 action 单元）——不设硬闸, 观察哪轮自然触发
  5. 时机注记: 第 1 轮应见「沉淀期」文案; 第 7 轮起应见「【剧情时机】」建议
  6. json 解析/重试/反馈是否干净（无结构错误循环）

用法: python experiments/mmt_messages_real.py   （约 7-9 次 LLM 调用）
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bond.bond_progress import BondProgress
from core.mmt.engine import MomoTalkEngine
from llm.client import LLMClient

ROOT = Path(__file__).resolve().parent.parent
CHAR = "igusa_haruka"          # 遥香——沉静内向, 不会乱触发

# 玩家话术序列: 日常闲聊 → 气氛铺垫 → 约出门（契机留给模型判断）
PLAYER_TURNS = [
    "你好呀遥香～今天过得怎么样？",
    "我刚忙完夏莱的工作，好累啊……",
    "对了，你上次说的那家甜品店后来去了吗？",
    "最近学习还顺利吗？社团那边忙不忙？",
    "说起来我们聊了这么多天，还没见过你真人呢，哈哈",
    "明天周末我打算去市中心逛逛，放空一下～",
    "要不要一起去？顺便吃个午饭，我请客！",
    "那就这么说定了！我现在出发去接你，到校门口啦，出来吧？",
]


def main() -> None:
    llm = LLMClient()
    print(f"模型: {llm.model}  base: {llm.base_url}\n")

    basic_dir = ROOT / "data" / "basic"
    basic_dir.mkdir(parents=True, exist_ok=True)     # data/ 被 gitignore——脚本自建
    progress = BondProgress(basic_dir / "_mmt_messages_bp.json")
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, bond_progress=progress)
    engine.start_session(CHAR)
    print(f"角色: {CHAR}（{engine.current_character.display_name}）")

    stats = {"turns": 0, "json_fail_retries": 0, "send_media": 0,
             "trigger": False, "legacy_format": 0, "notes": {}}
    trigger_turn = None

    for i, u in enumerate(PLAYER_TURNS, 1):
        note = engine._bond_progress_note()
        stats["notes"][i] = "建议" if "【剧情时机】" in note else "沉淀"
        print(f"\n=== [轮 {i}] 玩家: {u}")
        print(f"    注记: {note[:40]}…")

        t0 = time.time()
        try:
            result = engine.agent_turn(u)
        except Exception as e:                       # noqa: BLE001
            print(f"    ✗ 异常: {type(e).__name__}: {e}")
            continue
        dt = time.time() - t0
        stats["turns"] += 1

        acts = [a["action"] for a in result.actions]
        print(f"    → actions: {acts}  ({dt:.1f}s)")
        if result.reply:
            print(f"    → reply: {result.reply[:120]!r}")
        # 协议合规观察: 隐含 mmt_chat 前的动作都是 LLM 输出的真操作
        if any("send_media" in a for a in acts):
            stats["send_media"] += 1
        if result.bond_story:
            stats["trigger"] = True
            trigger_turn = i
            print(f"    *** 触发羁绊剧情! reason={result.payload.get('reason', '')!r}")
            break

        if i >= 6:
            # 轮 7/8 明确邀约与"已到校门口"——观察模型是否在【剧情时机】注记
            # （第 8 轮起 gap≥6）出现后响应建议并触发
            print("    （观察: 邀约轮——看模型是否响应注记建议触发）")

    print("\n" + "=" * 60)
    print(f"实机摘要: {stats['turns']} 轮 / 注记序列: "
          f"{'→'.join(f'轮{k}:{v}' for k, v in stats['notes'].items())}")
    print(f"send_media 出现: {stats['send_media']} 次 | 触发: "
          f"{'是(第 %d 轮)' % trigger_turn if stats['trigger'] else '否(8 轮内未自然触发)'}")
    if not stats["trigger"]:
        print("注: 不强迫触发是 v2 设计意图——引擎只建议, 触发权在模型; "
              "邀约达成仍未触发可能意味着『沉淀期』注记语气仍在抑制模型"
              "（下一轮迭代方向: 沉淀文案弱化为纯事实）")
    # 结构错误重试观察（agent_turn 内部已消化, 从 trace 无法直接数——看 LLM 调用次数
    # vs 轮数差异需 llm 层日志; 这里仅报告结果层面无异常即可）


if __name__ == "__main__":
    main()
