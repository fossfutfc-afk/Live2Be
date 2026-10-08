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
const bondWrites = [];            // 回忆册只读回放期间不该出现的 bond 写请求
//: `/api/bond/turn` **直返场景**的响应体（预生成领出 / 分支消费）。
//: 为什么要盯它: "章中途的纪念板"只走这条路，而前端曾在这条路上漏 `syncMemorial`
//: ⇒ 纪念板照常显示立绘 + 普通背景（2026-09-26 真机报障）。轮询那条路一直是对的，
//: 所以**只断言纪念视觉**抓不到这个 bug —— 必须同时断言"这一板是 /turn 直返的"。
const turnSceneDeliveries = [];
//: ⑥-3b: MMT 会话 id（从 `/api/mmt/session` 响应里抓）——"第一个气泡早于整轮完成"
//: 的判据要**直接问后端** `running`（与前端轮询同一个接口、同一个字段）。
let mmtSessionId = "";
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
    // ★ 段级纪念态（2026-09-20 M3）: 记录**这一段上屏那一刻**的视觉——
    //   记录级进入点要求"触发记录之前那几条是正常视觉"（立绘在、背景在），
    //   只有事后逐段取样才断得出来（板读完再断已经晚了）。
    const layer = document.getElementById("bond-memorial");
    const stage = document.getElementById("bond-stage");
    const bg = document.getElementById("bond-bg");
    return {
      speaker: sp ? sp.textContent.trim() : "",
      text: para ? para.textContent.trim() : "",
      memorial: !!(layer && layer.classList.contains("on")),
      stageHidden: !!(stage && stage.classList.contains("hidden")),
      bgCleared: !(bg && bg.style.backgroundImage),
    };
  });
  if (!cur || !cur.text) return;
  const norm = (s) => s.replace(/\s+/g, " ").trim();
  const now = {
    speaker: norm(cur.speaker), text: norm(cur.text),
    memorial: cur.memorial, stageHidden: cur.stageHidden, bgCleared: cur.bgCleared,
  };
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

/** 交互就绪选择器（**决策 #41**: "▼ 继续"按钮已删——板读完的信号 = 右下三角带
 *  `.ready`, 板内"还有下一段"的三角不带它, 所以能区分"板读完"与"板内推进"）。 */
const INTERACTIVE = "#bond-choices .bond-choice, #bond-continue.ready";

/** ⑥-3b 流式判据: 盯住一轮 MMT 的**上屏时间线**（每 ~40ms 一次, 在页面内跑）。

 *  为什么要盯: 前端 ⑥-3b 起"到达即渲染"、后端 ⑥-3a 起"行一到就交付"——若哪一端
 *  退回批式, 气泡会**一次性**出现（旧行为: 整轮收完 / 1s 轮询攒成一批）, 而那
 *  在肉眼与旧断言里都完全看不出问题。
 *  判据 = 第一个气泡上屏那一刻, **后端还在跑这一轮**（直接问 `/api/mmt/events`
 *  的 `running`, 与前端同一个字段——不是推断）。整轮的最后一行是触发行,
 *  它的粉泡（`.bond-entry`）出现即"整轮办完"。
 */
/** ⑥-3b: 直接问后端"这一轮还在跑吗"（与前端轮询同一个接口/同一个字段）。
 *  拿不到会话 id 或请求失败 → null（判据据此**不算谎报**, 宁缺勿错）。 */
async function runningNow(page) {
  if (!mmtSessionId) return null;
  return await page.evaluate(async (sid) => {
    try {
      const r = await fetch(`/api/mmt/events?char_id=igusa_haruka&session_id=${sid}&since=999999`);
      return (await r.json()).running;
    } catch (e) { return null; }
  }, mmtSessionId);
}

async function watchMmtStream(page, sessionId, charId, timeoutMs = 10000) {  return await page.evaluate(async ({ limit, sid, cid }) => {
    const t0 = performance.now();
    const samples = [];
    while (performance.now() - t0 < limit) {
      const w = document.getElementById("mmt-chat-window");
      const chars = w ? w.querySelectorAll(".mmt-bubble.char:not(.typing)").length : 0;
      const entry = !!document.querySelector(".bond-entry");
      const s = { t: Math.round(performance.now() - t0), chars, entry, running: null };
      if (chars >= 1 && sid) {
        try {
          const r = await fetch(`/api/mmt/events?char_id=${cid}&session_id=${sid}&since=999999`);
          s.running = (await r.json()).running;
        } catch (e) { /* 读不到就不算数（判据会因此判失败, 正是我们要的） */ }
      }
      samples.push(s);
      if (entry) break;                       // 粉泡 = 最后一行办完 → 整轮结束
      await new Promise((r) => setTimeout(r, 40));
    }
    return samples;
  }, { limit: timeoutMs, sid: sessionId, cid: charId });
}

/** 等交互区清空 = 上一板的选项/板读完态已撤（新板开始渲染）。 */
async function waitInteractionReset(page, timeout = 40000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await page.locator(INTERACTIVE).count() === 0) return;
    await page.waitForTimeout(100);
  }
  throw new Error("点击后交互区未清空（新板未开始渲染?）");
}

/** 点画面推进到下一板（**决策 #41**: 没有"▼ 继续"按钮了——板读完点画面即下一板）。 */
async function advanceBoard(page, timeout = 40000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await page.locator(INTERACTIVE).count() === 0) return;   // 已进下一板
    await page.locator("#bond-text")
      .click({ position: { x: 30, y: 20 }, timeout: 5000 })
      .catch(() => { /* 文字区正在替换 → 下一轮再试 */ });
    await page.waitForTimeout(150);
  }
  throw new Error("点画面推进失败: 交互区一直没清空（板没进下一板?）");
}

/** 读完整板直到出现交互元素（选项 / 板读完三角）或 VN 退出; 返回逐段记录。 */
async function readUntilInteraction(page, label, timeout = 90000) {
  const deadline = Date.now() + timeout;
  const seen = [];
  while (Date.now() < deadline) {
    await capturePara(page, seen);
    if (await page.locator(INTERACTIVE).count()) return cleanTranscript(seen);
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
  // 只读回放契约: 回忆册里播章**不许**出现任何 bond 写请求（turn/finish/start）
  page.on("request", (r) => {
    if (r.method() !== "POST") return;
    if (/\/api\/bond\/(turn|finish|start)/.test(r.url())) {
      bondWrites.push(`${r.method()} ${r.url()}`);
    }
  });
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
  // `/api/bond/turn` 直返场景留痕（纪念修复的判据路径, 见 `turnSceneDeliveries` 注释）
  page.on("response", async (r) => {
    if (r.request().method() !== "POST" || !/\/api\/bond\/turn/.test(r.url())) return;
    try {
      const body = await r.text();
      if (body.includes('"scene"')) turnSceneDeliveries.push(body.slice(0, 160));
    } catch (e) { /* body 读不到（中断/重定向）→ 跳过 */ }
  });
  // MMT 会话 id 留痕（⑥-3b 的流式判据要拿它直读 `running`）
  page.on("response", async (r) => {
    if (!/\/api\/mmt\/session/.test(r.url()) || r.status() >= 400) return;
    try { mmtSessionId = (await r.json()).session_id || mmtSessionId; } catch (e) { /* 忽略 */ }
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

  // ── 4b. ⑥-3b: 气泡**逐条**上屏（第一个气泡早于整轮完成）─────────────────
  // 桩的 MMT 回复 4 行、行间 0.3s（`MMT_STREAM_GAP_S`）; 批式实现下 4 条会挤在
  // 同一次轮询里出现（`firstBubble.running` 也会是 false）。
  const stream = await watchMmtStream(page, mmtSessionId, "igusa_haruka", 20000);
  const firstBubble = stream.find((s) => s.chars >= 1) || null;
  const last = stream[stream.length - 1] || {};
  const leadMs = firstBubble && last.entry ? last.t - firstBubble.t : -1;
  record("MMT 流式交付", {
    info: firstBubble
      ? `首泡 t=${firstBubble.t}ms（当时 running=${firstBubble.running}, ${firstBubble.chars} 条）`
        + `; 整轮 t=${last.t}ms（${last.chars} 条）; 提前 ${leadMs}ms`
      : "❌ 没看到任何角色气泡",
    streamed: !!firstBubble && firstBubble.running === true,
    leadMs, samples: stream.length,
  });
  if (!firstBubble) throw new Error("MMT 一轮没有任何角色气泡上屏");
  if (firstBubble.running !== true) {
    throw new Error(
      `第一个气泡上屏时这一轮**已经跑完**（running=${firstBubble.running}）——`
      + `流式交付退回了批式: ${JSON.stringify(stream.slice(0, 6))}`);
  }
  if (firstBubble.entry) {
    throw new Error("第一个气泡与触发粉泡同一刻出现（整轮一次性落地）");
  }
  if (leadMs < 250) {
    throw new Error(`首泡与整轮结束只差 ${leadMs}ms（前端 250ms 轮询都吃不满, 像批式）`);
  }

  // ── 4c. 节奏: 同一批里的角色气泡必须**逐条**上屏（不许同帧）──────────────
  // 桩按 `MMT_ROW_GAPS_S` 吐行: 前几行**突发**（= 真机形态: 她一口气写完几条,
  // 一次轮询抓好几条）, 只在触发行之前留间隔 ⇒ 于是这里量得出"批内节奏"。
  // ⚠️ 判据取**前两条**之间的间隔, 不取"第 1 条 → 最后 1 条": 引擎是**一行前瞻**
  //    交付（下一行到达才上屏最后一条内容行）⇒ 最后一条天然被那个 0.9s 行间推迟,
  //    混进判据里会把"同帧上屏"伪装成 855ms（2026-10-08 变异验红时踩到: 守门抓不住）。
  //    前两条则确实落在**同一批**（同一次轮询抓到）⇒ 干净。
  //   · 有节奏（`chunkTypingMs` 逐条"打完再发"）⇒ 第 2 条要等她"打完第 2 条"（~1.5s）
  //   · 没节奏（那个 bug: 整批 `at` 恒 0 ⇒ 全走同帧那支）⇒ 两条同一帧 ⇒ ~0ms
  // ⚠️ 别拿粉泡量: 它是**非角色**气泡、不推进队列 ⇒ 必然紧跟前一条（恒 0ms, 假红）。
  const maxChars = stream.reduce((m, s) => Math.max(m, s.chars || 0), 0);
  const t1 = firstBubble ? firstBubble.t : null;
  const two = stream.find((s) => (s.chars || 0) >= 2) || null;
  const gapMs = (t1 != null && two) ? two.t - t1 : -1;
  const lastChar = stream.find((s) => (s.chars || 0) === maxChars) || null;
  record("MMT 气泡节奏（批内逐条）", {
    info: `第 1 条 t=${t1}ms → 第 2 条 t=${two ? two.t : "-"}ms; 间隔 ${gapMs}ms`
      + `（共 ${maxChars} 条, 第 1→最后 ${lastChar && t1 != null ? lastChar.t - t1 : "-"}ms）`
      + `（有节奏 ⇒ ~1.5s; 同帧上屏 ⇒ ~0ms）`,
    gapMs, maxChars,
  });
  if (maxChars >= 2 && gapMs < 800) {
    throw new Error(
      `**整批气泡同帧上屏**（前两条只隔 ${gapMs}ms）——`
      + "前端\"打完再发\"的节奏失效了（查 mmt.js 里 firstOfBatch && base === 0 那个判据）");
  }

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

  // ── 5b. 板级背景: **晚到的地点必须补切**（2026-10-08 报障"永远是默认教室兜底"）──
  await page.evaluate(({ cid, sid }) => {          // 给下面那段诊断用（status 直询）
    window.__bgChar = cid; window.__bgSid = sid;
  }, { cid: "igusa_haruka", sid: mmtSessionId });
  // 首板经 `/api/bond/start` **直返快照**进场（那一刻 place 还没解析出来）⇒ `_resolve_scene`
  // 走兜底 `_BG_FALLBACK_PRIORITY[0] = class_room`（教室）; place lane ~0.5s 后把地点写回
  // `state.scene`（`lanes.py:299`）⇒ **前端必须自己补切**（`bond.js::syncBoardBg`, 挂在
  // 阅读期守望 `startEmoWatch` 上）——此前 fixture/指纹都不管背景, 于是永远是教室。
  // ⛔ 判据依赖"桩的 switch 文本 ≠ 教室": 咖啡馆那张（BG_ModernCafe.jpg）与兜底教室
  //    （BG_ClassRoom.jpg）必须**不同图**, 否则分不清"地点生效"还是"掉兜底"。
  const bgLate = await page.evaluate(async () => {
    const el = document.getElementById("bond-bg");
    const first = (el && el.style.backgroundImage) || "";
    // 诊断: 直接问一次 status —— 分清"后端没给"与"前端没应用"（差一个人就是一条线索）
    let probe = {};
    try {
      const r = await fetch(
        `/api/bond/status?char_id=${window.__bgChar}&session_id=${window.__bgSid}`);
      const st = await r.json();
      const s = st.scene || {};
      probe = { place: s.place, inherited: s.place_inherited,
                bg: (s.background_url || "").slice(-44), gate: st.gate_busy,
                round: st.round, ver: st.emo_version };
    } catch (e) { probe = { err: String(e) }; }
    for (let i = 0; i < 120; i++) {                       // ≤ 6s
      const cur = (el && el.style.backgroundImage) || "";
      if (cur.includes("BG_ModernCafe")) return { ok: true, first, final: cur, probe };
      await new Promise((r) => setTimeout(r, 50));
    }
    return { ok: false, first, final: (el && el.style.backgroundImage) || "", probe };
  });
  record("板级背景（晚到的地点补切）", {
    info: `首次读=${bgLate.first.slice(-44) || "无"} → 最终=${bgLate.final.slice(-44) || "无"}`
      + `; status: ${JSON.stringify(bgLate.probe)}`,
    ok: bgLate.ok,
    shot: await shot(page, "vn-bg-late"),
  });
  if (!bgLate.ok) {
    throw new Error(
      `板级背景没补切到咖啡馆（最终 ${bgLate.final || "空"}）——`
      + "晚到的 place 没被应用到屏上（查 bond.js 的 syncBoardBg / startEmoWatch）");
  }
  // 当前角色自己说话时**不画**红字名字行（名字牌已表明是谁）——2026-09-11 用户反馈
  const onStageNames = board1.filter((p) => p.speaker).map((p) => p.speaker);
  if (onStageNames.length) {
    throw new Error(`角色段落仍画了重复名字行: ${JSON.stringify(onStageNames)}`);
  }
  if (choices.length < 1) throw new Error("首板没有选项（记录流板切分异常?）");

  // ── 5.5 纪念链路（**2026-09-26 起覆盖 `/turn` 直返那条路**）───────────────
  // ⚠️ 纪念现在在**第二板**（桩块挪过位置, 见 `stub_world.BOND_BLOCK`）:
  //    首板走 `/api/bond/start` 直返（那条路 2026-09-12 已补 `syncMemorial`），
  //    **第二板走 `/api/bond/turn` 直返**（预生成领出）——真机 2026-09-26 报障的
  //    正是后者（纪念板照常显示立绘+普通背景、图不淡入; 名字牌倒是被 `is_end`
  //    隐藏了, 所以看起来"只做对了一半"）。本节只断言"首板全段都是正常视觉";
  //    第二板的纪念断言在裁决推进之后（"6.6 纪念链路·第二板"）。
  const readMemorial = () => page.evaluate(() => {
    const layer = document.getElementById("bond-memorial");
    const stage = document.getElementById("bond-stage");
    const bg = document.getElementById("bond-bg");
    return {
      layerOn: !!(layer && layer.classList.contains("on")),
      layerImg: (layer && layer.style.backgroundImage) || "",
      stageHidden: !!(stage && stage.classList.contains("hidden")),
      bgCleared: !(bg && bg.style.backgroundImage),
      para: ((document.querySelector("#bond-text .bond-para") || {}).textContent || "").trim(),
    };
  });
  {
    const first = board1[0] || {};
    record("纪念链路·首板（应无纪念）", {
      info: `段数=${board1.length} 首段="${(first.text || "").slice(0, 14)}" `
        + `立绘隐藏=${first.stageHidden} 背景清空=${first.bgCleared} 纪念层=${first.memorial}`,
      shot: await shot(page, "vn-board1-nomemorial"),
      first, transcript: board1,
    });
    const leaked = board1.filter((p) => p.memorial || p.stageHidden || p.bgCleared);
    if (leaked.length) {
      throw new Error("首板就出现了纪念视觉（纪念不该在首板——桩块被改回去了?）: "
        + JSON.stringify(leaked));
    }
  }

  // ── 6. 裁决 → **第一次点击后直接推进**（2026-09-21 用户裁决）; 玩家那句永不上屏 ──
  // 语义定稿（2026-09-12, 用户核对 BA）: **玩家的话语永远只体现为选项**——
  // 裁决后正文保持"上一句角色台词/旁白", 名字牌/立绘都不动; 把玩家那句当正文念
  // 出来就会被读成"角色说了玩家的话"（真机报障: 睦月/便利屋68 + 你还打算对我怎么恶作剧？）。
  // ⚠️ **2026-09-21 用户裁决（收窄决策 #41 的 live 半边）**: 真机报障 *"点击选项过后，
  //    会弹出一次黄色的已选择选项按钮和灰色的未选按钮"* —— 根因**不是回放**, 而是
  //    `waitTurnIdle` 等待期 `showWaitDots` 把 `#bond-choices` 清空, 只读黄灰组要等
  //    忙等结束才被补画（`bond.js` 的 `data.picked` 分支）。用户口径: *"只要前端的逻辑
  //    是第一次点击后直接推进即可，不要渲染第二次的那个黄色"*。
  //    判据随之改了（**旧的写法正是漏掉这个 bug 的原因**: 原来这里
  //    `waitForFunction(…bs.every(resolved))` = **主动等黄组出现** 20s, 于是"迟到几秒
  //    才弹出"在冒烟里永远是绿的）:
  //      ① 选项组**当场收掉**; ② 整个 live 裁决过程 `.resolved/.picked` **一次都不许出现**;
  //      ③ 不点第二次就进下一板。回放/续看侧的"只读 + 高亮所选"在 6.5 步断言
  //      （那才是真需要它的地方）。
  //    为什么用 MutationObserver 全程盯: ①②都是"**不许发生**"的判据 —— 只在某个时刻
  //    取样, 正好会漏掉"闪一下又没了"。
  const lastLineBefore = board1[board1.length - 1].text;
  const turnSceneAtPick = turnSceneDeliveries.length;      // 裁决前快照（6.6 判据用）
  const plateBeforePick = await page.evaluate(() => ({
    name: (document.querySelector("#bond-name") || {}).textContent || "",
    club: (document.querySelector("#bond-club") || {}).textContent || "",
  }));
  await page.evaluate(() => {
    const box = document.getElementById("bond-choices");
    const txt = document.getElementById("bond-text");
    window.__pickTrace = { resolved: 0, picked: 0, continueBtn: 0, wiped: 0, leaked: [] };
    const scanChoices = () => {
      const bs = [...box.querySelectorAll(".bond-choice")];
      if (bs.some((b) => b.classList.contains("resolved"))) window.__pickTrace.resolved++;
      if (bs.some((b) => b.classList.contains("picked"))) window.__pickTrace.picked++;
      if (!bs.length) window.__pickTrace.wiped++;
      window.__pickTrace.continueBtn += box.querySelectorAll(".bond-continue-btn").length;
    };
    const scanText = () => {
      [...txt.querySelectorAll(".bond-para")].forEach((p) => {
        // 桩世界里 "我来了。" **只是选项文本**（sensei 记录 = 老师的选项组）,
        // 正文里出现它 = 把玩家那句当正文念了（决策 #37 禁止）
        const t = p.textContent.trim();
        if (t.includes("我来了")) window.__pickTrace.leaked.push(t.slice(0, 40));
      });
    };
    new MutationObserver(scanChoices).observe(box, {
      childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    new MutationObserver(scanText).observe(txt, {
      childList: true, subtree: true, characterData: true });
    scanChoices(); scanText();
  });
  await page.locator("#bond-choices .bond-choice").first().click();
  // ① 选项组**当场收掉**（不再"留屏转只读"）
  const collected = await page.waitForFunction(
    () => document.querySelectorAll("#bond-choices .bond-choice").length === 0,
    null, { timeout: 20000 }).then(() => true).catch(() => false);
  // ② **不点任何东西** → 下一板到达（正文换新 或 新板自己的选项出现）。
  //    必须在 ① 之后才判 `bs.length > 0`——否则"还没收掉的旧组"会被当成新板。
  const advanced = await page.waitForFunction((prev) => {
    const ps = [...document.querySelectorAll("#bond-text .bond-para")];
    const last = ps.length ? ps[ps.length - 1].textContent.trim() : "";
    const bs = [...document.querySelectorAll("#bond-choices .bond-choice")];
    return last !== prev || bs.length > 0;
  }, lastLineBefore, { timeout: 20000 }).then(() => true).catch(() => false);
  const pickTrace = await page.evaluate(() => window.__pickTrace);
  const pickState = { collected, advanced, ...pickTrace };
  record("裁决：直接推进（不画第二次黄组）", {
    info: `选项组当场收掉=${collected}; 不点第二次就进下一板=${advanced}; `
      + `黄组出现 resolved=${pickTrace.resolved} picked=${pickTrace.picked}（须 0）; `
      + `等待期清空 ${pickTrace.wiped} 次; `
      + `玩家那句上屏=${JSON.stringify(pickTrace.leaked)}（须空）; `
      + `继续按钮=${pickTrace.continueBtn}（须 0）`,
    shot: await shot(page, "vn-after-pick"),
    pickState,
  });
  if (pickTrace.leaked.length) {
    throw new Error(`裁决后玩家那句被当正文渲染（应只体现为选项）: `
      + JSON.stringify(pickTrace.leaked));
  }
  if (pickTrace.resolved || pickTrace.picked) {
    throw new Error(`live 裁决后不该再画只读黄灰组（2026-09-21 用户: `
      + `"不要渲染第二次的那个黄色"）: ${JSON.stringify(pickTrace)}`);
  }
  if (!collected) {
    throw new Error("点了选项但选项组没被收掉（应点下去直接推进）");
  }
  if (!advanced) {
    throw new Error(`裁决后没有直接进下一板（用户要求: 第一次点击后直接推进）: `
      + JSON.stringify(pickState));
  }
  if (pickTrace.continueBtn) {
    throw new Error(`决策 #41: "▼ 继续"按钮应已删除, 却仍在屏上: ${pickTrace.continueBtn}`);
  }
  // 名字牌仍是角色（用户核对 BA: "名字什么的都不用变"）——裁决不该碰它
  const plateAfterPick = await page.evaluate(() => {
    const np = document.querySelector(".bond-nameplate");
    return {
      name: (document.querySelector("#bond-name") || {}).textContent || "",
      club: (document.querySelector("#bond-club") || {}).textContent || "",
      hidden: !!(np && np.classList.contains("hidden")),
    };
  });
  if (plateAfterPick.name !== plateBeforePick.name
      || plateAfterPick.club !== plateBeforePick.club) {
    throw new Error(`裁决后名字牌不该变（BA: 名字不用变）: `
      + `${JSON.stringify(plateBeforePick)} → ${JSON.stringify(plateAfterPick)}`);
  }

  // ── 6.6 纪念链路·第二板（**`/turn` 直返**）——真机 2026-09-26 报障的那条路 ────
  // 两个判据缺一不可:
  //   ① 这一板确实是 `/api/bond/turn` **直返场景**送来的。轮询那条路一直有
  //      `syncMemorial` ⇒ **只断言纪念视觉抓不到这个 bug**（首板就这么漏过去的）;
  //   ② 触发段**之前**是正常视觉, 触发段起 = 立绘隐藏 + 普通背景清空 + 图淡入。
  // 只读到触发那一段就停——后面 6.5 要的是"中途退出"的状态（别把板读完）。
  {
    const delivered = turnSceneDeliveries.length > turnSceneAtPick;
    // ⚠️ 取样**只做一次**（裁决后那一段 = 触发前）: 再用"边播边轮询要断言的状态"——
    //    按段数计数会抖（打字中点屏会被吞, 2026-09-26 实测 `段数=1` 偶发失败）。
    const board2 = [];
    await capturePara(page, board2);
    const before = board2[0] || {};
    // ── 停在"纪念那一句"上做断言（**逐段推进 + 每段都采样**）──────────────────
    // 锚点 = 桩里那句纪念原文（确定性）; 从前这里是"循环推进直到看见纪念层亮" ——
    // 那是**赌采样撞上窗口**: 纪念板只有 3 段、`_tick` 一次推一段 ⇒ 亮着的窗口
    // 只有一两百毫秒, 采样一错开就整段错过, 而报出来的却是"纪念板没切黑屏"
    // （2026-10-08 实测 3 连红, 引擎侧日志一切正常 —— 假红同样是事故）。
    // 现在: 推一段 → 立刻采样 → 认出纪念句就**停在那儿**再断言视觉。
    const MEMO_LINE = "第一次直视我的眼睛";
    const trace = [];
    let trig = null;
    for (let i = 0; i < 40 && !trig; i++) {
      const s = await page.evaluate(() => {
        const stage = document.getElementById("bond-stage");
        const bg = document.getElementById("bond-bg");
        const layer = document.getElementById("bond-memorial");
        return {
          text: ((document.querySelector("#bond-text .bond-para") || {}).textContent || "").trim(),
          memorial: !!(layer && layer.classList.contains("on")),
          stageHidden: !!(stage && stage.classList.contains("hidden")),
          bgCleared: !(bg && bg.style.backgroundImage),
        };
      });
      trace.push((s.stageHidden && s.bgCleared ? "黑" : "·") + (s.text || "").slice(0, 8));
      if ((s.text || "").includes(MEMO_LINE)) { trig = s; break; }
      await _tick(page);
    }
    record("纪念链路·第二板（/turn 直返）", {
      info: `/turn 直返=${delivered} `
        + `触发前="${(before.text || "").slice(0, 12)}"(立绘隐藏=${before.stageHidden} `
        + `背景清空=${before.bgCleared} 纪念层=${before.memorial}) `
        + `纪念句="${((trig || {}).text || "(没走到)").slice(0, 12)}"`
        + `(立绘隐藏=${(trig || {}).stageHidden} 背景清空=${(trig || {}).bgCleared} `
        + `纪念层=${(trig || {}).memorial}) 逐段=${trace.join(" ")}`,
      shot: await shot(page, "vn-memorial-turn"),
      delivered, before, trigger: trig, trace,
    });
    if (!delivered) {
      throw new Error("裁决后这一板不是 /api/bond/turn 直返的（本用例前提不成立: "
        + "桩块/预生成路径变了?）—— /turn 直返那条路的纪念修复就没人守了");
    }
    if (before.memorial || before.stageHidden || before.bgCleared) {
      throw new Error("触发记录之前就进了纪念视觉（M3 记录级进入点失效?）: "
        + JSON.stringify(before));
    }
    if (!trig) {
      throw new Error("**纪念那一句从没上屏**（段落被跳过 / 板切早了?）逐段="
        + trace.join(" | "));
    }
    // ⚠️ 这里**只**断言"黑屏已切"（M3 记录级进入点）。⛔ 不要断言 `.on`:
    //    `.on` 的真身是"**纪念图已淡入**"（`bond.js:507-511`——只有 `memorialSt.img`
    //    非空才 add），而黑屏（`stage.hidden` + 背景清空, :504-506）**不依赖图**。
    //    旧断言写的是 `!trig.memorial` ⇒ 它其实在赌"图在几秒内到位"（当时桩图是即时的,
    //    所以看起来像在守黑屏）; 桩一生效"图晚到"，它就红成"纪念板没切黑屏" ——
    //    **报文与事实不符**（2026-10-08 实测）。图那件事由下面的"晚到上屏"专门守。
    if (!trig.stageHidden || !trig.bgCleared) {
      throw new Error("**纪念句在屏上时没切黑屏**（M3 记录级进入点 / `/turn` 直返漏"
        + " syncMemorial?）: " + JSON.stringify(trig) + " 逐段=" + trace.join(" | "));
    }
    // ⭐ **图晚到也必须上屏**（2026-10-08 真机 5/5 未上屏的那个 bug）:
    //   桩把生图延迟 `STUB_IMAGE_DELAY_S` 秒（真机 ≈49s）⇒ 这块板上屏时服务端**还没有**图。
    //   判据分两段: ① 轮询**服务端状态**直到 `memorial_img` 非空（记就绪耗时）
    //                ② 此后**玩家零操作**下, 前端必须自己把图淡入（记上屏耗时）。
    //   ⚠️ 从前这里只写"等 6 秒图就该出现" —— 而桩图是**即时**的, 板上屏那一刻就带
    //      URL ⇒ 那条断言其实只验了"图上屏"的**情形③（图先到）**, 对"晚到"永远绿。
    let srv = null;
    let srvMs = 0;
    // 前置判据: **板上屏这一刻服务端必须还没有图**（否则这条断言退化成"图先到"）
    const atBoard = await page.evaluate(async ({ cid, sid }) => {
      try {
        const st = await (await fetch(
          `/api/bond/status?char_id=${cid}&session_id=${sid}`)).json();
        return { img: st.memorial_img || "", busy: !!st.memorial_img_busy };
      } catch (e) { return { img: "", busy: false, err: String(e) }; }
    }, { cid: "igusa_haruka", sid: mmtSessionId });
    if (atBoard.img) {
      throw new Error("桩没演出'图晚到'（板上屏时服务端已有图）—— 调大 "
        + "`STUB_IMAGE_DELAY_S`, 否则这条断言等于只验了'图先到': "
        + JSON.stringify(atBoard));
    }
    const tSrv = Date.now();
    for (let i = 0; i < 300; i++) {                    // 最多 30s 等服务端出图
      srv = await page.evaluate(async ({ cid, sid }) => {
        try {
          const st = await (await fetch(
            `/api/bond/status?char_id=${cid}&session_id=${sid}`)).json();
          return { img: st.memorial_img || "", busy: !!st.memorial_img_busy };
        } catch (e) { return { img: "", busy: false, err: String(e) }; }
      }, { cid: "igusa_haruka", sid: mmtSessionId });
      if (srv.img) { srvMs = Date.now() - tSrv; break; }
      await new Promise((r) => setTimeout(r, 100));
    }
    if (!srv || !srv.img) {
      throw new Error("服务端始终没出纪念图（桩的 STUB_IMAGE_DELAY_S? 生图链断?）: "
        + JSON.stringify(srv));
    }
    let memOk = null;
    let shownMs = 0;
    const tShow = Date.now();
    for (let i = 0; i < 40; i++) {                     // 服务端有图后给前端 4s
      memOk = await readMemorial();
      if (memOk.layerOn && memOk.layerImg) { shownMs = Date.now() - tShow; break; }
      await new Promise((r) => setTimeout(r, 100));
    }
    record("纪念图·晚到上屏（玩家零操作）", {
      info: `板上屏时服务端无图 ✓（busy=${atBoard.busy}）; 服务端就绪 ${srvMs}ms `
        + `→ 前端自行淡入 ${shownMs ? shownMs + "ms" : "❌ 4s 内没上屏"}`
        + `（层开=${!!(memOk && memOk.layerOn)} `
        + `图=${JSON.stringify((memOk || {}).layerImg || "")}）`,
      srvMs, shownMs,
    });
    if (!memOk || !memOk.layerImg) {
      throw new Error("**图晚到就不上屏**: 服务端 `memorial_img` 已就绪, 前端在 4s 内"
        + "没有自己淡入 —— 纪念窗口内没有任何轮询会 syncMemorial"
        + "（玩家不点画面就没有 status 轮询）: " + JSON.stringify(memOk));
    }
    // 把这一板**裁决掉**（点它的老师群选项）——目的是让它**落库**（`_log_scene`
    // 发生在玩家推进时）: 6.5 的"中途退出重进"只回放**已落库的前缀**, 纪念板不落库
    // 就回放不到, 那条路上的纪念同步也就没人守了。
    // ⚠️ 切板只能用老师群（纪念区间内 `switch`/`art` 是硬违规）。
    for (let i = 0; i < 8; i++) {
      const bs = await page.locator("#bond-choices .bond-choice").count();
      if (bs) break;
      await _tick(page);
    }
    if (await page.locator("#bond-choices .bond-choice").count()) {
      await page.locator("#bond-choices .bond-choice").first().click();
      await page.waitForFunction(
        () => document.querySelectorAll("#bond-choices .bond-choice").length === 0,
        null, { timeout: 20000 }).catch(() => {});
    }
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
    // ⚠️ 2026-09-20 真机报障（"还得点到选项**外面**才推进"）的守门搬到这里:
    //    原来它断言在 **live 裁决**那一步（"已裁决的选项不该 disabled"）——而 2026-09-21
    //    起 live 侧根本不再画只读组了, 只读组只剩**回放/续看**这一处, 所以判据跟着搬:
    //    `disabled` 的按钮**吞掉点击**, 而回放里点选项 = 推进（本地下一板）——
    //    一旦被 disabled, 回放里"另一个选项也能点"（决策 #41）就没了。
    if (locked.disabled !== 0) {
      throw new Error(`回放里的只读选项不该被 disabled（点它要能推进）: `
        + JSON.stringify(locked));
    }
    // 回放的**纪念板**同样要进纪念态（立绘隐藏 + 普通背景清空）,
    // 且**档案图要能恢复**（2026-09-12: 图是异步生成的 → 单开 `memorial_image`
    // marker 落真源, 回放/重启据此恢复——这就是"重进还能看到那张纪念图"）
    //
    // ⚠️ 2026-09-26: 纪念板现在是回放的**第二板**（桩块把纪念挪到第二板以覆盖
    //    `/turn` 直返那条路）⇒ 先**推进过去**再看。回放里点只读选项 = 本地推进下一板
    //    （决策 #41）, 而这条推进走的正是 `/api/bond/turn` 的**回放分支（直返场景）**
    //    ——也就是 live 侧曾经漏 `syncMemorial` 的同一条路, 所以这里连"直返"一起断言。
    const turnSceneBeforeReplayMem = turnSceneDeliveries.length;
    await page.locator("#bond-choices .bond-choice").first().click();
    // 等这一次推进的 /turn 直返到达（**别抢跑**——点击后响应是异步的;
    // 2026-09-26 第一版就是立刻查, 恒 false）
    let replayTurnDelivered = false;
    for (let i = 0; i < 40; i++) {
      if (turnSceneDeliveries.length > turnSceneBeforeReplayMem) {
        replayTurnDelivered = true;
        break;
      }
      await new Promise((r) => setTimeout(r, 100));
    }
    // ⭐ 记录级进入点（M3）: 黑屏从 `stage:memorial` **那一段**开始 —— 所以回放里
    //    也必须**逐段播过去**才该看到纪念视觉（只轮询不推进 = 永远停在触发前那一段,
    //    那是 2026-09-26 第一版的第二个错）。
    let replayMem = null;
    for (let i = 0; i < 30; i++) {
      replayMem = await page.evaluate(() => {
        const stage = document.getElementById("bond-stage");
        const bg = document.getElementById("bond-bg");
        const layer = document.getElementById("bond-memorial");
        return {
          stageHidden: !!(stage && stage.classList.contains("hidden")),
          bgCleared: !(bg && bg.style.backgroundImage),
          layerOn: !!(layer && layer.classList.contains("on")),
          layerImg: (layer && layer.style.backgroundImage) || "",
        };
      });
      if (replayMem.layerOn && replayMem.layerImg) break;
      await _tick(page);          // ⭐ 记录级进入点: 必须逐段播到 memorial 那一段
      await new Promise((r) => setTimeout(r, 100));
    }
    record("回放·纪念态", {
      info: `立绘隐藏=${replayMem.stageHidden} 背景清空=${replayMem.bgCleared} `
        + `档案图=${replayMem.layerImg ? "已恢复" : "缺失"} 这一板/turn直返=${replayTurnDelivered}`,
      replayMemorial: replayMem, replayTurnDelivered,
    });
    if (!replayTurnDelivered) {
      throw new Error("回放推进不是 /api/bond/turn 直返的（用例前提不成立: 回放队列变了?）");
    }
    if (!replayMem.stageHidden || !replayMem.bgCleared) {
      throw new Error(`回放的纪念板未进纪念态: ${JSON.stringify(replayMem)}`);
    }
    if (!replayMem.layerImg) {
      throw new Error(`回放没恢复档案纪念图（memorial_image marker 断?）: `
        + JSON.stringify(replayMem));
    }
    // 注: 这里**不推进** —— 交给步骤 7 从回放交棒到后续板。
  }

  // ── 7. 点画面推进（决策 #41: 无"▼ 继续"按钮）→ 收尾板 → 自动 finish 回 MMT ──
  await advanceBoard(page);
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
  // 无条件 showTyping）。
  // ⚠️ 2026-09-27（⑥-3b）判据收窄: 轮询提到 250ms 后, 前端**可能在"这一轮还真的
  //    在跑"时**短暂显示三个点（那是诚实的状态, 不是谎报）⇒ 只认"**后端说没在跑**
  //    却还在跳"，且要持续 >0.8s（前端最长 250ms 才轮到下一拍）+ 留证当时的 running。
  let lieMs = 0, lieSample = null, typingSeen = false;
  for (let i = 0; i < 35; i++) {
    const st = await page.evaluate(() => ({ typing: !!document.getElementById("mmt-typing") }));
    if (!st.typing) { lieMs = 0; await new Promise((r) => setTimeout(r, 100)); continue; }
    typingSeen = true;
    const running = await runningNow(page);
    if (running !== false) { lieMs = 0; await new Promise((r) => setTimeout(r, 100)); continue; }
    lieMs += 100;
    lieSample = { running, lieMs };
    if (lieMs > 800) break;
    await new Promise((r) => setTimeout(r, 100));
  }
  record("收尾后打字指示", {
    info: lieMs > 800
      ? `❌ 收尾话已到且后端已停（running=false）, 三个点仍跳 ${lieMs}ms`
      : (typingSeen ? "三个点只在该轮真在跑时出现（诚实状态）" : "收尾话落地即消失（观察 3.5s）"),
    lieSample,
  });
  if (lieMs > 800) {
    throw new Error(`收尾话已显示完且 running=false, 打字指示（mmt-typing）仍残留 `
      + `${lieMs}ms —— 宽限窗口谎报: ${JSON.stringify(lieSample)}`);
  }

  // ── 9. 回忆册: 书页 → 角色页 → 只读回放（DESIGN_COLLECTION_BOOK）────────
  //  口径: 一格一角色; 角色页只列**已确认结束**的章; 只读回放 0 LLM、不写事件流。
  const CHAR = "igusa_haruka";
  bondWrites.length = 0;                    // 从这里开始算"回放期间的写请求"
  await page.click("#mmt-back");
  await page.waitForSelector("#view-main:not(.hidden)", { timeout: 10000 });
  await page.click("#btn-playback");
  await page.waitForSelector("#view-collection:not(.hidden)", { timeout: 10000 });
  await page.waitForSelector('.col-grid [data-char]', { timeout: 20000 });
  // 2026-09-13（审计 A2）: `[data-char]` **包含留白格**（data-char 在"有无封面"
  // 分支之前就设了）——原来把它的数量打成"N 格可点"是**标签撒谎**。这里分开数:
  // 有封面的格子（有 <img>）与留白格, 并**真去点一个留白格**验证能进角色页
  // （原实现在留白分支提前 return, 没挂 click → 点不动）。
  const bookTotal = await page.locator(".col-grid [data-char]").count();
  const withCover = await page.locator(".col-grid [data-char] .col-cell-img").count();
  const blankInfo = await page.evaluate(() =>
    [...document.querySelectorAll(".col-grid .col-slot.blank[data-char]")]
      .map((el) => el.dataset.char));
  record("回忆册书页", {
    info: `${bookTotal} 格（${withCover} 有封面 / ${blankInfo.length} 留白）`,
    shot: await shot(page, "book"),
    bookTotal, withCover, blankChars: blankInfo,
  });
  if (!bookTotal) throw new Error("回忆册书页没有任何角色格");

  if (blankInfo.length) {
    // 留白格必须可点: 点它 → 角色页打开（后端本就不看封面）
    await page.click(`.col-grid [data-char="${blankInfo[0]}"]`);
    await page.waitForSelector("#col-char:not(.hidden)", { timeout: 10000 });
    await page.click("#col-char-back");
    await page.waitForSelector("#col-char.hidden", { timeout: 10000 });
  }

  await page.click(`.col-grid [data-char="${CHAR}"]`);
  await page.waitForSelector("#col-char:not(.hidden)", { timeout: 10000 });
  // ⚠️ 留证（2026-09-27）: 这条 20s 等待偶发超时, 而"超时"本身分不清三种真身——
  //    列表停在"加载中…"（请求没回来）/ "还没有结束的故事。"（后端返回空）/
  //    "读不到她的故事: …"（请求失败）。失败信息带上列表原文, 一次就能定位。
  await page.waitForSelector("#col-chapters .col-chapter", { timeout: 20000 })
    .catch(async (e) => {
      const txt = await page.evaluate(() =>
        ((document.getElementById("col-chapters") || {}).innerText || "").slice(0, 200));
      throw new Error(`角色页没列出章节（列表原文=${JSON.stringify(txt)}）: ${e.message}`);
    });
  const chapterTitles = await page.locator("#col-chapters .col-chapter-name").allInnerTexts();
  const hasThumb = await page.locator("#col-chapters .col-chapter-thumb").count();
  record("回忆册角色页", {
    info: `章节=${JSON.stringify(chapterTitles)} 纪念图缩略=${hasThumb}`,
    shot: await shot(page, "book-chapters"),
    chapterTitles, hasThumb,
  });
  if (!chapterTitles.includes("放学后的约定")) {
    throw new Error(`角色页没列出刚结束的章: ${JSON.stringify(chapterTitles)}`);
  }

  await page.click("#col-chapters .col-chapter .col-play");
  await page.waitForSelector("#view-bond:not(.hidden)", { timeout: 20000 });
  const roBoard1 = await readUntilInteraction(page, "只读回放首板", 60000);
  // 只读回放的选项板（决策 #41）: **另一个选项也可以点**（"毕竟都是一句话"——收敛链
  // 下通往同一后续）, 高亮仍留在当时选的那句; 点了只推进, 不发任何请求。
  const roChoice = await page.evaluate(() => {
    const bs = [...document.querySelectorAll("#bond-choices .bond-choice")];
    return {
      total: bs.length,
      disabled: bs.filter((b) => b.disabled).length,
      picked: (bs.find((b) => b.classList.contains("picked")) || {}).textContent || "",
      continueBtn: document.querySelectorAll("#bond-choices .bond-continue-btn").length,
    };
  });
  record("只读回放首板", {
    info: `${roBoard1.length} 段; 选项 ${roChoice.total}（可点 ${roChoice.total - roChoice.disabled}）`
      + ` 高亮=${JSON.stringify(roChoice.picked)} 继续按钮=${roChoice.continueBtn}`,
    shot: await shot(page, "book-replay"),
    transcript: roBoard1, roChoice,
  });
  // P1①（2026-09-20）: **只读回放里的纪念板 = live**（立绘隐藏 + 普通背景清空 +
  // 档案纪念图淡入）。此前这三件事只在 live 的 `syncMemorial` 里做, 回放只挂章缩略图
  // ⇒ 册子里播到纪念段是"普通板 + 没有图"。
  // ⚠️ 2026-09-26: 纪念板现在在**第二板**（桩块为覆盖 `/turn` 直返挪过位置）,
  //    且记录级进入点（M3）要求"播到 `stage:memorial` **那一段**才切" ⇒ 只读回放也
  //    必须**逐段播过去**（只读态点画面 = 本地推进, 不发任何请求）。
  let roMem = null;
  for (let i = 0; i < 40; i++) {
    roMem = await page.evaluate(() => {
      const layer = document.getElementById("bond-memorial");
      const stage = document.getElementById("bond-stage");
      const bg = document.getElementById("bond-bg");
      return {
        on: !!(layer && layer.classList.contains("on")),
        img: (layer && layer.dataset.src) || "",
        stageHidden: !!(stage && stage.classList.contains("hidden")),
        bgCleared: !bg || !bg.style.backgroundImage,
      };
    });
    if (roMem.on && roMem.img) break;
    await _tick(page);
    await new Promise((r) => setTimeout(r, 100));
  }
  record("只读回放·纪念板", {
    info: `纪念层=${roMem.on ? "淡入" : "❌未开"} 图=${roMem.img || "（无）"}`
      + ` 立绘隐藏=${roMem.stageHidden} 普通背景清空=${roMem.bgCleared}`,
    shot: await shot(page, "book-replay-memorial"), memorial: roMem,
  });
  if (!roMem.on || !roMem.img.includes("/gallery/") || !roMem.stageHidden
      || !roMem.bgCleared) {
    throw new Error(`只读回放的纪念板没进纪念态（应与 live 一致）: ${JSON.stringify(roMem)}`);
  }
  if (bondWrites.length) {
    throw new Error(`只读回放发了写请求（应 0 LLM/不写事件流）: ${bondWrites.join(" / ")}`);
  }
  if (roChoice.continueBtn !== 0) {
    throw new Error(`决策 #41: 回放里不该有"▼ 继续"按钮: ${JSON.stringify(roChoice)}`);
  }
  if (roChoice.disabled !== 0) {
    throw new Error(`回放的另一个选项应可点（决策 #41）: ${JSON.stringify(roChoice)}`);
  }
  if (roChoice.picked.trim() !== "我来了。") {
    throw new Error(`回放应保留当时所选的高亮: ${JSON.stringify(roChoice)}`);
  }
  // 点"另一个选项"：只读推进（本地下一板）——不报错、不发写请求
  const other = page.locator("#bond-choices .bond-choice:not(.picked)").first();
  const otherCount = await other.count();
  let afterOther = [];
  if (otherCount) {
    await other.click();
    await waitInteractionReset(page, 20000).catch(() => { /* 末板可能直接到出口 */ });
    afterOther = await readUntilInteraction(
      page, "只读回放（点了另一个选项之后）", 60000).catch(() => []);
  }
  record("只读回放·另一个选项可点", {
    info: otherCount
      ? `点『另一个选项』→ 本地推进到下一板（${afterOther.length} 段, 无写请求）`
      : "（本章只有一个选项, 跳过）",
    bondWrites: bondWrites.length, afterOther,
  });
  if (otherCount && !afterOther.length) {
    throw new Error("点回放的另一个选项没有推进到下一板（决策 #41: 点了应推进）");
  }
  if (bondWrites.length) {
    throw new Error(`点回放选项后出现写请求（只读契约破）: ${bondWrites.join(" / ")}`);
  }
  // 一路推进到章末 → 出现"返回回忆册"
  const exitBtn = page.locator("#bond-choices .bond-replay-exit");
  let sawEndButton = false;
  for (let i = 0; i < 16 && !sawEndButton; i++) {
    if (await exitBtn.count()) { sawEndButton = true; break; }
    await readUntilInteraction(page, `只读回放第 ${i + 1} 板`, 30000).catch(() => {});
    if (await exitBtn.count()) { sawEndButton = true; break; }   // is_end 板读完 → 出口
    await advanceBoard(page, 30000).catch(() => { /* 已在末板/出口 */ });
  }
  record("只读回放播完", {
    info: sawEndButton ? "出现『返回回忆册』" : "❌ 没走到章末",
    shot: await shot(page, "book-replay-end"),
  });
  if (!sawEndButton) throw new Error("只读回放没走到章末（『返回回忆册』未出现）");
  // ★ 退出纪念后**普通背景要还回来**（2026-09-20 用户要求）: 进入纪念时
  //   `syncMemorial` 把 `#bond-bg` 清空当黑屏兜底, 退出时若它仍空着 → 按当前这块板
  //   的 `background_url` 还回去（本章是"整章都在纪念窗口里", 所以只能在出口屏验:
  //   收尾板本身没有 background_url 时**不该**把上一张糊回来）。
  const bgAfter = await page.evaluate(() => {
    const bg = document.getElementById("bond-bg");
    return { bg: (bg && bg.style.backgroundImage) || "", layerOn:
      !!(document.getElementById("bond-memorial") || {}).classList
      && document.getElementById("bond-memorial").classList.contains("on") };
  });
  record("只读回放·退出后背景", {
    info: `背景=${bgAfter.bg ? "已恢复" : "（空——本章收尾板无背景, 正确）"}`
      + ` 纪念层=${bgAfter.layerOn ? "❌仍开" : "已淡出"}`,
    bgAfter,
  });
  if (bgAfter.layerOn) throw new Error(`退出只读回放后纪念层仍开着: ${JSON.stringify(bgAfter)}`);
  if (bondWrites.length) {
    throw new Error(`只读回放全程出现写请求: ${bondWrites.join(" / ")}`);
  }
  await exitBtn.click();                                       // 返回回忆册
  await page.waitForSelector("#view-collection:not(.hidden):not(#view-bond)", { timeout: 10000 })
    .catch(() => { /* 视图类名不同也不致命, 下面用 DOM 判断 */ });
  const backToChar = await page.evaluate(() => {
    const v = document.getElementById("view-collection");
    const c = document.getElementById("col-char");
    return { book: v && !v.classList.contains("hidden"),
             char: c && !c.classList.contains("hidden") };
  });
  record("回放后回角色页", { info: JSON.stringify(backToChar) });
  if (!backToChar.book) throw new Error("退出只读回放后没回到回忆册");

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
            continue_count: box ? box.querySelectorAll(".bond-replay-exit").length : 0,
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
