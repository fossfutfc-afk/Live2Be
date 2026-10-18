// Live2Be 素材页 —— 立绘与背景按需下载（首次运行向导）
// 后端: webgui/routers/packs.py；清单格式见 infra/packs.py
"use strict";

// 注意: 不重复声明 $ / show —— gui.js 已声明（普通 script 共享全局作用域）

const PACK_STATE_TEXT = { installed: "已安装", partial: "部分", missing: "未安装" };
const PACK_STAGE_TEXT = {
  starting: "准备中", downloading: "下载中", verifying: "校验中",
  extracting: "解压中", done: "完成", error: "失败",
  finished: "已完成", failed: "有失败", cancelled: "已取消"
};

let _packs = null;
let _pollTimer = null;

function fmtMB(bytes) {
  return (bytes / 1048576).toFixed(1) + " MB";
}

function _msg(text) {
  const el = $("packs-msg");
  el.textContent = text || "";
  el.classList.toggle("hidden", !text);
}

function renderPacks(packs) {
  const list = $("packs-list");
  list.textContent = "";
  let groups = [];
  for (const p of packs) {
    if (!groups.includes(p.group)) groups.push(p.group);
  }
  for (const group of groups) {
    const head = document.createElement("h3");
    head.textContent = group;
    list.append(head);
    for (const p of packs.filter((x) => x.group === group)) {
      const row = document.createElement("label");
      row.className = "check pack-row";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.dataset.pack = p.id;
      box.checked = p.state !== "installed";
      const num = document.createElement("span");
      num.className = "pack-num";
      // "缺 N/M" 比"部分"准: 最小包里随包带了一份 emotions.yml, 从没装过的包也会 present=1
      const stateText = p.state === "partial"
        ? `缺 ${p.total - p.present}/${p.total}` : PACK_STATE_TEXT[p.state];
      num.textContent = `${fmtMB(p.zip_bytes)} · ${p.file_count} 件 · ${stateText}`;
      row.append(box, document.createTextNode(" " + p.title + " "), num);
      list.append(row);
    }
  }
  updateSummary();
}

function _checkedIds() {
  return [...document.querySelectorAll("#packs-list input[data-pack]")]
    .filter((b) => b.checked).map((b) => b.dataset.pack);
}

function updateSummary() {
  const packs = (_packs && _packs.packs) || [];
  const summary = $("packs-summary");
  if (!packs.length) { summary.textContent = "这里还没有可装的包。"; return; }
  const ids = _checkedIds();
  const picked = packs.filter((p) => ids.includes(p.id));
  const need = picked.reduce((n, p) => n + p.zip_bytes, 0);
  const missing = packs.filter((p) => p.state === "missing").length;
  summary.textContent = `共 ${packs.length} 个包 · ${missing} 个还没装 · ` +
    `这次挑了 ${picked.length} 个（要下 ${fmtMB(need)}）`;
}

async function loadPacks() {
  _msg("");
  const list = $("packs-list");
  list.textContent = "读取中…";
  let data = null;
  try {
    data = await (await fetch("/api/packs")).json();
  } catch (e) {
    $("packs-summary").textContent = "读不到后端（服务没起？）";
    list.textContent = "";
    return;
  }
  _packs = data;
  $("packs-url").value = data.manifest_url || "";
  $("packs-proxy").value = data.proxy || "";
  if (!data.configured) {
    $("packs-summary").textContent = "还没配素材源 —— 填上面的清单地址再点保存。";
    list.textContent = "";
    return;
  }
  if (data.error) {
    $("packs-summary").textContent = "清单读不到";
    _msg(data.error);
    list.textContent = "";
    return;
  }
  if (!(data.packs || []).length) {
    $("packs-summary").textContent = "清单是空的。";
    list.textContent = "";
    return;
  }
  renderPacks(data.packs);
}

// 三个 POST 都要口令（`/api/menu` 下发, gui.js 暴露成 window.l2bToken）
function _token() {
  return (window.l2bToken && window.l2bToken()) || "";
}

async function saveSource() {
  _msg("");
  const body = {
    manifest_url: $("packs-url").value.trim(),
    proxy: $("packs-proxy").value.trim(),
    token: _token()
  };
  const res = await fetch("/api/packs/source", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  }).catch(() => null);
  if (!res || !res.ok) { _msg("保存失败（后端没响应，或口令不对）"); return; }
  await loadPacks();
}

function _bar(ratio) {
  $("packs-bar").classList.remove("hidden");
  $("packs-bar-fill").style.width = Math.max(0, Math.min(1, ratio)) * 100 + "%";
}

function _stopPoll() {
  clearInterval(_pollTimer);
  _pollTimer = null;
  $("btn-packs-cancel").classList.add("hidden");
}

async function _tick() {
  let st = null;
  try { st = await (await fetch("/api/packs/progress")).json(); } catch (e) { return; }
  const total = st.ids ? st.ids.length : 0;
  const doneCount = (st.done || []).length;
  const label = PACK_STAGE_TEXT[st.stage] || st.stage || "";
  if (st.running) {
    const frac = st.total ? st.received / st.total : 0;
    _bar((doneCount + frac) / Math.max(1, total));
    const cur = (st.pack_id || "").split(".").slice(-1)[0];
    $("packs-summary").textContent =
      `${label} ${doneCount + 1}/${total} · ${cur} · ${fmtMB(st.received)}` +
      (st.total ? " / " + fmtMB(st.total) : "");
    return;
  }
  _stopPoll();
  $("btn-packs-install").disabled = false;
  const failed = (st.done || []).filter((d) => !d.ok);
  if (st.stage === "cancelled") {
    _msg("已取消 —— 当前这个包作废，之前装好的不动。");
  } else if (failed.length) {
    _msg("有 " + failed.length + " 个包失败：" +
      failed.map((d) => d.pack_id + "（" + d.error + "）").join("；"));
  } else {
    _msg("");
    _bar(1);
  }
  await loadPacks();
}

async function installPacks() {
  const ids = _checkedIds();
  if (!ids.length) { _msg("先挑几个包。"); return; }
  _msg("");
  $("btn-packs-install").disabled = true;
  const res = await fetch("/api/packs/install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids: ids, token: _token() })
  }).catch(() => null);
  if (!res || !res.ok) {
    $("btn-packs-install").disabled = false;
    const data = res ? await res.json().catch(() => null) : null;
    _msg("起不来：" + ((data && data.detail) || "后端没响应"));
    return;
  }
  $("btn-packs-cancel").classList.remove("hidden");
  _bar(0);
  _pollTimer = setInterval(_tick, 500);
}

async function cancelPacks() {
  await fetch("/api/packs/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: _token() })
  }).catch(() => null);
}

document.addEventListener("DOMContentLoaded", () => {
  $("packs-list").addEventListener("change", updateSummary);
  $("btn-packs-save").addEventListener("click", saveSource);
  $("btn-packs-all").addEventListener("click", () => {
    document.querySelectorAll("#packs-list input[data-pack]").forEach((b) => { b.checked = true; });
    updateSummary();
  });
  $("btn-packs-none").addEventListener("click", () => {
    document.querySelectorAll("#packs-list input[data-pack]").forEach((b) => { b.checked = false; });
    updateSummary();
  });
  $("btn-packs-install").addEventListener("click", installPacks);
  $("btn-packs-cancel").addEventListener("click", cancelPacks);
  $("btn-packs-back").addEventListener("click", () => show("view-main"));
});

// main.js 切到本视图时调它（避免登录就拉一次远端清单）
window.Packs = { refresh: loadPacks };
