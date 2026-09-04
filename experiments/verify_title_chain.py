# -*- coding: utf-8 -*-
"""实机链路验证（2026-09-05 B 线/A 线）: MMT 触发带 chapter_title → vn_enter 事件 →
bond_start 灌窗口 → 首场（章名命题 seed + 触发前对话在窗口）→ 场景落库（emotion 终态）
→ 收尾灌窗。跑在 tmp 世界线（不污染 world1）。
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.momotalk import MomoTalkEngine
from core.session import SessionStore
from core.session.renderer import render_bond_scene_text, window_messages
from core.ui.vn_cli import _trigger_title, run_bond_story_vn, wrapup_after_vn
from llm.client import LLMClient

CHAR = "igusa_haruka"
ROOT = Path("config/characters")

tmp = Path(tempfile.mkdtemp())
st = SessionStore(str(tmp), world_id="verify")
engine = MomoTalkEngine(ROOT, LLMClient(), store=st)

root = st.create(CHAR, "遥香")
engine.start_session(CHAR)
engine.attach_session(root.session_id)
print("=== 会话就绪:", tmp, "===")

# 对话引导触发（真实 LLM——给强邀约契机）
lines = [
    "遥香，今天放学后要不要一起去逛逛？我想看看你平时喜欢的地方。",
    "嗯，就是现在！走吧，我们出发吧！",
    "（遥香犹豫着点了点头）那我们边走边聊——你带路吧。",
]
triggered = False
for i, msg in enumerate(lines, 1):
    print(f"\n--- 玩家（引导 {i}）: {msg}")
    try:
        r = engine.agent_turn(msg)
    except Exception as e:
        print("turn 异常:", e)
        break
    if r.bond_story:
        print(f"!!! 第 {i} 条引导后触发羁绊剧情")
        triggered = True
        break
    if i == len(lines):                      # 引导耗尽仍没触发 → 再来一轮硬邀约
        try:
            r = engine.agent_turn("别犹豫了，把手给我——我们现在就去！")
            if r.bond_story:
                print("!!! 追加轮触发")
                triggered = True
        except Exception as e:
            print("追加轮异常:", e)
        break

if not triggered:
    print("== 未能触发（LLM 未选择 trigger）——检查最近回复 ==")
    print("trace 尾:", engine.trace[-1:] if engine.trace else None)
    sys.exit(1)

title = _trigger_title(engine)
print("\n=== trigger 章名: ", repr(title))
assert title, "trigger 应带 chapter_title"

# 窗口（bond 视角）: 触发前对话应在窗口里
evs = st.events(CHAR)
win = window_messages(evs)
print(f"\n窗口共 {len(win)} 条消息, 尾 4 条:")
for m in win[-4:]:
    print(f"  [{m['role']}] {m['content'][:80]}")
assert any("出发" in str(m["content"]) or "走" in str(m["content"])
           for m in win[-6:]), "窗口应含触发前邀约对话"

# 跑 bond（自动推进: 纯叙事场继续 / 有选项选第 1 个; 最多 4 场后退出）
print("\n=== 进入羁绊剧情 VN（自动推进, 至多 4 场）===")
auto = {"n": 0}

def input_fn_auto(prompt=""):
    auto["n"] += 1
    return "（继续）" if auto["n"] <= 4 else "b"

try:
    completed = run_bond_story_vn(engine, input_fn=input_fn_auto, store=st,
                                  end_rounds=6, remind_rounds=4, memorial_seed=42)
    print("bond 返回 completed =", completed, "（跑了", auto["n"], "轮输入）")
except Exception as e:
    print("VN 异常:", type(e).__name__, e)
    completed = False

# vn_enter 事件检查（run_bond_story_vn 内 enter_vn 写入——trigger 本身只放行）
evs = st.events(CHAR)
vn_enter = [e for e in evs if e.subtype == "vn_enter"]
print("vn_enter payload:", vn_enter[-1].payload if vn_enter else None)
assert vn_enter and (vn_enter[-1].payload or {}).get("chapter_title") == title, \
    "vn_enter 应带 chapter_title"

# 场景落库检查（emotion 终态 + 叙事提取）
evs = st.events(CHAR)
bonds = [e for e in evs if e.type == "bond"]
print(f"\n=== bond 事件 {len(bonds)} 条 ===")
for e in bonds[-2:]:
    paras = (e.payload or {}).get("paragraphs", [])
    emos = [p.get("emotion") for p in paras if isinstance(p, dict)]
    print(f"  {e.subtype}: {len(paras)} 句段, emotions={emos}")
    print(f"    title 在 payload: {'title' in (e.payload or {})}")
    text = render_bond_scene_text(e.payload)
    print(f"    渲染前 120 字: {text[:120]}")
    assert emos and all(emos), "落库场景句段应带 emotion（终态）"

# 收尾（wrapup 灌窗后 agent_turn）
print("\n=== 收尾（wrapup_after_vn）===")
try:
    wrapup_after_vn(engine, completed=completed)
    tail = st.events(CHAR)[-1]
    print("收尾事件:", tail.subtype, (tail.payload or {}).get("reply", "")[:60])
except Exception as e:
    print("收尾异常:", type(e).__name__, e)

print("\n=== 全部关键断言通过——链路正确写入 ===")
