# -*- coding: utf-8 -*-
"""core/director 单测 — v2 视觉导演（意图查表驱动, DESIGN_VISUAL_PROTOCOL.md）。

fallback:  infer_sprite 关键词/优先级/白名单过滤（beats 缺失兜底用）
Director:  beats[].emotion 查表映射（1:1）/ 词表外延续 / 拍内延续
           place 背景查表（合法 / 非法 / 缺失保持）
           beats 缺失 → 旧链（正则 → 保持 → 默认）
           last_beat_sprites 暴露 / 引擎集成（BondScene 携带 beats+beat_sprites+place）
v1 退役项（导演 LLM 大空间选择 / nudge / 人设注入 / 背景目录分层）不再测试——
   情感判断归主 LLM, 导演只查表; 导演 LLM 仅在 1:N 拍板时上场（本轮无数据）。

运行: python -m pytest tests/core/test_director.py
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine
from core.director import Director, VisualState, infer_sprite
from core.media import MediaCatalog

ROOT = Path(__file__).resolve().parent.parent.parent
_CHARACTER = "igusa_haruka"


# ----------------------------------------------------------------------------
# 假资产树 + 构造
# ----------------------------------------------------------------------------

def _make_assets(tmp_path):
    root = tmp_path / "assets"
    bg = root / "background"
    (bg / "BG_Class").mkdir(parents=True)
    (bg / "BG_Class" / "BG_ClassRoom.jpg").write_bytes(b"x")
    (bg / "BG_Class" / "BG_ClassRoom_Night.jpg").write_bytes(b"x")
    (bg / "BG_Class" / "BG_ClassStairs.jpg").write_bytes(b"x")
    (bg / "BG_Gehenna").mkdir()
    (bg / "BG_Gehenna" / "BG_GehennaCampus.jpg").write_bytes(b"x")
    (bg / "BG_Gehenna" / "BG_GehennaStreet.jpg").write_bytes(b"x")
    (bg / "BG_Gehenna" / "BG_GehennaStreet_Night.jpg").write_bytes(b"x")
    ch = root / "illustration" / _CHARACTER
    (ch / "diff").mkdir(parents=True)
    for i in range(1, 7):
        (ch / "diff" / f"haruka_spr_0{i}.png").write_bytes(b"png")
    (ch / "emotions.yml").write_text(
        "emotions:\n"
        "  nomal: diff/haruka_spr_01.png\n"
        "  respond: diff/haruka_spr_02.png\n"
        "  smile: diff/haruka_spr_03.png\n"
        "  embarass: diff/haruka_spr_04.png\n"
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
    """引擎集成测试用的主 LLM stub（单动作脚本）。"""

    def __init__(self, script: dict):
        self._script = script

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text"):
        return self._script

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


# ----------------------------------------------------------------------------
# fallback: infer_sprite（beats 缺失时正则兜底）
# ----------------------------------------------------------------------------

_EMOTIONS = ["nomal", "respond", "smile", "embarass", "serious", "shout"]


def test_infer_sprite_keywords_and_priority():
    assert infer_sprite("她笑着挥了挥手", _EMOTIONS) == "smile"
    assert infer_sprite("他怒吼道：滚开！", _EMOTIONS) == "shout"
    assert infer_sprite("她脸红了，支支吾吾说不出话", _EMOTIONS) == "embarass"
    assert infer_sprite("他板着脸，严肃地说", _EMOTIONS) == "serious"
    assert infer_sprite("她点点头，低声应道", _EMOTIONS) == "respond"
    # 优先级: embarass(脸红) 在 smile(笑) 之前 → 脸红着笑 = embarass
    assert infer_sprite("她脸红着笑了", _EMOTIONS) == "embarass"
    print("    infer_sprite: 关键词命中 + 优先级（脸红着笑→embarass）")


def test_infer_sprite_whitelist_and_empty():
    assert infer_sprite("她脸红了", ["nomal"]) is None      # 白名单外 → None
    assert infer_sprite("", _EMOTIONS) is None               # 空文本
    assert infer_sprite("天气很好，树叶沙沙作响", _EMOTIONS) is None  # 无情绪词
    assert infer_sprite(None, _EMOTIONS) is None
    print("    infer_sprite: 白名单过滤 + 空/无匹配 → None（宁缺勿错）")


def test_visual_state_defaults():
    vs = VisualState()
    assert vs.sprite == "nomal" and vs.background == "neutral"
    print("    VisualState: 冷启动默认 nomal/neutral")


# ----------------------------------------------------------------------------
# v2: beats 意图查表映射（1:1 + 词表外延续 + 拍内延续）
# ----------------------------------------------------------------------------

def test_visual_for_beats_map_1to1(tmp_path):
    d = _director(tmp_path)
    vs = d.visual_for([{"text": "她笑了", "emotion": "smile"}], place="class_room")
    assert vs.sprite == "smile"                      # 1:1 查表（合法 → 直接用）
    assert vs.background == "class_room"             # place 合法 → 直接用
    assert d.last_beat_sprites == ["smile"]
    print("    beats 查表: 合法 emotion → sprite; place 合法 → background")


def test_visual_for_beats_unknown_continues(tmp_path):
    d = _director(tmp_path)
    # 冷启动 + 词表外 emotion → 默认 nomal（协议 §11 静默兜底）
    vs = d.visual_for([{"text": "t", "emotion": "angry"}])
    assert vs.sprite == "nomal"
    # 拍内延续: 合法后接词表外/空 → 延续上一拍
    vs2 = d.visual_for([
        {"text": "a", "emotion": "smile"},
        {"text": "b", "emotion": "angry"},           # 词表外 → 延续 smile
        {"text": "c", "emotion": "  "},              # 空 emotion → 延续 smile
    ])
    assert vs2.sprite == "smile"
    assert d.last_beat_sprites == ["smile", "smile", "smile"]
    print("    beats 词表外/空: 延续上一拍/默认, 静默不拒绝")


def test_visual_for_beats_scene_sprite_is_last(tmp_path):
    d = _director(tmp_path)
    vs = d.visual_for([
        {"text": "a", "emotion": "embarass"},
        {"text": "b", "emotion": "shout"},
    ])
    assert vs.sprite == "shout"                       # 场景主表情 = 最后一拍
    assert d.last_beat_sprites == ["embarass", "shout"]
    print("    beats: 场景主表情 = 最后一拍有效映射")


# ----------------------------------------------------------------------------
# v2: place 背景（合法 / 非法 / 缺失保持）
# ----------------------------------------------------------------------------

def test_visual_for_place_validation(tmp_path):
    d = _director(tmp_path)
    # 合法 place → 用
    assert d.visual_for([], place="class_room").background == "class_room"
    # 非法 place → 保持上一场（静默降级）
    assert d.visual_for([], place="nope_room").background == "class_room"
    # 缺失 place → 保持上一场
    assert d.visual_for([], place=None).background == "class_room"
    # 冷启动（无上一场）非法 place → 默认 neutral
    d.reset()
    assert d.visual_for([], place="nope_room").background == "neutral"
    print("    place: 合法用 / 非法·缺失保持 / 冷启动非法默认（静默降级）")


# ----------------------------------------------------------------------------
# v2: beats 缺失（纯文本模式）→ 旧链（正则 → 保持 → 默认）
# ----------------------------------------------------------------------------

def test_visual_for_legacy_regex_when_no_beats(tmp_path):
    d = _director(tmp_path)
    # beats 缺失 → 正则当驱动器（旧链保留, 纯文本兼容）
    vs = d.visual_for(None, text="她脸红了，低下头")
    assert vs.sprite == "embarass"
    assert d.last_beat_sprites == []                  # 无 beats → 无 per-beat 映射
    # 无情绪词 → 状态保持
    vs2 = d.visual_for(None, text="天气不错，树叶沙沙作响")
    assert vs2.sprite == "embarass"
    print("    beats 缺失: 正则逐场推断 + 无情绪词保持（VN 照跑）")


# ----------------------------------------------------------------------------
# 引擎集成: BondScene 携带 beats + beat_sprites + place（导演输出不进主 LLM 历史）
# ----------------------------------------------------------------------------

def test_engine_beats_attach(tmp_path):
    main = _MainLLM({"action": "story_scene", "payload": {
        "paragraphs": ["她脸红了。"],
        "beats": [{"text": "她脸红了", "emotion": "embarass"},
                  {"text": "对不起", "emotion": "smile"}],
        "place": "class_room",
        "choices": [],
    }})
    d = _director(tmp_path)
    vn = BondStoryEngine(ROOT / "config" / "characters", main, director=d)
    vn.start_session(_CHARACTER)
    scene = vn.send_vn_scene("（开场）")
    assert scene.sprite == "smile"                    # 场景主表情 = 最后一拍
    assert scene.beat_sprites == ["embarass", "smile"]
    assert scene.background == "class_room"
    assert scene.place == "class_room"
    dct = scene.to_dict()
    assert dct["beat_sprites"] == ["embarass", "smile"]   # 存档可见
    hist = json.loads(vn.history[-1]["content"])
    assert "beat_sprites" not in hist                 # 导演输出不进主 LLM 历史（单向）
    print("    engine: beats→beat_sprites+place 合并进 BondScene; 历史不含视觉字段")


def test_engine_no_director_pure_text(tmp_path):
    main = _MainLLM({"action": "story_scene", "payload": {
        "paragraphs": ["纯文本。"], "choices": []}})
    vn = BondStoryEngine(ROOT / "config" / "characters", main)  # director=None
    vn.start_session(_CHARACTER)
    scene = vn.send_vn_scene("x")
    assert scene.sprite is None and scene.background is None
    assert not scene.beat_sprites
    assert "sprite" not in scene.to_dict() and "beat_sprites" not in scene.to_dict()
    print("    engine: 无导演 → 纯文本模式, 无视觉字段")
