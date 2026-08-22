import { ExtensionType } from '../../../../extensions/Extensions';
import { ShaderOverrides } from '../../shared/shader/ShaderOverrides';
import { STENCIL_MODES } from '../../shared/state/const';
import type { Topology } from '../../shared/geometry/const';
import type { Geometry } from '../../shared/geometry/Geometry';
import type { RenderTarget } from '../../shared/renderTarget/RenderTarget';
import type { State } from '../../shared/state/State';
import type { System } from '../../shared/system/System';
import type { GPU } from '../GpuDeviceSystem';
import type { GpuProgram } from '../shader/GpuProgram';
import type { WebGPURenderer } from '../WebGPURenderer';
/**
 * Rewrites WGSL source by replacing `override` declarations with `const` declarations
 * whose values are baked in from the provided overrides map. Used as a fallback for
 * browsers that don't support the `constants` field in `GPURenderPipelineDescriptor` (e.g. Safari).
 *
 * Values are formatted according to WGSL literal rules:
 * - `u32` → unsigned integer suffix (`42u`)
 * - `i32` → plain integer (`42`)
 * - `f32` → float with decimal point (`42.0`)
 * @param source - The WGSL shader source string containing `override` declarations.
 * @param overrides - A map of override names to their numeric values.
 * @returns The modified WGSL source with matching `override` declarations replaced by `const`.
 * @internal
 */
export declare function bakeOverridesIntoSource(source: string, overrides: Record<string, number>): string;
/**
 * A system that creates and manages the GPU pipelines.
 *
 * Caching Mechanism: At its core, the system employs a two-tiered caching strategy to minimize
 * the redundant creation of GPU pipelines (or "pipes"). This strategy is based on generating unique
 * keys that represent the state of the graphics settings and the specific requirements of the
 * item being rendered. By caching these pipelines, subsequent draw calls with identical configurations
 * can reuse existing pipelines instead of generating new ones.
 *
 * State Management: The system differentiates between "global" state properties (like color masks
 * and stencil masks, which do not change frequently) and properties that may vary between draw calls
 * (such as geometry, shaders, and blend modes). Unique keys are generated for both these categories
 * using getStateKey for global state and getGraphicsStateKey for draw-specific settings. These keys are
 * then then used to caching the pipe. The next time we need a pipe we can check
 * the cache by first looking at the state cache and then the pipe cache.
 * @category rendering
 * @advanced
 */
export declare class PipelineSystem implements System {
    /** @ignore */
    static extension: {
        readonly type: readonly [ExtensionType.WebGPUSystem];
        readonly name: "pipeline";
    };
    private readonly _renderer;
    protected CONTEXT_UID: number;
    private _moduleCache;
    private _bufferLayoutsCache;
    private readonly _bindingNamesCache;
    private _pipeCache;
    private readonly _pipeStateCaches;
    private _gpu;
    private _stencilState;
    private _stencilMode;
    private _colorMask;
    private _multisampleCount;
    private _colorTargetCount;
    private _colorFormat;
    private _colorFormatId;
    private _depthStencilFormat;
    private _depthStencilFormatData;
    private _depthReadOnly;
    private _invertFrontFace;
    constructor(renderer: WebGPURenderer);
    protected contextChange(gpu: GPU): void;
    setMultisampleCount(multisampleCount: number): void;
    setRenderTarget(renderTarget: RenderTarget): void;
    setColorMask(colorMask: number): void;
    setStencilMode(stencilMode: STENCIL_MODES): void;
    /**
     * Builds a {@link GPURenderBundleEncoderDescriptor} that matches the current render target
     * configuration (color formats, sample count, and depth/stencil format).
     * Used by {@link GpuEncoderSystem.beginBundle} to create a compatible render bundle encoder.
     * @returns A descriptor for creating a GPURenderBundleEncoder.
     */
    getBundleDescriptor(): GPURenderBundleEncoderDescriptor;
    setPipeline(geometry: Geometry, program: GpuProgram, state: State, passEncoder: GPURenderPassEncoder): void;
    /**
     * Generates a key for the pipeline.advanced usage only.
     * @param geometry - The geometry to get the key for
     * @param program - The program to get the key for
     * @param state - The state to get the key for
     * @param topology - The topology to get the key for
     * @param overrides - The overrides to get the key for
     * @returns The key for the pipeline
     */
    getPipelineKey(geometry: Geometry, program: GpuProgram, state: State, topology: Topology, overrides: ShaderOverrides): number;
    getPipeline(geometry: Geometry, program: GpuProgram, state: State, topology?: Topology, overrides?: ShaderOverrides): GPURenderPipeline;
    private _createPipeline;
    private _getModule;
    private _createModule;
    /**
     * Generates and caches a numeric layout key on the geometry based on its sorted attribute
     * descriptors (offset, format, stride, instancing). Geometries with identical attribute
     * layouts share the same key, enabling pipeline reuse.
     * @param geometry - The geometry to generate a layout key for.
     */
    private _generateBufferKey;
    private _generateAttributeLocationsKey;
    /**
     * Returns a hash of buffer names mapped to bind locations.
     * This is used to bind the correct buffer to the correct location in the shader.
     * @param geometry - The geometry where to get the buffer names
     * @param program - The program where to get the buffer names
     * @returns An object of buffer names mapped to the bind location.
     */
    getBufferNamesToBind(geometry: Geometry, program: GpuProgram): Record<string, string>;
    private _createVertexBufferLayouts;
    private _updatePipeHash;
    destroy(): void;
}
