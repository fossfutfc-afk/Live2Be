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
const END_HOLD_MS = 1600;       // 收尾场景停留后自动 finish

// 打字速度档位（菜单"打字速度"切换——逐字基准与标点停顿）
const SPEEDS = [
  { label: "慢", char: 70, punct: 240 },
  { label: "中", char: 42, punct: 150 },
  { label: "快", char: 22, punct: 80 },
];

// 特效符号表（fx 名 → 符号 + 颜色; 与后端 renderer/effects.py 的 fx 键一致）:
// 官方 BA 的"冒爱心/音符/惊叹"是 UI 层粒子——我们用 Unicode 符号 + CSS 浮动动画实现
// （零素材成本, 跨平台字体渲染; 符号可随时换 emoji/SVG, 映射只改这一处）。
const FX_SYMBOLS = {
  sparkle:  { sym: "✦", color: "#ffe9a8" },   // 开心闪光（白金色四角星）
  heart:    { sym: "♥", color: "#ff7aa2" },   // 爱心（官方粉心）
  notes:    { sym: "♪", color: "#bfe0ff" },   // 音符（官方蓝紫音符）
  bang:     { sym: "❗", color: "#ffd166" },   // 惊叹号
  anger:    { sym: "💢", color: "#ff8a8a" },   // 怒纹
  raindrop: { sym: "💧", color: "#9cc4ff" },   // 低落/泪滴
  sweat:    { sym: "💦", color: "#b8e2ff" },   // 汗
  blush:    { sym: "❥", color: "#ffb3c6" },   // 脸红（轻粉心; 主体脸红由立绘差分表达）
};

const BondVN = (() => {
  let charId = "", sessionId = "", name = "";
  let seenRound = 0;            // 已渲染的 round（status 幂等去重）
  let gotScene = false;         // 本轮 enter 是否已渲染过场景
  let player = null;            // SpinePlayer（无 spine 资产 → null, 纯文字）
  let playerMeta = null;        // /api/spine 元信息 {pack, emotions}
  let busy = false;             // 场景切换中（防双击）
  let finished = false;         // 已 finish（防重复收尾）
  let autoOn = false;           // 自动模式（右上"自动"按钮: 黄 = 开）
  let autoTimer = null;         // 自动推进倒计时（打字完 3s 自动下一段/自动选第 1 个选项; 玩家介入 → 取消）
  let menuOpen = false;         // 菜单面板打开中（打开时空格/点击不触发跳过）
  let speedIdx = 1;             // 打字速度档（0 慢 / 1 中 / 2 快）
  let typeCharMs = SPEEDS[1].char, typePunctMs = SPEEDS[1].punct;
  let historyLog = [];          // 对话记录（每场 {round, paras}——菜单"对话记录"）

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
    historyLog = [];
    speedIdx = 1; typeCharMs = SPEEDS[1].char; typePunctMs = SPEEDS[1].punct;
    setAuto(false);               // 重置自动模式
    toggleMenu(false);            // 重置菜单（含绑定守卫状态）
    bindSkip();                   // 空格/Enter/点空白 → 快速跳出整段文字
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
    clearAutoTimer();
    unbindSkip();
    setAuto(false);
    toggleMenu(false);
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
        // SpinePlayer 内部 ResizeObserver + fit 保证;
        // fitShift 0.15 = 官方构图（立绘完整大小居中, 整体下移 15% 屏高,
        // 小腿以下刻意移出屏幕外——不是放大裁切）
        player = await createSpinePlayer($("bond-stage"), playerMeta.pack, {
          emotionMap: playerMeta.emotions,
          autoFit: true,
          fitShift: 0.36,
          fitScale: 1.5,
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
    clearAutoTimer();             // 新场景开始 → 旧自动倒计时作废
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
    // 对话记录（菜单"对话记录"数据源）
    historyLog.push({ round: seenRound, paras: scene.paragraphs || [] });
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
        btn.addEventListener("click", () => {
          clearAutoTimer();              // 玩家手动选择 → 取消自动倒计时（不冲突）
          submit(c);
        });
        choiceBox.appendChild(btn);
      });
      // 自动模式: 打字完成后 3s 自动选第一个选项（玩家手动介入 → 取消）
      if (autoOn) scheduleAutoChoice(scene.choices);
    } else {
      // 纯叙事场（无选项）: "点击继续"推进——输入固定"（继续）", 后端 Storyloom
      // 式预生成已就绪 → 衔接零等待（2026-08-30 替代自由输入框: 纯叙事场不需要
      // 玩家打字, 读完全自动继续; 想自由发挥的场次由 LLM 给选项承载）
      const wrap = document.createElement("div");
      wrap.className = "bond-free";
      const btn = document.createElement("button");
      btn.className = "bond-continue-btn";       // 不与 #bond-continue（继续三角）撞名
      btn.textContent = "▼ 继续";
      btn.addEventListener("click", () => {
        clearAutoTimer();            // 玩家手动继续 → 取消自动倒计时（不冲突）
        submit("（继续）");
      });
      wrap.appendChild(btn);
      choiceBox.appendChild(wrap);
      // 自动模式: 3s 后自动继续（纯叙事场输入固定"（继续）"——不是伪造玩家话, 安全）
      if (autoOn) scheduleAutoContinue();
    }
  }

  // ── 自动模式（右上"自动"按钮: 黄 = 开）─────────────────────────────
  // 一段对话打字完成后 3s 自动推进（有选项 → 自动选第 1 个; is_end 走原自动兜底）。
  // 玩家手动操作（点选项/自由输入/跳过）优先——倒计时取消, 不冲突。

  function setAuto(on) {
    autoOn = !!on;
    const btn = document.querySelector("#bond-auto");
    if (btn) btn.classList.toggle("active", autoOn);
    if (!autoOn) clearAutoTimer();
    updateMenuLabels();           // 菜单打开时同步"自动播放"标签
  }

  function toggleAuto() {
    setAuto(!autoOn);
    if (autoOn) {
      // 已显示的选项立即进入 3s 自动选择（无需等下一场）
      const choiceBox = $("bond-choices");
      const btns = [...choiceBox.querySelectorAll(".bond-choice")];
      const texts = btns.map((b) => b.textContent);
      if (btns.length) scheduleAutoChoice(texts);
    }
  }

  function clearAutoTimer() {
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
  }

  function scheduleAutoChoice(choices) {
    clearAutoTimer();
    autoTimer = setTimeout(() => {
      autoTimer = null;
      if (choices && choices.length) submit(choices[0]);
    }, 3000);
  }

  // 纯叙事场自动继续（3s）——输入固定"（继续）", 不伪造玩家话（2026-08-30）
  function scheduleAutoContinue() {
    clearAutoTimer();
    autoTimer = setTimeout(() => {
      autoTimer = null;
      if (autoOn) submit("（继续）");
    }, 3000);
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
    // 段首切立绘表情（缺省 = 延续上一段, 静默）+ 触发情绪特效（立绘头顶浮现符号）
    if (player && p && p.emotion) player.setEmotion(p.emotion);
    if (p && p.fx && p.fx.length) showFx(p.fx);
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
        const pause = /[，。！？…、；：—-]/.test(ch) ? typePunctMs : typeCharMs;
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

  // 情绪特效: 立绘头顶浮现符号（官方 UI 层粒子——浮起 + 淡出 + 左右飘散）。
  // 布局: 特效层绝对定位在立绘舞台内; 符号随机散布在角色头顶上方区域。
  function showFx(fxList) {
    const stage = $("bond-stage");
    if (!stage) return;
    stage.querySelectorAll(".bond-fx").forEach((el) => el.remove());  // 旧特效清场
    const layer = document.createElement("div");
    layer.className = "bond-fx";
    fxList.forEach((name) => {
      const def = FX_SYMBOLS[name];
      if (!def) return;
      for (let k = 0; k < 2; k++) {
        const s = document.createElement("span");
        s.className = "bond-fx-sym";
        s.textContent = def.sym;
        s.style.color = def.color;
        s.style.left = (26 + Math.random() * 44) + "%";     // 头顶水平散布（角色居中）
        s.style.top = (6 + Math.random() * 16) + "%";       // 头顶上方高度
        s.style.fontSize = (1.1 + Math.random() * 0.6) + "rem";
        s.style.animationDelay = (Math.random() * 0.35).toFixed(2) + "s";
        layer.appendChild(s);
      }
    });
    stage.appendChild(layer);
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
    // 快速跳出（空格/Enter/点击空白/继续三角）: 补全所有段落立即显示 + 完成。
    // 注意: 先取 box 引用再清 timer——stopTyping() 会把 typeBoxEl 置 null,
    // 若先清再用 innerHTML 会 TypeError（2026-08-29 修复的顺序坑, 与 finishType 同款）。
    if (!typeBoxEl) return;
    const box = typeBoxEl;
    if (typeTimer) { clearTimeout(typeTimer); typeTimer = null; }
    box.innerHTML = "";
    typeParas.forEach((p) => {
      const div = document.createElement("div");
      div.className = "bond-para";
      div.textContent = _paraText(p);
      box.appendChild(div);
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

  // ── 快速跳出: 空格 / Enter / 点空白 → 整段文字立即显示（不逐字）──────────
  // 交互元素（选项/自由输入/右上按钮/继续三角/标题面板）不触发跳过——不冲突。
  // is_end 场景: 空格/Enter/点击 = 直接收尾 finish。

  function onKey(e) {
    if (menuOpen) return;               // 菜单打开时空格/Enter 不跳过（不冲突）
    if (e.key !== " " && e.key !== "Enter") return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    e.preventDefault();
    if (sceneIsEnd) finish();
    else skipType();
  }

  function onClick(e) {
    if (menuOpen) return;               // 菜单打开时点击不跳过（菜单项已处理）
    if (e.target.closest(".bond-choice, .bond-topbtn, .bond-free, #bond-continue, #bond-title")) return;
    if (sceneIsEnd) finish();
    else skipType();
  }

  function bindSkip() {
    window.addEventListener("keydown", onKey);
    $("view-bond").addEventListener("click", onClick);
  }

  function unbindSkip() {
    window.removeEventListener("keydown", onKey);
    $("view-bond").removeEventListener("click", onClick);
  }

  // ── 菜单（右上"菜单": 对话记录 / 打字速度 / 自动播放 / 结束剧情）─────────
  // 菜单打开时: 空格/Enter/点击空白不触发跳过（menuOpen 守卫, 不冲突）。

  function toggleMenu(open) {
    const m = $("bond-menu");
    menuOpen = !!open;
    if (open) {
      m.classList.remove("hidden");
      updateMenuLabels();
      showMenuMain();
    } else {
      m.classList.add("hidden");
    }
  }

  function showMenuMain() {
    $("bond-menu-main").classList.remove("hidden");
    $("bond-menu-history").classList.add("hidden");
  }

  function updateMenuLabels() {
    const autoItem = document.querySelector('.bond-menu-item[data-act="auto"]');
    if (autoItem) autoItem.textContent = "自动播放：" + (autoOn ? "开" : "关");
    const speedItem = document.querySelector('.bond-menu-item[data-act="speed"]');
    if (speedItem) speedItem.textContent = "打字速度：" + SPEEDS[speedIdx].label;
  }

  function applySpeed() {
    typeCharMs = SPEEDS[speedIdx].char;
    typePunctMs = SPEEDS[speedIdx].punct;
  }

  function renderHistory() {
    const list = $("bond-history-list");
    list.innerHTML = "";
    if (!historyLog.length) {
      list.textContent = "（暂无记录）";
    } else {
      historyLog.forEach((h, i) => {
        const text = h.paras
          .map((p) => (typeof p === "string" ? p : (p.text || "")))
          .filter(Boolean)
          .join("\n");
        const div = document.createElement("div");
        const inner = document.createElement("div");
        inner.textContent = text;
        div.innerHTML = `<div class="bond-history-round">— 第 ${i + 1} 场 —</div>`;
        div.appendChild(inner);
        list.appendChild(div);
      });
    }
    $("bond-menu-main").classList.add("hidden");
    $("bond-menu-history").classList.remove("hidden");
  }

  function onMenuAction(act) {
    switch (act) {
      case "history": renderHistory(); break;
      case "speed":
        speedIdx = (speedIdx + 1) % SPEEDS.length;
        applySpeed();
        updateMenuLabels();
        break;
      case "auto":
        setAuto(!autoOn);
        updateMenuLabels();
        break;
      case "end":
        toggleMenu(false);
        finish();                  // 完整收尾（事件流 vn_exit + wrapup + digest）
        break;
      case "back": showMenuMain(); break;
      case "close": default: toggleMenu(false); break;
    }
  }

  // 右上角: 自动（切换黄态）/ 菜单（面板）
  function bindTopbar() {
    const auto = document.getElementById("bond-auto");
    const menu = document.getElementById("bond-menubtn");
    if (auto) auto.addEventListener("click", toggleAuto);
    if (menu) menu.addEventListener("click", () => toggleMenu(true));
  }

  // 菜单面板内点击（事件委托）
  function bindMenu() {
    $("bond-menu").addEventListener("click", (e) => {
      const item = e.target.closest(".bond-menu-item");
      if (item) onMenuAction(item.dataset.act);
    });
  }

  async function submit(text) {
    if (busy) return;
    busy = true;
    clearAutoTimer();             // 推进 → 自动倒计时作废（防自动+手动双提交）
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
  bindTopbar();
  bindMenu();

  // ---------------------------------------------------------------------------

  return { enter, exit };
})();

window.BondVN = BondVN;
