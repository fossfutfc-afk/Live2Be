# -*- coding: utf-8 -*-
"""两遍式 C（生成骨架 + 情绪标注解耦）— 标注服务测试。

覆盖:
    annotate_emotions      正常/非法输出/LLM 异常/空输入/无词表
    fill_missing_emotions  骨架补标/延续兜底/部分缺漏/依赖注入
    引擎集成                send_vn_scene 骨架 → 标注 attach（正文 + branches）
"""

import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class _AnnoLLM:
    """标注调用脚本化 LLM: 返回预设 tags / 抛异常 / 非法输出。"""

    def __init__(self, *scripts):
        self._s = list(scripts)
        self.calls = 0
        self.last_messages = None

    def chat(self, messages, temperature=0.2, max_tokens=256, response_format="json_object"):
        self.calls += 1
        self.last_messages = [dict(m) for m in messages]
        if not self._s:
            raise RuntimeError("脚本耗尽")
        return self._s.pop(0)


def _annos(*scripts):
    llm = _AnnoLLM(*scripts)
    from core.bond.emotion_annotate import annotate_emotions

    tags = annotate_emotions(llm, ["她站在窗边。", "老师来了！", "（她低下头）"],
                             ["nomal", "smile", "embarrassed", "expectant"])
    return llm, tags


# ----------------------------------------------------------------------------
# annotate_emotions: 清洗/校验/降级
# ----------------------------------------------------------------------------

def test_annotate_normal():
    llm, tags = _annos(["nomal", "smile", "embarrassed"])
    assert llm.calls == 1
    assert tags == ["nomal", "smile", "embarrassed"]
    # prompt 组装: 词表 + 句子行号都在
    sys_msg = llm.last_messages[0]["content"]
    assert "nomal" in sys_msg and "embarrassed" in sys_msg
    assert "1: 她站在窗边。" in sys_msg and "3: （她低下头）" in sys_msg
    print("    annotate: 正常标注（3 句 → 3 标签, prompt 含词表+行号）")


def test_annotate_invalid_output_fallback():
    # 长度不齐 → None（调用方兜底）
    _, tags = _annos(["nomal", "smile"])
    assert tags is None
    # 词表外 → None
    _, tags = _annos(["nomal", "angry_xyz", "embarrassed"])
    assert tags is None
    # 非数组 → None
    _, tags = _annos("nomal")
    assert tags is None
    print("    annotate: 非法输出（长度/词表外/非数组）→ None 兜底")


def test_annotate_llm_error_and_edges():
    from core.bond.emotion_annotate import annotate_emotions

    # LLM 异常 → None
    llm = _AnnoLLM()
    llm.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("api down"))
    tags = annotate_emotions(llm, ["句一。"], ["nomal"])
    assert tags is None
    # 空句子 → []
    llm2 = _AnnoLLM()
    assert annotate_emotions(llm2, [], ["nomal"]) == []
    assert llm2.calls == 0
    # 无词表 → None（不调用 LLM）
    llm3 = _AnnoLLM()
    assert annotate_emotions(llm3, ["句一。"], []) is None
    assert llm3.calls == 0
    print("    annotate: LLM 异常/空输入/无词表 → 降级不调用")


# ----------------------------------------------------------------------------
# fill_missing_emotions: 骨架补标 + 延续兜底
# ----------------------------------------------------------------------------

def test_fill_missing_normal():
    from core.bond.emotion_annotate import fill_missing_emotions

    paras = [{"text": "她站在窗边。"}, {"text": "老师来了！"}, {"text": "（她低下头）"}]
    out = fill_missing_emotions(
        paras, annotator=lambda s, k, h: ["nomal", "smile", "embarrassed"],
        lexicon_keys=["nomal", "smile", "embarrassed"])
    assert out == [
        {"text": "她站在窗边。", "emotion": "nomal"},
        {"text": "老师来了！", "emotion": "smile"},
        {"text": "（她低下头）", "emotion": "embarrassed"},
    ]
    # 部分已有 emotion → 只补缺的
    paras2 = [{"text": "a", "emotion": "smile"}, {"text": "b"}, {"text": "c"}]
    out2 = fill_missing_emotions(
        paras2, annotator=lambda s, k, h: ["embarrassed", "nomal"],
        lexicon_keys=["nomal", "smile", "embarrassed"])
    assert out2[0]["emotion"] == "smile"          # 已有保留
    assert out2[1]["emotion"] == "embarrassed"
    assert out2[2]["emotion"] == "nomal"
    # 无缺漏 → 不调用
    paras3 = [{"text": "a", "emotion": "smile"}]
    calls = {"n": 0}
    fill_missing_emotions(paras3, annotator=lambda s, k, h: calls.__setitem__("n", calls["n"] + 1) or [], lexicon_keys=["nomal"])
    assert calls["n"] == 0
    print("    fill: 骨架补标（部分缺只补缺, 已有保留, 无缺不调用）")


def test_fill_missing_fallback():
    from core.bond.emotion_annotate import fill_missing_emotions

    # 标注不可用（None）→ 延续前一句（首句默认 nomal）
    paras = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    out = fill_missing_emotions(paras, annotator=lambda s, k, h: None,
                                lexicon_keys=["nomal", "smile"])
    assert [p["emotion"] for p in out] == ["nomal", "nomal", "nomal"]
    # 标注部分非法 → 非法位延续
    paras2 = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    out2 = fill_missing_emotions(paras2, annotator=lambda s, k, h: ["smile", "bad_key", "nomal"],
                                 lexicon_keys=["nomal", "smile"])
    assert [p["emotion"] for p in out2] == ["smile", "smile", "nomal"]  # b 延续 a
    print("    fill: 标注不可用/非法位 → 延续兜底（首句 nomal）")


# ----------------------------------------------------------------------------
# 引擎集成: send_vn_scene 骨架 → 标注 attach（正文 + branches）
# ----------------------------------------------------------------------------

def test_engine_skeleton_annotated():
    from core.bond.bond_story import BondStoryEngine

    skeleton = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "她站在窗边。"}, {"text": "啊，老师……你来得正好。"}],
        "choices": ["走过去", "笑着说"],
        "branches": {
            "走过去": [{"text": "她张了张嘴。"}],
            "笑着说": [{"text": "她松了口气。"}],
        }}}

    class ScriptedLLM:
        def __init__(self):
            self._scripts = [skeleton, ["nomal", "embarrassed"],
                             ["expectant"], ["smile"]]
        def chat(self, messages, **kw):
            if not self._scripts:
                raise RuntimeError("脚本耗尽")
            return self._scripts.pop(0)
        def format_messages(self, **kw):
            return []

    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM())
    vn.start_session("igusa_haruka")
    scene = vn.send_vn_scene("（开场）")
    # 正文 2 句已标注（1 次标注调用）
    assert scene.paragraphs[0]["emotion"] == "nomal", scene.paragraphs
    assert scene.paragraphs[1]["emotion"] == "embarrassed", scene.paragraphs
    # branches 各分支已标注（各 1 次标注调用）
    assert scene.branches["走过去"][0]["emotion"] == "expectant", scene.branches
    assert scene.branches["笑着说"][0]["emotion"] == "smile", scene.branches
    print("    engine: 骨架段落 + branches 全部经标注 attach（正文 1 次 + 分支各 1 次调用）")


def test_engine_skeleton_annotate_failure_degrade():
    """标注全失败 → 静默兜底（nomal/延续）, 剧情不阻断（失败成本 O(0)）。"""
    from core.bond.bond_story import BondStoryEngine

    skeleton = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "她站在窗边。"}, {"text": "老师来了！"}]}}

    class ScriptedLLM:
        def __init__(self):
            self._scripts = [skeleton, RuntimeError("api down"), RuntimeError("api down")]
        def chat(self, messages, **kw):
            if self._scripts and isinstance(self._scripts[0], RuntimeError):
                e = self._scripts.pop(0)
                raise e
            if not self._scripts:
                raise RuntimeError("脚本耗尽")
            return self._scripts.pop(0)
        def format_messages(self, **kw):
            return []

    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM())
    vn.start_session("igusa_haruka")
    scene = vn.send_vn_scene("（开场）")          # 标注异常 → 不 raise
    assert scene.paragraphs[0]["emotion"] == "nomal"   # 首句兜底
    assert scene.paragraphs[1]["emotion"] == "nomal"   # 延续
    print("    engine: 标注失败 → 静默兜底（nomal/延续）, 剧情不阻断")


def test_engine_inline_emotion_discarded():
    """2026-09-02 定稿: 骨架自带 emotion（旧桩习惯）→ 契约层**丢弃**, 标注层
    全量回填（标注层唯一真源——防双源/锚定; 旧输出带 emotion 兼容丢弃）。"""
    from core.bond.bond_story import BondStoryEngine

    inline = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "她笑了。", "emotion": "smile"},
                       {"text": "她低下头。", "emotion": "embarrassed"}]}}

    class ScriptedLLM:
        def __init__(self):
            self._scripts = [inline, ["smile", "embarrassed"]]
        def chat(self, messages, **kw):
            if not self._scripts:
                raise RuntimeError("脚本耗尽")
            return self._scripts.pop(0)
        def format_messages(self, **kw):
            return []

    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM())
    vn.start_session("igusa_haruka")
    scene = vn.send_vn_scene("（开场）")
    # 标注层回填（值与骨架同——模型自己写的情绪被独立标注确认）
    assert scene.paragraphs[0]["emotion"] == "smile"
    assert scene.paragraphs[1]["emotion"] == "embarrassed"
    print("    engine: 骨架自带 emotion → 丢弃后由标注层全量回填（唯一真源）")


if __name__ == "__main__":
    for fn in sorted(k for k, v in globals().items() if k.startswith("test_")):
        fn()
