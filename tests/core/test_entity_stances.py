# -*- coding: utf-8 -*-
"""**出厂物化**（B 笔, 2026-10-08）: `interperson.yml` 的立场 ⇒ 图里的 entity。

用户裁: *"一旦新认识一个人……出场建立 interperson.json 中的角色 entity 节点,
这样连 about 都省"* —— 因为 entity 一存在:

  ① **`entity.text` 出厂就有内容**（此前真档 `x0001` 的 text 一直是空的,
     全靠 digest 慢慢长）;
  ② **名字车道**才成立（`like` 用 `surface_forms` 做路由）⇒ ⭐ 玩家说"阿露"时,
     那些**正文里没写"阿露"、只用"她"指代**的 episode 也召得回来 ——
     这就是"连 about 都省"的意思（她不必主动查, 召回自己会摆）。

守门:
  ① 建出来: 主名/别名按 `id` 取档案（engine 侧解析）、`text` = 表里那句
  ② 幂等: 第二次调用 **零新建**（⇒ 调用方不会写盘）
  ③ **保留号不被顶**: self=x0000 / sensei=x0001
  ④ 同名撞上已有 entity ⇒ **不重复建**, 且**只填空 text**（⛔ 不覆盖她后来长出来的）
  ⑤ 名字解析不出 ⇒ 跳过 + warning（宁可不建, 也不建个没名字的）
  ⑥ 键 `self` / `sensei` ⇒ 只填立场, 不建新的
  ⑦ ⭐ 端到端（真表 + 真档案）: 6 个 entity 各就各位
  ⑧ ⭐ **名字车道**: 建出对象之后, "关于他但没写他名字"的那条经历召得回来
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.brain import WikiStoreV2, make_node                    # noqa: E402
from core.brain.entities import (SELF_ID, SENSEI_ID,             # noqa: E402
                                 ensure_entities, surface_forms)
from core.brain.read.like import RecallCtx, like                 # noqa: E402
from core.mmt.engine import _stances_of                          # noqa: E402
from core.parsing.dynamic_character_parser import CharacterLoader   # noqa: E402
from core.session.store import SessionStore                       # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REAL_TABLE = ROOT / "config" / "settings" / "relation" / "interperson.yml"
CHAR_ROOT = ROOT / "config" / "characters"
CHARACTER = "igusa_haruka"


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)


def _names(store) -> dict[str, str]:
    return {n.id: n.name for n in store.all() if n.kind == "entity"}


def _stances(loader, character=CHARACTER):
    return _stances_of(character, REAL_TABLE, loader)


def test_stances_are_materialized_with_text(tmp_path):
    """① 建出来 + `text` = 表里那句（名字/别名按 `id` 取档案, 零手写）。"""
    loader = CharacterLoader(CHAR_ROOT)
    store = _store(tmp_path)
    table = {k: v for k, v, _a, _t in [(s[0], s[1], s[2], s[3])
                                       for s in _stances(loader)]}
    made = ensure_entities(store, char_name="伊草 遥香",
                           sensei_name="老师", stances=_stances(loader))
    names = _names(store)
    assert list(names) == [SELF_ID, SENSEI_ID, "x0002", "x0003", "x0004", "x0005"], names
    # ⚠️ 名字取自**档案**（`most called name` 原文带空格: `陆八魔 阿露`）;
    #    而 saori 没档案, 名字来自表里那句 `name`（作者怎么写就怎么用）
    assert names["x0002"] == "陆八魔 阿露" and names["x0003"] == "浅黄 睦月"
    assert names["x0004"] == "鬼方 佳代子" and names["x0005"] == "锭前纱织"
    assert {"x0002", "x0003", "x0004", "x0005"} <= set(made), made
    # 阿露: 名字与别名来自 `profile.yml`（而不是手抄）
    aru = store.get("x0002")
    assert "阿露" in surface_forms(aru), surface_forms(aru)
    assert aru.text.startswith("陆八魔阿露大人"), aru.text
    # ⭐ sensei（保留号）的立场是**表里那句**（此前真档一直是空的）
    assert store.get(SENSEI_ID).text.startswith("sensei非常照顾我")
    assert table  # 防"表没读到却全绿"
    print(f"    materialize: {len(made)} 个新对象 + sensei 的立场已装（{names['x0002']} …）")


def test_materialize_is_idempotent_and_never_overwrites(tmp_path):
    """②③④ 幂等 · 保留号 · **只填空 text**: 跑第二遍零新建, 也不动她长出来的立场。"""
    loader = CharacterLoader(CHAR_ROOT)
    store = _store(tmp_path)
    stances = _stances(loader)
    first = ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                            stances=stances)
    assert first
    # 模拟"她后来长出来的立场"（digest 的 R3 会改写 text）
    grown = store.get("x0002")
    grown.text = "（这是她后来自己长出来的看法）"
    second = ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                             stances=stances)
    assert second == [], "第二次不该新建（幂等 ⇒ 调用方不写盘）"
    assert len(_names(store)) == 6, _names(store)
    assert store.get("x0002").text == "（这是她后来自己长出来的看法）", \
        "⛔ 不许覆盖她后来长出来的立场"
    assert store.get(SELF_ID).id == SELF_ID and store.get(SENSEI_ID).id == SENSEI_ID
    print("    materialize: 幂等（零新建）+ 不覆盖已有的 text + 保留号不动")


def test_empty_text_is_filled_later(tmp_path):
    """④ 已存在但 `text` 空 ⇒ **补填**（表里后来才写立场也认）。"""
    loader = CharacterLoader(CHAR_ROOT)
    store = _store(tmp_path)
    ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                    stances=[s for s in _stances(loader) if s[0] != "sensei"])
    assert not store.get(SENSEI_ID).text.strip()
    ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                    stances=_stances(loader))          # 这一遍带上 sensei 那条
    assert store.get(SENSEI_ID).text.startswith("sensei非常照顾我")
    print("    materialize: 空 text 补填（不新建节点）")


def test_nameless_and_dup_entries_are_skipped(tmp_path):
    """⑤ 没名字 ⇒ 跳过; ④ 与既有对象同名 ⇒ 不重复建（只填空 text）。"""
    store = _store(tmp_path)
    make = ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                           stances=[("", "", [], "x"), ("dup", "", [], "y"),
                                    ("aru", "陆八魔阿露", ["阿露"], "她是我社长")])
    # ⚠️ `make` 里还有 self/sensei（这一趟是第一次建）—— 只看我们关心的那一条
    assert "x0002" in make, make
    assert _names(store) == {SELF_ID: "伊草 遥香", SENSEI_ID: "老师",
                             "x0002": "陆八魔阿露"}, _names(store)
    again = ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                            stances=[("aru_alias", "阿露", [], "别名撞上也算同一个人")])
    assert again == [] and len(_names(store)) == 3, _names(store)
    print("    materialize: 没名字跳过 / 同名（含别名）不重复建")


def test_same_name_modulo_whitespace_is_not_a_new_person(tmp_path):
    """⭐ 幂等**跨空白**（`form_key`, 2026-10-12）: `陆八魔阿露` ≡ `陆八魔 阿露`。

    判据从 `casefold` 换成 `form_key`（去空白）—— 否则"名字中间差一个空格"会被当成
    一个**新人**建出来, 而此后 `look(entity="陆八魔阿露")` 会 **ambiguous**
    （两个人都叫这个名; `entities.find_entity` 不猜）⇒ 静默查不出来。
    """
    store = _store(tmp_path)
    made = ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                           stances=[("aru", "陆八魔 阿露", [], "她是我社长")])
    assert len(made) == 3, made                     # self + sensei + 阿露
    again = ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                            stances=[("aru2", "陆八魔阿露", [], "另一个写法")])
    assert again == [], again                       # ⛔ 不建第二个人
    assert len(_names(store)) == 3, _names(store)
    assert store.get("x0002").text == "她是我社长"   # ⛔ 也不覆盖已有的看法
    print("    materialize: 名字差一个空格 ⇒ 还是同一个人（不重复建, 不覆盖看法）")


def test_the_real_table_materializes_six_entities(tmp_path):
    """⑦ ⭐ 端到端: **真表 + 真档案** ⇒ self/sensei + 表里那 5 个人。"""
    loader = CharacterLoader(CHAR_ROOT)
    store = _store(tmp_path)
    ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                    stances=_stances(loader))
    names = _names(store)
    assert len(names) == 6, names
    assert "老师" in names[SENSEI_ID] and "伊草" in names[SELF_ID]
    for nid in ("x0002", "x0003", "x0004", "x0005"):
        assert store.get(nid).text.strip(), f"{nid} 的立场没装上"
    print(f"    materialize: 真表 ⇒ {len(names)} 个 entity, 立场全装上")


def test_session_open_materializes_before_the_first_digest(tmp_path):
    """⭐ **开会话就物化**（C 笔）: 新档在**第一次 digest 之前**也得有那几个人。

    否则 brain 段的「我知道的名字」是空的 —— 出厂印象要等到消化完才出现,
    而"出厂就有看法"正是这一整条的目的。
    ⚠️ 同时钉住**严格性分档**: 只读注入路径（`digest=False`）**不抛** ——
    config 坏一天不该让她连记忆段都没有（消化的严格性照旧, 见 `_ensure_char_entities`）。
    """
    from core.mmt.engine import MomoTalkEngine

    store = SessionStore(data_root=tmp_path)
    eng = MomoTalkEngine(CHAR_ROOT, object(), store=store, interperson_path=REAL_TABLE)
    name = eng.start_session(CHARACTER)
    root = store.create(CHARACTER, name)
    eng.attach_session(root.session_id)
    eng._inject_brain(CHARACTER, root.session_id)          # 只读注入路径（不消化）

    wstore = WikiStoreV2(tmp_path, world_id=store.world_id, char_id=CHARACTER)
    names = {n.id: n.name for n in wstore.all() if n.kind == "entity"}
    assert len(names) == 6, names                          # self/sensei + 表里那 4 个
    assert SELF_ID in names and SENSEI_ID in names
    seg = eng._brain_injection
    assert "我知道的名字" in seg and "陆八魔" in seg, seg[:200]
    assert "sensei非常照顾我" in seg, seg[:200]             # sensei 的立场也在
    # ⭐ 她那一格在**表尾**（用户 2026-10-12: 原「我是这样看自己的」并进那张表）
    table = seg.split("我知道的名字（想起谁、翻谁的事，都用这些叫法）：\n")[1].split("\n\n")[0]
    lines = table.splitlines()
    assert lines[-1].startswith("- 伊草"), lines[-1]
    assert any(ln.startswith("- 陆八魔") for ln in lines), lines
    print(f"    materialize: 开会话即物化（{len(names)} 个）+ brain 段里有「我知道的名字」")


def test_session_open_survives_a_broken_table(tmp_path):
    """⚠️ 表坏了/没了 ⇒ **照常开会话**（只 warn）—— 那条路是只读注入, 不是消化。

    ⭐ 顺带钉住"表不是**全部**的名字来源": `self` + `sensei` 两个保留号来自
    **各自的档案**（不读 `interperson.yml`）⇒ 表没了, 那张表上仍然有这两行
    （只有别人不见了）—— 这与"表坏了不该让她连记忆段都没有"是同一条纪律。
    """
    from core.mmt.engine import MomoTalkEngine

    store = SessionStore(data_root=tmp_path)
    eng = MomoTalkEngine(CHAR_ROOT, object(), store=store,
                         interperson_path=tmp_path / "不存在.yml")
    name = eng.start_session(CHARACTER)
    root = store.create(CHARACTER, name)
    eng.attach_session(root.session_id)
    eng._inject_brain(CHARACTER, root.session_id)
    seg = eng._brain_injection or ""
    assert "- 陆八魔" not in seg                           # 表没了 ⇒ 那四个人不物化
    table = seg.split("我知道的名字（想起谁、翻谁的事，都用这些叫法）：\n")[1].split("\n\n")[0]
    lines = table.splitlines()
    assert lines[0] == "- 老师", lines                     # sensei 的档案不在这张表里
    assert lines[-1].startswith("- 伊草"), lines           # 她那一格照旧在表尾
    assert len(lines) == 2, lines
    print("    materialize: 表缺失 ⇒ 只 warn, 不挡开会话（self/sensei 照旧在表上）")


def test_the_name_lane_boosts_what_was_about_her(tmp_path):
    """⑧ ⭐ **名字车道**（"连 `about` 都省"的**准确**含义）。

    对象建出来之后才有车道可言（⛔ 没有 entity, `about` 边根本落不下来 ——
    `add_edge` 拒悬空）。车道有两条用途:
      · ⭐ 这一条: `like` 的 **`name` 路**（`spec="turn"` = P19 那条）—— 玩家提"阿露",
        把**关于阿露**的那几条**抬上来**;
      · `find({"entity": …})`: 按名字**全捞**（那是"定向寻找", `like` 不做 —— 见 `part_name`
        的裁决: 「老师」车道真机 10/21 条, 作准入的话一句寒暄就凑出 10 条并列）。

    ⇒ 所以判据是**加成/排序**, 不是"只有它召得回"。两条 episode 字面同样沾"炸弹",
    唯一的差别是**有没有挂 `about` 边**。
    """
    loader = CharacterLoader(CHAR_ROOT)
    store = _store(tmp_path)
    ensure_entities(store, char_name="伊草 遥香", sensei_name="老师",
                    stances=_stances(loader))
    # ⛔ 两条的**正文与标题都不许出现"阿露"** —— 否则字面路自己就命中了, 测的就不是车道;
    #    正文则**故意几乎一样**（唯一的差别就是那条 `about` 边）。
    #    ⚠️ 覆盖率下限是 `_COVER_MIN = 0.35` —— 正文得跟 query 有真重叠才进得来
    #    （这也是"宁缺勿错": 一条都不像 ⇒ 返回空, 不拿最近一条来凑）。
    ep1 = store.add(make_node("episode", text="社团让我把炸弹箱子搬去仓库清点",
                              title="搬箱子", ts="2026-09-30T10:00:00",
                              significance=0.6, event_seq=[1]))
    store.add(make_node("episode", text="社团让我把炸弹箱子搬去仓库清点",
                        title="清点仓库", ts="2026-09-30T10:00:00",
                        significance=0.6, event_seq=[1]))
    store.add_edge("about", ep1, "x0002", ts="2026-09-30T10:00:00")
    store.save()

    def _scored(query: str) -> dict[str, float]:
        ctx = RecallCtx(now=datetime(2026, 10, 8, 21, 0), query=query, embed_fn=None)
        return {c.node.title: c.score for c in like(store, ctx, spec="turn")}

    named = _scored("阿露让我把炸弹箱子搬去仓库")      # query 里点了名字
    assert set(named) == {"搬箱子", "清点仓库"}, named
    assert named["搬箱子"] > named["清点仓库"], named   # ⭐ 名字车道把它抬上来
    plain = _scored("让我把炸弹箱子搬去仓库")           # 不提名字 ⇒ 车道不参与
    assert abs(plain["搬箱子"] - plain["清点仓库"]) < 1e-9, plain
    print("    materialize: 名字车道 —— 提「阿露」时关于她的那条被抬到前面")
