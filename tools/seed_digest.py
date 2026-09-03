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


# ---------------------------------------------------------------------------
# 2.4 产物校验: 硬错误（拒绝落盘）/ 软警告（第三人称残留提示）
# ---------------------------------------------------------------------------

def validate_entry(entry: dict, source_key: str, aliases: tuple[str, ...],
                   ) -> tuple[list[str], list[str]]:
    """校验单条改编产物。

    Returns: (errors, warnings)——errors 非空 = 该条不合格（不写盘, --only 重跑）;
    warnings = 第三人称自指残留等质量问题（提示, 仍落盘待作者 review）。
    """
    errors: list[str] = []
    warnings: list[str] = []

    got_sk = str(entry.get("source_key") or "").strip()
    if got_sk != source_key:
        errors.append(f"source_key 回填不一致: 期望 {source_key!r}, 实得 {got_sk!r}")
    narration = str(entry.get("narration") or "").strip()
    if not narration:
        errors.append("narration 为空")
    title = str(entry.get("title") or "").strip()
    if not title:
        errors.append("title 为空")
    sig = entry.get("significance")
    if sig is None:
        errors.append("significance 缺失")
    else:
        try:
            sigf = float(sig)
            if not 0 <= sigf <= 1:
                errors.append(f"significance 越界: {sig!r}")
        except (TypeError, ValueError):
            errors.append(f"significance 非数字: {sig!r}")
    for key in ("verbatim", "author_notes"):
        v = entry.get(key)
        if v is not None and not isinstance(v, str):
            errors.append(f"{key} 必须是字符串: {type(v).__name__}")
    extra = set(entry) - {"source_key", "title", "narration", "verbatim",
                          "significance", "author_notes"}
    if extra:
        warnings.append(f"多余键（忽略）: {sorted(extra)}")

    # 软校验: 第一人称记忆里出现角色名 = 第三人称残留嫌疑
    if narration:
        hit = [a for a in aliases if len(a) >= 2 and a in narration]
        if hit:
            warnings.append(
                f"narration 含角色名（{', '.join(hit)}）——疑似第三人称未转'我'; "
                f"若为引语内转述可忽略, 请 review")
    return errors, warnings


def char_aliases(char_id: str) -> tuple[str, ...]:
    """角色名变体（第三人称残留检测用）: 显示名全称（含空格保留）+ other_names 拆分。"""
    ch = CharacterLoader(CHARACTERS_ROOT).load(char_id, strict=False)
    names: list[str] = []
    for key in ("REQ~most_called_name", "other_names"):
        raw = ch.profile.get(key)
        if not raw:
            continue
        text = str(raw)
        if key == "REQ~most_called_name" and text.strip():
            names.append(text.strip())                # 全名原样（含空格）
        for part in text.replace("，", ",").replace(" ", ",").split(","):
            part = part.strip()
            if part:
                names.append(part)
    return tuple(dict.fromkeys(names))


# ---------------------------------------------------------------------------
# 2.5 写 brain_seed.yml（作者可读可改; 已存在防覆盖, --force 先 .bak）
# ---------------------------------------------------------------------------

def _yaml_scalar(value: str) -> str:
    """YAML 双引号标量（json.dumps 转义与 YAML 双引号兼容——任意文本安全）。"""
    import json
    return json.dumps(str(value), ensure_ascii=False)


def write_brain_seed(char_id: str, entries: list[dict], force: bool,
                     generated_at: str) -> Path:
    """写 brain_seed.yml（初稿——作者 review 手改后定稿）。

    episodes[]: source_key/title/narration/verbatim(可选)/significance;
    review_notes[]: source_key + author_notes（剥离的点评句——beliefs 素材, 不落库）。
    已存在且非 force → FileExistsError; force → 旧文件改名 .bak。
    """
    out = _char_dir(char_id) / OUT_NAME
    if out.exists():
        if not force:
            raise FileExistsError(
                f"{out} 已存在（作者手改过的定稿?）——重跑会覆盖 review 内容; "
                f"确认要重新生成请加 --force（旧文件自动备份 .bak）")
        bak = out.with_suffix(".yml.bak")
        out.rename(bak)
        print(f"旧文件已备份: {bak.name}")

    lines = [
        "# 出厂经历定稿（tools/seed_digest.py 生成——LLM 初稿, 请 review 后手改才算定稿）",
        f"# 生成时间: {generated_at}; 来源: experience.yml（逐条改编, 人设锚注入）",
        "# 手改后不要重跑（重跑需 --force, 旧版自动备份 .bak）。narration 保持第一人称;",
        "# 若把 review_notes 的点评句写进 beliefs.yml, links 引用下方对应 source_key 即可。",
        "episodes:",
    ]
    for e in entries:
        lines.append(f"  - source_key: {_yaml_scalar(e['source_key'])}")
        lines.append(f"    title: {_yaml_scalar(e.get('title', ''))}")
        lines.append(f"    narration: {_yaml_scalar(e.get('narration', ''))}")
        if e.get("verbatim"):
            lines.append(f"    verbatim: {_yaml_scalar(e['verbatim'])}")
        lines.append(f"    significance: {float(e['significance'])}")
    notes = [(e["source_key"], e.get("author_notes"))
             for e in entries if e.get("author_notes")]
    if notes:
        lines.append("#")
        lines.append("# 作者点评句（beliefs.yml 素材——不落库, 仅供你取材; 出处见 source_key）")
        lines.append("review_notes:")
        for sk, note in notes:
            lines.append(f"  - source_key: {_yaml_scalar(sk)}")
            lines.append(f"    note: {_yaml_scalar(note)}")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="出厂经历改编工具（brain_seed 定稿制）")
    ap.add_argument("--char", required=True, help="角色目录名（config/characters/ 下）")
    ap.add_argument("--dry", action="store_true",
                    help="只列出待改编清单（source_key + 字数 + 人设锚/称谓表预览）")
    ap.add_argument("--only", default="", metavar="SOURCE_KEY",
                    help="只改编指定 source_key（失败单条重跑用; 不写盘仅当校验未过）")
    ap.add_argument("--force", action="store_true",
                    help="brain_seed.yml 已存在时覆盖（旧文件自动备份 .bak）")
    args = ap.parse_args()

    if not _char_dir(args.char).exists():
        sys.exit(f"角色目录不存在: {_char_dir(args.char)}")

    leaves = load_experience_leaves(args.char)
    if args.only:
        keep = [item for item in leaves if item[0] == args.only]
        if not keep:
            available = ", ".join(sk for sk, _ in leaves)
            sys.exit(f"--only 的 source_key 不存在: {args.only}（可用: {available}）")
        leaves = keep
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
    ch = CharacterLoader(CHARACTERS_ROOT).load(args.char, strict=False)
    name = str(ch.profile.get("REQ~most_called_name") or args.char)
    aliases = char_aliases(args.char)

    entries, failed = adapt_all(client, args.char, name, leaves)

    # 2.4 校验: 硬错误 → 不合格清单; 软警告 → 打印提示（仍落盘, 作者 review）
    ok_entries: list[dict] = []
    bad: list[str] = []
    for e in entries:
        sk = str(e.get("source_key") or "?").strip()
        errors, warnings = validate_entry(e, sk, aliases)
        for w in warnings:
            print(f"  ~ {sk} 软警告: {w}")
        if errors:
            bad.append(sk)
            for err in errors:
                print(f"  ✗ {sk} 不合格: {err}")
        else:
            ok_entries.append(e)
    if bad:
        print(f"校验未过 {len(bad)} 条: {bad}——可用 --only <source_key> 单条重跑")

    if not ok_entries:
        print("没有合格产物——不写盘")
        return
    try:
        from datetime import datetime
        out = write_brain_seed(args.char, ok_entries, force=args.force,
                               generated_at=datetime.now().isoformat(timespec="seconds"))
    except FileExistsError as e:
        sys.exit(f"{e}")
    notes = sum(1 for e in ok_entries if e.get("author_notes"))
    print(f"\n✅ 初稿已写: {out}")
    print(f"   {len(ok_entries)} 条 episode / {notes} 条点评句(review_notes)"
          f" / {len(failed) + len(bad)} 条待重跑")
    print("   请 review 手改后定稿; 点评句是 beliefs.yml 素材（出处见 review_notes.source_key）")


if __name__ == "__main__":
    main()
