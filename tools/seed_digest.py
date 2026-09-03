#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seed_digest.py — 出厂经历改编工具（brain_seed 定稿制, TODO 阶段 2）。

把 config/characters/{char}/experience.yml 的预设经历**逐条**交给 LLM
（llm/prompts/seed_digest.md, 人设锚三段注入）改编成第一人称 episode 记忆,
产物 = config/characters/{char}/brain_seed.yml（**初稿**——作者 review 手改后
才算定稿; 工具防覆盖, 重跑需 --force）。

用法:
    python tools/seed_digest.py --char igusa_haruka --dry     # 预览待改编清单
    python tools/seed_digest.py --char igusa_haruka           # 全量逐条改编
    python tools/seed_digest.py --char igusa_haruka --force   # 重跑（覆盖手改前先备份? 不——
                                                              #   覆盖前把旧文件改名 .bak）
    python tools/seed_digest.py --char igusa_haruka --only self.regular.1   # 单条重跑

设计（TODO.md 出厂定稿管线）: 出厂经历是"定死的"——改编是一次定稿动作
（逐条调用保质量 + 人设锚注入, 避免批量敷衍/无角色口吻）, 之后引擎 seed
只做确定性复制（阶段 3）。产物结构:
    episodes[]:   source_key/title/narration/verbatim(可选)/significance
    review_notes[]: source_key + 剥离的作者点评句（beliefs.yml 素材, 不落库）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.brain.wiki_v2.seed import _collect_leaves            # noqa: E402  复用 yml walker
from core.parsing.dynamic_character_parser import (            # noqa: E402
    CharacterLoader, load_yaml_file, yaml_to_prompt)

CHARACTERS_ROOT = ROOT / "config" / "characters"
PROMPT_PATH = ROOT / "llm" / "prompts" / "seed_digest.md"
OUT_NAME = "brain_seed.yml"


# ---------------------------------------------------------------------------
# 2.1 读卡: experience 叶子 + 人设锚渲染（profile/personality）
# ---------------------------------------------------------------------------

def _char_dir(char_id: str) -> Path:
    return CHARACTERS_ROOT / char_id


def load_experience_leaves(char_id: str) -> list[tuple[str, str]]:
    """experience.yml → [(source_key, 原文全文), …]（复用 seed._collect_leaves）。"""
    p = _char_dir(char_id) / "experience.yml"
    if not p.exists():
        raise FileNotFoundError(f"缺 experience.yml: {p}")
    data = load_yaml_file(p)
    leaves = _collect_leaves(data)
    if not leaves:
        raise ValueError(f"experience.yml 没有可改编的经历条目: {p}")
    return leaves


def render_character_anchor(char_id: str) -> str:
    """人设锚（prompt 的 {{char_profile}}/{{char_personality}} 素材）:
    profile 全量 + personality 全量（yaml_to_prompt 剥 REQ~/SIG~ 前缀）。"""
    loader = CharacterLoader(CHARACTERS_ROOT)
    ch = loader.load(char_id, strict=False)
    parts = [yaml_to_prompt(ch.profile, "角色档案"),
             yaml_to_prompt(ch.personality, "性格与口吻")]
    return "\n\n".join(p for p in parts if p.strip())


def render_name_table(char_id: str) -> str:
    """人物称谓表: knowledge.yml 的 friends 段（剥前缀后 == friends 的 dict）。

    每行 `- {人物key}: {文本}`——文本即人物档案 + 称谓线索（"即陆八魔阿露……
    尊称她阿露大人"）。LLM 据此按角色口吻称呼人物, 不猜。无 friends → ""。
    """
    loader = CharacterLoader(CHARACTERS_ROOT)
    ch = loader.load(char_id, strict=False)
    friends: dict | None = None
    for k, v in ch.knowledge.items():
        if k.lstrip("REQ~SIG~").lstrip("~") == "friends" and isinstance(v, dict):
            friends = v
            break
    if not friends:
        return ""
    lines: list[str] = []
    for name, desc in friends.items():
        text = str(desc).strip().replace("\n", " ")
        lines.append(f"- {name}: {text}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="出厂经历改编工具（brain_seed 定稿制）")
    ap.add_argument("--char", required=True, help="角色目录名（config/characters/ 下）")
    ap.add_argument("--dry", action="store_true",
                    help="只列出待改编清单（source_key + 字数）, 不调 LLM")
    args = ap.parse_args()

    if not _char_dir(args.char).exists():
        sys.exit(f"角色目录不存在: {_char_dir(args.char)}")

    leaves = load_experience_leaves(args.char)
    total_chars = sum(len(t) for _, t in leaves)
    print(f"{args.char}: {len(leaves)} 条预设经历（共 {total_chars} 字）→ brain_seed.yml 初稿")
    for sk, text in leaves:
        print(f"  - {sk}  ({len(text)} 字)  {text[:24].replace(chr(10), ' ')}…")

    if args.dry:
        table = render_name_table(args.char)
        print(f"\n人设锚: {len(render_character_anchor(args.char))} 字")
        print(f"称谓表 ({table.count(chr(10)) + 1 if table else 0} 人):")
        print(table or "（无 friends 段——称谓表为空）")
        return
    # 2.3+ 阶段: 逐条 LLM 改编 → 校验（2.4）→ 写 brain_seed.yml（2.5）
    print("（改编管线 2.3-2.5 未接入——本文件按子阶段增量构建）")


if __name__ == "__main__":
    main()
