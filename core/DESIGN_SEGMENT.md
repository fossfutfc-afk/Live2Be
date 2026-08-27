# 段模型（SEGMENT）—— Live2Be 的根基数据模型

> 2026-08-27 用户声明 + 实现确认。**最小单元 = Trigger mmt + Bond story + Finish mmt**。
> 这是项目大部分处理的底层结构（digest / 好感 / 回退 / regenerate / 回放 / 中断都基于它）。
> 所有子系统在设计中引用本档，避免各自发明边界。

---

## 1. 最小单元（根基声明）

```
段（SEGMENT）= Trigger mmt（铺垫） + Bond story（主体） + Finish mmt（余韵）

  Trigger mmt: 触发羁绊剧情前的手机聊天——"为什么进入这段剧情"（上下文）
  Bond story:  剧情主体——"发生了什么"（核心）
  Finish mmt:  剧情结束后回到手机的余韵——"关系如何变化"（情感收尾）
```

**为什么是它**：一段"经历"的语义完整单位 = 铺垫 + 主体 + 收尾。
截断在任何一环都会破坏"一次记忆"的完整性（定稿原则：**根本不产生截断**）。

## 2. 事件流时序（digest 输入的自然边界）

```
[段1 trigger mmt] [bond1] [wrapup1*] [finish1 余韵 MMT] [段2 trigger mmt] [bond2] ...
                  └─ digest1 ─┘                        └── digest2 ──┘
                        ↑ 本段闭环                         ↑ 本段闭环

* wrapup = bond 结束后的自动收尾消息（角色主动发几句）
  —— 已验证: vn_cli.wrapup_after_vn 先落库收尾消息, 再调 engine.async_digest() ✅

digest 触发点 = 本段 bond 闭环（wrapup_after_vn → async_digest）
digest 输入   = seq > digested_seq 的全部事件（增量, 已实现）
```

## 3. 推论：digest 消化范围（用户声明, 自动成立）

```
每次 digest 的输入【自然】= 上一段 Finish mmt + 本段 Trigger mmt + 本段 Bond story

原因（无需新机制）:
  · 触发点 = 本段 bond 闭环（在上一段 finish 之后）
  · 输入 = 上次 digest 点之后的所有事件（digested_seq 增量）
  · 上次 digest 点在上一段 bond 闭环——那时上一段的 finish 尚未发生
  → 上一段 finish 落入本段 digest——正是"上一段余韵 + 本段完整闭环"
```

**推论**：finish mmt 没有独立结束标记——由"下一段 trigger"隐式界定。
玩家余韵聊了很久（未再触发 bond）→ 该段延迟消化（wiki 不更新, 事件流完整,
resume 重建历史不受影响）——段完整性优先, 可接受。

## 4. 双轴正交：affection × significance（2026-08-27 定名）

```
affection（好感度 delta）  = 关系温度——情感价（正/负/零）
significance（显著性 0~1） = 记忆强度——这段经历对角色多深刻/多难忘

理论上 |affection| ≈ significance 大概率成立（强烈情感 → 深刻记忆）,
但【分离设计 handle 更多情况】——正交轴, 不合并:
  悲伤剧情:   affection 不增（甚至降） × significance 极高（深刻记忆）
  平淡铺垫:   affection 微增              × significance 低
  共同日常:   affection 增                × significance 中（值得记但不深刻）

用途分离:
  affection → 关系/解锁（高好感解锁）——"角色对你的感情"
  significance → 记忆/检索（高显著永存/优先召回）——"角色记得什么"
```

**字段名定名**：`significance`（不是 importance——importance 语义宽泛:
"对关系重要/对剧情重要/对世界重要"无法区分; significance 专指记忆显著性）。

## 5. 基于段模型的子系统（统一边界）

| 子系统 | 段模型语义 |
|---|---|
| digest | 本段闭环后消化上一段 finish + 本段 trigger + 本段 bond（§3） |
| 好感 | affection_exp_delta 按段打分（LLM 看完整段输入, 与 significance 分开判断） |
| 记忆 | significance 决定珍贵通道保底 / 检索排序（高显著永存） |
| regenerate（剧情粒度） | 撤销整段（vn_enter 后事件删除 + wiki 回滚） |
| 回退/回放 | 段为最小回放/回退单元（回放源: 当前线 or 快照） |
| 中断 | 无闭环（无 story_end）→ 段未完成 → 不消化（"中断的剧情不处理"） |

## 6. 边界

- events.jsonl 唯一真源（段是事件的逻辑分组, 不新增存储）
- digest 不阻断主流程（async 后台, 失败静默降级）
- 平行世界: 段模型 per session（每世界线各自成段, 无跨线归并）
