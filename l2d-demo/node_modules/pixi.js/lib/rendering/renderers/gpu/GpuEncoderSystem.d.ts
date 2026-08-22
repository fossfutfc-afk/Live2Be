import { ExtensionType } from '../../../extensions/Extensions';
import { type ShaderOverrides } from '../shared/shader/ShaderOverrides';
import type { Rectangle } from '../../../maths/shapes/Rectangle';
import type { Topology } from '../shared/geometry/const';
import type { Geometry } from '../shared/geometry/Geometry';
import type { Shader } from '../shared/shader/Shader';
import type { State } from '../shared/state/State';
import type { System } from '../shared/system/System';
import type { GPU } from './GpuDeviceSystem';
import type { GpuRenderTarget } from './renderTarget/GpuRenderTarget';
import type { BindGroup } from './shader/BindGroup';
import type { GpuProgram } from './shader/GpuProgram';
import type { WebGPURenderer } from './WebGPURenderer';
/**
 * The system that handles encoding commands for the GPU.
 * @category rendering
 * @advanced
 */
export declare class GpuEncoderSystem implements System {
    /** @ignore */
    static extension: {
        readonly type: readonly [ExtensionType.WebGPUSystem];
        readonly name: "encoder";
        readonly priority: 1;
    };
    commandEncoder: GPUCommandEncoder;
    /**
     * The active command target that draws and state are recorded into. This is the live render
     * pass during normal rendering, or a {@link GPURenderBundleEncoder} while a render bundle is
     * being recorded (see {@link beginBundle}). Both encoders expose the same render/bind command
     * API the encoder relies on ({@link GPURenderCommandsMixin} + {@link GPUBindingCommandsMixin}),
     * so callers write to it without caring which one is active. Pass-level commands (viewport,
     * stencil, executeBundles, end) are not part of that shared API and go through {@link _passEncoder}.
     */
    renderPassEncoder: GPURenderPassEncoder | GPURenderBundleEncoder;
    commandFinished: Promise<void>;
    private _resolveCommandFinished;
    private _gpu;
    /**
     * Per-slot cache of the last (bindGroup, program, resource-key) bound to that
     * group index. All three prongs must match for the encoder to skip rebinding —
     * see {@link setBindGroup}. Slots are allocated once in the constructor and
     * mutated in place to avoid per-call allocation on the hot path.
     */
    private _boundBindGroup;
    private _boundVertexBuffer;
    private _boundIndexBuffer;
    private _boundPipeline;
    /**
     * The real render pass encoder. Unlike {@link renderPassEncoder}, this is never swapped out for
     * a bundle encoder, so pass-level commands (viewport, stencil, executeBundles, end) always have
     * a correctly typed target — even while a bundle is being recorded.
     */
    private _passEncoder;
    private readonly _renderer;
    constructor(renderer: WebGPURenderer);
    renderStart(): void;
    beginRenderPass(gpuRenderTarget: GpuRenderTarget): void;
    endRenderPass(): void;
    /**
     * Begins recording a render bundle. While recording, all draw commands are captured into a
     * {@link GPURenderBundleEncoder} instead of the active render pass. The current render pass
     * encoder is saved and restored when {@link endBundle} is called.
     *
     * Render bundles allow pre-recording of draw commands that can be replayed multiple times
     * via {@link executeBundle}, reducing CPU overhead for repeated draw sequences.
     * @throws If a render bundle is already being recorded.
     */
    beginBundle(): void;
    /**
     * Finishes recording the current render bundle and restores the previous render pass encoder.
     * @returns The recorded {@link GPURenderBundle} ready to be executed via {@link executeBundle}.
     */
    endBundle(): GPURenderBundle;
    /**
     * Replays a previously recorded render bundle on the current render pass.
     * The bound state cache is cleared since the bundle may set its own pipeline, bind groups, and buffers.
     * @param bundle - The render bundle to execute.
     */
    executeBundle(bundle: GPURenderBundle): void;
    setViewport(viewport: Rectangle): void;
    /**
     * Sets the stencil reference value for subsequent draws. This is a pass-level command, so it
     * always targets the real render pass — not a bundle encoder, which cannot set stencil state.
     * @param stencilReference - The stencil reference value to use.
     */
    setStencilReference(stencilReference: number): void;
    setPipelineFromGeometryProgramAndState(geometry: Geometry, program: GpuProgram, state: any, topology?: Topology, overrides?: ShaderOverrides): void;
    setPipeline(pipeline: GPURenderPipeline): void;
    private _setVertexBuffer;
    private _setIndexBuffer;
    resetBindGroup(index: number): void;
    setBindGroup(index: number, bindGroup: BindGroup, program: GpuProgram): void;
    setGeometry(geometry: Geometry, program: GpuProgram): void;
    private _setShaderBindGroups;
    private _syncBindGroup;
    draw(options: {
        geometry: Geometry;
        shader: Shader;
        state?: State;
        topology?: Topology;
        size?: number;
        start?: number;
        baseVertex?: number;
        instanceCount?: number;
        skipSync?: boolean;
        firstInstance?: number;
    }): void;
    /**
     * Sets up the pipeline, geometry, and bind groups then issues an indirect draw call.
     * Uses `drawIndexedIndirect` when the geometry has an index buffer, otherwise `drawIndirect`.
     * Draw parameters (vertex count, instance count, etc.) are read from the indirect buffer on the GPU.
     * @param options - The draw options.
     * @param options.geometry - The geometry to draw.
     * @param options.shader - The shader to use.
     * @param options.state - Optional render state (blending, depth, etc.).
     * @param options.topology - Optional primitive topology override.
     * @param options.skipSync - If true, skips syncing uniform groups to their GPU buffers.
     * @param options.indirectBuffer - The GPU buffer containing the indirect draw parameters.
     * @param options.indirectOffset - Byte offset into the indirect buffer.
     */
    drawIndirect(options: {
        geometry: Geometry;
        shader: Shader;
        state?: State;
        topology?: Topology;
        skipSync?: boolean;
        indirectBuffer: GPUBuffer;
        indirectOffset: number;
    }): void;
    finishRenderPass(): void;
    postrender(): void;
    private _clearCache;
    destroy(): void;
    protected contextChange(gpu: GPU): void;
}
