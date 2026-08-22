import type { ConvertedFillStyle } from '../FillTypes';
/**
 * Collects gradient/pattern definitions encountered during SVG export.
 * After all elements are processed, call `build()` to emit the `<defs>` block.
 * @internal
 */
export declare class SVGDefsCollector {
    private readonly _gradients;
    private _nextId;
    /**
     * Registers a gradient from a fill/stroke style and returns a `url(#id)` reference.
     * If the style has no gradient, returns `null`.
     * @param style
     */
    addStyle(style: ConvertedFillStyle): string | null;
    /** Renders the collected definitions as an SVG `<defs>` string. */
    build(): string;
}
