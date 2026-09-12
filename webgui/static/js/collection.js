// Live2Be 回忆册（DESIGN_COLLECTION_BOOK.md）
//   书页 = 两半页 × 3行4列 = 24 格; 一格 = 一角色（collection.png 封面, 无素材留白）
//   → 点格子进"角色页"（该角色**已确认结束**的章, 标题 + 进入按钮）
//   → 只读回放（BondVN.enterReadonly: 复用 VN 渲染器, 播完即停, 0 LLM）
//
// 口径（作者 2026-09-12）:
//   · 顺序 = mmt_registry 白名单顺序（后端给, 前端不重排）
//   · 未结束的章**连条目都不渲染**（后端就不返回——前端不做过滤逻辑）
//   · 留白格 = 有这个人但没有 collection.png（占位, 顺序稳定）; 真正的空槽不画框
"use strict";

// 注意: 不重复声明 $/show —— gui.js 已提供全局

const Book = (() => {
  const ROWS = 3, COLS = 4;          // 后端也会给（唯一真源在后端, 这里只是缺省）
  let cells = [];
  let perPage = ROWS * COLS;         // 每半页格数
  let page = 0;
  let curChar = null;                // 当前角色页的角色（返回时用）

  // ── 小工具 ────────────────────────────────────────────────────────────────
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) {
      let detail = res.status + "";
      try { detail = (await res.json()).detail || detail; } catch (e) { /* 忽略 */ }
      throw new Error(detail);
    }
    return res.json();
  }

  // ── 书页 ─────────────────────────────────────────────────────────────────

  async function open() {
    show("view-collection");
    $("col-char").classList.add("hidden");
    $("col-book").classList.remove("hidden");
    curChar = null;
    const grid = $("col-grid-left");
    grid.innerHTML = "";
    grid.appendChild(el("p", "col-loading", "正在翻开回忆册…"));
    try {
      const data = await getJSON("/api/collection/book");
      perPage = (data.rows || ROWS) * (data.cols || COLS);
      cells = data.cells || [];
      page = 0;
      renderSpread();
    } catch (e) {
      grid.innerHTML = "";
      grid.appendChild(el("p", "col-loading", "回忆册打不开: " + e.message));
    }
  }

  function close() {
    $("col-char").classList.add("hidden");
    $("col-book").classList.remove("hidden");
    curChar = null;
    show("view-main");
  }

  function renderSpread() {
    const left = $("col-grid-left"), right = $("col-grid-right");
    left.innerHTML = "";
    right.innerHTML = "";
    const start = page * perPage * 2;                  // 一跨页 = 两半页
    for (let i = 0; i < perPage; i++) {
      left.appendChild(slotFor(cells[start + i]));
      right.appendChild(slotFor(cells[start + perPage + i]));
    }
    const spreads = Math.max(1, Math.ceil(cells.length / (perPage * 2)));
    $("col-prev").disabled = page <= 0;
    $("col-next").disabled = page >= spreads - 1;
    $("col-prev").classList.toggle("hidden", spreads <= 1);
    $("col-next").classList.toggle("hidden", spreads <= 1);
    $("col-pager").textContent = spreads > 1
      ? `${page + 1} / ${spreads}` : "";
  }

  /** 一个格子: 有角色即可点（封面只是外观）; 无角色 → 空槽（不画）。
   *
   * 2026-09-13 修正（审计 A2）: 原实现把 `addEventListener("click")` 放在
   * "有封面"那条分支里, 而留白分支 `return box` **在挂监听之前** → 没封面的
   * 角色**整格点不动**。后端 `/api/collection/{char_id}/chapters` 只看事件流、
   * **从不看封面**（routers/collection.py:90-102）, 所以这个限制纯属前端自造:
   * 触发路径不是"别人 clone"（.gitignore 忽略 portrait/*.png, fresh clone 每格
   * 都留白）, 更常见的是**作者加新角色**——人设/spine 就位、封面还没做时,
   * 她已结束的章在册子里根本进不去。
   */
  function slotFor(c) {
    if (!c) return el("div", "col-slot empty");
    const box = el("div", "col-slot");
    box.dataset.char = c.char_id;               // 便于定位（冒烟/调试）
    if (!c.has_cover || !c.cover) {
      box.classList.add("blank");
      box.title = `${c.name}（还没有 collection 素材）`;
      box.appendChild(el("span", "col-blank-mark", "？"));
      box.appendChild(el("span", "col-cell-name", c.name));
    } else {
      const img = el("img", "col-cell-img");
      img.src = c.cover;
      img.alt = c.name;
      img.loading = "lazy";
      box.appendChild(img);
      box.appendChild(el("span", "col-cell-name", c.name));
      box.title = c.name;
    }
    // 挂监听在两条分支之外——有角色就能进角色页（封面缺失不影响可点性）
    box.addEventListener("click", () => openChar(c));
    return box;
  }

  function turn(delta) {
    page = Math.max(0, page + delta);
    renderSpread();
  }

  // ── 角色页（已结束的章） ──────────────────────────────────────────────────

  async function openChar(c) {
    curChar = c;
    $("col-book").classList.add("hidden");
    const pane = $("col-char");
    pane.classList.remove("hidden");
    $("col-char-name").textContent = c.name;
    $("col-char-club").textContent = "";
    const list = $("col-chapters");
    list.innerHTML = "";
    list.appendChild(el("p", "col-loading", "加载中…"));
    try {
      const d = await getJSON(`/api/collection/${encodeURIComponent(c.char_id)}/chapters`);
      $("col-char-name").textContent = d.name || c.name;
      $("col-char-club").textContent = d.club || "";
      renderChapters(d);
    } catch (e) {
      list.innerHTML = "";
      list.appendChild(el("p", "col-loading", "读不到她的故事: " + e.message));
    }
  }

  function backToBook() {
    $("col-char").classList.add("hidden");
    $("col-book").classList.remove("hidden");
    curChar = null;
  }

  /** 章节条目: 标题 + （有纪念图时的缩略图）+ 进入按钮。**只画后端给的章**。 */
  function renderChapters(d) {
    const list = $("col-chapters");
    const chapters = d.chapters || [];
    list.innerHTML = "";
    const head = el("div", "col-chapter-head");
    head.appendChild(el("span", "col-chapter-title", "已结束的故事"));
    head.appendChild(el("span", "col-chapter-count", `${chapters.length} 章`));
    list.appendChild(head);
    if (!chapters.length) {
      list.appendChild(el("p", "col-empty", "还没有结束的故事。"));
      return;
    }
    chapters.forEach((ch, i) => {
      const row = el("div", "col-chapter");
      if (ch.memorial_url) {                       // 有纪念图 → 条目上挂缩略图
        const thumb = el("img", "col-chapter-thumb");
        thumb.src = ch.memorial_url;
        thumb.alt = "";
        row.appendChild(thumb);
      } else {
        row.appendChild(el("span", "col-chapter-no", String(i + 1)));
      }
      const meta = el("div", "col-chapter-meta");
      meta.appendChild(el("div", "col-chapter-name",
                          (ch.title || "").trim() || `第 ${i + 1} 章`));
      meta.appendChild(el("div", "col-chapter-sub",
                          `${ch.boards} 板${ch.memorial_url ? " · 含纪念图" : ""}`));
      row.appendChild(meta);
      const btn = el("button", "col-play", "回放");
      btn.addEventListener("click", () => play(d.char_id, ch));
      row.appendChild(btn);
      list.appendChild(row);
    });
  }

  // ── 只读回放（交给 VN 渲染器; 播完回角色页） ──────────────────────────────

  async function play(charId, ch) {
    try {
      const payload = await getJSON(
        `/api/collection/${encodeURIComponent(charId)}/${ch.from_seq}`);
      window.BondVN.enterReadonly(payload, () => {
        // 播完/退出 → 回角色页（若角色页还在, 直接露出来）
        show("view-collection");
        if (curChar) $("col-char").classList.remove("hidden");
        else $("col-book").classList.remove("hidden");
      });
    } catch (e) {
      alert("这一章读不出来: " + e.message);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("col-back").addEventListener("click", close);
    $("col-char-back").addEventListener("click", backToBook);
    $("col-prev").addEventListener("click", () => turn(-1));
    $("col-next").addEventListener("click", () => turn(1));
  });

  return { open, close };
})();

window.Book = Book;
