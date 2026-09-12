# -*- coding: utf-8 -*-
"""MemorialProbe 流式嗅探状态机测试（方案 A step2）——**已归档 2026-09-12**。

v1 专用: 它嗅的是 `"action":"memorial_enter"` 的 prompt 字段, 记录流 v2 里不存在
→ 主链改用"一行 `stage:memorial` 解析即开画"（决策 #39）; 本模块留档供考古,
v2 行为由 `tests/core/test_vn_records_engine.py::test_memorial_fires_image_hook_*`
与 B 层冒烟"纪念链路"步骤覆盖。

要点: 值闭合即定稿（触发点可靠）; 分块边界任意; 非目标动作永不误触发;
只触发一次; 乱序退化为"action 确认后立即触发"（不亏）; 回调异常不炸流。
"""
import pytest

from core.bond.stream_probe import MemorialProbe, _find_key_string

ENTER = ('{"action": "memorial_enter", "payload": {"prompt": "她在湖边微笑，'
         '眼角带着一滴泪，黄昏暖光", "paragraphs": [{"text": "（煽情）"}]}}')


def test_find_key_string_closed_and_unclosed():
    assert _find_key_string('{"action": "memorial_enter', "action") is None   # 引号未到
    assert _find_key_string('{"action": "memorial_enter"', "action") == "memorial_enter"  # 值闭合即定稿（不等 JSON 闭合）
    assert _find_key_string('{"a": 1, "action": "story_scene"}', "action") == "story_scene"
    assert _find_key_string('{"action": 123}', "action") is None      # 非字符串值


def test_single_chunk_fires():
    calls: list[str] = []
    probe = MemorialProbe(calls.append)
    probe.feed(ENTER)
    assert calls == ["她在湖边微笑，眼角带着一滴泪，黄昏暖光"]
    assert probe.fired


def test_split_chunks_arbitrary_boundaries():
    """chunk 边界任意切（含引号/转义跨 chunk）——闭合才触发, 值完整。"""
    calls: list[str] = []
    probe = MemorialProbe(calls.append)
    cuts = [0, 7, 13, 40, 41, 42, 60, len(ENTER)]      # 特意切在引号/冒号附近
    prev = 0
    for c in cuts[1:]:
        probe.feed(ENTER[prev:c])
        prev = c
    assert calls == ["她在湖边微笑，眼角带着一滴泪，黄昏暖光"]


def test_non_memorial_action_never_fires():
    calls: list[str] = []
    probe = MemorialProbe(calls.append)
    probe.feed('{"action": "story_scene", "payload": {"paragraphs": []}}')
    assert not calls
    assert probe.fired                     # 已判定非目标, 永久静默


def test_fires_only_once():
    calls: list[str] = []
    probe = MemorialProbe(calls.append)
    probe.feed(ENTER)
    probe.feed("更多内容")
    assert len(calls) == 1


def test_reversed_order_prompt_before_action():
    """乱序: prompt 字段先完整输出, action 后到——action 确认时值已闭合, 立即触发。"""
    calls: list[str] = []
    probe = MemorialProbe(calls.append)
    probe.feed('{"payload": {"prompt": "湖边", "paragraphs": []}, "action": "')
    assert not calls                      # action 未确认——不触发
    probe.feed('memorial_enter"}')
    assert calls == ["湖边"]


def test_escaped_quotes_in_prompt():
    raw = '{"action": "memorial_enter", "payload": {"prompt": "她说\\"谢谢\\"\\\\真好"}}'
    calls: list[str] = []
    probe = MemorialProbe(calls.append)
    probe.feed(raw)
    assert calls == ['她说"谢谢"\\真好']


def test_empty_prompt_does_not_fire():
    calls: list[str] = []
    probe = MemorialProbe(calls.append)
    probe.feed('{"action": "memorial_enter", "payload": {"prompt": ""}}')
    assert not calls


def test_reset_reenables():
    calls: list[str] = []
    probe = MemorialProbe(calls.append)
    probe.feed(ENTER)
    assert len(calls) == 1
    probe.reset()
    probe.feed(ENTER)
    assert len(calls) == 2


def test_callback_exception_swallowed():
    def bad(_p):
        raise RuntimeError("boom")
    probe = MemorialProbe(bad)
    probe.feed(ENTER)                     # 不炸
    assert probe.fired
