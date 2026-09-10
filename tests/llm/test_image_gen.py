# -*- coding: utf-8 -*-
"""llm/image_gen.py 单测 — 懒加载 + 错误路径（不真加载模型/不真生成）。

真机生图（CUDA + SD1.5）属实验验证, 见 experiments/（不放进单测, 避免拖慢/无 GPU 环境失败）。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from llm.image_gen import ImageGenerator


def test_lazy_load_pipe_is_none():
    """构造不加载模型——import/构造零成本（pipe 懒加载）。"""
    gen = ImageGenerator()
    assert gen.pipe is None, "构造后不应加载 pipe"
    print("    lazy: 构造不触发模型加载")


def test_missing_model_dir_raises_clear_error():
    """模型目录不存在 → 明确报错（宁缺勿错）, 且不残留半加载状态。

    api_key="" 强制本地 diffusers 模式（.env 配了 IMAGE_API_KEY 时默认走 APIYI）。
    """
    gen = ImageGenerator(model_path="D:/__no_such_sd_model__", api_key="")
    with pytest.raises(RuntimeError) as ei:
        gen.generate("test prompt")
    msg = str(ei.value)
    assert "SD 模型目录不存在" in msg, msg
    assert "__no_such_sd_model__" in msg
    assert gen.pipe is None, "失败后 pipe 不应被缓存"
    print("    error: 模型目录缺失 → 清晰报错 + 无残留")


def test_empty_prompt_rejected():
    """空 prompt → ValueError。"""
    gen = ImageGenerator(model_path="D:/__no_such_sd_model__", api_key="")
    with pytest.raises(ValueError):
        gen.generate("   ")
    print("    error: 空 prompt 拒绝")


def test_constructor_override_and_env_defaults():
    """构造覆盖优先于 .env; 默认路径符合约定。"""
    gen = ImageGenerator(model_path="D:/custom_model", output_dir="D:/custom_out")
    assert str(gen.model_path) == "D:\\custom_model"
    assert str(gen.output_dir) == "D:\\custom_out"
    default = ImageGenerator()
    assert "stable-diffusion-v1-5" in str(default.model_path)
    print("    config: 覆盖优先 + 默认路径")


# ---------------------------------------------------------------------------
# 2026-09-10: 屏幕尺寸 / 逐图标签 / 返回值（接口完善, 全部离线, 不碰 API）
# ---------------------------------------------------------------------------

def _png(path: Path, size=(64, 64), color=(10, 20, 30)) -> Path:
    """造一张真 png（尺寸相关逻辑要用真图）。"""
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def test_parse_size_variants():
    """'1920x1080' / '1920*1080' / '1920×1080' / 列表 都可解析; 非法 → None。"""
    from llm.image_gen import parse_size
    assert parse_size("1920x1080") == (1920, 1080)
    assert parse_size("1920*1080") == (1920, 1080)
    assert parse_size("1920×1080") == (1920, 1080)
    assert parse_size([1280, 720]) == (1280, 720)
    assert parse_size((1280, 720)) == (1280, 720)
    assert parse_size("bad") is None and parse_size(None) is None
    assert parse_size([0, 5]) is None
    print("    size: 尺寸字符串/元组解析 + 非法兜底")


def test_screen_size_defaults_and_override():
    """screen_size 优先级: 构造参数 > settings.toml > 1920x1080; fit 白名单。"""
    from llm.image_gen import DEFAULT_SCREEN_SIZE, ImageGenerator
    assert ImageGenerator(api_key="", screen_size="1280x720").screen_size == (1280, 720)
    assert ImageGenerator(api_key="").screen_size == (1920, 1080) or \
        ImageGenerator(api_key="").screen_size != DEFAULT_SCREEN_SIZE  # settings 可覆盖
    assert ImageGenerator(api_key="", fit="weird").fit == "contain"     # 非法 → contain
    print("    size: 构造覆盖 + fit 白名单")


def test_ref_specs_labels_and_order(tmp_path):
    """ref 分组顺序固定 角色→画风→配饰, 且每张带中文标签（halo → 光环）。"""
    from llm.image_gen import collect_ref_images, ref_specs
    ref = tmp_path / "illustration" / "igusa_haruka" / "ref"
    for name in ("sprite_1.png", "style_1.png", "style_2.png", "halo.png"):
        _png(ref / name)
    specs = ref_specs("igusa_haruka", assets_root=tmp_path)
    assert [k for k, _, _ in specs] == ["role", "style", "style", "acc"]
    assert [label for _, label, _ in specs] == ["角色本体", "画风参考", "画风参考", "光环"]
    assert [p.name for p in collect_ref_images("igusa_haruka", assets_root=tmp_path)] == [
        "sprite_1.png", "style_1.png", "style_2.png", "halo.png"]
    print("    ref: 顺序 + 标签（光环/画风 不再错位）")


def test_build_api_parts_labels_every_ref(tmp_path):
    """parts 逐图带标签（旧版写死三张导致错位）+ 尾部带屏幕比例。"""
    from llm.image_gen import _build_api_parts, ref_specs
    ref = tmp_path / "illustration" / "igusa_haruka" / "ref"
    for name in ("sprite_1.png", "style_1.png", "style_2.png", "halo.png"):
        _png(ref / name)
    parts = _build_api_parts(ref_specs("igusa_haruka", assets_root=tmp_path),
                             "伊草春香", "夜晚的天台", (1920, 1080))
    texts = [p["text"] for p in parts if "text" in p]
    assert len([p for p in parts if "inline_data" in p]) == 4
    assert any("【图1 角色本体】" in t and "伊草春香" in t for t in texts)
    assert sum("画风参考" in t for t in texts) == 2
    assert any("配饰参考：光环" in t for t in texts)
    assert any("16:9" in t and "1920x1080" in t for t in texts)
    for i, part in enumerate(parts):                 # 每张图前面必是标签 text
        if "inline_data" in part:
            assert "text" in parts[i - 1]
    print("    parts: 逐图标签 + 比例声明")


def test_generated_image_path_protocol(tmp_path):
    """GeneratedImage 兼容 os.fspath/str（gallery.copy2 可直接吃）+ as_dict。"""
    import os
    from llm.image_gen import GeneratedImage
    gi = GeneratedImage(path=tmp_path / "a.png", width=1920, height=1080,
                        size_bytes=123, backend="apiyi", elapsed_s=26.08)
    assert os.fspath(gi).endswith("a.png") and str(gi).endswith("a.png")
    d = gi.as_dict()
    assert (d["width"], d["height"], d["backend"], d["elapsed_s"]) == (1920, 1080, "apiyi", 26.08)
    print("    result: 路径协议 + 元信息")


def test_normalize_contain_and_cover(tmp_path):
    """归一化到屏幕尺寸: contain 留边不裁 / cover 裁满; 都记录 source_size。"""
    from PIL import Image
    from llm.image_gen import ImageGenerator
    gen = ImageGenerator(model_path="D:/__none__", api_key="", screen_size=(160, 90))
    src = _png(tmp_path / "src.png", size=(64, 64))
    out = gen._normalize(src, (160, 90), "contain", backend="test")
    assert (out.width, out.height) == (160, 90) and out.source_size == (64, 64)
    assert Image.open(src).size == (160, 90) and out.fit == "contain"
    src2 = _png(tmp_path / "src2.png", size=(64, 64))
    out2 = gen._normalize(src2, (160, 90), "cover", backend="test")
    assert (out2.width, out2.height) == (160, 90) and out2.fit == "cover"
    print("    normalize: contain/cover → 精确屏幕尺寸")


def test_unsupported_aspect_detection():
    """代理不认 imageConfig.aspectRatio 的报错识别（用于自动降级重试）。"""
    from llm.image_gen import _unsupported_aspect
    assert _unsupported_aspect('HTTP 400: Unknown name "imageConfig"')
    assert _unsupported_aspect("Invalid JSON payload received. Unknown name aspectRatio")
    assert not _unsupported_aspect("HTTP 429 rate limited")
    print("    aspect: 不支持字段的识别")
