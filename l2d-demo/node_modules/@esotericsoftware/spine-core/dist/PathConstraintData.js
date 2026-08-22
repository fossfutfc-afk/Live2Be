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
import { ConstraintData } from "./ConstraintData.js";
/** Stores the setup pose for a {@link PathConstraint}.
 *
 * See [path constraints](http://esotericsoftware.com/spine-path-constraints) in the Spine User Guide. */
export class PathConstraintData extends ConstraintData {
    /** The bones that will be modified by this path constraint. */
    bones = new Array();
    /** The slot whose path attachment will be used to constrained the bones. */
    _target = null;
    set target(slotData) { this._target = slotData; }
    get target() {
        if (!this._target)
            throw new Error("SlotData not set.");
        else
            return this._target;
    }
    /** The mode for positioning the first bone on the path. */
    positionMode = PositionMode.Fixed;
    /** The mode for positioning the bones after the first bone on the path. */
    spacingMode = SpacingMode.Fixed;
    /** The mode for adjusting the rotation of the bones. */
    rotateMode = RotateMode.Chain;
    /** An offset added to the constrained bone rotation. */
    offsetRotation = 0;
    /** The position along the path. */
    position = 0;
    /** The spacing between bones. */
    spacing = 0;
    mixRotate = 0;
    mixX = 0;
    mixY = 0;
    constructor(name) {
        super(name, 0, false);
    }
}
/** Controls how the first bone is positioned along the path.
 *
 * See [position](http://esotericsoftware.com/spine-path-constraints#Position) in the Spine User Guide. */
export var PositionMode;
(function (PositionMode) {
    PositionMode[PositionMode["Fixed"] = 0] = "Fixed";
    PositionMode[PositionMode["Percent"] = 1] = "Percent";
})(PositionMode || (PositionMode = {}));
/** Controls how bones after the first bone are positioned along the path.
 *
 * See [spacing](http://esotericsoftware.com/spine-path-constraints#Spacing) in the Spine User Guide. */
export var SpacingMode;
(function (SpacingMode) {
    SpacingMode[SpacingMode["Length"] = 0] = "Length";
    SpacingMode[SpacingMode["Fixed"] = 1] = "Fixed";
    SpacingMode[SpacingMode["Percent"] = 2] = "Percent";
    SpacingMode[SpacingMode["Proportional"] = 3] = "Proportional";
})(SpacingMode || (SpacingMode = {}));
/** Controls how bones are rotated, translated, and scaled to match the path.
 *
 * See [rotate mix](http://esotericsoftware.com/spine-path-constraints#Rotate-mix) in the Spine User Guide. */
export var RotateMode;
(function (RotateMode) {
    RotateMode[RotateMode["Tangent"] = 0] = "Tangent";
    RotateMode[RotateMode["Chain"] = 1] = "Chain";
    RotateMode[RotateMode["ChainScale"] = 2] = "ChainScale";
})(RotateMode || (RotateMode = {}));
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiUGF0aENvbnN0cmFpbnREYXRhLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsiLi4vc3JjL1BhdGhDb25zdHJhaW50RGF0YS50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiQUFBQTs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OytFQTJCK0U7QUFHL0UsT0FBTyxFQUFFLGNBQWMsRUFBRSxNQUFNLHFCQUFxQixDQUFDO0FBSXJEOzt5R0FFeUc7QUFDekcsTUFBTSxPQUFPLGtCQUFtQixTQUFRLGNBQWM7SUFFckQsK0RBQStEO0lBQy9ELEtBQUssR0FBRyxJQUFJLEtBQUssRUFBWSxDQUFDO0lBRTlCLDRFQUE0RTtJQUNwRSxPQUFPLEdBQW9CLElBQUksQ0FBQztJQUN4QyxJQUFXLE1BQU0sQ0FBRSxRQUFrQixJQUFJLElBQUksQ0FBQyxPQUFPLEdBQUcsUUFBUSxDQUFDLENBQUMsQ0FBQztJQUNuRSxJQUFXLE1BQU07UUFDaEIsSUFBSSxDQUFDLElBQUksQ0FBQyxPQUFPO1lBQUUsTUFBTSxJQUFJLEtBQUssQ0FBQyxtQkFBbUIsQ0FBQyxDQUFBOztZQUNsRCxPQUFPLElBQUksQ0FBQyxPQUFPLENBQUM7SUFDMUIsQ0FBQztJQUVELDJEQUEyRDtJQUMzRCxZQUFZLEdBQWlCLFlBQVksQ0FBQyxLQUFLLENBQUM7SUFFaEQsMkVBQTJFO0lBQzNFLFdBQVcsR0FBZ0IsV0FBVyxDQUFDLEtBQUssQ0FBQztJQUU3Qyx3REFBd0Q7SUFDeEQsVUFBVSxHQUFlLFVBQVUsQ0FBQyxLQUFLLENBQUM7SUFFMUMsd0RBQXdEO0lBQ3hELGNBQWMsR0FBVyxDQUFDLENBQUM7SUFFM0IsbUNBQW1DO0lBQ25DLFFBQVEsR0FBVyxDQUFDLENBQUM7SUFFckIsaUNBQWlDO0lBQ2pDLE9BQU8sR0FBVyxDQUFDLENBQUM7SUFFcEIsU0FBUyxHQUFHLENBQUMsQ0FBQztJQUNkLElBQUksR0FBRyxDQUFDLENBQUM7SUFDVCxJQUFJLEdBQUcsQ0FBQyxDQUFDO0lBRVQsWUFBYSxJQUFZO1FBQ3hCLEtBQUssQ0FBQyxJQUFJLEVBQUUsQ0FBQyxFQUFFLEtBQUssQ0FBQyxDQUFDO0lBQ3ZCLENBQUM7Q0FDRDtBQUVEOzswR0FFMEc7QUFDMUcsTUFBTSxDQUFOLElBQVksWUFBK0I7QUFBM0MsV0FBWSxZQUFZO0lBQUcsaURBQUssQ0FBQTtJQUFFLHFEQUFPLENBQUE7QUFBQyxDQUFDLEVBQS9CLFlBQVksS0FBWixZQUFZLFFBQW1CO0FBRTNDOzt3R0FFd0c7QUFDeEcsTUFBTSxDQUFOLElBQVksV0FBb0Q7QUFBaEUsV0FBWSxXQUFXO0lBQUcsaURBQU0sQ0FBQTtJQUFFLCtDQUFLLENBQUE7SUFBRSxtREFBTyxDQUFBO0lBQUUsNkRBQVksQ0FBQTtBQUFDLENBQUMsRUFBcEQsV0FBVyxLQUFYLFdBQVcsUUFBeUM7QUFFaEU7OzhHQUU4RztBQUM5RyxNQUFNLENBQU4sSUFBWSxVQUF5QztBQUFyRCxXQUFZLFVBQVU7SUFBRyxpREFBTyxDQUFBO0lBQUUsNkNBQUssQ0FBQTtJQUFFLHVEQUFVLENBQUE7QUFBQyxDQUFDLEVBQXpDLFVBQVUsS0FBVixVQUFVLFFBQStCIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBBcHJpbCA1LCAyMDI1LiBSZXBsYWNlcyBhbGwgcHJpb3IgdmVyc2lvbnMuXG4gKlxuICogQ29weXJpZ2h0IChjKSAyMDEzLTIwMjUsIEVzb3RlcmljIFNvZnR3YXJlIExMQ1xuICpcbiAqIEludGVncmF0aW9uIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlIG9yIG90aGVyd2lzZSBjcmVhdGluZ1xuICogZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgaXMgcGVybWl0dGVkIHVuZGVyIHRoZSB0ZXJtcyBhbmRcbiAqIGNvbmRpdGlvbnMgb2YgU2VjdGlvbiAyIG9mIHRoZSBTcGluZSBFZGl0b3IgTGljZW5zZSBBZ3JlZW1lbnQ6XG4gKiBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtZWRpdG9yLWxpY2Vuc2VcbiAqXG4gKiBPdGhlcndpc2UsIGl0IGlzIHBlcm1pdHRlZCB0byBpbnRlZ3JhdGUgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmVcbiAqIG9yIG90aGVyd2lzZSBjcmVhdGUgZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgKGNvbGxlY3RpdmVseSxcbiAqIFwiUHJvZHVjdHNcIiksIHByb3ZpZGVkIHRoYXQgZWFjaCB1c2VyIG9mIHRoZSBQcm9kdWN0cyBtdXN0IG9idGFpbiB0aGVpciBvd25cbiAqIFNwaW5lIEVkaXRvciBsaWNlbnNlIGFuZCByZWRpc3RyaWJ1dGlvbiBvZiB0aGUgUHJvZHVjdHMgaW4gYW55IGZvcm0gbXVzdFxuICogaW5jbHVkZSB0aGlzIGxpY2Vuc2UgYW5kIGNvcHlyaWdodCBub3RpY2UuXG4gKlxuICogVEhFIFNQSU5FIFJVTlRJTUVTIEFSRSBQUk9WSURFRCBCWSBFU09URVJJQyBTT0ZUV0FSRSBMTEMgXCJBUyBJU1wiIEFORCBBTllcbiAqIEVYUFJFU1MgT1IgSU1QTElFRCBXQVJSQU5USUVTLCBJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgVEhFIElNUExJRURcbiAqIFdBUlJBTlRJRVMgT0YgTUVSQ0hBTlRBQklMSVRZIEFORCBGSVRORVNTIEZPUiBBIFBBUlRJQ1VMQVIgUFVSUE9TRSBBUkVcbiAqIERJU0NMQUlNRUQuIElOIE5PIEVWRU5UIFNIQUxMIEVTT1RFUklDIFNPRlRXQVJFIExMQyBCRSBMSUFCTEUgRk9SIEFOWVxuICogRElSRUNULCBJTkRJUkVDVCwgSU5DSURFTlRBTCwgU1BFQ0lBTCwgRVhFTVBMQVJZLCBPUiBDT05TRVFVRU5USUFMIERBTUFHRVNcbiAqIChJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgUFJPQ1VSRU1FTlQgT0YgU1VCU1RJVFVURSBHT09EUyBPUiBTRVJWSUNFUyxcbiAqIEJVU0lORVNTIElOVEVSUlVQVElPTiwgT1IgTE9TUyBPRiBVU0UsIERBVEEsIE9SIFBST0ZJVFMpIEhPV0VWRVIgQ0FVU0VEIEFORFxuICogT04gQU5ZIFRIRU9SWSBPRiBMSUFCSUxJVFksIFdIRVRIRVIgSU4gQ09OVFJBQ1QsIFNUUklDVCBMSUFCSUxJVFksIE9SIFRPUlRcbiAqIChJTkNMVURJTkcgTkVHTElHRU5DRSBPUiBPVEhFUldJU0UpIEFSSVNJTkcgSU4gQU5ZIFdBWSBPVVQgT0YgVEhFIFVTRSBPRlxuICogVEhFIFNQSU5FIFJVTlRJTUVTLCBFVkVOIElGIEFEVklTRUQgT0YgVEhFIFBPU1NJQklMSVRZIE9GIFNVQ0ggREFNQUdFLlxuICoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqL1xuXG5pbXBvcnQgeyBCb25lRGF0YSB9IGZyb20gXCIuL0JvbmVEYXRhLmpzXCI7XG5pbXBvcnQgeyBDb25zdHJhaW50RGF0YSB9IGZyb20gXCIuL0NvbnN0cmFpbnREYXRhLmpzXCI7XG5pbXBvcnQgeyBTbG90RGF0YSB9IGZyb20gXCIuL1Nsb3REYXRhLmpzXCI7XG5cblxuLyoqIFN0b3JlcyB0aGUgc2V0dXAgcG9zZSBmb3IgYSB7QGxpbmsgUGF0aENvbnN0cmFpbnR9LlxuICpcbiAqIFNlZSBbcGF0aCBjb25zdHJhaW50c10oaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLXBhdGgtY29uc3RyYWludHMpIGluIHRoZSBTcGluZSBVc2VyIEd1aWRlLiAqL1xuZXhwb3J0IGNsYXNzIFBhdGhDb25zdHJhaW50RGF0YSBleHRlbmRzIENvbnN0cmFpbnREYXRhIHtcblxuXHQvKiogVGhlIGJvbmVzIHRoYXQgd2lsbCBiZSBtb2RpZmllZCBieSB0aGlzIHBhdGggY29uc3RyYWludC4gKi9cblx0Ym9uZXMgPSBuZXcgQXJyYXk8Qm9uZURhdGE+KCk7XG5cblx0LyoqIFRoZSBzbG90IHdob3NlIHBhdGggYXR0YWNobWVudCB3aWxsIGJlIHVzZWQgdG8gY29uc3RyYWluZWQgdGhlIGJvbmVzLiAqL1xuXHRwcml2YXRlIF90YXJnZXQ6IFNsb3REYXRhIHwgbnVsbCA9IG51bGw7XG5cdHB1YmxpYyBzZXQgdGFyZ2V0IChzbG90RGF0YTogU2xvdERhdGEpIHsgdGhpcy5fdGFyZ2V0ID0gc2xvdERhdGE7IH1cblx0cHVibGljIGdldCB0YXJnZXQgKCkge1xuXHRcdGlmICghdGhpcy5fdGFyZ2V0KSB0aHJvdyBuZXcgRXJyb3IoXCJTbG90RGF0YSBub3Qgc2V0LlwiKVxuXHRcdGVsc2UgcmV0dXJuIHRoaXMuX3RhcmdldDtcblx0fVxuXG5cdC8qKiBUaGUgbW9kZSBmb3IgcG9zaXRpb25pbmcgdGhlIGZpcnN0IGJvbmUgb24gdGhlIHBhdGguICovXG5cdHBvc2l0aW9uTW9kZTogUG9zaXRpb25Nb2RlID0gUG9zaXRpb25Nb2RlLkZpeGVkO1xuXG5cdC8qKiBUaGUgbW9kZSBmb3IgcG9zaXRpb25pbmcgdGhlIGJvbmVzIGFmdGVyIHRoZSBmaXJzdCBib25lIG9uIHRoZSBwYXRoLiAqL1xuXHRzcGFjaW5nTW9kZTogU3BhY2luZ01vZGUgPSBTcGFjaW5nTW9kZS5GaXhlZDtcblxuXHQvKiogVGhlIG1vZGUgZm9yIGFkanVzdGluZyB0aGUgcm90YXRpb24gb2YgdGhlIGJvbmVzLiAqL1xuXHRyb3RhdGVNb2RlOiBSb3RhdGVNb2RlID0gUm90YXRlTW9kZS5DaGFpbjtcblxuXHQvKiogQW4gb2Zmc2V0IGFkZGVkIHRvIHRoZSBjb25zdHJhaW5lZCBib25lIHJvdGF0aW9uLiAqL1xuXHRvZmZzZXRSb3RhdGlvbjogbnVtYmVyID0gMDtcblxuXHQvKiogVGhlIHBvc2l0aW9uIGFsb25nIHRoZSBwYXRoLiAqL1xuXHRwb3NpdGlvbjogbnVtYmVyID0gMDtcblxuXHQvKiogVGhlIHNwYWNpbmcgYmV0d2VlbiBib25lcy4gKi9cblx0c3BhY2luZzogbnVtYmVyID0gMDtcblxuXHRtaXhSb3RhdGUgPSAwO1xuXHRtaXhYID0gMDtcblx0bWl4WSA9IDA7XG5cblx0Y29uc3RydWN0b3IgKG5hbWU6IHN0cmluZykge1xuXHRcdHN1cGVyKG5hbWUsIDAsIGZhbHNlKTtcblx0fVxufVxuXG4vKiogQ29udHJvbHMgaG93IHRoZSBmaXJzdCBib25lIGlzIHBvc2l0aW9uZWQgYWxvbmcgdGhlIHBhdGguXG4gKlxuICogU2VlIFtwb3NpdGlvbl0oaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLXBhdGgtY29uc3RyYWludHMjUG9zaXRpb24pIGluIHRoZSBTcGluZSBVc2VyIEd1aWRlLiAqL1xuZXhwb3J0IGVudW0gUG9zaXRpb25Nb2RlIHsgRml4ZWQsIFBlcmNlbnQgfVxuXG4vKiogQ29udHJvbHMgaG93IGJvbmVzIGFmdGVyIHRoZSBmaXJzdCBib25lIGFyZSBwb3NpdGlvbmVkIGFsb25nIHRoZSBwYXRoLlxuICpcbiAqIFNlZSBbc3BhY2luZ10oaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLXBhdGgtY29uc3RyYWludHMjU3BhY2luZykgaW4gdGhlIFNwaW5lIFVzZXIgR3VpZGUuICovXG5leHBvcnQgZW51bSBTcGFjaW5nTW9kZSB7IExlbmd0aCwgRml4ZWQsIFBlcmNlbnQsIFByb3BvcnRpb25hbCB9XG5cbi8qKiBDb250cm9scyBob3cgYm9uZXMgYXJlIHJvdGF0ZWQsIHRyYW5zbGF0ZWQsIGFuZCBzY2FsZWQgdG8gbWF0Y2ggdGhlIHBhdGguXG4gKlxuICogU2VlIFtyb3RhdGUgbWl4XShodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtcGF0aC1jb25zdHJhaW50cyNSb3RhdGUtbWl4KSBpbiB0aGUgU3BpbmUgVXNlciBHdWlkZS4gKi9cbmV4cG9ydCBlbnVtIFJvdGF0ZU1vZGUgeyBUYW5nZW50LCBDaGFpbiwgQ2hhaW5TY2FsZSB9XG4iXX0=