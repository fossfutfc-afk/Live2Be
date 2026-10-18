"""把 `assets/` 切成可下载的包 —— 产物是 zip + `manifest.json`，喂给首次运行向导。

包口径（改这里 = 改"用户第一次要下多少"）:

| 包 | 范围 | 约 |
|---|---|---|
| `char.<id>` | `illustration/<id>/default/`（差分 + 头像 + spine + emotions.yml） | 20-48 MB |
| `char.<id>.ref` | `illustration/<id>/ref/`（纪念生图的参考图） | 16 MB |
| `char.<id>.outfits` | `illustration/<id>/` 其余外观目录（dress/newyear/suit/possession） | 15 MB |
| `bg.place_table` | 地点表 `files` 声明的每一张背景 | 100 MB |
| `menu.vol2` | 登录页轮播图（`/api/menu` 读它） | 18 MB |

口径的三条理由:

1. **只有 `default/` 是必备外观** —— `MediaCatalog` 用 `outfit="default"` 起步，缺这个目录
   角色就点不出来；`ref/` 与变装是可选功能，单独成包，别让不想生图的人白下 16 MB。
2. **背景按地点表切，不按磁盘全量** —— 表里 `files` 声明的 435 张才是引擎会引用的；
   磁盘另有 663 张没人引用（151 MB）。要收全的人自己下全量包不加进来，是有意的。
3. **没有立绘的角色不打空包** —— 向导据此显示"无素材"，而不是给一个 0 字节的包。

zip 内路径与 `assets/` 同构（`illustration/…`、`background/…`）⇒ 解压目标恒为 assets 根，
**读取侧不需要认识"包"这个概念**。清单里记了每个文件的相对路径与大小，运行时就靠 stat
这些路径判断装没装，不另存状态文件（用户手动删图后状态立刻自愈）。

产物可复现：zip 内条目时间戳固定为 1980-01-01，同样输入两次跑出同一个 sha256。

用法::

    python packaging/make_packs.py --src assets --dst dist/packs --dry-run
    python packaging/make_packs.py --src assets --dst dist/packs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: 有立绘的预设角色（其余角色卡能读，但没有图 —— 不打空包）
PRESET_CHARACTERS = ("igusa_haruka", "asagi_mutsuki", "rikuhachima_aru", "onikata_kayoko")
#: 必备外观目录
BASE_OUTFIT = "default"
#: 不算外观的兄弟目录（生图参考图单独成包）
REF_DIR = "ref"
#: 背景包：地点表在 config/ 里的相对位置
PLACE_TABLE_REL = Path("settings") / "world" / "place_entities.json"
#: 登录页轮播
MENU_CAROUSEL = "vol2.0"

_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


@dataclass
class Pack:
    """一个可下载单元。`files` 是源文件绝对路径，`root` 是 zip 内路径的基准。"""

    id: str
    kind: str
    group: str
    title: str
    files: list[Path]
    root: Path

    def entries(self) -> list[tuple[str, int]]:
        return [(f.relative_to(self.root).as_posix(), f.stat().st_size) for f in self.files]

    def total_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.files)


def _walk(root: Path) -> list[Path]:
    """目录下所有文件（排序保证可复现；跳过 `__pycache__` 之类）。"""
    if not root.is_dir():
        return []
    return [
        f for f in sorted(root.rglob("*"))
        if f.is_file() and not any(p.startswith((".", "__")) for p in f.relative_to(root).parts)
    ]


def _display_name(config_root: Path, char_id: str) -> str:
    """`profile.yml` 的 `most_called_name` —— 有中文名就用中文名，读不到退回 id。"""
    profile = config_root / "characters" / char_id / "profile.yml"
    try:
        for line in profile.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition(":")
            if sep and "most_called_name" in key:
                return value.strip().strip("'\"") or char_id
    except OSError:
        pass
    return char_id


def character_packs(assets: Path, config: Path) -> list[Pack]:
    """每个角色一个必备包；`ref/` 与变装在有料时才单独成包。"""
    packs: list[Pack] = []
    for char_id in PRESET_CHARACTERS:
        char_dir = assets / "illustration" / char_id
        name = _display_name(config, char_id)
        base = char_dir / BASE_OUTFIT
        packs.append(Pack(
            id=f"char.{char_id}", kind="character", group="角色立绘",
            title=name, files=_walk(base), root=assets,
        ))
        ref_files = _walk(char_dir / REF_DIR)
        if ref_files:
            packs.append(Pack(
                id=f"char.{char_id}.ref", kind="character", group="角色立绘",
                title=f"{name}·生图参考", files=ref_files, root=assets,
            ))
        others = sorted(
            d for d in char_dir.iterdir()
            if d.is_dir() and d.name not in (BASE_OUTFIT, REF_DIR) and not d.name.startswith((".", "__"))
        ) if char_dir.is_dir() else []
        outfit_files = [f for d in others for f in _walk(d)]
        if outfit_files:
            packs.append(Pack(
                id=f"char.{char_id}.outfits", kind="character", group="角色立绘",
                title=f"{name}·变装（{'/'.join(d.name for d in others)}）",
                files=outfit_files, root=assets,
            ))
    return packs


def background_pack(assets: Path, config: Path) -> Pack:
    """地点表 `files` 声明的每一张背景（去重保序）。"""
    from core.media.place_table import load_table

    table = load_table(config / PLACE_TABLE_REL)
    if not table:
        raise SystemExit(f"地点表读不出来: {table.error}（背景包无从切起）")

    root = assets / "background"
    files: list[Path] = []
    seen: set[str] = set()
    missing: list[str] = []
    for entry in table.all():
        for rel, _label in entry.image_candidates():
            if rel in seen:
                continue
            seen.add(rel)
            path = root / rel
            if path.is_file():
                files.append(path)
            else:
                missing.append(rel)
    if missing:
        print(f"[注意] 地点表声明了 {len(missing)} 张磁盘上没有（不进包）:", file=sys.stderr)
        for rel in missing[:10]:
            print(f"    {rel}", file=sys.stderr)
        if len(missing) > 10:
            print(f"    … 另有 {len(missing) - 10} 张", file=sys.stderr)
    return Pack(
        id="bg.place_table", kind="background", group="场景背景",
        title=f"地点表引用的 {len(files)} 张背景", files=files, root=assets,
    )


def menu_pack(assets: Path) -> Pack | None:
    files = _walk(assets / "menu" / MENU_CAROUSEL)
    if not files:
        return None
    return Pack(
        id="menu.vol2", kind="menu", group="登录页",
        title="登录页轮播图", files=files, root=assets,
    )


def write_zip(pack: Pack, dst: Path) -> dict:
    """打一个 zip，返回它的清单条目（含 sha256）。"""
    name = pack.id.replace(".", "_") + ".zip"
    out = dst / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src in pack.files:
            info = zipfile.ZipInfo(src.relative_to(pack.root).as_posix(), date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, src.read_bytes())
    digest = hashlib.sha256()
    with out.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    entries = pack.entries()
    return {
        "id": pack.id,
        "kind": pack.kind,
        "group": pack.group,
        "title": pack.title,
        "zip": name,
        "zip_bytes": out.stat().st_size,
        "zip_sha256": digest.hexdigest(),
        "bytes": sum(size for _, size in entries),
        "file_count": len(entries),
        "files": [[rel, size] for rel, size in entries],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_packs")
    parser.add_argument("--src", default="assets", help="仓库 assets/ 目录")
    parser.add_argument("--config", default="config", help="仓库 config/ 目录（读地点表与角色名）")
    parser.add_argument("--dst", default="dist/packs", help="zip 与 manifest.json 落到哪")
    parser.add_argument("--dry-run", action="store_true", help="只报包清单，不写任何文件")
    args = parser.parse_args(argv)

    assets = Path(args.src)
    config = Path(args.config)
    if not assets.is_dir():
        print(f"找不到 {assets}（包从仓库的 assets/ 里切）", file=sys.stderr)
        return 2

    packs = character_packs(assets, config)
    packs.append(background_pack(assets, config))
    carousel = menu_pack(assets)
    if carousel is not None:
        packs.append(carousel)

    empty = [p.id for p in packs if not p.files]
    packs = [p for p in packs if p.files]
    if empty:
        print(f"[注意] 这些包没有文件，已跳过: {', '.join(empty)}", file=sys.stderr)

    if args.dry_run:
        print(f"{'包':<28} {'件数':>5} {'原始':>10} {'压缩后':>10}")
        for p in packs:
            print(f"{p.id:<28} {len(p.files):>5} {p.total_bytes() / 1048576:>9.1f}M {'—':>10}")
        print(f"{'合计':<28} {sum(len(p.files) for p in packs):>5} "
              f"{sum(p.total_bytes() for p in packs) / 1048576:>9.1f}M")
        return 0

    dst = Path(args.dst)
    dst.mkdir(parents=True, exist_ok=True)
    entries = [write_zip(p, dst) for p in packs]
    manifest = {
        "schema": 1,
        "generated": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
        "packs": entries,
    }
    path = dst / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for e in entries:
        print(f"{e['id']:<28} {e['file_count']:>5}件 "
              f"{e['bytes'] / 1048576:>8.1f}M → {e['zip_bytes'] / 1048576:>8.1f}M  {e['zip']}")
    print(f"manifest → {path}（{path.stat().st_size / 1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
