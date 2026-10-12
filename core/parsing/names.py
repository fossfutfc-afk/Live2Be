"""names.py — **名字接口**（读角色配置取名/别名的唯一入口; N1, 2026-09-23）。

## 为什么要有它（收敛前的四处重复）

| 位置 | 干什么 |
|---|---|
| `parsing/dynamic_character_parser.get_display_name` | 真源: `REQ~most_called_name` → 显示名 |
| `mmt/engine._name_aliases`（**私有**） | `other_names`/`jp_name`/`en_name` 切分成别名 |
| `webgui/routers/bond._speaker_name_map` | 角色 id → 显示名; `sensei` → 老师; `narrator` → 空 |
| `apps/vn_cli._speaker_names` | **同上又写一遍**（差别只在 narrator 不在表里） |
| `bond_story/engine._speaker_names` | `{char_id: display_name}` **第三遍**（零调用方, 本次删） |

用户 2026-09-22 指出"**多人模式的显示名**也要用" ⇒ 该上升为接口。

## 两条纪律

1. **只读配置, 不猜路径**: 本模块是纯函数（吃 profile dict / 已加载的角色对象）,
   **不碰文件系统**——"到哪儿去找角色"是 `CharacterLoader` 的事, 别混进来。
2. **键形态兼容**: 人设 yml 是**混合**的——`REQ~most_called_name`（带前缀）与
   `other_names`/`jp_name`/`en_name`（裸键）**同时存在**（真机实测）。所以每个字段
   都按 **裸键 → SIG~ → REQ~** 依次回落到第一个非空值。
   ⚠️ 收敛前 `_name_aliases` 只认裸键与 `SIG~`, **读不到带前缀的**; 本接口修掉这个洞,
   但**别名集合保持逐字不变**（`most_called_name` 读到的就是显示名本身, 与 display 重复,
   按 `display` 排除——见 `char_names`）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from contract import CHARACTER_NARRATOR, DEFAULT_SPEAKER_NAMES
from core.parsing.dynamic_character_parser import get_display_name

#: 人设里承载"名字/称呼"的四个字段（其余字段不参与）
_NAME_FIELDS = ("most_called_name", "other_names", "jp_name", "en_name")

#: 键前缀形态（真机混合存在; 顺序 = 优先级）
_PREFIXES = ("", "SIG~", "REQ~")

#: 名字分隔符（yml 原文里四种都见过）
_SPLIT = re.compile(r"[，,、/;；]")

#: 单个名字的长度上限（**太长会误伤文本替换**——原 `_name_aliases` 的规矩, 保留）
MAX_NAME_LEN = 8


@dataclass(frozen=True)
class CharNames:
    """一个角色的**名字集合**（显示名 + 别名）。"""

    display: str
    aliases: tuple[str, ...]

    def all(self) -> tuple[str, ...]:
        """显示名 + 别名（"她说的话里哪些词等于我"——别名归一/第一人称化用）。"""
        return (self.display, *self.aliases) if self.display else tuple(self.aliases)


def _pick(profile: Mapping[str, Any], field: str) -> str:
    """取一个名字字段（**裸键 → SIG~ → REQ~** 依次回落, 第一个非空者胜）。

    ⚠️ **值可能是列表** —— `other_names: ['空崎阳奈', '阳奈']` 是**合法 YAML**, 作者
    两种写法都用过（真档: 逗号串 / 行内 list / 块 list 三种并存）。
    以前这里一律 `str()` ⇒ list 变成 **Python repr**（`"['空崎阳奈', '阳奈']"`）,
    再被 `_SPLIT` 按逗号切 ⇒ 切出来的是**带引号与中括号的垃圾**
    （`"['空崎阳奈'"` / `"'阳奈']"`）—— 而且**静默**: 名字车道认不出"阳奈/委员长"、
    `find_entity` 也认不出（真机 `sorasaki_hina` / `ginkyou_iori` / `amau_ako` 就是这样,
    2026-10-08 C2 摸底时抓到）。
    ⇒ 列表**直接拼成 `，` 串**（与逗号串走同一套切分, 不另开一条路）。
    """
    for pre in _PREFIXES:
        raw = profile.get(f"{pre}{field}")
        if isinstance(raw, (list, tuple)):
            v = "，".join(str(x).strip() for x in raw if str(x).strip())
        else:
            v = str(raw or "").strip()
        if v:
            return v
    return ""


def _split_names(value: str) -> list[str]:
    """按分隔符切开、去空白、去重、丢掉超长的（> `MAX_NAME_LEN`）。"""
    out: list[str] = []
    for part in _SPLIT.split(value or ""):
        part = part.strip()
        if part and part not in out and len(part) <= MAX_NAME_LEN:
            out.append(part)
    return out


def char_names(profile: Mapping[str, Any] | None) -> CharNames:
    """人设 dict → `CharNames`（**纯函数**）。

    * `display` = `REQ~most_called_name`（缺失 → 第一个 REQ~ 值 → "未知角色"），
      走 `dynamic_character_parser.get_display_name`（**真源, 不在本模块重写**）。
    * `aliases` = 四个名字字段切分去重后**去掉 display 本身**（真机里
      `most_called_name` 读出来就是显示名 ⇒ 不去掉会在别名表里重复一遍）。
    """
    profile = profile or {}
    display = get_display_name(dict(profile))
    aliases: list[str] = []
    for field in _NAME_FIELDS:
        for part in _split_names(_pick(profile, field)):
            if part != display and part not in aliases:
                aliases.append(part)
    return CharNames(display=display, aliases=tuple(aliases))


def names_of(char) -> CharNames:
    """已加载的角色 → `CharNames`（鸭子类型: 只读 `.profile` / `.display_name`）。

    `char=None` → 空名字（调用方自己决定兜底文案）。
    """
    if char is None:
        return CharNames("", ())
    n = char_names(getattr(char, "profile", None))
    display = str(getattr(char, "display_name", "") or "").strip() or n.display
    return CharNames(display=display, aliases=n.aliases)


def speaker_names(char=None, *, char_id: str = "", display: str = "",
                  with_narrator: bool = False) -> dict[str, str]:
    """**说话人取值 → 显示名**（记录流 v2 渲染/回放前端唯一实现）。

    基础表 = `contract.DEFAULT_SPEAKER_NAMES`（`sensei` → 老师——**别在这儿再写一遍 "老师"**）。

    Args:
        char: 已加载的角色（读 `.character_id` / `.display_name`）; 与下面两个参数三选一。
        char_id / display: 调用方手里只有 id / 只有名字时用（webgui 的路由就是这样:
        它自己按 id 查人设, 只把结果交进来）。
        with_narrator: **要不要 `narrator` 这一键**——两个现网约定不同, 别统一掉:
            · webgui: 要（`narrator` → `""` 空串 ⇒ 前端"不加名字行"）
            · vn_cli: **不要**（靠"缺键"决定不画名字行）

    Returns: `{说话人取值: 显示名}`; 取不到名字 → 回落 `char_id`（宁缺勿错）。
    """
    out = dict(DEFAULT_SPEAKER_NAMES)
    cid = str(char_id or getattr(char, "character_id", "") or "").strip()
    if cid:
        out[cid] = (str(display or "").strip()
                    or str(getattr(char, "display_name", "") or "").strip()
                    or cid)
    if with_narrator:
        out[CHARACTER_NARRATOR] = ""
    return out


__all__ = ["MAX_NAME_LEN", "CharNames", "char_names", "names_of", "speaker_names"]
