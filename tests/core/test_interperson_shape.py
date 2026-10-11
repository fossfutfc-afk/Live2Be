# -*- coding: utf-8 -*-
"""`interperson.json` 的**两种形状**与那一块注入（2026-10-08 换写法 · A 笔）。

背景（用户裁）: 值从**熟知程度数字**（1/2/3, 给 `inspect` 开门用）换成 **entity 的 text**
（一句**她自己的看法**）—— 内容从 `knowledge.yml` 的 `SIG~friends` 搬来。
一次换一个角色 ⇒ 引擎**必须同时认两种形状**, 且**两段都印**（宁可重复, 不可丢失）。

守门:
  ① 新形渲染成"她眼里的他们"（立场句 + 零数字）; 旧形**逐字照旧**（别的角色不受影响）
  ② 双形共存 ⇒ 两段都印（搬迁期的安全性）
  ③ `__comment__` 不当角色（否则它会被候选表/渲染器当成一个"人"）
  ④ `resolve_access_level`: 旧形按权重 / 新形（按 id 或名字命中）⇒ 3（**过渡判据**,
     随 `inspect` 退役一起消失）
  ⑤ ⭐ **真档**（`config/settings/relation/interperson.json`）能被这两条读通
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.mmt.mmt_executor import (load_interperson,      # noqa: E402
                                   resolve_access_level,
                                   self_entry_to_prompt)

ROOT = Path(__file__).resolve().parents[2]
REAL = ROOT / "config" / "settings" / "relation" / "interperson.json"

HARUKA_ROW = {
    "sensei": {"text": "即主角/玩家：她极度信任sensei"},
    "aru": {"id": "rikuhachima_aru", "text": "即陆八魔阿露：她所处社团便利屋68的社长"},
    "saori": {"name": "锭前纱织", "aliases": ["纱织"], "text": "即锭前纱织：后来化敌为友"},
}
OLD_ROW = {"rikuhachima_aru": 2, "asagi_mutsuki": 3}


def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "interperson.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
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
    """④ `__comment__` 是注释不是角色（否则候选表/渲染器会把它当"人"）。"""
    p = _write(tmp_path, {"__comment__": ["说明"], "igusa_haruka": HARUKA_ROW})
    data = load_interperson(p)
    assert "__comment__" not in data and list(data) == ["igusa_haruka"]
    print("    interperson: `__` 开头的键被丢掉")


def test_access_level_covers_both_shapes():
    """⑤ `inspect` 的门（**过渡判据**）: 旧形按权重; 新形按 id / 名字命中 ⇒ 3。"""
    table = {"igusa_haruka": HARUKA_ROW, "asagi_mutsuki": OLD_ROW}
    assert resolve_access_level(table, "asagi_mutsuki", "rikuhachima_aru") == 2
    assert resolve_access_level(table, "asagi_mutsuki", "asagi_mutsuki") == 3
    # 新形: 她发的是**角色 id**（引擎归一后的）, 也能按名字（没档案的人只有名字）
    assert resolve_access_level(table, "igusa_haruka", "rikuhachima_aru") == 3
    assert resolve_access_level(table, "igusa_haruka", "锭前纱织") == 3
    assert resolve_access_level(table, "igusa_haruka", "纱织") == 3
    assert resolve_access_level(table, "igusa_haruka", "不存在的人") == 0
    assert resolve_access_level({}, "igusa_haruka", "rikuhachima_aru") == 0
    print("    interperson: 门 —— 旧形按权重 / 新形命中 ⇒ 3（过渡）")


def test_the_real_file_reads_through_both_paths():
    """⑥ ⭐ **真档**能读通: haruka 那一行已经搬完（无数字）, 别的角色仍是旧形。"""
    table = load_interperson(REAL)
    assert "__comment__" not in table
    haruka = table["igusa_haruka"]
    assert haruka and all(isinstance(v, dict) for v in haruka.values()), haruka
    assert all(str(v.get("text") or "").strip() for v in haruka.values())
    # 没档案的 saori 必须自带名字（关系不绑角色卡）
    assert haruka["saori"]["name"] == "锭前纱织"
    others = [k for k in table if k != "igusa_haruka"]
    assert others and all(not isinstance(v, dict) for k in others
                          for v in table[k].values()), "别的角色这一笔不该动"
    text = self_entry_to_prompt(table, "igusa_haruka")
    assert "你眼里的他们" in text and "你的关系记录" not in text
    print(f"    interperson: 真档 —— haruka 已换（{len(haruka)} 条立场）, 其余 {len(others)} 人未动")
