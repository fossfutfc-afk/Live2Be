# -*- coding: utf-8 -*-
"""promptkit 组装层单元测试（DESIGN_PROMPTKIT §3, Phase 1）。

覆盖: round_messages 槽位协议 / build_box 装配 / describe 报表结构。
盒内容字节回归 = tests/core/test_promptkit_baseline.py（黄金夹具）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from contract import build_schema
from core.mmt.mmt_actions import build_mmt_registry
from core.parsing.dynamic_character_parser import CharacterLoader
from core.promptkit import (
    DOMAIN_BOXES,
    BlockContext,
    box_chunks,
    build_box,
    describe,
    round_messages,
    task_card,
)
from core.promptkit.blocks import render_block

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


# ---------------------------------------------------------------------------
# round_messages（每轮动态尾）
# ---------------------------------------------------------------------------

def test_round_messages_slot_layout():
    """槽位协议: [system(盒+brain)] + history + [注记们] + [user]。"""
    history = [{"role": "user", "content": "上轮"}, {"role": "assistant", "content": "（上轮回复）"}]
    m = round_messages(
        system="SYS", history=history,
        notes=["注记1", None, "", "注记2"], brain="B1\nB2", user="U")
    assert [x["role"] for x in m] == ["system", "user", "assistant",
                                      "system", "system", "user"]
    assert m[0]["content"] == "SYS\n\nB1\nB2"          # brain 追加 system 尾（不 strip 注记原文）
    assert m[1] is history[0] and m[2] is history[1]   # 历史原样引用, 不改写
    assert [x["content"] for x in m if x["role"] == "system"][1:] == ["注记1", "注记2"]
    assert m[-1] == {"role": "user", "content": "U"}


def test_round_messages_prefix_stable_and_no_brain():
    """无 brain / 空白 brain → system 逐字节 = 盒; 注记缺席不占位。"""
    for brain in ("", "   "):
        m = round_messages(system="SYS", notes=[None, ""], brain=brain, user="U")
        assert m[0]["content"] == "SYS"
        assert len(m) == 2


# ---------------------------------------------------------------------------
# build_box / 块
# ---------------------------------------------------------------------------

def _ctx():
    loader = CharacterLoader(ROOT / "config" / "characters")
    char = loader.load(CHARACTER)
    return BlockContext(
        char=char,
        names=[char.display_name],
        greeting_suffix="——以下是你的行为规则，请严格遵守：",
        schema=build_schema(build_mmt_registry(), action_list=True),
        interperson_path=ROOT / "config" / "settings" / "relation" / "interperson.json",
    )


def test_build_box_v2_order():
    """盒A v2: 称呼行首段, 其后 角色设定 → 世界 → 基调 → …; 两次装配幂等。"""
    ctx = _ctx()
    box = build_box("mmt", ctx)
    assert box.startswith("你好，伊草 遥香——")
    assert box.index("你好，伊草 遥香") < box.index("# 角色设定")
    assert box.index("【MomoTalk 行为规则】") < box.index("可用动作 schema:")
    assert build_box("mmt", ctx) == box                # 幂等（逐字节稳定前提）


def test_render_block_blank_skip():
    """缺席/空白块 → None; 注册表外 id → None; schema 空原文仍带前缀壳（与现网一致）。"""
    assert render_block("no_such_block", _ctx()) is None
    assert render_block("greeting", BlockContext(names=[])) is None     # 无名单 → 缺席
    assert render_block("schema", BlockContext(schema="")) == "可用动作 schema:\n"


def test_box_chunks_unknown_domain():
    try:
        box_chunks("nope", _ctx())
        assert False, "未知域应抛 ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# task 卡（Phase 2）
# ---------------------------------------------------------------------------

def test_task_card_chat_default_and_char_replace():
    """默认 kind=chat: task_mmt.md 模板; {char} 占位替换。"""
    from core.promptkit.task import _template_name
    assert _template_name("mmt", "chat") == "task_mmt"
    assert _template_name("mmt", "wrapup") == "task_mmt_wrapup"
    card = task_card("mmt", enabled=True, char="伊草 遥香")
    assert card is not None
    assert "{char}" not in card and "伊草 遥香" in card
    assert "mmt_trigger_bond_story" in card


def test_task_card_wrapup_kind():
    """收尾轮 kind=wrapup: 只发消息行（不触发剧情）的任务约束。"""
    card = task_card("mmt", "wrapup", char="遥香", enabled=True)
    assert card is not None
    assert "只发**消息行**" in card and "不要再次触发剧情" in card


def test_task_card_bond_kinds():
    """Bond 场卡: 只有 scene 一种（task_bond.md, 记录流 v2）。

    2026-09-13（审计 B1）: `memorial_exit` kind **已退役**——v2 里纪念区间到块尾,
    边界由块边界结构性给出, 不存在"退出动作"; 原 kind 会把 v1 已退役动作名喂给
    只吃记录流的引擎。这里钉住"卡模板不存在 → 不注入"。
    """
    scene = task_card("bond", enabled=True, char="伊草 遥香")
    assert scene is not None
    assert scene.startswith("本场任务：作为伊草 遥香推进当前这一段剧情")
    assert '"stage": "switch"' in scene and "sensei" in scene and '"stage": "end"' in scene
    assert "story_scene" not in scene and "branches" not in scene     # 旧契约字样退役
    # 退役 kind: 模板已删 → None（而不是注入一条指向不存在动作的指令）
    assert task_card("bond", "memorial_exit", char="伊草 遥香", enabled=True) is None


def test_task_card_disabled_or_missing():
    """禁用 / kind 无模板 → None（不注入, 宁缺勿错）。"""
    assert task_card("mmt", enabled=False) is None                 # 开关关
    assert task_card("bond", enabled=False) is None                # 开关关
    assert task_card("mmt", "scene", enabled=True) is None         # 未知 kind 模板缺失
    assert task_card("unknown_domain", enabled=True) is None


# ---------------------------------------------------------------------------
# describe（报表）
# ---------------------------------------------------------------------------

def test_describe_mmt_manifest():
    """describe 报表: 行序 = 盒声明序; 首行 = greeting; 缺席块有标注。"""
    ctx = _ctx()
    rep = describe("mmt", ctx)
    lines = rep.splitlines()
    assert lines[0].startswith("# promptkit describe: mmt")
    assert "| 1 | greeting |" in rep
    assert "| 2 | persona_mmt |" in rep
    assert len(DOMAIN_BOXES["mmt"]) == 10               # 声明 10 块
    assert "缺席块" not in rep                          # 遥香全量资料 → 10 块全注入
