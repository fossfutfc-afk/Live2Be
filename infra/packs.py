"""素材包（`assets/` 的可下载切片）—— 清单解析 / 装没装的判定 / 下载校验解压。

只有 stdlib（`infra/` 不进第三方）。HTTP 用 `urllib.request`：它免费带来
`HTTP(S)_PROXY` 环境变量支持，也能被 `[net] proxy` 显式覆盖 —— 这点很要紧，
直连不稳时代理必须是第一等公民，而不是事后补钩子。

三条纪律:

1. **包只是"往 assets/ 里放文件"** —— zip 内路径与 `assets/` 同构，解压目标恒为 assets 根。
   读取侧（`core/media/`、`/assets/*` 挂载）永远不需要知道"包"这个概念存在。
2. **装没装只看磁盘**：清单里带了每个文件的相对路径与字节数，判定 = 逐个 stat。
   不写状态文件 —— 用户手动删两张图，状态立刻变成"部分"，不用他去删记录。
3. **先校验再落地**：下载到 `.part`，字节数与 sha256 都对上才开始解压；解压逐条防穿越
   （成员解析后的绝对路径必须仍落在 assets 根之下）。

清单由 `packaging/make_packs.py` 生成，放哪都行（`[assets] manifest_url` 指过去即可，
`LIVE2BE_PACKS_MANIFEST` 可临时覆盖）。相对 zip 名按 manifest 自身地址解析 ——
所以同一份清单在 `http://127.0.0.1:8000/` 和任何对象存储上都能直接用。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import ProxyHandler, Request, build_opener

from contract.errors import Live2BeError, err
from infra import settings

MANIFEST_ENV = "LIVE2BE_PACKS_MANIFEST"
DEFAULT_TIMEOUT = 20.0
_CHUNK = 1 << 20
#: 清单格式版本（只认这个）
SCHEMA = 1

Stage = str                       # downloading / verifying / extracting / done / error
Progress = Callable[[str, Stage, int, int], None]


class PackError(Live2BeError):
    """清单坏、下载失败、校验不过、解压越界 —— 一律这一类。"""


class Cancelled(PackError):
    """用户中途取消。和"失败"分开：取消不该在日志里留成错误。"""


@dataclass(frozen=True)
class Pack:
    """清单里的一个可下载单元。`files` = `(assets 相对路径, 字节数)`。"""

    id: str
    kind: str
    group: str
    title: str
    zip: str
    zip_bytes: int
    zip_sha256: str
    bytes: int
    file_count: int
    files: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Manifest:
    schema: int
    generated: str
    packs: tuple[Pack, ...]
    source: str = ""

    def get(self, pack_id: str) -> Pack | None:
        return next((p for p in self.packs if p.id == pack_id), None)


@dataclass
class Outcome:
    """一个包的安装结果（失败不抛，好让其余包继续）。"""

    pack_id: str
    ok: bool
    files: int = 0
    bytes: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def manifest_url() -> str:
    """清单地址：`LIVE2BE_PACKS_MANIFEST` > `[assets] manifest_url` > ""。"""
    env = os.environ.get(MANIFEST_ENV, "").strip()
    if env:
        return env
    return str(settings.section("assets").get("manifest_url") or "").strip()


def proxy_url() -> str:
    """代理：`[net] proxy` > ""（空 = 交给 urllib 读环境变量）。"""
    return str(settings.section("net").get("proxy") or "").strip()


def _opener(proxy: str):
    if proxy:
        return build_opener(ProxyHandler({"http": proxy, "https": proxy}))
    return build_opener()


# ---------------------------------------------------------------------------
# 清单
# ---------------------------------------------------------------------------


def _parse_pack(raw: object) -> Pack:
    if not isinstance(raw, dict):
        raise PackError("清单里的 pack 不是对象")
    pack_id = str(raw.get("id") or "")
    if not pack_id:
        raise PackError("清单里有 pack 缺 id")
    try:
        files = tuple((str(rel), int(size)) for rel, size in raw.get("files") or ())
    except (TypeError, ValueError) as e:
        raise PackError(f"{pack_id}: files 形状不对（{e}）") from e
    if not files:
        raise PackError(f"{pack_id}: files 为空 —— 空包不该进清单")
    for rel, _size in files:
        if rel.startswith("/") or ".." in Path(rel).parts or ":" in rel:
            raise PackError(f"{pack_id}: 清单里有可疑路径 {rel}")
    return Pack(
        id=pack_id,
        kind=str(raw.get("kind") or ""),
        group=str(raw.get("group") or ""),
        title=str(raw.get("title") or pack_id),
        zip=str(raw.get("zip") or ""),
        zip_bytes=int(raw.get("zip_bytes") or 0),
        zip_sha256=str(raw.get("zip_sha256") or ""),
        bytes=int(raw.get("bytes") or sum(size for _, size in files)),
        file_count=int(raw.get("file_count") or len(files)),
        files=files,
    )


def parse_manifest(raw: object, *, source: str = "") -> Manifest:
    """校验并解析清单（坏数据一律 PackError，不猜）。"""
    if not isinstance(raw, dict):
        raise PackError("清单不是 JSON 对象")
    schema = int(raw.get("schema") or 0)
    if schema != SCHEMA:
        raise PackError(f"清单 schema={schema}，本程序只认 {SCHEMA}")
    packs = tuple(_parse_pack(p) for p in raw.get("packs") or ())
    if not packs:
        raise PackError("清单里没有任何包")
    if len({p.id for p in packs}) != len(packs):
        raise PackError("清单里 pack id 重复")
    return Manifest(
        schema=schema,
        generated=str(raw.get("generated") or ""),
        packs=packs,
        source=source,
    )


def read_manifest(url: str | None = None, *, timeout: float = DEFAULT_TIMEOUT,
                  proxy: str | None = None) -> Manifest:
    """拉清单（`url` 缺省取 `manifest_url()`）。支持 `file://` —— 测试与局域网共享用得上。"""
    target = (url if url is not None else manifest_url()).strip()
    if not target:
        raise PackError("还没配置素材源（`[assets] manifest_url` 为空）")
    px = proxy_url() if proxy is None else proxy
    try:
        with _opener(px).open(Request(target, headers={"Accept": "application/json"}),
                              timeout=timeout) as resp:
            body = resp.read()
    except PackError:
        raise
    except Exception as e:                     # 网络错误种类太多，统一折成 PackError
        raise PackError(f"清单取不到: {target}（{type(e).__name__}: {e}）") from e
    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise PackError(f"清单不是合法 JSON: {target}（{e}）") from e
    return parse_manifest(raw, source=target)


def pack_url(manifest: Manifest, pack: Pack) -> str:
    """zip 的绝对地址（相对名按清单地址解析）。"""
    if urlparse(pack.zip).scheme:
        return pack.zip
    return urljoin(manifest.source, pack.zip)


# ---------------------------------------------------------------------------
# 本地状态
# ---------------------------------------------------------------------------


def local_state(pack: Pack, assets_root: Path) -> tuple[str, int, int]:
    """`("installed" | "partial" | "missing", 已存在件数, 总件数)` —— 逐文件 stat。"""
    present = 0
    for rel, size in pack.files:
        path = assets_root / rel
        try:
            if path.is_file() and path.stat().st_size == size:
                present += 1
        except OSError:
            pass
    total = len(pack.files)
    if present == total:
        return "installed", present, total
    if present == 0:
        return "missing", 0, total
    return "partial", present, total


# ---------------------------------------------------------------------------
# 下载 / 校验 / 解压
# ---------------------------------------------------------------------------


def download(url: str, dest: Path, *, expect_sha256: str, expect_bytes: int,
             timeout: float = DEFAULT_TIMEOUT, proxy: str = "",
             progress: Progress | None = None, pack_id: str = "",
             cancel: threading.Event | None = None) -> Path:
    """流式下载到 `dest`（先写 `.part`），字节数与 sha256 都对上才改名。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    digest = hashlib.sha256()
    received = 0
    total = expect_bytes
    try:
        with _opener(proxy).open(Request(url), timeout=timeout) as resp, part.open("wb") as fh:
            header = resp.headers.get("Content-Length") if resp.headers else None
            if header and header.isdigit():
                total = int(header)
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled("已取消")
                block = resp.read(_CHUNK)
                if not block:
                    break
                fh.write(block)
                digest.update(block)
                received += len(block)
                if progress is not None:
                    progress(pack_id, "downloading", received, total)
        if expect_bytes and received != expect_bytes:
            raise PackError(f"字节数不符: 期望 {expect_bytes}，收到 {received}")
        if expect_sha256 and digest.hexdigest() != expect_sha256:
            raise PackError(f"sha256 不符: 期望 {expect_sha256[:12]}…，实际 {digest.hexdigest()[:12]}…")
        part.replace(dest)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return dest


def extract(zip_path: Path, assets_root: Path, *, pack_id: str = "",
            progress: Progress | None = None) -> int:
    """解压到 assets 根（逐条防穿越）。返回写入件数。"""
    root = assets_root.resolve()
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        members = [i for i in zf.infolist() if not i.is_dir()]
        for info in members:
            target = (root / info.filename).resolve()
            if root not in target.parents:
                raise PackError(f"zip 内路径越界: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, _CHUNK)
            count += 1
            if progress is not None:
                progress(pack_id, "extracting", count, len(members))
    return count


def install(manifest: Manifest, pack_ids: list[str], assets_root: Path, work_dir: Path,
            *, proxy: str | None = None, timeout: float = DEFAULT_TIMEOUT,
            progress: Progress | None = None,
            cancel: threading.Event | None = None) -> list[Outcome]:
    """按顺序装若干包。**单包失败不中断其余**（宁缺勿错），结果逐包返回。"""
    px = proxy_url() if proxy is None else proxy
    outcomes: list[Outcome] = []
    work_dir.mkdir(parents=True, exist_ok=True)
    for pack_id in pack_ids:
        pack = manifest.get(pack_id)
        if pack is None:
            outcomes.append(Outcome(pack_id, False, error="清单里没有这个包"))
            continue
        zip_path = work_dir / (pack.zip or f"{pack.id.replace('.', '_')}.zip")
        try:
            download(pack_url(manifest, pack), zip_path,
                     expect_sha256=pack.zip_sha256, expect_bytes=pack.zip_bytes,
                     timeout=timeout, proxy=px, progress=progress,
                     pack_id=pack.id, cancel=cancel)
            if progress is not None:
                progress(pack.id, "verifying", pack.zip_bytes, pack.zip_bytes)
            count = extract(zip_path, assets_root, pack_id=pack.id, progress=progress)
            outcomes.append(Outcome(pack.id, True, files=count, bytes=pack.bytes))
            if progress is not None:
                progress(pack.id, "done", count, pack.file_count)
        except Cancelled:
            outcomes.append(Outcome(pack_id, False, error="已取消"))
            if progress is not None:
                progress(pack.id, "error", 0, 0)
            break
        except PackError as e:
            outcomes.append(Outcome(pack.id, False, error=str(e)))
            if progress is not None:
                progress(pack.id, "error", 0, 0)
        except Exception as e:                 # noqa: BLE001 — 磁盘满 / 权限也归这里
            outcomes.append(Outcome(pack.id, False, error=err("PackIO", f"{type(e).__name__}: {e}")))
            if progress is not None:
                progress(pack.id, "error", 0, 0)
        finally:
            zip_path.unlink(missing_ok=True)
    return outcomes


__all__ = [
    "MANIFEST_ENV",
    "Cancelled",
    "Manifest",
    "Outcome",
    "Pack",
    "PackError",
    "install",
    "local_state",
    "manifest_url",
    "pack_url",
    "parse_manifest",
    "proxy_url",
    "read_manifest",
]
