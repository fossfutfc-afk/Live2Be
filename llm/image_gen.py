# -*- coding: utf-8 -*-
"""生图接口 — 本地 SD 模型调用封装（llm/ 板块, 支持 SD1.5 + SDXL + IP-Adapter 参考图）。

与 LLMClient 同风格：从 .env 读配置、构造时可覆盖、统一 err() 错误格式。
**懒加载**：diffusers/torch 在首次 generate 才 import + 加载模型（pipe 加载
SD1.5 ~10s / SDXL ~15s），import 本模块不触发。

**模型自动识别**（按 model_index.json）:
    - 含 text_encoder_2 → SDXL（StableDiffusionXLPipeline, 原生 1024）
    - 否则 → SD1.5（StableDiffusionPipeline, 512）
SDXL 下自动: fp16 + enable_model_cpu_offload（8G 显存跑 1024）+ VAE slicing/tiling
+ 动漫质量标签前缀（masterpiece, best quality, anime style）+ 默认动漫 negative。
SD1.5 保持原行为（512, 无自动前缀/negative, 兼容旧调用）。

**IP-Adapter（角色参考图一致性, 2026-08-24）**:
    generate(ref_images=[...]) → 首次加载 ip-adapter-plus_sdxl_vit-h（本地
    h94/IP-Adapter 结构, 含 CLIP-ViT-H image encoder）→ 生成时 ip_adapter_image
    注入角色外观特征（ref 三张图: 立绘/光环/官方 L2D）。仅 SDXL 支持
    （SD1.5 传 ref_images → 忽略并 warning）。

配置（.env，均可构造时覆盖）:
    IMAGE_MODEL_PATH       本地 SD 模型目录（默认 SD1.5 路径; 指向 SDXL 目录即自动切换）
    IMAGE_OUTPUT_DIR       生成图输出目录（默认 D:\\by-user\\fossf\\AI\\output）
    IMAGE_IP_ADAPTER_PATH  IP-Adapter 模型目录（默认 D:\\by-user\\fossf\\AI\\models\\IP-Adapter）

用法:
    from llm.image_gen import ImageGenerator
    gen = ImageGenerator()   # 默认 SD1.5
    gen2 = ImageGenerator(model_path=r"D:\by-user\fossf\AI\models\animagine-xl-4.0")
    path = gen2.generate("purple hair girl, weeds, sunset, anime style", seed=42,
                         ref_images=[r"assets\illustration\igusa_haruka\ref\haruka_spr_00.png",
                                     r"assets\illustration\igusa_haruka\ref\Haruka_Original_Halo.png"])
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from core.common import err

logger = logging.getLogger(__name__)

# 默认路径（.env 注释的既有约定; 无变量时兜底）
_DEFAULT_MODEL = r"D:\by-user\fossf\AI\models\AI-ModelScope\stable-diffusion-v1-5"
_DEFAULT_OUTPUT = r"D:\by-user\fossf\AI\output"
_DEFAULT_IP_ADAPTER = r"D:\by-user\fossf\AI\models\IP-Adapter"

#: SDXL 动漫质量标签前缀（Animagine 4.0 等 SDXL 动漫模型的质量体系）
_SDXL_QUALITY_PREFIX = "masterpiece, best quality, anime style, "
#: SDXL 默认动漫 negative（通用画质缺陷; 模型通常还建议补 anatomy 类, 按需传 negative_prompt 覆盖）
_SDXL_NEGATIVE = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
    "fewer digits, cropped, worst quality, low quality, normal quality, "
    "jpeg artifacts, signature, watermark, username, blurry"
)
#: IP-Adapter 权重（角色 ref 图一致性; SDXL 的 plus 变体, 含 vit-h image encoder）
#: 双 adapter: plus=整体外观参考, plus-face=脸部特写参考（diffusers 每 adapter 一张图）
_IP_ADAPTER_WEIGHTS = ("ip-adapter-plus_sdxl_vit-h.safetensors",
                       "ip-adapter-plus-face_sdxl_vit-h.safetensors")
_IP_ADAPTER_SUBFOLDER = "sdxl_models"
_IP_ADAPTER_ENCODER_FOLDER = "models/image_encoder"
_IP_ADAPTER_SCALE = 0.6          # ref 图特征强度（0.5~0.8; 太低角色不像, 太高构图被锁死）


class ImageGenerator:
    """本地 SD 生图客户端（懒加载 pipe, 单例复用; SD1.5/SDXL 自动识别 + IP-Adapter）。

    构造不加载模型——首次 generate()/warmup() 才 import torch/diffusers 并
    from_pretrained（pipe 可复用, 多次生成只加载一次）。
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        output_dir: str | Path | None = None,
        device: str = "auto",
        offline: bool = True,
        ip_adapter_path: str | Path | None = None,
    ):
        self.model_path = Path(
            model_path or os.getenv("IMAGE_MODEL_PATH", _DEFAULT_MODEL))
        self.output_dir = Path(
            output_dir or os.getenv("IMAGE_OUTPUT_DIR", _DEFAULT_OUTPUT))
        self.ip_adapter_path = Path(
            ip_adapter_path or os.getenv("IMAGE_IP_ADAPTER_PATH", _DEFAULT_IP_ADAPTER))
        self.device = device
        self.offline = offline          # local_files_only + HF_HUB_OFFLINE（本地模型）
        self._pipe = None               # 懒加载: 首次 generate/warmup 才载入
        self._device = "cpu"
        self._is_sdxl = False           # 模型类型（_load_pipe 时定）
        self._default_size = 512        # 原生分辨率（SDXL=1024, SD1.5=512）
        self._ip_loaded = False         # IP-Adapter 已加载（ref 首次需要时加载）
        self._lock = threading.Lock()   # pipe/ip-adapter 懒加载并发安全（预热线程 + 生成）

    # ------------------------------------------------------------------
    # 懒加载
    # ------------------------------------------------------------------

    def _is_sdxl_model(self) -> bool:
        """按 model_index.json 识别 SDXL（有 text_encoder_2 = 双文本编码器）。"""
        try:
            import json
            idx = json.loads(
                (self.model_path / "model_index.json").read_text(encoding="utf-8"))
            return "text_encoder_2" in idx
        except Exception:                    # noqa: BLE001 — 识别失败按 SD1.5 走
            return False

    def _load_pipe(self):
        """载入生图 pipeline（fp16 + CUDA/CPU, 禁 safety_checker; SDXL 加 8G 显存优化）。

        返回后缓存复用; 模型目录缺失 / diffusers 未装 → 明确报错（宁缺勿错）。
        双检锁: 后台预热线程与生成线程并发调用安全（只加载一次）。
        """
        if self._pipe is not None:
            return self._pipe
        with self._lock:
            if self._pipe is not None:          # 预热线程可能已加载完
                return self._pipe
            if not self.model_path.is_dir():
                raise RuntimeError(err(
                    "ImageGen", f"SD 模型目录不存在: {self.model_path}。"
                    "请在 .env 配 IMAGE_MODEL_PATH 或确认模型已下载"))
            try:
                import torch
                from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline
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

            self._is_sdxl = self._is_sdxl_model()
            pipe_cls = StableDiffusionXLPipeline if self._is_sdxl else StableDiffusionPipeline
            pipe = pipe_cls.from_pretrained(
                str(self.model_path),
                torch_dtype=torch_dtype,
                safety_checker=None,          # 本地自用, 跳过审核（.env 注释约定）
                local_files_only=self.offline,
            )
            if self._is_sdxl:
                self._default_size = 1024
                # 8G 显存: 非必要层放 CPU + VAE 分片/平铺（1024 生成不 OOM）
                pipe.enable_model_cpu_offload()
                pipe.enable_vae_slicing()
                pipe.enable_vae_tiling()
            else:
                self._default_size = 512
                pipe.to(device)               # SD1.5: 整体搬显存（原行为）
                pipe.enable_attention_slicing()
            self._pipe = pipe
            self._device = device
            return self._pipe

    # ------------------------------------------------------------------
    # 预热
    # ------------------------------------------------------------------

    def warmup(self) -> None:
        """预热 pipe（后台线程调用）: 提前加载模型到显存。

        首次生成从 ~15s（SDXL 加载）降到 ~3s（复用）——trigger 后立即预热,
        memorial_enter 轮当场生图时玩家几乎无感知。失败静默降级
        （模型缺失/无 GPU → 记 warning, 生成时会重试并明确报错）。
        """
        try:
            self._load_pipe()
        except Exception as e:                     # noqa: BLE001 — 预热失败不阻断
            logger.warning("生图 pipe 预热失败（生成时将重试）: %s", e)

    # ------------------------------------------------------------------
    # IP-Adapter（角色 ref 图一致性; 仅 SDXL）
    # ------------------------------------------------------------------

    def _load_ip_adapter(self):
        """加载 IP-Adapter（plus + plus-face 双权重 + CLIP-ViT-H encoder）。

        本地路径加载（h94/IP-Adapter 目录结构）; 失败明确报错。线程安全（双检锁）。
        双 adapter → generate 时 ip_adapter_image 传 [外观图, 脸部图]（各一张）。
        """
        if self._ip_loaded:
            return
        if not self._is_sdxl:
            logger.warning("IP-Adapter 仅 SDXL 支持, 已忽略 ref_images")
            return
        with self._lock:
            if self._ip_loaded:
                return
            for weight in _IP_ADAPTER_WEIGHTS:
                if not (self.ip_adapter_path / _IP_ADAPTER_SUBFOLDER / weight).is_file():
                    raise RuntimeError(err(
                        "ImageGen", f"IP-Adapter 权重缺失: {self.ip_adapter_path}. "
                        "请下载 h94/IP-Adapter（含 sdxl_models/*.safetensors）"))
            try:
                # list 形式一次加载双 adapter（分两次调用会被后者覆盖）
                self._pipe.load_ip_adapter(
                    [str(self.ip_adapter_path)] * len(_IP_ADAPTER_WEIGHTS),
                    subfolder=[_IP_ADAPTER_SUBFOLDER] * len(_IP_ADAPTER_WEIGHTS),
                    weight_name=list(_IP_ADAPTER_WEIGHTS),
                    image_encoder_folder=_IP_ADAPTER_ENCODER_FOLDER,
                )
                # 每 adapter 一个 scale（list; 双 adapter = 外观/脸部各自强度）
                self._pipe.set_ip_adapter_scale([_IP_ADAPTER_SCALE] * len(_IP_ADAPTER_WEIGHTS))
                # cpu_offload 不管 image_encoder（独立模块）——加载后默认在 CPU,
                # 生成时 CUDA 输入会报"Input type/weight type 不一致"。手动搬上卡。
                self._pipe.image_encoder.to(self._device)
            except Exception as e:                 # noqa: BLE001 — 明确报错
                raise RuntimeError(err(
                    "ImageGen", f"IP-Adapter 加载失败: {e}")) from e
            self._ip_loaded = True

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        height: int | None = None,
        width: int | None = None,
        guidance_scale: float = 7.5,
        steps: int = 20,
        seed: int | None = None,
        ref_images: list[str | Path] | None = None,
    ) -> Path:
        """生成一张图并保存到输出目录, 返回文件路径（l2d 事件的资产引用）。

        height/width 缺省 → 按模型原生分辨率（SDXL 1024 / SD1.5 512）。
        negative_prompt 缺省 → SDXL 用默认动漫 negative; SD1.5 保持 None（原行为）。
        SDXL 自动加动漫质量前缀（masterpiece, best quality, anime style）。
        ref_images（IP-Adapter 参考图, 仅 SDXL）→ 注入角色外观特征（角色一致性）。

        seed 固定 → 可复现（同 prompt 同 seed 同图）; None = 随机。
        文件名: gen_{ts}_{seed}.png（seed 为 None 时用 4 位随机后缀）。
        """
        import torch  # noqa: PLC0415 — 与 _load_pipe 同层懒加载

        if not prompt.strip():
            raise ValueError(err("ImageGen", "prompt 不能为空"))

        pipe = self._load_pipe()

        kwargs: dict = {}
        if ref_images:
            self._load_ip_adapter()
            if self._ip_loaded:
                try:
                    from PIL import Image
                    # 双 adapter: [0]=外观参考(plus), [1]=脸部参考(plus-face); 多余忽略
                    imgs = [Image.open(p).convert("RGB") for p in ref_images[:2]]
                    if len(ref_images) > 2:
                        logger.warning("ref_images 超过 2 张, 只取前 2（外观+脸部）")
                    kwargs["ip_adapter_image"] = imgs if len(imgs) > 1 else imgs[0]
                except Exception as e:                 # noqa: BLE001 — ref 图读不了降级纯文本
                    logger.warning("ref 图读取失败, 本次无角色参考: %s", e)

        if self._is_sdxl:
            prompt = _SDXL_QUALITY_PREFIX + prompt
            if negative_prompt is None:
                negative_prompt = _SDXL_NEGATIVE
        h = height or self._default_size
        w = width or self._default_size

        generator = None
        seed_label = "rand"
        if seed is not None:
            generator = torch.Generator(device=self._device).manual_seed(seed)
            seed_label = str(seed)

        img = pipe(
            prompt,
            negative_prompt=negative_prompt,
            height=h,
            width=w,
            guidance_scale=guidance_scale,
            num_inference_steps=steps,
            generator=generator,
            **kwargs,
        ).images[0]

        self.output_dir.mkdir(parents=True, exist_ok=True)
        out = self.output_dir / f"gen_{datetime.now():%Y%m%d_%H%M%S}_{seed_label}.png"
        img.save(out)
        return out

    # 便捷属性（懒加载入口, 测试断言用）
    @property
    def pipe(self):
        return self._pipe
