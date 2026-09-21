# -*- coding: utf-8 -*-
"""`webgui.bond` 的**生成与预生成**（C7, `docs/EXEC_SPLIT.md`）—— 板是怎么被造出来的。

## 放什么

· **生成**: `_generate`（一次 LLM 调用 → 流式/批式交付 → 失败重试 `MAX_GEN_FAILURES`、
  超限给 `_CLOSING_PARA` 收尾稿）· `_pregenerate`（读屏期间先把下一板造好; 节点 4′ 起
  与 live **同一条交付路径**）· `_scene_landed`（板落地后的统一收尾: marker / 草稿 /
  预热缓存 / 候选 spawn）
· **可归因**: `_log_board_deliver`（`bond_board_deliver src=… board=… recs=… dur=…`）
· **候选支**（DESIGN_CHOICE_PREGEN）: `_choice_pregen_enabled` · `_spawn_candidates` ·
  `_candidate_worker`
· **丢弃唯一入口**: `_discard_boards`（节点 2″; 清预生成板 + 候选支池 + 草稿旁路, 打
  一行 `bond_boards_discarded`）· `_discard_candidates`
· **每轮系统注记**: `_system_note`（`_REMIND_ROUNDS` 起收束提示, `_END_ROUNDS` 起强制
  收尾注记）—— ⚠️ 产品侧只有 `_generate` / `_pregenerate` 两处调用, 所以它住这里

## 纪律

· 依赖方向: `pregen` → `stores`（落库/草稿/预热缓存）+ `memorial`（纪念开画）+
  `state` + `deps` + `util`; **不反向** import `_impl`（标注入队走 `deps.enqueue_annotate`,
  不直接依赖 `lanes`）;
· ⚠️ **预生成 = provisional**（节点 4′）: 它的 `on_board` 回调**只记账不落库** ——
  事件的 `bond` 正文要等玩家消费后再推进一次才写（`_log_scene`）。改这里前先读
  `docs/EXEC_PIPELINE_UNIFY.md` §3.1 的不变量;
· ⚠️ 生图/看门狗阈值/choice 开关一律 `deps.*`（打**包属性**会静默失效, 见 C1a）;
· 搬进来的代码**逐字未改**。
"""

from __future__ import annotations

import json
import threading
import logging
import time
from core.bond.bond_story import (
    BondScene,
    SceneLoopError,
)
from webgui import chat, deps
from webgui.bond.memorial import (
    _ensure_memorial_img,
    _make_memorial_cb,
)
from webgui.bond.state import (
    BoardLifecycle,
    BondState,
    ChoiceCandidate,
    _bonds,
)
from webgui.bond.stores import (
    _draft_delete,
    _draft_save,
    _flow_store,
    _log_scene_meta,
    _prewarm_cache_save,
)
from webgui.bond.util import _ms_since

logger = logging.getLogger(__name__)


_CLOSING_TEXT = "（夜色渐深，这一章的羁绊剧情就此落下帷幕。）"


_CLOSING_PARA = [{"text": _CLOSING_TEXT, "emotion": "nomal"}]


MAX_GEN_FAILURES = 3


_REMIND_ROUNDS = 30


_END_ROUNDS = 50


def _generate(state: BondState, char_id: str, session_id: str, user_input: str) -> bool:
    """后台线程: 生成下一场 → 更新 state（场景/事件/兜底）。

    真实模式: send_vn_scene（LLM）; 演示模式: DEMO_SCRIPT 预设场景逐个弹出。
    Returns: 是否启动生成（False = 已有生成在跑——原子抢占失败, 调用方按 busy
    处理——2026-09-02 修复: 多标签页/前端并发 turn 的竞态, 双生成线程会互相
    覆盖 scene_obj/round, 造成黑背景/场景错乱）。
    """
    with state._lock:
        if state.busy:
            return False
        state.busy = True
        state.busy_since = time.monotonic()      # 看门狗计时起点（2026-09-11）
    state.error = ""

    def run():
        t0 = time.monotonic()                    # 计时埋点（§6.1）
        # 本次调用的台账短 id（2026-09-11）: 打给本块产出的每一板, 交付台账据此
        # 回答"这一板是哪次调用写的"（0 LLM 路径为 `-`）
        cid = f"{int(time.time() * 1000) % 0xFFFF:04x}"
        state._call_id = cid
        try:
            with chat._lock(char_id):
                first_scene = state.scene_obj is None   # 首场（重试也命中此判据）
                state.round += 1
                if state.demo is not None:
                    # 演示模式: 弹预设场景; 剧本耗尽 → closing 收尾（剧情必须终结）
                    scene_dict = state.demo.pop(0) if state.demo else None
                    scene = (BondScene.from_dict(scene_dict) if scene_dict
                             else BondScene(paragraphs=list(_CLOSING_PARA),
                                            is_end=True))
                else:
                    # 渐进渲染（P2-1 前置）: 引擎在**流式**中把已闭合的板交回来——
                    # 首板不必等整块写完（实测省 ~4-5s 首屏等待）。落地一次即止
                    # （`_streamed` 标记让下面的统一落地跳过它）。
                    def _on_board(scene_b: BondScene) -> None:
                        if state.scene_obj is not None and not state.scene_state.committed:
                            return          # 已有未播放板（不该发生）→ 不覆盖
                        scene_b._call_id = cid
                        _scene_landed(state, scene_b, char_id, session_id,
                                      user_input, t0=t0, save_cache=first_scene,
                                      source="stream")
                        logger.info("bond_stream_first %s/%s dur=%dms",
                                    char_id, session_id, _ms_since(t0))

                    scene = state.vn.send_vn_scene(
                        user_input, system_note=_system_note(state), annotate=False,
                        on_memorial_prompt=_make_memorial_cb(
                            state, char_id, session_id),
                        on_board=_on_board,
                    )
                    # SceneStream P1.5（2026-09-09 语义修正）: 篇幅超限不再丢弃
                    # LLM 场景换 closing 伪收场——纠正面在 system_note;
                    # 持续不收尾 = 玩家可离开（中场退出, 在押续写）
                scene._call_id = cid
                # 待发队列里的后续板同属这次调用 → 一并打上 id（交付时读得到）
                if state.vn is not None:
                    for _b in getattr(state.vn, "_pending_boards", None) or []:
                        _b._call_id = cid
                if getattr(scene, "_streamed", False):
                    state.fail_count = 0        # 流式已落地（含标注/日志）→ 只清失败计数
                else:
                    # 台账来源: 领待发队列（0 LLM——本回合早先那次调用切的尾板, 或
                    # 重进时草稿旁路灌回的板）→ 标 queue/draft, 别一律记 gen
                    # （决策 #35 可归因性: "这一板从哪来"要一眼可查）。
                    src = "demo" if state.demo is not None else "gen"
                    if state.demo is None and getattr(state.vn, "_served_from_pending",
                                                      False):
                        src = "draft" if getattr(scene, "_from_draft", False) else "queue"
                    _scene_landed(state, scene, char_id, session_id, user_input,
                                  t0=t0, save_cache=first_scene, source=src)
        except (SceneLoopError, ValueError) as e:
            # 模型连语义校验都过不了 → 偶发失败先给重试机会（2026-09-02:
            # 一败就 closing 会把偶发 JSON 错误变成"剧情突然结束"——上一场保持
            # 在屏, error 置位, 前端显示重试按钮重新 submit; 连续 3 次失败才
            # 中止（2026-09-09 语义修正, 用户拍板: **中断/异常 ≠ 失败/完成**）:
            # 不再 closing 伪收场——closing 曾伪装 story_end(is_end + completed)
            # → 前端 1.6s 自动 finish → vn_exit completed=True → digest 触发 +
            # "完整剧情"收尾话/兜底落库（历史遗留: 大量重复"好好记住"兜底话 +
            # wiki 空 = 从未自然完成的佐证）。修正: 超限 = 中止态——completed
            # 保持 False（剧情不终结, vn_enter 在押 = 中场退出语义）, 不落任何
            # 结束事件, 玩家可重试（error 已置, 前端重试按钮）或离开（重进走
            # 回放续写——2026-09-07 中断接入）。"放弃本章/拒绝邀约"= 未来项。
            logger.warning("bond 场景生成失败 (%s/%s) 第 %d 次 (%dms): %s",
                           char_id, session_id, state.fail_count + 1,
                           _ms_since(t0), e)
            state.fail_count += 1
            if state.fail_count > MAX_GEN_FAILURES:
                # 中止态（completed 保持 False）: 可重试或离开（重进回放续写）。
                # 错误详情不进 error（前端横幅短文案）——完整异常在 warning 日志
                # （diag 落盘 data/diag/live2be.log）
                state.error = ("剧情生成多次失败，已暂缓。"
                               "可点击重试继续；离开后重进可从已记录剧情续写。")
            else:
                state.error = str(e)        # 普通失败: 前端重试按钮
        finally:
            state.busy = False
            state.busy_since = 0.0
            # Storyloom bridge 式预生成（2026-08-30）: 主生成完成后（busy 已清零）
            # 才触发——纯叙事场（无 choices 未收尾）提前生成下一场, 玩家点"继续"
            # 时已就绪, 体感零等待。放 finally 而非 success 分支: success 分支里
            # busy 仍为 True, _pregenerate 守卫会误判"生成中"而跳过（真实踩坑）。
            if (state.demo is None and state.pregen_scene is None
                    and not state.completed
                    and state.scene_obj is not None
                    and not state.scene_obj.choices
                    and not state.scene_obj.is_end):
                _pregenerate(state, char_id, session_id)

    th = threading.Thread(target=run, daemon=True)
    state._gen_thread = th                          # 看门狗存活判定用
    th.start()


def _pregenerate(state: BondState, char_id: str, session_id: str) -> None:
    """Storyloom bridge 式预生成: 纯叙事场（无 choices）渲染完成即提前生成下一场。

    输入固定"（继续）"——玩家点继续时已就绪, 体感零等待; 生成失败降级
    （清 pregen, 玩家点击时走正常生成路径, 不阻断剧情）。预生成场景同样计入
    选项配额/表情统计（供后续 system_note 参考）。演示模式不预生成（即时弹出）。
    入口原子抢占（2026-09-02 修复: 与 _generate 同款锁——防并发双启动）。

    ⚠️ **节点 4′（2026-09-21）: 预生成与 live 走同一条交付路径**。
    此前这里**不传 `on_board`** ⇒ 引擎退回批式（`DeliveryMode.BLOCK`）——于是同一份
    LLM 输出在两条路上**给出不同的板**: "首板已交付之后的形状违规"在 live（流式）是
    advisory（照常交付）, 在预生成（批式）却是硬违规（打回 3 次 → `SceneLoopError`
    → 预生成失败）。预生成承诺的正是"玩家点继续时会看到什么", 所以必须与 live 同源:
    现在传 `on_board`（`_on_pregen_board`）⇒ `DeliveryMode.STREAM`。

    **预生成 = provisional（未 adopt 即丢弃）**: 那个回调只记账**不落库**——板进
    `state.pregen_scene` / 草稿旁路, 真源与暂存的 `bond` 事件要等玩家真的消费
    （`bond_turn` 的提升分支 → `_log_scene`）才写。"丢弃"不需要清任何东西
    （`docs/EXEC_PIPELINE_UNIFY.md` §3.1: 任何丢弃都不写标记）。
    """
    with state._lock:
        if state.busy or state.pregen_scene is not None \
                or state.demo is not None or state.vn is None:
            return
        state.busy = True
        state.busy_since = time.monotonic()      # 看门狗计时起点（2026-09-11）

    def run():
        t0 = time.monotonic()                    # 计时埋点（§6.1）
        cid = f"{int(time.time() * 1000) % 0xFFFF:04x}"
        state._call_id = cid
        delivered: list[BondScene] = []          # 流式回调收到的板（**provisional**）

        def _on_pregen_board(scene_b: BondScene) -> None:
            """预生成板的流式交付点——**只记账, 不落库**（节点 4′）。

            · 不落库 = provisional: `_log_scene` 在玩家消费时才调用（见函数 docstring）;
            · 记 `_call_id`: 板上要留"是哪次调用写的"（台账/草稿旁路都读它）;
            · `bond_pregen_board` 一行 = 预生成板的到达时刻（首板 TTFT 可比对
              `bond_pregen src=gen dur=ms`, 后者是**整块**写完的时刻）。
            """
            scene_b._call_id = cid
            delivered.append(scene_b)
            logger.info("bond_pregen_board board=%d recs=%d dur=%dms %s/%s",
                        len(delivered), len(scene_b.records), _ms_since(t0),
                        char_id, session_id)

        try:
            with chat._lock(char_id):
                scene = state.vn.send_vn_scene(
                    "（继续）", system_note=_system_note(state), annotate=False,
                    on_memorial_prompt=_make_memorial_cb(
                        state, char_id, session_id),
                    on_board=_on_pregen_board)
                # 台账（2026-09-11）: 这次预生成是**领队列**（0 LLM）还是**真调用**?
                # 引擎的 trace 写得很清楚（record_stream/pending = 从待发板拿出）。
                # 领队列时板上的 `_call_id` 保留"当初写它的那次调用"。
                trace = getattr(state.vn, "_trace", None) or [{}]
                from_queue = trace[0].get("action") == "record_stream/pending"
                if from_queue:
                    # 0 LLM 领队列: 板上的 `_call_id` 保留"当初写它的那次调用"
                    # （交付台账 src=queue 时会打出来）, 这里不另发 id
                    logger.info("bond_pregen src=queue call=- %s/%s dur=%dms",
                                char_id, session_id, _ms_since(t0))
                else:
                    scene._call_id = cid
                    for _b in getattr(state.vn, "_pending_boards", None) or []:
                        _b._call_id = cid
                    logger.info("bond_pregen src=gen call=%s boards=%d %s/%s dur=%dms",
                                cid, len(delivered), char_id, session_id,
                                _ms_since(t0))
                state.pregen_obj = scene
                state.pregen_scene = scene.to_dict()
                state.pregen_input = "（继续）"
                # 预生成场景同样异步标注（与主场景同一队列串行, 玩家消费时表情就绪）
                deps.enqueue_annotate(state, scene)
                _draft_save(state, char_id, session_id)   # 草稿旁路刷新（#28b）
        except Exception as e:                     # noqa: BLE001 — 预生成失败降级
            logger.warning("bond 预生成失败 (%dms, 降级为点击时再生成): %s",
                           _ms_since(t0), e)
            _discard_boards(state, char_id, reason="pregen-fail")
            _draft_save(state, char_id, session_id)    # 队列/当前板仍值得留（#28b）
        finally:
            state.busy = False
            state.busy_since = 0.0

    th = threading.Thread(target=run, daemon=True)
    state._pregen_thread = th                    # 看门狗存活判定用
    th.start()


def _scene_landed(state: BondState, scene: BondScene, char_id: str,
                  session_id: str, user_input: str, *, t0: float,
                  save_cache: bool, source: str = "gen") -> None:
    """场景落地公共路径（_generate 成功块与跨重启缓存命中共用, 2026-09-09）:

    设置 scene_obj/scene/input/落库就绪标记 + 配额/prev/meta/异步标注/候选
    spawn + 失败计数清零 + 计时日志。save_cache=True（LLM 首场落地）→ 写
    跨重启预热缓存; demo 不写。

    source（2026-09-11）: 交付来源——"stream"/"gen"/"prewarm"/"draft"/"demo"，
    透传给 `_log_board_deliver` 台账（调用方各自注明; 缺省 gen）。
    """
    state.scene_obj = scene
    state.scene = scene.to_dict()
    state.scene_input = user_input
    state.scene_state = BoardLifecycle.DELIVERED
    if scene.memorial and state.vn is not None:
        # 纪念区间置位（2026-09-12）: 引擎侧 `_finish_scene` 已置位, 但**预热缓存/
        # 草稿旁路/回放**这些“直接落地”的路径绕过它——统一在这里补一道（只置位,
        # 不复位: 区间内的后续板 `memorial=False` 但仍在窗口里）。
        state.vn._in_memorial = True
    _ensure_memorial_img(state, char_id, session_id)     # 回放/重启: 恢复档案图
    if scene.is_end:
        state.completed = True       # 仅自然 story_end 才 completed
    _log_board_deliver(state, scene, char_id, session_id, source,
                       dur_ms=_ms_since(t0) if t0 else -1)
    _log_scene_meta(state, char_id, session_id, scene)
    # 两遍式 C 异步标注: 骨架先显示, emotion 解析入队补标（不阻塞玩家）
    deps.enqueue_annotate(state, scene)
    # SceneStream P1.5（N2a）: 本板若带 choices → 候选支 spawn
    # （读板期后台预生成, 不占 busy; spawn 内部先清旧池）
    # 记录流 v2（P0-7c 修正）: 不 spawn——后继板已在引擎待发队列（0 LLM）,
    # fork 候选只是白复制一份; 裁决路径也不需要候选（见 bond_turn 裁决段）。
    if not scene.records:
        _spawn_candidates(state, scene, char_id, session_id)
    state.fail_count = 0           # 生成成功 → 失败计数清零
    # 计时埋点（§6.1）: 每轮生成耗时; 首场且仍处预热态（未被丢弃/
    # adopt）→ 预热就绪 latency
    if state.staged_seq is not None and state.round == 1:
        cur = _bonds.get((char_id, session_id))
        if cur is state and state.t_staged > 0:
            logger.info(
                "bond_prewarm_ready %s/%s lat=%dms",
                char_id, session_id, _ms_since(state.t_staged))
    suffix = ""
    if state.demo is not None:
        suffix = " demo"
    elif not save_cache:
        suffix = " cache"
    logger.info("bond_gen ok %s/%s round=%d dur=%dms%s",
                char_id, session_id, state.round, _ms_since(t0), suffix)
    # 跨重启预热缓存: 首个落地场景（LLM 真实引擎）→ 落盘（重启后 0 LLM）;
    # demo 不写; 缓存注入路径 save_cache=False 不自写
    if save_cache and state.demo is None:
        _prewarm_cache_save(char_id, session_id, scene.to_dict(),
                            user_input, state.chapter_title,
                            store=_flow_store(state))
    # 草稿旁路（#28b）: 每次板落地都刷新"未播放内容"（当前未落库板 + 待发队列）
    if state.demo is None:
        _draft_save(state, char_id, session_id)


def _log_board_deliver(state: BondState, scene: BondScene | None, char_id: str,
                       session_id: str, source: str, *, dur_ms: int = -1) -> None:
    """**板交付台账**（2026-09-11）: 这一板是怎么到玩家眼前的——一板一行 INFO。

    为什么需要（用户实际追问过）: 系统只记"生成了什么", 不记"这一板从哪来", 于是
    "玩家几乎零卡顿"到底是一次 LLM 写完整章、命中预热缓存、还是回放/草稿旁路,
    只能靠考古比对时间戳与条数（`[vn][records]` / `bond_pregen ok dur=0ms` /
    事件流时间戳）。有了这行, 一眼可答:

        bond_board_deliver src=queue board=3 recs=12 paras=10 call=c7f3 dur=0ms

    src 取值: stream（流式先交付）| gen（等整块/批量生成）| queue（预生成/待发队列,
    0 LLM）| prewarm（跨重启首场缓存）| draft（草稿旁路）| replay（事件流回放）
    | demo。call = 产出该板的 LLM 调用短 id（0 LLM 路径为 `-`）。
    """
    if scene is None:
        return
    try:
        logger.info(
            "bond_board_deliver src=%s board=%d recs=%d paras=%d call=%s dur=%dms %s/%s",
            source, state.round, len(getattr(scene, "records", None) or []),
            len(getattr(scene, "paragraphs", None) or []),
            getattr(scene, "_call_id", None) or "-",
            dur_ms, char_id, session_id)
    except Exception:                                # noqa: BLE001 — 埋点绝不阻断
        pass


def _choice_pregen_enabled() -> bool:
    """choice_pregen 开关（转发到 `deps.choice_pregen_enabled()`）。"""
    return deps.choice_pregen_enabled()


def _spawn_candidates(state: BondState, scene: BondScene,
                      char_id: str, session_id: str) -> None:
    """SceneStream P1.5（DESIGN_CHOICE_PREGEN §0, N2a）: choices 板候选支 spawn。

    choices 板落地（玩家开始读板/选项）即对每个候选项 fork 草稿引擎, 后台
    send("（继续）") 预生成"选了它之后的下一板"——把等待窗口前移到选项阅读期。
    - 候选引擎独立（fork_for_pick: 历史已 A1 内嵌裁决行, 标注链/place 分岔
      预期内）; **不持 chat._lock / 不占 state.busy**（加速器语义——玩家路径
      永不被候选阻塞; 同角色 LLM 并发 ≤ live+候选+lane, httpx 并发安全）
    - annotate=True（后台不可见, 同步标完——省 lane 归属改造; 消费即视觉就绪）
    - 失败 → status=failed（N2b 消费端降级老路）; 换板/作废 → 池清空, 孤儿
      线程完成即不可达（GC, 零落库）
    - 调用点: 主线 _generate 落地 + pregen 消费提升出 choices 板（N2b 补口）;
      spawn 前必清旧池（本函数负责, 调用方无需前置清池）
    """
    if state.demo is not None or state.vn is None:
        return
    if not deps.choice_pregen_enabled():         # 开关（N2d）: off → 老路
        return
    if not scene.choices or scene.is_end or scene.memorial:
        # 2026-09-21: 原判据含 v1 的 `scene.memorial_prompt`（字段已删）→ 改 v2 的
        # `scene.memorial`（同一意图: 纪念板不预生成候选支）
        return
    cands: list[ChoiceCandidate] = []
    for picked in scene.choices:
        fork = state.vn.fork_for_pick(picked)
        if fork is None:
            continue
        cands.append(ChoiceCandidate(picked=picked, engine=fork))
    if not cands:
        return
    with state._lock:
        state.choice_candidates = cands
    for c in cands:
        threading.Thread(target=_candidate_worker,
                         args=(state, c, char_id, session_id), daemon=True).start()
    logger.info("bond_cand spawn %s/%s round=%d n=%d",
                char_id, session_id, state.round, len(cands))


def _candidate_worker(state: BondState, cand: ChoiceCandidate,
                      char_id: str, session_id: str) -> None:
    """候选支生成线程: fork 引擎预生成下一板（同步标注）; 写回带池身份检查。"""
    t0 = time.monotonic()                     # 计时埋点（§6.1）
    try:
        scene = cand.engine.send_vn_scene("（继续）", annotate=True)
        with state._lock:
            # 池身份检查: 已被换板/作废 → 结果丢弃（孤儿, 不可达即 GC）
            if any(c is cand for c in state.choice_candidates):
                cand.scene_obj = scene
                cand.status = "ready"
                logger.info("bond_cand ready %s/%s picked=%s dur=%dms para=%d",
                            char_id, session_id, cand.picked, _ms_since(t0),
                            len(scene.paragraphs))
    except Exception as e:                    # noqa: BLE001 — 失败降级老路
        with state._lock:
            if any(c is cand for c in state.choice_candidates):
                cand.status = "failed"
        logger.warning("bond_cand fail %s/%s picked=%s (%dms): %s",
                       char_id, session_id, cand.picked, _ms_since(t0), e)


def _discard_boards(state: BondState, char_id: str, *, reason: str) -> None:
    """**统一的"丢弃未提交内容"入口**（节点 2″, `EXEC_PIPELINE_UNIFY` §3.1 不变量）。

    "丢" = **什么都不写**。append-only 真源与章内暂存里本来就没有未提交的板, 所以
    丢弃只是一次内存/草稿引用的摘除——**没有任何标记要清**, 也就没有"漏一处就污染"
    的问题（这正是 `staging.py` 相对 `vn_abandon` 的优势, 见 `docs/DESIGN_RESEND.md`）。

    覆盖三类未提交内容:
      ① **预生成板**（`pregen_obj/scene/input`）——生命周期里的 PROVISIONAL;
      ② **候选支池**（未选支的 fork 结果, 纯内存孤儿）;
      ③ **草稿旁路**（"已生成未播放"的持久化临时存储——预生成板的落点）。

    ⚠️ **不动当前板**（`scene_obj` / `scene` / `scene_state`）: 它一旦 DELIVERED 就是
    玩家屏上的内容, 要不要丢是**产品决策**（重发 / 拒绝邀约, 见 `docs/DESIGN_RESEND.md`
    的两区语义）, 不是清理动作。所以这里**不**替调用方决定, 只清"没人看过的东西"。
    ⚠️ 也不动 `_prewarm_cache`（那是**章节入口**的暂存首场, 生命周期属于"预热"而非
    "板"——它的失效判据是新鲜度 `staged_seq`, 见 `_prewarm_cache_delete`）。
    """
    had_pregen = state.pregen_obj is not None or state.pregen_scene is not None
    n_cands = len(state.choice_candidates or [])
    state.pregen_obj = None
    state.pregen_scene = None
    state.pregen_input = ""
    _discard_candidates(state)
    _draft_delete(char_id, _flow_store(state))
    # 丢弃的**唯一痕迹**就是这行日志（不写事件流——这正是 §3.1 那条不变量）
    logger.info("bond_boards_discarded reason=%s pregen=%s candidates=%d %s",
                reason, "yes" if had_pregen else "no", n_cands, char_id)


def _discard_candidates(state: BondState) -> None:
    """候选支池作废（DESIGN_CHOICE_PREGEN §1, N2c）: 清空引用 → 未选候选引擎
    即孤儿（生成中线程完成即不可达 → GC, 零落库）。列表替换为原子操作
    （GIL）; worker 写回带池身份检查（any(c is cand)）——清池后结果自然丢弃。
    """
    state.choice_candidates = []


def _system_note(state: BondState) -> str | None:
    """本轮系统注记（只进 context 不入历史）: 选项配额 / 表情单一提醒 /
    收尾提醒 / 上限建议。多条聚合为多行（每条一行）。

    **v1 的"纪念模式 → 请输出 memorial_exit 动作"注记已删除**（2026-09-12）:
    记录流 v2 里纪念是块内区间（`stage:memorial` 之后到块尾）, 没有 exit 动作——
    那条注记会把"输出动作 JSON"喂给只吃记录流的引擎（打回重发 → 反馈回环）。
    """
    notes: list[str] = []
    # ⚠️ 2026-09-20（用户裁决）: **中途退出后再进 = 静默重进, 不注任何信息**。
    #    曾经在这里注入过「老师上一轮是中途离开的…现在是老师回来了」——
    #    **已撤**（用户: *"不用这样设计啊，不需要任何信息，直接静默重进就可以了"*）。
    #    `state.quit_resume` / `_prev_chapter_quit()` 作为 **API 保留**（见那里的注释）,
    #    当前**没有消费者**。
    # 记录流 v2（P0-7c）: 旧的"整段剧情 2~3 次选项配额"注记退役——v2 的交互密度
    # 由 rules 引导（一段戏里老师开口 3~5 次）, 引擎不再逐轮念配额（注记进 prompt,
    # 提旧概念只会干扰守形）。计数器 `choices_used` 2026-09-21 一并删（只写不读）。
    # 2026-09-13（审计 B8）: "上一场 emotion 全同 → 请切换 emotion 并切新单元"
    # 注记**一并退役**——emotion 由标注层按记录逐条给（决策 #27）; 写作者既看不见
    # 也没有 emotion 字段可写（v2 schema 只有 character/stage + text）。那条注记
    # 是写给 v1（emotion 由主 LLM 内联）的, 在 v2 下每轮白喂且会诱导模型为了
    # "切换单元"把输出碎化。`prev_emotions` 字段随之失去唯一消费者, 已删。
    if state.round == _REMIND_ROUNDS:
        notes.append(
            f"（系统）剧情已推进 {state.round} 轮，剩余约 {_END_ROUNDS - state.round} 轮。"
            "请开始把剧情向结尾收束——感情到位、约定达成、道别告别的时刻"
            "就把本轮的**最后一条记录**写成 stage=end 收尾，不要再开新场景"
            "不过也谨记这只是中段提示，你并不需要匆匆结尾，但是建议开始铺垫"
        )
    if state.round == _END_ROUNDS:
        notes.append(
            "（系统）已达剧情篇幅上限。本轮请用 stage=end 收尾"
            "结束剧情——收尾那一条 text 是收尾字段（可留空 = 直接黑屏退场）。"
        )
    if state.round > _END_ROUNDS:
        # 超限后的每轮强制（2026-09-09 取代旧 FORCE_AFTER closing——强制注记
        # 引导自然收尾, 不做伪收场）
        notes.append(
            "（系统）剧情已远超篇幅上限。本轮**必须**把最后一条记录写成 stage=end"
            "收尾结束剧情——不再开新场景、不再写新的铺垫。"
        )
    return "\n".join(notes) if notes else None
