# -*- coding: utf-8 -*-
"""digest 轮次**命名守门** —— 轮名只有一处真源（2026-09-29 乙-2）。

> 用户原话：*"digest 方面的不管过不过 LLM 都加上 digest 前缀吧"* ·
> *"命名要一眼看出归属"*。

## 为什么有它

从前一轮的名字**散在四处**（表里的 `label` / `prompt` / `phase` 三格 + 每条日志的字面量），
改一次 key 要同时改四处, 漏一处就是**静默不一致**: 日志里还写着 `digest_span` / `digest_hit`,
而表里那一步早叫别的了 —— `grep digest_<那一轮>` 就再也拿不全它的日志。

乙-2 之后表里**没有**那三格了（`label` / `prompt` / `phase` 都是 `key` 的 property）;
日志字面量**仍在**轮文件里（把一个日志前缀穿进 `_link_akin` / `_collapse_bond_episodes`
的签名, 噪声比收益大）—— 于是由这两条判据钉住:

  ① **日志第一段若是"轮名形状", 必须是当前轮次的 key** ——
     旧名残留（`digest_span` / `digest_hit` / `digest_a` / `digest_v2_round_a`…）一律红。
     管**全包**（`segment.py` 那种轮外的日志也算 —— 它正是在乙-2 里被抓出来的那一处）。
  ② **轮文件里的日志第一段 = 它自己的轮名** —— `record.py` 里的日志只能叫 `digest_record`;
     轮名从该文件的 `ctx.enter("<key>")` 读出来, 不另写一份映射。

⚠️ 两条**只看日志调用的第一个字面量**（其余字符串常量不扫）—— 判据要精确:
`digest_segment` / `digest_retry` / `digest_schema` / `digest_registry` 这些**不是轮名**,
扫宽了只会把守门变成噪声。⚠️ docstring / 注释不扫（文档必须能引用形状, 同
`test_marks_guard.py` 的取舍）。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from core.digest.rounds import DIGEST_LOG_PREFIX, ROUNDS

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "core" / "digest"
KEYS = frozenset(s.key for s in ROUNDS)
#: 当前轮次的**日志标签**（带前缀的那一种 —— 与 key 本身区分开）
TAGS = frozenset(f"{DIGEST_LOG_PREFIX}{k}" for k in KEYS)

#: 允许的两种"非轮名"日志开头:
#:   · `digest`（不带下划线）= **整条管线级**的日志（放弃这一段 / 第 N 次失败）
#:   · `digest_%s` = **派生**（`spec.name`, 见 `call._log_skip`）
PIPELINE_TAG = "digest"
DERIVED_TAG = f"{DIGEST_LOG_PREFIX}%s"

_ROUND_TAG = re.compile(rf"^{re.escape(DIGEST_LOG_PREFIX)}([a-z_]+)$")


def _pkg_files() -> list[Path]:
    return sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


def _log_first_tokens(path: Path) -> list[tuple[int, str]]:
    """每处 `logger.<level>("…", …)` 的**第一个字面量**取其第一个词（动态拼的不算）。

    末尾的 `:` 剥掉 —— `logger.info("digest_group: %s", w)` 与
    `logger.info("digest_group blocks=%d", …)` 是同一轮的两种写法。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
                and fn.value.id == "logger"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            words = node.args[0].value.split()
            out.append((node.lineno, words[0].rstrip(":") if words else ""))
    return out


def test_log_tags_are_current_round_names():
    """① 日志第一段只要是"轮名形状", 就得是**当前**轮次的 key（全包扫）。"""
    bad: list[str] = []
    for path in _pkg_files():
        for lineno, tag in _log_first_tokens(path):
            if not tag.startswith(DIGEST_LOG_PREFIX):
                continue                               # 不评判（`creep` / `%s` …）
            if tag in (PIPELINE_TAG, DERIVED_TAG) or tag in TAGS:
                continue                               # 管线级 / 派生 / 当前轮名
            m = _ROUND_TAG.match(tag)
            bad.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}  {tag!r}"
                       + ("（旧轮名残留）" if m else "（不是轮名的形状）"))
    assert not bad, (
        "digest 包里的日志打了**非当前**的轮名（改名漏了这一处?）:\n  " + "\n  ".join(bad)
        + f"\n当前轮次 key = {sorted(KEYS)}（真源: core/digest/rounds/__init__.py 的 ROUNDS）")
    print(f"    轮名形状: 日志第一段只出现当前 key {sorted(KEYS)}（+ 管线级 {PIPELINE_TAG!r}）")


def test_round_files_speak_their_own_name():
    """② 每个轮文件里的日志第一段**等于它自己的轮名**（`ctx.enter("<key>")` 说了算）。"""
    bad: list[str] = []
    seen: dict[str, int] = {}
    for path in _pkg_files():
        keys = re.findall(r'ctx\.enter\("([a-z_]+)"\)', path.read_text(encoding="utf-8"))
        if not keys:
            continue                                   # base.py / pipeline.py 不是轮文件
        assert len(set(keys)) == 1, f"{path.name}: 一个文件里进了多个轮的门: {keys}"
        key = keys[0]
        tagged = _log_first_tokens(path)
        seen[key] = len(tagged)
        want = f"{DIGEST_LOG_PREFIX}{key}"
        bad += [f"{path.name}:{lineno}  日志以 {tag!r} 开头, 该是 {want!r}"
                for lineno, tag in tagged if tag != want]
    assert not bad, ("轮文件里的日志打了别人的名字（grep 一轮的日志会漏）:\n  "
                     + "\n  ".join(bad))
    assert set(seen) == KEYS, (
        f"有轮次没有自己的文件（或文件里没进门）: 表={sorted(KEYS)} 实得={sorted(seen)}")
    print("    日志: " + " / ".join(f"{k}={n}条" for k, n in sorted(seen.items())))


if __name__ == "__main__":
    test_log_tags_are_current_round_names()
    test_round_files_speak_their_own_name()
    print("all digest naming guard tests passed")
