# -*- coding: utf-8 -*-
"""web E2E 桩世界 — 真 FastAPI app + 桩 LLM + 临时世界线（浏览器级冒烟的底座）。

**为什么不直接用真 LLM**: 浏览器级冒烟要把"界面链路"与"模型发挥"分开——桩 LLM
让每一步都可预期、零成本、可反复跑; 真 LLM 的时序/内容问题属另一层验收
（见 docs/EXEC_BOND_LATENCY.md 的真机数据）。

**隔离**: 事件流落 `.testtmp/webtest/run-*/data`（临时 SessionStore 注入
接缝模块 `webgui.deps`）——绝不写真实 data/; settings.toml 只读（生图默认已被
tests/conftest 的开关关掉这里不适用, 故这里显式置 `LIVE2BE_IMAGE=off`）。

用法（一般由 run.py 调, 也可单独起）:
    python experiments/web_e2e/stub_world.py --port 0
    → 打印 `E2E_URL=http://127.0.0.1:PORT` 后阻塞服务
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from llm import task_labels as T  # noqa: E402

#: 生图总开关: 界面冒烟绝不出图（纪念场景走纯文字降级）
os.environ.setdefault("LIVE2BE_IMAGE", "off")

CHARACTER = "igusa_haruka"
CHAPTER_TITLE = "放学后的约定"

#: 记录流 v2 桩块（板 = switch/正文/选项 → 收尾板[多段!]）
#: **收尾板故意放多段**——2026-09-11 真机 bug: is_end 板点击=直接 finish 而非
#: 推进段落, 导致"最后一段只看到第一句就退出 VN"。冒烟必须能抓住它。
#:
#: ⚠️ **纪念故意落在第二板**（2026-09-26 真机 bug 的覆盖）: 首板经 `/api/bond/start`
#: **直返场景**（那条路 2026-09-12 已补 `syncMemorial`），而**章中途的板**经
#: `/api/bond/turn` 直返（预生成领出）——后者曾漏了同一个同步 ⇒ 纪念板照常显示
#: 立绘 + 普通背景（用户报障"名字隐藏了、立绘还在、图不上屏"）。
#: 把纪念放到第二板，冒烟才真的走到那条路径（此前纪念在首板 ⇒ 缺口一直没盖住）。
BOND_BLOCK = "\n".join([
    '{"stage": "switch", "text": "教室"}',
    f'{{"character": "{CHARACTER}", "text": "（她抬起头，指尖还沾着粉笔灰。）老师……你来了。"}}',
    '{"character": "sensei", "text": "我来了。"}',
    '{"character": "sensei", "text": "再等一会儿。"}',
    # ↑ sensei 群结束 = 板切 ⇒ 以上是**首板**（含 2 个选项）; 以下进第二板
    f'{{"character": "{CHARACTER}", "text": "（她愣了一下，随即笑起来。）嗯……那我等你。"}}',
    # 纪念触发（第二板第 2 段 = 下标 1）: 其后到板尾都是纪念正文
    '{"stage": "memorial", "text": "（她抬起头，第一次直视我的眼睛。）"}',
    f'{{"character": "{CHARACTER}", "text": "（收尾一）谢谢您，老师……！"}}',
    # ↑ 切板用**老师群**（纪念区间里唯一合法的切板手段——`switch`/`art` 在纪念区间
    #   内是**硬违规** `block.memorial-forbidden-stage`, 2026-09-26 试过, 引擎当场
    #   打回重发）。这样纪念板=独立一板且**不是收尾板**: 读完裁决一次即可让它落库,
    #   6.5 的中途退出回放才带得上它（落库发生在玩家推进时: `_log_scene`）。
    '{"character": "sensei", "text": "我们上去吧。"}',
    '{"character": "sensei", "text": "上面风大，我带了外套。"}',
    '{"character": "narrator", "text": "（收尾二：她用力地鞠了一躬。）"}',
    '{"stage": "end", "text": "（收尾三：她抱着那本笔记站在门口，一直挥着手。）"}',
])
#: 预生成/续写兜底块（若待发板被耗尽还有请求 → 纯叙事板, 不炸）
BOND_FALLBACK = "\n".join([
    f'{{"character": "{CHARACTER}", "text": "（窗外的天色又暗了一点。）"}}',
    '{"stage": "end", "text": ""}',
])
MMT_TRIGGER = ('{"text": "老师，你现在方便吗？"}\n'
               '{"text": "有件事……我想当面和你说。"}\n'
               '{"text": "在手机上说不清楚。"}\n'
               '{"action": "mmt_trigger_bond_story",'
               f' "payload": {{"chapter_title": "{CHAPTER_TITLE}"}}}}')
MMT_REPLY = '{"text": "嗯……我、我其实很开心的！"}'
#: 羁绊收尾话（wrapup）——文本独立, 冒烟据此断言"收尾气泡不用切页就能到"
WRAPUP_REPLY = '{"text": "（收尾话）老师，今天真的很谢谢你。"}'
#: ⑥-3b: 冒烟桩的 MMT 逐行间隔（秒）——生产是 LLM 的真实生成速度;
#: 这里给一个**比前端轮询间隔大**的值, 好让"第一个气泡早于整轮完成"可断言
#: （首行到达时整轮还剩 ~0.9s）。要改就改这里一处。
MMT_STREAM_GAP_S = 0.3

#: ⭐ 前端"打完再发"节奏的守门要用**真机的到达形态**: 真机一轮 8 条是在最后
#: 几百毫秒里**突发**写完的（`mmt_stream_first ms=9718` / `mmt_turn ms=10108`）,
#: 前端一次轮询就抓到好几条 ⇒ 那时才谈得上"批内逐条上屏"。
#: 而桩若把每行都隔 0.3s 吐, 每次轮询只抓到 1 条 ⇒ 每条都是"批内第一条"（不延迟）
#: ⇒ **节奏永远不会被触发**, 断言再写也是假绿（2026-10-08 实测踩到）。
#: 所以: 前几行**不睡**（= 突发, 落进同一次轮询）, 只在**触发行之前**留一个间隔
#: —— 那个间隔同时保住 ⑥-3b 那条"首泡早于整轮完成"（整轮还没完, 首泡已经上屏）。
#: 形状 = 每行**之前**睡多久（第一项对应第 1 行, 恒 0）; 长度不足时回落到
#: `MMT_STREAM_GAP_S`。
MMT_ROW_GAPS_S = (0.0, 0.0, 0.0, 0.9)


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

    def _side_effect(self, task: str | None, note: str):
        """标注/digest 旁路 → 合法空应答（不消耗主生成脚本）。

        节点 5b（2026-09-21）: 判据从 prompt 中文关键字换成 `llm.chat(task=…)`
        的**调用身份**——改文案不再让冒烟桩漂移（少一个分支的后果不是报错而是
        **脚本漂移**: 调用落进主生成分支, 把 `bond_calls` 计数吃掉一轮）。
        """
        if task == T.EMOTION:
            m = re.search(r"恰 (\d+) 项", note)
            return ["nomal"] * (int(m.group(1)) if m else 1)
        if task == T.PLACE:
            return []
        if task == T.PLACE_BOARD:
            return {"place": ""}
        if task == T.PLACE_VARIANT:
            # 选图（第二遍, PL6′ 2026-09-19）→ 保持默认图
            return {"image": ""}
        if task == T.DIGEST_RECORD:            # ⭐ M1: 好感归 R1
            return {"episodes": [], "affection_exp_delta": 0}
        if task in (T.DIGEST_RELATE, T.DIGEST):
            return {"relations": []}           # L1（判关系）: 空包 = 没看出关系
        return None

    # -- 契约（引擎只要求这两个方法）-----------------------------------------
    def chat(self, messages, temperature=0.8, max_tokens=4096,
             response_format="text", **kw):
        task = kw.get("task")
        system = messages[0]["content"] if messages else ""
        note = self._last_note(messages)
        side = self._side_effect(task, note)
        if side is not None:
            self.calls.append("side")
            return side
        # 全量文本（system_note 可能落在 system 段或独立 system 消息里——收尾轮
        # 的判据是"这段剧情刚结束/只进行到一半"这个**注记**, 不只看最后一条 user）
        joined = "\n".join(str(m.get("content") or "") for m in messages)
        if task == T.MMT:
            self.mmt_calls += 1
            self.calls.append(f"mmt#{self.mmt_calls}")
            if self.mmt_calls == 1:
                return MMT_TRIGGER         # 第一轮即触发羁绊剧情（界面走全链）
            if "羁绊剧情刚刚结束" in joined or "只进行到一半" in joined:
                return WRAPUP_REPLY        # 收尾话（wrapup 轮）——区别于普通回复
            return MMT_REPLY
        if task != T.BOND:
            raise AssertionError(
                f"冒烟桩不认识 task={task!r}（产品侧漏传或新增任务没补桩; "
                f"system 首 40 字: {system[:40]!r}）")
        self.bond_calls += 1
        self.calls.append(f"bond#{self.bond_calls}")
        return BOND_BLOCK if self.bond_calls == 1 else BOND_FALLBACK

    def chat_full(self, messages, temperature=0.8, max_tokens=4096,
                  response_format="text", on_chunk=None, **kw):
        """⑥-3b: 流式等价 —— **MMT 逐行喂 + 行间 sleep**（生产形状）。

        为什么 MMT 要带间隔: 引擎 ⑥-3a 起"行一到就交付"，冒烟要能断言
        **第一个气泡早于整轮完成**（前后端一起改，没有这个间隔就测不到）。
        ⭐ 间隔按 `MMT_ROW_GAPS_S` **逐行给**（前几行 0 = 突发, 与真机同形;
        触发行之前留一个间隔 ⇒ ⑥-3b 那条断言仍成立）—— 见那段常量的注释。
        bond 那一侧一次性喂完（VN 的板级流式另有断言, 不必拖慢冒烟）。
        """
        out = self.chat(messages, temperature=temperature, max_tokens=max_tokens,
                        response_format=response_format, **kw)
        is_mmt = kw.get("task") == T.MMT
        if on_chunk is not None and isinstance(out, str):
            for i, line in enumerate(out.splitlines(keepends=True)):
                if is_mmt:
                    if i < len(MMT_ROW_GAPS_S):
                        gap = MMT_ROW_GAPS_S[i]
                    else:
                        gap = MMT_STREAM_GAP_S
                    if gap:
                        time.sleep(gap)
                on_chunk(line)
        return out

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


class _FakeImageGen:
    """离线生图替身（冒烟用）: **不碰网络**, 写一张 1×1 PNG 当"纪念图"。

    为什么需要: 纪念链路的验证点是"引擎的 art/memorial → 生图 → gallery URL →
    `bond_status.memorial_img` → 前端纪念层淡入"整条线（2026-09-12 v2 重接线）。
    真调 API 花钱且不确定, 所以这里替身出一个真实存在的文件（GalleryStore 要复制它）。

    ⚠️ **必须演"图晚到"**（2026-10-08）: 真机生图 ≈49s（`elapsed_ms=49152` 实测）,
    而桩原先**即时**返回 ⇒ `state.memorial_img` 在**板上屏那一刻就已经就绪**
    ⇒ 前端"上屏时同步一次"就够, "图晚到 ⇒ 前端没人去问 ⇒ 永远不上屏"那条
    bug（真机 5/5 未上屏）在冒烟里**永远是绿的**（假绿）。所以这里睡
    `STUB_IMAGE_DELAY_S` 秒, 让"板上屏"与"图就绪"**错开**。
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, prompt: str, **kw):  # noqa: ANN003 — 与真接口同形
        from llm.image_gen import GeneratedImage

        self.calls.append(prompt)
        if STUB_IMAGE_DELAY_S > 0:
            time.sleep(STUB_IMAGE_DELAY_S)       # 生图在**独立线程**里（见 _make_memorial_cb）
        root = ROOT / ".testtmp" / "webtest" / "fakeimg"
        root.mkdir(parents=True, exist_ok=True)
        path = root / "memorial.png"
        if not path.is_file():
            path.write_bytes(base64.b64decode(_PNG_1PX))
        return GeneratedImage(path=path, width=1, height=1, size_bytes=path.stat().st_size)


#: 冒烟: 生图替身的**人为延迟（秒）**。
#: ⚠️ 必须**大于**"那块纪念板上屏 → 冒烟开始查图"之间的间隔。实测那个间隔 ≈8s
#: （开画 → 裁决步骤 → 逐段推进到纪念句）: 给 8s 会正好撞上 ⇒ 断言退化成
#: "情形③（图先到）"的假绿（2026-10-08 两次踩到: 延迟 4s → 就绪 4ms; 8s → 撞上）。
#: 15s 留够余量; 冒烟里另有**前置判据**在校验"板上屏那一刻服务端确实还没图"。
STUB_IMAGE_DELAY_S = 15.0


#: 1×1 透明 PNG（冒烟占位图; 不下载资产、不出网）
_PNG_1PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAF"
    "AAH/q842iQAAAABJRU5ErkJggg=="
)


def build_world(data_root: Path):
    """临时世界线 + 注入 chat/deps（引擎/store 都指向 data_root）。

    **硬隔离（2026-09-11 事故）**: 冒烟会在登录页取名 → `POST /api/name` →
    `mmt_preset.save_player_name()` 写的是**模块级常量 PLAYER_JSON**（真实
    `data/basic/player.json`）——冒烟曾把用户自己的名字覆盖成"老师"（用户报障
    "填名字总在后面追加老师"就是它的后遗症: 登录框预填了被污染的名字）。
    这里把 PLAYER_JSON / AFFECTION / 进度等**所有全局落盘点**都改到临时目录。

    Returns: (store, session_id, engine, llm)
    """
    from core.mmt import mmt_preset
    from core.mmt.engine import MomoTalkEngine
    from core.session import SessionStore
    from webgui import chat, deps

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
    deps.set_store(st)          # C1a: store 接缝在 `webgui.deps`（`chat._store` 已不存在）
    # 纪念生图替身（2026-09-12）: 离线出图, 让"引擎 art/memorial → gallery URL →
    # 前端纪念层淡入"整条线在冒烟里真的跑一遍（`LIVE2BE_IMAGE=off` 也拦不住它,
    # 因为这里直接替换了 `deps.image_generator` 的返回值, 不碰网络也不写真实 gallery）。
    # ⚠️ C1a: 必须打**接缝模块**——打 `bond_mod._image_generator` 从今往后是静默 no-op。
    deps.image_generator = lambda: _FakeImageGen()
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

    #: 画廊取图路由读的是**模块级 `webgui.app.DATA_DIR`**（真 data/）——桩世界的
    #: 世界线在临时目录, 不重定向就会"图写进了临时 gallery, 前端取图 404"
    #: （2026-09-12 冒烟实测: 纪念层淡入但图片请求 404）。与 PLAYER_JSON 同款隔离。
    from webgui import app as app_mod
    app_mod.DATA_DIR = root

    #: 冒烟专用钩子（**只在桩世界里注册**, 产品 app 没有这个路由）:
    #: 丢掉进程内的 BondState —— 模拟"服务端重启/内存态丢失", 让下一次进入
    #: 走**事件流回放**（回放/续看路径）。用它验证"重进时选项组只读重现"
    #: （用户 2026-09-12 要求: 否则选哪个选项看起来都一样）。
    @app.post("/__e2e/drop_bond_state")
    async def _e2e_drop_bond_state() -> dict:
        from webgui import bond as _bond

        n = len(_bond._bonds)
        _bond._bonds.clear()
        return {"dropped": n}

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
