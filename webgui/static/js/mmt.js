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
  // 头像 = 后端给什么显示什么。avatar_type: portrait(该外观 GUI 头像, 如遥香的
  // collection.png) | mmt(BA 圆头像帧) | png(diff 立绘兜底)。
  // 三种都按圆形裁剪: .mmt-avatar 自带 border-radius 50% + object-fit cover,
  // 非方图（半身像 404x456）居中裁成方。
  const img = document.createElement("img");
  img.src = c.avatar;
  img.className = "mmt-avatar" + (c.avatar_type === "mmt" ? "" : " rounded");
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
//: resumePolling 后的宽限期（2026-09-11）: 收尾 wrapup 可能还没占上任务位,
//: 窗口内即使 `running=false` 也继续轮询（否则收尾气泡要切页才出现）
let _pollGraceUntil = 0;
//: 宽限窗口内**是否已经收到新气泡**（2026-09-12 真机报障修正）:
//: 收尾话已经全部显示完了, 三个点却还跳了半分钟才静默消失——宽限窗口只该覆盖
//: "收尾话还没到"的那段; 气泡一旦落地就没有人在输入了（轮询照旧继续, 只为不丢
//: 后续气泡, 但不再显示"对方正在输入…"）。
let _graceGotBubbles = false;

const POLL_MS = 1000;          // 轮询间隔
const POLL_RESUME_GRACE_MS = 25 * 1000;   // VN 退出后继续轮询的宽限窗口
const BUBBLE_GAP_MS = 600;     // 逐块冒出间隔（第一块 TTFT 立即, 后续块此间隔）

// ── 分块打字节奏（2026-08-30: 复刻 core/ui/streaming.py + text_processors.py 的
// publish_reply 语义——webgui 未消费 TurnResult.steps 的补位）─────────────
// split_reply_chunks（字数+随机数切块）: 强断点。！？必切; 逗号/省略号按
// 随机阈值 6~10 字切（丢逗号）; 硬上限 30 字; 尾部 ≤4 字碎片并入上一块。
// chunk_typing_time: 块字数 × 每字随机 80~200ms + 200ms 基础停顿。
const MMT_CHUNK_MAX = 30;
const MMT_CHUNK_FRAGMENT = 4;

function splitReplyChunks(text) {
  const chunks = [];
  let buf = "";
  const threshold = () => 6 + Math.floor(Math.random() * 5);   // 6~10
  for (const ch of text) {
    buf += ch;
    if ("。！？!?".includes(ch)) { chunks.push(buf); buf = ""; }
    else if (ch === "…") {
      if (buf.length >= threshold()) { chunks.push(buf); buf = ""; }
    } else if ("，、,;；".includes(ch)) {
      if (buf.length >= threshold()) { chunks.push(buf.slice(0, -1)); buf = ""; }
    } else if (buf.length >= MMT_CHUNK_MAX) { chunks.push(buf); buf = ""; }
  }
  if (buf) {
    if (buf.length <= MMT_CHUNK_FRAGMENT && chunks.length) {
      chunks[chunks.length - 1] += buf;         // 尾部碎片并入上一块
    } else {
      chunks.push(buf);
    }
  }
  return chunks.filter(Boolean);
}

// 该块打字时长（秒）: 字数 × 每字随机延迟 + 基础停顿（对齐 chunk_typing_time）
function chunkTypingTime(chunk) {
  const perChar = (80 + Math.random() * 120) / 1000;   // 80~200ms
  return chunk.length * perChar + 0.2;
}
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
  renderBubbles(data.bubbles || []);      // 历史气泡一次性渲染（不逐块; 含 bond_entry → 锁定）
  scrollBubbles();
  if (data.in_vn) {
    // 2026-09-09 修复: 中断在押（in_vn）重进**不再强制拉入 VN**——停在聊天页,
    // 由玩家点击羁绊入口主动续进（历史粉泡 bond_entry, 或下方兜底注入的
    // "继续"条 → enterBond → 后端幂等 resumed/回放）。输入保持锁定（VN 中
    // 不许插嘴, 与既有语义一致——入口点击时 lockChat 幂等）。
    lockChat();
    ensureBondResumeEntry();
  } else {
    // 2026-08-30 修复: 历史渲染的 bond_entry 无条件 lockChat——但 bond_entry
    // 也可能来自**已结束**的剧情（vn_exit 已落, 事件流保留）→ 重开聊天窗会
    // 锁死输入, 该角色无法继续对话。会话不在 VN 中 → 解锁。
    unlockChat();
  }
  // 注意: 不主动 unlockChat——历史渲染的 bond_entry 已锁定; 正常会话输入框
  // 默认可用（openChat 重建了聊天窗）; 切换角色时 win.innerHTML 重建也默认可用
  $("mmt-send").addEventListener("click", sendMessage);
  $("mmt-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });
  $("mmt-input").focus();
}

// 已完成羁绊剧情（气泡淡化 2026-09-07）: 完整走完的剧情入口从粉泡变淡行。
// 后端对已完成入口直接给 kind=bond_done（成品文本, 不可点）; 已渲染的粉泡靠
// 轮询响应 bond_done 列表原地翻转（移除点击 → 换 class/文本）。
// _bondEls: seq → div（未完成的入口气泡; 完成翻转时注销）
const _bondEls = new Map();

function bubbleKindClass(b) {
  if (b.kind === "bond_entry") return "bond-entry clickable";
  if (b.kind === "bond_done") return "bond-done";
  return b.side === "player" ? "player" : "char";
}

// 入口粉泡装饰（点击进 VN + 注册翻转位）; bond_done 不装饰（纯文本淡行）
function decorateBubble(div, b) {
  if (b.kind === "bond_entry") {
    const handler = () => enterBond();
    div._bondClick = handler;                 // 翻转时需移除监听
    div.addEventListener("click", handler);
    div.setAttribute("role", "button");
    div.setAttribute("tabindex", "0");
    if (typeof b.seq === "number") _bondEls.set(b.seq, div);
  }
  return div;
}

// 轮询响应的 bond_done: [{seq, text}] → 把已渲染的粉泡原地翻成淡行
function applyBondDone(list) {
  if (!Array.isArray(list)) return;
  for (const it of list) {
    const el = _bondEls.get(it.seq);
    if (!el) continue;
    _bondEls.delete(it.seq);
    if (el._bondClick) {
      el.removeEventListener("click", el._bondClick);
      delete el._bondClick;
    }
    el.classList.remove("bond-entry", "clickable");
    el.classList.add("bond-done");
    el.removeAttribute("role");
    el.removeAttribute("tabindex");
    el.textContent = it.text || "已完成羁绊剧情";
  }
}

function renderBubble(b) {
  const box = $("mmt-bubbles");
  if (!box) return;
  const div = document.createElement("div");
  div.className = "mmt-bubble " + bubbleKindClass(b);
  div.textContent = b.text;
  // 羁绊剧情入口（2026-09-01）: 粉色横幅 = 进入按钮——点击才进入（后端裁决:
  // 首进生成 / 中断续进 resumed / 已完成拒绝→淡行）; 不自动锁输入（点击时锁）
  decorateBubble(div, b);
  box.appendChild(div);
  scrollBubbles();
  return div;
}

// 2026-09-09: 中断在押重进——聊天页若无任何可点羁绊入口（trigger 行可能在
// 窗口外/被排除）, 注入一条"继续"入口条; 已有 bond-entry 则不重复
function ensureBondResumeEntry() {
  const box = $("mmt-bubbles");
  if (!box) return;
  if (box.querySelector(".bond-entry")) return;
  renderBubble({ kind: "bond_entry", text: "羁绊剧情进行中——点击继续" });
}

// 点击粉泡进入羁绊剧情: BondVN.enter 内 POST /api/bond/start——单入口
// （P1 收敛: 原 enterBond 自身先 POST 一次 + enter 内再 POST 一次冗余双发;
// 错误处理统一在 enter 的 catch: showError + exit() → 解锁回 MMT）
async function enterBond() {
  if (!_chatChar || !_chatSession) return;
  lockChat();                                   // 进入 → 锁定输入, 不许插嘴
  window.BondVN.enter(_chatChar, _chatSession, _chatName);
}

// 羁绊剧情锁定: 触发后输入框禁用（VN 模式中不许插嘴; vn_exit 后 unlockChat）
function lockChat() {
  const input = $("mmt-input"), send = $("mmt-send");
  if (input) { input.disabled = true; input.placeholder = "羁绊剧情进行中…"; }
  if (send) send.disabled = true;
}

function unlockChat() {
  const input = $("mmt-input"), send = $("mmt-send");
  if (input) { input.disabled = false; input.placeholder = "输入消息…"; }
  if (send) send.disabled = false;
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
      div.className = "mmt-bubble " + bubbleKindClass(b);
      div.style.animation = "none";          // 历史无入场动画
      div.textContent = b.text;
      // 历史粉泡同样可点击进入（后端裁决: 进行中 resumed 续进）;
      // 已完成剧情 = bond_done 淡行（无装饰, 不可点）
      decorateBubble(div, b);
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
// 设计: 不包 wrap 容器——感叹号 absolute 定位在气泡左侧外（不占流 →
// 失败/成功切换只改气泡 class + 增删感叹号元素, 气泡位置不变, 无拉长/瞬移）
// ---------------------------------------------------------------------------

// 异步失败 → 把对应文本的玩家气泡转失败态（找不到/已失败 → 放弃）
function markFailedBubble(text, errMsg) {
  const box = $("mmt-bubbles");
  if (!box) return;
  const bubbles = Array.from(box.querySelectorAll(".mmt-bubble.player"));
  const target = bubbles.reverse().find((b) => b.textContent === text);
  if (!target || target.classList.contains("failed")) return;
  target.classList.add("failed");
  attachFailMark(target, text, "发送失败" + (errMsg ? "：" + errMsg : ""));
  scrollBubbles();
}

// 给气泡挂感叹号（absolute 定位在气泡左侧外）
function attachFailMark(bubble, text, tip) {
  const mark = document.createElement("span");
  mark.className = "mmt-fail-mark";
  mark.textContent = "!";
  mark.title = tip + "（点击重发或删除）";
  mark.addEventListener("click", (e) => {
    e.stopPropagation();
    showFailMenu(mark, text, bubble);
  });
  bubble.appendChild(mark);
}

function showFailMenu(mark, text, bubble) {
  const old = bubble.querySelector(".mmt-fail-menu");
  if (old) { old.remove(); return; }
  const menu = document.createElement("div");
  menu.className = "mmt-fail-menu";
  const retry = document.createElement("button");
  retry.textContent = "重发";
  retry.className = "mmt-fail-act";
  retry.onclick = () => {
    menu.remove();
    retryFailedMessage(text, bubble);
  };
  const del = document.createElement("button");
  del.textContent = "删除";
  del.className = "mmt-fail-act danger";
  del.onclick = () => {
    menu.remove();
    bubble.remove();               // 本地删除（未入库, 重开也没有）
  };
  menu.append(retry, del);
  bubble.appendChild(menu);
}

// 重发: 气泡恢复正常（移除 failed + 感叹号——气泡本身不动, 无布局抖动）
async function retryFailedMessage(text, bubble) {
  bubble.classList.remove("failed");
  const mark = bubble.querySelector(".mmt-fail-mark");
  if (mark) mark.remove();
  const menu = bubble.querySelector(".mmt-fail-menu");
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
    bubble.classList.add("failed");
    attachFailMark(bubble, text, "重发失败（网络错误: " + e.message + "）");
    renderError("重发失败（网络错误: " + e.message + "）");
    return;
  }
  if (!res.ok || !data.accepted) {
    bubble.classList.add("failed");
    attachFailMark(bubble, text, "重发失败");
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
    // 转态不新建（与异步失败路径 markFailedBubble 一致）——修复 2026-08-30 重复 bug:
    // 之前用 renderFailedBubble 再渲染一条 → 同文本两条气泡（乐观 + 失败标记）
    markFailedBubble(text, e.message);
    renderError("发送失败（网络错误: " + e.message + "）");
    return;
  }
  if (!res.ok || !data.accepted) {
    hideTyping();
    markFailedBubble(text, data.detail || data.reason || "发送失败");
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
    if (data.failed) {
      hideTyping();
      _polling = false;
      // 微信式失败: 把对应文本的玩家气泡转感叹号（可重发/删除）——错误信息进 title
      markFailedBubble(data.failed.text, data.failed.error);
      break;
    }
    if (data.bubbles && data.bubbles.length) {
      hideTyping();
      _graceGotBubbles = true;       // 宽限窗口内已见新气泡 → 收尾话到了（见下）
      _lastSeq = data.last_seq;
      // 增量轮询: 跳过 player 气泡（sendMessage 已乐观渲染, 避免重复渲染;
      // 全量加载 openChat(since=0) 仍渲染 player——历史重建需要）
      // 分块节奏（对齐 publish_reply）: 后端已按 split_reply_chunks 切块（每条
      // 事件一块）→ 第一条直接出（TTFT/生成等待已充当自然延迟）, 后续每块前
      // "对方正在输入…" + 按字数延迟（chunk_typing_time）——"不同段根据字数
      // 多少 bubble 等待"（2026-08-30 修复: 之前逐条直接渲染, 块间零延迟）
      const renderable = data.bubbles.filter((b) => b.side !== "player");
      for (let i = 0; i < renderable.length; i++) {
        const b = renderable[i];
        if (b.kind === "bond_entry" || b.kind === "bond_done") {
          renderBubble(b);
          continue;
        }
        if (i > 0) {
          showTyping();
          await sleep(chunkTypingTime(b.text) * 1000);
          hideTyping();
        }
        renderBubble(b);
      }
      scrollBubbles();
    }
    // 气泡淡化: 已渲染粉泡的剧情完成了 → 原地翻转（无新气泡也每轮同步）
    applyBondDone(data.bond_done || []);
    // 羁绊剧情触发（2026-09-01）: 触发轮只渲染粉色入口气泡（已在 bubbles 循环
    // 渲染, 含 lockChat→改为点击才进入）——不再自动接管 VN 视图; 玩家点击
    // 粉泡（enterBond）才进入; 想继续聊天也可以（粉泡常驻等待点击）
    if (!data.running) {
      // 宽限窗口内（刚退出 VN）: 收尾 wrapup 可能还没占上任务位 → 再等一会。
      // 2026-09-12: **已收到气泡就不再显示"对方正在输入…"**（真机报障: 收尾话
      // 全部显示完了, 三个点还在跳, 半分钟后静默消失）。仍然继续轮询（只到窗口
      // 耗尽）, 免得后到的收尾气泡被漏掉——只是不再谎报"有人在打字"。
      if (Date.now() < _pollGraceUntil) {
        if (!_graceGotBubbles) {
          showTyping();                       // 收尾话还没到
        } else {
          hideTyping();                       // 已到: 静默等窗口耗尽
        }
        continue;
      }
      hideTyping();
      _polling = false;
      break;
    }
    showTyping();                           // 还在处理（或排队）, 保持打字指示
  }
  setInputEnabled(true);
}

// 重启轮询（BondVN 收尾后调用——拉 wrapup 收尾话 + 后续聊天回复）
// 2026-09-11: 带**宽限窗口**——收尾 wrapup 是后端起线程跑的, 前端重启轮询时
// 它可能还没占上任务位（`running` 仍是 false）→ 旧逻辑第一轮就停轮询, 收尾气泡
// 要等切页/重进才出现（真机报障"finish 后 mmt 不会立刻逐条显示"）。窗口内即使
// 看见 running=false 也继续轮询, 直到收尾话落地或窗口耗尽。
function resumePolling() {
  _pollGraceUntil = Date.now() + POLL_RESUME_GRACE_MS;
  _graceGotBubbles = false;          // 新一轮宽限: 还没收到收尾气泡
  if (!_polling) {
    _polling = true;
    pollLoop();
  }
}

// 暴露给 BondVN（羁绊剧情视图）: VN 结束后解锁输入 + 重启轮询
window.MMT = { unlockChat, resumePolling };

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
