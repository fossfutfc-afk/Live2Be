"""固定路径的唯一清单（宏形态，全部平铺在本文件顶层）。

五个根：

    RESOURCE_ROOT   代码、prompts、前端静态。程序不写。
    CONFIG_ROOT     人设卡、世界观、作息表。程序不写；用户手改是正常的。
    ASSETS_ROOT     立绘、背景、素材库。程序不写。
    APP_ROOT        settings.toml 与 .env。程序写（设置页）。
    DATA_ROOT       事件流真源、世界线、台账、诊断日志。程序写。

源码树里 RESOURCE_ROOT 与 APP_ROOT 就是仓库根，其余三个是根下同名目录；打包后
RESOURCE_ROOT 指向包内（只读），其余四个在 exe 同级。可写与不可写分开写清楚，
是为了让"往只读根写"这种事在改代码时就看得见——打包后往那儿写不报错，只是退出即丢。

CONFIG_ROOT / ASSETS_ROOT / DATA_ROOT 可以被 settings.toml 的 [paths] 覆盖（首次向导写它）：

    [paths]
      config = "D:/我的资产/人设"     # 相对路径按 APP_ROOT 解析
      assets = "D:/我的资产/图"

读它必须在这里（import 期），因为有不少模块在 import 期就把 paths.X 存成了自己的常量
（`CHAR_ROOT = paths.CHARACTERS_DIR` 这种），晚一步改就有人拿着旧值。向导保存后要重启。

约定：
1. 不许在函数体里现拼路径，一律在本文件顶层写常量。
2. 消费方写 `from infra import paths` 然后用 `paths.NAME`，便于 grep。
3. 命名：文件用 `*_PATH`，目录用 `*_DIR`，根用 `*_ROOT`。

定位清单：grep -n "^[A-Z][A-Z_]* = " infra/paths.py
定位消费点：grep -rn "paths\\.[A-Z]" --include=*.py .
"""
from __future__ import annotations

import sys
from pathlib import Path

from infra import settings

#: PyInstaller 打包后会设 sys.frozen
_FROZEN: bool = bool(getattr(sys, "frozen", False))

APP_ROOT = settings.app_root()
# 打包后资源在包内（onefile 解到临时目录、onedir 在 _internal/），与 APP_ROOT 不在一级
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT)) if _FROZEN else APP_ROOT

#: settings.toml 的 [paths] 那段（缺省 = 空表）
_OVERRIDE = settings.raw().get("paths") or {}


def _root(key: str, default: Path) -> Path:
    """[paths] 的覆盖值；相对路径按 APP_ROOT 解析，没配就用默认。"""
    val = _OVERRIDE.get(key)
    if not isinstance(val, str) or not val.strip():
        return default
    p = Path(val).expanduser()
    return p if p.is_absolute() else (APP_ROOT / p)


CONFIG_ROOT = _root("config", APP_ROOT / "config")
ASSETS_ROOT = _root("assets", APP_ROOT / "assets")
DATA_ROOT = _root("data", APP_ROOT / "data")

# ── APP_ROOT：运行时配置（gitignore；缺失即全默认）────────────────────────
#: 与 `settings.default_path()` 同源（LIVE2BE_SETTINGS 指到别处时跟着走）
SETTINGS_PATH = settings.default_path()
DOTENV_PATH = APP_ROOT / ".env"

# ── CONFIG_ROOT：作者手编的数据 ───────────────────────────────────────────
CONFIG_DIR = CONFIG_ROOT
#: 角色卡根目录（config/characters/{char_id}/ 六文件；CharacterLoader 的 root）
CHARACTERS_DIR = CONFIG_DIR / "characters"
#: 玩家（老师）档案。作者层，进 git；玩家在 GUI 里改的名字走 data/basic/player.json。
PLAYER_DIR = CONFIG_DIR / "player"
PLAYER_PROFILE_PATH = PLAYER_DIR / "profile.yml"
#: 特殊日期表（core/worldtime/realtime.py）
EGGS_DIR = CONFIG_DIR / "eggs"
FESTIVALS_PATH = EGGS_DIR / "festivals.json"
#: 角色名彩蛋：正则 → 回复列表（core/mmt/mmt_preset.py）
NAMEGG_PATH = EGGS_DIR / "namegg.json"
#: 世界数据（世界观 / 地理 / 地点）
WORLD_DIR = CONFIG_DIR / "settings" / "world"
WORLD_OVERVIEW_PATH = WORLD_DIR / "overview.yml"
REGIONS_PATH = WORLD_DIR / "regions.yml"
#: 地点语义键表（core/media/place_table.py；由 tempo 工作台导出）
PLACE_TABLE_PATH = WORLD_DIR / "place_entities.json"
#: 人际层：谁 + 她自己的看法（yml 而非 json，长中文能折行、能写注释）
RELATION_DIR = CONFIG_DIR / "settings" / "relation"
INTERPERSON_PATH = RELATION_DIR / "interperson.yml"
#: MMT 白名单表（core/mmt/mmt_registry.py）
MMT_REGISTRY_PATH = CONFIG_DIR / "settings" / "mmt_registry.toml"

# ── ASSETS_ROOT：资产（gitignore）─────────────────────────────────────────
ASSETS_DIR = ASSETS_ROOT
BACKGROUND_DIR = ASSETS_DIR / "background"
ILLUSTRATION_DIR = ASSETS_DIR / "illustration"
MENU_DIR = ASSETS_DIR / "menu"
#: 导演地点白名单。旧表，只在 place 词表读不出来时当降级兜底。
DIRECTOR_WHITELIST_PATH = ASSETS_DIR / "_director_whitelist.json"

# ── DATA_ROOT：运行时数据（gitignore）─────────────────────────────────────
DATA_DIR = DATA_ROOT
#: 世界线根（data/worlds/{world}/characters/{char}/…；首次运行才创建）
WORLDS_DIR = DATA_DIR / "worlds"
#: 诊断日志（旁路，不进事件流）
DIAG_DIR = DATA_DIR / "diag"
DIAG_LOG_PATH = DIAG_DIR / "live2be.log"

# ── RESOURCE_ROOT：随程序发的只读件 ───────────────────────────────────────
WEBGUI_STATIC_DIR = RESOURCE_ROOT / "webgui" / "static"


__all__ = [  # noqa: RUF022 — 按五根分组，字典序读不出"谁归哪根"
    # 五个根
    "APP_ROOT", "ASSETS_ROOT", "CONFIG_ROOT", "DATA_ROOT", "RESOURCE_ROOT",
    # APP_ROOT
    "DOTENV_PATH", "SETTINGS_PATH",
    # CONFIG_ROOT
    "CHARACTERS_DIR", "CONFIG_DIR", "EGGS_DIR", "FESTIVALS_PATH", "INTERPERSON_PATH",
    "MMT_REGISTRY_PATH", "NAMEGG_PATH", "PLAYER_DIR", "PLAYER_PROFILE_PATH",
    "PLACE_TABLE_PATH", "REGIONS_PATH", "RELATION_DIR", "WORLD_DIR",
    "WORLD_OVERVIEW_PATH",
    # ASSETS_ROOT
    "ASSETS_DIR", "BACKGROUND_DIR", "DIRECTOR_WHITELIST_PATH", "ILLUSTRATION_DIR",
    "MENU_DIR",
    # DATA_ROOT
    "DATA_DIR", "DIAG_DIR", "DIAG_LOG_PATH", "WORLDS_DIR",
    # RESOURCE_ROOT
    "WEBGUI_STATIC_DIR",
]
