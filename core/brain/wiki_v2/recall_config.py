# -*- coding: utf-8 -*-
"""recall_config — 记忆召回旋钮（settings.toml `[recall]` 分组）。

**为什么单独一个模块**（DESIGN_WIKI_V3 §3.1/§3.5，2026-09-13 V3-0）:

v2 的记忆召回参数是**散落的模块常量**（`recall.CAND_HIGH=0.50` 等），后果有两条:

1. **没法按模型标定**。`CAND_HIGH` 决定"能不能 add 出新 belief"——`>= 0.50` 的
   候选被 `parse_round_b` **结构强制**只能 touch/update。而实测（审计 §10）:
   `nomic-embed-text` 下无关对基线就有 0.60、真实 belief 对 0.77~0.87;
   `Qwen3-Embedding-0.6B` 下是 0.26 / 0.53~0.71。**同一常数跨模型必然失效**。
2. **调参要改代码**。一次真机实验要改常量 + 重启 + 回滚，成本高到不会去做。

所以 V3-0 只做一件事: **把旋钮搬到配置面，且默认值 = 现值**（行为零变化）。
真正的标定是 V3-3/V3-4 的工作，本模块只提供可调入口与可观测口径。

## settings.toml 形态（可选，不配也能跑）

    [recall]
      cand_high = 0.50      # 候选碰撞上限阈值（>= 即判【疑似同主题】）
      cand_med  = 0.25      # 参考阈值（>= 标注【可能相关】）
      cand_k    = 3         # 每条 episode 最多带几个候选
      sim_k     = 5         # 读路径语义通道 top-k
      accept_hit_rate = 0.5 # 健康位: 结构强制命中率超过它就值得告警（仅台账用）

## 优先级

`settings.toml [recall]` > 模块默认。缺失/损坏/类型不符 → 默认（宁缺勿错，不阻塞）。
与 `core/promptkit/config.py`、`llm/client.py` 同一读取模式（tomllib）。
"""
from __future__ import annotations

import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

#: 项目根 settings.toml（core/brain/wiki_v2/ → parents[3]）
_SETTINGS_PATH = Path(__file__).resolve().parents[3] / "settings.toml"

#: 默认值 —— **与 v2 模块常量逐字一致**（V3-0 行为零变化）
DEFAULTS: dict[str, float] = {
    "cand_high": 0.50,          # recall.CAND_HIGH
    "cand_med": 0.25,           # recall.CAND_MED
    "cand_k": 3.0,              # recall.CAND_K
    "sim_k": 5.0,               # recall_recall_subgraph k_sim
    "accept_hit_rate": 0.5,     # 台账告警线（不参与判定）
}

_cache: dict[str, float] | None = None


def _load() -> dict[str, float]:
    """读 settings.toml → 归一化旋钮（失败 → 全默认; 只认数值型）。"""
    out = dict(DEFAULTS)
    try:
        with open(_SETTINGS_PATH, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return out
    except Exception as e:                           # noqa: BLE001 — 损坏不阻塞
        logger.warning("recall settings 读取失败, 用默认: %s", e)
        return out
    section = data.get("recall")
    if not isinstance(section, dict):
        return out
    for key in DEFAULTS:
        val = section.get(key)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue                                 # 类型不符 → 保持默认
        out[key] = float(val)
    return out


def get(name: str) -> float:
    """取旋钮值（首次访问懒加载; 未知键 → KeyError——防拼错静默走默认）。"""
    global _cache
    if _cache is None:
        _cache = _load()
    if name not in DEFAULTS:
        raise KeyError(f"未知 recall 旋钮: {name!r}（可用: {sorted(DEFAULTS)}）")
    return _cache[name]


def reload() -> None:
    """丢弃缓存（设置变更/测试用——下次 get 重新读盘）。"""
    global _cache
    _cache = None


def snapshot() -> dict[str, float]:
    """当前全部旋钮（台账打印用——一次调用只读一次盘）。"""
    global _cache
    if _cache is None:
        _cache = _load()
    return dict(_cache)
