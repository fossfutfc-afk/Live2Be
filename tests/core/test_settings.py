"""infra/settings.py 单测 —— settings.toml 的唯一读入口。

钉四件事：

  ① 每次读都是最新的：文件一改，下一次读就是新值（**没有缓存** ⇒ 同长度改写也读得到）
  ② 缺文件 → {}（不是错误）；坏文件 → {} 且 last_error() 说得出来
  ③ section() 只给表，标量/缺段 → {}
  ④ LIVE2BE_SETTINGS 能把这份文件指到别处
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from infra import settings


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """一份 tmp 的 settings.toml（路径已通过 LIVE2BE_SETTINGS 指好）。"""
    path = tmp_path / "settings.toml"
    monkeypatch.setenv("LIVE2BE_SETTINGS", str(path))
    return path


def test_env_points_elsewhere(cfg):
    """LIVE2BE_SETTINGS 改的是"读哪份文件"，不改 app_root。"""
    assert settings.default_path() == cfg
    assert settings.app_root() == Path(__file__).resolve().parents[2]


def test_missing_file_is_not_an_error(cfg):
    assert settings.raw() == {}
    assert settings.last_error() == ""
    assert settings.section("llm") == {}


def test_every_read_sees_the_current_file(cfg):
    """没有缓存：改一次读一次（同长度的改写也必须读到 —— 2026-10-15 踩过的坑）。"""
    cfg.write_text("[llm]\n  model = \"a\"\n", encoding="utf-8")
    assert settings.raw()["llm"]["model"] == "a"
    cfg.write_text("[llm]\n  model = \"b\"\n", encoding="utf-8")     # 同样长度
    assert settings.raw()["llm"]["model"] == "b", \
        "同一长度、同一 mtime 刻度的改写也必须读到新值（缓存会在这里骗人）"
    cfg.write_text("[llm]\n  model = \"longer\"\n", encoding="utf-8")
    assert settings.raw()["llm"]["model"] == "longer"


def test_broken_file_reports_reason(cfg):
    cfg.write_text("[llm\n  bad = ", encoding="utf-8")
    assert settings.raw() == {}
    assert settings.last_error(), "坏文件必须留下原因（从前 5 个读者是静默的）"
    assert "settings.toml" in settings.last_error()


def test_fixed_file_clears_the_error(cfg):
    cfg.write_text("[llm\n", encoding="utf-8")
    assert settings.raw() == {} and settings.last_error()
    cfg.write_text("[llm]\n  model = \"ok\"\n", encoding="utf-8")
    assert settings.raw()["llm"]["model"] == "ok"
    assert settings.last_error() == "", "修好之后原因要清掉"


def test_section_only_returns_tables(cfg):
    cfg.write_text('title = "x"\n[llm]\n  model = "m"\n[weird]\n  n = 3\n',
                   encoding="utf-8")
    assert settings.section("llm") == {"model": "m"}
    assert settings.section("weird") == {"n": 3}
    assert settings.section("title") == {}, "标量不是表 → 空表"
    assert settings.section("nope") == {}


def test_app_root_is_a_directory():
    assert settings.app_root().is_dir()
    assert settings.default_path().name == "settings.toml"
    if not os.environ.get("LIVE2BE_SETTINGS"):
        assert settings.default_path() == settings.app_root() / "settings.toml"
