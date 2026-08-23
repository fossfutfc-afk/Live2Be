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
    TYPE_BOND,
    TYPE_MMT,
    SessionMeta,
    VNState,
    append_jsonl,
    append_jsonls,
    atomic_write_json,
    read_jsonl,
)
from core.session.events import (
    TYPE_L2D,
    TYPE_MARKER,
    Event,
    M_SESSION_END,
    M_SESSION_START,
    M_VN_ENTER,
    M_VN_STATE,
    make_event,
    marker,
    parse_events,
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
        session_id="20260823_143022_ab12",
        type=TYPE_BOND,
        character_id="igusa_haruka",
        character_name="伊草 遥香",
        created_at="2026-08-23T14:30:22.123456",
    )
    rt = SessionMeta.from_dict(meta.to_dict())
    assert rt.session_id == meta.session_id
    assert rt.type == TYPE_BOND
    assert rt.character_name == "伊草 遥香"
    assert rt.created_at == meta.created_at
    # 纯索引: 无状态字段（状态由 events marker 推导）
    assert "state" not in meta.to_dict() and "parent_session_id" not in meta.to_dict()
    print("    models: SessionMeta 往返（纯索引, 无状态机字段）")


def test_session_meta_defaults_and_tolerance():
    # 坏字段 → 默认, 不 raise
    meta = SessionMeta.from_dict({"type": 42, "character_id": None, "session_id": 99})
    assert meta.type == TYPE_MMT
    assert meta.character_id == ""
    assert meta.session_id == ""
    assert SessionMeta.from_dict(None).session_id == ""
    # to_dict 只含非空字段（小文件原则）
    d = SessionMeta().to_dict()
    assert "character_name" not in d
    print("    models: 默认值 + 坏字段降级 + to_dict 省略空字段")


def test_vn_state_roundtrip():
    vs = VNState(round=12, seed="都点吧，今天我请客。", completed=False,
                 force_after=32, visual={"background": "class_room", "audio": None})
    rt = VNState.from_dict(vs.to_dict())
    assert rt.round == 12 and rt.seed == vs.seed
    assert rt.visual == {"background": "class_room", "audio": None}
    # 坏字段降级
    bad = VNState.from_dict({"round": "x", "force_after": None})
    assert bad.round == 1 and bad.force_after == 32
    print("    models: VNState 往返 + 坏字段降级")


# ----------------------------------------------------------------------------
# events: 事件骨架往返 / 坏骨架丢弃 / marker 构造 / l2d 引用式
# ----------------------------------------------------------------------------

def test_event_roundtrip_and_parse():
    rows = [
        {"seq": 1, "ts": "2026-08-23T15:02:11", "type": "mmt", "subtype": "mmt_chat",
         "payload": {"player": "你好", "reply": "啊、老师…"}},
        {"seq": 2, "ts": "2026-08-23T15:04:12", "type": "bond", "subtype": "story_scene",
         "payload": {"paragraphs": ["她脸红了。"], "beats": [{"text": "x", "emotion": "embarass"}],
                     "picked": "别紧张"}},
        {"seq": 3, "ts": "2026-08-23T15:05:00", "type": "l2d", "subtype": "generate",
         "payload": {"image": "gallery/x.png", "scene_ref": 2}},   # 引用式最小
    ]
    evs = parse_events(rows)
    assert len(evs) == 3
    # 往返无损（复现）
    rt = parse_events([e.to_dict() for e in evs])
    assert [e.to_dict() for e in rt] == [e.to_dict() for e in evs]
    assert evs[2].type == TYPE_L2D and evs[2].payload["image"] == "gallery/x.png"
    print("    events: 三板块往返无损 + l2d 引用式最小")


def test_event_bad_skeleton_dropped():
    bad_rows = [
        {"seq": "x", "ts": "t", "type": "mmt", "subtype": "a"},      # seq 非 int
        {"seq": 2, "ts": "", "type": "mmt", "subtype": "a"},         # ts 空
        {"seq": 3, "ts": "t", "type": "unknown", "subtype": "a"},    # type 不在白名单
        {"seq": 4, "ts": "t", "type": "mmt", "subtype": ""},         # subtype 空
        {"seq": 5, "ts": "t", "type": "mmt", "subtype": "a",
         "payload": [1, 2]},                                          # payload 非 dict → 空
        None,
    ]
    evs = parse_events(bad_rows)
    assert len(evs) == 1 and evs[0].payload == {}
    print("    events: 坏骨架丢弃, payload 非 dict 宽容为空")


def test_marker_construction():
    start = marker(M_SESSION_START, seq=1)
    assert start.type == TYPE_MARKER and start.subtype == M_SESSION_START
    enter = marker(M_VN_ENTER, {"parent_session_id": "abc", "reason": "邀约"}, seq=2)
    assert enter.payload["parent_session_id"] == "abc"
    st = marker(M_VN_STATE, VNState(round=3, seed="s").to_dict(), seq=5)
    assert st.payload["round"] == 3
    end = marker(M_SESSION_END, {"ended": True}, seq=9)
    assert end.payload["ended"] is True
    # make_event 一般事件
    mmt = make_event("mmt", "mmt_chat", {"player": "hi"}, seq=2)
    assert mmt.to_dict()["seq"] == 2
    print("    events: marker 构造（start/enter/state/end）+ make_event")
