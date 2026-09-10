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
    行为规则在 llm/prompts/bond_story_rules.md; 契约 schema 由 build_record_schema 注入
    （2026-09-10 记录流 v2——story 域不再用 build_schema 的单动作外壳）。

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

from contract import (AgentAction, CHARACTER_SENSEI, MAX_SENSEI_RUN, NON_PICKS,
                      STAGE_ART, STAGE_END, STAGE_EXIT, STAGE_MEMORIAL,
                      STAGE_SWITCH, VnBlock, build_record_schema, build_schema,
                      pick_insert_index, sensei_groups)
from core.common import Live2BeError, err
from core.bond.bond_actions import MAX_SCENE_RETRIES, build_story_registry
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

#: 一次 LLM 回合最多切几板（记录流 v2 防御: 模型写飞了也不无限排队。正常一拍
#: 2~4 个槽; 24 板 ≈ 150 条记录, 只在模型彻底失控时兜底）
MAX_BOARDS_PER_TURN = 24

#: 记录流"硬"违规 → 打回重发（形状类: 说明模型没守约, 重发值得）
HARD_BLOCK_ISSUE_MARKS = ("空块", "必须块尾", "必须块首", "首条不是 switch",
                          "纪念区间内", "条 memorial", "条 art")


def split_board_issues(issues: tuple[str, ...] | list[str]) -> tuple[list[str], list[str]]:
    """把 `check_block` 的问题清单分成 (硬, 软)。

    硬 = 形状类（块首/块尾/纪念区间/空块）→ 引擎打回重发;
    软 = sensei 群过长 → **切群**（契约是硬上限, 但为一处超长整块重发代价太大,
    切成多个 <=MAX_SENSEI_RUN 的槽即可, 内容零损失）。
    """
    hard = [i for i in issues if any(m in i for m in HARD_BLOCK_ISSUE_MARKS)]
    soft = [i for i in issues if i not in hard]
    return hard, soft


def _board_spans(records: tuple) -> list[tuple[int, int, tuple[int, ...]]]:
    """记录流块 → 板切分（P0-4b 的"板 = 引擎派生单位"最小实现）。

    板边界（§6）: ① **换场点前**（switch 记录另起一板）; ② **交互槽后**（老师的
    候选台词挂在**本板末尾**——玩家读完本板正文才看到那几个选项, 选中后下一板
    才是角色的反应, 即"槽在板尾、反应在下一板"）。超长群（>MAX_SENSEI_RUN）再
    按上限切槽 → 每板一组候选项, 内容零损失。

    Returns: [(起, 止, 本板群内记录下标)]——止为开区间; 空块 → []。
    """
    group_ends: dict[int, tuple[int, ...]] = {}
    for group in sensei_groups(records):
        for k in range(0, len(group), MAX_SENSEI_RUN):
            chunk = tuple(group[k:k + MAX_SENSEI_RUN])
            group_ends[chunk[-1]] = chunk
    spans: list[tuple[int, int, tuple[int, ...]]] = []
    start = 0
    for i, rec in enumerate(records):
        if i in group_ends:                      # 槽后收板（候选 = 本板 choices）
            spans.append((start, i + 1, group_ends[i]))
            start = i + 1
        elif i and getattr(rec, "stage", "") == STAGE_SWITCH and i > start:
            spans.append((start, i, ()))         # 换场前必切（已在板首则不重复切）
            start = i
    if start < len(records):
        spans.append((start, len(records), ()))
    return spans


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
    # SceneStream P1（2026-09-08）: 段分组边界（句平铺列表里每个自然段的终点下标）。
    # 仅引擎侧标注流水消费——**不进 to_dict/from_dict**（事件/回放不携带）
    segments: list[int] | None = None
    memorial_prompt: str = ""
    memorial_exit: bool = False
    # 记录流 v2（2026-09-10, P0-4b）: 本板记录（真源）+ 解析记账。
    # paragraphs/choices 由记录**派生**（过渡期：老 renderer/前端照旧吃派生字段,
    # 消费者迁移见 §11 P0-7）；空 = 本场景来自旧动作路径（回放旧档/开发通道）。
    records: list[dict] = field(default_factory=list)     # [{"character"|"stage":…, "text":…}]
    notes: list[str] = field(default_factory=list)        # 解析 NOTE/DROP（可观测, 不进 LLM）
    # 记录流 v2 额外信号: 换场记录原文（P1 翻译成资产键）+ 本板是否含纪念触发 +
    # 块级画面意向（`art` 声明——本块含纪念时提前开画, §10.4）。
    # 三者都**不进 LLM 上下文**（历史渲染只出叙事/switch 文本）。
    place_hint: str | None = None
    memorial: bool = False
    art_hint: str = ""

    @property
    def has_records(self) -> bool:
        return bool(self.records)

    def record_texts(self) -> list[str]:
        """各记录文本（诊断/回放用）。"""
        return [str(r.get("text", "")) for r in self.records]

    @classmethod
    def from_board(cls, records: tuple, group: tuple[int, ...] = (), *,
                   notes: list[str] | None = None) -> "BondScene":
        """一块记录（板切片）→ BondScene（记录流 v2, P0-4b）。

        - `paragraphs` **由记录派生**（一记录 = 一判定/显示单元）:
          `switch`/`art`/`exit` 是引擎信号（不显示）; 群内候选（老师的话）不显示
          ——它们变成 `choices`; 其余（角色/narrator/sensei 之外的正文）照常显示;
        - `choices` = 本板群内候选台词（run=1 也弹, 拍板 18）;
        - `is_end` = 本板含 `stage:end`/`exit`（记录是块尾, 故只可能落在末板）;
        - `records` = **真源**（含全部记录, 落库/回放用）。
        """
        paras: list[dict] = []
        for i, rec in enumerate(records):
            if i in group:
                continue
            if rec.is_stage and rec.stage in (STAGE_SWITCH, STAGE_ART, STAGE_EXIT):
                continue
            if rec.text:
                item: dict = {"text": rec.text}
                if not rec.is_stage:
                    item["speaker"] = rec.value        # 最小说话人形态（UI 样式留 P0-7）
                paras.append(item)
        scene = cls(
            paragraphs=paras,
            choices=[records[i].text for i in group],
            is_end=any(r.stage in (STAGE_END, STAGE_EXIT) for r in records),
            memorial=any(r.stage == STAGE_MEMORIAL for r in records),
            place_hint=(records[0].text if records and records[0].stage == STAGE_SWITCH
                        else None),
            records=[r.to_dict() for r in records],
            notes=list(notes or ()),
        )
        return scene

    def to_dict(self) -> dict:
        """序列化为存档/契约同构 dict（回放读档的反向）。

        视觉/意图字段空值（None / 空列表）→ 省略, 不污染存档（旧档兼容）。
        记录流板额外带 `records`（**唯一真源**）+ `notes`（可观测）。
        """
        d = {
            "paragraphs": [dict(p) if isinstance(p, dict) else {"text": p}
                           for p in self.paragraphs],
            "choices": list(self.choices),
            "is_end": bool(self.is_end),
        }
        if self.records:
            d["records"] = [dict(r) for r in self.records]
        if self.notes:
            d["notes"] = list(self.notes)
        if self.place_hint:
            d["place_hint"] = self.place_hint
        if self.memorial:
            d["memorial"] = True
        if self.art_hint:
            d["art_hint"] = self.art_hint
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
                    speaker = p.get("speaker")          # 记录流 v2: 最小说话人形态透传
                    if isinstance(speaker, str) and speaker.strip():
                        item["speaker"] = speaker.strip()
                    emotion = p.get("emotion")
                    if isinstance(emotion, str) and emotion.strip():
                        item["emotion"] = emotion.strip()
                    # 视觉键透传（P3b-2）: place 锚点（句级）随回放场景保留——
                    # 事件流 append-only 已定格, 回放渲染时间轴依赖它
                    pid = p.get("place")
                    if isinstance(pid, str) and pid.strip():
                        item["place"] = pid.strip()
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
        records = [dict(r) for r in raw.get("records", []) if isinstance(r, dict)]
        notes = [str(x) for x in raw.get("notes", []) if isinstance(x, str)]
        place_hint = raw.get("place_hint")
        art_hint = raw.get("art_hint")
        picked = raw.get("picked")
        if records and isinstance(picked, str) and picked.strip() and picked.strip() not in NON_PICKS:
            # 记录流 v2 显示层物化（P0-5）: 裁决行插回群首（派生 paragraphs 已剔除整群）
            idx = pick_insert_index(records, choices)
            paras.insert(min(idx, len(paras)),
                         {"text": picked.strip(), "speaker": CHARACTER_SENSEI})
        return cls(
            paragraphs=paras,
            choices=choices,
            branches=branches,
            is_end=bool(raw.get("is_end", False)),
            background=background if isinstance(background, str) else None,
            audio=audio if isinstance(audio, str) else None,
            place=place if isinstance(place, str) else None,
            title=title if isinstance(title, str) and title.strip() else None,
            records=records,
            notes=notes,
            place_hint=place_hint if isinstance(place_hint, str) and place_hint else None,
            memorial=bool(raw.get("memorial", False)),
            art_hint=art_hint if isinstance(art_hint, str) else "",
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
        # SceneStream P1: 段边界随 parse 结果携带（引擎侧, 不进事件/回放）
        _segs = payload.get("_seg_ends")
        if isinstance(_segs, list):
            scene.segments = [int(x) for x in _segs if isinstance(x, int) and x > 0]
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
        # SceneStream P1 链记账（DESIGN_SCENE_STREAM §4.2/§8）: 情绪标注按自然段
        # 流水——"已生效链" = 上一段原文 + 末句情绪（段 >1 情境）; 会话首段退化
        # 本章 seed 锚（开场那一句, 禁后文）; 跨完整剧情衔接 = P2+ 开放项（§11）
        self._carry_text: str | None = None     # 上一自然段原文（标注情境用）
        self._carry_emo = ""                    # 链尾部情绪（carry + 段首兜底起点）
        self._seed_anchor = ""                  # 本章开场锚（首段情境; 空 = 模板通用句）
        self._para_seq = 0                      # 自然段全局序号（跨板递增; 日志/metrics）
        # 本回合任务卡（DESIGN_PROMPTKIT §4, Phase 3）: 构造参数 > settings 开关;
        # start_session 定值; 每场 kind 自推（in_memorial → memorial_exit, 否则 scene）
        self._task_card_override: bool | None = task_card
        self._task_on = True
        # 方案A-A1 选项回录（DESIGN_PROMPTKIT §5, Phase 4）: 最近一次成功动作的
        # payload（生成时落库, picked 尚不存在）——裁决后 record_picked 重渲尾部
        self._last_payload: dict | None = None
        # SceneStream P1.5 候选草稿标记（DESIGN_CHOICE_PREGEN §2）:
        # fork_for_pick 产物 = True——消费方据此跳过重复 record_picked
        self._draft = False
        # 记录流 v2（P0-4b）: 上一次调用切出的尾板（0 LLM 待发——记录里已经写好了
        # 后续内容, 玩家点继续即领下一板; 天然"预生成", 见 §6 板派生）
        self._pending_boards: list[BondScene] = []

    # ------------------------------------------------------------------
    # 会话生命周期
    # ------------------------------------------------------------------

    def start_session(self, character_id: str) -> str:
        char = self.char_loader.load(character_id)

        # 盒B v2（DESIGN_PROMPTKIT §4.1, Phase 3）: 命名块清单装配——称呼行归位盒顶
        # （身份先行; 此前夹在 bond_tone 与 rules 之间）。视觉意图协议 §11 词表
        # 开场喂一遍（few-shot）; Brain 段开场注入（剧情内固定）。
        # 2026-09-10 记录流 v2: 契约块 = 记录文法（build_record_schema, 带真实角色 id）,
        # 标题改「本轮输出契约」——story 域不再有 action 外壳（§8.4）。
        _assets_root = Path(__file__).resolve().parent.parent.parent / "assets"
        system_prompt = build_box("bond", BlockContext(
            char=char,
            names=self._character_names or [char.display_name],
            greeting_suffix="——以下是你的剧情行为规则，请严格遵守：",
            schema=build_record_schema(char_id=char.character_id,
                                       char_display=char.display_name),
            schema_title="本轮输出契约（VN 记录流）",
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
        # SceneStream P1 链记账复位（每会话从零起——跨剧情 carry 是 P2+ 开放项）
        self._carry_text = None
        self._carry_emo = ""
        self._seed_anchor = ""
        self._para_seq = 0
        self._system_prompt = system_prompt
        self._history = []
        self._trace = []
        self._in_memorial = False
        self._memorial_used = False
        self._last_payload = None           # 回录基准重置（每个引擎实例新剧情）
        self._pending_boards = []           # 记录流待发板（同会话生命周期）
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

        max_tokens: 输出上限（None → 真源 llm/task_levels.py 形态 "bond" = 16384,
        2026-09-02 集中管理, 2026-09-10 翻倍——思考与正文共享预算且 wiki 只增不减;
        CLI 等调用方可显式传更小值覆盖）。

        LLM 直接输出 story_scene/story_end 契约 JSON（json_object 模式, 内部已有
        3 次语法自纠错）; 外层再做解析/执行重试（双核: registry.parse + executor.
        execute, 任一失败 → feedback 回灌, 最多 MAX_SCENE_RETRIES 次）, 耗尽抛
        SceneLoopError（宁缺勿错: 循环必须终结）。每轮成功/失败都记入 trace。

        system_note: 本轮系统注记（只进 context 不入历史, 最近位置最醒目）——
        双层收尾机制用: 轮数提醒 / 达上限建议收尾。None = 不注入。
        annotate: 两遍式 C——True（默认）= 同步标注（骨架缺 emotion → **按自然段
        逐段标注** fill_scene_emotions_text 补标后返回, CLI/测试用）; False = 只
        返回骨架（标注由调用方异步执行——webgui 用它把 emotion 解析挪出玩家等待
        路径, 同一 fill_scene_emotions_text 在 emo lane 补标）。
        on_memorial_prompt: 方案 A 流式嗅探钩子（2026-09-01）——LLM 输出流式
        到达, MemorialProbe 在 memorial_enter 的 prompt 字段值闭合（定稿）时
        立即回调（生图与 LLM 剩余输出并行）。None = 不嗅探（原同步行为）。
        注意: 触发时动作尚未通过契约校验（频率限制/坏 JSON 可能打回）——已触发
        的生图可能作废（调用方接受浪费, 宁缺勿错）。
        """
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        # SceneStream P1: 会话首场捕获"本章 seed 锚"（开场那一句——首段情绪标注
        # 的情境退化项; 括注指令/继续占位不算叙事锚, 留空走模板通用句）
        if not self._history and not self._seed_anchor:
            _seed = (user_input or "").strip()
            if _seed and _seed not in {"（开场）", "（继续）", "（开始）",
                                       "开场", "继续", "开始", "（进入羁绊剧情）"}:
                self._seed_anchor = _seed

        self._trace = []

        # 记录流 v2（P0-4b）: 上一回合切出的尾板——内容已在手, **0 LLM 直接发**
        # （玩家点继续即领下一板; 这是"读屏期间生成下一板"最朴素形态, §6）
        if self._pending_boards:
            scene = self._pending_boards.pop(0)
            self._trace = [{"attempt": 0, "action": "record_stream/pending",
                            "records": len(scene.records), "parse_valid": True}]
            return self._finish_scene(scene, user_input, annotate=annotate)

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
        # 记录流 v2（P0-4b）: 输出是 **JSONL（多行多条）**——不能用 json_object
        # （那是"整回复单个 JSON 对象", 且客户端会把回复 json.loads 成 dict, 反而
        # 被当成旧动作分支）。纪念子模式仍是单动作 JSON → 保持 json_object。
        resp_format = "json_object" if self._in_memorial else "text"

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
                        response_format=resp_format,
                        on_chunk=probe.feed if probe is not None else None,
                    )
                else:
                    response = self.llm.chat(
                        messages, temperature=0.8, max_tokens=max_tokens,
                        response_format=resp_format,
                    )
            except Exception as e:
                logger.warning("LLM 调用失败（第 %d 次）: %s", attempt, e)
                feedback(messages, f"LLM 调用失败: {e}\n请重试。")
                continue
            messages.append({"role": "assistant", "content": str(response)})

            # ---- 记录流 v2（P0-4b）: 字符串输出 = 记录流（真机路径）----
            # dict = 旧动作 JSON（测试桩/开发通道——P0-7 迁移后退役）; 纪念子模式
            # 仍走旧动作（memorial_exit 独占一轮; 记录流里"区间 = 本板", 该动作待退役）
            if not isinstance(response, dict) and not self._in_memorial:
                boards, hard = self._build_record_boards(str(response), attempt)
                if not boards:
                    feedback(
                        messages,
                        "记录流不合规: " + "; ".join(hard or ["空块：没有任何合法记录"]),
                        "请按「本轮输出契约」重发整轮记录: 一行一条 JSON（换场发 "
                        "stage=switch; 收尾 end 放最后一条; art 预告放首条; 老师的话连写 "
                        "1~3 条 sensei）——不要数组、不要围栏、不要动作 JSON。",
                    )
                    continue
                self._pending_boards = list(boards[1:])
                return self._finish_scene(boards[0], user_input, annotate=annotate)

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

        # 方案A-A1 回录基准 + 历史灌入 + 两遍式标注 + 导演视觉 → 统一收尾
        #（旧契约板走 payload 分支: 渲染为空时用紧凑 JSON 兜底, 保持旧行为）
        hist_text = render_bond_scene_text(action.payload)
        return self._finish_scene(
            BondScene.from_action(action), user_input, payload=action.payload,
            fallback_text=hist_text or json.dumps(action.payload, ensure_ascii=False,
                                                  separators=(",", ":")),
            annotate=annotate)

    # ------------------------------------------------------------------
    # 记录流 v2（P0-4b）: 块解析 → 板派生 → 收尾
    # ------------------------------------------------------------------

    def _speaker_names(self) -> dict[str, str]:
        """历史渲染的说话人名字表（角色 id → 显示名)——仅诊断/日志用。

        历史与回放的**唯一**渲染源是 `render_bond_scene_text(payload)`：它只看
        payload（说话人用记录里的取值，老师固定「老师」），故 live 与 resume
        逐字节同形；显示名替换是 UI 层的事（P0-7）。
        """
        char = self._current_char
        return {char.character_id: char.display_name} if char else {}

    def _build_record_boards(self, raw: str,
                             attempt: int) -> tuple[list["BondScene"], list[str]]:
        """LLM 原始记录流文本 → (板列表, 硬违规)。

        板列表首板本次发, 其余进待发队列; 每板的历史文本由
        `render_bond_scene_text(scene.to_dict())` 在交付时现算（唯一渲染源）。
        硬违规（形状类）→ 板列表为空, 由调用方 feedback 打回重发。
        """
        char = self._current_char
        main_id = char.character_id if char else ""
        aliases = ([char.display_name] if char else []) + list(self._character_names or [])
        block = VnBlock.from_text(raw, main_id=main_id, aliases=aliases)
        block_art = next((r.text for r in block.records if r.stage == STAGE_ART), "")
        hard, soft = split_board_issues(block.issues)
        drops = [n for n in block.notes if n.startswith("[DROP")]
        notes = [n for n in block.notes if not n.startswith("[DROP")]
        self._trace.append({
            "attempt": attempt,
            "action": "record_stream",
            "records": len(block.records),
            "parse_valid": bool(block.records) and not hard,
            "parse_errors": list(hard),
            "issues": list(block.issues),
            "soft": list(soft),
            "notes": notes,
            "drops": drops,
        })
        logger.info("[vn][records] attempt=%d n=%d drop=%d note=%d issues=%d%s",
                    attempt, len(block.records), len(drops), len(notes), len(block.issues),
                    f" soft={len(soft)}" if soft else "")
        for d in drops:                          # 逐条坏行（原文前 100 字在 diag 里）
            logger.warning("[vn][records] 丢行 %s", d)
        if not block.records:
            return [], ["空块：没有任何合法记录"]
        if hard:
            return [], hard
        if soft:                                 # 超长群 → 切群（内容零损失）
            logger.info("[vn][records] 软违规（已切群处理）: %s", "; ".join(soft))
        if block_art and not any(r.stage == STAGE_MEMORIAL for r in block.records):
            logger.warning("[vn][records] 声明了 art 但本回合没有 memorial（降级: 不发图）")

        # `art` 是**块级声明**（本轮画面意向）——不参与板切分（否则会切出一个纯声明
        # 的空板）; 挂在含纪念的那一板上（无纪念则挂首板, 信息不丢）
        flow = tuple(r for r in block.records if r.stage != STAGE_ART)
        spans = _board_spans(flow)
        if len(spans) > MAX_BOARDS_PER_TURN:
            logger.warning("[vn][records] 本回合派生 %d 板 → 只发前 %d（其余丢弃）",
                           len(spans), MAX_BOARDS_PER_TURN)
            spans = spans[:MAX_BOARDS_PER_TURN]
        names = self._speaker_names()
        boards: list[BondScene] = []
        spare: tuple = ()                        # 不可见板（纯 switch）→ 记录并入下一板
        for start, end, group in spans:
            slice_ = flow[start:end]
            group_local = tuple(i - start for i in group)
            if spare:                            # 真源不丢: 空板的记录挂在下一板里
                group_local = tuple(i + len(spare) for i in group_local)
                slice_ = spare + slice_
                spare = ()
            scene = BondScene.from_board(slice_, group_local, notes=list(block.notes))
            # 无可显示内容 → 并入下一板真源; 但**含 end/exit 的板必须保留**
            #（"老师一句 → 空镜 → end 留空"这类收尾组合: 段落为空也要让玩家走到黑屏）
            if not scene.paragraphs and not scene.choices and not scene.is_end:
                spare = slice_
                continue
            boards.append(scene)
        if spare:                                # 结尾只剩不可见记录 → 并入末板真源
            if boards:
                scene = boards[-1]
                scene.records = [r.to_dict() for r in spare] + scene.records
            else:
                boards.append(BondScene.from_board(spare, (), notes=list(block.notes)))
        if block_art:                            # 画面意向挂到含纪念的板（否则首板）
            target = next((s for s in boards if s.memorial), boards[0])
            target.art_hint = block_art
        if any(scene.memorial for scene in boards):
            self._memorial_used = True           # 章内 ≤1（区间 = 本板, 拍板 17: 降级为普通 VN）
            logger.info("[vn][records] 本回合含纪念触发（区间 = 本板; v2 不切模式）")
        return boards, []

    def _finish_scene(self, scene: "BondScene", user_input: str, *,
                      payload: dict | None = None, fallback_text: str = "",
                      annotate: bool = True) -> "BondScene":
        """本板收尾（回录基准 + 历史灌入 + 两遍式标注 + 导演视觉）——记录流/旧动作共用。

        历史文本一律由 `render_bond_scene_text(payload)` 现算（**唯一渲染源**——
        记录流板 = records + 未选候选剔除, 旧契约板 = paragraphs 提取）;
        `fallback_text` 仅旧契约的兜底（渲染为空时用紧凑 JSON，保持旧行为）。
        """
        # 方案A-A1 回录基准（裁决后 record_picked 用同一渲染函数 + 同一 payload 重渲尾部）:
        # 记录流板 = to_dict()（records 真源 + 派生 paragraphs/choices/speaker）
        self._last_payload = dict(payload) if payload is not None else scene.to_dict()
        self._history.append({"role": "user", "content": user_input})
        self._history.append({
            "role": "assistant",
            "content": render_bond_scene_text(self._last_payload) or fallback_text or "（……）",
        })
        self._trim_history()
        # 两遍式 C + SceneStream P1 按段流水（正文逐段标注; annotate=False → webgui emo lane）
        if annotate and self._lexicon_keys and not scene.memorial_exit:
            try:
                self.fill_scene_emotions_text(scene)
            except Exception as e:             # noqa: BLE001 — 标注异常不阻断剧情
                logger.warning("emotion 标注异常（兜底延续）: %s", e)
        # place 标注（同步路径）: 换场句锚点写回（记录流路径沿用现网标注器; switch →
        # 资产键的翻译是 P1-2 的事, 本期 place_hint 只随 payload 落库）
        if annotate and self._place_keys and not scene.memorial_exit:
            try:
                self.fill_scene_places(scene)
            except Exception as e:             # noqa: BLE001 — 标注异常不阻断剧情
                logger.warning("place 标注异常（兜底保持背景）: %s", e)
        if self.director is not None:
            # 视觉导演（v2）: place 意图 → background + audio 占位
            vs = self.director.visual_for(scene.place, is_end=scene.is_end)
            scene.background = vs.background
            scene.audio = vs.audio
        return scene

    def fill_scene_emotions_text(self, scene: "BondScene") -> bool:
        """SceneStream P1 按段标注回填（公共方法——同步路径与 webgui emo lane
        同一入口, 取代整场批标 fill_scene_emotions）。

        正文按**自然段**分组（scene.segments = parse 层累计句界, DESIGN_SCENE_
        STREAM §10: 段分组在 P1 恢复随 parse 携带）逐段小请求标注; 段间链记账
        （情境 = 上一段原文 + 末句情绪; 会话首段退化 seed 锚——只给"她此刻恰好
        读到/知道"的信息, 禁后文）。失败半径 = 单段数句——长度不符重试一次,
        残余段内确定性延续（前一句键 → 段首 carry）, **永不整批 None**; 每段
        一条 grep 日志 `scene_anno para=…`（§8）。branches 逐分支一组（上下文
        = 主线尾段; 不更新链——分支是主线外反应, 展示链仍以主线为准）。

        Returns: 是否触发过标注（False = 无词表 / memorial_exit / 无正文 / 已齐）。
        """
        if not self._lexicon_keys or scene.memorial_exit or not scene.paragraphs:
            return False
        if self._scene_emo_complete(scene):
            return False                                # 幂等: 已全带 → 不再调用
        groups: list[list[dict]] = []
        start = 0
        for end in (scene.segments or [len(scene.paragraphs)]):
            end = int(end)
            if end > start:                             # 段界不齐 → 宁缺勿错合并兜底
                groups.append(scene.paragraphs[start:end])
                start = end
        if start < len(scene.paragraphs):
            groups.append(scene.paragraphs[start:])
        for group in groups:
            self._annotate_text_group(group)
        for branch in scene.branches.values():
            if branch:
                self._annotate_text_group(branch, chain=False)
        return True

    @staticmethod
    def _scene_emo_complete(scene: "BondScene") -> bool:
        """骨架是否已全带 emotion（幂等短路——重入/晚到回填不再重复调用）。"""
        for p in scene.paragraphs:
            if isinstance(p, dict) and not (p.get("emotion") or "").strip():
                return False
        for br in scene.branches.values():
            for p in br:
                if isinstance(p, dict) and not (p.get("emotion") or "").strip():
                    return False
        return True

    def _annotate_text_group(self, group: list[dict], *, chain: bool = True) -> None:
        """标一段（自然段一组）: 组段任务（情境 + carry + 全注释词表 + 人设卡）
        → 校验回填（annotate_paragraph 已保证长度恒等/词表内/零整批 None）。
        成功/兜底都推进链记账（§4.2: 显示链按写回实时更新——冲突以文本为准,
        正常切键由前端补切基建兜住）。异常 → 段内确定性延续, 不 raise。
        """
        from core.bond.emo_text import annotate_paragraph

        sentences = [p.get("text") for p in group
                     if isinstance(p, dict) and (p.get("text") or "").strip()]
        if not sentences:
            return
        self._para_seq += 1                     # 自然段全局序号（日志/metrics/模板标题）
        prev_carry = self._carry_emo or "nomal"
        context = ""
        if self._carry_text is not None:
            context = (
                "（上一段原文——她刚读完的内容, 情境最近的一屏）\n"
                f"{self._carry_text}\n"
                f"（上一段末句已生效情绪: {prev_carry}）"
            )
        elif self._seed_anchor:
            context = f"（本章开场那一句——剧情锚点）\n{self._seed_anchor}"
        try:
            labels, info = annotate_paragraph(
                self.llm, sentences, self._lexicon_keys, self._lexicon_hint,
                self._character_hint,
                char_name=self._current_char.display_name
                if self._current_char else "",
                context=context,
                para_no=self._para_seq,
                prev=prev_carry,
            )
        except Exception as e:                  # noqa: BLE001 — 失败半径=单段
            logger.warning("emo 按段标注异常 para=%d（段内延续）: %s",
                           self._para_seq, e)
            labels = [prev_carry] * len(sentences)
            info = {"attempts": 0, "retry": 0, "fallback": len(sentences)}
        for p, label in zip(group, labels):
            if isinstance(p, dict):
                p["emotion"] = label
        tail = labels[-1] if labels else prev_carry
        logger.info(
            "scene_anno para=%d n=%d retry=%d fallback_sents=%d carry=%s→%s",
            self._para_seq, len(sentences), int(info.get("retry", 0)),
            int(info.get("fallback", 0)), prev_carry, tail)
        if chain:
            self._carry_text = "\n".join(sentences)     # 已生效链: 上一段原文
            self._carry_emo = tail                      # + 末句已生效情绪

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
        """方案A-A1 选项回录（DESIGN_PROMPTKIT §5；记录流 v2 版 = **裁决物化**）。

        背景: 引擎历史在**生成时**落库, 当时 picked 尚不存在; 而事件流（resume/
        wrapup 预灌/replay）渲染时 payload 已带 picked → 同一场戏 live 与恢复
        看到的会不同（live 缺老师那句——续写靠猜的半边洞）。

        记录流 v2: 裁决不是注解而是**物化**——被选中的候选成为群里的一条 `sensei`
        记录（`老师：X`），其余候选彻底消失; 因为 live 与回放都调
        `render_bond_scene_text`（同一 payload + picked）→ 逐字节同形（构造性成立）。
        旧契约板（无 records）保持"（选择了: X）"旧语义（旧档回放冻结）。
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

    # ------------------------------------------------------------------
    # SceneStream P1.5: 候选支 fork 原语（DESIGN_CHOICE_PREGEN §2）
    # ------------------------------------------------------------------

    def fork_for_pick(self, picked: str) -> "BondStoryEngine | None":
        """候选世界线草稿（sibling 预生成的引擎原语, 2026-09-08）。

        板块带 choices → 调用方对每个候选 fork 一个引擎, 各自后台
        send("（继续）") 预生成"选了该选项后的下一板"——玩家裁决后
        选中支直接端上, 未选支作废（草稿零落库, append-only 不受影响）。

        Fork 规则（只读面共享 + 可变面独立, DESIGN_CHOICE_PREGEN §2）:
          - 共享: llm / _system_prompt（同字节 → 跨支前缀缓存成立的关键）/
            char_loader / registry / lexicon / 人设卡 / 词表
          - 独立: _history（**尾部 A1 同形回录** "（选择了: X）"——与
            record_picked 同一渲染函数, live 历史原样不动）; 标注链
            carry/seed/para_seq（两路链分岔预期内）; place 延续态;
            视觉导演克隆（catalog 只读 + _state 延续记忆——两路视觉
            记忆互不污染）
          - _draft 标记: 消费方据此跳过重复 record_picked（fork 历史已内嵌）

        Returns: fork 引擎; 守卫失败（未开场/无上一板/无 payload/空白
        picked/纪念模式中）→ None（安全 no-op）。
        """
        if (self._current_char is None or not self._history
                or not self._last_payload or not isinstance(picked, str)
                or not picked.strip() or self._in_memorial):
            return None
        import copy as _copy

        fork = object.__new__(BondStoryEngine)   # 免构造: 属性面逐项复制
        fork.__dict__.update(self.__dict__)      # 只读面共享（含 _system_prompt）
        # ---- 可变/独立面 ----
        fork._history = _copy.deepcopy(self._history)
        fork._trace = []
        fork._last_payload = dict(self._last_payload)   # 尾部重渲基准
        fork._carry_text = self._carry_text
        fork._carry_emo = self._carry_emo
        fork._seed_anchor = self._seed_anchor
        fork._para_seq = self._para_seq
        fork._current_place = self._current_place
        fork._in_memorial = False                # 守卫已排除 True
        fork._memorial_used = self._memorial_used
        fork._task_on = self._task_on
        # A1 同形回录（fork 生成的下一板必须已见裁决行; live 零污染）
        if fork._history[-1]["role"] == "assistant":
            enriched = dict(fork._last_payload)
            enriched["picked"] = picked.strip()
            text = render_bond_scene_text(enriched)
            if text:
                fork._history[-1]["content"] = text
        # 视觉导演克隆: catalog/char/default 只读共享, 视觉记忆独立延续。
        # 仅支持标准 Director 形态（catalog/char_id/default_background 构造
        # 面）; 自定义 director 无法克隆 → 降级 None（宁缺勿错——webgui 端
        # 有 _resolve_scene/fallback 兜底, 候选支背景短暂缺省可接受）
        if self.director is not None:
            try:
                d = self.director
                clone = d.__class__(
                    catalog=d.catalog, char_id=d.char_id,
                    default_background=d.default_background)
                clone._state = d._state          # VisualState 不可变 → 共享起点
                fork.director = clone
            except Exception as e:               # noqa: BLE001
                logger.warning("fork 导演克隆失败（候选支降级无导演）: %s", e)
                fork.director = None
        fork._draft = True                       # 候选草稿标记（消费方语义用）
        return fork

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
