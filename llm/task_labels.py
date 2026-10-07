# -*- coding: utf-8 -*-
"""LLM 调用的 **task 标签**（节点 5b, 2026-09-21）——"这次调用是谁"的唯一真源。

## 为什么有它

测试桩此前按**中文关键字**认任务（`情绪标签` / `变更句数组` / `地点 id JSON` /
`选中的文件名` / `记录员` / `整理者`），而那些串全部来自 prompt 文案 ⇒ **改一次措辞
就让桩静默不命中**（ARCH_REVIEW P2-8；同类事故已发生过一次, 见 CLAUDE.md §4 的
`恰 N 项` 条目）。现在调用方在 `llm.chat(..., task=…)` 上**显式声明身份**:

· **不进 messages、不进 payload** —— 前缀缓存与夹具零影响;
· **进日志**（`llm chat task=emotion …`）—— 顺带补上生产侧那句一直缺的
  "这次调用是谁"（此前只能从 `json=y` + `max_tokens` 猜）;
· 测试桩读 `kw["task"]` 分派（`tests/stub_tasks.py` 是共享的应答助手）。

## 取值纪律

名字尽量复用 `llm/task_levels.py` 的**形态名**（mmt / bond / emotion / place / digest
——那份表管"档位与 max_tokens"，这份管"调用身份"），只在需要区分时加后缀:
`place`（句级锚点）vs `place_board`（板级换场翻译）vs `place_variant`（选图）、
⭐ `digest.record` / `digest.relate`（**与 `core/digest/rounds/` 的轮次 key 逐字同名**,
2026-09-29 乙-2 改名: 从前叫 `round_a` / `round_b` —— Round A/B 时代的遗留名;
2026-10-07 P1b-2: `digest.understand` → `digest.relate`, 那一轮换成"只判关系"）。

⚠️ 新增调用点 → 在这里加常量（`tests/core/test_stub_dispatch_guard.py` 会扫源码,
用未声明的标签直接红）; 新任务还要在 `tests/stub_tasks.py` 给出标准应答。
"""
from __future__ import annotations

#: 记录级情绪标注（`core/bond/emo_text.py`）**与** v1 整场批标
#: （`core/bond/emotion_annotate.py`）——两者应答形状相同, 所以共用一个标签
EMOTION = "emotion"
#: 句级地点锚点（`place_annotate.annotate_places`）→ 返回锚点数组
PLACE = "place"
#: 板级换场翻译（`place_annotate.resolve_place`）→ 返回 {"place": <键>}
PLACE_BOARD = "place_board"
#: 选图（`variant_annotate.pick_image`, 第二遍）→ 返回 {"image": <文件名>}
PLACE_VARIANT = "place_variant"
#: digest 记忆消化（`digest/llm_call.llm_chat`; 细分见下几行）
#: ⚠️ **细分标签的后缀 ≡ `core/digest/rounds/` 的轮次 key**（`digest_label(spec.label)`,
#: 而 `spec.label` 由 key 派生 —— 见 `rounds.RoundSpec`）。改名要两处一起改, 守门用例钉住。
DIGEST = "digest"
#: ⭐ **R0 切分员**（`rounds/split.py`）—— 每段的**第一步**: 划区间 + `abstract`
#: + **账目**（`state` / `id` / `due` —— "切片即账目", 2026-10-05 取代旧的 `keep`）。
#: ⚠️ 2026-09-29（N4d）新增: 它拿走了 R1 从前最重的那件事（划区间）。
#: ⭐ **2026-10-05（L8）: 收口轮删掉之后, digest 一共 5 个 LLM 轮**（split / record /
#: relate / attribute / group）—— 硬顶随之回到 **600**（见 `rounds.DIGEST_SEGMENT_HARD_CAP`）。
DIGEST_SPLIT = "digest.split"
#: ① R1 记录员（`rounds/record.py`）—— ⭐ 它**同时**是 note 账目的落地点（按 R0 的表产
#: `add` / `update` / `close`; 收口轮 2026-10-05 删）
DIGEST_RECORD = "digest.record"
#: ② L1 判关系（`rounds/relate.py`）—— ⭐ 只落边, **一个字正文都不写**
DIGEST_RELATE = "digest.relate"
#: ③ R3 归属（把本轮新节点挂到 entity 上 + 维护载荷）
DIGEST_ATTRIBUTE = "digest.attribute"
#: ⭐ N7（2026-09-29）**L2-a 分群** —— 每段的**最后一步**, 与 R1–R3 不同层:
#: 吃"她连过的块"（`akin` 连通块）, 产**群节点 + `member_of` 边**（引擎切块 + 只起名）
DIGEST_GROUP = "digest.group"
# ⚠️ ~~`DIGEST_CLOSE`~~（R4 收口）**2026-10-05（L8）删** —— 那一轮读的是 120 字转述,
# 而 R0 手里就是原文; 账目如今由 R0 判、由 R1 落。
# ⚠️ ~~`DIGEST_PANORAMA`~~（全景轮）**2026-09-29（N4a）已退役** —— 它没有输出了
# （`habits` 槽取消 · `on_mind` 改由 Round A 写; ⛔ 后者 2026-09-29 / N4e 也退役了）。
# 别把它加回来。
#: 主链（创作）——MMT 消息流 / Bond 记录流
MMT = "mmt"
BOND = "bond"

#: 全部合法标签（源码扫描守门用）
ALL: frozenset[str] = frozenset({
    EMOTION, PLACE, PLACE_BOARD, PLACE_VARIANT,
    DIGEST, DIGEST_SPLIT, DIGEST_RECORD, DIGEST_RELATE,
    DIGEST_ATTRIBUTE, DIGEST_GROUP, MMT, BOND,
})

#: 主链（输出是"创作"本身, 桩按脚本队列回）
MAIN: frozenset[str] = frozenset({MMT, BOND})

#: 旁路（标注/记忆消化: 廉价、可失败、由引擎兜底）
ANNOTATION: frozenset[str] = ALL - MAIN

#: 标签 → `llm/task_levels.py` 的**形态名**（档位 thinking + max_tokens 按形态取）。
#: `place` 一系的三个标签**共用 place 形态**——它们要做的事同类（低价值判定、off 思考、
#: 256 上限）, 分开只是为了测试桩/日志能区分"是哪一道"。
PROFILE_OF: dict[str, str] = {
    EMOTION: "emotion",
    PLACE: "place",
    PLACE_BOARD: "place",
    PLACE_VARIANT: "place",
    DIGEST: "digest",
    DIGEST_SPLIT: "digest",
    DIGEST_RECORD: "digest",
    DIGEST_RELATE: "digest",
    DIGEST_ATTRIBUTE: "digest",
    DIGEST_GROUP: "digest",
    MMT: "mmt",
    BOND: "bond",
}


def digest_label(round_label: str) -> str:
    """`digest/llm_call.llm_chat` 的 `label` → task 标签。

    label 缺省 `"digest"`（整轮）; 调用方传轮次 key（`"record"` / `"understand"` …）→ 细分标签。
    ⚠️ 传进来的就是 `rounds.RoundSpec.key`（`label` 那一格由 key 派生, 不再手写）。
    """
    lab = (round_label or "").strip()
    if not lab or lab == DIGEST:
        return DIGEST
    return f"{DIGEST}.{lab}"
