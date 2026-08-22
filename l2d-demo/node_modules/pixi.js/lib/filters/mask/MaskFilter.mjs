import { Matrix } from '../../maths/matrix/Matrix.mjs';
import { GlProgram } from '../../rendering/renderers/gl/shader/GlProgram.mjs';
import { GpuProgram } from '../../rendering/renderers/gpu/shader/GpuProgram.mjs';
import { UniformGroup } from '../../rendering/renderers/shared/shader/UniformGroup.mjs';
import { Texture } from '../../rendering/renderers/shared/texture/Texture.mjs';
import { TextureMatrix } from '../../rendering/renderers/shared/texture/TextureMatrix.mjs';
import { warn } from '../../utils/logging/warn.mjs';
import { Filter } from '../Filter.mjs';
import fragment from './mask.frag.mjs';
import vertex from './mask.vert.mjs';
import source from './mask.wgsl.mjs';

"use strict";
class MaskFilter extends Filter {
  constructor(options) {
    const { sprite, ...rest } = options;
    const textureMatrix = new TextureMatrix(sprite.texture);
    const filterUniforms = new UniformGroup({
      uFilterMatrix: { value: new Matrix(), type: "mat3x3<f32>" },
      uMaskClamp: { value: textureMatrix.uClampFrame, type: "vec4<f32>" },
      uAlpha: { value: 1, type: "f32" },
      uInverse: { value: options.inverse ? 1 : 0, type: "f32" },
      uChannel: { value: options.channel === "alpha" ? 1 : 0, type: "f32" }
    });
    const gpuProgram = GpuProgram.from({
      vertex: {
        source,
        entryPoint: "mainVertex"
      },
      fragment: {
        source,
        entryPoint: "mainFragment"
      }
    });
    const glProgram = GlProgram.from({
      vertex,
      fragment,
      name: "mask-filter"
    });
    super({
      ...rest,
      gpuProgram,
      glProgram,
      clipToViewport: false,
      resources: {
        filterUniforms,
        uMaskTexture: sprite.texture.source
      }
    });
    this.sprite = sprite;
    this._textureMatrix = textureMatrix;
  }
  /**
   * Rebinds the filter to a new mask sprite, moving the texture-matrix `update`
   * listener and the bind group's `change` subscription over to the new sprite's
   * texture. `apply` refreshes the same bindings on every use — this method exists
   * to release the previous sprite's texture immediately, without waiting for
   * (or requiring) another `apply`.
   * @param sprite - the sprite to mask with from now on.
   */
  setSprite(sprite) {
    this.sprite = sprite;
    const texture = this._getSafeTexture();
    this._textureMatrix.texture = texture;
    this.resources.uMaskTexture = texture.source;
  }
  set inverse(value) {
    this.resources.filterUniforms.uniforms.uInverse = value ? 1 : 0;
  }
  get inverse() {
    return this.resources.filterUniforms.uniforms.uInverse === 1;
  }
  set channel(value) {
    this.resources.filterUniforms.uniforms.uChannel = value === "alpha" ? 1 : 0;
  }
  get channel() {
    return this.resources.filterUniforms.uniforms.uChannel === 1 ? "alpha" : "red";
  }
  apply(filterManager, input, output, clearMode) {
    const texture = this._getSafeTexture();
    this._textureMatrix.texture = texture;
    filterManager.calculateSpriteMatrix(
      this.resources.filterUniforms.uniforms.uFilterMatrix,
      this.sprite
    ).prepend(this._textureMatrix.mapCoord);
    this.resources.uMaskTexture = texture.source;
    filterManager.applyFilter(this, input, output, clearMode);
  }
  /**
   * The sprite's texture, or `Texture.EMPTY` when that texture has been destroyed —
   * a destroyed texture has no source left to sample, so the mask degrades to empty
   * rather than crashing the render.
   */
  _getSafeTexture() {
    const texture = this.sprite.texture;
    if (texture.destroyed || !texture.source || texture.source.destroyed) {
      warn("[MaskFilter] The mask texture was destroyed while the mask is still in use. Remove the mask before destroying its texture.");
      return Texture.EMPTY;
    }
    return texture;
  }
  destroy(destroyPrograms = false) {
    this._textureMatrix.destroy();
    super.destroy(destroyPrograms);
  }
}

export { MaskFilter };
//# sourceMappingURL=MaskFilter.mjs.map
