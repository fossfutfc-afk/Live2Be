# guidance — 角色卡写作指导（Human / LLM 共读）

本目录教你怎么为 Live2Be 写一个角色。

> 角色卡作者的最低心智模型：你只需要回答四个问题 ——
> 1. 她看起来什么样？（`profile.yml`）
> 2. 她是什么性格？（`personality.yml`）
> 3. 她知道些什么？（`knowledge.yml`）
> 4. 她经历过什么？（`experience.yml`）
>
> 程序注入她的人设（1-3）+ 背景经历（4，原文直注 —— **她游戏开始前的人生，引擎不改编，
> LLM 扮演时自然内化**）。每一次互动产生的新记忆由 digest 整理进角色的图记忆（wiki），
> 随经历自然演化。

## 文件索引

| 文件 | 讲什么 |
|---|---|
| [CHARACTER.md](CHARACTER.md) | **从零配一个角色**：要占哪几个位置 · YAML 怎么写 · `REQ~` / `SIG~` 前缀 · `emotions.yml`（表情 → 图片）· spine 与 sprite 二选一（**做 OC 没有 spine 怎么办**）· `interperson.yml` · `mmt_registry.toml` · 最小可跑清单 · 自检 |
| 各配置文件 | 逐个 `<文件名>.md` 陆续补充中 |

写之前先看一遍 `config/characters/igusa_haruka/` —— 那是最完整的一份实例。

注意两条容易踩的：

- `experience.yml` 的**条目顺序 = 注入展示顺序**（默认取前 6 条），想突出的经历放前面
- 旧 `beliefs.yml` 出厂认知层已随 2026-09-05 运行时解耦归档，见 `archive/factory_memory/`
