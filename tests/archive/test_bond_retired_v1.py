# 留档: webgui test_bond.py 里三例**已退役机制**的用例（P0-7c）
#  - 旧段落锚点 place 路（v2 = switch 记录 → 背景键翻译）
#  - memorial_enter 子模式 + 立绘异步注入（v2 = 块内 stage:memorial, 降级为普通 VN;
#    生图钩子待 P2 重接到 art/memorial 记录）
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"


# ----------------------------------------------------------------------------

def test_bond_async_place_anchors_written(tmp_path):
    """place lane 异步写回: 变更句 place 键落到 payload; 门控 = emotion+place 双路齐。"""
    from core.media.emotion_lexicon import load_place_lexicon
    place_keys = load_place_lexicon()
    if not place_keys:                      # 无地点词表资产 → 无标注能力, 跳过
        print("    (跳过: 无 _director_whitelist 资产)")
        return
    anchor = place_keys[0]

    class PlaceLLM(ScriptedLLM):
        def chat(self, messages, temperature=0.8, max_tokens=4096,
                 response_format="text", **kw):
            self.snapshots.append([dict(m) for m in messages])
            head = messages[0]["content"]
            last = messages[-1]["content"] if len(messages) > 1 else ""
            if "情绪标签数组" in last:               # emotion → 全 nomal
                import re as _re
                n = len(_re.findall(r"(?m)^\d+: ", head))
                return ["nomal"] * max(n, 1)
            if "变更句数组" in last:                  # place → 末句锚点
                import re as _re
                n = len(_re.findall(r"(?m)^\d+: ", head))
                return [{"sentence": max(n, 1), "place": anchor}]
            if "记录员" in head or "整理者" in head:
                return _digest_stub(messages)
            if not self._scripts:
                raise RuntimeError("PlaceLLM 脚本耗尽")
            _rec(self._scripts.pop(0))

    scene1 = {"action": "story_scene", "payload": {
        "paragraphs": ["她在教室里收拾着书包。",
                       "她带我穿过走廊，推开了天台的门。"]}}
    scene2 = {"action": "story_end", "payload": {
        "paragraphs": [{"text": "（夜色渐深, 这一章落下帷幕。）"}]}}
    llm = PlaceLLM(scene1, scene2)
    engine, st, sid, _ = _setup(tmp_path)
    chat._engines[CHARACTER] = engine
    engine.llm = llm
    try:
        bond.bond_start(CHARACTER, sid)
        st1 = _wait_status(CHARACTER, sid)
        # place lane 异步: 锚点写回当前展示场景的变更句（轮询状态直到出现）
        deadline = time.time() + 8.0
        while time.time() < deadline:
            s = bond.bond_status(CHARACTER, sid)
            paras = s["scene"]["paragraphs"] if s.get("scene") else []
            if paras and any(p.get("place") == anchor for p in paras):
                break
            time.sleep(0.05)
        assert any(p.get("place") == anchor for p in paras), paras
        # 门控放行（双路齐）: 自由输入推进可立即被接受
        r = _turn_until_accepted(CHARACTER, sid, "老师，今晚就到这里吧")
        assert r["accepted"], r
        # 事件落库携带锚点（_log_scene 用 scene.to_dict()——append-only 视觉键定格）
        evs = st.events(CHARACTER, sid)
        logged = [e for e in evs if e.type == "bond"][0]
        assert any(p.get("place") == anchor
                   for p in logged.payload["paragraphs"] if isinstance(p, dict))
        print("    place lane: 异步锚点写回 payload + 门控放行 + 事件落库携带")
    finally:
        _cleanup()




# ----------------------------------------------------------------------------

MEMORIAL_ENTER = {"action": "memorial_enter", "payload": {
    "prompt": "湖边, 黑发少女含泪抬头, 月光",
    "paragraphs": [{"text": "（她终于抬起头）老师……我这种人……", "emotion": "embarrass"}],
    "choices": ["抱住她"]}}


class StreamLLM:
    """带 chat_full 的流式 mock（方案 A: chat_full 流式输出触发嗅探回调）。"""

    def __init__(self, *scripts):
        self._scripts = list(scripts)
        self.probe_chunks: list[str] = []

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text",
             **kw):
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last:               # emotion 标注 → 全 nomal
            import re as _re
            n = len(_re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        if "变更句数组" in last:                  # place 标注（P3a）→ 无变更
            return []
        if "地点 id JSON" in last:                # 换场翻译（P0-7）→ 不切背景
            return {"place": ""}
        if "记录员" in head or "整理者" in head:
            return _digest_stub(messages)              # digest 调用 → 两轮空包
        if not self._scripts:
            raise RuntimeError("StreamLLM 脚本耗尽")
        _rec(self._scripts.pop(0))

    def chat_full(self, messages, temperature=0.8, max_tokens=4096,
                  response_format="text", extra_body=None, on_chunk=None):
        head = messages[0]["content"]
        last = messages[-1]["content"] if len(messages) > 1 else ""
        if "情绪标签数组" in last:               # 标注调用（chat_full 路径兜底）
            import re as _re
            n = len(_re.findall(r"(?m)^\d+: ", head))
            return ["nomal"] * max(n, 1)
        if "变更句数组" in last:                  # place 标注 → 无变更
            return []
        if "地点 id JSON" in last:                # 换场翻译（P0-7）→ 不切背景
            return {"place": ""}
        if "记录员" in head or "整理者" in head:
            return _digest_stub(messages)
        if not self._scripts:
            raise RuntimeError("StreamLLM 脚本耗尽")
        result = self._scripts.pop(0)
        raw = json.dumps(result, ensure_ascii=False)
        for i in range(0, len(raw), 11):               # 任意分块模拟 token 流
            chunk = raw[i:i + 11]
            if on_chunk is not None:
                self.probe_chunks.append(chunk)
                on_chunk(chunk)
        return result

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


class FakeImageGen:
    """fake 生图器: 记录 prompt + 返回假 png（不碰 API）。"""

    def __init__(self, tmp_path: Path):
        self.tmp = Path(tmp_path)
        self.prompts: list[str] = []

    @property
    def is_api_mode(self):
        return True

    def generate(self, prompt, ref_images=None, character_name="角色", **kw):
        self.prompts.append(prompt)
        self.kwargs = kw                     # 记录角色生图提示注入（illustration.yml）
        p = self.tmp / "fake.png"
        p.write_bytes(b"fake-png-bytes")
        return GeneratedImage(path=p, width=1920, height=1080,
                              size_bytes=p.stat().st_size, backend="apiyi")


def test_bond_memorial_async_image(tmp_path, monkeypatch):
    from webgui import bond as bond_mod

    fake = FakeImageGen(tmp_path)
    monkeypatch.setattr(bond_mod, "_image_generator", lambda: fake)

    llm = StreamLLM(SCENE_A, MEMORIAL_ENTER)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    st = SessionStore(tmp_path)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine
    chat._store = st
    sid = root.session_id
    try:
        # 首场（带选项）→ 分支消费（同响应）→ 分支播放时 pregen 触发
        # → 生成 memorial_enter（流式嗅探）→ 后台生图
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        r = bond.bond_turn(CHARACTER, sid, "选A")
        assert r["accepted"] and r.get("branch"), r

        # 等 pregen（memorial_enter 生成）完成 → in_memorial=True（引擎状态机）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if not bond.bond_status(CHARACTER, sid)["busy"]:
                break
            time.sleep(0.05)
        st1 = bond.bond_status(CHARACTER, sid)
        assert st1["in_memorial"] is True, st1
        assert llm.probe_chunks, "流式嗅探应已观察到 token 流"

        # 等生图线程完成 → 图 URL 就绪（gallery 落盘在 tmp data_root）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if bond.bond_status(CHARACTER, sid)["memorial_img"]:
                break
            time.sleep(0.05)
        st2 = bond.bond_status(CHARACTER, sid)
        assert st2["memorial_img"].startswith(f"/gallery/world1/{CHARACTER}/"), \
            st2["memorial_img"]
        assert fake.prompts == ["湖边, 黑发少女含泪抬头, 月光"], fake.prompts
        # 生图提示注入: illustration.yml 的 halo_hint 必须一路传到生图调用（端到端确认）
        assert "钝角三角形" in fake.kwargs.get("halo_hint", ""), fake.kwargs
        # 画廊成对落盘（png + json, 2026-09-02: 世界线角色目录内）——list 只认成对
        gdir = (tmp_path / "worlds" / "world1" / "characters"
                / CHARACTER / "gallery")
        assert len(list(gdir.glob("*.png"))) == 1
        assert len(list(gdir.glob("*.json"))) == 1
        print("    bond 纪念立绘: 流式嗅探 prompt 定稿即生图 → 画廊落盘 → memorial_img 就绪")
    finally:
        chat._engines.pop(CHARACTER, None)
        chat._store = _ORIG_STORE


class FailingImageGen:
    """生图失败 mock: generate 抛异常——纪念应降级纯文字, 剧情照走。"""

    @property
    def is_api_mode(self):
        return True

    def generate(self, prompt, ref_images=None, character_name="角色"):
        raise RuntimeError("生图 API 超时")




# ----------------------------------------------------------------------------
# 纪念立绘异步生成（方案 A 2026-09-01）: 流式嗅探到 memorial_enter 的 prompt
# 定稿 → 后台生图（与 LLM 剩余输出并行）→ 画廊落盘 → bond_status.memorial_img
def test_bond_memorial_image_failure_degrades(tmp_path, monkeypatch):
    from webgui import bond as bond_mod

    monkeypatch.setattr(bond_mod, "_image_generator", lambda: FailingImageGen())

    llm = StreamLLM(SCENE_A, MEMORIAL_ENTER)
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm)
    engine.start_session(CHARACTER)
    st = SessionStore(tmp_path)
    root = st.create(CHARACTER)
    engine.attach_session(root.session_id)
    chat._engines[CHARACTER] = engine
    chat._store = st
    sid = root.session_id
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)
        r = bond.bond_turn(CHARACTER, sid, "选A")
        assert r["accepted"] and r.get("branch"), r

        # pregen（memorial_enter）完成后: in_memorial=True 但图失败 → memorial_img None
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if not bond.bond_status(CHARACTER, sid)["busy"]:
                break
            time.sleep(0.05)
        deadline = time.time() + 5.0
        while time.time() < deadline:          # 等生图线程失败写回（busy 标志清除）
            if not bond.bond_status(CHARACTER, sid)["memorial_img_busy"]:
                break
            time.sleep(0.05)
        s = bond.bond_status(CHARACTER, sid)
        assert s["in_memorial"] is True, s
        assert s["memorial_img"] is None, s   # 失败 → 纯文字降级（前端无图）
        print("    bond 纪念立绘失败: 降级纯文字, 剧情照走（memorial_img=None）")
    finally:
        chat._engines.pop(CHARACTER, None)
        chat._store = _ORIG_STORE


# ----------------------------------------------------------------------------
# 中途退出收尾（2026-09-01）: vn_exit 带 completed 标志; 中断剧情不 digest
# （实测 bug: 收尾链把未发生的剧情总结成"玩得很开心" + 写进 wiki——记忆污染）
# ----------------------------------------------------------------------------



# ----------------------------------------------------------------------------

def test_bond_async_annotate(tmp_path):
    """骨架（缺 emotion）→ 主生成立即返回（等待=骨架）→ 异步标注补标 → scene 更新。"""
    skeleton = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "她站在窗边。", "emotion": "nomal"},
                       {"text": "老师来了！"}],      # 缺 emotion → 触发标注
        "choices": ["选A", "选B"],
        "branches": {"选A": [{"text": "分支一。"}],
                     "选B": [{"text": "分支二。", "emotion": "smile"}]}}}
    engine, st, sid, llm = _setup(tmp_path, skeleton, '["smile"]',
                                  '["expectant"]')
    try:
        bond.bond_start(CHARACTER, sid)
        st1 = _wait_status(CHARACTER, sid)          # 主生成完成（骨架, busy=False）
        # 标注队列补标（后台线程）→ 轮询 emo_version 变化 + scene emotion 补齐
        # （桩标注即时完成, 不要求中间态; 中间态由竞态测试的 GatedLLM 覆盖）
        deadline = time.time() + 10.0
        while time.time() < deadline:
            s = bond.bond_status(CHARACTER, sid)
            if s["emo_version"] > st1.get("emo_version", 0) \
                    and s["scene"]["paragraphs"][1].get("emotion"):
                break
            time.sleep(0.05)
        s2 = bond.bond_status(CHARACTER, sid)
        # 2026-09-02: 记录自带 emotion 丢弃 → 标注 stub 全 nomal 回填（补标机制不变）
        assert s2["scene"]["paragraphs"][1]["emotion"] == "nomal", s2["scene"]
        # 反应板（下一板, 待发）在继续时进入并独立标注
        r = _turn_until_accepted(CHARACTER, sid, "选A")
        assert r.get("branch"), r
        _turn_until_accepted(CHARACTER, sid, "（继续）")
        _wait_status(CHARACTER, sid)
        deadline = time.time() + 10.0
        while time.time() < deadline:
            s = bond.bond_status(CHARACTER, sid)
            paras = (s["scene"] or {}).get("paragraphs") or []
            if paras and paras[0]["text"] == "分支一。" and paras[0].get("emotion"):
                break
            time.sleep(0.05)
        s3 = bond.bond_status(CHARACTER, sid)
        assert s3["scene"]["paragraphs"][0]["text"] == "分支一。", s3["scene"]
        assert s3["scene"]["paragraphs"][0]["emotion"] == "nomal", s3["scene"]
        assert "选B" not in [p["text"] for p in s3["scene"]["paragraphs"]]   # 未选不显示
        print("    bond 异步标注: 骨架先显示（等待=生成）→ 队列补标 emo_version++ → 反应板补齐")
    finally:
        _cleanup()


def test_bond_annotate_gate_blocks_then_releases(tmp_path):
    """推进门控（2026-09-02, 用户拍板）: 情绪没到位不让点下一轮——标注未完成
    （闸门阻塞）→ turn 被 busy 拦（前端自动轮询）; 标注完成 → 放行推进。
    场景推进后的 worker 写回对象检查保留为防御（门控下竞态不可达, 不污染新场景）。"""
    import threading as _th

    gate = _th.Event()                             # 标注调用阻塞闸门
    released = {"n": 0}

    class GatedLLM:
        """骨架顺序输出; 标注调用（user 消息含'情绪标签'）阻塞等闸门;
        place 标注（'变更句数组'）不阻塞——快速 keep, 门控只由 emotion 路卡住。"""
        def __init__(self, *scripts):
            self._scripts = list(scripts)
        def chat(self, messages, **kw):
            user = messages[-1]["content"] if messages else ""
            if "情绪标签" in user:                    # 标注调用（识别 user 消息）
                gate.wait()                           # 不放行（确定性: 无超时 → 无兜底填充）
                released["n"] += 1
                return '["nomal", "smile"]'
            if "变更句数组" in user:                  # place 标注 → 无变更（不占闸门）
                return []
            if not self._scripts:
                raise RuntimeError("脚本耗尽")
            _rec(self._scripts.pop(0))
        def format_messages(self, *, system_prompt, user_message, history=None):
            msgs = [{"role": "system", "content": system_prompt}]
            msgs.extend(history or [])
            msgs.append({"role": "user", "content": user_message})
            return msgs

    sk1 = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "第一场。", "emotion": "nomal"}, {"text": "缺标。"}],
        "choices": ["继续走"],
        "branches": {"继续走": [{"text": "分支。", "emotion": "nomal"}]}}}
    sk2 = {"action": "story_scene", "payload": {
        "paragraphs": [{"text": "第二场。", "emotion": "smile"}]}}
    engine, st, sid, _llm = _setup(tmp_path)
    chat._engines[CHARACTER] = engine
    llm = GatedLLM(sk1, sk2)
    engine.llm = llm
    try:
        bond.bond_start(CHARACTER, sid)
        _wait_status(CHARACTER, sid)               # 骨架1 就绪, 标注线程已阻塞在闸门
        # 等标注线程确实进入阻塞（gate 有等待者）
        deadline = time.time() + 5.0
        while time.time() < deadline and not gate._cond._waiters:
            time.sleep(0.02)
        # 推进门控（2026-09-02）: 标注未完成 → 分支选择也被拦（busy 语义,
        # 前端自动轮询重试）——情绪不到位不推进
        r = bond.bond_turn(CHARACTER, sid, "继续走")
        assert not r["accepted"] and r.get("busy") is True, r
        assert "标注中" in r.get("error", ""), r          # 双路门控（emotion+place）
        # 释放标注 → 回填完成 → 重试放行（分支消费）
        gate.set()
        r2 = _turn_until_accepted(CHARACTER, sid, "继续走")
        assert r2.get("branch"), r2
        _wait_status(CHARACTER, sid)               # 分支触发的预生成完成（busy=False）
        # 场景推进后 worker 写回对象检查（防御: 丢弃不污染——门控下竞态不可达,
        # 防御保留）。消费预生成 → scene_obj = 骨架2 → 骨架2 自身标注完成
        r3 = _turn_until_accepted(CHARACTER, sid, "（继续）")
        assert r3.get("pregen") or r3.get("accepted"), r3
        deadline = time.time() + 5.0
        while time.time() < deadline:
            s = bond.bond_status(CHARACTER, sid)
            if s["scene"]["paragraphs"] and s["scene"]["paragraphs"][0].get("emotion"):
                break
            time.sleep(0.05)
        s = bond.bond_status(CHARACTER, sid)
        # 新场景段落未被骨架1 的标注污染（对象检查丢弃生效——文本仍是第二场）;
        # 2026-09-02: 骨架 emotion 丢弃 → 标注返回 2 标签 vs 1 句 → 清洗失败兜底 nomal
        assert s["scene"]["paragraphs"][0]["text"] == "第二场。", s["scene"]
        assert s["scene"]["paragraphs"][0]["emotion"] == "nomal", s["scene"]
        print("    bond 门控: 标注未完成 turn 被拦 → 释放后放行; 写回对象检查防御保留")
    finally:
        _cleanup()


# ----------------------------------------------------------------------------
# place 标注 lane（DESIGN_BOND_CONTRACT_V2 §7, P3b-1）: 异步锚点写回 + 门控双路
