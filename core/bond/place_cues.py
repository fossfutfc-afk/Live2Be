"""place_cues — 换场**线索词**（PL3, 2026-09-19）: 板内没有它就根本不问标注 LLM。

## 它解决什么

`annotate_places`（句级锚点）每板恒定一次调用（7022 字符 prompt）。
但它的**唯一用途**是救一种情形: **writer 描述了移动却没发 `switch`**
（`switch` 会开新板, 所以板级地点本来就由它决定）。真机实测（2026-09-19）:

    20 板 / 93 段正文 → 含线索词的板 **0/20** ⇒ 20 次调用**零收益**
    （正文几乎全是对话/独白, 位移都写在 `switch` 里, 而 switch 不进 paragraphs）

⇒ 先用这份**纯字符串**线索表过一遍（0 调用）, 没有线索就整板跳过标注。

## 为什么取"宽"而不是取"准"

判据 = **代价不对称**:
* 误报（有线索其实没换场）→ 多花一次廉价调用（**就是今天的行为**）
* 漏报（真换场却无线索）→ 画面不切

所以宁滥勿缺, 把"穿过边界的位移动词"尽量收全。**故意排除**那些
`place_annotate.md` 明确判为"不换场"的词: `转身` / `走近窗边` / `坐下` / `蹲下`
—— 收了它们等于把预筛关掉。

## 同源纪律（`CORE_CUES`）

`CORE_CUES` 是**必须同时出现在两份 prompt 里**的核心子集:
`bond_story_rules.md §五【换场】` 与 `llm/prompts/place_annotate.md` 的「强线索句式」。
`tests/core/test_place_annotate.py::test_judgement_mirror_between_rules_and_prompt`
钉住这一点 —— **改判据时三处一起改**（rules / annotate prompt / 本表）。

`CUES` 是本表的全量（比 `CORE_CUES` 宽）, 引擎只用它做预筛。
"""
from __future__ import annotations

from typing import Iterable

#: 预筛用的全量线索词（**宽**; 见模块 docstring 的代价不对称说明）
CUES: tuple[str, ...] = (
    # 出 / 进 / 入 —— 穿过边界
    "走出", "走进", "走入", "跨出", "跨进", "踏出", "踏进", "钻出", "钻进",
    "冲出", "冲进", "跑出", "跑进", "溜出", "溜进", "闯进", "出了", "进了",
    # 升降 —— 换层
    "走上", "走下", "上楼", "下楼", "爬上", "爬下",
    # 到达 / 返回 / 前往
    "来到", "回到", "赶往", "前往", "抵达", "到达", "奔向", "跑向", "冲向",
    # 穿过 / 经过 / 推拉门
    "穿过", "路过", "推开", "拉开",
    # 只表明"离开"、不表明去哪 —— 交给 LLM 判
    "离开",
)

#: **必须与两份 prompt 逐字一致**的核心子集（镜像防漂移测试钉它）
CORE_CUES: tuple[str, ...] = ("走进", "来到", "回到", "推开", "穿过")


def cue_in(text: str) -> str | None:
    """`text` 里命中的第一个线索词（没有 → None）。给日志用。"""
    t = text or ""
    for c in CUES:
        if c in t:
            return c
    return None


def has_cue(texts: Iterable[str]) -> str | None:
    """这批文本里有没有换场线索 → 命中的那个词 / None。

    返回命中的词（而不是 bool）是为了让日志能写清"为什么这一板要扫":
    `[place][SCAN] cue=推开` 比 `cue=True` 可排查得多。
    """
    for t in texts or ():
        hit = cue_in(t)
        if hit:
            return hit
    return None


__all__ = ["CUES", "CORE_CUES", "cue_in", "has_cue"]
