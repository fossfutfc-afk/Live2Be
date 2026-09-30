# -*- coding: utf-8 -*-
"""⭐ N5 接线单测 —— 「你想起的事」真的进了 MMT 本轮的 messages（2026-09-29）。

与 `tests/core/test_momotalk_time_notes.py` 同一套桩口径（**脚本按 `task=` 分派**）。

VALUE: 这条测的是**接线与落点**（`agent_turn` 的 P19 槽位）, 不是召回质量本身
（那在 `test_wiki_recall.py`）。三个最容易静默错的地方各钉一条:

1. ⭐ **它必须落在动态尾, 不能拼进 system** —— 这一段的查询是**玩家这一句**,
   每轮都不同; 进了 system（盒 + brain 的稳定前缀）就**逐轮破上下文缓存**,
   而"稳定前缀"是体感主线的地基（`core/promptkit/tail.py` 的不变式）。
2. ⭐ **查询 = 本轮玩家输入**（不是她的上一句、不是窗口全文）——用"哪一条被想起"
   反着验: 两条 episode 各带一个词, 换一句话就该换一条出来。
3. 召回失败 / 空库 / 一条都不像 ⇒ **不注**（宁缺勿错: 少一段上下文, 剧情照走）。

⚠️ **后端一律走构造参数 `embed_fn=`（N5 接缝）, 不 patch 模块属性**:
`core.mmt.engine` 在 `tests/core/test_split_safety.py` 的 TARGETS 里, patch 模块属性
将来会**静默失效**（那条守门拦的就是这个）。这里给一个"一调就炸"的后端 ⇒
走**词面降级**（确定性, 不依赖本机有没有起 embedding 服务）。
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brain.wiki_v2 import WikiStoreV2, make_node      # noqa: E402
from core.mmt.engine import MomoTalkEngine                # noqa: E402
from core.session.store import SessionStore               # noqa: E402
from llm import task_labels as T                          # noqa: E402
from tests import stub_tasks                              # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CHARACTER = "igusa_haruka"
HEADER = "【你想起的事"


def _no_embed():
    """确定性后端: 一调就炸 ⇒ `recommend_candidates` 自动退词面（tags/Dice）。"""
    def boom(texts):
        raise RuntimeError("embed backend off（本用例走词面降级）")
    return boom


class ScriptedLLM:
    def __init__(self):
        self.snapshots: list[list[dict]] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.snapshots.append([dict(m) for m in messages])
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:
            return reply
        if task in T.MAIN:
            return '{"text": "嗯……早、早上好！"}'
        raise stub_tasks.unknown_task(task)


def _engine(tmp_path, llm) -> MomoTalkEngine:
    store = SessionStore(data_root=tmp_path)
    eng = MomoTalkEngine(ROOT / "config" / "characters", llm, store=store,
                         embed_fn=_no_embed)
    name = eng.start_session(CHARACTER)
    root = store.create(CHARACTER, name)
    eng.attach_session(root.session_id)
    return eng


def _seed(tmp_path, text, *, title, tags, ts="2026-09-20T10:00:00") -> None:
    """写一条 episode 到真机同款位置（引擎是**另开一个 store** 读的, 所以要 save）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    st.add(make_node("episode", text=text, title=title, tags=list(tags), ts=ts,
                     significance=0.6, event_seq=[1]))
    st.save()          # ⚠️ `add` 只改内存


def _joined(llm: ScriptedLLM) -> str:
    return "\n".join((m.get("content") or "") for m in llm.snapshots[-1])


def test_recall_note_reaches_messages(tmp_path):
    """★ 召回到的那条（**带标题**）出现在本轮 messages 里。"""
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午",
          title="苔藓的约定", tags=("杂草",))
    eng.agent_turn("我今天又去杂草屋那边了")
    joined = _joined(llm)
    assert HEADER in joined, joined[-500:]
    assert "《苔藓的约定》" in joined                 # ⭐ 标题 = 她要指的地址
    assert "老师陪我在杂草屋蹲了一下午" in joined
    print("    N5: 「你想起的事」进了 messages（带标题）")


def test_recall_note_is_in_the_dynamic_tail_not_system(tmp_path):
    """⭐⭐ **落点守卫**: 它必须在 history 之后的动态尾, 且**不在**盒+brain 那条 system 里。

    进了 system = 每轮改一次前缀 ⇒ 上下文缓存逐轮全灭（`tail.py` 的不变式）。
    这条用例就是那个不变式的守门人。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午",
          title="苔藓的约定", tags=("杂草",))
    eng.agent_turn("我今天又去杂草屋那边了")
    msgs = llm.snapshots[-1]

    assert msgs[0]["role"] == "system"
    assert HEADER not in msgs[0]["content"], "召回段被拼进了 system（前缀缓存会逐轮失效）"
    idx_recall = next(i for i, m in enumerate(msgs)
                      if HEADER in (m.get("content") or ""))
    assert idx_recall > 0
    # 在 task 卡**之前**（时间事实 → 想起的事 → 目标层, 末位离生成最近）
    idx_card = next(i for i, m in enumerate(msgs)
                    if "本回合任务" in (m.get("content") or ""))
    assert idx_recall < idx_card, (idx_recall, idx_card)
    # 一轮里**只出现一次**（重复注入 = 白花一遍 token, 还会读成"两件事"）
    assert _joined(llm).count(HEADER) == 1
    print("    N5: 落点在动态尾（system 干净 / 在 task 卡之前 / 只出现一次）")


def test_query_is_this_player_line(tmp_path):
    """⭐ 查询 = **本轮玩家输入** —— 换一句话, 浮上来的就是另一条。

    这是"按当前对话召回"的**可观测**判据（比 spy 调用参数更强: 它同时钉住了
    "查询取的是这一句"和"召回结果真的随它变"）。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定", tags=("杂草",))
    _seed(tmp_path, "和老师去吃了高级料理", title="第一顿高级料理", tags=("料理",))

    eng.agent_turn("我今天又去杂草屋那边了")
    first = _joined(llm)
    assert "《苔藓的约定》" in first and "《第一顿高级料理》" not in first

    eng.agent_turn("上次那家餐厅的料理真好吃")
    second = _joined(llm)
    assert "《第一顿高级料理》" in second and "《苔藓的约定》" not in second
    print("    N5: 查询随玩家这一句变（杂草屋 → 苔藓 / 料理 → 高级料理）")


def test_recall_note_silent_when_nothing_matches(tmp_path):
    """宁缺勿错: 空库 / 一条都不像 ⇒ **不注**（不返回一个空段头）。"""
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    eng.agent_turn("今天天气不错")                    # 空库
    assert HEADER not in _joined(llm)

    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定", tags=("杂草",))
    eng.agent_turn("你昨天睡得好吗")                  # 有库, 但这句话跟它不像
    assert HEADER not in _joined(llm), _joined(llm)[-400:]
    print("    N5: 无命中 → 不注（宁缺勿错）")


def test_recall_query_is_truncated(tmp_path):
    """查询截断到 `RECALL_QUERY_CHARS` —— 长消息的后半段不进检索。"""
    from core.mmt import engine as engine_mod
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定", tags=("杂草",))
    # 关键词**落在截断点之后** ⇒ 不该被召回（钉子: 截断真的发生了）
    eng.agent_turn("啊" * engine_mod.RECALL_QUERY_CHARS + "杂草屋")
    assert HEADER not in _joined(llm)
    # 关键词在最前面 ⇒ 召回
    eng.agent_turn("杂草屋" + "啊" * engine_mod.RECALL_QUERY_CHARS)
    assert HEADER in _joined(llm)
    print(f"    N5: 查询截断到 {engine_mod.RECALL_QUERY_CHARS} 字")


def test_recall_uses_the_now_of_the_turn(tmp_path):
    """时间短语来自**本轮的 `now`**（与时间注记共用同一个"现在"）。"""
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定",
          tags=("杂草",), ts="2026-09-20T10:00:00")
    eng.agent_turn("我今天又去杂草屋那边了",
                   now=datetime.fromisoformat("2026-09-21T10:00:00"))
    assert "〔《苔藓的约定》｜昨天｜9/20〕" in _joined(llm), _joined(llm)[-400:]
    print("    N5: 短语用本轮 now（昨天）")
