"""
MomoTalk 对话引擎 — 全 JSON 动作 agent loop。

每轮对话（agent_turn）:
    用户输入 → LLM 输出**动作列表** JSON（{"actions": [动作1, 动作2, ...]}, mmt_ 前缀）
    → 列表解析（inspect 不进列表 / trigger 独占）→ 全量 parse（原子）→ 顺序执行
    → 全部成功 → 渲染全部步骤（混合节奏"说话→发图→说话"）+ 记历史（每动作一条）
    → 触发羁绊剧情（mmt_trigger_bond_story, 独占一轮）才切换模式。

历史格式（每轮至少记动作名 + reply, 可追溯 agent 干了什么）:
    user:      用户说的话
    assistant: "[mmt_chat] 今天谢谢你！" / "[mmt_send_media] 你看这张！"

五层认知（与 mmt_actions / mmt_executor 一致）:
    L0 自我层   build_prompt("momotalk") + 世界观（common+system 档）→ 常驻
    L1 人际层   interperson 自表条目注入（self_entry_to_prompt）→ 常驻
    L2 硬知识   LLM 世界知识 + 知识库（规划中）
    L3 深挖层   mmt_inspect_character（静默推理轮, 权重分级）→ 仅此入口

MomoTalk 与羁绊剧情的区别:
    - MomoTalk = 手机聊天, 无动作描写, 短消息, 逐块输出（…打字指示 + 气泡）
    - 羁绊剧情 = 视觉小说, 允许动作描写（括号）, 长对白（BondStoryEngine）

用法:
    engine = MomoTalkEngine("config/characters", llm_client)
    engine.start_session("haruka")
    result = engine.agent_turn("我们去天台吧？")
    for step in result.steps:   # …打字指示 + 气泡, 依序渲染
        ...
    engine.save_session()
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.common import Live2BeError, err
from core.common.tone import load_story_tone
from llm.client import LLMClient, feedback
from llm.prompts import load_prompt
from contract import AgentAction, build_schema
from core.bond.bond_progress import BondProgress
from core.mmt.mmt_actions import build_mmt_registry
from core.mmt.mmt_executor import (
    ExecResult,
    MmtExecError,
    MmtExecutor,
    load_interperson,
    self_entry_to_prompt,
)
from core.parsing.dynamic_character_parser import (
    CharacterLoader,
    DynamicCharacter,
    yaml_to_prompt,
)
from core.parsing.world_parser import DEFAULT_WORLD_PATH, load_world, world_to_prompt
from core.session import SessionStore
from core.session.events import make_event
from core.session.renderer import render_events, session_status
from core.brain.wiki_v2.digest import digest_segment
from core.brain.wiki_v2.render import render_character_view
from core.brain.wiki_v2.seed import seed_from_config
from core.brain.wiki_v2.store import WikiStoreV2
from core.ui.display import MomoTalkOutput
from core.ui.streaming import DisplayStep
from core.ui.text_processors import _process_for_momotalk, _strip_action_brackets, split_reply_chunks

logger = logging.getLogger(__name__)


def _interact_max(events: list, digested_seq: int) -> int:
    """本段互动 max seq（好感事件幂等键——affection 事件自身的 seq 会漂移,
    不能作键; 重复 digest 同区间时 interact_max 不变, 同 legacy 语义）。"""
    return max(
        (e.seq for e in events
         if e.seq > digested_seq and not e.is_marker and e.type != "affection"),
        default=0)


def load_brain_segment(store: SessionStore, char_id: str, char_name: str = "",
                       characters_root: str | Path | None = None) -> str:
    """角色注入段（wiki_v2, 0 LLM）——bond 开场/剧情引擎共用（webgui.bond/vn_cli）。

    出厂基座确保（空库 seed, source_key 幂等）→ render_character_view 第一人称;
    失败/空库 → ""（零注入, 平行世界; 读失败静默跳过, 不阻断剧情）。
    """
    try:
        wstore = WikiStoreV2(store.data_root, world_id=store.world_id,
                             char_id=char_id)
        if characters_root is not None \
                and not any(n.kind == "fact" for n in wstore.all()):
            seed_from_config(wstore, Path(characters_root) / char_id)
        return render_character_view(wstore.all(), char_name=char_name) or ""
    except Exception:                                # noqa: BLE001 — 宁缺勿错
        return ""

#: 滑动窗口默认轮数（每轮 = user+assistant 2 条消息; 40 轮 = 80 条消息）。
#: 玩家可配（引擎构造参数 history_rounds 传入; 设置页接入见 docs/DESIGN_MEMORY.md Step 1）
DEFAULT_HISTORY_ROUNDS = 40
# 兼容旧名（历史引用）
MAX_HISTORY_ROUNDS = DEFAULT_HISTORY_ROUNDS
# 会话存档走角色根目录（DESIGN_SAVE.md §三）: data/{char_id}/sessions/

# agent loop 参数
MAX_STEPS = 6          # 单轮动作步数上限（含 inspect 静默轮）
TEMP = 0.8             # 与旧 send_message 一致
MMT_MAX_TOKENS = 4096  # 动作 JSON + 对白（推理模型需大 max_tokens, 勿改小）

#: mmt 会话窗口 digest 间隔（蓝图 §3.1: 2026-09-02 用户拍板 N=25——纯 MMT 长聊
#: 每 N 轮后台消化一次, 节流而非精确窗口; bond 剧情闭环触发不变）
MMT_DIGEST_INTERVAL = 25


class MmtLoopError(Live2BeError):
    """MomoTalk agent loop 错误（步数耗尽等）。message 供调用方展示/重试。

    __str__ 自动产出 [momotalk.py][MmtLoopError][message]。
    """


# ============================================================================
# 会话数据结构辅助类
# ============================================================================


@dataclass
class Session:
    """对话会话的完整状态（可序列化）。"""
    character_id: str
    character_name: str
    history: list[dict[str, str]] = field(default_factory=list)
    created_at: str = ""

    def to_json(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "character_id": self.character_id,
                "character_name": self.character_name,
                "created_at": self.created_at or datetime.now().isoformat(),
                "messages": self.history,
            }, fh, ensure_ascii=False, indent=2)

    @staticmethod
    def from_json(path: Path) -> "Session":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return Session(
            character_id=data.get("character_id", ""),
            character_name=data.get("character_name", ""),
            history=data.get("messages", []),
            created_at=data.get("created_at", ""),
        )


@dataclass
class TurnResult:
    """一轮 agent 对话的结果。

    steps      — 显示步骤序列（…打字指示 + 气泡）, 由 UI 依序渲染
    reply      — 完整对白（不含名字前缀, 历史存档用; 可能为空）
    action     — 最后一个动作名（mmt_chat / mmt_send_media / mmt_trigger_bond_story）
    payload    — 最后一个动作的干净 payload（GUI 可渲染媒体等）
    actions    — 动作列表视图 [{action, reply, payload}]（GUI 依序渲染媒体/切换, 2026-08-23）
    bond_story — True = 触发羁绊剧情成功, 调用方应切换到羁绊剧情模式
    error      — ok=False 时的原因（预留; 当前异常走 MmtLoopError）
    """
    ok: bool = True
    steps: list[DisplayStep] = field(default_factory=list)
    reply: str = ""
    action: str = ""
    payload: dict = field(default_factory=dict)
    actions: list[dict] = field(default_factory=list)
    bond_story: bool = False
    error: str = ""


# ============================================================================
# 引擎
# ============================================================================


class MomoTalkEngine:
    """MomoTalk 对话引擎 — 会话生命周期 + 全 JSON 动作 agent loop。"""

    def __init__(
        self,
        characters_root: str | Path,
        llm_client: LLMClient,
        interperson_path: str | Path | None = None,
        affection_threshold: int = 5,
        bond_progress: BondProgress | None = None,
        store: SessionStore | None = None,
        character_names: list[str] | None = None,
        history_rounds: int = DEFAULT_HISTORY_ROUNDS,
    ):
        self.char_loader = CharacterLoader(characters_root)
        self._characters_root = Path(characters_root)   # seed（出厂 digest）读 config 用
        self.llm = llm_client
        self.registry = build_mmt_registry()
        # 滑动窗口（轮数, 每轮 2 条消息）——玩家可配（docs/DESIGN_MEMORY.md Step 1）
        self._history_rounds = max(1, int(history_rounds))
        # 称呼名单（分饰多角预留）: None = 单人（默认当前角色 display_name）;
        # 未来一个 LLM 扮演多角色时注入多个名字（"你好，A / B / C——以下是行为规则…"）
        self._character_names = list(character_names) if character_names else None
        # 羁绊触发门槛（默认 5 轮, 用户确认: 轮数门槛非情绪数值）; 传入同一实例
        # 供 executor 读轮数 + 本引擎记录轮数, 保证门槛/记录一致
        self.bond_progress = bond_progress or BondProgress()
        self.executor = MmtExecutor(
            characters_root,
            interperson_path,
            affection_threshold=affection_threshold,
            bond_progress=self.bond_progress,
        )
        # 事件流存档（DESIGN_SAVE.md §4）: store 注入 + attach_session 后,
        # 每轮 agent_turn 落 mmt 事件 + 会话内轮数; None = 不记录（向后兼容）
        self._store = store
        self._session_id: str = ""
        self._session_rounds: int = 0

        self._current_char: DynamicCharacter | None = None
        self._system_prompt: str = ""
        self._brain_injection: str = ""   # 角色记忆注入段（动态拼装; digest 后台原子替换）
        self._history: list[dict[str, str]] = []
        self._trace: list[dict] = []      # 最近一轮的完整动作轨迹（追溯/调试）
        self._random_cooldowns: dict = {}  # 随机事件冷却状态（per 引擎实例, 不跨会话串）
        self._digest_lock = threading.Lock()  # 同引擎 digest 串行（async_digest 后台线程）

    # ------------------------------------------------------------------
    # 公共 API — 会话生命周期
    # ------------------------------------------------------------------

    def start_session(self, character_id: str) -> str:
        char = self.char_loader.load(character_id)

        sp = char.build_prompt("momotalk")          # L0 自我层: 完整人设 + 行为约束

        world_chunk = world_to_prompt(load_world(DEFAULT_WORLD_PATH))
        if world_chunk:                              # 世界观（common + system 档）
            sp += "\n\n" + world_chunk

        # 剧情基调（对话生成层, "最一开始告诉 AI", DESIGN_BRAIN.md §0）:
        # per 角色写在扮演手册 script.yml 的 SIG~main_tone（旧: personality 的
        # SIG~story_tone, 兼容）——AI 从卡学角色, 基调也从卡来。digest 是事后提炼
        # 救不了基调——生成的剧情必须一开始就符合角色类型。
        sp += "\n\n【本角色剧情基调】\n" + load_story_tone(char)
        # 扮演手册 MMT 风格（script.yml 的 SIG~mmt_tone; 缺失 → 不注入, 照旧）
        if char.mmt_tone:
            sp += "\n\n【本角色 MMT 风格】\n" + char.mmt_tone

        try:                                         # L1 人际层: 自表条目注入（键值+权重）
            interperson = load_interperson(self.executor.interperson_path)
        except MmtExecError as e:                    # 文件损坏 → 跳过注入, 不挡会话启动
            logger.warning("interperson 读取失败, 跳过 L1 注入: %s", e)
            interperson = {}
        entry = self_entry_to_prompt(interperson, char.character_id)
        if entry:
            sp += "\n\n" + entry

        # 玩家名不注入 system prompt——学生不会直呼玩家自定义名（一直称呼"老师"）。
        # 名字只做系统显示（终端提示符 / 菜单 / 存档标识）, 见 mmt_preset 玩家名系统。
        sp += "\n\n" + load_prompt("momotalk_environment")
        # 称呼注入（强化角色身份认知; list 为一人分饰多角预留——多角色时
        # 调用方传 character_names=["A","B"] → "你好，A / B——以下是你的行为规则…"）
        names = self._character_names or [char.display_name]
        greeting = "你好，" + " / ".join(names) + "——以下是你的行为规则，请严格遵守："
        sp += "\n\n" + greeting + "\n\n" + load_prompt("momotalk_rules")
        # MMT 域用动作列表格式（2026-08-23 定稿: 混合节奏 "说话→发图→说话"）
        sp += "\n\n可用动作 schema:\n" + build_schema(self.registry, action_list=True)

        self._current_char = char
        self._system_prompt = sp
        self._history = []
        self._trace = []
        self.executor.set_current_character(char)   # inspect/trigger 依赖会话角色

        logger.info("新会话: %s (%s)", character_id, char.display_name)
        return char.display_name

    def save_session(self, path: str | Path | None = None) -> Path:
        if path is None:
            # 角色根目录（DESIGN_SAVE.md §三）: data/{char_id}/sessions/{char}_{ts}.json
            char_dir = Path("data") / self._char_id / "sessions"
            char_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            path = char_dir / f"{self._char_id}_{ts}.json"
        Session(
            character_id=self._char_id,
            character_name=self._current_char.display_name if self._current_char else "",
            history=list(self._history),
            created_at=datetime.now().isoformat(),
        ).to_json(Path(path))
        logger.info("会话已保存: %s (%d 条消息)", path, len(self._history))
        return Path(path)

    def attach_session(self, session_id: str) -> None:
        """绑定事件流会话（DESIGN_SAVE.md §4）: main 层 store.create 后调用。

        绑定后每轮 agent_turn 落 mmt 事件 + 会话内轮数（store 已注入）。
        """
        self._session_id = session_id
        self._session_rounds = 0

    def _inject_brain(self, character_id: str, session_id: str = "", *,
                      digest: bool = False) -> None:
        """Brain 接线（wiki_v2, 2026-09-02 切换）: 注入角色 wiki → 注入段。

        角色记忆 = per-char 单库（wiki.jsonl, 与 events.jsonl 同目录——SessionStore
        session_id 不参与路径）; 注入段动态拼装（_brain_injection 原子替换）——
        digest 后台完成后**下一轮自动生效**, 不追加防重复注入, 跨线程零锁。

        digest=False（resume）: 只读注入 + 出厂基座确保（0 LLM, source_key 幂等）。
        digest=True（async_digest 后台线程, _digest_lock 串行）: 出厂基座 →
        digest_segment（Round A 记录 + Round B 组织）→ 好感结算
        （affection 事件, 幂等键 interact_max）→ 注入刷新。
        失败静默降级——wiki 是派生视图, events.jsonl 唯一真源, 可重算。
        """
        store = self._store
        if store is None or self._current_char is None:
            return
        char = self._current_char
        anchor = yaml_to_prompt(
            {**char.personality, **char.knowledge}, "角色人设（锚点）")
        try:
            wstore = WikiStoreV2(store.data_root, world_id=store.world_id,
                                 char_id=character_id)
            # 出厂基座（0 LLM; fact 节点存在 = 已 seed——确定性映射, 幂等）
            if not any(n.kind == "fact" for n in wstore.all()):
                seed_from_config(wstore, self._characters_root / character_id)
            if digest:
                events = store.events(character_id)
                interact_max = _interact_max(events, wstore.digested_seq)
                res = digest_segment(wstore, self.llm, events,
                                     character_prompt=anchor)
                if not res.ok:
                    logger.warning("digest 未完成 (%s): %s", character_id,
                                   " | ".join(res.errors))
                elif res.affection_delta > 0 and interact_max:
                    self._write_affection_event(store, character_id, events,
                                                interact_max, res.affection_delta)
            seg = render_character_view(wstore.all(),
                                        char_name=char.display_name or "")
            self._brain_injection = seg or ""
        except Exception as e:                       # noqa: BLE001 — 宁缺勿错
            logger.warning("brain 注入失败 (%s): %s", character_id, e)

    @staticmethod
    def _write_affection_event(store: SessionStore, character_id: str,
                               events: list, interact_max: int, delta: int) -> None:
        """好感事件写（真源 events.jsonl; 幂等键 interact_max——同 legacy 语义:
        重复 digest 同区间 → digested_seq 相同 → 已存在则跳过）。"""
        already = any(
            e.type == "affection"
            and int((e.payload or {}).get("digested_seq", 0) or 0) >= interact_max
            for e in events)
        if already:
            return
        try:
            store.append_event(character_id, "", make_event(
                "affection", "digest",
                {"delta": delta, "digested_seq": interact_max}))
        except Exception as e:                       # noqa: BLE001 — 写失败降级
            logger.warning("affection 事件写入失败: %s", e)

    def async_digest(self) -> None:
        """异步消化本角色线未消化事件（后台线程, 不阻塞对话/UI）。

        触发点: ① bond 剧情闭环后（语义完整段, story_end 收尾）;
        ② mmt 会话每 N=25 轮（蓝图 §3.1, 纯 MMT 长聊窗口消化——节流非精确窗口,
        剧情中 in_vn/in_memorial 不触发, 由 _maybe_mmt_digest 保护）。
        digest 增量幂等（digested_seq 推进）——失败/跳过零损失; resume 只注入不消化。
        """
        if self._store is None or not self._session_id:
            return
        char_id = self._current_char.character_id if self._current_char else ""
        if not char_id:
            return
        threading.Thread(
            target=self._run_digest, args=(char_id, self._session_id), daemon=True,
        ).start()

    def _maybe_mmt_digest(self) -> None:
        """mmt 窗口触发检查（每轮落盘后调用; 蓝图 §3.1 N=25）:

        未到窗口 / 剧情中（in_vn/in_memorial——bond 闭环自会消化）→ 不触发。
        触发 → async_digest（后台; digest 增量, 无新增 0 调用, 撞车锁内空跑无害）。
        """
        if self._session_rounds < MMT_DIGEST_INTERVAL:
            return
        if self._session_rounds % MMT_DIGEST_INTERVAL != 0:
            return
        store = self._store
        char = self._current_char
        if store is None or char is None or not self._session_id:
            return
        try:
            st = session_status(store.events(char.character_id))
        except Exception:                            # noqa: BLE001 — 读失败不触发
            return
        if st.get("in_vn") or st.get("in_memorial"):
            return                                   # 剧情中: bond 闭环自会消化
        self.async_digest()

    def _run_digest(self, char_id: str, session_id: str) -> None:
        """后台线程: digest（同引擎串行锁）→ 提炼 + 好感结算（写 affection 事件）。"""
        try:
            with self._digest_lock:
                self._inject_brain(char_id, session_id, digest=True)
        except Exception as e:                           # noqa: BLE001
            logger.warning("异步 digest 失败 (%s/%s): %s", char_id, session_id, e)

    def resume_session(self, character_id: str, session_id: str) -> dict:
        """从事件流恢复会话（DESIGN_SAVE.md §4.2/§六）: 重建 system + history, 继续 MMT。

        store.resume → events → render_events（mmt 事件 → user/assistant 对,
        与引擎 history 同格式 `[动作名] 回复`）→ 灌入 _history → attach_session。
        ended 会话拒绝恢复（宁缺勿错）; in_vn/in_memorial 中断 → 仍恢复 MMT 上下文
        （VN/纪念中断的现场恢复后续支持, 玩家可重新触发 bond）。

        Returns: {"status": dict, "history_len": int, "display_name": str}
        """
        if self._store is None:
            raise RuntimeError(err("NotBound", "未绑定事件流存储, 无法恢复会话"))
        data = self._store.resume(character_id, session_id)
        status = data["status"]
        if status["ended"]:
            raise RuntimeError(err("ResumeRejected", "会话已结束, 不能恢复"))
        self.start_session(character_id)                  # 重建 system（人设/世界观/schema）
        if self._store is not None:                       # Brain 接线（wiki_v2）:
            self._inject_brain(character_id, session_id)  # 恢复时只注入已有 wiki（不消化——
                                                          # digest 由 async_digest 触发: bond 闭环 / mmt N=25 轮）
        history = render_events(data["events"])           # 事件流 → LLM 消息（同格式）
        self._history = history[-(self._history_rounds * 2):]
        self.attach_session(session_id)
        return {
            "status": status,
            "history_len": len(self._history),
            "display_name": self._current_char.display_name if self._current_char else "",
        }

    def clear(self) -> None:
        self._current_char = None
        self._system_prompt = ""
        self._history = []
        self._trace = []
        self.executor.set_current_character(None)
        self._session_id = ""
        self._session_rounds = 0

    # ------------------------------------------------------------------
    # 公共 API — 对话（全 JSON 动作 loop）
    # ------------------------------------------------------------------

    def agent_turn(
        self,
        user_input: str,
        *,
        system_note: str | None = None,
        record_input: bool = True,
    ) -> TurnResult:
        """一轮 agent 对话：LLM 输出**动作列表**, 逐动作执行, 直到用户可见输出。

        动作列表（2026-08-23 定稿, schema/rules 已切）: LLM 一次返回
        {"actions": [动作1, 动作2, ...]}——按序执行, 实现"说话→发图→说话"
        的混合节奏（每动作 reply 由 text_processor 各自切分渲染）。

        循环内（MAX_STEPS 步）:
            LLM 决策（json_object）→ 列表解析（含约束: inspect 不进列表 /
                trigger 独占一轮）→ **全量 parse（原子: 任一无效 → 整列表回灌）**
            → 顺序执行（执行失败 → 该动作 feedback, 本轮重试, 已执行副作用保留）
            → 全部成功 → 渲染所有步骤 + 记历史（每动作一条）+ 轮数 +1（列表整体算一轮）

        system_note: 本轮额外系统注记（只进 LLM context, 不入历史）。
        record_input: False 时不把 user_input 记入历史（自动收尾等系统触发轮）。
        """
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        self._trace = []
        brain = (self._brain_injection or "").strip()
        system = self._system_prompt
        if brain:
            system += "\n\n" + brain                   # 注入段动态拼装（digest 后下轮生效）
        messages = [{"role": "system", "content": system}]
        messages.extend(self._history)
        # 羁绊进度参考（软门槛）: 轮数注入 LLM 作判断依据, 不入历史
        messages.append({"role": "system", "content": self._bond_progress_note()})
        if system_note:
            messages.append({"role": "system", "content": system_note})
        # 随机事件（概率性, soft——低频惊喜）: 角色想说话（只进 LLM context）
        if self._store is not None:          # 事件流会话才有轮数/冷却语境
            from core.random_events import fire_event
            rand_note = fire_event(
                "want_to_speak",
                {"round": self._session_rounds, "_cooldowns": self._random_cooldowns})
            if rand_note:
                messages.append({"role": "system", "content": rand_note})
        messages.append({"role": "user", "content": user_input})

        for step in range(MAX_STEPS):
            # 1) LLM 决策（json_object 已内置 JSON 清洗与修正重试, 返回 dict）
            try:
                response = self.llm.chat(
                    messages, temperature=TEMP, max_tokens=MMT_MAX_TOKENS,
                    response_format="json_object",
                )
            except Exception as e:
                logger.warning("LLM 调用失败（step %d）: %s", step, e)
                feedback(messages, f"LLM 调用失败: {e}\n请重试。")
                continue
            messages.append({"role": "assistant", "content": str(response)})

            # 2) 列表解析（结构 + 约束违规 → feedback 整列表重试）
            raw_actions = self._parse_action_list(response, messages)
            if raw_actions is None:
                continue

            # 3) 全量 parse（原子: 任一无效 → 整列表回灌, 不执行任何动作）
            parsed: list[AgentAction] = []
            parse_ok = True
            for raw in raw_actions:
                action, result = self.registry.parse(raw)
                self._trace.append({
                    "step": step,
                    "action": action.action if action else None,
                    "summary": action.summary if action else "",
                    "reply": action.reply if action else "",
                    "payload": action.payload if action else None,
                    "parse_valid": result.is_valid,
                    "parse_errors": list(result.errors),
                })
                if not result.is_valid:
                    parse_ok = False
                    feedback(
                        messages,
                        f"动作无效: {'; '.join(result.errors)}",
                        "请严格按 schema 重新输出动作列表（所有动作都必须有效）。",
                    )
                    break
                parsed.append(action)
            if not parse_ok:
                continue

            # 4) 顺序执行（执行失败 → 该动作 feedback, 本轮重试）
            exec_results: list[ExecResult] = []
            exec_ok = True
            for i, action in enumerate(parsed):
                try:
                    exec_result = self.executor.execute(action)
                except MmtExecError as e:
                    self._trace[-1]["exec_message"] = str(e)
                    feedback(messages, str(e))
                    exec_ok = False
                    break
                self._trace[-1]["exec_ok"] = exec_result.ok
                self._trace[-1]["exec_message"] = exec_result.message
                if not exec_result.ok:
                    feedback(messages, exec_result.message)
                    exec_ok = False
                    break
                exec_results.append(exec_result)
            if not exec_ok:
                continue

            # 5) 全部成功 → 渲染全部步骤 + 历史 + TurnResult
            return self._finish_turn_list(
                parsed, exec_results, user_input, record_input)

        raise MmtLoopError(f"单轮动作循环超过 {MAX_STEPS} 步仍未产出可见回复")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _parse_action_list(self, response, messages: list[dict]) -> list[dict] | None:
        """解析 LLM 返回 → 动作列表（{"actions": [...]}）。

        结构错误 / 约束违规（inspect 混入 / trigger 不独占）→ feedback 并返回 None
        （整列表重试, 原子性）。动作字段级校验在 registry.parse（全量 parse）。
        """
        if not isinstance(response, dict):
            feedback(messages, "输出必须是 JSON 对象: {\"actions\": [动作1, 动作2, ...]}")
            return None
        raw_actions = response.get("actions")
        if not isinstance(raw_actions, list) or not raw_actions:
            feedback(messages, "actions 必须是数组（至少一个动作）")
            return None
        # 约束: inspect 是静默推理轮（查完回灌继续）, 不能混入列表
        if any(isinstance(a, dict) and a.get("action") == "mmt_inspect_character"
               for a in raw_actions):
            feedback(messages, "mmt_inspect_character 不能混入 actions 列表——它是静默推理轮, "
                               "需要单独输出一轮（查完回灌给你后继续说话）")
            return None
        # 约束: trigger 是模式切换, 必须独占一轮
        if len(raw_actions) > 1 and any(
                isinstance(a, dict) and a.get("action") == "mmt_trigger_bond_story"
                for a in raw_actions):
            feedback(messages, "mmt_trigger_bond_story 必须独占一轮（模式切换, 之后不再是手机消息）"
                               "——请单独输出它, 不要与其他动作混合")
            return None
        return raw_actions

    def _finish_turn_list(
        self,
        actions: list[AgentAction],
        exec_results: list[ExecResult],
        user_input: str,
        record_input: bool = True,
    ) -> TurnResult:
        """动作列表全部成功 → 渲染显示步骤 + 存档历史 + 组装 TurnResult。

        列表整体算一轮对话（用户一句输入 → LLM 一次返回 → N 个动作）:
            - 轮数只 +1 一次
            - 历史: 每动作一条 assistant 消息（对齐事件流: 每动作一事件）
            - steps: 每动作的 reply 气泡块拼接（媒体由 GUI 用 TurnResult.actions 渲染）
            - actions: [{action, reply, payload}] —— GUI 依序渲染媒体/切换
            - action/payload: 列表最后一个动作（兼容现有 GUI/调用方）
            - bond_story: 列表含 mmt_trigger_bond_story
        """
        display = MomoTalkOutput(_process_for_momotalk, self._current_char.display_name)
        steps: list[DisplayStep] = []
        reply_blocks: list[str] = []
        actions_view: list[dict] = []

        for action, _exec in zip(actions, exec_results):
            reply = (action.reply or "").strip()
            if reply:
                reply_blocks.append(reply)
                steps.extend(display.publish_reply(reply))
            actions_view.append({
                "action": action.action,
                "reply": reply,
                "payload": dict(action.payload),
            })

        # 历史: 每轮至少记动作名 + reply（可追溯 agent 干了什么）;
        # record_input=False（自动收尾等系统轮）不记假 user 消息, 只记回复
        # 切片回灌（与 render_events 一致）: reply 去括号 + 切块, 只第一块带动作名
        if record_input:
            self._history.append({"role": "user", "content": user_input})
        for action in actions:
            reply = (action.reply or "").strip()
            text = _strip_action_brackets(reply).strip()
            chunks = split_reply_chunks(text) if text else []
            if chunks:
                for i, chunk in enumerate(chunks):
                    prefix = f"[{action.action}] " if i == 0 else ""
                    self._history.append({"role": "assistant", "content": f"{prefix}{chunk}"})
            else:
                self._history.append({
                    "role": "assistant",
                    "content": f"[{action.action}]",
                })
        self._trim_history()

        # 列表整体算一轮 → 轮数 +1 一次（落盘跨会话累计）
        if self._current_char is not None:
            self.bond_progress.record_turn(self._current_char.character_id)

        # 事件流落盘（store 注入 + attach_session 后）: 每动作一条事件,
        # 同轮第一个动作带 player（render_events 去重约定, DESIGN_SAVE.md §4.2）
        self._record_events(actions, user_input, record_input)

        last = actions[-1]
        last_reply = (last.reply or "").strip()
        return TurnResult(
            ok=True,
            steps=steps,
            reply="\n".join(reply_blocks),
            action=last.action,
            payload=dict(last.payload),
            bond_story=any(a.action == "mmt_trigger_bond_story" for a in actions),
            actions=actions_view,
        )

    def _record_events(
        self, actions: list[AgentAction], user_input: str, record_input: bool,
    ) -> None:
        """mmt 事件流落盘（DESIGN_SAVE.md §4.2）: 每动作一条 type=mmt 事件。

        同轮第一个动作带 player（后续空 → render_events 不重复 user 消息）;
        payload = 干净动作字段 + reply; 写失败静默降级（不阻断对话）。
        """
        if self._store is None or not self._session_id:
            return
        char_id = self._current_char.character_id if self._current_char else ""
        try:
            for i, action in enumerate(actions):
                payload = dict(action.payload)
                payload["reply"] = (action.reply or "").strip()
                if i == 0 and record_input:
                    payload["player"] = user_input
                self._store.append_event(
                    char_id, self._session_id, make_event("mmt", action.action, payload))
            self._session_rounds += 1
            self._store.update_session_progress(
                char_id, self._session_id, self._session_rounds)
            # mmt 会话窗口 digest（蓝图 §3.1: 每 N=25 轮; 内部判定+剧情保护）
            self._maybe_mmt_digest()
        except Exception as e:                      # 宁缺勿错: 存档失败不阻断对话
            logger.warning("事件流落盘失败, 本轮不记录: %s", e)

    def _bond_progress_note(self) -> str:
        """本轮羁绊进度参考注记（注入 LLM context, 不入历史）。

        软门槛（2026-08-21 用户确认）: 轮数只是参考——AI 有最终裁决权,
        剧情确有需要（如老师有急事）可提前触发; 程序只在首条消息兜底
        （见 mmt_executor._execute_mmt_trigger_bond_story）。
        """
        rounds = self.bond_progress.rounds(self._char_id) if self._current_char else 0
        threshold = self.executor.affection_threshold
        return (
            f"羁绊进度参考: 与该角色已累计对话 {rounds} 轮。"
            f"一般建议至少积累 {threshold} 轮后再考虑触发羁绊剧情; "
            "但轮数仅供参考——若剧情确有需要（如老师有急事、气氛已到）, "
            "可不受轮数限制提前触发 mmt_trigger_bond_story。"
        )

    def _trim_history(self) -> None:
        max_messages = self._history_rounds * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_character(self) -> DynamicCharacter | None:
        return self._current_char

    @property
    def _char_id(self) -> str:
        return self._current_char.character_id if self._current_char else ""

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    @property
    def history_length(self) -> int:
        return len(self._history)

    @property
    def trace(self) -> list[dict]:
        """最近一轮的完整动作轨迹（每步: action/summary/reply/payload/执行结果）。"""
        return list(self._trace)
