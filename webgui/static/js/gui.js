// Live2Be GUI — 登录页逻辑（M1: 起名字/改名字 + namegg 彩蛋）
"use strict";

const $ = (id) => document.getElementById(id);

function show(id) {
  document.querySelectorAll("#app > section").forEach((s) => s.classList.add("hidden"));
  $(id).classList.remove("hidden");
}

// ── menu 背景轮播（BA 大版本图按序播放, 淡入淡出 + 随机上下缓慢漂移） ──
let _bgImages = [];
let _bgIdx = 0;
let _bgTimer = null;
let _shutdownToken = "";        // `/api/menu` 下发, 关停端点要它（其它源读不到）

// 别的 script（settings.js）也要用那个口令 —— 显式给一个 getter，别靠 let 的跨脚本可见性
function l2bToken() { return _shutdownToken; }
window.l2bToken = l2bToken;
const BG_INTERVAL_MS = 4500;   // 轮播间隔（加快: 8s → 4s）
const PAN_CLASSES = ["bg-pan-up", "bg-pan-down"];

function setBgPan(randomDir) {
  const layer = $("bg-layer");
  PAN_CLASSES.forEach((c) => layer.classList.remove(c));
  void layer.offsetWidth;                       // 强制 reflow, 重置动画
  layer.classList.add(randomDir ? PAN_CLASSES[1] : PAN_CLASSES[0]);
}

async function startBgLoop() {
  try {
    const data = await (await fetch("/api/menu")).json();
    _bgImages = data.images || [];
    _shutdownToken = data.shutdown_token || "";
  } catch (e) { _bgImages = []; }
  if (!_bgImages.length) return;
  const layer = $("bg-layer");
  let failStreak = 0;                       // 连续加载失败计数（服务停了别再空转重试）
  const preload = (src, onErr) => {
    const im = new Image();
    im.onerror = () => { if (onErr) onErr(); };
    im.src = src;
  };
  const fail = () => {
    failStreak++;
    if (failStreak >= 3) {                  // 连续 3 次失败 → 服务疑似不可达, 停轮播
      clearInterval(_bgTimer);
      _bgTimer = null;
    }
  };
  // 只预加载前 2 张——避免 47 张并发下载拖垮首屏（刷新才正常的老毛病）
  _bgImages.slice(0, 2).forEach((s) => preload(s, fail));
  layer.style.backgroundImage = `url("${_bgImages[0]}")`;
  setBgPan(Math.random() < 0.5);
  _bgTimer = setInterval(() => {
    _bgIdx = (_bgIdx + 5) % _bgImages.length;
    preload(_bgImages[(_bgIdx + 1) % _bgImages.length], fail);   // 提前预加载下一张
    layer.style.opacity = 0;
    setTimeout(() => {
      layer.style.backgroundImage = `url("${_bgImages[_bgIdx]}")`;
      setBgPan(Math.random() < 0.5);            // 每次换图随机上/下
      layer.style.opacity = 0.60;
    }, 2000);   // 淡出 → 换图（含新漂移方向）→ 淡入
  }, BG_INTERVAL_MS);
}

function renderEgg(egg) {
  const box = $("egg-box");
  if (!egg) { box.classList.add("hidden"); return; }
  let prefix = "";
  let text = egg;
  if (egg.startsWith("AC~") || egg.startsWith("RJ~") || egg.startsWith("ER~")
      || egg.startsWith("SP~") || egg.startsWith("FT~")) {
    prefix = egg.slice(0, 3);
    text = egg.slice(3);
  }
  if (prefix === "FT~") {
    // 致命: 假装系统宕机——跳转伪 404 页
    location.href = "/err404";
    return;
  }
  if (prefix === "ER~") {
    // 系统级（超强人工智能体等）: alert 弹窗——突兀的系统感
    alert(`【???】${text}`);
    return;
  }
  if (prefix === "SP~") {
    // 惊喜: 弹窗吓人但不阻止——alert 后照常保存成功
    alert(`【???】${text}`);
    return;
  }
  box.textContent = `【???】${text}`;
  box.classList.remove("hidden");
}

async function init() {
  const res = await fetch("/api/name");
  const data = await res.json();
  $("main-name").textContent = data.name;
  const input = $("input-name");
  if (data.has_name) {
    // 已设置过: 预填当前名字（可改）+ 显示欢迎 + 快捷进入主界面
    $("welcome-line").textContent = `欢迎回来，${data.name}（想换个称呼，直接改吧）`;
    $("welcome-line").classList.remove("hidden");
    input.value = data.name;
    $("btn-enter").classList.remove("hidden");
    // 2026-09-11 真机反馈（"填名字总在后面追加老师"）: 预填后**全选**——玩家一
    // 打字就是"替换"而不是"插在旧名字前面/后面"。聚焦时再选一次（点回输入框
    // 想改名也直接替换, 不用先手动删）。
    input.select();
    input.addEventListener("focus", () => input.select());
  }
  show("view-login");
}

async function submitName() {
  const name = $("input-name").value.trim();
  $("msg-error").classList.add("hidden");
  const res = await fetch("/api/name", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name || "sensei" }),
  });
  const data = await res.json();
  if (data.rejected) {
    // RJ~/ER~ 阻止取名: 彩蛋展示（ER → alert 弹窗）+ 提示换名
    // 并 ban 掉「进入主界面」——名字没被接受, 不能进（必须换到有效名字）
    renderEgg(data.egg);
    $("btn-enter").classList.add("hidden");
    $("msg-error").textContent = "这个名字……好像不行。换个称呼吧？";
    $("msg-error").classList.remove("hidden");
    return;
  }
  if (!res.ok) {
    $("msg-error").textContent = data.detail || "保存失败";
    $("msg-error").classList.remove("hidden");
    return;
  }
  renderEgg(data.egg);
  $("welcome-line").textContent = `已保存，学生们将称呼你为「${data.name}」`;
  $("welcome-line").classList.remove("hidden");
  $("main-name").textContent = data.name;
  $("btn-enter").classList.remove("hidden");
  // 不自动进入——玩家自己点「进入主界面」（彩蛋停留眼前, 想看多久看多久）
}

// ── 关闭服务（后端的 Ctrl+C 被忽略, 这里才是常规出口） ──
// 两种关法: 等它跑完（省 token）/ 立刻强制（随时可用 —— 不强制用户等待）。
// 强制是安全的: 提交是两阶段的, 被杀不会写坏; 只是这一段白花而已。
let _shutdownTimer = null;

async function _runtimeStatus() {
  try {
    const res = await fetch("/api/runtime/status");
    return res.ok ? await res.json() : null;
  } catch (e) { return null; }
}

function _fmtBusy(busy) {
  return (busy || [])
    .map((b) => `${b.name}（${b.stage}，已 ${Math.round(b.elapsed_s)} 秒）`)
    .join("、");
}

async function openShutdown() {
  const st = await _runtimeStatus();
  const busy = (st && st.busy) || [];
  const waitBtn = $("btn-shutdown-wait");
  if (busy.length) {
    $("shutdown-msg").textContent =
      `正在跑：${_fmtBusy(busy)}。\n建议等它跑完再关 —— 现在关会把这一段已经花掉的 token` +
      `白费（不会写坏数据）。等不及也可以直接关。`;
    waitBtn.classList.remove("hidden");
  } else {
    $("shutdown-msg").textContent = "现在没有正在跑的任务，可以立刻关。";
    waitBtn.classList.add("hidden");
  }
  $("btn-shutdown-now").classList.remove("hidden");
  $("btn-shutdown-cancel").classList.remove("hidden");
  $("shutdown-modal").classList.remove("hidden");
}

function _closeShutdownModal() {
  clearInterval(_shutdownTimer);
  _shutdownTimer = null;
  $("shutdown-modal").classList.add("hidden");
}

function _watchShutdown(force) {
  $("btn-shutdown-wait").classList.add("hidden");
  $("btn-shutdown-cancel").classList.add("hidden");
  $("shutdown-msg").textContent = force ? "正在强制关闭……" : "正在等它跑完……";
  clearInterval(_shutdownTimer);
  _shutdownTimer = setInterval(async () => {
    const st = await _runtimeStatus();
    if (!st) {                                   // 拉不到 = 服务已经走了
      clearInterval(_shutdownTimer);
      _shutdownTimer = null;
      $("btn-shutdown-now").classList.add("hidden");
      $("shutdown-msg").textContent = "服务已停止，可以关掉这个标签页了。";
      return;
    }
    if (force) return;
    $("shutdown-msg").textContent = st.busy.length
      ? `正在等：${_fmtBusy(st.busy)}……（等不及就点「立即关闭」）`
      : "任务已收手，正在关停……";
  }, 1000);
}

async function closeService(force) {
  let res = null;
  try {
    res = await fetch("/api/shutdown", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: force ? "force" : "graceful", token: _shutdownToken }),
    });
  } catch (e) { res = null; }
  if (!res || !res.ok) {
    $("shutdown-msg").textContent =
      "关不掉：后端没有响应，或者服务不是用 `python -m webgui.serve` 起的。" +
      "急停请关掉控制台窗口，或用任务管理器结束进程。";
    return;
  }
  _watchShutdown(force);
}

document.addEventListener("DOMContentLoaded", () => {
  startBgLoop();
  init();
  $("btn-ok").addEventListener("click", submitName);
  $("input-name").addEventListener("keydown", (e) => { if (e.key === "Enter") submitName(); });
  $("btn-enter").addEventListener("click", () => show("view-main"));
  $("btn-back-login").addEventListener("click", () => show("view-login"));
  $("btn-shutdown").addEventListener("click", openShutdown);
  $("btn-shutdown-wait").addEventListener("click", () => closeService(false));
  $("btn-shutdown-now").addEventListener("click", () => closeService(true));
  $("btn-shutdown-cancel").addEventListener("click", _closeShutdownModal);
});
