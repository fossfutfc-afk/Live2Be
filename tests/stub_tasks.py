"""测试桩的**任务分派**助手（节点 5b, 2026-09-21）。

桩不再按中文关键字认任务（`情绪标签` / `变更句数组` / …——那些串来自 prompt 文案,
改一次措辞就静默不命中, ARCH_REVIEW P2-8）。产品侧现在在
`llm.chat(..., task=…)` / `chat_full(..., task=…)` 上声明调用身份
（`llm/task_labels.py`）, 桩读 `kw["task"]` 分派。

## 用法

```python
from llm import task_labels as T
from tests import stub_tasks

class ScriptedLLM:
    def chat(self, messages, **kw):
        task = kw.get("task")
        self.tasks.append(task)                 # 需要按调用身份过滤时记一份
        if task == T.PLACE:                     # 本用例特别关心的那一路: 显式覆盖
            return [{"sentence": 2, "place": "school_rooftop"}]
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:                   # 其余标注/后台调用: 走标准应答
            return reply
        return self._scripts.pop(0)             # 主链（mmt / bond）: 按脚本队列
```

## 两条纪律

1. **不要**再写 `if "某中文串" in last` —— 那正是本条要根除的耦合
   （`tests/core/test_stub_dispatch_guard.py` 会扫出来）;
2. 主链之外的新任务 → 在 `llm/task_labels.py` 加标签, 并在这里给出标准应答;
   漏了会在**调用点**炸（`unknown_task` 的报错信息直接指路）。
"""
from __future__ import annotations

import json
import re

from llm import task_labels as T

#: 情绪标注的**条数口径**: `恰 N 项`（记录级模板显式双写）——**别**用 system 的
#: `^\d+: ` 编号行（模板【示范】也带编号行, 会恒多 4 条 → 全程兜底还不报错）
_COUNT_RE = re.compile(r"恰 (\d+) 项")
#: R0 桩找"本段有几个事件块": 时间线里**行首**的 `[28]`（事件头）。
#: ⚠️ 锚在**行首**（`^` + MULTILINE）—— `[28.0]` / `[28.p]` 是记录行, 不匹配;
#: 正文里出现的方括号也不会被当成块头。
_EVENT_HEAD_RE = re.compile(r"^\[(\d+)\]", re.MULTILINE)


def emotion_count(messages) -> int:
    """情绪标注期望的条数（取不到 → 1）。"""
    last = messages[-1]["content"] if len(messages) > 1 else ""
    m = _COUNT_RE.search(last or "")
    return int(m.group(1)) if m else 1


def timeline_heads(messages) -> list[str]:
    """从 user 消息里抓出本段时间线的**事件头编号**（升序去重）。

    ⚠️ 只扫 user 消息: 事件头只出现在【本段新增互动】那一节里
    （`_sections_for` 只拼非空块, 别的节没有 `[N]` 行首）。
    """
    text = "\n".join(str(m.get("content") or "") for m in messages
                     if m.get("role") == "user")
    return sorted(dict.fromkeys(_EVENT_HEAD_RE.findall(text)), key=int)


def split_reply(messages, *, join: int = 0) -> dict:
    """R0 的标准应答: **一个事件头一条切片**（`join>0` 时每 N 个头并成一条）。

    ⚠️ 为什么默认"一头一片": R1 的每条 episode 都对着一条切片 ⇒ 桩这样回,
    "每条 episode 都有落点"这个前提**天然成立**, 各用例不用各自编 `span`。
    真机当然不是一头一片（MMT 0~5 条）—— 桩不模仿真实分布, 只保证形状合法。
    """
    heads = timeline_heads(messages)
    if not heads:
        return {"segments": []}
    step = max(1, join)
    groups = [heads[i:i + step] for i in range(0, len(heads), step)]
    return {"segments": [{"span": [int(g[0]), int(g[-1])],
                          "abstract": f"第 {g[0]} 件事"} for g in groups]}


def splits_for_episodes(episodes, messages=None) -> dict:
    """R0 的应答 —— ⭐ **照着 R1 那份应答里声明的区间回**（只抄不改）。

    给"自己写死 R1 输出"的桩用: R1 说它覆盖 `[1,4]`, 那 R0 就得先把 `[1,4]` 切出来,
    否则编排层会以为"这一段没有值得记的"而当场收工（R1 那份应答白写）。
    ⚠️ **只搬运, 不修正**: 区间写得坏（端点越界 / 起止反）就原样回 —— 那是用例
    故意要触发的契约行为（`drops`）, 在这里"顺手改好"会把被测的路径绕过去。

    三种情形（按 R1 那份应答的形状分）::

        [{"span": [1, 4]}, …]   → 每个声明的区间一条切片（只抄不改）
        [{"text": "…"}, …]      → ⚠️ **旧形状（没有 span）**: 回**一条覆盖整段**的切片
                                  （`messages` 给得出事件头时用首尾, 否则 `[1, 999]`）
                                  —— 对齐 `_create_a_nodes` 的兜底语义（"没有位置"
                                  的条目吃段级指针 = 整段都算它覆盖了）
        []                      → 一条覆盖整段（同上）
    """
    if isinstance(episodes, dict):
        episodes = episodes.get("episodes")           # 整个应答传进来也认
    episodes = list(episodes or [])
    spans = re.findall(r'"span"\s*:\s*\[?\s*(-?\d+)\s*(?:,\s*(-?\d+)\s*)?\]?',
                       json.dumps(episodes, ensure_ascii=False))
    if spans:
        return {"segments": [{"span": [int(lo), int(hi if hi != "" else lo)],
                              "abstract": f"第 {lo} 件事"}
                             for lo, hi in spans]}
    if not episodes:
        # `{"episodes": []}` = "这一段我不记" ⇒ 空骨架（那正是它的意思）
        return {"segments": []}
    # ⚠️ R1 **没声明区间**（3b-2 起它本来就不该声明）⇒ 按**它给了几条**切几片。
    # ⭐ 判据: 这个桩的职责是"让对位成立" ——
    #   · 条数 = **R1 给的条数**（多切会让后面几条没人填 ⇒ 下一轮 decisions 覆盖不全）;
    #   · 区间**互不相同且在时间线内**（逐字相同会被当重复丢、端点越界会被丢整条）。
    # ⇒ 把 n 个事件头**均匀摊给 N 条切片**; 头不够时按实测最大 seq 往后让一格。
    # ⚠️ 真机的 R0 一条一切、不会重叠/越界 —— 这些只是**桩**为了"对位成立"的取法。
    heads = timeline_heads(messages or [])
    h = sorted({int(x) for x in heads}) or [1]
    n = max(1, len(episodes))
    hi = _max_seq_in(messages)                         # 时间线的**实测**上界
    spans: list[list[int]] = []
    used: set[tuple[int, int]] = set()
    for i in range(n):
        a, b = i * len(h) // n, (i + 1) * len(h) // n
        part = h[a:max(a + 1, b)]
        lo_i, hi_i = part[0], part[-1]
        while (lo_i, hi_i) in used and hi_i < hi:      # 撞了 ⇒ 往后让一格（仍在范围内）
            hi_i += 1
        if (lo_i, hi_i) in used:                       # 让不动了（时间线太窄）⇒ 只能重复
            lo_i = hi_i = min(hi, hi_i)
        used.add((lo_i, hi_i))
        spans.append([lo_i, hi_i])
    return {"segments": [{"span": s, "abstract": f"第 {i + 1} 件"}
                         for i, s in enumerate(spans)]}


def _max_seq_in(messages) -> int:
    """user 料里出现过的**最大事件头编号**（时间线的实测上界; 取不到 → 999）。"""
    heads = timeline_heads(messages or [])
    return max((int(x) for x in heads), default=999)


def split_for_scripted(messages, episodes) -> dict:
    """R0 的应答 —— 给"R1 那份应答已经写死在测试里"的桩用（脚本桩的统一入口）。

    在**每一个** task 分派处照抄这一行就够::

        if task == T.DIGEST_SPLIT:
            return stub_tasks.split_for_scripted(messages, self.episodes)

    三种情形::

        [{"span": [1, 4]}, …]   → 每个声明的区间一条切片（只抄不改 —— 坏的原样回）
        [{"text": "…"}, …]      → ⚠️ **没给区间**: 回**一条覆盖整段**的切片
                                  （⚠️ **一条**, 不是一头一片 —— 见下）
        []                      → **空骨架**（`{"segments": []}`）

    ⛔ **它永远不返回空骨架** —— "这一段没有值得记的"是 R0 的一条**判据**,
    要测它必须**显式**给（把桩的 `split=` 参数设成 `{"segments": []}`）。
    判据: 派生出来的东西不该顺手改变链路走向 —— 否则每个脚本桩的用例都会
    在 R0 悄悄收工（实测: 一次改动 81 条用例变红, 全部同一个原因）。

    ⭐ **`[]` 也当"一条覆盖整段"**（3b-2 改）: 从前 `[{"episodes": []}]` ⇒ 空骨架。
    但 3b-2 起 R1 **不再声明位置**, 所以"R1 给了几条 episode"与"R0 切了几条"必须
    **条数一致**, 否则多出来的切片没人填、下一轮的 decisions 覆盖不全 ⇒ 整段被拒。
    这个桩的职责是**让对位成立**, 不是模仿真实切分。
    """
    if isinstance(episodes, dict):
        episodes = episodes.get("episodes")
    return splits_for_episodes(episodes or [], messages)


def annotation_reply(task: str | None, messages, *,
                     digest_delta: int = 0,
                     split: dict | None = None,
                     digest_segments: bool = False) -> object | None:
    """标注/记忆消化类调用的**标准应答**; 主链任务 → None（调用方继续走脚本队列）。

    `digest_delta`: 好感增量（用例需要非 0 时传, 如 webgui 的 5）—— ⭐ 它由 **R1** 交,
    所以挂在 `DIGEST_RECORD` 那一支（M1 之前挂在 understand/relate 那一支）。
    `split` / `digest_segments`: R0 切分轮 —— 缺省回**空骨架**
    （= "这一段没有值得记的" ⇒ 编排层当场收工, 后面几轮一次都不发;
    这一条让"不关心记忆的用例"零成本跳过整条 digest 链）。
    要看完整链路（建节点/连边/归属/分群）的用例传 `digest_segments=True`
    （或直接给 `split={...}` 指定应答）。
    """
    if task == T.EMOTION:
        return ["nomal"] * emotion_count(messages)
    if task == T.PLACE:                 # 句级锚点 → 无变更
        return []
    if task == T.PLACE_BOARD:           # 板级换场翻译 → 不切背景
        return {"place": ""}
    if task == T.PLACE_VARIANT:         # 选图（第二遍）→ 保持当前图
        return {"image": ""}
    if task == T.DIGEST_SPLIT:          # R0 切分 → 缺省"没有值得记的"
        if split is not None:
            return split
        return split_reply(messages) if digest_segments else {"segments": []}
    if task == T.DIGEST_RECORD:
        # ⭐ **M1（2026-10-05）: 好感由 R1 判** —— 它曾挂在下面的 understand 那一支。
        return {"episodes": [], "affection_exp_delta": digest_delta}
    if task in (T.DIGEST_RELATE, T.DIGEST):
        # ⭐ L1（2026-10-07 P1b-2）: 只判关系、**不写正文** ⇒ 缺省"什么关系都没看出来"。
        return {"relations": []}
    if task == T.DIGEST_SETTLE:           # ④ 沉淀（settle）→ 没有可归属的
        return {"entities": []}
    if task == T.DIGEST_GROUP:          # L2-a 分群 → 一个类都不分（块留到下段）
        return {"attach": [], "new": [], "merge": []}
    if task == T.DIGEST_COGNIZE:        # ⭐ L2-b（P10）→ 一条看法都不造、沉淀不动
        return {"cognitions": []}
    return None


def unknown_task(task: str | None) -> AssertionError:
    """未知/缺失 task 的报错（**产品侧漏传 `task=` 或新任务没补桩**都走它）。"""
    if task is None:
        return AssertionError(
            "这次 LLM 调用没带 task= —— 产品侧调用点漏了调用身份（节点 5b）: "
            "去 `llm/task_labels.py` 挑一个标签并加到那处 `llm.chat(...)` 上。")
    return AssertionError(
        f"桩不认识 task={task!r} —— 若是新任务: 在 `llm/task_labels.py` 加标签, "
        f"并到 `tests/stub_tasks.py::annotation_reply` 给出标准应答。"
        f"合法标签: {sorted(T.ALL)}")
