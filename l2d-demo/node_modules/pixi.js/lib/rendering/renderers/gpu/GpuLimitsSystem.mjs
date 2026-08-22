import { ExtensionType } from '../../../extensions/Extensions.mjs';

"use strict";
class GpuLimitsSystem {
  constructor(renderer) {
    /** Whether the GPU supports pipeline-level `constants` (WGSL `override`). Falls back to source baking when `false`. */
    this.supportsOverrideConstants = false;
    this._renderer = renderer;
  }
  contextChange() {
    const device = this._renderer.device.gpu.device;
    this.maxTextures = Math.min(
      device.limits.maxSampledTexturesPerShaderStage,
      device.limits.maxSamplersPerShaderStage
    );
    this.maxBatchableTextures = this.maxTextures;
    this._detectOverrideConstantsSupport(device);
  }
  _detectOverrideConstantsSupport(device) {
    device.pushErrorScope("validation");
    const testModule = device.createShaderModule({
      code: "override TEST_VALUE: f32 = 0.0;\n@compute @workgroup_size(1) fn main() {}"
    });
    device.createComputePipeline({
      layout: "auto",
      compute: {
        module: testModule,
        entryPoint: "main",
        constants: { TEST_VALUE: 1 }
      }
    });
    void device.popErrorScope().then((error) => {
      this.supportsOverrideConstants = !error;
    });
  }
  destroy() {
  }
}
/** @ignore */
GpuLimitsSystem.extension = {
  type: [
    ExtensionType.WebGPUSystem
  ],
  name: "limits"
};

export { GpuLimitsSystem };
//# sourceMappingURL=GpuLimitsSystem.mjs.map
