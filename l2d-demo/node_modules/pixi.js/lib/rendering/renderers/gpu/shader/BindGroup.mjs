import { warn } from '../../../../utils/logging/warn.mjs';

"use strict";
class BindGroup {
  /**
   * Create a new instance of the Bind Group.
   * @param resources - The resources that are bound together for use by a shader.
   */
  constructor(resources) {
    /** The resources that are bound together for use by a shader. */
    this.resources = /* @__PURE__ */ Object.create(null);
    this._dirty = true;
    let index = 0;
    for (const i in resources) {
      const resource = resources[i];
      this.setResource(resource, index++);
    }
  }
  /**
   * A key used internally to match it up to a WebGPU BindGroup.
   * Lazily rebuilt from resource IDs when dirty.
   * @internal
   */
  get _key() {
    if (this._dirty) {
      this._dirty = false;
      const keyParts = [];
      let index = 0;
      for (const i in this.resources) {
        keyParts[index++] = this.resources[i] ? this.resources[i]._resourceId : -1;
      }
      this._keyValue = keyParts.join("|");
    }
    return this._keyValue;
  }
  /**
   * Set a resource at a given index. This function will
   * ensure that listeners will be removed from the current resource
   * and added to the new resource.
   * @param resource - The resource to set.
   * @param index - The index to set the resource at.
   */
  setResource(resource, index) {
    const currentResource = this.resources[index];
    if (resource === currentResource) return;
    if (currentResource) {
      currentResource.off?.("change", this.onResourceChange, this);
    }
    resource.on?.("change", this.onResourceChange, this);
    this.resources[index] = resource;
    this._dirty = true;
  }
  /**
   * Returns the resource at the current specified index.
   * @param index - The index of the resource to get.
   * @returns - The resource at the specified index.
   */
  getResource(index) {
    return this.resources[index];
  }
  /**
   * Used internally to 'touch' each resource, to ensure that the GC
   * knows that all resources in this bind group are still being used.
   * @param now - The current time in milliseconds.
   * @param tick - The current tick.
   * @internal
   */
  _touch(now, tick) {
    const resources = this.resources;
    for (const i in resources) {
      const resource = resources[i];
      if (!resource) continue;
      resource._gcLastUsed = now;
      resource._touched = tick;
    }
  }
  /** Destroys this bind group and removes all listeners. */
  destroy() {
    const resources = this.resources;
    for (const i in resources) {
      const resource = resources[i];
      resource?.off?.("change", this.onResourceChange, this);
    }
    this.resources = null;
  }
  onResourceChange(resource) {
    this._dirty = true;
    if (resource.destroyed) {
      const resources = this.resources;
      for (const i in resources) {
        if (resources[i] === resource) {
          resources[i] = null;
        }
      }
      warn(`[BindGroup] a '${resource._resourceType}' was destroyed while still bound to a shader. Remove it from the shader before destroying it.`);
    }
  }
}

export { BindGroup };
//# sourceMappingURL=BindGroup.mjs.map
