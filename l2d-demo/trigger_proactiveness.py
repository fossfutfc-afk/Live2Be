# -*- coding: utf-8 -*-
"""便利屋68 主动程度测试（问题1 规则验证, 2026-09-01）— 纯日常闲聊看触发。

对照官方剧情梗概（橘光缠着老师"girl on the train"）: 角色应自说自话制造
"当面见"的势, 不等老师表态。性格差异可接受: 睦月应高主动, 遥香/佳代子可差。

每角色: 新会话 + 4 轮中性日常闲聊（无 集合/见面/测试/羁绊 等关键词）。
记录每轮动作与回复摘要; 触发 mmt_trigger_bond_story 即停。

用法: python l2d-demo/trigger_proactiveness.py
"""
import os
import sys
from pathlib import Path

os.environ["NO_PROXY"] = "api.deepseek.com,*"
os.environ.setdefault("HTTPS_PROXY", "")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm.client import LLMClient                       # noqa: E402
from core.momotalk import MomoTalkEngine               # noqa: E402

CHARS = [
    ("rikuhachima_aru", "阿露"),
    ("asagi_mutsuki", "睦月"),
    ("onikata_kayoko", "佳代子"),
    ("igusa_haruka", "遥香"),
]
# 中性日常闲聊（不含触发词; 第 4 句"话说回来"给角色接话机会）
LINES = [
    "今天天气真不错呢",
    "作业好多，好累啊",
    "你最近在忙什么呀",
    "嗯嗯，话说回来……",
]


def main() -> None:
    llm = LLMClient()
    results: list[str] = []
    for char_id, display in CHARS:
        engine = MomoTalkEngine(ROOT / "config" / "characters", llm)
        engine.start_session(char_id)
        print(f"\n========== {display} ({char_id}) ==========")
        triggered = False
        proactive = False
        for i, line in enumerate(LINES):
            try:
                r = engine.agent_turn(line)
            except Exception as e:
                print(f"  轮{i+1} 异常: {e}")
                continue
            names = [a.get("action") for a in r.actions]
            reply = (r.reply or "").replace("\n", " ")[:70]
            print(f"  你: {line}")
            print(f"  她: {reply}")
            print(f"  动作: {names}")
            if "mmt_trigger_bond_story" in names:
                triggered = True
                break
            # 主动造势判定: 提议见面/邀请/约地点（无关键词触发但角色在拉近距离）
            if any(k in r.reply for k in ("当面", "过来", "一起", "去找你",
                                          "见面", "带你去", "来找", "约", "等我")):
                proactive = True
        verdict = "第N轮主动触发" if triggered else (
            "主动造势（提议见面/邀约）" if proactive else "全程被动（未触发未造势）")
        if triggered:
            verdict = f"第{i + 1}轮主动触发 ✓"
        print(f"  ==> {verdict}")
        results.append(f"{display}: {verdict}")
    llm.close()
    print("\n========== 汇总 ==========")
    for r in results:
        print("  " + r)


if __name__ == "__main__":
    main()
