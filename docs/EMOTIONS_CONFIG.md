# 角色资产配置填写手册（emotions.yml + outfits/）

> 面向：作者（人类）与 LLM 共读。真源 = `assets/illustration/{char}/emotions.yml`。
> 架构：2026-08-28 双投影定稿——**diff 静态图与 spine 动画同源**，一份值派生两个资源。

---

## 一、目录结构

```
assets/illustration/{char_id}/
├── emotions.yml          # 默认外观：情绪语义（唯一真源）+ 默认资源
├── outfits/              # 附加外观：每外观一个文件（层级恒 1）
│   ├── _template.yml     # 模板（复制即注册新外观, 勿直接改）
│   ├── newyear.yml       # 例：遥香新春（CH0087）
│   └── ...
├── diff/                 # 默认外观静态表情图（{spine}_{id}.png 命名）
├── spine/                # spine 包（每子目录 = 一包, 三件套 skel/atlas/png）
│   ├── {char}_spr/       #   表情包（情绪脸/光环; 数字动画 + Eye_Close_01 + Idle_01）
│   ├── {char}_home/      #   身体包（说话/待机/摸头; M4 双包后启用）
│   └── ...
├── portrait/  original/  voice/ ...   # GUI 头像 / 分层立绘 / 语音（不被词表引用）
```

---

## 二、emotions.yml（主文件 = 默认外观）

### 2.1 格式

```yaml
spine: haruka_spr          # 默认外观的表情包（= spine/ 下目录名）
body: Haruka_home          # M4 双包预留：身体包（可选）
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

## 三、outfits/（附加外观）

### 3.1 规则

- **每外观一个文件**，文件名 = 外观 id（英文小写，LLM outfit 意图输出用）
- 层级恒 1：label / spine / body / emotions 平铺，无嵌套
- **emotions 键必须 ⊆ 主文件键**（语义层唯一真源在主文件；超出 → 校验警告）
- **未写键 = 该外观无此表情的图** → 渲染端静默保持上一张（宁缺勿错）
  - 例：遥香礼服缺 12/13（官方 CH0247_spr 没有 panic_2/outburst 动画）——这两键不写即可
- 值 = 资源 ID，规则同主文件；变体通常只有 spine 资产 → 写序号（diff 投影缺失自动容忍, 播放器优先 spine）

### 3.2 添加新外观（三步）

1. **资产就位**：spine 包拷入 `spine/{外观}_spr/`（+ `{外观}_home/` 如有身体包）
2. **验证动画名**（确认哪些情绪有动画、哪些缺）：
   ```bash
   node l2d-demo/scripts/anim_list.mjs   # 或对照官方资源说明
   ```
3. **复制 `_template.yml` 为 `{外观id}.yml`**，填 label + spine/body + emotions（只写有的键）

### 3.3 示例（遥香新春）

```yaml
label: 新春                      # 人类可读名 → 喂 LLM 的服装词表
spine: CH0087_spr               # 表情包
body: CH0087_home               # 身体包（M4 双包后启用）
emotions:
  nomal: 01
  smile: 03
  # ...（13 键）; outburst 不写 = 新春装无失控表情
```

---

## 四、验证

```bash
# 解析检查（键数 / 动画映射数）
python -c "from pathlib import Path; from core.media.manifest import load_character_manifest; \
m = load_character_manifest(Path('assets/illustration/{char_id}')); \
print(len(m['sprites']), len([a for a in m['animations'].values() if a]))"

# 前端 API（起服务后）
curl http://127.0.0.1:8080/api/spine/{char_id}?outfit=newyear   # 未来支持 outfit 参数
```

---

## 五、与代码的关系

| 消费者 | 读什么 |
|---|---|
| `core/media/manifest.py` | emotions.yml → sprites（diff 路径）+ animations（spine 动画名）双投影 |
| `core/media/emotion_lexicon.py` | emotions.yml 逐行 → 键 + 注释 + eg → 喂主 LLM 的表情词表 |
| `core/media/catalog.py` | `sprite(char, emotion, outfit)` → SpriteMedia（static_path/spine/anim） |
| `webgui/routers/spine.py` | `/api/spine/{char_id}` → 包 URL + emotion→动画映射（前端播放器） |
| LLM 契约 | `story_scene` payload `outfit`（未来）→ 换装意图（词表外静默保持） |
