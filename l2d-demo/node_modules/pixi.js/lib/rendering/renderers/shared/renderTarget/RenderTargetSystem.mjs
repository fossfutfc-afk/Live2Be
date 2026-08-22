import { Matrix } from '../../../../maths/matrix/Matrix.mjs';
import { Rectangle } from '../../../../maths/shapes/Rectangle.mjs';
import { deprecation } from '../../../../utils/logging/deprecation.mjs';
import { warn } from '../../../../utils/logging/warn.mjs';
import { CLEAR } from '../../gl/const.mjs';
import { calculateProjection } from '../../gpu/renderTarget/calculateProjection.mjs';
import { RendererType } from '../../types.mjs';
import { SystemRunner } from '../system/SystemRunner.mjs';
import { CanvasSource } from '../texture/sources/CanvasSource.mjs';
import { TextureSource } from '../texture/sources/TextureSource.mjs';
import { Texture } from '../texture/Texture.mjs';
import { getCanvasTexture } from '../texture/utils/getCanvasTexture.mjs';
import { isRenderingToScreen } from './isRenderingToScreen.mjs';
import { RenderTarget } from './RenderTarget.mjs';

"use strict";
class RenderTargetSystem {
  constructor(renderer) {
    /** This is the root viewport for the render pass */
    this.rootViewPort = new Rectangle();
    /** the current viewport that the gpu is using */
    this.viewport = new Rectangle();
    /**
     * a runner that lets systems know if the active render target has changed.
     * Eg the Stencil System needs to know so it can manage the stencil buffer
     */
    this.onRenderTargetChange = new SystemRunner("onRenderTargetChange");
    /** the projection matrix that is used by the shaders based on the active render target and the viewport */
    this.projectionMatrix = new Matrix();
    /** the default clear color for render targets */
    this.defaultClearColor = [0, 0, 0, 0];
    /**
     * a hash that stores the render target for a given render surface. When you pass in a texture source,
     * a render target is created for it. This map stores and makes it easy to retrieve the render target
     */
    this._renderSurfaceToRenderTargetHash = /* @__PURE__ */ new Map();
    /** A hash that stores a gpu render target for a given render target. */
    this._gpuRenderTargetHash = /* @__PURE__ */ Object.create(null);
    /** the pushed bindings; each entry is a replayable BindOptions that pop() re-binds */
    this._renderTargetStack = [];
    /**
     * the state of the current binding, written on every bind — backs the `renderSurface`,
     * `mipLevel` and `layer` getters and `getBindState`. Its `frame` aliases `_bindFrame`
     * and must never be handed out by reference.
     */
    this._bindState = {
      target: null,
      frame: void 0,
      mipLevel: 0,
      layer: 0,
      flipY: false
    };
    /** system-owned rect backing `_bindState.frame`; as-passed frames are copied into it */
    this._bindFrame = new Rectangle();
    this._renderer = renderer;
    renderer.gc.addCollection(this, "_gpuRenderTargetHash", "hash");
  }
  /** the current active render surface that the render target is created from */
  get renderSurface() {
    return this._bindState.target;
  }
  /** the current mip level being rendered to (for texture subresources) */
  get mipLevel() {
    return this._bindState.mipLevel;
  }
  /** the current array layer being rendered to (for array-backed targets) */
  get layer() {
    return this._bindState.layer;
  }
  /** called when dev wants to finish a render pass */
  finishRenderPass() {
    this.adaptor.finishRenderPass(this.renderTarget);
  }
  /**
   * called when the renderer starts to render a scene: resets the bind stack and binds the
   * root render surface
   * @param options - the {@link BindOptions} for the root binding
   */
  renderStart(options) {
    this._renderTargetStack.length = 0;
    this.push(options);
    this.rootViewPort.copyFrom(this.viewport);
    this.rootRenderTarget = this.renderTarget;
    this.renderingToScreen = isRenderingToScreen(this.rootRenderTarget);
    this.adaptor.prerender?.(this.rootRenderTarget);
  }
  postrender() {
    this.adaptor.postrender?.(this.rootRenderTarget);
  }
  bind(surfaceOrOptions, clear = true, clearColor, frame, mipLevel = 0, layer = 0, flipY) {
    let options;
    if ("target" in surfaceOrOptions) {
      options = surfaceOrOptions;
    } else {
      deprecation("8.20.0", "RenderTargetSystem.bind: positional arguments are deprecated, please use an options object instead: bind({ target, clear, clearColor, frame, mipLevel, layer, flipY })");
      options = { target: surfaceOrOptions, clear, clearColor, frame, mipLevel, layer, flipY };
    }
    const renderSurface = options.target;
    clear = options.clear ?? true;
    clearColor = options.clearColor;
    mipLevel = (options.mipLevel ?? 0) | 0;
    layer = (options.layer ?? 0) | 0;
    flipY = options.flipY;
    frame = options.frame;
    const renderTarget = this.getRenderTarget(renderSurface);
    const didChange = this.renderTarget !== renderTarget;
    this.renderTarget = renderTarget;
    const gpuRenderTarget = this.getGpuRenderTarget(renderTarget);
    if (renderTarget.pixelWidth !== gpuRenderTarget.width || renderTarget.pixelHeight !== gpuRenderTarget.height) {
      this.adaptor.resizeGpuRenderTarget(renderTarget);
      gpuRenderTarget.width = renderTarget.pixelWidth;
      gpuRenderTarget.height = renderTarget.pixelHeight;
    }
    const source = renderTarget.colorAttachments[0]?.texture || renderTarget.depthStencilAttachment?.texture;
    const viewport = this.viewport;
    const arrayLayerCount = source.arrayLayerCount || 1;
    if (layer < 0 || layer >= arrayLayerCount) {
      throw new Error(`[RenderTargetSystem] layer ${layer} is out of bounds (arrayLayerCount=${arrayLayerCount}).`);
    }
    const bindState = this._bindState;
    bindState.target = renderSurface;
    bindState.frame = frame ? this._bindFrame.copyFrom(frame) : void 0;
    bindState.mipLevel = mipLevel;
    bindState.layer = layer;
    bindState.flipY = flipY;
    const pixelWidth = Math.max(source.pixelWidth >> mipLevel, 1);
    const pixelHeight = Math.max(source.pixelHeight >> mipLevel, 1);
    if (!frame && renderSurface instanceof Texture) {
      frame = renderSurface.frame;
    }
    if (frame) {
      const resolution = source._resolution;
      const scale = 1 << Math.max(mipLevel, 0);
      const baseX = frame.x * resolution + 0.5 | 0;
      const baseY = frame.y * resolution + 0.5 | 0;
      const baseW = frame.width * resolution + 0.5 | 0;
      const baseH = frame.height * resolution + 0.5 | 0;
      let x = Math.floor(baseX / scale);
      let y = Math.floor(baseY / scale);
      let w = Math.ceil(baseW / scale);
      let h = Math.ceil(baseH / scale);
      if (x < 0) {
        w += x;
        x = 0;
      }
      if (y < 0) {
        h += y;
        y = 0;
      }
      x = Math.min(x, pixelWidth - 1);
      y = Math.min(y, pixelHeight - 1);
      w = Math.min(w, pixelWidth - x);
      h = Math.min(h, pixelHeight - y);
      w = Math.max(w, 1);
      h = Math.max(h, 1);
      viewport.x = x;
      viewport.y = y;
      viewport.width = w;
      viewport.height = h;
    } else {
      viewport.x = 0;
      viewport.y = 0;
      viewport.width = pixelWidth;
      viewport.height = pixelHeight;
    }
    renderTarget.flipY = flipY;
    calculateProjection(
      this.projectionMatrix,
      0,
      0,
      viewport.width / source.resolution,
      viewport.height / source.resolution,
      !renderTarget.isRoot !== !!renderTarget.flipY
    );
    this.adaptor.startRenderPass(renderTarget, clear, clearColor, viewport, mipLevel, layer);
    if (didChange) {
      this.onRenderTargetChange.emit(renderTarget);
    }
    return renderTarget;
  }
  /**
   * Captures the current binding as a {@link BindOptions} that can be passed back to
   * {@link RenderTargetSystem.bind} to restore it. The capture replays non-destructively:
   * its `clear` is `CLEAR.NONE`, so restoring never wipes the target.
   *
   * ```js
   * const saved = renderer.renderTarget.getBindState();
   *
   * renderer.renderTarget.bind({ target: scratchTexture, clear: true });
   * // ... draw ...
   * renderer.renderTarget.bind(saved);
   *
   * // or compose: the saved binding, but into mip 1
   * renderer.renderTarget.bind({ ...saved, mipLevel: 1 });
   * ```
   *
   * The capture is a snapshot owned by the caller — later binds cannot change it — and holds
   * `target` and `frame` as they were passed, so a Texture bound without an explicit frame
   * replays through its frame fallback. It stays valid for as long as its target does.
   * Pass `out` to reuse one object across captures; every field of it is overwritten.
   * @param out - an optional object to write the bind state into; allocated when omitted
   * @returns the captured bind state (`out` when provided)
   */
  getBindState(out) {
    if (!this.renderTarget) {
      throw new Error("[RenderTargetSystem] getBindState is only valid while a render surface is bound");
    }
    const bindState = this._bindState;
    out ?? (out = {});
    out.target = bindState.target;
    out.clear = CLEAR.NONE;
    out.clearColor = void 0;
    if (!bindState.frame) {
      out.frame = void 0;
    } else if (out.frame) {
      out.frame.copyFrom(bindState.frame);
    } else {
      out.frame = bindState.frame.clone();
    }
    out.mipLevel = bindState.mipLevel;
    out.layer = bindState.layer;
    out.flipY = !!bindState.flipY;
    return out;
  }
  /**
   * The effective front-face orientation of the current bind — `true` when a front-facing triangle
   * ends up wound the opposite way on the surface (so the winding/cull has been inverted to compensate).
   *
   * This is the requested `flipY` combined with the backend's inherent orientation, not the raw request:
   *
   * ```text
   * frontFaceInverted = flipY XOR (isWebGL && !isRoot)
   * ```
   *
   * WebGL's non-root FBOs carry an inherent Y-flip vs the root (the classic render-texture flip), so the
   * same requested `flipY` lands with the opposite winding depending on `isRoot`. WebGPU has no such
   * inherent flip, so there it is simply `flipY`. This is exactly the winding inversion each backend bakes
   * at bind ({@link GlStateSystem} / {@link PipelineSystem}), exposed so consumers (e.g. 3D pipelines) can
   * read the resolved orientation instead of re-deriving it from `flipY`, `isRoot`, and a backend check of
   * their own.
   *
   * It is per-bind, not per-target: `flipY` is set on every `bind`/`renderStart` while `isRoot` is fixed on
   * the target, so this recomputes from whatever the last bind resolved.
   * @returns whether the current bind's front face is inverted
   */
  get frontFaceInverted() {
    const renderTarget = this.renderTarget;
    if (!renderTarget) return false;
    const glInherentFlip = this._renderer.type === RendererType.WEBGL && !renderTarget.isRoot;
    return !!renderTarget.flipY !== glInherentFlip;
  }
  clear(target, clear = CLEAR.ALL, clearColor, mipLevel = this.mipLevel, layer = this.layer) {
    if (!clear) return;
    if (target) {
      target = this.getRenderTarget(target);
    }
    this.adaptor.clear(
      target || this.renderTarget,
      clear,
      clearColor,
      this.viewport,
      mipLevel,
      layer
    );
  }
  contextChange() {
    this._gpuRenderTargetHash = /* @__PURE__ */ Object.create(null);
  }
  push(surfaceOrOptions, clear = CLEAR.ALL, clearColor, frame, mipLevel = 0, layer = 0, flipY) {
    let options;
    if ("target" in surfaceOrOptions) {
      options = surfaceOrOptions;
    } else {
      deprecation("8.20.0", "RenderTargetSystem.push: positional arguments are deprecated, please use an options object instead: push({ target, clear, clearColor, frame, mipLevel, layer, flipY })");
      options = { target: surfaceOrOptions, clear, clearColor, frame, mipLevel, layer, flipY };
    }
    const renderTarget = this.bind(options);
    this._renderTargetStack.push({
      target: options.target,
      clear: false,
      clearColor: void 0,
      frame: options.frame ? options.frame.clone() : void 0,
      mipLevel: options.mipLevel,
      layer: options.layer,
      flipY: options.flipY
    });
    return renderTarget;
  }
  /**
   * Pops the current render target and restores the previous binding.
   * @returns the render target that was restored
   */
  pop() {
    this._renderTargetStack.pop();
    const previous = this._renderTargetStack[this._renderTargetStack.length - 1];
    if (!previous) {
      throw new Error("[RenderTargetSystem] pop: no previous binding to restore (unbalanced pop)");
    }
    return this.bind(previous);
  }
  /**
   * Gets the render target from the provide render surface. Eg if its a texture,
   * it will return the render target for the texture.
   * If its a render target, it will return the same render target.
   * @param renderSurface - the render surface to get the render target for
   * @returns the render target for the render surface
   */
  getRenderTarget(renderSurface) {
    if (renderSurface.isTexture) {
      renderSurface = renderSurface.source;
    }
    return this._renderSurfaceToRenderTargetHash.get(renderSurface) ?? this._initRenderTarget(renderSurface);
  }
  /**
   * Copies a render surface to another texture.
   *
   * NOTE:
   * for sourceRenderSurfaceTexture, The render target must be something that is written too by the renderer
   *
   * The following is not valid:
   * @example
   * const canvas = document.createElement('canvas')
   * canvas.width = 200;
   * canvas.height = 200;
   *
   * const ctx = canvas2.getContext('2d')!
   * ctx.fillStyle = 'red'
   * ctx.fillRect(0, 0, 200, 200);
   *
   * const texture = RenderTexture.create({
   *   width: 200,
   *   height: 200,
   * })
   * const renderTarget = renderer.renderTarget.getRenderTarget(canvas2);
   *
   * renderer.renderTarget.copyToTexture(renderTarget,texture, {x:0,y:0},{width:200,height:200},{x:0,y:0});
   *
   * The best way to copy a canvas is to create a texture from it. Then render with that.
   *
   * Parsing in a RenderTarget canvas context (with a 2d context)
   * @param sourceRenderSurface - the render surface (render target, texture, or canvas) to copy from
   * @param {Texture} destinationTexture - the texture to copy to
   * @param {object} originSrc - the origin of the copy
   * @param {number} originSrc.x - the x origin of the copy
   * @param {number} originSrc.y - the y origin of the copy
   * @param {object} size - the size of the copy
   * @param {number} size.width - the width of the copy
   * @param {number} size.height - the height of the copy
   * @param {object} originDest - the destination origin (top left to paste from!)
   * @param {number} originDest.x - the x origin of the paste
   * @param {number} originDest.y - the y origin of the paste
   */
  copyToTexture(sourceRenderSurface, destinationTexture, originSrc, size, originDest) {
    const sourceRenderTarget = this.getRenderTarget(sourceRenderSurface);
    if (originSrc.x < 0) {
      size.width += originSrc.x;
      originDest.x -= originSrc.x;
      originSrc.x = 0;
    }
    if (originSrc.y < 0) {
      size.height += originSrc.y;
      originDest.y -= originSrc.y;
      originSrc.y = 0;
    }
    const { pixelWidth, pixelHeight } = sourceRenderTarget;
    size.width = Math.min(size.width, pixelWidth - originSrc.x);
    size.height = Math.min(size.height, pixelHeight - originSrc.y);
    return this.adaptor.copyToTexture(
      sourceRenderTarget,
      destinationTexture,
      originSrc,
      size,
      originDest
    );
  }
  /**
   * Copies the depth attachment from one render target to another.
   * Both source and destination must have a depthStencilAttachment.
   *
   * **Important Note:** When using the copied depth buffer in a subsequent render pass,
   * you must ensure you do not clear the depth buffer again. If you need to clear the color
   * buffer of the destination render target, use `clear: CLEAR.COLOR` to preserve the copied depth data.
   * @example
   * ```js
   * renderer.renderTarget.copyDepthTexture(
   *   sourceRT, destRT, { x: 0, y: 0 }, { width: 200, height: 200 }, { x: 0, y: 0 }
   * );
   *
   * // In the subsequent render pass, clear ONLY the color buffer!
   * renderer.render({
   *   target: destRT,
   *   container: myMesh,
   *   clear: CLEAR.COLOR, // Preserves the copied depth
   *   clearColor: [0, 0, 0, 1]
   * });
   * ```
   * @param source - the render surface (render target, depth texture, or canvas) to copy depth from
   * @param destination - the depth/stencil texture to copy depth to
   * @param {object} originSrc - the origin of the copy
   * @param {number} originSrc.x - the x origin of the copy
   * @param {number} originSrc.y - the y origin of the copy
   * @param {object} size - the size of the copy
   * @param {number} size.width - the width of the copy
   * @param {number} size.height - the height of the copy
   * @param {object} originDest - the destination origin (top left to paste from!)
   * @param {number} originDest.x - the x origin of the paste
   * @param {number} originDest.y - the y origin of the paste
   */
  copyDepthTexture(source, destination, originSrc, size, originDest = { x: 0, y: 0 }) {
    const sourceRenderTarget = this.getRenderTarget(source);
    if (!sourceRenderTarget.depthStencilAttachment) {
      warn("[RenderTargetSystem] copyDepthTexture: the source render target has no depth attachment to copy from");
      return;
    }
    const destSource = destination.source;
    if (!destSource.format.includes("depth") && !destSource.format.includes("stencil")) {
      warn(`[RenderTargetSystem] copyDepthTexture: the destination texture must have a depth/stencil format (got '${destSource.format}')`);
      return;
    }
    let srcX = originSrc.x;
    let srcY = originSrc.y;
    let destX = originDest.x;
    let destY = originDest.y;
    let width = size.width;
    let height = size.height;
    if (srcX < 0) {
      width += srcX;
      destX -= srcX;
      srcX = 0;
    }
    if (srcY < 0) {
      height += srcY;
      destY -= srcY;
      srcY = 0;
    }
    width = Math.min(width, sourceRenderTarget.pixelWidth - srcX);
    height = Math.min(height, sourceRenderTarget.pixelHeight - srcY);
    width = Math.min(width, destSource.pixelWidth - destX);
    height = Math.min(height, destSource.pixelHeight - destY);
    if (width <= 0 || height <= 0) return;
    this.adaptor.copyDepthTexture(
      sourceRenderTarget,
      destination,
      { x: srcX, y: srcY },
      { width, height },
      { x: destX, y: destY }
    );
  }
  /**
   * ensures that we have a depth stencil buffer available to render to
   * This is used by the mask system to make sure we have a stencil buffer.
   */
  ensureDepthStencil() {
    if (!this.renderTarget.stencil) {
      if (this.renderTarget.depthStencilTexture) {
        warn(`[RenderTargetSystem] a stencil mask is being used, but the render target's depthStencilTexture format '${this.renderTarget.depthStencilTexture.format}' has no stencil aspect, so masking cannot work here. Use a 'depth24plus-stencil8' texture instead.`);
        return;
      }
      this.renderTarget._depth = true;
      this.renderTarget._stencil = true;
      this.adaptor.startRenderPass(this.renderTarget, false, null, this.viewport, 0, this.layer);
    }
  }
  /** nukes the render target system */
  destroy() {
    this._renderer = null;
    this._renderSurfaceToRenderTargetHash.forEach((renderTarget, key) => {
      if (renderTarget !== key) {
        this._releaseRenderTarget(key, renderTarget);
      }
    });
    this._renderSurfaceToRenderTargetHash.clear();
    this._gpuRenderTargetHash = /* @__PURE__ */ Object.create(null);
  }
  _initRenderTarget(renderSurface) {
    let renderTarget = null;
    if (CanvasSource.test(renderSurface)) {
      renderSurface = getCanvasTexture(renderSurface).source;
    }
    if (renderSurface instanceof RenderTarget) {
      renderTarget = renderSurface;
    } else if (renderSurface instanceof TextureSource) {
      const format = renderSurface.format;
      const isDepthStencil = format.includes("depth") || format.includes("stencil");
      renderTarget = isDepthStencil ? new RenderTarget({ colorTextures: 0, depthStencilTexture: renderSurface }) : new RenderTarget({ colorTextures: [renderSurface] });
      if (renderSurface.source instanceof CanvasSource) {
        renderTarget.isRoot = true;
      }
      renderSurface.once("destroy", this._onRenderSurfaceDestroy, this);
    }
    this._renderSurfaceToRenderTargetHash.set(renderSurface, renderTarget);
    return renderTarget;
  }
  _onRenderSurfaceDestroy(renderSurface) {
    const renderTarget = this._renderSurfaceToRenderTargetHash.get(renderSurface);
    if (renderTarget) this._releaseRenderTarget(renderSurface, renderTarget);
  }
  /**
   * Tears down a render target that wraps a texture source, removing every reference the
   * system holds to it so neither the system's own teardown nor the source's `destroy`
   * event can destroy it a second time.
   * @param renderSurface - the texture source the render target wraps
   * @param renderTarget - the render target to release
   */
  _releaseRenderTarget(renderSurface, renderTarget) {
    renderTarget.destroy();
    this._renderSurfaceToRenderTargetHash.delete(renderSurface);
    renderSurface.off("destroy", this._onRenderSurfaceDestroy, this);
    const gpuRenderTarget = this._gpuRenderTargetHash[renderTarget.uid];
    if (gpuRenderTarget) {
      this._gpuRenderTargetHash[renderTarget.uid] = null;
      this.adaptor.destroyGpuRenderTarget(gpuRenderTarget);
    }
  }
  getGpuRenderTarget(renderTarget) {
    return this._gpuRenderTargetHash[renderTarget.uid] || (this._gpuRenderTargetHash[renderTarget.uid] = this.adaptor.initGpuRenderTarget(renderTarget));
  }
  resetState() {
    this.renderTarget = null;
    this._bindState.target = null;
  }
}

export { RenderTargetSystem };
//# sourceMappingURL=RenderTargetSystem.mjs.map
