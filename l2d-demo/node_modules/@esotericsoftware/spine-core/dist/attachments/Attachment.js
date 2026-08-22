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
import { Utils } from "../Utils.js";
/** The base class for all attachments. */
export class Attachment {
    name;
    constructor(name) {
        if (!name)
            throw new Error("name cannot be null.");
        this.name = name;
    }
}
/** Base class for an attachment with vertices that are transformed by one or more bones and can be deformed by a slot's
 * {@link Slot#deform}. */
export class VertexAttachment extends Attachment {
    static nextID = 0;
    /** The unique ID for this attachment. */
    id = VertexAttachment.nextID++;
    /** The bones which affect the {@link #getVertices()}. The array entries are, for each vertex, the number of bones affecting
     * the vertex followed by that many bone indices, which is the index of the bone in {@link Skeleton#bones}. Will be null
     * if this attachment has no weights. */
    bones = null;
    /** The vertex positions in the bone's coordinate system. For a non-weighted attachment, the values are `x,y`
     * entries for each vertex. For a weighted attachment, the values are `x,y,weight` entries for each bone affecting
     * each vertex. */
    vertices = [];
    /** The maximum number of world vertex values that can be output by
     * {@link #computeWorldVertices()} using the `count` parameter. */
    worldVerticesLength = 0;
    /** Timelines for the timeline attachment are also applied to this attachment.
     * May be null if no attachment-specific timelines should be applied. */
    timelineAttachment = this;
    constructor(name) {
        super(name);
    }
    /** Transforms the attachment's local {@link #vertices} to world coordinates. If the slot's {@link Slot#deform} is
     * not empty, it is used to deform the vertices.
     *
     * See [World transforms](http://esotericsoftware.com/spine-runtime-skeletons#World-transforms) in the Spine
     * Runtimes Guide.
     * @param start The index of the first {@link #vertices} value to transform. Each vertex has 2 values, x and y.
     * @param count The number of world vertex values to output. Must be <= {@link #worldVerticesLength} - `start`.
     * @param worldVertices The output world vertices. Must have a length >= `offset` + `count` *
     *           `stride` / 2.
     * @param offset The `worldVertices` index to begin writing values.
     * @param stride The number of `worldVertices` entries between the value pairs written. */
    computeWorldVertices(slot, start, count, worldVertices, offset, stride) {
        count = offset + (count >> 1) * stride;
        let skeleton = slot.bone.skeleton;
        let deformArray = slot.deform;
        let vertices = this.vertices;
        let bones = this.bones;
        if (!bones) {
            if (deformArray.length > 0)
                vertices = deformArray;
            let bone = slot.bone;
            let x = bone.worldX;
            let y = bone.worldY;
            let a = bone.a, b = bone.b, c = bone.c, d = bone.d;
            for (let v = start, w = offset; w < count; v += 2, w += stride) {
                let vx = vertices[v], vy = vertices[v + 1];
                worldVertices[w] = vx * a + vy * b + x;
                worldVertices[w + 1] = vx * c + vy * d + y;
            }
            return;
        }
        let v = 0, skip = 0;
        for (let i = 0; i < start; i += 2) {
            let n = bones[v];
            v += n + 1;
            skip += n;
        }
        let skeletonBones = skeleton.bones;
        if (deformArray.length == 0) {
            for (let w = offset, b = skip * 3; w < count; w += stride) {
                let wx = 0, wy = 0;
                let n = bones[v++];
                n += v;
                for (; v < n; v++, b += 3) {
                    let bone = skeletonBones[bones[v]];
                    let vx = vertices[b], vy = vertices[b + 1], weight = vertices[b + 2];
                    wx += (vx * bone.a + vy * bone.b + bone.worldX) * weight;
                    wy += (vx * bone.c + vy * bone.d + bone.worldY) * weight;
                }
                worldVertices[w] = wx;
                worldVertices[w + 1] = wy;
            }
        }
        else {
            let deform = deformArray;
            for (let w = offset, b = skip * 3, f = skip << 1; w < count; w += stride) {
                let wx = 0, wy = 0;
                let n = bones[v++];
                n += v;
                for (; v < n; v++, b += 3, f += 2) {
                    let bone = skeletonBones[bones[v]];
                    let vx = vertices[b] + deform[f], vy = vertices[b + 1] + deform[f + 1], weight = vertices[b + 2];
                    wx += (vx * bone.a + vy * bone.b + bone.worldX) * weight;
                    wy += (vx * bone.c + vy * bone.d + bone.worldY) * weight;
                }
                worldVertices[w] = wx;
                worldVertices[w + 1] = wy;
            }
        }
    }
    /** Does not copy id (generated) or name (set on construction). **/
    copyTo(attachment) {
        if (this.bones) {
            attachment.bones = new Array(this.bones.length);
            Utils.arrayCopy(this.bones, 0, attachment.bones, 0, this.bones.length);
        }
        else
            attachment.bones = null;
        if (this.vertices) {
            attachment.vertices = Utils.newFloatArray(this.vertices.length);
            Utils.arrayCopy(this.vertices, 0, attachment.vertices, 0, this.vertices.length);
        }
        attachment.worldVerticesLength = this.worldVerticesLength;
        attachment.timelineAttachment = this.timelineAttachment;
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiQXR0YWNobWVudC5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIi4uLy4uL3NyYy9hdHRhY2htZW50cy9BdHRhY2htZW50LnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiJBQUFBOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7K0VBMkIrRTtBQUcvRSxPQUFPLEVBQW1CLEtBQUssRUFBRSxNQUFNLGFBQWEsQ0FBQztBQUVyRCwwQ0FBMEM7QUFDMUMsTUFBTSxPQUFnQixVQUFVO0lBQy9CLElBQUksQ0FBUztJQUViLFlBQWEsSUFBWTtRQUN4QixJQUFJLENBQUMsSUFBSTtZQUFFLE1BQU0sSUFBSSxLQUFLLENBQUMsc0JBQXNCLENBQUMsQ0FBQztRQUNuRCxJQUFJLENBQUMsSUFBSSxHQUFHLElBQUksQ0FBQztJQUNsQixDQUFDO0NBR0Q7QUFFRDswQkFDMEI7QUFDMUIsTUFBTSxPQUFnQixnQkFBaUIsU0FBUSxVQUFVO0lBQ2hELE1BQU0sQ0FBQyxNQUFNLEdBQUcsQ0FBQyxDQUFDO0lBRTFCLHlDQUF5QztJQUN6QyxFQUFFLEdBQUcsZ0JBQWdCLENBQUMsTUFBTSxFQUFFLENBQUM7SUFFL0I7OzRDQUV3QztJQUN4QyxLQUFLLEdBQXlCLElBQUksQ0FBQztJQUVuQzs7c0JBRWtCO0lBQ2xCLFFBQVEsR0FBb0IsRUFBRSxDQUFDO0lBRS9CO3NFQUNrRTtJQUNsRSxtQkFBbUIsR0FBRyxDQUFDLENBQUM7SUFFeEI7NEVBQ3dFO0lBQ3hFLGtCQUFrQixHQUFlLElBQUksQ0FBQztJQUV0QyxZQUFhLElBQVk7UUFDeEIsS0FBSyxDQUFDLElBQUksQ0FBQyxDQUFDO0lBQ2IsQ0FBQztJQUVEOzs7Ozs7Ozs7OzhGQVUwRjtJQUMxRixvQkFBb0IsQ0FBRSxJQUFVLEVBQUUsS0FBYSxFQUFFLEtBQWEsRUFBRSxhQUE4QixFQUFFLE1BQWMsRUFBRSxNQUFjO1FBQzdILEtBQUssR0FBRyxNQUFNLEdBQUcsQ0FBQyxLQUFLLElBQUksQ0FBQyxDQUFDLEdBQUcsTUFB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QUFNLENBQUMsQ0FBQztZQUNoRSxLQUFLLENBQUMsU0FBUyxDQUFDLElBQUksQ0FBQyxRQUFRLEVBQUUsQ0FBQyxFQUFFLFVBQVUsQ0FBQyxRQUFRLEVBQUUsQ0FBQyxFQUFFLElBQUksQ0FBQyxRQUFRLENBQUMsTUFBTSxDQUFDLENBQUM7UUFDakYsQ0FBQztRQUVELFVBQVUsQ0FBQyxtQkFBbUIsR0FBRyxJQUFJLENBQUMsbUJBQW1CLENBQUM7UUFDMUQsVUFBVSxDQUFDLGtCQUFrQixHQUFHLElBQUksQ0FBQyxrQkFBa0IsQ0FBQztJQUN6RCxDQUFDIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBBcHJpbCA1LCAyMDI1LiBSZXBsYWNlcyBhbGwgcHJpb3IgdmVyc2lvbnMuXG4gKlxuICogQ29weXJpZ2h0IChjKSAyMDEzLTIwMjUsIEVzb3RlcmljIFNvZnR3YXJlIExMQ1xuICpcbiAqIEludGVncmF0aW9uIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlIG9yIG90aGVyd2lzZSBjcmVhdGluZ1xuICogZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgaXMgcGVybWl0dGVkIHVuZGVyIHRoZSB0ZXJtcyBhbmRcbiAqIGNvbmRpdGlvbnMgb2YgU2VjdGlvbiAyIG9mIHRoZSBTcGluZSBFZGl0b3IgTGljZW5zZSBBZ3JlZW1lbnQ6XG4gKiBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtZWRpdG9yLWxpY2Vuc2VcbiAqXG4gKiBPdGhlcndpc2UsIGl0IGlzIHBlcm1pdHRlZCB0byBpbnRlZ3JhdGUgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmVcbiAqIG9yIG90aGVyd2lzZSBjcmVhdGUgZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgKGNvbGxlY3RpdmVseSxcbiAqIFwiUHJvZHVjdHNcIiksIHByb3ZpZGVkIHRoYXQgZWFjaCB1c2VyIG9mIHRoZSBQcm9kdWN0cyBtdXN0IG9idGFpbiB0aGVpciBvd25cbiAqIFNwaW5lIEVkaXRvciBsaWNlbnNlIGFuZCByZWRpc3RyaWJ1dGlvbiBvZiB0aGUgUHJvZHVjdHMgaW4gYW55IGZvcm0gbXVzdFxuICogaW5jbHVkZSB0aGlzIGxpY2Vuc2UgYW5kIGNvcHlyaWdodCBub3RpY2UuXG4gKlxuICogVEhFIFNQSU5FIFJVTlRJTUVTIEFSRSBQUk9WSURFRCBCWSBFU09URVJJQyBTT0ZUV0FSRSBMTEMgXCJBUyBJU1wiIEFORCBBTllcbiAqIEVYUFJFU1MgT1IgSU1QTElFRCBXQVJSQU5USUVTLCBJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgVEhFIElNUExJRURcbiAqIFdBUlJBTlRJRVMgT0YgTUVSQ0hBTlRBQklMSVRZIEFORCBGSVRORVNTIEZPUiBBIFBBUlRJQ1VMQVIgUFVSUE9TRSBBUkVcbiAqIERJU0NMQUlNRUQuIElOIE5PIEVWRU5UIFNIQUxMIEVTT1RFUklDIFNPRlRXQVJFIExMQyBCRSBMSUFCTEUgRk9SIEFOWVxuICogRElSRUNULCBJTkRJUkVDVCwgSU5DSURFTlRBTCwgU1BFQ0lBTCwgRVhFTVBMQVJZLCBPUiBDT05TRVFVRU5USUFMIERBTUFHRVNcbiAqIChJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgUFJPQ1VSRU1FTlQgT0YgU1VCU1RJVFVURSBHT09EUyBPUiBTRVJWSUNFUyxcbiAqIEJVU0lORVNTIElOVEVSUlVQVElPTiwgT1IgTE9TUyBPRiBVU0UsIERBVEEsIE9SIFBST0ZJVFMpIEhPV0VWRVIgQ0FVU0VEIEFORFxuICogT04gQU5ZIFRIRU9SWSBPRiBMSUFCSUxJVFksIFdIRVRIRVIgSU4gQ09OVFJBQ1QsIFNUUklDVCBMSUFCSUxJVFksIE9SIFRPUlRcbiAqIChJTkNMVURJTkcgTkVHTElHRU5DRSBPUiBPVEhFUldJU0UpIEFSSVNJTkcgSU4gQU5ZIFdBWSBPVVQgT0YgVEhFIFVTRSBPRlxuICogVEhFIFNQSU5FIFJVTlRJTUVTLCBFVkVOIElGIEFEVklTRUQgT0YgVEhFIFBPU1NJQklMSVRZIE9GIFNVQ0ggREFNQUdFLlxuICoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqL1xuXG5pbXBvcnQgeyBTbG90IH0gZnJvbSBcIi4uL1Nsb3QuanNcIjtcbmltcG9ydCB7IE51bWJlckFycmF5TGlrZSwgVXRpbHMgfSBmcm9tIFwiLi4vVXRpbHMuanNcIjtcblxuLyoqIFRoZSBiYXNlIGNsYXNzIGZvciBhbGwgYXR0YWNobWVudHMuICovXG5leHBvcnQgYWJzdHJhY3QgY2xhc3MgQXR0YWNobWVudCB7XG5cdG5hbWU6IHN0cmluZztcblxuXHRjb25zdHJ1Y3RvciAobmFtZTogc3RyaW5nKSB7XG5cdFx0aWYgKCFuYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJuYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHR0aGlzLm5hbWUgPSBuYW1lO1xuXHR9XG5cblx0YWJzdHJhY3QgY29weSAoKTogQXR0YWNobWVudDtcbn1cblxuLyoqIEJhc2UgY2xhc3MgZm9yIGFuIGF0dGFjaG1lbnQgd2l0aCB2ZXJ0aWNlcyB0aGF0IGFyZSB0cmFuc2Zvcm1lZCBieSBvbmUgb3IgbW9yZSBib25lcyBhbmQgY2FuIGJlIGRlZm9ybWVkIGJ5IGEgc2xvdCdzXG4gKiB7QGxpbmsgU2xvdCNkZWZvcm19LiAqL1xuZXhwb3J0IGFic3RyYWN0IGNsYXNzIFZlcnRleEF0dGFjaG1lbnQgZXh0ZW5kcyBBdHRhY2htZW50IHtcblx0cHJpdmF0ZSBzdGF0aWMgbmV4dElEID0gMDtcblxuXHQvKiogVGhlIHVuaXF1ZSBJRCBmb3IgdGhpcyBhdHRhY2htZW50LiAqL1xuXHRpZCA9IFZlcnRleEF0dGFjaG1lbnQubmV4dElEKys7XG5cblx0LyoqIFRoZSBib25lcyB3aGljaCBhZmZlY3QgdGhlIHtAbGluayAjZ2V0VmVydGljZXMoKX0uIFRoZSBhcnJheSBlbnRyaWVzIGFyZSwgZm9yIGVhY2ggdmVydGV4LCB0aGUgbnVtYmVyIG9mIGJvbmVzIGFmZmVjdGluZ1xuXHQgKiB0aGUgdmVydGV4IGZvbGxvd2VkIGJ5IHRoYXQgbWFueSBib25lIGluZGljZXMsIHdoaWNoIGlzIHRoZSBpbmRleCBvZiB0aGUgYm9uZSBpbiB7QGxpbmsgU2tlbGV0b24jYm9uZXN9LiBXaWxsIGJlIG51bGxcblx0ICogaWYgdGhpcyBhdHRhY2htZW50IGhhcyBubyB3ZWlnaHRzLiAqL1xuXHRib25lczogQXJyYXk8bnVtYmVyPiB8IG51bGwgPSBudWxsO1xuXG5cdC8qKiBUaGUgdmVydGV4IHBvc2l0aW9ucyBpbiB0aGUgYm9uZSdzIGNvb3JkaW5hdGUgc3lzdGVtLiBGb3IgYSBub24td2VpZ2h0ZWQgYXR0YWNobWVudCwgdGhlIHZhbHVlcyBhcmUgYHgseWBcblx0ICogZW50cmllcyBmb3IgZWFjaCB2ZXJ0ZXguIEZvciBhIHdlaWdodGVkIGF0dGFjaG1lbnQsIHRoZSB2YWx1ZXMgYXJlIGB4LHksd2VpZ2h0YCBlbnRyaWVzIGZvciBlYWNoIGJvbmUgYWZmZWN0aW5nXG5cdCAqIGVhY2ggdmVydGV4LiAqL1xuXHR2ZXJ0aWNlczogTnVtYmVyQXJyYXlMaWtlID0gW107XG5cblx0LyoqIFRoZSBtYXhpbXVtIG51bWJlciBvZiB3b3JsZCB2ZXJ0ZXggdmFsdWVzIHRoYXQgY2FuIGJlIG91dHB1dCBieVxuXHQgKiB7QGxpbmsgI2NvbXB1dGVXb3JsZFZlcnRpY2VzKCl9IHVzaW5nIHRoZSBgY291bnRgIHBhcmFtZXRlci4gKi9cblx0d29ybGRWZXJ0aWNlc0xlbmd0aCA9IDA7XG5cblx0LyoqIFRpbWVsaW5lcyBmb3IgdGhlIHRpbWVsaW5lIGF0dGFjaG1lbnQgYXJlIGFsc28gYXBwbGllZCB0byB0aGlzIGF0dGFjaG1lbnQuXG5cdCAqIE1heSBiZSBudWxsIGlmIG5vIGF0dGFjaG1lbnQtc3BlY2lmaWMgdGltZWxpbmVzIHNob3VsZCBiZSBhcHBsaWVkLiAqL1xuXHR0aW1lbGluZUF0dGFjaG1lbnQ6IEF0dGFjaG1lbnQgPSB0aGlzO1xuXG5cdGNvbnN0cnVjdG9yIChuYW1lOiBzdHJpbmcpIHtcblx0XHRzdXBlcihuYW1lKTtcblx0fVxuXG5cdC8qKiBUcmFuc2Zvcm1zIHRoZSBhdHRhY2htZW50J3MgbG9jYWwge0BsaW5rICN2ZXJ0aWNlc30gdG8gd29ybGQgY29vcmRpbmF0ZXMuIElmIHRoZSBzbG90J3Mge0BsaW5rIFNsb3QjZGVmb3JtfSBpc1xuXHQgKiBub3QgZW1wdHksIGl0IGlzIHVzZWQgdG8gZGVmb3JtIHRoZSB2ZXJ0aWNlcy5cblx0ICpcblx0ICogU2VlIFtXb3JsZCB0cmFuc2Zvcm1zXShodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtcnVudGltZS1za2VsZXRvbnMjV29ybGQtdHJhbnNmb3JtcykgaW4gdGhlIFNwaW5lXG5cdCAqIFJ1bnRpbWVzIEd1aWRlLlxuXHQgKiBAcGFyYW0gc3RhcnQgVGhlIGluZGV4IG9mIHRoZSBmaXJzdCB7QGxpbmsgI3ZlcnRpY2VzfSB2YWx1ZSB0byB0cmFuc2Zvcm0uIEVhY2ggdmVydGV4IGhhcyAyIHZhbHVlcywgeCBhbmQgeS5cblx0ICogQHBhcmFtIGNvdW50IFRoZSBudW1iZXIgb2Ygd29ybGQgdmVydGV4IHZhbHVlcyB0byBvdXRwdXQuIE11c3QgYmUgPD0ge0BsaW5rICN3b3JsZFZlcnRpY2VzTGVuZ3RofSAtIGBzdGFydGAuXG5cdCAqIEBwYXJhbSB3b3JsZFZlcnRpY2VzIFRoZSBvdXRwdXQgd29ybGQgdmVydGljZXMuIE11c3QgaGF2ZSBhIGxlbmd0aCA+PSBgb2Zmc2V0YCArIGBjb3VudGAgKlxuXHQgKiAgICAgICAgICAgYHN0cmlkZWAgLyAyLlxuXHQgKiBAcGFyYW0gb2Zmc2V0IFRoZSBgd29ybGRWZXJ0aWNlc2AgaW5kZXggdG8gYmVnaW4gd3JpdGluZyB2YWx1ZXMuXG5cdCAqIEBwYXJhbSBzdHJpZGUgVGhlIG51bWJlciBvZiBgd29ybGRWZXJ0aWNlc2AgZW50cmllcyBiZXR3ZWVuIHRoZSB2YWx1ZSBwYWlycyB3cml0dGVuLiAqL1xuXHRjb21wdXRlV29ybGRWZXJ0aWNlcyAoc2xvdDogU2xvdCwgc3RhcnQ6IG51bWJlciwgY291bnQ6IG51bWJlciwgd29ybGRWZXJ0aWNlczogTnVtYmVyQXJyYXlMaWtlLCBvZmZzZXQ6IG51bWJlciwgc3RyaWRlOiBudW1iZXIpIHtcblx0XHRjb3VudCA9IG9mZnNldCArIChjb3VudCA+PiAxKSAqIHN0cmlkZTtcblx0XHRsZXQgc2tlbGV0b24gPSBzbG90LmJvbmUuc2tlbGV0b247XG5cdFx0bGV0IGRlZm9ybUFycmF5ID0gc2xvdC5kZWZvcm07XG5cdFx0bGV0IHZlcnRpY2VzID0gdGhpcy52ZXJ0aWNlcztcblx0XHRsZXQgYm9uZXMgPSB0aGlzLmJvbmVzO1xuXHRcdGlmICghYm9uZXMpIHtcblx0XHRcdGlmIChkZWZvcm1BcnJheS5sZW5ndGggPiAwKSB2ZXJ0aWNlcyA9IGRlZm9ybUFycmF5O1xuXHRcdFx0bGV0IGJvbmUgPSBzbG90LmJvbmU7XG5cdFx0XHRsZXQgeCA9IGJvbmUud29ybGRYO1xuXHRcdFx0bGV0IHkgPSBib25lLndvcmxkWTtcblx0XHRcdGxldCBhID0gYm9uZS5hLCBiID0gYm9uZS5iLCBjID0gYm9uZS5jLCBkID0gYm9uZS5kO1xuXHRcdFx0Zm9yIChsZXQgdiA9IHN0YXJ0LCB3ID0gb2Zmc2V0OyB3IDwgY291bnQ7IHYgKz0gMiwgdyArPSBzdHJpZGUpIHtcblx0XHRcdFx0bGV0IHZ4ID0gdmVydGljZXNbdl0sIHZ5ID0gdmVydGljZXNbdiArIDFdO1xuXHRcdFx0XHR3b3JsZFZlcnRpY2VzW3ddID0gdnggKiBhICsgdnkgKiBiICsgeDtcblx0XHRcdFx0d29ybGRWZXJ0aWNlc1t3ICsgMV0gPSB2eCAqIGMgKyB2eSAqIGQgKyB5O1xuXHRcdFx0fVxuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblx0XHRsZXQgdiA9IDAsIHNraXAgPSAwO1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgc3RhcnQ7IGkgKz0gMikge1xuXHRcdFx0bGV0IG4gPSBib25lc1t2XTtcblx0XHRcdHYgKz0gbiArIDE7XG5cdFx0XHRza2lwICs9IG47XG5cdFx0fVxuXHRcdGxldCBza2VsZXRvbkJvbmVzID0gc2tlbGV0b24uYm9uZXM7XG5cdFx0aWYgKGRlZm9ybUFycmF5Lmxlbmd0aCA9PSAwKSB7XG5cdFx0XHRmb3IgKGxldCB3ID0gb2Zmc2V0LCBiID0gc2tpcCAqIDM7IHcgPCBjb3VudDsgdyArPSBzdHJpZGUpIHtcblx0XHRcdFx0bGV0IHd4ID0gMCwgd3kgPSAwO1xuXHRcdFx0XHRsZXQgbiA9IGJvbmVzW3YrK107XG5cdFx0XHRcdG4gKz0gdjtcblx0XHRcdFx0Zm9yICg7IHYgPCBuOyB2KyssIGIgKz0gMykge1xuXHRcdFx0XHRcdGxldCBib25lID0gc2tlbGV0b25Cb25lc1tib25lc1t2XV07XG5cdFx0XHRcdFx0bGV0IHZ4ID0gdmVydGljZXNbYl0sIHZ5ID0gdmVydGljZXNbYiArIDFdLCB3ZWlnaHQgPSB2ZXJ0aWNlc1tiICsgMl07XG5cdFx0XHRcdFx0d3ggKz0gKHZ4ICogYm9uZS5hICsgdnkgKiBib25lLmIgKyBib25lLndvcmxkWCkgKiB3ZWlnaHQ7XG5cdFx0XHRcdFx0d3kgKz0gKHZ4ICogYm9uZS5jICsgdnkgKiBib25lLmQgKyBib25lLndvcmxkWSkgKiB3ZWlnaHQ7XG5cdFx0XHRcdH1cblx0XHRcdFx0d29ybGRWZXJ0aWNlc1t3XSA9IHd4O1xuXHRcdFx0XHR3b3JsZFZlcnRpY2VzW3cgKyAxXSA9IHd5O1xuXHRcdFx0fVxuXHRcdH0gZWxzZSB7XG5cdFx0XHRsZXQgZGVmb3JtID0gZGVmb3JtQXJyYXk7XG5cdFx0XHRmb3IgKGxldCB3ID0gb2Zmc2V0LCBiID0gc2tpcCAqIDMsIGYgPSBza2lwIDw8IDE7IHcgPCBjb3VudDsgdyArPSBzdHJpZGUpIHtcblx0XHRcdFx0bGV0IHd4ID0gMCwgd3kgPSAwO1xuXHRcdFx0XHRsZXQgbiA9IGJvbmVzW3YrK107XG5cdFx0XHRcdG4gKz0gdjtcblx0XHRcdFx0Zm9yICg7IHYgPCBuOyB2KyssIGIgKz0gMywgZiArPSAyKSB7XG5cdFx0XHRcdFx0bGV0IGJvbmUgPSBza2VsZXRvbkJvbmVzW2JvbmVzW3ZdXTtcblx0XHRcdFx0XHRsZXQgdnggPSB2ZXJ0aWNlc1tiXSArIGRlZm9ybVtmXSwgdnkgPSB2ZXJ0aWNlc1tiICsgMV0gKyBkZWZvcm1bZiArIDFdLCB3ZWlnaHQgPSB2ZXJ0aWNlc1tiICsgMl07XG5cdFx0XHRcdFx0d3ggKz0gKHZ4ICogYm9uZS5hICsgdnkgKiBib25lLmIgKyBib25lLndvcmxkWCkgKiB3ZWlnaHQ7XG5cdFx0XHRcdFx0d3kgKz0gKHZ4ICogYm9uZS5jICsgdnkgKiBib25lLmQgKyBib25lLndvcmxkWSkgKiB3ZWlnaHQ7XG5cdFx0XHRcdH1cblx0XHRcdFx0d29ybGRWZXJ0aWNlc1t3XSA9IHd4O1xuXHRcdFx0XHR3b3JsZFZlcnRpY2VzW3cgKyAxXSA9IHd5O1xuXHRcdFx0fVxuXHRcdH1cblx0fVxuXG5cdC8qKiBEb2VzIG5vdCBjb3B5IGlkIChnZW5lcmF0ZWQpIG9yIG5hbWUgKHNldCBvbiBjb25zdHJ1Y3Rpb24pLiAqKi9cblx0Y29weVRvIChhdHRhY2htZW50OiBWZXJ0ZXhBdHRhY2htZW50KSB7XG5cdFx0aWYgKHRoaXMuYm9uZXMpIHtcblx0XHRcdGF0dGFjaG1lbnQuYm9uZXMgPSBuZXcgQXJyYXk8bnVtYmVyPih0aGlzLmJvbmVzLmxlbmd0aCk7XG5cdFx0XHRVdGlscy5hcnJheUNvcHkodGhpcy5ib25lcywgMCwgYXR0YWNobWVudC5ib25lcywgMCwgdGhpcy5ib25lcy5sZW5ndGgpO1xuXHRcdH0gZWxzZVxuXHRcdFx0YXR0YWNobWVudC5ib25lcyA9IG51bGw7XG5cblx0XHRpZiAodGhpcy52ZXJ0aWNlcykge1xuXHRcdFx0YXR0YWNobWVudC52ZXJ0aWNlcyA9IFV0aWxzLm5ld0Zsb2F0QXJyYXkodGhpcy52ZXJ0aWNlcy5sZW5ndGgpO1xuXHRcdFx0VXRpbHMuYXJyYXlDb3B5KHRoaXMudmVydGljZXMsIDAsIGF0dGFjaG1lbnQudmVydGljZXMsIDAsIHRoaXMudmVydGljZXMubGVuZ3RoKTtcblx0XHR9XG5cblx0XHRhdHRhY2htZW50LndvcmxkVmVydGljZXNMZW5ndGggPSB0aGlzLndvcmxkVmVydGljZXNMZW5ndGg7XG5cdFx0YXR0YWNobWVudC50aW1lbGluZUF0dGFjaG1lbnQgPSB0aGlzLnRpbWVsaW5lQXR0YWNobWVudDtcblx0fVxufVxuIl19