# 纪念立绘生图速度实验（2026-08-24）

> 目的（预判式 memorial 设计, 用户决策点 3）: 测本地 SD1.5 对"总结性描述"的生成速度——
> 快则剧情中 LLM 可自由发挥（当场生图兜底也可接受）; 预判→后台线程生图需覆盖首次加载耗时。

## 环境

- 模型: `D:\by-user\fossf\AI\models\AI-ModelScope\stable-diffusion-v1-5`（本地 SD1.5, offline）
- GPU: RTX 5070（CUDA, float16）| 512x512 | 脚本 `experiments/memorial_gen_speed.py`

## 结果

| 项 | 耗时 | 说明 |
|---|---|---|
| 首次生成（含 pipe 懒加载 from_pretrained） | **14.08s** | 加载 ~12s + 生成 ~2s |
| 二次生成（pipe 复用, 20 步） | **2.59s** | 纯生成 |
| 三次生成（15 步） | **1.93s** | 步数越低越快 |

生成图: `D:\by-user\fossf\AI\output\gen_20260824_010200_42.png`（580 KB, seed=42 可复现）

## 发现

1. **pipe 复用后 2s/张——足够"LLM 自由发挥"**：当场生图兜底（20 步 2.6s）在剧情中可接受；
   预判式设计下更是零感知（玩家互动期覆盖首次 14s）。
2. **CLIP 77 token 截断**：prompt 超 77 token 尾部被静默截断（本次 184 > 77）——
   "总结性描述"必须精炼，或引擎把描述精简为关键视觉词（角色特征+场景+氛围+风格）。
3. **pipe 预热建议**：trigger 后预判无论 will_trigger 与否，都后台加载 pipe——
   预判 false 但剧情中 LLM 想触发时，pipe 已就绪，当场只需 2s（而非首次 14s）。

## 结论

预判式 memorial 设计可行：trigger → 预判（主 LLM 给场景总结）→ 后台线程预热 pipe
+（will_trigger 时）生图 → 剧情中 memorial_generate 零等待展示。

## 待验证（角色一致性）

SD1.5（原版）**不认识 BA 角色**——"黑色长发少女"只会生成任意角色，角色身份无法保证。
候选方案（后续实验）:
- **IP-Adapter / reference-only**：喂角色现有立绘（`assets/illustration/{char}/diff/` 现成素材）
  作参考图 → 生图保持角色外观（需验证 diffusers IP-Adapter 离线可用性）
- **人设卡外观描述**：从 profile.yml 提取外观特征拼进 prompt（改善但不保证像）
- 结论方向: "总结性描述 + 参考图"组合最可行; 需要一次角色一致性对照实验
