// Live2Be 羁绊剧情 VN 视图 — 后端 /api/bond/* 状态机的浏览器消费端。
// 流程: mmt 轮询收到 bond_story → enter() → 轮询 status → 渲染场景（背景/立绘/
// 打字机文字/选项）→ 玩家裁决 → turn → 下一场 → is_end → finish → 回 MMT。
//
// 布局（对齐官方 bond story, 2026-08-29 视觉版对照）:
//   背景 cover 全屏 + 底部暗渐 → 立绘透明浮层(中央偏左) → 左下名字+社团+分隔线
//   → 下部对话文本(逐字打字机) + 选项 → 右上 自动/菜单 占位 → 右下 继续三角(跳过打字)。
//
// 图片大小参数:
//   - SpinePlayer: resolution = devicePixelRatio（retina 清晰, autoDensity 保证 CSS 尺寸）;
//     fit('contain') 按骨骼 bounds 自适应容器（完整可见, 不裁切）
//   - 背景: CSS object-fit: cover 全屏铺满（不变形）
//   - 立绘舞台: 左 56% 宽 × 上 88% 高（透明浮层中央偏左）; 容器尺寸由 CSS 固定,
//     防 0×0（SpinePlayer 内部 ResizeObserver 跟随）
"use strict";

import { createSpinePlayer } from "./spine-player.js";

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const BOND_POLL_MS = 700;       // status 轮询间隔（LLM 秒级, 不用太快）
const PARA_GAP_MS = 320;        // 段与段之间停顿
const CHAR_MS = 42;             // 打字机基准（每字）
const PUNCT_MS = 150;           // 标点停顿（，。！？…；：等）
const END_HOLD_MS = 1600;       // 收尾场景停留后自动 finish

const BondVN = (() => {
  let charId = "", sessionId = "", name = "";
  let seenRound = 0;            // 已渲染的 round（status 幂等去重）
  let gotScene = false;         // 本轮 enter 是否已渲染过场景
  let player = null;            // SpinePlayer（无 spine 资产 → null, 纯文字）
  let playerMeta = null;        // /api/spine 元信息 {pack, emotions}
  let busy = false;             // 场景切换中（防双击）
  let finished = false;         // 已 finish（防重复收尾）

  // 打字机状态（renderScene → typeOut → 打完 → showInteraction）
  let typeTimer = null;
  let typeParas = [];
  let typeSeg = 0;
  let typeOnDone = null;
  let typeBoxEl = null;
  let sceneIsEnd = false;           // 当前场景是否 is_end（continue 三角分派: 结束→finish）

  // ---------------------------------------------------------------------------
  // 公开: 进入 VN（mmt.js 收到 bond_story 或重进 in_vn 会话时调用）
  // ---------------------------------------------------------------------------

  async function enter(cid, sid, nm) {
    charId = cid; sessionId = sid; name = nm || cid;
    finished = false; busy = false; seenRound = 0; gotScene = false;
    // 换角色/重进: 销毁旧立绘（spine 包/情绪映射是 per 角色的——不重建会残留上一位）
    if (player) {
      try { player.destroy(); } catch (e) { /* 尽力而为 */ }
      player = null;
      playerMeta = null;
    }
    stopTyping();
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
    stopTyping();
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
  // 轮询 status → 场景就绪 → 渲染（status 附带 name/club → 名字牌）
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
      // 名字牌（官方: 名字 + 社团）——status 返回, 覆盖 enter 传入的兜底 name
      if (st.name) $("bond-name").textContent = st.name;
      if (st.club !== undefined) $("bond-club").textContent = st.club;
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
  // 场景渲染: 背景 → 打字机（逐字输出 + 段首切立绘表情）→ 打完 → 选项/输入/收尾
  // ---------------------------------------------------------------------------

  async function renderScene(scene) {
    busy = false;
    stopTyping();
    sceneIsEnd = !!scene.is_end;
    // 背景（scene_id → background_url; is_end 无背景 → 清空显示默认黑屏——官方结束样式）
    const bg = $("bond-bg");
    if (scene.background_url) {
      bg.style.backgroundImage = `url("${scene.background_url}")`;
    } else if (!scene.background) {
      bg.style.backgroundImage = "";
    }
    // 名字牌: is_end（旁白余韵, 无角色名）→ 隐藏
    const np = document.querySelector(".bond-nameplate");
    if (np) np.classList.toggle("hidden", !!scene.is_end);
    // 立绘: is_end 且无背景（黑屏余韵, 角色已离场）→ 隐藏; 否则显示
    const stage = $("bond-stage");
    if (stage) stage.classList.toggle("hidden", !!scene.is_end && !scene.background);

    const box = $("bond-text");
    const choiceBox = $("bond-choices");
    choiceBox.innerHTML = "";
    hideContinue();
    // 章节标题面板（可选: scene.title —— 如"预先应对"）→ 展示后进入逐字
    if (scene.title) {
      await showTitle(scene.title, scene.background_url);
    }
    typeOut(box, scene.paragraphs || [], () => {
      hideContinue();
      showInteraction(scene);
    });
    showContinue();                              // 打字中亮起 → 点击跳过
  }

  async function showTitle(title, bgUrl) {
    const t = $("bond-title");
    const v = $("view-bond");
    $("bond-title-text").textContent = title;
    // 模糊背景层用当前场景背景（或无背景 → 深色兜底）
    document.querySelector(".bond-title-bg").style.backgroundImage =
      bgUrl ? `url("${bgUrl}")` : "";
    t.classList.remove("hidden");
    // 官方标题屏: 隐藏名字牌 + 模糊背景/立绘（整个画面虚化, 只留中央标题条清晰）
    document.querySelector(".bond-nameplate").classList.add("hidden");
    v.classList.add("title-active");
    // 点击跳过 / 2.4s 自动继续
    await new Promise((res) => {
      let done = false;
      const fin = () => {
        if (done) return;
        done = true;
        t.classList.add("hidden");
        v.classList.remove("title-active");
        // 名字牌恢复（is_end 时 renderScene 会再隐藏）
        document.querySelector(".bond-nameplate").classList.remove("hidden");
        res();
      };
      t.addEventListener("click", fin, { once: true });
      setTimeout(fin, 2400);
    });
  }

  function showInteraction(scene) {
    const choiceBox = $("bond-choices");
    if (scene.is_end) {
      // 官方结束样式: 黑屏余韵——无"结束"横幅, 右下三角亮（点击 finish 或自动兜底）
      showContinue();
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

  // ---------------------------------------------------------------------------
  // 打字机: 逐字逐段（段首切 emotion）; 打完回调; 继续三角可补全跳过
  // ---------------------------------------------------------------------------

  function typeOut(box, paras, onDone) {
    stopTyping();
    box.innerHTML = "";
    typeParas = paras;
    typeSeg = 0;
    typeOnDone = onDone;
    typeBoxEl = box;
    writePara();
  }

  function _paraText(p) {
    return typeof p === "string" ? p : (p.text || "");
  }

  function writePara() {
    const p = typeParas[typeSeg];
    if (!p) { return finishType(); }
    // 段首切立绘表情（缺省 = 延续上一段, 静默）
    if (player && p && p.emotion) player.setEmotion(p.emotion);
    const div = document.createElement("div");
    div.className = "bond-para";
    typeBoxEl.appendChild(div);
    const t = _paraText(p);
    let i = 0;
    const step = () => {
      if (i < t.length) {
        div.textContent = t.slice(0, i + 1);
        const ch = t[i];
        i++;
        const pause = /[，。！？…、；：—-]/.test(ch) ? PUNCT_MS : CHAR_MS;
        typeTimer = setTimeout(step, pause);
      } else {
        // 段完成 → 停顿后下一段
        typeTimer = setTimeout(() => {
          typeSeg++;
          if (typeSeg < typeParas.length) writePara();
          else finishType();
        }, PARA_GAP_MS);
      }
    };
    step();
  }

  function finishType() {
    // 先取回调再清——stopTyping() 会把 typeOnDone 置 null, 若先清再读则 cb 恒为 null,
    // showInteraction（选项/收尾）永不触发。这是 2026-08-29 修复的顺序坑。
    const cb = typeOnDone;
    typeOnDone = null;
    stopTyping();
    if (cb) cb();
  }

  function skipType() {
    // 继续三角: 补全所有段落文本立即显示 + 完成（跳过剩余打字）
    if (!typeBoxEl) return;
    stopTyping();
    typeBoxEl.innerHTML = "";
    typeParas.forEach((p) => {
      const div = document.createElement("div");
      div.className = "bond-para";
      div.textContent = _paraText(p);
      typeBoxEl.appendChild(div);
      if (player && p && p.emotion) player.setEmotion(p.emotion);
    });
    typeSeg = typeParas.length;
    finishType();
  }

  function stopTyping() {
    if (typeTimer) { clearTimeout(typeTimer); typeTimer = null; }
    typeBoxEl = null;
    typeOnDone = null;
  }

  // 继续三角（右下）: 打字中 = 跳过打字; is_end = 点击收尾 finish
  function bindContinue() {
    $("bond-continue").addEventListener("click", () => {
      if (sceneIsEnd) finish();
      else skipType();
    });
  }
  function showContinue() { $("bond-continue").classList.add("show"); $("bond-continue").setAttribute("aria-hidden", "false"); }
  function hideContinue() { $("bond-continue").classList.remove("show"); $("bond-continue").setAttribute("aria-hidden", "true"); }

  async function submit(text) {
    if (busy) return;
    busy = true;
    stopTyping();
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
    hideContinue();
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
    $("bond-name").textContent = name;   // 兜底（status 会再覆盖 name/club）
    $("bond-bg").style.backgroundImage = "";
    $("bond-text").innerHTML = "";
    $("bond-choices").innerHTML = "";
    hideContinue();
    $("bond-title").classList.add("hidden");
    v.classList.remove("title-active");
    // 新场景默认显示名字牌（is_end 时 renderScene 隐藏）; 立绘默认显示
    const np = document.querySelector(".bond-nameplate");
    if (np) np.classList.remove("hidden");
    const stg = $("bond-stage");
    if (stg) stg.classList.remove("hidden");
    // 舞台尺寸: CSS 固定（左 56% × 上 88vh）——fit 由 SpinePlayer 管; 强制一次 reflow
    // 防首帧 0×0（ResizeObserver 首帧可能缺失）
    const stage = $("bond-stage");
    if (stage && stage.clientWidth === 0) {
      stage.style.height = (window.innerHeight * 0.88) + "px";
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

  bindContinue();

  // ---------------------------------------------------------------------------

  return { enter, exit };
})();

window.BondVN = BondVN;
