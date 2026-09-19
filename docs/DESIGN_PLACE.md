# 地点 / 背景系统（DESIGN_PLACE）——**现网事实**

> **这份文档是什么**：地点与背景系统的**唯一一份**设计文档。2026-09-20 重写——
> 旧稿（09-05 定稿 + 09-15 状态头 + 09-19 三次补丁）已删，它是一份"设计意图 +
> 作废章节 + 进度勾选"混在一起的千层饼，读它的人（包括 AI）会被带偏。
> 旧稿里那些**曾经写过、但一条都没做**的话，集中收在 §10，见到就当它不存在。
>
> **读法**：§1–§2 是一分钟版；§3–§7 是机制；§8 是作者侧工作流；§10 是防坑清单。
> 本文只写**今天为真的事**。不确定时以代码为准（`core/media/place_table.py`
> `core/bond/place_annotate.py` `core/bond/variant_annotate.py`）。
>
> **落地进度**：PL0–PL6′ 全部完成（2026-09-19/20）；作者侧收尾清单见 §8.3；
> C 链路（`channel_impl.py`）**未通电**、语义检索**未接线**——都是有意为之，不是漏做。

---

## 1. 一分钟版

**writer 自由写地点（自然语言，表里没有也行）；后台标注层把它翻成表里的一个键；
同一个键往往有好几张图，再由第二遍挑出"这一场用哪一张"；记忆里同时存"键"
（管回放/同一张图）和"writer 原话"（管检索/同一个地方）。**

四条不变量（改代码前先记牢）：

| # | 不变量 | 为什么 |
|---|---|---|
| 1 | **主 LLM 零内容词表**——不注入任何地点清单（只有一个例外，见 §6） | 从 168 条菜单里挑 = **收窄**创作空间（用户 2026-09-15 裁决） |
| 2 | **键 = "用哪张图"的编号，不是"这是哪儿"的名字** | 一键多义（`ruinschoolcorridor` 也能当"杂草屋"）与一地多键（`天台` → 3 个键）**实测都在表里活着** |
| 3 | **key 不可改**（回放按 key 查表，事件流 append-only）；改名的唯一合法路径 = 只改表 + 写台账（§5.2） | 旧事件里躺着的是"当时按哪张图演" |
| 4 | **视觉键不进 LLM 上下文**（`place` / `place_asset` 都不进） | resume 窗口不被视觉键污染（`core/session/renderer.py` 只读 text/emotion/inner） |

---

## 2. 一条地点话的完整旅程

```
writer 发  {"stage":"switch","text":"深夜的格黑娜学院天台"}
   ↓ 这里写什么都可以（表里没有也行 —— 这是设计，不是 bug）
引擎       bond_story.fill_scene_places()
   ↓
① 第一遍：定"哪个地点"      resolve_place()   [core/bond/place_annotate.py]
     层1  表里的 place + keywords 做字面命中（整串 → 最长子串≥2字）→ **0 次调用**
     层2  把**整张表（含 note）**丢给廉价 LLM 就近推测 → 1 次调用（off-thinking）
     都失败 → ""（keep，画面不动）
   ↓ 键 = school_rooftop
①′ 第二遍：定"用哪一张图"    pick_image()      [core/bond/variant_annotate.py]
     该键只有一张图 → **不发调用**（22/168 个键）
     否则：候选 = 该键 files 的每一张（夜/夕/差分2…），**作者 note 原样进 prompt**，
           输出必须是候选文件名之一，判不出 → 空 = 保持
   ↓
② 句级锚点：板内后续又换场   annotate_places()（两道 0 调用闸先过，见 §4.3）
   ↳ 锚点也是换场 ⇒ **同样会选图**，落在**段落**上：
     paragraphs[i].place 与 paragraphs[i].place_asset
   ↓
scene.place         = 键          ← 进事件流（回放/记忆/两轴）
scene.place_hint    = writer 原话   ← 进事件流（检索/追溯）
scene.place_asset   = 选中的文件（表内相对路径；空 = 默认图）
   ↓
引擎 _place_scene_id()  键 → 资产 scene_id（classroom → class_room，翻译靠 files 文件名）
   ↓
路由 _resolve_scene() → **优先表的路径**（place_asset → /assets/background/…），
                        catalog 只作回落 → 前端换图（缺图 → 黑屏 + 报出来，§5.1）
```

**两个最容易搞错的翻译**：

* **表键 ≠ 资产 scene_id**。`classroom` ↔ `class_room`；`68office` ↔ `kohshinjo_room`。
  翻译只走 `PlaceEntry.scene_id()`（从 `files` 文件名派生），**不是靠猜名字**。
* **板级 `place_asset` 管板首那一段，段落级 `paragraphs[i].place_asset` 管锚点之后那一段**——
  段落没写 asset 就回落该键的默认图，绝不会串用板级那张。

---

## 3. 表：`config/settings/world/place_entities.json`

作者在 **tempo 工作台**（`D:\myStuff\tempo\place_studio.py`）整理、导出，**拷进 repo**。
仓库里只有这一份，**不再有第二份手维护的词表**（旧的 `places.yml` 已于 PL4 删除）。

```json
"big_bridge": {
  "sdir": "SDIR_Streets",         // 资产大类（作者的语义分组；也是"写作用词"的判据）
  "dir":  "DIR_BigBridge",        // 资产子目录
  "place": "big_bridge",          // ★ 查表键（唯一标识；外层键 == 它，A1 不变量）
  "region": "",                   // 剧情地理（regions.yml 主名；148/168 仍为空）
  "keywords": ["桥", "天桥"],      // 别名 —— 层1 精确命中的语料
  "note": "……",                   // ★ 作者写的用途说明 = **资源说明书**（见 §4.2）
  "files": {"day":   ["SDIR_Streets/DIR_BigBridge/BG_BigBridge.jpg"],
            "night": ["SDIR_Streets/DIR_BigBridge/BG_BigBridge_Night.jpg"]}
}                                 // files 相对 assets/background/
```

**规模（2026-09-20 实测）**：168 键 · **428 个别名**（`place`+`keywords`）·
194 张时刻图（`_Night` 153 / `_Sunset` 35 / 其余少量）· **45 个键各有 ≥2 张"无变体"图**
（作者叫**差分**）· 22 个单图键 · 137 个键有时刻候选 · 层2 词表文本 **9378 字符**
（≈4.7k tokens，只在层1 未命中时付）。

**纪律**

| 纪律 | 落地 |
|---|---|
| **动态读入**（用户：*"官方地点的更新会调整措辞……最好动态读入而非写成死代码"*） | `load_table()` 按 `(path, mtime_ns, size)` 缓存 → 作者改完表**下一次调用即生效，不重启** |
| **路径只在 `core/paths.py`** | `paths.PLACE_TABLE_PATH`；`grep -n "^[A-Z][A-Z_]* = " core/paths.py` 是全量清单 |
| **缺表/坏表 → 空表降级**，绝不抛 | 引擎回落 `_director_whitelist.json` 的 31 条裸 slug（**只剩这一个用途**） |
| **坏条目逐条丢弃**；**重复键要报出来** | `object_pairs_hook` 数重复键 → WARNING + `PlaceTable.error`（手编 JSON 里写两遍同一个键，`json.loads` 是静默保留最后一个的） |
| **A1**: 外层键 == 行内 `place` | `tests/core/test_place_table.py` 守着（工具侧退回按族名建键就红） |

---

## 4. 判定层（两道主判定 + 两道省钱闸）

### 4.1 第一遍：哪个地点

| 层 | 做什么 | 成本 |
|---|---|---|
| **层1** `PlaceTable.resolve_exact` | `place` + `keywords` 的纯字符串命中：**整串优先**，否则取**最长子串**（针长 ≥2）；**不做反向包含**（`"z"` 会抓走一串 latin 键） | **0 调用** |
| **层2** `place_resolve.md` / `place_annotate.md` + `lexicon_text()` | 吃**整表**（`【中文分组头】` + 每行 `键（别名）［时刻候选］: note`），**就近推测**一张最说得通的图 | 1 次廉价调用（place 档，off-thinking） |

* **层1 歧义不猜**（`天台` 指着 3 个键）→ 照实返回多条，**下沉层2**（层1 只负责"确定无疑"那部分）。
* **"词表里没有"不是失败**（旧稿写过"宁可空着"——那是第一版为了让程序跑起来的遗老）：
  用户 *"writer 的自由不受限制……annotation-llm 只要看到 note 就能大致推测出地点"*。
* **`note` 是表外落位的唯一依据** ⇒ 缺 note = 这条路直接断（现只有 1 条空 note）。

### 4.2 第二遍：用哪一张图（时刻 / 天气 / 作者差分）

**同一个键在资源库里常有好几张图**，两条轴：

| 轴 | 例 | 之前 |
|---|---|---|
| **时刻 / 天气** | `_Night` 153 张 · `_Sunset` 35 张 · dawn/fineday/cloudy/rain/fog 少量 | `catalog.background(sid, variant=None)` = **永远第一条**，全都选不了 |
| **作者差分** | `BG_X.jpg` / `BG_X2.jpg`（"2 则有圣诞树"、"普通差分天台为主,差分2天空为主"） | 45 个键的差分只有 note 描述，**引擎永远取第一张**；`fishing_village`/`lighthousepier` 的 note 明写"请/建议使用差分2"，**没有任何消费方** |

**做法**：候选**从文件名派生**（`PlaceEntry.image_candidates()`，标签机器生成：
`夜` / `默认·差分2`），**作者 note 原样进 prompt**（用户：*"我的部分 note 里面本身就
会教 LLM 某些特殊常用的夜景以及差分的区别"*），输出**必须是候选之一**。

⚠️ **不走关键词表**（用户当场否掉，四句反例已写进 `llm/prompts/place_variant.md`）：

| 文本 | 关键词表会判 | 实际 |
|---|---|---|
| 从早到晚，我都想一直陪在老师身边 | 夜 / 晨 | 范围成语，与此刻无关 |
| 这些灯光，感觉像在白天一样呢~ | 白天 | **比喻 + 否定** ⇒ 其实是夜 |
| 我一定要将老师的善良公布在光天化日之下！ | 白天 | 成语，与时刻无关 |
| 私は夜の散歩が一番好きです | 夜 | 外语 + 意愿句：喜欢夜里散步 ≠ 现在是夜里 |

关键词表会 3 句判反 + 1 句判错，而且**漏判是静默的**（画面停在旧图，没人报错）。
真机 12/12（含这四句）——见 `experiments/place_pick_real.py`。

**可选时刻子集** = `MOMENT_VARIANTS`（night/sunset/dawn/fineday/cloudy/rain/fog）。
**剧情状态类**（ruin/erode/off/party/fake/blur/dark/fire/alert/tent/sky）**刻意不进候选**：
现在没有任何信号源告诉标注层"这场戏停电了/被侵蚀了"，放进去只会变成瞎挑。

**调用纪律**：单图键 0 调用 · 判不出/候选外/坏 JSON/服务失败 → **保持当前画面**
（选错一张图比不动更糟）· 档位与第一遍相同（place / off-thinking / 256 tokens）。

### 4.3 句级锚点的两道省钱闸（PL3）

板内"writer 描述了移动却没发 switch"的补刀此前**每板恒定一次 9378 字符调用**，
而真机存档 20 板 / 93 段正文里含换场线索的板 = **0**。两道闸（都 0 调用）：

1. **线索预筛**：板内没有换场线索词（`core/bond/place_cues.py`，38 个位移动词：
   走出/走进/来到/推开/穿过…）→ 整板跳过，日志 `[place][SKIP] skip=no_cue`
2. **句级层1**：有线索，但每句都能被别名**唯一**命中且 ≠ 当前 → 直接落锚，`skip=layer1_hit`

⚠️ **闸2 从宽**：只要有一句带线索却解决不了（歧义/表外/与当前相同）就**整板交 LLM**——
省钱的代价只允许落在"确定无疑"的板上。**不许用"歧义∩当前就 keep"这种捷径**：
真机最常见的换场恰恰是「她拉着我**走出教室**，来到**天台**」（当前与目的地同时出现），
走捷径会让画面**永远不切**（有测试钉着）。

---

## 5. 缺素材 / 改名 / 回放

### 5.1 缺素材 → 黑屏 + 报出来（用户裁决）

> *"假如发现资源库里没有这张图，就用黑屏 black，且 alert/console.log 素材未找到即可。"*

**不再静默换一张别的图**（那样"看起来正常，其实错了"——真机 20/20 板显示教室就是这么来的）。
现状：`missing_asset` 随场景下发 + `background_url` = 黑屏 `black`；前端
`console.error` 每次都记 + 每个键 `alert` 一次。板级与锚点级都覆盖（板级独立于导演的
"保持上一场"，所以不会被上一张图掩盖）。

### 5.2 改名 → 只改表 + 留台账

key 不可改是**纪律**（回放按 key 查表），不是"改名不会发生"。合法路径：

```
python -m core.media.place_rename --from OLD --to NEW [--reason "…"] [--apply]
  ① 扫引用面: 事件流 payload.place + paragraphs[*].place + soul/staging + _place_review.json
  ② 改表那一行（先验证"能逐字节复原导出格式"才敢重写；目标键已存在 → 拒绝）
  ③ 留痕: data/worlds/{world}/place_renames.jsonl（append-only, 链 a→b→c 可回溯）
```
**事件流一个字不动**。台账的消费方 = `_place_bg()` 查不到图时先说
*"key 'X' 已改名为 'Y'（原因）"*，而不是笼统的"素材未找到"。
⚠️ 表是 **tempo → repo 单向同步**：就地改 repo 的表只对本机有效，源头也要改。

### 5.3 回放

* 旧事件没有 `place_asset` → 默认图（第一条）；没有改名台账 → 就是"素材未找到"。
* **append-only**：视觉键（`place` / `place_asset`）落 payload 是为了回放时间轴，
  不是为了补写。
* 记忆两轴（`core/brain/wiki_v2/digest.py` 物化）：`node.place` = **键**序列（字面相等 ⇒
  **同一张图**）· `node.place_raw` = **writer 原话**序列（语义相似 ⇒ **同一个地方**）。
  两个字段**都不进 LLM 上下文**。

---

## 6. 给谁看什么（三档分流）

| 档 | 判据（表自带 / 手写） | 给谁 | 状态 |
|---|---|---|---|
| **写作用词**（镜头/特效：`星空`/`纯黑`/`黄昏`…） | `sdir == SDIR_Atmosphere` 的 4 条 | **writer**——手抄在 `llm/prompts/bond_shots.md`【一】那行（盒B 的一块） | ✅ PL2；`test_bond_shots.py` 钉住"每个词层1 唯一命中" |
| **粗粒度地理**（学院/地区名，21 条） | `regions.yml` | **writer**——盒B【世界区域】块（**世界设定，不是菜单**） | ✅ T16 |
| **具体地点键 + note** | 整张表 | **标注层**（层2） | ✅ C1–C5 |
| **这一场的图**（候选清单 + note） | 该键的 `files` | **标注层**（第二遍选图） | ✅ PL6′ |
| 资产 scene_id | `files` 文件名派生 | 导演 / 前端 | ✅ C5 |

⚠️ `PlaceTable.writing_words()`（按 sdir 判）**至今没有生产消费方**——真正到 writer
手里的是那份**手写**的 `bond_shots.md`。改了表**不会**自动进盒，**两处都得动**。

---

## 7. 语义检索（`core/rag/place.py`，**未接线**）

* 语料 = **同一张表**（168 键 / 428 别名，PL4 起），手维护的 `places.yml` 已删。
* 返回**表键**（不是 scene_id）；层1 唯一命中 → 1.0 且 0 次 embedding；
  **歧义不猜** → 下沉语义层，服务不可用就 `[]`。
* 打分 = 键内**全部别名**取最大余弦（旧实现只留"范数最大"的一条 ≈ 只留第一条别名）。
* **生产零调用**（只 `experiments/rag_test.py` 用）——用户：*"我们需要一个地点语义检索
  来体现既视感以增强我们的召回策略"*，接线与召回策略同批。
* ⚠️ 表里**一个假名别名都没有**（428 条中 0 条），删掉的 `places.yml` 有 21 条
  ⇒ 跨语言从"字面命中"退化成"纯靠模型"。想要字面命中就在 tempo 表里加别名。

### 7.1 两轴融合 `magic`（2026-09-20, 用户口径）

> 用户原话: *"现在考虑一下背景 RAG，我觉得最好是混合策略，一个特殊的 magic function，
> 在 writer 词和 key 相似度都高的时候值高，反之一般"*

`core/media/place_fuse.py`（**纯函数、无旋钮、两边共用**）:

| 轴 | 输入 | 算什么 |
|---|---|---|
| **叙事轴 `sw`** | writer 原话 ↔ 记忆里的原话（`place_raw`） | **语义**（embedding cos, 要 `embed_fn`） |
| **素材轴 `sk`** | 键 ↔ 键（同名 / **别名相交** / **键名 token**） | **字面**（0 调用） |

形状 = **调和平均** `2·sw·sk/(sw+sk)`（用户选定）: 两轴都高 → 顶格; 一高一低 → 中;
**一轴为零 → 0**（形状自带语义: 不是"弱关系"）。严格顺序 `乘积 ≤ 调和 ≤ 几何`。
🚫 **无阈值**（T17）——只出分, 取 top-k 是合成层的事。

⚠️ **素材轴必须字面**: 键侧若也去 embedding, 两轴同源（都是文本↔文本 cos）→ 融合退化成
单轴。实测也支持字面: `天台` 指 3 个键而它们**别名直接相交**; 但 **`dir` 不能当判据**——
那三个键分属 `DIR_SchoolRoodtop` / `DIR_Rooftop` / `DIR_Building`（作者按**图族**组织目录）。

**接线现状**: 召回侧已接（`channel_impl.PlaceGate`: `raw = magic(sem, key_sim)`,
`detail` 带 `same_image` / `key_sim_by` / `axes`）; **解析侧（writer 原话 → 键）还没注入**
—— 它要的是"原话↔原话 + 候选键↔已知键", 数据来自那张 **AI 判过的映射回灌表**（现在**零条**,
且本地 embedding 服务 1234/1235 都不可达）⇒ 与召回策略同批做。

两轴融合还顺手修掉了 §7 之前记的那条**反向假阴性**（同地不同键: 键不等就不准入）:
现在 `sk` 的字面那一半（别名/token）能把 `school_rooftop` / `rooftop` / `building_roof_top`
连起来 —— 但**一轴为零仍然是 0**, 所以"只有措辞像、键八竿子打不着"的候选照样进不来。

---

## 8. 作者侧工作流

### 8.1 同步方向：tempo → repo（单向）

作者在 `D:\myStuff\tempo\` 工作（工具 `place_studio.py` + `_place_entities.json` +
`_place_review.json`），整理完把 **`SDIR_*/DIR_*` 资产树 + 导出表**同步进 repo：

```
tempo\_place_entities.json   →   config/settings/world/place_entities.json
tempo\_place_review.json     →   assets/background/_place_review.json（审校视图, 只作参考）
```
拷完**不用重启**（mtime 缓存），跑一次对账确认：
`python experiments/place_asset_audit.py`（A: 表 `files` ↔ 磁盘 / B: 运行时取图 / C: 目录形态）。

### 8.2 资产组织

`assets/background/{SDIR_*}/{DIR_*}/BG_{Scene}_{Variant}.jpg`。
**文件名不变 ⇒ `derive_background()` 派生的 scene_id 不变 ⇒ 换组织不影响查库**；
扫描会剪掉 `.`/`_` 开头的目录（`.thumbs` 之类）。

### 8.3 作者侧待办（PL7 清单）

| 事 | 现状 |
|---|---|
| `files.night` 归类 | 混进状态变体 25 张（ruin/erode/blur/off/dark/party/fake）+ 白天天气 7 张（fog/rain/cloudy/dawn/sky）；真夜景只有 115/168。⚠️ 选图只放行"时刻/天气"子集，**暂时无害** |
| 覆盖 | 435/1094 张 = 39%；`SDIR_Special` 59 组 **0 active**；`SDIR_Schools` 9/126 |
| `region` | 148/168 为空（用户说"作用不大"，可做可不做） |
| 写了 note 却没勾 active | `ruinpianoroom`（废弃琴房）等 |
| ⭐ **note 的写法现在有回报** | 第二遍选图**照办** note 里的偏好（"请使用差分2"已验证）。给每个多图键写一句"默认用哪张、几张差分各是什么场合"，就是最划算的投入 |

---

## 9. 纪律与测试

* **不许在代码里写死地名**（用户：*"最好是动态读入而非写成死代码"*）。
  还写死的地方：`webgui/routers/bond.py` 的 `_BG_FALLBACK_PRIORITY`（7 个 id，展示兜底）、
  `core/director/state.py` 的 `DEFAULT_BACKGROUND = "neutral"`。
* **路径走 `core/paths.py` 的宏**（`grep -n "^[A-Z][A-Z_]* = " core/paths.py`），
  现拼项目根路径会被 `tests/core/test_paths.py` 挡下。
* **镜像防漂移**：`bond_shots.md` 的镜头词 ↔ 表（`test_bond_shots.py`）；
  `CORE_CUES` ↔ rules ↔ `place_annotate.md` 三处同源；`SDIR_LABELS` 覆盖真表全部 sdir。
* **测试桩约定**：桩按 user 尾部关键字应答——`地点 id JSON`（换场翻译）、
  `变更句数组`（句级锚点）、**`选中的文件名`（第二遍选图）**、`情绪标签`、
  `记录员/整理者`。新增标注任务必须同步补分支，否则吞场景脚本（CLAUDE.md §11）。
* **真机脚本**：`experiments/place_switch_real.py`（真剧情，纯内存**不写事件流**）·
  `place_pick_real.py`（选图判定 12 用例）· `place_asset_audit.py`（对账）·
  `place_resolve_real.py`。

---

## 10. 会带偏你的旧话（见到就当它不存在）

| 你会读到的 | 真相 |
|---|---|
| `time_of_day`（"day"/"night" 字段，LLM 可选） | **不存在**。时刻现在由**第二遍选图**判（§4.2），判据是 scene 文本 |
| "注入活跃键表（region 子集 ≤100 中文名）给主 LLM" | **作废**。主 LLM 零内容词表（唯一例外 = 写作用词，§6） |
| "主 LLM 写 `place` 字段" | **作废**（记录流 v2 起 writer 只发 `switch`；WHEN 归它、WHICH 归标注层） |
| `config/settings/world/places.yml` | **已删**（PL4）。语料 = 表本身；`paths.PLACES_PATH` 也没了 |
| "`_director_whitelist.json` 是现役地点词表" | **过时**。它是**降级兜底**（表读不出来时才用） |
| 资产是 `BG_*` 一目录一场景 | **`SDIR_*/DIR_*` 两级**（作者的组织）；文件名不变，查库不受影响 |
| "一个 key 就是一张图" | **一个 key 是一族图**：194 张时刻图 + 45 个键的差分（§4.2） |
| "`catalog.background(scene_id, variant)` 是取图正路" | 取图**优先走表的路径**：catalog 的 scene_id 派生会漏 6 张时刻图（`BG_ClassRoom2_Night.jpg` 派生成 `class_room_2`） |
| "时刻可以从文本里用关键词判出来" | **被否**（四句反例，§4.2）。判据是"这句话在说什么"，归标注层 |
| "`PlaceRetriever` 返回 scene_id" | 返回**表键**；要图走 `asset_scene()` |
| "缺素材就兜底一张别的图" | **被否**：黑屏 + 报出来（§5.1） |
| "C 链路吃 `region`/`place` 判同地" | C 链路（`channel_impl.py`）**没通电**；`node.place`/`place_raw` 照常物化，等 v3 |

---

## 附：关键文件

| 件 | 干什么 |
|---|---|
| `core/media/place_table.py` | 表加载（mtime 缓存/坏表降级/重复键守卫）+ 层1 `resolve_exact` + 层2 `lexicon_text` + 候选图 `moments()/image_candidates()/asset_for()` |
| `core/bond/place_annotate.py` | 第一遍：`resolve_place`（层1→层2）、`annotate_places`（句级锚点） |
| `core/bond/variant_annotate.py` | 第二遍：`pick_image`（时刻/天气/作者差分） |
| `core/bond/place_cues.py` | 换场线索词（闸1）+ `CORE_CUES`（与两份 prompt 同源） |
| `core/bond/bond_story.py` | `fill_scene_places`（①定键 → ①′选图 → ②句级锚点 的顺序与延续态 `_current_place`/`_current_asset`） |
| `core/media/place_renames.py` · `place_rename.py` | 改名台账 + 改名工具 |
| `core/rag/place.py` | 语义检索（语料 = 表；未接线） |
| `webgui/routers/bond.py` | `_resolve_scene` / `_place_bg` / `_table_bg_url`（取图与黑屏回执） |
| `llm/prompts/place_resolve.md` · `place_annotate.md` · `place_variant.md` | 三道标注 prompt |
| `llm/prompts/bond_shots.md` | writer 手里的镜头词（手写，唯一给 writer 的内容词表） |
| 表 / 审校 / 白名单 | `config/settings/world/place_entities.json` · `assets/background/_place_review.json` · `assets/_director_whitelist.json`（兜底） |
