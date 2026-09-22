# -*- coding: utf-8 -*-
"""`entities.py` 的测试（DESIGN_GRAPH_V4 §3.0 · **D0**）。

只留两条 —— 一条钉"字段形状与 kind 不被归一"（§3.0 埋的那个坑），
一条钉 `ensure_entities` 的行为（保留号 + 幂等 + 不写盘）。
其余（audit 干净 / 渲染不误注入 / classify_pair 的 about 方向）已有别处覆盖。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from core.brain.wiki_v2 import WikiStoreV2, make_node                  # noqa: E402
from core.brain.wiki_v2.entities import SELF_ID, SENSEI_ID, ensure_entities  # noqa: E402
from core.brain.wiki_v2.nodes import KINDS                             # noqa: E402


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")


def test_entity_kind_and_new_fields_roundtrip():
    """entity 是一个真 kind（**不再被 `from_dict` 归一成 episode**）+ 四个新字段往返。

    ⚠️ `from_dict` 对不认识的 kind 一律降级成 `episode` —— 所以"进了 `KINDS`"
    这件事必须被钉住: 忘了加的那天, 每条 entity 都会被静默当成一条经历。
    """
    assert "entity" in KINDS
    n = make_node("entity", name="老师", text="老师是第一个不会嫌弃我的人",
                  aliases=["sensei", "他"], state=["今天戴了眼镜"])
    assert n.kind == "entity"                      # 没被降级
    assert n.validate() == []
    back = type(n).from_json_line(n.to_json_line())
    assert (back.kind, back.name, back.aliases, back.state, back.text) == \
        ("entity", "老师", ["sensei", "他"], ["今天戴了眼镜"], "老师是第一个不会嫌弃我的人")
    assert make_node("entity").validate()          # 缺 name → 拒
    # `items` 是 episode 的字段（§3.1 的物品台账）
    ep = make_node("episode", text="老师送了我一盆杂草", items=["一盆杂草", "锈饼干盒"])
    assert type(ep).from_json_line(ep.to_json_line()).items == ["一盆杂草", "锈饼干盒"]


def test_ensure_entities_reserves_ids_and_is_idempotent(tmp_path):
    """保留号 x0000/x0001 + 幂等 + **不写盘**（读路径纪律: 调用方决定何时 save）。"""
    st = _store(tmp_path)
    created = ensure_entities(st, char_name="伊草 遥香", aliases=("遥香", "ハルカ"),
                             player_name="阿宅")
    assert created == [SELF_ID, SENSEI_ID] == ["x0000", "x0001"]
    assert st.get(SELF_ID).name == "伊草 遥香" and "遥香" in st.get(SELF_ID).aliases
    assert st.get(SENSEI_ID).name == "老师"
    assert set(st.get(SENSEI_ID).aliases) == {"sensei", "阿宅"}
    assert st.get(SELF_ID).text == ""              # 立场留空, 由第 3 轮长出来
    assert st.audit() == []                        # entity 不触发任何不变量

    assert not st.path.is_file()                   # 没写盘
    assert ensure_entities(st, char_name="伊草 遥香", player_name="阿宅") == []
    assert len(st) == 2                            # 幂等
    assert st.next_id("x") == "x0002"              # 保留号挡住了 0/1
