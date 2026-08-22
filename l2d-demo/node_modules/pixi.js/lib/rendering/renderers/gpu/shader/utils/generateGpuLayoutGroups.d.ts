import type { ProgramPipelineLayoutDescription } from '../GpuProgram';
import type { StructsAndGroups } from './extractStructAndGroups';
/**
 * Generates the default WebGPU bind group layout for a shader from its extracted structs and groups.
 * Every binding is marked visible to both the vertex and fragment stages
 * (`GPUShaderStage.VERTEX | GPUShaderStage.FRAGMENT`).
 *
 * This is the same generator {@link GpuProgram} uses internally when no `gpuLayout` is supplied.
 * It is exported so you can build the default layout, tweak only the entries you care about
 * (for example narrowing a binding's `visibility` to a single stage), and pass the complete
 * result back in via the `gpuLayout` option - rather than hand-authoring the whole layout:
 * @example
 * import { extractStructAndGroups, generateGpuLayoutGroups, GpuProgram } from 'pixi.js';
 *
 * const gpuLayout = generateGpuLayoutGroups(extractStructAndGroups(source));
 *
 * // only expose this texture to the fragment stage
 * gpuLayout[0][1].visibility = GPUShaderStage.FRAGMENT;
 *
 * const program = new GpuProgram({ vertex, fragment, gpuLayout });
 * @param root0 - The structs and groups extracted from the shader source, typically produced by
 * {@link extractStructAndGroups}.
 * @param root0.groups - The `@group`/`@binding` entries parsed from the WGSL source.
 * @returns The generated bind group layout description, one entry array per bind group.
 * @category rendering
 * @advanced
 */
export declare function generateGpuLayoutGroups({ groups }: StructsAndGroups): ProgramPipelineLayoutDescription;
