"""契约常量与通用约束 — 最底层，零依赖。

所有上层模块（model / spec / registry / schema）都引用这里的常量。
本文件不 import 任何本包模块，只依赖标准库。

内容:
    审批策略、动作域、通用 id 校验、外壳字段集合、字段上限。
"""

from __future__ import annotations

import re
from typing import Any

# ============================================================================
# 审批策略 — 决定动作如何被处理
# ============================================================================

APPROVAL_REQUIRED = "required"   # 写动作：用户批准后才执行（辅助项目写配置）
APPROVAL_AUTO     = "auto"       # 规则校验通过即执行（主项目运行时）
APPROVAL_NEVER    = "never"      # 只读/抓取：直接执行（fetch_url 等）

# ============================================================================
# 动作域（domain）— 分门别类，域之间隔离
# ============================================================================

DOMAIN_IDE = "ide"       # 辅助项目（配置写入）
DOMAIN_MMT = "mmt"       # MomoTalk 运行时（未来 agent：模拟手机操作）
DOMAIN_STORY = "story"   # 羁绊剧情运行时（表情/背景切换）

# ============================================================================
# 通用约束
# ============================================================================

# 通用标识符（角色 id / 关系名等）：小写字母、数字、下划线。
# 正则本身排除路径穿越 / 注入——id 校验是写入安全的第一道防线。
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9_]+$")
MAX_ID_LENGTH = 64

# 外壳字段上限
MAX_SUMMARY_LENGTH = 500
MAX_SOURCE_COUNT = 20
MAX_BASIS_COUNT = 20

# 外壳字段全集 — LLM 可见的外壳字段均来自此集合。
ALL_SHELL_FIELDS = frozenset({"action", "summary", "payload", "sources", "basis"})

# 运行时动作常用的最小外壳字段集（无证据字段）。
# Story / MMT 动作注册时传这个，AI 的 schema 里就不会出现 sources/basis。
RUNTIME_SHELL_FIELDS = frozenset({"action", "summary", "payload"})


# ============================================================================
# 通用校验
# ============================================================================

def is_valid_identifier(name: Any) -> bool:
    """通用 id 校验（角色 id / 关系名共用）。

    Returns:
        True 当 name 是非空 str、≤64 字符、且匹配 [a-z0-9_]+。
    """
    return (
        isinstance(name, str)
        and len(name) <= MAX_ID_LENGTH
        and bool(IDENTIFIER_PATTERN.fullmatch(name))
    )
