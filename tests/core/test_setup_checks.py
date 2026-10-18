"""资源配置辅助工具的体检逻辑守门 —— 分组齐、判据来自现役实现、写只碰 `[paths]`。

为什么值得钉: 体检最容易变成"自己发明一套判据"（我第一版拿 `MediaCatalog.background(地点key)`
查背景，168 个地点报出 103 个"缺"——全是假阳性，因为那个 API 是按**文件名**索引的）。
这里的用例把"判据来源"钉住：缺图要按**地点表自己声明的路径**判，角色卡要按 loader 判。

跑法: python -m pytest tests/core/test_setup_checks.py
"""
import json
from pathlib import Path

import pytest

from infra import settings
from setup_tool import checks

ROOT = Path(__file__).resolve().parent.parent.parent


def test_run_all_covers_the_five_groups():
    result = checks.run_all(probe_embedding=False)
    groups = {c.group for c in result}
    assert {"路径", "LLM", "角色卡", "素材", "数据"} <= groups, groups
    s = checks.summary(result)
    assert sum(s.values()) == len(result)
    assert s[checks.BAD] == 0, [c.line() for c in result if c.level == checks.BAD]
    # 真机仓库: 角色卡都该读得进来（8 个）
    names = [c.name for c in result if c.group == "角色卡"]
    assert any("找到角色" in n for n in names), names


def test_broken_character_card_is_reported(tmp_path, monkeypatch):
    """「有子目录但缺 profile.yml」= 不是角色卡 —— 必须报出来（否则只看到"0 个角色"）。"""
    root = tmp_path / "characters"
    (root / "not_a_card").mkdir(parents=True)
    (root / "not_a_card" / "worldview.yml").write_text("名字: 坏的\n", encoding="utf-8")
    monkeypatch.setattr(checks.paths, "CHARACTERS_DIR", root)

    result = checks.characters_checks()
    warn = [c for c in result if c.level == checks.WARN]
    assert warn, [c.line() for c in result]
    assert "not_a_card" in warn[0].detail, warn[0].line()
    assert "profile.yml" in warn[0].detail


def test_missing_background_is_judged_by_the_place_table(tmp_path, monkeypatch):
    """缺图要按**地点表声明的路径**判（不是按文件名猜）。"""
    assets = tmp_path / "assets"
    (assets / "background" / "SDIR_X" / "DIR_Y").mkdir(parents=True)
    (assets / "background" / "SDIR_X" / "DIR_Y" / "have.jpg").write_bytes(b"x")
    table = tmp_path / "place_entities.json"
    table.write_text(json.dumps({
        "ok_place": {"files": {"day": ["SDIR_X/DIR_Y/have.jpg"], "night": []}},
        "bad_place": {"files": {"day": ["SDIR_X/DIR_Y/gone.jpg"], "night": []}},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(checks.paths, "ASSETS_ROOT", assets)
    monkeypatch.setattr(checks.paths, "PLACE_TABLE_PATH", table)
    monkeypatch.setattr(checks.paths, "CHARACTERS_DIR", tmp_path / "no_characters")

    result = checks.assets_checks()
    warn = [c for c in result if c.level == checks.WARN and "背景" in c.name]
    assert warn, [c.line() for c in result]
    assert "gone.jpg" in warn[0].detail, warn[0].line()


def test_write_paths_round_trip(tmp_path, monkeypatch):
    """只写 `[paths]`；空串 = 删掉该覆盖；不许的键直接拒。"""
    target = tmp_path / "settings.toml"
    target.write_text("[llm]\n  model = \"keep-me\"\n", encoding="utf-8")
    monkeypatch.setattr(settings, "default_path", lambda: target)

    written = checks.write_paths(assets=str(tmp_path / "A"), data=str(tmp_path / "D"))
    assert written == target
    raw = settings.raw()
    assert raw["paths"] == {"assets": str(tmp_path / "A"), "data": str(tmp_path / "D")}
    assert raw["llm"]["model"] == "keep-me", "别的段一个字节都不许动"

    checks.write_paths(assets="")                       # 空串 = 删这条覆盖
    assert settings.raw()["paths"] == {"data": str(tmp_path / "D")}

    checks.write_paths(data="")
    assert "paths" not in settings.raw(), "全空 ⇒ 连 [paths] 表一起去掉"

    with pytest.raises(ValueError):
        checks.write_paths(app=str(tmp_path))           # 程序的落脚点不给改
