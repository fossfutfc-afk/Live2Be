# -*- coding: utf-8 -*-
"""真机跑批: 官方羁绊剧情 → 事件流 → 真 digest → 三标量分布。

为什么要它: 真机自有数据只有 8 条 episode, 而 `span`/`int` 是否冗余、
`emo_valence` 是否恒正, **都需要足够的「完整故事弧」样本**才能判断。
官方羁绊剧情是真人写的完整弧（含明确负面/崩溃的段落）, 正好补这个缺口。

用法:
    python .testtmp/ba_digest_run.py [GroupId ...]

不传参数 = 跑默认清单（haruka 五档 + mutsuki 五档 + aru 四档, 按序）。
真 API 调用; 世界线建在 .testtmp/ba_world（不动真机数据）。
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, ".testtmp")

from ba_to_events import build_events                             # noqa: E402
from core.affection import Affection, load_affection_from_events  # noqa: E402
from core.brain.wiki_v2.digest import digest_segment              # noqa: E402
from core.brain.wiki_v2.store import WikiStoreV2                  # noqa: E402
from core.media import assets_root, load_emotion_lexicon          # noqa: E402
from core.parsing.dynamic_character_parser import (               # noqa: E402
    CharacterLoader,
    yaml_to_prompt,
)
from core.session.events import parse_events                      # noqa: E402
from core.session.store import SessionStore                       # noqa: E402
from llm.client import LLMClient                                  # noqa: E402

# GroupId → Live2Be 角色目录名
PLAN = {
    "1600002": "igusa_haruka", "1600003": "igusa_haruka",
    "1600005": "igusa_haruka", "1600006": "igusa_haruka",
    "1600008": "igusa_haruka",
    "1300002": "asagi_mutsuki", "1300003": "asagi_mutsuki",
    "1300005": "asagi_mutsuki", "1300006": "asagi_mutsuki",
    "1300008": "asagi_mutsuki",
    "1000002": "rikuhachima_aru", "1000003": "rikuhachima_aru",
    "1000005": "rikuhachima_aru", "1000006": "rikuhachima_aru",
}
OUT = Path(".testtmp/ba_world")
SCEN = Path(".testtmp/ba_scenarios")


def setup_world(tag: str) -> SessionStore:
    """每个故事一个独立世界根 —— 否则同角色的不同故事会共享 wiki 互相污染。"""
    root = OUT / tag / "worlds" / "world1"
    (root / "characters").mkdir(parents=True, exist_ok=True)
    (root / "world.json").write_text(
        json.dumps({"id": "world1", "name": "ba-probe"}, ensure_ascii=False),
        encoding="utf-8")
    return SessionStore(data_root=str(OUT / tag))


def main() -> None:
    gids = sys.argv[1:] or list(PLAN)
    if not gids:
        return
    llm = LLMClient()
    loader = CharacterLoader(Path("config/characters"))

    results: list[dict] = []
    for gid in gids:
        ch = PLAN.get(gid)
        if ch is None:
            print(f"!! 未登记 {gid}")
            continue
        src = SCEN / f"ba_{gid}.json"
        if not src.is_file():
            print(f"!! 缺剧本 {src}")
            continue

        store = setup_world(gid)          # ★ 每故事一个独立世界
        char = loader.load(ch)
        anchor = yaml_to_prompt({**char.personality, **char.knowledge},
                                "角色人设（锚点）")
        lex = load_emotion_lexicon(assets_root() / "illustration" / ch / "default")

        recs = json.loads(src.read_text(encoding="utf-8"))
        evs_raw = build_events(recs, char_id=ch)
        # ★ 必须带 ts（`Event.from_dict` 丢弃 ts 空的事件——缺了会整段静默消失）
        _ts = "2026-09-12T20:00:00"
        evs = parse_events([
            {"type": e["type"], "subtype": e["subtype"], "payload": e["payload"],
             "seq": e["seq"], "ts": _ts} for e in evs_raw])
        wstore = WikiStoreV2(store.data_root, world_id="world1", char_id=ch)
        bond_boards = len(evs_raw)
        n_records = sum(len(e["payload"]["paragraphs"]) for e in evs_raw)
        res = digest_segment(wstore, llm, evs, character_prompt=anchor,
                             emotion_lexicon=lex)
        eps = [wstore.get(i) for i in res.created]
        eps = [e for e in eps if e is not None]
        print(f"== {gid} {ch}: 板 {bond_boards} 记录 {n_records} → "
              f"episode {len(eps)} ok={res.ok} aff={res.affection_delta} "
              f"errs={res.errors}")
        for e in eps:
            f = lambda v: "  -  " if v is None else f"{v:.2f}"      # noqa: E731
            print(f"   {e.id} SIG={e.significance:.2f} "
                  f"span={f(e.emo_span)} int={f(e.emo_int)} "
                  f"val={f(e.emo_valence)}  {e.title}")
            results.append({
                "gid": gid, "ch": ch, "id": e.id, "sig": e.significance,
                "span": e.emo_span, "int": e.emo_int,
                "val": e.emo_valence, "title": e.title,
                "narration": e.narration,
            })

    out = Path(".testtmp/ba_digest_results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n汇总 {len(results)} 条 episode → {out}")

    # 分布
    def stat(vals, name):
        vs = [v for v in vals if v is not None]
        if len(vs) < 2:
            print(f"  {name}: 样本不足 ({len(vs)})")
            return
        print(f"  {name}: n={len(vs)} min={min(vs):+.2f} max={max(vs):+.2f} "
              f"mean={sum(vs) / len(vs):+.2f} sd={(sum((x - sum(vs) / len(vs)) ** 2 for x in vs) / len(vs)) ** 0.5:.3f}")

    print("\n=== 分布 ===")
    stat([r["sig"] for r in results], "SIG ")
    stat([r["span"] for r in results], "span")
    stat([r["int"] for r in results], "int ")
    stat([r["val"] for r in results], "val ")

    # span vs int 是否冗余（|diff| 分布）
    d = [abs(r["span"] - r["int"]) for r in results
         if r["span"] is not None and r["int"] is not None]
    if d:
        print(f"  |span-int|: mean={sum(d) / len(d):.3f} max={max(d):.3f} "
              f"≤0.10 的占 {sum(1 for x in d if x <= 0.10)}/{len(d)}")

    # val 有正有负吗
    va = [r["val"] for r in results if r["val"] is not None]
    if va:
        print(f"  val 符号: 正={sum(1 for x in va if x > 0)} "
              f"负={sum(1 for x in va if x < 0)} 零={sum(1 for x in va if x == 0)}")


if __name__ == "__main__":
    main()
