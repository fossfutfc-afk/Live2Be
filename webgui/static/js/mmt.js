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
  openChat(id, name);
}

// ---------------------------------------------------------------------------
// 聊天窗（会话 + 发送 + 轮询 + 逐块冒出渲染）
// 渲染规则: 角色回复【一小块一小块直接冒出】——第一块立即(TTFT), 后续块间隔冒出,
//           模拟"对方一句一句发消息"的真实聊天感。
// ---------------------------------------------------------------------------

let _chatChar = "";        // 当前聊天角色 id
let _chatSession = "";     // session_id
let _chatName = "";        // 显示名
let _lastSeq = 0;          // 已渲染的最后 seq
let _polling = false;      // 是否在轮询回复中

const POLL_MS = 1000;          // 轮询间隔
const BUBBLE_GAP_MS = 600;     // 逐块冒出间隔（第一块 TTFT 立即, 后续块此间隔）
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function openChat(charId, name) {
  _polling = false;                       // 停止旧轮询
  _chatChar = charId;
  _chatName = name;
  // 打开会话（恢复进行中 or 新开世界线）+ 拉历史
  let data;
  try {
    data = await (await fetch(`/api/mmt/session?char_id=${charId}`)).json();
  } catch (e) {
    const win = $("mmt-chat-window");
    if (win) {
      win.classList.add("has-chat");
      win.innerHTML = `<div class="mmt-chat-error">打开会话失败（网络错误: ${e.message}）</div>`;
    }
    return;
  }
  _chatSession = data.session_id;
  _lastSeq = data.last_seq || 0;
  _chatName = data.display_name || name;
  // 聊天窗结构
  const win = $("mmt-chat-window");
  win.classList.add("has-chat");
  win.innerHTML = `
    <div class="mmt-chat-head">
      <span class="mmt-chat-name">${_chatName}</span>
    </div>
    <div class="mmt-bubbles" id="mmt-bubbles"></div>
    <div class="mmt-chat-input">
      <input id="mmt-input" type="text" maxlength="500" placeholder="输入消息…" autocomplete="off">
      <button id="mmt-send">发送</button>
    </div>
  `;
  renderBubbles(data.bubbles || []);      // 历史气泡一次性渲染（不逐块）
  scrollBubbles();
  $("mmt-send").addEventListener("click", sendMessage);
  $("mmt-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });
  $("mmt-input").focus();
}

function renderBubble(b) {
  const box = $("mmt-bubbles");
  if (!box) return;
  const div = document.createElement("div");
  div.className = "mmt-bubble " + (
    b.kind === "bond_entry" ? "bond-entry"
      : (b.side === "player" ? "player" : "char"));
  div.textContent = b.text;
  box.appendChild(div);
  scrollBubbles();
}

// 渲染规则: 历史(stream=false)一次性批量渲染（fragment + 无动画 + 一次滚动,
// 避免逐个 append + N 个入场动画压渲染——"载入存档慢"的根因）;
// 新回复(stream=true)逐块冒出（第一块立即=TTFT, 后续块间隔 + 入场动画）
async function renderBubbles(bubbles, { stream = false } = {}) {
  const box = $("mmt-bubbles");
  if (!box) return;
  if (!stream) {
    const frag = document.createDocumentFragment();
    for (const b of bubbles) {
      const div = document.createElement("div");
      div.className = "mmt-bubble " + (
        b.kind === "bond_entry" ? "bond-entry"
          : (b.side === "player" ? "player" : "char"));
      div.style.animation = "none";          // 历史无入场动画
      div.textContent = b.text;
      frag.appendChild(div);
    }
    box.appendChild(frag);
    scrollBubbles();                          // 一次滚动
    return;
  }
  for (let i = 0; i < bubbles.length; i++) {
    renderBubble(bubbles[i]);                 // 新回复保留入场动画 + 逐块
    if (i > 0) {
      await sleep(BUBBLE_GAP_MS);             // 第一块 TTFT, 后续块等待间隔
    }
  }
}

function scrollBubbles() {
  const box = $("mmt-bubbles");
  if (box) box.scrollTop = box.scrollHeight;
}

function showTyping() {
  const box = $("mmt-bubbles");
  if (!box || $("mmt-typing")) return;
  const t = document.createElement("div");
  t.className = "mmt-bubble char typing";
  t.id = "mmt-typing";
  t.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
  box.appendChild(t);
  scrollBubbles();
}

function hideTyping() { $("mmt-typing")?.remove(); }

function renderError(msg) {
  const box = $("mmt-bubbles");
  if (!box) return;
  const d = document.createElement("div");
  d.className = "mmt-bubble error";
  d.textContent = "（" + msg + "）";
  box.appendChild(d);
  scrollBubbles();
}

// ---------------------------------------------------------------------------
// 微信式发送失败（感叹号 + 重发/删除）
// ---------------------------------------------------------------------------

// 发送失败 → 玩家气泡保留 + 红色感叹号（点击 → 重发/删除菜单）
function renderFailedBubble(text) {
  const box = $("mmt-bubbles");
  if (!box) return;
  const wrap = document.createElement("div");
  wrap.className = "mmt-msg failed";
  const bubble = document.createElement("div");
  bubble.className = "mmt-bubble player";
  bubble.textContent = text;
  const mark = document.createElement("span");
  mark.className = "mmt-fail-mark";
  mark.textContent = "!";
  mark.title = "发送失败，点击重发或删除";
  mark.addEventListener("click", (e) => {
    e.stopPropagation();
    showFailMenu(mark, text, wrap);
  });
  wrap.appendChild(bubble);
  wrap.appendChild(mark);
  box.appendChild(wrap);
  scrollBubbles();
}

function showFailMenu(mark, text, wrap) {
  const old = wrap.querySelector(".mmt-fail-menu");
  if (old) { old.remove(); return; }
  const menu = document.createElement("div");
  menu.className = "mmt-fail-menu";
  const retry = document.createElement("button");
  retry.textContent = "重发";
  retry.className = "mmt-fail-act";
  retry.onclick = () => {
    menu.remove();
    retryFailedMessage(text, wrap);
  };
  const del = document.createElement("button");
  del.textContent = "删除";
  del.className = "mmt-fail-act danger";
  del.onclick = () => {
    menu.remove();
    wrap.remove();               // 本地删除（未入库, 重开也没有）
  };
  menu.append(retry, del);
  wrap.appendChild(menu);
}

// 重发: 气泡恢复正常态（移除感叹号）→ 调 chat → 轮询拿角色回复
async function retryFailedMessage(text, wrap) {
  wrap.classList.remove("failed");
  const mark = wrap.querySelector(".mmt-fail-mark");
  if (mark) mark.remove();
  const menu = wrap.querySelector(".mmt-fail-menu");
  if (menu) menu.remove();
  showTyping();
  let res, data;
  try {
    res = await fetch("/api/mmt/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ char_id: _chatChar, session_id: _chatSession, text }),
    });
    data = await res.json();
  } catch (e) {
    wrap.classList.add("failed");
    renderError("重发失败（网络错误: " + e.message + "）");
    return;
  }
  if (!res.ok || !data.accepted) {
    wrap.classList.add("failed");
    renderError(data.detail || data.reason || "重发失败");
    return;
  }
  if (!_polling) {
    _polling = true;
    pollLoop();                             // 重发成功 → 轮询角色回复
  }
}

function setInputEnabled(on) {
  const input = $("mmt-input"), send = $("mmt-send");
  if (input) input.disabled = !on;
  if (send) send.disabled = !on;
  if (on && input) input.focus();
}

async function sendMessage() {
  const input = $("mmt-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  renderBubble({ side: "player", text });   // 玩家气泡立即上屏（允许连发, 不锁输入）
  showTyping();                             // 打字指示
  let res, data;
  try {
    res = await fetch("/api/mmt/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ char_id: _chatChar, session_id: _chatSession, text }),
    });
    data = await res.json();
  } catch (e) {
    hideTyping();
    renderFailedBubble(text);      // 微信式: 气泡保留 + 感叹号（可重发/删除）
    renderError("发送失败（网络错误: " + e.message + "）");
    return;
  }
  if (!res.ok || !data.accepted) {
    hideTyping();
    renderFailedBubble(text);
    renderError(data.detail || data.reason || "发送失败");
    return;
  }
  if (!_polling) {
    _polling = true;
    pollLoop();                             // 已在轮询则复用, 不重复启动
  }
}

async function pollLoop() {
  while (_polling) {
    await sleep(POLL_MS);
    let data;
    try {
      data = await (await fetch(
        `/api/mmt/events?char_id=${_chatChar}&session_id=${_chatSession}&since=${_lastSeq}`,
      )).json();
    } catch (e) {
      hideTyping();
      renderError("轮询失败（网络错误: " + e.message + "）");
      _polling = false;
      break;
    }
    if (data.error) {
      hideTyping();
      renderError("回复失败: " + data.error);
      _polling = false;
      break;
    }
    if (data.bubbles && data.bubbles.length) {
      hideTyping();
      _lastSeq = data.last_seq;
      // 增量轮询: 跳过 player 气泡（sendMessage 已乐观渲染, 避免重复渲染;
      // 全量加载 openChat(since=0) 仍渲染 player——历史重建需要）
      const renderable = data.bubbles.filter((b) => b.side !== "player");
      await renderBubbles(renderable, { stream: true });  // 逐块冒出
    }
    if (!data.running) {
      hideTyping();
      _polling = false;
      break;
    }
    showTyping();                           // 还在处理（或排队）, 保持打字指示
  }
  setInputEnabled(true);
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
