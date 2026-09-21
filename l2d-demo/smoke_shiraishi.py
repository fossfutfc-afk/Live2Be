# -*- coding: utf-8 -*-
"""白石心（shiraishi_kokoro）冒烟测试 — 真 LLM 验证"用语言直接触发剧情测试"。

流程:
    1. MomoTalk 会话: 测试者指令"我们来测试一下羁绊剧情吧" → 断言 mmt_trigger_bond_story
    2. run_bond_story_vn（CLI 模式）: seed 覆盖注入"安排纪念时刻"指令,
       输入交替 "1"/"（继续）" 推进（read_choice 支持数字索引; 无效时自愈）
    3. 事件流断言: memorial_enter / memorial_exit marker 是否出现

用法: python l2d-demo/smoke_shiraishi.py [--image]
"""
import json
import os
import sys
from pathlib import Path

# 直连 DeepSeek（系统代理可能失效——NO_PROXY 绕过, 同 l2d-demo/_noproxy.py）
os.environ["NO_PROXY"] = "api.deepseek.com,*"
os.environ.setdefault("HTTPS_PROXY", "")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm.client import LLMClient                      # noqa: E402
from core.mmt.engine import MomoTalkEngine              # noqa: E402
from core.session import SessionStore                 # noqa: E402
from apps.vn_cli import run_bond_story_vn          # noqa: E402

CHAR = "shiraishi_kokoro"


def main() -> None:
    with_image = "--image" in sys.argv
    llm = LLMClient()
    store = SessionStore(ROOT / "data")
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=store)
    engine.start_session(CHAR)
    sid = engine._session_id

    print(f"\n========== 1) MomoTalk: 用语言触发羁绊剧情 ==========")
    r = engine.agent_turn("我们来测试一下羁绊剧情吧——请发起一次剧情场景测试！")
    names = [a.get("action") for a in r.actions]
    print(f"[回复] {r.reply}")
    print(f"[动作] {names}")
    if "mmt_trigger_bond_story" not in names:
        print("[FAIL] 未触发 mmt_trigger_bond_story——测试角色人设未生效")
        llm.close()
        sys.exit(1)
    print("[OK] 触发成功——测试角色直接配合发起剧情测试")

    print(f"\n========== 2) 羁绊剧情（CLI 模式, 真 LLM） ==========")
    if with_image:
        from llm.image_gen import ImageGenerator
        image_gen = ImageGenerator()
        print(f"[生图] API 模式: {image_gen.is_api_mode}")
    else:
        image_gen = None
        print("[生图] 纯文字模式（--image 可开真生图）")

    # 首场种子: 覆盖旁白——把"安排纪念时刻"指令直接送进 LLM 上下文
    seed = ("（旁白）基于「测试纪念时刻」……测试者指令: 本次剧情测试请安排一次"
            "值得纪念的时刻——剧本走到升华瞬间时执行纪念立绘渲染测试。")
    # 输入交替 数字1(选项)/（继续）: read_choice 支持数字索引;
    # 无效选择会重问并消费下一输入——交替序列自动自愈
    seq = ["1", "（继续）"] * 8

    def input_fn(_prompt=""):
        return seq.pop(0) if seq else "b"

    try:
        completed = run_bond_story_vn(
            engine, input_fn=input_fn, seed=seed,
            remind_rounds=30, end_rounds=50,
            image_gen=image_gen, store=store)
        print(f"[结束] completed={completed}")
    except Exception as e:
        print(f"[异常] {e}")

    # 事件流检查 memorial marker（bond 事件流与 CLI 同构落库）
    try:
        evs = store.events(CHAR, sid)
    except Exception:
        evs = []
    subs = [(e.type, e.subtype) for e in evs]
    bond_subs = [s for t, s in subs if t == "bond"]
    print(f"[bond 事件序列] {bond_subs}")
    has_mem_enter = ("marker", "memorial_enter") in subs
    has_mem_exit = ("marker", "memorial_exit") in subs
    if has_mem_enter:
        print("[OK] memorial_enter 已触发——纪念子模式链路可用")
        if has_mem_exit:
            print("[OK] memorial_exit 已触发——状态机完整走通")
    else:
        print("[INFO] 本次未触发 memorial（规则谨慎使用）——可重跑或加强 seed 指令")
    # 每场剧情摘要（首段文本）
    for e in evs:
        if e.type == "bond":
            paras = (e.payload or {}).get("paragraphs") or []
            first = paras[0].get("text", "") if isinstance(paras[0], dict) else str(paras[0] if paras else "")
            print(f"  · {e.subtype}: {first[:48]}")

    llm.close()
    print("\n========== 冒烟结束 ==========")


if __name__ == "__main__":
    main()
