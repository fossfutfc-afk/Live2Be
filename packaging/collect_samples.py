"""挑出**开箱能玩**的最小样张 —— 全量 assets 是 448 MB，装不进安装包。

清单（改这里 = 改"第一印象里有什么"）:

| 类 | 范围 | 约 |
|---|---|---|
| 登录页背景 `menu/` | 全给（含 logo 与 vol2.0 轮播） | 18 MB |
| 角色立绘 `illustration/` | **一个角色全给**（含 `ref/`：纪念生图的参考图） | 70 MB |
| 场景背景 `background/` | 两个最常见的分类全给 + 学校类抽若干张 | 21 MB |

抽样只用文件名排序（可复现，不随机）: 换机器、换时间跑出来的包必须是同一份清单，
否则"我这边能看到的背景"会变成不可解释的差异。

用法::

    python packaging/collect_samples.py --src assets --dry-run          # 只报清单与体积
    python packaging/collect_samples.py --src assets --dst dist/Live2Be/assets

不足的地方由渲染层自己兜底（找不到背景/立绘就退化成纯文字 + 默认底图），不报错。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

#: 整目录全带的分类
BACKGROUND_DIRS = ("SDIR_Atmosphere", "SDIR_Clubs")
#: 抽样带的分类 → 张数（按文件名排序取前 N）
BACKGROUND_SAMPLE = {"SDIR_Schools": 40}
#: 立绘只带这些角色（`ref/` 也带：纪念生图要用参考图）
ILLUSTRATIONS = ("igusa_haruka",)
#: 登录页背景整目录带
MENU_DIR = "menu"


def plan(src: Path) -> list[tuple[Path, Path]]:
    """`[(源文件, 目标相对路径)]` —— 不碰磁盘, 只算清单。"""
    out: list[tuple[Path, Path]] = []

    def add_dir(d: Path) -> None:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                out.append((f, f.relative_to(src)))

    menu = src / MENU_DIR
    if menu.is_dir():
        add_dir(menu)

    for char in ILLUSTRATIONS:
        d = src / "illustration" / char
        if d.is_dir():
            add_dir(d)

    bg = src / "background"
    for name in BACKGROUND_DIRS:
        d = bg / name
        if d.is_dir():
            add_dir(d)
    for name, count in BACKGROUND_SAMPLE.items():
        d = bg / name
        if not d.is_dir():
            continue
        files = [f for f in sorted(d.rglob("*")) if f.is_file()]
        for f in files[:count]:
            out.append((f, f.relative_to(src)))
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
    parser = argparse.ArgumentParser(prog="collect_samples")
    parser.add_argument("--src", default="assets", help="仓库 assets/ 目录")
    parser.add_argument("--dst", default="dist/Live2Be/assets", help="拷到哪")
    parser.add_argument("--dry-run", action="store_true", help="只报清单与体积")
    args = parser.parse_args(argv)

    src = Path(args.src)
    if not src.is_dir():
        print(f"找不到 {src}（样张从仓库的 assets/ 里挑，打包机上要有它）", file=sys.stderr)
        return 2
    items = plan(src)
    size = sum(f.stat().st_size for f, _ in items)
    print(f"样张: {len(items)} 个文件 · {size / 1024 / 1024:.1f} MB")
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
