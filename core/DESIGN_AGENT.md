# Agent 層 — 結構化輸出與情感驅動視覺切換

> 狀態：設計階段，待實現。
> 目標：LLM 輸出純文本對白 → 算法層分析情感 → 程序查映射表切換立繪/背景。

> **與 MMT 契约动作化的关系**：本文的「LLM 輸出純文本對白」前提在 MMT 全 JSON
> 动作化後會調整——LLM 每輪輸出單個**動作 JSON**（chat），對白承載在 `AgentAction.reply`
> 字段。情感/立繪層（本文 EmotionClassifier / SpriteMapper / ExpressionController）
> 仍保持「算法做導演」：對 `reply` 文本做分類 → 查映射表切換，**不新增 emotion/sprite
> 動作**（v1 動作集 = chat / inspect_character / send_media / trigger_bond_story，
> 见 [../contract/DESIGN.md](../contract/DESIGN.md) §8）。本文的 Phase D 改為消費
> `action.reply` 而非 `send_message()` 的返回。

---

## 一、設計原則

### 核心決策：LLM 寫劇本，算法做導演

```
LLM（語言區）:
  輸入: System Prompt + 角色人設 + 記憶上下文 + 玩家輸入
  輸出: 純文本對白（str）—— 不標 emotion，不標 sprite

→ LLM 不需要知道 spritesheet 的存在
→ LLM 的 token 全部用於對白質量
→ 對白本身攜帶足夠的情感訊號
```

### 情感分析層（導演區）:

```
LLM 輸出純文本
      │
      ▼
┌─────────────────────────┐
│ EmotionClassifier       │  ← 本地 1-3B / 規則混合
│ .classify(text, char_id)│     每輪調用，延遲 < 50ms
└───────────┬─────────────┘
            │ emotion_label
            ▼
┌─────────────────────────┐
│ SpriteMapper            │  ← 查 emotion_map.yml
│ .resolve(char, emotion) │     + 角色覆蓋
└───────────┬─────────────┘
            │ sprite_diff_id
            ▼
        前端渲染
```

### LLM 可選介入

LLM 如果在對白中**明確標記情感關鍵轉折**（例如 `{emotion: crying}`），則算法層直接採信，跳過分類。但這是例外路徑，不是默認路徑。

---

## 二、YAML 層設計

### 2.1 全局情感分類表（`config/settings/emotion_map.yml`）

```yaml
# 全局定義 — 所有角色共享的情感標籤體系
# 算法層輸出 emotion_label，程序查此表獲取 sprite_id

emotions:
  neutral:    { sprite: "regular",      priority: 0 }
  happy:      { sprite: "smile",        priority: 2 }
  sad:        { sprite: "frown",        priority: 2 }
  surprised:  { sprite: "surprise",     priority: 3 }
  angry:      { sprite: "angry",        priority: 3 }
  nervous:    { sprite: "anxious",      priority: 2 }
  shy:        { sprite: "blush",        priority: 1 }
  determined: { sprite: "serious",      priority: 1 }
  pained:     { sprite: "pain",         priority: 3 }
  gentle:     { sprite: "soft_smile",   priority: 1 }
  confused:   { sprite: "tilt_head",    priority: 1 }
  thinking:   { sprite: "look_away",    priority: 1 }
  relieved:   { sprite: "relief",       priority: 2 }

# priority 說明:
#   0 = 基準狀態，任何變化都可覆蓋
#   1 = 輕微情緒，需累積 2 次才切換（防抖）
#   2 = 明顯情緒，直接切換
#   3 = 強烈情緒，直接切換且忽略防抖
```

### 2.2 角色級別覆蓋（`profile.yml` 內）

```yaml
# 每個角色可覆蓋特定 emotion 對應的 sprite
# 角色擁有的 sprite 列表定義在 resources/ 中（此處僅做映射）
SIG~expression_overrides:
  happy: "haruka_smile_02"
  nervous: "haruka_anxious_03"
  shy: "haruka_blush_01"

# 角色專屬情感觸發詞（輔助規則引擎）
SIG~emotion_keywords:
  nervous: ["对不起", "我这种人", "怎么配", "不配", "打扰"]
  happy: ["sensei！", "太好了", "真的吗", "好开心"]
  determined: ["我会努力", "交给我", "保护", "请放心"]
  angry: ["请你去死", "不可原谅", "妨碍", "消灭"]
  sad: ["对不起…", "都是我不好", "我配不上"]
  shy: ["那个…", "谢谢你…", "好害羞"]
```

---

## 三、情感分類器（EmotionClassifier）

### 3.1 混合策略

| 方法 | 適用場景 | 延遲 |
|------|---------|------|
| **角色關鍵詞匹配** | 高置信度關鍵詞命中（"请你去死"→angry） | < 1ms |
| **本地小模型** | 一般情感分類（1B-3B，4-bit 量化） | < 50ms |
| **LLM 顯式標記** | 對白中的 `{emotion: xxx}` 標記 | 0ms（在對白中） |

**優先級：LLM 標記 > 關鍵詞匹配 > 本地模型**

關鍵詞命中後可跳過本地模型，節省 GPU/內存。但關鍵詞的 `precision` 優先於 `recall`——寧可不觸發，不要誤觸發。

### 3.2 面向微妙情感的角色

你的關鍵洞察：遙香情感明顯，但其他角色可能更內斂。

這對分類器的影響：

```
明顯角色（遙香）:
  文本: "请你去死！请你去死！！" → 關鍵詞直接命中 angry
  本地模型不需要跑

內斂角色（如佳代子）:
  文本: "……这样啊。" → 關鍵詞無法命中
  本地模型判斷: p(neutral)=0.6, p(thinking)=0.3, p(sad)=0.1
  → 輸出 thinking，優先級 low → 防抖累積
```

**關鍵詞表應該按角色配置**（在 `SIG~emotion_keywords` 中），而非全局。佳代子的"……"可能代表思考，遙香的"……"可能代表緊張——同一個省略號，不同角色完全不同。

---

## 四、切換頻率控制

### 防抖機制

```python
class ExpressionController:
    def __init__(self):
        self._current: str = "neutral"
        self._pending: str | None = None
        self._pending_count: int = 0

    def update(self, emotion: str, priority: int) -> str | None:
        """返回應切換到的 sprite_id，或 None（不切）。"""
        if emotion == self._current:
            self._pending = None
            self._pending_count = 0
            return None

        if priority >= 2:
            # 明顯/強烈情緒 → 立即切換
            self._current = emotion
            self._pending = None
            self._pending_count = 0
            return emotion

        # 輕微情緒 → 累積防抖
        if emotion == self._pending:
            self._pending_count += 1
            if self._pending_count >= 2:
                self._current = emotion
                self._pending = None
                self._pending_count = 0
                return emotion
        else:
            self._pending = emotion
            self._pending_count = 1

        return None  # 不切
```

### 效果

```
對白流（3 句）:
  "啊…sensei…"           → nervous, priority 1 → 累積 1, 不切
  "您、您怎么来了…"        → nervous, priority 1 → 累積 2, 切換到 anxious
  "我、我很高兴！"          → happy, priority 2   → 立即切換到 smile
```

---

## 五、對現有代碼的影響

### 新增文件

```yaml
config/settings/emotion_map.yml    # 全局 emotion → sprite 映射
core/emotion_classifier.py         # EmotionClassifier 類
```

### 修改文件

```yaml
core/momotalk.py:
  send_message() 返回值: str → AgentResponse  (namedtuple)
    AgentResponse:
      text: str              # 格式化後的對白文本 (含 [角色名: ] 前綴)
      bubbles: list[str]     # 氣泡列表
      emotion: str           # 當前情感標籤
      sprite_id: str         # 對應的立繪差分 ID
      should_switch: bool    # 是否觸發視覺切換

  _process_reply() 之後新增:
    _classify_emotion(text) → emotion_label

main.py:
  不需修改（CLI 只顯示 text）
```

### 不需要修改

- `llm/client.py` — LLM 仍然輸出純文本
- `core/parsing/dynamic_character_parser.py` — `SIG~expression_overrides` 只是透傳，已有機制直接支持
- git commits: `da4d406 dynamic cp` ~ `40b6a87 gitignore`

---

## 六、實現路線

| 階段 | 內容 | 交付物 |
|------|------|--------|
| Phase A | `emotion_map.yml` + `SpriteMapper`（查映射表） | 靜態映射層，無 AI |
| Phase B | `EmotionClassifier`（規則 + 可選本地模型） | 情感分類層 |
| Phase C | `ExpressionController`（防抖 + 切換邏輯） | 頻率控制 |
| Phase D | `send_message` 返回值改為 `AgentResponse` | 集成到 MomoTalk |
