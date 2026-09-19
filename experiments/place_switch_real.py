# -*- coding: utf-8 -*-
"""地点链真机复测: 跑一场**真剧情**, 看换场到底通没通（C2–C6 验收）。

此前真机的症状（2026-09-19 复核）: 3 次换场 **3 次 MISS**、board 级 `place` 0 条、
记录级锚点 0 条、每一板 `background=neutral` → 展示兜底成 `class_room`
（**每次 VN 都在显示教室**）。

本脚本跑真 LLM + 真导演 + 真 catalog（**不写事件流**——纯内存引擎），逐板打印:
    switch 原文 → 解出的键 → 资产 scene_id → 背景图（**文件是否存在**）
    + 句级锚点（板内后续换场）
最后汇总: 换场成功/失败、层1（0 调用）与层2 的次数、背景切换率。

用法: python experiments/place_switch_real.py [角色id] [板数] ["开场种子"]
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bond.bond_story import BondStoryEngine            # noqa: E402
from core.media.catalog import MediaCatalog                 # noqa: E402
from core.media.place_table import load_table               # noqa: E402
from core.ui.vn_cli import _build_director                  # noqa: E402
from llm.client import LLMClient                            # noqa: E402

#: 默认种子刻意**邀请移动**（不换场就验不出"背景能不能切"）
DEFAULT_SEED = "（旁白）放学后的教室里，老师来找她。她提议带老师去学校天台看看。"


class Counting:
    """包 LLM: 分清"地点相关调用"与主生成, 记耗时。"""

    def __init__(self, inner):
        self.inner = inner
        self.place_calls = 0
        self.place_secs = 0.0
        self.gen_calls = 0

    def chat(self, messages, **kw):
        last = messages[-1]["content"] if len(messages) > 1 else ""
        is_place = ("地点 id JSON" in last) or ("变更句数组" in last)
        t0 = time.time()
        out = self.inner.chat(messages, **kw)
        dt = time.time() - t0
        if is_place:
            self.place_calls += 1
            self.place_secs += dt
        return out

    def chat_full(self, messages, **kw):
        self.gen_calls += 1
        return self.inner.chat_full(messages, **kw)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def main():
    char_id = sys.argv[1] if len(sys.argv) > 1 else "igusa_haruka"
    max_boards = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    seed = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_SEED

    table = load_table()
    cat = MediaCatalog(ROOT / "assets")
    scenes = set(cat.background_scenes())
    llm = Counting(LLMClient())
    char = None
    from core.parsing.dynamic_character_parser import CharacterLoader
    char = CharacterLoader(ROOT / "config" / "characters").load(char_id)
    vn = BondStoryEngine(ROOT / "config" / "characters", llm,
                         director=_build_director(char))
    vn.start_session(char_id)
    print(f"角色 {char_id} | 表 {len(table)} 条 | 词表键 {len(vn._place_keys)} 个 | "
          f"可用背景 {len(scenes)} 个")
    print(f"层2 词表体量 {len(table.lexicon_text())} 字符")
    print(f"种子: {seed}\n")

    n_switch = n_ok = n_miss = 0
    n_anchor = 0
    bg_seen = []
    inp = seed
    for i in range(1, max_boards + 1):
        t0 = time.time()
        scene = vn.send_vn_scene(inp, annotate=True)
        dur = time.time() - t0
        hint = scene.place_hint
        key = scene.place
        sid = vn._place_scene_id(key) if key else None
        bg = scene.background
        exists = None
        if bg and bg in scenes:
            m = cat.background(bg)
            exists = bool(m and m.path.exists()) if m else False
        anchors = [(j + 1, p.get("place")) for j, p in enumerate(scene.paragraphs)
                   if isinstance(p, dict) and p.get("place")]
        if hint:
            n_switch += 1
            if key:
                n_ok += 1
            else:
                n_miss += 1
        n_anchor += len(anchors)
        bg_seen.append(bg)
        print(f"── 板{i}  {len(scene.paragraphs)} 句  {dur:.0f}s  "
              f"is_end={scene.is_end}  choices={len(scene.choices)}")
        print(f"   switch 原文 : {hint or '（本板无换场）'}")
        print(f"   → 地点键    : {key or '（未变/keep）'}")
        print(f"   → 资产键    : {sid or '-'}")
        print(f"   → 背景      : {bg}   图存在={exists}")
        if anchors:
            print(f"   句级锚点    : "
                  + "; ".join(f"第{s}句→{p}" for s, p in anchors))
        if scene.choices:
            print(f"   选项        : {scene.choices}")
        if scene.is_end:
            break
        inp = scene.choices[0] if scene.choices else "（继续）"

    print("\n" + "=" * 66)
    print(f"换场 {n_switch} 次: 解出 {n_ok} / MISS {n_miss}; 句级锚点 {n_anchor} 条")
    print(f"背景序列: {bg_seen}")
    uniq = [b for b in dict.fromkeys(bg_seen) if b and b != "neutral"]
    print(f"非 neutral 背景 {len(uniq)} 种: {uniq}")
    if "neutral" in bg_seen:
        print("⚠️ 仍出现过 neutral（= 展示兜底会顶成 class_room）")
    print(f"地点相关调用 {llm.place_calls} 次 / 共 {llm.place_secs:.1f}s "
          f"（均 {llm.place_secs / max(llm.place_calls, 1):.2f}s）; "
          f"主生成 {llm.gen_calls} 次")


if __name__ == "__main__":
    main()
