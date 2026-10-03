# -*- coding: utf-8 -*-
"""轮次表守门（`core/digest/rounds/`, 2026-09-29 节点 C; 乙-1 起是包）。

它钉住**六件事** —— 都是"不钉就会烂掉"的约定:

  ① **结果字段分类齐全**: `DigestResult` 上每个字段要么被某轮声明（⇒ 回滚时清空）,
     要么在 `COMMIT_ONLY` 里（调用路径的记录 / 提交时才赋值）。**加字段忘了归类 → 这里红**
     —— 那正是"手抄清单"时代的病根（`notes_warnings` 漏了很久）。
  ② **`writes` 里的名字真实存在**: 节点面查 `nodes.BrainNode` 的字段 · `edge` 查
     `graph.REL_*` · `note` 查 `notes.SLOT_*`。表里写错一个字段名 = 表在骗人。
  ③ **LLM 四件套同生共死**: `label` / `prompt` / `phase` / `parse` 要么都有, 要么都没有
     （只有 `akin` 是零 LLM 的一步）; prompt 文件必须在盘上; 标签必须在词表里。
  ④ **表与执行一一对应**: `pipeline.IMPL` 的 key 与表**同序同集**, 且每一步自己都
     `ctx.enter("<key>")` 进过门（没实现 = 表里挂着死步骤; 代码里 enter 了表里没有的
     key = 表漏了）。
  ⑤ **只有一步自带快照**（分群, 而且是最后一步）—— 别的步骤失败必须连累整段。
  ⑥ **游标不许回头**（顺序的真源是表, 不是语句先后）。

运行: python -m pytest tests/core/test_digest_rounds.py
"""
import dataclasses
import re
import sys
import time
from dataclasses import MISSING
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
#: ⭐ 乙-1（2026-09-29）起**各轮的正文**住在这里 —— 调用点守门扫的就是这个目录。
ROUNDS_DIR = ROOT / "core" / "digest" / "rounds"
BASE = ROUNDS_DIR / "base.py"


def _rounds_src() -> str:
    """`rounds/` 包里所有模块的源码（含表自己）—— 扫调用点用。"""
    return "\n".join(p.read_text(encoding="utf-8")
                     for p in sorted(ROUNDS_DIR.glob("*.py")))

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
    """回滚清空**表里声明的那些**（回到**各自的初值**）, 且**不碰**失败报告本身。

    ⚠️ 判据是"回到 dataclass 的初值", 不是"回到 `[]`/`0`"（2026-09-29 D1 起
    `record_gaps` 是 dict ⇒ 拿 `in ([], 0)` 判会误报）。
    """
    res = DigestResult(ok=False)
    defaults = {f.name: (f.default_factory() if f.default_factory is not MISSING
                         else f.default)
                for f in dataclasses.fields(DigestResult)}
    for name in R.RESULT_FIELDS:                       # 全部弄脏
        setattr(res, name, "脏")
    for name in R.COMMIT_ONLY:                         # 提交态与账目也摆上
        setattr(res, name, "留")

    R.reset_result(res)

    dirty = {n: getattr(res, n) for n in R.RESULT_FIELDS
             if getattr(res, n) != defaults[n]}
    assert not dirty, f"这些字段没被清干净: {dirty}"
    for name in R.COMMIT_ONLY:                         # 一个都不许动
        assert getattr(res, name) == "留", \
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
# ③ LLM 四件套同生共死 + 三个派生标识 + prompt 文件在 + 标签在词表里 + 相位是真的
# ---------------------------------------------------------------------------

def test_llm_rounds_are_complete():
    """`llm` 标志与 `parse` 必须同进同退; 三个派生标识随它空/不空（只有 `akin` 全空）。

    ⚠️ 乙-2（2026-09-29）起 `label` / `prompt` / `phase` **不再写在表里** —— 它们由
    `key` 派生（`RoundSpec` 的 property）, 所以这里钉的判据改成
    "**`llm` 与 `parse` 一致**" + "派生值同生共死"。
    """
    for spec in R.ROUNDS:
        assert spec.llm == (spec.parse is not None), (
            f"{spec.key}: `llm={spec.llm}` 与 `parse="
            f"{'有' if spec.parse else '无'}` 不一致 —— 四件套就破了")
        derived = (spec.label, spec.prompt, spec.phase)
        assert all(derived) if spec.llm else not any(derived), \
            f"{spec.key}: 三个派生标识（label/prompt/phase）必须同生共死, 实得 {derived}"
    no_llm = [s.key for s in R.ROUNDS if not s.llm]
    assert no_llm == ["akin"], f"零 LLM 的步只该有 akin, 实得 {no_llm}"
    print(f"    {len(R.ROUNDS)} 步: {len(R.ROUNDS) - 1} 次 LLM + 1 次零成本补边（派生标识同生共死）")


def test_derived_identifiers_come_from_the_key():
    """⭐ 三个派生标识**逐字等于 key**（prompt 多一个 `digest_` 前缀）—— 乙-2 的立项理由。"""
    from core.digest.rounds import DIGEST_LOG_PREFIX

    for spec in R.ROUNDS:
        if not spec.llm:
            continue
        assert spec.label == spec.key, f"{spec.key}: label 该等于 key, 实得 {spec.label!r}"
        assert spec.phase == spec.key, f"{spec.key}: phase 该等于 key, 实得 {spec.phase!r}"
        assert spec.prompt == f"{DIGEST_LOG_PREFIX}{spec.key}", \
            f"{spec.key}: prompt 该是 {DIGEST_LOG_PREFIX}{spec.key}, 实得 {spec.prompt!r}"
        assert spec.name == f"{DIGEST_LOG_PREFIX}{spec.key}", spec.name
    assert R.ROUNDS[1].name == "digest_akin", "零 LLM 的 akin 也有日志前缀（用户裁决）"
    print("    派生: key → name / label / prompt / phase（一个都不手写）")


def test_every_phase_is_a_real_contract_phase():
    """⭐ `key` 取的就是**契约相位名** —— 每个 LLM 轮的相位必须真的能 `build_schema`。

    这条替换了从前"表里写死 `PHASE_*` 常量"的那份保证: 现在表里**没有**相位那一格了,
    所以由这条用例来钉"key 与契约相位是同一批词"。
    """
    from contract.digest_registry import (
        PHASE_ATTRIBUTE, PHASE_CLOSE, PHASE_GROUP, PHASE_RECORD, PHASE_UNDERSTAND,
        digest_registry,
    )
    real = {PHASE_RECORD, PHASE_UNDERSTAND, PHASE_CLOSE, PHASE_ATTRIBUTE, PHASE_GROUP}
    for spec in R.ROUNDS:
        if not spec.llm:
            continue
        assert spec.phase in real, \
            f"{spec.key}: phase {spec.phase!r} 不是契约认识的相位 {sorted(real)}"
        digest_registry.build_schema(spec.phase)          # 渲染不出来才是真的错
    print(f"    相位: {sorted(real)} —— 表里的 key 全在里面, 且都能 build_schema")


def test_prompt_files_exist():
    """表里写的 prompt 文件必须在盘上（改名忘了改表 → 红）。"""
    missing = [s.prompt for s in R.ROUNDS
               if s.prompt and not (ROOT / "llm" / "prompts" / f"{s.prompt}.md").is_file()]
    assert not missing, f"这些 prompt 文件不存在: {missing}"


def test_labels_are_in_the_vocabulary():
    """每步的 `label` 都要拼得出一个**词表里的** task 标签（桩与档位都按它走）。"""
    for spec in R.ROUNDS:
        if not spec.llm:
            continue
        tag = T.digest_label(spec.label)
        assert tag in T.ALL, f"{spec.key}: 标签 {tag!r} 不在 llm/task_labels.ALL 里"
        assert tag in T.PROFILE_OF, f"{tag} 没有映射到档位形态"
    print("    标签: " + " / ".join(T.digest_label(s.label)
                                   for s in R.ROUNDS if s.llm))


# ---------------------------------------------------------------------------
# ④ 料与执行一一对应
# ---------------------------------------------------------------------------

def test_every_round_is_implemented_and_entered():
    """表里的每一步都要**真有实现**、且**真的进过门** —— 双向。

    两处判据（乙-1 起正文按轮搬进了 `rounds/`）:
      · `pipeline.IMPL` 的 key 与表**同序同集**（少一个 = 表里挂着死步骤; 多一个/写错 =
        表漏了或名字打错了）
      · 那一步自己的文件里确实 `ctx.enter("<key>")` —— 进门才受游标管, 越序才炸得响
    """
    from core.digest.pipeline import IMPL

    keys = [s.key for s in R.ROUNDS]
    assert list(IMPL) == keys, (
        f"`pipeline.IMPL` 与轮次表不对应（**顺序也要一致**）:\n"
        f"  表={keys}\n  实现={list(IMPL)}\n"
        "（在 core/digest/rounds/ 加了/改了轮次, 就去看 core/digest/pipeline.py 的 IMPL）")
    entered = set(re.findall(r'ctx\.enter\("([a-z_]+)"\)', _rounds_src()))
    assert entered == set(keys), (
        f"表里挂着但没人进门: {sorted(set(keys) - entered)}（死步骤）\n"
        f"进了门但表里没有: {sorted(entered - set(keys))}（表漏了）")
    print(f"    {len(keys)} 步: IMPL 同序同集, 且每步都 `ctx.enter` 过门: {sorted(entered)}")


def test_material_sections_are_all_named():
    """每一步的料标题**非空**（零 LLM 的那步除外）—— 料是表的一半价值。"""
    for spec in R.ROUNDS:
        if spec.llm:
            assert spec.material, f"{spec.key}: LLM 轮必须有料（谁吃什么 = 表的一半）"
            assert len(set(spec.material)) == len(spec.material), \
                f"{spec.key}: 料标题重复（`_sections_for` 是逐字比对的）"


def test_sections_check_is_wired():
    """料校对真的接在调用点上（否则表里的 `material` 只是注释）。

    三条: 每个 LLM 轮都走 `ctx.sections_for(spec, …)` · 不许再有裸 `_join_sections([`
    的 LLM 输入 · `_sections_for` 里那条 `AssertionError` 还在。
    ⚠️ 乙-1 起**调用点**在 `rounds/<轮>.py`（`Ctx` 的方法转发）, **实现**在 `material.py`
    —— 两边都看。
    """
    src = _rounds_src()
    mat = MATERIAL.read_text(encoding="utf-8")
    n_llm = len([s for s in R.ROUNDS if s.material])
    assert src.count("ctx.sections_for(spec,") >= n_llm, \
        "有 LLM 轮没走 `ctx.sections_for`（料就不受表管了）"
    assert "_join_sections([" not in mat, \
        "还有裸 `_join_sections([` —— 那就是绕过料校对的写法（`_sections_for` 内部自己调它）"
    assert "的料与轮次表不一致" in mat, "`_sections_for` 的当场炸不见了"
    print(f"    料: {n_llm} 个 LLM 轮都过 `sections_for` 逐字校对（对不上当场炸）")


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
    cur.enter("record")
    cur.enter("understand")                       # 跳过 akin / close
    try:
        cur.enter("close")
    except AssertionError as e:
        assert "越序" in str(e), e
    else:
        raise AssertionError("游标允许回头了 —— 表就不再是顺序的真源")
    cur.enter("attribute")                          # 往前走照旧
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
    planned, cap = R.planned_seconds(), R.DIGEST_SEGMENT_HARD_CAP
    assert planned <= cap, (
        f"各轮预算之和 {planned}s 超过整段硬顶 {cap}s —— 硬顶会替前面的轮吃掉后面的轮"
        "（刀 1 要修的就是这个）; 要么调小某轮 budget, 要么抬硬顶")
    print(f"    预算: 每轮 {R.DIGEST_ROUND_BUDGET_SECONDS:.0f}s × "
          f"{len([s for s in R.ROUNDS if s.llm])} 轮 = {planned:.0f}s ≤ 硬顶 {cap:.0f}s")


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
    assert "record" in msg, msg                    # ⭐ 哪一轮（轮次 key）
    assert "时间预算" in msg and "硬顶" in msg, msg    # ⭐ 哪种预算（0 秒 ⇒ 硬顶更紧）
    assert st.digested_seq == 0
    print(f"    {msg}")


def test_the_round_deadline_is_computed_in_one_place():
    """调用点不许把整段硬顶直接当本轮截止传下去（那就绕过了 `_round_deadline`）。

    乙-1 起这件事变成了**结构**: 每轮只经 `base.Ctx.call` 一处发调用, 它交出去的是
    **整段硬顶**, "本轮截止 = min(硬顶, 现在+预算)"的折算在 `call._round_call` 里做。
    ⇒ 三条判据: 每个 LLM 轮都走 `ctx.call(` · 全包内没有裸 `deadline=hard_deadline` ·
    `Ctx.call` 交给 `_round_call` 的确实是整段硬顶。
    """
    src = _rounds_src()
    n_llm = len([s for s in R.ROUNDS if s.llm])
    assert src.count("ctx.call(") >= n_llm, \
        "有 LLM 轮没走 `ctx.call`（模型参数与预算就绕过去了）"
    # ⚠️ 用词边界看: `hard_deadline=hard_deadline` 里的尾巴不算"裸传硬顶"
    assert not re.search(r"(?<![_A-Za-z])deadline=hard_deadline", src), \
        "有调用点把整段硬顶直接当本轮 deadline 传了 —— 每轮预算就白设了"
    base = BASE.read_text(encoding="utf-8")
    assert "hard_deadline=self.hard_deadline" in base, \
        "`Ctx.call` 该把**整段硬顶**交给 `_round_call`（本轮截止在那边按预算折算）"
    print(f"    截止: {n_llm} 个 LLM 轮都经 `Ctx.call`, 折算只在 `call._round_call` 一处")


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
        if task == T.DIGEST_RECORD:
            return {"episodes": [{"text": "模型店门口", "title": "模型店门口",
                                  "tags": ["约定"]}]}
        if task == T.DIGEST_CLOSE:
            return {"add": [{"text": "拍一张模型店的照", "refs": ["m9999"]}], "close": []}
        if task in (T.DIGEST_UNDERSTAND, T.DIGEST):
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
    assert llm.tasks[:2] == [T.DIGEST_RECORD, T.DIGEST_CLOSE], llm.tasks
    assert [n.id for n in st.all() if n.kind == "episode"] == []      # R1 的节点也回滚了
    print("    端到端: 整批回滚 ⇒ note 面（ops + warnings）一起作废")


if __name__ == "__main__":
    import tempfile

    test_every_result_field_is_classified()
    test_rollback_clears_exactly_the_tables_fields()
    test_writes_names_exist_in_the_graph()
    test_writes_covers_the_edge_table()
    test_llm_rounds_are_complete()
    test_derived_identifiers_come_from_the_key()
    test_every_phase_is_a_real_contract_phase()
    test_prompt_files_exist()
    test_labels_are_in_the_vocabulary()
    test_every_round_is_implemented_and_entered()
    test_material_sections_are_all_named()
    test_sections_check_is_wired()
    test_only_the_group_step_carries_its_own_snapshot()
    test_cursor_allows_skips_but_never_goes_back()
    test_round_budgets_fit_inside_the_segment_cap()
    test_round_deadline_is_the_tighter_of_the_two()
    test_the_round_deadline_is_computed_in_one_place()
    with tempfile.TemporaryDirectory() as d:
        test_budget_hit_names_the_round(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_batch_rollback_also_drops_the_close_warnings(Path(d))
    print("all digest rounds guard tests passed")
