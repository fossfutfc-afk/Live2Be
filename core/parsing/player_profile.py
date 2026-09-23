# -*- coding: utf-8 -*-
"""player_profile.py — 玩家（老师）档案 `config/player/profile.yml`（2026-09-23 建立）。

## 为什么玩家要有一份 config 档案

`self` entity 的名字/别名全来自角色人设（`profile.yml`），而 sensei 那一套此前**硬编码**
在 `wiki_v2/entities.py`（`SENSEI_NAMES = ("老师", "sensei")`）—— 同一件事两套来源。
用户 2026-09-23 裁决: 玩家也走 config，**一份 `profile.yml`、同一套字段前缀约定**
⇒ 白拿 `names.char_names()` 的三级回落（裸键 → `SIG~` → `REQ~`）、四种分隔符切分、
长度护栏与去重；"老师"于是只剩 `contract.DEFAULT_SPEAKER_NAMES` 那一份**兜底**。

## 两个写者，别合并（用户裁决 ①）

| | `config/player/profile.yml`（本模块） | `data/basic/player.json` |
|---|---|---|
| 谁写 | **作者**（进 git） | **玩家自己**（GUI/CLI; 带长度/符号校验 + 取名彩蛋） |
| 住哪 | `CONFIG_DIR` | `DATA_DIR`（gitignored） |
| 给什么 | entity 的**主名** + 作者别名 | 玩家自取名 → 追加成**一条别名** |

## 读失败 = 报错，**不兜底**（用户裁决 ④）

⚠️ 别的配置读不到可以静默降级（宁缺勿错），**这一份不行**: 静默退回"老师"会让一个坏文件
**永远不被人发现**。所以文件不存在 / YAML 坏 / 缺 `REQ~most_called_name` 一律**抛错**，
错误里带路径; 由调用方决定怎么办（现网 = `MmtEngine._ensure_char_entities` 中止本轮
digest 并打 ERROR —— 水位不推进, 修好即恢复）。

## 只做两件事

`load_player_profile()` 读 yml（**不缓存** —— digest 很低频, 且改了要立刻生效）;
`player_names()` = `char_names(上面那份)`。**纯读, 不写**。
"""
from __future__ import annotations

from typing import Any

from core import paths
from core.common import err
from core.parsing.dynamic_character_parser import load_yaml_file
from core.parsing.names import CharNames, char_names

#: 玩家档案的必填字段（`REQ~` = 必填层的约定, 与角色档案同一套）。
REQUIRED_FIELD = "most_called_name"

#: 缺字段时的报错类型（可 grep: `PlayerProfileIncomplete`）
ERR_INCOMPLETE = "PlayerProfileIncomplete"


def load_player_profile() -> dict[str, Any]:
    """读 `config/player/profile.yml` → 原始 dict。

    Raises:
        FileNotFoundError: 文件不存在（`load_yaml_file` 抛, 带路径）
        yaml.YAMLError: YAML 语法错误
        ValueError: 内容不是 dict, 或缺 `REQ~most_called_name`

    ⚠️ **不兜底**: 见模块 docstring（用户 2026-09-23 裁决）。
    ⚠️ 必填检查看的是**原始 `REQ~` 键**（不是 `get_display_name` 的兜底值）——
    后者缺字段时会返回"未知角色", 那正是"静默兜底"要避免的东西。
    """
    path = paths.PLAYER_PROFILE_PATH
    data = load_yaml_file(path)
    if not str(data.get(f"REQ~{REQUIRED_FIELD}") or "").strip():
        raise ValueError(err(ERR_INCOMPLETE,
                             f"{path} 缺必填字段 REQ~{REQUIRED_FIELD}（玩家显示名）"))
    return data


def player_names() -> CharNames:
    """玩家档案 → `CharNames`（**主名 + 作者别名**; 玩家自取名不在这里, 见模块 docstring）。"""
    return char_names(load_player_profile())


__all__ = ["ERR_INCOMPLETE", "REQUIRED_FIELD", "load_player_profile", "player_names"]
