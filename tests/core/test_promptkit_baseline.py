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
import tempfile
from datetime import datetime
from pathlib import Path


from core.bond.bond_story import BondStoryEngine
from core.mmt.engine import MomoTalkEngine

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
DISPLAY = "伊草 遥香"
FIXT = ROOT / "tests" / "fixtures" / "promptkit"
#: ⚠️ 进度落盘走**临时目录**——`BondProgress` 的 data_root 指到真机 `data/` 会把
#: `data/basic/bond_progress.json` 里真实角色的累计轮数刷上去（2026-09-26 实测）。
_PROGRESS_ROOT = Path(tempfile.mkdtemp(prefix="promptkit_progress_"))

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
            # ⚠️ 喂给 on_chunk 的必须是**返回的那段文本本身**（生产客户端就是内容增量）——
            #    脚本是 str 时再 `json.dumps` 一次 = 双重编码 ⇒ 行协议一行都解析不出来
            #    （⑥-3a 实测: 三个 MMT 基线用例因此跑到 MAX_STEPS 才报错）。
            on_chunk(resp if isinstance(resp, str)
                     else json.dumps(resp, ensure_ascii=False))
        return resp

    def format_messages(self, **kw):
        # 无 system_note 分支委托给客户端——本基线只锁手动装配分支
        return []


def _mmt_engine(llm, store=None):
    from core.bond.bond_progress import BondProgress
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm,
                            bond_progress=BondProgress(data_root=_PROGRESS_ROOT),
                            store=store)
    engine.start_session(CHARACTER)
    return engine


def _freeze_wall_clock(monkeypatch, when):
    """把 `prompt_time` 的壁钟冻住 —— 否则夹具会**每天失效**。

    时间注记里的"手机上的日期"取 `datetime.now()`（真实日期）;
    真机要真实日期, 但**夹具必须可重现**（今天跑出 9月15, 明天就是 9月16）,
    所以这里只替换**读时钟**的那一处。
    """
    import core.worldtime.prompt_time as _pt

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return when

    monkeypatch.setattr(_pt, "datetime", _FixedDateTime)
    return when


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
    f"你好，{DISPLAY}",                 # 称呼行: v2 归位盒顶（Phase 3 完成——身份先行）
    "# 角色设定",
    "【世界常识】",
    "【世界规则】",
    "【本角色剧情基调】",
    "【本角色羁绊剧情建议】",
    "【羁绊剧情 回复规则】",
    "【镜头与手法】",                    # PL2 2026-09-19: 手法手册（紧挨规则书）
    "本轮输出契约（VN 记录流）",           # 记录流 v2: 标题可换（无 action 外壳）
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
    _schema_at = markers.index("本轮输出契约（VN 记录流）")
    if "【表情标注词表】" in box:        # 词表/地点资产 gitignore——存在才断言
        markers.insert(_schema_at + 1, "【表情标注词表】")
    if "【可去的地方】" in box:          # 舞台清单（资产 whitelist 存在才有）
        at = (markers.index("【表情标注词表】") + 1
              if "【表情标注词表】" in markers
              else _schema_at + 1)
        markers.insert(at, "【可去的地方】")
    _assert_ordered(box, markers)


# ---------------------------------------------------------------------------
# 每轮/每场 messages 基线（手动装配分支: 有 system_note / P16 注记）
# ---------------------------------------------------------------------------

def test_mmt_round_tail_baseline(monkeypatch):
    """MMT 一轮完整 messages（task 卡 on）: [system(盒A)] + [注记们] + [卡] + [user]。

    ⚠️ **注记条数不写死**（2026-09-13 加时间注记后, 原按条数断言的写法会失效）。
    改为**按内容定位 + 只断言顺序关系**。
    ⚠️ 壁钟**冻住** —— 手机日期取 `datetime.now()`, 不冻则夹具每天失效。
    """
    _freeze_wall_clock(monkeypatch, datetime(2026, 9, 13, 20, 41))
    llm = ScriptedLLM('{"text": "嗯……我、我有点紧张。"}',
                      '{"text": "老师你听我慢慢说。"}')
    engine = _mmt_engine(llm)
    box = engine._system_prompt

    r = engine.agent_turn("你好呀，在吗")
    assert r.ok
    m1 = llm.snapshots[0]
    assert m1[0]["content"] == box                    # 前缀 = 盒A 逐字节
    assert all(x["role"] == "system" for x in m1[:-1]), m1
    assert m1[-1] == {"role": "user", "content": "你好呀，在吗"}
    icard = next(i for i, x in enumerate(m1)
                 if x["content"].startswith("本回合任务：以伊草 遥香身份"))
    # ⛔ P16「羁绊进度注记」已封印（2026-10-08）⇒ 排序断言换成"**不许**再出现"。
    #    （原断言的锚点就是那条注记的抬头"羁绊进度事实", 封印后该锚点不存在。）
    assert all("【剧情时机】" not in (x.get("content") or "") for x in m1), m1
    assert icard == len(m1) - 2, (icard, len(m1))      # 卡恒在 user 前最后一位

    r2 = engine.agent_turn("继续")
    assert r2.ok
    m2 = llm.snapshots[1]
    assert m2[0]["content"] == box                    # 前缀跨轮逐字节稳定（缓存基本盘）
    assert m2[-2]["content"].startswith("本回合任务")   # 卡恒在 user 前最后一位
    assert m2[-1] == {"role": "user", "content": "继续"}
    _write_json_fixture("mmt_round.txt", m2)


def test_mmt_round_tail_task_off():
    """task 卡 off（引擎参数）: 尾部无卡。"""
    llm = ScriptedLLM('{"text": "嗯……我、我有点紧张。"}')
    engine = _mmt_engine(llm)
    engine._task_on = False
    engine.agent_turn("你好呀，在吗")
    m = llm.snapshots[0]
    assert all("本回合任务" not in x["content"] for x in m)
    assert m[-1] == {"role": "user", "content": "你好呀，在吗"}


def test_mmt_wrapup_tail_card():
    """收尾轮（task_kind="wrapup"）: 注记之后是收尾卡, 卡内容 = task_mmt_wrapup.md。"""
    from core.promptkit import task_card as _card
    llm = ScriptedLLM('{"text": "嗯…今晚的事我会记住的。"}')
    engine = _mmt_engine(llm)
    note = "（系统）羁绊剧情刚刚结束，回到手机聊天。只使用 mmt_chat 动作。"
    r = engine.agent_turn("（自动收尾）", system_note=note, record_input=False,
                          task_kind="wrapup")
    assert r.ok
    m = llm.snapshots[0]
    card = _card("mmt", "wrapup", char="伊草 遥香", enabled=True)
    assert m[-1] == {"role": "user", "content": "（自动收尾）"}
    assert m[-2]["content"] == card                   # 卡恒在 user 前最后一位
    i16 = next((i for i, x in enumerate(m) if x["content"] == note), None)
    assert i16 is not None and i16 < len(m) - 2, (i16, len(m))
    # ⛔ P16 已封印（2026-10-08）: 原来的锚点"羁绊进度事实"不存在了; 改成反向断言
    assert all("【剧情时机】" not in (x.get("content") or "") for x in m), m
    assert engine.history[-1]["role"] == "assistant"  # record_input=False → 无假 user 历史


def test_bond_scene_tail_baseline():
    """Bond 一场完整 messages（task 卡 on）: [system(盒B)] + [注记] + [场卡] + [user]。

    记录流 v2（P0-7c）: 场景桩 = 记录流（一板一块）。
    """
    from tests.vn_fixtures import scene as _scene

    block = _scene(
        switch_to="测试教室",
        lines=["（测试）她站在窗边，听到声音回过头来。",
               "那个……有些话，我一直想找机会跟你说。"],
        sensei=["走过去，在她身边坐下", "笑着说：说吧，我在听"],
    )
    llm = ScriptedLLM(block)
    engine = _bond_engine(llm)
    box = engine._system_prompt

    seed = "（旁白）本章：测试章——从刚才的对话与契机自然展开。"
    s = engine.send_vn_scene(seed, system_note="（系统）测试注记", annotate=False)
    assert s is not None and not s.is_end
    assert s.choices == ["走过去，在她身边坐下", "笑着说：说吧，我在听"]
    m = llm.snapshots[0]
    assert [x["role"] for x in m] == ["system", "system", "system", "user"], m
    assert m[0]["content"] == box                     # 前缀 = 盒B 逐字节
    assert m[1] == {"role": "system", "content": "（系统）测试注记"}
    assert m[2]["content"].startswith("本场任务：作为伊草 遥香推进当前这一段剧情")  # scene 场卡
    assert m[3] == {"role": "user", "content": seed}
    _write_json_fixture("bond_scene.txt", m)


def test_bond_scene_tail_task_off():
    """Bond task 卡 off（构造参数）: 旧行为 [system]+[注记]+[user]。"""
    from tests.vn_fixtures import scene as _scene

    block = _scene(switch_to="测试教室", lines=["（测试）她推开门走了进来。"],
                   sensei=["A", "B"])
    llm = ScriptedLLM(block)
    engine = BondStoryEngine(ROOT / "config" / "characters", llm, task_card=False)
    engine.start_session(CHARACTER)
    s = engine.send_vn_scene("（旁白）测试。", system_note="（系统）测试注记", annotate=False)
    assert s is not None
    m = llm.snapshots[0]
    assert [x["role"] for x in m] == ["system", "system", "user"], m
    assert all("本场任务" not in x["content"] for x in m)
