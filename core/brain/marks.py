"""marks.py — **括号与信息头的唯一实现**（`docs/CONTEXT_MARKS.md` 的代码真源）。

她（以及 digest 那五轮）眼前那几行字的形状全从这里出::

    - 〔《中秋的杂草屋》｜4 天前｜9/27｜难忘〕中秋节晚上, 社团的大家…   ← head()  (她)
    〔m0021｜《今天的杂草屋》〕今天放学后又去了杂草屋…                  ← head()  (R2/R4)
    〔u0001｜belief｜被引 3〕sensei：老师是第一个…                     ← head()  (L2)
    〔u0001｜《模型店》｜episode〕模型店门口                            ← head()  (R3)
    〔《那片苔藓》｜3 条〕…                                            ← head()  (L2-a 分群: 已有的类)
    〔b1｜3 条〕…                                                     ← head(None)  (L2-a 分群: 块的把手)
    n3 周六模型店 (《模型店的午后》)  ← 记于 3 天前                     ← name() + relative()  (note)

## 三条不变量（`docs/CONTEXT_MARKS.md`）

1. ⭐ **一形一义** —— `【】`段头 · `〔〕`元信息（信息头）· `《》`事件名=地址 ·
   `（）「」`正文与原话 · `[]`历史动作前缀 · `{}`JSON 行;
   ⚠️ **字段分隔是 `｜`**, `·` 是**并列**（`星空 · 夜空` 那种）**不是**字段边界。
2. ⭐ **空字段不占位** —— 没有的格直接不出现; **一个格都没有 ⇒ 整段不出现**（返回 `""`）。
   由此**位置不固定**: 判"哪一段是名字"要**按书名号找, 不按位置找**。
3. ⭐ **名字只有一处印法**（`name()`）—— 它是**地址**: 她照抄下来交给
   `{"noticed": …}` / 将来的 `{"look": […]}`，引擎拿它查库（`address.find_episode`）。
   多一处实现就多一次**静默命中 0**。

## 为什么单独一件（而不是塞进 `render.py` / `address.py`）

· `render.py` 与 `notes.py` 之间**已经有延迟 import 的环**（`render` 里
  `from …notes import render_item`）—— 公共件放进任一方, 另一方就得反向依赖;
  本模块**零依赖、零 IO、不碰 store**, 谁都能 import, 没有环。
· `address.py` 是**另一半**（她写下的形式 → 节点）。两半**共用同一份字符集**
  （`address` 从这里取 `STRIP_CHARS` / `FIELD_SEP`, 不再自己抄一份）, 但不住一个文件
  —— 否则一个模块两件事。

## 边界（这里**不管**什么）

正文（第一人称转换 / 截断 / `subject：` / `原话:` 行 / 边续行）由各读者自己写 ·
缩进 · 段级拼装（`digest._join_sections`）· note 行的**整行形状**（它是"自然语言小节,
零结构化痕迹"的裁决, 只借 `name()` 与 `relative()`）。

## 守门

`tests/core/test_marks_guard.py` 用 `ast` 扫 `core/brain/` 的**代码字面量**
（docstring / 注释不算）: 除本模块外**不许再出现 `《` `〔` `〕` `｜`** —— 谁手写一处就红。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                       # 仅注解求值期可见（避免运行时循环导入）
    from core.brain.nodes import BrainNode

# ---------------------------------------------------------------------------
# 1. 括号表 —— 与 `docs/CONTEXT_MARKS.md` 那张表**一行对一行**
# ---------------------------------------------------------------------------

#: 段头（`【角色记忆（brain）】` / `【本段新增的经历】`）
SECTION_OPEN, SECTION_CLOSE = "【", "】"
#: 元信息 = **信息头**（`〔钥匙｜《名字》｜…〕`）; 第一格 = **引用要用的钥匙**
HEAD_OPEN, HEAD_CLOSE = "〔", "〕"
#: 事件名 = **地址**（她照抄的那几个字）
NAME_OPEN, NAME_CLOSE = "《", "》"
#: 正文里的补注（旁白 / 原话都在这里面）
BODY_OPEN, BODY_CLOSE = "（", "）"
#: 逐字原话（**只表示原话** —— 标题绝不许用它, 那是 N2 修掉的那个同形不同义）
QUOTE_OPEN, QUOTE_CLOSE = "「", "」"
#: 历史里的动作名前缀（`[mmt_send_media]` 那种）
ACTION_OPEN, ACTION_CLOSE = "[", "]"
#: ⭐ **字段分隔**（全角竖线）—— 不是 `·`: `·` 在提示词里到处都是
#: （`bond_shots` 的镜头词表就是 `星空 · 夜空 · 黄昏`）, 而**事件名是 LLM 起的, 可能自带 `·`**
#: ⇒ 她"抄到第一个 `·` 为止"就会抄多抄少 ⇒ 查库命中 0 ⇒ **静默丢**。
FIELD_SEP = "｜"

#: 解析侧要剥掉的**语法字符**（内容字符不在内）—— 与 `address.normalize_title` 配套:
#: 印（`name()`）与剥（`STRIP_CHARS`）**必须是同一份清单**, 否则她抄回来的名字认不出。
STRIP_CHARS = (NAME_OPEN + NAME_CLOSE + "〈〉<>"
               + SECTION_OPEN + SECTION_CLOSE + HEAD_OPEN + HEAD_CLOSE
               + "\"“”'‘’" + QUOTE_OPEN + QUOTE_CLOSE
               + " \t\r\n\u3000")


# ---------------------------------------------------------------------------
# 2. 单格
# ---------------------------------------------------------------------------

def section(title: str) -> str:
    """段头: `【本段新增的经历】`。"""
    return f"{SECTION_OPEN}{title}{SECTION_CLOSE}"


def name(title: object) -> str:
    """⭐ **事件名 = 地址**: `《中秋的杂草屋》`; 没有名字 ⇒ `""`（**空字段不占位**）。

    ⚠️ **原样印**（只做"空不空"的判据, 不动空白）—— 它是地址, 她抄下来的串必须与库里的
    `node.title` **逐字相同**; 顺手 strip 一下就会让"库里带空格的名字"永远命中不了,
    而且**静默**。
    ⚠️ **绝不套在 `「」` 里**: `「」` 在这套约定里只表示**逐字原话**（她视图的
    `（「月亮, 真的很圆。」）`）, 同一个形状两种意思 = 她抄错东西。
    """
    if not title:
        return ""
    return f"{NAME_OPEN}{title}{NAME_CLOSE}"


def kind_tag(node: "BrainNode") -> str:
    """节点类型: `episode` / `belief` / `group`（**不带方括号** —— 括号表里 `[]` 另有含义）。

    ⚠️ **类型从节点上取, 不由调用方传进来**（传进来就有两个真源, 而"类型怎么印"
    这种印法必须只有一处）。
    ⏸ **原 `promise·已兑现` 那一支 2026-09-29 删** —— promise 退图（节点上不再有
    `outcome`）, 结局该由**那条经历的正文**说（2026-10-05 起 note 面也不再渲染它:
    `close` = 划掉即移除）。
    """
    return node.kind


def relative(ts: object, now, *, significance: float = 0.5) -> str:
    """**相对短语**（她的口吻）: `今天 / 昨天 / 4 天前 / 1 周前 / 很久以前`; 算不出 ⇒ `""`。

    ⚠️ **哨兵纪律**（同 `age.render_relative`）: `now is None`（调用方没给"现在"）
    或 `ts` 缺失 / 坏值 ⇒ **整格不出现** —— 不编一个"很久以前", 那会让"未采集"与
    "真的很旧"混为一谈。
    ⚠️ **绝不出现精确值**（I-c）: 短语由 `age` 的桶决定, 这里不做任何算术。
    """
    if now is None or not ts:
        return ""
    try:
        from core.worldtime.age import age_days, render_relative
        age = age_days(ts, now=now)
        if age is None:
            return ""
        return render_relative(age, significance)
    except Exception:                            # noqa: BLE001 — 渲染绝不因时间炸
        return ""


def abs_date(ts: object, now) -> str:
    """**绝对日期**（引擎坐标）: `9/27` / 跨年 `2025/9/26`; 算不出 ⇒ `""`。

    ⚠️ 它是**引擎的坐标, 不是她的口吻** —— 两个都要（`PROCEED §2 #16`）: 相对短语用来
    "像人一样记得", 绝对日期用来"定位到具体哪天"。
    """
    if now is None or not ts:
        return ""
    try:
        from core.worldtime.age import render_date
        return render_date(ts, now=now)
    except Exception:                            # noqa: BLE001 — 渲染绝不因时间炸
        return ""


# ---------------------------------------------------------------------------
# 3. 信息头
# ---------------------------------------------------------------------------

def head(node: "BrainNode | None" = None, *, key: str = "", kind: bool = False,
         now=None, extra: object = ()) -> str:
    """⭐ **信息头**: `〔钥匙｜《名字》｜类型｜相对｜绝对｜…读者自己的字段〕`。

    格序**固定**（`key → 名字 → kind → 相对 → 绝对 → extra…`）, 但**空的一律不占位**
    —— 所以同一个格在不同读者那里位置会变, 这是**不变量 2**, 不是 bug:
    "哪一段是名字"**按书名号找, 不按位置找**（位置规则在缺字段的行上会读错）。

    三个参数对应"这一格要不要":

    | 参数 | 谁决定 | 说明 |
    |---|---|---|
    | `key` | **调用方给的串** | ⚠️ 不是布尔: **"要不要编号"的真身是"这一轮她要不要拿这个串写回引擎"**。`key=node.id`（真实 id, digest 的 `refs` 用它）· `key=本地号`（`u0001`, 防 LLM 猜真实 id）· **不传**（她的视图: **编号绝不进**, 名字就是钥匙） |
    | `kind` | 布尔 | 印不印 `kind_tag(node)`（她的视图不印: 分节已经说了这是"我记得的事"） |
    | `now` | **时刻或 `None`** | 不传布尔: `now=None` ⇒ 时间两格都不出现（哨兵纪律） |

    ⭐ **`node=None`**（N7）: 给**不是图节点**的把手用 —— 一个块（`b1`）、一个临时分组,
    它们只有"钥匙"与"读者自己的字段"两格（`head(None, key="b1", extra=["3 条"])`
    → `〔b1｜3 条〕`）。⚠️ 名字格**只认节点上的 `title`**（不接字符串）——
    名字是**地址**, 只有一处印法（`name()`）, 谁能被指必须有据可查。

    `extra` = **读者自己的字段**（`被引 3` / `sig 0.90` / `难忘` / `3 条` …）:
    只有它知道该印什么、什么顺序 —— 但**不许把名字写进去**（名字只能由 `name()` 产,
    守门用例钉着）。

    ⚠️ **`key` 与 `extra` 都为空、node 也没名字（或没给 node）⇒ 返回 `""`** = 整段不出现
    （旧档逐字节不变）。
    """
    fields: list[str] = []
    if key:
        fields.append(str(key))
    if node is not None:
        fields.append(name(getattr(node, "title", "")))      # 空串自然被滤掉
        if kind:
            fields.append(kind_tag(node))
        if now is not None:
            fields.append(relative(getattr(node, "ts", ""), now,
                                   significance=getattr(node, "significance", 0.5)))
            fields.append(abs_date(getattr(node, "ts", ""), now))
    fields.extend(str(f) for f in extra if f)
    fields = [f for f in fields if f]
    if not fields:
        return ""
    return f"{HEAD_OPEN}{FIELD_SEP.join(fields)}{HEAD_CLOSE}"
