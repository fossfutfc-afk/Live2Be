/******************************************************************************
 * Spine Runtimes License Agreement
 * Last updated April 5, 2025. Replaces all prior versions.
 *
 * Copyright (c) 2013-2025, Esoteric Software LLC
 *
 * Integration of the Spine Runtimes into software or otherwise creating
 * derivative works of the Spine Runtimes is permitted under the terms and
 * conditions of Section 2 of the Spine Editor License Agreement:
 * http://esotericsoftware.com/spine-editor-license
 *
 * Otherwise, it is permitted to integrate the Spine Runtimes into software
 * or otherwise create derivative works of the Spine Runtimes (collectively,
 * "Products"), provided that each user of the Products must obtain their own
 * Spine Editor license and redistribution of the Products in any form must
 * include this license and copyright notice.
 *
 * THE SPINE RUNTIMES ARE PROVIDED BY ESOTERIC SOFTWARE LLC "AS IS" AND ANY
 * EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL ESOTERIC SOFTWARE LLC BE LIABLE FOR ANY
 * DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES,
 * BUSINESS INTERRUPTION, OR LOSS OF USE, DATA, OR PROFITS) HOWEVER CAUSED AND
 * ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
 * THE SPINE RUNTIMES, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *****************************************************************************/
import { Triangulator } from "./Triangulator.js";
import { Utils } from "./Utils.js";
export class SkeletonClipping {
    triangulator = new Triangulator();
    clippingPolygon = new Array();
    clipOutput = new Array();
    clippedVertices = new Array();
    clippedUVs = new Array();
    clippedTriangles = new Array();
    scratch = new Array();
    clipAttachment = null;
    clippingPolygons = null;
    clipStart(slot, clip) {
        if (this.clipAttachment)
            return 0;
        this.clipAttachment = clip;
        let n = clip.worldVerticesLength;
        let vertices = Utils.setArraySize(this.clippingPolygon, n);
        clip.computeWorldVertices(slot, 0, n, vertices, 0, 2);
        let clippingPolygon = this.clippingPolygon;
        SkeletonClipping.makeClockwise(clippingPolygon);
        let clippingPolygons = this.clippingPolygons = this.triangulator.decompose(clippingPolygon, this.triangulator.triangulate(clippingPolygon));
        for (let i = 0, n = clippingPolygons.length; i < n; i++) {
            let polygon = clippingPolygons[i];
            SkeletonClipping.makeClockwise(polygon);
            polygon.push(polygon[0]);
            polygon.push(polygon[1]);
        }
        return clippingPolygons.length;
    }
    clipEndWithSlot(slot) {
        if (this.clipAttachment && this.clipAttachment.endSlot == slot.data)
            this.clipEnd();
    }
    clipEnd() {
        if (!this.clipAttachment)
            return;
        this.clipAttachment = null;
        this.clippingPolygons = null;
        this.clippedVertices.length = 0;
        this.clippedTriangles.length = 0;
        this.clippingPolygon.length = 0;
    }
    isClipping() {
        return this.clipAttachment != null;
    }
    clipTriangles(vertices, verticesLengthOrTriangles, trianglesOrTrianglesLength, trianglesLengthOrUvs, uvsOrLight, lightOrDark, darkOrTwoColor, twoColorParam) {
        // Determine which overload is being used
        let triangles;
        let trianglesLength;
        let uvs;
        let light;
        let dark;
        let twoColor;
        if (typeof verticesLengthOrTriangles === 'number') {
            triangles = trianglesOrTrianglesLength;
            trianglesLength = trianglesLengthOrUvs;
            uvs = uvsOrLight;
            light = lightOrDark;
            dark = darkOrTwoColor;
            twoColor = twoColorParam;
        }
        else {
            triangles = verticesLengthOrTriangles;
            trianglesLength = trianglesOrTrianglesLength;
            uvs = trianglesLengthOrUvs;
            light = uvsOrLight;
            dark = lightOrDark;
            twoColor = darkOrTwoColor;
        }
        if (uvs && light && dark && typeof twoColor === 'boolean')
            this.clipTrianglesRender(vertices, triangles, trianglesLength, uvs, light, dark, twoColor);
        else
            this.clipTrianglesNoRender(vertices, triangles, trianglesLength);
    }
    clipTrianglesNoRender(vertices, triangles, trianglesLength) {
        let clipOutput = this.clipOutput, clippedVertices = this.clippedVertices;
        let clippedTriangles = this.clippedTriangles;
        let polygons = this.clippingPolygons;
        let polygonsCount = polygons.length;
        let index = 0;
        clippedVertices.length = 0;
        clippedTriangles.length = 0;
        for (let i = 0; i < trianglesLength; i += 3) {
            let vertexOffset = triangles[i] << 1;
            let x1 = vertices[vertexOffset], y1 = vertices[vertexOffset + 1];
            vertexOffset = triangles[i + 1] << 1;
            let x2 = vertices[vertexOffset], y2 = vertices[vertexOffset + 1];
            vertexOffset = triangles[i + 2] << 1;
            let x3 = vertices[vertexOffset], y3 = vertices[vertexOffset + 1];
            for (let p = 0; p < polygonsCount; p++) {
                let s = clippedVertices.length;
                if (this.clip(x1, y1, x2, y2, x3, y3, polygons[p], clipOutput)) {
                    let clipOutputLength = clipOutput.length;
                    if (clipOutputLength == 0)
                        continue;
                    let clipOutputCount = clipOutputLength >> 1;
                    let clipOutputItems = this.clipOutput;
                    let clippedVerticesItems = Utils.setArraySize(clippedVertices, s + clipOutputCount * 2);
                    for (let ii = 0; ii < clipOutputLength; ii += 2, s += 2) {
                        let x = clipOutputItems[ii], y = clipOutputItems[ii + 1];
                        clippedVerticesItems[s] = x;
                        clippedVerticesItems[s + 1] = y;
                    }
                    s = clippedTriangles.length;
                    let clippedTrianglesItems = Utils.setArraySize(clippedTriangles, s + 3 * (clipOutputCount - 2));
                    clipOutputCount--;
                    for (let ii = 1; ii < clipOutputCount; ii++, s += 3) {
                        clippedTrianglesItems[s] = index;
                        clippedTrianglesItems[s + 1] = (index + ii);
                        clippedTrianglesItems[s + 2] = (index + ii + 1);
                    }
                    index += clipOutputCount + 1;
                }
                else {
                    let clippedVerticesItems = Utils.setArraySize(clippedVertices, s + 3 * 2);
                    clippedVerticesItems[s] = x1;
                    clippedVerticesItems[s + 1] = y1;
                    clippedVerticesItems[s + 2] = x2;
                    clippedVerticesItems[s + 3] = y2;
                    clippedVerticesItems[s + 4] = x3;
                    clippedVerticesItems[s + 5] = y3;
                    s = clippedTriangles.length;
                    let clippedTrianglesItems = Utils.setArraySize(clippedTriangles, s + 3);
                    clippedTrianglesItems[s] = index;
                    clippedTrianglesItems[s + 1] = (index + 1);
                    clippedTrianglesItems[s + 2] = (index + 2);
                    index += 3;
                    break;
                }
            }
        }
    }
    clipTrianglesRender(vertices, triangles, trianglesLength, uvs, light, dark, twoColor) {
        let clipOutput = this.clipOutput, clippedVertices = this.clippedVertices;
        let clippedTriangles = this.clippedTriangles;
        let polygons = this.clippingPolygons;
        let polygonsCount = polygons.length;
        let vertexSize = twoColor ? 12 : 8;
        let index = 0;
        clippedVertices.length = 0;
        clippedTriangles.length = 0;
        for (let i = 0; i < trianglesLength; i += 3) {
            let vertexOffset = triangles[i] << 1;
            let x1 = vertices[vertexOffset], y1 = vertices[vertexOffset + 1];
            let u1 = uvs[vertexOffset], v1 = uvs[vertexOffset + 1];
            vertexOffset = triangles[i + 1] << 1;
            let x2 = vertices[vertexOffset], y2 = vertices[vertexOffset + 1];
            let u2 = uvs[vertexOffset], v2 = uvs[vertexOffset + 1];
            vertexOffset = triangles[i + 2] << 1;
            let x3 = vertices[vertexOffset], y3 = vertices[vertexOffset + 1];
            let u3 = uvs[vertexOffset], v3 = uvs[vertexOffset + 1];
            for (let p = 0; p < polygonsCount; p++) {
                let s = clippedVertices.length;
                if (this.clip(x1, y1, x2, y2, x3, y3, polygons[p], clipOutput)) {
                    let clipOutputLength = clipOutput.length;
                    if (clipOutputLength == 0)
                        continue;
                    let d0 = y2 - y3, d1 = x3 - x2, d2 = x1 - x3, d4 = y3 - y1;
                    let d = 1 / (d0 * d2 + d1 * (y1 - y3));
                    let clipOutputCount = clipOutputLength >> 1;
                    let clipOutputItems = this.clipOutput;
                    let clippedVerticesItems = Utils.setArraySize(clippedVertices, s + clipOutputCount * vertexSize);
                    for (let ii = 0; ii < clipOutputLength; ii += 2, s += vertexSize) {
                        let x = clipOutputItems[ii], y = clipOutputItems[ii + 1];
                        clippedVerticesItems[s] = x;
                        clippedVerticesItems[s + 1] = y;
                        clippedVerticesItems[s + 2] = light.r;
                        clippedVerticesItems[s + 3] = light.g;
                        clippedVerticesItems[s + 4] = light.b;
                        clippedVerticesItems[s + 5] = light.a;
                        let c0 = x - x3, c1 = y - y3;
                        let a = (d0 * c0 + d1 * c1) * d;
                        let b = (d4 * c0 + d2 * c1) * d;
                        let c = 1 - a - b;
                        clippedVerticesItems[s + 6] = u1 * a + u2 * b + u3 * c;
                        clippedVerticesItems[s + 7] = v1 * a + v2 * b + v3 * c;
                        if (twoColor) {
                            clippedVerticesItems[s + 8] = dark.r;
                            clippedVerticesItems[s + 9] = dark.g;
                            clippedVerticesItems[s + 10] = dark.b;
                            clippedVerticesItems[s + 11] = dark.a;
                        }
                    }
                    s = clippedTriangles.length;
                    let clippedTrianglesItems = Utils.setArraySize(clippedTriangles, s + 3 * (clipOutputCount - 2));
                    clipOutputCount--;
                    for (let ii = 1; ii < clipOutputCount; ii++, s += 3) {
                        clippedTrianglesItems[s] = index;
                        clippedTrianglesItems[s + 1] = (index + ii);
                        clippedTrianglesItems[s + 2] = (index + ii + 1);
                    }
                    index += clipOutputCount + 1;
                }
                else {
                    let clippedVerticesItems = Utils.setArraySize(clippedVertices, s + 3 * vertexSize);
                    clippedVerticesItems[s] = x1;
                    clippedVerticesItems[s + 1] = y1;
                    clippedVerticesItems[s + 2] = light.r;
                    clippedVerticesItems[s + 3] = light.g;
                    clippedVerticesItems[s + 4] = light.b;
                    clippedVerticesItems[s + 5] = light.a;
                    if (!twoColor) {
                        clippedVerticesItems[s + 6] = u1;
                        clippedVerticesItems[s + 7] = v1;
                        clippedVerticesItems[s + 8] = x2;
                        clippedVerticesItems[s + 9] = y2;
                        clippedVerticesItems[s + 10] = light.r;
                        clippedVerticesItems[s + 11] = light.g;
                        clippedVerticesItems[s + 12] = light.b;
                        clippedVerticesItems[s + 13] = light.a;
                        clippedVerticesItems[s + 14] = u2;
                        clippedVerticesItems[s + 15] = v2;
                        clippedVerticesItems[s + 16] = x3;
                        clippedVerticesItems[s + 17] = y3;
                        clippedVerticesItems[s + 18] = light.r;
                        clippedVerticesItems[s + 19] = light.g;
                        clippedVerticesItems[s + 20] = light.b;
                        clippedVerticesItems[s + 21] = light.a;
                        clippedVerticesItems[s + 22] = u3;
                        clippedVerticesItems[s + 23] = v3;
                    }
                    else {
                        clippedVerticesItems[s + 6] = u1;
                        clippedVerticesItems[s + 7] = v1;
                        clippedVerticesItems[s + 8] = dark.r;
                        clippedVerticesItems[s + 9] = dark.g;
                        clippedVerticesItems[s + 10] = dark.b;
                        clippedVerticesItems[s + 11] = dark.a;
                        clippedVerticesItems[s + 12] = x2;
                        clippedVerticesItems[s + 13] = y2;
                        clippedVerticesItems[s + 14] = light.r;
                        clippedVerticesItems[s + 15] = light.g;
                        clippedVerticesItems[s + 16] = light.b;
                        clippedVerticesItems[s + 17] = light.a;
                        clippedVerticesItems[s + 18] = u2;
                        clippedVerticesItems[s + 19] = v2;
                        clippedVerticesItems[s + 20] = dark.r;
                        clippedVerticesItems[s + 21] = dark.g;
                        clippedVerticesItems[s + 22] = dark.b;
                        clippedVerticesItems[s + 23] = dark.a;
                        clippedVerticesItems[s + 24] = x3;
                        clippedVerticesItems[s + 25] = y3;
                        clippedVerticesItems[s + 26] = light.r;
                        clippedVerticesItems[s + 27] = light.g;
                        clippedVerticesItems[s + 28] = light.b;
                        clippedVerticesItems[s + 29] = light.a;
                        clippedVerticesItems[s + 30] = u3;
                        clippedVerticesItems[s + 31] = v3;
                        clippedVerticesItems[s + 32] = dark.r;
                        clippedVerticesItems[s + 33] = dark.g;
                        clippedVerticesItems[s + 34] = dark.b;
                        clippedVerticesItems[s + 35] = dark.a;
                    }
                    s = clippedTriangles.length;
                    let clippedTrianglesItems = Utils.setArraySize(clippedTriangles, s + 3);
                    clippedTrianglesItems[s] = index;
                    clippedTrianglesItems[s + 1] = (index + 1);
                    clippedTrianglesItems[s + 2] = (index + 2);
                    index += 3;
                    break;
                }
            }
        }
    }
    clipTrianglesUnpacked(vertices, triangles, trianglesLength, uvs) {
        let clipOutput = this.clipOutput, clippedVertices = this.clippedVertices, clippedUVs = this.clippedUVs;
        let clippedTriangles = this.clippedTriangles;
        let polygons = this.clippingPolygons;
        let polygonsCount = polygons.length;
        let index = 0;
        clippedVertices.length = 0;
        clippedUVs.length = 0;
        clippedTriangles.length = 0;
        for (let i = 0; i < trianglesLength; i += 3) {
            let vertexOffset = triangles[i] << 1;
            let x1 = vertices[vertexOffset], y1 = vertices[vertexOffset + 1];
            let u1 = uvs[vertexOffset], v1 = uvs[vertexOffset + 1];
            vertexOffset = triangles[i + 1] << 1;
            let x2 = vertices[vertexOffset], y2 = vertices[vertexOffset + 1];
            let u2 = uvs[vertexOffset], v2 = uvs[vertexOffset + 1];
            vertexOffset = triangles[i + 2] << 1;
            let x3 = vertices[vertexOffset], y3 = vertices[vertexOffset + 1];
            let u3 = uvs[vertexOffset], v3 = uvs[vertexOffset + 1];
            for (let p = 0; p < polygonsCount; p++) {
                let s = clippedVertices.length;
                if (this.clip(x1, y1, x2, y2, x3, y3, polygons[p], clipOutput)) {
                    let clipOutputLength = clipOutput.length;
                    if (clipOutputLength == 0)
                        continue;
                    let d0 = y2 - y3, d1 = x3 - x2, d2 = x1 - x3, d4 = y3 - y1;
                    let d = 1 / (d0 * d2 + d1 * (y1 - y3));
                    let clipOutputCount = clipOutputLength >> 1;
                    let clipOutputItems = this.clipOutput;
                    let clippedVerticesItems = Utils.setArraySize(clippedVertices, s + clipOutputCount * 2);
                    let clippedUVsItems = Utils.setArraySize(clippedUVs, s + clipOutputCount * 2);
                    for (let ii = 0; ii < clipOutputLength; ii += 2, s += 2) {
                        let x = clipOutputItems[ii], y = clipOutputItems[ii + 1];
                        clippedVerticesItems[s] = x;
                        clippedVerticesItems[s + 1] = y;
                        let c0 = x - x3, c1 = y - y3;
                        let a = (d0 * c0 + d1 * c1) * d;
                        let b = (d4 * c0 + d2 * c1) * d;
                        let c = 1 - a - b;
                        clippedUVsItems[s] = u1 * a + u2 * b + u3 * c;
                        clippedUVsItems[s + 1] = v1 * a + v2 * b + v3 * c;
                    }
                    s = clippedTriangles.length;
                    let clippedTrianglesItems = Utils.setArraySize(clippedTriangles, s + 3 * (clipOutputCount - 2));
                    clipOutputCount--;
                    for (let ii = 1; ii < clipOutputCount; ii++, s += 3) {
                        clippedTrianglesItems[s] = index;
                        clippedTrianglesItems[s + 1] = (index + ii);
                        clippedTrianglesItems[s + 2] = (index + ii + 1);
                    }
                    index += clipOutputCount + 1;
                }
                else {
                    let clippedVerticesItems = Utils.setArraySize(clippedVertices, s + 3 * 2);
                    clippedVerticesItems[s] = x1;
                    clippedVerticesItems[s + 1] = y1;
                    clippedVerticesItems[s + 2] = x2;
                    clippedVerticesItems[s + 3] = y2;
                    clippedVerticesItems[s + 4] = x3;
                    clippedVerticesItems[s + 5] = y3;
                    let clippedUVSItems = Utils.setArraySize(clippedUVs, s + 3 * 2);
                    clippedUVSItems[s] = u1;
                    clippedUVSItems[s + 1] = v1;
                    clippedUVSItems[s + 2] = u2;
                    clippedUVSItems[s + 3] = v2;
                    clippedUVSItems[s + 4] = u3;
                    clippedUVSItems[s + 5] = v3;
                    s = clippedTriangles.length;
                    let clippedTrianglesItems = Utils.setArraySize(clippedTriangles, s + 3);
                    clippedTrianglesItems[s] = index;
                    clippedTrianglesItems[s + 1] = (index + 1);
                    clippedTrianglesItems[s + 2] = (index + 2);
                    index += 3;
                    break;
                }
            }
        }
    }
    /** Clips the input triangle against the convex, clockwise clipping area. If the triangle lies entirely within the clipping
     * area, false is returned. The clipping area must duplicate the first vertex at the end of the vertices list. */
    clip(x1, y1, x2, y2, x3, y3, clippingArea, output) {
        let originalOutput = output;
        let clipped = false;
        // Avoid copy at the end.
        let input;
        if (clippingArea.length % 4 >= 2) {
            input = output;
            output = this.scratch;
        }
        else
            input = this.scratch;
        input.length = 0;
        input.push(x1);
        input.push(y1);
        input.push(x2);
        input.push(y2);
        input.push(x3);
        input.push(y3);
        input.push(x1);
        input.push(y1);
        output.length = 0;
        let clippingVerticesLast = clippingArea.length - 4;
        let clippingVertices = clippingArea;
        for (let i = 0;; i += 2) {
            let edgeX = clippingVertices[i], edgeY = clippingVertices[i + 1];
            let ex = edgeX - clippingVertices[i + 2], ey = edgeY - clippingVertices[i + 3];
            let outputStart = output.length;
            let inputVertices = input;
            for (let ii = 0, nn = input.length - 2; ii < nn;) {
                let inputX = inputVertices[ii], inputY = inputVertices[ii + 1];
                ii += 2;
                let inputX2 = inputVertices[ii], inputY2 = inputVertices[ii + 1];
                let s2 = ey * (edgeX - inputX2) > ex * (edgeY - inputY2);
                let s1 = ey * (edgeX - inputX) - ex * (edgeY - inputY);
                if (s1 > 0) {
                    if (s2) { // v1 inside, v2 inside
                        output.push(inputX2);
                        output.push(inputY2);
                        continue;
                    }
                    // v1 inside, v2 outside
                    let ix = inputX2 - inputX, iy = inputY2 - inputY, t = s1 / (ix * ey - iy * ex);
                    if (t >= 0 && t <= 1) {
                        output.push(inputX + ix * t);
                        output.push(inputY + iy * t);
                    }
                    else {
                        output.push(inputX2);
                        output.push(inputY2);
                        continue;
                    }
                }
                else if (s2) { // v1 outside, v2 inside
                    let ix = inputX2 - inputX, iy = inputY2 - inputY, t = s1 / (ix * ey - iy * ex);
                    if (t >= 0 && t <= 1) {
                        output.push(inputX + ix * t);
                        output.push(inputY + iy * t);
                        output.push(inputX2);
                        output.push(inputY2);
                    }
                    else {
                        output.push(inputX2);
                        output.push(inputY2);
                        continue;
                    }
                }
                clipped = true;
            }
            if (outputStart == output.length) { // All edges outside.
                originalOutput.length = 0;
                return true;
            }
            output.push(output[0]);
            output.push(output[1]);
            if (i == clippingVerticesLast)
                break;
            let temp = output;
            output = input;
            output.length = 0;
            input = temp;
        }
        if (originalOutput != output) {
            originalOutput.length = 0;
            for (let i = 0, n = output.length - 2; i < n; i++)
                originalOutput[i] = output[i];
        }
        else
            originalOutput.length = originalOutput.length - 2;
        return clipped;
    }
    static makeClockwise(polygon) {
        let vertices = polygon;
        let verticeslength = polygon.length;
        let area = vertices[verticeslength - 2] * vertices[1] - vertices[0] * vertices[verticeslength - 1], p1x = 0, p1y = 0, p2x = 0, p2y = 0;
        for (let i = 0, n = verticeslength - 3; i < n; i += 2) {
            p1x = vertices[i];
            p1y = vertices[i + 1];
            p2x = vertices[i + 2];
            p2y = vertices[i + 3];
            area += p1x * p2y - p2x * p1y;
        }
        if (area < 0)
            return;
        for (let i = 0, lastX = verticeslength - 2, n = verticeslength >> 1; i < n; i += 2) {
            let x = vertices[i], y = vertices[i + 1];
            let other = lastX - i;
            vertices[i] = vertices[other];
            vertices[i + 1] = vertices[other + 1];
            vertices[other] = x;
            vertices[other + 1] = y;
        }
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiU2tlbGV0b25DbGlwcGluZy5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIi4uL3NyYy9Ta2VsZXRvbkNsaXBwaW5nLnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiJBQUFBOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7K0VBMkIrRTtBQUkvRSxPQUFPLEVBQUUsWUFBWSxFQUFFLE1BQU0sbUJBQW1CLENBQUM7QUFDakQsT0FBTyxFQUFFLEtBQUssRUFBMEIsTUFBTSxZQUFZLENBQUM7QUFFM0QsTUFBTSxPQUFPLGdCQUFnQjtJQUNwQixZQUFZLEdBQUcsSUFBSSxZQUFZLEVBQUUsQ0FBQztJQUNsQyxlQUFlLEdBQUcsSUFBSSxLQUFLLEVBQVUsQ0FBQztJQUN0QyxVQUFVLEdBQUcsSUFBSSxLQUFLLEVBQVUsQ0FBQztJQUN6QyxlQUFlLEdBQUcsSUFBSSxLQUFLLEVBQVUsQ0FBQztJQUN0QyxVQUFVLEdBQUcsSUFBSSxLQUFLLEVBQVUsQ0FBQztJQUNqQyxnQkFBZ0IsR0FBRyxJQUFJLEtBQUssRUFBVSxDQUFDO0lBQy9CLE9BQU8sR0FBRyxJQUFJLEtBQUssRUFBVSxDQUFDO0lBRTlCLGNBQWMsR0FBOEIsSUFBSSxDQUFDO0lBQ2pELGdCQUFnQixHQUFnQyxJQUFJLENBQUM7SUFFN0QsU0FBUyxDQUFFLElBQVUsRUFBRSxJQUF3QjtRQUM5QyxJQUFJLElBQUksQ0FBQyxjQUFjO1lBQUUsT0FBTyxDQUFDLENBQUM7UUFDbEMsSUFBSSxDQUFDLGNBQWMsR0FBRyxJQUFJLENBQUM7UUFFM0IsSUFBSSxDQUFDLEdBQUcsSUFBSSxDQUFDLG1CQUFtQixDQUFDO1FBQ2pDLElBQUksUUFBUSxHQUFHLEtBQUssQ0FBQyxZQUFZLENBQUMsSUFBSSxDQUFDLGVBQWUsRUFBRSxDQUFDLENBQUMsQ0FBQztRQUMzRCxJQUFJLENBQUMsb0JBQW9CLENBQUMsSUFBSSxFQUFFLENBQUMsRUFBRSxDQUFDLEVBQUUsUUFBUSxFQUFFLENBQUMsRUFBRSxDQUFDLENBQUMs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R0FBRyxDQUFDLENBQUM7UUFDM0IsZ0JBQWdCLENBQUMsTUFBTSxHQUFHLENBQUMsQ0FBQztRQUM1QixLQUFLLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsZUFBZSxFQUFFLENBQUMsSUFBSSxDQUFDLEVBQUUsQ0FBQztZQUM3QyxJQUFJLFlBQVksR0FBRyxTQUFTLENBQUMsQ0FBQyxDQUFDLElBQUksQ0FBQyxDQUFDO1lBQ3JDLElBQUksRUFBRSxHQUFHLFFBQVEsQ0FBQyxZQUFZLENBQUMsRUFBRSxFQUFFLEdBQUcsUUFBUSxDQUFDLFlBQVksR0FBRyxDQUFDLENBQUMsQ0FBQztZQUNqRSxJQUFJLEVBQUUsR0FBRyxHQUFHLENBQUMsWUFBWSxDQUFDLEVBQUUsRUFBRSxHQUFHLEdBQUcsQ0FBQyxZQUFZLEdBQUcsQ0FBQyxDQUFDLENBQUM7WUFFdkQsWUFBWSxHQUFHLFNBQVMsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLElBQUksQ0FBQyxDQUFDO1lBQ3JDLElBQUksRUFBRSxHQUFHLFFBQVEsQ0FBQyxZQUFZLENBQUMsRUFBRSxFQUFFLEdBQUcsUUFBUSxDQUFDLFlBQVksR0FBRyxDQUFDLENBQUMsQ0FBQztZQUNqRSxJQUFJLEVBQUUsR0FBRyxHQUFHLENBQUMsWUFBWSxDQUFDLEVBQUUsRUFBRSxHQUFHLEdBQUcsQ0FBQyxZQUFZLEdBQUcsQ0FBQyxDQUFDLENBQUM7WUFFdkQsWUFBWSxHQUFHLFNBQVMsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLElBQUksQ0FBQyxDQUFDO1lBQ3JDLElBQUksRUFBRSxHQUFHLFFBQVEsQ0FBQyxZQUFZLENBQUMsRUFBRSxFQUFFLEdBQUcsUUFBUSxDQUFDLFlBQVksR0FBRyxDQUFDLENBQUMsQ0FBQztZQUNqRSxJQUFJLEVBQUUsR0FBRyxHQUFHLENBQUMsWUFBWSxDQUFDLEVBQUUsRUFBRSxHQUFHLEdBQUcsQ0FBQyxZQUFZLEdBQUcsQ0FBQyxDQUFDLENBQUM7WUFFdkQsS0FBSyxJQUFJLENBQUMsR0FBRyxDQUFDLEVBQUUsQ0FBQyxH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Q0FBQyxDQUFDLENBQUMsR0FBRyxFQUFFLENBQUM7b0JBQzdCLG9CQUFvQixDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxFQUFFLENBQUM7b0JBQ2pDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDO29CQUN0QyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLEdBQUcsS0FBSyxDQUFDLENBQUMsQ0FBQztvQkFDdEMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLEtBQUssQ0FBQyxDQUFDLENBQUM7b0JBQ3RDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDO29CQUN0QyxJQUFJLENBQUMsUUFBUSxFQUFFLENBQUM7d0JBQ2Ysb0JBQW9CLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQzt3QkFDakMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQzt3QkFFakMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQzt3QkFDakMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQzt3QkFDakMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxHQUFHLEtBQUssQ0FBQyxDQUFDLENBQUM7d0JBQ3ZDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDO3dCQUN2QyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsS0FBSyxDQUFDLENBQUMsQ0FBQzt3QkFDdkMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxHQUFHLEtBQUssQ0FBQyxDQUFDLENBQUM7d0JBQ3ZDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxFQUFFLENBQUM7d0JBQ2xDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxFQUFFLENBQUM7d0JBRWxDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxFQUFFLENBQUM7d0JBQ2xDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxFQUFFLENBQUM7d0JBQ2xDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDO3dCQUN2QyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsS0FBSyxDQUFDLENBQUMsQ0FBQzt3QkFDdkMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxHQUFHLEtBQUssQ0FBQyxDQUFDLENBQUM7d0JBQ3ZDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDO3dCQUN2QyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsRUFBRSxDQUFDO3dCQUNsQyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsRUFBRSxDQUFDO29CQUNuQyxDQUFDO3lCQUFNLENBQUM7d0JBQ1Asb0JBQW9CLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQzt3QkFDakMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQzt3QkFDakMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLElBQUksQ0FBQyxDQUFDLENBQUM7d0JBQ3JDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxJQUFJLENBQUMsQ0FBQyxDQUFDO3dCQUNyQyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsSUFBSSxDQUFDLENBQUMsQ0FBQzt3QkFDdEMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxHQUFHLElBQUksQ0FBQyxDQUFDLENBQUM7d0JBRXRDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxFQUFFLENBQUM7d0JBQ2xDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxFQUFFLENBQUM7d0JBQ2xDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDO3dCQUN2QyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsS0FBSyxDQUFDLENBQUMsQ0FBQzt3QkFDdkMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxHQUFHLEtBQUssQ0FBQyxDQUFDLENBQUM7d0JBQ3ZDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDO3dCQUN2QyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsRUFBRSxDQUFDO3dCQUNsQyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsRUFBRSxDQUFDO3dCQUNsQyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsSUFBSSxDQUFDLENBQUMsQ0FBQzt3QkFDdEMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxHQUFHLElBQUksQ0FBQyxDQUFDLENBQUM7d0JBQ3RDLG9CQUFvQixDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsR0FBRyxJQUFJLENBQUMsQ0FBQyxDQUFDO3dCQUN0QyxvQkFBb0IsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDLEdBQUcsSUFBSSxDQUFDLENBQUMsQ0FBQzt3QkFFdEMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxHQUFHLEVBQUUsQ0FBQzt3QkFDbEMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxHQUFHLEVBQUUsQ0FBQzt3QkFDbEMsb0JBQW9CLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxHQUFHLEtBQUssQ0FBQyxD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QztZQUN0QixJQUFJLElBQUksR0FBRyxHQUFHLEdBQUcsR0FBRyxHQUFHLEdBQUcsR0FBRyxDQUFDO1FBQy9CLENBQUM7UUFDRCxJQUFJLElBQUksR0FBRyxDQUFDO1lBQUUsT0FBTztRQUVyQixLQUFLLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxLQUFLLEdBQUcsY0FBYyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsY0FBYyxJQUFJLENBQUMsRUFBRSxDQUFDLEdBQUcsQ0FBQyxFQUFFLENBQUMsSUFBSSxDQUFDLEVBQUUsQ0FBQztZQUNwRixJQUFJLENBQUMsR0FBRyxRQUFRLENBQUMsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxHQUFHLFFBQVEsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLENBQUM7WUFDekMsSUFBSSxLQUFLLEdBQUcsS0FBSyxHQUFHLENBQUMsQ0FBQztZQUN0QixRQUFRLENBQUMsQ0FBQyxDQUFDLEdBQUcsUUFBUSxDQUFDLEtBQUssQ0FBQyxDQUFDO1lBQzlCLFFBQVEsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLEdBQUcsUUFBUSxDQUFDLEtBQUssR0FBRyxDQUFDLENBQUMsQ0FBQztZQUN0QyxRQUFRLENBQUMsS0FBSyxDQUFDLEdBQUcsQ0FBQyxDQUFDO1lBQ3BCLFFBQVEsQ0FBQyxLQUFLLEdBQUcsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDO1FBQ3pCLENBQUM7SUFDRixDQUFDO0NBQ0QiLCJzb3VyY2VzQ29udGVudCI6WyIvKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqXG4gKiBTcGluZSBSdW50aW1lcyBMaWNlbnNlIEFncmVlbWVudFxuICogTGFzdCB1cGRhdGVkIEFwcmlsIDUsIDIwMjUuIFJlcGxhY2VzIGFsbCBwcmlvciB2ZXJzaW9ucy5cbiAqXG4gKiBDb3B5cmlnaHQgKGMpIDIwMTMtMjAyNSwgRXNvdGVyaWMgU29mdHdhcmUgTExDXG4gKlxuICogSW50ZWdyYXRpb24gb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmUgb3Igb3RoZXJ3aXNlIGNyZWF0aW5nXG4gKiBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpcyBwZXJtaXR0ZWQgdW5kZXIgdGhlIHRlcm1zIGFuZFxuICogY29uZGl0aW9ucyBvZiBTZWN0aW9uIDIgb2YgdGhlIFNwaW5lIEVkaXRvciBMaWNlbnNlIEFncmVlbWVudDpcbiAqIGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1lZGl0b3ItbGljZW5zZVxuICpcbiAqIE90aGVyd2lzZSwgaXQgaXMgcGVybWl0dGVkIHRvIGludGVncmF0ZSB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZVxuICogb3Igb3RoZXJ3aXNlIGNyZWF0ZSBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyAoY29sbGVjdGl2ZWx5LFxuICogXCJQcm9kdWN0c1wiKSwgcHJvdmlkZWQgdGhhdCBlYWNoIHVzZXIgb2YgdGhlIFByb2R1Y3RzIG11c3Qgb2J0YWluIHRoZWlyIG93blxuICogU3BpbmUgRWRpdG9yIGxpY2Vuc2UgYW5kIHJlZGlzdHJpYnV0aW9uIG9mIHRoZSBQcm9kdWN0cyBpbiBhbnkgZm9ybSBtdXN0XG4gKiBpbmNsdWRlIHRoaXMgbGljZW5zZSBhbmQgY29weXJpZ2h0IG5vdGljZS5cbiAqXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMgQVJFIFBST1ZJREVEIEJZIEVTT1RFUklDIFNPRlRXQVJFIExMQyBcIkFTIElTXCIgQU5EIEFOWVxuICogRVhQUkVTUyBPUiBJTVBMSUVEIFdBUlJBTlRJRVMsIElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBUSEUgSU1QTElFRFxuICogV0FSUkFOVElFUyBPRiBNRVJDSEFOVEFCSUxJVFkgQU5EIEZJVE5FU1MgRk9SIEEgUEFSVElDVUxBUiBQVVJQT1NFIEFSRVxuICogRElTQ0xBSU1FRC4gSU4gTk8gRVZFTlQgU0hBTEwgRVNPVEVSSUMgU09GVFdBUkUgTExDIEJFIExJQUJMRSBGT1IgQU5ZXG4gKiBESVJFQ1QsIElORElSRUNULCBJTkNJREVOVEFMLCBTUEVDSUFMLCBFWEVNUExBUlksIE9SIENPTlNFUVVFTlRJQUwgREFNQUdFU1xuICogKElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBQUk9DVVJFTUVOVCBPRiBTVUJTVElUVVRFIEdPT0RTIE9SIFNFUlZJQ0VTLFxuICogQlVTSU5FU1MgSU5URVJSVVBUSU9OLCBPUiBMT1NTIE9GIFVTRSwgREFUQSwgT1IgUFJPRklUUykgSE9XRVZFUiBDQVVTRUQgQU5EXG4gKiBPTiBBTlkgVEhFT1JZIE9GIExJQUJJTElUWSwgV0hFVEhFUiBJTiBDT05UUkFDVCwgU1RSSUNUIExJQUJJTElUWSwgT1IgVE9SVFxuICogKElOQ0xVRElORyBORUdMSUdFTkNFIE9SIE9USEVSV0lTRSkgQVJJU0lORyBJTiBBTlkgV0FZIE9VVCBPRiBUSEUgVVNFIE9GXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMsIEVWRU4gSUYgQURWSVNFRCBPRiBUSEUgUE9TU0lCSUxJVFkgT0YgU1VDSCBEQU1BR0UuXG4gKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKiovXG5cbmltcG9ydCB7IENsaXBwaW5nQXR0YWNobWVudCB9IGZyb20gXCIuL2F0dGFjaG1lbnRzL0NsaXBwaW5nQXR0YWNobWVudC5qc1wiO1xuaW1wb3J0IHsgU2xvdCB9IGZyb20gXCIuL1Nsb3QuanNcIjtcbmltcG9ydCB7IFRyaWFuZ3VsYXRvciB9IGZyb20gXCIuL1RyaWFuZ3VsYXRvci5qc1wiO1xuaW1wb3J0IHsgVXRpbHMsIENvbG9yLCBOdW1iZXJBcnJheUxpa2UgfSBmcm9tIFwiLi9VdGlscy5qc1wiO1xuXG5leHBvcnQgY2xhc3MgU2tlbGV0b25DbGlwcGluZyB7XG5cdHByaXZhdGUgdHJpYW5ndWxhdG9yID0gbmV3IFRyaWFuZ3VsYXRvcigpO1xuXHRwcml2YXRlIGNsaXBwaW5nUG9seWdvbiA9IG5ldyBBcnJheTxudW1iZXI+KCk7XG5cdHByaXZhdGUgY2xpcE91dHB1dCA9IG5ldyBBcnJheTxudW1iZXI+KCk7XG5cdGNsaXBwZWRWZXJ0aWNlcyA9IG5ldyBBcnJheTxudW1iZXI+KCk7XG5cdGNsaXBwZWRVVnMgPSBuZXcgQXJyYXk8bnVtYmVyPigpO1xuXHRjbGlwcGVkVHJpYW5nbGVzID0gbmV3IEFycmF5PG51bWJlcj4oKTtcblx0cHJpdmF0ZSBzY3JhdGNoID0gbmV3IEFycmF5PG51bWJlcj4oKTtcblxuXHRwcml2YXRlIGNsaXBBdHRhY2htZW50OiBDbGlwcGluZ0F0dGFjaG1lbnQgfCBudWxsID0gbnVsbDtcblx0cHJpdmF0ZSBjbGlwcGluZ1BvbHlnb25zOiBBcnJheTxBcnJheTxudW1iZXI+PiB8IG51bGwgPSBudWxsO1xuXG5cdGNsaXBTdGFydCAoc2xvdDogU2xvdCwgY2xpcDogQ2xpcHBpbmdBdHRhY2htZW50KTogbnVtYmVyIHtcblx0XHRpZiAodGhpcy5jbGlwQXR0YWNobWVudCkgcmV0dXJuIDA7XG5cdFx0dGhpcy5jbGlwQXR0YWNobWVudCA9IGNsaXA7XG5cblx0XHRsZXQgbiA9IGNsaXAud29ybGRWZXJ0aWNlc0xlbmd0aDtcblx0XHRsZXQgdmVydGljZXMgPSBVdGlscy5zZXRBcnJheVNpemUodGhpcy5jbGlwcGluZ1BvbHlnb24sIG4pO1xuXHRcdGNsaXAuY29tcHV0ZVdvcmxkVmVydGljZXMoc2xvdCwgMCwgbiwgdmVydGljZXMsIDAsIDIpO1xuXHRcdGxldCBjbGlwcGluZ1BvbHlnb24gPSB0aGlzLmNsaXBwaW5nUG9seWdvbjtcblx0XHRTa2VsZXRvbkNsaXBwaW5nLm1ha2VDbG9ja3dpc2UoY2xpcHBpbmdQb2x5Z29uKTtcblx0XHRsZXQgY2xpcHBpbmdQb2x5Z29ucyA9IHRoaXMuY2xpcHBpbmdQb2x5Z29ucyA9IHRoaXMudHJpYW5ndWxhdG9yLmRlY29tcG9zZShjbGlwcGluZ1BvbHlnb24sIHRoaXMudHJpYW5ndWxhdG9yLnRyaWFuZ3VsYXRlKGNsaXBwaW5nUG9seWdvbikpO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gY2xpcHBpbmdQb2x5Z29ucy5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBwb2x5Z29uID0gY2xpcHBpbmdQb2x5Z29uc1tpXTtcblx0XHRcdFNrZWxldG9uQ2xpcHBpbmcubWFrZUNsb2Nrd2lzZShwb2x5Z29uKTtcblx0XHRcdHBvbHlnb24ucHVzaChwb2x5Z29uWzBdKTtcblx0XHRcdHBvbHlnb24ucHVzaChwb2x5Z29uWzFdKTtcblx0XHR9XG5cblx0XHRyZXR1cm4gY2xpcHBpbmdQb2x5Z29ucy5sZW5ndGg7XG5cdH1cblxuXHRjbGlwRW5kV2l0aFNsb3QgKHNsb3Q6IFNsb3QpIHtcblx0XHRpZiAodGhpcy5jbGlwQXR0YWNobWVudCAmJiB0aGlzLmNsaXBBdHRhY2htZW50LmVuZFNsb3QgPT0gc2xvdC5kYXRhKSB0aGlzLmNsaXBFbmQoKTtcblx0fVxuXG5cdGNsaXBFbmQgKCkge1xuXHRcdGlmICghdGhpcy5jbGlwQXR0YWNobWVudCkgcmV0dXJuO1xuXHRcdHRoaXMuY2xpcEF0dGFjaG1lbnQgPSBudWxsO1xuXHRcdHRoaXMuY2xpcHBpbmdQb2x5Z29ucyA9IG51bGw7XG5cdFx0dGhpcy5jbGlwcGVkVmVydGljZXMubGVuZ3RoID0gMDtcblx0XHR0aGlzLmNsaXBwZWRUcmlhbmdsZXMubGVuZ3RoID0gMDtcblx0XHR0aGlzLmNsaXBwaW5nUG9seWdvbi5sZW5ndGggPSAwO1xuXHR9XG5cblx0aXNDbGlwcGluZyAoKTogYm9vbGVhbiB7XG5cdFx0cmV0dXJuIHRoaXMuY2xpcEF0dGFjaG1lbnQgIT0gbnVsbDtcblx0fVxuXG5cdC8qKlxuXHQqIEBkZXByZWNhdGVkIFVzZSBjbGlwVHJpYW5nbGVzIHdpdGhvdXQgdmVydGljZXNMZW5ndGggcGFyYW1ldGVyLiBNYXJrIGZvciByZW1vdmFsIGluIDQuMy5cblx0Ki9cblx0Y2xpcFRyaWFuZ2xlcyAodmVydGljZXM6IE51bWJlckFycmF5TGlrZSwgdmVydGljZXNMZW5ndGg6IG51bWJlciwgdHJpYW5nbGVzOiBOdW1iZXJBcnJheUxpa2UsIHRyaWFuZ2xlc0xlbmd0aDogbnVtYmVyKTogdm9pZDtcblxuXHQvKipcblx0ICogQGRlcHJlY2F0ZWQgVXNlIGNsaXBUcmlhbmdsZXMgd2l0aG91dCB2ZXJ0aWNlc0xlbmd0aCBwYXJhbWV0ZXIuIE1hcmsgZm9yIHJlbW92YWwgaW4gNC4zLlxuXHQgKi9cblx0Y2xpcFRyaWFuZ2xlcyAodmVydGljZXM6IE51bWJlckFycmF5TGlrZSwgdmVydGljZXNMZW5ndGg6IG51bWJlciwgdHJpYW5nbGVzOiBOdW1iZXJBcnJheUxpa2UsIHRyaWFuZ2xlc0xlbmd0aDogbnVtYmVyLCB1dnM6IE51bWJlckFycmF5TGlrZSwgbGlnaHQ6IENvbG9yLCBkYXJrOiBDb2xvciwgdHdvQ29sb3I6IGJvb2xlYW4pOiB2b2lkO1xuXG5cdGNsaXBUcmlhbmdsZXMgKHZlcnRpY2VzOiBOdW1iZXJBcnJheUxpa2UsIHRyaWFuZ2xlczogTnVtYmVyQXJyYXlMaWtlLCB0cmlhbmdsZXNMZW5ndGg6IG51bWJlcik6IHZvaWQ7XG5cdGNsaXBUcmlhbmdsZXMgKHZlcnRpY2VzOiBOdW1iZXJBcnJheUxpa2UsIHRyaWFuZ2xlczogTnVtYmVyQXJyYXlMaWtlLCB0cmlhbmdsZXNMZW5ndGg6IG51bWJlciwgdXZzOiBOdW1iZXJBcnJheUxpa2UsIGxpZ2h0OiBDb2xvciwgZGFyazogQ29sb3IsIHR3b0NvbG9yOiBib29sZWFuKTogdm9pZDtcblx0Y2xpcFRyaWFuZ2xlcyAoXG5cdFx0dmVydGljZXM6IE51bWJlckFycmF5TGlrZSxcblx0XHR2ZXJ0aWNlc0xlbmd0aE9yVHJpYW5nbGVzOiBudW1iZXIgfCBOdW1iZXJBcnJheUxpa2UsXG5cdFx0dHJpYW5nbGVzT3JUcmlhbmdsZXNMZW5ndGg6IE51bWJlckFycmF5TGlrZSB8IG51bWJlcixcblx0XHR0cmlhbmdsZXNMZW5ndGhPclV2cz86IG51bWJlciB8IE51bWJlckFycmF5TGlrZSxcblx0XHR1dnNPckxpZ2h0PzogTnVtYmVyQXJyYXlMaWtlIHwgQ29sb3IsXG5cdFx0bGlnaHRPckRhcms/OiBDb2xvcixcblx0XHRkYXJrT3JUd29Db2xvcj86IENvbG9yIHwgYm9vbGVhbixcblx0XHR0d29Db2xvclBhcmFtPzogYm9vbGVhblxuXHQpOiB2b2lkIHtcblx0XHQvLyBEZXRlcm1pbmUgd2hpY2ggb3ZlcmxvYWQgaXMgYmVpbmcgdXNlZFxuXHRcdGxldCB0cmlhbmdsZXM6IE51bWJlckFycmF5TGlrZTtcblx0XHRsZXQgdHJpYW5nbGVzTGVuZ3RoOiBudW1iZXI7XG5cdFx0bGV0IHV2czogTnVtYmVyQXJyYXlMaWtlIHwgdW5kZWZpbmVkO1xuXHRcdGxldCBsaWdodDogQ29sb3IgfCB1bmRlZmluZWQ7XG5cdFx0bGV0IGRhcms6IENvbG9yIHwgdW5kZWZpbmVkO1xuXHRcdGxldCB0d29Db2xvcjogYm9vbGVhbiB8IHVuZGVmaW5lZDtcblxuXHRcdGlmICh0eXBlb2YgdmVydGljZXNMZW5ndGhPclRyaWFuZ2xlcyA9PT0gJ251bWJlcicpIHtcblx0XHRcdHRyaWFuZ2xlcyA9IHRyaWFuZ2xlc09yVHJpYW5nbGVzTGVuZ3RoIGFzIE51bWJlckFycmF5TGlrZTtcblx0XHRcdHRyaWFuZ2xlc0xlbmd0aCA9IHRyaWFuZ2xlc0xlbmd0aE9yVXZzIGFzIG51bWJlcjtcblx0XHRcdHV2cyA9IHV2c09yTGlnaHQgYXMgTnVtYmVyQXJyYXlMaWtlO1xuXHRcdFx0bGlnaHQgPSBsaWdodE9yRGFyayBhcyBDb2xvciB8IHVuZGVmaW5lZDtcblx0XHRcdGRhcmsgPSBkYXJrT3JUd29Db2xvciBhcyBDb2xvciB8IHVuZGVmaW5lZDtcblx0XHRcdHR3b0NvbG9yID0gdHdvQ29sb3JQYXJhbTtcblx0XHR9IGVsc2Uge1xuXHRcdFx0dHJpYW5nbGVzID0gdmVydGljZXNMZW5ndGhPclRyaWFuZ2xlcztcblx0XHRcdHRyaWFuZ2xlc0xlbmd0aCA9IHRyaWFuZ2xlc09yVHJpYW5nbGVzTGVuZ3RoIGFzIG51bWJlcjtcblx0XHRcdHV2cyA9IHRyaWFuZ2xlc0xlbmd0aE9yVXZzIGFzIE51bWJlckFycmF5TGlrZTtcblx0XHRcdGxpZ2h0ID0gdXZzT3JMaWdodCBhcyBDb2xvciB8IHVuZGVmaW5lZDtcblx0XHRcdGRhcmsgPSBsaWdodE9yRGFyayBhcyBDb2xvciB8IHVuZGVmaW5lZDtcblx0XHRcdHR3b0NvbG9yID0gZGFya09yVHdvQ29sb3IgYXMgYm9vbGVhbjtcblx0XHR9XG5cblx0XHRpZiAodXZzICYmIGxpZ2h0ICYmIGRhcmsgJiYgdHlwZW9mIHR3b0NvbG9yID09PSAnYm9vbGVhbicpXG5cdFx0XHR0aGlzLmNsaXBUcmlhbmdsZXNSZW5kZXIodmVydGljZXMsIHRyaWFuZ2xlcywgdHJpYW5nbGVzTGVuZ3RoLCB1dnMsIGxpZ2h0LCBkYXJrLCB0d29Db2xvcik7XG5cdFx0ZWxzZVxuXHRcdFx0dGhpcy5jbGlwVHJpYW5nbGVzTm9SZW5kZXIodmVydGljZXMsIHRyaWFuZ2xlcywgdHJpYW5nbGVzTGVuZ3RoKTtcblx0fVxuXG5cdHByaXZhdGUgY2xpcFRyaWFuZ2xlc05vUmVuZGVyICh2ZXJ0aWNlczogTnVtYmVyQXJyYXlMaWtlLCB0cmlhbmdsZXM6IE51bWJlckFycmF5TGlrZSwgdHJpYW5nbGVzTGVuZ3RoOiBudW1iZXIpIHtcblxuXHRcdGxldCBjbGlwT3V0cHV0ID0gdGhpcy5jbGlwT3V0cHV0LCBjbGlwcGVkVmVydGljZXMgPSB0aGlzLmNsaXBwZWRWZXJ0aWNlcztcblx0XHRsZXQgY2xpcHBlZFRyaWFuZ2xlcyA9IHRoaXMuY2xpcHBlZFRyaWFuZ2xlcztcblx0XHRsZXQgcG9seWdvbnMgPSB0aGlzLmNsaXBwaW5nUG9seWdvbnMhO1xuXHRcdGxldCBwb2x5Z29uc0NvdW50ID0gcG9seWdvbnMubGVuZ3RoO1xuXG5cdFx0bGV0IGluZGV4ID0gMDtcblx0XHRjbGlwcGVkVmVydGljZXMubGVuZ3RoID0gMDtcblx0XHRjbGlwcGVkVHJpYW5nbGVzLmxlbmd0aCA9IDA7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCB0cmlhbmdsZXNMZW5ndGg7IGkgKz0gMykge1xuXHRcdFx0bGV0IHZlcnRleE9mZnNldCA9IHRyaWFuZ2xlc1tpXSA8PCAxO1xuXHRcdFx0bGV0IHgxID0gdmVydGljZXNbdmVydGV4T2Zmc2V0XSwgeTEgPSB2ZXJ0aWNlc1t2ZXJ0ZXhPZmZzZXQgKyAxXTtcblxuXHRcdFx0dmVydGV4T2Zmc2V0ID0gdHJpYW5nbGVzW2kgKyAxXSA8PCAxO1xuXHRcdFx0bGV0IHgyID0gdmVydGljZXNbdmVydGV4T2Zmc2V0XSwgeTIgPSB2ZXJ0aWNlc1t2ZXJ0ZXhPZmZzZXQgKyAxXTtcblxuXHRcdFx0dmVydGV4T2Zmc2V0ID0gdHJpYW5nbGVzW2kgKyAyXSA8PCAxO1xuXHRcdFx0bGV0IHgzID0gdmVydGljZXNbdmVydGV4T2Zmc2V0XSwgeTMgPSB2ZXJ0aWNlc1t2ZXJ0ZXhPZmZzZXQgKyAxXTtcblxuXHRcdFx0Zm9yIChsZXQgcCA9IDA7IHAgPCBwb2x5Z29uc0NvdW50OyBwKyspIHtcblx0XHRcdFx0bGV0IHMgPSBjbGlwcGVkVmVydGljZXMubGVuZ3RoO1xuXHRcdFx0XHRpZiAodGhpcy5jbGlwKHgxLCB5MSwgeDIsIHkyLCB4MywgeTMsIHBvbHlnb25zW3BdLCBjbGlwT3V0cHV0KSkge1xuXHRcdFx0XHRcdGxldCBjbGlwT3V0cHV0TGVuZ3RoID0gY2xpcE91dHB1dC5sZW5ndGg7XG5cdFx0XHRcdFx0aWYgKGNsaXBPdXRwdXRMZW5ndGggPT0gMCkgY29udGludWU7XG5cblx0XHRcdFx0XHRsZXQgY2xpcE91dHB1dENvdW50ID0gY2xpcE91dHB1dExlbmd0aCA+PiAxO1xuXHRcdFx0XHRcdGxldCBjbGlwT3V0cHV0SXRlbXMgPSB0aGlzLmNsaXBPdXRwdXQ7XG5cdFx0XHRcdFx0bGV0IGNsaXBwZWRWZXJ0aWNlc0l0ZW1zID0gVXRpbHMuc2V0QXJyYXlTaXplKGNsaXBwZWRWZXJ0aWNlcywgcyArIGNsaXBPdXRwdXRDb3VudCAqIDIpO1xuXHRcdFx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCBjbGlwT3V0cHV0TGVuZ3RoOyBpaSArPSAyLCBzICs9IDIpIHtcblx0XHRcdFx0XHRcdGxldCB4ID0gY2xpcE91dHB1dEl0ZW1zW2lpXSwgeSA9IGNsaXBPdXRwdXRJdGVtc1tpaSArIDFdO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbc10gPSB4O1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDFdID0geTtcblx0XHRcdFx0XHR9XG5cblx0XHRcdFx0XHRzID0gY2xpcHBlZFRyaWFuZ2xlcy5sZW5ndGg7XG5cdFx0XHRcdFx0bGV0IGNsaXBwZWRUcmlhbmdsZXNJdGVtcyA9IFV0aWxzLnNldEFycmF5U2l6ZShjbGlwcGVkVHJpYW5nbGVzLCBzICsgMyAqIChjbGlwT3V0cHV0Q291bnQgLSAyKSk7XG5cdFx0XHRcdFx0Y2xpcE91dHB1dENvdW50LS07XG5cdFx0XHRcdFx0Zm9yIChsZXQgaWkgPSAxOyBpaSA8IGNsaXBPdXRwdXRDb3VudDsgaWkrKywgcyArPSAzKSB7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVHJpYW5nbGVzSXRlbXNbc10gPSBpbmRleDtcblx0XHRcdFx0XHRcdGNsaXBwZWRUcmlhbmdsZXNJdGVtc1tzICsgMV0gPSAoaW5kZXggKyBpaSk7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVHJpYW5nbGVzSXRlbXNbcyArIDJdID0gKGluZGV4ICsgaWkgKyAxKTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0aW5kZXggKz0gY2xpcE91dHB1dENvdW50ICsgMTtcblxuXHRcdFx0XHR9IGVsc2Uge1xuXHRcdFx0XHRcdGxldCBjbGlwcGVkVmVydGljZXNJdGVtcyA9IFV0aWxzLnNldEFycmF5U2l6ZShjbGlwcGVkVmVydGljZXMsIHMgKyAzICogMik7XG5cdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbc10gPSB4MTtcblx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMV0gPSB5MTtcblxuXHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyXSA9IHgyO1xuXHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAzXSA9IHkyO1xuXG5cdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDRdID0geDM7XG5cdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDVdID0geTM7XG5cblx0XHRcdFx0XHRzID0gY2xpcHBlZFRyaWFuZ2xlcy5sZW5ndGg7XG5cdFx0XHRcdFx0bGV0IGNsaXBwZWRUcmlhbmdsZXNJdGVtcyA9IFV0aWxzLnNldEFycmF5U2l6ZShjbGlwcGVkVHJpYW5nbGVzLCBzICsgMyk7XG5cdFx0XHRcdFx0Y2xpcHBlZFRyaWFuZ2xlc0l0ZW1zW3NdID0gaW5kZXg7XG5cdFx0XHRcdFx0Y2xpcHBlZFRyaWFuZ2xlc0l0ZW1zW3MgKyAxXSA9IChpbmRleCArIDEpO1xuXHRcdFx0XHRcdGNsaXBwZWRUcmlhbmdsZXNJdGVtc1tzICsgMl0gPSAoaW5kZXggKyAyKTtcblx0XHRcdFx0XHRpbmRleCArPSAzO1xuXHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0fVxuXHR9XG5cblx0cHJpdmF0ZSBjbGlwVHJpYW5nbGVzUmVuZGVyICh2ZXJ0aWNlczogTnVtYmVyQXJyYXlMaWtlLCB0cmlhbmdsZXM6IE51bWJlckFycmF5TGlrZSwgdHJpYW5nbGVzTGVuZ3RoOiBudW1iZXIsIHV2czogTnVtYmVyQXJyYXlMaWtlLFxuXHRcdGxpZ2h0OiBDb2xvciwgZGFyazogQ29sb3IsIHR3b0NvbG9yOiBib29sZWFuKSB7XG5cblx0XHRsZXQgY2xpcE91dHB1dCA9IHRoaXMuY2xpcE91dHB1dCwgY2xpcHBlZFZlcnRpY2VzID0gdGhpcy5jbGlwcGVkVmVydGljZXM7XG5cdFx0bGV0IGNsaXBwZWRUcmlhbmdsZXMgPSB0aGlzLmNsaXBwZWRUcmlhbmdsZXM7XG5cdFx0bGV0IHBvbHlnb25zID0gdGhpcy5jbGlwcGluZ1BvbHlnb25zITtcblx0XHRsZXQgcG9seWdvbnNDb3VudCA9IHBvbHlnb25zLmxlbmd0aDtcblx0XHRsZXQgdmVydGV4U2l6ZSA9IHR3b0NvbG9yID8gMTIgOiA4O1xuXG5cdFx0bGV0IGluZGV4ID0gMDtcblx0XHRjbGlwcGVkVmVydGljZXMubGVuZ3RoID0gMDtcblx0XHRjbGlwcGVkVHJpYW5nbGVzLmxlbmd0aCA9IDA7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCB0cmlhbmdsZXNMZW5ndGg7IGkgKz0gMykge1xuXHRcdFx0bGV0IHZlcnRleE9mZnNldCA9IHRyaWFuZ2xlc1tpXSA8PCAxO1xuXHRcdFx0bGV0IHgxID0gdmVydGljZXNbdmVydGV4T2Zmc2V0XSwgeTEgPSB2ZXJ0aWNlc1t2ZXJ0ZXhPZmZzZXQgKyAxXTtcblx0XHRcdGxldCB1MSA9IHV2c1t2ZXJ0ZXhPZmZzZXRdLCB2MSA9IHV2c1t2ZXJ0ZXhPZmZzZXQgKyAxXTtcblxuXHRcdFx0dmVydGV4T2Zmc2V0ID0gdHJpYW5nbGVzW2kgKyAxXSA8PCAxO1xuXHRcdFx0bGV0IHgyID0gdmVydGljZXNbdmVydGV4T2Zmc2V0XSwgeTIgPSB2ZXJ0aWNlc1t2ZXJ0ZXhPZmZzZXQgKyAxXTtcblx0XHRcdGxldCB1MiA9IHV2c1t2ZXJ0ZXhPZmZzZXRdLCB2MiA9IHV2c1t2ZXJ0ZXhPZmZzZXQgKyAxXTtcblxuXHRcdFx0dmVydGV4T2Zmc2V0ID0gdHJpYW5nbGVzW2kgKyAyXSA8PCAxO1xuXHRcdFx0bGV0IHgzID0gdmVydGljZXNbdmVydGV4T2Zmc2V0XSwgeTMgPSB2ZXJ0aWNlc1t2ZXJ0ZXhPZmZzZXQgKyAxXTtcblx0XHRcdGxldCB1MyA9IHV2c1t2ZXJ0ZXhPZmZzZXRdLCB2MyA9IHV2c1t2ZXJ0ZXhPZmZzZXQgKyAxXTtcblxuXHRcdFx0Zm9yIChsZXQgcCA9IDA7IHAgPCBwb2x5Z29uc0NvdW50OyBwKyspIHtcblx0XHRcdFx0bGV0IHMgPSBjbGlwcGVkVmVydGljZXMubGVuZ3RoO1xuXHRcdFx0XHRpZiAodGhpcy5jbGlwKHgxLCB5MSwgeDIsIHkyLCB4MywgeTMsIHBvbHlnb25zW3BdLCBjbGlwT3V0cHV0KSkge1xuXHRcdFx0XHRcdGxldCBjbGlwT3V0cHV0TGVuZ3RoID0gY2xpcE91dHB1dC5sZW5ndGg7XG5cdFx0XHRcdFx0aWYgKGNsaXBPdXRwdXRMZW5ndGggPT0gMCkgY29udGludWU7XG5cdFx0XHRcdFx0bGV0IGQwID0geTIgLSB5MywgZDEgPSB4MyAtIHgyLCBkMiA9IHgxIC0geDMsIGQ0ID0geTMgLSB5MTtcblx0XHRcdFx0XHRsZXQgZCA9IDEgLyAoZDAgKiBkMiArIGQxICogKHkxIC0geTMpKTtcblxuXHRcdFx0XHRcdGxldCBjbGlwT3V0cHV0Q291bnQgPSBjbGlwT3V0cHV0TGVuZ3RoID4+IDE7XG5cdFx0XHRcdFx0bGV0IGNsaXBPdXRwdXRJdGVtcyA9IHRoaXMuY2xpcE91dHB1dDtcblx0XHRcdFx0XHRsZXQgY2xpcHBlZFZlcnRpY2VzSXRlbXMgPSBVdGlscy5zZXRBcnJheVNpemUoY2xpcHBlZFZlcnRpY2VzLCBzICsgY2xpcE91dHB1dENvdW50ICogdmVydGV4U2l6ZSk7XG5cdFx0XHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IGNsaXBPdXRwdXRMZW5ndGg7IGlpICs9IDIsIHMgKz0gdmVydGV4U2l6ZSkge1xuXHRcdFx0XHRcdFx0bGV0IHggPSBjbGlwT3V0cHV0SXRlbXNbaWldLCB5ID0gY2xpcE91dHB1dEl0ZW1zW2lpICsgMV07XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzXSA9IHg7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMV0gPSB5O1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDJdID0gbGlnaHQucjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAzXSA9IGxpZ2h0Lmc7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgNF0gPSBsaWdodC5iO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDVdID0gbGlnaHQuYTtcblx0XHRcdFx0XHRcdGxldCBjMCA9IHggLSB4MywgYzEgPSB5IC0geTM7XG5cdFx0XHRcdFx0XHRsZXQgYSA9IChkMCAqIGMwICsgZDEgKiBjMSkgKiBkO1xuXHRcdFx0XHRcdFx0bGV0IGIgPSAoZDQgKiBjMCArIGQyICogYzEpICogZDtcblx0XHRcdFx0XHRcdGxldCBjID0gMSAtIGEgLSBiO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDZdID0gdTEgKiBhICsgdTIgKiBiICsgdTMgKiBjO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDddID0gdjEgKiBhICsgdjIgKiBiICsgdjMgKiBjO1xuXHRcdFx0XHRcdFx0aWYgKHR3b0NvbG9yKSB7XG5cdFx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyA4XSA9IGRhcmsucjtcblx0XHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDldID0gZGFyay5nO1xuXHRcdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTBdID0gZGFyay5iO1xuXHRcdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTFdID0gZGFyay5hO1xuXHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdH1cblxuXHRcdFx0XHRcdHMgPSBjbGlwcGVkVHJpYW5nbGVzLmxlbmd0aDtcblx0XHRcdFx0XHRsZXQgY2xpcHBlZFRyaWFuZ2xlc0l0ZW1zID0gVXRpbHMuc2V0QXJyYXlTaXplKGNsaXBwZWRUcmlhbmdsZXMsIHMgKyAzICogKGNsaXBPdXRwdXRDb3VudCAtIDIpKTtcblx0XHRcdFx0XHRjbGlwT3V0cHV0Q291bnQtLTtcblx0XHRcdFx0XHRmb3IgKGxldCBpaSA9IDE7IGlpIDwgY2xpcE91dHB1dENvdW50OyBpaSsrLCBzICs9IDMpIHtcblx0XHRcdFx0XHRcdGNsaXBwZWRUcmlhbmdsZXNJdGVtc1tzXSA9IGluZGV4O1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFRyaWFuZ2xlc0l0ZW1zW3MgKyAxXSA9IChpbmRleCArIGlpKTtcblx0XHRcdFx0XHRcdGNsaXBwZWRUcmlhbmdsZXNJdGVtc1tzICsgMl0gPSAoaW5kZXggKyBpaSArIDEpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0XHRpbmRleCArPSBjbGlwT3V0cHV0Q291bnQgKyAxO1xuXG5cdFx0XHRcdH0gZWxzZSB7XG5cdFx0XHRcdFx0bGV0IGNsaXBwZWRWZXJ0aWNlc0l0ZW1zID0gVXRpbHMuc2V0QXJyYXlTaXplKGNsaXBwZWRWZXJ0aWNlcywgcyArIDMgKiB2ZXJ0ZXhTaXplKTtcblx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzXSA9IHgxO1xuXHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAxXSA9IHkxO1xuXHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyXSA9IGxpZ2h0LnI7XG5cdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDNdID0gbGlnaHQuZztcblx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgNF0gPSBsaWdodC5iO1xuXHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyA1XSA9IGxpZ2h0LmE7XG5cdFx0XHRcdFx0aWYgKCF0d29Db2xvcikge1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDZdID0gdTE7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgN10gPSB2MTtcblxuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDhdID0geDI7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgOV0gPSB5Mjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAxMF0gPSBsaWdodC5yO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDExXSA9IGxpZ2h0Lmc7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTJdID0gbGlnaHQuYjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAxM10gPSBsaWdodC5hO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDE0XSA9IHUyO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDE1XSA9IHYyO1xuXG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTZdID0geDM7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTddID0geTM7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMThdID0gbGlnaHQucjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAxOV0gPSBsaWdodC5nO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDIwXSA9IGxpZ2h0LmI7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMjFdID0gbGlnaHQuYTtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyMl0gPSB1Mztcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyM10gPSB2Mztcblx0XHRcdFx0XHR9IGVsc2Uge1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDZdID0gdTE7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgN10gPSB2MTtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyA4XSA9IGRhcmsucjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyA5XSA9IGRhcmsuZztcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAxMF0gPSBkYXJrLmI7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTFdID0gZGFyay5hO1xuXG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTJdID0geDI7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTNdID0geTI7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTRdID0gbGlnaHQucjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAxNV0gPSBsaWdodC5nO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDE2XSA9IGxpZ2h0LmI7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMTddID0gbGlnaHQuYTtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAxOF0gPSB1Mjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAxOV0gPSB2Mjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyMF0gPSBkYXJrLnI7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMjFdID0gZGFyay5nO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDIyXSA9IGRhcmsuYjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyM10gPSBkYXJrLmE7XG5cblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyNF0gPSB4Mztcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyNV0gPSB5Mztcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyNl0gPSBsaWdodC5yO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDI3XSA9IGxpZ2h0Lmc7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMjhdID0gbGlnaHQuYjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAyOV0gPSBsaWdodC5hO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDMwXSA9IHUzO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDMxXSA9IHYzO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDMyXSA9IGRhcmsucjtcblx0XHRcdFx0XHRcdGNsaXBwZWRWZXJ0aWNlc0l0ZW1zW3MgKyAzM10gPSBkYXJrLmc7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMzRdID0gZGFyay5iO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDM1XSA9IGRhcmsuYTtcblx0XHRcdFx0XHR9XG5cblx0XHRcdFx0XHRzID0gY2xpcHBlZFRyaWFuZ2xlcy5sZW5ndGg7XG5cdFx0XHRcdFx0bGV0IGNsaXBwZWRUcmlhbmdsZXNJdGVtcyA9IFV0aWxzLnNldEFycmF5U2l6ZShjbGlwcGVkVHJpYW5nbGVzLCBzICsgMyk7XG5cdFx0XHRcdFx0Y2xpcHBlZFRyaWFuZ2xlc0l0ZW1zW3NdID0gaW5kZXg7XG5cdFx0XHRcdFx0Y2xpcHBlZFRyaWFuZ2xlc0l0ZW1zW3MgKyAxXSA9IChpbmRleCArIDEpO1xuXHRcdFx0XHRcdGNsaXBwZWRUcmlhbmdsZXNJdGVtc1tzICsgMl0gPSAoaW5kZXggKyAyKTtcblx0XHRcdFx0XHRpbmRleCArPSAzO1xuXHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0fVxuXHR9XG5cblx0cHVibGljIGNsaXBUcmlhbmdsZXNVbnBhY2tlZCAodmVydGljZXM6IE51bWJlckFycmF5TGlrZSwgdHJpYW5nbGVzOiBOdW1iZXJBcnJheUxpa2UsIHRyaWFuZ2xlc0xlbmd0aDogbnVtYmVyLCB1dnM6IE51bWJlckFycmF5TGlrZSkge1xuXHRcdGxldCBjbGlwT3V0cHV0ID0gdGhpcy5jbGlwT3V0cHV0LCBjbGlwcGVkVmVydGljZXMgPSB0aGlzLmNsaXBwZWRWZXJ0aWNlcywgY2xpcHBlZFVWcyA9IHRoaXMuY2xpcHBlZFVWcztcblx0XHRsZXQgY2xpcHBlZFRyaWFuZ2xlcyA9IHRoaXMuY2xpcHBlZFRyaWFuZ2xlcztcblx0XHRsZXQgcG9seWdvbnMgPSB0aGlzLmNsaXBwaW5nUG9seWdvbnMhO1xuXHRcdGxldCBwb2x5Z29uc0NvdW50ID0gcG9seWdvbnMubGVuZ3RoO1xuXG5cdFx0bGV0IGluZGV4ID0gMDtcblx0XHRjbGlwcGVkVmVydGljZXMubGVuZ3RoID0gMDtcblx0XHRjbGlwcGVkVVZzLmxlbmd0aCA9IDA7XG5cdFx0Y2xpcHBlZFRyaWFuZ2xlcy5sZW5ndGggPSAwO1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgdHJpYW5nbGVzTGVuZ3RoOyBpICs9IDMpIHtcblx0XHRcdGxldCB2ZXJ0ZXhPZmZzZXQgPSB0cmlhbmdsZXNbaV0gPDwgMTtcblx0XHRcdGxldCB4MSA9IHZlcnRpY2VzW3ZlcnRleE9mZnNldF0sIHkxID0gdmVydGljZXNbdmVydGV4T2Zmc2V0ICsgMV07XG5cdFx0XHRsZXQgdTEgPSB1dnNbdmVydGV4T2Zmc2V0XSwgdjEgPSB1dnNbdmVydGV4T2Zmc2V0ICsgMV07XG5cblx0XHRcdHZlcnRleE9mZnNldCA9IHRyaWFuZ2xlc1tpICsgMV0gPDwgMTtcblx0XHRcdGxldCB4MiA9IHZlcnRpY2VzW3ZlcnRleE9mZnNldF0sIHkyID0gdmVydGljZXNbdmVydGV4T2Zmc2V0ICsgMV07XG5cdFx0XHRsZXQgdTIgPSB1dnNbdmVydGV4T2Zmc2V0XSwgdjIgPSB1dnNbdmVydGV4T2Zmc2V0ICsgMV07XG5cblx0XHRcdHZlcnRleE9mZnNldCA9IHRyaWFuZ2xlc1tpICsgMl0gPDwgMTtcblx0XHRcdGxldCB4MyA9IHZlcnRpY2VzW3ZlcnRleE9mZnNldF0sIHkzID0gdmVydGljZXNbdmVydGV4T2Zmc2V0ICsgMV07XG5cdFx0XHRsZXQgdTMgPSB1dnNbdmVydGV4T2Zmc2V0XSwgdjMgPSB1dnNbdmVydGV4T2Zmc2V0ICsgMV07XG5cblx0XHRcdGZvciAobGV0IHAgPSAwOyBwIDwgcG9seWdvbnNDb3VudDsgcCsrKSB7XG5cdFx0XHRcdGxldCBzID0gY2xpcHBlZFZlcnRpY2VzLmxlbmd0aDtcblx0XHRcdFx0aWYgKHRoaXMuY2xpcCh4MSwgeTEsIHgyLCB5MiwgeDMsIHkzLCBwb2x5Z29uc1twXSwgY2xpcE91dHB1dCkpIHtcblx0XHRcdFx0XHRsZXQgY2xpcE91dHB1dExlbmd0aCA9IGNsaXBPdXRwdXQubGVuZ3RoO1xuXHRcdFx0XHRcdGlmIChjbGlwT3V0cHV0TGVuZ3RoID09IDApIGNvbnRpbnVlO1xuXHRcdFx0XHRcdGxldCBkMCA9IHkyIC0geTMsIGQxID0geDMgLSB4MiwgZDIgPSB4MSAtIHgzLCBkNCA9IHkzIC0geTE7XG5cdFx0XHRcdFx0bGV0IGQgPSAxIC8gKGQwICogZDIgKyBkMSAqICh5MSAtIHkzKSk7XG5cblx0XHRcdFx0XHRsZXQgY2xpcE91dHB1dENvdW50ID0gY2xpcE91dHB1dExlbmd0aCA+PiAxO1xuXHRcdFx0XHRcdGxldCBjbGlwT3V0cHV0SXRlbXMgPSB0aGlzLmNsaXBPdXRwdXQ7XG5cdFx0XHRcdFx0bGV0IGNsaXBwZWRWZXJ0aWNlc0l0ZW1zID0gVXRpbHMuc2V0QXJyYXlTaXplKGNsaXBwZWRWZXJ0aWNlcywgcyArIGNsaXBPdXRwdXRDb3VudCAqIDIpO1xuXHRcdFx0XHRcdGxldCBjbGlwcGVkVVZzSXRlbXMgPSBVdGlscy5zZXRBcnJheVNpemUoY2xpcHBlZFVWcywgcyArIGNsaXBPdXRwdXRDb3VudCAqIDIpO1xuXHRcdFx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCBjbGlwT3V0cHV0TGVuZ3RoOyBpaSArPSAyLCBzICs9IDIpIHtcblx0XHRcdFx0XHRcdGxldCB4ID0gY2xpcE91dHB1dEl0ZW1zW2lpXSwgeSA9IGNsaXBPdXRwdXRJdGVtc1tpaSArIDFdO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbc10gPSB4O1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbcyArIDFdID0geTtcblx0XHRcdFx0XHRcdGxldCBjMCA9IHggLSB4MywgYzEgPSB5IC0geTM7XG5cdFx0XHRcdFx0XHRsZXQgYSA9IChkMCAqIGMwICsgZDEgKiBjMSkgKiBkO1xuXHRcdFx0XHRcdFx0bGV0IGIgPSAoZDQgKiBjMCArIGQyICogYzEpICogZDtcblx0XHRcdFx0XHRcdGxldCBjID0gMSAtIGEgLSBiO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFVWc0l0ZW1zW3NdID0gdTEgKiBhICsgdTIgKiBiICsgdTMgKiBjO1xuXHRcdFx0XHRcdFx0Y2xpcHBlZFVWc0l0ZW1zW3MgKyAxXSA9IHYxICogYSArIHYyICogYiArIHYzICogYztcblx0XHRcdFx0XHR9XG5cblx0XHRcdFx0XHRzID0gY2xpcHBlZFRyaWFuZ2xlcy5sZW5ndGg7XG5cdFx0XHRcdFx0bGV0IGNsaXBwZWRUcmlhbmdsZXNJdGVtcyA9IFV0aWxzLnNldEFycmF5U2l6ZShjbGlwcGVkVHJpYW5nbGVzLCBzICsgMyAqIChjbGlwT3V0cHV0Q291bnQgLSAyKSk7XG5cdFx0XHRcdFx0Y2xpcE91dHB1dENvdW50LS07XG5cdFx0XHRcdFx0Zm9yIChsZXQgaWkgPSAxOyBpaSA8IGNsaXBPdXRwdXRDb3VudDsgaWkrKywgcyArPSAzKSB7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVHJpYW5nbGVzSXRlbXNbc10gPSBpbmRleDtcblx0XHRcdFx0XHRcdGNsaXBwZWRUcmlhbmdsZXNJdGVtc1tzICsgMV0gPSAoaW5kZXggKyBpaSk7XG5cdFx0XHRcdFx0XHRjbGlwcGVkVHJpYW5nbGVzSXRlbXNbcyArIDJdID0gKGluZGV4ICsgaWkgKyAxKTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0aW5kZXggKz0gY2xpcE91dHB1dENvdW50ICsgMTtcblxuXHRcdFx0XHR9IGVsc2Uge1xuXHRcdFx0XHRcdGxldCBjbGlwcGVkVmVydGljZXNJdGVtcyA9IFV0aWxzLnNldEFycmF5U2l6ZShjbGlwcGVkVmVydGljZXMsIHMgKyAzICogMik7XG5cdFx0XHRcdFx0Y2xpcHBlZFZlcnRpY2VzSXRlbXNbc10gPSB4MTtcblx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMV0gPSB5MTtcblx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgMl0gPSB4Mjtcblx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgM10gPSB5Mjtcblx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgNF0gPSB4Mztcblx0XHRcdFx0XHRjbGlwcGVkVmVydGljZXNJdGVtc1tzICsgNV0gPSB5MztcblxuXHRcdFx0XHRcdGxldCBjbGlwcGVkVVZTSXRlbXMgPSBVdGlscy5zZXRBcnJheVNpemUoY2xpcHBlZFVWcywgcyArIDMgKiAyKTtcblx0XHRcdFx0XHRjbGlwcGVkVVZTSXRlbXNbc10gPSB1MTtcblx0XHRcdFx0XHRjbGlwcGVkVVZTSXRlbXNbcyArIDFdID0gdjE7XG5cdFx0XHRcdFx0Y2xpcHBlZFVWU0l0ZW1zW3MgKyAyXSA9IHUyO1xuXHRcdFx0XHRcdGNsaXBwZWRVVlNJdGVtc1tzICsgM10gPSB2Mjtcblx0XHRcdFx0XHRjbGlwcGVkVVZTSXRlbXNbcyArIDRdID0gdTM7XG5cdFx0XHRcdFx0Y2xpcHBlZFVWU0l0ZW1zW3MgKyA1XSA9IHYzO1xuXG5cdFx0XHRcdFx0cyA9IGNsaXBwZWRUcmlhbmdsZXMubGVuZ3RoO1xuXHRcdFx0XHRcdGxldCBjbGlwcGVkVHJpYW5nbGVzSXRlbXMgPSBVdGlscy5zZXRBcnJheVNpemUoY2xpcHBlZFRyaWFuZ2xlcywgcyArIDMpO1xuXHRcdFx0XHRcdGNsaXBwZWRUcmlhbmdsZXNJdGVtc1tzXSA9IGluZGV4O1xuXHRcdFx0XHRcdGNsaXBwZWRUcmlhbmdsZXNJdGVtc1tzICsgMV0gPSAoaW5kZXggKyAxKTtcblx0XHRcdFx0XHRjbGlwcGVkVHJpYW5nbGVzSXRlbXNbcyArIDJdID0gKGluZGV4ICsgMik7XG5cdFx0XHRcdFx0aW5kZXggKz0gMztcblx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0fVxuXHRcdFx0fVxuXHRcdH1cblx0fVxuXG5cdC8qKiBDbGlwcyB0aGUgaW5wdXQgdHJpYW5nbGUgYWdhaW5zdCB0aGUgY29udmV4LCBjbG9ja3dpc2UgY2xpcHBpbmcgYXJlYS4gSWYgdGhlIHRyaWFuZ2xlIGxpZXMgZW50aXJlbHkgd2l0aGluIHRoZSBjbGlwcGluZ1xuXHQgKiBhcmVhLCBmYWxzZSBpcyByZXR1cm5lZC4gVGhlIGNsaXBwaW5nIGFyZWEgbXVzdCBkdXBsaWNhdGUgdGhlIGZpcnN0IHZlcnRleCBhdCB0aGUgZW5kIG9mIHRoZSB2ZXJ0aWNlcyBsaXN0LiAqL1xuXHRjbGlwICh4MTogbnVtYmVyLCB5MTogbnVtYmVyLCB4MjogbnVtYmVyLCB5MjogbnVtYmVyLCB4MzogbnVtYmVyLCB5MzogbnVtYmVyLCBjbGlwcGluZ0FyZWE6IEFycmF5PG51bWJlcj4sIG91dHB1dDogQXJyYXk8bnVtYmVyPikge1xuXHRcdGxldCBvcmlnaW5hbE91dHB1dCA9IG91dHB1dDtcblx0XHRsZXQgY2xpcHBlZCA9IGZhbHNlO1xuXG5cdFx0Ly8gQXZvaWQgY29weSBhdCB0aGUgZW5kLlxuXHRcdGxldCBpbnB1dDogQXJyYXk8bnVtYmVyPjtcblx0XHRpZiAoY2xpcHBpbmdBcmVhLmxlbmd0aCAlIDQgPj0gMikge1xuXHRcdFx0aW5wdXQgPSBvdXRwdXQ7XG5cdFx0XHRvdXRwdXQgPSB0aGlzLnNjcmF0Y2g7XG5cdFx0fSBlbHNlXG5cdFx0XHRpbnB1dCA9IHRoaXMuc2NyYXRjaDtcblxuXHRcdGlucHV0Lmxlbmd0aCA9IDA7XG5cdFx0aW5wdXQucHVzaCh4MSk7XG5cdFx0aW5wdXQucHVzaCh5MSk7XG5cdFx0aW5wdXQucHVzaCh4Mik7XG5cdFx0aW5wdXQucHVzaCh5Mik7XG5cdFx0aW5wdXQucHVzaCh4Myk7XG5cdFx0aW5wdXQucHVzaCh5Myk7XG5cdFx0aW5wdXQucHVzaCh4MSk7XG5cdFx0aW5wdXQucHVzaCh5MSk7XG5cdFx0b3V0cHV0Lmxlbmd0aCA9IDA7XG5cblx0XHRsZXQgY2xpcHBpbmdWZXJ0aWNlc0xhc3QgPSBjbGlwcGluZ0FyZWEubGVuZ3RoIC0gNDtcblx0XHRsZXQgY2xpcHBpbmdWZXJ0aWNlcyA9IGNsaXBwaW5nQXJlYTtcblx0XHRmb3IgKGxldCBpID0gMDsgOyBpICs9IDIpIHtcblx0XHRcdGxldCBlZGdlWCA9IGNsaXBwaW5nVmVydGljZXNbaV0sIGVkZ2VZID0gY2xpcHBpbmdWZXJ0aWNlc1tpICsgMV07XG5cdFx0XHRsZXQgZXggPSBlZGdlWCAtIGNsaXBwaW5nVmVydGljZXNbaSArIDJdLCBleSA9IGVkZ2VZIC0gY2xpcHBpbmdWZXJ0aWNlc1tpICsgM107XG5cblx0XHRcdGxldCBvdXRwdXRTdGFydCA9IG91dHB1dC5sZW5ndGg7XG5cdFx0XHRsZXQgaW5wdXRWZXJ0aWNlcyA9IGlucHV0O1xuXHRcdFx0Zm9yIChsZXQgaWkgPSAwLCBubiA9IGlucHV0Lmxlbmd0aCAtIDI7IGlpIDwgbm47KSB7XG5cdFx0XHRcdGxldCBpbnB1dFggPSBpbnB1dFZlcnRpY2VzW2lpXSwgaW5wdXRZID0gaW5wdXRWZXJ0aWNlc1tpaSArIDFdO1xuXHRcdFx0XHRpaSArPSAyO1xuXHRcdFx0XHRsZXQgaW5wdXRYMiA9IGlucHV0VmVydGljZXNbaWldLCBpbnB1dFkyID0gaW5wdXRWZXJ0aWNlc1tpaSArIDFdO1xuXHRcdFx0XHRsZXQgczIgPSBleSAqIChlZGdlWCAtIGlucHV0WDIpID4gZXggKiAoZWRnZVkgLSBpbnB1dFkyKTtcblx0XHRcdFx0bGV0IHMxID0gZXkgKiAoZWRnZVggLSBpbnB1dFgpIC0gZXggKiAoZWRnZVkgLSBpbnB1dFkpO1xuXHRcdFx0XHRpZiAoczEgPiAwKSB7XG5cdFx0XHRcdFx0aWYgKHMyKSB7IC8vIHYxIGluc2lkZSwgdjIgaW5zaWRlXG5cdFx0XHRcdFx0XHRvdXRwdXQucHVzaChpbnB1dFgyKTtcblx0XHRcdFx0XHRcdG91dHB1dC5wdXNoKGlucHV0WTIpO1xuXHRcdFx0XHRcdFx0Y29udGludWU7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHRcdC8vIHYxIGluc2lkZSwgdjIgb3V0c2lkZVxuXHRcdFx0XHRcdGxldCBpeCA9IGlucHV0WDIgLSBpbnB1dFgsIGl5ID0gaW5wdXRZMiAtIGlucHV0WSwgdCA9IHMxIC8gKGl4ICogZXkgLSBpeSAqIGV4KTtcblx0XHRcdFx0XHRpZiAodCA+PSAwICYmIHQgPD0gMSkge1xuXHRcdFx0XHRcdFx0b3V0cHV0LnB1c2goaW5wdXRYICsgaXggKiB0KTtcblx0XHRcdFx0XHRcdG91dHB1dC5wdXNoKGlucHV0WSArIGl5ICogdCk7XG5cdFx0XHRcdFx0fSBlbHNlIHtcblx0XHRcdFx0XHRcdG91dHB1dC5wdXNoKGlucHV0WDIpO1xuXHRcdFx0XHRcdFx0b3V0cHV0LnB1c2goaW5wdXRZMik7XG5cdFx0XHRcdFx0XHRjb250aW51ZTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdH0gZWxzZSBpZiAoczIpIHsgLy8gdjEgb3V0c2lkZSwgdjIgaW5zaWRlXG5cdFx0XHRcdFx0bGV0IGl4ID0gaW5wdXRYMiAtIGlucHV0WCwgaXkgPSBpbnB1dFkyIC0gaW5wdXRZLCB0ID0gczEgLyAoaXggKiBleSAtIGl5ICogZXgpO1xuXHRcdFx0XHRcdGlmICh0ID49IDAgJiYgdCA8PSAxKSB7XG5cdFx0XHRcdFx0XHRvdXRwdXQucHVzaChpbnB1dFggKyBpeCAqIHQpO1xuXHRcdFx0XHRcdFx0b3V0cHV0LnB1c2goaW5wdXRZICsgaXkgKiB0KTtcblx0XHRcdFx0XHRcdG91dHB1dC5wdXNoKGlucHV0WDIpO1xuXHRcdFx0XHRcdFx0b3V0cHV0LnB1c2goaW5wdXRZMik7XG5cdFx0XHRcdFx0fSBlbHNlIHtcblx0XHRcdFx0XHRcdG91dHB1dC5wdXNoKGlucHV0WDIpO1xuXHRcdFx0XHRcdFx0b3V0cHV0LnB1c2goaW5wdXRZMik7XG5cdFx0XHRcdFx0XHRjb250aW51ZTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdH1cblx0XHRcdFx0Y2xpcHBlZCA9IHRydWU7XG5cdFx0XHR9XG5cblx0XHRcdGlmIChvdXRwdXRTdGFydCA9PSBvdXRwdXQubGVuZ3RoKSB7IC8vIEFsbCBlZGdlcyBvdXRzaWRlLlxuXHRcdFx0XHRvcmlnaW5hbE91dHB1dC5sZW5ndGggPSAwO1xuXHRcdFx0XHRyZXR1cm4gdHJ1ZTtcblx0XHRcdH1cblxuXHRcdFx0b3V0cHV0LnB1c2gob3V0cHV0WzBdKTtcblx0XHRcdG91dHB1dC5wdXNoKG91dHB1dFsxXSk7XG5cblx0XHRcdGlmIChpID09IGNsaXBwaW5nVmVydGljZXNMYXN0KSBicmVhaztcblx0XHRcdGxldCB0ZW1wID0gb3V0cHV0O1xuXHRcdFx0b3V0cHV0ID0gaW5wdXQ7XG5cdFx0XHRvdXRwdXQubGVuZ3RoID0gMDtcblx0XHRcdGlucHV0ID0gdGVtcDtcblx0XHR9XG5cblx0XHRpZiAob3JpZ2luYWxPdXRwdXQgIT0gb3V0cHV0KSB7XG5cdFx0XHRvcmlnaW5hbE91dHB1dC5sZW5ndGggPSAwO1xuXHRcdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBvdXRwdXQubGVuZ3RoIC0gMjsgaSA8IG47IGkrKylcblx0XHRcdFx0b3JpZ2luYWxPdXRwdXRbaV0gPSBvdXRwdXRbaV07XG5cdFx0fSBlbHNlXG5cdFx0XHRvcmlnaW5hbE91dHB1dC5sZW5ndGggPSBvcmlnaW5hbE91dHB1dC5sZW5ndGggLSAyO1xuXG5cdFx0cmV0dXJuIGNsaXBwZWQ7XG5cdH1cblxuXHRwdWJsaWMgc3RhdGljIG1ha2VDbG9ja3dpc2UgKHBvbHlnb246IE51bWJlckFycmF5TGlrZSkge1xuXHRcdGxldCB2ZXJ0aWNlcyA9IHBvbHlnb247XG5cdFx0bGV0IHZlcnRpY2VzbGVuZ3RoID0gcG9seWdvbi5sZW5ndGg7XG5cblx0XHRsZXQgYXJlYSA9IHZlcnRpY2VzW3ZlcnRpY2VzbGVuZ3RoIC0gMl0gKiB2ZXJ0aWNlc1sxXSAtIHZlcnRpY2VzWzBdICogdmVydGljZXNbdmVydGljZXNsZW5ndGggLSAxXSwgcDF4ID0gMCwgcDF5ID0gMCwgcDJ4ID0gMCwgcDJ5ID0gMDtcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IHZlcnRpY2VzbGVuZ3RoIC0gMzsgaSA8IG47IGkgKz0gMikge1xuXHRcdFx0cDF4ID0gdmVydGljZXNbaV07XG5cdFx0XHRwMXkgPSB2ZXJ0aWNlc1tpICsgMV07XG5cdFx0XHRwMnggPSB2ZXJ0aWNlc1tpICsgMl07XG5cdFx0XHRwMnkgPSB2ZXJ0aWNlc1tpICsgM107XG5cdFx0XHRhcmVhICs9IHAxeCAqIHAyeSAtIHAyeCAqIHAxeTtcblx0XHR9XG5cdFx0aWYgKGFyZWEgPCAwKSByZXR1cm47XG5cblx0XHRmb3IgKGxldCBpID0gMCwgbGFzdFggPSB2ZXJ0aWNlc2xlbmd0aCAtIDIsIG4gPSB2ZXJ0aWNlc2xlbmd0aCA+PiAxOyBpIDwgbjsgaSArPSAyKSB7XG5cdFx0XHRsZXQgeCA9IHZlcnRpY2VzW2ldLCB5ID0gdmVydGljZXNbaSArIDFdO1xuXHRcdFx0bGV0IG90aGVyID0gbGFzdFggLSBpO1xuXHRcdFx0dmVydGljZXNbaV0gPSB2ZXJ0aWNlc1tvdGhlcl07XG5cdFx0XHR2ZXJ0aWNlc1tpICsgMV0gPSB2ZXJ0aWNlc1tvdGhlciArIDFdO1xuXHRcdFx0dmVydGljZXNbb3RoZXJdID0geDtcblx0XHRcdHZlcnRpY2VzW290aGVyICsgMV0gPSB5O1xuXHRcdH1cblx0fVxufVxuIl19