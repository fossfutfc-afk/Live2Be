"""`note` 事件类型的**登记与隔离**（链路 ① 第一步, 2026-09-23）。

`note` = 她自己的备忘录**操作**（`DESIGN_GRAPH_V4` §3.2）: 成品是 `soul/notes.json`
（折叠出来的派生缓存）, 事件流里那份是 append-only 的操作本身 —— 加一条 / 划掉一条 /
整体重写。它是**账目不是剧情**:

    · 不进 LLM 上下文（`render_events` / `window_messages`）
    · 不进 digest 的时间线（`render_timeline` —— 那是 Round A 的**唯一输入**）
    · 不参与"本段互动 max seq"（好感事件的幂等键）

⚠️ 登记不是可选项: `Event.from_dict` 对**没进 `EVENT_TYPES` 的 type 直接返回 None**
⇒ 事件写得进磁盘、读回来是空气, 且**一声不响**。本文件把这条也钉住。

范围: 只测**事件层**。折叠（`notes.json`）/ 渲染 / 注入 / 全景轮是后续步骤。
"""
import sys
from pathlib import Path

from core.brain.store import WikiStoreV2
from core.digest.pipeline import digest_segment
from core.mmt.engine import _interact_max
from core.session import make_event
from core.session.events import (
    EVENT_TYPES,
    N_ADD,
    N_CLOSE,
    N_UPDATE,
    NON_CONTENT_TYPES,
    NOTE_SUBTYPES,
    TYPE_NOTE,
    Event,
    is_content_event,
)
from core.session.renderer import render_events, render_timeline, window_messages
from llm import task_labels as T
from tests import stub_tasks

ROOT = Path(__file__).resolve().parent.parent.parent
PROD_DIRS = ("core", "webgui", "cli", "contract", "llm")


class FakeLLM:
    """按序吐预置响应; **不给响应 → 一旦被调用就炸**（"不该有调用"这种断言用它）。"""

    def __init__(self, *responses, split=None):
        self.responses = list(responses)
        self.calls: list = []
        self.split = split                      # 显式骨架（3b-2: 空 episodes ⇒ 空骨架）

    def chat(self, messages, **kw):
        task = kw.get("task")
        first = (self.responses[0] if self.responses else None)
        if task == T.DIGEST_SPLIT:
            if self.split is not None:
                return self.split
            if isinstance(first, dict):
                # ⭐ R0: 照搬 R1 那份应答里的区间（**不消耗队列** —— 它读的是同一份剧本）
                return stub_tasks.split_for_scripted(messages, first)
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("这条窗口不该产生 LLM 调用")
        return self.responses.pop(0)


def _note(seq, sub=N_ADD, payload=None):
    e = make_event(TYPE_NOTE, sub,
                   payload or {"id": "n1", "text": "周六模型店", "refs": ["m0009"]})
    e.seq = seq
    return e


def _mmt(seq, player="老师好", reply="啊、老师好……"):
    e = make_event("mmt", "chat", {"player": player, "reply": reply})
    e.seq = seq
    return e


# ---------------------------------------------------------------------------
# 登记: 没登记的 type 会被静默丢掉
# ---------------------------------------------------------------------------

def test_note_type_is_registered_and_roundtrips():
    assert TYPE_NOTE in EVENT_TYPES
    assert NOTE_SUBTYPES == (N_ADD, N_CLOSE, N_UPDATE)
    # ⛔ `retire`（2026-10-05 与 `close` 合并）与 `rewrite`（`on_mind` 退役）**只在旧档**
    assert "retire" not in NOTE_SUBTYPES and "rewrite" not in NOTE_SUBTYPES

    e = _note(7, sub=N_CLOSE)
    back = Event.from_dict(e.to_dict())
    assert back is not None
    assert (back.type, back.subtype, back.seq) == (TYPE_NOTE, N_CLOSE, 7)
    assert back.payload["text"] == "周六模型店"

    # 反证（"必须登记"的理由本身）: 换成一个没登记的 type → 整条被丢掉
    assert Event.from_dict(dict(e.to_dict(), type="memo")) is None


def test_note_is_not_a_content_event():
    assert not is_content_event(_note(1))
    assert not is_content_event(make_event("marker", "vn_enter", {}))
    assert not is_content_event(make_event("affection", "digest", {"delta": 1}))
    assert is_content_event(_mmt(2))
    # ⭐ N5b（2026-09-29）: `noticed`（她顺手记的那一笔账）也是账目, 不是剧情 ——
    # 一处登记 ⇒ 三处自动生效（不进历史 / 不进 digest 时间线 / 不上前端气泡）。
    assert not is_content_event(make_event("noticed", "noticed",
                                           {"title": "苔藓", "hit": "m0001"}))
    assert NON_CONTENT_TYPES == ("affection", TYPE_NOTE, "noticed")


# ---------------------------------------------------------------------------
# 隔离: 三条读路径都对 note 无感（输出与"没有这条事件"逐字相同）
# ---------------------------------------------------------------------------

def test_note_never_enters_context_window():
    without = [_mmt(1), _mmt(3, "在吗", "在的")]
    with_note = [_mmt(1), _note(2), _mmt(3, "在吗", "在的")]

    msgs = render_events(with_note)
    assert msgs == render_events(without)                 # 上下文字节级不变
    assert window_messages(with_note) == window_messages(without)
    assert all("模型店" not in str(m["content"]) for m in msgs)


def test_note_never_enters_timeline():
    without = [_mmt(1)]
    assert render_timeline([_mmt(1), _note(2)]) == render_timeline(without)
    assert "模型店" not in render_timeline([_mmt(1), _note(2)])

    # 同一处顺手挡掉的另一类账目: 好感事件此前会被兜底标签印成 `【affection】`
    aff = make_event("affection", "digest", {"delta": 3, "digested_seq": 1})
    aff.seq = 3
    tl = render_timeline([_mmt(1), aff])
    assert "affection" not in tl


def test_interact_max_ignores_note_and_affection():
    """幂等键必须落在**内容**事件的 seq 上。"""
    aff = make_event("affection", "digest", {"delta": 1})
    aff.seq = 9
    assert _interact_max([_mmt(3), _note(4), aff], 0) == 3
    # 下界照旧: 水位之内的事件不算
    assert _interact_max([_mmt(3), _note(4)], 3) == 0


# ---------------------------------------------------------------------------
# digest: 只有账目的窗口 = 0 次 LLM 调用
# ---------------------------------------------------------------------------

def test_note_only_window_digests_to_nothing(tmp_path):
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    llm = FakeLLM()                                       # 一被调用就炸
    res = digest_segment(st, llm, [_note(1), _note(2, sub=N_CLOSE)])

    assert res.ok and res.llm_calls == 0
    assert llm.calls == []
    assert st.digested_seq == 0                           # 水位不动（无内容可消化）


def test_note_in_window_does_not_disturb_digest(tmp_path):
    """同窗口混着一条 note: 消化照常, **水位越过账目**（否则每个 digest 都重扫它）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    # ⚠️ 3b-2: 空 episodes ⇒ 桩派生空骨架 ⇒ 链条在 R0 就停。本用例测的是
    # "**账目事件不进食料**" ⇒ 显式给一条骨架把链条放过去。
    llm = FakeLLM({"episodes": []},
                  {"relations": []},
                  split={"segments": [{"span": [3, 3],
                                       "abstract": "这一段"}]})
    res = digest_segment(st, llm, [_mmt(3), _note(4, sub=N_CLOSE)])

    assert res.ok, res.errors
    assert res.llm_calls == 3                             # R0 + 内容照常走完两轮
    assert st.digested_seq == 4


# ---------------------------------------------------------------------------
# 守门: 判据只有一处, 不许在别处再抄一份
# ---------------------------------------------------------------------------

def test_content_filter_is_not_reimplemented_elsewhere():
    """静态守门 —— "非内容事件"的例外只该出现在 `NON_CONTENT_TYPES` 里。

    抓的形状 = **同一行里既有 `is_marker` 又有 `"affection"`**（那就是老写法的指纹）。
    注意别抓 `core/affection/affection_calc.py` 那种"只挑 affection"的相反判据 ——
    它不含 `is_marker`, 所以不在本守门的射程内。
    """
    bad: list[str] = []
    for d in PROD_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "is_marker" in line and '"affection"' in line:
                    bad.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not bad, "内容事件判据被抄了第二份（应改用 events.is_content_event）:\n" + \
                    "\n".join(bad)
