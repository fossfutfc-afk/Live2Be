"""seed.py 出厂 digest pass 测试（AGENT_BRAIN.md §3 Step 0 / M1c）。

v2 语义（2026-09-02 用户拍板: experience 与 bond story 对等——预设记忆 =
角色记得的经历, 不是"我知道的事"）:
    experience.yml → episode（observed_fact, narration 原文, sig 0.9）
    knowledge.yml → fact（canon_fact, sig 0.7）
验收: 遥香 yml → 出厂条目 100% 映射, source_key 可溯源; 幂等（重复 seed 零新增）;
出厂基座 immutable; 落盘（wiki.jsonl 真实写入——不落盘根因回归）; v1 fact 迁移。
"""
from pathlib import Path

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
    assert res.migrated == []
    # experience: self.regular 5 + self.new_year 3 + main 3 + valentine 1 = 12 → episode
    # knowledge: friends 5 + technique 3 + possession 3 + enemy 4 + places 3 = 18 → fact
    assert res.total == 30
    assert len(res.created) == 30

    eps = {n.source_key: n for n in st.all()
           if n.kind == "episode" and n.source == "experience"}
    facts = {n.source_key: n for n in st.all() if n.kind == "fact"}
    assert len(eps) == 12 and len(facts) == 18
    # 预设经历 → episode（narration 原文; 渲染层 _me 做第一人称）
    assert eps["self.regular.1"].narration.startswith("不小心错误地给sensei发送了消息")
    assert eps["self.regular.5"].narration.startswith("sensei误打误撞找到了遥香养杂草的秘密基地")
    assert eps["self.new_year.2"].narration.startswith("明明在冬天")
    assert eps["main.1"].narration.startswith("遥香与便利屋68的同伴们")
    # valentine 是多行纯标量——整体是 valentine 键的叶子
    assert eps["valentine"].narration.startswith("sensei提前把遥香叫过来")
    assert "于是受到夸奖的遥香带着笑容回去了" in eps["valentine"].narration
    # 知识 → fact（content）
    assert facts["friends.aru"].content.startswith("即陆八魔阿露")
    assert facts["technique.1"].content.startswith("是一个埋炸弹高手")
    assert facts["possession.COCAO99%"].content.startswith("这是自己在情人节送sensei的巧克力")
    assert facts["places.杂草屋"].content.startswith("她经常去的一个破败的房子")
    # 空叶子跳过（self.dress: null）
    assert "self.dress" not in eps
    # epistemic / source 护栏 + 显著性
    assert all(e.epistemic == "observed_fact" and e.source == "experience"
               for e in eps.values())
    assert all(f.epistemic == "canon_fact" and f.source == "knowledge"
               for f in facts.values())
    assert all(e.significance == 0.9 for e in eps.values())      # 出厂锚珍贵档
    assert all(f.significance == 0.7 for f in facts.values())
    # 出厂基座 immutable（is_seed 覆盖出厂 episode）
    assert all(e.is_seed() for e in eps.values())
    # evolution log 落 seed 条目（kind 按 v2）
    entries = EvolutionLog.for_store(st).read()
    assert len(entries) == 30 and entries[0]["pkg"] == "seed"
    assert entries[0]["detail"] == "experience:self.regular.1"
    assert entries[0]["kind"] == "episode"
    # 落盘修复回归: wiki.jsonl 真实写入（此前 add 不 save → 恒空 → 重复 seed）
    assert st.path.exists()
    lines = st.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 30, f"wiki.jsonl 应落盘 30 条, 实为 {len(lines)}"


def test_seed_idempotent_and_no_log_duplication(tmp_path):
    st = _store(tmp_path)
    first = seed_from_config(st, HARUKA)
    second = seed_from_config(st, HARUKA)
    assert second.created == []                       # 零新增
    assert len(second.skipped) == 30                  # 全部按 source_key 跳过
    assert len(st) == len(first.created)
    # evolution 不重复 append（落盘根因回归）
    assert len(EvolutionLog.for_store(st).read()) == 30


def test_seed_missing_file(tmp_path):
    st = _store(tmp_path)
    res = seed_from_config(st, "config/characters/igusa_haruka_no_such")
    assert res.errors                       # experience.yml 缺失被记录
    assert len(st) == 0


def test_seed_migrates_v1_experience_facts(tmp_path):
    """v1 残留（experience 曾建模为 fact）→ 迁移删除 + v2 episode 重建。"""
    st = _store(tmp_path)
    st.add(make_node("fact", content="旧版内容", epistemic="canon_fact",
                     source="experience", source_key="self.regular.1",
                     significance=0.9))
    res = seed_from_config(st, HARUKA)
    assert res.migrated == ["self.regular.1"]         # v1 fact 被迁移删除
    assert len(res.created) == 30                     # 全量重建（含迁移掉的 1 条）
    # 旧 fact 不残留, v2 episode 就位
    old = [n for n in st.all()
           if n.kind == "fact" and n.source == "experience"]
    assert old == []
    eps = {n.source_key: n for n in st.all()
           if n.kind == "episode" and n.source == "experience"}
    assert eps["self.regular.1"].narration.startswith("不小心错误地给sensei发送了消息")
    # 迁移记录在 evolution log
    log = EvolutionLog.for_store(st).read()
    mig = [e for e in log if e.get("action") == "migrate"]
    assert len(mig) == 1 and mig[0]["detail"].startswith("experience:self.regular.1")
