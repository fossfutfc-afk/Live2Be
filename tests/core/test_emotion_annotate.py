"""两遍式 C（生成骨架 + 情绪标注解耦）— 标注服务测试。

覆盖:
    annotate_emotions      正常/非法输出/LLM 异常/空输入/无词表
    fill_missing_emotions  骨架补标/延续兜底/部分缺漏/依赖注入
    引擎集成                send_vn_scene 记录流块 → 一板一组标注（反应板独立一组）
"""

import sys
from pathlib import Path

from llm import task_labels as T  # noqa: E402
from tests import stub_tasks  # noqa: E402
from tests.vn_fixtures import scene as _scene  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


class _AnnoLLM:
    """标注调用脚本化 LLM: 返回预设 tags / 抛异常 / 非法输出。"""

    def __init__(self, *scripts):
        self._s = list(scripts)
        self.calls = 0
        self.last_messages = None
        self.last_task = None

    def chat(self, messages, temperature=0.2, max_tokens=256,
             response_format="json_object", **kw):
        self.calls += 1
        self.last_messages = [dict(m) for m in messages]
        self.last_task = kw.get("task")        # 调用身份（节点 5b）
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
    assert llm.last_task == T.EMOTION, llm.last_task     # 调用身份（节点 5b）
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
        paras, annotator=lambda s, k, h, c: ["nomal", "smile", "embarrassed"],
        lexicon_keys=["nomal", "smile", "embarrassed"])
    assert out == [
        {"text": "她站在窗边。", "emotion": "nomal"},
        {"text": "老师来了！", "emotion": "smile"},
        {"text": "（她低下头）", "emotion": "embarrassed"},
    ]
    # 部分已有 emotion → 只补缺的
    paras2 = [{"text": "a", "emotion": "smile"}, {"text": "b"}, {"text": "c"}]
    out2 = fill_missing_emotions(
        paras2, annotator=lambda s, k, h, c: ["embarrassed", "nomal"],
        lexicon_keys=["nomal", "smile", "embarrassed"])
    assert out2[0]["emotion"] == "smile"          # 已有保留
    assert out2[1]["emotion"] == "embarrassed"
    assert out2[2]["emotion"] == "nomal"
    # 无缺漏 → 不调用
    paras3 = [{"text": "a", "emotion": "smile"}]
    calls = {"n": 0}
    fill_missing_emotions(paras3, annotator=lambda s, k, h, c: calls.__setitem__("n", calls["n"] + 1) or [], lexicon_keys=["nomal"])
    assert calls["n"] == 0
    print("    fill: 骨架补标（部分缺只补缺, 已有保留, 无缺不调用）")


def test_fill_missing_fallback():
    from core.bond.emotion_annotate import fill_missing_emotions

    # 标注不可用（None）→ 延续前一句（首句默认 nomal）
    paras = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    out = fill_missing_emotions(paras, annotator=lambda s, k, h, c: None,
                                lexicon_keys=["nomal", "smile"])
    assert [p["emotion"] for p in out] == ["nomal", "nomal", "nomal"]
    # 标注部分非法 → 非法位延续
    paras2 = [{"text": "a"}, {"text": "b"}, {"text": "c"}]
    out2 = fill_missing_emotions(paras2, annotator=lambda s, k, h, c: ["smile", None, "nomal"],
                                 lexicon_keys=["nomal", "smile"])
    assert [p["emotion"] for p in out2] == ["smile", "smile", "nomal"]  # b 延续 a
    print("    fill: 标注不可用/非法位 → 延续兜底（首句 nomal）")


# ----------------------------------------------------------------------------
# robust 标注（2026-09-02）: 二分降级 + 逐项容错 + character 注入
# ----------------------------------------------------------------------------

def test_annotate_smart_binary_split():
    """全量失败 → 二分递归: 左半成功右半再失败再拆——局部错只牺牲局部。"""
    from core.bond.emotion_annotate import annotate_emotions_smart

    class SplitLLM:
        def __init__(self):
            self.calls: list[int] = []
        def chat(self, messages, **kw):
            self.calls.append(0)                       # 每次调用都失败
            raise RuntimeError("api down")

    llm = SplitLLM()
    # 4 句全失败 → 递归拆解, 但 LLM 调用被全局预算硬顶（2026-09-08: 防 27s 级
    # 串行爆炸, 预算 _ANNO_CALL_BUDGET=4）——预算耗尽即停, 剩余整批 None
    tags = annotate_emotions_smart(llm, ["a", "b", "c", "d"], ["nomal"])
    assert tags == [None, None, None, None]
    assert len(llm.calls) == 4, f"预算 4 次调用: {llm.calls}"
    # 空输入 → [] / 无词表 → 全 None 不调用
    assert annotate_emotions_smart(llm, [], ["nomal"]) == []
    assert annotate_emotions_smart(SplitLLM(), ["x"], []) == [None]
    print("    smart: 全失败 → 二分递归但预算封顶 4 次全 None; 空输入/无词表短路")


def test_annotate_smart_partial_recover():
    """二分降级恢复: 全量坏 → 左右半各自成功（各自一次调用）。"""
    from core.bond.emotion_annotate import annotate_emotions_smart

    class HalfLLM:
        def __init__(self):
            self.n = 0
        def chat(self, messages, **kw):
            self.n += 1
            if self.n == 1:
                return "[bad"                          # 全量坏（解析失败）
            return ["nomal", "smile"]                  # 半组成功

    tags = annotate_emotions_smart(HalfLLM(), ["a", "b", "c", "d"], ["nomal", "smile"])
    assert tags == ["nomal", "smile", "nomal", "smile"], tags
    print("    smart: 全量坏 → 左右半成功（1 + 2 次调用, 局部恢复）")


def test_annotate_smart_per_item_tolerance():
    """逐项容错: 长度对齐但个别词表外 → 该项 None, 其余保留（不整批弃）。"""
    from core.bond.emotion_annotate import annotate_emotions_smart

    class OneBadLLM:
        def chat(self, messages, **kw):
            return ["smile", "not_in_lexicon", "nomal"]

    tags = annotate_emotions_smart(OneBadLLM(), ["a", "b", "c"], ["nomal", "smile"])
    assert tags == ["smile", None, "nomal"], tags
    print("    smart: 词表外单项 → None, 其余保留")


def test_annotate_character_injected():
    """character 人设注入: prompt system 含角色段（标注层人设化判断基准）。"""
    from core.bond.emotion_annotate import _try_batch

    seen = {}

    class SpyLLM:
        def chat(self, messages, **kw):
            seen["system"] = messages[0]["content"]
            return ["nomal"]

    tags = _try_batch(SpyLLM(), ["她笑着说没事。"], ["nomal", "smile"],
                      "", "角色: 测试（性格: 逞强, 把错归己）", max_tokens=256)
    assert tags == ["nomal"]
    assert "角色: 测试" in seen["system"], seen["system"][:200]
    assert "逞强" in seen["system"]
    print("    smart: character 人设段注入标注 prompt")


def test_engine_fill_passes_character():
    """引擎集成: 标注层注入角色人设（_character_hint 非空且含遥香性格）。"""
    from core.bond.bond_story import BondStoryEngine

    skeleton = "line"

    class ScriptedLLM:
        def __init__(self):
            self.seen_system: str = ""
            self._scripts = [_scene(lines=["对不起……我又做错了……"])]
        def chat(self, messages, **kw):
            task = kw.get("task")
            head = messages[0]["content"]
            if task == T.EMOTION:                    # 记录标注（节点 5b: 按 task 分派）
                self.seen_system = head
                return ["depressed"]
            if task in T.MAIN:
                if not self._scripts:
                    raise RuntimeError("脚本耗尽")
                return self._scripts.pop(0)
            reply = stub_tasks.annotation_reply(task, messages)
            if reply is not None:
                return reply
            raise stub_tasks.unknown_task(task)
        def format_messages(self, **kw):
            return []

    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM())
    vn.start_session("igusa_haruka")
    vn._place_keys = []          # 本组用例只关心 emo 路（place 关断）
    assert "遥香" in vn._character_hint, vn._character_hint
    assert "自卑" in vn._character_hint or "胆小" in vn._character_hint, \
        vn._character_hint
    scene = vn.send_vn_scene("（开场）")
    assert scene.paragraphs[0]["emotion"] == "depressed", scene.paragraphs
    assert skeleton == "line"        # 占位（下方用例共用记录流夹具）
    print("    engine: 标注 prompt 带遥香人设（自卑/胆小行为逻辑）")


def test_engine_skeleton_annotated():
    """记录流 v2: 一板一组标注（正文 2 条 → 1 次调用）; 反应板独立一组（槽挂板尾）。"""
    from core.bond.bond_story import BondStoryEngine

    block = _scene(lines=["她站在窗边。", "啊，老师……你来得正好。"],
                   sensei=["走过去", "笑着说"], after=["她张了张嘴。"])

    class ScriptedLLM:
        def __init__(self):
            self._scripts = [block, ["nomal", "embarrassed"], ["expectant"]]
        def chat(self, messages, **kw):
            if not self._scripts:
                raise RuntimeError("脚本耗尽")
            return self._scripts.pop(0)
        def format_messages(self, **kw):
            return []

    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM())
    vn.start_session("igusa_haruka")
    vn._place_keys = []          # 本组用例只关心 emo 路（place 关断）
    scene = vn.send_vn_scene("（开场）")
    assert [p["emotion"] for p in scene.paragraphs] == ["nomal", "embarrassed"], \
        scene.paragraphs
    assert scene.choices == ["走过去", "笑着说"]
    nxt = vn.send_vn_scene("（继续）")                       # 待发板（0 LLM）
    assert [p["text"] for p in nxt.paragraphs] == ["她张了张嘴。"]
    assert nxt.paragraphs[0]["emotion"] == "expectant"
    print("    engine: 一板一组标注 + 反应板独立标注")


def test_engine_skeleton_annotate_failure_degrade():
    """标注全失败 → 静默兜底（nomal/延续）, 剧情不阻断（失败成本 O(0)）。"""
    from core.bond.bond_story import BondStoryEngine

    block = _scene(lines=["她站在窗边。", "老师来了！"])

    class ScriptedLLM:
        def __init__(self):
            self._scripts = [block, RuntimeError("api down"), RuntimeError("api down")]
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
    vn._place_keys = []          # 本组用例只关心 emo 路（place 关断）
    scene = vn.send_vn_scene("（开场）")          # 标注异常 → 不 raise
    assert scene.paragraphs[0]["emotion"] == "nomal"   # 首条兜底
    assert scene.paragraphs[1]["emotion"] == "nomal"   # 延续
    print("    engine: 标注失败 → 静默兜底（nomal/延续）, 剧情不阻断")


def test_engine_inline_emotion_discarded():
    """2026-09-02 定稿（记录流版）: 记录自带 emotion（旧桩习惯）→ 契约层**丢弃**
    （多余字段只记 NOTE）, 标注层全量回填（唯一真源——防双源/锚定）。"""
    from core.bond.bond_story import BondStoryEngine

    # 手工拼两行, 带上旧版才会写的 emotion 字段
    block = "\n".join([
        '{"character": "igusa_haruka", "text": "她笑了。", "emotion": "smile"}',
        '{"character": "igusa_haruka", "text": "她低下头。", "emotion": "embarrassed"}',
    ])

    class ScriptedLLM:
        def __init__(self):
            self._scripts = [block, ["smile", "embarrassed"]]
        def chat(self, messages, **kw):
            if not self._scripts:
                raise RuntimeError("脚本耗尽")
            return self._scripts.pop(0)
        def format_messages(self, **kw):
            return []

    vn = BondStoryEngine(ROOT / "config" / "characters", ScriptedLLM())
    vn.start_session("igusa_haruka")
    vn._place_keys = []          # 本组用例只关心 emo 路（place 关断）
    scene = vn.send_vn_scene("（开场）")
    # 标注层回填（值与骨架同——模型自己写的情绪被独立标注确认）; 记录里不带 emotion
    assert scene.paragraphs[0]["emotion"] == "smile"
    assert scene.paragraphs[1]["emotion"] == "embarrassed"
    assert all("emotion" not in r for r in scene.records)
    assert any("多余字段" in n for n in scene.notes)
    print("    engine: 记录自带 emotion → 丢弃后由标注层全量回填（唯一真源）")


if __name__ == "__main__":
    for fn in sorted(k for k, v in globals().items() if k.startswith("test_")):
        fn()
