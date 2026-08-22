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
/** Stores mix (crossfade) durations to be applied when {@link AnimationState} animations are changed. */
export class AnimationStateData {
    /** The SkeletonData to look up animations when they are specified by name. */
    skeletonData;
    animationToMixTime = {};
    /** The mix duration to use when no mix duration has been defined between two animations. */
    defaultMix = 0;
    constructor(skeletonData) {
        if (!skeletonData)
            throw new Error("skeletonData cannot be null.");
        this.skeletonData = skeletonData;
    }
    /** Sets a mix duration by animation name.
     *
     * See {@link #setMixWith()}. */
    setMix(fromName, toName, duration) {
        let from = this.skeletonData.findAnimation(fromName);
        if (!from)
            throw new Error("Animation not found: " + fromName);
        let to = this.skeletonData.findAnimation(toName);
        if (!to)
            throw new Error("Animation not found: " + toName);
        this.setMixWith(from, to, duration);
    }
    /** Sets the mix duration when changing from the specified animation to the other.
     *
     * See {@link TrackEntry#mixDuration}. */
    setMixWith(from, to, duration) {
        if (!from)
            throw new Error("from cannot be null.");
        if (!to)
            throw new Error("to cannot be null.");
        let key = from.name + "." + to.name;
        this.animationToMixTime[key] = duration;
    }
    /** Returns the mix duration to use when changing from the specified animation to the other, or the {@link #defaultMix} if
      * no mix duration has been set. */
    getMix(from, to) {
        let key = from.name + "." + to.name;
        let value = this.animationToMixTime[key];
        return value === undefined ? this.defaultMix : value;
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiQW5pbWF0aW9uU3RhdGVEYXRhLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsiLi4vc3JjL0FuaW1hdGlvblN0YXRlRGF0YS50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiQUFBQTs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OytFQTJCK0U7QUFPL0UseUdBQXlHO0FBQ3pHLE1BQU0sT0FBTyxrQkFBa0I7SUFDOUIsOEVBQThFO0lBQzlFLFlBQVksQ0FBZTtJQUUzQixrQkFBa0IsR0FBc0IsRUFBRSxDQUFDO0lBRTNDLDRGQUE0RjtJQUM1RixVQUFVLEdBQUcsQ0FBQyxDQUFDO0lBRWYsWUFBYSxZQUEwQjtRQUN0QyxJQUFJLENBQUMsWUFBWTtZQUFFLE1BQU0sSUFBSSxLQUFLLENBQUMsOEJBQThCLENBQUMsQ0FBQztRQUNuRSxJQUFJLENBQUMsWUFBWSxHQUFHLFlBQVksQ0FBQztJQUNsQyxDQUFDO0lBRUQ7O29DQUVnQztJQUNoQyxNQUFNLENBQUUsUUFBZ0IsRUFBRSxNQUFjLEVBQUUsUUFBZ0I7UUFDekQsSUFBSSxJQUFJLEdBQUcsSUFBSSxDQUFDLFlBQVksQ0FBQyxhQUFhLENBQUMsUUFBUSxDQUFDLENBQUM7UUFDckQsSUFBSSxDQUFDLElBQUk7WUFBRSxNQUFNLElBQUksS0FBSyxDQUFDLHVCQUF1QixHQUFHLFFBQVEsQ0FBQyxDQUFDO1FBQy9ELElBQUksRUFBRSxHQUFHLElBQUksQ0FBQyxZQUFZLENBQUMsYUFBYSxDQUFDLE1BQU0sQ0FBQyxDQUFDO1FBQ2pELElBQUksQ0FBQyxFQUFFO1lBQUUsTUFBTSxJQUFJLEtBQUssQ0FBQyx1QkFBdUIsR0FBRyxNQUFNLENBQUMsQ0FBQztRQUMzRCxJQUFJLENBQUMsVUFBVSxDQUFDLElBQUksRUFBRSxFQUFFLEVBQUUsUUFBUSxDQUFDLENBQUM7SUFDckMsQ0FBQztJQUVEOzs2Q0FFeUM7SUFDekMsVUFBVSxDQUFFLElBQWUsRUFBRSxFQUFhLEVBQUUsUUFBZ0I7UUFDM0QsSUFBSSxDQUFDLElBQUk7WUFBRSxNQUFNLElBQUksS0FBSyxDQUFDLHNCQUFzQixDQUFDLENBQUM7UUFDbkQsSUFBSSxDQUFDLEVBQUU7WUFBRSxNQUFNLElBQUksS0FBSyxDQUFDLG9CQUFvQixDQUFDLENBQUM7UUFDL0MsSUFBSSxHQUFHLEdBQUcsSUFBSSxDQUFDLElBQUksR0FBRyxHQUFHLEdBQUcsRUFBRSxDQUFDLElBQUksQ0FBQztRQUNwQyxJQUFJLENBQUMsa0JBQWtCLENBQUMsR0FBRyxDQUFDLEdBQUcsUUFBUSxDQUFDO0lBQ3pDLENBQUM7SUFFRDt3Q0FDb0M7SUFDcEMsTUFBTSxDQUFFLElBQWUsRUFBRSxFQUFhO1FBQ3JDLElBQUksR0FBRyxHQUFHLElBQUksQ0FBQyxJQUFJLEdBQUcsR0FBRyxHQUFHLEVBQUUsQ0FBQyxJQUFJLENBQUM7UUFDcEMsSUFBSSxLQUFLLEdBQUcsSUFBSSxDQUFDLGtCQUFrQixDQUFDLEdBQUcsQ0FBQyxDQUFDO1FBQ3pDLE9BQU8sS0FBSyxLQUFLLFNBQVMsQ0FBQyxDQUFDLENBQUMsSUFBSSxDQUFDLFVBQVUsQ0FBQyxDQUFDLENBQUMsS0FBSyxDQUFDO0lBQ3RELENBQUM7Q0FDRCIsInNvdXJjZXNDb250ZW50IjpbIi8qKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKipcbiAqIFNwaW5lIFJ1bnRpbWVzIExpY2Vuc2UgQWdyZWVtZW50XG4gKiBMYXN0IHVwZGF0ZWQgQXByaWwgNSwgMjAyNS4gUmVwbGFjZXMgYWxsIHByaW9yIHZlcnNpb25zLlxuICpcbiAqIENvcHlyaWdodCAoYykgMjAxMy0yMDI1LCBFc290ZXJpYyBTb2Z0d2FyZSBMTENcbiAqXG4gKiBJbnRlZ3JhdGlvbiBvZiB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZSBvciBvdGhlcndpc2UgY3JlYXRpbmdcbiAqIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGlzIHBlcm1pdHRlZCB1bmRlciB0aGUgdGVybXMgYW5kXG4gKiBjb25kaXRpb25zIG9mIFNlY3Rpb24gMiBvZiB0aGUgU3BpbmUgRWRpdG9yIExpY2Vuc2UgQWdyZWVtZW50OlxuICogaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLWVkaXRvci1saWNlbnNlXG4gKlxuICogT3RoZXJ3aXNlLCBpdCBpcyBwZXJtaXR0ZWQgdG8gaW50ZWdyYXRlIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlXG4gKiBvciBvdGhlcndpc2UgY3JlYXRlIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIChjb2xsZWN0aXZlbHksXG4gKiBcIlByb2R1Y3RzXCIpLCBwcm92aWRlZCB0aGF0IGVhY2ggdXNlciBvZiB0aGUgUHJvZHVjdHMgbXVzdCBvYnRhaW4gdGhlaXIgb3duXG4gKiBTcGluZSBFZGl0b3IgbGljZW5zZSBhbmQgcmVkaXN0cmlidXRpb24gb2YgdGhlIFByb2R1Y3RzIGluIGFueSBmb3JtIG11c3RcbiAqIGluY2x1ZGUgdGhpcyBsaWNlbnNlIGFuZCBjb3B5cmlnaHQgbm90aWNlLlxuICpcbiAqIFRIRSBTUElORSBSVU5USU1FUyBBUkUgUFJPVklERUQgQlkgRVNPVEVSSUMgU09GVFdBUkUgTExDIFwiQVMgSVNcIiBBTkQgQU5ZXG4gKiBFWFBSRVNTIE9SIElNUExJRUQgV0FSUkFOVElFUywgSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFRIRSBJTVBMSUVEXG4gKiBXQVJSQU5USUVTIE9GIE1FUkNIQU5UQUJJTElUWSBBTkQgRklUTkVTUyBGT1IgQSBQQVJUSUNVTEFSIFBVUlBPU0UgQVJFXG4gKiBESVNDTEFJTUVELiBJTiBOTyBFVkVOVCBTSEFMTCBFU09URVJJQyBTT0ZUV0FSRSBMTEMgQkUgTElBQkxFIEZPUiBBTllcbiAqIERJUkVDVCwgSU5ESVJFQ1QsIElOQ0lERU5UQUwsIFNQRUNJQUwsIEVYRU1QTEFSWSwgT1IgQ09OU0VRVUVOVElBTCBEQU1BR0VTXG4gKiAoSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFBST0NVUkVNRU5UIE9GIFNVQlNUSVRVVEUgR09PRFMgT1IgU0VSVklDRVMsXG4gKiBCVVNJTkVTUyBJTlRFUlJVUFRJT04sIE9SIExPU1MgT0YgVVNFLCBEQVRBLCBPUiBQUk9GSVRTKSBIT1dFVkVSIENBVVNFRCBBTkRcbiAqIE9OIEFOWSBUSEVPUlkgT0YgTElBQklMSVRZLCBXSEVUSEVSIElOIENPTlRSQUNULCBTVFJJQ1QgTElBQklMSVRZLCBPUiBUT1JUXG4gKiAoSU5DTFVESU5HIE5FR0xJR0VOQ0UgT1IgT1RIRVJXSVNFKSBBUklTSU5HIElOIEFOWSBXQVkgT1VUIE9GIFRIRSBVU0UgT0ZcbiAqIFRIRSBTUElORSBSVU5USU1FUywgRVZFTiBJRiBBRFZJU0VEIE9GIFRIRSBQT1NTSUJJTElUWSBPRiBTVUNIIERBTUFHRS5cbiAqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKi9cblxuaW1wb3J0IHsgQW5pbWF0aW9uIH0gZnJvbSBcIi4vQW5pbWF0aW9uLmpzXCI7XG5pbXBvcnQgeyBTa2VsZXRvbkRhdGEgfSBmcm9tIFwiLi9Ta2VsZXRvbkRhdGEuanNcIjtcbmltcG9ydCB7IFN0cmluZ01hcCB9IGZyb20gXCIuL1V0aWxzLmpzXCI7XG5cblxuLyoqIFN0b3JlcyBtaXggKGNyb3NzZmFkZSkgZHVyYXRpb25zIHRvIGJlIGFwcGxpZWQgd2hlbiB7QGxpbmsgQW5pbWF0aW9uU3RhdGV9IGFuaW1hdGlvbnMgYXJlIGNoYW5nZWQuICovXG5leHBvcnQgY2xhc3MgQW5pbWF0aW9uU3RhdGVEYXRhIHtcblx0LyoqIFRoZSBTa2VsZXRvbkRhdGEgdG8gbG9vayB1cCBhbmltYXRpb25zIHdoZW4gdGhleSBhcmUgc3BlY2lmaWVkIGJ5IG5hbWUuICovXG5cdHNrZWxldG9uRGF0YTogU2tlbGV0b25EYXRhO1xuXG5cdGFuaW1hdGlvblRvTWl4VGltZTogU3RyaW5nTWFwPG51bWJlcj4gPSB7fTtcblxuXHQvKiogVGhlIG1peCBkdXJhdGlvbiB0byB1c2Ugd2hlbiBubyBtaXggZHVyYXRpb24gaGFzIGJlZW4gZGVmaW5lZCBiZXR3ZWVuIHR3byBhbmltYXRpb25zLiAqL1xuXHRkZWZhdWx0TWl4ID0gMDtcblxuXHRjb25zdHJ1Y3RvciAoc2tlbGV0b25EYXRhOiBTa2VsZXRvbkRhdGEpIHtcblx0XHRpZiAoIXNrZWxldG9uRGF0YSkgdGhyb3cgbmV3IEVycm9yKFwic2tlbGV0b25EYXRhIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHR0aGlzLnNrZWxldG9uRGF0YSA9IHNrZWxldG9uRGF0YTtcblx0fVxuXG5cdC8qKiBTZXRzIGEgbWl4IGR1cmF0aW9uIGJ5IGFuaW1hdGlvbiBuYW1lLlxuXHQgKlxuXHQgKiBTZWUge0BsaW5rICNzZXRNaXhXaXRoKCl9LiAqL1xuXHRzZXRNaXggKGZyb21OYW1lOiBzdHJpbmcsIHRvTmFtZTogc3RyaW5nLCBkdXJhdGlvbjogbnVtYmVyKSB7XG5cdFx0bGV0IGZyb20gPSB0aGlzLnNrZWxldG9uRGF0YS5maW5kQW5pbWF0aW9uKGZyb21OYW1lKTtcblx0XHRpZiAoIWZyb20pIHRocm93IG5ldyBFcnJvcihcIkFuaW1hdGlvbiBub3QgZm91bmQ6IFwiICsgZnJvbU5hbWUpO1xuXHRcdGxldCB0byA9IHRoaXMuc2tlbGV0b25EYXRhLmZpbmRBbmltYXRpb24odG9OYW1lKTtcblx0XHRpZiAoIXRvKSB0aHJvdyBuZXcgRXJyb3IoXCJBbmltYXRpb24gbm90IGZvdW5kOiBcIiArIHRvTmFtZSk7XG5cdFx0dGhpcy5zZXRNaXhXaXRoKGZyb20sIHRvLCBkdXJhdGlvbik7XG5cdH1cblxuXHQvKiogU2V0cyB0aGUgbWl4IGR1cmF0aW9uIHdoZW4gY2hhbmdpbmcgZnJvbSB0aGUgc3BlY2lmaWVkIGFuaW1hdGlvbiB0byB0aGUgb3RoZXIuXG5cdCAqXG5cdCAqIFNlZSB7QGxpbmsgVHJhY2tFbnRyeSNtaXhEdXJhdGlvbn0uICovXG5cdHNldE1peFdpdGggKGZyb206IEFuaW1hdGlvbiwgdG86IEFuaW1hdGlvbiwgZHVyYXRpb246IG51bWJlcikge1xuXHRcdGlmICghZnJvbSkgdGhyb3cgbmV3IEVycm9yKFwiZnJvbSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0aWYgKCF0bykgdGhyb3cgbmV3IEVycm9yKFwidG8gY2Fubm90IGJlIG51bGwuXCIpO1xuXHRcdGxldCBrZXkgPSBmcm9tLm5hbWUgKyBcIi5cIiArIHRvLm5hbWU7XG5cdFx0dGhpcy5hbmltYXRpb25Ub01peFRpbWVba2V5XSA9IGR1cmF0aW9uO1xuXHR9XG5cblx0LyoqIFJldHVybnMgdGhlIG1peCBkdXJhdGlvbiB0byB1c2Ugd2hlbiBjaGFuZ2luZyBmcm9tIHRoZSBzcGVjaWZpZWQgYW5pbWF0aW9uIHRvIHRoZSBvdGhlciwgb3IgdGhlIHtAbGluayAjZGVmYXVsdE1peH0gaWZcblx0ICAqIG5vIG1peCBkdXJhdGlvbiBoYXMgYmVlbiBzZXQuICovXG5cdGdldE1peCAoZnJvbTogQW5pbWF0aW9uLCB0bzogQW5pbWF0aW9uKSB7XG5cdFx0bGV0IGtleSA9IGZyb20ubmFtZSArIFwiLlwiICsgdG8ubmFtZTtcblx0XHRsZXQgdmFsdWUgPSB0aGlzLmFuaW1hdGlvblRvTWl4VGltZVtrZXldO1xuXHRcdHJldHVybiB2YWx1ZSA9PT0gdW5kZWZpbmVkID8gdGhpcy5kZWZhdWx0TWl4IDogdmFsdWU7XG5cdH1cbn1cbiJdfQ==