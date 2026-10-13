# PROCEED.md — 接续用（**整篇覆盖写**；上一版见 git 历史）

> **2026-10-13 · 位置 `0504bc3` · 树干净 · 本会话 943 → 960（+17 个提交）**
> 本会话干的是**大重构**（不是记忆/look 接线）—— 上一版 PROCEED 讲的是召回接线，已进 git 历史。
> 现状：**回归 1483 passed（约 3 分钟）· ruff 1511 → 387**。

---

## 0. 三十秒概览

用户要的是：把这个"缝补出来的"项目改成**正常 Python 项目的样子**，然后再扩展。
他定的四条：① 彻底改（允许改包名/import 路径）② 顶层保持分散但改名 ③ 测试随行重写
④ 文档只写 mmt/vn 输出形式 + digest + 召回三块（其余写进各包 `__init__.py`）。

工作方式（他明确要求）：
- **逐个包改，每完成一个包他会详细了解询问** → 做完整阶段就停下等他
- 每步**独立提交**；小板块配冒烟；大板块才跑全量回归
- **死代码一律先过目**，不许自行处置（这条已经救过一次，见坑 §4.3）

已定下的目标形状：
```
contract/   纯契约（零项目内依赖）
infra/      ★新建：paths / errors / atomic / fuse / 时间 —— 为断 core↔llm 环
llm/        外部适配器（只依赖 contract + infra）
engine/     ← 现 core/ 的领域部分
tui/        ← 现 renderer/ + core/tui/
webgui/  cli/(←apps/)   tests/   docs/{design,spec,archive}/
```

---

## 1. 下一步该怎么做（按顺序，可直接执行）

### 1b-2b · 拆常量与文档（**下一刀**）
- 常量 + `is_full_date` + `OUTPUT_RULES/OUTPUT_DISCIPLINE` → `contract/digest_tables.py`
- `DigestAction` + 字段块/语义块/契约文案 + 各文档定义 + `DEFAULT_ACTIONS` → `contract/digest_docs.py`
- 判据：**逐字节不变**（§4.8 的命令）
- ⭐ 顺手做：把 `digest_registry.py` 那 **7 行函数内 import 收回模块级** ——
  `digest_parse` 只需从 `digest_tables` 取常量，环就没了（1b-2a 留了注释说明这一点）

### 1b-2c · 收成包
四个平铺模块（registry / parse / tables / docs）→ `contract/digest/` 包 + `__init__.py` 门面。
引用面：全仓 `from contract.digest_registry import X` → `from contract.digest import X`（脚本替换）。

### 1b-2d · 重命名（用户已批"一起改掉"）
- `parse_round_a` → `parse_record`（相位 `record`）
- `parse_round_b` → `parse_decisions`（与 `apply_decisions` 成对；**这一族是停放的，只改名不删**）
- `DigestAction` → `PhaseDoc`（它描述的是"相位产出的文档"）
- 同步改 `docs/TODO_TWO_PASSES.md:94` 里那条记名 + `tests/core/test_digest_registry.py` 里约 60 处

### 1c · 文案外移（`TODO.md` 里那条）
digest 的 LLM 可见文案 → `llm/prompts/*.md` + `{{槽}}`（用 1a 做好的 `render_template`）。
⚠️ 这一步**真的改文本** ⇒ 必须刷 `tests/core/test_promptkit_baseline.py` 的夹具并人工审 diff。

### 1d · 三引擎接原语
用 1a 做好的 `llm.retry.call_with_feedback` 替掉三份自写循环。**digest 先**（它已经抽过一层），
再 bond、再 mmt；**每切一家跑一次全量**。这是全项目最易静默出错的地方。

### 1e · contract 收尾
删 IDE 死域（`constants.py` 的 `APPROVAL_*`/`DOMAIN_IDE`/`MAX_*` · `registry.py` 的
`IDEActionRegistry`/`parse_action_text` · `schema.py` 的 `build_schema` 只被 archive 消费）；
`records/__init__` 直指真家（消掉那 4 处再导出与 5 条 F401）。

### 然后 · 批次 2 起
纯移动：`core` → `infra/` + `engine/`；`renderer+tui` → `tui/`；`apps` → `cli/`。
⭐ `infra/paths.py` 要做 **frozen-aware**（用户要打包成 exe；现在 `Path(__file__).parent.parent` 必炸）。

---

## 2. 必读文件

| 文件 | 为什么 |
|---|---|
| 本文件 | —— |
| `TODO.md`（我加的第一条） | prompt 外移那条待办 + 实测分布 |
| `docs/TODO_TWO_PASSES.md:94` | ⛔ **停放族裁决** —— 不删 `TOUCH/UPDATE/ADD`·`parse_round_b`·`apply_decisions` |
| `.testtmp/capture_schemas.py` | **逐字节判据工具**（25 个形态 + 全体 sha256） |
| `.testtmp/split_2a.py` | 切分手法样板（按连续行范围 + 从实现生成委托签名） |
| `contract/digest_registry.py` / `digest_parse.py` | 当前契约层形状 |
| `CLAUDE.md` | ⚠️ 89 KB 且**多处过时**；当索引读，冲突时信代码 |

---

## 3. 已做的更改（按批，都在 master）

| 批次 | 提交 | 做了什么 |
|---|---|---|
| 0 | `dbb8ca2` | `pyproject.toml` 成唯一工程真源（删 `pytest.ini`/`requirements*.txt`）；修 6 处注解 bug；`.vscode/settings.json` 入库 |
| 0.5a | 同上 | ruff 配置诚实化：干掉 167 条假 `invalid-syntax`；`select` 加 BLE、去掉 E402 的 ignore（**398 条 noqa 本就是刻意标注**） |
| 0.5b | `df8ef0d` | 删 257 个 `# -*- coding: utf-8 -*-` |
| — | `67f8ba8` | **修真 bug**：digest 预算预检 `>` → `>=`（Windows `monotonic()` 粒度 15.6ms，0 秒硬顶等于没预检；191/200 → 0/200） |
| 0.5b′ | `8cc1907` | 删 100 个测试文件的 `sys.path.insert` hack + 9 个孤儿 `ROOT` |
| 0.5c/d | `e66e504` | UP037 去多余引号 + UP035 + I001 排序（197 文件） |
| — | `4420f31` | **修 3 处真 bug**：注解引用了没导入的名字（UP037 去引号后由守门捉住） |
| 0.5e | `5523fd4` | 删 23 处未用 import + 190 条无用 noqa |
| — | `809b017` | 修 tests 两处缺 import / 未绑定名 |
| 1a | `2a91e29` `b15cfdc` `6af53af` `54a61e6` | **抽出三个共享原语**：`llm.client._classify`（传输重试判据唯一）· `llm.retry.call_with_feedback`（三引擎共用的重试循环）· `llm.prompts.render_template`（`{{槽}}` 双向下对不上就炸）· `schema.py` 规则编号按位置算 |
| — | `4aab6f5` | `ActionRegistry.specs()/prompt_specs()` —— 消掉"对可能为 None 取属性" |
| 1b-1 | `a15f426` | 删假旋钮 `include_examples`；修 `record` 相位的硬编码查名 |
| 1b-2a | `0504bc3` | digest 校验实现 → `digest_parse.py`（2345 → 1145 行），registry 留七个薄委托 |

---

## 4. 隐形坑（踩过的，别再踩）

**4.1 `ruff check --select X --fix` 是陷阱。** `--select` 会**覆盖** pyproject 的 select，
把其他规则关掉 ⇒ "本来生效的 noqa"被判成无用批量删掉（实测：192 条带尾随说明的
`# noqa: BLE001` 被删光，BLE001 从 18 涨到 205；而且它改的是**整个仓库**）。
删 noqa 只用 `.testtmp/strip_dead_noqa.py`（读**配置视角**报告、只删指定规则）。

**4.2 动 F401 前必须查"有没有人从这个模块 import 走"。** ruff 看不见再导出。
本会话栽过 5 处：`contract/records/{check,grammar,parse}.py` 的 4 个名字 +
`core/mmt/engine.py` 的 `parse_lines`（`api_surface.txt` 记着它是公开面）。

**4.3 ⛔ `parse_round_b` 那一族是用户明确停放的**（`docs/TODO_TWO_PASSES.md:94`：
*"有些可能会留给 L2，你觉得有用的不用着急删"*）。它在生产代码里**零调用者**（那 4 处命中
全是注释），看着像死件 —— **但不许删**。只改名。

**4.4 切分要按连续行范围搬，不要按 AST 节点取段** —— 后者会丢掉节点之间的注释，
而那些注释（`LINK_RELS` 的说明、每个助手头的判据）是这个仓的文档。

**4.5 循环依赖：`digest_parse` ← 常量 ← `digest_registry`。** 1b-2a 用**函数内 import**
解开（两个导入顺序都安全，已实测）。2b 之后环消失，记得把那 7 行收回模块级。

**4.6 跑测试必须带这两个参数**（`%TEMP%\pytest-of-johnf` 的 Windows 权限坏了，
在工作区**之外**，没清）：
```powershell
python -m pytest --basetemp=.testtmp/_pytemp -o cache_dir=.testtmp/_pcache
```

**4.7 解释器用 `C:\Users\johnf\miniconda3\envs\live2be\python.exe`** —— conda `base` 缺 `jieba`。

**4.8 逐字节判据怎么跑**（改契约文案/搬渲染代码时）：
```powershell
& $envPy .testtmp\capture_schemas.py > .testtmp\schemas_after.txt
Compare-Object (Get-Content .testtmp\schemas_before.txt) (Get-Content .testtmp\schemas_after.txt)
# 空 = 逐字节不变；当前基准 sha256 = a4464c4053b3e5ddfdd2722328b1a2f69452a819d64eeb74539d7e3f71d71f7a
```

**4.9 API 面守门**：给这 9 个模块**增删模块级名字**要刷 `tests/fixtures/api_surface.txt`
（`$env:SPLIT_API_UPDATE='1'` 跑 `tests/core/test_split_safety.py`），**并人工审 diff**：
`webgui.bond` · `webgui.chat` · `core.bond.bond_story` · `contract.records` · `contract.streams` ·
`contract.issues` · `core.mmt.engine` · `apps.vn_cli` · `llm.client`。

**4.10 PowerShell 里 `git commit -m "...引号..."` 会被吃掉** ⇒ 一律写消息文件 + `git commit -F`。

**4.11 测试依赖私有名**（`from contract.digest_registry import _split_tags`）—— 既有味道，归批次 9。

**4.12 逐字节不变只对"搬代码"有效**；改文案（1c）时它**必然红**，那时改用 promptkit 夹具 + 人工审 diff。

**4.13 别把 `Measure-Object -Line` 的行数当真** —— 它比 Python 的 `splitlines()` 少约 6%。
报行数用切分脚本的输出。
