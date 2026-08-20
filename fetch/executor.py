"""执行层 — 写盘 / 抓取 / diff 预览。

契约层只解析动作（纯结构校验, 不访问文件系统）；执行层负责真正的文件系统
与网络操作。分两个阶段:

    plan(action)    写动作的写前预览——读现有文件、计算最终内容、生成 diff。
                    抛 ExecError 表示不可执行（附原因, 供 agent 回灌给 LLM）。
    execute(action) 批准后落盘 / 抓取。默认幂等——重新计算最终内容。
                    写动作可传回 plan 复用其 execute_state（如 update_character
                    merge 已算好的最终内容）: 省一次 YAML round-trip, 且落盘内容
                    与展示给用户的 diff 严格一致。

agent loop 流程: LLM 动作 → 契约解析 → plan(生成 diff) → 用户审批 → execute。

职责边界:
    - 目录存在性: create 要求目录不存在, update 要求目录存在
    - update merge: 顶层字段级合并（{**existing, **incoming}）, 嵌套结构整体替换;
      经 YAML round-trip 会规范化格式并丢弃注释——这是 merge 的已知代价
    - interperson: 角色粒度替换 + 新增关系依据硬校验（宁缺勿错）
    - fetch_url: httpx 抓取 + html.parser 提取文本 + 截断
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import yaml

from contract import AgentAction
from fetch.actions.common import CHARACTER_FILES, MODE_MERGE
from fetch.actions.search import WIKI_ALIASES
from parsing.dynamic_character_parser import get_completeness, get_display_name

# 配置路径（相对项目根）
CHARACTERS_DIR = "config/characters"
INTERPERSON_PATH = "config/settings/relation/interperson.json"

# fetch_url 默认截断长度（契约层未指定时）
DEFAULT_FETCH_CHARS = 8000
_HTTP_TIMEOUT = 15.0
_USER_AGENT = "Live2Be/0.1 (+local agent; character-data fetcher)"


class ExecError(Exception):
    """执行层拒绝/失败。message 供 agent 回灌给 LLM 修正。"""


@dataclass
class Plan:
    """写动作的写前预览（审批界面展示 diff）。"""

    action: str
    summary: str
    diff: str = ""
    # 执行所需的最终状态（plan 计算, execute 可选复用）
    execute_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecResult:
    """执行结果。message 回灌给 LLM（或展示给用户）。"""

    ok: bool
    message: str


class Executor:
    """动作执行器。root = Live2Be 项目根目录。"""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def plan(self, action: AgentAction) -> Plan:
        """写动作的写前预览。非写动作返回空 diff（无需审批）。"""
        handler = getattr(self, f"_plan_{action.action}", None)
        if handler is None:
            return Plan(action=action.action, summary=action.summary, diff="")
        return handler(action)

    def execute(self, action: AgentAction, plan: Plan | None = None) -> ExecResult:
        """批准后落盘 / 抓取。抛 ExecError 表示执行失败。

        plan 可选——仅 update_character 复用（merge 已算好的最终内容,
        与展示的 diff 一致）; 不传 plan 或非 update_character → 幂等重算。
        """
        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            raise ExecError(f"未知执行动作: {action.action}")
        if plan is not None and action.action == "update_character":
            return handler(action, plan)
        return handler(action)

    # ==================================================================
    # create_character
    # ==================================================================

    def _plan_create_character(self, action: AgentAction) -> Plan:
        char_dir = self._char_dir(action)
        if char_dir.exists():
            raise ExecError(f"角色目录已存在: {char_dir}")
        return Plan(
            action=action.action,
            summary=action.summary,
            diff=self._diff_new_files(char_dir, action.payload["files"]),
        )

    def _execute_create_character(self, action: AgentAction) -> ExecResult:
        char_dir = self._char_dir(action)
        if char_dir.exists():
            raise ExecError(f"角色目录已存在: {char_dir}")
        char_dir.mkdir(parents=True)
        for name, content in action.payload["files"].items():
            (char_dir / name).write_text(content, encoding="utf-8")
        return ExecResult(
            ok=True,
            message=f"已创建角色 {action.payload['character_id']}: "
                    f"{', '.join(action.payload['files'])}",
        )

    # ==================================================================
    # update_character
    # ==================================================================

    def _plan_update_character(self, action: AgentAction) -> Plan:
        char_dir = self._char_dir(action)
        if not char_dir.exists():
            raise ExecError(f"角色目录不存在: {char_dir}")
        files = self._resolve_update_files(action, char_dir)
        return Plan(
            action=action.action,
            summary=action.summary,
            diff=self._diff_updated_files(char_dir, files),
            # 最终内容缓存进 execute_state——execute 复用则无需重算
            execute_state={"files": files},
        )

    def _execute_update_character(self, action: AgentAction,
                                  plan: Plan | None = None) -> ExecResult:
        char_dir = self._char_dir(action)
        if not char_dir.exists():
            raise ExecError(f"角色目录不存在: {char_dir}")
        if plan is not None and "files" in plan.execute_state:
            files = plan.execute_state["files"]
        else:
            files = self._resolve_update_files(action, char_dir)
        for name, content in files.items():
            (char_dir / name).write_text(content, encoding="utf-8")
        return ExecResult(
            ok=True,
            message=f"已更新角色 {action.payload['character_id']}: "
                    f"{', '.join(files)}",
        )

    def _resolve_update_files(self, action: AgentAction, char_dir: Path) -> dict[str, str]:
        """按 mode 计算每个文件的最终内容。

        overwrite → 直接用 LLM 提交的完整内容；
        merge     → 读现有文件, 顶层字段级合并（现有未提及的字段保留）。
        """
        mode = action.payload["mode"]
        result: dict[str, str] = {}
        for name, content in action.payload["files"].items():
            path = char_dir / name
            if mode == MODE_MERGE and path.exists():
                existing = _load_yaml_dict(path)
                incoming = _load_yaml_str(content)
                merged = {**existing, **incoming}
                result[name] = yaml.safe_dump(
                    merged, allow_unicode=True, sort_keys=False
                )
            else:
                result[name] = content
        return result

    # ==================================================================
    # update_interperson
    # ==================================================================

    def _plan_update_interperson(self, action: AgentAction) -> Plan:
        updated = self._interperson_updated(action)
        old = self._load_interperson()
        return Plan(
            action=action.action,
            summary=action.summary,
            diff=self._diff_interperson(old, updated, action.payload["character_id"]),
            execute_state={"content": updated},
        )

    def _execute_update_interperson(self, action: AgentAction) -> ExecResult:
        updated = self._interperson_updated(action)
        self._write_interperson(updated)
        return ExecResult(
            ok=True,
            message=f"已更新 interperson.json: {action.payload['character_id']}",
        )

    def _interperson_updated(self, action: AgentAction) -> dict:
        """角色粒度替换 + 新增关系依据硬校验（宁缺勿错）。"""
        char_id = action.payload["character_id"]
        new = action.payload["relations"]

        current = self._load_interperson()
        existing = current.get(char_id, {})

        added = set(new) - set(existing)
        if added and not (action.sources or action.basis):
            raise ExecError(
                f"新增关系 {sorted(added)} 缺少依据（sources/basis）——"
                f"宁缺勿错, 请提供资料依据或用户明确需求"
            )

        updated = dict(current)
        updated[char_id] = new
        return updated

    # ==================================================================
    # search
    # ==================================================================

    def _execute_search(self, action: AgentAction) -> ExecResult:
        """MediaWiki opensearch 搜索 → 返回 标题+简介+URL 清单（回灌给 LLM）。

        多候选尝试（解决别名/繁体/日文名搜不到）:
            原查询 → 别名索引命中规范标题 → 简体变体(zhconv)，
        逐个 opensearch, 首个非空即返回。全空 → ExecError 列出已尝试项 +
        换词建议, 供 LLM 修正而不是用同样的词反复重试。
        source 为 WIKI_ALIASES 别名或任意 MediaWiki base URL。
        """
        query = action.payload["query"]
        source = action.payload["source"]
        max_results = action.payload["max_results"]
        aliases = action.payload.get("aliases", [])
        base = WIKI_ALIASES.get(source, source.rstrip("/"))

        tried: list[str] = []
        for q in self._search_attempts(query, aliases):
            tried.append(q)
            titles, descs, urls = _opensearch(base, q, max_results)
            if titles:
                lines = [f"[搜索结果] {source}（{query}, {len(titles)} 条）:"]
                for i, (title, url) in enumerate(zip(titles, urls), 1):
                    desc = descs[i - 1] if i - 1 < len(descs) else ""
                    lines.append(f"{i}. {title} — {desc[:200]}\n   {url}")
                return ExecResult(ok=True, message="\n".join(lines))

        raise ExecError(
            f"在 {source} 未找到关于 {query!r} 的结果"
            f"（已尝试: {', '.join(tried)}）。\n"
            "试试: 简体全名（如 伊草遥香）/ 别名（如 地雷妹）/ 日文名 / "
            "其他译名，或换 source。不要用同样的词反复重试。"
        )

    def _search_attempts(
        self, query: str, aliases: list[str] | tuple[str, ...] = ()
    ) -> list[str]:
        """候选查询序列（去重保序）。

        每个种子词（原查询 + AI 提交的 aliases）分别展开:
            种子本身 → 索引命中规范标题 → 简体变体(zhconv)。
        aliases 用于**新角色**（自动索引尚无条目）: AI 凭自身知识把
        别名/日文名/其他译名一次放进 search 调用, 执行层逐个尝试,
        避免"搜不到→再试"的多次 LLM 往返。宁缺勿错: 候选词是 LLM
        显式提交的（可见于 trace/diff）, 不是代码臆造。
        """
        from fetch.search_index import build_alias_index, normalize_query

        index = build_alias_index(self.root)
        attempts: list[str] = []
        seen: set[str] = set()

        def add(q: str) -> None:
            q = q.strip()
            if q and q not in seen:
                seen.add(q)
                attempts.append(q)

        for seed in (query, *aliases):
            add(seed)
            for title in sorted(index.get(normalize_query(seed), ())):
                add(title)
            try:
                from zhconv import convert
                simp = convert(seed, "zh-cn")
            except ImportError:  # zhconv 未装 → 跳过简体会话（萌娘百科自带繁→简归一）
                simp = seed
            if simp != seed:
                add(simp)
        return attempts

    # ==================================================================
    # fetch_url
    # ==================================================================

    def _execute_fetch_url(self, action: AgentAction) -> ExecResult:
        url = action.payload["url"]
        max_chars = action.payload.get("max_chars", DEFAULT_FETCH_CHARS)
        try:
            resp = httpx.get(
                url,
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ExecError(f"抓取失败 {url}: {e}") from e

        text = _extract_html_text(resp.text)
        if not text:
            raise ExecError(f"{url} 未提取到文本内容（可能是 JS 渲染页）")
        return ExecResult(ok=True, message=text[:max_chars])

    # ==================================================================
    # view_character
    # ==================================================================

    def _execute_view_character(self, action: AgentAction) -> ExecResult:
        """查看角色现状——结果回灌给 LLM, 供"补全/完善"决策。

        不带 file → 五件套清单（每个文件 已存在(字符数)/缺失）+ 显示名 + 完整度;
        带 file → 该文件全文 +（profile 的）缺失 SIG/REQ 清单。
        只读, 不落盘; 解析失败的文件照常展示, 只是不提供完整度。
        """
        char_id = action.payload["character_id"]
        char_dir = self._char_dir(action)
        if not char_dir.is_dir():
            raise ExecError(f"角色不存在: {char_id}")

        file = action.payload.get("file")
        if file:
            return self._view_one_file(char_dir, file)

        lines = [f"[角色 {char_id} 五件套现状]"]
        for name in CHARACTER_FILES:
            path = char_dir / name
            if path.exists():
                size = len(path.read_text(encoding="utf-8"))
                lines.append(f"  {name}: 已存在 ({size} 字符)")
            else:
                lines.append(f"  {name}: 缺失")
        info = self._completeness_info(char_dir / "profile.yml")
        if info:
            lines.append(info)
        lines.append("提示: 缺什么就写什么（update_character mode=merge, 一次一个文件）")
        return ExecResult(ok=True, message="\n".join(lines))

    def _view_one_file(self, char_dir: Path, file: str) -> ExecResult:
        """单文件视图：全文 +（profile 的）缺失 SIG/REQ 清单。"""
        path = char_dir / file
        if not path.exists():
            raise ExecError(f"文件不存在: {char_dir.name}/{file}")
        content = path.read_text(encoding="utf-8").rstrip("\n")
        lines = [f"[角色 {char_dir.name}/{file} 现状]", content or "(空文件)"]
        info = self._completeness_info(path)
        if info:
            lines.append(info)
        return ExecResult(ok=True, message="\n".join(lines))

    def _completeness_info(self, path: Path) -> str:
        """profile.yml 的显示名 + 完整度 / 缺失 SIG·REQ（剥前缀后补回字面量）。

        非 profile 或解析失败 → 空串。
        """
        if path.name != "profile.yml":
            return ""
        data = _safe_load_yaml(path)
        if not data:
            return ""
        comp = get_completeness(data)
        info = (
            f"显示名: {get_display_name(data)}   "
            f"完整度 {comp['score']}/{comp['total_sig']} ({comp['ratio']:.0%})"
        )
        if comp["missing_sig"]:
            info += "  缺失 SIG: " + ", ".join(
                "SIG~" + k for k in sorted(comp["missing_sig"])
            )
        if comp["missing_req"]:
            info += "  缺失 REQ: " + ", ".join(
                "REQ~" + k for k in sorted(comp["missing_req"])
            )
        return info

    # ==================================================================
    # view_interperson
    # ==================================================================

    def _execute_view_interperson(self, action: AgentAction) -> ExecResult:
        """查看 interperson.json 现状——结果回灌给 LLM, 供"改/补关系"决策。

        不带 character_id → 列出有记录的每个角色及关系（内联, interperson 天然很小）;
        带 character_id → 该角色完整关系（{关系角色id: 权重}）。
        只读, 不落盘; 无记录角色 → ExecError。
        """
        current = self._load_interperson()
        char_id = action.payload.get("character_id")
        if char_id:
            rel = current.get(char_id)
            if rel is None:
                raise ExecError(f"角色无关系记录: {char_id}")
            lines = [f"[角色 {char_id} 关系现状]"]
            for name in sorted(rel):
                lines.append(f"  {name}: {rel[name]}")
            lines.append("权重语义: 1=萍水相逢/只见profile  2=社团成员/加personality  "
                         "3=故知/再加experience")
            lines.append("提示: update_interperson 是全量快照替换——新增关系须附依据"
                         "(sources/basis), 并带上想保留的现有关系")
            return ExecResult(ok=True, message="\n".join(lines))

        lines = [f"[interperson 现状] {len(current)} 个角色有记录"]
        for cid in sorted(current):
            rel = current[cid]
            if rel:
                inline = "  ".join(f"{n}({w})" for n, w in sorted(rel.items()))
                lines.append(f"  {cid} ({len(rel)}): {inline}")
            else:
                lines.append(f"  {cid}: (空)")
        lines.append("提示: 看某角色完整关系用 view_interperson(character_id=...); "
                     "改关系前先看清现状再 update_interperson")
        return ExecResult(ok=True, message="\n".join(lines))

    # ==================================================================
    # 内部工具
    # ==================================================================

    def _char_dir(self, action: AgentAction) -> Path:
        return self.root / CHARACTERS_DIR / action.payload["character_id"]

    def _load_interperson(self) -> dict:
        path = self.root / INTERPERSON_PATH
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_interperson(self, content: dict) -> None:
        path = self.root / INTERPERSON_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(content, ensure_ascii=False, indent=4), encoding="utf-8"
        )

    # ---- diff ----

    def _diff_new_files(self, char_dir: Path, files: dict[str, str]) -> str:
        blocks = []
        for name, content in files.items():
            blocks.append(f"+ === [新建] {char_dir / name} ===")
            blocks.extend(f"+ {line}" for line in content.splitlines())
        return "\n".join(blocks)

    def _diff_updated_files(self, char_dir: Path, files: dict[str, str]) -> str:
        blocks = []
        for name, content in files.items():
            path = char_dir / name
            if not path.exists():
                blocks.append(f"+ === [新建] {path} ===")
                blocks.extend(f"+ {line}" for line in content.splitlines())
                continue
            old = path.read_text(encoding="utf-8")
            if old == content:
                blocks.append(f"  === [无变化] {path} ===")
                continue
            diff = difflib.unified_diff(
                old.splitlines(), content.splitlines(),
                fromfile=f"旧/{name}", tofile=f"新/{name}", lineterm="",
            )
            blocks.append(f"=== [更新] {path} ===")
            blocks.extend(diff)
        return "\n".join(blocks)

    @staticmethod
    def _diff_interperson(old: dict, new: dict, char_id: str) -> str:
        old_rel = old.get(char_id, {})
        new_rel = new.get(char_id, {})
        lines = [f"=== interperson.json: {char_id} 的关系 ==="]
        for name in sorted(set(old_rel) | set(new_rel)):
            o, n = old_rel.get(name), new_rel.get(name)
            if o is None:
                lines.append(f"+ {name}: {n}   (新增)")
            elif n is None:
                lines.append(f"- {name}: {o}   (删除)")
            elif o != n:
                lines.append(f"~ {name}: {o} → {n}")
            else:
                lines.append(f"  {name}: {n}   (不变)")
        # 新增熟悉度3（故知）须显式告知用户确认——AI 推断加码可以, 但要用户拍板
        new_f3 = sorted(
            n for n, w in new_rel.items()
            if w == 3 and old_rel.get(n) != 3
        )
        if new_f3:
            lines.append(
                f"⚠️ 新增熟悉度3(故知): {', '.join(new_f3)} — "
                "程度很高, 请确认资料/用户依据属实"
            )
        return "\n".join(lines)


# ============================================================================
# 模块级工具
# ============================================================================

def _load_yaml_dict(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _safe_load_yaml(path: Path) -> dict | None:
    """读 YAML, 缺失/解析失败/非对象 → None。

    view_character 是只读工具, 不能因某个文件坏了而整段失败——照常展示内容,
    只是不算完整度。
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _load_yaml_str(text: str) -> dict:
    data = yaml.safe_load(text) or {}
    return data if isinstance(data, dict) else {}


def _opensearch(base: str, query: str, limit: int) -> tuple[list[str], list[str], list[str]]:
    """MediaWiki opensearch → (titles, descs, urls)。网络/解析失败抛 ExecError。

    独立模块级函数便于测试 monkeypatch（_execute_search 的多候选尝试按此注入）。
    """
    url = (
        f"{base}/api.php?action=opensearch"
        f"&search={quote(query)}&limit={limit}&namespace=0&format=json"
    )
    try:
        resp = httpx.get(
            url,
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        raise ExecError(f"搜索失败 {url}: {e}") from e

    try:
        titles, descs, urls = data[1], data[2], data[3]
    except (IndexError, TypeError) as e:
        raise ExecError(f"{base} 返回了无法解析的搜索结果") from e
    return list(titles), list(descs), list(urls)


def _extract_html_text(html: str) -> str:
    """用标准库 html.parser 提取可见文本（跳过 script/style/标签）。"""
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(parser.parts)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            stripped = data.strip()
            if stripped:
                self.parts.append(stripped)
