// webgui/static/js/curtain.js — 换场黑幕的唯一实现。
//
// 只做一件事: 把一次视觉切换包进「黑入 → 干活 → 黑住 → 亮出」。
// **谁该黑由调用方决定, 本模块不认识场景** —— 触发点只有四个（背景切换 ×3 + 纪念进出）,
// 都由引擎事件驱动, 与标注/LLM 无关（动作层是另一回事, 见 bond.js 的 act）。
//
// 三条纪律:
//   1. 在途折叠: 一次只跑一条幕布; 在途期间再来只记住最后一次。连点「继续」/标注晚到
//      会让几次切换挨在一起, 排队就是肉眼可见的一串闪黑。
//   2. 干活抛异常也必须亮回来 —— 否则整块场景永久黑, 而且没有任何东西会告诉你。
//   3. 纯逻辑: fade / wait 由调用方注入（浏览器给 CSS 过渡, 测试给假函数）,
//      所以本文件不碰 DOM, node 里能直接 import 测。
//
// 幕布只盖**场景层**（CSS 把 z-index 压在 .bond-dialogue 之前）: 打字机照常跑, 字永不被黑。

export const CURTAIN_MS = {
  board:   { in: 200, hold: 60, out: 280 },   // 板首换场: 玩家刚点过「继续」, 等一下不显卡
  anchor:  { in: 120, hold: 40, out: 180 },   // 句级锚点: 打字中途换场, 长了像卡死
  onMemo:  { in: 140, hold: 0,  out: 420 },   // 进纪念: 亮出慢, 与纪念图 0.8s 淡入叠成一次渐变
  offMemo: { in: 200, hold: 80, out: 300 },   // 出纪念: 黑住时把背景还回去, 亮出就是干净的换场
  end:     { in: 260, hold: 0,  out: 0 },     // 收尾黑屏: 淡到黑就**停住**（out=0 = 不亮回来）
};

const DEFAULT_KIND = "board";

/**
 * 该不该为这次背景切换开一幕。
 *
 * 不黑的两种情形都踩过: 首帧（`enter` 有章节卡盖着, 再黑一次是多余的一闪）·
 * 同图（`syncBoardBg` 在轮询里反复调用, 同 URL 天天走到这里）。
 * 「有图 ↔ 无图」**算**切换 —— 收尾黑屏就是 fade to black, 那正是幕布该干的事。
 *
 * @param {{ primed: boolean, prev: string, next: string }} s
 */
export function needCurtain({ primed, prev, next }) {
  if (!primed) return false;
  return (prev || "") !== (next || "");
}

export class Curtain {
  /**
   * @param {{ fade: (target: number, ms: number) => Promise<void>,
   *           wait?: (ms: number) => Promise<void>,
   *           onError?: (e: unknown) => void }} deps
   */
  constructor({ fade, wait, onError } = {}) {
    this._fade = fade;
    this._wait = wait || ((ms) => new Promise((r) => setTimeout(r, ms)));
    this._onError = onError || (() => {});
    this._pending = null;      // 攒下的最后一次 {work, kind}
    this._busy = false;
    this._drain = Promise.resolve();
  }

  get busy() { return this._busy; }

  /**
   * 把一次切换包进黑幕。在途 → 折叠（只保留最后一次）。
   * 返回的 Promise = **含折叠进来的那次**都跑完 —— 调用方（渲染路径）不必 await。
   */
  run(work, kind = DEFAULT_KIND) {
    this._pending = { work, kind };
    if (this._busy) return this._drain;
    this._busy = true;
    this._drain = this._pump();
    return this._drain;
  }

  async _pump() {
    let broken = false;
    try {
      while (this._pending) {
        const { work, kind } = this._pending;
        this._pending = null;
        const ms = CURTAIN_MS[kind] || CURTAIN_MS[DEFAULT_KIND];
        await this._fade(1, ms.in);
        try {
          await work();
        } catch (e) {
          // 切换失败（素材/表达式炸了）→ 记一笔, 但黑幕必须继续走完
          this._onError(e);
        }
        if (ms.hold > 0) await this._wait(ms.hold);
        if (ms.out > 0) await this._fade(0, ms.out);
      }
    } catch (e) {
      broken = true;                    // 过渡本身炸了（元素被移除等）
      this._onError(e);
    } finally {
      this._busy = false;
      if (broken) {
        try { await this._fade(0, 0); } catch { /* 尽力而为 */ }
      }
    }
  }
}
