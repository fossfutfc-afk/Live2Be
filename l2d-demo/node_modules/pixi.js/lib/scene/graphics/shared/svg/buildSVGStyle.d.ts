import type { ConvertedFillStyle, ConvertedStrokeStyle } from '../FillTypes';
import type { SVGDefsCollector } from './buildSVGDefinitions';
/**
 * Converts a fill style into SVG attribute string fragments.
 * Handles solid colours and gradients (via the defs collector).
 * @param style
 * @param defs
 * @internal
 */
export declare function buildSVGFillAttributes(style: ConvertedFillStyle, defs: SVGDefsCollector): string;
/**
 * Converts a stroke style into SVG attribute string fragments.
 * @param style
 * @param defs
 * @internal
 */
export declare function buildSVGStrokeAttributes(style: ConvertedStrokeStyle, defs: SVGDefsCollector): string;
