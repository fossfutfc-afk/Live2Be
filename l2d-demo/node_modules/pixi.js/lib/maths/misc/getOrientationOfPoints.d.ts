/**
 * Determines the winding order of a polygon's points.
 * @param points - Flat array of point coordinates [x1, y1, x2, y2, ...]
 * @returns 1 for clockwise, -1 for counter-clockwise winding
 * @category maths
 * @internal
 */
export declare function getOrientationOfPoints(points: number[]): number;
