# -*- coding: utf-8 -*-
"""羁绊剧情存档只读回放 — 无 LLM, 纯渲染存档 scenes[]。

用法:
    python experiments/replay_bond.py            # 回放最近一份存档
    python experiments/replay_bond.py <存档路径> # 回放指定存档

验证对象: 契约 JSON 副产物存档（data/saves/bond_story_*.json）能被
BondScene.from_dict 逐条解析渲染——一解析器两用（运行时 + 回放）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bond.bond_save import list_saves, load_save
from core.ui.vn_cli import replay_bond_story


def main() -> None:
    if len(sys.argv) > 1:
        save_path = Path(sys.argv[1])
    else:
        saves = list_saves()
        if not saves:
            print("没有找到任何羁绊剧情存档（data/saves/bond_story_*.json）。")
            sys.exit(1)
        save_path = saves[-1]                     # 最近一份
        print(f"自动取最近存档: {save_path}")

    if not load_save(save_path):
        print(f"[系统] 无法读取存档: {save_path}")
        sys.exit(1)
    replay_bond_story(save_path)


if __name__ == "__main__":
    main()
