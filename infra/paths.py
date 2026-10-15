r"""paths — **固定路径的唯一清单**（macro 形态, 全部平铺在本文件顶层）。

## 五个根（2026-10-15 定；用户裁"按照 5 root 来做"）

| 根 | 装什么 | 谁可写 | frozen 下在哪 |
|---|---|---|---|
| `RESOURCE_ROOT` | 代码 + `prompts/*.md` + 前端静态 | ⛔ **程序不许写** | **bundle 内**（临时解包目录 / `_internal`） |
| `CONFIG_ROOT` | 人设卡 / 世界观 / 作息表（作者层） | ⛔ 程序不写（**用户手改合法**） | exe 同级 `config/` |
| `ASSETS_ROOT` | 立绘 / 背景 / 素材库 | ⛔ 程序不写（见下"AI 生成物"） | exe 同级 `assets/` |
| `APP_ROOT` | `settings.toml` / `.env` | ✅ 程序写（GUI 设置页） | exe 同级 |
| `DATA_ROOT` | 事件流真源 / 世界线 / 台账 / 诊断日志 | ✅ 程序写 | exe 同级 `data/` |

⭐ **为什么"程序不许写"要写进常量名**（而不是约定俗成）: 打包后 `RESOURCE_ROOT` 是**只读的**
——往它里面写，轻则 `PermissionError`，重则**写成功但退出即丢**（onefile 解包目录会删），
而**不会报任何错**。把可写与不可写分成两栏之后，
`tests/core/test_paths.py::test_no_writes_under_readonly_roots` 能在测试期就拦住这种写。
⚠️ 拆根**不给文件系统权限**（不 chattr/chmod）: `CONFIG_ROOT` / `ASSETS_ROOT` 里的文件
用户随时能手改，那是设计的一部分。

## `CONFIG_ROOT` / `ASSETS_ROOT` / `DATA_ROOT` 的位置以后**可能由用户定**

这两样（人设卡、图片资产）传不到 GitHub，用户很可能得自己放 —— 所以它们的位置以后会由
**首次向导**写进 `settings.toml` 的 `[paths]`，本文件读它（今天还没有这一节, 读不到就全默认）。
⇒ 这正是"为什么必须分栏"的真理由: **不是"将来要打包"，而是"这几个根的值以后不由程序决定"**。
⭐ 改放哪只动本文件一处 —— 消费点写的都是 `paths.X`，不是 `ROOT / "X"`。

## 其它约定（用户 2026-09-19）

1. **不许在函数体里现拼路径**——`Path(__file__)... / "config" / "..."` 散在各模块
   就是"下次改目录时找不到的东西"。一律在本文件顶层写一个常量。
2. 消费方: `from infra import paths` → `paths.REGIONS_PATH`（**写全 `paths.`**，
   别 `from infra.paths import X`——否则 grep 消费点时要猜别名）。
3. 模块**自己的**默认值常量可以保留（`DEFAULT_REGIONS_PATH = paths.REGIONS_PATH`），
   因为那是公开 API/构造参数默认值; 但**值的来源只有这里一处**。
4. 命名: 文件 `*_PATH` / 目录 `*_DIR` / 根 `*_ROOT`。

## ⛔ AI 生成的背景**不写 `ASSETS_ROOT`**

`ASSETS_ROOT` 是**资产库**（作者整理 / tempo 同步）; AI 生成物是**运行时产物**
⇒ 落 `DATA_ROOT`（覆盖层），取图时"先查 data 侧覆盖, 再回落资产库"。
理由: ① 语义上它属于那条世界线; ② 打包后 `ASSETS_ROOT` 可能是只读的下载包;
③ 覆盖层天然支持"同一地点每个世界线一张不同的图"。（取图那一层今天还没接, 先立规矩。）

## 全量定位（两条 grep，就够了）

```bash
grep -n "^[A-Z][A-Z_]* = " infra/paths.py        # ① 清单本身（有哪些固定路径）
grep -rn "paths\.[A-Z]" --include=*.py .         # ② 谁在用（消费点）
```

## 为什么放在 `infra/` 而不是 `config/`

它是**代码**（要被 import），不是配置; `config/` 是给作者改的数据。
真正的运行时可覆盖项走 `settings.toml`（运行时配置, gitignore）与各模块的
构造参数——本文件只是**出厂默认值**的家。
⚠️ 它住在 `infra/`（最底层, 只依赖 stdlib）而不是 `core/`: `llm/` 也要用它
（`llm/task_levels.py` 读 `settings.toml`）, 而 `llm → core` 是一条**反向依赖**
（2026-10-15 搬完 ⇒ 那条依赖**归零**, `test_import_direction.py` 的豁免表清空）。
"""
from __future__ import annotations

import sys
from pathlib import Path

#: 是否跑在打包产物里（PyInstaller 会设 `sys.frozen`）
_FROZEN: bool = bool(getattr(sys, "frozen", False))

if not _FROZEN:
    # ── 源码树：五个根都落在**仓根**下（= 搬迁前那 25 个常量的值, 一个字都没变）──
    _BASE = Path(__file__).resolve().parents[1]                 # infra/paths.py → 仓根
    RESOURCE_ROOT = APP_ROOT = _BASE                            # 代码/静态/settings.toml 都在仓根
    CONFIG_ROOT = _BASE / "config"
    ASSETS_ROOT = _BASE / "assets"
    DATA_ROOT = _BASE / "data"
else:
    # ── 打包：资源随包（只读）; 其余在 exe 同级（用户内容 / 可写）────────
    # ⚠️ onefile 解包到临时目录、onedir 的资源在 `_internal/` ⇒ RESOURCE_ROOT
    #    与 APP_ROOT **天然不同级**, 这也是"五个根必须分开声明"的直接原因。
    RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    APP_ROOT = Path(sys.executable).resolve().parent
    CONFIG_ROOT = APP_ROOT / "config"
    ASSETS_ROOT = APP_ROOT / "assets"
    DATA_ROOT = APP_ROOT / "data"

#: ⭐ **五个根的语义与模式无关**（这条一致性是判据）:
#:   · `*_ROOT` = **那个内容目录本身**（不是"放它的父目录"）⇒ `CONFIG_DIR = CONFIG_ROOT` 恒成立;
#:   · 源码树里 `RESOURCE_ROOT` / `APP_ROOT` 恰好都是仓根（代码与 settings.toml 就在那儿）。

# ── APP_ROOT：运行时配置（gitignore; 缺失即全默认）────────────────────────
SETTINGS_PATH = APP_ROOT / "settings.toml"
#: API key 等（`load_dotenv` 的输入; 缺文件正常）
DOTENV_PATH = APP_ROOT / ".env"

# ── CONFIG_ROOT：作者手编的数据 ───────────────────────────────────────────
CONFIG_DIR = CONFIG_ROOT
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
#: 角色名彩蛋（`core/mmt/mmt_preset.py`; 正则 → 回复列表）。
#: ⚠️ 2026-10-15 从"模块里现拼"收进来的（那次现拼在 frozen 下会指向 bundle）。
NAMEGG_PATH = EGGS_DIR / "namegg.json"
#: 世界数据（世界观/地理/地点）
WORLD_DIR = CONFIG_DIR / "settings" / "world"
WORLD_OVERVIEW_PATH = WORLD_DIR / "overview.yml"
REGIONS_PATH = WORLD_DIR / "regions.yml"
#: 地点语义键表（`core/media/place_table.py`; 由 tempo 工作台导出, 会随时更新）
PLACE_TABLE_PATH = WORLD_DIR / "place_entities.json"
#: 人际层（**她眼里的他们**：谁 + 一句她自己的看法）
#: ⚠️ 2026-10-08 从 `interperson.json` 换成 **`.yml`** —— 值从"熟知程度数字"变成长句
#: 立场, JSON 写长中文太苦（不能折行、要转义）; YAML 还能写真注释。
RELATION_DIR = CONFIG_DIR / "settings" / "relation"
INTERPERSON_PATH = RELATION_DIR / "interperson.yml"
#: MMT 白名单表（`core/mmt/mmt_registry.py`）
MMT_REGISTRY_PATH = CONFIG_DIR / "settings" / "mmt_registry.toml"

# ── ASSETS_ROOT：资产（gitignore, 除白名单外不入库）────────────────────────
ASSETS_DIR = ASSETS_ROOT
BACKGROUND_DIR = ASSETS_DIR / "background"
ILLUSTRATION_DIR = ASSETS_DIR / "illustration"
MENU_DIR = ASSETS_DIR / "menu"
#: 导演地点白名单（`common_scenes`; **只剩降级兜底**——表读不出来时
#: `bond_story` 拿它当 `place_keys`, 见 `core/media/emotion_lexicon.load_place_lexicon`）
DIRECTOR_WHITELIST_PATH = ASSETS_DIR / "_director_whitelist.json"

# ── DATA_ROOT：运行时数据（gitignore）─────────────────────────────────────
DATA_DIR = DATA_ROOT
#: 世界线根（`data/worlds/{world}/characters/{char}/…`; 首次运行才创建）
WORLDS_DIR = DATA_DIR / "worlds"
#: 诊断日志落盘（旁路, 不进事件流——见 `webgui/app.py:_setup_file_logging`）
DIAG_DIR = DATA_DIR / "diag"
DIAG_LOG_PATH = DIAG_DIR / "live2be.log"

# ── RESOURCE_ROOT：随程序发的只读件（⛔ 程序不许写）──────────────────────
#: 前端静态（`webgui/app.py` 挂载; 与服务端代码同属"随包发的只读件"）
WEBGUI_STATIC_DIR = RESOURCE_ROOT / "webgui" / "static"


__all__ = [
    # ── 五个根 ──
    "APP_ROOT", "ASSETS_ROOT", "CONFIG_ROOT", "DATA_ROOT", "RESOURCE_ROOT",
    # ── APP_ROOT ──
    "DOTENV_PATH", "SETTINGS_PATH",
    # ── CONFIG_ROOT ──
    "CHARACTERS_DIR", "CONFIG_DIR", "EGGS_DIR", "FESTIVALS_PATH", "INTERPERSON_PATH",
    "MMT_REGISTRY_PATH", "NAMEGG_PATH", "PLAYER_DIR", "PLAYER_PROFILE_PATH",
    "PLACE_TABLE_PATH", "REGIONS_PATH", "RELATION_DIR", "WORLD_DIR",
    "WORLD_OVERVIEW_PATH",
    # ── ASSETS_ROOT ──
    "ASSETS_DIR", "BACKGROUND_DIR", "DIRECTOR_WHITELIST_PATH", "ILLUSTRATION_DIR",
    "MENU_DIR",
    # ── DATA_ROOT ──
    "DATA_DIR", "DIAG_DIR", "DIAG_LOG_PATH", "WORLDS_DIR",
    # ── RESOURCE_ROOT ──
    "WEBGUI_STATIC_DIR",
]
