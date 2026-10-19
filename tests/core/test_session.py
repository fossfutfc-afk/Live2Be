"""core/session 单测 — 存储原语（io）+ 会话模型（models）。

io:     atomic_write_json（原子替换）/ append_jsonl（追加不重写）/ read_jsonl 行级容错
models: SessionMeta / VNState to_dict/from_dict 往返 + 坏字段降级

设计: core/session/.md（统一会话目录 + jsonl + 状态机）。

运行: python -m pytest tests/core/test_session.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

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
    M_SESSION_END,
    M_SESSION_START,
    M_VN_ENTER,
    M_VN_EXIT,
    M_VN_STATE,
    TYPE_L2D,
    TYPE_MARKER,
    make_event,
    marker,
    parse_events,
)
from core.session.renderer import (
    filter_bond,
    render_events,
    render_timeline,
    session_status,
)
from core.session.store import SessionStore

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
         "payload": {"paragraphs": ["她脸红了。"], "beats": [{"text": "x", "emotion": "embarrass"}],
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


# ----------------------------------------------------------------------------
# renderer: 事件流 → LLM 消息 / 回放过滤 / 状态推导 / brain 时间线
# ----------------------------------------------------------------------------

def _session_events():
    """典型会话: MMT 3 动作（同轮）→ VN 进 → bond 2 场 → 收尾。"""
    return [
        marker(M_SESSION_START, seq=1),
        make_event("mmt", "mmt_chat", {"player": "老师你看！", "reply": "啊、好看吧？"}, seq=2),
        make_event("mmt", "mmt_send_media", {"player": "", "reply": "",
                                             "media_type": "image", "image": "天台"}, seq=3),
        make_event("mmt", "mmt_chat", {"player": "", "reply": "是我拍的…"}, seq=4),
        marker(M_VN_ENTER, {"parent_session_id": "root_1", "reason": "邀约"}, seq=5),
        make_event("bond", "story_scene",
                   {"input": "（旁白）基于「邀约」…", "paragraphs": ["她红着脸。"],
                    "picked": "别紧张"}, seq=6),
        marker(M_VN_STATE, {"round": 1, "seed": "别紧张"}, seq=7),
        make_event("bond", "story_end",
                   {"input": "别紧张", "paragraphs": ["她笑了。"]}, seq=8),
        marker(M_VN_EXIT, seq=9),
        marker(M_SESSION_END, {"ended": True}, seq=10),
    ]


def test_render_events_messages():
    evs = parse_events([e.to_dict() for e in _session_events()])
    msgs = render_events(evs)
    # MMT 3 动作: 只有第一个带 player → 1 条 user; 3 条 assistant（含无 reply 的 send_media）
    assert msgs[0] == {"role": "user", "content": "老师你看！"}
    assert msgs[1] == {"role": "assistant", "content": "[mmt_chat] 啊、好看吧？"}
    assert msgs[2] == {"role": "assistant", "content": "[mmt_send_media]"}
    assert msgs[3] == {"role": "assistant", "content": "[mmt_chat] 是我拍的…"}
    # bond: input → user + 叙事提取 assistant（2026-09-05: 不再整 payload JSON——
    # 上下文只放"发生过什么的叙事 + 情绪"; 段落无 emotion → 不标, 原样句段文本）
    assert msgs[4]["role"] == "user" and "旁白" in msgs[4]["content"]
    assert msgs[5] == {"role": "assistant", "content": "她红着脸。"}
    # 第二个 bond 的 input=上一场 picked
    assert msgs[6] == {"role": "user", "content": "别紧张"}
    # marker/l2d 不产生消息
    assert all(m["role"] in ("user", "assistant") for m in msgs)
    assert len(msgs) == 8
    print("    render_events: mmt 同轮去重 + bond 叙事提取 + marker/l2d 跳过")


def test_render_events_roundtrip_with_engine_format():
    """渲染结果与引擎 history 格式一致（恢复 = start_session + 塞回 render 消息）。"""
    evs = parse_events([e.to_dict() for e in _session_events()])
    msgs = render_events(evs)
    # mmt 历史格式: "[mmt_chat] 回复"（momotalk._finish_turn_list 同款）
    assert msgs[1]["content"].startswith("[mmt_chat] ")
    # bond 历史格式: 叙事文本（2026-09-05——同 render_bond_scene_text;
    # 与引擎 history 同构的改动见 bond_story, 此断言 = 渲染无结构噪音）
    assert "她红着脸。" in msgs[5]["content"]
    assert "{" not in msgs[5]["content"], "bond assistant 应为叙事文本（非 JSON）"
    print("    render_events: 与引擎 history 格式一致（恢复零转换）")


def test_render_events_merges_story_pick_supplement():
    """★ **补录裁决**在模型窗口里同样物化（2026-09-21）——与正常裁决过的板**逐字同形**。

    退出补录的板（`picked=None`）+ 后来补的 `bond/story_pick` ⇒ 渲染出来的
    assistant 行必须与"板自带 picked"的那次一模一样（否则 A1"live 与回放同形"就破了）;
    补录事件自己**不产生**任何消息（它不是板）。
    """
    recs = [{"character": "igusa_haruka", "text": "……老师，你来了。"},
            {"character": "sensei", "text": "选A"},
            {"character": "sensei", "text": "选B"}]
    payload = {"records": recs, "paragraphs": [{"text": "……老师，你来了。"}],
               "choices": ["选A", "选B"], "input": "（种子）"}
    split = parse_events([
        make_event("bond", "story_scene", payload, seq=1).to_dict(),
        make_event("bond", "story_pick",
                   {"picked": "选B", "board_seq": 1}, seq=2).to_dict(),
    ])
    inline = parse_events([
        make_event("bond", "story_scene",
                   {**payload, "picked": "选B"}, seq=1).to_dict(),
    ])
    got, want = render_events(split), render_events(inline)
    assert got == want, (got, want)
    assert any("选B" in m["content"] for m in got)      # 物化成"老师：选B"
    assert not any("选A" in m["content"] for m in got)  # 未选候选不出现（同 v2 口径）
    print("    render_events: 补录裁决与板内 picked 逐字同形（补录本身不产生消息）✓")


def test_filter_bond_and_status():
    evs = parse_events([e.to_dict() for e in _session_events()])
    bonds = filter_bond(evs)
    assert len(bonds) == 2 and all(e.type == "bond" for e in bonds)
    st = session_status(evs)
    assert st["ended"] is True
    assert st["in_vn"] is False              # vn_exit 后 → 不在 VN
    assert st["parent_session_id"] == "root_1"
    assert st["vn_state"]["round"] == 1      # 取最后一个 vn_state marker（调用方结合 in_vn 判断）
    print("    filter_bond + session_status: 结束态推导")


def test_session_status_interrupted_vn():
    """中断（无 session_end）: 无标记即中断; 崩溃在 VN 中 → in_vn=True + vn_state。"""
    evs = parse_events([e.to_dict() for e in [
        marker(M_SESSION_START, seq=1),
        marker(M_VN_ENTER, {"parent_session_id": "root_1"}, seq=2),
        make_event("bond", "story_scene", {"paragraphs": ["x"]}, seq=3),
        marker(M_VN_STATE, {"round": 5, "seed": "继续吧", "visual": {"background": "rooftop"}}, seq=4),
    ]])
    st = session_status(evs)
    assert st["ended"] is False              # 无 session_end = 中断
    assert st["in_vn"] is True               # 崩溃在 VN 中
    assert st["parent_session_id"] == "root_1"
    assert st["vn_state"] is not None and st["vn_state"]["round"] == 5
    assert st["vn_state"]["visual"] == {"background": "rooftop"}
    # 纯 MMT 会话（无 vn_enter）
    st2 = session_status(parse_events([
        marker(M_SESSION_START, seq=1),
        make_event("mmt", "mmt_chat", {"player": "hi", "reply": "嗯"}, seq=2)]))
    assert st2["in_vn"] is False and st2["parent_session_id"] is None
    print("    session_status: 中断=VN 中推导（in_vn + vn_state 取最后）")


def test_render_timeline_brain():
    evs = parse_events([e.to_dict() for e in _session_events()])
    tl = render_timeline(evs)
    assert "【MMT对话】" in tl and "【羁绊剧情】" in tl
    assert "玩家: 老师你看！" in tl and "角色: 是我拍的…" in tl
    assert "她红着脸。" in tl
    assert "【L2D生成】" not in tl           # 本会话无 l2d
    # 不截断（2026-09-13, Q26 落地）: 原 max_paragraph_chars 已删——长板全文保留,
    # 因为 Round A 靠它看见完整情绪弧与 verbatim 可复制的原话
    long = [make_event("bond", "story_scene", {"paragraphs": ["长" * 300]}, seq=1)]
    tl2 = render_timeline(long)
    assert "长" * 300 in tl2 and "…" not in tl2
    # 表情标注（2026-08-28）: 段落显式带 emotion → 段落后 (emotion); 缺省段不标注
    with_emo = [make_event("bond", "story_scene", {
        "paragraphs": [{"text": "她低头笑了。", "emotion": "smile"},
                       {"text": "（沉默片刻）"}],
    }, seq=1)]
    tl3 = render_timeline(with_emo)
    assert "她低头笑了。 (smile)" in tl3
    assert "（沉默片刻）" in tl3 and " (smile)" not in tl3.split("（沉默片刻）")[1]
    print("    render_timeline: 板块标签 + 长板不截断 + 表情标注（brain 消化输入）")


def test_render_timeline_indexed():
    """T14: `indexed=True` → 记录级行索引（LLM 抄行号的唯一词汇表）。"""
    evs = parse_events([
        make_event("mmt", "mmt_chat", {"player": "你好呀", "reply": "库呼呼～"}, seq=2).to_dict(),
        make_event("bond", "story_scene", {
            "paragraphs": [{"text": "……这块，给你。", "emotion": "smile"},
                           {"text": "刚才推过来那块是唯一一块没被我动过的。"}],
            "picked": "那就谢谢了",
        }, seq=28).to_dict(),
    ])
    tl = render_timeline(evs, indexed=True)
    lines = tl.splitlines()
    print("    ---- indexed 形态 ----")
    for ln in lines:
        print(f"      {ln}")
    # 事件头（板指针抄它）
    assert "[2] 【MMT对话】" in lines
    assert "[28] 【羁绊剧情】" in lines
    # 记录（verbatim 抄它）——索引 = paragraphs 的**数组下标**, 不是渲染序
    assert "[2.0] 玩家: 你好呀" in lines
    assert "[2.1] 角色: 库呼呼～" in lines
    assert "[28.0] ……这块，给你。 (smile)" in lines
    assert "[28.1] 刚才推过来那块是唯一一块没被我动过的。" in lines
    # 玩家裁决行: 不在 paragraphs 里 → 独立位 `.p`
    assert "[28.p] 老师: 那就谢谢了" in lines
    # 一记录一行（现行形态是一事件一行 + `" / "` 拼接）
    assert len(lines) == 7, lines
    assert not any(" / " in ln for ln in lines)
    # 缺省形态不变（上下文窗口 / 回放仍走它）
    assert " / " in render_timeline(evs)
    assert "[28.0]" not in render_timeline(evs)
    # ★ 不变量: indexed 形态下**每一行都必须可寻址**（LLM 指得到才叫索引）
    from contract.timeline_index import parse_index
    for ln in lines:
        head = ln.split(" ", 1)[0]
        assert parse_index(head) is not None, f"行不可寻址: {ln!r}"
    print("    render_timeline(indexed): 记录级行索引 + 板指针 + 裁决行 `.p`")


def test_digest_record_prompt_matches_index_format():
    """镜像防漂移（`AGENTS.md`「产品决策」）: prompt 描述的形态必须与渲染器**同源**。

    2026-09-15 之前这里是 `每行 [seq N]`——而渲染器的 `[seq N]` 前缀**从未被消费**
    （`event_seq` 被丢弃 + 被覆写成常量）。现在两侧都换成记录级索引,
    任何一侧单独漂移都会让 Round A 抄出行号却指不到东西（**静默取错, 不报错**）。
    """
    from llm.prompts import load_prompt
    text = load_prompt("digest_record")
    assert "[seq " not in text, "prompt 仍描述已删除的 `[seq N]` 形态"
    for form in ("[28]", "[28.3]", "[28.p]"):
        assert form in text, f"prompt 未描述索引形态 {form}"
    print("    digest Round A prompt 与时间线索引形态同源（无 `[seq N]` 残留）")


def test_timeline_index_vocabulary():
    """`contract.timeline_index`: 渲染/解析**同源**（漂移 = 静默取错原文）。"""
    from contract.timeline_index import (
        REC_PICKED,
        format_event,
        format_record,
        parse_index,
        parse_index_list,
    )

    assert format_event(28) == "[28]"
    assert format_record(28, 3) == "[28.3]"
    assert format_record(28, REC_PICKED) == "[28.p]"
    # 往返（渲染 → 解析）自洽
    assert parse_index(format_event(28)) == (28, "")
    assert parse_index(format_record(28, 3)) == (28, 3)
    assert parse_index(format_record(28, REC_PICKED)) == (28, "p")
    # 宽松: 裸数字 / 带方括号 / 空白容忍
    assert parse_index("28.3") == (28, 3)
    assert parse_index(" [ 28 . 3 ] ") == (28, 3)
    # **绝不抛**: 坏索引 → None（丢掉那一条, 不废整包）
    for bad in ("", "abc", "[", "28.x", None, 28.3, "[]", "[-1]"):
        assert parse_index(bad) is None, bad
    # 数组: 坏项逐条丢弃
    assert parse_index_list(["28.3", "坏", "20.p", 7, None]) == [(28, 3), (20, "p"), (7, "")]
    assert parse_index_list("28.3") == []          # 非数组整体拒
    assert parse_index_list(None) == []
    print("    timeline_index: 渲染/解析同源往返 + 坏索引逐条丢弃（绝不抛）")


# ----------------------------------------------------------------------------
# store: 会话生命周期（create/open_vn/append/finish/list_open/resume）
# ----------------------------------------------------------------------------

def test_store_create_and_append(tmp_path):
    st = SessionStore(tmp_path)
    meta = st.create("igusa_haruka", "伊草 遥香")
    assert meta.type == "conversation" and meta.character_id == "igusa_haruka"
    assert meta.session_id, "应生成 session_id"
    # create 已写 meta + session_start marker
    assert (st.char_dir("igusa_haruka") / "meta.json").exists()
    evs = st.events("igusa_haruka", meta.session_id)
    assert len(evs) == 1 and evs[0].subtype == "session_start" and evs[0].seq == 1
    # append seq 递增
    e1 = st.append_event("igusa_haruka", meta.session_id,
                         make_event("mmt", "mmt_chat", {"player": "hi", "reply": "嗯"}))
    e2 = st.append_marker("igusa_haruka", meta.session_id, "vn_state", {"round": 1})
    assert e1.seq == 2 and e2.seq == 3
    # 新 store 实例（模拟重启）→ 从文件恢复 seq
    st2 = SessionStore(tmp_path)
    e3 = st2.append_event("igusa_haruka", meta.session_id,
                          make_event("mmt", "mmt_chat", {"reply": "继续"}))
    assert e3.seq == 4, "重启后 seq 应从文件续"
    print("    store: create + seq 递增 + 重启续 seq")


def test_store_enter_vn_and_status(tmp_path):
    st = SessionStore(tmp_path)
    root = st.create("igusa_haruka")
    assert root.type == "conversation"
    sid = st.enter_vn("igusa_haruka", root.session_id, title="邀约")
    assert sid == root.session_id
    # vn_enter 事件 payload 记 chapter_title（2026-09-05 reason 退役）
    vn_enter = [e for e in st.events("igusa_haruka", sid)
                if e.subtype == "vn_enter"][0]
    assert vn_enter.payload.get("chapter_title") == "邀约"
    st.append_event("igusa_haruka", sid,
                    make_event("bond", "story_scene", {"paragraphs": ["她脸红了。"]}))
    st.append_marker("igusa_haruka", sid, "vn_state", {"round": 1, "seed": "继续"})
    # 2026-09-21: 原 `update_session_progress()`（自称"[废弃]…无人读"的 v1 兼容方法）已删
    st.write_bond_gap("igusa_haruka", 2)
    # 中断（未 finish）→ resume 推导 in_vn（同会话单流）
    r = st.resume("igusa_haruka", sid)
    assert r["meta"].type == "conversation"
    assert r["status"]["in_vn"] is True
    assert r["status"]["parent_session_id"] is None     # 单流无 parent
    assert r["status"]["vn_state"]["round"] == 1
    # 单目录: mmt/bond 事件同文件（session_start + vn_enter + bond + vn_state）
    evs = st.events("igusa_haruka", sid)
    assert [e.subtype for e in evs] == ["session_start", "vn_enter", "story_scene", "vn_state"]
    import json as _json
    prog = _json.loads((st.progress_path("igusa_haruka", sid)).read_text(encoding="utf-8"))
    # 2026-09-02: progress 语义 = 距上次 bond 剧情的 MMT 轮数（rounds_since_bond）
    assert prog["rounds_since_bond"] == 2
    assert st.read_bond_gap("igusa_haruka") == 2        # 读方法同源
    print("    store: enter_vn（单流）+ resume 推导 in_vn + 同文件事件 + progress(rounds_since_bond) 落盘")


def test_store_finish_and_list_open(tmp_path):
    st = SessionStore(tmp_path)
    a = st.create("igusa_haruka")
    b = st.create("rikuhachima_aru")
    st.finish("igusa_haruka", a.session_id, ended=True)   # a 结束
    # list_open: 只列未结束（b）
    opens = st.list_open()
    assert [m.session_id for m in opens] == [b.session_id]
    # 全部结束 → 空
    st.finish("rikuhachima_aru", b.session_id)
    assert st.list_open() == []
    # finish 后 resume 推导 ended
    r = st.resume("igusa_haruka", a.session_id)
    assert r["status"]["ended"] is True
    print("    store: finish(session_end) + list_open 过滤未结束")


def test_store_meta_tolerance(tmp_path):
    st = SessionStore(tmp_path)
    assert st.meta("no_char", "no_such_id").session_id == ""     # 缺失 → 空 meta
    assert st.events("no_char", "no_such_id") == []              # 缺失 → 空事件
    print("    store: 缺失 meta/events → 空（宁缺勿错）")


# ----------------------------------------------------------------------------
# 引擎接入: momotalk agent_turn → 落 mmt 事件（同轮去重）+ session progress
# ----------------------------------------------------------------------------

def test_engine_mmt_records_events(tmp_path):
    from core.bond.bond_progress import BondProgress
    from core.mmt.engine import MomoTalkEngine

    class LLM:
        def chat(self, messages, **kw):
            # 行协议（⑥-2e）: 一行一条 JSON —— 消息行说话 / 操作行做事, 任意交错
            return ('{"text": "第一句"}\n'
                    '{"action": "mmt_send_media",'
                    ' "payload": {"media_type": "image", "image": "天台夕阳"}}\n'
                    '{"text": "第三句"}')

        def format_messages(self, **kw):
            return []

    st = SessionStore(tmp_path)
    engine = MomoTalkEngine(ROOT / "config" / "characters", LLM(),
                            bond_progress=BondProgress(data_root=tmp_path), store=st)
    engine.start_session("igusa_haruka")
    meta = st.create("igusa_haruka")
    engine.attach_session(meta.session_id)
    r = engine.agent_turn("你好呀")

    evs = st.events("igusa_haruka", meta.session_id)
    # 行序 = 事件序: 话1 → send_media → 话2
    assert [e.subtype for e in evs] == [
        "session_start", "mmt_chat", "mmt_send_media", "mmt_chat"]
    assert evs[1].payload["player"] == "你好呀"        # 第一条消息行挂 player
    assert "player" not in evs[2].payload              # 后续行不带（render 去重约定）
    assert evs[2].payload["image"] == "天台夕阳"        # 干净动作字段保留
    assert evs[1].payload["reply"] == "第一句"
    assert evs[3].payload["reply"] == "第三句"          # 交错: 图后还能说话
    assert evs[2].payload["reply"] == ""               # 操作行不上屏（落库空串, 历史格式）
    # session progress = 距上次 bond 剧情的轮数（rounds_since_bond, 列表整体一轮）
    import json as _json
    prog = _json.loads(st.progress_path("igusa_haruka", meta.session_id).read_text(encoding="utf-8"))
    assert prog["rounds_since_bond"] == 1
    # render 回读: 同轮多条消息只有 1 条 user
    msgs = render_events(st.events("igusa_haruka", meta.session_id))
    assert sum(1 for m in msgs if m["role"] == "user") == 1
    assert msgs[1]["content"] == "[mmt_chat] 第一句"
    assert msgs[-1]["content"].startswith("[mmt_chat] 第三句")
    print("    engine-mmt: 消息流（话→图→话 交错, 旧 reply 前置）→ 事件流顺序 + progress + render 回读")


def test_engine_mmt_no_store_no_events(tmp_path):
    """store 未注入 → 不落事件（向后兼容, 现有引擎行为不变）。"""
    from core.bond.bond_progress import BondProgress
    from core.mmt.engine import MomoTalkEngine

    class LLM:
        def chat(self, messages, **kw):
            return '{"text": "嗯"}'

        def format_messages(self, **kw):
            return []

    engine = MomoTalkEngine(ROOT / "config" / "characters", LLM(),
                            bond_progress=BondProgress(data_root=tmp_path))  # 无 store
    engine.start_session("igusa_haruka")
    engine.agent_turn("hi")
    # 无 store → 不产生会话目录/事件（仅 BondProgress 写 progress.json, 正常）
    assert not (tmp_path / "igusa_haruka" / "sessions").exists()
    print("    engine-mmt: 无 store → 零事件（兼容）")


# ----------------------------------------------------------------------------
# 事件流恢复入口（store.resume + engine.resume_session, core/session/.md）
# ----------------------------------------------------------------------------

def test_engine_resume_rebuilds_history(tmp_path):
    """中断会话 resume: 重建 history（render_events 同格式）→ 继续聊天续写同一会话。"""
    from core.mmt.engine import MomoTalkEngine
    from core.session import SessionStore

    class Scripted:
        def __init__(self, *scripts):
            self._s = list(scripts)
        def chat(self, messages, **kw):
            if "记忆巩固" in messages[0]["content"]:      # digest 调用 → 空消化
                return {"summary": "", "facts": [], "beliefs": [], "relations": []}
            if not self._s:
                raise RuntimeError("脚本耗尽")
            return self._s.pop(0)
        def format_messages(self, **kw):
            return []

    st = SessionStore(tmp_path)
    chat1 = '{"text": "你好呀"}'
    engine = MomoTalkEngine(ROOT / "config" / "characters", Scripted(chat1), store=st)
    engine.start_session("igusa_haruka")
    root = st.create("igusa_haruka", "遥香")
    engine.attach_session(root.session_id)
    engine.agent_turn("你好")                     # 1 轮; 不 finish = 中断

    chat2 = '{"text": "继续呀"}'
    engine2 = MomoTalkEngine(ROOT / "config" / "characters", Scripted(chat2), store=st)
    info = engine2.resume_session("igusa_haruka", root.session_id)
    assert info["status"]["ended"] is False
    assert info["history_len"] == 2, info
    assert engine2.history[0] == {"role": "user", "content": "你好"}
    assert "[mmt_chat]" in engine2.history[1]["content"]

    r = engine2.agent_turn("继续聊聊")
    assert r.ok
    evs = st.events("igusa_haruka", root.session_id)
    assert len(evs) == 3, [e.subtype for e in evs]   # session_start + 2 个 mmt_chat
    print("    resume: 重建 history + 继续聊天 + 事件流续写同一会话")


def test_engine_resume_rejects_ended(tmp_path):
    import pytest

    from core.mmt.engine import MomoTalkEngine
    from core.session import SessionStore

    class LLM:
        def chat(self, messages, **kw):
            return '{"text": "嗯"}'
        def format_messages(self, **kw):
            return []

    st = SessionStore(tmp_path)
    engine = MomoTalkEngine(ROOT / "config" / "characters", LLM(), store=st)
    engine.start_session("igusa_haruka")
    root = st.create("igusa_haruka", "遥香")
    engine.attach_session(root.session_id)
    engine.agent_turn("你好")
    st.finish("igusa_haruka", root.session_id, ended=True)   # 正常收尾
    engine2 = MomoTalkEngine(ROOT / "config" / "characters", LLM(), store=st)
    with pytest.raises(RuntimeError):
        engine2.resume_session("igusa_haruka", root.session_id)
    print("    resume: ended 会话拒绝恢复")


def test_engine_resume_history_window(tmp_path):
    """resume 时 AI 只拿统一上下文窗口（2026-09-05: 120 单元预算 = rounds×3——
    每条消息单行计 1 单元; bond 句段按行占窗）——与实时 _trim_history 一致。

    造 80 轮 mmt 事件（160 条, 远超 120 单元）→ resume → 截断为最近 120 条。
    """
    from core.mmt.engine import MomoTalkEngine
    from core.session import SessionStore
    from core.session.events import make_event

    class Scripted:
        def chat(self, messages, **kw):
            if "记忆巩固" in messages[0]["content"]:      # digest 分支（resume 不触发, 防御）
                return {"summary": "（空）", "facts": [], "beliefs": [],
                        "relations": [], "affection_exp_delta": 0}
            return '{"text": "嗯嗯"}'
        def format_messages(self, **kw):
            return []

    st = SessionStore(tmp_path)
    root = st.create("igusa_haruka", "遥香")
    for i in range(80):                                   # 80 轮 = 160 条, 远超 120 单元
        st.append_event("igusa_haruka", root.session_id,
                        make_event("mmt", "mmt_chat", {"player": f"p{i}", "reply": f"r{i}"}))

    engine = MomoTalkEngine(ROOT / "config" / "characters", Scripted(), store=st)
    info = engine.resume_session("igusa_haruka", root.session_id)
    assert info["history_len"] == 40 * 3, info            # 120 单元（默认 rounds 40 × 3）
    assert engine.history[0]["content"] == "p20", engine.history[0]   # 丢最老 40 条(20轮)
    assert engine.history[-2]["content"] == "p79", engine.history[-2] # 窗口终点 = 最新
    assert engine.history[1]["role"] == "assistant"
    print("    resume 窗口: 80 轮事件 → 最近 120 单元（40×3）, 与实时 _trim_history 一致")
