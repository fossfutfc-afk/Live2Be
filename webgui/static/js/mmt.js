// Live2Be MMT 界面（顶部横幅 + 左模式栏: 资料/对话——右侧按模式渲染）
// 聊天逻辑后写; 各模式独立排序（资料: 好感/生日/名字; 对话: 最新/好感）
"use strict";

// 注意: 不重复声明 $/show —— gui.js 已提供全局

let _profileSort = "affection";   // 资料模式排序
let _chatSort = "recent";         // 对话模式排序

// ---------------------------------------------------------------------------
// 渲染辅助
// ---------------------------------------------------------------------------

function renderAvatar(wrap, c, sizeCls) {
  // BA 圆头像（mmt/ 渲染图）直接用; diff 兜底 png 圆形裁剪
  const img = document.createElement("img");
  img.src = c.avatar;
  img.className = "mmt-avatar" + (c.avatar_type === "png" ? " rounded" : "");
  if (sizeCls) img.classList.add(sizeCls);
  wrap.appendChild(img);
}

function heartHTML(c) {
  const level = c.affection ? c.affection.level : 1;   // 无好感 = 初始 1
  return `<span class="mmt-item-heart">❤<span class="val">${level}</span></span>`;
}

// ---------------------------------------------------------------------------
// 资料模式（角色卡: 圆头像+名字+生日+bio+好感）
// ---------------------------------------------------------------------------

async function loadProfile() {
  const list = $("mmt-profile-list");
  list.innerHTML = '<p class="mmt-loading">加载中…</p>';
  try {
    const data = await (await fetch("/api/mmt/characters")).json();
    let chars = data.characters || [];
    if (!chars.length) {
      list.innerHTML = '<p class="mmt-loading">没有角色（需白名单 + 头像）</p>';
      return;
    }
    chars = sortBy(chars, _profileSort);
    list.innerHTML = "";
    for (const c of chars) {
      const card = document.createElement("div");
      card.className = "mmt-profile-card";
      card.dataset.id = c.id;
      card.innerHTML = `
        <span class="mmt-avatar-wrap"></span>
        <div class="mmt-item-meta">
          <div class="mmt-item-name">${c.name}</div>
          <div class="mmt-item-sub">🎂 ${c.birthday || "—"}</div>
          <div class="mmt-item-bio">${c.bio ? c.bio : "&nbsp;"}</div>
        </div>
        ${heartHTML(c)}
      `;
      renderAvatar(card.querySelector(".mmt-avatar-wrap"), c);
      card.addEventListener("click", () => selectProfile(c.id, c.name));
      list.appendChild(card);
    }
  } catch (e) {
    list.innerHTML = '<p class="mmt-loading">加载失败: ' + e + '</p>';
  }
}

function selectProfile(id, name) {
  document.querySelectorAll(".mmt-profile-card").forEach((x) => x.classList.remove("selected"));
  const el = document.querySelector(`.mmt-profile-card[data-id="${id}"]`);
  if (el) el.classList.add("selected");
}

// ---------------------------------------------------------------------------
// 对话模式（成员列表 + 聊天窗口占位）
// ---------------------------------------------------------------------------

async function loadChatList() {
  const list = $("mmt-chat-list");
  list.innerHTML = '<p class="mmt-loading">加载中…</p>';
  try {
    const data = await (await fetch(`/api/mmt/characters?sort=${_chatSort}`)).json();
    const chars = data.characters || [];
    if (!chars.length) {
      list.innerHTML = '<p class="mmt-loading">没有角色</p>';
      return;
    }
    list.innerHTML = "";
    for (const c of chars) {
      const item = document.createElement("div");
      item.className = "mmt-item";
      item.dataset.id = c.id;
      item.innerHTML = `
        <span class="mmt-avatar-wrap"></span>
        <div class="mmt-item-meta">
          <div class="mmt-item-name">${c.name}</div>
          <div class="mmt-item-bio">${c.bio ? c.bio : "&nbsp;"}</div>
        </div>
        ${heartHTML(c)}
      `;
      renderAvatar(item.querySelector(".mmt-avatar-wrap"), c);
      item.addEventListener("click", () => selectChatChar(c.id, c.name));
      list.appendChild(item);
    }
  } catch (e) {
    list.innerHTML = '<p class="mmt-loading">加载失败: ' + e + '</p>';
  }
}

function selectChatChar(id, name) {
  document.querySelectorAll("#mmt-chat-list .mmt-item").forEach((x) => x.classList.remove("selected"));
  const el = document.querySelector(`#mmt-chat-list .mmt-item[data-id="${id}"]`);
  if (el) el.classList.add("selected");
  // 聊天窗口占位（逻辑后写: 连引擎、气泡、进 VN）
  $("mmt-chat-window").innerHTML = `
    <div class="mmt-chat-box">
      <h3>与 ${name} 的对话</h3>
      <p class="mmt-empty">（聊天逻辑建设中——后续接入引擎）</p>
    </div>`;
}

// ---------------------------------------------------------------------------
// 排序（前端独立排序逻辑——资料: 好感/生日/名字; 对话: 后端 sort 参数）
// ---------------------------------------------------------------------------

function sortBy(chars, mode) {
  const arr = chars.slice();
  if (mode === "birthday") {
    // 生日 M/D → 按 (月,日) 排
    return arr.sort((a, b) => {
      const pa = parseBirthday(a.birthday), pb = parseBirthday(b.birthday);
      return (pa[0] - pb[0]) || (pa[1] - pb[1]);
    });
  }
  if (mode === "name") {
    return arr.sort((a, b) => a.name.localeCompare(b.name, "zh"));
  }
  // 默认好感（exp 倒序; 无好感 = 1 级 exp 0）
  return arr.sort((a, b) => expOf(b) - expOf(a));
}

function expOf(c) { return c.affection ? (c.affection.exp || 0) : 0; }

function parseBirthday(bd) {
  if (!bd) return [99, 99];            // 无生日 → 排最后
  const m = /^(\d{1,2})\/(\d{1,2})/.exec(bd.trim());
  return m ? [Number(m[1]), Number(m[2])] : [99, 99];
}

// ---------------------------------------------------------------------------
// 模式切换
// ---------------------------------------------------------------------------

function switchMode(mode) {
  document.querySelectorAll(".mode-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === mode));
  $("mmt-profile").classList.toggle("hidden", mode !== "profile");
  $("mmt-chat").classList.toggle("hidden", mode !== "chat");
}

document.addEventListener("DOMContentLoaded", () => {
  loadProfile();
  loadChatList();
  // 模式切换（资料/对话）
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchMode(btn.dataset.mode));
  });
  // 资料模式排序
  document.querySelectorAll("#mmt-profile .sort-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      _profileSort = btn.dataset.sort;
      document.querySelectorAll("#mmt-profile .sort-btn").forEach((x) =>
        x.classList.toggle("active", x === btn));
      loadProfile();
    });
  });
  // 对话模式排序
  document.querySelectorAll("#mmt-chat .sort-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      _chatSort = btn.dataset.sort;
      document.querySelectorAll("#mmt-chat .sort-btn").forEach((x) =>
        x.classList.toggle("active", x === btn));
      loadChatList();
    });
  });
  $("mmt-back").addEventListener("click", () => show("view-main"));
});
