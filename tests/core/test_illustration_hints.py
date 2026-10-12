"""角色生图提示（illustration.yml）加载单测。

与 profile.yml 的 halo 字段**刻意分开**: 那里是给其他角色/扮演查阅的设定,
illustration.yml 专供生图。缺失/坏值 → 空（不阻断生图）。

运行: python -m pytest tests/core/test_illustration_hints.py
"""
import sys
from pathlib import Path

from core.parsing.dynamic_character_parser import CharacterLoader

ROOT = Path(__file__).resolve().parent.parent.parent


def _mk(tmp_path: Path, char_id: str, illustration: str | None) -> None:
    d = tmp_path / char_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "profile.yml").write_text("REQ~most_called_name: 测试角色\n", encoding="utf-8")
    if illustration is not None:
        (d / "illustration.yml").write_text(illustration, encoding="utf-8")


def test_missing_file_returns_empty(tmp_path):
    """没有 illustration.yml / 角色不存在 → {}（接口可空, 引擎用默认文案）。"""
    _mk(tmp_path, "a", None)
    loader = CharacterLoader(tmp_path)
    assert loader.load_illustration("a") == {}
    assert loader.load_illustration("no_such_char") == {}
    print("    empty: 缺文件 → 默认文案")


def test_reads_and_folds_hints(tmp_path):
    """读到 halo_hint（YAML 折行 → 单行）与 character_hint。"""
    _mk(tmp_path, "b", """
halo_hint: >
  三个互相分离的紫色钝角三角形，
  绕中心旋转对称。
character_hint: 紫色短发, 精灵耳发型
""")
    hints = CharacterLoader(tmp_path).load_illustration("b")
    assert hints["halo_hint"].startswith("三个互相分离的紫色钝角三角形")
    assert "\n" not in hints["halo_hint"]              # 折行折叠成单行
    assert hints["character_hint"] == "紫色短发, 精灵耳发型"
    print("    parse: halo_hint 折行折叠 + character_hint")


def test_ignores_unknown_and_bad_values(tmp_path):
    """白名单外的键忽略; 非字符串/空串忽略（宁缺勿错）。"""
    _mk(tmp_path, "c", "halo_hint: 123\nother: x\ncharacter_hint: ''\n")
    assert CharacterLoader(tmp_path).load_illustration("c") == {}
    _mk(tmp_path, "d", "halo_hint: [1, 2]\n")
    assert CharacterLoader(tmp_path).load_illustration("d") == {}
    print("    bad: 白名单过滤 + 类型过滤")


def test_real_character_illustration_yml():
    """真机角色卡: igusa_haruka 的 illustration.yml 已提供光环描述（接口打通）。"""
    hints = CharacterLoader(ROOT / "config" / "characters").load_illustration("igusa_haruka")
    assert "钝角三角形" in hints.get("halo_hint", ""), hints
    print("    real: igusa_haruka halo_hint 就位")
