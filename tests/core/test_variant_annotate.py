"""第二遍「选图」——时刻/天气/作者差分（2026-09-19）。

## 为什么有这一步

第一遍只回答"哪个地点"。但同一地点常有好几张图:
  · **时刻/天气**: `_Night` 153 张 / `_Sunset` 35 张 —— 此前**谁都选不了**
    （`catalog.background(sid, variant=None)` 永远第一条）
  · **作者差分**: 45 个键各有 ≥2 张**无变体**图（`BG_X.jpg` / `BG_X2.jpg`），
    区别写在 `note` 里（*"请使用差分2"* / *"2则有圣诞树"*）——此前**没有任何消费方**

用户 2026-09-19: *"好消息是我的部分 note 里面本身就会教 LLM 某些特殊常用的夜景以及
差分的区别"* ⇒ note 就是这个资源的说明书，所以这一步把 **note + 候选图原样**摆给
标注 LLM，让它挑**文件**。

## 为什么不走关键词表（用户当场否掉）

「从早到晚，我都想一直陪在老师身边」/「这些灯光，感觉像在白天一样呢~」/
「我一定要将老师的善良公布在光天化日之下！」/「私は夜の散歩が一番好きです」——
范围成语 / 比喻+否定 / 成语 / 外语意愿句: 关键词表会把 3 句判反、1 句判错，
而且**漏判是静默的**。⇒ 语义判定归标注层（这四句也写进了 prompt 当反例）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from core.bond.variant_annotate import pick_image
from core.media.place_table import MOMENT_VARIANTS, load_table, moment_label, moment_token
from llm import task_labels as T
from llm.prompts import load_prompt
from tests import stub_tasks

ROOT = Path(__file__).resolve().parent.parent.parent


class PickLLM:
    """记录调用并按序作答的桩（`chat` 文本模式）。"""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[str] = []

    def chat(self, messages, **kw):
        self.calls.append(messages[0]["content"])
        return self.replies.pop(0) if self.replies else "{}"

    def chat_full(self, messages, **kw):        # 未用; 保持接口完整
        raise AssertionError("选图应走 chat（text 模式）")


def _entry(table, key):
    e = table.get(key)
    assert e is not None, f"表里没有 {key}"
    return e


# ---------------------------------------------------------------------------
# ① 表的候选派生
# ---------------------------------------------------------------------------

def test_candidates_derived_from_filenames():
    """候选 = 这个键**实际有的每一张图**（含作者差分）, 时刻标签从文件名派生。"""
    t = load_table()
    assert t.ok, t.error
    e = _entry(t, "school_rooftop")
    rels = [r for r, _ in e.image_candidates()]
    names = [Path(r).name for r in rels]
    assert "BG_SchoolRooftop.jpg" in names and "BG_SchoolRooftop2.jpg" in names, names
    assert any("Night" in n for n in names), names
    assert len(rels) == len(set(rels)), "候选该去重"
    # 标签: 时刻中文名 + 差分号（作者在 note 里就叫"差分2"）
    labels = dict(e.image_candidates())
    assert labels[[r for r in rels if r.endswith("BG_SchoolRooftop2.jpg")][0]] == "默认·差分2"
    assert "夜" in "".join(labels.values())
    # 单图键: 候选只有 1 张 ⇒ 第二遍根本不该发（0 调用）
    only = [x for x in t.all() if len(x.image_candidates()) == 1]
    assert only, "应该有单图键（22 个）"
    print(f"    candidates: school_rooftop {len(rels)} 张 {sorted(set(labels.values()))}; "
          f"单图键 {len(only)} 个")


def test_moment_tokens_and_labels_roundtrip():
    """中文名 ↔ token 互通（prompt 里两种都写, 模型抄哪个都认）。"""
    assert moment_token("夜") == "night" and moment_token("night") == "night"
    assert moment_token("默认") == "" and moment_token("") == ""
    assert moment_token("不存在") == ""
    assert moment_label("night") == "夜" and moment_label("") == "默认"
    assert set(MOMENT_VARIANTS) >= {"night", "sunset", "dawn"}, MOMENT_VARIANTS
    # 剧情状态类（erode/ruin/off/party…）**故意不在**可选时刻里（没有信号源）
    for bad in ("erode", "ruin", "off", "party", "fake"):
        assert bad not in MOMENT_VARIANTS
    print("    moment: 中文名↔token 互通; 状态类不进候选")


def test_asset_for_falls_back_to_base():
    """要的时刻没有那张图 → 回落默认图（宁缺勿错, 不给黑屏）。"""
    t = load_table()
    e = _entry(t, "school_rooftop")
    assert "Night" in Path(e.asset_for("night")).name
    assert "Sunset" in Path(e.asset_for("sunset")).name
    assert Path(e.asset_for("rain")).name == Path(e.asset()).name, "没有雨天图 → 默认图"
    assert e.asset_for("night").startswith("SDIR_"), "给的是表内相对路径"
    print(f"    asset_for: night→{Path(e.asset_for('night')).name}; "
          f"rain（无）→{Path(e.asset_for('rain')).name}")


# ---------------------------------------------------------------------------
# ② 选图调用（pick_image）
# ---------------------------------------------------------------------------

def test_pick_image_returns_candidate_and_zero_call_for_single_image():
    """单图键 → **不调用**; 多图键 → 调用并只接受候选内的文件名。"""
    t = load_table()
    single = next(x for x in t.all() if len(x.image_candidates()) == 1)
    llm = PickLLM('{"image": "x"}')
    assert pick_image(llm, "某个地方", single) == ""
    assert llm.calls == [], "只有一张图就不该调用"

    e = _entry(t, "school_rooftop")
    want = Path(e.asset_for("night")).name
    llm2 = PickLLM(f'{{"image": "{want}"}}')
    got = pick_image(llm2, "天已经黑了", e)
    assert got and got.endswith(want), got
    assert len(llm2.calls) == 1
    sys_text = llm2.calls[0]
    assert e.note in sys_text, "作者说明必须进 prompt（它就是资源说明书）"
    assert "天已经黑了" in sys_text
    assert "BG_SchoolRooftop2.jpg" in sys_text, "候选文件名要在 prompt 里"
    print(f"    选图: 单图 0 调用; 多图 → {want}")


def test_pick_image_rejects_non_candidate_and_keeps_on_empty():
    """候选外的文件名 / 显式空 / 解析失败 → `""`（保持当前画面, 绝不乱换）。"""
    t = load_table()
    e = _entry(t, "classroom")
    assert pick_image(PickLLM('{"image": "BG_NotHere.jpg"}'), "夜里", e) == ""
    assert pick_image(PickLLM('{"image": ""}'), "夜里", e) == ""
    assert pick_image(PickLLM("不是 JSON"), "夜里", e) == ""       # 重试后仍失败
    assert pick_image(PickLLM(), "", e) == ""                      # 无文本 → 直接空
    print("    选图: 候选外/空/坏 JSON/无文本 → 全部保持")


def test_prompt_carries_the_four_counter_examples():
    """★ 用户给的四句反例必须在 prompt 里（它们是这条判据的真源）。

    红了怎么修: 别改测试——把反例补回 `llm/prompts/place_variant.md`。
    """
    text = load_prompt("place_variant")
    for line in ("从早到晚，我都想一直陪在老师身边",
                 "这些灯光，感觉像在白天一样呢~",
                 "我一定要将老师的善良公布在光天化日之下！",
                 "私は夜の散歩が一番好きです"):
        assert line in text, f"反例丢了: {line}"
    assert "不是里面有没有" in text, "得写明判据是'这句话在说什么', 不是找词"
    for ph in ("{{place}}", "{{candidates}}", "{{note}}", "{{text}}"):
        assert ph in text, f"占位符缺了: {ph}（槽写法 2026-10-12 起是 `{{}}`）"
    print("    prompt: 四句反例 + 占位符齐全")


# ---------------------------------------------------------------------------
# ③ 引擎接线（payload 带 place_asset; 不进 LLM 上下文）
# ---------------------------------------------------------------------------

def test_engine_records_place_asset_in_payload():
    """switch → 键（层1）→ 选图 → `scene.place_asset` 进 payload; 回放读得回来。"""
    from core.bond.bond_story import BondStoryEngine
    from tests.vn_fixtures import scene as _scene

    board = _scene(switch_to="格黑娜学院·旧校舍天台", lines=["她抬头看天。"])
    want_night = "BG_SchoolRooftop_Night.jpg"

    class LLM:
        def __init__(self):
            self.pick_calls = 0

        def chat_full(self, messages, **kw):
            return board

        def chat(self, messages, **kw):
            task = kw.get("task")
            if task == T.PLACE_VARIANT:
                self.pick_calls += 1
                return {"image": want_night}
            if task == T.PLACE:
                return []
            if task == T.PLACE_BOARD:
                return {"place": "school_rooftop"}      # 层2（该句歧义）
            reply = stub_tasks.annotation_reply(task, messages)
            if reply is not None:                       # emotion → nomal
                return reply
            raise stub_tasks.unknown_task(task)

    llm = LLM()
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session("igusa_haruka")
    engine._lexicon_keys = []
    scene = engine.send_vn_scene("（开场）", annotate=True)
    assert scene.place == "school_rooftop", scene.place
    assert scene.place_asset and scene.place_asset.endswith(want_night), scene.place_asset
    assert llm.pick_calls == 1
    d = scene.to_dict()
    assert d["place_asset"].endswith(want_night)
    # 回放: payload → BondScene 原样读回
    from core.bond.bond_story import BondScene
    back = BondScene.from_dict(d)
    assert back.place_asset == scene.place_asset
    # 视觉键不进 LLM 上下文（与 place/emotion 同一条纪律）
    from core.session.renderer import render_bond_scene_text
    assert want_night not in render_bond_scene_text(d)
    print(f"    引擎: place_asset={Path(scene.place_asset).name}; 回放读回; 不进上下文")


def test_anchor_switch_also_picks_image():
    """★ 句级锚点（板内后续换场）**也要选图**——落在**段落**上, 不是板级。

    缺口补于 2026-09-19: 此前板首 switch 会选图、板内锚点只会定键 ⇒ 板内换场
    永远退回默认图（真机上板 2 出现过 `[place][SCAN] cue=进了`）。
    """
    from core.bond.bond_story import BondScene, BondStoryEngine
    from tests.vn_fixtures import scene as _scene

    board = _scene(switch_to="教室", lines=["她放下书包。", "她拉着我走出教室，来到天台。"])
    want = "BG_SchoolRooftop_Night.jpg"

    class LLM:
        def __init__(self):
            self.picks: list[str] = []

        def chat_full(self, messages, **kw):
            return board

        def chat(self, messages, **kw):
            task = kw.get("task")
            head = messages[0]["content"]                    # 候选清单在 system 里
            if task == T.PLACE_VARIANT:
                self.picks.append(head)
                # 板首（教室）给默认图, 锚点（天台）给夜景
                return {"image": want if "BG_SchoolRooftop" in head else ""}
            if task == T.PLACE:                              # ② 句级锚点
                return [{"sentence": 2, "place": "school_rooftop"}]
            reply = stub_tasks.annotation_reply(task, messages)
            if reply is not None:                            # 其余标注 → 标准应答
                return reply
            raise stub_tasks.unknown_task(task)

    llm = LLM()
    engine = BondStoryEngine(ROOT / "config" / "characters", llm)
    engine.start_session("igusa_haruka")
    engine._lexicon_keys = []
    scene = engine.send_vn_scene("（开场）", annotate=True)
    assert scene.place == "classroom", scene.place
    p2 = scene.paragraphs[1]
    assert p2.get("place") == "school_rooftop", p2
    assert p2.get("place_asset", "").endswith(want), p2          # ★ 段落级选的图
    assert p2["place_asset"] in {r for r, _ in
                                 engine._place_table.get("school_rooftop").image_candidates()}
    assert len(llm.picks) == 2, "板首 + 锚点各一次选图"
    # 回放读回（payload 里有 place_asset）
    back = BondScene.from_dict(scene.to_dict())
    assert back.paragraphs[1].get("place_asset", "").endswith(want), back.paragraphs[1]
    # 视觉键不进 LLM 上下文
    from core.session.renderer import render_bond_scene_text
    assert want not in render_bond_scene_text(scene.to_dict())
    print(f"    锚点选图: 段落 place=school_rooftop, place_asset={want}（2 次选图）")


def test_webgui_uses_paragraph_asset():
    """前端: 锚点句用自己的 `place_asset` 取图（板级那张不串到段落上）。"""
    from webgui.routers.bond import _resolve_scene
    scene = {
        "background": None, "is_end": False, "place": "classroom",
        "place_asset": "SDIR_Inner/DIR_Class/BG_ClassRoom.jpg",
        "paragraphs": [
            {"text": "她推开门。", "place": "school_rooftop",
             "place_asset": "SDIR_Outer/DIR_SchoolRoodtop/BG_SchoolRooftop_Night.jpg"},
            {"text": "夜里的话。", "place": "school_rooftop"},      # 无 asset → 默认图
        ],
    }
    out = _resolve_scene(scene, "igusa_haruka")
    assert out["paragraphs"][0]["place_bg"].endswith("BG_SchoolRooftop_Night.jpg"), \
        out["paragraphs"][0]
    assert "SchoolRooftop" in out["paragraphs"][1]["place_bg"], out["paragraphs"][1]
    print(f"    前端: 锚点用自己的 place_asset（{Path(out['paragraphs'][0]['place_bg']).name}）")


def test_webgui_prefers_table_path_and_validates_asset():
    """前端取图: 表的路径优先（catalog 会漏 6 张）, 非法 asset 回落默认图。"""
    from webgui.routers.bond import _place_bg
    url, st = _place_bg("school_rooftop", "SDIR_Outer/DIR_SchoolRoodtop/BG_SchoolRooftop_Night.jpg")
    assert st == "ok" and url.endswith("BG_SchoolRooftop_Night.jpg"), (url, st)
    # 不属于这个键的文件（哪怕真的存在）→ 回落默认图, 不串键
    url2, st2 = _place_bg("school_rooftop", "SDIR_Inner/DIR_Class/BG_ClassRoom.jpg")
    assert st2 == "ok" and "SchoolRooftop" in url2, (url2, st2)
    # 路径穿越 → 拒绝
    assert _place_bg("school_rooftop", "../../../etc/passwd")[1] == "ok"
    print(f"    取图: night={Path(url).name}; 串键/穿越 → 默认图")


if __name__ == "__main__":
    test_candidates_derived_from_filenames()
    test_moment_tokens_and_labels_roundtrip()
    test_asset_for_falls_back_to_base()
    test_pick_image_returns_candidate_and_zero_call_for_single_image()
    test_pick_image_rejects_non_candidate_and_keeps_on_empty()
    test_prompt_carries_the_four_counter_examples()
    test_engine_records_place_asset_in_payload()
    test_anchor_switch_also_picks_image()
    test_webgui_uses_paragraph_asset()
    test_webgui_prefers_table_path_and_validates_asset()
    print("all variant_annotate tests passed")
