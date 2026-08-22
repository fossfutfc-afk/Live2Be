import { Matrix } from '../../../maths/matrix/Matrix.mjs';
import { applyMatrix } from './applyMatrix.mjs';

"use strict";
function setUvs(tilingSprite, uvs) {
  const texture = tilingSprite.texture;
  const width = texture.frame.width;
  const height = texture.frame.height;
  let anchorX = 0;
  let anchorY = 0;
  if (tilingSprite.applyAnchorToTexture) {
    anchorX = tilingSprite.anchor.x;
    anchorY = tilingSprite.anchor.y;
  }
  uvs[0] = uvs[6] = -anchorX;
  uvs[2] = uvs[4] = 1 - anchorX;
  uvs[1] = uvs[3] = -anchorY;
  uvs[5] = uvs[7] = 1 - anchorY;
  const tileMatrix = tilingSprite._tileTransform.matrix;
  const textureMatrix = Matrix.shared;
  textureMatrix.set(
    tileMatrix.a * width / tilingSprite.width,
    tileMatrix.b * width / tilingSprite.height,
    tileMatrix.c * height / tilingSprite.width,
    tileMatrix.d * height / tilingSprite.height,
    tileMatrix.tx / tilingSprite.width,
    tileMatrix.ty / tilingSprite.height
  );
  textureMatrix.invert();
  applyMatrix(uvs, 2, 0, textureMatrix);
}

export { setUvs };
//# sourceMappingURL=setUvs.mjs.map
