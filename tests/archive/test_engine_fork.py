# -*- coding: utf-8 -*-
"""SceneStream P1.5 — 候选支 fork 原语（DESIGN_CHOICE_PREGEN §2, N1）。

覆盖:
    fork_for_pick   只读共享(system 同字节) + 可变独立(历史 A1 内嵌裁决行 /
                     标注链/place 延续/para_seq) + 草稿零污染 live
    fork 后 send    两路独立预生成, live 历史不动, 链各自推进
    director 克隆   视觉记忆独立延续（catalog 只读共享）
    守卫            未开场/无上一板/空白 picked/纪念模式 → None
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

BOARD1 = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "她低着头站在窗边，像是鼓足了勇气才开口。"}],
    "choices": ["选A", "选B"],
    "branches": {"选A": [{"text": "她怔了一下，点了点头。"}],
                 "选B": [{"text": "她抿抿嘴，没有说话。"}]}}}
NEXT_A = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "她终于抬起脸，眼睛亮亮的。「嗯，那说好了。」"}]}}
NEXT_B = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "她摇了摇头，声音闷闷的。「不了……今天就算了吧。」"}]}}


class ScriptedLLM:
    """场景脚本按序弹出; 情绪/place 标注调用自动应答（不消耗脚本）。"""

    def __init__(self, *scripts):
        self._s = list(scripts)
        self.calls = 0

    def chat(self, messages, **kw):
        self.calls += 1
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last:
            n = len(re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        if "变更句数组" in last:
            return []
        if not self._s:
            raise RuntimeError("脚本耗尽")
        return self._s.pop(0)


def _engine(llm, *, director=None):
    from core.bond.bond_story import BondStoryEngine

    vn = BondStoryEngine(ROOT / "config" / "characters", llm, director=director)
    vn.start_session("igusa_haruka")
    return vn


def _plain_scene(llm, payload):
    llm._s.insert(0, {"action": "story_scene", "payload": payload})


# ----------------------------------------------------------------------------
# fork: 只读共享 + A1 内嵌 + live 零污染
# ----------------------------------------------------------------------------

def test_fork_embeds_pick_and_leaves_live_untouched():
    vn = _engine(ScriptedLLM(BOARD1))
    scene = vn.send_vn_scene("（开场）", annotate=False)
    hist_before = vn.history

    fa = vn.fork_for_pick("选A")
    fb = vn.fork_for_pick("选B")
    assert fa is not None and fb is not None
    # 只读面共享: system 同字节（跨支前缀缓存成立的关键）
    assert fa._system_prompt == vn._system_prompt
    assert fb._system_prompt == vn._system_prompt
    # fork 历史 = 主线历史 + A1 同形回录（各自裁决行内嵌）
    assert fa.history_length == fb.history_length == len(hist_before)
    assert "（选择了: 选A）" in fa._history[-1]["content"], \
        fa._history[-1]["content"][-160:]
    assert "（选择了: 选B）" in fb._history[-1]["content"]
    assert fa._history[-1]["content"] != fb._history[-1]["content"]
    # live 零污染: 无裁决行、长度不变
    assert vn.history == hist_before
    assert "（选择了:" not in vn.history[-1]["content"]
    # 草稿标记 + 独立实例
    assert fa is not vn and getattr(fa, "_draft", False) is True
    print("    fork: system 同字节 / A1 内嵌裁决行 / live 零污染 / _draft 标记")


def test_fork_send_independent_paths():
    llm = ScriptedLLM(BOARD1, NEXT_A, NEXT_B)
    vn = _engine(llm)
    vn.send_vn_scene("（开场）", annotate=True)      # 主线 1 板（含标注）
    live_hist_len = vn.history_length

    fa = vn.fork_for_pick("选A")
    fb = vn.fork_for_pick("选B")
    assert fa is not None and fb is not None
    fork_base = fa._para_seq                       # fork 复制时的主线链
    assert fork_base == vn._para_seq == fb._para_seq
    sa = fa.send_vn_scene("（继续）", annotate=True)
    sb = fb.send_vn_scene("（继续）", annotate=True)
    # 两路各自生成、内容不同（脚本不同）; live 未新增历史
    sa_text = "".join(p.get("text", "") for p in sa.paragraphs)
    sb_text = "".join(p.get("text", "") for p in sb.paragraphs)
    assert "说好了" in sa_text and "今天就算了吧" in sb_text
    assert vn.history_length == live_hist_len
    # 标注链分岔（预期内）: fork 复制主线链后各自再推进一步（正文段组）,
    # live 链不动（para_seq 含正文+branch 组, 故用相对增量断言）
    assert fa._para_seq == fork_base + 1 and fb._para_seq == fork_base + 1
    assert vn._para_seq == fork_base
    assert fa._carry_emo == "nomal" and fb._carry_emo == "nomal"
    assert fa._carry_text != "" and fb._carry_text != ""
    # 两路间互不可见
    assert fa._history[-1]["content"] != fb._history[-1]["content"]
    assert fa.history_length == fb.history_length
    print("    fork-send: 两路独立预生成 / live 零新增 / 标注链各自推进")


# ----------------------------------------------------------------------------
# director 克隆: 视觉记忆独立延续
# ----------------------------------------------------------------------------

def test_fork_director_clone_independent():
    from core.bond.bond_story import BondStoryEngine
    from core.director.director import Director

    class FakeCat:
        def background_scenes(self):
            return ["rooftop", "class_room"]

    d = Director(FakeCat(), "igusa_haruka", default_background="neutral")
    vn = _engine(ScriptedLLM(BOARD1), director=d)
    vn.send_vn_scene("（开场）", annotate=False)

    fa = vn.fork_for_pick("选A")
    assert fa is not None and fa.director is not d            # 克隆而非共享
    assert fa.director.state.background == d.state.background  # 同一起点
    fa.director.visual_for("rooftop")
    assert fa.director.state.background == "rooftop"
    assert d.state.background != "rooftop"                    # 主线视觉不被候选污染
    print("    fork-director: 克隆独立（候选换景不污染主线视觉记忆）")


# ----------------------------------------------------------------------------
# 守卫: None 路径
# ----------------------------------------------------------------------------

def test_fork_guards():
    from core.bond.bond_story import BondStoryEngine

    llm = ScriptedLLM(BOARD1)
    # 未开场 → None
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    assert vn.fork_for_pick("选A") is None
    # 无上一板（_last_payload 为空, 历史空）→ None
    vn2 = _engine(ScriptedLLM())
    assert vn2.fork_for_pick("选A") is None
    # 空白 picked → None
    vn3 = _engine(ScriptedLLM(BOARD1))
    vn3.send_vn_scene("（开场）", annotate=False)
    assert vn3.fork_for_pick("") is None
    assert vn3.fork_for_pick("   ") is None
    assert vn3.fork_for_pick(123) is None
    # 纪念模式中 → None（防御: 纪念内只有 exit, 无选项板）
    vn3._in_memorial = True
    assert vn3.fork_for_pick("选A") is None
    print("    fork 守卫: 未开场/无板/空白 picked/纪念模式 → None")


if __name__ == "__main__":
    for fn in sorted(k for k, v in globals().items() if k.startswith("test_")):
        fn()
