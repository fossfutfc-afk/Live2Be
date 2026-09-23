# -*- coding: utf-8 -*-
"""`entities.py` 的测试（DESIGN_GRAPH_V4 §3.0 · **D0** / §8.3 · **D2a**）。

只留五条 —— 一条钉"字段形状与 kind 不被归一"（§3.0 埋的那个坑），
一条钉 `ensure_entities` 的行为（保留号 + 幂等 + 不写盘），
三条钉第 3 轮**输入侧**三件套（候选表只给身份 / 命中集确定性规则 / 载荷区只给命中集）。
其余（audit 干净 / 渲染不误注入 / classify_pair 的 about 方向）已有别处覆盖。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from core.brain.wiki_v2 import WikiStoreV2, make_node                  # noqa: E402
from core.brain.wiki_v2.entities import (                             # noqa: E402
    SELF_ID, SENSEI_ID, candidate_table, ensure_entities, hit_set, payload_block,
)
from core.brain.wiki_v2.nodes import KINDS, BrainNode                  # noqa: E402


def _store(tmp_path) -> WikiStoreV2:
    return WikiStoreV2(tmp_path, world_id="world1", char_id="igusa_haruka")


class _Nodes:
    """最小 store 替身（只 `all()`/`get()`）—— 这三个函数只读这两个（顺手记下这个面）。

    用途: 造 `store.add` 拒绝得了的坏数据（`add` 会 `validate`, 无名的 entity 进不去）。
    """

    def __init__(self, *nodes):
        self._ns = list(nodes)

    def all(self):
        return list(self._ns)

    def get(self, nid):
        return next((n for n in self._ns if n.id == nid), None)



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


# ---------------------------------------------------------------------------
# D2a —— 第 3 轮的输入侧（§8.3 的两层注入）
# ---------------------------------------------------------------------------

def test_candidate_table_is_identity_only(tmp_path):
    """候选表 = 本地 id + 名字 + 别名; **不印类别**（2026-09-23 用户裁决, 见 §8.3）。"""
    st = _store(tmp_path)
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香", "ハルカ"),
                    player_name="阿宅")
    st.add(make_node("entity", name="小玉", aliases=["tama"]))     # x0002
    text, local_of = candidate_table(st)
    assert text.splitlines() == [
        "c0001 伊草 遥香（遥香/ハルカ）",
        "c0002 老师（sensei/阿宅）",
        "c0003 小玉（tama）",
    ]
    assert local_of == {"x0000": "c0001", "x0001": "c0002", "x0002": "c0003"}
    assert "（人）" not in text and "entity" not in text           # 类别一个字都不印

    nameless = BrainNode()                                        # `add` 进不去的坏数据
    nameless.id, nameless.kind = "x0009", "entity"
    assert candidate_table(_Nodes(nameless)) == ("", {})           # 无名的不进表


def test_hit_set_rules_and_short_alias_floor(tmp_path):
    """命中集 = hint ∪ 正文提及, **确定性**; 单字称呼不扫正文（否则命中一切）。"""
    st = _store(tmp_path)
    ensure_entities(st, char_name="伊草 遥香", aliases=("遥香",))
    st.update(SENSEI_ID, {"aliases": ["sensei", "他"]})            # 单字代词

    assert hit_set(st, hints=["老师"]) == [SENSEI_ID]              # 精确
    assert hit_set(st, hints=["他"]) == [SENSEI_ID]                # 单字 hint 不限长
    assert hit_set(st, hints=["Sensei"]) == [SENSEI_ID]            # 忽略大小写
    assert hit_set(st, hints=["伊草"]) == [SELF_ID]                # hint ⊂ name

    assert hit_set(st, texts=["遥香今天很安静"]) == [SELF_ID]       # 别名进正文
    assert hit_set(st, texts=["sensei, 早上好"]) == [SENSEI_ID]
    assert hit_set(st, texts=["他今天没来"]) == []                  # ⚠️ 单字别名不扫
    assert hit_set(st, texts=["今天天气不错"]) == []
    assert hit_set(st, hints=["老师"], texts=["遥香今天很安静"]) == [SELF_ID, SENSEI_ID]


def test_payload_block_renders_hits_only(tmp_path):
    """载荷区 = `立场` + `现状` 逐行; 只有一行头 = 还没载荷; 表外 id 一律不印。"""
    st = _store(tmp_path)
    ensure_entities(st, char_name="伊草 遥香")
    st.update(SENSEI_ID, {"text": "他是第一个不会嫌弃我的人",
                          "state": ["今天戴了眼镜", "手腕上贴着创可贴"]})
    _, local_of = candidate_table(st)
    assert payload_block(st, [SELF_ID, SENSEI_ID], local_of).splitlines() == [
        "c0001 伊草 遥香",                       # 还没载荷（该第 3 轮写）
        "c0002 老师",
        "  立场: 他是第一个不会嫌弃我的人",
        "  现状:",
        "    - 今天戴了眼镜",
        "    - 手腕上贴着创可贴",
    ]
    assert payload_block(st, ["m0001"], local_of) == ""            # 不在候选表里
    assert payload_block(st, [SELF_ID], {}) == ""                  # 没有 local_of 就不印
