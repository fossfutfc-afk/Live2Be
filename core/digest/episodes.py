"""episodes.py — **把 R1 的条目落成节点**（2026-09-29 从 `pipeline.py` 拆出）。

L1 的**引擎侧**（零 LLM）: 条目 → `episode` 节点，并把"召回侧才用"的字段
一次物化好:

| 函数 | 干什么 |
|---|---|
| `_create_a_nodes` | 字段归属（引擎定，防幻觉）+ 去重（崩溃窗口重跑幂等） |
| `_node_ts` | 一条节点的时刻 = **它自己指向的事件里最后一条**（不是段 ts） |
| `_resolve_verbatim` / `_text_at` | 记录行号 → **逐字原文**（索引是唯一通道；解析不出就留空） |
| `_emotion_shape` / `_place_shape` / `_place_raw` | 板指针 → 情绪键/地点键/writer 原文序列（🚫 **绝不进 LLM 上下文**） |
"""
from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any

from core.brain.address import unique_title
from core.brain.nodes import make_node
from core.brain.revise import link_entity_refs
from core.digest.segment import _seqs_of

if TYPE_CHECKING:                       # 仅注解求值期
    from core.brain.store import WikiStoreV2

logger = logging.getLogger(__name__)


def _node_ts(seqs: Any, by_seq: dict | None, default: str) -> str:
    """一条节点的时刻 = **它自己指向的那些事件里最后一条**的 ts（取不到 → 传进来的段 ts）。

    ⭐ 2026-09-25（链路 ④-①）: 从前**整段一个 ts** —— 那批记忆共享同一天, 读不出先后。
    取"最后一条"的理由与"段 ts = 段内最后一条内容事件"**同源**: 那一刻才是这条记忆
    "到这儿为止"的样子。

    ⚠️ **只改第 1 轮产的节点**（episode / 玩家画像）: 它们手里有 LLM 指的**真事件指针**。
    第 2/4 轮产的节点（信念 / 承诺）指针本来就是段级的 `[interact_max]`, 且"她什么时候
    想明白的 = 消化那一刻"语义没错 ⇒ 继续用段 ts。
    ⚠️ **真机实测: 羁绊章内的跨度只有分钟级**（haruka 那批 75 条事件跨 12 分钟）⇒
    「（3 周前）」这类短语**不会变**（按日历日算）; 这条改动的收益在
    **① 批内排序**（从 id 序 → 真实时刻序）**② MMT 段**（一次消化覆盖 25 轮、可能横跨几天,
    从前全部被标成"最后那条消息那一天"）。
    """
    best, best_seq = "", -1
    for s in seqs or []:
        try:
            seq = int(s)
        except (TypeError, ValueError):
            continue
        ev = (by_seq or {}).get(seq)
        t = str(getattr(ev, "ts", "") or "").strip() if ev is not None else ""
        if t and seq >= best_seq:
            best, best_seq = t, seq
    return best or default


def _create_a_nodes(store: WikiStoreV2, entries: list[dict], *, ts: str,
                    event_seq: list[int],
                    aff_at_encoding: float | None = None,
                    by_seq: dict | None = None,
                    reused_out: list[str] | None = None,
                    strangers_out: list[str] | None = None
                    ) -> list[str]:
    """Round A 条目 → 节点（引擎字段归属——确定性归引擎, 防幻觉）。

    今天条目**只有一种**: `kind=episode`（缺键 = episode）→ episode 节点。
    ⏸ **`kind=profile`（玩家画像）那一支 2026-10-14 删** —— 先停产（2026-10-12,
    用户裁 *"`entity.text` 取代了它的定位"*）、再删格式（整个 kind 退役, 见 `nodes.KINDS`）;
    真机 9 个 jsonl 零个 profile 节点 ⇒ 无老档依赖。⚠️ **这一支必须删干净, 不能只停产**:
    `make_node("profile", …)` 今天会**静默降级成 episode**（`from_dict` 认不出 kind 时的
    兜底）⇒ 留着一个"照条目建节点"的分支等于埋一条"画像被写成经历"的路。
    上游（`parse_round_a`）仍**认得** `kind=profile` ⇒ 丢行 + 记账, ⛔ 不判非法。
    dedupe: (kind, event_seq, 主文本) 命中已有节点 → 复用 id（崩溃窗口重跑防双写）。

    event_seq（T14, 2026-09-15）: **条目自带就用条目自带的**（Round A 抄的行号,
    已在 parse 层校验 ⊆ 本段）, 否则回落到段级 `[interact_max]`。
    ⭐ **N3（2026-09-29）后, "条目自带的"是引擎展开好的区间** —— 而 3b-1 起展开的结果
    存在 **`seqs`**（`span` 留着当身份, 见 `segment._expand_spans`）⇒ 本函数两种键名
    都认（`segment._seqs_of`, **唯一取法**）。形状与字段名（`node.event_seq`）没变,
    变的只是它的来源: 从"她挑的点"→"引擎算的区间"。
    旧版**无条件覆写**成 `[interact_max]`——实测 mutsuki 全段 `[60]` 而板最大 55,
    它指向一条 MMT 消息、不指向任何一板, 于是板指针从来没存在过,
    而 `migrate_time` 的唯一排序信号也一起死掉（全部节点同键 → 退化成插入序）。

    aff_at_encoding（§3.3.3, 2026-09-13）: 本段**开始之前**的好感标量
    （`Affection.to_scalar()`, [−1,1]）——快照, 写入后永不改。
    调用方传 None = 未采集（旧档/CLI 路径）→ 字段不落库, 与 `0.0`（中性）区分。

    ⭐ D1（2026-09-22）:
      · ~~`items`（§3.1 物品台账）随条目自动落库~~ —— **2026-09-29 字段退役**（零活读者;
        物品面将来走 `inventory` 旁路）。
      · ~~`about_hint`（§8.2 归属线索）必须在这里摘掉~~ —— **2026-09-29 字段退役**:
        它和 R3 的"挂谁"**判两次**（还可能不一致）, 而 R3 本来就拿得到全量候选表 +
        新节点正文 ⇒ 引擎不必替它预判一个名字。

    Returns: `episode_ids`——供 B 覆盖检查。
    """
    from core.brain.revise import _find_duplicate
    episode_ids: list[str] = []
    for ent in entries:
        node = make_node("episode", **{k: v for k, v in ent.items() if k != "kind"})
        # ⭐ **N2b**: 标题唯一性**写入时强制**（冲突加数字; 只增不重排）——
        # 解析与写入都在 `address.py` 里（那边是"谁能被指到"的唯一约定）。
        node.title = unique_title(store, node.title)
        node.event_seq = list(_seqs_of(ent) or event_seq)
        node.ts = _node_ts(node.event_seq, by_seq, ts)       # ⭐ 自己的时刻（④-①）
        # 板级情绪键序列（T15）——召回侧物化, **不进 LLM 上下文**
        if by_seq is not None:
            node.emo_shape = _emotion_shape(node.event_seq, by_seq)
            # 地点键序列（M3, 2026-09-19）——同一手物化, 同一纪律
            node.place = _place_shape(node.event_seq, by_seq)
            # 叙事轴: writer 原文（键不是地名的双射, 判"同地"只能靠语义）
            node.place_raw = _place_raw(node.event_seq, by_seq)
        node.aff_at_encoding = aff_at_encoding
        dup = _find_duplicate(store, node)
        if dup is not None:
            if reused_out is not None:
                reused_out.append(dup.id)         # ⭐ D1: 这一条**没建节点**（复用旧的）
            episode_ids.append(dup.id)
            continue
        nid = store.add(node)
        episode_ids.append(nid)
        _t, _strangers = link_entity_refs(store, nid, ts=node.ts)
        if strangers_out is not None:
            strangers_out.extend(_strangers)
    return episode_ids


def _spanless_nodes(store: WikiStoreV2, segments: list[dict], *, note_state, now_ts: str,
                    interact_max: int, reused_out: list[str] | None = None) -> list[str]:
    """⭐ **无区间那一行 ⇒ 一条"没有那一刻"的经历**（L7, 2026-10-05）—— §2.3 / §4.3。

    R0 的行 `{span: null, state: "close", id: n?}` 说的是 *"我答应过/等过, 而那一刻
    根本没发生"*（"生日那天, 老师没有来"）—— 它**没有事件可写**, 正文**就是那一行的
    `abstract`**, 所以它**不经 R1**, 在这里直接落节点。

    | 字段 | 值 | 为什么 |
    |---|---|---|
    | `text` | 那一行的 `abstract` | 它就是那条回忆的正文（契约按正文的上限量它, 不是 60） |
    | `title` / `significance` | 那一行给的 | R1 看不到这一行 ⇒ 只能 R0 给（"值不值"必须有人拍） |
    | `ts` | **哪一天**（那条约定的期限日） | 记忆属于那天, 不属于"消化那一刻" |
    | `event_seq` | `[interact_max]` | ⚠️ **账的指针, 不是覆盖声明** —— 见下 |
    | `verbatim` | 空 | 没有事件, **绝不编** |

    ⚠️ **`event_seq` 为什么不能空**（`revise._find_duplicate` 的第一行就是"空 ⇒ 不比"）:
    崩溃窗口重跑时, 没有位置就没有去重键 ⇒ **每重跑一次图上就多一条**"生日那天没人来"。
    ⇒ 落段级指针（R2/R3 的既有先例: 记忆属那天, 账记本段）。

    ⛔ **那个指针不许拿去推水位**: 它是"账记在本段", 不是"这段被覆盖了" ——
    `pipeline._next_watermark` 读的正是 `node.event_seq`, 不排除它就会把**欠着的尾巴**
    一起推过水位（尾巴从此不再重喂）。⇒ 这些 id 由调用方记进 `result.spanless_ids`。
    """
    from core.brain.revise import _find_duplicate
    spanless: list[str] = []
    for seg in segments:
        if seg.get("span") is not None or seg.get("state") != "close":
            continue
        text = str(seg.get("abstract") or "").strip()
        if not text:
            continue
        nid = str(seg.get("id") or "").strip()
        node = make_node("episode", text=text,
                         title=str(seg.get("title") or "").strip() or unique_title(
                             store, text[:12]),
                         significance=seg.get("significance", 0.5))
        node.title = unique_title(store, node.title)
        node.event_seq = [int(interact_max)]
        node.ts = _due_moment(note_state, nid, now_ts)
        dup = _find_duplicate(store, node)
        if dup is not None:
            if reused_out is not None:
                reused_out.append(dup.id)
            spanless.append(dup.id)
            continue
        spanless.append(store.add(node))
    return spanless


def _due_moment(note_state, item_id: str, now_ts: str) -> str:
    """那条约定的**期限日** → 一个带时刻的时间戳（取不到 ⇒ 段末尾那个时刻）。

    ⚠️ **时刻与偏移从 `now_ts` 借**（`2026-10-05T21:33:00+08:00` 的 `T21:33:00+08:00` 那半截）:
    节点的 `ts` 是 **aware** 时间戳, 而 `due` 是裸日期 —— 直接拿裸日期当 `ts`,
    后面 `age_days`（aware − naive）会当场 TypeError（P1 那个坑, 已踩过）。
    语义上也没错: 那一天 + 她那阵子的作息。
    """
    item = next((it for it in getattr(note_state, "pinned", []) or []
                 if str(getattr(it, "id", "")) == item_id), None)
    due = str(getattr(item, "due", "") or "").strip() if item is not None else ""
    try:
        date.fromisoformat(due)
    except ValueError:
        return now_ts
    return f"{due}{now_ts[10:]}" if len(now_ts) > 10 else due


def _resolve_verbatim(ent: dict, by_seq: dict) -> None:
    """`verbatim_seq`（记录行号）→ `verbatim`（逐字原文）——**索引是唯一来源**。

    ```
    LLM 只给行号  → 引擎解析出原文回填     ← 唯一的通道, 逐字且永久可重解析
    行号解析不出  → 留空（**绝不编**）      ← 宁缺勿错; 行号本身留在 `verbatim_seq` 里
    ```

    ## ⏸ 文本通道与"文本优先" **2026-09-29 退役**

    从前 LLM 也可以直接抄一句原话（`"verbatim": "…"` 字符串）, 且**两条都给时文本优先**
    —— 那是个**安全决定**: 用户把"错索引不可见"放进待办了, 而错的索引会解析出一句真文本、
    看起来完全正常, 错的原话至少一眼看得出不对。

    退役的理由: 两条通道说的是**同一件事**, 而正文里的原话本来就
    逐字躺在 append-only 的事件流里 —— 让模型再抄一遍, 等于给"静默换掉一句正确原话"
    开了一个口子, 换来的只是"抄得对"这一种情况下的冗余保险。今天行号是唯一入口,
    解析不出就**留空**: 宁可这条记忆没有原话, 也不放一句无法溯源的引文进去。
    """
    seqs = ent.get("verbatim_seq") or []
    if not seqs:
        return                                   # 无行号 → 留空
    from contract.timeline_index import parse_index
    picked: list[str] = []
    for idx in seqs:
        got = parse_index(idx)
        if got is None:
            continue
        ev = by_seq.get(got[0])
        if ev is None:
            continue
        text = _text_at(ev, got[1])
        if text:
            picked.append(text)
    if picked:
        # 多条关键句拼一行（`" / "` 与时间线的记录分隔同形）——`render.py` 的
        # `（「{verbatim}」）` 是单行渲染, 换行符会把视图打断。
        ent["verbatim"] = " / ".join(picked)


def _text_at(ev, rec) -> str:
    """事件 + 记录位 → 那一条记录的**逐字原文**（取不到 → `""`, 绝不编）。"""
    from contract.timeline_index import REC_PICKED
    if rec == REC_PICKED:
        pk = ev.payload.get("picked")
        return pk.strip() if isinstance(pk, str) else ""
    if ev.type == "mmt":
        key = {0: "player", 1: "reply"}.get(rec)
        v = ev.payload.get(key) if key else None
        return v.strip() if isinstance(v, str) and v.strip() else ""
    paras = ev.payload.get("paragraphs")
    if not isinstance(paras, list) or not isinstance(rec, int):
        return ""
    if not (0 <= rec < len(paras)):
        return ""
    p = paras[rec]
    t = p.get("text", "") if isinstance(p, dict) else str(p)
    return t.strip() if isinstance(t, str) else ""


def _emotion_shape(seqs: list, by_seq: dict) -> list[str]:
    """板指针 → **板级情绪键序列**（按 seq 序拼接; 取不到 → `[]`, 绝不编）。

    只收 bond 事件: 情绪键由**标注层**产出（每条记录一个键）, MMT 事件没有键。
    空键（`""`/None）跳过——标注失败与"真的无表情"在数据里不可分,
    所以只把**有值的键**按顺序连起来（保持弧的形状, 不补位）。

    🚫 返回值只进 `node.emo_shape`（召回侧）——**绝不进 LLM 上下文**。
    """
    out: list[str] = []
    for seq in sorted(seqs or []):
        ev = by_seq.get(seq)
        if ev is None or ev.type != "bond":
            continue
        paras = ev.payload.get("paragraphs")
        if not isinstance(paras, list):
            continue
        for p in paras:
            k = p.get("emotion") if isinstance(p, dict) else None
            if isinstance(k, str) and k.strip():
                out.append(k.strip())
    return out


def _place_shape(seqs: list, by_seq: dict) -> list[str]:
    """板指针 → **地点键序列**（M3, 2026-09-19）; 取不到 → `[]`, 绝不编。

    与 `_emotion_shape` 同一手（`digest` 按 `event_seq` 从真源物化，
    因为 `Channel.gather` 只拿得到节点、翻不了板）:

    * 每板取 `payload.place`（板首 `switch` 解出的**键**）
    * 再取 `payload.paragraphs[*].place`（句级锚点, 板内后续换场）
    * **相邻去重保序** —— 结果 = "这段去过哪些地方"的变化序列;
      同地反复去会留下多个元素（`school_rooftop, classroom, school_rooftop`）

    只收 bond 事件: 地点键由**标注层**产出, MMT 事件没有键。空键跳过
    （标注失败与"这段没换场"在数据里不可分, 不补位——同 `emo_shape` 的取舍）。

    ⚠️ **带的是键不是 writer 本名**（用户 2026-09-19 的疑问）:
    C 链路比的是相等, 而「放学后的教室」/「教室里」/「回到教室」是同一张图、
    三个字符串 —— 本名做等值分组是废的。本名留在事件流里
    （`payload.place_hint` + 锚点句原文）, `event_seq` 指得到, 要重解析时回捞即可。

    🚫 返回值只进 `node.place`（召回侧）——**绝不进 LLM 上下文**。
    """
    out: list[str] = []
    for seq in sorted(seqs or []):
        ev = by_seq.get(seq)
        if ev is None or ev.type != "bond":
            continue
        keys: list[str] = []
        board = ev.payload.get("place")
        if isinstance(board, str) and board.strip():
            keys.append(board.strip())
        paras = ev.payload.get("paragraphs")
        if isinstance(paras, list):
            for p in paras:
                k = p.get("place") if isinstance(p, dict) else None
                if isinstance(k, str) and k.strip():
                    keys.append(k.strip())
        for k in keys:
            if not out or out[-1] != k:              # 相邻去重（保留"再次到访"）
                out.append(k)
    return out


def _place_raw(seqs: list, by_seq: dict) -> list[str]:
    """板指针 → **writer 原文序列**（叙事轴, 2026-09-19 用户指出后补落）。

    取每板的 `payload.place_hint` —— **writer 自己写的那个名词短语**
    （「放学后的教室」「傍晚的学校天台」），相邻去重保序。

    为什么必须有它: 键**不是地名的双射**（一键多义 / 一地多键），所以判"**同地**"
    只能靠语义, 而语义的输入就是原话 —— 见 `nodes.BrainNode.place_raw` 的两轴表。

    ⚠️ 句级锚点的原文**不在这里**（锚点只存 `{sentence, place}`）——那条句子的
    原文在 `payload.paragraphs[i].text`，与 `verbatim_seq` 同一手:
    地址永久有效，要用时按 `event_seq` 回捞。

    🚫 只进 `node.place_raw`（召回侧）——**绝不进 LLM 上下文**。
    """
    out: list[str] = []
    for seq in sorted(seqs or []):
        ev = by_seq.get(seq)
        if ev is None or ev.type != "bond":
            continue
        hint = ev.payload.get("place_hint")
        if isinstance(hint, str) and hint.strip():
            h = hint.strip()
            if not out or out[-1] != h:
                out.append(h)
    return out
