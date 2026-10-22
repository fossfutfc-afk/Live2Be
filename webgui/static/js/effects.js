// webgui/static/js/effects.js — VN 的**全部装饰**（无构建步骤）。
//
// 三件事放一起, 因为它们是同一类: 后端只给"名字或事件", 怎么动全在这里。
//   ① 换场幕布 — 引擎事件驱动（背景切换 / 纪念进出）, 没有判定的余地, 也不进任何词表
//   ② 情绪符号 — 名字的真源在 `tui/effects.py`, 由 `webgui/routers/bond.py` 写进 `p.fx`
//   ③ 角色动作 — 名字的真源在 `core/bond/actions.py`, 与情绪同构成一格, 写回时拆成 `p.act`
//
// 触发点全在 bond.js（幕布四个 / 动作在段首与晚到补演）, 本文件只提供"怎么表现"。
//
// ⚠️ ②③ 都是"后端说名字、前端负责画": 词表漂移的表现是网页上什么都不动、也不报错 ——
//    `tests/webgui/test_frontend_contract.py` 双向钉死, 少一个就红。

// ---------------------------------------------------------------------------
// ① 换场幕布
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// ② 情绪符号（键 = tui/effects.py 产出的 fx 名）
// ---------------------------------------------------------------------------

// 官方 BA 的"冒爱心/音符/惊叹"是 UI 层粒子 —— 这里用 Unicode 符号 + CSS 浮动动画
// （零素材成本; 符号可随时换 emoji/SVG, 映射只改这一处）。
export const FX_SYMBOLS = {
  sparkle:  { sym: "✦", color: "#ffe9a8" },   // 开心闪光（白金色四角星）
  heart:    { sym: "♥", color: "#ff7aa2" },   // 爱心（官方粉心）
  notes:    { sym: "♪", color: "#bfe0ff" },   // 音符（官方蓝紫音符）
  bang:     { sym: "❗", color: "#ffd166" },   // 惊叹号
  anger:    { sym: "💢", color: "#ff8a8a" },   // 怒纹
  raindrop: { sym: "💧", color: "#9cc4ff" },   // 低落/泪滴
  sweat:    { sym: "💦", color: "#b8e2ff" },   // 汗
  blush:    { sym: "❥", color: "#ffb3c6" },   // 脸红（轻粉心; 主体脸红由立绘差分表达）
};

// ---------------------------------------------------------------------------
// ③ 角色动作（键 = core/bond/actions.py 的 ACTION_NAMES）
// ---------------------------------------------------------------------------

// 时长与幅度按 BA 的手感自定 —— 原作**没有可抄的曲线**: 剧情动作在原作里是代码枚举
// （`ScenarioCharacterAction`）驱动的位移, spine 立绘包里根本没有跳跃动画。
// 全部作用在 `#bond-stage` 的 transform 上（立绘与符号一起动; 字与按钮不动）。
// 单位用 %（舞台满屏, 所以 % ≈ 屏高/屏宽的百分比, 不用量元素尺寸 → 纯数据, 可 node 测）。
export const ACT_SPECS = {
  jump: {
    ms: 420, easing: "ease-in-out",
    frames: [
      { offset: 0, transform: "translateY(0%) scaleY(1)" },
      { offset: 0.42, transform: "translateY(-6%) scaleY(1.03)" },
      { offset: 0.70, transform: "translateY(0%) scaleY(1)" },
      { offset: 0.85, transform: "translateY(0%) scaleY(0.94)" },   // 落地压缩
      { offset: 1, transform: "translateY(0%) scaleY(1)" },
    ],
  },
  hop: {
    ms: 320, easing: "ease-out",
    frames: [
      { offset: 0, transform: "translateY(0%) scaleY(1)" },
      { offset: 0.45, transform: "translateY(-2.5%) scaleY(1)" },
      { offset: 0.80, transform: "translateY(0%) scaleY(0.97)" },
      { offset: 1, transform: "translateY(0%) scaleY(1)" },
    ],
  },
  shake: {
    ms: 260, easing: "linear",
    frames: [
      { offset: 0, transform: "translateX(0%)" },
      { offset: 0.18, transform: "translateX(-0.6%)" },
      { offset: 0.40, transform: "translateX(0.6%)" },
      { offset: 0.62, transform: "translateX(-0.4%)" },
      { offset: 0.82, transform: "translateX(0.3%)" },
      { offset: 1, transform: "translateX(0%)" },
    ],
  },
  stiff: {
    ms: 180, easing: "ease-out",
    frames: [
      { offset: 0, transform: "scaleY(1)" },
      { offset: 0.35, transform: "scaleY(0.96)" },
      { offset: 1, transform: "scaleY(1)" },
    ],
  },
  fall: {
    // 定格: 坐倒之后就该一直坐着, 直到下一段/下一板把它撤掉
    ms: 460, easing: "cubic-bezier(.45,0,.75,0)", fill: "forwards",
    frames: [
      { offset: 0, transform: "translateY(0%) rotate(0deg)" },
      { offset: 1, transform: "translateY(4%) rotate(-8deg)" },
    ],
  },
  greet: {
    ms: 520, easing: "ease-in-out",
    frames: [
      { offset: 0, transform: "translateY(0%)" },
      { offset: 0.25, transform: "translateY(2.5%)" },
      { offset: 0.50, transform: "translateY(0%)" },
      { offset: 0.75, transform: "translateY(2.5%)" },
      { offset: 1, transform: "translateY(0%)" },
    ],
  },
};

export const ACT_NAMES = Object.freeze(Object.keys(ACT_SPECS));

/**
 * 播一个动作。返回 false = 词表里没有（**静默不动**, 宁缺勿错 ——
 * 后端已校验过词表, 走到这里说明两边漂了, 调用方负责打日志）。
 *
 * @param {HTMLElement} el   动谁（VN 里是 `#bond-stage`）
 * @param {string} name
 * @param {{ onError?: (e: unknown) => void }} [opts]
 */
export function playAct(el, name, { onError } = {}) {
  const spec = ACT_SPECS[name];
  if (!el || !spec || typeof el.animate !== "function") return false;
  try {
    // 一次只留一个: 上一次的 `fall` 定格和没播完的跳都先撤掉（否则 transform 会叠）
    if (typeof el.getAnimations === "function") {
      el.getAnimations().forEach((a) => a.cancel());
    }
    el.animate(spec.frames, {
      duration: spec.ms,
      easing: spec.easing || "ease-in-out",
      fill: spec.fill || "none",
    });
    return true;
  } catch (e) {
    if (onError) onError(e);
    return false;
  }
}

/** 撤掉所有动作（换板/换角色时清场: `fall` 的定格不该带到下一场）。 */
export function resetAct(el) {
  if (!el) return;
  try {
    if (typeof el.getAnimations === "function") {
      el.getAnimations().forEach((a) => a.cancel());
    }
  } catch { /* 尽力而为 */ }
  el.style.transform = "";
}
