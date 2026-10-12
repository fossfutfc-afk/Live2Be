"""MMT 白名单（config/settings/mmt_registry.toml）— 作者维护: 哪些角色显示在桃信。

项目约定: 便于机器读取的用 toml（settings / mmt_registry）; 人审查方便的用 yaml（五件套）。

缺文件 → []（作者填了才显示）; 损坏 → 警告 + []（不阻塞, 宁缺勿错）。
"""
from __future__ import annotations

import logging
import tomllib

from core import paths
from core.common.errors import err

logger = logging.getLogger(__name__)

#: 白名单路径 = `core/paths.py` 的宏（config/settings/mmt_registry.toml）
REGISTRY_PATH = paths.MMT_REGISTRY_PATH


def load_mmt_registry() -> list[dict]:
    """读白名单 → [{id, state, bio, birthday}]（按文件顺序）; 缺文件/损坏 → []。

    state: active(正式) | experiment(半成品——显示但可标注)。
    bio: 社交媒体个人简介（MMT 展示; 五件套无此概念, 作者在 toml 填）。
    birthday: **显示用生日**（MMT 主页展示——显示真源在 toml; profile 的
      SIG~birthday 是给 AI 的日期概念, 两者分工不同, 作者人工保持一致）。
    只保留带 id 的合法条目; 未知字段忽略（宽容）。
    """
    if not REGISTRY_PATH.is_file():
        return []
    try:
        data = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning(err("RegistryLoad", f"mmt_registry.toml 读取失败: {e}"))
        return []
    entries: list[dict] = []
    for c in data.get("characters", []) or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not cid:
            continue
        state = c.get("state", "active")
        bio = c.get("bio", "")
        birthday = c.get("birthday", "")
        entries.append({
            "id": cid,
            "state": state if state in ("active", "experiment") else "active",
            "bio": bio if isinstance(bio, str) else "",
            "birthday": birthday if isinstance(birthday, str) else "",
        })
    return entries
