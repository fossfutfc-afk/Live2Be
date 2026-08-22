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
import { VertexAttachment } from "./attachments/Attachment.js";
import { Color } from "./Utils.js";
/** Stores a slot's current pose. Slots organize attachments for {@link Skeleton#drawOrder} purposes and provide a place to store
 * state for an attachment. State cannot be stored in an attachment itself because attachments are stateless and may be shared
 * across multiple skeletons. */
export class Slot {
    /** The slot's setup pose data. */
    data;
    /** The bone this slot belongs to. */
    bone;
    /** The color used to tint the slot's attachment. If {@link #getDarkColor()} is set, this is used as the light color for two
     * color tinting. */
    color;
    /** The dark color used to tint the slot's attachment for two color tinting, or null if two color tinting is not used. The dark
     * color's alpha is not used. */
    darkColor = null;
    attachment = null;
    attachmentState = 0;
    /** The index of the texture region to display when the slot's attachment has a {@link Sequence}. -1 represents the
     * {@link Sequence#getSetupIndex()}. */
    sequenceIndex = -1;
    /** Values to deform the slot's attachment. For an unweighted mesh, the entries are local positions for each vertex. For a
     * weighted mesh, the entries are an offset for each vertex which will be added to the mesh's local vertex positions.
     *
     * See {@link VertexAttachment#computeWorldVertices()} and {@link DeformTimeline}. */
    deform = new Array();
    constructor(data, bone) {
        if (!data)
            throw new Error("data cannot be null.");
        if (!bone)
            throw new Error("bone cannot be null.");
        this.data = data;
        this.bone = bone;
        this.color = new Color();
        this.darkColor = !data.darkColor ? null : new Color();
        this.setToSetupPose();
    }
    /** The skeleton this slot belongs to. */
    getSkeleton() {
        return this.bone.skeleton;
    }
    /** The current attachment for the slot, or null if the slot has no attachment. */
    getAttachment() {
        return this.attachment;
    }
    /** Sets the slot's attachment and, if the attachment changed, resets {@link #sequenceIndex} and clears the {@link #deform}.
     * The deform is not cleared if the old attachment has the same {@link VertexAttachment#getTimelineAttachment()} as the
     * specified attachment. */
    setAttachment(attachment) {
        if (this.attachment == attachment)
            return;
        if (!(attachment instanceof VertexAttachment) || !(this.attachment instanceof VertexAttachment)
            || attachment.timelineAttachment != this.attachment.timelineAttachment) {
            this.deform.length = 0;
        }
        this.attachment = attachment;
        this.sequenceIndex = -1;
    }
    /** Sets this slot to the setup pose. */
    setToSetupPose() {
        this.color.setFromColor(this.data.color);
        if (this.darkColor)
            this.darkColor.setFromColor(this.data.darkColor);
        if (!this.data.attachmentName)
            this.attachment = null;
        else {
            this.attachment = null;
            this.setAttachment(this.bone.skeleton.getAttachment(this.data.index, this.data.attachmentName));
        }
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiU2xvdC5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIi4uL3NyYy9TbG90LnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiJBQUFBOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7K0VBMkIrRTtBQUUvRSxPQUFPLEVBQWMsZ0JBQWdCLEVBQUUsTUFBTSw2QkFBNkIsQ0FBQztBQUkzRSxPQUFPLEVBQUUsS0FBSyxFQUFFLE1BQU0sWUFBWSxDQUFDO0FBRW5DOztnQ0FFZ0M7QUFDaEMsTUFBTSxPQUFPLElBQUk7SUFDaEIsa0NBQWtDO0lBQ2xDLElBQUksQ0FBVztJQUVmLHFDQUFxQztJQUNyQyxJQUFJLENBQU87SUFFWDt3QkFDb0I7SUFDcEIsS0FBSyxDQUFRO0lBRWI7b0NBQ2dDO0lBQ2hDLFNBQVMsR0FBaUIsSUFBSSxDQUFDO0lBRS9CLFVBQVUsR0FBc0IsSUFBSSxDQUFDO0lBRXJDLGVBQWUsR0FBVyxDQUFDLENBQUM7SUFFNUI7MkNBQ3VDO0lBQ3ZDLGFBQWEsR0FBVyxDQUFDLENBQUMsQ0FBQztJQUUzQjs7O3lGQUdxRjtJQUNyRixNQUFNLEdBQUcsSUFBSSxLQUFLLEVBQVUsQ0FBQztJQUU3QixZQUFhLElBQWMsRUFBRSxJQUFVO1FBQ3RDLElBQUksQ0FBQyxJQUFJO1lBQUUsTUFBTSxJQUFJLEtBQUssQ0FBQyxzQkFBc0IsQ0FBQyxDQUFDO1FBQ25ELElBQUksQ0FBQyxJQUFJO1lBQUUsTUFBTSxJQUFJLEtBQUssQ0FBQyxzQkFBc0IsQ0FBQyxDQUFDO1FBQ25ELElBQUksQ0FBQyxJQUFJLEdBQUcsSUFBSSxDQUFDO1FBQ2pCLElBQUksQ0FBQyxJQUFJLEdBQUcsSUFBSSxDQUFDO1FBQ2pCLElBQUksQ0FBQyxLQUFLLEdBQUcsSUFBSSxLQUFLLEVBQUUsQ0FBQztRQUN6QixJQUFJLENBQUMsU0FBUyxHQUFHLENBQUMsSUFBSSxDQUFDLFNBQVMsQ0FBQyxDQUFDLENBQUMsSUFBSSxDQUFDLENBQUMsQ0FBQyxJQUFJLEtBQUssRUFBRSxDQUFDO1FBQ3RELElBQUksQ0FBQyxjQUFjLEVBQUUsQ0FBQztJQUN2QixDQUFDO0lBRUQseUNBQXlDO0lBQ3pDLFdBQVc7UUFDVixPQUFPLElBQUksQ0FBQyxJQUFJLENBQUMsUUFBUSxDQUFDO0lBQzNCLENBQUM7SUFFRCxrRkFBa0Y7SUFDbEYsYUFBYTtRQUNaLE9BQU8sSUFBSSxDQUFDLFVBQVUsQ0FBQztJQUN4QixDQUFDO0lBRUQ7OytCQUUyQjtJQUMzQixhQUFhLENBQUUsVUFBNkI7UUFDM0MsSUFBSSxJQUFJLENBQUMsVUFBVSxJQUFJLFVBQVU7WUFBRSxPQUFPO1FBQzFDLElBQUksQ0FBQyxDQUFDLFVBQVUsWUFBWSxnQkFBZ0IsQ0FBQyxJQUFJLENBQUMsQ0FBQyxJQUFJLENBQUMsVUFBVSxZQUFZLGdCQUFnQixDQUFDO2VBQ3hFLFVBQVcsQ0FBQyxrQkFBa0IsSUFBdUIsSUFBSSxDQUFDLFVBQVcsQ0FBQyxrQkFBa0IsRUFBRSxDQUFDO1lBQ2pILElBQUksQ0FBQyxNQUFNLENBQUMsTUFBTSxHQUFHLENBQUMsQ0FBQztRQUN4QixDQUFDO1FBQ0QsSUFBSSxDQUFDLFVBQVUsR0FBRyxVQUFVLENBQUM7UUFDN0IsSUFBSSxDQUFDLGFBQWEsR0FBRyxDQUFDLENBQUMsQ0FBQztJQUN6QixDQUFDO0lBRUQsd0NBQXdDO0lBQ3hDLGNBQWM7UUFDYixJQUFJLENBQUMsS0FBSyxDQUFDLFlBQVksQ0FBQyxJQUFJLENBQUMsSUFBSSxDQUFDLEtBQUssQ0FBQyxDQUFDO1FBQ3pDLElBQUksSUFBSSxDQUFDLFNBQVM7WUFBRSxJQUFJLENBQUMsU0FBUyxDQUFDLFlBQVksQ0FBQyxJQUFJLENBQUMsSUFBSSxDQUFDLFNBQVUsQ0FBQyxDQUFDO1FBQ3RFLElBQUksQ0FBQyxJQUFJLENBQUMsSUFBSSxDQUFDLGNBQWM7WUFDNUIsSUFBSSxDQUFDLFVBQVUsR0FBRyxJQUFJLENBQUM7YUFDbkIsQ0FBQztZQUNMLElBQUksQ0FBQyxVQUFVLEdBQUcsSUFBSSxDQUFDO1lBQ3ZCLElBQUksQ0FBQyxhQUFhLENBQUMsSUFBSSxDQUFDLElBQUksQ0FBQyxRQUFRLENBQUMsYUFBYSxDQUFDLElBQUksQ0FBQyxJQUFJLENBQUMsS0FBSyxFQUFFLElBQUksQ0FBQyxJQUFJLENBQUMsY0FBYyxDQUFDLENBQUMsQ0FBQztRQUNqRyxDQUFDO0lBQ0YsQ0FBQztDQUNEIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBBcHJpbCA1LCAyMDI1LiBSZXBsYWNlcyBhbGwgcHJpb3IgdmVyc2lvbnMuXG4gKlxuICogQ29weXJpZ2h0IChjKSAyMDEzLTIwMjUsIEVzb3RlcmljIFNvZnR3YXJlIExMQ1xuICpcbiAqIEludGVncmF0aW9uIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlIG9yIG90aGVyd2lzZSBjcmVhdGluZ1xuICogZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgaXMgcGVybWl0dGVkIHVuZGVyIHRoZSB0ZXJtcyBhbmRcbiAqIGNvbmRpdGlvbnMgb2YgU2VjdGlvbiAyIG9mIHRoZSBTcGluZSBFZGl0b3IgTGljZW5zZSBBZ3JlZW1lbnQ6XG4gKiBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtZWRpdG9yLWxpY2Vuc2VcbiAqXG4gKiBPdGhlcndpc2UsIGl0IGlzIHBlcm1pdHRlZCB0byBpbnRlZ3JhdGUgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmVcbiAqIG9yIG90aGVyd2lzZSBjcmVhdGUgZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgKGNvbGxlY3RpdmVseSxcbiAqIFwiUHJvZHVjdHNcIiksIHByb3ZpZGVkIHRoYXQgZWFjaCB1c2VyIG9mIHRoZSBQcm9kdWN0cyBtdXN0IG9idGFpbiB0aGVpciBvd25cbiAqIFNwaW5lIEVkaXRvciBsaWNlbnNlIGFuZCByZWRpc3RyaWJ1dGlvbiBvZiB0aGUgUHJvZHVjdHMgaW4gYW55IGZvcm0gbXVzdFxuICogaW5jbHVkZSB0aGlzIGxpY2Vuc2UgYW5kIGNvcHlyaWdodCBub3RpY2UuXG4gKlxuICogVEhFIFNQSU5FIFJVTlRJTUVTIEFSRSBQUk9WSURFRCBCWSBFU09URVJJQyBTT0ZUV0FSRSBMTEMgXCJBUyBJU1wiIEFORCBBTllcbiAqIEVYUFJFU1MgT1IgSU1QTElFRCBXQVJSQU5USUVTLCBJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgVEhFIElNUExJRURcbiAqIFdBUlJBTlRJRVMgT0YgTUVSQ0hBTlRBQklMSVRZIEFORCBGSVRORVNTIEZPUiBBIFBBUlRJQ1VMQVIgUFVSUE9TRSBBUkVcbiAqIERJU0NMQUlNRUQuIElOIE5PIEVWRU5UIFNIQUxMIEVTT1RFUklDIFNPRlRXQVJFIExMQyBCRSBMSUFCTEUgRk9SIEFOWVxuICogRElSRUNULCBJTkRJUkVDVCwgSU5DSURFTlRBTCwgU1BFQ0lBTCwgRVhFTVBMQVJZLCBPUiBDT05TRVFVRU5USUFMIERBTUFHRVNcbiAqIChJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgUFJPQ1VSRU1FTlQgT0YgU1VCU1RJVFVURSBHT09EUyBPUiBTRVJWSUNFUyxcbiAqIEJVU0lORVNTIElOVEVSUlVQVElPTiwgT1IgTE9TUyBPRiBVU0UsIERBVEEsIE9SIFBST0ZJVFMpIEhPV0VWRVIgQ0FVU0VEIEFORFxuICogT04gQU5ZIFRIRU9SWSBPRiBMSUFCSUxJVFksIFdIRVRIRVIgSU4gQ09OVFJBQ1QsIFNUUklDVCBMSUFCSUxJVFksIE9SIFRPUlRcbiAqIChJTkNMVURJTkcgTkVHTElHRU5DRSBPUiBPVEhFUldJU0UpIEFSSVNJTkcgSU4gQU5ZIFdBWSBPVVQgT0YgVEhFIFVTRSBPRlxuICogVEhFIFNQSU5FIFJVTlRJTUVTLCBFVkVOIElGIEFEVklTRUQgT0YgVEhFIFBPU1NJQklMSVRZIE9GIFNVQ0ggREFNQUdFLlxuICoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqL1xuXG5pbXBvcnQgeyBBdHRhY2htZW50LCBWZXJ0ZXhBdHRhY2htZW50IH0gZnJvbSBcIi4vYXR0YWNobWVudHMvQXR0YWNobWVudC5qc1wiO1xuaW1wb3J0IHsgQm9uZSB9IGZyb20gXCIuL0JvbmUuanNcIjtcbmltcG9ydCB7IFNrZWxldG9uIH0gZnJvbSBcIi4vU2tlbGV0b24uanNcIjtcbmltcG9ydCB7IFNsb3REYXRhIH0gZnJvbSBcIi4vU2xvdERhdGEuanNcIjtcbmltcG9ydCB7IENvbG9yIH0gZnJvbSBcIi4vVXRpbHMuanNcIjtcblxuLyoqIFN0b3JlcyBhIHNsb3QncyBjdXJyZW50IHBvc2UuIFNsb3RzIG9yZ2FuaXplIGF0dGFjaG1lbnRzIGZvciB7QGxpbmsgU2tlbGV0b24jZHJhd09yZGVyfSBwdXJwb3NlcyBhbmQgcHJvdmlkZSBhIHBsYWNlIHRvIHN0b3JlXG4gKiBzdGF0ZSBmb3IgYW4gYXR0YWNobWVudC4gU3RhdGUgY2Fubm90IGJlIHN0b3JlZCBpbiBhbiBhdHRhY2htZW50IGl0c2VsZiBiZWNhdXNlIGF0dGFjaG1lbnRzIGFyZSBzdGF0ZWxlc3MgYW5kIG1heSBiZSBzaGFyZWRcbiAqIGFjcm9zcyBtdWx0aXBsZSBza2VsZXRvbnMuICovXG5leHBvcnQgY2xhc3MgU2xvdCB7XG5cdC8qKiBUaGUgc2xvdCdzIHNldHVwIHBvc2UgZGF0YS4gKi9cblx0ZGF0YTogU2xvdERhdGE7XG5cblx0LyoqIFRoZSBib25lIHRoaXMgc2xvdCBiZWxvbmdzIHRvLiAqL1xuXHRib25lOiBCb25lO1xuXG5cdC8qKiBUaGUgY29sb3IgdXNlZCB0byB0aW50IHRoZSBzbG90J3MgYXR0YWNobWVudC4gSWYge0BsaW5rICNnZXREYXJrQ29sb3IoKX0gaXMgc2V0LCB0aGlzIGlzIHVzZWQgYXMgdGhlIGxpZ2h0IGNvbG9yIGZvciB0d29cblx0ICogY29sb3IgdGludGluZy4gKi9cblx0Y29sb3I6IENvbG9yO1xuXG5cdC8qKiBUaGUgZGFyayBjb2xvciB1c2VkIHRvIHRpbnQgdGhlIHNsb3QncyBhdHRhY2htZW50IGZvciB0d28gY29sb3IgdGludGluZywgb3IgbnVsbCBpZiB0d28gY29sb3IgdGludGluZyBpcyBub3QgdXNlZC4gVGhlIGRhcmtcblx0ICogY29sb3IncyBhbHBoYSBpcyBub3QgdXNlZC4gKi9cblx0ZGFya0NvbG9yOiBDb2xvciB8IG51bGwgPSBudWxsO1xuXG5cdGF0dGFjaG1lbnQ6IEF0dGFjaG1lbnQgfCBudWxsID0gbnVsbDtcblxuXHRhdHRhY2htZW50U3RhdGU6IG51bWJlciA9IDA7XG5cblx0LyoqIFRoZSBpbmRleCBvZiB0aGUgdGV4dHVyZSByZWdpb24gdG8gZGlzcGxheSB3aGVuIHRoZSBzbG90J3MgYXR0YWNobWVudCBoYXMgYSB7QGxpbmsgU2VxdWVuY2V9LiAtMSByZXByZXNlbnRzIHRoZVxuXHQgKiB7QGxpbmsgU2VxdWVuY2UjZ2V0U2V0dXBJbmRleCgpfS4gKi9cblx0c2VxdWVuY2VJbmRleDogbnVtYmVyID0gLTE7XG5cblx0LyoqIFZhbHVlcyB0byBkZWZvcm0gdGhlIHNsb3QncyBhdHRhY2htZW50LiBGb3IgYW4gdW53ZWlnaHRlZCBtZXNoLCB0aGUgZW50cmllcyBhcmUgbG9jYWwgcG9zaXRpb25zIGZvciBlYWNoIHZlcnRleC4gRm9yIGFcblx0ICogd2VpZ2h0ZWQgbWVzaCwgdGhlIGVudHJpZXMgYXJlIGFuIG9mZnNldCBmb3IgZWFjaCB2ZXJ0ZXggd2hpY2ggd2lsbCBiZSBhZGRlZCB0byB0aGUgbWVzaCdzIGxvY2FsIHZlcnRleCBwb3NpdGlvbnMuXG5cdCAqXG5cdCAqIFNlZSB7QGxpbmsgVmVydGV4QXR0YWNobWVudCNjb21wdXRlV29ybGRWZXJ0aWNlcygpfSBhbmQge0BsaW5rIERlZm9ybVRpbWVsaW5lfS4gKi9cblx0ZGVmb3JtID0gbmV3IEFycmF5PG51bWJlcj4oKTtcblxuXHRjb25zdHJ1Y3RvciAoZGF0YTogU2xvdERhdGEsIGJvbmU6IEJvbmUpIHtcblx0XHRpZiAoIWRhdGEpIHRocm93IG5ldyBFcnJvcihcImRhdGEgY2Fubm90IGJlIG51bGwuXCIpO1xuXHRcdGlmICghYm9uZSkgdGhyb3cgbmV3IEVycm9yKFwiYm9uZSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0dGhpcy5kYXRhID0gZGF0YTtcblx0XHR0aGlzLmJvbmUgPSBib25lO1xuXHRcdHRoaXMuY29sb3IgPSBuZXcgQ29sb3IoKTtcblx0XHR0aGlzLmRhcmtDb2xvciA9ICFkYXRhLmRhcmtDb2xvciA/IG51bGwgOiBuZXcgQ29sb3IoKTtcblx0XHR0aGlzLnNldFRvU2V0dXBQb3NlKCk7XG5cdH1cblxuXHQvKiogVGhlIHNrZWxldG9uIHRoaXMgc2xvdCBiZWxvbmdzIHRvLiAqL1xuXHRnZXRTa2VsZXRvbiAoKTogU2tlbGV0b24ge1xuXHRcdHJldHVybiB0aGlzLmJvbmUuc2tlbGV0b247XG5cdH1cblxuXHQvKiogVGhlIGN1cnJlbnQgYXR0YWNobWVudCBmb3IgdGhlIHNsb3QsIG9yIG51bGwgaWYgdGhlIHNsb3QgaGFzIG5vIGF0dGFjaG1lbnQuICovXG5cdGdldEF0dGFjaG1lbnQgKCk6IEF0dGFjaG1lbnQgfCBudWxsIHtcblx0XHRyZXR1cm4gdGhpcy5hdHRhY2htZW50O1xuXHR9XG5cblx0LyoqIFNldHMgdGhlIHNsb3QncyBhdHRhY2htZW50IGFuZCwgaWYgdGhlIGF0dGFjaG1lbnQgY2hhbmdlZCwgcmVzZXRzIHtAbGluayAjc2VxdWVuY2VJbmRleH0gYW5kIGNsZWFycyB0aGUge0BsaW5rICNkZWZvcm19LlxuXHQgKiBUaGUgZGVmb3JtIGlzIG5vdCBjbGVhcmVkIGlmIHRoZSBvbGQgYXR0YWNobWVudCBoYXMgdGhlIHNhbWUge0BsaW5rIFZlcnRleEF0dGFjaG1lbnQjZ2V0VGltZWxpbmVBdHRhY2htZW50KCl9IGFzIHRoZVxuXHQgKiBzcGVjaWZpZWQgYXR0YWNobWVudC4gKi9cblx0c2V0QXR0YWNobWVudCAoYXR0YWNobWVudDogQXR0YWNobWVudCB8IG51bGwpIHtcblx0XHRpZiAodGhpcy5hdHRhY2htZW50ID09IGF0dGFjaG1lbnQpIHJldHVybjtcblx0XHRpZiAoIShhdHRhY2htZW50IGluc3RhbmNlb2YgVmVydGV4QXR0YWNobWVudCkgfHwgISh0aGlzLmF0dGFjaG1lbnQgaW5zdGFuY2VvZiBWZXJ0ZXhBdHRhY2htZW50KVxuXHRcdFx0fHwgKDxWZXJ0ZXhBdHRhY2htZW50PmF0dGFjaG1lbnQpLnRpbWVsaW5lQXR0YWNobWVudCAhPSAoPFZlcnRleEF0dGFjaG1lbnQ+dGhpcy5hdHRhY2htZW50KS50aW1lbGluZUF0dGFjaG1lbnQpIHtcblx0XHRcdHRoaXMuZGVmb3JtLmxlbmd0aCA9IDA7XG5cdFx0fVxuXHRcdHRoaXMuYXR0YWNobWVudCA9IGF0dGFjaG1lbnQ7XG5cdFx0dGhpcy5zZXF1ZW5jZUluZGV4ID0gLTE7XG5cdH1cblxuXHQvKiogU2V0cyB0aGlzIHNsb3QgdG8gdGhlIHNldHVwIHBvc2UuICovXG5cdHNldFRvU2V0dXBQb3NlICgpIHtcblx0XHR0aGlzLmNvbG9yLnNldEZyb21Db2xvcih0aGlzLmRhdGEuY29sb3IpO1xuXHRcdGlmICh0aGlzLmRhcmtDb2xvcikgdGhpcy5kYXJrQ29sb3Iuc2V0RnJvbUNvbG9yKHRoaXMuZGF0YS5kYXJrQ29sb3IhKTtcblx0XHRpZiAoIXRoaXMuZGF0YS5hdHRhY2htZW50TmFtZSlcblx0XHRcdHRoaXMuYXR0YWNobWVudCA9IG51bGw7XG5cdFx0ZWxzZSB7XG5cdFx0XHR0aGlzLmF0dGFjaG1lbnQgPSBudWxsO1xuXHRcdFx0dGhpcy5zZXRBdHRhY2htZW50KHRoaXMuYm9uZS5za2VsZXRvbi5nZXRBdHRhY2htZW50KHRoaXMuZGF0YS5pbmRleCwgdGhpcy5kYXRhLmF0dGFjaG1lbnROYW1lKSk7XG5cdFx0fVxuXHR9XG59XG4iXX0=