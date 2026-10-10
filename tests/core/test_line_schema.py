# -*- coding: utf-8 -*-
"""MMT **行流契约**渲染（`contract/schema.py::build_line_schema`，⑥-2a 2026-09-25）。

与 `build_record_schema`（VN 记录流）并列的第三形态；设计见
`docs/DESIGN_STREAM_CONTRACT.md` §1（契约形式六条）/ §2（两域对照）/ §10.2 B1·B3。

覆盖:
    形状与硬规则   判别键两类行 / 一行一条 / 气泡粒度归模型 / 转义 / **三个**独占约束
    动作表来自注册表  运行时渲染 —— 新增动作**自动进 prompt**（手写清单会漂）
    示范合法      示例每一行都是合法 JSON 对象, 且判别键 ∈ {text, action}
    ⭐ 独占示范同款  inspect 那块只有一条行; look 那块它是**唯一操作行 + 最后一行**
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

#: 独占动作（`mmt_check` 判 `mmt.exclusive-violation`）—— ⚠️ 两族**口径不同款**:
#: `inspect` = 整轮只有它一条行; `look` = 唯一操作行 + 放最后一行（trigger 式）。
_EXCLUSIVE = ("mmt_inspect_character", "mmt_look")


def _example_lines(text: str) -> list[str]:
    """抠出示范行（缩进 4 空格的 `{…}` 那些）。"""
    return [ln.strip() for ln in text.splitlines()
            if ln.startswith("    {") and ln.rstrip().endswith("}")]


def _example_blocks(text: str) -> list[list[str]]:
    """把示范区切成**块** = 一次回复（连续的示范行算一块）。

    ⚠️ 块与块之间隔着空行/说明行 —— 这个结构本身就是"这是两次回复"的隐喻,
    所以"含独占行的块恰好一条行"才是一条有意义的判据。
    """
    blocks: list[list[str]] = []
    prev = False
    for ln in text.splitlines():
        row = ln.strip()
        is_json = ln.startswith("    {") and row.endswith("}")
        if is_json:
            if not prev:
                blocks.append([])
            blocks[-1].append(row)
        prev = is_json
    return blocks


def test_shape_and_hard_rules():
    text = build_line_schema(build_mmt_registry())
    assert "一行一条" in text and "不要数组" in text and "不要围栏" in text
    # 两类行的判别键
    assert '{"text": "角色说的话"}' in text
    assert '{"action": "<动作名>", "payload": {...}}' in text
    assert "一个气泡" in text                       # 一行 = 一气泡（新语义）
    assert "气泡粒度由你定" in text
    assert '\\"' in text                            # 转义示范（实战唯一真实错误源）
    # 三个独占约束（`mmt_check` 的硬校验与这里的文案必须同款; ⭐ 两族口径**不同款**）
    assert "必须是**唯一**的操作行" in text
    assert "**单独一轮**" in text
    assert "至少要有一条行" in text
    # ⭐ 5 = inspect（整轮只有它一条行）; 6 = look（唯一操作行 + **最后一行** — 用户 10-08 裁）
    rule5 = next(ln for ln in text.splitlines() if ln.startswith("5. "))
    rule6 = next(ln for ln in text.splitlines() if ln.startswith("6. "))
    assert "mmt_inspect_character" in rule5 and "单独一轮" in rule5, rule5
    assert "mmt_look" in rule6 and "唯一的操作行" in rule6, rule6
    assert "最后一行" in rule6, rule6
    # 文案纪律: **示范行**里的戏词不包「」（用户裁决 #24）。
    # ⚠️ 只查示范行 —— payload 说明里会引"她可能说的原话"（一形一义: 「」= 原话）,
    # 那不是戏词示范; 拿全局断言会把"引语"和"戏词示范"混成一件事。
    for row in _example_lines(text):
        assert "「" not in row and "」" not in row, row
    assert "messages" not in text
    print("    line-schema: 判别键/硬规则/独占约束/转义 + 不教旧形状")


def test_action_table_comes_from_registry():
    """动作表是**运行时渲染**的：注册表里加一个动作, 文本里立刻出现（不用改文案）。

    ⚠️ 条数**按注册表数**（不写死）—— 写死过一次, 加第 4 个动作时它静默过期
    （`df616a4` 注册 `mmt_look` 时就是这个用例在红, 当时没跑这个文件）。
    """
    reg = build_mmt_registry()
    before = build_line_schema(reg)
    n = len(reg.action_names())
    assert before.count("  - mmt_") == n, before
    reg.register(ActionSpec(
        "mmt_fake_action", lambda payload: dict(payload), APPROVAL_AUTO,
        prompt_fields=frozenset({"action", "payload"}),
        payload_schema="note: 假动作（用例用）"))
    after = build_line_schema(reg)
    assert "mmt_fake_action" in after and "note: 假动作（用例用）" in after
    assert after.count("  - mmt_") == n + 1
    print(f"    line-schema: 动作表来自注册表（{n} → {n + 1}, 新增动作自动进 prompt）")


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


def test_exclusive_examples_match_the_hard_rules():
    """⭐ **示范与硬规则必须同款**（示范才是形状的来源 —— 真机 art 命中率 0/5 的根因就是
    取值清单 / 硬规则 / 规则书三处说法强度不一, 模型只照抄了示范那个形状）:

      · `mmt_inspect_character` 那一块**只有它一条行**（静默推理轮）;
      · `mmt_look` 那一块里它必须是**唯一操作行**、且在**最后一行**
        （trigger 式 —— 2026-10-08 用户裁: "先说一句'让我想一想'再翻"必须合法）。
    """
    text = build_line_schema(build_mmt_registry())
    seen: set[str] = set()
    for block in _example_blocks(text):
        objs = [json.loads(r) for r in block]
        at = [(i, o["action"]) for i, o in enumerate(objs) if "action" in o]
        names = {a for _, a in at}
        if "mmt_inspect_character" in names:
            seen.add("inspect")
            assert len(block) == 1, f"inspect 那一轮只能有它一条行: {block}"
        if "mmt_look" in names:
            seen.add("look")
            assert names == {"mmt_look"}, f"look 必须是那一轮唯一的操作行: {block}"
            assert at[0][0] == len(block) - 1, f"look 要放在那一块的最后一行: {block}"
    assert seen == {"inspect", "look"}, f"两族都要有示范（实得 {sorted(seen)}）"


def test_examples_show_the_look_then_speak_pair():
    """⭐ "先说话再翻"要看得出是**两跳**: 那一块到 `look` 为止, 紧跟着的一块才是话。

    ⚠️ 松成"至少有一句"的话, 把"翻到之后"整块删掉也照样绿（下一块是想起旧事那块,
    它本身也带 text 行 ⇒ 洞就是这么来的）—— 所以判据是**全是话**。
    """
    blocks = _example_blocks(build_line_schema(build_mmt_registry()))
    idx = [i for i, b in enumerate(blocks)
           if any(json.loads(r).get("action") == "mmt_look" for r in b)]
    assert idx, "示范里必须有 mmt_look 那一轮"
    for i in idx:
        assert i + 1 < len(blocks), "翻到之后要接着说（下一块）"
        nxt = [json.loads(r) for r in blocks[i + 1]]
        assert nxt and all("text" in o for o in nxt), \
            f"翻到之后那一块应当全是话: {nxt}"
    print("    line-schema: look 收在一块末尾 + 紧跟一块全是话（两跳的形状）")


def test_without_examples_keeps_rules_and_actions():
    brief = build_line_schema(build_mmt_registry(), with_examples=False)
    full = build_line_schema(build_mmt_registry())
    assert len(brief) < len(full)
    assert "硬规则" in brief and "可用操作" in brief
    assert "mmt_trigger_bond_story" in brief
    assert not _example_lines(brief)
    print(f"    line-schema: 关示例 {len(brief)} < 全量 {len(full)} 字符（规则与动作表仍在）")
