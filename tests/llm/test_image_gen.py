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
