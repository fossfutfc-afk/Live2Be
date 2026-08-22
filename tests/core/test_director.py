# -*- coding: utf-8 -*-
"""core/director 单测 — 视觉导演全路径。

fallback:  infer_sprite 关键词/优先级/白名单过滤
catalog:   background_dirs / background_scenes_in_dir（背景目录分层数据源）
Director:  正则模式 / stub LLM 直给 / 背景分层两段流 / 状态保持 / nudge / 收尾提示
           人设注入 / LLM 连续失败禁用 / 引擎集成（BondScene 带视觉字段, 历史不含）

运行: python -m pytest tests/core/test_director.py
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine
from core.director import Director, VisualState, infer_sprite, load_common_whitelist
from core.director.llm import DirectorLLMError, DirectorSuggestion
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


def _director(tmp_path, llm=None, **kw) -> Director:
    return Director(
        _cat(tmp_path), _CHARACTER,
        persona="角色概要: 自卑敏感", rules="RULES", llm=llm, **kw)


class StubLLM:
    """记录每次 prompt + 按序循环返回预设建议; 预设为异常则抛出（降级路径）。"""

    def __init__(self, *responses):
        self._responses = list(responses)
        self._i = 0
        self.prompts: list[str] = []

    def suggest(self, prompt):
        self.prompts.append(prompt)
        if not self._responses:
            raise DirectorLLMError("脚本耗尽")
        r = self._responses[self._i % len(self._responses)]
        self._i += 1
        if isinstance(r, Exception):
            raise r
        return r


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
# fallback: infer_sprite（正则表情推断）
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
# catalog: 背景目录分层数据源
# ----------------------------------------------------------------------------

def test_catalog_dir_layer(tmp_path):
    c = _cat(tmp_path)
    assert c.background_dirs() == ["BG_Class", "BG_Gehenna"]
    assert c.background_scenes_in_dir("BG_Class") == ["class_room", "class_stairs"]
    assert c.background_scenes_in_dir("BG_Gehenna") == ["gehenna_campus", "gehenna_street"]
    assert c.background_scenes_in_dir("Nope") == []
    print("    catalog: background_dirs / scenes_in_dir（目录分层两段数据源）")


def test_load_common_whitelist_missing(tmp_path):
    assert load_common_whitelist(tmp_path / "nope.json") == {"scenes": [], "dirs": []}
    print("    load_common_whitelist: 缺失 → 空（宁缺勿错）")


# ----------------------------------------------------------------------------
# Director: 无导演 LLM（纯正则模式）
# ----------------------------------------------------------------------------

def test_director_regex_mode_no_llm(tmp_path):
    d = _director(tmp_path)
    s1 = d.visual_for("她脸红了，慌乱地低下头")
    assert s1.sprite == "embarass"
    assert s1.background == "neutral"          # 无导演 LLM → 背景冷启动默认
    s2 = d.visual_for("天气不错，树叶沙沙作响")  # 无情绪词 → 状态保持
    assert s2.sprite == "embarass"
    s3 = d.visual_for("她拍桌怒吼道：过分！")   # 正则当驱动器, 逐场可变
    assert s3.sprite == "shout"
    print("    regex 模式: 逐场正则推断 + 无情绪词保持 + 背景默认 neutral")


# ----------------------------------------------------------------------------
# Director: stub LLM 主驱动
# ----------------------------------------------------------------------------

def test_director_llm_direct(tmp_path):
    stub = StubLLM(DirectorSuggestion(sprite="smile", background="class_room"))
    d = _director(tmp_path, llm=stub, common={"scenes": ["class_room"], "dirs": []})
    vs = d.visual_for("段落")
    assert vs.sprite == "smile" and vs.background == "class_room"
    assert "class_room" in stub.prompts[0]     # 常用场景直给进 prompt
    print("    LLM 直给: 合法 sprite + 合法 scene_id → 直接应用")


def test_director_llm_invalid_falls_back(tmp_path):
    # 非法 sprite / 非法背景 → 冷启动降级（正则 + 默认）
    stub = StubLLM(DirectorSuggestion(sprite="angry", background="nope_room"))
    d = _director(tmp_path, llm=stub, common={"scenes": [], "dirs": []})
    vs = d.visual_for("她脸红了")
    assert vs.sprite == "embarass"             # 非法 → 正则（冷启动）
    assert vs.background == "neutral"          # 非法 → 默认
    print("    LLM 非法输出: 静默降级, 不进主 LLM retry（宁缺勿错）")


def test_director_llm_hold_no_regex_thrash(tmp_path):
    # 有导演 LLM + 已有状态 → 导演非法时保持, 不跑正则（防抖动）
    stub = StubLLM(
        DirectorSuggestion(sprite="smile", background="class_room"),  # 场1 合法
        DirectorSuggestion(sprite="angry", background="keep"),        # 场2 非法 → 保持
    )
    d = _director(tmp_path, llm=stub, common={"scenes": [], "dirs": []})
    s1 = d.visual_for("她脸红了")
    assert s1.sprite == "smile"
    s2 = d.visual_for("她怒吼道：过分！")       # 正则会猜 shout, 但应保持 smile
    assert s2.sprite == "smile"
    print("    LLM 非法 + 已有状态: 状态保持, 正则不盖过导演选择")


def test_director_background_drill(tmp_path):
    # 导演选目录 → 第二段给目录内容拍板
    stub = StubLLM(
        DirectorSuggestion(sprite=None, background="BG_Gehenna"),
        DirectorSuggestion(background="gehenna_street"),
    )
    d = _director(tmp_path, llm=stub, common={"scenes": [], "dirs": ["BG_Gehenna"]})
    vs = d.visual_for("她走在格赫娜的街道上")
    assert vs.background == "gehenna_street"
    assert "gehenna_campus" in stub.prompts[1]   # 第二段 prompt 含目录内场景
    assert "gehenna_street" in stub.prompts[1]
    print("    LLM 背景分层: 选目录 → 第二段拍板场景")


def test_director_background_drill_fail_holds(tmp_path):
    # 目录内拍板非法 → 保持上一场
    stub = StubLLM(
        DirectorSuggestion(background="class_room"),
        DirectorSuggestion(background="BG_Gehenna"),
        DirectorSuggestion(background="invalid_room"),
    )
    d = _director(tmp_path, llm=stub, common={"scenes": [], "dirs": ["BG_Gehenna"]})
    assert d.visual_for("a").background == "class_room"
    assert d.visual_for("b").background == "class_room"   # 拍板失败 → 保持
    print("    LLM 背景分层: 拍板非法 → 保持（宁缺勿错）")


def test_director_background_keep(tmp_path):
    stub = StubLLM(
        DirectorSuggestion(sprite=None, background="class_room"),
        DirectorSuggestion(sprite=None, background="keep"),
        DirectorSuggestion(sprite=None, background=None),
    )
    d = _director(tmp_path, llm=stub, common={"scenes": [], "dirs": []})
    assert d.visual_for("a").background == "class_room"
    assert d.visual_for("b").background == "class_room"   # keep → 保持
    assert d.visual_for("c").background == "class_room"   # null → 保持
    print("    LLM 背景: keep/null → 状态保持")


# ----------------------------------------------------------------------------
# nudge / 收尾提示 / 人设注入
# ----------------------------------------------------------------------------

def test_director_nudge_after_holds(tmp_path):
    stub = StubLLM(DirectorSuggestion(sprite="nomal", background="keep"))
    d = _director(tmp_path, llm=stub, common={"scenes": [], "dirs": []})
    for i in range(5):
        d.visual_for(f"场{i + 1}")
    nudges = ["表情已连续保持" in p for p in stub.prompts]
    assert nudges == [False, False, False, False, True], nudges
    # 场5 prompt 里的场数准确（保持 3 场后注记）
    assert "已连续保持 3 场" in stub.prompts[4]
    print("    nudge: 保持 ≥3 场后注记出现, 场数准确")


def test_director_end_hint(tmp_path):
    stub = StubLLM(DirectorSuggestion(sprite=None, background=None))
    d = _director(tmp_path, llm=stub, common={"scenes": [], "dirs": []})
    d.visual_for("a")
    d.visual_for("收尾了", is_end=True)
    assert "收尾" in stub.prompts[1]
    print("    end: 收尾场景给导演提示（不强制 nomal）")


def test_director_persona_injected(tmp_path):
    stub = StubLLM(DirectorSuggestion(sprite=None, background=None))
    d = _director(tmp_path, llm=stub, common={"scenes": [], "dirs": []})
    d.visual_for("a")
    assert "自卑敏感" in stub.prompts[0]       # 人设注入 → sprite 贴合角色
    print("    persona: 角色概要注入导演 prompt（7B 人设把握缓解）")


# ----------------------------------------------------------------------------
# 宁缺勿错: LLM 连续失败禁用
# ----------------------------------------------------------------------------

def test_director_llm_down_disables(tmp_path):
    class Failing:
        def __init__(self):
            self.calls = 0

        def suggest(self, prompt):
            self.calls += 1
            raise DirectorLLMError("boom")

    stub = Failing()
    d = _director(tmp_path, llm=stub, common={"scenes": [], "dirs": []})
    for txt in ("她脸红了", "她怒吼", "她笑了"):
        d.visual_for(txt)
    assert stub.calls == 2                     # 第 2 次失败后禁用, 第 3 场不再调
    assert d.visual_for("她笑了").sprite == "smile"   # 降级正则仍可用
    print("    LLM down: 连续 2 次失败禁用, 降级正则 VN 照跑")


# ----------------------------------------------------------------------------
# 引擎集成: BondScene 携带视觉字段
# ----------------------------------------------------------------------------

def test_engine_attaches_visuals(tmp_path):
    main = _MainLLM({"action": "story_scene", "payload": {
        "paragraphs": ["她脸红了。"], "choices": []}})
    stub = StubLLM(DirectorSuggestion(sprite="embarass", background="class_room"))
    d = _director(tmp_path, llm=stub, common={"scenes": ["class_room"], "dirs": []})
    vn = BondStoryEngine(ROOT / "config" / "characters", main, director=d)
    vn.start_session(_CHARACTER)
    scene = vn.send_vn_scene("（开场）")
    assert scene.sprite == "embarass" and scene.background == "class_room"
    assert scene.to_dict()["sprite"] == "embarass"          # 存档可见
    hist = json.loads(vn.history[-1]["content"])            # 历史是契约 payload
    assert "sprite" not in hist and "background" not in hist  # 导演不污染主 LLM 历史
    print("    engine: 导演视觉字段合并进 BondScene; 历史不含视觉字段")


def test_engine_no_director_pure_text(tmp_path):
    main = _MainLLM({"action": "story_scene", "payload": {
        "paragraphs": ["纯文本。"], "choices": []}})
    vn = BondStoryEngine(ROOT / "config" / "characters", main)  # director=None
    vn.start_session(_CHARACTER)
    scene = vn.send_vn_scene("x")
    assert scene.sprite is None and scene.background is None
    assert "sprite" not in scene.to_dict()
    print("    engine: 无导演 → 纯文本模式, 无视觉字段")
