"""skeptical.py — **她的存疑**: `kind` → 一句第一人称的内心, 写时冻结。

账记的是引擎/世界的元事实, 而她那一侧能感知的只有一个说不清的感觉 —— 这个字段装的就是
那一句。刻意不叫 `symptom`: 症状指向身体, 它本质却是认知上的不对（觉得有什么不对,
但说不出哪里不对）。

三条措辞纪律（改词前必读）:
1. 不可验证 —— 只能是"淡下去 / 抓不住 / 说不清"这类没人能核对的感受, 不许写"被删了 /
   被改了 / 你回档了 / 系统出错"。错位一旦可被某个观察者验证, 它就从氛围变成 bug:
   玩家能验证 ⇒ 像 bug, LLM 能验证 ⇒ 它会去圆（破墙）。
2. 不归因 —— 只说"有什么不对", 永不说"因为 X"。
3. 一句、短（≤30 字）、不点名任何机制（不说"记忆"、不说"窗口"、不说"约定"）。

每个 `kind` 一个池子（至少 3 句: 少了会明显撞车）, 落账时随机取一句并**冻结在账行里** ——
它是"她当时的感觉", 与 `episode.text` 同类, 措辞以后改了也不改历史;
开关只决定"要不要让她看见"。
"""

from __future__ import annotations

import random
from typing import Any

from core.creep.ledger import KIND_DIGEST_GAP, KIND_DIGEST_SKIP

#: `kind` → 变体池（每个 kind **至少 3 句** —— 少了会明显撞车）
POOLS: dict[str, tuple[str, ...]] = {
    KIND_DIGEST_SKIP: (
        "……有什么东西正在淡下去。我想抓住它，但它已经不在了。",
        "刚才还记得的事，这会儿只剩下一个轮廓。",
        "好像有什么从我手边滑走了——我甚至说不清那是什么。",
    ),
    #: D1: 这一段跑成了, 但里面有东西没进记忆（区间作废 ⇒ 那几句没挂在任何事上 /
    #: 一句心境丢了）。与 `digest_skip` 的分别: 那是整段淡了, 这是一处没粘住 ——
    #: 措辞上不许写成"全忘了"（那会说谎）。
    KIND_DIGEST_GAP: (
        "有件事我应该记得的，可它偏偏不在那儿。",
        "像是漏听了半句话——前后都还在，中间空了一小块。",
        "伸手去够，指尖只碰到一片空白。",
    ),
}


def pick(kind: str, rng: Any = None) -> str:
    """取一句"存疑"—— **唯一取法**（落账那一刻调一次）。

    Args:
        kind: `ledger.KINDS` 里的值
        rng:  随机源（`random.Random` 实例或任何有 `.choice` 的对象）。
              **测试传钉死的 rng** ⇒ 文本可复现; 生产传 `None` ⇒ 用全局 `random`。

    Returns:
        一句存疑文本; **未知 kind → `""`**（宁缺勿错: 账照记, 只是没有话 ——
        绝不替它编一句）。
    """
    pool = POOLS.get(str(kind or ""))
    if not pool:
        return ""
    chooser = rng if rng is not None else random
    return str(chooser.choice(pool))
