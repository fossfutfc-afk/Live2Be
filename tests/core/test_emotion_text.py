# -*- coding: utf-8 -*-
"""SceneStream P1 — 按 text(自然段) 情绪标注（core/bond/emo_text.py + 引擎链记账）。

覆盖（docs/DESIGN_SCENE_STREAM §4/§8/§10 验收口径）:
    pick_demo_keys         示范键恒 ∈ 词表（含单键词表兜底）
    annotate_paragraph     组装（段号/人设卡/情境/总数双写/全注释词表）;
                           长度不符 → 重试消息带"期望 N, 实得 M";
                           词表外单项只丢该项（段内延续）;
                           预算耗尽/调用异常 → 确定性延续,**绝不整批 None**
    引擎集成               按自然段分组逐段调用; 段 1 = 本章 seed 锚;
                           段 >1 = 上一段原文 + 末句情绪 carry（跨板链记账）;
                           填充率 100%（含延续显式写回）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tests.vn_fixtures import scene  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


class _ScriptLLM:
    """emo_text 原语测试桩: 按顺序返回预设响应, 记录 messages 副本。"""

    def __init__(self, *scripts):
        self._s = list(scripts)
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        if not self._s:
            raise RuntimeError("脚本耗尽")
        return self._s.pop(0)


def _para(*scripts):
    from core.bond.emo_text import annotate_paragraph

    llm = _ScriptLLM(*scripts)
    labels, info = annotate_paragraph(
        llm, ["她站在窗边，看着远处。", "老师来了！"],   # n=2
        ["nomal", "smile", "embarrassed"],
        "  nomal: 平静\n  smile: 微笑",
        "角色: 遥香\n性格要点: 胆小", "遥香",
        "（上一段原文）\n她抬起头。\n（末句情绪: nomal）",
        para_no=3, prev="nomal", max_tokens=256)
    return llm, labels, info


def _system(llm: _ScriptLLM, idx: int = -1) -> str:
    return llm.calls[idx][0]["content"]


# ----------------------------------------------------------------------------
# _extract_key_array: 严格 JSON 优先, 容忍裸键数组（真 API 观测补强）
# ----------------------------------------------------------------------------

def test_extract_key_array_lenient():
    from core.bond.emo_text import _extract_key_array

    # 编号映射形态（现网契约）: dict 直给 / JSON 字符串 / 乱序键按句号排序
    assert _extract_key_array({"labels": {"1": "smile", "2": "nomal"}}) == \
        ["smile", "nomal"]
    assert _extract_key_array('{"labels": {"1": "smile", "2": "nomal"}}') == \
        ["smile", "nomal"]
    assert _extract_key_array({"labels": {"2": "nomal", "1": "smile"}}) == \
        ["smile", "nomal"]
    assert _extract_key_array({"emotion": {"1": "smile"}}) == ["smile"]
    # 旧形态兼容: 数组 / 对象数组 / 裸键 / 字符串数组
    assert _extract_key_array('["smile", "nomal"]') == ["smile", "nomal"]
    assert _extract_key_array(["smile"]) == ["smile"]
    assert _extract_key_array({"labels": ["smile", "nomal"]}) == \
        ["smile", "nomal"]
    assert _extract_key_array("[nomal, embarrassed]") == ["nomal", "embarrassed"]
    assert _extract_key_array("输出如下:\n[nomal, smile]\n谢谢") == \
        ["nomal", "smile"]
    # 无法识别（引号混杂/中文/空/非编号对象）→ None（走重试路径）
    assert _extract_key_array("[nomal, \"smile\"]") is None
    assert _extract_key_array("[她低头, smile]") is None
    assert _extract_key_array("") is None
    assert _extract_key_array("抱歉，我无法完成") is None
    assert _extract_key_array({"labels": {"a": "smile"}}) is None
    print("    extract: 编号映射/数组/裸键全形态, 无法识别 → None")


def test_para_unquoted_keys_accepted():
    """裸键输出（省引号）不再判死——逐项词表校验后正常入链。"""
    from core.bond.emo_text import annotate_paragraph

    class _BareLLM:
        def chat(self, messages, **kw):
            return "[smile, nomal]"            # 无引号裸键

    labels, info = annotate_paragraph(
        _BareLLM(), ["a。", "b！"], ["nomal", "smile"], "", "", "", "",
        para_no=1, prev="nomal", max_tokens=256)
    assert labels == ["smile", "nomal"]
    assert info == {"attempts": 1, "retry": 0, "fallback": 0}
    print("    para: 裸键数组一次通过（无重试/无兜底）")



def test_pick_demo_keys_in_lexicon():
    from core.bond.emo_text import pick_demo_keys

    # 常规词表 → 3 个不同键, 全部在词表内（叙述键优先 nomal）
    keys = ["nomal", "smile", "embarrassed", "surprised"]
    n, a, b = pick_demo_keys(keys)
    assert n == "nomal" and {n, a, b} <= set(keys) and len({n, a, b}) == 3
    # 无 nomal 词表 → 用词表前两个合法键兜底（仍全 ∈ 词表）
    keys2 = ["expectant", "sad"]
    n2, a2, b2 = pick_demo_keys(keys2)
    assert n2 == "expectant" and {n2, a2, b2} == {"expectant", "sad"}
    # 单键词表 → 同键兜底（格式示范仍成立）
    assert pick_demo_keys(["smile"]) == ("smile", "smile", "smile")
    print("    demo keys: 示范键恒在词表内（常规/无 nomal/单键兜底）")


# ----------------------------------------------------------------------------
# annotate_paragraph: 组装 / 校验 / 重试 / 段内延续
# ----------------------------------------------------------------------------

def test_para_annotate_normal():
    llm, labels, info = _para(["smile", "nomal"])
    assert labels == ["smile", "nomal"]          # 逐句必填, 长度恰 n
    assert info == {"attempts": 1, "retry": 0, "fallback": 0}
    sys = _system(llm)
    assert "第 3 段" in sys and "遥香" in sys and "胆小" in sys      # 段号/人设卡
    assert "她抬起头" in sys and "末句情绪: nomal" in sys            # 情境块
    assert "共 2 句" in sys and "一行一项" in sys                    # 总数/逐行显式
    assert "1: 她站在窗边，看着远处。" in sys and "2: 老师来了！" in sys
    assert "smile: 微笑" in sys or "smile" in sys                    # 全注释词表
    assert '"labels"' in sys                                        # 编号映射契约
    assert "恰 2 项" in llm.calls[-1][-1]["content"]                 # 底部双写
    print("    para: 正常标注（模板全占位符替换, 编号映射, 1 次调用零兜底）")


def test_para_length_mismatch_retry_message():
    llm, labels, info = _para(["smile"], ["embarrassed", "nomal"])
    assert len(llm.calls) == 2                  # 长度不符 → 重试一次
    assert labels == ["embarrassed", "nomal"]
    assert info == {"attempts": 2, "retry": 1, "fallback": 0}
    # 重试消息带"期望 N, 实得 M"（DESIGN_SCENE_STREAM §10 验收）
    assert "期望 2" in _system(llm, 1) and "实得 1 项" in _system(llm, 1)
    print("    para: 长度不符 → 重试一次, 消息带「期望 2, 实得 1 项」")


def test_para_exhausted_chain_fallback_never_none():
    llm, labels, info = _para("不是数组", "[also bad]", "仍坏")
    assert len(llm.calls) == 3                  # 预算 = 首发 + 2 次重试
    # 耗尽 → 段内确定性延续（prev carry）——绝不整批 None / 不无限调用
    assert labels == ["nomal", "nomal"]
    assert info["fallback"] == 2 and info["retry"] == 2 and info["attempts"] == 3
    # 词表外单项 → 只丢该项, 其余保留（段内延续: 前一句键）
    llm2, labels2, info2 = _para(["smile", "zzz_not_in_lexicon"])
    assert labels2 == ["smile", "smile"] and info2["fallback"] == 1
    print("    para: 预算耗尽/非法项 → 段内延续兜底（无整批 None, 无无限调用）")


def test_para_llm_exception_then_success():
    from core.bond.emo_text import annotate_paragraph

    class BoomLLM:
        def __init__(self):
            self.n = 0
        def chat(self, messages, **kw):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("api down")
            return ["nomal", "smile"]

    llm = BoomLLM()
    labels, info = annotate_paragraph(
        llm, ["a。", "b！"], ["nomal", "smile"], "", "", "", "",
        para_no=1, prev="nomal", max_tokens=256)
    assert labels == ["nomal", "smile"] and info["attempts"] == 2
    print("    para: 调用异常 → 自动重试, 成功即返回")


# ----------------------------------------------------------------------------
# 引擎集成: 按自然段分组 + seed 锚 + 跨板 carry 链记账
# ----------------------------------------------------------------------------

# 记录流 v2（P0-7b）: 一记录 = 一显示/判定单元（= 旧契约的一个自然段）
SCENE1 = scene(lines=["她站在窗边看着天空。风把窗帘吹了起来。",
                      "「老师，你来啦。」"])
SCENE2 = scene(lines=["（她低头笑了笑。）"])
SCENE2_BRANCH = scene(lines=["（她低头笑了笑。）"], sensei=["留下来"],
                      after=["她轻轻点头。"])


class _EngineLLM:
    """引擎桩: 场景脚本与按段数组按序弹出（顺序 = 生成 → 段1 → 段2 → …）。"""

    def __init__(self, *scripts):
        self._s = list(scripts)
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kw):
        self.calls.append([dict(m) for m in messages])
        if not self._s:
            raise RuntimeError("脚本耗尽")
        return self._s.pop(0)


def _engine(*scripts):
    from core.bond.bond_story import BondStoryEngine

    llm = _EngineLLM(*scripts)
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session("igusa_haruka")
    vn._place_keys = []                         # 本测试只关心 emo 路（place 关断）
    return vn, llm


def test_engine_segmented_chain_and_seed():
    """记录流 v2 标注单元 = **记录**（一板一组）: 板内一次调用、跨板链记账;
    板 1 情境 = seed 锚, 下一板 = 上一板原文 + 末句 carry。"""
    vn, llm = _engine(SCENE1, ["smile", "nomal"])
    scene = vn.send_vn_scene("今天放学后的教室。")      # 叙事 seed → 捕获为锚
    assert [p["emotion"] for p in scene.paragraphs] == ["smile", "nomal"], \
        scene.paragraphs
    assert vn._para_seq == 1                            # 一板一组 = 1 次标注
    assert len(llm.calls) == 2                          # 生成 + 1 组标注
    # 板 1 情境: seed 锚（无上一板, 禁后文）
    sys1 = llm.calls[1][0]["content"]
    assert "第 1 段" in sys1 and "本章开场那一句——剧情锚点" in sys1 \
        and "今天放学后的教室。" in sys1, sys1[:300]
    assert vn._carry_emo == "nomal"                     # 链尾 = 板内末条
    # 跨板: 下一板情境 = 上一板（原文 + carry）
    vn2, llm2 = _engine(SCENE1, ["smile", "nomal"], SCENE2, ["embarrassed"])
    vn2.send_vn_scene("今天放学后的教室。")
    vn2.send_vn_scene("（继续）")
    sys2 = llm2.calls[3][0]["content"]
    assert "第 2 段" in sys2 and "「老师，你来啦。」" in sys2 \
        and "末句已生效情绪: nomal" in sys2, sys2[:400]
    print("    engine: 板内一次标注 + seed 锚 + 跨板 carry 链（记录 = 单元）")


def test_engine_reaction_board_annotated_with_chain():
    """记录流 v2: 角色反应在**下一板**（槽挂板尾）——它独立标注, 链随主线推进。"""
    vn, llm = _engine(SCENE2_BRANCH, ["smile"], ["expectant"])
    scene = vn.send_vn_scene("（开场）")
    assert scene.paragraphs[0]["emotion"] == "smile"
    assert scene.choices == ["留下来"]                    # 群 = 交互槽（run=1 也弹）
    assert vn._para_seq == 1 and vn._carry_emo == "smile"
    vn.record_picked("留下来")
    nxt = vn.send_vn_scene("（继续）")                     # 待发板（0 LLM）
    assert [p["text"] for p in nxt.paragraphs] == ["她轻轻点头。"]
    assert nxt.paragraphs[0]["emotion"] == "expectant"
    assert vn._para_seq == 2 and vn._carry_emo == "expectant"   # 链前进到反应板
    # 反应板情境 = 上一板原文 + carry
    sys_next = llm.calls[2][0]["content"]
    assert "第 2 段" in sys_next and "上一段原文" in sys_next, sys_next[:300]
    print("    engine: 反应板独立标注（槽挂板尾, 链随主线推进）")


if __name__ == "__main__":
    for fn in sorted(k for k, v in globals().items() if k.startswith("test_")):
        fn()
