import { ExtensionType } from '../extensions/Extensions.mjs';
import { TextureSource } from '../rendering/renderers/shared/texture/sources/TextureSource.mjs';

"use strict";
function isElementImage(resource) {
  const ElementImageCtor = globalThis.ElementImage;
  return !!ElementImageCtor && resource instanceof ElementImageCtor;
}
class ElementImageSource extends TextureSource {
  /**
   * @param options - Options for creating the snapshot source. `resource` is required.
   * @example
   * ```ts
   * const source = new ElementImageSource({
   *     resource: snapshot, // an ElementImage from captureElementImage()
   *     autoClose: true,    // close the snapshot when this source is destroyed
   * });
   * ```
   */
  constructor(options) {
    if (!options.resource) {
      throw new Error("[ElementImageSource] resource is required.");
    }
    super(options);
    /** The upload method for this texture. */
    this.uploadMethodId = "html";
    /** Snapshots are immutable, so the source is ready as soon as it is constructed. */
    this.isReady = true;
    this._autoClose = options.autoClose === true;
  }
  /**
   * Tests whether a resource is an {@link ElementImage} snapshot, used during automatic
   * source detection (`Texture.from`, `TextureSource.from`).
   * @param resource - The resource to test.
   * @returns `true` if this source can handle the resource.
   */
  static test(resource) {
    return isElementImage(resource);
  }
  /**
   * The width of the snapshot in pixels, rounded up.
   * @example
   * ```ts
   * const source = new ElementImageSource({ resource: snapshot });
   *
   * console.log(source.resourceWidth, source.resourceHeight);
   * ```
   */
  get resourceWidth() {
    return Math.ceil(this.resource.width);
  }
  /**
   * The height of the snapshot in pixels, rounded up.
   * @example
   * ```ts
   * const source = new ElementImageSource({ resource: snapshot });
   *
   * console.log(source.resourceWidth, source.resourceHeight);
   * ```
   */
  get resourceHeight() {
    return Math.ceil(this.resource.height);
  }
  /**
   * Destroys the underlying texture source. When {@link ElementImageSourceOptions.autoClose}
   * was set, also calls {@link ElementImage.close} on the snapshot.
   * @example
   * ```ts
   * const source = new ElementImageSource({ resource: snapshot });
   *
   * source.destroy();
   * snapshot.close(); // release the snapshot yourself unless autoClose was set
   * ```
   */
  destroy() {
    const snapshot = this.resource;
    super.destroy();
    if (this._autoClose && snapshot) {
      snapshot.close();
    }
  }
}
/**
 * Registers the source with the {@link extensions} system at the lowest texture-source
 * priority, so automatic detection only falls back to it when no other built-in source
 * claims the resource.
 */
ElementImageSource.extension = {
  type: ExtensionType.TextureSource,
  priority: -10
};

export { ElementImageSource };
//# sourceMappingURL=ElementImageSource.mjs.map
