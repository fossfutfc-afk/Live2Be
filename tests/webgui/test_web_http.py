# -*- coding: utf-8 -*-
"""web 层 HTTP 级端到端（A 层）— 真实 FastAPI app, 走 ASGI 传输, 全离线。

与 `test_bond.py` 那类"直接调驱动函数"的用例的区别: 这里**过 HTTP**——路由注册/
请求体校验/状态码/响应头/静态挂载/JSON 契约全部走真实链路（httpx + ASGITransport,
不开端口）。桩 LLM 与临时 store 进程内注入（同 tests/webgui/test_bond.py 手法）,
所以零成本、不碰真实 data/ 与 settings.toml。

覆盖:
    1. `/` 首页 + **index.html 引用的每个 /static 资源都 200**（防路径写错/改名漏改）
    2. `/api/menu` + 背景静态挂载 + `/api/spine/{char}`（404 或真实 pack 都合法）
    3. `/gallery/...` 路径校验（非法 id / 穿越 / 不存在 → 404, 不泄露文件）
    4. `/api/name` 往返 + namegg 彩蛋拒绝分支（写盘落 tmp_path）
    5. MMT: 开会话 → 发一轮 → 轮询拉回复（后台 worker 真跑）
    6. Bond: start → status 轮询 → turn 裁决 → replay → finish（含事件流断言）
    7. `/api/settings` GET/POST 往返（api_key 打码 + [image].enabled 布尔）

运行: python -m pytest tests/webgui/test_web_http.py
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.momotalk import MomoTalkEngine  # noqa: E402
from core.session import SessionStore  # noqa: E402
from tests.vn_fixtures import scene as rec_scene  # noqa: E402
from webgui import bond, chat  # noqa: E402
from webgui.app import app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
#: 章节标题（触发动作带下来的命题——标题屏文案; 2026-09-11 真机报障: 漏带则显示"羁绊剧情"）
CHAPTER_TITLE = "放学后的约定"

#: 模块级 store 快照（禁硬编码真 data——见 test_bond.py 的同类注释）
_ORIG_STORE = chat._store

#: 记录流 v2 桩: 首板带一组选项 + 反应板 + 收尾（与 test_bond.py 的 RECORD_BLOCK 同形）
RECORD_BLOCK = "\n".join([
    '{"stage": "switch", "text": "教室"}',
    f'{{"character": "{CHARACTER}", "text": "（首板）她抬起头。"}}',
    '{"character": "sensei", "text": "我来了。"}',
    '{"character": "sensei", "text": "再等一会儿。"}',
    f'{{"character": "{CHARACTER}", "text": "（反应板）她笑了。"}}',
    '{"stage": "end", "text": ""}',
])
PICK = "我来了。"
MMT_REPLY = {"messages": [{"text": "嗯……我、我其实很开心的！"}]}


class ScriptedLLM:
    """最小桩: 主生成给记录流 / MMT 轮给消息流, 标注与 digest 按关键字告空。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts) or [RECORD_BLOCK]

    def chat(self, messages, temperature=0.8, max_tokens=4096,
             response_format="text", **kw):
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last:                      # emotion 标注 → 全 nomal
            n = len(re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        if "变更句数组" in last:                        # place 标注 → 无变更
            return []
        if "地点 id JSON" in last:                      # 换场翻译 → 不切背景
            return {"place": ""}
        if "记录员" in head or "整理者" in head:        # digest → 空包
            return ({"episodes": []} if "记录员" in head
                    else {"decisions": [], "evidence": [], "affection_exp_delta": 0})
        if not self._scripts:
            raise RuntimeError("ScriptedLLM 脚本耗尽")
        return self._scripts.pop(0)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


# ---------------------------------------------------------------------------
# HTTP 夹具（ASGI 直连, 不开端口）
# ---------------------------------------------------------------------------

def _http(method: str, path: str, **kw):
    """一次 HTTP 往返（ASGI 传输——真实路由/校验/响应头, 无端口无网络）。"""
    from httpx import ASGITransport, AsyncClient

    async def go():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport,
                               base_url="http://testserver") as c:
            return await c.request(method, path, **kw)

    return asyncio.run(go())


def _setup(tmp_path):
    """引擎 + 事件流会话（tmp_path）+ chat 注入（与 tests/webgui/test_bond.py 同款）。"""
    st = SessionStore(tmp_path)
    engine = MomoTalkEngine(ROOT / "config" / "characters", ScriptedLLM(),
                            store=st)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine
    chat._store = st
    bond._bonds.pop((CHARACTER, root.session_id), None)
    return st, root.session_id


def _teardown():
    chat._engines.pop(CHARACTER, None)
    chat._store = _ORIG_STORE
    for key in [k for k in bond._bonds if k[0] == CHARACTER]:
        bond._bonds.pop(key, None)


def _seed_trigger(store, sid, title=CHAPTER_TITLE):
    """往事件流塞一条触发事件（= MMT 那轮的 `mmt_trigger_bond_story`）。

    章节标题的真源就是它——`_trigger_title`（内存 trace）在进程重启后是空的,
    引擎侧会回落到事件流取这个 payload（`_title_from_events`）。
    """
    from core.session.events import make_event
    return store.append_event(CHARACTER, sid, make_event(
        "mmt", "mmt_trigger_bond_story",
        {"player": "去逛逛吧", "reply": "嗯！好呀……", "chapter_title": title}))


@pytest.fixture()
def web(tmp_path):
    """注入桩引擎/临时 store 的 web 环境; 用完恢复（禁污染真 data/）。"""
    st, sid = _setup(tmp_path)
    try:
        yield st, sid
    finally:
        _teardown()


def _poll_status(sid, timeout=15.0):
    """轮询 /api/bond/status 直到 busy=False（后台生成线程完成）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = _http("GET", "/api/bond/status",
                  params={"char_id": CHARACTER, "session_id": sid})
        assert r.status_code == 200, r.text
        st = r.json()
        if not st["busy"]:
            return st
        time.sleep(0.05)
    raise AssertionError(f"bond 生成超时: {st}")


# ---------------------------------------------------------------------------
# 1~2. 页面与静态资源
# ---------------------------------------------------------------------------

def test_index_and_every_static_ref_resolves():
    """首页 200 + 不缓存; **index.html 里引用的每个 /static 资源都必须 200**。

    这条最便宜也最有用: 改名/挪目录/写错路径的 JS/CSS 会让整页按钮失效,
    而纯函数单测与"直接调驱动"的用例都发现不了。
    """
    r = _http("GET", "/")
    assert r.status_code == 200, r.text
    assert "text/html" in r.headers["content-type"]
    assert "no-cache" in r.headers.get("cache-control", "")
    html = r.text
    for anchor in ("view-bond", "view-mmt", "bond-choices"):
        assert anchor in html, f"index.html 缺关键节点 {anchor}"

    refs = sorted(set(re.findall(r'(?:src|href)="(/static/[^"]+)"', html)))
    assert len(refs) >= 5, refs
    for ref in refs:
        rr = _http("GET", ref)
        assert rr.status_code == 200, f"{ref} → {rr.status_code}"
        assert "no-cache" in rr.headers.get("cache-control", ""), ref

    # CSS 里 @import / url() 引用（如 settings.css 引 gui.css）也要能取到
    css_refs: set[str] = set()
    for ref in refs:
        if not ref.endswith(".css"):
            continue
        text = _http("GET", ref).text
        css_refs |= {m for m in re.findall(r'url\(["\']?(/static/[^"\')]+)', text)}
    for ref in sorted(css_refs):
        assert _http("GET", ref).status_code == 200, ref
    print(f"    web: 首页 200 + {len(refs)} 个静态资源 + {len(css_refs)} 个 CSS 引用全通")


def test_menu_spine_and_gallery_routes():
    """menu 列表/静态挂载/spine 元信息/gallery 路径校验（含穿越拒绝）。"""
    r = _http("GET", "/api/menu")
    assert r.status_code == 200 and isinstance(r.json().get("images"), list)
    for url in r.json()["images"][:3]:
        assert _http("GET", url).status_code == 200, url

    sp = _http("GET", f"/api/spine/{CHARACTER}")
    assert sp.status_code in (200, 404), sp.text      # 无资源 → 404 是合法降级
    if sp.status_code == 200:
        body = sp.json()
        assert body["char_id"] == CHARACTER and "pack" in body
        assert _http("GET", body["pack"]["atlas"]).status_code == 200

    for bad in ("/gallery/world1/../events.jsonl",
                "/gallery/world1/igusa_haruka/..%2F..%2Fevents.png",
                "/gallery/world1/igusa_haruka/not-a-scene.png",
                "/gallery/world1/igusa_haruka/20260101_000000_zzzz.png",
                "/gallery/WORLD/igusa_haruka/20260101_000000_abcd.png"):
        rr = _http("GET", bad)
        assert rr.status_code == 404, f"{bad} → {rr.status_code}"
    print("    web: menu/spine/gallery 路由与穿越校验通过")


# ---------------------------------------------------------------------------
# 3. 登录名（写盘落 tmp_path）
# ---------------------------------------------------------------------------

def test_name_roundtrip_and_egg_reject(monkeypatch, tmp_path):
    """/api/name: 正常名保存可读回; 空名 400; 彩蛋拒绝名（RJ~/ER~/FT~）不保存。

    彩蛋是**数据驱动**的（config/eggs/namegg.json: 名字命中 pattern → 回复带前缀）,
    所以这里用配置里真实存在的"不给取"名字（马尔库特 → RJ~/ER~/FT~ 三选一）。
    """
    from core.mmt import mmt_preset
    monkeypatch.setattr(mmt_preset, "PLAYER_JSON", tmp_path / "player.json")

    assert _http("GET", "/api/name").json()["has_name"] is False
    assert _http("POST", "/api/name", json={"name": "   "}).status_code == 400
    assert _http("POST", "/api/name", json={"name": "名" * 40}).status_code == 400
    ok = _http("POST", "/api/name", json={"name": "老师"})
    assert ok.status_code == 200 and ok.json()["ok"] is True, ok.text
    got = _http("GET", "/api/name").json()
    assert got["has_name"] is True and got["name"] == "老师"

    bad = _http("POST", "/api/name", json={"name": "马尔库特"})
    assert bad.status_code == 200, bad.text
    body = bad.json()
    assert body["ok"] is False and body["rejected"] is True, body
    assert body["kind"] in ("reject", "system", "fatal"), body
    assert body["egg"].startswith(("RJ~", "ER~", "FT~")), body
    assert _http("GET", "/api/name").json()["name"] == "老师"   # 未被改写
    print(f"    web: /api/name 往返 + 彩蛋拒绝名不落盘（kind={body['kind']}）")


# ---------------------------------------------------------------------------
# 4. MMT 一轮（后台 worker 真跑）
# ---------------------------------------------------------------------------

def test_mmt_chat_round_over_http(web):
    """/api/mmt/session → /api/mmt/chat → 轮询 /api/mmt/events 拿到回复气泡。"""
    st, sid = web
    engine = chat._engines[CHARACTER]
    engine.llm._scripts = [MMT_REPLY] * 3      # 本轮桩: 纯说话流（留几次余量防重试）

    opened = _http("GET", "/api/mmt/session", params={"char_id": CHARACTER})
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["session_id"] == sid and "bubbles" in body and "last_seq" in body

    sent = _http("POST", "/api/mmt/chat",
                 json={"char_id": CHARACTER, "session_id": sid, "text": "在吗？"})
    assert sent.status_code == 200 and sent.json()["accepted"] is True, sent.text
    assert _http("POST", "/api/mmt/chat",
                 json={"char_id": CHARACTER, "session_id": sid,
                       "text": "   "}).status_code == 400

    deadline = time.time() + 15.0
    texts: list[str] = []
    while time.time() < deadline:
        ev = _http("GET", "/api/mmt/events",
                   params={"char_id": CHARACTER, "session_id": sid, "since": 0})
        assert ev.status_code == 200, ev.text
        data = ev.json()
        texts = [b.get("text", "") for b in data["bubbles"]]
        if any("我其实很开心" in t for t in texts) and not data["running"]:
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"MMT 回复未落库: {texts}")

    # 玩家的原话也在气泡里（事件流真源）
    assert any("在吗" in t for t in texts), texts
    assert "我其实很开心" in " ".join(texts)
    print("    web: MMT 一轮走 HTTP → 回复进事件流 → 轮询可见")


# ---------------------------------------------------------------------------
# 5. Bond 全链（start → status → turn → replay → finish）
# ---------------------------------------------------------------------------

def test_bond_full_chain_over_http(web):
    """羁绊剧情全链过 HTTP; 场景过 _resolve_scene（有 speaker_name）, 事件流可回放。

    语义锚点（易踩）: ① `turn` 立即回**就地物化的当前板**（board + 老师那句）而
    `busy=True`——生成仍在后台, 必须轮询 status 等它落定; ② 待发板由**下一次
    `turn("（继续）")`** 领出（0 LLM, 返回 pregen=True）——这才是记录流 v2 的
    "一板一停"节奏; ③ 收尾板落定后 `completed=True` 才能 finish。
    """
    st, sid = web
    _seed_trigger(st, sid)                       # 章节标题的真源（触发动作 payload）
    started = _http("POST", "/api/bond/start",
                    json={"char_id": CHARACTER, "session_id": sid})
    assert started.status_code == 200, started.text
    assert started.json().get("accepted") is True, started.text
    # 章节标题必带（2026-09-11 修复: 遍历所有返回路径都要有——漏了前端标题屏
    # 就兜底成四个大字"羁绊剧情"）
    assert started.json().get("chapter_title") == CHAPTER_TITLE, started.json()

    first = _poll_status(sid)
    assert first["round"] == 1 and first["scene"], first
    paras = first["scene"]["paragraphs"]
    assert [p["text"] for p in paras] == ["（首板）她抬起头。"], paras
    assert paras[0].get("speaker_name") == "伊草 遥香", paras[0]
    assert first["scene"].get("records"), "回放/渲染真源 records 必须随 HTTP 一起出"
    assert first["scene"]["choices"] == ["我来了。", "再等一会儿。"]

    turned = _http("POST", "/api/bond/turn",
                   json={"char_id": CHARACTER, "session_id": sid, "text": PICK})
    assert turned.status_code == 200, turned.text
    body = turned.json()
    assert body.get("branch") and isinstance(body.get("scene"), dict), body
    # 2026-09-11 修复: 裁决返回**增量**（只回老师那句）——回完整物化板会让前端
    # 把已读过的板正文重播一遍（真机"第一段出现两遍"就是这个）
    assert [p["text"] for p in body["scene"]["paragraphs"]] == [PICK], body["scene"]
    names = [p.get("speaker_name") for p in body["scene"]["paragraphs"]]
    assert names == ["老师"], names                   # 只渲染老师那句（带名字行）
    _poll_status(sid)                                  # 等后台生成落定（busy 拒绝 finish）

    # 待发板（反应板 + end）: 点"继续"即领出, 0 LLM 且立刻完成
    cont = _http("POST", "/api/bond/turn",
                 json={"char_id": CHARACTER, "session_id": sid, "text": "（继续）"})
    assert cont.status_code == 200 and cont.json().get("accepted") is True, cont.text
    last = _poll_status(sid)
    assert last["round"] == 2 and last["completed"] is True, last
    assert last["scene"]["is_end"] is True, last["scene"]
    assert [p["text"] for p in last["scene"]["paragraphs"]] == ["（反应板）她笑了。"]

    # 回放器: 事件流里的记录流板 → 反向可读（含裁决）。注: 收尾板在 finish 时才
    # 落库（append-only 语义: 板在"被推进/收尾"那一刻才写），所以回放检查放后面。
    fin = _http("POST", "/api/bond/finish",
                json={"char_id": CHARACTER, "session_id": sid})
    assert fin.status_code == 200 and fin.json().get("completed") is True, fin.text

    rp = _http("GET", "/api/bond/replay",
               params={"char_id": CHARACTER, "session_id": sid})
    assert rp.status_code == 200, rp.text
    scenes = [s for at in rp.json()["attempts"] for s in at["scenes"]]
    assert len(scenes) == 2, rp.text
    assert scenes[0]["scene"].get("records"), rp.text
    assert scenes[0]["picked"] == PICK, scenes[0]
    assert scenes[1]["scene"]["is_end"] is True, scenes[1]
    assert rp.json()["attempts"][0]["completed"] is True, rp.text

    evs = st.events(CHARACTER, sid)
    kinds = [(e.type, e.subtype) for e in evs if e.is_marker]
    assert ("marker", "vn_enter") in kinds and ("marker", "vn_exit") in kinds, kinds
    bond_kinds = [e.subtype for e in evs if e.type == "bond"]
    assert "story_scene" in bond_kinds and "story_end" in bond_kinds, bond_kinds
    print(f"    web: bond 全链过 HTTP（{len(evs)} 条事件, 回放 {len(scenes)} 场, "
          f"待发板 0 LLM 续播）")


# ---------------------------------------------------------------------------
# 5b. 进入响应必带章节标题（真机: 标题屏曾显示四个大字"羁绊剧情"）
# ---------------------------------------------------------------------------

def test_bond_enter_adopt_carries_chapter_title(web):
    """**adopt 就绪**（预热已完成 → 玩家点击）是真实最常见路径——该返回路径此前
    漏带 `chapter_title`, 前端标题屏兜底成"羁绊剧情"（2026-09-11 用户报障）。"""
    st, sid = web
    _seed_trigger(st, sid)
    staged = bond.bond_start(CHARACTER, sid, staged=True)     # 入口预热（触发轮之后）
    assert staged.get("accepted") is True, staged
    _poll_status(sid)                                        # 等首场生成完（预热就绪）
    adopted = bond.bond_start(CHARACTER, sid)                # 玩家点击 → adopt
    assert adopted.get("accepted") is True and adopted.get("resumed") is True, adopted
    assert adopted.get("chapter_title") == CHAPTER_TITLE, adopted
    assert bond.bond_status(CHARACTER, sid).get("chapter_title") == CHAPTER_TITLE
    print("    web: adopt 就绪路径带章节标题（否则标题屏显示『羁绊剧情』）")


# ---------------------------------------------------------------------------
# 6. 设置页
# ---------------------------------------------------------------------------

def test_settings_over_http_roundtrip(monkeypatch, tmp_path):
    """/api/settings: api_key 打码返回、留空/打码不改 key、[image].enabled 布尔往返。"""
    from webgui import store
    monkeypatch.setattr(store, "SETTINGS_PATH", tmp_path / "settings.toml")
    monkeypatch.setattr(chat, "reset_engines", lambda *a, **kw: None)
    store.save_settings({**store.load_settings(),
                         "image": {"api_key": "sk-secret-1234", "enabled": True}})

    got = _http("GET", "/api/settings")
    assert got.status_code == 200
    assert got.headers.get("cache-control") == "no-store"
    body = got.json()
    assert body["image"]["api_key"] == store.mask_api_key("sk-secret-1234")
    assert body["image"]["enabled"] is True

    r = _http("POST", "/api/settings",
              json={"image": {"api_key": body["image"]["api_key"], "enabled": False}})
    assert r.status_code == 200 and r.json()["ok"] is True
    after = _http("GET", "/api/settings").json()["image"]
    assert after["enabled"] is False, after            # 复选框落盘
    assert after["api_key"] == body["image"]["api_key"], "打码值回传不得改 key"
    print("    web: /api/settings 打码 + 布尔开关往返")
