"""情绪标注的**线格式** A/B —— 真实 API + 真机板（只读）。

三档，同一批板:
    A  今天的形状: `{"labels": {"1": "smile"}}`（json_object, 一次性）
    B  JSONL 扁平: 每行 `{"1": "smile"}` 或 `{"2": "smile|jump"}`（流式）
    C  JSONL 命名字段: 每行 `{"row": 1, "emotion": "smile", "act": "jump"}`（流式）

量的四件事:
    ① 首行到位（第一次拿到可解析行）—— 玩家真正感知的那个数
    ② 整板完成 —— 门控要等的那个数
    ③ 正确率: 行数是否齐 / 键是否在词表内 / 有没有垃圾行（解释、围栏、多对象）
    ④ 相邻同键率（连续性）与动作命中率（动作通路到底会不会触发）

真板来源: `data/worlds/*/characters/*/soul/events.jsonl` 的 bond 板 × **只读**。
提示词来源: 真模板 + 真词表 + 真人设卡（起一个引擎读它的三个私有字段, 不发请求）;
  B/C 只**替换示范与输出规格**（其余逐字节与 A 相同）, 这样三档可比。

用法（在项目根, 烧 token; 一板 = 1~2 次调用）:
    python experiments/anno_wire_probe.py --limit 20
    python experiments/anno_wire_probe.py --limit 20 --variants A,B,C
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from contract.slots import render_template  # noqa: E402
from core.bond.actions import ACTION_NAMES, render_prompt_block  # noqa: E402
from core.bond.bond_story import BondStoryEngine  # noqa: E402
from core.bond.emo_text import annotate_items, pick_demo_keys  # noqa: E402
from llm.client import LLMClient  # noqa: E402
from llm.prompts import load_prompt  # noqa: E402
from llm.task_labels import EMOTION  # noqa: E402
from llm.task_levels import extra_body as _tl_extra  # noqa: E402
from llm.task_levels import max_tokens as _tl_max_tokens  # noqa: E402

EVENTS = ROOT / "data" / "worlds" / "world1" / "characters" / "igusa_haruka" / "soul" / "events.jsonl"

_SPEC_B = """【输出】严格 JSONL: 一行一条记录, **不要**包在外层对象里, 不要任何解释:
{"行号": "情绪键"}
- 行号 = 上面【本板】的行号, 共 {{n}} 行: 每行一条, 不许合并/省略
- 这一行她还有身体动作, 就把键写成 "情绪键|动作键"; 没有动作就只写情绪键
- 只有这些行, 无 markdown 围栏、无前后说明"""

_SPEC_C = """【输出】严格 JSONL: 一行一条记录, **不要**包在外层对象里, 不要任何解释:
{"row": 行号, "emotion": "情绪键"}
- `row` = 上面【本板】的行号, 共 {{n}} 行: 每行一条, 不许合并/省略
- 这一行她还有身体动作, 就在同一行再加 "act": "动作键"; 没有动作就不写这个字段
- 只有这些行, 无 markdown 围栏、无前后说明"""


class _NoLLM:
    """只用来构造引擎读词表/人设卡（绝不发请求）。"""

    def chat(self, *a, **k):
        raise RuntimeError("探针不调用写手")

    def format_messages(self, **k):
        return []


def load_boards(limit: int) -> list[dict]:
    """真机 bond 板 → [{items, prev, text_prev}]（只读）。"""
    boards: list[dict] = []
    prev_keys: list[str] = []
    prev_text = ""
    for line in EVENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ev = json.loads(line)
        if ev.get("type") != "bond":
            continue
        paras = [p for p in (ev.get("payload") or {}).get("paragraphs") or []
                 if isinstance(p, dict) and (p.get("text") or "").strip()]
        items = [p["text"].strip() for p in paras]
        keys = [p.get("emotion") or "" for p in paras]
        if items:
            boards.append({
                "items": items,
                "prev": (prev_keys[-1] if prev_keys else "nomal"),
                "context": (f"（上一板记录原文）\n{prev_text}\n"
                            f"（上一板末条已生效情绪: {prev_keys[-1] if prev_keys else 'nomal'}）")
                if prev_text else "",
            })
        if items:
            prev_keys = keys
            prev_text = "\n".join(items)
        if len(boards) >= limit:
            break
    return boards


def _resyntax(out: str, variant: str) -> str:
    """把**示范里的输出行**改写成目标语法 —— 示范条数/键值不变, 只换写法。

    这样才能把"线格式"和"示范教了多少"分开: 上一版我给 B/C 删了两个示范再补一个,
    等于同时改了示范数量, 那份对照不干净。
    """
    def _one(m: re.Match) -> str:
        pairs = re.findall(r'"(\d+)"\s*:\s*"?([a-z_]+)"?', m.group(0))
        if not pairs:
            return m.group(0)
        if variant == "B":
            return "输出: " + "\n".join(f'{{"{i}": "{k}"}}' for i, k in pairs)
        return "输出: " + "\n".join(
            f'{{"row": {i}, "emotion": "{k}"}}' for i, k in pairs)
    return re.sub(r"^输出: .*$", _one, out, flags=re.M)


def build_system(vn, items: list[str], context: str, variant: str) -> str:
    n = len(items)
    key_n, key_a, key_b = pick_demo_keys(vn._lexicon_keys)
    numbered = "\n".join(f"{i + 1}: {s}" for i, s in enumerate(items))
    out = render_template(
        load_prompt("emotion_text_annotate"),
        {"group_no": "X", "char_name": vn._current_char.display_name,
         "character_hint": vn._character_hint,
         "context": context or "（本章开场, 无更多情境。）",
         "n": str(n), "records": numbered,
         "lexicon": vn._lexicon_hint or "\n".join(vn._lexicon_keys),
         "acts": render_prompt_block(),
         "key_n": key_n, "key_a": key_a, "key_b": key_b},
        where="emotion_text_annotate.md")
    if variant == "A":
        return out
    out = _resyntax(out.split("【输出】")[0], variant)      # 示范只换语法
    spec = _SPEC_B if variant == "B" else _SPEC_C
    return out + spec.replace("{{n}}", str(n))


def user_msg(variant: str, n: int) -> str:
    if variant == "A":
        return ('请按行输出情绪键, 包装为 {"labels": {行号: 键}}, 行号从 1 到 '
                + str(n) + "（恰 " + str(n) + ' 项）; 这一行她还有身体动作, '
                '就把键写成 "情绪键|动作键"。')
    if variant == "B":
        ex = '{"行号": "键"}'
        return f"请输出 {n} 行, 每行 {ex}（行号 1..{n}）, 不要外壳对象, 不要解释。"
    ex = '{"row": 行号, "emotion": "键"}'
    return (f"请输出 {n} 行, 每行 {ex}（行号 1..{n}）, "
            "有动作就再加 act, 不要外壳对象, 不要解释。")


def parse_row(line: str, variant: str) -> tuple[int, str, str] | None:
    """一行 → (行号, 情绪键, 动作键); 认不出 → None（垃圾行）。"""
    s = line.strip().rstrip(",")
    if not s.startswith("{"):
        return None
    try:
        obj = json.loads(s)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    if variant == "B":
        for k, v in obj.items():
            try:
                idx = int(k)
            except (TypeError, ValueError):
                continue
            if isinstance(v, str):
                parts = [p.strip() for p in v.split("|") if p.strip()]
                return idx, (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
        return None
    row = obj.get("row")
    if not isinstance(row, int):
        return None
    return row, str(obj.get("emotion") or "").strip(), str(obj.get("act") or "").strip()


def run_stream(llm, system: str, user: str, n: int, variant: str) -> dict:
    """走**生产该走的那条路**: `chat_full(stream=True, on_chunk=…)`。

    它不是 `chat_stream`（那个是裸生成器: 无重试 / 无 usage / 无 extra_body）。
    `chat_full` 自带: extra_body(思考档位) · on_chunk 增量回调 · 429/5xx/超时退避 ·
    TTFT/usage 日志 · 返回完整串（收尾"末尾半行没换行"用）。

    ⚠️ `_stream_collect` 的重试是**整条流重放**（每个 attempt 都从头 drain）⇒ 消费侧
    必须幂等: 这里按行号覆盖 `rows[idx] = row`, 不累加、不设"已定稿"。
    """
    t0 = time.monotonic()
    st: dict = {"buf": "", "rows": {}, "junk": 0, "first": None}

    def _feed(chunk: str) -> None:
        st["buf"] += chunk
        while "\n" in st["buf"]:
            line, st["buf"] = st["buf"].split("\n", 1)
            if not line.strip():
                continue
            got = parse_row(line, variant)
            if got is None:
                st["junk"] += 1
                continue
            st["rows"][got[0]] = got                  # 幂等: 重放只覆盖
            if st["first"] is None:
                st["first"] = time.monotonic() - t0

    try:
        llm.chat_full(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2, max_tokens=_tl_max_tokens("emotion"),
            on_chunk=_feed,
            extra_body=_tl_extra("emotion"), task=EMOTION,
        )
    except Exception as e:                            # noqa: BLE001 — 流断就是失败样本
        return {"err": f"{type(e).__name__}: {str(e)[:80]}", "rows": st["rows"],
                "junk": st["junk"], "first_ms": None,
                "total_ms": int((time.monotonic() - t0) * 1000)}
    tail = st["buf"].strip()
    if tail:                                          # 末尾没有换行符的那半行
        got = parse_row(tail, variant)
        if got:
            st["rows"][got[0]] = got
        else:
            st["junk"] += 1
    return {"err": "", "rows": st["rows"], "junk": st["junk"],
            "first_ms": (int(st["first"] * 1000)
                         if st["first"] is not None else None),
            "total_ms": int((time.monotonic() - t0) * 1000)}


def run_block(llm, system: str, user: str, n: int, variant: str) -> dict:
    """C 的**形状** + **非流式**传输（chat + response_format=text, 整串回来再切行）。

    用来把"形状"和"传输"拆开: 如果它和流式 C 一样好, 那流式只值那 ~190ms。
    """
    t0 = time.monotonic()
    try:
        text = llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2, max_tokens=_tl_max_tokens("emotion"),
            response_format="text", extra_body=_tl_extra("emotion"), task=EMOTION,
        )
    except Exception as e:                            # noqa: BLE001
        return {"err": f"{type(e).__name__}: {str(e)[:80]}", "rows": {}, "junk": 0,
                "first_ms": None, "total_ms": int((time.monotonic() - t0) * 1000)}
    rows, junk = {}, 0
    for line in str(text).splitlines():
        if not line.strip():
            continue
        got = parse_row(line, variant)
        if got is None:
            junk += 1
            continue
        rows[got[0]] = got
    ms = int((time.monotonic() - t0) * 1000)
    return {"err": "", "rows": rows, "junk": junk, "first_ms": ms, "total_ms": ms}


def score(rows: dict, n: int, lexicon: set[str]) -> dict:
    """一板 → 质量向量。**变化度**是这里的主指标（越多变越好, 不是越连续越好）:"""
    ordered = [rows[i] for i in sorted(rows)]
    keys = [r[1] for r in ordered]
    acts = [r[2] for r in ordered if r[2]]
    adj = [(a, b) for a, b in pairwise(keys) if a and b]
    counts = Counter(k for k in keys if k)
    top = max(counts.values()) if counts else 0
    return {
        "n": n, "got": len(rows),
        "complete": len(rows) == n,
        "in_lex": sum(1 for k in keys if k in lexicon),
        "out_lex": sum(1 for k in keys if k and k not in lexicon),
        "acts": sum(1 for a in acts if a in ACTION_NAMES),
        "adj_same": sum(1 for a, b in adj if a == b),
        "adj": len(adj),
        # 变化度: 一板用了几个不同的键 / 单一键最多占几成
        "distinct": len(counts),
        # 短板(<=3 行)的"单键最大"没有意义(两行同键就是 100%) -> 只算 n>=4 的板
        "top_share": (top / len(keys)) if keys and n >= 4 else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="情绪标注线格式 A/B（真实 API, 真机板只读）")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--variants", default="A,B,C")
    ap.add_argument("--dry-run", action="store_true",
                    help="不发请求: 只验提示词装配 + 解析器（用假输出自测）")
    args = ap.parse_args()

    boards = load_boards(args.limit)
    if not boards:
        print("没找到真机 bond 板 —— 检查 data/worlds 路径")
        return 1
    vn = BondStoryEngine(ROOT / "config" / "characters", _NoLLM())
    vn.start_session("igusa_haruka")
    lexicon = set(vn._lexicon_keys)
    variants = [v.strip().upper() for v in args.variants.split(",") if v.strip()]
    print(f"板 {len(boards)} 块 · 词表 {len(lexicon)} 键 · 动作 {len(ACTION_NAMES)} 键 · "
          f"档位 {variants}")

    if args.dry_run:
        b = boards[0]
        n = len(b["items"])
        for v in variants:
            system = build_system(vn, b["items"], b["context"], v)
            fake = ('{"1": "smile"}' if v == "B"
                    else '{"row": 1, "emotion": "smile"}') if v != "A" else ""
            got = parse_row(fake, v) if fake else (1, "smile", "")
            print(f"  [{v}] system={len(system)} 字符 · 含输出规格="
                  f"{'严格 JSONL' in system or '严格 JSON 对象' in system} · "
                  f"行解析={got}")
            print(f"      示范段尾部: …{system.strip().splitlines()[-1][:70]}")
        print("\ndry-run 通过: 装配/解析可用, 未发任何请求")
        return 0

    agg = {v: {"first": [], "total": [], "junk": 0, "rows": 0, "n": 0,
               "complete": 0, "in_lex": 0, "out_lex": 0, "acts": 0,
               "adj_same": 0, "adj": 0, "err": 0,
               "distinct": 0, "top": 0.0, "act_boards": 0} for v in variants}
    for bi, b in enumerate(boards, 1):
        items = b["items"]
        n = len(items)
        for v in variants:
            if v == "A":
                llm = LLMClient()
                t0 = time.monotonic()
                try:
                    labels, acts, info = annotate_items(
                        llm, items, vn._lexicon_keys, vn._lexicon_hint,
                        vn._character_hint, vn._current_char.display_name,
                        context=b["context"], group_no=bi, prev=b["prev"])
                    ms = int((time.monotonic() - t0) * 1000)
                    rows = {i + 1: (i + 1, labels[i], acts[i]) for i in range(len(labels))}
                    r = {"err": "", "rows": rows, "junk": 0, "first_ms": ms, "total_ms": ms}
                    r["info"] = info
                except Exception as e:                # noqa: BLE001
                    agg[v]["err"] += 1
                    print(f"  [{v}] 板{bi} 失败: {type(e).__name__}: {str(e)[:60]}")
                    continue
            else:
                llm = LLMClient()
                system = build_system(vn, items, b["context"], v)
                if v == "D":
                    r = run_block(llm, system, user_msg(v, n), n, "C")
                    r["junk"] = r["junk"]
                r = run_stream(llm, system, user_msg(v, n), n, v)
                if r["err"]:
                    agg[v]["err"] += 1
                    print(f"  [{v}] 板{bi} 流失败: {r['err']}")
            s = score(r["rows"], n, lexicon)
            a = agg[v]
            a["n"] += n
            a["rows"] += s["got"]
            a["complete"] += int(s["complete"])
            a["in_lex"] += s["in_lex"]
            a["out_lex"] += s["out_lex"]
            a["acts"] += s["acts"]
            a["adj_same"] += s["adj_same"]
            a["adj"] += s["adj"]
            a["distinct"] += s["distinct"]
            a["top"] = max(a["top"], s["top_share"])
            a["act_boards"] += int(s["acts"] > 0)
            a["junk"] += r["junk"]
            if r["first_ms"] is not None:
                a["first"].append(r["first_ms"])
            a["total"].append(r["total_ms"])
            extra = f" retry={r['info'].get('retry')}" if "info" in r else ""
            print(f"  [{v}] 板{bi} n={n} 行={s['got']} 垃圾={r['junk']} "
                  f"首行={r['first_ms']}ms 整板={r['total_ms']}ms "
                  f"词表外={s['out_lex']} 动作={s['acts']}{extra}")

    def pct(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else 0

    print("\n===== 汇总 =====")
    print(f"{'档':<3}{'首行p50':>9}{'首行p95':>9}{'整板p50':>10}{'整板p95':>10}"
          f"{'整板齐':>8}{'行命中':>9}{'垃圾行':>8}{'词表外':>8}{'动作':>6}"
          f"{'相邻同键':>10}{'去重键':>8}{'单键最大':>9}{'失败':>6}")
    for v in variants:
        a = agg[v]
        adj = f"{100 * a['adj_same'] / a['adj']:.0f}%" if a["adj"] else "-"
        print(f"{v:<3}{pct(a['first'], .5):>9}{pct(a['first'], .95):>9}"
              f"{pct(a['total'], .5):>10}{pct(a['total'], .95):>10}"
              f"{a['complete']:>8}{a['rows']:>9}{a['junk']:>8}{a['out_lex']:>8}"
              f"{a['acts']:>6}{adj:>10}{a['distinct']:>8}"
              f"{100 * a['top']:>8.0f}%{a['err']:>6}")
    for v in variants:
        a = agg[v]
        hit = a["rows"] / a["n"] if a["n"] else 0.0
        print(f"  [{v}] 情绪覆盖 {100 * hit:.0f}% ⇒ "
              f"{'通过' if hit >= 0.80 else '判死'}（下限 80%: 情绪不可省略）")
    print(f"\n（'整板齐' = 行数恰好的板数 / {len(boards)}; '行命中' = 收到的行数 / "
          f"应标行数; '相邻同键' 今天 18%——**越低越多变, 高了就是偷\xe6\x87\x92**; "
          f"'单键最大' = 该档里最差那一板的单一键占比）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
