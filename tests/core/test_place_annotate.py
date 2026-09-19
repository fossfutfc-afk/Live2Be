# -*- coding: utf-8 -*-
"""place 地点变更标注单测（DESIGN_BOND_CONTRACT_V2 §5/P2）。

判定语义由 place_annotate.md prompt 承担（镜像编剧 rules 换场判据）; 本文件测
模块行为: 调用形状/清洗规则（越界、词表外、与当前相同、重复）/失败 keep 语义/
prompt 占位替换/与 rules 的判据镜像防漂移。

**层1（C3, 2026-09-19）**: 表里的别名精确命中 = **0 调用**; 歧义（`天台`×3）与
表外（`杂草屋`）**不许猜**，下沉层2 读 `note`; `place_keys` 是"允许哪些键"的真源，
收窄时层1 不许越界。设计见 `docs/DESIGN_PLACE.md §6`。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.place_annotate import (_RESOLVE_CACHE, _clean_anchors,  # noqa: E402
                                      annotate_places, resolve_place)
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
    # off → 显式 thinking disabled（2026-09-08: 不传 = 默认思考吃光预算→空 content）
    assert llm.calls[0]["kw"].get("extra_body") == \
        {"thinking": {"type": "disabled"}}


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
# switch → 背景键翻译（P0-7 最小换场翻译; P1-2 会用 tempo 导出视图替换词表）
# ---------------------------------------------------------------------------

def test_resolve_place_translates_and_caches():
    """地点话 → 词表键: 命中词表 → 返回; 重复同一句 → 命中缓存（0 调用）。"""
    _RESOLVE_CACHE.clear()
    llm = ScriptedLLM('{"place": "rooftop"}')
    assert resolve_place(llm, "放学后的天台", KEYS, "") == "rooftop"
    assert len(llm.calls) == 1
    assert resolve_place(llm, "放学后的天台", KEYS, "") == "rooftop"
    assert len(llm.calls) == 1                       # 缓存命中 → 不再调用
    # prompt 占位替换（词表 + 地点话 + 当前地点）
    system = llm.calls[0]["messages"][0]["content"]
    assert "rooftop" in system and "放学后的天台" in system
    assert "还没定" in system                         # 空当前地点 → 占位文案
    print("    resolve: 地点话 → 键 + 缓存命中 0 调用")


def test_resolve_place_keep_on_bad_output():
    """词表外 / 与当前相同 / 形状坏 / 异常 → 一律 ""（keep——画面保持）。"""
    _RESOLVE_CACHE.clear()
    cases = [
        ('{"place": "not_in_lexicon"}', "", ""),     # 词表外
        ('{"place": "rooftop"}', "rooftop", ""),     # 与当前相同 → 不动画面
        ("随便说点什么", "", ""),                      # 形状坏（重试后仍坏）
        ('{"place": ""}', "", ""),                   # 模型自己给空
    ]
    for raw, current, expect in cases:
        llm = ScriptedLLM(raw, raw)                  # 重试一次仍给同样输出
        assert resolve_place(llm, f"地点{raw}{current}", KEYS, current) == expect
    class BoomLLM:
        def chat(self, messages, **kw):
            raise RuntimeError("boom")
    assert resolve_place(BoomLLM(), "某个地方", KEYS, "") == ""
    print("    resolve: 词表外/同地点/坏输出/异常 → keep")


def test_resolve_place_uses_place_task_level():
    """档位复用 place 形态（thinking off + 256），与标注层同源。"""
    _RESOLVE_CACHE.clear()
    llm = ScriptedLLM('{"place": "campus"}')
    resolve_place(llm, "校园里", KEYS, "")
    assert llm.calls[0]["kw"]["max_tokens"] == tl_max_tokens("place") == 256
    print("    resolve: 复用 place 档位（256）")


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
# 引擎同步路径集成（记录流 v2: switch 记录 → 背景键; 旧段落锚点路径随 v1 契约退役）
# ---------------------------------------------------------------------------

from tests.vn_fixtures import scene as _scene  # noqa: E402

#: 记录流一块: 换场 + 两条正文（v2 的换场信号 = `stage:switch`, 不再是段落锚点）
SCENE = _scene(switch_to="学校天台",
               lines=["她在教室里收拾着书包。", "「老师，今天也陪我一会儿吧。」"])


class EngineLLM:
    """同步路径桩: chat_full 出记录流; chat 应答换场翻译（键/空）。"""

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
    """同步路径（记录流 v2）: switch → 背景键写 scene.place; 延续态顺延; 视觉键不进上下文。"""
    from core.session.renderer import render_bond_scene_text
    engine, llm = _engine_with(["classroom", "rooftop"],
                               [{"place": "rooftop"}])
    scene = engine.send_vn_scene("（旁白）本章：测试。", annotate=True)
    assert scene.place == "rooftop", scene.place          # 背景键（导演/前端据此切图）
    assert scene.place_hint == "学校天台"                  # 记录流原文（writer 自己写的地点话）
    assert engine._current_place == "rooftop"             # 延续态顺延
    # 翻译 prompt 带上了词表与地点话
    sys_text = llm.calls[0][0]["content"]
    assert "rooftop" in sys_text and "学校天台" in sys_text

    # place 视觉键不进 LLM 上下文（渲染只出叙事 + switch 自己写的地点话）
    text = render_bond_scene_text(scene.to_dict())
    assert "rooftop" not in text, text

    # 第二场: 当前地点带入翻译 prompt; 模型给空 → keep（画面保持）
    engine2, llm2 = _engine_with(["classroom", "rooftop"], [{"place": ""}])
    engine2._current_place = "rooftop"
    engine2.send_vn_scene("（旁白）第二场。", annotate=True)
    assert "rooftop" in llm2.calls[0][0]["content"]        # 当前地点已注入
    assert engine2._current_place == "rooftop"             # 无变更 → 保持


def test_engine_sync_no_place_keys_no_call():
    """无地点词表 → 换场翻译不触发（零调用, 宁缺勿错: 画面保持）。"""
    engine, llm = _engine_with([], [])
    scene = engine.send_vn_scene("（旁白）本章：测试。", annotate=True)
    assert scene.place is None
    assert llm.calls == []


# ---------------------------------------------------------------------------
# 层1 别名命中（C3, 2026-09-19）——**0 调用**; 歧义/表外才下沉层2
# ---------------------------------------------------------------------------

def _table():
    from core.media.place_table import load_table
    t = load_table()
    assert t.ok, t.error
    return t


def test_layer1_hits_with_zero_calls():
    """★ 层1: 别名命中 → **一次 LLM 都不调**（真机 `教室`/`街角的咖啡馆` 就是这类）。"""
    _RESOLVE_CACHE.clear()
    t = _table()
    keys = t.keys()
    for text, want in (("教室", "classroom"),
                       ("街角的咖啡馆，靠窗的位子", "moderncafe"),
                       ("学校天台", "school_rooftop"),
                       ("星空", "view_sky")):
        llm = ScriptedLLM()                      # 空脚本 —— 一旦被调就 IndexError
        got = resolve_place(llm, text, keys, "", table=t)
        assert got == want, f"{text!r} → {got!r}（期望 {want!r}）"
        assert llm.calls == [], f"{text!r} 不该调用 LLM"
    print(f"    layer1: 4 条真机话 0 调用命中（教室/咖啡馆/学校天台/星空）")


def test_layer1_same_place_keeps_screen():
    """层1 命中 == 当前地点 → `""`（画面不动, 同样 0 调用）。"""
    _RESOLVE_CACHE.clear()
    t = _table()
    llm = ScriptedLLM()
    assert resolve_place(llm, "教室", t.keys(), "classroom", table=t) == ""
    assert llm.calls == []
    print("    layer1: 命中即当前地点 → keep（0 调用）")


def test_layer1_defers_ambiguity_and_out_of_table_to_layer2():
    """★ 层1 **不猜**: 歧义（天台×3）与表外（杂草屋）都下沉层2（1 次调用）。"""
    _RESOLVE_CACHE.clear()
    t = _table()
    for text in ("天台", "深夜的杂草屋", "某个不知名的地方"):
        llm = ScriptedLLM('{"place": "school_rooftop"}')
        got = resolve_place(llm, text, t.keys(), "", table=t)
        assert got == "school_rooftop" and len(llm.calls) == 1, (text, got, llm.calls)
    # 歧义但 current 就在候选里 → 已经在那一带 → keep（0 调用）
    _RESOLVE_CACHE.clear()
    llm = ScriptedLLM()
    assert resolve_place(llm, "天台", t.keys(), "school_rooftop", table=t) == ""
    assert llm.calls == []
    print("    layer1: 歧义/表外 → 层2; 歧义∩当前 → keep")


def test_layer1_never_leaves_the_allowed_key_set():
    """★ `place_keys` 才是"允许哪些键"的真源（表只是语料）——收窄后层1 不许越界。"""
    _RESOLVE_CACHE.clear()
    t = _table()
    llm = ScriptedLLM('{"place": "class_room"}')     # 收窄后的唯一键
    got = resolve_place(llm, "教室", ["class_room"], "", table=t)
    assert got == "class_room", got                   # 层1 的 classroom 被挡下 → 层2
    assert len(llm.calls) == 1
    print("    layer1: 键集收窄时以 place_keys 为准（两个真源不许打架）")


def test_lexicon_text_carries_note_only_with_table():
    """层2 词表: 有表 → 整表**含 note**; 无表 → 旧口径（裸 id, 降级用）。"""
    _RESOLVE_CACHE.clear()
    t = _table()
    e = t.get("view_sky")
    llm = ScriptedLLM('{"place": "view_sky"}')
    resolve_place(llm, "表外地名甲乙丙", t.keys(), "", table=t)
    sys_text = llm.calls[0]["messages"][0]["content"]
    assert e.note in sys_text, "note 没进层2 词表 → 表外只能瞎猜"
    assert "【SDIR_" in sys_text, "没按 sdir 分组"
    # 无表: 退回裸 id 列表（老行为, 兼容）
    _RESOLVE_CACHE.clear()
    llm2 = ScriptedLLM('{"place": "rooftop"}')
    resolve_place(llm2, "另一个表外地名", KEYS, "")
    sys2 = llm2.calls[0]["messages"][0]["content"]
    assert "rooftop" in sys2 and "【SDIR_" not in sys2
    print("    lexicon: 有表带 note（含分组）; 无表退回裸 id")


def test_engine_maps_place_key_to_asset_scene_id():
    """★ 引擎把语义键翻成资产 scene_id 再喂导演（C5）——`classroom` → `class_room`。

    不翻的话 `visual_for` 的 `place in background_scenes` 闸门会静默拦住一切，
    背景永远停在 `neutral`（真机 20/20 板就是这个症状）。
    """
    from core.bond.bond_story import BondStoryEngine
    llm = EngineLLM()
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    assert engine._place_scene_id("classroom") == "class_room"
    assert engine._place_scene_id("68office") == "kohshinjo_room"
    assert engine._place_scene_id("school_rooftop") == "school_rooftop"
    assert engine._place_scene_id(None) is None
    assert engine._place_scene_id("没这个键") == "没这个键"      # 原样传, 不阻断
    print("    engine: 语义键 → 资产 scene_id（导演闸门才放行）")


def test_engine_switch_board_also_gets_sentence_anchors():
    """★ C6（2026-09-19）: **switch 板也要跑句级锚点** —— 消掉"二选一早返回"。

    此前板首有 `switch` 就 `return`，板内**后续换场永远标不出来**
    （writer 写「她拉着我走出教室」而没再发 switch → 画面不动）。
    现在 ① 板首 switch → 板级地点, ② 句级锚点覆盖板内后续换场, 顺序固定。

    本用例: switch=「教室」（层1 命中 → **0 调用**）+ 板内第二次移动（第 2 句）。
    总调用 = 1（只有 ②）——**这就是"没有早返回"的铁证**。
    """
    from core.bond.bond_story import BondStoryEngine
    board = _scene(switch_to="教室",
                   lines=["她放下书包。", "她拉着我走出教室，来到天台。"])

    class TwoStageLLM:
        def __init__(self):
            self.calls = []

        def chat_full(self, messages, **kw):
            return board

        def chat(self, messages, **kw):
            last = messages[-1]["content"] if len(messages) > 1 else ""
            self.calls.append(last)
            if "变更句数组" in last:                  # ② 句级锚点
                return [{"sentence": 2, "place": "school_rooftop"}]
            return []                                 # 其他（含 ① 若被调用）

    llm = TwoStageLLM()
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    engine._lexicon_keys = []                    # 本测试只关心 place 路（同 _engine_with）
    scene = engine.send_vn_scene("（开场）", annotate=True)

    assert scene.place == "classroom", scene.place            # ① 层1（0 调用）
    assert scene.paragraphs[1].get("place") == "school_rooftop", scene.paragraphs
    assert "place" not in scene.paragraphs[0], "第 1 句没换场, 不该有锚点"
    assert engine._current_place == "school_rooftop", "延续态该顺延到板内终地点"
    assert len(llm.calls) == 1, f"应只调 1 次（② 句级）——早返回没消掉? {llm.calls}"
    # 视觉键不进叙事历史
    from core.session.renderer import render_bond_scene_text
    text = render_bond_scene_text(scene.to_dict())
    assert "school_rooftop" not in text and "classroom" not in text
    print("    C6: switch 板 = 板级地点(层1 0 调用) + 句级锚点(1 调用), 无早返回")


def test_engine_uses_table_by_default():
    """引擎默认吃表（`_place_keys` = 表的键）; 表坏了才回落旧白名单。"""
    from core.bond.bond_story import BondStoryEngine
    from core.media.place_table import load_table
    llm = EngineLLM()
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    t = load_table()
    assert t.ok and engine._place_keys == t.keys(), "引擎没吃表"
    assert engine._place_table is not None and len(engine._place_table) == len(t)
    assert len(engine._place_keys) > 100, len(engine._place_keys)
    assert "classroom" in engine._place_keys
    print(f"    引擎: place 词表 = 表的 {len(engine._place_keys)} 条键")
