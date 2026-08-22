import { ExtensionType } from '../../../../extensions/Extensions.mjs';
import { warn } from '../../../../utils/logging/warn.mjs';
import { ensureAttributes } from '../../gl/shader/program/ensureAttributes.mjs';
import { ShaderOverrides } from '../../shared/shader/ShaderOverrides.mjs';
import { STENCIL_MODES } from '../../shared/state/const.mjs';
import { createIdFromString } from '../../shared/utils/createIdFromString.mjs';
import { GpuStencilModesToPixi } from '../state/GpuStencilModesToPixi.mjs';

"use strict";
const topologyStringToId = {
  "point-list": 0,
  "line-list": 1,
  "line-strip": 2,
  "triangle-list": 3,
  "triangle-strip": 4
};
const emptyOverrides = new ShaderOverrides({});
const depthStencilFormatMap = {
  "depth24plus-stencil8": { depth: true, stencil: true, index: 1 },
  depth24plus: { depth: true, stencil: false, index: 2 },
  depth32float: { depth: true, stencil: false, index: 3 },
  "depth32float-stencil8": { depth: true, stencil: true, index: 4 },
  depth16unorm: { depth: true, stencil: false, index: 5 },
  stencil8: { depth: false, stencil: true, index: 6 }
};
const emptyDepthStencilFormatData = { depth: false, stencil: false, index: 0 };
function bakeOverridesIntoSource(source, overrides) {
  for (const [name, value] of Object.entries(overrides)) {
    const re = new RegExp(
      `override\\s+${name}\\s*:\\s*(\\w+)\\s*(?:=[^;]*)?;`
    );
    source = source.replace(re, (_, type) => {
      let lit;
      if (type === "u32") lit = `${Math.trunc(value)}u`;
      else if (type === "i32") lit = `${Math.trunc(value)}`;
      else lit = Number.isInteger(value) ? `${value}.0` : `${value}`;
      return `const ${name}: ${type} = ${lit};`;
    });
  }
  return source;
}
function getGraphicsStateKey(geometryLayout, shaderKey, state, blendMode, topology, overrideId) {
  return geometryLayout * 35184372088832 + shaderKey * 536870912 + overrideId * 16384 + (state << 8) + (blendMode << 3) + topology;
}
const colorFormatIds = /* @__PURE__ */ Object.create(null);
let nextColorFormatId = 0;
function getColorFormatId(format) {
  let id = colorFormatIds[format];
  if (id === void 0) id = colorFormatIds[format] = nextColorFormatId++;
  return id;
}
function getGlobalStateKey(stencilStateId, multiSampleCount, colorMask, colorTargetCount, depthStencilFormat, colorFormatId, depthReadOnly, invertFrontFace) {
  return invertFrontFace << 20 | colorFormatId << 16 | depthStencilFormat << 13 | colorMask << 9 | stencilStateId << 6 | depthReadOnly << 5 | colorTargetCount << 1 | multiSampleCount;
}
class PipelineSystem {
  constructor(renderer) {
    this._moduleCache = /* @__PURE__ */ Object.create(null);
    this._bufferLayoutsCache = /* @__PURE__ */ Object.create(null);
    this._bindingNamesCache = /* @__PURE__ */ Object.create(null);
    this._pipeCache = /* @__PURE__ */ new Map();
    this._pipeStateCaches = /* @__PURE__ */ Object.create(null);
    this._colorMask = 15;
    this._multisampleCount = 1;
    this._colorTargetCount = 1;
    this._colorFormat = "bgra8unorm";
    this._colorFormatId = getColorFormatId("bgra8unorm");
    this._depthStencilFormat = "depth24plus-stencil8";
    this._depthStencilFormatData = emptyDepthStencilFormatData;
    this._depthReadOnly = false;
    this._invertFrontFace = false;
    this._renderer = renderer;
  }
  contextChange(gpu) {
    this._gpu = gpu;
    this.setStencilMode(STENCIL_MODES.DISABLED);
    this._updatePipeHash();
  }
  setMultisampleCount(multisampleCount) {
    if (this._multisampleCount === multisampleCount) return;
    this._multisampleCount = multisampleCount;
    this._updatePipeHash();
  }
  setRenderTarget(renderTarget) {
    const colorTexture = renderTarget.colorAttachments[0]?.texture;
    this._multisampleCount = colorTexture?.source.antialias ? 4 : 1;
    this._colorTargetCount = renderTarget.colorAttachments.length;
    this._colorFormat = colorTexture?.format ?? "bgra8unorm";
    this._colorFormatId = getColorFormatId(this._colorFormat);
    this._depthStencilFormat = renderTarget.depthStencilAttachment?.texture.format;
    this._depthStencilFormatData = depthStencilFormatMap[this._depthStencilFormat] || emptyDepthStencilFormatData;
    this._depthReadOnly = renderTarget.depthStencilAttachment?.depthReadOnly ?? false;
    this._invertFrontFace = !!renderTarget.flipY;
    this._updatePipeHash();
  }
  setColorMask(colorMask) {
    if (this._colorMask === colorMask) return;
    this._colorMask = colorMask;
    this._updatePipeHash();
  }
  setStencilMode(stencilMode) {
    if (this._stencilMode === stencilMode) return;
    this._stencilMode = stencilMode;
    this._stencilState = GpuStencilModesToPixi[stencilMode];
    this._updatePipeHash();
  }
  /**
   * Builds a {@link GPURenderBundleEncoderDescriptor} that matches the current render target
   * configuration (color formats, sample count, and depth/stencil format).
   * Used by {@link GpuEncoderSystem.beginBundle} to create a compatible render bundle encoder.
   * @returns A descriptor for creating a GPURenderBundleEncoder.
   */
  getBundleDescriptor() {
    const colorFormats = [];
    for (let i = 0; i < this._colorTargetCount; i++) {
      colorFormats.push(this._colorFormat);
    }
    const descriptor = {
      colorFormats,
      sampleCount: this._multisampleCount
    };
    if (this._depthStencilFormatData.depth || this._depthStencilFormatData.stencil) {
      descriptor.depthStencilFormat = this._depthStencilFormat;
    }
    return descriptor;
  }
  setPipeline(geometry, program, state, passEncoder) {
    const pipeline = this.getPipeline(geometry, program, state);
    passEncoder.setPipeline(pipeline);
  }
  /**
   * Generates a key for the pipeline.advanced usage only.
   * @param geometry - The geometry to get the key for
   * @param program - The program to get the key for
   * @param state - The state to get the key for
   * @param topology - The topology to get the key for
   * @param overrides - The overrides to get the key for
   * @returns The key for the pipeline
   */
  getPipelineKey(geometry, program, state, topology, overrides) {
    if (!geometry._layoutKey) {
      ensureAttributes(geometry, program.attributeData);
      this._generateBufferKey(geometry);
    }
    return getGraphicsStateKey(
      geometry._layoutKey,
      program._layoutKey,
      state.data,
      state._blendModeId,
      topologyStringToId[topology],
      overrides.id
    );
  }
  getPipeline(geometry, program, state, topology, overrides) {
    if (!geometry._layoutKey) {
      ensureAttributes(geometry, program.attributeData);
      this._generateBufferKey(geometry);
    }
    topology || (topology = geometry.topology);
    overrides || (overrides = emptyOverrides);
    const key = getGraphicsStateKey(
      geometry._layoutKey,
      program._layoutKey,
      state.data,
      state._blendModeId,
      topologyStringToId[topology],
      overrides.id
    );
    let pipeline = this._pipeCache.get(key);
    if (!pipeline) {
      pipeline = this._createPipeline(geometry, program, state, topology, overrides);
      this._pipeCache.set(key, pipeline);
    }
    return pipeline;
  }
  _createPipeline(geometry, program, state, topology, overrides) {
    const device = this._gpu.device;
    const buffers = this._createVertexBufferLayouts(geometry, program);
    const blendModes = this._renderer.state.getColorTargets(state, this._colorTargetCount, this._colorFormat);
    const writeMask = this._stencilMode === STENCIL_MODES.RENDERING_MASK_ADD ? 0 : this._colorMask;
    for (let i = 0; i < blendModes.length; i++) {
      blendModes[i].writeMask = writeMask;
    }
    const layout = this._renderer.shader.getProgramData(program).pipeline;
    const hasOverrides = Object.keys(overrides.data).length > 0;
    let vertexSource = program.vertex.source;
    let fragmentSource = program.fragment.source;
    let constants;
    if (hasOverrides) {
      if (this._renderer.limits.supportsOverrideConstants) {
        constants = overrides.data;
      } else {
        vertexSource = bakeOverridesIntoSource(vertexSource, overrides.data);
        fragmentSource = bakeOverridesIntoSource(fragmentSource, overrides.data);
      }
    }
    const descriptor = {
      // TODO later check if its helpful to create..
      // layout,
      vertex: {
        module: this._getModule(vertexSource),
        entryPoint: program.vertex.entryPoint,
        constants,
        buffers
      },
      fragment: {
        module: this._getModule(fragmentSource),
        entryPoint: program.fragment.entryPoint,
        targets: blendModes,
        constants
      },
      primitive: {
        topology,
        // Mirror WebGL's split: `gl.cullFace` is left at its `BACK` default, so the back is always
        // the culled side. Taking this from `state.cullMode` instead folds the winding into *which
        // side* is culled — the same triangles survive, but `@builtin(front_facing)` then reports
        // the opposite of `gl_FrontFacing` for clockwise-wound geometry.
        cullMode: state.culling ? "back" : "none",
        // The winding is stated once, here, exactly as `gl.frontFace` does it. `flipY` inverts the
        // projection (see setRenderTarget), so inverting the winding alongside it makes the two
        // cancel and a front face stays a front face. Both flags are part of the pipeline cache key.
        frontFace: state.clockwiseFrontFace !== this._invertFrontFace ? "cw" : "ccw"
      },
      layout,
      multisample: {
        count: this._multisampleCount
      },
      // depthStencil,
      label: program.name ? `PIXI Pipeline (${program.name})` : `PIXI Pipeline`
    };
    if (this._depthStencilFormatData.depth || this._depthStencilFormatData.stencil) {
      const formatData = this._depthStencilFormatData;
      descriptor.depthStencil = {
        ...this._stencilState,
        format: this._depthStencilFormat,
        depthWriteEnabled: formatData.depth ? state.depthMask && !this._depthReadOnly : false,
        depthCompare: formatData.depth && state.depthTest ? "less" : "always"
      };
    }
    const pipeline = device.createRenderPipeline(descriptor);
    return pipeline;
  }
  _getModule(code) {
    return this._moduleCache[code] || this._createModule(code);
  }
  _createModule(code) {
    const device = this._gpu.device;
    this._moduleCache[code] = device.createShaderModule({
      code
    });
    return this._moduleCache[code];
  }
  /**
   * Generates and caches a numeric layout key on the geometry based on its sorted attribute
   * descriptors (offset, format, stride, instancing). Geometries with identical attribute
   * layouts share the same key, enabling pipeline reuse.
   * @param geometry - The geometry to generate a layout key for.
   */
  _generateBufferKey(geometry) {
    const keyGen = [];
    let index = 0;
    const attributeKeys = Object.keys(geometry.attributes).sort();
    for (let i = 0; i < attributeKeys.length; i++) {
      const attribute = geometry.attributes[attributeKeys[i]];
      keyGen[index++] = attribute.offset;
      keyGen[index++] = attribute.format;
      keyGen[index++] = attribute.stride;
      keyGen[index++] = attribute.instance;
    }
    const stringKey = keyGen.join("|");
    geometry._layoutKey = createIdFromString(stringKey, "geometry");
    return geometry._layoutKey;
  }
  _generateAttributeLocationsKey(program) {
    const keyGen = [];
    let index = 0;
    const attributeKeys = Object.keys(program.attributeData).sort();
    for (let i = 0; i < attributeKeys.length; i++) {
      const attribute = program.attributeData[attributeKeys[i]];
      keyGen[index++] = attribute.location;
    }
    const stringKey = keyGen.join("|");
    program._attributeLocationsKey = createIdFromString(stringKey, "programAttributes");
    return program._attributeLocationsKey;
  }
  /**
   * Returns a hash of buffer names mapped to bind locations.
   * This is used to bind the correct buffer to the correct location in the shader.
   * @param geometry - The geometry where to get the buffer names
   * @param program - The program where to get the buffer names
   * @returns An object of buffer names mapped to the bind location.
   */
  getBufferNamesToBind(geometry, program) {
    const key = geometry._layoutKey << 16 | program._attributeLocationsKey;
    if (this._bindingNamesCache[key]) return this._bindingNamesCache[key];
    const data = this._createVertexBufferLayouts(geometry, program);
    const bufferNamesToBind = /* @__PURE__ */ Object.create(null);
    const attributeData = program.attributeData;
    for (let i = 0; i < data.length; i++) {
      const attributes = Object.values(data[i].attributes);
      const shaderLocation = attributes[0].shaderLocation;
      for (const j in attributeData) {
        if (attributeData[j].location === shaderLocation) {
          bufferNamesToBind[i] = j;
          break;
        }
      }
    }
    this._bindingNamesCache[key] = bufferNamesToBind;
    return bufferNamesToBind;
  }
  _createVertexBufferLayouts(geometry, program) {
    if (!program._attributeLocationsKey) this._generateAttributeLocationsKey(program);
    const key = geometry._layoutKey << 16 | program._attributeLocationsKey;
    if (this._bufferLayoutsCache[key]) {
      return this._bufferLayoutsCache[key];
    }
    const vertexBuffersLayout = [];
    geometry.buffers.forEach((buffer) => {
      const bufferEntry = {
        arrayStride: 0,
        stepMode: "vertex",
        attributes: []
      };
      const bufferEntryAttributes = bufferEntry.attributes;
      for (const i in program.attributeData) {
        const attribute = geometry.attributes[i];
        if ((attribute.divisor ?? 1) !== 1) {
          warn(`Attribute ${i} has an invalid divisor value of '${attribute.divisor}'. WebGPU only supports a divisor value of 1`);
        }
        if (attribute.buffer === buffer) {
          bufferEntry.arrayStride = attribute.stride;
          bufferEntry.stepMode = attribute.instance ? "instance" : "vertex";
          bufferEntryAttributes.push({
            shaderLocation: program.attributeData[i].location,
            offset: attribute.offset,
            format: attribute.format
          });
        }
      }
      if (bufferEntryAttributes.length) {
        vertexBuffersLayout.push(bufferEntry);
      }
    });
    this._bufferLayoutsCache[key] = vertexBuffersLayout;
    return vertexBuffersLayout;
  }
  _updatePipeHash() {
    var _a;
    const key = getGlobalStateKey(
      this._stencilMode,
      // normalize the raw sample count (1 or 4 — WebGPU's only renderable counts) to a
      // true single bit, so it cannot spill into the colorTargetCount field above it
      this._multisampleCount === 1 ? 0 : 1,
      this._colorMask,
      this._colorTargetCount,
      this._depthStencilFormatData.index,
      this._colorFormatId,
      this._depthReadOnly ? 1 : 0,
      this._invertFrontFace ? 1 : 0
    );
    this._pipeCache = (_a = this._pipeStateCaches)[key] ?? (_a[key] = /* @__PURE__ */ new Map());
  }
  destroy() {
    this._bufferLayoutsCache = null;
    this._pipeCache = null;
    this._gpu = null;
    this._renderer = null;
    this._bindingNamesCache = null;
    this._pipeStateCaches = null;
    this._moduleCache = null;
  }
}
/** @ignore */
PipelineSystem.extension = {
  type: [ExtensionType.WebGPUSystem],
  name: "pipeline"
};

export { PipelineSystem, bakeOverridesIntoSource };
//# sourceMappingURL=PipelineSystem.mjs.map
