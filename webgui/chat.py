"""MMT 聊天域 — 引擎管理 + 会话生命周期 + 后台任务 + 事件查询。

设计（docs/DESIGN_STREAM_CONTRACT.md）:
  - 每 char 一个独立引擎实例（并行多角色: 不同 char 各自线程跑 agent_turn,
    互不干扰; 同 char 串行锁防并发）——切换角色不取消后台任务, 回复落事件流,
    前端切回拉取补全。
  - agent_turn 在后台线程跑（真实 LLM 秒级耗时）, 结果由引擎落事件流
    （events.jsonl 唯一真源）, 前端轮询 events_after 拉新气泡。
  - 会话: 有进行中（未结束）会话 → resume（含 brain digest 注入世界线记忆）;
    无 → 新开世界线（平行世界语义, 见 DESIGN_WORLD.md）。

注意: 引擎实例在内存（单用户本机）; 重启服务丢内存状态但事件流在,
     重新 open_session = resume 重建。
"""
from __future__ import annotations

import logging
import threading

from core.mmt.engine import MomoTalkEngine
from core.session.events import M_VN_ENTER, M_VN_EXIT
from core.text import _strip_action_brackets
from infra import paths
from llm.client import LLMClient
from webgui import deps  # 接缝（C1a）: store 等可替换依赖

logger = logging.getLogger(__name__)

# 角色卡与关系表的路径真源 = `infra/paths.py`（**绝对路径, cwd 无关** —— uvicorn 从任意
# 目录启动; 从前这里自己 `Path(__file__).parent.parent` 拼 —— frozen 下会指向 bundle,
# 读不到用户在 exe 同级放的人设卡）
CHAR_ROOT = paths.CHARACTERS_DIR
# 数据根与 `SessionStore` 实例已随 C1a 搬到 `webgui/deps.py`
# ——这里不再留副本（同一事实两个来源 = 迟早对不上）。
INTERPERSON_PATH = paths.INTERPERSON_PATH

# ---------------------------------------------------------------------------
# 引擎管理（每 char 独立实例 + 同 char 串行锁）
# ---------------------------------------------------------------------------

_engines: dict[str, MomoTalkEngine] = {}
_locks: dict[str, threading.Lock] = {}
# 后台任务状态 + 输入队列（排队连发）: (char_id, session_id) → ...
_tasks: dict[tuple[str, str], dict] = {}
_queues: dict[tuple[str, str], list[str]] = {}
_worker_running: dict[tuple[str, str], bool] = {}

#: 入口预热开关（EXEC_BOND_LATENCY P1）: 触发轮结束即后台生成 bond 首场——
#: 玩家阅读触发对白/犹豫期间生成完成, 点击粉泡时通常已就绪（体感 ~0 等待）。
#: 关掉 = 回到"点击后才生成首场"的现状。
PREWARM_ENABLED = True


def _engine(char_id: str) -> MomoTalkEngine:
    """某角色的引擎实例（懒创建, 每 char 独立——并行多角色的基础）。"""
    if char_id not in _engines:
        _engines[char_id] = MomoTalkEngine(
            CHAR_ROOT,
            LLMClient(),
            interperson_path=INTERPERSON_PATH,
            store=deps.store(),                  # 接缝（C1a）: 测试换 store 后即时生效
        )
    return _engines[char_id]


def _lock(char_id: str) -> threading.Lock:
    """同 char 串行锁（防同一角色双标签页并发 / 等待中重复发送）。"""
    if char_id not in _locks:
        _locks[char_id] = threading.Lock()
    return _locks[char_id]


def reset_engines() -> None:
    """清空引擎实例（设置变更后调用——下次 `_engine()` 按新配置重建）。

    引擎构造时 LLMClient 已把 settings.toml 的 key/base_url 写死（含 Authorization
    header）——改配置后不重建则旧实例继续用旧 key（假 key 时期创建的实例改 key
    不生效）。设置路由保存成功后调用本函数。

    **2026-09-13 修正（审计 B17）: 不再 `_locks.clear()`。**
    锁是**并发保护**而非引擎的一部分: 一次 `agent_turn` 可能正持着旧 Lock 在跑,
    清掉 `_locks` 后新调用者拿到的是**另一个 Lock** → 同一角色两个 turn 并行
    跑（串行不变量被打破, 会话/事件流都可能写乱）。引擎重建本身不需要动锁——
    新引擎是通过 `_engine()` 惰性造的, 与锁无关。
    """
    _engines.clear()


# ---------------------------------------------------------------------------
# 会话生命周期
# ---------------------------------------------------------------------------

def _inject_brain_on_open(engine: MomoTalkEngine, char_id: str, session_id: str) -> None:
    """**会话打开即装填 brain 段**（★ P1, 2026-09-21）。

    病灶: `start_session` **不清空也不重读** `_brain_injection`（`engine.py:374` 只把它
    初始化成 `""`），而 `_inject_brain` 此前只有 **digest 完成** 与 **resume** 两个调用点
    ⇒ **新世界线会话的 brain 段是空串**：出厂背景段 + 全部 wiki 记忆都不进 prompt
    （盒A 的六文件人设 dump 不受影响——那走 `_persona_mmt`）。

    ⚠️ 这在真机上**是常态不是边角**: `bond_finish` 会 `finish(..., ended=True)`
    （`webgui/bond/api.py:504`）⇒ **每完成一章该会话即"结束"** ⇒ 章之后（以及任何一次
    进程重启之后）打开 MMT 必然走新分支 ⇒ 角色"完全不记得刚跑完的那章"。
    实测指纹（2026-09-21）: 22:16:40 那次 digest 有 `recall_read`；而 23:00 / 23:18 三次
    `新会话` 之后**一行 `recall_read` 都没有** —— 那三个会话全程无记忆。

    只读（`digest=False`: 不消化、不写库）；失败静默（`_inject_brain` 内部已兜底，
    这里再兜一层防伪 store/坏档把"开会话"整条打挂）。顺带打一行 INFO，让"这次打开注入了
    什么"在 diag 里可归因——与 `recall_read` 那行配套读。
    """
    try:
        engine._inject_brain(char_id, session_id)        # 与 webgui 其它接线同款（碰私有名）
    except Exception as e:                              # noqa: BLE001 — 注入失败不阻断开会话
        logger.warning("新会话 brain 注入失败（照常开会话）: %s", e)
        return
    seg = getattr(engine, "_brain_injection", "") or ""
    logger.info("新会话 brain 注入: %s/%s seg=%d 字%s", char_id, session_id, len(seg),
                "" if seg else "（空: wiki 无节点且出厂背景为空）")


def _record_name(char_id: str, name: str) -> None:
    """把显示名补进会话元数据 —— **只补缺**（已有名字不动），失败静默。

    名字该落在 `meta.json` 而不是"每次去角色卡现查": 角色卡改名/删除之后, 那条会话
    仍然该记得它当初是谁（CLI 列表读的就是这一格）。
    """
    if not name:
        return
    try:
        if deps.store().ensure_character_name(char_id, name):
            logger.info("会话元数据补名字: %s ← %r", char_id, name)
    except Exception as e:                              # noqa: BLE001 — 改名不许阻断开会话
        logger.warning("会话元数据补名字失败（不影响开会话）: %s", e)


def open_session(char_id: str) -> dict:
    """打开某角色的会话: 有进行中 → resume; 无 → 新开世界线。

    Returns: {session_id, display_name, new: bool, in_vn: bool}
    """
    engine = _engine(char_id)
    # 找进行中会话（list_open 按 created_at 倒序, 取最近）
    open_meta = next(
        (m for m in deps.store().list_open() if m.character_id == char_id), None)
    if open_meta is not None:
        res = engine.resume_session(char_id, open_meta.session_id)  # 含 brain digest
        display_name = res["display_name"]
        _record_name(char_id, display_name)             # 旧档: meta 里没有名字就补上
        return {
            "session_id": open_meta.session_id,
            "display_name": display_name,
            "new": False,
            "in_vn": res["status"].get("in_vn", False),
        }
    # 新世界线（先拿名字再建线——`create` 要在那一刻就把名字写进 meta）
    display_name = engine.start_session(char_id)
    meta = deps.store().create(char_id, display_name)
    engine.attach_session(meta.session_id)
    _inject_brain_on_open(engine, char_id, meta.session_id)   # ★ P1: 新分支也要装填
    return {
        "session_id": meta.session_id,
        "display_name": display_name,
        "new": True,
        "in_vn": False,
    }


# EXT: world-switch-m2 — 显式开新世界线（M2 未落地; 与 open_session 兜底分支逻辑重复）; 勿删（docs/EXTENSION_POINTS.md）
def new_world(char_id: str) -> dict:
    """显式开新世界线（平行世界语义: 旧线保留, 新线从零开始）。"""
    engine = _engine(char_id)
    display_name = engine.start_session(char_id)
    meta = deps.store().create(char_id, display_name)
    engine.attach_session(meta.session_id)
    _inject_brain_on_open(engine, char_id, meta.session_id)   # ★ P1: 同款（别漏这条）
    return {"session_id": meta.session_id, "display_name": display_name, "new": True}


# ---------------------------------------------------------------------------
# 后台任务（agent_turn 线程）
# ---------------------------------------------------------------------------

def chat_async(char_id: str, session_id: str, text: str) -> dict:
    """发起一轮对话（入队, worker 串行消费, 立即返回）。

    排队语义: 玩家连发多条 → 依次入队, worker 逐条跑 agent_turn（同 char 锁串行）;
    后面的 agent_turn 会看到前一条的完整上下文（LLM 综合回复, 见 momotalk_rules
    的"连续消息/插嘴"提示——不必逐条机械回应）。
    Returns: {accepted: bool, queued: bool}
    """
    key = (char_id, session_id)
    _queues.setdefault(key, []).append(text)
    if _worker_running.get(key):
        return {"accepted": True, "queued": True}
    _worker_running[key] = True
    threading.Thread(target=_worker, args=(char_id, session_id), daemon=True).start()
    return {"accepted": True, "queued": False}


def _worker(char_id: str, session_id: str) -> None:
    """worker: 串行消费输入队列（同 char 锁 + 单 worker 保证串行）。

    单个 agent_turn 失败不退出 worker（队列剩余消息继续处理）。失败不落库
    （微信语义: 发不出去的消息不存档——前端感叹号 + 重发/删除; 重发成功
    才有一条 player 事件）。
    """
    key = (char_id, session_id)
    try:
        with _lock(char_id):
            while _queues.get(key):
                text = _queues[key].pop(0)
                try:
                    _tasks[key] = {"running": True, "error": ""}
                    engine = _engine(char_id)
                    # 引擎状态兜底: reset_engines（设置页保存）后引擎实例被清空,
                    # 前端已打开的聊天窗仍可发消息——current_char 失效会 NotInSession
                    # → 自动重新 open_session（resume/新线）重建会话状态
                    if engine._current_char is None or engine._session_id != session_id:
                        try:
                            open_session(char_id)
                        except Exception as e2:   # noqa: BLE001 — 重建失败走原路径报错
                            logger.warning("会话状态重建失败 (%s): %s", char_id, e2)
                        engine = _engine(char_id)
                    result = engine.agent_turn(text)
                    if PREWARM_ENABLED and bool(result.bond_story):
                        # 入口预热（EXEC_BOND_LATENCY P1）: 触发轮结束即后台生成
                        # 首场——此刻事件流已终态（含触发轮对白）、engine.trace 仍
                        # 留着触发动作（章节标题）, 与点击时上下文一致。同步调用:
                        # bond_start 同步段 0 LLM 立即返回, 生成线程自行等 chat 锁。
                        # 失败降级: 点击时走现场生成, 零影响。
                        try:
                            from webgui import bond as _bond  # 延迟 import 破环
                            _bond.bond_start(char_id, session_id, staged=True)
                        except Exception as e3:          # noqa: BLE001 — 预热失败降级
                            logger.warning("bond 首场预热失败（点击时现场生成）: %s", e3)
                    # result.bond_story=True → 前端粉泡入口; vn_enter marker 由
                    # bond_start 落（staged 预热不落, 点击 adopt 时补——见 bond.py）
                    _tasks[key] = {"running": False, "error": "",
                                   "bond_story": bool(result.bond_story)}
                except Exception as e:            # noqa: BLE001 — LLM 失败/循环超限
                    logger.warning("agent_turn 失败 (%s/%s): %s", char_id, session_id, e)
                    _tasks[key] = {"running": False, "error": str(e),
                                   "failed_text": text}   # 前端转感叹号（微信式）
    finally:
        _worker_running[key] = False


def task_status(char_id: str, session_id: str) -> dict:
    """查询后台任务状态（前端轮询: busy=还在处理 or 队列有 pending / 出错 / bond）。"""
    key = (char_id, session_id)
    st = dict(_tasks.get(key, {"running": False, "error": ""}))
    st["busy"] = bool(st.get("running")) or bool(_queues.get(key)) \
        or _worker_running.get(key, False) or key in _external_busy
    return st


#: 外部流程占用 MMT 任务位（2026-09-11）: 羁绊收尾 wrapup 跑在自己的线程里,
#: 不走 `_worker` → 前端 `pollLoop` 在 VN 退出后第一轮就看见 `running: false`
#: 于是**停止轮询**, 收尾气泡要等玩家切页/重进才被 `since=0` 全量拉出来
#: （真机报障"finish 后 mmt 不会立刻逐条显示, 必须到其他页面再回来"）。
#: task_begin/task_end 让外部流程也如实反映"还在跑", 前端据此继续轮询 + 显示打字中。
_external_busy: set[tuple[str, str]] = set()


def task_begin(char_id: str, session_id: str) -> None:
    """标记该会话有外部流程在跑（前端轮询保持; 与 MMT worker 的 busy 等价）。"""
    key = (char_id, session_id)
    _external_busy.add(key)
    _tasks[key] = {"running": True, "error": ""}


def task_end(char_id: str, session_id: str, error: str = "") -> None:
    """外部流程结束（清忙态; error 走既有字段, 前端可显示失败）。"""
    key = (char_id, session_id)
    _external_busy.discard(key)
    _tasks[key] = {"running": False, "error": error}


# ---------------------------------------------------------------------------
# 事件查询（轮询）
# ---------------------------------------------------------------------------

def _bond_done_map(events, display_name: str = "") -> dict[int, str]:
    """完整事件流 → {触发事件 seq: 已完成文本}（气泡淡化, 2026-09-07）。

    配对规则（单事件流顺序扫描）: mmt_trigger_bond_story →（其后的）vn_enter
    （章节标题）→ …bond 事件… → vn_exit。vn_exit 带 completed=True（完整走完,
    含兜底收尾）→ 该次触发入口横幅应淡化为"已完成羁绊剧情：{标题}"——不可再点;
    completed=False（中途退出）→ 保持可点击（resumed 续进）。
    标题优先级: vn_enter.chapter_title > 触发事件 payload.chapter_title > display_name。
    """
    result: dict[int, str] = {}
    open_entry: int | None = None          # 最近一个尚未收尾的触发事件 seq
    pending_title = ""
    for e in events:
        t = getattr(e, "type", None)
        if t == "mmt" and e.subtype == "mmt_trigger_bond_story":
            open_entry = e.seq
            pending_title = str((e.payload.get("chapter_title") or "").strip())
        elif open_entry is not None:
            if t == "marker" and e.subtype == M_VN_ENTER:
                ct = str((e.payload.get("chapter_title") or "").strip())
                if ct:
                    pending_title = ct
            elif t == "marker" and e.subtype == M_VN_EXIT:
                if e.payload.get("completed"):
                    title = pending_title or display_name or "羁绊"
                    result[open_entry] = f"已完成羁绊剧情：{title}"
                open_entry = None           # 收尾（完成/中断）→ 配对关闭
    return result


def render_chat_events(events, display_name: str = "",
                       bond_done: dict[int, str] | None = None) -> list[dict]:
    """事件流 → 气泡列表 [{kind?, side, text, seq, subtype?}]。

    kind="bond_entry"（入口渲染）: mmt_trigger_bond_story 事件 → BA 风格粉色
    横幅"进入 xx 的羁绊剧情"（display_name 缺失用"羁绊"）。
    kind="bond_done": 该次剧情已完整走完（vn_exit completed=True）→ 淡行
    "已完成羁绊剧情：{标题}", 不可点击（bond_done: {触发 seq: 文本} 由调用方
    从完整事件流预计算——增量轮询时触发事件与收尾 marker 不在同一批, 需要全量视角）。
    其余: 角色回复**去动作括号后原样一条** = 一个气泡。

    ⭐ **一行 = 一个气泡**（2026-10-07 收尾 ⑥-2e）: 从前这里还过一道
    `split_reply_chunks`（字数+**随机**阈值切块, "模拟真人一条条发消息"）。
    ⑥-2e 起"一行 = 一条消息"已由**契约**定下（模型自己决定分几行说）——
    引擎再切一刀是**替她重切**, 副作用还三个: ① 条数**没有可解释的规则**
    （逗号前 6~10 字才掷一次骰子）② 切处**丢逗号** ③ 同一条回复在前端(按 seq 播种)
    与**喂 LLM 的历史**(没播种 ⇒ 走全局 random)两处切法不一致, 后者每轮重渲都在变
    ⇒ **前缀缓存被破坏**。切句器本体与它的单测**按用户裁决保留**（CLI 终端
    `core/display.py` 仍在用; 将来若要"行内二次切分", 回退位置就在这一行）。
    玩家消息不切（原样）。
    """
    bubbles: list[dict] = []
    for e in events:
        if getattr(e, "type", None) != "mmt":
            continue
        if e.subtype == "mmt_trigger_bond_story":
            # 触发轮完整渲染（原 bug: continue 吞掉 player+reply——"不声不响"+重进消失）:
            # 玩家消息 → AI 触发回复（当面对白）→ 粉色横幅（或已完成淡行）
            player = (e.payload.get("player") or "").strip()
            reply = (e.payload.get("reply") or "").strip()
            if player:
                bubbles.append({"side": "player", "text": player, "seq": e.seq})
            if reply:
                text = _strip_action_brackets(reply).strip()
                if text:
                    bubbles.append({"side": "char", "text": text,
                                    "seq": e.seq, "subtype": e.subtype})
            done_text = (bond_done or {}).get(e.seq)
            if done_text:
                bubbles.append({"kind": "bond_done", "text": done_text,
                                "seq": e.seq})
            else:
                name = display_name or "羁绊"
                bubbles.append({"kind": "bond_entry",
                                "text": f"进入 {name} 的羁绊剧情", "seq": e.seq})
            continue
        player = (e.payload.get("player") or "").strip()
        reply = (e.payload.get("reply") or "").strip()
        if player:
            bubbles.append({"side": "player", "text": player, "seq": e.seq})
        if reply:
            text = _strip_action_brackets(reply).strip()
            if text:
                bubbles.append({"side": "char", "text": text,
                                "seq": e.seq, "subtype": e.subtype})
    return bubbles


def events_after(char_id: str, session_id: str, since: int = 0,
                 display_name: str = "") -> dict:
    """轮询: seq > since 的 mmt 事件（渲染成气泡）+ 最新 seq + 任务状态。

    since=0 → 全量（打开聊天窗时拉历史）。display_name 供 bond_entry 横幅。
    """
    events = deps.store().events(char_id, session_id)
    new_events = [e for e in events if e.seq > since]
    status = task_status(char_id, session_id)
    # 完成态视角 = 全量事件流（触发与收尾 marker 可能跨多次轮询才到齐）
    done = _bond_done_map(events, display_name)
    return {
        "bubbles": render_chat_events(new_events, display_name, bond_done=done),
        "last_seq": max((e.seq for e in events), default=0),
        "running": bool(status.get("busy")),   # busy = 正在跑 or 队列有 pending
        "error": status.get("error", ""),
        "bond_story": bool(status.get("bond_story")),
        # 气泡淡化（2026-09-07）: 已完成剧情入口 [{seq, text}]——前端把已渲染的
        # 粉泡原地翻成淡行（历史渲染路径已直接产出 bond_done 气泡）
        "bond_done": [{"seq": s, "text": t} for s, t in sorted(done.items())],
        # 微信式失败: worker 异步失败时标记哪条消息没送达（前端转感叹号 + 重发/删除）
        "failed": {"text": status["failed_text"], "error": status["error"]}
        if status.get("failed_text") else None,
    }
