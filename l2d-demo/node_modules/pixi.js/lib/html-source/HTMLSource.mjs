import { ExtensionType } from '../extensions/Extensions.mjs';
import { TextureSource } from '../rendering/renderers/shared/texture/sources/TextureSource.mjs';

"use strict";
function isCanvas(resource) {
  return !!globalThis.HTMLCanvasElement && resource instanceof HTMLCanvasElement;
}
const _HTMLSource = class _HTMLSource extends TextureSource {
  /**
   * @param options - Options for creating the HTML source. `resource` is required.
   * @example
   * ```ts
   * const source = new HTMLSource({
   *     resource: domElement,   // a direct child of the Pixi canvas
   *     autoUpdate: true,       // track browser repaints (default)
   *     autoRequestPaint: true, // request one initial paint (default)
   * });
   * ```
   */
  constructor(options) {
    options = { ..._HTMLSource.defaultOptions, ...options };
    if (!options.resource) {
      throw new Error("[HTMLSource] resource is required.");
    }
    super(options);
    /** The upload method for this texture. */
    this.uploadMethodId = "html";
    const canvas = options.canvas ?? this._inferCanvas(options.resource);
    if (!canvas) {
      throw new Error(
        // eslint-disable-next-line max-len
        "[HTMLSource] Could not determine the owning canvas. Append the element to the canvas before constructing this source, or pass the `canvas` option."
      );
    }
    if (options.resource.parentElement !== canvas) {
      throw new Error(
        // eslint-disable-next-line max-len
        "[HTMLSource] resource must be a direct child of the owning canvas. Append the element to the canvas before constructing this source."
      );
    }
    this.canvas = canvas;
    this._autoUpdate = options.autoUpdate !== false;
    this._onPaintBound = this._onPaint.bind(this);
    this._isReady = !this._autoUpdate || !canvas.requestPaint;
    if (options.autoLayout !== false) {
      canvas.setAttribute("layoutsubtree", "");
    }
    if (this._autoUpdate) {
      canvas.addEventListener("paint", this._onPaintBound);
    }
    if (options.autoRequestPaint !== false) {
      this.requestPaint();
    }
  }
  /**
   * Tests whether a resource should be handled by `HTMLSource` during automatic source
   * detection (`Texture.from`, `TextureSource.from`). Deliberately strict: only generic HTML
   * elements pass. Image, video, and canvas elements are rejected because they have
   * dedicated, faster sources; snapshots are handled by {@link ElementImageSource}.
   * @param resource - The resource to test.
   * @returns `true` if this source can handle the resource.
   */
  static test(resource) {
    return !!globalThis.HTMLElement && resource instanceof HTMLElement && !(resource instanceof HTMLImageElement) && !(resource instanceof HTMLVideoElement) && !(resource instanceof HTMLCanvasElement);
  }
  /**
   * `true` once the owning canvas has produced an initial paint snapshot, so the texture has
   * real pixels. Non-auto-updating sources are ready immediately.
   * @example
   * ```ts
   * const source = new HTMLSource({ resource: domElement });
   *
   * if (!source.isReady)
   * {
   *     // The first paint has not landed yet — the texture is still blank.
   * }
   * ```
   */
  get isReady() {
    return this._isReady;
  }
  /**
   * Request a `paint` event from the owning canvas. Call this every frame to keep an animated
   * or frequently-changing element in sync with the rendered texture.
   * @returns `true` if the request was made, `false` when the browser lacks the experimental
   * `requestPaint` API or there is no owning canvas.
   * @example
   * ```ts
   * const source = new HTMLSource({ resource: clock, autoRequestPaint: false });
   *
   * app.ticker.add(() => {
   *     clock.textContent = new Date().toLocaleTimeString();
   *     source.requestPaint();
   * });
   * ```
   */
  requestPaint() {
    if (!this.canvas?.requestPaint) {
      return false;
    }
    this.canvas.requestPaint();
    return true;
  }
  /**
   * Detaches the `paint` listener from the owning canvas and destroys the underlying texture
   * source.
   * @example
   * ```ts
   * const source = new HTMLSource({ resource: domElement });
   *
   * source.destroy();
   * ```
   */
  destroy() {
    if (this.canvas && this._autoUpdate) {
      this.canvas.removeEventListener("paint", this._onPaintBound);
    }
    this.canvas = null;
    super.destroy();
  }
  /** Width in real pixels (`offsetWidth`). Use {@link width} for CSS pixels. */
  get resourceWidth() {
    return this.resource.offsetWidth || 1;
  }
  /** Height in real pixels (`offsetHeight`). Use {@link height} for CSS pixels. */
  get resourceHeight() {
    return this.resource.offsetHeight || 1;
  }
  _inferCanvas(resource) {
    return isCanvas(resource.parentElement) ? resource.parentElement : null;
  }
  _onPaint(event) {
    const changedElements = event.changedElements;
    if (changedElements?.length && !changedElements.includes(this.resource)) {
      return;
    }
    this._isReady = true;
    this.update();
  }
};
/**
 * Registers the source with the {@link extensions} system at the lowest texture-source
 * priority, so automatic detection only falls back to it when no other built-in source
 * claims the resource.
 */
_HTMLSource.extension = {
  type: ExtensionType.TextureSource,
  priority: -10
};
/**
 * The default options applied to every {@link HTMLSource}, merged with the options passed
 * to the constructor.
 * @example
 * ```ts
 * // Make every HTMLSource opt out of automatic repaint tracking by default.
 * HTMLSource.defaultOptions.autoUpdate = false;
 * ```
 */
_HTMLSource.defaultOptions = {
  autoLayout: true,
  autoUpdate: true,
  autoRequestPaint: true
};
let HTMLSource = _HTMLSource;

export { HTMLSource };
//# sourceMappingURL=HTMLSource.mjs.map
