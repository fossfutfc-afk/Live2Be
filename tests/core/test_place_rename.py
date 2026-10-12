"""地点改名台账 + 改名工具（PL6, 2026-09-19）。

用户裁决: key **不可改**（回放按 key 查表）, 但改名现实里会发生 ⇒
**只改表 + 留台账, 事件流一个字不动**（append-only）。本文件钉四件事:

  ① 台账: append/读/链回溯（a→b→c）/ 环被挡 / 缺失坏了都不抛
  ② 工具: 扫引用面（事件流 + 暂存 + 审校表）/ 干跑不落盘 / `--apply` 才写
  ③ 改表: **逐字节可复原**（非导出格式 → 拒绝, 免得顺手重排整个文件）+ 撞车保护
  ④ 消费方: `_place_bg()` 查不到旧名 → 状态 `renamed` + 人话（黑屏 alert 用它）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.media import place_rename as tool
from core.media import place_renames as pr


@pytest.fixture(autouse=True)
def _clear_cache():
    pr.reset_cache()
    yield
    pr.reset_cache()


def _world(tmp_path: Path, name: str = "w1", char: str = "c1",
           events: list[dict] | None = None, staging: list[dict] | None = None) -> Path:
    """造一条世界线（`data/worlds/{w}/characters/{c}/soul/…`）。"""
    root = tmp_path / "worlds"
    soul = root / name / "characters" / char / "soul"
    soul.mkdir(parents=True, exist_ok=True)
    for fname, rows in (("events.jsonl", events), ("staging/events.jsonl", staging)):
        if rows is None:
            continue
        f = soul / fname
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                     encoding="utf-8")
    return root


def _bond_event(place: str = "", para_places: list[str] | None = None,
                hint: str = "放学后的教室") -> dict:
    paras = [{"text": "……", "place": p} for p in (para_places or [])]
    return {"type": "bond", "subtype": "story_scene",
            "payload": {"place": place, "place_hint": hint, "paragraphs": paras}}


# ---------------------------------------------------------------------------
# ① 台账
# ---------------------------------------------------------------------------

def test_ledger_append_and_chain(tmp_path):
    """append → load → `resolve` 沿链回溯到最新名; `explain` 说人话。"""
    root = _world(tmp_path)
    pr.append("old_key", "mid_key", world="w1", reason="第一次改名",
              events=3, worlds_dir=root)
    pr.append("mid_key", "new_key", world="w1", reason="第二次改名",
              events=1, worlds_dir=root)
    assert len(pr.load("w1", worlds_dir=root)) == 2
    assert pr.resolve("old_key", worlds_dir=root) == "new_key", "链没回溯到最新名"
    assert pr.resolve("mid_key", worlds_dir=root) == "new_key"
    assert pr.resolve("untouched", worlds_dir=root) is None
    why = pr.explain("old_key", worlds_dir=root)
    assert "old_key" in why and "new_key" in why and "第一次改名" in why, why
    assert pr.explain("untouched", worlds_dir=root) == ""
    print(f"    台账: old→mid→new 链回溯 OK; explain={why[:40]}…")


def test_ledger_rejects_cycle_and_noop(tmp_path):
    """同名 / 空名 / 成环 → 拒绝（台账是 append-only, 写进去就收不回）。"""
    root = _world(tmp_path)
    pr.append("a", "b", world="w1", worlds_dir=root)
    with pytest.raises(ValueError):
        pr.append("b", "a", world="w1", worlds_dir=root)      # 成环
    with pytest.raises(ValueError):
        pr.append("x", "x", world="w1", worlds_dir=root)      # 没变化
    with pytest.raises(ValueError):
        pr.append("", "y", world="w1", worlds_dir=root)       # 空名
    assert len(pr.load("w1", worlds_dir=root)) == 1, "被拒的登记不该落盘"
    print("    台账: 环/同名/空名 → ValueError, 未落盘")


def test_ledger_missing_or_broken_is_silent(tmp_path):
    """缺文件 / 坏行 / 空世界 → `[]`（宁缺勿错; 台账缺失不该影响取图）。"""
    root = _world(tmp_path)
    assert pr.load("nope", worlds_dir=root) == []
    assert pr.resolve("x", worlds_dir=root) is None
    p = pr.ledger_path("w1", worlds_dir=root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{不是 json}\n\n" + json.dumps({"from": "a", "to": "b"}) + "\n",
                 encoding="utf-8")
    assert [r["to"] for r in pr.load("w1", worlds_dir=root)] == ["b"], "坏行该跳过"
    assert pr.resolve("a", worlds_dir=root) == "b"
    print("    台账: 缺失/坏行 → 跳过, 不抛")


# ---------------------------------------------------------------------------
# ② 扫引用面（只读）
# ---------------------------------------------------------------------------

def test_scan_finds_all_reference_surfaces(tmp_path):
    """事件流 `payload.place` + `paragraphs[*].place` + 暂存 + 审校表, 一处不漏。"""
    root = _world(
        tmp_path,
        events=[_bond_event(place="old_key", para_places=["old_key", "other"]),
                _bond_event(place="other")],
        staging=[_bond_event(para_places=["old_key"])])
    review = tmp_path / "_place_review.json"
    review.write_text(json.dumps({
        "SDIR_Outer|DIR_X|old_key": {"place": "old_key", "active": True},
        "SDIR_Outer|DIR_Y|other": {"place": "other", "active": True},
    }, ensure_ascii=False), encoding="utf-8")
    rep = tool.scan("old_key", worlds_dir=root, review_path=review)
    wheres = sorted(h["where"] for h in rep["events"])
    assert wheres == ["paragraphs[0].place", "payload.place"], wheres
    assert len(rep["staging"]) == 1, rep["staging"]
    assert rep["review"] == ["SDIR_Outer|DIR_X|old_key"], rep["review"]
    # `place_hint`（writer 原文）**不算引用** —— 它本来就不该被改
    assert all("place_hint" not in h["where"] for h in rep["events"])
    print(f"    扫: 事件 {len(rep['events'])} + 暂存 {len(rep['staging'])} "
          f"+ 审校 {len(rep['review'])}; place_hint 不计")


# ---------------------------------------------------------------------------
# ③ 改表（逐字节可复原 / 撞车保护）+ 干跑
# ---------------------------------------------------------------------------

def _export_table(path: Path, obj: dict) -> None:
    """按 tempo 导出格式落一张表（indent=1, 无尾换行）。"""
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def test_table_rename_is_byte_surgical(tmp_path):
    """改表只动两处（外层键 + 行内 place）, 其余逐字节不变。"""
    p = tmp_path / "place_entities.json"
    _export_table(p, {
        "old_key": {"place": "old_key", "keywords": ["别名"], "files": {"day": ["a.jpg"]}},
        "keep": {"place": "keep", "keywords": [], "files": {}},
    })
    before = p.read_text(encoding="utf-8")
    after = tool.table_text_rename("old_key", "new_key", path=p)
    assert '"new_key": {' in after and '"new_key"' in after
    assert before.replace("old_key", "new_key") == after, "改动不止那两处"
    obj = json.loads(after)
    assert obj["new_key"]["place"] == "new_key" and "old_key" not in obj
    assert obj["keep"] == {"place": "keep", "keywords": [], "files": {}}
    print("    改表: 外层键 + 行内 place 两处, 其余逐字节相同")


def test_table_rename_refuses_handmade_or_collision(tmp_path):
    """非导出格式（有人手搓过）→ 拒绝; 目标键已存在 → 拒绝。"""
    p = tmp_path / "place_entities.json"
    p.write_text(json.dumps({"old_key": {"place": "old_key"}}, indent=2,
                            ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="不是 tempo 的导出格式"):
        tool.table_text_rename("old_key", "new_key", path=p)
    _export_table(p, {"old_key": {"place": "old_key"}, "new_key": {"place": "new_key"}})
    with pytest.raises(ValueError, match="撞车"):
        tool.table_text_rename("old_key", "new_key", path=p)
    with pytest.raises(ValueError, match="没有"):
        tool.table_text_rename("nope", "new_key", path=p)
    print("    改表: 非导出格式/撞车/源不存在 → 全部拒绝")


def test_main_dry_run_then_apply(tmp_path, capsys):
    """默认**干跑**（不落盘）; `--apply` 才改表 + 写台账。"""
    root = _world(tmp_path, events=[_bond_event(place="old_key")])
    p = tmp_path / "place_entities.json"
    _export_table(p, {"old_key": {"place": "old_key"}})
    argv = ["--from", "old_key", "--to", "new_key", "--reason", "统一命名",
            "--table", str(p), "--worlds-dir", str(root)]
    assert tool.main(argv) == 0
    out = capsys.readouterr().out
    assert "干跑" in out and "事件流命中: 1 处" in out, out
    assert json.loads(p.read_text(encoding="utf-8")).get("old_key"), "干跑不该改表"
    assert pr.load("w1", worlds_dir=root) == [], "干跑不该写台账"

    assert tool.main(argv + ["--apply"]) == 0
    obj = json.loads(p.read_text(encoding="utf-8"))
    assert "new_key" in obj and obj["new_key"]["place"] == "new_key"
    rows = pr.load("w1", worlds_dir=root)
    assert len(rows) == 1 and rows[0]["from"] == "old_key" and rows[0]["to"] == "new_key"
    assert rows[0]["reason"] == "统一命名" and rows[0]["events"] == 1
    print(f"    工具: 干跑不变 → --apply 改表 + 台账 {rows[0]['events']} 条引用")


# ---------------------------------------------------------------------------
# ④ 消费方: 素材未找到 → "已改名为 X"
# ---------------------------------------------------------------------------

def test_place_bg_explains_renamed_key(tmp_path):
    """黑屏不再是笼统的"素材未找到", 而是"key 'X' 已改名为 'Y'"。"""
    from webgui.routers.bond import _place_bg, _resolve_scene
    root = _world(tmp_path)
    pr.append("old_place_key", "new_place_key", world="w1",
              reason="作者改名", worlds_dir=root)

    import core.paths as paths_mod
    old_worlds = paths_mod.WORLDS_DIR
    try:
        paths_mod.WORLDS_DIR = root
        pr.reset_cache()
        url, st = _place_bg("old_place_key")
        assert (url, st) == (None, "renamed"), (url, st)
        scene = {"background": "neutral", "place": "old_place_key", "is_end": False,
                 "paragraphs": [{"text": "她推开门。"}]}
        out = _resolve_scene(scene, "igusa_haruka")
        info = out["missing_asset"]
        assert info["key"] == "old_place_key"
        assert info["renamed_to"] == "new_place_key", info
        assert "已改名" in info["message"] and "new_place_key" in info["message"], info
        assert "BG_Black" in (out.get("background_url") or ""), "旧名照样黑屏"
        # 锚点路径同样带解释
        scene2 = {"background": None, "is_end": False,
                  "paragraphs": [{"text": "……", "place": "old_place_key"}]}
        out2 = _resolve_scene(scene2, "igusa_haruka")
        assert out2["paragraphs"][0]["missing_asset"]["renamed_to"] == "new_place_key"
    finally:
        paths_mod.WORLDS_DIR = old_worlds
        pr.reset_cache()
    print("    消费方: 旧名 → 状态 renamed + 黑屏 + '已改名为 new_place_key'")


def test_duplicate_key_in_table_is_reported(tmp_path):
    """★ 手编 JSON 写重复键, `json.loads` 静默保留最后一个 → 表要自己看见它。"""
    from core.media.place_table import load_table, reset_cache
    p = tmp_path / "dup.json"
    p.write_text('{"a": {"place": "a", "note": "第一遍"},'
                 ' "a": {"place": "a", "note": "第二遍"}}', encoding="utf-8")
    reset_cache()
    t = load_table(p)
    assert "重复键" in t.error, t.error
    assert t.get("a").note == "第二遍", "json 的既有语义: 后者胜"
    reset_cache()
    print(f"    重复键守卫: error={t.error}")


if __name__ == "__main__":
    import tempfile
    for fn in (test_ledger_append_and_chain, test_ledger_rejects_cycle_and_noop,
               test_ledger_missing_or_broken_is_silent,
               test_scan_finds_all_reference_surfaces,
               test_table_rename_is_byte_surgical,
               test_table_rename_refuses_handmade_or_collision,
               test_place_bg_explains_renamed_key,
               test_duplicate_key_in_table_is_reported):
        with tempfile.TemporaryDirectory() as td:
            fn(Path(td))
            pr.reset_cache()
    print("all place_rename tests passed")
