# -*- coding: utf-8 -*-
"""生图接口 — 本地 SD1.5（diffusers + CUDA）调用封装（llm/ 板块）。

与 LLMClient 同风格：从 .env 读配置、构造时可覆盖、统一 err() 错误格式。
**懒加载**：diffusers/torch 在首次 generate 才 import + 加载模型（pipe 加载 ~10s），
import 本模块不触发——避免无 GPU 环境或未用到时白白加载几百 MB。

配置（.env，均可构造时覆盖）:
    IMAGE_MODEL_PATH   本地 SD 模型目录（默认 D:\\by-user\\fossf\\AI\\models\\AI-ModelScope\\stable-diffusion-v1-5）
    IMAGE_OUTPUT_DIR   生成图输出目录（默认 D:\\by-user\\fossf\\AI\\output）

用法:
    from llm.image_gen import ImageGenerator
    gen = ImageGenerator()
    path = gen.generate("anime girl, night sky, holding a flower pot", seed=42)
    print(path)  # D:\\...\\gen_20260823_183000_42.png

与存档对接: 返回的 Path 即 l2d 事件的资产引用（events payload 引用式最小）。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from core.common import err

# 默认路径（.env 注释的既有约定; 无变量时兜底）
_DEFAULT_MODEL = r"D:\by-user\fossf\AI\models\AI-ModelScope\stable-diffusion-v1-5"
_DEFAULT_OUTPUT = r"D:\by-user\fossf\AI\output"


class ImageGenerator:
    """本地 SD1.5 生图客户端（懒加载 pipe, 单例复用）。

    构造不加载模型——首次 generate() 才 import torch/diffusers 并 from_pretrained
    （pipe 可复用, 多次生成只加载一次）。
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        output_dir: str | Path | None = None,
        device: str = "auto",
        offline: bool = True,
    ):
        self.model_path = Path(
            model_path or os.getenv("IMAGE_MODEL_PATH", _DEFAULT_MODEL))
        self.output_dir = Path(
            output_dir or os.getenv("IMAGE_OUTPUT_DIR", _DEFAULT_OUTPUT))
        self.device = device
        self.offline = offline          # local_files_only + HF_HUB_OFFLINE（本地模型）
        self._pipe = None               # 懒加载: 首次 generate 才载入

    # ------------------------------------------------------------------
    # 懒加载
    # ------------------------------------------------------------------

    def _load_pipe(self):
        """载入 StableDiffusionPipeline（float16 + CUDA/CPU, 禁 safety_checker）。

        返回后缓存复用; 模型目录缺失 / diffusers 未装 → 明确报错（宁缺勿错）。
        """
        if self._pipe is not None:
            return self._pipe
        if not self.model_path.is_dir():
            raise RuntimeError(err(
                "ImageGen", f"SD 模型目录不存在: {self.model_path}。"
                "请在 .env 配 IMAGE_MODEL_PATH 或确认模型已下载"))
        try:
            import torch
            from diffusers import StableDiffusionPipeline
        except ImportError as e:
            raise RuntimeError(err(
                "ImageGen", f"diffusers/torch 未安装: {e}（pip install diffusers torch）")) from e

        if self.offline:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        if self.device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = self.device
        torch_dtype = torch.float16 if device == "cuda" else torch.float32

        pipe = StableDiffusionPipeline.from_pretrained(
            str(self.model_path),
            torch_dtype=torch_dtype,
            safety_checker=None,          # 本地自用, 跳过审核（.env 注释约定）
            local_files_only=self.offline,
        )
        pipe.to(device)                   # from_pretrained 默认留 CPU, 必须显式搬
        pipe.enable_attention_slicing()
        self._pipe = pipe
        self._device = device
        return self._pipe

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        height: int = 512,
        width: int = 512,
        guidance_scale: float = 7.5,
        steps: int = 20,
        seed: int | None = None,
    ) -> Path:
        """生成一张图并保存到输出目录, 返回文件路径（l2d 事件的资产引用）。

        seed 固定 → 可复现（同 prompt 同 seed 同图）; None = 随机。
        文件名: gen_{ts}_{seed}.png（seed 为 None 时用 4 位随机后缀）。
        """
        import torch  # noqa: PLC0415 — 与 _load_pipe 同层懒加载

        if not prompt.strip():
            raise ValueError(err("ImageGen", "prompt 不能为空"))

        pipe = self._load_pipe()

        generator = None
        seed_label = "rand"
        if seed is not None:
            generator = torch.Generator(device=self._device).manual_seed(seed)
            seed_label = str(seed)

        img = pipe(
            prompt,
            negative_prompt=negative_prompt,
            height=height,
            width=width,
            guidance_scale=guidance_scale,
            num_inference_steps=steps,
            generator=generator,
        ).images[0]

        self.output_dir.mkdir(parents=True, exist_ok=True)
        out = self.output_dir / f"gen_{datetime.now():%Y%m%d_%H%M%S}_{seed_label}.png"
        img.save(out)
        return out

    # 便捷属性（懒加载入口, 测试断言用）
    @property
    def pipe(self):
        return self._pipe
