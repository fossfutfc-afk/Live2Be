# -*- coding: utf-8 -*-
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


#: 标量类型（settings.toml 叶子只能是这些; dict/None 等一律拒收——见 `_sane_value`）
_SCALARS = (str, bool, int, float)      # 注意: bool 是 int 子类, 须先判 bool


def _sane_value(v) -> bool:
    """**叶子**值是否可安全写进 settings.toml 并被 `load_settings` 读回。

    dict/list 拒收——不是"防垃圾键"的洁癖: `_to_toml` 里它会被 `str(v)` 降级成
    一段**看起来合法的 TOML 字符串**（如 `me = "{'a': 1}"`），读回时类型静默漂移。
    宁缺勿错: 拒收 → 该键不写, 比写坏配置好。
    """
    return v is None or isinstance(v, _SCALARS)


def _sane_table(v) -> bool:
    """**表**（嵌套 dict）是否可写: 键全为 str, 值**递归**合法（叶子或子表）。

    与 `_sane_value` 分开是必须的: 表本身是 dict, 拿叶子判据去量它必然 False
    → 嵌套表会被整张清空（`[llm.tasks.emotion]` 的覆盖语法就此消失）。
    """
    if not isinstance(v, dict) or not v:
        return False
    for k, sub in v.items():
        if not isinstance(k, str):
            return False
        if isinstance(sub, dict):
            if not _sane_table(sub):
                return False
        elif not _sane_value(sub):
            return False
    return True


def save_settings(data: dict) -> None:
    """写 settings.toml —— **保真落盘**: 文件名下有什么就写回什么。

    2026-09-13 修正（审计 A1）: 原实现只遍历 `DEFAULTS` 的已知分组/字段
    （llm 三键 + image）→ 而 `DEFAULTS` 里根本没有 `bond` 段、`llm` 也没有
    `reasoning_effort`/`use_proxy` —— **用户每点一次设置页保存, 这些键就被裁掉**。
    `routers/settings.py:46` 本就把完整 `load_settings()` 结果交给本函数, 所以
    丢数据的**唯一**原因就是这里的白名单裁剪。

    现在: 以传入结构为准全量写回（**深度保真**, 含嵌套表如 `[llm.tasks.emotion]`）,
    只做**类型防呆**: 叶子非标量（dict/list 等）→ 跳过不写; 表递归校验
    （`_sane_value` / `_sane_table`）。"防垃圾键"的职责归调用方
    （`routers/settings.py` 只从 POST body 取已知 section）; 本层不该用"丢弃"
    来实现校验——丢掉的是**用户手工维护的真配置**。

    已知取舍: `_to_toml` 是整文件重写, **注释不保留**（tomllib 解析后即丢）。
    要把注释也留住需引入 tomlkit 类的"带格式解析"依赖——当前依赖面刻意保持最小。
    """
    clean: dict = {}
    if not isinstance(data, dict):
        data = {}
    for section, fields in data.items():
        if not isinstance(section, str) or not isinstance(fields, dict):
            continue                       # 非表值（顶层标量）不写——TOML 顶层须先出表
        out: dict = {}
        for key, val in fields.items():
            if not isinstance(key, str):
                continue
            if isinstance(val, dict):
                # 嵌套表（[llm.tasks.emotion]）: 递归判据, 非法表整体跳过
                if _sane_table(val):
                    out[key] = val
                continue
            if _sane_value(val):
                out[key] = val
            # 非法值（dict/list 等）→ **跳过**（保持不写）。不回落 DEFAULTS:
            # 那是另一份数据, 替进去等于用默认值覆盖用户原值。
        clean[section] = out
    SETTINGS_PATH.write_text(_to_toml(clean), encoding="utf-8")
    logger.info("settings.toml 已保存: %s", SETTINGS_PATH)


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


def _to_toml(data: dict) -> str:
    """轻量 toml 序列化（分组 + k=v; 值 str/int/float/bool; **支持嵌套表**）。

    嵌套 dict → `[a.b]` 表（TOML 里子表必须排在父表标量之后; 本函数先写标量再
    递归写子表, 顺序天然合法）。2026-09-13: 原先无此分支 → 嵌套值走 `str(v)`
    被写成一段"看起来合法的字符串", 读回时静默变成 str（`[llm.tasks.*]` 覆盖语法
    一旦被写盘就废掉）。
    """
    lines: list[str] = []
    _emit_table(data, (), lines)
    return "\n".join(lines).rstrip() + "\n"


def _emit_table(data: dict, prefix: tuple[str, ...], lines: list[str]) -> None:
    """写一张表: 先标量、后子表（TOML 表头顺序要求）。

    只含子表的中间表**不写空表头**（`[llm.tasks]` 后紧跟 `[llm.tasks.emotion]`
    是冗余噪声; `source["tasks"]` 仍被隐式建出, 语义等价）。
    """
    scalars, tables = [], []
    for k, v in data.items():
        (tables if isinstance(v, dict) else scalars).append((k, v))
    # 空表也要出表头（否则键整个消失）; 只含子表的中间表则省略（冗余噪声）
    if prefix and (scalars or not tables):
        lines.append("[" + ".".join(prefix) + "]")
    for k, v in scalars:
        if isinstance(v, bool):
            lines.append(f'  {k} = {"true" if v else "false"}')
        elif isinstance(v, (int, float)):
            lines.append(f"  {k} = {v}")
        else:
            escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'  {k} = "{escaped}"')
    if prefix and (scalars or not tables):
        lines.append("")
    for k, v in tables:
        _emit_table(v, prefix + (k,), lines)
