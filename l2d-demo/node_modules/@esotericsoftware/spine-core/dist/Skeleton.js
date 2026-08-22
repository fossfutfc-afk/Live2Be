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
import { ClippingAttachment } from "./attachments/ClippingAttachment.js";
import { MeshAttachment } from "./attachments/MeshAttachment.js";
import { PathAttachment } from "./attachments/PathAttachment.js";
import { RegionAttachment } from "./attachments/RegionAttachment.js";
import { Bone } from "./Bone.js";
import { IkConstraint } from "./IkConstraint.js";
import { PathConstraint } from "./PathConstraint.js";
import { PhysicsConstraint } from "./PhysicsConstraint.js";
import { Slot } from "./Slot.js";
import { TransformConstraint } from "./TransformConstraint.js";
import { Color, Utils, MathUtils, Vector2 } from "./Utils.js";
/** Stores the current pose for a skeleton.
 *
 * See [Instance objects](http://esotericsoftware.com/spine-runtime-architecture#Instance-objects) in the Spine Runtimes Guide. */
export class Skeleton {
    static quadTriangles = [0, 1, 2, 2, 3, 0];
    static yDown = false;
    /** The skeleton's setup pose data. */
    data;
    /** The skeleton's bones, sorted parent first. The root bone is always the first bone. */
    bones;
    /** The skeleton's slots in the setup pose draw order. */
    slots;
    /** The skeleton's slots in the order they should be drawn. The returned array may be modified to change the draw order. */
    drawOrder;
    /** The skeleton's IK constraints. */
    ikConstraints;
    /** The skeleton's transform constraints. */
    transformConstraints;
    /** The skeleton's path constraints. */
    pathConstraints;
    /** The skeleton's physics constraints. */
    physicsConstraints;
    /** The list of bones and constraints, sorted in the order they should be updated, as computed by {@link #updateCache()}. */
    _updateCache = new Array();
    /** The skeleton's current skin. May be null. */
    skin = null;
    /** The color to tint all the skeleton's attachments. */
    color;
    /** Scales the entire skeleton on the X axis. This affects all bones, even if the bone's transform mode disallows scale
      * inheritance. */
    scaleX = 1;
    /** Scales the entire skeleton on the Y axis. This affects all bones, even if the bone's transform mode disallows scale
      * inheritance. */
    _scaleY = 1;
    get scaleY() {
        return Skeleton.yDown ? -this._scaleY : this._scaleY;
    }
    set scaleY(scaleY) {
        this._scaleY = scaleY;
    }
    /** Sets the skeleton X position, which is added to the root bone worldX position. */
    x = 0;
    /** Sets the skeleton Y position, which is added to the root bone worldY position. */
    y = 0;
    /** Returns the skeleton's time. This is used for time-based manipulations, such as {@link PhysicsConstraint}.
     * <p>
     * See {@link #update(float)}. */
    time = 0;
    constructor(data) {
        if (!data)
            throw new Error("data cannot be null.");
        this.data = data;
        this.bones = new Array();
        for (let i = 0; i < data.bones.length; i++) {
            let boneData = data.bones[i];
            let bone;
            if (!boneData.parent)
                bone = new Bone(boneData, this, null);
            else {
                let parent = this.bones[boneData.parent.index];
                bone = new Bone(boneData, this, parent);
                parent.children.push(bone);
            }
            this.bones.push(bone);
        }
        this.slots = new Array();
        this.drawOrder = new Array();
        for (let i = 0; i < data.slots.length; i++) {
            let slotData = data.slots[i];
            let bone = this.bones[slotData.boneData.index];
            let slot = new Slot(slotData, bone);
            this.slots.push(slot);
            this.drawOrder.push(slot);
        }
        this.ikConstraints = new Array();
        for (let i = 0; i < data.ikConstraints.length; i++) {
            let ikConstraintData = data.ikConstraints[i];
            this.ikConstraints.push(new IkConstraint(ikConstraintData, this));
        }
        this.transformConstraints = new Array();
        for (let i = 0; i < data.transformConstraints.length; i++) {
            let transformConstraintData = data.transformConstraints[i];
            this.transformConstraints.push(new TransformConstraint(transformConstraintData, this));
        }
        this.pathConstraints = new Array();
        for (let i = 0; i < data.pathConstraints.length; i++) {
            let pathConstraintData = data.pathConstraints[i];
            this.pathConstraints.push(new PathConstraint(pathConstraintData, this));
        }
        this.physicsConstraints = new Array();
        for (let i = 0; i < data.physicsConstraints.length; i++) {
            let physicsConstraintData = data.physicsConstraints[i];
            this.physicsConstraints.push(new PhysicsConstraint(physicsConstraintData, this));
        }
        this.color = new Color(1, 1, 1, 1);
        this.updateCache();
    }
    /** Caches information about bones and constraints. Must be called if the {@link #getSkin()} is modified or if bones,
     * constraints, or weighted path attachments are added or removed. */
    updateCache() {
        let updateCache = this._updateCache;
        updateCache.length = 0;
        let bones = this.bones;
        for (let i = 0, n = bones.length; i < n; i++) {
            let bone = bones[i];
            bone.sorted = bone.data.skinRequired;
            bone.active = !bone.sorted;
        }
        if (this.skin) {
            let skinBones = this.skin.bones;
            for (let i = 0, n = this.skin.bones.length; i < n; i++) {
                let bone = this.bones[skinBones[i].index];
                do {
                    bone.sorted = false;
                    bone.active = true;
                    bone = bone.parent;
                } while (bone);
            }
        }
        // IK first, lowest hierarchy depth first.
        let ikConstraints = this.ikConstraints;
        let transformConstraints = this.transformConstraints;
        let pathConstraints = this.pathConstraints;
        let physicsConstraints = this.physicsConstraints;
        let ikCount = ikConstraints.length, transformCount = transformConstraints.length, pathCount = pathConstraints.length, physicsCount = this.physicsConstraints.length;
        let constraintCount = ikCount + transformCount + pathCount + physicsCount;
        outer: for (let i = 0; i < constraintCount; i++) {
            for (let ii = 0; ii < ikCount; ii++) {
                let constraint = ikConstraints[ii];
                if (constraint.data.order == i) {
                    this.sortIkConstraint(constraint);
                    continue outer;
                }
            }
            for (let ii = 0; ii < transformCount; ii++) {
                let constraint = transformConstraints[ii];
                if (constraint.data.order == i) {
                    this.sortTransformConstraint(constraint);
                    continue outer;
                }
            }
            for (let ii = 0; ii < pathCount; ii++) {
                let constraint = pathConstraints[ii];
                if (constraint.data.order == i) {
                    this.sortPathConstraint(constraint);
                    continue outer;
                }
            }
            for (let ii = 0; ii < physicsCount; ii++) {
                const constraint = physicsConstraints[ii];
                if (constraint.data.order == i) {
                    this.sortPhysicsConstraint(constraint);
                    continue outer;
                }
            }
        }
        for (let i = 0, n = bones.length; i < n; i++)
            this.sortBone(bones[i]);
    }
    sortIkConstraint(constraint) {
        constraint.active = constraint.target.isActive() && (!constraint.data.skinRequired || (this.skin && Utils.contains(this.skin.constraints, constraint.data, true)));
        if (!constraint.active)
            return;
        let target = constraint.target;
        this.sortBone(target);
        let constrained = constraint.bones;
        let parent = constrained[0];
        this.sortBone(parent);
        if (constrained.length == 1) {
            this._updateCache.push(constraint);
            this.sortReset(parent.children);
        }
        else {
            let child = constrained[constrained.length - 1];
            this.sortBone(child);
            this._updateCache.push(constraint);
            this.sortReset(parent.children);
            child.sorted = true;
        }
    }
    sortPathConstraint(constraint) {
        constraint.active = constraint.target.bone.isActive() && (!constraint.data.skinRequired || (this.skin && Utils.contains(this.skin.constraints, constraint.data, true)));
        if (!constraint.active)
            return;
        let slot = constraint.target;
        let slotIndex = slot.data.index;
        let slotBone = slot.bone;
        if (this.skin)
            this.sortPathConstraintAttachment(this.skin, slotIndex, slotBone);
        if (this.data.defaultSkin && this.data.defaultSkin != this.skin)
            this.sortPathConstraintAttachment(this.data.defaultSkin, slotIndex, slotBone);
        for (let i = 0, n = this.data.skins.length; i < n; i++)
            this.sortPathConstraintAttachment(this.data.skins[i], slotIndex, slotBone);
        let attachment = slot.getAttachment();
        if (attachment instanceof PathAttachment)
            this.sortPathConstraintAttachmentWith(attachment, slotBone);
        let constrained = constraint.bones;
        let boneCount = constrained.length;
        for (let i = 0; i < boneCount; i++)
            this.sortBone(constrained[i]);
        this._updateCache.push(constraint);
        for (let i = 0; i < boneCount; i++)
            this.sortReset(constrained[i].children);
        for (let i = 0; i < boneCount; i++)
            constrained[i].sorted = true;
    }
    sortTransformConstraint(constraint) {
        constraint.active = constraint.target.isActive() && (!constraint.data.skinRequired || (this.skin && Utils.contains(this.skin.constraints, constraint.data, true)));
        if (!constraint.active)
            return;
        this.sortBone(constraint.target);
        let constrained = constraint.bones;
        let boneCount = constrained.length;
        if (constraint.data.local) {
            for (let i = 0; i < boneCount; i++) {
                let child = constrained[i];
                this.sortBone(child.parent);
                this.sortBone(child);
            }
        }
        else {
            for (let i = 0; i < boneCount; i++) {
                this.sortBone(constrained[i]);
            }
        }
        this._updateCache.push(constraint);
        for (let i = 0; i < boneCount; i++)
            this.sortReset(constrained[i].children);
        for (let i = 0; i < boneCount; i++)
            constrained[i].sorted = true;
    }
    sortPathConstraintAttachment(skin, slotIndex, slotBone) {
        let attachments = skin.attachments[slotIndex];
        if (!attachments)
            return;
        for (let key in attachments) {
            this.sortPathConstraintAttachmentWith(attachments[key], slotBone);
        }
    }
    sortPathConstraintAttachmentWith(attachment, slotBone) {
        if (!(attachment instanceof PathAttachment))
            return;
        let pathBones = attachment.bones;
        if (!pathBones)
            this.sortBone(slotBone);
        else {
            let bones = this.bones;
            for (let i = 0, n = pathBones.length; i < n;) {
                let nn = pathBones[i++];
                nn += i;
                while (i < nn)
                    this.sortBone(bones[pathBones[i++]]);
            }
        }
    }
    sortPhysicsConstraint(constraint) {
        const bone = constraint.bone;
        constraint.active = bone.active && (!constraint.data.skinRequired || (this.skin != null && Utils.contains(this.skin.constraints, constraint.data, true)));
        if (!constraint.active)
            return;
        this.sortBone(bone);
        this._updateCache.push(constraint);
        this.sortReset(bone.children);
        bone.sorted = true;
    }
    sortBone(bone) {
        if (!bone)
            return;
        if (bone.sorted)
            return;
        let parent = bone.parent;
        if (parent)
            this.sortBone(parent);
        bone.sorted = true;
        this._updateCache.push(bone);
    }
    sortReset(bones) {
        for (let i = 0, n = bones.length; i < n; i++) {
            let bone = bones[i];
            if (!bone.active)
                continue;
            if (bone.sorted)
                this.sortReset(bone.children);
            bone.sorted = false;
        }
    }
    /** Updates the world transform for each bone and applies all constraints.
     *
     * See [World transforms](http://esotericsoftware.com/spine-runtime-skeletons#World-transforms) in the Spine
     * Runtimes Guide. */
    updateWorldTransform(physics) {
        if (physics === undefined || physics === null)
            throw new Error("physics is undefined");
        let bones = this.bones;
        for (let i = 0, n = bones.length; i < n; i++) {
            let bone = bones[i];
            bone.ax = bone.x;
            bone.ay = bone.y;
            bone.arotation = bone.rotation;
            bone.ascaleX = bone.scaleX;
            bone.ascaleY = bone.scaleY;
            bone.ashearX = bone.shearX;
            bone.ashearY = bone.shearY;
        }
        let updateCache = this._updateCache;
        for (let i = 0, n = updateCache.length; i < n; i++)
            updateCache[i].update(physics);
    }
    updateWorldTransformWith(physics, parent) {
        if (!parent)
            throw new Error("parent cannot be null.");
        let bones = this.bones;
        for (let i = 1, n = bones.length; i < n; i++) { // Skip root bone.
            let bone = bones[i];
            bone.ax = bone.x;
            bone.ay = bone.y;
            bone.arotation = bone.rotation;
            bone.ascaleX = bone.scaleX;
            bone.ascaleY = bone.scaleY;
            bone.ashearX = bone.shearX;
            bone.ashearY = bone.shearY;
        }
        // Apply the parent bone transform to the root bone. The root bone always inherits scale, rotation and reflection.
        let rootBone = this.getRootBone();
        if (!rootBone)
            throw new Error("Root bone must not be null.");
        let pa = parent.a, pb = parent.b, pc = parent.c, pd = parent.d;
        rootBone.worldX = pa * this.x + pb * this.y + parent.worldX;
        rootBone.worldY = pc * this.x + pd * this.y + parent.worldY;
        const rx = (rootBone.rotation + rootBone.shearX) * MathUtils.degRad;
        const ry = (rootBone.rotation + 90 + rootBone.shearY) * MathUtils.degRad;
        const la = Math.cos(rx) * rootBone.scaleX;
        const lb = Math.cos(ry) * rootBone.scaleY;
        const lc = Math.sin(rx) * rootBone.scaleX;
        const ld = Math.sin(ry) * rootBone.scaleY;
        rootBone.a = (pa * la + pb * lc) * this.scaleX;
        rootBone.b = (pa * lb + pb * ld) * this.scaleX;
        rootBone.c = (pc * la + pd * lc) * this.scaleY;
        rootBone.d = (pc * lb + pd * ld) * this.scaleY;
        // Update everything except root bone.
        let updateCache = this._updateCache;
        for (let i = 0, n = updateCache.length; i < n; i++) {
            let updatable = updateCache[i];
            if (updatable != rootBone)
                updatable.update(physics);
        }
    }
    /** Sets the bones, constraints, and slots to their setup pose values. */
    setToSetupPose() {
        this.setBonesToSetupPose();
        this.setSlotsToSetupPose();
    }
    /** Sets the bones and constraints to their setup pose values. */
    setBonesToSetupPose() {
        for (const bone of this.bones)
            bone.setToSetupPose();
        for (const constraint of this.ikConstraints)
            constraint.setToSetupPose();
        for (const constraint of this.transformConstraints)
            constraint.setToSetupPose();
        for (const constraint of this.pathConstraints)
            constraint.setToSetupPose();
        for (const constraint of this.physicsConstraints)
            constraint.setToSetupPose();
    }
    /** Sets the slots and draw order to their setup pose values. */
    setSlotsToSetupPose() {
        let slots = this.slots;
        Utils.arrayCopy(slots, 0, this.drawOrder, 0, slots.length);
        for (let i = 0, n = slots.length; i < n; i++)
            slots[i].setToSetupPose();
    }
    /** @returns May return null. */
    getRootBone() {
        if (this.bones.length == 0)
            return null;
        return this.bones[0];
    }
    /** @returns May be null. */
    findBone(boneName) {
        if (!boneName)
            throw new Error("boneName cannot be null.");
        let bones = this.bones;
        for (let i = 0, n = bones.length; i < n; i++) {
            let bone = bones[i];
            if (bone.data.name == boneName)
                return bone;
        }
        return null;
    }
    /** Finds a slot by comparing each slot's name. It is more efficient to cache the results of this method than to call it
     * repeatedly.
     * @returns May be null. */
    findSlot(slotName) {
        if (!slotName)
            throw new Error("slotName cannot be null.");
        let slots = this.slots;
        for (let i = 0, n = slots.length; i < n; i++) {
            let slot = slots[i];
            if (slot.data.name == slotName)
                return slot;
        }
        return null;
    }
    /** Sets a skin by name.
     *
     * See {@link #setSkin()}. */
    setSkinByName(skinName) {
        let skin = this.data.findSkin(skinName);
        if (!skin)
            throw new Error("Skin not found: " + skinName);
        this.setSkin(skin);
    }
    /** Sets the skin used to look up attachments before looking in the {@link SkeletonData#defaultSkin default skin}. If the
     * skin is changed, {@link #updateCache()} is called.
     *
     * Attachments from the new skin are attached if the corresponding attachment from the old skin was attached. If there was no
     * old skin, each slot's setup mode attachment is attached from the new skin.
     *
     * After changing the skin, the visible attachments can be reset to those attached in the setup pose by calling
     * {@link #setSlotsToSetupPose()}. Also, often {@link AnimationState#apply()} is called before the next time the
     * skeleton is rendered to allow any attachment keys in the current animation(s) to hide or show attachments from the new skin.
     * @param newSkin May be null. */
    setSkin(newSkin) {
        if (newSkin == this.skin)
            return;
        if (newSkin) {
            if (this.skin)
                newSkin.attachAll(this, this.skin);
            else {
                let slots = this.slots;
                for (let i = 0, n = slots.length; i < n; i++) {
                    let slot = slots[i];
                    let name = slot.data.attachmentName;
                    if (name) {
                        let attachment = newSkin.getAttachment(i, name);
                        if (attachment)
                            slot.setAttachment(attachment);
                    }
                }
            }
        }
        this.skin = newSkin;
        this.updateCache();
    }
    /** Finds an attachment by looking in the {@link #skin} and {@link SkeletonData#defaultSkin} using the slot name and attachment
     * name.
     *
     * See {@link #getAttachment()}.
     * @returns May be null. */
    getAttachmentByName(slotName, attachmentName) {
        let slot = this.data.findSlot(slotName);
        if (!slot)
            throw new Error(`Can't find slot with name ${slotName}`);
        return this.getAttachment(slot.index, attachmentName);
    }
    /** Finds an attachment by looking in the {@link #skin} and {@link SkeletonData#defaultSkin} using the slot index and
     * attachment name. First the skin is checked and if the attachment was not found, the default skin is checked.
     *
     * See [Runtime skins](http://esotericsoftware.com/spine-runtime-skins) in the Spine Runtimes Guide.
     * @returns May be null. */
    getAttachment(slotIndex, attachmentName) {
        if (!attachmentName)
            throw new Error("attachmentName cannot be null.");
        if (this.skin) {
            let attachment = this.skin.getAttachment(slotIndex, attachmentName);
            if (attachment)
                return attachment;
        }
        if (this.data.defaultSkin)
            return this.data.defaultSkin.getAttachment(slotIndex, attachmentName);
        return null;
    }
    /** A convenience method to set an attachment by finding the slot with {@link #findSlot()}, finding the attachment with
     * {@link #getAttachment()}, then setting the slot's {@link Slot#attachment}.
     * @param attachmentName May be null to clear the slot's attachment. */
    setAttachment(slotName, attachmentName) {
        if (!slotName)
            throw new Error("slotName cannot be null.");
        let slots = this.slots;
        for (let i = 0, n = slots.length; i < n; i++) {
            let slot = slots[i];
            if (slot.data.name == slotName) {
                let attachment = null;
                if (attachmentName) {
                    attachment = this.getAttachment(i, attachmentName);
                    if (!attachment)
                        throw new Error("Attachment not found: " + attachmentName + ", for slot: " + slotName);
                }
                slot.setAttachment(attachment);
                return;
            }
        }
        throw new Error("Slot not found: " + slotName);
    }
    /** Finds an IK constraint by comparing each IK constraint's name. It is more efficient to cache the results of this method
     * than to call it repeatedly.
     * @return May be null. */
    findIkConstraint(constraintName) {
        if (!constraintName)
            throw new Error("constraintName cannot be null.");
        return this.ikConstraints.find((constraint) => constraint.data.name == constraintName) ?? null;
    }
    /** Finds a transform constraint by comparing each transform constraint's name. It is more efficient to cache the results of
     * this method than to call it repeatedly.
     * @return May be null. */
    findTransformConstraint(constraintName) {
        if (!constraintName)
            throw new Error("constraintName cannot be null.");
        return this.transformConstraints.find((constraint) => constraint.data.name == constraintName) ?? null;
    }
    /** Finds a path constraint by comparing each path constraint's name. It is more efficient to cache the results of this method
     * than to call it repeatedly.
     * @return May be null. */
    findPathConstraint(constraintName) {
        if (!constraintName)
            throw new Error("constraintName cannot be null.");
        return this.pathConstraints.find((constraint) => constraint.data.name == constraintName) ?? null;
    }
    /** Finds a physics constraint by comparing each physics constraint's name. It is more efficient to cache the results of this
     * method than to call it repeatedly. */
    findPhysicsConstraint(constraintName) {
        if (constraintName == null)
            throw new Error("constraintName cannot be null.");
        return this.physicsConstraints.find((constraint) => constraint.data.name == constraintName) ?? null;
    }
    /** Returns the axis aligned bounding box (AABB) of the region and mesh attachments for the current pose as `{ x: number, y: number, width: number, height: number }`.
     * Note that this method will create temporary objects which can add to garbage collection pressure. Use `getBounds()` if garbage collection is a concern. */
    getBoundsRect(clipper) {
        let offset = new Vector2();
        let size = new Vector2();
        this.getBounds(offset, size, undefined, clipper);
        return { x: offset.x, y: offset.y, width: size.x, height: size.y };
    }
    /** Returns the axis aligned bounding box (AABB) of the region and mesh attachments for the current pose.
     * @param offset An output value, the distance from the skeleton origin to the bottom left corner of the AABB.
     * @param size An output value, the width and height of the AABB.
     * @param temp Working memory to temporarily store attachments' computed world vertices.
     * @param clipper {@link SkeletonClipping} to use. If <code>null</code>, no clipping is applied. */
    getBounds(offset, size, temp = new Array(2), clipper = null) {
        if (!offset)
            throw new Error("offset cannot be null.");
        if (!size)
            throw new Error("size cannot be null.");
        let drawOrder = this.drawOrder;
        let minX = Number.POSITIVE_INFINITY, minY = Number.POSITIVE_INFINITY, maxX = Number.NEGATIVE_INFINITY, maxY = Number.NEGATIVE_INFINITY;
        for (let i = 0, n = drawOrder.length; i < n; i++) {
            let slot = drawOrder[i];
            if (!slot.bone.active)
                continue;
            let verticesLength = 0;
            let vertices = null;
            let triangles = null;
            let attachment = slot.getAttachment();
            if (attachment instanceof RegionAttachment) {
                verticesLength = 8;
                vertices = Utils.setArraySize(temp, verticesLength, 0);
                attachment.computeWorldVertices(slot, vertices, 0, 2);
                triangles = Skeleton.quadTriangles;
            }
            else if (attachment instanceof MeshAttachment) {
                let mesh = attachment;
                verticesLength = mesh.worldVerticesLength;
                vertices = Utils.setArraySize(temp, verticesLength, 0);
                mesh.computeWorldVertices(slot, 0, verticesLength, vertices, 0, 2);
                triangles = mesh.triangles;
            }
            else if (attachment instanceof ClippingAttachment && clipper != null) {
                clipper.clipStart(slot, attachment);
                continue;
            }
            if (vertices && triangles) {
                if (clipper != null && clipper.isClipping()) {
                    clipper.clipTriangles(vertices, triangles, triangles.length);
                    vertices = clipper.clippedVertices;
                    verticesLength = clipper.clippedVertices.length;
                }
                for (let ii = 0, nn = vertices.length; ii < nn; ii += 2) {
                    let x = vertices[ii], y = vertices[ii + 1];
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                }
            }
            if (clipper != null)
                clipper.clipEndWithSlot(slot);
        }
        if (clipper != null)
            clipper.clipEnd();
        offset.set(minX, minY);
        size.set(maxX - minX, maxY - minY);
    }
    /** Increments the skeleton's {@link #time}. */
    update(delta) {
        this.time += delta;
    }
    physicsTranslate(x, y) {
        const physicsConstraints = this.physicsConstraints;
        for (let i = 0, n = physicsConstraints.length; i < n; i++)
            physicsConstraints[i].translate(x, y);
    }
    /** Calls {@link PhysicsConstraint#rotate(float, float, float)} for each physics constraint. */
    physicsRotate(x, y, degrees) {
        const physicsConstraints = this.physicsConstraints;
        for (let i = 0, n = physicsConstraints.length; i < n; i++)
            physicsConstraints[i].rotate(x, y, degrees);
    }
}
/** Determines how physics and other non-deterministic updates are applied. */
export var Physics;
(function (Physics) {
    /** Physics are not updated or applied. */
    Physics[Physics["none"] = 0] = "none";
    /** Physics are reset to the current pose. */
    Physics[Physics["reset"] = 1] = "reset";
    /** Physics are updated and the pose from physics is applied. */
    Physics[Physics["update"] = 2] = "update";
    /** Physics are not updated but the pose from physics is applied. */
    Physics[Physics["pose"] = 3] = "pose";
})(Physics || (Physics = {}));
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiU2tlbGV0b24uanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyIuLi9zcmMvU2tlbGV0b24udHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OzsrRUEyQitFO0FBRy9FLE9BQU8sRUFBRSxrQkFBa0IsRUFBRSxNQUFNLHFDQUFxQyxDQUFDO0FBQ3pFLE9BQU8sRUFBRSxjQUFjLEVBQUUsTUFBTSxpQ0FBaUMsQ0FBQztBQUNqRSxPQUFPLEVBQUUsY0FBYyxFQUFFLE1BQU0saUNBQWlDLENBQUM7QUFDakUsT0FBTyxFQUFFLGdCQUFnQixFQUFFLE1BQU0sbUNBQW1DLENBQUM7QUFDckUsT0FBTyxFQUFFLElBQUksRUFBRSxNQUFNLFdBQVcsQ0FBQztBQUNqQyxPQUFPLEVBQUUsWUFBWSxFQUFFLE1BQU0sbUJBQW1CLENBQUM7QUFDakQsT0FBTyxFQUFFLGNBQWMsRUFBRSxNQUFNLHFCQUFxQixDQUFDO0FBQ3JELE9BQU8sRUFBRSxpQkFBaUIsRUFBRSxNQUFNLHdCQUF3QixDQUFDO0FBSTNELE9BQU8sRUFBRSxJQUFJLEVBQUUsTUFBTSxXQUFXLENBQUM7QUFDakMsT0FBTyxFQUFFLG1CQUFtQixFQUFFLE1BQU0sMEJBQTBCLENBQUM7QUFFL0QsT0FBTyxFQUFFLEtBQUssRUFBRSxLQUFLLEVBQUUsU0FBUyxFQUFFLE9BQU8sRUFBbUIsTUFBTSxZQUFZLENBQUM7QUFFL0U7O2tJQUVrSTtBQUNsSSxNQUFNLE9BQU8sUUFBUTtJQUNaLE1BQU0sQ0FBQyxhQUFhLEdBQUcsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxFQUFFLENBQUMsRUFBRSxDQUFDLEVBQUUsQ0FBQyxFQUFFLENBQUMsQ0FBQyxDQUFDO0lBQ2xELE1BQU0sQ0FBQyxLQUFLLEdBQUcsS0FBSyxDQUFDO0lBRXJCLHNDQUFzQztJQUN0QyxJQUFJLENBQWU7SUFFbkIseUZBQXlGO0lBQ3pGLEtBQUssQ0FBYztJQUVuQix5REFBeUQ7SUFDekQsS0FBSyxD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LEdBQUcsU0FBUyxDQUFDLE1BQU0sQ0FBQztRQUN6RSxNQUFNLEVBQUUsR0FBRyxJQUFJLENBQUMsR0FBRyxDQUFDLEVBQUUsQ0FBQyxHQUFHLFFBQVEsQ0FBQyxNQUFNLENBQUM7UUFDMUMsTUFBTSxFQUFFLEdBQUcsSUFBSSxDQUFDLEdBQUcsQ0FBQyxFQUFFLENBQUMsR0FBRyxRQUFRLENBQUMsTUFBTSxDQUFDO1FBQzFDLE1BQU0sRUFBRSxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsUUFBUSxDQUFDLE1BQU0sQ0FBQztRQUMxQyxNQUFNLEVBQUUsR0FBRyxJQUFJLENBQUMsR0FBRyxDQUFDLEVBQUUsQ0FBQyxHQUFHLFFBQVEsQ0FBQyxNQUFNLENBQUM7UUFDMUMsUUFBUSxDQUFDLENBQUMsR0FBRyxDQUFDLEVBQUUsR0FBRyxFQUFFLEdBQUcsRUFBRSxHQUFHLEVBQUUsQ0FBQyxHQUFHLElBQUksQ0FBQyxNQUFNLENBQUM7UUFDL0MsUUFBUSxDQUFDLENBQUMsR0FBRyxDQUFDLEVBQUUsR0FBRyxFQUFFLEdBQUcsRUFBRSxHQUFHLEVBQUUsQ0FBQyxHQUFHLElBQUksQ0FBQyxNQUFNLENBQUM7UUFDL0MsUUFBUSxDQUFDLENBQUMsR0FBRyxDQUFDLEVBQUUsR0FBRyxFQUFFLEdBQUcsRUFBRSxHQUFHLEVBQUUsQ0FBQyxHQUFHLElBQUksQ0FBQyxNQUFNLENBQUM7UUFDL0MsUUFBUSxDQUFDLENBQUMsR0FBRyxDQUFDLEVBQUUsR0FBRyxFQUFFLEdBQUcsRUFBRSxHQUFHLEVBQUUsQ0FBQyxHQUFHLElBQUksQ0FBQyxNQUFNLENBQUM7UUFFL0Msc0NBQXNDO1FBQ3RDLElBQUksV0FBVyxHQUFHLElBQUksQ0FBQyxZQUFZLENBQUM7UUFDcEMsS0FBSyxJQUFJLENBQUMsR0FBRyxDQUFDLEVBQUUsQ0FBQyxHQUFHLFdBQVcsQ0FBQyxNQUFNLEVBQUUsQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEVBQUUsRUFBRSxDQUFDO1lBQ3BELElBQUksU0FBUyxHQUFHLFdBQVcs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Q0FBQyxrQkFBa0IsQ0FBQztRQUNuRCxLQUFLLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsa0JBQWtCLENBQUMsTUFBTSxFQUFFLENBQUMsR0FBRyxDQUFDLEVBQUUsQ0FBQyxFQUFFO1lBQ3hELGtCQUFrQixDQUFDLENBQUMsQ0FBQyxDQUFDLFNBQVMsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxDQUFDLENBQUM7SUFDeEMsQ0FBQztJQUVELCtGQUErRjtJQUMvRixhQUFhLENBQUUsQ0FBUyxFQUFFLENBQVMsRUFBRSxPQUFlO1FBQ25ELE1BQU0sa0JBQWtCLEdBQUcsSUFBSSxDQUFDLGtCQUFrQixDQUFDO1FBQ25ELEtBQUssSUFBSSxDQUFDLEdBQUcsQ0FBQyxFQUFFLENBQUMsR0FBRyxrQkFBa0IsQ0FBQyxNQUFNLEVBQUUsQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEVBQUU7WUFDeEQsa0JBQWtCLENBQUMsQ0FBQyxDQUFDLENBQUMsTUFBTSxDQUFDLENBQUMsRUFBRSxDQUFDLEVBQUUsT0FBTyxDQUFDLENBQUM7SUFDOUMsQ0FBQzs7QUFHRiw4RUFBOEU7QUFDOUUsTUFBTSxDQUFOLElBQVksT0FZWDtBQVpELFdBQVksT0FBTztJQUNsQiwwQ0FBMEM7SUFDMUMscUNBQUksQ0FBQTtJQUVKLDZDQUE2QztJQUM3Qyx1Q0FBSyxDQUFBO0lBRUwsZ0VBQWdFO0lBQ2hFLHlDQUFNLENBQUE7SUFFTixvRUFBb0U7SUFDcEUscUNBQUksQ0FBQTtBQUNMLENBQUMsRUFaVyxPQUFPLEtBQVAsT0FBTyxRQVlsQiIsInNvdXJjZXNDb250ZW50IjpbIi8qKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKipcbiAqIFNwaW5lIFJ1bnRpbWVzIExpY2Vuc2UgQWdyZWVtZW50XG4gKiBMYXN0IHVwZGF0ZWQgQXByaWwgNSwgMjAyNS4gUmVwbGFjZXMgYWxsIHByaW9yIHZlcnNpb25zLlxuICpcbiAqIENvcHlyaWdodCAoYykgMjAxMy0yMDI1LCBFc290ZXJpYyBTb2Z0d2FyZSBMTENcbiAqXG4gKiBJbnRlZ3JhdGlvbiBvZiB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZSBvciBvdGhlcndpc2UgY3JlYXRpbmdcbiAqIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGlzIHBlcm1pdHRlZCB1bmRlciB0aGUgdGVybXMgYW5kXG4gKiBjb25kaXRpb25zIG9mIFNlY3Rpb24gMiBvZiB0aGUgU3BpbmUgRWRpdG9yIExpY2Vuc2UgQWdyZWVtZW50OlxuICogaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLWVkaXRvci1saWNlbnNlXG4gKlxuICogT3RoZXJ3aXNlLCBpdCBpcyBwZXJtaXR0ZWQgdG8gaW50ZWdyYXRlIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlXG4gKiBvciBvdGhlcndpc2UgY3JlYXRlIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIChjb2xsZWN0aXZlbHksXG4gKiBcIlByb2R1Y3RzXCIpLCBwcm92aWRlZCB0aGF0IGVhY2ggdXNlciBvZiB0aGUgUHJvZHVjdHMgbXVzdCBvYnRhaW4gdGhlaXIgb3duXG4gKiBTcGluZSBFZGl0b3IgbGljZW5zZSBhbmQgcmVkaXN0cmlidXRpb24gb2YgdGhlIFByb2R1Y3RzIGluIGFueSBmb3JtIG11c3RcbiAqIGluY2x1ZGUgdGhpcyBsaWNlbnNlIGFuZCBjb3B5cmlnaHQgbm90aWNlLlxuICpcbiAqIFRIRSBTUElORSBSVU5USU1FUyBBUkUgUFJPVklERUQgQlkgRVNPVEVSSUMgU09GVFdBUkUgTExDIFwiQVMgSVNcIiBBTkQgQU5ZXG4gKiBFWFBSRVNTIE9SIElNUExJRUQgV0FSUkFOVElFUywgSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFRIRSBJTVBMSUVEXG4gKiBXQVJSQU5USUVTIE9GIE1FUkNIQU5UQUJJTElUWSBBTkQgRklUTkVTUyBGT1IgQSBQQVJUSUNVTEFSIFBVUlBPU0UgQVJFXG4gKiBESVNDTEFJTUVELiBJTiBOTyBFVkVOVCBTSEFMTCBFU09URVJJQyBTT0ZUV0FSRSBMTEMgQkUgTElBQkxFIEZPUiBBTllcbiAqIERJUkVDVCwgSU5ESVJFQ1QsIElOQ0lERU5UQUwsIFNQRUNJQUwsIEVYRU1QTEFSWSwgT1IgQ09OU0VRVUVOVElBTCBEQU1BR0VTXG4gKiAoSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFBST0NVUkVNRU5UIE9GIFNVQlNUSVRVVEUgR09PRFMgT1IgU0VSVklDRVMsXG4gKiBCVVNJTkVTUyBJTlRFUlJVUFRJT04sIE9SIExPU1MgT0YgVVNFLCBEQVRBLCBPUiBQUk9GSVRTKSBIT1dFVkVSIENBVVNFRCBBTkRcbiAqIE9OIEFOWSBUSEVPUlkgT0YgTElBQklMSVRZLCBXSEVUSEVSIElOIENPTlRSQUNULCBTVFJJQ1QgTElBQklMSVRZLCBPUiBUT1JUXG4gKiAoSU5DTFVESU5HIE5FR0xJR0VOQ0UgT1IgT1RIRVJXSVNFKSBBUklTSU5HIElOIEFOWSBXQVkgT1VUIE9GIFRIRSBVU0UgT0ZcbiAqIFRIRSBTUElORSBSVU5USU1FUywgRVZFTiBJRiBBRFZJU0VEIE9GIFRIRSBQT1NTSUJJTElUWSBPRiBTVUNIIERBTUFHRS5cbiAqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKi9cblxuaW1wb3J0IHsgQXR0YWNobWVudCB9IGZyb20gXCIuL2F0dGFjaG1lbnRzL0F0dGFjaG1lbnQuanNcIjtcbmltcG9ydCB7IENsaXBwaW5nQXR0YWNobWVudCB9IGZyb20gXCIuL2F0dGFjaG1lbnRzL0NsaXBwaW5nQXR0YWNobWVudC5qc1wiO1xuaW1wb3J0IHsgTWVzaEF0dGFjaG1lbnQgfSBmcm9tIFwiLi9hdHRhY2htZW50cy9NZXNoQXR0YWNobWVudC5qc1wiO1xuaW1wb3J0IHsgUGF0aEF0dGFjaG1lbnQgfSBmcm9tIFwiLi9hdHRhY2htZW50cy9QYXRoQXR0YWNobWVudC5qc1wiO1xuaW1wb3J0IHsgUmVnaW9uQXR0YWNobWVudCB9IGZyb20gXCIuL2F0dGFjaG1lbnRzL1JlZ2lvbkF0dGFjaG1lbnQuanNcIjtcbmltcG9ydCB7IEJvbmUgfSBmcm9tIFwiLi9Cb25lLmpzXCI7XG5pbXBvcnQgeyBJa0NvbnN0cmFpbnQgfSBmcm9tIFwiLi9Ja0NvbnN0cmFpbnQuanNcIjtcbmltcG9ydCB7IFBhdGhDb25zdHJhaW50IH0gZnJvbSBcIi4vUGF0aENvbnN0cmFpbnQuanNcIjtcbmltcG9ydCB7IFBoeXNpY3NDb25zdHJhaW50IH0gZnJvbSBcIi4vUGh5c2ljc0NvbnN0cmFpbnQuanNcIjtcbmltcG9ydCB7IFNrZWxldG9uQ2xpcHBpbmcgfSBmcm9tIFwiLi9Ta2VsZXRvbkNsaXBwaW5nLmpzXCI7XG5pbXBvcnQgeyBTa2VsZXRvbkRhdGEgfSBmcm9tIFwiLi9Ta2VsZXRvbkRhdGEuanNcIjtcbmltcG9ydCB7IFNraW4gfSBmcm9tIFwiLi9Ta2luLmpzXCI7XG5pbXBvcnQgeyBTbG90IH0gZnJvbSBcIi4vU2xvdC5qc1wiO1xuaW1wb3J0IHsgVHJhbnNmb3JtQ29uc3RyYWludCB9IGZyb20gXCIuL1RyYW5zZm9ybUNvbnN0cmFpbnQuanNcIjtcbmltcG9ydCB7IFVwZGF0YWJsZSB9IGZyb20gXCIuL1VwZGF0YWJsZS5qc1wiO1xuaW1wb3J0IHsgQ29sb3IsIFV0aWxzLCBNYXRoVXRpbHMsIFZlY3RvcjIsIE51bWJlckFycmF5TGlrZSB9IGZyb20gXCIuL1V0aWxzLmpzXCI7XG5cbi8qKiBTdG9yZXMgdGhlIGN1cnJlbnQgcG9zZSBmb3IgYSBza2VsZXRvbi5cbiAqXG4gKiBTZWUgW0luc3RhbmNlIG9iamVjdHNdKGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1ydW50aW1lLWFyY2hpdGVjdHVyZSNJbnN0YW5jZS1vYmplY3RzKSBpbiB0aGUgU3BpbmUgUnVudGltZXMgR3VpZGUuICovXG5leHBvcnQgY2xhc3MgU2tlbGV0b24ge1xuXHRwcml2YXRlIHN0YXRpYyBxdWFkVHJpYW5nbGVzID0gWzAsIDEsIDIsIDIsIDMsIDBdO1xuXHRzdGF0aWMgeURvd24gPSBmYWxzZTtcblxuXHQvKiogVGhlIHNrZWxldG9uJ3Mgc2V0dXAgcG9zZSBkYXRhLiAqL1xuXHRkYXRhOiBTa2VsZXRvbkRhdGE7XG5cblx0LyoqIFRoZSBza2VsZXRvbidzIGJvbmVzLCBzb3J0ZWQgcGFyZW50IGZpcnN0LiBUaGUgcm9vdCBib25lIGlzIGFsd2F5cyB0aGUgZmlyc3QgYm9uZS4gKi9cblx0Ym9uZXM6IEFycmF5PEJvbmU+O1xuXG5cdC8qKiBUaGUgc2tlbGV0b24ncyBzbG90cyBpbiB0aGUgc2V0dXAgcG9zZSBkcmF3IG9yZGVyLiAqL1xuXHRzbG90czogQXJyYXk8U2xvdD47XG5cblx0LyoqIFRoZSBza2VsZXRvbidzIHNsb3RzIGluIHRoZSBvcmRlciB0aGV5IHNob3VsZCBiZSBkcmF3bi4gVGhlIHJldHVybmVkIGFycmF5IG1heSBiZSBtb2RpZmllZCB0byBjaGFuZ2UgdGhlIGRyYXcgb3JkZXIuICovXG5cdGRyYXdPcmRlcjogQXJyYXk8U2xvdD47XG5cblx0LyoqIFRoZSBza2VsZXRvbidzIElLIGNvbnN0cmFpbnRzLiAqL1xuXHRpa0NvbnN0cmFpbnRzOiBBcnJheTxJa0NvbnN0cmFpbnQ+O1xuXG5cdC8qKiBUaGUgc2tlbGV0b24ncyB0cmFuc2Zvcm0gY29uc3RyYWludHMuICovXG5cdHRyYW5zZm9ybUNvbnN0cmFpbnRzOiBBcnJheTxUcmFuc2Zvcm1Db25zdHJhaW50PjtcblxuXHQvKiogVGhlIHNrZWxldG9uJ3MgcGF0aCBjb25zdHJhaW50cy4gKi9cblx0cGF0aENvbnN0cmFpbnRzOiBBcnJheTxQYXRoQ29uc3RyYWludD47XG5cblxuXHQvKiogVGhlIHNrZWxldG9uJ3MgcGh5c2ljcyBjb25zdHJhaW50cy4gKi9cblx0cGh5c2ljc0NvbnN0cmFpbnRzOiBBcnJheTxQaHlzaWNzQ29uc3RyYWludD47XG5cblx0LyoqIFRoZSBsaXN0IG9mIGJvbmVzIGFuZCBjb25zdHJhaW50cywgc29ydGVkIGluIHRoZSBvcmRlciB0aGV5IHNob3VsZCBiZSB1cGRhdGVkLCBhcyBjb21wdXRlZCBieSB7QGxpbmsgI3VwZGF0ZUNhY2hlKCl9LiAqL1xuXHRfdXBkYXRlQ2FjaGUgPSBuZXcgQXJyYXk8VXBkYXRhYmxlPigpO1xuXG5cdC8qKiBUaGUgc2tlbGV0b24ncyBjdXJyZW50IHNraW4uIE1heSBiZSBudWxsLiAqL1xuXHRza2luOiBTa2luIHwgbnVsbCA9IG51bGw7XG5cblx0LyoqIFRoZSBjb2xvciB0byB0aW50IGFsbCB0aGUgc2tlbGV0b24ncyBhdHRhY2htZW50cy4gKi9cblx0Y29sb3I6IENvbG9yO1xuXG5cdC8qKiBTY2FsZXMgdGhlIGVudGlyZSBza2VsZXRvbiBvbiB0aGUgWCBheGlzLiBUaGlzIGFmZmVjdHMgYWxsIGJvbmVzLCBldmVuIGlmIHRoZSBib25lJ3MgdHJhbnNmb3JtIG1vZGUgZGlzYWxsb3dzIHNjYWxlXG5cdCAgKiBpbmhlcml0YW5jZS4gKi9cblx0c2NhbGVYID0gMTtcblxuXHQvKiogU2NhbGVzIHRoZSBlbnRpcmUgc2tlbGV0b24gb24gdGhlIFkgYXhpcy4gVGhpcyBhZmZlY3RzIGFsbCBib25lcywgZXZlbiBpZiB0aGUgYm9uZSdzIHRyYW5zZm9ybSBtb2RlIGRpc2FsbG93cyBzY2FsZVxuXHQgICogaW5oZXJpdGFuY2UuICovXG5cdHByaXZhdGUgX3NjYWxlWSA9IDE7XG5cblx0cHVibGljIGdldCBzY2FsZVkgKCkge1xuXHRcdHJldHVybiBTa2VsZXRvbi55RG93biA/IC10aGlzLl9zY2FsZVkgOiB0aGlzLl9zY2FsZVk7XG5cdH1cblxuXHRwdWJsaWMgc2V0IHNjYWxlWSAoc2NhbGVZOiBudW1iZXIpIHtcblx0XHR0aGlzLl9zY2FsZVkgPSBzY2FsZVk7XG5cdH1cblxuXHQvKiogU2V0cyB0aGUgc2tlbGV0b24gWCBwb3NpdGlvbiwgd2hpY2ggaXMgYWRkZWQgdG8gdGhlIHJvb3QgYm9uZSB3b3JsZFggcG9zaXRpb24uICovXG5cdHggPSAwO1xuXG5cdC8qKiBTZXRzIHRoZSBza2VsZXRvbiBZIHBvc2l0aW9uLCB3aGljaCBpcyBhZGRlZCB0byB0aGUgcm9vdCBib25lIHdvcmxkWSBwb3NpdGlvbi4gKi9cblx0eSA9IDA7XG5cblx0LyoqIFJldHVybnMgdGhlIHNrZWxldG9uJ3MgdGltZS4gVGhpcyBpcyB1c2VkIGZvciB0aW1lLWJhc2VkIG1hbmlwdWxhdGlvbnMsIHN1Y2ggYXMge0BsaW5rIFBoeXNpY3NDb25zdHJhaW50fS5cblx0ICogPHA+XG5cdCAqIFNlZSB7QGxpbmsgI3VwZGF0ZShmbG9hdCl9LiAqL1xuXHR0aW1lID0gMDtcblxuXHRjb25zdHJ1Y3RvciAoZGF0YTogU2tlbGV0b25EYXRhKSB7XG5cdFx0aWYgKCFkYXRhKSB0aHJvdyBuZXcgRXJyb3IoXCJkYXRhIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHR0aGlzLmRhdGEgPSBkYXRhO1xuXG5cdFx0dGhpcy5ib25lcyA9IG5ldyBBcnJheTxCb25lPigpO1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgZGF0YS5ib25lcy5sZW5ndGg7IGkrKykge1xuXHRcdFx0bGV0IGJvbmVEYXRhID0gZGF0YS5ib25lc1tpXTtcblx0XHRcdGxldCBib25lOiBCb25lO1xuXHRcdFx0aWYgKCFib25lRGF0YS5wYXJlbnQpXG5cdFx0XHRcdGJvbmUgPSBuZXcgQm9uZShib25lRGF0YSwgdGhpcywgbnVsbCk7XG5cdFx0XHRlbHNlIHtcblx0XHRcdFx0bGV0IHBhcmVudCA9IHRoaXMuYm9uZXNbYm9uZURhdGEucGFyZW50LmluZGV4XTtcblx0XHRcdFx0Ym9uZSA9IG5ldyBCb25lKGJvbmVEYXRhLCB0aGlzLCBwYXJlbnQpO1xuXHRcdFx0XHRwYXJlbnQuY2hpbGRyZW4ucHVzaChib25lKTtcblx0XHRcdH1cblx0XHRcdHRoaXMuYm9uZXMucHVzaChib25lKTtcblx0XHR9XG5cblx0XHR0aGlzLnNsb3RzID0gbmV3IEFycmF5PFNsb3Q+KCk7XG5cdFx0dGhpcy5kcmF3T3JkZXIgPSBuZXcgQXJyYXk8U2xvdD4oKTtcblx0XHRmb3IgKGxldCBpID0gMDsgaSA8IGRhdGEuc2xvdHMubGVuZ3RoOyBpKyspIHtcblx0XHRcdGxldCBzbG90RGF0YSA9IGRhdGEuc2xvdHNbaV07XG5cdFx0XHRsZXQgYm9uZSA9IHRoaXMuYm9uZXNbc2xvdERhdGEuYm9uZURhdGEuaW5kZXhdO1xuXHRcdFx0bGV0IHNsb3QgPSBuZXcgU2xvdChzbG90RGF0YSwgYm9uZSk7XG5cdFx0XHR0aGlzLnNsb3RzLnB1c2goc2xvdCk7XG5cdFx0XHR0aGlzLmRyYXdPcmRlci5wdXNoKHNsb3QpO1xuXHRcdH1cblxuXHRcdHRoaXMuaWtDb25zdHJhaW50cyA9IG5ldyBBcnJheTxJa0NvbnN0cmFpbnQ+KCk7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBkYXRhLmlrQ29uc3RyYWludHMubGVuZ3RoOyBpKyspIHtcblx0XHRcdGxldCBpa0NvbnN0cmFpbnREYXRhID0gZGF0YS5pa0NvbnN0cmFpbnRzW2ldO1xuXHRcdFx0dGhpcy5pa0NvbnN0cmFpbnRzLnB1c2gobmV3IElrQ29uc3RyYWludChpa0NvbnN0cmFpbnREYXRhLCB0aGlzKSk7XG5cdFx0fVxuXG5cdFx0dGhpcy50cmFuc2Zvcm1Db25zdHJhaW50cyA9IG5ldyBBcnJheTxUcmFuc2Zvcm1Db25zdHJhaW50PigpO1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgZGF0YS50cmFuc2Zvcm1Db25zdHJhaW50cy5sZW5ndGg7IGkrKykge1xuXHRcdFx0bGV0IHRyYW5zZm9ybUNvbnN0cmFpbnREYXRhID0gZGF0YS50cmFuc2Zvcm1Db25zdHJhaW50c1tpXTtcblx0XHRcdHRoaXMudHJhbnNmb3JtQ29uc3RyYWludHMucHVzaChuZXcgVHJhbnNmb3JtQ29uc3RyYWludCh0cmFuc2Zvcm1Db25zdHJhaW50RGF0YSwgdGhpcykpO1xuXHRcdH1cblxuXHRcdHRoaXMucGF0aENvbnN0cmFpbnRzID0gbmV3IEFycmF5PFBhdGhDb25zdHJhaW50PigpO1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgZGF0YS5wYXRoQ29uc3RyYWludHMubGVuZ3RoOyBpKyspIHtcblx0XHRcdGxldCBwYXRoQ29uc3RyYWludERhdGEgPSBkYXRhLnBhdGhDb25zdHJhaW50c1tpXTtcblx0XHRcdHRoaXMucGF0aENvbnN0cmFpbnRzLnB1c2gobmV3IFBhdGhDb25zdHJhaW50KHBhdGhDb25zdHJhaW50RGF0YSwgdGhpcykpO1xuXHRcdH1cblxuXHRcdHRoaXMucGh5c2ljc0NvbnN0cmFpbnRzID0gbmV3IEFycmF5PFBoeXNpY3NDb25zdHJhaW50PigpO1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgZGF0YS5waHlzaWNzQ29uc3RyYWludHMubGVuZ3RoOyBpKyspIHtcblx0XHRcdGxldCBwaHlzaWNzQ29uc3RyYWludERhdGEgPSBkYXRhLnBoeXNpY3NDb25zdHJhaW50c1tpXTtcblx0XHRcdHRoaXMucGh5c2ljc0NvbnN0cmFpbnRzLnB1c2gobmV3IFBoeXNpY3NDb25zdHJhaW50KHBoeXNpY3NDb25zdHJhaW50RGF0YSwgdGhpcykpO1xuXHRcdH1cblxuXHRcdHRoaXMuY29sb3IgPSBuZXcgQ29sb3IoMSwgMSwgMSwgMSk7XG5cdFx0dGhpcy51cGRhdGVDYWNoZSgpO1xuXHR9XG5cblx0LyoqIENhY2hlcyBpbmZvcm1hdGlvbiBhYm91dCBib25lcyBhbmQgY29uc3RyYWludHMuIE11c3QgYmUgY2FsbGVkIGlmIHRoZSB7QGxpbmsgI2dldFNraW4oKX0gaXMgbW9kaWZpZWQgb3IgaWYgYm9uZXMsXG5cdCAqIGNvbnN0cmFpbnRzLCBvciB3ZWlnaHRlZCBwYXRoIGF0dGFjaG1lbnRzIGFyZSBhZGRlZCBvciByZW1vdmVkLiAqL1xuXHR1cGRhdGVDYWNoZSAoKSB7XG5cdFx0bGV0IHVwZGF0ZUNhY2hlID0gdGhpcy5fdXBkYXRlQ2FjaGU7XG5cdFx0dXBkYXRlQ2FjaGUubGVuZ3RoID0gMDtcblxuXHRcdGxldCBib25lcyA9IHRoaXMuYm9uZXM7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBib25lcy5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBib25lID0gYm9uZXNbaV07XG5cdFx0XHRib25lLnNvcnRlZCA9IGJvbmUuZGF0YS5za2luUmVxdWlyZWQ7XG5cdFx0XHRib25lLmFjdGl2ZSA9ICFib25lLnNvcnRlZDtcblx0XHR9XG5cblx0XHRpZiAodGhpcy5za2luKSB7XG5cdFx0XHRsZXQgc2tpbkJvbmVzID0gdGhpcy5za2luLmJvbmVzO1xuXHRcdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSB0aGlzLnNraW4uYm9uZXMubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRcdGxldCBib25lOiBCb25lIHwgbnVsbCA9IHRoaXMuYm9uZXNbc2tpbkJvbmVzW2ldLmluZGV4XTtcblx0XHRcdFx0ZG8ge1xuXHRcdFx0XHRcdGJvbmUuc29ydGVkID0gZmFsc2U7XG5cdFx0XHRcdFx0Ym9uZS5hY3RpdmUgPSB0cnVlO1xuXHRcdFx0XHRcdGJvbmUgPSBib25lLnBhcmVudDtcblx0XHRcdFx0fSB3aGlsZSAoYm9uZSk7XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0Ly8gSUsgZmlyc3QsIGxvd2VzdCBoaWVyYXJjaHkgZGVwdGggZmlyc3QuXG5cdFx0bGV0IGlrQ29uc3RyYWludHMgPSB0aGlzLmlrQ29uc3RyYWludHM7XG5cdFx0bGV0IHRyYW5zZm9ybUNvbnN0cmFpbnRzID0gdGhpcy50cmFuc2Zvcm1Db25zdHJhaW50cztcblx0XHRsZXQgcGF0aENvbnN0cmFpbnRzID0gdGhpcy5wYXRoQ29uc3RyYWludHM7XG5cdFx0bGV0IHBoeXNpY3NDb25zdHJhaW50cyA9IHRoaXMucGh5c2ljc0NvbnN0cmFpbnRzO1xuXHRcdGxldCBpa0NvdW50ID0gaWtDb25zdHJhaW50cy5sZW5ndGgsIHRyYW5zZm9ybUNvdW50ID0gdHJhbnNmb3JtQ29uc3RyYWludHMubGVuZ3RoLCBwYXRoQ291bnQgPSBwYXRoQ29uc3RyYWludHMubGVuZ3RoLCBwaHlzaWNzQ291bnQgPSB0aGlzLnBoeXNpY3NDb25zdHJhaW50cy5sZW5ndGg7XG5cdFx0bGV0IGNvbnN0cmFpbnRDb3VudCA9IGlrQ291bnQgKyB0cmFuc2Zvcm1Db3VudCArIHBhdGhDb3VudCArIHBoeXNpY3NDb3VudDtcblxuXHRcdG91dGVyOlxuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgY29uc3RyYWludENvdW50OyBpKyspIHtcblx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCBpa0NvdW50OyBpaSsrKSB7XG5cdFx0XHRcdGxldCBjb25zdHJhaW50ID0gaWtDb25zdHJhaW50c1tpaV07XG5cdFx0XHRcdGlmIChjb25zdHJhaW50LmRhdGEub3JkZXIgPT0gaSkge1xuXHRcdFx0XHRcdHRoaXMuc29ydElrQ29uc3RyYWludChjb25zdHJhaW50KTtcblx0XHRcdFx0XHRjb250aW51ZSBvdXRlcjtcblx0XHRcdFx0fVxuXHRcdFx0fVxuXHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IHRyYW5zZm9ybUNvdW50OyBpaSsrKSB7XG5cdFx0XHRcdGxldCBjb25zdHJhaW50ID0gdHJhbnNmb3JtQ29uc3RyYWludHNbaWldO1xuXHRcdFx0XHRpZiAoY29uc3RyYWludC5kYXRhLm9yZGVyID09IGkpIHtcblx0XHRcdFx0XHR0aGlzLnNvcnRUcmFuc2Zvcm1Db25zdHJhaW50KGNvbnN0cmFpbnQpO1xuXHRcdFx0XHRcdGNvbnRpbnVlIG91dGVyO1xuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgcGF0aENvdW50OyBpaSsrKSB7XG5cdFx0XHRcdGxldCBjb25zdHJhaW50ID0gcGF0aENvbnN0cmFpbnRzW2lpXTtcblx0XHRcdFx0aWYgKGNvbnN0cmFpbnQuZGF0YS5vcmRlciA9PSBpKSB7XG5cdFx0XHRcdFx0dGhpcy5zb3J0UGF0aENvbnN0cmFpbnQoY29uc3RyYWludCk7XG5cdFx0XHRcdFx0Y29udGludWUgb3V0ZXI7XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCBwaHlzaWNzQ291bnQ7IGlpKyspIHtcblx0XHRcdFx0Y29uc3QgY29uc3RyYWludCA9IHBoeXNpY3NDb25zdHJhaW50c1tpaV07XG5cdFx0XHRcdGlmIChjb25zdHJhaW50LmRhdGEub3JkZXIgPT0gaSkge1xuXHRcdFx0XHRcdHRoaXMuc29ydFBoeXNpY3NDb25zdHJhaW50KGNvbnN0cmFpbnQpO1xuXHRcdFx0XHRcdGNvbnRpbnVlIG91dGVyO1xuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBib25lcy5sZW5ndGg7IGkgPCBuOyBpKyspXG5cdFx0XHR0aGlzLnNvcnRCb25lKGJvbmVzW2ldKTtcblx0fVxuXG5cdHNvcnRJa0NvbnN0cmFpbnQgKGNvbnN0cmFpbnQ6IElrQ29uc3RyYWludCkge1xuXHRcdGNvbnN0cmFpbnQuYWN0aXZlID0gY29uc3RyYWludC50YXJnZXQuaXNBY3RpdmUoKSAmJiAoIWNvbnN0cmFpbnQuZGF0YS5za2luUmVxdWlyZWQgfHwgKHRoaXMuc2tpbiAmJiBVdGlscy5jb250YWlucyh0aGlzLnNraW4uY29uc3RyYWludHMsIGNvbnN0cmFpbnQuZGF0YSwgdHJ1ZSkpKSE7XG5cdFx0aWYgKCFjb25zdHJhaW50LmFjdGl2ZSkgcmV0dXJuO1xuXG5cdFx0bGV0IHRhcmdldCA9IGNvbnN0cmFpbnQudGFyZ2V0O1xuXHRcdHRoaXMuc29ydEJvbmUodGFyZ2V0KTtcblxuXHRcdGxldCBjb25zdHJhaW5lZCA9IGNvbnN0cmFpbnQuYm9uZXM7XG5cdFx0bGV0IHBhcmVudCA9IGNvbnN0cmFpbmVkWzBdO1xuXHRcdHRoaXMuc29ydEJvbmUocGFyZW50KTtcblxuXHRcdGlmIChjb25zdHJhaW5lZC5sZW5ndGggPT0gMSkge1xuXHRcdFx0dGhpcy5fdXBkYXRlQ2FjaGUucHVzaChjb25zdHJhaW50KTtcblx0XHRcdHRoaXMuc29ydFJlc2V0KHBhcmVudC5jaGlsZHJlbik7XG5cdFx0fSBlbHNlIHtcblx0XHRcdGxldCBjaGlsZCA9IGNvbnN0cmFpbmVkW2NvbnN0cmFpbmVkLmxlbmd0aCAtIDFdO1xuXHRcdFx0dGhpcy5zb3J0Qm9uZShjaGlsZCk7XG5cblx0XHRcdHRoaXMuX3VwZGF0ZUNhY2hlLnB1c2goY29uc3RyYWludCk7XG5cblx0XHRcdHRoaXMuc29ydFJlc2V0KHBhcmVudC5jaGlsZHJlbik7XG5cdFx0XHRjaGlsZC5zb3J0ZWQgPSB0cnVlO1xuXHRcdH1cblx0fVxuXG5cdHNvcnRQYXRoQ29uc3RyYWludCAoY29uc3RyYWludDogUGF0aENvbnN0cmFpbnQpIHtcblx0XHRjb25zdHJhaW50LmFjdGl2ZSA9IGNvbnN0cmFpbnQudGFyZ2V0LmJvbmUuaXNBY3RpdmUoKSAmJiAoIWNvbnN0cmFpbnQuZGF0YS5za2luUmVxdWlyZWQgfHwgKHRoaXMuc2tpbiAmJiBVdGlscy5jb250YWlucyh0aGlzLnNraW4uY29uc3RyYWludHMsIGNvbnN0cmFpbnQuZGF0YSwgdHJ1ZSkpKSE7XG5cdFx0aWYgKCFjb25zdHJhaW50LmFjdGl2ZSkgcmV0dXJuO1xuXG5cdFx0bGV0IHNsb3QgPSBjb25zdHJhaW50LnRhcmdldDtcblx0XHRsZXQgc2xvdEluZGV4ID0gc2xvdC5kYXRhLmluZGV4O1xuXHRcdGxldCBzbG90Qm9uZSA9IHNsb3QuYm9uZTtcblx0XHRpZiAodGhpcy5za2luKSB0aGlzLnNvcnRQYXRoQ29uc3RyYWludEF0dGFjaG1lbnQodGhpcy5za2luLCBzbG90SW5kZXgsIHNsb3RCb25lKTtcblx0XHRpZiAodGhpcy5kYXRhLmRlZmF1bHRTa2luICYmIHRoaXMuZGF0YS5kZWZhdWx0U2tpbiAhPSB0aGlzLnNraW4pXG5cdFx0XHR0aGlzLnNvcnRQYXRoQ29uc3RyYWludEF0dGFjaG1lbnQodGhpcy5kYXRhLmRlZmF1bHRTa2luLCBzbG90SW5kZXgsIHNsb3RCb25lKTtcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IHRoaXMuZGF0YS5za2lucy5sZW5ndGg7IGkgPCBuOyBpKyspXG5cdFx0XHR0aGlzLnNvcnRQYXRoQ29uc3RyYWludEF0dGFjaG1lbnQodGhpcy5kYXRhLnNraW5zW2ldLCBzbG90SW5kZXgsIHNsb3RCb25lKTtcblxuXHRcdGxldCBhdHRhY2htZW50ID0gc2xvdC5nZXRBdHRhY2htZW50KCk7XG5cdFx0aWYgKGF0dGFjaG1lbnQgaW5zdGFuY2VvZiBQYXRoQXR0YWNobWVudCkgdGhpcy5zb3J0UGF0aENvbnN0cmFpbnRBdHRhY2htZW50V2l0aChhdHRhY2htZW50LCBzbG90Qm9uZSk7XG5cblx0XHRsZXQgY29uc3RyYWluZWQgPSBjb25zdHJhaW50LmJvbmVzO1xuXHRcdGxldCBib25lQ291bnQgPSBjb25zdHJhaW5lZC5sZW5ndGg7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBib25lQ291bnQ7IGkrKylcblx0XHRcdHRoaXMuc29ydEJvbmUoY29uc3RyYWluZWRbaV0pO1xuXG5cdFx0dGhpcy5fdXBkYXRlQ2FjaGUucHVzaChjb25zdHJhaW50KTtcblxuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgYm9uZUNvdW50OyBpKyspXG5cdFx0XHR0aGlzLnNvcnRSZXNldChjb25zdHJhaW5lZFtpXS5jaGlsZHJlbik7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBib25lQ291bnQ7IGkrKylcblx0XHRcdGNvbnN0cmFpbmVkW2ldLnNvcnRlZCA9IHRydWU7XG5cdH1cblxuXHRzb3J0VHJhbnNmb3JtQ29uc3RyYWludCAoY29uc3RyYWludDogVHJhbnNmb3JtQ29uc3RyYWludCkge1xuXHRcdGNvbnN0cmFpbnQuYWN0aXZlID0gY29uc3RyYWludC50YXJnZXQuaXNBY3RpdmUoKSAmJiAoIWNvbnN0cmFpbnQuZGF0YS5za2luUmVxdWlyZWQgfHwgKHRoaXMuc2tpbiAmJiBVdGlscy5jb250YWlucyh0aGlzLnNraW4uY29uc3RyYWludHMsIGNvbnN0cmFpbnQuZGF0YSwgdHJ1ZSkpKSE7XG5cdFx0aWYgKCFjb25zdHJhaW50LmFjdGl2ZSkgcmV0dXJuO1xuXG5cdFx0dGhpcy5zb3J0Qm9uZShjb25zdHJhaW50LnRhcmdldCk7XG5cblx0XHRsZXQgY29uc3RyYWluZWQgPSBjb25zdHJhaW50LmJvbmVzO1xuXHRcdGxldCBib25lQ291bnQgPSBjb25zdHJhaW5lZC5sZW5ndGg7XG5cdFx0aWYgKGNvbnN0cmFpbnQuZGF0YS5sb2NhbCkge1xuXHRcdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBib25lQ291bnQ7IGkrKykge1xuXHRcdFx0XHRsZXQgY2hpbGQgPSBjb25zdHJhaW5lZFtpXTtcblx0XHRcdFx0dGhpcy5zb3J0Qm9uZShjaGlsZC5wYXJlbnQhKTtcblx0XHRcdFx0dGhpcy5zb3J0Qm9uZShjaGlsZCk7XG5cdFx0XHR9XG5cdFx0fSBlbHNlIHtcblx0XHRcdGZvciAobGV0IGkgPSAwOyBpIDwgYm9uZUNvdW50OyBpKyspIHtcblx0XHRcdFx0dGhpcy5zb3J0Qm9uZShjb25zdHJhaW5lZFtpXSk7XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0dGhpcy5fdXBkYXRlQ2FjaGUucHVzaChjb25zdHJhaW50KTtcblxuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgYm9uZUNvdW50OyBpKyspXG5cdFx0XHR0aGlzLnNvcnRSZXNldChjb25zdHJhaW5lZFtpXS5jaGlsZHJlbik7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBib25lQ291bnQ7IGkrKylcblx0XHRcdGNvbnN0cmFpbmVkW2ldLnNvcnRlZCA9IHRydWU7XG5cdH1cblxuXHRzb3J0UGF0aENvbnN0cmFpbnRBdHRhY2htZW50IChza2luOiBTa2luLCBzbG90SW5kZXg6IG51bWJlciwgc2xvdEJvbmU6IEJvbmUpIHtcblx0XHRsZXQgYXR0YWNobWVudHMgPSBza2luLmF0dGFjaG1lbnRzW3Nsb3RJbmRleF07XG5cdFx0aWYgKCFhdHRhY2htZW50cykgcmV0dXJuO1xuXHRcdGZvciAobGV0IGtleSBpbiBhdHRhY2htZW50cykge1xuXHRcdFx0dGhpcy5zb3J0UGF0aENvbnN0cmFpbnRBdHRhY2htZW50V2l0aChhdHRhY2htZW50c1trZXldLCBzbG90Qm9uZSk7XG5cdFx0fVxuXHR9XG5cblx0c29ydFBhdGhDb25zdHJhaW50QXR0YWNobWVudFdpdGggKGF0dGFjaG1lbnQ6IEF0dGFjaG1lbnQsIHNsb3RCb25lOiBCb25lKSB7XG5cdFx0aWYgKCEoYXR0YWNobWVudCBpbnN0YW5jZW9mIFBhdGhBdHRhY2htZW50KSkgcmV0dXJuO1xuXHRcdGxldCBwYXRoQm9uZXMgPSAoPFBhdGhBdHRhY2htZW50PmF0dGFjaG1lbnQpLmJvbmVzO1xuXHRcdGlmICghcGF0aEJvbmVzKVxuXHRcdFx0dGhpcy5zb3J0Qm9uZShzbG90Qm9uZSk7XG5cdFx0ZWxzZSB7XG5cdFx0XHRsZXQgYm9uZXMgPSB0aGlzLmJvbmVzO1xuXHRcdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBwYXRoQm9uZXMubGVuZ3RoOyBpIDwgbjspIHtcblx0XHRcdFx0bGV0IG5uID0gcGF0aEJvbmVzW2krK107XG5cdFx0XHRcdG5uICs9IGk7XG5cdFx0XHRcdHdoaWxlIChpIDwgbm4pXG5cdFx0XHRcdFx0dGhpcy5zb3J0Qm9uZShib25lc1twYXRoQm9uZXNbaSsrXV0pO1xuXHRcdFx0fVxuXHRcdH1cblx0fVxuXG5cdHNvcnRQaHlzaWNzQ29uc3RyYWludCAoY29uc3RyYWludDogUGh5c2ljc0NvbnN0cmFpbnQpIHtcblx0XHRjb25zdCBib25lID0gY29uc3RyYWludC5ib25lO1xuXHRcdGNvbnN0cmFpbnQuYWN0aXZlID0gYm9uZS5hY3RpdmUgJiYgKCFjb25zdHJhaW50LmRhdGEuc2tpblJlcXVpcmVkIHx8ICh0aGlzLnNraW4gIT0gbnVsbCAmJiBVdGlscy5jb250YWlucyh0aGlzLnNraW4uY29uc3RyYWludHMsIGNvbnN0cmFpbnQuZGF0YSwgdHJ1ZSkpKTtcblx0XHRpZiAoIWNvbnN0cmFpbnQuYWN0aXZlKSByZXR1cm47XG5cblx0XHR0aGlzLnNvcnRCb25lKGJvbmUpO1xuXG5cdFx0dGhpcy5fdXBkYXRlQ2FjaGUucHVzaChjb25zdHJhaW50KTtcblxuXHRcdHRoaXMuc29ydFJlc2V0KGJvbmUuY2hpbGRyZW4pO1xuXHRcdGJvbmUuc29ydGVkID0gdHJ1ZTtcblx0fVxuXG5cdHNvcnRCb25lIChib25lOiBCb25lKSB7XG5cdFx0aWYgKCFib25lKSByZXR1cm47XG5cdFx0aWYgKGJvbmUuc29ydGVkKSByZXR1cm47XG5cdFx0bGV0IHBhcmVudCA9IGJvbmUucGFyZW50O1xuXHRcdGlmIChwYXJlbnQpIHRoaXMuc29ydEJvbmUocGFyZW50KTtcblx0XHRib25lLnNvcnRlZCA9IHRydWU7XG5cdFx0dGhpcy5fdXBkYXRlQ2FjaGUucHVzaChib25lKTtcblx0fVxuXG5cdHNvcnRSZXNldCAoYm9uZXM6IEFycmF5PEJvbmU+KSB7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBib25lcy5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBib25lID0gYm9uZXNbaV07XG5cdFx0XHRpZiAoIWJvbmUuYWN0aXZlKSBjb250aW51ZTtcblx0XHRcdGlmIChib25lLnNvcnRlZCkgdGhpcy5zb3J0UmVzZXQoYm9uZS5jaGlsZHJlbik7XG5cdFx0XHRib25lLnNvcnRlZCA9IGZhbHNlO1xuXHRcdH1cblx0fVxuXG5cdC8qKiBVcGRhdGVzIHRoZSB3b3JsZCB0cmFuc2Zvcm0gZm9yIGVhY2ggYm9uZSBhbmQgYXBwbGllcyBhbGwgY29uc3RyYWludHMuXG5cdCAqXG5cdCAqIFNlZSBbV29ybGQgdHJhbnNmb3Jtc10oaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLXJ1bnRpbWUtc2tlbGV0b25zI1dvcmxkLXRyYW5zZm9ybXMpIGluIHRoZSBTcGluZVxuXHQgKiBSdW50aW1lcyBHdWlkZS4gKi9cblx0dXBkYXRlV29ybGRUcmFuc2Zvcm0gKHBoeXNpY3M6IFBoeXNpY3MpIHtcblx0XHRpZiAocGh5c2ljcyA9PT0gdW5kZWZpbmVkIHx8IHBoeXNpY3MgPT09IG51bGwpIHRocm93IG5ldyBFcnJvcihcInBoeXNpY3MgaXMgdW5kZWZpbmVkXCIpO1xuXHRcdGxldCBib25lcyA9IHRoaXMuYm9uZXM7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBib25lcy5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBib25lID0gYm9uZXNbaV07XG5cdFx0XHRib25lLmF4ID0gYm9uZS54O1xuXHRcdFx0Ym9uZS5heSA9IGJvbmUueTtcblx0XHRcdGJvbmUuYXJvdGF0aW9uID0gYm9uZS5yb3RhdGlvbjtcblx0XHRcdGJvbmUuYXNjYWxlWCA9IGJvbmUuc2NhbGVYO1xuXHRcdFx0Ym9uZS5hc2NhbGVZID0gYm9uZS5zY2FsZVk7XG5cdFx0XHRib25lLmFzaGVhclggPSBib25lLnNoZWFyWDtcblx0XHRcdGJvbmUuYXNoZWFyWSA9IGJvbmUuc2hlYXJZO1xuXHRcdH1cblxuXHRcdGxldCB1cGRhdGVDYWNoZSA9IHRoaXMuX3VwZGF0ZUNhY2hlO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gdXBkYXRlQ2FjaGUubGVuZ3RoOyBpIDwgbjsgaSsrKVxuXHRcdFx0dXBkYXRlQ2FjaGVbaV0udXBkYXRlKHBoeXNpY3MpO1xuXHR9XG5cblx0dXBkYXRlV29ybGRUcmFuc2Zvcm1XaXRoIChwaHlzaWNzOiBQaHlzaWNzLCBwYXJlbnQ6IEJvbmUpIHtcblx0XHRpZiAoIXBhcmVudCkgdGhyb3cgbmV3IEVycm9yKFwicGFyZW50IGNhbm5vdCBiZSBudWxsLlwiKTtcblxuXHRcdGxldCBib25lcyA9IHRoaXMuYm9uZXM7XG5cdFx0Zm9yIChsZXQgaSA9IDEsIG4gPSBib25lcy5sZW5ndGg7IGkgPCBuOyBpKyspIHsgLy8gU2tpcCByb290IGJvbmUuXG5cdFx0XHRsZXQgYm9uZSA9IGJvbmVzW2ldO1xuXHRcdFx0Ym9uZS5heCA9IGJvbmUueDtcblx0XHRcdGJvbmUuYXkgPSBib25lLnk7XG5cdFx0XHRib25lLmFyb3RhdGlvbiA9IGJvbmUucm90YXRpb247XG5cdFx0XHRib25lLmFzY2FsZVggPSBib25lLnNjYWxlWDtcblx0XHRcdGJvbmUuYXNjYWxlWSA9IGJvbmUuc2NhbGVZO1xuXHRcdFx0Ym9uZS5hc2hlYXJYID0gYm9uZS5zaGVhclg7XG5cdFx0XHRib25lLmFzaGVhclkgPSBib25lLnNoZWFyWTtcblx0XHR9XG5cblx0XHQvLyBBcHBseSB0aGUgcGFyZW50IGJvbmUgdHJhbnNmb3JtIHRvIHRoZSByb290IGJvbmUuIFRoZSByb290IGJvbmUgYWx3YXlzIGluaGVyaXRzIHNjYWxlLCByb3RhdGlvbiBhbmQgcmVmbGVjdGlvbi5cblx0XHRsZXQgcm9vdEJvbmUgPSB0aGlzLmdldFJvb3RCb25lKCk7XG5cdFx0aWYgKCFyb290Qm9uZSkgdGhyb3cgbmV3IEVycm9yKFwiUm9vdCBib25lIG11c3Qgbm90IGJlIG51bGwuXCIpO1xuXHRcdGxldCBwYSA9IHBhcmVudC5hLCBwYiA9IHBhcmVudC5iLCBwYyA9IHBhcmVudC5jLCBwZCA9IHBhcmVudC5kO1xuXHRcdHJvb3RCb25lLndvcmxkWCA9IHBhICogdGhpcy54ICsgcGIgKiB0aGlzLnkgKyBwYXJlbnQud29ybGRYO1xuXHRcdHJvb3RCb25lLndvcmxkWSA9IHBjICogdGhpcy54ICsgcGQgKiB0aGlzLnkgKyBwYXJlbnQud29ybGRZO1xuXG5cdFx0Y29uc3QgcnggPSAocm9vdEJvbmUucm90YXRpb24gKyByb290Qm9uZS5zaGVhclgpICogTWF0aFV0aWxzLmRlZ1JhZDtcblx0XHRjb25zdCByeSA9IChyb290Qm9uZS5yb3RhdGlvbiArIDkwICsgcm9vdEJvbmUuc2hlYXJZKSAqIE1hdGhVdGlscy5kZWdSYWQ7XG5cdFx0Y29uc3QgbGEgPSBNYXRoLmNvcyhyeCkgKiByb290Qm9uZS5zY2FsZVg7XG5cdFx0Y29uc3QgbGIgPSBNYXRoLmNvcyhyeSkgKiByb290Qm9uZS5zY2FsZVk7XG5cdFx0Y29uc3QgbGMgPSBNYXRoLnNpbihyeCkgKiByb290Qm9uZS5zY2FsZVg7XG5cdFx0Y29uc3QgbGQgPSBNYXRoLnNpbihyeSkgKiByb290Qm9uZS5zY2FsZVk7XG5cdFx0cm9vdEJvbmUuYSA9IChwYSAqIGxhICsgcGIgKiBsYykgKiB0aGlzLnNjYWxlWDtcblx0XHRyb290Qm9uZS5iID0gKHBhICogbGIgKyBwYiAqIGxkKSAqIHRoaXMuc2NhbGVYO1xuXHRcdHJvb3RCb25lLmMgPSAocGMgKiBsYSArIHBkICogbGMpICogdGhpcy5zY2FsZVk7XG5cdFx0cm9vdEJvbmUuZCA9IChwYyAqIGxiICsgcGQgKiBsZCkgKiB0aGlzLnNjYWxlWTtcblxuXHRcdC8vIFVwZGF0ZSBldmVyeXRoaW5nIGV4Y2VwdCByb290IGJvbmUuXG5cdFx0bGV0IHVwZGF0ZUNhY2hlID0gdGhpcy5fdXBkYXRlQ2FjaGU7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSB1cGRhdGVDYWNoZS5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCB1cGRhdGFibGUgPSB1cGRhdGVDYWNoZVtpXTtcblx0XHRcdGlmICh1cGRhdGFibGUgIT0gcm9vdEJvbmUpIHVwZGF0YWJsZS51cGRhdGUocGh5c2ljcyk7XG5cdFx0fVxuXHR9XG5cblx0LyoqIFNldHMgdGhlIGJvbmVzLCBjb25zdHJhaW50cywgYW5kIHNsb3RzIHRvIHRoZWlyIHNldHVwIHBvc2UgdmFsdWVzLiAqL1xuXHRzZXRUb1NldHVwUG9zZSAoKSB7XG5cdFx0dGhpcy5zZXRCb25lc1RvU2V0dXBQb3NlKCk7XG5cdFx0dGhpcy5zZXRTbG90c1RvU2V0dXBQb3NlKCk7XG5cdH1cblxuXHQvKiogU2V0cyB0aGUgYm9uZXMgYW5kIGNvbnN0cmFpbnRzIHRvIHRoZWlyIHNldHVwIHBvc2UgdmFsdWVzLiAqL1xuXHRzZXRCb25lc1RvU2V0dXBQb3NlICgpIHtcblx0XHRmb3IgKGNvbnN0IGJvbmUgb2YgdGhpcy5ib25lcykgYm9uZS5zZXRUb1NldHVwUG9zZSgpO1xuXHRcdGZvciAoY29uc3QgY29uc3RyYWludCBvZiB0aGlzLmlrQ29uc3RyYWludHMpIGNvbnN0cmFpbnQuc2V0VG9TZXR1cFBvc2UoKTtcblx0XHRmb3IgKGNvbnN0IGNvbnN0cmFpbnQgb2YgdGhpcy50cmFuc2Zvcm1Db25zdHJhaW50cykgY29uc3RyYWludC5zZXRUb1NldHVwUG9zZSgpO1xuXHRcdGZvciAoY29uc3QgY29uc3RyYWludCBvZiB0aGlzLnBhdGhDb25zdHJhaW50cykgY29uc3RyYWludC5zZXRUb1NldHVwUG9zZSgpO1xuXHRcdGZvciAoY29uc3QgY29uc3RyYWludCBvZiB0aGlzLnBoeXNpY3NDb25zdHJhaW50cykgY29uc3RyYWludC5zZXRUb1NldHVwUG9zZSgpO1xuXHR9XG5cblx0LyoqIFNldHMgdGhlIHNsb3RzIGFuZCBkcmF3IG9yZGVyIHRvIHRoZWlyIHNldHVwIHBvc2UgdmFsdWVzLiAqL1xuXHRzZXRTbG90c1RvU2V0dXBQb3NlICgpIHtcblx0XHRsZXQgc2xvdHMgPSB0aGlzLnNsb3RzO1xuXHRcdFV0aWxzLmFycmF5Q29weShzbG90cywgMCwgdGhpcy5kcmF3T3JkZXIsIDAsIHNsb3RzLmxlbmd0aCk7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBzbG90cy5sZW5ndGg7IGkgPCBuOyBpKyspXG5cdFx0XHRzbG90c1tpXS5zZXRUb1NldHVwUG9zZSgpO1xuXHR9XG5cblx0LyoqIEByZXR1cm5zIE1heSByZXR1cm4gbnVsbC4gKi9cblx0Z2V0Um9vdEJvbmUgKCkge1xuXHRcdGlmICh0aGlzLmJvbmVzLmxlbmd0aCA9PSAwKSByZXR1cm4gbnVsbDtcblx0XHRyZXR1cm4gdGhpcy5ib25lc1swXTtcblx0fVxuXG5cdC8qKiBAcmV0dXJucyBNYXkgYmUgbnVsbC4gKi9cblx0ZmluZEJvbmUgKGJvbmVOYW1lOiBzdHJpbmcpIHtcblx0XHRpZiAoIWJvbmVOYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJib25lTmFtZSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0bGV0IGJvbmVzID0gdGhpcy5ib25lcztcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IGJvbmVzLmxlbmd0aDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGJvbmUgPSBib25lc1tpXTtcblx0XHRcdGlmIChib25lLmRhdGEubmFtZSA9PSBib25lTmFtZSkgcmV0dXJuIGJvbmU7XG5cdFx0fVxuXHRcdHJldHVybiBudWxsO1xuXHR9XG5cblx0LyoqIEZpbmRzIGEgc2xvdCBieSBjb21wYXJpbmcgZWFjaCBzbG90J3MgbmFtZS4gSXQgaXMgbW9yZSBlZmZpY2llbnQgdG8gY2FjaGUgdGhlIHJlc3VsdHMgb2YgdGhpcyBtZXRob2QgdGhhbiB0byBjYWxsIGl0XG5cdCAqIHJlcGVhdGVkbHkuXG5cdCAqIEByZXR1cm5zIE1heSBiZSBudWxsLiAqL1xuXHRmaW5kU2xvdCAoc2xvdE5hbWU6IHN0cmluZykge1xuXHRcdGlmICghc2xvdE5hbWUpIHRocm93IG5ldyBFcnJvcihcInNsb3ROYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRsZXQgc2xvdHMgPSB0aGlzLnNsb3RzO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gc2xvdHMubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRsZXQgc2xvdCA9IHNsb3RzW2ldO1xuXHRcdFx0aWYgKHNsb3QuZGF0YS5uYW1lID09IHNsb3ROYW1lKSByZXR1cm4gc2xvdDtcblx0XHR9XG5cdFx0cmV0dXJuIG51bGw7XG5cdH1cblxuXHQvKiogU2V0cyBhIHNraW4gYnkgbmFtZS5cblx0ICpcblx0ICogU2VlIHtAbGluayAjc2V0U2tpbigpfS4gKi9cblx0c2V0U2tpbkJ5TmFtZSAoc2tpbk5hbWU6IHN0cmluZykge1xuXHRcdGxldCBza2luID0gdGhpcy5kYXRhLmZpbmRTa2luKHNraW5OYW1lKTtcblx0XHRpZiAoIXNraW4pIHRocm93IG5ldyBFcnJvcihcIlNraW4gbm90IGZvdW5kOiBcIiArIHNraW5OYW1lKTtcblx0XHR0aGlzLnNldFNraW4oc2tpbik7XG5cdH1cblxuXHQvKiogU2V0cyB0aGUgc2tpbiB1c2VkIHRvIGxvb2sgdXAgYXR0YWNobWVudHMgYmVmb3JlIGxvb2tpbmcgaW4gdGhlIHtAbGluayBTa2VsZXRvbkRhdGEjZGVmYXVsdFNraW4gZGVmYXVsdCBza2lufS4gSWYgdGhlXG5cdCAqIHNraW4gaXMgY2hhbmdlZCwge0BsaW5rICN1cGRhdGVDYWNoZSgpfSBpcyBjYWxsZWQuXG5cdCAqXG5cdCAqIEF0dGFjaG1lbnRzIGZyb20gdGhlIG5ldyBza2luIGFyZSBhdHRhY2hlZCBpZiB0aGUgY29ycmVzcG9uZGluZyBhdHRhY2htZW50IGZyb20gdGhlIG9sZCBza2luIHdhcyBhdHRhY2hlZC4gSWYgdGhlcmUgd2FzIG5vXG5cdCAqIG9sZCBza2luLCBlYWNoIHNsb3QncyBzZXR1cCBtb2RlIGF0dGFjaG1lbnQgaXMgYXR0YWNoZWQgZnJvbSB0aGUgbmV3IHNraW4uXG5cdCAqXG5cdCAqIEFmdGVyIGNoYW5naW5nIHRoZSBza2luLCB0aGUgdmlzaWJsZSBhdHRhY2htZW50cyBjYW4gYmUgcmVzZXQgdG8gdGhvc2UgYXR0YWNoZWQgaW4gdGhlIHNldHVwIHBvc2UgYnkgY2FsbGluZ1xuXHQgKiB7QGxpbmsgI3NldFNsb3RzVG9TZXR1cFBvc2UoKX0uIEFsc28sIG9mdGVuIHtAbGluayBBbmltYXRpb25TdGF0ZSNhcHBseSgpfSBpcyBjYWxsZWQgYmVmb3JlIHRoZSBuZXh0IHRpbWUgdGhlXG5cdCAqIHNrZWxldG9uIGlzIHJlbmRlcmVkIHRvIGFsbG93IGFueSBhdHRhY2htZW50IGtleXMgaW4gdGhlIGN1cnJlbnQgYW5pbWF0aW9uKHMpIHRvIGhpZGUgb3Igc2hvdyBhdHRhY2htZW50cyBmcm9tIHRoZSBuZXcgc2tpbi5cblx0ICogQHBhcmFtIG5ld1NraW4gTWF5IGJlIG51bGwuICovXG5cdHNldFNraW4gKG5ld1NraW46IFNraW4gfCBudWxsKSB7XG5cdFx0aWYgKG5ld1NraW4gPT0gdGhpcy5za2luKSByZXR1cm47XG5cdFx0aWYgKG5ld1NraW4pIHtcblx0XHRcdGlmICh0aGlzLnNraW4pXG5cdFx0XHRcdG5ld1NraW4uYXR0YWNoQWxsKHRoaXMsIHRoaXMuc2tpbik7XG5cdFx0XHRlbHNlIHtcblx0XHRcdFx0bGV0IHNsb3RzID0gdGhpcy5zbG90cztcblx0XHRcdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBzbG90cy5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdFx0XHRsZXQgc2xvdCA9IHNsb3RzW2ldO1xuXHRcdFx0XHRcdGxldCBuYW1lID0gc2xvdC5kYXRhLmF0dGFjaG1lbnROYW1lO1xuXHRcdFx0XHRcdGlmIChuYW1lKSB7XG5cdFx0XHRcdFx0XHRsZXQgYXR0YWNobWVudCA9IG5ld1NraW4uZ2V0QXR0YWNobWVudChpLCBuYW1lKTtcblx0XHRcdFx0XHRcdGlmIChhdHRhY2htZW50KSBzbG90LnNldEF0dGFjaG1lbnQoYXR0YWNobWVudCk7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0fVxuXHRcdHRoaXMuc2tpbiA9IG5ld1NraW47XG5cdFx0dGhpcy51cGRhdGVDYWNoZSgpO1xuXHR9XG5cblxuXHQvKiogRmluZHMgYW4gYXR0YWNobWVudCBieSBsb29raW5nIGluIHRoZSB7QGxpbmsgI3NraW59IGFuZCB7QGxpbmsgU2tlbGV0b25EYXRhI2RlZmF1bHRTa2lufSB1c2luZyB0aGUgc2xvdCBuYW1lIGFuZCBhdHRhY2htZW50XG5cdCAqIG5hbWUuXG5cdCAqXG5cdCAqIFNlZSB7QGxpbmsgI2dldEF0dGFjaG1lbnQoKX0uXG5cdCAqIEByZXR1cm5zIE1heSBiZSBudWxsLiAqL1xuXHRnZXRBdHRhY2htZW50QnlOYW1lIChzbG90TmFtZTogc3RyaW5nLCBhdHRhY2htZW50TmFtZTogc3RyaW5nKTogQXR0YWNobWVudCB8IG51bGwge1xuXHRcdGxldCBzbG90ID0gdGhpcy5kYXRhLmZpbmRTbG90KHNsb3ROYW1lKTtcblx0XHRpZiAoIXNsb3QpIHRocm93IG5ldyBFcnJvcihgQ2FuJ3QgZmluZCBzbG90IHdpdGggbmFtZSAke3Nsb3ROYW1lfWApO1xuXHRcdHJldHVybiB0aGlzLmdldEF0dGFjaG1lbnQoc2xvdC5pbmRleCwgYXR0YWNobWVudE5hbWUpO1xuXHR9XG5cblx0LyoqIEZpbmRzIGFuIGF0dGFjaG1lbnQgYnkgbG9va2luZyBpbiB0aGUge0BsaW5rICNza2lufSBhbmQge0BsaW5rIFNrZWxldG9uRGF0YSNkZWZhdWx0U2tpbn0gdXNpbmcgdGhlIHNsb3QgaW5kZXggYW5kXG5cdCAqIGF0dGFjaG1lbnQgbmFtZS4gRmlyc3QgdGhlIHNraW4gaXMgY2hlY2tlZCBhbmQgaWYgdGhlIGF0dGFjaG1lbnQgd2FzIG5vdCBmb3VuZCwgdGhlIGRlZmF1bHQgc2tpbiBpcyBjaGVja2VkLlxuXHQgKlxuXHQgKiBTZWUgW1J1bnRpbWUgc2tpbnNdKGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1ydW50aW1lLXNraW5zKSBpbiB0aGUgU3BpbmUgUnVudGltZXMgR3VpZGUuXG5cdCAqIEByZXR1cm5zIE1heSBiZSBudWxsLiAqL1xuXHRnZXRBdHRhY2htZW50IChzbG90SW5kZXg6IG51bWJlciwgYXR0YWNobWVudE5hbWU6IHN0cmluZyk6IEF0dGFjaG1lbnQgfCBudWxsIHtcblx0XHRpZiAoIWF0dGFjaG1lbnROYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJhdHRhY2htZW50TmFtZSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0aWYgKHRoaXMuc2tpbikge1xuXHRcdFx0bGV0IGF0dGFjaG1lbnQgPSB0aGlzLnNraW4uZ2V0QXR0YWNobWVudChzbG90SW5kZXgsIGF0dGFjaG1lbnROYW1lKTtcblx0XHRcdGlmIChhdHRhY2htZW50KSByZXR1cm4gYXR0YWNobWVudDtcblx0XHR9XG5cdFx0aWYgKHRoaXMuZGF0YS5kZWZhdWx0U2tpbikgcmV0dXJuIHRoaXMuZGF0YS5kZWZhdWx0U2tpbi5nZXRBdHRhY2htZW50KHNsb3RJbmRleCwgYXR0YWNobWVudE5hbWUpO1xuXHRcdHJldHVybiBudWxsO1xuXHR9XG5cblx0LyoqIEEgY29udmVuaWVuY2UgbWV0aG9kIHRvIHNldCBhbiBhdHRhY2htZW50IGJ5IGZpbmRpbmcgdGhlIHNsb3Qgd2l0aCB7QGxpbmsgI2ZpbmRTbG90KCl9LCBmaW5kaW5nIHRoZSBhdHRhY2htZW50IHdpdGhcblx0ICoge0BsaW5rICNnZXRBdHRhY2htZW50KCl9LCB0aGVuIHNldHRpbmcgdGhlIHNsb3QncyB7QGxpbmsgU2xvdCNhdHRhY2htZW50fS5cblx0ICogQHBhcmFtIGF0dGFjaG1lbnROYW1lIE1heSBiZSBudWxsIHRvIGNsZWFyIHRoZSBzbG90J3MgYXR0YWNobWVudC4gKi9cblx0c2V0QXR0YWNobWVudCAoc2xvdE5hbWU6IHN0cmluZywgYXR0YWNobWVudE5hbWU6IHN0cmluZykge1xuXHRcdGlmICghc2xvdE5hbWUpIHRocm93IG5ldyBFcnJvcihcInNsb3ROYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRsZXQgc2xvdHMgPSB0aGlzLnNsb3RzO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gc2xvdHMubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRsZXQgc2xvdCA9IHNsb3RzW2ldO1xuXHRcdFx0aWYgKHNsb3QuZGF0YS5uYW1lID09IHNsb3ROYW1lKSB7XG5cdFx0XHRcdGxldCBhdHRhY2htZW50OiBBdHRhY2htZW50IHwgbnVsbCA9IG51bGw7XG5cdFx0XHRcdGlmIChhdHRhY2htZW50TmFtZSkge1xuXHRcdFx0XHRcdGF0dGFjaG1lbnQgPSB0aGlzLmdldEF0dGFjaG1lbnQoaSwgYXR0YWNobWVudE5hbWUpO1xuXHRcdFx0XHRcdGlmICghYXR0YWNobWVudCkgdGhyb3cgbmV3IEVycm9yKFwiQXR0YWNobWVudCBub3QgZm91bmQ6IFwiICsgYXR0YWNobWVudE5hbWUgKyBcIiwgZm9yIHNsb3Q6IFwiICsgc2xvdE5hbWUpO1xuXHRcdFx0XHR9XG5cdFx0XHRcdHNsb3Quc2V0QXR0YWNobWVudChhdHRhY2htZW50KTtcblx0XHRcdFx0cmV0dXJuO1xuXHRcdFx0fVxuXHRcdH1cblx0XHR0aHJvdyBuZXcgRXJyb3IoXCJTbG90IG5vdCBmb3VuZDogXCIgKyBzbG90TmFtZSk7XG5cdH1cblxuXG5cdC8qKiBGaW5kcyBhbiBJSyBjb25zdHJhaW50IGJ5IGNvbXBhcmluZyBlYWNoIElLIGNvbnN0cmFpbnQncyBuYW1lLiBJdCBpcyBtb3JlIGVmZmljaWVudCB0byBjYWNoZSB0aGUgcmVzdWx0cyBvZiB0aGlzIG1ldGhvZFxuXHQgKiB0aGFuIHRvIGNhbGwgaXQgcmVwZWF0ZWRseS5cblx0ICogQHJldHVybiBNYXkgYmUgbnVsbC4gKi9cblx0ZmluZElrQ29uc3RyYWludCAoY29uc3RyYWludE5hbWU6IHN0cmluZykge1xuXHRcdGlmICghY29uc3RyYWludE5hbWUpIHRocm93IG5ldyBFcnJvcihcImNvbnN0cmFpbnROYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRyZXR1cm4gdGhpcy5pa0NvbnN0cmFpbnRzLmZpbmQoKGNvbnN0cmFpbnQpID0+IGNvbnN0cmFpbnQuZGF0YS5uYW1lID09IGNvbnN0cmFpbnROYW1lKSA/PyBudWxsO1xuXHR9XG5cblx0LyoqIEZpbmRzIGEgdHJhbnNmb3JtIGNvbnN0cmFpbnQgYnkgY29tcGFyaW5nIGVhY2ggdHJhbnNmb3JtIGNvbnN0cmFpbnQncyBuYW1lLiBJdCBpcyBtb3JlIGVmZmljaWVudCB0byBjYWNoZSB0aGUgcmVzdWx0cyBvZlxuXHQgKiB0aGlzIG1ldGhvZCB0aGFuIHRvIGNhbGwgaXQgcmVwZWF0ZWRseS5cblx0ICogQHJldHVybiBNYXkgYmUgbnVsbC4gKi9cblx0ZmluZFRyYW5zZm9ybUNvbnN0cmFpbnQgKGNvbnN0cmFpbnROYW1lOiBzdHJpbmcpIHtcblx0XHRpZiAoIWNvbnN0cmFpbnROYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJjb25zdHJhaW50TmFtZSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0cmV0dXJuIHRoaXMudHJhbnNmb3JtQ29uc3RyYWludHMuZmluZCgoY29uc3RyYWludCkgPT4gY29uc3RyYWludC5kYXRhLm5hbWUgPT0gY29uc3RyYWludE5hbWUpID8/IG51bGw7XG5cdH1cblxuXHQvKiogRmluZHMgYSBwYXRoIGNvbnN0cmFpbnQgYnkgY29tcGFyaW5nIGVhY2ggcGF0aCBjb25zdHJhaW50J3MgbmFtZS4gSXQgaXMgbW9yZSBlZmZpY2llbnQgdG8gY2FjaGUgdGhlIHJlc3VsdHMgb2YgdGhpcyBtZXRob2Rcblx0ICogdGhhbiB0byBjYWxsIGl0IHJlcGVhdGVkbHkuXG5cdCAqIEByZXR1cm4gTWF5IGJlIG51bGwuICovXG5cdGZpbmRQYXRoQ29uc3RyYWludCAoY29uc3RyYWludE5hbWU6IHN0cmluZykge1xuXHRcdGlmICghY29uc3RyYWludE5hbWUpIHRocm93IG5ldyBFcnJvcihcImNvbnN0cmFpbnROYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRyZXR1cm4gdGhpcy5wYXRoQ29uc3RyYWludHMuZmluZCgoY29uc3RyYWludCkgPT4gY29uc3RyYWludC5kYXRhLm5hbWUgPT0gY29uc3RyYWludE5hbWUpID8/IG51bGw7XG5cdH1cblxuXHQvKiogRmluZHMgYSBwaHlzaWNzIGNvbnN0cmFpbnQgYnkgY29tcGFyaW5nIGVhY2ggcGh5c2ljcyBjb25zdHJhaW50J3MgbmFtZS4gSXQgaXMgbW9yZSBlZmZpY2llbnQgdG8gY2FjaGUgdGhlIHJlc3VsdHMgb2YgdGhpc1xuXHQgKiBtZXRob2QgdGhhbiB0byBjYWxsIGl0IHJlcGVhdGVkbHkuICovXG5cdGZpbmRQaHlzaWNzQ29uc3RyYWludCAoY29uc3RyYWludE5hbWU6IHN0cmluZykge1xuXHRcdGlmIChjb25zdHJhaW50TmFtZSA9PSBudWxsKSB0aHJvdyBuZXcgRXJyb3IoXCJjb25zdHJhaW50TmFtZSBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0cmV0dXJuIHRoaXMucGh5c2ljc0NvbnN0cmFpbnRzLmZpbmQoKGNvbnN0cmFpbnQpID0+IGNvbnN0cmFpbnQuZGF0YS5uYW1lID09IGNvbnN0cmFpbnROYW1lKSA/PyBudWxsO1xuXHR9XG5cblx0LyoqIFJldHVybnMgdGhlIGF4aXMgYWxpZ25lZCBib3VuZGluZyBib3ggKEFBQkIpIG9mIHRoZSByZWdpb24gYW5kIG1lc2ggYXR0YWNobWVudHMgZm9yIHRoZSBjdXJyZW50IHBvc2UgYXMgYHsgeDogbnVtYmVyLCB5OiBudW1iZXIsIHdpZHRoOiBudW1iZXIsIGhlaWdodDogbnVtYmVyIH1gLlxuXHQgKiBOb3RlIHRoYXQgdGhpcyBtZXRob2Qgd2lsbCBjcmVhdGUgdGVtcG9yYXJ5IG9iamVjdHMgd2hpY2ggY2FuIGFkZCB0byBnYXJiYWdlIGNvbGxlY3Rpb24gcHJlc3N1cmUuIFVzZSBgZ2V0Qm91bmRzKClgIGlmIGdhcmJhZ2UgY29sbGVjdGlvbiBpcyBhIGNvbmNlcm4uICovXG5cdGdldEJvdW5kc1JlY3QgKGNsaXBwZXI/OiBTa2VsZXRvbkNsaXBwaW5nKSB7XG5cdFx0bGV0IG9mZnNldCA9IG5ldyBWZWN0b3IyKCk7XG5cdFx0bGV0IHNpemUgPSBuZXcgVmVjdG9yMigpO1xuXHRcdHRoaXMuZ2V0Qm91bmRzKG9mZnNldCwgc2l6ZSwgdW5kZWZpbmVkLCBjbGlwcGVyKTtcblx0XHRyZXR1cm4geyB4OiBvZmZzZXQueCwgeTogb2Zmc2V0LnksIHdpZHRoOiBzaXplLngsIGhlaWdodDogc2l6ZS55IH07XG5cdH1cblxuXHQvKiogUmV0dXJucyB0aGUgYXhpcyBhbGlnbmVkIGJvdW5kaW5nIGJveCAoQUFCQikgb2YgdGhlIHJlZ2lvbiBhbmQgbWVzaCBhdHRhY2htZW50cyBmb3IgdGhlIGN1cnJlbnQgcG9zZS5cblx0ICogQHBhcmFtIG9mZnNldCBBbiBvdXRwdXQgdmFsdWUsIHRoZSBkaXN0YW5jZSBmcm9tIHRoZSBza2VsZXRvbiBvcmlnaW4gdG8gdGhlIGJvdHRvbSBsZWZ0IGNvcm5lciBvZiB0aGUgQUFCQi5cblx0ICogQHBhcmFtIHNpemUgQW4gb3V0cHV0IHZhbHVlLCB0aGUgd2lkdGggYW5kIGhlaWdodCBvZiB0aGUgQUFCQi5cblx0ICogQHBhcmFtIHRlbXAgV29ya2luZyBtZW1vcnkgdG8gdGVtcG9yYXJpbHkgc3RvcmUgYXR0YWNobWVudHMnIGNvbXB1dGVkIHdvcmxkIHZlcnRpY2VzLlxuXHQgKiBAcGFyYW0gY2xpcHBlciB7QGxpbmsgU2tlbGV0b25DbGlwcGluZ30gdG8gdXNlLiBJZiA8Y29kZT5udWxsPC9jb2RlPiwgbm8gY2xpcHBpbmcgaXMgYXBwbGllZC4gKi9cblx0Z2V0Qm91bmRzIChvZmZzZXQ6IFZlY3RvcjIsIHNpemU6IFZlY3RvcjIsIHRlbXA6IEFycmF5PG51bWJlcj4gPSBuZXcgQXJyYXk8bnVtYmVyPigyKSwgY2xpcHBlcjogU2tlbGV0b25DbGlwcGluZyB8IG51bGwgPSBudWxsKSB7XG5cdFx0aWYgKCFvZmZzZXQpIHRocm93IG5ldyBFcnJvcihcIm9mZnNldCBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0aWYgKCFzaXplKSB0aHJvdyBuZXcgRXJyb3IoXCJzaXplIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRsZXQgZHJhd09yZGVyID0gdGhpcy5kcmF3T3JkZXI7XG5cdFx0bGV0IG1pblggPSBOdW1iZXIuUE9TSVRJVkVfSU5GSU5JVFksIG1pblkgPSBOdW1iZXIuUE9TSVRJVkVfSU5GSU5JVFksIG1heFggPSBOdW1iZXIuTkVHQVRJVkVfSU5GSU5JVFksIG1heFkgPSBOdW1iZXIuTkVHQVRJVkVfSU5GSU5JVFk7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBkcmF3T3JkZXIubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRsZXQgc2xvdCA9IGRyYXdPcmRlcltpXTtcblx0XHRcdGlmICghc2xvdC5ib25lLmFjdGl2ZSkgY29udGludWU7XG5cdFx0XHRsZXQgdmVydGljZXNMZW5ndGggPSAwO1xuXHRcdFx0bGV0IHZlcnRpY2VzOiBOdW1iZXJBcnJheUxpa2UgfCBudWxsID0gbnVsbDtcblx0XHRcdGxldCB0cmlhbmdsZXM6IE51bWJlckFycmF5TGlrZSB8IG51bGwgPSBudWxsO1xuXHRcdFx0bGV0IGF0dGFjaG1lbnQgPSBzbG90LmdldEF0dGFjaG1lbnQoKTtcblx0XHRcdGlmIChhdHRhY2htZW50IGluc3RhbmNlb2YgUmVnaW9uQXR0YWNobWVudCkge1xuXHRcdFx0XHR2ZXJ0aWNlc0xlbmd0aCA9IDg7XG5cdFx0XHRcdHZlcnRpY2VzID0gVXRpbHMuc2V0QXJyYXlTaXplKHRlbXAsIHZlcnRpY2VzTGVuZ3RoLCAwKTtcblx0XHRcdFx0YXR0YWNobWVudC5jb21wdXRlV29ybGRWZXJ0aWNlcyhzbG90LCB2ZXJ0aWNlcywgMCwgMik7XG5cdFx0XHRcdHRyaWFuZ2xlcyA9IFNrZWxldG9uLnF1YWRUcmlhbmdsZXM7XG5cdFx0XHR9IGVsc2UgaWYgKGF0dGFjaG1lbnQgaW5zdGFuY2VvZiBNZXNoQXR0YWNobWVudCkge1xuXHRcdFx0XHRsZXQgbWVzaCA9ICg8TWVzaEF0dGFjaG1lbnQ+YXR0YWNobWVudCk7XG5cdFx0XHRcdHZlcnRpY2VzTGVuZ3RoID0gbWVzaC53b3JsZFZlcnRpY2VzTGVuZ3RoO1xuXHRcdFx0XHR2ZXJ0aWNlcyA9IFV0aWxzLnNldEFycmF5U2l6ZSh0ZW1wLCB2ZXJ0aWNlc0xlbmd0aCwgMCk7XG5cdFx0XHRcdG1lc2guY29tcHV0ZVdvcmxkVmVydGljZXMoc2xvdCwgMCwgdmVydGljZXNMZW5ndGgsIHZlcnRpY2VzLCAwLCAyKTtcblx0XHRcdFx0dHJpYW5nbGVzID0gbWVzaC50cmlhbmdsZXM7XG5cdFx0XHR9IGVsc2UgaWYgKGF0dGFjaG1lbnQgaW5zdGFuY2VvZiBDbGlwcGluZ0F0dGFjaG1lbnQgJiYgY2xpcHBlciAhPSBudWxsKSB7XG5cdFx0XHRcdGNsaXBwZXIuY2xpcFN0YXJ0KHNsb3QsIGF0dGFjaG1lbnQpO1xuXHRcdFx0XHRjb250aW51ZTtcblx0XHRcdH1cblx0XHRcdGlmICh2ZXJ0aWNlcyAmJiB0cmlhbmdsZXMpIHtcblx0XHRcdFx0aWYgKGNsaXBwZXIgIT0gbnVsbCAmJiBjbGlwcGVyLmlzQ2xpcHBpbmcoKSkge1xuXHRcdFx0XHRcdGNsaXBwZXIuY2xpcFRyaWFuZ2xlcyh2ZXJ0aWNlcywgdHJpYW5nbGVzLCB0cmlhbmdsZXMubGVuZ3RoKTtcblx0XHRcdFx0XHR2ZXJ0aWNlcyA9IGNsaXBwZXIuY2xpcHBlZFZlcnRpY2VzO1xuXHRcdFx0XHRcdHZlcnRpY2VzTGVuZ3RoID0gY2xpcHBlci5jbGlwcGVkVmVydGljZXMubGVuZ3RoO1xuXHRcdFx0XHR9XG5cdFx0XHRcdGZvciAobGV0IGlpID0gMCwgbm4gPSB2ZXJ0aWNlcy5sZW5ndGg7IGlpIDwgbm47IGlpICs9IDIpIHtcblx0XHRcdFx0XHRsZXQgeCA9IHZlcnRpY2VzW2lpXSwgeSA9IHZlcnRpY2VzW2lpICsgMV07XG5cdFx0XHRcdFx0bWluWCA9IE1hdGgubWluKG1pblgsIHgpO1xuXHRcdFx0XHRcdG1pblkgPSBNYXRoLm1pbihtaW5ZLCB5KTtcblx0XHRcdFx0XHRtYXhYID0gTWF0aC5tYXgobWF4WCwgeCk7XG5cdFx0XHRcdFx0bWF4WSA9IE1hdGgubWF4KG1heFksIHkpO1xuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0XHRpZiAoY2xpcHBlciAhPSBudWxsKSBjbGlwcGVyLmNsaXBFbmRXaXRoU2xvdChzbG90KTtcblx0XHR9XG5cdFx0aWYgKGNsaXBwZXIgIT0gbnVsbCkgY2xpcHBlci5jbGlwRW5kKCk7XG5cdFx0b2Zmc2V0LnNldChtaW5YLCBtaW5ZKTtcblx0XHRzaXplLnNldChtYXhYIC0gbWluWCwgbWF4WSAtIG1pblkpO1xuXHR9XG5cblx0LyoqIEluY3JlbWVudHMgdGhlIHNrZWxldG9uJ3Mge0BsaW5rICN0aW1lfS4gKi9cblx0dXBkYXRlIChkZWx0YTogbnVtYmVyKSB7XG5cdFx0dGhpcy50aW1lICs9IGRlbHRhO1xuXHR9XG5cblx0cGh5c2ljc1RyYW5zbGF0ZSAoeDogbnVtYmVyLCB5OiBudW1iZXIpIHtcblx0XHRjb25zdCBwaHlzaWNzQ29uc3RyYWludHMgPSB0aGlzLnBoeXNpY3NDb25zdHJhaW50cztcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IHBoeXNpY3NDb25zdHJhaW50cy5sZW5ndGg7IGkgPCBuOyBpKyspXG5cdFx0XHRwaHlzaWNzQ29uc3RyYWludHNbaV0udHJhbnNsYXRlKHgsIHkpO1xuXHR9XG5cblx0LyoqIENhbGxzIHtAbGluayBQaHlzaWNzQ29uc3RyYWludCNyb3RhdGUoZmxvYXQsIGZsb2F0LCBmbG9hdCl9IGZvciBlYWNoIHBoeXNpY3MgY29uc3RyYWludC4gKi9cblx0cGh5c2ljc1JvdGF0ZSAoeDogbnVtYmVyLCB5OiBudW1iZXIsIGRlZ3JlZXM6IG51bWJlcikge1xuXHRcdGNvbnN0IHBoeXNpY3NDb25zdHJhaW50cyA9IHRoaXMucGh5c2ljc0NvbnN0cmFpbnRzO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gcGh5c2ljc0NvbnN0cmFpbnRzLmxlbmd0aDsgaSA8IG47IGkrKylcblx0XHRcdHBoeXNpY3NDb25zdHJhaW50c1tpXS5yb3RhdGUoeCwgeSwgZGVncmVlcyk7XG5cdH1cbn1cblxuLyoqIERldGVybWluZXMgaG93IHBoeXNpY3MgYW5kIG90aGVyIG5vbi1kZXRlcm1pbmlzdGljIHVwZGF0ZXMgYXJlIGFwcGxpZWQuICovXG5leHBvcnQgZW51bSBQaHlzaWNzIHtcblx0LyoqIFBoeXNpY3MgYXJlIG5vdCB1cGRhdGVkIG9yIGFwcGxpZWQuICovXG5cdG5vbmUsXG5cblx0LyoqIFBoeXNpY3MgYXJlIHJlc2V0IHRvIHRoZSBjdXJyZW50IHBvc2UuICovXG5cdHJlc2V0LFxuXG5cdC8qKiBQaHlzaWNzIGFyZSB1cGRhdGVkIGFuZCB0aGUgcG9zZSBmcm9tIHBoeXNpY3MgaXMgYXBwbGllZC4gKi9cblx0dXBkYXRlLFxuXG5cdC8qKiBQaHlzaWNzIGFyZSBub3QgdXBkYXRlZCBidXQgdGhlIHBvc2UgZnJvbSBwaHlzaWNzIGlzIGFwcGxpZWQuICovXG5cdHBvc2Vcbn1cbiJdfQ==