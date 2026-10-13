"""digest 的**结构校验** —— 七个相位的文档形状不同, 所以有七个入口。

七个入口都**一处 `self` 都不用**（原先只是碰巧写成方法, 1b-2a 搬成模块级函数）——
调用点仍走 `DigestRegistry` 上的同名**薄委托**。

取值 / 上限读 `contract.digest/tables.py`, 文档形状（字段块 / 语义 / 范例）读
`contract/digest/docs.py` —— **本模块不定义任何契约文案**: 渲染与校验读的是同一份。

⚠️ `is_full_date` 住在 `digest_tables`（不在本模块）: 它既被 `parse_group` 用, 也被
`core/digest/material.py` 从外部导入 —— 它是「日期**取值**语义」而不是校验逻辑。
"""
from __future__ import annotations

from typing import Any

from contract.digest.docs import RELATION_ACTIONS
from contract.digest.tables import (
    ABSTRACT_MAX,
    ABSTRACT_MAX_FREEFORM,
    COGNIZE_ANCHORS,
    COGNIZE_KEYS,
    COGNIZE_RETIRED,
    ENTITY_NAME_MAX,
    ENTITY_REFS_MAX,
    ENTITY_TAG_PREFIX,
    ENTITY_TEXT_MAX,
    GROUP_TITLE_MAX,
    MAX_ALIASES,
    MAX_COGNITIONS,
    MAX_EPISODES,
    MAX_SEGMENTS,
    MAX_TAGS,
    MAX_TEXT,
    RELATION_ANCHORS,
    STATE_VALUES,
    TOPICS_MAX,
    is_full_date,
)
from contract.model import ValidationResult


def parse_round_a(raw: Any, *, seq_set: set[int] | None = None
                  ) -> tuple[list[dict], ValidationResult]:
    """Round A: `{"episodes": [...]}` → 规范化条目列表。

    `seq_set`（T14）: 本段**事件 seq 全集**——`event_seq` / `verbatim` 索引
    的 ⊆ 校验基准（与 `parse_round_b` 的 `episode_ids` 同思路:
    引用纪律在 parse 层, 不在 prompt 层）。`None` = 不校验（老调用方/单测）。

    ⛔ ~~`on_mind_out`~~ **2026-09-29（N4e）随 `on_mind` 槽退役** ——
    它从前是这个 parse 的第二个产物（用列表传出而不改返回签名的手法）。
    """
    errors: list[str] = []
    warnings: list[str] = []
    #: ⭐ D1（2026-09-29）: "真的丢了东西"的那几条 warning（见 `ValidationResult.drops`）
    drops: list[str] = []
    if not isinstance(raw, dict):
        return [], ValidationResult(errors=("Round A 输出必须是 JSON 对象",))
    raw_eps = raw.get("episodes")
    if not isinstance(raw_eps, list):
        return [], ValidationResult(errors=("episodes 必须是数组",))
    if len(raw_eps) > MAX_EPISODES:
        errors.append(f"episodes 超过 {MAX_EPISODES} 条（超出的丢弃）")
        raw_eps = raw_eps[:MAX_EPISODES]
    out: list[dict] = []
    for i, e in enumerate(raw_eps):
        # ⭐ **`drop`**（3b-2, 2026-09-29）: 她对**这一条切片**说"不记"。
        # 只有一种合法用途: 那条切片压根没什么可记的（纯寒暄 / 无实质进展）。
        # ⚠️ "骨架里带 ⭐ 的不许 drop" 是**提示词纪律**, 引擎侧不做硬拦 ——
        # 引擎不知道哪条带 ⭐（那是 `keep` 的语义, 属于 R0 的产出）;
        # 真丢了约定由 3b-3 的缺口账兜（走已有的 `digest_gap` 通路）。
        if isinstance(e, dict) and e.get("drop") is True:
            out.append({"drop": True})
            continue
        item, item_errs, item_warns = _clean_episode(e, i, seq_set, drops)
        errors.extend(item_errs)
        warnings.extend(item_warns)
        if item is not None:
            out.append(item)
    return out, ValidationResult(tuple(errors), tuple(warnings), tuple(drops))

def parse_relations(raw: Any, *, episode_ids: set[str] | None = None,
                    target_ids: set[str] | None = None,
                    topics_of: dict[str, list[str]] | None = None,
                    kind_of: dict[str, str] | None = None,
                    ) -> tuple[list[dict], ValidationResult]:
    """⭐ **L1（判关系）**: `{"relations": [...]}` → 规范化的**边行**列表。

    一行 → `{"rel": …, "src": …, "dst": …, "on"?: …}`（内部形状, 由 `apply_relations` 落库）。

    ## 校验（⚠️ **分两档** —— 这是本函数最要紧的决定）

    | 情况 | 处置 |
    |---|---|
    | 行形状坏（锚点键 ≠ 1 个 / 关系键 ≠ 1 个 / 值不是字符串 / 未知键）| **丢这一行** + 记账 |
    | `id` **不在渲染列表里**（编造）| ⛔ **整包拒** —— 那说明她没在引用真实世界, 整包不可信 |
    | `akin` 缺 `on` / `on` 不在**两端 `topics` 的交集**里 | **丢这一行** + 记账（轴是**逐行**的性质, 一行坏不毁整段记忆）|
    | `akin` / `contradicts` 的**两端类型**不对（P2）| **丢这一行** —— `akin` 两端都得是经历; `contradicts` 得**同侧**（经历↔经历 或 非经历↔非经历）|
    | `evolved_from` 的两端**不是看法**（P7-2, 2026-10-08）| **丢这一行** —— 那是"看法 ↔ 看法"的边（经历没有进化可言）|

    ⚠️ `on` 的判据用**原样字符串**（大小写 / 标点都不归一）—— 归一就等于引擎在替她判
    "这两个词是一回事"。`topics_of` = `{节点 id: [topics]}`（料侧提供; 缺省 `None` =
    **不校验交集**, 只查 `on` 给没给）。

    ⚠️ `kind_of` = `{她能写的 id: kind}`（P2）—— 键必须与她看到的那一套 id 同空间
    （经历/对象是真实 id · 认知是本地号 `u0001`）。缺省 `None` = **不校验类型**
    （老调用方 / 单测）。
    """
    errors: list[str] = []
    warnings: list[str] = []
    drops: list[str] = []
    if not isinstance(raw, dict):
        return [], ValidationResult(errors=("L1 输出必须是 JSON 对象",))
    raw_rows = raw.get("relations")
    if not isinstance(raw_rows, list):
        return [], ValidationResult(errors=("relations 必须是数组",))
    rel_names = {a.name for a in RELATION_ACTIONS}
    out: list[dict] = []
    for i, r in enumerate(raw_rows):
        if not isinstance(r, dict):
            drops.append(f"relations[{i}] 不是对象")
            continue
        anchors = [(k, v) for k, v in r.items() if k in RELATION_ANCHORS]
        rels = [(k, v) for k, v in r.items() if k in rel_names]
        if len(anchors) != 1 or len(rels) != 1:
            drops.append(f"relations[{i}] 形状坏（锚点键 {len(anchors)} 个 / 关系键 "
                         f"{len(rels)} 个）")
            continue
        (a_kind, aid), (rel, dst) = anchors[0], rels[0]
        if not isinstance(aid, str) or not aid.strip() or not isinstance(dst, str) or not dst.strip():
            drops.append(f"relations[{i}] 的 id 必须是字符串")
            continue
        aid, dst = aid.strip(), dst.strip()
        # ⛔ 编造 id ⇒ 整包拒（与今天的 `decisions` 同档）
        bad = ""
        if episode_ids is not None and target_ids is not None \
                and aid not in episode_ids and aid not in target_ids:
            bad = aid
        if not bad and target_ids is not None and dst not in target_ids:
            bad = dst
        if bad:
            errors.append(f"relations[{i}] 引用了列表里没有的 id: {bad}（整包拒）")
            continue
        # ⭐ **两端类型**（P2）: 与 `on` 同一档（**丢这一行**）—— 判据是"这条边的
        # 语义对不对", 一行错不该毁整段。`akin` 只要经历; `contradicts` 要**同侧**
        # （经历↔经历 或 看法↔看法 —— 混着来的那条边没有语义）。
        if kind_of and rel in ("akin", "contradicts", "evolved_from"):
            ka, kb = kind_of.get(aid), kind_of.get(dst)
            if ka is not None and kb is not None:
                if rel == "akin" and (ka != "episode" or kb != "episode"):
                    drops.append(f"relations[{i}] akin 两端必须都是经历"
                                 f"（实得 {ka} ↔ {kb}）")
                    continue
                if rel == "contradicts" and (ka == "episode") != (kb == "episode"):
                    drops.append(f"relations[{i}] contradicts 两端必须同侧"
                                 f"（经历 ↔ 经历 或 看法 ↔ 看法; 实得 {ka} ↔ {kb}）")
                    continue
                # ⭐ 2026-10-08（P7 第 2 笔, 用户裁决）: `evolved_from` **只能**是
                # 看法 ↔ 看法（经历没有"进化" —— 经历是流水, 时间线自己会说清）
                if rel == "evolved_from" and (ka != "belief" or kb != "belief"):
                    drops.append(f"relations[{i}] evolved_from 两端必须都是**看法**"
                                 f"（实得 {ka} ↔ {kb}）")
                    continue
        row: dict = {"rel": rel, "src": aid, "dst": dst}
        on = r.get("on")
        if rel == "akin":
            if not isinstance(on, str) or not on.strip():
                drops.append(f"relations[{i}] akin 缺 on（轴必填）")
                continue
            on = on.strip()
            if topics_of is not None:
                a_topics = list(topics_of.get(aid) or [])
                b_topics = list(topics_of.get(dst) or [])
                common = [t for t in a_topics if t in b_topics]
                if on not in common:
                    drops.append(f"relations[{i}] on={on!r} 不在两端 topics 的交集里"
                                 f"（{aid} ∩ {dst} = {common or '空'}）")
                    continue
            row["on"] = on
        elif on is not None:
            warnings.append(f"relations[{i}] 写了 on（只有 akin 用它）—— 已忽略")
        out.append(row)
    return out, ValidationResult(tuple(errors), tuple(warnings), tuple(drops))

def parse_cognitions(raw: Any, *,
                     evidence_ids: set[str] | None = None,
                     cognition_ids: set[str] | None = None,
                     group_ids: set[str] | None = None,
                     kind_of: dict[str, str] | None = None,
                     ) -> tuple[list[dict], ValidationResult]:
    """⭐ **L2（`cognize`）**: `{"cognitions": [...]}` → 规范化的**造 / 写**行。

    一行 → `{"action": "belief", "text": …, ["subject"], ["significance"],`
           ` ["supports"], ["evolved_from"]}` —— **造**一条新看法
    ⏸ 从前还有第二种行 `{"action": "experience", "group": "g0001", "text": …}`
       （给已有的类**写沉淀**）—— **2026-10-13 随 `group` 退役停产**: 今天**丢这一行** + 记账
       （认得出、⛔ 不判非法; 判据与那一格见 `COGNIZE_RETIRED`）。

    ## 校验（**分两档**, 与 `parse_relations` 同一口径）

    | 情况 | 处置 |
    |---|---|
    | **停产的锚点**（`experience` 行, 没带活着的锚点）| **丢这一行** + 记账（`group` 退役 ⇒ 没有类可写; ⛔ 不判非法）|
    | 行形状坏（锚点键 ≠ 1 个 / 有未知键 / 锚点值不是对象）| **丢这一行** + 记账 |
    | 一行**同时**带活锚点与停产锚点 | **照收活的那个**, 停产那一半忽略（只告警 —— ⛔ 别为它丢整行）|
    | 造看法：**缺 `text`**（或全空白 / 超 `MAX_TEXT`）| **丢这一行** + 记账（⛔ 不截断: 截断是静默改内容）|
    | 造看法：**带 `id`**（想改已有的看法）| **丢这一行** + 记账（这一趟只**造**）|
    | 一行**既没 `supports` 也没 `evolved_from`** | **丢这一行** + 记账（没有立足点的看法不进图; ⛔ 光跟人打架不算）|
    | `contradicts` 的另一端**不是看法** | **丢这一行** + 记账（同 `evolved_from`）|
    | 造看法**超过 `MAX_COGNITIONS`** | **丢这一行** + 记账（超出的丢弃 —— 一段里造太多就是流水账）|
    | `evolved_from` 指到的**不是看法** | **丢这一行** + 记账（语义错: 一行坏不毁整段）|
    | id **不在发下去的名单里**（编造）| ⛔ **整包拒** —— 与 L1 同档: 那说明她没在引用真实世界 |

    ⚠️ **方向**（同 `parse_relations`）: 行里已经归一成"经历 → 新看法"（`supports`）
    与"新看法 → 旧看法"（`evolved_from`）—— 执行侧**不再判方向**。

    ⚠️ `kind_of` = `{她能写的认知 id: kind}`（只用来挡 `evolved_from` 指向 `profile`:
    画像不是"看法", 没有"进化"可言）。缺省 `None` = 不校验。
    ⚠️ **三个名单缺省 `None` = 不校验**（单测 / 老调用方）; 给了就必须全都对得上。
    ⚠️ `group_ids` 今天**恒是空集**（`group` 退役 ⇒ 那条边不再有人落, 名单没有写者）——
    参数留着, 供 `_clean_soak` 的直接调用方（停产不删机器）。
    ⚠️ 锚点对象**内部的**未知键**静默忽略**（同 `_clean_episode_item` 的口径）,
    只有 `id` 是例外（`belief` 那处显式丢行）。
    """
    errors: list[str] = []
    warnings: list[str] = []
    drops: list[str] = []
    if not isinstance(raw, dict):
        return [], ValidationResult(errors=("L2 输出必须是 JSON 对象",))
    raw_rows = raw.get("cognitions")
    if not isinstance(raw_rows, list):
        return [], ValidationResult(errors=("cognitions 必须是数组",))
    out: list[dict] = []
    soaked: set[str] = set()                       # 同一个类只收第一条沉淀
    n_belief = 0                                   # 造了几条看法（上限见 MAX_COGNITIONS）
    for i, r in enumerate(raw_rows):
        if not isinstance(r, dict):
            drops.append(f"cognitions[{i}] 不是对象")
            continue
        anchors = [(k, v) for k, v in r.items() if k in COGNIZE_ANCHORS]
        retired = sorted(k for k in r if k in COGNIZE_RETIRED)
        unknown = sorted(k for k in r if k not in COGNIZE_KEYS)
        if not anchors and retired:
            # ⏸ **停产 = 认得出 + 丢这一行**（B 案第三档; ⛔ **不判非法** —— 判非法 = 罚她
            # 重写整段, 而"多写一条我们不要的东西"不值那个价。判据见 `COGNIZE_RETIRED`）。
            # ⚠️ 它**必须排在下面那道"形状坏"之前**: 停产的键已经不在 `COGNIZE_ANCHORS` 里,
            # 掉到下面去只会得到一句"锚点键 0 个"—— 读不出"这是停产", 而它每段都可能出现。
            _drop(warnings, drops,
                  f"cognitions[{i}]: {retired[0]}（给已有的类写沉淀）已停产 —— 这一行丢")
            continue
        if len(anchors) != 1 or unknown:
            drops.append(f"cognitions[{i}] 形状坏（锚点键 {len(anchors)} 个"
                         + (f"; 未知键 {'、'.join(unknown)}" if unknown else "") + "）")
            continue
        if retired:
            # 混写（`{"belief": …, "experience": …}`）: **活着的那个锚点照收**, 停产的
            # 那一半忽略 —— ⛔ 别为它丢掉整行（那会白丢一条看法）。
            warnings.append(f"cognitions[{i}]: {retired[0]} 那一半已停产 —— 已忽略")
        kind, val = anchors[0]
        if not isinstance(val, dict):
            drops.append(f"cognitions[{i}] 的 {kind} 必须是对象")
            continue
        if kind == "belief":
            if n_belief >= MAX_COGNITIONS:
                drops.append(f"cognitions[{i}]: 一段最多造 {MAX_COGNITIONS} 条看法"
                             "（超出的丢弃）")
                continue
            item = _clean_belief(val, i, drops, warnings)
            if item is None:
                continue
            sup = _ref_list(r.get("supports"), f"cognitions[{i}].supports",
                            evidence_ids, errors, drops)
            evo = _ref_one(r.get("evolved_from"), f"cognitions[{i}].evolved_from",
                           cognition_ids, errors)
            con = _ref_list(r.get("contradicts"), f"cognitions[{i}].contradicts",
                            cognition_ids, errors, drops)
            if sup is None or evo is None or con is None:
                continue                           # 有错 ⇒ 整包拒（上面的 errors 说了）
            if not sup and not evo:
                drops.append(f"cognitions[{i}]: 这条看法**没有立足点**"
                             "（supports / evolved_from 至少给一个 —— "
                             "光跟人打架不构成一条看法）")
                continue
            if evo and kind_of and kind_of.get(evo) not in (None, "belief"):
                drops.append(f"cognitions[{i}]: evolved_from 只能指向**看法**"
                             f"（{evo} 是 {kind_of.get(evo)}）")
                continue
            bad_con = [c for c in con
                       if kind_of and kind_of.get(c) not in (None, "belief")]
            if bad_con:
                drops.append(f"cognitions[{i}]: contradicts 的另一端也得是**看法**"
                             f"（{'、'.join(bad_con)} 不是）")
                continue
            n_belief += 1
            if sup:
                item["supports"] = sup
            if evo:
                item["evolved_from"] = evo
            if con:
                item["contradicts"] = con
        else:
            item = _clean_soak(val, i, group_ids, errors, drops)
            if item is None:
                continue
            if item["group"] in soaked:
                drops.append(f"cognitions[{i}]: 类 {item['group']} 写了两次沉淀"
                             "（第一条为准）")
                continue
            soaked.add(item["group"])
        out.append(item)
    return out, ValidationResult(tuple(errors), tuple(warnings), tuple(drops))

def parse_split(raw: Any, *, seq_set: set[int] | None = None,
                note_ids: set[str] | None = None,
                overdue_ids: set[str] | None = None,
                ) -> tuple[list[dict], ValidationResult]:
    """R0 切分: `{"segments": [{"span", "abstract", "state"?, "id"?, "due"?}, …]}`。

    ⭐ **只做形状校验**（键在不在 / 区间合不合法 / 真值表配不配 / `id` 在不在名单里）——
    "这段区间里到底有什么"是**世界的事**, 归引擎（`seq_set` 只用来查端点存在性）。

    ## 一行的合法形状只有五种（`state` × `span` × `id`）

    | `state` | `span` | `id` | 含义 |
    |---|---|---|---|
    | 省略 | 必填 | 不许 | 与账无关的一件事（**绝大多数**） |
    | `open` | 必填 | 不许 | 新建: 到本段结束还开着的约定 |
    | `open` | 必填 | 必填 | 更正: 那条约定后来才知道日期（`due` / `abstract` 变） |
    | `close` | 必填 | 必填 | 这一行**了结**了名单里那条 |
    | `close` | **null** | 必填 | **没有那一刻**的了结（`abstract` 就是那条回忆的正文） |

    ## 坏行分两档（**别混**）

    · **收下但改写 + 告警**（内容不丢 ⇒ 不 `_drop`）:
      `state` 值不在词表（按"省略"收）· `close` 有 `span` 但 `id` 缺失/不在名单
      （降级成普通一行 —— 那一刻照样是记忆）· `open` 给了 `id` 但不在名单
      （同上; ⛔ **不新建**, 免得把同一条约定记两遍）· `due` 不是全日期（当没期限）。
    · **真的丢**（`_drop`, 进 D1 台账）: 沿用今天那些（端点不在时间线 / 起止反 /
      形状错 / `abstract` 缺或空 / 同 span + 同 abstract 的重复行）。
    · **没有区间那几行的坏形状**: 走 `warnings`（**不进 `drops`**）——
      `_drop` 的判据是"有没有内容离开过**库**", 而 `span: null` 的行本来就没有库内容
      （它是 R0 凭引擎的资格位写出来的一句）:
      `span: null` 却不是 `close` · `close` + `null` 但 `id` 缺失/不在名单 ·
      `close` + `null` 而**引擎没发资格位**（`overdue_ids` 里没有它）。

    Args:
        seq_set: 本段**可寻址事件 seq 全集**（端点 ⊆ 它）。`None` = 不校验。
        note_ids: 本轮料里印出来的**还开着的约定**编号（`id` 的闭集）。
            `None` = 不校验（老调用方 / 单测）。
        overdue_ids: 引擎判定的**超期**条目（= 允许 `span: null` 的资格位）。
            `None` = 不限制（老调用方 / 单测）。

    Returns: `(segments, ValidationResult)` —— 每条 = 引擎要的那一行:
    `{"span": [起, 止] | None, "abstract": "…", "state"?: …, "id"?: …, "due"?: …}`。
    ⚠️ 引擎随后把 `span` 展开成 `event_seq` 并**就地改写这批字典**（R1 在同一批
    字典上填正文）—— 所以这里**不 pop `span`**, 它是这一行的身份。
    """
    errors: list[str] = []
    warnings: list[str] = []
    #: ⭐ D1: "真的丢了东西"的那几条 warning（见 `ValidationResult.drops`）
    drops: list[str] = []
    if not isinstance(raw, dict):
        return [], ValidationResult(errors=("切分轮输出必须是 JSON 对象",))
    raw_segs = raw.get("segments")
    if not isinstance(raw_segs, list):
        return [], ValidationResult(errors=("segments 必须是数组",))
    if len(raw_segs) > MAX_SEGMENTS:
        warnings.append(f"segments 给了 {len(raw_segs)} 条（> {MAX_SEGMENTS}）——"
                        f"超出的丢弃; 一段里切成这么多件 = 流水账, 不是记忆")
        raw_segs = raw_segs[:MAX_SEGMENTS]

    out: list[dict] = []
    #: 同 span + 同 abstract 才算重复（⚠️ **同 span 不同行是合法的** —— 出+进两行,
    #: 或同一个时刻长出的两条记忆; 2026-10-05 起不再"完全一样就丢"）
    seen: set[tuple[int, int, str]] = set()
    for i, seg in enumerate(raw_segs):
        if not isinstance(seg, dict):
            errors.append(f"segments[{i}] 必须是对象")
            continue
        label = f"segments[{i}]"
        # ── 账目三键（后面的分档都靠它） ──
        state_raw = seg.get("state")
        if state_raw is None:
            state = ""
        elif isinstance(state_raw, str) and state_raw.strip() in STATE_VALUES:
            state = state_raw.strip()
        else:
            warnings.append(f"{label}.state 不是 {'/'.join(STATE_VALUES)} 之一"
                            f"（{state_raw!r}）——按「无账目」收下（这一行的内容不丢）")
            state = ""
        nid = str(seg.get("id") or "").strip()
        id_given = bool(nid)
        # ⚠️ 闭集：名单没给就不校验（老调用方 / 单测）; 给了就必须命中
        id_ok = id_given and (note_ids is None or nid in note_ids)

        # ── span：可以是 null —— **只对 close 合法** ──
        if seg.get("span") is None:
            if state != "close":
                warnings.append(f"{label} 的 span 是 null, 但它不是 close"
                                f"（没有那一刻、又没有账目 ⇒ 这一行什么都没留下）——丢弃")
                continue
            if not id_ok:
                warnings.append(f"{label} 是 close + span=null, 但 id {nid!r} "
                                f"不在【还开着的约定】名单里 —— 丢弃")
                continue
            if overdue_ids is not None and nid not in overdue_ids:
                warnings.append(f"{label} 是 close + span=null, 但引擎**没有**判定 "
                                f"{nid!r} 超期（资格位没发）—— 丢弃"
                                f"（凭空造一条「没发生过」的记忆不行）")
                continue
            span: list[int] | None = None
        else:
            # 区间 —— **复用 `_clean_span`**（端点存在性 / 起止反 / >2 端点 / 记录级编号
            # 那一整套规矩与 R1 逐字相同; 坏的那条它已经 `_drop` 过了）
            span = _clean_span(seg.get("span"), seq_set, label=f"{label}.span",
                               warnings=warnings, drops=drops)
            if span is None:
                continue

        abstract = seg.get("abstract")
        if not isinstance(abstract, str) or not abstract.strip():
            text = (f"{label} 缺 abstract —— 丢弃"
                    if span is not None else
                    f"{label}（close + span=null）缺 abstract —— 丢弃: "
                    f"那一行的 abstract **就是**那条回忆的正文, 没有它这一行什么都不剩")
            if span is not None:
                _drop(warnings, drops, text)
            else:
                warnings.append(text)
            continue
        abstract = abstract.strip()

        if span is not None:
            key = (span[0], span[1], abstract)
            if key in seen:
                _drop(warnings, drops,
                      f"{label} 与前面那条**完全一样**（同 span 同 abstract）——丢弃")
                continue
            seen.add(key)
            cap = ABSTRACT_MAX
        else:
            cap = ABSTRACT_MAX_FREEFORM          # 它就是那条回忆的正文
        if len(abstract) > cap:
            # 软上限: 收下但告警（它不是形状错 —— 超了只说明她写得长）
            warnings.append(f"{label}.abstract {len(abstract)} 字 > {cap}（收下但请写短）")

        # ── id 配不上: close / 更正都做不成 ⇒ 降级成普通一行（⛔ 不新建） ──
        # ⚠️ **`open` 且没给 id 是合法的**（新建）—— 只有"给了 id 却配不上"才降级。
        if (state == "close" and not id_ok) or \
                (state == "open" and id_given and not id_ok):
            what = "close" if state == "close" else "更正"
            warnings.append(f"{label} 想做「{what}」, 但 id {nid!r} 不在"
                            f"【还开着的约定】名单里 —— 这一行按「无账目」收下"
                            f"（那一刻照样记; ⛔ 不新建, 免得同一条约定记两遍）")
            state = ""

        row: dict = {"span": list(span) if span is not None else None,
                     "abstract": abstract}
        if state:
            row["state"] = state
            if id_given:
                # ⚠️ **新建的 `open` 不带 `id`**（缺键 = 新建; 只有"更正"才带）
                row["id"] = nid
        # ⭐ **无区间那一行还带 `title` + `significance`**（L7, 2026-10-05）——
        # 它没有事件、也不经过写正文的那一轮（R1 看不到它）⇒ 那条记忆的**标题**与
        # "值不值"只能由 R0 给（§1.1 真值表的"另外必填"列）。
        # ⚠️ 缺了**不拒**: 一条"没有那一刻"的记忆比一个没标题重得多 ⇒ 收下 + 告警,
        # 标题退回 `abstract` 前 12 字（⛔ 不编一个漂亮名字）。
        if span is None:
            title = str(seg.get("title") or "").strip()
            if not title:
                warnings.append(f"{label} 是无区间那一行, 但没给 `title` —— "
                                f"退回用 abstract 前 12 字（那条记忆在视图里就引不到）")
            row["title"] = title or abstract[:12]
            sig = seg.get("significance")
            if isinstance(sig, bool) or not isinstance(sig, (int, float)):
                if sig is not None:
                    warnings.append(f"{label}.significance 不是数字 —— 取 0.5")
                row["significance"] = 0.5
            else:
                row["significance"] = max(0.0, min(1.0, float(sig)))
        # `due` 只跟新建的 `open`: ⚠️ **判不了就退化成"没有期限"**（不告警 ——
        # 契约已经写明"全日期"; 引擎判不了 = 它永不过期, 宁缺勿错。
        # ⛔ 绝不替她滚到明年、也绝不替她猜）
        if state == "open" and seg.get("due") is not None:
            due = str(seg.get("due") or "").strip()
            if due and is_full_date(due):
                row["due"] = due
        out.append(row)

    if not out and raw_segs:
        warnings.append("这一包**一条切片都没留下**（全部被剔除）——"
                        "本段不会有任何记忆, 看上面的 `drops`")
    return out, ValidationResult(tuple(errors), tuple(warnings), tuple(drops))

def parse_group(raw: Any, *, block_ids: set[str]
                ) -> tuple[list[dict], ValidationResult]:
    """L2-a 分群（N7）: `{"attach": […], "new": […]}` → 归一化行。

    **只做形状 + 闭集校验**（键在不在 / 是不是数组 / 必填 / 块的把手来自本轮名单 /
    ⭐ **每个块恰好一次归属**）。"那个类名存不存在"是**世界校验** ⇒ 归执行器
    （`groups.apply_groups`）**剔掉 + 记账、不拒整包** —— 同 `parse_attribution` 的口径:
    形状错重试有用, "看错了世界"重试大概率还是错。

    ⚠️ **覆盖是硬错**（同 `parse_round_b` 的"必须覆盖全部 episode"）: 漏一个块 =
    那几件事白连了一次, 而"漏"正是"没按契约说话" —— 带反馈重试一次通常就好。
    （调用方还有一道安全网: 这一步整体失败**只回滚它自己**, 不连累整段 —— 见 `digest_segment`。）

    Returns: `(rows, ValidationResult)`; 行形状

        `{"action": "attach", "block": "b1", "group": "那片苔藓"}`
        `{"action": "new", "block": "b2", "title": "模型店的那些事"}`
        `{"action": "merge", "from": "苔藓的事", "into": "那片苔藓"}`
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(raw, dict):
        return [], ValidationResult(errors=("分群轮输出必须是 JSON 对象",))

    out: list[dict] = []
    seen: set[str] = set()
    for key in ("attach", "new"):
        if key not in raw:
            errors.append(f"缺键 {key!r}（两个键都要在, 没有就写空数组）")
            continue
        rows = raw.get(key)
        if not isinstance(rows, list):
            errors.append(f"{key} 必须是数组")
            continue
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"{key}[{i}] 必须是对象")
                continue
            block = row.get("block")
            if not isinstance(block, str) or not block.strip():
                errors.append(f"{key}[{i}] 缺 block（块的把手 b1…）")
                continue
            block = block.strip()
            if block not in block_ids:
                errors.append(f"{key}[{i}] 块 {block!r} 不在本轮名单里"
                              f"（只有 {', '.join(sorted(block_ids))}）")
                continue
            if block in seen:
                warnings.append(f"{key}[{i}] 块 {block!r} 重复（只留第一条）")
                continue
            if key == "attach":
                name = row.get("group")
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"attach[{i}] 缺 group（已有类的名字）")
                    continue
                seen.add(block)
                out.append({"action": "attach", "block": block,
                            "group": name.strip()})
                continue
            title = row.get("title")
            if not isinstance(title, str) or not title.strip():
                errors.append(f"new[{i}] 缺 title（这个类叫什么）")
                continue
            title = title.strip()
            if len(title) > GROUP_TITLE_MAX:
                warnings.append(f"new[{i}] 类名偏长（{len(title)} 字）: {title!r}")
            seen.add(block)
            out.append({"action": "new", "block": block, "title": title})

    missing = sorted(b for b in block_ids if b not in seen)
    if missing:
        errors.append("这些块没有归属: " + ", ".join(missing)
                      + "（每个块都要出现在 attach 或 new 里, 一个都不能漏）")

    # —— `merge`（N7b）: 两个类名 —— ⚠️ "这对名字在不在候选里" 是**世界校验**,
    # 归执行器（`groups.apply_merges`）: 名字解析要归一, 而契约层不依赖 core。
    if "merge" not in raw:
        errors.append("缺键 'merge'（三个键都要在, 没有就写空数组）")
    else:
        rows = raw.get("merge")
        if not isinstance(rows, list):
            errors.append("merge 必须是数组")
        else:
            used: set[str] = set()
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    errors.append(f"merge[{i}] 必须是对象")
                    continue
                src, dst = row.get("from"), row.get("into")
                if not _nonempty_str(src) or not _nonempty_str(dst):
                    errors.append(f"merge[{i}] 需要 from 与 into（两个类名）")
                    continue
                src, dst = str(src).strip(), str(dst).strip()
                if src == dst:
                    errors.append(f"merge[{i}] from 与 into 是同一个类名: {src!r}")
                    continue
                if src in used or dst in used:
                    errors.append(f"merge[{i}] 一个类一轮只能并一次: {src!r} / {dst!r}")
                    continue
                used.add(src)
                used.add(dst)
                out.append({"action": "merge", "from": src, "into": dst})
    return out, ValidationResult(tuple(errors), tuple(warnings))

def parse_attribution(raw: Any, *, known_names: set[str] | None = None,
                      object_ids: set[str] | None = None,
                      ) -> tuple[list[dict], ValidationResult]:
    """⭐ **settle「沉淀」**（2026-10-13 从"只认人"扩成两路）: `{"entities": [...]}` → **动作行**。

    ⭐ **`id` 决定这一行是"建"还是"改"**（项目自己的形状规则, `docs.py` 的规则④）:
      · **没有 `id`** → `{"action": "create", "name", "reason", ["aliases"], ["text"]}`
        —— 建一个新的长期对象（号由引擎发）;
      · **有 `id`** → `{"action": "update", "id", ["name"], ["text"]}`
        —— 改一个已经认识的对象（改名 ⇒ 旧叫法降级成别名; 写看法 ⇒ 覆盖 `text`）。

    ## 校验（**没有"整包拒"档** —— 只有顶层形状坏才拒, 见下）

    | 情况 | 处置 |
    |---|---|
    | 顶层不是对象 / `entities` 不是数组 | **整包拒**（形状坏）|
    | 行不是对象 | **丢这一行** + 记账 |
    | **改**: `id` 不在【这一段认下的对象】里（编造）| **丢这一行** + 记账 |
    | **改**: `name` 与 `text` **两个键都没出现** | **丢这一行** + 记账（这行没说改什么）|
    | **改**: `name` 超 `ENTITY_NAME_MAX` | **只丢这一格** + warning（`text` 照收）|
    | **建**: `name` 空 / 超 `ENTITY_NAME_MAX` / 已在 `known_names` 里 | **丢这一行** + 记账 |
    | **建**: `reason` 空 | **丢这一行** + 记账 |
    | `text` 超 `ENTITY_TEXT_MAX` | **收下 + 告警**（⭐ 软尺: 不截断、也不丢行）|
    | **任一格的值是空的**（`""` / 没写）| ⭐ **当"不改"**（⛔ 不是"清空"）—— 见下 |
    | `aliases` 不是数组 / 超 `MAX_ALIASES` | 忽略 / 截断 + warning（别名只是效率优化）|
    | **改**那一路写了 `reason` / `aliases` | warning（忽略, ⛔ 不丢行）|

    ⭐ **空值 = 明确的不改**（用户 2026-10-13 裁）: `{"id": "x0001", "text": ""}` 是
    "**这一格没话可说**", ⛔ **不是"把看法清空"** ⇒ 引擎什么都不做（`apply_stances` 那一侧
    只记一笔 `empty_skips`, ⛔ **不记 `drops`** —— 这里没有东西可丢）。
    ⇒ 判"这行到底改了什么"**只看键在不在, 不看值空不空**。

    ⚠️ **为什么这个相位没有"整包拒"档**（与 L1/L2 不同, 2026-10-13 用户裁）: L1/L2 的
    **一行不是一个独立事实**（一行关系 / 一条看法 + 它的证据 ⇒ 编一个 id 说明整包没在看
    真实世界）; 而这一趟的每行是**互相独立的对象操作**（建小玉 与 改老师 毫无关系）——
    一行坏了没必要连坐（整包拒还要白花一次反馈重试）。
    ⚠️ **`known_names` 只挡"已经存在的对象"**（防重复建）; ⭐ **不核"名字在不在
    【她写了、但库里还没有的名字】里"** —— 那份名单是引擎扫**本段新节点**数出来的,
    而"这一段让我想记住的人"完全可能**没标引用**（用户 2026-10-13 裁: *"那一种情况
    不应该是我们的新建吗"*）⇒ 名单是**提示**不是笼子; 引擎只拦**能判定**的
    （已在库里的名字 · 超长 · 空）。
    ⚠️ `object_ids` = 【这一段认下的对象】（`settle_objects_block` 的第二个返回值,
    **真身 id**）—— 编号只能照抄它。缺省 `None` = 不校验（单测 / 老调用方）。
    """
    known = {str(x).casefold() for x in (known_names or set())}
    errors: list[str] = []
    warnings: list[str] = []
    drops: list[str] = []
    if not isinstance(raw, dict):
        return [], ValidationResult(errors=("settle 输出必须是 JSON 对象",))
    rows = raw.get("entities")
    if not isinstance(rows, list):
        return [], ValidationResult(errors=("entities 必须是数组",))
    out: list[dict] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            _drop(warnings, drops, f"entities[{i}] 不是对象 —— 丢了")
            continue
        where = f"entities[{i}]"
        name = str(row.get("name", "") or "").strip()
        text = str(row.get("text", "") or "").strip()
        if text and len(text) > ENTITY_TEXT_MAX:          # ⭐ 软尺: 收下 + 告警
            warnings.append(f"{where}.text 超过 {ENTITY_TEXT_MAX} 字"
                            f"（收下 —— 但这一格每轮都注入, 长了要压）")
        # ── 有 id ⇒ 改 ──────────────────────────────────────────────
        eid = str(row.get("id", "") or "").strip()
        if eid:
            if object_ids is not None and eid not in object_ids:
                _drop(warnings, drops,
                      f"{where} 的 id={eid!r} 不在【这一段认下的对象】里 —— 丢了")
                continue
            # ⭐ **判"这行改了什么"只看键在不在, 不看值空不空**（用户 2026-10-13 裁:
            # 空值 = "这一格没话可说", ⛔ 不是"清空"）—— 所以空值**照样收下**,
            # 由执行层记一笔 `empty_skips` 后什么都不做。
            if "name" not in row and "text" not in row:
                _drop(warnings, drops, f"{where} 既没写 name 也没写 text —— 丢了"
                                       "（改的那一行总得说改哪一格）")
                continue
            item: dict = {"action": "update", "id": eid}
            if "name" in row:
                if not name:
                    item["name"] = ""                     # 空 ⇒ 不改名（执行层记账）
                elif len(name) > ENTITY_NAME_MAX:         # 只丢这一格（text 照收）
                    warnings.append(f"{where}.name 超过 {ENTITY_NAME_MAX} 字 —— 丢掉这一格"
                                    "（更长的不是称呼, 是一句话）")
                else:
                    item["name"] = name
            if "text" in row:
                item["text"] = text                       # 空 ⇒ 不写看法（执行层记账）
            for k in ("reason", "aliases"):
                if row.get(k) not in (None, "", []):
                    warnings.append(f"{where} 改已有的对象不用写 {k} —— 已忽略")
            out.append(item)
            continue
        # ── 没有 id ⇒ 建 ────────────────────────────────────────────
        if not name:
            _drop(warnings, drops, f"{where} 没写 name —— 丢了")
            continue
        if len(name) > ENTITY_NAME_MAX:
            _drop(warnings, drops, f"{where} 的 name 超过 {ENTITY_NAME_MAX} 字 —— 丢了"
                                   "（超过这个长度的不是称呼, 是一句话）")
            continue
        if name.casefold() in known:
            _drop(warnings, drops, f"{where} {name!r} 已经在【已有的对象】里 —— 丢了"
                                   "（同一个人 / 地方 / 东西只能有一个对象）")
            continue
        reason = str(row.get("reason", "") or "").strip()
        if not reason:
            _drop(warnings, drops, f"{where} {name!r} 没给 reason —— 丢了"
                                   "（建对象是永久成本, 得说清为什么值得）")
            continue
        item = {"action": "create", "name": name, "reason": reason}
        raw_aliases = row.get("aliases")
        if raw_aliases is not None and not isinstance(raw_aliases, list):
            warnings.append(f"{where}.aliases 不是数组 —— 忽略")
        aliases = [str(a).strip() for a in (raw_aliases or [])
                   if isinstance(raw_aliases, list)
                   and isinstance(a, str) and str(a).strip()]
        if len(aliases) > MAX_ALIASES:
            warnings.append(f"{where}.aliases 超过 {MAX_ALIASES} 个"
                            f"（截到前 {MAX_ALIASES} 个）")
            aliases = aliases[:MAX_ALIASES]
        if aliases:
            item["aliases"] = list(dict.fromkeys(aliases))
        if text:                                          # 刚认识就有话说 ⇒ 顺手装上
            item["text"] = text
        out.append(item)
    return out, ValidationResult(tuple(errors), tuple(warnings), tuple(drops))
# ============================================================================
# 内部清洗（宁缺勿错: 坏项丢弃 + 报错; 质量项 warning 不阻断）
# ============================================================================

#: `links` 允许的 rel（**只有这三种** —— 见 DESIGN_GRAPH_V4 §2 的边表）。
#: ⚠️ 别加 `about`（⛔ **它不由 LLM 写**: 引擎从节点 `tags` 里的 `#entity:` 派生）·
#: 别加 `source` / `formed_by` / `from` / `to`（都随 promise 退图一起删了）。
#: ⭐ `supports` 在 `links` 这里**只认"看法 → 看法"那一种形状** ——
#: `supports` 共两种形状（§2）: `episode → 认知` 由**决策表**的 touch/update/add 写,
#: `认知 → 认知` 才轮到 links（用户 2026-09-29 裁决两条都留, 所以这一档**不是冗余**）。
LINK_RELS: tuple[str, ...] = ("supports", "contradicts", "evolved_from")
def _local_nodes(raw: Any, i: int, node_ids: set[str], errors: list[str],
                 optional: bool = False) -> list[str] | None:
    """`nodes` 字段清洗: 本地 id 数组（`u0001..`）。

    Returns: 归一化后的 id 列表; `None` = 有错（调用方丢这一行）。
    ⚠️ `optional=True`（`new_entity` 的顺手挂）时**空数组合法** —— 建对象本身就有价值。
    """
    if not isinstance(raw, list):
        errors.append(f"attributions[{i}].nodes 必须是数组（本地 id, 如 [\"u0001\"]）")
        return None
    out: list[str] = []
    for nid in raw:
        s = str(nid).strip()
        if s not in node_ids:
            errors.append(f"attributions[{i}].nodes 里的 {s!r} 不在本轮新节点里")
            return None
        if s not in out:
            out.append(s)
    if not out and not optional:
        errors.append(f"attributions[{i}]: nodes 不能是空的（挂谁上去?）")
        return None
    return out


def _clean_belief(val: dict, i: int, drops: list[str],
                  warnings: list[str]) -> dict | None:
    """`belief` 行的**对象内清洗**（L2 造看法 —— 缺正文/想改已有的 ⇒ 丢这一行）。

    ⛔ **不截断超长正文**: 截断是静默改内容（同 `_clean_episode_item` 的口径）。
    ⛔ **`id` 不合法**: 这一趟只**造**看法, 改已有的正文是另一件事（用户裁过"`update`
    那个词一个词扛三件事", 不复活它）。
    """
    if str(val.get("id", "") or "").strip():
        drops.append(f"cognitions[{i}]: belief 行不带 id"
                     "（这一趟只**造**新看法, 不改已有的正文）")
        return None
    text = str(val.get("text", "") or "").strip()
    if not text:
        drops.append(f"cognitions[{i}]: 造看法必须填 text（一条结论）")
        return None
    if len(text) > MAX_TEXT:
        drops.append(f"cognitions[{i}].text 超过 {MAX_TEXT} 字——丢这一行"
                     "（⛔ 不截断: 截断是静默改内容）")
        return None
    item: dict = {"action": "belief", "text": text}
    subject = str(val.get("subject", "") or "").strip()
    if subject:
        item["subject"] = subject
    tags, refs = _split_tags(val.get("tags"), val.get("entity"), warnings, drops,
                             where=f"cognitions[{i}].belief")
    if tags:
        item["tags"] = tags
    if refs:
        item["entity"] = refs
    sig = val.get("significance")
    if sig is not None and not isinstance(sig, bool):
        try:
            # 越界**夹紧**（值仍可用, 同 `_clamp` 的口径 —— 这不是"形状错"）
            item["significance"] = max(0.0, min(1.0, float(sig)))
        except (TypeError, ValueError):
            warnings.append(f"cognitions[{i}].significance 不是数——按缺省")
    return item


def _clean_soak(val: dict, i: int, group_ids: set[str] | None,
                errors: list[str], drops: list[str]) -> dict | None:
    """`experience` 行的**对象内清洗**（给**已有的类**重写沉淀 —— 建类不归它）。

    ⏸ **2026-10-13 停产**（随 `group` 退役）: `parse_cognitions` 已经**不再走到这里**
    （停产锚点在更前面就被丢行 + 记账了）。**函数留着** —— 停产不是删机器:
    `revise.apply_cognitions` 的 `_soak` 那一支也还在, 直接喂条目的调用方（单测 / 老档重放）
    照旧能用。
    """
    gid = str(val.get("id", "") or "").strip()
    if not gid:
        drops.append(f"cognitions[{i}]: experience 必须带 id（那是**已有的类**;"
                     " 建新类是上一道工序的活）")
        return None
    if group_ids is not None and gid not in group_ids:
        errors.append(f"cognitions[{i}].experience.id 不在发下去的类名单里: {gid!r}"
                      "（整包拒）")
        return None
    text = str(val.get("text", "") or "").strip()
    if not text:
        drops.append(f"cognitions[{i}]: 写沉淀必须填 text")
        return None
    if len(text) > MAX_TEXT:
        drops.append(f"cognitions[{i}].text 超过 {MAX_TEXT} 字——丢这一行"
                     "（⛔ 不截断: 截断是静默改内容）")
        return None
    return {"action": "experience", "group": gid, "text": text}


def _ref_list(v: Any, label: str, allowed: set[str] | None,
              errors: list[str], drops: list[str]) -> list[str] | None:
    """多值引用（`supports`）: **字符串或数组** → id 列表（去重保序）。

    ⭐ **单个字符串也收** —— 形状规则的①本来就是"值是字符串 = 引用一个已有节点",
    多值只是"一次给好几条"的省行写法; 写成一条**不该判错**。
    ⛔ 名单外的 id ⇒ **整包拒**（与 L1 同档: 那说明她没在引用真实世界）。

    Returns: `None` = 有错（调用方丢这一行, errors 已填）; `[]` = 她没写这个键（合法）。
    """
    if v is None:
        return []
    vals = [v] if isinstance(v, str) else (
        list(v) if isinstance(v, (list, tuple)) else None)
    if vals is None or any(not isinstance(x, str) for x in vals):
        drops.append(f"{label} 必须是字符串或字符串数组")
        return None
    out: list[str] = []
    for x in vals:
        s = x.strip()
        if not s or s in out:
            continue
        if allowed is not None and s not in allowed:
            errors.append(f"{label} 里的 {s!r} 不在列表里（整包拒）")
            return None
        out.append(s)
    return out


def _ref_one(v: Any, label: str, allowed: set[str] | None,
             errors: list[str]) -> str | None:
    """单值引用（`evolved_from`）: `""` = 她没写; `None` = 名单外（整包拒）。"""
    s = str(v or "").strip()
    if not s:
        return ""
    if allowed is not None and s not in allowed:
        errors.append(f"{label} 的 {s!r} 不在列表里（整包拒）")
        return None
    return s


def _id_list(v: Any) -> list[str]:
    """宽松取 id 数组（非列表 → 空; 元素转字符串去空白）。"""
    if not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip() for x in v if isinstance(x, (str, int)) and str(x).strip()]


def _clean_episode(e: Any, i: int, seq_set: set[int] | None = None,
                   drops: list[str] | None = None
                   ) -> tuple[dict | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(e, dict):
        return None, [f"episodes[{i}] 必须是对象"], []
    # 引擎字段一律不收（id/ts——LLM 塞了也丢弃）
    # ⚠️ `event_seq`（**板指针**, 引擎展开 `span` 后写上的）**不在这份名单里** ——
    #    旧版把它当引擎字段丢弃, 而 `digest.py` 又把它覆写成常量 ⇒ 板指针从来没存在过。
    # ⚠️ `segment_id` 也不在（那个字段本身已退役, 引擎不再落它）。
    for f in ("id", "ts"):
        if f in e:
            warnings.append(f"episodes[{i}] 含引擎字段 {f}——已忽略")
    # ⭐ **2026-09-29: `kind` 只在"例外"时写**（用户裁决: 轮次决定的常量不该由 LLM 声明）——
    # 缺键 / 空串 ⇒ 默认 **episode**；写坏值照旧拒（不静默降级 —— 静默改 kind 会让模型
    # 下次还这么写）。
    # ⏸ **2026-10-12 起"例外"没有了**: `profile`（玩家画像）停产（用户裁:
    # *"`entity.text` 取代了它的定位"*）⇒ 今天只有"经历"一种条目。但这条通路**不删**、
    # 也**不判成非法**（见下面那个 `if`）—— 契约已经不再要它, 可她惯性还会写,
    # 而"多写一条我们不要的东西"**不该罚她重写整段**（坏 kind 才拒）。
    kind = str(e.get("kind", "") or "").strip() or "episode"
    if kind == "episode":
        item, errors, warnings = _clean_episode_item(
            e, i, errors, warnings, seq_set, drops)
        if item is not None:
            item["kind"] = "episode"
        return item, errors, warnings
    if kind == "profile":
        # ⏸ **停产 = 认得出 + 不产条目**。`_drop` 写进 `ValidationResult.drops`
        #（"真的丢了东西"的账目行, 与 `warnings` 分开）⇒ 图上一个 profile 节点都不会
        # 再新建。⚠️ **存量档照旧读得到**（`nodes.KINDS` / 读侧 / `_PREFIX["profile"]`
        # 都留着）: 停的是**生产**, 不是**格式**（用户 2026-10-12 裁: 先停产, 真删等
        # 确认没有老档依赖）。
        _drop(warnings, drops, f"episodes[{i}]: kind=profile（玩家画像）"
                               "已停产, 这一条丢")
        return None, [], warnings
    return None, [f"episodes[{i}].kind 非法: {kind!r}（不写 = 经历; 今天没有"
                  f"第二种合法条目）"], []


def _split_tags(raw: Any, refs: Any, warnings: list[str], drops: list[str], *,
                where: str) -> tuple[list[str], list[str]]:
    """`tags` + `entity` → （**检索词** ≤`MAX_TAGS`, **引用** ≤`ENTITY_REFS_MAX`）。

    ⭐ **2026-10-13**: 引用从 `tags` 里的 `#entity:名字` **搬进了独立字段 `entity`**
    （用户裁 —— 那个前缀养着前缀识别 / 分开计数 / "`#` 是标记空间"三样东西, 而它在节点
    `tags` 里只有 `#entity:` 一个成员）。所以这里收**两处**:
      · `entity` = **正路**（一个新字段, 对模型自解释）;
      · `tags` 里那些 `#entity:名字` = **她惯性还在写**（老契约教了两版）⇒ **认得出、
        挪进 `entity`**（⛔ 不丢行、不判非法 —— 同 `profile` / `experience` 的 B 案口径）,
        只记一条 warning 提醒她"下次写在 `entity` 那一格"。
    ⛔ **`#` 开头的别的东西**照旧只告警（那是引擎的标记空间, 不该占检索词）——
    但 `#pinned` 那种**根本不在节点 tags 上**的东西, 不必在这里编故事。

    ⚠️ 本函数**只做形状**（纯字符串）: 引用里的名字**不在这里解析**（契约层没有 store）
    ⇒ 归一与落边在执行层（`entities.normalize_entity_refs` / `revise.link_entity_refs`）。
    """
    words: list[str] = []
    names: list[str] = []
    for t in (raw if isinstance(raw, list) else []):
        if not isinstance(t, str) or not t.strip():
            continue
        s = t.strip()
        if s.startswith(ENTITY_TAG_PREFIX):
            legacy = s[len(ENTITY_TAG_PREFIX):].strip()
            if not legacy:
                _drop(warnings, drops, f"{where}.tags 里那个 `#entity:` 没写名字 —— 丢了")
                continue
            warnings.append(f"{where}.tags 里的 `{s}` 是**旧的写法** —— 已挪进 `entity`"
                            "（引用现在写在自己的那一格里）")
            names.append(legacy)
            continue
        if s.startswith("#"):
            warnings.append(f"{where}.tags 里 {s!r} 以 `#` 开头 —— 那不会被当检索词"
                            "（`#` 是引擎的标记空间）")
        words.append(s)
    for t in (refs if isinstance(refs, list) else []):
        if isinstance(t, str) and t.strip():
            names.append(t.strip())
    if refs is not None and not isinstance(refs, list):
        warnings.append(f"{where}.entity 必须是数组 —— 忽略")
    names = list(dict.fromkeys(names))
    if len(words) > MAX_TAGS:
        warnings.append(f"{where}.tags 超过 {MAX_TAGS} 个检索词（截到前 {MAX_TAGS} 个）")
        words = words[:MAX_TAGS]
    if len(names) > ENTITY_REFS_MAX:
        warnings.append(f"{where}.entity 超过 {ENTITY_REFS_MAX} 个引用"
                        f"（截到前 {ENTITY_REFS_MAX} 个 —— 这条涉及谁要挑）")
        names = names[:ENTITY_REFS_MAX]
    return words, names


def _norm_index(raw: Any) -> str | None:
    """索引项 → 规范串 `"28.3"` / `"28.p"` / `"28"`（坏项 → None）。"""
    from contract.timeline_index import parse_index
    got = parse_index(raw) if isinstance(raw, str) else (
        (raw, "") if isinstance(raw, int) and not isinstance(raw, bool) else None)
    if got is None:
        return None
    seq, rec = got
    return f"{seq}.{rec}" if rec != "" else str(seq)


def _drop(warnings: list[str], drops: list[str] | None, text: str) -> None:
    """记一条**真的丢了东西**的 warning（⭐ D1, 2026-09-29）。

    ⚠️ 这是"分类"的**唯一来源**: 一处 warning 是不是"丢"由**写它的这一行代码**说了算,
    绝不靠事后拿中文子串去猜（`ValidationResult.drops` 的 docstring 讲了为什么）。
    ⇒ **改这里的用法时只有一个判据**: 这条 warning 背后**有没有一个内容离开过库**?
    有（区间作废 / 原话丢了 / 心境丢了）⇒ 用 `_drop`; 只是形状建议 / 夹紧 / 兼容旧名 ⇒
    `warnings.append`。
    """
    warnings.append(text)
    if drops is not None:
        drops.append(text)


def _clean_seq_list(raw: Any, seq_set: set[int] | None, *,
                    label: str, warnings: list[str],
                    record_level: bool, drops: list[str] | None = None) -> list[str]:
    """索引数组清洗 —— **坏项逐条丢弃**（不废整包, 与 `parse_index_list` 同纪律）。

    `record_level=False`（板指针 `event_seq`）: 只收事件级 `"28"`, 记录级
    `"28.3"` 视为写错（它的 seq 部分仍然认, 但会记一条 warning 提醒）。
    `record_level=True`（`verbatim` 索引通道）: 收 `"28.3"` / `"28.p"` / `"28"`。

    `seq_set` 非空时做 ⊆ 校验——**抄不存在的编号 → 丢弃**（防幻觉: 序号由引擎发,
    抄不到就丢, 绝不猜）。
    """
    from contract.timeline_index import parse_index
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    out: list[str] = []
    bad = 0
    for it in items:
        norm = _norm_index(it)
        if norm is None:
            bad += 1
            continue
        seq = parse_index(norm)[0]
        if not record_level and "." in norm:
            warnings.append(f"{label} 收了记录级索引 {norm!r}——板指针只收事件级"
                            f"（已按事件 {seq} 收下）")
            norm = str(seq)
        if seq_set is not None and seq not in seq_set:
            bad += 1
            _drop(warnings, drops, f"{label} 的 {norm!r} 不在本段时间线里——丢弃")
            continue
        if norm not in out:
            out.append(norm)
    if bad:
        warnings.append(f"{label}: {bad} 个索引不可用（已丢弃）")
    return out


def _clean_span(raw: Any, seq_set: set[int] | None, *, label: str,
                warnings: list[str], drops: list[str] | None = None) -> list[int] | None:
    """⭐ 区间清洗（**N3**, 2026-09-29）—— `[28, 30]` → `[28, 30]`；坏形状 → `None`。

    规矩:
      · 收 **2 个端点**的数组；单值也收（退化成 `[n, n]`）；>2 个 ⇒ **只取首尾** + 告警
      · 端点必须是**事件级** seq（`"28"`）；记录级 `"28.3"` 取它的 seq 部分 + 告警
      · `起 ≤ 止`；**反了 ⇒ 丢弃**（⚠️ **不自动交换** —— 静默改她的意思比报错贵）
      · `seq_set` 非空时**两端都必须存在**（抄不存在的编号 → 丢弃）

    ⚠️ **只校验两端的存在性，不逐块校验** —— 区间是"这一段"，引擎按 `seq_set` 求交即可；
    逐块校验会把"区间里夹着 marker（marker 不在 `seq_set` 里）"误判成坏区间。

    ⚠️ **一律告警、不废整包**（与 `_clean_seq_list` 同纪律）: 一个坏区间不该让她重写整段,
    而"本条没有位置"是**可见的**（节点 `event_seq` 为空 ⇒ `_node_ts` 回落到段 ts）。
    """
    from contract.timeline_index import parse_index
    if raw is None:
        return None
    if isinstance(raw, (str, int)):
        items: list = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        _drop(warnings, drops, f"{label} 不是数组——丢弃")
        return None
    if not items:
        _drop(warnings, drops, f"{label} 是空数组——丢弃")
        return None
    if len(items) > 2:
        warnings.append(f"{label} 给了 {len(items)} 个端点——只取首尾")
        items = [items[0], items[-1]]
    seqs: list[int] = []
    for it in items:
        norm = _norm_index(it)
        if norm is None:
            _drop(warnings, drops, f"{label} 的 {it!r} 不是合法编号——丢弃整个区间")
            return None
        seq = parse_index(norm)[0]
        if "." in norm:
            warnings.append(f"{label} 收了记录级索引 {norm!r}——已按事件 {seq} 收下")
        seqs.append(seq)
    if len(seqs) == 1:
        seqs.append(seqs[0])                      # 单值 ⇒ 退化成一块
    lo, hi = seqs
    if lo > hi:
        _drop(warnings, drops, f"{label} 起止反了（{lo} > {hi}）——丢弃（不自动交换）")
        return None
    missing = [s for s in (lo, hi) if seq_set is not None and s not in seq_set]
    if missing:
        _drop(warnings, drops, f"{label} 的端点 {missing} 不在本段时间线里——丢弃")
        return None
    return [lo, hi]


def _fill_verbatim(item: dict, e: dict, i: int, warnings: list[str],
                   seq_set: set[int] | None, drops: list[str] | None = None) -> None:
    """`verbatim` = **记录行号**（唯一通道）。

    ① `"verbatim": ["28.3", "20.p"]` —— 抄时间线的记录行号
    ② 也可显式给 `"verbatim_seq": [...]`（等价; 两条并存时合并去重）

    落库: `verbatim_seq` = 索引（可重解析 / 板归属）; `verbatim` = 文本, **由引擎在
    `digest.py` 解析索引后回填**（parse 层拿不到事件流）。

    ⏸ **文本通道（`"verbatim": "…"` 字符串）2026-09-29 退役**：它和索引说的是同一件事,
    而并存时**文本优先** ⇒ 一个偏了一位的索引会被一句"看起来正常的"手抄文本静默盖掉。
    现在只认数组: 写字符串 → 逐条丢弃 + 告警（**不兜底**）。
    """
    seqs: list[str] = []
    for key in ("verbatim", "verbatim_seq"):
        v = e.get(key)
        if isinstance(v, (list, tuple)):
            seqs.extend(_clean_seq_list(v, seq_set, label=f"episodes[{i}].{key}",
                                        warnings=warnings, record_level=True,
                                        drops=drops))
        elif v is not None:
            _drop(warnings, drops,
                  f"episodes[{i}].{key} 必须是数组（记录行号）——忽略")
    if seqs:
        item["verbatim_seq"] = list(dict.fromkeys(seqs))


def _read_text(e: dict, i: int, warnings: list[str]) -> str:
    """条目正文 —— 主字段 `text`（2026-09-21 三槽合流）, 兼容旧名 `narration`/
    `pattern`/`content`。

    ## 为什么兼容旧名（这是一个**安全**决定, 不是留恋旧形状）

    契约文案改名的那个版本落地时, 模型有惯性（也可能命中**旧的 prompt 缓存**）——
    若只认 `text`, 一次惯性就**整条丢弃**（episode/experience 都是"缺正文即丢"）,
    代价是整包重发 + 反馈重试。兼容读 + **一行 warning** 把这件事变成可观测:
    长期还在出现旧名 → grep `用了旧字段名` 就能发现（同 §8"示例才是形状来源"那条纪律）。
    """
    for key in ("text", "narration", "pattern", "content"):
        v = e.get(key)
        if isinstance(v, str) and v.strip():
            if key != "text":
                warnings.append(
                    f"episodes[{i}] 用了旧字段名 {key}——已按 text 收下"
                    f"（schema 已改名, 若长期出现请查 prompt 缓存）")
            return v.strip()
    return ""


def _clean_episode_item(e: dict, i: int, errors: list[str], warnings: list[str],
                        seq_set: set[int] | None = None,
                        drops: list[str] | None = None
                        ) -> tuple[dict | None, list[str], list[str]]:
    """kind=episode 条目的字段清洗（缺 text 整条丢弃, 宁缺勿错）。"""
    text = _read_text(e, i, warnings)
    if not text:
        return None, errors + [f"episodes[{i}] 缺 text"], warnings
    if len(text) > MAX_TEXT:
        # 宁缺勿错: 整条丢弃（包已无效 → 反馈重试会让 LLM 重写整包, 截断反而静默改内容）
        return None, errors + [f"episodes[{i}].text 超过 {MAX_TEXT} 字——整条丢弃"], warnings
    item: dict = {"text": text}
    title = e.get("title")
    if isinstance(title, str) and title.strip():
        item["title"] = title.strip()
    else:
        warnings.append(f"episodes[{i}] 缺 title（建议 8-16 字短标题）")
    # ⛔ **位置不从这里读**（3b-2）: 切分权归 R0 ⇒ 一条经历覆盖哪一段由**骨架**定
    # （`split` 那轮的 `seqs`）, 引擎按顺序把这一行并到那条切片上。
    # ⇒ `span` 与旧形状 `event_seq`（"她自己挑位置"时代的产物）**都已退役**:
    # 还写就只记一句 warning, 引擎忽略它（没有"她的位置"可错了）。
    for gone in ("span", "event_seq"):
        if gone in e:
            warnings.append(f"episodes[{i}] 写了 {gone}——位置由【本段骨架】定, 这个字段已退役"
                            f"（引擎忽略它）")
    # verbatim: 记录行号（唯一通道 —— 文本通道 2026-09-29 退役）
    _fill_verbatim(item, e, i, warnings, seq_set, drops=drops)
    tags, refs = _split_tags(e.get("tags"), e.get("entity"), warnings, drops,
                             where=f"episodes[{i}]")
    if not tags:
        warnings.append(f"episodes[{i}] 缺 tags（检索导向 1-4 个）")
    if tags:
        item["tags"] = tags
    if refs:
        item["entity"] = refs                   # 这条经历**涉及谁**（引擎据此落 `about`）
    # ⭐ `topics`（2026-10-07, `TODO_TWO_PASSES` 的 P0）—— "这条经历关于什么"的**具体东西**,
    # 是"同类的事"认亲的把手（L1 的 `akin` 要求 `on` ∈ 两端 `topics` 的交集）。
    # ⚠️ **缺了不告警**（想不出具体的 ⇒ 空数组是合法的 —— 那是"这条还没轴"的正常状态）;
    # 超上限 ⇒ 截 + 告警（与 `MAX_SEGMENTS` 同族: 上限要能看见）。
    topics = [t.strip() for t in e.get("topics", []) if isinstance(t, str) and t.strip()]
    if len(topics) > TOPICS_MAX:
        warnings.append(f"episodes[{i}].topics 超过 {TOPICS_MAX} 个（截到前 {TOPICS_MAX} 个）")
        topics = topics[:TOPICS_MAX]
    if topics:
        item["topics"] = list(dict.fromkeys(topics))      # 去重保序
    # ⏸ `about_hint`（归属线索）与 `items`（物品台账）两个字段 2026-09-29 退役 ——
    # 这里不再有清洗代码: **白名单外的键本来就不落库**。（前者与 R3 的"挂谁"判两次,
    # 见 `core/brain/REDUNDANCY.md` #2。）
    sig = e.get("significance")
    try:
        sig_f = float(sig) if sig is not None else 0.5
    except (TypeError, ValueError):
        warnings.append(f"episodes[{i}].significance 非数字——取 0.5")
        sig_f = 0.5
    item["significance"] = max(0.0, min(1.0, sig_f))
    # 情绪两标量（§3.3.3）: **缺/坏 → 不落字段**（None 哨兵）, 不折成 0.0——
    # 「未采集」与「真的毫无波澜」是两件事, 合并会让旧档在召回里冒充后者。
    # （`emo_valence` 2026-09-21 删——有生产零消费, 极性由 `emo_shape` 逐键承担。）
    for fname, lo, hi in (("emo_int", 0.0, 1.0), ("emo_span", 0.0, 1.0)):
        raw_v = e.get(fname)
        if raw_v is None:
            continue
        if isinstance(raw_v, bool):
            warnings.append(f"episodes[{i}].{fname} 是布尔——忽略")
            continue
        try:
            v = float(raw_v)
        except (TypeError, ValueError):
            warnings.append(f"episodes[{i}].{fname} 非数字——忽略")
            continue
        if v != v:                              # NaN
            warnings.append(f"episodes[{i}].{fname} 是 NaN——忽略")
            continue
        item[fname] = max(lo, min(hi, v))       # 越界**夹紧**（不丢弃——值仍可用）
    # 来源: 非空 = 听说的 + 转述者是谁; 空 = 亲历。
    # ⏸ `epistemic` 已退役（与 observer 互为函数, 见 `REDUNDANCY.md` #3）—— 旧 prompt 缓存
    # 里还带着它的话只**提一句**不落库（值与 observer 重复, 信息没丢, 不废整包）。
    if e.get("epistemic") not in (None, ""):
        warnings.append(f"episodes[{i}].epistemic 字段已退役——只填 observer（忽略）")
    obs = e.get("observer")
    if isinstance(obs, str) and obs.strip():
        item["observer"] = obs.strip()
    return item, errors, warnings


def _nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


#: 默认注册表实例（板块 4 引擎编排消费）
