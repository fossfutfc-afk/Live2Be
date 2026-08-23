# -*- coding: utf-8 -*-
"""端到端冒烟 — 真实 LLM 跑通 MMT → bond story → 正常结束, 记录对话 md。

验证板块（2026-08-23 架构）:
    MMT 动作列表（{"actions":[...]} 混合节奏）
    bond 契约（paragraphs 内联 emotion / place）→ BondScene → para_emotions
    导演（place → background 查表）
    vn_cli run_bond_story_vn（段落渲染 + [表情] 标注 + 选项）
    事件流存档（root MMT 会话 + bond 子会话 open_vn/events/markers）
    wrapup 手机收尾

用法: python experiments/e2e_smoke.py
产出: experiments/recordings/e2e_{ts}.md
"""
import io
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.client import LLMClient
from core.momotalk import MomoTalkEngine
from core.session import SessionStore
from core.ui.vn_cli import run_bond_story_vn, wrapup_after_vn

CHAR = sys.argv[1] if len(sys.argv) > 1 else "igusa_haruka"
# 默认 igusa_haruka; 可传参覆盖: python experiments/e2e_smoke.py <char_id>
# （需该角色有 emotions.yml; 目前: igusa_haruka / rikuhachima_aru / onikata_kayoko / asagi_mutsuki）
ROOT = Path(__file__).resolve().parent.parent


def _auto_input(prompt: str = "") -> str:
    """VN 自动推进: 有选项 → 选第一个; 无选项 → 固定一句话。"""
    return "1" if "选择" in prompt else "继续聊聊吧"


def main() -> None:
    llm = LLMClient()
    store = SessionStore()
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=store)
    engine.start_session(CHAR)
    char = engine.current_character
    root = store.create(CHAR, char.display_name)
    engine.attach_session(root.session_id)

    md: list[str] = []
    md.append(f"# Live2Be 端到端冒烟记录 — {char.display_name}")
    md.append("")
    md.append(f"> 时间: {datetime.now().isoformat()} ｜ 引擎: {llm.model}")
    md.append("")
    md.append("## 一、MomoTalk 对话")
    md.append("")

    inputs = ["你好呀，今天过得怎么样？", "我们一起去天台走走吧？", "最近在忙什么呀？"]
    triggered = False
    for i, u in enumerate(inputs, 1):
        print(f"\n=== MMT 轮 {i}: {u} ===")
        md.append(f"**sensei**: {u}")
        md.append("")
        try:
            r = engine.agent_turn(u)
        except Exception as e:                     # noqa: BLE001
            print(f"  [异常] {e}")
            md.append(f"（本轮异常: {e}）")
            continue
        for a in r.actions:
            line = f"- **{char.display_name}**: {a['reply']}" if a["reply"] else f"- [动作 {a['action']}]"
            md.append(line)
            print(f"  {a['action']}: {a['reply'][:44] if a['reply'] else '(无对白)'}")
        if r.bond_story:
            triggered = True
            break

    md.append("")
    md.append("## 二、羁绊剧情（VN）")
    md.append("")
    if not triggered:
        print("\n=== 测试捷径: 3 轮内 LLM 未自然触发 → 脚本强制进入 VN（真实引擎由 LLM 触发）===")
        md.append("> （测试捷径: 为覆盖 VN 板块, 脚本在 LLM 未自然触发时强制进入;\n"
                  ">  真实引擎中触发由 LLM 决定——mmt_trigger_bond_story 动作独占一轮, 轮数仅软门槛）")
        md.append("")

    reason = f"老师约{char.display_name}放学后见面聊聊"
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            completed = run_bond_story_vn(
                engine, input_fn=_auto_input, char_ms=0,
                remind_rounds=5, end_rounds=8, store=store)
        print(buf.getvalue())
        md.append("```")
        md.append(buf.getvalue().rstrip("\n"))
        md.append("```")
        md.append("")
        md.append(f"VN completed = {completed}")
        md.append("")

        print("\n=== 手机收尾 wrapup ===")
        buf = io.StringIO()  # 清空, 避免 md 重复 VN 渲染
        with redirect_stdout(buf):
            wrapup_after_vn(engine, reason)
        print(buf.getvalue())
        md.append("## 三、手机收尾（wrapup）")
        md.append("")
        md.append("```")
        md.append(buf.getvalue().rstrip("\n"))
        md.append("```")
    except Exception as e:                          # noqa: BLE001
        print(f"  [VN 异常] {e}")
        md.append(f"（VN 异常: {e}）")

    # 事件流验证
    md.append("")
    md.append("## 四、事件流存档（验证）")
    md.append("")
    char_dir = ROOT / "data" / CHAR / "sessions"
    if char_dir.exists():
        for sid_dir in sorted(char_dir.iterdir()):
            if not sid_dir.is_dir():
                continue
            evs = store.events(CHAR, sid_dir.name)
            subs = [e.subtype for e in evs]
            md.append(f"- 会话 `{sid_dir.name}`: {len(evs)} 事件")
            md.append(f"  - 类型序列: {', '.join(subs[:12])}{' …' if len(subs) > 12 else ''}")
    opens = store.list_open()
    md.append(f"- 未结束会话（可恢复）: {len(opens)} 个")
    md.append("")

    out = ROOT / "experiments" / "recordings" / f"e2e_{datetime.now():%Y%m%d_%H%M%S}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"\n对话记录已写入: {out}")


if __name__ == "__main__":
    main()
