# -*- coding: utf-8 -*-
"""promptkit 卡 A/B 计时基准（真实 API, CLI 运行）——task 卡对生成速度的影响。

用法（项目根）:
    python experiments/promptkit_card_ab.py --rounds 4

对 card_on / card_off 两态（BondStoryEngine task_card 参数——settings
[promptkit].task_card 的设计初衷即 A/B 对照）: 同一角色/同一 seed, 各跑 N 场
send_vn_scene（annotate=False 隔离标注噪声——webgui 标注走异步线程）,
打印: 每场墙钟 / LLM 调用耗时 / TTFT（首 chunk）/ 输出字符数 / 段落·选项数 /
usage cache_hit·cache_miss（前缀缓存命中趋势——promptkit 抽盒后 system 前缀
逐字节稳定, 是本调整能加速的主要机制）。

注意: 缓存是服务端按前缀共享的——两程交替进行可对冲"后跑者吃缓存"偏差;
单看趋势（场内第 1 场 vs 后续）与两程均值的量级即可, 别把几 ms 差异当结论。
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

from core.bond.bond_story import BondStoryEngine  # noqa: E402
from llm import client as _llm_client  # noqa: E402
from llm.client import LLMClient  # noqa: E402

DEFAULT_SEED = "（旁白）放学后的教室里，老师来找遥香，今天想陪她多待一会儿。"


class BenchLLM:
    """包装真实 client: 记录每次调用的耗时 / TTFT / 输出长度 / usage 缓存命中。"""

    def __init__(self, inner: LLMClient):
        self._inner = inner
        self.log: list[dict] = []
        # TTFT 捕获: 包一层 SSE 观察者（首个 content chunk 即 ttft）——不改 client
        _orig_drain = inner._drain_stream

        def _drained(resp, on_chunk=None):
            t0 = time.monotonic()
            first: list[float | None] = [None]

            def _obs(c: str) -> None:
                if first[0] is None:
                    first[0] = time.monotonic() - t0
                if on_chunk is not None:
                    on_chunk(c)

            out = _orig_drain(resp, _obs)
            self.log[-1]["ttft_ms"] = int(first[0] * 1000) if first[0] is not None else -1
            return out

        inner._drain_stream = _drained

    def _wrap(self, name):
        def _wrapped(messages, **kw):
            entry = {"name": name, "ttft_ms": -1}
            self.log.append(entry)                     # 先占位（_drained 流式中途回填 ttft）
            t0 = time.monotonic()
            try:
                res = getattr(self._inner, name)(messages, **kw)
            except BaseException:
                self.log.pop()                          # 失败不留残条目
                raise
            usage = dict(_llm_client._LAST_USAGE or {})
            entry.update({
                "ms": int((time.monotonic() - t0) * 1000),
                "chars": len(str(res)),
                "max_tokens": kw.get("max_tokens"),
                "cache_hit": int(usage.get("prompt_cache_hit_tokens") or 0),
                "cache_miss": int(usage.get("prompt_cache_miss_tokens") or 0),
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


def run_mode(card_on: bool, char_id: str, rounds: int, seed: str) -> dict:
    llm = BenchLLM(LLMClient())
    vn = BondStoryEngine(ROOT / "config" / "characters", llm,
                         task_card=card_on)
    vn.start_session(char_id)
    inp = seed
    scenes: list[dict] = []
    print(f"\n===== task_card = {card_on} =====")
    for i in range(1, rounds + 1):
        t0 = time.monotonic()
        try:
            scene = vn.send_vn_scene(inp, annotate=False)
        except Exception as e:                       # noqa: BLE001 — 单场失败继续
            print(f"  第 {i} 场 FAILED: {type(e).__name__}: {str(e)[:120]}")
            break
        wall = int((time.monotonic() - t0) * 1000)
        call = llm.log[-1] if llm.log else {}
        scenes.append({
            "i": i, "wall_ms": wall,
            "llm_ms": call.get("ms", -1), "ttft_ms": call.get("ttft_ms", -1),
            "chars": call.get("chars", -1),
            "cache_hit": call.get("cache_hit", -1), "cache_miss": call.get("cache_miss", -1),
            "paras": len(scene.paragraphs), "choices": len(scene.choices or []),
            "is_end": scene.is_end,
        })
        print(f"  第 {i} 场: wall={wall}ms llm={call.get('ms', -1)}ms "
              f"ttft={call.get('ttft_ms', -1)}ms 输出 {call.get('chars', -1)} 字符 "
              f"cache_hit={call.get('cache_hit', 0)} miss={call.get('cache_miss', 0)}"
              f" | 段落 {len(scene.paragraphs)} 选项 {len(scene.choices or [])}"
              f"{' [END]' if scene.is_end else ''}")
        if scene.is_end:
            break
        inp = scene.choices[0] if scene.choices else "（继续）"
    return {"card_on": card_on, "scenes": scenes,
            "calls": len(llm.log), "llm_total_ms": sum(c.get("ms", 0) for c in llm.log)}


def main() -> int:
    ap = argparse.ArgumentParser(description="promptkit 卡 A/B 计时基准")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--char", default="igusa_haruka")
    ap.add_argument("--seed", default=DEFAULT_SEED)
    args = ap.parse_args()

    # 顺序对冲缓存偏差: 平均两程（on/off 谁先跑谁略吃亏/占便宜）, 均值说明量级
    results = [run_mode(c, args.char, args.rounds, args.seed) for c in (True, False)]

    print("\n===== 汇总 =====")
    for r in results:
        scenes = r["scenes"]
        if not scenes:
            print(f"  card={r['card_on']}: 无完成场次")
            continue
        avg_wall = sum(s["wall_ms"] for s in scenes) / len(scenes)
        avg_llm = sum(s["llm_ms"] for s in scenes) / len(scenes)
        ttfts = [s["ttft_ms"] for s in scenes if s["ttft_ms"] > 0]
        avg_ttft = sum(ttfts) / len(ttfts) if ttfts else -1
        hits = [s for s in scenes if s["cache_hit"] > 0]
        hit_rate = len(hits) / len(scenes)
        print(f"  card={r['card_on']}: 场均 wall={int(avg_wall)}ms / llm={int(avg_llm)}ms"
              f" / ttft={int(avg_ttft)}ms（{len(scenes)} 场; "
              f"缓存命中场次 {len(hits)}/{len(scenes)} = {hit_rate:.0%}; "
              f"LLM 调用合计 {r['llm_total_ms']}ms）")
    print("\n提示: 卡只加 ~50-100 token/场——速度机制在缓存命中与少走错重试;")
    print("     卡开/关的内容差异（会不会少废话/少重试）请看进程日志与输出字符数。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
