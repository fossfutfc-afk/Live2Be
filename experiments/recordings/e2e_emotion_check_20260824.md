# 表情标注优化验证 — 三角色 e2e 对比（2026-08-24）

> 修复内容（2026-08-24 落盘）：
> - `llm/prompts/bond_story_rules.md`：paragraphs 语义从「叙事段落」改为**「情绪单元」**（一句对白或一个动作描写，情绪一致才合并；情绪变就切新单元）
> - `core/bond/bond_actions.py`（story_scene/story_end schema）：emotion 从**「可选，不填=延续」改为「必填，每单元必须标」**
> - `core/media/emotion_lexicon.py`：词表注入措辞同步（beats[].text → 情绪单元）
> - 契约结构 `[{text, emotion}]` 未变；`para_emotions` 延续逻辑保留为漏标兜底

## 运行

- 脚本：`experiments/e2e_smoke.py <char_id>`（本次起支持传参，默认 igusa_haruka）
- 引擎：deepseek-v4-flash，真实 LLM；每角色一个完整会话（MMT → VN → wrapup）
- 完整记录：
  - 阿露 `experiments/recordings/e2e_20260824_002945.md`
  - 佳代子 `experiments/recordings/e2e_20260824_002831.md`
  - 睦月 `experiments/recordings/e2e_20260824_002921.md`

## 结果总览

| 角色 | 词表键数 | VN 场数 | emotion 标注 | 词表外键 | 角色专属表情使用 |
|---|---|---|---|---|---|
| 陆八魔 阿露 | 16 | 7 | 每单元都有 | 0 | fake_confident / worry / confident / laugh ✅ |
| 鬼方 佳代子 | 9 | 5 | 每单元都有 | 0 | sigh / nervous ✅ |
| 浅黄 睦月 | 15 | 7 | 每单元都有 | 0 | tease / laugh ✅ |

## 关键观察

1. **零漏标**：三个角色 VN 的**每个段落前都有 `[表情 xxx]`**——对比修复前
   （`e2e_20260823_173549.md`，段落级 + emotion 可选）存在"无 `[表情]` 直接进段落"
   的漏标段（源数据里 paragraphs 项缺 emotion 字段）。修复后未再出现。
2. **词表 100% 合规**：所有 emotion 键都在各自角色词表内（渲染端 `catalog.sprite`
   可查到对应图，不会落到默认/无图）。
3. **角色专属表情被用上**：阿露的 `fake_confident`（假装自信）、`worry`（没底）；
   佳代子的 `sigh`（无奈叹气）、`nervous`（棘手紧张）；睦月的 `tease`（调戏）、
   `laugh`（库呼呼大笑）——不再是修复前那种清一色 nomal 兜底。
4. **粒度正确**：动作描写单独成单元（如"（她垂下眼帘，手指摩挲枪套）"→ pensive），
   对白按情绪切单元（"老师，你来了。"→ respond → "……我一直在想…"→ pensive），
   情绪变化即切新单元。

## 旁注（非阻断）

- **角色名变体**：阿露 VN 中 LLM 两次把「佳代子」写成「佳世子」、「睦月」写成
  「无月」——名字变体问题（typical.yml 校准），与 emotion 机制无关。
- **通用键拼写已统一**：遥香/佳代子词表原用 `embarass`（拼写错误），已于
  2026-08-24 修正为 `embarrass`（与阿露/睦月一致）。`nomal` 保留（BA 官方笔误，
  社区传统）。
- **触发差异**：阿露/睦月第 2 轮自然触发 VN；佳代子 3 轮未触发（软门槛正常表现，
  脚本强制进入覆盖 VN 板块）。

## 结论

emotion 必填 + 情绪单元方案在 3 个不同词表角色上**全部生效**：表情密度显著上升、
词表零越界、且角色人设通过专属表情得到体现——此前"可选+延续 → AI 偷懒 → nomal
兜底"的失忆问题未再复现。
