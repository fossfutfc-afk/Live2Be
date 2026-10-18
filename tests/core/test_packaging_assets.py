"""随包 `assets/` 清单守门 —— `packaging/collect_assets.py` 只算不改盘。

为什么值得钉: 打包时"包里有没有图"由这份清单决定，而它一旦变成随机 / 依赖机器上的文件
顺序，同一个提交在两台机器上打出来的包就不一样 —— 那类差异事后解释不清。

两条口径都要钉:

  · `minimal` 必须带上**少了就报错或破相**的那几样（emotions.yml / 登录页 logo 与主界面
    背景 / director 白名单），其余一律不带 —— 否则安装包又会涨回 100 MB+
  · `full` 只带产品**真正读**的: 四角色的 spine+portrait（**不带 diff/ 与 ref/**）、
    地点表**声明过**的背景（磁盘上没被引用的不带）、登录页三件

⚠️ 为什么按**文件路径**加载而不是 `import packaging.collect_assets`: 仓库根的
`packaging/` 和 PyPI 上的 `packaging`（setuptools / pip 在用）同名，而**普通包优先于
命名空间包** ⇒ `import packaging` 拿到的是 PyPI 那个。这里显式从文件加载，不依赖 sys.path。

跑法: python -m pytest tests/core/test_packaging_assets.py
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
_MOD_PATH = ROOT / "packaging" / "collect_assets.py"

_spec = importlib.util.spec_from_file_location("live2be_collect_assets", _MOD_PATH)
assert _spec and _spec.loader, f"加载不到 {_MOD_PATH}"
assets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(assets)

FULL_CHARACTERS = assets.FULL_CHARACTERS
MENU_MUST = assets.MENU_MUST


def _fake_repo(tmp_path):
    """一棵最小仓库: 一个有图角色 + 一个只有词表的角色 + 两张背景（只声明一张）。"""
    src = tmp_path / "assets"

    def touch(rel: str, size: int = 10) -> None:
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * size)

    touch("_director_whitelist.json")
    touch("menu/default/a.jpg")
    touch("menu/logo/logo.png")
    touch("menu/vol2.0/carousel.jpg")

    char = FULL_CHARACTERS[0]
    touch(f"illustration/{char}/default/emotions.yml")
    touch(f"illustration/{char}/default/portrait/student.png")
    touch(f"illustration/{char}/default/spine/haruka_spr/haruka_spr.skel")
    touch(f"illustration/{char}/default/diff/haruka_spr_01.png")
    touch(f"illustration/{char}/ref/halo.png")
    touch(f"illustration/{char}/dress/emotions.yml")
    touch(f"illustration/{char}/dress/spine/CH0247_spr/CH0247_spr.skel")
    # 没立绘的角色: 只有词表（它在 minimal 里该出现, 在 full 里不该带出任何图）
    touch("illustration/nobody/default/emotions.yml")

    touch("background/SDIR_X/DIR_Y/have.jpg")
    touch("background/SDIR_X/DIR_Y/unused.jpg")

    config = tmp_path / "config"
    (config / "settings" / "world").mkdir(parents=True)
    (config / "settings" / "world" / "place_entities.json").write_text(json.dumps({
        "ok_place": {"place": "ok_place",
                     "files": {"day": ["SDIR_X/DIR_Y/have.jpg"], "night": []}},
    }, ensure_ascii=False), encoding="utf-8")
    return src, config


def test_minimal_has_only_what_would_break(tmp_path):
    src, _ = _fake_repo(tmp_path)
    rels = {rel.as_posix() for _, rel in assets.plan(src, "minimal")}
    assert "_director_whitelist.json" in rels
    for name in MENU_MUST:
        assert any(r.startswith(f"menu/{name}/") for r in rels), f"{name} 必须带"
    assert "illustration/nobody/default/emotions.yml" in rels, "没立绘的角色也要带词表"
    # 图一张都不该跟包走
    assert not [r for r in rels if r.endswith((".png", ".jpg")) and not r.startswith("menu/")]
    assert not [r for r in rels if r.startswith("background/")]


def test_full_takes_spine_and_portrait_but_not_diff_or_ref(tmp_path):
    src, config = _fake_repo(tmp_path)
    rels = {rel.as_posix() for _, rel in assets.plan(src, "full", config=config)}
    char = FULL_CHARACTERS[0]
    assert f"illustration/{char}/default/spine/haruka_spr/haruka_spr.skel" in rels
    assert f"illustration/{char}/default/portrait/student.png" in rels
    assert f"illustration/{char}/dress/spine/CH0247_spr/CH0247_spr.skel" in rels, "变装要带"
    assert not [r for r in rels if "/diff/" in r], "diff/ 只有 CLI 用，不带（119 MB）"
    assert not [r for r in rels if "/ref/" in r], "ref/ 只有生图参考用，不带"
    assert "menu/vol2.0/carousel.jpg" in rels, "登录页轮播属于产品界面"


def test_full_backgrounds_follow_the_place_table(tmp_path):
    """只带地点表声明过的 —— 磁盘上那 663 张没人引用的（151 MB）不进包。"""
    src, config = _fake_repo(tmp_path)
    rels = {rel.as_posix() for _, rel in assets.plan(src, "full", config=config)}
    assert "background/SDIR_X/DIR_Y/have.jpg" in rels
    assert "background/SDIR_X/DIR_Y/unused.jpg" not in rels


def test_full_does_not_invent_art_for_a_wordlist_only_character(tmp_path):
    src, config = _fake_repo(tmp_path)
    rels = {rel.as_posix() for _, rel in assets.plan(src, "full", config=config)}
    assert "illustration/nobody/default/emotions.yml" in rels, "词表还是带（它进 prompt）"
    assert not [r for r in rels if r.startswith("illustration/nobody/") and not r.endswith(".yml")]


def test_run_copies_exactly_the_plan(tmp_path):
    """真拷一遍（小文件）: 目标树 = 清单。"""
    src, config = _fake_repo(tmp_path)
    items = assets.plan(src, "full", config=config)
    dst = tmp_path / "out"
    n, total = assets.run(items, dst)
    assert n == len(items) and total > 0
    copied = {p.relative_to(dst).as_posix() for p in dst.rglob("*") if p.is_file()}
    assert copied == {rel.as_posix() for _, rel in items}


def test_unknown_mode_is_rejected(tmp_path):
    src, _ = _fake_repo(tmp_path)
    with pytest.raises(ValueError):
        assets.plan(src, "everything")
