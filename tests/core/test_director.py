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
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine
from core.director import Director, VisualState, build_director
from core.media import MediaCatalog

from tests.vn_fixtures import scene as _scene  # noqa: E402

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
    """引擎集成测试用的主 LLM stub（记录流脚本; 标注/翻译调用按关键字应答）。"""

    def __init__(self, script):
        self._script = script
        self.place_reply: dict = {"place": ""}

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        import re as _re
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签" in last:               # emotion 标注 → 全 nomal
            m = _re.search(r"恰 (\d+) 项", last)
            n = int(m.group(1)) if m else 1
            return ["nomal"] * n
        if "地点 id JSON" in last:                # 换场翻译（P0-7）
            return self.place_reply
        if "变更句数组" in last:                  # 旧 place 标注（v1 通道）→ 无变更
            return []
        if "选中的文件名" in last:                # 选图（第二遍）→ 保持默认图
            return {"image": ""}
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
    """记录流 v2: switch → 背景键（place 路）→ 导演查表出 background; 导演字段不进 LLM 历史。"""
    main = _MainLLM(_scene(switch_to="教室", lines=["她脸红了。"]))
    d = _director(tmp_path)
    vn = BondStoryEngine(ROOT / "config" / "characters", main, director=d)
    vn.start_session(_CHARACTER)
    vn._place_keys = ["class_room"]              # 只留一个键 → 翻译桩直接给 class_room
    main.place_reply = {"place": "class_room"}
    scene = vn.send_vn_scene("（开场）")
    assert scene.place == "class_room"                   # switch → 背景键
    assert scene.background == "class_room"              # 导演查表
    assert scene.audio is None                           # 占位
    assert [p["text"] for p in scene.paragraphs] == ["她脸红了。"]
    dct = scene.to_dict()
    assert dct["background"] == "class_room"             # 存档可见
    assert "sprite" not in dct and "beat_sprites" not in dct
    hist = vn.history[-1]["content"]                    # 叙事文本历史
    assert "background" not in hist and "audio" not in hist   # 导演输出不进主 LLM 历史
    assert "class_room" not in hist                      # 视觉键也不进
    print("    engine: switch→place→background 合并进 BondScene; 历史不含导演字段")


def test_engine_no_director_pure_text(tmp_path):
    main = _MainLLM(_scene(lines=["纯文本。"]))
    vn = BondStoryEngine(ROOT / "config" / "characters", main)  # director=None
    vn.start_session(_CHARACTER)
    scene = vn.send_vn_scene("x")
    assert scene.background is None and scene.audio is None
    assert [p["text"] for p in scene.paragraphs] == ["纯文本。"]
    assert "background" not in scene.to_dict() and "audio" not in scene.to_dict()
    print("    engine: 无导演 → 纯文本模式, 无视觉字段")


def test_real_table_switch_end_to_end_zero_calls(tmp_path):
    """★ **表接线后能否真跑通**（C2–C5 端到端）: `switch_to="教室"` 全链。

    层1 命中（`教室` → `classroom`, **0 次 LLM 调用**）→ 语义键 → 资产 scene_id
    （`class_room`）→ 导演闸门放行 → `scene.background` = 真 scene_id（不是 neutral）。
    这条链任一环断了, 真机症状就是"背景恒 neutral / 每板都是教室"。
    """
    main = _MainLLM(_scene(switch_to="教室", lines=["她放下了书包。"]))
    d = _director(tmp_path)
    vn = BondStoryEngine(ROOT / "config" / "characters", main, director=d)
    vn.start_session(_CHARACTER)
    assert len(vn._place_keys) > 100, "没吃表"
    calls_before = len(main.calls) if hasattr(main, "calls") else None
    scene = vn.send_vn_scene("（开场）")
    assert scene.place == "classroom", f"层1 该把「教室」解成 classroom, 实得 {scene.place!r}"
    assert scene.place_hint == "教室"                    # 原文仍留着
    assert scene.background == "class_room", scene.background   # 语义键 → 资产键
    assert scene.background != "neutral", "背景没切（导演闸门被拦 → 真机 20/20 板的老症状）"
    # 视觉键不进叙事历史（老纪律）
    hist = vn.history[-1]["content"]
    assert "classroom" not in hist and "class_room" not in hist
    print(f"    e2e: 「教室」→ classroom → class_room → background（层1 0 调用）")


def test_real_table_extends_beyond_old_whitelist(tmp_path):
    """表键**超出旧 31 条白名单**的那些也能走通（否则接线等于白接）。

    `moderncafe` / `hyakkayouran_tatamiroom` 这类键在旧白名单里根本没有;
    用假资产树时它们查不到图 → 导演保持上一场（静默降级, 不崩）。
    """
    main = _MainLLM(_scene(switch_to="街角的咖啡馆，靠窗的位子", lines=["她笑了。"]))
    d = _director(tmp_path)
    vn = BondStoryEngine(ROOT / "config" / "characters", main, director=d)
    vn.start_session(_CHARACTER)
    scene = vn.send_vn_scene("（开场）")
    assert scene.place == "moderncafe", scene.place       # 层1 命中（旧白名单没有这个键）
    assert scene.place not in ("class_room", "school_rooftop"), "不该退回旧白名单的键"
    # 假资产树里没有 BG_ModernCafe → 导演保持冷启动默认, 这是**预期降级**
    assert scene.background == "neutral", scene.background
    print("    e2e: 表外于旧白名单的键也能解出（无图时静默降级保持）")
