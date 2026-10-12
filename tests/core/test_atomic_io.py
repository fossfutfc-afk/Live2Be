"""回归: 原子写的 **Windows 占用重试**（`core/common/atomic.py` + `core/session/io.py`）。

背景（实测过一次真实红）: Windows 上 `os.replace` 在目标文件被别的进程/线程**短暂打开**时
抛 `PermissionError`（WinError 5/32）——杀软/索引器/另一端刚读过都会这样。
这不是"写坏了"而是"这一刻不让换"; 老代码没有重试 ⇒ 一次偶发占用就让"本轮不记录"。
本文件钉住三件事: ① 瞬时错误会重试并最终成功 ② 用尽后**原样抛出**（不吞）
③ 失败时不留 temp 残渣。另: 永久性错误（FileNotFoundError）**不**重试。

运行: python -m pytest tests/core/test_atomic_io.py
"""
import json
import os
import pathlib
import sys


from core.common import atomic                                   # noqa: E402
from core.session import io as sio                               # noqa: E402


def _boom(*_a, **_kw):
    raise PermissionError(13, "另一个程序正在使用此文件")


def _flaky(times: int, real=os.replace):
    """前 `times` 次抛占用, 之后转真实现。"""
    state = {"n": 0}

    def fn(src, dst):
        state["n"] += 1
        if state["n"] <= times:
            raise PermissionError(13, "另一个程序正在使用此文件")
        return real(src, dst)

    return fn


def test_replace_retries_transient_and_succeeds(monkeypatch, tmp_path):
    src = tmp_path / "a.tmp"
    dst = tmp_path / "a.json"
    src.write_text("{}", encoding="utf-8")
    flaky = _flaky(2)
    monkeypatch.setattr(atomic, "_replace", flaky)

    atomic.replace_with_retry(src, dst, attempts=5, base_delay=0.001)

    assert dst.is_file() and not src.exists()
    print("    atomic-io: 被占用 2 次后成功（第 3 次）")


def test_replace_gives_up_and_reraises(monkeypatch, tmp_path, capsys):
    src = tmp_path / "b.tmp"
    dst = tmp_path / "b.json"
    src.write_text("{}", encoding="utf-8")
    calls = {"n": 0}

    def always(*_a, **_kw):
        calls["n"] += 1
        raise PermissionError(13, "占用中")

    monkeypatch.setattr(atomic, "_replace", always)

    try:
        atomic.replace_with_retry(src, dst, attempts=3, base_delay=0.001)
    except PermissionError as e:
        assert "占用中" in str(e)
    else:
        raise AssertionError("用尽重试后必须原样抛出（不能吞）")
    assert calls["n"] == 3, f"应恰好尝试 3 次, 实际 {calls['n']}"
    print("    atomic-io: 用尽 3 次后原样抛出（不吞）")


def test_non_transient_is_not_retried(monkeypatch, tmp_path):
    src = tmp_path / "c.tmp"
    dst = tmp_path / "c.json"
    calls = {"n": 0}

    def missing(*_a, **_kw):
        calls["n"] += 1
        raise FileNotFoundError(2, "temp 没了")

    monkeypatch.setattr(atomic, "_replace", missing)
    try:
        atomic.replace_with_retry(src, dst, attempts=5, base_delay=0.001)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("FileNotFoundError 应直接抛")
    assert calls["n"] == 1, f"非瞬时错误不该重试, 实际 {calls['n']} 次"
    print("    atomic-io: FileNotFoundError 不重试（1 次）")


def test_atomic_write_json_survives_transient_and_leaves_no_tmp(monkeypatch, tmp_path):
    """整合: 写 JSON 时被占用 2 次 → 仍然落盘, 且目录里不留 temp。"""
    target = tmp_path / "meta.json"
    monkeypatch.setattr(atomic, "_replace", _flaky(2))
    monkeypatch.setattr(atomic, "REPLACE_BASE_DELAY", 0.001)

    sio.atomic_write_json(target, {"ok": True, "n": 1})

    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True, "n": 1}
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "meta.json"]
    assert leftovers == [], f"不该留 temp 残渣: {leftovers}"
    print("    atomic-io: atomic_write_json 被占用 2 次后落盘、无残渣")


def test_atomic_write_json_failure_cleans_tmp_and_raises(monkeypatch, tmp_path):
    """持续占用 → 抛出, 且 **不留** temp（老代码的清理分支同样要成立）。"""
    target = tmp_path / "meta.json"
    monkeypatch.setattr(atomic, "_replace", _boom)
    monkeypatch.setattr(atomic, "REPLACE_BASE_DELAY", 0.001)

    try:
        sio.atomic_write_json(target, {"ok": False})
    except PermissionError:
        pass
    else:
        raise AssertionError("持续占用应抛出")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == [], "失败后必须清掉 temp"
    print("    atomic-io: 持续占用 → 抛出且清理 temp")


def test_atomic_write_lines_survives_transient(monkeypatch, tmp_path):
    target = tmp_path / "nodes.jsonl"
    monkeypatch.setattr(atomic, "_replace", _flaky(1))
    monkeypatch.setattr(atomic, "REPLACE_BASE_DELAY", 0.001)

    sio.atomic_write_lines(target, ["{\"a\": 1}", "{\"b\": 2}\n"])

    assert target.read_text(encoding="utf-8") == '{"a": 1}\n{"b": 2}\n'
    print("    atomic-io: atomic_write_lines 被占用 1 次后落盘（行尾补 \\n）")
