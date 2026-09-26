# -*- coding: utf-8 -*-
"""MMT 操作行自愈（`core/mmt/mmt_repair.py`，⑥-2c 2026-09-25）。

覆盖:
    character_id 归一     精确 / 折叠（大小写·下划线·连字符）/ 子串唯一命中
    ⭐ 不猜              多命中一律放弃（宁缺勿错；放弃 ⇒ 上层回灌）
    media_type 纠错      video → image；library_id 非字符串丢弃；image 空 → 修不了
    chapter_title       去空白 / 超长截断；太短 → 修不了（不替模型起标题）
    repair_line          分派 + 内容行/未知动作原样返回（交 registry 判）
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from core.mmt.mmt_repair import (                                        # noqa: E402
    build_candidates,
    normalize_character_id,
    repair_inspect,
    repair_line,
    repair_send_media,
    repair_trigger,
)
from core.mmt.mmt_lines import MmtLine                                   # noqa: E402
from core.mmt.mmt_check import TITLE_MAX                                 # noqa: E402

CANDS = build_candidates(
    ["igusa_haruka", "asagi_mutsuki"],
    {"igusa_haruka": ["伊草 遥香", "遥香"], "asagi_mutsuki": ["浅黄 睦月", "睦月"]},
)


def test_normalize_exact_and_folded():
    assert normalize_character_id("igusa_haruka", candidates=CANDS) == ("igusa_haruka", "")
    for raw in ("伊草 遥香", "伊草遥香", "遥香", "IGUSA_HARUKA", "igusa-haruka", " igusa_haruka "):
        cid, note = normalize_character_id(raw, candidates=CANDS)
        assert cid == "igusa_haruka", (raw, cid, note)
    assert "归一" in normalize_character_id("IGUSA-HARUKA", candidates=CANDS)[1]
    print("    repair: 精确 + 折叠（大小写/下划线/连字符/空格/中文名）都命中")


def test_normalize_refuses_when_ambiguous():
    """⭐ 两可就不猜——`("", 原因)`，让上层回灌（宁缺勿错）。"""
    dup = build_candidates(["a_haruka", "b_haruka"], {"a_haruka": ["遥香"],
                                                      "b_haruka": ["遥香"]})
    cid, why = normalize_character_id("遥香", candidates=dup)
    assert cid == "" and "不猜" in why, (cid, why)
    # 子串两可同样不猜（"遥香" 同时是两个人名字的一部分）
    dup2 = build_candidates(["igusa_haruka", "haruka_alt"],
                            {"igusa_haruka": ["伊草 遥香"], "haruka_alt": ["遥香 二号"]})
    cid, why = normalize_character_id("遥香", candidates=dup2)
    assert cid == "" and "不猜" in why, (cid, why)
    # 子串**唯一**才用（"伊草" 只属于一个人）
    cid, why = normalize_character_id("伊草", candidates=CANDS)
    assert cid == "igusa_haruka" and "子串唯一命中" in why, (cid, why)
    # 完全对不上
    cid, why = normalize_character_id("胡编的名字", candidates=CANDS)
    assert cid == "" and "对不上" in why
    cid, why = normalize_character_id("", candidates=CANDS)
    assert cid == "" and "空的" in why
    print("    repair: 歧义/无命中/空 → 一律放弃（附原因）；唯一子串才用")


def test_repair_inspect_line():
    line = MmtLine(kind="action", action="mmt_inspect_character",
                   payload={"character_id": "遥香"})
    fixed, note = repair_line(line, candidates=CANDS)
    assert fixed is not None and fixed.payload["character_id"] == "igusa_haruka"
    assert "唯一命中" in note or "归一" in note
    # 修不了 → None（上层回灌；**不猜一个角色塞进去**）
    bad = MmtLine(kind="action", action="mmt_inspect_character",
                  payload={"character_id": "不存在的人"})
    fixed, note = repair_line(bad, candidates=CANDS)
    assert fixed is None and "对不上" in note
    # repair_inspect 是同一实现的直接入口
    assert repair_inspect({"character_id": "睦月"}, candidates=CANDS)[0] == {
        "character_id": "asagi_mutsuki"}
    print("    repair: inspect 行 —— 归一后照常执行 / 修不了则交给回灌")


def test_repair_send_media():
    fixed, note = repair_send_media({"image": " 夕阳 ", "media_type": "video"})
    assert fixed["media_type"] == "image" and fixed["image"] == "夕阳"
    assert "只支持图片" in note
    fixed, note = repair_send_media({"image": "夕阳", "library_id": 5})
    assert "library_id" not in fixed and "丢弃该字段" in note
    assert repair_send_media({"image": "   "})[0] is None      # 空描述修不了
    assert repair_send_media({})[0] is None
    print("    repair: send_media —— media_type 纠回 image / 丢坏字段 / 空描述不修")


def test_repair_trigger():
    fixed, note = repair_trigger({"chapter_title": "  电车上的零食  "})
    assert fixed["chapter_title"] == "电车上的零食" and note == ""
    fixed, note = repair_trigger({"chapter_title": "雨" * (TITLE_MAX + 4)})
    assert len(fixed["chapter_title"]) == TITLE_MAX and "截断" in note
    fixed, note = repair_trigger({"chapter_title": "雨"})     # 太短：**不替模型起标题**
    assert fixed is None and "修不了" in note
    print("    repair: trigger —— 去空白/截断；太短则回灌（不替模型起名）")


def test_repair_line_passthrough():
    text = MmtLine(kind="text", text="在的")
    assert repair_line(text, candidates=CANDS) == (text, "")
    unknown = MmtLine(kind="action", action="mmt_future_action", payload={"x": 1})
    assert repair_line(unknown, candidates=CANDS) == (unknown, "")   # 交 registry 判
    ok = MmtLine(kind="action", action="mmt_send_media", payload={"image": "夕阳"})
    assert repair_line(ok, candidates=CANDS) == (ok, "")             # 无需修 → 原样
    print("    repair: 内容行/未知动作/无需修 → 原样返回（不越界）")
