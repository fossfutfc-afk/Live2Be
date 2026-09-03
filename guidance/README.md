# guidance — 角色卡写作指导（Human / LLM 共读）

本目录教你怎么为 Live2Be 写一个角色。每个文件对应 config/characters/{角色}/ 下的一个
配置文件，讲清楚**它是什么、怎么写、写成什么样算好**。

> 角色卡作者的最低心智模型：
> 你只需要回答五个问题——
> 1. 她看起来什么样？（profile.yml）
> 2. 她是什么性格？（personality.yml）
> 3. 她知道些什么？（knowledge.yml）
> 4. 她经历过什么？（experience.yml）
> 5. 她怎么理解这些经历？（beliefs.yml）
>
> 程序会把 4 和 5 自动整理成角色的出厂记忆（wiki 图式），
> 之后的每一次互动，系统会让角色的记忆随经历自然演化。

## 文件索引

| 文件 | 讲什么 |
|------|--------|
| [beliefs.md](beliefs.md) | beliefs.yml —— 出厂认知（角色对经历的理解结论） |

（其余配置文件的指导陆续补充中——写作顺序建议：先 experience.yml，再 beliefs.yml，
因为 beliefs 要引用 experience 的条目。）
