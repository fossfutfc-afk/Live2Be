"""material.py — digest 各轮的**料**（2026-09-29 从 `pipeline.py` 拆出）。

"这一轮吃什么"的真源是 `rounds.ROUNDS` 的 `material` 格（段标题 + 顺序）;
本模块是那些**正文**的构造者（引擎侧, 零 LLM）:

| 给谁 | 函数 | 料 |
|---|---|---|
| **R0** | `_segment_time_text` · `_special_days_text` · `_open_pinned_text` · `_ledger_ids` | 本段的时间 · 日子 · 还开着的约定（带编号 + 期限）· **资格位**（L3, 2026-10-05） |
| R1 | `_collect_visual_prompts` · `_segment_emotion_keys` | 画面记忆 · 本段情绪标尺 |
| R4 | `_open_pinned_text` · `_episode_lines` | 还开着的约定（带编号）· 本段新增经历 |
| **L1** | `_round_b_material` · `_episode_candidates` | 新经历（钥匙 + 标题 + 正文 + 原话）+ 每条候选（正文/被引/边/为什么）· **现有经历（候选）**（`like(spec="digest")` 排出来的最像的几条 + 为什么）|
| **L2** | `_l2_material` · `_akin_region_rows` · `collided_beliefs_block` | **这次的事**（本段被 L1 连过的, 立足点）· **这一类事**（一跳 `akin` 邻居 —— 本段那几条只出信息头）· **跟这条撞上的现有看法**（共享证据 + 撞在哪）|
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

from contract.digest import RELATION_ACTIONS, STATE_VALUES, is_full_date
from core.brain import marks
from core.brain.graph import REL_AKIN
from core.digest.rounds import RoundSpec
from core.digest.segment import _span_range
from infra import paths

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
                      today: date | None = None,
                      first_day: date | None = None) -> str:
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

def _day_of(ts: object) -> date | None:
    """事件 `ts` → **那一天**（`2026-05-10T21:33:00+08:00` ⇒ `2026-05-10`）; 坏值 ⇒ None。"""
    raw = str(ts or "").strip()
    if len(raw) < 10:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _segment_days(events) -> list[date]:
    """本段跨了哪几天（升序去重）—— 【本段的时间】与"段起"共用这一处。

    ⚠️ 段的**最后一天**就是这一段的"今天"（`ctx.now_ts` 同源: 段内最后一条内容事件）
    —— 资格位判"过期没有"用的是它, **不是**机器的挂钟（补跑旧段时才不会全判成超期）。
    """
    return sorted({d for d in (_day_of(getattr(e, "ts", "")) for e in events) if d})


def _segment_time_text(days: list[date]) -> str:
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


def _parse_month_day(raw: str) -> tuple[int, int] | None:
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


def _role_birthday(char_id: str) -> tuple[int, int] | None:
    """角色的生日 —— 读**档案** `config/characters/{id}/profile.yml` 的 `birthday`。

    为什么读档案、不读 `mmt_registry.toml`: 后者是**显示用**生日, 而这份料是给 AI
    折算日期用的（两个真源的分工写在 `core/mmt/mmt_registry.py` 的注释里）。
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


def _due_date(item) -> date | None:
    """条目的 `due` → 那一天; **不是全日期 ⇒ None**（= 没有期限）。

    ⚠️ 判据与契约**同源**（`contract.digest.is_full_date`）——
    料与校验对"什么算日期"必须一个口径, 否则会印出一个校验层不认的日期。
    ⛔ **绝不喂 `age_days`**（它吃 aware 时间戳, 裸日期当场 TypeError —— P1）。
    """
    raw = str(getattr(item, "due", "") or "").strip()
    return date.fromisoformat(raw) if is_full_date(raw) else None


#: 期限那一格的引导（四个空格 —— 与 `_open_pinned_text` 的 `- ` 对齐, 一行一件事）
_DUE_LEAD = "    期限 "


def _due_cell(item, *, today: date | None, first_day: date | None = None) -> str:
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


def _overdue_detail(items: list, overdue_ids: set[str], *, today: date | None) -> str:
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
                today: date | None) -> tuple[set[str], set[str]]:
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


def _episode_lines(store: WikiStoreV2, episode_ids: list[str]) -> str:
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
# L1（`relate`）的料 —— 「现有经历（候选）」（2026-10-07 P2; 2026-10-14 换源走 `like`）
# ---------------------------------------------------------------------------

#: L1 的「现有经历（候选）」上限 —— **整段**最多摆几条（也是每条新经历问 `like` 的 k）。
#: ⚠️ 认知那侧是 `recall.CAND_K = 3` **每条**; 经历这边不按条算 —— 候选池是**整个历史**
#: （真机今天两位数, 以后三位数）, 而一段里她实际会连的边是"几条"。6 = 摆得下
#: "这一段可能同类的几条", 又不至于把注意力铺开。要调先看 P6 的观测（孤立经历的账）。
DIGEST_RELATE_CAND_K = 6


def _clip(text: object, n: int = 120) -> str:
    """正文截断（**只截正文** —— 头里的名字是地址, 截一半等于把地址截坏）。"""
    s = str(text or "")
    return s if len(s) <= n else s[:n] + "…"


#: ⏸ **`_axes_field` / `轴 …` 那一格 2026-10-14 随 `topics` 退役删掉**（用户裁 C1）——
#: 它当年有两个用处（L1 判 `akin` 时挑 `on`、判"同轴"），两个都随 `topics` 走了。
#: ⚠️ **别拿 `tags` 顶替**（真机实测: "约定/笔记"这种泛词让一条经历跟 9 条相连 ⇒ 零区分力）。


def _episode_candidates(store: WikiStoreV2, episode_ids: list[str], *,
                        embed_fn: EmbedFn | None = None,
                        k: int = DIGEST_RELATE_CAND_K,
                        now="" ) -> tuple[str, list[str]]:
    """L1 的料之二: **已有的经历里, 可能跟这一段像的那几条**（P2; ⭐ 2026-10-14 换源）。

    ⭐ **凭什么挑 = `like(spec="digest")`** —— query = 本段每条经历自己的正文
    （多条就各问一次, 候选**取并集、按分降序去重**）。引擎**不判**"这两条是不是同类"
    （那是她的活）, 它只摆**最像的几条**, 并把**为什么像**（`like` 的 `why`）一起印出来 ——
    而"看不见理由"正是老形态 `→ 候选(sim 0.72): u0001` 的毛病（N2 修过一次）。

    ⏸ **换源的理由**（用户 2026-10-14 裁"先把 `topics` 退役掉"）: 老判据是
    **两端 `topics` 有交集**, 而真机（haruka）21 条经历里只有 3 条标了 `topics`、
    那 3 条又**互相不共轴** ⇒ 候选**恒 0 条**（L1 的 `akin` 行因此一直没有产出）。
    新判据走读路径那条**写好了却零调用**的 `digest` 档（`like.SPECS["digest"]`）:
    字面 1.00 · **语义 1.00** · 结构 0.35 · 时间 0.15 · 重要 0.15
    （那一档的池里还有认知, 这里只取 `episode`）。

    ⚠️ **`semantic` 要 embedder**: 缺了它 `like` 自动把那一路降级（它自己的 `skip=` 台账
    会印原因）, 剩下四路照跑 —— L1 的账里有 `sim=` 一格（`cands=0` 的解释器）。

    ⚠️ **摆不出候选时返回的不是空串, 而是"（无 —— 为什么）"**（P6, 2026-10-08）:
    空串会被 `_join_sections` 的 `if body` **连段标题一起吞掉** ⇒ 她既看不到
    「现有经历（候选）」这一格, 也不知道"没有可接的旧事" —— 而**那本身是信息**
    （她就不该硬写 `akin`）。

    ⚠️ `now` 给了就印"多久以前 / 日期"两格 —— 契约那句"同一件事的先后两段**不算**
    `akin`（那是时间上的接续）"要她判得出来, 就得看得见旧事有多旧。

    Returns: `(text, ids)`; `ids` = 摆出来的**真实 id**（喂 parse 的 `target_ids`）。
        摆不出 ⇒ `（无 …）` + `[]`。
    """
    from core.brain.read.like import RecallCtx, like

    mine = {str(i) for i in episode_ids}
    scored: dict[str, tuple[float, str]] = {}          # 候选 id → (最好的一分, 为什么)
    for nid in episode_ids:
        node = store.get(nid)
        if node is None:
            continue
        query = f"{node.text} {node.verbatim or ''}".strip()
        if not query:
            continue
        ctx = RecallCtx(now=now, query=query, embed_fn=embed_fn,
                        char_id=str(getattr(store, "char_id", "") or ""))
        # ⚠️ 多要 `len(mine)` 几个: 召回池里有**本段自己那几条**（她刚记下就进库了,
        # 与 query 逐字相同 ⇒ 分最高）, 不补这一点就等于**自己占掉自己的名额**。
        for cand in like(store, ctx, spec="digest", k=int(k) + len(mine)):
            cid = str(cand.node.id)
            if cid in mine or str(cand.node.kind) != "episode":
                continue                  # 本段自己的不摆; 认知那两面归上面那一格
            best, why = scored.get(cid, (0.0, ""))
            if float(cand.score) >= best:
                scored[cid] = (float(cand.score), str(cand.why or why))
    if not scored:
        # 召回真没找到（≠ "语义那一路没起来" —— 那个由 L1 台账的 `sim=` 说）
        return "（无 —— 召回没找到跟这一段像的旧经历）", []
    order = sorted(scored.items(), key=lambda kv: (-kv[1][0], kv[0]))
    lines: list[str] = []
    ids_out: list[str] = []
    for oid, (score, why) in order[:max(int(k), 0)]:
        node = store.get(oid)
        if node is None:
            continue
        head = marks.head(node, key=oid, now=now, extra=[f"候选 {score:.2f}"])
        lines.append(f"{head}{_clip(node.text)}")
        if why:
            lines.append(f"   → 为什么: {why}")           # ⭐ 摆它的理由（看不见就判不准）
        ids_out.append(oid)
    return "\n".join(lines), ids_out


# ---------------------------------------------------------------------------
# settle 的料 —— 「这一段认下的对象」（2026-10-13, 那一轮从"只认人"扩成"认人 + 写看法"）
# ---------------------------------------------------------------------------

#: settle 的「这一段认下的对象」**摆几个** —— ⚠️ 它是**标尺不是硬闸**（超出只截 + 明说还有几个）。
#: 3 = 一段里她不可能对十个人改观, 而每个对象四五行的料不短。
DIGEST_SETTLE_OBJECTS = 3
#: 每个对象最多印几条「这一段它出现的地方」（同 `DIGEST_L2_AKIN` 的量级: 都只是"摆几条看得见的", ⛔ 不是闸）。
DIGEST_SETTLE_REFS = 3


def settle_objects_block(store, ids, *, now="", body: int = 110) -> tuple[str, list[str]]:
    """【这一段认下的对象】—— settle **写看法**那一半的唯一依据（2026-10-13）。

    来源 = 本段新节点（`ids`）里那些**解析得到的引用** = `about` 边的 `dst`。
    ⛔ **不是"库里全体对象"**（那是名字表: 印不下, 也不必印 —— 她只该改**这一段提到过的**）。

    每个对象印::

        x0001 老师（sensei）
          立场: 老师是第一个不会嫌弃我的人        ← 现 text; 空 ⇒ （还没写过）
          这一段它出现的地方:
            〔m0031｜《和老师的公园散步》｜3 天前｜10/10〕…正文…
            〔u0002｜belief｜被引 1〕老师会把我随口说的话记住
          正文里还提到过它 1 次（没标引用）        ← ⭐ 只当提示
          共出现 3 次（第一次在 2 周前）           ← 它的**引用面**（全部 `about` 入边）

    ⚠️ **两个提示的分工**（用户 2026-10-13 裁"两个都印"）:
      · 「正文里还提到过它 N 次（没标引用）」= 引擎扫**本段正文**数出来的 —— 真机实测
        "老师" **21/21 恒真、零区分力**（`DESIGN_ENTITY_TAGS §6.3`）⇒ 它**只能当提示**:
        正文里出现一个称呼 ≠ "这条记忆是关于它的";
      · 「共出现 N 次（第一次在 …）」= **她认过的引用面**（`about` 入边数 + 最早那条的时间）
        —— 这一条才是**可依据的**（她自己在写节点时标过"这条涉及谁"）。
    ⚠️ `（还没写过）` **不是错**: 出厂只给 `interperson.yml` 里的人装立场, 真机
      `老师`/`杂草屋`/`夏莱` 三条里就有空的 —— 那只是"她还没想过这个人"。

    Returns: `(文本, 印出来的那些对象的真身 id —— 一一对应)`。
    空 ⇒ 印一句**为什么空**（P6 的口径: 空串会被 `_join_sections` 连抬头一起吞掉）。
    """
    from core.brain.entities import _body_hits, entity_label, form_key, surface_forms

    seg = [str(i) for i in ids]
    segset = set(seg)
    edges = list(store.edges())
    graph = store.graph()
    refs: list[str] = []
    for e in edges:
        if str(e.rel) == "about" and str(e.src) in segset and str(e.dst) not in refs:
            refs.append(str(e.dst))
    if not refs:
        return "（这一段没有提到任何认识的对象 —— 写看法那半这趟没有依据）", []

    texts_key = [form_key(t) for nid in seg
                 for t in ((getattr(store.get(nid), "text", "") or ""),
                           (getattr(store.get(nid), "title", "") or ""))]
    shown: list[str] = []
    out: list[str] = []
    for eid in refs[:max(int(DIGEST_SETTLE_OBJECTS), 0)]:
        node = store.get(eid)
        if node is None:
            continue
        shown.append(eid)
        out.append(entity_label(node))
        text = str(node.text or "").strip()
        out.append(f"  立场: {text}" if text else "  立场: （还没写过）")
        mine = [nid for nid in seg
                if any(str(e.rel) == "about" and str(e.src) == nid and str(e.dst) == eid
                       for e in edges)]
        out.append("  这一段它出现的地方:")
        for nid in mine[:max(int(DIGEST_SETTLE_REFS), 0)]:
            src = store.get(nid)
            if src is None:
                continue
            if src.kind == "episode":
                out.append("    " + _episode_line(store, nid, now=now, body=body))
            else:
                head = marks.head(src, key=str(nid), kind=True, now=now,
                                  extra=[f"被引 {len(graph.supporters(str(nid)))}"])
                out.append(f"    {head}{_clip(src.text, body)}")
        unmarked = sum(1 for nid in seg if nid not in mine
                       and any(_body_hits(f, texts_key) for f in surface_forms(node)))
        if unmarked:                                   # ⭐ 只当提示（见 docstring）
            out.append(f"  正文里还提到过它 {unmarked} 次（没标引用）")
        fans = [str(e.src) for e in edges
                if str(e.rel) == "about" and str(e.dst) == eid]
        first = min((getattr(store.get(s), "ts", "") or "" for s in fans), default="")
        rel = marks.relative(first, now)
        out.append(f"  共出现 {len(fans)} 次" + (f"（第一次在 {rel}）" if rel else ""))
    if len(refs) > len(shown):                         # 截了要说（同群块的"还有 N 条没印"）
        out.append(f"（还有 {len(refs) - len(shown)} 个对象没印 —— 先写印出来的这几个）")
    return "\n".join(out), shown


# ---------------------------------------------------------------------------
# L2（`cognize`）的料 —— 「这次的事」+「这一类事」（2026-10-08 P8 / 2026-10-13 / 2026-10-14）
# ⭐ **2026-10-13: 相似簇接替了「本段归类的群」** —— 那一格由 `member_of` 喂, 而 `group`
#    退役后那条边不再有人落 ⇒ 恒空。新的一格喂它的是 **`akin`**（她自己认过的"同一类事"）:
#    老块是给她**写沉淀**用的, 而沉淀已停产; 新块是给她**写结论**用的 —— "这条看法不只被
#    这一段那一条撑着, 还有她早先认过'像'的那些" ⇒ 她才写得出"总是/每次"而不是"这一次"。
# ⭐ **2026-10-14 区域化**（用户裁）: 这两样东西**分成两个段头** —— 【这次的事】（本段被 L1
#    连过的, 归纳的立足点）与【这一类事】（它们的一跳 `akin` 邻居, 额外的证据）。
#    ⚠️ 从前它们挤在**一张平表**里（靠缩进与一个 `↳` 抬头区分）, 而簇**散在每条 anchor
#    下面** ⇒ 她数不出"这一类一共几条 / 跨多长时间", 而那正是"总是 / 每次"与"这一次"
#    的区别所在。**判据一个字没改**（一跳 · 打架的不摆 · 边建立序 · 先到先得）——
#    换的只是**摆放**, 顺带修掉"谁先处理谁的位置随机"那个顺序毛病。
# ---------------------------------------------------------------------------

#: ⭐ L2 的「这一类事」**整区**最多印几条**老经历**（= 印正文的那些）。
#: 5 = 与 `AKIN_JOIN_MAX` / `DIGEST_L2_COLLIDE` 同量级（一次归纳的立足点规模）。
#: ⚠️ **本段的信息头不占这个额度** —— 它们的正文在【这次的事】里, 让它们吃额度只会把
#: 老经历挤没（"这一类跨了多长时间"正是这一区存在的理由）。⏸ 旧语义 = 每条 anchor 3 条。
#: ⚠️ 超了**明说还有几条没印**（⛔ 不静默截断）; 而写入侧的额度是另一件事（`AKIN_JOIN_MAX`）。
DIGEST_L2_AKIN = 5

#: 「被 L1 连过」= **L1 的动作面那几条边**（`RELATION_ACTIONS` —— 契约单源, ⛔ 不另抄一份）。
#: ⚠️ **2026-10-08（E3）起是四条**（`supports`/`akin`/`contradicts`/`evolved_from`）——
#: `about` 移出了动作面（归属改由**引擎**从节点 `entity` 派生）⇒ 它不再算
#: "被 L1 连过"。**这是判据的正确收紧**: 一条经历只带"关于谁"的标记, 不等于"她把它
#: 跟别的经历/看法连上了" ⇒ 它仍然是**孤立经历**, 不进 L2（P8 的原始门槛）。
#: ⚠️ `member_of` **不在里面**（那是 `group` 落的边）—— 它要是算进来, 每个归了类的经历
#: 都成了"被连过", 孤立经历那道理应存在的门槛就失效了。
_L2_LINK_RELS = frozenset(a.name for a in RELATION_ACTIONS)


def existing_entities_line(store, *, texts=()) -> str:
    """【已有的对象】—— ⭐ **写引用名的那两轮都要看这一栏**（R1 记经历 / L2 写看法）。

    **为什么要给**（用户 2026-10-08 裁）: 防她自己造 alias —— 她只该照这里出现过的
    **名字或别名**写引用; 自造一个新叫法 ⇒ 引擎 `find_entity` 认不出 ⇒
    **同一个人被重复建**（认人那一轮的目的正是建"还没有的"对象, 所以它不会替你拦住）。

    ⚠️ 印法与 L1 当年那一栏**同一个实现**（`entities.object_lines`: 真身 id + 名字（别名）
    + 一行字面命中提示）—— 同一张图, 两处长得一样。
    ⚠️ 空表 ⇒ 印一句"为什么空"（P6 的口径: 空串会被 `_join_sections` 连抬头一起吞掉）。
    """
    from core.brain import entities as _ent
    text, _ids = _ent.object_lines(store, texts=texts)
    return text or "（还没有任何对象 —— 这条涉及谁, 就照你看到的那个称呼写）"


def _l2_material(ctx) -> tuple[str, str, list[str]]:
    """L2 的料 → `(【这次的事】, 【这一类事】, **她能引用的经历 id**)`。

    ⭐ **两个区**（用户 2026-10-14 裁; 判据一个字没改, 只换了摆放）——

        【这次的事】 本段被 L1 连过的那几条（**归纳的立足点**）
        〔m0013｜《咖啡厅的甜点》｜3 天前｜10-05〕老师约我去咖啡厅…
           ↳ 关于: x0001 老师

        【这一类事】 它们的一跳 `akin` 邻居（**她认过"是同一类事"的那些, 也算证据**）
        〔m0004｜《上次的甜点》｜三周前｜09-20〕上次老师也把点心分给我…
              〔m0022｜《被感谢的人》｜6 天前｜10/8〕（正文见上面【这次的事】）
        （还有 2 条没印 —— 先照印出来的这几条写）

    ⭐ **正文互斥**: 一条正文**全料只印一次** —— 本段的条目在第二区只出一行**信息头**
    （`（正文见上面【这次的事】）`）, ⛔ 不重复正文、**也不占额度**（额度只管老经历）。

    **判据**: 邻居 = **一跳 `akin`**（她认过的像, ⛔ 不走两跳 —— `walk.py` 那条纪律:
    真机那个簇两跳就串到别的簇去了）。

    ⭐ **第三个返回值** = `parse` 的 `evidence_ids`: **料里印出来过的全部经历**
    （"右边能引用的 = 她看到的全部" —— L1 的教训: 少一类就把合法行判成**编造 id**
    ⇒ 整包拒 ⇒ 白跑一次重试）。⚠️ **老经历也在内**（第二区里印出来的那些）—— 它们正是
    "这一类事"的另外几条, ⛔ 判它们"编造 id"就是把她自己的这一类锁在门外。
    ⛔ **不另算一份**（另算必然与渲染漂开）。

    第一区空 ⇒ 印一句**为什么空**（P6 的口径: 空串会被 `_join_sections` 连抬头一起吞掉,
    她既看不见这一格、也不知道那个结论）; 第二区空 ⇒ 整区连段头一起不印。
    """
    ids = [str(m) for m in _linked_episode_ids(ctx)]
    mine = set(ids)
    this_rows: list[str] = []
    for m in ids:
        node = ctx.store.get(m)
        if node is None:
            continue
        # ⚠️ 本段的每一条**都在自己这一行印正文**（第二区对它们只出信息头 —— 一份料里
        #    同一段正文只印一次, 而"印全文"这件事归这一块负责）
        this_rows.append(_episode_line(ctx.store, m, now=ctx.now_ts, body=150))
        about = _about_line(ctx.store, m)          # 只在真有 `about` 边时出现
        if about:
            this_rows.append(about)
    cls_rows, joined = _akin_region_rows(ctx.store, ids, mine=mine, now=ctx.now_ts)
    this_text = "\n".join(this_rows) or (
        "（这一段没有被连过的经历 —— 归纳没有立足点, 那就什么都别造）")
    # 去重保序: 本段的在前（第二区里印出正文的老经历接在后面）
    return this_text, "\n".join(cls_rows), list(dict.fromkeys(ids + joined))


def _akin_region_rows(store, anchor_ids: list[str], *, mine: set[str], now="",
                      cap: int = DIGEST_L2_AKIN, body: int = 150
                      ) -> tuple[list[str], list[str]]:
    """【这一类事】**整区**的行 → `(行, 印出正文的老经历 id)`。

    ⭐ **一个区, 不再是每条 anchor 一小块**（用户 2026-10-14 裁）: 同一个邻居挂在两条
    anchor 上 ⇒ 区内**先到先得**只印一次 —— 从前"它落在谁下面"由**处理顺序**决定,
    位置看起来随机（而且先处理过的 anchor 会从后面的簇里整个消失、后处理的才露信息头,
    同一件事两副面孔）。

    ⭐ **本段的条目（`mine`）只出信息头**: 它的正文在上面【这次的事】里, 全料只印一次;
    ⚠️ **信息头不占 `cap`** —— 额度管的是"这一类能看见几条**老经历**", 而本段那几条
    本来就在她眼前（让它们吃额度只会把老经历挤没）。

    ⚠️ **判据照抄旧版, 一字未改**: 一跳 `akin` · 与**它认过的那条**打架的不摆
    （同写入侧 `revise._join_akin`: 打架的证据不共撑一个结论）· 排序 = **边的建立序**
    （= 她认过的先后, 与写入侧取前 `AKIN_JOIN_MAX` 条**同一个口径**, 免得"她看到的"与
    "引擎并的"在截断时各挑各的）· ⛔ 只收 `episode`。
    ⏸ **`轴` 那一格 2026-10-14 撤**（随 `topics` 退役）: 邻居行的信息头只剩
    钥匙 + 标题 + 时间（`marks.head` 出）。

    Returns: `(行, 要当证据的老经历 id)` —— ⚠️ **信息头那几条不在第二个返回值里**
    （它们已经在第一区, 调用方的 `ids` 收着; 重复收也不出错, 但那是两个真源）。
    """
    rows: list[str] = []
    got: list[str] = []
    seen: set[str] = set()                        # 区内先到先得（正文 / 信息头都算）
    rest = 0
    for anchor in anchor_ids:
        aid = str(anchor)
        for cand in store.related(aid, REL_AKIN):
            if cand in seen or cand == aid:
                continue
            node = store.get(cand)
            if node is None or str(node.kind) != "episode":
                continue
            if store.conflicting(cand, aid):          # 打架的不摆（同写入侧）
                continue
            seen.add(cand)
            if cand in mine:                          # 正文在上面那区印过了
                rows.append("      " + marks.head(node, key=cand, now=now)
                            + "（正文见上面【这次的事】）")
                continue
            if len(got) >= max(int(cap), 0):
                rest += 1
                continue
            got.append(cand)
            rows.append(_episode_line(store, cand, now=now, body=body))
    if rest:
        rows.append(f"（还有 {rest} 条没印 —— 先照印出来的这几条写）")
    return rows, got


# ---------------------------------------------------------------------------
# 两趟各补一格: 「同类印证过的看法」(L1) / 「跟这条撞上的现有看法」(L2)
# ---------------------------------------------------------------------------

#: 【她认过的同类印证过的看法】最多印几条**看法**（超了明说还有几条没印）。
#: 量级同 `DIGEST_L2_AKIN`: 都只是"摆几条看得见的", ⛔ 不是闸。
DIGEST_L1_AKIN_BELIEFS = 5
#: 【跟这条撞上的现有看法】最多印几条（同上; 真机 `m0022` 一条就撞 3 条 ⇒ 这个额度会用到）。
DIGEST_L2_COLLIDE = 5


def _key_title(store, nid: str) -> str:
    """`m0004《和老师的第一顿高级料理》` —— **钥匙 + 标题**（重复引用只留这几个字）。

    ⚠️ 书名号走 `marks.name`（那四个字符是唯一实现处, 守门扫代码字面量）。
    没标题 ⇒ 只给钥匙（⛔ 不编）。
    """
    node = store.get(str(nid))
    title = str(getattr(node, "title", "") or "").strip() if node is not None else ""
    return f"{nid}{marks.name(title)}" if title else str(nid)


def akin_supported_beliefs_block(store: WikiStoreV2, episode_ids: list[str],
                                 local_of: dict[str, str]) -> str:
    """L1 的第七段【她认过的同类印证过的看法】（零 LLM）—— 补的是 L1 唯一缺的那一刀。

    她今天看得见**候选旧经历**, 却看不见"**那条旧经历当年印证过哪条看法**" ⇒
    "挂证据"（`supports`）只能靠猜。这一段把那两步接起来:

        本段经历 ——(`akin`)——> 同类旧经历 ——(`supports`)——> 已有看法

    ⚠️ **方向**: `supports` 是"经历 → 看法" ⇒ 经历那一头查 `targets`（**出边**）。
    写成 `sources` 就**恒空且不报错**（经历永远不是被支撑的那一头 —— 坑 4.34 的第四次
    就是这么来的, 而它已经在交接文档里骗过一次人）。

    ⚠️ **按看法归并**（用户 2026-10-14 裁）: 同一看法被好几条同类印证过 ⇒ **一行**,
    右边只印那些经历的**钥匙 + 标题**（⛔ 不重复正文 —— 一份料里同一段正文只印一次,
    而且重复的信息只留关键的那几个字）。

    ⚠️ **看见就得能引用**: 看法若没进【现有认知】（cap 之外）⇒ 印全行**并给它发一个本地号**
    （并进调用方那份 `local_of`）—— 否则"看见了却写不了"（写了对不上名单 ⇒ **整包拒**）。

    空 ⇒ `""`（`_join_sections` 跳过空块 ⇒ **整段不印**, 与她视图里"没有钥匙就不印空手"同一条纪律）。
    """
    from core.brain.graph import REL_SUPPORTS
    from core.brain.read.render import render_cognition_line

    graph = store.graph()
    grouped: dict[str, list[str]] = {}            # 看法 id → 印证过它的同类经历（保序去重）
    for m in episode_ids:
        for cand in store.related(str(m), REL_AKIN):
            node = store.get(cand)
            if node is None or str(node.kind) != "episode":
                continue
            for b in graph.targets(cand, REL_SUPPORTS):
                bn = store.get(b)
                if bn is None or str(bn.kind) != "belief":
                    continue
                seen = grouped.setdefault(b, [])
                if cand not in seen:
                    seen.append(cand)
    if not grouped:
        return ""
    rows = ["（← 后面那几条是**认过跟本段经历像**的旧经历 —— ⚠️ 同类 ≠ 印证:"
            " 这一条经历到底印证没印证那条看法, 由你判）"]
    for b, eps in list(grouped.items())[:DIGEST_L1_AKIN_BELIEFS]:
        node_b = store.get(b)
        if node_b is None:                       # 上一圈筛过; 图变了就当没有（不编）
            continue
        keys = " · ".join(_key_title(store, e) for e in eps)
        local = local_of.get(b)
        if local:
            rows.append(f"{local} ← {keys}")
            continue
        local = f"u{len(local_of) + 1:04d}"       # 没印过 ⇒ 发一个本地号（并进引用面）
        local_of[b] = local
        rows.extend(render_cognition_line(store, node_b, graph, local_of, max_body=60))
        rows.append(f"    ← {keys}")
    rest = len(grouped) - DIGEST_L1_AKIN_BELIEFS
    if rest > 0:
        rows.append(f"（还有 {rest} 条没印 —— 先照印出来的这几条判）")
    return "\n".join(rows)


def collided_beliefs_block(store: WikiStoreV2, evidence_ids: list[str],
                           local_of: dict[str, str]) -> str:
    """L2 的第五段【跟这条撞上的现有看法】（零 LLM）—— 治"同一个结论写第二条"。

    **判据**: `本段证据集 ∩ 那条看法的 supporters`（**共同证据优先**）——
    同一条经历支撑过它 ⇒ 她这次很可能要说的就是同一件事。
    排序: **交集条数降序**, 其次**被引数降序**, 再 id。

    ⏸ **语义那一路**（`like(spec="digest")` 对看法面）暂缺: 那一刻她**还没写出**新看法的正文,
    query 只能拿本段经历正文顶; 而没有 embedder 时 `like` 也只退化成词面 ⇒ 等 `[embed]`
    在位时再补, 那时它印的是 `相近 0.58（为什么: …）`（**弱**那一档, 与 `同一条证据` 分开写）。

    ⚠️ **看见就得能引用**: 没进【现有认知】的看法 ⇒ 印全行 + 发本地号（并进 `local_of`）。
    ⚠️ **面只在"有信息"时印**（用户 2026-10-14 裁）: 没写 `entity` 的看法按 `DEFAULT_FACES`
    算成**她自己** —— 那是绝大多数 ⇒ 每行都写"关于我"是纯噪声。所以:
      · ⛔ **她自己那一条不印**（明确写了 `x0000` 与"没写"在这件事上是同一句话）;
      · 其余的面最多印两个（`关于「老师」「杂草屋」`）—— 面是次要信息, 别把行撑长。
    ⚠️ 撞在哪的**强弱分开写**: `同一条证据 …`（强）与 `相近 …`（弱）⛔ 不混在一格里读。
    """
    from core.brain.entities import SELF_ID
    from core.brain.graph import REL_ABOUT
    from core.brain.read.render import render_cognition_line

    graph = store.graph()
    pool = {str(x) for x in evidence_ids}
    hits: list[tuple[int, int, str, list[str]]] = []
    for n in store.all():
        if str(n.kind) != "belief":
            continue
        shared = [e for e in graph.supporters(n.id) if str(e) in pool]
        if shared:
            hits.append((len(shared), len(graph.supporters(n.id)), n.id, shared))
    if not hits:
        return ""
    hits.sort(key=lambda t: (-t[0], -t[1], t[2]))
    rows: list[str] = []
    for _n_shared, _n_all, bid, shared in hits[:DIGEST_L2_COLLIDE]:
        node = store.get(bid)
        if node is None:                          # 与上面同理: 取不到就不印, 不编
            continue
        names: list[str] = []
        for x in graph.targets(bid, REL_ABOUT):
            if str(x) == SELF_ID:                     # ⛔ 她自己那一条不印（零信息）
                continue
            end = store.get(x)
            label = str(getattr(end, "name", "") or "").strip() if end is not None else ""
            if label and label not in names:
                names.append(label)
        face = " · 关于「" + "」「".join(names[:2]) + "」" if names else ""
        where = "撞在哪: 同一条证据 " + "、".join(shared) + face
        local = local_of.get(bid)
        if local:
            rows.append(f"{local}（正文见上）· {where}")
            continue
        local = f"u{len(local_of) + 1:04d}"
        local_of[bid] = local
        rows.extend(render_cognition_line(store, node, graph, local_of, max_body=60))
        rows.append(f"    ↳ {where}")
    rest = len(hits) - DIGEST_L2_COLLIDE
    if rest > 0:
        rows.append(f"（还有 {rest} 条没印 —— 只照印出来的这几条判）")
    return "\n".join(rows)


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


def _episode_line(store, nid: str, *, now="", body: int = 120, extra=()) -> str:
    """一条经历的行 = **信息头 + 截断正文**（与 L1 的候选行**同一个印法**）。

    `extra` 追加在信息头里（读者自己的字段 —— L1 的候选行用 `候选 0.46`）。
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


# ---------------------------------------------------------------------------
# R2 / R3 的料
# ---------------------------------------------------------------------------

def _node_texts(store: WikiStoreV2, ids: list[str]) -> list[str]:
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


def _round_b_material(store: WikiStoreV2, episode_ids: list[str],
                      local_of: dict[str, str],
                      embed_fn: EmbedFn | None,
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
    from core.brain.read.recall import CAND_K, _thr, recommend_candidates
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
        # 头由 `marks.head` 出（**唯一实现**）—— `〔m0025｜《今天的杂草屋》〕正文`。
        # 编号是**钥匙**（L1 的 `relations` 用它指 episode, 真实 id）；
        # 书名号里是**gist**（正文被截到 120 字, 8~16 字的名字是"这是哪件事"的压缩）。
        # ⏸ `轴 …` 那一格 2026-10-14 随 `topics` 退役撤掉（用户裁 C1）。
        lines.append(f"{marks.head(node, key=node.id)}{head}")
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
