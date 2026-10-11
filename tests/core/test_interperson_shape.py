# -*- coding: utf-8 -*-
"""`interperson.yml` 的**两种形状**与那一块注入（2026-10-08 换写法 · A 笔）。

背景（用户裁）: 值从**熟知程度数字**（1/2/3, 给 `inspect` 开门用）换成 **entity 的 text**
（一句**她自己的看法**）—— 内容从 `knowledge.yml` 的 `SIG~friends` 搬来。
一次换一个角色 ⇒ 引擎**必须同时认两种形状**, 且**两段都印**（宁可重复, 不可丢失）。
⚠️ 文件同日从 `.json` 换成 **`.yml`**（长句立场写 JSON 太苦）。

守门:
  ① 新形渲染成"她眼里的他们"（立场句 + 零数字）; 旧形**逐字照旧**（别的角色不受影响）
  ② 双形共存 ⇒ 两段都印（搬迁期的安全性）
  ③ `__comment__` 不当角色（旧 `.json` 用它写注释; 现在有真 `#` 注释, 过滤留作防御）
  ④ `resolve_access_level`: 旧形按权重 / 新形（按 id 或名字命中）⇒ 3（**过渡判据**,
     随 `inspect` 退役一起消失）
  ⑤ ⭐ **YAML 折行不留空格** —— 汉字之间的空白在读取时被规整掉（作者可以随便折行）
  ⑥ ⭐ **真档**（`config/settings/relation/interperson.yml`）能被这两条读通
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.mmt.mmt_executor import (load_interperson,      # noqa: E402
                                   resolve_access_level,
                                   self_entry_to_prompt)

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "config" / "settings" / "relation" / "interperson.yml"

HARUKA_ROW = {
    "sensei": {"text": "即主角/玩家：她极度信任sensei"},
    "aru": {"id": "rikuhachima_aru", "text": "即陆八魔阿露：她所处社团便利屋68的社长"},
    "saori": {"name": "锭前纱织", "aliases": ["纱织"], "text": "即锭前纱织：后来化敌为友"},
}
OLD_ROW = {"rikuhachima_aru": 2, "asagi_mutsuki": 3}


def _write(tmp_path: Path, data) -> Path:
    p = tmp_path / "interperson.yml"
    if isinstance(data, str):
        p.write_text(data, encoding="utf-8")
    else:
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def test_new_shape_renders_stances_without_numbers(tmp_path):
    """① 新形 = **她自己的看法**（键=她的叫法; ⛔ 一个数字都不出现）。"""
    text = self_entry_to_prompt({"igusa_haruka": HARUKA_ROW}, "igusa_haruka")
    assert text.startswith("你眼里的他们"), text
    assert "aru：即陆八魔阿露" in text and "sensei：即主角/玩家" in text
    assert "saori：即锭前纱织" in text
    # ⛔ 旧那套"键=id / 值=熟悉程度"在**这一行**里不许再出现
    assert "你的关系记录" not in text and "熟悉程度" not in text
    assert "2" not in text and "3" not in text
    print("    interperson: 新形印立场（键=她的叫法, 零数字）")


def test_old_shape_still_renders_verbatim(tmp_path):
    """② 旧形**逐字照旧** —— 别的角色还没搬, 他们必须一点变化都没有。"""
    text = self_entry_to_prompt({"asagi_mutsuki": OLD_ROW}, "asagi_mutsuki")
    assert text == (
        "你的关系记录: {asagi_mutsuki: 3, rikuhachima_aru: 2}\n"
        "含义: 键=角色id（查资料时用）, 值=熟悉程度（1=萍水相逢 2=社团/队友 3=故知）; "
        "未列出的角色=素不相识, 但你可能听说过其公开信息")
    print("    interperson: 旧形逐字不变")


def test_both_shapes_coexist_and_are_both_printed():
    """③ 双形共存 ⇒ 两段都印（搬家期的安全网: 宁可重复, 不可丢失）。"""
    row = {**HARUKA_ROW, "rikuhachima_aru": 2}
    text = self_entry_to_prompt({"igusa_haruka": row}, "igusa_haruka")
    assert "你眼里的他们" in text and "你的关系记录" in text
    assert "aru：即陆八魔阿露" in text and "rikuhachima_aru: 2" in text
    print("    interperson: 两种形状同表 ⇒ 两段都印")


def test_comment_key_is_not_a_person(tmp_path):
    """③ `__comment__` 是注释不是角色（旧 `.json` 这么写; 现在有真 `#` 注释, 过滤留作防御）。"""
    p = _write(tmp_path, {"__comment__": ["说明"], "igusa_haruka": HARUKA_ROW})
    data = load_interperson(p)
    assert "__comment__" not in data and list(data) == ["igusa_haruka"]
    print("    interperson: `__` 开头的键被丢掉")


def test_line_folding_is_layout_not_content(tmp_path):
    """⑤ ⭐ **换行 = 排版（无痕）, 空格 = 内容（保留）** —— 换 YAML 的主要理由之一。

    · `|`（**推荐**）: 换行**直接删掉** ⇒ 汉字↔拉丁 交界处**也不会多出空格**
      （作者把 `我非常信任 / sensei` 折成两行, 读出来是 `我非常信任sensei`）;
    · `>`（兼容）: 解析时换行**已经变成空格** ⇒ 只能兜"汉字之间"那种
      （`…在某个人面前 敞开心扉` —— `knowledge.yml` 的 `SIG~friends` 就是这个毛病）;
    · **同一行里自己敲的空格一律保留**（那是内容, 不是排版）。
    """
    literal = (
        "igusa_haruka:\n"
        "  aru:\n"
        "    text: |\n"
        "      即陆八魔阿露：社长，\n"
        "      曾带她逃出霸凌。\n"
        "  sensei:\n"
        "    text: |\n"
        "      我非常信任\n"
        "      sensei，也信任 Aru 这个人\n"
    )
    row = load_interperson(_write(tmp_path, literal))["igusa_haruka"]
    assert row["aru"]["text"] == "即陆八魔阿露：社长，曾带她逃出霸凌。", row["aru"]["text"]
    # ⭐ 折行删掉（汉字↔拉丁 也不留空格）, 但**行内**的空格照旧
    assert row["sensei"]["text"] == "我非常信任sensei，也信任 Aru 这个人", \
        row["sensei"]["text"]

    folded = (
        "igusa_haruka:\n"
        "  aru:\n"
        "    text: >\n"
        "      即陆八魔阿露：社长，\n"
        "      曾带她逃出霸凌。\n"
    )
    assert load_interperson(_write(tmp_path, folded))["igusa_haruka"]["aru"]["text"] == \
        "即陆八魔阿露：社长，曾带她逃出霸凌。"
    print("    interperson: 换行=排版（`|` 无痕）/ 空格=内容（行内保留）")


def test_empty_file_is_not_an_error(tmp_path):
    """空 `.yml`（只有注释）= 没有关系, **不是错误**（⛔ 别把"没写"当损坏）。"""
    p = _write(tmp_path, "# 什么都还没写\n")
    assert load_interperson(p) == {}
    assert load_interperson(tmp_path / "不存在.yml") == {}
    print("    interperson: 空文件 / 缺文件 → {}（不是错误）")


def test_access_level_covers_both_shapes():
    """④ `inspect` 的门（**过渡判据**）: 旧形按权重; 新形按 id / 名字命中 ⇒ 3。"""
    table = {"igusa_haruka": HARUKA_ROW, "asagi_mutsuki": OLD_ROW}
    assert resolve_access_level(table, "asagi_mutsuki", "rikuhachima_aru") == 2
    assert resolve_access_level(table, "asagi_mutsuki", "asagi_mutsuki") == 3
    # 新形: 她发的是**角色 id**（引擎归一后的）, 也能按名字 / 键（没档案的人只有这些）
    assert resolve_access_level(table, "igusa_haruka", "rikuhachima_aru") == 3
    assert resolve_access_level(table, "igusa_haruka", "锭前纱织") == 3
    assert resolve_access_level(table, "igusa_haruka", "纱织") == 3
    assert resolve_access_level(table, "igusa_haruka", "saori") == 3      # 键也是把手
    assert resolve_access_level(table, "igusa_haruka", "不存在的人") == 0
    assert resolve_access_level({}, "igusa_haruka", "rikuhachima_aru") == 0
    print("    interperson: 门 —— 旧形按权重 / 新形命中 ⇒ 3（过渡）")


def test_the_real_file_reads_through_both_paths():
    """⑥ ⭐ **真档**能读通: haruka 那一行已经搬完（无数字）, 别的角色仍是旧形。"""
    table = load_interperson(REAL)
    assert "__comment__" not in table
    haruka = table["igusa_haruka"]
    assert haruka and all(isinstance(v, dict) for v in haruka.values()), haruka
    # ⚠️ `self`（她对自己的看法）是**故意留空**的占位 —— 用户 2026-10-08: "先不写, 但要补"。
    #    ⛔ 别把它当成"搬漏了一条"：真档那条今天由 digest 的 R3 长着。
    assert all(str(v.get("text") or "").strip()
               for k, v in haruka.items() if k != "self"), haruka
    assert "self" in haruka and not str(haruka["self"]["text"]).strip()
    # 没档案的 saori 必须自带名字（关系不绑角色卡）
    assert haruka["saori"]["name"] == "锭前纱织"
    others = [k for k in table if k != "igusa_haruka"]
    assert others and all(not isinstance(v, dict) for k in others
                          for v in table[k].values()), "别的角色这一笔不该动"
    text = self_entry_to_prompt(table, "igusa_haruka")
    assert "你眼里的他们" in text and "你的关系记录" not in text
    print(f"    interperson: 真档 —— haruka 已换（{len(haruka)} 条立场）, 其余 {len(others)} 人未动")
