"""统一上下文窗口测试（docs/DESIGN_CONTEXT_WINDOW.md, 2026-09-05 定稿）。

覆盖:
    1. render_bond_scene_text——叙事提取（title/句段带 emotion/inner/选项+picked/
       is_end; emotion 缺失不标; 裸字符串段兼容; branches 内容永不出现）
    2. render_events bond/l2d 段——叙事文本而非 payload JSON; marker 跳过
    3. window_messages——倒序装填 / 120 单元预算截断 / 多行单元计数
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.session.events import make_event
from core.session.renderer import (
    render_bond_scene_text,
    render_events,
    window_messages,
)


def _bond_payload(**over):
    p = {
        "input": "（旁白）……",
        "title": "杂草屋的午后",
        "paragraphs": [
            {"text": "（她抱着小水壶, 回头看你时差点被自己绊倒。）", "emotion": "nomal"},
            {"text": "那个……老师, 这边走。", "emotion": "nomal"},
            {"text": "杂草们最近都有好好长高！", "emotion": "smile",
             "inner": "好想让老师夸我……"},
        ],
        "choices": ["认真看每一盆杂草", "问她哪一盆最宝贝"],
        "picked": "问她哪一盆最宝贝",
        "is_end": False,
    }
    p.update(over)
    return p


def test_render_bond_scene_text_full():
    out = render_bond_scene_text(_bond_payload())
    lines = out.split("\n")
    assert lines[0] == "「杂草屋的午后」"                       # title
    assert lines[1] == "（她抱着小水壶, 回头看你时差点被自己绊倒。）（nomal）"   # 句末 emotion
    assert lines[2] == "那个……老师, 这边走。（nomal）"
    assert lines[3] == "杂草们最近都有好好长高！（smile）"
    assert lines[4] == "（好想让老师夸我……）"                  # inner 独立行
    assert "（选项: 认真看每一盆杂草 / 问她哪一盆最宝贝）" in lines
    assert "（选择了: 问她哪一盆最宝贝）" in lines
    assert "本章结束" not in out
    # branches 未选内容永不进上下文（payload 里即使有 branches 键也不渲染）
    out2 = render_bond_scene_text({**_bond_payload(),
                                   "branches": {"认真看每一盆杂草": [{"text": "隐藏分支内容"}]}})
    assert "隐藏分支内容" not in out2


def test_render_bond_scene_text_edge_cases():
    # 无 emotion → 行尾不标; 无 title/choices → 无对应行
    out = render_bond_scene_text({"paragraphs": ["她红着脸。"]})
    assert out == "她红着脸。"
    # 裸字符串段 + dict 混排; emotion 空串不标
    out2 = render_bond_scene_text({
        "paragraphs": [{"text": "一句", "emotion": ""}, "第二句",
                       {"text": "", "emotion": "smile"}]})
    assert out2.split("\n") == ["一句", "第二句"]
    # is_end → 结束标
    assert render_bond_scene_text({"paragraphs": ["她笑了。"], "is_end": True}).endswith(
        "（本章结束）")
    # 空 payload → ""
    assert render_bond_scene_text({}) == ""
    assert render_bond_scene_text({"paragraphs": []}) == ""


def test_render_events_bond_narrative_not_json():
    evs = [make_event("bond", "story_scene", _bond_payload())]
    msgs = render_events(evs)
    assert msgs[0]["role"] == "user" and "旁白" in msgs[0]["content"]
    assert msgs[1]["role"] == "assistant"
    assert "「杂草屋的午后」" in msgs[1]["content"]
    assert "（smile）" in msgs[1]["content"]
    assert "{" not in msgs[1]["content"]            # 非 JSON 全量
    assert "background" not in msgs[1]["content"]   # 结构元数据不进


def test_render_events_l2d_memorial_text():
    evs = [make_event("l2d", "memorial_img", {
        "paragraphs": [{"text": "月光下的天台, 她把那盆杂草递给我。", "emotion": "nomal"}],
        "images": ["/assets/xx.png"]})]
    msgs = render_events(evs)
    assert len(msgs) == 1 and "月光下的天台" in msgs[0]["content"]
    assert "xx.png" not in msgs[0]["content"]       # 图 URL 不进
    # 纯资产 l2d（无段落）→ 跳过
    assert render_events([make_event("l2d", "memorial_img", {"images": ["/a.png"]})]) == []


def test_window_messages_fill_and_cap():
    # 事件流: 若干 mmt（每事件 1-2 条消息）——构造 30 个 mmt 事件
    evs = []
    for i in range(30):
        evs.append(make_event("mmt", "mmt_chat",
                              {"player": f"消息{i}", "reply": f"回复{i}"}))
    # 大预算 → 全装
    msgs = window_messages(evs, max_units=1000)
    assert len(msgs) == 60 and msgs[0]["content"] == "消息0"
    # 小预算 → 倒序保留最近（丢最老）
    small = window_messages(evs, max_units=10)
    assert len(small) <= 11
    assert small[-1]["content"].endswith("回复29")    # 最新的在尾（倒序装填 → 正序输出）
    assert all("消息0" != m["content"] for m in small)   # 最老被挤掉
    # 顺序保持: user/assistant 严格交替从事件尾部延续
    assert small[-2]["content"] == "消息29"


def test_render_events_is_byte_stable():
    """⭐ **同一份事件渲两次必须逐字节相同** —— 这是"前缀缓存"的地基（2026-10-07 收尾 ⑥-2e）。

    真机病根: `render_events` 从前对每条 mmt 回复过 `split_reply_chunks(text)`
    （**没给 rng** ⇒ 走全局 `random`）⇒ 逗号处的切点每轮重掷 ⇒ history 逐字节不稳定
    ⇒ 每轮都 `cache_miss`。

    ⚠️ 判据必须用**长回复**（逗号前落到 6~10 字的弹性区）才抓得住 —— 短回复一次骰子
    都不掷, 拿"回复1"这种文本写的用例永远是绿的（这正是它躲过守门的原因）。
    """
    long_reply = "今天天气不错，要不要一起去天台看看，我带了点心"
    evs = [make_event("mmt", "mmt_chat",
                      {"player": "在吗", "reply": long_reply}, seq=1)]
    first = render_events(evs)
    assert first == render_events(evs) == window_messages(evs, max_units=1000)
    assert all(render_events(evs) == first for _ in range(60))
    # ⭐ 一行 = 一条 assistant 消息（⑥-2e: 引擎不再切句）—— 那条回复只该产出一条
    said = [m for m in first if m["role"] == "assistant"]
    assert len(said) == 1 and said[0]["content"] == f"[mmt_chat] {long_reply}"
    print("    render_events: 逐字节稳定（长回复 60 次重渲同形）+ 一行一条")


def test_window_messages_bond_units_by_lines():
    # bond 场景（多句段多行）按行数占窗——长场景自然挤掉更多旧消息
    bond = make_event("bond", "story_scene", _bond_payload())
    evs = []
    for i in range(8):
        evs.append(make_event("mmt", "mmt_chat", {"player": f"p{i}", "reply": f"r{i}"}))
    evs.append(bond)
    # 预算 10: bond(7 行) + 尾部少量 mmt; 预算 60: 全装
    small = window_messages(evs, max_units=10)
    assert small[-1]["role"] == "assistant" and "杂草屋的午后" in small[-1]["content"]
    assert all("p0" != m["content"] for m in small)
    full = window_messages(evs, max_units=1000)
    assert full[-1]["role"] == "assistant"
