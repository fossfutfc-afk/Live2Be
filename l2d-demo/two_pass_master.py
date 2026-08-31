# -*- coding: utf-8 -*-
"""主分支（内联 emotion）对比跑法——兼容版（无 _lexicon_keys, 容错）。
用法: python l2d-demo/two_pass_master.py
"""
import sys, time
from pathlib import Path
ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT))
from core.bond.bond_story import BondStoryEngine
from core.media.emotion_lexicon import load_emotion_lexicon
from llm.client import LLMClient

def keys():
    try:
        return list(load_emotion_lexicon(ROOT / "assets" / "illustration" / "igusa_haruka" / "default").keys())
    except Exception:
        return []

def stats(vn, scene, label):
    paras = scene.paragraphs
    emos = [p.get("emotion", "") for p in paras]
    lex = set(keys())
    in_lex = all(e in lex for e in emos if e)
    retries = sum(1 for t in vn._trace if not t.get("parse_valid"))
    print(f"[{label}] 段落 {len(paras)} | emotion 齐全 {all(emos)} | 词表内 {in_lex} | 唯一表情 {len(set(emos))} | 契约重试 {retries}")
    for p in paras:
        print(f"    {p.get('emotion','?'):<12} {p.get('text','')[:38]}")

def main():
    llm = LLMClient()
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session("igusa_haruka")
    print(f"词表键数: {len(keys())}")
    inp = "（旁白）放学后的教室里，老师来找遥香。"
    for i in range(1, 4):
        t0 = time.time()
        try:
            scene = vn.send_vn_scene(inp)
            print(f"第 {i} 场生成总耗时: {time.time()-t0:.1f}s")
            stats(vn, scene, f"场{i}")
            inp = scene.choices[0] if scene.choices else "（继续）"
        except Exception as e:
            print(f"第 {i} 场 FAILED: {type(e).__name__}: {str(e)[:100]}")
            break

main()
