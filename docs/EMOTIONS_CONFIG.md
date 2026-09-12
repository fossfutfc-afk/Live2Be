# 角色资产配置填写手册（emotions.yml + 板块结构）

> 面向：作者（人类）与 LLM 共读。真源 = `assets/illustration/{char}/default/emotions.yml`。
> 架构：2026-08-28 双投影 + 板块定稿——**每外观一个自包含目录**（diff/spine/emotions.yml 同处一板块），
> **diff 静态图与 spine 动画同源**，一份值派生两个资源。

---

## 一、板块结构（每外观 = 一个并行目录）

```
assets/illustration/{char_id}/
├── default/                  # 默认外观（id = default, 代码缺省值; 语义真源）
│   ├── emotions.yml          # 键 + 注释 + eg 写全（喂 LLM 词表读这里）
│   ├── diff/                 # 静态表情图（{spine}_{id}.png 命名）
│   ├── spine/                # 自己的 spine 包（{spine}/ 三件套）
│   ├── mmt/                  # 聊天头像帧（外观级）——MMT 列表的兜底来源, 见注①
│   ├── portrait/             # 该外观的 GUI 头像（MMT 列表首选来源, 见注①）
│   └── original/             # 该外观的分层立绘
├── newyear/                  # 附加外观（例: 遥香新春 CH0087）——自包含
│   ├── emotions.yml          # 只写资源（键 ⊆ default; 注释不重复）
│   └── spine/                # CH0087_spr + CH0087_home
├── dress/  suit/ ...         # 更多外观（目录里没有的 = 该外观没有）
├── ref/                      # ★ 角色级（生图参考——不随外观走, 放角色根）
└── possession/               # ★ 角色级（物品图）
```

**关键规则**：
- **注① MMT 列表头像 = 每个角色各取自己的**（2026-09-12 定稿, `webgui/routers/mmt.py`）:
  优先级 `{cid}/{outfit}/portrait/*.png`（首选 `collection.png`）→ `mmt/*.png`
  → `diff/*Idle*.png`（前端一律圆形裁剪）。**遥香必须走 portrait/**——她的 `mmt/`
  里放的是整张立绘 sprite（1.4MB）, 当 52px 头像会糊成一团。
  （历史: 一度改成"全角色共用遥香那一张", 那是过度解读, 已回退。）
- **"有 emotions.yml 的目录 = 外观"**——扫描零歧义（ref/possession 无 yml 自动排除）
- **语义继承**：注释/eg few-shot 只在 `default/emotions.yml` 写全（LLM 词表注入永远读 default——换装不漂移词表）; 其他外观 emotions.yml 只写键 + 资源 ID
- **键 ⊆ default 的键**（超出 → 校验警告）; **未写键 = 该外观无此表情** → 渲染端静默保持（宁缺勿错）
- **新增外观 = 建目录 + 写 emotions.yml + 放资产**——完全正交，可整体拷贝/删除/分享

---

## 二、emotions.yml（每外观一份, 结构相同）

### 2.1 格式（default 写全; 附加外观省略注释）

```yaml
spine: haruka_spr          # 该外观的表情包（= 本板块 spine/ 下目录名）
body: Haruka_home          # M4 双包预留：身体包（可选; 西服等无身体包则不写）
diff_dir: diff             # 可选：静态图目录（缺省 diff）

emotions:
  nomal: 01                # 默认态: 抿嘴谨慎的样子        ← 值 = 资源 ID
  smile: 03                # 眯眼开心: 被夸奖/发自心底的开心  ← 行尾注释 = LLM few-shot
  # eg[smile]: 例句...      # eg 行 = 该情绪的示范例句（可选）
  custom: custom/a.png     # 自绘图：显式路径形态（可选）
```

### 2.2 值 = 资源 ID，双投影规则

| 值形态 | 含义 | diff 路径 | spine 动画 |
|---|---|---|---|
| `01`（无 `/` 无扩展名） | 资源 ID | `{diff_dir}/{spine}_01.png` 自动拼 | `01` 直接用 |
| `diff/xxx_03.png`（含路径） | 旧格式路径 | 原样 | stem 去 `{spine}_` 前缀（匹配才推导） |
| `custom/a.png`（无前缀路径） | 自绘图 | 原样 | 无（纯静态图, 播放器降级 diff） |

**添加新情绪**（两步）：
1. 图就位：官方资产 → 放 `diff/{spine}_{id}.png` 与 spine 动画名对应；自绘图 → 放任意路径
2. 加一行：`键名: 资源ID` + 行尾中文示范注释（这条注释就是喂 LLM 的词表描述——**必写，写清楚"何时用 + 什么神态"**）

### 2.3 YAML 注意

- `01` 会被 YAML 解析成 int 1（八进制）——**代码自动补零回 2 位**，作者写 `01` 或 `1` 均可
- 键名必须是英文小写（LLM 输出用）；键名对齐官方区名习惯（nomal 而非 normal 是官方笔误，保留）
- 行尾 `#` 注释和 `# eg[键]:` 例句是 few-shot 素材，逐行解析——**不要删**

---

## 三、添加新外观（三步）

1. **资产就位**：spine 包拷入 `{外观id}/spine/`（+ `{外观id}/home/` 如有身体包）; 静态图/头像/分层立绘按需放入
2. **验证动画名**（确认哪些情绪有动画、哪些缺）：
   ```bash
   node l2d-demo/scripts/anim_list.mjs   # 或对照官方资源说明
   ```
3. **写 `{外观id}/emotions.yml`**：label + spine/body + emotions（只写有的键）

### 3.1 示例（遥香新春）

```yaml
label: 新春                      # 人类可读名 → 喂 LLM 的服装词表
spine: CH0087_spr               # 表情包
body: CH0087_home               # 身体包（M4 双包后启用）
emotions:
  nomal: 01
  smile: 03
  # ...（13 键）; outburst 不写 = 新春装无失控表情（官方 CH0087_spr 无 13 动画）
```

---

## 四、验证

```bash
# 解析检查（键数 / 动画映射数）
python -c "from pathlib import Path; from core.media.manifest import load_character_manifest; \
m = load_character_manifest(Path('assets/illustration/{char_id}/default')); \
print(len(m['sprites']), len([a for a in m['animations'].values() if a]))"

# 前端 API（起服务后）
curl http://127.0.0.1:8080/api/spine/{char_id}?outfit=newyear
```

---

## 五、与代码的关系

| 消费者 | 读什么 |
|---|---|
| `core/media/manifest.py` | `{char}/{outfit}/emotions.yml` → sprites（diff 路径）+ animations（spine 动画名）双投影 |
| `core/media/emotion_lexicon.py` | default 的 emotions.yml 逐行 → 键 + 注释 + eg → 喂主 LLM 的表情词表 |
| `core/media/catalog.py` | `sprite(char, emotion, outfit="default")` → SpriteMedia（static_path/spine/anim） |
| `webgui/routers/spine.py` | `/api/spine/{char_id}?outfit=` → 包 URL + emotion→动画映射（前端播放器） |
| `webgui/routers/mmt.py` | 头像三层回落（`portrait/`→`mmt/`→`diff/`）→ `/api/mmt/characters` 的 `avatar`/`avatar_type`（注①） |
| LLM 契约 | `story_scene` payload `outfit`（未来）→ 换装意图（词表外静默保持） |
