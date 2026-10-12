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
    5. MMT: 开会话 → 发一轮 → 轮询拉回复（后台 worker 真跑）+ 列表头像按角色三层回落
    6. Bond: start → status 轮询 → turn 裁决 → replay → finish（含事件流断言）
    7. `/api/settings` GET/POST 往返（api_key 打码 + [image].enabled 布尔）

运行: python -m pytest tests/webgui/test_web_http.py
"""
import asyncio
import re
import sys
import time
from pathlib import Path

import pytest

from core.mmt.engine import MomoTalkEngine
from core.session import SessionStore
from llm import task_labels as T
from tests import stub_tasks
from webgui import bond, chat, deps
from webgui.app import app

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
#: 章节标题（触发动作带下来的命题——标题屏文案; 2026-09-11 真机报障: 漏带则显示"羁绊剧情"）
CHAPTER_TITLE = "放学后的约定"

#: 模块级 store 快照（禁硬编码真 data——见 test_bond.py 的同类注释）
_ORIG_STORE = deps.store()

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
MMT_REPLY = '{"text": "嗯……我、我其实很开心的！"}'


class ScriptedLLM:
    """最小桩: 主生成给记录流 / MMT 轮给消息流, 标注与 digest 按 **task** 告空。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts) or [RECORD_BLOCK]

    def chat(self, messages, temperature=0.8, max_tokens=4096,
             response_format="text", **kw):
        task = kw.get("task")
        if task in (T.DIGEST_RECORD, T.DIGEST_RELATE):            # digest → 空包
            return stub_tasks.annotation_reply(task, messages)
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                           # 标注类 → 标准应答
            return reply
        if task in T.MAIN:
            if not self._scripts:
                raise RuntimeError("ScriptedLLM 脚本耗尽")
            return self._scripts.pop(0)
        raise stub_tasks.unknown_task(task)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs

    def chat_full(self, messages, temperature=0.8, max_tokens=4096,
                  response_format="text", on_chunk=None, **kw):
        """流式等价（**生产路径**）——节点 5（2026-09-21）: 按行喂 `on_chunk`,
        板一闭合即交付（与真机 `LLMClient.chat_full` 同语义）。

        此前本桩没有它 ⇒ A 层 HTTP 测试全走批式, 与真机不是同一条流水线。
        """
        out = self.chat(messages, temperature=temperature, max_tokens=max_tokens,
                        response_format=response_format, **kw)
        if on_chunk is not None and isinstance(out, str):
            for line in out.splitlines(keepends=True):
                on_chunk(line)
        return out


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
    deps.set_store(st)
    bond._bonds.pop((CHARACTER, root.session_id), None)
    return st, root.session_id


def _teardown():
    chat._engines.pop(CHARACTER, None)
    deps.set_store(_ORIG_STORE)
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

def test_mmt_avatar_picks_each_char_own_portrait(monkeypatch, tmp_path):
    """MMT 头像 = **每个角色各取自己的** `{cid}/{outfit}/portrait/`（2026-09-12 定稿）。

    为什么断言里不写真资产路径: `assets/` 是 gitignore 的——本机没那些图就会假红。
    这里把 `ILLUS_ROOT` 指到 tmp 世界树, 覆盖标准外观格式与"无图"两端:
      ① 有 `portrait/collection.png` → 用它, type=portrait（且压过 diff 立绘）;
      ② 只有 `portrait/` 里的其他名 → 仍算 portrait（约定名缺失时可容忍）;
      ③ 无 portrait/（资产缺件）→ 回落 `diff/*Idle*.png`, type=png;
      ④ 什么都没有 → 空串（列表跳过该角色, 不炸）。
      ⑤ **`mmt/` 目录已退役**: 放那里不再被认（回归守卫——那条来源被删掉了）。

    **反向断言**: 甲角色的头像绝不能出现在乙角色身上（曾被改成"全角色共用一张",
    该错误单靠 ① 是抓不到的——每个角色都"有"头像, 只是都指向同一张）。
    """
    from webgui.routers import mmt as mmt_router

    def put(cid, rel, data=b"x"):
        p = tmp_path / cid / "default" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return "/assets/illustration/" + f"{cid}/default/{rel}"

    url_haruka = put("igusa_haruka", "portrait/collection.png")   # ① 约定名
    put("igusa_haruka", "diff/haruka_spr_Idle_01.png")            # 应被 portrait 压过
    url_kayoko = put("onikata_kayoko", "portrait/lobby_icon.png")  # ② 其他名
    url_mutsuki = put("asagi_mutsuki", "diff/mutsuki_spr_Idle_01.png")  # ③ 兜底
    put("rikuhachima_aru", "mmt/Lobbyillust_Icon_01.png")          # ⑤ 退役来源, 不算
    monkeypatch.setattr(mmt_router, "ILLUS_ROOT", tmp_path)

    want = {"igusa_haruka": (url_haruka, "portrait"),
            "onikata_kayoko": (url_kayoko, "portrait"),
            "asagi_mutsuki": (url_mutsuki, "png"),
            "rikuhachima_aru": ("", ""),                           # ⑤ mmt/ 不再认
            "shiraishi_kokoro": ("", "")}                          # ④ 无图
    for cid, exp in want.items():
        assert mmt_router._find_avatar(cid) == exp, cid
    urls = {u for u, _t in want.values() if u}
    assert urls == {url_haruka, url_kayoko, url_mutsuki}, \
        f"每角色必须各取各的（曾错误地全指向同一张）: {urls}"

    r = _http("GET", "/api/mmt/characters")
    assert r.status_code == 200, r.text
    body = r.json()
    if body["registry_empty"]:
        pytest.skip("mmt_registry.toml 为空——无白名单可验")
    assert body["characters"], body
    avatars = [c["avatar"] for c in body["characters"]]
    assert len(set(avatars)) == len(avatars), avatars     # 白名单角色头像互不相同
    for c in body["characters"]:
        assert c["avatar"].startswith(f"/assets/illustration/{c['id']}/"), c

    monkeypatch.setattr(mmt_router, "ILLUS_ROOT", tmp_path / "empty")
    assert mmt_router._find_avatar("igusa_haruka") == ("", "")
    print(f"    web: MMT 头像按角色各取各的（{len(avatars)} 个角色, portrait/diff 回落全通; "
          f"mmt/ 来源已退役; 缺资产 → 空串跳过, 不炸）")


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

    语义锚点（易踩）: ① `turn` 裁决**不回 scene**（只回 `picked`）——玩家的话语永远
    只体现为选项, 正文停在上一句; ② 待发板由**下一次 `turn("（继续）")`** 领出
    （0 LLM）——这才是记录流 v2 的"一板一停"节奏; ③ 收尾板落定后 `completed=True`
    才能 finish。
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
    assert body.get("branch") is True and body.get("picked") == PICK, body
    # 2026-09-12 定稿（用户核对 BA）: **玩家的话语永远只体现为选项**——裁决不返回
    # scene, 前端只清选项、正文停在上一句; 把这句话当正文回给前端就会被念出来,
    # 读成"角色说了玩家的话"（真机报障）。展示视图保留板正文、只去掉选项。
    assert "scene" not in body, body
    shown = bond.bond_status(CHARACTER, sid)["scene"]
    assert [p["text"] for p in shown["paragraphs"]] == ["（首板）她抬起头。"], shown
    assert shown["choices"] == [] and shown["picked"] == PICK, shown
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


def test_bond_enter_adopt_returns_ready_scene(web):
    """**就绪场景随 bond_start 一起回**（2026-09-11）: 重进/预热命中/adopt 就绪
    这些路径场景本来就在手里（纯读文件）, 旧协议只回 `resumed: true` → 前端黑屏
    等一轮轮询（+ 标题屏黑底）。现在直接带 scene/round/emo_version。"""
    st, sid = web
    _seed_trigger(st, sid)
    bond.bond_start(CHARACTER, sid, staged=True)
    _poll_status(sid)
    adopted = bond.bond_start(CHARACTER, sid)
    assert isinstance(adopted.get("scene"), dict), adopted
    assert adopted["scene"]["paragraphs"], adopted["scene"]
    assert adopted.get("round") == 1, adopted
    assert "emo_version" in adopted, adopted
    print("    web: adopt 就绪 → 响应自带场景（前端 0 等待上屏, 无黑屏）")


def test_bond_watchdogs_self_heal_stuck_gate(web, monkeypatch):
    """看门狗（2026-09-11 / 2026-09-13 审计 A6 收紧）: 视觉门/预生成消费门卡住
    不能变成"点击永久无响应"——但**只在没人会再来标它时**才降级。

    真机现象: 点继续后前端一直"剧情推进中…（已等待 110s）"而后端其实闲着——
    某些异常下标注 lane 不会再回来 → `gate` 永远 False。

    2026-09-13 修正后的前置条件（`_gate_stalled` = `_lanes_idle`）: 无积压 **且**
    无在途。原先只看队列深度 → worker 正 `await` 标注时 `qsize()==0` 也成立,
    于是一次**健康的慢调用**就会被强制兜底, 而兜底产物会随 `_log_scene` 进
    append-only 真源（假 nomal + 假 `_place_done`）。

    本用例要覆盖**三种**状态（第二版曾漏掉第三种, 导致兜底在稳态永不触发）:
      ① 有 worker 在途 → 不抢;
      ② 线程都没起来 / 已退出 → 必须放行;
      ③ **稳态**: worker 线程**活着**（阻塞在 `q.get()` 上——全仓没有任何地方投
         `None` 哨兵, 所以它活到进程结束）、队列空、无在途 → **也必须放行**。
         第三种才是真实会话的常态; 若判据里掺了"线程死活", ②③ 就永远不触发。
    """
    st, sid = web
    _seed_trigger(st, sid)
    bond.bond_start(CHARACTER, sid, staged=True)
    _poll_status(sid)
    state = bond._state(CHARACTER, sid)

    def _make_unready():
        """造一个"永远不就绪"的场景: 抹掉 emotion + place 标记。"""
        for p in state.scene_obj.paragraphs:
            p.pop("emotion", None)
        state.scene_obj._place_done = False
        state.gate_since = 0.0

    _make_unready()
    assert bond._scene_visual_ready(state) is False, "前置: 场景确实卡在未就绪"
    monkeypatch.setattr(deps, "GATE_WATCHDOG_MS", -1)        # 视为已超时

    # ① 有 worker 正在 await 标注（在途）→ **不得**抢它的活: 等真标注回来
    monkeypatch.setattr(state, "_lane_inflight", 1)
    st_mid = bond.bond_status(CHARACTER, sid)
    assert st_mid["gate_busy"] is True, \
        f"worker 在途时不该强推兜底（会污染 append-only）: {st_mid}"
    monkeypatch.setattr(state, "_lane_inflight", 0)

    # ③ 稳态: 线程活着 + 队列空 + 无在途 → 放行（真实会话的常态）
    assert bond._lane_writer_alive(state) is True, "前置: 稳态下 writer 线程应活着"
    assert bond._gate_stalled(state) is True, \
        "稳态（writer 活着但队列空/无在途）也必须是 stalled——否则兜底永不触发"
    st_after = bond.bond_status(CHARACTER, sid)
    assert st_after["gate_busy"] is False, st_after           # 看门狗兜底放行
    assert all((p.get("emotion") or "").strip()
               for p in state.scene_obj.paragraphs), state.scene_obj.paragraphs

    # ② 线程已死 / 从未启动 → 同样必须放行
    _make_unready()
    state.gate_since = 0.0
    monkeypatch.setattr(state, "_anno_started", False)
    monkeypatch.setattr(state, "_place_started", False)
    monkeypatch.setattr(state, "_anno_thread", None)
    monkeypatch.setattr(state, "_place_thread", None)
    assert bond._gate_stalled(state) is True, "无人可标时前置条件应成立"
    st_dead = bond.bond_status(CHARACTER, sid)
    assert st_dead["gate_busy"] is False, st_dead
    print("    web: 视觉门看门狗——在途不抢 / 稳态放行 / 线程没了也放行")


def test_bond_busy_watchdog_resets_lost_thread(web, monkeypatch):
    """忙态看门狗: 生成线程丢失（异常退出/线程没了）而 busy 仍在 → 复位。

    否则前端 `waitTurnIdle` 会一直等一个永远不会结束的忙态（真机 110s+ 的形态之一）。
    """
    st, sid = web
    bond.bond_start(CHARACTER, sid)
    _poll_status(sid)
    state = bond._state(CHARACTER, sid)
    state.busy = True
    state.busy_since = time.monotonic()
    state._gen_thread = None
    state._pregen_thread = None
    monkeypatch.setattr(deps, "BUSY_WATCHDOG_MS", -1)
    st_after = bond.bond_status(CHARACTER, sid)
    assert st_after["busy"] is False, st_after
    print("    web: 忙态看门狗复位（线程丢失不再让点击永久无响应）")


def test_turn_reject_is_logged(web, caplog):
    """推进被拒要留痕: 前端在重试, 后端不记日志等于"事故无迹可查"。

    ⚠️ 2026-10-08（链式读前）改: `busy` 现在**只拦"要领的东西还没写好"**的推进
    （见下一条 `test_busy_with_board_in_hand_still_advances`）⇒ 要验"被拒留痕",
    必须把**手里的板清空**（槽位 + 待发队列）, 让这次推进真的无事可领。
    """
    import logging
    st, sid = web
    bond.bond_start(CHARACTER, sid)
    _poll_status(sid)
    state = bond._state(CHARACTER, sid)
    state.pregen_obj = state.pregen_scene = None             # 槽位空
    state.vn._pending_boards = []                            # 队列空
    state.busy = True                                        # 模拟生成中
    with caplog.at_level(logging.WARNING, logger="live2be.bond"):
        r = bond.bond_turn(CHARACTER, sid, "（继续）")
    state.busy = False
    assert r.get("accepted") is False and r.get("busy") is True, r
    assert any("bond_turn 被拒" in rec.getMessage()
               for rec in caplog.records), [r.getMessage() for r in caplog.records]
    print("    web: 推进被拒有 WARNING 留痕（reason + 次数）")


def test_busy_with_board_in_hand_still_advances(web):
    """⭐ 链式读前（2026-10-08）: **后台在写将来的块时, 玩家手里的板照常领**。

    为什么单独立一条: `busy` 从前是推进的无条件闸门（`reason=busy:生成中`）——
    链式之后后台生成会持续 ~25s, 那条件会把**每一块都变成"点击被拒、等生成"**
    （比不做链式更糟）。判据: 这一次推进 0 LLM 可服务（槽位/待发队列有板）⇒ 放行。
    """
    st, sid = web
    bond.bond_start(CHARACTER, sid)
    _poll_status(sid)
    state = bond._state(CHARACTER, sid)
    assert state.pregen_obj is not None or state.vn._pending_boards, \
        "本用例需要手里有板（预热/预生成给的那一块）"
    state.busy = True                                        # 后台正在写将来那块
    try:
        r = bond.bond_turn(CHARACTER, sid, "（继续）")
    finally:
        state.busy = False
    assert r.get("accepted") is True, f"手里有板却被 busy 拒了: {r}"
    print("    web: busy + 手里有板 ⇒ 推进照常（链式不卡玩家）")




def test_turn_accept_is_logged(web, caplog):
    """⭐ 推进**成功**也要留痕: `bond_turn ok src=… board=…`（2026-10-08）。

    为什么单独立一条: 从前"接受"只在**曾被拒**时才打日志（`_clear_rejects` 的第一行
    是 `if not state.turn_rejects: return`）⇒ **顺畅的那一轮在 diag 里什么都没有**。
    2026-10-08 排查"纪念图为什么不上屏"时正是被这一点误导 —— 一段十几分钟的全静默，
    分不清"玩家没点"和"点了没记"，最后靠用户回忆才定性（真相是**杀进程**）。
    ⇒ 判据: 每次接受都有一行带 `src=` 与轮号的 INFO（`src` 说出这一板从哪来:
    replay/queue/branch/live）。
    """
    import logging
    st, sid = web
    bond.bond_start(CHARACTER, sid)
    _poll_status(sid)
    with caplog.at_level(logging.INFO, logger="live2be.bond"):
        r = bond.bond_turn(CHARACTER, sid, "（继续）")
    assert r.get("accepted") is True, r
    accepts = [rec.getMessage() for rec in caplog.records
               if "bond_turn ok" in rec.getMessage()]
    assert accepts, [rec.getMessage() for rec in caplog.records]
    assert "src=" in accepts[0] and "board=" in accepts[0], accepts[0]
    print(f"    web: 推进成功留痕 → {accepts[0][:90]}")


def test_finish_wrapup_marks_task_busy(web, monkeypatch):
    """收尾 wrapup 必须占住 MMT 任务位（2026-09-11 真机报障的根因）。

    现象: finish 后收尾气泡不立刻出现, 要切页/重进才看得到。
    根因: wrapup 跑在 bond 自己的线程里, 不走 chat 的 `_worker` → 前端
    `pollLoop` 第一轮就看见 `running: false` → **停止轮询**。
    修法: `chat.task_begin/task_end` 由 wrapup 占位/释放; 这里把慢的收尾话
    换成一个会阻塞的桩, 断言"收尾在跑时 task busy=True, 结束后 False"。
    """
    import threading as _th
    st, sid = web
    _seed_trigger(st, sid)
    bond.bond_start(CHARACTER, sid, staged=True)
    _poll_status(sid)

    gate = _th.Event()
    engine = chat._engines[CHARACTER]
    real_turn = engine.agent_turn

    def slow_turn(*a, **kw):
        if kw.get("task_kind") == "wrapup":
            gate.wait(timeout=10)
            return real_turn(*a, **kw)
        return real_turn(*a, **kw)

    monkeypatch.setattr(engine, "agent_turn", slow_turn)
    monkeypatch.setattr(engine, "async_digest", lambda *a, **kw: None)
    r = bond.bond_finish(CHARACTER, sid)
    assert r.get("completed") is True, r

    # 收尾在跑 → 前端轮询会看到 busy（因此不会停止轮询）
    deadline = time.time() + 5.0
    while time.time() < deadline and not chat.task_status(CHARACTER, sid)["busy"]:
        time.sleep(0.02)
    assert chat.task_status(CHARACTER, sid)["busy"] is True, "wrapup 应占住任务位"
    gate.set()
    deadline = time.time() + 10.0
    while time.time() < deadline and chat.task_status(CHARACTER, sid)["busy"]:
        time.sleep(0.05)
    assert chat.task_status(CHARACTER, sid)["busy"] is False, "wrapup 结束必须释放"
    print("    web: 收尾 wrapup 占/放任务位（前端轮询据此继续拉收尾气泡）")


# ---------------------------------------------------------------------------
# 5c. 板交付台账（回答"这一板是生成的还是缓存/回放来的"）
# ---------------------------------------------------------------------------

def test_board_deliver_ledger(web, caplog):
    """**板交付台账**（2026-09-11）: 每板一行, 标明"这一板怎么到玩家眼前的"。

    用户实际追问过"你怎么确定是一次 LLM 写完而不是缓存"——为此必须能从日志直接
    读出每板来源（stream/gen/queue/prewarm/draft/replay）与产出它的调用 id。
    """
    import logging
    st, sid = web
    with caplog.at_level(logging.INFO, logger="live2be.bond"):
        _seed_trigger(st, sid)
        bond.bond_start(CHARACTER, sid, staged=True)
        _poll_status(sid)                        # 首板（预热生成）
        first = bond.bond_start(CHARACTER, sid)  # adopt 就绪（场景随响应回）
        assert first.get("scene"), first
        bond.bond_turn(CHARACTER, sid, PICK)     # 裁决 → 反应板进 pregen
        _poll_status(sid)
        bond.bond_turn(CHARACTER, sid, "（继续）")   # 领预生成（0 LLM）
        _poll_status(sid)
    lines = [r.getMessage() for r in caplog.records
             if "bond_board_deliver" in r.getMessage()]
    assert lines, "没有交付台账"
    srcs = [ln.split("src=")[1].split()[0] for ln in lines]
    assert "gen" in srcs or "stream" in srcs, srcs       # 首板: 真生成
    assert "queue" in srcs, srcs                         # 后续板: 0 LLM 领队列
    assert all("call=" in ln and "recs=" in ln for ln in lines), lines
    print(f"    web: 交付台账 {len(lines)} 行, srcs={sorted(set(srcs))}")





# ---------------------------------------------------------------------------
# 5d. 回忆册（书页 / 角色页 / 只读回放）—— DESIGN_COLLECTION_BOOK.md
# ---------------------------------------------------------------------------

def _seed_chapters(store, sid):
    """塞三章: 甲（已结束, 3 板, 含一组已裁决选项 + **一段纪念窗口 + 一张纪念图**）/
    乙（未完）/ 丙（废弃）。

    返回甲的 from_seq（章的稳定 id）与乙的——后者用来断言"未完章后端根本没有"。
    """
    from core.session.events import make_event

    def board(text, choices=None, picked=None, **extra):
        store.append_event(CHARACTER, sid, make_event(
            "bond", "story_scene",
            {"paragraphs": [{"text": text}], "background": "class_room",
             "choices": choices or [], "picked": picked, "input": "（继续）", **extra}))

    # 甲: 已确认结束（第 2 板触发纪念 —— v2 形状: 板 → memorial_enter → 图晚到）
    a = store.append_marker(CHARACTER, sid, "vn_enter",
                            {"chapter_title": "咖啡厅的甜点陷阱"}).seq
    board("她抬起头。")
    board("我来了。", choices=["我来了。", "再等一会儿。"], picked="我来了。",
          memorial=True)
    store.append_marker(CHARACTER, sid, "memorial_enter",
                        {"chapter_title": "咖啡厅的甜点陷阱", "v2": True})
    store.append_marker(CHARACTER, sid, "memorial_image",
                        {"url": "/gallery/world1/igusa_haruka/20260101_000000_ab12.png",
                         "prompt": "p", "width": 1024, "height": 1024,
                         "scene_id": "20260101_000000_ab12"})
    board("她笑了。")                     # 这一板的落地收窗（v2 形状）
    store.append_marker(CHARACTER, sid, "memorial_exit", {"v2": True, "auto": True})
    store.append_marker(CHARACTER, sid, "vn_exit", {"completed": True})

    # 乙: 未完（流尾未关）——册子不该看到它
    b = store.append_marker(CHARACTER, sid, "vn_enter",
                            {"chapter_title": "没写完的章"}).seq
    board("半截。")

    # 丙: 被 vn_abandon 关闭（视为未发生）
    c = store.append_marker(CHARACTER, sid, "vn_enter",
                            {"chapter_title": "废弃的章"}).seq
    board("这段不算数。")
    store.append_marker(CHARACTER, sid, "vn_abandon",
                        {"start_seq": c, "end_seq": c + 1})
    return a, b, c


def test_collection_book_routes(web, monkeypatch, tmp_path):
    """书页 → 角色页 → 只读回放: **只有已确认结束的章出现**, 未完/废弃的连数据都没有。

    资产（`collection.png` 封面）指到 tmp 世界树——`assets/` 是 gitignore 的, 写真路径
    会假红; 这里同时验证"无素材角色 → 留白格"（作者口径）。
    """
    from webgui.routers import mmt as mmt_router

    st, sid = web
    a_seq, b_seq, c_seq = _seed_chapters(st, sid)

    # 封面: 只有 CHARACTER 有 collection.png, 其余白名单角色留白
    illus = tmp_path / "illus"
    cover = illus / CHARACTER / "default" / "portrait" / "collection.png"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(mmt_router, "ILLUS_ROOT", illus)

    r = _http("GET", "/api/collection/book")
    assert r.status_code == 200, r.text
    book = r.json()
    assert book["rows"] == 3 and book["cols"] == 4
    assert book["cells"], book
    by_id = {c["char_id"]: c for c in book["cells"]}
    assert by_id[CHARACTER]["has_cover"] is True
    assert by_id[CHARACTER]["cover"].endswith(f"{CHARACTER}/default/portrait/collection.png")
    blanks = [c for c in book["cells"] if not c["has_cover"]]
    assert blanks, "无素材角色应留白占位（不是从书里消失）"
    assert all(c["name"] for c in book["cells"]), "每格都要有显示名"
    # 2026-09-13（审计 A2）: 前端按 `char_id` 挂点击并 `openChar(c)`, 留白格原先
    # 提前 return 漏挂 → 没封面的角色**整格点不动**。契约层钉住"每格都带 char_id",
    # 前端 invariant 才成立（真正的点击路径由 B 层浏览器冒烟覆盖）。
    assert all(c["char_id"] for c in book["cells"]), "每格都要有 char_id（前端靠它挂点击）"
    # 留白格的角色页必须**照样能开**——后端从不看封面（只读事件流）
    r = _http("GET", f"/api/collection/{blanks[0]['char_id']}/chapters")
    assert r.status_code == 200, f"留白格角色页应可开: {r.text}"
    assert r.json()["chapters"] == [], "该角色无已结束章 → 空列表（不是 404/报错）"

    # 角色页: 只有甲
    r = _http("GET", f"/api/collection/{CHARACTER}/chapters")
    assert r.status_code == 200, r.text
    body = r.json()
    chs = body["chapters"]
    assert [c["title"] for c in chs] == ["咖啡厅的甜点陷阱"], chs
    assert chs[0]["from_seq"] == a_seq and chs[0]["boards"] == 3
    assert chs[0]["memorial_url"].endswith("20260101_000000_ab12.png"), chs[0]
    assert "scenes" not in chs[0], "角色页不该背正文"

    # 只读回放: 逐板 + 当时的选择 + 渲染信息
    r = _http("GET", f"/api/collection/{CHARACTER}/{a_seq}")
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["title"] == "咖啡厅的甜点陷阱" and len(rep["scenes"]) == 3
    mid = rep["scenes"][1]
    assert mid["picked"] == "我来了。" and mid["scene"]["picked"] == "我来了。"
    assert mid["scene"]["choices"] == ["我来了。", "再等一会儿。"]
    assert "input" not in mid["scene"], "input 摘出来单放（前端不渲染玩家那句）"
    assert rep["images"], rep
    # P1①（2026-09-20）: 纪念态落到**板**——前端只读回放据此隐藏立绘/清背景/淡入图。
    # 触发板带图, 窗口内后续板只带 in_memorial（图保持亮着, 与 live 同）;
    # 窗口外的板一个纪念键都不带。
    assert mid["scene"].get("in_memorial") is True, mid["scene"]
    assert mid["scene"].get("memorial_img", "").endswith("20260101_000000_ab12.png"), \
        mid["scene"]
    assert "in_memorial" not in rep["scenes"][0]["scene"], rep["scenes"][0]["scene"]
    assert "in_memorial" not in rep["scenes"][2]["scene"], rep["scenes"][2]["scene"]

    # 未完 / 废弃的章: 后端也没有（"渲染都不渲染"是数据口径, 不是前端过滤）
    for seq, why in ((b_seq, "未完"), (c_seq, "废弃")):
        rr = _http("GET", f"/api/collection/{CHARACTER}/{seq}")
        assert rr.status_code == 404, f"{why}章不该可取: {rr.status_code}"
    rr = _http("GET", f"/api/collection/{CHARACTER}/999999")
    assert rr.status_code == 404
    print(f"    web: 回忆册 {len(book['cells'])} 格（{len(blanks)} 格留白）; "
          f"角色页 {len(chs)} 章; 未完/废弃章 404")


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

    # 2026-09-13（A1 余波复核）: **JSON `null` = 不改**——走真 HTTP 钉住这条边界。
    # 为什么值得单独钉: pydantic 的 `llm: dict` 对内部值不设类型, `null` 会原样到
    # 路由; 而 store 对 None 只会"跳过不写" → 键从文件消失 → 读回回落 DEFAULTS。
    # 于是 `{"image": {"enabled": null}}` 会把生图开关**翻回默认 true = 花钱方向**,
    # `{"llm": {"model": null}}` 会把自定义 model 重置成内置默认。入口必须拦住。
    model_before = _http("GET", "/api/settings").json()["llm"]["model"]
    r = _http("POST", "/api/settings", json={"llm": {"model": None}})
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert _http("GET", "/api/settings").json()["llm"]["model"] == model_before, \
        "null 改了 model（应视为'不改'）"
    _http("POST", "/api/settings", json={"image": {"enabled": None}})
    assert _http("GET", "/api/settings").json()["image"]["enabled"] is False, \
        "null 把生图开关翻回默认 true 了（花钱方向）"
    print("    web: /api/settings 打码 + 布尔开关往返 + null=不改（真 JSON 边界）")
