# -*- coding: utf-8 -*-
"""名字接口测试（N1, 2026-09-23）。只一条 —— 把"收敛前散在四处"的约定一次钉住。

真机 profile 是**混合键形态**（`REQ~most_called_name` + 裸 `other_names`/`jp_name`/`en_name`），
这是本接口存在的直接原因，所以用它当真样本。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from core.parsing.dynamic_character_parser import CharacterLoader      # noqa: E402
from core.parsing.names import char_names, names_of, speaker_names     # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def test_names_interface():
    """显示名/别名/说话人表三件事，一个接口给全（含两处现网差异）。"""
    # ① 真机 profile（混合键形态）→ 显示名走真源, 别名切分去重且**不含显示名本身**
    ch = CharacterLoader(ROOT / "config" / "characters").load("igusa_haruka",
                                                              strict=False)
    n = names_of(ch)
    assert n.display == "伊草 遥香", n
    assert "遥香" in n.aliases and "伊草 ハルカ" in n.aliases, n.aliases
    assert n.display not in n.aliases, "显示名不该在别名里重复（真机 most_called_name 只有 REQ~ 形态）"
    assert n.all()[0] == "伊草 遥香"

    # ② 带前缀的键也读得到（收敛前 `_name_aliases` 只认裸键/SIG~ —— 这里修掉那个洞）
    assert char_names({"REQ~most_called_name": "甲",
                       "REQ~other_names": "小甲，阿甲"}).aliases == ("小甲", "阿甲")
    # 超长名字丢掉（会误伤文本替换）+ 空 profile 不炸
    assert char_names({"other_names": "这个词实在是太长了不该当别名"}).aliases == ()
    assert names_of(None).display == "" and names_of(None).aliases == ()

    # ③ 说话人表: 基础表来自 contract（sensei → 老师, **不再各写一遍**）
    m = speaker_names(char_id="igusa_haruka", display="伊草 遥香", with_narrator=True)
    assert m == {"sensei": "老师", "narrator": "", "igusa_haruka": "伊草 遥香"}, m
    # 两处现网差异都不许被"统一"掉: CLI 不要 narrator 键（靠缺键不画名字行）
    assert "narrator" not in speaker_names(ch, with_narrator=False)
    # 取不到名字 → 回落 id
    assert speaker_names(char_id="nobody", display="")["nobody"] == "nobody"
    print(f"    names: {n.display} / aliases={len(n.aliases)} / 说话人表 3 键")
