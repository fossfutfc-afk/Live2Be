import { Rectangle } from '../../../../maths/shapes/Rectangle';
import { GlRenderTarget } from '../GlRenderTarget';
import type { RgbaArray } from '../../../../color/Color';
import type { RenderTarget } from '../../shared/renderTarget/RenderTarget';
import type { RenderTargetAdaptor, RenderTargetSystem } from '../../shared/renderTarget/RenderTargetSystem';
import type { Texture } from '../../shared/texture/Texture';
import type { CLEAR_OR_BOOL } from '../const';
import type { WebGLRenderer } from '../WebGLRenderer';
/**
 * The WebGL adaptor for the render target system. Allows the Render Target System to be used with the WebGL renderer
 * @category rendering
 * @ignore
 */
export declare class GlRenderTargetAdaptor implements RenderTargetAdaptor<GlRenderTarget> {
    private _renderTargetSystem;
    private _renderer;
    private _clearColorCache;
    private _viewPortCache;
    /** Pre-computed draw buffers arrays for MRT, indexed by color attachment count */
    private _drawBuffersCache;
    /**
     * The framebuffer currently bound to `gl.FRAMEBUFFER`, used to skip a redundant `bindFramebuffer`
     * when re-binding the same target. `undefined` means "unknown" (force a real bind). All framebuffer
     * binding must go through {@link bindFramebuffer} to keep this coherent; {@link resetState} marks
     * it unknown when external GL code may have changed the binding.
     */
    private _boundFramebuffer;
    init(renderer: WebGLRenderer, renderTargetSystem: RenderTargetSystem<GlRenderTarget>): void;
    contextChange(): void;
    copyToTexture(sourceRenderSurfaceTexture: RenderTarget, destinationTexture: Texture, originSrc: {
        x: number;
        y: number;
    }, size: {
        width: number;
        height: number;
    }, originDest: {
        x: number;
        y: number;
    }): Texture<import("../../..").TextureSource<any>>;
    copyDepthTexture(source: RenderTarget, destination: Texture, originSrc: {
        x: number;
        y: number;
    }, size: {
        width: number;
        height: number;
    }, originDest: {
        x: number;
        y: number;
    }): void;
    startRenderPass(renderTarget: RenderTarget, clear?: CLEAR_OR_BOOL, clearColor?: RgbaArray, viewport?: Rectangle, mipLevel?: number, layer?: number): void;
    finishRenderPass(renderTarget?: RenderTarget): void;
    initGpuRenderTarget(renderTarget: RenderTarget): GlRenderTarget;
    destroyGpuRenderTarget(gpuRenderTarget: GlRenderTarget): void;
    clear(renderTarget: RenderTarget, clear: CLEAR_OR_BOOL, clearColor?: RgbaArray, _viewport?: Rectangle, _mipLevel?: number, layer?: number): void;
    resizeGpuRenderTarget(renderTarget: RenderTarget): void;
    private _initColor;
    private _initDepth;
    private _resizeColor;
    private _attachDepthStencilTexture;
    private _initStencil;
    private _resizeStencil;
    prerender(renderTarget: RenderTarget): void;
    postrender(renderTarget: RenderTarget): void;
    private _setDrawBuffers;
    /**
     * Forget the GL-call caches (framebuffer binding, viewport, clear color) so the next pass
     * re-applies them. Called via the renderer's `resetState` runner when external GL code may
     * have changed state behind our back.
     */
    resetState(): void;
    /**
     * Binds a framebuffer to `gl.FRAMEBUFFER`, skipping the call when it is already bound.
     * The single blessed way to bind a framebuffer — keeps {@link _boundFramebuffer} coherent.
     * @param framebuffer - the framebuffer to bind
     * @internal
     */
    bindFramebuffer(framebuffer: WebGLFramebuffer | null): void;
}
