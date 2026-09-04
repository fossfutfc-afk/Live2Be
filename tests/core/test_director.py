# -*- coding: utf-8 -*-
"""core/director 单测 — v2 视觉导演（只决定背景 + 音频占位）。

Director:  place → background 查表（合法 / 非法 / 缺失保持 / 冷启动默认）
           audio 恒 None（占位, 未来背景/音乐仲裁填）
           reset / state / 引擎集成（BondScene 携带 background+audio+beats+place）
表情（beats[].emotion）不经导演——渲染端直查 emotions.yml（catalog.sprite）,
   测试见 test_media.py（sprite 查询）。infer_sprite 正则已随导演表情职责退役
   （2026-08-23, 见 git 历史 core/director/fallback.py）。

运行: python -m pytest tests/core/test_director.py
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine
from core.director import Director, VisualState, build_director
from core.media import MediaCatalog

ROOT = Path(__file__).resolve().parent.parent.parent
_CHARACTER = "igusa_haruka"


# ----------------------------------------------------------------------------
# 假资产树 + 构造
# ----------------------------------------------------------------------------

def _make_assets(tmp_path):
    root = tmp_path / "assets"
    bg = root / "background"
    (bg / "BG_Class").mkdir(parents=True, exist_ok=True)
    (bg / "BG_Class" / "BG_ClassRoom.jpg").write_bytes(b"x")
    (bg / "BG_Class" / "BG_ClassRoom_Night.jpg").write_bytes(b"x")
    (bg / "BG_Class" / "BG_ClassStairs.jpg").write_bytes(b"x")
    (bg / "BG_Gehenna").mkdir(exist_ok=True)
    (bg / "BG_Gehenna" / "BG_GehennaCampus.jpg").write_bytes(b"x")
    (bg / "BG_Gehenna" / "BG_GehennaStreet.jpg").write_bytes(b"x")
    (bg / "BG_Gehenna" / "BG_GehennaStreet_Night.jpg").write_bytes(b"x")
    ch = root / "illustration" / _CHARACTER
    (ch / "diff").mkdir(parents=True, exist_ok=True)
    for i in range(1, 7):
        (ch / "diff" / f"haruka_spr_0{i}.png").write_bytes(b"png")
    (ch / "emotions.yml").write_text(
        "emotions:\n"
        "  nomal: diff/haruka_spr_01.png\n"
        "  respond: diff/haruka_spr_02.png\n"
        "  smile: diff/haruka_spr_03.png\n"
        "  embarrass: diff/haruka_spr_04.png\n"
        "  serious: diff/haruka_spr_05.png\n"
        "  shout: diff/haruka_spr_06.png\n",
        encoding="utf-8",
    )
    return root


def _cat(tmp_path) -> MediaCatalog:
    return MediaCatalog(_make_assets(tmp_path))


def _director(tmp_path, **kw) -> Director:
    return Director(_cat(tmp_path), _CHARACTER, **kw)


class _MainLLM:
    """引擎集成测试用的主 LLM stub（单动作脚本; 标注调用返回 nomal 数组）。"""

    def __init__(self, script: dict):
        self._script = script

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text"):
        import re as _re
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last:               # emotion 标注 → 全 nomal
            n = len(_re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        return self._script

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


# ----------------------------------------------------------------------------
# VisualState: 背景 + 音频占位（无 sprite）
# ----------------------------------------------------------------------------

def test_visual_state_defaults():
    vs = VisualState()
    assert vs.background == "neutral"
    assert vs.audio is None
    assert vs.to_dict() == {"background": "neutral"}     # audio None 省略
    assert "sprite" not in vs.to_dict()                  # 表情不在导演职责
    print("    VisualState: 冷启动默认 neutral + audio 占位 None, 无 sprite")


# ----------------------------------------------------------------------------
# place → background: 合法 / 非法 / 缺失保持 / 冷启动默认
# ----------------------------------------------------------------------------

def test_visual_for_place_valid(tmp_path):
    d = _director(tmp_path)
    vs = d.visual_for(place="class_room")
    assert vs.background == "class_room"
    assert vs.audio is None                              # 占位恒 None
    assert d.state.background == "class_room"            # 视觉记忆已更新
    print("    visual_for: 合法 place → background; audio 占位 None")


def test_visual_for_place_invalid_holds(tmp_path):
    d = _director(tmp_path)
    assert d.visual_for(place="class_room").background == "class_room"
    # 非法 place → 保持上一场（静默降级, 不回传主 LLM）
    assert d.visual_for(place="nope_room").background == "class_room"
    # 缺失 place → 保持上一场
    assert d.visual_for(place=None).background == "class_room"
    # 冷启动（无上一场）非法 place → 默认 neutral
    d.reset()
    assert d.visual_for(place="nope_room").background == "neutral"
    print("    place: 合法用 / 非法·缺失保持 / 冷启动非法默认（静默降级）")


def test_director_reset_and_build(tmp_path):
    d = _director(tmp_path)
    d.visual_for(place="class_room")
    d.reset()
    assert d.state.background == "neutral"               # reset 回冷启动
    # build_director: 从 char 构建（纯背景查表）
    from core.parsing.dynamic_character_parser import CharacterLoader
    char = CharacterLoader(ROOT / "config" / "characters").load(_CHARACTER)
    built = build_director(char, catalog=_cat(tmp_path))
    assert built.char_id == _CHARACTER
    print("    director: reset 回冷启动; build_director 从 char 构建")


# ----------------------------------------------------------------------------
# 引擎集成: BondScene 携带 background + audio + beats + place（导演输出不进主 LLM 历史）
# ----------------------------------------------------------------------------

def test_engine_attaches_background_audio(tmp_path):
    main = _MainLLM({"action": "story_scene", "payload": {
        "paragraphs": [{"text": "她脸红了。", "emotion": "embarrass"}],
        "place": "class_room",
        "choices": [],
    }})
    d = _director(tmp_path)
    vn = BondStoryEngine(ROOT / "config" / "characters", main, director=d)
    vn.start_session(_CHARACTER)
    scene = vn.send_vn_scene("（开场）")
    assert scene.background == "class_room"
    assert scene.audio is None                           # 占位
    # 2026-09-02: 骨架 emotion 丢弃 → 标注层回填（stub 返回 nomal）
    assert scene.paragraphs == [{"text": "她脸红了。", "emotion": "nomal"}]
    assert scene.place == "class_room"
    dct = scene.to_dict()
    assert dct["background"] == "class_room"             # 存档可见
    assert "sprite" not in dct and "beat_sprites" not in dct
    hist = vn.history[-1]["content"]                    # 2026-09-05: 叙事文本历史
    assert "background" not in hist and "audio" not in hist   # 导演输出不进主 LLM 历史
    print("    engine: place→background + audio 合并进 BondScene; 历史不含导演字段")


def test_engine_no_director_pure_text(tmp_path):
    main = _MainLLM({"action": "story_scene", "payload": {
        "paragraphs": [{"text": "纯文本。", "emotion": "nomal"}], "choices": []}})
    vn = BondStoryEngine(ROOT / "config" / "characters", main)  # director=None
    vn.start_session(_CHARACTER)
    scene = vn.send_vn_scene("x")
    assert scene.background is None and scene.audio is None
    assert scene.paragraphs == [{"text": "纯文本。", "emotion": "nomal"}]  # 契约 emotion 必填
    assert "background" not in scene.to_dict() and "audio" not in scene.to_dict()
    print("    engine: 无导演 → 纯文本模式, 无视觉字段")
