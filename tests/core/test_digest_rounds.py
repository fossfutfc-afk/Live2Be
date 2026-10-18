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

from core.brain import WikiStoreV2, graph, notes
from core.brain.entities import ensure_entities
from core.brain.nodes import KINDS, BrainNode
from core.digest import rounds as R
from core.digest.pipeline import DigestResult, digest_segment
from core.digest.rounds import Cursor
from core.session import make_event
from llm import task_labels as T
from tests import stub_tasks

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
            if face in R.FREE_FACES:
                continue                     # 中间产物（`segment`）没有真源可查
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


def test_l1_writes_edges_only():
    """⭐ **L1 只落边** —— `writes` 格里**不许出现节点面**（造看法 / 写正文是 L2 的活）。

    判据写在**表**上而不是去读 `relate.py` 的代码: 表是"这一步写什么"的唯一真源,
    它一旦长出 `belief` / `episode` 面, 就说明**两趟又被并回一趟**了
    （`DESIGN_DIGEST_TWO_PASSES §1` 那条已否决的写法）。
    """
    spec = next(s for s in R.ROUNDS if s.key == "relate")
    faces = [face for face, _fields in spec.writes]
    assert faces == [R.EDGE_FACE], f"relate 写了不该写的面: {spec.writes}"
    fields = sorted(f for _face, fs in spec.writes for f in fs)
    # ⚠️ 2026-10-08（E3）: 去掉 `about`（它不由 LLM 写）、补上 `evolved_from`
    # （P7-2 加了动作却漏了这一格 —— 红账, 见 `DESIGN_ENTITY_TAGS §7`）
    assert fields == ["akin", "contradicts", "evolved_from", "supports"], fields
    print(f"    L1 只落边: {spec.writes}")


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
    # 零 LLM 的那一步（`akin`）**也有日志前缀** —— 它不再是表里的第二位（R0 插到了最前）
    akin = next(s for s in R.ROUNDS if not s.llm)
    assert akin.name == "digest_akin", "零 LLM 的 akin 也有日志前缀（用户裁决）"
    print("    派生: key → name / label / prompt / phase（一个都不手写）")


def test_every_phase_is_a_real_contract_phase():
    """⭐ `key` 取的就是**契约相位名** —— 每个 LLM 轮的相位必须真的能 `build_schema`。

    这条替换了从前"表里写死 `PHASE_*` 常量"的那份保证: 现在表里**没有**相位那一格了,
    所以由这条用例来钉"key 与契约相位是同一批词"。
    """
    from contract.digest import (
        PHASE_COGNIZE,
        PHASE_RECORD,
        PHASE_RELATE,
        PHASE_SETTLE,
        PHASE_SPLIT,
        digest_registry,
    )
    # ⏸ `PHASE_GROUP` 2026-10-13 退役 —— 相位名与 `parse_group` 仍活着（老档要解析）,
    #    但它不再是一个"能渲染契约的轮", 所以不进这张表。
    real = {PHASE_SPLIT, PHASE_RECORD, PHASE_RELATE,
            PHASE_COGNIZE, PHASE_SETTLE}
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

def test_only_the_additive_steps_carry_their_own_snapshot():
    """自带快照的只有**加法性的那两步**（L2 造看法 · R3 认人）—— 而且它们排在最后。

    ⚠️ **2026-10-08（P10 接线）加上了 `cognize`**（用户裁决: L2 也是加法的 —— 失败只丢
    "新造的看法", 经历与边照旧）。⚠️ **2026-10-13 去掉了 `group`**（那一轮退役）。
    判据没放松: 除这两步外, 别的步失败**必须连累整段**（宁缺勿错: 半截记忆比没有记忆坏）。
    """
    own = [s.key for s in R.ROUNDS if s.own_snapshot]
    assert own == ["cognize", "settle"], (
        f"自带快照的只该是这两步（它们产的是加法）, 实得 {own} —— 别的步骤失败必须连累整段"
        "（宁缺勿错: 半截记忆比没有记忆坏）")
    assert [s.key for s in R.ROUNDS[-2:]] == own, "这两步必须是每段的最后两步"
    print("    快照: 造看法 + 认人自带（失败只回滚自己）")


def test_cursor_allows_skips_but_never_goes_back():
    """跳过的步留空是允许的; **回头**不行（顺序的真源是表）。"""
    cur = Cursor()
    cur.enter("record")
    cur.enter("relate")                           # 跳过 akin
    try:
        cur.enter("record")
    except AssertionError as e:
        assert "越序" in str(e), e
    else:
        raise AssertionError("游标允许回头了 —— 表就不再是顺序的真源")
    cur.enter("cognize")                            # 往前走照旧（跳过 akin/group 那两个位置）
    cur.enter("settle")                          # ⭐ E4: 表里最后一步（认人）
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
    # ⭐ 哪一轮（轮次 key）—— 硬顶已过 ⇒ 死在**第一步**（R0 切分, 表里的第一位）
    assert R.ROUNDS[0].key in msg, msg
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
    """R0 一头一片 / R1 正常 / L1 引用不存在的 episode（用来把整段打回）。

    ⚠️ 三个应答都**可以逐个覆盖**（`a` / `b` / `split`）—— 3b-3 那几条用例要的是
    "`state=open` 长成 note", 默认那套（L1 引用 `m9999`）会先把整段打回。
    """

    def __init__(self, *, a=None, b=None, split=None):
        self.a = a or {"episodes": [{"text": "模型店门口", "title": "模型店门口",
                                     "tags": ["约定"]}]}
        self.b = b or {"relations": [{"episode": "m9999", "supports": "u0001"}]}
        self.split = split
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_SPLIT:
            return self.split if self.split is not None \
                else stub_tasks.split_reply(messages)
        if task == T.DIGEST_RECORD:
            return self.a
        if task in (T.DIGEST_RELATE, T.DIGEST):
            return self.b
        if task == T.DIGEST_SETTLE:      # 挂 —— 这些用例不测它, 空包放行
            return {"entities": []}
        if task == T.DIGEST_COGNIZE:        # L2-b（P10）—— 同上
            return {"cognitions": []}
        raise RuntimeError(f"意外调用 task={task!r}")


class _EmptySkeletonLLM:
    """R0 交**空骨架**（"这一段没有值得记的"）; 其余轮一律不该被调到。"""

    def __init__(self):
        self.tasks: list[str | None] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.tasks.append(task)
        if task == T.DIGEST_SPLIT:
            return {"segments": []}
        raise AssertionError(f"空骨架下不该发这一轮: {task!r}")


def test_empty_skeleton_stops_the_content_rounds(tmp_path):
    """⭐ R0 交空骨架 ⇒ **对着切片的那几轮一次都不发** —— 而 `close` 那一轮照常走到。

    两条判据（2026-09-29 与用户定的）:
      · 空骨架 = 切分员说"这一段没有值得记的" ⇒ 建节点/连边/归属/分群全在空转
        （`understand` 还会被契约判形状错 —— 下面那个 `raise` 就是这条判据的探针）;
      · ⛔ **`close`（收口）不被这条闸拦**（表里 `needs_segments=False`）: 它吃的是
        **备忘录**, 而那条约定的翻篇**可能正好落在这一段** —— 跳过它 = 它永远开着。
        ⚠️ "没被拦" ≠ "一定发": 它自己还有一条 `skip`（这一段没有新经历**且**
        手上没有开着的约定 ⇒ 必然空转）。⇒ 本用例分两种: 没有开着的 (它自己跳过) /
        有开着的 (它真的发出去)。
    水位照推（推到触发点）: 内容留在事件流里, 只是不进记忆 —— 见 `_note_empty_segments`。
    """
    st = _store(tmp_path)
    llm = _EmptySkeletonLLM()
    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    assert llm.tasks == [T.DIGEST_SPLIT], "空骨架 + 手上没有约定 ⇒ 收口自己跳过"
    assert res.llm_calls == 1, "空骨架只发 R0 一轮"
    assert res.segments == [] and res.created == []
    assert st.digested_seq == 3, "水位照推（否则同一批会被反复喂给 R0）"

    # 手上**有**一条开着的约定 ⇒ 收口那一轮必须真的发出去
    st2 = _store(tmp_path / "b")
    st2.save()
    note = make_event("note", "add", {"text": "周六模型店", "refs": ["m0001"]})
    note.seq = 1
    llm2 = _EmptySkeletonLLM()
    res2 = digest_segment(st2, llm2, [note, _mmt(3)])

    assert res2.ok, res2.errors
    assert llm2.tasks == [T.DIGEST_SPLIT], llm2.tasks
    assert res2.llm_calls == 1, "空骨架 ⇒ 除了 R0 一次都不发（账留在本子上, 下一段自愈）"
    print("    空骨架: 对着切片的几轮全不发; 收口照常（没约定时它自己跳过）")


def _seg(i: int) -> dict:
    """一条切片（给 `_align_to_skeleton` 的单测用）。"""
    return {"span": [i, i], "abstract": f"第{i}件", "seqs": [i]}


def test_align_to_skeleton_three_judgements():
    """⭐ 3b-2 的核心对位: **位置与条数都归 R0**, 她只填（+ 唯一的裁决权 `drop`）。

    三条判据（都是"谁说了算"）:
      · 位置: 取 `segments[i]["seqs"]` —— 条目**自带**的 `span`/`event_seq` 一律不读;
      · 多写: **挂在末条切片上**（不丢 —— 一条切片能长不止一条记忆）+ 一行 warning;
      · 少写: 那几条切片没人填 ⇒ 进 D1 台账（`unfilled`）;
      · `drop`: 不落节点, 但要**占位**（否则后面几条会错位）。
    """
    from core.digest.rounds.record import _align_to_skeleton

    segs = [_seg(4), _seg(5)]
    # ① 正常: 一条对一条; 顺带钉住"自带 span 不看"
    out, gaps = _align_to_skeleton(
        [{"text": "a", "span": [99, 99]}, {"text": "b"}], segs)
    assert [e["seqs"] for e in out] == [[4], [5]], out
    assert gaps == {"dropped": [], "unfilled": [], "orders": [0, 1]}

    # ② 多写: 三条对两条 ⇒ 第 3 条附在**末条切片**上
    out2, gaps2 = _align_to_skeleton(
        [{"text": "a"}, {"text": "b"}, {"text": "c"}], segs)
    assert [e["seqs"] for e in out2] == [[4], [5], [5]], out2
    assert gaps2["dropped"] == [] and gaps2["unfilled"] == []

    # ③ 少写: 只给一条 ⇒ 第 2 条切片没人填（进账）
    out3, gaps3 = _align_to_skeleton([{"text": "a"}], segs)
    assert [e["seqs"] for e in out3] == [[4]]
    assert len(gaps3["unfilled"]) == 1 and "第5件" in gaps3["unfilled"][0], gaps3

    # ④ drop: 不落节点、但占位（后一条仍对到第 2 条切片）
    out4, gaps4 = _align_to_skeleton(
        [{"drop": True}, {"text": "b"}], segs)
    assert [e.get("text") for e in out4] == ["b"] and out4[0]["seqs"] == [5], out4
    assert len(gaps4["dropped"]) == 1 and gaps4["unfilled"] == []
    print("    对位: 位置取切片 / 多写附末条 / 少写进账 / drop 占位 ✓")


def test_state_open_grows_into_a_note(tmp_path):
    """⭐ 3b-3 / L1: **`state=open` 的切片 ⇒ 一条 `note/add`**（`refs` = 它自己那条 episode）。

    判据三件:
      · `text` = 切片的 `abstract` **原样**（契约要求 `always` 那句就是"她带走的那句话"）;
      · `refs` = **新**建出来的 episode（判重复复用的不算 —— 那一段已经写过 note 了）;
      · op 里带 **`src`**（去重键, 见 `notes.ALREADY_PINNED`）。
    """
    st = _store(tmp_path)
    llm = RoundLLM(
        split={"segments": [
            {"span": [3, 3], "state": "open", "abstract": "明天把两个团子带去夏莱, 别多想"},
            {"span": [3, 3], "abstract": "随口聊了几句"}]},
        a={"episodes": [{"text": "她答应了带团子", "title": "团子之约", "tags": ["约定"]},
                        {"text": "闲聊", "title": "闲聊", "tags": ["闲聊"]}]},
        b={"relations": []})          # L1: 这一段没接上任何关系

    res = digest_segment(st, llm, [_mmt(3)])

    assert res.ok, res.errors
    adds = [op for op in res.notes_ops if op.get("action") == "add"]
    assert len(adds) == 1, res.notes_ops
    op = adds[0]
    assert op["text"] == "明天把两个团子带去夏莱, 别多想"     # abstract 原样
    assert op["refs"] == ["m0001"] and op["src"] == "m0001"   # 指向它自己那条 episode
    assert "due" not in op


def test_kept_slice_without_a_node_is_a_loss(tmp_path):
    """⛔ 3b-3 / L1: `state=open` 的那条切片**没长成 note** ⇒ **收下她的裁决但记一笔账**。

    它意味着一件"说过要一直带着的事"没被记住 —— 那不能是静默的。
    ⛔ **不替她补**: 引擎补 = 把她没说的话写进她的本子。
    """
    st = _store(tmp_path)
    # 她 drop 掉了那条 ⭐（契约说"不许 drop", 那是**提示词纪律** —— 引擎不硬拦, 但记账）
    llm = RoundLLM(
        split={"segments": [
            {"span": [3, 3], "state": "open", "abstract": "以后每年生日都一起过"},
            {"span": [4, 4], "abstract": "闲聊"}]},
        a={"episodes": [{"drop": True},
                        {"text": "闲聊", "title": "闲聊", "tags": ["闲聊"]}]},
        b={"relations": []})
    res = digest_segment(st, llm, [_mmt(3), _mmt(4)])

    assert res.ok, res.errors
    assert [op for op in res.notes_ops if op.get("action") == "add"] == []
    dropped = res.record_gaps["items"]["dropped"]
    assert any("每年生日" in d for d in dropped), dropped


def test_batch_rollback_clears_the_fields_the_table_declares(tmp_path):
    """⭐ 回滚清单由表推导（`rounds.reset_result`）—— **这一轮写进去的东西必须一并作废**。

    从前 `_rollback` 是**手抄清单**, 而它**真的漏过**字段（`notes_warnings` 当年就没被清,
    那是这条机制诞生的证词 —— 该字段 2026-10-05 随收口轮一起删了）。
    这里拿 `record_gaps` 验同一个机制: R1 那一轮**确实写过它**（`_note_items`）,
    而 R2 一失败, 它必须跟着整批消失 —— 否则调用方拿到的是一个自相矛盾的
    `DigestResult`（`ok=False` 却带着"本段条目面"的账）。
    """
    st = _store(tmp_path)
    llm = RoundLLM()

    res = digest_segment(st, llm, [_mmt(3)])

    assert not res.ok, "R2 引用不存在的 episode ⇒ 整批失败"
    assert res.notes_ops == []
    assert res.record_gaps == {}, f"R1 写过的账该随整批作废: {res.record_gaps}"
    # ⚠️ 顺序里必须先有 R0（切分）—— `digest.split` 是表里的第一位
    assert llm.tasks[:2] == [T.DIGEST_SPLIT, T.DIGEST_RECORD], llm.tasks
    assert [n.id for n in st.all() if n.kind == "episode"] == []      # R1 的节点也回滚了
    print("    端到端: 整批回滚 ⇒ 表里声明的字段一起作废")


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
    test_only_the_additive_steps_carry_their_own_snapshot()
    test_cursor_allows_skips_but_never_goes_back()
    test_round_budgets_fit_inside_the_segment_cap()
    test_round_deadline_is_the_tighter_of_the_two()
    test_the_round_deadline_is_computed_in_one_place()
    with tempfile.TemporaryDirectory() as d:
        test_budget_hit_names_the_round(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_batch_rollback_clears_the_fields_the_table_declares(Path(d))
    print("all digest rounds guard tests passed")
