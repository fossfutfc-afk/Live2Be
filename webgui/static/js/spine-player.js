// webgui/static/js/spine-player.js — Live2Be Spine 播放器组件（零构建依赖）。
//
// 依赖: pixi.js + @esotericsoftware/spine-pixi-v8 的官方自包含 ESM bundle,
//       由 index.html 的 import map 映射（"pixi.js" → /static/vendor/pixi.min.mjs）。
//       本文件用相对 vendor 路径直接 import spine bundle（spine-core 已内联）。
//
// 设计（docs/DESIGN_RENDERER.md §4.3 + side-request 定稿）:
//   - mount/load 分离: 先占位显示再异步出资源, UI 不阻塞
//   - setEmotion 是语义层: 查 emotion→anim 映射（load 时注入或默认推导）, 命中才播
//   - play 不存在的动画 → 返回 false 保持现状（宁缺勿错, 静默降级）
//   - 事件走 EventTarget: VN 台词节奏层与调试面板可同时监听
//
// 用法:
//   const player = new SpinePlayer();
//   await player.mount(document.getElementById('stage'));
//   await player.load({ skel: '/assets/.../x.skel', atlas: '/assets/.../x.atlas' });
//   player.setEmotion('smile');
//   player.play('Idle_01', { loop: true });

import {
  Spine,
  SkeletonBinary,
  AtlasAttachmentLoader,
  Physics,
} from '/static/vendor/spine-pixi-v8.min.mjs';
import { Application, Assets } from 'pixi.js';

// ---------------------------------------------------------------------------
// 错误类型 — 带阶段信息, 供上层区分失败点
// ---------------------------------------------------------------------------

export class SpinePlayerError extends Error {
  constructor(stage, message, cause) {
    super(message);
    this.name = 'SpinePlayerError';
    this.stage = stage;          // 'init' | 'load' | 'parse' | 'render'
    this.cause = cause;
  }
}

// ---------------------------------------------------------------------------
// SpinePlayer
// ---------------------------------------------------------------------------

export class SpinePlayer extends EventTarget {
  /**
   * @param {{ antialias?: boolean, background?: string|number }} [opts]
   */
  constructor(opts = {}) {
    super();
    this._opts = opts;
    this._app = null;
    this._spine = null;          // pixi Spine 渲染对象
    this._container = null;
    this._resizeObserver = null;
    this._emotionMap = null;     // { emotion: anim } — setEmotion 的映射
    this._animSet = new Set();   // skel 动画名集合（play 校验用）
    this._loaded = false;
    this._autoFit = true;
    this._flipped = false;
    this._alpha = 1;
    this._info = null;
  }

  // ── 生命周期 ──────────────────────────────────────────────────────────

  /**
   * 创建 pixi canvas 并挂进容器。之后容器尺寸变化自动跟随（ResizeObserver）。
   * @param {HTMLElement} container
   * @param {{ autoFit?: boolean, background?: string|number, antialias?: boolean,
   *           resolution?: number }} [opts]
   */
  async mount(container, opts = {}) {
    if (this._app) throw new SpinePlayerError('init', '已 mount, 先 destroy()');
    if (!(container instanceof HTMLElement)) {
      throw new SpinePlayerError('init', 'container 必须是 HTMLElement');
    }
    this._container = container;
    this._autoFit = opts.autoFit ?? this._opts.autoFit ?? true;
    try {
      const app = new Application();
      const bg = opts.background ?? this._opts.background;
      const appOpts = {
        antialias: opts.antialias ?? this._opts.antialias ?? true,
        // resolution 必须显式给: 缺省时 pixi view.resolution 为 undefined,
        // resize 内部 canvas.width = 宽 × undefined = NaN → canvas 变 0x0 画不出任何东西
        resolution: opts.resolution ?? this._opts.resolution ?? 1,
        autoDensity: true,
      };
      if (bg === undefined || bg === 'transparent') {
        // 透明背景（VN 场景: 立绘浮在背景图之上）。
        // 实测（pixi v8 该版本）: background:'transparent' / {r,g,b,a:0} / '#0000'
        // 都不会让 canvas 透明——clear 仍是不透明黑（toDataURL alpha=255 黑块,
        // 盖住下层场景图）。必须显式 backgroundAlpha: 0 才真正透明。
        appOpts.background = 0x000000;
        appOpts.backgroundAlpha = 0;
      } else {
        appOpts.background = bg;
      }
      await app.init(appOpts);
      this._app = app;
      container.appendChild(app.canvas);
      // 立即同步一次容器尺寸——不依赖 ResizeObserver 首帧回调（headless/首挂载可能缺失）
      const w0 = container.clientWidth;
      const h0 = container.clientHeight;
      if (w0 && h0) app.renderer.resize(w0, h0);
    } catch (e) {
      throw new SpinePlayerError('init', `pixi 初始化失败: ${e.message}`, e);
    }
    // 容器尺寸变化 → 同步 renderer + 自动 fit（不用 pixi resizeTo, 避免双份监听）
    this._resizeObserver = new ResizeObserver(() => {
      if (!this._app) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w && h) this._app.renderer.resize(w, h);
      if (this._autoFit && this._spine) this.fit();
    });
    this._resizeObserver.observe(container);
  }

  /**
   * 加载 spine 包（skel + atlas 两个 URL; png 由 atlas 页名同目录自动解析）。
   * @param {{ skel: string, atlas: string } | string} pack
   *        对象 = 两个资源 URL; 字符串 = 目录 URL（按 {dir}/{name}.skel|.atlas 约定, name=最后一段）
   * @param {{ emotionMap?: Record<string,string> }} [opts]
   * @returns {Promise<{bones:number, animations:string[], skins:string[]}>}
   */
  async load(pack, opts = {}) {
    if (!this._app) throw new SpinePlayerError('load', '先 mount() 再 load()');
    let skelUrl, atlasUrl;
    if (typeof pack === 'string') {
      const dir = pack.replace(/\/+$/, '');
      const name = dir.split('/').pop();
      skelUrl = `${dir}/${name}.skel`;
      atlasUrl = `${dir}/${name}.atlas`;
    } else {
      skelUrl = pack.skel;
      atlasUrl = pack.atlas;
    }
    if (!skelUrl || !atlasUrl) {
      throw new SpinePlayerError('load', 'pack 需要 skel + atlas 两个 URL');
    }
    this._emit('error-clear');
    try {
      await Assets.load([atlasUrl, skelUrl]);
    } catch (e) {
      throw new SpinePlayerError('load', `资源加载失败: ${e.message}`, e);
    }
    let atlas, skel;
    try {
      atlas = Assets.get(atlasUrl);
      skel = Assets.get(skelUrl);
    } catch (e) {
      throw new SpinePlayerError('parse', `资源解析失败: ${e.message}`, e);
    }
    if (!atlas || !skel) {
      throw new SpinePlayerError('parse', 'atlas/skel 加载器未注册或资源缺失');
    }
    try {
      const parser = new SkeletonBinary(new AtlasAttachmentLoader(atlas));
      parser.scale = 1;
      const skeletonData = parser.readSkeletonData(skel);
      const spine = new Spine(skeletonData);
      spine.skeleton.setToSetupPose();
      spine.update(0);                       // 让 setup pose 的 bounds 有效
      this._spine = spine;
      this._app.stage.addChild(spine);
      this._animSet = new Set(skeletonData.animations.map((a) => a.name));
      this._emotionMap = opts.emotionMap ?? null;
      this._loaded = true;
      this._info = {
        bones: skeletonData.bones.length,
        animations: [...this._animSet],
        skins: skeletonData.skins.map((s) => s.name),
      };
      // spine-core AnimationState 事件 → 本组件事件
      spine.state.addListener({
        start: (entry) => this._emit('animationstart', { anim: entry.animation.name, track: entry.trackIndex }),
        complete: (entry) => this._emit('animationcomplete', { anim: entry.animation.name, track: entry.trackIndex }),
        end: (entry) => this._emit('animationend', { anim: entry.animation.name, track: entry.trackIndex }),
      });
      if (this._autoFit) this.fit();
      this._emit('load', { info: this._info });
      return this._info;
    } catch (e) {
      throw new SpinePlayerError('parse', `skel 解析失败: ${e.message}`, e);
    }
  }

  /** 卸载: 销毁 pixi app / 解绑 observer / 清状态。之后可重新 mount。 */
  destroy() {
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
    if (this._app) {
      try { this._app.destroy(true, { children: true }); } catch { /* 尽力而为 */ }
      this._app = null;
    }
    this._spine = null;
    this._loaded = false;
    this._info = null;
    this._animSet = new Set();
    this._emotionMap = null;
  }

  // ── 播放 ──────────────────────────────────────────────────────────────

  /**
   * 播放动画。返回 false = 动画不存在（保持当前, 静默降级——宁缺勿错）。
   * @param {string} anim
   * @param {{ loop?: boolean, track?: number, mix?: number, timeScale?: number }} [opts]
   */
  play(anim, opts = {}) {
    if (!this._loaded || !this._spine) return false;
    if (!this._animSet.has(anim)) return false;
    const track = opts.track ?? 0;
    const loop = opts.loop ?? true;
    const entry = this._spine.state.setAnimation(track, anim, loop);
    if (typeof opts.mix === 'number') {
      const data = this._spine.state.data;
      const prev = this._spine.state.getCurrent(track);
      if (prev) data.setMix(prev.animation.name, anim, opts.mix);
    }
    if (typeof opts.timeScale === 'number') {
      entry.timeScale = opts.timeScale;
      this._spine.state.timeScale = opts.timeScale;
    }
    return true;
  }

  /** 停掉某 track（缺省 0）。 */
  stop(track = 0) {
    if (!this._loaded || !this._spine) return;
    this._spine.state.setEmptyAnimation(track, 0);
  }

  /**
   * 语义层: emotion → anim 映射（load 时注入或 setEmotionMap 设置）→ 播放。
   * 无映射 / 映射动画不存在 → false（保持现状）。
   */
  setEmotion(emotion) {
    if (!this._emotionMap) return false;
    const anim = this._emotionMap[emotion];
    if (!anim) return false;
    if (!this.play(anim, { loop: true })) return false;
    this._emit('emotionchange', { emotion, anim });
    return true;
  }

  /** 注入/替换 emotion→anim 映射（如后端下发的 /api/spine 元信息）。 */
  setEmotionMap(map) {
    this._emotionMap = map ? { ...map } : null;
  }

  // ── 表现 ──────────────────────────────────────────────────────────────

  /**
   * 按骨骼 bounds 自适应缩放居中（BA 各包锚点/尺寸不同, 必须按包算）。
   * 用 spine-core 的 SkeletonBounds（纯骨骼数据, 不依赖 pixi transform/渲染状态）。
   * @param {'contain'|'cover'} [mode] 缺省 contain（完整可见）
   * @param {number} [padding] 边距像素
   */
  fit(mode = 'contain', padding = 0) {
    if (!this._app || !this._spine) return;
    const cw = this._app.screen.width;
    const ch = this._app.screen.height;
    if (!cw || !ch) return;
    // 用 spine-core 的 getBoundsRect 算局部包围盒（与 pixi Spine.getBounds 同路数）:
    // skeleton 副本 + setToSetupPose + updateWorldTransform(Physics.update)。
    // spine-core 4.2 的 updateWorldTransform(physics) 必须显式传 Physics 枚举, null 会抛错;
    // SkeletonBounds 类对某些附件类型收集不到, 不适用。
    this._spine.skeleton.setToSetupPose();
    this._spine.skeleton.updateWorldTransform(Physics.update);
    const b = this._spine.skeleton.getBoundsRect();
    if (!b || !b.width || !b.height) return;
    const availW = cw - padding * 2;
    const availH = ch - padding * 2;
    const s = mode === 'cover'
      ? Math.max(availW / b.width, availH / b.height)
      : Math.min(availW / b.width, availH / b.height);
    // flipX 用 scale.x 负号, 缩放时保留符号
    const sx = this._flipped ? -Math.abs(s) : Math.abs(s);
    this._spine.scale.set(sx, Math.abs(s));
    // bounds 中心对齐容器中心
    this._spine.position.set(
      (cw - b.width * s) / 2 - b.x * s,
      (ch - b.height * s) / 2 - b.y * s,
    );
    this._emit('fit', { mode, scale: s });
  }

  /** 水平翻转（BA 立绘默认面朝左? 按需调整朝向）。 */
  flipX(on) {
    this._flipped = !!on;
    if (this._spine) this._spine.scale.x = this._flipped ? -Math.abs(this._spine.scale.x) : Math.abs(this._spine.scale.x);
  }

  setSkin(name) {
    if (!this._loaded || !this._spine) return false;
    if (!this._info.skins.includes(name)) return false;
    this._spine.skeleton.setSkinByName(name);
    this._spine.skeleton.setSlotsToSetupPose();
    return true;
  }

  setTimeScale(s) {
    if (!this._loaded || !this._spine) return;
    this._spine.state.timeScale = s;
  }

  setAlpha(a) {
    this._alpha = a;
    if (this._spine) this._spine.alpha = a;
  }

  show() { if (this._spine) this._spine.visible = true; }
  hide() { if (this._spine) this._spine.visible = false; }

  // ── 查询 ──────────────────────────────────────────────────────────────

  get loaded() { return this._loaded; }
  get animations() { return this._info ? this._info.animations : []; }
  get skins() { return this._info ? this._info.skins : []; }
  get bones() { return this._info ? this._info.bones : 0; }

  get currentAnimation() {
    if (!this._loaded || !this._spine) return null;
    const entry = this._spine.state.getCurrent(0);
    return entry ? entry.animation.name : null;
  }

  /** 底层渲染对象（高级操作逃生舱）。 */
  get skeleton() { return this._spine; }

  /** 底层 AnimationState（track 操作逃生舱）。 */
  get state() { return this._loaded && this._spine ? this._spine.state : null; }

  get emotionMap() { return this._emotionMap ? { ...this._emotionMap } : null; }

  // ── 内部 ──────────────────────────────────────────────────────────────

  _emit(type, detail = {}) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }
}

// ---------------------------------------------------------------------------
// 便捷工厂: 一步 mount + load（不关心两阶段的调用方用这个）
// ---------------------------------------------------------------------------

/**
 * @param {HTMLElement} container
 * @param {{ skel: string, atlas: string } | string} pack
 * @param {{ autoFit?: boolean, emotionMap?: Record<string,string> }} [opts]
 */
export async function createSpinePlayer(container, pack, opts = {}) {
  const player = new SpinePlayer();
  await player.mount(container, opts);
  try {
    await player.load(pack, opts);
  } catch (e) {
    player.destroy();
    throw e;
  }
  return player;
}
