// 无头验证 l2d-demo 的 Spine 加载（连系统 Chrome），抓取 404 与运行时状态。
import puppeteer from 'puppeteer-core';
const EXE = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

const browser = await puppeteer.launch({
  executablePath: EXE, headless: 'new',
  args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--window-size=1000,800'],
});
const page = await browser.newPage();
const logs = [];
const bad = [];
page.on('console', (m) => logs.push(`${m.type()}: ${m.text()}`));
page.on('pageerror', (e) => logs.push(`PAGEERROR: ${e.message}`));
page.on('response', (r) => { if (r.status() >= 400) bad.push(`${r.status()} ${r.url()}`); });
page.on('requestfailed', (r) => bad.push(`REQFAIL ${r.url()} ${r.failure()?.errorText}`));
await page.setViewport({ width: 1000, height: 800 });

try { await page.goto('http://localhost:5199/', { waitUntil: 'networkidle0', timeout: 30000 }); }
catch (e) { console.log('GOTO_ERR:', e.message); }
await new Promise((r) => setTimeout(r, 5000));

const dbg = await page.evaluate(() => window.__spineDebug || {});
await page.screenshot({ path: 'l2d-demo/screenshot.png' }).catch(() => {});
console.log('DEBUG:', JSON.stringify(dbg));
console.log('BAD_HTTP:', JSON.stringify(bad));
console.log('LOGS: ' + JSON.stringify(logs.slice(0, 25)));
await browser.close();
