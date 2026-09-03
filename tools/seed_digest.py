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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.brain.wiki_v2.seed import _collect_leaves            # noqa: E402  复用 yml walker
from core.parsing.dynamic_character_parser import (            # noqa: E402
    CharacterLoader, load_yaml_file, yaml_to_prompt)
from llm.client import LLMClient                               # noqa: E402

CHARACTERS_ROOT = ROOT / "config" / "characters"
PROMPT_PATH = ROOT / "llm" / "prompts" / "seed_digest.md"
OUT_NAME = "brain_seed.yml"

#: 改编温度（低——有原文锚的转换任务, 求稳不求花样）
TEMP = 0.3
#: 单条失败外层重试次数（client json_object 内建提取修正之外）
RETRIES = 2


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


# ---------------------------------------------------------------------------
# 2.3 prompt 组装 + 逐条 LLM 改编（temp 低 / 失败重试 ×2 / 单条失败不阻塞）
# ---------------------------------------------------------------------------

def assemble_prompt(char_id: str, char_name: str, source_key: str, text: str) -> str:
    """渲染单条改编 prompt:

    seed_digest.md 的【输入结构】~【输出规格】之间的段落（含占位符说明, 工具端
    契约）整体替换为实际输入块——角色定位/输出规格/规则/示范/纪律保持原文。
    """
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    head, _, rest = raw.partition("【输入结构】")
    _, sep, tail = rest.partition("【输出规格】")
    if not sep:
        raise ValueError("seed_digest.md 结构异常: 缺【输出规格】锚点")
    inputs = (
        "【角色档案与性格】\n"
        + render_character_anchor(char_id)
        + "\n\n【人物称谓表】\n"
        + (render_name_table(char_id) or "（无——按原文称谓, 不猜）")
        + "\n\n【本轮改编目标】\n- source_key: " + source_key + "\n- 原文:\n" + text
    )
    body = head.rstrip() + "\n\n" + inputs + "\n\n【输出规格】" + tail
    body = body.replace("{{char_name}}", char_name)
    body = body.replace("{{name_table}}", "上方【人物称谓表】")
    return body


def adapt_one(client, prompt_text: str) -> dict:
    """单条改编调用（LLM 一次; json_object 内建提取修正; 档位 = task_levels
    seed_digest: medium thinking + 4096）。"""
    from llm import task_levels as tl
    resp = client.chat(
        messages=[{"role": "user", "content": prompt_text}],
        temperature=TEMP,
        max_tokens=tl.max_tokens("seed_digest"),
        response_format="json_object",
        extra_body=tl.extra_body("seed_digest"),
    )
    if not isinstance(resp, dict):
        raise ValueError(f"响应不是 JSON 对象: {str(resp)[:200]}")
    return resp


def adapt_all(client, char_id: str, char_name: str,
              leaves: list[tuple[str, str]]) -> tuple[list[dict], list[str]]:
    """逐条改编（串行, 每条失败重试 RETRIES 次; 单条最终失败 → 跳过记入 failed）。

    Returns: (entries, failed_source_keys)。entries 未经校验（2.4 单独做）。
    """
    results: list[dict] = []
    failed: list[str] = []
    for i, (sk, text) in enumerate(leaves, 1):
        t0 = time.time()
        prompt_text = assemble_prompt(char_id, char_name, sk, text)
        last_err: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                data = adapt_one(client, prompt_text)
                results.append(data)
                break
            except Exception as e:                            # noqa: BLE001
                last_err = e
                print(f"  ⚠ {sk} 第 {attempt + 1} 次失败: {e}")
                time.sleep(1)
        else:
            failed.append(sk)
            print(f"  ✗ {sk} 改编失败（{last_err}）——已跳过, 可用 --only 单独重跑")
            continue
        print(f"  ✓ [{i}/{len(leaves)}] {sk}  ({time.time() - t0:.0f}s)")
    return results, failed


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

    print("连接 LLM（settings.toml [llm] / .env 凭据）…")
    client = LLMClient()
    name = (CharacterLoader(CHARACTERS_ROOT).load(args.char, strict=False)
            .profile.get("REQ~most_called_name") or args.char)
    entries, failed = adapt_all(client, args.char, name, leaves)
    print(f"\n改编完成: {len(entries)} 成功 / {len(failed)} 失败{failed}")
    if failed:
        print("失败条目可用 --only <source_key> 单独重跑（2.6 接入）")
    # 2.4-2.5 阶段: 校验 + 写 brain_seed.yml


if __name__ == "__main__":
    main()
