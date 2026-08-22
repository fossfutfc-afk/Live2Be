import type { GraphicsPath } from '../path/GraphicsPath';
/**
 * Converts a `GraphicsPath` into an SVG path `d` attribute string.
 * Mirrors `parseSVGPath` but in the reverse direction.
 * @param path - The GraphicsPath to convert.
 * @param precision - Number of decimal places for coordinates.
 * @param flatten - When true, forces curve/arc geometry to be emitted as polylines.
 *                  Used when the parser's naive area estimator must parse every number
 *                  as a coordinate (e.g. hole subpaths).
 * @returns The SVG `d` attribute value.
 * @internal
 */
export declare function buildSVGPath(path: GraphicsPath, precision?: number, flatten?: boolean): string;
