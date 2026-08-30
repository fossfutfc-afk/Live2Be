# -*- coding: utf-8 -*-
"""两遍式 C 真实 LLM 冒烟: 骨架生成 → 批量标注 → 统计。

跑 3 场（seed → 选项/继续 → 继续），输出:
    每场耗时（骨架生成 + 标注的总时长）; 段落数; emotion 齐全度（词表内）;
    契约重试次数（trace.attempt——两遍式应几乎为零）; 内容/表情样本。

用法: python experiments/two_pass_real.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bond.bond_story import BondStoryEngine  # noqa: E402
from llm.client import LLMClient  # noqa: E402


def _stats(vn, scene, label):
    paras = scene.paragraphs
    emos = [p.get("emotion", "") for p in paras]
    in_lex = all(e in set(vn._lexicon_keys) for e in emos if e)
    retries = sum(1 for t in vn._trace if not t.get("parse_valid"))
    uniq = set(emos)
    print(f"[{label}] 段落 {len(paras)} | emotion 齐全 {all(emos)} "
          f"| 词表内 {in_lex} | 唯一表情 {len(uniq)} | 契约重试 {retries}")
    for p in paras:
        print(f"    {p.get('emotion', '?'):<12} {p.get('text', '')[:38]}")
    if scene.choices:
        print(f"    选项: {scene.choices}")
    return emos


def main():
    llm = LLMClient()
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session("igusa_haruka")
    print(f"角色词表键数: {len(vn._lexicon_keys)}  {vn._lexicon_keys[:8]}...")
    t0 = time.time()
    scene = vn.send_vn_scene("（旁白）放学后的教室里，老师来找遥香。")
    print(f"第 1 场生成总耗时: {time.time() - t0:.1f}s")
    _stats(vn, scene, "场1")
    inp = scene.choices[0] if scene.choices else "（继续）"
    t1 = time.time()
    scene2 = vn.send_vn_scene(inp)
    print(f"第 2 场生成总耗时: {time.time() - t1:.1f}s")
    _stats(vn, scene2, "场2")
    t2 = time.time()
    scene3 = vn.send_vn_scene("（继续）")
    print(f"第 3 场生成总耗时: {time.time() - t2:.1f}s")
    _stats(vn, scene3, "场3")
    print("\n总耗时:", round(time.time() - t0, 1), "s")
    print("history 轮数:", vn.history_length)


if __name__ == "__main__":
    main()
