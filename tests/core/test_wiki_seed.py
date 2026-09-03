"""seed.py 出厂 digest pass 测试（AGENT_BRAIN.md §3 Step 0 / M1c）。

v3 语义（2026-09-02 定稿: 出厂 wiki = **纯记忆**, fact 退役）:
    experience.yml → episode（预设记忆 = 角色记得的经历; sig 0.9 出厂锚）
    beliefs.yml    → belief（出厂认知种子; links 校验 source_key → 真实 episode id）
    knowledge.yml  → **不再出厂化**（世界观知识 = config 档案职责）
验收: 100% 映射 / source_key 溯源 / 幂等零重复（含落盘回归）/ 出厂 immutable /
      beliefs 孤儿引用报错并列出可用键。

v4（2026-09-04 brain_seed 定稿制）: brain_seed.yml 存在 → 出厂 episode 从定稿复制
    （narration 第一人称成品 + title/verbatim/sig; review_notes 不落库）;
    无 brain_seed → 原文兜底。判重键两分支一致 (source=experience, source_key)。
"""
from pathlib import Path

import pytest

from core.brain.wiki_v2 import WikiStoreV2, make_node
from core.brain.wiki_v2.evolution import EvolutionLog
from core.brain.wiki_v2.seed import seed_from_config

HARUKA = "config/characters/igusa_haruka"


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")


def test_seed_haruka_full_mapping(tmp_path):
    st = _store(tmp_path)
    res = seed_from_config(st, HARUKA)
    assert not res.errors, res.errors
    # experience: self.regular 5 + self.new_year 3 + main 3 + valentine 1 = 12 → episode
    assert res.total == 12
    assert len(res.created) == 12

    eps = {n.source_key: n for n in st.all()
           if n.kind == "episode" and n.source == "experience"}
    assert len(eps) == 12
    # 无 fact（knowledge 不再出厂化——世界观知识 = config 档案）
    assert all(n.kind != "fact" for n in st.all())
    assert len(st) == 12
    # 预设经历 → episode（narration 原文; 渲染层 _me 做第一人称）
    assert eps["self.regular.1"].narration.startswith("不小心错误地给sensei发送了消息")
    assert eps["self.regular.5"].narration.startswith("sensei误打误撞找到了遥香养杂草的秘密基地")
    assert eps["self.new_year.1"].narration.startswith("新年伊始")
    assert eps["main.1"].narration.startswith("遥香与便利屋68的同伴们")
    assert eps["valentine"].narration.startswith("sensei提前把遥香叫过来")
    # 空叶子跳过（self.dress: null）
    assert "self.dress" not in eps
    # epistemic / source / significance / immutable
    assert all(e.epistemic == "observed_fact" and e.source == "experience"
               for e in eps.values())
    assert all(e.significance == 0.9 for e in eps.values())
    assert all(e.is_seed() for e in eps.values())
    # evolution log（12 条 episode, 无 fact 条目）
    entries = EvolutionLog.for_store(st).read()
    assert len(entries) == 12 and entries[0]["pkg"] == "seed"
    assert entries[0]["detail"] == "experience:self.regular.1"
    assert entries[0]["kind"] == "episode"
    assert all(e.get("kind") != "fact" for e in entries)
    # 落盘回归: wiki.jsonl 真实写入（add 不 save 的根因已修）
    assert st.path.exists()
    lines = st.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 12, f"wiki.jsonl 应落盘 12 条, 实为 {len(lines)}"


def test_seed_beliefs(tmp_path):
    """beliefs.yml → belief（links 解析 source_key → episode id; 出厂不 immutable）。"""
    char = Path(tmp_path) / "char"
    char.mkdir(parents=True)
    (char / "experience.yml").write_text(
        "self:\n  - regular:\n    - 1: 拆炸弹事件\n    - 2: 杂草事件\nmain:\n  - 1: 黑市事件\n",
        encoding="utf-8")
    (char / "beliefs.yml").write_text(
        "- subject: 老师\n"
        "  content: 老师是第一个不会嫌弃我的人\n"
        "  links: [self.regular.1, self.regular.2]\n"
        "  significance: 0.95\n"
        "- subject: 便利屋68\n"
        "  content: 和大家在一起就是我最珍惜的事\n"
        "  links: [main.1]\n",
        encoding="utf-8")
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    res = seed_from_config(st, char)
    assert not res.errors, res.errors
    eps = {n.source_key: n for n in st.all() if n.kind == "episode"}
    bels = [n for n in st.all() if n.kind == "belief"]
    assert len(eps) == 3 and len(bels) == 2
    b1 = next(b for b in bels if b.subject == "老师")
    assert b1.content == "老师是第一个不会嫌弃我的人"
    assert b1.epistemic == "inferred_belief"
    assert b1.significance == 0.95
    assert set(b1.links) == {eps["self.regular.1"].id, eps["self.regular.2"].id}
    # 出厂 belief 不 immutable（认知种子, 运行时 touch/update 演化）
    assert b1.is_seed() is False
    # 默认 significance 0.85
    b2 = next(b for b in bels if b.subject == "便利屋68")
    assert b2.significance == 0.85
    assert b2.links == [eps["main.1"].id]


def test_seed_beliefs_bad_links_report_available(tmp_path):
    """孤儿 links 引用 → 报错并列出可用 source_key（guidance 承诺的友好报错）。"""
    char = Path(tmp_path) / "char"
    char.mkdir(parents=True)
    (char / "experience.yml").write_text("self:\n  - regular:\n    - 1: 拆炸弹\n",
                                         encoding="utf-8")
    (char / "beliefs.yml").write_text(
        "- subject: 老师\n  content: 结论\n  links: [self.regular.1, nope.9]\n",
        encoding="utf-8")
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    res = seed_from_config(st, char)
    assert any("nope.9" in e and "self.regular.1" in e for e in res.errors), res.errors
    assert all(n.kind != "belief" for n in st.all())      # 坏条目不落库
    assert len(st) == 1                                    # episode 已建


def test_seed_idempotent_and_no_log_duplication(tmp_path):
    st = _store(tmp_path)
    first = seed_from_config(st, HARUKA)
    second = seed_from_config(st, HARUKA)
    assert second.created == []                       # 零新增
    assert len(second.skipped) == 12                  # 全部按 source_key 跳过
    assert len(st) == len(first.created)
    # evolution 不重复 append（落盘根因回归）
    assert len(EvolutionLog.for_store(st).read()) == 12


def test_seed_missing_file(tmp_path):
    st = _store(tmp_path)
    res = seed_from_config(st, "config/characters/igusa_haruka_no_such")
    assert res.errors                       # experience.yml 缺失被记录
    assert len(st) == 0


def test_seed_legacy_fact_auto_filtered(tmp_path):
    """旧库 fact（v1/v2 残留）→ kind 已退役: 加载层自动过滤, save 整写清除。"""
    st = _store(tmp_path)
    st.add(make_node("episode", narration="拆炸弹", source="experience",
                     source_key="self.regular.1"))
    st.save()                                        # 先落盘再注入旧 fact 行
    # 模拟旧文件含 fact 行（kind=fact 已不在 KINDS → 加载被拒跳过）
    import json as _json
    lines = st.path.read_text(encoding="utf-8").strip().splitlines()
    fact_row = _json.dumps({"id": "c0099", "kind": "fact", "content": "旧知识",
                            "epistemic": "canon_fact", "source": "knowledge",
                            "source_key": "places.杂草屋", "significance": 0.7},
                           ensure_ascii=False)
    st.path.write_text("\n".join(lines + [fact_row]) + "\n", encoding="utf-8")
    st2 = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    assert all(n.kind != "fact" for n in st2.all())   # fact 不进内存
    assert len(st2) == 1
    res = seed_from_config(st2, HARUKA)               # 幂等 + save 整写清除 fact 行
    assert len(res.created) == 11                     # 补缺 11（regular.1 已在）
    raw = st2.path.read_text(encoding="utf-8")
    assert '"kind": "fact"' not in raw and "c0099" not in raw


# ============================================================================
# v4 brain_seed 定稿分支（2026-09-04: 出厂经历一次定稿, seed 确定性复制）
# ============================================================================

_BRAIN_SEED_YML = """\
episodes:
  - source_key: self.regular.1
    title: 拆炸弹乌龙
    narration: 我给老师发消息时不小心说漏了埋炸弹的事, 老师陪我拆完了炸弹
    verbatim: 没关系，我陪你拆完。
    significance: 0.95
  - source_key: main.1
    title: 黑市讨债
    narration: 大家一起去找黑市老板讨债, 社长差点被气哭
    significance: 0.7
review_notes:
  - source_key: self.regular.1
    note: 从这一刻开始, 遥香就对sensei无比信任。
"""


def _brain_seed_char(tmp_path: Path) -> Path:
    """假角色目录: experience.yml（原文）+ brain_seed.yml（定稿）+ beliefs.yml。"""
    char = Path(tmp_path) / "char"
    char.mkdir(parents=True)
    (char / "experience.yml").write_text(
        "SIG~self:\n  - regular:\n    - 1: 原文A\nmain:\n  - 1: 原文B\n",
        encoding="utf-8")
    (char / "brain_seed.yml").write_text(_BRAIN_SEED_YML, encoding="utf-8")
    (char / "beliefs.yml").write_text(
        "- subject: 老师\n  content: 老师是第一个接纳我的人\n  links: [self.regular.1]\n",
        encoding="utf-8")
    return char


def test_seed_brain_seed_full_mapping(tmp_path):
    """定稿分支: brain_seed episodes → episode（narration/title/verbatim/sig 入档;
    review_notes 不落库; beliefs links 仍按 source_key 解析到定稿 episode）。"""
    char = _brain_seed_char(tmp_path)
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    res = seed_from_config(st, char)
    assert not res.errors, res.errors
    eps = {n.source_key: n for n in st.all()
           if n.kind == "episode" and n.source == "experience"}
    assert len(eps) == 2
    n1 = eps["self.regular.1"]
    assert n1.narration.startswith("我给老师发消息时不小心说漏了埋炸弹的事")
    assert n1.title == "拆炸弹乌龙"
    assert n1.verbatim == "没关系，我陪你拆完。"
    assert n1.significance == 0.95
    assert n1.epistemic == "observed_fact" and n1.is_seed() is True
    assert eps["main.1"].title == "黑市讨债" and eps["main.1"].significance == 0.7
    # review_notes 不落库（beliefs 素材, 非节点）
    assert len(st) == 3                       # 2 episode + 1 belief
    bel = next(n for n in st.all() if n.kind == "belief")
    assert bel.links == [n1.id]               # source_key → 定稿 episode id
    # evolution log detail 标记定稿来源
    entries = EvolutionLog.for_store(st).read()
    assert entries[0]["detail"] == "brain_seed:self.regular.1"
    # 原文兜底不发生: narration 是定稿不是原文
    assert all("原文A" not in n.narration for n in eps.values())


def test_seed_brain_seed_idempotent(tmp_path):
    char = _brain_seed_char(tmp_path)
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    first = seed_from_config(st, char)
    second = seed_from_config(st, char)
    assert second.created == [] and len(second.skipped) == 3
    assert len(EvolutionLog.for_store(st).read()) == len(first.created)
    # 定稿条目 immutable（只允许 notes）
    with pytest.raises(ValueError):
        st.update(first.created[0], {"narration": "篡改"})


def test_seed_brain_seed_bad_entry_isolated(tmp_path):
    """坏条目（缺 source_key/缺 narration/sig 越界）→ errors 列清单, 好条目照落。"""
    char = _brain_seed_char(tmp_path)
    (char / "brain_seed.yml").write_text(
        "episodes:\n"
        "  - source_key: self.regular.1\n    title: ok\n    narration: 好的\n"
        "  - title: 缺source_key\n    narration: x\n"
        "  - source_key: main.1\n    title: 缺narration\n"
        "  - source_key: valentine\n    title: sig越界\n    narration: y\n"
        "    significance: 7\n",
        encoding="utf-8")
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    res = seed_from_config(st, char)
    # created = 1 episode + 1 belief（beliefs.yml 独立正常建）
    assert len(res.created) == 2
    assert any("缺 source_key" in e for e in res.errors)
    assert any("缺 narration" in e for e in res.errors)
    assert any("significance 非法" in e for e in res.errors)


def test_seed_brain_seed_parse_error_no_fallback(tmp_path):
    """定稿文件损坏 → 报错不崩, 且**不**静默回退原文（作者侧问题要显式）。"""
    char = _brain_seed_char(tmp_path)
    (char / "brain_seed.yml").write_text(
        "episodes:\n  - source_key: 'self.regular.1\n    title: x\n",   # 引号未闭合 → YAML 错
        encoding="utf-8")
    st = WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")
    res = seed_from_config(st, char)
    assert any("brain_seed.yml 解析失败" in e for e in res.errors)
    assert len(st) == 0                        # 原文不兜底——修/删定稿后重跑

