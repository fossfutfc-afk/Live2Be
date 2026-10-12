"""生图接口 — APIYI（Gemini 图像 / nano banana）单后端。

**单后端（2026-09-10 用户拍板: 移除本地 diffusers 兜底）**:
    本地 SD 出图"不像人类", 维护两套后端得不偿失——已删除。未配 IMAGE_API_KEY 时
    generate() 明确报错（宁缺勿错, 不静默降级成低质量本地图）。

配置（settings.toml [image] 优先, .env 兜底; 构造参数可覆盖）:
    enabled              生图总开关（默认 true; false = 全局关闭, 见下）
    IMAGE_API_KEY        APIYI key（必填）
    IMAGE_API_BASE_URL   默认 https://api.apiyi.com
    IMAGE_MODEL          默认 gemini-3.1-flash-lite-image（Nano Banana 2 Lite）
    IMAGE_API_VERSION    默认 v1beta
    IMAGE_OUTPUT_DIR     生成图输出目录（默认 D:\\by-user\\fossf\\AI\\output）
    screen_size          目标尺寸 = 屏幕尺寸（默认 1920x1080）
    fit                  contain(留边不裁, 默认) / cover(裁满屏) / none
    api_aspect_ratio     请求是否携带 imageConfig.aspectRatio（默认 true; 不支持自动降级）

**生图总开关（2026-09-11）**——第一个 `image_enabled()`:
    环境变量 `LIVE2BE_IMAGE=off`（最高优先, 进程级硬关, 不碰配置文件）
    > settings.toml `[image].enabled = false`（GUI 设置页复选框, 持久)
    > 默认 **开**。关闭时: `ImageGenerator.enabled=False` → 消费方（webgui 纪念
    线程 / vn_cli / main）一律**不开生图线程、降级纯文字**; 直接调 `generate()`
    会明确报错（不静默假装成功）。用途: 跑测试 / 离线调试 / 临时省钱的**确定性**
    关闭——不再依赖"忘了配 key"这种偶然保护（key 配着时跑测试是真会出图烧钱的）。

**ref 命名约定（不变; 目录路径可变——每个角色都会有对应图片）**:
    <ref 目录>/
        sprite_*.png     角色本体（官方立绘拆件, 可多张）
        style_*.png      同一角色的**官方记忆大厅插画**——画风与质感基准,
                         同时也是角色外观的补充参考（不是别的角色）
        其余 png         配饰（光环/随身物品; 文件名即标签, 如 halo.png → 光环）
    ref_specs(char_id, ref_dir=...) → [(kind, 中文标签, path)];
    collect_ref_images() 是其路径视图; 只给路径时按同一命名规则推断标签。

**目标尺寸 = 屏幕尺寸**:
    - 实测出图宽高比跟随第一张 ref（sprite 800x2286 → 出图 608x1737 同比例）,
      故请求携带 generationConfig.imageConfig.aspectRatio = 屏幕比例;
      代理不支持该字段时自动去掉重试一次（不额外计费）。
    - 出图后归一化到 screen_size; generate() 返回 GeneratedImage（宽高/耗时等元信息）。

用法:
    from llm.image_gen import ImageGenerator, collect_ref_images
    gen = ImageGenerator()
    img = gen.generate(scene_prompt,                      # 中文场景指令（不写外观）
                       ref_images=collect_ref_images(char_id),
                       character_name=char.display_name)  # 名字由角色卡提供, 不硬编码
    img.path, img.width, img.height
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
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

#: 默认输出目录（.env IMAGE_OUTPUT_DIR 可覆盖）
_DEFAULT_OUTPUT = r"D:\by-user\fossf\AI\output"
#: ref 目录默认形态: {assets_root}/illustration/{char_id}/ref
#: （路径可变——以后换位置只需传 ref_dir/assets_root, 命名约定 sprite_/style_/其余 不变）
_DEFAULT_REF_SUBDIR = Path("illustration")

#: 默认屏幕尺寸（生图目标 = 屏幕尺寸; settings.toml [image] screen_size 可覆盖）
DEFAULT_SCREEN_SIZE = (1920, 1080)
#: 配饰文件名 → 中文标签（未列出的直接用文件名主干, 保持通用）
_ACCESSORY_LABELS = {"halo": "光环", "weapon": "武器", "bag": "挎包", "gift": "礼物"}

#: 生图总开关的环境变量名（进程级; 值 off/0/false/no = 关闭, on/1/true/yes = 打开）
ENV_SWITCH = "LIVE2BE_IMAGE"
#: 视为"关闭"的取值（大小写不敏感）
_OFF_VALUES = {"off", "0", "false", "no", "none", "disable", "disabled"}
#: 视为"只构造请求、不发 HTTP"的取值（dry-run: 探针/实验/调试零成本跑通代码路径）
_DRY_VALUES = {"dry", "dry-run", "dryrun", "noop", "fake"}
#: 显式允许**测试进程**真实生图（默认禁止——见 _refuse_real_call_in_pytest）
ENV_ALLOW_REAL = "LIVE2BE_IMAGE_ALLOW_REAL"


def _running_under_pytest() -> bool:
    """是否在 pytest 进程里（含测试派生的后台线程——环境变量是进程级的）。"""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return "pytest" in sys.modules


def _refuse_real_call_in_pytest() -> None:
    """**测试进程硬闸**（2026-09-11 真机事故后加）: 禁止真实生图 HTTP。

    事故: 我给"生图总开关"写的冒烟探针（`.testtmp/probe_image_switch.py`）里
    `g.generate('测试')` 被 try/except 包着, 本意是"验证打开时不报错", 结果它
    **真的发了一次计费请求**（`D:\\by-user\\fossf\\AI\\output\\gen_20260911_202541_apiyi.png`）。
    conftest 的 `LIVE2BE_IMAGE=off` 管不到这种独立脚本, 于是钱花了才发现。

    所以闸门放在**唯一的 HTTP 出口**（`_post_api`）上, 按进程环境判定:
    测试进程一律拒绝, 除非显式 `LIVE2BE_IMAGE_ALLOW_REAL=1`（真机连通性用例
    才需要）。experiments/ 脚本用 `conda run python` 跑, 不受影响。
    """
    if not _running_under_pytest():
        return
    if str(os.environ.get(ENV_ALLOW_REAL, "")).strip().lower() in ("1", "true", "yes", "on"):
        return
    raise RuntimeError(err(
        "ImageGen", "测试进程禁止真实生图调用（会计费）——用例请 monkeypatch "
        "`ImageGenerator._post_api`, 或设 dry（LIVE2BE_IMAGE=dry）; "
        f"确实要真调请显式 {ENV_ALLOW_REAL}=1"))


def _settings_image_cfg() -> dict:
    """读项目根 settings.toml 的 [image] 分组（缺失/损坏 → {}; 不阻塞）。"""
    try:
        st = _PROJECT_ROOT / "settings.toml"
        if not st.is_file():
            return {}
        import tomllib
        data = tomllib.loads(st.read_text(encoding="utf-8"))
        cfg = data.get("image", {}) if isinstance(data, dict) else {}
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError, ImportError):
        return {}


def image_enabled(cfg: dict | None = None) -> bool:
    """生图总开关: 环境变量 `LIVE2BE_IMAGE` > settings `[image].enabled` > 默认 True。

    环境变量只在**明确取值**时生效（未设 → 落到配置）; 关闭 = 所有消费方不开生图
    线程、降级纯文字（见模块头"生图总开关"）。cfg 可传入已读好的 [image] 分组
    （ImageGenerator.__init__ 复用, 少读一次文件）。

    注: `LIVE2BE_IMAGE=dry`（= 只构造请求不发 HTTP）**也算"开"**——dry 由
    `image_dry_run()` 单独判定; 这样"开关关了"与"开关开着但干跑"互不混淆。
    """
    raw = str(_env_raw()).strip().lower()
    if raw and raw not in _DRY_VALUES:
        return raw not in _OFF_VALUES
    if raw in _DRY_VALUES:
        return True
    if cfg is None:
        cfg = _settings_image_cfg()
    v = cfg.get("enabled", True)
    return bool(v) if isinstance(v, bool) else True


def image_dry_run(cfg: dict | None = None) -> bool:
    """是否**干跑**（构造完整请求 + 打日志, 但不发 HTTP）: `LIVE2BE_IMAGE=dry`
    > settings `[image].dry_run = true` > 默认 False。

    用途: 探针/实验/调试零成本跑通生图代码路径（我就是缺这个才误触了一次真调用）。
    干跑时 `generate()` 返回**占位 GeneratedImage**（路径按正常命名给, 但不落盘）。
    """
    raw = str(_env_raw()).strip().lower()
    if raw:
        return raw in _DRY_VALUES
    if cfg is None:
        cfg = _settings_image_cfg()
    v = cfg.get("dry_run", False)
    return bool(v) if isinstance(v, bool) else False


def _env_raw() -> str:
    """生图开关环境变量的原始值（空 = 未设）。"""
    return os.getenv(ENV_SWITCH, "")


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
    backend: str = "apiyi"
    elapsed_s: float = 0.0
    source_size: tuple[int, int] | None = None    # 归一化前的原始尺寸
    screen_size: tuple[int, int] | None = None    # 目标屏幕尺寸（未归一化 → None）
    fit: str = "none"                             # contain | cover | none

    def __fspath__(self) -> str:
        return str(self.path)

    def __str__(self) -> str:
        return str(self.path)


# ---------------------------------------------------------------------------
# APIYI 提示词框架（引擎侧拼接, 不依赖 LLM 每次写）
# 逐图标签按实际 ref 动态生成——旧版写死"图1角色/图2画风/图3配饰", ref 超过 3 张时
# 标签错位（光环被当多余图 → 画错, 2026-09-10 实测确诊）
# ---------------------------------------------------------------------------

_APIYI_HEADER = "《蔚蓝档案》官方风格插画。依据以下参考图与场景指令，绘制一张单幅插画。"
_APIYI_ROLE_LABEL = (
    '【图{n} 角色本体】角色"{name}"的官方立绘拆件。严格保持其设计：发型、瞳色、'
    "服装、配饰、头顶光环；不改设计、不换装、不变年龄感。"
)
_APIYI_STYLE_LABEL = (
    "【图{n} 画风与质感基准】同一角色的官方记忆大厅插画：线条、上色、光影、氛围照此执行，"
    "亦作外观补充参考。"
)
_APIYI_ACC_LABEL = "【图{n} 配饰：{acc}】必须画出：形状与颜色照图{hint}。"
_APIYI_HALO_HINT = "；光环悬浮于头顶上方、不与头部相连，半透明发光"
#: 角色卡 profile.yml 的 halo 字段注入形态（该角色光环形状特殊时按此描述绘制）
_APIYI_HALO_DESC = "【图{n} 配饰：{acc}】必须画出，形状严格按参考图与以下描述：{desc}。" \
                   "光环悬浮于头顶上方、不与头部相连，半透明发光。"
#: 角色卡补充设定（外观要点 **+ 性格简卡**）追加到角色本体标签之后。
#: ⚠️ 为什么要有"性格"这一半（2026-09-20）: 生图模型**不知道她是谁**——光有外观
#: 参考图画不出"自卑/惶恐"那层神态（真机那张纪念图给她画成了明亮的笑）。
#: 料 = `personality.yml` 的 SIG~brief_traits（`DynamicCharacter.image_persona_brief`），
#: 或 `illustration.yml` 的作者手写版。**不给外貌细节**（外貌有参考图）。
_APIYI_ROLE_HINT = "【补充设定（画神态时照此，外貌仍以参考图为准）】\n{hint}"
_APIYI_TAIL = (
    "【场景指令】\n{scene}\n\n"
    "【构图】单幅横构图 {ratio}（{w}x{h}）: 默认**中近景**——她占画面主要位置、"
    "脸与上半身清晰可辨；场景指令若要全景/远景则照它。不要多人同框、不要分格或设定表排版。\n"
    "【光线与氛围】按场景指令里的时间与情绪定光（黄昏暖光／夜里冷光／室内散射光）;"
    "情绪低落时压暗、收窄光域，明亮时给一点高光。\n"
    "【要求】官方动画风格（干净线稿、通透色彩、柔和光影）；表情与姿态严格按场景指令；"
    "不要文字、水印、签名、边框、设定表、多视图、分格；"
    "不改角色设计，不新增场景外人物。"
)


def _mime_of(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"


def _ref_cache_dir() -> Path:
    """ref 压缩缓存目录（默认 <IMAGE_OUTPUT_DIR>/_ref_cache; 环境变量可覆盖）。"""
    env = os.getenv("IMAGE_REF_CACHE_DIR", "").strip()
    base = Path(env) if env else Path(os.getenv("IMAGE_OUTPUT_DIR", _DEFAULT_OUTPUT))
    return base / "_ref_cache"


def _prepare_ref_bytes(path: Path, max_edge: int = 0, quality: int = 85,
                       cache_dir: Path | None = None) -> tuple[bytes, str]:
    """上传前处理 ref 图: 长边压到 max_edge 并转 JPEG（按 mtime/尺寸缓存）。

    - max_edge <= 0 → 原图原样（PNG 无损, 但请求体可能是几十 MB——实测 21.7MB, 延迟大头）;
    - 压缩失败/PIL 缺失 → 回退原图（宁缺勿错, 不阻断生图）;
    - 缓存键 = 文件名 + mtime + 体积 + 参数 → 原图不变则零重复压缩。
    """
    if max_edge <= 0:
        return path.read_bytes(), _mime_of(path)
    try:
        from PIL import Image
    except ImportError:
        return path.read_bytes(), _mime_of(path)
    cache_root = cache_dir or _ref_cache_dir()
    try:
        st = path.stat()
        key = f"{path.stem}_{int(st.st_mtime)}_{st.st_size}_{max_edge}_{quality}.jpg"
        cached = cache_root / key
        if cached.is_file():
            return cached.read_bytes(), "image/jpeg"
        with Image.open(path) as raw:
            im = raw.convert("RGB")
            w, h = im.size
            scale = max_edge / max(w, h)
            if scale < 1:
                im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                               Image.LANCZOS)
            cache_root.mkdir(parents=True, exist_ok=True)
            im.save(cached, format="JPEG", quality=quality, optimize=True)
        return cached.read_bytes(), "image/jpeg"
    except Exception as e:                               # noqa: BLE001 — 压缩失败不废图
        logger.warning("ref 压缩失败（用原图 %s）: %s", path.name, e)
        return path.read_bytes(), _mime_of(path)


def _kind_label(path: Path) -> tuple[str, str]:
    """ref 文件名 → (kind, 中文标签): sprite_*=角色本体 / style_*=画风基准 / 其余=配饰。"""
    stem = path.stem
    low = stem.lower()
    if low.startswith("sprite"):
        return "role", "角色本体"
    if low.startswith("style"):
        return "style", "画风与质感基准"
    return "acc", _ACCESSORY_LABELS.get(low, stem)


def _build_api_parts(specs: list[tuple[str, str, Path]], name: str, scene: str,
                     size: tuple[int, int] | None, *, ref_max_edge: int = 0,
                     ref_jpeg_quality: int = 85, cache_dir: Path | None = None,
                     character_hint: str = "", halo_hint: str = "") -> list[dict]:
    """逐图带标签的 parts（标签 text 与 inline_data 交替）+ 场景指令尾。

    specs = [(kind, 中文标签, path)]（ref_specs() 或路径推断的结果）。
    ref_max_edge > 0 → ref 上传前压到该长边并转 JPEG（实测 21.7MB→0.33MB,
    延迟大头是上传; 见 _prepare_ref_bytes）。
    character_hint → 追加到【角色本体】标签（外观要点等）;
    halo_hint → 替换默认光环描述（角色卡 profile.yml 的 halo 字段——模型没见过
    的非典型光环形状靠它讲清楚）。
    """
    parts: list[dict] = [{"text": _APIYI_HEADER}]
    role_text = _APIYI_ROLE_LABEL.format(n=1, name=name)
    if character_hint.strip():
        role_text += "\n" + _APIYI_ROLE_HINT.format(hint=character_hint.strip())
    for i, (kind, label, path) in enumerate(specs, start=1):
        if kind == "role":
            text = role_text if i == 1 else _APIYI_ROLE_LABEL.format(n=i, name=name)
        elif kind == "style":
            text = _APIYI_STYLE_LABEL.format(n=i)
        elif label == "光环" and halo_hint.strip():
            text = _APIYI_HALO_DESC.format(
                n=i, acc=label, desc=halo_hint.strip().rstrip("。；;，, "))
        else:
            hint = _APIYI_HALO_HINT if label == "光环" else ""
            text = _APIYI_ACC_LABEL.format(n=i, acc=label, hint=hint)
        raw, mime = _prepare_ref_bytes(path, ref_max_edge, ref_jpeg_quality, cache_dir)
        parts.append({"text": text})
        parts.append({"inline_data": {"mime_type": mime,
                                      "data": base64.b64encode(raw).decode()}})
    w, h = size or DEFAULT_SCREEN_SIZE
    parts.append({"text": _APIYI_TAIL.format(scene=scene, ratio=_ratio_str(w, h), w=w, h=h)})
    return parts


class ImageGenerator:
    """生图客户端（APIYI Gemini 后端, 单后端）。

    API 模式: 构造即就绪（无模型加载）, generate() 走 HTTP（实测单张 26s 量级）。
    """

    def __init__(
        self,
        output_dir: str | Path | None = None,
        api_key: str | None = None,
        screen_size: tuple[int, int] | str | None = None,
        fit: str | None = None,
    ):
        # 优先级: 构造参数 > settings.toml [image]（GUI 设置页）> .env
        cfg = _settings_image_cfg()
        # 生图总开关（LIVE2BE_IMAGE 环境变量最高优先——测试/离线硬关, 见 image_enabled）
        self.enabled = image_enabled(cfg)
        # 干跑（只构造请求不发 HTTP; 探针/实验用——2026-09-11）
        self.dry_run = image_dry_run(cfg)
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
        self.output_dir = Path(
            output_dir or os.getenv("IMAGE_OUTPUT_DIR", _DEFAULT_OUTPUT))

        # ---- 目标尺寸 / 归一化（出图尺寸 = 屏幕尺寸）----
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

        # ref 上传前压缩（长边像素; 0 = 原图不压）——实测请求体 21.7MB 是延迟/成本大头
        try:
            self.ref_max_edge = int(cfg.get("ref_max_edge", 1024))
        except (TypeError, ValueError):
            self.ref_max_edge = 1024
        try:
            self.ref_jpeg_quality = int(cfg.get("ref_jpeg_quality", 85))
        except (TypeError, ValueError):
            self.ref_jpeg_quality = 85

    @property
    def is_api_mode(self) -> bool:
        """是否配了 APIYI key（单后端——未配 = 不可用）。

        注意: 只说"配了 key", **不含总开关**（`enabled`）——消费方要判断"能不能
        出图"请用 `available`（或分别看 `enabled`）。
        """
        return bool(self._api_key)

    @property
    def available(self) -> bool:
        """实际可出图 = 总开关开 **且** 配了 key（消费方统一用这个判据）。"""
        return bool(self.enabled and self._api_key)

    def warmup(self) -> None:
        """接口兼容占位（本地 diffusers 已移除; API 后端无预热对象）。"""

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        ref_images: list[str | Path] | None = None,
        character_name: str = "角色",
        size: tuple[int, int] | str | None = None,
        fit: str | None = None,
        character_hint: str = "",
        halo_hint: str = "",
        **_legacy,
    ) -> GeneratedImage:
        """生成一张图并保存到输出目录, 返回 GeneratedImage（路径 + 尺寸 + 元信息）。

        prompt = **中文场景指令**（场景/光线/情感/构图, 不写角色外观——ref 图锚定）;
        ref_images = collect_ref_images(char_id)（角色→画风→配饰顺序, 逐图带标签）;
        character_name 注入角色本体标签; character_hint/halo_hint 来自角色卡
        （profile.yml 的 halo 字段等）——逐角色讲清"模型没见过的"特殊形状;
        size 缺省 = self.screen_size（屏幕尺寸）, fit 缺省 = self.fit。
        **_legacy 吞掉旧参数（seed/steps/height…本地后端残留）, 避免历史调用点报错。
        """
        if not prompt.strip():
            raise ValueError(err("ImageGen", "prompt 不能为空"))
        if not self.enabled:
            raise RuntimeError(err(
                "ImageGen", f"生图已关闭（{ENV_SWITCH}=off / settings.toml "
                "[image].enabled=false）——如需出图请打开总开关"))
        if not self.is_api_mode:
            raise RuntimeError(err(
                "ImageGen", "未配置 IMAGE_API_KEY（本地 diffusers 兜底已于 2026-09-10 移除）"
                "——请在 settings.toml [image] 或 .env 配置 APIYI key"))
        # 干跑（2026-09-11）: 请求照常构造 + 打日志, **不发 HTTP**——探针/实验/调试
        # 零成本跑通代码路径; 返回占位 GeneratedImage（路径按正常命名, 但不落盘——
        # 下游做文件 copy 的调用方会失败, 那是"干跑"应有的表现, 别拿它当成功）
        if self.dry_run:
            size = parse_size(size) or self.screen_size
            out = Path(self.output_dir) / (
                f"DRYRUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.png")
            logger.info("生图 dry-run: 已构造请求, 未发送（prompt=%r ref=%d 张 size=%s）",
                        prompt[:40], len(ref_images or []), size)
            return GeneratedImage(path=out, width=size[0], height=size[1],
                                  size_bytes=0, backend="dry", elapsed_s=0.0)
        return self._generate_apiyi(
            prompt, ref_images, character_name,
            size=parse_size(size) or self.screen_size, fit=fit or self.fit,
            character_hint=character_hint, halo_hint=halo_hint)

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
        character_hint: str = "",
        halo_hint: str = "",
    ) -> GeneratedImage:
        """APIYI generateContent: 逐图带标签的多图 parts + 场景指令 → 落盘 → 归一化。

        - ref 逐张带文字标签（角色本体/画风基准/配饰:{名}）; 标签按实际 ref 数量生成。
        - 实测出图宽高比跟随第一张 ref, 故携带 imageConfig.aspectRatio = 屏幕比例;
          代理不认该字段 → 去掉重试一次（失败请求不计费）。
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
        parts = _build_api_parts(specs, character_name, scene_prompt, size,
                                 ref_max_edge=self.ref_max_edge,
                                 ref_jpeg_quality=self.ref_jpeg_quality,
                                 cache_dir=_ref_cache_dir(),
                                 character_hint=character_hint,
                                 halo_hint=halo_hint)
        inline_b64 = sum(len(p["inline_data"]["data"]) for p in parts if "inline_data" in p)
        logger.info("生图请求: ref=%d 张, 内联载荷≈%.1fMB (max_edge=%d, q=%d, %s)",
                    len(specs), inline_b64 * 3 / 4 / 1048576, self.ref_max_edge,
                    self.ref_jpeg_quality, self.api_model)
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
        # **测试进程硬闸**（唯一 HTTP 出口, 2026-09-11 误触计费事故后加）:
        # 见 _refuse_real_call_in_pytest 的说明。放在这里 = 任何调用方
        # （webgui 纪念线程 / vn_cli / main / 探针脚本）在测试进程里都拦得住。
        _refuse_real_call_in_pytest()
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
        src = (0, 0)
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


# ---------------------------------------------------------------------------
# ref 图分组（命名约定: 角色 → 画风 → 配饰; 目录路径可变, 命名不变）
# ---------------------------------------------------------------------------

def ref_specs(char_id: str, ref_dir: str | Path | None = None,
              assets_root: str | Path | None = None) -> list[tuple[str, str, Path]]:
    """取角色 ref 图, 返回 [(kind, 中文标签, path)]（顺序: 角色 → 画风 → 配饰）。

    ref_dir 直接给目录（路径随角色/世界变化时用）; 缺省 = {assets_root}/illustration/
    {char_id}/ref。命名约定 sprite_*(角色本体) / style_*(画风基准) / 其余(配饰) 不变——
    换目录只需传 ref_dir, 标签体系不用改。缺失 → 空列表（调用方降级纯文本）。
    """
    if ref_dir is not None:
        directory = Path(ref_dir)
    else:
        base = Path(assets_root) if assets_root else (_PROJECT_ROOT / "assets")
        directory = base / _DEFAULT_REF_SUBDIR / char_id / "ref"
    if not directory.is_dir():
        return []
    ordered = (sorted(directory.glob("sprite_*.png"))
               + sorted(directory.glob("style_*.png"))
               + sorted(p for p in directory.glob("*.png")
                        if not p.name.startswith(("sprite_", "style_"))))
    return [(*_kind_label(p), p) for p in ordered]


def collect_ref_images(char_id: str, ref_dir: str | Path | None = None,
                       assets_root: str | Path | None = None) -> list[Path]:
    """ref 图路径列表（喂图顺序固定: 角色 → 画风 → 配饰）——ref_specs 的路径视图。"""
    return [path for _, _, path in ref_specs(char_id, ref_dir, assets_root)]


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
