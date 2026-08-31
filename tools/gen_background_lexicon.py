#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""gen_background_lexicon — 背景词表初稿生成器（目录驱动 + 本地 VLM 打标）。

设计定稿（2026-09-01, 背景决定策略）:
    - **目录 = 场景组织层**: assets/background/BG_XXX/ 每目录一场景（变体在目录内）。
      目录保留（组织/管理/变体归属）, 不参与运行时查询。
    - **词表 = 运行时唯一查询层**: assets/_background_lexicon.json——
      语义名/别名/类别/变体 → scene_id。place 标注 LLM 选词 → 直查命中。
    - **变体（白天/夜晚）**: 目录内文件名派生（VARIANT_TOKENS 白名单）;
      词表记 variants + 变体别名（park_night → park+night）——精确时刻查询用。
    - **退火链（查询不到降级）**:
        scene_id 直查 → 变体别名 → 语义名/别名 → 目录名 fuzzy（子串双向）
        → None（调用方: 保持上一场 / default, 不阻断剧情）。

VLM 打标（可选）: 本地 LM Studio Qwen2.5-VL——每场景代表图 → {中文名, 类别, tags}。
服务器不可用/打标失败 → 骨架条目（name 空, 进"待细化清单"）, 不阻塞。
断点续跑: 输出 json 已存在 → 只补标缺失 name 的条目。

用法:
    python tools/gen_background_lexicon.py              # 全量（VLM 打标, 断点续跑）
    python tools/gen_background_lexicon.py --limit 5    # 只处理前 N 个目录（验证打标质量）
    python tools/gen_background_lexicon.py --skip-vlm   # 纯骨架（不开服务器）
    python tools/gen_background_lexicon.py --query "夜晚的公园"   # 测试查询退火链
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# 项目根（tools/gen_background_lexicon.py → Live2Be）
ROOT = Path(__file__).resolve().parent.parent
BG_ROOT = ROOT / "assets" / "background"
OUT_PATH = ROOT / "assets" / "_background_lexicon.json"

# 本地视觉模型（LM Studio, 同 tools/imgdesc.py）
BASE_URL = "http://localhost:1234/v1"
VLM_MODEL = "qwen2.5-vl-7b-instruct"
LMS = r"C:\Users\johnf\.lmstudio\bin\lms.exe"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
# 目录名 → scene_id（camelCase → snake_case; 逻辑同 core/media/background.py::_snake）
_CAMEL_SPLIT = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])"
    r"|(?<=[A-Z])(?=[A-Z][a-z])"
    r"|(?<=[a-zA-Z])(?=[0-9])"
)


def _snake(name: str) -> str:
    """camelCase → snake_case（数字边界也切: ClassRoom2 → class_room_2）。"""
    return _CAMEL_SPLIT.sub("_", name).lower()


def derive_scene_id(dir_name: str) -> str:
    """目录名 → scene_id: BG_Park_ → park; BG_CS_Abydos_ → cs_abydos。"""
    base = dir_name[3:] if dir_name.startswith("BG_") else dir_name
    return _snake(base.strip("_"))


# 时刻类变体（白天/夜晚语义, 与状态类变体区分——词表渲染/提示用）
TIME_VARIANTS = frozenset({
    "night", "sunset", "dawn", "day", "fineday", "cloudy", "rain", "fog",
})
# 变体白名单（文件名派生, 同 core/media/background.py::VARIANT_TOKENS）
_VARIANT_TOKENS = frozenset({
    "night", "sunset", "ruin", "erode", "blur", "dark", "off",
    "fineday", "cloudy", "rain", "fog", "dawn", "day", "fire",
    "tent", "sky", "fake", "party", "alert",
})


def derive_variant(stem: str) -> tuple[str, str | None]:
    """文件名 → (scene_id, variant)（同 core/media/background.py::derive_background）。"""
    base = stem[3:] if stem.startswith("BG_") else stem
    if "_" in base:
        head, _, tail = base.rpartition("_")
        if tail.lower() in _VARIANT_TOKENS:
            return _snake(head), tail.lower()
    return _snake(base), None


# ---------------------------------------------------------------------------
# 本地 VLM（结构化打标; 服务器不可用 → 降级骨架）
# ---------------------------------------------------------------------------

def server_alive(timeout=3) -> bool:
    try:
        req = urllib.request.Request(f"{BASE_URL}/models")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def start_server(max_wait=60) -> bool:
    print(f"[gen] 本地模型服务器未启动, 尝试启动: {LMS} server start", file=sys.stderr)
    try:
        subprocess.run([LMS, "server", "start"], capture_output=True, timeout=30)
    except Exception as e:
        print(f"[gen] 启动失败: {e}", file=sys.stderr)
        return False
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if server_alive(2):
            return True
        time.sleep(2)
    return False


CATEGORIES = "学园/都市/自然/室内/设施/战斗/特殊"

_TAG_PROMPT = (
    "你是一名背景美术分类助手。看图后输出**严格 JSON**（不要任何其他文字）:\n"
    '{"name": "2~6字中文场景名", "category": "类别", "tags": ["3个中文标签"]}\n'
    f"category 只能从: {CATEGORIES} 里选。\n"
    "name 用玩家能懂的中文（如 公园/教学楼走廊/海边沙滩）; tags 描述画面特征"
    "（如 树木、黄昏、课桌椅）。图片是二次元游戏背景, 没有人物。"
)


def describe_with_vlm(image_path: Path) -> dict | None:
    """VLM 打标一张背景图 → {name, category, tags} | None（失败降级）。"""
    from openai import OpenAI
    try:
        b64 = base64.b64encode(image_path.read_bytes()).decode()
        client = OpenAI(base_url=BASE_URL, api_key="lm-studio")
        resp = client.chat.completions.create(
            model=VLM_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": _TAG_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]}],
            max_tokens=200,
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return None
        data = json.loads(m.group(0))
        name = str(data.get("name", "")).strip()
        cat = str(data.get("category", "")).strip()
        tags: list[str] = []
        for t in (data.get("tags") or []):          # 容忍 VLM 用顿号/逗号塞多项
            for part in re.split(r"[、,，]", str(t)):
                part = part.strip()
                if part and part not in tags:
                    tags.append(part)
        if not name:
            return None
        if cat not in CATEGORIES.split("/"):
            cat = ""
        return {"name": name, "category": cat, "tags": tags[:3]}
    except Exception as e:
        print(f"[gen] VLM 打标失败 {image_path.name}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# 扫描 + 建表
# ---------------------------------------------------------------------------

def scan_dirs(limit: int | None = None) -> tuple[list[dict], list[str]]:
    """扫描目录 → **文件粒度**条目（catalog 的 scene_id 是文件名派生的——
    目录是大区域分组, 具体场景在文件: BG_Abydos/ 内含 council_room/residence…）。
    同 scene_id 多变体合并为一条; 代表图 = 默认变体优先。跳过非 BG_ 目录。
    """
    skipped: list[str] = []
    by_sid: dict[str, dict] = {}
    for d in sorted(BG_ROOT.iterdir()):
        if not d.is_dir():
            continue
        if not d.name.startswith("BG_"):
            skipped.append(d.name)
            continue
        for p in sorted(d.iterdir()):
            if not p.is_file() or p.suffix.lower() not in _IMAGE_EXTS:
                continue
            sid, var = derive_variant(p.stem)
            e = by_sid.setdefault(sid, {
                "scene_id": sid, "dirs": [], "variants": [], "repr": None,
            })
            if d.name not in e["dirs"]:
                e["dirs"].append(d.name)
            if var and var not in e["variants"]:
                e["variants"].append(var)
            if e["repr"] is None and var is None:
                e["repr"] = p
            elif e["repr"] is None:
                e["repr"] = p
    entries = sorted(by_sid.values(), key=lambda e: e["scene_id"])
    if limit:
        entries = entries[:limit]
    return entries, skipped


def load_existing() -> dict | None:
    """读旧词表（断点续跑: 只补标缺失 name 的条目）。"""
    if not OUT_PATH.is_file():
        return None
    try:
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_lexicon(entries, use_vlm: bool, limit: int | None) -> tuple[dict, dict]:
    """建表: 骨架 + VLM 打标（断点续跑）→ (lexicon, 报告)。"""
    existing = load_existing()
    old_scenes = (existing or {}).get("scenes", {})
    scenes: dict = {}
    todo: list[str] = []          # 待细化（无 name）
    mismatched: list[str] = []    # 目录派生 vs 文件名派生不一致
    tagged = 0

    for e in entries:
        sid = e["scene_id"]
        old = old_scenes.get(sid, {})
        # 骨架（文件派生 + 目录分组 + 变体）
        scene = {
            "dirs": e["dirs"],
            "name": old.get("name", ""),
            "category": old.get("category", ""),
            "tags": old.get("tags", []),
            "variants": e["variants"],
            "time_variants": [v for v in e["variants"] if v in TIME_VARIANTS],
            "variant_aliases": {f"{sid}_{v}": v for v in e["variants"]},
            "alias": old.get("alias", []),
        }
        # VLM 打标（仅缺失 name 的条目——断点续跑）
        if use_vlm and not scene["name"]:
            meta = describe_with_vlm(e["repr"])
            if meta:
                scene["name"] = meta["name"]
                scene["category"] = meta["category"]
                scene["tags"] = meta["tags"]
                tagged += 1
            else:
                todo.append(f"{sid} (dirs={','.join(e['dirs'])}, VLM 未标)")
        if not scene["name"]:
            todo.append(f"{sid} (dirs={','.join(e['dirs'])}, 未标)")
        scenes[sid] = scene

    # default 校验（保底背景必须真实存在）
    default = (existing or {}).get("default", "campus")
    if default not in scenes:
        candidates = [s for s in scenes if s in ("campus", "school_ground", "park")]
        default = candidates[0] if candidates else (sorted(scenes)[0] if scenes else "")
        print(f"[gen] default 修正: 原 default 不存在 → {default or '（无场景!）'}")

    lexicon = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(),
        "default": default,
        "scenes": scenes,
    }
    report = {
        "total_scenes": len(entries),
        "tagged": tagged,
        "todo": todo,
        "mismatched": mismatched,
        "skipped": skipped_dirs,
    }
    return lexicon, report


# ---------------------------------------------------------------------------
# 查询退火链（运行时用——脚本内自带, 供 --query 测试）
# ---------------------------------------------------------------------------

def query(lexicon: dict, text: str) -> dict | None:
    """退火链: scene_id 直查 → 变体别名 → 语义名/别名 → 目录名 fuzzy → None。

    返回 {"scene_id", "variant"} | None（None = 调用方保持上一场/default）。
    """
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    scenes = lexicon.get("scenes", {})

    if low in scenes:                                       # ① 精确 scene_id
        return {"scene_id": low, "variant": None}
    for sid, s in scenes.items():                           # ② 变体别名 park_night
        va = s.get("variant_aliases", {})
        if low in va:
            return {"scene_id": sid, "variant": va[low]}
    for sid, s in scenes.items():                           # ③ 语义名/别名
        names = [s.get("name", "")] + list(s.get("alias", []))
        for n in names:
            if n and n.strip().lower() == low:
                return {"scene_id": sid, "variant": None}
    best, best_len = None, 0                                # ④ fuzzy 双向子串
    for sid, s in scenes.items():
        hay = " ".join([
            s.get("name", ""), *s.get("alias", []),
            sid.replace("_", " "), s.get("dir", "").replace("_", " "),
        ]).lower()
        if low in hay and len(low) > best_len:
            best, best_len = (sid, None), len(low)
        for n in [s.get("name", "")] + list(s.get("alias", [])):
            if n and n.strip().lower() in low and len(n.strip()) > best_len:
                best, best_len = (sid, None), len(n.strip())
    return {"scene_id": best[0], "variant": best[1]} if best else None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    global skipped_dirs
    ap = argparse.ArgumentParser(description="背景词表初稿生成器（目录驱动 + VLM 打标）")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 个目录（验证用）")
    ap.add_argument("--skip-vlm", action="store_true", help="纯骨架（不开 VLM）")
    ap.add_argument("--query", help="测试查询退火链后退出")
    args = ap.parse_args()

    if args.query:
        lex = load_existing()
        if not lex:
            print("[gen] 词表不存在, 先运行生成。")
            sys.exit(1)
        print(f"query({args.query!r}) → {query(lex, args.query)}")
        return

    if not BG_ROOT.is_dir():
        print(f"[gen] 背景目录不存在: {BG_ROOT}")
        sys.exit(2)

    entries, skipped_dirs = scan_dirs(args.limit)
    print(f"[gen] 扫描 {len(entries)} 个场景目录（跳过 {len(skipped_dirs)} 个非 BG_ 目录: "
          f"{', '.join(skipped_dirs) or '无'}）")

    use_vlm = not args.skip_vlm
    if use_vlm and not server_alive():
        use_vlm = start_server()
        if not use_vlm:
            print("[gen] VLM 不可用 → 纯骨架（name 空, 进待细化清单）")

    lexicon, report = build_lexicon(entries, use_vlm, args.limit)
    OUT_PATH.write_text(json.dumps(lexicon, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"[gen] 已写出: {OUT_PATH}（{len(lexicon['scenes'])} 条, 本次 VLM 新标 {report['tagged']}）")

    if report["todo"]:
        print(f"\n[待细化] {len(report['todo'])} 条（补中文名/别名/类别）:")
        for t in report["todo"][:30]:
            print(f"  · {t}")
        if len(report["todo"]) > 30:
            print(f"  …共 {len(report['todo'])} 条")
    if report["mismatched"]:
        print(f"\n[命名不一致] 目录派生 vs 文件名派生（需人工确认）:")
        for m in report["mismatched"][:10]:
            print(f"  · {m}")
    print(f"\n[default] {lexicon['default']}")
    print("\n[下一步] 细化 json（name/alias/category/tags）→ place 标注通道接线后直接使用。")


if __name__ == "__main__":
    main()
