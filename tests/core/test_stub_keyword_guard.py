# -*- coding: utf-8 -*-
"""守门: **测试桩依赖的中文关键字**, 必须仍由产品侧的源真实产出。

## 为什么需要这条（ARCH_REVIEW P2-8 的廉价解）

各测试文件的 `ScriptedLLM` 是按**中文关键字**认任务的（`情绪标签` / `变更句数组` /
`地点 id JSON` / `选中的文件名` / `记录员` / `整理者`），而这些串全部由产品侧的
**user 消息代码或 prompt 模板**产出。于是：**谁改一次措辞，桩就静默不命中**——
轻则标注调用吞掉一个场景脚本（后续断言以奇怪的方式挂），重则一路走兜底路径
**还全绿**（同类事故已发生过一次: 桩曾用 `^\\d+: ` 数 system 行, 模板【示范】也带
编号行 → 恒多 4 条 → 全程兜底不报错, 见 CLAUDE.md §4 与 §11）。

这条用例把"关键字 ↔ 产出它的源"钉成一张表: 源里没了这个串 → **直接红**,
并且红的时候告诉你该去哪儿改。

## 与节点 5b 的关系

这是 **5b（`task=` 元数据）的廉价前置**：它只保证"串还在"，不解决"桩分支顺序 /
新任务忘了补桩 / 生产日志分不清调用方"——那三件仍归 5b
（`docs/EXEC_PIPELINE_UNIFY.md`）。做了 5b 之后, 这张表可以整体删掉。

运行: python -m pytest tests/core/test_stub_keyword_guard.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent

#: 桩依赖的**中文关键字** → 产出它的源文件（相对项目根）。
#:
#: ⚠️ **改这些源里的串 = 让桩静默不命中**。真要改文案时, 两件事一起做:
#: ① 同步改所有测试文件里的桩分支; ② 改这张表。或者干脆做 5b（`task=`）。
STUB_KEYWORD_SOURCES: dict[str, tuple[str, ...]] = {
    # 记录级情绪标注 / v1 整场批标 —— 桩据此回 "nomal" 数组
    "情绪标签": ("core/bond/emo_text.py", "core/bond/emotion_annotate.py"),
    # 句级锚点（place 标注第二路）—— 桩据此回 []
    "变更句数组": ("core/bond/place_annotate.py",),
    # 板级换场翻译 —— 桩据此回 {"place": ""}
    "地点 id JSON": ("core/bond/place_annotate.py",),
    # 选图（第二遍）—— 桩据此回 {"image": ""}
    "选中的文件名": ("core/bond/variant_annotate.py",),
    # digest 两轮（Round A 记录员 / Round B 整理者）—— 桩据此回空包
    "记录员": ("llm/prompts/digest_v2_round_a.md", "core/brain/wiki_v2/digest.py"),
    "整理者": ("llm/prompts/digest_v2_round_b.md",),
}

#: 情绪标注的**条数口径**（桩用正则 `恰 (\d+) 项` 从 user 里取 N, **不用** system
#: 的 `^\d+: ` 编号行——模板【示范】也带编号行会恒多 4 条, 那次事故就是这么来的）。
#: 产出侧是**拼串**（`'（恰 ' + str(n) + ' 项）'`），所以按片段守、不按整串。
COUNT_CONVENTION = {
    "source": "core/bond/emo_text.py",
    "source_fragments": ("恰 ", " 项）"),
    "stub_literal": r"恰 (\d+) 项",          # 测试文件里应出现这个正则字面量
}


def _drifted(keywords=None, count=None, read=None) -> list[str]:
    """返回"关键字/口径已不在其源里"的清单（空 = 没漂）。

    抽成函数是为了**能被自测**——守门用例自己必须证明它会红（见最后一条用例）。
    """
    table = STUB_KEYWORD_SOURCES if keywords is None else keywords
    conv = COUNT_CONVENTION if count is None else count
    reader = read or (lambda rel: (ROOT / rel).read_text(encoding="utf-8"))
    out: list[str] = []

    def _read(rel: str) -> str | None:
        try:
            return reader(rel)
        except OSError:
            out.append(f"{rel}（文件不存在）")
            return None

    for kw, sources in table.items():
        assert sources, f"{kw!r} 没有登记源文件"
        for rel in sources:
            text = _read(rel)
            if text is not None and kw not in text:
                out.append(f"{kw} ← {rel}")
    text = _read(conv["source"]) if conv else None
    if text is not None:
        for frag in conv["source_fragments"]:
            if frag not in text:
                out.append(f"条数口径片段 {frag!r} ← {conv['source']}")
    return out


def _test_sources() -> dict[Path, str]:
    files = [p for p in (ROOT / "tests").rglob("test_*.py")
             if p.name != Path(__file__).name]
    return {p: p.read_text(encoding="utf-8") for p in files}


def test_stub_keywords_still_produced_by_product_sources():
    """主判据: 表里每个关键字都仍由声明的源产出（否则测试桩正在静默失效）。"""
    drifted = _drifted()
    assert not drifted, (
        "以下关键字/口径在产品源里已不存在 —— 测试桩会静默不命中（要么回错误的"
        "数据, 要么一路走兜底路径还全绿）:\n  " + "\n  ".join(drifted) + "\n"
        "修法: ① 同步改测试文件里所有桩分支; ② 改本文件的 STUB_KEYWORD_SOURCES / "
        "COUNT_CONVENTION。（根治 = EXEC_PIPELINE_UNIFY 节点 5b: llm.chat 加 task=。）")
    print(f"    stub-guard: {len(STUB_KEYWORD_SOURCES)} 个关键字 + 条数口径未漂")


def test_every_entry_is_actually_used_by_a_stub():
    """反向判据: 表不能腐烂——每个关键字/口径至少还被一个测试文件用着。

    （桩改完分派方式后忘了删表 → 这条会红, 提醒把死条目清掉。）
    """
    texts = list(_test_sources().values())
    orphans = [kw for kw in STUB_KEYWORD_SOURCES
               if not any(kw in t for t in texts)]
    if not any(COUNT_CONVENTION["stub_literal"] in t for t in texts):
        orphans.append(COUNT_CONVENTION["stub_literal"])
    assert not orphans, f"这些条目已没有测试在用, 请从表里删掉: {orphans}"


def test_guard_can_actually_fail():
    """守门用例必须**真的会红**——否则它只是装饰（自测: 喂一个被改过的源）。"""
    fake = {"情绪标签": ("core/bond/emo_text.py",)}
    fake_conv = {"source": "core/bond/emo_text.py",
                 "source_fragments": ("恰 ", " 项）")}
    assert _drifted(fake, fake_conv,
                    read=lambda rel: "（改过的文案，不含那个关键字）") == \
        ["情绪标签 ← core/bond/emo_text.py",
         "条数口径片段 '恰 ' ← core/bond/emo_text.py",
         "条数口径片段 ' 项）' ← core/bond/emo_text.py"]
    assert _drifted(fake, fake_conv, read=lambda rel: "请输出情绪标签（恰 3 项）") == []
    # 文件不存在/改名 = 一样的失效
    def _boom(rel):
        raise OSError()

    assert _drifted(fake, None, read=_boom) == \
        ["core/bond/emo_text.py（文件不存在）", "core/bond/emo_text.py（文件不存在）"]
    print("    stub-guard: 守门本身可失败（自测通过）")
