// Live2Be 主界面（M2: 三按钮——设置已接入视图, MMT/回放占位待实装）
"use strict";

function wireMenuButton(id, label, onClick) {
  const btn = document.getElementById(id);
  if (!btn) return;
  btn.addEventListener("click", onClick || (() => {
    alert(`${label}：建设中，后续版本实装`);
  }));
}

document.addEventListener("DOMContentLoaded", () => {
  wireMenuButton("btn-settings", "设置", () => show("view-settings"));
  wireMenuButton("btn-mmt", "手机MMT", () => show("view-mmt"));
  wireMenuButton("btn-playback", "回放");
});
