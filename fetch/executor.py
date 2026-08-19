"""执行层 — 写盘 / 抓取 / diff 预览。

契约层只解析动作（纯结构校验, 不访问文件系统）；执行层负责真正的文件系统
与网络操作。分两个阶段:

    plan(action)    写动作的写前预览——读现有文件、计算最终内容、生成 diff。
                    抛 ExecError 表示不可执行（附原因, 供 agent 回灌给 LLM）。
    execute(action) 批准后落盘 / 抓取。幂等——重新计算最终内容, 不依赖 plan。

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

    def execute(self, action: AgentAction) -> ExecResult:
        """批准后落盘 / 抓取。抛 ExecError 表示执行失败。"""
        handler = getattr(self, f"_execute_{action.action}", None)
        if handler is None:
            raise ExecError(f"未知执行动作: {action.action}")
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
        )

    def _execute_update_character(self, action: AgentAction) -> ExecResult:
        char_dir = self._char_dir(action)
        if not char_dir.exists():
            raise ExecError(f"角色目录不存在: {char_dir}")
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

        source 为 WIKI_ALIASES 别名或任意 MediaWiki base URL；返回格式:
        [query, [titles], [descriptions], [urls]]。
        """
        query = action.payload["query"]
        source = action.payload["source"]
        max_results = action.payload["max_results"]
        base = WIKI_ALIASES.get(source, source.rstrip("/"))
        search_url = (
            f"{base}/api.php?action=opensearch"
            f"&search={quote(query)}&limit={max_results}&namespace=0&format=json"
        )
        try:
            resp = httpx.get(
                search_url,
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ExecError(f"搜索失败 {search_url}: {e}") from e

        try:
            titles, descs, urls = data[1], data[2], data[3]
        except (IndexError, TypeError) as e:
            raise ExecError(f"{source} 返回了无法解析的搜索结果") from e

        if not titles:
            raise ExecError(
                f"在 {source} 未找到关于 {query!r} 的结果，试试换关键词或换 source"
            )

        lines = [f"[搜索结果] {source}（{query}, {len(titles)} 条）:"]
        for i, (title, url) in enumerate(zip(titles, urls), 1):
            desc = descs[i - 1] if i - 1 < len(descs) else ""
            lines.append(f"{i}. {title} — {desc[:200]}\n   {url}")
        return ExecResult(ok=True, message="\n".join(lines))

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
