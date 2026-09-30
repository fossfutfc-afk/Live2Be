# -*- coding: utf-8 -*-
"""MMT **行流契约**渲染（`contract/schema.py::build_line_schema`，⑥-2a 2026-09-25）。

与 `build_record_schema`（VN 记录流）并列的第三形态；设计见
`docs/DESIGN_STREAM_CONTRACT.md` §1（契约形式六条）/ §2（两域对照）/ §10.2 B1·B3。

覆盖:
    形状与硬规则   判别键两类行 / 一行一条 / 气泡粒度归模型 / 转义 / 两个独占约束
    动作表来自注册表  运行时渲染 —— 新增动作**自动进 prompt**（手写清单会漂）
    示范合法      示例每一行都是合法 JSON 对象, 且判别键 ∈ {text, action}
    不教旧形状    文本里不出现 `messages`（旧协议 ⑥-2e 才删, 但不能同时教两种形状）
    关示例        with_examples=False 更短, 但硬规则与动作表仍在
"""
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from contract.constants import APPROVAL_AUTO                          # noqa: E402
from contract.registry import ActionRegistry                          # noqa: E402
from contract.schema import build_line_schema                         # noqa: E402
from contract.spec import ActionSpec                                  # noqa: E402
from core.mmt.mmt_actions import build_mmt_registry                   # noqa: E402


def _example_lines(text: str) -> list[str]:
    """抠出示范行（缩进 4 空格的 `{…}` 那些）。"""
    return [ln.strip() for ln in text.splitlines()
            if ln.startswith("    {") and ln.rstrip().endswith("}")]


def test_shape_and_hard_rules():
    text = build_line_schema(build_mmt_registry())
    assert "一行一条" in text and "不要数组" in text and "不要围栏" in text
    # 两类行的判别键
    assert '{"text": "角色说的话"}' in text
    assert '{"action": "<动作名>", "payload": {...}}' in text
    assert "一个气泡" in text                       # 一行 = 一气泡（新语义）
    assert "气泡粒度由你定" in text
    assert '\\"' in text                            # 转义示范（实战唯一真实错误源）
    # 两个独占约束（⑥-2c 的硬校验与这里的文案必须同款）
    assert "必须是**唯一**的操作行" in text
    assert "**单独一轮**" in text
    assert "至少要有一条行" in text
    # 文案纪律: 不包「」; 不教旧形状（不能同时存在两种形状的示范）
    assert "「" not in text and "」" not in text
    assert "messages" not in text
    print("    line-schema: 判别键/硬规则/独占约束/转义 + 不教旧形状")


def test_action_table_comes_from_registry():
    """动作表是**运行时渲染**的：注册表里加一个动作, 文本里立刻出现（不用改文案）。"""
    reg = build_mmt_registry()
    before = build_line_schema(reg)
    assert before.count("  - mmt_") == 3, before
    reg.register(ActionSpec(
        "mmt_fake_action", lambda payload: dict(payload), APPROVAL_AUTO,
        prompt_fields=frozenset({"action", "payload"}),
        payload_schema="note: 假动作（用例用）"))
    after = build_line_schema(reg)
    assert "mmt_fake_action" in after and "note: 假动作（用例用）" in after
    assert after.count("  - mmt_") == 4
    print("    line-schema: 动作表来自注册表（新增动作自动进 prompt）")


def test_examples_are_valid_json_objects():
    """⭐ 示范本身必须合法——`示例才是形状的来源`（CLAUDE.md §8），形状错了模型照抄。"""
    text = build_line_schema(build_mmt_registry())
    rows = _example_lines(text)
    assert len(rows) >= 4, rows
    for row in rows:
        obj = json.loads(row)                       # 不合法直接抛
        assert isinstance(obj, dict), row
        # ⭐ 判别键**恰好其一**（三类行互斥, N5b 起含想起行）
        assert sum(k in obj for k in ("text", "action", "noticed")) == 1, row
    kinds = [next(k for k in ("text", "action", "noticed") if k in json.loads(r))
             for r in rows]
    assert {"action", "text", "noticed"} <= set(kinds)   # 三类行都有示范
    # 交错顺序：文本示范里第一条是 text、第二条是 action（话→图→话 的演示）
    assert kinds[0] == "text" and kinds[1] == "action"
    print(f"    line-schema: {len(rows)} 条示范行全部合法 JSON 且判别键唯一")


def test_without_examples_keeps_rules_and_actions():
    brief = build_line_schema(build_mmt_registry(), with_examples=False)
    full = build_line_schema(build_mmt_registry())
    assert len(brief) < len(full)
    assert "硬规则" in brief and "可用操作" in brief
    assert "mmt_trigger_bond_story" in brief
    assert not _example_lines(brief)
    print(f"    line-schema: 关示例 {len(brief)} < 全量 {len(full)} 字符（规则与动作表仍在）")
