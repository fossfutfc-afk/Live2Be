# -*- coding: utf-8 -*-
"""纪念立绘生图速度实验 — 给本地 SD1.5 一段总结性描述, 测生成耗时（2026-08-24）。

目的（用户决策, 预判式 memorial 设计讨论点 3）:
    预判式设计下, 若本地生图模型对"总结性描述"生成够快, 剧情中 LLM 可自由发挥
    （当场生图兜底也可接受）。测:
      1) 首次生成（含 pipe 懒加载 from_pretrained）总耗时
      2) 二次生成（pipe 复用）纯生成耗时
      3) 15 步 vs 20 步耗时对比

用法: python experiments/memorial_gen_speed.py（需 live2be env: torch/diffusers 已装）
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.image_gen import ImageGenerator

# 总结性描述样例（从真实 bond 剧情提炼的场景定格——模拟"主 LLM 安排的场景"）
PROMPT = (
    "傍晚的天台上，一个黑色长发的少女抱着淡蓝色的花盆站在晚风里，"
    "回眸微笑，眼里带着不舍与期待，夕阳柔光洒在她身上，唯美构图，"
    "日系动画风格，精致细节"
)


def main() -> None:
    gen = ImageGenerator()
    print(f"模型: {gen.model_path}")
    print(f"输出目录: {gen.output_dir}")

    # 1) 首次: 含模型懒加载（from_pretrained, 首次 ~10s）
    t0 = time.perf_counter()
    path = gen.generate(PROMPT, steps=20, seed=42)
    t1 = time.perf_counter()
    print(f"\n首次生成（含 pipe 加载）: {t1 - t0:.2f}s")
    print(f"  输出: {path}")
    print(f"  图存在: {path.is_file()}, 大小: {path.stat().st_size / 1024:.0f} KB")

    # 2) 二次: pipe 已缓存, 纯生成耗时
    t2 = time.perf_counter()
    path2 = gen.generate(PROMPT, steps=20, seed=42)
    t3 = time.perf_counter()
    print(f"二次生成（pipe 复用, 20 步）: {t3 - t2:.2f}s")

    # 3) 15 步对比
    t4 = time.perf_counter()
    gen.generate(PROMPT, steps=15, seed=42)
    t5 = time.perf_counter()
    print(f"三次生成（15 步）: {t5 - t4:.2f}s")

    print("\n参考结论: 预判→后台线程生图, 玩家互动期（读开场+选选项）足以覆盖首次 12s+;")


if __name__ == "__main__":
    main()
