# -*- coding: utf-8 -*-
"""地点标注真机基准（C2–C5 验收）: 层1 分流 / 层2 就近推测 / 句级锚点。

回答一个问题: **表接线之后, 真机上到底能不能工作。** 三段:

  ① 层1（0 调用）: 哪些地点话能纯字符串命中
  ② 层2（真 API）: 层1 接不住的那些, 模型拿着 **含 `note` 的整表** 会挑哪一条
     —— 这是"表外也能落位"的唯一验证点（我们自己的示例「深夜的杂草屋」就在这）
  ③ `annotate_places`（真 API）: 一块真实的板 → 句级锚点

用法: python experiments/place_resolve_real.py
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bond.place_annotate import (_RESOLVE_CACHE, annotate_places,  # noqa: E402
                                      resolve_place)
from core.media.place_table import load_table                          # noqa: E402
from llm.client import LLMClient                                       # noqa: E402

#: (地点话, 参考期望) —— 期望是**人判**, 不是真值; `None` = 只看它挑什么
#: ⚠️ 期望值要写**表的 `place` 键**（不是资产 slug、不是 A1 之前的 root 键）——
#: 首轮我就把 `riversideroad` 写成 `riverside_road`、`schale_office` 写成
#: `main_office`, 白记了两个 ✗。真实键用 `load_table().keys()` 查。
CASES = [
    # ── 真机生产里真实出现过的 ──
    ("教室", "classroom"),
    ("街角的咖啡馆，靠窗的位子", "moderncafe"),
    ("校舍后面的杂草屋", None),
    # ── 我们自己 prompt/契约里的示例 ──
    ("星空", "view_sky"),
    ("放学后的天台", "school_rooftop"),
    ("深夜的杂草屋", None),
    ("傍晚的杂草坡道", None),
    # ── 表里有明确正主的（考"读 note 找最近"） ──
    ("便利屋68的活动室", "68office"),
    ("游戏开发部的房间", "gamedevroom"),
    ("百花缭乱的榻榻米会客室", "hyakkayouran_tatamiroom"),
    ("河边那条樱花小路", "riversideroad"),
    ("流星雨的夜空", "view_constellation"),
    # ⚠️ 废弃琴房的正主 `ruinpianoroom`（kw=废弃琴房）**在表里没勾 active** →
    #    模型只能就近落到 `practiceroom`（乐队练习室）。这条 ✗ = **表缺口**, 不是模型错。
    ("废弃的琴房", None),
    ("夏莱的办公室", "schale_office"),
    # 「有护栏」是 `rooftop` 的 note 原文 → 考它是不是真读了 note
    ("天台的护栏边", "rooftop"),
    # ── 根本不是地点（该给空） ──
    ("第二天早上", ""),
    ("她沉默了一会儿", ""),
    ("雨停了", ""),
]

#: 一块真实的板（含一次换场 + 一次非地点推进）
BOARD = [
    "教室里只剩下我们两个。",
    "「老师，今天也陪我一会儿吧。」",
    "她说完就抓起书包，推开教室后门跑了出去。",
    "我跟着她穿过走廊，走上楼梯，推开天台的门。",
    "晚风把她的头发吹了起来。",
    "「你看，这里的星星比教室里看得清楚多了。」",
]
CURRENT_BEFORE = "classroom"


class Recording:
    """包一层 LLMClient: 记原始回复 / 耗时 / prompt 字符数（不改行为）。"""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def chat(self, messages, **kw):
        t0 = time.time()
        out = self.inner.chat(messages, **kw)
        self.calls.append({"raw": out, "dur": time.time() - t0,
                           "in_chars": len(messages[0]["content"])})
        return out

    def __getattr__(self, name):
        return getattr(self.inner, name)


def main():
    t = load_table()
    if not t.ok:
        print("表读不出来:", t.error)
        return
    keys = t.keys()
    s = t.stats()
    print(f"表: {s['n']} 条 / 别名 {s['keywords']} / 无 note {s['no_note']} / "
          f"写作用词 {s['writing']} 条")
    print(f"层2 词表文本: {len(t.lexicon_text())} 字符"
          f"（≈{len(t.lexicon_text()) // 2} tokens, 只在层1 未命中时付）\n")

    # ── ① 层1 分流（0 调用, 先不碰 API） ──
    print("=" * 74)
    print("① 层1 分流（纯字符串, 0 调用）")
    print("=" * 74)
    layer2_cases = []
    for text, want in CASES:
        hits = t.resolve_exact(text)
        if len(hits) == 1:
            mark = "✔" if (want is None or hits[0] == want) else "✗"
            print(f"  {mark} 层1  {text:<22} → {hits[0]}")
        elif hits:
            print(f"  ⚠ 歧义 {text:<22} → {len(hits)} 条 {hits[:4]}")
            layer2_cases.append((text, want))
        else:
            print(f"  ·  层2  {text:<22} （层1 未命中）")
            layer2_cases.append((text, want))
    print(f"\n  层1 独占命中 {len(CASES) - len(layer2_cases)}/{len(CASES)}; "
          f"需层2 {len(layer2_cases)} 条\n")

    # ── ② 层2 真机（含 note 的整表） ──
    print("=" * 74)
    print("② 层2 真机: 拿含 note 的整表挑一条")
    print("=" * 74)
    llm = Recording(LLMClient())
    ok = bad = 0
    for text, want in layer2_cases:
        _RESOLVE_CACHE.clear()
        got = resolve_place(llm, text, keys, "", table=t)
        call = llm.calls[-1] if llm.calls else None
        entry = t.get(got) if got else None
        if want is None:
            verdict = "（人判）"
        elif got == want:
            verdict = "✔"; ok += 1
        else:
            verdict = f"✗ 期望 {want}"; bad += 1
        dur = f"{call['dur']:.1f}s" if call else "0s"
        print(f"  {text:<22} → {got or '（空=keep）':<26} {verdict}  [{dur}]")
        if entry and entry.note:
            print(f"      选中条目 note: {entry.note[:56]}")
    if ok or bad:
        print(f"\n  有人判期望的: ✔{ok} / ✗{bad}（其余看它挑什么）")

    # ── ③ 句级锚点（annotate_places, 真 API） ──
    print()
    print("=" * 74)
    print("③ annotate_places 真机: 一块板 → 句级锚点")
    print("=" * 74)
    n0 = len(llm.calls)
    t0 = time.time()
    anchors = annotate_places(llm, BOARD, keys, CURRENT_BEFORE, table=t)
    dur = time.time() - t0
    print(f"  当前地点 = {CURRENT_BEFORE}; 板 {len(BOARD)} 句; 耗时 {dur:.1f}s")
    for a in anchors:
        i = a["sentence"] - 1
        print(f"    第 {a['sentence']} 句 → {a['place']}"
              f"    （{BOARD[i][:34]}…）" if i < len(BOARD) else f"    {a}")
    if not anchors:
        print("    （无锚点 = keep——画面不动）")
    print(f"  调用 {len(llm.calls) - n0} 次; prompt {llm.calls[-1]['in_chars']} 字符")

    # ── 汇总 ──
    total = len(llm.calls)
    print()
    print(f"真机调用合计 {total} 次; 平均 {sum(c['dur'] for c in llm.calls) / max(total, 1):.1f}s; "
          f"最长 {max((c['dur'] for c in llm.calls), default=0):.1f}s")


if __name__ == "__main__":
    main()
