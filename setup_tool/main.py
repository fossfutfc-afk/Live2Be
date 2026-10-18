"""入口 —— `python -m setup_tool`（开发）/ `Live2BeSetup.exe`（打包）。

没有参数就是开界面；`--check` 只在控制台打一遍体检结果（给脚本/排障用，不开窗口）。
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="Live2BeSetup")
    parser.add_argument("--check", action="store_true",
                        help="只做体检并打印（不开窗口；适合脚本 / 排障）")
    parser.add_argument("--no-embedding", action="store_true",
                        help="体检时不探 embedding 服务（更快）")
    args = parser.parse_args(argv)

    from setup_tool import checks

    if args.check:
        result = checks.run_all(probe_embedding=not args.no_embedding)
        for c in result:
            print(c.line())
        s = checks.summary(result)
        print(f"\n共 {len(result)} 项：正常 {s['ok']} · 注意 {s['warn']} · 问题 {s['bad']}")
        return 1 if s["bad"] else 0

    try:
        from setup_tool import ui
    except ImportError as e:                     # 极简环境下没有 tkinter
        print(f"界面起不来（缺 tkinter: {e}）—— 用 `--check` 走控制台体检", file=sys.stderr)
        return 2
    ui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
