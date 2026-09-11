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

document.addEventListener("DOMContentLoaded", () => {
  startBgLoop();
  init();
  $("btn-ok").addEventListener("click", submitName);
  $("input-name").addEventListener("keydown", (e) => { if (e.key === "Enter") submitName(); });
  $("btn-enter").addEventListener("click", () => show("view-main"));
  $("btn-back-login").addEventListener("click", () => show("view-login"));
});
