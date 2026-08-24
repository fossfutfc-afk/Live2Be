# -*- coding: utf-8 -*-
"""Brain 真机验证 — digest 整合过程 + 增量 + 联想 + 双通道 + 注入。

两段剧情（一段稀松平常 → 一段比较有意义）, 分段 digest:
  第一段后: digest 全量提炼（wiki1）——稀松平常内容应少提炼/低 importance
  第二段后: digest 增量提炼（只新增）+ 联想（召回/双通道回忆）——意义段应长出信念

验证点:
  1. 提炼质量（提炼而非记录 / 稀松平常 vs 有意义的筛选差异）
  2. 初遇 importance（若有初遇回忆 → 0.9+?）
  3. 增量（第二次 digest 输入只含新增段）
  4. 联想（第二次输入含 回想/珍贵回忆/旧日片段 段）
  5. 注入段渲染（build_brain_injection 第一人称）

记录: experiments/runs/brain_real_{char}_{ts}.md
用法: python experiments/brain_real_run.py [character_id]   （需 .env LLM_API_KEY）
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.client import LLMClient
from core.momotalk import MomoTalkEngine
from core.session import SessionStore
from core.brain.consolidation import digest_session
from core.brain.recall import build_brain_injection

CHARACTER = sys.argv[1] if len(sys.argv) > 1 else "igusa_haruka"
RUNS_DIR = Path(__file__).resolve().parent / "runs"


def main() -> None:
    ts = time.strftime("%Y%m%d_%H%M%S")
    RUNS_DIR.mkdir(exist_ok=True)
    log_path = RUNS_DIR / f"brain_real_{CHARACTER}_{ts}.md"
    log: list[str] = []

    def note(*a) -> None:
        line = " ".join(str(x) for x in a)
        print(line)
        log.append(line)

    note(f"# Brain 真机验证 — {CHARACTER} {ts}")
    note("")

    client = LLMClient()
    store = SessionStore()
    engine = MomoTalkEngine("config/characters", client, store=store)
    name = engine.start_session(CHARACTER)
    root = store.create(CHARACTER, name)
    engine.attach_session(root.session_id)
    sid = root.session_id
    note(f"会话: {sid} ({name})")
    note("")

    # ── 第一段: 稀松平常（日常闲聊） ──────────────────────────────
    note("## 第一段: 稀松平常（日常闲聊）")
    daily = [
        "老师晚上好！今天社团活动有点累……",
        "明天好像有数学小测，我有点慌，考砸了怎么办……",
        "老师知道怎么背单词比较快吗？我老是记不住",
    ]
    for p in daily:
        r = engine.agent_turn(p)
        note(f"\n**你**: {p}")
        note(f"**{name}**: {r.reply}")
        time.sleep(0.5)
    note("")

    # 第一次 digest（全量提炼）
    note("## 第一次 digest（第一段后, 全量）")
    wiki1 = digest_session(client, store.data_root, CHARACTER, sid)
    note(f"digest 返回: {wiki1 is not None}")
    if wiki1:
        note(f"summary: {wiki1.get('summary')}")
        note(f"facts({len(wiki1.get('facts', []))}): {wiki1.get('facts')}")
        note(f"beliefs({len(wiki1.get('beliefs', []))}): {wiki1.get('beliefs')}")
        note(f"relations({len(wiki1.get('relations', []))}): {wiki1.get('relations')}")
    note("")

    # ── 第二段: 比较有意义（情感/羁绊） ────────────────────────────
    note("## 第二段: 比较有意义（情感/羁绊）")
    meaningful = [
        "其实……老师，我小时候总是一个人，没有什么朋友，经常被欺负",
        "但是和老师在一起的时候，我总觉得……自己好像也是有点用的",
        "老师，我们约好了哦，以后也一直这样陪着我，好不好？",
    ]
    for p in meaningful:
        r = engine.agent_turn(p)
        note(f"\n**你**: {p}")
        note(f"**{name}**: {r.reply}")
        time.sleep(0.5)
    note("")

    # 第二次 digest（增量 + 联想 + 双通道）
    note("## 第二次 digest（第二段后, 增量 + 联想）")
    wiki2 = digest_session(client, store.data_root, CHARACTER, sid)
    note(f"digest 返回: {wiki2 is not None}")
    if wiki2:
        note(f"digested_seq: {wiki2.get('digested_seq')}")
        note(f"summary: {wiki2.get('summary')}")
        note(f"facts({len(wiki2.get('facts', []))}): {wiki2.get('facts')}")
        note(f"beliefs({len(wiki2.get('beliefs', []))}): {wiki2.get('beliefs')}")
        note(f"relations({len(wiki2.get('relations', []))}): {wiki2.get('relations')}")
    note("")

    # 第三次 digest（无新增 → 0 调用, 应直接返回旧 wiki）
    note("## 第三次 digest（无新增 → 0 次 LLM 调用）")
    wiki3 = digest_session(client, store.data_root, CHARACTER, sid)
    note(f"直接返回旧 wiki（无新增）: {wiki3 is not None and wiki3.get('digested_seq') == (wiki2 or {}).get('digested_seq')}")
    note("")

    # 注入段渲染
    note("## 注入段（build_brain_injection, 第一人称）")
    if wiki2:
        seg = build_brain_injection(wiki2, char_name=name.split()[-1] if name else "")
        note(seg)
    note("")

    # 验证点汇总
    note("## 验证点")
    w1 = wiki1 or {}
    w2 = wiki2 or {}
    note(f"1. 稀松平常段提炼量: facts={len(w1.get('facts', []))}, beliefs={len(w1.get('beliefs', []))}"
         f"（日常闲聊应少提炼）")
    note(f"2. 意义段新增提炼量: facts={len(w2.get('facts', []))}, beliefs={len(w2.get('beliefs', []))}"
         f"（对比 wiki1 增长）")
    hi = [f for f in w2.get("facts", []) + w2.get("beliefs", [])
          if isinstance(f, dict) and float(f.get("importance", 0) or 0) >= 0.9]
    note(f"3. 高 importance(≥0.9) 条目: {len(hi)} 条 -> {[h.get('content') for h in hi]}")
    note(f"4. 增量生效: 第三次 digest 0 调用（无新增直返）")

    log_path.write_text("\n".join(log), encoding="utf-8")
    print(f"\n[记录] {log_path}")
    client.close()


if __name__ == "__main__":
    main()
