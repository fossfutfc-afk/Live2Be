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
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from contract import (BlockStreamParser, CHARACTER_NARRATOR, Issue,
                      IssueCode, KIND_CHARACTER, MAX_SENSEI_RUN, NON_PICKS,
                      STAGE_ART, STAGE_END, STAGE_EXIT, STAGE_MEMORIAL,
                      STAGE_SWITCH, VnBlock, VnRecord, build_record_schema,
                      check_board, check_block, format_issues, sensei_groups,
                      split_issues)
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
from llm.task_labels import BOND
from llm.task_levels import max_tokens as task_levels_max_tokens
from core.parsing.dynamic_character_parser import CharacterLoader, DynamicCharacter
from core.parsing.names import names_of        # 名字接口（N1）
from core.promptkit import (
    BlockContext,
    build_box,
    round_messages,
    task_card,
    task_card_enabled,
)
from core.session.renderer import render_bond_scene_text

from core.bond.bond_story.boards import (
    DeliveryMode,
    _BoardAssembler,
    _board_spans,
)

from core.bond.bond_story.scene import (
    BondScene,
    SceneLoopError,
)

logger = logging.getLogger(__name__)

#: 一次 LLM 回合最多切几板（记录流 v2 防御: 模型写飞了也不无限排队。正常一拍
#: 2~4 个槽; 24 板 ≈ 150 条记录, 只在模型彻底失控时兜底）

#: 单场景解析的最大重试次数（原在 `bond_actions.py`——该模块 2026-09-21 随 v1 退役删除,
#: 常量搬到唯一消费者这里; 值不变）
MAX_SCENE_RETRIES = 3

#: ⚠️ 2026-09-21 删除: 原 `LEGACY_ACTION_ENV` / `legacy_action_enabled()`——**零调用者**
#: （`grep legacy_action_enabled` 只剩定义与审计文档）。旧动作 JSON 在 `send_vn_scene`
#: 里**无条件**打回重发（见那里的 `isinstance(response, dict)` 分支）; 复活 v1 动作通道时
#: 别只删那个分支——把闸门一起加回来, 参考 git 历史里的这个开关。

#: 记录流"硬"违规 → 打回重发（形状类: 说明模型没守约, 重发值得）。
#: ⚠️ 2026-09-21（节点 6）: 原来这里是一张**中文标记串**表（`HARD_BLOCK_ISSUE_MARKS`），
#: 由 `split_board_issues` 做子串匹配判硬软——给软问题换个措辞就可能静默变成"整轮
#: 重发"（ARCH_REVIEW P0-3）。现在分级是 `contract.records.ISSUE_SEVERITY` 里
#: `IssueCode → IssueSeverity` 的显式声明，`split_issues` 只读 `Issue.severity`。
#: 本文件**不再**有任何按问题文案判分级的代码（`tests/core/test_records.py` 有守门用例）。


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

#: 纪念总开关的环境变量（同 `LIVE2BE_IMAGE` 的约定: 进程级, 优先于配置文件）
MEMORIAL_ENV = "LIVE2BE_MEMORIAL"


def memorial_allowed() -> bool:
    """**纪念总开关**（2026-09-23）: 环境变量 `LIVE2BE_MEMORIAL` > settings `[bond].memorial` > 默认 True。

    关掉的效果 = **桥段降级为旁白、画不画都不谈**:
    `stage:memorial` 记录被静默降级（不置 `in_memorial` / 不写 `memorial_enter` /
    不触发生图 / 不进回忆册）, **文字照常上屏**——观感与"章内第二次纪念"的既有
    降级完全一致（复用同一条通道, 见 `_demote_repeat_memorial`）。

    ⚠️ 与 `[image].enabled`（生图总开关）**不是一回事**: 那个关掉后纪念演出照旧
    （仍黑屏 + 转场句, 只是没插画）; 本开关关掉后**连桥段一起没有**。

    读取失败/缺省 → True（与 `choice_pregen`/`image_enabled` 同一姿势: 不配 = 现状）。
    """
    import os
    env = str(os.environ.get(MEMORIAL_ENV, "") or "").strip().lower()
    if env in ("off", "0", "false", "no"):
        return False
    if env in ("on", "1", "true", "yes"):
        return True
    try:
        import tomllib
        from core import paths
        text = paths.SETTINGS_PATH.read_text(encoding="utf-8")
        cfg = (tomllib.loads(text).get("bond") or {})
        val = cfg.get("memorial", True)
        return bool(val) if isinstance(val, bool) else True
    except Exception:                              # noqa: BLE001 — 缺省开
        return True


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
        memorial_enabled: bool | None = None,   # None = settings [bond].memorial（默认 true）
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
        #: **纪念总开关**（2026-09-23）: 关 → 所有 `stage:memorial` 记录静默降级为旁白
        #: （不置位 / 不写 marker / 不触发生图 / 不进回忆册; **文字照常上屏**）。
        #: 判据复用 M5 的既有降级通道（`_demote_repeat_memorial`）——不是新机制。
        self._memorial_enabled = (memorial_allowed() if memorial_enabled is None
                                  else bool(memorial_enabled))
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
        #: 上一块留下的**形状问题**（节点 3, 2026-09-21）: 流式下**已交付**的板拦不住
        #: （打回重发会产出另一段文本 = 玩家看到"同一段戏讲两遍", 见
        #: `docs/DESIGN_RESEND.md` §3）→ 改成**下一轮注记纠偏**: 把问题带到下一轮,
        #: 让你模型自己避免。一次性（下轮注入后即清）; 干净块也会清。
        self._pending_feedback: list[Issue] = []

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
        readahead: bool = False,
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
        readahead: ⭐ **链式读前**（2026-10-08）—— True = **跳过"领队列"早返回,
        强制生成新的一块**（并把它的板**追加**到待发队列尾部, 不动玩家还没读完的板）。
        为什么需要这个开关: 下面那条早返回是"队列有货就先发队列"（玩家点继续的正常
        路径）; 读前生成是在**队列非空**时故意再写一块排到后面, 语义完全不同。
        ⚠️ 只有 `_pregenerate` 传 True; 默认 False ⇒ 现有调用方零影响。
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
        # ⚠️ `readahead=True` 时**跳过**这一支（读前要的是"再写一块", 不是"发一块"）
        if self._pending_boards and not readahead:
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
        if self._memorial_used:
            # ⭐ 2026-10-08（用户裁决"加这条提示"）: 章内**已经用过**纪念插画 ——
            #    `_memorial_used` 从前**只写不读**（第二次 memorial 由
            #    `_demote_repeat_memorial` 静默丢弃, 有意**不给反馈**以免反馈回环,
            #    见那里的 docstring）。代价是 writer 每块都可能再写一次 memorial/art
            #    ——**白写**（图与 marker 都不会出）。真机 2026-10-08 就中过一次
            #    （`[vn][memorial] 章内第二次纪念 → 静默拒绝`）。
            #    这条是**静态事实**（"本章用过没"）, 不是"你上一轮写错了"那种纠偏
            #    ⇒ 不构成回环; 只进动态尾（notes）, 不碰 system 盒（前缀缓存安全）。
            notes.append(
                "（系统）本章的纪念插画**已经用过了**（一章至多一次）："
                "不要再写 stage=art / stage=memorial——重复的会被丢弃，"
                "画面与回执都不会产生; 把这一段写成本章的后日谈/收束即可。")
        if self._pending_feedback:
            # 节点 3（2026-09-21）: 上一轮**已交付**但形状有问题（流式拦不住, 见
            # `DeliveryMode.STREAM`）→ 下一轮明说一次让模型纠偏; **一次性消费**
            # （此处清空, 下一轮若仍脏会重新置上）。放在场卡之前, 保持场卡在末位。
            # 注入的是 `Issue.message`（人读中文）——给模型看的, 不是码。
            notes.append(
                "（系统）上一轮输出的**形状**有这些问题: "
                + format_issues(self._pending_feedback)
                + "。本轮请避免（形状规则见「本轮输出契约」）。")
            self._pending_feedback = []
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
            # 交付模式（节点 2′）: 流式 = 增量交付（板级闸只在首板交付前拦）;
            # 批式 = 整块交付（板级 + 块级全拦）。写进 trace 便于事后归因。
            mode = DeliveryMode.STREAM if stream is not None else DeliveryMode.BLOCK
            # 节点 2′: 板装配统一走 `_BoardAssembler`（与批式同一套语义）
            asm = _BoardAssembler(self)
            gate_issues: list[str] = []      # 板级闸拦下的违规（本 attempt 作废）

            def _deliver(boards_now: list["BondScene"]) -> None:
                for scene_b in boards_now:
                    scene_b._streamed = True     # 已在流中交付, 调用方勿重复落地
                    delivered.append(scene_b)
                    logger.info("[vn][stream] 板提前交付 n=%d 累计=%d",
                                len(scene_b.records), len(delivered))
                    try:
                        on_board(scene_b)
                    except Exception as e:       # noqa: BLE001 — 交付回调异常不炸生成
                        logger.warning("流式交付回调异常（继续收集）: %s", e)

            def _accept(board_records) -> None:
                """收一块**已闭合**的板: 过板级闸 → 装配 → 交付。

                板级闸（`check_board`）**只在还没交付过任何板时拦**——那一板还没上屏,
                拦得住; 一旦交付过 → 一律 advisory（打回重发会产出另一段文本,
                玩家侧表现为"同一段戏讲两遍", 见 docs/DESIGN_RESEND.md §3）。
                """
                if gate_issues:                  # 本 attempt 已作废, 后续板不再交付
                    return
                issues = check_board(board_records)
                if issues:
                    if not delivered and mode is DeliveryMode.STREAM:
                        gate_issues.extend(issues)
                        logger.warning(
                            "[vn][stream] 板级闸拦下首板（本 attempt 作废, 打回重发）: %s",
                            format_issues(issues))
                        return
                    logger.warning("[vn][stream] 板级违规（已交付 → 只记账, 不回滚）: %s",
                                   format_issues(issues))
                asm.set_block_art(stream.art_hint)
                asm.set_notes(stream.notes)
                _deliver(asm.push(board_records))

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
                    _accept(board_records)

            try:
                # 流式优先（chat_full = chat 的流式等价 + on_chunk 观察者）;
                # 旧 mock LLM（仅实现 chat）自动回退——渐进渲染随之失效（行为=旧）
                chat_full = getattr(self.llm, "chat_full", None)
                if chat_full is not None:
                    response = chat_full(
                        messages, temperature=0.8, max_tokens=max_tokens,
                        response_format=resp_format,
                        on_chunk=_feed if stream is not None else None,
                        task=BOND,       # 主链调用身份（节点 5b: 桩按它分派）
                    )
                else:
                    response = self.llm.chat(
                        messages, temperature=0.8, max_tokens=max_tokens,
                        response_format=resp_format,
                        task=BOND,
                    )
                if stream is not None:
                    stream.finish()                  # 收残余行 + 末板
                    for board_records in stream.pop_ready():
                        _accept(board_records)
                    if not gate_issues:              # 块尾: 挂起的不可见板照原样成板
                        asm.set_block_art(stream.art_hint)
                        asm.set_notes(stream.notes)
                        _deliver(asm.finish())
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
            if mode is DeliveryMode.STREAM and gate_issues:
                # 板级闸（DeliveryMode.STREAM）: 首板形状违规 → 本 attempt **一块都没交付**,
                # 打回重发整轮——板没上屏, 所以拦得住（与批式的"硬违规打回"同语义）。
                self._trace.append({
                    "attempt": attempt, "action": "record_stream/board_gate",
                    "delivery_mode": mode.value,
                    "parse_valid": False,
                    # trace 保持 JSON 友好: 人读文本 + 机器码各一份
                    "parse_errors": [str(i) for i in gate_issues],
                    "issue_codes": [i.code.value for i in gate_issues],
                })
                feedback(
                    messages,
                    "板级校验失败: " + format_issues(gate_issues),
                    "请按「本轮输出契约」重发整轮记录: end 必须放最后一条; "
                    "每轮至多一条 memorial, 且它之后不要再换场（switch）。",
                )
                continue
            if delivered:
                # 流式已交付（on_board 给过板）: **不再重复解析/交付**——校验只做记账。
                # 注: 流式下"硬违规"无法回滚（板已在玩家屏上）, 故只 trace/日志,
                # 不打回重发（真机守形 0 违规）。
                # 节点 3（2026-09-21）: 记账 → **下一轮注记纠偏**（`_pending_feedback`,
                # 见 notes 装配处）——这是"拦不住"之下唯一还能纠偏的通道。
                issues = check_block(tuple(stream.records))
                self._trace.append({
                    "attempt": attempt, "action": "record_stream/streamed",
                    "delivery_mode": mode.value,
                    "records": len(stream.records), "boards": len(delivered),
                    "parse_valid": bool(stream.records),
                    "issues": [str(i) for i in issues],
                    "issue_codes": [i.code.value for i in issues],
                    "notes": list(stream.notes),
                })
                logger.info("[vn][stream] 完成 n=%d boards=%d issues=%d%s",
                            len(stream.records), len(delivered), len(issues),
                            # 节点 1（2026-09-21）: 问题**文本**也进日志。此前只打数量,
                            # 于是 CLAUDE.md §12 那条"grep 软问题串（如'含 memorial
                            # 但没有 art'）"在生产路径上永远 grep 不到——生产走流式。
                            f" issues_txt={format_issues(issues, ' | ')}" if issues else "")
                # 节点 3: 记账 → **下一轮纠偏**（下一轮 notes 注入一次后自清）
                self._pending_feedback = list(issues)
                boards = delivered
            else:
                boards, hard = self._build_record_boards(str(response), attempt)
                if not boards:
                    feedback(
                        messages,
                        "记录流不合规: "
                        + (format_issues(hard) or "空块：没有任何合法记录"),
                        "请按「本轮输出契约」重发整轮记录: 一行一条 JSON（换场发 "
                        "stage=switch; 收尾 end 放最后一条; art 预告放首条; 老师的话连写 "
                        "1~3 条 sensei）——不要数组、不要围栏、不要动作 JSON。",
                    )
                    continue
            # **新的一块解析成功** = v2 纪念区间（本块内）结束 → 复位子模式标志。
            # （放在这里而不是尝试循环开头: 预生成/重试可能失败, 那不是窗口结束;
            #   本块若自己又带 memorial, `_finish_scene` 会立刻再置位——章内 ≤1。）
            self._in_memorial = False
            # ⭐ 2026-10-08（链式读前）: **追加, 不是赋值** —— 待发队列从此允许**跨块累积**
            #    （读前生成的那一块排在"玩家还没读完的板"**后面**）。
            #    为什么今天两条写法等价: 走到这里就意味着**队列是空的** —— 函数开头
            #    `if self._pending_boards: … pop(0) … return` 会先返回。所以 `extend`
            #    在现有调用形态下与 `list(...)` 逐字节同效, 只是**多了一种情况能用**:
            #    读前生成时不会把上一块没读的板整段丢掉。
            #    ⛔ **别改回 `=`**: 那会让"提前生成的下一块"把玩家的待读板清空
            #    （守门 `tests/core/test_bond_pending_append.py` 会当场红）。
            self._pending_boards.extend(boards[1:])
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
        if not any(getattr(r, "stage", "") == STAGE_MEMORIAL for r in records):
            return records
        if not self._memorial_enabled:
            # 总开关为关（2026-09-23）: 与"章内第二次"走**同一条**降级通道 ——
            # 文字照常上屏, 只是不再有纪念语义（不生图/不置位/不写 marker/不进回忆册）。
            logger.info("[vn][memorial] 总开关为关 → 静默降级为旁白"
                        "（settings [bond].memorial=false / LIVE2BE_MEMORIAL=off）")
        elif self._memorial_used:
            logger.info("[vn][memorial] 章内第二次纪念 → 静默拒绝"
                        "（降级为旁白; 不生图/不置位/不写 marker）")
        else:
            return records
        return tuple(
            VnRecord(KIND_CHARACTER, CHARACTER_NARRATOR, r.text,
                     getattr(r, "line_no", 0))
            if getattr(r, "stage", "") == STAGE_MEMORIAL else r
            for r in records
        )

    def _main_aliases(self) -> list[str]:
        """主角别名表（显示名 + 构造期注入的额外名字）——别名归一与 emo 标注
        "谁是自己"判定**同一份**（`contract.is_main_speaker`, 记录流 v2）。"""
        char = self._current_char
        return ([char.display_name] if char else []) + list(self._character_names or [])

    def _speaker_names(self) -> dict[str, str]:
        """**流式解析器**的说话人名字表（角色 id → 显示名）——别名归一动用。

        ⚠️ 这里**只给自己一个键**（不给 `sensei`/`narrator`）: 解析器拿它做别名归一,
        多塞键会改变归一结果。读名字的实现已收敛到 `core.parsing.names`（N1）——
        本方法是那张**表**的构造, 不再是"怎么读人设"的第二份实现。
        """
        char = self._current_char
        if char is None:
            return {}
        return {char.character_id: names_of(char).display}

    def _build_record_boards(self, raw: str,
                             attempt: int) -> tuple[list["BondScene"], list[Issue]]:
        """LLM 原始记录流文本 → (板列表, 硬违规 `Issue` 清单)。

        板列表首板本次发, 其余进待发队列; 每板的历史文本由
        `render_bond_scene_text(scene.to_dict())` 在交付时现算（唯一渲染源）。
        硬违规（形状类）→ 板列表为空, 由调用方 feedback 打回重发。
        """
        char = self._current_char
        main_id = char.character_id if char else ""
        aliases = self._main_aliases()
        block = VnBlock.from_text(raw, main_id=main_id, aliases=aliases)
        block_art = next((r.text for r in block.records if r.stage == STAGE_ART), "")
        hard, soft = split_issues(block.issues)
        drops = [n for n in block.notes if n.startswith("[DROP")]
        notes = [n for n in block.notes if not n.startswith("[DROP")]
        self._trace.append({
            "attempt": attempt,
            "action": "record_stream",
            "delivery_mode": DeliveryMode.BLOCK.value,
            "records": len(block.records),
            "parse_valid": bool(block.records) and not hard,
            "parse_errors": [str(i) for i in hard],
            "issue_codes": [i.code.value for i in block.issues],
            "issues": [str(i) for i in block.issues],
            "soft": [str(i) for i in soft],
            "notes": notes,
            "drops": drops,
        })
        logger.info("[vn][records] attempt=%d n=%d drop=%d note=%d issues=%d%s",
                    attempt, len(block.records), len(drops), len(notes), len(block.issues),
                    f" soft={len(soft)}" if soft else "")
        for d in drops:                          # 逐条坏行（原文前 100 字在 diag 里）
            logger.warning("[vn][records] 丢行 %s", d)
        if not block.records:
            return [], [Issue(IssueCode.BLOCK_EMPTY, "空块：没有任何合法记录")]
        if hard:
            return [], hard
        if soft:                                 # 超长群 → 切群; 其余（配对/章末）只记录
            logger.info("[vn][records] 软违规（不阻断）: %s", format_issues(soft))
        # 节点 3: 软问题只记录不打回 → 带到**下一轮**纠偏（硬问题已即时打回, 不重复纠偏）
        self._pending_feedback = list(soft)
        if block_art and not any(r.stage == STAGE_MEMORIAL for r in block.records):
            logger.warning("[vn][records] 声明了 art 但本回合没有 memorial（降级: 不发图）")

        # `art` 是**块级声明**（本轮画面意向）——不参与板切分（否则会切出一个纯声明
        # 的空板）。装配统一走 `_BoardAssembler`（节点 2′: 与流式**同一套语义**,
        # 差异清单见 tests/core/test_pipeline_parity.py）
        flow = tuple(r for r in block.records if r.stage != STAGE_ART)
        asm = _BoardAssembler(self, block_art=block_art, notes=block.notes)
        for start, end, _grp in _board_spans(flow):
            asm.push(flow[start:end])
        asm.finish()                                  # 块尾: 挂起的不可见板成板
        return asm.boards, []

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
            logger.info("[place][SWITCH] %r → %s", scene.place_hint, key or "keep（不换场）")
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

    def adopt_replayed(self, scene: "BondScene | None") -> None:
        """接入一块**来自事件流**的板（回放/续看）: 把回录基准指向它（2026-09-21）。

        为什么需要它: `record_picked`（A1 物化 `老师：X`）靠 `self._last_payload`
        重渲历史尾部; 而回放的板**不是本引擎生成的** ⇒ 不设基准时, 玩家在回放末板
        补的那次裁决**进不了引擎历史** —— 下一轮生成看不到裁决行（A1 那个洞的翻版,
        真机/探针都在: 重进回放末板补裁决后, 模型的历史里没有"老师：X"）。
        """
        self._last_payload = scene.to_dict() if scene is not None else None

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
