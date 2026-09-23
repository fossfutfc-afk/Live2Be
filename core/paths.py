# -*- coding: utf-8 -*-
r"""paths — **固定路径的唯一清单**（macro 形态, 全部平铺在本文件顶层）。

## 约定（用户 2026-09-19）

> *"这种固定路径我推荐你写成 macro 的形式放在最上面，因为说不准这类路径进行
> 更改，最后改成你用 grep 能直接全量定位的方法。"*

1. **不许在函数体里现拼路径**——`Path(__file__)... / "config" / "..."` 散在各模块
   就是"下次改目录时找不到的东西"。一律在本文件顶层写一个常量。
2. 消费方: `from core import paths` → `paths.REGIONS_PATH`（**写全 `paths.`**，
   别 `from core.paths import X`——否则 grep 消费点时要猜别名）。
3. 模块**自己的**默认值常量可以保留（`DEFAULT_REGIONS_PATH = paths.REGIONS_PATH`），
   因为那是公开 API/构造参数默认值; 但**值的来源只有这里一处**。
4. 命名: 文件 `*_PATH` / 目录 `*_DIR` / 根 `ROOT`。

## 全量定位（两条 grep，就够了）

```bash
grep -n "^[A-Z][A-Z_]* = " core/paths.py        # ① 清单本身（有哪些固定路径）
grep -rn "paths\.[A-Z]" --include=*.py .         # ② 谁在用（消费点）
```

## 为什么放在 `core/` 而不是 `config/`

它是**代码**（要被 import），不是配置; `config/` 是给作者改的数据。
真正的运行时可覆盖项走 `settings.toml`（运行时配置, gitignore）与各模块的
构造参数——本文件只是**出厂默认值**的家。
"""
from __future__ import annotations

from pathlib import Path

#: 项目根（`core/paths.py` → 上一级）
ROOT = Path(__file__).resolve().parent.parent

# ── 运行时配置（settings.toml, gitignore; 缺失即全默认）────────────────────
SETTINGS_PATH = ROOT / "settings.toml"

# ── config/：作者手编的数据 ────────────────────────────────────────────────
CONFIG_DIR = ROOT / "config"
#: 角色卡根目录（`config/characters/{char_id}/` 六文件; `CharacterLoader` 的 root）
CHARACTERS_DIR = CONFIG_DIR / "characters"
#: 玩家（老师）档案目录 —— **只有这一个文件**（2026-09-23）: 身份/称呼, 与角色档案同一套
#: 字段前缀约定（所以直接吃 `core/parsing/names.char_names`）。
#: ⚠️ 与 `data/basic/player.json` 分工: 这里是**作者层**（进 git, 给 sensei entity 的主名+
#: 别名）; player.json 是玩家自己在 GUI 里改的名字（运行时数据, 追加成一条别名）。
PLAYER_DIR = CONFIG_DIR / "player"
PLAYER_PROFILE_PATH = PLAYER_DIR / "profile.yml"
#: 特殊日期表（`core/worldtime/realtime.py`）
EGGS_DIR = CONFIG_DIR / "eggs"
FESTIVALS_PATH = EGGS_DIR / "festivals.json"
#: 世界数据（世界观/地理/地点）
WORLD_DIR = CONFIG_DIR / "settings" / "world"
WORLD_OVERVIEW_PATH = WORLD_DIR / "overview.yml"
REGIONS_PATH = WORLD_DIR / "regions.yml"
#: 地点语义键表（`core/media/place_table.py`; 由 tempo 工作台导出, 会随时更新）
PLACE_TABLE_PATH = WORLD_DIR / "place_entities.json"
#: 人际权重表
RELATION_DIR = CONFIG_DIR / "settings" / "relation"
INTERPERSON_PATH = RELATION_DIR / "interperson.json"
#: MMT 白名单表（`core/common/mmt_registry.py`）
MMT_REGISTRY_PATH = CONFIG_DIR / "settings" / "mmt_registry.toml"

# ── assets/：资产（gitignore, 除白名单外不入库）────────────────────────────
ASSETS_DIR = ROOT / "assets"
BACKGROUND_DIR = ASSETS_DIR / "background"
ILLUSTRATION_DIR = ASSETS_DIR / "illustration"
MENU_DIR = ASSETS_DIR / "menu"
#: 导演地点白名单（`common_scenes`; **只剩降级兜底**——表读不出来时
#: `bond_story` 拿它当 `place_keys`, 见 `core/media/emotion_lexicon.load_place_lexicon`）
DIRECTOR_WHITELIST_PATH = ASSETS_DIR / "_director_whitelist.json"

# ── data/：运行时数据（gitignore）─────────────────────────────────────────
DATA_DIR = ROOT / "data"
#: 世界线根（`data/worlds/{world}/characters/{char}/…`; 首次运行才创建）
WORLDS_DIR = DATA_DIR / "worlds"
#: 诊断日志落盘（旁路, 不进事件流——见 `webgui/app.py:_setup_file_logging`）
DIAG_DIR = DATA_DIR / "diag"
DIAG_LOG_PATH = DIAG_DIR / "live2be.log"

# ── 前端静态（webgui）────────────────────────────────────────────────────
WEBGUI_STATIC_DIR = ROOT / "webgui" / "static"


__all__ = [
    "ROOT", "SETTINGS_PATH",
    "CONFIG_DIR", "CHARACTERS_DIR", "PLAYER_DIR", "PLAYER_PROFILE_PATH",
    "EGGS_DIR", "FESTIVALS_PATH",
    "WORLD_DIR", "WORLD_OVERVIEW_PATH", "REGIONS_PATH",
    "PLACE_TABLE_PATH", "RELATION_DIR", "INTERPERSON_PATH",
    "MMT_REGISTRY_PATH",
    "ASSETS_DIR", "BACKGROUND_DIR", "ILLUSTRATION_DIR", "MENU_DIR",
    "DIRECTOR_WHITELIST_PATH",
    "DATA_DIR", "WORLDS_DIR", "DIAG_DIR", "DIAG_LOG_PATH", "WEBGUI_STATIC_DIR",
]
