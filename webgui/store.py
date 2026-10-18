"""GUI 配置存储（settings.toml）— 与路由分离的配置层。

**定位**: GUI 设置页的读写存档——**引擎已接入**: llm/client.py（LLMClient）
与 llm/image_gen.py（ImageGenerator）读配置时「settings.toml 非空字段优先,
.env 兜底」（优先级: 构造参数 > settings.toml > .env > 默认）。GUI 设置页
改 key/base_url/model 立即生效。

文件: 项目根 settings.toml（gitignore, 与 .env 并列——运行时用户配置）。

结构（v1, 平铺分组; 未来 per 角色参数加 [characters.xxx]）:
    [llm]
      api_key = ""          # 空 = 用 .env 的 LLM_API_KEY
      base_url = "https://api.deepseek.com"
      model = "deepseek-chat"
    [image]
      api_key = ""
      base_url = "https://api.apiyi.com"
      enabled = true        # 生图总开关（false = 纪念降级纯文字）; LIVE2BE_IMAGE=off 优先

写: 手写轻量 toml 序列化（分组 + k=v, 值 str/int/bool——够用;
     未来复杂类型（列表/嵌套）再升级 tomli_w）。
"""
from __future__ import annotations

import logging

from contract.errors import err
from infra import settings

logger = logging.getLogger(__name__)

#: 默认配置（缺失/损坏 → 兜底; 与 .env 同名变量对应）
DEFAULTS: dict = {
    "llm": {
        "api_key": "",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-flash",
    },
    "image": {
        "api_key": "",
        "base_url": "https://api.apiyi.com",
        "model": "gemini-3.1-flash-lite-image",
        # 生图总开关（2026-09-11）: false = 纪念场景降级纯文字, 不生图不花钱。
        # 环境变量 LIVE2BE_IMAGE=off 优先于本项（进程级硬关, 跑测试用）。
        "enabled": True,
        # 目标尺寸 = 屏幕尺寸（出图归一化到该尺寸; 2026-09-10）
        "screen_size": "1920x1080",
        "fit": "contain",              # contain=留边不裁 / cover=裁满屏 / none=不处理
        "api_aspect_ratio": True,      # 请求携带 imageConfig.aspectRatio（不支持自动降级）
        "ref_max_edge": 1024,          # ref 上传前压到该长边（0=原图不压）
        "ref_jpeg_quality": 85,        # 压缩质量
    },
}

#: api_key 打码标记（GET 返回用; POST 收到此标记 = 不改 key）
#: 格式: "****" + 后 4 位（如 "****a8a7"——前面打星, 尾部可辨认）
MASK_PREFIX = "****"


def load_settings() -> dict:
    """settings.toml 全量 + 合并 DEFAULTS（缺失/损坏 → 默认 + 警告, 不阻塞）。"""
    data = settings.raw()
    if settings.last_error():                    # 文件在, 但读坏了
        logger.warning(err("SettingsLoad",
                           f"settings.toml 读取失败, 用默认: {settings.last_error()}"))
        return _deep_copy(DEFAULTS)
    # 合并默认（缺失分组补默认值; 用户配置优先）
    merged = _deep_copy(DEFAULTS)
    for section, fields in data.items():
        if not isinstance(fields, dict):
            continue
        merged.setdefault(section, {})
        for k, v in fields.items():
            merged[section][k] = v
    return merged


def save_settings(data: dict) -> None:
    """写 settings.toml —— 实现已下沉 `infra.settings.write`（唯一写入口）。

    "清洗 + 手写 toml" 从前只服务设置页, 现在「资源配置」辅助工具也要写 `[paths]`
    ⇒ 两处各写一份是事故来源（本仓已经因为"两处写"出过问题）, 收成一个写口。
    "这次不改某个键"仍由调用方过滤（本层对不可写的值只是跳过 = 该键消失）。
    """
    settings.write(data)


def mask_api_key(api_key: str) -> str:
    """打码: 非空 → '****' + 后 4 位（如 '****a8a7'）; 空 → 空串。"""
    if not api_key:
        return ""
    tail = api_key[-4:] if len(api_key) > 4 else api_key
    return f"{MASK_PREFIX}{tail}"


def is_masked(value: str) -> bool:
    """POST 收到的 api_key 是否打码标记（是 → 不改 key）。"""
    return isinstance(value, str) and value.startswith(MASK_PREFIX)


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------

def _deep_copy(data: dict) -> dict:
    return {k: dict(v) for k, v in data.items()}
