// Live2Be 主界面（M2: 三按钮占位, 功能未实现——M3 起逐个实装）
"use strict";

// 按钮 → 提示（占位）。功能实现时替换为视图切换/路由。
function wireMenuButton(id, label) {
  const btn = document.getElementById(id);
  if (!btn) return;
  btn.addEventListener("click", () => {
    alert(`${label}：建设中，后续版本实装`);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  wireMenuButton("btn-settings", "设置");
  wireMenuButton("btn-mmt", "手机MMT");
  wireMenuButton("btn-playback", "回放");
});
