# -*- coding: utf-8 -*-
"""Promptkit Phase 0 — 现网装配基线黄金夹具（DESIGN_PROMPTKIT.md §7 Phase 0）。

锁定三件事（重构 Phase 1+ 不得破坏; 唯一例外 = 设计内规定的称呼行归位,
届时显式更新夹具并留 git diff）:
    1. 盒（system prompt）全文逐字节
    2. 典型轮/场的完整 messages 逐字节（MMT 一轮 / Bond 一场, 手动装配分支）
    3. 段顺序断言（结构, 不锁全文）

夹具更新: 设 PROMPTKIT_UPDATE_FIXTURES=1 运行本文件 → 重写
tests/fixtures/promptkit/*.txt（生成后人工审 diff 再提交）。
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine
from core.momotalk import MomoTalkEngine

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
DISPLAY = "伊草 遥香"
FIXT = ROOT / "tests" / "fixtures" / "promptkit"

UPDATE = os.environ.get("PROMPTKIT_UPDATE_FIXTURES") == "1"


class ScriptedLLM:
    """脚本桩: 记录每次调用的 messages; chat/chat_full 都支持（bond 走流式优先）。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots = []

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        return self._scripts.pop(0)

    def chat_full(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        resp = self._scripts.pop(0)
        on_chunk = kw.get("on_chunk")
        if on_chunk is not None:
            on_chunk(json.dumps(resp, ensure_ascii=False))
        return resp

    def format_messages(self, **kw):
        # 无 system_note 分支委托给客户端——本基线只锁手动装配分支
        return []


def _mmt_engine(llm):
    from core.bond.bond_progress import BondProgress
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm,
                            bond_progress=BondProgress(data_root=ROOT / "data"))
    engine.start_session(CHARACTER)
    return engine


def _bond_engine(llm):
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    return engine


# ---------------------------------------------------------------------------
# 夹具读写
# ---------------------------------------------------------------------------

def _write_fixture(name: str, text: str) -> None:
    if UPDATE:
        FIXT.mkdir(parents=True, exist_ok=True)
        (FIXT / name).write_text(text, encoding="utf-8")


def _assert_fixture(name: str, text: str) -> None:
    p = FIXT / name
    if UPDATE:                              # 更新模式: 直接写（生成后人工审 git diff）
        FIXT.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return
    if not p.exists():
        raise AssertionError(
            f"夹具缺失: {p}\n首次运行请设 PROMPTKIT_UPDATE_FIXTURES=1 生成（生成后审 diff）")
    expected = p.read_text(encoding="utf-8")
    assert text == expected, (
        f"夹具漂移: {name}\n"
        f"—— 非设计的重构改动会漂; 有意变更请重生成并留 git diff 记录。\n"
        f"期望(len={len(expected)}) 前 80 字: {expected[:80]!r}\n"
        f"实际(len={len(text)}) 前 80 字: {text[:80]!r}")


def _write_json_fixture(name: str, messages: list) -> None:
    _assert_fixture(name, json.dumps(messages, ensure_ascii=False, indent=1))


def _order(box: str, markers: list[str]) -> list[int]:
    return [box.find(m) for m in markers]


def _assert_ordered(box: str, markers: list[str]) -> None:
    pos = _order(box, markers)
    missing = [m for m, i in zip(markers, pos) if i < 0]
    assert not missing, f"盒内缺少段标记: {missing}"
    assert pos == sorted(pos), (
        f"段顺序漂移: {list(zip(markers, pos))}（非设计变更即回归）")


# ---------------------------------------------------------------------------
# 盒（system prompt）基线
# ---------------------------------------------------------------------------

_MMT_MARKERS = [
    f"你好，{DISPLAY}",                 # 称呼行: v2 归位盒顶（Phase 1 完成——身份先行）
    "# 角色设定",
    "【世界常识】",
    "【世界规则】",
    "【本角色剧情基调】",
    "【本角色 MMT 风格】",
    "【MomoTalk 环境说明】",
    "【MomoTalk 行为规则】",
    "可用动作 schema",
]

_BOND_MARKERS = [
    "# 角色设定",
    "【世界常识】",
    "【世界规则】",
    "【本角色剧情基调】",
    "【本角色羁绊剧情建议】",
    f"你好，{DISPLAY}",                 # 称呼行: 现网位置（tone 与 rules 之间）——Phase 3 归位盒顶时此处改
    "【羁绊剧情 回复规则】",
    "可用动作 schema",
]


def test_mmt_box_baseline():
    """盒A 全文夹具 + 段顺序（含称呼行现网位置）。"""
    engine = _mmt_engine(ScriptedLLM())
    box = engine._system_prompt
    _assert_fixture("mmt_box.txt", box)
    _assert_ordered(box, _MMT_MARKERS)


def test_bond_box_baseline():
    """盒B 全文夹具 + 段顺序（含称呼行现网位置）。"""
    engine = _bond_engine(ScriptedLLM())
    box = engine._system_prompt
    _assert_fixture("bond_box.txt", box)
    markers = list(_BOND_MARKERS)
    if "【表情标注词表】" in box:        # 词表/地点资产 gitignore——存在才断言
        markers.insert(markers.index("可用动作 schema") + 1, "【表情标注词表】")
    _assert_ordered(box, markers)


# ---------------------------------------------------------------------------
# 每轮/每场 messages 基线（手动装配分支: 有 system_note / P16 注记）
# ---------------------------------------------------------------------------

def test_mmt_round_tail_baseline():
    """MMT 一轮完整 messages: [system(盒A)] + [P16 羁绊注记 system] + [user]。"""
    llm = ScriptedLLM({"messages": [{"text": "嗯……我、我有点紧张。"}]},
                      {"messages": [{"text": "老师你听我慢慢说。"}]})
    engine = _mmt_engine(llm)
    box = engine._system_prompt

    r = engine.agent_turn("你好呀，在吗")
    assert r.ok
    m1 = llm.snapshots[0]
    assert [m["role"] for m in m1] == ["system", "system", "user"], m1
    assert m1[0]["content"] == box                    # 前缀 = 盒A 逐字节
    assert m1[1]["content"].startswith("羁绊进度事实")   # P16 注记（新会话 gap=0）
    assert m1[2] == {"role": "user", "content": "你好呀，在吗"}

    r2 = engine.agent_turn("继续")
    assert r2.ok
    m2 = llm.snapshots[1]
    assert m2[0]["content"] == box                    # 前缀跨轮逐字节稳定（缓存基本盘）
    assert m2[-1] == {"role": "user", "content": "继续"}
    _write_json_fixture("mmt_round.txt", m2)


def test_bond_scene_tail_baseline():
    """Bond 一场完整 messages（有 system_note）: [system(盒B)] + [注记] + [user]。"""
    scene = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "（测试）她站在窗边，听到声音回过头来。"},
                       {"text": "那个……有些话，我一直想找机会跟你说。"}],
        "choices": ["走过去，在她身边坐下", "笑着说：说吧，我在听"],
        "branches": {
            "走过去，在她身边坐下": [{"text": "（测试）她张了张嘴，小声说：那我说了哦。"}],
            "笑着说：说吧，我在听": [{"text": "（测试）她松了口气，声音轻快了些。"}],
        },
    }}
    llm = ScriptedLLM(scene)
    engine = _bond_engine(llm)
    box = engine._system_prompt

    seed = "（旁白）本章：测试章——从刚才的对话与契机自然展开。"
    s = engine.send_vn_scene(seed, system_note="（系统）测试注记", annotate=False)
    assert s is not None and not s.is_end
    m = llm.snapshots[0]
    assert [x["role"] for x in m] == ["system", "system", "user"], m
    assert m[0]["content"] == box                     # 前缀 = 盒B 逐字节
    assert m[1] == {"role": "system", "content": "（系统）测试注记"}
    assert m[2] == {"role": "user", "content": seed}
    _write_json_fixture("bond_scene.txt", m)
