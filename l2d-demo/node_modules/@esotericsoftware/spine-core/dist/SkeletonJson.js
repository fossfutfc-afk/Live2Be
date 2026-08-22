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
import { Animation, InheritTimeline, AttachmentTimeline, RGBATimeline, RGBTimeline, AlphaTimeline, RGBA2Timeline, RGB2Timeline, RotateTimeline, TranslateTimeline, TranslateXTimeline, TranslateYTimeline, ScaleTimeline, ScaleXTimeline, ScaleYTimeline, ShearTimeline, ShearXTimeline, ShearYTimeline, IkConstraintTimeline, TransformConstraintTimeline, PathConstraintPositionTimeline, PathConstraintSpacingTimeline, PathConstraintMixTimeline, DeformTimeline, DrawOrderTimeline, EventTimeline, PhysicsConstraintResetTimeline, PhysicsConstraintInertiaTimeline, PhysicsConstraintStrengthTimeline, PhysicsConstraintDampingTimeline, PhysicsConstraintMassTimeline, PhysicsConstraintWindTimeline, PhysicsConstraintGravityTimeline, PhysicsConstraintMixTimeline } from "./Animation.js";
import { BoneData, Inherit } from "./BoneData.js";
import { EventData } from "./EventData.js";
import { Event } from "./Event.js";
import { IkConstraintData } from "./IkConstraintData.js";
import { PathConstraintData, PositionMode, SpacingMode, RotateMode } from "./PathConstraintData.js";
import { SkeletonData } from "./SkeletonData.js";
import { Skin } from "./Skin.js";
import { SlotData, BlendMode } from "./SlotData.js";
import { TransformConstraintData } from "./TransformConstraintData.js";
import { Utils, Color } from "./Utils.js";
import { Sequence, SequenceMode } from "./attachments/Sequence.js";
import { SequenceTimeline } from "./Animation.js";
import { PhysicsConstraintData } from "./PhysicsConstraintData.js";
/** Loads skeleton data in the Spine JSON format.
 *
 * See [Spine JSON format](http://esotericsoftware.com/spine-json-format) and
 * [JSON and binary data](http://esotericsoftware.com/spine-loading-skeleton-data#JSON-and-binary-data) in the Spine
 * Runtimes Guide. */
export class SkeletonJson {
    attachmentLoader;
    /** Scales bone positions, image sizes, and translations as they are loaded. This allows different size images to be used at
     * runtime than were used in Spine.
     *
     * See [Scaling](http://esotericsoftware.com/spine-loading-skeleton-data#Scaling) in the Spine Runtimes Guide. */
    scale = 1;
    linkedMeshes = new Array();
    constructor(attachmentLoader) {
        this.attachmentLoader = attachmentLoader;
    }
    readSkeletonData(json) {
        let scale = this.scale;
        let skeletonData = new SkeletonData();
        let root = typeof (json) === "string" ? JSON.parse(json) : json;
        // Skeleton
        let skeletonMap = root.skeleton;
        if (skeletonMap) {
            skeletonData.hash = skeletonMap.hash;
            skeletonData.version = skeletonMap.spine;
            skeletonData.x = skeletonMap.x;
            skeletonData.y = skeletonMap.y;
            skeletonData.width = skeletonMap.width;
            skeletonData.height = skeletonMap.height;
            skeletonData.referenceScale = getValue(skeletonMap, "referenceScale", 100) * scale;
            skeletonData.fps = skeletonMap.fps;
            skeletonData.imagesPath = skeletonMap.images ?? null;
            skeletonData.audioPath = skeletonMap.audio ?? null;
        }
        // Bones
        if (root.bones) {
            for (let i = 0; i < root.bones.length; i++) {
                let boneMap = root.bones[i];
                let parent = null;
                let parentName = getValue(boneMap, "parent", null);
                if (parentName)
                    parent = skeletonData.findBone(parentName);
                let data = new BoneData(skeletonData.bones.length, boneMap.name, parent);
                data.length = getValue(boneMap, "length", 0) * scale;
                data.x = getValue(boneMap, "x", 0) * scale;
                data.y = getValue(boneMap, "y", 0) * scale;
                data.rotation = getValue(boneMap, "rotation", 0);
                data.scaleX = getValue(boneMap, "scaleX", 1);
                data.scaleY = getValue(boneMap, "scaleY", 1);
                data.shearX = getValue(boneMap, "shearX", 0);
                data.shearY = getValue(boneMap, "shearY", 0);
                data.inherit = Utils.enumValue(Inherit, getValue(boneMap, "inherit", "Normal"));
                data.skinRequired = getValue(boneMap, "skin", false);
                let color = getValue(boneMap, "color", null);
                if (color)
                    data.color.setFromString(color);
                skeletonData.bones.push(data);
            }
        }
        // Slots.
        if (root.slots) {
            for (let i = 0; i < root.slots.length; i++) {
                let slotMap = root.slots[i];
                let slotName = slotMap.name;
                let boneData = skeletonData.findBone(slotMap.bone);
                if (!boneData)
                    throw new Error(`Couldn't find bone ${slotMap.bone} for slot ${slotName}`);
                let data = new SlotData(skeletonData.slots.length, slotName, boneData);
                let color = getValue(slotMap, "color", null);
                if (color)
                    data.color.setFromString(color);
                let dark = getValue(slotMap, "dark", null);
                if (dark)
                    data.darkColor = Color.fromString(dark);
                data.attachmentName = getValue(slotMap, "attachment", null);
                data.blendMode = Utils.enumValue(BlendMode, getValue(slotMap, "blend", "normal"));
                data.visible = getValue(slotMap, "visible", true);
                skeletonData.slots.push(data);
            }
        }
        // IK constraints
        if (root.ik) {
            for (let i = 0; i < root.ik.length; i++) {
                let constraintMap = root.ik[i];
                let data = new IkConstraintData(constraintMap.name);
                data.order = getValue(constraintMap, "order", 0);
                data.skinRequired = getValue(constraintMap, "skin", false);
                for (let ii = 0; ii < constraintMap.bones.length; ii++) {
                    let bone = skeletonData.findBone(constraintMap.bones[ii]);
                    if (!bone)
                        throw new Error(`Couldn't find bone ${constraintMap.bones[ii]} for IK constraint ${constraintMap.name}.`);
                    data.bones.push(bone);
                }
                let target = skeletonData.findBone(constraintMap.target);
                ;
                if (!target)
                    throw new Error(`Couldn't find target bone ${constraintMap.target} for IK constraint ${constraintMap.name}.`);
                data.target = target;
                data.mix = getValue(constraintMap, "mix", 1);
                data.softness = getValue(constraintMap, "softness", 0) * scale;
                data.bendDirection = getValue(constraintMap, "bendPositive", true) ? 1 : -1;
                data.compress = getValue(constraintMap, "compress", false);
                data.stretch = getValue(constraintMap, "stretch", false);
                data.uniform = getValue(constraintMap, "uniform", false);
                skeletonData.ikConstraints.push(data);
            }
        }
        // Transform constraints.
        if (root.transform) {
            for (let i = 0; i < root.transform.length; i++) {
                let constraintMap = root.transform[i];
                let data = new TransformConstraintData(constraintMap.name);
                data.order = getValue(constraintMap, "order", 0);
                data.skinRequired = getValue(constraintMap, "skin", false);
                for (let ii = 0; ii < constraintMap.bones.length; ii++) {
                    let boneName = constraintMap.bones[ii];
                    let bone = skeletonData.findBone(boneName);
                    if (!bone)
                        throw new Error(`Couldn't find bone ${boneName} for transform constraint ${constraintMap.name}.`);
                    data.bones.push(bone);
                }
                let targetName = constraintMap.target;
                let target = skeletonData.findBone(targetName);
                if (!target)
                    throw new Error(`Couldn't find target bone ${targetName} for transform constraint ${constraintMap.name}.`);
                data.target = target;
                data.local = getValue(constraintMap, "local", false);
                data.relative = getValue(constraintMap, "relative", false);
                data.offsetRotation = getValue(constraintMap, "rotation", 0);
                data.offsetX = getValue(constraintMap, "x", 0) * scale;
                data.offsetY = getValue(constraintMap, "y", 0) * scale;
                data.offsetScaleX = getValue(constraintMap, "scaleX", 0);
                data.offsetScaleY = getValue(constraintMap, "scaleY", 0);
                data.offsetShearY = getValue(constraintMap, "shearY", 0);
                data.mixRotate = getValue(constraintMap, "mixRotate", 1);
                data.mixX = getValue(constraintMap, "mixX", 1);
                data.mixY = getValue(constraintMap, "mixY", data.mixX);
                data.mixScaleX = getValue(constraintMap, "mixScaleX", 1);
                data.mixScaleY = getValue(constraintMap, "mixScaleY", data.mixScaleX);
                data.mixShearY = getValue(constraintMap, "mixShearY", 1);
                skeletonData.transformConstraints.push(data);
            }
        }
        // Path constraints.
        if (root.path) {
            for (let i = 0; i < root.path.length; i++) {
                let constraintMap = root.path[i];
                let data = new PathConstraintData(constraintMap.name);
                data.order = getValue(constraintMap, "order", 0);
                data.skinRequired = getValue(constraintMap, "skin", false);
                for (let ii = 0; ii < constraintMap.bones.length; ii++) {
                    let boneName = constraintMap.bones[ii];
                    let bone = skeletonData.findBone(boneName);
                    if (!bone)
                        throw new Error(`Couldn't find bone ${boneName} for path constraint ${constraintMap.name}.`);
                    data.bones.push(bone);
                }
                let targetName = constraintMap.target;
                let target = skeletonData.findSlot(targetName);
                if (!target)
                    throw new Error(`Couldn't find target slot ${targetName} for path constraint ${constraintMap.name}.`);
                data.target = target;
                data.positionMode = Utils.enumValue(PositionMode, getValue(constraintMap, "positionMode", "Percent"));
                data.spacingMode = Utils.enumValue(SpacingMode, getValue(constraintMap, "spacingMode", "Length"));
                data.rotateMode = Utils.enumValue(RotateMode, getValue(constraintMap, "rotateMode", "Tangent"));
                data.offsetRotation = getValue(constraintMap, "rotation", 0);
                data.position = getValue(constraintMap, "position", 0);
                if (data.positionMode == PositionMode.Fixed)
                    data.position *= scale;
                data.spacing = getValue(constraintMap, "spacing", 0);
                if (data.spacingMode == SpacingMode.Length || data.spacingMode == SpacingMode.Fixed)
                    data.spacing *= scale;
                data.mixRotate = getValue(constraintMap, "mixRotate", 1);
                data.mixX = getValue(constraintMap, "mixX", 1);
                data.mixY = getValue(constraintMap, "mixY", data.mixX);
                skeletonData.pathConstraints.push(data);
            }
        }
        // Physics constraints.
        if (root.physics) {
            for (let i = 0; i < root.physics.length; i++) {
                const constraintMap = root.physics[i];
                const data = new PhysicsConstraintData(constraintMap.name);
                data.order = getValue(constraintMap, "order", 0);
                data.skinRequired = getValue(constraintMap, "skin", false);
                const boneName = constraintMap.bone;
                const bone = skeletonData.findBone(boneName);
                if (bone == null)
                    throw new Error("Physics bone not found: " + boneName);
                data.bone = bone;
                data.x = getValue(constraintMap, "x", 0);
                data.y = getValue(constraintMap, "y", 0);
                data.rotate = getValue(constraintMap, "rotate", 0);
                data.scaleX = getValue(constraintMap, "scaleX", 0);
                data.shearX = getValue(constraintMap, "shearX", 0);
                data.limit = getValue(constraintMap, "limit", 5000) * scale;
                data.step = 1 / getValue(constraintMap, "fps", 60);
                data.inertia = getValue(constraintMap, "inertia", 1);
                data.strength = getValue(constraintMap, "strength", 100);
                data.damping = getValue(constraintMap, "damping", 1);
                data.massInverse = 1 / getValue(constraintMap, "mass", 1);
                data.wind = getValue(constraintMap, "wind", 0);
                data.gravity = getValue(constraintMap, "gravity", 0);
                data.mix = getValue(constraintMap, "mix", 1);
                data.inertiaGlobal = getValue(constraintMap, "inertiaGlobal", false);
                data.strengthGlobal = getValue(constraintMap, "strengthGlobal", false);
                data.dampingGlobal = getValue(constraintMap, "dampingGlobal", false);
                data.massGlobal = getValue(constraintMap, "massGlobal", false);
                data.windGlobal = getValue(constraintMap, "windGlobal", false);
                data.gravityGlobal = getValue(constraintMap, "gravityGlobal", false);
                data.mixGlobal = getValue(constraintMap, "mixGlobal", false);
                skeletonData.physicsConstraints.push(data);
            }
        }
        // Skins.
        if (root.skins) {
            for (let i = 0; i < root.skins.length; i++) {
                let skinMap = root.skins[i];
                let skin = new Skin(skinMap.name);
                if (skinMap.bones) {
                    for (let ii = 0; ii < skinMap.bones.length; ii++) {
                        let boneName = skinMap.bones[ii];
                        let bone = skeletonData.findBone(boneName);
                        if (!bone)
                            throw new Error(`Couldn't find bone ${boneName} for skin ${skinMap.name}.`);
                        skin.bones.push(bone);
                    }
                }
                if (skinMap.ik) {
                    for (let ii = 0; ii < skinMap.ik.length; ii++) {
                        let constraintName = skinMap.ik[ii];
                        let constraint = skeletonData.findIkConstraint(constraintName);
                        if (!constraint)
                            throw new Error(`Couldn't find IK constraint ${constraintName} for skin ${skinMap.name}.`);
                        skin.constraints.push(constraint);
                    }
                }
                if (skinMap.transform) {
                    for (let ii = 0; ii < skinMap.transform.length; ii++) {
                        let constraintName = skinMap.transform[ii];
                        let constraint = skeletonData.findTransformConstraint(constraintName);
                        if (!constraint)
                            throw new Error(`Couldn't find transform constraint ${constraintName} for skin ${skinMap.name}.`);
                        skin.constraints.push(constraint);
                    }
                }
                if (skinMap.path) {
                    for (let ii = 0; ii < skinMap.path.length; ii++) {
                        let constraintName = skinMap.path[ii];
                        let constraint = skeletonData.findPathConstraint(constraintName);
                        if (!constraint)
                            throw new Error(`Couldn't find path constraint ${constraintName} for skin ${skinMap.name}.`);
                        skin.constraints.push(constraint);
                    }
                }
                if (skinMap.physics) {
                    for (let ii = 0; ii < skinMap.physics.length; ii++) {
                        let constraintName = skinMap.physics[ii];
                        let constraint = skeletonData.findPhysicsConstraint(constraintName);
                        if (!constraint)
                            throw new Error(`Couldn't find physics constraint ${constraintName} for skin ${skinMap.name}.`);
                        skin.constraints.push(constraint);
                    }
                }
                for (let slotName in skinMap.attachments) {
                    let slot = skeletonData.findSlot(slotName);
                    if (!slot)
                        throw new Error(`Couldn't find slot ${slotName} for skin ${skinMap.name}.`);
                    let slotMap = skinMap.attachments[slotName];
                    for (let entryName in slotMap) {
                        let attachment = this.readAttachment(slotMap[entryName], skin, slot.index, entryName, skeletonData);
                        if (attachment)
                            skin.setAttachment(slot.index, entryName, attachment);
                    }
                }
                skeletonData.skins.push(skin);
                if (skin.name == "default")
                    skeletonData.defaultSkin = skin;
            }
        }
        // Linked meshes.
        for (let i = 0, n = this.linkedMeshes.length; i < n; i++) {
            let linkedMesh = this.linkedMeshes[i];
            let skin = !linkedMesh.skin ? skeletonData.defaultSkin : skeletonData.findSkin(linkedMesh.skin);
            if (!skin)
                throw new Error(`Skin not found: ${linkedMesh.skin}`);
            let parent = skin.getAttachment(linkedMesh.slotIndex, linkedMesh.parent);
            if (!parent)
                throw new Error(`Parent mesh not found: ${linkedMesh.parent}`);
            linkedMesh.mesh.timelineAttachment = linkedMesh.inheritTimeline ? parent : linkedMesh.mesh;
            linkedMesh.mesh.setParentMesh(parent);
            if (linkedMesh.mesh.region != null)
                linkedMesh.mesh.updateRegion();
        }
        this.linkedMeshes.length = 0;
        // Events.
        if (root.events) {
            for (let eventName in root.events) {
                let eventMap = root.events[eventName];
                let data = new EventData(eventName);
                data.intValue = getValue(eventMap, "int", 0);
                data.floatValue = getValue(eventMap, "float", 0);
                data.stringValue = getValue(eventMap, "string", "");
                data.audioPath = getValue(eventMap, "audio", null);
                if (data.audioPath) {
                    data.volume = getValue(eventMap, "volume", 1);
                    data.balance = getValue(eventMap, "balance", 0);
                }
                skeletonData.events.push(data);
            }
        }
        // Animations.
        if (root.animations) {
            for (let animationName in root.animations) {
                let animationMap = root.animations[animationName];
                this.readAnimation(animationMap, animationName, skeletonData);
            }
        }
        return skeletonData;
    }
    readAttachment(map, skin, slotIndex, name, skeletonData) {
        let scale = this.scale;
        name = getValue(map, "name", name);
        switch (getValue(map, "type", "region")) {
            case "region": {
                let path = getValue(map, "path", name);
                let sequence = this.readSequence(getValue(map, "sequence", null));
                let region = this.attachmentLoader.newRegionAttachment(skin, name, path, sequence);
                if (!region)
                    return null;
                region.path = path;
                region.x = getValue(map, "x", 0) * scale;
                region.y = getValue(map, "y", 0) * scale;
                region.scaleX = getValue(map, "scaleX", 1);
                region.scaleY = getValue(map, "scaleY", 1);
                region.rotation = getValue(map, "rotation", 0);
                region.width = map.width * scale;
                region.height = map.height * scale;
                region.sequence = sequence;
                let color = getValue(map, "color", null);
                if (color)
                    region.color.setFromString(color);
                if (region.region != null)
                    region.updateRegion();
                return region;
            }
            case "boundingbox": {
                let box = this.attachmentLoader.newBoundingBoxAttachment(skin, name);
                if (!box)
                    return null;
                this.readVertices(map, box, map.vertexCount << 1);
                let color = getValue(map, "color", null);
                if (color)
                    box.color.setFromString(color);
                return box;
            }
            case "mesh":
            case "linkedmesh": {
                let path = getValue(map, "path", name);
                let sequence = this.readSequence(getValue(map, "sequence", null));
                let mesh = this.attachmentLoader.newMeshAttachment(skin, name, path, sequence);
                if (!mesh)
                    return null;
                mesh.path = path;
                let color = getValue(map, "color", null);
                if (color)
                    mesh.color.setFromString(color);
                mesh.width = getValue(map, "width", 0) * scale;
                mesh.height = getValue(map, "height", 0) * scale;
                mesh.sequence = sequence;
                let parent = getValue(map, "parent", null);
                if (parent) {
                    this.linkedMeshes.push(new LinkedMesh(mesh, getValue(map, "skin", null), slotIndex, parent, getValue(map, "timelines", true)));
                    return mesh;
                }
                let uvs = map.uvs;
                this.readVertices(map, mesh, uvs.length);
                mesh.triangles = map.triangles;
                mesh.regionUVs = uvs;
                if (mesh.region != null)
                    mesh.updateRegion();
                mesh.edges = getValue(map, "edges", null);
                mesh.hullLength = getValue(map, "hull", 0) * 2;
                return mesh;
            }
            case "path": {
                let path = this.attachmentLoader.newPathAttachment(skin, name);
                if (!path)
                    return null;
                path.closed = getValue(map, "closed", false);
                path.constantSpeed = getValue(map, "constantSpeed", true);
                let vertexCount = map.vertexCount;
                this.readVertices(map, path, vertexCount << 1);
                let lengths = Utils.newArray(vertexCount / 3, 0);
                for (let i = 0; i < map.lengths.length; i++)
                    lengths[i] = map.lengths[i] * scale;
                path.lengths = lengths;
                let color = getValue(map, "color", null);
                if (color)
                    path.color.setFromString(color);
                return path;
            }
            case "point": {
                let point = this.attachmentLoader.newPointAttachment(skin, name);
                if (!point)
                    return null;
                point.x = getValue(map, "x", 0) * scale;
                point.y = getValue(map, "y", 0) * scale;
                point.rotation = getValue(map, "rotation", 0);
                let color = getValue(map, "color", null);
                if (color)
                    point.color.setFromString(color);
                return point;
            }
            case "clipping": {
                let clip = this.attachmentLoader.newClippingAttachment(skin, name);
                if (!clip)
                    return null;
                let end = getValue(map, "end", null);
                if (end)
                    clip.endSlot = skeletonData.findSlot(end);
                let vertexCount = map.vertexCount;
                this.readVertices(map, clip, vertexCount << 1);
                let color = getValue(map, "color", null);
                if (color)
                    clip.color.setFromString(color);
                return clip;
            }
        }
        return null;
    }
    readSequence(map) {
        if (map == null)
            return null;
        let sequence = new Sequence(getValue(map, "count", 0));
        sequence.start = getValue(map, "start", 1);
        sequence.digits = getValue(map, "digits", 0);
        sequence.setupIndex = getValue(map, "setup", 0);
        return sequence;
    }
    readVertices(map, attachment, verticesLength) {
        let scale = this.scale;
        attachment.worldVerticesLength = verticesLength;
        let vertices = map.vertices;
        if (verticesLength == vertices.length) {
            let scaledVertices = Utils.toFloatArray(vertices);
            if (scale != 1) {
                for (let i = 0, n = vertices.length; i < n; i++)
                    scaledVertices[i] *= scale;
            }
            attachment.vertices = scaledVertices;
            return;
        }
        let weights = new Array();
        let bones = new Array();
        for (let i = 0, n = vertices.length; i < n;) {
            let boneCount = vertices[i++];
            bones.push(boneCount);
            for (let nn = i + boneCount * 4; i < nn; i += 4) {
                bones.push(vertices[i]);
                weights.push(vertices[i + 1] * scale);
                weights.push(vertices[i + 2] * scale);
                weights.push(vertices[i + 3]);
            }
        }
        attachment.bones = bones;
        attachment.vertices = Utils.toFloatArray(weights);
    }
    readAnimation(map, name, skeletonData) {
        let scale = this.scale;
        let timelines = new Array();
        // Slot timelines.
        if (map.slots) {
            for (let slotName in map.slots) {
                let slotMap = map.slots[slotName];
                let slot = skeletonData.findSlot(slotName);
                if (!slot)
                    throw new Error("Slot not found: " + slotName);
                let slotIndex = slot.index;
                for (let timelineName in slotMap) {
                    let timelineMap = slotMap[timelineName];
                    if (!timelineMap)
                        continue;
                    let frames = timelineMap.length;
                    if (timelineName == "attachment") {
                        let timeline = new AttachmentTimeline(frames, slotIndex);
                        for (let frame = 0; frame < frames; frame++) {
                            let keyMap = timelineMap[frame];
                            timeline.setFrame(frame, getValue(keyMap, "time", 0), getValue(keyMap, "name", null));
                        }
                        timelines.push(timeline);
                    }
                    else if (timelineName == "rgba") {
                        let timeline = new RGBATimeline(frames, frames << 2, slotIndex);
                        let keyMap = timelineMap[0];
                        let time = getValue(keyMap, "time", 0);
                        let color = Color.fromString(keyMap.color);
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, color.r, color.g, color.b, color.a);
                            let nextMap = timelineMap[frame + 1];
                            if (!nextMap) {
                                timeline.shrink(bezier);
                                break;
                            }
                            let time2 = getValue(nextMap, "time", 0);
                            let newColor = Color.fromString(nextMap.color);
                            let curve = keyMap.curve;
                            if (curve) {
                                bezier = readCurve(curve, timeline, bezier, frame, 0, time, time2, color.r, newColor.r, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 1, time, time2, color.g, newColor.g, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 2, time, time2, color.b, newColor.b, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 3, time, time2, color.a, newColor.a, 1);
                            }
                            time = time2;
                            color = newColor;
                            keyMap = nextMap;
                        }
                        timelines.push(timeline);
                    }
                    else if (timelineName == "rgb") {
                        let timeline = new RGBTimeline(frames, frames * 3, slotIndex);
                        let keyMap = timelineMap[0];
                        let time = getValue(keyMap, "time", 0);
                        let color = Color.fromString(keyMap.color);
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, color.r, color.g, color.b);
                            let nextMap = timelineMap[frame + 1];
                            if (!nextMap) {
                                timeline.shrink(bezier);
                                break;
                            }
                            let time2 = getValue(nextMap, "time", 0);
                            let newColor = Color.fromString(nextMap.color);
                            let curve = keyMap.curve;
                            if (curve) {
                                bezier = readCurve(curve, timeline, bezier, frame, 0, time, time2, color.r, newColor.r, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 1, time, time2, color.g, newColor.g, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 2, time, time2, color.b, newColor.b, 1);
                            }
                            time = time2;
                            color = newColor;
                            keyMap = nextMap;
                        }
                        timelines.push(timeline);
                    }
                    else if (timelineName == "alpha") {
                        timelines.push(readTimeline1(timelineMap, new AlphaTimeline(frames, frames, slotIndex), 0, 1));
                    }
                    else if (timelineName == "rgba2") {
                        let timeline = new RGBA2Timeline(frames, frames * 7, slotIndex);
                        let keyMap = timelineMap[0];
                        let time = getValue(keyMap, "time", 0);
                        let color = Color.fromString(keyMap.light);
                        let color2 = Color.fromString(keyMap.dark);
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, color.r, color.g, color.b, color.a, color2.r, color2.g, color2.b);
                            let nextMap = timelineMap[frame + 1];
                            if (!nextMap) {
                                timeline.shrink(bezier);
                                break;
                            }
                            let time2 = getValue(nextMap, "time", 0);
                            let newColor = Color.fromString(nextMap.light);
                            let newColor2 = Color.fromString(nextMap.dark);
                            let curve = keyMap.curve;
                            if (curve) {
                                bezier = readCurve(curve, timeline, bezier, frame, 0, time, time2, color.r, newColor.r, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 1, time, time2, color.g, newColor.g, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 2, time, time2, color.b, newColor.b, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 3, time, time2, color.a, newColor.a, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 4, time, time2, color2.r, newColor2.r, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 5, time, time2, color2.g, newColor2.g, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 6, time, time2, color2.b, newColor2.b, 1);
                            }
                            time = time2;
                            color = newColor;
                            color2 = newColor2;
                            keyMap = nextMap;
                        }
                        timelines.push(timeline);
                    }
                    else if (timelineName == "rgb2") {
                        let timeline = new RGB2Timeline(frames, frames * 6, slotIndex);
                        let keyMap = timelineMap[0];
                        let time = getValue(keyMap, "time", 0);
                        let color = Color.fromString(keyMap.light);
                        let color2 = Color.fromString(keyMap.dark);
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, color.r, color.g, color.b, color2.r, color2.g, color2.b);
                            let nextMap = timelineMap[frame + 1];
                            if (!nextMap) {
                                timeline.shrink(bezier);
                                break;
                            }
                            let time2 = getValue(nextMap, "time", 0);
                            let newColor = Color.fromString(nextMap.light);
                            let newColor2 = Color.fromString(nextMap.dark);
                            let curve = keyMap.curve;
                            if (curve) {
                                bezier = readCurve(curve, timeline, bezier, frame, 0, time, time2, color.r, newColor.r, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 1, time, time2, color.g, newColor.g, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 2, time, time2, color.b, newColor.b, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 3, time, time2, color2.r, newColor2.r, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 4, time, time2, color2.g, newColor2.g, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 5, time, time2, color2.b, newColor2.b, 1);
                            }
                            time = time2;
                            color = newColor;
                            color2 = newColor2;
                            keyMap = nextMap;
                        }
                        timelines.push(timeline);
                    }
                }
            }
        }
        // Bone timelines.
        if (map.bones) {
            for (let boneName in map.bones) {
                let boneMap = map.bones[boneName];
                let bone = skeletonData.findBone(boneName);
                if (!bone)
                    throw new Error("Bone not found: " + boneName);
                let boneIndex = bone.index;
                for (let timelineName in boneMap) {
                    let timelineMap = boneMap[timelineName];
                    let frames = timelineMap.length;
                    if (frames == 0)
                        continue;
                    if (timelineName === "rotate") {
                        timelines.push(readTimeline1(timelineMap, new RotateTimeline(frames, frames, boneIndex), 0, 1));
                    }
                    else if (timelineName === "translate") {
                        let timeline = new TranslateTimeline(frames, frames << 1, boneIndex);
                        timelines.push(readTimeline2(timelineMap, timeline, "x", "y", 0, scale));
                    }
                    else if (timelineName === "translatex") {
                        let timeline = new TranslateXTimeline(frames, frames, boneIndex);
                        timelines.push(readTimeline1(timelineMap, timeline, 0, scale));
                    }
                    else if (timelineName === "translatey") {
                        let timeline = new TranslateYTimeline(frames, frames, boneIndex);
                        timelines.push(readTimeline1(timelineMap, timeline, 0, scale));
                    }
                    else if (timelineName === "scale") {
                        let timeline = new ScaleTimeline(frames, frames << 1, boneIndex);
                        timelines.push(readTimeline2(timelineMap, timeline, "x", "y", 1, 1));
                    }
                    else if (timelineName === "scalex") {
                        let timeline = new ScaleXTimeline(frames, frames, boneIndex);
                        timelines.push(readTimeline1(timelineMap, timeline, 1, 1));
                    }
                    else if (timelineName === "scaley") {
                        let timeline = new ScaleYTimeline(frames, frames, boneIndex);
                        timelines.push(readTimeline1(timelineMap, timeline, 1, 1));
                    }
                    else if (timelineName === "shear") {
                        let timeline = new ShearTimeline(frames, frames << 1, boneIndex);
                        timelines.push(readTimeline2(timelineMap, timeline, "x", "y", 0, 1));
                    }
                    else if (timelineName === "shearx") {
                        let timeline = new ShearXTimeline(frames, frames, boneIndex);
                        timelines.push(readTimeline1(timelineMap, timeline, 0, 1));
                    }
                    else if (timelineName === "sheary") {
                        let timeline = new ShearYTimeline(frames, frames, boneIndex);
                        timelines.push(readTimeline1(timelineMap, timeline, 0, 1));
                    }
                    else if (timelineName === "inherit") {
                        let timeline = new InheritTimeline(frames, bone.index);
                        for (let frame = 0; frame < timelineMap.length; frame++) {
                            let aFrame = timelineMap[frame];
                            timeline.setFrame(frame, getValue(aFrame, "time", 0), Utils.enumValue(Inherit, getValue(aFrame, "inherit", "Normal")));
                        }
                        timelines.push(timeline);
                    }
                }
            }
        }
        // IK constraint timelines.
        if (map.ik) {
            for (let constraintName in map.ik) {
                let constraintMap = map.ik[constraintName];
                let keyMap = constraintMap[0];
                if (!keyMap)
                    continue;
                let constraint = skeletonData.findIkConstraint(constraintName);
                if (!constraint)
                    throw new Error("IK Constraint not found: " + constraintName);
                let constraintIndex = skeletonData.ikConstraints.indexOf(constraint);
                let timeline = new IkConstraintTimeline(constraintMap.length, constraintMap.length << 1, constraintIndex);
                let time = getValue(keyMap, "time", 0);
                let mix = getValue(keyMap, "mix", 1);
                let softness = getValue(keyMap, "softness", 0) * scale;
                for (let frame = 0, bezier = 0;; frame++) {
                    timeline.setFrame(frame, time, mix, softness, getValue(keyMap, "bendPositive", true) ? 1 : -1, getValue(keyMap, "compress", false), getValue(keyMap, "stretch", false));
                    let nextMap = constraintMap[frame + 1];
                    if (!nextMap) {
                        timeline.shrink(bezier);
                        break;
                    }
                    let time2 = getValue(nextMap, "time", 0);
                    let mix2 = getValue(nextMap, "mix", 1);
                    let softness2 = getValue(nextMap, "softness", 0) * scale;
                    let curve = keyMap.curve;
                    if (curve) {
                        bezier = readCurve(curve, timeline, bezier, frame, 0, time, time2, mix, mix2, 1);
                        bezier = readCurve(curve, timeline, bezier, frame, 1, time, time2, softness, softness2, scale);
                    }
                    time = time2;
                    mix = mix2;
                    softness = softness2;
                    keyMap = nextMap;
                }
                timelines.push(timeline);
            }
        }
        // Transform constraint timelines.
        if (map.transform) {
            for (let constraintName in map.transform) {
                let timelineMap = map.transform[constraintName];
                let keyMap = timelineMap[0];
                if (!keyMap)
                    continue;
                let constraint = skeletonData.findTransformConstraint(constraintName);
                if (!constraint)
                    throw new Error("Transform constraint not found: " + constraintName);
                let constraintIndex = skeletonData.transformConstraints.indexOf(constraint);
                let timeline = new TransformConstraintTimeline(timelineMap.length, timelineMap.length * 6, constraintIndex);
                let time = getValue(keyMap, "time", 0);
                let mixRotate = getValue(keyMap, "mixRotate", 1);
                let mixX = getValue(keyMap, "mixX", 1);
                let mixY = getValue(keyMap, "mixY", mixX);
                let mixScaleX = getValue(keyMap, "mixScaleX", 1);
                let mixScaleY = getValue(keyMap, "mixScaleY", mixScaleX);
                let mixShearY = getValue(keyMap, "mixShearY", 1);
                for (let frame = 0, bezier = 0;; frame++) {
                    timeline.setFrame(frame, time, mixRotate, mixX, mixY, mixScaleX, mixScaleY, mixShearY);
                    let nextMap = timelineMap[frame + 1];
                    if (!nextMap) {
                        timeline.shrink(bezier);
                        break;
                    }
                    let time2 = getValue(nextMap, "time", 0);
                    let mixRotate2 = getValue(nextMap, "mixRotate", 1);
                    let mixX2 = getValue(nextMap, "mixX", 1);
                    let mixY2 = getValue(nextMap, "mixY", mixX2);
                    let mixScaleX2 = getValue(nextMap, "mixScaleX", 1);
                    let mixScaleY2 = getValue(nextMap, "mixScaleY", mixScaleX2);
                    let mixShearY2 = getValue(nextMap, "mixShearY", 1);
                    let curve = keyMap.curve;
                    if (curve) {
                        bezier = readCurve(curve, timeline, bezier, frame, 0, time, time2, mixRotate, mixRotate2, 1);
                        bezier = readCurve(curve, timeline, bezier, frame, 1, time, time2, mixX, mixX2, 1);
                        bezier = readCurve(curve, timeline, bezier, frame, 2, time, time2, mixY, mixY2, 1);
                        bezier = readCurve(curve, timeline, bezier, frame, 3, time, time2, mixScaleX, mixScaleX2, 1);
                        bezier = readCurve(curve, timeline, bezier, frame, 4, time, time2, mixScaleY, mixScaleY2, 1);
                        bezier = readCurve(curve, timeline, bezier, frame, 5, time, time2, mixShearY, mixShearY2, 1);
                    }
                    time = time2;
                    mixRotate = mixRotate2;
                    mixX = mixX2;
                    mixY = mixY2;
                    mixScaleX = mixScaleX2;
                    mixScaleY = mixScaleY2;
                    mixScaleX = mixScaleX2;
                    keyMap = nextMap;
                }
                timelines.push(timeline);
            }
        }
        // Path constraint timelines.
        if (map.path) {
            for (let constraintName in map.path) {
                let constraintMap = map.path[constraintName];
                let constraint = skeletonData.findPathConstraint(constraintName);
                if (!constraint)
                    throw new Error("Path constraint not found: " + constraintName);
                let constraintIndex = skeletonData.pathConstraints.indexOf(constraint);
                for (let timelineName in constraintMap) {
                    let timelineMap = constraintMap[timelineName];
                    let keyMap = timelineMap[0];
                    if (!keyMap)
                        continue;
                    let frames = timelineMap.length;
                    if (timelineName === "position") {
                        let timeline = new PathConstraintPositionTimeline(frames, frames, constraintIndex);
                        timelines.push(readTimeline1(timelineMap, timeline, 0, constraint.positionMode == PositionMode.Fixed ? scale : 1));
                    }
                    else if (timelineName === "spacing") {
                        let timeline = new PathConstraintSpacingTimeline(frames, frames, constraintIndex);
                        timelines.push(readTimeline1(timelineMap, timeline, 0, constraint.spacingMode == SpacingMode.Length || constraint.spacingMode == SpacingMode.Fixed ? scale : 1));
                    }
                    else if (timelineName === "mix") {
                        let timeline = new PathConstraintMixTimeline(frames, frames * 3, constraintIndex);
                        let time = getValue(keyMap, "time", 0);
                        let mixRotate = getValue(keyMap, "mixRotate", 1);
                        let mixX = getValue(keyMap, "mixX", 1);
                        let mixY = getValue(keyMap, "mixY", mixX);
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, mixRotate, mixX, mixY);
                            let nextMap = timelineMap[frame + 1];
                            if (!nextMap) {
                                timeline.shrink(bezier);
                                break;
                            }
                            let time2 = getValue(nextMap, "time", 0);
                            let mixRotate2 = getValue(nextMap, "mixRotate", 1);
                            let mixX2 = getValue(nextMap, "mixX", 1);
                            let mixY2 = getValue(nextMap, "mixY", mixX2);
                            let curve = keyMap.curve;
                            if (curve) {
                                bezier = readCurve(curve, timeline, bezier, frame, 0, time, time2, mixRotate, mixRotate2, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 1, time, time2, mixX, mixX2, 1);
                                bezier = readCurve(curve, timeline, bezier, frame, 2, time, time2, mixY, mixY2, 1);
                            }
                            time = time2;
                            mixRotate = mixRotate2;
                            mixX = mixX2;
                            mixY = mixY2;
                            keyMap = nextMap;
                        }
                        timelines.push(timeline);
                    }
                }
            }
        }
        // Physics constraint timelines.
        if (map.physics) {
            for (let constraintName in map.physics) {
                let constraintMap = map.physics[constraintName];
                let constraintIndex = -1;
                if (constraintName.length > 0) {
                    let constraint = skeletonData.findPhysicsConstraint(constraintName);
                    if (!constraint)
                        throw new Error("Physics constraint not found: " + constraintName);
                    constraintIndex = skeletonData.physicsConstraints.indexOf(constraint);
                }
                for (let timelineName in constraintMap) {
                    let timelineMap = constraintMap[timelineName];
                    let keyMap = timelineMap[0];
                    if (!keyMap)
                        continue;
                    let frames = timelineMap.length;
                    if (timelineName == "reset") {
                        const timeline = new PhysicsConstraintResetTimeline(frames, constraintIndex);
                        for (let frame = 0; keyMap != null; keyMap = timelineMap[frame + 1], frame++)
                            timeline.setFrame(frame, getValue(keyMap, "time", 0));
                        timelines.push(timeline);
                        continue;
                    }
                    let timeline;
                    if (timelineName == "inertia")
                        timeline = new PhysicsConstraintInertiaTimeline(frames, frames, constraintIndex);
                    else if (timelineName == "strength")
                        timeline = new PhysicsConstraintStrengthTimeline(frames, frames, constraintIndex);
                    else if (timelineName == "damping")
                        timeline = new PhysicsConstraintDampingTimeline(frames, frames, constraintIndex);
                    else if (timelineName == "mass")
                        timeline = new PhysicsConstraintMassTimeline(frames, frames, constraintIndex);
                    else if (timelineName == "wind")
                        timeline = new PhysicsConstraintWindTimeline(frames, frames, constraintIndex);
                    else if (timelineName == "gravity")
                        timeline = new PhysicsConstraintGravityTimeline(frames, frames, constraintIndex);
                    else if (timelineName == "mix") //
                        timeline = new PhysicsConstraintMixTimeline(frames, frames, constraintIndex);
                    else
                        continue;
                    timelines.push(readTimeline1(timelineMap, timeline, 0, 1));
                }
            }
        }
        // Attachment timelines.
        if (map.attachments) {
            for (let attachmentsName in map.attachments) {
                let attachmentsMap = map.attachments[attachmentsName];
                let skin = skeletonData.findSkin(attachmentsName);
                if (!skin)
                    throw new Error("Skin not found: " + attachmentsName);
                for (let slotMapName in attachmentsMap) {
                    let slotMap = attachmentsMap[slotMapName];
                    let slot = skeletonData.findSlot(slotMapName);
                    if (!slot)
                        throw new Error("Slot not found: " + slotMapName);
                    let slotIndex = slot.index;
                    for (let attachmentMapName in slotMap) {
                        let attachmentMap = slotMap[attachmentMapName];
                        let attachment = skin.getAttachment(slotIndex, attachmentMapName);
                        for (let timelineMapName in attachmentMap) {
                            let timelineMap = attachmentMap[timelineMapName];
                            let keyMap = timelineMap[0];
                            if (!keyMap)
                                continue;
                            if (timelineMapName == "deform") {
                                let weighted = attachment.bones;
                                let vertices = attachment.vertices;
                                let deformLength = weighted ? vertices.length / 3 * 2 : vertices.length;
                                let timeline = new DeformTimeline(timelineMap.length, timelineMap.length, slotIndex, attachment);
                                let time = getValue(keyMap, "time", 0);
                                for (let frame = 0, bezier = 0;; frame++) {
                                    let deform;
                                    let verticesValue = getValue(keyMap, "vertices", null);
                                    if (!verticesValue)
                                        deform = weighted ? Utils.newFloatArray(deformLength) : vertices;
                                    else {
                                        deform = Utils.newFloatArray(deformLength);
                                        let start = getValue(keyMap, "offset", 0);
                                        Utils.arrayCopy(verticesValue, 0, deform, start, verticesValue.length);
                                        if (scale != 1) {
                                            for (let i = start, n = i + verticesValue.length; i < n; i++)
                                                deform[i] *= scale;
                                        }
                                        if (!weighted) {
                                            for (let i = 0; i < deformLength; i++)
                                                deform[i] += vertices[i];
                                        }
                                    }
                                    timeline.setFrame(frame, time, deform);
                                    let nextMap = timelineMap[frame + 1];
                                    if (!nextMap) {
                                        timeline.shrink(bezier);
                                        break;
                                    }
                                    let time2 = getValue(nextMap, "time", 0);
                                    let curve = keyMap.curve;
                                    if (curve)
                                        bezier = readCurve(curve, timeline, bezier, frame, 0, time, time2, 0, 1, 1);
                                    time = time2;
                                    keyMap = nextMap;
                                }
                                timelines.push(timeline);
                            }
                            else if (timelineMapName == "sequence") {
                                let timeline = new SequenceTimeline(timelineMap.length, slotIndex, attachment);
                                let lastDelay = 0;
                                for (let frame = 0; frame < timelineMap.length; frame++) {
                                    let delay = getValue(keyMap, "delay", lastDelay);
                                    let time = getValue(keyMap, "time", 0);
                                    let mode = SequenceMode[getValue(keyMap, "mode", "hold")];
                                    let index = getValue(keyMap, "index", 0);
                                    timeline.setFrame(frame, time, mode, index, delay);
                                    lastDelay = delay;
                                    keyMap = timelineMap[frame + 1];
                                }
                                timelines.push(timeline);
                            }
                        }
                    }
                }
            }
        }
        // Draw order timelines.
        if (map.drawOrder) {
            let timeline = new DrawOrderTimeline(map.drawOrder.length);
            let slotCount = skeletonData.slots.length;
            let frame = 0;
            for (let i = 0; i < map.drawOrder.length; i++, frame++) {
                let drawOrderMap = map.drawOrder[i];
                let drawOrder = null;
                let offsets = getValue(drawOrderMap, "offsets", null);
                if (offsets) {
                    drawOrder = Utils.newArray(slotCount, -1);
                    let unchanged = Utils.newArray(slotCount - offsets.length, 0);
                    let originalIndex = 0, unchangedIndex = 0;
                    for (let ii = 0; ii < offsets.length; ii++) {
                        let offsetMap = offsets[ii];
                        let slot = skeletonData.findSlot(offsetMap.slot);
                        if (!slot)
                            throw new Error("Slot not found: " + slot);
                        let slotIndex = slot.index;
                        // Collect unchanged items.
                        while (originalIndex != slotIndex)
                            unchanged[unchangedIndex++] = originalIndex++;
                        // Set changed items.
                        drawOrder[originalIndex + offsetMap.offset] = originalIndex++;
                    }
                    // Collect remaining unchanged items.
                    while (originalIndex < slotCount)
                        unchanged[unchangedIndex++] = originalIndex++;
                    // Fill in unchanged items.
                    for (let ii = slotCount - 1; ii >= 0; ii--)
                        if (drawOrder[ii] == -1)
                            drawOrder[ii] = unchanged[--unchangedIndex];
                }
                timeline.setFrame(frame, getValue(drawOrderMap, "time", 0), drawOrder);
            }
            timelines.push(timeline);
        }
        // Event timelines.
        if (map.events) {
            let timeline = new EventTimeline(map.events.length);
            let frame = 0;
            for (let i = 0; i < map.events.length; i++, frame++) {
                let eventMap = map.events[i];
                let eventData = skeletonData.findEvent(eventMap.name);
                if (!eventData)
                    throw new Error("Event not found: " + eventMap.name);
                let event = new Event(Utils.toSinglePrecision(getValue(eventMap, "time", 0)), eventData);
                event.intValue = getValue(eventMap, "int", eventData.intValue);
                event.floatValue = getValue(eventMap, "float", eventData.floatValue);
                event.stringValue = getValue(eventMap, "string", eventData.stringValue);
                if (event.data.audioPath) {
                    event.volume = getValue(eventMap, "volume", 1);
                    event.balance = getValue(eventMap, "balance", 0);
                }
                timeline.setFrame(frame, event);
            }
            timelines.push(timeline);
        }
        let duration = 0;
        for (let i = 0, n = timelines.length; i < n; i++)
            duration = Math.max(duration, timelines[i].getDuration());
        skeletonData.animations.push(new Animation(name, timelines, duration));
    }
}
class LinkedMesh {
    parent;
    skin;
    slotIndex;
    mesh;
    inheritTimeline;
    constructor(mesh, skin, slotIndex, parent, inheritDeform) {
        this.mesh = mesh;
        this.skin = skin;
        this.slotIndex = slotIndex;
        this.parent = parent;
        this.inheritTimeline = inheritDeform;
    }
}
function readTimeline1(keys, timeline, defaultValue, scale) {
    let keyMap = keys[0];
    let time = getValue(keyMap, "time", 0);
    let value = getValue(keyMap, "value", defaultValue) * scale;
    let bezier = 0;
    for (let frame = 0;; frame++) {
        timeline.setFrame(frame, time, value);
        let nextMap = keys[frame + 1];
        if (!nextMap) {
            timeline.shrink(bezier);
            return timeline;
        }
        let time2 = getValue(nextMap, "time", 0);
        let value2 = getValue(nextMap, "value", defaultValue) * scale;
        if (keyMap.curve)
            bezier = readCurve(keyMap.curve, timeline, bezier, frame, 0, time, time2, value, value2, scale);
        time = time2;
        value = value2;
        keyMap = nextMap;
    }
}
function readTimeline2(keys, timeline, name1, name2, defaultValue, scale) {
    let keyMap = keys[0];
    let time = getValue(keyMap, "time", 0);
    let value1 = getValue(keyMap, name1, defaultValue) * scale;
    let value2 = getValue(keyMap, name2, defaultValue) * scale;
    let bezier = 0;
    for (let frame = 0;; frame++) {
        timeline.setFrame(frame, time, value1, value2);
        let nextMap = keys[frame + 1];
        if (!nextMap) {
            timeline.shrink(bezier);
            return timeline;
        }
        let time2 = getValue(nextMap, "time", 0);
        let nvalue1 = getValue(nextMap, name1, defaultValue) * scale;
        let nvalue2 = getValue(nextMap, name2, defaultValue) * scale;
        let curve = keyMap.curve;
        if (curve) {
            bezier = readCurve(curve, timeline, bezier, frame, 0, time, time2, value1, nvalue1, scale);
            bezier = readCurve(curve, timeline, bezier, frame, 1, time, time2, value2, nvalue2, scale);
        }
        time = time2;
        value1 = nvalue1;
        value2 = nvalue2;
        keyMap = nextMap;
    }
}
function readCurve(curve, timeline, bezier, frame, value, time1, time2, value1, value2, scale) {
    if (curve == "stepped") {
        timeline.setStepped(frame);
        return bezier;
    }
    let i = value << 2;
    let cx1 = curve[i];
    let cy1 = curve[i + 1] * scale;
    let cx2 = curve[i + 2];
    let cy2 = curve[i + 3] * scale;
    timeline.setBezier(bezier, frame, value, time1, value1, cx1, cy1, cx2, cy2, time2, value2);
    return bezier + 1;
}
function getValue(map, property, defaultValue) {
    return map[property] !== undefined ? map[property] : defaultValue;
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiU2tlbGV0b25Kc29uLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsiLi4vc3JjL1NrZWxldG9uSnNvbi50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiQUFBQTs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OytFQTJCK0U7QUFFL0UsT0FBTyxFQUFFLFNBQVMsRUFBWSxlQUFlLEVBQUUsa0JBQWtCLEVBQUUsWUFBWSxFQUFFLFdBQVcsRUFBRSxhQUFhLEVBQUUsYUFBYSxFQUFFLFlBQVksRUFBRSxjQUFjLEVBQUUsaUJBQWlCLEVBQUUsa0JBQWtCLEVBQUUsa0JBQWtCLEVBQUUsYUFBYSxFQUFFLGNBQWMsRUFBRSxjQUFjLEVBQUUsYUFBYSxFQUFFLGNBQWMsRUFBRSxjQUFjLEVBQUUsb0JBQW9CLEVBQUUsMkJBQTJCLEVBQUUsOEJBQThCLEVBQUUsNkJBQTZCLEVBQUUseUJBQXlCLEVBQUUsY0FBYyxFQUFFLGlCQUFpQixFQUFFLGFBQWEsRUFBaUQsOEJBQThCLEVBQUUsZ0NBQWdDLEVBQUUsaUNBQWlDLEVBQUUsZ0NBQWdDLEVBQUUsNkJBQTZCLEVBQUUsNkJBQTZCLEVBQUUsZ0NBQWdDLEVBQUUsNEJBQTRCLEVBQUUsTUFBTSxnQkFBZ0IsQ0FBQztBQUk3ekIsT0FBTyxFQUFFLFFBQVEsRUFBRSxPQUFPLEVBQUUsTUFBTSxlQUFlLENBQUM7QUFDbEQsT0FBTyxFQUFFLFNBQVMsRUFBRSxNQUFNLGdCQUFnQixDQUFDO0FBQzNDLE9BQU8sRUFBRSxLQUFLLEVBQUUsTUFBTSxZQUFZLENBQUM7QUFDbkMsT0FBTyxFQUFFLGdCQUFnQixFQUFFLE1BQU0sdUJBQXVCLENBQUM7QUFDekQsT0FBTyxFQUFFLGtCQUFrQixFQUFFLFlBQVksRUFBRSxXQUFXLEVBQUUsVUFBVSxFQUFFLE1BQU0seUJBQXlCLENBQUM7QUFDcEcsT0FBTyxFQUFFLFlBQVksRUFBRSxNQUFNLG1CQUFtQixDQUFDO0FBQ2pELE9BQU8sRUFBRSxJQUFJLEVBQUUsTUFBTSxXQUFXLENB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R0FBRyxRQUFRLENBQUMsYUFBYSxFQUFFLFNBQVMsRUFBRSxDQUFDLENBQUMsQ0FBQztnQkFDckQsSUFBSSxDQUFDLFFBQVEsR0FBRyxRQUFRLENBQUMsYUFBYSxFQUFFLFVBQVUsRUFBRSxHQUFHLENBQUMsQ0FBQztnQkFDekQsSUFBSSxDQUFDLE9BQU8sR0FBRyxRQUFRLENBQUMsYUFBYSxFQUFFLFNBQVMsRUFBRSxDQUFDLENBQUMsQ0FBQztnQkFDckQsSUFBSSxDQUFDLFdBQVcsR0FBRyxDQUFDLEdBQUcsUUFBUSxDQUFDLGFBQWEsRUFBRSxNQUFNLEVBQUUsQ0FBQyxDQUFDLENBQUM7Z0JBQzFELElBQUksQ0FBQyxJQUFJLEdBQUcsUUFBUSxDQUFDLGFBQWEsRUFBRSxNQUFNLEVBQUUsQ0FBQyxDQUFDLENBQUM7Z0JBQy9DLElBQUksQ0FBQyxPQUFPLEdBQUcsUUFBUSxDQUFDLGFBQWEsRUFBRSxTQUFTLEVBQUUsQ0FBQyxDQUFDLENBQUM7Z0JBQ3JELElBQUksQ0FBQyxHQUFHLEdBQUcsUUFBUSxDQUFDLGFBQWEsRUFBRSxLQUFLLEVBQUUsQ0FBQyxDQUFDLENBQUM7Z0JBQzdDLElBQUksQ0FBQyxhQUFhLEdBQUcsUUFBUSxDQUFDLGFBQWEsRUFBRSxlQUFlLEVBQUUsS0FBSyxDQUFDLENBQUM7Z0JBQ3JFLElBQUksQ0FBQyxjQUFjLEdBQUcsUUFBUSxDQUFDLGFBQWEsRUFBRSxnQkFBZ0IsRUFBRSxLQUFLLENBQUMsQ0FBQztnQkFDdkUsSUFBSSxDQUFDLGFBQWEsR0FBRyxRQUFRLENBQUMsYUFBYSxFQUFFLGVBQWUsRUFBRSxLQUFLLENBQUMsQ0FBQztnQkFDckUsSUFBSSxDQUFDLFVBQVUsR0FBRyxRQUFRLENBQUMsYUFBYSxFQUFFLFlBQVksRUFBRSxLQUFLLENBQUMsQ0FBQztnQkFDL0QsSUFBSSxDQUFDLFVBQVUsR0FBRyxRQUFRLENBQUMsYUFBYSxFQUFFLFlBQVksRUFBRSxLQUFLLENBQUMsQ0FBQztnQkFDL0QsSUFBSSxDQUFDLGFBQWEsR0FBRyxRQUFRLENBQUMsYUFBYSxFQUFF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Q0FBQyxDQUFDLEVBQUUsUUFBUSxDQUFDLENBQUMsRUFBRSxDQUFDLENBQUMsQ0FBQztnQ0FDM0YsTUFBTSxHQUFHLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxLQUFLLEVBQUUsS0FBSyxDQUFDLENBQUMsRUFBRSxRQUFRLENBQUMsQ0FBQyxFQUFFLENBQUMsQ0FBQyxDQUFDO2dDQUMzRixNQUFNLEdBQUcsU0FBUyxDQUFDLEtBQUssRUFBRSxRQUFRLEVBQUUsTUFBTSxFQUFFLEtBQUssRUFBRSxDQUFDLEVBQUUsSUFBSSxFQUFFLEtBQUssRUFBRSxLQUFLLENBQUMsQ0FBQyxFQUFFLFFBQVEsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxDQUFDLENBQUM7Z0NBQzNGLE1BQU0sR0FBRyxTQUFTLENBQUMsS0FBSyxFQUFFLFFBQVEsRUFBRSxNQUFNLEVBQUUsS0FBSyxFQUFFLENBQUMsRUFBRSxJQUFJLEVBQUUsS0FBSyxFQUFFLE1BQU0sQ0FBQyxDQUFDLEVBQUUsU0FBUyxDQUFDLENBQUMsRUFBRSxDQUFDLENBQUMsQ0FBQztnQ0FDN0YsTUFBTSxHQUFHLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxLQUFLLEVBQUUsTUFBTSxDQUFDLENBQUMsRUFBRSxTQUFTLENBQUMsQ0FBQyxFQUFFLENBQUMsQ0FBQyxDQUFDO2dDQUM3RixNQUFNLEdBQUcsU0FBUyxDQUFDLEtBQUssRUFBRSxRQUFRLEVBQUUsTUFBTSxFQUFFLEtBQUssRUFBRSxDQUFDLEVBQUUsSUFBSSxFQUFFLEtBQUssRUFBRSxNQUFNLENBQUMsQ0FBQyxFQUFFLFNBQVMsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxDQUFDLENBQUM7NEJBQzlGLENBQUM7NEJBQ0QsSUFBSSxHQUFHLEtBQUssQ0FBQzs0QkFDYixLQUFLLEdBQUcsUUFBUSxDQUFDOzRCQUNqQixNQUFNLEdBQUcsU0FBUyxDQUFD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d0JBQzdELFNBQVMsQ0FBQyxJQUFJLENBQUMsYUFBYSxDQUFDLFdBQVcsRUFBRSxRQUFRLEVBQUUsQ0FBQyxFQUFFLENBQUMsQ0FBQyxDQUFDLENBQUM7b0JBQzVELENBQUM7eUJBQU0sSUFBSSxZQUFZLEtBQUssUUFBUSxFQUFFLENBQUM7d0JBQ3RDLElBQUksUUFBUSxHQUFHLElBQUksY0FBYyxDQUFDLE1BQU0sRUFBRSxNQUFNLEVBQUUsU0FBUyxDQUFDLENBQUM7d0JBQzdELFNBQVMsQ0FBQyxJQUFJLENBQUMsYUFBYSxDQUFDLFdBQVcsRUFBRSxRQUFRLEVBQUUsQ0FBQyxFQUFFLENBQUMsQ0FBQyxDQUFDLENBQUM7b0JBQzVELENBQUM7eUJBQU0sSUFBSSxZQUFZLEtBQUssT0FBTyxFQUFFLENBQUM7d0JBQ3JDLElBQUksUUFBUSxHQUFHLElBQUksYUFBYSxDQUFDLE1BQU0sRUFBRSxNQUFNLElBQUksQ0FBQyxFQUFFLFNBQVMsQ0FBQyxDQUFDO3dCQUNqRSxTQUFTLENBQUMsSUFBSSxDQUFDLGFBQWEsQ0FBQyxXQUFXLEVBQUUsUUFBUSxFQUFFLEdBQUcsRUFBRSxHQUFHLEVBQUUsQ0FBQyxFQUFFLENBQUMsQ0FBQyxDQUFDLENBQUM7b0JBQ3RFLENBQUM7eUJBQU0sSUFBSSxZQUFZLEtBQUssUUFBUSxFQUFFLENBQUM7d0JBQ3RDLElBQUksUUFBUSxHQUFHLElBQUksY0FBYyxDQUFDLE1BQU0sRUFBRSxNQUFNLEVBQUUsU0FBUyxDQUFDLENBQUM7d0JBQzdELFNBQVMsQ0FBQyxJQUFJLENBQUMsYUFBYSxDQUFDLFdBQVcsRUFBRSxRQUFRLEVBQUUsQ0FBQyxFQUFFLENBQUMsQ0FBQyxDQUFDLENBQUM7b0JBQzVELENBQUM7eUJBQU0sSUFBSSxZQUFZLEtBQUssUUFBUSxFQUFFLENBQUM7d0JBQ3RDLElBQUksUUFBUSxHQUFHLElBQUksY0FBYyxDQUFDLE1BQU0sRUFBRSxNQUFNLEVBQUUsU0FBUyxDQUFDLENBQUM7d0JBQzdELFNBQVMsQ0FBQyxJQUFJLENBQUMsYUFBYSxDQUFDLFdBQVcs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RUFBRSxLQUFLLEVBQUUsU0FBUyxFQUFFLFVBQVUsRUFBRSxDQUFDLENBQUMsQ0FBQzt3QkFDN0YsTUFBTSxHQUFHLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxLQUFLLEVBQUUsSUFBSSxFQUFFLEtBQUssRUFBRSxDQUFDLENBQUMsQ0FBQzt3QkFDbkYsTUFBTSxHQUFHLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxLQUFLLEVBQUUsSUFBSSxFQUFFLEtBQUssRUFBRSxDQUFDLENBQUMsQ0FBQzt3QkFDbkYsTUFBTSxHQUFHLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxLQUFLLEVBQUUsU0FBUyxFQUFFLFVBQVUsRUFBRSxDQUFDLENBQUMsQ0FBQzt3QkFDN0YsTUFBTSxHQUFHLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxLQUFLLEVBQUUsU0FBUyxFQUFFLFVBQVUsRUFBRSxDQUFDLENBQUMsQ0FBQzt3QkFDN0YsTUFBTSxHQUFHLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxLQUFLLEVBQUUsU0FBUyxFQUFFLFVBQVUsRUFBRSxDQUFDLENBQUMsQ0FBQztvQkFDOUYsQ0FBQztvQkFFRCxJQUFJLEdBQUcsS0FBSyxDQUFDO29CQUNiLFNBQVMsR0FBRyxVQUFVLENBQUM7b0JBQ3ZCLElBQUksR0FBRyxLQUFLLENBQUM7b0JBQ2IsSUFBSSxHQUFHLEtBQUssQ0FBQztvQkFDYixTQUFTLEdBQUcsVUFBVSxDQUFDO29CQUN2QixTQUFTLEdBQUcsVUFBVSxDQUFDO29CQUN2QixTQUFTLEdBQUcsVUFB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QUMsQ0FBQztJQUNuQixJQUFJLEdBQUcsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDLENBQUM7SUFDbkIsSUFBSSxHQUFHLEdBQUcsS0FBSyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxLQUFLLENBQUM7SUFDL0IsSUFBSSxHQUFHLEdBQUcsS0FBSyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsQ0FBQztJQUN2QixJQUFJLEdBQUcsR0FBRyxLQUFLLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLEtBQUssQ0FBQztJQUMvQixRQUFRLENBQUMsU0FBUyxDQUFDLE1BQU0sRUFBRSxLQUFLLEVBQUUsS0FBSyxFQUFFLEtBQUssRUFBRSxNQUFNLEVBQUUsR0FBRyxFQUFFLEdBQUcsRUFBRSxHQUFHLEVBQUUsR0FBRyxFQUFFLEtBQUssRUFBRSxNQUFNLENBQUMsQ0FBQztJQUMzRixPQUFPLE1BQU0sR0FBRyxDQUFDLENBQUM7QUFDbkIsQ0FBQztBQUVELFNBQVMsUUFBUSxDQUFFLEdBQVEsRUFBRSxRQUFnQixFQUFFLFlBQWlCO0lBQy9ELE9BQU8sR0FBRyxDQUFDLFFBQVEsQ0FBQyxLQUFLLFNBQVMsQ0FBQyxDQUFDLENBQUMsR0FBRyxDQUFDLFFBQVEsQ0FBQyxDQUFDLENBQUMsQ0FBQyxZQUFZLENBQUM7QUFDbkUsQ0FBQyIsInNvdXJjZXNDb250ZW50IjpbIi8qKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKipcbiAqIFNwaW5lIFJ1bnRpbWVzIExpY2Vuc2UgQWdyZWVtZW50XG4gKiBMYXN0IHVwZGF0ZWQgQXByaWwgNSwgMjAyNS4gUmVwbGFjZXMgYWxsIHByaW9yIHZlcnNpb25zLlxuICpcbiAqIENvcHlyaWdodCAoYykgMjAxMy0yMDI1LCBFc290ZXJpYyBTb2Z0d2FyZSBMTENcbiAqXG4gKiBJbnRlZ3JhdGlvbiBvZiB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZSBvciBvdGhlcndpc2UgY3JlYXRpbmdcbiAqIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGlzIHBlcm1pdHRlZCB1bmRlciB0aGUgdGVybXMgYW5kXG4gKiBjb25kaXRpb25zIG9mIFNlY3Rpb24gMiBvZiB0aGUgU3BpbmUgRWRpdG9yIExpY2Vuc2UgQWdyZWVtZW50OlxuICogaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLWVkaXRvci1saWNlbnNlXG4gKlxuICogT3RoZXJ3aXNlLCBpdCBpcyBwZXJtaXR0ZWQgdG8gaW50ZWdyYXRlIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlXG4gKiBvciBvdGhlcndpc2UgY3JlYXRlIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIChjb2xsZWN0aXZlbHksXG4gKiBcIlByb2R1Y3RzXCIpLCBwcm92aWRlZCB0aGF0IGVhY2ggdXNlciBvZiB0aGUgUHJvZHVjdHMgbXVzdCBvYnRhaW4gdGhlaXIgb3duXG4gKiBTcGluZSBFZGl0b3IgbGljZW5zZSBhbmQgcmVkaXN0cmlidXRpb24gb2YgdGhlIFByb2R1Y3RzIGluIGFueSBmb3JtIG11c3RcbiAqIGluY2x1ZGUgdGhpcyBsaWNlbnNlIGFuZCBjb3B5cmlnaHQgbm90aWNlLlxuICpcbiAqIFRIRSBTUElORSBSVU5USU1FUyBBUkUgUFJPVklERUQgQlkgRVNPVEVSSUMgU09GVFdBUkUgTExDIFwiQVMgSVNcIiBBTkQgQU5ZXG4gKiBFWFBSRVNTIE9SIElNUExJRUQgV0FSUkFOVElFUywgSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFRIRSBJTVBMSUVEXG4gKiBXQVJSQU5USUVTIE9GIE1FUkNIQU5UQUJJTElUWSBBTkQgRklUTkVTUyBGT1IgQSBQQVJUSUNVTEFSIFBVUlBPU0UgQVJFXG4gKiBESVNDTEFJTUVELiBJTiBOTyBFVkVOVCBTSEFMTCBFU09URVJJQyBTT0ZUV0FSRSBMTEMgQkUgTElBQkxFIEZPUiBBTllcbiAqIERJUkVDVCwgSU5ESVJFQ1QsIElOQ0lERU5UQUwsIFNQRUNJQUwsIEVYRU1QTEFSWSwgT1IgQ09OU0VRVUVOVElBTCBEQU1BR0VTXG4gKiAoSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFBST0NVUkVNRU5UIE9GIFNVQlNUSVRVVEUgR09PRFMgT1IgU0VSVklDRVMsXG4gKiBCVVNJTkVTUyBJTlRFUlJVUFRJT04sIE9SIExPU1MgT0YgVVNFLCBEQVRBLCBPUiBQUk9GSVRTKSBIT1dFVkVSIENBVVNFRCBBTkRcbiAqIE9OIEFOWSBUSEVPUlkgT0YgTElBQklMSVRZLCBXSEVUSEVSIElOIENPTlRSQUNULCBTVFJJQ1QgTElBQklMSVRZLCBPUiBUT1JUXG4gKiAoSU5DTFVESU5HIE5FR0xJR0VOQ0UgT1IgT1RIRVJXSVNFKSBBUklTSU5HIElOIEFOWSBXQVkgT1VUIE9GIFRIRSBVU0UgT0ZcbiAqIFRIRSBTUElORSBSVU5USU1FUywgRVZFTiBJRiBBRFZJU0VEIE9GIFRIRSBQT1NTSUJJTElUWSBPRiBTVUNIIERBTUFHRS5cbiAqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKi9cblxuaW1wb3J0IHsgQW5pbWF0aW9uLCBUaW1lbGluZSwgSW5oZXJpdFRpbWVsaW5lLCBBdHRhY2htZW50VGltZWxpbmUsIFJHQkFUaW1lbGluZSwgUkdCVGltZWxpbmUsIEFscGhhVGltZWxpbmUsIFJHQkEyVGltZWxpbmUsIFJHQjJUaW1lbGluZSwgUm90YXRlVGltZWxpbmUsIFRyYW5zbGF0ZVRpbWVsaW5lLCBUcmFuc2xhdGVYVGltZWxpbmUsIFRyYW5zbGF0ZVlUaW1lbGluZSwgU2NhbGVUaW1lbGluZSwgU2NhbGVYVGltZWxpbmUsIFNjYWxlWVRpbWVsaW5lLCBTaGVhclRpbWVsaW5lLCBTaGVhclhUaW1lbGluZSwgU2hlYXJZVGltZWxpbmUsIElrQ29uc3RyYWludFRpbWVsaW5lLCBUcmFuc2Zvcm1Db25zdHJhaW50VGltZWxpbmUsIFBhdGhDb25zdHJhaW50UG9zaXRpb25UaW1lbGluZSwgUGF0aENvbnN0cmFpbnRTcGFjaW5nVGltZWxpbmUsIFBhdGhDb25zdHJhaW50TWl4VGltZWxpbmUsIERlZm9ybVRpbWVsaW5lLCBEcmF3T3JkZXJUaW1lbGluZSwgRXZlbnRUaW1lbGluZSwgQ3VydmVUaW1lbGluZTEsIEN1cnZlVGltZWxpbmUyLCBDdXJ2ZVRpbWVsaW5lLCBQaHlzaWNzQ29uc3RyYWludFJlc2V0VGltZWxpbmUsIFBoeXNpY3NDb25zdHJhaW50SW5lcnRpYVRpbWVsaW5lLCBQaHlzaWNzQ29uc3RyYWludFN0cmVuZ3RoVGltZWxpbmUsIFBoeXNpY3NDb25zdHJhaW50RGFtcGluZ1RpbWVsaW5lLCBQaHlzaWNzQ29uc3RyYWludE1hc3NUaW1lbGluZSwgUGh5c2ljc0NvbnN0cmFpbnRXaW5kVGltZWxpbmUsIFBoeXNpY3NDb25zdHJhaW50R3Jhdml0eVRpbWVsaW5lLCBQaHlzaWNzQ29uc3RyYWludE1peFRpbWVsaW5lIH0gZnJvbSBcIi4vQW5pbWF0aW9uLmpzXCI7XG5pbXBvcnQgeyBWZXJ0ZXhBdHRhY2htZW50LCBBdHRhY2htZW50IH0gZnJvbSBcIi4vYXR0YWNobWVudHMvQXR0YWNobWVudC5qc1wiO1xuaW1wb3J0IHsgQXR0YWNobWVudExvYWRlciB9IGZyb20gXCIuL2F0dGFjaG1lbnRzL0F0dGFjaG1lbnRMb2FkZXIuanNcIjtcbmltcG9ydCB7IE1lc2hBdHRhY2htZW50IH0gZnJvbSBcIi4vYXR0YWNobWVudHMvTWVzaEF0dGFjaG1lbnQuanNcIjtcbmltcG9ydCB7IEJvbmVEYXRhLCBJbmhlcml0IH0gZnJvbSBcIi4vQm9uZURhdGEuanNcIjtcbmltcG9ydCB7IEV2ZW50RGF0YSB9IGZyb20gXCIuL0V2ZW50RGF0YS5qc1wiO1xuaW1wb3J0IHsgRXZlbnQgfSBmcm9tIFwiLi9FdmVudC5qc1wiO1xuaW1wb3J0IHsgSWtDb25zdHJhaW50RGF0YSB9IGZyb20gXCIuL0lrQ29uc3RyYWludERhdGEuanNcIjtcbmltcG9ydCB7IFBhdGhDb25zdHJhaW50RGF0YSwgUG9zaXRpb25Nb2RlLCBTcGFjaW5nTW9kZSwgUm90YXRlTW9kZSB9IGZyb20gXCIuL1BhdGhDb25zdHJhaW50RGF0YS5qc1wiO1xuaW1wb3J0IHsgU2tlbGV0b25EYXRhIH0gZnJvbSBcIi4vU2tlbGV0b25EYXRhLmpzXCI7XG5pbXBvcnQgeyBTa2luIH0gZnJvbSBcIi4vU2tpbi5qc1wiO1xuaW1wb3J0IHsgU2xvdERhdGEsIEJsZW5kTW9kZSB9IGZyb20gXCIuL1Nsb3REYXRhLmpzXCI7XG5pbXBvcnQgeyBUcmFuc2Zvcm1Db25zdHJhaW50RGF0YSB9IGZyb20gXCIuL1RyYW5zZm9ybUNvbnN0cmFpbnREYXRhLmpzXCI7XG5pbXBvcnQgeyBVdGlscywgQ29sb3IsIE51bWJlckFycmF5TGlrZSB9IGZyb20gXCIuL1V0aWxzLmpzXCI7XG5pbXBvcnQgeyBTZXF1ZW5jZSwgU2VxdWVuY2VNb2RlIH0gZnJvbSBcIi4vYXR0YWNobWVudHMvU2VxdWVuY2UuanNcIjtcbmltcG9ydCB7IFNlcXVlbmNlVGltZWxpbmUgfSBmcm9tIFwiLi9BbmltYXRpb24uanNcIjtcbmltcG9ydCB7IEhhc1RleHR1cmVSZWdpb24gfSBmcm9tIFwiLi9hdHRhY2htZW50cy9IYXNUZXh0dXJlUmVnaW9uLmpzXCI7XG5pbXBvcnQgeyBQaHlzaWNzQ29uc3RyYWludERhdGEgfSBmcm9tIFwiLi9QaHlzaWNzQ29uc3RyYWludERhdGEuanNcIjtcblxuLyoqIExvYWRzIHNrZWxldG9uIGRhdGEgaW4gdGhlIFNwaW5lIEpTT04gZm9ybWF0LlxuICpcbiAqIFNlZSBbU3BpbmUgSlNPTiBmb3JtYXRdKGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1qc29uLWZvcm1hdCkgYW5kXG4gKiBbSlNPTiBhbmQgYmluYXJ5IGRhdGFdKGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1sb2FkaW5nLXNrZWxldG9uLWRhdGEjSlNPTi1hbmQtYmluYXJ5LWRhdGEpIGluIHRoZSBTcGluZVxuICogUnVudGltZXMgR3VpZGUuICovXG5leHBvcnQgY2xhc3MgU2tlbGV0b25Kc29uIHtcblx0YXR0YWNobWVudExvYWRlcjogQXR0YWNobWVudExvYWRlcjtcblxuXHQvKiogU2NhbGVzIGJvbmUgcG9zaXRpb25zLCBpbWFnZSBzaXplcywgYW5kIHRyYW5zbGF0aW9ucyBhcyB0aGV5IGFyZSBsb2FkZWQuIFRoaXMgYWxsb3dzIGRpZmZlcmVudCBzaXplIGltYWdlcyB0byBiZSB1c2VkIGF0XG5cdCAqIHJ1bnRpbWUgdGhhbiB3ZXJlIHVzZWQgaW4gU3BpbmUuXG5cdCAqXG5cdCAqIFNlZSBbU2NhbGluZ10oaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLWxvYWRpbmctc2tlbGV0b24tZGF0YSNTY2FsaW5nKSBpbiB0aGUgU3BpbmUgUnVudGltZXMgR3VpZGUuICovXG5cdHNjYWxlID0gMTtcblx0cHJpdmF0ZSBsaW5rZWRNZXNoZXMgPSBuZXcgQXJyYXk8TGlua2VkTWVzaD4oKTtcblxuXHRjb25zdHJ1Y3RvciAoYXR0YWNobWVudExvYWRlcjogQXR0YWNobWVudExvYWRlcikge1xuXHRcdHRoaXMuYXR0YWNobWVudExvYWRlciA9IGF0dGFjaG1lbnRMb2FkZXI7XG5cdH1cblxuXHRyZWFkU2tlbGV0b25EYXRhIChqc29uOiBzdHJpbmcgfCBhbnkpOiBTa2VsZXRvbkRhdGEge1xuXHRcdGxldCBzY2FsZSA9IHRoaXMuc2NhbGU7XG5cdFx0bGV0IHNrZWxldG9uRGF0YSA9IG5ldyBTa2VsZXRvbkRhdGEoKTtcblx0XHRsZXQgcm9vdCA9IHR5cGVvZiAoanNvbikgPT09IFwic3RyaW5nXCIgPyBKU09OLnBhcnNlKGpzb24pIDoganNvbjtcblxuXHRcdC8vIFNrZWxldG9uXG5cdFx0bGV0IHNrZWxldG9uTWFwID0gcm9vdC5za2VsZXRvbjtcblx0XHRpZiAoc2tlbGV0b25NYXApIHtcblx0XHRcdHNrZWxldG9uRGF0YS5oYXNoID0gc2tlbGV0b25NYXAuaGFzaDtcblx0XHRcdHNrZWxldG9uRGF0YS52ZXJzaW9uID0gc2tlbGV0b25NYXAuc3BpbmU7XG5cdFx0XHRza2VsZXRvbkRhdGEueCA9IHNrZWxldG9uTWFwLng7XG5cdFx0XHRza2VsZXRvbkRhdGEueSA9IHNrZWxldG9uTWFwLnk7XG5cdFx0XHRza2VsZXRvbkRhdGEud2lkdGggPSBza2VsZXRvbk1hcC53aWR0aDtcblx0XHRcdHNrZWxldG9uRGF0YS5oZWlnaHQgPSBza2VsZXRvbk1hcC5oZWlnaHQ7XG5cdFx0XHRza2VsZXRvbkRhdGEucmVmZXJlbmNlU2NhbGUgPSBnZXRWYWx1ZShza2VsZXRvbk1hcCwgXCJyZWZlcmVuY2VTY2FsZVwiLCAxMDApICogc2NhbGU7XG5cdFx0XHRza2VsZXRvbkRhdGEuZnBzID0gc2tlbGV0b25NYXAuZnBzO1xuXHRcdFx0c2tlbGV0b25EYXRhLmltYWdlc1BhdGggPSBza2VsZXRvbk1hcC5pbWFnZXMgPz8gbnVsbDtcblx0XHRcdHNrZWxldG9uRGF0YS5hdWRpb1BhdGggPSBza2VsZXRvbk1hcC5hdWRpbyA/PyBudWxsO1xuXHRcdH1cblxuXHRcdC8vIEJvbmVzXG5cdFx0aWYgKHJvb3QuYm9uZXMpIHtcblx0XHRcdGZvciAobGV0IGkgPSAwOyBpIDwgcm9vdC5ib25lcy5sZW5ndGg7IGkrKykge1xuXHRcdFx0XHRsZXQgYm9uZU1hcCA9IHJvb3QuYm9uZXNbaV07XG5cblx0XHRcdFx0bGV0IHBhcmVudDogQm9uZURhdGEgfCBudWxsID0gbnVsbDtcblx0XHRcdFx0bGV0IHBhcmVudE5hbWU6IHN0cmluZyA9IGdldFZhbHVlKGJvbmVNYXAsIFwicGFyZW50XCIsIG51bGwpO1xuXHRcdFx0XHRpZiAocGFyZW50TmFtZSkgcGFyZW50ID0gc2tlbGV0b25EYXRhLmZpbmRCb25lKHBhcmVudE5hbWUpO1xuXHRcdFx0XHRsZXQgZGF0YSA9IG5ldyBCb25lRGF0YShza2VsZXRvbkRhdGEuYm9uZXMubGVuZ3RoLCBib25lTWFwLm5hbWUsIHBhcmVudCk7XG5cdFx0XHRcdGRhdGEubGVuZ3RoID0gZ2V0VmFsdWUoYm9uZU1hcCwgXCJsZW5ndGhcIiwgMCkgKiBzY2FsZTtcblx0XHRcdFx0ZGF0YS54ID0gZ2V0VmFsdWUoYm9uZU1hcCwgXCJ4XCIsIDApICogc2NhbGU7XG5cdFx0XHRcdGRhdGEueSA9IGdldFZhbHVlKGJvbmVNYXAsIFwieVwiLCAwKSAqIHNjYWxlO1xuXHRcdFx0XHRkYXRhLnJvdGF0aW9uID0gZ2V0VmFsdWUoYm9uZU1hcCwgXCJyb3RhdGlvblwiLCAwKTtcblx0XHRcdFx0ZGF0YS5zY2FsZVggPSBnZXRWYWx1ZShib25lTWFwLCBcInNjYWxlWFwiLCAxKTtcblx0XHRcdFx0ZGF0YS5zY2FsZVkgPSBnZXRWYWx1ZShib25lTWFwLCBcInNjYWxlWVwiLCAxKTtcblx0XHRcdFx0ZGF0YS5zaGVhclggPSBnZXRWYWx1ZShib25lTWFwLCBcInNoZWFyWFwiLCAwKTtcblx0XHRcdFx0ZGF0YS5zaGVhclkgPSBnZXRWYWx1ZShib25lTWFwLCBcInNoZWFyWVwiLCAwKTtcblx0XHRcdFx0ZGF0YS5pbmhlcml0ID0gVXRpbHMuZW51bVZhbHVlKEluaGVyaXQsIGdldFZhbHVlKGJvbmVNYXAsIFwiaW5oZXJpdFwiLCBcIk5vcm1hbFwiKSk7XG5cdFx0XHRcdGRhdGEuc2tpblJlcXVpcmVkID0gZ2V0VmFsdWUoYm9uZU1hcCwgXCJza2luXCIsIGZhbHNlKTtcblxuXHRcdFx0XHRsZXQgY29sb3IgPSBnZXRWYWx1ZShib25lTWFwLCBcImNvbG9yXCIsIG51bGwpO1xuXHRcdFx0XHRpZiAoY29sb3IpIGRhdGEuY29sb3Iuc2V0RnJvbVN0cmluZyhjb2xvcik7XG5cblx0XHRcdFx0c2tlbGV0b25EYXRhLmJvbmVzLnB1c2goZGF0YSk7XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0Ly8gU2xvdHMuXG5cdFx0aWYgKHJvb3Quc2xvdHMpIHtcblx0XHRcdGZvciAobGV0IGkgPSAwOyBpIDwgcm9vdC5zbG90cy5sZW5ndGg7IGkrKykge1xuXHRcdFx0XHRsZXQgc2xvdE1hcCA9IHJvb3Quc2xvdHNbaV07XG5cdFx0XHRcdGxldCBzbG90TmFtZSA9IHNsb3RNYXAubmFtZTtcblxuXHRcdFx0XHRsZXQgYm9uZURhdGEgPSBza2VsZXRvbkRhdGEuZmluZEJvbmUoc2xvdE1hcC5ib25lKTtcblx0XHRcdFx0aWYgKCFib25lRGF0YSkgdGhyb3cgbmV3IEVycm9yKGBDb3VsZG4ndCBmaW5kIGJvbmUgJHtzbG90TWFwLmJvbmV9IGZvciBzbG90ICR7c2xvdE5hbWV9YCk7XG5cdFx0XHRcdGxldCBkYXRhID0gbmV3IFNsb3REYXRhKHNrZWxldG9uRGF0YS5zbG90cy5sZW5ndGgsIHNsb3ROYW1lLCBib25lRGF0YSk7XG5cblx0XHRcdFx0bGV0IGNvbG9yOiBzdHJpbmcgPSBnZXRWYWx1ZShzbG90TWFwLCBcImNvbG9yXCIsIG51bGwpO1xuXHRcdFx0XHRpZiAoY29sb3IpIGRhdGEuY29sb3Iuc2V0RnJvbVN0cmluZyhjb2xvcik7XG5cblx0XHRcdFx0bGV0IGRhcms6IHN0cmluZyA9IGdldFZhbHVlKHNsb3RNYXAsIFwiZGFya1wiLCBudWxsKTtcblx0XHRcdFx0aWYgKGRhcmspIGRhdGEuZGFya0NvbG9yID0gQ29sb3IuZnJvbVN0cmluZyhkYXJrKTtcblxuXHRcdFx0XHRkYXRhLmF0dGFjaG1lbnROYW1lID0gZ2V0VmFsdWUoc2xvdE1hcCwgXCJhdHRhY2htZW50XCIsIG51bGwpO1xuXHRcdFx0XHRkYXRhLmJsZW5kTW9kZSA9IFV0aWxzLmVudW1WYWx1ZShCbGVuZE1vZGUsIGdldFZhbHVlKHNsb3RNYXAsIFwiYmxlbmRcIiwgXCJub3JtYWxcIikpO1xuXHRcdFx0XHRkYXRhLnZpc2libGUgPSBnZXRWYWx1ZShzbG90TWFwLCBcInZpc2libGVcIiwgdHJ1ZSk7XG5cdFx0XHRcdHNrZWxldG9uRGF0YS5zbG90cy5wdXNoKGRhdGEpO1xuXHRcdFx0fVxuXHRcdH1cblxuXHRcdC8vIElLIGNvbnN0cmFpbnRzXG5cdFx0aWYgKHJvb3QuaWspIHtcblx0XHRcdGZvciAobGV0IGkgPSAwOyBpIDwgcm9vdC5pay5sZW5ndGg7IGkrKykge1xuXHRcdFx0XHRsZXQgY29uc3RyYWludE1hcCA9IHJvb3QuaWtbaV07XG5cdFx0XHRcdGxldCBkYXRhID0gbmV3IElrQ29uc3RyYWludERhdGEoY29uc3RyYWludE1hcC5uYW1lKTtcblx0XHRcdFx0ZGF0YS5vcmRlciA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwib3JkZXJcIiwgMCk7XG5cdFx0XHRcdGRhdGEuc2tpblJlcXVpcmVkID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJza2luXCIsIGZhbHNlKTtcblxuXHRcdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgY29uc3RyYWludE1hcC5ib25lcy5sZW5ndGg7IGlpKyspIHtcblx0XHRcdFx0XHRsZXQgYm9uZSA9IHNrZWxldG9uRGF0YS5maW5kQm9uZShjb25zdHJhaW50TWFwLmJvbmVzW2lpXSk7XG5cdFx0XHRcdFx0aWYgKCFib25lKSB0aHJvdyBuZXcgRXJyb3IoYENvdWxkbid0IGZpbmQgYm9uZSAke2NvbnN0cmFpbnRNYXAuYm9uZXNbaWldfSBmb3IgSUsgY29uc3RyYWludCAke2NvbnN0cmFpbnRNYXAubmFtZX0uYCk7XG5cdFx0XHRcdFx0ZGF0YS5ib25lcy5wdXNoKGJvbmUpO1xuXHRcdFx0XHR9XG5cblx0XHRcdFx0bGV0IHRhcmdldCA9IHNrZWxldG9uRGF0YS5maW5kQm9uZShjb25zdHJhaW50TWFwLnRhcmdldCk7O1xuXHRcdFx0XHRpZiAoIXRhcmdldCkgdGhyb3cgbmV3IEVycm9yKGBDb3VsZG4ndCBmaW5kIHRhcmdldCBib25lICR7Y29uc3RyYWludE1hcC50YXJnZXR9IGZvciBJSyBjb25zdHJhaW50ICR7Y29uc3RyYWludE1hcC5uYW1lfS5gKTtcblx0XHRcdFx0ZGF0YS50YXJnZXQgPSB0YXJnZXQ7XG5cblx0XHRcdFx0ZGF0YS5taXggPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcIm1peFwiLCAxKTtcblx0XHRcdFx0ZGF0YS5zb2Z0bmVzcyA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwic29mdG5lc3NcIiwgMCkgKiBzY2FsZTtcblx0XHRcdFx0ZGF0YS5iZW5kRGlyZWN0aW9uID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJiZW5kUG9zaXRpdmVcIiwgdHJ1ZSkgPyAxIDogLTE7XG5cdFx0XHRcdGRhdGEuY29tcHJlc3MgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcImNvbXByZXNzXCIsIGZhbHNlKTtcblx0XHRcdFx0ZGF0YS5zdHJldGNoID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJzdHJldGNoXCIsIGZhbHNlKTtcblx0XHRcdFx0ZGF0YS51bmlmb3JtID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJ1bmlmb3JtXCIsIGZhbHNlKTtcblxuXHRcdFx0XHRza2VsZXRvbkRhdGEuaWtDb25zdHJhaW50cy5wdXNoKGRhdGEpO1xuXHRcdFx0fVxuXHRcdH1cblxuXHRcdC8vIFRyYW5zZm9ybSBjb25zdHJhaW50cy5cblx0XHRpZiAocm9vdC50cmFuc2Zvcm0pIHtcblx0XHRcdGZvciAobGV0IGkgPSAwOyBpIDwgcm9vdC50cmFuc2Zvcm0ubGVuZ3RoOyBpKyspIHtcblx0XHRcdFx0bGV0IGNvbnN0cmFpbnRNYXAgPSByb290LnRyYW5zZm9ybVtpXTtcblx0XHRcdFx0bGV0IGRhdGEgPSBuZXcgVHJhbnNmb3JtQ29uc3RyYWludERhdGEoY29uc3RyYWludE1hcC5uYW1lKTtcblx0XHRcdFx0ZGF0YS5vcmRlciA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwib3JkZXJcIiwgMCk7XG5cdFx0XHRcdGRhdGEuc2tpblJlcXVpcmVkID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJza2luXCIsIGZhbHNlKTtcblxuXHRcdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgY29uc3RyYWludE1hcC5ib25lcy5sZW5ndGg7IGlpKyspIHtcblx0XHRcdFx0XHRsZXQgYm9uZU5hbWUgPSBjb25zdHJhaW50TWFwLmJvbmVzW2lpXTtcblx0XHRcdFx0XHRsZXQgYm9uZSA9IHNrZWxldG9uRGF0YS5maW5kQm9uZShib25lTmFtZSk7XG5cdFx0XHRcdFx0aWYgKCFib25lKSB0aHJvdyBuZXcgRXJyb3IoYENvdWxkbid0IGZpbmQgYm9uZSAke2JvbmVOYW1lfSBmb3IgdHJhbnNmb3JtIGNvbnN0cmFpbnQgJHtjb25zdHJhaW50TWFwLm5hbWV9LmApO1xuXHRcdFx0XHRcdGRhdGEuYm9uZXMucHVzaChib25lKTtcblx0XHRcdFx0fVxuXG5cdFx0XHRcdGxldCB0YXJnZXROYW1lOiBzdHJpbmcgPSBjb25zdHJhaW50TWFwLnRhcmdldDtcblx0XHRcdFx0bGV0IHRhcmdldCA9IHNrZWxldG9uRGF0YS5maW5kQm9uZSh0YXJnZXROYW1lKTtcblx0XHRcdFx0aWYgKCF0YXJnZXQpIHRocm93IG5ldyBFcnJvcihgQ291bGRuJ3QgZmluZCB0YXJnZXQgYm9uZSAke3RhcmdldE5hbWV9IGZvciB0cmFuc2Zvcm0gY29uc3RyYWludCAke2NvbnN0cmFpbnRNYXAubmFtZX0uYCk7XG5cdFx0XHRcdGRhdGEudGFyZ2V0ID0gdGFyZ2V0O1xuXG5cdFx0XHRcdGRhdGEubG9jYWwgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcImxvY2FsXCIsIGZhbHNlKTtcblx0XHRcdFx0ZGF0YS5yZWxhdGl2ZSA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwicmVsYXRpdmVcIiwgZmFsc2UpO1xuXHRcdFx0XHRkYXRhLm9mZnNldFJvdGF0aW9uID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJyb3RhdGlvblwiLCAwKTtcblx0XHRcdFx0ZGF0YS5vZmZzZXRYID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJ4XCIsIDApICogc2NhbGU7XG5cdFx0XHRcdGRhdGEub2Zmc2V0WSA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwieVwiLCAwKSAqIHNjYWxlO1xuXHRcdFx0XHRkYXRhLm9mZnNldFNjYWxlWCA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwic2NhbGVYXCIsIDApO1xuXHRcdFx0XHRkYXRhLm9mZnNldFNjYWxlWSA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwic2NhbGVZXCIsIDApO1xuXHRcdFx0XHRkYXRhLm9mZnNldFNoZWFyWSA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwic2hlYXJZXCIsIDApO1xuXG5cdFx0XHRcdGRhdGEubWl4Um90YXRlID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJtaXhSb3RhdGVcIiwgMSk7XG5cdFx0XHRcdGRhdGEubWl4WCA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwibWl4WFwiLCAxKTtcblx0XHRcdFx0ZGF0YS5taXhZID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJtaXhZXCIsIGRhdGEubWl4WCk7XG5cdFx0XHRcdGRhdGEubWl4U2NhbGVYID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJtaXhTY2FsZVhcIiwgMSk7XG5cdFx0XHRcdGRhdGEubWl4U2NhbGVZID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJtaXhTY2FsZVlcIiwgZGF0YS5taXhTY2FsZVgpO1xuXHRcdFx0XHRkYXRhLm1peFNoZWFyWSA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwibWl4U2hlYXJZXCIsIDEpO1xuXG5cdFx0XHRcdHNrZWxldG9uRGF0YS50cmFuc2Zvcm1Db25zdHJhaW50cy5wdXNoKGRhdGEpO1xuXHRcdFx0fVxuXHRcdH1cblxuXHRcdC8vIFBhdGggY29uc3RyYWludHMuXG5cdFx0aWYgKHJvb3QucGF0aCkge1xuXHRcdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCByb290LnBhdGgubGVuZ3RoOyBpKyspIHtcblx0XHRcdFx0bGV0IGNvbnN0cmFpbnRNYXAgPSByb290LnBhdGhbaV07XG5cdFx0XHRcdGxldCBkYXRhID0gbmV3IFBhdGhDb25zdHJhaW50RGF0YShjb25zdHJhaW50TWFwLm5hbWUpO1xuXHRcdFx0XHRkYXRhLm9yZGVyID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJvcmRlclwiLCAwKTtcblx0XHRcdFx0ZGF0YS5za2luUmVxdWlyZWQgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcInNraW5cIiwgZmFsc2UpO1xuXG5cdFx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCBjb25zdHJhaW50TWFwLmJvbmVzLmxlbmd0aDsgaWkrKykge1xuXHRcdFx0XHRcdGxldCBib25lTmFtZSA9IGNvbnN0cmFpbnRNYXAuYm9uZXNbaWldO1xuXHRcdFx0XHRcdGxldCBib25lID0gc2tlbGV0b25EYXRhLmZpbmRCb25lKGJvbmVOYW1lKTtcblx0XHRcdFx0XHRpZiAoIWJvbmUpIHRocm93IG5ldyBFcnJvcihgQ291bGRuJ3QgZmluZCBib25lICR7Ym9uZU5hbWV9IGZvciBwYXRoIGNvbnN0cmFpbnQgJHtjb25zdHJhaW50TWFwLm5hbWV9LmApO1xuXHRcdFx0XHRcdGRhdGEuYm9uZXMucHVzaChib25lKTtcblx0XHRcdFx0fVxuXG5cdFx0XHRcdGxldCB0YXJnZXROYW1lOiBzdHJpbmcgPSBjb25zdHJhaW50TWFwLnRhcmdldDtcblx0XHRcdFx0bGV0IHRhcmdldCA9IHNrZWxldG9uRGF0YS5maW5kU2xvdCh0YXJnZXROYW1lKTtcblx0XHRcdFx0aWYgKCF0YXJnZXQpIHRocm93IG5ldyBFcnJvcihgQ291bGRuJ3QgZmluZCB0YXJnZXQgc2xvdCAke3RhcmdldE5hbWV9IGZvciBwYXRoIGNvbnN0cmFpbnQgJHtjb25zdHJhaW50TWFwLm5hbWV9LmApO1xuXHRcdFx0XHRkYXRhLnRhcmdldCA9IHRhcmdldDtcblxuXHRcdFx0XHRkYXRhLnBvc2l0aW9uTW9kZSA9IFV0aWxzLmVudW1WYWx1ZShQb3NpdGlvbk1vZGUsIGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwicG9zaXRpb25Nb2RlXCIsIFwiUGVyY2VudFwiKSk7XG5cdFx0XHRcdGRhdGEuc3BhY2luZ01vZGUgPSBVdGlscy5lbnVtVmFsdWUoU3BhY2luZ01vZGUsIGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwic3BhY2luZ01vZGVcIiwgXCJMZW5ndGhcIikpO1xuXHRcdFx0XHRkYXRhLnJvdGF0ZU1vZGUgPSBVdGlscy5lbnVtVmFsdWUoUm90YXRlTW9kZSwgZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJyb3RhdGVNb2RlXCIsIFwiVGFuZ2VudFwiKSk7XG5cdFx0XHRcdGRhdGEub2Zmc2V0Um90YXRpb24gPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcInJvdGF0aW9uXCIsIDApO1xuXHRcdFx0XHRkYXRhLnBvc2l0aW9uID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJwb3NpdGlvblwiLCAwKTtcblx0XHRcdFx0aWYgKGRhdGEucG9zaXRpb25Nb2RlID09IFBvc2l0aW9uTW9kZS5GaXhlZCkgZGF0YS5wb3NpdGlvbiAqPSBzY2FsZTtcblx0XHRcdFx0ZGF0YS5zcGFjaW5nID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJzcGFjaW5nXCIsIDApO1xuXHRcdFx0XHRpZiAoZGF0YS5zcGFjaW5nTW9kZSA9PSBTcGFjaW5nTW9kZS5MZW5ndGggfHwgZGF0YS5zcGFjaW5nTW9kZSA9PSBTcGFjaW5nTW9kZS5GaXhlZCkgZGF0YS5zcGFjaW5nICo9IHNjYWxlO1xuXHRcdFx0XHRkYXRhLm1peFJvdGF0ZSA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwibWl4Um90YXRlXCIsIDEpO1xuXHRcdFx0XHRkYXRhLm1peFggPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcIm1peFhcIiwgMSk7XG5cdFx0XHRcdGRhdGEubWl4WSA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwibWl4WVwiLCBkYXRhLm1peFgpO1xuXG5cdFx0XHRcdHNrZWxldG9uRGF0YS5wYXRoQ29uc3RyYWludHMucHVzaChkYXRhKTtcblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBQaHlzaWNzIGNvbnN0cmFpbnRzLlxuXHRcdGlmIChyb290LnBoeXNpY3MpIHtcblx0XHRcdGZvciAobGV0IGkgPSAwOyBpIDwgcm9vdC5waHlzaWNzLmxlbmd0aDsgaSsrKSB7XG5cdFx0XHRcdGNvbnN0IGNvbnN0cmFpbnRNYXAgPSByb290LnBoeXNpY3NbaV07XG5cdFx0XHRcdGNvbnN0IGRhdGEgPSBuZXcgUGh5c2ljc0NvbnN0cmFpbnREYXRhKGNvbnN0cmFpbnRNYXAubmFtZSk7XG5cdFx0XHRcdGRhdGEub3JkZXIgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcIm9yZGVyXCIsIDApO1xuXHRcdFx0XHRkYXRhLnNraW5SZXF1aXJlZCA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwic2tpblwiLCBmYWxzZSk7XG5cblx0XHRcdFx0Y29uc3QgYm9uZU5hbWUgPSBjb25zdHJhaW50TWFwLmJvbmU7XG5cdFx0XHRcdGNvbnN0IGJvbmUgPSBza2VsZXRvbkRhdGEuZmluZEJvbmUoYm9uZU5hbWUpO1xuXHRcdFx0XHRpZiAoYm9uZSA9PSBudWxsKSB0aHJvdyBuZXcgRXJyb3IoXCJQaHlzaWNzIGJvbmUgbm90IGZvdW5kOiBcIiArIGJvbmVOYW1lKTtcblx0XHRcdFx0ZGF0YS5ib25lID0gYm9uZTtcblxuXHRcdFx0XHRkYXRhLnggPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcInhcIiwgMCk7XG5cdFx0XHRcdGRhdGEueSA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwieVwiLCAwKTtcblx0XHRcdFx0ZGF0YS5yb3RhdGUgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcInJvdGF0ZVwiLCAwKTtcblx0XHRcdFx0ZGF0YS5zY2FsZVggPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcInNjYWxlWFwiLCAwKTtcblx0XHRcdFx0ZGF0YS5zaGVhclggPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcInNoZWFyWFwiLCAwKTtcblx0XHRcdFx0ZGF0YS5saW1pdCA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwibGltaXRcIiwgNTAwMCkgKiBzY2FsZTtcblx0XHRcdFx0ZGF0YS5zdGVwID0gMSAvIGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwiZnBzXCIsIDYwKTtcblx0XHRcdFx0ZGF0YS5pbmVydGlhID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJpbmVydGlhXCIsIDEpO1xuXHRcdFx0XHRkYXRhLnN0cmVuZ3RoID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJzdHJlbmd0aFwiLCAxMDApO1xuXHRcdFx0XHRkYXRhLmRhbXBpbmcgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcImRhbXBpbmdcIiwgMSk7XG5cdFx0XHRcdGRhdGEubWFzc0ludmVyc2UgPSAxIC8gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJtYXNzXCIsIDEpO1xuXHRcdFx0XHRkYXRhLndpbmQgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcIndpbmRcIiwgMCk7XG5cdFx0XHRcdGRhdGEuZ3Jhdml0eSA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwiZ3Jhdml0eVwiLCAwKTtcblx0XHRcdFx0ZGF0YS5taXggPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcIm1peFwiLCAxKTtcblx0XHRcdFx0ZGF0YS5pbmVydGlhR2xvYmFsID0gZ2V0VmFsdWUoY29uc3RyYWludE1hcCwgXCJpbmVydGlhR2xvYmFsXCIsIGZhbHNlKTtcblx0XHRcdFx0ZGF0YS5zdHJlbmd0aEdsb2JhbCA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwic3RyZW5ndGhHbG9iYWxcIiwgZmFsc2UpO1xuXHRcdFx0XHRkYXRhLmRhbXBpbmdHbG9iYWwgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcImRhbXBpbmdHbG9iYWxcIiwgZmFsc2UpO1xuXHRcdFx0XHRkYXRhLm1hc3NHbG9iYWwgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcIm1hc3NHbG9iYWxcIiwgZmFsc2UpO1xuXHRcdFx0XHRkYXRhLndpbmRHbG9iYWwgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcIndpbmRHbG9iYWxcIiwgZmFsc2UpO1xuXHRcdFx0XHRkYXRhLmdyYXZpdHlHbG9iYWwgPSBnZXRWYWx1ZShjb25zdHJhaW50TWFwLCBcImdyYXZpdHlHbG9iYWxcIiwgZmFsc2UpO1xuXHRcdFx0XHRkYXRhLm1peEdsb2JhbCA9IGdldFZhbHVlKGNvbnN0cmFpbnRNYXAsIFwibWl4R2xvYmFsXCIsIGZhbHNlKTtcblxuXHRcdFx0XHRza2VsZXRvbkRhdGEucGh5c2ljc0NvbnN0cmFpbnRzLnB1c2goZGF0YSk7XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0Ly8gU2tpbnMuXG5cdFx0aWYgKHJvb3Quc2tpbnMpIHtcblx0XHRcdGZvciAobGV0IGkgPSAwOyBpIDwgcm9vdC5za2lucy5sZW5ndGg7IGkrKykge1xuXHRcdFx0XHRsZXQgc2tpbk1hcCA9IHJvb3Quc2tpbnNbaV1cblx0XHRcdFx0bGV0IHNraW4gPSBuZXcgU2tpbihza2luTWFwLm5hbWUpO1xuXG5cdFx0XHRcdGlmIChza2luTWFwLmJvbmVzKSB7XG5cdFx0XHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IHNraW5NYXAuYm9uZXMubGVuZ3RoOyBpaSsrKSB7XG5cdFx0XHRcdFx0XHRsZXQgYm9uZU5hbWUgPSBza2luTWFwLmJvbmVzW2lpXTtcblx0XHRcdFx0XHRcdGxldCBib25lID0gc2tlbGV0b25EYXRhLmZpbmRCb25lKGJvbmVOYW1lKTtcblx0XHRcdFx0XHRcdGlmICghYm9uZSkgdGhyb3cgbmV3IEVycm9yKGBDb3VsZG4ndCBmaW5kIGJvbmUgJHtib25lTmFtZX0gZm9yIHNraW4gJHtza2luTWFwLm5hbWV9LmApO1xuXHRcdFx0XHRcdFx0c2tpbi5ib25lcy5wdXNoKGJvbmUpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0fVxuXG5cdFx0XHRcdGlmIChza2luTWFwLmlrKSB7XG5cdFx0XHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IHNraW5NYXAuaWsubGVuZ3RoOyBpaSsrKSB7XG5cdFx0XHRcdFx0XHRsZXQgY29uc3RyYWludE5hbWUgPSBza2luTWFwLmlrW2lpXTtcblx0XHRcdFx0XHRcdGxldCBjb25zdHJhaW50ID0gc2tlbGV0b25EYXRhLmZpbmRJa0NvbnN0cmFpbnQoY29uc3RyYWludE5hbWUpO1xuXHRcdFx0XHRcdFx0aWYgKCFjb25zdHJhaW50KSB0aHJvdyBuZXcgRXJyb3IoYENvdWxkbid0IGZpbmQgSUsgY29uc3RyYWludCAke2NvbnN0cmFpbnROYW1lfSBmb3Igc2tpbiAke3NraW5NYXAubmFtZX0uYCk7XG5cdFx0XHRcdFx0XHRza2luLmNvbnN0cmFpbnRzLnB1c2goY29uc3RyYWludCk7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHR9XG5cblx0XHRcdFx0aWYgKHNraW5NYXAudHJhbnNmb3JtKSB7XG5cdFx0XHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IHNraW5NYXAudHJhbnNmb3JtLmxlbmd0aDsgaWkrKykge1xuXHRcdFx0XHRcdFx0bGV0IGNvbnN0cmFpbnROYW1lID0gc2tpbk1hcC50cmFuc2Zvcm1baWldO1xuXHRcdFx0XHRcdFx0bGV0IGNvbnN0cmFpbnQgPSBza2VsZXRvbkRhdGEuZmluZFRyYW5zZm9ybUNvbnN0cmFpbnQoY29uc3RyYWludE5hbWUpO1xuXHRcdFx0XHRcdFx0aWYgKCFjb25zdHJhaW50KSB0aHJvdyBuZXcgRXJyb3IoYENvdWxkbid0IGZpbmQgdHJhbnNmb3JtIGNvbnN0cmFpbnQgJHtjb25zdHJhaW50TmFtZX0gZm9yIHNraW4gJHtza2luTWFwLm5hbWV9LmApO1xuXHRcdFx0XHRcdFx0c2tpbi5jb25zdHJhaW50cy5wdXNoKGNvbnN0cmFpbnQpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0fVxuXG5cdFx0XHRcdGlmIChza2luTWFwLnBhdGgpIHtcblx0XHRcdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgc2tpbk1hcC5wYXRoLmxlbmd0aDsgaWkrKykge1xuXHRcdFx0XHRcdFx0bGV0IGNvbnN0cmFpbnROYW1lID0gc2tpbk1hcC5wYXRoW2lpXTtcblx0XHRcdFx0XHRcdGxldCBjb25zdHJhaW50ID0gc2tlbGV0b25EYXRhLmZpbmRQYXRoQ29uc3RyYWludChjb25zdHJhaW50TmFtZSk7XG5cdFx0XHRcdFx0XHRpZiAoIWNvbnN0cmFpbnQpIHRocm93IG5ldyBFcnJvcihgQ291bGRuJ3QgZmluZCBwYXRoIGNvbnN0cmFpbnQgJHtjb25zdHJhaW50TmFtZX0gZm9yIHNraW4gJHtza2luTWFwLm5hbWV9LmApO1xuXHRcdFx0XHRcdFx0c2tpbi5jb25zdHJhaW50cy5wdXNoKGNvbnN0cmFpbnQpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0fVxuXG5cdFx0XHRcdGlmIChza2luTWFwLnBoeXNpY3MpIHtcblx0XHRcdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgc2tpbk1hcC5waHlzaWNzLmxlbmd0aDsgaWkrKykge1xuXHRcdFx0XHRcdFx0bGV0IGNvbnN0cmFpbnROYW1lID0gc2tpbk1hcC5waHlzaWNzW2lpXTtcblx0XHRcdFx0XHRcdGxldCBjb25zdHJhaW50ID0gc2tlbGV0b25EYXRhLmZpbmRQaHlzaWNzQ29uc3RyYWludChjb25zdHJhaW50TmFtZSk7XG5cdFx0XHRcdFx0XHRpZiAoIWNvbnN0cmFpbnQpIHRocm93IG5ldyBFcnJvcihgQ291bGRuJ3QgZmluZCBwaHlzaWNzIGNvbnN0cmFpbnQgJHtjb25zdHJhaW50TmFtZX0gZm9yIHNraW4gJHtza2luTWFwLm5hbWV9LmApO1xuXHRcdFx0XHRcdFx0c2tpbi5jb25zdHJhaW50cy5wdXNoKGNvbnN0cmFpbnQpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0fVxuXG5cdFx0XHRcdGZvciAobGV0IHNsb3ROYW1lIGluIHNraW5NYXAuYXR0YWNobWVudHMpIHtcblx0XHRcdFx0XHRsZXQgc2xvdCA9IHNrZWxldG9uRGF0YS5maW5kU2xvdChzbG90TmFtZSk7XG5cdFx0XHRcdFx0aWYgKCFzbG90KSB0aHJvdyBuZXcgRXJyb3IoYENvdWxkbid0IGZpbmQgc2xvdCAke3Nsb3ROYW1lfSBmb3Igc2tpbiAke3NraW5NYXAubmFtZX0uYCk7XG5cdFx0XHRcdFx0bGV0IHNsb3RNYXAgPSBza2luTWFwLmF0dGFjaG1lbnRzW3Nsb3ROYW1lXTtcblx0XHRcdFx0XHRmb3IgKGxldCBlbnRyeU5hbWUgaW4gc2xvdE1hcCkge1xuXHRcdFx0XHRcdFx0bGV0IGF0dGFjaG1lbnQgPSB0aGlzLnJlYWRBdHRhY2htZW50KHNsb3RNYXBbZW50cnlOYW1lXSwgc2tpbiwgc2xvdC5pbmRleCwgZW50cnlOYW1lLCBza2VsZXRvbkRhdGEpO1xuXHRcdFx0XHRcdFx0aWYgKGF0dGFjaG1lbnQpIHNraW4uc2V0QXR0YWNobWVudChzbG90LmluZGV4LCBlbnRyeU5hbWUsIGF0dGFjaG1lbnQpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0fVxuXHRcdFx0XHRza2VsZXRvbkRhdGEuc2tpbnMucHVzaChza2luKTtcblx0XHRcdFx0aWYgKHNraW4ubmFtZSA9PSBcImRlZmF1bHRcIikgc2tlbGV0b25EYXRhLmRlZmF1bHRTa2luID0gc2tpbjtcblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBMaW5rZWQgbWVzaGVzLlxuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gdGhpcy5saW5rZWRNZXNoZXMubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRsZXQgbGlua2VkTWVzaCA9IHRoaXMubGlua2VkTWVzaGVzW2ldO1xuXHRcdFx0bGV0IHNraW4gPSAhbGlua2VkTWVzaC5za2luID8gc2tlbGV0b25EYXRhLmRlZmF1bHRTa2luIDogc2tlbGV0b25EYXRhLmZpbmRTa2luKGxpbmtlZE1lc2guc2tpbik7XG5cdFx0XHRpZiAoIXNraW4pIHRocm93IG5ldyBFcnJvcihgU2tpbiBub3QgZm91bmQ6ICR7bGlua2VkTWVzaC5za2lufWApO1xuXHRcdFx0bGV0IHBhcmVudCA9IHNraW4uZ2V0QXR0YWNobWVudChsaW5rZWRNZXNoLnNsb3RJbmRleCwgbGlua2VkTWVzaC5wYXJlbnQpO1xuXHRcdFx0aWYgKCFwYXJlbnQpIHRocm93IG5ldyBFcnJvcihgUGFyZW50IG1lc2ggbm90IGZvdW5kOiAke2xpbmtlZE1lc2gucGFyZW50fWApO1xuXHRcdFx0bGlua2VkTWVzaC5tZXNoLnRpbWVsaW5lQXR0YWNobWVudCA9IGxpbmtlZE1lc2guaW5oZXJpdFRpbWVsaW5lID8gPFZlcnRleEF0dGFjaG1lbnQ+cGFyZW50IDogPFZlcnRleEF0dGFjaG1lbnQ+bGlua2VkTWVzaC5tZXNoO1xuXHRcdFx0bGlua2VkTWVzaC5tZXNoLnNldFBhcmVudE1lc2goPE1lc2hBdHRhY2htZW50PnBhcmVudCk7XG5cdFx0XHRpZiAobGlua2VkTWVzaC5tZXNoLnJlZ2lvbiAhPSBudWxsKSBsaW5rZWRNZXNoLm1lc2gudXBkYXRlUmVnaW9uKCk7XG5cdFx0fVxuXHRcdHRoaXMubGlua2VkTWVzaGVzLmxlbmd0aCA9IDA7XG5cblx0XHQvLyBFdmVudHMuXG5cdFx0aWYgKHJvb3QuZXZlbnRzKSB7XG5cdFx0XHRmb3IgKGxldCBldmVudE5hbWUgaW4gcm9vdC5ldmVudHMpIHtcblx0XHRcdFx0bGV0IGV2ZW50TWFwID0gcm9vdC5ldmVudHNbZXZlbnROYW1lXTtcblx0XHRcdFx0bGV0IGRhdGEgPSBuZXcgRXZlbnREYXRhKGV2ZW50TmFtZSk7XG5cdFx0XHRcdGRhdGEuaW50VmFsdWUgPSBnZXRWYWx1ZShldmVudE1hcCwgXCJpbnRcIiwgMCk7XG5cdFx0XHRcdGRhdGEuZmxvYXRWYWx1ZSA9IGdldFZhbHVlKGV2ZW50TWFwLCBcImZsb2F0XCIsIDApO1xuXHRcdFx0XHRkYXRhLnN0cmluZ1ZhbHVlID0gZ2V0VmFsdWUoZXZlbnRNYXAsIFwic3RyaW5nXCIsIFwiXCIpO1xuXHRcdFx0XHRkYXRhLmF1ZGlvUGF0aCA9IGdldFZhbHVlKGV2ZW50TWFwLCBcImF1ZGlvXCIsIG51bGwpO1xuXHRcdFx0XHRpZiAoZGF0YS5hdWRpb1BhdGgpIHtcblx0XHRcdFx0XHRkYXRhLnZvbHVtZSA9IGdldFZhbHVlKGV2ZW50TWFwLCBcInZvbHVtZVwiLCAxKTtcblx0XHRcdFx0XHRkYXRhLmJhbGFuY2UgPSBnZXRWYWx1ZShldmVudE1hcCwgXCJiYWxhbmNlXCIsIDApO1xuXHRcdFx0XHR9XG5cdFx0XHRcdHNrZWxldG9uRGF0YS5ldmVudHMucHVzaChkYXRhKTtcblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBBbmltYXRpb25zLlxuXHRcdGlmIChyb290LmFuaW1hdGlvbnMpIHtcblx0XHRcdGZvciAobGV0IGFuaW1hdGlvbk5hbWUgaW4gcm9vdC5hbmltYXRpb25zKSB7XG5cdFx0XHRcdGxldCBhbmltYXRpb25NYXAgPSByb290LmFuaW1hdGlvbnNbYW5pbWF0aW9uTmFtZV07XG5cdFx0XHRcdHRoaXMucmVhZEFuaW1hdGlvbihhbmltYXRpb25NYXAsIGFuaW1hdGlvbk5hbWUsIHNrZWxldG9uRGF0YSk7XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0cmV0dXJuIHNrZWxldG9uRGF0YTtcblx0fVxuXG5cdHJlYWRBdHRhY2htZW50IChtYXA6IGFueSwgc2tpbjogU2tpbiwgc2xvdEluZGV4OiBudW1iZXIsIG5hbWU6IHN0cmluZywgc2tlbGV0b25EYXRhOiBTa2VsZXRvbkRhdGEpOiBBdHRhY2htZW50IHwgbnVsbCB7XG5cdFx0bGV0IHNjYWxlID0gdGhpcy5zY2FsZTtcblx0XHRuYW1lID0gZ2V0VmFsdWUobWFwLCBcIm5hbWVcIiwgbmFtZSk7XG5cblx0XHRzd2l0Y2ggKGdldFZhbHVlKG1hcCwgXCJ0eXBlXCIsIFwicmVnaW9uXCIpKSB7XG5cdFx0XHRjYXNlIFwicmVnaW9uXCI6IHtcblx0XHRcdFx0bGV0IHBhdGggPSBnZXRWYWx1ZShtYXAsIFwicGF0aFwiLCBuYW1lKTtcblx0XHRcdFx0bGV0IHNlcXVlbmNlID0gdGhpcy5yZWFkU2VxdWVuY2UoZ2V0VmFsdWUobWFwLCBcInNlcXVlbmNlXCIsIG51bGwpKTtcblx0XHRcdFx0bGV0IHJlZ2lvbiA9IHRoaXMuYXR0YWNobWVudExvYWRlci5uZXdSZWdpb25BdHRhY2htZW50KHNraW4sIG5hbWUsIHBhdGgsIHNlcXVlbmNlKTtcblx0XHRcdFx0aWYgKCFyZWdpb24pIHJldHVybiBudWxsO1xuXHRcdFx0XHRyZWdpb24ucGF0aCA9IHBhdGg7XG5cdFx0XHRcdHJlZ2lvbi54ID0gZ2V0VmFsdWUobWFwLCBcInhcIiwgMCkgKiBzY2FsZTtcblx0XHRcdFx0cmVnaW9uLnkgPSBnZXRWYWx1ZShtYXAsIFwieVwiLCAwKSAqIHNjYWxlO1xuXHRcdFx0XHRyZWdpb24uc2NhbGVYID0gZ2V0VmFsdWUobWFwLCBcInNjYWxlWFwiLCAxKTtcblx0XHRcdFx0cmVnaW9uLnNjYWxlWSA9IGdldFZhbHVlKG1hcCwgXCJzY2FsZVlcIiwgMSk7XG5cdFx0XHRcdHJlZ2lvbi5yb3RhdGlvbiA9IGdldFZhbHVlKG1hcCwgXCJyb3RhdGlvblwiLCAwKTtcblx0XHRcdFx0cmVnaW9uLndpZHRoID0gbWFwLndpZHRoICogc2NhbGU7XG5cdFx0XHRcdHJlZ2lvbi5oZWlnaHQgPSBtYXAuaGVpZ2h0ICogc2NhbGU7XG5cdFx0XHRcdHJlZ2lvbi5zZXF1ZW5jZSA9IHNlcXVlbmNlO1xuXG5cdFx0XHRcdGxldCBjb2xvcjogc3RyaW5nID0gZ2V0VmFsdWUobWFwLCBcImNvbG9yXCIsIG51bGwpO1xuXHRcdFx0XHRpZiAoY29sb3IpIHJlZ2lvbi5jb2xvci5zZXRGcm9tU3RyaW5nKGNvbG9yKTtcblxuXHRcdFx0XHRpZiAocmVnaW9uLnJlZ2lvbiAhPSBudWxsKSByZWdpb24udXBkYXRlUmVnaW9uKCk7XG5cdFx0XHRcdHJldHVybiByZWdpb247XG5cdFx0XHR9XG5cdFx0XHRjYXNlIFwiYm91bmRpbmdib3hcIjoge1xuXHRcdFx0XHRsZXQgYm94ID0gdGhpcy5hdHRhY2htZW50TG9hZGVyLm5ld0JvdW5kaW5nQm94QXR0YWNobWVudChza2luLCBuYW1lKTtcblx0XHRcdFx0aWYgKCFib3gpIHJldHVybiBudWxsO1xuXHRcdFx0XHR0aGlzLnJlYWRWZXJ0aWNlcyhtYXAsIGJveCwgbWFwLnZlcnRleENvdW50IDw8IDEpO1xuXHRcdFx0XHRsZXQgY29sb3I6IHN0cmluZyA9IGdldFZhbHVlKG1hcCwgXCJjb2xvclwiLCBudWxsKTtcblx0XHRcdFx0aWYgKGNvbG9yKSBib3guY29sb3Iuc2V0RnJvbVN0cmluZyhjb2xvcik7XG5cdFx0XHRcdHJldHVybiBib3g7XG5cdFx0XHR9XG5cdFx0XHRjYXNlIFwibWVzaFwiOlxuXHRcdFx0Y2FzZSBcImxpbmtlZG1lc2hcIjoge1xuXHRcdFx0XHRsZXQgcGF0aCA9IGdldFZhbHVlKG1hcCwgXCJwYXRoXCIsIG5hbWUpO1xuXHRcdFx0XHRsZXQgc2VxdWVuY2UgPSB0aGlzLnJlYWRTZXF1ZW5jZShnZXRWYWx1ZShtYXAsIFwic2VxdWVuY2VcIiwgbnVsbCkpO1xuXHRcdFx0XHRsZXQgbWVzaCA9IHRoaXMuYXR0YWNobWVudExvYWRlci5uZXdNZXNoQXR0YWNobWVudChza2luLCBuYW1lLCBwYXRoLCBzZXF1ZW5jZSk7XG5cdFx0XHRcdGlmICghbWVzaCkgcmV0dXJuIG51bGw7XG5cdFx0XHRcdG1lc2gucGF0aCA9IHBhdGg7XG5cblx0XHRcdFx0bGV0IGNvbG9yID0gZ2V0VmFsdWUobWFwLCBcImNvbG9yXCIsIG51bGwpO1xuXHRcdFx0XHRpZiAoY29sb3IpIG1lc2guY29sb3Iuc2V0RnJvbVN0cmluZyhjb2xvcik7XG5cblx0XHRcdFx0bWVzaC53aWR0aCA9IGdldFZhbHVlKG1hcCwgXCJ3aWR0aFwiLCAwKSAqIHNjYWxlO1xuXHRcdFx0XHRtZXNoLmhlaWdodCA9IGdldFZhbHVlKG1hcCwgXCJoZWlnaHRcIiwgMCkgKiBzY2FsZTtcblx0XHRcdFx0bWVzaC5zZXF1ZW5jZSA9IHNlcXVlbmNlO1xuXG5cdFx0XHRcdGxldCBwYXJlbnQ6IHN0cmluZyA9IGdldFZhbHVlKG1hcCwgXCJwYXJlbnRcIiwgbnVsbCk7XG5cdFx0XHRcdGlmIChwYXJlbnQpIHtcblx0XHRcdFx0XHR0aGlzLmxpbmtlZE1lc2hlcy5wdXNoKG5ldyBMaW5rZWRNZXNoKG1lc2gsIDxzdHJpbmc+Z2V0VmFsdWUobWFwLCBcInNraW5cIiwgbnVsbCksIHNsb3RJbmRleCwgcGFyZW50LCBnZXRWYWx1ZShtYXAsIFwidGltZWxpbmVzXCIsIHRydWUpKSk7XG5cdFx0XHRcdFx0cmV0dXJuIG1lc2g7XG5cdFx0XHRcdH1cblxuXHRcdFx0XHRsZXQgdXZzOiBBcnJheTxudW1iZXI+ID0gbWFwLnV2cztcblx0XHRcdFx0dGhpcy5yZWFkVmVydGljZXMobWFwLCBtZXNoLCB1dnMubGVuZ3RoKTtcblx0XHRcdFx0bWVzaC50cmlhbmdsZXMgPSBtYXAudHJpYW5nbGVzO1xuXHRcdFx0XHRtZXNoLnJlZ2lvblVWcyA9IHV2cztcblx0XHRcdFx0aWYgKG1lc2gucmVnaW9uICE9IG51bGwpIG1lc2gudXBkYXRlUmVnaW9uKCk7XG5cblx0XHRcdFx0bWVzaC5lZGdlcyA9IGdldFZhbHVlKG1hcCwgXCJlZGdlc1wiLCBudWxsKTtcblx0XHRcdFx0bWVzaC5odWxsTGVuZ3RoID0gZ2V0VmFsdWUobWFwLCBcImh1bGxcIiwgMCkgKiAyO1xuXHRcdFx0XHRyZXR1cm4gbWVzaDtcblx0XHRcdH1cblx0XHRcdGNhc2UgXCJwYXRoXCI6IHtcblx0XHRcdFx0bGV0IHBhdGggPSB0aGlzLmF0dGFjaG1lbnRMb2FkZXIubmV3UGF0aEF0dGFjaG1lbnQoc2tpbiwgbmFtZSk7XG5cdFx0XHRcdGlmICghcGF0aCkgcmV0dXJuIG51bGw7XG5cdFx0XHRcdHBhdGguY2xvc2VkID0gZ2V0VmFsdWUobWFwLCBcImNsb3NlZFwiLCBmYWxzZSk7XG5cdFx0XHRcdHBhdGguY29uc3RhbnRTcGVlZCA9IGdldFZhbHVlKG1hcCwgXCJjb25zdGFudFNwZWVkXCIsIHRydWUpO1xuXG5cdFx0XHRcdGxldCB2ZXJ0ZXhDb3VudCA9IG1hcC52ZXJ0ZXhDb3VudDtcblx0XHRcdFx0dGhpcy5yZWFkVmVydGljZXMobWFwLCBwYXRoLCB2ZXJ0ZXhDb3VudCA8PCAxKTtcblxuXHRcdFx0XHRsZXQgbGVuZ3RoczogQXJyYXk8bnVtYmVyPiA9IFV0aWxzLm5ld0FycmF5KHZlcnRleENvdW50IC8gMywgMCk7XG5cdFx0XHRcdGZvciAobGV0IGkgPSAwOyBpIDwgbWFwLmxlbmd0aHMubGVuZ3RoOyBpKyspXG5cdFx0XHRcdFx0bGVuZ3Roc1tpXSA9IG1hcC5sZW5ndGhzW2ldICogc2NhbGU7XG5cdFx0XHRcdHBhdGgubGVuZ3RocyA9IGxlbmd0aHM7XG5cblx0XHRcdFx0bGV0IGNvbG9yOiBzdHJpbmcgPSBnZXRWYWx1ZShtYXAsIFwiY29sb3JcIiwgbnVsbCk7XG5cdFx0XHRcdGlmIChjb2xvcikgcGF0aC5jb2xvci5zZXRGcm9tU3RyaW5nKGNvbG9yKTtcblx0XHRcdFx0cmV0dXJuIHBhdGg7XG5cdFx0XHR9XG5cdFx0XHRjYXNlIFwicG9pbnRcIjoge1xuXHRcdFx0XHRsZXQgcG9pbnQgPSB0aGlzLmF0dGFjaG1lbnRMb2FkZXIubmV3UG9pbnRBdHRhY2htZW50KHNraW4sIG5hbWUpO1xuXHRcdFx0XHRpZiAoIXBvaW50KSByZXR1cm4gbnVsbDtcblx0XHRcdFx0cG9pbnQueCA9IGdldFZhbHVlKG1hcCwgXCJ4XCIsIDApICogc2NhbGU7XG5cdFx0XHRcdHBvaW50LnkgPSBnZXRWYWx1ZShtYXAsIFwieVwiLCAwKSAqIHNjYWxlO1xuXHRcdFx0XHRwb2ludC5yb3RhdGlvbiA9IGdldFZhbHVlKG1hcCwgXCJyb3RhdGlvblwiLCAwKTtcblxuXHRcdFx0XHRsZXQgY29sb3IgPSBnZXRWYWx1ZShtYXAsIFwiY29sb3JcIiwgbnVsbCk7XG5cdFx0XHRcdGlmIChjb2xvcikgcG9pbnQuY29sb3Iuc2V0RnJvbVN0cmluZyhjb2xvcik7XG5cdFx0XHRcdHJldHVybiBwb2ludDtcblx0XHRcdH1cblx0XHRcdGNhc2UgXCJjbGlwcGluZ1wiOiB7XG5cdFx0XHRcdGxldCBjbGlwID0gdGhpcy5hdHRhY2htZW50TG9hZGVyLm5ld0NsaXBwaW5nQXR0YWNobWVudChza2luLCBuYW1lKTtcblx0XHRcdFx0aWYgKCFjbGlwKSByZXR1cm4gbnVsbDtcblxuXHRcdFx0XHRsZXQgZW5kID0gZ2V0VmFsdWUobWFwLCBcImVuZFwiLCBudWxsKTtcblx0XHRcdFx0aWYgKGVuZCkgY2xpcC5lbmRTbG90ID0gc2tlbGV0b25EYXRhLmZpbmRTbG90KGVuZCk7XG5cblx0XHRcdFx0bGV0IHZlcnRleENvdW50ID0gbWFwLnZlcnRleENvdW50O1xuXHRcdFx0XHR0aGlzLnJlYWRWZXJ0aWNlcyhtYXAsIGNsaXAsIHZlcnRleENvdW50IDw8IDEpO1xuXG5cdFx0XHRcdGxldCBjb2xvcjogc3RyaW5nID0gZ2V0VmFsdWUobWFwLCBcImNvbG9yXCIsIG51bGwpO1xuXHRcdFx0XHRpZiAoY29sb3IpIGNsaXAuY29sb3Iuc2V0RnJvbVN0cmluZyhjb2xvcik7XG5cdFx0XHRcdHJldHVybiBjbGlwO1xuXHRcdFx0fVxuXHRcdH1cblx0XHRyZXR1cm4gbnVsbDtcblx0fVxuXG5cdHJlYWRTZXF1ZW5jZSAobWFwOiBhbnkpIHtcblx0XHRpZiAobWFwID09IG51bGwpIHJldHVybiBudWxsO1xuXHRcdGxldCBzZXF1ZW5jZSA9IG5ldyBTZXF1ZW5jZShnZXRWYWx1ZShtYXAsIFwiY291bnRcIiwgMCkpO1xuXHRcdHNlcXVlbmNlLnN0YXJ0ID0gZ2V0VmFsdWUobWFwLCBcInN0YXJ0XCIsIDEpO1xuXHRcdHNlcXVlbmNlLmRpZ2l0cyA9IGdldFZhbHVlKG1hcCwgXCJkaWdpdHNcIiwgMCk7XG5cdFx0c2VxdWVuY2Uuc2V0dXBJbmRleCA9IGdldFZhbHVlKG1hcCwgXCJzZXR1cFwiLCAwKTtcblx0XHRyZXR1cm4gc2VxdWVuY2U7XG5cdH1cblxuXHRyZWFkVmVydGljZXMgKG1hcDogYW55LCBhdHRhY2htZW50OiBWZXJ0ZXhBdHRhY2htZW50LCB2ZXJ0aWNlc0xlbmd0aDogbnVtYmVyKSB7XG5cdFx0bGV0IHNjYWxlID0gdGhpcy5zY2FsZTtcblx0XHRhdHRhY2htZW50LndvcmxkVmVydGljZXNMZW5ndGggPSB2ZXJ0aWNlc0xlbmd0aDtcblx0XHRsZXQgdmVydGljZXM6IEFycmF5PG51bWJlcj4gPSBtYXAudmVydGljZXM7XG5cdFx0aWYgKHZlcnRpY2VzTGVuZ3RoID09IHZlcnRpY2VzLmxlbmd0aCkge1xuXHRcdFx0bGV0IHNjYWxlZFZlcnRpY2VzID0gVXRpbHMudG9GbG9hdEFycmF5KHZlcnRpY2VzKTtcblx0XHRcdGlmIChzY2FsZSAhPSAxKSB7XG5cdFx0XHRcdGZvciAobGV0IGkgPSAwLCBuID0gdmVydGljZXMubGVuZ3RoOyBpIDwgbjsgaSsrKVxuXHRcdFx0XHRcdHNjYWxlZFZlcnRpY2VzW2ldICo9IHNjYWxlO1xuXHRcdFx0fVxuXHRcdFx0YXR0YWNobWVudC52ZXJ0aWNlcyA9IHNjYWxlZFZlcnRpY2VzO1xuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblx0XHRsZXQgd2VpZ2h0cyA9IG5ldyBBcnJheTxudW1iZXI+KCk7XG5cdFx0bGV0IGJvbmVzID0gbmV3IEFycmF5PG51bWJlcj4oKTtcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IHZlcnRpY2VzLmxlbmd0aDsgaSA8IG47KSB7XG5cdFx0XHRsZXQgYm9uZUNvdW50ID0gdmVydGljZXNbaSsrXTtcblx0XHRcdGJvbmVzLnB1c2goYm9uZUNvdW50KTtcblx0XHRcdGZvciAobGV0IG5uID0gaSArIGJvbmVDb3VudCAqIDQ7IGkgPCBubjsgaSArPSA0KSB7XG5cdFx0XHRcdGJvbmVzLnB1c2godmVydGljZXNbaV0pO1xuXHRcdFx0XHR3ZWlnaHRzLnB1c2godmVydGljZXNbaSArIDFdICogc2NhbGUpO1xuXHRcdFx0XHR3ZWlnaHRzLnB1c2godmVydGljZXNbaSArIDJdICogc2NhbGUpO1xuXHRcdFx0XHR3ZWlnaHRzLnB1c2godmVydGljZXNbaSArIDNdKTtcblx0XHRcdH1cblx0XHR9XG5cdFx0YXR0YWNobWVudC5ib25lcyA9IGJvbmVzO1xuXHRcdGF0dGFjaG1lbnQudmVydGljZXMgPSBVdGlscy50b0Zsb2F0QXJyYXkod2VpZ2h0cyk7XG5cdH1cblxuXHRyZWFkQW5pbWF0aW9uIChtYXA6IGFueSwgbmFtZTogc3RyaW5nLCBza2VsZXRvbkRhdGE6IFNrZWxldG9uRGF0YSkge1xuXHRcdGxldCBzY2FsZSA9IHRoaXMuc2NhbGU7XG5cdFx0bGV0IHRpbWVsaW5lcyA9IG5ldyBBcnJheTxUaW1lbGluZT4oKTtcblxuXHRcdC8vIFNsb3QgdGltZWxpbmVzLlxuXHRcdGlmIChtYXAuc2xvdHMpIHtcblx0XHRcdGZvciAobGV0IHNsb3ROYW1lIGluIG1hcC5zbG90cykge1xuXHRcdFx0XHRsZXQgc2xvdE1hcCA9IG1hcC5zbG90c1tzbG90TmFtZV07XG5cdFx0XHRcdGxldCBzbG90ID0gc2tlbGV0b25EYXRhLmZpbmRTbG90KHNsb3ROYW1lKTtcblx0XHRcdFx0aWYgKCFzbG90KSB0aHJvdyBuZXcgRXJyb3IoXCJTbG90IG5vdCBmb3VuZDogXCIgKyBzbG90TmFtZSk7XG5cdFx0XHRcdGxldCBzbG90SW5kZXggPSBzbG90LmluZGV4O1xuXHRcdFx0XHRmb3IgKGxldCB0aW1lbGluZU5hbWUgaW4gc2xvdE1hcCkge1xuXHRcdFx0XHRcdGxldCB0aW1lbGluZU1hcCA9IHNsb3RNYXBbdGltZWxpbmVOYW1lXTtcblx0XHRcdFx0XHRpZiAoIXRpbWVsaW5lTWFwKSBjb250aW51ZTtcblx0XHRcdFx0XHRsZXQgZnJhbWVzID0gdGltZWxpbmVNYXAubGVuZ3RoO1xuXHRcdFx0XHRcdGlmICh0aW1lbGluZU5hbWUgPT0gXCJhdHRhY2htZW50XCIpIHtcblx0XHRcdFx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBBdHRhY2htZW50VGltZWxpbmUoZnJhbWVzLCBzbG90SW5kZXgpO1xuXHRcdFx0XHRcdFx0Zm9yIChsZXQgZnJhbWUgPSAwOyBmcmFtZSA8IGZyYW1lczsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHRsZXQga2V5TWFwID0gdGltZWxpbmVNYXBbZnJhbWVdO1xuXHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgZ2V0VmFsdWUoa2V5TWFwLCBcInRpbWVcIiwgMCksIGdldFZhbHVlKGtleU1hcCwgXCJuYW1lXCIsIG51bGwpKTtcblx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHRpbWVsaW5lKTtcblxuXHRcdFx0XHRcdH0gZWxzZSBpZiAodGltZWxpbmVOYW1lID09IFwicmdiYVwiKSB7XG5cdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgUkdCQVRpbWVsaW5lKGZyYW1lcywgZnJhbWVzIDw8IDIsIHNsb3RJbmRleCk7XG5cdFx0XHRcdFx0XHRsZXQga2V5TWFwID0gdGltZWxpbmVNYXBbMF07XG5cdFx0XHRcdFx0XHRsZXQgdGltZSA9IGdldFZhbHVlKGtleU1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdFx0XHRcdFx0bGV0IGNvbG9yID0gQ29sb3IuZnJvbVN0cmluZyhrZXlNYXAuY29sb3IpO1xuXG5cdFx0XHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgY29sb3IuciwgY29sb3IuZywgY29sb3IuYiwgY29sb3IuYSk7XG5cdFx0XHRcdFx0XHRcdGxldCBuZXh0TWFwID0gdGltZWxpbmVNYXBbZnJhbWUgKyAxXTtcblx0XHRcdFx0XHRcdFx0aWYgKCFuZXh0TWFwKSB7XG5cdFx0XHRcdFx0XHRcdFx0dGltZWxpbmUuc2hyaW5rKGJlemllcik7XG5cdFx0XHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0bGV0IHRpbWUyID0gZ2V0VmFsdWUobmV4dE1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdFx0XHRcdFx0XHRsZXQgbmV3Q29sb3IgPSBDb2xvci5mcm9tU3RyaW5nKG5leHRNYXAuY29sb3IpO1xuXHRcdFx0XHRcdFx0XHRsZXQgY3VydmUgPSBrZXlNYXAuY3VydmU7XG5cdFx0XHRcdFx0XHRcdGlmIChjdXJ2ZSkge1xuXHRcdFx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCBjb2xvci5yLCBuZXdDb2xvci5yLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRiZXppZXIgPSByZWFkQ3VydmUoY3VydmUsIHRpbWVsaW5lLCBiZXppZXIsIGZyYW1lLCAxLCB0aW1lLCB0aW1lMiwgY29sb3IuZywgbmV3Q29sb3IuZywgMSk7XG5cdFx0XHRcdFx0XHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMiwgdGltZSwgdGltZTIsIGNvbG9yLmIsIG5ld0NvbG9yLmIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDMsIHRpbWUsIHRpbWUyLCBjb2xvci5hLCBuZXdDb2xvci5hLCAxKTtcblx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0XHR0aW1lID0gdGltZTI7XG5cdFx0XHRcdFx0XHRcdGNvbG9yID0gbmV3Q29sb3I7XG5cdFx0XHRcdFx0XHRcdGtleU1hcCA9IG5leHRNYXA7XG5cdFx0XHRcdFx0XHR9XG5cblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHRpbWVsaW5lKTtcblxuXHRcdFx0XHRcdH0gZWxzZSBpZiAodGltZWxpbmVOYW1lID09IFwicmdiXCIpIHtcblx0XHRcdFx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBSR0JUaW1lbGluZShmcmFtZXMsIGZyYW1lcyAqIDMsIHNsb3RJbmRleCk7XG5cdFx0XHRcdFx0XHRsZXQga2V5TWFwID0gdGltZWxpbmVNYXBbMF07XG5cdFx0XHRcdFx0XHRsZXQgdGltZSA9IGdldFZhbHVlKGtleU1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdFx0XHRcdFx0bGV0IGNvbG9yID0gQ29sb3IuZnJvbVN0cmluZyhrZXlNYXAuY29sb3IpO1xuXG5cdFx0XHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgY29sb3IuciwgY29sb3IuZywgY29sb3IuYik7XG5cdFx0XHRcdFx0XHRcdGxldCBuZXh0TWFwID0gdGltZWxpbmVNYXBbZnJhbWUgKyAxXTtcblx0XHRcdFx0XHRcdFx0aWYgKCFuZXh0TWFwKSB7XG5cdFx0XHRcdFx0XHRcdFx0dGltZWxpbmUuc2hyaW5rKGJlemllcik7XG5cdFx0XHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0bGV0IHRpbWUyID0gZ2V0VmFsdWUobmV4dE1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdFx0XHRcdFx0XHRsZXQgbmV3Q29sb3IgPSBDb2xvci5mcm9tU3RyaW5nKG5leHRNYXAuY29sb3IpO1xuXHRcdFx0XHRcdFx0XHRsZXQgY3VydmUgPSBrZXlNYXAuY3VydmU7XG5cdFx0XHRcdFx0XHRcdGlmIChjdXJ2ZSkge1xuXHRcdFx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCBjb2xvci5yLCBuZXdDb2xvci5yLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRiZXppZXIgPSByZWFkQ3VydmUoY3VydmUsIHRpbWVsaW5lLCBiZXppZXIsIGZyYW1lLCAxLCB0aW1lLCB0aW1lMiwgY29sb3IuZywgbmV3Q29sb3IuZywgMSk7XG5cdFx0XHRcdFx0XHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMiwgdGltZSwgdGltZTIsIGNvbG9yLmIsIG5ld0NvbG9yLmIsIDEpO1xuXHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdHRpbWUgPSB0aW1lMjtcblx0XHRcdFx0XHRcdFx0Y29sb3IgPSBuZXdDb2xvcjtcblx0XHRcdFx0XHRcdFx0a2V5TWFwID0gbmV4dE1hcDtcblx0XHRcdFx0XHRcdH1cblxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXG5cdFx0XHRcdFx0fSBlbHNlIGlmICh0aW1lbGluZU5hbWUgPT0gXCJhbHBoYVwiKSB7XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaChyZWFkVGltZWxpbmUxKHRpbWVsaW5lTWFwLCBuZXcgQWxwaGFUaW1lbGluZShmcmFtZXMsIGZyYW1lcywgc2xvdEluZGV4KSwgMCwgMSkpO1xuXHRcdFx0XHRcdH0gZWxzZSBpZiAodGltZWxpbmVOYW1lID09IFwicmdiYTJcIikge1xuXHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IFJHQkEyVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMgKiA3LCBzbG90SW5kZXgpO1xuXG5cdFx0XHRcdFx0XHRsZXQga2V5TWFwID0gdGltZWxpbmVNYXBbMF07XG5cdFx0XHRcdFx0XHRsZXQgdGltZSA9IGdldFZhbHVlKGtleU1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdFx0XHRcdFx0bGV0IGNvbG9yID0gQ29sb3IuZnJvbVN0cmluZyhrZXlNYXAubGlnaHQpO1xuXHRcdFx0XHRcdFx0bGV0IGNvbG9yMiA9IENvbG9yLmZyb21TdHJpbmcoa2V5TWFwLmRhcmspO1xuXG5cdFx0XHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgY29sb3IuciwgY29sb3IuZywgY29sb3IuYiwgY29sb3IuYSwgY29sb3IyLnIsIGNvbG9yMi5nLCBjb2xvcjIuYik7XG5cdFx0XHRcdFx0XHRcdGxldCBuZXh0TWFwID0gdGltZWxpbmVNYXBbZnJhbWUgKyAxXTtcblx0XHRcdFx0XHRcdFx0aWYgKCFuZXh0TWFwKSB7XG5cdFx0XHRcdFx0XHRcdFx0dGltZWxpbmUuc2hyaW5rKGJlemllcik7XG5cdFx0XHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0bGV0IHRpbWUyID0gZ2V0VmFsdWUobmV4dE1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdFx0XHRcdFx0XHRsZXQgbmV3Q29sb3IgPSBDb2xvci5mcm9tU3RyaW5nKG5leHRNYXAubGlnaHQpO1xuXHRcdFx0XHRcdFx0XHRsZXQgbmV3Q29sb3IyID0gQ29sb3IuZnJvbVN0cmluZyhuZXh0TWFwLmRhcmspO1xuXHRcdFx0XHRcdFx0XHRsZXQgY3VydmUgPSBrZXlNYXAuY3VydmU7XG5cdFx0XHRcdFx0XHRcdGlmIChjdXJ2ZSkge1xuXHRcdFx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCBjb2xvci5yLCBuZXdDb2xvci5yLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRiZXppZXIgPSByZWFkQ3VydmUoY3VydmUsIHRpbWVsaW5lLCBiZXppZXIsIGZyYW1lLCAxLCB0aW1lLCB0aW1lMiwgY29sb3IuZywgbmV3Q29sb3IuZywgMSk7XG5cdFx0XHRcdFx0XHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMiwgdGltZSwgdGltZTIsIGNvbG9yLmIsIG5ld0NvbG9yLmIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDMsIHRpbWUsIHRpbWUyLCBjb2xvci5hLCBuZXdDb2xvci5hLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRiZXppZXIgPSByZWFkQ3VydmUoY3VydmUsIHRpbWVsaW5lLCBiZXppZXIsIGZyYW1lLCA0LCB0aW1lLCB0aW1lMiwgY29sb3IyLnIsIG5ld0NvbG9yMi5yLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRiZXppZXIgPSByZWFkQ3VydmUoY3VydmUsIHRpbWVsaW5lLCBiZXppZXIsIGZyYW1lLCA1LCB0aW1lLCB0aW1lMiwgY29sb3IyLmcsIG5ld0NvbG9yMi5nLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRiZXppZXIgPSByZWFkQ3VydmUoY3VydmUsIHRpbWVsaW5lLCBiZXppZXIsIGZyYW1lLCA2LCB0aW1lLCB0aW1lMiwgY29sb3IyLmIsIG5ld0NvbG9yMi5iLCAxKTtcblx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0XHR0aW1lID0gdGltZTI7XG5cdFx0XHRcdFx0XHRcdGNvbG9yID0gbmV3Q29sb3I7XG5cdFx0XHRcdFx0XHRcdGNvbG9yMiA9IG5ld0NvbG9yMjtcblx0XHRcdFx0XHRcdFx0a2V5TWFwID0gbmV4dE1hcDtcblx0XHRcdFx0XHRcdH1cblxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXG5cdFx0XHRcdFx0fSBlbHNlIGlmICh0aW1lbGluZU5hbWUgPT0gXCJyZ2IyXCIpIHtcblx0XHRcdFx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBSR0IyVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMgKiA2LCBzbG90SW5kZXgpO1xuXG5cdFx0XHRcdFx0XHRsZXQga2V5TWFwID0gdGltZWxpbmVNYXBbMF07XG5cdFx0XHRcdFx0XHRsZXQgdGltZSA9IGdldFZhbHVlKGtleU1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdFx0XHRcdFx0bGV0IGNvbG9yID0gQ29sb3IuZnJvbVN0cmluZyhrZXlNYXAubGlnaHQpO1xuXHRcdFx0XHRcdFx0bGV0IGNvbG9yMiA9IENvbG9yLmZyb21TdHJpbmcoa2V5TWFwLmRhcmspO1xuXG5cdFx0XHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgY29sb3IuciwgY29sb3IuZywgY29sb3IuYiwgY29sb3IyLnIsIGNvbG9yMi5nLCBjb2xvcjIuYik7XG5cdFx0XHRcdFx0XHRcdGxldCBuZXh0TWFwID0gdGltZWxpbmVNYXBbZnJhbWUgKyAxXTtcblx0XHRcdFx0XHRcdFx0aWYgKCFuZXh0TWFwKSB7XG5cdFx0XHRcdFx0XHRcdFx0dGltZWxpbmUuc2hyaW5rKGJlemllcik7XG5cdFx0XHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0bGV0IHRpbWUyID0gZ2V0VmFsdWUobmV4dE1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdFx0XHRcdFx0XHRsZXQgbmV3Q29sb3IgPSBDb2xvci5mcm9tU3RyaW5nKG5leHRNYXAubGlnaHQpO1xuXHRcdFx0XHRcdFx0XHRsZXQgbmV3Q29sb3IyID0gQ29sb3IuZnJvbVN0cmluZyhuZXh0TWFwLmRhcmspO1xuXHRcdFx0XHRcdFx0XHRsZXQgY3VydmUgPSBrZXlNYXAuY3VydmU7XG5cdFx0XHRcdFx0XHRcdGlmIChjdXJ2ZSkge1xuXHRcdFx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCBjb2xvci5yLCBuZXdDb2xvci5yLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRiZXppZXIgPSByZWFkQ3VydmUoY3VydmUsIHRpbWVsaW5lLCBiZXppZXIsIGZyYW1lLCAxLCB0aW1lLCB0aW1lMiwgY29sb3IuZywgbmV3Q29sb3IuZywgMSk7XG5cdFx0XHRcdFx0XHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMiwgdGltZSwgdGltZTIsIGNvbG9yLmIsIG5ld0NvbG9yLmIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDMsIHRpbWUsIHRpbWUyLCBjb2xvcjIuciwgbmV3Q29sb3IyLnIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDQsIHRpbWUsIHRpbWUyLCBjb2xvcjIuZywgbmV3Q29sb3IyLmcsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDUsIHRpbWUsIHRpbWUyLCBjb2xvcjIuYiwgbmV3Q29sb3IyLmIsIDEpO1xuXHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdHRpbWUgPSB0aW1lMjtcblx0XHRcdFx0XHRcdFx0Y29sb3IgPSBuZXdDb2xvcjtcblx0XHRcdFx0XHRcdFx0Y29sb3IyID0gbmV3Q29sb3IyO1xuXHRcdFx0XHRcdFx0XHRrZXlNYXAgPSBuZXh0TWFwO1xuXHRcdFx0XHRcdFx0fVxuXG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0Ly8gQm9uZSB0aW1lbGluZXMuXG5cdFx0aWYgKG1hcC5ib25lcykge1xuXHRcdFx0Zm9yIChsZXQgYm9uZU5hbWUgaW4gbWFwLmJvbmVzKSB7XG5cdFx0XHRcdGxldCBib25lTWFwID0gbWFwLmJvbmVzW2JvbmVOYW1lXTtcblx0XHRcdFx0bGV0IGJvbmUgPSBza2VsZXRvbkRhdGEuZmluZEJvbmUoYm9uZU5hbWUpO1xuXHRcdFx0XHRpZiAoIWJvbmUpIHRocm93IG5ldyBFcnJvcihcIkJvbmUgbm90IGZvdW5kOiBcIiArIGJvbmVOYW1lKTtcblx0XHRcdFx0bGV0IGJvbmVJbmRleCA9IGJvbmUuaW5kZXg7XG5cdFx0XHRcdGZvciAobGV0IHRpbWVsaW5lTmFtZSBpbiBib25lTWFwKSB7XG5cdFx0XHRcdFx0bGV0IHRpbWVsaW5lTWFwID0gYm9uZU1hcFt0aW1lbGluZU5hbWVdO1xuXHRcdFx0XHRcdGxldCBmcmFtZXMgPSB0aW1lbGluZU1hcC5sZW5ndGg7XG5cdFx0XHRcdFx0aWYgKGZyYW1lcyA9PSAwKSBjb250aW51ZTtcblxuXHRcdFx0XHRcdGlmICh0aW1lbGluZU5hbWUgPT09IFwicm90YXRlXCIpIHtcblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHJlYWRUaW1lbGluZTEodGltZWxpbmVNYXAsIG5ldyBSb3RhdGVUaW1lbGluZShmcmFtZXMsIGZyYW1lcywgYm9uZUluZGV4KSwgMCwgMSkpO1xuXHRcdFx0XHRcdH0gZWxzZSBpZiAodGltZWxpbmVOYW1lID09PSBcInRyYW5zbGF0ZVwiKSB7XG5cdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgVHJhbnNsYXRlVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMgPDwgMSwgYm9uZUluZGV4KTtcblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHJlYWRUaW1lbGluZTIodGltZWxpbmVNYXAsIHRpbWVsaW5lLCBcInhcIiwgXCJ5XCIsIDAsIHNjYWxlKSk7XG5cdFx0XHRcdFx0fSBlbHNlIGlmICh0aW1lbGluZU5hbWUgPT09IFwidHJhbnNsYXRleFwiKSB7XG5cdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgVHJhbnNsYXRlWFRpbWVsaW5lKGZyYW1lcywgZnJhbWVzLCBib25lSW5kZXgpO1xuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMSh0aW1lbGluZU1hcCwgdGltZWxpbmUsIDAsIHNjYWxlKSk7XG5cdFx0XHRcdFx0fSBlbHNlIGlmICh0aW1lbGluZU5hbWUgPT09IFwidHJhbnNsYXRleVwiKSB7XG5cdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgVHJhbnNsYXRlWVRpbWVsaW5lKGZyYW1lcywgZnJhbWVzLCBib25lSW5kZXgpO1xuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMSh0aW1lbGluZU1hcCwgdGltZWxpbmUsIDAsIHNjYWxlKSk7XG5cdFx0XHRcdFx0fSBlbHNlIGlmICh0aW1lbGluZU5hbWUgPT09IFwic2NhbGVcIikge1xuXHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IFNjYWxlVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMgPDwgMSwgYm9uZUluZGV4KTtcblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHJlYWRUaW1lbGluZTIodGltZWxpbmVNYXAsIHRpbWVsaW5lLCBcInhcIiwgXCJ5XCIsIDEsIDEpKTtcblx0XHRcdFx0XHR9IGVsc2UgaWYgKHRpbWVsaW5lTmFtZSA9PT0gXCJzY2FsZXhcIikge1xuXHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IFNjYWxlWFRpbWVsaW5lKGZyYW1lcywgZnJhbWVzLCBib25lSW5kZXgpO1xuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMSh0aW1lbGluZU1hcCwgdGltZWxpbmUsIDEsIDEpKTtcblx0XHRcdFx0XHR9IGVsc2UgaWYgKHRpbWVsaW5lTmFtZSA9PT0gXCJzY2FsZXlcIikge1xuXHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IFNjYWxlWVRpbWVsaW5lKGZyYW1lcywgZnJhbWVzLCBib25lSW5kZXgpO1xuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMSh0aW1lbGluZU1hcCwgdGltZWxpbmUsIDEsIDEpKTtcblx0XHRcdFx0XHR9IGVsc2UgaWYgKHRpbWVsaW5lTmFtZSA9PT0gXCJzaGVhclwiKSB7XG5cdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgU2hlYXJUaW1lbGluZShmcmFtZXMsIGZyYW1lcyA8PCAxLCBib25lSW5kZXgpO1xuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMih0aW1lbGluZU1hcCwgdGltZWxpbmUsIFwieFwiLCBcInlcIiwgMCwgMSkpO1xuXHRcdFx0XHRcdH0gZWxzZSBpZiAodGltZWxpbmVOYW1lID09PSBcInNoZWFyeFwiKSB7XG5cdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgU2hlYXJYVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMsIGJvbmVJbmRleCk7XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaChyZWFkVGltZWxpbmUxKHRpbWVsaW5lTWFwLCB0aW1lbGluZSwgMCwgMSkpO1xuXHRcdFx0XHRcdH0gZWxzZSBpZiAodGltZWxpbmVOYW1lID09PSBcInNoZWFyeVwiKSB7XG5cdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgU2hlYXJZVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMsIGJvbmVJbmRleCk7XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaChyZWFkVGltZWxpbmUxKHRpbWVsaW5lTWFwLCB0aW1lbGluZSwgMCwgMSkpO1xuXHRcdFx0XHRcdH0gZWxzZSBpZiAodGltZWxpbmVOYW1lID09PSBcImluaGVyaXRcIikge1xuXHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IEluaGVyaXRUaW1lbGluZShmcmFtZXMsIGJvbmUuaW5kZXgpO1xuXHRcdFx0XHRcdFx0Zm9yIChsZXQgZnJhbWUgPSAwOyBmcmFtZSA8IHRpbWVsaW5lTWFwLmxlbmd0aDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHRsZXQgYUZyYW1lID0gdGltZWxpbmVNYXBbZnJhbWVdO1xuXHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgZ2V0VmFsdWUoYUZyYW1lLCBcInRpbWVcIiwgMCksIFV0aWxzLmVudW1WYWx1ZShJbmhlcml0LCBnZXRWYWx1ZShhRnJhbWUsIFwiaW5oZXJpdFwiLCBcIk5vcm1hbFwiKSkpO1xuXHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0fVxuXHRcdFx0fVxuXHRcdH1cblxuXHRcdC8vIElLIGNvbnN0cmFpbnQgdGltZWxpbmVzLlxuXHRcdGlmIChtYXAuaWspIHtcblx0XHRcdGZvciAobGV0IGNvbnN0cmFpbnROYW1lIGluIG1hcC5paykge1xuXHRcdFx0XHRsZXQgY29uc3RyYWludE1hcCA9IG1hcC5pa1tjb25zdHJhaW50TmFtZV07XG5cdFx0XHRcdGxldCBrZXlNYXAgPSBjb25zdHJhaW50TWFwWzBdO1xuXHRcdFx0XHRpZiAoIWtleU1hcCkgY29udGludWU7XG5cblx0XHRcdFx0bGV0IGNvbnN0cmFpbnQgPSBza2VsZXRvbkRhdGEuZmluZElrQ29uc3RyYWludChjb25zdHJhaW50TmFtZSk7XG5cdFx0XHRcdGlmICghY29uc3RyYWludCkgdGhyb3cgbmV3IEVycm9yKFwiSUsgQ29uc3RyYWludCBub3QgZm91bmQ6IFwiICsgY29uc3RyYWludE5hbWUpO1xuXHRcdFx0XHRsZXQgY29uc3RyYWludEluZGV4ID0gc2tlbGV0b25EYXRhLmlrQ29uc3RyYWludHMuaW5kZXhPZihjb25zdHJhaW50KTtcblx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IElrQ29uc3RyYWludFRpbWVsaW5lKGNvbnN0cmFpbnRNYXAubGVuZ3RoLCBjb25zdHJhaW50TWFwLmxlbmd0aCA8PCAxLCBjb25zdHJhaW50SW5kZXgpO1xuXG5cdFx0XHRcdGxldCB0aW1lID0gZ2V0VmFsdWUoa2V5TWFwLCBcInRpbWVcIiwgMCk7XG5cdFx0XHRcdGxldCBtaXggPSBnZXRWYWx1ZShrZXlNYXAsIFwibWl4XCIsIDEpO1xuXHRcdFx0XHRsZXQgc29mdG5lc3MgPSBnZXRWYWx1ZShrZXlNYXAsIFwic29mdG5lc3NcIiwgMCkgKiBzY2FsZTtcblxuXHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCB0aW1lLCBtaXgsIHNvZnRuZXNzLCBnZXRWYWx1ZShrZXlNYXAsIFwiYmVuZFBvc2l0aXZlXCIsIHRydWUpID8gMSA6IC0xLCBnZXRWYWx1ZShrZXlNYXAsIFwiY29tcHJlc3NcIiwgZmFsc2UpLCBnZXRWYWx1ZShrZXlNYXAsIFwic3RyZXRjaFwiLCBmYWxzZSkpO1xuXHRcdFx0XHRcdGxldCBuZXh0TWFwID0gY29uc3RyYWludE1hcFtmcmFtZSArIDFdO1xuXHRcdFx0XHRcdGlmICghbmV4dE1hcCkge1xuXHRcdFx0XHRcdFx0dGltZWxpbmUuc2hyaW5rKGJlemllcik7XG5cdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHR9XG5cblx0XHRcdFx0XHRsZXQgdGltZTIgPSBnZXRWYWx1ZShuZXh0TWFwLCBcInRpbWVcIiwgMCk7XG5cdFx0XHRcdFx0bGV0IG1peDIgPSBnZXRWYWx1ZShuZXh0TWFwLCBcIm1peFwiLCAxKTtcblx0XHRcdFx0XHRsZXQgc29mdG5lc3MyID0gZ2V0VmFsdWUobmV4dE1hcCwgXCJzb2Z0bmVzc1wiLCAwKSAqIHNjYWxlO1xuXHRcdFx0XHRcdGxldCBjdXJ2ZSA9IGtleU1hcC5jdXJ2ZTtcblx0XHRcdFx0XHRpZiAoY3VydmUpIHtcblx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCBtaXgsIG1peDIsIDEpO1xuXHRcdFx0XHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMSwgdGltZSwgdGltZTIsIHNvZnRuZXNzLCBzb2Z0bmVzczIsIHNjYWxlKTtcblx0XHRcdFx0XHR9XG5cblx0XHRcdFx0XHR0aW1lID0gdGltZTI7XG5cdFx0XHRcdFx0bWl4ID0gbWl4Mjtcblx0XHRcdFx0XHRzb2Z0bmVzcyA9IHNvZnRuZXNzMjtcblx0XHRcdFx0XHRrZXlNYXAgPSBuZXh0TWFwO1xuXHRcdFx0XHR9XG5cdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHRpbWVsaW5lKTtcblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBUcmFuc2Zvcm0gY29uc3RyYWludCB0aW1lbGluZXMuXG5cdFx0aWYgKG1hcC50cmFuc2Zvcm0pIHtcblx0XHRcdGZvciAobGV0IGNvbnN0cmFpbnROYW1lIGluIG1hcC50cmFuc2Zvcm0pIHtcblx0XHRcdFx0bGV0IHRpbWVsaW5lTWFwID0gbWFwLnRyYW5zZm9ybVtjb25zdHJhaW50TmFtZV07XG5cdFx0XHRcdGxldCBrZXlNYXAgPSB0aW1lbGluZU1hcFswXTtcblx0XHRcdFx0aWYgKCFrZXlNYXApIGNvbnRpbnVlO1xuXG5cdFx0XHRcdGxldCBjb25zdHJhaW50ID0gc2tlbGV0b25EYXRhLmZpbmRUcmFuc2Zvcm1Db25zdHJhaW50KGNvbnN0cmFpbnROYW1lKTtcblx0XHRcdFx0aWYgKCFjb25zdHJhaW50KSB0aHJvdyBuZXcgRXJyb3IoXCJUcmFuc2Zvcm0gY29uc3RyYWludCBub3QgZm91bmQ6IFwiICsgY29uc3RyYWludE5hbWUpO1xuXHRcdFx0XHRsZXQgY29uc3RyYWludEluZGV4ID0gc2tlbGV0b25EYXRhLnRyYW5zZm9ybUNvbnN0cmFpbnRzLmluZGV4T2YoY29uc3RyYWludCk7XG5cdFx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBUcmFuc2Zvcm1Db25zdHJhaW50VGltZWxpbmUodGltZWxpbmVNYXAubGVuZ3RoLCB0aW1lbGluZU1hcC5sZW5ndGggKiA2LCBjb25zdHJhaW50SW5kZXgpO1xuXG5cdFx0XHRcdGxldCB0aW1lID0gZ2V0VmFsdWUoa2V5TWFwLCBcInRpbWVcIiwgMCk7XG5cdFx0XHRcdGxldCBtaXhSb3RhdGUgPSBnZXRWYWx1ZShrZXlNYXAsIFwibWl4Um90YXRlXCIsIDEpO1xuXHRcdFx0XHRsZXQgbWl4WCA9IGdldFZhbHVlKGtleU1hcCwgXCJtaXhYXCIsIDEpO1xuXHRcdFx0XHRsZXQgbWl4WSA9IGdldFZhbHVlKGtleU1hcCwgXCJtaXhZXCIsIG1peFgpO1xuXHRcdFx0XHRsZXQgbWl4U2NhbGVYID0gZ2V0VmFsdWUoa2V5TWFwLCBcIm1peFNjYWxlWFwiLCAxKTtcblx0XHRcdFx0bGV0IG1peFNjYWxlWSA9IGdldFZhbHVlKGtleU1hcCwgXCJtaXhTY2FsZVlcIiwgbWl4U2NhbGVYKTtcblx0XHRcdFx0bGV0IG1peFNoZWFyWSA9IGdldFZhbHVlKGtleU1hcCwgXCJtaXhTaGVhcllcIiwgMSk7XG5cblx0XHRcdFx0Zm9yIChsZXQgZnJhbWUgPSAwLCBiZXppZXIgPSAwOyA7IGZyYW1lKyspIHtcblx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgbWl4Um90YXRlLCBtaXhYLCBtaXhZLCBtaXhTY2FsZVgsIG1peFNjYWxlWSwgbWl4U2hlYXJZKTtcblx0XHRcdFx0XHRsZXQgbmV4dE1hcCA9IHRpbWVsaW5lTWFwW2ZyYW1lICsgMV07XG5cdFx0XHRcdFx0aWYgKCFuZXh0TWFwKSB7XG5cdFx0XHRcdFx0XHR0aW1lbGluZS5zaHJpbmsoYmV6aWVyKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdH1cblxuXHRcdFx0XHRcdGxldCB0aW1lMiA9IGdldFZhbHVlKG5leHRNYXAsIFwidGltZVwiLCAwKTtcblx0XHRcdFx0XHRsZXQgbWl4Um90YXRlMiA9IGdldFZhbHVlKG5leHRNYXAsIFwibWl4Um90YXRlXCIsIDEpO1xuXHRcdFx0XHRcdGxldCBtaXhYMiA9IGdldFZhbHVlKG5leHRNYXAsIFwibWl4WFwiLCAxKTtcblx0XHRcdFx0XHRsZXQgbWl4WTIgPSBnZXRWYWx1ZShuZXh0TWFwLCBcIm1peFlcIiwgbWl4WDIpO1xuXHRcdFx0XHRcdGxldCBtaXhTY2FsZVgyID0gZ2V0VmFsdWUobmV4dE1hcCwgXCJtaXhTY2FsZVhcIiwgMSk7XG5cdFx0XHRcdFx0bGV0IG1peFNjYWxlWTIgPSBnZXRWYWx1ZShuZXh0TWFwLCBcIm1peFNjYWxlWVwiLCBtaXhTY2FsZVgyKTtcblx0XHRcdFx0XHRsZXQgbWl4U2hlYXJZMiA9IGdldFZhbHVlKG5leHRNYXAsIFwibWl4U2hlYXJZXCIsIDEpO1xuXHRcdFx0XHRcdGxldCBjdXJ2ZSA9IGtleU1hcC5jdXJ2ZTtcblx0XHRcdFx0XHRpZiAoY3VydmUpIHtcblx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCBtaXhSb3RhdGUsIG1peFJvdGF0ZTIsIDEpO1xuXHRcdFx0XHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMSwgdGltZSwgdGltZTIsIG1peFgsIG1peFgyLCAxKTtcblx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDIsIHRpbWUsIHRpbWUyLCBtaXhZLCBtaXhZMiwgMSk7XG5cdFx0XHRcdFx0XHRiZXppZXIgPSByZWFkQ3VydmUoY3VydmUsIHRpbWVsaW5lLCBiZXppZXIsIGZyYW1lLCAzLCB0aW1lLCB0aW1lMiwgbWl4U2NhbGVYLCBtaXhTY2FsZVgyLCAxKTtcblx0XHRcdFx0XHRcdGJlemllciA9IHJlYWRDdXJ2ZShjdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDQsIHRpbWUsIHRpbWUyLCBtaXhTY2FsZVksIG1peFNjYWxlWTIsIDEpO1xuXHRcdFx0XHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgNSwgdGltZSwgdGltZTIsIG1peFNoZWFyWSwgbWl4U2hlYXJZMiwgMSk7XG5cdFx0XHRcdFx0fVxuXG5cdFx0XHRcdFx0dGltZSA9IHRpbWUyO1xuXHRcdFx0XHRcdG1peFJvdGF0ZSA9IG1peFJvdGF0ZTI7XG5cdFx0XHRcdFx0bWl4WCA9IG1peFgyO1xuXHRcdFx0XHRcdG1peFkgPSBtaXhZMjtcblx0XHRcdFx0XHRtaXhTY2FsZVggPSBtaXhTY2FsZVgyO1xuXHRcdFx0XHRcdG1peFNjYWxlWSA9IG1peFNjYWxlWTI7XG5cdFx0XHRcdFx0bWl4U2NhbGVYID0gbWl4U2NhbGVYMjtcblx0XHRcdFx0XHRrZXlNYXAgPSBuZXh0TWFwO1xuXHRcdFx0XHR9XG5cdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHRpbWVsaW5lKTtcblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBQYXRoIGNvbnN0cmFpbnQgdGltZWxpbmVzLlxuXHRcdGlmIChtYXAucGF0aCkge1xuXHRcdFx0Zm9yIChsZXQgY29uc3RyYWludE5hbWUgaW4gbWFwLnBhdGgpIHtcblx0XHRcdFx0bGV0IGNvbnN0cmFpbnRNYXAgPSBtYXAucGF0aFtjb25zdHJhaW50TmFtZV07XG5cdFx0XHRcdGxldCBjb25zdHJhaW50ID0gc2tlbGV0b25EYXRhLmZpbmRQYXRoQ29uc3RyYWludChjb25zdHJhaW50TmFtZSk7XG5cdFx0XHRcdGlmICghY29uc3RyYWludCkgdGhyb3cgbmV3IEVycm9yKFwiUGF0aCBjb25zdHJhaW50IG5vdCBmb3VuZDogXCIgKyBjb25zdHJhaW50TmFtZSk7XG5cdFx0XHRcdGxldCBjb25zdHJhaW50SW5kZXggPSBza2VsZXRvbkRhdGEucGF0aENvbnN0cmFpbnRzLmluZGV4T2YoY29uc3RyYWludCk7XG5cdFx0XHRcdGZvciAobGV0IHRpbWVsaW5lTmFtZSBpbiBjb25zdHJhaW50TWFwKSB7XG5cdFx0XHRcdFx0bGV0IHRpbWVsaW5lTWFwID0gY29uc3RyYWludE1hcFt0aW1lbGluZU5hbWVdO1xuXHRcdFx0XHRcdGxldCBrZXlNYXAgPSB0aW1lbGluZU1hcFswXTtcblx0XHRcdFx0XHRpZiAoIWtleU1hcCkgY29udGludWU7XG5cblx0XHRcdFx0XHRsZXQgZnJhbWVzID0gdGltZWxpbmVNYXAubGVuZ3RoO1xuXHRcdFx0XHRcdGlmICh0aW1lbGluZU5hbWUgPT09IFwicG9zaXRpb25cIikge1xuXHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IFBhdGhDb25zdHJhaW50UG9zaXRpb25UaW1lbGluZShmcmFtZXMsIGZyYW1lcywgY29uc3RyYWludEluZGV4KTtcblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHJlYWRUaW1lbGluZTEodGltZWxpbmVNYXAsIHRpbWVsaW5lLCAwLCBjb25zdHJhaW50LnBvc2l0aW9uTW9kZSA9PSBQb3NpdGlvbk1vZGUuRml4ZWQgPyBzY2FsZSA6IDEpKTtcblx0XHRcdFx0XHR9IGVsc2UgaWYgKHRpbWVsaW5lTmFtZSA9PT0gXCJzcGFjaW5nXCIpIHtcblx0XHRcdFx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBQYXRoQ29uc3RyYWludFNwYWNpbmdUaW1lbGluZShmcmFtZXMsIGZyYW1lcywgY29uc3RyYWludEluZGV4KTtcblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHJlYWRUaW1lbGluZTEodGltZWxpbmVNYXAsIHRpbWVsaW5lLCAwLCBjb25zdHJhaW50LnNwYWNpbmdNb2RlID09IFNwYWNpbmdNb2RlLkxlbmd0aCB8fCBjb25zdHJhaW50LnNwYWNpbmdNb2RlID09IFNwYWNpbmdNb2RlLkZpeGVkID8gc2NhbGUgOiAxKSk7XG5cdFx0XHRcdFx0fSBlbHNlIGlmICh0aW1lbGluZU5hbWUgPT09IFwibWl4XCIpIHtcblx0XHRcdFx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBQYXRoQ29uc3RyYWludE1peFRpbWVsaW5lKGZyYW1lcywgZnJhbWVzICogMywgY29uc3RyYWludEluZGV4KTtcblx0XHRcdFx0XHRcdGxldCB0aW1lID0gZ2V0VmFsdWUoa2V5TWFwLCBcInRpbWVcIiwgMCk7XG5cdFx0XHRcdFx0XHRsZXQgbWl4Um90YXRlID0gZ2V0VmFsdWUoa2V5TWFwLCBcIm1peFJvdGF0ZVwiLCAxKTtcblx0XHRcdFx0XHRcdGxldCBtaXhYID0gZ2V0VmFsdWUoa2V5TWFwLCBcIm1peFhcIiwgMSk7XG5cdFx0XHRcdFx0XHRsZXQgbWl4WSA9IGdldFZhbHVlKGtleU1hcCwgXCJtaXhZXCIsIG1peFgpO1xuXHRcdFx0XHRcdFx0Zm9yIChsZXQgZnJhbWUgPSAwLCBiZXppZXIgPSAwOyA7IGZyYW1lKyspIHtcblx0XHRcdFx0XHRcdFx0dGltZWxpbmUuc2V0RnJhbWUoZnJhbWUsIHRpbWUsIG1peFJvdGF0ZSwgbWl4WCwgbWl4WSk7XG5cdFx0XHRcdFx0XHRcdGxldCBuZXh0TWFwID0gdGltZWxpbmVNYXBbZnJhbWUgKyAxXTtcblx0XHRcdFx0XHRcdFx0aWYgKCFuZXh0TWFwKSB7XG5cdFx0XHRcdFx0XHRcdFx0dGltZWxpbmUuc2hyaW5rKGJlemllcik7XG5cdFx0XHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0bGV0IHRpbWUyID0gZ2V0VmFsdWUobmV4dE1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdFx0XHRcdFx0XHRsZXQgbWl4Um90YXRlMiA9IGdldFZhbHVlKG5leHRNYXAsIFwibWl4Um90YXRlXCIsIDEpO1xuXHRcdFx0XHRcdFx0XHRsZXQgbWl4WDIgPSBnZXRWYWx1ZShuZXh0TWFwLCBcIm1peFhcIiwgMSk7XG5cdFx0XHRcdFx0XHRcdGxldCBtaXhZMiA9IGdldFZhbHVlKG5leHRNYXAsIFwibWl4WVwiLCBtaXhYMik7XG5cdFx0XHRcdFx0XHRcdGxldCBjdXJ2ZSA9IGtleU1hcC5jdXJ2ZTtcblx0XHRcdFx0XHRcdFx0aWYgKGN1cnZlKSB7XG5cdFx0XHRcdFx0XHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMCwgdGltZSwgdGltZTIsIG1peFJvdGF0ZSwgbWl4Um90YXRlMiwgMSk7XG5cdFx0XHRcdFx0XHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMSwgdGltZSwgdGltZTIsIG1peFgsIG1peFgyLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRiZXppZXIgPSByZWFkQ3VydmUoY3VydmUsIHRpbWVsaW5lLCBiZXppZXIsIGZyYW1lLCAyLCB0aW1lLCB0aW1lMiwgbWl4WSwgbWl4WTIsIDEpO1xuXHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdHRpbWUgPSB0aW1lMjtcblx0XHRcdFx0XHRcdFx0bWl4Um90YXRlID0gbWl4Um90YXRlMjtcblx0XHRcdFx0XHRcdFx0bWl4WCA9IG1peFgyO1xuXHRcdFx0XHRcdFx0XHRtaXhZID0gbWl4WTI7XG5cdFx0XHRcdFx0XHRcdGtleU1hcCA9IG5leHRNYXA7XG5cdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0Ly8gUGh5c2ljcyBjb25zdHJhaW50IHRpbWVsaW5lcy5cblx0XHRpZiAobWFwLnBoeXNpY3MpIHtcblx0XHRcdGZvciAobGV0IGNvbnN0cmFpbnROYW1lIGluIG1hcC5waHlzaWNzKSB7XG5cdFx0XHRcdGxldCBjb25zdHJhaW50TWFwID0gbWFwLnBoeXNpY3NbY29uc3RyYWludE5hbWVdO1xuXHRcdFx0XHRsZXQgY29uc3RyYWludEluZGV4ID0gLTE7XG5cdFx0XHRcdGlmIChjb25zdHJhaW50TmFtZS5sZW5ndGggPiAwKSB7XG5cdFx0XHRcdFx0bGV0IGNvbnN0cmFpbnQgPSBza2VsZXRvbkRhdGEuZmluZFBoeXNpY3NDb25zdHJhaW50KGNvbnN0cmFpbnROYW1lKTtcblx0XHRcdFx0XHRpZiAoIWNvbnN0cmFpbnQpIHRocm93IG5ldyBFcnJvcihcIlBoeXNpY3MgY29uc3RyYWludCBub3QgZm91bmQ6IFwiICsgY29uc3RyYWludE5hbWUpO1xuXHRcdFx0XHRcdGNvbnN0cmFpbnRJbmRleCA9IHNrZWxldG9uRGF0YS5waHlzaWNzQ29uc3RyYWludHMuaW5kZXhPZihjb25zdHJhaW50KTtcblx0XHRcdFx0fVxuXHRcdFx0XHRmb3IgKGxldCB0aW1lbGluZU5hbWUgaW4gY29uc3RyYWludE1hcCkge1xuXHRcdFx0XHRcdGxldCB0aW1lbGluZU1hcCA9IGNvbnN0cmFpbnRNYXBbdGltZWxpbmVOYW1lXTtcblx0XHRcdFx0XHRsZXQga2V5TWFwID0gdGltZWxpbmVNYXBbMF07XG5cdFx0XHRcdFx0aWYgKCFrZXlNYXApIGNvbnRpbnVlO1xuXG5cdFx0XHRcdFx0bGV0IGZyYW1lcyA9IHRpbWVsaW5lTWFwLmxlbmd0aDtcblx0XHRcdFx0XHRpZiAodGltZWxpbmVOYW1lID09IFwicmVzZXRcIikge1xuXHRcdFx0XHRcdFx0Y29uc3QgdGltZWxpbmUgPSBuZXcgUGh5c2ljc0NvbnN0cmFpbnRSZXNldFRpbWVsaW5lKGZyYW1lcywgY29uc3RyYWludEluZGV4KTtcblx0XHRcdFx0XHRcdGZvciAobGV0IGZyYW1lID0gMDsga2V5TWFwICE9IG51bGw7IGtleU1hcCA9IHRpbWVsaW5lTWFwW2ZyYW1lICsgMV0sIGZyYW1lKyspXG5cdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCBnZXRWYWx1ZShrZXlNYXAsIFwidGltZVwiLCAwKSk7XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0XHRcdFx0XHRjb250aW51ZTtcblx0XHRcdFx0XHR9XG5cblx0XHRcdFx0XHRsZXQgdGltZWxpbmU7XG5cdFx0XHRcdFx0aWYgKHRpbWVsaW5lTmFtZSA9PSBcImluZXJ0aWFcIilcblx0XHRcdFx0XHRcdHRpbWVsaW5lID0gbmV3IFBoeXNpY3NDb25zdHJhaW50SW5lcnRpYVRpbWVsaW5lKGZyYW1lcywgZnJhbWVzLCBjb25zdHJhaW50SW5kZXgpO1xuXHRcdFx0XHRcdGVsc2UgaWYgKHRpbWVsaW5lTmFtZSA9PSBcInN0cmVuZ3RoXCIpXG5cdFx0XHRcdFx0XHR0aW1lbGluZSA9IG5ldyBQaHlzaWNzQ29uc3RyYWludFN0cmVuZ3RoVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMsIGNvbnN0cmFpbnRJbmRleCk7XG5cdFx0XHRcdFx0ZWxzZSBpZiAodGltZWxpbmVOYW1lID09IFwiZGFtcGluZ1wiKVxuXHRcdFx0XHRcdFx0dGltZWxpbmUgPSBuZXcgUGh5c2ljc0NvbnN0cmFpbnREYW1waW5nVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMsIGNvbnN0cmFpbnRJbmRleCk7XG5cdFx0XHRcdFx0ZWxzZSBpZiAodGltZWxpbmVOYW1lID09IFwibWFzc1wiKVxuXHRcdFx0XHRcdFx0dGltZWxpbmUgPSBuZXcgUGh5c2ljc0NvbnN0cmFpbnRNYXNzVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMsIGNvbnN0cmFpbnRJbmRleCk7XG5cdFx0XHRcdFx0ZWxzZSBpZiAodGltZWxpbmVOYW1lID09IFwid2luZFwiKVxuXHRcdFx0XHRcdFx0dGltZWxpbmUgPSBuZXcgUGh5c2ljc0NvbnN0cmFpbnRXaW5kVGltZWxpbmUoZnJhbWVzLCBmcmFtZXMsIGNvbnN0cmFpbnRJbmRleCk7XG5cdFx0XHRcdFx0ZWxzZSBpZiAodGltZWxpbmVOYW1lID09IFwiZ3Jhdml0eVwiKVxuXHRcdFx0XHRcdFx0dGltZWxpbmUgPSBuZXcgUGh5c2ljc0NvbnN0cmFpbnRHcmF2aXR5VGltZWxpbmUoZnJhbWVzLCBmcmFtZXMsIGNvbnN0cmFpbnRJbmRleCk7XG5cdFx0XHRcdFx0ZWxzZSBpZiAodGltZWxpbmVOYW1lID09IFwibWl4XCIpIC8vXG5cdFx0XHRcdFx0XHR0aW1lbGluZSA9IG5ldyBQaHlzaWNzQ29uc3RyYWludE1peFRpbWVsaW5lKGZyYW1lcywgZnJhbWVzLCBjb25zdHJhaW50SW5kZXgpO1xuXHRcdFx0XHRcdGVsc2Vcblx0XHRcdFx0XHRcdGNvbnRpbnVlO1xuXHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHJlYWRUaW1lbGluZTEodGltZWxpbmVNYXAsIHRpbWVsaW5lLCAwLCAxKSk7XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBBdHRhY2htZW50IHRpbWVsaW5lcy5cblx0XHRpZiAobWFwLmF0dGFjaG1lbnRzKSB7XG5cdFx0XHRmb3IgKGxldCBhdHRhY2htZW50c05hbWUgaW4gbWFwLmF0dGFjaG1lbnRzKSB7XG5cdFx0XHRcdGxldCBhdHRhY2htZW50c01hcCA9IG1hcC5hdHRhY2htZW50c1thdHRhY2htZW50c05hbWVdO1xuXHRcdFx0XHRsZXQgc2tpbiA9IHNrZWxldG9uRGF0YS5maW5kU2tpbihhdHRhY2htZW50c05hbWUpO1xuXHRcdFx0XHRpZiAoIXNraW4pIHRocm93IG5ldyBFcnJvcihcIlNraW4gbm90IGZvdW5kOiBcIiArIGF0dGFjaG1lbnRzTmFtZSk7XG5cdFx0XHRcdGZvciAobGV0IHNsb3RNYXBOYW1lIGluIGF0dGFjaG1lbnRzTWFwKSB7XG5cdFx0XHRcdFx0bGV0IHNsb3RNYXAgPSBhdHRhY2htZW50c01hcFtzbG90TWFwTmFtZV07XG5cdFx0XHRcdFx0bGV0IHNsb3QgPSBza2VsZXRvbkRhdGEuZmluZFNsb3Qoc2xvdE1hcE5hbWUpO1xuXHRcdFx0XHRcdGlmICghc2xvdCkgdGhyb3cgbmV3IEVycm9yKFwiU2xvdCBub3QgZm91bmQ6IFwiICsgc2xvdE1hcE5hbWUpO1xuXHRcdFx0XHRcdGxldCBzbG90SW5kZXggPSBzbG90LmluZGV4O1xuXHRcdFx0XHRcdGZvciAobGV0IGF0dGFjaG1lbnRNYXBOYW1lIGluIHNsb3RNYXApIHtcblx0XHRcdFx0XHRcdGxldCBhdHRhY2htZW50TWFwID0gc2xvdE1hcFthdHRhY2htZW50TWFwTmFtZV07XG5cdFx0XHRcdFx0XHRsZXQgYXR0YWNobWVudCA9IDxWZXJ0ZXhBdHRhY2htZW50PnNraW4uZ2V0QXR0YWNobWVudChzbG90SW5kZXgsIGF0dGFjaG1lbnRNYXBOYW1lKTtcblxuXHRcdFx0XHRcdFx0Zm9yIChsZXQgdGltZWxpbmVNYXBOYW1lIGluIGF0dGFjaG1lbnRNYXApIHtcblx0XHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lTWFwID0gYXR0YWNobWVudE1hcFt0aW1lbGluZU1hcE5hbWVdO1xuXHRcdFx0XHRcdFx0XHRsZXQga2V5TWFwID0gdGltZWxpbmVNYXBbMF07XG5cdFx0XHRcdFx0XHRcdGlmICgha2V5TWFwKSBjb250aW51ZTtcblxuXHRcdFx0XHRcdFx0XHRpZiAodGltZWxpbmVNYXBOYW1lID09IFwiZGVmb3JtXCIpIHtcblx0XHRcdFx0XHRcdFx0XHRsZXQgd2VpZ2h0ZWQgPSBhdHRhY2htZW50LmJvbmVzO1xuXHRcdFx0XHRcdFx0XHRcdGxldCB2ZXJ0aWNlcyA9IGF0dGFjaG1lbnQudmVydGljZXM7XG5cdFx0XHRcdFx0XHRcdFx0bGV0IGRlZm9ybUxlbmd0aCA9IHdlaWdodGVkID8gdmVydGljZXMubGVuZ3RoIC8gMyAqIDIgOiB2ZXJ0aWNlcy5sZW5ndGg7XG5cblx0XHRcdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgRGVmb3JtVGltZWxpbmUodGltZWxpbmVNYXAubGVuZ3RoLCB0aW1lbGluZU1hcC5sZW5ndGgsIHNsb3RJbmRleCwgYXR0YWNobWVudCk7XG5cdFx0XHRcdFx0XHRcdFx0bGV0IHRpbWUgPSBnZXRWYWx1ZShrZXlNYXAsIFwidGltZVwiLCAwKTtcblx0XHRcdFx0XHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHRcdFx0bGV0IGRlZm9ybTogTnVtYmVyQXJyYXlMaWtlO1xuXHRcdFx0XHRcdFx0XHRcdFx0bGV0IHZlcnRpY2VzVmFsdWU6IEFycmF5PE51bWJlcj4gPSBnZXRWYWx1ZShrZXlNYXAsIFwidmVydGljZXNcIiwgbnVsbCk7XG5cdFx0XHRcdFx0XHRcdFx0XHRpZiAoIXZlcnRpY2VzVmFsdWUpXG5cdFx0XHRcdFx0XHRcdFx0XHRcdGRlZm9ybSA9IHdlaWdodGVkID8gVXRpbHMubmV3RmxvYXRBcnJheShkZWZvcm1MZW5ndGgpIDogdmVydGljZXM7XG5cdFx0XHRcdFx0XHRcdFx0XHRlbHNlIHtcblx0XHRcdFx0XHRcdFx0XHRcdFx0ZGVmb3JtID0gVXRpbHMubmV3RmxvYXRBcnJheShkZWZvcm1MZW5ndGgpO1xuXHRcdFx0XHRcdFx0XHRcdFx0XHRsZXQgc3RhcnQgPSA8bnVtYmVyPmdldFZhbHVlKGtleU1hcCwgXCJvZmZzZXRcIiwgMCk7XG5cdFx0XHRcdFx0XHRcdFx0XHRcdFV0aWxzLmFycmF5Q29weSh2ZXJ0aWNlc1ZhbHVlLCAwLCBkZWZvcm0sIHN0YXJ0LCB2ZXJ0aWNlc1ZhbHVlLmxlbmd0aCk7XG5cdFx0XHRcdFx0XHRcdFx0XHRcdGlmIChzY2FsZSAhPSAxKSB7XG5cdFx0XHRcdFx0XHRcdFx0XHRcdFx0Zm9yIChsZXQgaSA9IHN0YXJ0LCBuID0gaSArIHZlcnRpY2VzVmFsdWUubGVuZ3RoOyBpIDwgbjsgaSsrKVxuXHRcdFx0XHRcdFx0XHRcdFx0XHRcdFx0ZGVmb3JtW2ldICo9IHNjYWxlO1xuXHRcdFx0XHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdFx0XHRcdGlmICghd2VpZ2h0ZWQpIHtcblx0XHRcdFx0XHRcdFx0XHRcdFx0XHRmb3IgKGxldCBpID0gMDsgaSA8IGRlZm9ybUxlbmd0aDsgaSsrKVxuXHRcdFx0XHRcdFx0XHRcdFx0XHRcdFx0ZGVmb3JtW2ldICs9IHZlcnRpY2VzW2ldO1xuXHRcdFx0XHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdFx0XHR9XG5cblx0XHRcdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCB0aW1lLCBkZWZvcm0pO1xuXHRcdFx0XHRcdFx0XHRcdFx0bGV0IG5leHRNYXAgPSB0aW1lbGluZU1hcFtmcmFtZSArIDFdO1xuXHRcdFx0XHRcdFx0XHRcdFx0aWYgKCFuZXh0TWFwKSB7XG5cdFx0XHRcdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNocmluayhiZXppZXIpO1xuXHRcdFx0XHRcdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0XHRcdGxldCB0aW1lMiA9IGdldFZhbHVlKG5leHRNYXAsIFwidGltZVwiLCAwKTtcblx0XHRcdFx0XHRcdFx0XHRcdGxldCBjdXJ2ZSA9IGtleU1hcC5jdXJ2ZTtcblx0XHRcdFx0XHRcdFx0XHRcdGlmIChjdXJ2ZSkgYmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMCwgdGltZSwgdGltZTIsIDAsIDEsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdFx0dGltZSA9IHRpbWUyO1xuXHRcdFx0XHRcdFx0XHRcdFx0a2V5TWFwID0gbmV4dE1hcDtcblx0XHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXHRcdFx0XHRcdFx0XHR9IGVsc2UgaWYgKHRpbWVsaW5lTWFwTmFtZSA9PSBcInNlcXVlbmNlXCIpIHtcblx0XHRcdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgU2VxdWVuY2VUaW1lbGluZSh0aW1lbGluZU1hcC5sZW5ndGgsIHNsb3RJbmRleCwgYXR0YWNobWVudCBhcyB1bmtub3duIGFzIEhhc1RleHR1cmVSZWdpb24pO1xuXHRcdFx0XHRcdFx0XHRcdGxldCBsYXN0RGVsYXkgPSAwO1xuXHRcdFx0XHRcdFx0XHRcdGZvciAobGV0IGZyYW1lID0gMDsgZnJhbWUgPCB0aW1lbGluZU1hcC5sZW5ndGg7IGZyYW1lKyspIHtcblx0XHRcdFx0XHRcdFx0XHRcdGxldCBkZWxheSA9IGdldFZhbHVlKGtleU1hcCwgXCJkZWxheVwiLCBsYXN0RGVsYXkpO1xuXHRcdFx0XHRcdFx0XHRcdFx0bGV0IHRpbWUgPSBnZXRWYWx1ZShrZXlNYXAsIFwidGltZVwiLCAwKTtcblx0XHRcdFx0XHRcdFx0XHRcdGxldCBtb2RlID0gU2VxdWVuY2VNb2RlW2dldFZhbHVlKGtleU1hcCwgXCJtb2RlXCIsIFwiaG9sZFwiKV0gYXMgdW5rbm93biBhcyBudW1iZXI7XG5cdFx0XHRcdFx0XHRcdFx0XHRsZXQgaW5kZXggPSBnZXRWYWx1ZShrZXlNYXAsIFwiaW5kZXhcIiwgMCk7XG5cdFx0XHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgbW9kZSwgaW5kZXgsIGRlbGF5KTtcblx0XHRcdFx0XHRcdFx0XHRcdGxhc3REZWxheSA9IGRlbGF5O1xuXHRcdFx0XHRcdFx0XHRcdFx0a2V5TWFwID0gdGltZWxpbmVNYXBbZnJhbWUgKyAxXTtcblx0XHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0Ly8gRHJhdyBvcmRlciB0aW1lbGluZXMuXG5cdFx0aWYgKG1hcC5kcmF3T3JkZXIpIHtcblx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBEcmF3T3JkZXJUaW1lbGluZShtYXAuZHJhd09yZGVyLmxlbmd0aCk7XG5cdFx0XHRsZXQgc2xvdENvdW50ID0gc2tlbGV0b25EYXRhLnNsb3RzLmxlbmd0aDtcblx0XHRcdGxldCBmcmFtZSA9IDA7XG5cdFx0XHRmb3IgKGxldCBpID0gMDsgaSA8IG1hcC5kcmF3T3JkZXIubGVuZ3RoOyBpKyssIGZyYW1lKyspIHtcblx0XHRcdFx0bGV0IGRyYXdPcmRlck1hcCA9IG1hcC5kcmF3T3JkZXJbaV07XG5cdFx0XHRcdGxldCBkcmF3T3JkZXI6IEFycmF5PG51bWJlcj4gfCBudWxsID0gbnVsbDtcblx0XHRcdFx0bGV0IG9mZnNldHMgPSBnZXRWYWx1ZShkcmF3T3JkZXJNYXAsIFwib2Zmc2V0c1wiLCBudWxsKTtcblx0XHRcdFx0aWYgKG9mZnNldHMpIHtcblx0XHRcdFx0XHRkcmF3T3JkZXIgPSBVdGlscy5uZXdBcnJheTxudW1iZXI+KHNsb3RDb3VudCwgLTEpO1xuXHRcdFx0XHRcdGxldCB1bmNoYW5nZWQgPSBVdGlscy5uZXdBcnJheTxudW1iZXI+KHNsb3RDb3VudCAtIG9mZnNldHMubGVuZ3RoLCAwKTtcblx0XHRcdFx0XHRsZXQgb3JpZ2luYWxJbmRleCA9IDAsIHVuY2hhbmdlZEluZGV4ID0gMDtcblx0XHRcdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgb2Zmc2V0cy5sZW5ndGg7IGlpKyspIHtcblx0XHRcdFx0XHRcdGxldCBvZmZzZXRNYXAgPSBvZmZzZXRzW2lpXTtcblx0XHRcdFx0XHRcdGxldCBzbG90ID0gc2tlbGV0b25EYXRhLmZpbmRTbG90KG9mZnNldE1hcC5zbG90KTtcblx0XHRcdFx0XHRcdGlmICghc2xvdCkgdGhyb3cgbmV3IEVycm9yKFwiU2xvdCBub3QgZm91bmQ6IFwiICsgc2xvdCk7XG5cdFx0XHRcdFx0XHRsZXQgc2xvdEluZGV4ID0gc2xvdC5pbmRleDtcblx0XHRcdFx0XHRcdC8vIENvbGxlY3QgdW5jaGFuZ2VkIGl0ZW1zLlxuXHRcdFx0XHRcdFx0d2hpbGUgKG9yaWdpbmFsSW5kZXggIT0gc2xvdEluZGV4KVxuXHRcdFx0XHRcdFx0XHR1bmNoYW5nZWRbdW5jaGFuZ2VkSW5kZXgrK10gPSBvcmlnaW5hbEluZGV4Kys7XG5cdFx0XHRcdFx0XHQvLyBTZXQgY2hhbmdlZCBpdGVtcy5cblx0XHRcdFx0XHRcdGRyYXdPcmRlcltvcmlnaW5hbEluZGV4ICsgb2Zmc2V0TWFwLm9mZnNldF0gPSBvcmlnaW5hbEluZGV4Kys7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHRcdC8vIENvbGxlY3QgcmVtYWluaW5nIHVuY2hhbmdlZCBpdGVtcy5cblx0XHRcdFx0XHR3aGlsZSAob3JpZ2luYWxJbmRleCA8IHNsb3RDb3VudClcblx0XHRcdFx0XHRcdHVuY2hhbmdlZFt1bmNoYW5nZWRJbmRleCsrXSA9IG9yaWdpbmFsSW5kZXgrKztcblx0XHRcdFx0XHQvLyBGaWxsIGluIHVuY2hhbmdlZCBpdGVtcy5cblx0XHRcdFx0XHRmb3IgKGxldCBpaSA9IHNsb3RDb3VudCAtIDE7IGlpID49IDA7IGlpLS0pXG5cdFx0XHRcdFx0XHRpZiAoZHJhd09yZGVyW2lpXSA9PSAtMSkgZHJhd09yZGVyW2lpXSA9IHVuY2hhbmdlZFstLXVuY2hhbmdlZEluZGV4XTtcblx0XHRcdFx0fVxuXHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgZ2V0VmFsdWUoZHJhd09yZGVyTWFwLCBcInRpbWVcIiwgMCksIGRyYXdPcmRlcik7XG5cdFx0XHR9XG5cdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0fVxuXG5cdFx0Ly8gRXZlbnQgdGltZWxpbmVzLlxuXHRcdGlmIChtYXAuZXZlbnRzKSB7XG5cdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgRXZlbnRUaW1lbGluZShtYXAuZXZlbnRzLmxlbmd0aCk7XG5cdFx0XHRsZXQgZnJhbWUgPSAwO1xuXHRcdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBtYXAuZXZlbnRzLmxlbmd0aDsgaSsrLCBmcmFtZSsrKSB7XG5cdFx0XHRcdGxldCBldmVudE1hcCA9IG1hcC5ldmVudHNbaV07XG5cdFx0XHRcdGxldCBldmVudERhdGEgPSBza2VsZXRvbkRhdGEuZmluZEV2ZW50KGV2ZW50TWFwLm5hbWUpO1xuXHRcdFx0XHRpZiAoIWV2ZW50RGF0YSkgdGhyb3cgbmV3IEVycm9yKFwiRXZlbnQgbm90IGZvdW5kOiBcIiArIGV2ZW50TWFwLm5hbWUpO1xuXHRcdFx0XHRsZXQgZXZlbnQgPSBuZXcgRXZlbnQoVXRpbHMudG9TaW5nbGVQcmVjaXNpb24oZ2V0VmFsdWUoZXZlbnRNYXAsIFwidGltZVwiLCAwKSksIGV2ZW50RGF0YSk7XG5cdFx0XHRcdGV2ZW50LmludFZhbHVlID0gZ2V0VmFsdWUoZXZlbnRNYXAsIFwiaW50XCIsIGV2ZW50RGF0YS5pbnRWYWx1ZSk7XG5cdFx0XHRcdGV2ZW50LmZsb2F0VmFsdWUgPSBnZXRWYWx1ZShldmVudE1hcCwgXCJmbG9hdFwiLCBldmVudERhdGEuZmxvYXRWYWx1ZSk7XG5cdFx0XHRcdGV2ZW50LnN0cmluZ1ZhbHVlID0gZ2V0VmFsdWUoZXZlbnRNYXAsIFwic3RyaW5nXCIsIGV2ZW50RGF0YS5zdHJpbmdWYWx1ZSk7XG5cdFx0XHRcdGlmIChldmVudC5kYXRhLmF1ZGlvUGF0aCkge1xuXHRcdFx0XHRcdGV2ZW50LnZvbHVtZSA9IGdldFZhbHVlKGV2ZW50TWFwLCBcInZvbHVtZVwiLCAxKTtcblx0XHRcdFx0XHRldmVudC5iYWxhbmNlID0gZ2V0VmFsdWUoZXZlbnRNYXAsIFwiYmFsYW5jZVwiLCAwKTtcblx0XHRcdFx0fVxuXHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgZXZlbnQpO1xuXHRcdFx0fVxuXHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXHRcdH1cblxuXHRcdGxldCBkdXJhdGlvbiA9IDA7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSB0aW1lbGluZXMubGVuZ3RoOyBpIDwgbjsgaSsrKVxuXHRcdFx0ZHVyYXRpb24gPSBNYXRoLm1heChkdXJhdGlvbiwgdGltZWxpbmVzW2ldLmdldER1cmF0aW9uKCkpO1xuXHRcdHNrZWxldG9uRGF0YS5hbmltYXRpb25zLnB1c2gobmV3IEFuaW1hdGlvbihuYW1lLCB0aW1lbGluZXMsIGR1cmF0aW9uKSk7XG5cdH1cbn1cblxuY2xhc3MgTGlua2VkTWVzaCB7XG5cdHBhcmVudDogc3RyaW5nOyBza2luOiBzdHJpbmc7XG5cdHNsb3RJbmRleDogbnVtYmVyO1xuXHRtZXNoOiBNZXNoQXR0YWNobWVudDtcblx0aW5oZXJpdFRpbWVsaW5lOiBib29sZWFuO1xuXG5cdGNvbnN0cnVjdG9yIChtZXNoOiBNZXNoQXR0YWNobWVudCwgc2tpbjogc3RyaW5nLCBzbG90SW5kZXg6IG51bWJlciwgcGFyZW50OiBzdHJpbmcsIGluaGVyaXREZWZvcm06IGJvb2xlYW4pIHtcblx0XHR0aGlzLm1lc2ggPSBtZXNoO1xuXHRcdHRoaXMuc2tpbiA9IHNraW47XG5cdFx0dGhpcy5zbG90SW5kZXggPSBzbG90SW5kZXg7XG5cdFx0dGhpcy5wYXJlbnQgPSBwYXJlbnQ7XG5cdFx0dGhpcy5pbmhlcml0VGltZWxpbmUgPSBpbmhlcml0RGVmb3JtO1xuXHR9XG59XG5cbmZ1bmN0aW9uIHJlYWRUaW1lbGluZTEgKGtleXM6IGFueVtdLCB0aW1lbGluZTogQ3VydmVUaW1lbGluZTEsIGRlZmF1bHRWYWx1ZTogbnVtYmVyLCBzY2FsZTogbnVtYmVyKSB7XG5cdGxldCBrZXlNYXAgPSBrZXlzWzBdO1xuXHRsZXQgdGltZSA9IGdldFZhbHVlKGtleU1hcCwgXCJ0aW1lXCIsIDApO1xuXHRsZXQgdmFsdWUgPSBnZXRWYWx1ZShrZXlNYXAsIFwidmFsdWVcIiwgZGVmYXVsdFZhbHVlKSAqIHNjYWxlO1xuXHRsZXQgYmV6aWVyID0gMDtcblx0Zm9yIChsZXQgZnJhbWUgPSAwOyA7IGZyYW1lKyspIHtcblx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgdmFsdWUpO1xuXHRcdGxldCBuZXh0TWFwID0ga2V5c1tmcmFtZSArIDFdO1xuXHRcdGlmICghbmV4dE1hcCkge1xuXHRcdFx0dGltZWxpbmUuc2hyaW5rKGJlemllcik7XG5cdFx0XHRyZXR1cm4gdGltZWxpbmU7XG5cdFx0fVxuXHRcdGxldCB0aW1lMiA9IGdldFZhbHVlKG5leHRNYXAsIFwidGltZVwiLCAwKTtcblx0XHRsZXQgdmFsdWUyID0gZ2V0VmFsdWUobmV4dE1hcCwgXCJ2YWx1ZVwiLCBkZWZhdWx0VmFsdWUpICogc2NhbGU7XG5cdFx0aWYgKGtleU1hcC5jdXJ2ZSkgYmV6aWVyID0gcmVhZEN1cnZlKGtleU1hcC5jdXJ2ZSwgdGltZWxpbmUsIGJlemllciwgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCB2YWx1ZSwgdmFsdWUyLCBzY2FsZSk7XG5cdFx0dGltZSA9IHRpbWUyO1xuXHRcdHZhbHVlID0gdmFsdWUyO1xuXHRcdGtleU1hcCA9IG5leHRNYXA7XG5cdH1cbn1cblxuZnVuY3Rpb24gcmVhZFRpbWVsaW5lMiAoa2V5czogYW55W10sIHRpbWVsaW5lOiBDdXJ2ZVRpbWVsaW5lMiwgbmFtZTE6IHN0cmluZywgbmFtZTI6IHN0cmluZywgZGVmYXVsdFZhbHVlOiBudW1iZXIsIHNjYWxlOiBudW1iZXIpIHtcblx0bGV0IGtleU1hcCA9IGtleXNbMF07XG5cdGxldCB0aW1lID0gZ2V0VmFsdWUoa2V5TWFwLCBcInRpbWVcIiwgMCk7XG5cdGxldCB2YWx1ZTEgPSBnZXRWYWx1ZShrZXlNYXAsIG5hbWUxLCBkZWZhdWx0VmFsdWUpICogc2NhbGU7XG5cdGxldCB2YWx1ZTIgPSBnZXRWYWx1ZShrZXlNYXAsIG5hbWUyLCBkZWZhdWx0VmFsdWUpICogc2NhbGU7XG5cdGxldCBiZXppZXIgPSAwO1xuXHRmb3IgKGxldCBmcmFtZSA9IDA7IDsgZnJhbWUrKykge1xuXHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCB0aW1lLCB2YWx1ZTEsIHZhbHVlMik7XG5cdFx0bGV0IG5leHRNYXAgPSBrZXlzW2ZyYW1lICsgMV07XG5cdFx0aWYgKCFuZXh0TWFwKSB7XG5cdFx0XHR0aW1lbGluZS5zaHJpbmsoYmV6aWVyKTtcblx0XHRcdHJldHVybiB0aW1lbGluZTtcblx0XHR9XG5cdFx0bGV0IHRpbWUyID0gZ2V0VmFsdWUobmV4dE1hcCwgXCJ0aW1lXCIsIDApO1xuXHRcdGxldCBudmFsdWUxID0gZ2V0VmFsdWUobmV4dE1hcCwgbmFtZTEsIGRlZmF1bHRWYWx1ZSkgKiBzY2FsZTtcblx0XHRsZXQgbnZhbHVlMiA9IGdldFZhbHVlKG5leHRNYXAsIG5hbWUyLCBkZWZhdWx0VmFsdWUpICogc2NhbGU7XG5cdFx0bGV0IGN1cnZlID0ga2V5TWFwLmN1cnZlO1xuXHRcdGlmIChjdXJ2ZSkge1xuXHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMCwgdGltZSwgdGltZTIsIHZhbHVlMSwgbnZhbHVlMSwgc2NhbGUpO1xuXHRcdFx0YmV6aWVyID0gcmVhZEN1cnZlKGN1cnZlLCB0aW1lbGluZSwgYmV6aWVyLCBmcmFtZSwgMSwgdGltZSwgdGltZTIsIHZhbHVlMiwgbnZhbHVlMiwgc2NhbGUpO1xuXHRcdH1cblx0XHR0aW1lID0gdGltZTI7XG5cdFx0dmFsdWUxID0gbnZhbHVlMTtcblx0XHR2YWx1ZTIgPSBudmFsdWUyO1xuXHRcdGtleU1hcCA9IG5leHRNYXA7XG5cdH1cbn1cblxuZnVuY3Rpb24gcmVhZEN1cnZlIChjdXJ2ZTogYW55LCB0aW1lbGluZTogQ3VydmVUaW1lbGluZSwgYmV6aWVyOiBudW1iZXIsIGZyYW1lOiBudW1iZXIsIHZhbHVlOiBudW1iZXIsIHRpbWUxOiBudW1iZXIsIHRpbWUyOiBudW1iZXIsXG5cdHZhbHVlMTogbnVtYmVyLCB2YWx1ZTI6IG51bWJlciwgc2NhbGU6IG51bWJlcikge1xuXHRpZiAoY3VydmUgPT0gXCJzdGVwcGVkXCIpIHtcblx0XHR0aW1lbGluZS5zZXRTdGVwcGVkKGZyYW1lKTtcblx0XHRyZXR1cm4gYmV6aWVyO1xuXHR9XG5cdGxldCBpID0gdmFsdWUgPDwgMjtcblx0bGV0IGN4MSA9IGN1cnZlW2ldO1xuXHRsZXQgY3kxID0gY3VydmVbaSArIDFdICogc2NhbGU7XG5cdGxldCBjeDIgPSBjdXJ2ZVtpICsgMl07XG5cdGxldCBjeTIgPSBjdXJ2ZVtpICsgM10gKiBzY2FsZTtcblx0dGltZWxpbmUuc2V0QmV6aWVyKGJlemllciwgZnJhbWUsIHZhbHVlLCB0aW1lMSwgdmFsdWUxLCBjeDEsIGN5MSwgY3gyLCBjeTIsIHRpbWUyLCB2YWx1ZTIpO1xuXHRyZXR1cm4gYmV6aWVyICsgMTtcbn1cblxuZnVuY3Rpb24gZ2V0VmFsdWUgKG1hcDogYW55LCBwcm9wZXJ0eTogc3RyaW5nLCBkZWZhdWx0VmFsdWU6IGFueSkge1xuXHRyZXR1cm4gbWFwW3Byb3BlcnR5XSAhPT0gdW5kZWZpbmVkID8gbWFwW3Byb3BlcnR5XSA6IGRlZmF1bHRWYWx1ZTtcbn1cbiJdfQ==