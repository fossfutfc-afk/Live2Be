"""`tests/webgui` 的会话级约定（2026-10-08 链式读前加）。

## 为什么要有这个文件

链式读前（`pregen._READAHEAD_MIN_BOARDS`）把预生成的触发判据从"**手里空了才开工**"
改成了"**手里不够读（< 4 板）就再写一块**"。这会让**桩世界的预生成触发得勤得多**：
真机一块 6~13 板, 而多数用例的桩块只有 2~4 板 ⇒ 一开工就连续触发, 把 `ScriptedLLM`
的脚本吃光（表现是"预生成失败 / 脚本耗尽", 与本用例要验的东西无关）。

⇒ 这里把链式**关回旧节奏**（`min=1` = "手里有货就不开工"）, 让既有用例继续验它们
本来要验的东西（预热/adopt/台账/被拒留痕…）。**链式自己另有守门**:
`tests/webgui/test_bond_chain_readahead.py`（那里显式把 min 设成 4）。"""
import pytest

from webgui.bond import pregen as _pregen


@pytest.fixture(autouse=True)
def _chain_back_to_old_cadence(monkeypatch):
    """`min=1` = 旧行为（手里有货就不开工）。想验链式的用例自己再 monkeypatch 成 4。"""
    monkeypatch.setattr(_pregen, "_READAHEAD_MIN_BOARDS", 1, raising=False)
    yield
