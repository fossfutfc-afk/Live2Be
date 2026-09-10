# docs/archive/ — 归档设计文档

> **归档政策（2026-09-02）**: 被取代/过时的设计文档移入本目录，**不再更新**。
> 一切以代码为准；活文档在根目录与 `core/`、`docs/` 中维护。

| 文件 | 归档日期 | 原因 | 取代者 |
|---|---|---|---|
| `DESIGN_BRAIN.md` | 2026-09-02 | 与 DESIGN_MEMORY 合并 | 根目录 `DESIGN_BRAIN.md` |
| `DESIGN_MEMORY.md` | 2026-09-02 | 与 DESIGN_BRAIN 合并 | 根目录 `DESIGN_BRAIN.md` |
| `DESIGN_SAVE.md` | 2026-09-02 | 存储布局 v1（per-char sessions），代码已迁 worlds/ v2 | `core/session/store.py`（v2 世界模型） |
| `DESIGN_AGENT.md` | 2026-09-02 | 算法做导演早期方案（CLAUDE.md 早已标注过时） | 视觉意图协议（core/director/） |
| `DESIGN_BOND_CONTRACT_V2.md` | 2026-09-10 | 旧契约（单动作 JSON + 板级粒度） | `docs/DESIGN_VN_UPGRADE.md`（记录流 v2） |
| `DESIGN_CHOICE_PREGEN.md` | 2026-09-10 | 选项候选预生成（收敛链终局, sibling 为终态） | 同上（"选项"被 Sensei 台词槽取代） |
| `DESIGN_SCENE_STREAM.md` | 2026-09-10 | 旧契约下的板级场景流 | 同上（按段标注原则被继承, 形态被取代） |
| `DESIGN_BOND_STORY.md` | 2026-09-10 | VN 引擎旧运行时（双动作 + 双 registry） | 同上（§8 registry 关系清单） |

> 历史版本保留在 git 中；本目录存的是归档时刻的最后版本。
