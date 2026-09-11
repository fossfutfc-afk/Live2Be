# -*- coding: utf-8 -*-
"""web E2E 桩世界 — 真 FastAPI app + 桩 LLM + 临时世界线（浏览器级冒烟的底座）。

**为什么不直接用真 LLM**: 浏览器级冒烟要把"界面链路"与"模型发挥"分开——桩 LLM
让每一步都可预期、零成本、可反复跑; 真 LLM 的时序/内容问题属另一层验收
（见 docs/EXEC_BOND_LATENCY.md 的真机数据）。

**隔离**: 事件流落 `.testtmp/webtest/run-*/data`（临时 SessionStore 注入
`webgui.chat`）——绝不写真实 data/; settings.toml 只读（生图默认已被
tests/conftest 的开关关掉这里不适用, 故这里显式置 `LIVE2BE_IMAGE=off`）。

用法（一般由 run.py 调, 也可单独起）:
    python experiments/web_e2e/stub_world.py --port 0
    → 打印 `E2E_URL=http://127.0.0.1:PORT` 后阻塞服务
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

#: 生图总开关: 界面冒烟绝不出图（纪念场景走纯文字降级）
os.environ.setdefault("LIVE2BE_IMAGE", "off")

CHARACTER = "igusa_haruka"
CHAPTER_TITLE = "放学后的约定"

#: 记录流 v2 桩块（板 = switch/正文/选项 → 收尾板[多段!]）
#: **收尾板故意放多段**——2026-09-11 真机 bug: is_end 板点击=直接 finish 而非
#: 推进段落, 导致"最后一段只看到第一句就退出 VN"。冒烟必须能抓住它。
BOND_BLOCK = "\n".join([
    '{"stage": "switch", "text": "教室"}',
    f'{{"character": "{CHARACTER}", "text": "（她抬起头，指尖还沾着粉笔灰。）老师……你来了。"}}',
    '{"character": "sensei", "text": "我来了。"}',
    '{"character": "sensei", "text": "再等一会儿。"}',
    f'{{"character": "{CHARACTER}", "text": "（她愣了一下，随即笑起来。）嗯……那我等你。"}}',
    f'{{"character": "{CHARACTER}", "text": "（收尾一）谢谢您，老师……！"}}',
    '{"character": "narrator", "text": "（收尾二：她用力地鞠了一躬。）"}',
    '{"stage": "end", "text": "（收尾三：她抱着那本笔记站在门口，一直挥着手。）"}',
])
#: 预生成/续写兜底块（若待发板被耗尽还有请求 → 纯叙事板, 不炸）
BOND_FALLBACK = "\n".join([
    f'{{"character": "{CHARACTER}", "text": "（窗外的天色又暗了一点。）"}}',
    '{"stage": "end", "text": ""}',
])
MMT_TRIGGER = {"messages": [
    {"text": "我们当面说吧！"},
    {"action": "mmt_trigger_bond_story",
     "payload": {"reason": "邀约", "chapter_title": CHAPTER_TITLE}},
]}
MMT_REPLY = {"messages": [{"text": "嗯……我、我其实很开心的！"}]}
#: 羁绊收尾话（wrapup）——文本独立, 冒烟据此断言"收尾气泡不用切页就能到"
WRAPUP_REPLY = {"messages": [{"text": "（收尾话）老师，今天真的很谢谢你。"}]}


class StubLLM:
    """按 system prompt 分流: MMT 轮 / bond 生成 / 标注 / digest, 全部离线可预期。"""

    def __init__(self):
        self.mmt_calls = 0
        self.bond_calls = 0
        self.calls: list[str] = []          # 调用形态留痕（冒烟报告里看得见）

    # -- 内部 ---------------------------------------------------------------
    @staticmethod
    def _last_note(messages) -> str:
        for m in reversed(messages):
            c = m.get("content")
            if m.get("role") == "user" and isinstance(c, str):
                return c
        return ""

    def _side_effect(self, system: str, note: str):
        """标注/digest 旁路 → 合法空应答（不消耗主生成脚本）。"""
        if "情绪标签" in note:
            m = re.search(r"恰 (\d+) 项", note)
            return ["nomal"] * (int(m.group(1)) if m else 1)
        if "变更句数组" in note:
            return []
        if "地点 id JSON" in note:
            return {"place": ""}
        if "记录员" in system:
            return {"episodes": []}
        if "整理者" in system:
            return {"decisions": [], "evidence": [], "affection_exp_delta": 0}
        return None

    # -- 契约（引擎只要求这两个方法）-----------------------------------------
    def chat(self, messages, temperature=0.8, max_tokens=4096,
             response_format="text", **kw):
        system = messages[0]["content"] if messages else ""
        note = self._last_note(messages)
        side = self._side_effect(system, note)
        if side is not None:
            self.calls.append("side")
            return side
        # 全量文本（system_note 可能落在 system 段或独立 system 消息里——收尾轮
        # 的判据是"这段剧情刚结束/只进行到一半"这个**注记**, 不只看最后一条 user）
        joined = "\n".join(str(m.get("content") or "") for m in messages)
        if "mmt_chat" in system or "MomoTalk" in system:
            self.mmt_calls += 1
            self.calls.append(f"mmt#{self.mmt_calls}")
            if self.mmt_calls == 1:
                return MMT_TRIGGER         # 第一轮即触发羁绊剧情（界面走全链）
            if "羁绊剧情刚刚结束" in joined or "只进行到一半" in joined:
                return WRAPUP_REPLY        # 收尾话（wrapup 轮）——区别于普通回复
            return MMT_REPLY
        self.bond_calls += 1
        self.calls.append(f"bond#{self.bond_calls}")
        return BOND_BLOCK if self.bond_calls == 1 else BOND_FALLBACK

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


def build_world(data_root: Path):
    """临时世界线 + 注入 chat（引擎/store 都指向 data_root）。

    **硬隔离（2026-09-11 事故）**: 冒烟会在登录页取名 → `POST /api/name` →
    `mmt_preset.save_player_name()` 写的是**模块级常量 PLAYER_JSON**（真实
    `data/basic/player.json`）——冒烟曾把用户自己的名字覆盖成"老师"（用户报障
    "填名字总在后面追加老师"就是它的后遗症: 登录框预填了被污染的名字）。
    这里把 PLAYER_JSON / AFFECTION / 进度等**所有全局落盘点**都改到临时目录。

    Returns: (store, session_id, engine, llm)
    """
    from core.mmt import mmt_preset
    from core.momotalk import MomoTalkEngine
    from core.session import SessionStore
    from webgui import chat

    data_root.mkdir(parents=True, exist_ok=True)
    basic = data_root / "basic"
    basic.mkdir(parents=True, exist_ok=True)
    # 玩家名等全局文件 → 临时目录（否则冒烟会改写真实 data/basic/*）
    mmt_preset.PLAYER_JSON = basic / "player.json"

    st = SessionStore(data_root)
    llm = StubLLM()
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=st)
    engine.start_session(CHARACTER)
    sid = st.create(CHARACTER).session_id
    engine.attach_session(sid)
    chat._engines[CHARACTER] = engine
    chat._store = st
    return st, sid, engine, llm


def serve(port: int = 0, data_root: Path | None = None, ready_timeout: float = 20.0):
    """起 uvicorn（后台线程）→ (url, server, session_id, llm); port=0 → 随机空闲端口。

    data_root = **世界线根**（其下即 worlds/…）; 缺省 .testtmp/webtest/run-<ts>/data。
    """
    import uvicorn

    root = data_root or (ROOT / ".testtmp" / "webtest"
                         / f"run-{time.strftime('%Y%m%d_%H%M%S')}" / "data")
    # 诊断日志也重定向到本次运行目录（2026-09-11）: app 在 import 时挂全局
    # FileHandler——不重定向的话冒烟的日志会混进真机 data/diag/live2be.log
    os.environ.setdefault("LIVE2BE_DIAG_LOG", str(root.parent / "diag.log"))

    from webgui.app import app

    _st, sid, _engine, llm = build_world(root)

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    th = threading.Thread(target=server.run, daemon=True)
    th.start()

    deadline = time.time() + ready_timeout
    while time.time() < deadline:
        if getattr(server, "started", False) and server.servers:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("uvicorn 未在超时内就绪")
    sockets = getattr(server.servers[0], "sockets", None) or []
    actual = port or (sockets[0].getsockname()[1] if sockets else 0)
    return f"http://127.0.0.1:{actual}", server, sid, llm


def main() -> int:
    ap = argparse.ArgumentParser(description="web E2E 桩世界（离线）")
    ap.add_argument("--port", type=int, default=0, help="0 = 随机空闲端口")
    args = ap.parse_args()
    url, server, sid, llm = serve(port=args.port)
    print(f"E2E_URL={url}")
    print(f"E2E_SESSION={sid}", flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
