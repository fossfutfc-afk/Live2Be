# -*- coding: utf-8 -*-
"""A/B 对比: branch（两遍式 C + 异步标注）webgui 路径——玩家等待 = 骨架, 3 场。"""
import sys, time, tempfile
from pathlib import Path
ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT))
from core.session import SessionStore
from core.momotalk import MomoTalkEngine
import webgui.bond as bond
import webgui.chat as chat
from llm.client import LLMClient
from core.media.emotion_lexicon import load_emotion_lexicon

CHAR = "igusa_haruka"
LEX = set(load_emotion_lexicon(ROOT / "assets" / "illustration" / CHAR / "default").keys())
st = SessionStore(Path(tempfile.mkdtemp()))
engine = MomoTalkEngine(ROOT / "config" / "characters", LLMClient(), store=st)
engine.start_session(CHAR)
root = st.create(CHAR)
engine.attach_session(root.session_id)
chat._engines[CHAR] = engine
chat._store = st

def wait_scene():
    t0 = time.time()
    while bond.bond_status(CHAR, root.session_id)["busy"]:
        time.sleep(0.05)
    return time.time() - t0, bond.bond_status(CHAR, root.session_id)

def report(tag, s):
    paras = s["scene"]["paragraphs"]
    emos = [p.get("emotion", "") for p in paras]
    print(f"[{tag}] 玩家等待 {s['_t']:.1f}s | 段落 {len(paras)} | emotion 齐全 {all(emos)} "
          f"| 词表内 {all(e in LEX for e in emos if e)} | 唯一 {len(set(emos))} | emo_v {s['emo_version']}")
    for p in paras:
        print(f"    {p.get('emotion','?'):<12} {p.get('text','')[:36]}")

bond.bond_start(CHAR, root.session_id)
t, s = wait_scene(); s["_t"] = t
report("场1", s)
inp = s["scene"]["choices"][0] if s["scene"].get("choices") else "（继续）"
bond.bond_turn(CHAR, root.session_id, inp)
t, s = wait_scene(); s["_t"] = t
report("场2", s)
inp = s["scene"]["choices"][0] if s["scene"].get("choices") else "（继续）"
bond.bond_turn(CHAR, root.session_id, inp)
t, s = wait_scene(); s["_t"] = t
report("场3", s)
print("完成:", s["completed"])
