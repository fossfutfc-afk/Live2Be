# -*- coding: utf-8 -*-
"""回忆册派生单测（core/session/chapters, 2026-09-12）。

口径（DESIGN_COLLECTION_BOOK §1/§3）:
    · 章 = vn_enter…vn_exit; **只收 vn_exit completed=True**
    · 未完(open) / 主动中断(completed=False) / 废弃(vn_abandon) / 空壳(无板) → 都不收
    · 纪念图归属: 章区间内 → 该章; vn_enter 之前（预热先出图 #40）→ 紧随其后的章;
      中间夹 vn_abandon → 作废; 无后续章 = 孤儿 → 不显示

运行: python -m pytest tests/core/test_chapters.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.session.chapters import chapter_index, replayable_chapters  # noqa: E402
from core.session.events import make_event, marker  # noqa: E402


def _board(seq, text="一板", **extra):
    return make_event("bond", "story_scene",
                      {"paragraphs": [{"text": text}], **extra}, seq=seq)


def _chapter(enter, exit_, title="章", boards=(3, 4), completed=True):
    """一段完整的章: vn_enter → 板们 → vn_exit。"""
    evs = [marker("vn_enter", {"chapter_title": title} if title else None, seq=enter)]
    evs += [_board(s) for s in boards]
    evs.append(marker("vn_exit", {"completed": completed}, seq=exit_))
    return evs


def test_completed_chapter_is_replayable():
    evs = _chapter(2, 9, title="咖啡厅的甜点陷阱", boards=(3, 5, 7))
    chs = replayable_chapters(evs)
    assert len(chs) == 1
    ch = chs[0]
    assert (ch["from_seq"], ch["to_seq"]) == (2, 9)
    assert ch["title"] == "咖啡厅的甜点陷阱"
    assert ch["boards"] == 3 and len(ch["scenes"]) == 3
    # 场景项与现网回放同构: seq + input/picked 摘出, 其余即渲染字段
    assert ch["scenes"][0]["seq"] == 3
    assert ch["scenes"][0]["picked"] is None
    assert ch["scenes"][0]["scene"]["paragraphs"] == [{"text": "一板"}]
    assert "input" not in ch["scenes"][0]["scene"]


def test_only_confirmed_completed_renders():
    """未完 / 主动中断 / 废弃 / 空壳 —— 四种都不进册子（"渲染都不渲染"）。"""
    open_ch = _chapter(2, 5)[:-1]                     # vn_enter + 板, 无 vn_exit
    aborted = _chapter(10, 13, completed=False)       # 主动中断（completed=False）
    evs = open_ch + aborted
    assert replayable_chapters(evs) == []


def test_abandoned_chapter_dropped():
    """vn_abandon 关闭的段 close_kind='abandon' → 不是章（即使它的板都在）。"""
    evs = _chapter(2, 6)
    evs.append(marker("vn_abandon", {"start_seq": 2, "end_seq": 6}, seq=7))
    assert replayable_chapters(evs) == []


def test_empty_shell_chapter_dropped():
    """空壳重启段（只有 marker, 无板）→ 不渲染（点进去也是空的）。"""
    evs = [marker("vn_enter", {"chapter_title": "空壳"}, seq=2),
           marker("vn_exit", {"completed": True}, seq=3)]
    assert replayable_chapters(evs) == []


def test_legacy_bond_without_enter_not_a_chapter():
    """v1 旧档: 无 vn_enter 的裸 bond 事件不构成章（册子只认有边界的章）。"""
    evs = [_board(2), _board(3)]
    assert replayable_chapters(evs) == []


def test_chapters_keep_stream_order():
    """顺序 = 事件流行序（作者口径: 按 events.jsonl 行序渲染标题）。"""
    evs = _chapter(2, 4, title="第一章") + _chapter(10, 12, title="第二章")
    assert [c["title"] for c in replayable_chapters(evs)] == ["第一章", "第二章"]


def test_memorial_image_attribution():
    """图归属: ① 章前预热图 → 紧随其后的章; ② 晚到的图（本章结束后才落盘）→ 仍归本章。

    ② 是**必须有**的一条: 生图 ~26s, 纪念又多在本章末尾——图常常在 `vn_exit` 之后
    才写 marker; 只按区间判就会把它错挂到下一章（玩家会在下一章看到上一章的画）。
    判据 = 最近的前置 `memorial_enter`（哪块板触发的图）——**锚点说了算**, 哪怕图
    落盘时本章（甚至下一章）早已收尾。
    """
    img = lambda seq, url: marker("memorial_image", {"url": url, "scene_id": "s"}, seq=seq)
    evs = [
        img(1, "/gallery/w/c/prewarm.png"),            # ① 章前, 无板锚点 → 归甲
        *_chapter(2, 6, title="甲"),
        marker("memorial_enter", {"chapter_title": "甲"}, seq=5),   # 甲内纪念窗口
        img(7, "/gallery/w/c/late.png"),               # ② 甲已收尾, 但板锚点在甲里 → 甲
        *_chapter(10, 12, title="乙"),
        marker("memorial_enter", {"chapter_title": "没跑起来"}, seq=19),  # 章后预热板
        img(20, "/gallery/w/c/orphan.png"),            # ③ 孤儿（其后无章）→ 不显示
    ]
    chs = replayable_chapters(evs)
    assert [c["images"] for c in chs] == [
        ["/gallery/w/c/prewarm.png", "/gallery/w/c/late.png"],
        [],
    ]


def test_prewarm_image_before_enter_goes_to_next_chapter():
    """决策 #40: 预热会先出图——板锚点也落在章前（下一章的首板）→ 归**下一章**。"""
    evs = [
        *_chapter(2, 6, title="上一章"),
        marker("memorial_enter", {"chapter_title": "下一章"}, seq=8),   # 章前预热板
        marker("memorial_image", {"url": "/gallery/w/c/pre.png"}, seq=9),
        *_chapter(10, 12, title="下一章"),
    ]
    chs = replayable_chapters(evs)
    assert chs[0]["images"] == []
    assert chs[1]["images"] == ["/gallery/w/c/pre.png"]


def test_prewarm_image_dropped_when_abandon_between():
    """预热出的图若与后续 vn_enter 之间夹了 vn_abandon → 作废（那是废弃章的图）。"""
    evs = [
        marker("memorial_image", {"url": "/gallery/w/c/dead.png"}, seq=1),
        marker("vn_abandon", {"start_seq": 0, "end_seq": 1}, seq=2),
        *_chapter(3, 6, title="新章"),
    ]
    chs = replayable_chapters(evs)
    assert [c["images"] for c in chs] == [[]]


def test_chapter_index_drops_scenes():
    """角色页索引不背正文（scenes 摘掉, 其余字段留给列表渲染）。"""
    idx = chapter_index(_chapter(2, 6, title="甲"))
    assert len(idx) == 1
    assert "scenes" not in idx[0]
    assert idx[0]["title"] == "甲" and idx[0]["boards"] == 2
