# -*- coding: utf-8 -*-
"""webgui 羁绊剧情驱动 — CLI run_bond_story_vn（core/ui/vn_cli.py）的异步化状态机。

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
    - 双层收尾兜底（remind/end 系统注记 + 超限强制 closing——剧情必须终结）
    - 纪念子模式（in_memorial → 注入 exit schema; 无生图 → 纯文字, 剧情照走）
    - 失败降级（SceneLoopError → closing 场景落库 + completed, 宁缺勿错）
    - 事件流: bond 事件 {input, picked, ...scene} + memorial/vn_state marker
      （与 CLI 落库格式一致, 回放兼容）

注意: BondStoryEngine 实例在内存（单用户本机, 同 chat.py 引擎管理）;
重启服务丢内存态, 事件流在——中断的 VN 通过 vn_state marker 可重建（M3 回放）。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field

from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError
from core.media.gallery import GalleryStore
from core.momotalk import load_brain_segment
from core.session.events import (
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_VN_EXIT,
    M_VN_STATE,
    make_event,
)
from core.session.renderer import window_messages
from core.ui.vn_cli import _build_director, _trigger_reason
from llm.image_gen import ImageGenerator, collect_ref_images
from webgui import chat

logger = logging.getLogger(__name__)

#: 双层收尾兜底（与 CLI 默认一致——剧情必须终结, 宁缺勿错）
_REMIND_ROUNDS = 30
_END_ROUNDS = 50
#: 超限强制收尾（CLI force_after = end_rounds + 2）
_FORCE_AFTER = _END_ROUNDS + 2
#: 程序兜底 closing 文案（错误收场 / 超限收场）
_CLOSING_TEXT = "（夜色渐深，这一章的羁绊剧情就此落下帷幕。）"
#: closing 段落（程序文案, 无标注——自带 emotion, 门控恒就绪, 2026-09-02）
_CLOSING_PARA = [{"text": _CLOSING_TEXT, "emotion": "nomal"}]
#: 场景生成连续失败上限（2026-09-02: 偶发 JSON 失败给重试机会, 超限才 closing）
MAX_GEN_FAILURES = 3

#: 演示模式预设剧本（不调 LLM——前端 VN 体验/联调用; 3 场: 选项 → 选项 → is_end,
#: 覆盖背景切换/emotion 变化/收尾。BondScene 契约格式, 键用最新词表名）
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


@dataclass
class BondState:
    """一场羁绊剧情的驱动状态（per (char_id, session_id) 内存态）。"""

    vn: BondStoryEngine | None = None
    demo: list[dict] | None = None      # 演示模式: 预设剧本（不调 LLM）; None = 真实引擎
    round: int = 0                      # 已生成场景数（系统注记 / 前端轮询去重）
    busy: bool = False                  # 场景生成中（LLM 秒级, 后台线程）
    scene_obj: BondScene | None = None  # 当前展示场景（运行时对象, 含 memorial 标记）
    scene: dict | None = None           # scene_obj.to_dict()（前端消费）
    scene_input: str = ""               # 生成 scene 用的输入（落库 input 字段）
    scene_logged: bool = True           # scene 是否已落事件流（append-only: 玩家裁决时补录）
    error: str = ""
    completed: bool = False             # 剧情已终结（is_end / 致命错误）→ 前端调 finish
    reason: str = ""
    # 生成失败重试（2026-09-02: 偶发 JSON 失败不再一败就 closing——前 3 次失败保留
    # 上一场在屏 + 置 error, 前端显示重试按钮重新生成; 连续超限才 closing 收尾）
    fail_count: int = 0
    # Storyloom bridge 式预生成（2026-08-30）: 纯叙事场（无 choices）渲染完成即
    # 提前生成下一场（输入固定"（继续）"）——玩家点继续时已就绪, 体感零等待
    pregen_obj: BondScene | None = None
    pregen_scene: dict | None = None
    pregen_input: str = ""
    # 选项配额（整段剧情 2~3 次选择——LLM 每场给选项的疲劳问题）: 已用计数,
    # 注入 system_note 提醒; 预生成场景的 choices 同样计入
    choices_used: int = 0
    # 上一场 emotion 序列（单一检测: 全场同一 emotion → 下一场 system_note 提醒 LLM）
    prev_emotions: list[str] = field(default_factory=list)
    # 异步标注（两遍式 C 2026-08-31）: emotion 解析挪出玩家等待路径——
    # 骨架先显示, 标注队列单 worker 串行补标, 写回经对象身份检查防竞态
    emo_version: int = 0                       # emotion 补标版本（前端感知补切表情）
    _anno_queue: "queue.Queue | None" = field(default=None, repr=False)
    _anno_started: bool = field(default=False, repr=False)
    # 纪念立绘异步生成（方案 A 2026-09-01）: 流式嗅探到 memorial_enter 的 prompt
    # 定稿即后台生图（与 LLM 剩余输出并行）——玩家看到纪念场景时图已就绪, 淡入
    memorial_img: str = ""                     # 前端 URL（/gallery/{char}/{sid}.png）; 空 = 未就绪/失败
    memorial_img_ready: bool = False           # 图已落盘可展示
    memorial_img_busy: bool = False            # 生图中（防重复触发; 重试 attempt 可能重复回调）
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


_bonds: dict[tuple[str, str], BondState] = {}


def _state(char_id: str, session_id: str) -> BondState:
    """懒创建 bond 状态（每 (char, session) 一场剧情）。"""
    key = (char_id, session_id)
    if key not in _bonds:
        _bonds[key] = BondState()
    return _bonds[key]


def _store():
    return chat._store


#: 生图器懒初始化缓存（首次纪念触发才构造——无 key 环境零开销）
_image_gen: ImageGenerator | None = None


def _image_generator() -> ImageGenerator | None:
    """懒初始化生图器。未配 IMAGE_API_KEY（非 API 模式）→ None = 纪念降级纯文字。

    webgui 不做本地 diffusers 兜底（20 分钟/张不可接受）——API 模式才启用。
    """
    global _image_gen
    if _image_gen is None:
        try:
            _image_gen = ImageGenerator()
        except Exception as e:                   # noqa: BLE001 — 构造失败降级
            logger.warning("生图器初始化失败（纪念降级纯文字）: %s", e)
            return None
    if not _image_gen.is_api_mode:
        return None
    return _image_gen


def _memorial_gen(state: BondState, char_id: str, session_id: str,
                  prompt: str) -> None:
    """纪念立绘异步生成（方案 A）: generate → 画廊落盘 → 写回 state。

    触发早于契约校验——动作最终可能被拒（频率限制/坏 JSON → 图作废, 接受浪费）。
    失败降级: 不设置 memorial_img（前端纯文字, 剧情照走）。写回持短锁;
    场景已推进不影响（前端只在纪念场景显示图）。
    """
    try:
        gen = _image_generator()
        if gen is None:
            return                              # 未配 key → 降级纯文字
        char = chat._engine(char_id).current_character
        name = char.display_name if char is not None else "角色"
        png = gen.generate(prompt, ref_images=collect_ref_images(char_id),
                           character_name=name)
        sid = GalleryStore(_store().data_root, world_id=_store().world_id).write(
            char_id, prompt, session_id, png)
        with state._lock:
            state.memorial_img = (
                f"/gallery/{_store().world_id}/{char_id}/{sid}.png")
            state.memorial_img_ready = True
    except Exception as e:                       # noqa: BLE001 — 失败降级纯文字
        logger.warning("纪念立绘生成失败（降级纯文字）: %s", e)
        with state._lock:
            state.memorial_img = ""
            state.memorial_img_ready = False
    finally:
        with state._lock:
            state.memorial_img_busy = False


def _make_memorial_cb(state: BondState, char_id: str, session_id: str):
    """流式嗅探回调: prompt 定稿 → 重置图状态 + 开生图线程（不阻塞 LLM 收集线程）。

    在 LLM 收集线程内被调用（持 chat._lock）——只开线程, 不做重活。
    防重复: memorial_img_busy 时跳过（重试 attempt 可能再次触发, 第一张作废）。
    """
    def cb(prompt: str) -> None:
        if state.demo is not None:
            return
        with state._lock:
            if state.memorial_img_busy:
                return
            state.memorial_img_busy = True
            state.memorial_img = ""
            state.memorial_img_ready = False
        threading.Thread(target=_memorial_gen,
                         args=(state, char_id, session_id, prompt),
                         daemon=True).start()
    return cb


# ---------------------------------------------------------------------------
# 公开 API（路由层调用）
# ---------------------------------------------------------------------------

def bond_start(char_id: str, session_id: str) -> dict:
    """进入羁绊剧情: 构造引擎 + vn_enter marker + 后台生成首场。

    幂等: 已有进行中的 bond 状态（真实引擎或演示剧本）→ 返回现状（前端重进不重建）。
    已完成（completed）→ 拒绝再进入（粉泡入口点击后由后端裁决——2026-09-01）。
    中断再进入: 玩家中途退出后重进 → 内存态在（resumed）→ 从中断场景继续,
    vn 引擎历史完整 → AI 正确衔接（事件流重建是 M3 回放, 服务重启前不做）。
    """
    state = _state(char_id, session_id)
    if state.completed:
        return {"accepted": False, "completed": True,
                "error": "这段羁绊剧情已经完成"}
    if state.vn is not None or state.demo is not None:
        return {"accepted": True, "busy": state.busy, "resumed": True}
    if state.busy:
        return {"accepted": False, "busy": True, "error": "正在生成首场"}

    engine = chat._engine(char_id)
    char = engine.current_character
    if char is None:
        return {"accepted": False, "error": "会话未打开"}
    reason = _trigger_reason(engine)

    # brain 注入（DESIGN_BRAIN.md, wiki_v2 2026-09-02 切换）: 世界线 wiki 第一人称——
    # VN 中角色记得前面的事（出厂基座 0 LLM 确保; 失败静默零注入）
    brain_segment = load_brain_segment(
        _store(), char.character_id, char.display_name,
        characters_root=engine.char_loader.root)

    vn = BondStoryEngine(
        engine.char_loader.root, engine.llm,
        director=_build_director(char, reason), brain_segment=brain_segment)
    vn.start_session(char.character_id)
    # 统一上下文窗口（2026-09-05, DESIGN_CONTEXT_WINDOW）: 从事件流灌最近叙事进
    # vn._history——首场带着触发前的 MMT 对话（断桥修复）; 事件流已是终态
    # （裁决时落库 + 门控保证标注就绪）; 与引擎自增历史同构, 滑动无缝
    try:
        _win = window_messages(_store().events(char_id))
        if _win:
            vn._history = _win
    except Exception:                                # noqa: BLE001 — 灌窗失败不阻断
        pass

    state.vn = vn
    state.reason = reason
    # 事件流: vn_enter marker（单事件流; 中断恢复依赖它推导 in_vn）
    try:
        _store().enter_vn(char_id, session_id, reason)
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断 VN
        logger.warning("事件流 vn_enter 写入失败: %s", e)

    seed = f"（旁白）基于「{reason}」……" if reason else "（旁白）故事开始了……"
    _generate(state, char_id, session_id, seed)
    # reason 随响应返回——前端进场景等待期显示"章节标题卡"（掩盖首场生成缓冲）
    return {"accepted": True, "busy": True, "resumed": False, "reason": reason}


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
    state.reason = "（演示）"
    try:
        _store().enter_vn(char_id, session_id, state.reason)
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断
        logger.warning("事件流 vn_enter 写入失败: %s", e)
    _generate(state, char_id, session_id, "（演示开始）")
    return {"accepted": True, "busy": True, "resumed": False}


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
    groups = [scene.paragraphs] + list(scene.branches.values())
    for group in groups:
        for p in group:
            if isinstance(p, dict) and not (p.get("emotion") or "").strip():
                return False
    return True


def _scene_ready_or_busy(state: BondState) -> dict | None:
    """门控检查: 未就绪 → 返回 busy 响应（前端已有 busy 轮询重试, 标注 2~5s 内
    完成/兜底 → 下次重试放行）; 就绪 → None（继续正常 turn 流程）。"""
    if not _scene_emotions_ready(state):
        return {"accepted": False, "busy": True,
                "error": "情绪标注中, 稍后自动继续"}
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


def bond_turn(char_id: str, session_id: str, text: str) -> dict:
    """玩家裁决（选项文本 / 自由输入 / 点击继续）→ 补录上一场事件 → 衔接下一场。

    预生成消费（Storyloom bridge 式）: 纯叙事场（无 choices）点"（继续）"时,
    下一场已提前生成（state.pregen）→ 直接衔接, 零等待; 预生成失败降级为
    正常生成路径（不阻断剧情）。
    """
    state = _state(char_id, session_id)
    if state.vn is None and state.demo is None:
        return {"accepted": False, "error": "剧情未开始"}
    if state.busy:
        return {"accepted": False, "busy": True, "error": "剧情生成中"}
    if state.completed:
        return {"accepted": False, "completed": True, "error": "剧情已结束"}
    text = (text or "").strip()
    if not text:
        return {"accepted": False, "error": "输入不能为空"}

    # 推进门控（2026-09-02）: 当前场景（含分支）emotion 未标注完成 → 不让推进
    # （情绪不到位不点下一轮——标注 2~5s, 前端 busy 轮询自动放行; 同时保证
    # 落库场景 emotion 完整: 分支消费/继续/自由输入都在标注就绪后才落库）
    gate = _scene_ready_or_busy(state)
    if gate is not None:
        return gate

    if text == "（继续）" and state.pregen_scene is not None:
        # 预生成就绪 → 补录当前场 → 提升预生成场景为当前场 → 链式预生成
        _log_scene(state, char_id, session_id, picked=None)
        state.scene_obj = state.pregen_obj
        state.scene = state.pregen_scene
        state.scene_input = state.pregen_input
        state.scene_logged = False
        state.pregen_obj = None
        state.pregen_scene = None
        state.pregen_input = ""
        state.round += 1
        if state.scene_obj is not None and state.scene_obj.is_end:
            state.completed = True
        _log_scene_meta(state, char_id, session_id, state.scene_obj)
        # 链式: 新场景若是纯叙事（无 choices 未收尾）→ 继续预生成下一场
        if (state.scene_obj is not None
                and not state.scene_obj.choices and not state.scene_obj.is_end):
            _pregenerate(state, char_id, session_id)
        return {"accepted": True, "busy": state.busy, "pregen": True}

    # 分支消费（板块契约 2026-08-30）: 选项带同响应分支 → 立即展示分支内容
    # （零等待——分支已在场景响应里, 无需再调 LLM; 返回 scene 由前端直接渲染）
    # + 分支播放时预生成下一板块（输入固定"（继续）"）——读完点继续零等待
    if (state.scene_obj is not None and state.scene_obj.branches
            and text in state.scene_obj.branches):
        branch = state.scene_obj.branches[text]
        _log_scene(state, char_id, session_id, picked=text)   # 场景（含 branches）落库
        state.scene_obj = BondScene(
            paragraphs=branch,
            background=state.scene_obj.background,
            place=state.scene_obj.place,
        )
        state.scene = state.scene_obj.to_dict()
        state.scene_logged = True    # 分支是场景一部分（已随场景落库）——继续时不重复落
        # prev_emotions 由标注 worker 回填后统一更新（骨架无 emotion, 2026-09-02）
        # 分支段落可能是骨架（branches 未标注）→ 入队异步标注（与主场景同队列）
        _enqueue_annotate(state, state.scene_obj)
        # 2026-09-02 修复: 分支渲染后前端不轮询 status（turn 直接返回 scene）——
        # 若返回未标注骨架, 立绘 default 且标注完成无补切通道; 同步短等标注
        # （修复后标注 ~1-3s, 上限 8s 兜底——标注层失败也有 _fallback_fill 保证就绪）
        _wait_annotated(state, timeout=8.0)
        state.scene = state.scene_obj.to_dict()
        # 分支播放时预生成下一板块（choices_used 已在场景生成时计过, 这里不加）
        _pregenerate(state, char_id, session_id)
        return {"accepted": True, "busy": state.busy, "branch": True,
                "scene": state.scene}

    # append-only 事件流: 当前展示场景在玩家裁决时落库（带 picked）;
    # 纯叙事场的"（继续）"是推进指令不是内容裁决 → picked=None（与预生成消费一致）
    _log_scene(state, char_id, session_id,
               picked=None if text == "（继续）" else text)
    _generate(state, char_id, session_id, text)
    return {"accepted": True, "busy": True}


def bond_status(char_id: str, session_id: str) -> dict:
    """轮询: 生成状态 + 最新场景（前端按 round 去重）+ 终结标记 + 名字牌信息
    + emo_version（异步标注补标版本——前端感知后补切已显示段落的立绘表情）
    + memorial（纪念模式标记 + 立绘 URL——前端进纪念淡入图背景, 退出淡出）。"""
    state = _state(char_id, session_id)
    role = _role_info(char_id)
    return {
        "busy": state.busy,
        "round": state.round,
        "scene": state.scene,
        "error": state.error,
        "completed": state.completed,
        "name": role["name"],
        "club": role["club"],
        "emo_version": state.emo_version,
        # 纪念立绘（方案 A）: in_memorial = 纪念模式中（前端保持图背景）;
        # memorial_img = 图 URL（None = 未就绪/失败 → 纯文字降级）;
        # memorial_img_busy = 生图中（防重/调试可见）
        "in_memorial": bool(state.vn is not None and state.vn.in_memorial),
        "memorial_img": state.memorial_img or None,
        "memorial_img_busy": state.memorial_img_busy,
    }


def _role_info(char_id: str) -> dict:
    """当前角色显示屏信息 {name, club}——前端名字牌（官方: 名字 + 便利屋68）。"""
    try:
        ch = chat._engine(char_id).current_character
        if ch is not None:
            club = ch.profile.get("club") or ch.profile.get("SIG~club") or ""
            return {
                "name": ch.display_name or char_id,
                "club": str(club).split("（")[0].split("(")[0].strip(),
            }
    except Exception:                                # noqa: BLE001 — 取不到降级用 id
        pass
    return {"name": char_id, "club": ""}


def bond_finish(char_id: str, session_id: str) -> dict:
    """剧情终结收尾: 补录最后场景 + vn_exit + session_end + wrapup + digest。"""
    state = _state(char_id, session_id)
    if state.vn is None and state.demo is None:
        return {"completed": False, "error": "剧情未开始"}
    if state.busy:
        return {"completed": False, "busy": True, "error": "剧情生成中"}

    # 收尾前等最后场景标注就绪（2026-09-02）——append-only 落库缺 emotion
    # 不可补; 标注 worker 独立线程, 短等（失败兜底也回填 → 必达; 超时宁缺勿错）
    if not _scene_emotions_ready(state):
        deadline = time.time() + 8.0
        while time.time() < deadline and not _scene_emotions_ready(state):
            time.sleep(0.05)
        if not _scene_emotions_ready(state):
            logger.warning("bond_finish 等待标注超时, 场景可能缺 emotion: %s/%s",
                           char_id, session_id)

    # 最后场景（is_end / closing）: 玩家无裁决 → picked=None
    _log_scene(state, char_id, session_id, picked=None)
    try:
        # vn_exit 带剧情完成标志（2026-09-01）: completed = 剧情真正走完
        # （story_end / 兜底收尾）; False = 玩家中途退出——收尾链据此分支
        # （中断不脑补收尾话 + 不 digest——记忆只反映完整剧情段）
        _store().append_marker(char_id, session_id, M_VN_EXIT,
                               {"completed": state.completed})
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
    reason = state.reason
    threading.Thread(target=_wrapup,
                     args=(char_id, session_id, reason, state.completed),
                     daemon=True).start()
    return {"completed": True}


# ---------------------------------------------------------------------------
# 内部: 生成 / 落库 / 收尾
# ---------------------------------------------------------------------------

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
    state.error = ""

    def run():
        try:
            with chat._lock(char_id):
                state.round += 1
                if state.demo is not None:
                    # 演示模式: 弹预设场景; 剧本耗尽 → closing 收尾（剧情必须终结）
                    scene_dict = state.demo.pop(0) if state.demo else None
                    scene = (BondScene.from_dict(scene_dict) if scene_dict
                             else BondScene(paragraphs=list(_CLOSING_PARA),
                                            is_end=True))
                else:
                    scene = state.vn.send_vn_scene(
                        user_input, system_note=_system_note(state), annotate=False,
                        on_memorial_prompt=_make_memorial_cb(
                            state, char_id, session_id),
                    )
                    if state.round > _FORCE_AFTER and not scene.is_end:
                        # 超限强制收尾（CLI force_after 语义——剧情必须终结）
                        scene = BondScene(
                            paragraphs=list(_CLOSING_PARA), is_end=True)
                state.scene_obj = scene
                state.scene = scene.to_dict()
                state.scene_input = user_input
                state.scene_logged = False
                if scene.is_end:
                    state.completed = True
                # 选项配额（供下一场 system_note 参考）
                if scene.choices:
                    state.choices_used += 1
                # prev_emotions（情绪单调注记）由标注 worker 回填后统一更新——
                # 骨架无 emotion（2026-09-02）, 生成时取只会得到空列表
                _log_scene_meta(state, char_id, session_id, scene)
                # 两遍式 C 异步标注: 骨架先显示, emotion 解析入队补标（不阻塞玩家）
                _enqueue_annotate(state, scene)
                state.fail_count = 0           # 生成成功 → 失败计数清零
        except (SceneLoopError, ValueError) as e:
            # 模型连语义校验都过不了 → 偶发失败先给重试机会（2026-09-02:
            # 一败就 closing 会把偶发 JSON 错误变成"剧情突然结束"——上一场保持
            # 在屏, error 置位, 前端显示重试按钮重新 submit; 连续 3 次失败才
            # 中断收场（宁缺勿错, 剧情必须终结））
            logger.warning("bond 场景生成失败 (%s/%s) 第 %d 次: %s",
                           char_id, session_id, state.fail_count + 1, e)
            state.error = str(e)
            state.fail_count += 1
            if state.fail_count > MAX_GEN_FAILURES:
                closing = BondScene(paragraphs=list(_CLOSING_PARA),
                                    is_end=True)
                state.scene_obj = closing
                state.scene = closing.to_dict()
                state.scene_logged = False
                state.completed = True
        finally:
            state.busy = False
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

    threading.Thread(target=run, daemon=True).start()


def _pregenerate(state: BondState, char_id: str, session_id: str) -> None:
    """Storyloom bridge 式预生成: 纯叙事场（无 choices）渲染完成即提前生成下一场。

    输入固定"（继续）"——玩家点继续时已就绪, 体感零等待; 生成失败降级
    （清 pregen, 玩家点击时走正常生成路径, 不阻断剧情）。预生成场景同样计入
    选项配额/表情统计（供后续 system_note 参考）。演示模式不预生成（即时弹出）。
    入口原子抢占（2026-09-02 修复: 与 _generate 同款锁——防并发双启动）。
    """
    with state._lock:
        if state.busy or state.pregen_scene is not None \
                or state.demo is not None or state.vn is None:
            return
        state.busy = True

    def run():
        try:
            with chat._lock(char_id):
                scene = state.vn.send_vn_scene(
                    "（继续）", system_note=_system_note(state), annotate=False,
                    on_memorial_prompt=_make_memorial_cb(
                        state, char_id, session_id))
                state.pregen_obj = scene
                state.pregen_scene = scene.to_dict()
                state.pregen_input = "（继续）"
                if scene.choices:
                    state.choices_used += 1
                state.prev_emotions = [p.get("emotion", "") for p in scene.paragraphs
                                       if isinstance(p, dict)]
                # 预生成场景同样异步标注（与主场景同一队列串行, 玩家消费时表情就绪）
                _enqueue_annotate(state, scene)
        except Exception as e:                     # noqa: BLE001 — 预生成失败降级
            logger.warning("bond 预生成失败（降级为点击时再生成）: %s", e)
            state.pregen_obj = None
            state.pregen_scene = None
            state.pregen_input = ""
        finally:
            state.busy = False

    threading.Thread(target=run, daemon=True).start()


def _enqueue_annotate(state: BondState, scene: BondScene) -> None:
    """场景入队异步标注（两遍式 C: emotion 解析挪出玩家等待路径）。

    骨架先显示 → 标注队列单 worker 串行补标（标注 LLM 调用不持 chat._lock——
    并发 API 调用可接受; 写回持短锁 + 对象身份检查——场景已被替换则丢弃,
    异步线程绝不覆盖比它新的状态）。
    """
    if state.demo is not None or state.vn is None:
        return
    if not state.vn._lexicon_keys:
        return                                      # 无词表 → 无需标注
    if not any(not p.get("emotion") for p in scene.paragraphs
               if isinstance(p, dict)):
        return                                      # 骨架已全带 emotion → 跳过
    if state._anno_queue is None:
        state._anno_queue = queue.Queue()
    state._anno_queue.put(scene)
    if not state._anno_started:
        state._anno_started = True
        threading.Thread(target=_anno_worker, args=(state,), daemon=True).start()


def _fallback_fill(scene: BondScene) -> None:
    """标注兜底（2026-09-02）: 空 emotion 段落强制回填 nomal。

    保险网——fill_scene_emotions 正常路径已全量回填/延续（幂等）; 若标注层
    异常漏网（段落仍无 emotion）→ 强制兜底, 保证推进门控就绪**恒可达**
    （剧情必须能推进; 失败只影响表情精度, 宁缺勿错）。
    """
    for group in [scene.paragraphs, *scene.branches.values()]:
        for p in group:
            if isinstance(p, dict) and not (p.get("emotion") or "").strip():
                p["emotion"] = "nomal"


def _anno_worker(state: BondState) -> None:
    """标注队列单 worker: 串行补标场景（正文 + branches）, 写回带防竞态检查。

    写回规则: scene_obj 仍是 state.scene_obj（当前展示）或 state.pregen_obj
    （预生成待消费）→ 序列化更新 + emo_version++（前端补切表情）;
    否则（场景已被推进/替换）→ 丢弃（标注结果作废, 不污染新场景）。
    2026-09-02: 骨架 emotion 已移交标注层——回填后同步 prev_emotions
    （当前展示场景的情绪谱, 供下一场 system_note 防单调; 预生成场景不更新——
    它尚未展示, prev 语义 = 上一场）。fill 异常 → _fallback_fill 强制兜底
    （门控就绪恒可达, 剧情必须能推进）。
    """
    while True:
        scene = state._anno_queue.get()
        if scene is None:
            break
        try:
            state.vn.fill_scene_emotions(scene)     # 标注 LLM（不持锁）
        except Exception as e:                       # noqa: BLE001 — 标注失败兜底
            logger.warning("bond 异步标注失败（兜底延续）: %s", e)
        _fallback_fill(scene)                        # 保险网: 空 emotion 强制 nomal
        with state._lock:
            if state.scene_obj is scene:
                state.scene = scene.to_dict()
                state.emo_version += 1
                state.prev_emotions = [p.get("emotion", "")
                                       for p in scene.paragraphs
                                       if isinstance(p, dict)]
            elif state.pregen_obj is scene:
                state.pregen_scene = scene.to_dict()
                state.emo_version += 1
            # 已被替换/消费后又被推进 → 丢弃（异步不覆盖新状态）
        state._anno_queue.task_done()


def _log_scene(state: BondState, char_id: str, session_id: str, picked) -> None:
    """补录当前场景事件（append-only: 玩家裁决/收尾时落, 带 picked）。

    与 CLI 落库格式一致: {**scene.to_dict(), "input": 本场输入, "picked": 玩家裁决}
    ——回放兼容（filter_bond → BondScene.from_dict + input/picked）。
    """
    if state.scene_logged or state.scene_obj is None:
        return
    scene = state.scene_obj
    if scene.memorial_exit:
        sub = "memorial_exit"
    elif scene.memorial_prompt:
        sub = "memorial_enter"
    else:
        sub = "story_end" if scene.is_end else "story_scene"
    try:
        _store().append_event(char_id, session_id, make_event(
            "bond", sub,
            {**scene.to_dict(), "input": state.scene_input, "picked": picked}))
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断
        logger.warning("事件流 bond 写入失败: %s", e)
    state.scene_logged = True


def _log_scene_meta(state: BondState, char_id: str, session_id: str,
                    scene: BondScene) -> None:
    """每场 marker 落库: 纪念子模式 + vn_state 恢复点（与 CLI 对齐）。"""
    try:
        if scene.memorial_prompt:
            _store().append_marker(char_id, session_id, M_MEMORIAL_ENTER,
                                   {"reason": state.reason})
        elif scene.memorial_exit:
            _store().append_marker(char_id, session_id, M_MEMORIAL_EXIT)
        vn = state.vn
        visual = (vn.director.state.to_dict()
                  if vn is not None and vn.director is not None else {})
        _store().append_marker(char_id, session_id, M_VN_STATE, {
            "round": state.round, "seed": state.scene_input, "visual": visual})
    except Exception as e:                           # noqa: BLE001 — 写失败降级不阻断
        logger.warning("事件流 marker 写入失败: %s", e)


def _system_note(state: BondState) -> str | None:
    """本轮系统注记（只进 context 不入历史）: 纪念模式 / 选项配额 / 表情单一提醒 /
    收尾提醒 / 上限建议。多条聚合为多行（每条一行）。"""
    vn = state.vn
    if vn is not None and vn.in_memorial:
        return (
            "（系统）当前处于**纪念模式**——纪念场景已结束, 本场请输出"
            " memorial_exit 动作回到 bond（可选过渡文字, 不要输出其他动作）。\n"
            f"可用动作 schema:\n{vn.memorial_exit_schema()}"
        )
    notes: list[str] = []
    # 选项配额（整段剧情 2~3 次——每场给选项的疲劳问题）: 已用 X/3
    if state.choices_used >= 3:
        notes.append(
            f"（系统）本段剧情已用 {state.choices_used}/3 个选项——已到配额上限,"
            "后续场次一律省略 choices（纯叙事推进, 系统自动衔接下一场）。"
        )
    elif state.choices_used >= 1:
        notes.append(
            f"（系统）本段剧情已用 {state.choices_used}/3 个选项——尽量少给,"
            f"只在真正需要老师表态的关键时刻再给（最多还能给 {3 - state.choices_used} 个）。"
        )
    # 表情单一提醒（上一场 ≥3 个单元但 emotion 全同 → 提示 LLM 情绪变化）
    uniq = {e for e in state.prev_emotions if e}
    if len(state.prev_emotions) >= 3 and len(uniq) <= 1:
        notes.append(
            "（系统）上一场所有单元都是同一 emotion——若剧情有情绪起伏,"
            "请随情绪变化切换 emotion 并切新单元（不要整场一个表情）。"
        )
    if state.round == _REMIND_ROUNDS:
        notes.append(
            f"（系统）剧情已推进 {state.round} 轮，剩余约 {_END_ROUNDS - state.round} 轮。"
            "请开始把剧情向结尾收束——感情到位、约定达成、道别告别的时刻"
            "就改用 story_end 动作收尾结束剧情，不要再开新场景"
            "不过也谨记这只是中段提示，你并不需要匆匆结尾，但是建议开始铺垫"
        )
    if state.round == _END_ROUNDS:
        notes.append(
            "（系统）已达剧情篇幅上限。本轮请改用 story_end 动作收尾"
            "结束剧情——收尾场景只有 paragraphs，不再输出选项。"
        )
    return "\n".join(notes) if notes else None


def _wrapup(char_id: str, session_id: str, reason: str, completed: bool) -> None:
    """剧情收尾后的手机收尾: 自动触发一轮, AI 就这段剧情回几段话 + digest。

    收尾话 = agent_turn（system_note 注入, record_input=False——不落假 player 事件,
    只落 assistant 回复）; 前端轮询 events_after 自然拉到收尾气泡。
    completed=True（剧情 story_end 自然结束/兜底收尾）: 话术按"完整剧情"收尾 +
    async_digest（提炼 + 好感结算——digest 唯一触发点）。
    completed=False（玩家中途退出）: 话术明确"剧情只进行到一半"（防 LLM 脑补
    未发生的剧情结果）+ **不 digest**（记忆只反映完整剧情段——中断不提炼,
    未消化的 mmt 留到下次完整剧情段一起消化, 增量幂等）。
    演示模式（state.demo）: 预设收尾话落 mmt 事件, 跳过 agent_turn 和 digest（不调 LLM）。
    """
    state = _state(char_id, session_id)
    if state.demo is not None:
        try:
            _store().append_event(char_id, session_id, make_event(
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
    reason_suffix = f"（起因: {reason}）" if reason else ""
    if completed:
        note = (
            "（系统）羁绊剧情刚刚结束，你们回到了 MomoTalk 手机聊天。"
            f"请以{char.display_name}的身份，就刚才这段羁绊剧情{reason_suffix}，"
            "在手机上回复老师几句话作为收尾——自然、简短、像真实的手机消息。"
            "只使用 mmt_chat 动作，不要再次触发羁绊剧情。"
        )
    else:
        # 中途退出: 剧情只进行到一半——明示中断, 防止 LLM 依据触发起因
        # 脑补"剧情结果"（实测: 收尾话把未发生的对决总结成"玩得很开心"）
        note = (
            "（系统）羁绊剧情**只进行到一半**就中断了——老师中途离开了，"
            f"你们没有完成这段剧情{reason_suffix}。"
            f"请以{char.display_name}的身份，在手机上给老师发一条简短的告别消息"
            "（如「下次再继续」）——**不要总结剧情结果、不要描述没有发生的剧情**。"
            "只使用 mmt_chat 动作，不要再次触发羁绊剧情。"
        )
    try:
        with chat._lock(char_id):
            engine.agent_turn("（自动收尾）", system_note=note, record_input=False)
    except Exception as e:                           # noqa: BLE001 — 收尾失败不阻塞
        logger.warning("羁绊剧情收尾回复失败: %s", e)
        # 兜底收尾话（2026-08-30）: LLM 收尾失败 → 本地预设结语落库——保证
        # 结束回 MMT 时玩家一定看得到结语（之前失败时静默, "强硬回 MMT"）
        try:
            if completed:
                fallback = "（今晚的事……我会好好记住的。老师，谢谢你。）"
            else:
                fallback = "（……老师突然就走了。嗯，剧情下次再继续吧。）"
            _store().append_event(char_id, session_id, make_event(
                "mmt", "mmt_chat",
                {"player": "", "reply": fallback}))
        except Exception as e2:                      # noqa: BLE001
            logger.warning("兜底收尾话写入失败: %s", e2)
    if completed:
        engine.async_digest()             # 仅完整剧情消化（中断不提炼）
