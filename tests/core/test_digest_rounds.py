# -*- coding: utf-8 -*-
"""轮次表守门（`core/digest/rounds.py`, 2026-09-29 节点 C）。

它钉住**六件事** —— 都是"不钉就会烂掉"的约定:

  ① **结果字段分类齐全**: `DigestResult` 上每个字段要么被某轮声明（⇒ 回滚时清空）,
     要么在 `COMMIT_ONLY` 里（调用路径的记录 / 提交时才赋值）。**加字段忘了归类 → 这里红**
     —— 那正是"手抄清单"时代的病根（`notes_warnings` 漏了很久）。
  ② **`writes` 里的名字真实存在**: 节点面查 `nodes.BrainNode` 的字段 · `edge` 查
     `graph.REL_*` · `note` 查 `notes.SLOT_*`。表里写错一个字段名 = 表在骗人。
  ③ **LLM 四件套同生共死**: `label` / `prompt` / `phase` / `parse` 要么都有, 要么都没有
     （只有 `akin` 是零 LLM 的一步）; prompt 文件必须在盘上; 标签必须在词表里。
  ④ **料与 exec 一一对应**: 表里每一步都真的被 `pipeline` 用 `cur.enter(key)` 走过
     （没走 = 表里挂着一步死步骤; 代码里 enter 了表里没有的 key = 表漏了）。
  ⑤ **只有一步自带快照**（分群, 而且是最后一步）—— 别的步骤失败必须连累整段。
  ⑥ **游标不许回头**（顺序的真源是表, 不是语句先后）。

运行: python -m pytest tests/core/test_digest_rounds.py
"""
import dataclasses
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain import graph, notes
from core.brain.nodes import KINDS, BrainNode
from core.digest import rounds as R
from core.digest.pipeline import DigestResult, digest_segment
from core.brain import WikiStoreV2
from core.digest.rounds import Cursor
from core.brain.entities import ensure_entities
from core.session import make_event
from llm import task_labels as T  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE = ROOT / "core" / "digest" / "pipeline.py"
MATERIAL = ROOT / "core" / "digest" / "material.py"

_NODE_FIELDS = {f.name for f in dataclasses.fields(BrainNode)}
_RELS = {v for k, v in vars(graph).items() if k.startswith("REL_")}
_SLOTS = {v for k, v in vars(notes).items() if k.startswith("SLOT_")}


# ---------------------------------------------------------------------------
# ① 结果字段分类齐全（加字段忘了归类 → 红）
# ---------------------------------------------------------------------------

def test_every_result_field_is_classified():
    """`DigestResult` 的每个字段: 要么某轮声明（回滚清它）, 要么在 `COMMIT_ONLY` 里。"""
    declared = set(R.RESULT_FIELDS) | set(R.COMMIT_ONLY)
    actual = {f.name for f in dataclasses.fields(DigestResult)}
    assert declared == actual, (
        f"没归类的字段: {sorted(actual - declared)}（要么写进某一轮的 result_fields, "
        f"要么加进 rounds.COMMIT_ONLY）\n"
        f"表里有而 dataclass 上没有: {sorted(declared - actual)}")
    assert not (set(R.RESULT_FIELDS) & set(R.COMMIT_ONLY)), "同一字段不许既清又留"
    print(f"    {len(actual)} 个结果字段: 回滚清 {len(R.RESULT_FIELDS)} / 不动 "
          f"{len(R.COMMIT_ONLY)}")


def test_rollback_clears_exactly_the_tables_fields():
    """回滚清空**表里声明的那些**, 且**不碰**失败报告本身（`errors` / `llm_calls`）。"""
    res = DigestResult(ok=False)
    for name in R.RESULT_FIELDS:                       # 全部弄脏
        cur = getattr(res, name)
        setattr(res, name, 7 if isinstance(cur, int) else ["脏"])
    for name in R.COMMIT_ONLY:                         # 提交态与账目也摆上
        cur = getattr(res, name)
        if isinstance(cur, list):
            setattr(res, name, ["留"])
        elif isinstance(cur, int):
            setattr(res, name, 3)

    R.reset_result(res)

    dirty = {n: getattr(res, n) for n in R.RESULT_FIELDS if getattr(res, n) not in ([], 0)}
    assert not dirty, f"这些字段没被清干净: {dirty}"
    for name in R.COMMIT_ONLY:                         # 一个都不许动
        assert getattr(res, name) not in ([], 0), \
            f"{name} 是调用路径的记录/提交态, 回滚不许碰它"
    print(f"    回滚: 清 {list(R.RESULT_FIELDS)}; 保留 {list(R.COMMIT_ONLY)}")


# ---------------------------------------------------------------------------
# ② writes 里的名字得是真的
# ---------------------------------------------------------------------------

def test_writes_names_exist_in_the_graph():
    """`writes` 的每个字段名/边名/笔记槽都要能在真源里找到。"""
    bad: list[str] = []
    for spec in R.ROUNDS:
        for face, fields in spec.writes:
            if face not in R.FACES:
                bad.append(f"{spec.key}: 未知的面 {face!r}")
                continue
            source = (_NODE_FIELDS if face in R.NODE_FACES
                      else _RELS if face == R.EDGE_FACE else _SLOTS)
            for f in fields:
                if f not in source:
                    bad.append(f"{spec.key}: {face}.{f} 不存在"
                               f"（{face} 的真源里没有这个名字）")
    assert not bad, "轮次表写了不存在的字段:\n  " + "\n  ".join(bad)
    n = sum(len(fs) for s in R.ROUNDS for _f, fs in s.writes)
    print(f"    writes: {n} 个字段名全部对得上真源（节点字段/边/笔记槽）")


def test_writes_covers_the_edge_table():
    """表里出现的边是边表的一个子集（不许写出不存在的边名）。"""
    used = {f for s in R.ROUNDS for face, fs in s.writes
            if face == R.EDGE_FACE for f in fs}
    assert used <= _RELS, f"表里的边不在边表里: {sorted(used - _RELS)}"
    print(f"    表用到 {len(used)}/{len(_RELS)} 条边: {sorted(used)}")


# ---------------------------------------------------------------------------
# ③ LLM 四件套同生共死 + prompt 文件在 + 标签在词表里
# ---------------------------------------------------------------------------

def test_llm_rounds_are_complete():
    """`label` / `prompt` / `phase` / `parse` 要么都有, 要么都没有（只有 `akin` 都没有）。"""
    for spec in R.ROUNDS:
        quad = (spec.label, spec.prompt, spec.phase, spec.parse)
        filled = [bool(x) for x in quad]
        assert all(filled) or not any(filled), \
            f"{spec.key}: LLM 四件套（label/prompt/phase/parse）必须同生共死, 实得 {quad}"
    no_llm = [s.key for s in R.ROUNDS if not s.label]
    assert no_llm == ["akin"], f"零 LLM 的步只该有 akin, 实得 {no_llm}"
    print(f"    {len(R.ROUNDS)} 步: {len(R.ROUNDS) - 1} 次 LLM + 1 次零成本补边")


def test_prompt_files_exist():
    """表里写的 prompt 文件必须在盘上（改名忘了改表 → 红）。"""
    missing = [s.prompt for s in R.ROUNDS
               if s.prompt and not (ROOT / "llm" / "prompts" / f"{s.prompt}.md").is_file()]
    assert not missing, f"这些 prompt 文件不存在: {missing}"


def test_labels_are_in_the_vocabulary():
    """每步的 `label` 都要拼得出一个**词表里的** task 标签（桩与档位都按它走）。"""
    for spec in R.ROUNDS:
        if not spec.label:
            continue
        tag = T.digest_label(spec.label)
        assert tag in T.ALL, f"{spec.key}: 标签 {tag!r} 不在 llm/task_labels.ALL 里"
        assert tag in T.PROFILE_OF, f"{tag} 没有映射到档位形态"
    print("    标签: " + " / ".join(T.digest_label(s.label)
                                   for s in R.ROUNDS if s.label))


# ---------------------------------------------------------------------------
# ④ 料与执行一一对应
# ---------------------------------------------------------------------------

def test_every_round_is_entered_by_the_pipeline():
    """表里的每一步都要被 `pipeline` 真的走过（`cur.enter("<key>")`）—— 双向。"""
    src = PIPELINE.read_text(encoding="utf-8")
    entered = set(re.findall(r'cur\.enter\("([a-z_]+)"\)', src))
    keys = {s.key for s in R.ROUNDS}
    assert entered == keys, (
        f"表里挂着但没人跑: {sorted(keys - entered)}（死步骤）\n"
        f"代码里跑了但表里没有: {sorted(entered - keys)}（表漏了）")
    print(f"    pipeline 走全 {len(entered)} 步: {sorted(entered)}")


def test_material_sections_are_all_named():
    """每一步的料标题**非空**（零 LLM 的那步除外）—— 料是表的一半价值。"""
    for spec in R.ROUNDS:
        if spec.label:
            assert spec.material, f"{spec.key}: LLM 轮必须有料（谁吃什么 = 表的一半）"
            assert len(set(spec.material)) == len(spec.material), \
                f"{spec.key}: 料标题重复（`_sections_for` 是逐字比对的）"


def test_sections_check_is_wired():
    """料校对真的接在调用点上（否则表里的 `material` 只是注释）。

    三条: 拼料一律走 `_sections_for`(spec, …) · 不许再有裸 `_join_sections([` 的 LLM 输入 ·
    `_sections_for` 里那条 `AssertionError` 还在。
    ⚠️ 拆包后（2026-09-29）: **调用点**在 `pipeline.py`, **实现**在 `material.py` —— 两边都看。
    """
    src = PIPELINE.read_text(encoding="utf-8")
    mat = MATERIAL.read_text(encoding="utf-8")
    assert src.count("_sections_for(spec,") >= len([s for s in R.ROUNDS if s.material]), \
        "有 LLM 轮没走 `_sections_for`（料就不受表管了）"
    assert "_join_sections([" not in mat, \
        "还有裸 `_join_sections([` —— 那就是绕过料校对的写法（`_sections_for` 内部自己调它）"
    assert "的料与轮次表不一致" in mat, "`_sections_for` 的当场炸不见了"
    print("    料: 每个 LLM 轮都过 `_sections_for` 逐字校对（对不上当场炸）")


# ---------------------------------------------------------------------------
# ⑤ 只有一步自带快照 ⑥ 游标不许回头
# ---------------------------------------------------------------------------

def test_only_the_group_step_carries_its_own_snapshot():
    """自带快照的只有分群（加法性的, 失败自己吞）—— 而且它是最后一步。"""
    own = [s.key for s in R.ROUNDS if s.own_snapshot]
    assert own == ["group"], (
        f"自带快照的步只该有 group, 实得 {own} —— 别的步骤失败必须连累整段"
        "（宁缺勿错: 半截记忆比没有记忆坏）")
    assert R.ROUNDS[-1].key == "group", "分群是每段的最后一步（与 R1–R4 不同层）"
    print("    快照: 只有 L2-a 分群自带（失败只回滚它自己）")


def test_cursor_allows_skips_but_never_goes_back():
    """跳过的步留空是允许的; **回头**不行（顺序的真源是表）。"""
    cur = Cursor()
    cur.enter("round_a")
    cur.enter("round_b")                       # 跳过 akin / close
    try:
        cur.enter("close")
    except AssertionError as e:
        assert "越序" in str(e), e
    else:
        raise AssertionError("游标允许回头了 —— 表就不再是顺序的真源")
    cur.enter("attr")                          # 往前走照旧
    cur.enter("group")
    assert cur.at == len(R.ROUNDS)
    print("    cursor: 可跳步, 不可回头（越序当场炸）")


# ---------------------------------------------------------------------------
# 时间预算（⭐ 2026-09-29 刀 1）: 每轮一份, 整段留硬顶
# ---------------------------------------------------------------------------

def test_round_budgets_fit_inside_the_segment_cap():
    """⭐ 各轮预算之和必须 ≤ 整段硬顶 —— 否则后面的轮又会被前面的吃掉, 等于没改。"""
    for spec in R.ROUNDS:
        assert R.budget_of(spec) > 0, f"{spec.key}: 预算必须为正"
    planned, cap = R.planned_seconds(), R.SEGMENT_HARD_CAP_SECONDS
    assert planned <= cap, (
        f"各轮预算之和 {planned}s 超过整段硬顶 {cap}s —— 硬顶会替前面的轮吃掉后面的轮"
        "（刀 1 要修的就是这个）; 要么调小某轮 budget, 要么抬硬顶")
    print(f"    预算: 每轮 {R.ROUND_BUDGET_SECONDS:.0f}s × "
          f"{len([s for s in R.ROUNDS if s.label])} 轮 = {planned:.0f}s ≤ 硬顶 {cap:.0f}s")


def test_round_deadline_is_the_tighter_of_the_two():
    """本轮的截止 = `min(整段硬顶, 现在 + 本轮预算)` —— 两个都要管用。"""
    from core.digest.call import _round_deadline
    now = time.monotonic()
    # 硬顶更近（前几轮把整段拖到快超时了）→ 取硬顶
    assert _round_deadline(now + 5, 120) - now <= 5.01
    # 预算更近（整段还有富余）→ 取预算
    assert abs((_round_deadline(now + 999, 120) - now) - 120) < 0.5
    # 没给硬顶 → 只有本轮预算
    assert abs((_round_deadline(None, 120) - now) - 120) < 0.5
    # 预算 0 → 退回"只有硬顶"（老调用方语义）
    assert _round_deadline(now + 7, 0) == now + 7
    print("    每轮截止 = min(硬顶, 现在+预算): 两种都管用, 预算 0 时退回老语义")


class _MustNotBeCalled:
    """硬顶已过 ⇒ 连 llm.chat 都不该被调（探针）。"""

    def chat(self, messages, **kw):                # pragma: no cover - 被调即失败
        raise AssertionError("硬顶已过却还发起了调用")


def test_budget_hit_names_the_round(tmp_path):
    """⭐ 撞预算的失败要**指明是哪一轮、哪种预算** —— 从前那句看不出（刀 1 的另一半）。"""
    st = _store(tmp_path)
    res = digest_segment(st, _MustNotBeCalled(), [_mmt(3)], deadline_seconds=0.0)

    assert not res.ok
    assert res.llm_calls == 0                       # 预检拦下, 一次都没发
    msg = " | ".join(res.errors)
    assert "round_a" in msg, msg                    # ⭐ 哪一轮
    assert "时间预算" in msg and "硬顶" in msg, msg    # ⭐ 哪种预算（0 秒 ⇒ 硬顶更紧）
    assert st.digested_seq == 0
    print(f"    {msg}")


def test_pipeline_does_not_pass_the_hard_cap_as_a_round_deadline():
    """调用点不许把整段硬顶直接当本轮截止传下去（那就绕过了 `_round_deadline`）。"""
    src = PIPELINE.read_text(encoding="utf-8")
    # ⚠️ 用词边界看: `hard_deadline=hard_deadline` 里的尾巴不算"裸传硬顶"
    assert not re.search(r"(?<![_A-Za-z])deadline=hard_deadline", src), \
        "有调用点把整段硬顶直接当本轮 deadline 传了 —— 每轮预算就白设了"
    assert src.count("hard_deadline=hard_deadline") == len([s for s in R.ROUNDS if s.label]), \
        "每个 LLM 轮都该传 hard_deadline=（本轮预算在 `_round_call` 里折算）"


# ---------------------------------------------------------------------------
# 端到端: 表推导出来的回滚清单**真的**清掉了那笔漏网的告警
# ---------------------------------------------------------------------------

def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="c")
    ensure_entities(st, char_name="伊草 遥香", sensei_name="老师")
    st.save()
    return st


def _mmt(seq, player="老师", reply="嗯"):
    e = make_event("mmt", "chat", {"player": player, "reply": reply})
    e.seq = seq
    return e


class RoundLLM:
    """R1 正常 / R4 给一条**引用坏了**的约定 / R2 引用不存在的 episode。"""

    def __init__(self):
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_A:
            return {"episodes": [{"text": "模型店门口", "title": "模型店门口",
                                  "tags": ["约定"]}]}
        if task == T.DIGEST_CLOSE:
            return {"add": [{"text": "拍一张模型店的照", "refs": ["m9999"]}], "close": []}
        if task in (T.DIGEST_B, T.DIGEST):
            return {"decisions": [{"episode": "m9999", "decision": "add",
                                   "kind": "belief", "text": "关于那家店的看法"}]}
        raise RuntimeError(f"意外调用 task={task!r}")


def test_batch_rollback_also_drops_the_close_warnings(tmp_path):
    """⭐ 回滚清单由表推导**修掉的那笔漏网**: R4 的世界校验告警也必须一并作废。

    从前 `_rollback` 的手抄清单里有 `notes_ops` 却没有 `notes_warnings` ⇒
    整批回滚之后, 结果对象里还留着一串**描述已作废操作**的告警
    （调用方看到 `ok=False` 不写事件, 但它拿到的 `DigestResult` 是自相矛盾的）。
    """
    st = _store(tmp_path)
    llm = RoundLLM()

    res = digest_segment(st, llm, [_mmt(3)])

    assert not res.ok, "R2 引用不存在的 episode ⇒ 整批失败"
    assert res.notes_ops == []
    assert res.notes_warnings == [], f"R4 的告警该随整批一起作废: {res.notes_warnings}"
    # 那些告警确实**产生过**（否则这条用例什么也没验到 —— 它得先在 R4 那里出现）
    assert llm.tasks[:2] == [T.DIGEST_A, T.DIGEST_CLOSE], llm.tasks
    assert [n.id for n in st.all() if n.kind == "episode"] == []      # R1 的节点也回滚了
    print("    端到端: 整批回滚 ⇒ note 面（ops + warnings）一起作废")


if __name__ == "__main__":
    import tempfile

    test_every_result_field_is_classified()
    test_rollback_clears_exactly_the_tables_fields()
    test_writes_names_exist_in_the_graph()
    test_writes_covers_the_edge_table()
    test_llm_rounds_are_complete()
    test_prompt_files_exist()
    test_labels_are_in_the_vocabulary()
    test_every_round_is_entered_by_the_pipeline()
    test_material_sections_are_all_named()
    test_sections_check_is_wired()
    test_only_the_group_step_carries_its_own_snapshot()
    test_cursor_allows_skips_but_never_goes_back()
    test_round_budgets_fit_inside_the_segment_cap()
    test_round_deadline_is_the_tighter_of_the_two()
    test_pipeline_does_not_pass_the_hard_cap_as_a_round_deadline()
    with tempfile.TemporaryDirectory() as d:
        test_budget_hit_names_the_round(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_batch_rollback_also_drops_the_close_warnings(Path(d))
    print("all digest rounds guard tests passed")
