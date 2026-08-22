import { ExtensionType } from '../../../extensions/Extensions.mjs';
import { FilterEffect } from '../../../filters/FilterEffect.mjs';
import { MaskFilter } from '../../../filters/mask/MaskFilter.mjs';
import { Bounds } from '../../../scene/container/bounds/Bounds.mjs';
import { getGlobalBounds } from '../../../scene/container/bounds/getGlobalBounds.mjs';
import { Sprite } from '../../../scene/sprite/Sprite.mjs';
import { BigPool } from '../../../utils/pool/PoolGroup.mjs';
import { Texture } from '../../renderers/shared/texture/Texture.mjs';
import { TexturePool } from '../../renderers/shared/texture/TexturePool.mjs';
import { RendererType } from '../../renderers/types.mjs';

"use strict";
const tempBounds = new Bounds();
class AlphaMaskEffect extends FilterEffect {
  constructor() {
    super();
    /** the sprite the pooled filter is parked on between uses */
    this._placeholderSprite = new Sprite(Texture.EMPTY);
    this.filters = [new MaskFilter({
      sprite: this._placeholderSprite,
      inverse: false,
      resolution: "inherit",
      antialias: "inherit"
    })];
  }
  get sprite() {
    return this.filters[0].sprite;
  }
  set sprite(value) {
    this.filters[0].setSprite(value);
  }
  get inverse() {
    return this.filters[0].inverse;
  }
  set inverse(value) {
    this.filters[0].inverse = value;
  }
  get channel() {
    return this.filters[0].channel;
  }
  set channel(value) {
    this.filters[0].channel = value;
  }
  /**
   * Called by {@link BigPool} when the pipe returns the effect: parks the filter
   * on the empty placeholder so a pooled effect keeps no bindings to the last
   * mask it applied. Without this, the pooled filter pins the mask sprite and
   * its texture for as long as the effect sits in the pool, and destroying that
   * texture's source hits a bind group subscription the user cannot release.
   */
  reset() {
    this._placeholderSprite.texture = Texture.EMPTY;
    this.sprite = this._placeholderSprite;
  }
}
class AlphaMaskPipe {
  constructor(renderer) {
    this._activeMaskStage = [];
    this._usedEffects = [];
    this._renderer = renderer;
    renderer.runners.postrender.add(this);
  }
  push(mask, maskedContainer, instructionSet) {
    const renderer = this._renderer;
    renderer.renderPipes.batch.break(instructionSet);
    instructionSet.add({
      renderPipeId: "alphaMask",
      action: "pushMaskBegin",
      mask,
      inverse: maskedContainer._maskOptions.inverse,
      canBundle: false,
      maskedContainer
    });
    mask.inverse = maskedContainer._maskOptions.inverse;
    mask.channel = maskedContainer._maskOptions.channel ?? "red";
    if (mask.renderMaskToTexture) {
      const maskContainer = mask.mask;
      maskContainer.includeInBuild = true;
      maskContainer.collectRenderables(
        instructionSet,
        renderer,
        null
      );
      maskContainer.includeInBuild = false;
    }
    renderer.renderPipes.batch.break(instructionSet);
    instructionSet.add({
      renderPipeId: "alphaMask",
      action: "pushMaskEnd",
      mask,
      maskedContainer,
      inverse: maskedContainer._maskOptions.inverse,
      canBundle: false
    });
  }
  pop(mask, _maskedContainer, instructionSet) {
    const renderer = this._renderer;
    renderer.renderPipes.batch.break(instructionSet);
    instructionSet.add({
      renderPipeId: "alphaMask",
      action: "popMaskEnd",
      mask,
      inverse: _maskedContainer._maskOptions.inverse,
      canBundle: false
    });
  }
  execute(instruction) {
    const renderer = this._renderer;
    const renderMask = instruction.mask.renderMaskToTexture;
    if (instruction.action === "pushMaskBegin") {
      const filterEffect = BigPool.get(AlphaMaskEffect);
      filterEffect.inverse = instruction.inverse;
      filterEffect.channel = instruction.mask.channel;
      if (renderMask) {
        instruction.mask.mask.measurable = true;
        const bounds = getGlobalBounds(instruction.mask.mask, true, tempBounds);
        instruction.mask.mask.measurable = false;
        bounds.ceil();
        const colorTextureSource = renderer.renderTarget.renderTarget.colorTexture.source;
        const filterTexture = TexturePool.getOptimalTexture(
          bounds.width,
          bounds.height,
          colorTextureSource._resolution,
          colorTextureSource.antialias
        );
        renderer.renderTarget.push({ target: filterTexture, clear: true });
        renderer.globalUniforms.push({
          offset: bounds,
          worldColor: 4294967295
        });
        const sprite = filterEffect.sprite;
        sprite.texture = filterTexture;
        sprite.worldTransform.tx = bounds.minX;
        sprite.worldTransform.ty = bounds.minY;
        this._activeMaskStage.push({
          filterEffect,
          maskedContainer: instruction.maskedContainer,
          filterTexture
        });
      } else {
        filterEffect.sprite = instruction.mask.mask;
        this._activeMaskStage.push({
          filterEffect,
          maskedContainer: instruction.maskedContainer
        });
      }
    } else if (instruction.action === "pushMaskEnd") {
      const maskData = this._activeMaskStage[this._activeMaskStage.length - 1];
      if (renderMask) {
        if (renderer.type === RendererType.WEBGL) {
          renderer.renderTarget.finishRenderPass();
        }
        renderer.renderTarget.pop();
        renderer.globalUniforms.pop();
      }
      renderer.filter.push({
        renderPipeId: "filter",
        action: "pushFilter",
        container: maskData.maskedContainer,
        filterEffect: maskData.filterEffect,
        canBundle: false
      });
    } else if (instruction.action === "popMaskEnd") {
      renderer.filter.pop();
      const maskData = this._activeMaskStage.pop();
      if (renderMask) {
        TexturePool.returnTexture(maskData.filterTexture);
      }
      this._usedEffects.push(maskData.filterEffect);
    }
  }
  postrender() {
    const effects = this._usedEffects;
    for (let i = 0; i < effects.length; i++) {
      BigPool.return(effects[i]);
    }
    effects.length = 0;
  }
  destroy() {
    this.postrender();
    this._renderer.runners.postrender.remove(this);
    this._renderer = null;
    this._activeMaskStage = null;
    this._usedEffects = null;
  }
}
/** @ignore */
AlphaMaskPipe.extension = {
  type: [
    ExtensionType.WebGLPipes,
    ExtensionType.WebGPUPipes,
    ExtensionType.CanvasPipes
  ],
  name: "alphaMask"
};

export { AlphaMaskPipe };
//# sourceMappingURL=AlphaMaskPipe.mjs.map
