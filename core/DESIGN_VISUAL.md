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

### ① core/media/ — 查库（纯数据，一次扫描建索引）
- `background.py`：命名派生（`BG_` 前缀 + 变体白名单 + camel→snake），零 manifest。已核实 1089 张 jpg 全带 `BG_` 前缀。
- `sprites.py`：diff/spine 登记（atlas 区名解析、SpinePack 三件套识别）。
- `manifest.py`：`assets/illustration/{char}/_media.yml`——情绪→png 映射，**情绪白名单真源**；缺失/损坏降级 `{}`。
- `catalog.py`：`MediaCatalog`，`sprite()/background()/sprite_emotions()/background_scenes()`；构造时 assets 根缺失才抛错，查询永不抛。
- 现成资产：背景 1089 jpg（可派生）；差分 `haruka_spr_01~06`（人工确认 01→nomal…06→shout）；spine 导出 4 包（haruka_spr/_HD/_Steam、Haruka_home）。

### ② 导演组件（实现时定 core/director/ 或 core/visual.py）
- `VisualState{sprite, background}`（视觉记忆，engine 持有）。
- Director 接口：`visual_for(text, state) -> {sprite?, background?}`——LLM 实现 + 保持/正则/默认 fallback 链。
- 引擎集成：`send_vn_scene` 每场后调导演 → 白名单校验 → 合并进 BondScene（新增 `sprite`/`background` 字段）。
- CLI：`simulate_vn_scene` print `[表情 smile] [背景 class_room]`；回放同理。
- 测试：假导演 stub + 正则 fallback + 白名单校验 + nudge（≥3 场）+ 收尾提示 + 宁缺勿错路径。
- 导演 prompt：`llm/prompts/director_rules.md`（封闭词表白名单 + 少样本 + 视觉状态输入格式）。

### ③ web 渲染面（未来）
- `channel=roleplay` 新频道，worker 跑 BondStoryEngine → SSE scene 事件（含 sprite/background）→ 前端渲染。
- v1 CSS fade 换图；spine v2（emotion → spine 区/动画）。web/ 现有 IDE GUI 不动。

### ④ 转场/媒体（未来）
- 背景切换过渡动画；`mmt_send_media` 查库落地。

## 6. 文件清单
- `core/media/{__init__,catalog,background,sprites,manifest}.py`
- `tests/core/test_media.py`
- `assets/illustration/igusa_haruka/_media.yml`（种子 manifest）
- ②：导演组件 + `llm/prompts/director_rules.md` + BondScene 加字段 + vn_cli print
- 本文档即设计依据（① 不再单开 DESIGN_MEDIA.md）

## 7. 验证
1. `python -m pytest -q -p no:cacheprovider` 全绿（含新增 media/director 测试）。
2. 引擎冒烟：假导演 + 正则 fallback 跑 VN，BondScene 带 sprite/background，CLI 打印。
3. 实机（风险点）：本地小模型当导演，观察其输出 JSON 可靠率；不良 → 回主分支。
