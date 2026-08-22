# -*- coding: utf-8 -*-
"""羁绊剧情存档单测 — 原子写 + 逐场 append + 读档容错 + 列出。

BondStorySave : append/finish 逐场落盘, 构造即写骨架, 原子写无 tmp 残留
load_save     : 往返 round-trip; 坏文件/非 dict → {} 不 raise; scenes 只留 dict 项
list_saves    : 排序 + char_id 过滤

运行: python -m pytest tests/core/test_bond_story_save.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.bond_story import BondScene
from core.bond.bond_save import BondStorySave, DEFAULT_SAVE_DIR, load_save, list_saves


def _recorder(save_dir, char_id="igusa_haruka", **kw) -> BondStorySave:
    return BondStorySave(char_id, "伊草 遥香", "天台谈心", save_dir=save_dir, **kw)


def test_append_finish_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        rec = _recorder(d)
        rec.append(BondScene(paragraphs=["她看着你。"], choices=["陪她", "问她"], is_end=False),
                   picked="陪她", input_text="（旁白）……")
        rec.append(BondScene(paragraphs=["她笑了。"], is_end=True), picked=None, input_text="陪她")
        rec.finish(ended=True)

        data = load_save(rec.path)
        assert data["character_id"] == "igusa_haruka"
        assert data["character_name"] == "伊草 遥香"
        assert data["trigger_reason"] == "天台谈心"
        assert data["ended"] is True
        assert len(data["scenes"]) == 2
        s0, s1 = data["scenes"]
        assert s0["seq"] == 1 and s0["picked"] == "陪她"
        assert s0["paragraphs"] == ["她看着你。"] and s0["choices"] == ["陪她", "问她"]
        assert s0["is_end"] is False
        assert s1["seq"] == 2 and s1["is_end"] is True
        assert s1["input"] == "陪她"
    print("    append/finish: 逐场落盘 round-trip, seq/input/picked/is_end 齐全")


def test_construct_writes_skeleton():
    with tempfile.TemporaryDirectory() as d:
        rec = _recorder(d)
        assert rec.path.exists(), "构造即写骨架（崩溃也留痕）"
        data = json.loads(rec.path.read_text(encoding="utf-8"))
        assert data["ended"] is False and data["scenes"] == []
        assert data["character_name"] == "伊草 遥香", "骨架应写真实角色名（勿写死空串）"
    print("    构造即写骨架: 空 scenes + 真实 character_name")


def test_atomic_write_no_tmp_leftovers():
    with tempfile.TemporaryDirectory() as d:
        rec = _recorder(d)
        for i in range(5):
            rec.append(BondScene(paragraphs=[f"场景{i}。"], is_end=(i == 4)), None, f"输入{i}")
        leftovers = [p for p in Path(d).iterdir() if p.name.startswith("._savetmp_")]
        assert not leftovers, f"原子写不应残留 tmp: {leftovers}"
        assert len([p for p in Path(d).iterdir()]) == 1, "只应有存档本体"
    print("    原子写: 多次 append 无 tmp 残留")


def test_load_save_corrupt_returns_empty():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bond_story_broken.json"
        bad.write_text("{ 这不是合法 JSON", encoding="utf-8")
        assert load_save(bad) == {}, "坏 JSON 应降级为 {} 不 raise"

        not_dict = Path(d) / "bond_story_list.json"
        not_dict.write_text(json.dumps([1, 2]), encoding="utf-8")
        assert load_save(not_dict) == {}, "非 dict JSON 应降级为 {}"

        missing = Path(d) / "bond_story_missing.json"
        assert load_save(missing) == {}, "缺失文件应降级为 {}"
    print("    load_save: 坏文件/非 dict/缺失 → {} 不 raise（宁缺勿错）")


def test_load_save_filters_non_dict_scenes():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "bond_story_mixed.json"
        path.write_text(json.dumps({
            "character_id": "igusa_haruka",
            "scenes": [{"seq": 1}, "bad", None, 42],
        }), encoding="utf-8")
        data = load_save(path)
        assert len(data["scenes"]) == 1 and data["scenes"][0]["seq"] == 1, data["scenes"]
    print("    load_save: scenes 只留 dict 项（坏项丢弃）")


def test_list_saves_order_and_filter():
    import time
    with tempfile.TemporaryDirectory() as d:
        r1 = _recorder(d, "igusa_haruka")
        time.sleep(1.1)                      # 文件名秒级精度, 错开避免同名覆盖
        r2 = _recorder(d, "rikuhachima_aru")
        r3 = _recorder(d, "igusa_haruka")
        all_saves = list_saves(save_dir=d)
        assert all_saves == sorted(all_saves), "应按文件名排序"
        assert len(all_saves) == 3
        haruka = list_saves("igusa_haruka", save_dir=d)
        assert len(haruka) == 2 and all(r.name.startswith("bond_story_igusa_haruka_") for r in haruka)
        assert r1.path in haruka and r3.path in haruka and r2.path not in haruka
    print("    list_saves: 排序 + char_id 过滤")


def test_default_save_dir_constant():
    assert DEFAULT_SAVE_DIR == Path("data/saves"), DEFAULT_SAVE_DIR
    print("    默认存档目录: data/saves（.gitignore 已忽略）")
