// Live2Be MMT 界面（纯 UI——列表/头像/点选占位; 聊天逻辑后写）
"use strict";

// 注意: 不重复声明 $/show —— gui.js 已提供全局

async function loadMmtCharacters() {
  const list = $("mmt-list");
  try {
    const data = await (await fetch("/api/mmt/characters")).json();
    const chars = data.characters || [];
    if (!chars.length) {
      list.innerHTML = '<p class="mmt-loading">没有角色（需 assets/illustration/{id}/diff/*Idle* 头像）</p>';
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
        <span class="mmt-item-heart">❤<span class="val"></span></span>
      `;
      // 头像（png → img; webm → 静音循环 video 播放——遥香是 webm 动图）
      const wrap = item.querySelector(".mmt-avatar-wrap");
      if (c.avatar_type === "webm") {
        const v = document.createElement("video");
        v.src = c.avatar; v.muted = true; v.loop = true; v.autoplay = true;
        v.className = "mmt-avatar anim";
        wrap.appendChild(v);
      } else {
        const img = document.createElement("img");
        img.src = c.avatar; img.className = "mmt-avatar";
        wrap.appendChild(img);
      }
      item.addEventListener("click", () => selectMmtChar(c.id, c.name));
      list.appendChild(item);
    }
  } catch (e) {
    list.innerHTML = '<p class="mmt-loading">加载失败: ' + e + '</p>';
  }
}

function selectMmtChar(id, name) {
  document.querySelectorAll(".mmt-item").forEach((x) => x.classList.remove("selected"));
  const el = document.querySelector(`.mmt-item[data-id="${id}"]`);
  if (el) el.classList.add("selected");
  // 聊天区占位（逻辑后写: 连引擎、气泡、进 VN）
  $("mmt-chat").innerHTML = `
    <div class="mmt-chat-box">
      <h3>与 ${name} 的对话</h3>
      <p class="mmt-empty">（聊天逻辑建设中——M3 后续接入引擎）</p>
    </div>`;
}

document.addEventListener("DOMContentLoaded", () => {
  loadMmtCharacters();
  $("mmt-back").addEventListener("click", () => show("view-main"));
});
