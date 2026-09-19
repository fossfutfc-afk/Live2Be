# -*- coding: utf-8 -*-
"""`bond_shots.md`（镜头与手法, PL2 2026-09-19）——单开的小文件 + 它与地点表的镜像。

用户原话: *"你写一个简单的 bond_shots.md 吧，把煽情场景以及一些常用的 switch
组合手法（我怀疑现在全堆在 bond_rules）丢进去"*。⇒ 规则书说"**不能**怎么写"
（硬规则 + 判据）; 本文件说"怎么写**好看**"（手法 + 范本），以盒B 的一块注入。

三件事值得单独钉（都是"会漂"的地方）:

  ① **它是手写的**（用户: *"这个东西我打算单开一个小文件"*）——不从表生成, 所以
     没有任何机制拦着它和表脱钩; 而它给的镜头词**是**唯一到 writer 手里的写作用词
     （`PlaceTable.writing_words()` 至今没有生产消费方, 只有测试和 stats 在读它）。
  ② **镜头词只有在表里有逐字别名时才是免费的**: 层1（`resolve_exact`）命中 = **0 次**
     place 调用; 写错一个字 → 每次空镜都白花一次调用, 而且**层2 可能挑到别的图**。
     实测过的坑: 曾写 `繁星`, 而表的别名是 `繁星夜空` —— 层1 直接 miss。
     用户给这些词的理由是 *"这些词能让 LLM 更好的写作"* ⇒ 它们必须真的能用。
  ③ **搬走的不许留副本**: 收尾组合 ①②③④ 与范本原本在规则书 §七/§八, 现在只在
     `bond_shots.md` 里 —— 规则书剩一句指针。两份真源必然漂。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.bond.place_annotate import _layer1                    # noqa: E402
from core.media.place_table import WRITING_SDIR, load_table     # noqa: E402
from core.promptkit.blocks import BlockContext, render_block    # noqa: E402
from llm.prompts import load_prompt                             # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
FIXT_BOX = ROOT / "tests" / "fixtures" / "promptkit" / "bond_box.txt"


def _lens_words() -> list[str]:
    """抠出【一、可用的镜头词】那一行（文件里唯一用 `·` 分隔的行）。"""
    for line in load_prompt("bond_shots").splitlines():
        if "·" in line:
            return [w.strip() for w in line.split("·") if w.strip()]
    raise AssertionError("bond_shots.md 里找不到镜头词行（【一、可用的镜头词】下那行）")


class _Char:
    """`_bond_shots` 只读这两个属性（真身是 DynamicCharacter）。"""

    character_id = "igusa_haruka"
    display_name = "伊草遥香"


# ---------------------------------------------------------------------------
# ① 镜头词 ↔ 表的镜像（0 调用那条路）
# ---------------------------------------------------------------------------

def test_lens_words_are_free_layer1_hits():
    """★ 每个镜头词都得在层1 **唯一命中**（0 调用）且指向**写作用词**。

    ⚠️ "命中"不等于"逐字是别名": 层1（`PlaceTable.resolve_exact`）是**最长别名子串**
    匹配——`海边夜空` 靠别名 `夜空` 命中, 也是 0 调用。要求的是**唯一**（歧义会被
    层1 拒绝并下沉层2）, 以及落在 `sdir == SDIR_Atmosphere` 上（别指向一个真地点）。

    这一条红了怎么修（二选一, 别改测试）:
      · 词写错了 → 改成表里能唯一命中的说法
      · 表里确实少了这个词 → 作者侧（tempo 工作台）加别名后同步表
    """
    t = load_table()
    assert t.ok, f"真表读不出来: {t.error}"
    key_set = set(t.keys())
    atmos = {e.place: e for e in t.writing_words()}
    assert atmos, "表里一条写作用词都没有——【镜头词】这一节就成了一纸空话"

    words = _lens_words()
    assert len(words) >= 4, f"镜头词太少: {words}"
    assert len(set(words)) == len(words), f"镜头词有重复: {words}"

    seen: dict[str, str] = {}
    for w in words:
        hits = t.resolve_exact(w)
        assert len(hits) == 1, (
            f"镜头词 {w!r} 层1 命中不唯一（{hits}）——"
            f"层1 不猜（歧义下沉层2）, 每次都会多花一次调用")
        key = _layer1(w, t, "", key_set)
        assert key, f"镜头词 {w!r} 层1 没命中（返回 {key!r}）——writer 照抄了也白搭"
        assert key in atmos, (
            f"镜头词 {w!r} → {key}, 但它不是写作用词"
            f"（sdir={t.get(key).sdir!r} ≠ {WRITING_SDIR!r}）——镜头不该指向一个真地点")
        seen[w] = key

    # 反方向也要守: 表里每张 atmosphere 图都得有一个 writer 能照抄的词,
    # 否则那张图**永远用不上**（writer 不知道它存在, 层1 也没有入口）。
    missing = sorted(set(atmos) - set(seen.values()))
    assert not missing, (
        f"表里的写作用词 {missing} 在 bond_shots.md【一】里没有对应的词——"
        f"新图进表后请把它的别名补进那一行, 否则这张图只能靠层2 瞎撞")
    print(f"    镜头词: {len(words)} 个词 → {sorted(set(seen.values()))}（全部层1 0 调用）")


def test_lens_words_line_is_the_only_copiable_list():
    """镜头词行是 writer 照抄用的 —— 它得**明说照抄**, 且别在别处再列一份。"""
    text = load_prompt("bond_shots")
    assert "照抄" in text, "得告诉 writer 这行是照抄用的（改一个字画面就认不出来）"
    assert text.count("·") == len(_lens_words()) - 1, "`·` 只该出现在镜头词那一行"
    # 曾经的坑: 在正文里写"纯黑（黑场）"——"黑场"**不是**表的别名（黑屏/黑色/黑幕才是）,
    # writer 照抄括号里的词就 miss。凡是摆在 writer 面前的同义词, 都得是别名。
    assert "黑场" not in text, "“黑场”不是表的别名——writer 抄走就 miss（要么改表, 要么别写它）"
    print("    镜头词行: 唯一一份、明说照抄、没有表外词")


# ---------------------------------------------------------------------------
# ② 规则书里只留指针（搬走了就别留副本）
# ---------------------------------------------------------------------------

def test_rules_keeps_only_a_pointer():
    """收尾组合与范本已搬进 bond_shots —— 规则书里不许留副本。"""
    rules = load_prompt("bond_story_rules")
    shots = load_prompt("bond_shots")
    assert "【镜头与手法】" in rules, "规则书里得有指针, 否则 writer 不知道手法那一节存在"
    assert "【八、范本】" not in rules, "范本已搬走, 规则书里不许留副本"
    assert "【七、收尾与收尾组合】" not in rules, "标题已收窄为【七、收尾】"
    # 范本/收尾原句只在 shots 里（挑几个不会在别处出现的特征串——"放学后的天台"
    # 这类词在【换场】节里本来就有, 不能当判据）
    for moved in ("老、老师……你真的来了。", "她走进夜色里，脚步比来时轻了很多",
                  "那沓写得歪歪扭扭却格外认真的小卡片"):
        assert moved not in rules, f"搬走的正文还在规则书里: {moved}"
        assert moved in shots, f"搬走的正文没落进 bond_shots: {moved}"
    # 硬规则仍归规则书（end 的形态是判据, 不是手法）
    assert "收尾字段，不是老师的话" in rules
    print("    规则书: 只剩 end 硬规则 + 一句指针; 组合/范本已迁走")


# ---------------------------------------------------------------------------
# ③ 块渲染（占位替换 / 盒内位置 / 夹具无残留占位符）
# ---------------------------------------------------------------------------

def test_block_renders_and_substitutes_char():
    """块渲染: 标题 + 占位替换; 无 char 也不抛（纯文本块用手写占位）。"""
    text = render_block("bond_shots", BlockContext(char=_Char()))
    assert text and text.startswith("【镜头与手法】")
    assert "{char_id}" not in text and "{char_name}" not in text
    assert "igusa_haruka" in text, "范本里的 {char_id} 该换成角色 id"
    for section in ("【一、可用的镜头词】", "【二、switch 的几种组合拳】",
                    "【三、煽情场景怎么写】", "【四、收尾的几种收法】", "【五、范本】"):
        assert section in text, f"少了小节: {section}"
    assert render_block("bond_shots", BlockContext())       # 不抛（占位保留）
    print(f"    块: 【镜头与手法】{len(text)} 字符, 占位已替换")


def test_bond_box_fixture_has_no_raw_placeholder():
    """现网盒B 快照: 镜头与手法在盒里, 且 writer 看不到任何 `{...}` 占位。"""
    box = FIXT_BOX.read_text(encoding="utf-8")
    assert "【镜头与手法】" in box, "夹具没刷新（改盒内容后须跑 PROMPTKIT_UPDATE_FIXTURES）"
    assert "{char_id}" not in box and "{char_name}" not in box, "盒里残留了未替换占位符"
    print("    盒B 夹具: 【镜头与手法】在盒内; 无未替换占位符")


if __name__ == "__main__":
    test_lens_words_are_free_layer1_hits()
    test_lens_words_line_is_the_only_copiable_list()
    test_rules_keeps_only_a_pointer()
    test_block_renders_and_substitutes_char()
    test_bond_box_fixture_has_no_raw_placeholder()
