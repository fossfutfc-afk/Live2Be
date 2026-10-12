"""MMT 行流解析（`core/mmt/mmt_lines.py`，⑥-2b 2026-09-25）。

契约: `docs/DESIGN_STREAM_CONTRACT.md` §1/§2；两段式校验 §10.2 B5。

覆盖:
    形状        text 行 / action 行 / 恰好一个判别键 / payload 必须是对象
    丢行记账    坏行只丢自己（别的行照常交付）+ ParseDiag 记账
    增量交付    ⭐ 行即交付单元——chunk 切在行中间也能逐行取走
    数组行拍平   LLM 手痒包了一层 → 拍平；⚠️ 多条共用同一 line_no（气泡序号别用它）
    桥          to_action_raw → registry.parse（形状过了, 字段级仍由 registry 判）
    无救援      转义错 = 丢行（A5：MMT 不做 _rescape_repair）
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from core.mmt.mmt_actions import build_mmt_registry                    # noqa: E402
from core.mmt.mmt_lines import (                                       # noqa: E402
    KIND_ACTION,
    KIND_TEXT,
    MmtLine,
    MmtStream,
    line_from_obj,
    parse_lines,
    to_action_raw,
)


# ---------------------------------------------------------------------------
# 形状
# ---------------------------------------------------------------------------

def test_line_shapes():
    line, why = line_from_obj({"text": "  老师你看这个！  "})
    assert why == "" and line.kind == KIND_TEXT and line.text == "老师你看这个！"

    line, why = line_from_obj({"action": "mmt_send_media",
                               "payload": {"image": "夕阳", "media_type": "image"}})
    assert why == "" and line.is_action and line.action == "mmt_send_media"
    assert line.payload == {"image": "夕阳", "media_type": "image"}

    # payload 可省（= {}）；字段级必填由 registry.parse 判，不在这一层
    bare, why = line_from_obj({"action": "mmt_look"})
    assert why == "" and bare.payload == {}
    print("    lines: text 行 / action 行形状（strip / payload 可省）")


def test_shape_violations_dropped_with_diag():
    cases = [
        ({"text": "x", "action": "mmt_send_media"}, "同时含"),
        ({"payload": {"image": "x"}}, "既无"),
        ({"text": "   "}, "不能为空"),
        ({"text": 123}, "必须是字符串"),
        ({"action": "   "}, "不能为空"),
        ({"action": "mmt_send_media", "payload": []}, "payload 必须是对象"),
        ("裸字符串", "必须是 JSON 对象"),
        ([1, 2], "必须是 JSON 对象"),
    ]
    for obj, expect in cases:
        line, why = line_from_obj(obj)
        assert line is None and expect in why, (obj, why)
    # 走行骨架（含 JSON 层）时: 坏行 → 丢行 + 记账
    lines, diags = parse_lines(['{"text": "好的"}', '{"text": "x", "action": "y"}',
                                "这不是 JSON", ""])
    assert [x.text for x in lines] == ["好的"]              # 坏行只丢自己
    assert len(diags) == 2 and all(d.dropped for d in diags)
    assert "同时含" in diags[0].error and "JSON 解析失败" in diags[1].error
    print("    lines: 形状违规 → 丢行 + 记账（其余行照常）")


def test_extra_field_is_note_not_drop():
    """多余字段 → `dropped=False` 的 note（行本身留下）——与 VN 同款纪律。"""
    lines, diags = parse_lines(['{"text": "好的", "mood": "开心"}'])
    assert len(lines) == 1 and lines[0].text == "好的"
    assert len(diags) == 1 and not diags[0].dropped
    assert "多余字段已丢弃" in diags[0].error and "mood" in diags[0].error
    print("    lines: 多余字段 = note（不丢行）")


def test_no_rescue_for_unescaped_quotes():
    """A5: MMT 不做辅助转义救援——未转义引号 = 丢行（宁缺勿错）。

    （VN 靠"`text` 恒为最后字段"救援；MMT 的 action 行 `payload` 在后, 前提不成立，
    所以两边都不做，行为差写在测试里免得以后有人"顺手补上"。）
    """
    lines, diags = parse_lines([
        '{"text": "他说 \\"别担心\\" 的时候，我差点搞砸。"}',   # 正确转义 → 正常
        '{"text": "他说 "别担心" 的时候，我差点搞砸。"}',        # 未转义 → 丢行
    ])
    assert len(lines) == 1 and "别担心" in lines[0].text
    assert len(diags) == 1 and diags[0].dropped
    assert "JSON 解析失败" in diags[0].error
    print("    lines: 转义正确 → 留下; 未转义 → 丢行（不做救援）")


# ---------------------------------------------------------------------------
# 增量交付（⭐ 行 = 交付单元）
# ---------------------------------------------------------------------------

def test_stream_delivers_each_line_as_it_arrives():
    stream = MmtStream()
    stream.feed('{"text": "老师你看这')
    assert stream.pop_ready() == []                    # 行还没完整 → 不交付
    stream.feed('个！"}\n{"action": "mmt_send_media",')
    ready = stream.pop_ready()
    assert len(ready) == 1 and ready[0].text == "老师你看这个！"
    stream.feed(' "payload": {"image": "夕阳"}}\n```\n\n{"text": "好看吧？"}\n')
    ready = stream.pop_ready()
    assert [x.kind for x in ready] == [KIND_ACTION, KIND_TEXT]
    assert ready[0].action == "mmt_send_media" and ready[1].text == "好看吧？"
    stream.finish()
    assert stream.pop_ready() == []                    # 收尾无残余（行已交付）
    assert [x.text for x in stream.records if x.is_text] == ["老师你看这个！", "好看吧？"]
    print("    lines: 逐行交付（切在行中间也能即时取出；围栏/空行静默跳过）")


def test_array_row_flattened_and_line_no_shared():
    """数组行拍平 → 多条；⚠️ 它们**共用同一 `line_no`** ⇒ 气泡序号别用它（A6）。"""
    stream = MmtStream()
    stream.feed('[{"text": "一"}, {"text": "二"}, {"text": "三"}]\n')
    ready = stream.pop_ready()
    assert [x.text for x in ready] == ["一", "二", "三"]
    assert {x.line_no for x in ready} == {1}           # 同一行裂成三条
    assert stream.line_no == 1
    assert any("数组行 → 拍平 3 条" in n for n in stream.notes)
    print("    lines: 数组行拍平 3 条（共用 line_no=1 ⇒ 气泡序号须另给）")


def test_stream_notes_format():
    stream = MmtStream()
    stream.feed('{"text": "ok"}\n{"nope": 1}\n')
    stream.finish()
    assert stream.notes and stream.notes[0].startswith("[DROP line 2]"), stream.notes
    print(f"    lines: 记账格式 {stream.notes[0]!r}")


# ---------------------------------------------------------------------------
# 桥：行 → registry.parse（两段式校验的第二段）
# ---------------------------------------------------------------------------

def test_to_action_raw_bridges_to_registry():
    """两段式校验的第二段：**字段级**问题由 `registry.parse` 判（形状层不看）。

    ⚠️ 实测记录（⑥-2c 要补的两件，别以为 registry 都管）：
    ① `mmt_trigger_bond_story` 的 **`chapter_title` 必填 + 3-16 字只写在提示词里**——
       `parse_mmt_trigger_bond_story` 只校验"是字符串", 空标题**照样放行**
       （执行器再兜底成"无标题"）⇒ 这一条得在 `mmt_check.py` 里自己加；
    ② `character_id`（`[a-z0-9_]+`）与 `media_type`/`image` **都是硬拒绝** ⇒
       归一化 / 纠错必须**跑在 registry.parse 之前**（晚一步就没机会了）。
    """
    reg = build_mmt_registry()
    line, _ = line_from_obj({"action": "mmt_trigger_bond_story",
                             "payload": {"chapter_title": "电车上的零食"}})
    action, result = reg.parse(to_action_raw(line))
    assert result.is_valid and action.action == "mmt_trigger_bond_story"
    assert action.payload["chapter_title"] == "电车上的零食"

    # ① 标题：类型错会被拒；**空标题不会**（现状 = 提示词级必填）
    wrong_type, _ = line_from_obj({"action": "mmt_trigger_bond_story",
                                   "payload": {"chapter_title": 5}})
    _a, res = reg.parse(to_action_raw(wrong_type))
    assert not res.is_valid, "chapter_title 非字符串必须被 registry 拒"
    empty_title, _ = line_from_obj({"action": "mmt_trigger_bond_story", "payload": {}})
    _a, res = reg.parse(to_action_raw(empty_title))
    assert res.is_valid, "现状如此：空标题放行（c 阶段在 mmt_check.py 补校验）"

    # ② 看不懂的线索 / 视频：registry 直接拒 ⇒ 自愈必须在它之前跑
    # ⚠️ 2026-10-08（D 笔）: 从前这一格举的是 `inspect` 写歪的 character_id ——
    #    那个动作退役, 换成 look 写成正则（线索只认字面, `compile_clue` 当场拒）。
    bad_clue, _ = line_from_obj({"action": "mmt_look",
                                 "payload": {"clue": "苔藓.*杂草"}})
    _a, res = reg.parse(to_action_raw(bad_clue))
    assert not res.is_valid, "线索里有正则味 → registry 拒（schema 里说清了只认字面）"
    video, _ = line_from_obj({"action": "mmt_send_media",
                              "payload": {"image": "夕阳", "media_type": "video"}})
    _a, res = reg.parse(to_action_raw(video))
    assert not res.is_valid, "media_type=video → registry 拒（纠错要在它之前）"
    print("    lines: to_action_raw → registry.parse（形状/字段两段分工 + 两处实测发现）")


def test_text_line_is_not_an_action():
    """text 行**不进 registry**（它是隐含 mmt_chat，由引擎侧映射，不是注册动作）。"""
    line, _ = line_from_obj({"text": "在的"})
    assert line.is_text and not line.is_action
    assert "mmt_chat" not in build_mmt_registry().action_names()
    print("    lines: text 行不是注册动作（隐含 mmt_chat 由引擎映射）")
