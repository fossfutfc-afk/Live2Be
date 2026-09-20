"""羁绊剧情引擎 — 视觉小说模式对话。

与 MomoTalk 的区别:
    - 不去括号（允许动作描写）
    - 不断句（段落为单位，非气泡）
    - 不加 [名字]: 前缀（UI 层单独显示角色名）

场景契约（**v2 记录流, 2026-09-10 起唯一形态**）:
    一次 LLM 调用输出**一行一条 JSON 记录**（character/stage + text）; 引擎解析成块
    → 派生板（`_board_spans` / `BlockStreamParser`）→ BondScene。
    收尾 = `stage:end`; 纪念 = `stage:art` + `stage:memorial` 成对（DESIGN_MEMORIAL）。
    ⚠️ **v1 的"单动作 JSON"契约已整体退役**（2026-09-21 删除）: 原
    `core/bond/{bond_actions,bond_executor,memorial_actions,sentence_splitter}.py`
    与 `BondScene.from_action` 一并移除; 现在收到动作 dict **一律打回重发**
    （见 `send_vn_scene` 的 `isinstance(response, dict)` 分支）。
    BondScene 是解析后的程序侧结构; to_dict/from_dict 是序列化唯一路径
    （读存档 json[] 回放与运行时同一条路径）。
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

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from contract import (BlockStreamParser, CHARACTER_NARRATOR,
                      KIND_CHARACTER, MAX_SENSEI_RUN, NON_PICKS, STAGE_ART,
                      STAGE_END, STAGE_EXIT, STAGE_MEMORIAL, STAGE_SWITCH,
                      VnBlock, VnRecord, build_record_schema,
                      check_block, sensei_groups)
from core.common import Live2BeError, err
from core.media.emotion_lexicon import (
    assets_root,
    build_emotion_injection,
    load_emotion_lexicon,
    load_place_lexicon,
)
from core.media.place_table import PlaceTable, load_table
from core.bond.place_annotate import annotate_places, resolve_place
from core.bond.variant_annotate import pick_image           # 第二遍: 选图（时刻/差分）
from core.bond import place_cues                      # 换场线索词（PL3 预筛）
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

#: 单场景解析的最大重试次数（原在 `bond_actions.py`——该模块 2026-09-21 随 v1 退役删除,
#: 常量搬到唯一消费者这里; 值不变）
MAX_SCENE_RETRIES = 3

#: ⚠️ 2026-09-21 删除: 原 `LEGACY_ACTION_ENV` / `legacy_action_enabled()`——**零调用者**
#: （`grep legacy_action_enabled` 只剩定义与审计文档）。旧动作 JSON 在 `send_vn_scene`
#: 里**无条件**打回重发（见那里的 `isinstance(response, dict)` 分支）; 复活 v1 动作通道时
#: 别只删那个分支——把闸门一起加回来, 参考 git 历史里的这个开关。

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
    # 记录流 v2（2026-09-10, P0-4b）: 本板记录（真源）+ 解析记账。
    # paragraphs/choices 由记录**派生**（过渡期：老 renderer/前端照旧吃派生字段,
    # 消费者迁移见 §11 P0-7）；空 = 本场景来自旧动作路径（回放旧档/开发通道）。
    records: list[dict] = field(default_factory=list)     # [{"character"|"stage":…, "text":…}]
    notes: list[str] = field(default_factory=list)        # 解析 NOTE/DROP（可观测, 不进 LLM）
    # 记录流 v2 额外信号: 换场记录原文（P1 翻译成资产键）+ 本板是否含纪念触发 +
    # 块级画面意向（`art` 声明——本块含纪念时提前开画, §10.4）。
    # 三者都**不进 LLM 上下文**（历史渲染只出叙事/switch 文本）。
    place_hint: str | None = None
    #: **选图结果**（第二遍, 2026-09-19）: 这个地点的**哪一张图**（表 `files` 里的
    #: 相对路径, 如 `SDIR_Outer/…/BG_SchoolRooftop2_Night.jpg`）。空 = 用默认图
    #: （旧事件没有这个字段 → 回放安全, 落回第一条）。与 `place` 同属视觉键,
    #: **不进 LLM 上下文**。
    place_asset: str | None = None
    memorial: bool = False
    #: **记录级进入点**（2026-09-20, docs/DESIGN_MEMORIAL.md M3）: `stage:memorial`
    #: 那条记录在 **`paragraphs` 里的下标**——前端据此在"播到那一段时"才切黑屏
    #: （隐藏立绘 + 清空普通背景 + 图淡入）。语义见 `syncMemorial`:
    #: **这句 text 本身就是黑屏期里唯一的内容**，所以黑屏必须从它开始。
    #: None = 没有纪念记录（旧档/普通板）→ 前端按板级处理（整板即窗口）。
    memorial_at: int | None = None
    art_hint: str = ""
    #: 已裁决的选项原文（决策 #37）: 只作**展示标记**——回放/续看时前端据此把选项组
    #: 画出来（锁定 + 高亮所选）; 绝不进 paragraphs（玩家的话语只体现为选项）。
    picked: str = ""
    #: 运行时标记: 该板已在**流式**过程中交付给调用方（勿重复落地）——不进序列化
    _streamed: bool = False

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
        memorial_at: int | None = None
        for i, rec in enumerate(records):
            if i in group:
                continue
            if rec.is_stage and rec.stage in (STAGE_SWITCH, STAGE_ART, STAGE_EXIT):
                continue
            if rec.text:
                if rec.is_stage and rec.stage == STAGE_MEMORIAL:
                    # 记录级进入点（2026-09-20）: 记住它落在 paragraphs 的第几段
                    memorial_at = len(paras)
                item: dict = {"text": rec.text}
                if not rec.is_stage:
                    item["speaker"] = rec.value        # 最小说话人形态（UI 样式留 P0-7）
                paras.append(item)
        is_memorial = any(r.stage == STAGE_MEMORIAL for r in records)
        if is_memorial and memorial_at is None:
            # 触发记录没带 text（空串）⇒ 屏上没有属于它的那一句 → 退回板级
            # （整板即窗口, 与 2026-09-20 之前的行为一致; 宁缺勿错）
            memorial_at = 0
        scene = cls(
            paragraphs=paras,
            choices=[records[i].text for i in group],
            is_end=any(r.stage in (STAGE_END, STAGE_EXIT) for r in records),
            memorial=is_memorial,
            memorial_at=memorial_at,
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
        if self.memorial_at is not None:
            d["memorial_at"] = int(self.memorial_at)
        if self.art_hint:
            d["art_hint"] = self.art_hint
        if self.picked:
            d["picked"] = self.picked
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
        if self.place_asset:
            d["place_asset"] = self.place_asset
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
                    # 事件流 append-only 已定格, 回放渲染时间轴依赖它。
                    # `place_asset`（第二遍选的图）同理, 只是**段落级**。
                    pid = p.get("place")
                    if isinstance(pid, str) and pid.strip():
                        item["place"] = pid.strip()
                    passet = p.get("place_asset")
                    if isinstance(passet, str) and passet.strip():
                        item["place_asset"] = passet.strip()
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
        place_asset = raw.get("place_asset")
        art_hint = raw.get("art_hint")
        picked_raw = raw.get("picked")
        picked = (picked_raw.strip()
                  if isinstance(picked_raw, str) and picked_raw.strip() not in NON_PICKS
                  else "")
        # **不把裁决句物化进 paragraphs**（决策 #37: 玩家的话语永远只体现为选项）。
        # 它一旦当正文上屏, 配上角色的名字牌就会被读成"角色说了玩家的话"
        # （真机报障）。`picked` 随场景带着走, 供回放 UI 把**选项组**画出来并高亮
        # 所选（见 webgui `showInteraction` 的 resolved 分支）。
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
            place_asset=(place_asset.strip()
                         if isinstance(place_asset, str) and place_asset.strip() else None),
            memorial=bool(raw.get("memorial", False)),
            memorial_at=(raw.get("memorial_at")
                         if isinstance(raw.get("memorial_at"), int)
                         and raw.get("memorial_at") >= 0 else None),
            art_hint=art_hint if isinstance(art_hint, str) else "",
            picked=picked,
        )


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
        #: 最近一张纪念图的 prompt 来源（`art` / `memorial_text`）——见
        #: `_fire_memorial_image`。回调侧同步读走, 用于可归因记账（节点 C）。
        self.memorial_prompt_source = ""
        self._memorial_used = False       # 一段剧情至多 1 次 memorial（enter 已用 = True）
        self._lexicon_keys: list[str] = []     # 两遍式 C: 角色词表键（标注层用）
        self._lexicon_hint: str = ""           # 词表注入文本（few-shot 示范, 标注 prompt 用）
        self._character_hint: str = ""         # 角色人设摘要（标注层用, 2026-09-02:
                                               # 人设化情绪判断基准——逞强笑 ≠ smile）
        # place 标注（DESIGN_BOND_CONTRACT_V2 §5, P3a）: 地点语义键表 + 引擎本地
        # "当前地点"延续态（同步路径用; 异步 webgui 由 lane/state 同源维护）——
        # 锚点句写回 payload 的 place 键, 视觉键不进 LLM 上下文（renderer 忽略）。
        # `_place_table`（C2, 2026-09-19）= 层1 别名索引 + 层2 词表文本来源;
        # `_place_keys` 仍是"有没有地点能力"的门控（webgui 双路 lane 据此决定入队）
        self._place_table: "PlaceTable" = PlaceTable()
        self._place_keys: list[str] = []
        self._current_place = ""
        #: 当前画面用的那张图（表 `files` 相对路径）——第二遍"选图"的延续态:
        #: 给标注 LLM 一个"保持当前画面"的参照, 也是 `place_asset` 缺省时的回落依据
        self._current_asset = ""
        # 链记账（记录流 v2: 标注单元 = 记录, 一板一组一次调用）: 情绪标注按**板**
        # 流水——"已生效链" = 上一板记录原文 + 末条情绪; 首板退化
        # 本章 seed 锚（开场那一句, 禁后文）; 跨完整剧情衔接 = P2+ 开放项（§11）
        self._carry_text: str | None = None     # 上一板记录原文（标注情境用）
        self._carry_emo = ""                    # 链尾部情绪（carry + 板首兜底起点）
        self._seed_anchor = ""                  # 本章开场锚（首板情境; 空 = 模板通用句）
        self._group_seq = 0                     # 标注组序号（跨板递增; 日志/metrics）
        # 本回合任务卡（DESIGN_PROMPTKIT §4, Phase 3）: 构造参数 > settings 开关;
        # start_session 定值; 每场 kind 恒为 "scene"（2026-09-13 起——原
        # in_memorial → memorial_exit 分支随 v1 动作退役, 见 `_scene_task_kind`）
        self._task_card_override: bool | None = task_card
        self._task_on = True
        # 方案A-A1 选项回录（DESIGN_PROMPTKIT §5, Phase 4）: 最近一次成功动作的
        # payload（生成时落库, picked 尚不存在）——裁决后 record_picked 重渲尾部
        self._last_payload: dict | None = None
        # 记录流 v2（P0-4b）: 上一次调用切出的尾板（0 LLM 待发——记录里已经写好了
        # 后续内容, 玩家点继续即领下一板; 天然"预生成", 见 §6 板派生）
        self._pending_boards: list[BondScene] = []
        #: 可归因性（决策 #35）: 上一次 `send_vn_scene` 是否**领的待发队列**（0 LLM）
        #: ——调用方据此标注 `bond_board_deliver src=`（queue/draft 而非 gen）。
        self._served_from_pending = False

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
        # 2026-09-13: 资产根改从 media 层取（此前此处与 core/media/catalog.py 各自
        # 拼过同一个三层 parents 路径——集中到 assets_root() 一处）。
        _assets_root = assets_root()
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
        # place 标注语料（C2, 2026-09-19）——**地点语义键表优先，旧白名单兜底**:
        #   表 = `config/settings/world/place_entities.json`（168 条, 带 keywords/note）
        #   缺表/坏表 → 空表 → 回落 `_director_whitelist.json` 的 `common_scenes`（31 条裸 slug）
        # 读取失败一律降级为"该剧情不标地点, 画面保持"（宁缺勿错）。
        # 当前地点延续态重置（每个引擎实例从"未知"起, 首次变更句即起始背景）
        self._place_table = load_table()
        self._place_keys = self._place_table.keys() or load_place_lexicon()
        self._current_place = ""
        self._current_asset = ""
        # 链记账复位（每会话从零起——跨剧情 carry 是 P2+ 开放项）
        self._carry_text = None
        self._carry_emo = ""
        self._seed_anchor = ""
        self._group_seq = 0
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
        on_board: Callable[["BondScene"], None] | None = None,
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
        on_memorial_prompt: 纪念生图钩子（v2, 2026-09-12）——**一行
        `stage:memorial` 解析出来就回调**（生图与 LLM 剩余输出并行, 越早越好:
        真机生图 ~26s, 玩家读纪念正文即缓冲）; prompt = 块级 `art` 画面意向,
        缺省退化为触发句。流式路径即时触发, 非流式路径在整块解析后补触发。
        None = 不开画（纯文字降级）。**只在本轮确实出现 memorial 时才触发**
        （模型写了 `art` 预告却没兑现 → 不发图, 不浪费调用）。
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
            # 可归因性（决策 #35）: 这一板**不是本次调用生成的**——来自待发队列
            # （本回合早先那次调用切出的尾板, 或重进时草稿旁路灌回来的板）。
            # 调用方据此把 `bond_board_deliver src=` 标成 queue/draft 而不是 gen。
            self._served_from_pending = True
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
        # 记录流 v2: 输出是 **JSONL（多行多条）**——必须走 text 模式
        # （json_object = 整回复单个 JSON 对象, 且客户端会 json.loads 成 dict,
        # 反而被当成"收到的不是记录流" → 打回重发）。
        resp_format = "text"

        # ⚠️ 2026-09-13（审计 B19, **仍未修**——原因记在此处, 免得下次又踩）:
        # 曾想在这里清空 `_pending_boards`, 让"生成期间队列里没有可交付的板"成为
        # 不变式。实测**这段在队列非空时不可达**: 上面的 0-LLM 快路径
        # （`if self._pending_boards:` → `return`）会先返回。而流式交付窗口恰恰
        # 是"队列非空"的情形——本回合的板尚未解析出来, 队列里还挂着**上一回合的
        # 尾板**, 此时首板在下面的 LLM 调用中闭合即回调, webgui 的 `_draft_save`
        # 在回调里读 `_pending_boards` → 草稿混入旧板 → 进程若在此刻死掉, 重进会
        # 把旧板当"已生成未播放"续播。
        # 正确修法（待做）: 在 **webgui 侧**标记"正在生成中", 让 `_draft_boards`
        # 在生成期间不取引擎待发队列; 或把"本回合待发板"与"上一回合残留"在引擎里
        # 分成两个字段。

        for attempt in range(MAX_SCENE_RETRIES):
            # 纪念生图提前开画（v2, 2026-09-12）: v1 的 `MemorialProbe` 嗅探的是
            # `"action":"memorial_enter"` 的 prompt 字段——记录流下不存在, 所以
            # 探针已退役（模块留档, 主链不调用）。现在:**一行 `stage:memorial`
            # 解析出来就触发**（越早越好——生图真机 ~26s, 玩家读纪念正文即缓冲）,
            # prompt = 块级 `art` 画面意向（本轮首行, 通常已先到）→ 缺省用触发句。
            memorial_fired = False
            # 记录流 v2 渐进渲染（P2-1 前置）: chunk 逐行喂增量解析器, **板一闭合
            # 就回调交付**（on_board）——首板不必等整块写完（实测省 4~5s 首屏等待）。
            stream = BlockStreamParser(main_id=self._current_char.character_id
                                       if self._current_char else "",
                                       aliases=self._speaker_names()) \
                if on_board is not None else None
            delivered: list["BondScene"] = []

            def _feed(text: str) -> None:
                nonlocal memorial_fired
                if stream is None:
                    return
                stream.feed(str(text))
                # 纪念生图提前开画（v2）: 见 attempt 循环头注释。
                # ⚠️ `not self._memorial_used`: 章内第二次纪念会被
                # `_demote_repeat_memorial` 静默降级 —— 这里也不能先开画。
                if (on_memorial_prompt is not None and not memorial_fired
                        and not self._memorial_used
                        and any(r.stage == STAGE_MEMORIAL for r in stream.records)):
                    memorial_fired = True
                    self._fire_memorial_image(on_memorial_prompt,
                                              stream.records, stream.art_hint)
                for board_records in stream.pop_ready():
                    scene_b = self._scene_from_records(board_records, stream)
                    if stream.art_hint and not delivered:      # 画面意向挂首个交付板
                        scene_b.art_hint = stream.art_hint
                    if scene_b.memorial:
                        self._memorial_used = True             # 章内 ≤1（区间 = 本板）
                    scene_b._streamed = True         # 已在流中交付, 调用方勿重复落地
                    delivered.append(scene_b)
                    logger.info("[vn][stream] 板提前交付 n=%d 累计=%d",
                                len(board_records), len(delivered))
                    try:
                        on_board(scene_b)
                    except Exception as e:           # noqa: BLE001 — 交付回调异常不炸生成
                        logger.warning("流式交付回调异常（继续收集）: %s", e)

            try:
                # 流式优先（chat_full = chat 的流式等价 + on_chunk 观察者）;
                # 旧 mock LLM（仅实现 chat）自动回退——渐进渲染随之失效（行为=旧）
                chat_full = getattr(self.llm, "chat_full", None)
                if chat_full is not None:
                    response = chat_full(
                        messages, temperature=0.8, max_tokens=max_tokens,
                        response_format=resp_format,
                        on_chunk=_feed if stream is not None else None,
                    )
                else:
                    response = self.llm.chat(
                        messages, temperature=0.8, max_tokens=max_tokens,
                        response_format=resp_format,
                    )
                if stream is not None:
                    stream.finish()                  # 收残余行 + 末板
                    for board_records in stream.pop_ready():
                        scene_b = self._scene_from_records(board_records, stream)
                        if stream.art_hint and not delivered:
                            scene_b.art_hint = stream.art_hint
                        if scene_b.memorial:
                            self._memorial_used = True
                        scene_b._streamed = True
                        delivered.append(scene_b)
                        try:
                            on_board(scene_b)
                        except Exception as e:       # noqa: BLE001
                            logger.warning("流式交付回调异常（收尾）: %s", e)
            except Exception as e:
                logger.warning("LLM 调用失败（第 %d 次）: %s", attempt, e)
                feedback(messages, f"LLM 调用失败: {e}\n请重试。")
                continue
            messages.append({"role": "assistant", "content": str(response)})

            # ---- 输入形态（P0-7c 定稿）: **唯一形态 = 记录流字符串** ----
            # 旧动作 JSON（story_scene/story_end/memorial_*）彻底退役（§8.4）:
            # 收到 dict 一律打回重发——store 域动作集与双 registry 解析已不在主链上。
            if isinstance(response, dict):
                self._trace.append({
                    "attempt": attempt,
                    "action": "legacy_action_rejected",
                    "parse_valid": False,
                    "parse_errors": ["输出不是记录流（收到动作 JSON 对象）"],
                })
                feedback(
                    messages,
                    "输出形态无效: 需要一行一条 JSON 记录，收到了动作 JSON。",
                    "请按「本轮输出契约」重发整轮记录——旧动作已退役; 换场发 "
                    "stage=switch, 收尾用 stage=end, 纪念用 stage=memorial。",
                )
                continue
            if delivered:
                # 流式已交付（on_board 给过板）: **不再重复解析/交付**——校验只做记账。
                # 注: 流式下"硬违规"无法回滚（板已在玩家屏上）, 故只 trace/日志,
                # 不打回重发（真机守形 0 违规; 反馈留给上层下一轮注记）。
                issues = check_block(tuple(stream.records))
                self._trace.append({
                    "attempt": attempt, "action": "record_stream/streamed",
                    "records": len(stream.records), "boards": len(delivered),
                    "parse_valid": bool(stream.records),
                    "issues": issues, "notes": list(stream.notes),
                })
                logger.info("[vn][stream] 完成 n=%d boards=%d issues=%d%s",
                            len(stream.records), len(delivered), len(issues),
                            # 节点 1（2026-09-21）: 问题**文本**也进日志。此前只打数量,
                            # 于是 CLAUDE.md §12 那条"grep 软问题串（如'含 memorial
                            # 但没有 art'）"在生产路径上永远 grep 不到——生产走流式。
                            f" issues_txt={' | '.join(issues)}" if issues else "")
                boards = delivered
            else:
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
            # **新的一块解析成功** = v2 纪念区间（本块内）结束 → 复位子模式标志。
            # （放在这里而不是尝试循环开头: 预生成/重试可能失败, 那不是窗口结束;
            #   本块若自己又带 memorial, `_finish_scene` 会立刻再置位——章内 ≤1。）
            self._in_memorial = False
            self._pending_boards = list(boards[1:])
            # 非流式路径（无 on_board / 旧 mock LLM）: 整块解析完才知道有纪念 →
            # 这里补触发（延迟几秒, 但保证"有声明的就一定会开画"）
            if (on_memorial_prompt is not None and not memorial_fired
                    and any(getattr(sc, "memorial", False) for sc in boards)):
                memorial_fired = True
                sc = next(sc for sc in boards if sc.memorial)
                # 画面意向挂在**首个交付板**（流式与批式同规则）——合并时取任意一块的
                art = sc.art_hint or next(
                    (getattr(b, "art_hint", "") for b in boards
                     if getattr(b, "art_hint", "")), "")
                self._fire_memorial_image(on_memorial_prompt, sc.records, art)
            return self._finish_scene(boards[0], user_input, annotate=annotate)
        else:
            raise SceneLoopError(
                f"单场景解析或执行超过 {MAX_SCENE_RETRIES} 次仍未通过"
            )

    # ------------------------------------------------------------------
    # 记录流 v2（P0-4b）: 块解析 → 板派生 → 收尾
    # ------------------------------------------------------------------

    @staticmethod
    def _memorial_image_prompt(records, art_hint: str) -> str:
        """纪念生图 prompt（v2, 2026-09-12）: 块级 `art` 画面意向优先。

        `art` 是 rules 要求的"1~2 句画面意向"（**必须写清她此刻在画面里是什么样**,
        见 `bond_story_rules.md` §六 与 schema）；缺省退化用 `memorial` 触发句
        （同样是"她在做什么"的一句话, 保证画面里有主角）。都没有 → ""（不开画）。
        """
        art = (art_hint or "").strip()
        if art:
            return art
        for r in records or ():
            if isinstance(r, dict):
                stage = r.get("stage")
                text = (r.get("text") or "").strip()
            else:
                stage = getattr(r, "stage", "")
                text = (getattr(r, "text", "") or "").strip()
            if stage == STAGE_MEMORIAL and text:
                return text
        return ""

    def _fire_memorial_image(self, cb, records, art_hint: str) -> None:
        """触发纪念生图回调（v2）——回调异常不外抛（生图失败只降级纯文字, §10.2）。"""
        prompt = self._memorial_image_prompt(records, art_hint)
        if not prompt:
            logger.warning("[vn][memorial] 没拿到画面意向/触发句 → 不开画（纯文字降级）")
            return
        #: 本张图的 prompt 来源——`art` = 画面意向（配对成功）/ `memorial_text` = 降级
        #: （触发句顶替）。回调侧据此记账（gallery json 的 `prompt_source`），用来量
        #: art↔memorial **配对命中率**（docs/DESIGN_MEMORIAL.md 节点 C）。
        #: 只在 `_fire_memorial_image` 里赋值、由 cb 同步读走（同一线程内）。
        self.memorial_prompt_source = (
            "art" if (art_hint or "").strip() else "memorial_text")
        logger.info("[vn][memorial] 开画 prompt=%r src=%s",
                    prompt[:60], self.memorial_prompt_source)
        try:
            cb(prompt)
        except Exception as e:                     # noqa: BLE001 — 生图触发失败不炸生成
            logger.warning("[vn][memorial] 生图回调异常（降级纯文字）: %s", e)

    def _demote_repeat_memorial(self, records: tuple) -> tuple:
        """章内**第二次** `memorial` → **静默拒绝**（降级成旁白记录, 纪念语义全去）。

        ## 为什么补这一手（2026-09-20）

        规则书写着"**章内至多一次**（重复会被拒绝）", 但 `_memorial_used` 此前
        **只写不读**（全仓 3 处赋值、0 处读取）⇒ **同块内**的重复由契约校验挡住
        （`contract/records.py:342` 报 issue, 会反馈重试）, 而**跨块**的第二次
        一路放行: 又开一张图、又写一条 `memorial_enter`、又置 `in_memorial`
        （回忆册那边"一章多图"就是这么来的——章级缩略图只能取最后一张）。

        用户 2026-09-20: *"engine 以后遇到第二次 memo 可以直接静默拒绝"*。

        ## "静默"的准确含义

        * **不给模型反馈、不重试**（不写 `notes`/不进 feedback——那会变成反馈回环,
          与 `_system_note` 里删掉那条"请输出 memorial_exit"注记同一个理由）;
        * 只打一行 INFO 供 grep;
        * **文字照常显示**: `stage=memorial` 的记录本来就以旁白形态上屏
          （`from_board` 只跳过 switch/art/exit, 且 stage 记录不带 speaker）——
          改成 `narrator` 记录后**观感逐字节不变**, 只是不再有纪念语义:
          不置 `in_memorial` / 不写 `memorial_enter` / 不触发生图 / 不进回忆册的图列表。
        """
        if not self._memorial_used:
            return records
        if not any(getattr(r, "stage", "") == STAGE_MEMORIAL for r in records):
            return records
        logger.info("[vn][memorial] 章内第二次纪念 → 静默拒绝"
                    "（降级为旁白; 不生图/不置位/不写 marker）")
        return tuple(
            VnRecord(KIND_CHARACTER, CHARACTER_NARRATOR, r.text,
                     getattr(r, "line_no", 0))
            if getattr(r, "stage", "") == STAGE_MEMORIAL else r
            for r in records
        )

    def _scene_from_records(self, records: tuple, stream: "BlockStreamParser") -> BondScene:
        """流式板块 → BondScene（与批式 `_build_record_boards` 同语义）。

        群的判定: 板内所有 sensei 记录即本板候选（切板规则保证群在板尾）。
        """
        records = self._demote_repeat_memorial(records)
        group = tuple(i for i, r in enumerate(records) if r.is_sensei)
        return BondScene.from_board(records, group, notes=list(stream.notes))

    def _main_aliases(self) -> list[str]:
        """主角别名表（显示名 + 构造期注入的额外名字）——别名归一与 emo 标注
        "谁是自己"判定**同一份**（`contract.is_main_speaker`, 记录流 v2）。"""
        char = self._current_char
        return ([char.display_name] if char else []) + list(self._character_names or [])

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
        aliases = self._main_aliases()
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
        if soft:                                 # 超长群 → 切群; 其余（配对/章末）只记录
            logger.info("[vn][records] 软违规（不阻断）: %s", "; ".join(soft))
        if block_art and not any(r.stage == STAGE_MEMORIAL for r in block.records):
            logger.warning("[vn][records] 声明了 art 但本回合没有 memorial（降级: 不发图）")

        # `art` 是**块级声明**（本轮画面意向）——不参与板切分（否则会切出一个纯声明
        # 的空板）; 挂在含纪念的那一板上（无纪念则挂首板, 信息不丢）
        flow = tuple(r for r in block.records if r.stage != STAGE_ART)
        flow = self._demote_repeat_memorial(flow)     # 章内第二次纪念 → 静默降级
        spans = _board_spans(flow)
        if len(spans) > MAX_BOARDS_PER_TURN:
            logger.warning("[vn][records] 本回合派生 %d 板 → 只发前 %d（其余丢弃）",
                           len(spans), MAX_BOARDS_PER_TURN)
            spans = spans[:MAX_BOARDS_PER_TURN]
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
        if scene.memorial:
            # v2 纪念区间（2026-09-12）: 触发之后到**本块结束**都属于纪念正文——
            # 期间前端隐藏立绘 + 清空普通背景, 只等纪念图淡入（`syncMemorial` 读
            # `bond_status.in_memorial`）。v1 靠 `memorial_enter` 动作置位, 记录流下
            # 那条路径不存在（实测该标志永为 False → 纪念视觉整条链死掉）;
            # 复位在"要新生成一块"时（见 send_vn_scene 的 attempt 循环头）。
            self._in_memorial = True
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
        if annotate and self._lexicon_keys:
            try:
                self.fill_scene_emotions_text(scene)
            except Exception as e:             # noqa: BLE001 — 标注异常不阻断剧情
                logger.warning("emotion 标注异常（兜底延续）: %s", e)
        # place 标注（同步路径）: 换场句锚点写回（记录流路径沿用现网标注器; switch →
        # 资产键的翻译是 P1-2 的事, 本期 place_hint 只随 payload 落库）
        if annotate and self._place_keys:
            try:
                self.fill_scene_places(scene)
            except Exception as e:             # noqa: BLE001 — 标注异常不阻断剧情
                logger.warning("place 标注异常（兜底保持背景）: %s", e)
        if self.director is not None:
            # 视觉导演（v2）: place 意图 → background + audio 占位。
            # ⚠️ 传的是**资产 scene_id**（C5, 2026-09-19）: 表的语义键（`classroom`）
            # 与资产 scene_id（`class_room`）不是一回事, 而导演/catalog 吃后者。
            # `scene.place` 本身仍存**语义键**（事件流里的地点语义, 给记忆用）。
            vs = self.director.visual_for(self._place_scene_id(scene.place),
                                          is_end=scene.is_end)
            scene.background = vs.background
            scene.audio = vs.audio
        return scene

    def _place_scene_id(self, key: str | None) -> str | None:
        """地点键 → 资产 scene_id（导演/查图用）。表里没有/没 files → 原样传（老行为）。"""
        if not key:
            return key
        try:
            return self._place_table.scene_id(key) or key
        except Exception:                       # noqa: BLE001 — 翻不动就原样, 不阻断
            return key

    def fill_scene_emotions_text(self, scene: "BondScene") -> bool:
        """按**板**标注回填（公共方法——同步路径与 webgui emo lane 同一入口,
        取代整场批标 fill_scene_emotions）。

        标注单元 = **记录**（记录流 v2 P0-7b 定稿）: `scene.segments` 在 v2 恒为
        None（`_seg_ends` 只由旧动作契约 parse 产生）→ 一板 = 一组 = **一次调用**
        （真机 3~12 条; 单元 = 一条记录, 记录内多句也只给一个键）。组间链记账
        （情境 = 上一板记录原文 + 末条情绪; 首板退化 seed 锚——只给"她此刻恰好
        读到/知道"的信息, 禁后文）。失败半径 = 整板: 长度不符重试一次, 残余板内
        确定性延续（前一条键 → 板首 carry）, **永不整批 None**; 每组一条 grep
        日志 `scene_anno group=…`（§8）。branches 逐分支一组（上下文 = 主线尾板;
        不更新链——分支是主线外反应, 展示链仍以主线为准）。

        Returns: 是否触发过标注（False = 无词表 / 无正文 / 已齐）。
        """
        if not self._lexicon_keys or not scene.paragraphs:
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
        """标一板（一组记录）: 组任务（情境 + carry + 全注释词表 + 人设卡）
        → 校验回填（annotate_items 已保证长度恒等/词表内/零整批 None）。
        成功/兜底都推进链记账（§4.2: 显示链按写回实时更新——冲突以文本为准,
        正常切键由前端补切基建兜住）。异常 → 板内确定性延续, 不 raise。

        **谁进标注**（2026-09-11 定稿）: 只有**当前角色自己的记录**和**旁白**
        （无 speaker）——其他角色的台词（客串/NPC）没有差分（只有 default 一张）,
        送标注纯属浪费且会把别人的语气标到主角脸上: 它们由引擎确定性地继承
        "上一条已生效键"（立绘保持不变, 零 LLM 决策）; `sensei` 记录同理
        （v2 里它本来就是选项槽, 不进 paragraphs）。
        """
        from core.bond.emo_text import annotate_items
        from contract import is_main_speaker

        main_id = self._current_char.character_id if self._current_char else ""
        aliases = self._main_aliases()
        order: list[dict] = []                  # 板内可见项（回填顺序 = 显示顺序）
        texts: list[str] = []
        items: list[dict] = []                  # 送标注: 当前角色记录 + 旁白
        for p in group:
            if not isinstance(p, dict):
                continue
            text = (p.get("text") or "").strip()
            if not text:
                continue
            order.append(p)
            texts.append(text)
            speaker = p.get("speaker")
            own = not isinstance(speaker, str) or not speaker.strip()
            if not own and main_id:
                own = is_main_speaker(str(speaker), main_id, aliases)
            if own:
                items.append(p)
        if not order:
            return
        self._group_seq += 1                    # 标注组序号（日志/metrics/模板标题）
        prev_carry = self._carry_emo or "nomal"
        context = ""
        if self._carry_text is not None:
            context = (
                "（上一板记录原文——她刚读完的内容, 情境最近的一屏）\n"
                f"{self._carry_text}\n"
                f"（上一板末条已生效情绪: {prev_carry}）"
            )
        elif self._seed_anchor:
            context = f"（本章开场那一句——剧情锚点）\n{self._seed_anchor}"
        info = {"attempts": 0, "retry": 0, "fallback": 0}
        labels: list[str] = []
        if items:
            try:
                labels, info = annotate_items(
                    self.llm, [p["text"] for p in items],
                    self._lexicon_keys, self._lexicon_hint, self._character_hint,
                    char_name=self._current_char.display_name
                    if self._current_char else "",
                    context=context,
                    group_no=self._group_seq,
                    prev=prev_carry,
                )
            except Exception as e:              # noqa: BLE001 — 失败半径=整板
                logger.warning("emo 按板标注异常 group=%d（板内延续）: %s",
                               self._group_seq, e)
                labels = [prev_carry] * len(items)
                info = {"attempts": 0, "retry": 0, "fallback": len(items)}
        # 回填: 按显示顺序走一遍——不送标注的项继承上一条已生效键（立绘不变）
        by_item = {id(p): label for p, label in zip(items, labels)}
        cur = prev_carry
        for p in order:
            cur = by_item.get(id(p), cur)
            p["emotion"] = cur
        logger.info(
            "scene_anno group=%d n=%d npc=%d retry=%d fallback_items=%d carry=%s→%s",
            self._group_seq, len(items), len(order) - len(items),
            int(info.get("retry", 0)), int(info.get("fallback", 0)),
            prev_carry, cur)
        if chain:
            self._carry_text = "\n".join(texts)         # 已生效链: 上一板记录原文
            self._carry_emo = cur                       # + 末条已生效情绪

    def fill_scene_places(self, scene: "BondScene") -> bool:
        """地点变更回填（DESIGN_BOND_CONTRACT_V2 §5, P3a; 公共方法供同步/异步调用）。

        ## 一条路（C6, 2026-09-19）

        此前是"**二选一 + 早返回**": 板首有 `switch` 就只做 `resolve_place`、
        否则只做 `annotate_places` —— 于是 switch 板上的板内换场标不出来。
        现在**两件事都做, 顺序固定**:
          ① 板首 `switch`（writer 明说的地点）= **权威信号** → `resolve_place` →
             板级 `scene.place`（层1 别名 0 调用 / 层2 读 note 就近推测）
          ② 句级覆盖**板内后续换场**（带上 ① 之后的最新 `current_place`）

        `switch` 记录**不在 `paragraphs` 里**（`from_board` 跳过 STAGE_SWITCH）,
        所以 ② 看不到它, 不会和 ① 撞车。

        ## ② 的两道省钱闸（PL3, 2026-09-19）

        ② 的**唯一用途**是救"writer 描述了移动却没发 switch"。它此前每板恒定一次
        7022 字符调用, 而真机实测 **20 板 / 93 段正文里含换场线索词的板 = 0/20**
        （正文几乎全是对话, 位移都写在 `switch` 里）⇒ 20 次调用零收益。两道闸:

        * **闸1 线索预筛**（0 调用）: 板内没有任何换场线索词（`place_cues.has_cue`）
          → 整板跳过, 日志 `skip=no_cue`
        * **闸2 句级层1**（0 调用）: 有线索, 但**每个带线索的句子都能被表的别名唯一
          解决** → 直接落锚, 日志 `skip=layer1_hit`
        * 两道都过不了 → 照旧叫 `annotate_places`（日志 `scan cue=…`）

        ⚠️ 闸2 **从宽**: 只要有一句带线索却解决不了（歧义/表外/与当前相同）就**整板
        交 LLM** —— 省钱的代价只允许落在"确定无疑"的那些板上。

        判定语义在 `place_annotate.md`（镜像编剧 rules 换场判据）; 失败 → keep
        （画面保持, 不 raise）。branches/纪念文字不标（反应段与正文同场延续）。

        Returns: 是否有地点变化（板级 place 或任一句级锚点）。
        """
        if not self._place_keys:
            return False
        changed = False
        # ① 板首 `switch` → 板级地点（权威; 决定这一板用哪张图）
        if scene.place_hint:
            key = resolve_place(self.llm, scene.place_hint, self._place_keys,
                                self._current_place,
                                table=self._place_table)
            logger.info("[place][SWITCH] %r → %s", scene.place_hint, key or "MISS(keep)")
            if key:
                scene.place = key
                self._current_place = key
                changed = True
                # ①′ **第二遍: 选图**（时刻/天气/作者差分）——只有这个键真有别的图才发
                picked = self._pick_asset(scene.place_hint, key)
                if picked:
                    scene.place_asset = picked
        # ② 句级锚点 —— 板内后续换场（switch 板也要跑, 见 docstring）
        texts = [(p.get("text") or "") if isinstance(p, dict) else ""
                 for p in scene.paragraphs]
        anchors = self._scan_places(texts)
        for a in anchors:
            idx = a["sentence"] - 1
            if 0 <= idx < len(scene.paragraphs):
                item = scene.paragraphs[idx]
                if isinstance(item, dict):
                    item["place"] = a["place"]
                    # ②′ 锚点也是换场 ⇒ 同样要挑图（用**锚点那一句**当文本）;
                    # 选图落在**段落**上（板级 place_asset 管的是板首那一段）
                    picked = self._pick_asset(
                        texts[idx] if idx < len(texts) else "", a["place"])
                    if picked:
                        item["place_asset"] = picked
        if anchors:
            self._current_place = anchors[-1]["place"]     # 延续态: 终地点
            changed = True
        return changed

    def _pick_asset(self, text: str, key: str) -> str:
        """**第二遍选图**（板首 `switch` 与句级锚点共用）→ 表内相对路径; `""` = 保持。

        * 键只有一张图 → 不发调用（22/168）
        * 作者 `note` 与候选清单由 `pick_image` 摆进 prompt（note 就是资源说明书）
        * 失败/候选外/判不出 → `""`（保持当前画面, 宁缺勿错）
        * 顺带推进 `_current_asset` 延续态（下次调用能说"当前画面用的是…"）
        """
        entry = self._place_table.get(key) if self._place_table else None
        if entry is None:
            return ""
        picked = ""
        if len(entry.image_candidates()) > 1:
            picked = pick_image(self.llm, text, entry, current_image=self._current_asset)
            logger.info("[place][PICK] key=%s → %s", key,
                        picked.rsplit("/", 1)[-1] if picked else "保持")
        self._current_asset = picked or entry.asset() or ""
        return picked

    def _scan_places(self, texts: list[str]) -> list[dict]:
        """板内换场扫描 —— **两道 0 调用闸**先过, 过不了才叫标注 LLM（PL3）。

        见 `fill_scene_places` 的 docstring。返回 `[{sentence, place}]`。
        """
        cue = place_cues.has_cue(texts)
        if not cue:
            logger.info("[place][SKIP] skip=no_cue recs=%d", len(texts))
            return []
        quick = self._layer1_anchors(texts)
        if quick is not None:
            logger.info("[place][SKIP] skip=layer1_hit cue=%s anchors=%d",
                        cue, len(quick))
            return quick
        logger.info("[place][SCAN] cue=%s recs=%d", cue, len(texts))
        return annotate_places(
            self.llm, texts, self._place_keys, self._current_place,
            table=self._place_table)

    def _layer1_anchors(self, texts: list[str]) -> list[dict] | None:
        """**句级层1**（0 调用）: 带线索的句子**全都能被别名唯一命中** → 直接落锚。

        返回锚点列表; **任何一句不够确定**就返回 `None` = 整板交 LLM。判据从宽:

        | 该句的情况 | 处理 |
        |---|---|
        | 别名**唯一**命中且 ≠ 当前地点 | ✅ 直接锚（0 调用） |
        | 歧义（`天台` → 3 个键） | ❌ 交 LLM |
        | 表外（一个别名都不命中） | ❌ 交 LLM |
        | 唯一命中 == 当前地点 | ❌ 交 LLM |

        ⚠️ 最后一行**不能用 `place_annotate._layer1` 的"歧义∩当前 → keep"捷径**:
        句子级最常见的换场恰恰是「她拉着我**走出教室**，来到**天台**」——
        那里当前地点与目的地**同时出现**, 走捷径会把这一整板判成"不用动"
        （2026-09-19 实测踩到, 就是本函数不用 `_layer1` 的原因）。
        同理 `她走出教室`（只写离开、没写去哪）也交 LLM。
        """
        if not self._place_table:
            return None
        key_set = set(self._place_keys)
        out: list[dict] = []
        for i, t in enumerate(texts, start=1):
            if not place_cues.cue_in(t):
                continue
            hits = [p for p in self._place_table.resolve_exact(t) if p in key_set]
            if len(hits) != 1 or hits[0] == self._current_place:
                return None
            out.append({"sentence": i, "place": hits[0]})
        return out

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

    def _scene_task_kind(self) -> str:
        """场卡 kind（DESIGN_PROMPTKIT §4）——**v2 恒为 `scene`**。

        2026-09-13 修正（审计 B1）: 原实现 `"memorial_exit" if self._in_memorial
        else "scene"`。该分支在记录流 v2 下既是**死动作**又是**错指令**:

        ① 死动作——`memorial_exit` 是 v1 的独占动作, v2 只吃记录流、动作 JSON
           一律打回（见本文件 `feedback(... "请按「本轮输出契约」重发整轮记录")`）。
           同类坑已修过一次: `webgui/bond.py` 的 `_system_note` 里那条
           "请输出 memorial_exit" 注记正是为此删除的（注释写着"会打回重发 →
           反馈回环"）——任务卡这条路径漏改。
        ② 错指令（更隐蔽）——`_in_memorial` 只在**新一块解析成功后**复位
           （本文件 `self._in_memorial = False`）, 所以**构造提示词的那一刻**
           `_in_memorial=True` 的真实含义是"**上一块**含纪念", 而不是"本场在
           纪念区间内"。把它读成后者就会对着一场**新块**说"纪念已落幕"。
        ③ 而 v2 根本不需要这条指令——纪念区间 = 触发之后到**本块块尾**
           （决策 #39/#40）, 边界由块边界结构性给出; `MEMORIAL`/`END`/`EXIT`
           的写法在盒B rules 与输出契约里已有, 无需场卡再说一遍。

        故恒返回 `scene`; 模板 `task_bond_memorial_exit.md` 同时删除（已成孤儿）。
        """
        return "scene"

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
        fork._group_seq = self._group_seq
        fork._current_place = self._current_place
        fork._current_asset = self._current_asset
        fork._place_table = self._place_table      # 只读语料, 共享无妨（fork 不改它）
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
