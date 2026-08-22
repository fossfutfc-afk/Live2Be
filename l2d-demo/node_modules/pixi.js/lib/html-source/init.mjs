import { extensions } from '../extensions/Extensions.mjs';
import { ElementImageSource } from './ElementImageSource.mjs';
import { glUploadHTMLResource } from './glUploadHTMLResource.mjs';
import { gpuUploadHTMLResource } from './gpuUploadHTMLResource.mjs';
import { HTMLSource } from './HTMLSource.mjs';
import './index.mjs';

"use strict";
extensions.add(
  HTMLSource,
  ElementImageSource,
  glUploadHTMLResource,
  gpuUploadHTMLResource
);

export { ElementImageSource, HTMLSource, glUploadHTMLResource, gpuUploadHTMLResource };
//# sourceMappingURL=init.mjs.map
