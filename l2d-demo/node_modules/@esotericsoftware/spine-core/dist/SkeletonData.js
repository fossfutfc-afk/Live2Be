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
/** Stores the setup pose and all of the stateless data for a skeleton.
 *
 * See [Data objects](http://esotericsoftware.com/spine-runtime-architecture#Data-objects) in the Spine Runtimes
 * Guide. */
export class SkeletonData {
    /** The skeleton's name, which by default is the name of the skeleton data file, if possible. May be null. */
    name = null;
    /** The skeleton's bones, sorted parent first. The root bone is always the first bone. */
    bones = new Array(); // Ordered parents first.
    /** The skeleton's slots in the setup pose draw order. */
    slots = new Array(); // Setup pose draw order.
    skins = new Array();
    /** The skeleton's default skin. By default this skin contains all attachments that were not in a skin in Spine.
     *
     * See {@link Skeleton#getAttachmentByName()}.
     * May be null. */
    defaultSkin = null;
    /** The skeleton's events. */
    events = new Array();
    /** The skeleton's animations. */
    animations = new Array();
    /** The skeleton's IK constraints. */
    ikConstraints = new Array();
    /** The skeleton's transform constraints. */
    transformConstraints = new Array();
    /** The skeleton's path constraints. */
    pathConstraints = new Array();
    /** The skeleton's physics constraints. */
    physicsConstraints = new Array();
    /** The X coordinate of the skeleton's axis aligned bounding box in the setup pose. */
    x = 0;
    /** The Y coordinate of the skeleton's axis aligned bounding box in the setup pose. */
    y = 0;
    /** The width of the skeleton's axis aligned bounding box in the setup pose. */
    width = 0;
    /** The height of the skeleton's axis aligned bounding box in the setup pose. */
    height = 0;
    /** Baseline scale factor for applying distance-dependent effects on non-scalable properties, such as angle or scale. Default
     * is 100. */
    referenceScale = 100;
    /** The Spine version used to export the skeleton data, or null. */
    version = null;
    /** The skeleton data hash. This value will change if any of the skeleton data has changed. May be null. */
    hash = null;
    // Nonessential
    /** The dopesheet FPS in Spine. Available only when nonessential data was exported. */
    fps = 0;
    /** The path to the images directory as defined in Spine. Available only when nonessential data was exported. May be null. */
    imagesPath = null;
    /** The path to the audio directory as defined in Spine. Available only when nonessential data was exported. May be null. */
    audioPath = null;
    /** Finds a bone by comparing each bone's name. It is more efficient to cache the results of this method than to call it
     * multiple times.
     * @returns May be null. */
    findBone(boneName) {
        if (!boneName)
            throw new Error("boneName cannot be null.");
        let bones = this.bones;
        for (let i = 0, n = bones.length; i < n; i++) {
            let bone = bones[i];
            if (bone.name == boneName)
                return bone;
        }
        return null;
    }
    /** Finds a slot by comparing each slot's name. It is more efficient to cache the results of this method than to call it
     * multiple times.
     * @returns May be null. */
    findSlot(slotName) {
        if (!slotName)
            throw new Error("slotName cannot be null.");
        let slots = this.slots;
        for (let i = 0, n = slots.length; i < n; i++) {
            let slot = slots[i];
            if (slot.name == slotName)
                return slot;
        }
        return null;
    }
    /** Finds a skin by comparing each skin's name. It is more efficient to cache the results of this method than to call it
     * multiple times.
     * @returns May be null. */
    findSkin(skinName) {
        if (!skinName)
            throw new Error("skinName cannot be null.");
        let skins = this.skins;
        for (let i = 0, n = skins.length; i < n; i++) {
            let skin = skins[i];
            if (skin.name == skinName)
                return skin;
        }
        return null;
    }
    /** Finds an event by comparing each events's name. It is more efficient to cache the results of this method than to call it
     * multiple times.
     * @returns May be null. */
    findEvent(eventDataName) {
        if (!eventDataName)
            throw new Error("eventDataName cannot be null.");
        let events = this.events;
        for (let i = 0, n = events.length; i < n; i++) {
            let event = events[i];
            if (event.name == eventDataName)
                return event;
        }
        return null;
    }
    /** Finds an animation by comparing each animation's name. It is more efficient to cache the results of this method than to
     * call it multiple times.
     * @returns May be null. */
    findAnimation(animationName) {
        if (!animationName)
            throw new Error("animationName cannot be null.");
        let animations = this.animations;
        for (let i = 0, n = animations.length; i < n; i++) {
            let animation = animations[i];
            if (animation.name == animationName)
                return animation;
        }
        return null;
    }
    /** Finds an IK constraint by comparing each IK constraint's name. It is more efficient to cache the results of this method
     * than to call it multiple times.
     * @return May be null. */
    findIkConstraint(constraintName) {
        if (!constraintName)
            throw new Error("constraintName cannot be null.");
        const ikConstraints = this.ikConstraints;
        for (let i = 0, n = ikConstraints.length; i < n; i++) {
            const constraint = ikConstraints[i];
            if (constraint.name == constraintName)
                return constraint;
        }
        return null;
    }
    /** Finds a transform constraint by comparing each transform constraint's name. It is more efficient to cache the results of
     * this method than to call it multiple times.
     * @return May be null. */
    findTransformConstraint(constraintName) {
        if (!constraintName)
            throw new Error("constraintName cannot be null.");
        const transformConstraints = this.transformConstraints;
        for (let i = 0, n = transformConstraints.length; i < n; i++) {
            const constraint = transformConstraints[i];
            if (constraint.name == constraintName)
                return constraint;
        }
        return null;
    }
    /** Finds a path constraint by comparing each path constraint's name. It is more efficient to cache the results of this method
     * than to call it multiple times.
     * @return May be null. */
    findPathConstraint(constraintName) {
        if (!constraintName)
            throw new Error("constraintName cannot be null.");
        const pathConstraints = this.pathConstraints;
        for (let i = 0, n = pathConstraints.length; i < n; i++) {
            const constraint = pathConstraints[i];
            if (constraint.name == constraintName)
                return constraint;
        }
        return null;
    }
    /** Finds a physics constraint by comparing each physics constraint's name. It is more efficient to cache the results of this method
     * than to call it multiple times.
     * @return May be null. */
    findPhysicsConstraint(constraintName) {
        if (!constraintName)
            throw new Error("constraintName cannot be null.");
        const physicsConstraints = this.physicsConstraints;
        for (let i = 0, n = physicsConstraints.length; i < n; i++) {
            const constraint = physicsConstraints[i];
            if (constraint.name == constraintName)
                return constraint;
        }
        return null;
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiU2tlbGV0b25EYXRhLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsiLi4vc3JjL1NrZWxldG9uRGF0YS50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiQUFBQTs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OytFQTJCK0U7QUFZL0U7OztZQUdZO0FBQ1osTUFBTSxPQUFPLFlBQVk7SUFFeEIsNkdBQTZHO0lBQzdHLElBQUksR0FBa0IsSUFBSSxDQUFDO0lBRTNCLHlGQUF5RjtJQUN6RixLQUFLLEdBQUcsSUFBSSxLQUFLLEVBQVksQ0FBQyxDQUFDLHlCQUF5QjtJQUV4RCx5REFBeUQ7SUFDekQsS0FBSyxHQUFHLElBQUksS0FBSyxFQUFZLENBQUMsQ0FBQyx5QkFBeUI7SUFFeEQsS0FBSyxHQUFHLElBQUksS0FBSyxFQUFRLENBQUM7SUFFMUI7OztzQkFHa0I7SUFDbEIsV0FBVyxHQUFnQixJQUFJLENBQUM7SUFFaEMsNkJBQTZCO0lBQzdCLE1BQU0sR0FBRyxJQUFJLEtBQUssRUFBYSxDQUFDO0lBRWhDLGlDQUFpQztJQUNqQyxVQUFVLEdBQUcsSUFBSSxLQUFLLEVBQWEsQ0FBQztJQUVwQyxxQ0FBcUM7SUFDckMsYUFBYSxHQUFHLElBQUksS0FBSyxFQUFvQixDQUFDO0lBRTlDLDRDQUE0QztJQUM1QyxvQkFBb0IsR0FBRyxJQUFJLEtBQUssRUFBMkIsQ0FBQztJQUU1RCx1Q0FBdUM7SUFDdkMsZUFBZSxHQUFHLElBQUksS0FBSyxFQUFzQixDQUFDO0lBRWxELDBDQUEwQztJQUMxQyxrQkFBa0IsR0FBRyxJQUFJLEtBQUssRUFBeUIsQ0FBQztJQUV4RCxzRkFBc0Y7SUFDdEYsQ0FBQyxHQUFXLENBQUMsQ0FBQztJQUVkLHNGQUFzRjtJQUN0RixDQUFDLEdBQVcsQ0FBQyxDQUFDO0lBRWQsK0VBQStFO0lBQy9FLEtBQUssR0FBVyxDQUFDLENBQUM7SUFFbEIsZ0ZBQWdGO0lBQ2hGLE1BQU0sR0FBVyxDQUFDLENBQUM7SUFFbkI7aUJBQ2E7SUFDYixj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RSxDQUFDO1lBQzNELE1BQU0sVUFBVSxHQUFHLGtCQUFrQixDQUFDLENBQUMsQ0FBQyxDQUFDO1lBQ3pDLElBQUksVUFBVSxDQUFDLElBQUksSUFBSSxjQUFjO2dCQUFFLE9BQU8sVUFBVSxDQUFDO1FBQzFELENBQUM7UUFDRCxPQUFPLElBQUksQ0FBQztJQUNiLENBQUM7Q0FDRCIsInNvdXJjZXNDb250ZW50IjpbIi8qKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKipcbiAqIFNwaW5lIFJ1bnRpbWVzIExpY2Vuc2UgQWdyZWVtZW50XG4gKiBMYXN0IHVwZGF0ZWQgQXByaWwgNSwgMjAyNS4gUmVwbGFjZXMgYWxsIHByaW9yIHZlcnNpb25zLlxuICpcbiAqIENvcHlyaWdodCAoYykgMjAxMy0yMDI1LCBFc290ZXJpYyBTb2Z0d2FyZSBMTENcbiAqXG4gKiBJbnRlZ3JhdGlvbiBvZiB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZSBvciBvdGhlcndpc2UgY3JlYXRpbmdcbiAqIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGlzIHBlcm1pdHRlZCB1bmRlciB0aGUgdGVybXMgYW5kXG4gKiBjb25kaXRpb25zIG9mIFNlY3Rpb24gMiBvZiB0aGUgU3BpbmUgRWRpdG9yIExpY2Vuc2UgQWdyZWVtZW50OlxuICogaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLWVkaXRvci1saWNlbnNlXG4gKlxuICogT3RoZXJ3aXNlLCBpdCBpcyBwZXJtaXR0ZWQgdG8gaW50ZWdyYXRlIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlXG4gKiBvciBvdGhlcndpc2UgY3JlYXRlIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIChjb2xsZWN0aXZlbHksXG4gKiBcIlByb2R1Y3RzXCIpLCBwcm92aWRlZCB0aGF0IGVhY2ggdXNlciBvZiB0aGUgUHJvZHVjdHMgbXVzdCBvYnRhaW4gdGhlaXIgb3duXG4gKiBTcGluZSBFZGl0b3IgbGljZW5zZSBhbmQgcmVkaXN0cmlidXRpb24gb2YgdGhlIFByb2R1Y3RzIGluIGFueSBmb3JtIG11c3RcbiAqIGluY2x1ZGUgdGhpcyBsaWNlbnNlIGFuZCBjb3B5cmlnaHQgbm90aWNlLlxuICpcbiAqIFRIRSBTUElORSBSVU5USU1FUyBBUkUgUFJPVklERUQgQlkgRVNPVEVSSUMgU09GVFdBUkUgTExDIFwiQVMgSVNcIiBBTkQgQU5ZXG4gKiBFWFBSRVNTIE9SIElNUExJRUQgV0FSUkFOVElFUywgSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFRIRSBJTVBMSUVEXG4gKiBXQVJSQU5USUVTIE9GIE1FUkNIQU5UQUJJTElUWSBBTkQgRklUTkVTUyBGT1IgQSBQQVJUSUNVTEFSIFBVUlBPU0UgQVJFXG4gKiBESVNDTEFJTUVELiBJTiBOTyBFVkVOVCBTSEFMTCBFU09URVJJQyBTT0ZUV0FSRSBMTEMgQkUgTElBQkxFIEZPUiBBTllcbiAqIERJUkVDVCwgSU5ESVJFQ1QsIElOQ0lERU5UQUwsIFNQRUNJQUwsIEVYRU1QTEFSWSwgT1IgQ09OU0VRVUVOVElBTCBEQU1BR0VTXG4gKiAoSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFBST0NVUkVNRU5UIE9GIFNVQlNUSVRVVEUgR09PRFMgT1IgU0VSVklDRVMsXG4gKiBCVVNJTkVTUyBJTlRFUlJVUFRJT04sIE9SIExPU1MgT0YgVVNFLCBEQVRBLCBPUiBQUk9GSVRTKSBIT1dFVkVSIENBVVNFRCBBTkRcbiAqIE9OIEFOWSBUSEVPUlkgT0YgTElBQklMSVRZLCBXSEVUSEVSIElOIENPTlRSQUNULCBTVFJJQ1QgTElBQklMSVRZLCBPUiBUT1JUXG4gKiAoSU5DTFVESU5HIE5FR0xJR0VOQ0UgT1IgT1RIRVJXSVNFKSBBUklTSU5HIElOIEFOWSBXQVkgT1VUIE9GIFRIRSBVU0UgT0ZcbiAqIFRIRSBTUElORSBSVU5USU1FUywgRVZFTiBJRiBBRFZJU0VEIE9GIFRIRSBQT1NTSUJJTElUWSBPRiBTVUNIIERBTUFHRS5cbiAqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKi9cblxuaW1wb3J0IHsgQW5pbWF0aW9uIH0gZnJvbSBcIi4vQW5pbWF0aW9uLmpzXCJcbmltcG9ydCB7IEJvbmVEYXRhIH0gZnJvbSBcIi4vQm9uZURhdGEuanNcIjtcbmltcG9ydCB7IEV2ZW50RGF0YSB9IGZyb20gXCIuL0V2ZW50RGF0YS5qc1wiO1xuaW1wb3J0IHsgSWtDb25zdHJhaW50RGF0YSB9IGZyb20gXCIuL0lrQ29uc3RyYWludERhdGEuanNcIjtcbmltcG9ydCB7IFBhdGhDb25zdHJhaW50RGF0YSB9IGZyb20gXCIuL1BhdGhDb25zdHJhaW50RGF0YS5qc1wiO1xuaW1wb3J0IHsgUGh5c2ljc0NvbnN0cmFpbnREYXRhIH0gZnJvbSBcIi4vUGh5c2ljc0NvbnN0cmFpbnREYXRhLmpzXCI7XG5pbXBvcnQgeyBTa2luIH0gZnJvbSBcIi4vU2tpbi5qc1wiO1xuaW1wb3J0IHsgU2xvdERhdGEgfSBmcm9tIFwiLi9TbG90RGF0YS5qc1wiO1xuaW1wb3J0IHsgVHJhbnNmb3JtQ29uc3RyYWludERhdGEgfSBmcm9tIFwiLi9UcmFuc2Zvcm1Db25zdHJhaW50RGF0YS5qc1wiO1xuXG4vKiogU3RvcmVzIHRoZSBzZXR1cCBwb3NlIGFuZCBhbGwgb2YgdGhlIHN0YXRlbGVzcyBkYXRhIGZvciBhIHNrZWxldG9uLlxuICpcbiAqIFNlZSBbRGF0YSBvYmplY3RzXShodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtcnVudGltZS1hcmNoaXRlY3R1cmUjRGF0YS1vYmplY3RzKSBpbiB0aGUgU3BpbmUgUnVudGltZXNcbiAqIEd1aWRlLiAqL1xuZXhwb3J0IGNsYXNzIFNrZWxldG9uRGF0YSB7XG5cblx0LyoqIFRoZSBza2VsZXRvbidzIG5hbWUsIHdoaWNoIGJ5IGRlZmF1bHQgaXMgdGhlIG5hbWUgb2YgdGhlIHNrZWxldG9uIGRhdGEgZmlsZSwgaWYgcG9zc2libGUuIE1heSBiZSBudWxsLiAqL1xuXHRuYW1lOiBzdHJpbmcgfCBudWxsID0gbnVsbDtcblxuXHQvKiogVGhlIHNrZWxldG9uJ3MgYm9uZXMsIHNvcnRlZCBwYXJlbnQgZmlyc3QuIFRoZSByb290IGJvbmUgaXMgYWx3YXlzIHRoZSBmaXJzdCBib25lLiAqL1xuXHRib25lcyA9IG5ldyBBcnJheTxCb25lRGF0YT4oKTsgLy8gT3JkZXJlZCBwYXJlbnRzIGZpcnN0LlxuXG5cdC8qKiBUaGUgc2tlbGV0b24ncyBzbG90cyBpbiB0aGUgc2V0dXAgcG9zZSBkcmF3IG9yZGVyLiAqL1xuXHRzbG90cyA9IG5ldyBBcnJheTxTbG90RGF0YT4oKTsgLy8gU2V0dXAgcG9zZSBkcmF3IG9yZGVyLlxuXG5cdHNraW5zID0gbmV3IEFycmF5PFNraW4+KCk7XG5cblx0LyoqIFRoZSBza2VsZXRvbidzIGRlZmF1bHQgc2tpbi4gQnkgZGVmYXVsdCB0aGlzIHNraW4gY29udGFpbnMgYWxsIGF0dGFjaG1lbnRzIHRoYXQgd2VyZSBub3QgaW4gYSBza2luIGluIFNwaW5lLlxuXHQgKlxuXHQgKiBTZWUge0BsaW5rIFNrZWxldG9uI2dldEF0dGFjaG1lbnRCeU5hbWUoKX0uXG5cdCAqIE1heSBiZSBudWxsLiAqL1xuXHRkZWZhdWx0U2tpbjogU2tpbiB8IG51bGwgPSBudWxsO1xuXG5cdC8qKiBUaGUgc2tlbGV0b24ncyBldmVudHMuICovXG5cdGV2ZW50cyA9IG5ldyBBcnJheTxFdmVudERhdGE+KCk7XG5cblx0LyoqIFRoZSBza2VsZXRvbidzIGFuaW1hdGlvbnMuICovXG5cdGFuaW1hdGlvbnMgPSBuZXcgQXJyYXk8QW5pbWF0aW9uPigpO1xuXG5cdC8qKiBUaGUgc2tlbGV0b24ncyBJSyBjb25zdHJhaW50cy4gKi9cblx0aWtDb25zdHJhaW50cyA9IG5ldyBBcnJheTxJa0NvbnN0cmFpbnREYXRhPigpO1xuXG5cdC8qKiBUaGUgc2tlbGV0b24ncyB0cmFuc2Zvcm0gY29uc3RyYWludHMuICovXG5cdHRyYW5zZm9ybUNvbnN0cmFpbnRzID0gbmV3IEFycmF5PFRyYW5zZm9ybUNvbnN0cmFpbnREYXRhPigpO1xuXG5cdC8qKiBUaGUgc2tlbGV0b24ncyBwYXRoIGNvbnN0cmFpbnRzLiAqL1xuXHRwYXRoQ29uc3RyYWludHMgPSBuZXcgQXJyYXk8UGF0aENvbnN0cmFpbnREYXRhPigpO1xuXG5cdC8qKiBUaGUgc2tlbGV0b24ncyBwaHlzaWNzIGNvbnN0cmFpbnRzLiAqL1xuXHRwaHlzaWNzQ29uc3RyYWludHMgPSBuZXcgQXJyYXk8UGh5c2ljc0NvbnN0cmFpbnREYXRhPigpO1xuXG5cdC8qKiBUaGUgWCBjb29yZGluYXRlIG9mIHRoZSBza2VsZXRvbidzIGF4aXMgYWxpZ25lZCBib3VuZGluZyBib3ggaW4gdGhlIHNldHVwIHBvc2UuICovXG5cdHg6IG51bWJlciA9IDA7XG5cblx0LyoqIFRoZSBZIGNvb3JkaW5hdGUgb2YgdGhlIHNrZWxldG9uJ3MgYXhpcyBhbGlnbmVkIGJvdW5kaW5nIGJveCBpbiB0aGUgc2V0dXAgcG9zZS4gKi9cblx0eTogbnVtYmVyID0gMDtcblxuXHQvKiogVGhlIHdpZHRoIG9mIHRoZSBza2VsZXRvbidzIGF4aXMgYWxpZ25lZCBib3VuZGluZyBib3ggaW4gdGhlIHNldHVwIHBvc2UuICovXG5cdHdpZHRoOiBudW1iZXIgPSAwO1xuXG5cdC8qKiBUaGUgaGVpZ2h0IG9mIHRoZSBza2VsZXRvbidzIGF4aXMgYWxpZ25lZCBib3VuZGluZyBib3ggaW4gdGhlIHNldHVwIHBvc2UuICovXG5cdGhlaWdodDogbnVtYmVyID0gMDtcblxuXHQvKiogQmFzZWxpbmUgc2NhbGUgZmFjdG9yIGZvciBhcHBseWluZyBkaXN0YW5jZS1kZXBlbmRlbnQgZWZmZWN0cyBvbiBub24tc2NhbGFibGUgcHJvcGVydGllcywgc3VjaCBhcyBhbmdsZSBvciBzY2FsZS4gRGVmYXVsdFxuXHQgKiBpcyAxMDAuICovXG5cdHJlZmVyZW5jZVNjYWxlID0gMTAwO1xuXG5cdC8qKiBUaGUgU3BpbmUgdmVyc2lvbiB1c2VkIHRvIGV4cG9ydCB0aGUgc2tlbGV0b24gZGF0YSwgb3IgbnVsbC4gKi9cblx0dmVyc2lvbjogc3RyaW5nIHwgbnVsbCA9IG51bGw7XG5cblx0LyoqIFRoZSBza2VsZXRvbiBkYXRhIGhhc2guIFRoaXMgdmFsdWUgd2lsbCBjaGFuZ2UgaWYgYW55IG9mIHRoZSBza2VsZXRvbiBkYXRhIGhhcyBjaGFuZ2VkLiBNYXkgYmUgbnVsbC4gKi9cblx0aGFzaDogc3RyaW5nIHwgbnVsbCA9IG51bGw7XG5cblx0Ly8gTm9uZXNzZW50aWFsXG5cdC8qKiBUaGUgZG9wZXNoZWV0IEZQUyBpbiBTcGluZS4gQXZhaWxhYmxlIG9ubHkgd2hlbiBub25lc3NlbnRpYWwgZGF0YSB3YXMgZXhwb3J0ZWQuICovXG5cdGZwcyA9IDA7XG5cblx0LyoqIFRoZSBwYXRoIHRvIHRoZSBpbWFnZXMgZGlyZWN0b3J5IGFzIGRlZmluZWQgaW4gU3BpbmUuIEF2YWlsYWJsZSBvbmx5IHdoZW4gbm9uZXNzZW50aWFsIGRhdGEgd2FzIGV4cG9ydGVkLiBNYXkgYmUgbnVsbC4gKi9cblx0aW1hZ2VzUGF0aDogc3RyaW5nIHwgbnVsbCA9IG51bGw7XG5cblx0LyoqIFRoZSBwYXRoIHRvIHRoZSBhdWRpbyBkaXJlY3RvcnkgYXMgZGVmaW5lZCBpbiBTcGluZS4gQXZhaWxhYmxlIG9ubHkgd2hlbiBub25lc3NlbnRpYWwgZGF0YSB3YXMgZXhwb3J0ZWQuIE1heSBiZSBudWxsLiAqL1xuXHRhdWRpb1BhdGg6IHN0cmluZyB8IG51bGwgPSBudWxsO1xuXG5cdC8qKiBGaW5kcyBhIGJvbmUgYnkgY29tcGFyaW5nIGVhY2ggYm9uZSdzIG5hbWUuIEl0IGlzIG1vcmUgZWZmaWNpZW50IHRvIGNhY2hlIHRoZSByZXN1bHRzIG9mIHRoaXMgbWV0aG9kIHRoYW4gdG8gY2FsbCBpdFxuXHQgKiBtdWx0aXBsZSB0aW1lcy5cblx0ICogQHJldHVybnMgTWF5IGJlIG51bGwuICovXG5cdGZpbmRCb25lIChib25lTmFtZTogc3RyaW5nKSB7XG5cdFx0aWYgKCFib25lTmFtZSkgdGhyb3cgbmV3IEVycm9yKFwiYm9uZU5hbWUgY2Fubm90IGJlIG51bGwuXCIpO1xuXHRcdGxldCBib25lcyA9IHRoaXMuYm9uZXM7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBib25lcy5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBib25lID0gYm9uZXNbaV07XG5cdFx0XHRpZiAoYm9uZS5uYW1lID09IGJvbmVOYW1lKSByZXR1cm4gYm9uZTtcblx0XHR9XG5cdFx0cmV0dXJuIG51bGw7XG5cdH1cblxuXHQvKiogRmluZHMgYSBzbG90IGJ5IGNvbXBhcmluZyBlYWNoIHNsb3QncyBuYW1lLiBJdCBpcyBtb3JlIGVmZmljaWVudCB0byBjYWNoZSB0aGUgcmVzdWx0cyBvZiB0aGlzIG1ldGhvZCB0aGFuIHRvIGNhbGwgaXRcblx0ICogbXVsdGlwbGUgdGltZXMuXG5cdCAqIEByZXR1cm5zIE1heSBiZSBudWxsLiAqL1xuXHRmaW5kU2xvdCAoc2xvdE5hbWU6IHN0cmluZykge1xuXHRcdGlmICghc2xvdE5hbWUpIHRocm93IG5ldyBFcnJvcihcInNsb3ROYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRsZXQgc2xvdHMgPSB0aGlzLnNsb3RzO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gc2xvdHMubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRsZXQgc2xvdCA9IHNsb3RzW2ldO1xuXHRcdFx0aWYgKHNsb3QubmFtZSA9PSBzbG90TmFtZSkgcmV0dXJuIHNsb3Q7XG5cdFx0fVxuXHRcdHJldHVybiBudWxsO1xuXHR9XG5cblx0LyoqIEZpbmRzIGEgc2tpbiBieSBjb21wYXJpbmcgZWFjaCBza2luJ3MgbmFtZS4gSXQgaXMgbW9yZSBlZmZpY2llbnQgdG8gY2FjaGUgdGhlIHJlc3VsdHMgb2YgdGhpcyBtZXRob2QgdGhhbiB0byBjYWxsIGl0XG5cdCAqIG11bHRpcGxlIHRpbWVzLlxuXHQgKiBAcmV0dXJucyBNYXkgYmUgbnVsbC4gKi9cblx0ZmluZFNraW4gKHNraW5OYW1lOiBzdHJpbmcpIHtcblx0XHRpZiAoIXNraW5OYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJza2luTmFtZSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0bGV0IHNraW5zID0gdGhpcy5za2lucztcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IHNraW5zLmxlbmd0aDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IHNraW4gPSBza2luc1tpXTtcblx0XHRcdGlmIChza2luLm5hbWUgPT0gc2tpbk5hbWUpIHJldHVybiBza2luO1xuXHRcdH1cblx0XHRyZXR1cm4gbnVsbDtcblx0fVxuXG5cdC8qKiBGaW5kcyBhbiBldmVudCBieSBjb21wYXJpbmcgZWFjaCBldmVudHMncyBuYW1lLiBJdCBpcyBtb3JlIGVmZmljaWVudCB0byBjYWNoZSB0aGUgcmVzdWx0cyBvZiB0aGlzIG1ldGhvZCB0aGFuIHRvIGNhbGwgaXRcblx0ICogbXVsdGlwbGUgdGltZXMuXG5cdCAqIEByZXR1cm5zIE1heSBiZSBudWxsLiAqL1xuXHRmaW5kRXZlbnQgKGV2ZW50RGF0YU5hbWU6IHN0cmluZykge1xuXHRcdGlmICghZXZlbnREYXRhTmFtZSkgdGhyb3cgbmV3IEVycm9yKFwiZXZlbnREYXRhTmFtZSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0bGV0IGV2ZW50cyA9IHRoaXMuZXZlbnRzO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gZXZlbnRzLmxlbmd0aDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGV2ZW50ID0gZXZlbnRzW2ldO1xuXHRcdFx0aWYgKGV2ZW50Lm5hbWUgPT0gZXZlbnREYXRhTmFtZSkgcmV0dXJuIGV2ZW50O1xuXHRcdH1cblx0XHRyZXR1cm4gbnVsbDtcblx0fVxuXG5cdC8qKiBGaW5kcyBhbiBhbmltYXRpb24gYnkgY29tcGFyaW5nIGVhY2ggYW5pbWF0aW9uJ3MgbmFtZS4gSXQgaXMgbW9yZSBlZmZpY2llbnQgdG8gY2FjaGUgdGhlIHJlc3VsdHMgb2YgdGhpcyBtZXRob2QgdGhhbiB0b1xuXHQgKiBjYWxsIGl0IG11bHRpcGxlIHRpbWVzLlxuXHQgKiBAcmV0dXJucyBNYXkgYmUgbnVsbC4gKi9cblx0ZmluZEFuaW1hdGlvbiAoYW5pbWF0aW9uTmFtZTogc3RyaW5nKSB7XG5cdFx0aWYgKCFhbmltYXRpb25OYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJhbmltYXRpb25OYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRsZXQgYW5pbWF0aW9ucyA9IHRoaXMuYW5pbWF0aW9ucztcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IGFuaW1hdGlvbnMubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRsZXQgYW5pbWF0aW9uID0gYW5pbWF0aW9uc1tpXTtcblx0XHRcdGlmIChhbmltYXRpb24ubmFtZSA9PSBhbmltYXRpb25OYW1lKSByZXR1cm4gYW5pbWF0aW9uO1xuXHRcdH1cblx0XHRyZXR1cm4gbnVsbDtcblx0fVxuXG5cdC8qKiBGaW5kcyBhbiBJSyBjb25zdHJhaW50IGJ5IGNvbXBhcmluZyBlYWNoIElLIGNvbnN0cmFpbnQncyBuYW1lLiBJdCBpcyBtb3JlIGVmZmljaWVudCB0byBjYWNoZSB0aGUgcmVzdWx0cyBvZiB0aGlzIG1ldGhvZFxuXHQgKiB0aGFuIHRvIGNhbGwgaXQgbXVsdGlwbGUgdGltZXMuXG5cdCAqIEByZXR1cm4gTWF5IGJlIG51bGwuICovXG5cdGZpbmRJa0NvbnN0cmFpbnQgKGNvbnN0cmFpbnROYW1lOiBzdHJpbmcpIHtcblx0XHRpZiAoIWNvbnN0cmFpbnROYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJjb25zdHJhaW50TmFtZSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0Y29uc3QgaWtDb25zdHJhaW50cyA9IHRoaXMuaWtDb25zdHJhaW50cztcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IGlrQ29uc3RyYWludHMubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRjb25zdCBjb25zdHJhaW50ID0gaWtDb25zdHJhaW50c1tpXTtcblx0XHRcdGlmIChjb25zdHJhaW50Lm5hbWUgPT0gY29uc3RyYWludE5hbWUpIHJldHVybiBjb25zdHJhaW50O1xuXHRcdH1cblx0XHRyZXR1cm4gbnVsbDtcblx0fVxuXG5cdC8qKiBGaW5kcyBhIHRyYW5zZm9ybSBjb25zdHJhaW50IGJ5IGNvbXBhcmluZyBlYWNoIHRyYW5zZm9ybSBjb25zdHJhaW50J3MgbmFtZS4gSXQgaXMgbW9yZSBlZmZpY2llbnQgdG8gY2FjaGUgdGhlIHJlc3VsdHMgb2Zcblx0ICogdGhpcyBtZXRob2QgdGhhbiB0byBjYWxsIGl0IG11bHRpcGxlIHRpbWVzLlxuXHQgKiBAcmV0dXJuIE1heSBiZSBudWxsLiAqL1xuXHRmaW5kVHJhbnNmb3JtQ29uc3RyYWludCAoY29uc3RyYWludE5hbWU6IHN0cmluZykge1xuXHRcdGlmICghY29uc3RyYWludE5hbWUpIHRocm93IG5ldyBFcnJvcihcImNvbnN0cmFpbnROYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRjb25zdCB0cmFuc2Zvcm1Db25zdHJhaW50cyA9IHRoaXMudHJhbnNmb3JtQ29uc3RyYWludHM7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSB0cmFuc2Zvcm1Db25zdHJhaW50cy5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGNvbnN0IGNvbnN0cmFpbnQgPSB0cmFuc2Zvcm1Db25zdHJhaW50c1tpXTtcblx0XHRcdGlmIChjb25zdHJhaW50Lm5hbWUgPT0gY29uc3RyYWludE5hbWUpIHJldHVybiBjb25zdHJhaW50O1xuXHRcdH1cblx0XHRyZXR1cm4gbnVsbDtcblx0fVxuXG5cdC8qKiBGaW5kcyBhIHBhdGggY29uc3RyYWludCBieSBjb21wYXJpbmcgZWFjaCBwYXRoIGNvbnN0cmFpbnQncyBuYW1lLiBJdCBpcyBtb3JlIGVmZmljaWVudCB0byBjYWNoZSB0aGUgcmVzdWx0cyBvZiB0aGlzIG1ldGhvZFxuXHQgKiB0aGFuIHRvIGNhbGwgaXQgbXVsdGlwbGUgdGltZXMuXG5cdCAqIEByZXR1cm4gTWF5IGJlIG51bGwuICovXG5cdGZpbmRQYXRoQ29uc3RyYWludCAoY29uc3RyYWludE5hbWU6IHN0cmluZykge1xuXHRcdGlmICghY29uc3RyYWludE5hbWUpIHRocm93IG5ldyBFcnJvcihcImNvbnN0cmFpbnROYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRjb25zdCBwYXRoQ29uc3RyYWludHMgPSB0aGlzLnBhdGhDb25zdHJhaW50cztcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IHBhdGhDb25zdHJhaW50cy5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGNvbnN0IGNvbnN0cmFpbnQgPSBwYXRoQ29uc3RyYWludHNbaV07XG5cdFx0XHRpZiAoY29uc3RyYWludC5uYW1lID09IGNvbnN0cmFpbnROYW1lKSByZXR1cm4gY29uc3RyYWludDtcblx0XHR9XG5cdFx0cmV0dXJuIG51bGw7XG5cdH1cblxuXHQvKiogRmluZHMgYSBwaHlzaWNzIGNvbnN0cmFpbnQgYnkgY29tcGFyaW5nIGVhY2ggcGh5c2ljcyBjb25zdHJhaW50J3MgbmFtZS4gSXQgaXMgbW9yZSBlZmZpY2llbnQgdG8gY2FjaGUgdGhlIHJlc3VsdHMgb2YgdGhpcyBtZXRob2Rcblx0ICogdGhhbiB0byBjYWxsIGl0IG11bHRpcGxlIHRpbWVzLlxuXHQgKiBAcmV0dXJuIE1heSBiZSBudWxsLiAqL1xuXHRmaW5kUGh5c2ljc0NvbnN0cmFpbnQgKGNvbnN0cmFpbnROYW1lOiBzdHJpbmcpIHtcblx0XHRpZiAoIWNvbnN0cmFpbnROYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJjb25zdHJhaW50TmFtZSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0Y29uc3QgcGh5c2ljc0NvbnN0cmFpbnRzID0gdGhpcy5waHlzaWNzQ29uc3RyYWludHM7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBwaHlzaWNzQ29uc3RyYWludHMubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRjb25zdCBjb25zdHJhaW50ID0gcGh5c2ljc0NvbnN0cmFpbnRzW2ldO1xuXHRcdFx0aWYgKGNvbnN0cmFpbnQubmFtZSA9PSBjb25zdHJhaW50TmFtZSkgcmV0dXJuIGNvbnN0cmFpbnQ7XG5cdFx0fVxuXHRcdHJldHVybiBudWxsO1xuXHR9XG59XG4iXX0=