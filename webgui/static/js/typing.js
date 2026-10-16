// typing.js —— 逐字浮现的节奏：参数 + 计算 + 一个"顺序揭示队列"。
//
// 为什么要单独一个文件: 网页这一侧原本有两套节奏计算（VN 的 `SPEEDS` 打字机、MMT 的
// `chunkTypingMs` 气泡时长），加上终端那份 `tui/cli.py:PARA_CHAR_MS` 共三处；
// 2026-10-08 在 MMT 那边踩过一次坑（"本批第一条 + 队列空闲"判错 ⇒ 整批延迟恒为 0 ⇒
// 节奏彻底消失），那段记账逻辑现在住在这里、并有 `tests/webgui/js/typing.test.js` 钉住。
//
// ⚠️ 与终端那份**不强行同源**: 浏览器和终端的手感可以不同。这里是网页侧的唯一实现。
//
// 为什么不是 ESM: `mmt.js` / `gui.js` 等都是经典脚本（index.html 里没写 type=module），
// `import` 用不了 ⇒ 挂全局 `window.L2BTyping`。bond.js 虽是模块，读全局一样能用。
(() => {
  "use strict";

  // ── VN 打字机的速度档（bond.js 的速度菜单按它切换）────────────────────────
  const SPEEDS = [
    { label: "慢", char: 70, punct: 240 },
    { label: "中", char: 42, punct: 150 },
    { label: "快", char: 22, punct: 80 },
  ];

  //: 这些字符停顿更久（VN 正文）
  const PUNCT_RE = /[，。！？…、；：—-]/;

  /** 一个字符该停多久（标点用 punctMs，其余用 charMs）。 */
  function charPause(ch, charMs, punctMs) {
    return PUNCT_RE.test(ch) ? punctMs : charMs;
  }

  // ── MMT 气泡时长 ─────────────────────────────────────────────────────────
  // ⚠️ 这三个数连带两条约定，别单独改（2026-10-08 的产物）:
  //   ① 只作用于**新到**的气泡（历史一次性渲染走 renderBubbles，不经过这里）
  //   ② **队列空闲时第一条不延迟** —— B 层冒烟守的是"首个气泡早于整轮完成"
  const TYPING_MS_PER_CHAR_MIN = 60; // ← mmt.js 的 `_CHAR_DELAY_MIN`
  const TYPING_MS_PER_CHAR_MAX = 120; // ← `_CHAR_DELAY_MAX`
  const TYPING_MS_PAUSE = 400; // ← `_BUBBLE_PAUSE`

  /** 一个气泡要"打"多久（每字 60~120ms + 收尾 400ms）。 */
  function chunkTypingMs(text) {
    const per = TYPING_MS_PER_CHAR_MIN
      + Math.random() * (TYPING_MS_PER_CHAR_MAX - TYPING_MS_PER_CHAR_MIN);
    return Math.round(String(text || "").length * per + TYPING_MS_PAUSE);
  }

  /**
   * 顺序揭示队列：给定这一批 `items` 与当前队列尾，算出每条什么时候上屏。
   *
   * @param items 形如 `[{side, text}]`（side: "player" / "char" / 其它）
   * @param opts  `{now, revealUntil}`
   * @returns `{entries: [{item, delay}], revealUntil, totalMs}`
   *          delay 相对 now；revealUntil 是绝对时间戳；totalMs 是这批放完还要多久。
   *
   * 五条规则（都是踩出来的）:
   *   · `player` 气泡跳过（发送时已乐观渲染，再渲染就重复）
   *   · 只有 `char` 气泡**推进**队列；其它（bond 横幅/淡行）跟着当前队位走，不许插队
   *   · **本批第一条 + 队列恰好空闲** ⇒ 不延迟（"首个气泡早于整轮完成"靠它）
   *   · 上一批没放完（revealUntil 在未来）⇒ 这一批接到它后面（顺序铁律）
   *   · 队列里没东西时 totalMs=0，revealUntil 原样返回（调用方据此收起"正在输入…"）
   */
  function planReveal(items, opts) {
    const now = (opts && opts.now) || Date.now();
    const prevUntil = (opts && opts.revealUntil) || 0;
    const base = Math.max(0, prevUntil - now);   // 上一批还剩多久（0 = 队列空闲）
    let at = base;
    let firstOfBatch = true;
    const entries = [];
    for (const b of items || []) {
      if (b && b.side === "player") continue;
      if (b && b.side === "char") {
        if (!(firstOfBatch && base === 0)) at += chunkTypingMs(b.text || "");
        firstOfBatch = false;
      }
      entries.push({ item: b, delay: at });
    }
    return { entries, revealUntil: at > 0 ? now + at : prevUntil, totalMs: at };
  }

  window.L2BTyping = {
    SPEEDS,
    PUNCT_RE,
    charPause,
    TYPING_MS_PER_CHAR_MIN,
    TYPING_MS_PER_CHAR_MAX,
    TYPING_MS_PAUSE,
    chunkTypingMs,
    planReveal,
  };
})();
