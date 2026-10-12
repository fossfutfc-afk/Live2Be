"""renderer/ 单测 — 输入规范化 / 背景 / 差分 / 特效 / 管线同构 / CLI / 播放层。

策略（DESIGN_RENDERER.md §十一）:
    背景解算: scene_id → 图/过渡; 缺失 → 保持; 相同 → 不切换
    差分解算: 每段 emotion（标注层写入）; 词表外 → 保持（确定性）
    （⚠️ 2026-09-21: 原 Python 侧 `BondScene.para_emotions()` 已删——零消费者）
    特效映射: 每 emotion → 期望特效; 缺省 → 无
    同构验证: 同一场景 dict 走 from_live 与 from_event → RenderOutput 一致
    CLI 输出: 标签/特效符号/选项渲染

运行: python -m pytest tests/renderer/test_renderer.py
"""
import sys
from pathlib import Path



from renderer import (
    AudioRequest,
    BackgroundResolver,
    BackgroundResult,
    EffectResolver,
    RenderScene,
    Renderer,
    RenderState,
    SpriteResolver,
)
from renderer.cli import _fx_symbol, render_choices
from core.media.catalog import MediaCatalog


# ----------------------------------------------------------------------------
# 假资产（与 tests/core/test_media.py 同构——tmp 目录免真实 assets 依赖）
# ----------------------------------------------------------------------------

def _make_assets(tmp_path):
    root = tmp_path / "assets"
    bg = root / "background"
    for sub, files in {
        "BG_Class": ["BG_ClassRoom.jpg", "BG_ClassRoom_Night.jpg"],
        "BG_Gehenna": ["BG_GehennaCampus_Night.jpg"],
    }.items():
        d = bg / sub
        d.mkdir(parents=True, exist_ok=True)   # 可重复调用（同构测试建两次）
        for f in files:
            (d / f).write_bytes(b"img")
    # 角色（板块结构: {char}/default/ 为默认外观）
    ch = root / "illustration" / "igusa_haruka" / "default"
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


def _catalog(tmp_path):
    return MediaCatalog(_make_assets(tmp_path))


# ----------------------------------------------------------------------------
# RenderScene: 输入规范化（from_live / from_event 双路径 + 容错）
# ----------------------------------------------------------------------------

def test_scene_from_event_and_live(tmp_path):
    payload = {
        "paragraphs": [{"text": "天台的风好舒服。", "emotion": "smile"},
                       {"text": "（她低头抿嘴）"}, "旧档字符串段落"],
        "choices": ["走过去", "喊她"], "is_end": False,
        "background": "class_room", "audio": None, "place": "class_room",
        "input": "你在哪", "picked": "走过去",
    }
    scene = RenderScene.from_event(payload)
    assert scene.paragraphs == [
        {"text": "天台的风好舒服。", "emotion": "smile"},
        {"text": "（她低头抿嘴）"},
        {"text": "旧档字符串段落"},
    ]
    assert scene.choices == ["走过去", "喊她"]
    assert not scene.is_end and scene.background == "class_room"
    assert scene.input == "你在哪" and scene.picked == "走过去"

    class FakeScene:                       # 鸭子类型: 任何有 to_dict() 的对象
        def to_dict(self): return payload

    live = RenderScene.from_live(FakeScene())
    assert live.paragraphs == scene.paragraphs
    assert live.background == scene.background
    assert live.input == ""               # 实时路径无 input/picked
    assert live.picked is None
    print("    scene: from_event/from_live 双路径 + input/picked 区分")


def test_scene_bad_data_defaults():
    assert RenderScene.from_event(None).paragraphs == []
    assert RenderScene.from_event({}).is_end is False
    robust = RenderScene.from_event({
        "paragraphs": ["好", 42, None, {"text": ""}, {"text": "嗯", "emotion": 7}],
        "choices": ["A", 1, None], "is_end": "yes",
        "background": 3, "input": 9, "picked": 8,
    })
    assert robust.paragraphs == [{"text": "好"}, {"text": "嗯"}], robust.paragraphs  # emotion 非 str → 丢弃
    assert robust.choices == ["A"] and robust.background is None
    assert robust.input == "" and robust.picked is None
    print("    scene: 坏数据过滤, 宁缺勿错")


# ----------------------------------------------------------------------------
# BackgroundResolver: 切换/保持/缺失
# ----------------------------------------------------------------------------

def test_background_switch_hold_missing(tmp_path):
    r = BackgroundResolver(_catalog(tmp_path))
    r1 = r.resolve("class_room")
    assert r1.changed and r1.scene_id == "class_room"
    assert r1.media_path and r1.media_path.endswith("BG_ClassRoom.jpg")
    assert r1.transition > 0
    r2 = r.resolve("class_room")          # 相同 → 不切换
    assert not r2.changed and r2.transition == 0
    r3 = r.resolve("no_such_scene")       # 缺失 → 保持当前
    assert not r3.changed and r3.scene_id == "class_room"
    r4 = r.resolve(None)                  # 纯文本模式 → 保持
    assert not r4.changed and r4.scene_id == "class_room"
    r.reset()                             # 重置 → 重新切换
    r5 = r.resolve("class_room")
    assert r5.changed
    print("    background: 切换→保持→缺失保持→重置")


def test_background_result_frozen():
    br = BackgroundResult("a", None, 0.0, False)
    assert br.scene_id == "a" and not br.changed
    print("    background: Result 数据类")


# ----------------------------------------------------------------------------
# SpriteResolver: 确定性延续 + 词表外降级
# ----------------------------------------------------------------------------

def test_sprite_emotion_continuation(tmp_path):
    c = _catalog(tmp_path)
    r = SpriteResolver("igusa_haruka", c)
    seq = r.emotions([
        {"text": "a"},                      # 首段缺省 → 默认（词表首项）
        {"text": "b", "emotion": "smile"},
        {"text": "c"},                      # 缺省 → 延续 smile
        {"text": "d", "emotion": "not_in_table"},   # 词表外 → 保持 smile
        {"text": "e", "emotion": "embarrass"},
    ])
    assert seq == ["nomal", "smile", "smile", "smile", "embarrass"], seq
    assert r.emotions([]) == []
    print("    sprite: 首段默认 + 缺省延续 + 词表外保持")


# ----------------------------------------------------------------------------
# EffectResolver: 查表（全局 + 角色覆盖 + 缺省）
# ----------------------------------------------------------------------------

def test_effects_global_table_and_missing():
    r = EffectResolver()
    assert r.resolve(["smile"]) == [["sparkle"]]
    assert r.resolve(["embarrass"]) == [["blush", "notes"]]
    assert r.resolve(["nomal"]) == [[]]            # 缺省 → 无
    assert r.resolve(["no_such"]) == [[]]          # 未知 → 无
    assert r.resolve([None]) == [[]]
    assert r.effects_for("love") == ["heart"]
    assert r.effects_for(None) == []
    print("    effects: 全局查表 + 未知/None → 空")


def test_effects_character_override(tmp_path):
    ch = tmp_path / "assets" / "illustration" / "igusa_haruka"
    ch.mkdir(parents=True)
    (ch / "effects.yml").write_text(
        "shy: [blush, notes, petal]\n"
        "smile: 星星,闪闪\n",                      # 值兼容逗号分隔字符串
        encoding="utf-8",
    )
    r = EffectResolver(ch)
    assert r.resolve(["shy"]) == [["blush", "notes", "petal"]]
    assert r.resolve(["smile"]) == [["星星", "闪闪"]]
    assert r.resolve(["angry"]) == [["anger"]]     # 未覆盖 → 全局兜底
    assert EffectResolver(tmp_path / "nope").resolve(["smile"]) == [["sparkle"]]
    print("    effects: 角色表优先 + 全局兜底 + 缺失文件兜底")


# ----------------------------------------------------------------------------
# Renderer 管线: 同构（from_live == from_event）+ 完整输出
# ----------------------------------------------------------------------------

def test_render_pipeline_isomorphic(tmp_path):
    payload = {
        "paragraphs": [{"text": "天台的风好舒服。", "emotion": "smile"},
                       {"text": "（她低头抿嘴）"}],
        "choices": ["走过去"], "is_end": False, "background": "class_room",
    }

    class FakeScene:
        def to_dict(self): return payload

    # 同构验证用两个独立 Renderer——背景切换状态机不跨实例（回放=实时"看到的画面"一致）
    out_live = Renderer("igusa_haruka", _make_assets(tmp_path)).render(
        RenderScene.from_live(FakeScene()))
    out_ev = Renderer("igusa_haruka", _make_assets(tmp_path)).render(
        RenderScene.from_event(payload))
    assert out_live.background == out_ev.background
    assert out_live.sprites == out_ev.sprites == ["smile", "smile"]
    assert out_live.effects == out_ev.effects == [["sparkle"], ["sparkle"]]
    assert out_live.choices == ["走过去"] and not out_live.is_end
    assert out_ev.audio is None
    print("    pipeline: from_live/from_event 同构（回放=实时）")


def test_render_pipeline_end_and_audio(tmp_path):
    r = Renderer("igusa_haruka", _make_assets(tmp_path))
    out = r.render(RenderScene.from_event({
        "paragraphs": [{"text": "再见。"}], "choices": [],
        "is_end": True, "audio": "bgm_ending"}))
    assert out.is_end and not out.choices
    assert isinstance(out.audio, AudioRequest) and out.audio.asset == "bgm_ending"
    print("    pipeline: is_end 透传 + audio 指令")


# ----------------------------------------------------------------------------
# RenderState: 状态机推进
# ----------------------------------------------------------------------------

def test_render_state_machine():
    st = RenderState()
    assert st.phase == "idle"
    st.begin_scene(background="class_room", transition=0.5,
                   sprite_stack=["nomal", "smile"], effects=[["sparkle"]],
                   choices=["A"], is_end=False)
    assert st.phase == "scene_playing" and st.paragraph_index == -1
    st.advance_paragraph()                 # 段落 0
    assert st.paragraph_index == 0 and st.sprite == "nomal"
    st.advance_paragraph()                 # 段落 1（末尾）
    assert st.paragraph_index == 1 and st.sprite == "smile"
    st.advance_paragraph()                 # 已到末尾 → CHOICE
    assert st.phase == "choice"
    st.resolve_choice()
    assert st.phase == "next"
    st.begin_scene(background=None, transition=0.0, sprite_stack=["nomal"],
                   effects=[[]], choices=[], is_end=True)
    st.advance_paragraph()
    st.advance_paragraph()                 # 末尾 + is_end → END
    assert st.phase == "end"
    print("    state: PLAYING→CHOICE→NEXT / PLAYING→END")


# ----------------------------------------------------------------------------
# CLI 输出: 特效符号 / 选项渲染
# ----------------------------------------------------------------------------

def test_cli_fx_symbol():
    assert _fx_symbol(["sparkle"]) == "✨"
    assert _fx_symbol(["blush", "notes"]) == "🌸♪"
    assert _fx_symbol(["unknown_fx"]) == "✨"      # 未知 → 通用符号
    assert _fx_symbol([]) == ""
    print("    cli: 特效符号映射")


def test_cli_render_choices(capsys):
    render_choices(["走过去", "喊她"])
    out = capsys.readouterr().out
    assert "  [1] 走过去" in out and "  [2] 喊她" in out
    assert "当时的选择" not in out and "退出" in out
    render_choices(["走过去"], picked="走过去")
    out2 = capsys.readouterr().out
    assert "←（当时的选择）" in out2 and "退出" not in out2
    print("    cli: 选项编号 + picked 高亮 + 退出提示")


def test_cli_read_choice_and_free():
    from renderer.cli import read_choice, read_free_input
    assert read_choice(["A", "B"], input_fn=lambda p: "2") == "B"
    assert read_choice(["A"], input_fn=lambda p: "b") is None
    # 无效输入重试（第一次 "9" 无效 → 第二次 "1" 有效）
    calls = {"n": 0}
    def retry(prompt=""):
        calls["n"] += 1
        return "9" if calls["n"] == 1 else "1"
    assert read_choice(["A"], input_fn=retry) == "A" and calls["n"] == 2
    assert read_free_input(input_fn=lambda p: "走吧") == "走吧"
    assert read_free_input(input_fn=lambda p: "b") is None
    print("    cli: 选项读取 + 无效重试 + 自由输入 + 退出")


# ----------------------------------------------------------------------------
# sprite_player: 播放层双 API
# ----------------------------------------------------------------------------

def test_sprite_player_diff_and_spine(tmp_path):
    from core.media.sprite_player import SpritePlayer
    assets = _make_assets(tmp_path)
    sp = SpritePlayer(assets)
    diff = sp.play_diff("igusa_haruka", "smile")
    assert diff is not None and diff.static_path is not None
    assert diff.static_path.name == "haruka_spr_03.png"
    assert sp.play_diff("igusa_haruka", "nope") is None     # 未知情绪 → None
    assert sp.play_spine("igusa_haruka", "smile") is None   # 无 spine 资产 → None
    assert sp.emotions("igusa_haruka") == ["embarrass", "nomal", "respond",
                                           "serious", "shout", "smile"]
    print("    sprite_player: play_diff 查图 + 缺失 None + 白名单")
