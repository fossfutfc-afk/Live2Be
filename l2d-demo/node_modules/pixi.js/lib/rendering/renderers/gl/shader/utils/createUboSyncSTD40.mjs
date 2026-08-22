import { compileBufferSync } from '../../../shared/shader/utils/compileBufferSync.mjs';
import { uboSyncFunctionsSTD40 } from '../../../shared/shader/utils/uboSyncFunctions.mjs';
import { generateArraySyncSTD40 } from './generateArraySyncSTD40.mjs';

"use strict";
function createUboSyncFunctionSTD40(uboElements) {
  return compileBufferSync(
    uboElements,
    uboSyncFunctionsSTD40,
    generateArraySyncSTD40
  );
}

export { createUboSyncFunctionSTD40 };
//# sourceMappingURL=createUboSyncSTD40.mjs.map
