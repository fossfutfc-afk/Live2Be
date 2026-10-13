"""`contract.digest` —— 记忆整理（digest）那七轮 LLM 输出的**契约单源**。

digest 从前是"数据产出"风格: 手写 schema（LLM 可见面）与 `revise.py` 手写校验（runtime
接受面）**两处双写**, 漂移源。现在是一份**动作注册表**: 一份文档一份 spec, 同一份 spec
驱动两层 —— `build_schema(phase)` 渲染 prompt 里的输出格式, `parse_*` 做结构校验
（宁缺勿错, 逐条报错; 内容质量只 warning, 引用级 / 图语义交给引擎执行层）。

## 五个模块: 按"谁读它"分家

| 模块 | 装什么 | 谁读 |
|---|---|---|
| `tables.py` | **值表** —— 相位名 / 上限 / 取值域 / 日期格式 | 只有机器; ⛔ 一句给 LLM 看的话都没有 |
| `prompts/` | **文案**（md）—— 每个相位要说给 LLM 听的那段字 + 共用片段 | 人改; `registry` 读它 + 填槽 |
| `docs.py` | **文档清单** —— 哪个相位有哪几份文档（名称 / 相位） | `actions(phase)` · `parse` 的键域 |
| `parse.py` | 七个相位的**结构校验** | 引擎执行层 |
| `registry.py` | 取哪份 md + 槽填什么 + 七个薄委托 | 调用点 |

⚠️ **加载顺序**: `contract.slots` → tables → docs / prompts → parse → registry, **单向**。
所以包内子模块之间一律**直接**互导（`from contract.digest.tables import X`）——
⛔ **不许经本文件**, 那会把环接回来。

## 本文件只做再导出

对外只有这一个入口: `from contract.digest import PHASE_SPLIT, digest_registry, …`。

⚠️ **私有名刻意不在这里**（`_split_tags` / `_domain_part` …）: 要用的地方写全路径
（`from contract.digest.parse import _split_tags`）—— 让"我在碰私有名"在调用点看得见,
而不是从门面混出来。

⚠️ 不用 `from .x import *`: 下划线名会当场丢, 而且"这个包对外有什么、住在哪"就读不出来了。
"""
from __future__ import annotations

from contract.digest.docs import (  # 文档清单（哪个相位有哪几份文档）
    COGNIZE_ACTIONS,
    DEFAULT_ACTIONS,
    OUTPUT_DISCIPLINE,
    OUTPUT_RULES,
    RECORD_EPISODE,
    RELATION_ACTIONS,
    DigestAction,
)
from contract.digest.parse import (  # 七个相位的结构校验
    parse_attribution,
    parse_cognitions,
    parse_group,
    parse_relations,
    parse_round_a,
    parse_split,
)
from contract.digest.prompts import (  # 契约文案仓库（md）+ 填槽
    fill,
    fragment,
    load,
)
from contract.digest.registry import (  # 建表 + 渲染 schema + 七个薄委托 + 单例
    DigestRegistry,
    digest_registry,
)
from contract.digest.tables import (  # 值表（相位名 / 上限 / 取值域 / 日期格式）
    ABSTRACT_MAX,
    ABSTRACT_MAX_FREEFORM,
    COGNIZE_ANCHORS,
    COGNIZE_KEYS,
    COGNIZE_RETIRED,
    ENTITY_TAG_PREFIX,
    ENTITY_TAGS_MAX,
    GROUP_TITLE_MAX,
    MAX_ALIASES,
    MAX_COGNITIONS,
    MAX_EPISODES,
    MAX_SEGMENTS,
    MAX_TAGS,
    MAX_TEXT,
    PHASE_COGNIZE,
    PHASE_DEEP,
    PHASE_GROUP,
    PHASE_RECORD,
    PHASE_RELATE,
    PHASE_SETTLE,
    PHASE_SPLIT,
    PLAYER_SUBJECT,
    RELATION_ANCHORS,
    STATE_VALUES,
    TOPICS_MAX,
    is_full_date,
)
