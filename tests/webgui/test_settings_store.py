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


# ---------------------------------------------------------------------------
# 2026-09-13 审计 A1: 保存必须**保真** —— 原实现按 store.DEFAULTS 白名单裁剪,
# 用户每点一次保存就把 GUI 不认识的键（reasoning_effort / use_proxy / [bond]）
# 连带删掉。本组用例钉住"文件里有什么就写回什么"。
# ---------------------------------------------------------------------------

#: 一份"手工维护"的配置: 含 GUI 不认识的键、整段 [bond]、嵌套表 [llm.tasks.*]
_HANDMADE = """[llm]
  api_key = "sk-real"
  base_url = "https://api.deepseek.com"
  model = "deepseek-v4-flash"
  reasoning_effort = "high"
  use_proxy = "false"

[llm.tasks.emotion]
  thinking = "medium"
  max_tokens = 768

[image]
  api_key = "img-real"
  enabled = true

[bond]
  choice_pregen = "sibling"
"""


def _write_handmade():
    store.SETTINGS_PATH.write_text(_HANDMADE, encoding="utf-8")


def test_save_settings_preserves_unknown_keys_and_sections():
    """GUI 不认识的分组/键必须原样活下来（A1 的直接回归）。"""
    _write_handmade()
    cur = store.load_settings()
    cur["llm"]["model"] = "deepseek-v4-pro"        # GUI 改一个它认识的键
    store.save_settings(cur)
    after = store.load_settings()
    assert after["llm"]["reasoning_effort"] == "high", "reasoning_effort 被裁掉"
    assert after["llm"]["use_proxy"] == "false", "use_proxy 被裁掉"
    assert after.get("bond", {}).get("choice_pregen") == "sibling", "[bond] 整段被裁掉"
    assert after["llm"]["api_key"] == "sk-real", "api_key 被抹"
    assert after["llm"]["model"] == "deepseek-v4-pro", "改动没生效"
    print("    settings: 未知键/整段/嵌套表在保存后全部保真")


def test_save_settings_preserves_nested_tables():
    """嵌套表 `[llm.tasks.emotion]` 往返保真（原实现会 str() 成字符串）。"""
    _write_handmade()
    store.save_settings(store.load_settings())
    after = store.load_settings()
    assert after["llm"]["tasks"] == {"emotion": {"thinking": "medium",
                                                 "max_tokens": 768}}
    text = store.SETTINGS_PATH.read_text(encoding="utf-8")
    assert "[llm.tasks.emotion]" in text, "嵌套表头丢失（被降级成字符串?）"
    print("    settings: 嵌套表 [llm.tasks.emotion] 保真落盘")


def test_save_settings_rejects_non_scalar_without_wiping():
    """非法叶子（list/dict 塞进标量位）→ 跳过, 且不误伤别的键。"""
    _write_handmade()
    cur = store.load_settings()
    cur["llm"]["bogus_list"] = ["a", "b"]          # 不可序列化 → 应被跳过
    cur["llm"]["model"] = "kept"
    store.save_settings(cur)
    after = store.load_settings()
    assert "bogus_list" not in after["llm"], "非法值被写进配置"
    assert after["llm"]["model"] == "kept"
    assert after["llm"]["reasoning_effort"] == "high"
    print("    settings: 非法值跳过 + 其余键无损")


def test_save_settings_rejects_none_leaf():
    """`null` 叶子被拒 → 不写成垃圾 `"None"`; 但**它是"删键"不是"保持原值"**。

    2026-09-13 复核（用户复核上一批修复时发现）: 本用例原先断言
    `after["llm"]["model"] == "deepseek-v4-flash"` 并写着"None 应被跳过（保持原值）"
    ——**那条断言不可能失败**: `_HANDMADE` 里的 model 恰好等于 `DEFAULTS` 的值,
    所以"值被保住"和"键被删掉→回落默认"两种实现都会通过（断言成了装饰）。

    实测真相（先落一个**非默认值**再看）: 拒收 = 跳过不写 = 该键从文件消失 →
    读回回落 `DEFAULTS`。所以"null = 不改"这个语义**不在本层**, 它归入口
    （`routers/settings.py::_acceptable`, 见下一个用例）。
    """
    _write_handmade()
    assert store._sane_value(None) is False, "None 必须被判为不可写"

    # 先落一个非默认值——否则下面的断言两种实现都通过, 等于没测
    cur = store.load_settings()
    cur["llm"]["model"] = "deepseek-reasoner"
    store.save_settings(cur)
    assert store.load_settings()["llm"]["model"] == "deepseek-reasoner"

    cur = store.load_settings()
    cur["llm"]["model"] = None                     # 手搓 POST {"llm": {"model": null}}
    store.save_settings(cur)
    text = store.SETTINGS_PATH.read_text(encoding="utf-8")
    assert '"None"' not in text and "= None" not in text, \
        f"null 落成了垃圾值: {text[:200]}"
    after = store.load_settings()
    # 本层行为: 键被删 → 回落 DEFAULTS（**不是**保住 "deepseek-reasoner"）
    assert after["llm"]["model"] == store.DEFAULTS["llm"]["model"], after["llm"]["model"]
    assert after["llm"]["model"] != "deepseek-reasoner", \
        "store 层不做'保持原值'——若哪天做了, 这条会红, 请同步改入口的说明"
    print("    settings: null 叶子不写成垃圾（键被删→回落默认, '不改'归入口）")


def test_post_settings_null_means_no_change():
    """**入口层**: POST 里的 `null` = 不改这个键（2026-09-13 修）。

    `store` 的"拒收"是跳过不写 → 删键; 所以"不改"必须在路由层拦。两个最要紧的
    后果（都是上面那条 store 用例的延伸）:
      · `[llm].model` 自定义值不能被 null 重置成内置默认;
      · **`[image].enabled=false` 不能被 null 翻回默认 true**（生图开 = 花钱方向）。
    """
    _write_handmade()
    asyncio.run(post_settings(SettingsIn(llm={"model": "deepseek-reasoner"})))
    asyncio.run(post_settings(SettingsIn(llm={"model": None})))          # null → 不改
    assert store.load_settings()["llm"]["model"] == "deepseek-reasoner", \
        "null 把自定义 model 重置成默认了（入口没拦住）"

    asyncio.run(post_settings(SettingsIn(image={"enabled": False})))
    assert store.load_settings()["image"]["enabled"] is False
    asyncio.run(post_settings(SettingsIn(image={"enabled": None})))      # null → 不改
    assert store.load_settings()["image"]["enabled"] is False, \
        "null 把生图开关翻回默认 true 了（花钱方向）"
    print("    settings: POST null = 不改（自定义 model / 生图开关都不被冲掉）")


def test_post_settings_ignores_non_scalar_junk():
    """非标量塞进标量键 → 不改; 但**合法的嵌套表写入不能被误伤**（2026-09-13）。"""
    _write_handmade()
    asyncio.run(post_settings(SettingsIn(llm={"model": {"x": 1}, "bogus": ["a"]})))
    after = store.load_settings()
    assert after["llm"]["model"] == "deepseek-v4-flash", \
        f"dict 把标量键顶成表了: {after['llm']['model']!r}"
    assert "bogus" not in after["llm"], "list 被写进配置"

    # 嵌套表是合法配置形态（[llm.tasks.*] 覆盖语法）——必须照常可写
    asyncio.run(post_settings(SettingsIn(
        llm={"tasks": {"emotion": {"thinking": "off", "max_tokens": 768}}})))
    assert store.load_settings()["llm"]["tasks"]["emotion"]["thinking"] == "off"
    print("    settings: 非法类型不改 / 嵌套表仍可写")


def test_post_settings_does_not_overwrite_real_key_with_mask():
    """打码值回传不得覆盖真 key（`is_masked` 是唯一防线, 此前零覆盖）。"""
    _write_handmade()
    assert store.is_masked(store.mask_api_key("sk-real")) is True
    assert store.is_masked("sk-real") is False
    asyncio.run(post_settings(SettingsIn(llm={"api_key": "****real",
                                              "model": "new-model"})))
    after = store.load_settings()
    assert after["llm"]["api_key"] == "sk-real", "打码值覆盖了真 key!"
    assert after["llm"]["model"] == "new-model", "同请求的其它字段应正常落盘"
    print("    settings: 打码 api_key 不覆盖真 key")


def test_post_settings_preserves_untouched_fields():
    """POST 只送 image.enabled 时, llm/bond 全部原样（走真实路由, 非直接调 store）。"""
    _write_handmade()
    asyncio.run(post_settings(SettingsIn(image={"enabled": False})))
    after = store.load_settings()
    assert after["image"]["enabled"] is False
    assert after["llm"]["reasoning_effort"] == "high"
    assert after["llm"]["api_key"] == "sk-real"
    assert after["bond"]["choice_pregen"] == "sibling"
    print("    settings: POST 局部字段 → 其余配置零损失")
