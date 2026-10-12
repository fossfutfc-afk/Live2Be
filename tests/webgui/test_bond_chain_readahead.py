"""**链式读前**的守门（2026-10-08 用户裁决: *"我们明明可以一条链直接生成完的吧，不用等待"*）。

机制三段（`webgui/bond/pregen.py`）:
  ① **判据** `_READAHEAD_MIN_BOARDS`（默认 4）: "手里还有几块没被玩家读过的板"低于它
     就**再写一块排到队尾**（旧判据 = "手里有货就不开工" ⇒ 每次块尾硬等一整块生成）;
  ② **不抢槽位**: 槽位（`pregen_obj/scene` = 正等玩家点继续的那一块）有人 ⇒ 新块的
     首板**排到队尾**, 绝不顶掉它;
  ③ **未裁决选项注记**: 读前生成时那些板上的选项还没答案 ⇒ 告诉 writer"按任一选择
     都成立写开场", 免得它猜一个选择来承接。

⚠️ 本文件**显式把 min 设成 4**（`tests/webgui/conftest.py` 里全局钉的是 1 = 旧节奏）。
⚠️ 不调 `bond_finish` 收尾: 引擎/store 都注入在 `tmp_path`（`_setup`），测完即弃。

运行: python -m pytest tests/webgui/test_bond_chain_readahead.py
"""
import sys
import time
from pathlib import Path

from tests.webgui.test_bond import (  # noqa: E402
    CHARACTER,
    RECORD_BLOCK,
    _setup,
    scene,
)
from webgui.bond import _state  # noqa: E402
from webgui.bond import pregen as _pregen  # noqa: E402

_bond = __import__("webgui.bond", fromlist=["bond_start"])


def _chain_on(monkeypatch, n: int = 4) -> None:
    monkeypatch.setattr(_pregen, "_READAHEAD_MIN_BOARDS", n, raising=False)


def _wait(cond, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.05)
    return False


def _slot(state):
    return state.pregen_obj is not None or state.pregen_scene is not None


class _DummyVN:
    _pending_boards: list = []


class _BoardWithChoices:
    """一块"带未裁决选项"的板（`_pending_choice_note` 只读 `choices`）。"""

    choices = ["我订了窗边的位子。", "今天要你选一个。"]


def test_in_hand_counts_slot_and_queue():
    """`_in_hand_boards` = **槽位 + 待发队列**（不算屏上那块、不算草稿——草稿是镜像）。"""
    state = _state(CHARACTER, "s1")
    state.pregen_obj = state.pregen_scene = None
    state.vn = _DummyVN()
    assert _pregen._in_hand_boards(state) == 0

    state.vn._pending_boards = [1, 2, 3]
    assert _pregen._in_hand_boards(state) == 3           # 队列
    state.pregen_obj = object()
    assert _pregen._in_hand_boards(state) == 4           # + 槽位
    print("    in_hand = 队列 3 + 槽位 1 ✓")


def _block_with(marker: str) -> str:
    """一块**可辨认**的两板记录流。

    ⚠️ 尾板用**固定文本**（不含 marker）—— 否则"首板丢了"的变异会被子串命中蒙混过去
    （`（marker·尾板）` 里含 marker ⇒ `marker in text` 恒真; 2026-10-08 踩到）。
    """
    return "\n".join([
        '{"stage": "switch", "text": "深夜的杂草屋"}',
        f'{{"character": "{CHARACTER}", "text": "{marker}"}}',
        '{"character": "sensei", "text": "（切板）"}',
        f'{{"character": "{CHARACTER}", "text": "（本块尾板）"}}',
    ])


def _all_texts(state) -> list[str]:
    """手里所有板的正文（槽位 + 待发队列）——"首板去哪了"的判据。"""
    out: list[str] = []
    if state.pregen_obj is not None:
        out.extend((p or {}).get("text", "") for p in state.pregen_obj.paragraphs)
    for b in state.vn._pending_boards or []:
        out.extend((p or {}).get("text", "") for p in b.paragraphs)
    return out


def test_chain_generates_readahead_when_short(tmp_path, monkeypatch):
    """⭐ 槽位有人 + 手里不够读 ⇒ **起一次读前生成**:
      · **不顶掉槽位**（玩家眼前那块板不动）;
      · 新块的首板**必须落在手里**（排到队尾）——丢了就是白烧一次生成。

    变异验证（两条都得红）:
      A. 落地那段的 `else` 分支删掉 ⇒ 首板谁都没接（`_all_texts` 少一句）⇒ 红;
      B. 落地改成"无条件写槽位"（旧写法）⇒ 槽位被顶掉 ⇒ 红。
    """
    # ⚠️ 先**关掉**链式（min=99）: 否则 `bond_start` 之后链会自己连跑两次把 in_hand
    #    顶到 4 ⇒ 下面这次手动 `_pregenerate` 撞 `skip=enough` ⇒ 用例根本没走到落地那段
    #    （2026-10-08 实测踩到: 两条变异都"抓不住"就是这么来的）。
    # ⚠️ **两次生成必须给不同的脚本**（`_OLD_MARK` / `_NEW_MARK`）—— 给一模一样的内容时
    #    `pregen_scene == slot_before` 恒成立（dict 逐字判等）⇒ "顶掉槽位"的变异抓不住。
    _chain_on(monkeypatch, 99)
    _OLD_MARK = "（槽位那一块·首板）"
    _NEW_MARK = "（读前生成的块·首板）"
    narr = scene(lines=["（开场）她在门口气喘吁吁。"])
    engine, st, sid, llm = _setup(tmp_path, narr, _block_with(_OLD_MARK),
                                  _block_with(_NEW_MARK))
    _bond.bond_start(CHARACTER, sid)
    state = _bond._state(CHARACTER, sid)
    assert _wait(lambda: _slot(state)), "第一步应该有板进槽位"
    assert _wait(lambda: not state.busy), "开场那次生成该跑完了"
    slot_before = state.pregen_scene
    queued_before = len(state.vn._pending_boards)
    assert any(t.strip() == _OLD_MARK for t in _all_texts(state)), \
        f"槽位里应是开场块: {_all_texts(state)}"

    # 手动触发一次读前（正常由推进/入场触发）——此时槽位有人、in_hand 很小
    _chain_on(monkeypatch, 4)
    _pregen._pregenerate(state, CHARACTER, sid)
    assert _wait(lambda: not state.busy), "读前生成应该跑完"
    texts = _all_texts(state)
    queued_after = len(state.vn._pending_boards)

    assert state.pregen_scene is not None, "槽位被清空了（读前生成不该动它）"
    assert state.pregen_scene == slot_before, (
        "**槽位被读前生成顶掉了** —— 玩家眼前那一块板被换成了将来的板")
    assert queued_after > queued_before, (
        f"读前生成的板没排队尾: {queued_before} → {queued_after}")
    assert any(t.strip() == _NEW_MARK for t in texts), (
        "**新块的首板丢了** —— 既没进槽位也没排队尾（这次生成白烧）: "
        f"{texts}")
    print(f"    读前生成: 槽位不动, 队列 {queued_before} → {queued_after}, "
          f"首板在手里 ✓")


def test_chain_skips_when_enough_in_hand(tmp_path, monkeypatch):
    """手里够读（≥ min）⇒ **什么都不做**（不多烧一次生成）。"""
    _chain_on(monkeypatch, 4)
    narr = scene(lines=["（开场）她在门口气喘吁吁。"])
    engine, st, sid, llm = _setup(tmp_path, narr, RECORD_BLOCK)
    _bond.bond_start(CHARACTER, sid)
    state = _bond._state(CHARACTER, sid)
    assert _wait(lambda: _slot(state))
    # ⚠️ 采样前先让**双路标注**跑完：它们也是 LLM 调用（`emotion` / `place`），
    #    异步落在"采样之后、断言之前"就会让计数凭空多几条 —— 全量/组合跑时踩过
    #    （单独跑绿、`tests/core` + `tests/webgui` 同跑红：`assert 6 == 3`）。
    #    判据用 `busy` 复位（开场那次生成 + 标注 lane 都算在它里面）。
    assert _wait(lambda: not state.busy)
    state.vn._pending_boards = [object()] * 6            # 手里 7 块 ⇒ 远够
    calls_before = len(getattr(llm, "snapshots", []))
    _pregen._pregenerate(state, CHARACTER, sid)
    time.sleep(0.2)
    assert not state.busy, "手里够读却开工了（会白烧一次生成）"
    assert len(getattr(llm, "snapshots", [])) == calls_before, "不该调 LLM"
    print("    手里 7 块 ⇒ 不开工 ✓")


def test_pending_choice_note_lists_unanswered_options(tmp_path, monkeypatch):
    """未裁决选项注记: 手里有带 choices 的板 ⇒ 列出选项; 没有 ⇒ 不注入。"""
    _chain_on(monkeypatch, 4)
    narr = scene(lines=["（开场）她在门口气喘吁吁。"])
    engine, st, sid, llm = _setup(tmp_path, narr, RECORD_BLOCK)
    _bond.bond_start(CHARACTER, sid)
    state = _bond._state(CHARACTER, sid)
    assert _wait(lambda: _slot(state))

    state.vn._pending_boards = [_BoardWithChoices()]
    note = _pregen._pending_choice_note(state)
    assert note and "我订了窗边的位子。" in note, note
    assert "任一选择都成立" in note, note

    state.vn._pending_boards = []
    state.pregen_obj = state.pregen_scene = None
    assert _pregen._pending_choice_note(state) is None, "没有未裁决选项时不该注入"
    print("    注记: 有未裁决选项才给（含选项原文）✓")
