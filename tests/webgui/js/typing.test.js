// typing.js 的单测（node --test tests/webgui/js/）。
//
// typing.js 是经典脚本（挂 window.L2BTyping），所以这里用 new Function 给它一个假的 window
// 再取出来 —— 顺带也证明了它不依赖 DOM。
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const SRC = new URL("../../../webgui/static/js/typing.js", import.meta.url);
const sandbox = {};
new Function("window", readFileSync(SRC, "utf8"))(sandbox);
const T = sandbox.L2BTyping;

test("导出的东西都在", () => {
  for (const k of ["SPEEDS", "charPause", "chunkTypingMs", "planReveal"]) {
    assert.ok(T && T[k] !== undefined, `缺 ${k}`);
  }
});

test("charPause：标点停得久，其余用基准", () => {
  assert.equal(T.charPause("，", 42, 150), 150);
  assert.equal(T.charPause("。", 42, 150), 150);
  assert.equal(T.charPause("…", 42, 150), 150);
  assert.equal(T.charPause("你", 42, 150), 42);
  assert.equal(T.charPause("a", 42, 150), 42);
});

test("chunkTypingMs：字数 × [60,120] + 400", () => {
  for (const text of ["", "a", "你好世界", "x".repeat(50)]) {
    const ms = T.chunkTypingMs(text);
    const lo = text.length * T.TYPING_MS_PER_CHAR_MIN + T.TYPING_MS_PAUSE;
    const hi = text.length * T.TYPING_MS_PER_CHAR_MAX + T.TYPING_MS_PAUSE;
    assert.ok(ms >= lo && ms <= hi, `${text.length} 字 → ${ms}，应在 [${lo}, ${hi}]`);
  }
  assert.equal(T.chunkTypingMs(null), T.TYPING_MS_PAUSE, "null 当空串");
});

test("planReveal：队列空闲时第一条不延迟，后续逐条排队", () => {
  const { entries, totalMs, revealUntil } = T.planReveal(
    [{ side: "char", text: "你好" }, { side: "char", text: "再见" }],
    { now: 1000, revealUntil: 0 });
  assert.equal(entries.length, 2);
  assert.equal(entries[0].delay, 0, "第一条不该等（首泡必须早于整轮完成）");
  assert.ok(entries[1].delay > 0, "第二条要排在第一条后面");
  assert.ok(totalMs >= entries[1].delay);
  assert.equal(revealUntil, 1000 + totalMs);
});

test("planReveal：队列没放完时，第一条也得排队（顺序铁律）", () => {
  const now = 1000;
  // 上一批要**两条**才会留下队列尾：单条 char 是"立刻上屏"，at 仍是 0（见下一条用例）
  const first = T.planReveal(
    [{ side: "char", text: "前一批一" }, { side: "char", text: "前一批二" }],
    { now, revealUntil: 0 });
  assert.ok(first.revealUntil > now, "两条才排得起来");
  const later = now + 10;
  const second = T.planReveal([{ side: "char", text: "后一批" }],
    { now: later, revealUntil: first.revealUntil });
  assert.ok(second.entries[0].delay > 0, "上一批还在放 ⇒ 这一批不许插队");
  assert.ok(second.entries[0].delay >= first.revealUntil - later,
    "应接在上一批的队尾之后");
});

test("planReveal：单条 char 是立刻上屏（at 停在 0，不留队列尾）", () => {
  const p = T.planReveal([{ side: "char", text: "只有一条" }], { now: 700, revealUntil: 0 });
  assert.equal(p.entries[0].delay, 0);
  assert.equal(p.totalMs, 0, "第一条不延迟 ⇒ 没有排队的");
  assert.equal(p.revealUntil, 0, "没排队就不该改队列尾");
});

test("planReveal：player 跳过；非 char 不推进队列", () => {
  const { entries } = T.planReveal([
    { side: "player", text: "老师那句" },
    { side: "char", text: "角色" },
    { side: "bond_entry", text: "羁绊入口" },
    { side: "char", text: "再一条" },
  ], { now: 0, revealUntil: 0 });
  assert.deepEqual(entries.map((e) => e.item.side), ["char", "bond_entry", "char"]);
  assert.equal(entries[0].delay, 0);
  // bond_entry 跟着当前队位走（不推进）：与它前面那条 char 同延迟
  assert.equal(entries[1].delay, entries[0].delay);
  assert.ok(entries[2].delay > entries[1].delay, "后一条 char 才推进队列");
});

test("planReveal：没东西可放且队列空闲 ⇒ totalMs=0，revealUntil 原样", () => {
  const empty = T.planReveal([], { now: 500, revealUntil: 0 });
  assert.equal(empty.totalMs, 0);
  assert.equal(empty.revealUntil, 0);
  const onlyPlayer = T.planReveal([{ side: "player", text: "x" }],
    { now: 500, revealUntil: 0 });
  assert.equal(onlyPlayer.totalMs, 0);
  assert.deepEqual(onlyPlayer.entries, []);
});

test("planReveal：上一批还在放时，被跳过的那条也让 totalMs 反映剩余队列", () => {
  // 调用方靠 totalMs 决定"要不要收起正在输入…"——所以剩余队列必须如实报出来
  const p = T.planReveal([{ side: "player", text: "老师那句" }],
    { now: 500, revealUntil: 999 });
  assert.deepEqual(p.entries, [], "player 不渲染");
  assert.equal(p.totalMs, 499, "但上一批还剩 499ms");
  assert.equal(p.revealUntil, 999, "没新东西排队 ⇒ 队列尾不动");
});
