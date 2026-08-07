# Character Parser — 欄位驅動重構設計

> 狀態：設計階段，待實現。
> 目標：消除"加一個 YAML 欄位需改 4 處代碼"的硬編碼問題。

---

## 一、問題診斷

### 當前狀態

```
加一個 birthday 欄位 → 需要改 4 處：
  ① Profile dataclass 欄位定義
  ② _load_profile() 內的 raw.get("birthday")
  ③ to_prompt_lines() 內的 if self.birthday
  ④ _assess_info_level() 的 meaningful 列表
```

每個 YAML 欄位 → Python 欄位的映射都是手工維護的。5 個角色文件，10+ 欄位每個，= 50+ 處硬編碼。

### 為什麼會這樣

三個關注點被混合在一個方法裡：
- **載入**：YAML key → dataclass 欄位
- **格式化**：dataclass 欄位 → Prompt 文本
- **評分**：哪些欄位計入資訊完整度

任何一個變動都迫使修改另外兩個。

---

## 二、目標架構

### 核心原則：約定優於配置

> YAML key 名 = dataclass 欄位名，除非顯式覆蓋。
> 欄位不為空才注入 Prompt。
> `_meaningful` set 決定哪些欄位計分。

### 每個 dataclass 附帶三個 ClassVar

```
@dataclass
class Profile:
    # ═══ 類級別：欄位元數據 ═══
    _loaders: ClassVar[dict]     # 特殊加載器（無法1:1映射的欄位）
    _prompts: ClassVar[dict]     # 欄位名 → Prompt 模板片段
    _meaningful: ClassVar[set]   # 哪些欄位計入資訊完整度評分

    # ═══ 實例欄位（欄位名 = YAML key，除非 _loaders 中有覆蓋）═══
    most_called_name: str = ""
    age: int = 0
    birthday: str = ""
    ...
```

### 加欄位的前後對比

```
之前（硬編碼）:
  ① dataclass 加定義
  ② _load_profile() 加 raw.get("birthday")
  ③ to_prompt_lines() 加 if self.birthday
  ④ meaningful list 加 "birthday"

之後（欄位驅動）:
  ① dataclass 加定義
  ② _prompts 加一行 "birthday": "，生日{value}"
  ③ （可選）_meaningful 加 "birthday"
  _loaders 不動（因為 birthday 就是 flat 欄位，約定映射）
```

---

## 三、三個 ClassVar 詳述

### 3.1 `_loaders` — 載入映射

**只登記無法 1:1 映射的欄位**。登記的是**函數**，簽名 `(raw_dict) -> 欄位值`。

```
_loaders = {
    # ── 這些無法直接 raw.get(欄位名) ──
    "most_called_name": lambda raw: _extract_name(raw, "IMP_most_called_name"),
    "en_name":          lambda raw: _extract_name(raw, "en_name"),
    "jp_name":          lambda raw: _extract_name(raw, "jp_name"),
    "other_names":      lambda raw: _extract_name_list(raw, "other_name"),
    "is_official":      lambda raw: raw.get("is_official_character",
                                  raw.get("is_official-character", True)),
    "appearance":       lambda raw: _flatten_list_of_dicts(raw.get("appearance")),

    # ── 以下欄位不需要登記：age, height, weight, birthday,
    #   gender, position, gun_type, gun_name, interest, school, club, introduction
    #   因為它們就是 raw.get(欄位名) 的 1:1 映射 ──
}
```

`auto_load()` 的邏輯：

```
for each field in dataclasses.fields(cls):
    if field.name in cls._loaders:
        value = cls._loaders[field.name](raw_dict)
    else:
        value = raw_dict.get(field.name)  # 約定映射
    value = _safe_cast(value, field.type) # str→str, int→int, list→list
    setattr(instance, field.name, value)
```

**自我審視 — `_loaders` 的問題**：

一個 lambda 裡用 `raw.get("is_official_character", raw.get("is_official-character", True))` 來兼容舊鍵名——這類映射關係分散在 lambda 裡不夠明顯。**解決**：提取一個 `_KEY_ALIASES: ClassVar[dict] = {"is_official": ["is_official_character", "is_official-character"]}` 單獨管理鍵名別名，在 `auto_load` 中自動嘗試所有別名。這樣 `_loaders` 就只處理真正的結構轉換。

### 3.2 `_prompts` — Prompt 注入

每個欄位有一條格式模板，`{value}` 被替換為實際值。空值欄位 → 不輸出。

```
_prompts = {
    # 拼在第一行的欄位
    "most_called_name": "你叫{value}",
    "en_name":          "（{value}）",
    "gender":           "，{value}",
    "age":              "，{value}岁",
    "birthday":         "，生日{value}",
    "height":           "，身高{value}cm",
    # 獨立行的欄位
    "school":           "学校：{value}",
    "club":             "社团：{value}",
    "position":         "定位：{value}",
    "gun_name":         "武器：{value}（{gun_type}）",  # ← 跨欄位引用
    "interest":         "爱好：{value}",
    "introduction":     "简介：{value}",
}
```

**自我審視 — 跨欄位引用的問題**：`gun_name` 的模板引用了 `{gun_type}`——這是一個跨欄位引用，`auto_prompt` 需要從 instance 上取兩個欄位來格式化一個模板。這意味著模板不能只是 `str.format(value=...)`，而應該是 `str.format(**instance.__dict__)` 或 `str.format_map(vars(instance))`。兩者都可以，但 `format_map` 更乾淨：不需要先構造一個 dict。

**修正**：模板用 `{value}` 作為主值佔位符，也可以用 `{任何欄位名}` 引用其他欄位。`auto_prompt` 使用 `template.format_map(vars(instance))`。

**自我審視 — 分組問題**：第一行（名字+性別+年齡+生日+身高）是一個連續拼句，和後面的獨立行在渲染方式上不同。目前的 `_prompts` flat dict 不區分這兩種。這導致 `auto_prompt` 需要知道哪些欄位是"inline"（拼成一句）、哪些是"line"（獨立成行）。

**權衡**：引入 `_prompt_groups`（分組配置）vs 保持當前的手寫 `to_prompt_lines()`。我選擇後者——`to_prompt_lines()` 仍然**手寫分組邏輯**（約 15 行），但每個組內用 `_render_fields()` 宏來取值。這樣分組變動是可讀的業務代碼，而不是被配置化的黑盒。欄位增刪只需動 `_prompts`，分組不變。

### 3.3 `_meaningful` — 完整度評分

```
_meaningful = {
    "most_called_name", "en_name", "gender", "age", "birthday",
    "height", "school", "club", "position", "interest", "introduction",
}
```

`auto_score(instance)` → 計算 `_meaningful` 中有多少非空欄位。

**自我審視 — 問題**：`_meaningful` 和 `_prompts` 有很大重疊（大部分有意義的欄位也會注入 Prompt）。但兩者的語義不同：`_prompts` 關心"是否顯示給 LLM"，`_meaningful` 關心"是否代表用戶提供了信息"。例如 `gun_name` 會注入 Prompt 但可能不計入完整度（用戶填了槍名 ≠ 角色信息充分）。保留兩個獨立 set 是對的。

---

## 四、`_KEY_ALIASES` — 鍵名別名

`_loaders` 中 `is_official` 的兩個候選鍵名的處理方式不夠好。改為獨立的別名機制：

```
_key_aliases: ClassVar[dict[str, list[str]]] = {
    "is_official": ["is_official_character", "is_official-character"],
}
```

`auto_load` 在 `raw_dict.get(欄位名)` 返回 None 時，自動嘗試 `_key_aliases.get(欄位名, [])` 中的每個別名，取第一個非 None 的值。

**自我審視 — 過度設計？**：目前只有一個欄位需要別名（`is_official`）。為一個案例建一個通用機制有點過度。但考慮到：
1. 用戶可能拼錯 YAML key（`introduction` vs `intro`），別名機制可以優雅處理
2. 未來 config 結構變動時會產生更多別名需求
3. 實現成本極低（在 `auto_load` 中加 4 行）

→ 保留。

---

## 五、`auto_load` 引擎函數

```
def auto_load(dataclass_type, raw_dict) -> instance:
    instance = dataclass_type()
    for field in dataclasses.fields(dataclass_type):
        if field.name.startswith("_"):
            continue  # 跳過 ClassVar 和私有欄位
        
        # 優先級：_loaders > raw_dict[field.name] > _key_aliases
        if field.name in dataclass_type._loaders:
            value = dataclass_type._loaders[field.name](raw_dict)
        else:
            value = raw_dict.get(field.name)
            if value is None and hasattr(dataclass_type, "_key_aliases"):
                for alias in dataclass_type._key_aliases.get(field.name, []):
                    value = raw_dict.get(alias)
                    if value is not None:
                        break
        
        value = _safe_cast(value, _field_python_type(field))
        setattr(instance, field.name, value)
    return instance
```

### `_safe_cast` — 類型安全轉換

```
def _safe_cast(value, target_type):
    if value is None:
        return _default_for(target_type)
    
    origin = get_origin(target_type)  # list[str] → list, dict[str,int] → dict
    
    if target_type is int:
        try: return int(value)
        except: return 0
    elif target_type is str:
        return str(value).strip() if value is not None else ""
    elif target_type is float:
        try: return float(value)
        except: return 0.0
    elif target_type is bool:
        if isinstance(value, bool): return value
        return str(value).lower() in ("true", "1", "yes")
    elif origin is list:
        return list(value) if isinstance(value, list) else []
    elif origin is dict:
        return dict(value) if isinstance(value, dict) else {}
    
    return value  # 未知類型，保持原值
```

**自我審視 — `bool` 處理陷阱**：`bool("false")` 在 Python 中是 `True`（非空字符串）。`_safe_cast` 必須**先檢查原始型別**再轉換，即 `isinstance(value, bool) → 直接返回`，這一步順序不能錯。

**自我審視 — YAML 的 `1.0` vs Python int**：YAML 中 `age: 15` 解析後 `isinstance(15, int)` 為 True，所以 `int(value)` 安全。但 `age: "15"`（帶引號）才是字符串，`int("15")` 也安全。邊緣情況 `age: 15.7` → `int(15.7)` = 15（不報錯但精度丟失），可以接受。

---

## 六、`auto_prompt` 引擎函數

```
def auto_prompt(instance, mode: str = "full") -> list[str]:
    """根據 _prompts 自動生成 Prompt 行。
    
    mode="full": 所有非空欄位
    mode="identity": 僅名字+性別+年齡（基本身份）
    """
    lines = []
    for field_name, template in instance._prompts.items():
        value = getattr(instance, field_name, None)
        if not value:  # 空值不輸出
            continue
        line = template.format_map(vars(instance))
        lines.append(line)
    return lines
```

`format_map(vars(instance))` 允許模板引用同一實例上的任何欄位，而不僅僅是當前欄位。

**自我審視 — format_map 安全嗎？**：`str.format_map` 對缺失的 key 會拋 `KeyError`。如果 `gun_name` 的模板是 `"武器：{gun_name}（{gun_type}）"`，但 `gun_type` 是空字符串 → 不報錯（因為 key 存在，只是值為空）。但如果模板打錯字（`{gun_typo}`），會崩潰。這是一個可接受的風險——模板是我們自己手寫在 `_prompts` 中的，寫錯的概率低，而且單元測試會立即發現。

**自我審視 — 和手寫分組的關係**：`to_prompt_lines()` 不會被 `auto_prompt` 完全取代。它仍然手寫分組結構，但內部的欄位取值可以用 `_get(instance, "birthday")` 來做空值檢查，而不需要 `if self.birthday:`。

實際分工：

```
to_prompt_lines() → 手寫分組，用 _render(instance, field) 取值
  ├── 第一行（名字塊）：手寫拼接 most_called_name + en_name + gender + age + birthday + height
  ├── 第二行（學校塊）：手寫拼接 school + club
  ├── 第三行（定位塊）：_render(position) + _render_gun(instance)
  └── 後續行：遍歷 _prompts 中的 LINE 類型欄位
_render(instance, field) → 查 _prompts，空值跳過
```

這比重寫整個 `auto_prompt` 更務實。

---

## 七、對五個 dataclass 的影響

| 類 | 現狀 | 重構後 |
|----|------|--------|
| `Profile` | ~20 行 dataclass + ~30 行 loader + ~30 行 prompt = 80 行 | ~20 行 dataclass + ~15 行 _loaders + ~15 行 _prompts = 50 行 |
| `Personality` | 兩個 list，loader 已簡單 | 幾乎不變（字段太少，不值得引入引擎） |
| `Knowledge` | 5 個 dict | 適用 auto_load |
| `Experience` | 嵌套結構，loader 複雜 | loader 保留手寫（嵌套太深，auto 不合適） |
| `Typical` | 兩個 list | 適用 auto_load |

**自我審視 — 適用範圍**：不是所有五個類都適合 `auto_load`。`Experience` 的 YAML 結構是 `self: [{常服: [{1: "..."}]}]` 這種三層嵌套，用 `auto_load` 反而更複雜。設計規則應該是：**flat 結構用 auto，嵌套結構保留手寫 loader**。

---

## 八、用戶常見操作對應表

| 操作 | 需要改動 |
|------|---------|
| 加 flat 欄位（如 `birthday`） | ① dataclass 定義 ② `_prompts` 一行 ③（可選）`_meaningful` |
| 刪除欄位 | ① 從 dataclass 移除 ② 從 `_prompts` 移除 ③ 從 `_meaningful` 移除 |
| YAML key 改名（`club` → `organization`） | 在 `_key_aliases` 加映射：`"club": ["organization", "old_club_name"]` |
| 值類型改動（str → list） | ① dataclass 改類型 ② `_prompts` 改模板（用 `{value}` 會得到 list 的 str 表示，可能需要 `_loaders` 加格式化函數）|
| 嵌套結構變動 | 只改 `_loaders` 中的提取函數 |
| 新增特殊加載邏輯 | `_loaders` 加一個 lambda/函數 |
| 新增角色文件 | 不需改代碼（`list_characters` 自動發現） |

---

## 九、不做的事（非目標）

- **自動推導 `_meaningful`**：有欄位有值 ≠ 用戶提供了有意義的資訊。手寫一個 set 更清晰。
- **JSON Schema 校驗**：不在這個階段做。YAML 類型錯誤 → 靜默轉換為默認值，不拋異常。
- **把嵌套結構全部自動化**：只有在"多了比少了更複雜"的時候才自動化。`Experience` 的嵌套結構保留手寫。
- **把分組邏輯配置化**：分組是 UI 相關的決策，變動頻率低，不值得為它引入配置格式。手寫 `to_prompt_lines()` 中的分組順序即可。

---

## 十、實現代碼量估算

| 新增 | 行數 |
|------|------|
| `_safe_cast()` 函數 | ~25 行 |
| `auto_load()` 函數 | ~30 行 |
| `_render()` 輔助 | ~10 行 |
| `_extract_name()` 等共享輔助 | 已有，不變 |
| Profile `_loaders` + `_prompts` + `_meaningful` | ~40 行 |
| **總計** | ~105 行新增，同時刪除 ~80 行硬編碼 |

淨增 ~25 行，但每次加欄位從 4 處改為 2 處。

---

## 十一、重構風險

| 風險 | 緩解 |
|------|------|
| `auto_load` 的類型轉換太寬容，可能掩蓋 YAML 錯誤 | `_safe_cast` 在轉換失敗時記錄 warning（不拋異常） |
| `format_map(vars(instance))` 跨欄位引用可能打錯字 | 單元測試覆蓋所有 `_prompts` 模板 |
| 重構期間破壞現有加載邏輯 | 保留現有 10 個測試用例，重構後全跑一遍 |
