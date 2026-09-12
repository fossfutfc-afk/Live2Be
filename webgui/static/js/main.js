// Live2Be 主界面（M2: 三按钮——设置/MMT/回忆册已接入视图）
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
  // 回放 = 回忆册（DESIGN_COLLECTION_BOOK）: 书页 → 角色页 → 只读回放
  wireMenuButton("btn-playback", "回放", () => {
    if (window.Book) window.Book.open();
    else alert("回忆册脚本未加载（检查 /static/js/collection.js）");
  });
});
