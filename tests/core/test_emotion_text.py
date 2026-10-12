"""emo 标注原语 — 按**记录**情绪标注（core/bond/emo_text.py + 引擎链记账）。

口径（记录流 v2 P0-7b 定稿, 2026-09-11 修正）: 标注单元 = **记录**（一条 = 一个
显示/判定单元, 记录内多句也只给一个键）; 分组 = 一板一组 = **一次调用**;
板间 carry 链（情境 = 上一板记录原文 + 末条情绪）; 非当前角色的台词不送标注。

覆盖（docs/DESIGN_STREAM_CONTRACT.md 附录 A §6/§9 验收口径）:
    pick_demo_keys         示范键恒 ∈ 词表（含单键词表兜底）
    annotate_items         组装（板号/人设卡/情境/条数双写/全注释词表）;
                           长度不符 → 重试消息带"期望 N, 实得 M";
                           词表外单项只丢该项（板内延续）;
                           预算耗尽/调用异常 → 确定性延续,**绝不整批 None**
    引擎集成               一板一组一次调用; 首板 = 本章 seed 锚;
                           非首板 = 上一板记录原文 + 末条情绪 carry（跨板链记账）;
                           其他角色（NPC）记录不送标注（继承上一条已生效键）;
                           填充率 100%（含延续显式写回）
"""

import sys
from pathlib import Path


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


def _group(*scripts):
    from core.bond.emo_text import annotate_items

    llm = _ScriptLLM(*scripts)
    labels, info = annotate_items(
        llm, ["她站在窗边，看着远处。", "老师来了！"],   # n=2 条记录
        ["nomal", "smile", "embarrassed"],
        "  nomal: 平静\n  smile: 微笑",
        "角色: 遥香\n性格要点: 胆小", "遥香",
        "（上一板记录原文）\n她抬起头。\n（末条情绪: nomal）",
        group_no=3, prev="nomal", max_tokens=256)
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


def test_items_unquoted_keys_accepted():
    """裸键输出（省引号）不再判死——逐项词表校验后正常入链。"""
    from core.bond.emo_text import annotate_items

    class _BareLLM:
        def chat(self, messages, **kw):
            return "[smile, nomal]"            # 无引号裸键

    labels, info = annotate_items(
        _BareLLM(), ["a。", "b！"], ["nomal", "smile"], "", "", "", "",
        group_no=1, prev="nomal", max_tokens=256)
    assert labels == ["smile", "nomal"]
    assert info == {"attempts": 1, "retry": 0, "fallback": 0}
    print("    items: 裸键数组一次通过（无重试/无兜底）")



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
# annotate_items: 组装 / 校验 / 重试 / 板内延续
# ----------------------------------------------------------------------------

def test_items_annotate_normal():
    llm, labels, info = _group(["smile", "nomal"])
    assert labels == ["smile", "nomal"]          # 每条必填, 长度恰 n
    assert info == {"attempts": 1, "retry": 0, "fallback": 0}
    sys = _system(llm)
    assert "第 3 板" in sys and "遥香" in sys and "胆小" in sys      # 板号/人设卡
    assert "她抬起头" in sys and "末条情绪: nomal" in sys            # 情境块
    assert "共 2 条记录" in sys and "一行一项" in sys                # 条数/逐行显式
    assert "不是句子数" in sys                                      # 口径: 记录 ≠ 句子
    assert "1: 她站在窗边，看着远处。" in sys and "2: 老师来了！" in sys
    assert "smile: 微笑" in sys or "smile" in sys                    # 全注释词表
    assert '"labels"' in sys                                        # 编号映射契约
    assert "恰 2 项" in llm.calls[-1][-1]["content"]                 # 底部双写
    print("    items: 正常标注（模板全占位符替换, 编号映射, 1 次调用零兜底）")


def test_items_length_mismatch_retry_message():
    llm, labels, info = _group(["smile"], ["embarrassed", "nomal"])
    assert len(llm.calls) == 2                  # 长度不符 → 重试一次
    assert labels == ["embarrassed", "nomal"]
    assert info == {"attempts": 2, "retry": 1, "fallback": 0}
    # 重试消息带"期望 N, 实得 M"（§10 验收）
    assert "期望 2" in _system(llm, 1) and "实得 1 项" in _system(llm, 1)
    print("    items: 长度不符 → 重试一次, 消息带「期望 2, 实得 1 项」")


def test_items_exhausted_chain_fallback_never_none():
    llm, labels, info = _group("不是数组", "[also bad]", "仍坏")
    assert len(llm.calls) == 3                  # 预算 = 首发 + 2 次重试
    # 耗尽 → 板内确定性延续（prev carry）——绝不整批 None / 不无限调用
    assert labels == ["nomal", "nomal"]
    assert info["fallback"] == 2 and info["retry"] == 2 and info["attempts"] == 3
    # 词表外单项 → 只丢该项, 其余保留（板内延续: 前一条键）
    llm2, labels2, info2 = _group(["smile", "zzz_not_in_lexicon"])
    assert labels2 == ["smile", "smile"] and info2["fallback"] == 1
    print("    items: 预算耗尽/非法项 → 板内延续兜底（无整批 None, 无无限调用）")


def test_items_llm_exception_then_success():
    from core.bond.emo_text import annotate_items

    class BoomLLM:
        def __init__(self):
            self.n = 0
        def chat(self, messages, **kw):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("api down")
            return ["nomal", "smile"]

    llm = BoomLLM()
    labels, info = annotate_items(
        llm, ["a。", "b！"], ["nomal", "smile"], "", "", "", "",
        group_no=1, prev="nomal", max_tokens=256)
    assert labels == ["nomal", "smile"] and info["attempts"] == 2
    print("    items: 调用异常 → 自动重试, 成功即返回")


# ----------------------------------------------------------------------------
# 引擎集成: 一板一组 + seed 锚 + 跨板 carry 链记账 + 非当前角色不送标注
# ----------------------------------------------------------------------------

# 记录流 v2（P0-7b）: 一记录 = 一显示/判定单元（= 旧契约的一个自然段）
SCENE1 = scene(lines=["她站在窗边看着天空。风把窗帘吹了起来。",
                      "「老师，你来啦。」"])
SCENE2 = scene(lines=["（她低头笑了笑。）"])
SCENE2_BRANCH = scene(lines=["（她低头笑了笑。）"], sensei=["留下来"],
                      after=["她轻轻点头。"])
# 同场客串（NPC）: 其他角色的台词没有差分（只有 default 一张）→ 不送标注
SCENE_NPC = scene(lines=[("igusa_haruka", "「老师，您看，它发芽了。」"),
                         ("asagi_mutsuki", "「哎呀，遥香又在逞强了。」"),
                         ("igusa_haruka", "「才、才没有……」")])


class _EngineLLM:
    """引擎桩: 场景脚本与按板数组按序弹出（顺序 = 生成 → 板1 → 板2 → …）。"""

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


def test_engine_board_chain_and_seed():
    """记录流 v2 标注单元 = **记录**（一板一组）: 板内一次调用、跨板链记账;
    板 1 情境 = seed 锚, 下一板 = 上一板记录原文 + 末条 carry。"""
    vn, llm = _engine(SCENE1, ["smile", "nomal"])
    scene = vn.send_vn_scene("今天放学后的教室。")      # 叙事 seed → 捕获为锚
    assert [p["emotion"] for p in scene.paragraphs] == ["smile", "nomal"], \
        scene.paragraphs
    assert vn._group_seq == 1                           # 一板一组 = 1 次标注
    assert len(llm.calls) == 2                          # 生成 + 1 组标注
    # 板 1 情境: seed 锚（无上一板, 禁后文）
    sys1 = llm.calls[1][0]["content"]
    assert "第 1 板" in sys1 and "本章开场那一句——剧情锚点" in sys1 \
        and "今天放学后的教室。" in sys1, sys1[:300]
    assert vn._carry_emo == "nomal"                     # 链尾 = 板内末条
    # 跨板: 下一板情境 = 上一板（原文 + carry）
    vn2, llm2 = _engine(SCENE1, ["smile", "nomal"], SCENE2, ["embarrassed"])
    vn2.send_vn_scene("今天放学后的教室。")
    vn2.send_vn_scene("（继续）")
    sys2 = llm2.calls[3][0]["content"]
    assert "第 2 板" in sys2 and "「老师，你来啦。」" in sys2 \
        and "上一板末条已生效情绪: nomal" in sys2, sys2[:400]
    print("    engine: 板内一次标注 + seed 锚 + 跨板 carry 链（记录 = 单元）")


def test_engine_non_main_speaker_not_annotated():
    """其他角色（客串/NPC）的台词**不送标注**——只有当前角色记录 + 旁白进 items;
    NPC 由引擎确定性继承"上一条已生效键"（无差分可切, 零 LLM 决策）。

    注: 批式 parse 现在把**未知说话人归一给主角**（决策 #21 单人模式兜底；见本用例
    第二段）, 流式路径保留原值——所以这里直接构造带 speaker 的段落, 锁 emo 层规则;
    多角色/NPC table 落地时这条规则即生效（`contract.is_main_speaker` 判据同源）。
    """
    from core.bond.bond_story import BondScene

    vn, llm = _engine(["smile", "embarrassed", "nomal"])
    scene = BondScene(paragraphs=[
        {"text": "「老师，您看，它发芽了。」", "speaker": "igusa_haruka"},
        {"text": "「哎呀，遥香又在逞强了。」", "speaker": "asagi_mutsuki"},
        {"text": "「才、才没有……」", "speaker": "igusa_haruka"},
        {"text": "（她低下头，指尖绞在一起。）"},              # 旁白 = 无 speaker
    ])
    assert vn.fill_scene_emotions_text(scene) is True
    labels = [p["emotion"] for p in scene.paragraphs]
    # 主角两句 = 模型给的键; NPC 行继承上一条已生效键（立绘不变）
    assert labels == ["smile", "smile", "embarrassed", "nomal"], labels
    sys1 = llm.calls[0][0]["content"]
    assert "共 3 条记录" in sys1                             # 只送 3 条（NPC 不在内）
    assert "又在逞强" not in sys1                            # NPC 文本不出现
    assert "1: 「老师，您看，它发芽了。」" in sys1 \
        and "2: 「才、才没有……」" in sys1 \
        and "3: （她低下头，指尖绞在一起。）" in sys1
    assert len(llm.calls) == 1                               # 标注只发生一次
    assert vn._group_seq == 1 and vn._carry_emo == "nomal"

    # 批式 parse 路径: 未知说话人 → 归一给主角（决策 #21）→ 仍进标注, 不误判成 NPC
    vn2, llm2 = _engine(SCENE_NPC, ["smile", "smile", "nomal"])
    scene2 = vn2.send_vn_scene("（开场）")
    assert [p["speaker"] for p in scene2.paragraphs] == ["igusa_haruka"] * 3
    assert [p["emotion"] for p in scene2.paragraphs] == ["smile", "smile", "nomal"]
    assert "共 3 条记录" in llm2.calls[1][0]["content"]
    print("    engine: NPC 台词不送标注（继承上一条已生效键, 立绘不变）")


def test_engine_reaction_board_annotated_with_chain():
    """记录流 v2: 角色反应在**下一板**（槽挂板尾）——它独立标注, 链随主线推进。"""
    vn, llm = _engine(SCENE2_BRANCH, ["smile"], ["expectant"])
    scene = vn.send_vn_scene("（开场）")
    assert scene.paragraphs[0]["emotion"] == "smile"
    assert scene.choices == ["留下来"]                    # 群 = 交互槽（run=1 也弹）
    assert vn._group_seq == 1 and vn._carry_emo == "smile"
    vn.record_picked("留下来")
    nxt = vn.send_vn_scene("（继续）")                     # 待发板（0 LLM）
    assert [p["text"] for p in nxt.paragraphs] == ["她轻轻点头。"]
    assert nxt.paragraphs[0]["emotion"] == "expectant"
    assert vn._group_seq == 2 and vn._carry_emo == "expectant"   # 链前进到反应板
    # 反应板情境 = 上一板记录原文 + carry
    sys_next = llm.calls[2][0]["content"]
    assert "第 2 板" in sys_next and "上一板记录原文" in sys_next, sys_next[:300]
    print("    engine: 反应板独立标注（槽挂板尾, 链随主线推进）")


if __name__ == "__main__":
    for fn in sorted(k for k, v in globals().items() if k.startswith("test_")):
        fn()
