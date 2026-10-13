# `archive/digest_group/` —— **L2-a 分群（群 / `experience`）整族归档**

**归档日**: 2026-10-13（用户裁决："group 退役，但是把代码整合一下搬到 archive 里面"）。
**当时的提交**: 见 PROCEED §3 那一行"group 退役"。

## 这里是什么

| 文件 | 原来住哪 | 干什么 |
|---|---|---|
| `groups.py` | `core/brain/groups.py` | **引擎切块**（`akin` 连通分量 = "同类候选"）+ 渲染料 + 执行器（`apply_groups` / `apply_merges`）+ 并群候选（跨群 `akin` 边） |
| `round_group.py` | `core/digest/rounds/group.py` | 那一轮 LLM：吃【还没归类的块 / 已有的类 / 可能重复的类】, 产 `experience` 节点 + `member_of` 边（起名 / attach / merge） |
| `group.md` | `contract/digest/prompts/group.md` | 那一轮的输出契约文案（相位 `group`） |
| `test_round_group.py` | `tests/core/test_round_group.py` | 它的守门（⚠️ 搬走后 `parents[2]` 的 `sys.path` 计算失效, 要跑得先改路径） |

## 为什么退

1. **"归属"和"概括"都能被更轻的东西接手**: 归属 = 写侧顺手写的引用（引擎物化节点 + 边）;
   "概括"本来就是 **`belief`** 的活（`DESIGN_MEMORY_MODES.md` 自己写着"一个簇的代表性总结
   是描述, 不是决定 ⇒ 它不该住进 `belief`"—— 反过来说, 类那格也没有独立存在的必要）。
2. **名字守恒风险**: 类名是**地址**（`address.find_group` 只认 `title` 精确匹配, 不看别名）,
   抄错 = 分裂成两个类, 而唯一的解药（`merge`）又是一次 LLM 判断 + 一个会"从地址空间里
   抹掉一个名字"的动作。
3. **聚合是读侧的事**: MMT 那边"recall 一个『花』就能拿到同类的所有重要东西" ——
   `like` 的字面/语义那几路本来就在做聚合, 写侧不必先造一个容器。
4. **门槛不废, 换载体**: 原设计是"`akin` 原料 → `experience` 门槛（n≥2）→ `belief` 产出"
   （`DESIGN_MEMORY_MODES.md`）。退役后门槛改由 **`akin` 簇直接对着 `belief`**:
   引擎算出"**没有被共同 belief 压住的 akin 簇**", 交给 L2 强制压住其中 ≥2 条 ——
   "兄弟"= 共同 `supports` 同一条 belief（**可图推导, 不需要新 kind**）。

## ⚠️ 还活在树里、**别删**的那一半（读侧机器件）

- `nodes.KINDS` 的 `"experience"` · `graph.REL_MEMBER_OF` · `store._PREFIX["experience"]="g"`
- `address.find_group` · `read/find.py` 的 `group` 锚 · `like._STRUCT_EDGES` 的"同类兄弟"(0.80)
  · `walk.NARROW` 与 `_deep_neighbors`
- `material._groups_for_l2` / `_group_block`（`cognize` 的**冷路径**：库里已有类时仍会摆出它们）
- `revise.apply_cognitions` 的 soak 分支 · `contract.digest.parse_group` · `tables.PHASE_GROUP`

理由：**真机 haruka 现在就有 1 个 `experience` + 6 条 `member_of`**（同 `profile` 的 B 案口径
——"停产不是删格式"）。

## 想复活的话

1. 把三个文件搬回原位（`prompts/group.md` → `contract/digest/prompts/`）;
2. `contract/digest/registry.py::PHASE_FILES` 加回 `PHASE_GROUP: "group"`;
3. `core/digest/rounds/__init__.py` 的 `ROUNDS` 里插回那一行 `RoundSpec(key="group", …)`
   （`step`/`parse`/`material`/`writes`/`result_fields`/`skip`/`own_snapshot=True` 都在 git 历史里）,
   `DIGEST_SEGMENT_HARD_CAP` 720 → 600 那条注释也一并回退;
4. `core/digest/pipeline.py::IMPL` 与 `from core.digest.rounds import (…)` 各加回 `group`。
