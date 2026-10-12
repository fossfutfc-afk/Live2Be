"""MMT 操作行自愈（`core/mmt/mmt_repair.py`，⑥-2c 2026-09-25）。

覆盖:
    media_type 纠错      video → image；library_id 非字符串丢弃；image 空 → 修不了
    chapter_title       去空白 / 超长截断；太短 → 修不了（不替模型起标题）
    repair_line          分派 + 内容行/未知动作原样返回（交 registry 判）

⚠️ **2026-10-08（D 笔）**: 从前这里还覆盖 `mmt_inspect_character` 的 `character_id`
归一（精确 / 折叠 / 子串唯一命中 / 两可不猜）—— 那个动作退役, 那三组用例连同
`build_candidates` / `normalize_character_id` / `repair_inspect` 一起删了
（她今天没有任何"按 id 查人"的动作）。
"""
import pathlib
import sys

from core.mmt.mmt_check import TITLE_MAX  # noqa: E402
from core.mmt.mmt_lines import MmtLine  # noqa: E402
from core.mmt.mmt_repair import (  # noqa: E402
    repair_line,
    repair_send_media,
    repair_trigger,
)


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
    assert repair_line(text) == (text, "")
    unknown = MmtLine(kind="action", action="mmt_future_action", payload={"x": 1})
    assert repair_line(unknown) == (unknown, "")           # 交 registry 判
    ok = MmtLine(kind="action", action="mmt_send_media", payload={"image": "夕阳"})
    assert repair_line(ok) == (ok, "")                     # 无需修 → 原样
    # ⭐ 退役的动作名 ⇒ 本层不认识 ⇒ 原样交 registry（registry 会报"未知动作"）
    gone = MmtLine(kind="action", action="mmt_inspect_character",
                   payload={"character_id": "rikuhachima_aru"})
    assert repair_line(gone) == (gone, "")
    print("    repair: 内容行/未知动作/无需修 → 原样返回（不越界）")
