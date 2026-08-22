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
/** Stores the setup pose for an {@link IkConstraint}.
 * <p>
 * See [IK constraints](http://esotericsoftware.com/spine-ik-constraints) in the Spine User Guide. */
export class IkConstraintData extends ConstraintData {
    /** The bones that are constrained by this IK constraint. */
    bones = new Array();
    /** The bone that is the IK target. */
    _target = null;
    set target(boneData) { this._target = boneData; }
    get target() {
        if (!this._target)
            throw new Error("BoneData not set.");
        else
            return this._target;
    }
    /** Controls the bend direction of the IK bones, either 1 or -1. */
    bendDirection = 0;
    /** When true and only a single bone is being constrained, if the target is too close, the bone is scaled to reach it. */
    compress = false;
    /** When true, if the target is out of range, the parent bone is scaled to reach it. If more than one bone is being constrained
     * and the parent bone has local nonuniform scale, stretch is not applied. */
    stretch = false;
    /** When true, only a single bone is being constrained, and {@link #getCompress()} or {@link #getStretch()} is used, the bone
     * is scaled on both the X and Y axes. */
    uniform = false;
    /** A percentage (0-1) that controls the mix between the constrained and unconstrained rotations. */
    mix = 0;
    /** For two bone IK, the distance from the maximum reach of the bones that rotation will slow. */
    softness = 0;
    constructor(name) {
        super(name, 0, false);
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiSWtDb25zdHJhaW50RGF0YS5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIi4uL3NyYy9Ja0NvbnN0cmFpbnREYXRhLnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiJBQUFBOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7K0VBMkIrRTtBQUcvRSxPQUFPLEVBQUUsY0FBYyxFQUFFLE1BQU0scUJBQXFCLENBQUM7QUFHckQ7O3FHQUVxRztBQUNyRyxNQUFNLE9BQU8sZ0JBQWlCLFNBQVEsY0FBYztJQUNuRCw0REFBNEQ7SUFDNUQsS0FBSyxHQUFHLElBQUksS0FBSyxFQUFZLENBQUM7SUFFOUIsc0NBQXNDO0lBQzlCLE9BQU8sR0FBb0IsSUFBSSxDQUFDO0lBQ3hDLElBQVcsTUFBTSxDQUFFLFFBQWtCLElBQUksSUFBSSxDQUFDLE9BQU8sR0FBRyxRQUFRLENBQUMsQ0FBQyxDQUFDO0lBQ25FLElBQVcsTUFBTTtRQUNoQixJQUFJLENBQUMsSUFBSSxDQUFDLE9BQU87WUFBRSxNQUFNLElBQUksS0FBSyxDQUFDLG1CQUFtQixDQUFDLENBQUE7O1lBQ2xELE9BQU8sSUFBSSxDQUFDLE9BQU8sQ0FBQztJQUMxQixDQUFDO0lBRUQsbUVBQW1FO0lBQ25FLGFBQWEsR0FBRyxDQUFDLENBQUM7SUFFbEIseUhBQXlIO0lBQ3pILFFBQVEsR0FBRyxLQUFLLENBQUM7SUFFakI7aUZBQzZFO0lBQzdFLE9BQU8sR0FBRyxLQUFLLENBQUM7SUFFaEI7NkNBQ3lDO0lBQ3pDLE9BQU8sR0FBRyxLQUFLLENBQUM7SUFFaEIsb0dBQW9HO0lBQ3BHLEdBQUcsR0FBRyxDQUFDLENBQUM7SUFFUixpR0FBaUc7SUFDakcsUUFBUSxHQUFHLENBQUMsQ0FBQztJQUViLFlBQWEsSUFBWTtRQUN4QixLQUFLLENBQUMsSUFBSSxFQUFFLENBQUMsRUFBRSxLQUFLLENBQUMsQ0FBQztJQUN2QixDQUFDO0NBQ0QiLCJzb3VyY2VzQ29udGVudCI6WyIvKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqXG4gKiBTcGluZSBSdW50aW1lcyBMaWNlbnNlIEFncmVlbWVudFxuICogTGFzdCB1cGRhdGVkIEFwcmlsIDUsIDIwMjUuIFJlcGxhY2VzIGFsbCBwcmlvciB2ZXJzaW9ucy5cbiAqXG4gKiBDb3B5cmlnaHQgKGMpIDIwMTMtMjAyNSwgRXNvdGVyaWMgU29mdHdhcmUgTExDXG4gKlxuICogSW50ZWdyYXRpb24gb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmUgb3Igb3RoZXJ3aXNlIGNyZWF0aW5nXG4gKiBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpcyBwZXJtaXR0ZWQgdW5kZXIgdGhlIHRlcm1zIGFuZFxuICogY29uZGl0aW9ucyBvZiBTZWN0aW9uIDIgb2YgdGhlIFNwaW5lIEVkaXRvciBMaWNlbnNlIEFncmVlbWVudDpcbiAqIGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1lZGl0b3ItbGljZW5zZVxuICpcbiAqIE90aGVyd2lzZSwgaXQgaXMgcGVybWl0dGVkIHRvIGludGVncmF0ZSB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZVxuICogb3Igb3RoZXJ3aXNlIGNyZWF0ZSBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyAoY29sbGVjdGl2ZWx5LFxuICogXCJQcm9kdWN0c1wiKSwgcHJvdmlkZWQgdGhhdCBlYWNoIHVzZXIgb2YgdGhlIFByb2R1Y3RzIG11c3Qgb2J0YWluIHRoZWlyIG93blxuICogU3BpbmUgRWRpdG9yIGxpY2Vuc2UgYW5kIHJlZGlzdHJpYnV0aW9uIG9mIHRoZSBQcm9kdWN0cyBpbiBhbnkgZm9ybSBtdXN0XG4gKiBpbmNsdWRlIHRoaXMgbGljZW5zZSBhbmQgY29weXJpZ2h0IG5vdGljZS5cbiAqXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMgQVJFIFBST1ZJREVEIEJZIEVTT1RFUklDIFNPRlRXQVJFIExMQyBcIkFTIElTXCIgQU5EIEFOWVxuICogRVhQUkVTUyBPUiBJTVBMSUVEIFdBUlJBTlRJRVMsIElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBUSEUgSU1QTElFRFxuICogV0FSUkFOVElFUyBPRiBNRVJDSEFOVEFCSUxJVFkgQU5EIEZJVE5FU1MgRk9SIEEgUEFSVElDVUxBUiBQVVJQT1NFIEFSRVxuICogRElTQ0xBSU1FRC4gSU4gTk8gRVZFTlQgU0hBTEwgRVNPVEVSSUMgU09GVFdBUkUgTExDIEJFIExJQUJMRSBGT1IgQU5ZXG4gKiBESVJFQ1QsIElORElSRUNULCBJTkNJREVOVEFMLCBTUEVDSUFMLCBFWEVNUExBUlksIE9SIENPTlNFUVVFTlRJQUwgREFNQUdFU1xuICogKElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBQUk9DVVJFTUVOVCBPRiBTVUJTVElUVVRFIEdPT0RTIE9SIFNFUlZJQ0VTLFxuICogQlVTSU5FU1MgSU5URVJSVVBUSU9OLCBPUiBMT1NTIE9GIFVTRSwgREFUQSwgT1IgUFJPRklUUykgSE9XRVZFUiBDQVVTRUQgQU5EXG4gKiBPTiBBTlkgVEhFT1JZIE9GIExJQUJJTElUWSwgV0hFVEhFUiBJTiBDT05UUkFDVCwgU1RSSUNUIExJQUJJTElUWSwgT1IgVE9SVFxuICogKElOQ0xVRElORyBORUdMSUdFTkNFIE9SIE9USEVSV0lTRSkgQVJJU0lORyBJTiBBTlkgV0FZIE9VVCBPRiBUSEUgVVNFIE9GXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMsIEVWRU4gSUYgQURWSVNFRCBPRiBUSEUgUE9TU0lCSUxJVFkgT0YgU1VDSCBEQU1BR0UuXG4gKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKiovXG5cbmltcG9ydCB7IEJvbmVEYXRhIH0gZnJvbSBcIi4vQm9uZURhdGEuanNcIjtcbmltcG9ydCB7IENvbnN0cmFpbnREYXRhIH0gZnJvbSBcIi4vQ29uc3RyYWludERhdGEuanNcIjtcblxuXG4vKiogU3RvcmVzIHRoZSBzZXR1cCBwb3NlIGZvciBhbiB7QGxpbmsgSWtDb25zdHJhaW50fS5cbiAqIDxwPlxuICogU2VlIFtJSyBjb25zdHJhaW50c10oaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLWlrLWNvbnN0cmFpbnRzKSBpbiB0aGUgU3BpbmUgVXNlciBHdWlkZS4gKi9cbmV4cG9ydCBjbGFzcyBJa0NvbnN0cmFpbnREYXRhIGV4dGVuZHMgQ29uc3RyYWludERhdGEge1xuXHQvKiogVGhlIGJvbmVzIHRoYXQgYXJlIGNvbnN0cmFpbmVkIGJ5IHRoaXMgSUsgY29uc3RyYWludC4gKi9cblx0Ym9uZXMgPSBuZXcgQXJyYXk8Qm9uZURhdGE+KCk7XG5cblx0LyoqIFRoZSBib25lIHRoYXQgaXMgdGhlIElLIHRhcmdldC4gKi9cblx0cHJpdmF0ZSBfdGFyZ2V0OiBCb25lRGF0YSB8IG51bGwgPSBudWxsO1xuXHRwdWJsaWMgc2V0IHRhcmdldCAoYm9uZURhdGE6IEJvbmVEYXRhKSB7IHRoaXMuX3RhcmdldCA9IGJvbmVEYXRhOyB9XG5cdHB1YmxpYyBnZXQgdGFyZ2V0ICgpIHtcblx0XHRpZiAoIXRoaXMuX3RhcmdldCkgdGhyb3cgbmV3IEVycm9yKFwiQm9uZURhdGEgbm90IHNldC5cIilcblx0XHRlbHNlIHJldHVybiB0aGlzLl90YXJnZXQ7XG5cdH1cblxuXHQvKiogQ29udHJvbHMgdGhlIGJlbmQgZGlyZWN0aW9uIG9mIHRoZSBJSyBib25lcywgZWl0aGVyIDEgb3IgLTEuICovXG5cdGJlbmREaXJlY3Rpb24gPSAwO1xuXG5cdC8qKiBXaGVuIHRydWUgYW5kIG9ubHkgYSBzaW5nbGUgYm9uZSBpcyBiZWluZyBjb25zdHJhaW5lZCwgaWYgdGhlIHRhcmdldCBpcyB0b28gY2xvc2UsIHRoZSBib25lIGlzIHNjYWxlZCB0byByZWFjaCBpdC4gKi9cblx0Y29tcHJlc3MgPSBmYWxzZTtcblxuXHQvKiogV2hlbiB0cnVlLCBpZiB0aGUgdGFyZ2V0IGlzIG91dCBvZiByYW5nZSwgdGhlIHBhcmVudCBib25lIGlzIHNjYWxlZCB0byByZWFjaCBpdC4gSWYgbW9yZSB0aGFuIG9uZSBib25lIGlzIGJlaW5nIGNvbnN0cmFpbmVkXG5cdCAqIGFuZCB0aGUgcGFyZW50IGJvbmUgaGFzIGxvY2FsIG5vbnVuaWZvcm0gc2NhbGUsIHN0cmV0Y2ggaXMgbm90IGFwcGxpZWQuICovXG5cdHN0cmV0Y2ggPSBmYWxzZTtcblxuXHQvKiogV2hlbiB0cnVlLCBvbmx5IGEgc2luZ2xlIGJvbmUgaXMgYmVpbmcgY29uc3RyYWluZWQsIGFuZCB7QGxpbmsgI2dldENvbXByZXNzKCl9IG9yIHtAbGluayAjZ2V0U3RyZXRjaCgpfSBpcyB1c2VkLCB0aGUgYm9uZVxuXHQgKiBpcyBzY2FsZWQgb24gYm90aCB0aGUgWCBhbmQgWSBheGVzLiAqL1xuXHR1bmlmb3JtID0gZmFsc2U7XG5cblx0LyoqIEEgcGVyY2VudGFnZSAoMC0xKSB0aGF0IGNvbnRyb2xzIHRoZSBtaXggYmV0d2VlbiB0aGUgY29uc3RyYWluZWQgYW5kIHVuY29uc3RyYWluZWQgcm90YXRpb25zLiAqL1xuXHRtaXggPSAwO1xuXG5cdC8qKiBGb3IgdHdvIGJvbmUgSUssIHRoZSBkaXN0YW5jZSBmcm9tIHRoZSBtYXhpbXVtIHJlYWNoIG9mIHRoZSBib25lcyB0aGF0IHJvdGF0aW9uIHdpbGwgc2xvdy4gKi9cblx0c29mdG5lc3MgPSAwO1xuXG5cdGNvbnN0cnVjdG9yIChuYW1lOiBzdHJpbmcpIHtcblx0XHRzdXBlcihuYW1lLCAwLCBmYWxzZSk7XG5cdH1cbn1cbiJdfQ==