# -*- coding: utf-8 -*-
"""llm/image_gen.py 单测 — 单后端（APIYI）接口契约, 全部离线, 不碰 API。

覆盖:
    1. 配置解析（output_dir 覆盖 / 尺寸解析 / fit 白名单 / 未配 key 的明确报错）
    2. ref 命名约定 → (kind, 中文标签) 与顺序（角色 → 画风 → 配饰）
    3. 请求体拼装（逐图带标签 + 屏幕比例声明; 旧版写死三张导致光环错位）
    4. 返回值 GeneratedImage（路径协议 / 元信息 / 尺寸归一化 contain·cover）
    5. **生图总开关** `image_enabled()`（env > settings [image].enabled > 默认开）
       ——注意本套件整体跑在 `LIVE2BE_IMAGE=off` 下（tests/conftest.py 会话级
       autouse 硬关）, 所以凡是要走 `generate()` 正常路径的用例都要显式打开。
真机出图（APIYI 计费）属实验验证, 见 experiments/（不放进单测）。
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import llm.image_gen as ig  # noqa: E402
from llm.image_gen import (DEFAULT_SCREEN_SIZE, ENV_ALLOW_REAL, ENV_SWITCH,  # noqa: E402
                           GeneratedImage, ImageGenerator, _build_api_parts,
                           _settings_image_cfg, _unsupported_aspect,
                           collect_ref_images, image_dry_run, image_enabled,
                           parse_size, ref_specs)


def _png(path: Path, size=(64, 64), color=(10, 20, 30)) -> Path:
    """造一张真 png（尺寸相关逻辑要用真图）。"""
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


# ---------------------------------------------------------------------------
# 配置与错误路径
# ---------------------------------------------------------------------------

def test_no_api_key_raises_clear_error(monkeypatch):
    """未配 key → 明确报错（本地兜底已移除, 不静默降级）。

    显式打开总开关（套件默认 off）——本用例考的是"没 key"这条, 不是"被关闭"。
    """
    monkeypatch.setenv(ENV_SWITCH, "on")
    gen = ImageGenerator(api_key="")
    assert gen.is_api_mode is False
    with pytest.raises(RuntimeError) as ei:
        gen.generate("test prompt")
    msg = str(ei.value)
    assert "IMAGE_API_KEY" in msg and "本地 diffusers" in msg, msg
    print("    error: 无 key → 清晰报错（无本地兜底）")


def test_empty_prompt_rejected():
    """空 prompt → ValueError（先于后端判定）。"""
    gen = ImageGenerator(api_key="")
    with pytest.raises(ValueError):
        gen.generate("   ")
    print("    error: 空 prompt 拒绝")


def test_constructor_overrides_and_defaults():
    """output_dir / screen_size / fit 构造覆盖; 默认输出目录符合约定。"""
    gen = ImageGenerator(output_dir="D:/custom_out", api_key="", screen_size="1280x720",
                         fit="cover")
    assert str(gen.output_dir) == "D:\\custom_out"
    assert gen.screen_size == (1280, 720) and gen.fit == "cover"
    assert "fossf" in str(ImageGenerator(api_key="").output_dir)
    assert ImageGenerator(api_key="", fit="weird").fit == "contain"   # 非法 → contain
    assert ImageGenerator(api_key="", screen_size="bad").screen_size == \
        parse_size("1920x1080") or DEFAULT_SCREEN_SIZE
    print("    config: 覆盖优先 + fit 白名单 + 默认路径")


def test_parse_size_variants():
    """'1920x1080' / '1920*1080' / '1920×1080' / 列表 都可解析; 非法 → None。"""
    assert parse_size("1920x1080") == (1920, 1080)
    assert parse_size("1920*1080") == (1920, 1080)
    assert parse_size("1920×1080") == (1920, 1080)
    assert parse_size([1280, 720]) == (1280, 720)
    assert parse_size((1280, 720)) == (1280, 720)
    assert parse_size("bad") is None and parse_size(None) is None
    assert parse_size([0, 5]) is None
    print("    size: 尺寸字符串/元组解析 + 非法兜底")


def test_warmup_is_noop():
    """warmup 保留为兼容占位（CLI 后台线程仍调用; 本地 pipe 已移除）。"""
    assert ImageGenerator(api_key="").warmup() is None
    print("    warmup: 兼容占位, 无副作用")


# ---------------------------------------------------------------------------
# 生图总开关（2026-09-11: 跑测试/离线时确定性关掉, 不依赖"忘配 key"）
# ---------------------------------------------------------------------------

def test_env_switch_name_in_sync_with_conftest():
    """conftest 的硬关变量名必须与本模块一致（不同步 = 测试静默恢复真出图/烧钱）。"""
    from tests.conftest import _IMG_SWITCH
    assert ENV_SWITCH == _IMG_SWITCH == "LIVE2BE_IMAGE"


def test_image_enabled_precedence(monkeypatch):
    """env > settings [image].enabled > 默认开; 非法形态一律回默认开。"""
    monkeypatch.delenv(ENV_SWITCH, raising=False)
    assert image_enabled({}) is True                       # 缺字段 → 开
    assert image_enabled({"enabled": True}) is True
    assert image_enabled({"enabled": False}) is False
    assert image_enabled({"enabled": "no"}) is True        # 非 bool → 回默认
    for off in ("off", "0", "false", "FALSE", " no ", "Disabled"):
        monkeypatch.setenv(ENV_SWITCH, off)
        assert image_enabled({"enabled": True}) is False, off   # env 压过配置
    for on in ("on", "1", "true", "yes"):
        monkeypatch.setenv(ENV_SWITCH, on)
        assert image_enabled({"enabled": False}) is True, on    # env 反向也压过配置
    monkeypatch.setenv(ENV_SWITCH, "")                     # 空 = 未设 → 落配置
    assert image_enabled({"enabled": False}) is False
    print("    switch: env > settings > 默认开")


def test_image_enabled_reads_settings_file(monkeypatch, tmp_path):
    """真实文件路径分支: 项目根 settings.toml 的 [image].enabled 被读到。"""
    monkeypatch.delenv(ENV_SWITCH, raising=False)
    monkeypatch.setattr(ig, "_PROJECT_ROOT", tmp_path)
    assert _settings_image_cfg() == {} and image_enabled() is True   # 无文件 → 开
    (tmp_path / "settings.toml").write_text(
        "[image]\n  enabled = false\n  model = \"x\"\n", encoding="utf-8")
    assert _settings_image_cfg()["model"] == "x"
    assert image_enabled() is False
    (tmp_path / "settings.toml").write_text("[image\nbad", encoding="utf-8")
    assert _settings_image_cfg() == {} and image_enabled() is True   # 损坏 → 开
    print("    switch: settings.toml [image].enabled 生效 + 损坏回默认")


def test_disabled_generator_raises_and_declares_unavailable(monkeypatch):
    """关掉后: available=False（消费方据此不开线程）+ generate() 明确报错。"""
    monkeypatch.setenv(ENV_SWITCH, "off")
    gen = ImageGenerator(api_key="fake-key")
    assert gen.enabled is False
    assert gen.is_api_mode is True          # key 仍在——只是被开关否决
    assert gen.available is False
    with pytest.raises(RuntimeError) as ei:
        gen.generate("test prompt")
    assert "生图已关闭" in str(ei.value), ei.value
    monkeypatch.setenv(ENV_SWITCH, "on")
    assert ImageGenerator(api_key="fake-key").available is True
    assert ImageGenerator(api_key="").available is False     # 开关开但无 key → 不可用
    print("    switch: 关闭 → available=False + generate() 明确报错")


# ---------------------------------------------------------------------------
# 防误触计费（2026-09-11 真机事故）: 测试进程硬闸 + dry-run
# ---------------------------------------------------------------------------

def test_post_api_refuses_real_call_under_pytest(monkeypatch):
    """**唯一 HTTP 出口**在测试进程里必须拒绝（事故: 探针真的发了一次计费请求）。

    闸门在 `_post_api` 上（不是 generate），所以任何调用方——webgui 纪念线程、
    vn_cli、main、探针脚本——在 pytest 进程里都拦得住。
    """
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")           # 模拟测试进程
    monkeypatch.delenv(ENV_ALLOW_REAL, raising=False)
    gen = ImageGenerator(api_key="fake-key")
    with pytest.raises(RuntimeError) as ei:
        gen._post_api({})
    assert "测试进程禁止真实生图调用" in str(ei.value), ei.value
    # 显式放行（真机连通性用例）
    monkeypatch.setenv(ENV_ALLOW_REAL, "1")
    try:
        gen._post_api({})                                    # 会走到网络层 → 任何异常都行
    except RuntimeError as e:                                # pragma: no cover
        assert "测试进程禁止" not in str(e), e
    except Exception:                                        # noqa: BLE001 — 网络层报错可接受
        pass
    print("    guard: 测试进程拒绝真实生图（ALLOW_REAL=1 可显式放行）")


def test_dry_run_builds_request_without_http(monkeypatch):
    """dry（`LIVE2BE_IMAGE=dry`）: enabled 仍为真, 但只构造请求、不发 HTTP。

    返回占位 GeneratedImage（backend="dry"、不落盘）——探针/实验/调试零成本跑通
    生图代码路径（我就是缺这个才误触了一次真调用）。
    """
    monkeypatch.setenv(ENV_SWITCH, "dry")
    assert image_enabled() is True                           # dry 也算"开"
    assert image_dry_run() is True
    gen = ImageGenerator(api_key="fake-key")
    assert gen.dry_run is True and gen.enabled is True
    called = []
    monkeypatch.setattr(gen, "_post_api", lambda body: called.append(body))
    img = gen.generate("干跑测试")
    assert called == [], "dry-run 不得发 HTTP"
    assert img.backend == "dry" and (img.width, img.height) == (1920, 1080)
    assert not Path(img.path).is_file(), "dry-run 不落盘"
    monkeypatch.setenv(ENV_SWITCH, "on")
    assert image_dry_run() is False
    print("    dry: 构造请求但不发 HTTP（占位返回, 不落盘）")




# ---------------------------------------------------------------------------
# ref 命名约定
# ---------------------------------------------------------------------------

def test_ref_specs_labels_and_order(tmp_path):
    """ref 分组顺序固定 角色→画风→配饰, 且每张带中文标签（halo → 光环）。"""
    ref = tmp_path / "illustration" / "igusa_haruka" / "ref"
    for name in ("sprite_1.png", "style_1.png", "style_2.png", "halo.png"):
        _png(ref / name)
    specs = ref_specs("igusa_haruka", assets_root=tmp_path)
    assert [k for k, _, _ in specs] == ["role", "style", "style", "acc"]
    assert [label for _, label, _ in specs] == [
        "角色本体", "画风与质感基准", "画风与质感基准", "光环"]
    assert [p.name for p in collect_ref_images("igusa_haruka", assets_root=tmp_path)] == [
        "sprite_1.png", "style_1.png", "style_2.png", "halo.png"]
    print("    ref: 顺序 + 标签（光环/画风不再错位）")


def test_ref_specs_accepts_explicit_dir(tmp_path):
    """路径可变: 直接传 ref_dir 也按同一命名约定取图（以后换目录不用改标签体系）。"""
    ref = tmp_path / "somewhere" / "else" / "ref"
    _png(ref / "sprite_9.png")
    _png(ref / "halo.png")
    specs = ref_specs("igusa_haruka", ref_dir=ref)
    assert [k for k, _, _ in specs] == ["role", "acc"]
    assert specs[1][1] == "光环"
    assert ref_specs("igusa_haruka", ref_dir=tmp_path / "nope") == []
    print("    ref: 显式目录 + 命名约定复用")


# ---------------------------------------------------------------------------
# 请求体拼装
# ---------------------------------------------------------------------------

def test_build_api_parts_labels_every_ref(tmp_path):
    """parts 逐图带标签（旧版写死三张导致错位）+ 尾部带屏幕比例与反排版约束。"""
    ref = tmp_path / "illustration" / "igusa_haruka" / "ref"
    for name in ("sprite_1.png", "style_1.png", "style_2.png", "halo.png"):
        _png(ref / name)
    parts = _build_api_parts(ref_specs("igusa_haruka", assets_root=tmp_path),
                             "测试角色", "夜晚的天台，她转过头来微笑。", (1920, 1080))
    texts = [p["text"] for p in parts if "text" in p]
    assert len([p for p in parts if "inline_data" in p]) == 4
    assert any("【图1 角色本体】" in t and "测试角色" in t for t in texts)
    assert sum("画风与质感基准" in t for t in texts) == 2
    assert any("配饰：光环" in t and "悬浮于头顶上方" in t for t in texts)
    assert any("16:9" in t and "1920x1080" in t for t in texts)
    assert any("设定表" in t for t in texts)                  # 防参考图排版被抄成多视图
    for i, part in enumerate(parts):                          # 每张图前面必是标签 text
        if "inline_data" in part:
            assert "text" in parts[i - 1]
    print("    parts: 逐图标签 + 比例声明 + 反排版约束")


def test_unsupported_aspect_detection():
    """代理不认 imageConfig.aspectRatio 的报错识别（用于自动降级重试）。"""
    assert _unsupported_aspect('HTTP 400: Unknown name "imageConfig"')
    assert _unsupported_aspect("Invalid JSON payload received. Unknown name aspectRatio")
    assert not _unsupported_aspect("HTTP 429 rate limited")
    print("    aspect: 不支持字段的识别")


def test_ref_compression_before_upload(tmp_path):
    """ref_max_edge > 0 → 上传前压成 JPEG 且体积骤降; 再次构建命中缓存。"""
    ref = tmp_path / "illustration" / "igusa_haruka" / "ref"
    _png(ref / "sprite_1.png", size=(800, 2286))
    _png(ref / "style_1.png", size=(2560, 1440))
    cache = tmp_path / "cache"
    specs = ref_specs("igusa_haruka", assets_root=tmp_path)
    parts = _build_api_parts(specs, "测试角色", "场景", (1920, 1080),
                             ref_max_edge=256, ref_jpeg_quality=80, cache_dir=cache)
    imgs = [p["inline_data"] for p in parts if "inline_data" in p]
    assert len(imgs) == 2 and all(i["mime_type"] == "image/jpeg" for i in imgs)
    assert len(list(cache.glob("*.jpg"))) == 2
    raw_total = sum(p.stat().st_size for _, _, p in specs)
    b64_total = sum(len(i["data"]) for i in imgs)
    assert b64_total * 3 / 4 < raw_total / 4, (b64_total, raw_total)   # 至少降到 1/4
    parts2 = _build_api_parts(specs, "测试角色", "场景", (1920, 1080),
                              ref_max_edge=256, ref_jpeg_quality=80, cache_dir=cache)
    assert [p["inline_data"]["data"] for p in parts2 if "inline_data" in p] == \
        [i["data"] for i in imgs]                                      # 缓存命中
    print("    ref: 压缩上传 + 缓存复用")


def test_ref_compression_off_keeps_png(tmp_path):
    """ref_max_edge=0 → 原图原样上传（PNG, 无损; 默认关闭路径）。"""
    ref = tmp_path / "illustration" / "igusa_haruka" / "ref"
    _png(ref / "sprite_1.png", size=(200, 300))
    parts = _build_api_parts(ref_specs("igusa_haruka", assets_root=tmp_path),
                             "测试角色", "场景", (1920, 1080))
    imgs = [p["inline_data"] for p in parts if "inline_data" in p]
    assert imgs and all(i["mime_type"] == "image/png" for i in imgs)
    print("    ref: 关闭压缩 → 原图")


def test_halo_and_character_hints_injected(tmp_path):
    """角色生图提示: halo_hint 替换默认光环描述; character_hint 追加到角色本体标签。

    来源是 illustration.yml（CharacterLoader.load_illustration）——与 profile.yml 的
    halo 字段分开, 那边是给其他角色查阅的设定。
    """
    ref = tmp_path / "illustration" / "igusa_haruka" / "ref"
    _png(ref / "sprite_1.png")
    _png(ref / "halo.png")
    parts = _build_api_parts(ref_specs("igusa_haruka", assets_root=tmp_path),
                             "测试角色", "场景", (1920, 1080),
                             character_hint="紫色短发, 精灵耳发型",
                             halo_hint="三个互相分离的紫色钝角三角形")
    texts = [p["text"] for p in parts if "text" in p]
    assert any("补充设定：紫色短发" in t for t in texts)
    assert any("三个互相分离的紫色钝角三角形" in t for t in texts)
    assert not any("形状与颜色照图；光环悬浮" in t for t in texts)   # 默认光环提示被替换
    # 未给 hint 时回落默认（普适配饰路径不受影响）
    parts2 = _build_api_parts(ref_specs("igusa_haruka", assets_root=tmp_path),
                              "测试角色", "场景", (1920, 1080))
    assert any("悬浮于头顶上方" in p["text"] for p in parts2 if "text" in p)
    print("    hints: 角色补充设定 + 光环描述注入（缺省回落）")


# ---------------------------------------------------------------------------
# 返回值与尺寸归一化
# ---------------------------------------------------------------------------

def test_end_to_end_yml_hint_reaches_request_body(tmp_path, monkeypatch):
    """端到端: illustration.yml → CharacterLoader → generate → 真实请求体含该描述。

    这是"prompt 真的接进去了"的证据: 不调 API, 但抓的是最终 wire body。
    """
    import base64 as _b64
    import json as _json
    from io import BytesIO

    from PIL import Image

    from core.parsing.dynamic_character_parser import CharacterLoader
    import llm.image_gen as ig

    monkeypatch.setenv(ENV_SWITCH, "on")       # 套件默认 off——本用例要走真 generate()

    char_root = tmp_path / "characters"
    d = char_root / "test_char"
    d.mkdir(parents=True)
    (d / "profile.yml").write_text("REQ~most_called_name: 测试角色\n", encoding="utf-8")
    (d / "illustration.yml").write_text(
        "halo_hint: 三个互相分离的紫色钝角三角形\ncharacter_hint: 紫色短发\n",
        encoding="utf-8")
    ref = tmp_path / "assets" / "illustration" / "test_char" / "ref"
    _png(ref / "sprite_1.png")
    _png(ref / "halo.png")

    gen = ImageGenerator(api_key="test-key", output_dir=tmp_path / "out",
                         screen_size=(160, 90))
    monkeypatch.setattr(ig, "_ref_cache_dir", lambda: tmp_path / "cache")
    buf = BytesIO()
    Image.new("RGB", (1376, 768), (9, 9, 9)).save(buf, format="PNG")
    captured: dict = {}

    def fake_post(body):
        captured["body"] = body
        return {"candidates": [{"content": {"parts": [
            {"inlineData": {"data": _b64.b64encode(buf.getvalue()).decode()}}]}}]}

    monkeypatch.setattr(gen, "_post_api", fake_post)
    hints = CharacterLoader(char_root).load_illustration("test_char")
    img = gen.generate("夜晚的天台", ref_images=collect_ref_images("test_char", ref_dir=ref),
                       character_name="测试角色", **hints)
    wire = _json.dumps(captured["body"], ensure_ascii=False)
    assert "三个互相分离的紫色钝角三角形" in wire, "halo_hint 未进入请求体"
    assert "补充设定：紫色短发" in wire, "character_hint 未进入请求体"
    assert (img.width, img.height) == (160, 90) and img.source_size == (1376, 768)
    print("    e2e: illustration.yml → 请求体 → 落盘归一化")


def test_generated_image_path_protocol(tmp_path):
    """GeneratedImage 兼容 os.fspath/str（gallery.copy2 可直接吃）+ as_dict。"""
    gi = GeneratedImage(path=tmp_path / "a.png", width=1920, height=1080,
                        size_bytes=123, backend="apiyi", elapsed_s=26.08)
    assert os.fspath(gi).endswith("a.png") and str(gi).endswith("a.png")
    d = gi.as_dict()
    assert (d["width"], d["height"], d["backend"], d["elapsed_s"]) == \
        (1920, 1080, "apiyi", 26.08)
    print("    result: 路径协议 + 元信息")


def test_normalize_contain_and_cover(tmp_path):
    """归一化到屏幕尺寸: contain 留边不裁 / cover 裁满; 都记录 source_size。"""
    from PIL import Image
    gen = ImageGenerator(api_key="", screen_size=(160, 90))
    src = _png(tmp_path / "src.png", size=(64, 64))
    out = gen._normalize(src, (160, 90), "contain", backend="test")
    assert (out.width, out.height) == (160, 90) and out.source_size == (64, 64)
    assert Image.open(src).size == (160, 90) and out.fit == "contain"
    src2 = _png(tmp_path / "src2.png", size=(64, 64))
    out2 = gen._normalize(src2, (160, 90), "cover", backend="test")
    assert (out2.width, out2.height) == (160, 90) and out2.fit == "cover"
    same = _png(tmp_path / "same.png", size=(160, 90))
    out3 = gen._normalize(same, (160, 90), "contain", backend="test")
    assert (out3.width, out3.height) == (160, 90) and out3.fit == "none"   # 已是目标尺寸
    print("    normalize: contain/cover/原尺寸直通")
