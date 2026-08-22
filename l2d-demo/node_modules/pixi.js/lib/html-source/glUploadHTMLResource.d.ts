import { ExtensionType } from '../extensions/Extensions';
import type { GLTextureUploader } from '../rendering/renderers/gl/texture/uploaders/GLTextureUploader';
/** @internal */
export declare const glUploadHTMLResource: GLTextureUploader & {
    extension: {
        type: ExtensionType;
        name: string;
    };
};
