"""material.py — digest 各轮的**料**（2026-09-29 从 `pipeline.py` 拆出）。

"这一轮吃什么"的真源是 `rounds.ROUNDS` 的 `material` 格（段标题 + 顺序）;
本模块是那些**正文**的构造者（引擎侧, 零 LLM）:

| 给谁 | 函数 | 料 |
|---|---|---|
| **R0** | `_segment_time_text` · `_special_days_text` · `_open_pinned_text` · `_ledger_ids` | 本段的时间 · 日子 · 还开着的约定（带编号 + 期限）· **资格位**（L3, 2026-10-05） |
| R1 | `_collect_visual_prompts` · `_segment_emotion_keys` | 画面记忆 · 本段情绪标尺 |
| R4 | `_open_pinned_text` · `_episode_lines` | 还开着的约定（带编号）· 本段新增经历 |
| **L1** | `_round_b_material` · `_episode_candidates` | 新经历（**带 `topics` 轴**）+ 每条候选（正文/被引/边/为什么）· **现有经历（候选）**（按 `topics` 相交摆）|
| R3 | `_node_texts` | 本轮**动过**的节点正文（喂 `entities.hit_set`） |
| 全体 | `_sections_for` · `_join_sections` | 按表校对段标题 → 拼成 user 串 |

⚠️ **两条纪律**（拆出来也要带着走）:
1. **LLM 轮的输入一律走 `_sections_for`**（先拿轮次表校对段标题, 再拼）——
   直接调 `_join_sections` = 绕过校对, `test_sections_check_is_wired` 会红。
2. **行格式只有一个实现**: 段头走 `marks.section`, 记忆行头走 `marks.head`
   （`〔m0021｜《标题》〕`）, note 行走 `notes.render_item` —— 本模块**只拼不造**。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from contract.digest_registry import RELATION_ACTIONS, STATE_VALUES, is_full_date
from core import paths
from core.brain import marks
from core.digest.rounds import RoundSpec
from core.digest.segment import _span_range

if TYPE_CHECKING:                       # 仅注解求值期（避免与编排层循环 import）
    from core.brain.read.recall import EmbedFn
    from core.brain.store import WikiStoreV2

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# R0 / R1 共用的"骨架"视图（3b-2）
# ---------------------------------------------------------------------------

def _skeleton_rows(segments: list[dict]) -> list[tuple[int, dict]]:
    """**能填的骨架行** → `[(原始下标, 切片)]` —— L5（2026-10-05）。

    只收**有位置的行**（`_span_range` 非空: 有 `span`, 或旧形状的逐点 `event_seq`）。
    ⛔ **无区间那一行（`span: null` = "没有那一刻"）不进这里** —— 它没有事件可写,
    正文**就是 R0 给的 `abstract`**（§1.3 / §2.3）; 派给 R1 = 派一件它写不了的活,
    而契约那句"每一条切片给一行"还会逼它硬编一条出来。

    ⚠️ **印骨架与对位必须是同一份清单**（`_skeleton_text` 印它, `_align_to_skeleton`
    照它对位）: 两处各过滤一次 = 迟早错位 —— 而对位一错, note 的出生地址就挂到
    别条经历上了（那种错**不报错**, 只会让"这条约定是从哪件事长出来的"变成另一件事）。
    """
    return [(i, seg) for i, seg in enumerate(segments)
            if _span_range(seg) is not None]


def _skeleton_text(segments: list[dict]) -> str:
    """R1 的料之一: **本段骨架**（这一段要填哪几条）—— 3b-2, 2026-09-29。

    形态（一行一件, 顺序 = `episodes` 的顺序）::

        第 1 件｜28-28｜教师在周日突然邀请我去了咖啡厅吃东西
        第 2 件｜29-29｜⭐ 明天把两个团子带去夏莱, 别多想

    ⚠️ **只印有区间的行, 而且重编 1..N**（L5, 2026-10-05）: 无区间那一行不派活
    （见 `_skeleton_rows`）; 编号**不保留 R0 的原始件号** —— 留着旧号会让模型以为漏了一件。
    ⚠️ **⭐ 的含义 = "不许 drop"**（`open` 与 `close` **都**打星星）—— 从前只有 `open` 打、
    含义是"她往后要一直带着的"; 现在 `close`（哪一件把一笔账了结了）同样不许丢,
    ⇒ 星星只表示"这条不许 drop", 与 `SKELETON_HINT` 那句**同源**。
    ⚠️ **区间要印**（用户裁决）: 它把 abstract 钉在时间线的某一段上 ——
    "第 2 件" 是几号, 不如"29-29"直接。
    """
    lines: list[str] = []
    for k, (_i, seg) in enumerate(_skeleton_rows(segments), start=1):
        rng = _span_range(seg)
        where = f"{rng[0]}-{rng[1]}" if rng else "-"
        star = "⭐ " if seg.get("state") in STATE_VALUES else ""
        lines.append(f"第 {k} 件｜{where}｜{star}{seg.get('abstract') or '-'}")
    return "\n".join(lines)


#: 骨架这一段的行格式说明（**与 `_skeleton_text` 同源** —— 印的和说的在一处）
SKELETON_HINT = ("（⭐ = **不许 drop** 的那几条 —— 账目行（她答应了什么 / 哪一件把一笔账"
                 "了结了）; 别的都可以 drop）")


def _sections_for(spec: RoundSpec, sections: list[tuple[str, str]]) -> str:
    """按表校对**料的段标题**再拼装 —— 表说这一轮吃什么, 这里就必须是那几段。

    ⚠️ 只校标题（"吃什么"的地图）, 不校正文（正文由各家现算）。对不上 = 表在骗人,
    所以**当场炸**而不是静默放行 —— 这正是"料跨 3~4 个文件"的解药:
    想知道 R2 吃什么, 看表一行就够, 而表**不可能**与实际不符。
    """
    got = tuple(title for title, _ in sections)
    if got != spec.material:
        raise AssertionError(
            f"digest {spec.key!r} 的料与轮次表不一致: 表={spec.material} 实际={got}"
            "（改料就要改 core/digest/rounds/__init__.py 的 ROUNDS）")
    return _join_sections(sections)


def _join_sections(sections: list[tuple[str, str]]) -> str:
    """输入块拼装: 非空块才注入（省 token）; 空块跳过。

    ⚠️ 段头 `【】` 的构造在 `marks.section`（括号表唯一实现）—— 本函数只管"拼"。
    ⚠️ **LLM 轮的输入一律走 `_sections_for`**（它先拿轮次表校对段标题, 再调这里）——
    直接调本函数 = 绕过料校对, `test_sections_check_is_wired` 会红。
    """
    parts = [f"{marks.section(title)}\n{body}" for title, body in sections if body]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 公共料: 画面记忆 / 情绪标尺
# ---------------------------------------------------------------------------

def _collect_visual_prompts(events) -> list[str]:
    """l2d 事件的 gallery png → 同名 json 的 prompt（视觉记忆）。"""
    prompts: list[str] = []
    for e in events:
        if e.type != "l2d":
            continue
        for img in e.payload.get("images", []) or []:
            if not isinstance(img, str) or not img:
                continue
            gjson = Path(img).with_suffix(".json")
            try:
                meta = json.loads(gjson.read_text(encoding="utf-8"))
                prompt = meta.get("prompt", "")
                if isinstance(prompt, str) and prompt.strip():
                    prompts.append(prompt.strip())
            except (OSError, ValueError):
                continue
    return prompts


def _segment_emotion_keys(events) -> list[str]:
    """本段所有 bond 板里**出现过的**情绪键（按首次出现顺序, 去重）。

    来源 = `payload.paragraphs[i].emotion`（标注层产物, 真源在事件流里）。
    只读不写——用于决定"给 Round A 注哪些键的标尺"（§3.3.2）。
    缺字段/坏结构 → 跳过, 不抛（宁缺勿错: 少注一个键, 不阻断 digest）。
    """
    keys: list[str] = []
    seen: set[str] = set()
    for e in events:
        if getattr(e, "type", None) != "bond":
            continue
        payload = getattr(e, "payload", None) or {}
        for p in payload.get("paragraphs") or []:
            if not isinstance(p, dict):
                continue
            k = p.get("emotion")
            if isinstance(k, str) and k.strip() and k.strip() not in seen:
                seen.add(k.strip())
                keys.append(k.strip())
    return keys


# ---------------------------------------------------------------------------
# R4 的料: 还开着的约定 / 本段新增经历
# ---------------------------------------------------------------------------

def _open_pinned_text(items: list, *, now: object | None = None,
                      today: "date | None" = None,
                      first_day: "date | None" = None) -> str:
    """**还开着的约定**（带编号 —— 写 `close` / 更正要照着 `id`）。

    ⭐ **R4（收口轮）与 R0（切分员, L3 2026-10-05）共用这一份**: 行格式 = 她备忘录那一行
    （`notes.render_item` —— **一份行格式只有一个实现**）+ 尾巴那格 **期限**
    （只在调用方给了 `today` 时印: R4 今天不看日期, R0 非看不可）。

    ⚠️ 期限那格**三种措辞说的是三件事**（`DESIGN_DIGEST_LEDGER §3.2`）:
    `—（没有期限）`（永不过期）/ `（本段期间到期）`（原文就在它手边）/ `（已过 N 天）`（陈年旧账）。
    """
    from core.brain.notes import render_item
    return "\n".join(
        f"- {render_item(it, now=now)}{_due_cell(it, today=today, first_day=first_day)}"
        for it in items)


# ---------------------------------------------------------------------------
# R0 的料（**L3, 2026-10-05**）: 本段的时间 · 日子 · 期限那格 + 资格位
#
# ⚠️ 为什么这些**只给 R0**: 它今天的料里一个日期都没有（行首只有 `[28]` 那种位置号）
# ⇒ "生日那天"折算不出绝对日期、`due` 也写不出来 —— 而 R1 写正文, 正文里出现绝对
# 日期会与"剧情里不走绝对日期"那条口径打架（用户裁决: `DESIGN_DIGEST_LEDGER §3.6`）。
# ---------------------------------------------------------------------------

def _day_of(ts: object) -> "date | None":
    """事件 `ts` → **那一天**（`2026-05-10T21:33:00+08:00` ⇒ `2026-05-10`）; 坏值 ⇒ None。"""
    raw = str(ts or "").strip()
    if len(raw) < 10:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _segment_days(events) -> list["date"]:
    """本段跨了哪几天（升序去重）—— 【本段的时间】与"段起"共用这一处。

    ⚠️ 段的**最后一天**就是这一段的"今天"（`ctx.now_ts` 同源: 段内最后一条内容事件）
    —— 资格位判"过期没有"用的是它, **不是**机器的挂钟（补跑旧段时才不会全判成超期）。
    """
    return sorted({d for d in (_day_of(getattr(e, "ts", "")) for e in events) if d})


def _segment_time_text(days: list["date"]) -> str:
    """⭐ R0 的料之一: **本段的时间** —— `2026-05-08 ~ 2026-05-10`（**单日只印一个**）。

    段可能跨天（水位欠着的尾巴会并进下一段）⇒ 给范围, 不给单点。
    """
    if not days:
        return ""
    if len(days) == 1:
        return days[0].isoformat()
    return f"{days[0].isoformat()} ~ {days[-1].isoformat()}"


#: `5/13` / `5月13日` / `05-13` / `5.13` —— **一个解析器吃几种写法**（真机两种并存）
_MONTH_DAY = re.compile(r"^\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?\s*$")


def _parse_month_day(raw: str) -> "tuple[int, int] | None":
    """`5/13` / `5月13日` → `(5, 13)`; 认不出 ⇒ **None**（绝不猜 —— 猜错 = 误判失约）。

    ⚠️ 真机两种格式并存（`5/13` 与 `5月13日`, 见 `DESIGN_DIGEST_LEDGER §3.5` 实情 1）
    ⇒ 不按格式分支, 一个解析器吃完; `2/30` 这种日历上不存在的当天淘汰。
    """
    m = _MONTH_DAY.match(str(raw or ""))
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    try:
        date(2000, month, day)          # 2000 是闰年 ⇒ 2/29 合法, 2/30 当场淘汰
    except ValueError:
        return None
    return month, day


def _role_birthday(char_id: str) -> "tuple[int, int] | None":
    """角色的生日 —— 读**档案** `config/characters/{id}/profile.yml` 的 `birthday`。

    为什么读档案、不读 `mmt_registry.toml`: 后者是**显示用**生日, 而这份料是给 AI
    折算日期用的（两个真源的分工写在 `core/common/mmt_registry.py` 的注释里）。
    ⚠️ **不一致时以档案为准**（`DESIGN_DIGEST_LEDGER §3` 待裁项, 2026-10-05 采此解）。
    读不到 / 格式认不出 ⇒ None —— **不印那一格, 更不编一个日期**。
    """
    if not char_id:
        return None
    from core.parsing.dynamic_character_parser import load_yaml_file
    for name in ("profile.yml", "profile.yaml"):
        path = paths.CHARACTERS_DIR / char_id / name
        if not path.is_file():
            continue
        try:
            data = load_yaml_file(path)
        except Exception:                    # noqa: BLE001 — 料缺一格不该拖垮整段
            return None
        # 前缀三档 = `core/parsing/names._PREFIXES` 那套口径（裸键 → SIG~ → REQ~）
        for key in ("SIG~birthday", "REQ~birthday", "birthday"):
            raw = str(data.get(key) or "").strip()
            if raw:
                return _parse_month_day(raw)
        return None
    return None


def _special_days_text(*, char_id: str) -> str:
    """⭐ R0 的料之二: **日子**（她的生日 + 节日表）—— 让"生日那天"折算成绝对日期。

    形态: `她 5/13 生日｜节日：元旦 1/1 · 情人节 2/14 · 教师节 9/10 · 圣诞节 12/25`

    ⚠️ **整张节日表都印**（今天 4 行 ≈ 40 字）, **不设"附近"窗口**: 六月里说定
    "圣诞节一起过"照样要折算, 窗口反而把它挡在外面; 表是作者手编的, 长得很慢。
    ⚠️ **老师的生日那一格不印** —— `config/player/profile.yml` **没有生日字段**
    （2026-10-05 查）; 印一个 `老师 —` 等于告诉她"有个你不知道的东西"。
    "不知道日期就不写 `due`"（§3.5 第三档）本来就覆盖这种情况。
    """
    parts: list[str] = []
    birthday = _role_birthday(char_id)
    if birthday:
        parts.append(f"她 {birthday[0]}/{birthday[1]} 生日")
    from core.worldtime.realtime import load_occasions
    rows = [f"{o.name} {o.month}/{o.day}" for o in load_occasions()]
    if rows:
        parts.append("节日：" + " · ".join(rows))
    return "｜".join(parts)


def _due_date(item) -> "date | None":
    """条目的 `due` → 那一天; **不是全日期 ⇒ None**（= 没有期限）。

    ⚠️ 判据与契约**同源**（`contract.digest_registry.is_full_date`）——
    料与校验对"什么算日期"必须一个口径, 否则会印出一个校验层不认的日期。
    ⛔ **绝不喂 `age_days`**（它吃 aware 时间戳, 裸日期当场 TypeError —— P1）。
    """
    raw = str(getattr(item, "due", "") or "").strip()
    return date.fromisoformat(raw) if is_full_date(raw) else None


#: 期限那一格的引导（四个空格 —— 与 `_open_pinned_text` 的 `- ` 对齐, 一行一件事）
_DUE_LEAD = "    期限 "


def _due_cell(item, *, today: "date | None", first_day: "date | None" = None) -> str:
    """名单行尾巴那一格: **期限**（三态）。`today is None` ⇒ 整格不印。"""
    if today is None:
        return ""
    due = _due_date(item)
    if due is None:
        return f"{_DUE_LEAD}—（没有期限）"
    if first_day is not None and due < first_day:
        return f"{_DUE_LEAD}{due.isoformat()}（已过 {(today - due).days} 天）"
    if due <= today:
        return f"{_DUE_LEAD}{due.isoformat()}（本段期间到期）"
    return f"{_DUE_LEAD}{due.isoformat()}"


def _overdue_detail(items: list, overdue_ids: set[str], *, today: "date | None") -> str:
    """**超期未决**那几条的一句话明细（日志/体检用）—— L9（2026-10-05）。

    形态: `n3（已过 4 天） · n7（已过 1 天）`；没有 ⇒ `"-"`（最多 4 条 + 省略号）。

    ⚠️ **它是体检账, 不是判决**: 引擎只把"这条过期了、而这一段没提到它"摆出来,
    判不判在 R0（见 `_ledger_ids`）。用户 2026-10-05 裁: **不进 creep 账** ——
    可 grep 的日志够了, 不必为此多开一个 kind（`digest_split` 那行就是它的家）。
    """
    if today is None or not overdue_ids:
        return "-"
    out: list[str] = []
    for it in items:
        nid = str(getattr(it, "id", "") or "")
        if nid not in overdue_ids:
            continue
        due = _due_date(it)
        days = (today - due).days if due is not None else 0
        out.append(f"{nid}（已过 {days} 天）")
    return " · ".join(out[:4]) + (" …" if len(out) > 4 else "")


def _mentioned(store, item, *, seq_set: set[int], timeline: str) -> bool:
    """**本段有没有提到这条约定**（粗筛, 只回答"有没有", 不判轻重）。

    两条判据, 任一命中即算"提到":
      ① **结构**: 它的出生经历（`refs`）的 `event_seq` 与本段 seq **有交集**
         ⇒ 这一段覆盖了那件事本身;
      ② **词面**: 那些经历的 `tags`（引擎写的"以后可能被提到的词"）出现在**本段时间线**里。
    ⚠️ 两条都不中 ⇒ 算**没提到**（"宁可多发"）: 资格位只是"允不允许写 `span: null`",
    判不判在她 —— 而她手里就是原文。宁可多发一格, 不可替她把话说死。
    ⛔ 拿不到经历（旧档/refs 空）⇒ 也算没提到（同上: 不替她判）。
    """
    for ref in getattr(item, "refs", None) or []:
        node = store.get(str(ref))
        if node is None:
            continue
        if seq_set & set(getattr(node, "event_seq", None) or []):
            return True
        for tag in getattr(node, "tags", None) or []:
            word = str(tag).strip()
            # `#pinned` 那种标记不是词; 一个字太容易误撞
            if len(word) >= 2 and not word.startswith("#") and word in timeline:
                return True
    return False


def _ledger_ids(store, items: list, *, seq_set: set[int], timeline: str,
                today: "date | None") -> "tuple[set[str], set[str]]":
    """→（**闭集** `note_ids`, **资格位** `overdue_ids`）—— L3。

    `note_ids` = 料里印出来的每一条（`open.id` / `close.id` 只能引用它）;
    `overdue_ids` = 其中**超期且本段没提到**的那些 ⇒ 只有它们允许写 `span: null`
    （"没有那一刻"的收口 —— 契约层的第二道闸, 见 `parse_split`）。

    ⚠️ **超期 = `due < 今天`（无宽限）**, "今天" = 本段的最后一天（见 `_segment_days`）。
    没有 `due` ⇒ 永不过期, 永不发资格位（"我会一直陪着你"不该被判失约）。
    """
    note_ids = {str(it.id) for it in items if getattr(it, "id", "")}
    overdue: set[str] = set()
    if today is None:
        return note_ids, overdue
    for it in items:
        due = _due_date(it)
        if due is None or due >= today:
            continue
        if not _mentioned(store, it, seq_set=seq_set, timeline=timeline):
            overdue.add(str(it.id))
    return note_ids, overdue


def _episode_lines(store: "WikiStoreV2", episode_ids: list[str]) -> str:
    """R4 输入之二: **本段新增的经历**（真 id —— `add`/`close` 的 `refs` 只能引它们）。

    ⭐ **2026-09-29**: 行首那一段从 `- m0021 「标题」 正文` 改成 **`- 〔m0021｜《标题》〕正文`**
    —— 与 R2 的新经历行（`_round_b_material`）**同一个头**, 由 `marks.head` 出
    （唯一实现）。⚠️ 原来标题写 `「」`, 而她那份视图里 `「」` 是**逐字原话**
    ⇒ 同形不同义; 而 `「」` 恰恰是会让她**抄错东西**的那种形状。
    ⚠️ **没起名就不出名字格**（不印"（无题）"这种假名字）—— 钥匙仍在, 她照样引得到。
    """
    lines: list[str] = []
    for nid in episode_ids:
        node = store.get(nid)
        if node is None:
            continue
        head = node.text if len(node.text) <= 120 else node.text[:120] + "…"
        lines.append(f"- {marks.head(node, key=node.id)}{head}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# L1（`relate`）的料 —— 「现有经历（候选）」与 `topics` 的印法（2026-10-07, P2）
# ---------------------------------------------------------------------------

#: L1 的「现有经历（候选）」上限 —— **整段**最多摆几条。
#: ⚠️ 认知那侧是 `recall.CAND_K = 3` **每条**; 经历这边不按条算 —— 候选池是**整个历史**
#: （真机今天两位数, 以后三位数）, 而一段里她实际会连的边是"几条"。6 = 摆得下
#: "这一段可能同类的几条", 又不至于把注意力铺开。要调先看 P6 的观测（孤立经历的账）。
DIGEST_RELATE_CAND_K = 6


def _clip(text: object, n: int = 120) -> str:
    """正文截断（**只截正文** —— 头里的名字是地址, 截一半等于把地址截坏）。"""
    s = str(text or "")
    return s if len(s) <= n else s[:n] + "…"


def _axes_field(topics) -> list[str]:
    """`topics` 印成信息头里的一格: `轴 苔藓·天台`（没有 ⇒ 整格不出现）。

    ⭐ **必须印**（P2 的理由）: L1 判 `akin` 时 `on` 要落在**两端 `topics` 的交集**里 ——
    看不见它, 那个词就只能靠猜, 猜不中就**静默丢行**（P1b-2 期间正是这样）。

    ⚠️ 多值用 `·` 并列, ⛔ **不能用 `｜`** —— 那是字段分隔（`marks.FIELD_SEP`）。
    """
    vals = [str(t).strip() for t in (topics or ()) if str(t or "").strip()]
    return [f"轴 {'·'.join(vals)}"] if vals else []


def _episode_candidates(store: "WikiStoreV2", episode_ids: list[str], *,
                        k: int = DIGEST_RELATE_CAND_K,
                        now="" ) -> tuple[str, list[str]]:
    """L1 的料之二: **已有的经历里, 可能跟这一段同类的那几条**（P2）。

    ⭐ **凭什么挑 = 两端 `topics` 有交集** —— 与 `akin` 的判据（`on` ∈ 两端交集）**同源**。
    引擎**不判**"这两条是不是同类"（那是她的活）, 它只做一件纯集合运算: 摆出那些
    **过得了校验的两端**。交集为空的旧经历摆上去也没用 —— 她写出来的 `akin` 会被
    `on` 那一关丢掉, 白占注意力。

    排序: 交集**元素多**的在前（越像越靠前）; 同数按 `ts` 新的在前。
    ⚠️ 一条旧经历都没相交 ⇒ **这一段的经历是孤立的**（那也是一个结论, 不编候选）。

    ⚠️ **摆不出候选时返回的不是空串, 而是"（无 —— 为什么）"**（P6, 2026-10-08）:
    空串会被 `_join_sections` 的 `if body` **连段标题一起吞掉** ⇒ 她既看不到
    「现有经历（候选）」这一格, 也不知道"候选是空的" —— 而**"没有可接的旧事"本身
    就是信息**（那她就不该硬写 `akin`）。⭐ 两种"空"是**两件事**, 文案分开:
    「本段经历没有标轴」（没法比）≠「没有一条同轴」（比过了, 真没有）。

    ⚠️ `now` 给了就印"多久以前 / 日期"两格 —— 契约那句"同一件事的先后两段**不算**
    `akin`（那是时间上的接续）"要她判得出来, 就得看得见旧事有多旧。

    ⚠️ 每一行印的 `轴 …` 是**交集**（不是那条旧经历的全部 `topics`）—— 摆出来的每个词
    都得能用: 印一个不在交集里的词, 只会诱她写一条**过不了校验**的 `akin`。

    Returns: `(text, ids)`; `ids` = 摆出来的**真实 id**（喂 parse 的 `target_ids`
        与 `topics_of`）。摆不出 ⇒ `（无 …）` + `[]`。
    """
    ids = {str(i) for i in episode_ids}
    mine: list[set[str]] = []
    for nid in ids:
        node = store.get(nid)
        if node is not None and node.topics:
            mine.append({str(t) for t in node.topics})
    if not mine:
        return "（无 —— 本段经历没有标轴, 无法比对）", []
    scored: dict[str, tuple[int, str, list[str]]] = {}
    for old in store.all():
        if old.kind != "episode" or old.id in ids:
            continue
        topics = [str(t) for t in old.topics]
        best, axes = 0, []
        for want in mine:
            common = [t for t in topics if t in want]
            if len(common) > best:
                best, axes = len(common), common
        if best:
            scored[old.id] = (best, str(old.ts or ""), axes)
    if not scored:
        # 比过了、真没有（≠ 上面那支"没法比"）—— 抬头要留着, 让她看见这个结论
        return "（无 —— 已有的经历里没有一条与本段同轴）", []
    order = sorted(scored.items(), key=lambda kv: kv[1][1], reverse=True)  # ts 新的在前
    order.sort(key=lambda kv: -kv[1][0])                                  # 再按交集大小
    lines: list[str] = []
    ids_out: list[str] = []
    for oid, (_n, _ts, axes) in order[:k]:
        node = store.get(oid)
        if node is None:
            continue
        head = marks.head(node, key=oid, now=now, extra=_axes_field(axes))
        lines.append(f"{head}{_clip(node.text)}")
        ids_out.append(oid)
    return "\n".join(lines), ids_out


# ---------------------------------------------------------------------------
# L2（`cognize`）的料 —— 「本段归类的群」+「被连过的经历」（2026-10-08, P8）
# ---------------------------------------------------------------------------

#: L2 的「本段归类的群」**摆几组**（用户 2026-10-08: *"GROUPS 数可以增加了…
#: 我觉得 2-3 都可以"* —— 前提是他把每块摆的成员数砍小了（`DIGEST_L2_MEMBERS=4`）:
#: 每块的料短了 ⇒ 一次摆得下更多块）。
#: 挑法见 `_groups_for_l2`: **本段新归入多的先**, 平手时**还没写过沉淀的先**。
DIGEST_L2_GROUPS = 3

#: 「被 L1 连过」= **L1 的动作面那几条边**（`RELATION_ACTIONS` —— 契约单源, ⛔ 不另抄一份）。
#: ⚠️ **2026-10-08（E3）起是四条**（`supports`/`akin`/`contradicts`/`evolved_from`）——
#: `about` 移出了动作面（归属改由**引擎**从节点 `tags` 的 `#entity:` 派生）⇒ 它不再算
#: "被 L1 连过"。**这是判据的正确收紧**: 一条经历只带"关于谁"的标记, 不等于"她把它
#: 跟别的经历/看法连上了" ⇒ 它仍然是**孤立经历**, 不进 L2（P8 的原始门槛）。
#: ⚠️ `member_of` **不在里面**（那是 `group` 落的边）—— 它要是算进来, 每个归了类的经历
#: 都成了"被连过", 孤立经历那道理应存在的门槛就失效了。
_L2_LINK_RELS = frozenset(a.name for a in RELATION_ACTIONS)

#: 一类最多印几条**已有成员**（用户 2026-10-08 裁: 4 条 —— 8 条太多）。
#: ⚠️ **本段新归入的不吃这个上限**（它们是这一趟的**理由**, 必须看得见）。
DIGEST_L2_MEMBERS = 4


def existing_entities_line(store, *, texts=()) -> str:
    """【已有的对象】—— ⭐ **写 `#entity:` 的那两轮都要看这一栏**（R1 记经历 / L2 写看法）。

    **为什么要给**（用户 2026-10-08 裁）: 防她自己造 alias —— 她只该照这里出现过的
    **名字或别名**写 `#entity:`; 自造一个新叫法 ⇒ 引擎 `find_entity` 认不出 ⇒
    **同一个人被重复建**（认人那一轮的目的正是建"还没有的"对象, 所以它不会替你拦住）。

    ⚠️ 印法与 L1 当年那一栏**同一个实现**（`entities.object_lines`: 真身 id + 名字（别名）
    + 一行字面命中提示）—— 同一张图, 两处长得一样。
    ⚠️ 空表 ⇒ 印一句"为什么空"（P6 的口径: 空串会被 `_join_sections` 连抬头一起吞掉）。
    """
    from core.brain import entities as _ent
    text, _ids = _ent.object_lines(store, texts=texts)
    return text or "（还没有任何对象 —— 这条涉及谁, 就照你看到的那个称呼写）"


def _l2_material(ctx) -> tuple[str, str, list[str]]:
    """L2 的三样料 → `(「本段归类的群」, 「被连过的经历」, **她能引用的经历 id**)`。

    ⚠️ **两块互相知道**（所以必须同一个函数产出）: 已经在【被连过的经历】里印过**全文**的
    经历, 在群块的「本段新归入」里**只印把手**（`〔m0022｜《被感谢的人》〕（正文见下）`）——
    免得同一段正文在一份料里出现两遍。⛔ 但**不许丢**: 没在别处印过的照印全文
    （经历可能"刚归了类却没被连过"）。

    ⭐ **第三个返回值（P10 补）** = `parse` 的 `evidence_ids`: **料里印出来过的全部经历**
    =【被连过的经历】∪【群块印过的成员】—— "右边能引用的 = 她看到的全部"
    （L1 的教训: 少一类就把合法行判成**编造 id** ⇒ 整包拒 ⇒ 白跑一次重试）。
    ⛔ **不另算一份**（另算必然与渲染漂开）。

    两块各自的空 ⇒ 印一句**为什么空**（P6 的口径: 空串会被 `_join_sections` 连抬头
    一起吞掉, 她既看不见这一格、也不知道那个结论）。
    """
    linked_ids = _linked_episode_ids(ctx)
    rows: list[str] = []
    for m in linked_ids:
        node = ctx.store.get(str(m))
        rows.append(_episode_line(ctx.store, m, now=ctx.now_ts, body=150,
                                  extra=_axes_field(getattr(node, "topics", None))))
        about = _about_line(ctx.store, m)              # 只在真有 `about` 边时出现
        if about:
            rows.append(about)
    linked = "\n".join(rows) or (
        "（这一段没有被连过的经历 —— 归纳没有立足点, 那就什么都别造）")
    blocks: list[str] = []
    shown: list[str] = []
    for gid, new in _groups_for_l2(ctx):
        block, ids = _group_block(ctx.store, gid, new_ids=new,
                                  linked_ids=set(linked_ids), now=ctx.now_ts)
        blocks.append(block)
        shown += ids
    grp = "\n\n".join(blocks) or (
        "（这一段没有新归类的群 —— 沉淀那半这趟不用写, 只造看法）")
    return grp, linked, list(dict.fromkeys([*linked_ids, *shown]))    # 去重保序


def _linked_episode_ids(ctx) -> list[str]:
    """**被 L1 连过的**本段经历（规格 §3: "读边取两端, 纯计算"）。

    判据 = 本段新建的 episode 里，**被 L1 那几条边**（`_L2_LINK_RELS`）沾到的那些。
    ⚠️ **`member_of` 不算**（那是 `group` 落的边, 每个归了类的经历都有它）——
    我第一版数"任意边", 结果**凡是被归了类的经历都不再孤立** ⇒ 天然门槛整个失效
    （自测 `test_l2_body_text_appears_exactly_once` 抓到）。
    ⭐ 判据从 `RELATION_ACTIONS`（L1 的动作面 = 契约单源）取, ⛔ 不另抄一份边名。

    孤立经历（一条这样的边都没有）**不进 L2** —— 它跟任何已有认知/经历都没关系
    ⇒ 归纳没有立足点（那是**天然的归纳门槛**, 规格 §3）。
    """
    touched: set[str] = set()
    for e in ctx.store.edges():
        if str(e.rel) in _L2_LINK_RELS:
            touched.add(str(e.src))
            touched.add(str(e.dst))
    return [str(m) for m in ctx.episode_ids if str(m) in touched]


def _groups_for_l2(ctx, *, cap: int = DIGEST_L2_GROUPS) -> list[tuple[str, list[str]]]:
    """本段**新归入过成员**的类 → `[(类 id, 本段新归入的成员 id), …]`（最多 `cap` 组）。

    ⚠️ 「本段新归入」的判据 = **本段新建的经历 ∩ 有 `member_of` 边**（用户 2026-10-08 点头:
    不覆盖"老经历本段才被归类"那个边角 —— `group` 自吞后补归类的那些要等下一段）。

    ⭐ **排序 = `(-本段新归入数, 有没有沉淀, 类 id)`**:
      · 新归入多的先（"这一段刚给它添了最多东西" ⇒ 最该更新）;
      · ⚠️ 平手时**还没写过沉淀的先** —— ⛔ 不能只按 id 排: 那样"**从没写过沉淀的类**"
        会永远排在队尾, 而它可能**永远轮不到**（一段只摆 `cap` 组）。这条是"永远不写"
        那个缺口的一半解药（另一半 = 旋钮给到 2~3）;
      · 最后按 id ⇒ 结果稳定可复现（同输入同输出）。
    """
    seg = {str(m) for m in ctx.episode_ids}
    by_group: dict[str, list[str]] = {}
    for e in ctx.store.edges():
        if e.rel == "member_of" and str(e.src) in seg:
            by_group.setdefault(str(e.dst), []).append(str(e.src))

    def _rank(kv: tuple[str, list[str]]) -> tuple:
        gid, new = kv
        node = ctx.store.get(gid)
        return (-len(new), bool(node is not None and node.text), gid)

    return sorted(by_group.items(), key=_rank)[:max(int(cap), 0)]


def _episode_line(store, nid: str, *, now="", body: int = 120, extra=()) -> str:
    """一条经历的行 = **信息头 + 截断正文**（与 L1 的候选行**同一个印法**）。

    `extra` 追加在信息头里（L2 用 `轴 …` —— `_axes_field` 产的那一格）。
    """
    node = store.get(str(nid))
    if node is None:
        return ""
    return f"{marks.head(node, key=str(nid), now=now, extra=extra)}{_clip(node.text, body)}"


def _about_line(store, nid: str) -> str:
    """⭐ 「关于谁」那一行（`   ↳ 关于: x0001 老师（sensei）`）—— 没有 `about` 边 ⇒ `""`。

    ⚠️ **印证 / 同类不印**（用户 2026-10-08 裁: *"要么给全, 要么不给…现有的关系不需要
    知道它的印证什么的"*）—— 那些是"已有成分之间的关系", 而契约明写着
    "不用你判, 上一趟已经判过了" ⇒ 摆出来不止没用, 还诱她多想。
    ⭐ 「关于谁」留着（用户裁决: *"还是保留吧, 保障扩展"*）: 它是 `entity` 那条链在 L2
    视野里的**唯一把手**（将来 entity 有载荷 / 有读者时, 这一行就是入口）。
    印法走 `entities.entity_label`（与 L1 的对象候选**同一处实现**）。
    """
    from core.brain import entities as _ent

    ends = [store.get(x) for x in store.graph().targets(str(nid), "about")]
    ends = [n for n in ends if n is not None]
    if not ends:
        return ""
    return "   ↳ 关于: " + " · ".join(_ent.entity_label(n) for n in ends)


def _members_by_precious(store, gid: str) -> list[str]:
    """类的成员（`member_of` 入边）—— **难忘降序**, 同分**时间新的在前**（结果稳定）。"""
    ids = [str(e.src) for e in store.edges()
           if e.rel == "member_of" and str(e.dst) == str(gid)]
    nodes = [n for n in (store.get(i) for i in ids) if n is not None]
    nodes.sort(key=lambda n: (n.significance or 0.0, str(n.ts or "")), reverse=True)
    return [n.id for n in nodes]


def _group_block(store, gid: str, *, new_ids: list[str], linked_ids: set[str],
                 cap: int = DIGEST_L2_MEMBERS, now="", body: int = 120
                 ) -> tuple[str, list[str]]:
    """【本段归类的群】的**一块** → `(文本, **印出来的成员 id**)`。

    ⭐ 第二个返回值是 `evidence_ids` 的一半（"她看到的 == 她能引用的"）——
    从渲染里带出来, ⛔ 不另算一份（另算必然与这里的截断/顺序漂开）。

    ⚠️ 「已有成员」按**难忘降序**（同分时间新的在前）—— 沉淀要概括"这一类事的共同点",
    难忘的更有代表性; 超 `cap` 只印前几条并**明说还有几条没印**（不静默截断）。
    ⚠️ 「本段新归入」**不吃 `cap`**（见 `DIGEST_L2_MEMBERS`）。
    """
    node = store.get(str(gid))
    if node is None:
        return "", []
    members = _members_by_precious(store, str(gid))
    new_set = {str(x) for x in new_ids}
    others = [m for m in members if m not in new_set]
    printed: list[str] = []
    out = [f"群 {gid}《{node.title}》（这一类现在有 {len(members)} 条经历 · "
           f"本段新归入 {len(new_ids)} 条）"]
    if node.text:
        out.append(f"  现状沉淀: {_clip(node.text, 200)}")
        out.append("            （⚠️ 整段重写: 你新写的这句会替掉它 —— 要保留它说对的部分）")
    else:
        out.append("  现状沉淀:（还没有 —— 你写的这一句会是它的第一句）")
    out.append("  本段新归入:")
    for m in new_ids:
        mn = store.get(str(m))
        if mn is None:
            continue
        printed.append(str(m))
        if str(m) in linked_ids:
            # 正文在【被连过的经历】里印过全文（一份料里同一段正文只出现一次）
            out.append(f"    〔{m}｜《{mn.title}》〕（正文见下）")
        else:
            out.append("    " + _episode_line(store, m, now=now, body=body,
                                              extra=_axes_field(mn.topics)))
    if others:
        shown, rest = others[:cap], max(len(others) - cap, 0)
        out.append(f"  已有成员（按难忘排, 最多印 {cap} 条"
                   + (f"; 还有 {rest} 条没印" if rest else "") + "）:")
        for m in shown:
            mn = store.get(str(m))
            if mn is not None:
                printed.append(str(m))
                out.append("    " + _episode_line(store, m, now=now, body=body,
                                                  extra=_axes_field(mn.topics)))
    return "\n".join(out), printed


# ---------------------------------------------------------------------------
# R2 / R3 的料
# ---------------------------------------------------------------------------

def _node_texts(store: "WikiStoreV2", ids: list[str]) -> list[str]:
    """**要归属的那些节点的正文**（喂 `entities.hit_set` 扫称呼用）。

    连 `title` / `verbatim` 一起给 —— 称呼常出现在这两处（"老师"多半在标题或原话里,
    而不在她自己那句总结里）。取不到 → 跳过（绝不编）。
    """
    out: list[str] = []
    for nid in ids:
        node = store.get(str(nid))
        if node is None:
            continue
        for t in (node.text, node.title, node.verbatim):
            if isinstance(t, str) and t.strip():
                out.append(t)
    return out


def _round_b_material(store: "WikiStoreV2", episode_ids: list[str],
                      local_of: dict[str, str],
                      embed_fn: "EmbedFn | None",
                      *, char_id: str = "") -> str:
    """Round B 输入: 新经历摘要 + 每条引擎候选提示（板块 5）。

    每条 episode 用 text 走 recommend_candidates 与现有认知碰撞,
    把最像的几条**列出来给 LLM 参考**（⭐ N2 起: 带正文 + 被引 + 边 + 为什么）。

    ⭐ **N2（2026-09-29）两处形态变化**（都是"看不见就写不出来"那条）:
      · 新经历行: `m0025 「标题」 正文` → **`〔m0025｜《标题》〕正文`**
        （编号是钥匙、书名号里是 gist; 顺带修 `「」` 与她视图里"逐字原话"的同形不同义）
      · 候选行: `→ 候选(sim 0.72): u0001 u0003` → **每条候选一行**,
        带 `〔u0001｜belief｜被引 3〕正文` + 边续行 + `为什么: tags[…]/语义 …`
        （旧形态要求 LLM 自己去翻上面那张表, 而"为什么推荐"完全看不见）

    ⚠️ **候选只是提示, 不分档、不强制**（2026-09-15 T17）: 原先
    `≥CAND_HIGH` 会标【疑似同主题】并让 parse 层**结构强制**禁 `add`——
    而那个阈值从未标定过、实测两模型皆 6/6 全越线 → 新认知永远长不出来。
    现在排序取 top-k 无条件列出，判断全在 LLM（判 add 要在 note 里说明理由）。

    **2026-09-13 V3-0（DESIGN_WIKI_V3 §3.5）**: 末尾打一行**写路径召回台账**
    `recall_write char=… eps=… cands=… best=… mode=…`。

    Returns: episodes_text（含候选提示行）。
    """
    from core.brain.read import recall_ledger
    from core.brain.read.recall import _thr, CAND_K
    from core.brain.read.recall import recommend_candidates
    from core.brain.read.render import render_cognition_line

    thr_k = int(_thr("cand_k", CAND_K))
    acc = recall_ledger.CollisionAccount(char_id)
    modes: list[str] = []

    lines: list[str] = []
    for nid in episode_ids:
        node = store.get(nid)
        if node is None:
            continue
        head = _clip(node.text)
        # 头由 `marks.head` 出（**唯一实现**）—— `〔m0025｜《今天的杂草屋》｜轴 苔藓〕正文`。
        # 编号是**钥匙**（L1 的 `relations` 用它指 episode, 真实 id）；
        # 书名号里是**gist**（正文被截到 120 字, 8~16 字的名字是"这是哪件事"的压缩）。
        # ⭐ P2 起多一格 `轴 …` —— `akin` 的 `on` 要落在两端 `topics` 交集里, 不印就只能猜。
        lines.append(f"{marks.head(node, key=node.id, extra=_axes_field(node.topics))}{head}")
        if node.verbatim:
            lines.append(f"    原话: {node.verbatim}")
        query = f"{node.text} {node.verbatim}".strip()
        why: list[str] = []
        cands = recommend_candidates(store, query, embed_fn=embed_fn,
                                     mode_out=modes, why_out=why)
        cands = [(c, s) for c, s in cands if c.id in local_of]   # 只标已渲染的
        acc.episode(n_cand=len(cands),
                    best_sim=(cands[0][1] if cands else 0.0))
        if cands:
            # ⭐ N2: 候选不再只给编号 —— **编号 + 正文 + 被引 + 边 + 为什么被推荐**。
            # 旧形态 `→ 候选(sim 0.72): u0001 u0003` 要求它自己去翻上面那张表,
            # 而"为什么推荐"（tags 命中 / 语义）今天完全看不见 —— 看不见就判不准。
            best = cands[0][1]
            reason = why[0] if why else ""
            lines.append(f"    → 候选 {best:.2f}（为什么: {reason}）:")
            graph = store.graph()
            for i, (c, _s) in enumerate(cands):
                rows = render_cognition_line(store, c, graph, local_of, max_body=60,
                                             indent="       ")
                # ⭐ 只有第一个候选带边续行（后面几个是备选, 印全了纯占地方）
                lines.extend(rows if i == 0 else rows[:1])
            lines.append("       （仅供参照 —— 是不是同一条线上的, 你自己判）")

    # 通道口径: 全程 semantic / 全程 keyword / 混合（部分 episode 失败降级）
    if modes and all(m == "semantic" for m in modes):
        acc.mode = "semantic"
    elif modes and all(m == "keyword" for m in modes):
        acc.mode = "keyword"
    elif modes:
        acc.mode = "mixed"
    acc.log(thr_k=thr_k)
    return "\n".join(lines) or "（无）"
