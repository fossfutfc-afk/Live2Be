// Live2Be web E2E 浏览器冒烟（Playwright + 本机已装 Chrome/Edge, 不下载浏览器）
//
// 用法: node experiments/web_e2e/smoke.mjs <baseUrl> <artifactsDir> [--headed] [--edge]
//   → 逐步截图 + 全段文字记录 + console 错误/失败请求, 结论写 <artifactsDir>/result.json
//
// 覆盖: 登录页 → 主界面 → MMT 资料/对话 → 选角色 → 发一轮 → 羁绊入口粉泡 →
//       点入 VN → 首板（背景/名字行/选项）→ 裁决 → 就地物化「老师：X」→
//       继续 → 收尾板 → 自动 finish 回 MMT（输入框解锁 + 已完成行）
//
// 界面语义提醒（读这段能省一小时）: VN 是**点击推进制 + 逐段替换渲染**——
// 一次只显示一段, 段末出现右下"继续三角"（#bond-continue.show）等左键推进;
// 打字中按 x 可补全当前段; 全部段读完才进 showInteraction（选项 / "▼ 继续" /
// is_end 自动 finish）。所以脚本必须"读完整板"才能等到交互元素。
"use strict";

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

// ESM import 不认 NODE_PATH（那是 CJS 的解析规则）——用 createRequire 走 CJS 解析,
// 这样 run.py 传进来的 NODE_PATH（npx 缓存里的 playwright）就能被找到。
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const argv = process.argv.slice(2);
const flags = new Set(argv.filter((a) => a.startsWith("--")));
const [baseUrl, artDir] = argv.filter((a) => !a.startsWith("--"));
if (!baseUrl || !artDir) {
  console.error("用法: node smoke.mjs <baseUrl> <artifactsDir> [--headed] [--edge]");
  process.exit(2);
}
const headed = flags.has("--headed");
const channel = flags.has("--edge") ? "msedge" : "chrome";
fs.mkdirSync(artDir, { recursive: true });

const steps = [];
const consoleErrors = [];        // 真 JS 错误（pageerror / console.error 非资源加载）
const resourceConsole = [];      // "Failed to load resource" 类（由 badResponses 定责）
const benignNotices = [];        // 明确无害的噪音（如浏览器自动探测 /favicon.ico）
const failedRequests = [];
const badResponses = [];
const allowedNotices = [];       // 白名单内的非 2xx（如 /api/spine 404 = 无 spine 降级）
//: 允许的非 2xx: /api/spine 404 = 无 spine 资源 → 前端按纯文字降级（合法）
const ALLOWED_4XX = [/\/api\/spine\//];

const results = {
  url: baseUrl, ok: false, steps,
  consoleErrors, resourceConsole, failedRequests, badResponses, allowedNotices,
  benignNotices,
};

function record(name, detail = {}) {
  steps.push({ name, ...detail });
  console.log(`  [step] ${name}${detail.info ? " — " + detail.info : ""}`);
}

async function shot(page, name) {
  const file = path.join(artDir, `${String(steps.length).padStart(2, "0")}-${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return path.basename(file);
}

// ── VN 逐段阅读 ──────────────────────────────────────────────────────────
// 记录"玩家实际看到的每一段"（段内替换式渲染——同一时刻只有一段在屏上）
async function capturePara(page, seen) {
  const cur = await page.evaluate(() => {
    const box = document.getElementById("bond-text");
    if (!box) return null;
    const sp = box.querySelector(".bond-speaker");
    const para = box.querySelector(".bond-para");
    return { speaker: sp ? sp.textContent.trim() : "", text: para ? para.textContent.trim() : "" };
  });
  if (!cur || !cur.text) return;
  const norm = (s) => s.replace(/\s+/g, " ").trim();
  const now = { speaker: norm(cur.speaker), text: norm(cur.text) };
  const last = seen[seen.length - 1];
  if (!last || norm(last.text) !== now.text || last.speaker !== now.speaker) seen.push(now);
}

async function _tick(page) {
  // 推进一段: 点**文字区**（= 玩家点屏）。不点右下继续三角——它带无限 bob 动画
  // （`.bond-continue { animation: bond-continue-bob ... infinite }`）, Playwright 的
  // "元素稳定"检查永不通过 → click 必然超时; 而 onClick 挂在 #view-bond 上,
  // 点文字区同样走 advance()（打字中点屏本就是无操作, 与真人一致）。
  await page.locator("#bond-text")
    .click({ position: { x: 30, y: 20 }, timeout: 5000 })
    .catch(() => { /* 文字区被替换中 → 下一步再试 */ });
  await page.keyboard.press("x");    // 打字中 → 补全当前段（停段尾）
  await page.waitForTimeout(120);
}

/** 丢掉打字过程中的半截捕获（是后续某条的前缀）——只留"读完整"的段落。 */
function cleanTranscript(seen) {
  return seen.filter((p, i) => {
    for (let j = i + 1; j < seen.length; j++) {
      if (seen[j].text.startsWith(p.text) && seen[j].text.length > p.text.length) return false;
    }
    return true;
  });
}

/** 等交互区清空 = 上一板的选项/继续按钮已撤（新板开始渲染）。 */
async function waitInteractionReset(page, timeout = 40000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const n = await page.locator(
      "#bond-choices .bond-choice, #bond-choices .bond-continue-btn").count();
    if (n === 0) return;
    await page.waitForTimeout(100);
  }
  throw new Error("点击后交互区未清空（新板未开始渲染?）");
}

/** 读完整板直到出现交互元素（选项 / "▼ 继续"）或 VN 退出; 返回逐段记录。 */
async function readUntilInteraction(page, label, timeout = 90000) {
  const deadline = Date.now() + timeout;
  const seen = [];
  while (Date.now() < deadline) {
    await capturePara(page, seen);
    const interactive = await page.locator(
      "#bond-choices .bond-choice, #bond-choices .bond-continue-btn").count();
    if (interactive) return cleanTranscript(seen);
    if (await page.locator("#view-bond.hidden").count()) return cleanTranscript(seen);
    await _tick(page);
  }
  throw new Error(`等待交互超时（${label}）`);
}

/** 一直推进到 VN 退出（is_end 自动 finish）; 返回逐段记录。 */
async function readToEnd(page, timeout = 90000) {
  const deadline = Date.now() + timeout;
  const seen = [];
  while (Date.now() < deadline) {
    if (await page.locator("#view-bond.hidden").count()) return cleanTranscript(seen);
    await capturePara(page, seen);
    await _tick(page);
  }
  throw new Error("收尾超时: VN 未回到 MMT");
}

async function main() {
  const browser = await chromium.launch({ channel, headless: !headed });
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  globalThis.__page = page;                 // 失败现场留档用（见 catch）

  page.on("console", (m) => {
    if (m.type() !== "error") return;
    const loc = m.location() || {};
    const t = `${m.text().slice(0, 300)} @ ${loc.url || "?"}:${loc.lineNumber ?? "?"}`;
    if (t.includes("favicon.ico")) { benignNotices.push(t); return; }  // 浏览器自动探测, 无害
    (t.includes("Failed to load resource") ? resourceConsole : consoleErrors).push(t);
  });
  page.on("pageerror", (e) => consoleErrors.push("pageerror: " + String(e).slice(0, 400)));
  page.on("requestfailed", (r) => {
    const f = r.failure();
    failedRequests.push(`${r.method()} ${r.url()} — ${f ? f.errorText : "?"}`);
  });
  page.on("response", (r) => {
    if (r.status() < 400) return;
    const line = `${r.status()} ${r.request().method()} ${r.url()}`;
    console.log(`  [http>=400] ${line}`);        // 立刻打出来: 能对上当时的步骤
    if (ALLOWED_4XX.some((re) => re.test(r.url()))) { allowedNotices.push(line); return; }
    badResponses.push(line);
  });

  // ── 1. 登录页 ─────────────────────────────────────────────────────────
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#view-login:not(.hidden)", { timeout: 15000 });
  await page.fill("#input-name", "老师");
  await page.click("#btn-ok");
  await page.waitForSelector("#btn-enter:not(.hidden)", { timeout: 15000 });
  record("登录页", { info: "保存名字 → 进入按钮出现", shot: await shot(page, "login") });

  // ── 2. 主界面 ─────────────────────────────────────────────────────────
  await page.click("#btn-enter");
  await page.waitForSelector("#view-main:not(.hidden)", { timeout: 10000 });
  record("主界面", { shot: await shot(page, "main") });

  // ── 3. MMT 资料模式（成员列表真加载 /api/mmt/characters）──────────────
  await page.click("#btn-mmt");
  await page.waitForSelector("#view-mmt:not(.hidden)", { timeout: 10000 });
  await page.waitForSelector("#mmt-profile-list [data-id]", { timeout: 20000 });
  const profileCount = await page.locator("#mmt-profile-list [data-id]").count();
  if (profileCount < 1) throw new Error("资料模式成员列表为空（mmt_registry / 头像缺）");
  record("MMT 资料模式", { info: `${profileCount} 个成员`, shot: await shot(page, "mmt-profile") });

  // ── 4. 对话模式 → 选角色 → 发一轮 → 羁绊入口粉泡 ─────────────────────
  await page.click('.mode-btn[data-mode="chat"]');
  await page.waitForSelector("#mmt-chat-list [data-id]", { timeout: 20000 });
  await page.click('#mmt-chat-list [data-id="igusa_haruka"]');
  await page.waitForSelector("#mmt-input", { timeout: 15000 });
  await page.fill("#mmt-input", "在吗？");
  await page.click("#mmt-send");
  await page.waitForSelector(".bond-entry", { timeout: 30000 });
  record("MMT 一轮 + 羁绊入口", {
    info: "桩 LLM 回邀约 → 入口粉泡出现",
    shot: await shot(page, "mmt-bond-entry"),
  });

  // ── 5. 点入口 → 章节标题屏 → VN 首板 ─────────────────────────────────
  await page.click(".bond-entry");
  await page.waitForSelector("#view-bond:not(.hidden)", { timeout: 25000 });
  // 章节标题屏（~2.4s 自动过 / 点击跳过）: 文案必须是**章节名**而不是兜底的"羁绊剧情"
  // （2026-09-11 真机报障: adopt 就绪路径漏带 chapter_title → 标题屏显示四个大字）
  const titlePanel = await page.evaluate(async () => {
    for (let i = 0; i < 80; i++) {
      const t = document.getElementById("bond-title");
      const txt = document.getElementById("bond-title-text");
      if (t && !t.classList.contains("hidden") && txt && txt.textContent.trim()) {
        return txt.textContent.trim();
      }
      await new Promise((r) => setTimeout(r, 50));
    }
    return "";
  });
  await page.waitForFunction(
    () => {
      const t = document.getElementById("bond-text");
      return t && t.innerText.trim().length > 4;
    }, { timeout: 40000 });
  const board1 = await readUntilInteraction(page, "VN 首板选项");
  const choices = await page.locator("#bond-choices .bond-choice").allInnerTexts();
  const bg = await page.evaluate(() =>
    (document.getElementById("bond-bg").style.backgroundImage || ""));
  const stage = await page.evaluate(() => {
    const s = document.getElementById("bond-stage");
    return { hidden: s.classList.contains("hidden"), children: s.children.length };
  });
  // 名字牌（随当前角色变动的两个字段）: 名字 + 社团
  const nameplate = await page.evaluate(() => ({
    name: (document.getElementById("bond-name") || {}).textContent || "",
    club: (document.getElementById("bond-club") || {}).textContent || "",
  }));
  record("VN 首板", {
    info: `标题屏=${JSON.stringify(titlePanel)} 名字牌=${nameplate.name}/${nameplate.club} `
      + `段落=${board1.length} 选项=${JSON.stringify(choices)} 背景=${bg ? "有" : "无"}`,
    shot: await shot(page, "vn-board1"),
    chapterTitlePanel: titlePanel, nameplate,
    transcript: board1, choices, background: bg.slice(0, 160), stage,
  });
  if (!titlePanel || titlePanel === "羁绊剧情") {
    throw new Error(`标题屏没拿到章节名（得到 ${JSON.stringify(titlePanel)}）`);
  }
  if (!titlePanel.includes("放学后的约定")) {
    throw new Error(`标题屏文案不是章节名: ${JSON.stringify(titlePanel)}`);
  }
  if (!nameplate.name.trim() || !nameplate.club.trim()) {
    throw new Error(`名字牌缺名字/社团: ${JSON.stringify(nameplate)}`);
  }
  // 当前角色自己说话时**不画**红字名字行（名字牌已表明是谁）——2026-09-11 用户反馈
  const onStageNames = board1.filter((p) => p.speaker).map((p) => p.speaker);
  if (onStageNames.length) {
    throw new Error(`角色段落仍画了重复名字行: ${JSON.stringify(onStageNames)}`);
  }
  if (choices.length < 1) throw new Error("首板没有选项（记录流板切分异常?）");

  // ── 5.5 纪念链路（v2, 2026-09-12）: in_memorial → 立绘隐藏 + 背景清空 + 图淡入 ──
  // 桩块在首板里放了 `stage:memorial`, 生图走替身（离线 1×1 PNG）——验证的是
  // **整条接线**: 引擎 art/memorial → 生图回调 → gallery URL → bond_status →
  // 前端纪念层。旧版这条线在 v2 是断的（v1 探针只认 action=memorial_enter）。
  {
    // 等图就绪（替身是毫秒级, 但状态要过一轮轮询）
    let memOk = null;
    for (let i = 0; i < 60; i++) {
      memOk = await page.evaluate(() => {
        const layer = document.getElementById("bond-memorial");
        const stage = document.getElementById("bond-stage");
        const bg = document.getElementById("bond-bg");
        return {
          layerOn: !!(layer && layer.classList.contains("on")),
          layerImg: (layer && layer.style.backgroundImage) || "",
          stageHidden: !!(stage && stage.classList.contains("hidden")),
          bgCleared: !(bg && bg.style.backgroundImage),
        };
      });
      if (memOk.layerOn && memOk.layerImg) break;
      await new Promise((r) => setTimeout(r, 100));
    }
    record("纪念链路", {
      info: `图=${memOk.layerImg ? "已淡入" : "未就绪"} 立绘隐藏=${memOk.stageHidden} `
        + `普通背景清空=${memOk.bgCleared}`,
      shot: await shot(page, "vn-memorial"),
      memorial: memOk,
    });
    if (!memOk.layerImg) throw new Error(`纪念图未淡入（生图链断?）: ${JSON.stringify(memOk)}`);
    if (!memOk.stageHidden) throw new Error(`纪念期间立绘未隐藏: ${JSON.stringify(memOk)}`);
    if (!memOk.bgCleared) throw new Error(`纪念期间普通背景未清空: ${JSON.stringify(memOk)}`);
  }

  // ── 6. 裁决 → 玩家那句话**不上屏**（只消失选项, 正文停在上一句）──────────
  // 语义定稿（2026-09-12, 用户核对 BA）: **玩家的话语永远只体现为选项**——
  // 裁决后正文保持"上一句角色台词/旁白", 名字牌/立绘都不动; 把玩家那句当正文念
  // 出来就会被读成"角色说了玩家的话"（真机报障: 睦月/便利屋68 + 你还打算对我怎么恶作剧？）。
  // 注: 点击后**必须先等交互区清空**——旧板的选项按钮会停留到响应到达为止,
  // 直接开读会立刻"发现"旧选项并误判为读完了。
  const lastLineBefore = board1[board1.length - 1].text;
  await page.locator("#bond-choices .bond-choice").first().click();
  await waitInteractionReset(page);
  const afterPick = await readUntilInteraction(page, "裁决后（选项消失, 正文不动）");
  const leaked = afterPick.filter((p) => p.text.includes("我来了"));
  record("裁决不上屏", {
    info: leaked.length
      ? `❌ 玩家那句被当正文渲染: ${JSON.stringify(leaked.map((p) => p.text))}`
      : `正文保持上一句=${JSON.stringify(afterPick.map((p) => p.text.slice(0, 20)))}`,
    shot: await shot(page, "vn-after-pick"),
    transcript: afterPick,
  });
  if (leaked.length) {
    throw new Error(`裁决后玩家那句被当正文渲染（应只体现为选项）: ${JSON.stringify(leaked)}`);
  }
  // 正文停在上一句角色台词/旁白: 整屏只有那一段, 不许重播板正文
  if (afterPick.length !== 1 || afterPick[0].text !== lastLineBefore) {
    throw new Error(`裁决后正文应保持上一句（期望 1 段 ${JSON.stringify(lastLineBefore)}）`
      + `: ${JSON.stringify(afterPick)}`);
  }
  const strayLabels = afterPick.filter((p) => p.speaker).map((p) => p.speaker);
  if (strayLabels.length) {
    throw new Error(`裁决节点仍画了名字行（应无）: ${JSON.stringify(strayLabels)}`);
  }
  // 名字牌必须仍是角色（用户核对 BA: "名字什么的都不用变"）
  const plateAfterPick = await page.evaluate(() => {
    const np = document.querySelector(".bond-nameplate");
    return {
      name: (document.querySelector("#bond-name") || {}).textContent || "",
      club: (document.querySelector("#bond-club") || {}).textContent || "",
      hidden: !!(np && np.classList.contains("hidden")),
    };
  });
  if (plateAfterPick.hidden || !plateAfterPick.name.trim()) {
    throw new Error(`裁决后名字牌不该变（BA: 名字不用变）: ${JSON.stringify(plateAfterPick)}`);
  }

  // ── 6.5 中途退出重进 → 回放里"选项态"必须看得见（2026-09-12 用户要求）────
  // 场景: 玩家选了选项后关掉页面（硬退出, 事件流里那条 bond 场景已带 picked）→
  // 重进 → 回放该场。此时正文仍不许出现玩家那句（决策 #37）, 但**选项组要画出来**
  // 并高亮所选——否则"选哪个选项看起来都一样"（用户反馈）。
  {
    // 先丢掉进程内状态（桩世界钩子）——**模拟服务端重启**: 浏览器刷新时服务端
    // 内存态还在的话, 重进走的是"就地续玩"（选项已被裁决清空, 不该再给）;
    // 只有内存态没了, 才走事件流**回放**, 那里才需要把选项组画出来。
    const dropped = await page.evaluate(async (base) => {
      const r = await fetch(`${base}/__e2e/drop_bond_state`, { method: "POST" });
      return r.ok ? await r.json() : { dropped: -1 };
    }, baseUrl);
    await page.reload({ waitUntil: "domcontentloaded" });
    // 重载后回到登录确认屏（名字已存）→ 再进主界面（与步骤 1/2 同路径）
    await page.waitForSelector("#view-login:not(.hidden)", { timeout: 30000 });
    await page.click("#btn-ok");
    await page.waitForSelector("#btn-enter:not(.hidden)", { timeout: 15000 });
    await page.click("#btn-enter");
    await page.waitForSelector("#view-main:not(.hidden)", { timeout: 15000 });
    await page.click("#btn-mmt");
    await page.waitForSelector("#view-mmt:not(.hidden)", { timeout: 15000 });
    await page.click('.mode-btn[data-mode="chat"]');
    await page.waitForSelector("#mmt-chat-list [data-id]", { timeout: 20000 });
    await page.click('#mmt-chat-list [data-id="igusa_haruka"]');
    // 在押章节: 历史重建的粉泡（bond_entry）或下方兜底入口条 —— 点它续进回放
    await page.waitForSelector(".bond-entry", { timeout: 30000 });
    await page.click(".bond-entry");
    await page.waitForSelector("#view-bond:not(.hidden)", { timeout: 25000 });
    await page.waitForFunction(
      () => {
        const t = document.getElementById("bond-text");
        return t && t.innerText.trim().length > 2;
      }, { timeout: 40000 });
    const replayParas = await readUntilInteraction(page, "重进回放（选项态）");
    const locked = await page.evaluate(() => {
      const all = [...document.querySelectorAll("#bond-choices .bond-choice")];
      return {
        total: all.length,
        resolved: all.filter((b) => b.classList.contains("resolved")).length,
        pickedText: (all.find((b) => b.classList.contains("picked")) || {}).textContent || "",
        disabled: all.filter((b) => b.disabled).length,
      };
    });
    record("重进回放·选项态", {
      info: `${JSON.stringify(dropped)} 正文=${JSON.stringify(replayParas.map((p) => p.text.slice(0, 16)))} `
        + `选项=${locked.total} 锁定=${locked.resolved} 禁用=${locked.disabled} `
        + `所选=${JSON.stringify(locked.pickedText)}`,
      shot: await shot(page, "vn-replay-choices"),
      transcript: replayParas, locked,
    });
    if (replayParas.some((p) => p.text.includes("我来了"))) {
      throw new Error(`重进回放仍把玩家那句当正文: ${JSON.stringify(replayParas)}`);
    }
    if (!locked.total || locked.resolved !== locked.total) {
      throw new Error(`重进回放的选项组没画成锁定态: ${JSON.stringify(locked)}`);
    }
    if (locked.pickedText.trim() !== "我来了。") {
      throw new Error(`重进回放没高亮所选: ${JSON.stringify(locked)}`);
    }
    // 回放的**纪念板**同样要进纪念态（立绘隐藏 + 普通背景清空; 图属档案保真,
    // 见"回放不带 gallery URL"的已知缺口——这里只断言状态驱动的两项）
    const replayMem = await page.evaluate(() => {
      const stage = document.getElementById("bond-stage");
      const bg = document.getElementById("bond-bg");
      return {
        stageHidden: !!(stage && stage.classList.contains("hidden")),
        bgCleared: !(bg && bg.style.backgroundImage),
      };
    });
    if (!replayMem.stageHidden || !replayMem.bgCleared) {
      throw new Error(`回放的纪念板未进纪念态: ${JSON.stringify(replayMem)}`);
    }
    // 注: 这里**不推进** —— 交给步骤 7 的"▼ 继续"从回放交棒到后续板。
  }

  // ── 7. 继续 → 收尾板 → 自动 finish 回 MMT ────────────────────────────
  await page.click("#bond-choices .bond-continue-btn");
  await waitInteractionReset(page);
  const ending = await readToEnd(page);
  // **收尾板多段必须逐段读完**（2026-09-11 真机 bug: is_end 板点一下就直接 finish,
  // "最后一段只看到第一句就退出 VN"）。桩块的收尾板有 4 段（收尾一/二/三 + 反应板）。
  const wantEnd = ["收尾一", "收尾二", "收尾三"];
  const missing = wantEnd.filter((k) => !ending.some((p) => p.text.includes(k)));
  if (missing.length) {
    throw new Error(`收尾板段落没读完（is_end 提前 finish?）缺: ${JSON.stringify(missing)}`
      + ` 实际: ${JSON.stringify(ending.map((p) => p.text.slice(0, 16)))}`);
  }
  const endLabels = ending.filter((p) => p.speaker).map((p) => p.speaker);
  if (endLabels.length) {
    throw new Error(`收尾节点仍画了名字行（应无）: ${JSON.stringify(endLabels)}`);
  }
  await page.waitForSelector("#mmt-input:not([disabled])", { timeout: 25000 });
  // 退出 VN 后前端重启轮询拉完成态气泡 → 等"已完成羁绊剧情"行出现（别抢跑）
  await page.waitForFunction(
    () => {
      const w = document.getElementById("mmt-chat-window");
      return w && w.innerText.includes("已完成羁绊剧情");
    }, { timeout: 25000 }).catch(() => { /* 下面统一判断 + 留证 */ });
  const finalTexts = await page.locator("#mmt-chat-window").innerText();
  const done = finalTexts.includes("已完成羁绊剧情");
  record("收尾回 MMT", {
    info: `${ending.length} 段收尾; ${done ? "出现『已完成羁绊剧情』行" : "未见完成行"}`,
    shot: await shot(page, "mmt-after-finish"),
    transcript: ending, done,
  });
  if (!done) throw new Error("收尾后 MMT 未见『已完成羁绊剧情』行: "
    + finalTexts.slice(0, 200).replace(/\n/g, " / "));

  // ── 8. 收尾话必须**不用切页**就逐条冒出来（2026-09-11 真机 bug）──────────
  // 根因: wrapup 跑在 bond 自己的线程里, 不占 MMT 任务位 → 前端 pollLoop 第一轮
  // 就看见 running=false 而停止轮询 → 气泡要切页/重进才被 since=0 全量拉出来。
  // 判定: 就在当前页面等收尾话气泡出现（不点击、不切换视图）。
  await page.waitForFunction(
    () => {
      const w = document.getElementById("mmt-chat-window");
      // 注: 桩回复文本是"（收尾话）老师，今天真的很谢谢你。"——括号内心声会被引擎
      // 剥掉, 所以断言用后半句
      return w && w.innerText.includes("今天真的很谢谢你");
    }, { timeout: 30000 }).catch(() => { /* 下面统一判定 */ });
  const afterWrapup = await page.locator("#mmt-chat-window").innerText();
  const wrapupShown = afterWrapup.includes("今天真的很谢谢你");
  record("收尾话自动冒泡", {
    info: wrapupShown ? "未切页即出现（轮询保持）" : "未出现（要切页才看得到）",
    shot: await shot(page, "mmt-wrapup"),
    wrapupShown,
  });
  if (!wrapupShown) {
    throw new Error("收尾话未自动冒泡（前端轮询过早停止）: "
      + afterWrapup.slice(0, 200).replace(/\n/g, " / "));
  }
  // 收尾话到了之后**不该再显示"对方正在输入…"**（2026-09-12 真机报障: 话已经
  // 全部显示完了, 三个点还在跳, 半分钟后静默消失——旧逻辑在 25s 宽限窗口里
  // 无条件 showTyping）。观察 3.5s: **期间任何一次出现**都算残留（轮询 1s 一次,
  // 只看"当下有没有"会错过它下一拍又冒出来）。
  let typingSeen = false;
  for (let i = 0; i < 35; i++) {
    typingSeen = await page.evaluate(() => !!document.getElementById("mmt-typing"));
    if (typingSeen) break;
    await new Promise((r) => setTimeout(r, 100));
  }
  record("收尾后打字指示", {
    info: typingSeen ? "❌ 收尾话已到, 三个点仍在跳" : "收尾话落地即消失（观察 3.5s）",
  });
  if (typingSeen) {
    throw new Error("收尾话已显示完, 打字指示（mmt-typing）仍残留 —— 宽限窗口谎报");
  }

  await browser.close();

  results.ok = consoleErrors.length === 0 && failedRequests.length === 0
    && badResponses.length === 0;
  fs.writeFileSync(path.join(artDir, "result.json"),
    JSON.stringify(results, null, 2), "utf8");
  console.log(`  [console] js errors=${consoleErrors.length} `
    + `resource-noise=${resourceConsole.length} failed=${failedRequests.length} `
    + `badResponses=${badResponses.length} benign=${benignNotices.length}`);
  return results.ok ? 0 : 1;
}

main()
  .then((code) => process.exit(code))
  .catch(async (e) => {
    results.error = String(e && e.stack ? e.stack.split("\n")[0] : e);
    try {
      // 失败现场留档: 截图 + 关键 DOM 快照（交互区/文字区/视图可见性）
      const page = globalThis.__page;
      if (page) {
        const f = path.join(artDir, `FAIL-${steps.length}.png`);
        await page.screenshot({ path: f }).catch(() => {});
        results.failShot = path.basename(f);
        results.failDom = await page.evaluate(() => {
          const vis = (id) => {
            const el = document.getElementById(id);
            return el ? !el.classList.contains("hidden") : null;
          };
          const box = document.getElementById("bond-choices");
          return {
            view_bond: vis("view-bond"), view_mmt: vis("view-mmt"),
            choices_html: box ? box.innerHTML.slice(0, 600) : null,
            choice_count: box ? box.querySelectorAll(".bond-choice").length : null,
            continue_count: box ? box.querySelectorAll(".bond-continue-btn").length : 0,
            text: (document.getElementById("bond-text") || {}).innerText || "",
            tri_shown: !!document.querySelector("#bond-continue.show"),
          };
        }).catch(() => null);
      }
    } catch { /* 尽力而为 */ }
    try {
      fs.writeFileSync(path.join(artDir, "result.json"),
        JSON.stringify(results, null, 2), "utf8");
    } catch { /* 写不了就算了 */ }
    console.error("  [FAIL] " + results.error);
    process.exit(1);
  });
