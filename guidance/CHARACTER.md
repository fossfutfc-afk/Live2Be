# 配置一个角色

从零写一个角色的完整流程。想改现有角色，直接照抄 `config/characters/{id}/`。

> 心智模型：**你负责"她是谁"，程序负责"她怎么被用"。**
> 人设写完她就能聊天；立绘与头像是可选的 —— 缺了只降级，不报错。

## 0. 她要占哪几个位置

```
config/characters/{id}/                人设（profile.yml 是唯一硬要求）
├── profile.yml          外貌 / 年龄 / 社团 / 怎么叫她
├── personality.yml      性格
├── knowledge.yml        她知道的事
├── experience.yml       她经历过什么（原文直注，引擎不改编）
├── typical.yml          典型问答（few-shot，教模型学她的说话方式）
├── script.yml           扮演手册（分域基调）
└── illustration.yml     生图提示（可选，只影响纪念立绘）

assets/illustration/{id}/default/      外观（可选，但"头像"几乎必需）
├── emotions.yml         表情词表 —— **有它的目录才算一个"外观"**
├── portrait/collection.png   MMT 列表头像（首选约定名）
├── spine/{包名}/        骨骼动画（有它 VN 里才"活"）
└── diff/                静态差分（CLI 用；VN 不用）

config/settings/relation/interperson.yml   她眼里的别人
config/settings/mmt_registry.toml          出不出现在 MMT 列表
```

`id` = 目录名，惯例 `fname_lname`（如 `igusa_haruka`）。**改名要连四处一起改**（上面每个位置都按 id 派生）。

## 1. YAML 怎么写

- 缩进**只用空格**，2 个；`键:` 后面**一个空格**才是值
- 列表用 `- `，每项一行
- 长文本用 **`|`**（字面块）：**换行 = 排版（读取时删掉），空格 = 内容**
  - 别用 `>`（折叠块）：它解析时就把换行变成空格，汉字之间会多出空格 ——
    `knowledge.yml` 的 `SIG~friends` 就被这个咬过
- 前导零（`01`）在 YAML 1.1 里会被读成整数，`01` → `1`。**能加引号就加**：`"01"`
- 键名只写英文小写 + 下划线；中文放值里

## 2. 三个前缀：`REQ~` / `SIG~` / 无前缀

| 写法 | 含义 | 程序怎么用 |
|---|---|---|
| `REQ~字段` | 必填 | 缺失或为空 → 体检报满，**不阻断运行** |
| `SIG~字段` | 重要 | 计入"信息完整度"（填了几个 / 共几个） |
| `字段` | 普通 | 原样透传给 LLM，**完全不校验** |
| `字段: null` | 合法占位 | 跳过，不报错（"该有，先空着"） |

三条纪律：

1. 前缀是**键名的一部分**（`SIG~birthday:`），不是注释、不是行内标记。
2. 前缀标在**容器**上 = 整个容器重要，里层子项**不继承**。保持前两层干净就够了。
3. **引擎不认识的键照样进 prompt** —— 加一条设定就是加一行 YAML，不用改任何代码。

`profile.yml` 里必须有的两个：

```yaml
REQ~is_official_character: false        # OC 写 false（默认是 true）
REQ~most_called_name: 某某              # 你平时怎么叫她 → 显示名 / 存档 / MMT 列表都用它
```

`is_official_character` 目前只用于展示标注，**不会改变行为** —— 但别让自制角色自称官方。

`SIG~` 的用法看 `personality.yml` 的 `SIG~brief_traits`（一份短句清单）与
`SIG~detailed_personality`（展开说）—— 前者是摘要，后者是细节，两份都要。

## 3. `emotions.yml`：表情 → 图片

```yaml
spine: haruka_spr          # 可选：spine/ 下的包名（也是 diff 文件名的前缀）
diff_dir: diff             # 可选：静态图目录，缺省就是 diff
emotions:
  nomal: "01"              # 资源 ID 形态
  smile: custom/smile.png  # 显式路径形态
```

值的**两种形态**决定它怎么被解析：

| 值 | 判据 | 派生出的图片 | 派生出的动画 |
|---|---|---|---|
| `"01"` | 没有 `/`、没有扩展名 | `{diff_dir}/{spine}_01.png`（**需要 `spine:`**） | `01` |
| `custom/a.png` | 含 `/` 或扩展名 | 原样（相对 `{角色}/{外观}/`） | 文件名恰是 `{spine}_{名}.png` 时才有 |

### 做 OC（没有 spine）的关键一条

**值一律写显式路径。** 写 `"01"` 却没填 `spine:` → 拼不出文件名 → 那个情绪**静默没有图**，
不报错、不提示，只是表情不变。

## 4. spine 与 sprite 二选一

| | 有 spine | 只有 sprite |
|---|---|---|
| 目录 | `spine/{包名}/` 里 `.skel` + `.atlas` + `.png` **三件套齐全**才算一包（缺一件跳过） | 只要 `diff/` 或 `portrait/` |
| VN 里的立绘 | 能动（呼吸 / 眨眼 / 表情） | **不出** —— VN 只吃 spine，会退化成纯文字 |
| MMT 头像 | `portrait/collection.png` | 同一套；没 `portrait/` 时兜底找 `diff/*Idle*.png` |
| 聊天 / 记忆 / 剧情判定 | 一样 | 一样 |
| 纪念生图参考图 | `ref/`（可选） | 可省 |

**所以 OC 的现实预期**：MMT 里能聊天、有头像；**羁绊剧情里不出立绘**（纯文字仍可玩）。

**头像不是可选项**：MMT 列表会把"没有头像"的角色**直接跳过**（`webgui/routers/mmt.py`），
所以哪怕别的都还没做，也先放一张 `portrait/collection.png` —— 一张 png 就够。

## 5. `interperson.yml`：她眼里的别人

键 = **她的叫法**；值 = **她自己的看法**（主观，会随经历演化，不是客观档案）。

```yaml
{角色id}:
  self:                                # 保留键：她对自己的看法
    text: |
      一句话立场。
  sensei:                              # 保留键：老师（名字由玩家档案给）
    text: |
      她怎么看老师。
  aru:                                 # 有角色卡的人：给 id，引擎自己取显示名与别名
    id: rikuhachima_aru
    text: |
      她怎么看阿露。
  some_npc:                            # 没角色卡的人：给 name / aliases
    name: 便利屋的常客
    aliases: [常客, 那位]
    text: |
      她怎么看这个人。
```

- `self` / `sensei` 是**保留键**，引擎按名字认，别改成别的
- `text` 一信用 `|`：换行只是排版，空格才是内容
- 旧写法（值是数字 = 熟知程度）引擎仍认，但那套正在退役，新写的用上面的形状

## 6. `mmt_registry.toml`：让她出现在列表里

```toml
[[characters]]
id = "your_character"        # = config/characters/ 下的目录名
state = "experiment"         # active(正式) | experiment(半成品，标注出来)
bio = "一句话个性签名"        # MMT 主页的"个性签名"
birthday = "5/13"            # 显示用；profile 的 SIG~birthday 是给 AI 的，两处要一致
```

**顺序 = MMT 列表的显示顺序**。不在这里登记的角色，即使人设齐全也不会出现。

## 7. 最小可跑清单

只想到"能在 MMT 里聊起来"，四步就够：

1. `config/characters/{id}/profile.yml` —— 至少两个 `REQ~`
2. `config/characters/{id}/personality.yml` —— `SIG~brief_traits` 一份短句清单
3. `assets/illustration/{id}/default/portrait/collection.png` —— 一张头像 png
4. `config/settings/mmt_registry.toml` 加一条 `[[characters]]`

再往下补：`knowledge` / `experience` / `typical` / `script` 让人设变厚；
`emotions.yml` + `diff/` 让表情能变；`spine/` 让她在羁绊剧情里动起来。

## 8. 写完自检

```bash
# Windows release 用户
Live2BeSetup.exe --check

# 源码用户（macOS / Linux 也行）
python -m setup_tool --check
```

它会逐条报：路径对不对、每张角色卡能不能被**现役 loader** 读进来、哪些角色有卡没头像、
地点表声明的背景缺几张。有"问题"项时退出码 1，适合脚本。
