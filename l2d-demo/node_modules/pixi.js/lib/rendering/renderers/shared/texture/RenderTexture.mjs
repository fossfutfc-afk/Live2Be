import { TextureSource } from './sources/TextureSource.mjs';
import { Texture } from './Texture.mjs';

"use strict";
class RenderTexture extends Texture {
  /**
   * Creates a RenderTexture. Pass `dynamic: true` in options to allow resizing after creation.
   * @param options - Options for the RenderTexture, including width, height, textureOptions, and dynamic.
   * @returns A new RenderTexture instance.
   * @example
   * const textureOptions = { defaultAnchor: { x: 0.5, y: 0.5 } };
   * const rt = RenderTexture.create({ width: 100, height: 100, dynamic: true, textureOptions });
   * rt.resize(500, 500);
   */
  static create(options) {
    const { dynamic, textureOptions, ...rest } = options;
    return new RenderTexture({
      ...textureOptions,
      source: new TextureSource(rest),
      dynamic: dynamic ?? false
    });
  }
  /**
   * Resizes the render texture.
   * @param width - The new width of the render texture.
   * @param height - The new height of the render texture.
   * @param resolution - The new resolution of the render texture.
   * @returns This texture.
   */
  resize(width, height, resolution) {
    this.source.resize(width, height, resolution);
    return this;
  }
}

export { RenderTexture };
//# sourceMappingURL=RenderTexture.mjs.map
