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
import { Color } from "./Utils.js";
/** Stores the setup pose for a {@link Bone}. */
export class BoneData {
    /** The index of the bone in {@link Skeleton#getBones()}. */
    index = 0;
    /** The name of the bone, which is unique across all bones in the skeleton. */
    name;
    /** @returns May be null. */
    parent = null;
    /** The bone's length. */
    length = 0;
    /** The local x translation. */
    x = 0;
    /** The local y translation. */
    y = 0;
    /** The local rotation in degrees, counter clockwise. */
    rotation = 0;
    /** The local scaleX. */
    scaleX = 1;
    /** The local scaleY. */
    scaleY = 1;
    /** The local shearX. */
    shearX = 0;
    /** The local shearX. */
    shearY = 0;
    /** The transform mode for how parent world transforms affect this bone. */
    inherit = Inherit.Normal;
    /** When true, {@link Skeleton#updateWorldTransform()} only updates this bone if the {@link Skeleton#skin} contains this
      * bone.
      * @see Skin#bones */
    skinRequired = false;
    /** The color of the bone as it was in Spine. Available only when nonessential data was exported. Bones are not usually
     * rendered at runtime. */
    color = new Color();
    /** The bone icon as it was in Spine, or null if nonessential data was not exported. */
    icon;
    /** False if the bone was hidden in Spine and nonessential data was exported. Does not affect runtime rendering. */
    visible = false;
    constructor(index, name, parent) {
        if (index < 0)
            throw new Error("index must be >= 0.");
        if (!name)
            throw new Error("name cannot be null.");
        this.index = index;
        this.name = name;
        this.parent = parent;
    }
}
/** Determines how a bone inherits world transforms from parent bones. */
export var Inherit;
(function (Inherit) {
    Inherit[Inherit["Normal"] = 0] = "Normal";
    Inherit[Inherit["OnlyTranslation"] = 1] = "OnlyTranslation";
    Inherit[Inherit["NoRotationOrReflection"] = 2] = "NoRotationOrReflection";
    Inherit[Inherit["NoScale"] = 3] = "NoScale";
    Inherit[Inherit["NoScaleOrReflection"] = 4] = "NoScaleOrReflection";
})(Inherit || (Inherit = {}));
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiQm9uZURhdGEuanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyIuLi9zcmMvQm9uZURhdGEudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OzsrRUEyQitFO0FBRS9FLE9BQU8sRUFBRSxLQUFLLEVBQUUsTUFBTSxZQUFZLENBQUM7QUFFbkMsZ0RBQWdEO0FBQ2hELE1BQU0sT0FBTyxRQUFRO0lBQ3BCLDREQUE0RDtJQUM1RCxLQUFLLEdBQVcsQ0FBQyxDQUFDO0lBRWxCLDhFQUE4RTtJQUM5RSxJQUFJLENBQVM7SUFFYiw0QkFBNEI7SUFDNUIsTUFBTSxHQUFvQixJQUFJLENBQUM7SUFFL0IseUJBQXlCO0lBQ3pCLE1BQU0sR0FBVyxDQUFDLENBQUM7SUFFbkIsK0JBQStCO0lBQy9CLENBQUMsR0FBRyxDQUFDLENBQUM7SUFFTiwrQkFBK0I7SUFDL0IsQ0FBQyxHQUFHLENBQUMsQ0FBQztJQUVOLHdEQUF3RDtJQUN4RCxRQUFRLEdBQUcsQ0FBQyxDQUFDO0lBRWIsd0JBQXdCO0lBQ3hCLE1BQU0sR0FBRyxDQUFDLENBQUM7SUFFWCx3QkFBd0I7SUFDeEIsTUFBTSxHQUFHLENBQUMsQ0FBQztJQUVYLHdCQUF3QjtJQUN4QixNQUFNLEdBQUcsQ0FBQyxDQUFDO0lBRVgsd0JBQXdCO0lBQ3hCLE1BQU0sR0FBRyxDQUFDLENBQUM7SUFFWCwyRUFBMkU7SUFDM0UsT0FBTyxHQUFHLE9BQU8sQ0FBQyxNQUFNLENBQUM7SUFFekI7OzBCQUVzQjtJQUN0QixZQUFZLEdBQUcsS0FBSyxDQUFDO0lBRXJCOzhCQUMwQjtJQUMxQixLQUFLLEdBQUcsSUFBSSxLQUFLLEVBQUUsQ0FBQztJQUVwQix1RkFBdUY7SUFDdkYsSUFBSSxDQUFVO0lBRWQsbUhBQW1IO0lBQ25ILE9BQU8sR0FBRyxLQUFLLENBQUM7SUFFaEIsWUFBYSxLQUFhLEVBQUUsSUFBWSxFQUFFLE1BQXVCO1FBQ2hFLElBQUksS0FBSyxHQUFHLENBQUM7WUFBRSxNQUFNLElBQUksS0FBSyxDQUFDLHFCQUFxQixDQUFDLENBQUM7UUFDdEQsSUFBSSxDQUFDLElBQUk7WUFBRSxNQUFNLElBQUksS0FBSyxDQUFDLHNCQUFzQixDQUFDLENBQUM7UUFDbkQsSUFBSSxDQUFDLEtBQUssR0FBRyxLQUFLLENBQUM7UUFDbkIsSUFBSSxDQUFDLElBQUksR0FBRyxJQUFJLENBQUM7UUFDakIsSUFBSSxDQUFDLE1BQU0sR0FBRyxNQUFNLENBQUM7SUFDdEIsQ0FBQztDQUNEO0FBRUQseUVBQXlFO0FBQ3pFLE1BQU0sQ0FBTixJQUFZLE9BQXlGO0FBQXJHLFdBQVksT0FBTztJQUFHLHlDQUFNLENBQUE7SUFBRSwyREFBZSxDQUFBO0lBQUUseUVBQXNCLENBQUE7SUFBRSwyQ0FBTyxDQUFBO0lBQUUsbUVBQW1CLENBQUE7QUFBQyxDQUFDLEVBQXpGLE9BQU8sS0FBUCxPQUFPLFFBQWtGIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBBcHJpbCA1LCAyMDI1LiBSZXBsYWNlcyBhbGwgcHJpb3IgdmVyc2lvbnMuXG4gKlxuICogQ29weXJpZ2h0IChjKSAyMDEzLTIwMjUsIEVzb3RlcmljIFNvZnR3YXJlIExMQ1xuICpcbiAqIEludGVncmF0aW9uIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlIG9yIG90aGVyd2lzZSBjcmVhdGluZ1xuICogZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgaXMgcGVybWl0dGVkIHVuZGVyIHRoZSB0ZXJtcyBhbmRcbiAqIGNvbmRpdGlvbnMgb2YgU2VjdGlvbiAyIG9mIHRoZSBTcGluZSBFZGl0b3IgTGljZW5zZSBBZ3JlZW1lbnQ6XG4gKiBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtZWRpdG9yLWxpY2Vuc2VcbiAqXG4gKiBPdGhlcndpc2UsIGl0IGlzIHBlcm1pdHRlZCB0byBpbnRlZ3JhdGUgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmVcbiAqIG9yIG90aGVyd2lzZSBjcmVhdGUgZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgKGNvbGxlY3RpdmVseSxcbiAqIFwiUHJvZHVjdHNcIiksIHByb3ZpZGVkIHRoYXQgZWFjaCB1c2VyIG9mIHRoZSBQcm9kdWN0cyBtdXN0IG9idGFpbiB0aGVpciBvd25cbiAqIFNwaW5lIEVkaXRvciBsaWNlbnNlIGFuZCByZWRpc3RyaWJ1dGlvbiBvZiB0aGUgUHJvZHVjdHMgaW4gYW55IGZvcm0gbXVzdFxuICogaW5jbHVkZSB0aGlzIGxpY2Vuc2UgYW5kIGNvcHlyaWdodCBub3RpY2UuXG4gKlxuICogVEhFIFNQSU5FIFJVTlRJTUVTIEFSRSBQUk9WSURFRCBCWSBFU09URVJJQyBTT0ZUV0FSRSBMTEMgXCJBUyBJU1wiIEFORCBBTllcbiAqIEVYUFJFU1MgT1IgSU1QTElFRCBXQVJSQU5USUVTLCBJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgVEhFIElNUExJRURcbiAqIFdBUlJBTlRJRVMgT0YgTUVSQ0hBTlRBQklMSVRZIEFORCBGSVRORVNTIEZPUiBBIFBBUlRJQ1VMQVIgUFVSUE9TRSBBUkVcbiAqIERJU0NMQUlNRUQuIElOIE5PIEVWRU5UIFNIQUxMIEVTT1RFUklDIFNPRlRXQVJFIExMQyBCRSBMSUFCTEUgRk9SIEFOWVxuICogRElSRUNULCBJTkRJUkVDVCwgSU5DSURFTlRBTCwgU1BFQ0lBTCwgRVhFTVBMQVJZLCBPUiBDT05TRVFVRU5USUFMIERBTUFHRVNcbiAqIChJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgUFJPQ1VSRU1FTlQgT0YgU1VCU1RJVFVURSBHT09EUyBPUiBTRVJWSUNFUyxcbiAqIEJVU0lORVNTIElOVEVSUlVQVElPTiwgT1IgTE9TUyBPRiBVU0UsIERBVEEsIE9SIFBST0ZJVFMpIEhPV0VWRVIgQ0FVU0VEIEFORFxuICogT04gQU5ZIFRIRU9SWSBPRiBMSUFCSUxJVFksIFdIRVRIRVIgSU4gQ09OVFJBQ1QsIFNUUklDVCBMSUFCSUxJVFksIE9SIFRPUlRcbiAqIChJTkNMVURJTkcgTkVHTElHRU5DRSBPUiBPVEhFUldJU0UpIEFSSVNJTkcgSU4gQU5ZIFdBWSBPVVQgT0YgVEhFIFVTRSBPRlxuICogVEhFIFNQSU5FIFJVTlRJTUVTLCBFVkVOIElGIEFEVklTRUQgT0YgVEhFIFBPU1NJQklMSVRZIE9GIFNVQ0ggREFNQUdFLlxuICoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqL1xuXG5pbXBvcnQgeyBDb2xvciB9IGZyb20gXCIuL1V0aWxzLmpzXCI7XG5cbi8qKiBTdG9yZXMgdGhlIHNldHVwIHBvc2UgZm9yIGEge0BsaW5rIEJvbmV9LiAqL1xuZXhwb3J0IGNsYXNzIEJvbmVEYXRhIHtcblx0LyoqIFRoZSBpbmRleCBvZiB0aGUgYm9uZSBpbiB7QGxpbmsgU2tlbGV0b24jZ2V0Qm9uZXMoKX0uICovXG5cdGluZGV4OiBudW1iZXIgPSAwO1xuXG5cdC8qKiBUaGUgbmFtZSBvZiB0aGUgYm9uZSwgd2hpY2ggaXMgdW5pcXVlIGFjcm9zcyBhbGwgYm9uZXMgaW4gdGhlIHNrZWxldG9uLiAqL1xuXHRuYW1lOiBzdHJpbmc7XG5cblx0LyoqIEByZXR1cm5zIE1heSBiZSBudWxsLiAqL1xuXHRwYXJlbnQ6IEJvbmVEYXRhIHwgbnVsbCA9IG51bGw7XG5cblx0LyoqIFRoZSBib25lJ3MgbGVuZ3RoLiAqL1xuXHRsZW5ndGg6IG51bWJlciA9IDA7XG5cblx0LyoqIFRoZSBsb2NhbCB4IHRyYW5zbGF0aW9uLiAqL1xuXHR4ID0gMDtcblxuXHQvKiogVGhlIGxvY2FsIHkgdHJhbnNsYXRpb24uICovXG5cdHkgPSAwO1xuXG5cdC8qKiBUaGUgbG9jYWwgcm90YXRpb24gaW4gZGVncmVlcywgY291bnRlciBjbG9ja3dpc2UuICovXG5cdHJvdGF0aW9uID0gMDtcblxuXHQvKiogVGhlIGxvY2FsIHNjYWxlWC4gKi9cblx0c2NhbGVYID0gMTtcblxuXHQvKiogVGhlIGxvY2FsIHNjYWxlWS4gKi9cblx0c2NhbGVZID0gMTtcblxuXHQvKiogVGhlIGxvY2FsIHNoZWFyWC4gKi9cblx0c2hlYXJYID0gMDtcblxuXHQvKiogVGhlIGxvY2FsIHNoZWFyWC4gKi9cblx0c2hlYXJZID0gMDtcblxuXHQvKiogVGhlIHRyYW5zZm9ybSBtb2RlIGZvciBob3cgcGFyZW50IHdvcmxkIHRyYW5zZm9ybXMgYWZmZWN0IHRoaXMgYm9uZS4gKi9cblx0aW5oZXJpdCA9IEluaGVyaXQuTm9ybWFsO1xuXG5cdC8qKiBXaGVuIHRydWUsIHtAbGluayBTa2VsZXRvbiN1cGRhdGVXb3JsZFRyYW5zZm9ybSgpfSBvbmx5IHVwZGF0ZXMgdGhpcyBib25lIGlmIHRoZSB7QGxpbmsgU2tlbGV0b24jc2tpbn0gY29udGFpbnMgdGhpc1xuXHQgICogYm9uZS5cblx0ICAqIEBzZWUgU2tpbiNib25lcyAqL1xuXHRza2luUmVxdWlyZWQgPSBmYWxzZTtcblxuXHQvKiogVGhlIGNvbG9yIG9mIHRoZSBib25lIGFzIGl0IHdhcyBpbiBTcGluZS4gQXZhaWxhYmxlIG9ubHkgd2hlbiBub25lc3NlbnRpYWwgZGF0YSB3YXMgZXhwb3J0ZWQuIEJvbmVzIGFyZSBub3QgdXN1YWxseVxuXHQgKiByZW5kZXJlZCBhdCBydW50aW1lLiAqL1xuXHRjb2xvciA9IG5ldyBDb2xvcigpO1xuXG5cdC8qKiBUaGUgYm9uZSBpY29uIGFzIGl0IHdhcyBpbiBTcGluZSwgb3IgbnVsbCBpZiBub25lc3NlbnRpYWwgZGF0YSB3YXMgbm90IGV4cG9ydGVkLiAqL1xuXHRpY29uPzogc3RyaW5nO1xuXG5cdC8qKiBGYWxzZSBpZiB0aGUgYm9uZSB3YXMgaGlkZGVuIGluIFNwaW5lIGFuZCBub25lc3NlbnRpYWwgZGF0YSB3YXMgZXhwb3J0ZWQuIERvZXMgbm90IGFmZmVjdCBydW50aW1lIHJlbmRlcmluZy4gKi9cblx0dmlzaWJsZSA9IGZhbHNlO1xuXG5cdGNvbnN0cnVjdG9yIChpbmRleDogbnVtYmVyLCBuYW1lOiBzdHJpbmcsIHBhcmVudDogQm9uZURhdGEgfCBudWxsKSB7XG5cdFx0aWYgKGluZGV4IDwgMCkgdGhyb3cgbmV3IEVycm9yKFwiaW5kZXggbXVzdCBiZSA+PSAwLlwiKTtcblx0XHRpZiAoIW5hbWUpIHRocm93IG5ldyBFcnJvcihcIm5hbWUgY2Fubm90IGJlIG51bGwuXCIpO1xuXHRcdHRoaXMuaW5kZXggPSBpbmRleDtcblx0XHR0aGlzLm5hbWUgPSBuYW1lO1xuXHRcdHRoaXMucGFyZW50ID0gcGFyZW50O1xuXHR9XG59XG5cbi8qKiBEZXRlcm1pbmVzIGhvdyBhIGJvbmUgaW5oZXJpdHMgd29ybGQgdHJhbnNmb3JtcyBmcm9tIHBhcmVudCBib25lcy4gKi9cbmV4cG9ydCBlbnVtIEluaGVyaXQgeyBOb3JtYWwsIE9ubHlUcmFuc2xhdGlvbiwgTm9Sb3RhdGlvbk9yUmVmbGVjdGlvbiwgTm9TY2FsZSwgTm9TY2FsZU9yUmVmbGVjdGlvbiB9XG4iXX0=