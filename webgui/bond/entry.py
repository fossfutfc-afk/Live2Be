"""`webgui.bond` 的**开场与场景载荷**（○C8b, `docs/EXEC_SPLIT.md`）。

    `bond_start`        构造引擎 + 落 vn_enter + 首场 seed（路由层 POST /bond/start）
    `bond_start_demo`   演示模式（`DEMO_SCRIPT` 预设剧本, **0 LLM**——前端联调/体验）
    `_start_replay`     回放编排（中断重进 → 已记录前缀排队 → 交棒预生成）
    `_entry_already_done` 重进闸（只看事件流: 已完成的章不许再进）
    `_ready_scene_payload` / `_role_info`  **前端要的那份场景载荷**（scene+round+emo_version+name/club）

## 依赖方向（○C8b）

    entry → （state / stores / lanes / pregen / replay / memorial / watchdog）
    api   → entry（`bond_turn`/`bond_status` 借上面的载荷与角色卡）
    **entry 不 import api** —— "开场"不该知道"轮次/收尾"怎么实现。

## 纪律

· 代码从 `api.py`（C8 前是 `bond.py`）**逐字搬来**, 零行为改动;
· 包级"对外契约"那段原 `bond.py` 模块说明留在 `api.py` 的 docstring（这一层是它的门面）。
"""


from __future__ import annotations

import json
import logging
import time

from core.bond.bond_story import (
    BondScene,
    BondStoryEngine,
)
from core.director.wiring import (
    _build_director,
    _trigger_title,
)
from core.mmt.engine import load_brain_segment
from core.session.events import M_VN_EXIT
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
from infra import paths
from webgui import chat
from webgui.bond.memorial import _ensure_memorial_img, board_in_memorial
from webgui.bond.pregen import (
    _generate,
    _log_board_deliver,
    _pregenerate,
    _scene_landed,
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
    _draft_pending,
    _draft_queue,
    _draft_save,
    _flow_store,
    _last_bond_seq,
    _last_mmt_seq,
    _open_chapter_board_seq,
    _open_vn_seq,
    _prewarm_cache_delete,
    _prewarm_cache_load,
    _store,
)
from webgui.bond.util import _ms_since

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
        out["in_memorial"] = board_in_memorial(state)
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
    replayed = BondScene.from_dict(first)
    replayed._place_done = True           # 回放场景来自事件流（视觉键已定格）——不占 lane
    state.scene_obj = replayed
    vn.adopt_replayed(replayed)           # 回录基准指向它（补裁决要重渲历史尾部, 2026-09-21）
    # 回放的纪念板也进纪念态（2026-09-12）: 否则重放纪念段时立绘照常显示、背景照常亮
    # （v2 区间 = 本块内, 其后从草稿/待发队列领出的板会沿用这个标志, 直到新生成一块）
    vn._in_memorial = bool(replayed.in_memorial or replayed.memorial)
    _ensure_memorial_img(state, char_id, session_id)     # 回放: 恢复档案纪念图
    state.scene = replayed.to_dict()
    state.round = 1
    state.scene_state = BoardLifecycle.COMMITTED   # 正文来自事件流——回放不重复落
    _log_board_deliver(state, replayed, char_id, session_id, "replay")
    if not state.replay_scenes:
        # 单场（或最后一场）: 续写在读屏期间备好 → 交棒零等待。
        # 顺序（2026-09-12 修正）: **先接草稿旁路**（已生成未播放的板, 0 LLM,
        # 内容不丢, 排队不动屏上场景）→ 没有再预生成。此前这里直接 `_pregenerate`,
        # 于是"选了选项后关页面再进"会把已生成的后继板丢掉、重新生成一份
        # （实测: `bond_pregen src=gen` 紧跟 `bond_board_deliver src=replay`）。
        # ⚠️ 这板**还等着裁决**也照常预生成 —— **有意为之**（不要"修"它）:
        #    收敛链下选项只是幌子（老师的"一句话拆成两句"）, 续写与选哪句**无关**
        #    （§6.5 拍板定稿; 规则书也是这么要求 writer 的）⇒ 交棒即备料是对的,
        #    玩家读完前缀时后继板已就绪。裁决行本身照旧进历史/真源（A1 物化）。
        if not _draft_queue(state, char_id, session_id):
            _pregenerate(state, char_id, session_id)
    return {"accepted": True, "busy": state.busy, "resumed": True,
            "replay": True,
            "chapter_title": _enter_title(state, char_id, session_id),
            **_ready_scene_payload(state, char_id)}


def _close_stale_attempts(flow_store, char_id: str, session_id: str,
                          *, moved: int) -> None:
    """收尾**真源里的陈旧未闭合段**（B0 整章暂存的那一半收尾动作）。

    ⚠️ **只在 `moved == 0`（暂存为空、什么都没搬）时才收** —— 这条条件是本函数的全部要点。

    为什么（2026-09-30 修，真机 bug）:
      `commit_staging` 内部**自带**一次"有条件的收尾"（只在暂存自带 `vn_enter` 时跑，
      收的是**真源里的旧**未闭合段）。刚搬完的那一批如果带着**本章**的 `vn_enter`，
      此刻真源里唯一的未闭合段**就是这一章本身** ⇒ 这里再无条件收一次 = 把
      **玩家正在玩的那一章**判成"没读完"，补一条
      `vn_exit {completed: false, reason: "staging:superseded"}`。

    真机后果（两条，同一个假 marker 引起）:
      · `webgui/chat.py::_bond_done_map` 是**顺序配对**（trigger → 其后第一个 `vn_exit`）
        ⇒ 被这条提前关闭 ⇒ MMT 里"已完成羁绊剧情"淡行**永不出现**
      · `core/session/chapters.py::replayable_chapters` 认不出这一章 ⇒ 回忆册 **0 章**

    `moved` 由调用方传 `commit_staging` 的返回值（搬了几条）。
    """
    if moved:
        return
    try:
        close_open_attempts(truth_store(flow_store), char_id, session_id)
    except Exception as e:                       # noqa: BLE001 — 收尾失败降级
        logger.warning("真源陈旧未闭合段收尾失败: %s", e)


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
        # ⭐ **补落 `vn_enter`**（2026-09-30 修 —— 陷阱 35 的**漏网分支**）:
        #   staged 预热**不落** `vn_enter`（防"没点也被拉进 VN"）, 交给玩家点击时补 ——
        #   `adopt`(上面) / `concurrent`(下面) 两支都有这份记账, **这一支原来没有**。
        #   落到这一支的条件是"`state.vn` 还在, 但 `staged_seq` 已被消费/为 None"
        #   ⇒ adopt 分支**进不来** ⇒ **整章永远没有 `vn_enter`**:
        #   剧情演得完、`vn_exit` 也照落, 但 `replayable_chapters` 认不出这一章
        #   ⇒ **回忆册里"0 章"**（真机报障症状, 陷阱 35 原文写的正是它）。
        #   ⚠️ 三支必须**同一份记账**, 少一支就是一条静默的丢章路径。
        #   ⚠️ 写的是 `_flow_store`（= overlay）⇒ 章内落暂存, 由 `vn_exit` 那次 commit 搬进真源。
        if state.demo is None and not state.vn_enter_written:
            if _pending_in_vn(char_id, session_id):
                state.vn_enter_written = True          # 事件流已有该段 vn_enter
            else:
                try:
                    _flow_store(state).enter_vn(char_id, session_id,
                                                state.chapter_title)
                    state.vn_enter_written = True
                    logger.info("bond_click resumed %s/%s（补落 vn_enter）",
                                char_id, session_id)
                except Exception as e:                 # noqa: BLE001 — 写失败降级不阻断
                    logger.warning("resumed vn_enter 写入失败: %s", e)
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
            # 并发下另一路已先初始化（通常是 worker 的 staged 预热抢先建好 vn）→
            # 放弃本次构造, 按现状返回（busy 由前端轮询）。
            # ⚠️ 2026-09-27（⑥-3b 冒烟抓到, 这条分支漏了两件事——同一竞态的先后两个后果）:
            #    ① **`chapter_title` 必带**——2026-09-11 那次"标题就是四个大字『羁绊剧情』"
            #       的修复漏了这条返回路径; ② 玩家**已经点了**, 就得把 adopt 的记账补上:
            #       staged 预热**不落** `vn_enter`（防未点击被推导 in_vn）, 而这里原来
            #       直接 return ⇒ 整章**一个 enter 都没有**: `chapter_index` 要 enter/exit
            #       配对 ⇒ 真机表现为回忆册里"已结束的故事 **0 章**"（`in_vn` 推导同样错）。
            #    为什么现在才露头: 前端 1s 轮询时"粉泡出现→点击"早过了预热窗口; ⑥-3b
            #    把轮询提到 250ms（气泡也更早上屏）⇒ 点击正落在预热**构造中**。
            if not staged and state.demo is None and not state.vn_enter_written:
                store = _flow_store(state)
                try:
                    store.enter_vn(char_id, session_id, state.chapter_title)
                    state.vn_enter_written = True
                except Exception as e:               # noqa: BLE001 — 写失败降级不阻断
                    logger.warning("并发 adopt vn_enter 写入失败: %s", e)
                state.t_staged = 0.0
                state.staged_seq = None
                _prewarm_cache_delete(char_id, store)   # adopt 消费（首场已进玩家视野）
                logger.info("bond_click concurrent adopt %s/%s（补落 vn_enter）",
                            char_id, session_id)
            logger.info("bond_click concurrent init skip %s/%s busy=%s staged=%s",
                        char_id, session_id, "y" if state.busy else "n",
                        "y" if staged else "n")
            return {"accepted": True, "busy": state.busy,
                    "chapter_title": _enter_title(state, char_id, session_id),
                    "resumed": state.vn is not None}

        engine = chat._engine(char_id)
        char = engine.current_character
        if char is None:
            return {"accepted": False, "error": "会话未打开"}
        title = _trigger_title(engine) or _title_from_events(
            char_id, session_id, _flow_store(state))

        # brain 注入（DESIGN_BRAIN.md, brain 2026-09-02 切换）: 世界线 wiki 第一人称——
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
            # ⚠️ **顺序不能反，且收尾要带条件** —— `commit_staging` 自带一次"有条件的
            # 收尾"（收真源里的**旧**未闭合段）; 搬完之后真源里那个未闭合段
            # **就是刚提交的这一章本身** ⇒ 这里只能收"没有东西可搬"时剩下的陈旧残留
            # （`_close_stale_attempts` 的长注释里有真机 bug 的完整来龙去脉）。
            moved = commit_staging(_fs, char_id, session_id, completed=False)
            _close_stale_attempts(_fs, char_id, session_id, moved=moved)
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
    # ⚠️ **2026-10-08 改闸门**: 从前是 `_last_bond_seq(...) == 0`（**全库**一条 bond
    #    事件都没有）⇒ 长线角色真源里早有前几章的板 ⇒ **恒 False** ⇒ 这条恢复路径
    #    实际上从没生效过。真机 `被感谢的人`: 预热写的 6 板里余下 5 板（含纪念板）
    #    白烧一次生成（`src=gen dur=20531ms`）。现在看**当前在押章**有没有已落库板:
    #    · 有 → 会被回放 ⇒ 交给回放交棒处（原语义不变）
    #    · 没有 → 正是"中断章 + 预热缓存/现场生成给首板"那条路 ⇒ **这里恢复后继板**
    if not staged and state.demo is None and state.scene_obj is None \
            and state.vn is not None \
            and _open_chapter_board_seq(char_id, session_id,
                                        _flow_store(state)) == 0:
        rest = _draft_pending(char_id, session_id, _flow_store(state))
        if rest:
            state.vn._pending_boards = [BondScene.from_dict(b) for b in rest]
            logger.info("bond_draft_q %s/%s boards=%d base_seq=%d vn_enter=%d",
                        char_id, session_id, len(rest),
                        _last_bond_seq(char_id, session_id, _flow_store(state)),
                        _open_vn_seq(char_id, session_id, _flow_store(state)))

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
