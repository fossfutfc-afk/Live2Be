# -*- coding: utf-8 -*-
"""`interperson.yml` 的**两种形状**与读取规整（2026-10-08 换写法 · A 笔 / C2 笔）。

背景（用户裁）: 值从**熟知程度数字**（1/2/3, 给 `inspect` 开门用）换成 **entity 的 text**
（一句**她自己的看法**）—— 内容从 `knowledge.yml` 的 `SIG~friends` 搬来。
一次换一个角色 ⇒ 引擎**必须同时认两种形状**。
⚠️ 文件同日从 `.json` 换成 **`.yml`**（长句立场写 JSON 太苦; 还能写真注释）。

守门:
  ① `__comment__` 不当角色（旧 `.json` 用它写注释; 现在有真 `#` 注释, 过滤留作防御）
  ② ⭐ **换行 = 排版（无痕）, 空格 = 内容（保留）** —— 作者可以随便折行
  ③ 空文件 / 缺文件 ⇒ `{}`（"没写"不是"损坏"）
  ④ ⭐ **真档**（`config/settings/relation/interperson.yml`）能被读通,
     且每一行都是 `ensure_entities(stances=…)` 能用的形状

⚠️ **2026-10-08（D 笔）删掉三组用例**: 从前这里还测过"新形渲染成什么样的字"与
`resolve_access_level`（`inspect` 的门）—— 那两个函数随 `mmt_inspect_character` 退役,
连同它们的用例一起删了。今天的读者是 `engine._stances_of` → `ensure_entities`
（守门在 `tests/core/test_entity_stances.py`）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.mmt.mmt_executor import load_interperson      # noqa: E402

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


def test_comment_key_is_not_a_person(tmp_path):
    """① `__comment__` 是注释不是角色（旧 `.json` 这么写; 现在有真 `#` 注释, 过滤留作防御）。"""
    p = _write(tmp_path, {"__comment__": ["说明"], "igusa_haruka": HARUKA_ROW})
    data = load_interperson(p)
    assert "__comment__" not in data and list(data) == ["igusa_haruka"]
    print("    interperson: `__` 开头的键被丢掉")


def test_line_folding_is_layout_not_content(tmp_path):
    """② ⭐ **换行 = 排版（无痕）, 空格 = 内容（保留）** —— 换 YAML 的主要理由之一。

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
    """③ 空 `.yml`（只有注释）= 没有关系, **不是错误**（⛔ 别把"没写"当损坏）。"""
    p = _write(tmp_path, "# 什么都还没写\n")
    assert load_interperson(p) == {}
    assert load_interperson(tmp_path / "不存在.yml") == {}
    print("    interperson: 空文件 / 缺文件 → {}（不是错误）")


def test_old_shape_rows_are_still_read(tmp_path):
    """③ 旧形（值 = 数字）**照读**（表是作者的, 引擎不擅自解释它）。

    ⚠️ 它今天**没有任何读者**: 从前那是 `inspect` 的门（按权重分级读他人档案）,
    那个动作 2026-10-08 退役了。真档只剩 `hinomiya_chinatsu` 一行是这种形状。
    """
    data = load_interperson(_write(tmp_path, {"asagi_mutsuki": OLD_ROW}))
    assert data["asagi_mutsuki"] == {"rikuhachima_aru": 2, "asagi_mutsuki": 3}
    print("    interperson: 旧形（数字）照读（但今天没有读者）")


def test_the_real_file_reads_through_both_paths():
    """④ ⭐ **真档**能读通: C2 之后除 `hinomiya_chinatsu` 之外, 每一行都是**立场形状**。

    ⚠️ `hinomiya_chinatsu` 是特例: 表里有她那一行, 但她**既没有角色卡也没有 friends**
    ⇒ 没有立场可搬（那一行留着旧的数字, 引擎两种形状都认, 它今天没有读者）。
    """
    table = load_interperson(REAL)
    assert "__comment__" not in table
    haruka = table["igusa_haruka"]
    assert haruka and all(isinstance(v, dict) for v in haruka.values()), haruka
    # ⚠️ `self`（她对自己的看法）**2026-10-12 作者写上了**（此前是留空占位）——
    #    它是**出厂设置**那一格，⛔ 别当成"搬漏了"或"多出来了"。
    assert all(str(v.get("text") or "").strip() for v in haruka.values()), haruka
    assert str(haruka["self"]["text"]).strip().startswith("我总感觉"), haruka["self"]

    migrated = [k for k in table if k not in ("igusa_haruka", "hinomiya_chinatsu")]
    assert len(migrated) >= 6, sorted(table)
    for cid in migrated:
        row = table[cid]
        assert row and all(isinstance(v, dict) for v in row.values()), (cid, row)
        assert all(str(v.get("text") or "").strip() for v in row.values()), cid
        for key, item in row.items():
            if str(key) in ("self", "sensei"):
                continue                 # ⭐ 保留键: 按 id 认（x0000/x0001）, 不需要名字
            # 其余每条要么指向档案（`id`）、要么自带名字（没卡的人）—— ⛔ 不许两条都没有
            assert "id" in item or "name" in item, (cid, key)
    # ⚠️ 只有 chinatsu 还是旧形状（没有立场可搬）—— 顺手钉住"别把它也顺手改了"
    assert all(isinstance(v, int) for v in table["hinomiya_chinatsu"].values())
    # 没档案的人**自带名字**（关系不绑角色卡）: haruka 的 saori / hina 的几位
    assert haruka["saori"]["name"] == "锭前纱织"
    assert table["sorasaki_hina"]["火宫千夏"]["name"] == "火宫千夏"
    # ⭐ 作者写的中文键「老师」**归一成保留键 `sensei`**（引擎按保留键认 x0001）
    assert "sensei" in table["onikata_kayoko"] and "老师" not in table["onikata_kayoko"]
    # 能对上档案的**给 id**（名字/别名零手写）—— 含译名变体那几条
    assert table["amau_ako"]["空崎阳奈（委员长）"]["id"] == "sorasaki_hina"
    assert table["onikata_kayoko"]["陆八魔亚瑠"]["id"] == "rikuhachima_aru"
    print(f"    interperson: 真档 —— {len(migrated)} 个角色已换（{len(haruka)} 条立场）")
