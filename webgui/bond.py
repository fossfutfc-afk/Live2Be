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
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from contract import CHARACTER_SENSEI, NON_PICKS, pick_insert_index
from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError
from core.media.gallery import GalleryStore
from core.momotalk import load_brain_segment
from core.session.events import (
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_VN_ABANDON,
    M_VN_EXIT,
    M_VN_STATE,
    make_event,
)
from core.session.maintenance import (
    abandon_open_attempts,
    abandon_opens_except,
    abandoned_ranges,
    exclude_abandoned,
)
from core.session.renderer import render_bond_scene_text, window_messages
from core.ui.vn_cli import _build_director, _trigger_title
from llm.image_gen import ImageGenerator, collect_ref_images
from webgui import chat

logger = logging.getLogger(__name__)


def _ms_since(t0: float) -> int:
    """自 t0（time.monotonic）起的毫秒（计时埋点, EXEC_BOND_LATENCY §6.1）。"""
    return int((time.monotonic() - t0) * 1000)

#: 收尾注记轮数（与 CLI 默认一致）: _REMIND_ROUNDS 起给收束提示,
#: _END_ROUNDS 起每轮强制收尾注记（_system_note）——**不再有超限伪收场**
#: （2026-09-09 语义修正: 伪收场会把中断伪装成完成, 触发 digest/完整收尾话/
#: 自动 finish——见 _generate 失败中止注释）; 模型持续不收尾 = 玩家可离开
#: （中场退出, 重进续写）, 不伪终结。记录流 v2 里注记指向 `stage=end` 记录。
_REMIND_ROUNDS = 30
_END_ROUNDS = 50
#: 程序兜底 closing 文案（demo 剧本耗尽收尾 / CLI 兜底用; 2026-09-09 起
#: webgui 生成失败路径不再用它——见 _generate）
_CLOSING_TEXT = "（夜色渐深，这一章的羁绊剧情就此落下帷幕。）"
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
class ChoiceCandidate:
    """候选支草稿（DESIGN_CHOICE_PREGEN §1, N2a）: 一个候选项对应的 fork 引擎。

    纯内存态: choices 板展示即 spawn（每个候选 fork 引擎后台预生成"选了它
    之后的下一板", 同步标注——后台不可见）; 玩家裁决命中且 ready → 消费提升
    （N2b: 切主引擎 + 提升为下一板）; 未选/换板 → 作废 GC（零落库, 事件流
    无感知——append-only 唯一真源不变）。
    """

    picked: str                                  # 对应 choices 的选项文本
    engine: BondStoryEngine | None = None        # fork 草稿引擎（独立历史/链）
    scene_obj: BondScene | None = None           # 就绪后的下一板场景
    status: str = "generating"                   # generating | ready | failed


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
    completed: bool = False             # 剧情已终结（is_end 自然收尾 → True）
    finished: bool = False              # finish 已执行（幂等, 2026-09-09 审计:
                                        # 重复 finish 曾刷重复 vn_exit/wrapup/兜底话）
    chapter_title: str = ""
    # 生成失败重试（2026-09-02: 偶发 JSON 失败不再一败就 closing——前 3 次失败保留
    # 上一场在屏 + 置 error, 前端显示重试按钮重新生成; 超限 = 中止态不伪收场, 见 _generate）
    fail_count: int = 0
    # 入口预热（EXEC_BOND_LATENCY P1 2026-09-05）: 触发轮结束即生成首场暂存
    # （staged）——玩家点击时 adopt。staged 期间**不落 vn_enter marker**（防未点击
    # 被 session_status 推导 in_vn / 前端自动拽入 VN）; adopt 时补落, 事件流时序
    # （触发 → vn_enter → 首场裁决落库）天然正确。点击前玩家又聊（新 mmt 事件）
    # → staged_seq 失配 → 丢弃重建, 首场反映最新上下文。
    staged_seq: int | None = None    # 非 None = 预热态; 值 = 预热时最后一条 mmt 事件 seq
    vn_enter_written: bool = False   # vn_enter marker 已落（首进/adopt 时置 True）
    # 计时埋点（§6.1）: 预热起点（monotonic）——adopt/预热就绪时算 latency。
    # 只随预热态存活: 丢弃重建（pop 新对象）/回放/普通首进 = 0, 天然无脏值
    t_staged: float = 0.0
    # 中断接入（2026-09-07）: 中断重进（无内存态）→ 回放已记录前缀（narrative-ized
    # 场景队列, 逐场本地推进, 0 LLM）; 队列尽 → 交棒常规 live 路径（promotion/生成）。
    # 回放场景来自事件流（已落库, scene_logged=True 不重复落）; 最后一场展示即
    # 预生成续写（读屏期间完成, handoff 零等待）。
    replay_scenes: list[dict] | None = None    # None = 非回放; [] = 队列尽待交棒
    # Storyloom bridge 式预生成（2026-08-30）: 纯叙事场（无 choices）渲染完成即
    # 提前生成下一场（输入固定"（继续）"）——玩家点继续时已就绪, 体感零等待
    pregen_obj: BondScene | None = None
    pregen_scene: dict | None = None
    pregen_input: str = ""
    # SceneStream P1.5 候选支池（DESIGN_CHOICE_PREGEN §1, N2a）: choices 板
    # 展示即 spawn——每候选项一个 fork 草稿引擎后台预生成（不占 busy）;
    # 裁决命中且就绪 → N2b 消费提升; 新板/换板 → _spawn_candidates 起点清池
    choice_candidates: list = field(default_factory=list)
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
    # place 标注 lane（DESIGN_BOND_CONTRACT_V2 §7, P3b-1 2026-09-07）: 与 emotion
    # 双路并行——各自队列/消费者; 推进门控 = 双路齐; 锚点写回 payload 变更句
    # （place 键, 稀有）。场景就绪标记挂 scene 对象（_place_done——判定完成即
    # 含 keep, gate 恒可达）; 分支反应段/无词表/纪念退出 = 视为就绪。
    _place_queue: "queue.Queue | None" = field(default=None, repr=False)
    _place_started: bool = field(default=False, repr=False)
    _anno_thread: "threading.Thread | None" = field(default=None, repr=False)
    _place_thread: "threading.Thread | None" = field(default=None, repr=False)
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
    """懒初始化生图器。未配 IMAGE_API_KEY → None = 纪念降级纯文字。

    本地 diffusers 兜底已于 2026-09-10 移除（出图"不像人类"）——只有 APIYI 一条路。
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
        eng = chat._engine(char_id)
        char = eng.current_character
        name = char.display_name if char is not None else "角色"
        hints = eng.char_loader.load_illustration(char_id)   # illustration.yml（可选）
        img = gen.generate(prompt, ref_images=collect_ref_images(char_id),
                           character_name=name,
                           character_hint=hints.get("character_hint", ""),
                           halo_hint=hints.get("halo_hint", ""))
        logger.info("纪念立绘: %dx%d %.1fs %s", img.width, img.height,
                    img.elapsed_s, img.path.name)
        sid = GalleryStore(_store().data_root, world_id=_store().world_id).write(
            char_id, prompt, session_id, img.path, width=img.width, height=img.height)
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
# 回放接口（2026-09-07, 纯读）: 会话内已记录的羁绊剧情逐场回放
# 原料 = 事件流里的 bond 事件——落库即终态（裁决时落库 + 门控保证标注就绪,
# 段落自带 emotion）, 与 live 渲染同源, 0 LLM 可完整回放。
# 消费方: ① 回放 UI ② 中断剧情"回放前缀 + LLM 后补"（attempt 分段复用）
# ---------------------------------------------------------------------------

def replay_attempts(char_id: str, session_id: str = "") -> list[dict]:
    """事件流 → 按 vn_enter 分段的回放列表（纯读, 幂等, 不碰状态机）。

    返回: [{from_seq, title, completed, interrupted,
            scenes: [{seq, input, picked, scene}]}]
      scene = 事件 payload 去 input/picked 的渲染字段——与 live BondVN
      renderScene 消费的 scene 同构（背景/表情/分支齐全）。
    分段规则: vn_enter 开新段; vn_exit 关段（completed 取 payload——False 即
    主动中断）; 段未关即遇新 vn_enter / 流尾 → interrupted=True。
    """
    try:
        evs = _store().events(char_id, session_id)
    except Exception:                                # noqa: BLE001 — 读失败空列表
        return []
    attempts: list[dict] = []
    cur: dict | None = None

    def close_interrupted():
        nonlocal cur
        if cur is not None:
            cur["interrupted"] = True
            attempts.append(cur)
            cur = None

    def open_attempt(from_seq: int, title: str):
        nonlocal cur
        close_interrupted()                 # 新段开 = 旧段未收尾 → 中断
        cur = {"from_seq": from_seq, "title": title, "completed": False,
               "interrupted": False, "scenes": []}

    for e in evs:
        t = getattr(e, "type", None)
        if t == "marker":
            if e.subtype == "vn_enter":
                open_attempt(e.seq,
                             str((e.payload.get("chapter_title") or "").strip()))
            elif e.subtype == "vn_exit" and cur is not None:
                cur["completed"] = bool(e.payload.get("completed"))
                cur["interrupted"] = not cur["completed"]
                attempts.append(cur)
                cur = None
        elif t == "bond":
            if cur is None:                 # 兼容旧事件: 无 vn_enter 直接开段
                open_attempt(e.seq, "")
            payload = e.payload or {}
            scene = {k: v for k, v in payload.items()
                     if k not in ("input", "picked")}
            cur["scenes"].append({
                "seq": e.seq,
                "input": str(payload.get("input") or ""),
                "picked": payload.get("picked"),
                "scene": scene,
            })
    close_interrupted()                     # 流尾未关段 → 中断
    return attempts


# ---------------------------------------------------------------------------
# 中断接入（2026-09-07）: 中断剧情重进 = 回放已记录前缀 + LLM 后补
#   无内存态 + 有内容的未完成段 → 逐场回放事件流里已落库的场景（0 LLM）;
#   队列尽 → 交棒常规 live 路径。语义: "从头开始播放已有的半截剧情,
#   后续剧情 LLM 生成后补"——确定性前缀, 生成只发生在断点之后。
# ---------------------------------------------------------------------------

def _pending_in_vn(char_id: str, session_id: str) -> bool:
    """事件流视角: 最近一个 vn_enter 之后没有 vn_exit/vn_abandon（中断在押, in_vn）。"""
    try:
        last_enter = last_exit = -1
        for e in _store().events(char_id, session_id):
            if getattr(e, "type", None) == "marker":
                if e.subtype == "vn_enter":
                    last_enter = e.seq
                elif e.subtype in ("vn_exit", "vn_abandon"):
                    last_exit = e.seq
        return last_enter > last_exit
    except Exception:                                # noqa: BLE001 — 读失败按无在押
        return False


def _narrativize(scene: dict, picked) -> dict:
    """回放场景叙事化: 主段落 + 所选分支段落顺接, 去掉选项/分支结构——
    前端只看到"段落流 + 继续", 与纯叙事场同交互（选项跟随记录自动隐含）。

    记录流 v2（P0-6）: 板带 `records` 时**裁决物化**（把 `老师：X` 插回群首,与
    `BondScene.from_dict`/`render_records` 同一语义、同一插入位置）——v1 的
    branches 顺接保持不变（旧档冻结）。
    """
    out = dict(scene or {})
    out.pop("choices", None)
    out.pop("branches", None)
    paras = [dict(p) for p in (out.get("paragraphs") or []) if isinstance(p, dict)]
    records = scene.get("records") if isinstance(scene, dict) else None
    pick_text = str(picked).strip() if isinstance(picked, str) else ""
    if pick_text and pick_text not in NON_PICKS and isinstance(records, list) and records:
        idx = pick_insert_index(records, (scene or {}).get("choices") or ())
        paras.insert(min(idx, len(paras)),
                     {"text": pick_text, "speaker": CHARACTER_SENSEI})
    elif picked:
        br = (scene or {}).get("branches") or {}
        if isinstance(br, dict) and picked in br:
            paras += [dict(p) for p in br[picked] if isinstance(p, dict)]
    out["paragraphs"] = paras
    return out


def _interrupted_replay_queue(char_id: str, session_id: str) -> tuple[list[dict], int] | None:
    """最新一条"有内容的未完成段" → (narrative-ized 场景列表, 段 enter_seq)。

    从段尾向前找 interrupted 且有 scenes 的段; 空壳重启段（0 场景——旧 bug 的
    重复 vn_enter 产物）自动跳过, 回退到更早的有内容段（如 seq12 场景 + seq18/21
    空壳）; **废弃段（vn_abandon 宣告, 被新章压掉）跳过**——档案在回放列表,
    不再自动续。无 → None（现场生成路径）。enter_seq 供"保留本段、压掉其余
    open"的定向废弃（防续写事件归属到更新的空壳段）。
    """
    try:
        ranges = abandoned_ranges(_store().events(char_id, session_id))
    except Exception:                                # noqa: BLE001 — 读失败无区间
        ranges = []
    for at in reversed(replay_attempts(char_id, session_id)):
        if at["interrupted"] and at["scenes"] and not any(
                a <= at["from_seq"] <= b for a, b in ranges):
            return ([_narrativize(s["scene"], s["picked"]) for s in at["scenes"]],
                    at["from_seq"])
    return None


def _start_replay(state: BondState, replay_q: list[dict],
                  char_id: str, session_id: str) -> dict:
    """进入回放模式: 引擎就绪（handoff 用, 历史=事件流窗口）+ 首场入屏。

    回放场景 scene_logged=True（事件流已落库, 不重复落）; 若队列只有一场（或
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
        _evs = exclude_abandoned(_store().events(char_id))
        _win = window_messages(_evs)
        if _win:
            vn._history = _win                # 前缀(含已记录场景)+ 触发前对话
    except Exception:                                # noqa: BLE001 — 灌窗失败不阻断
        pass
    state.vn = vn
    state.vn_enter_written = True             # 事件流已有该段 vn_enter（不重复落）
    state.replay_scenes = list(replay_q)
    try:
        from webgui.routers.bond import warm_render
        warm_render(char.character_id)
    except Exception:                                # noqa: BLE001 — 预热失败降级
        pass

    first = state.replay_scenes.pop(0)
    state.scene_obj = BondScene.from_dict(first)
    state.scene_obj._place_done = True    # 回放场景来自事件流（视觉键已定格）——不占 lane
    state.scene = state.scene_obj.to_dict()
    state.round = 1
    state.scene_logged = True                 # 已落库——回放不重复落
    if not state.replay_scenes:
        # 单场（或最后一场）: 续写在读屏期间预生成, busy=True 不阻塞回放推进
        _pregenerate(state, char_id, session_id)
    return {"accepted": True, "busy": state.busy, "resumed": True,
            "replay": True, "chapter_title": state.chapter_title}


# ---------------------------------------------------------------------------
# 公开 API（路由层调用）
# ---------------------------------------------------------------------------

def _last_mmt_seq(char_id: str, session_id: str) -> int:
    """事件流中最后一条 **mmt 事件** 的 seq（预热新鲜度基准）。

    只计 mmt 事件（玩家对白/触发轮）——staged 预热自身的后续写入
    （vn_state 等 marker / bond 事件, 产生于快照之后）不参与判定, 否则
    自生成标记会把预热误判为过期而丢弃重建。
    """
    try:
        last = 0
        for e in _store().events(char_id, session_id):
            if getattr(e, "type", None) == "mmt":
                last = e.seq
        return last
    except Exception:                                # noqa: BLE001 — 读失败保守
        return 0


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

    # ── 预热 adopt（staged 态 + 玩家点击 / 再次 staged 调用）────────
    if state.vn is not None and state.staged_seq is not None:
        if _last_mmt_seq(char_id, session_id) != state.staged_seq:
            # 预热后玩家又聊过（新 mmt 事件）/ 新触发轮 → 预热上下文过期, 丢弃重建
            logger.info("bond 预热态过期（mmt seq %s ≠ %s）, 丢弃重建: %s/%s",
                        state.staged_seq, _last_mmt_seq(char_id, session_id),
                        char_id, session_id)
            _bonds.pop((char_id, session_id), None)
            state = _state(char_id, session_id)
        else:
            # adopt: 补落 vn_enter marker（触发事件之后、首场裁决落库之前——时序正确）
            if not state.vn_enter_written:
                try:
                    _store().enter_vn(char_id, session_id, state.chapter_title)
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
            _prewarm_cache_delete(char_id)     # adopt 消费（首场已进玩家视野）
            if state.busy:
                # 预热生成仍在途 → 前端轮询等待（resumed=False → 章节等待卡可见）
                return {"accepted": True, "busy": True, "resumed": False,
                        "chapter_title": state.chapter_title}
            return {"accepted": True, "busy": False, "resumed": True}
    elif state.vn is not None or state.demo is not None:
        # 计时埋点（§6.1）: 内存态续玩（resumed）——即时可用
        logger.info("bond_click resumed %s/%s busy=%s",
                    char_id, session_id, "y" if state.busy else "n")
        # chapter_title 必带（2026-09-09: resumed/adopt 就绪同样展示章节标题屏）
        return {"accepted": True, "busy": state.busy, "resumed": True,
                "chapter_title": state.chapter_title}
    if state.busy:
        # 生成在途（P1: busy = 正在生成——让前端进入轮询, 不再报错）
        logger.info("bond_click busy_wait %s/%s", char_id, session_id)
        return {"accepted": True, "busy": True, "resumed": False}

    # ── 中断接入（2026-09-07）: 无内存态 + 有内容的未完成段 → 回放前缀 ──
    # （"从头开始播放已有半截剧情, 后续 LLM 后补"; staged 预热 = 新触发轮,
    # 不进回放——走下方现场构造续在押段或新段）
    if not staged:
        replay = _interrupted_replay_queue(char_id, session_id)
        if replay is not None:
            replay_q, keep_enter = replay
            # 定向废弃: 保留被回放段, 压掉其余 open（含空壳）——否则续写事件
            # 会按 vn_enter 归属追加到更新的空壳段, 分段/记忆归属错乱
            try:
                abandon_opens_except(_store(), char_id, session_id, keep_enter)
            except Exception as e:                   # noqa: BLE001 — 宣告失败降级
                logger.warning("回放前废弃宣告失败: %s", e)
            # 计时埋点（§6.1）: 中断回放入口（本地 0 LLM 展示, handoff 生成另计）
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
        title = _trigger_title(engine)

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
            _evs = exclude_abandoned(_store().events(char_id))
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
        try:
            _store().enter_vn(char_id, session_id, title)
            state.vn_enter_written = True
        except Exception as e:                       # noqa: BLE001 — 写失败降级不阻断 VN
            logger.warning("事件流 vn_enter 写入失败: %s", e)
    else:
        # 新章节触发轮（staged 预热）: 压掉旧 open 在押段——vn_abandon 宣告
        # （2026-09-07, maintenance）: 之后 openChat 不再自动拽入旧中断段,
        # 窗口/digest 按废弃区间过滤; 幂等（已关段自动跳过）
        try:
            abandon_open_attempts(_store(), char_id, session_id)
        except Exception as e:                       # noqa: BLE001 — 宣告失败降级
            logger.warning("旧在押段废弃宣告失败: %s", e)
        state.staged_seq = _last_mmt_seq(char_id, session_id)
        state.t_staged = time.monotonic()            # 计时埋点（§6.1）: 预热起点
        logger.info("bond_prewarm_start %s/%s title=%r",
                    char_id, session_id, title)

    # ── 跨重启预热缓存命中（2026-09-09）────────────────────────
    # 首场曾生成但未裁决/未 adopt 即中断（进程重启, 内存 staged 丢失）→
    # 磁盘旁路缓存（soul/prewarm.json, 非真源——LLM 不读, 裁决才落库）直接
    # 作为首场落地, 0 LLM。并发双开在 573 锁块被 skip（vn 已建）→ 本段单路。
    if not staged and state.demo is None and state.scene_obj is None:
        cache = _prewarm_cache_load(char_id, session_id)
        if cache is not None:
            scene_c, input_c, title_c = cache
            _prewarm_cache_delete(char_id)          # 命中即消费（旧首场不残留）
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
                          t0=time.monotonic(), save_cache=False)
            logger.info("bond_cache_hit %s/%s title=%r",
                        char_id, session_id, title_c or title)
            return {"accepted": True, "busy": False, "resumed": True,
                    "chapter_title": title_c or title or "羁绊剧情"}

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
        _store().enter_vn(char_id, session_id, state.chapter_title)
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
    if scene.memorial_exit:
        return True
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
    if not scene.memorial_exit:
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
            state.scene = state.scene_obj.to_dict()
            state.round += 1
            state.scene_logged = True          # 事件流已落库——回放不重复落
            if not state.replay_scenes:
                # 最后一场入屏 → 续写预生成（读屏期间完成, handoff 零等待）
                _pregenerate(state, char_id, session_id)
            # 不带 scene 返回——前端走 waitScene → status（场景经 _resolve_scene
            # 附 background_url/fx, 与分支直返路径同款降级规避）
            return {"accepted": True, "busy": False, "replay": True}
        state.replay_scenes = None             # 交棒: 走下方常规逻辑

    if state.busy:
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
        return gate

    if text == "（继续）" and state.pregen_scene is not None:
        # 预生成消费门（2026-09-08 实机修复）: 预生成场景自身的标注（emotion/place）
        # 未就绪 → 不提升、返回 busy（前端轮询重试）——否则场景被消费后
        # pregen_obj=None, 标注 worker 的身份检查把它当"已替换"丢弃 → 整板无
        # 表情且无补切通道（emo_version 不再涨）→ 表情卡 nomal。
        if not _scene_obj_visual_ready(state, state.pregen_obj):
            return {"accepted": False, "busy": True,
                    "error": "预生成标注中, 稍后自动继续"}
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
            # completed 置位只可能来自**场景 is_end**（自然 story_end / demo 收尾
            # ——digest/完整收尾话的唯一许可; 异常/中止永不置, 2026-09-09 语义）
            state.completed = True
        _log_scene_meta(state, char_id, session_id, state.scene_obj)
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
        return {"accepted": True, "busy": state.busy, "pregen": True}

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
            if nxt.choices:                      # 统计对齐 _pregenerate
                state.choices_used += 1
            state.prev_emotions = [p.get("emotion", "") for p in nxt.paragraphs
                                   if isinstance(p, dict)]
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
        state.scene_logged = True    # 分支是场景一部分（已随场景落库）——继续时不重复落
        # 分支反应段 = 同板延续（地点不重新判定, 主场景的 place 判定已随门控完成）;
        # 置就绪标记 → 不占 place lane（§7 gate 双路语义）
        state.scene_obj._place_done = True
        # prev_emotions 由标注 worker 回填后统一更新（骨架无 emotion, 2026-09-02）
        # 分支段落可能是骨架（branches 未标注）→ 入队异步标注（与主场景同队列）
        _enqueue_annotate(state, state.scene_obj)
        # 2026-09-02 修复: 分支渲染后前端不轮询 status（turn 直接返回 scene）——
        # 若返回未标注骨架, 立绘 default 且标注完成无补切通道; 同步短等标注
        # （修复后标注 ~1-3s, 上限 8s 兜底——标注层失败也有 _fallback_fill 保证就绪）
        _wait_annotated(state, timeout=8.0)
        state.scene = state.scene_obj.to_dict()
        # 候选命中时下一板已就绪（pregen 通道）→ 不再单路预生成（防双份）;
        # 老路则分支播放时照旧预生成
        if cand is None:
            _pregenerate(state, char_id, session_id)
        return {"accepted": True, "busy": state.busy, "branch": True,
                "scene": state.scene, "candidate": cand is not None}

    # 记录流 v2 裁决（P0-7）: 选中候选 = 老师那句话 —— **物化 + 就地展示**;
    # 角色的反应在**下一板**（引擎待发队列, 点继续 0 LLM 领出）——不在这里生成。
    if (state.scene_obj is not None and state.scene_obj.records
            and text in (state.scene_obj.choices or [])):
        _log_scene(state, char_id, session_id, picked=text)
        if state.vn is not None:
            state.vn.record_picked(text)          # 历史尾部物化（live == 回放）
        _discard_candidates(state)                # v2 不 fork（内容已在待发队列）
        # 就地展示老师那句（**不重建 scene_obj**——原对象的标注就绪态要保住,
        # 否则推进门控会一直等一个永不回来的标注）
        state.scene = _narrativize(state.scene, text)
        state.scene_obj.choices = []              # 已裁决: 不再给选项
        state.scene_logged = True                 # 本板已随裁决落库
        # 裁决后立刻备料（P0-7c 修正）: 这里必须先 record_picked（上面已做）——
        # 预生成请求的历史要含物化裁决行。待发有货 → 0 LLM 领出反应板; 没货 →
        # 真生成下一拍（玩家读老师那句的时间即缓冲桥）。
        _pregenerate(state, char_id, session_id)
        return {"accepted": True, "busy": state.busy, "branch": True,
                "scene": state.scene, "candidate": False}

    # append-only 事件流: 当前展示场景在玩家裁决时落库（带 picked）;
    # 纯叙事场的"（继续）"是推进指令不是内容裁决 → picked=None（与预生成消费一致）
    _log_scene(state, char_id, session_id,
               picked=None if text == "（继续）" else text)
    _generate(state, char_id, session_id, text)
    return {"accepted": True, "busy": True}


def bond_status(char_id: str, session_id: str) -> dict:
    """轮询: 生成状态 + 最新场景（前端按 round 去重）+ 终结标记 + 名字牌信息
    + emo_version（异步标注补标版本——前端感知后补切已显示段落的立绘表情）
    + memorial（纪念模式标记 + 立绘 URL——前端进纪念淡入图背景, 退出淡出）。
    + gate_busy（2026-09-07）: 推进门控视角——当前场景 emotion+place 未就绪
    （state.busy 之外的另一类"再等等"）; 前端忙等改轮询 status 而非狂发 turn。"""
    state = _state(char_id, session_id)
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
    return {
        "busy": state.busy,
        "gate_busy": not _scene_visual_ready(state),
        "round": state.round,
        "scene": state.scene,
        "error": state.error,
        "completed": state.completed,
        "name": role["name"],
        "club": role["club"],
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
    if state.finished:
        # 幂等（2026-09-09 审计: 01:20-01:21 同一进程 6s 内两次 finish →
        # 重复 vn_exit + wrapup + 兜底话; 前端有 finished 防重, 后端再兜一层）。
        # 留痕 warning → diag 落盘, "谁在调 finish"从此可查
        logger.warning("bond_finish 幂等跳过（重复调用） %s/%s",
                       char_id, session_id)
        return {"completed": True, "already": True}
    logger.info("bond_finish 执行 %s/%s completed=%s（入口留痕）",
                char_id, session_id, state.completed)
    _prewarm_cache_delete(char_id)             # 收尾: 旧首场缓存一并失效
    # SceneStream P1.5（中断/收尾防御, 2026-09-08 审计）: 会话收尾即清候选池
    # ——后台候选（若仍在生成）作废孤儿, 停止烧 token; 未选支零落库由
    # _log_scene 边界结构保证（候选从不触碰事件流）
    _discard_candidates(state)

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
    try:
        # vn_exit 带剧情完成标志（2026-09-01）: completed = 剧情真正走完
        # （story_end 自然收尾）; False = 玩家中途退出——收尾链据此分支
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
    title = state.chapter_title
    threading.Thread(target=_wrapup,
                     args=(char_id, session_id, title, state.completed),
                     daemon=True).start()
    state.finished = True               # 幂等标记（本内存态生命周期内只收尾一次）
    return {"completed": True}


# ---------------------------------------------------------------------------
# 内部: 生成 / 落库 / 收尾
# ---------------------------------------------------------------------------

#: 跨重启预热缓存（2026-09-09, 旁路非真源）: 首场生成成功即落盘
#: soul/prewarm.json——进程重启后玩家再点入时直接作为首场（0 LLM）,
#: 覆盖"首场已生成但从未裁决/从未 adopt"的冷等。LLM 不读（不在事件流,
#: 上下文从事件流构建）; 真源仍在裁决时落库（picked/回放/append-only 原样）。
_PREWARM_FILE = "prewarm.json"


def _prewarm_cache_path(char_id: str) -> Path | None:
    """缓存文件路径（char_dir/soul/prewarm.json）; 拿不到 → None（跳过缓存）。"""
    try:
        st = _store()
        return Path(st.char_dir(char_id)) / "soul" / _PREWARM_FILE
    except Exception:                              # noqa: BLE001 — 缓存不可用降级
        return None


def _prewarm_cache_save(char_id: str, session_id: str, scene_dict: dict,
                        scene_input: str, chapter_title: str) -> None:
    """首场落地即写缓存（round==1 真实引擎; 原子写 tmp+rename 防半写）。"""
    try:
        path = _prewarm_cache_path(char_id)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "anchor_seq": _last_mmt_seq(char_id, session_id),
            "chapter_title": chapter_title,
            "scene": scene_dict,
            "input": scene_input,
            "ts": time.time(),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(path)
    except Exception as e:                         # noqa: BLE001 — 缓存失败降级
        logger.warning("prewarm 缓存写失败（降级, 不影响剧情）: %s", e)


def _prewarm_cache_load(char_id: str, session_id: str):
    """读缓存 → (scene, scene_input, chapter_title) | None。

    新鲜判据: anchor_seq == 当前最新 mmt seq——期间玩家又聊/新触发轮 →
    上下文过期（与内存 staged_seq 同判据）→ miss; 坏文件/缺字段 → miss。
    """
    try:
        path = _prewarm_cache_path(char_id)
        if path is None or not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("anchor_seq", -1)) != \
                _last_mmt_seq(char_id, session_id):
            return None                                  # 触发后又聊过 → 过期
        scene = BondScene.from_dict(payload.get("scene"))
        if not scene.paragraphs:
            return None
        return scene, str(payload.get("input") or ""), \
            str(payload.get("chapter_title") or "")
    except Exception:                                # noqa: BLE001 — 坏缓存当 miss
        return None


def _prewarm_cache_delete(char_id: str) -> None:
    """缓存失效（adopt 消费 / finish / 命中使用后）——旧首场不得与后续段混淆。"""
    try:
        path = _prewarm_cache_path(char_id)
        if path is not None and path.is_file():
            path.unlink()
    except Exception:                                # noqa: BLE001 — 删除失败无碍
        pass


def _scene_landed(state: BondState, scene: BondScene, char_id: str,
                  session_id: str, user_input: str, *, t0: float,
                  save_cache: bool) -> None:
    """场景落地公共路径（_generate 成功块与跨重启缓存命中共用, 2026-09-09）:

    设置 scene_obj/scene/input/落库就绪标记 + 配额/prev/meta/异步标注/候选
    spawn + 失败计数清零 + 计时日志。save_cache=True（LLM 首场落地）→ 写
    跨重启预热缓存; demo 不写。
    """
    state.scene_obj = scene
    state.scene = scene.to_dict()
    state.scene_input = user_input
    state.scene_logged = False
    if scene.is_end:
        state.completed = True       # 仅自然 story_end 才 completed
    # 选项配额（供下一场 system_note 参考）
    if scene.choices:
        state.choices_used += 1
    # prev_emotions（情绪单调注记）由标注 worker 回填后统一更新——
    # 骨架无 emotion（2026-09-02）, 生成时取只会得到空列表
    _log_scene_meta(state, char_id, session_id, scene)
    # 两遍式 C 异步标注: 骨架先显示, emotion 解析入队补标（不阻塞玩家）
    _enqueue_annotate(state, scene)
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
                            user_input, state.chapter_title)

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
        t0 = time.monotonic()                    # 计时埋点（§6.1）
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
                    scene = state.vn.send_vn_scene(
                        user_input, system_note=_system_note(state), annotate=False,
                        on_memorial_prompt=_make_memorial_cb(
                            state, char_id, session_id),
                    )
                    # 2026-09-09 语义修正: 篇幅超限不再丢弃 LLM 场景换 closing
                    # 伪收场——纠正面在 system_note（_END_ROUNDS 后每轮强制
                    # story_end）; 持续不收尾 = 玩家可离开（中场退出, 在押续写）
                _scene_landed(state, scene, char_id, session_id, user_input,
                              t0=t0, save_cache=first_scene)
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
        t0 = time.monotonic()                    # 计时埋点（§6.1）
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
                logger.info("bond_pregen ok %s/%s dur=%dms",
                            char_id, session_id, _ms_since(t0))
        except Exception as e:                     # noqa: BLE001 — 预生成失败降级
            logger.warning("bond 预生成失败 (%dms, 降级为点击时再生成): %s",
                           _ms_since(t0), e)
            state.pregen_obj = None
            state.pregen_scene = None
            state.pregen_input = ""
        finally:
            state.busy = False

    threading.Thread(target=run, daemon=True).start()


def _discard_candidates(state: BondState) -> None:
    """候选支池作废（DESIGN_CHOICE_PREGEN §1, N2c）: 清空引用 → 未选候选引擎
    即孤儿（生成中线程完成即不可达 → GC, 零落库）。列表替换为原子操作
    （GIL）; worker 写回带池身份检查（any(c is cand)）——清池后结果自然丢弃。
    """
    state.choice_candidates = []


#: 运行时开关读取路径（settings.toml, gitignore——本机 GUI 设置文件）
_CAND_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.toml"


def _choice_pregen_enabled() -> bool:
    """choice_pregen 开关（DESIGN_CHOICE_PREGEN §4, N2d）:

    settings.toml [bond] choice_pregen = "off" | "sibling" | "tree"
    - sibling: 单层候选预生成（当前实现; tree 暂同 sibling——递归展开未做,
      预判收益趋零不做）; off: 关闭（走分支播放期单路 pregen 老路）。
    - 读取失败/缺省 → True（sibling——功能默认开, 不稳可一键关）。
    """
    try:
        import tomllib
        text = _CAND_SETTINGS_PATH.read_text(encoding="utf-8")
        mode = str(((tomllib.loads(text).get("bond") or {})
                    .get("choice_pregen") or "sibling")).strip().lower()
        return mode in ("sibling", "tree")
    except Exception:                              # noqa: BLE001 — 缺省开
        return True


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
    if not _choice_pregen_enabled():             # 开关（N2d）: off → 老路
        return
    if not scene.choices or scene.is_end or scene.memorial_prompt:
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
    # 入队打点（2026-09-08 首板 nomal 排查）: 每场景标注意向一目了然（emo/place）
    _want_emo = bool(state.vn._lexicon_keys and not scene.memorial_exit
                     and any(not p.get("emotion") for p in scene.paragraphs
                             if isinstance(p, dict)))
    _want_place = bool(state.vn._place_keys and not scene.memorial_exit
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
    if not state.vn._place_keys or scene.memorial_exit:
        return
    if getattr(scene, "_place_done", False):
        return
    if state._place_queue is None:
        state._place_queue = queue.Queue()
    state._place_queue.put(scene)
    _ensure_lane(state, started_attr="_place_started", thread_attr="_place_thread",
                 worker_fn=_place_worker, lane="place")


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
                    state.prev_emotions = [p.get("emotion", "")
                                           for p in scene.paragraphs
                                           if isinstance(p, dict)]
                elif state.pregen_obj is scene:
                    state.pregen_scene = scene.to_dict()
                    state.emo_version += 1
                # 已被替换/消费后又被推进 → 丢弃（异步不覆盖新状态）
        except Exception as e:                           # noqa: BLE001 — 保活: 单条失败
            logger.warning("bond 标注处理异常（跳过本条, worker 保活）: %s", e)
        finally:
            try:
                state._anno_queue.task_done()
            except Exception:                            # noqa: BLE001 — 幂等无害
                pass
    # 正常结束（None 哨兵）: 复位启动标记——后续入队可再启（worker 永不饿死）
    state._anno_started = False
    state._anno_thread = None


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
                                   {"chapter_title": state.chapter_title})
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
    # 记录流 v2（P0-7c）: 旧的"整段剧情 2~3 次选项配额"注记退役——v2 的交互密度
    # 由 rules 引导（一段戏里老师开口 3~5 次）, 引擎不再逐轮念配额（注记进 prompt,
    # 提旧概念只会干扰守形）。choices_used 仍计数（统计/诊断用）。
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


def _wrapup(char_id: str, session_id: str, title: str, completed: bool) -> None:
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
    # 后异步执行, 期间全局 chat._store 可能已被替换（测试 cleanup/未来多线）,
    # 迟到的兜底写入曾落错 store（真实 data 被测试污染）; 线程内一律用快照,
    # 与"谁调起它"时的归属一致
    store = _store()
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
