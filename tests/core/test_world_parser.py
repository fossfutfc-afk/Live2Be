"""parsing/world_parser 回归 — overview.yml 加载 + 注入渲染。

运行: python -m pytest tests/core/test_world_parser.py
"""
import sys
import tempfile
from pathlib import Path

from core.parsing.world_parser import load_world, world_to_prompt

PASS = 0
FAIL = 0

_WORLD_YML = """\
common:
  - 这个世界叫做基沃托斯
  - 学生都有自己的光环
hidden:
  - 学生本质是神明的化身
system:
  - 恋爱合法
"""


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS {name}")
    except Exception as e:  # noqa: BLE001
        FAIL += 1
        print(f"  FAIL {name}: {type(e).__name__}: {e}")


def _write(tmp: str, content: str = _WORLD_YML) -> Path:
    p = Path(tmp) / "overview.yml"
    p.write_text(content, encoding="utf-8")
    return p


def test_load_parses_tiers():
    with tempfile.TemporaryDirectory() as tmp:
        world = load_world(_write(tmp))
    assert world.common == ["这个世界叫做基沃托斯", "学生都有自己的光环"]
    assert world.hidden == ["学生本质是神明的化身"]
    assert world.system == ["恋爱合法"]


def test_missing_raises():
    try:
        load_world(Path("definitely/not/here.yml"))
    except FileNotFoundError as e:
        assert "世界观文件不存在" in str(e)
    else:
        raise AssertionError("缺失文件应抛 FileNotFoundError")


def test_to_prompt_default_hides_hidden():
    with tempfile.TemporaryDirectory() as tmp:
        world = load_world(_write(tmp))
    out = world_to_prompt(world)
    assert "【世界常识】" in out
    assert "【世界规则】" in out
    assert "基沃托斯" in out and "恋爱合法" in out
    assert "神明的化身" not in out  # hidden 默认不注入


def test_to_prompt_include_hidden():
    with tempfile.TemporaryDirectory() as tmp:
        world = load_world(_write(tmp))
    out = world_to_prompt(world, include_hidden=True)
    assert "【隐秘知识】" in out
    assert "神明的化身" in out


def test_empty_tiers_render_empty():
    with tempfile.TemporaryDirectory() as tmp:
        world = load_world(_write(tmp, "common: []\nsystem:\n"))
    assert world_to_prompt(world) == ""  # 全空 → 空串, 调用方跳过拼装


def test_non_list_tier_raises():
    with tempfile.TemporaryDirectory() as tmp:
        p = _write(tmp, "common: 不是列表\n")
        try:
            load_world(p)
        except ValueError as e:
            assert "common 档必须是列表" in str(e)
        else:
            raise AssertionError("非 list 档应抛 ValueError")


def test_real_overview_loads():
    root = Path(__file__).resolve().parent.parent.parent
    world = load_world(root / "config" / "settings" / "world" / "overview.yml")
    assert world.common and world.system
    assert "基沃托斯" in world_to_prompt(world)


if __name__ == "__main__":
    for fn in (
        test_load_parses_tiers,
        test_missing_raises,
        test_to_prompt_default_hides_hidden,
        test_to_prompt_include_hidden,
        test_empty_tiers_render_empty,
        test_non_list_tier_raises,
        test_real_overview_loads,
    ):
        check(fn.__name__, fn)
    print(f"\nparsing/world_parser 回归: {PASS}/{PASS + FAIL} 通过")
    sys.exit(1 if FAIL else 0)
