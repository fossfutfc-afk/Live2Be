"""recall_config — 记忆召回旋钮（`settings.toml [recall]` 分组）。

为什么单独一个模块: 旋钮从前是**散落的模块常量** ⇒ ① 没法按模型标定（同一常数跨模型必然
失效: `nomic` 下无关对 0.60 / 相关对 0.77~0.87, `Qwen3` 下 0.26 / 0.53~0.71）; ② 调参要改
代码 + 重启, 成本高到不会去做。所以把旋钮搬到配置面。

**这里的旋钮都不是"阈值"**, 只有两类: 取几条 · 半衰期 / 下界。
（阈值旋钮 `cand_high` / `cand_med` / `accept_hit_rate` 已删: 单阈值在实测中原理上不可分
—— nomic 下"无关经历"比"相关经历"还高, 两个模型下候选全都越线。）

    [recall]
      cand_k    = 3         # Round B 每条 episode 最多带几个候选（提示条数）
      sim_k     = 5         # 读路径语义通道 top-k
      like_k    = 3         # 相似召回 `like.like()` 取几条
      turn_k    = 2         # MMT 每轮"你想起的事"摆几条（`recall.recall_episodes`）
      turn_budget = 1000    # **每段**召回的字符预算（「你想着「X」」/「你想起的事」各算一次）
      time_half_life_days  = 5.0   # A 链路新鲜度半衰期（**现实日**）
      time_freshness_floor = 0.25  # A 链路新鲜度下界（0 = 关掉）

优先级: `settings.toml [recall]` > 模块默认; 缺失 / 损坏 / 类型不符 → 默认（宁缺勿错）。
读盘走 `infra/settings`（**不缓存、每次重读**）⇒ 手改 `[recall]` 下一次调用即生效。
"""
from __future__ import annotations

from infra import settings

#: 默认值 —— **全部非阈值**（只有"取几条"与"半衰期/下界"）
DEFAULTS: dict[str, float] = {
    "cand_k": 3.0,              # Round B 候选提示条数（recall.CAND_K）
    "sim_k": 5.0,               # recall_subgraph k_sim
    #: 2026-10-08: **相似召回 `like` 取几条**（`like.LIKE_K`）—— 与 `cand_k`/`turn_k`
    #: 同类（"取几条", 不是阈值）。与 `turn_k` 是**两道不同的闸**: `turn_k` 是
    #: "MMT 每轮摆几条"（装填面, `render_recall_block` 的预算那一路）, `like_k` 是
    #: `like()` 自己的签名缺省 —— P19 真接上 `like` 那一笔再定两者怎么对齐。
    "like_k": 3.0,
    #: N5（2026-09-29）: MMT 每轮"你想起的事"摆几条（`recall.recall_episodes`）。
    #: 与 `cand_k` 同类（"取几条"）; **它与下面那个预算是两道闸, 先撞到谁算谁**
    #: —— 条数是"顶多几条", 预算是"顶多几字", 真机那条 episode 长短不均, 两个都要。
    "turn_k": 2.0,
    #: N5: **P19 每一段**的**字符**预算（`render.render_candidates` / `render_section`）。
    #: 设计原话是"召回预算按 token（不是条数）"（`docs/TODO.md` N5 ①）——
    #: 这里用字符是因为注入面本来就是按字符记台账的（`render` 的读数口径一致）,
    #: 中文下 1 字 ≈ 1 token, 换算不引入误差。
    #: **P19 一次是两段**（`name` 名字段 + `turn` 兜底段, 见 `read/modes.py`）——
    #: 每段**各自**读这一个数 ⇒ 两段撞满时合计 ≈ 2×（2026-10-12 用户: "给 1000 字符吧先"）。
    "turn_budget": 1000.0,
    #: `A_intensity` 链路的时间半衰期（**单位 = 现实日**）。
    #: 语义 = **新鲜度**（*"TIME 做新鲜度语义, 这遗忘曲线
    #: 没办法适用了, 60 天跨度太大了"*）。
    #: **本注释原先写"单位 = 叙事日" + 换算式 `0.5 ** ((age_格 / 5) / hl)`**
    #: —— 那两样都随**时间轴换代**作废了（唯一日期轴 = 现实日期, 见
    #: `ESSAY_TIME_MODEL §10`; "格"= 1/5 叙事日的单位已不存在）。已改正。
    #: **数值 5.0 也待重标定**（它是按叙事日时代的口味定的）。
    "time_half_life_days": 5.0,
    #: 新鲜度**下界** —— `freshness(age, hl, floor)` 的 `floor`。
    #: `0.0` = 关掉下界（= 换代前的行为: 老记忆一路掉到 10⁻²²）。
    #: 见 `core/worldtime/age.py::freshness` 的 docstring（那里有实测的交叉点）。
    "time_freshness_floor": 0.25,
}

def _load() -> dict[str, float]:
    """settings.toml → 归一化旋钮（损坏 → 全默认；只认数值型）。"""
    out = dict(DEFAULTS)
    section = settings.section("recall")
    for key in DEFAULTS:
        val = section.get(key)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue                                 # 类型不符 → 保持默认
        out[key] = float(val)
    return out


def get(name: str) -> float:
    """取旋钮值（未知键 → KeyError——防拼错静默走默认）。"""
    if name not in DEFAULTS:
        raise KeyError(f"未知 recall 旋钮: {name!r}（可用: {sorted(DEFAULTS)}）")
    return _load()[name]


def snapshot() -> dict[str, float]:
    """当前全部旋钮（台账打印用）。"""
    return _load()
