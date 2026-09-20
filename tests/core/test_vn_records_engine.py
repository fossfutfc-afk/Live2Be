# -*- coding: utf-8 -*-
"""VN 记录流引擎接线单测（P0-4b）—— 块解析 → 板派生 → 群/槽 → 待发板 → 历史隔离。

覆盖设计文档 §6（板 = 引擎派生单位: 换场/槽前必切）、§2（文法）、决策 #21（别名归一）:
    记录流一场      : 字符串输出 → 板（switch/群/art 不进显示, end 行进 is_end）
    待发板          : 一块多群 → 首板本次发, 尾板 **0 LLM** 领出
    别名归一 + 辅助转义: 显示名/未知说话人 → 主角 id; 未转义引号救回
    硬违规/空块      : feedback 回灌重试; 耗尽抛 SceneLoopError
    历史隔离        : switch 文本与未选候选**不进 LLM 上下文**（A1 语义）

不碰 API: ScriptedLLM（场景轮返回记录流字符串; annotate=False 免标注调用）。
运行: python -m pytest tests/core/test_vn_records_engine.py
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

#: 一块两群（run=2 + run=1）+ 换场 + art 预告 + 收尾
TWO_GROUP_BLOCK = "\n".join([
    '{"stage": "switch", "text": "深夜的杂草屋"}',
    '{"character": "igusa_haruka", "text": "……老师。"}',
    '{"character": "narrator", "text": "（她把灯往我这边挪了挪。）"}',
    '{"character": "sensei", "text": "我来了。"}',
    '{"character": "sensei", "text": "路上买了点东西。"}',
    '{"character": "igusa_haruka", "text": "「不、不用这样的……」"}',
    '{"character": "sensei", "text": "先坐下。"}',
    '{"character": "igusa_haruka", "text": "「……好。」"}',
    '{"stage": "end", "text": "（夜风停了。）"}',
])


class ScriptedLLM:
    """场景轮按脚本返回**记录流字符串**；标注调用（emotion/place/换场翻译）按关键字
    自动应答, 不消耗脚本。每个脚本用完即提示（防静默多发调用）。"""

    def __init__(self, *scripts, place_reply: str = ""):
        self._scripts = list(scripts)
        self.snapshots = []
        self.place_reply = place_reply

    def chat_full(self, messages, **kw):
        return self.chat(messages, **kw)

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        last = messages[-1]["content"] if messages else ""
        head = messages[0]["content"] if messages else ""
        if "情绪标签" in last:                       # emotion 标注 → 全 nomal
            import re as _re
            m = _re.search(r"恰 (\d+) 项", last)
            n = int(m.group(1)) if m else 1
            return ["nomal"] * n
        if "地点 id JSON" in last:                       # switch → 背景键（P0-7）
            return {"place": self.place_reply}
        if "变更句数组" in last:                          # 旧 place 标注 → 无变更
            return []
        if "选中的文件名" in last:                # 选图（第二遍）→ 保持默认图
            return {"image": ""}
        if not self._scripts:
            raise AssertionError("ScriptedLLM 脚本耗尽——引擎多发了一次 LLM 调用")
        return self._scripts.pop(0)


def _engine(llm) -> BondStoryEngine:
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    return engine


# ---------------------------------------------------------------------------
# 板派生（换场/槽前必切）
# ---------------------------------------------------------------------------

def test_record_turn_splits_boards_at_switch_and_slots():
    """一块多群 + 换场 → 切成多板: 首板 = switch 后的正文 + 第一群（choices）。"""
    llm = ScriptedLLM(TWO_GROUP_BLOCK)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    # 首板: 群（run=2）成为 choices; 正文不含 switch/群内候选
    assert scene.choices == ["我来了。", "路上买了点东西。"]
    assert [p["text"] for p in scene.paragraphs] == [
        "……老师。", "（她把灯往我这边挪了挪。）"]
    assert scene.place_hint == "深夜的杂草屋"
    assert not scene.is_end
    # 记录流真源: 本板记录里 switch 仍在（落库/回放不丢信号）
    assert scene.records[0] == {"stage": "switch", "text": "深夜的杂草屋"}
    assert len(engine.history) == 2                       # user + assistant
    print("    engine: 换场/槽前必切板 + 群 → choices")


def test_pending_board_costs_zero_llm():
    """尾板已在手 → 后续调用 **0 LLM** 直接发（槽在板尾、反应在下一板）。"""
    llm = ScriptedLLM(TWO_GROUP_BLOCK)
    engine = _engine(llm)
    first = engine.send_vn_scene("（开场）", annotate=False)
    second = engine.send_vn_scene("（继续）", annotate=False)
    third = engine.send_vn_scene("（继续）", annotate=False)

    assert len(llm.snapshots) == 1                        # 后两次都没碰 LLM
    assert first.choices == ["我来了。", "路上买了点东西。"]
    assert second.choices == ["先坐下。"]                  # 第二个群（run=1 也弹）
    assert [p["text"] for p in second.paragraphs] == ["「不、不用这样的……」"]
    assert third.choices == [] and third.is_end is True    # 末板: 收尾（end 行进 is_end）
    assert [p["text"] for p in third.paragraphs] == ["「……好。」", "（夜风停了。）"]
    assert engine._trace[0]["action"] == "record_stream/pending"
    # 历史: 三板各 user+assistant
    assert len(engine.history) == 6
    print("    engine: 待发板 0 LLM（读屏期间预生成下一板的最朴素形态）")


def test_history_excludes_slot_candidates_keeps_switch_text():
    """历史隔离: **槽内候选不进 LLM 上下文**（A1 语义）; switch 回显 writer 自己的地点话。"""
    llm = ScriptedLLM(TWO_GROUP_BLOCK)
    engine = _engine(llm)
    for _ in range(3):
        engine.send_vn_scene("（继续）", annotate=False)
    joined = "\n".join(m["content"] for m in engine.history)
    assert "我来了。" not in joined and "先坐下。" not in joined   # 未选候选不出现
    assert "老师：" not in joined                            # 槽候选不当台词灌历史
    assert "深夜的杂草屋" in joined                           # §4: switch 回显自己写的地点话
    assert "「……好。」" in joined                             # 正文照常入历史
    print("    engine: 历史不含槽候选（switch 按 §4 回显）")


# ---------------------------------------------------------------------------
# 别名归一 + 辅助转义（决策 #21 / P0-2 修复）
# ---------------------------------------------------------------------------

def test_alias_normalization_and_rescape_in_engine():
    """显示名/未知说话人 → 主角 id（NOTE）; 未转义引号在引擎路径上被救回。"""
    block = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "伊草 遥香", "text": "「老师……」"}',
        '{"character": "遥香", "text": "我想要的不是 "别担心" 这种话。"}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    assert [r["character"] for r in scene.records if "character" in r] == [CHARACTER] * 2
    assert scene.paragraphs[1]["text"] == '我想要的不是 "别担心" 这种话。'
    assert any("别名归一" in n for n in scene.notes)
    assert any("辅助转义" in n for n in scene.notes)
    print("    engine: 别名归一 + 辅助转义（真机路径生效）")


# ---------------------------------------------------------------------------
# 硬违规 / 空块 → feedback 重试
# ---------------------------------------------------------------------------

def test_hard_violation_retries_with_feedback():
    """art 不在本轮首条（形状硬违规）→ 打回重发, 第二次守约则收下。"""
    bad = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "……"}',
        '{"stage": "art", "text": "画面意向"}',
    ])
    llm = ScriptedLLM(bad, TWO_GROUP_BLOCK)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    assert len(llm.snapshots) == 2
    retry_messages = "\n".join(m["content"] for m in llm.snapshots[1])
    assert "记录流不合规" in retry_messages and "art" in retry_messages
    assert scene.choices == ["我来了。", "路上买了点东西。"]
    assert engine.trace[0]["parse_valid"] is False and engine.trace[1]["parse_valid"] is True
    print("    engine: 硬违规 → feedback 回灌重试")


def test_empty_block_exhausts_retries():
    """一直给不出合法记录 → 重试耗尽抛 SceneLoopError（宁缺勿错: 循环必须终结）。"""
    llm = ScriptedLLM("这不是记录流", "还是不是", "仍然不是")
    engine = _engine(llm)
    with pytest.raises(SceneLoopError):
        engine.send_vn_scene("（开场）", annotate=False)
    assert len(llm.snapshots) == 3
    print("    engine: 空块重试耗尽 → SceneLoopError")


def test_second_memorial_in_chapter_is_silently_rejected():
    """★ 章内**第二次**纪念 → 静默拒绝（2026-09-20, 用户要求）。

    背景: 规则书写着"章内至多一次（重复会被拒绝）", 但 `_memorial_used` 此前
    **只写不读** ⇒ **同块内**由契约校验挡住, **跨块**的第二次一路放行: 又开一张图、
    又写 `memorial_enter`、又置 `in_memorial`（回忆册"一章多图"的来源）。

    "静默"= 不给模型反馈/不重试、只打一行 INFO; **文字照常显示**
    （`stage=memorial` 本来就以旁白形态上屏 ⇒ 降级成 narrator 后观感不变）。
    """
    first = "\n".join([
        '{"stage": "switch", "text": "黄昏的坡道"}',
        '{"character": "igusa_haruka", "text": "老师，你看。"}',
        '{"stage": "memorial", "text": "（她第一次直视我的眼睛。）"}',
    ])
    second = "\n".join([
        f'{{"character": "igusa_haruka", "text": "（第二段日常。）"}}',
        '{"stage": "memorial", "text": "（她又抬了一次头——这次不该再开画。）"}',
        '{"character": "igusa_haruka", "text": "……"}',
    ])
    shots: list[str] = []
    engine = _engine(ScriptedLLM(first, second))
    s1 = engine.send_vn_scene("（开场）", annotate=False, on_memorial_prompt=shots.append)
    assert s1.memorial is True and len(shots) == 1
    assert engine._memorial_used is True

    s2 = engine.send_vn_scene("（继续）", annotate=False, on_memorial_prompt=shots.append)
    assert len(shots) == 1, f"第二次纪念不该再开画: {shots}"
    assert s2.memorial is False, "第二次纪念该被静默降级"
    # 文字照常显示: 降级成**标准旁白记录**（`{"character": "narrator"}` —— writer
    # 写旁白本来就是这么写的; 前端把它渲染成没有名字牌的一段, 与 `stage:memorial`
    # 的呈现一致——`stage` 记录也不带 speaker, 两种都不上名字行）
    texts = [p["text"] for p in s2.paragraphs]
    assert "（她又抬了一次头——这次不该再开画。）" in texts, texts
    demoted = [p for p in s2.paragraphs if p["text"].startswith("（她又抬")]
    assert demoted and demoted[0].get("speaker") == "narrator", s2.paragraphs
    # 真源里也已经是 narrator 记录（回放/回忆册据此看不到第二个纪念窗口）
    recs = [r for r in s2.records if r.get("text", "").startswith("（她又抬")]
    assert recs and recs[0].get("character") == "narrator", s2.records
    print("    章内第二次纪念: 不生图 / 不置位 / 记录降级为旁白（文字照常显示）")


def test_memorial_fires_image_hook_with_art_intent():
    """纪念生图钩子（v2, 2026-09-12）: `stage:memorial` 一出现就回调, prompt =
    块级 `art` 画面意向（rules 要求写清"她此刻在画面里是什么样"）。

    v1 的 `MemorialProbe`（嗅 `"action":"memorial_enter"` 的 prompt 字段）在记录流下
    永不触发 → 已退役; 这里锁住替代行为的两条路径（批式 / 流式）。
    """
    block = "\n".join([
        '{"stage": "art", "text": "她在开满杂草的坡道上回头，夕阳打在脸上"}',
        '{"stage": "switch", "text": "黄昏的坡道"}',
        '{"character": "igusa_haruka", "text": "老师，你看。"}',
        '{"stage": "memorial", "text": "（她第一次直视我的眼睛。）"}',
        '{"character": "igusa_haruka", "text": "这句话我想说很久了。"}',
    ])
    got: list[str] = []
    engine = _engine(ScriptedLLM(block))
    scene = engine.send_vn_scene("（开场）", annotate=False,
                                 on_memorial_prompt=got.append)      # 批式（无 on_board）
    assert scene.memorial is True
    assert got == ["她在开满杂草的坡道上回头，夕阳打在脸上"], got   # 意向优先
    # prompt 来源记账（节点 C）: 配对成功 = `art` —— gallery json 的 prompt_source
    # 与 art 配对命中率都读它
    assert engine.memorial_prompt_source == "art"

    # 无 art 声明 → 退化为触发句（同样是"她在做什么"的一句话, 保证画面里有主角）
    block2 = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"stage": "memorial", "text": "（她抬起头，第一次直视我的眼睛。）"}',
        '{"character": "igusa_haruka", "text": "……老师。"}',
    ])
    got2: list[str] = []
    engine2 = _engine(ScriptedLLM(block2))
    scene2 = engine2.send_vn_scene("（开场）", annotate=False,
                                   on_memorial_prompt=got2.append)
    assert got2 == ["（她抬起头，第一次直视我的眼睛。）"], got2
    # 降级路径的记账: prompt 来自 memorial 的**转场句**, 不是画面意向
    assert engine2.memorial_prompt_source == "memorial_text"

    # 没有 memorial 的普通块 → **不开画**（模型写了 art 却没兑现 → 不浪费调用）
    block3 = "\n".join([
        '{"stage": "art", "text": "她在教室里回头"}',
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "老师，早上好。"}',
    ])
    got3: list[str] = []
    engine3 = _engine(ScriptedLLM(block3))
    engine3.send_vn_scene("（开场）", annotate=False, on_memorial_prompt=got3.append)
    assert got3 == [], got3

    # 记录级进入点（2026-09-20 M3）: `memorial_at` = 触发记录在 paragraphs 里的下标
    # ——前端据此**播到那一句**才切黑屏（它之前那几条仍是正常视觉 + 正常背景）。
    assert scene.memorial_at == 1, scene.to_dict()
    assert ([p["text"] for p in scene.paragraphs][scene.memorial_at]
            == "（她第一次直视我的眼睛。）")
    # 触发记录紧跟开场 switch → 下标 0 = 整板即窗口
    assert scene2.memorial_at == 0, scene2.to_dict()
    # 入档案: to_dict → from_dict 往返保留; 旧档没这个字段 → None（前端退回板级）
    assert BondScene.from_dict(scene.to_dict()).memorial_at == scene.memorial_at
    assert BondScene.from_dict(
        {"paragraphs": [{"text": "（她抬起头。）"}], "memorial": True}).memorial_at is None

    # 流式路径: 触发发生在**喂完其余输出之前**（生图与 LLM 剩余输出并行——
    # 真机生图 ~26s, 玩家读纪念正文即缓冲）
    class _StreamLLM:
        def __init__(self):
            self.order: list[str] = []

        def chat_full(self, messages, **kw):
            on_chunk = kw.get("on_chunk")
            if on_chunk:
                on_chunk('{"stage": "art", "text": "她回头, 夕阳打在脸上"}\n')
                on_chunk('{"stage": "switch", "text": "黄昏的坡道"}\n')
                on_chunk('{"character": "igusa_haruka", "text": "老师。"}\n')
                on_chunk('{"stage": "memorial", "text": "（她抬起头。）"}\n')
                self.order.append("memorial-fed")
                on_chunk('{"character": "igusa_haruka", "text": "……谢谢你。"}\n')
                self.order.append("rest-fed")
            return block

        def chat(self, messages, **kw):
            return block

    llm_s = _StreamLLM()
    engine_s = BondStoryEngine(ROOT / "config" / "characters", llm_s)
    engine_s.start_session(CHARACTER)
    got_s: list[tuple[str, list[str]]] = []
    engine_s.send_vn_scene("（开场）", annotate=False,
                           on_board=lambda sc: None,
                           on_memorial_prompt=lambda p: got_s.append(
                               (p, list(llm_s.order))))
    assert got_s, "流式路径应触发纪念生图钩子"
    prompt_s, order_at_fire = got_s[0]
    assert prompt_s == "她回头, 夕阳打在脸上", prompt_s
    assert order_at_fire == [], f"开画应在纪念行解析后立即发生: {order_at_fire}"
    print("    engine: 纪念生图钩子 = art 意向优先 / 触发句兜底 / 无纪念不开画 / "
          "流式即时开画")


def test_art_declaration_is_not_its_own_board():
    """`art` 是块级声明（真机实证: 模型把它放在首条）——不许切出一个纯声明的空板。"""
    block = "\n".join([
        '{"stage": "art", "text": "她在破屋后院里抱着半株杂草抬起头"}',
        '{"stage": "switch", "text": "黄昏的破屋后院"}',
        '{"character": "igusa_haruka", "text": "老师，就是这里。"}',
        '{"stage": "memorial", "text": "（她第一次直视我的眼睛。）"}',
        '{"character": "igusa_haruka", "text": "这些话我想说很久了。"}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    assert scene.paragraphs and scene.place_hint == "黄昏的破屋后院"
    assert scene.memorial is True
    assert scene.art_hint == "她在破屋后院里抱着半株杂草抬起头"     # 声明挂到纪念板
    print("    engine: art 声明不切空板（挂纪念板 art_hint）")


def test_invisible_board_merges_forward_without_losing_records():
    """连发两条 switch（无可显示内容）→ 不产生空板: 地点顺延, 记录并入下一板真源。"""
    block = "\n".join([
        '{"stage": "switch", "text": "走廊"}',
        '{"stage": "switch", "text": "天台"}',
        '{"character": "igusa_haruka", "text": "……风很大。"}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    scene = engine.send_vn_scene("（开场）", annotate=False)

    assert [p["text"] for p in scene.paragraphs] == ["……风很大。"]
    assert scene.place_hint == "走廊"                       # 空板地点顺延（首条 switch）
    assert [r.get("text") for r in scene.records][:4] == ["走廊", "天台", "……风很大。"]
    assert engine._pending_boards == []                     # 只有一板
    print("    engine: 空板记录并入下一板（真源不丢）")


def test_empty_end_board_is_kept_for_blackout_finish():
    """收尾组合③（老师一句 → 空镜 → end 留空）: 空段落板因 is_end 保留, 直接黑屏结束。"""
    block = "\n".join([
        '{"character": "igusa_haruka", "text": "……"}',
        '{"character": "sensei", "text": "你看那边，多漂亮啊"}',
        '{"stage": "switch", "text": "星空"}',
        '{"stage": "end", "text": ""}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    first = engine.send_vn_scene("（开场）", annotate=False)
    assert first.choices == ["你看那边，多漂亮啊"]         # 老师一句 = run=1 的群
    assert first.is_end is False
    second = engine.send_vn_scene("（继续）", annotate=False)   # 0 LLM
    assert second.is_end is True and second.paragraphs == []    # 纯黑屏收尾板
    assert second.place_hint == "星空"
    assert len(llm.snapshots) == 1
    print("    engine: end 留空 = 黑屏收尾板（空段落也保留）")


# ---------------------------------------------------------------------------
# 换场翻译（P0-7）: switch 记录 → 背景键
# ---------------------------------------------------------------------------

def test_stream_delivers_first_board_early():
    """渐进渲染（P2-1 前置）: `on_board` 在**流中途**就拿到首板（不等整块写完）。

    切板需要一行前瞻（槽挂板尾）: 首板在"群之后的第 1 行"到达时闭合——这里显式
    把流分成"够首板闭合的前半"与"其余", 断言交付发生在**喂完前半、还没喂其余**时。
    """
    first = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "一"}',
        '{"character": "sensei", "text": "A"}',
        '{"character": "sensei", "text": "B"}',
        '{"character": "igusa_haruka", "text": "二"}',     # ← 这行让首板闭合
    ])
    rest = "\n".join([
        '{"character": "sensei", "text": "C"}',
        '{"character": "igusa_haruka", "text": "三"}',
        '{"stage": "end", "text": ""}',
    ])
    block = first + "\n" + rest

    class StreamingLLM:
        """流式桩: 先喂前半（首板闭合）, 再喂其余。"""

        def __init__(self):
            self.order: list[str] = []

        def chat_full(self, messages, **kw):
            on_chunk = kw.get("on_chunk")
            if on_chunk:
                on_chunk(first + "\n")
                self.order.append("first-fed")
                on_chunk(rest)
                self.order.append("rest-fed")
            return block

        def chat(self, messages, **kw):
            return block

    llm = StreamingLLM()
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    got: list = []

    def on_board(sc) -> None:
        got.append((sc, list(llm.order)))                # 交付时刻的进度快照

    scene = engine.send_vn_scene("（开场）", annotate=False, on_board=on_board)
    assert got, "流式应至少提前交付一板"
    first_scene, order_at_first = got[0]
    # 交付在**喂入前半的那次 on_chunk 之内**同步发生（连 "first-fed" 都还没记）——
    # 也就是说玩家不必等整块写完
    assert order_at_first == [], f"首板应在喂完其余之前交付: {order_at_first}"
    assert first_scene.choices == ["A", "B"]
    assert [p["text"] for p in first_scene.paragraphs] == ["一"]
    assert first_scene._streamed is True and scene is first_scene   # 返回值即已交付那块
    # 其余板进待发队列（点击 0 LLM）; 流式下不再重复解析/交付
    assert [s.is_end for s, _ in got] == [False, False, True], \
        [[p["text"] for p in s.paragraphs] for s, _ in got]
    assert len(engine._pending_boards) == 2
    assert scene.is_end is False and engine._pending_boards[-1].is_end
    print("    engine: 流式提前交付首板（on_board 在流中途回调）")


def test_stream_first_board_keeps_art_and_notes():
    """流式交付板与批式同语义: art 声明挂首板, 群/候选/位置元数据一致,
    memorial 板（可能在后续板）也照常记账 `_memorial_used`。"""
    block = "\n".join([
        '{"stage": "art", "text": "画面意向"}',
        '{"stage": "switch", "text": "破屋后院"}',
        '{"character": "igusa_haruka", "text": "……"}',
        '{"character": "sensei", "text": "我在。"}',
        '{"stage": "memorial", "text": "（她抬起头。）"}',
        '{"character": "igusa_haruka", "text": "谢谢老师。"}',
    ])

    class StreamingLLM:
        def chat_full(self, messages, **kw):
            on_chunk = kw.get("on_chunk")
            if on_chunk:
                for i in range(0, len(block), 11):
                    on_chunk(block[i:i + 11])
            return block

        def chat(self, messages, **kw):
            return block

    engine = BondStoryEngine(ROOT / "config" / "characters", StreamingLLM())
    engine.start_session(CHARACTER)
    seen: list = []
    scene = engine.send_vn_scene("（开场）", annotate=False, on_board=seen.append)
    assert scene.art_hint == "画面意向" and seen[0].art_hint == "画面意向"
    assert scene.place_hint == "破屋后院" and scene.choices == ["我在。"]
    assert [p["text"] for p in scene.paragraphs] == ["……"]
    # 群收板 → memorial 落在**下一板**（待发）; 章内记账照样生效
    assert scene.memorial is False and engine._memorial_used is True
    assert len(engine._pending_boards) == 1
    tail = engine._pending_boards[0]
    assert tail.memorial is True and [p["text"] for p in tail.paragraphs] == [
        "（她抬起头。）", "谢谢老师。"]
    print("    engine: 流式板与批式同语义（art 挂首板 / 群 / memorial 记账）")


def test_legacy_action_input_is_rejected():
    """P0-7c 定稿: **唯一输入形态 = 记录流**——旧动作 JSON 一律被打回重发。"""
    legacy = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "（旧契约）段落。"}]}}
    llm = ScriptedLLM(legacy, legacy, legacy)
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    with pytest.raises(SceneLoopError):
        engine.send_vn_scene("（开场）", annotate=False)
    assert engine.trace[0]["action"] == "legacy_action_rejected"
    assert any("输出形态无效" in m["content"] for m in llm.snapshots[-1])
    print("    engine: 旧动作一律被拒（记录流是唯一形态）")


def test_switch_record_resolves_to_background_key():
    """`switch` 记录走换场翻译（place 档位）→ scene.place = 词表键; 失败 keep。"""
    from core.bond.place_annotate import _RESOLVE_CACHE
    _RESOLVE_CACHE.clear()                         # 进程内缓存跨用例, 先清
    llm = ScriptedLLM(TWO_GROUP_BLOCK, place_reply="school_rooftop")
    engine = _engine(llm)
    engine._lexicon_keys = []                      # 关掉 emotion 标注, 只测换场
    scene = engine.send_vn_scene("（开场）", annotate=True)
    assert scene.place == "school_rooftop"         # 背景键就位（导演/前端据此切图）
    assert engine._current_place == "school_rooftop"   # 延续态顺延

    # 翻译失败（词表外/空）→ keep: place 为空, 画面保持（换一句地点话, 避开缓存）
    block = TWO_GROUP_BLOCK.replace("深夜的杂草屋", "某个不知名的地方")
    llm2 = ScriptedLLM(block, place_reply="")
    engine2 = _engine(llm2)
    engine2._lexicon_keys = []
    scene2 = engine2.send_vn_scene("（开场）", annotate=True)
    assert scene2.place is None and engine2._current_place == ""
    print("    engine: switch → 背景键（失败 keep）")


def test_soft_violation_overlong_slot_is_chunked():
    """超长 sensei 群（软违规）→ 切成 ≤3 的槽而不是整块重发（内容零损失）。"""
    block = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "「那个……」"}',
        '{"character": "sensei", "text": "一"}',
        '{"character": "sensei", "text": "二"}',
        '{"character": "sensei", "text": "三"}',
        '{"character": "sensei", "text": "四"}',
        '{"character": "sensei", "text": "五"}',
    ])
    llm = ScriptedLLM(block)
    engine = _engine(llm)
    first = engine.send_vn_scene("（开场）", annotate=False)
    assert first.choices == ["一", "二", "三"]              # 首槽截到上限 3
    assert len(llm.snapshots) == 1                          # 没有整块重发
    second = engine.send_vn_scene("（继续）", annotate=False)
    assert second.choices == ["四", "五"]                    # 尾槽接着发
    assert len(llm.snapshots) == 1
    print("    engine: 超长群切槽（软违规不重发）")


def test_soft_issues_become_next_round_note():
    """节点 3（2026-09-21）: 软问题 → **下一轮注记纠偏**（一次性, 注入后自清）。

    改动前: 软问题只进日志/trace, 模型永远看不到 —— 上层注释写着
    "反馈留给上层下一轮注记", 但那条注记从来没实现过; 于是同一类形状错误
    会在每块里重复出现（改坏一处 ⇒ 全章坏）。改动后: 记账到
    `_pending_feedback`, 下一轮拼进 notes（场卡之前）, 然后清空。
    """
    # 第一轮: 有 memorial 但没有 art ⇒ 软问题（交付, 不打回）
    soft_bad = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "……"}',
        '{"stage": "memorial", "text": "（她抬起头。）"}',
        '{"stage": "end", "text": ""}',
    ])
    clean = "\n".join([
        '{"stage": "switch", "text": "教室"}',
        '{"character": "igusa_haruka", "text": "……"}',
        '{"stage": "end", "text": ""}',
    ])
    llm = ScriptedLLM(soft_bad, clean)
    engine = _engine(llm)

    first = engine.send_vn_scene("（开场）", annotate=False)
    assert first.memorial, "软问题不该拦交付"
    assert engine._pending_feedback, "软问题应记账待下一轮纠偏"

    engine.send_vn_scene("（继续）", annotate=False)
    second_notes = "\n".join(m["content"] for m in llm.snapshots[1])
    assert "上一轮输出的**形状**有这些问题" in second_notes, second_notes
    assert "含 memorial 但没有 art" in second_notes, second_notes
    assert engine._pending_feedback == [], "注记注入后应自清（不重复唠叨）"
    print("    engine: 软问题 → 下一轮注记纠偏（一次性）")
