/**
 * A specialized class that handles the caching and identification of shader overrides.
 * Shader overrides are used to inject constants into a shader pipeline, allowing for
 * powerful customization without the need for recompiling the shader source.
 *
 * This class ensures that override configurations are unique and immutable, allowing
 * the renderer to efficiently cache pipelines based on these configurations.
 * @category rendering
 * @advanced
 */
export declare class ShaderOverrides {
    /** The unique ID of the override configuration. Used for efficient caching. */
    readonly id: number;
    /** The dictionary of constants to override. */
    readonly data: Record<string, number>;
    /**
     * @param data - A dictionary of constants to set on the shader.
     * Keys should match the constant names in the WGSL shader.
     */
    constructor(data: Record<string, number>);
    /**
     * Creates a ShaderOverrides instance from a plain object or existing instance.
     * @param overrides - The overrides to convert.
     * @returns A ShaderOverrides instance.
     */
    static from(overrides: Record<string, number> | ShaderOverrides): ShaderOverrides;
}
