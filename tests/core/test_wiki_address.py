"""`address.py` —— **可见形式 → 节点**（N5b, 2026-09-29）。

这是 `render.py` 的另一半：那边把节点渲染成"她看得见的形式", 这边把她写下的形式
解回节点。两个调用者（`noticed` 与将来的 `look`）共用它 —— 各写一份必然漂。

判据只有一条: **只归一格式, 不做近似匹配**（剥的是我们自己定的语法字符, 不是猜她想说谁）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from core.brain import WikiStoreV2, make_node  # noqa: E402
from core.brain.address import find_episode, normalize_title  # noqa: E402


def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    st.add(make_node("episode", text="我把秘密基地告诉了老师", title="瓦片缝里的苔藓",
                     event_seq=[1]))
    st.add(make_node("episode", text="中秋节晚上老师来陪我", title="中秋的杂草屋",
                     event_seq=[2]))
    st.add(make_node("belief", text="杂草屋是我最安心的地方", title="瓦片缝里的苔藓", subject="杂草屋", event_seq=[1]))
    return st


# ---------------------------------------------------------------------------
# 格式归一（**只剥格式**）
# ---------------------------------------------------------------------------

def test_normalize_strips_marks_but_not_meaning():
    """剥的是语法字符: 书名号/尖括号/方括号/半全角引号/空白 + `｜` 取第一段。"""
    want = "瓦片缝里的苔藓"
    for raw in (
        "瓦片缝里的苔藓",
        " 瓦片缝里的苔藓 ",
        "《瓦片缝里的苔藓》",
        "〈瓦片缝里的苔藓〉",
        "<瓦片缝里的苔藓>",
        "【瓦片缝里的苔藓】",
        "〔《瓦片缝里的苔藓》〕",
        '"瓦片缝里的苔藓"',                      # 半角双引号
        "“瓦片缝里的苔藓”",                      # 全角双引号
        "「瓦片缝里的苔藓」",
        "《瓦片缝里的苔藓》｜5 天前｜9/26",        # 整段元信息抄进来了
    ):
        assert normalize_title(raw) == want, raw
    # ⚠️ **不做近似匹配**: 少一个字 / 多一个修饰词都不是它 —— 引擎不猜
    assert normalize_title("瓦片缝的苔藓") == "瓦片缝的苔藓"
    assert normalize_title("那件关于苔藓的事") == "那件关于苔藓的事"
    assert normalize_title(None) == "" and normalize_title(123) == ""
    print("    address: 归一剥格式（10 种写法 → 同一个名字）")


# ---------------------------------------------------------------------------
# 解析（命中 0 / 歧义 ⇒ 不猜）
# ---------------------------------------------------------------------------

def test_find_episode_ok_and_tolerance(tmp_path):
    st = _store(tmp_path)
    node, why = find_episode(st, "瓦片缝里的苔藓")
    assert why == "ok" and node is not None and node.title == "瓦片缝里的苔藓"
    # 她连书名号一起抄 / 整段抄 → 照样命中（**容错是兜底, 不是规范**）
    assert find_episode(st, "《瓦片缝里的苔藓》")[1] == "ok"
    assert find_episode(st, "《瓦片缝里的苔藓》｜5 天前｜9/26")[1] == "ok"
    print("    address: 带书名号 / 整段抄 → 照样命中")


def test_find_episode_miss_and_empty(tmp_path):
    st = _store(tmp_path)
    assert find_episode(st, "我编的一件事")[1] == "miss"
    assert find_episode(st, "")[1] == "empty"
    assert find_episode(st, "《》")[1] == "empty"          # 只有格式字符
    print("    address: 编造的 → miss; 空 → empty（都不是错误, 是丢的理由）")


def test_find_episode_ambiguous_does_not_guess(tmp_path):
    """同名 ≥2 条 ⇒ **不猜**（标题唯一性今天还没写入时强制, 这是真分支不是防御）。"""
    st = _store(tmp_path)
    st.add(make_node("episode", text="另一条同名的", title="瓦片缝里的苔藓",
                     event_seq=[9]))
    node, why = find_episode(st, "瓦片缝里的苔藓")
    assert node is None and why == "ambiguous"
    print("    address: 同名两条 → ambiguous（不猜）")


def test_find_episode_only_in_episode_namespace(tmp_path):
    """只在 **episode** 的标题空间里解析 —— belief 不是"另一件事"。"""
    st = _store(tmp_path)
    only_belief = WikiStoreV2(tmp_path / "b", world_id="world1", char_id="c")
    only_belief.add(make_node("belief", text="看法", title="某个名字", subject="x", event_seq=[1]))
    assert find_episode(only_belief, "某个名字")[1] == "miss"
    # 上例里 belief 与 episode 同名 → 只认 episode 那条, 所以不是 ambiguous
    assert find_episode(st, "瓦片缝里的苔藓")[1] == "ok"
    print("    address: 只在 episode 命名空间里找（belief 同名不算）")
