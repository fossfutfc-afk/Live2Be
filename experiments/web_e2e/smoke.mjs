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

  // ── 5. 点入口 → VN 首板 ───────────────────────────────────────────────
  await page.click(".bond-entry");
  await page.waitForSelector("#view-bond:not(.hidden)", { timeout: 25000 });
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
  record("VN 首板", {
    info: `段落=${board1.length} 选项=${JSON.stringify(choices)} 背景=${bg ? "有" : "无"} `
      + `立绘层=${stage.hidden ? "隐藏" : stage.children + " 个元素"}`,
    shot: await shot(page, "vn-board1"),
    transcript: board1, choices, background: bg.slice(0, 160), stage,
  });
  if (choices.length < 1) throw new Error("首板没有选项（记录流板切分异常?）");

  // ── 6. 裁决 → 就地物化「老师：X」 ─────────────────────────────────────
  // 注: 点击后**必须先等交互区清空**——旧板的选项按钮会停留到响应到达为止,
  // 直接开读会立刻"发现"旧选项并误判为读完了。
  await page.locator("#bond-choices .bond-choice").first().click();
  await waitInteractionReset(page);
  const afterPick = await readUntilInteraction(page, "裁决后物化板");
  const teacherLine = afterPick.find((p) => p.speaker === "老师") || null;
  record("裁决物化", {
    info: teacherLine
      ? `老师那句=${JSON.stringify(teacherLine.text.slice(0, 30))}`
      : `未读到老师名字行（段落=${afterPick.length}）`,
    shot: await shot(page, "vn-after-pick"),
    transcript: afterPick,
  });
  if (!teacherLine) throw new Error("裁决后未渲染出「老师」名字行");
  if (!teacherLine.text.includes("我来了")) throw new Error("老师那句内容不对: " + teacherLine.text);

  // ── 7. 继续 → 收尾板 → 自动 finish 回 MMT ────────────────────────────
  await page.click("#bond-choices .bond-continue-btn");
  await waitInteractionReset(page);
  const ending = await readToEnd(page);
  if (!ending.some((p) => p.text.includes("她愣了一下"))) {
    throw new Error("收尾板正文没读到（反应板未播完）: " + JSON.stringify(ending));
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
