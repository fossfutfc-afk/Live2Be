"use strict";
function isRenderingToScreen(renderTarget) {
  if (renderTarget.colorAttachments.length === 0) return false;
  const resource = renderTarget.colorTexture.resource;
  return globalThis.HTMLCanvasElement && resource instanceof HTMLCanvasElement && document.body.contains(resource);
}

export { isRenderingToScreen };
//# sourceMappingURL=isRenderingToScreen.mjs.map
