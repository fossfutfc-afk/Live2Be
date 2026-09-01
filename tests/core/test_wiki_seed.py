"""seed.py 出厂 digest pass 测试（AGENT_BRAIN.md §3 Step 0 / M1c）。

验收: 遥香 experience/knowledge → 出厂条目 100% 映射, source_key 可溯源到 yml 字段;
幂等（重复 seed 零新增）; 出厂基座 immutable。
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
    # experience: self.regular 5 + self.new_year 3 + main 3 + valentine 1 = 12
    # knowledge: friends 5 + technique 3 + possession 3 + enemy 4 + places 3 = 18
    assert res.total == 30
    assert len(res.created) == 30

    facts = {n.source_key: n for n in st.all() if n.kind == "fact"}
    # 结构溯源抽查
    assert facts["self.regular.1"].content.startswith("不小心错误地给sensei发送了消息")
    assert facts["self.regular.5"].content.startswith("sensei误打误撞找到了遥香养杂草的秘密基地")
    assert facts["self.new_year.2"].content.startswith("明明在冬天")
    assert facts["main.1"].content.startswith("遥香与便利屋68的同伴们")
    # valentine 是多行纯标量（无 > 块指示符）——整体是 valentine 键的叶子
    assert facts["valentine"].content.startswith("sensei提前把遥香叫过来")
    assert "于是受到夸奖的遥香带着笑容回去了" in facts["valentine"].content
    assert facts["friends.aru"].content.startswith("即陆八魔阿露")
    assert facts["friends.saori"].content.startswith("即锭前纱织")
    assert facts["technique.1"].content.startswith("是一个埋炸弹高手")
    assert facts["possession.COCAO99%"].content.startswith("这是自己在情人节送sensei的巧克力")
    assert facts["enemy.黑龟组"].content.startswith("一个强大的黑帮组织")
    assert facts["places.杂草屋"].content.startswith("她经常去的一个破败的房子")
    # 空叶子跳过（self.dress: null）
    assert "self.dress" not in facts
    # epistemic / source 护栏
    assert all(f.epistemic == "canon_fact" for f in facts.values())
    assert all(f.source in ("experience", "knowledge") for f in facts.values())
    # 显著性默认值
    assert all(facts[k].significance == 0.9
               for k in facts if k.startswith(("self.", "main.", "valentine")))
    assert facts["friends.aru"].significance == 0.7
    # evolution log 落 seed 条目
    entries = EvolutionLog.for_store(st).read()
    assert len(entries) == 30 and entries[0]["pkg"] == "seed"
    assert entries[0]["detail"] == "experience:self.regular.1"


def test_seed_idempotent(tmp_path):
    st = _store(tmp_path)
    first = seed_from_config(st, HARUKA)
    second = seed_from_config(st, HARUKA)
    assert second.created == []                       # 零新增
    assert len(second.skipped) == 30                  # 全部按 source_key 跳过
    assert len(st) == len(first.created)


def test_seed_missing_file(tmp_path):
    st = _store(tmp_path)
    res = seed_from_config(st, "config/characters/igusa_haruka_no_such")
    assert res.errors                       # experience.yml 缺失被记录
    assert len(st) == 0


def test_seed_partial_rerun(tmp_path):
    """已有部分出厂条目时: 只补缺失的, 不动已存在的。"""
    st = _store(tmp_path)
    st.add(make_node("fact", content="旧版内容", epistemic="canon_fact",
                     source="experience", source_key="self.regular.1",
                     significance=0.9))
    res = seed_from_config(st, HARUKA)
    assert len(res.created) == 29                       # 缺 29 补 29
    assert res.skipped == ["self.regular.1"]
    assert st.get("c0001").content == "旧版内容"        # 已存在的不覆盖（immutable）
