import { compileBufferSync } from '../../../shared/shader/utils/compileBufferSync.mjs';
import { uboSyncFunctionsWGSL } from '../../../shared/shader/utils/uboSyncFunctions.mjs';
import { generateArraySyncWGSL } from './generateArraySyncWGSL.mjs';

"use strict";
function createUboSyncFunctionWGSL(uboElements) {
  return compileBufferSync(
    uboElements,
    uboSyncFunctionsWGSL,
    generateArraySyncWGSL
  );
}

export { createUboSyncFunctionWGSL };
//# sourceMappingURL=createUboSyncFunctionWGSL.mjs.map
