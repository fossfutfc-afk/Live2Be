# -*- coding: utf-8 -*-
"""MMT 输出规范演示 — 字数+随机数逐块 + "…"等待指示（不依赖 LLM）。

跑一遍看效果:
    python experiments/demo_typing.py

展示三条回复的输出节奏: 每条 = 若干"…"(打字指示) 被真实气泡依次覆盖。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.tui.display import MomoTalkOutput
from core.tui.streaming import simulate_steps
from core.tui.text_processors import _process_for_momotalk


def main() -> None:
    samples = [
        "嗯嗯好的",
        "（轻笑）今天谢谢你！要不要一起去喝奶茶？",
        "今天天气很好我们一起去天台吧我想和你说说话明天见",
    ]
    for text in samples:
        print(f"\n— 回复: {text!r}")
        steps = MomoTalkOutput(_process_for_momotalk, "遥香").publish_reply(text)
        simulate_steps(steps)
    print("\n（每个气泡前都有短暂『…』打字等待 — 时长 = 字数 × 每字随机延迟）")


if __name__ == "__main__":
    main()
