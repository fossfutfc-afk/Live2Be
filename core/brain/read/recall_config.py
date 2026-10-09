# -*- coding: utf-8 -*-
"""recall_config — 记忆召回旋钮（settings.toml `[recall]` 分组）。

**为什么单独一个模块**（DESIGN_WIKI_V3 §3.1/§3.5，2026-09-13 V3-0）:

v2 的记忆召回参数是**散落的模块常量**，后果有两条:

1. **没法按模型标定**。实测 `nomic-embed-text` 下无关对基线就有 0.60、真实 belief
   对 0.77~0.87; `Qwen3-Embedding-0.6B` 下是 0.26 / 0.53~0.71。**同一常数跨模型必然失效**。
2. **调参要改代码**。一次真机实验要改常量 + 重启 + 回滚，成本高到不会去做。

所以 V3-0 只做一件事: **把旋钮搬到配置面**。

## ⚠️ 2026-09-15（T17）: **三个阈值旋钮已删**

`cand_high` / `cand_med` / `accept_hit_rate` **全部删除**（用户裁决
*"cand_high 相关全删掉"*，落地 Q11/Q31/Q32）。**这里不再有任何"阈值"。**

删的理由（不是口味，是实测结论）:

- `cand_high` 驱动的是一条**硬闸门**（`>= 阈值` → 该 episode 禁 `add`），
  而它**从未被真机标定过**（标定时 embedding 服务没通）; Q11 实测 nomic 下
  "无关经历"(0.868) 比"相关经历"(0.819) 还高 → **单阈值原理上不可分**;
  两个模型下候选皆 **6/6 全越线** → 新认知永远长不出来。
- Q31 已定 **"召回不要阈值"**（用户: *"肯定不能要阈值"*）→ 排序取 top-k。
- `cand_med` 是**陪葬的**: Qwen3 的实测窗口是 (0.452, 0.682)，而 `cand_med=0.25`
  **低于窗口下界** → 它一条都筛不掉，是个"看着像旋钮、实际不做事"的值。

**留下的旋钮都不是阈值**，只有"取几条"与"半衰期"两类。

## settings.toml 形态（可选，不配也能跑）

    [recall]
      cand_k    = 3         # Round B 每条 episode 最多带几个候选（提示条数）
      sim_k     = 5         # 读路径语义通道 top-k
      like_k    = 3         # ⭐ 相似召回 `like.like()` 取几条（2026-10-08）
      turn_k    = 2         # ⭐ N5: MMT 每轮"你想起的事"摆几条（`recall.recall_episodes`）
      turn_budget = 700     # ⭐ N5: 那一段的**字符**预算（真闸门; "按 token 不按条数"）
      time_half_life_days  = 5.0   # A 链路新鲜度半衰期（**现实日**）
      time_freshness_floor = 0.25  # A 链路新鲜度**下界**（0 = 关掉下界）

## 优先级

`settings.toml [recall]` > 模块默认。缺失/损坏/类型不符 → 默认（宁缺勿错，不阻塞）。
与 `core/promptkit/config.py`、`llm/client.py` 同一读取模式（tomllib）。
"""
from __future__ import annotations

import logging
import tomllib

from core import paths

logger = logging.getLogger(__name__)

#: 项目根 settings.toml（`core/paths.py` 的宏）
_SETTINGS_PATH = paths.SETTINGS_PATH

#: 默认值 —— **全部非阈值**（只有"取几条"与"半衰期/下界"）
DEFAULTS: dict[str, float] = {
    "cand_k": 3.0,              # Round B 候选提示条数（recall.CAND_K）
    "sim_k": 5.0,               # recall_subgraph k_sim
    #: ⭐ 2026-10-08: **相似召回 `like` 取几条**（`like.LIKE_K`）—— 与 `cand_k`/`turn_k`
    #: 同类（"取几条", 不是阈值）。⚠️ 与 `turn_k` 是**两道不同的闸**: `turn_k` 是
    #: "MMT 每轮摆几条"（装填面, `render_recall_block` 的预算那一路）, `like_k` 是
    #: `like()` 自己的签名缺省 —— P19 真接上 `like` 那一笔再定两者怎么对齐。
    "like_k": 3.0,
    #: ⭐ N5（2026-09-29）: MMT 每轮"你想起的事"摆几条（`recall.recall_episodes`）。
    #: 与 `cand_k` 同类（"取几条"）; ⚠️ **它与下面那个预算是两道闸, 先撞到谁算谁**
    #: —— 条数是"顶多几条", 预算是"顶多几字", 真机那条 episode 长短不均, 两个都要。
    "turn_k": 2.0,
    #: ⭐ N5: 「你想起的事」那一段的**字符**预算（`render.render_recall_block`）。
    #: 设计原话是"召回预算按 token（不是条数）"（`docs/TODO.md` N5 ①）——
    #: 这里用字符是因为注入面本来就是按字符记台账的（`render` 的读数口径一致）,
    #: 中文下 1 字 ≈ 1 token, 换算不引入误差。
    "turn_budget": 700.0,
    #: `A_intensity` 链路的时间半衰期（**单位 = 现实日**）。
    #: 语义 = **新鲜度**（用户裁决 2026-09-13: *"TIME 做新鲜度语义, 这遗忘曲线
    #: 没办法适用了, 60 天跨度太大了"*）。
    #: ⚠️ **本注释原先写"单位 = 叙事日" + 换算式 `0.5 ** ((age_格 / 5) / hl)`**
    #: —— 那两样都随**时间轴换代**作废了（唯一日期轴 = 现实日期, 见
    #: `ESSAY_TIME_MODEL §10`; "格"= 1/5 叙事日的单位已不存在）。已改正。
    #: ⚠️ **数值 5.0 也待重标定**（它是按叙事日时代的口味定的）。
    "time_half_life_days": 5.0,
    #: 新鲜度**下界** —— `freshness(age, hl, floor)` 的 `floor`。
    #: `0.0` = 关掉下界（= 换代前的行为: 老记忆一路掉到 10⁻²²）。
    #: 见 `core/worldtime/age.py::freshness` 的 docstring（那里有实测的交叉点）。
    "time_freshness_floor": 0.25,
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
    """丢弃缓存（设置变更/**测试**用——下次 get 重新读盘）。

    ⚠️ 2026-09-21 复核: 一度被当作"零消费者"删掉——**错的**: 它有 11+ 处调用,
    全在 `tests/core/test_wiki_recall_ledger.py` 的 autouse fixture 里（进程级懒加载
    缓存必须逐用例清, 否则用例间串味）。**测试基础设施也是消费者**。
    """
    global _cache
    _cache = None


def snapshot() -> dict[str, float]:
    """当前全部旋钮（台账打印用——一次调用只读一次盘）。"""
    global _cache
    if _cache is None:
        _cache = _load()
    return dict(_cache)
