# -*- coding: utf-8 -*-
"""端到端 BS 计时（真实 API, 同角色逐档 A/B）——MMT 触发 → bond 场景到收尾。

流程（每档）:
  1. 还原基线: events.jsonl ← events.bench.base.jsonl（用户裁剪的触发前状态）、
     progress.json ← 快照、删 soul/wiki.jsonl（记忆清空）
  2. MomoTalkEngine（mmt 侧用 settings 默认档）agent_turn(触发句) → 触发 bond,
     记触发轮耗时/章名
  3. BondStoryEngine（vn 侧按档注入 reasoning_effort）start_session + 灌窗口
     → send_vn_scene(annotate=False) 循环（选项取第一个/纯叙事继续）直到 is_end
  4. 汇总打印 RESULT 行; finally: 还原基线 + 删 wiki（本轮产生的记忆不留）

用法:
    python experiments/e2e_bs_bench.py --levels low,high [--trigger "我已经在门口了哦"]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bond.bond_story import BondStoryEngine  # noqa: E402
from core.mmt.engine import MomoTalkEngine  # noqa: E402
from core.session import SessionStore  # noqa: E402
from core.session.renderer import window_messages  # noqa: E402
from core.director.wiring import _build_director, _trigger_title  # noqa: E402  (C11: 真家)
from llm.client import LLMClient  # noqa: E402

CHAR_ROOT = ROOT / "config" / "characters"
DATA = ROOT / "data"
CHAR_DIR = DATA / "worlds" / "world1" / "characters" / "igusa_haruka"
SOUL = CHAR_DIR / "soul"
EVENTS = SOUL / "events.jsonl"
BASE_EVENTS = SOUL / "events.bench.base.jsonl"
WIKI = SOUL / "wiki.jsonl"
PROGRESS = CHAR_DIR / "progress.json"


class VnLLM:
    """bond 侧 LLM 包装: 按档注入 reasoning_effort（None = 跟随 settings）。"""

    def __init__(self, inner, level: str | None):
        self._inner = inner
        self.level = level          # None|'off'|'low'|'medium'|'high'
        self.log: list[dict] = []

    def _extra(self):
        if self.level is None:
            return None
        if self.level == "off":
            return {}
        return {"reasoning_effort": self.level}

    def _call(self, name, messages, kw):
        t0 = time.monotonic()
        if kw.get("extra_body") is None:
            kw["extra_body"] = self._extra()
        res = getattr(self._inner, name)(messages, **kw)
        self.log.append({"name": name,
                         "ms": int((time.monotonic() - t0) * 1000),
                         "chars": len(str(res))})
        return res

    def chat(self, messages, **kw):
        return self._call("chat", messages, kw)

    def chat_full(self, messages, **kw):
        return self._call("chat_full", messages, kw)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


def _snap(level: str, trigger: str, char_id: str) -> dict:
    """跑一档完整流程; 返回指标 dict。"""
    events_base = BASE_EVENTS.read_bytes() if BASE_EVENTS.is_file() else None
    if events_base is None:
        raise SystemExit("缺少基线快照 events.bench.base.jsonl——先建快照")
    progress_base = PROGRESS.read_bytes() if PROGRESS.is_file() else b""

    def restore():
        EVENTS.write_bytes(events_base)
        if progress_base:
            PROGRESS.write_bytes(progress_base)
        if WIKI.is_file():
            WIKI.unlink()                       # 记忆清空（含本轮产物）

    restore()                                   # 起跑即还原
    store = SessionStore(DATA)
    meta = store.create(char_id)                # 幂等: 已有 meta 直接返回
    sid = meta.session_id

    # ── MMT 触发（mmt 侧 = settings 默认档, 两档同基线）──────────
    mmt_llm = LLMClient()
    mmt = MomoTalkEngine(CHAR_ROOT, mmt_llm, store=store)
    mmt.start_session(char_id)
    mmt.attach_session(sid)
    title = ""
    trigger_ms = 0
    try:
        for attempt in range(1, 4):
            t0 = time.monotonic()
            r = mmt.agent_turn(trigger)
            trigger_ms = int((time.monotonic() - t0) * 1000)
            if r.bond_story:
                title = _trigger_title(mmt)
                break
        else:
            raise RuntimeError("3 次未触发 bond")
    except Exception as e:
        restore()
        raise

    # ── bond 场景（vn 侧按档注入）──────────────────────────────
    vn_llm = VnLLM(LLMClient(), level if level != "default" else None)
    vn = BondStoryEngine(CHAR_ROOT, vn_llm,
                         director=_build_director(mmt.current_character))
    vn.start_session(char_id)
    try:
        evs = store.events(char_id, sid)
        if evs:
            win = window_messages(evs)
            if win:
                vn._history = win               # 与 webgui 入场一致（含触发前对白）
    except Exception:
        pass

    seed = (f"（旁白）本章：{title}——从刚才的对话与契机自然展开。"
            if title else "（旁白）故事开始了……")
    inp = seed
    scenes: list[dict] = []
    try:
        for i in range(1, 13):                  # 上限 12 场防失控（正常应更早 is_end）
            t0 = time.monotonic()
            scene = vn.send_vn_scene(inp, annotate=False)
            dt = int((time.monotonic() - t0) * 1000)
            scenes.append({"round": i, "ms": dt,
                           "paras": len(scene.paragraphs),
                           "choices": len(scene.choices or [])})
            if scene.is_end:
                break
            inp = (scene.choices[0] if scene.choices else "（继续）")
        else:
            scenes.append({"round": "CLOSING_FORCED", "ms": 0, "paras": 0,
                           "choices": 0})
    finally:
        # 记忆/进度清理: 还原基线 + 删 wiki（用户约定: 跑完整个 bs 删 wiki）
        restore()

    return {
        "level": level,
        "title": title,
        "trigger_ms": trigger_ms,
        "scenes": scenes,
        "llm_calls": vn_llm.log,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="端到端 BS thinking A/B")
    ap.add_argument("--levels", default="low,high")
    ap.add_argument("--trigger", default="我已经在门口了哦")
    ap.add_argument("--char", default="igusa_haruka")
    args = ap.parse_args()

    results = []
    for lv in [x.strip() for x in args.levels.split(",") if x.strip()]:
        print(f"\n########## LEVEL = {lv} ##########", flush=True)
        try:
            r = _snap(lv, args.trigger, args.char)
            results.append(r)
            print(f"RESULT level={r['level']} title={r['title']!r} "
                  f"trigger_ms={r['trigger_ms']}")
            for s in r["scenes"]:
                print(f"RESULT scene round={s['round']} ms={s['ms']} "
                      f"paras={s['paras']} choices={s['choices']}")
            calls = r["llm_calls"]
            if calls:
                tot = sum(c["ms"] for c in calls)
                print(f"RESULT vn_llm_calls={len(calls)} vn_llm_total_ms={tot}")
        except Exception as e:                     # noqa: BLE001
            print(f"RESULT level={lv} ERROR {type(e).__name__}: {e}")

    print("\n===== 汇总（场景场均, ms）=====")
    for r in results:
        ms = [s["ms"] for s in r["scenes"]
              if isinstance(s.get("round"), int)]
        avg = sum(ms) / len(ms) if ms else 0
        print(f"  {r['level']}: 场均 {int(avg)}ms / {len(ms)} 场  "
              f"触发 {r['trigger_ms']}ms  标题 {r['title']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
