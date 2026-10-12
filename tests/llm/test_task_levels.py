"""llm/task_levels.py 单测 — 任务档位真源表（thinking + max_tokens 集中管理）。

覆盖:
    1. 三类 thinking 档位语义（main=default 跟随 settings / emotion=off / digest=high）
    2. max_tokens 形态值（mmt 4096 / bond 16384 / emotion 512 / digest 8192…）
    3. extra_body 换算（default→None / off→thinking disabled / 显式档→dict）
    4. settings.toml [llm.tasks] 覆盖（合法合并 / 非法忽略 / 未知形态忽略）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import llm.task_levels as tl


def test_base_profiles():
    """三类 thinking 的基准档位与 max_tokens 形态值。"""
    # thinking 分类（用户拍板: main / emotion / digest）
    assert tl.PROFILES["mmt"]["thinking"] == "default"      # main 跟随 settings 全局
    assert tl.PROFILES["bond"]["thinking"] == "default"
    assert tl.PROFILES["emotion"]["thinking"] == "off"      # 标注低价值, 显式关
    assert tl.PROFILES["digest"]["thinking"] == "high"      # 深度认知, 固定 high
    # max_tokens 形态值
    assert tl.max_tokens("mmt") == 4096
    assert tl.max_tokens("bond") == 16384
    assert tl.max_tokens("vn_cli") == 1536
    assert tl.max_tokens("emotion") == 512
    assert tl.max_tokens("digest") == 8192
    print("    基准: 三 thinking 类 + 五形态 max_tokens 就位")


def test_extra_body_conversion():
    """档位 → extra_body: default 交给客户端, off 显式关思考, 显式档注入。"""
    assert tl.extra_body("mmt") is None                     # default → 客户端 settings 档
    # off → 显式 thinking disabled（DeepSeek v4-flash 默认思考开——
    # 不传 = 思考吃光 max_tokens → 空 content, DeepSeek-V3#1610; 2026-09-08 真机定位）
    assert tl.extra_body("emotion") == {"thinking": {"type": "disabled"}}
    assert tl.extra_body("digest") == {"reasoning_effort": "high"}
    print("    extra_body: default→None / off→thinking disabled / high→显式注入")


def test_unknown_profile_raises():
    try:
        tl.max_tokens("nope")
    except KeyError:
        pass
    else:
        raise AssertionError("未知形态应抛 KeyError")


def test_settings_override(monkeypatch, tmp_path):
    """settings.toml [llm.tasks] 覆盖: 合法合并 / 非法忽略 / 未知形态忽略。"""
    cfg = tmp_path / "settings.toml"
    cfg.write_text(
        "[llm]\n"
        'reasoning_effort = "low"\n'
        "[llm.tasks.emotion]\n"
        'thinking = "medium"\n'
        "max_tokens = 768\n"
        "[llm.tasks.digest]\n"
        'thinking = "off"\n'
        "[llm.tasks.unknown]\n"
        'thinking = "high"\n'
        "[llm.tasks.mmt]\n"
        'thinking = "bogus"\n'
        "max_tokens = -5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tl, "_SETTINGS_PATH", cfg)
    monkeypatch.setattr(tl, "_OVERRIDES", None)             # 清缓存重读
    assert tl.profile("emotion")["thinking"] == "medium"
    assert tl.max_tokens("emotion") == 768
    assert tl.profile("digest")["thinking"] == "off"
    # 覆盖为 off → 显式关思考（同 emotion）
    assert tl.extra_body("digest") == {"thinking": {"type": "disabled"}}
    assert tl.profile("mmt") == tl.PROFILES["mmt"]          # 非法值 → 原样
    assert "unknown" not in tl._load_overrides()            # 未知形态忽略
    print("    settings 覆盖: 合法合并 / 非法忽略 / 未知形态忽略")


if __name__ == "__main__":
    test_base_profiles()
    test_extra_body_conversion()
    test_unknown_profile_raises()
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        # 最小覆盖测试（不经 pytest fixture）
        cfg = Path(d) / "settings.toml"
        cfg.write_text(
            "[llm.tasks.emotion]\nthinking = \"medium\"\nmax_tokens = 768\n",
            encoding="utf-8")
        tl._SETTINGS_PATH = cfg
        tl._OVERRIDES = None
        assert tl.profile("emotion")["thinking"] == "medium"
        tl._OVERRIDES = None
    print("llm/task_levels 单测: 全部通过")
