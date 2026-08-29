// Live2Be 羁绊剧情 VN 视图 — 后端 /api/bond/* 状态机的浏览器消费端。
// 流程: mmt 轮询收到 bond_story → enter() → 轮询 status → 渲染场景（背景/立绘/
// 打字机/选项）→ 玩家裁决 → turn → 下一场 → is_end → finish → 回 MMT。
//
// 图片大小参数（审查重点, 2026-08-29）:
//   - SpinePlayer: resolution = devicePixelRatio（retina 清晰, autoDensity 保证 CSS 尺寸）;
//     fit('contain') 按骨骼 bounds 自适应容器（完整可见, 不裁切）
//   - 背景: CSS object-fit: cover 全屏铺满（不变形）
//   - 舞台: 立绘区 = 视图上部 62%（滚动/缩放全由 SpinePlayer.fit 管）; 文字区 = 下部
//   - 容器尺寸固定由 CSS 保证（避免 0×0; SpinePlayer 内部 ResizeObserver 跟随）
"use strict";

import { createSpinePlayer } from "./spine-player.js";

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const BOND_POLL_MS = 700;       // status 轮询间隔（LLM 秒级, 不用太快）
const PARA_GAP_MS = 320;        // 段落依次出现间隔
const END_HOLD_MS = 1600;       // 收尾场景停留后自动 finish

const BondVN = (() => {
  let charId = "", sessionId = "", name = "";
  let seenRound = 0;            // 已渲染的 round（status 幂等去重）
  let gotScene = false;         // 本轮 enter 是否已渲染过场景
  let player = null;            // SpinePlayer（无 spine 资产 → null, 纯文字）
  let playerMeta = null;        // /api/spine 元信息 {pack, emotions}
  let busy = false;             // 场景切换中（防双击）
  let finished = false;         // 已 finish（防重复收尾）

  // ---------------------------------------------------------------------------
  // 公开: 进入 VN（mmt.js 收到 bond_story 或重进 in_vn 会话时调用）
  // ---------------------------------------------------------------------------

  async function enter(cid, sid, nm) {
    charId = cid; sessionId = sid; name = nm;
    finished = false; busy = false; seenRound = 0; gotScene = false;
    // 换角色/重进: 销毁旧立绘（spine 包/情绪映射是 per 角色的——不重建会残留上一位）
    if (player) {
      try { player.destroy(); } catch (e) { /* 尽力而为 */ }
      player = null;
      playerMeta = null;
    }
    showView();
    await initSpine();
    try {
      const res = await fetch("/api/bond/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ char_id: charId, session_id: sessionId }),
      });
      const data = await res.json();
      if (!res.ok || !data.accepted) {
        throw new Error(data.detail || data.error || "进入剧情失败");
      }
    } catch (e) {
      showError("进入羁绊剧情失败: " + e.message);
      exit();                        // 失败 → 回 MMT（解锁 + 重启轮询）
      return;
    }
    await waitScene();
  }

  function exit() {
    // 回 MMT: 隐藏 VN 视图（聊天窗原样保留）→ 解锁输入 + 重启轮询（拉 wrapup 收尾话）
    $("view-bond").classList.add("hidden");
    if (window.MMT && typeof window.MMT.unlockChat === "function") {
      window.MMT.unlockChat();
      window.MMT.resumePolling();
    }
  }

  // ---------------------------------------------------------------------------
  // 初始化: SpinePlayer（懒建一次; /api/spine 404 = 无 spine 资产 → 纯文字）
  // ---------------------------------------------------------------------------

  async function initSpine() {
    try {
      const res = await fetch(`/api/spine/${charId}`);
      if (!res.ok) return;                       // 404: 无 spine → 纯文字
      playerMeta = await res.json();
      if (!player) {
        // 图片大小: resolution = devicePixelRatio（retina 清晰）; autoFit 由
        // SpinePlayer 内部 ResizeObserver + fit('contain') 保证完整可见
        player = await createSpinePlayer($("bond-stage"), playerMeta.pack, {
          emotionMap: playerMeta.emotions,
          autoFit: true,
          resolution: window.devicePixelRatio || 1,
        });
      }
    } catch (e) {
      console.warn("[bond] SpinePlayer 不可用, 本次 VN 纯文字:", e);
      player = null;
    }
  }

  // ---------------------------------------------------------------------------
  // 轮询 status → 场景就绪 → 渲染
  // ---------------------------------------------------------------------------

  async function waitScene() {
    for (;;) {
      await sleep(BOND_POLL_MS);
      let st;
      try {
        st = await (await fetch(
          `/api/bond/status?char_id=${charId}&session_id=${sessionId}`)).json();
      } catch (e) {
        showError("轮询失败: " + e.message);
        return;
      }
      if (st.busy) continue;
      if (st.error && !st.scene) {
        showError("剧情生成失败: " + st.error);
        return;
      }
      if (st.scene && (!gotScene || st.round !== seenRound)) {
        gotScene = true;
        seenRound = st.round;
        renderScene(st.scene);
      }
      if (st.completed) return;                  // is_end 场景已渲染 → 等自动 finish
      if (!st.scene && st.error) return;
      return;                                    // 场景已取（或异常）→ 结束本轮轮询
    }
  }

  // ---------------------------------------------------------------------------
  // 场景渲染: 背景 → 段落（打字机 + 立绘 emotion）→ 选项/自由输入/收尾
  // ---------------------------------------------------------------------------

  function renderScene(scene) {
    busy = false;
    // 背景（scene_id → background_url; 无 → 保持当前/默认黑）
    const bg = $("bond-bg");
    if (scene.background_url) {
      bg.style.backgroundImage = `url("${scene.background_url}")`;
    } else if (!scene.background) {
      bg.style.backgroundImage = "";
    }

    // 段落（依次出现; 每段显式 emotion → 立绘切换; 缺省 = 延续, 静默）
    const box = $("bond-text");
    box.innerHTML = "";
    const paras = scene.paragraphs || [];
    paras.forEach((p, i) => {
      const div = document.createElement("div");
      div.className = "bond-para";
      div.textContent = typeof p === "string" ? p : (p.text || "");
      div.style.animationDelay = `${i * PARA_GAP_MS}ms`;
      box.appendChild(div);
      if (player && p && p.emotion) player.setEmotion(p.emotion);
    });

    // 交互区: 选项 / 自由输入 / 收尾
    const choiceBox = $("bond-choices");
    choiceBox.innerHTML = "";
    if (scene.is_end) {
      const done = document.createElement("div");
      done.className = "bond-end";
      done.textContent = "── 羁绊剧情结束 ──";
      choiceBox.appendChild(done);
      setTimeout(() => finish(), END_HOLD_MS);
    } else if (scene.choices && scene.choices.length) {
      scene.choices.forEach((c) => {
        const btn = document.createElement("button");
        btn.className = "bond-choice";
        btn.textContent = c;
        btn.addEventListener("click", () => submit(c));
        choiceBox.appendChild(btn);
      });
    } else {
      // 自由输入推进
      const wrap = document.createElement("div");
      wrap.className = "bond-free";
      const input = document.createElement("input");
      input.type = "text";
      input.maxLength = 200;
      input.placeholder = "输入一句话推进剧情…（Enter 发送）";
      const btn = document.createElement("button");
      btn.textContent = "推进";
      const send = () => {
        const t = input.value.trim();
        if (t) submit(t);
      };
      btn.addEventListener("click", send);
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
      wrap.append(input, btn);
      choiceBox.appendChild(wrap);
      input.focus();
    }
  }

  async function submit(text) {
    if (busy) return;
    busy = true;
    try {
      const res = await fetch("/api/bond/turn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ char_id: charId, session_id: sessionId, text }),
      });
      const data = await res.json();
      if (!res.ok || !data.accepted) {
        showError(data.detail || data.error || "剧情推进失败");
        busy = false;
        return;
      }
    } catch (e) {
      showError("剧情推进失败（网络错误: " + e.message + "）");
      busy = false;
      return;
    }
    $("bond-text").innerHTML = "";
    $("bond-choices").innerHTML = "";
    $("bond-choices").appendChild(loadingDots());
    await waitScene();
  }

  async function finish() {
    if (finished) return;
    finished = true;
    try {
      await fetch("/api/bond/finish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ char_id: charId, session_id: sessionId }),
      });
    } catch (e) {
      console.warn("[bond] finish 失败（事件流可能不完整）:", e);
    }
    exit();
  }

  // ---------------------------------------------------------------------------
  // 视图 / 提示
  // ---------------------------------------------------------------------------

  function showView() {
    const v = $("view-bond");
    v.classList.remove("hidden");
    $("bond-name").textContent = name;
    $("bond-bg").style.backgroundImage = "";
    $("bond-text").innerHTML = "";
    $("bond-choices").innerHTML = "";
    // 舞台尺寸: CSS 固定（62% 视高）——fit 由 SpinePlayer 管; 强制一次 reflow
    // 防首帧 0×0（ResizeObserver 首帧可能缺失）
    const stage = $("bond-stage");
    if (stage && stage.clientWidth === 0) {
      stage.style.height = (window.innerHeight * 0.62) + "px";
    }
  }

  function loadingDots() {
    const d = document.createElement("div");
    d.className = "bond-loading";
    d.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    return d;
  }

  function showError(msg) {
    const box = $("bond-choices");
    const div = document.createElement("div");
    div.className = "bond-error";
    div.textContent = "（" + msg + "）";
    box.appendChild(div);
  }

  // ---------------------------------------------------------------------------

  return { enter, exit };
})();

window.BondVN = BondVN;
