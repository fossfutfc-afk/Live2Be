"""体检逻辑 —— **纯函数**，不 import tkinter（测试与将来的 `--check` 都能直接用）。

每一条结果都是一个 `Check`：分组 / 名字 / 等级（ok/warn/bad/info）/ 说明。
判断依据一律调**现役实现**（角色卡 `CharacterLoader`、背景 `MediaCatalog`、
embedder 的 `health()`），这里只做汇总与措辞 —— 判据不在这层重写。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from infra import paths, settings

#: 等级（界面按它上色）
OK, WARN, BAD, INFO = "ok", "warn", "bad", "info"


@dataclass(frozen=True)
class Check:
    group: str
    name: str
    level: str = OK
    detail: str = ""

    def line(self) -> str:
        mark = {OK: "OK  ", WARN: "注意", BAD: "问题", INFO: "----"}[self.level]
        return f"[{mark}] {self.name}" + (f"  {self.detail}" if self.detail else "")


def _writable(p: Path) -> bool:
    return p.is_dir() and os.access(p, os.W_OK)


def _count_files(d: Path, suffixes: tuple[str, ...] = ()) -> int:
    if not d.is_dir():
        return 0
    return sum(1 for f in d.rglob("*")
               if f.is_file() and (not suffixes or f.suffix.lower() in suffixes))


# ---------------------------------------------------------------------------
# 五个根 / settings
# ---------------------------------------------------------------------------

def paths_checks() -> list[Check]:
    """五个根在哪、能不能写、`[paths]` 覆盖有没有生效。"""
    out = [
        Check("路径", "程序（只读）", INFO, str(paths.RESOURCE_ROOT)),
        Check("路径", "设置目录（settings.toml 在这）", INFO, str(paths.APP_ROOT)),
        Check("路径", "角色卡 / 世界观", OK if paths.CONFIG_ROOT.is_dir() else BAD,
              str(paths.CONFIG_ROOT)),
        Check("路径", "素材（立绘 / 背景）", OK if paths.ASSETS_ROOT.is_dir() else WARN,
              str(paths.ASSETS_ROOT)),
        Check("路径", "数据（事件流 / 记忆 / 日志）",
              OK if _writable(paths.DATA_ROOT) else WARN, str(paths.DATA_ROOT)),
    ]
    override = settings.raw().get("paths")
    if isinstance(override, dict) and override:
        used = "、".join(f"{k}={v}" for k, v in override.items())
        out.append(Check("路径", "[paths] 覆盖已生效", INFO, used))
    else:
        out.append(Check("路径", "[paths] 覆盖", INFO, "未配置（都用默认位置）"))
    err = settings.last_error()
    out.append(Check("路径", "settings.toml", WARN if err else OK,
                     err or str(settings.default_path())))
    return out


# ---------------------------------------------------------------------------
# 角色卡
# ---------------------------------------------------------------------------

def characters_checks() -> list[Check]:
    """每个角色卡能不能被现役 loader 读进来 + 完整度。"""
    from core.parsing.dynamic_character_parser import CharacterLoader

    root = paths.CHARACTERS_DIR
    if not root.is_dir():
        return [Check("角色卡", "角色目录", BAD, f"不存在: {root}")]
    try:
        loader = CharacterLoader(root)
        ids = sorted(loader.list_characters())
    except Exception as e:                       # noqa: BLE001 — 工具要能报告而不是崩
        return [Check("角色卡", "扫描角色目录", BAD, f"{type(e).__name__}: {e}")]
    out: list[Check] = [Check("角色卡", "找到角色", INFO, f"{len(ids)} 个")]
    # 目录里有子目录但**没被识别**（缺 profile.yml）—— "配错根目录"的典型症状,
    # 不报出来用户只会看到"0 个角色"然后一头雾水。
    subdirs = [p.name for p in root.iterdir()
               if p.is_dir() and not p.name.startswith(("__", "."))]
    unknown = [d for d in sorted(subdirs) if d not in ids]
    if unknown:
        out.append(Check("角色卡", "没被识别的子目录", WARN,
                         f"{', '.join(unknown)} —— 缺 profile.yml（不是角色卡）"))
    for cid in ids:
        try:
            ch = loader.load(cid)
        except Exception as e:                   # noqa: BLE001 — 缺文件/字段就报这一条
            out.append(Check("角色卡", f"{cid}", BAD, f"读不进来: {e}"))
            continue
        comp = ch.completeness if isinstance(getattr(ch, "completeness", None), dict) else {}
        ratio = float(comp.get("ratio") or 0.0)
        missing = comp.get("missing") or []
        if ratio >= 1.0:
            out.append(Check("角色卡", f"{cid}（{ch.display_name}）", OK, "完整"))
        else:
            out.append(Check("角色卡", f"{cid}（{ch.display_name}）", WARN,
                             f"完整度 {ratio:.0%}" + (f" · 缺 {', '.join(map(str, missing))}"
                                                     if missing else "")))
    return out


# ---------------------------------------------------------------------------
# 素材
# ---------------------------------------------------------------------------

def _place_table() -> dict:
    try:
        data = json.loads(Path(paths.PLACE_TABLE_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


#: 算"有图"的后缀。`emotions.yml` 不算 —— 它只是词表，光有它角色照样点不出来
ART_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".webm", ".skel", ".atlas")


def _has_art(char_dir: Path) -> bool:
    return any(f.is_file() and f.suffix.lower() in ART_SUFFIXES for f in char_dir.rglob("*"))


def assets_checks() -> list[Check]:
    """立绘（按角色）/ 背景（按**地点表自己的声明**）/ 菜单图。

    ⚠️ 背景这里**不猜**"某个 key 对应哪张图": 地点表每条自带 `files: {day: [...], night: [...]}`
    （路径相对 `assets/background/`）—— 拿它自己声明的路径去对磁盘, 才是"缺了没有"的判据。
    （我第一版拿 `MediaCatalog.background(key)` 查, 那是按**文件名**索引的, 于是 168 个地点里
    报出 103 个"缺" —— 全是假阳性。判据别自己发明。）

    ⚠️ "有立绘"也要看图，不看目录: 最小口径的包只带 `emotions.yml`（词表进 prompt 要用），
    目录存在但一张图都没有 —— 按目录判会报"5 个角色有立绘"，实际一张也没有。
    """
    out: list[Check] = []
    assets = Path(paths.ASSETS_ROOT)
    out.append(Check("素材", "素材根", OK if assets.is_dir() else WARN, str(assets)))

    # 立绘: 素材里真有图（或 spine 三件套）的角色 / 有角色卡却一张图都没有的
    illus = assets / "illustration"
    chars = sorted(p.name for p in illus.iterdir()
                   if p.is_dir() and not p.name.startswith(("__", ".")) and _has_art(p)) \
        if illus.is_dir() else []
    out.append(Check("素材", "有立绘的角色", INFO, f"{len(chars)} 个: {', '.join(chars) or '（无）'}"))
    char_root = Path(paths.CHARACTERS_DIR)
    if char_root.is_dir():
        missing_art = sorted(p.name for p in char_root.iterdir()
                             if p.is_dir() and not p.name.startswith(("__", "."))
                             and p.name not in chars)
        if missing_art:
            out.append(Check("素材", "有角色卡但没有立绘", WARN,
                             ", ".join(missing_art) + "（去前端「素材」页下载对应素材包）"))

    # 背景: 地点表声明的文件 ↔ 磁盘
    table = _place_table()
    if not table:
        out.append(Check("素材", "地点表", WARN, f"读不出来: {paths.PLACE_TABLE_PATH}"))
    else:
        bg = assets / "background"
        declared = 0
        missing: list[str] = []
        empty: list[str] = []
        for key, entry in table.items():
            files = entry.get("files") if isinstance(entry, dict) else None
            paths_declared = [p for group in (files or {}).values()
                              if isinstance(group, list) for p in group]
            if not paths_declared:
                empty.append(str(key))
                continue
            declared += len(paths_declared)
            missing += [str(p) for p in paths_declared if not (bg / str(p)).is_file()]
        if missing:
            out.append(Check("素材", "地点表声明的背景文件", WARN,
                             f"缺 {len(missing)}/{declared} 张（例: {', '.join(missing[:3])}）"
                             " —— 这些场景会退化成默认底图"))
        else:
            out.append(Check("素材", "地点表声明的背景文件", OK,
                             f"{len(table)} 个地点 / {declared} 张全部在位"))
        if empty:
            out.append(Check("素材", "地点表里没有图的条目", INFO, ", ".join(empty[:5])))

    menu = _count_files(assets / "menu", (".jpg", ".png"))
    out.append(Check("素材", "登录页轮播图", OK if menu else WARN, f"{menu} 张"))
    return out


# ---------------------------------------------------------------------------
# 数据 / 连通性
# ---------------------------------------------------------------------------

def data_checks() -> list[Check]:
    """数据在哪、有多少条线。**只读**（append-only 真源）。"""
    root = Path(paths.DATA_ROOT)
    out = [Check("数据", "数据根", OK if root.is_dir() else INFO, str(root))]
    worlds = root / "worlds"
    if not worlds.is_dir():
        out.append(Check("数据", "还没开始玩", INFO, "data/worlds 不存在（首次运行会建）"))
        return out
    # worlds/{world}/characters/{char}/soul/events.jsonl ⇒ parents[1] 才是角色目录
    lines = sorted(p.parents[1].name for p in worlds.glob("*/characters/*/soul/events.jsonl"))
    out.append(Check("数据", "事件流（角色线）", INFO,
                     f"{len(lines)} 条: {', '.join(lines) or '（无）'}"))
    log = Path(paths.DIAG_LOG_PATH)
    if log.is_file():
        out.append(Check("数据", "诊断日志", INFO,
                         f"{log.stat().st_size / 1024:.0f} KB · {log}"))
    out.append(Check("数据", "真源只读", INFO, "事件流 append-only：备份请复制，别改"))
    return out


def llm_checks() -> list[Check]:
    """LLM / 生图的配置在不在（**不花钱**：只看配置，不发请求）。"""
    llm = settings.section("llm")
    api_key = str(llm.get("api_key") or "").strip()
    env_key = (os.environ.get("LLM_API_KEY") or "").strip()
    out = [
        Check("LLM", "对话 API Key", OK if (api_key or env_key) else BAD,
              "settings.toml" if api_key else ("环境变量 .env" if env_key else "未配置")),
        Check("LLM", "Base URL", INFO, str(llm.get("base_url") or "（默认）")),
        Check("LLM", "模型", INFO, str(llm.get("model") or "（默认）")),
    ]
    image = settings.section("image")
    enabled = image.get("enabled", True)
    out.append(Check("LLM", "纪念立绘生图", INFO,
                     "已开" if enabled is not False else "已关（纪念场景纯文字）"))
    if enabled is not False and not (str(image.get("api_key") or "").strip()):
        out.append(Check("LLM", "生图 API Key", WARN, "未配置 ⇒ 生图会静默跳过"))
    return out


def embedding_check() -> Check:
    """本机 embedding 服务在不在（不花钱：它是本地 HTTP）。

    依赖缺失（打包版**有意**不带 httpx）与"服务没起"是两回事，别混成一条告警 ——
    前者是工具自己的边界，报成 WARN 会让人以为环境坏了。
    """
    try:
        from core.rag.embedder import LocalEmbedder

        emb = LocalEmbedder()
    except ModuleNotFoundError as e:
        return Check("LLM", "embedding", INFO,
                     f"跳过（这个工具不带 {e.name}，打包版有意不带 HTTP 栈）")
    except Exception as e:                       # noqa: BLE001
        return Check("LLM", "embedding", WARN, f"初始化失败: {type(e).__name__}: {e}")
    try:
        ok = bool(emb.health())
    except Exception as e:                       # noqa: BLE001
        return Check("LLM", "embedding", WARN, f"{emb.base_url} 探不通: {e}")
    return Check("LLM", "embedding", OK if ok else WARN,
                 f"{emb.base_url} · {emb.model}" + ("" if ok else " · 不在 ⇒ 语义召回退化成字面"))


def run_all(*, probe_embedding: bool = True) -> list[Check]:
    """一键体检（不吃 token）。"""
    checks: list[Check] = []
    for fn in (paths_checks, llm_checks, characters_checks, assets_checks, data_checks):
        try:
            checks += fn()
        except Exception as e:                   # noqa: BLE001 — 一组挂了不影响别的组
            checks.append(Check("体检", fn.__name__, BAD, f"{type(e).__name__}: {e}"))
    if probe_embedding:
        checks.append(embedding_check())
    return checks


def summary(checks: list[Check]) -> dict:
    out = {OK: 0, WARN: 0, BAD: 0, INFO: 0}
    for c in checks:
        out[c.level] = out.get(c.level, 0) + 1
    return out


# ---------------------------------------------------------------------------
# 写配置（只碰 [paths]）
# ---------------------------------------------------------------------------

#: 允许改的三个根（`app`/`resource` 不给改：那是程序的落脚点）
SETTABLE = ("config", "assets", "data")


def write_paths(**roots: str) -> Path:
    """把 `config/assets/data` 写进 settings.toml 的 `[paths]`；空串 = 删掉该覆盖。

    ⚠️ 五个根是 **import 期常量** ⇒ 写完必须重启主程序才生效（界面要提示）。
    """
    for key in roots:
        if key not in SETTABLE:
            raise ValueError(f"只能改 {SETTABLE}，收到 {key!r}")
    return settings.update("paths", **roots)
