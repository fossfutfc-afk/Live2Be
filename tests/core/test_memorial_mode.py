# -*- coding: utf-8 -*-
"""纪念子模式引擎层单测 — memorial_enter/exit 状态机（§4.7, 2026-08-24）。

send_vn_scene 双 registry 解析（story 域含 enter, memorial 域含 exit）:
    - enter 轮 → BondScene.memorial_prompt（生图总结）+ in_memorial=True
    - exit 轮 → BondScene.memorial_exit + in_memorial=False
    - 状态约束: 纪念模式内只许 exit / 非纪念模式 exit 拒绝 / 一段至多一次 enter
      （违规 → feedback 回灌 → LLM 修正重试）

运行: python -m pytest tests/core/test_memorial_mode.py
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine, SceneLoopError
from core.momotalk import MomoTalkEngine
from core.session import SessionStore
from llm.image_gen import GeneratedImage

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

ENTER = {"action": "memorial_enter", "payload": {
    "prompt": "湖边, 黑发少女含泪抬头, 月光",
    "paragraphs": [{"text": "（她终于抬起头）老师……我这种人……", "emotion": "embarrass"}],
    "choices": ["抱住她", "陪她坐着"]}}
EXIT = {"action": "memorial_exit", "payload": {
    "paragraphs": "遥香吸了吸鼻子, 破涕为笑。"}}
SCENE = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "她们蹲在路边摊前。", "emotion": "smile"}],
    "choices": ["一起吃"],
    "branches": {"一起吃": [{"text": "她递来一串章鱼烧。", "emotion": "smile"}]}}}
STORY_END = {"action": "story_end", "payload": {
    "paragraphs": [{"text": "（夜色里, 她的影子终于不再躲闪。）", "emotion": "smile"}]}}


class ScriptedLLM:
    """chat 兼容面: 按调用顺序返回预设 dict; snapshots 记 messages（断言 feedback）。
    emotion 标注调用（2026-09-02 骨架 emotion 丢弃 → 全量回填）自动返回全 nomal
    数组（从 system 编号行数推断句数）, 不消耗脚本。"""

    def __init__(self, *scripts: dict):
        self._scripts = list(scripts)
        self.snapshots: list[list[dict]] = []

    def chat(self, messages, temperature=0.8, max_tokens=1536, response_format="text"):
        self.snapshots.append([dict(m) for m in messages])
        import re as _re
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last:               # emotion 标注 → 全 nomal
            n = len(_re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        if "变更句数组" in last:                  # place 标注（P3a）→ 无变更
            return []
        if not self._scripts:
            raise RuntimeError("脚本耗尽")
        return self._scripts.pop(0)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


def _vn(llm) -> BondStoryEngine:
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session(CHARACTER)
    return vn


def _store_engine(llm, tmp_path: Path) -> tuple[MomoTalkEngine, SessionStore, str]:
    """MomoTalk 引擎 + 事件流会话（run_bond_story_vn 的 main 层前置）。"""
    st = SessionStore(tmp_path)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    return engine, st, root.session_id


def _last_fb(llm: ScriptedLLM) -> str:
    """最近一次**场景轮** chat 调用的最后一条 user 消息（feedback 回灌内容）。
    标注调用（user 含"情绪标签数组"）跳过——它们不是场景轮。"""
    for msgs in reversed(llm.snapshots):
        last = msgs[-1]["content"] if len(msgs) > 1 else ""
        if "情绪标签数组" not in last:
            return last
    return ""


def _scene_msgs(llm: ScriptedLLM) -> list[list[dict]]:
    """过滤标注调用后的场景轮 snapshots（标注不算场景轮）。"""
    return [msgs for msgs in llm.snapshots
            if "情绪标签数组" not in (msgs[-1]["content"] if len(msgs) > 1 else "")]


def test_enter_sets_memorial_prompt():
    vn = _vn(ScriptedLLM(ENTER))
    scene = vn.send_vn_scene("（湖边）")
    assert scene.memorial_prompt == "湖边, 黑发少女含泪抬头, 月光", scene.memorial_prompt
    # 2026-09-02: 骨架 emotion 丢弃 → 标注层回填（stub 返回 nomal）
    assert scene.paragraphs == [{"text": "（她终于抬起头）老师……我这种人……",
                                 "emotion": "nomal"}]
    assert scene.choices == ["抱住她", "陪她坐着"]
    assert not scene.is_end
    assert vn.in_memorial is True, "enter 后应处于纪念模式"
    print("    enter: memorial_prompt + 场景内容解析, in_memorial=True")


def test_exit_returns_to_bond():
    vn = _vn(ScriptedLLM(ENTER, EXIT, SCENE))
    vn.send_vn_scene("（湖边）")                       # enter
    scene2 = vn.send_vn_scene("抱住她")               # exit
    assert scene2.memorial_exit is True, "exit 轮应打标记"
    assert scene2.paragraphs == [{"text": "遥香吸了吸鼻子, 破涕为笑。"}], scene2.paragraphs
    assert vn.in_memorial is False, "exit 后应回 bond"
    scene3 = vn.send_vn_scene("（继续）")             # 回 bond 后 story_scene 正常
    assert scene3.paragraphs == [{"text": "她们蹲在路边摊前。", "emotion": "nomal"}]
    assert vn.in_memorial is False
    print("    exit: memorial_exit 标记 + 回 bond + story_scene 继续")


def test_story_scene_inside_memorial_rejected():
    """纪念模式内出 story_scene → feedback 回灌 → LLM 修正为 exit。"""
    llm = ScriptedLLM(ENTER, SCENE, EXIT)
    vn = _vn(llm)
    vn.send_vn_scene("（湖边）")                       # enter
    scene2 = vn.send_vn_scene("抱住她")
    # 第二次调用（SCENE）被状态机拒绝 → 第三次（EXIT）成功
    fb = _last_fb(llm)
    assert "纪念模式" in fb and "memorial_exit" in fb, fb
    assert scene2.memorial_exit is True
    assert vn.in_memorial is False
    print("    enter 后出 story_scene: 拒绝回灌 → 修正为 exit 成功")


def test_exit_outside_memorial_rejected():
    """非纪念模式出 memorial_exit → 拒绝 → 修正为 story_scene。"""
    llm = ScriptedLLM(EXIT, SCENE)
    vn = _vn(llm)
    scene = vn.send_vn_scene("（开场）")
    fb = _last_fb(llm)
    assert "不在纪念模式" in fb, fb
    assert scene.paragraphs == [{"text": "她们蹲在路边摊前。", "emotion": "nomal"}]
    assert scene.memorial_exit is False
    print("    exit 在非纪念模式: 拒绝回灌 → 修正为 story_scene")


def test_second_enter_rejected():
    """纪念模式内二次 enter → 被「模式内只许 exit」拦 → 修正为 exit。"""
    llm = ScriptedLLM(ENTER, ENTER, EXIT)
    vn = _vn(llm)
    vn.send_vn_scene("（湖边）")                       # 第一次 enter 成功
    scene2 = vn.send_vn_scene("（继续）")
    fb = _last_fb(llm)
    assert "纪念模式" in fb and "memorial_exit" in fb, fb
    assert scene2.memorial_exit is True, "二次 enter 被拒后修正为 exit"
    assert vn.in_memorial is False, "exit 后回 bond"
    print("    模式内二次 enter: 拒绝回灌（只许 exit）→ 修正为 exit")


def test_enter_after_exit_rejected():
    """一段剧情至多一次: exit 回 bond 后再 enter → 「至多一次」拒绝 → 修正为 story_scene。"""
    llm = ScriptedLLM(ENTER, EXIT, ENTER, SCENE)
    vn = _vn(llm)
    vn.send_vn_scene("（一）")                         # enter
    vn.send_vn_scene("（二）")                         # exit → 回 bond
    scene3 = vn.send_vn_scene("（三）")               # 再 enter → 至多一次拒绝
    fb = _last_fb(llm)
    assert "至多一次" in fb, fb
    assert scene3.paragraphs == [{"text": "她们蹲在路边摊前。", "emotion": "nomal"}]
    assert scene3.memorial_prompt == "", "exit 后的 enter 被拒, 不应再带 prompt"
    print("    exit 后再 enter: 拒绝回灌（至多一次）→ 修正为 story_scene")


def test_memorial_exit_schema_available():
    """memorial_exit_schema 返回 memorial 域 schema 文本（vn_cli 作 system_note 注入）。"""
    vn = _vn(ScriptedLLM())
    schema = vn.memorial_exit_schema()
    assert "memorial_exit" in schema, schema
    assert "paragraphs" in schema
    print("    memorial_exit_schema: 含动作名 + 字段约束")


def test_state_resets_on_new_session():
    """start_session 重置纪念状态（新剧情从 bond 开始）。"""
    llm = ScriptedLLM(ENTER, EXIT)
    vn = _vn(llm)
    vn.send_vn_scene("（一）")                         # enter
    assert vn.in_memorial is True
    vn.start_session(CHARACTER)                       # 新剧情
    assert vn.in_memorial is False and vn._memorial_used is False
    print("    start_session: 纪念状态重置（enter 可用）")


# ----------------------------------------------------------------------------
# CLI 全流程（run_bond_story_vn）: mock 生图 + 事件流 + exit schema 注记
# ----------------------------------------------------------------------------

def test_run_vn_memorial_flow(tmp_path):
    """story_scene → memorial_enter（生图+立绘）→ memorial_exit → story_end 全流程。"""
    from core.session import SessionStore
    from core.session.events import M_MEMORIAL_ENTER, M_MEMORIAL_EXIT
    from core.media.gallery import GalleryStore
    from core.ui.vn_cli import run_bond_story_vn

    OPEN = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "她们走进高级餐厅。", "emotion": "nomal"}],
        "choices": ["牵起她的手"]}}

    class FakeImageGen:
        """生图 mock: warmup 记一次; generate 返回假 png（写 tmp 文件）。"""
        def __init__(self, png: Path):
            self.png = png
            self.warmed = 0
            self.used = 0
            self.last_prompt = ""
            self.last_refs: list = []
        def warmup(self):
            self.warmed += 1
        def generate(self, prompt, seed=None, ref_images=None, character_name="角色",
                     **kw):
            self.used += 1
            self.last_prompt = prompt
            self.last_refs = list(ref_images or [])
            return GeneratedImage(path=self.png, width=1920, height=1080,
                                  size_bytes=self.png.stat().st_size, backend="apiyi")

    fake_png = tmp_path / "fake.png"
    fake_png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    gen = FakeImageGen(fake_png)

    engine, st, sid = _store_engine(
        ScriptedLLM(OPEN, ENTER, EXIT, STORY_END), tmp_path / "data")
    completed = run_bond_story_vn(
        engine, input_fn=lambda p: "1", char_ms=0,
        remind_rounds=15, end_rounds=22,
        store=st, image_gen=gen, gallery=GalleryStore(tmp_path / "gal"),
        memorial_seed=42)
    assert completed, "story_end 收尾应 completed=True"
    assert gen.warmed == 1, "开场应预热一次"
    assert gen.used == 1, "只应生图一次（一段至多 1 次 memorial）"

    evs = st.events(CHARACTER, sid)
    subs = [e.subtype for e in evs]
    # 状态机 marker 完整: enter 后 exit
    assert M_MEMORIAL_ENTER in subs and M_MEMORIAL_EXIT in subs
    assert subs.index(M_MEMORIAL_ENTER) < subs.index(M_MEMORIAL_EXIT)
    # bond 事件: enter 轮 + exit 轮（to_dict 不含 prompt——prompt 在 gallery json;
    # 2026-09-02: 落库场景 emotion = 标注回填值（stub nomal）, 文本不变）
    enter_ev = [e for e in evs if e.subtype == "memorial_enter" and e.type == "bond"][0]
    assert ([p["text"] for p in enter_ev.payload["paragraphs"]]
            == [p["text"] for p in ENTER["payload"]["paragraphs"]])
    assert all(p.get("emotion") == "nomal" for p in enter_ev.payload["paragraphs"])
    # l2d 事件: 立绘资产（含场景文字 + 图引用）
    l2d_evs = [e for e in evs if e.type == "l2d"]
    assert len(l2d_evs) == 1, l2d_evs
    assert l2d_evs[0].payload["images"], l2d_evs[0].payload
    assert "她终于抬起头" in l2d_evs[0].payload["paragraphs"][0]
    # exit 轮 bond 事件（过渡文字）
    exit_ev = [e for e in evs if e.subtype == "memorial_exit" and e.type == "bond"][0]
    assert "破涕为笑" in exit_ev.payload["paragraphs"][0]["text"]
    # gallery 落盘成对
    gal_items = GalleryStore(tmp_path / "gal").list(CHARACTER)
    assert len(gal_items) == 1 and Path(gal_items[0]["png"]).is_file()
    print("    run_vn(memorial 全流程): enter 生图 → l2d 事件 + marker enter/exit → exit 回 bond")


def test_run_vn_memorial_exit_note_injected(tmp_path):
    """纪念模式内下一轮 system_note 注入 memorial_exit schema（LLM 知道怎么写 exit）。"""
    from core.session import SessionStore
    from core.ui.vn_cli import run_bond_story_vn

    OPEN = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "开场。", "emotion": "nomal"}], "choices": ["继续"]}}

    llm = ScriptedLLM(OPEN, ENTER, EXIT, STORY_END)
    engine, st, _ = _store_engine(llm, tmp_path / "data2")
    run_bond_story_vn(engine, input_fn=lambda p: "1", char_ms=0,
                      remind_rounds=15, end_rounds=22, store=st)
    # exit 轮（第 3 个场景轮）: 尾序（2026-09-07 promptkit §4）= 约束注记（含
    # exit schema）→ 场 task 卡 → user; 此处断言约束注记层, 卡槽位由
    # test_promptkit_baseline 锁定
    exit_msgs = _scene_msgs(llm)[2]
    sys_msgs = [m["content"] for m in exit_msgs if m["role"] == "system"]
    note = [c for c in sys_msgs if not c.startswith("本场任务：")][-1]
    assert "纪念模式" in note and "memorial_exit" in note, note
    assert "可用动作 schema" in note
    assert sys_msgs[-1].startswith("本场任务：纪念时刻已落幕")      # memorial_exit 卡
    print("    run_vn: 纪念模式内下一轮注入 exit schema 注记")
