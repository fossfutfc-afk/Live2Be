# -*- coding: utf-8 -*-
"""place 地点变更标注单测（DESIGN_BOND_CONTRACT_V2 §5/P2）。

判定语义由 place_annotate.md prompt 承担（镜像编剧 rules 换场判据）; 本文件测
模块行为: 调用形状/清洗规则（越界、词表外、与当前相同、重复）/失败 keep 语义/
prompt 占位替换/与 rules 的判据镜像防漂移。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.place_annotate import _clean_anchors, annotate_places
from llm.prompts import load_prompt
from llm.task_levels import max_tokens as tl_max_tokens

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"
KEYS = ["campus", "classroom", "hallway", "rooftop", "ramen"]


class ScriptedLLM:
    """chat 文本模式桩（记录调用, 按序返回脚本）。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.calls = []

    def chat(self, messages, **kw):
        self.calls.append({"messages": [dict(m) for m in messages], "kw": kw})
        return self._scripts.pop(0)

    def chat_full(self, messages, **kw):     # 未用; 保持接口完整
        raise AssertionError("place 标注应走 chat（text 模式）")


SENTENCES = [
    "她在教室里收拾着书包。",
    "「老师，今天也陪我一会儿吧。」",
    "她带我穿过走廊，推开了天台的门。",
    "晚风迎面吹来。",
]


# ---------------------------------------------------------------------------
# 清洗规则（逐项容错）
# ---------------------------------------------------------------------------

def test_clean_anchors_rules():
    """越界/词表外/与当前相同/重复 → 丢弃; 排序去重; 类型容错。"""
    raw = [
        {"sentence": 3, "place": "rooftop"},      # 合法
        {"sentence": 3, "place": "ramen"},         # 同句重复 → 后者胜
        {"sentence": 99, "place": "rooftop"},      # 越界 → 丢
        {"sentence": 1, "place": "教室"},           # 词表外 → 丢
        {"sentence": 2, "place": "campus"},        # 与当前相同 → 丢
        {"sentence": "4", "place": "hallway"},     # str 序号 → 合法(4)
        {"foo": 1},                                 # 坏项 → 丢
        "bad",                                      # 非 dict → 丢
    ]
    out = _clean_anchors(raw, len(SENTENCES), set(KEYS), "campus")
    assert out == [
        {"sentence": 3, "place": "ramen"},          # 后者覆盖同句
        {"sentence": 4, "place": "hallway"},
    ], out
    assert _clean_anchors("garbage", 4, set(KEYS), "") == []
    assert _clean_anchors([], 4, set(KEYS), "") == []


# ---------------------------------------------------------------------------
# annotate_places 行为
# ---------------------------------------------------------------------------

def test_annotate_places_valid_and_prompt_shape():
    """合法返回: 锚点清洗后回传; prompt 占位全部替换（无残留 {}）。"""
    llm = ScriptedLLM([{"sentence": 3, "place": "rooftop"}])
    out = annotate_places(llm, SENTENCES, KEYS, "classroom")
    assert out == [{"sentence": 3, "place": "rooftop"}], out
    assert len(llm.calls) == 1
    sys_text = llm.calls[0]["messages"][0]["content"]
    assert "{lexicon}" not in sys_text and "{sentences}" not in sys_text
    assert "{current_place}" not in sys_text
    assert "当前所在地" in sys_text and "classroom" in sys_text
    assert "1: 她在教室里收拾着书包。" in sys_text          # 编号句子
    assert llm.calls[0]["kw"].get("temperature") == 0.2
    assert llm.calls[0]["kw"].get("extra_body") == {}       # off-thinking 真源


def test_annotate_places_empty_inputs():
    """空句/空词表 → 直接 []（不调 LLM）。"""
    llm = ScriptedLLM()
    assert annotate_places(llm, [], KEYS, "") == []
    assert annotate_places(llm, SENTENCES, [], "") == []
    assert llm.calls == []


def test_annotate_places_none_current_first_change():
    """current 未知: 首次出现的变更句即可作起始锚点。"""
    llm = ScriptedLLM([{"sentence": 1, "place": "classroom"}])
    out = annotate_places(llm, SENTENCES, KEYS, "")
    assert out == [{"sentence": 1, "place": "classroom"}], out


def test_annotate_places_failure_retry_then_keep():
    """坏形状 → 重试（提醒句）; 重试成功返回; 全败 → []（keep）。"""
    llm = ScriptedLLM("不是数组", [{"sentence": 3, "place": "rooftop"}])
    out = annotate_places(llm, SENTENCES, KEYS, "classroom", retries=1)
    assert out == [{"sentence": 3, "place": "rooftop"}]
    assert len(llm.calls) == 2
    assert "上一次输出无法解析" in llm.calls[1]["messages"][1]["content"]

    llm2 = ScriptedLLM("不是数组", "还是不是")
    out2 = annotate_places(llm2, SENTENCES, KEYS, "classroom", retries=1)
    assert out2 == []                                     # keep 兜底
    assert len(llm2.calls) == 2

    llm3 = ScriptedLLM([{"sentence": 3, "place": "rooftop"}])
    out3 = annotate_places(llm3, SENTENCES, KEYS, "rooftop")   # 当前已 rooftop
    assert out3 == []                                         # 相等 → keep
    assert len(llm3.calls) == 1


def test_annotate_places_llm_exception_keep():
    """LLM 异常 → 静默 []（keep, 不阻断）。"""
    class BoomLLM:
        def chat(self, messages, **kw):
            raise RuntimeError("boom")

    assert annotate_places(BoomLLM(), SENTENCES, KEYS, "") == []


def test_annotate_places_max_tokens_truth_source():
    """max_tokens 真源 = task_levels 形态 place（默认 256; 显式可覆盖）。"""
    assert tl_max_tokens("place") == 256
    llm = ScriptedLLM([])
    annotate_places(llm, SENTENCES, KEYS, "", max_tokens=64)
    assert llm.calls[0]["kw"]["max_tokens"] == 64
    llm2 = ScriptedLLM([])
    annotate_places(llm2, SENTENCES, KEYS, "")
    assert llm2.calls[0]["kw"]["max_tokens"] == 256


# ---------------------------------------------------------------------------
# 判据镜像防漂移（rules ↔ place_annotate——改判据两处同改）
# ---------------------------------------------------------------------------

def test_judgement_mirror_between_rules_and_prompt():
    """关键判据示例句必须同时存在于 编剧 rules 与 place prompt（防单侧漂移）。"""
    rules = load_prompt("bond_story_rules")
    place = load_prompt("place_annotate")
    for token in ("从…走进", "推开", "转身", "来到"):
        assert token in rules, f"rules 缺判据示例: {token}"
        assert token in place, f"place prompt 缺判据示例: {token}"


# ---------------------------------------------------------------------------
# 引擎同步路径集成（P3a: annotate=True → fill_scene_places 接线）
# ---------------------------------------------------------------------------

SCENE = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "她在教室里收拾着书包。"},
                   {"text": "「老师，今天也陪我一会儿吧。」"},
                   {"text": "她带我穿过走廊，推开了天台的门。"},
                   {"text": "晚风迎面吹来。"}]}}


class EngineLLM:
    """同步路径桩: chat_full 出场景; chat 应答 place 标注（锚点/空）。"""

    def __init__(self, *place_replies):
        self._scripts = list(place_replies)
        self.calls = []

    def chat_full(self, messages, **kw):
        return SCENE

    def chat(self, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        return self._scripts.pop(0)


def _engine_with(place_keys, place_replies):
    from core.bond.bond_story import BondStoryEngine
    llm = EngineLLM(*place_replies)
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    engine._lexicon_keys = []                 # 本测试只关心 place 路
    engine._place_keys = place_keys
    engine._current_place = ""
    return engine, llm


def test_engine_sync_fill_scene_places():
    """同步路径: 锚点写回 payload（变更句 place 键）; 当前地点延续; 上下文隔离。"""
    from core.session.renderer import render_bond_scene_text
    engine, llm = _engine_with(["classroom", "rooftop"],
                               [[{"sentence": 3, "place": "rooftop"}]])
    scene = engine.send_vn_scene("（旁白）本章：测试。", annotate=True)
    assert scene.paragraphs[2].get("place") == "rooftop", scene.paragraphs
    assert all("place" not in p for i, p in enumerate(scene.paragraphs) if i != 2)
    assert engine._current_place == "rooftop"                 # 延续态顺延

    # place 视觉键不进 LLM 上下文（render 忽略）
    text = render_bond_scene_text(scene.to_dict())
    assert "rooftop" not in text and "place" not in text, text

    # 第二场: 当前地点带入标注 prompt（“当前所在地…rooftop”）; 无变更 → keep
    engine2, llm2 = _engine_with(["classroom", "rooftop"], [[]])
    engine2._current_place = "rooftop"
    engine2.send_vn_scene("（旁白）第二场。", annotate=True)
    sys_text = llm2.calls[0][0]["content"]
    assert "rooftop" in sys_text                               # 当前地点已注入
    assert engine2._current_place == "rooftop"                 # 无变更 → 保持


def test_engine_sync_no_place_keys_no_call():
    """无地点词表 → place 标注不触发（零调用, 与改动前行为一致）。"""
    engine, llm = _engine_with([], [])
    scene = engine.send_vn_scene("（旁白）本章：测试。", annotate=True)
    assert all("place" not in p for p in scene.paragraphs)
    assert llm.calls == []
