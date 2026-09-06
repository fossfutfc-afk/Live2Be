# 背景系统：组织形式与查询框架（DESIGN_PLACE, 2026-09-05 定稿）

> 触发：资产 1094 张 / 620 scene_id——LLM 无法面对全量; 地点语义（杂草屋=破房子）
> 不在资产名里; 背景单调（LLM 无候选可选/不敢转场）。
> 定稿路线：**存储走现行自动扫描（扩展最优）, 键表 = 活跃语义视图, 日夜 = LLM
> 可选字段**——不是新存储, 是"存储上的语义层 + 契约字段"。

## 1. 三层框架

```
① 资产层（存储——现行不变）
   assets/background/{BG_*}/BG_{Scene}_{Variant}.jpg
   命名规范: camelCase scene + VARIANT_TOKENS 变体（night/sunset/...）;
   无变体后缀 = day（默认）
   自动扫描 → catalog（scene_id × variant, 加图自动可见——扩展零注册）
   整理时用不到的 → 移 _unused/（保留资产, 不进活跃键）

② 语义键层（活跃视图——整理产物, assets/_place_entities.json）
   每个键 = 一个可被剧情提到的地点（日夜无关）:
     scene_id: latin snake 锚（自动派生——与资产同源）
     name:     中文语义名（LLM 看到的就是它: "杂草屋""圣三一走廊"）
     region:   剧情地理（可选; region 子集注入用）
     group:    类型分组（可选: 学园/日常/商业…）
     active:   true（注入/可选）| false（保留资产不进键表）
     files:    {day: [...], night: [...]}（自动从 variant 归位——日夜不占键）
   数量目标: 活跃 ~150-250（资产 ÷2 的现实值）; 键量由"语义归并 + 剔除"决定

③ 契约/查询层
   story_scene payload 扩展:
     place:        语义名（候选注入 = 活跃集上下文子集 ≤100 或自由描述）
     time_of_day:  "day" | "night"（可选字段, 缺省 day——LLM 显式表达剧情氛围）
   程序解析链（core/rag, 语料 = 语义键表同源）:
     语义名/描述 → 精确（id/name/别名）→ embedding（跨语言中英日）→ 阈值宁缺勿错
     → scene_id × time_of_day variant → 资产 URL（无夜景 → 静默降级 day）
   切换保障: 候选含 60-100 语义名 + LLM 每场决策 → 剧情转场即换图（单调消除）
```

## 2. 日夜组织（独立字段, 不占键）

```
time_of_day: LLM 可选（"night" 或省略=day）——夜晚是剧情氛围决策, 表达权在 LLM
资产: scene × variant（_Night 文件已在位 337 张）
程序: night → 查 files.night → 缺 → 降级 day（宁缺勿错静默）
未来扩展: sunset/dawn 等 = 字段枚举 +2, 资产按 VARIANT_TOKENS 规范加图即可
```

## 3. 扩展性结论

| 动作 | 成本 |
|---|---|
| 加新地点图 | 资产落位 → 扫描自动可见 → 键表补 name 一次（工具辅助） |
| 加时刻变体 | 按命名规范加 _Night 文件 → files.night 自动归位 |
| 新区域/角色主场 | 键表 region 标注 → region 子集注入自动受益 |
| 玩家自由指定地点 | 自由描述 → 检索链（embedding 泛化）——CLAVIN 式后续 |
| 未来 embedding/记忆 RAG | 键表 = 语料/描述文档同源——一次构建双用 |

## 4. 整理操作规范（作者 tempo 工作流）

1. 目录结构保持官方 BG_*; 逐目录清理/补全
2. 命名规范不变: BG_{Scene}_{Variant}.jpg（Scene camelCase; Variant ∈ 白名单）
3. 同一地点的多镜头/版本图: 保留但语义键层自动同族（工具里可见/可调）
4. 确定用不到的（事件图/纯特效/重复）→ 移 `_unused/`
5. 产出物: 完整 assets/background + 工具审定的 _place_entities.json
   （工具: tools/place_studio.py——看图/命名/region/剔除/进度）

## 5. 契约接线（整理完成后实施）

- story_scene schema: place 语义名白名单（soft）+ time_of_day 枚举
- 注入: 活跃键表（region 子集 ≤100 中文名 + 分组标题 ~2k 字）
- bond_story_rules / 词表指引: "每个场景标 place; 夜晚剧情写 time_of_day=night"
- director: visual_for(place, time_of_day) → 变体选择
- core/rag place.py 语料升级 = 语义键表（别名同源）
