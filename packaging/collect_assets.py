"""挑出**随包发布的 `assets/`** —— 全量 448 MB，而产品真正读的只有一小半。

两种口径（`--mode`）:

| mode | 带什么 | 约 |
|---|---|---|
| `full`（默认） | 四角色的 `spine/` + `portrait/`（含变装）、地点表声明的 435 张背景、登录页（logo + 主界面背景 + 轮播） | 159 MB |
| `minimal` | 只带"少了就报错或破相"的那几样: 每个角色的 `emotions.yml`、登录页 `menu/{logo,default}`、`_director_whitelist.json` | 0.4 MB |

口径的两条依据（都是实测，不是估）:

1. **`diff/` 不带** —— 119 MB，占角色素材 74%，只有 `cli/` 的 `play_diff()` 读它；
   web 壳走 `spine/`（骨骼）+ `portrait/`（头像）。`catalog._scan_character` 在 diff 缺文件时
   `static_path=None`、spine 照给，`tests/core/test_media.py` 有现成断言钉着。
2. **背景只带地点表声明的那 435 张** —— 磁盘另有 663 张没人引用（151 MB）。
   表里 `files` 的路径就是记录，拿它对磁盘即可，不猜。

`ref/`（纪念生图参考图，16 MB）也不带: 只有生图那一路用它，缺了降级成纯文本。

清单按文件名排序（可复现，不随机）: 换机器、换时间跑出来的包必须是同一份清单。
缺图不报错：渲染层退化到纯文字 / 默认底图。

用法::

    python packaging/collect_assets.py --dry-run
    python packaging/collect_assets.py --dst dist/Live2Be/assets
    python packaging/collect_assets.py --mode minimal --dst dist/Live2Be-Slim/assets
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

#: 读地点表要 `core.media`，而按脚本路径直接跑时仓根不在 sys.path（脚本目录是 packaging/）
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: 少了就报错的根级文件
ALWAYS = ("_director_whitelist.json",)
#: 登录页直接引用的两个 menu 子目录（logo 是图标, default 是主界面背景）
MENU_MUST = ("logo", "default")
#: full 口径: 登录页轮播（`/api/menu` 读它）
MENU_CAROUSEL = "vol2.0"

#: full 口径: 有立绘的预设角色（其余角色卡能读，但没有图 —— 不打空目录）
FULL_CHARACTERS = ("igusa_haruka", "asagi_mutsuki", "rikuhachima_aru", "onikata_kayoko")
#: full 口径: 角色目录里**不带**的子目录（diff 只有 CLI 用; ref 只有生图参考用）
FULL_SKIP = frozenset({"diff", "ref"})
#: 地点表在 config/ 里的相对位置
PLACE_TABLE_REL = Path("settings") / "world" / "place_entities.json"

MODES = ("full", "minimal")


def _add_dir(out: list[tuple[Path, Path]], src: Path, directory: Path) -> None:
    if not directory.is_dir():
        return
    for f in sorted(directory.rglob("*")):
        if f.is_file():
            out.append((f, f.relative_to(src)))


def _minimal(src: Path) -> list[tuple[Path, Path]]:
    out: list[tuple[Path, Path]] = []
    for name in ALWAYS:
        path = src / name
        if path.is_file():
            out.append((path, Path(name)))
    for yml in sorted(src.glob("illustration/*/*/emotions.yml")):
        out.append((yml, yml.relative_to(src)))
    for name in MENU_MUST:
        _add_dir(out, src, src / "menu" / name)
    return out


def declared_backgrounds(config: Path) -> list[str]:
    """地点表 `files` 声明的每一张背景（去重保序）。表读不出来 → 空列表。"""
    from core.media.place_table import load_table

    table = load_table(config / PLACE_TABLE_REL)
    if not table:
        return []
    seen: set[str] = set()
    rels: list[str] = []
    for entry in table.all():
        for rel, _label in entry.image_candidates():
            if rel not in seen:
                seen.add(rel)
                rels.append(rel)
    return rels


def _full(src: Path, config: Path) -> list[tuple[Path, Path]]:
    out = _minimal(src)
    for char in FULL_CHARACTERS:
        char_dir = src / "illustration" / char
        if not char_dir.is_dir():
            continue
        for f in sorted(char_dir.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(src)
            if FULL_SKIP & set(rel.parts):
                continue
            out.append((f, rel))

    root = src / "background"
    missing: list[str] = []
    for rel in declared_backgrounds(config):
        path = root / rel
        if path.is_file():
            out.append((path, Path("background") / rel))
        else:
            missing.append(rel)
    if missing:
        print(f"[注意] 地点表声明了 {len(missing)} 张磁盘上没有（不进包）:", file=sys.stderr)
        for rel in missing[:10]:
            print(f"    {rel}", file=sys.stderr)
        if len(missing) > 10:
            print(f"    … 另有 {len(missing) - 10} 张", file=sys.stderr)

    _add_dir(out, src, src / "menu" / MENU_CAROUSEL)
    return out


def plan(src: Path, mode: str = "full", *, config: Path | None = None) -> list[tuple[Path, Path]]:
    """`[(源文件, 目标相对路径)]` —— 不碰磁盘, 只算清单。目标路径去重。"""
    if mode == "minimal":
        items = _minimal(src)
    elif mode == "full":
        items = _full(src, config or src.parent / "config")
    else:
        raise ValueError(f"mode 只能是 {MODES}，收到 {mode!r}")
    # `_full` 从 `_minimal` 起手, 所以每个角色的 emotions.yml 会出现两次（内容相同）。
    # 去重是为了"清单件数 == 落盘件数"——数量对不上时没人能一眼看出是重复还是漏拷。
    seen: set[str] = set()
    out: list[tuple[Path, Path]] = []
    for source, rel in items:
        key = rel.as_posix()
        if key not in seen:
            seen.add(key)
            out.append((source, rel))
    return out


def run(items: list[tuple[Path, Path]], dst: Path) -> tuple[int, int]:
    """按清单拷贝。返回 (文件数, 字节数)。"""
    total = 0
    for source, rel in items:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        total += source.stat().st_size
    return len(items), total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collect_assets")
    parser.add_argument("--src", default="assets", help="仓库 assets/ 目录")
    parser.add_argument("--config", default="config", help="仓库 config/ 目录（读地点表）")
    parser.add_argument("--dst", default="dist/Live2Be/assets", help="拷到哪")
    parser.add_argument("--mode", default="full", choices=MODES,
                        help="full = 产品真正读的全部（默认）; minimal = 只带不报错的那几样")
    parser.add_argument("--dry-run", action="store_true", help="只报清单与体积")
    args = parser.parse_args(argv)

    src = Path(args.src)
    if not src.is_dir():
        print(f"找不到 {src}（清单从仓库的 assets/ 里挑，打包机上要有它）", file=sys.stderr)
        return 2
    items = plan(src, args.mode, config=Path(args.config))
    size = sum(f.stat().st_size for f, _ in items)
    print(f"[{args.mode}] {len(items)} 个文件 · {size / 1024 / 1024:.1f} MB")
    if args.dry_run:
        for _, rel in items[:8]:
            print(f"  {rel.as_posix()}")
        if len(items) > 8:
            print(f"  … 另有 {len(items) - 8} 个")
        return 0
    n, total = run(items, Path(args.dst))
    print(f"已拷 {n} 个文件（{total / 1024 / 1024:.1f} MB）→ {args.dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
