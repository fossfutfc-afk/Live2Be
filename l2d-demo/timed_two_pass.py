# -*- coding: utf-8 -*-
"""两遍式耗时拆解: 包装 LLM client, 记录每次调用的耗时 + 输出大小。"""
import sys, time
from pathlib import Path
ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT))
from core.bond.bond_story import BondStoryEngine
from llm.client import LLMClient

class TimedLLM:
    """包装真实 client, 记录每次 chat 调用耗时/输出字符数。"""
    def __init__(self, inner):
        self._inner = inner
        self.log = []
    def chat(self, messages, **kw):
        t0 = time.time()
        r = self._inner.chat(messages, **kw)
        dt = time.time() - t0
        out = str(r)
        self.log.append({"dt": dt, "chars": len(out), "kw_max_tokens": kw.get("max_tokens"), "kind": "骨架" if kw.get("max_tokens", 0) > 1000 else "标注"})
        return r
    def format_messages(self, **kw):
        return self._inner.format_messages(**kw)

llm = TimedLLM(LLMClient())
vn = BondStoryEngine(ROOT / "config" / "characters", llm)
vn.start_session("igusa_haruka")
inp = "（旁白）放学后的教室里，老师来找遥香。"
for i in range(1, 3):
    t0 = time.time()
    try:
        scene = vn.send_vn_scene(inp)
        print(f"--- 第 {i} 场 总 {time.time()-t0:.1f}s 段落 {len(scene.paragraphs)} ---")
        inp = scene.choices[0] if scene.choices else "（继续）"
    except Exception as e:
        print(f"第 {i} 场 FAILED: {type(e).__name__}: {str(e)[:80]}")
        break
print("\n=== 调用耗时明细 ===")
for j, c in enumerate(llm.log):
    print(f"  调用{j+1}: {c['dt']:.1f}s  输出 {c['chars']} 字符  [{c['kind']}]")
