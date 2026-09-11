# -*- coding: utf-8 -*-
"""webgui 设置存档（settings.toml）单测 — 全部离线，只碰 tmp_path。

重点: **[image].enabled 生图总开关的往返**（2026-09-11）——GUI 设置页复选框 →
`POST /api/settings` → settings.toml → `llm.image_gen.image_enabled()` 读得到。
以前没有任何用例覆盖这一层, 开关一旦在写盘/合并处被吞掉（比如漏进 store.DEFAULTS
白名单 → save 时被裁掉）就会静默失效。
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from webgui import chat, store  # noqa: E402
from webgui.routers.settings import SettingsIn, post_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _tmp_settings(tmp_path, monkeypatch):
    """settings.toml 一律落 tmp_path（禁碰项目根真实配置）+ 不重建真引擎。"""
    monkeypatch.setattr(store, "SETTINGS_PATH", tmp_path / "settings.toml")
    monkeypatch.setattr(chat, "reset_engines", lambda *a, **kw: None)


def test_image_enabled_defaults_true_and_roundtrips():
    """默认开 → 改 false 存盘 → 读回 false（白名单不吞字段 + toml 写 bool）。"""
    assert store.load_settings()["image"]["enabled"] is True     # 缺文件 → 默认开
    cur = store.load_settings()
    cur["image"]["enabled"] = False
    store.save_settings(cur)
    assert (store.SETTINGS_PATH.read_text(encoding="utf-8")
            .count("enabled = false")) == 1
    assert store.load_settings()["image"]["enabled"] is False
    print("    settings: [image].enabled 默认 true + 往返保真")


def test_post_settings_accepts_checkbox_bool():
    """GUI 复选框路径: POST image.enabled=false → 落盘; 再 POST true → 复原。"""
    asyncio.run(post_settings(SettingsIn(image={"enabled": False})))
    assert store.load_settings()["image"]["enabled"] is False
    asyncio.run(post_settings(SettingsIn(image={"enabled": True})))
    assert store.load_settings()["image"]["enabled"] is True
    print("    settings: POST /api/settings 布尔复选框往返")


def test_image_enabled_reads_saved_file(monkeypatch):
    """存盘的 false 被引擎侧读到（两个模块各读同一路径, 这里钉住一致性）。"""
    from llm import image_gen as ig
    monkeypatch.delenv(ig.ENV_SWITCH, raising=False)
    monkeypatch.setattr(ig, "_PROJECT_ROOT", Path(store.SETTINGS_PATH).parent)
    assert ig.image_enabled() is True                     # 还没存过 → 默认开
    cur = store.load_settings()
    cur["image"]["enabled"] = False
    store.save_settings(cur)
    assert ig.image_enabled() is False, "引擎侧应读到 GUI 存的关闭"
    print("    settings: GUI 存 → image_enabled() 读到（关闭生效）")
