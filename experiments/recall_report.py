# -*- coding: utf-8 -*-
"""recall_report.py — **真机观察清单**的一条命令版（只读, 零引擎改动）。

## 它回答什么

PROCEED §2 那张"真机观察清单"要看的六个数, 全在 `data/diag/live2be.log` 里
（`webgui/app.py` 挂的 FileHandler; 路径真源 = `core.paths.DIAG_LOG_PATH`）:

| 看什么 | 从哪几行读 |
|---|---|
| 三段实际长度（撞没撞满 1000 字符） | `mmt_recall … per=name:…/when:…/turn:…` |
| 空手占比 | `mmt_recall … modes=name(empty)+…` |
| 她会不会过度汇报"想不起来" | 同上（`(empty)` 的出现率） |
| `noticed` 写不写 / 抄得对不对 | `mmt_noticed hit=… title='…' said='…'` / `drop=…` |
| `look` 用了几次 | `mmt_look …`（命中/空手/名字认不出 各自形状） |
| `ms=` 召回耗时 | `mmt_recall … ms=`（＋每轮 `mmt_turn … first_ms= ms=`） |
| 前缀缓存 | `llm chat_full … cache_hit= cache_miss=` |
| brain 段（顺带） | `recall_read … buckets=… dropped=…` |

## 怎么用

    python experiments/recall_report.py                     # 默认读 DIAG_LOG_PATH
    python experiments/recall_report.py --log 别的.log --char igusa_haruka

⛔ **纯读**: 只开文件读、只打 stdout, 不写盘、不碰引擎、不连 LLM。
⚠️ **两代格式都认**: 2026-10-12 之前的 `mmt_recall` 只有 `eps=/chars=/mode=`
（没有 `per=`/`ms=`）——那种行仍然统计总字数, 但**三段分布与耗时是"没有数据"**,
不是 0（`新格式 0 行` 就是提醒你该跑一次真机了）。
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.brain.read import recall_config          # noqa: E402
from core.paths import DIAG_LOG_PATH               # noqa: E402

#: 一行日志: `2026-10-08 20:06:33 core.mmt.engine INFO <msg>`
LINE = re.compile(r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) "
                  r"(?P<logger>\S+) (?P<level>\w+) (?P<msg>.*)$")

#: ⭐ 新格式（2026-10-12 起）: 有 `per=` 与 `ms=`
RECALL_NEW = re.compile(
    r"mmt_recall (?P<char>\S+) modes=(?P<modes>\S+) eps=(?P<eps>\d+) "
    r"name=(?P<name>\d+) when=(?P<when>\d+) chars=(?P<chars>\d+) "
    r"per=(?P<per>\S+) ms=(?P<ms>[\d.]+)")
#: 旧格式: 只有总字数（三段之前的档）
RECALL_OLD = re.compile(
    r"mmt_recall (?P<char>\S+) eps=(?P<eps>\d+) chars=(?P<chars>\d+)")

READ_NEW = re.compile(
    r"recall_read surface=(?P<surface>\S+) char=(?P<char>\S+) total=(?P<total>\d+) "
    r"picked=(?P<picked>\d+) dropped=(?P<dropped>\d+) mode=(?P<mode>\S+) "
    r"buckets=(?P<buckets>\S+)")

#: `mmt_look` 的四种落点（命中 / 空手 / 名字认不出 / 时间认不出 / 标题查）
LOOK_HIT = re.compile(r"mmt_look \S+ entity=(?P<e>.*?) clue=(?P<c>.*?) when=(?P<w>.*?) "
                      r"form=\S+ cand=(?P<cand>\d+)")
LOOK_EMPTY = re.compile(r"mmt_look \S+ entity=(?P<e>.*?) clue=(?P<c>.*?) "
                        r"when=(?P<w>.*?) ⇒ 空（连着第 (?P<n>\d+) 次）")
LOOK_BAD_ENTITY = re.compile(r"mmt_look \S+ entity=(?P<e>.*?) ⇒")
LOOK_BAD_WHEN = re.compile(r"mmt_look \S+ when=(?P<w>.*?) 认不出")
LOOK_BY_TITLE = re.compile(r"mmt_look \S+ 标题查")

NOTICED_HIT = re.compile(r"mmt_noticed hit=(?P<hit>\S+) title='(?P<title>[^']*)' "
                         r"said='(?P<said>[^']*)'")
NOTICED_DROP = re.compile(r"mmt_noticed drop=(?P<why>\S+) said=")

TURN = re.compile(r"mmt_turn \S+ steps=(?P<steps>\d+) rows=(?P<rows>\d+) "
                  r"delivered=(?P<deliv>\d+) first_ms=(?P<first>\d+) ms=(?P<ms>\d+)")

LLM = re.compile(r"llm (?P<kind>chat_full|chat) ms=(?P<ms>\d+) .*?"
                 r"cache_hit=(?P<hit>-?\d+) cache_miss=(?P<miss>\d+)")


def _p90(values: list[int]) -> str:
    """P90（样本 < 2 条时不编数 —— 印 `-`）。"""
    if len(values) < 2:
        return "-"
    return f"{statistics.quantiles(values, n=10)[8]:.0f}"


def _stat(values: list[int]) -> str:
    if not values:
        return "（没有数据）"
    return (f"n={len(values)} 平均 {statistics.fmean(values):.0f} "
            f"P90 {_p90(values)} 最长 {max(values)}")


def _parse_per(per_txt: str) -> dict[str, tuple[int, bool]]:
    """`name:58/when:0(empty)/turn:144` → `{段: (字数, 是不是空手)}`。"""
    out: dict[str, tuple[int, bool]] = {}
    for item in per_txt.split("/"):
        label, _, num = item.partition(":")
        empty = num.endswith("(empty)")
        out[label] = (int(num.removesuffix("(empty)") or 0), empty)
    return out


def collect(path: Path, char: str = "") -> dict:
    """读日志 → 结构化计数（纯函数, 一行日志一次判断）。

    ⚠️ **`--char` 只能过滤"行里带角色 id"的那几族**（`mmt_recall` / `recall_read` /
    `mmt_look` / `mmt_turn`）—— `mmt_noticed` 与 `llm chat_*` 行里**没有角色**
    ⇒ 那两节仍然是全角色的（`report()` 会标出来）。
    """
    d: dict = {
        "lines": 0, "recall_new": [], "recall_old": [], "read": [],
        "look": {"hit": 0, "empty": 0, "bad_entity": 0, "bad_when": 0, "title": 0},
        "noticed": [], "noticed_drop": 0, "turn": [], "llm": [],
    }
    if not path.exists():
        return d
    with path.open(encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            d["lines"] += 1
            m = LINE.match(raw.rstrip("\n"))
            if not m:
                continue
            msg = m.group("msg")
            mine = (not char) or (char in msg)          # 这一行是不是我要的那个角色
            if (hit := RECALL_NEW.search(msg)):
                if mine:
                    d["recall_new"].append(hit.groupdict())
            elif (old := RECALL_OLD.search(msg)):
                if mine:
                    d["recall_old"].append(old.groupdict())
            elif (rd := READ_NEW.search(msg)):
                if mine:
                    d["read"].append(rd.groupdict())
            elif (lk := LOOK_HIT.search(msg)):
                d["look"]["hit"] += int(mine)
            elif (le := LOOK_EMPTY.search(msg)):
                d["look"]["empty"] += int(mine)
            elif LOOK_BAD_ENTITY.search(msg):
                d["look"]["bad_entity"] += int(mine)
            elif LOOK_BAD_WHEN.search(msg):
                d["look"]["bad_when"] += int(mine)
            elif LOOK_BY_TITLE.search(msg):
                d["look"]["title"] += int(mine)
            elif (nh := NOTICED_HIT.search(msg)):       # ⚠️ 行里没有角色 id ⇒ 不过滤
                d["noticed"].append(nh.groupdict())
            elif NOTICED_DROP.search(msg):
                d["noticed_drop"] += 1
            elif (tn := TURN.search(msg)):
                if mine:
                    d["turn"].append(tn.groupdict())
            elif (lm := LLM.search(msg)):               # ⚠️ 同上
                d["llm"].append(lm.groupdict())
    return d


def report(d: dict, path: Path, char: str) -> None:
    budget = recall_config.get("turn_budget")
    print(f"日志: {path}")
    print(f"      {d['lines']} 行" + (f" · 过滤 char={char}" if char else " · 全部角色"))
    print()
    print("── 格式识别 " + "─" * 46)
    print(f"mmt_recall   新格式 {len(d['recall_new'])} 行 / 旧格式 {len(d['recall_old'])} 行"
          + ("   ← 旧格式没有 per=/ms=（三段之前的档, 只统计总字数）"
             if d["recall_old"] and not d["recall_new"] else ""))
    print(f"recall_read  {len(d['read'])} 行"
          + ("   ← ⚠️ 没有 `known:` 桶 = 那次跑的还不是 2026-10-12 之后的代码"
             if d["read"] and not any("known:" in r["buckets"] for r in d["read"]) else ""))
    print()
    print(f"── P19 三段（预算 = [recall].turn_budget = {budget:g} 字符/段）" + "─" * 10)
    if not d["recall_new"]:
        print("（没有数据 —— 真机跑一次新版再看; 旧格式只能给总字数: "
              + (_stat([int(r["chars"]) for r in d["recall_old"]]) if d["recall_old"]
                 else "（也没有旧格式）") + "）")
    else:
        per: dict[str, list[int]] = {}
        empties: dict[str, int] = {}
        for r in d["recall_new"]:
            for label, (n, is_empty) in _parse_per(r["per"]).items():
                per.setdefault(label, []).append(n)
                empties[label] = empties.get(label, 0) + int(is_empty)
        for label in ("name", "when", "turn"):
            vals = per.get(label, [])
            if not vals:
                print(f"{label:<6} （这一段从来没摆过）")
                continue
            full = sum(1 for v in vals if v >= budget)
            print(f"{label:<6} {_stat(vals)}   撞满 {full}/{len(vals)}"
                  f"（{full / len(vals) * 100:.0f}%）"
                  f"   空手 {empties.get(label, 0)}/{len(vals)}")
        print(f"{'总字数':<6} {_stat([int(r['chars']) for r in d['recall_new']])}")
        print(f"{'耗时ms':<6} "
              + _stat([int(float(r['ms'])) for r in d["recall_new"]])
              + f"   明细 → {[r['ms'] for r in d['recall_new'][-5:]]}")
    print()
    print("── 她主动翻（`look`）与想起（`noticed`）" + "─" * 26)
    lk = d["look"]
    total_look = sum(lk.values())
    print(f"look   {total_look} 次"
          + (f"（命中 {lk['hit']} · 空手 {lk['empty']} · 名字认不出 {lk['bad_entity']}"
             f" · 时间认不出 {lk['bad_when']} · 标题查 {lk['title']}）" if total_look else
             "（一次都没翻）"))
    print(f"noticed {len(d['noticed'])} 笔命中 · {d['noticed_drop']} 笔丢掉"
          + (f" · 命中率 {len(d['noticed']) / (len(d['noticed']) + d['noticed_drop']) * 100:.0f}%"
             if (len(d["noticed"]) + d["noticed_drop"]) else "")
          + ("   ← ⚠️ 这一节不过滤角色（行里没有 id）" if char else ""))
    for r in d["noticed"][-3:]:
        same = "抄对了" if r["said"].strip() == r["title"].strip() else "抄得不一样"
        print(f"      {r['hit']} 《{r['title']}》 ← said={r['said']!r}（{same}）")
    print()
    print("── 轮次 / 前缀缓存 / brain 段" + "─" * 33)
    if d["turn"]:
        print(f"轮次 {len(d['turn'])} 轮 · 首行 {_stat([int(r['first']) for r in d['turn']])} ms"
              f" · 整轮 {_stat([int(r['ms']) for r in d['turn']])} ms"
              f" · 每轮 {statistics.fmean([int(r['rows']) for r in d['turn']]):.1f} 行")
    if d["llm"]:
        hit = sum(int(r["hit"]) for r in d["llm"] if int(r["hit"]) >= 0)
        miss = sum(int(r["miss"]) for r in d["llm"])
        rate = hit / (hit + miss) * 100 if (hit + miss) else 0
        print(f"缓存 {len(d['llm'])} 次调用 · hit {hit} / miss {miss} ⇒ 命中 {rate:.0f}%"
              "（`cache_hit=-1` = 该次没报 usage, 已排除）"
              + ("   ← ⚠️ 这一节不过滤角色（行里没有 id）" if char else ""))
    if d["read"]:
        last = d["read"][-1]
        print(f"brain 段 最后一行: total={last['total']} picked={last['picked']} "
              f"dropped={last['dropped']} buckets={last['buckets']}")
        print("      ⚠️ `dropped` 应当在 entity 全进 `known` 桶之后**归 0**;"
              " 不为 0 说明还有 kind 没进桶（如 `experience`）")


def _selftest() -> int:
    """`--selftest`: 拿一段**合成日志**过一遍解析器（一行一族的形态都覆盖到）。

    ⭐ 为什么值得有: 这个脚本全是正则, 而日志格式会变（`mmt_recall` 就刚加过
    `per=`/`ms=`）—— 格式一漂, 脚本会**静默少统计**（看起来像"真机没跑", 其实是没认出来）。
    改完解析器跑一条命令: `python experiments/recall_report.py --selftest`。
    """
    import tempfile
    lines = [
        "2026-10-12 10:00:00 core.mmt.engine INFO mmt_recall igusa_haruka/s1 "
        "modes=name+when(empty)+turn eps=2 name=1 when=0 chars=1000 "
        "per=name:400/when:0(empty)/turn:600 ms=4.2 titles=甲 / 乙",
        "2026-10-12 10:00:01 core.mmt.engine INFO mmt_recall igusa_haruka/s1 "
        "eps=2 chars=460 mode=semantic titles=丙",
        "2026-10-12 10:00:02 live2be.brain INFO recall_read surface=chara "
        "char=igusa_haruka total=30 picked=30 dropped=0 mode=off "
        "buckets=episode:21 belief:4 known:5",
        "2026-10-12 10:00:03 core.mmt.engine INFO mmt_look igusa_haruka/s1 "
        "entity='阿露' clue='苔藓' when='上周' form=exact cand=3",
        "2026-10-12 10:00:04 core.mmt.engine INFO mmt_look igusa_haruka/s1 "
        "entity='小玉' ⇒ 认不出",
        "2026-10-12 10:00:05 core.mmt.engine INFO mmt_noticed hit=m0007 "
        "title='瓦片缝里的苔藓' said='瓦片缝里的苔藓'",
        "2026-10-12 10:00:06 core.mmt.engine INFO mmt_noticed drop=no_such_title said='瞎编的'",
        "2026-10-12 10:00:07 core.mmt.engine INFO mmt_turn igusa_haruka/s1 "
        "steps=1 rows=5 delivered=4 first_ms=2000 ms=2500",
        "2026-10-12 10:00:08 llm.client INFO llm chat_full ms=2797 "
        "ttf=1 cache_hit=5888 cache_miss=1354",
        "2026-10-12 10:00:09 llm.client INFO llm chat ms=100 json=y cache_hit=-1 cache_miss=9",
    ]
    with tempfile.TemporaryDirectory() as td:      # ⚠️ 用临时目录, 不碰真机日志
        p = Path(td) / "selftest.log"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        d = collect(p)
    got = {
        "recall_new": len(d["recall_new"]), "recall_old": len(d["recall_old"]),
        "read": len(d["read"]), "look": dict(d["look"]),
        "noticed": len(d["noticed"]), "noticed_drop": d["noticed_drop"],
        "turn": len(d["turn"]), "llm": len(d["llm"]),
        "per": _parse_per(d["recall_new"][0]["per"]) if d["recall_new"] else {},
        "read_char": d["read"][0]["char"] if d["read"] else "",
        "look_char": d["look"]["hit"],
    }
    want = {
        "recall_new": 1, "recall_old": 1, "read": 1,
        "look": {"hit": 1, "empty": 0, "bad_entity": 1, "bad_when": 0, "title": 0},
        "noticed": 1, "noticed_drop": 1, "turn": 1, "llm": 2,
        "per": {"name": (400, False), "when": (0, True), "turn": (600, False)},
        "read_char": "igusa_haruka", "look_char": 1,
    }
    if got != want:
        print("selftest FAIL")
        for k in want:
            if got.get(k) != want[k]:
                print(f"  {k}: 期望 {want[k]!r} 实得 {got.get(k)!r}")
        return 1
    # ⭐ 只带角色的那一族必须过滤得住（`mmt_recall` 行里有 char）
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "selftest.log"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        only = collect(p, "amau_ako")
    if only["recall_new"] or only["turn"]:
        print(f"selftest FAIL: --char 没过滤住（{len(only['recall_new'])}/{len(only['turn'])}）")
        return 1
    print("selftest ok: 两代 mmt_recall / recall_read / look 四态 / noticed 命中与丢弃 / "
          "turn / llm 缓存 全部认得出, 且 --char 过滤得住")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="真机观察清单（只读）")
    ap.add_argument("--log", default=str(DIAG_LOG_PATH), help="日志路径")
    ap.add_argument("--char", default="", help="只看这个角色（子串匹配）")
    ap.add_argument("--selftest", action="store_true",
                    help="拿合成日志过一遍解析器（不读真机日志）")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    path = Path(args.log)
    report(collect(path, args.char), path, args.char)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
