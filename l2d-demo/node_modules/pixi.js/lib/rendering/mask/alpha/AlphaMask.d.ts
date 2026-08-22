import type { ExtensionMetadata } from '../../../extensions/Extensions';
import type { MaskChannel } from '../../../filters/mask/MaskFilter';
import type { Point } from '../../../maths/point/Point';
import type { Bounds } from '../../../scene/container/bounds/Bounds';
import type { Container } from '../../../scene/container/Container';
import type { Effect } from '../../../scene/container/Effect';
import type { PoolItem } from '../../../utils/pool/Pool';
/**
 * AlphaMask is an effect that applies a mask to a container using a sprite texture.
 * By default, the red channel of the mask texture controls visibility. Set `channel` to `'alpha'`
 * to use the alpha channel instead, which is useful for masks defined by transparency.
 * The mask can be inverted, and non-sprite masks are rendered to a texture automatically.
 * @category rendering
 * @advanced
 */
export declare class AlphaMask implements Effect, PoolItem {
    static extension: ExtensionMetadata;
    priority: number;
    mask: Container;
    inverse: boolean;
    channel: MaskChannel;
    pipe: string;
    renderMaskToTexture: boolean;
    constructor(options?: {
        mask: Container;
    });
    init(mask: Container): void;
    reset(): void;
    addBounds(bounds: Bounds, skipUpdateTransform?: boolean): void;
    addLocalBounds(bounds: Bounds, localRoot: Container): void;
    containsPoint(point: Point, hitTestFn: (container: Container, point: Point) => boolean): boolean;
    destroy(): void;
    static test(mask: any): boolean;
}
