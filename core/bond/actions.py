"""表现层动作词表 —— 标注层能给的一条**立绘"动静"**（闭合表, 引擎只校验不发明）。

**它不是剧情里的物理动作**。`jump` 不等于"她真的跳起来", 而是"情绪一下子冲上来时,
立绘快速上移再落回"; `shake` 也不是发抖的剧情事实, 而是"画面上抖一下"。换句话说:
动作是情绪的**外化投影**, 和 `emotion` 同源、不同表现 —— 所以它永远不改变剧情,
只改变这一句的体感。

标注输出的一行里, 动作是 `act` 字段（可选）; 不认识就只丢动作, 情绪照旧 ——
**不进重试**。一处同名、三处消费, 改词表 = 改这张表:
  · 提示词: `render_prompt_block()` 渲进 `emotion_text_annotate.md` 的 `{{acts}}`
  · 校验:   `ACTION_NAMES`（词表外一律丢弃, 绝不传给前端）
  · 渲染:   前端 `webgui/static/js/effects.js` 的 `ACT_SPECS`
            （`tests/webgui/test_frontend_contract.py` 钉双向, 少一个就红）

**词表同构, 渲染不同构**: 情绪键落到 spine 的差分动画上（`01..13` 是姿态+表情的静帧）,
动作键只能落到前端的 transform tween 上 —— BA 的立绘包里没有跳跃动画（1005 个 `.skel`
里只有 13 个带 `Jump`/`Hop`）, 原作里这类演出也是代码枚举（`ScenarioCharacterAction`）
驱动的。

所以 `p["emotion"]` 恒为真情绪键 —— 它有两处按词表消费的地方: LLM 可见的历史文本
（`render_bond_scene_text` 给每句拼 `（emotion）`）与记忆里的情绪轨迹
（`digest.episodes._emotion_shape`）。混进动作名会把那两处一起带歪。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 一板最多几个动静。模型很容易"每句都演", 而一板三跳等于没有动静。
MAX_ACTS_PER_BOARD = 2


@dataclass(frozen=True)
class Action:
    name: str      # 标注输出用的键（也是前端 `ACT_SPECS` 的键）
    label: str     # 中文名（提示词与日志）
    when: str      # 一句话: 什么时候该点它（说的是情绪, 不是剧情事件）


ACTIONS: tuple[Action, ...] = (
    Action("jump", "弹一下", "情绪一下子冲上来——开心、惊喜、急得想蹦（快速上移再落回）"),
    Action("hop", "轻快两下", "窃喜、期待、按不住的雀跃（小幅上移两次）"),
    Action("shake", "抖一下", "害怕、强忍、摇头否认（左右小幅抖动）"),
    Action("stiff", "绷住", "被抓包、忽然严肃、大气不敢出（瞬间绷紧再放开）"),
    Action("fall", "沉下去", "腿软、被打击、泄了气（向下沉 + 轻微倾斜）"),
    Action("greet", "点头", "打招呼、应承、道谢（上下轻点两下）"),
)

ACTION_NAMES: frozenset[str] = frozenset(a.name for a in ACTIONS)


def render_prompt_block() -> str:
    """词表 → 提示词里那一段（键 + 中文名 + 何时点）。"""
    return "\n".join(f"  {a.name:<6} {a.label}: {a.when}" for a in ACTIONS)
