"""web/mock.py — IDE_MOCK=1 时的 StubLLM。

固定脚本驱动 agent 走完整流程（思考 → 提议 → 审批 → 执行 → 完成），
不碰网络; 执行层 root 用临时目录, 不污染真实 config/。每轮用唯一
character_id, 可反复跑多轮; 拒绝后重试会复用同一 character_id（目录未创建, 合法）。

本质是"关键字→动作"的胶水——未来可演化为无需 LLM 的本地指令层（见 DESIGN §10）。
"""
from __future__ import annotations

import tempfile
from pathlib import Path


def _cc(character_id: str, summary: str) -> dict:
    """合法 create_character 动作 dict（过契约 + 真实 executor 可落盘）。"""
    return {
        "action": "create_character",
        "summary": summary,
        "reply": "好的，我来创建这个角色。",
        "payload": {
            "character_id": character_id,
            "files": {"profile.yml": f"REQ~most_called_name: {character_id}\n"},
        },
    }


def _done(message: str) -> dict:
    return {
        "action": "done",
        "summary": message,
        "reply": "全部完成了。",
        "payload": {"message": message},
    }


class MockLLM:
    """按对话"最后一条 user 消息"里的标记决定下一步动作。

    chat 返回 registry.parse 可直接消费的动作 dict（与 _events_test 同源模式）。
    """

    def __init__(self) -> None:
        self._turns = 0
        self._current_char = ""

    def chat(self, messages: list[dict], **kw) -> dict:
        last_user = next(
            (str(m.get("content", "")) for m in reversed(messages)
             if m.get("role") == "user"),
            "",
        )
        # 执行完成后 agent 追加 "动作已执行: ..." → 该收尾了
        if last_user.startswith("动作已执行"):
            return _done(
                f"mock 角色 {self._current_char} 已创建（mock 模式, 未写真实配置）"
            )
        # 拒绝后 agent 追加 "用户拒绝了该动作..." → 按反馈重试（复用同一 character_id）
        if "用户拒绝" in last_user:
            return _cc(self._current_char, f"按反馈调整后重试创建 {self._current_char}")
        # 新的一轮
        self._turns += 1
        self._current_char = f"mock_char_{self._turns:03d}"
        return _cc(
            self._current_char,
            f"创建测试角色 {self._current_char}（mock 第 {self._turns} 轮）",
        )


def mock_root() -> Path:
    """mock 模式执行层落盘用临时目录（不污染真实 config/）。"""
    return Path(tempfile.mkdtemp(prefix="live2be_mock_"))
