"""写手（bond 任务, thinking=high）内联 `act` + `emotion` 的可行性探针 —— 真实 API。

问的是三件事（只有真机数据能答）:
  ① 写手会不会**照做**（每条记录在 `text` 之前补 `emotion` / `act`）;
  ② 补了之后**行有没有被写坏**（整行 JSON 解析失败 = 正文丢失, 这是最坏情况）;
  ③ 代价多大（输出字符数 / 耗时 相对"不带指令"的基线）。

做法: **不动契约, 不改引擎** —— 只给 system 末尾追加一段实验指令 + 两张词表,
  然后旁路记录写手的原始输出; 引擎照常解析（多出来的字段会被当成未知键记 note,
  正好能看出"多给字段会不会导致丢行"）。

隔离: 不 attach SessionStore → 不写任何 events.jsonl; 进程结束即销毁。

用法（在项目根, 烧 token）:
    python experiments/vn_inline_fields_probe.py --rounds 5 --thinking high
    python experiments/vn_inline_fields_probe.py --rounds 5 --thinking high --on   # 带指令
    （两次跑同一 seed 才能比基线; --on 默认开）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.bond.actions import ACTION_NAMES, ACTIONS  # noqa: E402
from core.bond.bond_story import BondStoryEngine  # noqa: E402
from llm.client import LLMClient  # noqa: E402
from llm.task_labels import BOND  # noqa: E402

DEFAULT_SEED = "（旁白）放学后的教室里，老师来找遥香，今天想陪她多待一会儿。"
#: 每个 run 一个新 seed ⇒ 一个新会话 ⇒ 一次新的写手调用
SEEDS = [
    DEFAULT_SEED,
    "（旁白）午休时间，遥香一个人在食堂角落吃饭，老师端着餐盘走过来。",
    "（旁白）下雨天，遥香在图书馆窗边看书，老师淋着雨冲进来。",
    "（旁白）深夜的杂草屋，遥香在整理捡来的东西，老师敲了敲门。",
    "（旁白）周末的商店街，遥香抱着购物袋站在路口，老师刚好路过。",
]
OUT_DIR = ROOT / ".testtmp"

INSTRUCTION = """

【实验附加指令（临时）】
本次输出的**每一条 character 记录**，在 `text` **之前**再给两个可选字段：
  `emotion`: 这一句她在什么表情。取值只能是下面表情词表里的键。
  `act`: 这一句她有没有身体动作。只有一个动作, 取自动作词表; 没有就**不写这个字段**。
字段顺序固定为 `{"character": …, "emotion": …, "act": …, "text": …}`——
`text` 必须**是最后一个字段**（后面的内容一律算正文）。
`stage` 记录不要加这两个字段。

表情词表: __EMO__
动作词表: __ACT__
动作含义（只在身体真的动起来时用, 绝大多数句子没有动作）:
__ACTLINES__
"""


def _instruction(lexicon_keys: list[str]) -> str:
    act_lines = "\n".join(f"  {a.name}: {a.when}" for a in ACTIONS)
    # 用 replace 而不是 format: 指令里含字面量 `{"character": …}`（花括号）
    return (INSTRUCTION.replace("__EMO__", " / ".join(lexicon_keys))
            .replace("__ACT__", " / ".join(sorted(ACTION_NAMES)))
            .replace("__ACTLINES__", act_lines))


class ProbeLLM:
    """包装真实 client: 按档位注入 reasoning、给 system 追加实验指令、旁路记录原始输出。"""

    def __init__(self, inner, thinking: str, inject: bool, lexicon_keys: list[str]):
        self._inner = inner
        self.thinking = thinking
        self.inject = inject
        self.extra = _instruction(lexicon_keys) if inject else ""
        self.raw: list[dict] = []

    def _extra_body(self):
        if self.thinking == "off":
            return {}
        if self.thinking in ("low", "medium", "high"):
            return {"reasoning_effort": self.thinking}
        return None

    def _prep(self, messages):
        if not self.extra:
            return messages
        msgs = [dict(m) for m in messages]
        for m in msgs:
            if m.get("role") == "system":
                m["content"] = m["content"] + self.extra
                break
        return msgs

    def _tap(self, name, messages, kw):
        kw = dict(kw)
        if kw.get("extra_body") is None:
            kw["extra_body"] = self._extra_body()
        t0 = time.monotonic()
        res = getattr(self._inner, name)(self._prep(messages), **kw)
        dt = int((time.monotonic() - t0) * 1000)
        if kw.get("task") == BOND:
            self.raw.append({"ms": dt, "text": str(res), "max_tokens": kw.get("max_tokens")})
        return res

    def chat(self, messages, **kw):
        return self._tap("chat", messages, kw)

    def chat_full(self, messages, **kw):
        return self._tap("chat_full", messages, kw)

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


def _lines(raw: str) -> list[dict]:
    """原始输出 → 逐行 dict（非 `{` 开头的行 = 围栏/说明, 不算行）。"""
    out: list[dict] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
        except ValueError:
            out.append({"__bad__": s[:100]})
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def analyze(raw: str, lexicon: set[str]) -> dict:
    rows = _lines(raw)
    bad = [r for r in rows if "__bad__" in r]
    chars = [r for r in rows if "character" in r]
    with_emo = [r for r in chars if isinstance(r.get("emotion"), str) and r["emotion"].strip()]
    with_act = [r for r in chars if isinstance(r.get("act"), str) and r["act"].strip()]
    emo_ok = [r for r in with_emo if r["emotion"].strip() in lexicon]
    act_ok = [r for r in with_act if r["act"].strip() in ACTION_NAMES]
    text_last = [r for r in chars if list(r.keys())[-1] == "text"]
    return {
        "rows": len(rows), "bad": len(bad),
        "chars": len(chars),
        "with_emo": len(with_emo), "emo_ok": len(emo_ok),
        "with_act": len(with_act), "act_ok": len(act_ok),
        "text_last": len(text_last),
        "chars_len": len(raw),
        "bad_samples": [r["__bad__"] for r in bad[:3]],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="写手内联 act/emotion 可行性探针（真实 API）")
    ap.add_argument("--runs", type=int, default=3,
                    help="跑几个独立会话（每个都产生一次写手调用）")
    ap.add_argument("--rounds", type=int, default=5, help="（旧名, 保留兼容; 已不用）")
    ap.add_argument("--thinking", default="high", help="high/low/medium/off/default")
    ap.add_argument("--char", default="igusa_haruka")
    ap.add_argument("--seed", default=DEFAULT_SEED)
    ap.add_argument("--no-inject", dest="inject", action="store_false", default=True)
    ap.add_argument("--min-emo", type=float, default=0.80,
                    help="情绪覆盖率下限: 低于它就判死（情绪不可省略）")
    args = ap.parse_args()

    llm = ProbeLLM(LLMClient(), args.thinking, args.inject, [])
    vn = BondStoryEngine(ROOT / "config" / "characters", llm)
    vn.start_session(args.char)
    lexicon = set(vn._lexicon_keys)
    llm.extra = _instruction(vn._lexicon_keys) if llm.inject else ""

    print(f"角色={args.char} 词表 {len(lexicon)} 键 · 动作 {len(ACTION_NAMES)} 键 · "
          f"thinking={args.thinking} · 指令={'开' if llm.inject else '关(基线)'}")

    totals = {"rows": 0, "bad": 0, "chars": 0, "with_emo": 0, "emo_ok": 0,
              "with_act": 0, "act_ok": 0, "text_last": 0, "chars_len": 0}
    #: 每个 run 开一个**新会话 + 新 seed** ⇒ 每个 run 必然有一次写手调用。
    #: （只喂同一会话的后续板 = 消费预生成, 不产生新调用 —— 那会白算样本量。）
    for i in range(1, args.runs + 1):
        seed = args.seed if args.runs == 1 else SEEDS[(i - 1) % len(SEEDS)]
        vn = BondStoryEngine(ROOT / "config" / "characters", llm)
        vn.start_session(args.char)
        before = len(llm.raw)
        t0 = time.monotonic()
        try:
            scene = vn.send_vn_scene(seed)
        except Exception as e:                        # noqa: BLE001 — 单次失败继续
            print(f"  run {i} FAILED: {type(e).__name__}: {str(e)[:120]}")
            continue
        dt = int((time.monotonic() - t0) * 1000)
        raws = llm.raw[before:]
        stats = [analyze(r["text"], lexicon) for r in raws]
        agg = {k: sum(s[k] for s in stats) for k in totals}
        bad_samples = [b for s in stats for b in s["bad_samples"]]
        for k in totals:
            totals[k] += agg[k]
        drops = [n for n in (scene.notes or []) if "丢" in n or "drop" in n.lower()]
        print(f"  run {i} {dt}ms  写手调用 {len(raws)} 次 · 引擎收下 {len(scene.records)} 条 · "
              f"原始 {agg['rows']} 行（坏行 {agg['bad']}）· "
              f"带表情 {agg['with_emo']} 词表内 {agg['emo_ok']} · "
              f"带动作 {agg['with_act']} 词表内 {agg['act_ok']} · "
              f"text 在末位 {agg['text_last']}/{agg['chars']} · "
              f"输出 {agg['chars_len']} 字符")
        if bad_samples:
            print(f"      坏行样本: {bad_samples[0]!r}")
        if drops:
            print(f"      引擎丢行: {drops[:2]}")

    print("\n===== 汇总 =====")
    if totals["chars"]:
        print(f"character 行 {totals['chars']} · 坏行 {totals['bad']} "
              f"({100 * totals['bad'] / max(1, totals['rows']):.1f}%)")
        print(f"内联情绪 {totals['with_emo']} ({100 * totals['with_emo'] / totals['chars']:.0f}%)"
              f" · 词表内 {totals['emo_ok']} "
              f"({100 * totals['emo_ok'] / max(1, totals['with_emo']):.0f}%)")
        print(f"内联动作 {totals['with_act']} ({100 * totals['with_act'] / totals['chars']:.0f}%)"
              f" · 词表内 {totals['act_ok']} "
              f"({100 * totals['act_ok'] / max(1, totals['with_act']):.0f}%)")
        cov = totals["with_emo"] / totals["chars"]
        print(f"情绪覆盖率 {100 * cov:.0f}%（下限 {100 * args.min_emo:.0f}%）⇒ "
              f"{'通过' if cov >= args.min_emo else '判死'}"
              " —— 情绪不可省略, 靠 carry 补满不算数")
        print(f"`text` 在末位 {totals['text_last']}/{totals['chars']} "
              f"({100 * totals['text_last'] / totals['chars']:.0f}%)  ← 这条不到 100% 就不能放字段")
    print(f"输出合计 {sum(len(r['text']) for r in llm.raw)} 字符 · "
          f"LLM 调用 {len(llm.raw)} 次 · 均 {int(sum(r['ms'] for r in llm.raw) / max(1, len(llm.raw)))}ms")

    OUT_DIR.mkdir(exist_ok=True)
    dump = OUT_DIR / "vn_inline_fields_samples.jsonl"
    with dump.open("w", encoding="utf-8") as fh:
        for r in llm.raw:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"原始输出已存 → {dump.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
