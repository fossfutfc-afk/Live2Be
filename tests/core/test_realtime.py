# -*- coding: utf-8 -*-
"""`core.worldtime.realtime` —— 现实日历（②）: 表 / 判定 / 台账 / 注记。

这些用例里**每条断言背后都是一次试出来的错**, 尤其是"零补发"那几条 ——
见 `realtime.due_occasions` docstring 里记的两条特例。
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from core.worldtime import realtime as rt


def D(y: int, m: int, d: int) -> datetime:
    """当天正午（带 `REAL_TZ`）—— 用它而不是裸 `date`, 顺带验一遍时区分支。"""
    return datetime(y, m, d, 12, 0, tzinfo=rt._REAL_TZ)


def clk(seen: str = "", fired: dict | None = None, rewind: int = 0) -> dict:
    return {"schema_version": 1, "last_seen_date": seen,
            "rewind_count": rewind, "fired": fired or {}}


def ids(occs) -> list[str]:
    return [o.id for o in occs]


@pytest.fixture()
def table(tmp_path):
    """小表: 一个年度节日 + 一个写死年份的一次性事件。"""
    p = tmp_path / "festivals.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "festivals": [
            {"id": "xmas", "month": 12, "day": 25, "year": "",
             "name": "圣诞节", "proactive": True},
            {"id": "one", "month": 4, "day": 1, "year": 2027,
             "name": "周年", "proactive": False},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 表 —— 读 / 容错
# ---------------------------------------------------------------------------

def test_default_table_loads():
    """出厂表能读、且全是 wildcard 节日。"""
    occs = rt.load_occasions()
    assert occs, "出厂 config/eggs/festivals.json 应当有内容"
    assert all(o.month and o.day for o in occs)
    assert all(o.proactive for o in occs)


def test_load_accepts_jsonc_comment_lines(tmp_path):
    """作者手编的文件得像配置 —— `//` 注释行要被吃掉, 不是把文件弄坏。"""
    p = tmp_path / "f.json"
    p.write_text(
        '{\n'
        '// 这是注释\n'
        '  "festivals": [\n'
        '    // 另一条\n'
        '    {"id": "a", "month": 1, "day": 2, "name": "甲", "proactive": true}\n'
        '  ]\n'
        '}\n', encoding="utf-8")
    assert ids(rt.load_occasions(p)) == ["a"]


def test_load_missing_file_is_empty(tmp_path):
    assert rt.load_occasions(tmp_path / "nope.json") == []


def test_load_broken_json_is_empty(tmp_path):
    p = tmp_path / "f.json"
    p.write_text("{ 这不是 json", encoding="utf-8")
    assert rt.load_occasions(p) == []


def test_load_root_not_object_is_empty(tmp_path):
    p = tmp_path / "f.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert rt.load_occasions(p) == []


def test_load_missing_festivals_key_is_empty(tmp_path):
    p = tmp_path / "f.json"
    p.write_text('{"schema_version": 1}', encoding="utf-8")
    assert rt.load_occasions(p) == []


def test_load_skips_bad_rows_keeps_good(tmp_path):
    """一行写坏 = 那一行没了, 不是整个节日系统停工。"""
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"festivals": [
        {"id": "good", "month": 5, "day": 6, "name": "好", "proactive": True},
        {"id": "", "month": 1, "day": 1, "name": "无 id", "proactive": True},
        {"id": "noday", "month": 1, "name": "缺 day", "proactive": True},
        {"id": "badmonth", "month": 13, "day": 1, "name": "越界", "proactive": True},
        {"id": "nopro", "month": 2, "day": 2, "name": "缺 proactive"},
        {"id": "notobj"},
        "我不是对象",
    ]}, ensure_ascii=False), encoding="utf-8")
    assert ids(rt.load_occasions(p)) == ["good"]


def test_proactive_is_required_no_default(tmp_path):
    """用户裁决: `proactive` 逐行手写 —— **没有默认值**, 缺了就跳过该行。"""
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"festivals": [
        {"id": "a", "month": 1, "day": 1, "name": "甲"},
        {"id": "b", "month": 1, "day": 1, "name": "乙", "proactive": "true"},
        {"id": "c", "month": 1, "day": 1, "name": "丙", "proactive": False},
    ]}, ensure_ascii=False), encoding="utf-8")
    occs = rt.load_occasions(p)
    assert ids(occs) == ["c"]                       # 字符串 "true" 不算
    assert occs[0].proactive is False


def test_enabled_false_is_dropped(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"festivals": [
        {"id": "off", "month": 1, "day": 1, "name": "停用",
         "proactive": True, "enabled": False},
    ]}, ensure_ascii=False), encoding="utf-8")
    assert rt.load_occasions(p) == []


def test_year_blank_forms_are_all_wildcard(tmp_path):
    """空串 / 缺键 / `"*"` —— 三种"留空"写法都吃（作者写空串, 程序吐 None）。"""
    p = tmp_path / "f.json"
    rows = [{"id": c, "month": 1, "day": 1, "name": c, "proactive": True, **extra}
            for c, extra in (("a", {"year": ""}), ("b", {}), ("c", {"year": "*"}))]
    p.write_text(json.dumps({"festivals": rows}, ensure_ascii=False),
                 encoding="utf-8")
    assert all(o.year is None for o in rt.load_occasions(p))


def test_year_numeric_string_is_accepted(tmp_path):
    """手编文件里 `"2027"` 和 `2027` 是同一个意思, 为此让一行失效不值得。"""
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"festivals": [
        {"id": "a", "month": 4, "day": 1, "year": "2027",
         "name": "周年", "proactive": True}]}, ensure_ascii=False),
        encoding="utf-8")
    occs = rt.load_occasions(p)
    assert occs[0].year == 2027
    assert occs[0].year_fixed is True


def test_duplicate_key_bucket_dropped(tmp_path):
    """同一个 key 的"任意年"与"写死年"并存会让幂等键打架 → 后到的丢。"""
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"festivals": [
        {"id": "a", "month": 1, "day": 1, "name": "任意年", "proactive": True},
        {"id": "a", "month": 1, "day": 1, "year": 2027, "name": "写死年",
         "proactive": True},
        {"id": "c", "key": "a", "month": 1, "day": 1, "year": "",
         "name": "同 key 同桶（任意年, 也要丢）", "proactive": True},
        {"id": "d", "key": "a", "month": 6, "day": 1,
         "name": "同 key 不同桶（允许）", "proactive": True},
    ]}, ensure_ascii=False), encoding="utf-8")
    occs = rt.load_occasions(p)
    # 桶 = (key, 年是否写死)。每个桶**先到的留下**, 后到的全是重复:
    #   a(任意年) 留; a(2027) 留; c 撞"任意年"桶 → 丢; d 撞"任意年"桶 → 丢
    assert [(o.id, o.year) for o in occs] == [("a", None), ("a", 2027)]


def test_load_order_is_file_order(tmp_path):
    """不排序 —— 作者手编的顺序就是作者的意图。"""
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"festivals": [
        {"id": "z", "month": 1, "day": 1, "name": "z", "proactive": True},
        {"id": "a", "month": 2, "day": 2, "name": "a", "proactive": True},
    ]}, ensure_ascii=False), encoding="utf-8")
    assert ids(rt.load_occasions(p)) == ["z", "a"]


# ---------------------------------------------------------------------------
# Occasion —— target / signature / 注记
# ---------------------------------------------------------------------------

def test_target_wildcard_is_this_year_even_if_future():
    """★ `target` **不回退到上一次** —— 否则新档会在 3/1 收到"圣诞快乐"。"""
    o = rt.Occasion(id="x", month=12, day=25, name="圣诞", proactive=True)
    assert o.target(date(2026, 3, 1)) == date(2026, 12, 25)
    assert o.target(date(2026, 12, 25)) == date(2026, 12, 25)
    assert o.target(date(2027, 1, 5)) == date(2027, 12, 25)


def test_target_fixed_year_ignores_today():
    o = rt.Occasion(id="a", month=4, day=1, name="周年", proactive=True, year=2027)
    for d in (date(2026, 1, 1), date(2027, 4, 1), date(2029, 6, 6)):
        assert o.target(d) == date(2027, 4, 1)


def test_target_feb29_falls_to_mar1():
    """`2/29` 而当年非闰年 → 落到 `3/1`, **绝不构造一个不存在的日期**。"""
    o = rt.Occasion(id="a", month=2, day=29, name="闰日", proactive=True)
    assert o.target(date(2026, 1, 1)) == date(2026, 3, 1)      # 2026 非闰年
    assert o.target(date(2028, 1, 1)) == date(2028, 2, 29)     # 2028 是闰年


def test_signature_uses_real_year_not_fictional_2100():
    """★ 决定 2: 拿角色的虚构年 2100 当键 = "每年一次"退化成"一辈子一次"。"""
    o = rt.Occasion(id="xmas", month=12, day=25, name="圣诞", proactive=True)
    assert o.signature(date(2026, 12, 25)) == "xmas:2026"
    assert o.signature(date(2027, 12, 25)) == "xmas:2027"


def test_signature_key_falls_back_to_id_but_key_wins():
    """生日要 8 个人共用 `birthday` 这个 id → 靠 `key` 区分。"""
    a = rt.Occasion(id="birthday", month=5, day=13, name="生日", proactive=True)
    b = rt.Occasion(id="birthday", month=5, day=13, name="生日", proactive=True,
                    key="haruka_bd")
    assert a.signature(date(2026, 5, 13)) == "birthday:2026"
    assert b.signature(date(2026, 5, 13)) == "haruka_bd:2026"


def test_note_default_template_has_attribution_and_permission():
    """归因（"手机日历上标着"）+ 许可半句 —— 两半都不能少。"""
    o = rt.Occasion(id="x", month=1, day=1, name="元旦", proactive=True)
    n = o.note()
    assert "手机日历上标着" in n and "元旦" in n
    assert "主动" in n


def test_note_proactive_false_has_no_permission():
    o = rt.Occasion(id="x", month=1, day=1, name="元旦", proactive=False)
    n = o.note()
    assert "手机日历上标着" in n and "元旦" in n
    assert "主动" not in n


def test_note_text_overrides_template():
    o = rt.Occasion(id="x", month=1, day=1, name="元旦", proactive=True,
                    note_text="  自己写的  ")
    assert o.note() == "自己写的"


# ---------------------------------------------------------------------------
# occasions_on —— 纯投影
# ---------------------------------------------------------------------------

def test_occasions_on_projects_without_filtering(table):
    """它只做"表 → 日期", 今年还没到的日子**照样在结果里**（过没过不归它管）。"""
    got = rt.occasions_on(D(2026, 6, 1), path=table)
    assert [(o.id, d) for o, d in got] == [
        ("xmas", date(2026, 12, 25)),
        ("one", date(2027, 4, 1)),
    ]


def test_occasions_on_accepts_date_datetime_and_iso(table):
    for arg in (date(2026, 6, 1), D(2026, 6, 1), "2026-06-01T12:00:00+08:00"):
        assert [o.id for o, _ in rt.occasions_on(arg, path=table)] == ["xmas", "one"]


# ---------------------------------------------------------------------------
# due_occasions —— 三闸
# ---------------------------------------------------------------------------

def test_new_character_gets_no_backfill(table):
    """★ 新角色零补发 —— 这是试出来的, 见 `due_occasions` docstring 特例 2。"""
    assert rt.due_occasions("h", clk(), D(2026, 3, 1), path=table) == []
    assert rt.due_occasions("h", clk(), D(2026, 9, 10), path=table) == []


def test_new_character_gets_the_very_day(table):
    """建号当天赶上的节日要给她。"""
    assert ids(rt.due_occasions("h", clk(), D(2026, 12, 25), path=table)) == ["xmas"]


def test_due_needs_a_clock(table):
    assert ids(rt.due_occasions("h", None, D(2026, 12, 26), path=table)) == ["xmas"]


def test_short_absence_is_caught_up(table):
    """12/25 玩过、12/27 回来 —— 仍然该听到圣诞（那是"她还记着那天"）。"""
    assert ids(rt.due_occasions("h", clk("2026-12-25"), D(2026, 12, 27),
                                path=table)) == ["xmas"]


def test_already_fired_is_not_repeated(table):
    c = clk("2026-12-25", {"h": {"xmas:2026": "2026-12-25"}})
    assert rt.due_occasions("h", c, D(2026, 12, 26), path=table) == []


def test_fired_is_per_character(table):
    """★ 台账按角色分桶 —— 否则遥香过完圣诞, 阿露永远收不到。"""
    c = clk("2026-12-25", {"haruka": {"xmas:2026": "2026-12-25"}})
    assert rt.due_occasions("haruka", c, D(2026, 12, 26), path=table) == []
    assert ids(rt.due_occasions("aru", c, D(2026, 12, 26), path=table)) == ["xmas"]


def test_past_the_day_no_longer_fires(table):
    """过了那天、且从没说过 → 第二天还能补, 但**一周后的新档**不再提。"""
    assert ids(rt.due_occasions("h", clk("2026-12-25"), D(2026, 12, 26),
                                path=table)) == ["xmas"]
    # 新角色（地板 = 昨天）在 12/27 建号 → 12/25 已经在地板之前
    assert rt.due_occasions("h", clk(), D(2026, 12, 27), path=table) == []


def test_leaving_during_a_period_does_not_dig_it_up():
    """长期离开一年: 上次说话**之前**错的节日一件不翻, 之后错的照常补。"""
    oc = [rt.Occasion(id="xmas", month=12, day=25, name="圣诞节", proactive=True)]
    c = clk("2027-01-02", {"h": {"xmas:2025": "2025-12-25",
                                 "xmas:2026": "2026-12-25"}})
    # 离场那一年（2026）的圣诞已经说过; 2027 还没到 → 一个都不该有
    assert rt.due_occasions("h", c, D(2027, 12, 24), occasions=oc) == []
    # 到了 2027 的圣诞, 才该说
    assert ids(rt.due_occasions("h", c, D(2027, 12, 25), occasions=oc)) == ["xmas"]


def test_fixed_year_fires_once_ever():
    """★ `year` 栏干两份活: 写死 = 一辈子一次（键不带年份后缀之外的年）。"""
    ann = rt.Occasion(id="anniv", month=4, day=1, name="周年", proactive=True,
                      year=2027)
    c = clk("2027-03-20")
    assert rt.due_occasions("h", c, D(2027, 3, 31), occasions=[ann]) == []
    assert ids(rt.due_occasions("h", c, D(2027, 4, 1), occasions=[ann])) == ["anniv"]
    # 说过了 → 之后再多年也不提
    c2 = clk("2027-04-01", {"h": {"anniv:2027": "2027-04-01"}})
    for d in (D(2027, 4, 2), D(2028, 4, 1), D(2029, 4, 1)):
        assert rt.due_occasions("h", c2, d, occasions=[ann]) == []


def test_yearly_festival_fires_once_per_year():
    """年度节日: 一年一次, 该说的那次不会被吞掉。"""
    oc = [rt.Occasion(id="xmas", month=12, day=25, name="圣诞节", proactive=True)]
    c = clk("2026-12-25", {"h": {"xmas:2026": "2026-12-25"}})
    assert rt.due_occasions("h", c, D(2027, 12, 24), occasions=oc) == []
    assert ids(rt.due_occasions("h", c, D(2027, 12, 25), occasions=oc)) == ["xmas"]


def test_clock_rewind_does_not_resend(table):
    """回拨: `fired` 的键不退 → 已经说过的不重发。"""
    c = clk("2026-12-26", {"h": {"xmas:2026": "2026-12-26"}})
    for d in (D(2026, 12, 26), D(2026, 12, 25), D(2026, 1, 1)):
        assert rt.due_occasions("h", c, d, path=table) == []


def test_future_last_seen_is_clamped(table):
    """台账写到未来（回拨残留）时不要把地板顶到未来, 否则她永远收不到东西。"""
    c = clk("2030-01-01")
    assert ids(rt.due_occasions("h", c, D(2026, 12, 25), path=table)) == ["xmas"]


# ---------------------------------------------------------------------------
# 台账 —— 读写 / 回拨计数
# ---------------------------------------------------------------------------

def test_new_clock_has_no_last_seen():
    """★ 空账本的 `last_seen_date` 必须是**空**, 不是"今天"。

    第一版写成了今天, 于是新档第一天就收到元旦+情人节两条祝福 ——
    一个"她早就见过老师"的假事实混进了新账本。
    """
    assert rt.new_clock()["last_seen_date"] == ""
    assert rt.new_clock()["fired"] == {}


def test_clock_roundtrip(tmp_path):
    c = rt.new_clock()
    rt.mark_seen(c, D(2026, 9, 17))
    rt.mark_fired(c, "haruka",
                  [rt.Occasion(id="x", month=9, day=10, name="教师节",
                               proactive=True)], D(2026, 9, 17))
    rt.save_clock(tmp_path, c)
    back = rt.load_clock(tmp_path)
    assert back["last_seen_date"] == "2026-09-17"
    assert back["fired"]["haruka"] == {"x:2026": "2026-09-17"}


def test_load_missing_or_broken_clock_is_empty(tmp_path):
    assert rt.load_clock(tmp_path)["last_seen_date"] == ""
    (tmp_path / rt.CLOCK_FILENAME).write_text("{ 坏掉的", encoding="utf-8")
    c = rt.load_clock(tmp_path)
    assert c["last_seen_date"] == "" and c["fired"] == {}
    # ★ 损坏时**不覆盖**磁盘 —— 还能人工救回来
    assert (tmp_path / rt.CLOCK_FILENAME).read_text(encoding="utf-8") == "{ 坏掉的"


def test_load_clock_sanitizes_junk(tmp_path):
    (tmp_path / rt.CLOCK_FILENAME).write_text(json.dumps({
        "schema_version": "x",
        "last_seen_date": "  2026-09-17  ",
        "rewind_count": -5,
        "fired": {"h": {"a:2026": "2026-01-01"}, "bad": "不是字典"},
    }, ensure_ascii=False), encoding="utf-8")
    c = rt.load_clock(tmp_path)
    assert c["last_seen_date"] == "2026-09-17"
    assert c["rewind_count"] == 0
    assert c["fired"] == {"h": {"a:2026": "2026-01-01"}}


def test_mark_seen_moves_forward_only():
    c = rt.new_clock()
    rt.mark_seen(c, D(2026, 9, 17))
    rt.mark_seen(c, D(2026, 9, 20))
    assert c["last_seen_date"] == "2026-09-20"
    assert c["rewind_count"] == 0
    rt.mark_seen(c, D(2026, 9, 18))
    assert c["rewind_count"] == 1


def test_mark_fired_is_idempotent(tmp_path):
    o = rt.Occasion(id="x", month=9, day=10, name="教师节", proactive=True)
    c = rt.new_clock()
    assert rt.mark_fired(c, "h", [o], D(2026, 9, 10)) == ["x:2026"]
    assert rt.mark_fired(c, "h", [o], D(2026, 9, 10)) == []
    assert rt.mark_fired(c, "h", [], D(2026, 9, 10)) == []
    assert rt.mark_fired(c, "aru", [o], D(2026, 9, 10)) == ["x:2026"]


# ---------------------------------------------------------------------------
# due_notes —— 引擎入口
# ---------------------------------------------------------------------------

def test_due_notes_fires_once_then_never_again(tmp_path, table):
    wd = tmp_path / "world1"

    first = rt.due_notes("haruka", wd, now=D(2026, 12, 25), path=table)
    assert len(first) == 1 and "圣诞节" in first[0]
    # ★ 调用即记账 —— LLM 调用失败也不会让同一轮再注一次
    assert rt.due_notes("haruka", wd, now=D(2026, 12, 25), path=table) == []
    assert rt.due_notes("haruka", wd, now=D(2026, 12, 26), path=table) == []
    # 别人还该有（台账按角色分桶）
    assert len(rt.due_notes("aru", wd, now=D(2026, 12, 25), path=table)) == 1
    # 台账真落了盘
    assert (wd / rt.CLOCK_FILENAME).is_file()


def test_due_notes_never_raises(tmp_path):
    """宁缺勿错: 台账坏掉时返回 [], 绝不抛。"""
    bad = tmp_path / "world1"
    bad.mkdir()
    (bad / rt.CLOCK_FILENAME).write_text("坏", encoding="utf-8")
    assert isinstance(rt.due_notes("h", bad, now=D(2026, 9, 10)), list)


def test_due_notes_returns_notes_with_permission_split(tmp_path):
    """出口是**注记文本**（不是 Occasion）, 且 `proactive` 真的改了文本。"""
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"festivals": [
        {"id": "x", "month": 9, "day": 10, "name": "教师节", "proactive": True},
        {"id": "y", "month": 9, "day": 10, "name": "安静的日子", "proactive": False},
    ]}, ensure_ascii=False), encoding="utf-8")
    notes = rt.due_notes("h", tmp_path / "w", now=D(2026, 9, 10), path=p)
    assert len(notes) == 2
    assert all(isinstance(n, str) and "手机日历上标着" in n for n in notes)
    assert any("主动" in n for n in notes) and any("主动" not in n for n in notes)
