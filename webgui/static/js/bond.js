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
  let seenEmo = -1;             // 已应用的 emo_version（异步标注补标感知）
  let player = null;            // SpinePlayer（无 spine 资产 → null, 纯文字）
  let playerMeta = null;        // /api/spine 元信息 {pack, emotions}
  let busy = false;             // 场景切换中（防双击）
  let lastText = "";            // 最近一次提交内容（生成失败重试用, 2026-09-02）
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
  // 点击推进制（2026-09-01 问题3）: typeState = "typing"（打字中, X 可补全, 左键无效）
  // / "waiting"（段完成, 左键推进下一段, X 无效）/ null（交互中）
  let typeState = null;
  // 当前立绘表情（段首同值不重播——AI 填同表情时立绘不闪）
  let curEmotion = "";

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
      // 纪念立绘（方案 A）: 每轮都同步（busy 也同步——图就绪随时淡入;
      // 图晚到: 进入纪念时黑屏+文字, 图就绪即静默淡入）
      syncMemorial(st);
      // 名字牌（官方: 名字 + 社团）——status 返回, 覆盖 enter 传入的兜底 name
      if (st.name) $("bond-name").textContent = st.name;
      if (st.club !== undefined) $("bond-club").textContent = st.club;
      if (st.busy) continue;
      // 生成失败（2026-09-02 可重试: 上一场保留在屏, 后端给 3 次机会）——
      // 失败提示 + 重试按钮重新提交同输入; closing 收尾已置 completed → 走渲染
      if (st.error && !st.completed) {
        showTurnError(st.error);
        return;
      }
      // 异步标注补标（两遍式 C）: emo_version 变化 → 已显示段落补切立绘表情
      // （不重置打字机——只切表情; 文本段落不动）。新场景渲染时同步版本,
      // 避免对旧段落误切（时序: round 优先, emo_version 次之）。
      if (st.scene && (!gotScene || st.round !== seenRound)) {
        gotScene = true;
        seenRound = st.round;
        seenEmo = (st.emo_version !== undefined) ? st.emo_version : -1;
        renderScene(st.scene);
        syncMemorial(st);          // 渲染后: 清普通背景（黑屏兜底）+ 隐藏立绘
      } else if (st.emo_version !== undefined && st.emo_version !== seenEmo) {
        seenEmo = st.emo_version;
        if (st.scene) applyEmotions(st.scene);
      }
      if (st.completed) return;                  // is_end 场景已渲染 → 等自动 finish
      if (!st.scene && st.error) return;
      return;                                    // 场景已取（或异常）→ 结束本轮轮询
    }
  }

  // 纪念立绘同步（方案 A）: in_memorial + memorial_img 就绪 → 淡入全屏图
  // （进入瞬间普通背景清空 = 黑屏兜底, 无加载 UI——图就绪静默淡入）;
  // 退出（in_memorial False）→ 淡出纪念层, 露出普通背景。
  // memorial 期间立绘隐藏（设计定稿: 纪念 = 图 + 文字, 无 spine/emotion/fx）。
  function syncMemorial(st) {
    const layer = $("bond-memorial");
    if (!layer) return;
    const stage = $("bond-stage");
    if (st.in_memorial && stage) stage.classList.add("hidden");   // 纪念无立绘
    if (st.in_memorial) {
      $("bond-bg").style.backgroundImage = "";                    // 黑屏兜底
      if (st.memorial_img && layer.dataset.src !== st.memorial_img) {
        layer.dataset.src = st.memorial_img;
        layer.style.backgroundImage = `url("${st.memorial_img}")`;
        layer.classList.add("on");                                // 静默淡入
      }
    } else if (layer.classList.contains("on")) {
      layer.classList.remove("on");                               // 淡出
      setTimeout(() => {                                          // 过渡后清空防误显
        if (!layer.classList.contains("on")) {
          layer.dataset.src = "";
          layer.style.backgroundImage = "";
        }
      }, 1200);
    }
  }

  // 异步标注补标: 场景已显示, emotion 就绪 → 对**当前显示段**补切立绘表情
  // （2026-09-01 替换式渲染: 对话窗只保留当前段——只补当前段; 同值不重播）
  function applyEmotions(scene) {
    if (!player) return;
    const paras = scene.paragraphs || [];
    const p = paras[typeSeg];
    if (p && p.emotion && p.emotion !== curEmotion) {
      player.setEmotion(p.emotion);
      curEmotion = p.emotion;
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
    // 2026-09-01 点击推进制: 打字中继续三角不亮——段完成时 paraDone 才亮
    // （提示"点击进入下一段"）; 交互期由 showInteraction 自行管理
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
    // 点击跳过 / 2.4s 自动继续（2026-09-01: 隐藏加淡出过渡——fade-out class）
    await new Promise((res) => {
      let done = false;
      const fin = () => {
        if (done) return;
        done = true;
        t.classList.add("fade-out");
        setTimeout(() => {
          t.classList.add("hidden");
          t.classList.remove("fade-out");
          v.classList.remove("title-active");
          // 名字牌恢复（is_end 时 renderScene 会再隐藏）
          document.querySelector(".bond-nameplate").classList.remove("hidden");
          res();
        }, 400);
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

  // 段完成统一收尾: 最后一段 → 场景交互; 否则停在段尾等左键/自动（2026-09-01）
  function paraDone() {
    typeTimer = null;
    typeState = "waiting";
    if (typeSeg >= typeParas.length - 1) {
      finishType();
    } else {
      showContinue();               // 提示"点击进入下一段"
      scheduleAutoPara();           // 自动模式: 3s 自动推进
    }
  }

  function writePara() {
    const p = typeParas[typeSeg];
    if (!p) { return finishType(); }
    // 替换式渲染（2026-09-01）: 对话窗只保留当前一句——前一句清空, 新段淡入
    typeBoxEl.innerHTML = "";
    // 段首切立绘表情（同值不重播——AI 填同表情时立绘保持, 不闪）
    if (player && p && p.emotion && p.emotion !== curEmotion) {
      player.setEmotion(p.emotion);
      curEmotion = p.emotion;
    }
    if (p && p.fx && p.fx.length) showFx(p.fx);
    const div = document.createElement("div");
    div.className = "bond-para";
    typeBoxEl.appendChild(div);
    const t = _paraText(p);
    let i = 0;
    typeState = "typing";
    const step = () => {
      if (i < t.length) {
        div.textContent = t.slice(0, i + 1);
        const ch = t[i];
        i++;
        const pause = /[，。！？…、；：—-]/.test(ch) ? typePunctMs : typeCharMs;
        typeTimer = setTimeout(step, pause);
      } else {
        paraDone();                  // 段完成 → 停段尾（不自动连播, 等左键/自动）
      }
    };
    step();
  }

  // 左键推进（2026-09-01）: 仅"waiting"（段渲染完成）有效——进入下一段
  // （清空重渲染 + 段首切差分）; 打字中左键 = 无操作（渲染完成是推进的前提）
  function advance() {
    if (typeState !== "waiting") return;
    hideContinue();
    typeSeg++;
    writePara();
  }

  // X 键补全（2026-09-01）: 仅"typing"（打字中）有效——取消打字机, 补齐当前段
  // 完整文字, 停在段尾（不推进、不重渲染、不变差分——那是左键的行为）;
  // 段渲染完成时按 X = 无操作
  function skipCurrent() {
    if (typeState !== "typing") return;
    const box = typeBoxEl;
    if (!box) return;
    if (typeTimer) { clearTimeout(typeTimer); typeTimer = null; }
    const p = typeParas[typeSeg];
    if (!p) return;
    const div = box.querySelector(".bond-para") || box.firstElementChild;
    if (div) div.textContent = _paraText(p);
    paraDone();
  }

  // 自动模式段级推进: 段完成 + autoOn → 3s 自动进入下一段（玩家介入取消）
  function scheduleAutoPara() {
    clearAutoTimer();
    autoTimer = setTimeout(() => {
      autoTimer = null;
      if (autoOn && typeState === "waiting") advance();
    }, 3000);
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
    typeState = null;                 // 交互中（点击推进制: 打字/等待都结束）
    if (cb) cb();
  }

  function stopTyping() {
    if (typeTimer) { clearTimeout(typeTimer); typeTimer = null; }
    typeBoxEl = null;
    typeOnDone = null;
  }

  // 继续三角（右下）: 段完成 = 推进下一段; is_end 段完成 = 点击收尾 finish;
  // 打字中点击 = 无操作（左键语义, 渲染完成是推进的前提——2026-09-01）
  function bindContinue() {
    $("bond-continue").addEventListener("click", () => {
      if (typeState === "typing") return;
      if (sceneIsEnd) finish();
      else advance();
    });
  }
  function showContinue() { $("bond-continue").classList.add("show"); $("bond-continue").setAttribute("aria-hidden", "false"); }
  function hideContinue() { $("bond-continue").classList.remove("show"); $("bond-continue").setAttribute("aria-hidden", "true"); }

  // ── 快速渲染（2026-09-01 问题3）: 仅 X 键——打字中补全当前段（停段尾）;
  // 空格/Enter 不绑定（以后再说）。左键推进见 onClick/advance。────────────
  // 交互元素（选项/自由输入/右上按钮/继续三角/标题面板）不触发——不冲突。

  function onKey(e) {
    if (menuOpen) return;               // 菜单打开时不响应（不冲突）
    if (e.key !== "x" && e.key !== "X") return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    e.preventDefault();
    skipCurrent();                      // 打字中补全; 段完成 = 无操作（函数内判断）
  }

  function onClick(e) {
    if (menuOpen) return;               // 菜单打开时点击不响应（菜单项已处理）
    if (e.target.closest(".bond-choice, .bond-topbtn, .bond-free, #bond-continue, #bond-title")) return;
    if (typeState === "typing") return; // 打字中左键没用（渲染完成是推进前提）
    if (sceneIsEnd) finish();
    else advance();
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
    lastText = text;              // 失败重试用（2026-09-02）
    clearAutoTimer();             // 推进 → 自动倒计时作废（防自动+手动双提交）
    stopTyping();
    let data;
    try {
      for (;;) {
        const res = await fetch("/api/bond/turn", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ char_id: charId, session_id: sessionId, text }),
        });
        data = await res.json();
        if (data.busy) {          // 生成中 / 情绪标注门控中（2026-09-02）→ 等待后自动重试
          if (!data.accepted) {   // 门控等待（标注未就绪）→ 显示等待点反馈
            $("bond-choices").innerHTML = "";
            $("bond-choices").appendChild(loadingDots());
          }
          await sleep(BOND_POLL_MS);
          continue;
        }
        if (!res.ok || !data.accepted) {
          showTurnError(data.detail || data.error || "剧情推进失败");
          busy = false;
          return;
        }
        break;
      }
    } catch (e) {
      showTurnError("网络错误: " + e.message);
      busy = false;
      return;
    }
    if (data.scene) {
      // 分支消费（板块契约）: turn 直接返回分支内容 → 零等待渲染, 不经轮询
      $("bond-text").innerHTML = "";
      $("bond-choices").innerHTML = "";
      hideContinue();
      renderScene(data.scene);
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
    // 纪念层清理（上次残留——淡出已完成的图/未淡出的状态）
    const mem = $("bond-memorial");
    if (mem) { mem.classList.remove("on"); mem.dataset.src = ""; mem.style.backgroundImage = ""; }
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

  // 生成失败 → 错误提示 + 重试按钮（2026-09-02: 偶发失败不再卡死/终结剧情;
  // 重试 = 重新提交最近一次输入, 后端重新走 LLM）
  function showTurnError(msg) {
    const box = $("bond-choices");
    box.innerHTML = "";
    const div = document.createElement("div");
    div.className = "bond-error";
    div.textContent = "（剧情生成失败: " + msg + "）";
    const btn = document.createElement("button");
    btn.className = "bond-choice bond-retry";
    btn.textContent = "↻ 重试";
    btn.addEventListener("click", () => {
      busy = false;
      submit(lastText);
    });
    box.appendChild(div);
    box.appendChild(btn);
  }

  bindContinue();
  bindTopbar();
  bindMenu();

  // ---------------------------------------------------------------------------

  return { enter, exit };
})();

window.BondVN = BondVN;
