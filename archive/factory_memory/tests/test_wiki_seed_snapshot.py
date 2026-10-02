"""seed_snapshot 世界线快照测试（v4 brain_seed 定稿制, TODO 阶段 4.2）。

语义: 世界线首次 seed（created 非空）时, 把定稿输入（brain_seed.yml 或原文
experience.yml + beliefs.yml）复制进 worlds/{w}/characters/{c}/seed_snapshot/——
回退/重建与 config 后续修改解耦。幂等: 快照已存在同名文件不覆盖。
"""
from pathlib import Path

from core.brain import WikiStoreV2
from core.brain.seed import seed_from_config

_BRAIN_SEED = """\
episodes:
  - source_key: self.regular.1
    title: 拆炸弹乌龙
    narration: 我给老师发消息时不小心说漏了埋炸弹的事
    significance: 0.95
"""


def _char_dir(tmp_path: Path, *, with_brain_seed: bool) -> Path:
    char = Path(tmp_path) / "char"
    char.mkdir(parents=True)
    (char / "experience.yml").write_text(
        "SIG~self:\n  - regular:\n    - 1: 原文A\n    - 2: 原文B\n",
        encoding="utf-8")
    if with_brain_seed:
        (char / "brain_seed.yml").write_text(_BRAIN_SEED, encoding="utf-8")
    (char / "beliefs.yml").write_text(
        "- subject: 老师\n  content: 出厂信念\n  links: [self.regular.1]\n",
        encoding="utf-8")
    return char


def _store(tmp_path: Path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")


def _snapshot_dir(st: WikiStoreV2) -> Path:
    return st.path.parent / "seed_snapshot"


def test_snapshot_created_on_first_seed_with_brain_seed(tmp_path):
    """定稿分支: 首次 seed 后快照 = brain_seed.yml + beliefs.yml, 内容与 config 一致。"""
    char = _char_dir(tmp_path, with_brain_seed=True)
    st = _store(tmp_path)
    res = seed_from_config(st, char)
    assert not res.errors and res.created
    snap = _snapshot_dir(st)
    assert (snap / "brain_seed.yml").exists()
    assert (snap / "beliefs.yml").exists()
    assert not (snap / "experience.yml").exists()   # 定稿分支不照原文
    assert (snap / "brain_seed.yml").read_text(encoding="utf-8") == _BRAIN_SEED
    assert (snap / "beliefs.yml").read_text(encoding="utf-8") == (
        char / "beliefs.yml").read_text(encoding="utf-8")


def test_snapshot_created_on_legacy_fallback(tmp_path):
    """原文兜底分支: 快照 = experience.yml（无 brain_seed）。"""
    char = _char_dir(tmp_path, with_brain_seed=False)
    st = _store(tmp_path)
    seed_from_config(st, char)
    snap = _snapshot_dir(st)
    assert (snap / "experience.yml").exists()
    assert not (snap / "brain_seed.yml").exists()
    assert (snap / "experience.yml").read_text(encoding="utf-8") == (
        char / "experience.yml").read_text(encoding="utf-8")


def test_snapshot_idempotent_no_overwrite(tmp_path):
    """快照一旦写入不再更新（世界线内快照语义——config 定稿后续修改只影响新世界线）。"""
    char = _char_dir(tmp_path, with_brain_seed=True)
    st = _store(tmp_path)
    seed_from_config(st, char)
    snap_file = _snapshot_dir(st) / "brain_seed.yml"
    snap_file.write_text("作者手改过的快照", encoding="utf-8")
    # 二次 seed（幂等 created=0 本就不触发快照）; 强制重灌也不覆盖
    res = seed_from_config(st, char)
    assert res.created == []
    assert snap_file.read_text(encoding="utf-8") == "作者手改过的快照"


def test_config_change_does_not_touch_worldline(tmp_path):
    """config 定稿修改 → 已有世界线内容不变 + 快照保持原样（世界线自足）。"""
    char = _char_dir(tmp_path, with_brain_seed=True)
    st = _store(tmp_path)
    seed_from_config(st, char)
    before = sorted((n.to_dict() for n in st.all()), key=lambda d: d["id"])

    # 作者改 config: brain_seed 换新文本 + experience 换新
    (char / "brain_seed.yml").write_text(
        "episodes:\n  - source_key: self.regular.1\n    title: 新版\n"
        "    narration: 作者后来改的版本\n    significance: 0.8\n",
        encoding="utf-8")
    (char / "experience.yml").write_text("self:\n  - regular:\n    - 1: 新原文\n",
                                         encoding="utf-8")
    st2 = _store(tmp_path)
    res = seed_from_config(st2, char)
    assert res.created == []                       # 幂等——世界线不重灌
    after = sorted((n.to_dict() for n in st2.all()), key=lambda d: d["id"])
    assert after == before                         # 世界线内容零变化
    snap_file = _snapshot_dir(st2) / "brain_seed.yml"
    assert snap_file.read_text(encoding="utf-8") == _BRAIN_SEED   # 快照仍旧版


def test_new_worldline_uses_new_seed(tmp_path):
    """新世界线（不同 world_id）→ 用 config 当前定稿（旧世界线快照不受影响）。"""
    char = _char_dir(tmp_path, with_brain_seed=True)
    w1 = _store(tmp_path)
    seed_from_config(w1, char)
    # 作者更新定稿
    (char / "brain_seed.yml").write_text(
        "episodes:\n  - source_key: self.regular.1\n    title: 新版\n"
        "    narration: 作者后来改的版本\n    significance: 0.8\n",
        encoding="utf-8")
    w2 = WikiStoreV2(tmp_path, world_id="world2", char_id="igusa_haruka")
    seed_from_config(w2, char)
    n2 = next(n for n in w2.all() if n.kind == "episode")
    assert n2.narration == "作者后来改的版本"
    assert n2.significance == 0.8
    # 旧世界线保持旧定稿
    n1 = next(n for n in w1.all() if n.kind == "episode")
    assert n1.narration.startswith("我给老师发消息时")
    assert (w1.path.parent / "seed_snapshot" / "brain_seed.yml").read_text(
        encoding="utf-8") == _BRAIN_SEED
