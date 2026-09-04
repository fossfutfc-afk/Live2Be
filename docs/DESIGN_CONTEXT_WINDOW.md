# 统一上下文窗口（Context Window）——设计 v1（2026-09-05）

> 状态: 设计草案, 待用户审阅后实施。
> 触发: bond story 无 MMT 记忆（触发断桥）→ 用户拍板分工定稿——
> **滑动窗口 = LLM 获取上下文（最近发生了什么）的唯一逻辑, 域无关**;
> wiki = 长期记忆; 角色卡 = 人设; 其余 = 系统设置。

## 1. 定位与分工（定稿）

| 层 | 内容 | 通道 |
|---|---|---|
| **上下文（短时）** | 事件流最近窗口——mmt 对话 / bond 剧情 / 纪念时刻 | `render_events` 统一渲染, **任何域唯一入口** |
| **长期记忆** | wiki（digest 产物） | brain 注入（出厂背景 yml + 运行时 wiki, 已解耦） |
| **人设** | 角色卡（profile/personality/knowledge/experience…） | config 直注（system） |
| **系统设置** | 世界观/规则/词表/动作 schema | 系统层注入（system） |

现状差距: momotalk resume 已从事件流重建窗口 ✓; **bond 触发时 `_history` 空**（首场只靠
reason 便签）——统一后任何剧情开始（触发/恢复）都从事件流灌最近窗口, 断桥自然修复,
reason 便签可退役（title 顶上）。

## 2. 事件 → 上下文文本（渲染规则）

统一渲染原则: **上下文里只放"发生过什么的叙事/对话", 不放结构元数据**
（place/emotion/background/visual/图 URL 等是导演/资产字段, LLM 读它们无意义）。

| 事件 | 渲染为 | 规则 |
|---|---|---|
| `mmt/mmt_chat` | user=player 文本; assistant=reply | 现状保留: 去动作括号 + 切块模拟逐条消息（`split_reply_chunks`） |
| `mmt/mmt_trigger_bond_story` | 不渲染正文 | 触发动作是系统转折点——但其 reply/reason 已在同轮前后（trigger 轮有 text 邀约话独立成 mmt chat? 需核对——设计: 只渲染该事件里的 reply 文本若非空, 不给 reason） |
| `bond/story_scene` | user=input（玩家输入/旁白种子）; assistant=叙事提取 | 见 §2.1 |
| `bond/memorial_enter` | 同 story_scene 叙事提取 | memorial 主体是 bond 事件（paragraphs=煽情文字）——**必渲染**, 行首标 `（纪念时刻画面…）` |
| `bond/memorial_exit` | 叙事提取（过渡文字） | 同上 |
| `l2d`（TYPE_L2D, 预留） | payload 若有 paragraphs → 文字同叙事提取 | 图 URL/资产引用不进（标 `（画面）` 占位即可）; 无文字 → 跳过 |
| `marker/*` | 跳过 | 状态标记（vn_enter/vn_state/…）不进对话上下文——但 vn_enter 的 reason? 触发起因由**窗口里的触发前对话**承担, reason 退役后无此字段 |
| `affection/*`, digest 事件 | 跳过 | 系统结算, 非叙事 |
| `official_story`（预留） | 同 bond 叙事提取 | 无生产数据, 规则预留 |

### 2.1 bond 叙事提取（payload → 文本）

输入 payload 实际结构: `{title?, paragraphs[{text, emotion}], choices[], picked?,
branches?, is_end?, input, background?...}`

```
标题（若有 title）:      「{title}」
段落:                  每段一行: `{text}（{emotion}）`——emotion **必须随行保留**
                       （2026-09-05 用户拍板: emotion 是回放表情时间轴的基础——
                       上下文/回放/渲染三消费方读同一真源）; 旧事件无 emotion → 不标
选项:                  （选项: {choices 文本逐条 }）——出现于场景带选项时
picked:                玩家选了 → （选择了: {picked 文本}）——分支走向必须入上下文
is_end:                末尾标 （本章结束）——防 LLM 以为对话仍在中途
```

段落内联 emotion 保留 ✓; **branches 不展开**——玩家未选分支的内容属于"未发生的
可能性", 历史只需 picked 的那条走向。

**emotion 落库欠账修正（回放基础）**: 现状骨架先落库（`_log_scene_meta` 早于
`_enqueue_annotate`）, 事件段落可能无 emotion。修正: 标注 worker 完成后**原位回写**
最近一条 scene 事件的段落 emotion——`SessionStore.patch_last_event(char_id, ...)`
（append/patch 统一过文件锁; 破例仅限"最近一条 scene 事件的 emotion 字段定稿",
语义 = 记录补齐, 非历史篡改）。消费方（上下文/回放）读事件流即得终态, 零合并逻辑。

### 2.2 渲染产物形态

统一产物 = `[{role, content}]`（现状格式）——渲染后**每事件可能产出多条消息**（mmt
reply 切块多条的现状保留）; bond 事件产出 user+assistant 两条（input 空 → 只 assistant）。

## 3. 窗口与预算

### 3.1 预算计量（事件单元数, 不引 tokenizer）

bond 场景的"大小" = 段落数（每段一 emotion 标签——2026-09-05 用户拍板:
**直接数情绪标签个数即可**, 段落是天然语义单元）; mmt = reply 切块数。

- 窗口预算 = **最大事件单元数**（块: mmt reply 切块 / bond 段落）;
  长段（段落多）自然多占窗口——"程序计算长段占多少窗口"即数段。
- 默认: `WINDOW_UNITS = 120`（≈ 原 40 轮 × 2 条当量, 语义从"条数/字符"改为
  "单元数"——每单元是完整叙事句, 无半切）。单单元超长（异常段落 > 500 字）
  → 句号切句（中文句末优先, 无则英文 `.`, 再无硬切）后按句数折计。

### 3.2 驱逐单元（裁剪粒度）

1. 正常驱逐单元 = **一个叙事单元**（mmt 切块 / bond 段落）——窗口尾部倒序装填,
   超预算丢最老的整单元, 不半切
2. 异常超长单元（> 500 字）→ 句子化折计（§3.1）——保留最近句

### 3.3 窗口算法（伪码）

```
def window_messages(events, *, max_units=120):
    msgs = render_events(events)          # 全部渲染
    # 倒序装填: 最近的先保证; 单元数 = mmt 切块数 + bond 段落数（渲染时记录）
    units = 0; out = []
    for m in reversed(msgs):
        u = unit_count(m)                 # 该消息含多少叙事单元（段落/切块数）
        if out and units + u > max_units:
            break                          # 超预算 → 丢更老的整条
        units += u; out.append(m)
    return list(reversed(out))
```

> 计量口径=叙事单元（数 emotion/切块）, 不做字符-token 换算——简单且语义化。

## 4. 挂接点（实施清单, 每文件独立 commit）

| 文件 | 改动 |
|---|---|
| `core/session/store.py` | `patch_last_event(char_id, patch_fn)`——标注完成后回写最近 scene 事件段落 emotion; append/patch 统一过文件锁 |
| `core/session/renderer.py` | ① `render_bond_scene_text(payload)`（§2.1 提取——段落带 emotion/标题/选项/picked/结束标）② `render_events` bond 段与 l2d 段改用提取（不再 json.dumps 全 payload）③ `window_messages()`（§3.3, 单元数计量）④ 单测 |
| `core/bond/bond_story.py` | `_history` append 的 assistant 内容改 `render_bond_scene_text(action.payload)`（与 render_events 同格式——bond 内历史与统一渲染同构, 滑动无缝） |
| `webgui/bond.py` | ① 标注 worker 完成后 `patch_last_event`（emotion 定稿回写）② `bond_start` 构造 vn 后灌 `window_messages(store.events(char_id))` 进 `_history` |
| `core/momotalk.py` | `resume_session` 窗口截取改 `window_messages`（单元预算） |
| `core/ui/vn_cli.py` | 恢复路径同款灌窗口 |

## 5. 收益与边界

- bond 首场知道起因/邀约/气氛（真对话, 非 reason 便签）; reason 可退役（title 必填方案另见标题设计）
- 任何域恢复（resume/中断重进）上下文一致——窗口 = 事件流渲染, 无私有状态
- 上下文与 wiki 长期记忆并存不重叠: 窗口 = 原始叙事（最近）, wiki = 消化摘要（长期）
- 边界: 窗口内 bond 全场景文本（不压缩）——长剧情下预算内可容纳的"轮数"少于 mmt
  纯聊天时; 这是"按量占窗"的预期行为, 后续如需可加 bond 摘要压缩（v2 再议, 设计预留）

## 6. 待确认点

1. 窗口默认 120 单元（mmt 切块 + bond 段落）、单单元异常阈值 500 字——数值 OK?
2. 段落行格式 `{text}（{emotion}）`——可读性 OK? 还是想要映射中文（nomal→平静）
   或行首标签 `[smile] text`?
3. `patch_last_event` 破 append-only 例（仅 emotion 定稿回写, 过锁）——认可?
4. trigger 事件渲染: 只保留其 reply 文本（若有）, reason 不渲染——等 title 方案落定后 reason 字段退役, 本节再校
5. branches 不展开只记 picked——认可?
