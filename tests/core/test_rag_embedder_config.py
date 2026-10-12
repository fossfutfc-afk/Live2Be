"""`LocalEmbedder` 配置面单测（T18, 2026-09-15）。

**为什么需要这一层**（用户裁决: *"Qwen 已经下载好了, 然后考虑如何真正接入"*）:
此前 `LocalEmbedder` **没有任何配置面** —— `DEFAULT_BASE_URL` 硬编码 1234、
模型靠 id 启发式发现。后果不是"少个旋钮", 而是**本机装好的模型对代码不可见**
（实验里 Qwen3 监听 1235）。配置面缺位时, 唯一"接入"办法是把服务挪到代码猜的
端口——让配置迁就代码。

优先级链与 `llm/client.py` / `llm/image_gen.py` 一致:
    构造参数 > settings.toml [embed] > 环境变量 > 默认

**测试不许联网**: 凡是要断言 base_url/model 的用例都显式给 `model`（配置或参数），
因为 `model` 为空会走 `_auto_discover()`（真发 HTTP）。健康探测一律 monkeypatch。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.rag import embedder as E  # noqa: E402


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    """清掉环境变量——防本机 `.env` / shell 里的值污染断言。"""
    for k in (E.ENV_BASE, E.ENV_MODEL):
        monkeypatch.delenv(k, raising=False)


def _write_settings(tmp_path, monkeypatch, body: str):
    p = tmp_path / "settings.toml"
    p.write_text(body, encoding="utf-8")
    monkeypatch.setattr(E, "_SETTINGS_PATH", p)
    return p


# ---------------------------------------------------------------------------
# 配置面
# ---------------------------------------------------------------------------

def test_defaults_without_config(monkeypatch):
    """无配置 → 默认地址 + 自动发现（发现被 patch 掉, 不联网）。"""
    monkeypatch.setattr(E, "_SETTINGS_PATH", Path("__no_such_settings__.toml"))
    monkeypatch.setattr(E.LocalEmbedder, "_auto_discover", lambda self: "auto-found")
    emb = E.LocalEmbedder()
    assert emb.base_url == E.DEFAULT_BASE_URL
    assert emb.model == "auto-found"
    print("    默认: base=1234 + 自动发现")


def test_settings_toml_wins_over_env(tmp_path, monkeypatch):
    """★ `[embed]` 段生效, 且**优先于环境变量**（与 llm/image 同一条链）。"""
    _write_settings(tmp_path, monkeypatch, (
        "[embed]\n"
        'base_url = "http://localhost:1235/v1"\n'
        'model = "Qwen3-Embedding-0.6B"\n'))
    monkeypatch.setenv(E.ENV_BASE, "http://env-should-lose:9999/v1")
    monkeypatch.setenv(E.ENV_MODEL, "env-model")
    monkeypatch.setattr(E.LocalEmbedder, "_probe_model", lambda self: True)
    emb = E.LocalEmbedder()
    assert emb.base_url == "http://localhost:1235/v1"       # 尾斜杠已归一
    assert emb.model == "Qwen3-Embedding-0.6B"
    print(f"    [embed]: base={emb.base_url} model={emb.model}（压过 env）")


def test_env_used_when_no_settings(tmp_path, monkeypatch):
    """没有 `[embed]` → 环境变量兜底（进程级覆盖, 测试/实验用）。"""
    _write_settings(tmp_path, monkeypatch, "[llm]\nmodel = \"deepseek-chat\"\n")
    monkeypatch.setenv(E.ENV_BASE, "http://localhost:1235/v1")
    monkeypatch.setenv(E.ENV_MODEL, "Qwen3-Embedding-0.6B")
    monkeypatch.setattr(E.LocalEmbedder, "_probe_model", lambda self: True)
    emb = E.LocalEmbedder()
    assert emb.base_url == "http://localhost:1235/v1"
    assert emb.model == "Qwen3-Embedding-0.6B"
    print("    env 兜底: LIVE2BE_EMBED_BASE / _MODEL 生效")


def test_constructor_wins(tmp_path, monkeypatch):
    """构造参数 > settings.toml（最高优先）。"""
    _write_settings(tmp_path, monkeypatch, (
        "[embed]\nbase_url = \"http://from-settings/v1\"\nmodel = \"s-model\"\n"))
    monkeypatch.setattr(E.LocalEmbedder, "_probe_model", lambda self: True)
    emb = E.LocalEmbedder("http://from-arg/v1", "arg-model")
    assert emb.base_url == "http://from-arg/v1" and emb.model == "arg-model"
    print("    构造参数: 压过 settings.toml")


def test_broken_or_missing_settings_degrades(tmp_path, monkeypatch):
    """**绝不抛**: 缺文件 / TOML 坏 / `[embed]` 不是表 → 回落默认。"""
    monkeypatch.setattr(E.LocalEmbedder, "_auto_discover", lambda self: "")
    monkeypatch.setattr(E, "_SETTINGS_PATH", tmp_path / "nope.toml")
    assert E.LocalEmbedder().base_url == E.DEFAULT_BASE_URL
    for body in ("[embed\n 坏 toml", "[embed]\nbase_url = 123\n",
                 "embed = \"not a table\"\n"):
        _write_settings(tmp_path, monkeypatch, body)
        assert E.LocalEmbedder().base_url == E.DEFAULT_BASE_URL, body
    print("    降级: 缺/坏/非表 → 默认地址（不抛）")


def test_empty_string_fields_skipped(tmp_path, monkeypatch):
    """空串 = "没配"（与 `llm/client.py` 同一口径）, 继续往下走链子。"""
    _write_settings(tmp_path, monkeypatch, '[embed]\nbase_url = ""\nmodel = "  "\n')
    monkeypatch.setenv(E.ENV_BASE, "http://env-fallback/v1")
    monkeypatch.setenv(E.ENV_MODEL, "env-model")
    monkeypatch.setattr(E.LocalEmbedder, "_probe_model", lambda self: True)
    emb = E.LocalEmbedder()
    assert emb.base_url == "http://env-fallback/v1"
    assert emb.model == "env-model"
    print("    空串视作未配 → 继续走 env")


# ---------------------------------------------------------------------------
# health 改真（配置面带来的新失败模式）
# ---------------------------------------------------------------------------

def test_health_probes_when_model_from_config(monkeypatch):
    """★ 配来的 model **真探一次** —— 名字打错不再伪装成 `fn=ok`。

    旧实现 `health() == bool(self.model)`: 自动发现年代它等价于"刚敲通 /v1/models";
    但手写 model 打错时它仍为 True → `_get_embed_fn()` 报 ok, 而每次 embed 都 404。
    """
    monkeypatch.setattr(E, "_SETTINGS_PATH", Path("__no_such_settings__.toml"))
    emb = E.LocalEmbedder(model="Qwen3-Embedding-0.6B")
    monkeypatch.setattr(emb, "available_models",
                        lambda: ["Qwen3-Embedding-0.6B", "qwen2.5-7b"])
    assert emb.health() is True
    # 打错名字
    emb2 = E.LocalEmbedder(model="Qwen3-Embedding-6B")      # 少了个 0.
    monkeypatch.setattr(emb2, "available_models",
                        lambda: ["Qwen3-Embedding-0.6B"])
    assert emb2.health() is False, "打错的模型名必须被挡住"
    # 服务不可达
    emb3 = E.LocalEmbedder(model="m")

    def _boom():
        raise E.RagError("服务没起")
    monkeypatch.setattr(emb3, "available_models", _boom)
    assert emb3.health() is False
    print("    health: 配来的模型真探（打错名/服务没起 → False, 不再伪装 ok）")


def test_health_cached(monkeypatch):
    """探测结果**缓存**——health() 会被 `_get_embed_fn` 反复调, 不能每次都发请求。"""
    monkeypatch.setattr(E, "_SETTINGS_PATH", Path("__no_such_settings__.toml"))
    emb = E.LocalEmbedder(model="m")
    calls = []
    monkeypatch.setattr(emb, "available_models",
                        lambda: (calls.append(1), ["m"])[1])
    assert emb.health() is True and emb.health() is True
    assert len(calls) == 1, f"探测被调用 {len(calls)} 次（应缓存）"
    print("    health: 探测结果缓存（只发一次请求）")


def test_auto_discover_recognizes_qwen3(monkeypatch):
    """`_EMBED_HINTS` 认得出 Qwen3-Embedding（`embed` 片段）——自动发现仍可用。"""
    emb = _bare_embedder()

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"data": [{"id": "qwen2.5-7b-instruct"},
                                         {"id": "Qwen3-Embedding-0.6B"}]}

    class _C:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return _R()

    monkeypatch.setattr(E.httpx, "Client", _C)
    assert emb._auto_discover() == "Qwen3-Embedding-0.6B"
    print("    自动发现: Qwen3-Embedding-0.6B 被 _EMBED_HINTS 认出")


def test_auto_discover_never_blind_picks_an_llm(monkeypatch):
    """★ **绝不盲选 `ids[0]`** —— 服务上只有 LLM 时必须返回 `""`。

    旧实现末尾是 `return ids[0] if ids else ""`（"只有一个模型也认"）。那在
    "这台机器只跑了一个 **LLM**"时是有毒的: 拿 LLM 的 id 当 embedding 模型
    → `health()` True → 每轮 embed 全失败, 而日志只说"调用失败",
    看不出是**端口指错了服务**。本机正是这种布局（embedding 在 1235, 1234 另有用）。
    """
    emb = _bare_embedder()

    class _R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"data": [{"id": "qwen2.5-7b-instruct"},
                                         {"id": "deepseek-v4-flash"}]}

    class _C:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return _R()

    monkeypatch.setattr(E.httpx, "Client", _C)
    assert emb._auto_discover() == "", "把 LLM 当 embedding 模型了"
    # 且空表同样返回 ""（不是崩）
    class _Empty(_R):
        def json(self): return {"data": []}
    class _C2(_C):
        def get(self, url): return _Empty()
    monkeypatch.setattr(E.httpx, "Client", _C2)
    assert emb._auto_discover() == ""
    print("    自动发现: 只有 LLM / 空表 → \"\"（宁可降级, 不可用错）")


def _bare_embedder():
    """不跑 __init__ 的裸实例（避开配置链与网络）——只测 `_auto_discover`。"""
    emb = E.LocalEmbedder.__new__(E.LocalEmbedder)
    emb.base_url = "http://x/v1"
    emb.timeout = 3.0
    return emb


if __name__ == "__main__":
    import pytest as _p
    raise SystemExit(_p.main([__file__, "-q", "-s"]))
