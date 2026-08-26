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
    collect_ref_images(char_id) 按此分组排序返回。

用法:
    from llm.image_gen import ImageGenerator, collect_ref_images
    gen = ImageGenerator()                       # 配了 IMAGE_API_KEY → APIYI
    refs = collect_ref_images("igusa_haruka")
    path = gen.generate("她在湖边微笑，眼角带一滴泪，黄昏暖光，晚风拂过鬓发",
                        ref_images=refs, character_name="伊草 遥香")
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
import urllib.error
import urllib.request
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

#: APIYI 固定框架（引擎侧拼接, 不依赖 LLM 每次写）——角色/画风/配饰三个锚点 + 质量要求
_APIYI_FRAME = """你是一位插画师，请根据以下参考图与要求生成一张图片。

【图1 角色本体】图1是角色"{name}"的本体参考图。必须严格保持她的外观特征
（发色/瞳色/发型/服装/标志物）——不要改动角色外观，不要擅自换装。

【图2 画风参考】图2是画风参考。整体绘画风格、上色方式、线条质感都按图2执行。

【图3 配饰参考】图3是角色标志性配饰（光环/随身物品）。按图3的形状与颜色绘制，
位置正确（如头顶上方），半透明发光质感。

【场景指令】
{scene}

【质量要求】高质量精细绘制，日系动画风格，构图完整，人物表情自然，情绪到位。"""


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
    ) -> Path:
        """生成一张图并保存到输出目录, 返回文件路径（l2d 事件的资产引用）。

        APIYI 模式（配了 IMAGE_API_KEY）:
            prompt = **中文场景指令**（场景/光线/情感/构图, 不写角色外观——ref 图锚定）;
            ref_images = collect_ref_images(char_id)（角色→画风→配饰顺序）;
            character_name 注入固定框架（"图1是角色 X 的本体参考图"）。
            内部拼固定框架 + 多图 parts → generateContent → 落盘。

        本地 diffusers 模式（fallback）:
            height/width 缺省 → 模型原生分辨率（SDXL 1024 / SD1.5 512）;
            SDXL 自动加动漫质量前缀 + 默认 negative; ref_images 走 IP-Adapter。

        seed 固定 → 可复现（仅本地模式; APIYI 无 seed 概念）。
        文件名: gen_{ts}_{seed}.png（APIYI 用 _apiyi 后缀）。
        """
        if not prompt.strip():
            raise ValueError(err("ImageGen", "prompt 不能为空"))

        # ---- APIYI 后端（推荐）----
        if self.is_api_mode:
            return self._generate_apiyi(prompt, ref_images, character_name)

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
        return out

    # ------------------------------------------------------------------
    # APIYI（Gemini 图像）后端
    # ------------------------------------------------------------------

    def _generate_apiyi(
        self,
        scene_prompt: str,
        ref_images: list[str | Path] | None,
        character_name: str,
    ) -> Path:
        """APIYI generateContent: 多图 parts（ref 角色/画风/配饰）+ 固定框架 + 场景指令。

        请求/响应格式（单点测试验证 2026-08-24）:
            POST {base}/{version}/models/{model}:generateContent
            body: {"contents":[{"parts":[{inline_data 图…},{text 指令}]}],
                   "generationConfig":{"responseModalities":["IMAGE"]}}
            响应: candidates[0].content.parts[].inlineData.data（base64）
        失败 → 明确报错（宁缺勿错, 不静默）。
        """
        parts: list[dict] = []
        for p in ref_images or []:
            path = Path(p)
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            parts.append({"inline_data": {
                "mime_type": mime,
                "data": base64.b64encode(path.read_bytes()).decode()}})
        parts.append({"text": _APIYI_FRAME.format(name=character_name, scene=scene_prompt)})

        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        url = (f"{self.api_base_url}/{self.api_version}"
               f"/models/{self.api_model}:generateContent")
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                resp = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(err(
                "ImageGen", f"APIYI 请求失败 HTTP {e.code}: {detail}")) from e
        except Exception as e:                           # noqa: BLE001
            raise RuntimeError(err("ImageGen", f"APIYI 请求失败: {e}")) from e

        for part in (resp.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
            data = part.get("inlineData") or part.get("inline_data") or {}
            b64 = data.get("data")
            if b64:
                img_bytes = base64.b64decode(b64)
                self.output_dir.mkdir(parents=True, exist_ok=True)
                out = self.output_dir / f"gen_{datetime.now():%Y%m%d_%H%M%S}_apiyi.png"
                out.write_bytes(img_bytes)
                return out
        raise RuntimeError(err("ImageGen", f"响应无图片输出: {str(resp)[:300]}"))

    # 便捷属性（懒加载入口, 测试断言用）
    @property
    def pipe(self):
        return self._pipe


# ---------------------------------------------------------------------------
# ref 图分组（命名约定: 角色 → 画风 → 配饰, 喂图顺序固定）
# ---------------------------------------------------------------------------

def collect_ref_images(char_id: str, assets_root: str | Path | None = None) -> list[Path]:
    """按 ref 命名约定分组取图, 顺序固定: sprite_*(角色) → style_*(画风) → 其余(配饰)。

    路径: assets/illustration/{char_id}/ref/（缺失 → 空列表, 调用方降级纯文本）。
    配饰组 = 非 sprite_/style_ 前缀的 png（物品名即可, 如 halo.png）——换配饰
    直接放文件, 不用改名。
    """
    base = Path(assets_root) if assets_root else (
        Path(__file__).resolve().parent.parent / "assets")
    ref_dir = base / "illustration" / char_id / "ref"
    if not ref_dir.is_dir():
        return []
    role = sorted(ref_dir.glob("sprite_*.png"))
    style = sorted(ref_dir.glob("style_*.png"))
    accessory = sorted(p for p in ref_dir.glob("*.png")
                       if not p.name.startswith(("sprite_", "style_")))
    return role + style + accessory
