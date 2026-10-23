// tests/webgui/js/effects.test.js — 装饰层（幕布 / 动作）的纯逻辑（node --test 传文件, 别传目录）
import test from "node:test";
import assert from "node:assert/strict";

import {
  ACT_NAMES,
  ACT_SPECS,
  CURTAIN_MS,
  Curtain,
  FX_SYMBOLS,
  needCurtain,
  playAct,
  resetAct,
} from "../../../webgui/static/js/effects.js";

// ---------------------------------------------------------------------------
// 幕布
// ---------------------------------------------------------------------------

function makeCurtain() {
  const ops = [];
  const c = new Curtain({
    fade: async (t, ms) => { ops.push(["fade", t, ms]); },
    wait: async (ms) => { ops.push(["wait", ms]); },
    onError: (e) => { ops.push(["error", (e && e.message) || String(e)]); },
  });
  return { c, ops };
}

test("首帧 / 同图不黑, 真的换图才黑", () => {
  assert.equal(needCurtain({ primed: false, prev: "", next: "/a.png" }), false);
  assert.equal(needCurtain({ primed: true, prev: "/a.png", next: "/a.png" }), false);
  assert.equal(needCurtain({ primed: true, prev: "/a.png", next: "/b.png" }), true);
  // 有图 ↔ 无图也算切换（收尾黑屏就是淡到黑）
  assert.equal(needCurtain({ primed: true, prev: "/a.png", next: "" }), true);
  assert.equal(needCurtain({ primed: true, prev: "", next: "/a.png" }), true);
  assert.equal(needCurtain({ primed: true, prev: "", next: "" }), false);
});

test("一次切换 = 黑入 → 干活 → 黑住 → 亮出, 顺序不变", async () => {
  const { c, ops } = makeCurtain();
  await c.run(async () => { ops.push(["work"]); });
  assert.deepEqual(ops, [
    ["fade", 1, CURTAIN_MS.board.in],
    ["work"],
    ["wait", CURTAIN_MS.board.hold],
    ["fade", 0, CURTAIN_MS.board.out],
  ]);
  assert.equal(c.busy, false);
});

test("在途折叠: 期间再来只跑最后一次, 不排队", async () => {
  const { c, ops } = makeCurtain();
  await c.run(async () => {
    ops.push(["w1"]);
    c.run(async () => { ops.push(["w2"]); });      // 被下一次覆盖
    c.run(async () => { ops.push(["w3"]); });      // 只有它活下来
  });
  const works = ops.filter((o) => o[0] !== "fade" && o[0] !== "wait");
  assert.deepEqual(works, [["w1"], ["w3"]]);
  assert.equal(ops.filter((o) => o[0] === "fade" && o[1] === 1).length, 2);
  assert.equal(ops.filter((o) => o[0] === "fade" && o[1] === 0).length, 2);
});

test("干活抛异常也必须亮回来", async () => {
  const { c, ops } = makeCurtain();
  await c.run(async () => { throw new Error("boom"); });
  assert.ok(ops.some((o) => o[0] === "error" && o[1] === "boom"));
  assert.deepEqual(ops.filter((o) => o[0] === "fade"), [
    ["fade", 1, CURTAIN_MS.board.in],
    ["fade", 0, CURTAIN_MS.board.out],
  ]);
  assert.equal(c.busy, false);
});

test("时长分档: 句级锚点比板首短, 收尾黑屏不亮回来", async () => {
  const { c, ops } = makeCurtain();
  await c.run(async () => {}, "anchor");
  assert.deepEqual(ops.filter((o) => o[0] === "fade"), [
    ["fade", 1, CURTAIN_MS.anchor.in],
    ["fade", 0, CURTAIN_MS.anchor.out],
  ]);
  assert.ok(CURTAIN_MS.anchor.in < CURTAIN_MS.board.in);

  const end = makeCurtain();
  await end.c.run(async () => {}, "end");
  assert.deepEqual(end.ops.filter((o) => o[0] === "fade"), [["fade", 1, CURTAIN_MS.end.in]]);
});

test("未知档位退回 board（不因为拼错一个 kind 就整场不黑）", async () => {
  const { c, ops } = makeCurtain();
  await c.run(async () => {}, "nonsense");
  assert.deepEqual(ops.filter((o) => o[0] === "fade"), [
    ["fade", 1, CURTAIN_MS.board.in],
    ["fade", 0, CURTAIN_MS.board.out],
  ]);
});

// ---------------------------------------------------------------------------
// 动作
// ---------------------------------------------------------------------------

function fakeEl() {
  const calls = [];
  const anims = [{ cancelled: false, cancel() { this.cancelled = true; } }];
  return {
    calls,
    anims,
    style: {},
    animate(frames, opts) { calls.push({ frames, opts }); return {}; },
    getAnimations() { return anims; },
  };
}

test("符号表与动作表都在这个文件里（装饰一类一处）", () => {
  assert.ok(Object.keys(FX_SYMBOLS).length > 0);
  assert.ok(ACT_NAMES.includes("jump"));
  assert.deepEqual(ACT_NAMES, Object.keys(ACT_SPECS));
});

test("每个动作都有正时长、单调偏移、首尾 0/1", () => {
  for (const [name, spec] of Object.entries(ACT_SPECS)) {
    assert.ok(spec.ms > 0, name);
    assert.ok(spec.frames.length >= 2, name);
    assert.equal(spec.frames[0].offset, 0, name);
    assert.equal(spec.frames[spec.frames.length - 1].offset, 1, name);
    const offs = spec.frames.map((f) => f.offset);
    assert.deepEqual(offs, [...offs].sort((a, b) => a - b), `${name} 偏移必须单调`);
    for (const f of spec.frames) assert.ok(f.transform, `${name} 每帧都要 transform`);
  }
});

test("playAct: 词表外 → false, 一根手指都不动", () => {
  const el = fakeEl();
  assert.equal(playAct(el, "backflip"), false);
  assert.equal(el.calls.length, 0);
  assert.equal(el.anims[0].cancelled, false);
});

test("playAct: 已知动作 → 先撤掉上一次（杜绝 transform 叠加）, 再按表播", () => {
  const el = fakeEl();
  assert.equal(playAct(el, "jump"), true);
  assert.equal(el.anims[0].cancelled, true);          // 上一次被撤掉
  assert.equal(el.calls.length, 1);
  const { frames, opts } = el.calls[0];
  assert.equal(frames, ACT_SPECS.jump.frames);
  assert.equal(opts.duration, ACT_SPECS.jump.ms);
  assert.equal(opts.easing, ACT_SPECS.jump.easing);
  assert.equal(opts.fill, "none");                    // 跳跃不留定格
});

test("playAct: 所有动作都不留定格（fill none）", () => {
  for (const name of ACT_NAMES) {
    const e = fakeEl();
    playAct(e, name);
    assert.equal(e.calls[0].opts.fill, "none", name);
  }
});

test("playAct: animate 炸了 → onError 收到, 仍返回 false（不许把渲染链带下水）", () => {
  const el = fakeEl();
  el.animate = () => { throw new Error("no WAAPI"); };
  const errs = [];
  assert.equal(playAct(el, "jump", { onError: (e) => errs.push(e.message) }), false);
  assert.deepEqual(errs, ["no WAAPI"]);
});

test("resetAct: 撤掉所有动画并清掉残留 transform（换板清场）", () => {
  const el = fakeEl();
  el.style.transform = "rotate(-8deg)";
  resetAct(el);
  assert.equal(el.anims[0].cancelled, true);
  assert.equal(el.style.transform, "");
});
