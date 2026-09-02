"""BondProgress 单测 — 轮数门槛（聚合单文件, 2026-09-02 合并拍板）。

- data/basic/bond_progress.json = {char_id: {"rounds", "updated_at"}}（所有角色一个 json）
- 缺失/损坏 → 0（宁缺勿错）; record_turn 重建落盘
- v0 分文件（data/{char}/progress.json）自动迁移: 并入聚合 → 删文件与空壳目录
- 旧全局聚合（{char_id: rounds}, legacy）兜底
运行: python -m pytest tests/core/test_bond_progress.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

import core.bond.bond_progress as bp_mod
from core.bond.bond_progress import BondProgress


def _bp(d: str) -> BondProgress:
    return BondProgress(data_root=Path(d))


def _agg_file(d: str) -> Path:
    return Path(d) / "basic" / "bond_progress.json"


def _char_file(d: str, char: str) -> Path:
    return Path(d) / char / "progress.json"


# ----------------------------------------------------------------------------
# 初始为 0; record_turn 递增; rounds 读回（聚合单文件）
# ----------------------------------------------------------------------------

def test_zero_and_record():
    with tempfile.TemporaryDirectory() as d:
        p = _bp(d)
        assert p.rounds("igusa_haruka") == 0, "未记录应返回 0"
        assert p.rounds("no_such_char") == 0, "未知角色应返回 0"
        n1 = p.record_turn("igusa_haruka")
        n2 = p.record_turn("igusa_haruka")
        assert n1 == 1 and n2 == 2, f"递增失败: {n1},{n2}"
        assert p.rounds("igusa_haruka") == 2
        # 一个 json 搞定: 聚合文件存在且只有它
        data = json.loads(_agg_file(d).read_text(encoding="utf-8"))
        assert data["igusa_haruka"]["rounds"] == 2
        print("    record: 0→1→2, 聚合单文件回读一致")


# ----------------------------------------------------------------------------
# 落盘往返: 新建实例读同一聚合文件, 轮数保留（跨会话累计语义）
# ----------------------------------------------------------------------------

def test_persist_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p1 = _bp(d)
        p1.record_turn("igusa_haruka")
        p1.record_turn("igusa_haruka")
        p1.record_turn("asagi_mutsuki")
        p2 = _bp(d)                       # 模拟新会话
        assert p2.rounds("igusa_haruka") == 2, "落盘往返后轮数丢失"
        assert p2.rounds("asagi_mutsuki") == 1
        print("    persist: 换实例读同一聚合文件, 累计保留")


# ----------------------------------------------------------------------------
# 多角色独立: 同一聚合文件内互不干扰
# ----------------------------------------------------------------------------

def test_multi_char_independent():
    with tempfile.TemporaryDirectory() as d:
        p = _bp(d)
        p.record_turn("igusa_haruka")
        p.record_turn("igusa_haruka")
        p.record_turn("rikuhachima_aru")
        assert p.rounds("igusa_haruka") == 2
        assert p.rounds("rikuhachima_aru") == 1
        assert p.rounds("asagi_mutsuki") == 0
        print("    multi: 同一聚合内角色轮数独立")


# ----------------------------------------------------------------------------
# 缺失聚合 → 0; record_turn 重建落盘
# ----------------------------------------------------------------------------

def test_missing_file():
    with tempfile.TemporaryDirectory() as d:
        p = _bp(d)
        assert p.rounds("x") == 0, "缺失文件应降级为 0"
        p.record_turn("x")               # 重建
        f = _agg_file(d)
        assert f.exists(), "record_turn 应创建聚合文件"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["x"]["rounds"] == 1
        print("    missing: 缺失→0, record 重建聚合落盘")


# ----------------------------------------------------------------------------
# 损坏 JSON / 非 dict / 非法 rounds → 降级为 0, 不崩
# ----------------------------------------------------------------------------

def test_corrupt():
    with tempfile.TemporaryDirectory() as d:
        f = _agg_file(d)
        f.parent.mkdir(parents=True)
        f.write_text("{ 不是 JSON", encoding="utf-8")
        p = _bp(d)
        assert p.rounds("x") == 0, "损坏 JSON 应降级为 0"
        p.record_turn("x")               # 降级后仍可写
        assert p.rounds("x") == 1
        print("    corrupt: 损坏→0, record 恢复写")

    with tempfile.TemporaryDirectory() as d:
        f = _agg_file(d)
        f.parent.mkdir(parents=True)
        f.write_text("[1,2,3]", encoding="utf-8")   # 非 dict
        assert _bp(d).rounds("x") == 0
        print("    corrupt: 非 dict 列表 → 0")

    with tempfile.TemporaryDirectory() as d:
        f = _agg_file(d)
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"x": {"rounds": -1}}), encoding="utf-8")
        assert _bp(d).rounds("x") == 0
        f.write_text(json.dumps({"x": {"rounds": "x"}}), encoding="utf-8")
        assert _bp(d).rounds("x") == 0
        f.write_text(json.dumps({"x": {"rounds": 3, "updated_at": "t"}}),
                     encoding="utf-8")
        assert _bp(d).rounds("x") == 3, "合法 rounds 保留"
        print("    corrupt: 负/非 int 丢弃, 合法保留")


# ----------------------------------------------------------------------------
# v0 分文件自动迁移（2026-09-02 合并单文件）
# ----------------------------------------------------------------------------

def test_v0_migrated_into_agg_and_cleaned():
    with tempfile.TemporaryDirectory() as d:
        # 预置 v0 分文件: data/{char}/progress.json（旧布局）
        for char, n in (("igusa_haruka", 7), ("rikuhachima_aru", 3)):
            f = _char_file(d, char)
            f.parent.mkdir(parents=True)
            f.write_text(json.dumps({"rounds": n, "updated_at": "t0"}),
                         encoding="utf-8")
        p = _bp(d)
        assert p.rounds("igusa_haruka") == 7      # 迁移后读到 v0 值
        assert p.rounds("rikuhachima_aru") == 3
        # v0 文件与空壳目录已清（一个 json 搞定, 不再有角色目录碎片）
        assert not _char_file(d, "igusa_haruka").exists()
        assert not (Path(d) / "igusa_haruka").exists()
        # 聚合文件含迁移值; record_turn 基于迁移值递增
        data = json.loads(_agg_file(d).read_text(encoding="utf-8"))
        assert data["igusa_haruka"]["rounds"] == 7
        assert p.record_turn("igusa_haruka") == 8
        print("    v0: 分文件并入聚合, 文件+空目录清理, 迁移值可续写")


def test_v0_migrate_idempotent():
    with tempfile.TemporaryDirectory() as d:
        f = _char_file(d, "x")
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"rounds": 5}), encoding="utf-8")
        p1 = _bp(d)
        assert p1.rounds("x") == 5
        p2 = _bp(d)                            # 第二次构造不再迁移/不丢
        assert p2.rounds("x") == 5
        print("    v0: 迁移幂等（二次构造值保留）")


def test_v0_corrupt_ignored():
    with tempfile.TemporaryDirectory() as d:
        f = _char_file(d, "x")
        f.parent.mkdir(parents=True)
        f.write_text("{ 坏", encoding="utf-8")
        p = _bp(d)
        assert p.rounds("x") == 0              # 坏 v0 忽略（不并入, 不删文件?）
        # 坏文件不并入 → 保留原样（宁缺勿错: 不破坏用户数据）
        assert _char_file(d, "x").exists()
        print("    v0: 损坏分文件忽略不删（保数据）")


# ----------------------------------------------------------------------------
# 旧全局聚合（{char_id: rounds}, legacy）兜底
# ----------------------------------------------------------------------------

def test_legacy_fallback(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        legacy = Path(d) / "legacy.json"
        legacy.write_text(json.dumps({"igusa_haruka": 42}), encoding="utf-8")
        monkeypatch.setattr(bp_mod, "_LEGACY_GLOBAL_PATH", legacy)
        p = _bp(d)
        assert p.rounds("igusa_haruka") == 42   # 聚合无记录 → legacy 兜底
        assert p.rounds("other") == 0
        print("    legacy: 聚合缺失 → 旧全局聚合兜底")
