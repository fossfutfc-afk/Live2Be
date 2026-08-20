# -*- coding: utf-8 -*-
"""mmt_preset 回归 — 玩家名系统 + /name 命令 + engine 玩家称呼注入。

用临时 PLAYER_JSON（monkeypatch 模块常量）避免污染 data/basic/player.json。
用法: python core/mmt/_preset_test.py   （项目根, live2be env）
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.mmt import mmt_preset
from core.mmt.mmt_preset import (
    DEFAULT_PLAYER_NAME,
    LoopResult,
    ensure_player_name,
    handle_command,
    has_player_name,
    load_player_name,
    save_player_name,
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


def _tmp_json(name="player.json") -> Path:
    d = Path(tempfile.mkdtemp(prefix="mmt_preset_"))
    return d / name


def _write(p: Path, payload) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(payload, encoding="utf-8")


# ----------------------------------------------------------------------------
# 玩家名系统
# ----------------------------------------------------------------------------

def _t_default_missing():
    old = mmt_preset.PLAYER_JSON
    mmt_preset.PLAYER_JSON = _tmp_json()
    try:
        assert load_player_name() == DEFAULT_PLAYER_NAME == "sensei"
        assert not has_player_name()
    finally:
        mmt_preset.PLAYER_JSON = old


def _t_default_null():
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


def _t_set_roundtrip():
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


def _t_corrupt():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        _write(p, "{{{ 不是 json")
        assert load_player_name() == "sensei", "损坏文件应回退默认"
        assert not has_player_name()
    finally:
        mmt_preset.PLAYER_JSON = old


def _t_ensure_already_set_no_prompt():
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


def _t_ensure_prompts_and_saves():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        name = ensure_player_name(input_fn=lambda _: "小明")
        assert name == "小明" and load_player_name() == "小明"
        # 再调一次 → 已设置, 不再询问
        name2 = ensure_player_name(input_fn=lambda _: "不应被调用")
        assert name2 == "小明"
    finally:
        mmt_preset.PLAYER_JSON = old


def _t_ensure_blank_defaults_sensei():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        assert ensure_player_name(input_fn=lambda _: "  ") == "sensei"
    finally:
        mmt_preset.PLAYER_JSON = old


# ----------------------------------------------------------------------------
# /name 命令
# ----------------------------------------------------------------------------

def _t_cmd_name():
    old = mmt_preset.PLAYER_JSON
    p = _tmp_json()
    mmt_preset.PLAYER_JSON = p
    try:
        assert handle_command("/name 小明", None) is None
        assert load_player_name() == "小明"
        # 无参数 → 显示当前称呼, 不修改
        assert handle_command("/name", None) is None
        assert load_player_name() == "小明"
    finally:
        mmt_preset.PLAYER_JSON = old


def _t_cmd_unknown_returns_none():
    assert handle_command("/foobar", None) is None  # 未知命令 → 继续循环


# ----------------------------------------------------------------------------
# engine 玩家称呼注入
# ----------------------------------------------------------------------------

def _t_engine_inject():
    from core.momotalk import MomoTalkEngine

    root = Path(__file__).resolve().parent.parent.parent / "config" / "characters"
    engine = MomoTalkEngine(root, StubLLM(), player_name="小明")
    engine.start_session("igusa_haruka")
    assert "玩家称呼（你的对话对象）: 小明" in engine._system_prompt, "应注入玩家称呼"
    # 不传 player_name → 不注入
    engine2 = MomoTalkEngine(root, StubLLM())
    engine2.start_session("igusa_haruka")
    assert "玩家称呼" not in engine2._system_prompt, "默认不应注入"
    print("    engine 注入: 小明 注入 / 默认无注入")


def main() -> None:
    print("mmt_preset 回归（玩家名 / /name / 注入）")
    print("=" * 46)
    check("默认: 文件缺失 → sensei", _t_default_missing)
    check("默认: null/空 → sensei", _t_default_null)
    check("save/load 往返 + has_player_name", _t_set_roundtrip)
    check("损坏文件 → sensei", _t_corrupt)
    check("已设置不询问", _t_ensure_already_set_no_prompt)
    check("首次询问并保存", _t_ensure_prompts_and_saves)
    check("留空默认 sensei", _t_ensure_blank_defaults_sensei)
    check("/name 改称呼", _t_cmd_name)
    check("/name 无参不修改 + 未知命令继续", _t_cmd_unknown_returns_none)
    check("engine 玩家称呼注入", _t_engine_inject)
    print("=" * 46)
    if FAIL:
        print(f"结果: {PASS} PASS / {FAIL} FAIL")
        sys.exit(1)
    print(f"结果: {PASS} PASS / 0 FAIL — 全部通过")


if __name__ == "__main__":
    main()
