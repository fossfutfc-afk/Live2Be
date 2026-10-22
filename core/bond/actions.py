"""剧情动作词表 —— 标注层能点名的**身体表演**（闭合表, 引擎只校验不发明）。

标注那一格写成 `"情绪键|动作键"`（`core/bond/emo_text.py::_split_value` 拆）:
同一行可以既切表情又演动作（前端顺序: `setEmotion` → `playAct`）; 动作段不认识就
只丢动作, 情绪照旧 —— **不进重试**。

一处同名、三处消费, 改词表 = 改这张表:
  · 提示词: `render_prompt_block()` 渲进 `emotion_text_annotate.md` 的 `{{acts}}`
  · 校验:   `ACTION_NAMES`（词表外一律丢弃, 绝不传给前端）
  · 渲染:   前端 `webgui/static/js/effects.js` 的 `ACT_SPECS`
            （`tests/webgui/test_frontend_contract.py` 钉双向, 少一个就红）

**词表同构, 渲染不同构**: 情绪键落到 spine 的差分动画上（`01..13` 是姿态+表情的静帧）,
动作键只能落到前端的位移 tween 上 —— BA 的立绘包里没有跳跃动画（1005 个 `.skel` 里只有
13 个带 `Jump`/`Hop`, 遥香的包只有 `Idle_01` + 数字）, 剧情动作在原作里也是代码枚举
（`ScenarioCharacterAction`）驱动的。

所以 `p["emotion"]` 恒为真情绪键 —— 它有两处按词表消费的地方: LLM 可见的历史文本
（`render_bond_scene_text` 给每句拼 `（emotion）`）与记忆里的情绪轨迹
（`digest.episodes._emotion_shape`）。混进动作名会把那两处一起带歪。
"""
from __future__ import annotations

from dataclasses import dataclass

#: 一板最多几个动作。模型很容易"每行都演", 而一板三跳等于没有动作。
MAX_ACTS_PER_BOARD = 2


@dataclass(frozen=True)
class Action:
    name: str      # 标注输出用的键（也是前端 `ACT_SPECS` 的键）
    label: str     # 中文名（提示词与日志）
    when: str      # 一句话: 什么时候该点它


ACTIONS: tuple[Action, ...] = (
    Action("jump", "跳", "整个人弹起来——被吓到、急得表态、扑过来"),
    Action("hop", "小跳", "轻快一下——高兴、期待、憋不住的雀跃"),
    Action("shake", "抖", "压不住的颤——恐惧、强忍、摇头否认"),
    Action("stiff", "僵住", "整个人绷直——被抓包、忽然严肃、大气不敢出"),
    Action("fall", "坐倒", "失去平衡——腿软、脱力、被打击到站不住"),
    Action("greet", "点头", "打招呼/应声——见面、答应、道谢"),
)

ACTION_NAMES: frozenset[str] = frozenset(a.name for a in ACTIONS)


def render_prompt_block() -> str:
    """词表 → 提示词里那一段（键 + 中文名 + 何时点）。"""
    return "\n".join(f"  {a.name:<6} {a.label}: {a.when}" for a in ACTIONS)
