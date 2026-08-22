# Live2Be 视觉层设计 — 导演架构（差分/背景播放）

> 状态：**设计定稿**（2026-08-22）。实现走分支 `visual-director`。
> 范围：① core/media 查库 → ② 导演组件 → ③ web 渲染面（未来）→ ④ 转场/媒体（未来）。
> 失败回退：小模型表现不良 → 回到主分支（冻结/删除 visual-director），VN 仍可纯文本跑。

## 1. 背景与目标

Bond Story VN 目前是纯文本（段落 + 选项）。视觉层 = 让每个场景有**差分（表情）和背景**。
核心问题 = 差分/背景的**播放**——渲染面 + 播放协议两层，分开设计才不会觉得遥不可及。

拍板决策（2026-08-22）：
- **播放表面 = Web 渲染面**（`channel=roleplay` + 游戏页，复用 web/ 的 EventHub+SSE+worker 模式）。
- **CLI 终端播不了 PNG → 降为调试/测试面**：BondScene 携带视觉字段，`simulate_vn_scene` 直接 print。
- **spine 已验证可行，但契约层不绑**——渲染器自由：v1 CSS fade 换静态差分，v2 接 spine（emotion → spine 区/动画）。

## 2. 核心架构决策：导演拆分

**主 LLM 专注文本，导演 LLM 管视觉**（用户设计，优于"主 LLM 顺带输出视觉字段"）。

```
主LLM(叙事) ──story_scene{paragraphs, choices} 纯文本──▶
                                              │
导演LLM(本地,纯文本) ◀─ 每场段落 + 当前视觉状态 VIS
        │  输出 {sprite, background} 小 JSON（封闭词表）
        ▼
引擎: ① catalog 白名单校验 → 状态保持 → 正则兜底 → 默认
```

收益：
- 主 LLM 契约**零改动**（story_scene/story_end 保持原样），不背视觉 schema/状态/rules → **token 喂量降低，专注写文**。
- 导演 = 封闭词表**分类式输出**（6 情绪 + 背景 id 或省略），小模型能胜任；输入仅数百 token，**重试便宜**。
- 导演**可注入**：本地模型在 → LLM 主驱动；缺失/挂了 → 降级纯正则+保持+默认，VN 照跑（宁缺勿错）。
- 视觉记忆 = `VisualState{sprite, background}`，engine 持有、每场喂回导演 context，导演决定何时/如何演进。

## 3. 决策链与优先级

### 表情
```
导演 sprite(合法)  >  状态保持(上一场)  >  正则推断(段落)  >  默认 nomal
```
- **算法辅助（nudge）**：同一表情保持 ≥3 场 → 系统注记「表情已保持 N 场，剧情有起伏的话请在下一场换 sprite」——**发给导演**，只进导演 context 不入历史（镜像 remind_rounds 模式）。
- **收尾放开**：不强制 nomal（微笑收尾很常见）。收尾表情走正常链；end 提示语给导演「收尾表情由你自然选择」。

### 背景
```
导演 background(合法)  >  状态保持(上一场)  >  默认(触发 reason 推导 / neutral)
```
- **无正则**（文本→地点太模糊，~200 场景靠关键词必翻车）。
- **不参与 nudge**（教室戏待在教室是对的，"不变"不是 bug）。
- 背景切换 = ④ 转场动画（CSS fade / spine），本层只出字段。

## 4. 校验与降级（宁缺勿错）

- 导演输出必须命中 ① catalog 白名单（`sprite_emotions()` / `background_scenes()`）。
- 校验失败 → **静默降级**（保持/正则/默认），**不进主 LLM retry 循环**——sprite/background 是低风险建议性字段，回灌烧 token 且打断 VN 节奏。
- 与 paragraphs 区分：paragraphs 是高风险（必回灌，进 SceneLoopError 重试），两套处理分开。

## 5. 分层实现

### ① core/media/ — 查库（纯数据，背景全量 + 差分按角色懒加载）
- `background.py`：命名派生（`BG_` 前缀 + 变体白名单 + camel→snake），零 manifest。已核实 1089 张 jpg 全带 `BG_` 前缀。
- `sprites.py`：diff/spine 登记（atlas 区名解析、SpinePack 三件套识别）。
- `manifest.py`：`assets/illustration/{char}/emotions.yml`——情绪→png 映射，**情绪白名单真源**（2026-08 由 `_media.yml` 改名；键=情绪名 id、值=diff/ 路径、注释=示范，见 DESIGN_VISUAL_PROTOCOL.md §4/§8）；缺失/损坏降级 `{}`。**catalog 已接 emotions.yml**（2026-08-23 重构）。
- `catalog.py`：`MediaCatalog`，`sprite()/background()/sprite_emotions()/background_scenes()`；构造时 assets 根缺失才抛错，查询永不抛。**加载策略**：背景构造时全量（数据驱动必须扫、便宜，且导演需完整场景白名单）；差分首次 query 该角色才扫并缓存（VN 单角色，且某个角色素材损坏只影响它自己，宁缺勿错）。
- 现成资产：背景 1089 jpg（可派生）；差分 `haruka_spr_01~06`（人工确认 01→nomal…06→shout）；spine 导出 4 包（haruka_spr/_HD/_Steam、Haruka_home）。

### ② 导演组件（core/director/，已实现）
- `VisualState{sprite, background}`（视觉记忆，engine 持有；冷启动 nomal/neutral）。
- `Director.visual_for(text, is_end)`——复合决策链 + 背景目录分层**两段流**。
- **背景分层**（用户拍板 2026-08-22）：第一层给「常用集合」`assets/_director_whitelist.json`
  （`common_scenes` 快速路径直给 + `common_dirs` 目录粗选）→ 导演输出 scene_id（直用）/
  目录名（第二层给该目录内场景清单拍板）/ keep·null（保持）。目录数据源 `background_dirs()` /
  `background_scenes_in_dir()`（懒扫单目录）。
- **人设注入**：persona = `char.build_prompt("trigger")`（profile + brief_traits 极简）——
  缓解「7B 把握不好人设 → sprite 质量低」。导演 rules 里明确「同一情绪不同性格表现不同」。
- **决策链**（宁缺勿错，失败**不进主 LLM retry**）：
  - 表情：导演(合法) > 正则（导演不可用当驱动器逐场 / 可用仅冷启动防抖动）> 保持 > 默认 nomal
  - 背景：导演 scene_id(合法) > 目录分层拍板 > 保持 > 默认 neutral；背景**无正则**、**不参与 nudge**
- **nudge**：同一表情保持 ≥3 场 → 导演 system 注记「已连续保持 N 场，有起伏请在接下来的场景换」。
- **收尾**：不强制 nomal（微笑收尾常见），只提示「收尾表情由你自然选择」。
- **LLM 降级**：连续 2 次 `DirectorLLMError` → 本轮禁用导演 LLM，降级正则+默认，VN 照跑。
- **导演 LLM**：`core/director/llm.py` 薄封装（Qwen2.5-7B，LM Studio localhost:1234/v1，
  json_object，temperature 0.3 → 分类式稳定；失败抛 DirectorLLMError 由上层降级）。
- 引擎集成：`send_vn_scene` 每场后 `director.visual_for(段落拼接, is_end)` → 白名单校验 →
  合并进 BondScene（新增 `sprite`/`background` 字段；主 LLM 契约与历史**零改动**）。
- CLI：`simulate_vn_scene` / 回放 print `[表情 smile] [背景 class_room]`；存档落 sprite/background
  （纯文本模式省略，旧档兼容）。

### ③ web 渲染面（未来）
- `channel=roleplay` 新频道，worker 跑 BondStoryEngine → SSE scene 事件（含 sprite/background）→ 前端渲染。
- v1 CSS fade 换图；spine v2（emotion → spine 区/动画）。web/ 现有 IDE GUI 不动。

### ④ 转场/媒体（未来）
- 背景切换过渡动画；`mmt_send_media` 查库落地。

## 6. 文件清单
- `core/media/{__init__,catalog,background,sprites,manifest}.py`
- `tests/core/test_media.py`
- `assets/illustration/igusa_haruka/emotions.yml`（情绪词表；作者 2026-08 由 `_media.yml` 改名，键=情绪 id + 示范注释）
- ②：`core/director/{__init__,state,fallback,prompt,llm,director}.py` + `tests/core/test_director.py`
- `llm/prompts/director_rules.md`（导演角色/输出格式/少样本）
- `assets/_director_whitelist.json`（导演背景常用集合，可编辑）
- `experiments/engine_smoke.py` 导演用例
- 本文档即设计依据（① 不再单开 DESIGN_MEDIA.md）

## 7. 验证
1. `python -m pytest -q -p no:cacheprovider` 全绿（含 media/director 测试）。
2. `python experiments/engine_smoke.py`：导演组件用例（BondScene 视觉字段 + 历史不含）。
3. 实机（风险点）：本地 Qwen2.5-7B 当导演，观察（a）输出 JSON 可靠率（b）背景分层命中率
   （常用集合/目录名是否选得对）（c）**sprite 是否贴合人设**（人设注入缓解）。不良 → 回主分支。
