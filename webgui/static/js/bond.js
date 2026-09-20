// Live2Be 羁绊剧情 VN 视图 — 后端 /api/bond/* 状态机的浏览器消费端。
// 流程: mmt 轮询收到 bond_story → enter() → 轮询 status → 渲染场景（背景/立绘/
// 打字机文字/选项）→ 玩家裁决 → turn → 下一场 → is_end → finish → 回 MMT。
//
// 布局（对齐官方 bond story, 2026-08-29 视觉版对照）:
//   背景 cover 全屏 + 底部暗渐 → 立绘透明浮层(中央偏左) → 左下名字+社团+分隔线
//   → 下部对话文本(逐字打字机) + 选项 → 右上 自动/菜单 → 右下 继续三角(唯一推进提示)。
//   推进 = **点画面**（决策 #41: "▼ 继续"按钮已删）: 板内 → 下一段; 板读完 → 下一板。
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
const BOND_POLL_FAST_MS = 250;  // 首场等待期细粒度（P1: 预热/在途, 拿到首场后回粗）
const MAX_TURN_WAIT = 600;      // 推进忙等预算: 600×700ms = 7min（LLM 超时已提至 240s,
                                // 覆盖慢思考/标注长尾——超限给明确错误而非无限静默）
//: 推进忙等**软上限**（2026-09-11）: 90s 还没空闲就先回调用方去取屏上内容
//: （后端 busy/gate 看门狗已兜底放行）——真机"已等待 110s 不动"就是硬等到 7min
const TURN_SOFT_WAIT_MS = 90 * 1000;
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
  // 诊断开关（2026-09-08 实机问题排查）: URL 带 ?bondDebug=1 → console.debug 打印
  // 表情链路关键点（renderScene/writePara/applyEmotions/emoWatch）
  const DBG = new URLSearchParams(window.location.search).has("bondDebug");
  const dbg = (...a) => { if (DBG) console.debug("[bond]", ...a); };

  let charId = "", sessionId = "", name = "";
  let seenRound = 0;            // 已渲染的 round（status 幂等去重）
  let gotScene = false;         // 本轮 enter 是否已渲染过场景
  let seenEmo = -1;             // 已应用的 emo_version（异步标注补标感知）
//: 已渲染场景的**内容指纹**（2026-09-11）: round 会在生成开始时先 +1（此时
//: status.scene 还是上一场）——只按 round 判新旧会把旧场景重渲染一遍（真机
//: "继续轮又看到老师/打搅了"）。指纹一致 = 屏上没变 → 不重渲染。
let lastSceneKey = "";
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
  let waitCard = false;         // 等待标题卡显示中（enter → 首场就绪; 与 showTitle 互斥）

  // ── 回忆册只读回放（2026-09-12, DESIGN_COLLECTION_BOOK §4）─────────────
  // 与 live 的区别: **播完即停**——0 LLM、不发 turn/finish、不碰后端状态机。
  // 数据由 /api/collection/{char}/{from_seq} 一次给全（逐板 scene）, 这里只是喂给
  // 同一套渲染器（背景/立绘/打字机/选项锁定态全部复用 → 看到的 = 当时看到的）。
  let readonly = false;         // 只读模式: submit 短路成"下一板", finish 短路成"退出"
  let roQueue = [];             // 待播场景（后端按事件流序给）
  let roIndex = 0;              // 下一板下标
  let roExit = null;            // 退出回调（回角色页）

  // ── 推进机制（决策 #41, 2026-09-12）──────────────────────────────────
  // **没有"▼ 继续"按钮**: 推进 = 点画面（右下 ▾ 三角只是提示）——
  //   板内还有段 → 下一段; 板读完 → 下一板; is_end → 收尾。
  // 例外: 板上有**未裁决**的选项时点画面不推进（等玩家点选项）。
  let pendingChoice = false;    // 当前板有未裁决选项（点画面不推进）
  let curScene = null;          // 当前板（裁决后就地重画选项组, 不重播正文）

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
  // 表情守望（2026-09-07）: 骨架场景标注完成后补切表情——waitScene 只在轮询期
  // 触发 applyEmotions, 阅读期无轮询 → 需轻量守望（含后续未打字段落补 emotion/fx）
  let emoWatchTimer = null;
  // place 锚点背景（DESIGN_BOND_CONTRACT_V2 P3b-2）: 当前已应用的背景地点——
  // 锚点句（段落项带 place/place_bg）到达/打字经过时切背景; 晚到锚点即切（§7.2）
  let appliedPlace = null;

  // ---------------------------------------------------------------------------

  function setBg(url) {
    const bg = $("bond-bg");
    if (bg && url) bg.style.backgroundImage = `url("${url}")`;
  }
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
    clearEmoWatch();              // 进入: 旧守望清场（renderScene 按需重启）    // P1 入口预热: start POST 先行发出（首场可能已由触发轮预热或在途——生成
    // 立即继续, 不与 spine 初始化串行）; initSpine 与其并行, 首帧渲染前等它就绪
    let data;
    try {
      const res = await fetch("/api/bond/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ char_id: charId, session_id: sessionId }),
      });
      data = await res.json();
      if (!res.ok || !data.accepted) {
        throw new Error(data.detail || data.error || "进入剧情失败");
      }
    } catch (e) {
      showError("进入羁绊剧情失败: " + e.message);
      exit();                        // 失败 → 回 MMT（解锁 + 重启轮询）
      return;
    }
    // 2026-09-11: 立绘加载**不阻塞首屏**——真机"重进先黑屏一小段"有一半耗在
    // spine 包（skel/atlas/png）加载上; 文字先上屏, 立绘就绪后自行进画面
    // （writePara 每段都实时读 player, 后续段落/补切照常带表情）。
    initSpine().catch(() => { /* 无 spine → 纯文字降级（原语义） */ });
    // 等待标题卡（2026-09-05）: 首场在后台 LLM 生成（5s+ 波动）——进入即显示
    // 章节卡（chapter_title 文案 + "故事正在展开…"）掩盖缓冲; 首场就绪 → waitScene
    // 收卡进场景。
    // 2026-09-09: resumed（续玩/预热就绪）也展示章节标题——标题无论如何都要
    // 给玩家看到, 预热只是"不必等生成"（短面板 2.4s/点击跳过, 场景已就绪）。
    // 2026-09-11 真机修复（"重进中断剧情先黑屏还要加载一小段"）: `bond_start`
    // **已经带回就绪场景**时（回放/预热命中/adopt 就绪/续玩）——直接上屏:
    //   · 回放（data.replay）不播章节卡（玩家是接着中断处看, 重复播报反而怪）;
    //   · 其余在**场景自己的背景**上播章节卡（不再是纯黑底等 2.4s）。
    if (data.scene) {
      if (!data.replay) {
        await showTitle(data.chapter_title || "",
                        data.scene.background_url || "");
      }
      // 名字牌（名字 + 社团——随角色变动的两个字段）: 不走轮询的路径也要立刻正确
      if (data.name) $("bond-name").textContent = data.name;
      if (data.club !== undefined) $("bond-club").textContent = data.club;
      gotScene = true;
      seenRound = data.round !== undefined ? data.round : seenRound;
      seenEmo = data.emo_version !== undefined ? data.emo_version : seenEmo;
      renderScene(data.scene);
      // 纪念态也要一起同步（2026-09-12）: 直返场景**不走 waitScene**, 而纪念的
      // 立绘隐藏/背景清空/图淡入都在 `syncMemorial` 里——不同步就会看到"纪念板
      // 照常显示立绘 + 普通背景"（冒烟实测抓到）。状态由 `_ready_scene_payload` 带。
      syncMemorial(data);
      return;
    }
    if (data.completed) {
      await waitScene();
    } else if (data.resumed) {
      await showTitle(data.chapter_title || "", "");
      await waitScene();
    } else {
      showEnterWait(data.chapter_title || "");
      await waitScene();
    }
  }

  // 等待标题卡: bond-title 面板的"进场景缓冲"模式——持续显示（不自动过/点击不跳）
  // 直到 hideEnterWait; 与 showTitle（章节标题屏, 2.4s/点击跳过）互斥（waitCard 标记）。
  // 2026-09-07 修复: 曾引用未定义的 reason 变量（历史遗留）——busy adopt 路径
  // （不等预热直接点击 → resumed:False）进这里即 ReferenceError → enter 中断,
  // waitScene 永不启动 → 卡死。改回用后端返回的 chapterTitle 参数。
  function showEnterWait(chapterTitle) {
    const t = $("bond-title");
    const v = $("view-bond");
    const note = $("bond-title-note");
    const np = document.querySelector(".bond-nameplate");
    if (!t || !v) return;
    waitCard = true;
    // 标题文案: 取首句（后端返回的章节标题）; 无标题 → 通用兜底
    let title = (chapterTitle || "").trim();
    const cut = title.indexOf("。");
    if (cut > 0) title = title.slice(0, cut);
    $("bond-title-text").textContent = title || "羁绊剧情";
    if (note) note.classList.remove("hidden");
    t.classList.remove("hidden", "fade-out");
    if (np) np.classList.add("hidden");
    v.classList.add("title-active");
  }

  function hideEnterWait() {
    const t = $("bond-title");
    const v = $("view-bond");
    const note = $("bond-title-note");
    const np = document.querySelector(".bond-nameplate");
    if (!t || !v || !waitCard) return;
    waitCard = false;
    t.classList.add("hidden");
    t.classList.remove("fade-out");
    if (note) note.classList.add("hidden");
    if (np) np.classList.remove("hidden");
    v.classList.remove("title-active");
  }

  /** 收起 VN 视图 + 停掉所有定时器/绑定（live 与只读共用）。 */
  function _hideVn() {
    stopTyping();
    clearEmoWatch();              // 退出 VN: 守望停（防隐藏页空轮询）
    clearAutoTimer();
    unbindSkip();
    setAuto(false);
    toggleMenu(false);
    hideEnterWait();              // 防残留: 失败/中断路径收等待卡
    $("view-bond").classList.add("hidden");
  }

  function exit() {
    // 回 MMT: 隐藏 VN 视图（聊天窗原样保留）→ 解锁输入 + 重启轮询（拉 wrapup 收尾话）
    _hideVn();
    if (window.MMT && typeof window.MMT.unlockChat === "function") {
      window.MMT.unlockChat();
      window.MMT.resumePolling();
    }
  }

  // ---------------------------------------------------------------------------
  // 回忆册只读回放（DESIGN_COLLECTION_BOOK §4）
  //   ① enterReadonly: 一次性收下整章逐板数据 → 复用 live 渲染器逐板播
  //   ② 推进 = 本地下一板（submit/finish 在 readonly 下短路, 绝不发请求）
  //   ③ 播完 = "返回回忆册"（不写事件流、不改玩家当前进度）
  // ---------------------------------------------------------------------------

  async function enterReadonly(payload, onExit) {
    readonly = true;
    roExit = typeof onExit === "function" ? onExit : null;
    roQueue = (payload && payload.scenes) || [];
    roIndex = 0;
    charId = (payload && payload.char_id) || "";
    sessionId = "";                       // 只读: 不绑任何会话
    name = (payload && payload.name) || charId;
    finished = false; busy = false; gotScene = true; seenRound = 0; seenEmo = -1;
    historyLog = [];
    speedIdx = 1; typeCharMs = SPEEDS[1].char; typePunctMs = SPEEDS[1].punct;
    setAuto(false);
    toggleMenu(false);
    bindSkip();
    if (player) {                         // 换角色: 旧立绘必须销毁（spine 是 per 角色）
      try { player.destroy(); } catch (e) { /* 尽力而为 */ }
      player = null;
      playerMeta = null;
    }
    stopTyping();
    clearEmoWatch();
    syncMemorial({ in_memorial: false });   // 清掉上一场 live 可能留下的纪念层/隐藏立绘
    showView();
    if (payload && payload.name) $("bond-name").textContent = payload.name;
    if (payload && payload.club !== undefined) $("bond-club").textContent = payload.club;
    // 立绘不阻塞首屏（与 live 同策略）; 章标题屏给"翻开这一章"的仪式感（点击可跳过）
    initSpine().catch(() => { /* 无 spine → 纯文字 */ });
    await showTitle((payload && payload.title) || "", "");
    if (!roQueue.length) { roEnd(); return; }
    roNext();
  }

  /** 播下一板（只读推进的唯一入口）。
   *
   *  ⚠️ **必须跟着调 `syncMemorial`**（P1①, 2026-09-20）: 纪念的三件事（隐藏立绘 /
   *  清空普通背景 / 图淡入）全在那个函数里, 而它此前只在 live 的两条路径被调用
   *  ⇒ 册子回放里纪念板是"立绘照常 + 背景照常 + 图不出现", 与 live 差三处。
   *  载荷里的键与 live 同形（`in_memorial` / `memorial_img`, 由 chapters 派生）。
   */
  function roNext() {
    if (!readonly) return;
    if (roIndex >= roQueue.length) { roEnd(); return; }
    const item = roQueue[roIndex++];
    $("bond-text").innerHTML = "";
    $("bond-choices").innerHTML = "";
    hideContinue();
    const scene = item.scene || {};
    renderScene(scene);                   // 与 live 同一渲染器（背景/立绘/打字机/选项态）
    syncMemorial(scene);                  // 再套纪念态（顺序与 live 一致: 先渲后同步）
  }

  /** 播完: 出口按钮（**不是**"继续"——继续已删, 见决策 #41）。 */
  function roEnd() {
    const box = $("bond-choices");
    if (!box) return;
    box.innerHTML = "";
    hideContinue();
    syncMemorial({ in_memorial: false });   // 最后一块若在纪念里 → 淡出, 别把图挂在出口屏上
    const btn = document.createElement("button");
    btn.className = "bond-replay-exit";
    btn.textContent = "▸ 返回回忆册";
    btn.addEventListener("click", exitReadonly);
    box.appendChild(btn);
  }

  function exitReadonly() {
    const cb = roExit;
    readonly = false; roQueue = []; roIndex = 0; roExit = null;
    _hideVn();                            // 只收视图——**不碰 MMT**（册子不是从聊天进来的）
    $("bond-choices").innerHTML = "";
    $("bond-text").innerHTML = "";
    if (cb) cb();
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
    try {
      let gateSince = 0;              // 视觉门等待起点（首帧防卡死: 8s 超时降级放行）
      for (;;) {
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
        // 视觉门（2026-09-08 实机修复: 首板表情整板 nomal）——新场景上屏前等
        // emotion+place 双路就绪（标注 ~1-3s）: 否则替换式渲染错过即错过, 骨架期
        // 整板默认表情。gate_busy 期间 loading 卡（故事正在展开…）保持显示。
        // 8s 超时降级放行（宁缺勿错——标注兜底恒可达, 仅防御 worker 异常）。
        if (st.scene && st.gate_busy && (!gotScene || st.round !== seenRound)) {
          if (!gateSince) gateSince = performance.now();
          if (performance.now() - gateSince > 8000) {
            dbg("视觉门超时降级放行 round", st.round, "gate_ms",
                Math.round(performance.now() - gateSince));
            gateSince = 0;
          } else {
            await sleep(BOND_POLL_FAST_MS);
            continue;
          }
        }
        // 中断回放/预热在途: 有场景先渲染（busy 可能来自续写预生成, 不阻塞展示）;
        // 无场景才按 busy 轮询等待。
        // 2026-09-11 加**场景指纹去重**（真机"继续轮又看到老师/打搅了"）: 只按
        // round 判新旧不够——round 会在生成**开始**时就 +1, 此时 status.scene 还是
        // 上一场 → 前端把旧场景重渲染一遍（重读 + 残留名字行）。指纹一致即视为
        // "屏上内容没变" → 不重渲染, 继续等真正的新场景。
        if (st.scene && (!gotScene || st.round !== seenRound)
            && sceneKey(st.scene) !== lastSceneKey) {
          hideEnterWait();              // 首场就绪 → 收等待卡（scene.title 走 showTitle 接力）
          gotScene = true;
          seenRound = st.round;
          seenEmo = (st.emo_version !== undefined) ? st.emo_version : -1;
          renderScene(st.scene);
          syncMemorial(st);          // 渲染后: 清普通背景（黑屏兜底）+ 隐藏立绘
          if (st.completed) return;    // is_end 已渲染 → 结束轮询（等自动 finish）
          return;                      // 新场景已取 → 结束本轮轮询（busy 与否都收）
        }
        if (st.busy) {
          // P1: 首场等待（gotScene 前）用细粒度轮询——预热/在途时就绪立取;
          // 已进场景后回粗粒度（后续场生成秒级, 700ms 足够）
          await sleep(gotScene ? BOND_POLL_MS : BOND_POLL_FAST_MS);
          continue;
        }
        // 生成失败（2026-09-02 可重试: 上一场保留在屏, 后端给 3 次机会）——
        // 失败提示 + 重试按钮重新提交同输入; closing 收尾已置 completed → 走渲染
        if (st.error && !st.completed) {
          showTurnError(st.error);
          return;
        }
        // 异步标注补标（两遍式 C）: emo_version 变化 → 已显示段落补切立绘表情
        // （不重置打字机——只切表情; 文本段落不动）。新场景渲染时同步版本,
        // 避免对旧段落误切（时序: round 优先, emo_version 次之）。
        if (st.emo_version !== undefined && st.emo_version !== seenEmo) {
          dbg("emo 补切触发 round", seenRound, "emoVer", st.emo_version,
              "player?", !!player, "curSeg", typeSeg);
          seenEmo = st.emo_version;
          if (st.scene) applyEmotions(st.scene);
        }
        if (st.completed) return;                  // is_end 场景已渲染 → 等自动 finish
        if (!st.scene && st.error) return;
        return;                                    // 场景已取（或异常）→ 结束本轮轮询
      }
    } finally {
      // 2026-09-02: busy 残留 = 点击无反应——等待无论如何结束都解锁
      // （renderScene 已复位则无副作用; 失败/异常路径不再吞后续点击）
      busy = false;
    }
  }

  // 纪念立绘同步（方案 A）: in_memorial + memorial_img 就绪 → 淡入全屏图
  // （进入瞬间普通背景清空 = 黑屏兜底, 无加载 UI——图就绪静默淡入）;
  // 退出（in_memorial False）→ 淡出纪念层 + **把普通背景还回来**。
  // memorial 期间立绘隐藏（设计定稿: 纪念 = 图 + 文字, 无 spine/emotion/fx）。
  function syncMemorial(st) {
    const layer = $("bond-memorial");
    if (!layer) return;
    const stage = $("bond-stage");
    const bg = $("bond-bg");
    if (st.in_memorial && stage) stage.classList.add("hidden");   // 纪念无立绘
    if (st.in_memorial) {
      if (bg) bg.style.backgroundImage = "";                    // 黑屏兜底
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
      // ★ 恢复正常背景（2026-09-20, 用户要求）: 进入纪念时把 `bond-bg` 清空了,
      //   退出时若它还空着 → 按**当前这块板的** `background_url` 还回去。
      //   为什么用 curScene 而不是"记住进场前那张": 纪念窗口之后的那一板若本来就
      //   没有背景（收尾黑屏余韵 / `is_end`）, 就不该把上一张图糊回来。
      if (bg && !bg.style.backgroundImage && curScene && curScene.background_url) {
        bg.style.backgroundImage = `url("${curScene.background_url}")`;
      }
    }
  }

  // 异步标注补标: 场景已显示, emotion 就绪 → 对**当前显示段**补切立绘表情
  // （2026-09-01 替换式渲染: 对话窗只保留当前段——只补当前段; 同值不重播）
  function applyEmotions(scene) {
    dbg("applyEmotions t=", Math.round(performance.now()),
        "ver", seenEmo, "seg", typeSeg, "player?", !!player,
        "emotions", (scene.paragraphs || []).map((p) => (p && p.emotion) || "-"));
    // 标注/锚点回填（emotion/fx/place——player 缺失纯文字模式也要补切背景）
    patchTypeParas(scene);
    // place 晚到锚点（§7.2 晚到即切）: 已打字经过的段若含新锚点 → 立即切背景
    const upto = Math.min(typeSeg, (typeParas.length || 1) - 1);
    for (let i = 0; i <= upto; i++) applyPlaceForSeg(typeParas[i]);
    if (!player) return;
    const paras = scene.paragraphs || [];
    const p = paras[typeSeg];
    if (p && p.emotion && p.emotion !== curEmotion) {
      player.setEmotion(p.emotion);
      curEmotion = p.emotion;
    }
  }

  // 标注回填 → 把 emotion/fx/place 写进正在打字/待打的段落对象（typeParas 引用同一批）
  function patchTypeParas(scene) {
    const src = (scene && scene.paragraphs) || [];
    if (!Array.isArray(typeParas) || typeParas.length !== src.length) return;
    for (let i = 0; i < src.length; i++) {
      const a = typeParas[i], b = src[i];
      if (!a || !b || typeof a === "string") continue;
      if (b && b.emotion) a.emotion = b.emotion;
      if (b && b.fx) a.fx = b.fx;
      if (b && b.place) a.place = b.place;          // place 锚点（P3b-2）
      if (b && b.place_bg) a.place_bg = b.place_bg; // 背景资源随行
    }
  }

  // 段级背景锚点: 锚点句（place_bg 就绪）且地点与当前不同 → 切背景并记录。
  // 语义: 锚点句起进入新地点, 后续段落沿用, 直到下一锚点/场景结束。
  function applyPlaceForSeg(p) {
    if (!p || typeof p === "string") return;
    if (p.missing_asset) reportMissingAsset(p.missing_asset);   // 缺素材 → 黑屏 + 报出
    if (p.place_bg && p.place && p.place !== appliedPlace) {
      setBg(p.place_bg);
      appliedPlace = p.place;
    }
  }

  // ── 素材未找到（用户 2026-09-19 裁决: 黑屏 + alert/console.log 即可）──
  // 背景此时已经是 `black`（服务端给的占位）——这里只负责**让人看见**。
  // 每个 key 只 alert 一次（否则一板一句能把人弹疯）；console 每次都留痕。
  const _missingAssetSeen = new Set();
  function reportMissingAsset(info) {
    const key = (info && info.key) || "?";
    // 服务端能解释原因时用它的原话（PL6: "key 'X' 已改名为 'Y'"——比"素材未找到"
    // 有用得多: 直接告诉人该去改什么）; 解释不了才是笼统的"素材未找到"。
    const why = (info && info.message) ||
      `素材未找到: ${key}\n（背景已用黑屏占位；检查 assets/background 与地点表）`;
    console.error(`[place] ${why}` +
                  (info && info.scene_id ? ` scene_id=${info.scene_id}` : "") +
                  " → 黑屏占位");
    if (!_missingAssetSeen.has(key)) {
      _missingAssetSeen.add(key);
      alert(why);
    }
  }

  // 阅读期轻量轮询: 标注（emo_version）到达即补切; 场景推进/全标注稳定后自停
  function startEmoWatch(scene) {
    clearEmoWatch();
    if (readonly) return;        // 只读回放: 板是从事件流读的（标注早已回填）, 不轮询 status
    const paras = (scene && scene.paragraphs) || [];
    if (!paras.length || scene.is_end) return;
    if (paras.every((p) => p && p.emotion)) return;      // 已全标注 → 无需守望
    let stable = 0;
    emoWatchTimer = setInterval(async () => {
      if (emoWatchTimer == null) return;
      try {
        const st = await (await fetch(
          `/api/bond/status?char_id=${charId}&session_id=${sessionId}`)).json();
        dbg("watch tick round", st.round, "ver", st.emo_version, "gate",
            st.gate_busy, "anno", st.anno,
            "emotions", ((st.scene && st.scene.paragraphs) || []).map(
                (p) => (p && p.emotion) || "-"));
        if (st.round !== seenRound) { clearEmoWatch(); return; }  // 场景已推进
        if (st.scene && st.emo_version !== undefined && st.emo_version !== seenEmo) {
          dbg("emoWatch 版本变化 t=", Math.round(performance.now()),
              "ver", seenEmo, "→", st.emo_version,
              "paras", (st.scene.paragraphs || []).map(
                  (p) => (p && p.emotion) || "-"));
          seenEmo = st.emo_version;
          stable = 0;
          applyEmotions(st.scene);
        } else {
          stable++;
        }
        const allDone = st.scene && (st.scene.paragraphs || [])
          .every((p) => p && p.emotion);
        if (allDone && stable >= 2) clearEmoWatch();      // 标注完成且稳定 → 自停
      } catch (e) { /* 网络瞬断忽略——下轮重试 */ }
    }, 800);
    setTimeout(() => { if (emoWatchTimer != null) clearEmoWatch(); }, 30000);
  }

  function clearEmoWatch() {
    if (emoWatchTimer != null) { clearInterval(emoWatchTimer); emoWatchTimer = null; }
  }

  // ---------------------------------------------------------------------------
  // 场景渲染: 背景 → 打字机（逐字输出 + 段首切立绘表情）→ 打完 → 选项/输入/收尾
  // ---------------------------------------------------------------------------

  /** 场景指纹（内容判等）——轮询去重用: 相同内容绝不重渲染（防重读/残留名字行）。
   *  2026-09-11 真机"继续轮又看到老师+打搅了"就是这个重复渲染造成的。
   *  **不含 choices**（2026-09-12）: 裁决是"就地"发生的——`choices` 被清空时正文
   *  一字未变, 若把 choices 算进指纹, 裁决后的展示视图就会被当成**新场景** → 从头
   *  重播板正文。新场景一定伴随段落变化（且 round 先变）, 故去掉 choices 不影响
   *  "换板必重渲染"。 */
  function sceneKey(scene) {
    if (!scene) return "";
    const paras = (scene.paragraphs || [])
      .map((p) => `${(p && p.speaker) || ""}|${(p && p.text) || ""}`).join("␟");
    return `${paras}␟${scene.is_end ? 1 : 0}`;
  }

  async function renderScene(scene) {
    busy = false;
    curScene = scene;                 // 裁决后就地重画选项组（不重播正文）
    pendingChoice = false;            // 新板: 未裁决态由 showInteraction 按需置位
    lastSceneKey = sceneKey(scene);   // 记指纹: 轮询里同内容不再重渲染
    dbg("renderScene paras=", (scene.paragraphs || []).map(
        (p) => (p && p.emotion) || "-"), "is_end", !!scene.is_end);
    clearAutoTimer();             // 新场景开始 → 旧自动倒计时作废
    stopTyping();
    clearEmoWatch();              // 场景切换 → 旧守望作废（新场景按需重启）
    sceneIsEnd = !!scene.is_end;
    // 背景（scene_id → background_url; is_end 无背景 → 清空显示默认黑屏——官方结束样式）
    const bg = $("bond-bg");
    appliedPlace = null;              // 板级背景复位——锚点句到达才切换（P3b-2）
    if (scene.missing_asset) reportMissingAsset(scene.missing_asset);
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
    // 骨架场景（标注未就绪）→ 阅读期守望: 标注到达即补切表情/后续段
    startEmoWatch(scene);
    // 2026-09-01 点击推进制: 打字中继续三角不亮——段完成时 paraDone 才亮
    // （提示"点击进入下一段"）; 交互期由 showInteraction 自行管理
  }

  async function showTitle(title, bgUrl) {
    const t = $("bond-title");
    const v = $("view-bond");
    // 2026-09-09: 空标题兜底（缓存命中/resumed 等路径的章节名缺失时面板不空白）
    $("bond-title-text").textContent = (title || "").trim() || "羁绊剧情";
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

  /** 屏幕交互区: 板读完 → **不画按钮**, 亮右下三角（"点这里往下"）。
   *
   *  决策 #41（2026-09-12 作者口径）: **删掉"▼ 继续"按钮**——推进 = 点画面;
   *  三角加 `.ready` 标记"整板读完, 点了就进下一板"（板内的"下一段"不带它,
   *  冒烟/自动化据此区分"板内还有段"与"板读完"）。
   *  自动模式在这里排下一板（原来是按钮排的）。 */
  function showAdvance() {
    showContinue();
    const tri = $("bond-continue");
    if (tri) tri.classList.add("ready");
    if (autoOn) scheduleAutoContinue();
  }

  /** 画选项组（live 与只读回放共用）。
   *
   *  locked = 只读态（压暗 + 高亮 `picked`）: live 是"裁决之后", 回放是"全程"。
   *    · live 已裁决 → **disabled**: 点它等于用另一句再提交一次, 会改写历史, 绝不允许;
   *    · 只读回放 → **可点, 但只推进**（决策 #41: "毕竟都是一句话"——收敛链下两句
   *      通往同一后续, 所以让另一个选项也能点; 高亮仍留在当时选的那句 = 事实不变）。
   */
  function paintChoices(choices, picked, locked) {
    const box = $("bond-choices");
    box.innerHTML = "";
    choices.forEach((c) => {
      const on = !!picked && c === picked;
      const btn = document.createElement("button");
      btn.className = "bond-choice" + (locked ? " resolved" : "")
        + (on ? " picked" : "");
      btn.textContent = c;
      if (!locked) {
        btn.addEventListener("click", () => {
          clearAutoTimer();            // 玩家手动选择 → 取消自动倒计时（不冲突）
          submit(c);
        });
      } else if (readonly) {
        btn.title = on ? "（当时选了这句）" : "（点一下继续）";
        btn.addEventListener("click", () => {
          clearAutoTimer();
          goNext();                    // 只读: 本地下一板, 不发任何请求
        });
      } else {
        // ⚠️ 2026-09-20 真机报障（"还得点到选项**外面**才推进"）:
        //    原来这里是 `btn.disabled = true` —— 而 disabled 的按钮**吞掉点击**,
        //    同时 onClick 又把 `.bond-choice` 排除在推进之外 ⇒ 玩家点黄着的那句
        //    **毫无反应**, 只有点到别的画面才走。功能上"能继续", 但没人会那样点。
        //    现在: 禁用改**不回填** —— 点它 = 推进（与只读回放同一手;
        //    收敛链下两条选项通往同一后续, 决策 #41 "毕竟都是一句话"）。
        //    不会重提交: 这里绑的是 goNext()（发"（继续）"）, 不是 submit(原选项文本)。
        btn.title = on ? "（你选了这句——点一下继续）" : "（当时未选——点一下继续）";
        btn.addEventListener("click", () => {
          clearAutoTimer();
          goNext();
        });
      }
      box.appendChild(btn);
    });
  }

  function showInteraction(scene) {
    curScene = scene;
    pendingChoice = false;
    if (scene.is_end) {
      // 官方结束样式: 黑屏余韵——无"结束"横幅, 右下三角亮（点击 finish 或自动兜底）
      showContinue();
      const tri = $("bond-continue");
      if (tri) tri.classList.add("ready");
      setTimeout(() => finish(), END_HOLD_MS);
      return;
    }
    if (scene.choices && scene.choices.length) {
      // 已裁决的板（回放/续看, `picked` 由后端随场景带回）: 选项组画成只读态并高亮所选
      // ——否则"选哪个选项看起来都一样"（用户 2026-09-12 反馈）。裁决句永不上屏（决策 #37）。
      const locked = readonly || !!scene.picked;
      paintChoices(scene.choices, scene.picked || "", locked);
      if (locked) {
        showAdvance();                 // 读完这一段 → 点画面进下一板
      } else {
        pendingChoice = true;          // 未裁决: 点画面不推进, 等玩家点选项
        if (autoOn) scheduleAutoChoice(scene.choices);
      }
      return;
    }
    // 纯叙事板: 板读完 → 点画面推进（输入固定"（继续）", 后端预生成已就绪 → 零等待）
    showAdvance();
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

  /** 是否**不该**画正文区名字行（`.bond-speaker`）。
   *
   *  2026-09-11 真机两轮反馈后的定稿规则: 不画的两类 = ① 当前在屏角色（名字牌
   *  #bond-name/#bond-club 已经写明, 再画是重复）; ② **老师**（玩家自己选的那句
   *  ——用户两次报"红字老师是不明字段", 它只在"裁决物化"那个节点出现,
   *  因为那时屏上就是玩家选的话）。
   *  其余 speaker（未来多角色同场）照常画——那时名字行是必要的区分。
   *  比对前归一化空白（"伊草 遥香" / "伊草遥香" 视为同一人）。
   */
  function _isOnStageSpeaker(speakerName) {
    const norm = (s) => String(s || "").replace(/\s+/g, "");
    const s = norm(speakerName);
    if (!s) return false;
    if (s === "老师" || s === "sensei") return true;      // 玩家那句不画标签
    return s === norm(name) || s === norm($("bond-name").textContent);
  }

  function writePara() {
    const p = typeParas[typeSeg];
    if (!p) { return finishType(); }
    dbg("writePara seg", typeSeg, "emotion", p && (p.emotion || null),
        "player?", !!player, "cur", curEmotion);
    // 段级背景锚点: 本段起换场 → 段首切背景（P3b-2; 晚到锚点由 applyEmotions 补）
    applyPlaceForSeg(p);
    // 替换式渲染（2026-09-01）: 对话窗只保留当前一句——前一句清空, 新段淡入
    typeBoxEl.innerHTML = "";
    // 段首切立绘表情（同值不重播——AI 填同表情时立绘保持, 不闪）
    if (player && p && p.emotion && p.emotion !== curEmotion) {
      player.setEmotion(p.emotion);
      curEmotion = p.emotion;
    }
    if (p && p.fx && p.fx.length) showFx(p.fx);
    // 说话人名字行（记录流 v2）: 后端已把 speaker → 显示名映射好
    // （旁白为空串 → 不画名字行）。
    // 2026-09-11 真机反馈（用户: "红色的伊草遥香是不必要的"）: **在当前角色自己说话时
    // 不画**——左上名字牌（.bond-nameplate: 名字 + 社团）已经标明是谁在屏上, 再画一行
    // 同名的红字是重复; 只有"非当前角色"（老师/其他角色）才需要这行来区分。
    if (p && p.speaker_name && !_isOnStageSpeaker(p.speaker_name)) {
      const nm = document.createElement("div");
      nm.className = "bond-speaker";
      nm.textContent = p.speaker_name;
      typeBoxEl.appendChild(nm);
    }
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

  /** 还有没读完的段吗（is_end 板常常是多段——收尾那一板尤其） */
  function _moreParas() {
    return !!(typeParas && typeSeg < typeParas.length - 1);
  }

  /** 左键/继续三角的统一语义（2026-09-11 真机修复）。
   *
   *  **bug**: 原来写成 `if (sceneIsEnd) finish(); else advance();` —— 收尾板（is_end）
   *  只要点一下就**直接结束整章**, 于是"最后一板"里第 2 段之后的正文永远看不到
   *  （用户报"到最后一段只看到第一段 outburst 就退出 VN 了, 还以为是 AI 写得不好"）。
   *  is_end 的语义是"没有下一板", 不是"没有下一段"。
   *  **正确语义**: 先把本板读完（逐段推进）; 读到段尾才由 showInteraction 走收尾
   *  （`is_end` → 继续三角 + 1.6s 后自动 finish）。
   */
  function advanceOrFinish() {
    if (typeState === "typing") return;      // 打字中点击无操作（渲染完成是推进前提）
    if (_moreParas()) { advance(); return; } // 本板还有段 → 先读完
    if (sceneIsEnd) { finish(); return; }    // 段读完了且是收尾板 → 收尾
    if (pendingChoice) return;               // 未裁决的选项板: 等玩家点选项（点画面不推进）
    goNext();                                // 板读完 → 下一板（决策 #41: 点画面即推进）
  }

  /** 板读完 → 下一板: live 提交"（继续）"（后端预生成已就绪 → 零等待）;
   *  只读回放走本地队列（0 LLM, 不发任何请求）。 */
  function goNext() {
    if (readonly) { roNext(); return; }
    submit("（继续）");
  }

  // 继续三角（右下）: 段完成 = 推进下一段; 段读完且 is_end = 收尾 finish;
  // 打字中点击 = 无操作（左键语义, 渲染完成是推进的前提——2026-09-01）
  function bindContinue() {
    $("bond-continue").addEventListener("click", advanceOrFinish);
  }
  function showContinue() { $("bond-continue").classList.add("show"); $("bond-continue").setAttribute("aria-hidden", "false"); }
  function hideContinue() {
    const t = $("bond-continue");
    t.classList.remove("show");
    t.classList.remove("ready");      // .ready = "整板读完"（决策 #41）——收起时一并清
    t.setAttribute("aria-hidden", "true");
  }

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
    if (e.target.closest(".bond-choice, .bond-replay-exit, .bond-topbtn, #bond-continue, #bond-title")) return;
    advanceOrFinish();                  // 与继续三角同一语义（含 is_end 多段先读完）
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
    const endItem = document.querySelector('.bond-menu-item[data-act="end"]');
    if (endItem) endItem.textContent = readonly ? "退出回放" : "结束剧情";
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

  // 忙等反馈（2026-09-07）: busy/gate 期间显示等待点 + 拒因小字 + 经过秒数,
  // 不再每 700ms 狂发 turn——改轮询 status, 空闲后再补发一次（未接受的提交）
  function showWaitDots(msg) {
    $("bond-choices").innerHTML = "";
    const dots = loadingDots();
    $("bond-choices").appendChild(dots);
    if (msg) {
      const note = document.createElement("div");
      note.className = "bond-wait-note";
      note.id = "bond-wait-note";
      note.textContent = msg;
      $("bond-choices").appendChild(note);
    }
  }

  function updateWaitNote(secs, why) {
    const n = $("bond-wait-note");
    // 2026-09-11: 带上**卡在哪**（生成中/视觉门/预生成标注）——真机"已等待 110s"
    // 时前端只显示一个数字, 排查只能靠猜; 现在后端 status 的原因直接显示出来。
    if (n) n.textContent = `剧情推进中…（已等待 ${secs}s${why ? "·" + why : ""}）`;
  }

  // 轮询 status 直到空闲（生成 busy 与标注门控都过）; 预算耗尽 → timedOut。
  // 2026-09-11 加固: ① 显示卡在哪（busy/gate）; ② **软上限** SOFT（默认 90s）——
  // 到点不再死等, 回给调用方去 waitScene 取屏上内容（后端看门狗也会兜底放行）;
  // ③ 硬上限 MAX_TURN_WAIT 仍保留（极小概率的双卡死）。
  async function waitTurnIdle(tries) {
    const t0 = Date.now();
    for (;;) {
      if (++tries > MAX_TURN_WAIT) return { tries, timedOut: true };
      await sleep(BOND_POLL_MS);
      let st;
      try {
        st = await (await fetch(
          `/api/bond/status?char_id=${charId}&session_id=${sessionId}`)).json();
      } catch (e) { return { tries, timedOut: false }; }   // 网络抖动: 放行重试
      if (st.completed || (!st.busy && !st.gate_busy)) return { tries, timedOut: false };
      const secs = Math.round((Date.now() - t0) / 1000);
      // 卡在哪（2026-09-11）: 后端把两路拆开给了（busy_ms/gate_emo/gate_place/
      // pregen_wait）——文案直接写出来, 且 dbg 留一份现场, 下次报障不必再猜。
      const why = st.busy
        ? `生成中${st.busy_ms ? "·" + Math.round(st.busy_ms / 1000) + "s" : ""}`
        : (st.pregen_wait ? "下一板标注中"
           : (st.gate_emo === false ? "表情标注中" : "换场判定中"));
      if (secs > 0 && secs % 5 === 0) {
        updateWaitNote(secs, why);
        dbg("等待卡点", secs, "s", why, "round", st.round,
            "anno", st.anno || {}, "busy_ms", st.busy_ms);
      }
      if (Date.now() - t0 > TURN_SOFT_WAIT_MS) {
        dbg("推进忙等软超时放行", secs, "s why=", why);
        updateWaitNote(secs, why + "·先展示");
        return { tries, timedOut: false, soft: true };
      }
    }
  }

  async function submit(text) {
    // 回忆册只读回放: 推进 = 本地下一板。**绝不**发 turn（那会推进真实剧情/写事件流）
    if (readonly) { roNext(); return; }
    if (busy) return;
    busy = true;
    lastText = text;              // 失败重试用（2026-09-02）
    clearAutoTimer();             // 推进 → 自动倒计时作废（防自动+手动双提交）
    stopTyping();
    let data = null;
    let waiting = false;
    try {
      let tries = 0;
      for (;;) {
        if (!data || !data.busy) {
          // 空闲/首次 → 提交一次裁决（busy 期间不再重复提交）
          const res = await fetch("/api/bond/turn", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ char_id: charId, session_id: sessionId, text }),
          });
          data = await res.json();
        }
        if (data.busy) {
          // 生成中 / 情绪标注门控中（2026-09-02）→ 轮询 status 等空闲;
          // 已接受（生成在途）→ 等空闲后交 waitScene 取场景; 未接受 → 补发一次
          if (!waiting) {
            waiting = true;
            showWaitDots(data.error || "剧情推进中…");
          }
          const r = await waitTurnIdle(tries);
          tries = r.tries;
          if (r.timedOut) {
            showTurnError("剧情生成时间过长（可能是模型响应慢）——请点下方按钮重试");
            busy = false;
            return;
          }
          if (r.soft) {                  // 软超时（2026-09-11）: 别死等——去看屏上有什么
            data = { ...(data || {}), accepted: true };
            break;
          }
          if (data.accepted) break;      // 本次裁决已生效 → 交 waitScene 取场景
          data = null;                   // 被拒（busy/门控）→ 空闲后重发一次
          continue;
        }
        if (!data.accepted) {
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
    if (data.picked) {
      // 记录流 v2 裁决: **玩家的话语永远只体现为选项**（2026-09-12 用户核对 BA 后
      // 定稿）——正文停在上一句角色台词/旁白, 名字牌/立绘都不动。这里**绝不**碰
      // #bond-text、绝不 renderScene（那会把玩家那句当正文念出来, 真机报障:
      // "睦月/便利屋68 + 你还打算对我怎么恶作剧？"）。
      // 决策 #41（2026-09-12）: 选项组**留在屏上**转只读态 + 高亮所选（不再消失,
      // 也没有"▼ 继续"按钮）——点画面即进下一板。
      $("bond-choices").innerHTML = "";
      if (curScene && Array.isArray(curScene.choices) && curScene.choices.length) {
        paintChoices(curScene.choices, data.picked, true);
      }
      // ⚠️ 2026-09-20 修（真机报障: "选完选项变黄且不推进了"）:
      //    **裁决生效 = 这一板不再有"未裁决选项"** ⇒ 必须清掉 pendingChoice。
      //    它是 `advanceOrFinish` 的门闩（见 line ~996: `if (pendingChoice) return;`）,
      //    不清 → 点画面、点右下三角**全被吞掉**, 唯一能走的只剩"自动模式"。
      //    为什么以前没炸: 上面的 showInteraction 只在"未裁决"时置位,
      //    而裁决分支只重画了选项组、没管这个闩。
      pendingChoice = false;
      busy = false;
      hideContinue();
      showAdvance();
      return;
    }
    $("bond-text").innerHTML = "";
    $("bond-choices").innerHTML = "";
    hideContinue();
    $("bond-choices").appendChild(loadingDots());
    await waitScene();
  }

  async function finish() {
    if (readonly) { roEnd(); return; }   // 只读: 收尾 = 播完本板（不写 vn_exit/wrapup/digest）
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

  return { enter, exit, enterReadonly };
})();

window.BondVN = BondVN;
