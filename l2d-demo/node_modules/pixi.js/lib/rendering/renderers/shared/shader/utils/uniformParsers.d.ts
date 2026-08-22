import type { UNIFORM_TYPES, UniformData } from '../types';
interface UniformParserDefinition {
    type: UNIFORM_TYPES;
    test(data: UniformData): boolean;
    ubo?: string;
    uniform?: string;
}
/** @internal */
export declare const uniformParsers: UniformParserDefinition[];
export {};
