# -*- coding: utf-8 -*-
"""SceneStream P1 按段情绪标注 — 真实 LLM 验证（DESIGN_SCENE_STREAM §10 验收）。

隔离性: 纯引擎循环（不 attach SessionStore）→ **不写任何 events.jsonl**;
引擎历史在内存, 进程结束即销毁。中途中断也无残留（无重置需求）。

跑一段短剧情（≤6 板, 到 story_end 自然收尾; 未自然收尾则末板 system_note 强收）,
输出:
    - 每板: 自然段数 / 句数 / 标注调用数与总耗时（含重试）; 填充率与词表内占比;
    - 每段: scene_anno 日志（para/retry/fallback/carry→out, engine 自带）+
      调用级延迟（wrapper 计时, 含每次 LLM 往返）;
    - 汇总: 段均耗时 / 重试组数 / 兜底句数 / 缓存与 usage 见 INFO 日志;
    - 抽样: 段 2+ 的情境块（上段原文+carry）是否注入; 示范键合法性。

用法: python experiments/p1_text_annotate_real.py [seed]
依赖: settings.toml [llm]（真 API 配置）; 角色词表 assets/illustration/igusa_haruka。
"""
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bond.bond_story import BondStoryEngine, SceneLoopError  # noqa: E402
from llm.client import LLMClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

MAX_BOARDS = int(os.environ.get("P1_MAX_BOARDS", "6"))

# ---------------------------------------------------------------------------
# annotate_paragraph 调用级计时（monkeypatch 模块属性——engine 每次
# `from core.bond.emo_text import annotate_paragraph` 走同一模块命名空间）
# ---------------------------------------------------------------------------
import core.bond.emo_text as emo_text_mod  # noqa: E402

_ORIG = emo_text_mod.annotate_paragraph
ANNO_CALLS: list[dict] = []
RAW_DUMP = os.environ.get("P1_RAW", "0") == "1"


def _wrapped(llm, sentences, lexicon_keys, lexicon_hint, character,
             char_name, context, para_no, *, prev=None, max_tokens=None):
    # 原始输出抓取（P1_RAW=1）: 在 LLM 层旁路记录每次标注响应形状
    if RAW_DUMP and not getattr(llm, "_p1_spied", False):
        import re as _re
        orig_chat = llm.chat

        def _spy(messages, **kw):
            last = messages[-1]["content"] if len(messages) > 1 else ""
            m = _re.search(r"第 1\.\.(\d+) 句", last)
            expect = int(m.group(1)) if m else -1
            raw = orig_chat(messages, **kw)
            if "情绪标签数组" in last:
                import json as _json
                got = "?"
                if isinstance(raw, list):
                    got = len(raw)
                elif isinstance(raw, str):
                    try:
                        got = len(_json.loads(raw))
                    except Exception:                 # noqa: BLE001
                        got = f"str({raw[:60]!r}…)"
                print(f"    [raw] para={para_no} expect={expect} got={got}"
                      f" raw={str(raw)[:150]!r}")
            return raw

        llm.chat = _spy                       # 仅本进程内替换（实验旁路）
        llm._p1_spied = True
    t0 = time.monotonic()
    labels, info = _ORIG(
        llm, sentences, lexicon_keys, lexicon_hint, character,
        char_name, context, para_no, prev=prev, max_tokens=max_tokens)
    ANNO_CALLS.append({
        "dur_ms": (time.monotonic() - t0) * 1000,
        "n": len(sentences),
        "para_no": para_no,
        "info": dict(info),
        "prev": prev,
        "out": labels[-1] if labels else None,
        "context": context[:80],
    })
    return labels, info


emo_text_mod.annotate_paragraph = _wrapped


def main():
    seed = sys.argv[1] if len(sys.argv) > 1 else "（旁白）放学后的教室里，老师来找遥香。"
    llm = LLMClient()
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session("igusa_haruka")
    kset = set(vn._lexicon_keys)
    print(f"角色词表键数: {len(kset)}  {vn._lexicon_keys[:10]}")

    user_input = seed
    board_times = []
    for round_i in range(1, MAX_BOARDS + 1):
        system_note = None
        if round_i == MAX_BOARDS:
            system_note = (
                "（系统）已达剧情篇幅上限。本轮请改用 story_end 动作收尾"
                "结束剧情——收尾场景只有 paragraphs, 不再输出选项。"
            )
        t0 = time.monotonic()
        try:
            scene = vn.send_vn_scene(user_input, system_note=system_note)
        except SceneLoopError as e:
            print(f"[板{round_i}] SceneLoopError: {e} —— 中断")
            break
        total_ms = (time.monotonic() - t0) * 1000
        board_times.append(total_ms)
        segs = scene.segments or [len(scene.paragraphs)]
        emos = [p.get("emotion", "") for p in scene.paragraphs]
        in_lex = all(e in kset for e in emos) and all(emos)
        # 诊断: 段号区间 / 覆盖 / trace / 缺漏探针（再次 fill 看幂等短路还是补标）
        br_miss = {k: sum(1 for p in v if not p.get("emotion"))
                   for k, v in scene.branches.items()}
        body_miss = [i for i, p in enumerate(scene.paragraphs)
                     if not p.get("emotion")]
        print(f"\n[板{round_i}] dur={total_ms:.0f}ms 自然段={len(segs)} 句={len(emos)} "
              f"填充={len(emos) and all(emos)} 词表内={in_lex} "
              f"is_end={scene.is_end} choices={len(scene.choices)}")
        print(f"    segments={segs} 缺漏句={body_miss} 分支缺漏={br_miss} "
              f"trace_attempts={[t['attempt'] for t in vn._trace[-1:]]}")
        if body_miss or any(br_miss.values()):
            t1 = time.monotonic()
            again = vn.fill_scene_emotions_text(scene)   # 幂等/覆盖探针
            miss2 = [i for i, p in enumerate(scene.paragraphs)
                     if not p.get("emotion")]
            print(f"    !! 探针补标返回={again} dur={(time.monotonic() - t1) * 1000:.0f}ms "
                  f"仍缺={miss2}")
        for p in scene.paragraphs:
            print(f"    {p.get('emotion', '?'):<11} {p.get('text', '')[:40]}")
        if scene.is_end:
            break
        user_input = scene.choices[0] if scene.choices else "（继续）"

    # 标注汇总（ANNO_CALLS 在本进程累计全部段）
    retried = [c for c in ANNO_CALLS if c["info"].get("retry")]
    fallback = sum(c["info"].get("fallback", 0) for c in ANNO_CALLS)
    durs = sorted(c["dur_ms"] for c in ANNO_CALLS)
    n_calls = len(ANNO_CALLS)
    def pct(p):  # noqa: E306
        return durs[min(len(durs) - 1, int(len(durs) * p))]
    print("\n==== 按段标注汇总 ====")
    print(f"段标注调用 {n_calls} 次 | 重试组 {len(retried)} "
          f"| 兜底句总数 {fallback}")
    if durs:
        print(f"单次调用: min={durs[0]:.0f}ms p50={pct(0.5):.0f}ms "
              f"p95={pct(0.95):.0f}ms max={durs[-1]:.0f}ms | "
              f"标注总耗时(串行)={sum(durs):.0f}ms")
    for c in ANNO_CALLS:
        print(f"    para={c['para_no']:<3} n={c['n']} dur={c['dur_ms']:.0f}ms "
              f"retry={c['info'].get('retry')} fb={c['info'].get('fallback')} "
              f"carry={c['prev']}→{c['out']}")
    print(f"主生成(每板含标注串行): {['%.0f' % t for t in board_times]}")
    print(f"示例情境块: {ANNO_CALLS[1]['context'] if len(ANNO_CALLS) > 1 else '(仅1段)'}")


if __name__ == "__main__":
    main()
