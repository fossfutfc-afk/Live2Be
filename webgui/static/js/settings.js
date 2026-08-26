// Live2Be 设置页（简略版）——读写 settings.toml（引擎非空字段优先, .env 兜底）
"use strict";

// 注意: 不重复声明 $ —— gui.js 已声明全局 const $（普通 script 共享全局作用域,
// 重复 const 声明会抛 SyntaxError 导致本文件不执行）

// 输入框 id 映射 → 配置路径（[section][key]）
const FIELDS = [
  ["llm", "api_key", "set-llm-key", true],      // 最后一个参数: 是否 password/打码字段
  ["llm", "base_url", "set-llm-base", false],
  ["llm", "model", "set-llm-model", false],
  ["image", "api_key", "set-img-key", true],
  ["image", "base_url", "set-img-base", false],
  ["image", "model", "set-img-model", false]
];

async function loadSettings() {
  try {
    const data = await (await fetch("/api/settings")).json();
    for (const [section, key, elId, masked] of FIELDS) {
      const val = (data[section] || {})[key] || "";
      const el = $(elId);
      if (masked) {
        // key 字段: 输入框留空 + placeholder 显示打码值（后端格式 "****last4",
        // 前面打星尾部可辨认——直接显示; 留空保存 = 不改 key）
        el.value = "";
        el.placeholder = val
          ? val + "（留空 = 保持不变）"
          : "未设置（留空 = 用 .env 的 key）";
      } else {
        el.value = val;
      }
    }
  } catch (e) {
    $("settings-msg").textContent = "设置加载失败: " + e;
    $("settings-msg").classList.remove("hidden");
  }
}

async function saveSettings() {
  const payload = {};
  for (const [section, key, elId] of FIELDS) {
    const val = $(elId).value.trim();
    if (!val) continue;                       // 空 = 不变（key 打码值不填输入框了）
    payload[section] = payload[section] || {};
    payload[section][key] = val;
  }
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  $("settings-msg").textContent = data.ok
    ? "已保存（立即生效——引擎按 settings.toml 非空字段优先）"
    : "保存失败";
  $("settings-msg").classList.remove("hidden");
  loadSettings();                             // 刷新打码显示（新 key 后 4 位）
}

document.addEventListener("DOMContentLoaded", () => {
  loadSettings();
  $("btn-save-settings").addEventListener("click", saveSettings);
  $("btn-back-main").addEventListener("click", () => show("view-main"));
});
