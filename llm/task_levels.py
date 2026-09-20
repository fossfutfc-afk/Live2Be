# -*- coding: utf-8 -*-
"""任务档位集中表 — thinking level（reasoning_effort） + max_tokens 唯一真源。

2026-09-02 集中管理（此前散落在 momotalk/bond_story/emotion_annotate/digest/
vn_cli/ide_agent 各自的常量与默认参数里——调一处忘一处）。

## thinking level 分三类（用户拍板分类）

| 任务类   | 档位      | 理由 |
|----------|-----------|------|
| main     | default   | 主对话/剧情创作（MomoTalk 消息流 + bond 场景）——跟随 settings.toml
|          |           | [llm].reasoning_effort（默认 high）; 想整体调创作思考深度 → 改 settings |
| emotion  | off       | 情绪标注——低价值快失败任务, 思考是纯浪费且截断引发 robust 链爆炸 |
| place    | off       | 地点变更标注——同 emotion 类低价值判定, 快失败快兜底（keep 保持画面） |
| digest   | high      | 记忆消化 Round A/B——深度认知/逐字校验（实验矩阵: low 浅 / high 最佳,
|          |           | 2026-09-02 拍板固定 high, 不随 settings 漂移） |

档位取值: default = 不注入（客户端按 settings [llm].reasoning_effort 默认档）;
off = **显式关闭思考**（传 `{"thinking": {"type": "disabled"}}`——DeepSeek
v4-flash 系**默认思考开启**, 不传参数 = 思考吃光 max_tokens 预算 → 空 content
+ finish_reason=length, 官方 issue deepseek-ai/DeepSeek-V3#1610 同型;
2026-09-08 真机定位, 传 disabled 后标注 4/4 一次通过且 500-900ms）;
low|medium|high = 显式覆盖（reasoning_effort）。

## max_tokens 分输出形态（同一任务类内输出长度不同）

| 形态      | 任务类 | max_tokens | 调用点 / 说明 |
|-----------|--------|-----------:|----------------|
| mmt       | main   |       4096 | MomoTalk 消息流 JSON + 对白（推理模型吃预算, 勿改小——462 截断事故） |
| bond      | main   |      16384 | 羁绊剧情记录流长输出块（思考 + 正文同预算）
|           |        |            | 2026-09-10 用户拍板 8192→16384: wiki 记忆只增不减, 思考水位持续上涨 |
| vn_cli    | main   |       1536 | CLI run_bond_story_vn 默认（历史值; 函数参数仍可覆盖） |
| emotion   | emotion|        512 | 标注数组输出（关 thinking 后足量） |
| place     | place  |        256 | 换场锚点数组（变更句稀疏输出, 256 足量） |
| digest    | digest |       8192 | Round A/B 长 JSON 决策（思考 + 输出同预算, high 长考实测 ~2min） |

## settings.toml 覆盖（可选, 不做也能跑）

    [llm.tasks.mmt]        thinking = "high"    # 覆盖档位（off/low/medium/high/default）
    [llm.tasks.emotion]    max_tokens = 768     # 覆盖输出上限

覆盖键按"输出形态"名（mmt/bond/vn_cli/emotion/place/digest）。
"""
from __future__ import annotations


from core import paths

#: 输出形态 → (thinking 档位, max_tokens, 备注)
PROFILES: dict[str, dict] = {
    "mmt":     {"thinking": "default", "max_tokens": 4096,
                "note": "MomoTalk 消息流 JSON + 对白"},
    "bond":    {"thinking": "default", "max_tokens": 16384,
                "note": "羁绊剧情记录流块级长输出（思考共预算; 2026-09-10 翻倍）"},
    "vn_cli":  {"thinking": "default", "max_tokens": 1536,
                "note": "CLI run_bond_story_vn 默认（参数可覆盖）"},
    "emotion": {"thinking": "off",     "max_tokens": 512,
                "note": "情绪标注数组（低价值, 快失败快兜底）"},
    "place":   {"thinking": "off",     "max_tokens": 256,
                "note": "地点变更锚点（稀疏数组; keep=保持画面）"},
    "digest":  {"thinking": "high",    "max_tokens": 8192,
                "note": "记忆消化 Round A/B 长 JSON 决策"},
}

_VALID_THINKING = ("default", "off", "low", "medium", "high")
#: settings.toml（`core/paths.py` 的宏 —— 项目根那一份）
_SETTINGS_PATH = paths.SETTINGS_PATH

_OVERRIDES: dict[str, dict] | None = None


def _load_overrides() -> dict[str, dict]:
    """settings.toml [llm.tasks] 覆盖（缺失/损坏 → {}; 非法值忽略）。"""
    global _OVERRIDES
    if _OVERRIDES is not None:
        return _OVERRIDES
    _OVERRIDES = {}
    try:
        import tomllib
        if not _SETTINGS_PATH.is_file():
            return _OVERRIDES
        data = tomllib.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        tasks = ((data.get("llm") or {}).get("tasks") or {})
    except (OSError, ValueError, ImportError):
        return _OVERRIDES
    if not isinstance(tasks, dict):
        return _OVERRIDES
    for name, ov in tasks.items():
        if not isinstance(ov, dict):
            continue
        base = PROFILES.get(name)
        if base is None:
            continue                                    # 未知形态名忽略
        merged: dict = {}
        th = str(ov.get("thinking") or "").strip().lower()
        if th:
            if th in _VALID_THINKING:
                merged["thinking"] = th
            # 非法档位忽略（保留默认）
        mt = ov.get("max_tokens")
        if isinstance(mt, int) and mt > 0:
            merged["max_tokens"] = mt
        if merged:
            _OVERRIDES[name] = merged
    return _OVERRIDES


def profile(name: str) -> dict:
    """取形态档位（含 settings 覆盖）: {"thinking", "max_tokens", "note"}。"""
    if name not in PROFILES:
        raise KeyError(f"未知任务形态: {name!r}（可选: {sorted(PROFILES)}）")
    p = dict(PROFILES[name])
    ov = _load_overrides().get(name) or {}
    p.update(ov)
    return p


def max_tokens(name: str) -> int:
    """形态输出上限（含覆盖）。"""
    return int(profile(name)["max_tokens"])


def extra_body(name: str) -> dict | None:
    """形态的 thinking 注入参数（含覆盖）:
    default → None（客户端按 settings [llm].reasoning_effort 默认档注入）;
    off → {"thinking": {"type": "disabled"}}（**显式关闭思考**——DeepSeek
    v4-flash 系默认思考开启, 空 dict 不传参数 = 思考吃光 max_tokens →
    空 content, 见模块顶部表注与 DeepSeek-V3#1610）;
    low|medium|high → 显式 reasoning_effort 档位。"""
    th = profile(name)["thinking"]
    if th == "default":
        return None
    if th == "off":
        return {"thinking": {"type": "disabled"}}
    return {"reasoning_effort": th}
