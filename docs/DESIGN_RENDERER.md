# 羁绊剧情渲染器（renderer/）—— 实时播放 + 回放 双用途设计

> 2026-08-27 定稿方向。渲染器是 **bond story 的显示层**——与引擎（BondStoryEngine）
> 解耦的纯消费方：输入场景数据（BondScene dict），输出渲染状态（背景/差分/特效/音频/文本）。
> 同一渲染管线服务两种用途：**实时播放**（引擎生成场景 → 渲染）与**回放**（事件流读场景 → 渲染）。

---

## 一、定位与职责边界

```
┌─────────────────────────────────────────────────────────────┐
│                      BondStoryEngine                        │
│              （剧情生成: send_vn_scene → BondScene）          │
└──────────────────────────┬──────────────────────────────────┘
                           │ scene dict（契约 JSON, 与事件流同构）
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     renderer/（本设计）                      │
│   场景解算: 背景/差分/特效/音频/文本 → RenderOutput           │
│   双用途:  实时（live）· 回放（replay）                       │
└──────────────────────────┬──────────────────────────────────┘
                           │ RenderOutput（平台无关状态）
                           ▼
                ┌──────────┴──────────┐
                ▼                      ▼
          CLI 输出（renderer/cli）   GUI 输出（view-vn, 未来）
```

**职责边界（关键）**：
- **输入**：`BondScene.to_dict()` 的 dict（实时）或事件流 bond 事件的 payload（回放）——**同构**，渲染器不区分来源
- **渲染器不 import 引擎**（core/bond_story）——只认 scene dict（防循环依赖 + 回放复用）
- **渲染器不做剧情决策**（生成/选择/收尾全在引擎）——只做"怎么显示"
- **平台无关**：核心解算（背景/差分/特效）是纯函数 → 输出平台指令；CLI/GUI 各自消费

**目录位置**：项目根 `renderer/`（与 tools/ 并列；依赖 core/ 的媒体查库，单向引用）。

---

## 二、核心概念

### 2.1 RenderScene（输入规范化）

实时与回放的 scene dict 字段完全一致（`BondScene.to_dict()` 契约）：

```python
@dataclass
class RenderScene:
    paragraphs: list[dict]    # [{text, emotion?}]（emotion 缺省 = 延续上一段）
    choices: list[str]        # 空 = 无选项（收尾/无选项场景）
    is_end: bool              # 剧情是否结束
    background: str | None    # 导演层背景 scene_id（None = 纯文本模式）
    audio: str | None         # 导演层音频占位（当前恒 None, 未来）
    place: str | None         # 场景级地点意图（导演已消费, 渲染器只读）
    input: str = ""           # 回放附加: 本场触发输入（实时可为空）
    picked: str | None = None # 回放附加: 玩家当时的选择
```

- `from_live(scene: BondScene)` / `from_event(payload: dict)` 两条构造路径——**一渲染器两用**
- 坏数据容错（宁缺勿错）：缺失字段 → 空/None，不 raise

### 2.2 RenderState（渲染状态机）

```
IDLE → SCENE_LOADING（背景/差分预解析）→ SCENE_PLAYING（段落逐条显示）
     → CHOICE（有选项: 等玩家）| NEXT（无选项: 自动下一场）| END（is_end）
回放模式: PLAYING 自动推进（定时器）; 实时模式: CHOICE 等玩家输入
```

状态字段：

```python
@dataclass
class RenderState:
    background: str | None        # 当前背景（scene_id）
    background_transition: float  # 切换过渡时长（秒, 0 = 立即）
    sprite: str | None            # 当前角色差分（emotion → 图 id）
    sprite_stack: list[str]       # 逐段差分序列（段落级表情变化）
    effects: list[list[str]]      # 逐段特效序列（每段落一个特效列表）
    paragraph_index: int          # 当前段落索引
    audio: AudioRequest | None    # 当前音频请求（未来）
    choices: list[str]            # 待选择项（CHOICE 态）
    is_end: bool
```

### 2.3 渲染管线（核心）

```
render(scene: RenderScene) -> RenderOutput
  ├─ ① 背景解算:   scene.background → MediaCatalog.background() → 图 + 过渡
  ├─ ② 差分解算:   每段 emotion（**标注层按记录写入**）→ catalog.sprite() → 图序列
  ├─ ③ 特效解算:   每段 emotion → 特效映射表（查表, 算法）→ 特效序列
  ├─ ④ 音频解算:   scene.audio / 未来 → AudioRequest（占位）
  └─ ⑤ 文本+选项:  paragraphs / choices 透传（平台渲染）
```

**确定性**：①②③ 全是纯查表/确定性算法——同输入必同输出（回放与实时一致）。

---

## 三、背景播放 / 切换

### 3.1 背景解析

```python
class BackgroundResolver:
    """背景解算: scene_id → 背景媒体 + 过渡（复用 core/media/catalog）。"""
    def resolve(self, scene_id: str | None) -> BackgroundResult:
        # MediaCatalog.background(scene_id) → BackgroundMedia{path, variant, ...}
        # 缺失 → 保持当前背景（不黑屏, 宁缺勿错）
```

- `scene.background` 来自导演层（Director.visual_for 的 place → scene_id 查表）——渲染器只消费
- 无 background 字段（纯文本模式）→ 保持当前背景或默认背景

### 3.2 切换策略

| 场景 | 行为 |
|---|---|
| 背景变化（新 scene_id ≠ 当前） | 过渡切换（GUI: 淡入淡出 0.4~0.8s; CLI: 打印 `[背景 xxx]` 标签） |
| 背景相同 | 不切换（无闪烁） |
| 背景缺失 | 保持当前（宁缺勿错） |

```python
@dataclass
class BackgroundResult:
    scene_id: str | None
    media_path: str | None     # 绝对路径（GUI 用）或 None
    transition: float          # 过渡秒数（0 = 无变化）
    changed: bool              # 是否发生了切换（平台据此做动画/标签）
```

### 3.3 未来扩展（预留接口）

- 动态背景（视频/粒子/视差）：`BackgroundResult.media_path` 未来可指向视频/序列帧——接口不变
- 背景叠加层（雨天/夜景滤镜）：`background_overlay` 字段预留

---

## 四、角色差分调用（独立模块, 两种 API）

### 4.1 职责划分（renderer 只出意图, 播放外包）

```
renderer/SpriteResolver（意图层）: 段落 emotion → emotion 序列（确定性延续）
      │ emotion 序列
      ▼
core/media/sprite_player.py（播放层, 独立于 renderer）:
      ├─ API 1: play_diff(char_id, emotion)   → diff/ 静态差分图（emotions.yml 查）
      └─ API 2: play_spine(char_id, emotion)  → spine/ 骨骼动画包（未来, spine 目录查）
```

- **renderer 不查图**——只输出"该显示什么表情"（emotion 序列）
- **播放实现外包**（core/media/sprite_player.py）——diff（静态图）与 spine（动画）两个独立 API
- 平台/调用方决定用哪个 API（GUI 有 spine 资产用 spine, 没有用 diff）

### 4.2 意图解算（renderer 内, 保留确定性延续）

```python
class SpriteResolver:
    """意图层: 段落 emotion → emotion 序列（不查图——播放由 sprite_player 负责）。"""
    def resolve(self, paragraphs: list[dict]) -> list[str]:
        # 每段 emotion 由标注层给（core/bond/emo_text.py）; 缺省延续在前端做
        # （⚠️ 2026-09-21: 原 Python 侧 `BondScene.para_emotions()` 已删——零消费者）
        # 词表外 → 保持上一段（静默降级）
        # 返回 emotion 序列（如 ["nomal", "smile", "smile", "embarrass"]）
```

### 4.3 播放 API（core/media/sprite_player.py, 独立模块）

```python
# API 1: diff 静态差分播放（直接播放 diff/ 图）
def play_diff(char_id: str, emotion: str) -> SpriteMedia | None:
    """emotions.yml 查 emotion → diff/{emotion}.png（缺失 → None, 调用方保持上一张）。"""

# API 2: spine 骨骼动画播放（未来——spine/ 目录资产）
def play_spine(char_id: str, emotion: str) -> SpinePack | None:
    """查 assets/illustration/{char_id}/spine/ 的骨骼动画包（呼吸/眨眼参数）。"""
```

- 复用现有资产结构：`assets/illustration/{char_id}/diff/`（静态差分）+ `spine/`（骨骼动画, 已扫描: core/media/sprites.py 的 SpinePack/find_spine_packs）
- 未来可扩展 `play_l2d()`（L2D 模型）——API 形态一致（char_id, emotion → 媒体/None）
- 测试：两个 API 独立单测（diff 查表 / spine 目录扫描）

### 4.4 切换策略（播放层职责）

| 段落 | 行为 |
|---|---|
| emotion 变化 | 换图/换动画（GUI: 立绘切换动画; CLI: `[表情 xxx]` 标注） |
| emotion 延续 | 保持当前（不闪烁） |
| API 返回 None | 保持上一张（静默降级） |

---

## 五、特效算法（表情 → 特效）

### 5.1 设计原则

- **纯查表算法**（非 LLM）：emotion（封闭词表）→ 特效类型——确定性、可测试
- 特效是**情绪的外化**——与差分同源（emotion），但独立输出（差分是"图"，特效是"动效"）
- **分层配置**: 多数角色用全局表; 个别角色可自定义覆盖（per 角色表优先, 全局兜底）

### 5.2 映射表（分层: 角色表 → 全局表 → 空）

```yaml
# 全局默认（config/settings/effects.toml 或代码内置）——大多数角色
global:
  smile: [sparkle]            # 微笑冒星星（用户举例）
  happy: [sparkle]
  joy:   [sparkle]
  embarrass: [blush, notes]    # 害羞: 脸红 + 音符
  shy:   [blush, notes]
  angry: [anger]               # 怒气符号
  rage:  [anger]
  sad:   [raindrop]            # 雨点/泪滴
  cry:   [raindrop]
  surprise: [bang]             # 惊叹号
  shock: [bang]
  love:  [heart]               # 爱心飘浮
  serious: []                  # 平静无特效
  nomal: []                    # 默认无特效

# per 角色覆盖（assets/illustration/{char_id}/effects.yml, 可选）——
# 个别角色自定义: 天然呆角色星星多、严肃角色少; 未写条目回落到全局表
# 例: 遥香的 effects.yml:
#   shy: [blush, notes, petal]   # 覆盖全局: 害羞多一个花瓣
```

```python
class EffectResolver:
    """特效解算: 分层查表（角色表 → 全局表 → 空）——确定性。"""
    def __init__(self, char_id: str, assets_root: Path):
        self._table = load_effects(char_id, assets_root)  # 合并: 角色覆盖 + 全局兜底

    def resolve(self, emotions: list[str]) -> list[list[str]]:
        return [self._table.get(e, []) for e in emotions]
```

### 5.3 触发时机与叠加

- 特效随**段落**出现（段落显示时特效同步播放）
- 多特效可叠加（如 `blush` + `notes`）
- 特效持续时间 = 段落显示时长（平台控制）
- CLI 降级：`[✨]` 符号标注（文本流不破坏）

---

## 六、音频接口（未来占位）

### 6.1 AudioRequest（渲染器输出音频指令）

```python
@dataclass
class AudioRequest:
    kind: str            # "bgm" | "sfx" | "voice" | "stop"
    asset: str           # 音频资源 id/路径（catalog 查）
    volume: float = 1.0
    fade_in: float = 0.0   # 淡入秒
    fade_out: float = 0.0  # 淡出秒
    loop: bool = False
```

- 渲染器**只输出指令**（不实现播放）——播放器（GUI WebAudio / CLI 无）未来接入
- 来源：`scene.audio`（导演层占位，当前恒 None）→ 未来导演填 bgm/sfx id
- 特效音（星星音效）：`EffectResolver` 可附带 `effect_audio`（未来）

### 6.2 状态

- `RenderState.audio`：当前播放请求（切背景/切差分时可联动切换 BGM）
- 平台消费：GUI 播放 / CLI 忽略（无音频输出）

---

## 七、实时 vs 回放（双用途）

### 7.1 实时（live）

```
BondStoryEngine.send_vn_scene(user_input)
  → BondScene → RenderScene.from_live(scene) → Renderer.render(scene) → 平台渲染
  → 玩家选择（CHOICE 态）→ choice 喂回引擎 → 下一场
```

- 引擎驱动：渲染器被动接收场景
- 交互：选项 → 引擎；自由输入 → 引擎

### 7.2 回放（replay）

```
events.jsonl → filter_bond（type=bond 事件）→ payload → RenderScene.from_event(payload)
  → Renderer.render(scene) → 自动推进（PLAYING 定时器）
```

- 事件流驱动：只读渲染
- **选项展示但锁定**: 有选项的场景显示选项列表, 但只有 `picked`（玩家当时的选择）
  高亮/标记——不可重新选择（分支回放不做, 纯展示"当时怎么选的"）
  ```js
  // GUI 回放: choices 全部渲染（disabled）; picked 高亮 + "（当时的选择）"标签
  choiceBtn.disabled = true;
  if (choice === scene.picked) choiceBtn.classList.add("picked");
  ```
- 控制：播放/暂停/跳过/倍速（回放 UI）

### 7.3 回放源（回溯场景, 2026-08-27 补充）

```
回溯（世界/角色回退, 见 docs/archive/world_model_evolution.md（已归档） 阶段 11）后:
  ├─ 当前线: 事件流被回档到存档点——之后的事件（含 bond 剧情）从当前线消失
  │          （语义: "没发生"——当前线角色也不记得）
  └─ 原线:  快照完整保留（snapshots/s_xxx/characters/{char}/events.jsonl）
             ——原线剧情永远可回放（平行时空分叉）

回放源设计（M3 回放入口）:
  source: "current"                     → 当前线 events.jsonl
        | "snapshot: s_xxx"             → 快照/原线 events.jsonl（回溯场景的原线回放）

渲染器零改动——RenderScene.from_event 输入同构（当前线/快照的 bond 事件 payload
一致）; 未来世界树 UI 提供"回放原线"入口（选择快照 → 该快照的完整剧情回放）。
```

### 7.3 一致性保证

- 输入同构（RenderScene）→ 渲染管线同一套 → **实时看到的 = 回放看到的**（除交互差异）
- 测试：同一场景 dict 实时/回放渲染输出一致

---

## 八、目录结构

```
renderer/
├── __init__.py           # 公开 API: Renderer, RenderOutput, RenderState
├── scene.py              # RenderScene（from_live / from_event 两用规范化）
├── state.py              # RenderState（渲染状态机: IDLE→PLAYING→CHOICE/END）
├── background.py         # BackgroundResolver（背景解算: catalog 查库 + 切换/过渡）
├── sprite.py             # SpriteResolver（意图层: 段落 emotion → emotion 序列——不查图）
├── effects.py            # EffectResolver（特效查表: 角色表 → 全局表 → 空, 确定性）
├── audio.py              # AudioRequest + 音频状态（未来占位接口）
├── core.py               # Renderer（渲染管线: scene → RenderOutput; 双用途入口）
├── cli.py                # CLI 输出（迁移 core/ui/vn_cli.py 的渲染部分: 打字/标签/选项）
└── tests/                # 单测（纯函数友好: scene dict → output 断言）

core/media/
└── sprite_player.py      # 【新增, 独立于 renderer】差分播放层:
                          #   play_diff(char_id, emotion)  → diff/ 静态差分图（API 1）
                          #   play_spine(char_id, emotion) → spine/ 骨骼动画包（API 2, 未来）
```

**与现有组件关系**：
- 复用：`core/media/catalog.py`（MediaCatalog: 背景查库）、`core/media/background.py`（derive_background）、`core/media/sprites.py`（SpinePack/find_spine_packs——spine API 的资产扫描基础）、`core/ui/display.py` 的 BondStoryOutput（文本缓冲）
- 新增：`core/media/sprite_player.py`（差分播放——diff/spine 双 API, 供 renderer 外任何调用方使用）
- 迁移：`core/ui/vn_cli.py` 的 `simulate_vn_scene`/`_print_visual`/`_type_paragraph` → `renderer/cli.py`（CLI 输出统一收编）
- 引擎不动：BondStoryEngine 继续输出 BondScene——渲染器在引擎之外新增

---

## 九、核心 API（草案）

```python
# renderer/__init__.py
class Renderer:
    """羁绊剧情渲染器——实时 + 回放双用途。"""

    def __init__(self, char_id: str, assets_root: Path, mode: str = "live"):
        # mode: "live"（等玩家交互）| "replay"（自动推进）
        self.background = BackgroundResolver(MediaCatalog(assets_root))
        self.sprite = SpriteResolver(char_id, MediaCatalog(assets_root))
        self.effects = EffectResolver()

    def render(self, scene: RenderScene) -> RenderOutput:
        """场景 → 渲染输出（背景/差分/特效/音频/文本/选项——平台无关）。"""
        bg = self.background.resolve(scene.background)
        sprites = self.sprite.resolve(scene.paragraphs)
        emotions = self.sprite.emotions          # 确定性延续结果
        fx = self.effects.resolve(emotions)
        audio = self.audio_for(scene)            # 未来
        return RenderOutput(
            background=bg, sprites=sprites, effects=fx,
            paragraphs=scene.paragraphs, choices=scene.choices,
            audio=audio, is_end=scene.is_end,
        )

    def on_choice(self, choice: str) -> None: ...   # live: 玩家选择
    def advance(self) -> None: ...                  # replay: 自动推进下一段/场


@dataclass
class RenderOutput:
    background: BackgroundResult
    sprites: list[str]            # 每段差分（图 id/路径）
    effects: list[list[str]]      # 每段特效
    paragraphs: list[dict]        # 原文透传
    choices: list[str]
    audio: AudioRequest | None
    is_end: bool
```

**平台消费**（GUI 未来 view-vn）：
```js
// 伪代码——GUI 渲染循环
const out = await api.renderScene(scene);     // 后端 Renderer.render
out.background.media_path → <img class="bg" style="transition: opacity">
out.sprites[i] → <img class="sprite" src=...>
out.effects[i] → 粒子/动画（sparkle → 星星粒子）
out.paragraphs[i].text → 打字机
out.choices → 按钮（live）
```

---

## 十、状态机细节

```
                    ┌────────────┐
                    │   IDLE     │
                    └─────┬──────┘
                          │ render(scene)
                          ▼
                 ┌────────────────┐
                 │ SCENE_LOADING  │  背景/差分/特效预解析（纯函数, 无副作用）
                 └───────┬────────┘
                         ▼
                 ┌────────────────┐
            ┌───▶│ SCENE_PLAYING  │  段落逐条显示（打字机; 特效随段落）
            │    └───────┬────────┘
            │            │ 段落显示完
            │            ▼
            │   ┌────────────────┐
            │   │  is_end? ──yes──▶ END（剧情结束）
            │   │  no              
            │   ▼                  
            │  choices 非空? ──yes──▶ CHOICE（live: 等玩家; replay: 自动取 picked）
            │   │ no                 
            │   ▼                  
            │  NEXT（live: 引擎下一场; replay: 自动下一事件）
            └───┘
```

---

## 十一、测试策略

| 测试 | 内容 |
|---|---|
| 背景解算 | scene_id → 图/过渡; 缺失 → 保持; 相同 → 不切换（纯函数断言） |
| 差分解算 | 每段 emotion 由标注层给（缺省继承在前端）; 词表外 → 保持（确定性） |
| 特效映射 | 每 emotion → 期望特效（查表断言）; 缺省 → 无 |
| 同构验证 | 同一场景 dict 走 from_live 与 from_event → RenderOutput 一致（回放=实时） |
| CLI 输出 | 打字/标签/选项渲染（迁移 vn_cli 后现有测试改指向 renderer/cli） |

---

## 十二、里程碑

| 阶段 | 内容 | 交付 |
|---|---|---|
| **M1** | renderer/ 骨架 + 三个 Resolver（背景/差分/特效）+ 渲染管线 + CLI 输出（迁移 vn_cli 渲染） | CLI 可跑（现有 vn_cli 行为不回归） |
| **M2** | GUI view-vn 消费 RenderOutput（背景图/差分图/打字/选项）——live 播放器 | GUI 可玩 bond story |
| **M3** | 回放模式（事件流 → 自动播放）+ 控制（暂停/跳过/倍速） | 回放可用 |
| **M4** | 特效落地（粒子/动画）+ 音频接口接入 | 完整渲染 |

---

## 十三、开放问题

1. ~~特效表配置位置~~ → **已定**: per 角色 `assets/illustration/{char}/effects.yml`（可选覆盖）+ 全局默认（config 或内置）——角色表优先, 全局兜底
2. ~~回放交互~~ → **已定**: 展示选项但锁定 picked（不可重新选择, 纯展示）
3. ~~差分调用位置~~ → **已定**: 独立 `core/media/sprite_player.py`——play_diff（API 1）+ play_spine（API 2）两接口, renderer 只出意图
4. 背景过渡时长可配置？（慢速淡入适合浪漫场景——导演可否输出 transition 意图？）
5. L2D 差分（spine）接入时 SpriteMedia 的扩展字段（呼吸/眨眼参数）——M4 前定
6. 特效表全局默认的存放: 代码内置（快速）vs config/settings/effects.toml（作者可改）——M1 前定

---

## 十四、VN 交互规格（2026-08-29 定稿, webgui/bond.js 已实现）

### 14.1 快速跳出（跳过逐字）
- **触发**: 空格 / Enter / 鼠标点击空白处（非交互元素）→ 整段文字立即显示, 不逐字渲染
- **排除**: 选项按钮 / 自由输入框 / 右上按钮 / 继续三角 / 标题面板——点击这些不触发跳过（不冲突）
- is_end 场景: 空格 / Enter / 点击空白 = 直接收尾 finish
- 自由输入框聚焦时: 空格 = 输入字符, Enter = 发送（不跳过）

### 14.2 自动模式（右上"自动"按钮）
- 点击 → 按钮变**黄色**（.active）; 再点 → 关闭
- 开启后: 一段对话**打字完成后 3s** 自动推进——
  - 有选项 → 3s 内自动选**第一个选项**
  - is_end → 走原自动兜底（END_HOLD 后 finish）
  - 自由输入 → **不自动**（不伪造玩家输入, 宁缺勿错）
- 开启瞬间若当前选项已显示 → 立即进入 3s 倒计时

### 14.3 自动 × 手动 × 快速跳出 不冲突
- **玩家手动介入优先**: 自动倒计时内点了选项 → 取消倒计时（clearAutoTimer）+ 用玩家选的; 自动模式**保持开启**（后续场景继续自动）
- 空格/Enter 跳过打字不影响自动倒计时（跳过 → 交互出现 → 倒计时开始）
- 场景切换 / 提交推进时自动倒计时一律作废（防双提交）
