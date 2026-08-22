import { ExtensionType } from '../extensions/Extensions.mjs';

"use strict";
const gpuUploadHTMLResource = {
  extension: {
    type: ExtensionType.TextureUploaderWebGPU,
    name: "html"
  },
  type: "html",
  upload(source, gpuTexture, gpu, originZOverride = 0) {
    const queue = gpu.device.queue;
    const copyElementImageToTexture = queue.copyElementImageToTexture;
    if (!copyElementImageToTexture) {
      throw new Error(
        // eslint-disable-next-line max-len
        "[HTMLSource] GPUQueue.copyElementImageToTexture is not available. Enable the browser HTML-in-Canvas API before using HTMLSource."
      );
    }
    if (!source.isReady) {
      source.requestPaint?.();
      return;
    }
    const premultipliedAlpha = source.alphaMode === "premultiply-alpha-on-upload";
    const destination = {
      texture: gpuTexture,
      origin: { x: 0, y: 0, z: originZOverride },
      premultipliedAlpha
    };
    const width = Math.min(gpuTexture.width, source.pixelWidth);
    const height = Math.min(gpuTexture.height, source.pixelHeight);
    if (copyElementImageToTexture.length === 2) {
      copyElementImageToTexture.call(
        queue,
        { source: source.resource },
        { destination, width, height }
      );
    } else {
      copyElementImageToTexture.call(
        queue,
        source.resource,
        width,
        height,
        destination
      );
    }
  }
};

export { gpuUploadHTMLResource };
//# sourceMappingURL=gpuUploadHTMLResource.mjs.map
