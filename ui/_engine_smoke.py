# -*- coding: utf-8 -*-
"""引擎冒烟 — 验证 text_processors 修复后 MomoTalk 三条输出路径无损。

batch  : send_message           → format_momotalk_reply 完整处理
stream : send_message_stream    → 逐 token feed 气泡 + flush 遗留
history: resume_session          → 历史回放渲染无损

用 stub LLM（不碰 API）喂入含连续标点的回复，断言"去前缀后拼回 == 原文"。
用法: python ui/_engine_smoke.py   （需项目根环境, 推荐 live2be env）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.momotalk import MomoTalkEngine
from parsing.dynamic_character_parser import CharacterLoader  # noqa: F401
from ui.text_processors import strip_name_prefix

ROOT = Path(__file__).resolve().parent.parent
CHARACTER = "igusa_haruka"

# 含连续标点 + 动作括号的高危文本（回归: 修前会丢 "！" 或全标点段）
REPLY = "（轻笑）今天天气真不错呢！！我们一起去天台吧？？"

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


class StubLLM:
    """最小 LLMClient 兼容面：format_messages / chat / chat_stream。"""

    def __init__(self, reply: str):
        self._reply = reply
        self.calls = 0

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs

    def chat(self, messages, temperature=0.8, max_tokens=512, response_format="text"):
        self.calls += 1
        return self._reply

    def chat_stream(self, messages, temperature=0.8, max_tokens=512):
        self.calls += 1
        # 逐 token 喂（含标点单独成 token 的极端切法, 打穿 LineBuffer）
        for ch in self._reply:
            yield ch


def _engine() -> MomoTalkEngine:
    engine = MomoTalkEngine(ROOT / "config" / "characters", StubLLM(REPLY))
    engine.start_session(CHARACTER)
    return engine


# ----------------------------------------------------------------------------
# batch: send_message 一次返回
# ----------------------------------------------------------------------------

def _t_batch():
    engine = _engine()
    processed = engine.send_message("我们去天台吧？")
    name = engine.current_character.display_name
    body = strip_name_prefix(processed, name)
    # 动作括号会被 _process_reply 保留（format_momotalk_reply 不去括号），断言不丢字
    assert body.count("！") == 2 and body.count("？") == 2, f"标点丢失: {body!r}"
    assert "天台" in body, body
    print(f"    batch: {body!r}")


# ----------------------------------------------------------------------------
# stream: 逐 token 气泡 + flush 遗留, 拼回无损
# ----------------------------------------------------------------------------

def _t_stream():
    engine = _engine()
    name = engine.current_character.display_name
    bubbles: list[str] = []
    for bubble, _delay in engine.send_message_stream("我们去天台吧？"):
        bubbles.append(bubble)
    joined = "".join(strip_name_prefix(b, name) for b in bubbles)
    # 动作括号在 momotalk 处理中被剥离, 其余应逐字无损
    assert joined == "今天天气真不错呢！！我们一起去天台吧？？", f"流式丢字: {joined!r}"
    print(f"    stream {len(bubbles)}泡: {joined!r}")


# ----------------------------------------------------------------------------
# history: resume_session 回放 + 继续对话不丢历史
# ----------------------------------------------------------------------------

def _t_history():
    from core.momotalk import Session

    session = Session(
        character_id=CHARACTER,
        character_name="测试",
        history=[
            {"role": "user", "content": "之前说的"},
            {"role": "assistant", "content": "好呀！！"},
        ],
    )
    path = ROOT / "data" / "sessions" / "_smoke_session.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    session.to_json(path)
    try:
        engine = _engine()
        restored = engine.resume_session(path)
        assert len(restored.history) == 2, f"历史条数 {len(restored.history)}"
        assert engine.history_length == 2
        # 恢复后继续对话, 历史前缀仍在（不会因 _process 问题丢消息）
        processed = engine.send_message("继续说")
        assert engine.history_length >= 4, f"继续对话后历史 {engine.history_length}"
        assert "之前说的" in engine.history[0]["content"]
        assert processed
        print(f"    history: 恢复 2 条 → 续聊 {engine.history_length} 条")
    finally:
        path.unlink(missing_ok=True)


def main() -> None:
    print(f"引擎冒烟（{CHARACTER} / stub LLM）")
    print("=" * 46)
    check("batch 输出无损", _t_batch)
    check("stream 逐 token 无损", _t_stream)
    check("history 恢复 + 续聊无损", _t_history)
    print("=" * 46)
    if FAIL:
        print(f"结果: {PASS} PASS / {FAIL} FAIL")
        sys.exit(1)
    print(f"结果: {PASS} PASS / 0 FAIL — 全部通过")


if __name__ == "__main__":
    main()
