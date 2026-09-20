# -*- coding: utf-8 -*-
"""mmt_preset 回归 — 玩家名系统 + 名字校验 + /name 命令 + 注入。

覆盖:
  - 玩家名读写: 默认 sensei（缺失/null/空/损坏）/ 往返 / 已设置不询问
  - JSON 安全: null/true/false/引号/换行 等恶意输入不崩 JSON, 原样往返
  - 名字校验: 角色名允许（彩蛋兜住）、保留词（null/true/false）、超长、符号
  - /name 命令: 合法改 / 非法拒绝 / 无参不修改
  - 交互改名 set_player_name: 拒绝→重询 / 留空取消
  - 玩家名只系统显示, 不注入 system prompt（学生不直呼玩家名）

用临时 PLAYER_JSON（monkeypatch 模块常量）避免污染 data/basic/player.json。
运行: python -m pytest tests/core/test_mmt_preset.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.mmt import mmt_preset
from core.mmt.mmt_preset import (
    DEFAULT_PLAYER_NAME,
    _name_problem,
    ensure_player_name,
    handle_command,
    has_player_name,
    load_player_name,
    name_confirm,
    save_player_name,
    set_player_name,
)

PASS = 0
FAIL = 0


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS {name}")
    except Exception as e:  # noqa: BLE001
        FAIL += 1
        print(f"  FAIL {name}: {type(e).__name__}: {e}")


class StubLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, temperature=0.8, max_tokens=4096, response_format="text"):
        self.calls += 1
        return {"action": "mmt_chat", "reply": "嗯！", "payload": {}}

    def format_messages(self, *, system_prompt, user_message, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        msgs.extend(history or [])
        msgs.append({"role": "user", "content": user_message})
        return msgs


ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTERS = ROOT / "config" / "characters"


def _engine():
    from core.momotalk import MomoTalkEngine
    return MomoTalkEngine(CHARACTERS, StubLLM())


def _tmp_json(name="player.json") -> Path:
    d = Path(tempfile.mkdtemp(prefix="mmt_preset_"))
    return d / name


def _write(p: Path, payload) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(payload, encoding="utf-8")


# ----------------------------------------------------------------------------
# 玩家名系统 — 读写 / 默认
# ----------------------------------------------------------------------------

def test_default_missing():
    old = mmt_preset.PLAYER_JSON
    mmt_preset.PLAYER_JSON = _tmp_json()
    try:
        assert load_player_name() == DEFAULT_PLAYER_NAME == "sensei"
        assert not has_player_name()
    finally:
        mmt_preset.PLAYER_JSON = old


def test_default_null():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        _write(p, '{"player_name": null}')
        assert load_player_name() == "sensei", "null 应回退默认"
        assert not has_player_name()
        _write(p, '{"player_name": "  "}')
        assert load_player_name() == "sensei", "空串应回退默认"
    finally:
        mmt_preset.PLAYER_JSON = old


def test_set_roundtrip():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        save_player_name("小明")
        assert load_player_name() == "小明"
        assert has_player_name()
        data = p.read_text(encoding="utf-8")
        assert '"player_name": "小明"' in data
    finally:
        mmt_preset.PLAYER_JSON = old


def test_corrupt():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        _write(p, "{{{ 不是 json")
        assert load_player_name() == "sensei", "损坏文件应回退默认"
        assert not has_player_name()
    finally:
        mmt_preset.PLAYER_JSON = old


# ----------------------------------------------------------------------------
# JSON 安全 — 恶意输入不崩, 原样往返
# ----------------------------------------------------------------------------

def test_json_safety():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        for evil in ["null", "true", "false", '"', "'", "\\", "a\nb", "{", "}"]:
            save_player_name(evil)
            # 文件必须仍是合法 JSON, 且存储为字符串（不是 JSON null/布尔）
            data = json.loads(p.read_text(encoding="utf-8"))
            assert isinstance(data["player_name"], str), f"{evil!r} 应以字符串存储"
            assert load_player_name() == evil, f"{evil!r} 应原样往返"
    finally:
        mmt_preset.PLAYER_JSON = old


# ----------------------------------------------------------------------------
# 名字校验 — 角色名允许 / 保留词 / 超长 / 符号
# ----------------------------------------------------------------------------

def test_char_name_allowed():
    """角色名不再禁止（取角色名由 name_confirm 彩蛋兜住）。"""
    for ok in ["陆八魔阿露", "伊草遥香", "浅黄 睦月", "陆八魔阿露 ",
               "小明", "sensei", "老师", "sensei酱"]:
        assert _name_problem(ok) is None, f"{ok!r} 应允许"


def test_reserved_words():
    for bad in ["null", "true", "false"]:
        assert _name_problem(bad) is not None, f"{bad!r} 应判为保留词"


def test_too_long():
    assert _name_problem("长" * 21) is not None, "超长应拒绝"


def test_symbols():
    for ok in ["小明", "sensei", "老师", "遥香酱", "ひろ", "カヨコ",
               "sensei_01", "星野 爱", "星野·爱"]:
        assert _name_problem(ok) is None, f"{ok!r} 不应判为非法"
    for bad in ["小☆明", "😊", 'a"b', "a<b", "a[b", "a\\b",
                "a​b",  # 零宽空格（肉眼不可见）
                "你好，", "a.b"]:
        assert _name_problem(bad) is not None, f"{bad!r} 应判为含非法符号"


# ----------------------------------------------------------------------------
# ensure_player_name — 首次询问
# ----------------------------------------------------------------------------

def test_ensure_already_set_no_prompt():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        save_player_name("遥香酱")
        answered = []
        name = ensure_player_name(input_fn=lambda _: answered.append(1) or "坏")
        assert name == "遥香酱", "已设置不应询问"
        assert not answered, f"不应触发输入: {answered}"
    finally:
        mmt_preset.PLAYER_JSON = old


def test_ensure_prompts_and_saves():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        # 取名 → 确认(y) → 保存
        answers = iter(["小明", "y"])
        name = ensure_player_name(input_fn=lambda _: next(answers))
        assert name == "小明" and load_player_name() == "小明"
        # 再调一次 → 已设置, 不再询问
        name2 = ensure_player_name(input_fn=lambda _: "不应被调用")
        assert name2 == "小明"
    finally:
        mmt_preset.PLAYER_JSON = old


def test_ensure_blank_defaults_sensei():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        assert ensure_player_name(input_fn=lambda _: "  ") == "sensei"
    finally:
        mmt_preset.PLAYER_JSON = old


def test_ensure_rejects_bad():
    """首次取名输保留词 → 拒绝并重询 → 合法名通过。"""
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        answers = iter(["null", "小明", "y"])
        name = ensure_player_name(input_fn=lambda _: next(answers))
        assert name == "小明" and load_player_name() == "小明"
    finally:
        mmt_preset.PLAYER_JSON = old


# ----------------------------------------------------------------------------
# set_player_name — 菜单 N 交互
# ----------------------------------------------------------------------------

def test_set_player_name_interactive():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        answers = iter(["null", "小明", "y"])
        name = set_player_name(input_fn=lambda _: next(answers))
        assert name == "小明", "保留词应被拒, 重询后存合法名"
        # 留空取消 → 保持原名
        before = load_player_name()
        name2 = set_player_name(input_fn=lambda _: "")
        assert name2 == before and load_player_name() == before
    finally:
        mmt_preset.PLAYER_JSON = old


# ----------------------------------------------------------------------------
# name_confirm — 彩蛋 / 常规确认（依赖真实 config/eggs/namegg.json）
# ----------------------------------------------------------------------------

def test_name_confirm_easter_egg():
    """名字命中 namegg.json 正则（"阿露"/"陆八魔阿露"）→ 打印彩蛋台词 + 确认环节照旧。"""
    from contextlib import redirect_stdout
    from io import StringIO

    for egg in ["阿露", "陆八魔阿露"]:
        buf, asked = StringIO(), []
        with redirect_stdout(buf):
            ok = name_confirm(egg, input_fn=lambda _: asked.append(1) or "y")
        assert ok is True, f"{egg!r} 彩蛋后输 y 应接受"
        assert asked, f"{egg!r} 彩蛋后仍应进入确认环节"
        assert "[???]" in buf.getvalue(), f"{egg!r} 应打印彩蛋台词"


def test_name_confirm_easter_egg_case():
    """英文 pattern 大小写不敏感（全大写 IGUSA_HARUKA 应命中并打印彩蛋）。"""
    from contextlib import redirect_stdout
    from io import StringIO

    buf = StringIO()
    with redirect_stdout(buf):
        ok = name_confirm("IGUSA_HARUKA", input_fn=lambda _: "y")
    assert ok is True, "彩蛋后输 y 应接受"
    assert "[???]" in buf.getvalue(), "英文 pattern 应大小写不敏感地命中"


def test_egg_pattern_matches():
    """别名匹配: 英文整词 / 中文子串 / 大小写不敏感。"""
    from core.mmt.mmt_preset import _egg_pattern_matches

    # 整词: aru 是 koharu 的子串（a-r-u）, 但非独立词, 不应命中
    assert not _egg_pattern_matches("aru", "koharu"), "aru 不应命中 koharu"
    assert not _egg_pattern_matches("haruka", "koharu"), "haruka 不应命中 koharu"
    assert not _egg_pattern_matches("haruka", "igusa_haruka_x"), "整词不命中带后缀"
    # 单独英文命中 / 大小写
    assert _egg_pattern_matches("aru", "aru")
    assert _egg_pattern_matches("aru", "ARU"), "英文应大小写不敏感"
    assert _egg_pattern_matches("igusa_haruka|haruka", "igusa_haruka")
    assert _egg_pattern_matches("haruka", "haruka酱"), "整词后接中文仍命中"
    # 中文/假名子串
    assert _egg_pattern_matches("阿露|aru", "陆八魔阿露")
    assert _egg_pattern_matches("阿露", "阿露酱")
    assert _egg_pattern_matches("アル", "陸八魔アル")


def test_name_confirm_sign():
    """彩蛋回复前缀: RJ~ 玩笑拒绝(去前缀, 只给 n/n) / AC~ 接受 / 无前缀普通。"""
    from contextlib import redirect_stdout
    from io import StringIO

    old_load = mmt_preset._load_namegg
    try:
        # RJ~ → 弹台词(去前缀) + 只给 (n/n) + 无论选什么都拒绝
        mmt_preset._load_namegg = lambda: {"小明": ["RJ~ 这个名字会带来灾难!"]}
        prompts = []

        def _fake_input(prompt):
            prompts.append(prompt)
            return "y"

        buf = StringIO()
        with redirect_stdout(buf):
            ok = name_confirm("小明", input_fn=_fake_input)
        assert ok is False, "RJ~ 应拒绝"
        assert "这个名字会带来灾难!" in buf.getvalue()
        assert "RJ~" not in buf.getvalue(), "RJ~ 台词应去掉前缀"
        assert prompts and "(n/n)" in prompts[0], "RJ~ 应只给 (n/n) 选项"

        # AC~ → 弹台词(去前缀) + 常规确认
        mmt_preset._load_namegg = lambda: {"小明": ["AC~ 这个名字很好。"]}
        buf = StringIO()
        with redirect_stdout(buf):
            ok = name_confirm("小明", input_fn=lambda _: "y")
        assert ok is True, "AC~ 输 y 应接受"
        assert "这个名字很好。" in buf.getvalue()
        assert "AC~" not in buf.getvalue(), "AC~ 台词应去掉前缀"

        # 无前缀 → 普通彩蛋 + 常规确认
        mmt_preset._load_namegg = lambda: {"小明": ["普普通通。"]}
        buf = StringIO()
        with redirect_stdout(buf):
            ok = name_confirm("小明", input_fn=lambda _: "n")
        assert ok is False, "无前缀输 n 应拒绝"
    finally:
        mmt_preset._load_namegg = old_load


def test_name_confirm_regular():
    """未命中 → 常规确认: y 接受 / n 拒绝 / EOF 接受。"""
    assert name_confirm("小明", input_fn=lambda _: "y") is True
    assert name_confirm("小明", input_fn=lambda _: "n") is False

    def _eof(_):
        raise EOFError

    assert name_confirm("小明", input_fn=_eof) is True


# ----------------------------------------------------------------------------
# /name 命令
# ----------------------------------------------------------------------------

def test_cmd_name():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        assert handle_command("/name 小明", _engine()) is None
        assert load_player_name() == "小明"
        # 无参数 → 显示当前称呼, 不修改
        assert handle_command("/name", _engine()) is None
        assert load_player_name() == "小明"
    finally:
        mmt_preset.PLAYER_JSON = old


def test_cmd_name_rejects():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        assert handle_command("/name null", _engine()) is None
        assert load_player_name() == "sensei", "保留词不应被保存"
        # 角色名已允许（LLM 不知道玩家自取名, 由 name_confirm 彩蛋兜住）
        assert handle_command("/name 陆八魔阿露", _engine()) is None
        assert load_player_name() == "陆八魔阿露", "角色名应允许"
    finally:
        mmt_preset.PLAYER_JSON = old


def test_cmd_unknown_returns_none():
    assert handle_command("/foobar", _engine()) is None  # 未知命令 → 继续循环


# ----------------------------------------------------------------------------
# 玩家名不注入 system prompt（仅系统显示）
# ----------------------------------------------------------------------------

def test_no_player_name_inject():
    """玩家名只系统显示, 不注入 system prompt（学生不会直呼玩家自定义名）。"""
    from core.momotalk import MomoTalkEngine

    engine = MomoTalkEngine(CHARACTERS, StubLLM())
    engine.start_session("igusa_haruka")
    assert "玩家称呼" not in engine._system_prompt, "不应注入玩家称呼"
    assert "小明" not in engine._system_prompt, "自定义名不应进 LLM context"
    print("    system prompt 无玩家名注入")


def main() -> None:
    print("mmt_preset 回归（玩家名 / 校验 / JSON 安全 / 注入）")
    print("=" * 46)
    check("默认: 文件缺失 → sensei", _t_default_missing)
    check("默认: null/空 → sensei", _t_default_null)
    check("save/load 往返 + has_player_name", _t_set_roundtrip)
    check("损坏文件 → sensei", _t_corrupt)
    check("JSON 安全: null/true/引号/换行 原样往返", _t_json_safety)
    check("校验: 角色名允许（彩蛋兜住）", _t_char_name_allowed)
    check("校验: 保留词拒绝", _t_reserved_words)
    check("校验: 超长拒绝", _t_too_long)
    check("校验: 符号白名单（文字/数字/_·〜～ 空格 vs 引号/emoji/零宽）", _t_symbols)
    check("ensure: 已设置不询问", _t_ensure_already_set_no_prompt)
    check("ensure: 首次询问并保存", _t_ensure_prompts_and_saves)
    check("ensure: 留空默认 sensei", _t_ensure_blank_defaults_sensei)
    check("ensure: 保留词拒绝重询", _t_ensure_rejects_bad)
    check("set_player_name: 拒绝重询 + 留空取消", _t_set_player_name_interactive)
    check("彩蛋别名: 英文整词/中文子串/大小写", _t_egg_pattern_matches)
    check("name_confirm: 命中彩蛋弹台词 + 确认照旧", _t_name_confirm_easter_egg)
    check("name_confirm: 英文 pattern 大小写不敏感", _t_name_confirm_easter_egg_case)
    check("name_confirm: 前缀 RJ~/AC~/无前缀", _t_name_confirm_sign)
    check("name_confirm: 常规确认 y/n/EOF", _t_name_confirm_regular)
    check("/name 改称呼", _t_cmd_name)
    check("/name 拒绝保留词/允许角色名", _t_cmd_name_rejects)
    check("未知命令继续", _t_cmd_unknown_returns_none)
    check("玩家名不注入 system prompt", _t_no_player_name_inject)
    print("=" * 46)
    if FAIL:
        print(f"结果: {PASS} PASS / {FAIL} FAIL")
        sys.exit(1)
    print(f"结果: {PASS} PASS / 0 FAIL — 全部通过")


if __name__ == "__main__":
    main()
