import EventEmitter from 'eventemitter3';
import type { BindResource } from '../../gpu/shader/BindResource';
import type { TextureSource } from './sources/TextureSource';
/**
 * A TextureView allows you to specify exactly how a `TextureSource` should be interpreted by the GPU.
 * This is particularly useful for advanced 3D rendering where you might need to view a depth/stencil
 * texture as purely a 'depth-only' or 'stencil-only' view.
 *
 * It implements `BindResource` so it can be passed directly into a `BindGroup` or `Shader`.
 * @category rendering
 * @advanced
 */
export declare class TextureView extends EventEmitter<{
    change: TextureView;
    destroy: TextureView;
}> implements BindResource {
    /** The type of resource this is (for BindGroup compatibility). */
    readonly _resourceType = "textureView";
    /** Unique ID for this resource. */
    readonly _resourceId: number;
    /** Used for GC. */
    _touched: number;
    /** The underlying texture source. */
    readonly source: TextureSource;
    /** The WebGPU texture view descriptor. */
    readonly viewDescriptor: GPUTextureViewDescriptor;
    /**
     * @param source - The texture source to view.
     * @param viewDescriptor - The WebGPU texture view descriptor.
     */
    constructor(source: TextureSource, viewDescriptor: GPUTextureViewDescriptor);
    private _onChange;
    private _onDestroy;
    /** Returns whether the underlying source is destroyed. */
    get destroyed(): boolean;
    /** Destroys the view and cleans up event listeners. */
    destroy(): void;
}
