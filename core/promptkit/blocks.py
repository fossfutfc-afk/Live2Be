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
from typing import Any, Callable

from core.common.tone import load_story_tone
from core.mmt.mmt_executor import MmtExecError, load_interperson, self_entry_to_prompt
from core.parsing.world_parser import DEFAULT_WORLD_PATH, load_world, world_to_prompt
from llm.prompts import load_prompt

logger = logging.getLogger(__name__)


@dataclass
class BlockContext:
    """盒装配原料（引擎准备; 字段缺失的块自行降级跳过）。"""

    char: Any = None                     # DynamicCharacter（引擎必传; None 仅供纯文本块测试）
    names: list[str] = field(default_factory=list)   # 称呼名单（单人=[display_name]）
    greeting_suffix: str = ""              # 称呼行尾句（域专属: MMT/Bond 的规则指向）
    schema: str = ""                       # 域契约 schema 原文（contract.build_schema 输出）
    interperson_path: Any = None           # MMT 人际层文件（executor 持有）
    world_path: str | None = None          # None → 默认 overview.yml


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
    """可用动作 schema: 引擎用自己 registry 渲染的契约原文（域专属壳）。"""
    return "可用动作 schema:\n" + (ctx.schema or "")


#: 块注册表（id → build）; 说明文案供 report.describe 用
BLOCKS: dict[str, Callable[[BlockContext], str | None]] = {
    "greeting": _greeting,
    "persona_mmt": _persona_mmt,
    "world": _world,
    "story_tone": _story_tone,
    "mmt_tone": _mmt_tone,
    "interperson": _interperson,
    "environment_mmt": _environment_mmt,
    "rules_mmt": _rules_mmt,
    "schema": _schema,
}

BLOCK_DOC: dict[str, str] = {
    "greeting": "称呼行（身份先行, 名单可多人）",
    "persona_mmt": "角色设定全量六文件 + 行为规则",
    "world": "世界常识/世界规则（common+system 档）",
    "story_tone": "本角色剧情基调（SIG~main_tone）",
    "mmt_tone": "本角色 MMT 风格（SIG~mmt_tone, 条件）",
    "interperson": "人际层自表（interperson.json, 条件）",
    "environment_mmt": "MomoTalk 环境说明",
    "rules_mmt": "MomoTalk 行为规则书",
    "schema": "可用动作 schema（域契约）",
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
