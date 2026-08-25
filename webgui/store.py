# -*- coding: utf-8 -*-
"""GUI 配置存储（settings.toml）— 与路由分离的配置层。

**定位**: 仅 GUI 设置页的读写存档。引擎（llm/image_gen）**仍从 .env 读**——
本文件是给未来接入留的桩: 引擎接入时改为"settings.toml 非空字段优先, .env 兜底"。

文件: 项目根 settings.toml（gitignore, 与 .env 并列——运行时用户配置）。

结构（v1, 平铺分组; 未来 per 角色参数加 [characters.xxx]）:
    [llm]
      api_key = ""          # 空 = 用 .env 的 LLM_API_KEY
      base_url = "https://api.deepseek.com"
      model = "deepseek-chat"
    [image]
      api_key = ""
      base_url = "https://api.apiyi.com"

写: 手写轻量 toml 序列化（分组 + k=v, 值 str/int/bool——够用;
     未来复杂类型（列表/嵌套）再升级 tomli_w）。
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.common.errors import err

logger = logging.getLogger(__name__)

#: settings.toml 位置（项目根——与 .env 并列, 用户容易找到）
#: 注意层级: webgui/store.py → parent=webgui → parent.parent=Live2Be（项目根）
SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.toml"

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
        "model": "gemini-3.1-flash-lite-image"
    },
}

#: api_key 打码标记（GET 返回用; POST 收到此标记 = 不改 key）
MASK_PREFIX = "已设置 ****"


def load_settings() -> dict:
    """读 settings.toml → dict（缺失/损坏 → 默认 + 警告, 不阻塞）。"""
    if not SETTINGS_PATH.is_file():
        return _deep_copy(DEFAULTS)
    try:
        import tomllib
        data = tomllib.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, ImportError) as e:
        logger.warning(err("SettingsLoad", f"settings.toml 读取失败, 用默认: {e}"))
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
    """写 settings.toml（只保留已知分组/字段, 防垃圾键）。"""
    clean: dict = {}
    for section, fields in DEFAULTS.items():
        clean[section] = {}
        src = data.get(section, {}) if isinstance(data, dict) else {}
        for key, default in DEFAULTS[section].items():
            val = src.get(key, default)
            if isinstance(val, str) or isinstance(val, (int, float, bool)):
                clean[section][key] = val
    SETTINGS_PATH.write_text(_to_toml(clean), encoding="utf-8")
    logger.info("settings.toml 已保存: %s", SETTINGS_PATH)


def mask_api_key(api_key: str) -> str:
    """打码: 非空 → '已设置 ****last4'; 空 → 空串。"""
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


def _to_toml(data: dict) -> str:
    """轻量 toml 序列化（分组 + k=v; 值 str/int/float/bool）。"""
    lines: list[str] = []
    for section, fields in data.items():
        lines.append(f"[{section}]")
        for k, v in fields.items():
            if isinstance(v, bool):
                lines.append(f'  {k} = {"true" if v else "false"}')
            elif isinstance(v, (int, float)):
                lines.append(f"  {k} = {v}")
            else:
                escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'  {k} = "{escaped}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
