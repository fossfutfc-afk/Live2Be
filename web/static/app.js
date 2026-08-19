"use strict";

// Live2Be IDE GUI 前端 — vanilla JS, 无构建链。
// 事件流: EventSource(/api/events?channel=ide) → data.kind 分发（见 DESIGN §6）。

// ---- DOM ----
const $ = (id) => document.getElementById(id);
const stream = $("stream");
const input = $("input");
const sendBtn = $("send");
const statusDot = $("status-dot");
const statusText = $("status-text");
const autoChk = $("auto-approve");
const autoDelayLabel = $("auto-delay-label");
const hint = $("hint");

let busy = false;
let pending = null;   // { approval_id, buttons: [], timer, note }

// ---- 小工具 ----
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setStatus(state, text) {
  statusDot.dataset.state = state;
  statusText.textContent = text;
}

function scrollBottom() {
  stream.scrollTop = stream.scrollHeight;
}

function appendBubble(text, who) {
  if (hint) hint.remove();
  const row = el("div", "bubble-row " + who);
  row.appendChild(el("div", "bubble", text));
  stream.appendChild(row);
  scrollBottom();
}

function appendStatus(text, cls) {
  stream.appendChild(el("div", "status-line " + (cls || "info"), text));
  scrollBottom();
}

// ---- busy 状态（DONE / ABORTED 事件恢复） ----
function setBusy(b) {
  busy = b;
  input.disabled = b;
  sendBtn.disabled = b;
  if (b) setStatus("busy", "运行中…");
}

// ---- 审批卡片 ----
function disableCard() {
  if (!pending) return;
  if (pending.timer) clearInterval(pending.timer);
  pending.buttons.forEach((btn) => { btn.disabled = true; });
  if (pending.note) pending.note.textContent = pending.note.dataset.done || "";
  pending = null;
}

async function decide(approvalId, decision) {
  if (!approvalId) return;
  try {
    const resp = await fetch("/api/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id: approvalId, decision }),
    });
    if (!resp.ok) {
      appendStatus("[审批失败] HTTP " + resp.status, "fail");
      return;
    }
    disableCard();
  } catch (e) {
    appendStatus("[审批失败] " + e, "fail");
  }
}

function showProposal(evt) {
  const d = evt.data || {};
  const card = el("div", "proposal");
  card.appendChild(el("div", "proposal-title", d.summary || "AI 提议"));

  const pre = el("pre", "diff");
  pre.textContent = d.diff || "(无 diff)";
  card.appendChild(pre);

  const note = el("div", "proposal-note");
  card.appendChild(note);

  const actions = el("div", "proposal-actions");
  const buttons = [];
  const make = (label, cls, decision) => {
    const b = el("button", cls, label);
    b.onclick = () => decide(pending ? pending.approval_id : null, decision);
    buttons.push(b);
    actions.appendChild(b);
  };
  make("✓ 批准", "btn-ok", "approve");
  make("✗ 拒绝", "btn-no", "reject");
  make("■ 中止", "btn-abort", "abort");
  card.appendChild(actions);

  // auto-approve 倒计时（纯展示; 真正批准由服务端窗口控制）
  let timer = null;
  if (autoChk.checked) {
    const delay = parseFloat(autoDelayLabel.textContent) || 2;
    note.textContent = delay + " 秒后自动批准…";
    note.dataset.done = "自动批准流程已结束";
    const start = Date.now();
    timer = setInterval(() => {
      const left = delay - (Date.now() - start) / 1000;
      if (left <= 0) {
        clearInterval(timer);
        note.textContent = "正在自动批准…";
      } else {
        note.textContent = left.toFixed(1) + " 秒后自动批准…";
      }
    }, 100);
  } else {
    note.textContent = "等待你的决定";
    note.dataset.done = "";
  }

  pending = { approval_id: evt.approval_id, buttons, timer, note };

  // 清掉上一张卡片（同轮理论只有一张 pending）
  stream.querySelectorAll(".proposal").forEach((n) => { if (n !== card) n.remove(); });
  stream.appendChild(card);
  scrollBottom();
}

// ---- 轻量提问（ASK_USER） ----
function showQuestion(evt) {
  const d = evt.data || {};
  const card = el("div", "proposal question");
  card.appendChild(el("div", "proposal-title", d.prompt || "确认"));

  const note = el("div", "proposal-note");
  card.appendChild(note);

  const actions = el("div", "proposal-actions");
  const buttons = [];
  const make = (label, cls, decision) => {
    const b = el("button", cls, label);
    b.onclick = () => decide(pending ? pending.approval_id : null, decision);
    buttons.push(b);
    actions.appendChild(b);
  };
  make("✓ 读取范例", "btn-ok", "approve");
  make("✗ 跳过", "btn-no", "reject");
  card.appendChild(actions);

  let timer = null;
  if (autoChk.checked) {
    const delay = parseFloat(autoDelayLabel.textContent) || 2;
    note.textContent = delay + " 秒后自动读取范例…";
    note.dataset.done = "自动决策流程已结束";
    const start = Date.now();
    timer = setInterval(() => {
      const left = delay - (Date.now() - start) / 1000;
      if (left <= 0) {
        clearInterval(timer);
        note.textContent = "正在自动决策…";
      } else {
        note.textContent = left.toFixed(1) + " 秒后自动读取范例…";
      }
    }, 100);
  } else {
    note.textContent = "等待你的决定";
    note.dataset.done = "";
  }

  pending = { approval_id: evt.approval_id, buttons, timer, note };
  stream.appendChild(card);
  scrollBottom();
}

// ---- 事件分发 ----
function handle(evt) {
  const k = evt.kind;
  const d = evt.data || {};
  switch (k) {
    case "THINKING":
      setStatus("busy", "思考中…");
      break;
    case "ASK_USER":
      showQuestion(evt);
      setStatus("approval", "等待决定");
      break;
    case "AI_MESSAGE":
      appendBubble(d.message, "ai");
      break;
    case "PENDING_APPROVAL":
      showProposal(evt);
      setStatus("approval", "等待审批");
      break;
    case "EXEC_RESULT":
      disableCard();
      appendStatus((d.ok ? "[已执行] " : "[执行失败] ") + d.message,
                   d.ok ? "ok" : "fail");
      break;
    case "DECISION":
      disableCard();
      appendStatus(d.choice === "reject" ? "[已拒绝]" : "[决策: " + d.choice + "]", "info");
      break;
    case "ABORTED":
      disableCard();
      appendStatus("[已中止本轮]", "warn");
      setBusy(false);
      setStatus("idle", "空闲");
      break;
    case "DONE":
      appendBubble(d.message, "ai");
      setBusy(false);
      setStatus("idle", "空闲");
      break;
    case "TOOL_START":
      appendStatus("[工具] " + (d.label || d.name) + " 运行中…", "info");
      break;
    case "TOOL_RESULT":
      appendStatus("[工具] " + (d.label || d.name) + " 已获取 " + d.chars + " 字符", "info");
      break;
    case "TOOL_ERROR":
      appendStatus("[工具失败] " + (d.label || d.name) + ": " + d.error, "fail");
      break;
    case "INVALID_ACTION":
    case "LLM_ERROR":
    case "PLAN_ERROR":
      appendStatus("[" + k + "] " + (d.error || (d.errors || []).join("; ")), "fail");
      break;
    case "COMMAND_RESULT":
      disableCard();
      if (d.text) {
        stream.appendChild(el("pre", "command-output", d.text));
        scrollBottom();
      }
      if (d.terminal) {
        setBusy(false);
        setStatus("idle", "空闲");
      }
      break;
    default:
      console.log("[event]", k, evt);
  }
}

// ---- 事件流 ----
const es = new EventSource("/api/events?channel=ide");
es.onopen = () => setStatus(busy ? "busy" : "idle", busy ? "运行中…" : "空闲");
es.onerror = () => setStatus("error", "连接断开, 重连中…");
es.onmessage = (msg) => {
  let evt;
  try { evt = JSON.parse(msg.data); } catch { return; }
  handle(evt);
};

// ---- /edit 多行粘贴弹窗 ----
function openPatchModal(original) {
  return new Promise((resolve) => {
    const overlay = el("div", "modal-overlay");
    const box = el("div", "modal");
    box.appendChild(el("div", "modal-title", "粘贴 YAML 补丁（/edit）"));
    const ta = el("textarea", "modal-textarea");
    ta.placeholder = "逐行输入, 如:\nSIG~age: 16\nclub: 格黑娜学园";
    box.appendChild(ta);
    const actions = el("div", "modal-actions");
    const ok = el("button", "btn-ok", "应用补丁");
    const cancel = el("button", "btn-no", "取消");
    ok.onclick = () => {
      overlay.remove();
      resolve(original + "\n" + ta.value.trim());
    };
    cancel.onclick = () => { overlay.remove(); resolve(null); };
    actions.appendChild(ok);
    actions.appendChild(cancel);
    box.appendChild(actions);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    ta.focus();
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ok.click();
      if (e.key === "Escape") cancel.click();
    });
  });
}

// ---- 发送 ----
async function sendTurn() {
  const text = input.value.trim();
  if (!text || busy) return;
  if (text === "/clear") {
    input.value = "";
    stream.innerHTML = "";
    return;
  }
  input.value = "";
  appendBubble(text, "user");
  setBusy(true);
  // /edit 无行内补丁（整条命令不含 ":"）→ 弹粘贴框, 组装成多行命令串
  let payload = text;
  if (/^\/edit\b/.test(text) && !text.includes(":")) {
    payload = await openPatchModal(text);
    if (payload === null) {
      setBusy(false);
      setStatus("idle", "空闲");
      return;
    }
  }
  try {
    const resp = await fetch("/api/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: payload }),
    });
    if (resp.status === 409) {
      appendStatus("[409] 上一轮还没结束", "warn");
      setBusy(false);
      return;
    }
    if (resp.status === 400) {
      appendStatus("[400] 消息不能为空", "warn");
      setBusy(false);
      return;
    }
    if (!resp.ok) {
      appendStatus("[HTTP " + resp.status + "] 提交失败", "fail");
      setBusy(false);
    }
    // 200 → busy 保持, 等 DONE/ABORTED 事件恢复
  } catch (e) {
    appendStatus("[提交失败] " + e, "fail");
    setBusy(false);
  }
}

sendBtn.onclick = sendTurn;
input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendTurn(); });

// 自动批准开关
autoChk.addEventListener("change", async () => {
  try {
    const resp = await fetch("/api/auto_approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: autoChk.checked }),
    });
    if (resp.ok) {
      const st = await resp.json();
      autoDelayLabel.textContent = st.auto_delay;
    } else {
      autoChk.checked = !autoChk.checked;
    }
  } catch {
    autoChk.checked = !autoChk.checked;
  }
});

// ---- 初始状态对齐 ----
(async function init() {
  try {
    const resp = await fetch("/api/status");
    const st = await resp.json();
    autoChk.checked = !!st.auto_approve;
    autoDelayLabel.textContent = st.auto_delay;
    setBusy(st.busy);
    if (st.busy) {
      appendStatus("[连接时上一轮仍在运行]", "warn");
    }
  } catch {
    setStatus("error", "无法连接服务");
  }
})();
