// Live2Be MMT 界面（顶部横幅 + 左模式栏: 资料/对话——右侧按模式渲染）
// 聊天逻辑后写; 各模式独立排序（资料: 好感/生日/名字; 对话: 最新/好感）
"use strict";

// 注意: 不重复声明 $/show —— gui.js 已提供全局

let _profileSort = "affection";   // 资料模式排序
let _chatSort = "recent";         // 对话模式排序

// ── 好感自动刷新（2026-09-20 用户: *"前端的好感度建议最好能自动刷新，现在一定要
//    重新排序或者重进才能看到"*）────────────────────────────────────────────
// 为什么用轮询而不是事件驱动: 好感是 **digest** 写的（收尾话之后才落地, 后台异步）,
// 客户端不知道它什么时候完成; 而两个列表都只是几十条 JSON —— 轮询最便宜也最稳。
// 只在"MMT 可见 + 不在 VN 里 + 页面没被切走"时跑; 值没变就**不碰 DOM**（不闪）。
const AFFECTION_REFRESH_MS = 10000;
let _affectionSig = "";

function sigOf(chars) {
  return (chars || []).map((c) => `${c.id}:${expOf(c)}:${c.affection ? c.affection.level : 1}`)
    .join("|");
}

setInterval(async () => {
  if (document.hidden) return;
  const v = $("view-mmt");
  if (!v || v.classList.contains("hidden")) return;
  const b = $("view-bond");
  if (b && !b.classList.contains("hidden")) return;          // 剧情中不刷
  const pl = $("mmt-profile-list"), cl = $("mmt-chat-list");
  const profVisible = pl && pl.offsetParent !== null;
  const chatVisible = cl && cl.offsetParent !== null;
  if (!profVisible && !chatVisible) return;
  try {
    const data = await (await fetch("/api/mmt/characters")).json();
    const sig = sigOf(data.characters || []);
    if (sig === _affectionSig) return;                        // 没变 → 不动
    _affectionSig = sig;
    if (profVisible) await loadProfile(); else await loadChatList();
  } catch (e) { /* 刷新失败静默（下次再来） */ }
}, AFFECTION_REFRESH_MS);

// ---------------------------------------------------------------------------
// 渲染辅助
// ---------------------------------------------------------------------------

function renderAvatar(wrap, c, sizeCls) {
  // 头像 = 后端给什么显示什么。avatar_type: portrait(该外观 GUI 头像, 如遥香的
  // collection.png) | png(diff 立绘兜底)。
  // 两者都圆形裁剪: .mmt-avatar 自带 border-radius 50% + object-fit cover,
  // 非方图（半身像 404x456）居中裁成方。
  const img = document.createElement("img");
  img.src = c.avatar;
  img.className = "mmt-avatar" + (c.avatar_type === "portrait" ? "" : " rounded");
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
    _affectionSig = sigOf(chars);        // 记签名（自动刷新据此判"变没变"）
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
    _affectionSig = sigOf(chars);
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

const POLL_MS = 1000;          // 轮询间隔（宽限窗口/空闲态）
//: ⑥-3b 生成期轮询间隔 —— 后端**逐条**落气泡（⑥-3a 流式交付），1s 轮询会把
//: 2~3 条并成一批，流式收益被吃掉一半（真机一轮 8 条短气泡）。
const POLL_MS_BUSY = 250;
const POLL_RESUME_GRACE_MS = 25 * 1000;   // VN 退出后继续轮询的宽限窗口

// ── 气泡节奏 = **CLI `LineBuffer` 的搭档 `TypingDelay` 同款**（`core/streaming.py`）──
// 后端从 ⑥-3a 起**逐条**落气泡，但真机一轮 8 条会在几百毫秒内到齐（她"想完一口气
// 写完"：日志 `mmt_stream_first ms=9718` / `mmt_turn ms=10108` ⇒ 8 条挤在最后 390ms）
// ⇒ 同帧涌出 = "爆开"。前端照 CLI 那一套逐条放（2026-10-07 用户裁决：
// *"按照 cli linebuffer 的同款逻辑"*）——**参数与"第一句怎么办"都照抄**:
//   `TypingDelay.for_bubble` = 每字 **60~120ms**（随机抖动）+ 气泡间停歇 **400ms**;
//   ⭐ **第一条不延迟**（CLI 原话: "TTFT 已经提供了自然等待" —— 她刚想完，
//      第一条等于刚打完就发出去；队列里还有没放完的则一律排队，**顺序铁律**）。
// ⚠️ 这些参数与那条"第一条"判据的实现都在 `typing.js`（`chunkTypingMs` / `planReveal`），
// 本文件只是调用方；端到端验收仍是 B 层那条"首个气泡早于整轮完成"的冒烟。
// ⚠️ 只作用于**新到**的气泡; 历史一次性渲染（`renderBubbles`）不走这条路。
//: 队列尾（时间戳）—— 上一批还在放就接到它后面（⚠️ 顺序铁律: 后到的批次不许插队）
let _revealUntil = 0;
//: 最近一次轮询看到的 running（队列收尾的定时器据此决定要不要收指示器）
let _pollRunning = false;
const _revealing = () => Date.now() < _revealUntil;
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
    _unlockBondEl(el);
    el.classList.remove("bond-entry", "clickable");
    el.classList.add("bond-done");
    el.removeAttribute("role");
    el.removeAttribute("tabindex");
    el.textContent = it.text || "已完成羁绊剧情";
  }
}

function _unlockBondEl(el) {
  if (el && el._bondClick) {
    el.removeEventListener("click", el._bondClick);
    delete el._bondClick;
  }
}

/** ⭐ 立刻锁掉所有**未完成**的入口粉泡（去掉点击能力）。
 *
 *  2026-09-20 用户: *"结束羁绊剧情后那个粉色气泡有小段延迟才消失，这个时间是足够
 *  手快的玩家直接重进，后果不堪设想"* —— 粉泡的完成翻转靠轮询（`applyBondDone`）,
 *  finish → 轮询到达之间有个窗口, 窗口里它还是可点的。
 *  `bond.js` 的 `finish(completed=true)` 在提交收尾**之前**调这个把窗口关掉;
 *  视觉翻转仍交给轮询（文案/样式以服务端为准）。
 *  **中途退出不调**（`completed=false`）——那种粉泡要保持可点, 再进 = 静默续章。
 */
window.mmtLockBondEntries = function () {
  for (const el of _bondEls.values()) {
    _unlockBondEl(el);
    el.classList.remove("clickable");
    el.classList.add("bond-locked");     // 视觉提示: 已在处理（不承诺"已完成"）
  }
};

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

// 渲染规则: 历史一次性批量渲染（fragment + 无动画 + 一次滚动, 避免逐个 append +
// N 个入场动画压渲染——"载入存档慢"的根因）；**新回复**由 `pollLoop` 逐条
// `renderBubble`（到达即渲染, 见那里的 ⑥-3b 注释）。
// 2026-09-27 删: `renderBubbles(bubbles, {stream:true})` 那一支 + `BUBBLE_GAP_MS`
// ——全仓零调用者的死代码（真节奏早已由后端逐条交付驱动）。
function renderBubbles(bubbles) {
  const box = $("mmt-bubbles");
  if (!box) return;
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

// 指示器**永远贴在末尾**（它就是"她正在打下一条"的位置）。
// ⛔ 2026-10-08 真机报障"粉色泡泡的渲染全乱掉了"的根因: 节奏化之后气泡是**延迟
//    append** 的, 而指示器是**立刻** append 在当时的末尾 ⇒ 之后到达的气泡会插到
//    它**下面** ⇒ 指示器卡在气泡上方（看着像乱序）。修法 = 每次上屏后把它移到末尾
//    （`appendChild` 移动节点会**重新触发**省略号弹跳动画 —— 正好是"每一条出现
//    之前都弹一次"）。
//    ⚠️ 只移动已存在的节点, **不新建**（她说完就该没有它; 该不该出现由
//    `showTyping()` / 轮询那两行判）。
function typingToTail() {
  const box = $("mmt-bubbles");
  const t = $("mmt-typing");
  if (box && t && box.lastElementChild !== t) box.appendChild(t);
}

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
  // ⑥-3b: 生成期用**快档**（250ms）——气泡是逐条落库的, 慢档会把它们攒成一批。
  // 进循环时通常刚发完消息（一定在跑）, 所以先按快档起; 每轮按 `running` 调整。
  let wait = POLL_MS_BUSY;
  while (_polling) {
    await sleep(wait);
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
    wait = data.running ? POLL_MS_BUSY : POLL_MS;   // ⑥-3b: 生成期快档
    _pollRunning = !!data.running;
    if (data.bubbles && data.bubbles.length) {
      _graceGotBubbles = true;       // 宽限窗口内已见新气泡 → 收尾话到了（见下）
      _lastSeq = data.last_seq;
      // 增量轮询: 跳过 player 气泡（sendMessage 已乐观渲染, 避免重复渲染;
      // 全量加载 openChat(since=0) 仍渲染 player——历史重建需要）
      // 节奏与"哪条什么时候上屏"由 `typing.js` 算（`planReveal` 里记着 2026-10-08 那个坑:
      // 判据必须是"本批第一条 + 队列空闲"这一个组合），这里只负责渲染与指示器。
      const plan = window.L2BTyping.planReveal(
        data.bubbles, { now: Date.now(), revealUntil: _revealUntil });
      for (const { item: b, delay } of plan.entries) {
        if (delay > 0) {
          setTimeout(() => {
            renderBubble(b);
            scrollBubbles();
            // 上屏之后把指示器移回末尾（她还在打 ⇒ 保持"正在输入…"; 详见 typingToTail）
            if (_pollRunning || _revealing()) { showTyping(); typingToTail(); }
          }, delay);
        } else {
          renderBubble(b);
          typingToTail();
        }
      }
      scrollBubbles();
      if (plan.totalMs > 0) {
        _revealUntil = plan.revealUntil;
        // 放完收指示器（若那时她还在生成, 让下面那行 showTyping 接管, 别来回闪）
        setTimeout(() => { if (!_pollRunning) hideTyping(); }, plan.totalMs);
      } else {
        hideTyping();
      }
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
        } else if (!_revealing()) {
          hideTyping();                       // 已到且放完: 静默等窗口耗尽
        }
        continue;
      }
      // ⭐ 队列还在逐条上屏就必须**继续轮询 + 保持"正在输入…"**（2026-10-08 真机
      //    报障"粉色泡泡的渲染全乱掉了"）: 节奏化之后气泡要放十几秒, 而后端
      //    `running=false` 在 ~2s 就到了 ⇒ 从这里直接收摊会让气泡**无声地**一条条
      //    冒出来（指示器早退了半个屏幕的时间）。
      if (_revealing()) {
        showTyping();
        typingToTail();
        continue;
      }
      hideTyping();
      _polling = false;
      break;
    }
    // ⚠️ 2026-09-20 真机报障（"触发羁绊剧情粉色气泡后, 底部还闪三个点"）:
    //    粉泡已上屏 = 轮到**玩家点击**进剧情, 此时不该再谎报"对方正在输入"
    //    （触发轮的尾巴 + **预热生成首场**还在跑, `running` 仍为 true → 原来必闪）。
    //    `_bondEls` = 未完成的入口气泡（翻转成 bond_done 时注销）—— 有它就静默。
    // 2026-10-07: 队列还在逐条上屏时 (`_revealing()`) 也要亮着 —— 那段正是"她在打
    //    下一条"（CLI 同款: 气泡之间的 "…"）。两个来源取或, 避免互相压掉来回闪。
    if (_bondEls.size === 0 && (data.running || _revealing())) showTyping();
    else hideTyping();
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
