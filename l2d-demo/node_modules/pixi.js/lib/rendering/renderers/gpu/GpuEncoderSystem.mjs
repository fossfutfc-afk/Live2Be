import { ExtensionType } from '../../../extensions/Extensions.mjs';

"use strict";
class GpuEncoderSystem {
  constructor(renderer) {
    /**
     * Per-slot cache of the last (bindGroup, program, resource-key) bound to that
     * group index. All three prongs must match for the encoder to skip rebinding —
     * see {@link setBindGroup}. Slots are allocated once in the constructor and
     * mutated in place to avoid per-call allocation on the hot path.
     */
    this._boundBindGroup = /* @__PURE__ */ Object.create(null);
    this._boundVertexBuffer = /* @__PURE__ */ Object.create(null);
    this._renderer = renderer;
    for (let i = 0; i < 16; i++) {
      this._boundBindGroup[i] = { bindGroup: null, program: null, key: null };
    }
  }
  renderStart() {
    this.commandFinished = new Promise((resolve) => {
      this._resolveCommandFinished = resolve;
    });
    this.commandEncoder = this._renderer.gpu.device.createCommandEncoder();
  }
  beginRenderPass(gpuRenderTarget) {
    this.endRenderPass();
    this._clearCache();
    this._passEncoder = this.commandEncoder.beginRenderPass(gpuRenderTarget.descriptor);
    this.renderPassEncoder = this._passEncoder;
  }
  endRenderPass() {
    if (this._passEncoder) {
      this._passEncoder.end();
    }
    this.renderPassEncoder = null;
    this._passEncoder = null;
  }
  /**
   * Begins recording a render bundle. While recording, all draw commands are captured into a
   * {@link GPURenderBundleEncoder} instead of the active render pass. The current render pass
   * encoder is saved and restored when {@link endBundle} is called.
   *
   * Render bundles allow pre-recording of draw commands that can be replayed multiple times
   * via {@link executeBundle}, reducing CPU overhead for repeated draw sequences.
   * @throws If a render bundle is already being recorded.
   */
  beginBundle() {
    if (this._passEncoder !== this.renderPassEncoder) {
      throw new Error("Cannot begin a new render bundle while one is already being recorded.");
    }
    this._clearCache();
    const descriptor = this._renderer.pipeline.getBundleDescriptor();
    this.renderPassEncoder = this._gpu.device.createRenderBundleEncoder(descriptor);
  }
  /**
   * Finishes recording the current render bundle and restores the previous render pass encoder.
   * @returns The recorded {@link GPURenderBundle} ready to be executed via {@link executeBundle}.
   */
  endBundle() {
    const encoder = this.renderPassEncoder;
    if (!encoder || !("finish" in encoder)) {
      throw new Error("endBundle called without an active render bundle.");
    }
    const bundle = encoder.finish();
    this.renderPassEncoder = this._passEncoder;
    this._clearCache();
    return bundle;
  }
  /**
   * Replays a previously recorded render bundle on the current render pass.
   * The bound state cache is cleared since the bundle may set its own pipeline, bind groups, and buffers.
   * @param bundle - The render bundle to execute.
   */
  executeBundle(bundle) {
    this._clearCache();
    this._passEncoder.executeBundles([bundle]);
  }
  setViewport(viewport) {
    this._passEncoder.setViewport(viewport.x, viewport.y, viewport.width, viewport.height, 0, 1);
  }
  /**
   * Sets the stencil reference value for subsequent draws. This is a pass-level command, so it
   * always targets the real render pass — not a bundle encoder, which cannot set stencil state.
   * @param stencilReference - The stencil reference value to use.
   */
  setStencilReference(stencilReference) {
    this._passEncoder.setStencilReference(stencilReference);
  }
  setPipelineFromGeometryProgramAndState(geometry, program, state, topology, overrides) {
    const pipeline = this._renderer.pipeline.getPipeline(
      geometry,
      program,
      state,
      topology,
      overrides
    );
    this.setPipeline(pipeline);
  }
  setPipeline(pipeline) {
    if (this._boundPipeline === pipeline) return;
    this._boundPipeline = pipeline;
    this.renderPassEncoder.setPipeline(pipeline);
  }
  _setVertexBuffer(index, buffer) {
    if (this._boundVertexBuffer[index] === buffer) return;
    this._boundVertexBuffer[index] = buffer;
    this.renderPassEncoder.setVertexBuffer(index, this._renderer.buffer.updateBuffer(buffer));
  }
  _setIndexBuffer(buffer) {
    if (this._boundIndexBuffer === buffer) return;
    this._boundIndexBuffer = buffer;
    const indexFormat = buffer.data.BYTES_PER_ELEMENT === 2 ? "uint16" : "uint32";
    this.renderPassEncoder.setIndexBuffer(this._renderer.buffer.updateBuffer(buffer), indexFormat);
  }
  resetBindGroup(index) {
    const slot = this._boundBindGroup[index];
    slot.bindGroup = null;
    slot.program = null;
    slot.key = null;
  }
  setBindGroup(index, bindGroup, program) {
    const slot = this._boundBindGroup[index];
    if (slot.bindGroup === bindGroup && slot.program === program && slot.key === bindGroup._key) return;
    slot.bindGroup = bindGroup;
    slot.program = program;
    slot.key = bindGroup._key;
    bindGroup._touch(this._renderer.gc.now, this._renderer.tick);
    const gpuBindGroup = this._renderer.bindGroup.getBindGroup(bindGroup, program, index);
    this.renderPassEncoder.setBindGroup(index, gpuBindGroup);
  }
  setGeometry(geometry, program) {
    const buffersToBind = this._renderer.pipeline.getBufferNamesToBind(geometry, program);
    for (const i in buffersToBind) {
      this._setVertexBuffer(parseInt(i, 10), geometry.attributes[buffersToBind[i]].buffer);
    }
    if (geometry.indexBuffer) {
      this._setIndexBuffer(geometry.indexBuffer);
    }
  }
  _setShaderBindGroups(shader, skipSync) {
    const program = shader.gpuProgram;
    for (const i in shader.groups) {
      if (!program.layout[i]) continue;
      const bindGroup = shader.groups[i];
      if (!skipSync) {
        this._syncBindGroup(bindGroup);
      }
      this.setBindGroup(i, bindGroup, program);
    }
  }
  _syncBindGroup(bindGroup) {
    for (const j in bindGroup.resources) {
      const resource = bindGroup.resources[j];
      if (!resource) continue;
      if (resource.isUniformGroup) {
        this._renderer.ubo.updateUniformGroup(resource);
      }
    }
  }
  draw(options) {
    const { geometry, shader, state, topology, size, start, baseVertex, instanceCount, skipSync, firstInstance } = options;
    this.setPipelineFromGeometryProgramAndState(geometry, shader.gpuProgram, state, topology, shader._overrides);
    this.setGeometry(geometry, shader.gpuProgram);
    this._setShaderBindGroups(shader, skipSync);
    if (geometry.indexBuffer) {
      this.renderPassEncoder.drawIndexed(
        size || geometry.indexBuffer.data.length,
        instanceCount ?? geometry.instanceCount,
        start || 0,
        baseVertex || 0,
        firstInstance || 0
      );
    } else {
      this.renderPassEncoder.draw(
        size || geometry.vertexCount,
        instanceCount ?? geometry.instanceCount,
        start || 0,
        firstInstance || 0
      );
    }
  }
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
  drawIndirect(options) {
    const { geometry, shader, state, topology, skipSync, indirectBuffer, indirectOffset } = options;
    this.setPipelineFromGeometryProgramAndState(geometry, shader.gpuProgram, state, topology, shader._overrides);
    this.setGeometry(geometry, shader.gpuProgram);
    this._setShaderBindGroups(shader, skipSync);
    if (geometry.indexBuffer) {
      this.renderPassEncoder.drawIndexedIndirect(indirectBuffer, indirectOffset);
    } else {
      this.renderPassEncoder.drawIndirect(indirectBuffer, indirectOffset);
    }
  }
  finishRenderPass() {
    if (this._passEncoder) {
      this._passEncoder.end();
      this.renderPassEncoder = null;
      this._passEncoder = null;
    }
  }
  postrender() {
    this.finishRenderPass();
    this._gpu.device.queue.submit([this.commandEncoder.finish()]);
    this._resolveCommandFinished();
    this.commandEncoder = null;
  }
  _clearCache() {
    for (let i = 0; i < 16; i++) {
      const slot = this._boundBindGroup[i];
      slot.bindGroup = null;
      slot.program = null;
      slot.key = null;
      this._boundVertexBuffer[i] = null;
    }
    this._boundIndexBuffer = null;
    this._boundPipeline = null;
  }
  destroy() {
    this._renderer = null;
    this._gpu = null;
    this._boundBindGroup = null;
    this._boundVertexBuffer = null;
    this._boundIndexBuffer = null;
    this._boundPipeline = null;
    this.renderPassEncoder = null;
    this._passEncoder = null;
  }
  contextChange(gpu) {
    this._gpu = gpu;
  }
}
/** @ignore */
GpuEncoderSystem.extension = {
  type: [ExtensionType.WebGPUSystem],
  name: "encoder",
  priority: 1
};

export { GpuEncoderSystem };
//# sourceMappingURL=GpuEncoderSystem.mjs.map
