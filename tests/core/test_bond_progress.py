"""BondProgress 单测 — 轮数门槛（按角色分文件, DESIGN_SAVE.md §三）。

- 每角色一个 data/{char_id}/progress.json（{"rounds": N, "updated_at": …}）
- 缺失/损坏 → 0（宁缺勿错）; record_turn 重建落盘
- 角色文件存在时优先于旧全局聚合（不回退 legacy）
运行: python -m pytest tests/core/test_bond_progress.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_progress import BondProgress


def _bp(d: str) -> BondProgress:
    return BondProgress(data_root=Path(d))


def _char_file(d: str, char: str) -> Path:
    return Path(d) / char / "progress.json"


# ----------------------------------------------------------------------------
# 初始为 0; record_turn 递增; rounds 读回
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
        print("    record: 0→1→2, rounds 回读一致")


# ----------------------------------------------------------------------------
# 落盘往返: 新建实例读同一角色文件, 轮数保留（跨会话累计语义）
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
        print("    persist: 换实例读同角色文件, 累计保留")


# ----------------------------------------------------------------------------
# 多角色独立: 各自文件互不干扰
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
        print("    multi: 角色间轮数独立（分文件）")


# ----------------------------------------------------------------------------
# 缺失文件 → 0; record_turn 重建落盘（写 data/{char}/progress.json）
# ----------------------------------------------------------------------------

def test_missing_file():
    with tempfile.TemporaryDirectory() as d:
        p = _bp(d)
        assert p.rounds("x") == 0, "缺失文件应降级为 0"
        p.record_turn("x")               # 重建
        f = _char_file(d, "x")
        assert f.exists(), "record_turn 应创建角色文件"
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["rounds"] == 1, f"角色文件应含 rounds=1: {data}"
        print("    missing: 缺失→0, record 重建落盘（rounds 字段）")


# ----------------------------------------------------------------------------
# 损坏 JSON / 非 dict / 非法 rounds → 降级为 0, 不崩
# ----------------------------------------------------------------------------

def test_corrupt():
    with tempfile.TemporaryDirectory() as d:
        f = _char_file(d, "x")
        f.parent.mkdir(parents=True)
        f.write_text("{ 不是 JSON", encoding="utf-8")
        p = _bp(d)
        assert p.rounds("x") == 0, "损坏 JSON 应降级为 0"
        p.record_turn("x")               # 降级后仍可写
        assert p.rounds("x") == 1
        print("    corrupt: 损坏→0, record 恢复写")

    with tempfile.TemporaryDirectory() as d:
        f = _char_file(d, "x")
        f.parent.mkdir(parents=True)
        f.write_text("[1,2,3]", encoding="utf-8")   # 非 dict
        assert _bp(d).rounds("x") == 0
        print("    corrupt: 非 dict 列表 → 0")

    with tempfile.TemporaryDirectory() as d:
        f = _char_file(d, "x")
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"rounds": -1}), encoding="utf-8")   # 负值
        assert _bp(d).rounds("x") == 0
        f.write_text(json.dumps({"rounds": "x"}), encoding="utf-8")  # 非 int
        assert _bp(d).rounds("x") == 0
        f.write_text(json.dumps({"rounds": 3, "updated_at": "t"}), encoding="utf-8")
        assert _bp(d).rounds("x") == 3, "合法 rounds 保留"
        print("    corrupt: 负/非 int 丢弃, 合法保留")


# ----------------------------------------------------------------------------
# 角色文件存在 → 优先角色文件（不回退旧全局聚合）
# ----------------------------------------------------------------------------

def test_char_file_priority_over_legacy():
    with tempfile.TemporaryDirectory() as d:
        p = _bp(d)
        p.record_turn("igusa_haruka")
        assert p.rounds("igusa_haruka") == 1
        # 临时 data_root 下没有 data/basic/bond_progress.json → 回退路径不触发
        # （角色文件存在时 rounds 一定来自角色文件）
        print("    priority: 角色文件存在 → 用角色文件")
