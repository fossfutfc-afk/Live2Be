# -*- coding: utf-8 -*-
"""send_vn_scene 流式嗅探集成测试（方案 A step3）— on_memorial_prompt 钩子。

覆盖:
    - memorial_enter 流式输出 → prompt 值闭合时回调触发（与 LLM 剩余输出并行）
    - 非 memorial 动作 → 永不触发
    - 不传钩子 → 不嗅探（on_chunk 为 None）
    - 旧 mock LLM（仅 chat）→ 自动回退, 行为与改造前一致
"""
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondStoryEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER = "igusa_haruka"

ENTER = {"action": "memorial_enter", "payload": {
    "prompt": "湖边, 黑发少女含泪抬头, 月光",
    "paragraphs": [{"text": "（她终于抬起头）老师……我这种人……", "emotion": "embarrass"}],
    "choices": ["抱住她", "陪她坐着"]}}
SCENE = {"action": "story_scene", "payload": {
    "paragraphs": [{"text": "她们蹲在路边摊前。", "emotion": "smile"}],
    "choices": ["一起吃"],
    "branches": {"一起吃": [{"text": "她递来一串章鱼烧。", "emotion": "smile"}]}}}


def _chunks(payload: dict, size: int = 12) -> list[str]:
    """契约 dict → 流式 chunk 列表（任意切分, 模拟 token 流）。"""
    raw = json.dumps(payload, ensure_ascii=False)
    return [raw[i:i + size] for i in range(0, len(raw), size)]


class StreamLLM:
    """带 chat_full 的流式 mock: 按 chunk 逐块喂 on_chunk, 返回预设 dict。"""

    def __init__(self, *scripts: dict, size: int = 12):
        self._scripts = list(scripts)
        self._size = size
        self.snapshots: list[list[dict]] = []
        self.probe_chunks: list[str] = []      # 实际喂给 on_chunk 的块（探针观察到的）

    def chat_full(self, messages, temperature=0.8, max_tokens=1536,
                  response_format="text", extra_body=None, on_chunk=None):
        self.snapshots.append([dict(m) for m in messages])
        if not self._scripts:
            raise RuntimeError("脚本耗尽")
        result = self._scripts.pop(0)
        for c in _chunks(result, self._size):
            if on_chunk is not None:
                self.probe_chunks.append(c)
                on_chunk(c)
        return result

    def chat(self, messages, temperature=0.8, max_tokens=1536, response_format="text"):
        raise AssertionError("流式 LLM 不应走 chat 回退路径")

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


class ChatOnlyLLM:
    """旧式 mock（仅 chat）——send_vn_scene 应自动回退。"""

    def __init__(self, *scripts: dict):
        self._scripts = list(scripts)

    def chat(self, messages, temperature=0.8, max_tokens=1536, response_format="text"):
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


def test_stream_fires_on_memorial_enter():
    calls: list[str] = []
    llm = StreamLLM(ENTER)
    vn = _vn(llm)

    scene = vn.send_vn_scene("（开场）", annotate=False, on_memorial_prompt=calls.append)

    assert calls == ["湖边, 黑发少女含泪抬头, 月光"]
    assert scene.memorial_prompt == "湖边, 黑发少女含泪抬头, 月光"
    assert len(llm.probe_chunks) > 1         # 确实走流式分块喂探针


def test_stream_silent_on_story_scene():
    calls: list[str] = []
    llm = StreamLLM(SCENE)
    vn = _vn(llm)

    scene = vn.send_vn_scene("（开场）", annotate=False, on_memorial_prompt=calls.append)

    assert not calls
    assert scene.memorial_prompt == ""


def test_no_hook_means_no_probe():
    llm = StreamLLM(ENTER)
    vn = _vn(llm)

    scene = vn.send_vn_scene("（开场）", annotate=False)

    assert scene.memorial_prompt == "湖边, 黑发少女含泪抬头, 月光"
    assert not llm.probe_chunks             # on_chunk=None → 不喂探针（仍流式收集）


def test_fallback_chat_only_llm():
    calls: list[str] = []
    llm = ChatOnlyLLM(ENTER)
    vn = _vn(llm)

    scene = vn.send_vn_scene("（开场）", annotate=False, on_memorial_prompt=calls.append)

    assert scene.memorial_prompt == "湖边, 黑发少女含泪抬头, 月光"
    assert not calls                        # 回退 chat → 无嗅探（行为与改造前一致）
