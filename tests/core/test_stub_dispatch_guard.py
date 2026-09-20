# -*- coding: utf-8 -*-
"""守门: **测试桩按 `task` 身份分派**（节点 5b, 2026-09-21）——三条不变量。

背景（ARCH_REVIEW P2-8）: 桩此前按**中文关键字**认任务（`情绪标签` / `变更句数组` /
`地点 id JSON` / `选中的文件名` / `记录员` / `整理者`）, 而那些串来自 prompt 文案 ⇒
**改一次措辞就让桩静默不命中**（轻则吞脚本, 重则一路兜底还全绿）。现在产品侧在
`llm.chat(..., task=…)` 上声明调用身份（`llm/task_labels.py`）, 桩读 `kw["task"]`。

本文件守三件事:

1. **产品侧每个调用点都带 `task=`**（漏了 → 桩在**那次调用**上直接炸,
   `tests/stub_tasks.py::unknown_task` 的报错会指路; 这里再静态扫一遍兜底）;
2. **产品侧用的标签都在词表里**（新增调用点忘了加常量 → 红）;
3. **测试里不许再有"按中文串分派"**（防漂回旧写法）。

运行: python -m pytest tests/core/test_stub_dispatch_guard.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from llm import task_labels as T  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent

#: 产品侧被扫描的目录（与 `tests/core/test_paths.py` 同一口径: 引擎/壳/客户端）
SCAN_DIRS = ("core", "webgui", "llm")
#: 调用身份的出现形式: `task=CONST` 或 `task="字面量"`
_TASK_ARG = re.compile(r"task\s*=\s*([A-Za-z_][A-Za-z0-9_.]*|\"[^\"]+\")")
#: 桩的调用点: `llm.chat(` / `self.llm.chat_full(` …（排除客户端自身与其测试）
_CALL = re.compile(r"\b(?:self\.)?(?:llm|client)\.chat(?:_full)?\s*\(")
#: 测试里"按中文串分派"的可疑写法（`if "情绪标签" in …`）
_STUB_KEYWORDS = ("情绪标签", "变更句数组", "地点 id JSON", "选中的文件名",
                  "记录员", "整理者")
_KEYWORD_DISPATCH = re.compile(
    r"if\s+[\"'](?:" + "|".join(re.escape(k) for k in _STUB_KEYWORDS) + r")[\"']")


def _iter_py(dirs=SCAN_DIRS):
    for d in dirs:
        yield from (ROOT / d).rglob("*.py")


def _call_span(text: str, open_paren: int) -> str:
    """从 `(` 起配对到闭合 `)` 的那段调用实参文本（跳过字符串/注释里的括号）。"""
    depth = 0
    i = open_paren
    n = len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote:                                  # 字符串里: 只找收尾引号
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "#":                            # 行注释 → 跳到行尾
            i = text.find("\n", i)
            if i < 0:
                break
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren:i + 1]
        i += 1
    return text[open_paren:]


def _prod_call_spans(text: str):
    """产品侧 `.chat(` / `.chat_full(` 的**真实调用**实参文本（跳过字符串/注释里的示例）。"""
    ignore = _string_spans(text)
    for m in _CALL.finditer(text):
        if any(a <= m.start() < b for a, b in ignore):
            continue                               # 文档字符串/注释里的示例代码
        yield text.count("\n", 0, m.start()) + 1, _call_span(text, m.end() - 1)


def _string_spans(text: str) -> list[tuple[int, int]]:
    """字符串与注释 token 的 (start, end) 偏移——`tokenize` 判定, 精确跳过。

    （为什么不用正则: `llm/client.py` 的模块 docstring 与 `digest.py` 的"兼容
    `llm.chat(...)`"说明里都有 `.chat(` 字样, 那是文档不是调用点。）
    """
    import io
    import tokenize

    spans: list[tuple[int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                spans.append((_offset(text, tok.start), _offset(text, tok.end)))
    except (tokenize.TokenError, IndentationError):
        pass                                       # 语法怪 → 尽力而为（不因守门崩掉）
    return spans


def _offset(text: str, pos: tuple[int, int]) -> int:
    line, col = pos
    lines = text.splitlines(keepends=True)
    return sum(len(x) for x in lines[:line - 1]) + col


def _product_calls():
    """产品侧每个 `.chat(` / `.chat_full(` 调用 → (相对路径, 行号, 实参文本)。"""
    for path in _iter_py():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "llm/client.py":                 # 客户端自身: 定义, 不是消费点
            continue
        text = path.read_text(encoding="utf-8")
        for line, span in _prod_call_spans(text):
            yield rel, line, span


def test_every_product_call_site_declares_task():
    """产品侧每个 LLM 调用点都要显式声明调用身份（节点 5b）。"""
    missing = [f"{rel}:{line}" for rel, line, span in _product_calls()
               if "task=" not in span]
    assert not missing, (
        "这些 LLM 调用点没带 `task=` —— 桩会拒绝应答（并指出漏在哪）:\n  "
        + "\n  ".join(missing)
        + "\n修法: 从 `llm/task_labels.py` 挑一个标签, 加到该 `llm.chat(...)` 上。")


def test_product_task_labels_are_declared():
    """产品侧用到的标签必须都在词表里（新增调用点忘了加常量 → 红）。"""
    unknown: list[str] = []
    for rel, line, span in _product_calls():
        for raw in _TASK_ARG.findall(span):
            lit = raw.strip()
            if lit.startswith(("'", '"')):
                value = lit.strip("'\"")
                if value not in T.ALL:
                    unknown.append(f"{rel}:{line} → 字面量 {value!r} 不在词表")
            # 常量名（如 EMOTION / digest_label(label)）不在此静态判定——
            # 值由 `llm/task_labels.py` 定义, 拼错会 ImportError/test 直接红
    assert not unknown, "\n  ".join(unknown)


def test_no_keyword_dispatch_left_in_tests():
    """测试里不许再按中文串分派（把旧写法漂回来 → 红）。"""
    offenders: list[str] = []
    for path in (ROOT / "tests").rglob("*.py"):
        if path.name == Path(__file__).name:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _KEYWORD_DISPATCH.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{i}: {line.strip()}")
    assert not offenders, (
        "以下位置又按 prompt 文案分派了 —— 改文案会让桩静默失效（P2-8）:\n  "
        + "\n  ".join(offenders)
        + "\n修法: 读 `kw.get(\"task\")`（见 `tests/stub_tasks.py` 的用法）。")


def test_stub_helper_rejects_missing_or_unknown_task():
    """运行期兜底: 桩助手对"没带 task"与"未知 task"给出**指路**的报错。

    （静态扫描管"产品侧有没有写"; 这条管"万一漏了, 桩别静默走兜底"。）
    """
    from tests import stub_tasks

    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "请输出情绪标签（恰 3 项）。"}]
    assert stub_tasks.emotion_count(msgs) == 3
    assert stub_tasks.annotation_reply(T.EMOTION, msgs) == ["nomal"] * 3
    assert stub_tasks.annotation_reply(T.PLACE, msgs) == []
    assert stub_tasks.annotation_reply(T.PLACE_VARIANT, msgs) == {"image": ""}
    assert stub_tasks.annotation_reply(T.MMT, msgs) is None      # 主链 → 交给桩自己
    assert "漏了调用身份" in str(stub_tasks.unknown_task(None))
    assert "不认识 task" in str(stub_tasks.unknown_task("nope"))
    print("    stub-guard: 桩助手对缺失/未知 task 都会报错指路")


def test_label_matches_task_levels_vocabulary():
    """每个标签都要映射到 `task_levels.PROFILES` 里真实存在的形态（档位/max_tokens 按它取）。"""
    from llm import task_levels

    assert set(T.PROFILE_OF) == set(T.ALL), (
        f"PROFILE_OF 与 ALL 不一致: 缺 {sorted(set(T.ALL) - set(T.PROFILE_OF))} / "
        f"多 {sorted(set(T.PROFILE_OF) - set(T.ALL))}")
    missing = sorted(set(T.PROFILE_OF.values()) - set(task_levels.PROFILES))
    assert not missing, (
        f"这些形态名在 task_levels.PROFILES 里不存在: {missing}"
        "（要么加形态, 要么改 PROFILE_OF——档位/max_tokens 是按形态取的）")
    print(f"    stub-guard: {len(T.ALL)} 个标签 / 产品调用点全部声明 task=")
