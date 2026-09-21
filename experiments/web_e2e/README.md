# web 端到端测试（两层）

> 2026-09-11 建立。目的：**我（或任何改前端/路由的人）能自己把界面跑一遍**，
> 不必每次请你手点。

## 两层各管什么

| 层 | 位置 | 代价 | 能抓 | 抓不到 |
|---|---|---|---|---|
| **A. HTTP 级** | `tests/webgui/test_web_http.py`（pytest, 随全量跑） | ~1s, 零成本 | 路由注册/请求校验/状态码/响应头/静态挂载/JSON 契约/gallery 路径校验/设置往返 | JS 与 DOM 行为 |
| **B. 浏览器级** | `experiments/web_e2e/`（Playwright + 本机 Chrome/Edge） | ~15s, 零成本（桩 LLM） | 真实点击链路：登录 → 主界面 → MMT → 羁绊入口 → VN 首板/选项/裁决物化/收尾 → 回 MMT；console 错误与失败请求 | 真 LLM 的时序与内容质量 |

真 LLM 验收（真钱真延迟）仍走人工：`docs/EXEC_BOND_LATENCY.md`。

## A 层

```powershell
conda run -n live2be python -m pytest tests/webgui/test_web_http.py -q --basetemp=.testtmp/pw
```
- 走 `httpx.ASGITransport`（真实 app、真实路由、不开端口）；
- 桩 LLM + 临时 `SessionStore` 进程内注入（同 `tests/webgui/test_bond.py` 手法）；
- `settings.toml` / 玩家名文件 / 事件流 全部落到 tmp_path——**不碰真实 data/**。

## B 层（浏览器冒烟）

```powershell
conda run -n live2be python experiments/web_e2e/run.py            # 默认 Chrome, headless
conda run -n live2be python experiments/web_e2e/run.py --headed   # 看着它点（调试）
conda run -n live2be python experiments/web_e2e/run.py --edge     # 用 Edge
```

- **不需要下载浏览器**：用本机已装的 Chrome/Edge（`channel=chrome|msedge`）。
  Playwright 的 Node 包缺了就自动 `npm i` 到 `.testtmp`（`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`）。
- 桩世界（`stub_world.py`）：真 app + 桩 LLM（MMT 第一轮就回"邀约 + 触发羁绊"，
  bond 生成给记录流块）+ 临时世界线（`.testtmp/webtest/<时间戳>/data`）。
- 产物：`result.json`（每步 info、**逐段文字记录**、console 错误、失败请求、非 2xx）
  + `NN-*.png` 逐步截图 + 失败时的 `FAIL-*.png` 与 DOM 快照。

### 界面语义（写脚本/排查必读）

VN 是**点击推进制 + 逐段替换渲染**：同一时刻只显示一段，段末右下出现"继续三角"
（`#bond-continue.show`；**`.ready` = 整板读完**，点了就进下一板）；打字中按 `x`
补全当前段；**全部段读完**才进 `showInteraction`（选项 / 板读完 / `is_end` 自动 finish）。

**没有"▼ 继续"按钮**（2026-09-12 决策 #41 删除）：推进 = **点 `#bond-text`**。
`readUntilInteraction` 的"交互就绪"信号 = `.bond-choice` 或 `#bond-continue.ready`
（`INTERACTIVE` 常量）；`advanceBoard()` 负责"点画面推进到下一板"。

因此脚本里有四条约定的坑（都已在 `smoke.mjs` 处理好）：

1. **不点继续三角**：`.bond-continue` 带无限 bob 动画，Playwright 的"元素稳定"
   检查永不通过 → `click` 必然超时。改点 `#bond-text`（`onClick` 挂在 `#view-bond`
   上，点文字区等价于玩家点屏）。
2. **裁决后选项组当场收掉**（2026-09-21 用户裁决: *"第一次点击后直接推进即可，不要渲染
   第二次的那个黄色"*）——live 侧**直接推进、不再画只读黄灰组**, 所以别去等黄组出现
   （它不该出现; 只读态 + 高亮所选只剩**回放/续看**）。旧写法
   `waitForFunction(…every(resolved))` = 主动等它出现, 正是漏掉这个 bug 的原因。
3. **只读回放里选项可点**：点了只是本地推进（0 请求）, 高亮仍是当时选的那句。
4. **退出 VN 后等完成态气泡**：`已完成羁绊剧情：…` 由前端轮询拉到，别抢跑。

## 扩展建议

- A 层加用例最便宜：新路由/新字段 → 在 `test_web_http.py` 里加一条 HTTP 断言。
- B 层加场景：改 `stub_world.BOND_BLOCK`（多板/纪念/收尾组合）+ 在 `smoke.mjs`
  里加断言；界面流程变了（新按钮/新面板）优先补 B 层。
