// tests/webgui/js/curtain.test.js — 换场黑幕的调度逻辑（node --test 传文件, 别传目录）
import test from "node:test";
import assert from "node:assert/strict";

import { CURTAIN_MS, Curtain, needCurtain } from "../../../webgui/static/js/curtain.js";

function make() {
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
  const { c, ops } = make();
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
  const { c, ops } = make();
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
  const { c, ops } = make();
  await c.run(async () => { throw new Error("boom"); });
  assert.ok(ops.some((o) => o[0] === "error" && o[1] === "boom"));
  assert.deepEqual(ops.filter((o) => o[0] === "fade"), [
    ["fade", 1, CURTAIN_MS.board.in],
    ["fade", 0, CURTAIN_MS.board.out],
  ]);
  assert.equal(c.busy, false);
});

test("时长分档: 句级锚点比板首短, 收尾黑屏不亮回来", async () => {
  const { c, ops } = make();
  await c.run(async () => {}, "anchor");
  assert.deepEqual(ops.filter((o) => o[0] === "fade"), [
    ["fade", 1, CURTAIN_MS.anchor.in],
    ["fade", 0, CURTAIN_MS.anchor.out],
  ]);
  assert.ok(CURTAIN_MS.anchor.in < CURTAIN_MS.board.in);

  const end = make();
  await end.c.run(async () => {}, "end");
  assert.deepEqual(end.ops.filter((o) => o[0] === "fade"), [["fade", 1, CURTAIN_MS.end.in]]);
});

test("未知档位退回 board（不因为拼错一个 kind 就整场不黑）", async () => {
  const { c, ops } = make();
  await c.run(async () => {}, "nonsense");
  assert.deepEqual(ops.filter((o) => o[0] === "fade"), [
    ["fade", 1, CURTAIN_MS.board.in],
    ["fade", 0, CURTAIN_MS.board.out],
  ]);
});
