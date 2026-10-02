# archive/factory_memory — 出厂记忆预处理链（已归档, 2026-09-05）

> **为什么归档**: 调研主流项目（Letta Memory Blocks / SillyTavern 角色卡 / 图记忆系）
> 后定稿——**作者的预置内容 = 直注上下文**（persona 块/description/背景文本原文,
> LLM 扮演时自然内化第一人称）, 图记忆/节点只存运行时发生的事。出厂经历
> （experience.yml）是作者人设描述的一部分, **不是"待改编成记忆节点"的中间产物**。
>
> 2026-09-05 运行时解耦落地（`4290f3e` + `ece0747`）: 主进程删除全部 seed 调用,
> 注入段 = 出厂背景（`render_background_experience`: experience.yml 原文直注 cap 6,
> 第三人称不转换）+ 运行时 wiki（digest 产物）。此目录所有文件仅供历史参考/创作
> 辅助复用, **不在主进程中使用, 不保证可独立运行**（import 路径已随搬迁失效）。

## 内容

| 文件 | 原位置 | 是什么 |
|---|---|---|
| `seed_engine.py` | core/brain/seed.py | 出厂 seed v3/v4（原文兜底 + brain_seed.yml 定稿复制 + beliefs.yml 解析 + 快照） |
| `seed_digest_prompt.md` | llm/prompts/seed_digest.md | 出厂经历改编员 prompt（v2 记忆化重构版——逐条/人设锚/禁句式镜像） |
| `seed_digest_cli.py` | tools/seed_digest.py | 逐条 LLM 改编工具（temp 0.3/重试/校验/防覆盖）——**可作创作辅助参考**（背景文本润色思路仍有效） |
| `brain_seed_haruka.yml` | config/characters/igusa_haruka/brain_seed.yml | 遥香 12 条改编 v2 稿（记忆化重构, 用户评价质量过关但路线废弃） |
| `brain_seed_haruka_v1.yml.bak` | 同目录 .bak | v1 翻译式稿（对照用） |
| `beliefs_guidance.md` | guidance/beliefs.md | beliefs.yml 写作手册（出厂认知层——beliefs 出厂预置 vs 涌现待定, 见 DESIGN_WORLD §9.6） |
| `smoke_digest_v2.py` | experiments/ | 出厂 seed + digest 冒烟实验 |
| `tests/` | tests/core + tests/tools | 对应测试（pytest 不收集——不在 testpaths） |

## 可复用资产（若未来重启）

1. **seed_digest prompt 的"记忆化重构"规则**（禁句式镜像/语气像她/点评句剥离）——
   若要做"背景文本润色"类创作辅助（IDE/工具让 AI 把作者草稿重写成作者想要的口吻）,
   规则与三版示范直接可用
2. **逐条调用 + 人设锚注入 + 相似度/浓缩校验**——任何"LLM 处理角色卡文本"工具的模式
3. `_collect_yml_leaves`（yml → 叶子收集）已内迁 core/brain/render.py
   （render_background_experience 在用）
4. brain_seed_haruka.yml 若未来想让遥香的背景注入就是润色版, 可人工把内容并回
   experience.yml（或做直注前的可选增强源）

## 关联决策

- DESIGN_WORLD.md §9.5（出厂记忆实例化 = 显式整理 → 后随解耦改为 yml 直注, 见 TODO）
- git 历史完整保留所有演进（v1 定稿制 → v2 记忆化 → 解耦归档）
