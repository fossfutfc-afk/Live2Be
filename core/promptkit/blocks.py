# -*- coding: utf-8 -*-
"""命名内容块 — 提示词的稳定注入段（DESIGN_PROMPTKIT §3 blocks.py）。

每块 = (id, 说明, build(ctx) -> str | None); build 返回 None/空白 = 该块缺席
（条件注入, 不占位）。盒 = box.py 的 id 有序清单, 块间以 "\n\n" 连接。
文案必须与注入地图（docs/PROMPT_INJECTION_MAP.md）逐字一致——这里就是单一
装配源; 改文案 = 显式更新黄金夹具（tests/core/test_promptkit_baseline.py）并留 diff。

ctx 原料由引擎准备（角色/称呼/registry schema/人际层路径等——引擎仍拥有
registry 与 executor, 块只做"渲染段落"）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.common.tone import load_story_tone
from core.media.emotion_lexicon import build_emotion_injection
from core.mmt.mmt_executor import MmtExecError, load_interperson, self_entry_to_prompt
from core.parsing.place_regions import load_regions
from core.parsing.world_parser import DEFAULT_WORLD_PATH, load_world, world_to_prompt
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)

#: assets 默认根（core/promptkit/blocks.py → 项目根/assets; 与 bond 引擎旧推导一致）
_DEFAULT_ASSETS = Path(__file__).resolve().parents[2] / "assets"


@dataclass
class BlockContext:
    """盒装配原料（引擎准备; 字段缺失的块自行降级跳过）。"""

    char: Any = None                     # DynamicCharacter（引擎必传; None 仅供纯文本块测试）
    names: list[str] = field(default_factory=list)   # 称呼名单（单人=[display_name]）
    greeting_suffix: str = ""              # 称呼行尾句（域专属: MMT/Bond 的规则指向）
    schema: str = ""                       # 域契约 schema 原文（contract 渲染）
    schema_title: str = "可用动作 schema"    # schema 块标题（bond 记录流域改称输出契约）
    interperson_path: Any = None           # MMT 人际层文件（executor 持有）
    world_path: str | None = None          # None → 默认 overview.yml
    brain_segment: str = ""                # Bond: 记忆段（开场注入, 剧情内固定）
    assets_root: Path | str | None = None  # Bond 词表资产根（None → 项目根/assets）
    regions_path: Path | str | None = None  # 剧情地理词表（None → 默认 regions.yml）


# ---------------------------------------------------------------------------
# 块实现（MMT 域 Phase 1; Bond 域 Phase 3 追加）
# ---------------------------------------------------------------------------

def _greeting(ctx: BlockContext) -> str:
    """称呼行（盒A/B v2 归位盒顶——身份先行, 2026-09-07）: 名单分隔 "/",
    一人分饰多角预留（character_names 列表）。"""
    if not ctx.names:
        return None
    return "你好，" + " / ".join(ctx.names) + ctx.greeting_suffix


def _persona_mmt(ctx: BlockContext) -> str:
    """L0 自我层: 六文件全量人设 + 行为规则（build_prompt("momotalk")）。"""
    return ctx.char.build_prompt("momotalk")


def _world(ctx: BlockContext) -> str | None:
    """【世界常识】【世界规则】: overview.yml common+system 档（hidden 不注入）。"""
    chunk = world_to_prompt(load_world(ctx.world_path or DEFAULT_WORLD_PATH))
    return chunk or None


def _story_tone(ctx: BlockContext) -> str:
    """【本角色剧情基调】: script.yml SIG~main_tone（旧 personality SIG~story_tone 兜底）。
    注意: 盒A 的角色设定 dump 含 script.yml 全量, tone 内容会二次出现（既有行为, 见地图 §1）。"""
    return "【本角色剧情基调】\n" + load_story_tone(ctx.char)


def _mmt_tone(ctx: BlockContext) -> str | None:
    """【本角色 MMT 风格】: script.yml SIG~mmt_tone（缺失 → 不注入）。"""
    tone = (ctx.char.mmt_tone or "").strip()
    return ("【本角色 MMT 风格】\n" + tone) if tone else None


def _interperson(ctx: BlockContext) -> str | None:
    """L1 人际层: interperson.json 自表条目（键值+权重）。文件损坏 → 跳过不挡会话。"""
    if ctx.interperson_path is None:
        return None
    try:
        interperson = load_interperson(ctx.interperson_path)
    except MmtExecError as e:
        logger.warning("interperson 读取失败, 跳过 L1 注入: %s", e)
        interperson = {}
    entry = self_entry_to_prompt(interperson, ctx.char.character_id)
    return entry or None


def _environment_mmt(ctx: BlockContext) -> str:
    """momotalk_environment.md: 虚拟手机场景（玩家名不注入——学生不直呼自定义名）。"""
    return load_prompt("momotalk_environment")


def _rules_mmt(ctx: BlockContext) -> str:
    """momotalk_rules.md: 消息流协议 + 单人模式 + 契机导向触发规则。"""
    return load_prompt("momotalk_rules")


def _schema(ctx: BlockContext) -> str:
    """输出契约：引擎用自己 registry / 记录文法渲染的契约原文（域专属壳）。

    标题可换（`schema_title`）：VN 记录流域没有"动作"概念 → 称「本轮输出契约」，
    免得模型去找一个不存在的 action 外壳（§8.4 外壳字段退役）。
    """
    return f"{ctx.schema_title}:\n" + (ctx.schema or "")


# ---- Bond 域（Phase 3; 盒B v2 见 box.DOMAIN_BOXES["bond"]）------------------

def _persona_bond(ctx: BlockContext) -> str:
    """角色设定（Bond 两层面: profile+personality）+ 行为规则（build_prompt("bond_story"））"""
    return ctx.char.build_prompt("bond_story")


def _bond_tone(ctx: BlockContext) -> str | None:
    """【本角色羁绊剧情建议】: script.yml SIG~bond_tone（缺失 → 不注入）。"""
    tone = (ctx.char.bond_tone or "").strip()
    return ("【本角色羁绊剧情建议】\n" + tone) if tone else None


def _rules_bond(ctx: BlockContext) -> str:
    """bond_story_rules.md: 单人视角/对白节奏/记录流写法（switch·群·memorial·end）。

    记录流 v2: 范本里的 `{char_id}` / `{char_name}` 占位按**本会话角色**替换——
    范例一律用真实 id（不许再出现 `haruka` 这类短名, 决策 #24）。
    """
    text = load_prompt("bond_story_rules")
    char = ctx.char
    if char is not None:
        text = (text.replace("{char_id}", char.character_id)
                    .replace("{char_name}", char.display_name))
    return text


def _lexicon_emotion(ctx: BlockContext) -> str | None:
    """【表情标注词表】: assets/illustration/{char}/default/emotions.yml 键+示范 few-shot。

    **已退出盒B**（记录流 v2, 决策 #24）: writer 不写 emotion（标注层逐记录挑），
    词表与创作无关; 保留块实现供标注层/测试复用（盒清单见 box.DOMAIN_BOXES）。
    """
    assets_root = Path(ctx.assets_root) if ctx.assets_root else _DEFAULT_ASSETS
    char_dir = assets_root / "illustration" / ctx.char.character_id / "default"
    inj = build_emotion_injection(char_dir)
    return inj or None


def _place_world(ctx: BlockContext) -> str | None:
    """【世界区域】剧情地理（`regions.yml` 的官方中文主名）。

    **2026-09-15（T16）取代 `place_palette`**（31 条资产 slug 的"舞台菜单"）。
    用户裁决: *"普通地点我希望以文本的形式说明, 比如各个学院, 不具体到那些咖啡馆
    这种地点词, 因为给主 LLM 这些反而会把它框死, 这是异步 lane 的工作。"*

    ## 为什么这一档要给（而 `place_palette` 不该给）

    | | `place_palette`（旧） | 【世界区域】（本块） |
    |---|---|---|
    | 内容 | 资产键（`school_rooftop`…） | 剧情地理主名（`阿拜多斯高级中学`…） |
    | 性质 | **可选空间**——"你能把故事写到哪" | **世界设定**——"这个世界有哪些地方" |
    | 副作用 | 诱导"为了用上拉面店而写一场拉面店" | 无（与 persona/world 同性质） |

    判据 = **"多给 writer 一个手段"还是"少给 writer 一个自由"**。
    而且 `overview.yml` 里**一个学院名都没有**——writer 本来不知道这个世界有哪些
    学院，会凭空发明。所以这不是"给菜单"，是**补世界设定**。

    ## 为什么删 `place_palette` 不损失"防单调"

    它当年存在的理由是"writer 不敢换场"。而那个职责**已经由规则书承担**:
    `bond_story_rules.md` §五【换场】写了何时发、怎么发、同地点小动作不换场,
    连示例都给了三条（含 `{"stage": "switch", "text": "星空"}`）。
    **规则书给的是"能力", 菜单给的是"选项"**——前者才是正解。
    """
    table = load_regions(ctx.regions_path)
    names = table.names()
    if not names:
        return None
    return "\n".join([
        "【世界区域】（剧情发生的地域）",
        "提到学院/地区时以这些为准（别发明新的）:",
        "、".join(names),
    ])


def _brain(ctx: BlockContext) -> str | None:
    """brain 段（Bond 开场注入, 剧情内固定）: 出厂背景 + wiki 第一人称视图。"""
    seg = (ctx.brain_segment or "").strip()
    return seg or None


#: 块注册表（id → build）; 说明文案供 report.describe 用
BLOCKS: dict[str, Callable[[BlockContext], str | None]] = {
    "greeting": _greeting,
    "persona_mmt": _persona_mmt,
    "persona_bond": _persona_bond,
    "world": _world,
    "story_tone": _story_tone,
    "mmt_tone": _mmt_tone,
    "interperson": _interperson,
    "environment_mmt": _environment_mmt,
    "rules_mmt": _rules_mmt,
    "bond_tone": _bond_tone,
    "rules_bond": _rules_bond,
    "lexicon_emotion": _lexicon_emotion,
    "place_world": _place_world,
    "schema": _schema,
    "brain": _brain,
}

BLOCK_DOC: dict[str, str] = {
    "greeting": "称呼行（身份先行, 名单可多人）",
    "persona_mmt": "角色设定全量六文件 + 行为规则",
    "persona_bond": "角色设定两层（profile+personality）+ 行为规则",
    "world": "世界常识/世界规则（common+system 档）",
    "story_tone": "本角色剧情基调（SIG~main_tone）",
    "mmt_tone": "本角色 MMT 风格（SIG~mmt_tone, 条件）",
    "interperson": "人际层自表（interperson.json, 条件）",
    "environment_mmt": "MomoTalk 环境说明",
    "rules_mmt": "MomoTalk 行为规则书",
    "bond_tone": "本角色羁绊剧情建议（SIG~bond_tone, 条件）",
    "rules_bond": "羁绊剧情规则书（记录流写法: switch/群/memorial/end）",
    "lexicon_emotion": "表情标注词表（emotions.yml, 条件）",
    "place_world": "世界区域·剧情地理（regions.yml 主名; 世界设定, 非可选空间）",
    "schema": "输出契约 schema（域契约; 标题随域可换）",
    "brain": "记忆段（brain_segment, 条件）",
}


def render_block(bid: str, ctx: BlockContext) -> str | None:
    """渲染单个块（未知 id → None; build 异常上抛——装配期宁错勿吞）。"""
    build = BLOCKS.get(bid)
    if build is None:
        return None
    text = build(ctx)
    if text is None or not str(text).strip():
        return None
    return str(text)
