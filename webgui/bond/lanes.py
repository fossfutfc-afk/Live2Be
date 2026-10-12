"""`webgui.bond` 的**双路标注 lane**（C4, `docs/EXEC_SPLIT.md`）。

## 放什么

· **就绪门控**（纯判定, 不碰线程）: `_memorial_no_visuals`（整板都在纪念里 → 标了没人看）·
  `_scene_emotions_ready` / `_scene_places_ready` / `_scene_visual_ready`（双路齐）·
  `_scene_obj_visual_ready`（对任意场景, 含预生成板）· `_scene_ready_or_busy` ·
  `_wait_annotated`
· **双路 lane**: `_ensure_lane`（懒起消费者线程）· `_enqueue_annotate`（emotion + place
  两路一起入队）· `_enqueue_place_annotate` · `_anno_worker` / `_place_worker`
  （各一路队列消费者）· `_fallback_fill`（板内延续兜底）

## 纪律

· 依赖方向: `lanes` → `state`（`BondState`）+ `util`（`_ms_since`）+ `deps`; 不反向
  import `_impl`。C8 的 `watchdog` 会**反过来** import 这里的 `_scene_*_ready`
  （单向 —— 门控判定属 lane, 看门狗只是消费它）;
· ⚠️ **换 store / 关 lane 一律走 `webgui.deps`**（`deps.enqueue_annotate` 的转发目标
  就是这里的 `_enqueue_annotate`）—— 子模块读自己的全局, 打**包属性**会静默失效;
· 搬进来的代码**逐字未改**。
"""
from __future__ import annotations

import logging
import queue
import threading
import time

from core.bond.bond_story import BondScene
from webgui.bond.state import BondState
from webgui.bond.util import _ms_since  # ⚠️ C4 漏了这一行（见 tests/core/test_split_safety.py 的泄漏守门）

logger = logging.getLogger(__name__)


def _memorial_no_visuals(state: BondState, scene=None) -> bool:
    """这一板**整板**都在纪念视觉里（立绘隐藏 + 普通背景清空）→ 标注无意义。

    依据（前端定稿行为, `bond.js::applyMemorial`）: 纪念窗口期间立绘整层隐藏 +
    普通背景清空（黑屏兜底, 只有纪念图淡入）——所以 emo（表情）与 place（背景）
    标了也没人看。跳过它们 = 每次纪念省 1~2 次调用, 也免掉门控白等 ~1s
    （2026-09-12 用户核对纪念行为时确认: 立绘不工作, emo lane 本不该跑）。

    ⚠️⚠️ **2026-09-20（M3 记录级进入点）改判据**: 原来是
    `scene.memorial or vn.in_memorial` = **整板**跳过。但进入点改成
    "黑屏从 `stage:memorial` **那一句**开始"之后, **触发记录之前的那几条是在
    正常视觉下播的**（立绘显示着、背景还在）——整板跳过会让它们**永远拿不到表情键、
    立绘恒默认**, 是一条静默的画质退化。所以现在:

    * 本板自己触发 → 只有进入点落在**板首**（`memorial_at` 为 0 / 缺字段）才整板无视觉;
    * 窗口从**上一板**延续过来（`vn.in_memorial`）→ 整板都在窗口里, 照旧跳过。

    注意判定**必须先看本板自己的 `memorial_at`**: `vn.in_memorial` 在纪念板落地时
    就已经是 True 了（`_scene_landed` 先置位、再入标注队列）, 先看它会误判。
    """
    if state.demo is not None or state.vn is None:
        return False
    if bool(getattr(scene, "memorial", False)):
        return getattr(scene, "memorial_at", None) in (None, 0)
    return bool(getattr(state.vn, "in_memorial", False))


def _scene_emotions_ready(state: BondState) -> bool:
    """当前展示场景的 emotion 是否已就绪（2026-09-02 推进门控）。

    骨架 emotion 已移交标注层（全量回填/兜底）——玩家推进前必须等标注完成,
    否则: ① 立绘表情不到位; ② 场景落库（append-only）会缺 emotion。
    就绪判定: demo/无词表（无标注能力）→ 恒就绪; 否则当前场景全部段落
    （含 branches）都有 emotion。
    """
    if state.demo is not None or state.vn is None:
        return True
    if not state.vn._lexicon_keys:            # 无词表 → 引擎不标注 → 恒就绪
        return True
    scene = state.scene_obj
    if scene is None:
        return True
    if _memorial_no_visuals(state, scene):
        return True                            # 纪念: 立绘隐藏 → 无需 emotion
    groups = [scene.paragraphs] + list(scene.branches.values())
    for group in groups:
        for p in group:
            if isinstance(p, dict) and not (p.get("emotion") or "").strip():
                return False
    return True


def _scene_places_ready(state: BondState) -> bool:
    """当前展示场景的 place 标注是否已就绪（DESIGN_BOND_CONTRACT_V2 §7, P3b-1）。

    place 是事件型判定（变化句才产出, keep 是常态）——不能靠内容判完成, 用
    scene 对象上的 _place_done 标记（place lane 对当前场景尝试过 = 完成, 无论
    是否产出锚点）。分支反应段/无词表/纪念退出/无当前场景 → 恒就绪（不占 lane）。
    """
    if state.demo is not None or state.vn is None:
        return True
    if not state.vn._place_keys:          # 无地点词表 → 引擎不标注 → 恒就绪
        return True
    scene = state.scene_obj
    if scene is None:
        return True
    if _memorial_no_visuals(state, scene):
        return True                            # 纪念: 背景清空（黑屏/纪念图）→ 无需 place
    return bool(getattr(scene, "_place_done", False))


def _scene_visual_ready(state: BondState) -> bool:
    """双路齐（gate = emotion + place 都就绪, §7.1）。"""
    return _scene_emotions_ready(state) and _scene_places_ready(state)


def _scene_obj_visual_ready(state: BondState, scene) -> bool:
    """任意场景对象的双路就绪判定（预生成消费门用, 2026-09-08）:

    emotion = 内容判（含 branches 全有键; 无词表/纪念退出 → 无需）;
    place   = 标记判（判定完成即含 keep; 无词表/纪念退出 → 无需）。
    demo/无引擎/无场景 → 恒就绪（不阻塞消费）。
    """
    if scene is None or state.vn is None or state.demo is not None:
        return True
    vn = state.vn
    if not _memorial_no_visuals(state, scene):
        if vn._lexicon_keys:
            for group in [scene.paragraphs, *scene.branches.values()]:
                for p in group:
                    if isinstance(p, dict) and not (p.get("emotion") or "").strip():
                        return False
        if vn._place_keys and not getattr(scene, "_place_done", False):
            return False
    return True


def _scene_ready_or_busy(state: BondState) -> dict | None:
    """门控检查: 未就绪 → 返回 busy 响应（前端已有 busy 轮询重试, 标注 2~5s 内
    完成/兜底 → 下次重试放行）; 就绪 → None（继续正常 turn 流程）。"""
    if not _scene_visual_ready(state):
        return {"accepted": False, "busy": True,
                "error": "视觉标注中, 稍后自动继续"}
    return None


def _wait_annotated(state: BondState, timeout: float = 8.0) -> None:
    """同步短等当前场景（scene_obj）标注就绪（2026-09-02 修复: 分支消费等
    turn 直接返回场景的路径——渲染即表情就绪, 不给前端留 default 残留窗口）。

    标注 worker 独立线程串行, 正常 1~3s（修复后无 reasoning 截断）; 超时返回
    （worker 卡死时 _fallback_fill 兜底后门控也必达——宁缺勿错不无限等）。
    """
    deadline = time.time() + timeout
    while time.time() < deadline and not _scene_emotions_ready(state):
        time.sleep(0.05)


def _ensure_lane(state: BondState, *, started_attr: str, thread_attr: str,
                 worker_fn, lane: str) -> None:
    """lane 看门狗（2026-09-08 自查加固）: 启动标记 + 线程存活双检——

    若 worker 曾意外死亡（标记 True 但线程已死）→ 下次入队自动重启, 防
    "ver 恒 0 + gate 恒 true" 的永久饥饿。正常驻留线程（阻塞等队列）→ 不重启。
    """
    th = getattr(state, thread_attr)
    if getattr(state, started_attr) and th is not None and th.is_alive():
        return
    setattr(state, started_attr, True)
    t = threading.Thread(target=worker_fn, args=(state,), daemon=True)
    setattr(state, thread_attr, t)
    t.start()
    logger.info("bond_anno lane %s start tid=%s", lane, t.ident)


def _enqueue_annotate(state: BondState, scene: BondScene) -> None:
    """场景入队异步标注（两遍式 C + place lane, P3b-1 双路并行）。

    骨架先显示 → emotion/place 各自 lane 串行补标（标注 LLM 调用不持 chat._lock
    ——并发 API 调用可接受; 写回持短锁 + 对象身份检查——场景已被替换则丢弃,
    异步线程绝不覆盖比它新的状态）。emotion 有内容判定（全回填/兜底）, place
    靠 scene._place_done 标记（含 keep 即完成）——推进门控 = 双路齐。
    """
    if state.demo is not None or state.vn is None:
        return
    if _memorial_no_visuals(state, scene):
        # 纪念窗口: 立绘隐藏 + 背景清空 → emo/place 标了也没人看, 不占 lane
        # （2026-09-12: 此前只排除 memorial_exit, 纪念板照样花 1~2 次调用 + 门控等待）
        logger.info("bond_anno enq emo=False place=False scene=%s (memorial: 无视觉键)",
                    id(scene))
        return
    # 入队打点（2026-09-08 首板 nomal 排查）: 每场景标注意向一目了然（emo/place）
    _want_emo = bool(state.vn._lexicon_keys
                     and any(not p.get("emotion") for p in scene.paragraphs
                             if isinstance(p, dict)))
    _want_place = bool(state.vn._place_keys
                       and not getattr(scene, "_place_done", False))
    logger.info("bond_anno enq emo=%s place=%s scene=%s",
                _want_emo, _want_place, id(scene))
    _enqueue_place_annotate(state, scene)   # 双路并行 lane（§7）——独立于 emotion 守卫
    if not state.vn._lexicon_keys:
        return                                      # 无词表 → 无需标注
    if not any(not p.get("emotion") for p in scene.paragraphs
               if isinstance(p, dict)):
        return                                      # 骨架已全带 emotion → 跳过
    if state._anno_queue is None:
        state._anno_queue = queue.Queue()
    state._anno_queue.put(scene)
    _ensure_lane(state, started_attr="_anno_started", thread_attr="_anno_thread",
                 worker_fn=_anno_worker, lane="emo")


def _enqueue_place_annotate(state: BondState, scene: BondScene) -> None:
    """场景入队地点变更标注（DESIGN_BOND_CONTRACT_V2 §7, P3b-1 双 lane 第二路）。

    判定完成（含 keep/失败）即置 scene._place_done（gate 恒可达）——place 是
    事件型判定, 不能靠内容判完成。分支反应段（同板延续）在创建处已置就绪,
    不占 lane; 无词表/纪念退出 → 不入队（就绪判定同样提前放行）。
    """
    if state.demo is not None or state.vn is None:
        return
    if not state.vn._place_keys:
        return
    if getattr(scene, "_place_done", False):
        return
    if state._place_queue is None:
        state._place_queue = queue.Queue()
    state._place_queue.put(scene)
    _ensure_lane(state, started_attr="_place_started", thread_attr="_place_thread",
                 worker_fn=_place_worker, lane="place")


def _anno_worker(state: BondState) -> None:
    """标注队列单 worker: 串行补标场景（正文 + branches）, 写回带防竞态检查。

    写回规则: scene_obj 仍是 state.scene_obj（当前展示）或 state.pregen_obj
    （预生成待消费）→ 序列化更新 + emo_version++（前端补切表情）;
    否则（场景已被推进/替换）→ 丢弃（标注结果作废, 不污染新场景）。
    fill 异常 → `_fallback_fill` 强制兜底（门控就绪恒可达, 剧情必须能推进）。
    """
    while True:
        scene = state._anno_queue.get()
        if scene is None:
            break
        state._lane_inflight += 1                # 在途（看门狗据此不误判 lane 空闲）
        t0 = time.monotonic()                    # 计时埋点（§6.1）
        try:
            try:
                state.vn.fill_scene_emotions_text(scene)   # 标注 LLM（不持锁）
                failed = False
            except Exception as e:                       # noqa: BLE001 — 标注失败兜底
                failed = True
                logger.warning("bond 异步标注失败（兜底延续）: %s", e)
            _fallback_fill(scene)                        # 保险网: 空 emotion 强制 nomal
            logger.info("bond_anno dur=%dms fallback=%s",
                        _ms_since(t0), "n" if not failed else "y")
            with state._lock:
                if state.scene_obj is scene:
                    state.scene = scene.to_dict()
                    state.emo_version += 1
                elif state.pregen_obj is scene:
                    state.pregen_scene = scene.to_dict()
                    state.emo_version += 1
                # 已被替换/消费后又被推进 → 丢弃（异步不覆盖新状态）
        except Exception as e:                           # noqa: BLE001 — 保活: 单条失败
            logger.warning("bond 标注处理异常（跳过本条, worker 保活）: %s", e)
        finally:
            state._lane_inflight -= 1                    # 出在途（与上面的 +1 成对）
            try:
                state._anno_queue.task_done()
            except Exception:                            # noqa: BLE001 — 幂等无害
                pass
    # 正常结束（None 哨兵）: 复位启动标记——后续入队可再启（worker 永不饿死）
    state._anno_started = False
    state._anno_thread = None


def _place_worker(state: BondState) -> None:
    """place 标注 lane: 串行判定场景换场锚点（fill_scene_places——成功/失败/
    无变更都置完成标记, keep 是合法结果）, 写回带防竞态检查（同 _anno_worker）。

    时序（§7.1）: place 判定句少、通常先于 emotion 完成; 锚点写回 scene 对象
    的变更句 place 键——事件落库（_log_scene 用 scene.to_dict()）与回放时间轴
    自动携带; 视觉键不进 LLM 上下文（render 忽略）。
    """
    while True:
        scene = state._place_queue.get()
        if scene is None:
            break
        state._lane_inflight += 1                # 在途（看门狗据此不误判 lane 空闲）
        t0 = time.monotonic()                    # 计时埋点（§6.1）
        anchors = False
        try:
            try:
                anchors = state.vn.fill_scene_places(scene)   # 标注 LLM（不持锁）
            except Exception as e:                       # noqa: BLE001 — 失败即 keep
                logger.warning("bond 异步 place 标注失败（keep 保持背景）: %s", e)
            scene._place_done = True                     # 判定完成（含 keep）——gate 可达
            logger.info("bond_anno_place dur=%dms anchors=%s",
                        _ms_since(t0), "y" if anchors else "n")
            with state._lock:
                if state.scene_obj is scene:
                    state.scene = scene.to_dict()        # 当前展示场景: 序列化视图同步
                elif state.pregen_obj is scene:
                    state.pregen_scene = scene.to_dict() # 预生成待消费: 只更新暂存视图
                # 已被推进/替换 → 丢弃（异步不覆盖新状态, 同 _anno_worker）
        except Exception as e:                           # noqa: BLE001 — 保活: 单条失败
            logger.warning("bond place 标注处理异常（跳过本条, worker 保活）: %s", e)
        finally:
            state._lane_inflight -= 1                    # 出在途（与上面的 +1 成对）
            try:
                state._place_queue.task_done()
            except Exception:                            # noqa: BLE001 — 幂等无害
                pass
    # 正常结束（None 哨兵）: 复位启动标记——后续入队可再启（worker 永不饿死）
    state._place_started = False
    state._place_thread = None


def _fallback_fill(scene: BondScene) -> None:
    """标注兜底（2026-09-02）: 空 emotion 段落强制回填 nomal。

    保险网——fill_scene_emotions_text 正常路径已全量回填/延续（幂等）; 若标注层
    异常漏网（段落仍无 emotion）→ 强制兜底, 保证推进门控就绪**恒可达**
    （剧情必须能推进; 失败只影响表情精度, 宁缺勿错）。
    """
    for group in [scene.paragraphs, *scene.branches.values()]:
        for p in group:
            if isinstance(p, dict) and not (p.get("emotion") or "").strip():
                p["emotion"] = "nomal"
