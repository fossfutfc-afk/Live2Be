import { TextureSource } from '../texture/sources/TextureSource';
import type { BindableTexture } from '../texture/Texture';
/**
 * Options for creating a render target.
 * @category rendering
 * @advanced
 */
export interface RenderTargetOptions {
    /** the width of the RenderTarget */
    width?: number;
    /** the height of the RenderTarget */
    height?: number;
    /** the resolution of the RenderTarget */
    resolution?: number;
    /** an array of textures, or a number indicating how many color textures there should be */
    colorTextures?: BindableTexture[] | number;
    /** should this render target have a stencil buffer? */
    stencil?: boolean;
    /** should this render target have a depth buffer? */
    depth?: boolean;
    /** a depth stencil texture that the depth and stencil outputs will be written to */
    depthStencilTexture?: BindableTexture | boolean;
    /** a label for debugging — shows up on the render pass in GPU debuggers (WebGPU) */
    label?: string;
    /** should this render target be antialiased? */
    antialias?: boolean;
    /** is this a root element, true if this is gl context owners render target */
    isRoot?: boolean;
}
/**
 * Descriptor for creating a RenderTarget from a WebGPU-flavored descriptor.
 * @category rendering
 * @advanced
 */
export interface RenderTargetDescriptor {
    /** The color attachments to use */
    colorAttachments: PixiColorAttachment[];
    /** The depth/stencil attachment to use */
    depthStencilAttachment?: PixiDepthStencilAttachment;
    /** Is this a root element, true if this is gl context owners render target */
    isRoot?: boolean;
    /** a label for debugging — shows up on the render pass in GPU debuggers (WebGPU) */
    label?: string;
}
/**
 * A Pixi-flavored Color Attachment that mirrors the WebGPU spec but replaces low-level JIT requirements
 * with high-level Pixi objects (like `texture`).
 * @example
 * ```typescript
 * import { RenderTarget, TextureSource } from 'pixi.js';
 *
 * const renderTarget = new RenderTarget({
 *     colorAttachments: [{
 *         texture: new TextureSource({ width: 100, height: 100 }),
 *         loadOp: 'clear', // Clears the texture before rendering
 *         clearValue: [1, 0, 0, 1], // Clears to red
 *     }]
 * });
 * ```
 * @category rendering
 * @advanced
 */
export interface PixiColorAttachment extends Omit<GPURenderPassColorAttachment, 'view' | 'resolveTarget'> {
    /** The Pixi texture to render to. */
    texture: TextureSource;
    /**
     * Optional overrides for how the GPU views the texture (e.g., viewing a specific aspect or dimension).
     * Rarely needed for 2D, but incredibly powerful for 3D and advanced compute pipelines.
     */
    viewDescriptor?: GPUTextureViewDescriptor;
}
/**
 * A Pixi-flavored Depth/Stencil Attachment that mirrors the WebGPU spec but replaces low-level JIT requirements
 * with high-level Pixi objects (like `texture`).
 * @example
 * ```typescript
 * import { RenderTarget, TextureSource } from 'pixi.js';
 *
 * const renderTarget = new RenderTarget({
 *     depthStencilAttachment: {
 *         texture: new TextureSource({ format: 'depth24plus-stencil8', width: 100, height: 100 }),
 *         depthLoadOp: 'clear',
 *         depthClearValue: 1.0,
 *         depthReadOnly: true, // Only test depth, don't write to it (advanced 3D trick)
 *     }
 * });
 * ```
 * @category rendering
 * @advanced
 */
export interface PixiDepthStencilAttachment extends Omit<GPURenderPassDepthStencilAttachment, 'view'> {
    /** The Pixi depth/stencil texture to use for testing/writing. */
    texture: TextureSource;
    /**
     * Optional overrides. For example, if you want to perform depth testing while simultaneously
     * sampling the stencil data in a shader, you can pass `{ aspect: 'depth-only' }`.
     */
    viewDescriptor?: GPUTextureViewDescriptor;
}
/**
 * A class that describes what the renderers are rendering to.
 * This can be as simple as a Texture, or as complex as a multi-texture, multi-sampled render target.
 * Support for stencil and depth buffers is also included.
 *
 * If you need something more complex than a Texture to render to, you should use this class.
 * Under the hood, all textures you render to have a RenderTarget created on their behalf.
 * @category rendering
 * @advanced
 */
export declare class RenderTarget {
    /** The default options for a render target */
    static defaultOptions: RenderTargetOptions;
    /** unique id for this render target */
    readonly uid: number;
    /**
     * An array of attachments that define exactly how the GPU should render to the color textures.
     * This includes the texture itself, as well as load/store operations and clear values.
     */
    colorAttachments: PixiColorAttachment[];
    /**
     * An attachment that defines exactly how the GPU should render to the depth/stencil texture.
     * Includes the texture, load/store operations, and depth/stencil specific clear values.
     */
    depthStencilAttachment?: PixiDepthStencilAttachment;
    dirtyId: number;
    isRoot: boolean;
    /**
     * Opt-in toggle that inverts this target's Y orientation, resolved at `bind` time.
     *
     * Defaults to `undefined`/`false` — a no-op, so rendering is exactly what it has always been
     * (texture targets flip so they sample upright in the 2D pipeline; the screen does not). Set `true`
     * to invert that automatic orientation — e.g. to store a capture in screen orientation for 3D, where
     * geometry UVs expect the un-flipped result.
     *
     * When `true`, the projection Y-flip and the winding/cull inversion flip together, so a front-facing
     * triangle stays front-facing — back-face culling of content rendered into the target stays correct.
     * @advanced
     */
    flipY?: boolean;
    /** a label for debugging — shows up on the render pass in GPU debuggers (WebGPU) */
    label?: string;
    private readonly _size;
    /** if true, then when the render target is destroyed, it will destroy all the textures that were created for it. */
    private _managedColorTextures;
    /** depth capability requested for this target — via options, attachment format, or the mask system @internal */
    _depth: boolean;
    /** stencil capability requested for this target — via options, attachment format, or the mask system @internal */
    _stencil: boolean;
    /**
     * @param options - Options for creating a render target, or a WebGPU-flavored descriptor.
     */
    constructor(options?: RenderTargetOptions | RenderTargetDescriptor);
    private _normalizeOptions;
    get size(): [number, number];
    get width(): number;
    get height(): number;
    get pixelWidth(): number;
    get pixelHeight(): number;
    get resolution(): number;
    private _colorTextures;
    /**
     * An array of textures that can be written to by the GPU - mostly this has one texture in Pixi, but you could
     * write to multiple if required! (eg deferred lighting).
     * This is a backwards-compatible getter that extracts the textures from `colorAttachments`.
     */
    get colorTextures(): TextureSource[];
    /** The stencil and depth buffer will write to this texture in WebGPU. */
    get depthStencilTexture(): TextureSource | null;
    /** Whether this target provides a depth buffer — requested via options or implied by its attachment's format. */
    get depth(): boolean;
    /** Whether this target provides a stencil buffer — requested via options or implied by its attachment's format. */
    get stencil(): boolean;
    get colorTexture(): TextureSource;
    /**
     * The texture that drives size, resolution, and resize events.
     * For standard targets this is `colorAttachments[0].texture`;
     * for depth-only targets it is `depthStencilAttachment.texture`.
     */
    get sizeSource(): TextureSource;
    protected onSourceResize(source: TextureSource): void;
    /**
     * This will ensure a depthStencil texture is created for this render target.
     * Most likely called by the mask system to make sure we have stencil buffer added.
     * @internal
     */
    ensureDepthStencilTexture(): void;
    resize(width: number, height: number, resolution?: number, skipColorTexture?: boolean): void;
    destroy(): void;
    /**
     * The single recipe for internally-created depth-stencil textures.
     * @param width
     * @param height
     * @param resolution
     */
    private _createDepthStencilTexture;
}
