# -*- coding: utf-8 -*-
"""`webgui.bond` 的**对外动作层**（C8, `docs/EXEC_SPLIT.md`）—— HTTP 门面 + 收尾。

## 放什么

`bond_start` / `bond_turn` / `bond_status` / `bond_finish`（路由层调用的全部动作）·
`bond_start_demo`（演示剧本）· `_start_replay`（回放编排）· `_ready_scene_payload` /
`_role_info`（场景载荷）· `_entry_already_done`（重进闸）· `_note_reject` / `_clear_rejects`
（被拒诊断）· `_wrapup` / `_wrapup_inner`（收尾话 + digest 唯一触发点）· `DEMO_SCRIPT`。

## 原 `webgui/bond.py` 的模块说明（逐字保留 —— 这一层就是它的对外契约）

    webgui 羁绊剧情驱动 — CLI run_bond_story_vn（core/ui/vn_cli.py）的异步化状态机。
    
    CLI 是同步循环（send_vn_scene → 渲染 → 玩家输入 → 下一场）; webgui 拆成
    请求驱动的状态机（与 chat.py 的后台线程 + 轮询模式一致）:
    
        bond_start    → 构造 BondStoryEngine（复用引擎 llm + director + brain 注入）
                        + 落 vn_enter marker + 首场 seed → 后台生成首场
        bond_turn     → 玩家裁决（选项/自由输入）→ 补录上一场事件（append-only:
                        本场事件在玩家裁决时落库, 带 picked）→ 后台生成下一场
        bond_status   → 轮询: busy / scene / error / completed
        bond_finish   → 补录最后一场（is_end, picked=None）+ vn_exit + session_end
                        + wrapup 收尾（agent_turn 收尾话, 落 mmt 事件）→ async_digest
                        （digest 唯一触发点: bond 闭环）
    
    与 CLI 对齐的语义:
        - 收尾兜底（remind/end 系统注记; 2026-09-09 起无超限伪收场）
        - 纪念子模式（in_memorial → 注入 exit schema; 无生图 → 纯文字, 剧情照走）
        - 失败降级（SceneLoopError → closing 场景落库 + completed, 宁缺勿错）
        - 事件流: bond 事件 {input, picked, ...scene} + memorial/vn_state marker
          （与 CLI 落库格式一致, 回放兼容）
    
    注意: BondStoryEngine 实例在内存（单用户本机, 同 chat.py 引擎管理）;
    重启服务丢内存态, 事件流在——中断的 VN 通过 vn_state marker 可重建（M3 回放）。
"""


from __future__ import annotations

import json
import threading
import time
import logging
from core import paths
from core.bond.bond_story import (
    BondScene,
    BondStoryEngine,
)
from core.mmt.engine import load_brain_segment
from core.session.events import (
    M_VN_EXIT,
    make_event,
)
from core.session.maintenance import exclude_abandoned
from core.session.renderer import (
    render_bond_scene_text,
    window_messages,
)
from core.session.staging import (
    close_open_attempts,
    commit_staging,
    truth_store,
)
from core.director.wiring import (          # C11: 接线层（此前借道 core.ui.vn_cli）
    _build_director,
    _trigger_title,
)
from webgui import chat, deps
from webgui.bond.lanes import (
    _anno_worker,
    _ensure_lane,
    _place_worker,
    _scene_emotions_ready,
    _scene_obj_visual_ready,
    _scene_places_ready,
    _scene_ready_or_busy,
    _scene_visual_ready,
    _wait_annotated,
)
from webgui.bond.memorial import _ensure_memorial_img
from webgui.bond.pregen import (
    _discard_boards,
    _discard_candidates,
    _generate,
    _log_board_deliver,
    _pregenerate,
    _scene_landed,
    _spawn_candidates,
)
from webgui.bond.replay import (
    _enter_title,
    _interrupted_replay_queue,
    _pending_in_vn,
    _prev_chapter_quit,
    _title_from_events,
)
from webgui.bond.state import (
    BoardLifecycle,
    BondState,
    _bonds,
    _state,
)
from webgui.bond.stores import (
    _close_memorial_window,
    _draft_pending,
    _draft_queue,
    _draft_save,
    _flow_store,
    _last_bond_seq,
    _last_mmt_seq,
    _log_scene,
    _log_scene_meta,
    _prewarm_cache_delete,
    _prewarm_cache_load,
    _stage_store,
    _store,
)
from webgui.bond.util import _ms_since
from webgui.bond.watchdog import _watchdog

logger = logging.getLogger(__name__)


DEMO_SCRIPT: list[dict] = [
    {
        "title": "放学后的约定",        # 章节标题 → 开场标题面板（对齐官方"预先应对"样式）
        "background": "class_room",
        "paragraphs": [
            {"text": "（演示·第 1 场）放学后的教室，夕阳把窗框的影子拉得很长。",
             "emotion": "nomal"},
            {"text": "「老师……那个……今天可以一起走回家吗？」她低着头，手指绞着衣角。",
             "emotion": "embarrassed"},
        ],
        "choices": ["「当然可以。」", "「我还有点事，改天吧。」"],
        # 同响应分支（板块契约）: 选完立即展示——零等待
        "branches": {
            "「当然可以。」": [
                {"text": "（她眼睛一下子亮了起来，用力点头）", "emotion": "happy"},
                {"text": "「嗯！那、那说好了哦……！」", "emotion": "embarrassed"},
            ],
            "「我还有点事，改天吧。」": [
                {"text": "（她愣了愣，随即笑着摆摆手）", "emotion": "smile"},
                {"text": "「嗯……那老师，改天一定要约我哦。」", "emotion": "expectant"},
            ],
        },
    },
    {
        "background": "wildhunt_street",
        "paragraphs": [
            {"text": "（演示·第 2 场）晚风拂过发梢，她悄悄靠近了些，脚步轻快。",
             "emotion": "smile"},
            {"text": "「老师，下次……下次还能像这样一起走吗？」她抬头，目光期待。",
             "emotion": "expectant"},
        ],
        # 纯叙事场（无 choices）——2026-08-30 契约语义: 整段剧情 2~3 次选择,
        # 其余场次纯叙事推进（前端"继续"按钮, 后端预生成零等待衔接）
    },
    {
        # 结束余韵（官方 bond story 结束样式）: 无背景 → 黑屏 + 一句旁白 + 右下三角
        "paragraphs": [
            {"text": "（目送她走远后，我站在原地——这个普通的傍晚，好像变得格外温柔。）",
             "emotion": "pensive"},
        ],
        "is_end": True,
    },
]


def _note_reject(state: "BondState", reason: str, char_id: str,
                 session_id: str) -> None:
    """推进被拒留痕（2026-09-11）: 前端会重试, 后端不记就等于没发生。

    首次 + 每 10 次打一条 WARNING（含计数与原因）, 让 diag 日志能直接读出
    "继续键被什么挡住了、挡了多久"——真机 110s 那种事故下次可一眼定位。
    """
    n = int(state.turn_rejects.get(reason, 0)) + 1
    state.turn_rejects[reason] = n
    if n == 1 or n % 10 == 0:
        logger.warning("bond_turn 被拒 %s/%s reason=%s 第 %d 次（客户端在重试）",
                       char_id, session_id, reason, n)


def _clear_rejects(state: "BondState", char_id: str, session_id: str) -> None:
    """推进成功 → 报一次"此前被拒 N 次"（把等待时间归因清楚）。"""
    if not state.turn_rejects:
        return
    summary = ", ".join(f"{k}×{v}" for k, v in state.turn_rejects.items())
    logger.info("bond_turn 接受（此前被拒: %s） %s/%s", summary, char_id, session_id)
    state.turn_rejects = {}


def _entry_already_done(char_id: str, session_id: str, store=None) -> bool:
    """这条羁绊入口的剧情**已经完整走完**了吗？（后端兜底, 只看真源）

    判据（倒序扫事件）: 先遇到 `vn_exit` 还是 `mmt_trigger_bond_story`——
    * 先遇到 `vn_exit` 且 `completed=True` ⇒ 这次触发已经走完（其后没有更新的触发）;
    * 先遇到**更新的触发** ⇒ 这是新一章, 放行;
    * 什么都没有 ⇒ 放行（全新进入）。

    ⚠️ `BondState.completed` 是**内存态**（重启即丢）; 这条是它的**事件流版本**,
    用来堵"结局粉泡翻转前的窗口里手快重进"（用户 2026-09-20 报障）。
    中途退出（`completed=False`）**不算走完** —— 那种要允许重进（静默续章）。
    """
    try:
        evs = (store or _flow_store(_state(char_id, session_id))).events(char_id, session_id)
    except Exception:                                # noqa: BLE001 — 读失败不拦
        return False
    for e in reversed(list(evs)):
        if e.is_marker and e.subtype == M_VN_EXIT:
            return bool((e.payload or {}).get("completed"))
        if e.type == "mmt" and e.subtype == "mmt_trigger_bond_story":
            return False                             # 更新的触发在 vn_exit 之后
    return False


def _ready_scene_payload(state: BondState, char_id: str = "") -> dict:
    """进入响应里带上"已就绪场景"——客户端可**立即上屏**（免黑屏 + 免一轮轮询）。

    2026-09-11 真机报障"重进中断剧情先黑屏还要加载一小段时间": 回放/预热命中/
    adopt 就绪/内存态续玩这些路径场景**本来就在手里**（纯读文件, 后端 ~0.1s）,
    但旧协议只回 `resumed: true` → 前端去 waitScene 轮询（700ms 起）+ 黑屏标题屏
    （bgUrl 空）→ 看着像"在加载"。现在把场景连同 round/emo_version 一起回:
    前端拿到即 renderScene, 后续轮询靠 round/指纹去重不会重播。

    **名字牌（name/club）也一起回**（2026-09-11 冒烟抓到）: 旧流程的名字牌信息
    只在 `/api/bond/status` 里, 不走轮询的路径会让社团栏空着——那是"随角色变动
    的两个字段", 必须随首帧到。

    场景不存在（真在生成中）→ 返回 {}（调用方保持原语义, 前端走等待卡）。
    """
    if state.scene is None:
        return {}
    out = {"scene": state.scene, "round": state.round,
           "emo_version": state.emo_version}
    # 纪念态随场景一起回（2026-09-12）: 直返场景不走 waitScene, 而纪念的立绘隐藏/
    # 背景清空/图淡入都在前端 `syncMemorial` 里——不带这几个字段就会"纪念板照常
    # 显示立绘 + 普通背景"（B 层冒烟实测抓到）。与 `/api/bond/status` 同源。
    if state.vn is not None:
        out["in_memorial"] = bool(state.vn.in_memorial)
        out["memorial_img"] = state.memorial_img or None
        out["memorial_img_busy"] = state.memorial_img_busy
    if char_id:
        try:
            role = _role_info(char_id)
            out["name"] = role.get("name", "")
            out["club"] = role.get("club", "")
        except Exception:                            # noqa: BLE001 — 名字牌降级
            pass
    return out


def _start_replay(state: BondState, replay_q: list[dict],
                  char_id: str, session_id: str) -> dict:
    """进入回放模式: 引擎就绪（handoff 用, 历史=事件流窗口）+ 首场入屏。

    回放场景 `scene_state=COMMITTED`（正文来自事件流, 不重复落）; 若队列只有一场（或
    最后一场入屏后队列尽）→ 立即预生成续写（_pregenerate, 玩家读屏期间完成,
    handoff 时零等待）。不写 vn_enter（事件流已有在押的——沿用同一段）。
    """
    engine = chat._engine(char_id)
    char = engine.current_character
    if char is None:
        return {"accepted": False, "error": "会话未打开"}
    brain_segment = load_brain_segment(
        _store(), char.character_id, char.display_name,
        characters_root=engine.char_loader.root)
    vn = BondStoryEngine(
        engine.char_loader.root, engine.llm,
        director=_build_director(char), brain_segment=brain_segment)
    vn.start_session(char.character_id)
    try:
        _evs = exclude_abandoned(_flow_store(state).events(char_id))
        _win = window_messages(_evs)
        if _win:
            vn._history = _win                # 前缀(含已记录场景)+ 触发前对话
    except Exception:                                # noqa: BLE001 — 灌窗失败不阻断
        pass
    state.vn = vn
    state.vn_enter_written = True             # 事件流已有该段 vn_enter（不重复落）
    # ⭐ 2026-09-20: 中断续章同样要写"回来"。`replay_attempts` 把
    # `vn_exit completed=False` 判成 `interrupted=True` ⇒ **中途退出后再进走的就是这条路**
    # （回放已读前缀 + 续同一章, 不新开 vn_enter）。注记落在**回放队列耗尽后的第一块
    # 新板**上（那才是"老师回来之后"的新内容）。
    state.quit_resume = _prev_chapter_quit(char_id, session_id, _flow_store(state))
    state.replay_scenes = list(replay_q)
    try:
        from webgui.routers.bond import warm_render
        warm_render(char.character_id)
    except Exception:                                # noqa: BLE001 — 预热失败降级
        pass

    first = state.replay_scenes.pop(0)
    state.scene_obj = BondScene.from_dict(first)
    state.scene_obj._place_done = True    # 回放场景来自事件流（视觉键已定格）——不占 lane
    # 回放的纪念板也进纪念态（2026-09-12）: 否则重放纪念段时立绘照常显示、背景照常亮
    # （v2 区间 = 本块内, 其后从草稿/待发队列领出的板会沿用这个标志, 直到新生成一块）
    state.vn._in_memorial = bool(state.scene_obj.memorial)
    _ensure_memorial_img(state, char_id, session_id)     # 回放: 恢复档案纪念图
    state.scene = state.scene_obj.to_dict()
    state.round = 1
    state.scene_state = BoardLifecycle.COMMITTED   # 正文来自事件流——回放不重复落
    _log_board_deliver(state, state.scene_obj, char_id, session_id, "replay")
    if not state.replay_scenes:
        # 单场（或最后一场）: 续写在读屏期间备好 → 交棒零等待。
        # 顺序（2026-09-12 修正）: **先接草稿旁路**（已生成未播放的板, 0 LLM,
        # 内容不丢, 排队不动屏上场景）→ 没有再预生成。此前这里直接 `_pregenerate`,
        # 于是"选了选项后关页面再进"会把已生成的后继板丢掉、重新生成一份
        # （实测: `bond_pregen src=gen` 紧跟 `bond_board_deliver src=replay`）。
        if not _draft_queue(state, char_id, session_id):
            _pregenerate(state, char_id, session_id)
    return {"accepted": True, "busy": state.busy, "resumed": True,
            "replay": True,
            "chapter_title": _enter_title(state, char_id, session_id),
            **_ready_scene_payload(state, char_id)}


def _role_info(char_id: str) -> dict:
    """角色显示屏信息 {name, club}——前端名字牌（官方: 名字 + 便利屋68）。

    ⚠️ **2026-09-20 修（真机报障: 回忆册回放的名字牌显示 `igusa_haruka`）**:
    原先只问 `chat._engine(char_id).current_character` —— 那是**内存里的 MMT 引擎**,
    只在"这个角色的会话开过且没被清"时才有。玩家从**回忆册**直接进回放（没开聊天、
    或服务端重启过）时取不到 → 回落到 id → 名字牌就成了 `igusa_haruka`。
    现在**两级**: ① 内存引擎（最快, 且与 MMT 列表同源）→ ② **角色卡（磁盘）** ——
    后者与 `collection.book` 取名字是同一条路（`CharacterLoader`）, 不依赖会话。
    """
    try:
        ch = chat._engine(char_id).current_character
        if ch is not None:
            club = ch.profile.get("club") or ch.profile.get("SIG~club") or ""
            return {
                "name": ch.display_name or char_id,
                "club": str(club).split("（")[0].split("(")[0].strip(),
            }
    except Exception:                                # noqa: BLE001 — 内存态取不到 → 走磁盘
        pass
    try:                                             # ② 角色卡（无会话也能取）
        from core.parsing.dynamic_character_parser import CharacterLoader
        ch2 = CharacterLoader(paths.CHARACTERS_DIR).load(char_id, strict=False)
        club = ch2.profile.get("club") or ch2.profile.get("SIG~club") or ""
        return {
            "name": ch2.display_name or char_id,
            "club": str(club).split("（")[0].split("(")[0].strip(),
        }
    except Exception as e:                           # noqa: BLE001 — 取不到降级用 id
        logger.debug("_role_info 角色卡读取失败 %s: %s", char_id, e)
    return {"name": char_id, "club": ""}


def bond_start(char_id: str, session_id: str, *,
               staged: bool = False) -> dict:
    """进入羁绊剧情: 构造引擎 + vn_enter marker + 后台生成首场。

    入口预热（staged=True, EXEC_BOND_LATENCY P1）: 触发轮结束由 chat worker 调用
    ——首场立即后台生成, 玩家点击时通常已就绪。staged 期间**不落 vn_enter marker**
    （防未点击被推导 in_vn）; 玩家点击命中预热态 → adopt: 新鲜度校验（点击前
    事件流未前进）通过 → 补落 marker + staged_seq=None → 以现有引擎继续。

    幂等/守卫: 已有进行中的 bond 状态（真实引擎或演示剧本）→ 返回现状（前端
    重进不重建）; 已完成（completed）→ 拒绝再进入; 生成在途（busy）→
    accepted=True 让前端轮询等待（P1 语义变更: 预热在途时点击是常态, 不再以
    accepted=False 报错）。中断再进入: 内存态在（resumed）→ 从中断场景继续。
    """
    state = _state(char_id, session_id)
    if state.completed:
        return {"accepted": False, "completed": True,
                "error": "这段羁绊剧情已经完成"}
    # ⚠️ 2026-09-20 用户: *"结束后那个粉色气泡有小段延迟才消失，这个时间是足够手快的
    #    玩家直接重进，后果不堪设想"* —— 前端在 finish 那一刻已即时锁粉泡
    #    （`window.mmtLockBondEntries`）; 这里是**后端兜底**, 防"锁还没生效就点进来"
    #    或服务端重启后内存态没了的同类窗口。
    #    只看事件流（`state.completed` 只是内存态, 重启即丢）:
    #    最近一条 `vn_exit completed=True` 之后**没有更新的触发** ⇒ 这条入口已走完。
    if _entry_already_done(char_id, session_id, _flow_store(state)):
        logger.info("bond_start 拒绝: 入口已完成（幂等兜底） %s/%s", char_id, session_id)
        return {"accepted": False, "completed": True,
                "error": "这段羁绊剧情已经结束（无需重进）"}

    # ── 预热 adopt（staged 态 + 玩家点击 / 再次 staged 调用）────────
    if state.vn is not None and state.staged_seq is not None:
        store = _flow_store(state)
        if _last_mmt_seq(char_id, session_id, store) != state.staged_seq:
            # 预热后玩家又聊过（新 mmt 事件）/ 新触发轮 → 预热上下文过期, 丢弃重建
            logger.info("bond 预热态过期（mmt seq %s ≠ %s）, 丢弃重建: %s/%s",
                        state.staged_seq, _last_mmt_seq(char_id, session_id, store),
                        char_id, session_id)
            _bonds.pop((char_id, session_id), None)
            state = _state(char_id, session_id)
        else:
            # adopt: 补落 vn_enter marker（触发事件之后、首场裁决落库之前——时序正确）
            if not state.vn_enter_written:
                try:
                    store.enter_vn(char_id, session_id, state.chapter_title)
                    state.vn_enter_written = True
                except Exception as e:               # noqa: BLE001 — 写失败降级不阻断
                    logger.warning("adopt vn_enter 写入失败: %s", e)
            # 计时埋点（§6.1）: 点击时预热态是否已就绪 + 预热起点 latency
            logger.info(
                "bond_click adopt %s/%s lat=%dms ready=%s",
                char_id, session_id,
                _ms_since(state.t_staged) if state.t_staged > 0 else -1,
                "y" if not state.busy else "n")
            state.t_staged = 0.0
            state.staged_seq = None
            _prewarm_cache_delete(char_id, store)   # adopt 消费（首场已进玩家视野）
            if state.busy:
                # 预热生成仍在途 → 前端轮询等待（resumed=False → 章节等待卡可见）
                return {"accepted": True, "busy": True, "resumed": False,
                        "chapter_title": _enter_title(state, char_id, session_id)}
            # adopt 就绪（最常见真机路径）: **chapter_title 必带**——漏了前端标题屏
            # 就兜底成"羁绊剧情"（2026-09-11 用户报障）; 场景已就绪 → 一起带上
            # （前端立即上屏, 不再黑屏等轮询）
            return {"accepted": True, "busy": False, "resumed": True,
                    "chapter_title": _enter_title(state, char_id, session_id),
                    **_ready_scene_payload(state, char_id)}
    elif state.vn is not None or state.demo is not None:
        # 计时埋点（§6.1）: 内存态续玩（resumed）——即时可用
        logger.info("bond_click resumed %s/%s busy=%s",
                    char_id, session_id, "y" if state.busy else "n")
        if state.demo is None:
            _draft_save(state, char_id, session_id)    # 草稿旁路保持新鲜（#28b）
        # chapter_title 必带（2026-09-09: resumed/adopt 就绪同样展示章节标题屏）;
        # 场景就绪则带上（重进/续玩立即有画面）
        return {"accepted": True, "busy": state.busy, "resumed": True,
                "chapter_title": _enter_title(state, char_id, session_id),
                **_ready_scene_payload(state, char_id)}
    if state.busy:
        # 生成在途（P1: busy = 正在生成——让前端进入轮询, 不再报错）
        logger.info("bond_click busy_wait %s/%s", char_id, session_id)
        return {"accepted": True, "busy": True, "resumed": False,
                "chapter_title": _enter_title(state, char_id, session_id)}

    # ── 中断接入（2026-09-07）: 无内存态 + 有内容的未完成段 → 回放前缀 ──
    # （"从头开始播放已有半截剧情, 后续 LLM 后补"; staged 预热 = 新触发轮,
    # 不进回放——走下方现场构造续在押段或新段）
    if not staged:
        replay = _interrupted_replay_queue(char_id, session_id)
        if replay is not None:
            replay_q, keep_enter = replay
            # 2026-09-17（B0）: 原「定向废弃：保留被回放段、压掉其余 open」
            # **不再需要** —— B0 的不变量保证真源里**最多只有一个未闭合段**,
            # 而被回放的那个就是它。故这里无操作（旧数据的多 open 由
            # `_interrupted_replay_queue` 的空壳跳过 + 收尾逻辑各自处理）。
            logger.info("bond_click replay %s/%s scenes=%d from=%d",
                        char_id, session_id, len(replay_q), keep_enter)
            return _start_replay(state, replay_q, char_id, session_id)

    # 现场建引擎段（双检锁, 2026-09-08 自查加固）: chat worker 的 staged 预热
    # 与前端直进点击可能并发进入本段——不加锁会双建/换 vn（首场标注对象与
    # 状态分叉 → ver 恒 0 / gate 恒 true / 表情整板 nomal 的一类根因）。
    with state._lock:
        if state.vn is not None or state.demo is not None:
            # 并发下另一路已先初始化 → 放弃本次, 按现状返回（busy 由前端轮询）
            logger.info("bond_click concurrent init skip %s/%s busy=%s",
                        char_id, session_id, "y" if state.busy else "n")
            return {"accepted": True, "busy": state.busy,
                    "resumed": state.vn is not None}

        engine = chat._engine(char_id)
        char = engine.current_character
        if char is None:
            return {"accepted": False, "error": "会话未打开"}
        title = _trigger_title(engine) or _title_from_events(
            char_id, session_id, _flow_store(state))

        # brain 注入（DESIGN_BRAIN.md, wiki_v2 2026-09-02 切换）: 世界线 wiki 第一人称——
        # VN 中角色记得前面的事（出厂基座 0 LLM 确保; 失败静默零注入）
        brain_segment = load_brain_segment(
            _store(), char.character_id, char.display_name,
            characters_root=engine.char_loader.root)

        vn = BondStoryEngine(
            engine.char_loader.root, engine.llm,
            director=_build_director(char), brain_segment=brain_segment)
        vn.start_session(char.character_id)
        # 统一上下文窗口（2026-09-05, DESIGN_CONTEXT_WINDOW）: 从事件流灌最近叙事进
        # vn._history——首场带着触发前的 MMT 对话（断桥修复）; 事件流已是终态
        # （裁决时落库 + 门控保证标注就绪）; 与引擎自增历史同构, 滑动无缝
        try:
            _evs = exclude_abandoned(_flow_store(state).events(char_id))
            _win = window_messages(_evs)
            if _win:
                vn._history = _win
        except Exception:                            # noqa: BLE001 — 灌窗失败不阻断
            pass

        state.vn = vn
        state.chapter_title = title
    # 渲染依赖预热（P2, EXEC_BOND_LATENCY §5#3）: MediaCatalog/特效表移出
    # 首帧 status 轮询——首次场景解析不再现构造（懒 import 破环 routers↔driver;
    # 幂等单例; 失败静默——渲染链自带降级）
    try:
        from webgui.routers.bond import warm_render
        warm_render(char.character_id)
    except Exception:                                # noqa: BLE001 — 预热失败降级
        pass
    # 事件流: vn_enter marker（单事件流; 中断恢复依赖它推导 in_vn）。
    # staged 预热不落——adopt（玩家点击）时补, 防"没点也被拉进 VN"。
    # 中断在押（无内容段续场 / 空壳段现场生成）→ 不重复落 marker（沿用同一段,
    # 防旧 bug 式 vn_enter 堆叠）
    if not staged and _pending_in_vn(char_id, session_id):
        state.vn_enter_written = True          # 事件流已有该段 vn_enter
    elif not staged:
        # 上一次是中途退出的 → 这一次是「回来」（用户 2026-09-20 裁决）:
        # 标记一次性注记, 由下一块板的 `_system_note` 消费（见那里的长注释）。
        state.quit_resume = _prev_chapter_quit(char_id, session_id,
                                               _flow_store(state))
        try:
            _flow_store(state).enter_vn(char_id, session_id, title)
            state.vn_enter_written = True
        except Exception as e:                       # noqa: BLE001 — 写失败降级不阻断 VN
            logger.warning("事件流 vn_enter 写入失败: %s", e)
    else:
        # 新章节触发轮（staged 预热）: 收尾旧的在押段。
        # 2026-09-17（B0）: **语义修正** —— 旧实现在这里打 `vn_abandon`
        # （宣告"这段**没发生过**"）。但玩家确实陪她走完了那半段 ——
        # 那是**有意义的叙事事件**（她可能失落），删掉它是素材损失。
        # 正确语义 = `vn_exit completed=False`（**发生过，但没读完**）:
        #   ① 暂存里有未闭合章 → 以 completed=False 整段提交
        #   ② 真源里还有未闭合段（旧档 / 半截 commit）→ 补一条收尾
        # 两头都做完，「真源里不留未闭合段」这条不变量恒成立。
        try:
            _fs = _flow_store(state)
            commit_staging(_fs, char_id, session_id, completed=False)
            close_open_attempts(truth_store(_fs), char_id, session_id)
        except Exception as e:                       # noqa: BLE001 — 收尾失败降级
            logger.warning("旧在押段收尾失败: %s", e)
        state.staged_seq = _last_mmt_seq(char_id, session_id, _flow_store(state))
        state.t_staged = time.monotonic()            # 计时埋点（§6.1）: 预热起点
        logger.info("bond_prewarm_start %s/%s title=%r",
                    char_id, session_id, title)

    # ── 草稿旁路: 恢复待发板队列（决策 #28b, 2026-09-10）────────────
    # 上一进程把"已生成未播放"的板落在 soul/bond_draft.json（含当前未落库板 +
    # 待发板）。这里只需恢复**后继板队列**——首板由下面的首场缓存（同内容）或
    # 正常生成给出; 中断回放场景则由**回放交棒处**（`_start_replay` / `_advance_replay`
    # 队列尽时）用 `_draft_queue` 排队接上（2026-09-12: 不再 adopt 上屏——那会顶掉
    # 刚回放的那一场, 或在进场时就丢掉后继板）。
    if not staged and state.demo is None and state.scene_obj is None \
            and state.vn is not None \
            and _last_bond_seq(char_id, session_id, _flow_store(state)) == 0:
        # 注: 已有已落库板（将被回放）时**不在此恢复**——那一路由回放交棒处
        # `_draft_queue` 统一接（避免队列被两处设置/历史重复注入）
        rest = _draft_pending(char_id, session_id, _flow_store(state))
        if rest:
            state.vn._pending_boards = [BondScene.from_dict(b) for b in rest]
            logger.info("bond_draft_q %s/%s boards=%d", char_id, session_id, len(rest))

    # ── 跨重启预热缓存命中（2026-09-09）────────────────────────
    # 首场曾生成但未裁决/未 adopt 即中断（进程重启, 内存 staged 丢失）→
    # 磁盘旁路缓存（soul/prewarm.json, 非真源——LLM 不读, 裁决才落库）直接
    # 作为首场落地, 0 LLM。并发双开在 573 锁块被 skip（vn 已建）→ 本段单路。
    if not staged and state.demo is None and state.scene_obj is None:
        store = _flow_store(state)
        cache = _prewarm_cache_load(char_id, session_id, store)
        if cache is not None:
            scene_c, input_c, title_c = cache
            _prewarm_cache_delete(char_id, store)   # 命中即消费（旧首场不残留）
            # 2026-09-09 修复（真机 prob2: 命中后"继续"反复重新开场——事件流
            # seq15 第二场与首场近同义）: 缓存首场未经过 send_vn_scene → 引擎
            # 历史/_last_payload 缺它 → record_picked 落空、后续生成无剧情上下文
            # → 每场重编开场。注入引擎状态使后续链路与正常生成完全等价:
            # 历史尾部同形（user=缓存 input + assistant=叙事渲染——AI 视角含
            # 首场内容）; _last_payload 供 record_picked/fork 候选回录基准
            try:
                vn_payload = scene_c.to_dict()
                hist_txt = render_bond_scene_text(vn_payload)
                state.vn._history.append(
                    {"role": "user", "content": input_c or ""})
                state.vn._history.append(
                    {"role": "assistant",
                     "content": hist_txt or json.dumps(
                         vn_payload, ensure_ascii=False,
                         separators=(",", ":"))})
                state.vn._last_payload = vn_payload
            except Exception as e:                   # noqa: BLE001 — 注入失败降级
                logger.warning("缓存命中引擎注入失败（后续生成可能重开）: %s", e)
            state.round += 1
            _scene_landed(state, scene_c, char_id, session_id, input_c,
                          t0=time.monotonic(), save_cache=False, source="prewarm")
            logger.info("bond_cache_hit %s/%s title=%r",
                        char_id, session_id, title_c or title)
            return {"accepted": True, "busy": False, "resumed": True,
                    "chapter_title": title_c or title or "羁绊剧情",
                    **_ready_scene_payload(state, char_id)}

    seed = (f"（旁白）本章：{title}——从刚才的对话与契机自然展开。"
            if title else "（旁白）故事开始了……")
    _generate(state, char_id, session_id, seed)
    # 计时埋点（§6.1）: 触发轮结束→点击时开始现场生成（无预热/续场路径）
    logger.info("bond_click %s %s/%s title=%r",
                "prewarm" if staged else "fresh",
                char_id, session_id, title)
    # reason 随响应返回——前端进场景等待期显示"章节标题卡"（掩盖首场生成缓冲）
    return {"accepted": True, "busy": True, "resumed": False,
            "chapter_title": title}


def bond_start_demo(char_id: str, session_id: str) -> dict:
    """演示模式: 预设剧本驱动（DEMO_SCRIPT, 不调 LLM）——前端 VN 体验/联调用。

    状态机照走（start/turn/status/finish 同链路）: 事件流落库、wrapup 用预设
    收尾话、跳过 digest。幂等同真实路径; 已完结（completed）→ 重置重玩。
    """
    state = _state(char_id, session_id)
    if state.completed and (state.vn is not None or state.demo is not None):
        # 重玩: 清状态重来（事件流追加新剧情——旧剧情已 session_end, 语义隔离）
        _bonds.pop((char_id, session_id), None)
        state = _state(char_id, session_id)
    if state.vn is not None or state.demo is not None:
        return {"accepted": True, "busy": state.busy, "resumed": True}
    if state.busy:
        return {"accepted": False, "busy": True, "error": "正在生成首场"}

    state.demo = list(DEMO_SCRIPT)         # 副本（pop 消费不污染常量）
    state.chapter_title = "（演示）"
    try:
        _flow_store(state).enter_vn(char_id, session_id, state.chapter_title)
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断
        logger.warning("事件流 vn_enter 写入失败: %s", e)
    _generate(state, char_id, session_id, "（演示开始）")
    return {"accepted": True, "busy": True, "resumed": False}


def bond_turn(char_id: str, session_id: str, text: str) -> dict:
    """玩家裁决（选项文本 / 自由输入 / 点击继续）→ 补录上一场事件 → 衔接下一场。

    预生成消费（Storyloom bridge 式）: 纯叙事场（无 choices）点"（继续）"时,
    下一场已提前生成（state.pregen）→ 直接衔接, 零等待; 预生成失败降级为
    正常生成路径（不阻断剧情）。
    """
    state = _state(char_id, session_id)
    if state.vn is None and state.demo is None:
        return {"accepted": False, "error": "剧情未开始"}

    # ── 回放推进（中断接入, 2026-09-07）: 纯本地逐场, 0 LLM ──────
    # 在 busy 守卫之前——回放期间续写预生成在跑（busy=True）也不阻塞推进;
    # 队列尽（[]）→ 交棒下方常规 live 路径（promotion/生成）
    if state.replay_scenes is not None:
        if state.replay_scenes:
            nxt = state.replay_scenes.pop(0)
            state.scene_obj = BondScene.from_dict(nxt)
            state.scene_obj._place_done = True    # 回放: 视觉键定格, 不占 lane
            # 纪念板 → 进纪念态（同 `_start_replay`: 重放纪念段时立绘隐藏/背景清空）
            state.vn._in_memorial = bool(state.scene_obj.memorial)
            _ensure_memorial_img(state, char_id, session_id)   # 回放: 恢复档案图
            state.scene = state.scene_obj.to_dict()
            state.round += 1
            state.scene_state = BoardLifecycle.COMMITTED    # 正文来自事件流——回放不重复落
            _log_board_deliver(state, state.scene_obj, char_id, session_id, "replay")
            if not state.replay_scenes:
                # 最后一场入屏 → 优先接续**草稿旁路**（已生成未播放, 0 LLM 续播,
                # 决策 #28b）: **排队**进待发队列（不 adopt 上屏——那会顶掉刚回放的
                # 这一场, 2026-09-12 修正）; 没草稿/过期 → 续写预生成（读屏期间完成）
                if not _draft_queue(state, char_id, session_id):
                    _pregenerate(state, char_id, session_id)
            # 场景一起回（2026-09-11）: 回放是纯本地 0 LLM, 前端拿到即上屏——
            # 省掉一轮 status 轮询（700ms 起）也不再黑屏
            return {"accepted": True, "busy": False, "replay": True,
                    **_ready_scene_payload(state, char_id)}
        state.replay_scenes = None             # 交棒: 走下方常规逻辑

    if state.busy:
        _note_reject(state, "busy:生成中", char_id, session_id)
        return {"accepted": False, "busy": True, "error": "剧情生成中"}
    if state.completed:
        return {"accepted": False, "completed": True, "error": "剧情已结束"}
    text = (text or "").strip()
    if not text:
        return {"accepted": False, "error": "输入不能为空"}

    # 推进门控（2026-09-02; P3b-1 双路齐）: 当前场景（含分支）emotion + place
    # 未就绪 → 不让推进（情绪不到位/换场锚点未定不点下一轮——标注 2~5s,
    # 前端 busy 轮询自动放行; 同时保证落库场景视觉键完整: append-only 不可补）
    gate = _scene_ready_or_busy(state)
    if gate is not None:
        _note_reject(state, f"gate:{'emotion' if not _scene_emotions_ready(state) else 'place'}",
                     char_id, session_id)
        return gate

    if text == "（继续）" and state.pregen_scene is not None:
        # 预生成消费门（2026-09-08 实机修复）: 预生成场景自身的标注（emotion/place）
        # 未就绪 → 不提升、返回 busy（前端轮询重试）——否则场景被消费后
        # pregen_obj=None, 标注 worker 的身份检查把它当"已替换"丢弃 → 整板无
        # 表情且无补切通道（emo_version 不再涨）→ 表情卡 nomal。
        # 2026-09-11: 加**超时兜底**（见 _watchdog ③）——否则这道门一旦标注没跑
        # 成就是"继续键永久无响应"（真机 110s 事故的可能形态之一）。
        if not _scene_obj_visual_ready(state, state.pregen_obj):
            _note_reject(state, "pregen:标注中", char_id, session_id)
            return {"accepted": False, "busy": True,
                    "error": "预生成标注中, 稍后自动继续"}
        state.pregen_gate_since = 0.0
        # 预生成就绪 → 补录当前场 → 提升预生成场景为当前场 → 链式预生成
        _log_scene(state, char_id, session_id, picked=None)
        state.scene_obj = state.pregen_obj
        state.scene = state.pregen_scene
        state.scene_input = state.pregen_input
        state.scene_state = BoardLifecycle.DELIVERED
        state.pregen_obj = None
        state.pregen_scene = None
        state.pregen_input = ""
        state.round += 1
        if state.scene_obj is not None and state.scene_obj.is_end:
            # completed 置位只可能来自**场景 is_end**（自然 story_end / demo 收尾
            # ——digest/完整收尾话的唯一许可; 异常/中止永不置, 2026-09-09 语义）
            state.completed = True
        # 台账（2026-09-11）: 这一板来自预生成暂存（0 LLM 领出）
        _log_board_deliver(state, state.scene_obj, char_id, session_id, "queue")
        _log_scene_meta(state, char_id, session_id, state.scene_obj)
        _draft_save(state, char_id, session_id)    # 草稿旁路刷新（#28b）
        # 链式备料（N2a 缺口补上, N2b）: 新场景未收尾——纯叙事 → 单路预生成;
        # 带 choices → 候选 spawn（读板期预跑, 与主线生成同款）
        # 记录流 v2（P0-7c 修正）: 待发板队列让"下一板"常常是 0 LLM, 但**块耗尽后
        # 仍需桥**（否则下一拍要玩家干等一次完整生成）——所以:
        #   无槽板（纯叙事/反应板）→ 照常预生成（待发有货就领, 没货就真生成）
        #   有槽板 → 不预生成（裁决要先落; 桥由"裁决后立即预生成"承担, 见裁决段）
        #   同时不再 fork 候选（v2 里后继板已在手, fork 无意义）
        if state.scene_obj is not None and not state.scene_obj.is_end:
            if state.scene_obj.records:
                if not state.scene_obj.choices:
                    _pregenerate(state, char_id, session_id)
            elif state.scene_obj.choices:
                _spawn_candidates(state, state.scene_obj, char_id, session_id)
            else:
                _pregenerate(state, char_id, session_id)
        _clear_rejects(state, char_id, session_id)
        # 新场景一起回（2026-09-11）: 预生成已在手, 前端拿到即上屏（省一轮轮询）
        return {"accepted": True, "busy": state.busy, "pregen": True,
                **_ready_scene_payload(state, char_id)}

    # 分支消费（板块契约 2026-08-30）: 选项带同响应分支 → 立即展示分支内容
    # （零等待——分支已在场景响应里, 无需再调 LLM; 返回 scene 由前端直接渲染）
    # + 分支播放时预生成下一板块（输入固定"（继续）"）——读完点继续零等待
    if (state.scene_obj is not None and state.scene_obj.branches
            and text in state.scene_obj.branches):
        branch = state.scene_obj.branches[text]
        _log_scene(state, char_id, session_id, picked=text)   # 场景（含 branches）落库
        # 方案A-A1 选项回录（DESIGN_PROMPTKIT §5, Phase 4）: 分支消费 = 裁决完成,
        # 立即写回引擎历史尾部（“（选择了: X）”）——后续预生成/正常续写的输入恒为
        # “（继续）”, 不回录则 AI 永远看不到玩家选了哪项（live 与 resume 分叉洞）。
        # 必须在 _pregenerate 之前: 预生成请求的历史要含本次裁决。
        # ── SceneStream P1.5（N2b）: 候选支命中（DESIGN_CHOICE_PREGEN §0）──
        # 若该选项的候选已就绪 → 切主引擎为候选 fork（历史已内嵌裁决行 +
        # “（继续）”一轮——**不再 record_picked, 防重复**）+ 下一板经 pregen
        # 通道暂存（点继续零等待消费）; 未就绪/失败 → 走老路（record_picked +
        # 分支播放期单路预生成）。任一裁决路径都在此处清池（未选候选作废 GC）。
        cand = next((c for c in state.choice_candidates
                     if c.picked == text and c.status == "ready"), None)
        if cand is None and state.choice_candidates:
            # generating → 给短窗口（候选通常已在跑, 白等可惜）; 超时走老路
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                with state._lock:
                    c = next((c for c in state.choice_candidates
                              if c.picked == text), None)
                    if c is not None and c.status in ("ready", "failed"):
                        break
                time.sleep(0.05)
            if c is not None and c.status == "ready":
                cand = c
        if cand is not None:
            state.vn = cand.engine               # 切主引擎 = 候选世界线（fork 历史自洽）
            _discard_candidates(state)           # 未选候选作废 GC
            nxt = cand.scene_obj
            # 候选同步标注已完成（annotate=True）; place 判定已随同步 fill 完成——
            # 置标记 → pregen 消费门放行（§7 双路语义, 不占 lane）
            nxt._place_done = True
            state.pregen_obj = nxt
            state.pregen_scene = nxt.to_dict()
            state.pregen_input = "（继续）"
            logger.info("bond_cand hit %s/%s picked=%s", char_id, session_id, text)
        else:
            _discard_candidates(state)           # 无命中候选 → 老路 + 池作废
            if state.vn is not None:
                state.vn.record_picked(text)
        state.scene_obj = BondScene(
            paragraphs=branch,
            background=state.scene_obj.background,
            place=state.scene_obj.place,
        )
        state.scene = state.scene_obj.to_dict()
        state.scene_state = BoardLifecycle.COMMITTED   # 分支属场景一部分（已随场景落库）
        _log_board_deliver(state, state.scene_obj, char_id, session_id, "branch")
        # 分支反应段 = 同板延续（地点不重新判定, 主场景的 place 判定已随门控完成）;
        # 置就绪标记 → 不占 place lane（§7 gate 双路语义）
        state.scene_obj._place_done = True
        # 分支段落可能是骨架（branches 未标注）→ 入队异步标注（与主场景同队列）
        deps.enqueue_annotate(state, state.scene_obj)
        # 2026-09-02 修复: 分支渲染后前端不轮询 status（turn 直接返回 scene）——
        # 若返回未标注骨架, 立绘 default 且标注完成无补切通道; 同步短等标注
        # （修复后标注 ~1-3s, 上限 8s 兜底——标注层失败也有 _fallback_fill 保证就绪）
        _wait_annotated(state, timeout=8.0)
        state.scene = state.scene_obj.to_dict()
        # 候选命中时下一板已就绪（pregen 通道）→ 不再单路预生成（防双份）;
        # 老路则分支播放时照旧预生成
        if cand is None:
            _pregenerate(state, char_id, session_id)
        _clear_rejects(state, char_id, session_id)
        return {"accepted": True, "busy": state.busy, "branch": True,
                "scene": state.scene, "candidate": cand is not None}

    # 记录流 v2 裁决（P0-7）: 选中候选 = 老师那句话 —— **只记不念**。
    # 角色的反应在**下一板**（引擎待发队列, 点继续 0 LLM 领出）——不在这里生成。
    # **屏幕语义定稿（2026-09-12 用户核对 BA 后明确）**: 玩家的话语**永远只体现为
    # 选项**——裁决后正文停在"上一句角色台词/旁白", 名字牌不动, 选项消失即继续;
    # 绝不把这句当正文播出来（真机报障:"睦月/便利屋68 + 你还打算对我怎么恶作剧？"
    # 读起来就是角色说了玩家的话）。所以这里**不返回 scene**（返回就会 renderScene
    # → 重播正文, #32 踩过）, 只回 `picked` 让前端清选项。
    if (state.scene_obj is not None and state.scene_obj.records
            and text in (state.scene_obj.choices or [])
            and not (state.scene or {}).get("picked")):
        _log_scene(state, char_id, session_id, picked=text)
        if state.vn is not None:
            state.vn.record_picked(text)          # 历史尾部物化（live == 回放/续写）
        _discard_candidates(state)                # v2 不 fork（内容已在待发队列）
        # 展示视图: 保留板正文（屏上就是它）, 只**去掉选项**并标记已裁决——
        # 指纹不含 choices（bond.js sceneKey）, 故轮询不会把它当成"新场景"重播。
        #
        # 2026-09-13（审计 B13 复核）: 这里**只清展示视图** `state.scene`。
        # 审计原判"落库 payload 也会变空"是**误报**——`_log_scene` 就在上面执行,
        # 它取的是 `scene_obj.to_dict()` 的当时快照, 所以事件流一直是对的
        # （实测 payload `choices=['选A','选B']`）。原先这里还多写了一句
        # `scene_obj.choices = []`, 那是**死代码**（落库已过、之后无人再读它）,
        # 只是平白多一个可变状态 → 删掉。重复裁决由上面守卫的
        # `not (state.scene or {}).get("picked")` 拦（展示视图已标 picked）。
        scene = dict(state.scene or {})
        scene["choices"] = []
        scene["picked"] = text
        state.scene = scene
        state.scene_state = BoardLifecycle.COMMITTED   # 本板已随裁决落库
        # 裁决后立刻备料（P0-7c 修正）: 这里必须先 record_picked（上面已做）——
        # 预生成请求的历史要含物化裁决行。待发有货 → 0 LLM 领出反应板; 没货 →
        # 真生成下一拍（玩家读上一句的时间即缓冲桥）。
        _draft_save(state, char_id, session_id)   # 草稿旁路刷新（#28b）
        _pregenerate(state, char_id, session_id)
        _clear_rejects(state, char_id, session_id)
        return {"accepted": True, "busy": state.busy, "branch": True,
                "picked": text, "candidate": False}

    # append-only 事件流: 当前展示场景在玩家裁决时落库（带 picked）;
    # 纯叙事场的"（继续）"是推进指令不是内容裁决 → picked=None（与预生成消费一致）
    _log_scene(state, char_id, session_id,
               picked=None if text == "（继续）" else text)
    _clear_rejects(state, char_id, session_id)
    _generate(state, char_id, session_id, text)
    return {"accepted": True, "busy": True}


def bond_status(char_id: str, session_id: str) -> dict:
    """轮询: 生成状态 + 最新场景（前端按 round 去重）+ 终结标记 + 名字牌信息
    + emo_version（异步标注补标版本——前端感知后补切已显示段落的立绘表情）
    + memorial（纪念模式标记 + 立绘 URL——前端进纪念淡入图背景, 退出淡出）。
    + gate_busy（2026-09-07）: 推进门控视角——当前场景 emotion+place 未就绪
    （state.busy 之外的另一类"再等等"）; 前端忙等改轮询 status 而非狂发 turn。"""
    state = _state(char_id, session_id)
    # 看门狗（2026-09-11）: 前端在轮询 status —— 借这次调用检查"忙态/视觉门/
    # 预生成消费门"是否卡死, 卡死就兜底放行（否则点击永久无响应, 用户只能重启）
    _watchdog(state, char_id, session_id)
    # lane 自愈（2026-09-08）: worker 意外死亡且队列有积压 → 看门狗立即重启
    # （_ensure_lane 只在入队时触发——本函数覆盖"死后无人入队"的饥饿窗口）
    if state.vn is not None and state.demo is None:
        for started_attr, thread_attr, q_attr, fn, lane in (
                ("_anno_started", "_anno_thread", "_anno_queue", _anno_worker, "emo"),
                ("_place_started", "_place_thread", "_place_queue", _place_worker,
                 "place")):
            q = getattr(state, q_attr)
            th = getattr(state, thread_attr)
            if (getattr(state, started_attr)
                    and (th is None or not th.is_alive())
                    and q is not None and q.qsize() > 0):
                logger.warning("bond_anno lane %s 死亡重启(status 自愈)", lane)
                _ensure_lane(state, started_attr=started_attr,
                             thread_attr=thread_attr, worker_fn=fn, lane=lane)
    role = _role_info(char_id)
    # 卡在哪（2026-09-11 第二次真机"已等待 110s"复盘）: 上一轮只给了 busy/gate_busy
    # 两个布尔, 事故时**无法判断是哪一路卡住**（旧日志里也没有）。这里把两路拆开 +
    # 忙态持续时长 + 预生成门一起给出——一次 status 快照即可定位:
    #   gate_emo=False → emotion 标注没回来（lane 死/结果被丢弃）;
    #   gate_place=False → place 判定没回来;
    #   busy_ms 很大而日志无生成 → 忙态卡死（线程丢失; 由看门狗复位）;
    #   pregen_wait=True → "继续"被预生成消费门挡住。
    gate_emo = _scene_emotions_ready(state)
    gate_place = _scene_places_ready(state)
    pregen = getattr(state, "pregen_obj", None)
    return {
        "busy": state.busy,
        "gate_busy": not (gate_emo and gate_place),
        "gate_emo": gate_emo,
        "gate_place": gate_place,
        "busy_ms": _ms_since(state.busy_since) if state.busy_since else 0,
        "pregen_wait": bool(pregen is not None
                            and not _scene_obj_visual_ready(state, pregen)),
        "round": state.round,
        "scene": state.scene,
        "error": state.error,
        "completed": state.completed,
        # 板级生命周期（节点 2″）: delivered（已上屏未提交）/ committed（已进事件流）——
        # 诊断用; "预生成待消费"由 pregen_wait/场景自身能否被提升体现
        "scene_state": state.scene_state.value,
        "pregen_ready": bool(pregen is not None),
        "name": role["name"],
        "club": role["club"],
        # 章节标题（2026-09-11）: 名字牌照常, 标题也随 status 一路带着——
        # 前端重进/刷新/回放都能拿到正确章节名（不再落到"羁绊剧情"兜底）
        "chapter_title": state.chapter_title,
        "emo_version": state.emo_version,
        # lane 诊断（2026-09-08, 前端 tick 直读）: 存活/积压/版本/场景对象——
        # 判定"标注没跑 / worker 死了 / 场景对象分叉"一线定位
        "anno": {
            "emo_alive": bool(state._anno_thread and state._anno_thread.is_alive()),
            "place_alive": bool(state._place_thread and state._place_thread.is_alive()),
            "emo_pending": state._anno_queue.qsize() if state._anno_queue else 0,
            "place_pending": state._place_queue.qsize() if state._place_queue else 0,
            "scene_id": id(state.scene_obj) if state.scene_obj else None,
        },
        # 纪念立绘（方案 A）: in_memorial = 纪念模式中（前端保持图背景）;
        # memorial_img = 图 URL（None = 未就绪/失败 → 纯文字降级）;
        # memorial_img_busy = 生图中（防重/调试可见）
        "in_memorial": bool(state.vn is not None and state.vn.in_memorial),
        "memorial_img": state.memorial_img or None,
        "memorial_img_busy": state.memorial_img_busy,
        # 候选支诊断（DESIGN_CHOICE_PREGEN, N2c）: 只暴露 {picked,status}——
        # 生成中/就绪/失败一目了然, 不泄场景数据
        "candidates": [
            {"picked": c.picked, "status": c.status}
            for c in state.choice_candidates
        ],
    }


def bond_finish(char_id: str, session_id: str) -> dict:
    """剧情终结收尾: 补录最后场景 + vn_exit + session_end + wrapup + digest。"""
    state = _state(char_id, session_id)
    if state.vn is None and state.demo is None:
        return {"completed": False, "error": "剧情未开始"}
    if state.busy:
        return {"completed": False, "busy": True, "error": "剧情生成中"}
    if state.finished:
        # 幂等（2026-09-09 审计: 01:20-01:21 同一进程 6s 内两次 finish →
        # 重复 vn_exit + wrapup + 兜底话; 前端有 finished 防重, 后端再兜一层）。
        # 留痕 warning → diag 落盘, "谁在调 finish"从此可查
        logger.warning("bond_finish 幂等跳过（重复调用） %s/%s",
                       char_id, session_id)
        return {"completed": True, "already": True}
    logger.info("bond_finish 执行 %s/%s completed=%s（入口留痕）",
                char_id, session_id, state.completed)
    _prewarm_cache_delete(char_id, _flow_store(state))   # 收尾: 旧首场缓存一并失效
    # 收尾: 未播放的预生成板/候选支/草稿一并作废（节点 2″: 走**唯一丢弃入口**——
    # 后台候选若仍在生成即孤儿, 停止烧 token; 未选支零落库由 `_log_scene` 边界
    # 结构保证：候选从不触碰事件流）
    _discard_boards(state, char_id, reason="finish")

    # 收尾前等最后场景标注就绪（2026-09-02 emotion; P3b-1 双路齐）——append-only
    # 落库缺 emotion/place 不可补; 标注 worker 独立线程, 短等（失败兜底也回填/
    # 置完成标记 → 必达; 超时宁缺勿错）
    if not _scene_visual_ready(state):
        deadline = time.time() + 8.0
        while time.time() < deadline and not _scene_visual_ready(state):
            time.sleep(0.05)
        if not _scene_visual_ready(state):
            logger.warning("bond_finish 等待标注超时, 场景可能缺 emotion/place: %s/%s",
                           char_id, session_id)

    # 最后场景（is_end / closing）: 玩家无裁决 → picked=None
    _log_scene(state, char_id, session_id, picked=None)
    # 2026-09-13（审计 B5）: 章在纪念窗口内结束（玩家读完纪念板就收尾）时,
    # "下一板落地"那条补 exit 的路径永不发生 → 必须在这里闭合, 否则流里留下
    # 未闭合的 memorial_enter, 下一章首板会被判成"纪念窗口内"而整块跳过标注。
    # 放在 vn_exit/session_end **之前**: `_memorial_open_in_events` 只认
    # exit/session_end 来闭合, 顺序上先写 exit 更直白（session_end 也会闭合,
    # 但那是"会话结束"而非"纪念结束"的语义）。`force=True`: 收尾时引擎
    # `vn.in_memorial` 可能仍为 True（玩家一板都没推进过, 没有"新块解析成功"
    # 来复位它）, 而章已经结束——必须强闭合, 否则窗口跨章悬空。
    _close_memorial_window(state, char_id, session_id, force=True)
    try:
        # vn_exit 带剧情完成标志（2026-09-01）: completed = 剧情真正走完
        # （story_end 自然收尾）; False = 玩家中途退出——收尾链据此分支
        # （中断不脑补收尾话 + 不 digest——记忆只反映完整剧情段）
        # 2026-09-17（B0/B-1 整章暂存）: `vn_exit` 改走**章内写入口**（暂存）,
        # 紧接 `commit_staging` 把暂存整段搬进真源 —— 于是真源里
        # `vn_enter…vn_exit` 一次到位, 中间**不留未闭合窗口**。
        # ⚠️ `commit_staging` 的收尾步骤**只在暂存自带 `vn_enter` 时才跑**:
        #    现阶段（B-2 之前）暂存通常只装这条 `vn_exit`,
        #    而真源里那个未闭合段**就是本章本身** —— 收尾它会把本章误判成"没读完"。
        _stage_store(state).append_marker(char_id, session_id, M_VN_EXIT,
                                          {"completed": state.completed})
        commit_staging(_flow_store(state), char_id, session_id,
                       completed=state.completed)
        _store().finish(char_id, session_id, ended=True)
        # 2026-09-02 用户拍板: 完整剧情结束（vn_exit completed）→ 距上次剧情
        # 计数清零（触发门槛 + 剧情后冷却一体; 中途退出不清——只有完整演过
        # 才值得冷却, 见 engine.bond_completed）
        if state.completed:
            try:
                chat._engine(char_id).bond_completed()
            except Exception as e:               # noqa: BLE001 — 清零失败降级
                logger.warning("bond_gap 清零失败: %s", e)
    except Exception as e:                           # noqa: BLE001 — 收尾写失败降级
        logger.warning("事件流收尾失败: %s", e)
    # 清任务状态（bond_story 标记）——否则 events_after 一直返回 True,
    # 前端 VN 结束后重启轮询会再次误入剧情视图（wrapup 的 mmt 任务随后覆盖）
    chat._tasks.pop((char_id, session_id), None)

    # wrapup 收尾（agent_turn 收尾话 → mmt 事件, 前端轮询拉到）→ 仅在剧情完整
    # 结束时 digest（中断剧情不提炼——wiki 只反映完整剧情段, 防记忆污染）
    # 2026-09-11 真机修复: wrapup 跑在自己的线程里, 不走 chat 的 `_worker` →
    # 前端 VN 退出后第一次轮询就看见 `running: false` → **停止轮询** → 收尾气泡
    # 要等切页/重进才被 `since=0` 全量拉出来。这里先占住任务位（task_begin）,
    # 线程结束再放（task_end）——前端因此保持轮询并显示"对方正在输入…"。
    title = state.chapter_title
    chat.task_begin(char_id, session_id)
    threading.Thread(target=_wrapup,
                     args=(char_id, session_id, title, state.completed),
                     daemon=True).start()
    state.finished = True               # 幂等标记（本内存态生命周期内只收尾一次）
    return {"completed": True}


def _wrapup(char_id: str, session_id: str, title: str, completed: bool) -> None:
    """收尾话线程入口（2026-09-11）: 占住 MMT 任务位 → 干活 → 必放。

    占位的作用: 前端 VN 退出后 `pollLoop` 依据 `running` 决定要不要继续轮询;
    wrapup 不走 chat 的 `_worker`（自己起线程）, 不占位的话前端第一轮就以为
    "没事了"而停轮询 → 收尾气泡要切页才看得到（真机报障）。
    """
    try:
        chat.task_begin(char_id, session_id)
        _wrapup_inner(char_id, session_id, title, completed)
    except Exception as e:                           # noqa: BLE001 — 收尾异常不致命
        logger.warning("羁绊收尾线程异常: %s", e)
    finally:
        chat.task_end(char_id, session_id)


def _wrapup_inner(char_id: str, session_id: str, title: str, completed: bool) -> None:
    """剧情收尾后的手机收尾: 自动触发一轮, AI 就这段剧情回几段话 + digest。

    收尾话 = agent_turn（system_note 注入, record_input=False——不落假 player 事件,
    只落 assistant 回复）; 前端轮询 events_after 自然拉到收尾气泡。
    2026-09-05: reason 退役——收尾前给引擎灌统一窗口（事件流含刚结束的 bond
    场景叙事, agent_turn 的 AI 知道这段剧情讲了什么）; title 仅兜底引用。
    completed=True（剧情 story_end 自然结束）: 话术按"完整剧情"收尾 +
    async_digest（提炼 + 好感结算——digest 唯一触发点）。
    completed=False（玩家中途退出）: 话术明确"剧情只进行到一半"（防 LLM 脑补
    未发生的剧情结果）+ **不 digest**（记忆只反映完整剧情段——中断不提炼,
    未消化的 mmt 留到下次完整剧情段一起消化, 增量幂等）。
    演示模式（state.demo）: 预设收尾话落 mmt 事件, 跳过 agent_turn 和 digest（不调 LLM）。
    """
    state = _state(char_id, session_id)
    # daemon 线程长生命周期——**store 快照**（2026-09-09 审计: wrapup 在 finish
    # 后异步执行, 期间全局 deps.store() 可能已被替换（测试 cleanup/未来多线）,
    # 迟到的兜底写入曾落错 store（真实 data 被测试污染）; 线程内一律用快照,
    # 与"谁调起它"时的归属一致。
    # 2026-09-13 修正（审计 B18）: 取的是**流程绑定的** store（`_flow_store`）,
    # 而不是全局 `_store()`——原实现与本 docstring 自相矛盾: 决策 #31 已经把
    # 长流程的一切读写钉到 `BondState.store`, 这里漏了一处, 多世界/多开时
    # 迟到的收尾话仍可能落错世界线。
    store = _flow_store(state)
    if state.demo is not None:
        try:
            store.append_event(char_id, session_id, make_event(
                "mmt", "mmt_chat",
                {"player": "", "reply": "（演示收尾）今晚的剧情，我会一直记在心里……"}))
        except Exception as e:                       # noqa: BLE001
            logger.warning("演示收尾话写入失败: %s", e)
        return
    engine = chat._engine(char_id)
    char = engine.current_character
    if char is None:
        if completed:
            engine.async_digest()
        return
    # 统一上下文窗口: bond 期间 momotalk 引擎未跑——收尾前把事件流（含刚结束的
    # bond 场景叙事）灌进 _history, 收尾话自然接续剧情（起因便签不再需要）
    try:
        _evs = exclude_abandoned(store.events(char_id))
        _win = window_messages(_evs)
        if _win:
            engine._history = _win
    except Exception:                                # noqa: BLE001 — 灌窗失败不阻断
        pass
    title_suffix = f"（本章: {title}）" if title else ""
    if completed:
        note = (
            "（系统）羁绊剧情刚刚结束，你们回到了 MomoTalk 手机聊天。"
            f"请以{char.display_name}的身份，就刚才这段羁绊剧情{title_suffix}，"
            "在手机上回复老师几句话作为收尾——自然、简短、像真实的手机消息。"
            "只使用 mmt_chat 动作，不要再次触发羁绊剧情。"
        )
    else:
        # 中途退出: 剧情只进行到一半——明示中断, 防止 LLM 依据触发起因
        # 脑补"剧情结果"（实测: 收尾话把未发生的对决总结成"玩得很开心"）
        note = (
            "（系统）羁绊剧情**只进行到一半**就中断了——老师中途离开了，"
            f"你们没有完成这段剧情{title_suffix}。"
            f"请以{char.display_name}的身份，在手机上给老师发一条简短的告别消息"
            "（如「下次再继续」）——**不要总结剧情结果、不要描述没有发生的剧情**。"
            "只使用 mmt_chat 动作，不要再次触发羁绊剧情。"
        )
    try:
        with chat._lock(char_id):
            engine.agent_turn("（自动收尾）", system_note=note, record_input=False,
                              task_kind="wrapup")
    except Exception as e:                           # noqa: BLE001 — 收尾失败不阻塞
        logger.warning("羁绊剧情收尾回复失败: %s", e)
        # 兜底收尾话（2026-08-30）: LLM 收尾失败 → 本地预设结语落库——保证
        # 结束回 MMT 时玩家一定看得到结语（之前失败时静默, "强硬回 MMT"）
        try:
            if completed:
                fallback = "（今晚的事……我会好好记住的。老师，谢谢你。）"
            else:
                fallback = "（……老师突然就走了。嗯，剧情下次再继续吧。）"
            store.append_event(char_id, session_id, make_event(
                "mmt", "mmt_chat",
                {"player": "", "reply": fallback}))
        except Exception as e2:                      # noqa: BLE001
            logger.warning("兜底收尾话写入失败: %s", e2)
    if completed:
        # digest 唯一触发点——completed 只可能来自自然 story_end（N_a 语义修正
        # 后异常/中止永不置位）; 中断（completed=False）不提炼, wiki 只反映
        # 完整剧情段
        engine.async_digest()
