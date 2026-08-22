import { createIdFromString } from '../utils/createIdFromString.mjs';

"use strict";
class ShaderOverrides {
  /**
   * @param data - A dictionary of constants to set on the shader.
   * Keys should match the constant names in the WGSL shader.
   */
  constructor(data) {
    this.data = { ...data };
    const key = Object.keys(data).sort().map((k) => `${k}:${data[k]}`).join("|");
    this.id = createIdFromString(key, "shader-overrides");
  }
  /**
   * Creates a ShaderOverrides instance from a plain object or existing instance.
   * @param overrides - The overrides to convert.
   * @returns A ShaderOverrides instance.
   */
  static from(overrides) {
    if (overrides instanceof ShaderOverrides) {
      return overrides;
    }
    return new ShaderOverrides(overrides);
  }
}

export { ShaderOverrides };
//# sourceMappingURL=ShaderOverrides.mjs.map
