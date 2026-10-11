# -*- coding: utf-8 -*-
"""`mmt_look` —— 第 1 件: **注册 + parse + 独占 + 接线 + 占位执行器**（2026-10-08）。

它一个一个落, 所以这个文件也**一节一节长**: 本件只有"她能不能用这个动作、用了会怎样"。
真检索（三级解析 + `find` + 放宽 + 三句话）在下一件。

守门:
  ① **注册与契约**: `mmt_look` 在注册表里、有 `payload_schema`、外壳字段与别的 MMT 动作一致
  ② **parse 只做结构白名单**: clue/when 至少一个; 线索编译不过 ⇒ 当场拒（可归因, 不静默）
  ③ ⭐ **payload 里只有字符串** —— 它会进 `TurnResult` / trace / 前端 JSON;
     塞一个编译好的 `Clue` 进去, 序列化那一层迟早出事（本件真 `json.dumps` 一次钉住）
  ④ **独占**: **唯一操作行**（trigger 式 —— 话可前置）; ⚠️ 想起行也**不算**（同 N5b 口径）
  ⑤ **接线**: `look` 在 `QUERY_ACTIONS` 里（查完回灌 + 继续这一轮）, ⛔ `trigger` 不在
  ⑥ ⭐ **占位执行器明说"未接线"**（注册表就是她的开关: 注册了她就能吐这一行,
     执行器缺席会走成"未知执行动作"⇒ 硬问题 + 整批不交付 —— 真机上表现为"她一句话没说"）
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contract import (APPROVAL_AUTO, DOMAIN_MMT, AgentAction,   # noqa: E402
                      ContractError)
from core.brain import WikiStoreV2, make_node                   # noqa: E402
from core.brain.read.render import (LOOK_EMPTY,                # noqa: E402
                                    LOOK_EMPTY_TIME, LOOK_FUTURE, look_empty)
from core.mmt.mmt_actions import (MMT_RUNTIME_FIELDS,           # noqa: E402
                                  build_mmt_registry, parse_mmt_look)
from core.mmt.mmt_check import (ACTION_LOOK, ACTION_TRIGGER,    # noqa: E402
                                QUERY_ACTIONS, WHOLE_TURN_ACTIONS,
                                MmtIssueCode, check_turn)
from core.mmt.mmt_executor import MmtExecError, MmtExecutor     # noqa: E402
from core.mmt.mmt_lines import MmtLine                          # noqa: E402
from core.mmt.engine import MomoTalkEngine                      # noqa: E402
from core.session.store import SessionStore                     # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CHARACTER = "igusa_haruka"


def _text(s="话"):
    return MmtLine(kind="text", text=s)


def _look(**payload):
    return MmtLine(kind="action", action=ACTION_LOOK, payload=payload)


def _codes(issues):
    return [i.code for i in issues]


def _action(**payload) -> AgentAction:
    return AgentAction(action=ACTION_LOOK, domain=DOMAIN_MMT,
                       approval=APPROVAL_AUTO, payload=payload)


# ---------------------------------------------------------------------------
# ① 注册与契约
# ---------------------------------------------------------------------------

def test_registry_registers_look_with_its_field_doc():
    reg = build_mmt_registry()
    assert ACTION_LOOK in reg.action_names(), reg.action_names()
    spec = reg.spec(ACTION_LOOK)
    assert spec.prompt_fields == MMT_RUNTIME_FIELDS          # 外壳同其他 MMT 动作
    assert "clue" in spec.payload_schema and "when" in spec.payload_schema
    assert "&&" in spec.payload_schema                       # 运算符的形态要看见
    print("    注册: mmt_look 在表里, 字段说明含 clue / when / 运算符")


# ---------------------------------------------------------------------------
# ② parse（结构白名单）
# ---------------------------------------------------------------------------

def test_parse_accepts_clue_when_or_both_and_strips():
    assert parse_mmt_look({"clue": " 苔藓 && 杂草 "}) == {"clue": "苔藓 && 杂草", "when": ""}
    assert parse_mmt_look({"when": " 上周 "}) == {"clue": "", "when": "上周"}
    assert parse_mmt_look({"clue": "苔藓", "when": "last 1 week"}) == \
        {"clue": "苔藓", "when": "last 1 week"}
    print("    parse: clue / when / 两个都给 都收（并去首尾空白）")


def test_parse_output_is_json_safe_strings():
    """⭐ payload 里**只有字符串** —— 真序列化一次, 编译好的 `Clue` 会在这儿炸。"""
    out = parse_mmt_look({"clue": "(苔藓 || 杂草) && 老师", "when": "上周"})
    assert all(isinstance(v, str) for v in out.values()), out
    json.dumps(out, ensure_ascii=False)                      # 不抛 = 前端/TurnResult 安全
    print("    parse: 返回值 JSON 安全（⛔ 不塞自定义对象）")


def test_parse_rejects_bad_input():
    for bad in ({}, {"clue": "   "}, {"clue": "  ", "when": ""},
                {"clue": 123}, {"when": ["上周"]},
                {"clue": "苔藓 \\d"}, {"clue": "(苔藓"}, {"clue": "苔藓 &"}):
        with pytest.raises(ContractError):
            parse_mmt_look(bad)
    print("    parse: 空 / 非字符串 / 正则味线索 / 括号不闭合 ⇒ 当场拒")


# ---------------------------------------------------------------------------
# ④ 独占（**trigger 式**: 唯一操作行 + 放最后一行 —— 2026-10-08 用户裁）
# ---------------------------------------------------------------------------

def test_look_is_the_only_action_but_words_may_come_first():
    """⭐ `look` 与 `inspect` **不同款**: 先说一句"唔……我找找看"再翻是自然的 ——
    照 `inspect` 判"整轮只有它一条行"会**逼她中断**（话与翻二选一）。

    ⇒ 判据 = **唯一操作行**（同 `trigger`）; 话写在它**前面**合法。
    ⚠️ **"放在最后一行"只教不判**（只写在契约与规则书里）: 写在它后面只是写法差,
    判成硬问题会白跑一次续写 —— 所以下面那条 `[*alone, _text(...)]` 必须**放行**。
    """
    alone = [_look(clue="苔藓")]
    assert check_turn(alone) == [], _codes(check_turn(alone))
    assert check_turn([_text("唔……我找找看"), *alone]) == []     # ⭐ 话可前置（新口径）
    assert check_turn([*alone, _text("……")]) == []              # 写在后面也不判（只建议）
    for bad in ([*alone, _look(when="上周")],                    # 它自己重复了
                [*alone, MmtLine(kind="action", action="mmt_send_media",
                                 payload={"image": "x"})],       # 夹别的操作行
                [MmtLine(kind="action", action=ACTION_TRIGGER,
                         payload={"chapter_title": "某某某某"}), *alone]):
        issues = check_turn(bad)
        assert MmtIssueCode.EXCLUSIVE_VIOLATION in _codes(issues), issues
        assert issues[0].hard
    print("    check: look —— 唯一操作行（话可前置）; 夹别的操作行/重复 ⇒ 硬违规")


def test_noticed_row_does_not_break_look_exclusivity():
    """⚠️ 同 N5b 口径: **想起行是账目不是内容** —— 与 `look` 同轮顺手记一笔是允许的。"""
    rows = [_look(clue="苔藓"), MmtLine(kind="noticed", noticed="苔藓的约定")]
    assert check_turn(rows) == [], _codes(check_turn(rows))
    assert check_turn([_text("唔……我找找看"), *rows]) == []      # 话 + 账目 + 翻, 都合法
    assert MmtIssueCode.EXCLUSIVE_VIOLATION in _codes(
        check_turn([*rows, MmtLine(kind="action", action="mmt_send_media",
                                   payload={"image": "x"})]))


# ---------------------------------------------------------------------------
# ⑤ 接线
# ---------------------------------------------------------------------------

def test_query_actions_cover_look_but_never_trigger():
    """⭐ 查完**回灌 + 继续这一轮**的族; ⛔ `trigger` 是模式切换, 不在内。"""
    assert ACTION_LOOK in QUERY_ACTIONS
    assert ACTION_LOOK in WHOLE_TURN_ACTIONS          # 独占 ⇒ 必须整轮可见才判/执行
    assert ACTION_TRIGGER not in QUERY_ACTIONS


# ---------------------------------------------------------------------------
# ⑥ 占位执行器 + 端到端接线（一轮里两次主调用）
# ---------------------------------------------------------------------------

def test_executor_needs_the_look_hook(tmp_path):
    """⚠️ `look_fn` 缺席 ⇒ **明确报错**（⛔ 不静默返回空: 那会让她以为"翻过了、没有"）。"""
    ex = MmtExecutor(tmp_path)
    ex.set_current_character(object())               # 有没有会话只判"是不是 None"
    with pytest.raises(MmtExecError, match="未接线"):
        ex.execute(_action(clue="苔藓"))
    ex.set_current_character(None)
    with pytest.raises(MmtExecError):
        ex.execute(_action(clue="苔藓"))
    print("    接线: 没注入 look_fn ⇒ MmtExecError（硬问题, 不伪装成「没翻到」）")


def test_executor_passes_clue_and_when_through(tmp_path):
    """执行器只管**透传**（取数在 engine）—— 用假回调钉住参数。"""
    seen: list[tuple[str, str]] = []
    ex = MmtExecutor(tmp_path, look_fn=lambda clue, when: seen.append((clue, when)) or "段")
    ex.set_current_character(object())
    res = ex.execute(_action(clue="苔藓 && 杂草", when="上周"))
    assert res.ok and res.message == "段" and seen == [("苔藓 && 杂草", "上周")], seen


class _ScriptedLLM:
    """第一次调用给一条 `look` 行, 之后正常说话（模拟"查完接着说"）。"""

    def __init__(self):
        self.snapshots: list[list[dict]] = []
        self.replies = ['{"action": "mmt_look", "payload": {"clue": "苔藓"}}',
                        '{"text": "……嗯，我想起来了"}',
                        '{"text": "（备用）"}']

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        return self.replies[min(len(self.snapshots) - 1, len(self.replies) - 1)]


# ---------------------------------------------------------------------------
# S1 · 三级解析（真执行器）
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 8, 21, 0, tzinfo=timezone(timedelta(hours=8)))


def _seed(tmp_path, text, *, title="", ts="", verbatim=""):
    """写一条 episode 到真机同款位置（引擎是另开一个 store 读的, 所以要 save）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    st.add(make_node("episode", text=text, title=title, ts=ts, verbatim=verbatim,
                     significance=0.6, event_seq=[1]))
    st.save()


def _engine(tmp_path, llm):
    store = SessionStore(data_root=tmp_path)
    eng = MomoTalkEngine(ROOT / "config" / "characters", llm, store=store)
    name = eng.start_session(CHARACTER)
    root = store.create(CHARACTER, name)
    eng.attach_session(root.session_id)
    # ⭐ **钉住"现在"**（同 `when.parse_when(now=…)` 的纪律: 模块不许偷读壁钟, 测试也不许）。
    # ⚠️ 直接调 `_look_result`（不起 LLM）时 `agent_turn` 没跑过 ⇒ `_turn_now` 是空的,
    # 它会**回落 `datetime.now()`** —— 于是 `上周` 这类相对时间随真实日期漂。
    # 真踩到过: `test_look_ledger_and_trace` 的种子在 09-30、查 `上周`,
    # 2026-10-08 那天在窗内（绿），10-12 就出了窗（红）—— **一条会过期的时间炸弹**。
    eng._turn_now = NOW
    return eng


def _look_text(eng) -> str:
    """直接调执行体（不起 LLM）—— 单元级验三级解析。"""
    return eng._look_result("苔藓", "")


def test_level1_title_hit_is_exact(tmp_path):
    """①级: 线索是**单个纯字面** ⇒ 先当**标题**精确查（一步到位）。"""
    _seed(tmp_path, "瓦片缝里的苔藓长得很好", title="瓦片缝里的苔藓", ts="2026-09-26T10:00:00")
    eng = _engine(tmp_path, _ScriptedLLM())
    seg = eng._look_result("瓦片缝里的苔藓", "")
    assert "【你翻到的" in seg and "《瓦片缝里的苔藓》" in seg, seg
    assert "1 条" in seg, seg
    print("    ①级: 标题精确查（`normalize_title` 剥壳 ⇒ 抄整段元信息也认）")


def test_level1_still_obeys_when(tmp_path):
    """⭐ ①级**也要过 `when`** —— 否则"上周的《某条》"会把两周前那条当命中。"""
    _seed(tmp_path, "很久以前的事", title="瓦片缝里的苔藓", ts="2026-09-01T10:00:00")
    eng = _engine(tmp_path, _ScriptedLLM())
    seg = eng._look_result("瓦片缝里的苔藓", "2026/09/25")
    assert "《瓦片缝里的苔藓》" not in seg, seg          # 标题在窗外 ⇒ 不算命中
    print("    ①级: 标题命中也要满足时间（锚是 AND）")


def test_level2_text_search_and_cap(tmp_path):
    """②级: 正文检索**全量**（⛔ 不 top-k）; 展示按 **cap 5** 截 + 如实报"还有几条"。"""
    for i in range(8):
        _seed(tmp_path, f"苔藓的事第 {i} 件", title=f"苔藓 {i}",
              ts=f"2026-10-0{i % 8 + 1}T10:00:00")
    eng = _engine(tmp_path, _ScriptedLLM())
    seg = eng._look_result("苔藓", "")
    assert "8 条" in seg, seg
    assert seg.count("\n- ") == 5, seg.count("\n- ")     # cap = 5
    assert "还有 3 条同类的事" in seg, seg
    print("    ②级: 全量命中 8 · 只摆 5 · 明说还有 3")


def test_level3_widening_is_for_points_only(tmp_path):
    """③级: **单点**窗口 `exact` 空 ⇒ 用 `wide`(±2 天) 再查一次, 并如实报告边界。

    ⭐ 同时钉住用户 2026-10-08 的裁定: **周期不放宽**（`last 1 week` = 7 天, 它本来就是
    宽的; 再扩没有信息量）—— 所以 `上周` 查空就是"没想起来", 不会去翻前后。
    """
    _seed(tmp_path, "三周前的那件事", title="很久以前", ts="2026-09-17T10:00:00")
    eng = _engine(tmp_path, _ScriptedLLM())
    # 周期窗口不放宽 ⇒ 空就是空
    assert eng._look_result("很久以前", "last 1 week") == LOOK_EMPTY
    # 单点窗口 + ±2 天 ⇒ 够得到（9/15 ±2 = 9/13~9/17）
    seg = eng._look_result("很久以前", "2026/09/15")
    assert "前后那阵子有" in seg and "《很久以前》" in seg, seg
    print("    ③级: 单点放宽命中（并说明「那阵子没有」）; 周期窗口**不放宽**")


def test_exact_window_wins_over_the_widened_one(tmp_path):
    """⭐ **`wide` 不许替代 `exact`**: 窗口内有货时, 就**只给窗口内的**。

    否则"9/15 那天有 1 条"会变成"9/13~9/17 一共 2 条" —— **静默换掉她问的范围**。
    """
    _seed(tmp_path, "窗口里的事", title="正日子", ts="2026-09-15T10:00:00")
    _seed(tmp_path, "窗口外但在放宽范围内", title="隔壁那天", ts="2026-09-17T10:00:00")
    eng = _engine(tmp_path, _ScriptedLLM())
    seg = eng._look_result("窗口", "2026/09/15")
    assert "《正日子》" in seg and "《隔壁那天》" not in seg, seg
    assert "前后那阵子" not in seg, seg                  # 没放宽 ⇒ 不许说放宽的话
    print("    ③级: exact 有货 ⇒ 不放宽（range 是她问的, 不许静默扩大）")


def test_time_failures_are_human_and_never_widen(tmp_path):
    """⭐ 三种失败分得开, 且都**不破墙**（她的内心话, 没有"格式/引擎"这类词）。"""
    _seed(tmp_path, "苔藓的事", title="苔藓的约定", ts="2026-09-26T10:00:00")
    eng = _engine(tmp_path, _ScriptedLLM())
    bad = eng._look_result("苔藓", "下周八")
    assert bad == LOOK_EMPTY_TIME, bad                   # 认不出 ⇒ 不查（不静默放宽）
    assert "格式" not in bad and "引擎" not in bad
    assert eng._look_result("苔藓", "2027/01/01") == LOOK_FUTURE
    assert eng._look_result("找不到的词", "") == LOOK_EMPTY
    print("    失败: 时间认不出 / 落在将来 / 查了没有 —— 三句各归各的")


def test_no_store_degrades_to_a_human_sentence(tmp_path, caplog):
    """⚠️ 没有 store（CLI/实验模式）⇒ **不伪装成硬错误**（同 P19 的宁缺勿错）。

    ⚠️ 判据里的**"没有 warning"**不是装饰: 这一格与"异常被外层兜住"在返回值上
    完全一样, 差别只在**它是正常降级还是吞了一次崩溃** —— 后者会每轮刷一条警告。
    ⭐ 而且**它不算"她翻空了"**: 引擎的配置问题不该记到她头上（计数保持 0）。
    """
    eng = MomoTalkEngine(ROOT / "config" / "characters", _ScriptedLLM())
    eng.start_session(CHARACTER)
    with caplog.at_level("WARNING", logger="core.mmt.engine"):
        assert eng._look_result("苔藓", "") == LOOK_EMPTY
    assert not [r for r in caplog.records if r.levelname == "WARNING"], \
        [r.getMessage() for r in caplog.records]
    assert eng._look_miss == 0, "无 store 不计入「翻空了几次」"


def test_empty_look_counts_up_and_a_hit_resets(tmp_path):
    """⭐ **翻空了要数次数, 命中就归零**（用户 2026-10-08 裁）。

    为什么由引擎数: 云端 LLM 是**无状态函数**, 数不清自己翻过几次 —— 不把次数告诉它,
    它就可能换个词一直查（轮内被 `MAX_STEPS=6` 截断, 而截断的形态是**整轮失败**）。
    ⛔ 不设硬闸（用户: 相信她有特殊理由, "连续 3 次"本身也可能被误判）⇒ 这里只钉
    **文案分档**与**计数口径**。
    """
    _seed(tmp_path, "苔藓的事", title="苔藓的约定", ts="2026-09-30T10:00:00")
    eng = _engine(tmp_path, _ScriptedLLM())

    assert eng._look_result("找不到的词", "") == LOOK_EMPTY        # 第 1 次: 原句不动
    assert eng._look_miss == 1
    again = eng._look_result("找不到的词", "")
    assert again == look_empty(2) and "还是没想起来" in again       # 第 2 次: 给回忆方法
    assert "换个说法" in again and "不写时间" in again
    third = eng._look_result("找不到的词", "")
    assert third == look_empty(3) and "连着 3 次" in third          # ≥3 次: 劝她停下

    # ⭐ 命中 ⇒ **归零**（下一次空手又从第 1 档算起）
    assert "苔藓的约定" in eng._look_result("苔藓", "")
    assert eng._look_miss == 0
    assert eng._look_result("找不到的词", "") == LOOK_EMPTY

    # ⚠️ 三种"不是记忆里没有"的 **不累加**: 时间认不出 / 落在将来 / （无 store 见上一条）
    assert eng._look_result("苔藓", "下周八") == LOOK_EMPTY_TIME
    assert eng._look_result("苔藓", "2027/01/01") == LOOK_FUTURE
    assert eng._look_miss == 1, "时间类失败不该记成「翻空」"
    print("    look: 空手分档 1/2/≥3 + 命中归零 + 时间类不计数")


def test_look_empty_copy_never_breaks_the_fourth_wall():
    """⛔ 四句话（含两档新的）**零技术词** —— 她是"想不起来", 不是"解析失败"。"""
    for miss in (1, 2, 3, 9):
        line = look_empty(miss)
        for bad in ("引擎", "格式", "解析", "参数", "错误", "JSON", "字段"):
            assert bad not in line, (miss, bad, line)
    assert look_empty(0) == LOOK_EMPTY and look_empty(1) == LOOK_EMPTY
    assert "9 次" in look_empty(9)                     # 数字如实报, 不封顶
    print("    look: 走空文案不破墙（零技术词）")


def test_look_ledger_and_trace(tmp_path, caplog):
    """台账可 grep: 查了什么 / 命中几条 / 用了 exact 还是 wide / 摆了谁（标题）。"""
    _seed(tmp_path, "苔藓的事", title="苔藓的约定", ts="2026-09-30T10:00:00")  # 上周内
    eng = _engine(tmp_path, _ScriptedLLM())
    with caplog.at_level("INFO", logger="core.mmt.engine"):
        eng._look_result("苔藓", "上周")
    # ⚠️ 只挑**引擎自己**那条（`find` 也会打一条含 `cand=` 的 INFO 行）——
    #    平时它被 logger 级别挡掉, 但**跨文件跑**时别处抬过全局级别, 它就会插到前面
    #    ⇒ 不筛 logger 的话"全量跑红、单独跑绿"（真踩过）。
    line = next(r.getMessage() for r in caplog.records
                if r.name == "core.mmt.engine" and "cand=" in r.getMessage())
    assert "clue='苔藓'" in line and "cand=1" in line and "widened=False" in line, line
    assert "titles=苔藓的约定" in line, line
    print("    台账:", line)


# ---------------------------------------------------------------------------
# ⑥ 端到端接线（一轮里两次主调用）
# ---------------------------------------------------------------------------

def test_look_round_is_fed_back_and_the_turn_continues(tmp_path):
    """⭐ **接线**: 她发一条 `look` ⇒ 引擎回灌 + **同一轮接着要一次**。"""
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定",
          ts="2026-09-26T10:00:00")
    llm = _ScriptedLLM()
    eng = _engine(tmp_path, llm)

    result = eng.agent_turn("我们上次说的那件事，你还记得吗", now=NOW)
    assert len(llm.snapshots) == 2, [len(s) for s in llm.snapshots]   # 一轮两次主调用
    joined = "\n".join((m.get("content") or "") for m in llm.snapshots[-1])
    assert "苔藓的约定" in joined                     # 真回灌（不是占位文案）
    assert llm.snapshots[-1][-1]["role"] == "user"   # `feedback()` 追加的是 **user**
    assert result.ok and "我想起来了" in result.reply  # 她接着说的话上了屏
    print("    look: ① 她发起 → ② 回灌真结果 → ③ 同一轮接着说（两次主调用）")


class _WordsThenLookLLM:
    """**先说话再翻**（新口径）: 第一次给"一句过渡话 + look 一行", 之后正常说话。"""

    def __init__(self):
        self.snapshots: list[list[dict]] = []
        self.replies = [
            '{"text": "唔……等一下，我找找看"}\n'
            '{"action": "mmt_look", "payload": {"clue": "苔藓"}}',
            '{"text": "……嗯，我想起来了"}',
        ]

    def chat(self, messages, **kw):
        self.snapshots.append([dict(m) for m in messages])
        return self.replies[min(len(self.snapshots) - 1, len(self.replies) - 1)]


def test_words_may_come_before_the_look(tmp_path):
    """⭐ **trigger 式独占**（2026-10-08 用户裁）: 先说一句"唔……我找找看"再翻 ——
    话照常上屏、`look` 照跑、结果照回灌、她接着把这一轮说完（**不再被逼中断**）。

    ⚠️ 判据落在"**话没有被丢掉**"上: 旧口径下这一轮判独占违规（话与翻二选一）;
    而**批式路径**（本用例的桩只有 `chat`）里 `plan` 攒着的话原本会随 `return` 静默
    消失 —— 所以这一条同时钉住"两条路径同形"。
    """
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定",
          ts="2026-09-26T10:00:00")
    llm = _WordsThenLookLLM()
    eng = _engine(tmp_path, llm)

    result = eng.agent_turn("我们上次说的那件事，你还记得吗", now=NOW)
    assert result.ok, result.error
    assert len(llm.snapshots) == 2, [len(s) for s in llm.snapshots]
    assert "我找找看" in result.reply            # ⭐ 翻之前那句上了屏（行序在前）
    assert "我想起来了" in result.reply          # 翻到之后接着说的话也上了屏
    joined = "\n".join((m.get("content") or "") for m in llm.snapshots[-1])
    assert "苔藓的约定" in joined                # 回灌的仍是真结果
    assert llm.snapshots[-1][-1]["role"] == "user"
    # 交付顺序 = 行序: 过渡话在前, 翻到之后的话在后
    assert result.reply.index("我找找看") < result.reply.index("我想起来了")
    print("    look: 先说话再翻 —— 话上屏 + 翻照跑 + 回灌 + 接着说（两次主调用）")


# ---------------------------------------------------------------------------
# ⑦ 规则书与契约不许漂（2026-10-08 立 —— 今天已经漂过两次）
# ---------------------------------------------------------------------------

RULES = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "momotalk_rules.md"


def test_rulebook_section_and_the_contract_say_the_same_thing():
    """⭐ **规则书那段【回忆】必须与输出契约同款**（示范才是形状的来源 —— 契约/规则书
    两处说法强度不一, 模型只照抄更强的那一处）。

    钉三件事:
      · 专段存在, 而且「操作使用时机」那一行**指向它**（⛔ 别只留个动作名）;
      · 专段说的独占口径 = **唯一操作行 + 放最后一行**（与 `check_turn` 的判据一致）;
      · ⛔ 退役的动作名与它那套"整轮只有它一条行"的口径**一个字都不许留**
        （D 笔把 `mmt_inspect_character` 整条退了, 悬空指令会让她去调一个不存在的动作）。
    """
    text = RULES.read_text(encoding="utf-8")
    assert "【回忆" in text, "规则书里必须有【回忆】专段"
    assert "见下方【回忆】专段" in text, "「操作使用时机」那一行要指向专段"
    seg = text[text.index("【回忆"):]
    seg = seg[:seg.index("【想起的事")] if "【想起的事" in seg else seg
    assert "唯一的操作行" in seg and "最后一行" in seg, seg
    assert "mmt_look" in seg and "不算失败" in seg, seg
    # ⛔ 退役动作与旧口径不许留
    assert "mmt_inspect_character" not in text
    assert "整轮只有它一条行" not in text
    assert "单独一轮" not in text
    print("    look: 规则书【回忆】与契约同款（唯一操作行 + 最后一行; 无退役动作残留）")
