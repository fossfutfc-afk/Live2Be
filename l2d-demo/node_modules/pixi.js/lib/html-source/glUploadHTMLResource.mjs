import { ExtensionType } from '../extensions/Extensions.mjs';

"use strict";
function ensureAllocated(gl, glTexture, target, width, height) {
  if (glTexture.width === width && glTexture.height === height) {
    return;
  }
  gl.texImage2D(
    target,
    0,
    glTexture.internalFormat,
    width,
    height,
    0,
    glTexture.format,
    glTexture.type,
    null
  );
  glTexture.width = width;
  glTexture.height = height;
}
const glUploadHTMLResource = {
  extension: {
    type: ExtensionType.TextureUploaderWebGL,
    name: "html"
  },
  id: "html",
  upload(source, glTexture, gl, _webGLVersion, targetOverride) {
    const upload = gl.texElementImage2D;
    if (!upload) {
      throw new Error(
        // eslint-disable-next-line max-len
        "[HTMLSource] WebGLRenderingContext.texElementImage2D is not available. Enable the browser HTML-in-Canvas API before using HTMLSource."
      );
    }
    const target = targetOverride ?? glTexture.target;
    const textureWidth = source.pixelWidth;
    const textureHeight = source.pixelHeight;
    if (!source.isReady) {
      ensureAllocated(gl, glTexture, target, textureWidth, textureHeight);
      source.requestPaint?.();
      return;
    }
    if (upload.length === 3) {
      upload.call(gl, target, glTexture.internalFormat, source.resource);
    } else {
      upload.call(
        gl,
        target,
        0,
        glTexture.internalFormat,
        glTexture.format,
        glTexture.type,
        source.resource
      );
    }
    glTexture.width = textureWidth;
    glTexture.height = textureHeight;
  }
};

export { glUploadHTMLResource };
//# sourceMappingURL=glUploadHTMLResource.mjs.map
