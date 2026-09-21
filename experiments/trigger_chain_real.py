# -*- coding: utf-8 -*-
"""真实模型端到端验证 — 阿露 6 轮约出门场景 → 触发 → VN → 手机收尾。

用 .env 配置的真实模型（DeepSeek，支持 json_object）跑完整链路:
  agent_turn×N（复刻 data/sessions 阿露 session 的 user 轮次, 新 prompt 重新生成）
  → 观察哪一轮触发 mmt_trigger_bond_story → 切 VN（自动选第 1 项, 双层收尾兜底）
  → 收尾 → wrapup_after_vn 手机收尾

VN 走 run_bond_story_vn 本身（验证对象就是生产函数）:
  第 VN_REMIND 场注入「剩余轮数」提醒, 第 VN_END 场注入「上限务必收尾」,
  超过 VN_END+2 场仍未【完】→ 程序兜底收尾（completed=True）。

验证对象: 触发措辞修复 + 双层收尾兜底在真实模型上是否成立。
结论基准: 修前阿露 6 轮 + 言语引导仍 0 触发; 本地 qwen 探针 0/5 → 4/5;
          VN 模型几乎从不主动输出【完】（需双层兜底保证循环终结）。

⚠️ 会消耗少量真实 API token（约 8-12 次调用）。宁缺勿错——全程 try 包裹, 失败打印不崩。

用法: python experiments/trigger_chain_real.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.mmt.engine import MomoTalkEngine
from core.bond.bond_progress import BondProgress
from core.ui.vn_cli import run_bond_story_vn, wrapup_after_vn
from llm.client import LLMClient

ROOT = Path(__file__).resolve().parent.parent
CHAR = "rikuhachima_aru"
SESSION = ROOT / "data" / "sessions" / "rikuhachima_aru_2026-08-21_230115.json"

# VN 走 run_bond_story_vn 的双层收尾兜底（调试值: 15 提醒 / 22 建议收尾 / 24 硬兜底）
VN_REMIND, VN_END = 15, 22

VN_ONLY = "--vn-only" in sys.argv


def main() -> None:
    llm = LLMClient()   # 读 .env → DeepSeek
    print(f"模型: {llm.model}  base: {llm.base_url}")

    progress = BondProgress(ROOT / "data" / "basic" / "_chain_bp.json")
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, bond_progress=progress)
    engine.start_session(CHAR)

    trigger_turn, reason = None, ""
    if not VN_ONLY:
        sess = json.loads(SESSION.read_text(encoding="utf-8"))
        user_msgs = [m["content"] for m in sess["messages"] if m["role"] == "user"]
        print(f"复刻 session user 轮次: {len(user_msgs)} 条")

        for i, u in enumerate(user_msgs, 1):
            print(f"\n[轮 {i}] 用户: {u[:44]}")
            result = engine.agent_turn(u)
            print(f"    -> {result.action} | reply: {result.reply[:56]!r}")
            if result.bond_story:
                trigger_turn, reason = i, result.payload.get("reason", "")
                print(f"    *** 触发羁绊剧情 (第 {i} 轮), reason={reason!r}")
                break

        if trigger_turn is None:
            print("\n[追加触发轮] 历史内未触发, 补强约定碰面轮…")
            result = engine.agent_turn("好，我这就出发，柴关拉面店门口见！")
            print(f"    -> {result.action} | reply: {result.reply[:56]!r}")
            if not result.bond_story:
                print("\n✗ FAIL: 真实模型在 7 轮内仍未触发——措辞修复对 DeepSeek 无效?")
                sys.exit(1)
            trigger_turn, reason = len(user_msgs) + 1, result.payload.get("reason", "")
            print(f"    *** 触发羁绊剧情 (追加轮), reason={reason!r}")
    else:
        reason = "老师邀约外出用餐"
        print(f"[--vn-only] 跳过 MMT 复刻, 直测 VN (seed reason={reason!r})")

    # ---- VN 循环（双层收尾兜底, 调试值 15 提醒 / 22 建议收尾 / 24 硬兜底）----
    vn_max_tokens = 2048
    for m in sys.argv:
        if m.startswith("--max-tokens="):
            vn_max_tokens = int(m.split("=", 1)[1])
    seed = f"（旁白）基于「{reason}」……" if reason else None

    print("\n" + "═" * 46)
    print(f"  羁绊剧情 VN — {engine.current_character.display_name}")
    print("═" * 46)
    completed = run_bond_story_vn(engine, input_fn=lambda _: "1", char_ms=0,
                                  remind_rounds=VN_REMIND, end_rounds=VN_END,
                                  max_tokens=vn_max_tokens, seed=seed)
    print(f"\n  VN 结果: {'【完】/程序兜底收尾' if completed else '玩家退出'}")

    # ---- 手机收尾 ----
    print("\n[收尾] wrapup_after_vn …")
    wrapup_after_vn(engine)
    print("\n✅ 链路验证完成: 触发(第{}轮) → VN({}) → 手机收尾".format(
        trigger_turn, "收尾" if completed else "玩家退出"))

    progress_path = progress.path
    if progress_path.exists() and "_chain_bp.json" in str(progress_path):
        progress_path.unlink()   # 清理临时进度文件


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n✗ 验证脚本异常: {type(e).__name__}: {e}")
        sys.exit(1)
