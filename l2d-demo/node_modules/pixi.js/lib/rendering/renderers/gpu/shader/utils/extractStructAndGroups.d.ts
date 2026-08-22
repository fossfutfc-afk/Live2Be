/**
 * The access mode for a buffer binding in WGSL
 * @category rendering
 * @advanced
 */
export type WgslAccessMode = 'uniform' | 'storage' | undefined;
/**
 * Defines the structure of the extracted WGSL structs and groups.
 * @category rendering
 * @advanced
 */
export interface StructsAndGroups {
    groups: {
        group: number;
        binding: number;
        name: string;
        /** The access mode for buffer bindings: 'uniform', 'storage', or undefined for textures/samplers */
        accessMode: WgslAccessMode;
        type: string;
    }[];
    structs: {
        name: string;
        members: Record<string, string>;
    }[];
}
/**
 * Parses a WGSL shader source and extracts its `@group`/`@binding` declarations and the
 * structs they reference. The result feeds {@link generateGpuLayoutGroups} to build a
 * WebGPU bind group layout.
 * @param wgsl - The WGSL shader source to parse.
 * @returns The structs and `@group`/`@binding` groups found in the source.
 * @category rendering
 * @advanced
 */
export declare function extractStructAndGroups(wgsl: string): StructsAndGroups;
