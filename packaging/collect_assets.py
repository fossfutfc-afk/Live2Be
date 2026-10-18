"""挑出**随包发布的 `assets/`** —— 全量 448 MB 装不进安装包。

两种口径（`--mode`）:

| mode | 带什么 | 约 |
|---|---|---|
| `minimal`（默认） | 少了它就**报错或破相**的那几样: 每个角色的 `emotions.yml`（表情标注词表进 prompt）、登录页 `menu/logo` 与 `menu/default`、`_director_whitelist.json` | 0.3 MB |
| `sample` | `minimal` 那些 + 一个角色的全套立绘（含 `ref/`）+ 若干背景分类（"不用联网也能看"的样张） | 106 MB |

**立绘与背景的常规来源是素材包**（`packaging/make_packs.py` 切、第一次运行时由向导下载），
所以默认不随包走。`sample` 只服务一个场景: 想发一个"装上就能看见画面"的预览版。

抽样只用文件名排序（可复现，不随机）: 换机器、换时间跑出来的包必须是同一份清单，
否则"我这边能看到的背景"会变成不可解释的差异。

不足的地方由渲染层自己兜底（找不到背景/立绘就退化成纯文字 + 默认底图），不报错。

用法::

    python packaging/collect_assets.py --mode minimal --dry-run
    python packaging/collect_assets.py --mode minimal --dst dist/Live2Be/assets
    python packaging/collect_assets.py --mode sample  --dst dist/Live2Be/assets
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

#: 少了就报错的根级文件
ALWAYS = ("_director_whitelist.json",)
#: 登录页直接引用的两个 menu 子目录（logo 是图标, default 是主界面背景）
MENU_MUST = ("logo", "default")

#: sample 口径: 整目录全带的分类
BACKGROUND_DIRS = ("SDIR_Atmosphere", "SDIR_Clubs")
#: sample 口径: 抽样带的分类 → 张数（按文件名排序取前 N）
BACKGROUND_SAMPLE = {"SDIR_Schools": 40}
#: sample 口径: 立绘只带这些角色（`ref/` 也带: 纪念生图要用参考图）
ILLUSTRATIONS = ("igusa_haruka",)

MODES = ("minimal", "sample")


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


def _sample(src: Path) -> list[tuple[Path, Path]]:
    out = _minimal(src)
    for char in ILLUSTRATIONS:
        _add_dir(out, src, src / "illustration" / char)
    background = src / "background"
    for name in BACKGROUND_DIRS:
        _add_dir(out, src, background / name)
    for name, count in BACKGROUND_SAMPLE.items():
        directory = background / name
        if not directory.is_dir():
            continue
        files = [f for f in sorted(directory.rglob("*")) if f.is_file()]
        for f in files[:count]:
            out.append((f, f.relative_to(src)))
    return out


def plan(src: Path, mode: str = "minimal") -> list[tuple[Path, Path]]:
    """`[(源文件, 目标相对路径)]` —— 不碰磁盘, 只算清单。"""
    if mode == "minimal":
        return _minimal(src)
    if mode == "sample":
        return _sample(src)
    raise ValueError(f"mode 只能是 {MODES}，收到 {mode!r}")


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
    parser.add_argument("--dst", default="dist/Live2Be/assets", help="拷到哪")
    parser.add_argument("--mode", default="minimal", choices=MODES,
                        help="minimal = 只带不报错的那几样（默认）; sample = 再带一套样张")
    parser.add_argument("--dry-run", action="store_true", help="只报清单与体积")
    args = parser.parse_args(argv)

    src = Path(args.src)
    if not src.is_dir():
        print(f"找不到 {src}（清单从仓库的 assets/ 里挑，打包机上要有它）", file=sys.stderr)
        return 2
    items = plan(src, args.mode)
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
