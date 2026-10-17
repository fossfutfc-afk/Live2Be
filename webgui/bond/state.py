"""`webgui.bond` 的**状态模型**（C2, `docs/EXEC_SPLIT.md`）—— 拆分的第一个叶子模块。

## 放什么

· `BondState`（每 `(char_id, session_id)` 一场剧情的内存态）
· `BoardLifecycle`（板级三态 PROVISIONAL/DELIVERED/COMMITTED, 节点 2″）
· `ChoiceCandidate`（候选支草稿, DESIGN_CHOICE_PREGEN §1）
· 状态注册表 `_bonds` + 工厂 `_state()`（懒创建, **store 在创建时绑定**）
· `_memorial_open_in_events()`（跨重启: 从事件流初始化纪念窗口记账）

## 为什么**先**拆这个（`EXEC_SPLIT` 原本把它排在 C7）

它是**叶子**: 只依赖 `core` / `contract` / `webgui.deps`, 不被同包任何模块依赖回去
⇒ 后面每个模块（stores / lanes / replay / pregen / memorial / api）都能直接
`from webgui.bond.state import BondState, BoardLifecycle`, 不会成环。
`BoardLifecycle` 尤其是关键: `BondState.scene_state`（本模块）与 `_log_scene`
（C3 起在 `stores.py`）**运行期**都要用它, 放在谁那里都会逼出一圈反向依赖 ——
放这里, 两者都只往下看。

## 纪律

· ⚠️ **本模块不许 import 同包其它模块**（`_impl` 正在被逐块搬空; 反向依赖 = 环）;
· ⚠️ **不是接缝**: 拿 store 一律 `deps.store()`（`webgui/deps.py`）—— 子模块读的是
  自己的全局, 打**包属性**（`monkeypatch.setattr(webgui.bond, …)`）会静默失效,
  见 C1a 与 `tests/core/test_split_safety.py`;
· 搬进来的代码**逐字未改**, 唯一改动 = `_store()` → `deps.store()`（等价转发）。
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from core.bond.bond_story import BondScene, BondStoryEngine
from core.session.events import M_MEMORIAL_ENTER, M_MEMORIAL_EXIT, M_SESSION_END
from webgui import deps

if TYPE_CHECKING:                       # 仅注解求值期（避免把 store 拖进运行期依赖图）
    from core.session.store import SessionStore


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


class BoardLifecycle(str, Enum):
    """**板级生命周期**（节点 2″, 2026-09-21）——取代裸 bool `scene_logged`。

    讲的是"**当前板**（`state.scene_obj`）走到哪一步了":

        PROVISIONAL ──交付上屏──► DELIVERED ──裁决/推进/收尾──► COMMITTED
             │                        │
             └──丢弃──►（无痕）        └──丢弃──►（无痕；"丢弃"不写任何标记）

    · `PROVISIONAL`: 已生成、**没交付**——预生成的板（`state.pregen_obj`）就是这一态;
    · `DELIVERED`:   已上屏, 正文**还没进事件流**（`_log_scene` 待写）;
    · `COMMITTED`:   正文已 append 进事件流（进暂存还是真源由 B0 决定）。

    ## 为什么值得显式化

    `docs/DESIGN_RESEND.md` 的"重发 / 拒绝羁绊"要按**固化线**分两区处置:
    `DELIVERED`（水位之上）**直接丢**——真源与暂存里本来什么都没有;
    `COMMITTED`（水位之下）只能走 `brain/revise` **更正**。
    一个 bool 让这两区的区别只活在注释里, 谁都能顺手 `= True`。
    三态 + 唯一丢弃入口 `_discard_boards` 之后, 这条边界可断言、可 grep。
    """

    PROVISIONAL = "provisional"
    DELIVERED = "delivered"
    COMMITTED = "committed"

    @property
    def committed(self) -> bool:
        """正文是否已进事件流（旧 `scene_logged=True` 的等价物）。"""
        return self is BoardLifecycle.COMMITTED


@dataclass
class BondState:
    """一场羁绊剧情的驱动状态（per (char_id, session_id) 内存态）。"""

    #: 流程绑定的 store（`_state()` 创建时捕获）——长流程（后台生成线程）可能活过
    #: 测试的 store 切换/多开/重启, 写入时再读全局 `deps.store()` 会写进别的世界线
    #: （2026-09-11 真机事故: 流式测试的生成线程把 vn_state 写进真实 events.jsonl）。
    store: SessionStore | None = None
    vn: BondStoryEngine | None = None
    demo: list[dict] | None = None      # 演示模式: 预设剧本（不调 LLM）; None = 真实引擎
    round: int = 0                      # 已生成场景数（系统注记 / 前端轮询去重）
    busy: bool = False                  # 场景生成中（LLM 秒级, 后台线程）
    scene_obj: BondScene | None = None  # 当前展示场景（运行时对象, 含 memorial 标记）
    scene: dict | None = None           # scene_obj.to_dict()（前端消费）
    scene_input: str = ""               # 生成 scene 用的输入（落库 input 字段）
    #: 板级生命周期（节点 2″, 2026-09-21; 原 `scene_logged: bool`）——见 `BoardLifecycle`。
    #: 缺省 COMMITTED: 回放/预热缓存/草稿旁路这些"正文已在事件流里"的路径直接落地,
    #: 真·新生成的板由 `_scene_landed` 显式降到 DELIVERED。
    scene_state: BoardLifecycle = BoardLifecycle.COMMITTED
    #: **板世代**（○C8c, 2026-09-21）: `_discard_boards` 每调用一次 +1 —— "丢弃那一刻
    #: **之前出生**的板全部作废"。异步落地（预生成/live 流式/候选支）都必须先复核自己
    #: 出生时的世代（`pregen._board_epoch_stale`）, 草稿旁路的写盘由
    #: `stores._draft_save(epoch=…)` 在同一临界区里复核。
    #: 为什么需要: "丢弃"只清得掉**当时在内存里**的引用, 一个在飞的线程随后就会把板
    #: 写回来（`pregen_scene` 复活 + 草稿文件复活）——全量跑时
    #: `test_discard_boards_is_traceless` 偶发红就是这条竞态（单跑常绿）。
    #: 与 `_call_id` 同款思路: **产者盖章、落地处复核**。
    board_epoch: int = 0
    error: str = ""
    completed: bool = False             # 剧情已终结（is_end 自然收尾 → True）
    #: 上次是**中途退出**（`vn_exit completed=False`）——进入时由
    #: `_prev_chapter_quit()` 打标。⚠️ **当前没有消费者**: 用户 2026-09-20 裁决
    #: *"不需要任何信息，直接**静默重进**就可以了，但这个 API 可以留着"*
    #: （先前用它注过「老师回来了」, 已撤）。留着当事实, 不做注入。
    quit_resume: bool = False
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
    # 回放场景来自事件流（已落库, `scene_state=COMMITTED` 不重复落）; 最后一场展示即
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
    # 2026-09-21: `choices_used` 已删——它是"选项配额注记"的计数侧, 而那条注记
    # 2026-09-10（P0-7c）随记录流 v2 退役, 字段从此**只写不读**（没有任何读点）。
    # 留着会让人误以为引擎还在逐轮念配额; 真要恢复配额, 字段与注记得一起回来。
    # 2026-09-13（审计 B8）: `prev_emotions` 已删——它唯一的消费者是那条
    # "上一场 emotion 全同 → 请切换 emotion"注记, 而 v2 的 emotion 由标注层给、
    # 写作者无字段可写。留着只会让人误以为主 LLM 还参与表情决策。
    # 异步标注（两遍式 C 2026-08-31）: emotion 解析挪出玩家等待路径——
    # 骨架先显示, 标注队列单 worker 串行补标, 写回经对象身份检查防竞态
    emo_version: int = 0                       # emotion 补标版本（前端感知补切表情）
    _anno_queue: queue.Queue | None = field(default=None, repr=False)
    _anno_started: bool = field(default=False, repr=False)
    # place 标注 lane（DESIGN_BOND_CONTRACT_V2 §7, P3b-1 2026-09-07）: 与 emotion
    # 双路并行——各自队列/消费者; 推进门控 = 双路齐; 锚点写回 payload 变更句
    # （place 键, 稀有）。场景就绪标记挂 scene 对象（_place_done——判定完成即
    # 含 keep, gate 恒可达）; 分支反应段/无词表/纪念退出 = 视为就绪。
    _place_queue: queue.Queue | None = field(default=None, repr=False)
    _place_started: bool = field(default=False, repr=False)
    _anno_thread: threading.Thread | None = field(default=None, repr=False)
    _place_thread: threading.Thread | None = field(default=None, repr=False)
    # 在途标注计数（2026-09-13 审计 A6）: worker 从队列取走 → `await` 标注 LLM →
    # 写回, 这段窗口里 `qsize()==0`, 光看队列深度会误判成"lane 空闲"。看门狗据此
    # 区分"慢但在途"（等它）与"没人会再来标"（才降级）——两路各自 +1/−1。
    _lane_inflight: int = field(default=0, repr=False)
    # 纪念立绘异步生成（方案 A 2026-09-01）: 流式嗅探到 memorial_enter 的 prompt
    # 定稿即后台生图（与 LLM 剩余输出并行）——玩家看到纪念场景时图已就绪, 淡入
    memorial_img: str = ""                     # 前端 URL（/gallery/{char}/{sid}.png）; 空 = 未就绪/失败
    # 2026-09-21: `memorial_img_ready` 已删——只写不读（全仓唯一读点在
    # tests/webgui/test_bond.py）; 前端就绪判据一直是 `memorial_img` 非空。
    memorial_img_busy: bool = False            # 生图中（防重复触发; 重试 attempt 可能重复回调）
    #: 纪念窗口 marker 记账（2026-09-12）: 已写过 `memorial_enter` 且还没写 `exit`。
    #: 状态创建时从事件流初始化（跨重启: 上一次进程可能死在窗口里）——据此在窗口
    #: 结束（新生成一块）时补一条 `memorial_exit`, 让 marker 栈与现实一致。
    memorial_logged: bool = False
    # 看门狗计时（2026-09-11 真机"继续键等了 110s 不动"）: 忙态/视觉门/预生成
    # 消费门各自记起点——bond_status（前端在轮询）顺手检查, 卡住就兜底放行 + WARNING,
    # 绝不让"点击永久无响应"这类问题只能靠用户重启服务解决。
    busy_since: float = 0.0                    # monotonic; 0 = 空闲
    gate_since: float = 0.0                     # 视觉门连续未就绪起点
    pregen_gate_since: float = 0.0              # 预生成消费门连续未通过起点
    _gen_thread: threading.Thread | None = field(default=None, repr=False)   # 生成线程（存活判定用）
    _pregen_thread: threading.Thread | None = field(default=None, repr=False)
    turn_rejects: dict = field(default_factory=dict)         # 推进被拒计数（诊断留痕）
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


_bonds: dict[tuple[str, str], BondState] = {}


def _state(char_id: str, session_id: str) -> BondState:
    """懒创建 bond 状态（每 (char, session) 一场剧情）。

    **store 在此绑定**（而非写入时再读 `deps.store()`）: 后台生成线程可能活过
    调用方的 store 切换（测试注入/多开/重启）, 那时再读全局就会写进别的世界线。
    """
    key = (char_id, session_id)
    if key not in _bonds:
        st = BondState(store=deps.store())
        # 跨重启: 上一次进程可能死在纪念窗口里（写了 enter 没写 exit）——按事件流
        # 初始化记账, 窗口结束时才能补上 exit（否则 marker 栈一直停在 in_memorial）。
        try:
            st.memorial_logged = _memorial_open_in_events(char_id, session_id, st.store)
        except Exception:                            # noqa: BLE001 — 读失败按未开
            st.memorial_logged = False
        _bonds[key] = st
    return _bonds[key]


def _memorial_open_in_events(char_id: str, session_id: str, store=None) -> bool:
    """事件流里是否存在**未闭合**的 `memorial_enter`（v1/v2 通用判据, 与
    `session_status.in_memorial` 同规则: 其后的 `memorial_exit`/`session_end` 才算闭合）。"""
    try:
        evs = (store or deps.store()).events(char_id, session_id)
    except Exception:                                # noqa: BLE001 — 读失败当未开
        return False
    open_ = False
    for e in evs:
        if not getattr(e, "is_marker", False):
            continue
        if e.subtype == M_MEMORIAL_ENTER:
            open_ = True
        elif e.subtype in (M_MEMORIAL_EXIT, M_SESSION_END):
            open_ = False
    return open_
