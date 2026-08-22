import { Matrix } from '../../../../maths/matrix/Matrix';
import { Rectangle } from '../../../../maths/shapes/Rectangle';
import { CLEAR } from '../../gl/const';
import { type Renderer } from '../../types';
import { SystemRunner } from '../system/SystemRunner';
import { TextureSource } from '../texture/sources/TextureSource';
import { Texture } from '../texture/Texture';
import { RenderTarget } from './RenderTarget';
import type { RgbaArray } from '../../../../color/Color';
import type { ICanvas } from '../../../../environment/canvas/ICanvas';
import type { CanvasRenderTarget } from '../../canvas/renderTarget/CanvasRenderTargetAdaptor';
import type { CLEAR_OR_BOOL } from '../../gl/const';
import type { GlRenderTarget } from '../../gl/GlRenderTarget';
import type { GpuRenderTarget } from '../../gpu/renderTarget/GpuRenderTarget';
import type { System } from '../system/System';
import type { BindableTexture } from '../texture/Texture';
/**
 * A render surface is a texture, canvas, or render target
 * @category rendering
 * @see environment.ICanvas
 * @see Texture
 * @see RenderTarget
 * @advanced
 */
export type RenderSurface = ICanvas | BindableTexture | RenderTarget;
/**
 * The persistent description of a render-surface binding: the target plus the frame,
 * subresource, and orientation axes. Captured by {@link RenderTargetSystem.getBindState}.
 *
 * A clear is a per-call action, not part of the binding — see {@link BindOptions}.
 * @category rendering
 * @advanced
 */
export interface BindState {
    /** the render surface to bind: a texture, canvas, or render target */
    target: RenderSurface;
    /**
     * the frame to render to, in base mip (mip 0) pixel space. When omitted, a {@link Texture}
     * target falls back to its own frame and any other target binds in full.
     */
    frame?: Rectangle;
    /**
     * the mip level to render to (subresource)
     * @default 0
     */
    mipLevel?: number;
    /**
     * the array layer (or slice/face) of the render surface to render to (subresource)
     * @default 0
     */
    layer?: number;
    /**
     * opt-in Y-orientation toggle. `false`/omitted is a no-op (the historical `!isRoot`
     * behavior); `true` inverts the orientation, and the winding with it.
     */
    flipY?: boolean;
}
/**
 * Options for binding a render surface via {@link RenderTargetSystem.bind}: the persistent
 * {@link BindState} plus the per-call clear actions.
 * @category rendering
 * @advanced
 */
export interface BindOptions extends BindState {
    /**
     * the clear mode to use. Can be `true` or a CLEAR number 'COLOR | DEPTH | STENCIL' 0b111
     * @default true
     */
    clear?: CLEAR_OR_BOOL;
    /** the color to clear to */
    clearColor?: RgbaArray;
}
/**
 * An adaptor interface for RenderTargetSystem to support WebGL and WebGPU.
 * This is used internally by the renderer, and is not intended to be used directly.
 * @ignore
 */
type RendererRenderTarget = GlRenderTarget | GpuRenderTarget | CanvasRenderTarget;
/**
 * An adaptor interface for RenderTargetSystem to support WebGL and WebGPU.
 * This is used internally by the renderer, and is not intended to be used directly.
 * @category rendering
 * @ignore
 */
export interface RenderTargetAdaptor<RENDER_TARGET extends RendererRenderTarget> {
    /**
     * Initializes the adaptor.
     * @param {Renderer} renderer - the renderer
     * @param {RenderTargetSystem} renderTargetSystem - the render target system
     */
    init(renderer: Renderer, renderTargetSystem: RenderTargetSystem<RENDER_TARGET>): void;
    /**
     * A function copies the contents of a render surface to a texture
     * @param {RenderTarget} sourceRenderSurfaceTexture - the render surface to copy from
     * @param {Texture} destinationTexture - the texture to copy to
     * @param {object} originSrc - the origin of the copy
     * @param {number} originSrc.x - the x origin of the copy
     * @param {number} originSrc.y - the y origin of the copy
     * @param {object} size - the size of the copy
     * @param {number} size.width - the width of the copy
     * @param {number} size.height - the height of the copy
     * @param {object} originDest - the destination origin (top left to paste from!)
     * @param {number} originDest.x - the x destination origin of the copy
     * @param {number} originDest.y - the y destination origin of the copy
     */
    copyToTexture(sourceRenderSurfaceTexture: RenderTarget, destinationTexture: Texture, originSrc: {
        x: number;
        y: number;
    }, size: {
        width: number;
        height: number;
    }, originDest?: {
        x: number;
        y: number;
    }): Texture;
    /**
     * starts a render pass on the render target
     * @param {RenderTarget} renderTarget - the render target to start the render pass on
     * @param {CLEAR_OR_BOOL} clear - the clear mode to use. Can be true or a CLEAR number 'COLOR | DEPTH | STENCIL' 0b111*
     * @param {RgbaArray} [clearColor] - the color to clear to
     * @param {Rectangle} [viewport] - the viewport to use
     */
    startRenderPass(renderTarget: RenderTarget, clear: CLEAR_OR_BOOL, clearColor?: RgbaArray, 
    /** the viewport to use */
    viewport?: Rectangle, 
    /** mip level to render to (subresource) */
    mipLevel?: number, 
    /** array layer to render to (subresource) */
    layer?: number): void;
    /**
     * clears the current render target to the specified color
     * @param {RenderTarget} renderTarget - the render target to clear
     * @param {CLEAR_OR_BOOL} clear - the clear mode to use. Can be true or a CLEAR number 'COLOR | DEPTH | STENCIL' 0b111*
     * @param {RgbaArray} [clearColor] - the color to clear to
     * @param {Rectangle} [viewport] - the viewport to use
     */
    clear(renderTarget: RenderTarget, clear: CLEAR_OR_BOOL, clearColor?: RgbaArray, 
    /** the viewport to use */
    viewport?: Rectangle, 
    /** mip level to clear (subresource) */
    mipLevel?: number, 
    /** array layer to clear (subresource) */
    layer?: number): void;
    /**
     * finishes the current render pass
     * @param {RenderTarget} renderTarget - the render target to finish the render pass for
     */
    finishRenderPass(renderTarget: RenderTarget): void;
    /**
     * called after the render pass is finished
     * @param {RenderTarget} renderTarget - the render target that was rendered to
     */
    postrender?(renderTarget: RenderTarget): void;
    /**
     * called before the render main pass is started
     * @param {RenderTarget} renderTarget - the render target that will be rendered to
     */
    prerender?(renderTarget: RenderTarget): void;
    /**
     * initializes a gpu render target
     * @param {RenderTarget} renderTarget - the render target to initialize
     */
    initGpuRenderTarget(renderTarget: RenderTarget): RENDER_TARGET;
    /**
     * resizes the gpu render target
     * @param {RenderTarget} renderTarget - the render target to resize
     */
    resizeGpuRenderTarget(renderTarget: RenderTarget): void;
    /**
     * destroys the gpu render target
     * @param {RendererRenderTarget} gpuRenderTarget - the gpu render target to destroy
     */
    destroyGpuRenderTarget(gpuRenderTarget: RENDER_TARGET): void;
    /**
     * Copies the depth attachment of a render target into a depth/stencil texture.
     *
     * **Important Note:** When using the copied depth buffer in a subsequent render pass,
     * you must ensure you do not clear the depth buffer again. If you need to clear the color
     * buffer of the destination render target, use `clear: CLEAR.COLOR` to preserve the copied depth data.
     * @example
     * ```js
     * renderer.renderTarget.copyDepthTexture(
     *   sourceRT, destDepthTexture, { x: 0, y: 0 }, { width: 200, height: 200 }, { x: 0, y: 0 }
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
     * @param {RenderTarget} source - the render target to copy depth from
     * @param {Texture} destination - the depth/stencil texture to copy depth to
     * @param {object} originSrc - the origin of the copy
     * @param {number} originSrc.x - the x origin of the copy
     * @param {number} originSrc.y - the y origin of the copy
     * @param {object} size - the size of the copy
     * @param {number} size.width - the width of the copy
     * @param {number} size.height - the height of the copy
     * @param {object} originDest - the destination origin (top left to paste from!)
     * @param {number} originDest.x - the x destination origin of the copy
     * @param {number} originDest.y - the y destination origin of the copy
     */
    copyDepthTexture(source: RenderTarget, destination: Texture, originSrc: {
        x: number;
        y: number;
    }, size: {
        width: number;
        height: number;
    }, originDest?: {
        x: number;
        y: number;
    }): void;
}
/**
 * A system that manages render targets. A render target is essentially a place where the shaders can color in the pixels.
 * The render target system is responsible for binding the render target to the renderer, and managing the viewport.
 * Render targets can be pushed and popped.
 *
 * To make it easier, you can also bind textures and canvases too. This will automatically create a render target for you.
 * The render target itself is a lot more powerful than just a texture or canvas,
 * as it can have multiple textures attached to it.
 * It will also give ou fine grain control over the stencil buffer / depth texture.
 * @example
 *
 * ```js
 *
 * // create a render target
 * const renderTarget = new RenderTarget({
 *   colorTextures: [new TextureSource({ width: 100, height: 100 })],
 * });
 *
 * // bind the render target
 * renderer.renderTarget.bind({ target: renderTarget });
 *
 * // draw something!
 * ```
 * @category rendering
 * @advanced
 */
export declare class RenderTargetSystem<RENDER_TARGET extends RendererRenderTarget> implements System {
    /** When rendering of a scene begins, this is where the root render surface is stored */
    rootRenderTarget: RenderTarget;
    /** This is the root viewport for the render pass */
    rootViewPort: Rectangle;
    /** A boolean that lets the dev know if the current render pass is rendering to the screen. Used by some plugins */
    renderingToScreen: boolean;
    /** the current active render target */
    renderTarget: RenderTarget;
    /** the current viewport that the gpu is using */
    readonly viewport: Rectangle;
    /**
     * a runner that lets systems know if the active render target has changed.
     * Eg the Stencil System needs to know so it can manage the stencil buffer
     */
    readonly onRenderTargetChange: SystemRunner;
    /** the projection matrix that is used by the shaders based on the active render target and the viewport */
    readonly projectionMatrix: Matrix;
    /** the default clear color for render targets */
    readonly defaultClearColor: RgbaArray;
    /** a reference to the adaptor that interfaces with WebGL / WebGP */
    readonly adaptor: RenderTargetAdaptor<RENDER_TARGET>;
    /**
     * a hash that stores the render target for a given render surface. When you pass in a texture source,
     * a render target is created for it. This map stores and makes it easy to retrieve the render target
     */
    private readonly _renderSurfaceToRenderTargetHash;
    /** A hash that stores a gpu render target for a given render target. */
    private _gpuRenderTargetHash;
    /** the pushed bindings; each entry is a replayable BindOptions that pop() re-binds */
    private readonly _renderTargetStack;
    /**
     * the state of the current binding, written on every bind — backs the `renderSurface`,
     * `mipLevel` and `layer` getters and `getBindState`. Its `frame` aliases `_bindFrame`
     * and must never be handed out by reference.
     */
    private readonly _bindState;
    /** system-owned rect backing `_bindState.frame`; as-passed frames are copied into it */
    private readonly _bindFrame;
    /** A reference to the renderer */
    private readonly _renderer;
    constructor(renderer: Renderer);
    /** the current active render surface that the render target is created from */
    get renderSurface(): RenderSurface;
    /** the current mip level being rendered to (for texture subresources) */
    get mipLevel(): number;
    /** the current array layer being rendered to (for array-backed targets) */
    get layer(): number;
    /** called when dev wants to finish a render pass */
    finishRenderPass(): void;
    /**
     * called when the renderer starts to render a scene: resets the bind stack and binds the
     * root render surface
     * @param options - the {@link BindOptions} for the root binding
     */
    renderStart(options: BindOptions): void;
    postrender(): void;
    /**
     * Binding a render surface! This is the main function of the render target system.
     * It will take the RenderSurface (which can be a texture, canvas, or render target) and bind it to the renderer.
     * Once bound all draw calls will be rendered to the render surface.
     *
     * If a frame is not provided and the render surface is a {@link Texture}, the frame of the texture will be used.
     *
     * IDEMPOTENT BIND:
     * Binding is "smart" — the viewport/projection math is always recomputed, but the underlying render pass is
     * only torn down and re-begun when something that actually requires it changes. If you bind the render target
     * that the currently open pass is already on (same `mipLevel`/`layer`) and request **no clear**
     * (`clear` is `false` / `CLEAR.NONE`), the live pass is reused and only the viewport is updated. This makes
     * drawing N things into one target at N viewports a single pass with N `setViewport` calls, and makes a
     * redundant same-target `bind`/`pop` essentially free. Any clear (even a partial one like `CLEAR.DEPTH`), a
     * different target, or a different `mipLevel`/`layer` forces a real begin. The MSAA resolve is never skipped:
     * it is deferred to the genuine pass end, which still happens before any target switch or read-back.
     *
     * IMPORTANT:
     * - `frame` is treated as **base mip (mip 0) pixel space**.
     * - When `mipLevel > 0`, the viewport derived from `frame` is scaled by \(2^{mipLevel}\) and clamped to the
     *   mip dimensions. This keeps "render the same region" semantics consistent across mip levels.
     * - When `renderSurface` is a {@link Texture}, `renderer.render({ container, target: texture, mipLevel })` will
     *   render into
     *   the underlying {@link TextureSource} (Pixi will create/use a {@link RenderTarget} for the source) using the
     *   texture's frame to define the region (in mip 0 space).
     * @param options - the bind options: see {@link BindOptions}
     * @returns the render target that was bound
     */
    bind(options: BindOptions): RenderTarget;
    /**
     * Binds a render surface using positional arguments.
     * @param renderSurface - the render surface to bind
     * @param clear - the clear mode to use. Can be true or a CLEAR number 'COLOR | DEPTH | STENCIL' 0b111
     * @param clearColor - the color to clear to
     * @param frame - the frame to render to
     * @param mipLevel - the mip level to render to
     * @param layer - the layer (or slice) of the render surface to render to
     * @param flipY - opt-in Y-orientation toggle
     * @returns the render target that was bound
     * @deprecated since 8.20.0 — use an options object instead:
     * `bind({ target, clear, clearColor, frame, mipLevel, layer, flipY })`
     */
    bind(renderSurface: RenderSurface, clear?: CLEAR_OR_BOOL, clearColor?: RgbaArray, frame?: Rectangle, mipLevel?: number, layer?: number, flipY?: boolean): RenderTarget;
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
    getBindState(out?: BindOptions): BindOptions;
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
    get frontFaceInverted(): boolean;
    clear(target?: RenderSurface, clear?: CLEAR_OR_BOOL, clearColor?: RgbaArray, mipLevel?: number, layer?: number): void;
    protected contextChange(): void;
    /**
     * Push a render surface to the renderer. This will bind the render surface to the renderer
     * and store the binding on a stack, so `pop()` can restore the previous binding.
     * @param options - the bind options: see {@link BindOptions}
     * @returns the render target that was bound
     */
    push(options: BindOptions): RenderTarget;
    /**
     * Push a render surface using positional arguments.
     * @param renderSurface - the render surface to push
     * @param clear - the clear mode to use. Can be true or a CLEAR number 'COLOR | DEPTH | STENCIL' 0b111
     * @param clearColor - the color to clear to
     * @param frame - the frame to use when rendering to the render surface
     * @param mipLevel - the mip level to render to
     * @param layer - the layer of the render surface to render to
     * @param flipY - opt-in Y-orientation toggle; stored on the stack so it is restored on `pop`
     * @returns the render target that was bound
     * @deprecated since 8.20.0 — use an options object instead:
     * `push({ target, clear, clearColor, frame, mipLevel, layer, flipY })`
     */
    push(renderSurface: RenderSurface, clear?: CLEAR | boolean, clearColor?: RgbaArray, frame?: Rectangle, mipLevel?: number, layer?: number, flipY?: boolean): RenderTarget;
    /**
     * Pops the current render target and restores the previous binding.
     * @returns the render target that was restored
     */
    pop(): RenderTarget;
    /**
     * Gets the render target from the provide render surface. Eg if its a texture,
     * it will return the render target for the texture.
     * If its a render target, it will return the same render target.
     * @param renderSurface - the render surface to get the render target for
     * @returns the render target for the render surface
     */
    getRenderTarget(renderSurface: RenderSurface): RenderTarget;
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
    copyToTexture(sourceRenderSurface: RenderSurface, destinationTexture: Texture, originSrc: {
        x: number;
        y: number;
    }, size: {
        width: number;
        height: number;
    }, originDest: {
        x: number;
        y: number;
    }): Texture<TextureSource<any>>;
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
    copyDepthTexture(source: RenderSurface, destination: Texture, originSrc: {
        x: number;
        y: number;
    }, size: {
        width: number;
        height: number;
    }, originDest?: {
        x: number;
        y: number;
    }): void;
    /**
     * ensures that we have a depth stencil buffer available to render to
     * This is used by the mask system to make sure we have a stencil buffer.
     */
    ensureDepthStencil(): void;
    /** nukes the render target system */
    destroy(): void;
    private _initRenderTarget;
    private _onRenderSurfaceDestroy;
    /**
     * Tears down a render target that wraps a texture source, removing every reference the
     * system holds to it so neither the system's own teardown nor the source's `destroy`
     * event can destroy it a second time.
     * @param renderSurface - the texture source the render target wraps
     * @param renderTarget - the render target to release
     */
    private _releaseRenderTarget;
    getGpuRenderTarget(renderTarget: RenderTarget): RENDER_TARGET;
    resetState(): void;
}
export {};
