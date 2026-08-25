// Live2Be 设置页（简略版）——读写 settings.toml 存档（引擎仍读 env, 后端调试用）
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
];

async function loadSettings() {
  try {
    const data = await (await fetch("/api/settings")).json();
    for (const [section, key, elId, masked] of FIELDS) {
      const val = (data[section] || {})[key] || "";
      $(elId).value = masked ? val : val;   // 打码值原样填入（POST 时识别"已设置 ****"不改）
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
    if (!val) continue;                       // 空 = 不变
    payload[section] = payload[section] || {};
    payload[section][key] = val;
  }
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  $("settings-msg").textContent = data.ok ? "已保存（引擎仍从 .env 读取, 存档生效待接入）" : "保存失败";
  $("settings-msg").classList.remove("hidden");
}

document.addEventListener("DOMContentLoaded", () => {
  loadSettings();
  $("btn-save-settings").addEventListener("click", saveSettings);
  $("btn-back-main").addEventListener("click", () => show("view-main"));
});
