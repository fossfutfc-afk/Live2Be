# -*- coding: utf-8 -*-
"""纪念立绘真实跑 — 强情感 reason 直接进 VN, 触发 memorial_enter → 真实生图。

e2e_smoke 的 reason 平淡（日常约见）→ LLM 不会用 memorial_enter; 本脚本给
强情感触发设定（湖边告白）, 验证: LLM 输出 memorial_enter → 生图（pipe 预热后
~2s, 显示"生成中"）→ gallery 落盘 → l2d 事件 + marker。

用法: python experiments/memorial_real_run.py [char_id]
产出: 立绘 data/{char_id}/gallery/{scene_id}.png+.json + 事件流会话
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.client import LLMClient
from llm.image_gen import ImageGenerator
from core.momotalk import MomoTalkEngine
from core.session import SessionStore
from core.ui.vn_cli import run_bond_story_vn

CHAR = sys.argv[1] if len(sys.argv) > 1 else "igusa_haruka"
ROOT = Path(__file__).resolve().parent.parent


def _auto_input(prompt: str = "") -> str:
    """有选项 → 选第一个; 无选项 → 一句推进（走完 memorial_exit 的自由输入）。"""
    return "1" if "选择" in prompt else "（握住她的手）我就在这里"


def main() -> None:
    llm = LLMClient()
    store = SessionStore()
    engine = MomoTalkEngine(ROOT / "config" / "characters", llm, store=store)
    engine.start_session(CHAR)
    char = engine.current_character
    root = store.create(CHAR, char.display_name)
    engine.attach_session(root.session_id)

    reason = (
        f"老师约{char.display_name}放学后到湖边见面——月色下, 老师终于决定说出心意: "
        f"『{char.display_name}, 你对我而言很特别……不是作为学生, 而是作为我想一直守护的人』"
    )
    print(f"reason: {reason}\n")

    completed = run_bond_story_vn(
        engine, input_fn=_auto_input, char_ms=0,
        remind_rounds=10, end_rounds=16, store=store,
        image_gen=ImageGenerator(), memorial_seed=42)
    print(f"\ncompleted = {completed}")

    from core.media.gallery import GalleryStore
    items = GalleryStore().list(CHAR)
    print(f"\n本次立绘（gallery 共 {len(items)} 张）:")
    for item in items:
        print(f"  [{item['scene_id']}] {item['prompt'][:56]}… → {item['png']}")


if __name__ == "__main__":
    main()
