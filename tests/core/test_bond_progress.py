"""BondProgress 单测 — 轮数门槛（羁绊进度系统）。

断言全部基于子串匹配; 用临时目录存进度文件, 不污染 data/basic/。
运行: python -m pytest tests/core/test_bond_progress.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond_progress import BondProgress

PASS = 0
FAIL = 0


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS {name}")
    except Exception as e:  # noqa: BLE001
        FAIL += 1
        print(f"  FAIL {name}: {type(e).__name__}: {e}")


def _tmp_path(tmp: Path) -> Path:
    return tmp / "bond_progress.json"


# ----------------------------------------------------------------------------
# 初始为 0; record_turn 递增; rounds 读回
# ----------------------------------------------------------------------------

def test_zero_and_record():
    with tempfile.TemporaryDirectory() as d:
        p = BondProgress(_tmp_path(Path(d)))
        assert p.rounds("igusa_haruka") == 0, "未记录应返回 0"
        assert p.rounds("no_such_char") == 0, "未知角色应返回 0"
        n1 = p.record_turn("igusa_haruka")
        n2 = p.record_turn("igusa_haruka")
        assert n1 == 1 and n2 == 2, f"递增失败: {n1},{n2}"
        assert p.rounds("igusa_haruka") == 2
        print("    record: 0→1→2, rounds 回读一致")


# ----------------------------------------------------------------------------
# 落盘往返: 新建实例读同一文件, 轮数保留（跨会话累计语义）
# ----------------------------------------------------------------------------

def test_persist_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        path = _tmp_path(Path(d))
        p1 = BondProgress(path)
        p1.record_turn("igusa_haruka")
        p1.record_turn("igusa_haruka")
        p1.record_turn("asagi_mutsuki")
        p2 = BondProgress(path)          # 模拟新会话
        assert p2.rounds("igusa_haruka") == 2, "落盘往返后轮数丢失"
        assert p2.rounds("asagi_mutsuki") == 1
        print("    persist: 换实例读同文件, 累计保留")


# ----------------------------------------------------------------------------
# 多角色独立: 各自计数互不干扰
# ----------------------------------------------------------------------------

def test_multi_char_independent():
    with tempfile.TemporaryDirectory() as d:
        p = BondProgress(_tmp_path(Path(d)))
        p.record_turn("igusa_haruka")
        p.record_turn("igusa_haruka")
        p.record_turn("rikuhachima_aru")
        assert p.rounds("igusa_haruka") == 2
        assert p.rounds("rikuhachima_aru") == 1
        assert p.rounds("asagi_mutsuki") == 0
        print("    multi: 角色间轮数独立")


# ----------------------------------------------------------------------------
# 缺失文件 → 0; record_turn 能重建落盘
# ----------------------------------------------------------------------------

def test_missing_file():
    with tempfile.TemporaryDirectory() as d:
        p = BondProgress(_tmp_path(Path(d)))
        assert not p.path.exists(), "临时文件不应预先存在"
        assert p.rounds("x") == 0, "缺失文件应降级为 0"
        p.record_turn("x")               # 重建
        assert p.path.exists(), "record_turn 应创建文件"
        assert json.loads(p.path.read_text(encoding="utf-8")) == {"x": 1}
        print("    missing: 缺失→0, record 重建落盘")


# ----------------------------------------------------------------------------
# 损坏 JSON / 非 dict / 非法条目 → 降级为空, 不崩
# ----------------------------------------------------------------------------

def test_corrupt():
    with tempfile.TemporaryDirectory() as d:
        path = _tmp_path(Path(d))
        path.write_text("{ 不是 JSON", encoding="utf-8")
        p = BondProgress(path)
        assert p.rounds("x") == 0, "损坏 JSON 应降级为 0"
        p.record_turn("x")               # 降级后仍可写
        assert p.rounds("x") == 1
        print("    corrupt: 损坏→0, record 恢复写")

    with tempfile.TemporaryDirectory() as d:
        path = _tmp_path(Path(d))
        path.write_text("[1,2,3]", encoding="utf-8")   # 非 dict
        assert BondProgress(path).rounds("x") == 0
        print("    corrupt: 非 dict 列表 → 0")

    with tempfile.TemporaryDirectory() as d:
        path = _tmp_path(Path(d))
        path.write_text(json.dumps({"a": "bad", "b": -1, "c": 3, 5: 6}),
                        encoding="utf-8")  # 非法条目混合
        p = BondProgress(path)
        assert p.rounds("a") == 0, "非 int 值应丢弃"
        assert p.rounds("b") == 0, "负值应丢弃"
        assert p.rounds("c") == 3, "合法条目保留"
        print("    corrupt: 混合非法条目, 只认合法")


# ----------------------------------------------------------------------------
# 损坏后 record_turn 覆盖写回（不叠加脏数据）
# ----------------------------------------------------------------------------

def test_corrupt_then_rewrite():
    with tempfile.TemporaryDirectory() as d:
        path = _tmp_path(Path(d))
        path.write_text("{ 坏", encoding="utf-8")
        p = BondProgress(path)
        p.record_turn("igusa_haruka")
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw == {"igusa_haruka": 1}, f"损坏后应重建干净: {raw}"
        print("    rewrite: 损坏文件 record 后重建为干净单键")


def main() -> None:
    print("BondProgress 单测（轮数门槛）")
    print("=" * 44)
    check("初始 0 + 递增", _t_zero_and_record)
    check("落盘往返保留", _t_persist_roundtrip)
    check("多角色独立", _t_multi_char_independent)
    check("缺失文件降级", _t_missing_file)
    check("损坏 JSON 降级", _t_corrupt)
    check("损坏后重建干净", _t_corrupt_then_rewrite)
    print("=" * 44)
    if FAIL:
        print(f"结果: {PASS} PASS / {FAIL} FAIL")
        sys.exit(1)
    print(f"结果: {PASS} PASS / 0 FAIL — 全部通过")


if __name__ == "__main__":
    main()
