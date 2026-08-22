import { ExtensionType } from '../extensions/Extensions';
import type { GpuTextureUploader } from '../rendering/renderers/gpu/texture/uploaders/GpuTextureUploader';
import type { HTMLUploadableSource } from './HTMLSourceTypes';
/** @internal */
export declare const gpuUploadHTMLResource: GpuTextureUploader<HTMLUploadableSource> & {
    extension: {
        type: ExtensionType;
        name: string;
    };
};
