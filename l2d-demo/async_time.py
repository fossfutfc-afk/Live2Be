# -*- coding: utf-8 -*-
"""异步标注时间实测: 玩家等待（busy=False）= 骨架生成; 标注完成（emo_version 变化）异步。"""
import sys, time, tempfile
from pathlib import Path
ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT))
from core.session import SessionStore
from core.momotalk import MomoTalkEngine
import webgui.bond as bond
import webgui.chat as chat
from webgui import deps
from llm.client import LLMClient

CHAR = "igusa_haruka"
st = SessionStore(Path(tempfile.mkdtemp()))
llm = LLMClient()
engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
engine.start_session(CHAR)
root = st.create(CHAR)
engine.attach_session(root.session_id)
chat._engines[CHAR] = engine
deps.set_store(st)          # C1a: store 接缝搬到了 webgui/deps（chat._store 已不存在）

bond.bond_start(CHAR, root.session_id)
t0 = time.time()
while bond.bond_status(CHAR, root.session_id)["busy"]:
    time.sleep(0.05)
t_scene = time.time() - t0
st0 = bond.bond_status(CHAR, root.session_id)
print(f"① 玩家等待（骨架生成）: {t_scene:.1f}s  段落 {len(st0['scene']['paragraphs'])}  emotion 齐全 {all(p.get('emotion') for p in st0['scene']['paragraphs'])}")
v0 = st0["emo_version"]
t1 = time.time()
while True:
    s = bond.bond_status(CHAR, root.session_id)
    if s["emo_version"] > v0:
        break
    if time.time() - t1 > 30:
        print("标注超时")
        break
    time.sleep(0.1)
print(f"② 标注异步完成（+{time.time()-t1:.1f}s）: emo_version {v0}→{s['emo_version']}")
print(f"   标注后段落 emotion: {[p.get('emotion') for p in s['scene']['paragraphs']]}")
print(f"   总（骨架+标注）: {time.time()-t0:.1f}s vs 之前同步 ~13s")
