import { GraphicsContext } from '../GraphicsContext';
import type { Graphics } from '../Graphics';
/**
 * Converts a Graphics object or GraphicsContext into an SVG string.
 *
 * This is a pure function — it reads from the context's instructions and
 * returns a self-contained SVG document string. Texture instructions are
 * skipped since they have no SVG equivalent.
 * @param source - A Graphics instance or a GraphicsContext.
 * @param precision - Decimal places for SVG coordinates (default 2).
 * @returns A complete SVG document string.
 * @category scene
 * @standard
 */
export declare function graphicsContextToSvg(source: Graphics | GraphicsContext, precision?: number): string;
