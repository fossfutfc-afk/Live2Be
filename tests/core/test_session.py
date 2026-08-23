# -*- coding: utf-8 -*-
"""core/session 单测 — 存储原语（io）+ 会话模型（models）。

io:     atomic_write_json（原子替换）/ append_jsonl（追加不重写）/ read_jsonl 行级容错
models: SessionMeta / VNState to_dict/from_dict 往返 + 坏字段降级

设计: core/DESIGN_SAVE.md（统一会话目录 + jsonl + 状态机）。

运行: python -m pytest tests/core/test_session.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.session import (
    STATE_ACTIVE,
    STATE_ENDED,
    STATE_PAUSED,
    TYPE_BOND,
    TYPE_MMT,
    SessionMeta,
    VNState,
    append_jsonl,
    append_jsonls,
    atomic_write_json,
    read_jsonl,
)


# ----------------------------------------------------------------------------
# io: 原子写 / append-only / 行级容错
# ----------------------------------------------------------------------------

def test_atomic_write_json(tmp_path):
    p = tmp_path / "meta.json"
    atomic_write_json(p, {"a": 1, "中文": "值"})
    import json
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "中文": "值"}
    # 覆盖写（原子替换, 不残留 temp 文件）
    atomic_write_json(p, {"b": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"b": 2}
    assert not list(tmp_path.glob("._savetmp_*")), "temp 文件应被替换清理"
    print("    io: atomic_write_json 原子替换 + 无 temp 残留")


def test_append_jsonl_no_rewrite(tmp_path):
    p = tmp_path / "history.jsonl"
    append_jsonl(p, {"role": "user", "content": "你好"})
    append_jsonl(p, {"role": "assistant", "content": "嗯…"})
    append_jsonls(p, [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
    rows = read_jsonl(p)
    assert len(rows) == 4
    assert rows[1] == {"role": "assistant", "content": "嗯…"}
    assert rows[3] == {"role": "assistant", "content": "b"}
    print("    io: append_jsonl(s) 追加不重写 + 读回 4 行")


def test_read_jsonl_tolerates_bad_lines(tmp_path):
    p = tmp_path / "history.jsonl"
    p.write_text(
        '{"role": "user", "content": "好"}\n'
        '{"role": "assistant", "content": "嗯"}\n'
        '{"role": "user", "content": "半行"\n'       # 坏行（中断残留）
        '\n'                                          # 空行
        'garbage\n',                                  # 非 JSON
        encoding="utf-8",
    )
    rows = read_jsonl(p)
    assert rows == [{"role": "user", "content": "好"}, {"role": "assistant", "content": "嗯"}]
    # 文件缺失 → []
    assert read_jsonl(tmp_path / "nope.jsonl") == []
    print("    io: read_jsonl 坏行/半行/空行丢弃（宁缺勿错）")


# ----------------------------------------------------------------------------
# models: SessionMeta 往返 + 状态机 + 容错
# ----------------------------------------------------------------------------

def test_session_meta_roundtrip():
    meta = SessionMeta(
        session_id="igusa_haruka_20260823_143022_ab12",
        type=TYPE_BOND,
        character_id="igusa_haruka",
        character_name="伊草 遥香",
        state=STATE_PAUSED,
        parent_session_id="igusa_haruka_20260823_140000_zz99",
        trigger_reason="老师约我放学后见面",
    )
    rt = SessionMeta.from_dict(meta.to_dict())
    assert rt.session_id == meta.session_id
    assert rt.type == TYPE_BOND and rt.state == STATE_PAUSED
    assert rt.parent_session_id == meta.parent_session_id
    assert rt.character_name == "伊草 遥香"
    assert rt.is_open, "paused 应算未结束（可恢复）"
    print("    models: SessionMeta 往返（含 parent 关联 + 中文名）")


def test_session_meta_defaults_and_tolerance():
    assert SessionMeta().is_open                      # 默认 active
    assert not SessionMeta(state=STATE_ENDED).is_open
    # 坏字段 → 默认, 不 raise
    meta = SessionMeta.from_dict({"state": 42, "parent_session_id": 99, "type": None})
    assert meta.state == STATE_ACTIVE
    assert meta.parent_session_id is None
    assert meta.type == TYPE_MMT
    assert SessionMeta.from_dict(None).session_id == ""
    # to_dict 只含非空字段（小文件原则）
    d = SessionMeta().to_dict()
    assert "character_name" not in d and "trigger_reason" not in d
    print("    models: 默认值 + 坏字段降级 + to_dict 省略空字段")


def test_vn_state_roundtrip():
    vs = VNState(round=12, seed="都点吧，今天我请客。", completed=False,
                 force_after=32, visual={"background": "class_room", "audio": None},
                 scenes_flushed=12)
    rt = VNState.from_dict(vs.to_dict())
    assert rt.round == 12 and rt.seed == vs.seed
    assert rt.visual == {"background": "class_room", "audio": None}
    assert rt.scenes_flushed == 12
    # 坏字段降级
    bad = VNState.from_dict({"round": "x", "force_after": None})
    assert bad.round == 1 and bad.force_after == 32
    print("    models: VNState 往返 + 坏字段降级")
