import { ExtensionType } from '../../../../extensions/Extensions.mjs';
import { State } from '../../shared/state/State.mjs';
import { GpuBlendModesToPixi } from './GpuBlendModesToPixi.mjs';

"use strict";
class GpuStateSystem {
  constructor() {
    this.defaultState = new State();
    this.defaultState.blend = true;
  }
  contextChange(gpu) {
    this.gpu = gpu;
  }
  /**
   * Gets the blend mode data for the current state
   * @param state - The state to get the blend mode from
   * @param count - The number of color targets to create
   * @param format - The texture format of the color attachments (assumed uniform across attachments)
   */
  getColorTargets(state, count, format) {
    const blend = state.blend ? GpuBlendModesToPixi[state.blendMode] || GpuBlendModesToPixi.normal : void 0;
    const targets = [];
    for (let i = 0; i < count; i++) {
      targets[i] = {
        format,
        writeMask: 0,
        blend
      };
    }
    return targets;
  }
  destroy() {
    this.gpu = null;
  }
}
/** @ignore */
GpuStateSystem.extension = {
  type: [
    ExtensionType.WebGPUSystem
  ],
  name: "state"
};

export { GpuStateSystem };
//# sourceMappingURL=GpuStateSystem.mjs.map
