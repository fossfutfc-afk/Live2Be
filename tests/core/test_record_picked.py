"""方案A-A1 选项回录（记录流 v2 版）单测。

核心: 裁决 = **物化**——被选中的候选成为群里一条 `sensei` 记录（`老师：X`）,
其余候选在渲染层消失; 因为 live 与回放都走 `render_bond_scene_text`（同一 payload
+ picked）, **逐字节同形是构造性成立的**（决策 #25）。

v1 时代那段（dict 场景 + 「（选择了: X）」旧注解）见
`tests/archive/test_record_picked_v1.py`——旧契约语义冻结在
`tests/core/test_vn_replay_compat.py` 里另有覆盖。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


class ScriptedLLM:
    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.snapshots = []

    def chat_full(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        return self._scripts.pop(0)

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        return self._scripts.pop(0)


def _engine(llm) -> BondStoryEngine:
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    return engine


# 记录流 v2（P0-5）: 裁决 = **物化**（不是注解）——`老师：X` 取代"（选择了: X）"
# ---------------------------------------------------------------------------

RECORD_BLOCK = "\n".join([
    '{"stage": "switch", "text": "深夜的杂草屋"}',
    '{"character": "igusa_haruka", "text": "……老师，你来了。"}',
    '{"character": "sensei", "text": "我来了。"}',
    '{"character": "sensei", "text": "路上买了点东西。"}',
    '{"character": "igusa_haruka", "text": "「不、不用这样的……」"}',
])
RECORD_PICKED = "路上买了点东西。"
RECORD_OTHER = "我来了。"


def _record_engine():
    llm = ScriptedLLM(RECORD_BLOCK)
    engine = _engine(llm)
    engine.send_vn_scene("（旁白）本章：测试。", annotate=False)
    return engine


def test_record_pick_is_materialized_into_history():
    """裁决 → 群里物化一条 `老师：X`; 未选候选与旧注解都不出现。"""
    engine = _record_engine()
    before = engine.history[-1]["content"]
    assert "老师：" not in before                          # 生成时槽未定 → 老师的话不出现
    assert RECORD_OTHER not in before and RECORD_PICKED not in before

    engine.record_picked(RECORD_PICKED)
    after = engine.history[-1]["content"]
    assert f"老师：{RECORD_PICKED}" in after
    assert RECORD_OTHER not in after                       # 未选台词永不进上下文
    assert "（选择了:" not in after                         # 旧注解退役
    # 位置: 物化行落在群首 —— 角色反应在**下一板**（§6 槽挂板尾, 不在本板渲染里）
    lines = after.split("\n")
    assert lines.index("igusa_haruka：……老师，你来了。") < lines.index(f"老师：{RECORD_PICKED}")
    # 真源不受影响: payload 仍保留整群候选（未选只在渲染层消失）
    assert engine._last_payload["choices"] == [RECORD_OTHER, RECORD_PICKED]
    nxt = engine.send_vn_scene("（继续）", annotate=False)  # 待发板（0 LLM）= 反应
    assert [p["text"] for p in nxt.paragraphs] == ["「不、不用这样的……」"]
    assert RECORD_OTHER not in "\n".join(p["text"] for p in nxt.paragraphs)
    print("    picked: 裁决物化为 `老师：X`（未选候选不进上下文）")


def test_live_and_replay_byte_identical_on_records():
    """A1 不变式（记录流版）: live 尾部 == 事件流渲染（同一函数同一 payload+picked）。"""
    from core.session.events import make_event
    from core.session.renderer import render_events

    engine = _record_engine()
    engine.record_picked(RECORD_PICKED)
    live_tail = engine.history[-1]["content"]

    payload = dict(engine._last_payload)
    payload["input"] = "（旁白）本章：测试。"
    payload["picked"] = RECORD_PICKED
    event = make_event("bond", "story_scene", payload, seq=1)
    replayed = render_events([event])
    assert replayed[-1]["content"] == live_tail             # 逐字节同形
    assert "（选择了:" not in live_tail
    print("    picked: live == 回放（逐字节）")


def test_from_dict_keeps_picked_without_materializing():
    """**裁决句不进正文**（决策 #37: 玩家的话语永远只体现为选项）。

    `BondScene.from_dict(payload+picked)` 只把 `picked` 带在场景上（前端据此把
    选项组画成锁定态 + 高亮所选）——不再插进 paragraphs: 那句话一旦当正文上屏,
    配上角色的名字牌就会被读成"角色说了玩家的话"（真机报障）。
    """
    from core.bond.bond_story import BondScene

    engine = _record_engine()
    payload = dict(engine._last_payload)
    payload["picked"] = RECORD_PICKED
    scene = BondScene.from_dict(payload)

    texts = [p["text"] for p in scene.paragraphs]
    assert RECORD_PICKED not in texts, texts               # 不上屏
    assert RECORD_OTHER not in texts
    assert scene.picked == RECORD_PICKED                   # 标记带回（选项态 UI 用）
    assert scene.choices                                   # 选项组保留（回放可显示）
    # 未给 picked → 场景无裁决标记（生成时形态）
    plain = BondScene.from_dict(engine._last_payload)
    assert plain.picked == "" and RECORD_PICKED not in [p["text"] for p in plain.paragraphs]
    # 往返: to_dict 带 picked, 再 from_dict 仍在
    assert BondScene.from_dict(scene.to_dict()).picked == RECORD_PICKED
    print("    picked: 只带标记不进正文（选项态 UI; 往返一致）")
