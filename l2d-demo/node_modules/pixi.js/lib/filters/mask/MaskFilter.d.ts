import { Texture } from '../../rendering/renderers/shared/texture/Texture';
import { Filter } from '../Filter';
import type { Sprite } from '../../scene/sprite/Sprite';
import type { FilterOptions } from '../Filter';
import type { FilterSystem } from '../FilterSystem';
/**
 * The channel to use for masking.
 * - `'red'` - Uses the red channel of the mask texture (default). Suitable for grayscale mask textures.
 * - `'alpha'` - Uses the alpha channel of the mask texture. Suitable for sprites with transparency.
 * @category rendering
 * @standard
 */
export type MaskChannel = 'red' | 'alpha';
/** @internal */
export interface MaskFilterOptions extends FilterOptions {
    sprite: Sprite;
    inverse?: boolean;
    channel?: MaskChannel;
    scale?: number | {
        x: number;
        y: number;
    };
}
/** @internal */
export declare class MaskFilter extends Filter {
    sprite: Sprite;
    private readonly _textureMatrix;
    constructor(options: MaskFilterOptions);
    /**
     * Rebinds the filter to a new mask sprite, moving the texture-matrix `update`
     * listener and the bind group's `change` subscription over to the new sprite's
     * texture. `apply` refreshes the same bindings on every use — this method exists
     * to release the previous sprite's texture immediately, without waiting for
     * (or requiring) another `apply`.
     * @param sprite - the sprite to mask with from now on.
     */
    setSprite(sprite: Sprite): void;
    set inverse(value: boolean);
    get inverse(): boolean;
    set channel(value: MaskChannel);
    get channel(): MaskChannel;
    apply(filterManager: FilterSystem, input: Texture, output: Texture, clearMode: boolean): void;
    /**
     * The sprite's texture, or `Texture.EMPTY` when that texture has been destroyed —
     * a destroyed texture has no source left to sample, so the mask degrades to empty
     * rather than crashing the render.
     */
    private _getSafeTexture;
    destroy(destroyPrograms?: boolean): void;
}
