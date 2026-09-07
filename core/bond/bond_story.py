"""羁绊剧情引擎 — 视觉小说模式对话。

与 MomoTalk 的区别:
    - 不去括号（允许动作描写）
    - 不断句（段落为单位，非气泡）
    - 不加 [名字]: 前缀（UI 层单独显示角色名）

场景契约（2026-08-22 JSON 契约化 + 双核升级, 用户拍板）:
    每场景 = 单个 story 动作 JSON: 中段 story_scene {paragraphs: [str], choices: [str]}
    或收尾 story_end {paragraphs: [str]}。is_end 由动作类型推导——story_scene 隐含
    False, story_end 隐含 True; 收尾成为一等动作, 结构上保证「收尾必无选项」。
    LLM 直接输出场景 JSON——contract.py 既规范输出也规范处理; 选项收敛到同一主线
    （无论选哪个, 剧情走向同一结局, 只影响紧接着的对白语气/细节）。
    双核（镜像 momotalk）: contract 层 core/bond/bond_actions.py（build_story_registry）
    + 执行层 core/bond/bond_executor.py（StoryExecutor/StoryExecError）, 引擎记 trace。
    BondScene 是契约解析后的程序侧结构; to_dict/from_dict 是序列化唯一路径——
    **一解析器两用**: 运行时 from_action（动作类型推导 is_end）+ 读存档 json[] 回放
    from_dict（存档显式 is_end）（DESIGN_BOND_STORY.md）。
    双空格/【选择】/【完】等自由文本标记解析已删除——结构由 JSON 字段强制。
    行为规则在 llm/prompts/bond_story_rules.md; 契约 schema 由 build_schema 注入。

用法:
    from core.bond.bond_story import BondStoryEngine
    vn = BondStoryEngine(characters_root, llm_client)
    vn.start_session("igusa_haruka")
    scene = vn.send_vn_scene("（开场）")
    for para in scene.paragraphs: ...
    if scene.choices: ...
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from contract import AgentAction, build_schema
from core.common import Live2BeError, err
from core.bond.bond_actions import MAX_SCENE_RETRIES, build_story_registry
from core.bond.emotion_annotate import annotate_emotions
from core.bond.bond_executor import StoryExecError, StoryExecutor
from core.bond.memorial_actions import build_memorial_registry
from core.bond.stream_probe import MemorialProbe
from core.media.emotion_lexicon import (
    build_emotion_injection,
    load_emotion_lexicon,
    load_place_lexicon,
)
from core.bond.place_annotate import annotate_places
from llm.client import LLMClient, feedback
from llm.task_levels import max_tokens as task_levels_max_tokens
from core.parsing.dynamic_character_parser import CharacterLoader, DynamicCharacter
from core.promptkit import (
    BlockContext,
    build_box,
    round_messages,
    task_card,
    task_card_enabled,
)
from core.session.renderer import render_bond_scene_text

logger = logging.getLogger(__name__)


def _personality_summary(char: "DynamicCharacter") -> str:
    """标注层角色人设摘要（2026-09-02）: 身份 + personality 行为逻辑要点。

    给 emotion-LLM 作人设化情绪判断基准——"逞强笑着说没事"的角色该标
    embarrassed/depressed 而非 smile。无 brief_traits → 只给身份（不注 None）。
    """
    brief = (char.personality or {}).get("SIG~brief_traits", [])
    if isinstance(brief, str):
        brief = [brief]
    lines = [f"角色: {char.display_name or char.character_id}"]
    items = [b for b in brief if isinstance(b, str) and b.strip()]
    if items:
        lines.append("性格要点（情绪判断参考, 按文本证据标, 不要硬套）:")
        lines.extend(f"- {b}" for b in items)
    return "\n".join(lines)

#: 滑动窗口默认轮数（同 momotalk——40 轮 = 80 条消息; 构造参数 history_rounds 可配）
DEFAULT_HISTORY_ROUNDS = 40
# 兼容旧名
MAX_HISTORY_ROUNDS = DEFAULT_HISTORY_ROUNDS


class SceneLoopError(Live2BeError):
    """单场景解析或执行任一失败超过 MAX_SCENE_RETRIES 仍未通过（循环必须终结, 宁缺勿错）。"""


@dataclass
class BondScene:
    """一个羁绊剧情场景（story_scene 契约解析后的程序侧结构）。

    paragraphs — 叙事段落（每项 {text, emotion?}: text=段落文本, emotion=可选表情词表键;
                  2026-08-23 架构定稿: 情绪内联进段落, 删 beats——emotion 缺省 = 延续上一段）
    choices    — 选项列表（空 = 无选项; 有选项时玩家选一个, 喂回下一场景）
    is_end     — 是否剧情结束（契约 is_end=true）
    background — 导演层视觉字段（背景 scene_id; None = 纯文本模式）
    audio      — 导演层音频字段（占位; 当前恒 None, 未来背景/音乐仲裁填）
    place      — 主 LLM 意图字段（场景级地点 scene_id, 协议 §5; None = 未标注/保持）
    memorial_prompt — memorial_enter 轮: 生图场景总结（非空 = 本场是纪念进入轮）;
                      仅运行时标记, **不进 to_dict/from_dict 序列化**（立绘走 l2d 事件）
    memorial_exit   — memorial_exit 轮: 纪念模式收尾（过渡文字）; 同上仅运行时标记
    """

    paragraphs: list[dict] = field(default_factory=list)   # [{text, emotion?}]
    choices: list[str] = field(default_factory=list)
    # 板块契约（2026-08-30）: 同响应分支内容 {选项文本: [段落…]}——玩家选该选项后
    # 立即展示（零等待, Storyloom <choice>+<branch> 模式）; 空 = 无分支
    branches: dict[str, list] = field(default_factory=dict)
    is_end: bool = False
    background: str | None = None
    audio: str | None = None
    place: str | None = None
    title: str | None = None        # 章节标题（如"预先应对"）——开场标题面板; None = 不显示
    memorial_prompt: str = ""
    memorial_exit: bool = False

    def to_dict(self) -> dict:
        """序列化为存档/契约同构 dict（回放读档的反向）。

        视觉/意图字段空值（None / 空列表）→ 省略, 不污染存档（旧档兼容）。
        """
        d = {
            "paragraphs": [dict(p) if isinstance(p, dict) else {"text": p}
                           for p in self.paragraphs],
            "choices": list(self.choices),
            "is_end": bool(self.is_end),
        }
        if self.branches:
            d["branches"] = {
                k: [dict(p) if isinstance(p, dict) else {"text": p} for p in v]
                for k, v in self.branches.items()}
        if self.background is not None:
            d["background"] = self.background
        if self.audio is not None:
            d["audio"] = self.audio
        if self.place is not None:
            d["place"] = self.place
        if self.title:
            d["title"] = self.title
        return d

    @classmethod
    def from_dict(cls, raw: dict | None) -> "BondScene":
        """宽松解析 dict → BondScene（运行时契约解析与回放读档同一条路径）。

        逐字段 .get 容错 + 过滤坏项 + is_end 缺省 False——宁缺勿错,
        坏数据不 raise, 只降级为空场景。paragraphs 兼容 str（旧档）与 {text, emotion?}。
        """
        if not isinstance(raw, dict):
            return cls()
        paras: list[dict] = []
        for p in raw.get("paragraphs", []):
            if isinstance(p, str) and p.strip():
                paras.append({"text": p.strip()})
            elif isinstance(p, dict):
                text = p.get("text")
                if isinstance(text, str) and text.strip():
                    item: dict = {"text": text.strip()}
                    emotion = p.get("emotion")
                    if isinstance(emotion, str) and emotion.strip():
                        item["emotion"] = emotion.strip()
                    paras.append(item)
        choices = [c for c in raw.get("choices", []) if isinstance(c, str)]
        branches: dict[str, list] = {}
        for k, v in (raw.get("branches") or {}).items():
            if not isinstance(k, str):
                continue
            branch_paras: list[dict] = []      # 独立变量名——不能复用 paras
            for p in v if isinstance(v, list) else []:
                if isinstance(p, str) and p.strip():
                    branch_paras.append({"text": p.strip()})
                elif isinstance(p, dict):
                    text = p.get("text")
                    if isinstance(text, str) and text.strip():
                        item: dict = {"text": text.strip()}
                        emo = p.get("emotion")
                        if isinstance(emo, str) and emo.strip():
                            item["emotion"] = emo.strip()
                        branch_paras.append(item)
            if branch_paras:
                branches[k] = branch_paras
        background = raw.get("background")
        audio = raw.get("audio")
        place = raw.get("place")
        title = raw.get("title")
        return cls(
            paragraphs=paras,
            choices=choices,
            branches=branches,
            is_end=bool(raw.get("is_end", False)),
            background=background if isinstance(background, str) else None,
            audio=audio if isinstance(audio, str) else None,
            place=place if isinstance(place, str) else None,
            title=title if isinstance(title, str) and title.strip() else None,
        )

    @classmethod
    def from_action(cls, action: "AgentAction") -> "BondScene":
        """运行时契约解析: AgentAction → BondScene, is_end 由动作类型推导。

        story_scene 隐含 is_end=False; story_end 隐含 is_end=True。payload 已过
        parse 白名单（干净字段）, 仍逐字段容错（宁缺勿错）——坏数据降级为空场景。
        memorial_enter → memorial_prompt（生图总结）; memorial_exit → memorial_exit
        标记（过渡文字; paragraphs 兼容纯字符串, exit 的 parse 输出是 [str]）。
        """
        payload = action.payload
        paras: list[dict] = []
        for p in payload.get("paragraphs", []):
            if isinstance(p, str) and p.strip():
                paras.append({"text": p.strip()})
            elif isinstance(p, dict):
                item = dict(p)
                if item.get("text"):
                    paras.append(item)
        scene = cls(
            paragraphs=paras,
            choices=[c for c in payload.get("choices", []) if isinstance(c, str)],
            branches=payload.get("branches") or {},
            is_end=(action.action == "story_end"),
            place=payload.get("place") if isinstance(payload.get("place"), str) else None,
        )
        if action.action == "memorial_enter":
            prompt = payload.get("prompt")
            if isinstance(prompt, str):
                scene.memorial_prompt = prompt
        elif action.action == "memorial_exit":
            scene.memorial_exit = True
        return scene

    def para_emotions(self, default: str = "nomal") -> list[str]:
        """逐段表情（per-para sprite, 2026-08-23 架构定稿）。

        情绪内联进 paragraphs（{text, emotion?}）——**AI 在写文本的同一时刻标注**
        （只有它知道语义）; 算法只做**确定性延续**: emotion → 用; 无 → 继承上一段;
        首段无 → default。零语义判断, 零算法猜测。
        渲染端逐段用 emotion 查 emotions.yml（catalog.sprite）拿图（表情不经导演）。
        """
        out: list[str] = []
        current = default
        for p in self.paragraphs:
            emotion = p.get("emotion") if isinstance(p, dict) else ""
            if emotion:
                current = emotion
            out.append(current)
        return out


class BondStoryEngine:
    """羁绊剧情对话引擎。

    与 MomoTalkEngine 共享相同的 LLMClient / CharacterLoader 模式，
    但输出策略不同：段落分割、不去括号、不加名字前缀。
    """

    def __init__(
        self,
        characters_root: str | Path,
        llm_client: LLMClient,
        *,
        director=None,
        brain_segment: str = "",
        character_names: list[str] | None = None,
        history_rounds: int = DEFAULT_HISTORY_ROUNDS,
        task_card: bool | None = None,   # None = settings [promptkit].task_card（默认 true）
    ):
        self.char_loader = CharacterLoader(characters_root)
        self.llm = llm_client
        self.registry = build_story_registry()
        self.memorial_registry = build_memorial_registry()
        self.executor = StoryExecutor()
        self.director = director          # 视觉导演（可注入; None = 纯文本模式）
        self._brain_segment = brain_segment   # Brain 记忆段（DESIGN_BRAIN.md）: VN 开场注入
        self._history_rounds = max(1, int(history_rounds))  # 滑动窗口（轮数, 玩家可配）
        # 称呼名单（分饰多角预留, 同 momotalk）: None = 单人（当前角色 display_name）
        self._character_names = list(character_names) if character_names else None
        self._current_char: DynamicCharacter | None = None
        self._system_prompt: str = ""
        self._history: list[dict[str, str]] = []
        self._trace: list[dict] = []      # 最近一次 send_vn_scene 的动作轨迹（追溯/调试）
        self._in_memorial = False         # 纪念子模式状态（enter 后 True, exit 后 False, §4.7）
        self._memorial_used = False       # 一段剧情至多 1 次 memorial（enter 已用 = True）
        self._lexicon_keys: list[str] = []     # 两遍式 C: 角色词表键（标注层用）
        self._lexicon_hint: str = ""           # 词表注入文本（few-shot 示范, 标注 prompt 用）
        self._character_hint: str = ""         # 角色人设摘要（标注层用, 2026-09-02:
                                               # 人设化情绪判断基准——逞强笑 ≠ smile）
        # place 标注（DESIGN_BOND_CONTRACT_V2 §5, P3a）: 地点词表 + 引擎本地
        # "当前地点"延续态（同步路径用; 异步 webgui 由 lane/state 同源维护）——
        # 锚点句写回 payload 的 place 键, 视觉键不进 LLM 上下文（renderer 忽略）
        self._place_keys: list[str] = []
        self._current_place = ""
        # 本回合任务卡（DESIGN_PROMPTKIT §4, Phase 3）: 构造参数 > settings 开关;
        # start_session 定值; 每场 kind 自推（in_memorial → memorial_exit, 否则 scene）
        self._task_card_override: bool | None = task_card
        self._task_on = True
        # 方案A-A1 选项回录（DESIGN_PROMPTKIT §5, Phase 4）: 最近一次成功动作的
        # payload（生成时落库, picked 尚不存在）——裁决后 record_picked 重渲尾部
        self._last_payload: dict | None = None

    # ------------------------------------------------------------------
    # 会话生命周期
    # ------------------------------------------------------------------

    def start_session(self, character_id: str) -> str:
        char = self.char_loader.load(character_id)

        # 盒B v2（DESIGN_PROMPTKIT §4.1, Phase 3）: 命名块清单装配——称呼行归位盒顶
        # （身份先行; 此前夹在 bond_tone 与 rules 之间）。视觉意图协议 §11 词表
        # 开场喂一遍（few-shot）; Brain 段开场注入（剧情内固定）。
        _assets_root = Path(__file__).resolve().parent.parent.parent / "assets"
        system_prompt = build_box("bond", BlockContext(
            char=char,
            names=self._character_names or [char.display_name],
            greeting_suffix="——以下是你的剧情行为规则，请严格遵守：",
            schema=build_schema(self.registry),
            brain_segment=self._brain_segment,
            assets_root=_assets_root,
        ))

        self._current_char = char
        # 两遍式 C: 角色词表键 + 注入文本（标注层用; 缺词表 → 空, 骨架不补标）
        _char_asset_dir = _assets_root / "illustration" / char.character_id / "default"
        _lex = load_emotion_lexicon(_char_asset_dir)
        self._lexicon_keys = list(_lex.keys())
        self._lexicon_hint = build_emotion_injection(_char_asset_dir)
        # 2026-09-02: 角色人设摘要（标注层情绪判断基准——personality 行为逻辑）
        self._character_hint = _personality_summary(char)
        # place 标注词表（closed; 读取失败 → 空 = 该剧情不标地点, 画面默认）;
        # 当前地点延续态重置（每个引擎实例从"未知"起, 首次变更句即起始背景）
        self._place_keys = load_place_lexicon()
        self._current_place = ""
        self._system_prompt = system_prompt
        self._history = []
        self._trace = []
        self._in_memorial = False
        self._memorial_used = False
        self._last_payload = None           # 回录基准重置（每个引擎实例新剧情）
        if self._task_card_override is None:        # 卡开关定值（会话内不变）
            self._task_on = task_card_enabled()
        else:
            self._task_on = bool(self._task_card_override)
        if self.director is not None:
            self.director.reset()        # 新会话清空视觉记忆与 nudge 计数

        logger.info("新羁绊剧情会话: %s (%s)", character_id, char.display_name)
        return char.display_name

    # ------------------------------------------------------------------
    # 对话
    # ------------------------------------------------------------------

    def send_vn_scene(
        self,
        user_input: str,
        max_tokens: int | None = None,
        system_note: str | None = None,
        annotate: bool = True,
        on_memorial_prompt: Callable[[str], None] | None = None,
    ) -> BondScene:
        """结构化场景 API：单次 LLM 调用 → BondScene（段落 + 选项 + 是否结束）。

        max_tokens: 输出上限（None → 真源 llm/task_levels.py 形态 "bond" = 8192,
        2026-09-02 集中管理; CLI 等调用方可显式传更小值覆盖）。

        LLM 直接输出 story_scene/story_end 契约 JSON（json_object 模式, 内部已有
        3 次语法自纠错）; 外层再做解析/执行重试（双核: registry.parse + executor.
        execute, 任一失败 → feedback 回灌, 最多 MAX_SCENE_RETRIES 次）, 耗尽抛
        SceneLoopError（宁缺勿错: 循环必须终结）。每轮成功/失败都记入 trace。

        system_note: 本轮系统注记（只进 context 不入历史, 最近位置最醒目）——
        双层收尾机制用: 轮数提醒 / 达上限建议收尾。None = 不注入。
        annotate: 两遍式 C——True（默认）= 同步标注（骨架缺 emotion → 批量标注
        补标后返回, CLI/测试用）; False = 只返回骨架（标注由调用方异步执行——
        webgui 用它把 emotion 解析挪出玩家等待路径, fill_scene_emotions 补标）。
        on_memorial_prompt: 方案 A 流式嗅探钩子（2026-09-01）——LLM 输出流式
        到达, MemorialProbe 在 memorial_enter 的 prompt 字段值闭合（定稿）时
        立即回调（生图与 LLM 剩余输出并行）。None = 不嗅探（原同步行为）。
        注意: 触发时动作尚未通过契约校验（频率限制/坏 JSON 可能打回）——已触发
        的生图可能作废（调用方接受浪费, 宁缺勿错）。
        """
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        self._trace = []

        # 每场动态尾（DESIGN_PROMPTKIT §2, Phase 3）: 唯一装配入口 round_messages——
        # [system(盒B)] + history + [约束注记?] + [场 task 卡] + [user]。无注记时
        # 与旧 format_messages 布局逐字节一致（format_messages 仅剩客户端公共方法）。
        notes: list[str] = []
        if system_note:                                     # 约束注记（纪念 exit schema/
            notes.append(system_note)                       # 配额/收尾提醒, webgui/vn_cli 拼）
        if self._task_on:                                   # 场卡 = 目标层（末位）
            card = task_card("bond", self._scene_task_kind(),
                             char=self._current_char.display_name
                             if self._current_char else "")
            if card:
                notes.append(card)
        messages = round_messages(
            system=self._system_prompt, history=self._history,
            notes=notes, user=user_input)
        if max_tokens is None:                       # 真源: task_levels 形态 bond
            max_tokens = task_levels_max_tokens("bond")

        for attempt in range(MAX_SCENE_RETRIES):
            # 方案 A 流式嗅探（每次 attempt 新建——重试是全新输出, 重新嗅探）
            probe = MemorialProbe(on_memorial_prompt) if on_memorial_prompt else None
            try:
                # 流式优先（chat_full = chat 的流式等价 + on_chunk 观察者）;
                # 旧 mock LLM（仅实现 chat）自动回退——嗅探随之失效, 行为与改造前一致
                chat_full = getattr(self.llm, "chat_full", None)
                if chat_full is not None:
                    response = chat_full(
                        messages, temperature=0.8, max_tokens=max_tokens,
                        response_format="json_object",
                        on_chunk=probe.feed if probe is not None else None,
                    )
                else:
                    response = self.llm.chat(
                        messages, temperature=0.8, max_tokens=max_tokens,
                        response_format="json_object",
                    )
            except Exception as e:
                logger.warning("LLM 调用失败（第 %d 次）: %s", attempt, e)
                feedback(messages, f"LLM 调用失败: {e}\n请重试。")
                continue
            messages.append({"role": "assistant", "content": str(response)})

            # 1) 契约解析（story 域优先, 未知动作名再试 memorial 域——双 registry）
            #    按**动作名归属**分流（不能按 parse 结果: parse 失败 = 动作有效但 payload
            #    非法, 仍应留在本域反馈具体错误, 而不是误判"未知动作"）
            if isinstance(response, dict) and self.registry.spec(
                    response.get("action", "")) is not None:
                action, result = self.registry.parse(response)
            elif isinstance(response, dict):
                action, result = self.memorial_registry.parse(response)
            else:
                action, result = self.registry.parse(response)
            self._trace.append({
                "attempt": attempt,
                "action": action.action if action else None,
                "summary": action.summary if action else "",
                "reply": action.reply if action else "",
                "payload": action.payload if action else None,
                "parse_valid": result.is_valid,
                "parse_errors": list(result.errors),
            })
            if not result.is_valid:
                feedback(
                    messages,
                    f"动作无效: {'; '.join(result.errors)}",
                    "请严格按 schema 重新输出可用动作 JSON（story_scene / story_end / "
                    "memorial_enter / memorial_exit）。",
                )
                continue

            # 1.5) 纪念子模式状态机约束（§4.7: enter 独占一轮含全部内容, 纪念模式内只许 exit）
            if action.action == "memorial_exit" and not self._in_memorial:
                feedback(
                    messages,
                    "动作无效: 当前不在纪念模式, memorial_exit 不可用。",
                    "请继续输出 story_scene 或 story_end。",
                )
                continue
            if action.action != "memorial_exit" and self._in_memorial:
                feedback(
                    messages,
                    "动作无效: 当前处于纪念模式, 只能输出 memorial_exit 回到 bond。",
                    "请输出 memorial_exit 动作（可选过渡文字）。",
                )
                continue
            if action.action == "memorial_enter" and self._memorial_used:
                feedback(
                    messages,
                    "动作无效: 一段剧情至多一次纪念, 已使用过。",
                    "请继续输出 story_scene 或 story_end。",
                )
                continue

            # 2) 执行确认（不可执行 → 回灌修正）
            try:
                exec_result = self.executor.execute(action)
            except StoryExecError as e:
                self._trace[-1]["exec_message"] = str(e)
                feedback(messages, str(e))
                continue
            self._trace[-1]["exec_ok"] = exec_result.ok
            self._trace[-1]["exec_message"] = exec_result.message
            break
        else:
            raise SceneLoopError(
                f"单场景解析或执行超过 {MAX_SCENE_RETRIES} 次仍未通过"
            )

        # 纪念子模式状态更新（enter → 进入; exit → 回 bond）
        if action.action == "memorial_enter":
            self._in_memorial = True
            self._memorial_used = True
        elif action.action == "memorial_exit":
            self._in_memorial = False

        # 方案A-A1 回录基准: 本场动作 payload 留存（含 choices/branches——生成时
        # picked 尚不存在; 裁决后 record_picked 重渲尾部, live 与 resume 同形）
        self._last_payload = dict(action.payload)

        self._history.append({"role": "user", "content": user_input})
        # 2026-09-05 统一窗口（DESIGN_CONTEXT_WINDOW）: 内部历史与事件流渲染同构——
        # 叙事提取（render_bond_scene_text, 与 render_events 同一函数）; 触发/恢复时
        # 外部灌入的 window_messages 与此自增历史格式一致, 滑动无缝
        hist_text = render_bond_scene_text(action.payload)
        self._history.append({"role": "assistant",
                              "content": hist_text or json.dumps(
                                  action.payload, ensure_ascii=False,
                                  separators=(",", ":"))})
        self._trim_history()
        scene = BondScene.from_action(action)
        # 两遍式 C（2026-08-31）: 骨架段落缺 emotion → 批量标注补标（生成与
        # 情绪解耦——生成不背 emotion 负担, 校验零重试; 失败静默兜底延续）。
        # 正文 + branches 段落统一处理; annotate=False 时跳过（异步标注, webgui）。
        # memorial_exit 跳过（过渡文字是纯字符串旁白, 无表情承载——不标, 前端延续）。
        if annotate and self._lexicon_keys and not scene.memorial_exit:
            try:
                self.fill_scene_emotions(scene)
            except Exception as e:             # noqa: BLE001 — 标注异常不阻断剧情
                logger.warning("emotion 标注异常（兜底延续）: %s", e)
        # place 标注（DESIGN_BOND_CONTRACT_V2 P3a, 同步路径）: 换场句锚点写回
        # payload（place 键, 稀有）; 失败静默 keep（画面保持）。webgui 异步路径
        # annotate=False → P3b 双 lane 承担。
        if annotate and self._place_keys and not scene.memorial_exit:
            try:
                self.fill_scene_places(scene)
            except Exception as e:             # noqa: BLE001 — 标注异常不阻断剧情
                logger.warning("place 标注异常（兜底保持背景）: %s", e)
        if self.director is not None:
            # 视觉导演（v2）: place 意图 → background + audio 占位
            # 表情不经导演——渲染端从段落内联 emotion 查 emotions.yml（catalog.sprite）
            vs = self.director.visual_for(scene.place, is_end=scene.is_end)
            scene.background = vs.background
            scene.audio = vs.audio
        return scene

    def fill_scene_emotions(self, scene: "BondScene") -> bool:
        """两遍式 C 标注回填（公共方法, 供异步标注调用）: 骨架段落（emotion 已由
        契约层丢弃）→ robust 全量标注（二分降级/逐项容错）并写回 scene
        （正文 + branches; 2026-09-02: 注入角色人设——人设化情绪判断基准）。
        标注失败 → 兜底延续（不 raise）。

        Returns: 是否触发过标注（False = 无词表 / memorial_exit / 无缺漏）。
        """
        if not self._lexicon_keys or scene.memorial_exit:
            return False
        from core.bond.emotion_annotate import (
            annotate_emotions_smart,
            fill_missing_emotions,
        )

        annotator = lambda sents, keys, hint, char: annotate_emotions_smart(  # noqa: E731
            self.llm, sents, keys, hint, char)
        fill_missing_emotions(scene.paragraphs, annotator=annotator,
                              lexicon_keys=self._lexicon_keys,
                              lexicon_hint=self._lexicon_hint,
                              character=self._character_hint)
        for branch in scene.branches.values():
            fill_missing_emotions(branch, annotator=annotator,
                                  lexicon_keys=self._lexicon_keys,
                                  lexicon_hint=self._lexicon_hint,
                                  character=self._character_hint)
        return True

    def fill_scene_places(self, scene: "BondScene") -> bool:
        """地点变更标注回填（DESIGN_BOND_CONTRACT_V2 §5, P3a; 公共方法供同步/
        异步调用）: 换场锚点写回正文句项（place 键, 稀有——只挂在变更句）;
        引擎本地"当前地点"延续态顺延（异步 webgui 由调用方同源维护）。

        判定语义在 place_annotate.md（镜像编剧 rules 换场判据）; 失败 → keep
        （画面保持, 不 raise）。branches/纪念文字不标（反应段与正文同场延续,
        过渡文字无承载——与 emotion 同规则）。memorial_exit 跳过。

        Returns: 是否产出锚点（False = 无词表 / memorial_exit / 无变更 / 失败）。
        """
        if not self._place_keys or scene.memorial_exit:
            return False
        texts = [(p.get("text") or "") if isinstance(p, dict) else ""
                 for p in scene.paragraphs]
        anchors = annotate_places(
            self.llm, texts, self._place_keys, self._current_place)
        for a in anchors:
            idx = a["sentence"] - 1
            if 0 <= idx < len(scene.paragraphs):
                item = scene.paragraphs[idx]
                if isinstance(item, dict):
                    item["place"] = a["place"]
        if anchors:
            self._current_place = anchors[-1]["place"]     # 延续态: 终地点
        return bool(anchors)

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_character(self) -> DynamicCharacter | None:
        return self._current_char

    @property
    def in_memorial(self) -> bool:
        """是否处于纪念子模式（enter 后 True, exit 后 False——vn_cli 据此分支渲染）。"""
        return self._in_memorial

    def memorial_exit_schema(self) -> str:
        """memorial 域 schema 文本（进入纪念模式后, vn_cli 作 system_note 注入
        给 LLM——本场可输出动作的 JSON 写法, §4.7）。"""
        return build_schema(self.memorial_registry)

    def _scene_task_kind(self) -> str:
        """场卡 kind 自推（DESIGN_PROMPTKIT §4）: 纪念模式中 → memorial_exit
        （本场唯一任务 = 退出）; 否则 scene（推进当前板块）。"""
        return "memorial_exit" if self._in_memorial else "scene"

    def record_picked(self, picked: str) -> None:
        """方案A-A1 选项回录（DESIGN_PROMPTKIT §5）: 玩家裁决写回引擎历史尾部。

        背景: 引擎历史在**生成时**落库, 当时 picked 尚不存在; 而事件流（resume/
        wrapup 预灌/replay）渲染时 payload 已带 picked → 同一场戏 live 与恢复
        看到的不同（live 缺"选择了 X"——续写靠猜的半边洞）。

        做法: 调用方在裁决消费后通知引擎, 用 render_bond_scene_text（同一函数,
        同一参数形态）重渲历史尾部该场 assistant 条目 → live 与事件流渲染
        逐字节同形。branches 内容仍不进上下文（A1, A2 留档见设计文档 §5.4）。
        未消费/无场景/空白 picked → 安全 no-op。
        """
        if not isinstance(picked, str) or not picked.strip():
            return
        if not self._last_payload or not self._history:
            return
        if self._history[-1]["role"] != "assistant":
            return
        enriched = dict(self._last_payload)
        enriched["picked"] = picked.strip()
        text = render_bond_scene_text(enriched)
        if text:
            self._history[-1]["content"] = text

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    @property
    def history_length(self) -> int:
        return len(self._history)

    @property
    def trace(self) -> list[dict]:
        """最近一次 send_vn_scene 的动作轨迹（attempt/action/payload/解析/执行结果）。"""
        return list(self._trace)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _trim_history(self) -> None:
        max_messages = self._history_rounds * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]
