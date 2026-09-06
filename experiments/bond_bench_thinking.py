# -*- coding: utf-8 -*-
"""bond 场景生成计时基准（真实 API, CLI 运行）——thinking 档位 A/B。

用法（在项目根）:
    python experiments/bond_bench_thinking.py --rounds 3 --thinking off,low,high

对每个档位: 新建 BondStoryEngine（与 webgui/CLI 同源）→ 跑 N 场
send_vn_scene → 打印每场耗时 / 段落数 / 每次 LLM 调用明细 → 档位汇总。

关键点:
  - 档位经包装器注入 extra_body={reasoning_effort: …}（off → {} 关闭思考），
    **不改 settings.toml**; default = 跟随 settings（当前通常 high）。
  - 走 chat_full 流式路径（同 webgui）——llm/client 的 INFO 日志
    `llm chat_full ms= ttft=` 会同步打出, 可据此看 TTFT。
  - annotate=True（同步标注）——纯测生成成本; webgui 标注在异步线程, 不挡首帧。
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

from core.bond.bond_story import BondStoryEngine  # noqa: E402
from llm.client import LLMClient  # noqa: E402

DEFAULT_SEED = "（旁白）放学后的教室里，老师来找遥香，今天想陪她多待一会儿。"


class BenchLLM:
    """包装真实 client: 按档位注入 reasoning_effort + 记录每次调用耗时。"""

    def __init__(self, inner, thinking: str | None):
        self._inner = inner
        self.thinking = thinking            # None=default(跟随 settings) | off/low/medium/high
        self.log: list[dict] = []

    def _extra(self):
        if self.thinking is None or self.thinking == "default":
            return None                     # client 默认（settings）
        if self.thinking == "off":
            return {}                       # 显式关闭思考
        return {"reasoning_effort": self.thinking}

    def _wrap(self, name):
        def _wrapped(messages, **kw):
            t0 = time.monotonic()
            if kw.get("extra_body") is None:
                kw["extra_body"] = self._extra()
            res = getattr(self._inner, name)(messages, **kw)
            self.log.append({
                "name": name,
                "ms": int((time.monotonic() - t0) * 1000),
                "chars": len(str(res)),
                "max_tokens": kw.get("max_tokens"),
            })
            return res
        return _wrapped

    def chat(self, messages, **kw):
        return self._wrap("chat")(messages, **kw)

    def chat_full(self, messages, **kw):
        return self._wrap("chat_full")(messages, **kw)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


def run_level(level: str | None, char_id: str, rounds: int, seed: str) -> dict:
    llm = BenchLLM(LLMClient(), level)
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session(char_id)
    inp = seed
    scenes = []
    print(f"\n===== thinking = {level or 'default(settings)'} =====")
    for i in range(1, rounds + 1):
        t0 = time.monotonic()
        try:
            scene = vn.send_vn_scene(inp)
        except Exception as e:                       # noqa: BLE001 — 单场失败继续
            print(f"  第 {i} 场 FAILED: {type(e).__name__}: {str(e)[:100]}")
            break
        dt_ms = int((time.monotonic() - t0) * 1000)
        scenes.append(dt_ms)
        print(f"  第 {i} 场: {dt_ms}ms  段落 {len(scene.paragraphs)}"
              f"  选项 {len(scene.choices or [])}")
        inp = (scene.choices[0] if scene.choices else "（继续）")
    calls = llm.log
    total_llm = sum(c.get("ms", 0) for c in calls)
    if calls:
        avg = total_llm / len(calls)
        print(f"  LLM 调用 {len(calls)} 次, 合计 {total_llm}ms, 均 {int(avg)}ms")
        for c in calls:
            print(f"    {c['name']}: {c['ms']}ms  输出 {c['chars']} 字符  "
                  f"max_tokens={c.get('max_tokens')}")
    return {"level": level, "scenes": scenes,
            "calls": len(calls), "llm_total_ms": total_llm}


def main() -> int:
    ap = argparse.ArgumentParser(description="bond 生成计时基准（thinking 档位 A/B）")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--thinking", default="off,low,high,default",
                    help="逗号分隔: off/low/medium/high/default(=settings)")
    ap.add_argument("--char", default="igusa_haruka")
    ap.add_argument("--seed", default=DEFAULT_SEED)
    args = ap.parse_args()

    levels = [x.strip() for x in args.thinking.split(",") if x.strip()]
    results = [run_level(lv, args.char, args.rounds, args.seed) for lv in levels]

    print("\n===== 汇总 =====")
    for r in results:
        scenes = r["scenes"]
        avg = sum(scenes) / len(scenes) if scenes else 0
        print(f"  thinking={r['level'] or 'default'}: 场均 {int(avg)}ms"
              f"（{len(scenes)} 场, 含同步标注 LLM {r['calls']} 次 "
              f"{r['llm_total_ms']}ms）")
    print("\n提示: chat_full 路径的 TTFT 见进程日志 'llm chat_full ms= ttft='。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
