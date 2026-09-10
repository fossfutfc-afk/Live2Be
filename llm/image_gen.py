# -*- coding: utf-8 -*-
"""生图接口 — APIYI（Gemini 图像/nano banana, 推荐）+ 本地 diffusers（fallback）。

**双后端（2026-08-24）**:
    1. APIYI（Gemini 协议, 推荐）: 配了 IMAGE_API_KEY 即启用——多图 ref
       （角色/画风/配饰）+ 中文场景指令原生支持, 秒级出图（对比本地 SD 20 分钟）。
       协议: POST {base}/{api_version}/models/{model}:generateContent
       （Google GenAI SDK 风格; parts: inline_data 多图 + text 指令）。
    2. 本地 diffusers（SD1.5/SDXL + IP-Adapter）: 未配 IMAGE_API_KEY 时兜底
       （能力弱: 中文 prompt 是噪声、无画风参考、8G 显存极慢——不建议日常用）。

配置（.env, 均可构造时覆盖）:
    IMAGE_API_KEY        APIYI key（有值 → 走 APIYI 后端）
    IMAGE_API_BASE_URL   默认 https://api.apiyi.com
    IMAGE_MODEL          默认 gemini-3.1-flash-lite-image（Nano Banana 2 Lite）
    IMAGE_API_VERSION    默认 v1beta
    IMAGE_MODEL_PATH     本地 diffusers 模型目录（仅 fallback 用）
    IMAGE_OUTPUT_DIR     生成图输出目录（默认 D:\\by-user\\fossf\\AI\\output）
    IMAGE_IP_ADAPTER_PATH IP-Adapter 模型目录（仅本地 SDXL fallback 用）

**ref 命名约定（喂图顺序固定: 角色 → 画风 → 配饰）**:
    assets/illustration/{char_id}/ref/
        sprite_*.png     角色本体（可多张）
        style_*.png      画风示例（可多张）
        其余 png         配饰（光环/随身物品, 物品名即可, 如 halo.png）
    collect_ref_images(char_id) 按此分组排序返回; ref_specs(char_id) 另带
    (kind, 中文标签, path)——每张 ref 在请求里**逐图带标签**（2026-09-10 修:
    旧版写死"图1角色/图2画风/图3配饰", ref 超过 3 张时标签错位, 光环被画错）。

**目标尺寸 = 屏幕尺寸（2026-09-10 用户拍板）**:
    - 实测出图宽高比会**跟随第一张 ref**（sprite 800x2286 → 出图 608x1737 同比例）,
      故请求携带 generationConfig.imageConfig.aspectRatio = 屏幕比例;
      代理不支持该字段时自动去掉重试一次（不额外计费）。
    - 出图后归一化到 `screen_size`（settings.toml [image] screen_size, 默认 1920x1080）:
      fit="contain" 留边不裁内容（默认）/ "cover" 裁满屏 / "none" 不处理。
    - generate() 返回 GeneratedImage（path + width/height + source_size + 耗时等）。

用法:
    from llm.image_gen import ImageGenerator, collect_ref_images
    gen = ImageGenerator()                       # 配了 IMAGE_API_KEY → APIYI
    refs = collect_ref_images("igusa_haruka")
    img = gen.generate("她在湖边微笑，眼角带一滴泪，黄昏暖光，晚风拂过鬓发",
                       ref_images=refs, character_name="伊草 遥香")
    img.path, img.width, img.height             # 尺寸 = 屏幕尺寸
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from core.common import err

logger = logging.getLogger(__name__)

#: 项目根（llm/image_gen.py → Live2Be）; .env 模块级加载（同 llm/client.py 模式）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# 默认路径（.env 注释的既有约定; 无变量时兜底）
_DEFAULT_MODEL = r"D:\by-user\fossf\AI\models\AI-ModelScope\stable-diffusion-v1-5"
_DEFAULT_OUTPUT = r"D:\by-user\fossf\AI\output"
_DEFAULT_IP_ADAPTER = r"D:\by-user\fossf\AI\models\IP-Adapter"

#: 默认屏幕尺寸（生图目标 = 屏幕尺寸; settings.toml [image] screen_size 可覆盖）
DEFAULT_SCREEN_SIZE = (1920, 1080)
#: 配饰文件名 → 中文标签（未列出的直接用文件名主干, 保持通用）
_ACCESSORY_LABELS = {"halo": "光环", "weapon": "武器", "bag": "挎包", "gift": "礼物"}


def parse_size(value) -> tuple[int, int] | None:
    """'1920x1080' / '1920*1080' / '1920×1080' / [1920, 1080] → (1920, 1080); 非法 → None。"""
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            w, h = int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
        return (w, h) if w > 0 and h > 0 else None
    text = str(value).strip().lower().replace("×", "x").replace("*", "x")
    parts = [p for p in text.replace(" ", "").replace(",", "x").split("x") if p]
    if len(parts) != 2:
        return None
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return (w, h) if w > 0 and h > 0 else None


def _ratio_str(w: int, h: int) -> str:
    """(1920, 1080) → '16:9'（按最大公约数化简, 供 imageConfig.aspectRatio）。"""
    from math import gcd
    g = gcd(w, h) or 1
    return f"{w // g}:{h // g}"


@dataclass(frozen=True)
class GeneratedImage:
    """生图结果: 路径 + 尺寸 + 元信息（接口返回值; 兼容 os.fspath/str/copy2）。"""

    path: Path
    width: int
    height: int
    size_bytes: int = 0
    backend: str = ""                             # apiyi | diffusers
    elapsed_s: float = 0.0
    source_size: tuple[int, int] | None = None    # 归一化前的原始尺寸
    screen_size: tuple[int, int] | None = None    # 目标屏幕尺寸（未归一化 → None）
    fit: str = "none"                             # contain | cover | none

    def __fspath__(self) -> str:
        return str(self.path)

    def __str__(self) -> str:
        return str(self.path)

    def as_dict(self) -> dict:
        """事件/画廊元数据用（扁平, 可直接进 payload）。"""
        return {
            "path": str(self.path),
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
            "backend": self.backend,
            "elapsed_s": round(self.elapsed_s, 2),
            "source_size": list(self.source_size) if self.source_size else None,
            "screen_size": list(self.screen_size) if self.screen_size else None,
            "fit": self.fit,
        }

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

#: APIYI 固定框架（引擎侧拼接, 不依赖 LLM 每次写）——逐图标签动态生成（2026-09-10 修:
#: 旧版写死"图1角色/图2画风/图3配饰", ref 超过 3 张时标签错位 → 光环/风格都画错）
_APIYI_HEADER = "你是一位插画师，请根据以下参考图与要求生成一张图片。"
_APIYI_ROLE_LABEL = (
    '【图{n} 角色本体】图{n}是角色"{name}"的本体参考图。必须严格保持她的外观特征'
    "（发色/瞳色/发型/服装/标志物）——不要改动角色外观，不要擅自换装。"
)
_APIYI_STYLE_LABEL = (
    "【图{n} 画风参考】图{n}只提供绘画风格（上色方式/线条质感/渲染），"
    "不要采用其中人物的外貌与服装。"
)
_APIYI_ACC_LABEL = (
    "【图{n} 配饰参考：{acc}】图{n}是角色标志性配饰（{acc}）。"
    "按图{n}的形状与颜色绘制，位置正确（如光环位于头顶上方），半透明发光质感。"
)
_APIYI_TAIL = (
    "【场景指令】\n{scene}\n\n"
    "【输出要求】画面比例 {ratio}（屏幕尺寸 {w}x{h}），构图完整，高质量精细绘制，"
    "日系动画风格，人物表情自然，情绪到位。"
)


def _mime_of(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"


def _kind_label(path: Path) -> tuple[str, str]:
    """ref 文件名 → (kind, 中文标签): sprite_*=角色本体 / style_*=画风参考 / 其余=配饰。"""
    stem = path.stem
    low = stem.lower()
    if low.startswith("sprite"):
        return "role", "角色本体"
    if low.startswith("style"):
        return "style", "画风参考"
    return "acc", _ACCESSORY_LABELS.get(low, stem)


def _build_api_parts(specs: list[tuple[str, str, Path]], name: str, scene: str,
                     size: tuple[int, int] | None) -> list[dict]:
    """逐图带标签的 parts（标签 text 与 inline_data 交替）+ 场景指令尾。

    specs = [(kind, 中文标签, path)]（ref_specs() 或路径推断的结果）。
    """
    parts: list[dict] = [{"text": _APIYI_HEADER}]
    for i, (kind, label, path) in enumerate(specs, start=1):
        if kind == "role":
            text = _APIYI_ROLE_LABEL.format(n=i, name=name)
        elif kind == "style":
            text = _APIYI_STYLE_LABEL.format(n=i)
        else:
            text = _APIYI_ACC_LABEL.format(n=i, acc=label)
        parts.append({"text": text})
        parts.append({"inline_data": {"mime_type": _mime_of(path),
                                      "data": base64.b64encode(path.read_bytes()).decode()}})
    w, h = size or DEFAULT_SCREEN_SIZE
    parts.append({"text": _APIYI_TAIL.format(scene=scene, ratio=_ratio_str(w, h), w=w, h=h)})
    return parts


class ImageGenerator:
    """生图客户端（APIYI Gemini 后端为主; 未配 key → 本地 diffusers fallback）。

    APIYI 模式: 构造即就绪（无模型加载）, generate() 走 HTTP。秒级出图。
    本地模式: 懒加载 pipe（首次 generate/warmup 才 import torch/diffusers）。
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        output_dir: str | Path | None = None,
        device: str = "auto",
        offline: bool = True,
        ip_adapter_path: str | Path | None = None,
        api_key: str | None = None,
        screen_size: tuple[int, int] | str | None = None,
        fit: str | None = None,
    ):
        # ---- APIYI（Gemini 图像）后端配置 ----
        # 优先级: 构造参数 > settings.toml [image]（GUI 设置页, 非空字段）> .env
        # api_key: None=自动读取; ""=强制本地 diffusers（测试用）; 非空=APIYI
        cfg = {}
        try:
            _root = Path(__file__).resolve().parents[1]
            _st = _root / "settings.toml"
            if _st.is_file():
                import tomllib
                _data = tomllib.loads(_st.read_text(encoding="utf-8"))
                cfg = _data.get("image", {}) if isinstance(_data, dict) else {}
        except (OSError, ValueError, ImportError):
            cfg = {}
        self._api_key = (
            api_key if api_key is not None
            else str(cfg.get("api_key") or "").strip()
            or os.getenv("IMAGE_API_KEY", "")
        )
        self.api_base_url = (
            str(cfg.get("base_url") or "").strip()
            or os.getenv("IMAGE_API_BASE_URL", "https://api.apiyi.com")
        )
        self.api_model = (
            str(cfg.get("model") or "").strip()
            or os.getenv("IMAGE_MODEL", "gemini-3.1-flash-lite-image")
        )
        self.api_version = os.getenv("IMAGE_API_VERSION", "v1beta")

        # ---- 本地 diffusers fallback 配置 ----
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

        # ---- 目标尺寸 / 归一化（2026-09-10: 出图尺寸 = 屏幕尺寸）----
        # 优先级: 构造参数 > settings.toml [image].screen_size > DEFAULT_SCREEN_SIZE
        self.screen_size = (
            parse_size(screen_size) or parse_size(cfg.get("screen_size"))
            or DEFAULT_SCREEN_SIZE
        )
        self.fit = str(fit or cfg.get("fit") or "contain").strip().lower()
        if self.fit not in ("contain", "cover", "none"):
            self.fit = "contain"
        self.api_aspect_ratio = bool(cfg.get("api_aspect_ratio", True))
        self._aspect_ok = True          # 代理不认 imageConfig.aspectRatio → 只降级一次

    @property
    def is_api_mode(self) -> bool:
        """是否走 APIYI 后端（配了 IMAGE_API_KEY）。"""
        return bool(self._api_key)

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
        character_name: str = "角色",
        size: tuple[int, int] | str | None = None,
        fit: str | None = None,
    ) -> GeneratedImage:
        """生成一张图并保存到输出目录, 返回 GeneratedImage（路径 + 尺寸 + 元信息）。

        APIYI 模式（配了 IMAGE_API_KEY）:
            prompt = **中文场景指令**（场景/光线/情感/构图, 不写角色外观——ref 图锚定）;
            ref_images = collect_ref_images(char_id)（角色→画风→配饰顺序）;
            character_name 注入固定框架（"图1是角色 X 的本体参考图"）。
            内部逐图带标签 + 多图 parts → generateContent → 落盘 → 归一化。
            size 缺省 = self.screen_size（屏幕尺寸）; fit 缺省 = self.fit。

        本地 diffusers 模式（fallback）:
            height/width 缺省 → 模型原生分辨率（SDXL 1024 / SD1.5 512）;
            SDXL 自动加动漫质量前缀 + 默认 negative; ref_images 走 IP-Adapter。
            本地默认**不做**尺寸归一化（分辨率低, 放大反而糊）; 显式传 size 才归一化。

        seed 固定 → 可复现（仅本地模式; APIYI 无 seed 概念）。
        文件名: gen_{ts}_{seed}.png（APIYI 用 _apiyi 后缀）。
        """
        if not prompt.strip():
            raise ValueError(err("ImageGen", "prompt 不能为空"))

        # ---- APIYI 后端（推荐）----
        if self.is_api_mode:
            return self._generate_apiyi(
                prompt, ref_images, character_name,
                size=parse_size(size) or self.screen_size, fit=fit or self.fit)

        # ---- 本地 diffusers fallback ----
        import torch  # noqa: PLC0415 — 与 _load_pipe 同层懒加载

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
        want = parse_size(size)                     # 本地默认不归一化（避免放大糊）
        if want:
            return self._normalize(out, want, fit or self.fit, backend="diffusers")
        return GeneratedImage(path=out, width=img.width, height=img.height,
                              size_bytes=out.stat().st_size, backend="diffusers")

    # ------------------------------------------------------------------
    # APIYI（Gemini 图像）后端
    # ------------------------------------------------------------------

    def _generate_apiyi(
        self,
        scene_prompt: str,
        ref_images: list[str | Path] | None,
        character_name: str,
        size: tuple[int, int] | None = None,
        fit: str | None = None,
    ) -> GeneratedImage:
        """APIYI generateContent: 逐图带标签的多图 parts + 场景指令 → 落盘 → 归一化。

        - ref 逐张带文字标签（角色本体/画风参考/配饰:{名}）——旧版写死"图1/图2/图3",
          ref 多于 3 张时标签错位（光环被当多余图 → 画错, 2026-09-10 实测确诊）。
        - 实测出图宽高比跟随第一张 ref（sprite 800x2286 → 出图 608x1737 同比例）,
          故请求携带 imageConfig.aspectRatio = 屏幕比例; 代理不认 → 去掉重试一次。
        - 出图后按 fit 归一化到屏幕尺寸（contain 留边 / cover 裁满 / none 不处理）。

        请求/响应格式（2026-08-24 单点验证）:
            POST {base}/{version}/models/{model}:generateContent
            body: {"contents":[{"parts":[text, inline_data, …]}],
                   "generationConfig":{"responseModalities":["IMAGE"],
                                       "imageConfig":{"aspectRatio":"16:9"}}}
            响应: candidates[0].content.parts[].inlineData.data（base64）
        失败 → 明确报错（宁缺勿错, 不静默）。
        """
        t0 = time.perf_counter()
        specs = _specs_from_paths(ref_images)
        size = size or self.screen_size
        fit = fit or self.fit
        parts = _build_api_parts(specs, character_name, scene_prompt, size)
        generation: dict = {"responseModalities": ["IMAGE"]}
        if size and self.api_aspect_ratio and self._aspect_ok:
            generation["imageConfig"] = {"aspectRatio": _ratio_str(*size)}
        body = {"contents": [{"parts": parts}], "generationConfig": generation}

        try:
            resp = self._post_api(body)
        except RuntimeError as e:                        # 代理不认 imageConfig → 降级一次
            if "imageConfig" in generation and _unsupported_aspect(str(e)):
                logger.warning("APIYI 不认 imageConfig.aspectRatio, 去掉后重试一次: %s",
                               str(e)[:120])
                self._aspect_ok = False
                generation.pop("imageConfig", None)
                resp = self._post_api(body)
            else:
                raise

        for part in (resp.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
            data = part.get("inlineData") or part.get("inline_data") or {}
            b64 = data.get("data")
            if b64:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                out = self.output_dir / f"gen_{datetime.now():%Y%m%d_%H%M%S}_apiyi.png"
                out.write_bytes(base64.b64decode(b64))
                return self._finalize(out, size, fit, backend="apiyi",
                                      elapsed_s=time.perf_counter() - t0)
        raise RuntimeError(err("ImageGen", f"响应无图片输出: {str(resp)[:300]}"))

    def _post_api(self, body: dict) -> dict:
        """POST generateContent → 解析 JSON; HTTP/网络失败 → 明确报错（不静默）。"""
        url = (f"{self.api_base_url}/{self.api_version}"
               f"/models/{self.api_model}:generateContent")
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(err(
                "ImageGen", f"APIYI 请求失败 HTTP {e.code}: {detail}")) from e
        except Exception as e:                           # noqa: BLE001
            raise RuntimeError(err("ImageGen", f"APIYI 请求失败: {e}")) from e

    def _finalize(self, path: Path, size: tuple[int, int] | None, fit: str,
                  backend: str, elapsed_s: float = 0.0) -> GeneratedImage:
        """收尾: 需要时归一化到目标尺寸, 并读回真实尺寸（PIL 缺失 → 尺寸记 0）。"""
        if size and fit != "none":
            return self._normalize(path, size, fit, backend=backend, elapsed_s=elapsed_s)
        w, h = _probe_size(path)
        return GeneratedImage(path=path, width=w, height=h,
                              size_bytes=path.stat().st_size, backend=backend,
                              elapsed_s=elapsed_s)

    def _normalize(self, path: Path, size: tuple[int, int], fit: str, *,
                   backend: str = "", elapsed_s: float = 0.0) -> GeneratedImage:
        """把图归一化到目标尺寸（contain=留边不裁内容 / cover=裁满屏）; 失败 → 保留原图。

        归一化就地覆盖同一文件（PNG）; 失败时只降级尺寸, 不影响图本身（宁缺勿错）。
        """
        try:
            from PIL import Image
        except ImportError:
            logger.warning("PIL 不可用, 跳过尺寸归一化")
            w, h = _probe_size(path)
            return GeneratedImage(path=path, width=w, height=h,
                                  size_bytes=path.stat().st_size, backend=backend,
                                  elapsed_s=elapsed_s)
        tw, th = size
        try:
            with Image.open(path) as raw:
                src = raw.size
                if src == (tw, th):
                    return GeneratedImage(path=path, width=tw, height=th,
                                          size_bytes=path.stat().st_size, backend=backend,
                                          elapsed_s=elapsed_s, source_size=src,
                                          screen_size=size, fit="none")
                im = raw.convert("RGB")
                scale = (max if fit == "cover" else min)(tw / src[0], th / src[1])
                nw, nh = max(1, round(src[0] * scale)), max(1, round(src[1] * scale))
                resized = im.resize((nw, nh), Image.LANCZOS)
                if fit == "cover":
                    left, top = (nw - tw) // 2, (nh - th) // 2
                    canvas = resized.crop((left, top, left + tw, top + th))
                else:
                    canvas = Image.new("RGB", (tw, th), (0, 0, 0))
                    canvas.paste(resized, ((tw - nw) // 2, (th - nh) // 2))
                canvas.save(path, format="PNG")
        except Exception as e:                           # noqa: BLE001 — 归一化失败不废图
            logger.warning("尺寸归一化失败（保留原图 %s）: %s", path.name, e)
            w, h = _probe_size(path)
            return GeneratedImage(path=path, width=w, height=h,
                                  size_bytes=path.stat().st_size, backend=backend,
                                  elapsed_s=elapsed_s, source_size=(w, h))
        return GeneratedImage(path=path, width=tw, height=th,
                              size_bytes=path.stat().st_size, backend=backend,
                              elapsed_s=elapsed_s, source_size=src,
                              screen_size=size, fit=fit)

    # 便捷属性（懒加载入口, 测试断言用）
    @property
    def pipe(self):
        return self._pipe


# ---------------------------------------------------------------------------
# ref 图分组（命名约定: 角色 → 画风 → 配饰, 喂图顺序固定）
# ---------------------------------------------------------------------------

def ref_specs(char_id: str, assets_root: str | Path | None = None
              ) -> list[tuple[str, str, Path]]:
    """按 ref 命名约定分组取图, 返回 [(kind, 中文标签, path)]。

    顺序固定: sprite_*(角色本体) → style_*(画风参考) → 其余(配饰)。
    路径: assets/illustration/{char_id}/ref/（缺失 → 空列表, 调用方降级纯文本）。
    配饰组 = 非 sprite_/style_ 前缀的 png（文件名即标签, 如 halo.png → 光环）——
    换配饰直接放文件, 不用改名。
    """
    base = Path(assets_root) if assets_root else (
        Path(__file__).resolve().parent.parent / "assets")
    ref_dir = base / "illustration" / char_id / "ref"
    if not ref_dir.is_dir():
        return []
    ordered = (sorted(ref_dir.glob("sprite_*.png"))
               + sorted(ref_dir.glob("style_*.png"))
               + sorted(p for p in ref_dir.glob("*.png")
                        if not p.name.startswith(("sprite_", "style_"))))
    return [(kind, label, path) for kind, label, path in
            ((*_kind_label(p), p) for p in ordered)]


def collect_ref_images(char_id: str, assets_root: str | Path | None = None) -> list[Path]:
    """ref 图路径列表（喂图顺序固定: 角色 → 画风 → 配饰）——ref_specs 的路径视图。"""
    return [path for _, _, path in ref_specs(char_id, assets_root)]


def _specs_from_paths(paths: list[str | Path] | None) -> list[tuple[str, str, Path]]:
    """调用方只给路径时, 按文件名推断 (kind, 标签) —— 与 ref_specs 同规则。"""
    specs: list[tuple[str, str, Path]] = []
    for p in paths or []:
        path = Path(p)
        kind, label = _kind_label(path)
        specs.append((kind, label, path))
    return specs


def _probe_size(path: Path) -> tuple[int, int]:
    """读图片真实尺寸（PIL 缺失/读失败 → (0, 0), 不阻断）。"""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception as e:                               # noqa: BLE001
        logger.warning("读取图片尺寸失败（元信息记 0）: %s", e)
        return (0, 0)


def _unsupported_aspect(detail: str) -> bool:
    """APIYI 报错是否像"不认 imageConfig/aspectRatio"（用于降级重试一次）。"""
    low = detail.lower()
    return any(k in low for k in ("imageconfig", "aspectratio", "aspect_ratio",
                                  "unknown name", "cannot find field",
                                  "invalid json payload"))
