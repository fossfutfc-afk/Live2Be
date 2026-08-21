# -*- coding: utf-8 -*-
"""风纪委员会四角色 CLI 完整建档驱动（用户离开期间的自主运行）。

用真实 CLI 引擎（IDEAgent + LLMClient, 同 `python -m ide.ide_agent`）执行:
    - ask 桥: 写动作 auto-approve; 范例询问 skip（不注入范例板块）
    - emit 桥: 事件写入 ide/_cli_run_log.jsonl（追加）+ 控制台摘要
    - 每轮后磁盘校验目标文件; interperson 写后守卫消除 sensei 类字段
    - 遇到的问题记入 ide/_cli_test_log.md（要求 3）

满足用户三项要求:
    1. 测试时名字形式变化（全名/后半/别称，如 大可爱/空崎阳奈 → 空崎日奈）
    2. interperson 出现 sensei 字段则消除
    3. 测试阶段遇到的问题记录

用法:
    python ide/_run_4chars.py 1        # 只跑 1 号角色（空崎日奈）
    python ide/_run_4chars.py --all    # 全部四个
    python ide/_run_4chars.py --verify # 不调 LLM, 只核验现状并汇总
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from llm.client import LLMClient
from ide.ide_agent import IDEAgent, AgentEvent
from ide.ide_events import AgentEventKind

CHAR_DIR = ROOT / "config" / "characters"
INTERPERSON = ROOT / "config" / "settings" / "relation" / "interperson.json"
EVENT_LOG = ROOT / "fetch" / "_cli_run_log.jsonl"
ISSUE_LOG = ROOT / "fetch" / "_cli_test_log.md"
TRANSCRIPT = ROOT / "fetch" / "_cli_run_transcript.txt"

# 要求 2: interperson 中应消除的"玩家/老师"类字段
_SENSEI_KEYS = {"sensei", "player", "user", "teacher", "master", "you",
                "先生", "老师", "玩家"}

# 已知合法角色 id（已有 4 + 本轮新建 4）
_KNOWN_IDS = {"igusa_haruka", "asagi_mutsuki", "onikata_kayoko",
              "rikuhachima_aru", "sorasaki_hina", "amau_ako",
              "ginkyou_iori", "hinomiya_chinatsu"}

CHARACTERS = [
    {"id": "sorasaki_hina", "name": "空崎日奈",
     "keywords": ["日奈", "ヒナ", "sorasaki", "风纪", "格黑娜"],
     "turns": [
        ("profile",
         "帮我为风纪委员会角色「空崎日奈」建档（character_id 用 sorasaki_hina）。"
         "第一步先写 profile.yml：先 search 萌娘百科再写，"
         "REQ~most_called_name 用「空崎 日奈」，en_name 用 Sorasaki Hina，"
         "jp_name 用 空崎 ヒナ。"),
        ("personality", "给「日奈」的档案补上 personality.yml。"),
        ("knowledge", "给「大可爱」补 knowledge.yml。"),
        ("experience", "给「空崎阳奈」补 experience.yml。"),
        ("typical", "给「空崎日奈」最后补 typical.yml。"),
        ("interperson",
         "给 sorasaki_hina 写 interperson 关系（全量快照）：风纪委员会成员 "
         "amau_ako(亚子)、ginkyou_iori(伊织)、hinomiya_chinatsu(千夏)、"
         "igusa_haruka(遥香) 都设 2；便利屋68 的 rikuhachima_aru、"
         "asagi_mutsuki、onikata_kayoko 按打过交道的程度设 1。"
         "注意：只写学生间关系，绝对不要出现 sensei/玩家/老师 字段。"),
     ]},
    {"id": "amau_ako", "name": "天雨亚子",
     "keywords": ["亚子", "アコ", "amau", "风纪", "格黑娜"],
     "turns": [
        ("profile",
         "帮我为风纪委员会角色「天雨亚子」建档（character_id 用 amau_ako）。"
         "第一步先写 profile.yml：先 search 萌娘百科再写，"
         "REQ~most_called_name 用「天雨 亚子」，en_name 用 Amau Ako，"
         "jp_name 用 天雨 アコ。"),
        ("personality", "给「亚子」补上 personality.yml。"),
        ("knowledge", "给「天雨亚子」补 knowledge.yml。"),
        ("experience", "给「亚子」补 experience.yml。"),
        ("typical", "给「天雨亚子」最后补 typical.yml。"),
        ("interperson",
         "给 amau_ako 写 interperson 关系（全量快照）：风纪委员会成员 "
         "sorasaki_hina(日奈)、ginkyou_iori(伊织)、hinomiya_chinatsu(千夏) "
         "都设 2；便利屋68 的 rikuhachima_aru、asagi_mutsuki、"
         "onikata_kayoko、igusa_haruka(遥香) 按打过交道的程度设 1。"
         "注意：只写学生间关系，绝对不要出现 sensei/玩家/老师 字段。"),
     ]},
    {"id": "ginkyou_iori", "name": "银镜伊织",
     "keywords": ["伊织", "イオリ", "iori", "风纪", "格黑娜"],
     "turns": [
        ("profile",
         "帮我为风纪委员会角色「银镜伊织」建档（character_id 用 ginkyou_iori）。"
         "第一步先写 profile.yml：先 search 萌娘百科再写，"
         "REQ~most_called_name 用「银镜 伊织」，en_name 用 Ginkyou Iori，"
         "jp_name 用 銀鏡 イオリ。"),
        ("personality", "给「银镜佐仓」补上 personality.yml。"),
        ("knowledge", "给「伊织」补 knowledge.yml。"),
        ("experience", "给「银镜伊织」补 experience.yml。"),
        ("typical", "给「银镜伊织」最后补 typical.yml。"),
        ("interperson",
         "给 ginkyou_iori 写 interperson 关系（全量快照）：风纪委员会成员 "
         "sorasaki_hina(日奈)、amau_ako(亚子)、hinomiya_chinatsu(千夏) "
         "都设 2；便利屋68 的 rikuhachima_aru、asagi_mutsuki、"
         "onikata_kayoko、igusa_haruka(遥香) 按打过交道的程度设 1。"
         "注意：只写学生间关系，绝对不要出现 sensei/玩家/老师 字段。"),
     ]},
    {"id": "hinomiya_chinatsu", "name": "火宫千夏",
     "keywords": ["千夏", "チナツ", "chinatsu", "风纪", "格黑娜"],
     "turns": [
        ("profile",
         "帮我为风纪委员会角色「火宫千夏」建档（character_id 用 hinomiya_chinatsu）。"
         "第一步先写 profile.yml：先 search 萌娘百科再写，"
         "REQ~most_called_name 用「火宫 千夏」，en_name 用 Hinomiya Chinatsu，"
         "jp_name 用 火宮 チナツ。"),
        ("personality", "给「千夏」补上 personality.yml。"),
        ("knowledge", "给「火宫千夏」补 knowledge.yml。"),
        ("experience", "给「千夏」补 experience.yml。"),
        ("typical", "给「火宫千夏」最后补 typical.yml。"),
        ("interperson",
         "给 hinomiya_chinatsu 写 interperson 关系（全量快照）：风纪委员会成员 "
         "sorasaki_hina(日奈)、amau_ako(亚子)、ginkyou_iori(伊织) 都设 2；"
         "便利屋68 的 rikuhachima_aru、asagi_mutsuki、onikata_kayoko、"
         "igusa_haruka(遥香) 按打过交道的程度设 1。"
         "注意：只写学生间关系，绝对不要出现 sensei/玩家/老师 字段。"),
     ]},
]

# 未落盘时的重试指令（用全名, 保证能解析到角色）
_RETRY = {
    "profile": "请为风纪委员会角色「{name}」创建 profile.yml（character_id: {cid}）。"
               "先 search 萌娘百科「{name}」再写。",
    "personality": "「{name}」（{cid}）的 personality.yml 还没写好，请现在用 "
                   "update_character(mode=merge) 为它写 personality.yml。",
    "knowledge": "「{name}」（{cid}）的 knowledge.yml 还没写好，请现在用 "
                 "update_character(mode=merge) 为它写 knowledge.yml。用全名「{name}」搜索资料。",
    "experience": "「{name}」（{cid}）的 experience.yml 还没写好，请现在用 "
                  "update_character(mode=merge) 为它写 experience.yml。",
    "typical": "「{name}」（{cid}）的 typical.yml 还没写好，请现在用 "
               "update_character(mode=merge) 为它写 typical.yml。",
    "interperson": "请为 {cid} 写 interperson 关系快照（update_interperson），"
                   "只写学生间关系，不要 sensei/玩家/老师 字段。",
}


# ============================================================================
# 桥接: emit / ask
# ============================================================================

TURN_EVENTS: list[dict] = []


def emit(evt: AgentEvent) -> None:
    d = evt.to_dict()
    TURN_EVENTS.append(d)
    k = d["kind"]
    data = d["data"]
    if k == "THINKING":
        return
    if k == "AI_MESSAGE":
        line = f"  [AI] {data.get('message', '')}"
    elif k == "PENDING_APPROVAL":
        diff = data.get("diff", "")
        line = f"  [提案] {data.get('summary', '')} (diff {len(diff)} 字符)"
    elif k == "TOOL_START":
        line = f"  [工具] {data.get('name')}: {data.get('label', '')}"
    elif k in ("TOOL_RESULT", "TOOL_ERROR"):
        line = (f"  [工具{'成功' if k == 'TOOL_RESULT' else '失败'}] "
                f"{data.get('name')} ({data.get('label', '')})")
    elif k == "EXEC_RESULT":
        ok = data.get("ok")
        line = f"  [执行{'成功' if ok else '失败'}] {data.get('message', '')[:160]}"
    elif k == "DONE":
        line = f"  [完成] {data.get('message', '')}"
    elif k == "INVALID_ACTION":
        line = f"  [动作无效] {'; '.join(data.get('errors', []))}"
    elif k == "LLM_ERROR":
        line = f"  [LLM错误] {data.get('error', '')[:160]}"
    elif k == "PLAN_ERROR":
        line = f"  [规划错误] {data.get('error', '')[:160]}"
    elif k == "ASK_USER":
        line = f"  [询问] {data.get('prompt', '')[:120]}"
    elif k == "DECISION":
        line = f"  [决策] {data.get('choice')}"
    else:
        line = f"  [{k}]"
    print(line, flush=True)


def ask(approval_id: str, prompt: str) -> str:
    if approval_id.startswith("example-"):
        print(f"  [范例询问 → skip] {prompt[:60]}", flush=True)
        return "skip"
    return "approve"  # 写动作 auto-approve（用户离开期间自主运行）


# ============================================================================
# 校验 / 守卫 / 日志
# ============================================================================

def _load_json(p: pathlib.Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def target_ok(cid: str, turn: str) -> bool:
    if turn == "interperson":
        data = _load_json(INTERPERSON)
        return isinstance(data, dict) and cid in data
    p = CHAR_DIR / cid / f"{turn}.yml"
    return p.exists() and bool(p.read_text(encoding="utf-8").strip())


def content_sane(cid: str, turn: str) -> bool:
    """内容粗检: 文件文本须出现角色关键词（防搜错角色写错档案）。"""
    if turn == "interperson":
        data = _load_json(INTERPERSON)
        return isinstance(data, dict) and isinstance(data.get(cid), dict)
    p = CHAR_DIR / cid / f"{turn}.yml"
    if not p.exists():
        return False
    txt = p.read_text(encoding="utf-8").lower()
    spec = next(s for s in CHARACTERS if s["id"] == cid)
    return any(k.lower() in txt for k in spec["keywords"])


def strip_sensei() -> list[tuple[str, str]]:
    """要求 2: 消除 interperson 中 sensei 类字段（含顶层与每个角色内部）。"""
    if not INTERPERSON.exists():
        return []
    data = _load_json(INTERPERSON)
    if not isinstance(data, dict):
        return []
    changed = False
    found: list[tuple[str, str]] = []
    for cid in [k for k in list(data) if k in _SENSEI_KEYS]:
        found.append(("顶层", cid))
        del data[cid]
        changed = True
    for cid, rels in data.items():
        if isinstance(rels, dict):
            for k in [k for k in list(rels) if k in _SENSEI_KEYS]:
                found.append((cid, k))
                del rels[k]
                changed = True
    if changed:
        INTERPERSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    return found


def unknown_relations(cid: str) -> list[str]:
    """interperson 中该角色的关系 id 是否为已知角色（防写错 id）。"""
    data = _load_json(INTERPERSON)
    rels = (data or {}).get(cid, {})
    if not isinstance(rels, dict):
        return []
    return [r for r in rels if r not in _KNOWN_IDS]


def stray_dirs() -> list[str]:
    if not CHAR_DIR.is_dir():
        return []
    return [d.name for d in CHAR_DIR.iterdir()
            if d.is_dir() and d.name not in _KNOWN_IDS]


def _log_line(text: str) -> None:
    with TRANSCRIPT.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def _init_logs() -> None:
    if not ISSUE_LOG.exists():
        ISSUE_LOG.write_text(
            "# CLI 测试记录 — 风纪委员会四角色建档\n\n"
            f"运行日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            "记录来源: ide/_run_4chars.py 自主驱动（auto-approve）。\n"
            "名字形式测试: 全名 / 后半 / 别称（如 大可爱、空崎阳奈 → 空崎日奈）。\n\n",
            encoding="utf-8")


def record_issue(title: str, detail: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n### {ts} — {title}\n\n{detail}\n"
    with ISSUE_LOG.open("a", encoding="utf-8") as f:
        f.write(entry)
    print(f"  !!! [记录问题] {title}", flush=True)


def issues_from(ev: dict) -> list[str]:
    k = ev["kind"]
    data = ev["data"]
    if k == "INVALID_ACTION":
        return [f"INVALID_ACTION: {'; '.join(data.get('errors', []))}"]
    if k == "LLM_ERROR":
        return [f"LLM_ERROR: {data.get('error', '')[:200]}"]
    if k == "TOOL_ERROR":
        return [f"TOOL_ERROR({data.get('name')}): {data.get('error', '')[:200]}"]
    if k == "PLAN_ERROR":
        return [f"PLAN_ERROR: {data.get('error', '')[:200]}"]
    if k == "EXEC_RESULT" and not data.get("ok"):
        return [f"EXEC_RESULT 失败: {data.get('message', '')[:200]}"]
    return []


def append_events(cid: str, turn: str, instruction: str) -> None:
    rec = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "character": cid,
        "turn": turn,
        "instruction": instruction,
        "events": TURN_EVENTS,
    }
    with EVENT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ============================================================================
# 单角色驱动
# ============================================================================

def run_character(agent: IDEAgent, spec: dict) -> None:
    cid = spec["id"]
    name = spec["name"]
    for turn, instruction in spec["turns"]:
        if target_ok(cid, turn):
            print(f"  [跳过] {cid}/{turn}.yml 已存在", flush=True)
            _log_line(f"[跳过] {cid}/{turn} 已存在")
            continue
        print(f"\n>>> {cid} {turn}\n    指令: {instruction}", flush=True)
        _log_line(f"\n>>> {cid} {turn}\n    指令: {instruction}")
        TURN_EVENTS.clear()
        agent.agent_turn(instruction)
        append_events(cid, turn, instruction)

        issues = []
        for ev in TURN_EVENTS:
            issues.extend(issues_from(ev))
        if not target_ok(cid, turn):
            issues.append(f"{turn} 未落盘（文件不存在 / interperson 无条目）")
        elif not content_sane(cid, turn):
            issues.append(f"{turn} 内容可疑：未出现角色关键词")
        if turn == "interperson":
            for rel in unknown_relations(cid):
                issues.append(f"interperson 未知角色 id: {rel}")
        for scope, key in strip_sensei():
            issues.append(f"interperson sensei 类字段已消除: {scope}.{key}")
        for sd in stray_dirs():
            issues.append(f"误建目录 {sd}（未删, 待人工确认）")

        if issues:
            record_issue(f"{cid} {turn} 轮次问题",
                         "\n".join(f"- {x}" for x in issues))
            _log_line("  问题: " + "; ".join(issues))
            if not target_ok(cid, turn):
                retry = _RETRY[turn].format(cid=cid, name=name)
                print(f"  >>> 重试: {retry}", flush=True)
                _log_line(f"  >>> 重试: {retry}")
                TURN_EVENTS.clear()
                agent.agent_turn(retry)
                append_events(cid, turn + "(retry)", retry)
                for ev in TURN_EVENTS:
                    for x in issues_from(ev):
                        record_issue(f"{cid} {turn}(retry) 问题", f"- {x}")
                if target_ok(cid, turn):
                    print("  [重试成功]", flush=True)
                else:
                    record_issue(f"{cid} {turn} 重试仍失败",
                                 "需人工检查：可能 MAX_STEPS 耗尽或 LLM 反复出问题。")
        else:
            _log_line("  [OK]")
    print(f"  [角色完成] {name} ({cid})", flush=True)


# ============================================================================
# 汇总核验（--verify, 不调 LLM）
# ============================================================================

def verify_all() -> None:
    print("=== 核验: 四角色五件套 + interperson ===\n")
    all_ok = True
    for spec in CHARACTERS:
        cid = spec["id"]
        status = []
        for turn in ("profile", "personality", "knowledge", "experience", "typical"):
            if target_ok(cid, turn):
                sane = content_sane(cid, turn)
                p = CHAR_DIR / cid / f"{turn}.yml"
                size = p.stat().st_size if p.exists() else 0
                status.append(f"{turn}:{'✓' if sane else '?'} {size}B")
            else:
                status.append(f"{turn}:✗")
                all_ok = False
        if target_ok(cid, "interperson"):
            data = _load_json(INTERPERSON)
            rels = data.get(cid, {}) if isinstance(data, dict) else {}
            unk = unknown_relations(cid)
            status.append(f"interperson:{len(rels)}关系" + (f"(未知id:{unk})" if unk else ""))
        else:
            status.append("interperson:✗")
            all_ok = False
        print(f"  {spec['name']:<6}({cid})  {', '.join(status)}")

    print("\n=== sensei 字段检查 ===")
    data = _load_json(INTERPERSON)
    hits = []
    if isinstance(data, dict):
        for cid, rels in data.items():
            if cid in _SENSEI_KEYS:
                hits.append(f"顶层:{cid}")
            if isinstance(rels, dict):
                hits += [f"{cid}.{k}" for k in rels if k in _SENSEI_KEYS]
    print("  无 sensei 类字段 ✓" if not hits else f"  发现: {hits}")

    print("\n=== 角色目录 ===")
    for d in sorted(CHAR_DIR.iterdir()):
        if d.is_dir():
            n = len(list(d.glob("*.yml")))
            print(f"  {d.name}  ({n} 个 yml)")
    print("\n" + ("全部落盘 ✓" if all_ok else "存在缺漏, 见上 ✗"))


def main() -> None:
    _init_logs()
    args = sys.argv[1:]
    if "--verify" in args:
        verify_all()
        return
    if "--all" in args or not args:
        idxs = list(range(len(CHARACTERS)))
    elif args[0].isdigit():
        idxs = [int(args[0]) - 1]
    else:
        print("用法: python ide/_run_4chars.py [1-4|--all|--verify]")
        sys.exit(1)
    client = LLMClient()
    agent = IDEAgent(client, str(ROOT), emit=emit, ask=ask)
    try:
        for i in idxs:
            if not 0 <= i < len(CHARACTERS):
                print(f"角色序号 {i + 1} 超出范围")
                continue
            spec = CHARACTERS[i]
            print(f"\n{'=' * 56}\n### 角色 {i + 1}/{len(CHARACTERS)}: "
                  f"{spec['name']} ({spec['id']})\n{'=' * 56}", flush=True)
            _log_line(f"\n{'=' * 56}\n### {spec['name']} ({spec['id']})")
            run_character(agent, spec)
    finally:
        client.close()
    print("\n驱动结束。", flush=True)


if __name__ == "__main__":
    main()
