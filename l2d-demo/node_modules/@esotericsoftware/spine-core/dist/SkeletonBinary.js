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
import { Animation, InheritTimeline, AttachmentTimeline, RGBATimeline, RGBTimeline, RGBA2Timeline, RGB2Timeline, AlphaTimeline, RotateTimeline, TranslateTimeline, TranslateXTimeline, TranslateYTimeline, ScaleTimeline, ScaleXTimeline, ScaleYTimeline, ShearTimeline, ShearXTimeline, ShearYTimeline, IkConstraintTimeline, TransformConstraintTimeline, PathConstraintPositionTimeline, PathConstraintSpacingTimeline, PathConstraintMixTimeline, DeformTimeline, DrawOrderTimeline, EventTimeline, SequenceTimeline, PhysicsConstraintResetTimeline, PhysicsConstraintInertiaTimeline, PhysicsConstraintStrengthTimeline, PhysicsConstraintDampingTimeline, PhysicsConstraintMassTimeline, PhysicsConstraintWindTimeline, PhysicsConstraintGravityTimeline, PhysicsConstraintMixTimeline } from "./Animation.js";
import { Sequence, SequenceModeValues } from "./attachments/Sequence.js";
import { BoneData } from "./BoneData.js";
import { Event } from "./Event.js";
import { EventData } from "./EventData.js";
import { IkConstraintData } from "./IkConstraintData.js";
import { PathConstraintData, PositionMode, SpacingMode } from "./PathConstraintData.js";
import { PhysicsConstraintData } from "./PhysicsConstraintData.js";
import { SkeletonData } from "./SkeletonData.js";
import { Skin } from "./Skin.js";
import { SlotData } from "./SlotData.js";
import { TransformConstraintData } from "./TransformConstraintData.js";
import { Color, Utils } from "./Utils.js";
/** Loads skeleton data in the Spine binary format.
 *
 * See [Spine binary format](http://esotericsoftware.com/spine-binary-format) and
 * [JSON and binary data](http://esotericsoftware.com/spine-loading-skeleton-data#JSON-and-binary-data) in the Spine
 * Runtimes Guide. */
export class SkeletonBinary {
    /** Scales bone positions, image sizes, and translations as they are loaded. This allows different size images to be used at
     * runtime than were used in Spine.
     *
     * See [Scaling](http://esotericsoftware.com/spine-loading-skeleton-data#Scaling) in the Spine Runtimes Guide. */
    scale = 1;
    attachmentLoader;
    linkedMeshes = new Array();
    constructor(attachmentLoader) {
        this.attachmentLoader = attachmentLoader;
    }
    readSkeletonData(binary) {
        let scale = this.scale;
        let skeletonData = new SkeletonData();
        skeletonData.name = ""; // BOZO
        let input = new BinaryInput(binary);
        let lowHash = input.readInt32();
        let highHash = input.readInt32();
        skeletonData.hash = highHash == 0 && lowHash == 0 ? null : highHash.toString(16) + lowHash.toString(16);
        skeletonData.version = input.readString();
        skeletonData.x = input.readFloat();
        skeletonData.y = input.readFloat();
        skeletonData.width = input.readFloat();
        skeletonData.height = input.readFloat();
        skeletonData.referenceScale = input.readFloat() * scale;
        let nonessential = input.readBoolean();
        if (nonessential) {
            skeletonData.fps = input.readFloat();
            skeletonData.imagesPath = input.readString();
            skeletonData.audioPath = input.readString();
        }
        let n = 0;
        // Strings.
        n = input.readInt(true);
        for (let i = 0; i < n; i++) {
            let str = input.readString();
            if (!str)
                throw new Error("String in string table must not be null.");
            input.strings.push(str);
        }
        // Bones.
        n = input.readInt(true);
        for (let i = 0; i < n; i++) {
            let name = input.readString();
            if (!name)
                throw new Error("Bone name must not be null.");
            let parent = i == 0 ? null : skeletonData.bones[input.readInt(true)];
            let data = new BoneData(i, name, parent);
            data.rotation = input.readFloat();
            data.x = input.readFloat() * scale;
            data.y = input.readFloat() * scale;
            data.scaleX = input.readFloat();
            data.scaleY = input.readFloat();
            data.shearX = input.readFloat();
            data.shearY = input.readFloat();
            data.length = input.readFloat() * scale;
            data.inherit = input.readByte();
            data.skinRequired = input.readBoolean();
            if (nonessential) {
                Color.rgba8888ToColor(data.color, input.readInt32());
                data.icon = input.readString() ?? undefined;
                data.visible = input.readBoolean();
            }
            skeletonData.bones.push(data);
        }
        // Slots.
        n = input.readInt(true);
        for (let i = 0; i < n; i++) {
            let slotName = input.readString();
            if (!slotName)
                throw new Error("Slot name must not be null.");
            let boneData = skeletonData.bones[input.readInt(true)];
            let data = new SlotData(i, slotName, boneData);
            Color.rgba8888ToColor(data.color, input.readInt32());
            let darkColor = input.readInt32();
            if (darkColor != -1)
                Color.rgb888ToColor(data.darkColor = new Color(), darkColor);
            data.attachmentName = input.readStringRef();
            data.blendMode = input.readInt(true);
            if (nonessential)
                data.visible = input.readBoolean();
            skeletonData.slots.push(data);
        }
        // IK constraints.
        n = input.readInt(true);
        for (let i = 0, nn; i < n; i++) {
            let name = input.readString();
            if (!name)
                throw new Error("IK constraint data name must not be null.");
            let data = new IkConstraintData(name);
            data.order = input.readInt(true);
            nn = input.readInt(true);
            for (let ii = 0; ii < nn; ii++)
                data.bones.push(skeletonData.bones[input.readInt(true)]);
            data.target = skeletonData.bones[input.readInt(true)];
            let flags = input.readByte();
            data.skinRequired = (flags & 1) != 0;
            data.bendDirection = (flags & 2) != 0 ? 1 : -1;
            data.compress = (flags & 4) != 0;
            data.stretch = (flags & 8) != 0;
            data.uniform = (flags & 16) != 0;
            if ((flags & 32) != 0)
                data.mix = (flags & 64) != 0 ? input.readFloat() : 1;
            if ((flags & 128) != 0)
                data.softness = input.readFloat() * scale;
            skeletonData.ikConstraints.push(data);
        }
        // Transform constraints.
        n = input.readInt(true);
        for (let i = 0, nn; i < n; i++) {
            let name = input.readString();
            if (!name)
                throw new Error("Transform constraint data name must not be null.");
            let data = new TransformConstraintData(name);
            data.order = input.readInt(true);
            nn = input.readInt(true);
            for (let ii = 0; ii < nn; ii++)
                data.bones.push(skeletonData.bones[input.readInt(true)]);
            data.target = skeletonData.bones[input.readInt(true)];
            let flags = input.readByte();
            data.skinRequired = (flags & 1) != 0;
            data.local = (flags & 2) != 0;
            data.relative = (flags & 4) != 0;
            if ((flags & 8) != 0)
                data.offsetRotation = input.readFloat();
            if ((flags & 16) != 0)
                data.offsetX = input.readFloat() * scale;
            if ((flags & 32) != 0)
                data.offsetY = input.readFloat() * scale;
            if ((flags & 64) != 0)
                data.offsetScaleX = input.readFloat();
            if ((flags & 128) != 0)
                data.offsetScaleY = input.readFloat();
            flags = input.readByte();
            if ((flags & 1) != 0)
                data.offsetShearY = input.readFloat();
            if ((flags & 2) != 0)
                data.mixRotate = input.readFloat();
            if ((flags & 4) != 0)
                data.mixX = input.readFloat();
            if ((flags & 8) != 0)
                data.mixY = input.readFloat();
            if ((flags & 16) != 0)
                data.mixScaleX = input.readFloat();
            if ((flags & 32) != 0)
                data.mixScaleY = input.readFloat();
            if ((flags & 64) != 0)
                data.mixShearY = input.readFloat();
            skeletonData.transformConstraints.push(data);
        }
        // Path constraints.
        n = input.readInt(true);
        for (let i = 0, nn; i < n; i++) {
            let name = input.readString();
            if (!name)
                throw new Error("Path constraint data name must not be null.");
            let data = new PathConstraintData(name);
            data.order = input.readInt(true);
            data.skinRequired = input.readBoolean();
            nn = input.readInt(true);
            for (let ii = 0; ii < nn; ii++)
                data.bones.push(skeletonData.bones[input.readInt(true)]);
            data.target = skeletonData.slots[input.readInt(true)];
            const flags = input.readByte();
            data.positionMode = flags & 1;
            data.spacingMode = (flags >> 1) & 3;
            data.rotateMode = (flags >> 3) & 3;
            if ((flags & 128) != 0)
                data.offsetRotation = input.readFloat();
            data.position = input.readFloat();
            if (data.positionMode == PositionMode.Fixed)
                data.position *= scale;
            data.spacing = input.readFloat();
            if (data.spacingMode == SpacingMode.Length || data.spacingMode == SpacingMode.Fixed)
                data.spacing *= scale;
            data.mixRotate = input.readFloat();
            data.mixX = input.readFloat();
            data.mixY = input.readFloat();
            skeletonData.pathConstraints.push(data);
        }
        // Physics constraints.
        n = input.readInt(true);
        for (let i = 0, nn; i < n; i++) {
            const name = input.readString();
            if (!name)
                throw new Error("Physics constraint data name must not be null.");
            const data = new PhysicsConstraintData(name);
            data.order = input.readInt(true);
            data.bone = skeletonData.bones[input.readInt(true)];
            let flags = input.readByte();
            data.skinRequired = (flags & 1) != 0;
            if ((flags & 2) != 0)
                data.x = input.readFloat();
            if ((flags & 4) != 0)
                data.y = input.readFloat();
            if ((flags & 8) != 0)
                data.rotate = input.readFloat();
            if ((flags & 16) != 0)
                data.scaleX = input.readFloat();
            if ((flags & 32) != 0)
                data.shearX = input.readFloat();
            data.limit = ((flags & 64) != 0 ? input.readFloat() : 5000) * scale;
            data.step = 1 / input.readUnsignedByte();
            data.inertia = input.readFloat();
            data.strength = input.readFloat();
            data.damping = input.readFloat();
            data.massInverse = (flags & 128) != 0 ? input.readFloat() : 1;
            data.wind = input.readFloat();
            data.gravity = input.readFloat();
            flags = input.readByte();
            if ((flags & 1) != 0)
                data.inertiaGlobal = true;
            if ((flags & 2) != 0)
                data.strengthGlobal = true;
            if ((flags & 4) != 0)
                data.dampingGlobal = true;
            if ((flags & 8) != 0)
                data.massGlobal = true;
            if ((flags & 16) != 0)
                data.windGlobal = true;
            if ((flags & 32) != 0)
                data.gravityGlobal = true;
            if ((flags & 64) != 0)
                data.mixGlobal = true;
            data.mix = (flags & 128) != 0 ? input.readFloat() : 1;
            skeletonData.physicsConstraints.push(data);
        }
        // Default skin.
        let defaultSkin = this.readSkin(input, skeletonData, true, nonessential);
        if (defaultSkin) {
            skeletonData.defaultSkin = defaultSkin;
            skeletonData.skins.push(defaultSkin);
        }
        // Skins.
        {
            let i = skeletonData.skins.length;
            Utils.setArraySize(skeletonData.skins, n = i + input.readInt(true));
            for (; i < n; i++) {
                let skin = this.readSkin(input, skeletonData, false, nonessential);
                if (!skin)
                    throw new Error("readSkin() should not have returned null.");
                skeletonData.skins[i] = skin;
            }
        }
        // Linked meshes.
        n = this.linkedMeshes.length;
        for (let i = 0; i < n; i++) {
            let linkedMesh = this.linkedMeshes[i];
            const skin = skeletonData.skins[linkedMesh.skinIndex];
            if (!linkedMesh.parent)
                throw new Error("Linked mesh parent must not be null");
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
        n = input.readInt(true);
        for (let i = 0; i < n; i++) {
            let eventName = input.readString();
            if (!eventName)
                throw new Error("Event data name must not be null");
            let data = new EventData(eventName);
            data.intValue = input.readInt(false);
            data.floatValue = input.readFloat();
            data.stringValue = input.readString();
            data.audioPath = input.readString();
            if (data.audioPath) {
                data.volume = input.readFloat();
                data.balance = input.readFloat();
            }
            skeletonData.events.push(data);
        }
        // Animations.
        n = input.readInt(true);
        for (let i = 0; i < n; i++) {
            let animationName = input.readString();
            if (!animationName)
                throw new Error("Animatio name must not be null.");
            skeletonData.animations.push(this.readAnimation(input, animationName, skeletonData));
        }
        return skeletonData;
    }
    readSkin(input, skeletonData, defaultSkin, nonessential) {
        let skin = null;
        let slotCount = 0;
        if (defaultSkin) {
            slotCount = input.readInt(true);
            if (slotCount == 0)
                return null;
            skin = new Skin("default");
        }
        else {
            let skinName = input.readString();
            if (!skinName)
                throw new Error("Skin name must not be null.");
            skin = new Skin(skinName);
            if (nonessential)
                Color.rgba8888ToColor(skin.color, input.readInt32());
            skin.bones.length = input.readInt(true);
            for (let i = 0, n = skin.bones.length; i < n; i++)
                skin.bones[i] = skeletonData.bones[input.readInt(true)];
            for (let i = 0, n = input.readInt(true); i < n; i++)
                skin.constraints.push(skeletonData.ikConstraints[input.readInt(true)]);
            for (let i = 0, n = input.readInt(true); i < n; i++)
                skin.constraints.push(skeletonData.transformConstraints[input.readInt(true)]);
            for (let i = 0, n = input.readInt(true); i < n; i++)
                skin.constraints.push(skeletonData.pathConstraints[input.readInt(true)]);
            for (let i = 0, n = input.readInt(true); i < n; i++)
                skin.constraints.push(skeletonData.physicsConstraints[input.readInt(true)]);
            slotCount = input.readInt(true);
        }
        for (let i = 0; i < slotCount; i++) {
            let slotIndex = input.readInt(true);
            for (let ii = 0, nn = input.readInt(true); ii < nn; ii++) {
                let name = input.readStringRef();
                if (!name)
                    throw new Error("Attachment name must not be null");
                let attachment = this.readAttachment(input, skeletonData, skin, slotIndex, name, nonessential);
                if (attachment)
                    skin.setAttachment(slotIndex, name, attachment);
            }
        }
        return skin;
    }
    readAttachment(input, skeletonData, skin, slotIndex, attachmentName, nonessential) {
        let scale = this.scale;
        let flags = input.readByte();
        const name = (flags & 8) != 0 ? input.readStringRef() : attachmentName;
        if (!name)
            throw new Error("Attachment name must not be null");
        switch ((flags & 0b111)) { // BUG?
            case AttachmentType.Region: {
                let path = (flags & 16) != 0 ? input.readStringRef() : null;
                const color = (flags & 32) != 0 ? input.readInt32() : 0xffffffff;
                const sequence = (flags & 64) != 0 ? this.readSequence(input) : null;
                let rotation = (flags & 128) != 0 ? input.readFloat() : 0;
                let x = input.readFloat();
                let y = input.readFloat();
                let scaleX = input.readFloat();
                let scaleY = input.readFloat();
                let width = input.readFloat();
                let height = input.readFloat();
                if (!path)
                    path = name;
                let region = this.attachmentLoader.newRegionAttachment(skin, name, path, sequence);
                if (!region)
                    return null;
                region.path = path;
                region.x = x * scale;
                region.y = y * scale;
                region.scaleX = scaleX;
                region.scaleY = scaleY;
                region.rotation = rotation;
                region.width = width * scale;
                region.height = height * scale;
                Color.rgba8888ToColor(region.color, color);
                region.sequence = sequence;
                if (sequence == null)
                    region.updateRegion();
                return region;
            }
            case AttachmentType.BoundingBox: {
                let vertices = this.readVertices(input, (flags & 16) != 0);
                let color = nonessential ? input.readInt32() : 0;
                let box = this.attachmentLoader.newBoundingBoxAttachment(skin, name);
                if (!box)
                    return null;
                box.worldVerticesLength = vertices.length;
                box.vertices = vertices.vertices;
                box.bones = vertices.bones;
                if (nonessential)
                    Color.rgba8888ToColor(box.color, color);
                return box;
            }
            case AttachmentType.Mesh: {
                let path = (flags & 16) != 0 ? input.readStringRef() : name;
                const color = (flags & 32) != 0 ? input.readInt32() : 0xffffffff;
                const sequence = (flags & 64) != 0 ? this.readSequence(input) : null;
                const hullLength = input.readInt(true);
                const vertices = this.readVertices(input, (flags & 128) != 0);
                const uvs = this.readFloatArray(input, vertices.length, 1);
                const triangles = this.readShortArray(input, (vertices.length - hullLength - 2) * 3);
                let edges = [];
                let width = 0, height = 0;
                if (nonessential) {
                    edges = this.readShortArray(input, input.readInt(true));
                    width = input.readFloat();
                    height = input.readFloat();
                }
                if (!path)
                    path = name;
                let mesh = this.attachmentLoader.newMeshAttachment(skin, name, path, sequence);
                if (!mesh)
                    return null;
                mesh.path = path;
                Color.rgba8888ToColor(mesh.color, color);
                mesh.bones = vertices.bones;
                mesh.vertices = vertices.vertices;
                mesh.worldVerticesLength = vertices.length;
                mesh.triangles = triangles;
                mesh.regionUVs = uvs;
                if (sequence == null)
                    mesh.updateRegion();
                mesh.hullLength = hullLength << 1;
                mesh.sequence = sequence;
                if (nonessential) {
                    mesh.edges = edges;
                    mesh.width = width * scale;
                    mesh.height = height * scale;
                }
                return mesh;
            }
            case AttachmentType.LinkedMesh: {
                const path = (flags & 16) != 0 ? input.readStringRef() : name;
                if (path == null)
                    throw new Error("Path of linked mesh must not be null");
                const color = (flags & 32) != 0 ? input.readInt32() : 0xffffffff;
                const sequence = (flags & 64) != 0 ? this.readSequence(input) : null;
                const inheritTimelines = (flags & 128) != 0;
                const skinIndex = input.readInt(true);
                const parent = input.readStringRef();
                let width = 0, height = 0;
                if (nonessential) {
                    width = input.readFloat();
                    height = input.readFloat();
                }
                let mesh = this.attachmentLoader.newMeshAttachment(skin, name, path, sequence);
                if (!mesh)
                    return null;
                mesh.path = path;
                Color.rgba8888ToColor(mesh.color, color);
                mesh.sequence = sequence;
                if (nonessential) {
                    mesh.width = width * scale;
                    mesh.height = height * scale;
                }
                this.linkedMeshes.push(new LinkedMesh(mesh, skinIndex, slotIndex, parent, inheritTimelines));
                return mesh;
            }
            case AttachmentType.Path: {
                const closed = (flags & 16) != 0;
                const constantSpeed = (flags & 32) != 0;
                const vertices = this.readVertices(input, (flags & 64) != 0);
                const lengths = Utils.newArray(vertices.length / 6, 0);
                for (let i = 0, n = lengths.length; i < n; i++)
                    lengths[i] = input.readFloat() * scale;
                const color = nonessential ? input.readInt32() : 0;
                const path = this.attachmentLoader.newPathAttachment(skin, name);
                if (!path)
                    return null;
                path.closed = closed;
                path.constantSpeed = constantSpeed;
                path.worldVerticesLength = vertices.length;
                path.vertices = vertices.vertices;
                path.bones = vertices.bones;
                path.lengths = lengths;
                if (nonessential)
                    Color.rgba8888ToColor(path.color, color);
                return path;
            }
            case AttachmentType.Point: {
                const rotation = input.readFloat();
                const x = input.readFloat();
                const y = input.readFloat();
                const color = nonessential ? input.readInt32() : 0;
                const point = this.attachmentLoader.newPointAttachment(skin, name);
                if (!point)
                    return null;
                point.x = x * scale;
                point.y = y * scale;
                point.rotation = rotation;
                if (nonessential)
                    Color.rgba8888ToColor(point.color, color);
                return point;
            }
            case AttachmentType.Clipping: {
                const endSlotIndex = input.readInt(true);
                const vertices = this.readVertices(input, (flags & 16) != 0);
                let color = nonessential ? input.readInt32() : 0;
                let clip = this.attachmentLoader.newClippingAttachment(skin, name);
                if (!clip)
                    return null;
                clip.endSlot = skeletonData.slots[endSlotIndex];
                clip.worldVerticesLength = vertices.length;
                clip.vertices = vertices.vertices;
                clip.bones = vertices.bones;
                if (nonessential)
                    Color.rgba8888ToColor(clip.color, color);
                return clip;
            }
        }
        return null;
    }
    readSequence(input) {
        let sequence = new Sequence(input.readInt(true));
        sequence.start = input.readInt(true);
        sequence.digits = input.readInt(true);
        sequence.setupIndex = input.readInt(true);
        return sequence;
    }
    readVertices(input, weighted) {
        const scale = this.scale;
        const vertexCount = input.readInt(true);
        const vertices = new Vertices();
        vertices.length = vertexCount << 1;
        if (!weighted) {
            vertices.vertices = this.readFloatArray(input, vertices.length, scale);
            return vertices;
        }
        let weights = new Array();
        let bonesArray = new Array();
        for (let i = 0; i < vertexCount; i++) {
            let boneCount = input.readInt(true);
            bonesArray.push(boneCount);
            for (let ii = 0; ii < boneCount; ii++) {
                bonesArray.push(input.readInt(true));
                weights.push(input.readFloat() * scale);
                weights.push(input.readFloat() * scale);
                weights.push(input.readFloat());
            }
        }
        vertices.vertices = Utils.toFloatArray(weights);
        vertices.bones = bonesArray;
        return vertices;
    }
    readFloatArray(input, n, scale) {
        let array = new Array(n);
        if (scale == 1) {
            for (let i = 0; i < n; i++)
                array[i] = input.readFloat();
        }
        else {
            for (let i = 0; i < n; i++)
                array[i] = input.readFloat() * scale;
        }
        return array;
    }
    readShortArray(input, n) {
        let array = new Array(n);
        for (let i = 0; i < n; i++)
            array[i] = input.readInt(true);
        return array;
    }
    readAnimation(input, name, skeletonData) {
        input.readInt(true); // Number of timelines.
        let timelines = new Array();
        let scale = this.scale;
        // Slot timelines.
        for (let i = 0, n = input.readInt(true); i < n; i++) {
            let slotIndex = input.readInt(true);
            for (let ii = 0, nn = input.readInt(true); ii < nn; ii++) {
                let timelineType = input.readByte();
                let frameCount = input.readInt(true);
                let frameLast = frameCount - 1;
                switch (timelineType) {
                    case SLOT_ATTACHMENT: {
                        let timeline = new AttachmentTimeline(frameCount, slotIndex);
                        for (let frame = 0; frame < frameCount; frame++)
                            timeline.setFrame(frame, input.readFloat(), input.readStringRef());
                        timelines.push(timeline);
                        break;
                    }
                    case SLOT_RGBA: {
                        let bezierCount = input.readInt(true);
                        let timeline = new RGBATimeline(frameCount, bezierCount, slotIndex);
                        let time = input.readFloat();
                        let r = input.readUnsignedByte() / 255.0;
                        let g = input.readUnsignedByte() / 255.0;
                        let b = input.readUnsignedByte() / 255.0;
                        let a = input.readUnsignedByte() / 255.0;
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, r, g, b, a);
                            if (frame == frameLast)
                                break;
                            let time2 = input.readFloat();
                            let r2 = input.readUnsignedByte() / 255.0;
                            let g2 = input.readUnsignedByte() / 255.0;
                            let b2 = input.readUnsignedByte() / 255.0;
                            let a2 = input.readUnsignedByte() / 255.0;
                            switch (input.readByte()) {
                                case CURVE_STEPPED:
                                    timeline.setStepped(frame);
                                    break;
                                case CURVE_BEZIER:
                                    setBezier(input, timeline, bezier++, frame, 0, time, time2, r, r2, 1);
                                    setBezier(input, timeline, bezier++, frame, 1, time, time2, g, g2, 1);
                                    setBezier(input, timeline, bezier++, frame, 2, time, time2, b, b2, 1);
                                    setBezier(input, timeline, bezier++, frame, 3, time, time2, a, a2, 1);
                            }
                            time = time2;
                            r = r2;
                            g = g2;
                            b = b2;
                            a = a2;
                        }
                        timelines.push(timeline);
                        break;
                    }
                    case SLOT_RGB: {
                        let bezierCount = input.readInt(true);
                        let timeline = new RGBTimeline(frameCount, bezierCount, slotIndex);
                        let time = input.readFloat();
                        let r = input.readUnsignedByte() / 255.0;
                        let g = input.readUnsignedByte() / 255.0;
                        let b = input.readUnsignedByte() / 255.0;
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, r, g, b);
                            if (frame == frameLast)
                                break;
                            let time2 = input.readFloat();
                            let r2 = input.readUnsignedByte() / 255.0;
                            let g2 = input.readUnsignedByte() / 255.0;
                            let b2 = input.readUnsignedByte() / 255.0;
                            switch (input.readByte()) {
                                case CURVE_STEPPED:
                                    timeline.setStepped(frame);
                                    break;
                                case CURVE_BEZIER:
                                    setBezier(input, timeline, bezier++, frame, 0, time, time2, r, r2, 1);
                                    setBezier(input, timeline, bezier++, frame, 1, time, time2, g, g2, 1);
                                    setBezier(input, timeline, bezier++, frame, 2, time, time2, b, b2, 1);
                            }
                            time = time2;
                            r = r2;
                            g = g2;
                            b = b2;
                        }
                        timelines.push(timeline);
                        break;
                    }
                    case SLOT_RGBA2: {
                        let bezierCount = input.readInt(true);
                        let timeline = new RGBA2Timeline(frameCount, bezierCount, slotIndex);
                        let time = input.readFloat();
                        let r = input.readUnsignedByte() / 255.0;
                        let g = input.readUnsignedByte() / 255.0;
                        let b = input.readUnsignedByte() / 255.0;
                        let a = input.readUnsignedByte() / 255.0;
                        let r2 = input.readUnsignedByte() / 255.0;
                        let g2 = input.readUnsignedByte() / 255.0;
                        let b2 = input.readUnsignedByte() / 255.0;
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, r, g, b, a, r2, g2, b2);
                            if (frame == frameLast)
                                break;
                            let time2 = input.readFloat();
                            let nr = input.readUnsignedByte() / 255.0;
                            let ng = input.readUnsignedByte() / 255.0;
                            let nb = input.readUnsignedByte() / 255.0;
                            let na = input.readUnsignedByte() / 255.0;
                            let nr2 = input.readUnsignedByte() / 255.0;
                            let ng2 = input.readUnsignedByte() / 255.0;
                            let nb2 = input.readUnsignedByte() / 255.0;
                            switch (input.readByte()) {
                                case CURVE_STEPPED:
                                    timeline.setStepped(frame);
                                    break;
                                case CURVE_BEZIER:
                                    setBezier(input, timeline, bezier++, frame, 0, time, time2, r, nr, 1);
                                    setBezier(input, timeline, bezier++, frame, 1, time, time2, g, ng, 1);
                                    setBezier(input, timeline, bezier++, frame, 2, time, time2, b, nb, 1);
                                    setBezier(input, timeline, bezier++, frame, 3, time, time2, a, na, 1);
                                    setBezier(input, timeline, bezier++, frame, 4, time, time2, r2, nr2, 1);
                                    setBezier(input, timeline, bezier++, frame, 5, time, time2, g2, ng2, 1);
                                    setBezier(input, timeline, bezier++, frame, 6, time, time2, b2, nb2, 1);
                            }
                            time = time2;
                            r = nr;
                            g = ng;
                            b = nb;
                            a = na;
                            r2 = nr2;
                            g2 = ng2;
                            b2 = nb2;
                        }
                        timelines.push(timeline);
                        break;
                    }
                    case SLOT_RGB2: {
                        let bezierCount = input.readInt(true);
                        let timeline = new RGB2Timeline(frameCount, bezierCount, slotIndex);
                        let time = input.readFloat();
                        let r = input.readUnsignedByte() / 255.0;
                        let g = input.readUnsignedByte() / 255.0;
                        let b = input.readUnsignedByte() / 255.0;
                        let r2 = input.readUnsignedByte() / 255.0;
                        let g2 = input.readUnsignedByte() / 255.0;
                        let b2 = input.readUnsignedByte() / 255.0;
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, r, g, b, r2, g2, b2);
                            if (frame == frameLast)
                                break;
                            let time2 = input.readFloat();
                            let nr = input.readUnsignedByte() / 255.0;
                            let ng = input.readUnsignedByte() / 255.0;
                            let nb = input.readUnsignedByte() / 255.0;
                            let nr2 = input.readUnsignedByte() / 255.0;
                            let ng2 = input.readUnsignedByte() / 255.0;
                            let nb2 = input.readUnsignedByte() / 255.0;
                            switch (input.readByte()) {
                                case CURVE_STEPPED:
                                    timeline.setStepped(frame);
                                    break;
                                case CURVE_BEZIER:
                                    setBezier(input, timeline, bezier++, frame, 0, time, time2, r, nr, 1);
                                    setBezier(input, timeline, bezier++, frame, 1, time, time2, g, ng, 1);
                                    setBezier(input, timeline, bezier++, frame, 2, time, time2, b, nb, 1);
                                    setBezier(input, timeline, bezier++, frame, 3, time, time2, r2, nr2, 1);
                                    setBezier(input, timeline, bezier++, frame, 4, time, time2, g2, ng2, 1);
                                    setBezier(input, timeline, bezier++, frame, 5, time, time2, b2, nb2, 1);
                            }
                            time = time2;
                            r = nr;
                            g = ng;
                            b = nb;
                            r2 = nr2;
                            g2 = ng2;
                            b2 = nb2;
                        }
                        timelines.push(timeline);
                        break;
                    }
                    case SLOT_ALPHA: {
                        let timeline = new AlphaTimeline(frameCount, input.readInt(true), slotIndex);
                        let time = input.readFloat(), a = input.readUnsignedByte() / 255;
                        for (let frame = 0, bezier = 0;; frame++) {
                            timeline.setFrame(frame, time, a);
                            if (frame == frameLast)
                                break;
                            let time2 = input.readFloat();
                            let a2 = input.readUnsignedByte() / 255;
                            switch (input.readByte()) {
                                case CURVE_STEPPED:
                                    timeline.setStepped(frame);
                                    break;
                                case CURVE_BEZIER:
                                    setBezier(input, timeline, bezier++, frame, 0, time, time2, a, a2, 1);
                            }
                            time = time2;
                            a = a2;
                        }
                        timelines.push(timeline);
                    }
                }
            }
        }
        // Bone timelines.
        for (let i = 0, n = input.readInt(true); i < n; i++) {
            let boneIndex = input.readInt(true);
            for (let ii = 0, nn = input.readInt(true); ii < nn; ii++) {
                let type = input.readByte(), frameCount = input.readInt(true);
                if (type == BONE_INHERIT) {
                    let timeline = new InheritTimeline(frameCount, boneIndex);
                    for (let frame = 0; frame < frameCount; frame++) {
                        timeline.setFrame(frame, input.readFloat(), input.readByte());
                    }
                    timelines.push(timeline);
                    continue;
                }
                let bezierCount = input.readInt(true);
                switch (type) {
                    case BONE_ROTATE:
                        timelines.push(readTimeline1(input, new RotateTimeline(frameCount, bezierCount, boneIndex), 1));
                        break;
                    case BONE_TRANSLATE:
                        timelines.push(readTimeline2(input, new TranslateTimeline(frameCount, bezierCount, boneIndex), scale));
                        break;
                    case BONE_TRANSLATEX:
                        timelines.push(readTimeline1(input, new TranslateXTimeline(frameCount, bezierCount, boneIndex), scale));
                        break;
                    case BONE_TRANSLATEY:
                        timelines.push(readTimeline1(input, new TranslateYTimeline(frameCount, bezierCount, boneIndex), scale));
                        break;
                    case BONE_SCALE:
                        timelines.push(readTimeline2(input, new ScaleTimeline(frameCount, bezierCount, boneIndex), 1));
                        break;
                    case BONE_SCALEX:
                        timelines.push(readTimeline1(input, new ScaleXTimeline(frameCount, bezierCount, boneIndex), 1));
                        break;
                    case BONE_SCALEY:
                        timelines.push(readTimeline1(input, new ScaleYTimeline(frameCount, bezierCount, boneIndex), 1));
                        break;
                    case BONE_SHEAR:
                        timelines.push(readTimeline2(input, new ShearTimeline(frameCount, bezierCount, boneIndex), 1));
                        break;
                    case BONE_SHEARX:
                        timelines.push(readTimeline1(input, new ShearXTimeline(frameCount, bezierCount, boneIndex), 1));
                        break;
                    case BONE_SHEARY:
                        timelines.push(readTimeline1(input, new ShearYTimeline(frameCount, bezierCount, boneIndex), 1));
                }
            }
        }
        // IK constraint timelines.
        for (let i = 0, n = input.readInt(true); i < n; i++) {
            let index = input.readInt(true), frameCount = input.readInt(true), frameLast = frameCount - 1;
            let timeline = new IkConstraintTimeline(frameCount, input.readInt(true), index);
            let flags = input.readByte();
            let time = input.readFloat(), mix = (flags & 1) != 0 ? ((flags & 2) != 0 ? input.readFloat() : 1) : 0;
            let softness = (flags & 4) != 0 ? input.readFloat() * scale : 0;
            for (let frame = 0, bezier = 0;; frame++) {
                timeline.setFrame(frame, time, mix, softness, (flags & 8) != 0 ? 1 : -1, (flags & 16) != 0, (flags & 32) != 0);
                if (frame == frameLast)
                    break;
                flags = input.readByte();
                const time2 = input.readFloat(), mix2 = (flags & 1) != 0 ? ((flags & 2) != 0 ? input.readFloat() : 1) : 0;
                const softness2 = (flags & 4) != 0 ? input.readFloat() * scale : 0;
                if ((flags & 64) != 0) {
                    timeline.setStepped(frame);
                }
                else if ((flags & 128) != 0) {
                    setBezier(input, timeline, bezier++, frame, 0, time, time2, mix, mix2, 1);
                    setBezier(input, timeline, bezier++, frame, 1, time, time2, softness, softness2, scale);
                }
                time = time2;
                mix = mix2;
                softness = softness2;
            }
            timelines.push(timeline);
        }
        // Transform constraint timelines.
        for (let i = 0, n = input.readInt(true); i < n; i++) {
            let index = input.readInt(true), frameCount = input.readInt(true), frameLast = frameCount - 1;
            let timeline = new TransformConstraintTimeline(frameCount, input.readInt(true), index);
            let time = input.readFloat(), mixRotate = input.readFloat(), mixX = input.readFloat(), mixY = input.readFloat(), mixScaleX = input.readFloat(), mixScaleY = input.readFloat(), mixShearY = input.readFloat();
            for (let frame = 0, bezier = 0;; frame++) {
                timeline.setFrame(frame, time, mixRotate, mixX, mixY, mixScaleX, mixScaleY, mixShearY);
                if (frame == frameLast)
                    break;
                let time2 = input.readFloat(), mixRotate2 = input.readFloat(), mixX2 = input.readFloat(), mixY2 = input.readFloat(), mixScaleX2 = input.readFloat(), mixScaleY2 = input.readFloat(), mixShearY2 = input.readFloat();
                switch (input.readByte()) {
                    case CURVE_STEPPED:
                        timeline.setStepped(frame);
                        break;
                    case CURVE_BEZIER:
                        setBezier(input, timeline, bezier++, frame, 0, time, time2, mixRotate, mixRotate2, 1);
                        setBezier(input, timeline, bezier++, frame, 1, time, time2, mixX, mixX2, 1);
                        setBezier(input, timeline, bezier++, frame, 2, time, time2, mixY, mixY2, 1);
                        setBezier(input, timeline, bezier++, frame, 3, time, time2, mixScaleX, mixScaleX2, 1);
                        setBezier(input, timeline, bezier++, frame, 4, time, time2, mixScaleY, mixScaleY2, 1);
                        setBezier(input, timeline, bezier++, frame, 5, time, time2, mixShearY, mixShearY2, 1);
                }
                time = time2;
                mixRotate = mixRotate2;
                mixX = mixX2;
                mixY = mixY2;
                mixScaleX = mixScaleX2;
                mixScaleY = mixScaleY2;
                mixShearY = mixShearY2;
            }
            timelines.push(timeline);
        }
        // Path constraint timelines.
        for (let i = 0, n = input.readInt(true); i < n; i++) {
            let index = input.readInt(true);
            let data = skeletonData.pathConstraints[index];
            for (let ii = 0, nn = input.readInt(true); ii < nn; ii++) {
                const type = input.readByte(), frameCount = input.readInt(true), bezierCount = input.readInt(true);
                switch (type) {
                    case PATH_POSITION:
                        timelines
                            .push(readTimeline1(input, new PathConstraintPositionTimeline(frameCount, bezierCount, index), data.positionMode == PositionMode.Fixed ? scale : 1));
                        break;
                    case PATH_SPACING:
                        timelines
                            .push(readTimeline1(input, new PathConstraintSpacingTimeline(frameCount, bezierCount, index), data.spacingMode == SpacingMode.Length || data.spacingMode == SpacingMode.Fixed ? scale : 1));
                        break;
                    case PATH_MIX:
                        let timeline = new PathConstraintMixTimeline(frameCount, bezierCount, index);
                        let time = input.readFloat(), mixRotate = input.readFloat(), mixX = input.readFloat(), mixY = input.readFloat();
                        for (let frame = 0, bezier = 0, frameLast = timeline.getFrameCount() - 1;; frame++) {
                            timeline.setFrame(frame, time, mixRotate, mixX, mixY);
                            if (frame == frameLast)
                                break;
                            let time2 = input.readFloat(), mixRotate2 = input.readFloat(), mixX2 = input.readFloat(), mixY2 = input.readFloat();
                            switch (input.readByte()) {
                                case CURVE_STEPPED:
                                    timeline.setStepped(frame);
                                    break;
                                case CURVE_BEZIER:
                                    setBezier(input, timeline, bezier++, frame, 0, time, time2, mixRotate, mixRotate2, 1);
                                    setBezier(input, timeline, bezier++, frame, 1, time, time2, mixX, mixX2, 1);
                                    setBezier(input, timeline, bezier++, frame, 2, time, time2, mixY, mixY2, 1);
                            }
                            time = time2;
                            mixRotate = mixRotate2;
                            mixX = mixX2;
                            mixY = mixY2;
                        }
                        timelines.push(timeline);
                }
            }
        }
        // Physics timelines.
        for (let i = 0, n = input.readInt(true); i < n; i++) {
            const index = input.readInt(true) - 1;
            for (let ii = 0, nn = input.readInt(true); ii < nn; ii++) {
                const type = input.readByte(), frameCount = input.readInt(true);
                if (type == PHYSICS_RESET) {
                    const timeline = new PhysicsConstraintResetTimeline(frameCount, index);
                    for (let frame = 0; frame < frameCount; frame++)
                        timeline.setFrame(frame, input.readFloat());
                    timelines.push(timeline);
                    continue;
                }
                const bezierCount = input.readInt(true);
                switch (type) {
                    case PHYSICS_INERTIA:
                        timelines.push(readTimeline1(input, new PhysicsConstraintInertiaTimeline(frameCount, bezierCount, index), 1));
                        break;
                    case PHYSICS_STRENGTH:
                        timelines.push(readTimeline1(input, new PhysicsConstraintStrengthTimeline(frameCount, bezierCount, index), 1));
                        break;
                    case PHYSICS_DAMPING:
                        timelines.push(readTimeline1(input, new PhysicsConstraintDampingTimeline(frameCount, bezierCount, index), 1));
                        break;
                    case PHYSICS_MASS:
                        timelines.push(readTimeline1(input, new PhysicsConstraintMassTimeline(frameCount, bezierCount, index), 1));
                        break;
                    case PHYSICS_WIND:
                        timelines.push(readTimeline1(input, new PhysicsConstraintWindTimeline(frameCount, bezierCount, index), 1));
                        break;
                    case PHYSICS_GRAVITY:
                        timelines.push(readTimeline1(input, new PhysicsConstraintGravityTimeline(frameCount, bezierCount, index), 1));
                        break;
                    case PHYSICS_MIX:
                        timelines.push(readTimeline1(input, new PhysicsConstraintMixTimeline(frameCount, bezierCount, index), 1));
                }
            }
        }
        // Deform timelines.
        for (let i = 0, n = input.readInt(true); i < n; i++) {
            let skin = skeletonData.skins[input.readInt(true)];
            for (let ii = 0, nn = input.readInt(true); ii < nn; ii++) {
                let slotIndex = input.readInt(true);
                for (let iii = 0, nnn = input.readInt(true); iii < nnn; iii++) {
                    let attachmentName = input.readStringRef();
                    if (!attachmentName)
                        throw new Error("attachmentName must not be null.");
                    let attachment = skin.getAttachment(slotIndex, attachmentName);
                    let timelineType = input.readByte();
                    let frameCount = input.readInt(true);
                    let frameLast = frameCount - 1;
                    switch (timelineType) {
                        case ATTACHMENT_DEFORM: {
                            let vertexAttachment = attachment;
                            let weighted = vertexAttachment.bones;
                            let vertices = vertexAttachment.vertices;
                            let deformLength = weighted ? vertices.length / 3 * 2 : vertices.length;
                            let bezierCount = input.readInt(true);
                            let timeline = new DeformTimeline(frameCount, bezierCount, slotIndex, vertexAttachment);
                            let time = input.readFloat();
                            for (let frame = 0, bezier = 0;; frame++) {
                                let deform;
                                let end = input.readInt(true);
                                if (end == 0)
                                    deform = weighted ? Utils.newFloatArray(deformLength) : vertices;
                                else {
                                    deform = Utils.newFloatArray(deformLength);
                                    let start = input.readInt(true);
                                    end += start;
                                    if (scale == 1) {
                                        for (let v = start; v < end; v++)
                                            deform[v] = input.readFloat();
                                    }
                                    else {
                                        for (let v = start; v < end; v++)
                                            deform[v] = input.readFloat() * scale;
                                    }
                                    if (!weighted) {
                                        for (let v = 0, vn = deform.length; v < vn; v++)
                                            deform[v] += vertices[v];
                                    }
                                }
                                timeline.setFrame(frame, time, deform);
                                if (frame == frameLast)
                                    break;
                                let time2 = input.readFloat();
                                switch (input.readByte()) {
                                    case CURVE_STEPPED:
                                        timeline.setStepped(frame);
                                        break;
                                    case CURVE_BEZIER:
                                        setBezier(input, timeline, bezier++, frame, 0, time, time2, 0, 1, 1);
                                }
                                time = time2;
                            }
                            timelines.push(timeline);
                            break;
                        }
                        case ATTACHMENT_SEQUENCE: {
                            let timeline = new SequenceTimeline(frameCount, slotIndex, attachment);
                            for (let frame = 0; frame < frameCount; frame++) {
                                let time = input.readFloat();
                                let modeAndIndex = input.readInt32();
                                timeline.setFrame(frame, time, SequenceModeValues[modeAndIndex & 0xf], modeAndIndex >> 4, input.readFloat());
                            }
                            timelines.push(timeline);
                            break;
                        }
                    }
                }
            }
        }
        // Draw order timeline.
        let drawOrderCount = input.readInt(true);
        if (drawOrderCount > 0) {
            let timeline = new DrawOrderTimeline(drawOrderCount);
            let slotCount = skeletonData.slots.length;
            for (let i = 0; i < drawOrderCount; i++) {
                let time = input.readFloat();
                let offsetCount = input.readInt(true);
                let drawOrder = Utils.newArray(slotCount, 0);
                for (let ii = slotCount - 1; ii >= 0; ii--)
                    drawOrder[ii] = -1;
                let unchanged = Utils.newArray(slotCount - offsetCount, 0);
                let originalIndex = 0, unchangedIndex = 0;
                for (let ii = 0; ii < offsetCount; ii++) {
                    let slotIndex = input.readInt(true);
                    // Collect unchanged items.
                    while (originalIndex != slotIndex)
                        unchanged[unchangedIndex++] = originalIndex++;
                    // Set changed items.
                    drawOrder[originalIndex + input.readInt(true)] = originalIndex++;
                }
                // Collect remaining unchanged items.
                while (originalIndex < slotCount)
                    unchanged[unchangedIndex++] = originalIndex++;
                // Fill in unchanged items.
                for (let ii = slotCount - 1; ii >= 0; ii--)
                    if (drawOrder[ii] == -1)
                        drawOrder[ii] = unchanged[--unchangedIndex];
                timeline.setFrame(i, time, drawOrder);
            }
            timelines.push(timeline);
        }
        // Event timeline.
        let eventCount = input.readInt(true);
        if (eventCount > 0) {
            let timeline = new EventTimeline(eventCount);
            for (let i = 0; i < eventCount; i++) {
                let time = input.readFloat();
                let eventData = skeletonData.events[input.readInt(true)];
                let event = new Event(time, eventData);
                event.intValue = input.readInt(false);
                event.floatValue = input.readFloat();
                event.stringValue = input.readString();
                if (event.stringValue == null)
                    event.stringValue = eventData.stringValue;
                if (event.data.audioPath) {
                    event.volume = input.readFloat();
                    event.balance = input.readFloat();
                }
                timeline.setFrame(i, event);
            }
            timelines.push(timeline);
        }
        let duration = 0;
        for (let i = 0, n = timelines.length; i < n; i++)
            duration = Math.max(duration, timelines[i].getDuration());
        return new Animation(name, timelines, duration);
    }
}
export class BinaryInput {
    strings;
    index;
    buffer;
    constructor(data, strings = new Array(), index = 0, buffer = new DataView(data instanceof ArrayBuffer ? data : data.buffer)) {
        this.strings = strings;
        this.index = index;
        this.buffer = buffer;
    }
    readByte() {
        return this.buffer.getInt8(this.index++);
    }
    readUnsignedByte() {
        return this.buffer.getUint8(this.index++);
    }
    readShort() {
        let value = this.buffer.getInt16(this.index);
        this.index += 2;
        return value;
    }
    readInt32() {
        let value = this.buffer.getInt32(this.index);
        this.index += 4;
        return value;
    }
    readInt(optimizePositive) {
        let b = this.readByte();
        let result = b & 0x7F;
        if ((b & 0x80) != 0) {
            b = this.readByte();
            result |= (b & 0x7F) << 7;
            if ((b & 0x80) != 0) {
                b = this.readByte();
                result |= (b & 0x7F) << 14;
                if ((b & 0x80) != 0) {
                    b = this.readByte();
                    result |= (b & 0x7F) << 21;
                    if ((b & 0x80) != 0) {
                        b = this.readByte();
                        result |= (b & 0x7F) << 28;
                    }
                }
            }
        }
        return optimizePositive ? result : ((result >>> 1) ^ -(result & 1));
    }
    readStringRef() {
        let index = this.readInt(true);
        return index == 0 ? null : this.strings[index - 1];
    }
    readString() {
        let byteCount = this.readInt(true);
        switch (byteCount) {
            case 0:
                return null;
            case 1:
                return "";
        }
        byteCount--;
        let chars = "";
        let charCount = 0;
        for (let i = 0; i < byteCount;) {
            let b = this.readUnsignedByte();
            switch (b >> 4) {
                case 12:
                case 13:
                    chars += String.fromCharCode(((b & 0x1F) << 6 | this.readByte() & 0x3F));
                    i += 2;
                    break;
                case 14:
                    chars += String.fromCharCode(((b & 0x0F) << 12 | (this.readByte() & 0x3F) << 6 | this.readByte() & 0x3F));
                    i += 3;
                    break;
                default:
                    chars += String.fromCharCode(b);
                    i++;
            }
        }
        return chars;
    }
    readFloat() {
        let value = this.buffer.getFloat32(this.index);
        this.index += 4;
        return value;
    }
    readBoolean() {
        return this.readByte() != 0;
    }
}
class LinkedMesh {
    parent;
    skinIndex;
    slotIndex;
    mesh;
    inheritTimeline;
    constructor(mesh, skinIndex, slotIndex, parent, inheritDeform) {
        this.mesh = mesh;
        this.skinIndex = skinIndex;
        this.slotIndex = slotIndex;
        this.parent = parent;
        this.inheritTimeline = inheritDeform;
    }
}
class Vertices {
    bones;
    vertices;
    length;
    constructor(bones = null, vertices = null, length = 0) {
        this.bones = bones;
        this.vertices = vertices;
        this.length = length;
    }
}
var AttachmentType;
(function (AttachmentType) {
    AttachmentType[AttachmentType["Region"] = 0] = "Region";
    AttachmentType[AttachmentType["BoundingBox"] = 1] = "BoundingBox";
    AttachmentType[AttachmentType["Mesh"] = 2] = "Mesh";
    AttachmentType[AttachmentType["LinkedMesh"] = 3] = "LinkedMesh";
    AttachmentType[AttachmentType["Path"] = 4] = "Path";
    AttachmentType[AttachmentType["Point"] = 5] = "Point";
    AttachmentType[AttachmentType["Clipping"] = 6] = "Clipping";
})(AttachmentType || (AttachmentType = {}));
function readTimeline1(input, timeline, scale) {
    let time = input.readFloat(), value = input.readFloat() * scale;
    for (let frame = 0, bezier = 0, frameLast = timeline.getFrameCount() - 1;; frame++) {
        timeline.setFrame(frame, time, value);
        if (frame == frameLast)
            break;
        let time2 = input.readFloat(), value2 = input.readFloat() * scale;
        switch (input.readByte()) {
            case CURVE_STEPPED:
                timeline.setStepped(frame);
                break;
            case CURVE_BEZIER:
                setBezier(input, timeline, bezier++, frame, 0, time, time2, value, value2, scale);
        }
        time = time2;
        value = value2;
    }
    return timeline;
}
function readTimeline2(input, timeline, scale) {
    let time = input.readFloat(), value1 = input.readFloat() * scale, value2 = input.readFloat() * scale;
    for (let frame = 0, bezier = 0, frameLast = timeline.getFrameCount() - 1;; frame++) {
        timeline.setFrame(frame, time, value1, value2);
        if (frame == frameLast)
            break;
        let time2 = input.readFloat(), nvalue1 = input.readFloat() * scale, nvalue2 = input.readFloat() * scale;
        switch (input.readByte()) {
            case CURVE_STEPPED:
                timeline.setStepped(frame);
                break;
            case CURVE_BEZIER:
                setBezier(input, timeline, bezier++, frame, 0, time, time2, value1, nvalue1, scale);
                setBezier(input, timeline, bezier++, frame, 1, time, time2, value2, nvalue2, scale);
        }
        time = time2;
        value1 = nvalue1;
        value2 = nvalue2;
    }
    return timeline;
}
function setBezier(input, timeline, bezier, frame, value, time1, time2, value1, value2, scale) {
    timeline.setBezier(bezier, frame, value, time1, value1, input.readFloat(), input.readFloat() * scale, input.readFloat(), input.readFloat() * scale, time2, value2);
}
const BONE_ROTATE = 0;
const BONE_TRANSLATE = 1;
const BONE_TRANSLATEX = 2;
const BONE_TRANSLATEY = 3;
const BONE_SCALE = 4;
const BONE_SCALEX = 5;
const BONE_SCALEY = 6;
const BONE_SHEAR = 7;
const BONE_SHEARX = 8;
const BONE_SHEARY = 9;
const BONE_INHERIT = 10;
const SLOT_ATTACHMENT = 0;
const SLOT_RGBA = 1;
const SLOT_RGB = 2;
const SLOT_RGBA2 = 3;
const SLOT_RGB2 = 4;
const SLOT_ALPHA = 5;
const ATTACHMENT_DEFORM = 0;
const ATTACHMENT_SEQUENCE = 1;
const PATH_POSITION = 0;
const PATH_SPACING = 1;
const PATH_MIX = 2;
const PHYSICS_INERTIA = 0;
const PHYSICS_STRENGTH = 1;
const PHYSICS_DAMPING = 2;
const PHYSICS_MASS = 4;
const PHYSICS_WIND = 5;
const PHYSICS_GRAVITY = 6;
const PHYSICS_MIX = 7;
const PHYSICS_RESET = 8;
const CURVE_LINEAR = 0;
const CURVE_STEPPED = 1;
const CURVE_BEZIER = 2;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiU2tlbGV0b25CaW5hcnkuanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyIuLi9zcmMvU2tlbGV0b25CaW5hcnkudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OzsrRUEyQitFO0FBRS9FLE9BQU8sRUFBRSxTQUFTLEVBQVksZUFBZSxFQUFFLGtCQUFrQixFQUFFLFlBQVksRUFBRSxXQUFXLEVBQUUsYUFBYSxFQUFFLFlBQVksRUFBRSxhQUFhLEVBQUUsY0FBYyxFQUFFLGlCQUFpQixFQUFFLGtCQUFrQixFQUFFLGtCQUFrQixFQUFFLGFBQWEsRUFBRSxjQUFjLEVBQUUsY0FBYyxFQUFFLGFBQWEsRUFBRSxjQUFjLEVBQUUsY0FBYyxFQUFFLG9CQUFvQixFQUFFLDJCQUEyQixFQUFFLDhCQUE4QixFQUFFLDZCQUE2QixFQUFFLHlCQUF5QixFQUFFLGNBQWMsRUFBRSxpQkFBaUIsRUFBRSxhQUFhLEVBQWlELGdCQUFnQixFQUFFLDhCQUE4QixFQUFFLGdDQUFnQyxFQUFFLGlDQUFpQyxFQUFFLGdDQUFnQyxFQUFFLDZCQUE2QixFQUFFLDZCQUE2QixFQUFFLGdDQUFnQyxFQUFFLDRCQUE0QixFQUFFLE1BQU0sZ0JBQWdCLENBQUM7QUFLLzBCLE9BQU8sRUFBRSxRQUFRLEVBQUUsa0JBQWtCLEVBQUUsTUFBTSwyQkFBMkIsQ0FBQztBQUN6RSxPQUFPLEVBQUUsUUFBUSxFQUFFLE1BQU0sZUFBZSxDQUFDO0FBQ3pDLE9BQU8sRUFBRSxLQUFLLEVBQUUsTUFBTSxZQUFZLENBQUM7QUFDbkMsT0FBTyxFQUFFLFNBQVMsRUFBRSxNQUFNLGdCQUFnQixDQUFDO0FBQzNDLE9BQU8sRUFBRSxnQkFBZ0IsRUFBRSxNQUFNLHVCQUF1QixDQUFDO0FBQ3pELE9BQU8sRUFBRSxrQkFBa0IsRUFBRSxZQUFZLEVBQUUsV0FBVyxFQUFFLE1BQU0seUJBQXlCLENBQUM7QUFDeEYsT0FBTyxFQUFFLHFCQUFxQixFQUFFLE1B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QUFDO3dCQUN6QyxJQUFJLENBQUMsR0FBRyxLQUFLLENBQUMsZ0JBQWdCLEVBQUUsR0FBRyxLQUFLLENBQUM7d0JBQ3pDLElBQUksQ0FBQyxHQUFHLEtBQUssQ0FBQyxnQkFBZ0IsRUFBRSxHQUFHLEtBQUssQ0FBQzt3QkFDekMsSUFBSSxFQUFFLEdBQUcsS0FBSyxDQUFDLGdCQUFnQixFQUFFLEdBQUcsS0FBSyxDQUFDO3dCQUMxQyxJQUFJLEVBQUUsR0FBRyxLQUFLLENBQUMsZ0JBQWdCLEVBQUUsR0FBRyxLQUFLLENBQUM7d0JBQzFDLElBQUksRUFBRSxHQUFHLEtBQUssQ0FBQyxnQkFBZ0IsRUFBRSxHQUFHLEtBQUssQ0FBQzt3QkFFMUMsS0FBSyxJQUFJLEtBQUssR0FBRyxDQUFDLEVBQUUsTUFBTSxHQUFHLENBQUMsR0FBSSxLQUFLLEVBQUUsRUFBRSxDQUFDOzRCQUMzQyxRQUFRLENBQUMsUUFBUSxDQUFDLEtBQUssRUFBRSxJQUFJLEVBQUUsQ0FBQyxFQUFFLENBQUMsRUFBRSxDQUFDLEVBQUUsQ0FBQyxFQUFFLEVBQUUsRUFBRSxFQUFFLEVBQUUsRUFBRSxDQUFDLENBQUM7NEJBQ3ZELElBQUksS0FBSyxJQUFJLFNBQVM7Z0NBQUUsTUFBTTs0QkFDOUIsSUFBSSxLQUFLLEdBQUcsS0FBSyxDQUFDLFNBQVMsRUFBRSxDQUFDOzRCQUM5QixJQUFJLEVBQUUsR0FBRyxLQUFLLENBQUMsZ0JBQWdCLEVBQUUsR0FBRyxLQUFLLENBQUM7NEJBQzFDLElBQUksRUFBRSxHQUFHLEtBQUssQ0FBQyxnQkFBZ0IsRUFBRSxHQUFHLEtBQUssQ0FBQzs0QkFDMUMsSUFBSSxFQUFFLEdBQUcsS0FBSyxDQUFDLGdCQUFnQixFQUFFLEdBQUcsS0FBSyxDQUFDOzRCQUMxQyxJQUFJLEVBQUUsR0FBRyxLQUFLLENBQUMsZ0JBQWdCLEVBQUUsR0FBRyxLQUFLLENBQUM7NEJBQzFDLElBQUksR0FBRyxHQUFHLEtBQUssQ0FBQyxnQkFBZ0IsRUFBRSxHQUFHLEtBQUssQ0FBQzs0QkFDM0MsSUFBSSxHQUFHLEdBQUcsS0FBSyxDQUFDLGdCQUFnQixFQUFFLEdBQUcsS0FBSyxDQUFDOzRCQUMzQyxJQUFJLEdBQUcsR0FBRyxLQUFLLENBQUMsZ0JBQWdCLEVBQUUsR0FBRyxLQUFLLENBQUM7NEJBRTNDLFFBQVEsS0FBSyxDQUFDLFFBQVEsRUFBRSxFQUFFLENBQUM7Z0NBQzFCLEtBQUssYUFBYTtvQ0FDakIsUUFBUSxDQUFDLFVBQVUsQ0FBQyxLQUFLLENBQUMsQ0FBQztvQ0FDM0IsTUFBTTtnQ0FDUCxLQUFLLFlBQVk7b0NBQ2hCLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxFQUFFLEtBQUssRUFBRSxDQUFDLEVBQUUsSUFBSSxFQUFFLEtBQUssRUFBRSxDQUFDLEVBQUUsRUFBRSxFQUFFLENBQUMsQ0FBQyxDQUFDO29DQUN0RSxTQUFTLENBQUMsS0FBSyxFQUFFLFFBQVEsRUFBRSxNQUFNLEVBQUUsRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLEVBQUUsRUFBRSxDQUFDLENBQUMsQ0FBQztvQ0FDdEUsU0FBUyxDQUFDLEtBQUssRUFBRSxRQUFRLEVBQUUsTUFBTSxFQUFFLEVBQUUsS0FBSyxFQUFFLENBQUMsRUFBRSxJQUFJLEVBQUUsS0FBSyxFQUFFLENBQUMsRUFBRSxFQUFFLEVBQUUsQ0FBQyxDQUFDLENBQUM7b0NBQ3RFLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxFQUFFLEtBQUssRUFBRSxDQUFDLEVBQUUsSUFBSSxFQUFFLEtBQUssRUFBRSxDQUFDLEVBQUUsRUFBRSxFQUFFLENBQUMsQ0FBQyxDQUFDO29DQUN0RSxTQUFTLENBQUMsS0FBSyxFQUFFLFFBQVEsRUFBRSxNQUFNLEVBQUUsRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxLQUFLLEVBQUUsRUFBRSxFQUFFLEdBQUcsRUFBRSxDQUFDLENBQUMsQ0FBQztvQ0FDeEUsU0FBUyxDQUFDLEtBQUssRUFBRSxRQUFRLEVBQUUsTUFBTSxFQUFFLEVBQUUsS0FBSyxFQUFFLENBQUMsRUFBRSxJQUFJLEVBQUUsS0FBSyxFQUFFLEVBQUUsRUFBRSxHQUFHLEVBQUUsQ0FBQyxDQUFDLENBQUM7b0NBQ3hFLFNBQVMsQ0FBQyxLQUFLLEVBQUUsUUFBUSxFQUFFLE1BQU0sRUFBRSxFQUFFLEtBQUssRUFBRSxDQUFDLEVBQUUsSUFBSSxFQUFFLEtBQUssRUFBRSxFQUFFLEVBQUUsR0FBRyxFQUFFLENBQUMsQ0FBQyxDQUFDOzRCQUMxRSxDQUFDOzRCQUNELElBQUksR0FBRyxLQUFLLENBQUM7NEJBQ2IsQ0FBQyxHQUFHLEVBQUUsQ0FBQzs0QkFDUCxDQUFDLEdBQUcsRUFBRSxDQUFDOzRCQUNQLENBQUMsR0FBRyxFQUFFLENBQUM7NEJBQ1AsQ0FBQyxHQUFHLEVBQUUsQ0FBQzs0QkFDUCxFQUFFLEdBQUcsR0FBRyxDQUFDOzRCQUNULEVBQUUsR0FBRyxHQUFHLENBQUM7NEJBQ1QsRUFBRSxHQUFHLEdBQUcsQ0FBQzt3QkFDVixDQUFDO3dCQUNELFNBQVMsQ0FBQyxJQUFJLENBQUMsUUFBUSxDQUFDLENBQUM7d0JBQ3pCLE1BQU07b0JBQ1AsQ0FBQztvQkFDRCxLQUFLLFNBQVMsQ0FBQyxDQUFDLENBQUM7d0JBQ2hCLElBQUksV0FBVyxHQUFHLEtBQUssQ0FBQyxPQUFPLENBQUMsSUFBSSxDQUFDLENBQUM7d0JBQ3RDLElBQUksUUFBUSxHQUFHLElBQUksWUFBWSxDQUFDLFVBQVUsRUFBRSxXQUFXLEVBQUUsU0FBUyxDQUFDLENBQUM7d0JBRXBFLElBQUksSUFBSSxHQUFHLEtBQUssQ0FBQyxTQUFTLEVBQUUsQ0FBQzt3QkFDN0IsSUFBSSxDQUFDLEdBQUcsS0FBSyxDQUFDLGdCQUFnQixFQUFFLEdBQUcsS0FBSyxDQUFDO3dCQUN6QyxJQUFJLENBQUMsR0FBRyxLQUFLLENBQUMsZ0JBQWdCLEVBQUUsR0FBRyxLQUFLLENBQUM7d0JBQ3pDLElBQUksQ0FBQyxHQUFHLEtBQUssQ0FBQyxnQkFBZ0IsRUFBRSxHQUFHLEtBQUssQ0FBQzt3QkFDekMsSUFBSSxFQUFFLEdBQUcsS0FBSyxDQUFDLGdCQUFnQixFQUFFLEdBQUcsS0FBSyxDQUFDO3dCQUMxQyxJQUFJLEVBQUUsR0FBRyxLQUFLLENBQUMsZ0JBQWdCLEVBQUUsR0FBRyxLQUFLLENBQUM7d0JBQzFDLElBQUksRUFBRSxHQUFHLEtBQUssQ0FBQyxnQkFBZ0IsRUFBRSxHQUFHLEtBQUssQ0FBQzt3QkFFMUMsS0FBSyxJQUFJLEtBQUssR0FBRyxDQUFDLEVBQUUsTUFBTSxHQUFHLENBQUMsR0FBSSxLQUFLLEVBQUUsRUFBRSxDQUFDOzRCQUMzQyxRQUFRLENBQUMsUUFBUSxDQUFDLEtBQUssRUFBRSxJQUFJLEVBQUUsQ0FBQyxFQUFFLENBQUMsRUFBRSxDQUFDLEVBQUUsRUFBRSxFQUFFLEVBQUUsRUFBRSxFQUFFLENBQUMsQ0FBQzs0QkFDcEQsSUFBSSxLQUFLLElBQUksU0FBUztnQ0FBRSxNQUFNOzRCQUM5QixJQUFJLEtBQUssR0FBRyxLQUFLLENBQUMsU0FBUyxFQUFFLENBQUM7NEJBQzlCLElBQUksRUFBRSxHQUFHLEtBQUssQ0FBQyxnQkFBZ0IsRUFBRSxHQUFHLEtBQUssQ0FBQzs0QkFDMUMsSUFBSSxFQUFFLEdBQUcsS0FBSyxDQUFDLGdCQUFnQixFQUFFLEdBQUcsS0FBSyxDQUFDOzRCQUMxQyxJQUFJLEVBQUUsR0FBRyxLQUFLLENBQUMsZ0JBQWdCLEVBQUUsR0FBRyxLQUFLLENBQUM7NEJBQzFDLElBQUksR0FBRyxHQUFHLEtBQUssQ0FBQyxnQkFBZ0IsRUFBRSxHQUFHLEtBQUssQ0FBQzs0QkFDM0MsSUFBSSxHQUFHLEdBQUcsS0FBSyxDQUFDLGdCQUFnQixFQUFFLEdBQUcsS0FBSyxDQUFDOzRCQUMzQyxJQUFJLEdBQUcsR0FBRyxLQUFLLENBQUMsZ0JBQWdCLEVBQUUsR0FBRyxLQUFLLENBQUM7NEJBRTNDLFFBQVEsS0FBSyxDQUFDLFFBQVEsRUFBRSxFQUFFLENBQUM7Z0NBQzFCLEtBQUssYUFBYTtvQ0FDakIsUUFBUSxDQUFDLFVBQVUsQ0FBQyxLQUFLLENBQUMsQ0FBQztv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UyxHQUFHLENBQUMsQ0FBQztBQUNwQixNQUFNLFFBQVEsR0FBRyxDQUFDLENBQUM7QUFDbkIsTUFBTSxVQUFVLEdBQUcsQ0FBQyxDQUFDO0FBQ3JCLE1BQU0sU0FBUyxHQUFHLENBQUMsQ0FBQztBQUNwQixNQUFNLFVBQVUsR0FBRyxDQUFDLENBQUM7QUFFckIsTUFBTSxpQkFBaUIsR0FBRyxDQUFDLENBQUM7QUFDNUIsTUFBTSxtQkFBbUIsR0FBRyxDQUFDLENBQUM7QUFFOUIsTUFBTSxhQUFhLEdBQUcsQ0FBQyxDQUFDO0FBQ3hCLE1BQU0sWUFBWSxHQUFHLENBQUMsQ0FBQztBQUN2QixNQUFNLFFBQVEsR0FBRyxDQUFDLENBQUM7QUFFbkIsTUFBTSxlQUFlLEdBQUcsQ0FBQyxDQUFDO0FBQzFCLE1BQU0sZ0JBQWdCLEdBQUcsQ0FBQyxDQUFDO0FBQzNCLE1BQU0sZUFBZSxHQUFHLENBQUMsQ0FBQztBQUMxQixNQUFNLFlBQVksR0FBRyxDQUFDLENBQUM7QUFDdkIsTUFBTSxZQUFZLEdBQUcsQ0FBQyxDQUFDO0FBQ3ZCLE1BQU0sZUFBZSxHQUFHLENBQUMsQ0FBQztBQUMxQixNQUFNLFdBQVcsR0FBRyxDQUFDLENBQUM7QUFDdEIsTUFBTSxhQUFhLEdBQUcsQ0FBQyxDQUFDO0FBRXhCLE1BQU0sWUFBWSxHQUFHLENBQUMsQ0FBQztBQUN2QixNQUFNLGFBQWEsR0FBRyxDQUFDLENBQUM7QUFDeEIsTUFBTSxZQUFZLEdBQUcsQ0FBQyxDQUFDIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBBcHJpbCA1LCAyMDI1LiBSZXBsYWNlcyBhbGwgcHJpb3IgdmVyc2lvbnMuXG4gKlxuICogQ29weXJpZ2h0IChjKSAyMDEzLTIwMjUsIEVzb3RlcmljIFNvZnR3YXJlIExMQ1xuICpcbiAqIEludGVncmF0aW9uIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlIG9yIG90aGVyd2lzZSBjcmVhdGluZ1xuICogZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgaXMgcGVybWl0dGVkIHVuZGVyIHRoZSB0ZXJtcyBhbmRcbiAqIGNvbmRpdGlvbnMgb2YgU2VjdGlvbiAyIG9mIHRoZSBTcGluZSBFZGl0b3IgTGljZW5zZSBBZ3JlZW1lbnQ6XG4gKiBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtZWRpdG9yLWxpY2Vuc2VcbiAqXG4gKiBPdGhlcndpc2UsIGl0IGlzIHBlcm1pdHRlZCB0byBpbnRlZ3JhdGUgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmVcbiAqIG9yIG90aGVyd2lzZSBjcmVhdGUgZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgKGNvbGxlY3RpdmVseSxcbiAqIFwiUHJvZHVjdHNcIiksIHByb3ZpZGVkIHRoYXQgZWFjaCB1c2VyIG9mIHRoZSBQcm9kdWN0cyBtdXN0IG9idGFpbiB0aGVpciBvd25cbiAqIFNwaW5lIEVkaXRvciBsaWNlbnNlIGFuZCByZWRpc3RyaWJ1dGlvbiBvZiB0aGUgUHJvZHVjdHMgaW4gYW55IGZvcm0gbXVzdFxuICogaW5jbHVkZSB0aGlzIGxpY2Vuc2UgYW5kIGNvcHlyaWdodCBub3RpY2UuXG4gKlxuICogVEhFIFNQSU5FIFJVTlRJTUVTIEFSRSBQUk9WSURFRCBCWSBFU09URVJJQyBTT0ZUV0FSRSBMTEMgXCJBUyBJU1wiIEFORCBBTllcbiAqIEVYUFJFU1MgT1IgSU1QTElFRCBXQVJSQU5USUVTLCBJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgVEhFIElNUExJRURcbiAqIFdBUlJBTlRJRVMgT0YgTUVSQ0hBTlRBQklMSVRZIEFORCBGSVRORVNTIEZPUiBBIFBBUlRJQ1VMQVIgUFVSUE9TRSBBUkVcbiAqIERJU0NMQUlNRUQuIElOIE5PIEVWRU5UIFNIQUxMIEVTT1RFUklDIFNPRlRXQVJFIExMQyBCRSBMSUFCTEUgRk9SIEFOWVxuICogRElSRUNULCBJTkRJUkVDVCwgSU5DSURFTlRBTCwgU1BFQ0lBTCwgRVhFTVBMQVJZLCBPUiBDT05TRVFVRU5USUFMIERBTUFHRVNcbiAqIChJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgUFJPQ1VSRU1FTlQgT0YgU1VCU1RJVFVURSBHT09EUyBPUiBTRVJWSUNFUyxcbiAqIEJVU0lORVNTIElOVEVSUlVQVElPTiwgT1IgTE9TUyBPRiBVU0UsIERBVEEsIE9SIFBST0ZJVFMpIEhPV0VWRVIgQ0FVU0VEIEFORFxuICogT04gQU5ZIFRIRU9SWSBPRiBMSUFCSUxJVFksIFdIRVRIRVIgSU4gQ09OVFJBQ1QsIFNUUklDVCBMSUFCSUxJVFksIE9SIFRPUlRcbiAqIChJTkNMVURJTkcgTkVHTElHRU5DRSBPUiBPVEhFUldJU0UpIEFSSVNJTkcgSU4gQU5ZIFdBWSBPVVQgT0YgVEhFIFVTRSBPRlxuICogVEhFIFNQSU5FIFJVTlRJTUVTLCBFVkVOIElGIEFEVklTRUQgT0YgVEhFIFBPU1NJQklMSVRZIE9GIFNVQ0ggREFNQUdFLlxuICoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqL1xuXG5pbXBvcnQgeyBBbmltYXRpb24sIFRpbWVsaW5lLCBJbmhlcml0VGltZWxpbmUsIEF0dGFjaG1lbnRUaW1lbGluZSwgUkdCQVRpbWVsaW5lLCBSR0JUaW1lbGluZSwgUkdCQTJUaW1lbGluZSwgUkdCMlRpbWVsaW5lLCBBbHBoYVRpbWVsaW5lLCBSb3RhdGVUaW1lbGluZSwgVHJhbnNsYXRlVGltZWxpbmUsIFRyYW5zbGF0ZVhUaW1lbGluZSwgVHJhbnNsYXRlWVRpbWVsaW5lLCBTY2FsZVRpbWVsaW5lLCBTY2FsZVhUaW1lbGluZSwgU2NhbGVZVGltZWxpbmUsIFNoZWFyVGltZWxpbmUsIFNoZWFyWFRpbWVsaW5lLCBTaGVhcllUaW1lbGluZSwgSWtDb25zdHJhaW50VGltZWxpbmUsIFRyYW5zZm9ybUNvbnN0cmFpbnRUaW1lbGluZSwgUGF0aENvbnN0cmFpbnRQb3NpdGlvblRpbWVsaW5lLCBQYXRoQ29uc3RyYWludFNwYWNpbmdUaW1lbGluZSwgUGF0aENvbnN0cmFpbnRNaXhUaW1lbGluZSwgRGVmb3JtVGltZWxpbmUsIERyYXdPcmRlclRpbWVsaW5lLCBFdmVudFRpbWVsaW5lLCBDdXJ2ZVRpbWVsaW5lMSwgQ3VydmVUaW1lbGluZTIsIEN1cnZlVGltZWxpbmUsIFNlcXVlbmNlVGltZWxpbmUsIFBoeXNpY3NDb25zdHJhaW50UmVzZXRUaW1lbGluZSwgUGh5c2ljc0NvbnN0cmFpbnRJbmVydGlhVGltZWxpbmUsIFBoeXNpY3NDb25zdHJhaW50U3RyZW5ndGhUaW1lbGluZSwgUGh5c2ljc0NvbnN0cmFpbnREYW1waW5nVGltZWxpbmUsIFBoeXNpY3NDb25zdHJhaW50TWFzc1RpbWVsaW5lLCBQaHlzaWNzQ29uc3RyYWludFdpbmRUaW1lbGluZSwgUGh5c2ljc0NvbnN0cmFpbnRHcmF2aXR5VGltZWxpbmUsIFBoeXNpY3NDb25zdHJhaW50TWl4VGltZWxpbmUgfSBmcm9tIFwiLi9BbmltYXRpb24uanNcIjtcbmltcG9ydCB7IFZlcnRleEF0dGFjaG1lbnQsIEF0dGFjaG1lbnQgfSBmcm9tIFwiLi9hdHRhY2htZW50cy9BdHRhY2htZW50LmpzXCI7XG5pbXBvcnQgeyBBdHRhY2htZW50TG9hZGVyIH0gZnJvbSBcIi4vYXR0YWNobWVudHMvQXR0YWNobWVudExvYWRlci5qc1wiO1xuaW1wb3J0IHsgSGFzVGV4dHVyZVJlZ2lvbiB9IGZyb20gXCIuL2F0dGFjaG1lbnRzL0hhc1RleHR1cmVSZWdpb24uanNcIjtcbmltcG9ydCB7IE1lc2hBdHRhY2htZW50IH0gZnJvbSBcIi4vYXR0YWNobWVudHMvTWVzaEF0dGFjaG1lbnQuanNcIjtcbmltcG9ydCB7IFNlcXVlbmNlLCBTZXF1ZW5jZU1vZGVWYWx1ZXMgfSBmcm9tIFwiLi9hdHRhY2htZW50cy9TZXF1ZW5jZS5qc1wiO1xuaW1wb3J0IHsgQm9uZURhdGEgfSBmcm9tIFwiLi9Cb25lRGF0YS5qc1wiO1xuaW1wb3J0IHsgRXZlbnQgfSBmcm9tIFwiLi9FdmVudC5qc1wiO1xuaW1wb3J0IHsgRXZlbnREYXRhIH0gZnJvbSBcIi4vRXZlbnREYXRhLmpzXCI7XG5pbXBvcnQgeyBJa0NvbnN0cmFpbnREYXRhIH0gZnJvbSBcIi4vSWtDb25zdHJhaW50RGF0YS5qc1wiO1xuaW1wb3J0IHsgUGF0aENvbnN0cmFpbnREYXRhLCBQb3NpdGlvbk1vZGUsIFNwYWNpbmdNb2RlIH0gZnJvbSBcIi4vUGF0aENvbnN0cmFpbnREYXRhLmpzXCI7XG5pbXBvcnQgeyBQaHlzaWNzQ29uc3RyYWludERhdGEgfSBmcm9tIFwiLi9QaHlzaWNzQ29uc3RyYWludERhdGEuanNcIjtcbmltcG9ydCB7IFNrZWxldG9uRGF0YSB9IGZyb20gXCIuL1NrZWxldG9uRGF0YS5qc1wiO1xuaW1wb3J0IHsgU2tpbiB9IGZyb20gXCIuL1NraW4uanNcIjtcbmltcG9ydCB7IFNsb3REYXRhIH0gZnJvbSBcIi4vU2xvdERhdGEuanNcIjtcbmltcG9ydCB7IFRyYW5zZm9ybUNvbnN0cmFpbnREYXRhIH0gZnJvbSBcIi4vVHJhbnNmb3JtQ29uc3RyYWludERhdGEuanNcIjtcbmltcG9ydCB7IENvbG9yLCBVdGlscyB9IGZyb20gXCIuL1V0aWxzLmpzXCI7XG5cbi8qKiBMb2FkcyBza2VsZXRvbiBkYXRhIGluIHRoZSBTcGluZSBiaW5hcnkgZm9ybWF0LlxuICpcbiAqIFNlZSBbU3BpbmUgYmluYXJ5IGZvcm1hdF0oaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLWJpbmFyeS1mb3JtYXQpIGFuZFxuICogW0pTT04gYW5kIGJpbmFyeSBkYXRhXShodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtbG9hZGluZy1za2VsZXRvbi1kYXRhI0pTT04tYW5kLWJpbmFyeS1kYXRhKSBpbiB0aGUgU3BpbmVcbiAqIFJ1bnRpbWVzIEd1aWRlLiAqL1xuZXhwb3J0IGNsYXNzIFNrZWxldG9uQmluYXJ5IHtcblx0LyoqIFNjYWxlcyBib25lIHBvc2l0aW9ucywgaW1hZ2Ugc2l6ZXMsIGFuZCB0cmFuc2xhdGlvbnMgYXMgdGhleSBhcmUgbG9hZGVkLiBUaGlzIGFsbG93cyBkaWZmZXJlbnQgc2l6ZSBpbWFnZXMgdG8gYmUgdXNlZCBhdFxuXHQgKiBydW50aW1lIHRoYW4gd2VyZSB1c2VkIGluIFNwaW5lLlxuXHQgKlxuXHQgKiBTZWUgW1NjYWxpbmddKGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1sb2FkaW5nLXNrZWxldG9uLWRhdGEjU2NhbGluZykgaW4gdGhlIFNwaW5lIFJ1bnRpbWVzIEd1aWRlLiAqL1xuXHRzY2FsZSA9IDE7XG5cblx0YXR0YWNobWVudExvYWRlcjogQXR0YWNobWVudExvYWRlcjtcblx0cHJpdmF0ZSBsaW5rZWRNZXNoZXMgPSBuZXcgQXJyYXk8TGlua2VkTWVzaD4oKTtcblxuXHRjb25zdHJ1Y3RvciAoYXR0YWNobWVudExvYWRlcjogQXR0YWNobWVudExvYWRlcikge1xuXHRcdHRoaXMuYXR0YWNobWVudExvYWRlciA9IGF0dGFjaG1lbnRMb2FkZXI7XG5cdH1cblxuXHRyZWFkU2tlbGV0b25EYXRhIChiaW5hcnk6IFVpbnQ4QXJyYXkgfCBBcnJheUJ1ZmZlcik6IFNrZWxldG9uRGF0YSB7XG5cdFx0bGV0IHNjYWxlID0gdGhpcy5zY2FsZTtcblxuXHRcdGxldCBza2VsZXRvbkRhdGEgPSBuZXcgU2tlbGV0b25EYXRhKCk7XG5cdFx0c2tlbGV0b25EYXRhLm5hbWUgPSBcIlwiOyAvLyBCT1pPXG5cblx0XHRsZXQgaW5wdXQgPSBuZXcgQmluYXJ5SW5wdXQoYmluYXJ5KTtcblxuXHRcdGxldCBsb3dIYXNoID0gaW5wdXQucmVhZEludDMyKCk7XG5cdFx0bGV0IGhpZ2hIYXNoID0gaW5wdXQucmVhZEludDMyKCk7XG5cdFx0c2tlbGV0b25EYXRhLmhhc2ggPSBoaWdoSGFzaCA9PSAwICYmIGxvd0hhc2ggPT0gMCA/IG51bGwgOiBoaWdoSGFzaC50b1N0cmluZygxNikgKyBsb3dIYXNoLnRvU3RyaW5nKDE2KTtcblx0XHRza2VsZXRvbkRhdGEudmVyc2lvbiA9IGlucHV0LnJlYWRTdHJpbmcoKTtcblx0XHRza2VsZXRvbkRhdGEueCA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdHNrZWxldG9uRGF0YS55ID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0c2tlbGV0b25EYXRhLndpZHRoID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0c2tlbGV0b25EYXRhLmhlaWdodCA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdHNrZWxldG9uRGF0YS5yZWZlcmVuY2VTY2FsZSA9IGlucHV0LnJlYWRGbG9hdCgpICogc2NhbGU7XG5cblx0XHRsZXQgbm9uZXNzZW50aWFsID0gaW5wdXQucmVhZEJvb2xlYW4oKTtcblx0XHRpZiAobm9uZXNzZW50aWFsKSB7XG5cdFx0XHRza2VsZXRvbkRhdGEuZnBzID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRza2VsZXRvbkRhdGEuaW1hZ2VzUGF0aCA9IGlucHV0LnJlYWRTdHJpbmcoKTtcblx0XHRcdHNrZWxldG9uRGF0YS5hdWRpb1BhdGggPSBpbnB1dC5yZWFkU3RyaW5nKCk7XG5cdFx0fVxuXG5cdFx0bGV0IG4gPSAwO1xuXHRcdC8vIFN0cmluZ3MuXG5cdFx0biA9IGlucHV0LnJlYWRJbnQodHJ1ZSlcblx0XHRmb3IgKGxldCBpID0gMDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IHN0ciA9IGlucHV0LnJlYWRTdHJpbmcoKTtcblx0XHRcdGlmICghc3RyKSB0aHJvdyBuZXcgRXJyb3IoXCJTdHJpbmcgaW4gc3RyaW5nIHRhYmxlIG11c3Qgbm90IGJlIG51bGwuXCIpO1xuXHRcdFx0aW5wdXQuc3RyaW5ncy5wdXNoKHN0cik7XG5cdFx0fVxuXG5cdFx0Ly8gQm9uZXMuXG5cdFx0biA9IGlucHV0LnJlYWRJbnQodHJ1ZSlcblx0XHRmb3IgKGxldCBpID0gMDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IG5hbWUgPSBpbnB1dC5yZWFkU3RyaW5nKCk7XG5cdFx0XHRpZiAoIW5hbWUpIHRocm93IG5ldyBFcnJvcihcIkJvbmUgbmFtZSBtdXN0IG5vdCBiZSBudWxsLlwiKTtcblx0XHRcdGxldCBwYXJlbnQgPSBpID09IDAgPyBudWxsIDogc2tlbGV0b25EYXRhLmJvbmVzW2lucHV0LnJlYWRJbnQodHJ1ZSldO1xuXHRcdFx0bGV0IGRhdGEgPSBuZXcgQm9uZURhdGEoaSwgbmFtZSwgcGFyZW50KTtcblx0XHRcdGRhdGEucm90YXRpb24gPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGRhdGEueCA9IGlucHV0LnJlYWRGbG9hdCgpICogc2NhbGU7XG5cdFx0XHRkYXRhLnkgPSBpbnB1dC5yZWFkRmxvYXQoKSAqIHNjYWxlO1xuXHRcdFx0ZGF0YS5zY2FsZVggPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGRhdGEuc2NhbGVZID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRkYXRhLnNoZWFyWCA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0ZGF0YS5zaGVhclkgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGRhdGEubGVuZ3RoID0gaW5wdXQucmVhZEZsb2F0KCkgKiBzY2FsZTtcblx0XHRcdGRhdGEuaW5oZXJpdCA9IGlucHV0LnJlYWRCeXRlKCk7XG5cdFx0XHRkYXRhLnNraW5SZXF1aXJlZCA9IGlucHV0LnJlYWRCb29sZWFuKCk7XG5cdFx0XHRpZiAobm9uZXNzZW50aWFsKSB7XG5cdFx0XHRcdENvbG9yLnJnYmE4ODg4VG9Db2xvcihkYXRhLmNvbG9yLCBpbnB1dC5yZWFkSW50MzIoKSk7XG5cdFx0XHRcdGRhdGEuaWNvbiA9IGlucHV0LnJlYWRTdHJpbmcoKSA/PyB1bmRlZmluZWQ7XG5cdFx0XHRcdGRhdGEudmlzaWJsZSA9IGlucHV0LnJlYWRCb29sZWFuKCk7XG5cdFx0XHR9XG5cdFx0XHRza2VsZXRvbkRhdGEuYm9uZXMucHVzaChkYXRhKTtcblx0XHR9XG5cblx0XHQvLyBTbG90cy5cblx0XHRuID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRmb3IgKGxldCBpID0gMDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IHNsb3ROYW1lID0gaW5wdXQucmVhZFN0cmluZygpO1xuXHRcdFx0aWYgKCFzbG90TmFtZSkgdGhyb3cgbmV3IEVycm9yKFwiU2xvdCBuYW1lIG11c3Qgbm90IGJlIG51bGwuXCIpO1xuXHRcdFx0bGV0IGJvbmVEYXRhID0gc2tlbGV0b25EYXRhLmJvbmVzW2lucHV0LnJlYWRJbnQodHJ1ZSldO1xuXHRcdFx0bGV0IGRhdGEgPSBuZXcgU2xvdERhdGEoaSwgc2xvdE5hbWUsIGJvbmVEYXRhKTtcblx0XHRcdENvbG9yLnJnYmE4ODg4VG9Db2xvcihkYXRhLmNvbG9yLCBpbnB1dC5yZWFkSW50MzIoKSk7XG5cblx0XHRcdGxldCBkYXJrQ29sb3IgPSBpbnB1dC5yZWFkSW50MzIoKTtcblx0XHRcdGlmIChkYXJrQ29sb3IgIT0gLTEpIENvbG9yLnJnYjg4OFRvQ29sb3IoZGF0YS5kYXJrQ29sb3IgPSBuZXcgQ29sb3IoKSwgZGFya0NvbG9yKTtcblxuXHRcdFx0ZGF0YS5hdHRhY2htZW50TmFtZSA9IGlucHV0LnJlYWRTdHJpbmdSZWYoKTtcblx0XHRcdGRhdGEuYmxlbmRNb2RlID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdGlmIChub25lc3NlbnRpYWwpIGRhdGEudmlzaWJsZSA9IGlucHV0LnJlYWRCb29sZWFuKCk7XG5cdFx0XHRza2VsZXRvbkRhdGEuc2xvdHMucHVzaChkYXRhKTtcblx0XHR9XG5cblx0XHQvLyBJSyBjb25zdHJhaW50cy5cblx0XHRuID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRmb3IgKGxldCBpID0gMCwgbm47IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBuYW1lID0gaW5wdXQucmVhZFN0cmluZygpO1xuXHRcdFx0aWYgKCFuYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJJSyBjb25zdHJhaW50IGRhdGEgbmFtZSBtdXN0IG5vdCBiZSBudWxsLlwiKTtcblx0XHRcdGxldCBkYXRhID0gbmV3IElrQ29uc3RyYWludERhdGEobmFtZSk7XG5cdFx0XHRkYXRhLm9yZGVyID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdG5uID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCBubjsgaWkrKylcblx0XHRcdFx0ZGF0YS5ib25lcy5wdXNoKHNrZWxldG9uRGF0YS5ib25lc1tpbnB1dC5yZWFkSW50KHRydWUpXSk7XG5cdFx0XHRkYXRhLnRhcmdldCA9IHNrZWxldG9uRGF0YS5ib25lc1tpbnB1dC5yZWFkSW50KHRydWUpXTtcblx0XHRcdGxldCBmbGFncyA9IGlucHV0LnJlYWRCeXRlKCk7XG5cdFx0XHRkYXRhLnNraW5SZXF1aXJlZCA9IChmbGFncyAmIDEpICE9IDA7XG5cdFx0XHRkYXRhLmJlbmREaXJlY3Rpb24gPSAoZmxhZ3MgJiAyKSAhPSAwID8gMSA6IC0xO1xuXHRcdFx0ZGF0YS5jb21wcmVzcyA9IChmbGFncyAmIDQpICE9IDA7XG5cdFx0XHRkYXRhLnN0cmV0Y2ggPSAoZmxhZ3MgJiA4KSAhPSAwO1xuXHRcdFx0ZGF0YS51bmlmb3JtID0gKGZsYWdzICYgMTYpICE9IDA7XG5cdFx0XHRpZiAoKGZsYWdzICYgMzIpICE9IDApIGRhdGEubWl4ID0gKGZsYWdzICYgNjQpICE9IDAgPyBpbnB1dC5yZWFkRmxvYXQoKSA6IDE7XG5cdFx0XHRpZiAoKGZsYWdzICYgMTI4KSAhPSAwKSBkYXRhLnNvZnRuZXNzID0gaW5wdXQucmVhZEZsb2F0KCkgKiBzY2FsZTtcblx0XHRcdHNrZWxldG9uRGF0YS5pa0NvbnN0cmFpbnRzLnB1c2goZGF0YSk7XG5cdFx0fVxuXG5cdFx0Ly8gVHJhbnNmb3JtIGNvbnN0cmFpbnRzLlxuXHRcdG4gPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdGZvciAobGV0IGkgPSAwLCBubjsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IG5hbWUgPSBpbnB1dC5yZWFkU3RyaW5nKCk7XG5cdFx0XHRpZiAoIW5hbWUpIHRocm93IG5ldyBFcnJvcihcIlRyYW5zZm9ybSBjb25zdHJhaW50IGRhdGEgbmFtZSBtdXN0IG5vdCBiZSBudWxsLlwiKTtcblx0XHRcdGxldCBkYXRhID0gbmV3IFRyYW5zZm9ybUNvbnN0cmFpbnREYXRhKG5hbWUpO1xuXHRcdFx0ZGF0YS5vcmRlciA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRubiA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgbm47IGlpKyspXG5cdFx0XHRcdGRhdGEuYm9uZXMucHVzaChza2VsZXRvbkRhdGEuYm9uZXNbaW5wdXQucmVhZEludCh0cnVlKV0pO1xuXHRcdFx0ZGF0YS50YXJnZXQgPSBza2VsZXRvbkRhdGEuYm9uZXNbaW5wdXQucmVhZEludCh0cnVlKV07XG5cdFx0XHRsZXQgZmxhZ3MgPSBpbnB1dC5yZWFkQnl0ZSgpO1xuXHRcdFx0ZGF0YS5za2luUmVxdWlyZWQgPSAoZmxhZ3MgJiAxKSAhPSAwO1xuXHRcdFx0ZGF0YS5sb2NhbCA9IChmbGFncyAmIDIpICE9IDA7XG5cdFx0XHRkYXRhLnJlbGF0aXZlID0gKGZsYWdzICYgNCkgIT0gMDtcblx0XHRcdGlmICgoZmxhZ3MgJiA4KSAhPSAwKSBkYXRhLm9mZnNldFJvdGF0aW9uID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRpZiAoKGZsYWdzICYgMTYpICE9IDApIGRhdGEub2Zmc2V0WCA9IGlucHV0LnJlYWRGbG9hdCgpICogc2NhbGU7XG5cdFx0XHRpZiAoKGZsYWdzICYgMzIpICE9IDApIGRhdGEub2Zmc2V0WSA9IGlucHV0LnJlYWRGbG9hdCgpICogc2NhbGU7XG5cdFx0XHRpZiAoKGZsYWdzICYgNjQpICE9IDApIGRhdGEub2Zmc2V0U2NhbGVYID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRpZiAoKGZsYWdzICYgMTI4KSAhPSAwKSBkYXRhLm9mZnNldFNjYWxlWSA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0ZmxhZ3MgPSBpbnB1dC5yZWFkQnl0ZSgpO1xuXHRcdFx0aWYgKChmbGFncyAmIDEpICE9IDApIGRhdGEub2Zmc2V0U2hlYXJZID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRpZiAoKGZsYWdzICYgMikgIT0gMCkgZGF0YS5taXhSb3RhdGUgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGlmICgoZmxhZ3MgJiA0KSAhPSAwKSBkYXRhLm1peFggPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGlmICgoZmxhZ3MgJiA4KSAhPSAwKSBkYXRhLm1peFkgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGlmICgoZmxhZ3MgJiAxNikgIT0gMCkgZGF0YS5taXhTY2FsZVggPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGlmICgoZmxhZ3MgJiAzMikgIT0gMCkgZGF0YS5taXhTY2FsZVkgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGlmICgoZmxhZ3MgJiA2NCkgIT0gMCkgZGF0YS5taXhTaGVhclkgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdHNrZWxldG9uRGF0YS50cmFuc2Zvcm1Db25zdHJhaW50cy5wdXNoKGRhdGEpO1xuXHRcdH1cblxuXHRcdC8vIFBhdGggY29uc3RyYWludHMuXG5cdFx0biA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG5uOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRsZXQgbmFtZSA9IGlucHV0LnJlYWRTdHJpbmcoKTtcblx0XHRcdGlmICghbmFtZSkgdGhyb3cgbmV3IEVycm9yKFwiUGF0aCBjb25zdHJhaW50IGRhdGEgbmFtZSBtdXN0IG5vdCBiZSBudWxsLlwiKTtcblx0XHRcdGxldCBkYXRhID0gbmV3IFBhdGhDb25zdHJhaW50RGF0YShuYW1lKTtcblx0XHRcdGRhdGEub3JkZXIgPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdFx0ZGF0YS5za2luUmVxdWlyZWQgPSBpbnB1dC5yZWFkQm9vbGVhbigpO1xuXHRcdFx0bm4gPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IG5uOyBpaSsrKVxuXHRcdFx0XHRkYXRhLmJvbmVzLnB1c2goc2tlbGV0b25EYXRhLmJvbmVzW2lucHV0LnJlYWRJbnQodHJ1ZSldKTtcblx0XHRcdGRhdGEudGFyZ2V0ID0gc2tlbGV0b25EYXRhLnNsb3RzW2lucHV0LnJlYWRJbnQodHJ1ZSldO1xuXHRcdFx0Y29uc3QgZmxhZ3MgPSBpbnB1dC5yZWFkQnl0ZSgpO1xuXHRcdFx0ZGF0YS5wb3NpdGlvbk1vZGUgPSBmbGFncyAmIDE7XG5cdFx0XHRkYXRhLnNwYWNpbmdNb2RlID0gKGZsYWdzID4+IDEpICYgMztcblx0XHRcdGRhdGEucm90YXRlTW9kZSA9IChmbGFncyA+PiAzKSAmIDM7XG5cdFx0XHRpZiAoKGZsYWdzICYgMTI4KSAhPSAwKSBkYXRhLm9mZnNldFJvdGF0aW9uID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRkYXRhLnBvc2l0aW9uID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRpZiAoZGF0YS5wb3NpdGlvbk1vZGUgPT0gUG9zaXRpb25Nb2RlLkZpeGVkKSBkYXRhLnBvc2l0aW9uICo9IHNjYWxlO1xuXHRcdFx0ZGF0YS5zcGFjaW5nID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRpZiAoZGF0YS5zcGFjaW5nTW9kZSA9PSBTcGFjaW5nTW9kZS5MZW5ndGggfHwgZGF0YS5zcGFjaW5nTW9kZSA9PSBTcGFjaW5nTW9kZS5GaXhlZCkgZGF0YS5zcGFjaW5nICo9IHNjYWxlO1xuXHRcdFx0ZGF0YS5taXhSb3RhdGUgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGRhdGEubWl4WCA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0ZGF0YS5taXhZID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRza2VsZXRvbkRhdGEucGF0aENvbnN0cmFpbnRzLnB1c2goZGF0YSk7XG5cdFx0fVxuXG5cdFx0Ly8gUGh5c2ljcyBjb25zdHJhaW50cy5cblx0XHRuID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRmb3IgKGxldCBpID0gMCwgbm47IGkgPCBuOyBpKyspIHtcblx0XHRcdGNvbnN0IG5hbWUgPSBpbnB1dC5yZWFkU3RyaW5nKCk7XG5cdFx0XHRpZiAoIW5hbWUpIHRocm93IG5ldyBFcnJvcihcIlBoeXNpY3MgY29uc3RyYWludCBkYXRhIG5hbWUgbXVzdCBub3QgYmUgbnVsbC5cIik7XG5cdFx0XHRjb25zdCBkYXRhID0gbmV3IFBoeXNpY3NDb25zdHJhaW50RGF0YShuYW1lKTtcblx0XHRcdGRhdGEub3JkZXIgPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdFx0ZGF0YS5ib25lID0gc2tlbGV0b25EYXRhLmJvbmVzW2lucHV0LnJlYWRJbnQodHJ1ZSldO1xuXHRcdFx0bGV0IGZsYWdzID0gaW5wdXQucmVhZEJ5dGUoKTtcblx0XHRcdGRhdGEuc2tpblJlcXVpcmVkID0gKGZsYWdzICYgMSkgIT0gMDtcblx0XHRcdGlmICgoZmxhZ3MgJiAyKSAhPSAwKSBkYXRhLnggPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGlmICgoZmxhZ3MgJiA0KSAhPSAwKSBkYXRhLnkgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGlmICgoZmxhZ3MgJiA4KSAhPSAwKSBkYXRhLnJvdGF0ZSA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0aWYgKChmbGFncyAmIDE2KSAhPSAwKSBkYXRhLnNjYWxlWCA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0aWYgKChmbGFncyAmIDMyKSAhPSAwKSBkYXRhLnNoZWFyWCA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0ZGF0YS5saW1pdCA9ICgoZmxhZ3MgJiA2NCkgIT0gMCA/IGlucHV0LnJlYWRGbG9hdCgpIDogNTAwMCkgKiBzY2FsZTtcblx0XHRcdGRhdGEuc3RlcCA9IDEgLyBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCk7XG5cdFx0XHRkYXRhLmluZXJ0aWEgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGRhdGEuc3RyZW5ndGggPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdGRhdGEuZGFtcGluZyA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0ZGF0YS5tYXNzSW52ZXJzZSA9IChmbGFncyAmIDEyOCkgIT0gMCA/IGlucHV0LnJlYWRGbG9hdCgpIDogMTtcblx0XHRcdGRhdGEud2luZCA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0ZGF0YS5ncmF2aXR5ID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRmbGFncyA9IGlucHV0LnJlYWRCeXRlKCk7XG5cdFx0XHRpZiAoKGZsYWdzICYgMSkgIT0gMCkgZGF0YS5pbmVydGlhR2xvYmFsID0gdHJ1ZTtcblx0XHRcdGlmICgoZmxhZ3MgJiAyKSAhPSAwKSBkYXRhLnN0cmVuZ3RoR2xvYmFsID0gdHJ1ZTtcblx0XHRcdGlmICgoZmxhZ3MgJiA0KSAhPSAwKSBkYXRhLmRhbXBpbmdHbG9iYWwgPSB0cnVlO1xuXHRcdFx0aWYgKChmbGFncyAmIDgpICE9IDApIGRhdGEubWFzc0dsb2JhbCA9IHRydWU7XG5cdFx0XHRpZiAoKGZsYWdzICYgMTYpICE9IDApIGRhdGEud2luZEdsb2JhbCA9IHRydWU7XG5cdFx0XHRpZiAoKGZsYWdzICYgMzIpICE9IDApIGRhdGEuZ3Jhdml0eUdsb2JhbCA9IHRydWU7XG5cdFx0XHRpZiAoKGZsYWdzICYgNjQpICE9IDApIGRhdGEubWl4R2xvYmFsID0gdHJ1ZTtcblx0XHRcdGRhdGEubWl4ID0gKGZsYWdzICYgMTI4KSAhPSAwID8gaW5wdXQucmVhZEZsb2F0KCkgOiAxO1xuXHRcdFx0c2tlbGV0b25EYXRhLnBoeXNpY3NDb25zdHJhaW50cy5wdXNoKGRhdGEpO1xuXHRcdH1cblxuXHRcdC8vIERlZmF1bHQgc2tpbi5cblx0XHRsZXQgZGVmYXVsdFNraW4gPSB0aGlzLnJlYWRTa2luKGlucHV0LCBza2VsZXRvbkRhdGEsIHRydWUsIG5vbmVzc2VudGlhbCk7XG5cdFx0aWYgKGRlZmF1bHRTa2luKSB7XG5cdFx0XHRza2VsZXRvbkRhdGEuZGVmYXVsdFNraW4gPSBkZWZhdWx0U2tpbjtcblx0XHRcdHNrZWxldG9uRGF0YS5za2lucy5wdXNoKGRlZmF1bHRTa2luKTtcblx0XHR9XG5cblx0XHQvLyBTa2lucy5cblx0XHR7XG5cdFx0XHRsZXQgaSA9IHNrZWxldG9uRGF0YS5za2lucy5sZW5ndGg7XG5cdFx0XHRVdGlscy5zZXRBcnJheVNpemUoc2tlbGV0b25EYXRhLnNraW5zLCBuID0gaSArIGlucHV0LnJlYWRJbnQodHJ1ZSkpO1xuXHRcdFx0Zm9yICg7IGkgPCBuOyBpKyspIHtcblx0XHRcdFx0bGV0IHNraW4gPSB0aGlzLnJlYWRTa2luKGlucHV0LCBza2VsZXRvbkRhdGEsIGZhbHNlLCBub25lc3NlbnRpYWwpO1xuXHRcdFx0XHRpZiAoIXNraW4pIHRocm93IG5ldyBFcnJvcihcInJlYWRTa2luKCkgc2hvdWxkIG5vdCBoYXZlIHJldHVybmVkIG51bGwuXCIpO1xuXHRcdFx0XHRza2VsZXRvbkRhdGEuc2tpbnNbaV0gPSBza2luO1xuXHRcdFx0fVxuXHRcdH1cblxuXHRcdC8vIExpbmtlZCBtZXNoZXMuXG5cdFx0biA9IHRoaXMubGlua2VkTWVzaGVzLmxlbmd0aDtcblx0XHRmb3IgKGxldCBpID0gMDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGxpbmtlZE1lc2ggPSB0aGlzLmxpbmtlZE1lc2hlc1tpXTtcblx0XHRcdGNvbnN0IHNraW4gPSBza2VsZXRvbkRhdGEuc2tpbnNbbGlua2VkTWVzaC5za2luSW5kZXhdO1xuXHRcdFx0aWYgKCFsaW5rZWRNZXNoLnBhcmVudCkgdGhyb3cgbmV3IEVycm9yKFwiTGlua2VkIG1lc2ggcGFyZW50IG11c3Qgbm90IGJlIG51bGxcIik7XG5cdFx0XHRsZXQgcGFyZW50ID0gc2tpbi5nZXRBdHRhY2htZW50KGxpbmtlZE1lc2guc2xvdEluZGV4LCBsaW5rZWRNZXNoLnBhcmVudCk7XG5cdFx0XHRpZiAoIXBhcmVudCkgdGhyb3cgbmV3IEVycm9yKGBQYXJlbnQgbWVzaCBub3QgZm91bmQ6ICR7bGlua2VkTWVzaC5wYXJlbnR9YCk7XG5cdFx0XHRsaW5rZWRNZXNoLm1lc2gudGltZWxpbmVBdHRhY2htZW50ID0gbGlua2VkTWVzaC5pbmhlcml0VGltZWxpbmUgPyBwYXJlbnQgYXMgVmVydGV4QXR0YWNobWVudCA6IGxpbmtlZE1lc2gubWVzaDtcblx0XHRcdGxpbmtlZE1lc2gubWVzaC5zZXRQYXJlbnRNZXNoKHBhcmVudCBhcyBNZXNoQXR0YWNobWVudCk7XG5cdFx0XHRpZiAobGlua2VkTWVzaC5tZXNoLnJlZ2lvbiAhPSBudWxsKSBsaW5rZWRNZXNoLm1lc2gudXBkYXRlUmVnaW9uKCk7XG5cdFx0fVxuXHRcdHRoaXMubGlua2VkTWVzaGVzLmxlbmd0aCA9IDA7XG5cblx0XHQvLyBFdmVudHMuXG5cdFx0biA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBldmVudE5hbWUgPSBpbnB1dC5yZWFkU3RyaW5nKCk7XG5cdFx0XHRpZiAoIWV2ZW50TmFtZSkgdGhyb3cgbmV3IEVycm9yKFwiRXZlbnQgZGF0YSBuYW1lIG11c3Qgbm90IGJlIG51bGxcIik7XG5cdFx0XHRsZXQgZGF0YSA9IG5ldyBFdmVudERhdGEoZXZlbnROYW1lKTtcblx0XHRcdGRhdGEuaW50VmFsdWUgPSBpbnB1dC5yZWFkSW50KGZhbHNlKTtcblx0XHRcdGRhdGEuZmxvYXRWYWx1ZSA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0ZGF0YS5zdHJpbmdWYWx1ZSA9IGlucHV0LnJlYWRTdHJpbmcoKTtcblx0XHRcdGRhdGEuYXVkaW9QYXRoID0gaW5wdXQucmVhZFN0cmluZygpO1xuXHRcdFx0aWYgKGRhdGEuYXVkaW9QYXRoKSB7XG5cdFx0XHRcdGRhdGEudm9sdW1lID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdGRhdGEuYmFsYW5jZSA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0fVxuXHRcdFx0c2tlbGV0b25EYXRhLmV2ZW50cy5wdXNoKGRhdGEpO1xuXHRcdH1cblxuXHRcdC8vIEFuaW1hdGlvbnMuXG5cdFx0biA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBhbmltYXRpb25OYW1lID0gaW5wdXQucmVhZFN0cmluZygpO1xuXHRcdFx0aWYgKCFhbmltYXRpb25OYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJBbmltYXRpbyBuYW1lIG11c3Qgbm90IGJlIG51bGwuXCIpO1xuXHRcdFx0c2tlbGV0b25EYXRhLmFuaW1hdGlvbnMucHVzaCh0aGlzLnJlYWRBbmltYXRpb24oaW5wdXQsIGFuaW1hdGlvbk5hbWUsIHNrZWxldG9uRGF0YSkpO1xuXHRcdH1cblx0XHRyZXR1cm4gc2tlbGV0b25EYXRhO1xuXHR9XG5cblx0cHJpdmF0ZSByZWFkU2tpbiAoaW5wdXQ6IEJpbmFyeUlucHV0LCBza2VsZXRvbkRhdGE6IFNrZWxldG9uRGF0YSwgZGVmYXVsdFNraW46IGJvb2xlYW4sIG5vbmVzc2VudGlhbDogYm9vbGVhbik6IFNraW4gfCBudWxsIHtcblx0XHRsZXQgc2tpbiA9IG51bGw7XG5cdFx0bGV0IHNsb3RDb3VudCA9IDA7XG5cblx0XHRpZiAoZGVmYXVsdFNraW4pIHtcblx0XHRcdHNsb3RDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSlcblx0XHRcdGlmIChzbG90Q291bnQgPT0gMCkgcmV0dXJuIG51bGw7XG5cdFx0XHRza2luID0gbmV3IFNraW4oXCJkZWZhdWx0XCIpO1xuXHRcdH0gZWxzZSB7XG5cdFx0XHRsZXQgc2tpbk5hbWUgPSBpbnB1dC5yZWFkU3RyaW5nKCk7XG5cdFx0XHRpZiAoIXNraW5OYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJTa2luIG5hbWUgbXVzdCBub3QgYmUgbnVsbC5cIik7XG5cdFx0XHRza2luID0gbmV3IFNraW4oc2tpbk5hbWUpO1xuXHRcdFx0aWYgKG5vbmVzc2VudGlhbCkgQ29sb3IucmdiYTg4ODhUb0NvbG9yKHNraW4uY29sb3IsIGlucHV0LnJlYWRJbnQzMigpKTtcblx0XHRcdHNraW4uYm9uZXMubGVuZ3RoID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdGZvciAobGV0IGkgPSAwLCBuID0gc2tpbi5ib25lcy5sZW5ndGg7IGkgPCBuOyBpKyspXG5cdFx0XHRcdHNraW4uYm9uZXNbaV0gPSBza2VsZXRvbkRhdGEuYm9uZXNbaW5wdXQucmVhZEludCh0cnVlKV07XG5cblx0XHRcdGZvciAobGV0IGkgPSAwLCBuID0gaW5wdXQucmVhZEludCh0cnVlKTsgaSA8IG47IGkrKylcblx0XHRcdFx0c2tpbi5jb25zdHJhaW50cy5wdXNoKHNrZWxldG9uRGF0YS5pa0NvbnN0cmFpbnRzW2lucHV0LnJlYWRJbnQodHJ1ZSldKTtcblx0XHRcdGZvciAobGV0IGkgPSAwLCBuID0gaW5wdXQucmVhZEludCh0cnVlKTsgaSA8IG47IGkrKylcblx0XHRcdFx0c2tpbi5jb25zdHJhaW50cy5wdXNoKHNrZWxldG9uRGF0YS50cmFuc2Zvcm1Db25zdHJhaW50c1tpbnB1dC5yZWFkSW50KHRydWUpXSk7XG5cdFx0XHRmb3IgKGxldCBpID0gMCwgbiA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7IGkgPCBuOyBpKyspXG5cdFx0XHRcdHNraW4uY29uc3RyYWludHMucHVzaChza2VsZXRvbkRhdGEucGF0aENvbnN0cmFpbnRzW2lucHV0LnJlYWRJbnQodHJ1ZSldKTtcblx0XHRcdGZvciAobGV0IGkgPSAwLCBuID0gaW5wdXQucmVhZEludCh0cnVlKTsgaSA8IG47IGkrKylcblx0XHRcdFx0c2tpbi5jb25zdHJhaW50cy5wdXNoKHNrZWxldG9uRGF0YS5waHlzaWNzQ29uc3RyYWludHNbaW5wdXQucmVhZEludCh0cnVlKV0pO1xuXG5cdFx0XHRzbG90Q291bnQgPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdH1cblxuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgc2xvdENvdW50OyBpKyspIHtcblx0XHRcdGxldCBzbG90SW5kZXggPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdFx0Zm9yIChsZXQgaWkgPSAwLCBubiA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7IGlpIDwgbm47IGlpKyspIHtcblx0XHRcdFx0bGV0IG5hbWUgPSBpbnB1dC5yZWFkU3RyaW5nUmVmKCk7XG5cdFx0XHRcdGlmICghbmFtZSlcblx0XHRcdFx0XHR0aHJvdyBuZXcgRXJyb3IoXCJBdHRhY2htZW50IG5hbWUgbXVzdCBub3QgYmUgbnVsbFwiKTtcblx0XHRcdFx0bGV0IGF0dGFjaG1lbnQgPSB0aGlzLnJlYWRBdHRhY2htZW50KGlucHV0LCBza2VsZXRvbkRhdGEsIHNraW4sIHNsb3RJbmRleCwgbmFtZSwgbm9uZXNzZW50aWFsKTtcblx0XHRcdFx0aWYgKGF0dGFjaG1lbnQpIHNraW4uc2V0QXR0YWNobWVudChzbG90SW5kZXgsIG5hbWUsIGF0dGFjaG1lbnQpO1xuXHRcdFx0fVxuXHRcdH1cblx0XHRyZXR1cm4gc2tpbjtcblx0fVxuXG5cdHByaXZhdGUgcmVhZEF0dGFjaG1lbnQgKGlucHV0OiBCaW5hcnlJbnB1dCwgc2tlbGV0b25EYXRhOiBTa2VsZXRvbkRhdGEsIHNraW46IFNraW4sIHNsb3RJbmRleDogbnVtYmVyLCBhdHRhY2htZW50TmFtZTogc3RyaW5nIHwgbnVsbCB8IHVuZGVmaW5lZCwgbm9uZXNzZW50aWFsOiBib29sZWFuKTogQXR0YWNobWVudCB8IG51bGwge1xuXHRcdGxldCBzY2FsZSA9IHRoaXMuc2NhbGU7XG5cblx0XHRsZXQgZmxhZ3MgPSBpbnB1dC5yZWFkQnl0ZSgpO1xuXHRcdGNvbnN0IG5hbWUgPSAoZmxhZ3MgJiA4KSAhPSAwID8gaW5wdXQucmVhZFN0cmluZ1JlZigpIDogYXR0YWNobWVudE5hbWU7XG5cdFx0aWYgKCFuYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJBdHRhY2htZW50IG5hbWUgbXVzdCBub3QgYmUgbnVsbFwiKTtcblx0XHRzd2l0Y2ggKChmbGFncyAmIDBiMTExKSBhcyBBdHRhY2htZW50VHlwZSkgeyAvLyBCVUc/XG5cdFx0XHRjYXNlIEF0dGFjaG1lbnRUeXBlLlJlZ2lvbjoge1xuXHRcdFx0XHRsZXQgcGF0aCA9IChmbGFncyAmIDE2KSAhPSAwID8gaW5wdXQucmVhZFN0cmluZ1JlZigpIDogbnVsbDtcblx0XHRcdFx0Y29uc3QgY29sb3IgPSAoZmxhZ3MgJiAzMikgIT0gMCA/IGlucHV0LnJlYWRJbnQzMigpIDogMHhmZmZmZmZmZjtcblx0XHRcdFx0Y29uc3Qgc2VxdWVuY2UgPSAoZmxhZ3MgJiA2NCkgIT0gMCA/IHRoaXMucmVhZFNlcXVlbmNlKGlucHV0KSA6IG51bGw7XG5cdFx0XHRcdGxldCByb3RhdGlvbiA9IChmbGFncyAmIDEyOCkgIT0gMCA/IGlucHV0LnJlYWRGbG9hdCgpIDogMDtcblx0XHRcdFx0bGV0IHggPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdFx0bGV0IHkgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdFx0bGV0IHNjYWxlWCA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHRsZXQgc2NhbGVZID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdGxldCB3aWR0aCA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHRsZXQgaGVpZ2h0ID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cblx0XHRcdFx0aWYgKCFwYXRoKSBwYXRoID0gbmFtZTtcblx0XHRcdFx0bGV0IHJlZ2lvbiA9IHRoaXMuYXR0YWNobWVudExvYWRlci5uZXdSZWdpb25BdHRhY2htZW50KHNraW4sIG5hbWUsIHBhdGgsIHNlcXVlbmNlKTtcblx0XHRcdFx0aWYgKCFyZWdpb24pIHJldHVybiBudWxsO1xuXHRcdFx0XHRyZWdpb24ucGF0aCA9IHBhdGg7XG5cdFx0XHRcdHJlZ2lvbi54ID0geCAqIHNjYWxlO1xuXHRcdFx0XHRyZWdpb24ueSA9IHkgKiBzY2FsZTtcblx0XHRcdFx0cmVnaW9uLnNjYWxlWCA9IHNjYWxlWDtcblx0XHRcdFx0cmVnaW9uLnNjYWxlWSA9IHNjYWxlWTtcblx0XHRcdFx0cmVnaW9uLnJvdGF0aW9uID0gcm90YXRpb247XG5cdFx0XHRcdHJlZ2lvbi53aWR0aCA9IHdpZHRoICogc2NhbGU7XG5cdFx0XHRcdHJlZ2lvbi5oZWlnaHQgPSBoZWlnaHQgKiBzY2FsZTtcblx0XHRcdFx0Q29sb3IucmdiYTg4ODhUb0NvbG9yKHJlZ2lvbi5jb2xvciwgY29sb3IpO1xuXHRcdFx0XHRyZWdpb24uc2VxdWVuY2UgPSBzZXF1ZW5jZTtcblx0XHRcdFx0aWYgKHNlcXVlbmNlID09IG51bGwpIHJlZ2lvbi51cGRhdGVSZWdpb24oKTtcblx0XHRcdFx0cmV0dXJuIHJlZ2lvbjtcblx0XHRcdH1cblx0XHRcdGNhc2UgQXR0YWNobWVudFR5cGUuQm91bmRpbmdCb3g6IHtcblx0XHRcdFx0bGV0IHZlcnRpY2VzID0gdGhpcy5yZWFkVmVydGljZXMoaW5wdXQsIChmbGFncyAmIDE2KSAhPSAwKTtcblx0XHRcdFx0bGV0IGNvbG9yID0gbm9uZXNzZW50aWFsID8gaW5wdXQucmVhZEludDMyKCkgOiAwO1xuXG5cdFx0XHRcdGxldCBib3ggPSB0aGlzLmF0dGFjaG1lbnRMb2FkZXIubmV3Qm91bmRpbmdCb3hBdHRhY2htZW50KHNraW4sIG5hbWUpO1xuXHRcdFx0XHRpZiAoIWJveCkgcmV0dXJuIG51bGw7XG5cdFx0XHRcdGJveC53b3JsZFZlcnRpY2VzTGVuZ3RoID0gdmVydGljZXMubGVuZ3RoO1xuXHRcdFx0XHRib3gudmVydGljZXMgPSB2ZXJ0aWNlcy52ZXJ0aWNlcyE7XG5cdFx0XHRcdGJveC5ib25lcyA9IHZlcnRpY2VzLmJvbmVzO1xuXHRcdFx0XHRpZiAobm9uZXNzZW50aWFsKSBDb2xvci5yZ2JhODg4OFRvQ29sb3IoYm94LmNvbG9yLCBjb2xvcik7XG5cdFx0XHRcdHJldHVybiBib3g7XG5cdFx0XHR9XG5cdFx0XHRjYXNlIEF0dGFjaG1lbnRUeXBlLk1lc2g6IHtcblx0XHRcdFx0bGV0IHBhdGggPSAoZmxhZ3MgJiAxNikgIT0gMCA/IGlucHV0LnJlYWRTdHJpbmdSZWYoKSA6IG5hbWU7XG5cdFx0XHRcdGNvbnN0IGNvbG9yID0gKGZsYWdzICYgMzIpICE9IDAgPyBpbnB1dC5yZWFkSW50MzIoKSA6IDB4ZmZmZmZmZmY7XG5cdFx0XHRcdGNvbnN0IHNlcXVlbmNlID0gKGZsYWdzICYgNjQpICE9IDAgPyB0aGlzLnJlYWRTZXF1ZW5jZShpbnB1dCkgOiBudWxsO1xuXHRcdFx0XHRjb25zdCBodWxsTGVuZ3RoID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdFx0Y29uc3QgdmVydGljZXMgPSB0aGlzLnJlYWRWZXJ0aWNlcyhpbnB1dCwgKGZsYWdzICYgMTI4KSAhPSAwKTtcblx0XHRcdFx0Y29uc3QgdXZzID0gdGhpcy5yZWFkRmxvYXRBcnJheShpbnB1dCwgdmVydGljZXMubGVuZ3RoLCAxKTtcblx0XHRcdFx0Y29uc3QgdHJpYW5nbGVzID0gdGhpcy5yZWFkU2hvcnRBcnJheShpbnB1dCwgKHZlcnRpY2VzLmxlbmd0aCAtIGh1bGxMZW5ndGggLSAyKSAqIDMpO1xuXHRcdFx0XHRsZXQgZWRnZXM6IG51bWJlcltdID0gW107XG5cdFx0XHRcdGxldCB3aWR0aCA9IDAsIGhlaWdodCA9IDA7XG5cdFx0XHRcdGlmIChub25lc3NlbnRpYWwpIHtcblx0XHRcdFx0XHRlZGdlcyA9IHRoaXMucmVhZFNob3J0QXJyYXkoaW5wdXQsIGlucHV0LnJlYWRJbnQodHJ1ZSkpO1xuXHRcdFx0XHRcdHdpZHRoID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0aGVpZ2h0ID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdH1cblxuXHRcdFx0XHRpZiAoIXBhdGgpIHBhdGggPSBuYW1lO1xuXHRcdFx0XHRsZXQgbWVzaCA9IHRoaXMuYXR0YWNobWVudExvYWRlci5uZXdNZXNoQXR0YWNobWVudChza2luLCBuYW1lLCBwYXRoLCBzZXF1ZW5jZSk7XG5cdFx0XHRcdGlmICghbWVzaCkgcmV0dXJuIG51bGw7XG5cdFx0XHRcdG1lc2gucGF0aCA9IHBhdGg7XG5cdFx0XHRcdENvbG9yLnJnYmE4ODg4VG9Db2xvcihtZXNoLmNvbG9yLCBjb2xvcik7XG5cdFx0XHRcdG1lc2guYm9uZXMgPSB2ZXJ0aWNlcy5ib25lcztcblx0XHRcdFx0bWVzaC52ZXJ0aWNlcyA9IHZlcnRpY2VzLnZlcnRpY2VzITtcblx0XHRcdFx0bWVzaC53b3JsZFZlcnRpY2VzTGVuZ3RoID0gdmVydGljZXMubGVuZ3RoO1xuXHRcdFx0XHRtZXNoLnRyaWFuZ2xlcyA9IHRyaWFuZ2xlcztcblx0XHRcdFx0bWVzaC5yZWdpb25VVnMgPSB1dnM7XG5cdFx0XHRcdGlmIChzZXF1ZW5jZSA9PSBudWxsKSBtZXNoLnVwZGF0ZVJlZ2lvbigpO1xuXHRcdFx0XHRtZXNoLmh1bGxMZW5ndGggPSBodWxsTGVuZ3RoIDw8IDE7XG5cdFx0XHRcdG1lc2guc2VxdWVuY2UgPSBzZXF1ZW5jZTtcblx0XHRcdFx0aWYgKG5vbmVzc2VudGlhbCkge1xuXHRcdFx0XHRcdG1lc2guZWRnZXMgPSBlZGdlcztcblx0XHRcdFx0XHRtZXNoLndpZHRoID0gd2lkdGggKiBzY2FsZTtcblx0XHRcdFx0XHRtZXNoLmhlaWdodCA9IGhlaWdodCAqIHNjYWxlO1xuXHRcdFx0XHR9XG5cdFx0XHRcdHJldHVybiBtZXNoO1xuXHRcdFx0fVxuXHRcdFx0Y2FzZSBBdHRhY2htZW50VHlwZS5MaW5rZWRNZXNoOiB7XG5cdFx0XHRcdGNvbnN0IHBhdGggPSAoZmxhZ3MgJiAxNikgIT0gMCA/IGlucHV0LnJlYWRTdHJpbmdSZWYoKSA6IG5hbWU7XG5cdFx0XHRcdGlmIChwYXRoID09IG51bGwpIHRocm93IG5ldyBFcnJvcihcIlBhdGggb2YgbGlua2VkIG1lc2ggbXVzdCBub3QgYmUgbnVsbFwiKTtcblx0XHRcdFx0Y29uc3QgY29sb3IgPSAoZmxhZ3MgJiAzMikgIT0gMCA/IGlucHV0LnJlYWRJbnQzMigpIDogMHhmZmZmZmZmZjtcblx0XHRcdFx0Y29uc3Qgc2VxdWVuY2UgPSAoZmxhZ3MgJiA2NCkgIT0gMCA/IHRoaXMucmVhZFNlcXVlbmNlKGlucHV0KSA6IG51bGw7XG5cdFx0XHRcdGNvbnN0IGluaGVyaXRUaW1lbGluZXMgPSAoZmxhZ3MgJiAxMjgpICE9IDA7XG5cdFx0XHRcdGNvbnN0IHNraW5JbmRleCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRcdGNvbnN0IHBhcmVudCA9IGlucHV0LnJlYWRTdHJpbmdSZWYoKTtcblx0XHRcdFx0bGV0IHdpZHRoID0gMCwgaGVpZ2h0ID0gMDtcblx0XHRcdFx0aWYgKG5vbmVzc2VudGlhbCkge1xuXHRcdFx0XHRcdHdpZHRoID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0aGVpZ2h0ID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdH1cblxuXHRcdFx0XHRsZXQgbWVzaCA9IHRoaXMuYXR0YWNobWVudExvYWRlci5uZXdNZXNoQXR0YWNobWVudChza2luLCBuYW1lLCBwYXRoLCBzZXF1ZW5jZSk7XG5cdFx0XHRcdGlmICghbWVzaCkgcmV0dXJuIG51bGw7XG5cdFx0XHRcdG1lc2gucGF0aCA9IHBhdGg7XG5cdFx0XHRcdENvbG9yLnJnYmE4ODg4VG9Db2xvcihtZXNoLmNvbG9yLCBjb2xvcik7XG5cdFx0XHRcdG1lc2guc2VxdWVuY2UgPSBzZXF1ZW5jZTtcblx0XHRcdFx0aWYgKG5vbmVzc2VudGlhbCkge1xuXHRcdFx0XHRcdG1lc2gud2lkdGggPSB3aWR0aCAqIHNjYWxlO1xuXHRcdFx0XHRcdG1lc2guaGVpZ2h0ID0gaGVpZ2h0ICogc2NhbGU7XG5cdFx0XHRcdH1cblx0XHRcdFx0dGhpcy5saW5rZWRNZXNoZXMucHVzaChuZXcgTGlua2VkTWVzaChtZXNoLCBza2luSW5kZXgsIHNsb3RJbmRleCwgcGFyZW50LCBpbmhlcml0VGltZWxpbmVzKSk7XG5cdFx0XHRcdHJldHVybiBtZXNoO1xuXHRcdFx0fVxuXHRcdFx0Y2FzZSBBdHRhY2htZW50VHlwZS5QYXRoOiB7XG5cdFx0XHRcdGNvbnN0IGNsb3NlZCA9IChmbGFncyAmIDE2KSAhPSAwO1xuXHRcdFx0XHRjb25zdCBjb25zdGFudFNwZWVkID0gKGZsYWdzICYgMzIpICE9IDA7XG5cdFx0XHRcdGNvbnN0IHZlcnRpY2VzID0gdGhpcy5yZWFkVmVydGljZXMoaW5wdXQsIChmbGFncyAmIDY0KSAhPSAwKTtcblxuXHRcdFx0XHRjb25zdCBsZW5ndGhzID0gVXRpbHMubmV3QXJyYXkodmVydGljZXMubGVuZ3RoIC8gNiwgMCk7XG5cdFx0XHRcdGZvciAobGV0IGkgPSAwLCBuID0gbGVuZ3Rocy5sZW5ndGg7IGkgPCBuOyBpKyspXG5cdFx0XHRcdFx0bGVuZ3Roc1tpXSA9IGlucHV0LnJlYWRGbG9hdCgpICogc2NhbGU7XG5cdFx0XHRcdGNvbnN0IGNvbG9yID0gbm9uZXNzZW50aWFsID8gaW5wdXQucmVhZEludDMyKCkgOiAwO1xuXG5cdFx0XHRcdGNvbnN0IHBhdGggPSB0aGlzLmF0dGFjaG1lbnRMb2FkZXIubmV3UGF0aEF0dGFjaG1lbnQoc2tpbiwgbmFtZSk7XG5cdFx0XHRcdGlmICghcGF0aCkgcmV0dXJuIG51bGw7XG5cdFx0XHRcdHBhdGguY2xvc2VkID0gY2xvc2VkO1xuXHRcdFx0XHRwYXRoLmNvbnN0YW50U3BlZWQgPSBjb25zdGFudFNwZWVkO1xuXHRcdFx0XHRwYXRoLndvcmxkVmVydGljZXNMZW5ndGggPSB2ZXJ0aWNlcy5sZW5ndGg7XG5cdFx0XHRcdHBhdGgudmVydGljZXMgPSB2ZXJ0aWNlcy52ZXJ0aWNlcyE7XG5cdFx0XHRcdHBhdGguYm9uZXMgPSB2ZXJ0aWNlcy5ib25lcztcblx0XHRcdFx0cGF0aC5sZW5ndGhzID0gbGVuZ3Rocztcblx0XHRcdFx0aWYgKG5vbmVzc2VudGlhbCkgQ29sb3IucmdiYTg4ODhUb0NvbG9yKHBhdGguY29sb3IsIGNvbG9yKTtcblx0XHRcdFx0cmV0dXJuIHBhdGg7XG5cdFx0XHR9XG5cdFx0XHRjYXNlIEF0dGFjaG1lbnRUeXBlLlBvaW50OiB7XG5cdFx0XHRcdGNvbnN0IHJvdGF0aW9uID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdGNvbnN0IHggPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdFx0Y29uc3QgeSA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHRjb25zdCBjb2xvciA9IG5vbmVzc2VudGlhbCA/IGlucHV0LnJlYWRJbnQzMigpIDogMDtcblxuXHRcdFx0XHRjb25zdCBwb2ludCA9IHRoaXMuYXR0YWNobWVudExvYWRlci5uZXdQb2ludEF0dGFjaG1lbnQoc2tpbiwgbmFtZSk7XG5cdFx0XHRcdGlmICghcG9pbnQpIHJldHVybiBudWxsO1xuXHRcdFx0XHRwb2ludC54ID0geCAqIHNjYWxlO1xuXHRcdFx0XHRwb2ludC55ID0geSAqIHNjYWxlO1xuXHRcdFx0XHRwb2ludC5yb3RhdGlvbiA9IHJvdGF0aW9uO1xuXHRcdFx0XHRpZiAobm9uZXNzZW50aWFsKSBDb2xvci5yZ2JhODg4OFRvQ29sb3IocG9pbnQuY29sb3IsIGNvbG9yKTtcblx0XHRcdFx0cmV0dXJuIHBvaW50O1xuXHRcdFx0fVxuXHRcdFx0Y2FzZSBBdHRhY2htZW50VHlwZS5DbGlwcGluZzoge1xuXHRcdFx0XHRjb25zdCBlbmRTbG90SW5kZXggPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdFx0XHRjb25zdCB2ZXJ0aWNlcyA9IHRoaXMucmVhZFZlcnRpY2VzKGlucHV0LCAoZmxhZ3MgJiAxNikgIT0gMCk7XG5cdFx0XHRcdGxldCBjb2xvciA9IG5vbmVzc2VudGlhbCA/IGlucHV0LnJlYWRJbnQzMigpIDogMDtcblxuXHRcdFx0XHRsZXQgY2xpcCA9IHRoaXMuYXR0YWNobWVudExvYWRlci5uZXdDbGlwcGluZ0F0dGFjaG1lbnQoc2tpbiwgbmFtZSk7XG5cdFx0XHRcdGlmICghY2xpcCkgcmV0dXJuIG51bGw7XG5cdFx0XHRcdGNsaXAuZW5kU2xvdCA9IHNrZWxldG9uRGF0YS5zbG90c1tlbmRTbG90SW5kZXhdO1xuXHRcdFx0XHRjbGlwLndvcmxkVmVydGljZXNMZW5ndGggPSB2ZXJ0aWNlcy5sZW5ndGg7XG5cdFx0XHRcdGNsaXAudmVydGljZXMgPSB2ZXJ0aWNlcy52ZXJ0aWNlcyE7XG5cdFx0XHRcdGNsaXAuYm9uZXMgPSB2ZXJ0aWNlcy5ib25lcztcblx0XHRcdFx0aWYgKG5vbmVzc2VudGlhbCkgQ29sb3IucmdiYTg4ODhUb0NvbG9yKGNsaXAuY29sb3IsIGNvbG9yKTtcblx0XHRcdFx0cmV0dXJuIGNsaXA7XG5cdFx0XHR9XG5cdFx0fVxuXHRcdHJldHVybiBudWxsO1xuXHR9XG5cblx0cHJpdmF0ZSByZWFkU2VxdWVuY2UgKGlucHV0OiBCaW5hcnlJbnB1dCkge1xuXHRcdGxldCBzZXF1ZW5jZSA9IG5ldyBTZXF1ZW5jZShpbnB1dC5yZWFkSW50KHRydWUpKTtcblx0XHRzZXF1ZW5jZS5zdGFydCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0c2VxdWVuY2UuZGlnaXRzID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRzZXF1ZW5jZS5zZXR1cEluZGV4ID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRyZXR1cm4gc2VxdWVuY2U7XG5cdH1cblxuXHRwcml2YXRlIHJlYWRWZXJ0aWNlcyAoaW5wdXQ6IEJpbmFyeUlucHV0LCB3ZWlnaHRlZDogYm9vbGVhbik6IFZlcnRpY2VzIHtcblx0XHRjb25zdCBzY2FsZSA9IHRoaXMuc2NhbGU7XG5cdFx0Y29uc3QgdmVydGV4Q291bnQgPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdGNvbnN0IHZlcnRpY2VzID0gbmV3IFZlcnRpY2VzKCk7XG5cdFx0dmVydGljZXMubGVuZ3RoID0gdmVydGV4Q291bnQgPDwgMTtcblx0XHRpZiAoIXdlaWdodGVkKSB7XG5cdFx0XHR2ZXJ0aWNlcy52ZXJ0aWNlcyA9IHRoaXMucmVhZEZsb2F0QXJyYXkoaW5wdXQsIHZlcnRpY2VzLmxlbmd0aCwgc2NhbGUpO1xuXHRcdFx0cmV0dXJuIHZlcnRpY2VzO1xuXHRcdH1cblx0XHRsZXQgd2VpZ2h0cyA9IG5ldyBBcnJheTxudW1iZXI+KCk7XG5cdFx0bGV0IGJvbmVzQXJyYXkgPSBuZXcgQXJyYXk8bnVtYmVyPigpO1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgdmVydGV4Q291bnQ7IGkrKykge1xuXHRcdFx0bGV0IGJvbmVDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRib25lc0FycmF5LnB1c2goYm9uZUNvdW50KTtcblx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCBib25lQ291bnQ7IGlpKyspIHtcblx0XHRcdFx0Ym9uZXNBcnJheS5wdXNoKGlucHV0LnJlYWRJbnQodHJ1ZSkpO1xuXHRcdFx0XHR3ZWlnaHRzLnB1c2goaW5wdXQucmVhZEZsb2F0KCkgKiBzY2FsZSk7XG5cdFx0XHRcdHdlaWdodHMucHVzaChpbnB1dC5yZWFkRmxvYXQoKSAqIHNjYWxlKTtcblx0XHRcdFx0d2VpZ2h0cy5wdXNoKGlucHV0LnJlYWRGbG9hdCgpKTtcblx0XHRcdH1cblx0XHR9XG5cdFx0dmVydGljZXMudmVydGljZXMgPSBVdGlscy50b0Zsb2F0QXJyYXkod2VpZ2h0cyk7XG5cdFx0dmVydGljZXMuYm9uZXMgPSBib25lc0FycmF5O1xuXHRcdHJldHVybiB2ZXJ0aWNlcztcblx0fVxuXG5cdHByaXZhdGUgcmVhZEZsb2F0QXJyYXkgKGlucHV0OiBCaW5hcnlJbnB1dCwgbjogbnVtYmVyLCBzY2FsZTogbnVtYmVyKTogbnVtYmVyW10ge1xuXHRcdGxldCBhcnJheSA9IG5ldyBBcnJheTxudW1iZXI+KG4pO1xuXHRcdGlmIChzY2FsZSA9PSAxKSB7XG5cdFx0XHRmb3IgKGxldCBpID0gMDsgaSA8IG47IGkrKylcblx0XHRcdFx0YXJyYXlbaV0gPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHR9IGVsc2Uge1xuXHRcdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBuOyBpKyspXG5cdFx0XHRcdGFycmF5W2ldID0gaW5wdXQucmVhZEZsb2F0KCkgKiBzY2FsZTtcblx0XHR9XG5cdFx0cmV0dXJuIGFycmF5O1xuXHR9XG5cblx0cHJpdmF0ZSByZWFkU2hvcnRBcnJheSAoaW5wdXQ6IEJpbmFyeUlucHV0LCBuOiBudW1iZXIpOiBudW1iZXJbXSB7XG5cdFx0bGV0IGFycmF5ID0gbmV3IEFycmF5PG51bWJlcj4obik7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBuOyBpKyspXG5cdFx0XHRhcnJheVtpXSA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0cmV0dXJuIGFycmF5O1xuXHR9XG5cblx0cHJpdmF0ZSByZWFkQW5pbWF0aW9uIChpbnB1dDogQmluYXJ5SW5wdXQsIG5hbWU6IHN0cmluZywgc2tlbGV0b25EYXRhOiBTa2VsZXRvbkRhdGEpOiBBbmltYXRpb24ge1xuXHRcdGlucHV0LnJlYWRJbnQodHJ1ZSk7IC8vIE51bWJlciBvZiB0aW1lbGluZXMuXG5cdFx0bGV0IHRpbWVsaW5lcyA9IG5ldyBBcnJheTxUaW1lbGluZT4oKTtcblx0XHRsZXQgc2NhbGUgPSB0aGlzLnNjYWxlO1xuXG5cdFx0Ly8gU2xvdCB0aW1lbGluZXMuXG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBpbnB1dC5yZWFkSW50KHRydWUpOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRsZXQgc2xvdEluZGV4ID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdGZvciAobGV0IGlpID0gMCwgbm4gPSBpbnB1dC5yZWFkSW50KHRydWUpOyBpaSA8IG5uOyBpaSsrKSB7XG5cdFx0XHRcdGxldCB0aW1lbGluZVR5cGUgPSBpbnB1dC5yZWFkQnl0ZSgpO1xuXHRcdFx0XHRsZXQgZnJhbWVDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRcdGxldCBmcmFtZUxhc3QgPSBmcmFtZUNvdW50IC0gMTtcblx0XHRcdFx0c3dpdGNoICh0aW1lbGluZVR5cGUpIHtcblx0XHRcdFx0XHRjYXNlIFNMT1RfQVRUQUNITUVOVDoge1xuXHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IEF0dGFjaG1lbnRUaW1lbGluZShmcmFtZUNvdW50LCBzbG90SW5kZXgpO1xuXHRcdFx0XHRcdFx0Zm9yIChsZXQgZnJhbWUgPSAwOyBmcmFtZSA8IGZyYW1lQ291bnQ7IGZyYW1lKyspXG5cdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCBpbnB1dC5yZWFkRmxvYXQoKSwgaW5wdXQucmVhZFN0cmluZ1JlZigpKTtcblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHRpbWVsaW5lKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0XHRjYXNlIFNMT1RfUkdCQToge1xuXHRcdFx0XHRcdFx0bGV0IGJlemllckNvdW50ID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdFx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBSR0JBVGltZWxpbmUoZnJhbWVDb3VudCwgYmV6aWVyQ291bnQsIHNsb3RJbmRleCk7XG5cblx0XHRcdFx0XHRcdGxldCB0aW1lID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0XHRsZXQgciA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0bGV0IGcgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdGxldCBiID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cdFx0XHRcdFx0XHRsZXQgYSA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXG5cdFx0XHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgciwgZywgYiwgYSk7XG5cdFx0XHRcdFx0XHRcdGlmIChmcmFtZSA9PSBmcmFtZUxhc3QpIGJyZWFrO1xuXG5cdFx0XHRcdFx0XHRcdGxldCB0aW1lMiA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHRcdFx0XHRsZXQgcjIgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdFx0bGV0IGcyID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cdFx0XHRcdFx0XHRcdGxldCBiMiA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0XHRsZXQgYTIgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblxuXHRcdFx0XHRcdFx0XHRzd2l0Y2ggKGlucHV0LnJlYWRCeXRlKCkpIHtcblx0XHRcdFx0XHRcdFx0XHRjYXNlIENVUlZFX1NURVBQRUQ6XG5cdFx0XHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRTdGVwcGVkKGZyYW1lKTtcblx0XHRcdFx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdFx0XHRcdGNhc2UgQ1VSVkVfQkVaSUVSOlxuXHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCAwLCB0aW1lLCB0aW1lMiwgciwgcjIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCAxLCB0aW1lLCB0aW1lMiwgZywgZzIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCAyLCB0aW1lLCB0aW1lMiwgYiwgYjIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCAzLCB0aW1lLCB0aW1lMiwgYSwgYTIsIDEpO1xuXHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdHRpbWUgPSB0aW1lMjtcblx0XHRcdFx0XHRcdFx0ciA9IHIyO1xuXHRcdFx0XHRcdFx0XHRnID0gZzI7XG5cdFx0XHRcdFx0XHRcdGIgPSBiMjtcblx0XHRcdFx0XHRcdFx0YSA9IGEyO1xuXHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHRcdGNhc2UgU0xPVF9SR0I6IHtcblx0XHRcdFx0XHRcdGxldCBiZXppZXJDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgUkdCVGltZWxpbmUoZnJhbWVDb3VudCwgYmV6aWVyQ291bnQsIHNsb3RJbmRleCk7XG5cblx0XHRcdFx0XHRcdGxldCB0aW1lID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0XHRsZXQgciA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0bGV0IGcgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdGxldCBiID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cblx0XHRcdFx0XHRcdGZvciAobGV0IGZyYW1lID0gMCwgYmV6aWVyID0gMDsgOyBmcmFtZSsrKSB7XG5cdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCB0aW1lLCByLCBnLCBiKTtcblx0XHRcdFx0XHRcdFx0aWYgKGZyYW1lID09IGZyYW1lTGFzdCkgYnJlYWs7XG5cblx0XHRcdFx0XHRcdFx0bGV0IHRpbWUyID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0XHRcdGxldCByMiA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0XHRsZXQgZzIgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdFx0bGV0IGIyID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cblx0XHRcdFx0XHRcdFx0c3dpdGNoIChpbnB1dC5yZWFkQnl0ZSgpKSB7XG5cdFx0XHRcdFx0XHRcdFx0Y2FzZSBDVVJWRV9TVEVQUEVEOlxuXHRcdFx0XHRcdFx0XHRcdFx0dGltZWxpbmUuc2V0U3RlcHBlZChmcmFtZSk7XG5cdFx0XHRcdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHRcdFx0XHRjYXNlIENVUlZFX0JFWklFUjpcblx0XHRcdFx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMCwgdGltZSwgdGltZTIsIHIsIHIyLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMSwgdGltZSwgdGltZTIsIGcsIGcyLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMiwgdGltZSwgdGltZTIsIGIsIGIyLCAxKTtcblx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0XHR0aW1lID0gdGltZTI7XG5cdFx0XHRcdFx0XHRcdHIgPSByMjtcblx0XHRcdFx0XHRcdFx0ZyA9IGcyO1xuXHRcdFx0XHRcdFx0XHRiID0gYjI7XG5cdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0Y2FzZSBTTE9UX1JHQkEyOiB7XG5cdFx0XHRcdFx0XHRsZXQgYmV6aWVyQ291bnQgPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IFJHQkEyVGltZWxpbmUoZnJhbWVDb3VudCwgYmV6aWVyQ291bnQsIHNsb3RJbmRleCk7XG5cblx0XHRcdFx0XHRcdGxldCB0aW1lID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0XHRsZXQgciA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0bGV0IGcgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdGxldCBiID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cdFx0XHRcdFx0XHRsZXQgYSA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0bGV0IHIyID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cdFx0XHRcdFx0XHRsZXQgZzIgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdGxldCBiMiA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXG5cdFx0XHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgciwgZywgYiwgYSwgcjIsIGcyLCBiMik7XG5cdFx0XHRcdFx0XHRcdGlmIChmcmFtZSA9PSBmcmFtZUxhc3QpIGJyZWFrO1xuXHRcdFx0XHRcdFx0XHRsZXQgdGltZTIgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdFx0XHRcdFx0bGV0IG5yID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cdFx0XHRcdFx0XHRcdGxldCBuZyA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0XHRsZXQgbmIgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdFx0bGV0IG5hID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cdFx0XHRcdFx0XHRcdGxldCBucjIgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdFx0bGV0IG5nMiA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0XHRsZXQgbmIyID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cblx0XHRcdFx0XHRcdFx0c3dpdGNoIChpbnB1dC5yZWFkQnl0ZSgpKSB7XG5cdFx0XHRcdFx0XHRcdFx0Y2FzZSBDVVJWRV9TVEVQUEVEOlxuXHRcdFx0XHRcdFx0XHRcdFx0dGltZWxpbmUuc2V0U3RlcHBlZChmcmFtZSk7XG5cdFx0XHRcdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHRcdFx0XHRjYXNlIENVUlZFX0JFWklFUjpcblx0XHRcdFx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMCwgdGltZSwgdGltZTIsIHIsIG5yLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMSwgdGltZSwgdGltZTIsIGcsIG5nLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMiwgdGltZSwgdGltZTIsIGIsIG5iLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMywgdGltZSwgdGltZTIsIGEsIG5hLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgNCwgdGltZSwgdGltZTIsIHIyLCBucjIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCA1LCB0aW1lLCB0aW1lMiwgZzIsIG5nMiwgMSk7XG5cdFx0XHRcdFx0XHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDYsIHRpbWUsIHRpbWUyLCBiMiwgbmIyLCAxKTtcblx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0XHR0aW1lID0gdGltZTI7XG5cdFx0XHRcdFx0XHRcdHIgPSBucjtcblx0XHRcdFx0XHRcdFx0ZyA9IG5nO1xuXHRcdFx0XHRcdFx0XHRiID0gbmI7XG5cdFx0XHRcdFx0XHRcdGEgPSBuYTtcblx0XHRcdFx0XHRcdFx0cjIgPSBucjI7XG5cdFx0XHRcdFx0XHRcdGcyID0gbmcyO1xuXHRcdFx0XHRcdFx0XHRiMiA9IG5iMjtcblx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHRpbWVsaW5lKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0XHRjYXNlIFNMT1RfUkdCMjoge1xuXHRcdFx0XHRcdFx0bGV0IGJlemllckNvdW50ID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdFx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBSR0IyVGltZWxpbmUoZnJhbWVDb3VudCwgYmV6aWVyQ291bnQsIHNsb3RJbmRleCk7XG5cblx0XHRcdFx0XHRcdGxldCB0aW1lID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0XHRsZXQgciA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0bGV0IGcgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdGxldCBiID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cdFx0XHRcdFx0XHRsZXQgcjIgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdGxldCBnMiA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0bGV0IGIyID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cblx0XHRcdFx0XHRcdGZvciAobGV0IGZyYW1lID0gMCwgYmV6aWVyID0gMDsgOyBmcmFtZSsrKSB7XG5cdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCB0aW1lLCByLCBnLCBiLCByMiwgZzIsIGIyKTtcblx0XHRcdFx0XHRcdFx0aWYgKGZyYW1lID09IGZyYW1lTGFzdCkgYnJlYWs7XG5cdFx0XHRcdFx0XHRcdGxldCB0aW1lMiA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHRcdFx0XHRsZXQgbnIgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdFx0bGV0IG5nID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cdFx0XHRcdFx0XHRcdGxldCBuYiA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXHRcdFx0XHRcdFx0XHRsZXQgbnIyID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1LjA7XG5cdFx0XHRcdFx0XHRcdGxldCBuZzIgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTUuMDtcblx0XHRcdFx0XHRcdFx0bGV0IG5iMiA9IGlucHV0LnJlYWRVbnNpZ25lZEJ5dGUoKSAvIDI1NS4wO1xuXG5cdFx0XHRcdFx0XHRcdHN3aXRjaCAoaW5wdXQucmVhZEJ5dGUoKSkge1xuXHRcdFx0XHRcdFx0XHRcdGNhc2UgQ1VSVkVfU1RFUFBFRDpcblx0XHRcdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldFN0ZXBwZWQoZnJhbWUpO1xuXHRcdFx0XHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0XHRcdFx0Y2FzZSBDVVJWRV9CRVpJRVI6XG5cdFx0XHRcdFx0XHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCByLCBuciwgMSk7XG5cdFx0XHRcdFx0XHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDEsIHRpbWUsIHRpbWUyLCBnLCBuZywgMSk7XG5cdFx0XHRcdFx0XHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDIsIHRpbWUsIHRpbWUyLCBiLCBuYiwgMSk7XG5cdFx0XHRcdFx0XHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDMsIHRpbWUsIHRpbWUyLCByMiwgbnIyLCAxKTtcblx0XHRcdFx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgNCwgdGltZSwgdGltZTIsIGcyLCBuZzIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCA1LCB0aW1lLCB0aW1lMiwgYjIsIG5iMiwgMSk7XG5cdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0dGltZSA9IHRpbWUyO1xuXHRcdFx0XHRcdFx0XHRyID0gbnI7XG5cdFx0XHRcdFx0XHRcdGcgPSBuZztcblx0XHRcdFx0XHRcdFx0YiA9IG5iO1xuXHRcdFx0XHRcdFx0XHRyMiA9IG5yMjtcblx0XHRcdFx0XHRcdFx0ZzIgPSBuZzI7XG5cdFx0XHRcdFx0XHRcdGIyID0gbmIyO1xuXHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHRcdGNhc2UgU0xPVF9BTFBIQToge1xuXHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IEFscGhhVGltZWxpbmUoZnJhbWVDb3VudCwgaW5wdXQucmVhZEludCh0cnVlKSwgc2xvdEluZGV4KTtcblx0XHRcdFx0XHRcdGxldCB0aW1lID0gaW5wdXQucmVhZEZsb2F0KCksIGEgPSBpbnB1dC5yZWFkVW5zaWduZWRCeXRlKCkgLyAyNTU7XG5cdFx0XHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgYSk7XG5cdFx0XHRcdFx0XHRcdGlmIChmcmFtZSA9PSBmcmFtZUxhc3QpIGJyZWFrO1xuXHRcdFx0XHRcdFx0XHRsZXQgdGltZTIgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdFx0XHRcdFx0bGV0IGEyID0gaW5wdXQucmVhZFVuc2lnbmVkQnl0ZSgpIC8gMjU1O1xuXHRcdFx0XHRcdFx0XHRzd2l0Y2ggKGlucHV0LnJlYWRCeXRlKCkpIHtcblx0XHRcdFx0XHRcdFx0XHRjYXNlIENVUlZFX1NURVBQRUQ6XG5cdFx0XHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRTdGVwcGVkKGZyYW1lKTtcblx0XHRcdFx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdFx0XHRcdGNhc2UgQ1VSVkVfQkVaSUVSOlxuXHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCAwLCB0aW1lLCB0aW1lMiwgYSwgYTIsIDEpO1xuXHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdHRpbWUgPSB0aW1lMjtcblx0XHRcdFx0XHRcdFx0YSA9IGEyO1xuXHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0fVxuXHRcdFx0fVxuXHRcdH1cblxuXHRcdC8vIEJvbmUgdGltZWxpbmVzLlxuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gaW5wdXQucmVhZEludCh0cnVlKTsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGJvbmVJbmRleCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRmb3IgKGxldCBpaSA9IDAsIG5uID0gaW5wdXQucmVhZEludCh0cnVlKTsgaWkgPCBubjsgaWkrKykge1xuXHRcdFx0XHRsZXQgdHlwZSA9IGlucHV0LnJlYWRCeXRlKCksIGZyYW1lQ291bnQgPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdFx0XHRpZiAodHlwZSA9PSBCT05FX0lOSEVSSVQpIHtcblx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgSW5oZXJpdFRpbWVsaW5lKGZyYW1lQ291bnQsIGJvbmVJbmRleCk7XG5cdFx0XHRcdFx0Zm9yIChsZXQgZnJhbWUgPSAwOyBmcmFtZSA8IGZyYW1lQ291bnQ7IGZyYW1lKyspIHtcblx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCBpbnB1dC5yZWFkRmxvYXQoKSwgaW5wdXQucmVhZEJ5dGUoKSk7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHRpbWVsaW5lKTtcblx0XHRcdFx0XHRjb250aW51ZTtcblx0XHRcdFx0fVxuXHRcdFx0XHRsZXQgYmV6aWVyQ291bnQgPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdFx0XHRzd2l0Y2ggKHR5cGUpIHtcblx0XHRcdFx0XHRjYXNlIEJPTkVfUk9UQVRFOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMShpbnB1dCwgbmV3IFJvdGF0ZVRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBib25lSW5kZXgpLCAxKSk7XG5cdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHRjYXNlIEJPTkVfVFJBTlNMQVRFOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMihpbnB1dCwgbmV3IFRyYW5zbGF0ZVRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBib25lSW5kZXgpLCBzY2FsZSkpO1xuXHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0Y2FzZSBCT05FX1RSQU5TTEFURVg6XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaChyZWFkVGltZWxpbmUxKGlucHV0LCBuZXcgVHJhbnNsYXRlWFRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBib25lSW5kZXgpLCBzY2FsZSkpO1xuXHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0Y2FzZSBCT05FX1RSQU5TTEFURVk6XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaChyZWFkVGltZWxpbmUxKGlucHV0LCBuZXcgVHJhbnNsYXRlWVRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBib25lSW5kZXgpLCBzY2FsZSkpO1xuXHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0Y2FzZSBCT05FX1NDQUxFOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMihpbnB1dCwgbmV3IFNjYWxlVGltZWxpbmUoZnJhbWVDb3VudCwgYmV6aWVyQ291bnQsIGJvbmVJbmRleCksIDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgQk9ORV9TQ0FMRVg6XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaChyZWFkVGltZWxpbmUxKGlucHV0LCBuZXcgU2NhbGVYVGltZWxpbmUoZnJhbWVDb3VudCwgYmV6aWVyQ291bnQsIGJvbmVJbmRleCksIDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgQk9ORV9TQ0FMRVk6XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaChyZWFkVGltZWxpbmUxKGlucHV0LCBuZXcgU2NhbGVZVGltZWxpbmUoZnJhbWVDb3VudCwgYmV6aWVyQ291bnQsIGJvbmVJbmRleCksIDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgQk9ORV9TSEVBUjpcblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHJlYWRUaW1lbGluZTIoaW5wdXQsIG5ldyBTaGVhclRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBib25lSW5kZXgpLCAxKSk7XG5cdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHRjYXNlIEJPTkVfU0hFQVJYOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMShpbnB1dCwgbmV3IFNoZWFyWFRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBib25lSW5kZXgpLCAxKSk7XG5cdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHRjYXNlIEJPTkVfU0hFQVJZOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMShpbnB1dCwgbmV3IFNoZWFyWVRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBib25lSW5kZXgpLCAxKSk7XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBJSyBjb25zdHJhaW50IHRpbWVsaW5lcy5cblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBpbmRleCA9IGlucHV0LnJlYWRJbnQodHJ1ZSksIGZyYW1lQ291bnQgPSBpbnB1dC5yZWFkSW50KHRydWUpLCBmcmFtZUxhc3QgPSBmcmFtZUNvdW50IC0gMTtcblx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBJa0NvbnN0cmFpbnRUaW1lbGluZShmcmFtZUNvdW50LCBpbnB1dC5yZWFkSW50KHRydWUpLCBpbmRleCk7XG5cdFx0XHRsZXQgZmxhZ3MgPSBpbnB1dC5yZWFkQnl0ZSgpO1xuXHRcdFx0bGV0IHRpbWUgPSBpbnB1dC5yZWFkRmxvYXQoKSwgbWl4ID0gKGZsYWdzICYgMSkgIT0gMCA/ICgoZmxhZ3MgJiAyKSAhPSAwID8gaW5wdXQucmVhZEZsb2F0KCkgOiAxKSA6IDA7XG5cdFx0XHRsZXQgc29mdG5lc3MgPSAoZmxhZ3MgJiA0KSAhPSAwID8gaW5wdXQucmVhZEZsb2F0KCkgKiBzY2FsZSA6IDA7XG5cdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgbWl4LCBzb2Z0bmVzcywgKGZsYWdzICYgOCkgIT0gMCA/IDEgOiAtMSwgKGZsYWdzICYgMTYpICE9IDAsIChmbGFncyAmIDMyKSAhPSAwKTtcblx0XHRcdFx0aWYgKGZyYW1lID09IGZyYW1lTGFzdCkgYnJlYWs7XG5cdFx0XHRcdGZsYWdzID0gaW5wdXQucmVhZEJ5dGUoKTtcblx0XHRcdFx0Y29uc3QgdGltZTIgPSBpbnB1dC5yZWFkRmxvYXQoKSwgbWl4MiA9IChmbGFncyAmIDEpICE9IDAgPyAoKGZsYWdzICYgMikgIT0gMCA/IGlucHV0LnJlYWRGbG9hdCgpIDogMSkgOiAwO1xuXHRcdFx0XHRjb25zdCBzb2Z0bmVzczIgPSAoZmxhZ3MgJiA0KSAhPSAwID8gaW5wdXQucmVhZEZsb2F0KCkgKiBzY2FsZSA6IDA7XG5cdFx0XHRcdGlmICgoZmxhZ3MgJiA2NCkgIT0gMCkge1xuXHRcdFx0XHRcdHRpbWVsaW5lLnNldFN0ZXBwZWQoZnJhbWUpO1xuXHRcdFx0XHR9IGVsc2UgaWYgKChmbGFncyAmIDEyOCkgIT0gMCkge1xuXHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMCwgdGltZSwgdGltZTIsIG1peCwgbWl4MiwgMSk7XG5cdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCAxLCB0aW1lLCB0aW1lMiwgc29mdG5lc3MsIHNvZnRuZXNzMiwgc2NhbGUpO1xuXHRcdFx0XHR9XG5cdFx0XHRcdHRpbWUgPSB0aW1lMjtcblx0XHRcdFx0bWl4ID0gbWl4Mjtcblx0XHRcdFx0c29mdG5lc3MgPSBzb2Z0bmVzczI7XG5cdFx0XHR9XG5cdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0fVxuXG5cdFx0Ly8gVHJhbnNmb3JtIGNvbnN0cmFpbnQgdGltZWxpbmVzLlxuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gaW5wdXQucmVhZEludCh0cnVlKTsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGluZGV4ID0gaW5wdXQucmVhZEludCh0cnVlKSwgZnJhbWVDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSksIGZyYW1lTGFzdCA9IGZyYW1lQ291bnQgLSAxO1xuXHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IFRyYW5zZm9ybUNvbnN0cmFpbnRUaW1lbGluZShmcmFtZUNvdW50LCBpbnB1dC5yZWFkSW50KHRydWUpLCBpbmRleCk7XG5cdFx0XHRsZXQgdGltZSA9IGlucHV0LnJlYWRGbG9hdCgpLCBtaXhSb3RhdGUgPSBpbnB1dC5yZWFkRmxvYXQoKSwgbWl4WCA9IGlucHV0LnJlYWRGbG9hdCgpLCBtaXhZID0gaW5wdXQucmVhZEZsb2F0KCksXG5cdFx0XHRcdG1peFNjYWxlWCA9IGlucHV0LnJlYWRGbG9hdCgpLCBtaXhTY2FsZVkgPSBpbnB1dC5yZWFkRmxvYXQoKSwgbWl4U2hlYXJZID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDA7IDsgZnJhbWUrKykge1xuXHRcdFx0XHR0aW1lbGluZS5zZXRGcmFtZShmcmFtZSwgdGltZSwgbWl4Um90YXRlLCBtaXhYLCBtaXhZLCBtaXhTY2FsZVgsIG1peFNjYWxlWSwgbWl4U2hlYXJZKTtcblx0XHRcdFx0aWYgKGZyYW1lID09IGZyYW1lTGFzdCkgYnJlYWs7XG5cdFx0XHRcdGxldCB0aW1lMiA9IGlucHV0LnJlYWRGbG9hdCgpLCBtaXhSb3RhdGUyID0gaW5wdXQucmVhZEZsb2F0KCksIG1peFgyID0gaW5wdXQucmVhZEZsb2F0KCksIG1peFkyID0gaW5wdXQucmVhZEZsb2F0KCksXG5cdFx0XHRcdFx0bWl4U2NhbGVYMiA9IGlucHV0LnJlYWRGbG9hdCgpLCBtaXhTY2FsZVkyID0gaW5wdXQucmVhZEZsb2F0KCksIG1peFNoZWFyWTIgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdFx0c3dpdGNoIChpbnB1dC5yZWFkQnl0ZSgpKSB7XG5cdFx0XHRcdFx0Y2FzZSBDVVJWRV9TVEVQUEVEOlxuXHRcdFx0XHRcdFx0dGltZWxpbmUuc2V0U3RlcHBlZChmcmFtZSk7XG5cdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHRjYXNlIENVUlZFX0JFWklFUjpcblx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMCwgdGltZSwgdGltZTIsIG1peFJvdGF0ZSwgbWl4Um90YXRlMiwgMSk7XG5cdFx0XHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDEsIHRpbWUsIHRpbWUyLCBtaXhYLCBtaXhYMiwgMSk7XG5cdFx0XHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDIsIHRpbWUsIHRpbWUyLCBtaXhZLCBtaXhZMiwgMSk7XG5cdFx0XHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDMsIHRpbWUsIHRpbWUyLCBtaXhTY2FsZVgsIG1peFNjYWxlWDIsIDEpO1xuXHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCA0LCB0aW1lLCB0aW1lMiwgbWl4U2NhbGVZLCBtaXhTY2FsZVkyLCAxKTtcblx0XHRcdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgNSwgdGltZSwgdGltZTIsIG1peFNoZWFyWSwgbWl4U2hlYXJZMiwgMSk7XG5cdFx0XHRcdH1cblx0XHRcdFx0dGltZSA9IHRpbWUyO1xuXHRcdFx0XHRtaXhSb3RhdGUgPSBtaXhSb3RhdGUyO1xuXHRcdFx0XHRtaXhYID0gbWl4WDI7XG5cdFx0XHRcdG1peFkgPSBtaXhZMjtcblx0XHRcdFx0bWl4U2NhbGVYID0gbWl4U2NhbGVYMjtcblx0XHRcdFx0bWl4U2NhbGVZID0gbWl4U2NhbGVZMjtcblx0XHRcdFx0bWl4U2hlYXJZID0gbWl4U2hlYXJZMjtcblx0XHRcdH1cblx0XHRcdHRpbWVsaW5lcy5wdXNoKHRpbWVsaW5lKTtcblx0XHR9XG5cblx0XHQvLyBQYXRoIGNvbnN0cmFpbnQgdGltZWxpbmVzLlxuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gaW5wdXQucmVhZEludCh0cnVlKTsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGluZGV4ID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdGxldCBkYXRhID0gc2tlbGV0b25EYXRhLnBhdGhDb25zdHJhaW50c1tpbmRleF07XG5cdFx0XHRmb3IgKGxldCBpaSA9IDAsIG5uID0gaW5wdXQucmVhZEludCh0cnVlKTsgaWkgPCBubjsgaWkrKykge1xuXHRcdFx0XHRjb25zdCB0eXBlID0gaW5wdXQucmVhZEJ5dGUoKSwgZnJhbWVDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSksIGJlemllckNvdW50ID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdFx0c3dpdGNoICh0eXBlKSB7XG5cdFx0XHRcdFx0Y2FzZSBQQVRIX1BPU0lUSU9OOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzXG5cdFx0XHRcdFx0XHRcdC5wdXNoKHJlYWRUaW1lbGluZTEoaW5wdXQsIG5ldyBQYXRoQ29uc3RyYWludFBvc2l0aW9uVGltZWxpbmUoZnJhbWVDb3VudCwgYmV6aWVyQ291bnQsIGluZGV4KSxcblx0XHRcdFx0XHRcdFx0XHRkYXRhLnBvc2l0aW9uTW9kZSA9PSBQb3NpdGlvbk1vZGUuRml4ZWQgPyBzY2FsZSA6IDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgUEFUSF9TUEFDSU5HOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzXG5cdFx0XHRcdFx0XHRcdC5wdXNoKHJlYWRUaW1lbGluZTEoaW5wdXQsIG5ldyBQYXRoQ29uc3RyYWludFNwYWNpbmdUaW1lbGluZShmcmFtZUNvdW50LCBiZXppZXJDb3VudCwgaW5kZXgpLFxuXHRcdFx0XHRcdFx0XHRcdGRhdGEuc3BhY2luZ01vZGUgPT0gU3BhY2luZ01vZGUuTGVuZ3RoIHx8IGRhdGEuc3BhY2luZ01vZGUgPT0gU3BhY2luZ01vZGUuRml4ZWQgPyBzY2FsZSA6IDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgUEFUSF9NSVg6XG5cdFx0XHRcdFx0XHRsZXQgdGltZWxpbmUgPSBuZXcgUGF0aENvbnN0cmFpbnRNaXhUaW1lbGluZShmcmFtZUNvdW50LCBiZXppZXJDb3VudCwgaW5kZXgpO1xuXHRcdFx0XHRcdFx0bGV0IHRpbWUgPSBpbnB1dC5yZWFkRmxvYXQoKSwgbWl4Um90YXRlID0gaW5wdXQucmVhZEZsb2F0KCksIG1peFggPSBpbnB1dC5yZWFkRmxvYXQoKSwgbWl4WSA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHRcdFx0Zm9yIChsZXQgZnJhbWUgPSAwLCBiZXppZXIgPSAwLCBmcmFtZUxhc3QgPSB0aW1lbGluZS5nZXRGcmFtZUNvdW50KCkgLSAxOyA7IGZyYW1lKyspIHtcblx0XHRcdFx0XHRcdFx0dGltZWxpbmUuc2V0RnJhbWUoZnJhbWUsIHRpbWUsIG1peFJvdGF0ZSwgbWl4WCwgbWl4WSk7XG5cdFx0XHRcdFx0XHRcdGlmIChmcmFtZSA9PSBmcmFtZUxhc3QpIGJyZWFrO1xuXHRcdFx0XHRcdFx0XHRsZXQgdGltZTIgPSBpbnB1dC5yZWFkRmxvYXQoKSwgbWl4Um90YXRlMiA9IGlucHV0LnJlYWRGbG9hdCgpLCBtaXhYMiA9IGlucHV0LnJlYWRGbG9hdCgpLFxuXHRcdFx0XHRcdFx0XHRcdG1peFkyID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0XHRcdHN3aXRjaCAoaW5wdXQucmVhZEJ5dGUoKSkge1xuXHRcdFx0XHRcdFx0XHRcdGNhc2UgQ1VSVkVfU1RFUFBFRDpcblx0XHRcdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldFN0ZXBwZWQoZnJhbWUpO1xuXHRcdFx0XHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0XHRcdFx0Y2FzZSBDVVJWRV9CRVpJRVI6XG5cdFx0XHRcdFx0XHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCBtaXhSb3RhdGUsIG1peFJvdGF0ZTIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCAxLCB0aW1lLCB0aW1lMiwgbWl4WCwgbWl4WDIsIDEpO1xuXHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCAyLCB0aW1lLCB0aW1lMiwgbWl4WSwgbWl4WTIsIDEpO1xuXHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHRcdHRpbWUgPSB0aW1lMjtcblx0XHRcdFx0XHRcdFx0bWl4Um90YXRlID0gbWl4Um90YXRlMjtcblx0XHRcdFx0XHRcdFx0bWl4WCA9IG1peFgyO1xuXHRcdFx0XHRcdFx0XHRtaXhZID0gbWl4WTI7XG5cdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBQaHlzaWNzIHRpbWVsaW5lcy5cblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7IGkgPCBuOyBpKyspIHtcblx0XHRcdGNvbnN0IGluZGV4ID0gaW5wdXQucmVhZEludCh0cnVlKSAtIDE7XG5cdFx0XHRmb3IgKGxldCBpaSA9IDAsIG5uID0gaW5wdXQucmVhZEludCh0cnVlKTsgaWkgPCBubjsgaWkrKykge1xuXHRcdFx0XHRjb25zdCB0eXBlID0gaW5wdXQucmVhZEJ5dGUoKSwgZnJhbWVDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRcdGlmICh0eXBlID09IFBIWVNJQ1NfUkVTRVQpIHtcblx0XHRcdFx0XHRjb25zdCB0aW1lbGluZSA9IG5ldyBQaHlzaWNzQ29uc3RyYWludFJlc2V0VGltZWxpbmUoZnJhbWVDb3VudCwgaW5kZXgpO1xuXHRcdFx0XHRcdGZvciAobGV0IGZyYW1lID0gMDsgZnJhbWUgPCBmcmFtZUNvdW50OyBmcmFtZSsrKVxuXHRcdFx0XHRcdFx0dGltZWxpbmUuc2V0RnJhbWUoZnJhbWUsIGlucHV0LnJlYWRGbG9hdCgpKTtcblx0XHRcdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0XHRcdFx0Y29udGludWU7XG5cdFx0XHRcdH1cblx0XHRcdFx0Y29uc3QgYmV6aWVyQ291bnQgPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdFx0XHRzd2l0Y2ggKHR5cGUpIHtcblx0XHRcdFx0XHRjYXNlIFBIWVNJQ1NfSU5FUlRJQTpcblx0XHRcdFx0XHRcdHRpbWVsaW5lcy5wdXNoKHJlYWRUaW1lbGluZTEoaW5wdXQsIG5ldyBQaHlzaWNzQ29uc3RyYWludEluZXJ0aWFUaW1lbGluZShmcmFtZUNvdW50LCBiZXppZXJDb3VudCwgaW5kZXgpLCAxKSk7XG5cdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHRjYXNlIFBIWVNJQ1NfU1RSRU5HVEg6XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaChyZWFkVGltZWxpbmUxKGlucHV0LCBuZXcgUGh5c2ljc0NvbnN0cmFpbnRTdHJlbmd0aFRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBpbmRleCksIDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgUEhZU0lDU19EQU1QSU5HOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMShpbnB1dCwgbmV3IFBoeXNpY3NDb25zdHJhaW50RGFtcGluZ1RpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBpbmRleCksIDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgUEhZU0lDU19NQVNTOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMShpbnB1dCwgbmV3IFBoeXNpY3NDb25zdHJhaW50TWFzc1RpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBpbmRleCksIDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgUEhZU0lDU19XSU5EOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMShpbnB1dCwgbmV3IFBoeXNpY3NDb25zdHJhaW50V2luZFRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBpbmRleCksIDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgUEhZU0lDU19HUkFWSVRZOlxuXHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2gocmVhZFRpbWVsaW5lMShpbnB1dCwgbmV3IFBoeXNpY3NDb25zdHJhaW50R3Jhdml0eVRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBpbmRleCksIDEpKTtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgUEhZU0lDU19NSVg6XG5cdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaChyZWFkVGltZWxpbmUxKGlucHV0LCBuZXcgUGh5c2ljc0NvbnN0cmFpbnRNaXhUaW1lbGluZShmcmFtZUNvdW50LCBiZXppZXJDb3VudCwgaW5kZXgpLCAxKSk7XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBEZWZvcm0gdGltZWxpbmVzLlxuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gaW5wdXQucmVhZEludCh0cnVlKTsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IHNraW4gPSBza2VsZXRvbkRhdGEuc2tpbnNbaW5wdXQucmVhZEludCh0cnVlKV07XG5cdFx0XHRmb3IgKGxldCBpaSA9IDAsIG5uID0gaW5wdXQucmVhZEludCh0cnVlKTsgaWkgPCBubjsgaWkrKykge1xuXHRcdFx0XHRsZXQgc2xvdEluZGV4ID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdFx0Zm9yIChsZXQgaWlpID0gMCwgbm5uID0gaW5wdXQucmVhZEludCh0cnVlKTsgaWlpIDwgbm5uOyBpaWkrKykge1xuXHRcdFx0XHRcdGxldCBhdHRhY2htZW50TmFtZSA9IGlucHV0LnJlYWRTdHJpbmdSZWYoKTtcblx0XHRcdFx0XHRpZiAoIWF0dGFjaG1lbnROYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJhdHRhY2htZW50TmFtZSBtdXN0IG5vdCBiZSBudWxsLlwiKTtcblx0XHRcdFx0XHRsZXQgYXR0YWNobWVudCA9IHNraW4uZ2V0QXR0YWNobWVudChzbG90SW5kZXgsIGF0dGFjaG1lbnROYW1lKTtcblx0XHRcdFx0XHRsZXQgdGltZWxpbmVUeXBlID0gaW5wdXQucmVhZEJ5dGUoKTtcblx0XHRcdFx0XHRsZXQgZnJhbWVDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRcdFx0bGV0IGZyYW1lTGFzdCA9IGZyYW1lQ291bnQgLSAxO1xuXG5cdFx0XHRcdFx0c3dpdGNoICh0aW1lbGluZVR5cGUpIHtcblx0XHRcdFx0XHRcdGNhc2UgQVRUQUNITUVOVF9ERUZPUk06IHtcblx0XHRcdFx0XHRcdFx0bGV0IHZlcnRleEF0dGFjaG1lbnQgPSBhdHRhY2htZW50IGFzIFZlcnRleEF0dGFjaG1lbnQ7XG5cdFx0XHRcdFx0XHRcdGxldCB3ZWlnaHRlZCA9IHZlcnRleEF0dGFjaG1lbnQuYm9uZXM7XG5cdFx0XHRcdFx0XHRcdGxldCB2ZXJ0aWNlcyA9IHZlcnRleEF0dGFjaG1lbnQudmVydGljZXM7XG5cdFx0XHRcdFx0XHRcdGxldCBkZWZvcm1MZW5ndGggPSB3ZWlnaHRlZCA/IHZlcnRpY2VzLmxlbmd0aCAvIDMgKiAyIDogdmVydGljZXMubGVuZ3RoO1xuXG5cblx0XHRcdFx0XHRcdFx0bGV0IGJlemllckNvdW50ID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IERlZm9ybVRpbWVsaW5lKGZyYW1lQ291bnQsIGJlemllckNvdW50LCBzbG90SW5kZXgsIHZlcnRleEF0dGFjaG1lbnQpO1xuXG5cdFx0XHRcdFx0XHRcdGxldCB0aW1lID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0XHRcdGZvciAobGV0IGZyYW1lID0gMCwgYmV6aWVyID0gMDsgOyBmcmFtZSsrKSB7XG5cdFx0XHRcdFx0XHRcdFx0bGV0IGRlZm9ybTtcblx0XHRcdFx0XHRcdFx0XHRsZXQgZW5kID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdFx0XHRcdFx0XHRpZiAoZW5kID09IDApXG5cdFx0XHRcdFx0XHRcdFx0XHRkZWZvcm0gPSB3ZWlnaHRlZCA/IFV0aWxzLm5ld0Zsb2F0QXJyYXkoZGVmb3JtTGVuZ3RoKSA6IHZlcnRpY2VzO1xuXHRcdFx0XHRcdFx0XHRcdGVsc2Uge1xuXHRcdFx0XHRcdFx0XHRcdFx0ZGVmb3JtID0gVXRpbHMubmV3RmxvYXRBcnJheShkZWZvcm1MZW5ndGgpO1xuXHRcdFx0XHRcdFx0XHRcdFx0bGV0IHN0YXJ0ID0gaW5wdXQucmVhZEludCh0cnVlKTtcblx0XHRcdFx0XHRcdFx0XHRcdGVuZCArPSBzdGFydDtcblx0XHRcdFx0XHRcdFx0XHRcdGlmIChzY2FsZSA9PSAxKSB7XG5cdFx0XHRcdFx0XHRcdFx0XHRcdGZvciAobGV0IHYgPSBzdGFydDsgdiA8IGVuZDsgdisrKVxuXHRcdFx0XHRcdFx0XHRcdFx0XHRcdGRlZm9ybVt2XSA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHRcdFx0XHRcdFx0fSBlbHNlIHtcblx0XHRcdFx0XHRcdFx0XHRcdFx0Zm9yIChsZXQgdiA9IHN0YXJ0OyB2IDwgZW5kOyB2KyspXG5cdFx0XHRcdFx0XHRcdFx0XHRcdFx0ZGVmb3JtW3ZdID0gaW5wdXQucmVhZEZsb2F0KCkgKiBzY2FsZTtcblx0XHRcdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0XHRcdGlmICghd2VpZ2h0ZWQpIHtcblx0XHRcdFx0XHRcdFx0XHRcdFx0Zm9yIChsZXQgdiA9IDAsIHZuID0gZGVmb3JtLmxlbmd0aDsgdiA8IHZuOyB2KyspXG5cdFx0XHRcdFx0XHRcdFx0XHRcdFx0ZGVmb3JtW3ZdICs9IHZlcnRpY2VzW3ZdO1xuXHRcdFx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0XHRcdH1cblxuXHRcdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCB0aW1lLCBkZWZvcm0pO1xuXHRcdFx0XHRcdFx0XHRcdGlmIChmcmFtZSA9PSBmcmFtZUxhc3QpIGJyZWFrO1xuXHRcdFx0XHRcdFx0XHRcdGxldCB0aW1lMiA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHRcdFx0XHRcdHN3aXRjaCAoaW5wdXQucmVhZEJ5dGUoKSkge1xuXHRcdFx0XHRcdFx0XHRcdFx0Y2FzZSBDVVJWRV9TVEVQUEVEOlxuXHRcdFx0XHRcdFx0XHRcdFx0XHR0aW1lbGluZS5zZXRTdGVwcGVkKGZyYW1lKTtcblx0XHRcdFx0XHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0XHRcdFx0XHRjYXNlIENVUlZFX0JFWklFUjpcblx0XHRcdFx0XHRcdFx0XHRcdFx0c2V0QmV6aWVyKGlucHV0LCB0aW1lbGluZSwgYmV6aWVyKyssIGZyYW1lLCAwLCB0aW1lLCB0aW1lMiwgMCwgMSwgMSk7XG5cdFx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0XHRcdHRpbWUgPSB0aW1lMjtcblx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0Y2FzZSBBVFRBQ0hNRU5UX1NFUVVFTkNFOiB7XG5cdFx0XHRcdFx0XHRcdGxldCB0aW1lbGluZSA9IG5ldyBTZXF1ZW5jZVRpbWVsaW5lKGZyYW1lQ291bnQsIHNsb3RJbmRleCwgYXR0YWNobWVudCBhcyB1bmtub3duIGFzIEhhc1RleHR1cmVSZWdpb24pO1xuXHRcdFx0XHRcdFx0XHRmb3IgKGxldCBmcmFtZSA9IDA7IGZyYW1lIDwgZnJhbWVDb3VudDsgZnJhbWUrKykge1xuXHRcdFx0XHRcdFx0XHRcdGxldCB0aW1lID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0XHRcdFx0bGV0IG1vZGVBbmRJbmRleCA9IGlucHV0LnJlYWRJbnQzMigpO1xuXHRcdFx0XHRcdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCB0aW1lLCBTZXF1ZW5jZU1vZGVWYWx1ZXNbbW9kZUFuZEluZGV4ICYgMHhmXSwgbW9kZUFuZEluZGV4ID4+IDQsXG5cdFx0XHRcdFx0XHRcdFx0XHRpbnB1dC5yZWFkRmxvYXQoKSk7XG5cdFx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHRcdFx0dGltZWxpbmVzLnB1c2godGltZWxpbmUpO1xuXHRcdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHRcdH1cblx0XHRcdFx0XHR9XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHR9XG5cblx0XHQvLyBEcmF3IG9yZGVyIHRpbWVsaW5lLlxuXHRcdGxldCBkcmF3T3JkZXJDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0aWYgKGRyYXdPcmRlckNvdW50ID4gMCkge1xuXHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IERyYXdPcmRlclRpbWVsaW5lKGRyYXdPcmRlckNvdW50KTtcblx0XHRcdGxldCBzbG90Q291bnQgPSBza2VsZXRvbkRhdGEuc2xvdHMubGVuZ3RoO1xuXHRcdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBkcmF3T3JkZXJDb3VudDsgaSsrKSB7XG5cdFx0XHRcdGxldCB0aW1lID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdGxldCBvZmZzZXRDb3VudCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRcdGxldCBkcmF3T3JkZXIgPSBVdGlscy5uZXdBcnJheShzbG90Q291bnQsIDApO1xuXHRcdFx0XHRmb3IgKGxldCBpaSA9IHNsb3RDb3VudCAtIDE7IGlpID49IDA7IGlpLS0pXG5cdFx0XHRcdFx0ZHJhd09yZGVyW2lpXSA9IC0xO1xuXHRcdFx0XHRsZXQgdW5jaGFuZ2VkID0gVXRpbHMubmV3QXJyYXkoc2xvdENvdW50IC0gb2Zmc2V0Q291bnQsIDApO1xuXHRcdFx0XHRsZXQgb3JpZ2luYWxJbmRleCA9IDAsIHVuY2hhbmdlZEluZGV4ID0gMDtcblx0XHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IG9mZnNldENvdW50OyBpaSsrKSB7XG5cdFx0XHRcdFx0bGV0IHNsb3RJbmRleCA9IGlucHV0LnJlYWRJbnQodHJ1ZSk7XG5cdFx0XHRcdFx0Ly8gQ29sbGVjdCB1bmNoYW5nZWQgaXRlbXMuXG5cdFx0XHRcdFx0d2hpbGUgKG9yaWdpbmFsSW5kZXggIT0gc2xvdEluZGV4KVxuXHRcdFx0XHRcdFx0dW5jaGFuZ2VkW3VuY2hhbmdlZEluZGV4KytdID0gb3JpZ2luYWxJbmRleCsrO1xuXHRcdFx0XHRcdC8vIFNldCBjaGFuZ2VkIGl0ZW1zLlxuXHRcdFx0XHRcdGRyYXdPcmRlcltvcmlnaW5hbEluZGV4ICsgaW5wdXQucmVhZEludCh0cnVlKV0gPSBvcmlnaW5hbEluZGV4Kys7XG5cdFx0XHRcdH1cblx0XHRcdFx0Ly8gQ29sbGVjdCByZW1haW5pbmcgdW5jaGFuZ2VkIGl0ZW1zLlxuXHRcdFx0XHR3aGlsZSAob3JpZ2luYWxJbmRleCA8IHNsb3RDb3VudClcblx0XHRcdFx0XHR1bmNoYW5nZWRbdW5jaGFuZ2VkSW5kZXgrK10gPSBvcmlnaW5hbEluZGV4Kys7XG5cdFx0XHRcdC8vIEZpbGwgaW4gdW5jaGFuZ2VkIGl0ZW1zLlxuXHRcdFx0XHRmb3IgKGxldCBpaSA9IHNsb3RDb3VudCAtIDE7IGlpID49IDA7IGlpLS0pXG5cdFx0XHRcdFx0aWYgKGRyYXdPcmRlcltpaV0gPT0gLTEpIGRyYXdPcmRlcltpaV0gPSB1bmNoYW5nZWRbLS11bmNoYW5nZWRJbmRleF07XG5cdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGksIHRpbWUsIGRyYXdPcmRlcik7XG5cdFx0XHR9XG5cdFx0XHR0aW1lbGluZXMucHVzaCh0aW1lbGluZSk7XG5cdFx0fVxuXG5cdFx0Ly8gRXZlbnQgdGltZWxpbmUuXG5cdFx0bGV0IGV2ZW50Q291bnQgPSBpbnB1dC5yZWFkSW50KHRydWUpO1xuXHRcdGlmIChldmVudENvdW50ID4gMCkge1xuXHRcdFx0bGV0IHRpbWVsaW5lID0gbmV3IEV2ZW50VGltZWxpbmUoZXZlbnRDb3VudCk7XG5cdFx0XHRmb3IgKGxldCBpID0gMDsgaSA8IGV2ZW50Q291bnQ7IGkrKykge1xuXHRcdFx0XHRsZXQgdGltZSA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHRsZXQgZXZlbnREYXRhID0gc2tlbGV0b25EYXRhLmV2ZW50c1tpbnB1dC5yZWFkSW50KHRydWUpXTtcblx0XHRcdFx0bGV0IGV2ZW50ID0gbmV3IEV2ZW50KHRpbWUsIGV2ZW50RGF0YSk7XG5cdFx0XHRcdGV2ZW50LmludFZhbHVlID0gaW5wdXQucmVhZEludChmYWxzZSk7XG5cdFx0XHRcdGV2ZW50LmZsb2F0VmFsdWUgPSBpbnB1dC5yZWFkRmxvYXQoKTtcblx0XHRcdFx0ZXZlbnQuc3RyaW5nVmFsdWUgPSBpbnB1dC5yZWFkU3RyaW5nKCk7XG5cdFx0XHRcdGlmIChldmVudC5zdHJpbmdWYWx1ZSA9PSBudWxsKSBldmVudC5zdHJpbmdWYWx1ZSA9IGV2ZW50RGF0YS5zdHJpbmdWYWx1ZTtcblx0XHRcdFx0aWYgKGV2ZW50LmRhdGEuYXVkaW9QYXRoKSB7XG5cdFx0XHRcdFx0ZXZlbnQudm9sdW1lID0gaW5wdXQucmVhZEZsb2F0KCk7XG5cdFx0XHRcdFx0ZXZlbnQuYmFsYW5jZSA9IGlucHV0LnJlYWRGbG9hdCgpO1xuXHRcdFx0XHR9XG5cdFx0XHRcdHRpbWVsaW5lLnNldEZyYW1lKGksIGV2ZW50KTtcblx0XHRcdH1cblx0XHRcdHRpbWVsaW5lcy5wdXNoKHRpbWVsaW5lKTtcblx0XHR9XG5cblx0XHRsZXQgZHVyYXRpb24gPSAwO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gdGltZWxpbmVzLmxlbmd0aDsgaSA8IG47IGkrKylcblx0XHRcdGR1cmF0aW9uID0gTWF0aC5tYXgoZHVyYXRpb24sIHRpbWVsaW5lc1tpXS5nZXREdXJhdGlvbigpKTtcblx0XHRyZXR1cm4gbmV3IEFuaW1hdGlvbihuYW1lLCB0aW1lbGluZXMsIGR1cmF0aW9uKTtcblx0fVxufVxuXG5leHBvcnQgY2xhc3MgQmluYXJ5SW5wdXQge1xuXHRjb25zdHJ1Y3RvciAoZGF0YTogVWludDhBcnJheSB8IEFycmF5QnVmZmVyLCBwdWJsaWMgc3RyaW5ncyA9IG5ldyBBcnJheTxzdHJpbmc+KCksIHByaXZhdGUgaW5kZXg6IG51bWJlciA9IDAsIHByaXZhdGUgYnVmZmVyID0gbmV3IERhdGFWaWV3KGRhdGEgaW5zdGFuY2VvZiBBcnJheUJ1ZmZlciA/IGRhdGEgOiBkYXRhLmJ1ZmZlcikpIHtcblx0fVxuXG5cdHJlYWRCeXRlICgpOiBudW1iZXIge1xuXHRcdHJldHVybiB0aGlzLmJ1ZmZlci5nZXRJbnQ4KHRoaXMuaW5kZXgrKyk7XG5cdH1cblxuXHRyZWFkVW5zaWduZWRCeXRlICgpOiBudW1iZXIge1xuXHRcdHJldHVybiB0aGlzLmJ1ZmZlci5nZXRVaW50OCh0aGlzLmluZGV4KyspO1xuXHR9XG5cblx0cmVhZFNob3J0ICgpOiBudW1iZXIge1xuXHRcdGxldCB2YWx1ZSA9IHRoaXMuYnVmZmVyLmdldEludDE2KHRoaXMuaW5kZXgpO1xuXHRcdHRoaXMuaW5kZXggKz0gMjtcblx0XHRyZXR1cm4gdmFsdWU7XG5cdH1cblxuXHRyZWFkSW50MzIgKCk6IG51bWJlciB7XG5cdFx0bGV0IHZhbHVlID0gdGhpcy5idWZmZXIuZ2V0SW50MzIodGhpcy5pbmRleClcblx0XHR0aGlzLmluZGV4ICs9IDQ7XG5cdFx0cmV0dXJuIHZhbHVlO1xuXHR9XG5cblx0cmVhZEludCAob3B0aW1pemVQb3NpdGl2ZTogYm9vbGVhbikge1xuXHRcdGxldCBiID0gdGhpcy5yZWFkQnl0ZSgpO1xuXHRcdGxldCByZXN1bHQgPSBiICYgMHg3Rjtcblx0XHRpZiAoKGIgJiAweDgwKSAhPSAwKSB7XG5cdFx0XHRiID0gdGhpcy5yZWFkQnl0ZSgpO1xuXHRcdFx0cmVzdWx0IHw9IChiICYgMHg3RikgPDwgNztcblx0XHRcdGlmICgoYiAmIDB4ODApICE9IDApIHtcblx0XHRcdFx0YiA9IHRoaXMucmVhZEJ5dGUoKTtcblx0XHRcdFx0cmVzdWx0IHw9IChiICYgMHg3RikgPDwgMTQ7XG5cdFx0XHRcdGlmICgoYiAmIDB4ODApICE9IDApIHtcblx0XHRcdFx0XHRiID0gdGhpcy5yZWFkQnl0ZSgpO1xuXHRcdFx0XHRcdHJlc3VsdCB8PSAoYiAmIDB4N0YpIDw8IDIxO1xuXHRcdFx0XHRcdGlmICgoYiAmIDB4ODApICE9IDApIHtcblx0XHRcdFx0XHRcdGIgPSB0aGlzLnJlYWRCeXRlKCk7XG5cdFx0XHRcdFx0XHRyZXN1bHQgfD0gKGIgJiAweDdGKSA8PCAyODtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHR9XG5cdFx0cmV0dXJuIG9wdGltaXplUG9zaXRpdmUgPyByZXN1bHQgOiAoKHJlc3VsdCA+Pj4gMSkgXiAtKHJlc3VsdCAmIDEpKTtcblx0fVxuXG5cdHJlYWRTdHJpbmdSZWYgKCk6IHN0cmluZyB8IG51bGwge1xuXHRcdGxldCBpbmRleCA9IHRoaXMucmVhZEludCh0cnVlKTtcblx0XHRyZXR1cm4gaW5kZXggPT0gMCA/IG51bGwgOiB0aGlzLnN0cmluZ3NbaW5kZXggLSAxXTtcblx0fVxuXG5cdHJlYWRTdHJpbmcgKCk6IHN0cmluZyB8IG51bGwge1xuXHRcdGxldCBieXRlQ291bnQgPSB0aGlzLnJlYWRJbnQodHJ1ZSk7XG5cdFx0c3dpdGNoIChieXRlQ291bnQpIHtcblx0XHRcdGNhc2UgMDpcblx0XHRcdFx0cmV0dXJuIG51bGw7XG5cdFx0XHRjYXNlIDE6XG5cdFx0XHRcdHJldHVybiBcIlwiO1xuXHRcdH1cblx0XHRieXRlQ291bnQtLTtcblx0XHRsZXQgY2hhcnMgPSBcIlwiO1xuXHRcdGxldCBjaGFyQ291bnQgPSAwO1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgYnl0ZUNvdW50Oykge1xuXHRcdFx0bGV0IGIgPSB0aGlzLnJlYWRVbnNpZ25lZEJ5dGUoKTtcblx0XHRcdHN3aXRjaCAoYiA+PiA0KSB7XG5cdFx0XHRcdGNhc2UgMTI6XG5cdFx0XHRcdGNhc2UgMTM6XG5cdFx0XHRcdFx0Y2hhcnMgKz0gU3RyaW5nLmZyb21DaGFyQ29kZSgoKGIgJiAweDFGKSA8PCA2IHwgdGhpcy5yZWFkQnl0ZSgpICYgMHgzRikpO1xuXHRcdFx0XHRcdGkgKz0gMjtcblx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0Y2FzZSAxNDpcblx0XHRcdFx0XHRjaGFycyArPSBTdHJpbmcuZnJvbUNoYXJDb2RlKCgoYiAmIDB4MEYpIDw8IDEyIHwgKHRoaXMucmVhZEJ5dGUoKSAmIDB4M0YpIDw8IDYgfCB0aGlzLnJlYWRCeXRlKCkgJiAweDNGKSk7XG5cdFx0XHRcdFx0aSArPSAzO1xuXHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRkZWZhdWx0OlxuXHRcdFx0XHRcdGNoYXJzICs9IFN0cmluZy5mcm9tQ2hhckNvZGUoYik7XG5cdFx0XHRcdFx0aSsrO1xuXHRcdFx0fVxuXHRcdH1cblx0XHRyZXR1cm4gY2hhcnM7XG5cdH1cblxuXHRyZWFkRmxvYXQgKCk6IG51bWJlciB7XG5cdFx0bGV0IHZhbHVlID0gdGhpcy5idWZmZXIuZ2V0RmxvYXQzMih0aGlzLmluZGV4KTtcblx0XHR0aGlzLmluZGV4ICs9IDQ7XG5cdFx0cmV0dXJuIHZhbHVlO1xuXHR9XG5cblx0cmVhZEJvb2xlYW4gKCk6IGJvb2xlYW4ge1xuXHRcdHJldHVybiB0aGlzLnJlYWRCeXRlKCkgIT0gMDtcblx0fVxufVxuXG5jbGFzcyBMaW5rZWRNZXNoIHtcblx0cGFyZW50OiBzdHJpbmcgfCBudWxsOyBza2luSW5kZXg6IG51bWJlcjtcblx0c2xvdEluZGV4OiBudW1iZXI7XG5cdG1lc2g6IE1lc2hBdHRhY2htZW50O1xuXHRpbmhlcml0VGltZWxpbmU6IGJvb2xlYW47XG5cblx0Y29uc3RydWN0b3IgKG1lc2g6IE1lc2hBdHRhY2htZW50LCBza2luSW5kZXg6IG51bWJlciwgc2xvdEluZGV4OiBudW1iZXIsIHBhcmVudDogc3RyaW5nIHwgbnVsbCwgaW5oZXJpdERlZm9ybTogYm9vbGVhbikge1xuXHRcdHRoaXMubWVzaCA9IG1lc2g7XG5cdFx0dGhpcy5za2luSW5kZXggPSBza2luSW5kZXg7XG5cdFx0dGhpcy5zbG90SW5kZXggPSBzbG90SW5kZXg7XG5cdFx0dGhpcy5wYXJlbnQgPSBwYXJlbnQ7XG5cdFx0dGhpcy5pbmhlcml0VGltZWxpbmUgPSBpbmhlcml0RGVmb3JtO1xuXHR9XG59XG5cbmNsYXNzIFZlcnRpY2VzIHtcblx0Y29uc3RydWN0b3IgKHB1YmxpYyBib25lczogQXJyYXk8bnVtYmVyPiB8IG51bGwgPSBudWxsLCBwdWJsaWMgdmVydGljZXM6IEFycmF5PG51bWJlcj4gfCBGbG9hdDMyQXJyYXkgfCBudWxsID0gbnVsbCwgcHVibGljIGxlbmd0aDogbnVtYmVyID0gMCkgeyB9XG59XG5cbmVudW0gQXR0YWNobWVudFR5cGUgeyBSZWdpb24sIEJvdW5kaW5nQm94LCBNZXNoLCBMaW5rZWRNZXNoLCBQYXRoLCBQb2ludCwgQ2xpcHBpbmcgfVxuXG5mdW5jdGlvbiByZWFkVGltZWxpbmUxIChpbnB1dDogQmluYXJ5SW5wdXQsIHRpbWVsaW5lOiBDdXJ2ZVRpbWVsaW5lMSwgc2NhbGU6IG51bWJlcik6IEN1cnZlVGltZWxpbmUxIHtcblx0bGV0IHRpbWUgPSBpbnB1dC5yZWFkRmxvYXQoKSwgdmFsdWUgPSBpbnB1dC5yZWFkRmxvYXQoKSAqIHNjYWxlO1xuXHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDAsIGZyYW1lTGFzdCA9IHRpbWVsaW5lLmdldEZyYW1lQ291bnQoKSAtIDE7IDsgZnJhbWUrKykge1xuXHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCB0aW1lLCB2YWx1ZSk7XG5cdFx0aWYgKGZyYW1lID09IGZyYW1lTGFzdCkgYnJlYWs7XG5cdFx0bGV0IHRpbWUyID0gaW5wdXQucmVhZEZsb2F0KCksIHZhbHVlMiA9IGlucHV0LnJlYWRGbG9hdCgpICogc2NhbGU7XG5cdFx0c3dpdGNoIChpbnB1dC5yZWFkQnl0ZSgpKSB7XG5cdFx0XHRjYXNlIENVUlZFX1NURVBQRUQ6XG5cdFx0XHRcdHRpbWVsaW5lLnNldFN0ZXBwZWQoZnJhbWUpO1xuXHRcdFx0XHRicmVhaztcblx0XHRcdGNhc2UgQ1VSVkVfQkVaSUVSOlxuXHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDAsIHRpbWUsIHRpbWUyLCB2YWx1ZSwgdmFsdWUyLCBzY2FsZSk7XG5cdFx0fVxuXHRcdHRpbWUgPSB0aW1lMjtcblx0XHR2YWx1ZSA9IHZhbHVlMjtcblx0fVxuXHRyZXR1cm4gdGltZWxpbmU7XG59XG5cbmZ1bmN0aW9uIHJlYWRUaW1lbGluZTIgKGlucHV0OiBCaW5hcnlJbnB1dCwgdGltZWxpbmU6IEN1cnZlVGltZWxpbmUyLCBzY2FsZTogbnVtYmVyKTogQ3VydmVUaW1lbGluZTIge1xuXHRsZXQgdGltZSA9IGlucHV0LnJlYWRGbG9hdCgpLCB2YWx1ZTEgPSBpbnB1dC5yZWFkRmxvYXQoKSAqIHNjYWxlLCB2YWx1ZTIgPSBpbnB1dC5yZWFkRmxvYXQoKSAqIHNjYWxlO1xuXHRmb3IgKGxldCBmcmFtZSA9IDAsIGJlemllciA9IDAsIGZyYW1lTGFzdCA9IHRpbWVsaW5lLmdldEZyYW1lQ291bnQoKSAtIDE7IDsgZnJhbWUrKykge1xuXHRcdHRpbWVsaW5lLnNldEZyYW1lKGZyYW1lLCB0aW1lLCB2YWx1ZTEsIHZhbHVlMik7XG5cdFx0aWYgKGZyYW1lID09IGZyYW1lTGFzdCkgYnJlYWs7XG5cdFx0bGV0IHRpbWUyID0gaW5wdXQucmVhZEZsb2F0KCksIG52YWx1ZTEgPSBpbnB1dC5yZWFkRmxvYXQoKSAqIHNjYWxlLCBudmFsdWUyID0gaW5wdXQucmVhZEZsb2F0KCkgKiBzY2FsZTtcblx0XHRzd2l0Y2ggKGlucHV0LnJlYWRCeXRlKCkpIHtcblx0XHRcdGNhc2UgQ1VSVkVfU1RFUFBFRDpcblx0XHRcdFx0dGltZWxpbmUuc2V0U3RlcHBlZChmcmFtZSk7XG5cdFx0XHRcdGJyZWFrO1xuXHRcdFx0Y2FzZSBDVVJWRV9CRVpJRVI6XG5cdFx0XHRcdHNldEJlemllcihpbnB1dCwgdGltZWxpbmUsIGJlemllcisrLCBmcmFtZSwgMCwgdGltZSwgdGltZTIsIHZhbHVlMSwgbnZhbHVlMSwgc2NhbGUpO1xuXHRcdFx0XHRzZXRCZXppZXIoaW5wdXQsIHRpbWVsaW5lLCBiZXppZXIrKywgZnJhbWUsIDEsIHRpbWUsIHRpbWUyLCB2YWx1ZTIsIG52YWx1ZTIsIHNjYWxlKTtcblx0XHR9XG5cdFx0dGltZSA9IHRpbWUyO1xuXHRcdHZhbHVlMSA9IG52YWx1ZTE7XG5cdFx0dmFsdWUyID0gbnZhbHVlMjtcblx0fVxuXHRyZXR1cm4gdGltZWxpbmU7XG59XG5cbmZ1bmN0aW9uIHNldEJlemllciAoaW5wdXQ6IEJpbmFyeUlucHV0LCB0aW1lbGluZTogQ3VydmVUaW1lbGluZSwgYmV6aWVyOiBudW1iZXIsIGZyYW1lOiBudW1iZXIsIHZhbHVlOiBudW1iZXIsXG5cdHRpbWUxOiBudW1iZXIsIHRpbWUyOiBudW1iZXIsIHZhbHVlMTogbnVtYmVyLCB2YWx1ZTI6IG51bWJlciwgc2NhbGU6IG51bWJlcikge1xuXHR0aW1lbGluZS5zZXRCZXppZXIoYmV6aWVyLCBmcmFtZSwgdmFsdWUsIHRpbWUxLCB2YWx1ZTEsIGlucHV0LnJlYWRGbG9hdCgpLCBpbnB1dC5yZWFkRmxvYXQoKSAqIHNjYWxlLCBpbnB1dC5yZWFkRmxvYXQoKSwgaW5wdXQucmVhZEZsb2F0KCkgKiBzY2FsZSwgdGltZTIsIHZhbHVlMik7XG59XG5cbmNvbnN0IEJPTkVfUk9UQVRFID0gMDtcbmNvbnN0IEJPTkVfVFJBTlNMQVRFID0gMTtcbmNvbnN0IEJPTkVfVFJBTlNMQVRFWCA9IDI7XG5jb25zdCBCT05FX1RSQU5TTEFURVkgPSAzO1xuY29uc3QgQk9ORV9TQ0FMRSA9IDQ7XG5jb25zdCBCT05FX1NDQUxFWCA9IDU7XG5jb25zdCBCT05FX1NDQUxFWSA9IDY7XG5jb25zdCBCT05FX1NIRUFSID0gNztcbmNvbnN0IEJPTkVfU0hFQVJYID0gODtcbmNvbnN0IEJPTkVfU0hFQVJZID0gOTtcbmNvbnN0IEJPTkVfSU5IRVJJVCA9IDEwO1xuXG5jb25zdCBTTE9UX0FUVEFDSE1FTlQgPSAwO1xuY29uc3QgU0xPVF9SR0JBID0gMTtcbmNvbnN0IFNMT1RfUkdCID0gMjtcbmNvbnN0IFNMT1RfUkdCQTIgPSAzO1xuY29uc3QgU0xPVF9SR0IyID0gNDtcbmNvbnN0IFNMT1RfQUxQSEEgPSA1O1xuXG5jb25zdCBBVFRBQ0hNRU5UX0RFRk9STSA9IDA7XG5jb25zdCBBVFRBQ0hNRU5UX1NFUVVFTkNFID0gMTtcblxuY29uc3QgUEFUSF9QT1NJVElPTiA9IDA7XG5jb25zdCBQQVRIX1NQQUNJTkcgPSAxO1xuY29uc3QgUEFUSF9NSVggPSAyO1xuXG5jb25zdCBQSFlTSUNTX0lORVJUSUEgPSAwO1xuY29uc3QgUEhZU0lDU19TVFJFTkdUSCA9IDE7XG5jb25zdCBQSFlTSUNTX0RBTVBJTkcgPSAyO1xuY29uc3QgUEhZU0lDU19NQVNTID0gNDtcbmNvbnN0IFBIWVNJQ1NfV0lORCA9IDU7XG5jb25zdCBQSFlTSUNTX0dSQVZJVFkgPSA2O1xuY29uc3QgUEhZU0lDU19NSVggPSA3O1xuY29uc3QgUEhZU0lDU19SRVNFVCA9IDg7XG5cbmNvbnN0IENVUlZFX0xJTkVBUiA9IDA7XG5jb25zdCBDVVJWRV9TVEVQUEVEID0gMTtcbmNvbnN0IENVUlZFX0JFWklFUiA9IDI7XG4iXX0=