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
import { MeshAttachment } from "./attachments/MeshAttachment.js";
import { Color } from "./Utils.js";
/** Stores an entry in the skin consisting of the slot index, name, and attachment **/
export class SkinEntry {
    slotIndex;
    name;
    attachment;
    constructor(slotIndex = 0, name, attachment) {
        this.slotIndex = slotIndex;
        this.name = name;
        this.attachment = attachment;
    }
}
/** Stores attachments by slot index and attachment name.
 *
 * See SkeletonData {@link SkeletonData#defaultSkin}, Skeleton {@link Skeleton#skin}, and
 * [Runtime skins](http://esotericsoftware.com/spine-runtime-skins) in the Spine Runtimes Guide. */
export class Skin {
    /** The skin's name, which is unique across all skins in the skeleton. */
    name;
    attachments = new Array();
    bones = Array();
    constraints = new Array();
    /** The color of the skin as it was in Spine, or a default color if nonessential data was not exported. */
    color = new Color(0.99607843, 0.61960787, 0.30980393, 1); // fe9e4fff
    constructor(name) {
        if (!name)
            throw new Error("name cannot be null.");
        this.name = name;
    }
    /** Adds an attachment to the skin for the specified slot index and name. */
    setAttachment(slotIndex, name, attachment) {
        if (!attachment)
            throw new Error("attachment cannot be null.");
        let attachments = this.attachments;
        if (slotIndex >= attachments.length)
            attachments.length = slotIndex + 1;
        if (!attachments[slotIndex])
            attachments[slotIndex] = {};
        attachments[slotIndex][name] = attachment;
    }
    /** Adds all attachments, bones, and constraints from the specified skin to this skin. */
    addSkin(skin) {
        for (let i = 0; i < skin.bones.length; i++) {
            let bone = skin.bones[i];
            let contained = false;
            for (let ii = 0; ii < this.bones.length; ii++) {
                if (this.bones[ii] == bone) {
                    contained = true;
                    break;
                }
            }
            if (!contained)
                this.bones.push(bone);
        }
        for (let i = 0; i < skin.constraints.length; i++) {
            let constraint = skin.constraints[i];
            let contained = false;
            for (let ii = 0; ii < this.constraints.length; ii++) {
                if (this.constraints[ii] == constraint) {
                    contained = true;
                    break;
                }
            }
            if (!contained)
                this.constraints.push(constraint);
        }
        let attachments = skin.getAttachments();
        for (let i = 0; i < attachments.length; i++) {
            var attachment = attachments[i];
            this.setAttachment(attachment.slotIndex, attachment.name, attachment.attachment);
        }
    }
    /** Adds all bones and constraints and copies of all attachments from the specified skin to this skin. Mesh attachments are not
     * copied, instead a new linked mesh is created. The attachment copies can be modified without affecting the originals. */
    copySkin(skin) {
        for (let i = 0; i < skin.bones.length; i++) {
            let bone = skin.bones[i];
            let contained = false;
            for (let ii = 0; ii < this.bones.length; ii++) {
                if (this.bones[ii] == bone) {
                    contained = true;
                    break;
                }
            }
            if (!contained)
                this.bones.push(bone);
        }
        for (let i = 0; i < skin.constraints.length; i++) {
            let constraint = skin.constraints[i];
            let contained = false;
            for (let ii = 0; ii < this.constraints.length; ii++) {
                if (this.constraints[ii] == constraint) {
                    contained = true;
                    break;
                }
            }
            if (!contained)
                this.constraints.push(constraint);
        }
        let attachments = skin.getAttachments();
        for (let i = 0; i < attachments.length; i++) {
            var attachment = attachments[i];
            if (!attachment.attachment)
                continue;
            if (attachment.attachment instanceof MeshAttachment) {
                attachment.attachment = attachment.attachment.newLinkedMesh();
                this.setAttachment(attachment.slotIndex, attachment.name, attachment.attachment);
            }
            else {
                attachment.attachment = attachment.attachment.copy();
                this.setAttachment(attachment.slotIndex, attachment.name, attachment.attachment);
            }
        }
    }
    /** Returns the attachment for the specified slot index and name, or null. */
    getAttachment(slotIndex, name) {
        let dictionary = this.attachments[slotIndex];
        return dictionary ? dictionary[name] : null;
    }
    /** Removes the attachment in the skin for the specified slot index and name, if any. */
    removeAttachment(slotIndex, name) {
        let dictionary = this.attachments[slotIndex];
        if (dictionary)
            delete dictionary[name];
    }
    /** Returns all attachments in this skin. */
    getAttachments() {
        let entries = new Array();
        for (var i = 0; i < this.attachments.length; i++) {
            let slotAttachments = this.attachments[i];
            if (slotAttachments) {
                for (let name in slotAttachments) {
                    let attachment = slotAttachments[name];
                    if (attachment)
                        entries.push(new SkinEntry(i, name, attachment));
                }
            }
        }
        return entries;
    }
    /** Returns all attachments in this skin for the specified slot index. */
    getAttachmentsForSlot(slotIndex, attachments) {
        let slotAttachments = this.attachments[slotIndex];
        if (slotAttachments) {
            for (let name in slotAttachments) {
                let attachment = slotAttachments[name];
                if (attachment)
                    attachments.push(new SkinEntry(slotIndex, name, attachment));
            }
        }
    }
    /** Clears all attachments, bones, and constraints. */
    clear() {
        this.attachments.length = 0;
        this.bones.length = 0;
        this.constraints.length = 0;
    }
    /** Attach each attachment in this skin if the corresponding attachment in the old skin is currently attached. */
    attachAll(skeleton, oldSkin) {
        let slotIndex = 0;
        for (let i = 0; i < skeleton.slots.length; i++) {
            let slot = skeleton.slots[i];
            let slotAttachment = slot.getAttachment();
            if (slotAttachment && slotIndex < oldSkin.attachments.length) {
                let dictionary = oldSkin.attachments[slotIndex];
                for (let key in dictionary) {
                    let skinAttachment = dictionary[key];
                    if (slotAttachment == skinAttachment) {
                        let attachment = this.getAttachment(slotIndex, key);
                        if (attachment)
                            slot.setAttachment(attachment);
                        break;
                    }
                }
            }
            slotIndex++;
        }
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiU2tpbi5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIi4uL3NyYy9Ta2luLnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiJBQUFBOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7K0VBMkIrRTtBQUcvRSxPQUFPLEVBQUUsY0FBYyxFQUFFLE1BQU0saUNBQWlDLENBQUM7QUFJakUsT0FBTyxFQUFFLEtBQUssRUFBYSxNQUFNLFlBQVksQ0FBQztBQUU5QyxzRkFBc0Y7QUFDdEYsTUFBTSxPQUFPLFNBQVM7SUFDRDtJQUE4QjtJQUFxQjtJQUF2RSxZQUFvQixZQUFvQixDQUFDLEVBQVMsSUFBWSxFQUFTLFVBQXNCO1FBQXpFLGNBQVMsR0FBVCxTQUFTLENBQVk7UUFBUyxTQUFJLEdBQUosSUFBSSxDQUFRO1FBQVMsZUFBVSxHQUFWLFVBQVUsQ0FBWTtJQUFJLENBQUM7Q0FDbEc7QUFFRDs7O21HQUdtRztBQUNuRyxNQUFNLE9BQU8sSUFBSTtJQUNoQix5RUFBeUU7SUFDekUsSUFBSSxDQUFTO0lBRWIsV0FBVyxHQUFHLElBQUksS0FBSyxFQUF5QixDQUFDO0lBQ2pELEtBQUssR0FBRyxLQUFLLEVBQVksQ0FBQztJQUMxQixXQUFXLEdBQUcsSUFBSSxLQUFLLEVBQWtCLENBQUM7SUFFMUMsMEdBQTBHO0lBQzFHLEtBQUssR0FBRyxJQUFJLEtBQUssQ0FBQyxVQUFVLEVBQUUsVUFBVSxFQUFFLFVBQVUsRUFBRSxDQUFDLENBQUMsQ0FBQyxDQUFDLFdBQVc7SUFFckUsWUFBYSxJQUFZO1FBQ3hCLElBQUksQ0FBQyxJQUFJO1lBQUUsTUFBTSxJQUFJLEtBQUssQ0FBQyxzQkFBc0IsQ0FBQyxDQUFDO1FBQ25ELElBQUksQ0FBQyxJQUFJLEdBQUcsSUFBSSxDQUFDO0lBQ2xCLENBQUM7SUFFRCw0RUFBNEU7SUFDNUUsYUFBYSxDQUFFLFNBQWlCLEVBQUUsSUFBWSxFQUFFLFVBQXNCO1FBQ3JFLElBQUksQ0FBQyxVQUFVO1lBQUUsTUFBTSxJQUFJLEtBQUssQ0FBQyw0QkFBNEIsQ0FBQyxDQUFDO1FBQy9ELElBQUksV0FBVyxHQUFHLElBQUksQ0FBQyxXQUFXLENBQUM7UUFDbkMsSUFBSSxTQUFTLElBQUksV0FBVyxDQUFDLE1BQU07WUFBRSxXQUFXLENBQUMsTUFBTSxHQUFHLFNBQVMsR0FBRyxDQUFDLENBQUM7UUFDeEUsSUFBSSxDQUFDLFdBQVcsQ0FBQyxTQUFTLENBQUM7WUFBRSxXQUFXLENBQUMsU0FBUyxDQUFDLEdBQUcsRUFBRSxDQUFDO1FBQ3pELFdBQVcsQ0FBQyxTQUFTLENBQUMsQ0FBQyxJQUFJLENBQUMsR0FBRyxVQUFVLENBQUM7SUFDM0MsQ0FBQztJQUVELHlGQUF5RjtJQUN6RixPQUFPLENBQUUsSUFBVTtRQUNsQixLQUFLLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxNQUFNLEVBQUUsQ0FBQyxFQUFFLEVBQUUsQ0FBQztZQUM1QyxJQUFJLElBQUksR0FBRyxJQUFJLENBQUMsS0FBSyxDQUFDLENBQUMsQ0FBQyxDQUFDO1lBQ3pCLElBQUksU0FBUyxHQUFHLEtBQUssQ0FBQztZQUN0QixLQUFLLElBQUksRUFBRSxHQUFHLENBQUMsRUFBRSxFQUFFLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxNQUFNLEVBQUUsRUFBRSxFQUFFLEVBQUUsQ0FBQztnQkFDL0MsSUFBSSxJQUFJLENBQUMsS0FBSyxDQUFDLEVBQUUsQ0FBQyxJQUFJLElBQUksRUFBRSxDQUFDO29CQUM1QixTQUFTLEdBQUcsSUFBSSxDQUFDO29CQUNqQixNQUFNO2dCQUNQLENBQUM7WUFDRixDQUFDO1lBQ0QsSUFBSSxDQUFDLFNBQVM7Z0JBQUUsSUFBSSxDQUFDLEtBQUssQ0FBQyxJQUFJLENBQUMsSUFBSSxDQUFDLENBQUM7UUFDdkMsQ0FBQztRQUVELEtBQUssSUFBSSxDQUFDLEdBQUcsQ0FBQyxFQUFFLENBQUMsR0FBRyxJQUFJLENBQUMsV0FBVyxDQUFDLE1BQU0sRUFBRSxDQUFDLEVBQUUsRUFBRSxDQUFDO1lBQ2xELElBQUksVUFBVSxHQUFHLElBQUksQ0FBQyxXQUFXLENBQUMsQ0FBQyxDQUFDLENBQUM7WUFDckMsSUFBSSxTQUFTLEdBQUcsS0FBSyxDQUFDO1lBQ3RCLEtBQUssSUFBSSxFQUFFLEdBQUcsQ0FBQyxFQUFFLEVBQUUsR0FBRyxJQUFJLENBQUMsV0FBVyxDQUFDLE1BQU0sRUFBRSxFQUFFLEVBQUUsRUFBRSxDQUFDO2dCQUNyRCxJQUFJLElBQUksQ0FBQyxXQUFXLENBQUMsRUFBRSxDQUFDLElBQUksVUFBVSxFQUFFLENBQUM7b0JBQ3hDLFNBQVMsR0FBRyxJQUFJLENBQUM7b0JBQ2pCLE1BQU07Z0JBQ1AsQ0FBQztZQUNGLENBQUM7WUFDRCxJQUFJLENBQUMsU0FBUztnQkFBRSxJQUFJLENBQUMsV0FBVyxDQUFDLElBQUksQ0FBQyxVQUFVLENBQUMsQ0FBQztRQUNuRCxDQUFDO1FBRUQsSUFBSSxXQUFXLEdBQUcsSUFBSSxDQUFDLGNBQWMsRUFBRSxDQUFDO1FBQ3hDLEtBQUssSUFBSSxDQUFDLEdBQUcsQ0FBQyxFQUFFLENBQUMsR0FBRyxXQUFXLENBQUMsTUFBTSxFQUFFLENBQUMsRUFBRSxFQUFFLENBQUM7WUFDN0MsSUFBSSxVQUFVLEdBQUcsV0FBVyxDQUFDLENBQUMsQ0FBQyxDQUFDO1lBQ2hDLElBQUksQ0FBQyxhQUFhLENBQUMsVUFBVSxDQUFDLFNBQVMsRUFBRSxVQUFVLENBQUMsSUFBSSxFQUFFLFVBQVUsQ0FBQyxVQUFVLENBQUMsQ0FBQztRQUNsRixDQUFDO0lBQ0YsQ0FBQztJQUVEOzhIQUMwSDtJQUMxSCxRQUFRLENBQUUsSUFBVTtRQUNuQixLQUFLLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxNQUFNLEVBQUUsQ0FBQyxFQUFFLEVBQUUsQ0FBQztZQUM1QyxJQUFJLElBQUksR0FBRyxJQUFJLENBQUMsS0FBSyxDQUFDLENBQUMsQ0FBQyxDQUFDO1lBQ3pCLElBQUksU0FBUyxHQUFHLEtBQUssQ0FBQztZQUN0QixLQUFLLElBQUksRUFBRSxHQUFHLENBQUMsRUFBRSxFQUFFLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxNQUFNLEVBQUUsRUFBRSxFQUFFLEVBQUUsQ0FBQztnQkFDL0MsSUFBSSxJQUFJLENBQUMsS0FBSyxDQUFDLEVBQUUsQ0FBQyxJQUFJLElBQUksRUFBRSxDQUFDO29CQUM1QixTQUFTLEdBQUcsSUFBSSxDQUFDO29CQUNqQixNQUFNO2dCQUNQLENBQUM7WUFDRixDQUFDO1lBQ0QsSUFBSSxDQUFDLFNBQVM7Z0JBQUUsSUFBSSxDQUFDLEtBQUssQ0FBQyxJQUFJLENBQUMsSUFBSSxDQUFDLENBQUM7UUFDdkMsQ0FBQztRQUVELEtBQUssSUFBSSxDQUFDLEdBQUcsQ0FBQyxFQUFFLENBQUMsR0FBRyxJQUFJLENBQUMsV0FBVyxDQUFDLE1BQU0sRUFBRSxDQUFDLEVBQUUsRUFBRSxDQUFDO1lBQ2xELElBQUksVUFBVSxHQUFHLElBQUksQ0FBQyxXQUFXLENBQUMsQ0FBQyxDQUFDLENBQUM7WUFDckMsSUFBSSxTQUFTLEdBQUcsS0FBSyxDQUFDO1lBQ3RCLEtBQUssSUFBSSxFQUFFLEdBQUcsQ0FBQyxFQUFFLEVBQUUsR0FBRyxJQUFJLENBQUMsV0FBVyxDQUFDLE1BQU0sRUFBRSxFQUFFLEVBQUUsRUFBRSxDQUFDO2dCQUNyRCxJQUFJLElBQUksQ0FBQyxXQUFXLENBQUMsRUFBRSxDQUFDLElBQUksVUFBVSxFQUFFLENBQUM7b0JBQ3hDLFNBQVMsR0FBRyxJQUFJLENBQUM7b0JBQ2pCLE1BQU07Z0JBQ1AsQ0FBQztZQUNGLENBQUM7WUFDRCxJQUFJLENBQUMsU0FBUztnQkFBRSxJQUFJLENBQUMsV0FBVyxDQUFDLElBQUksQ0FBQyxVQUFVLENBQUMsQ0FBQztRQUNuRCxDQUFDO1FBRUQsSUFBSSxXQUFXLEdBQUcsSUFBSSxDQUFDLGNBQWMsRUFBRSxDQUFDO1FBQ3hDLEtBQUssSUFBSSxDQUFDLEdBQUcsQ0FBQyxFQUFFLENBQUMsR0FBRyxXQUFXLENBQUMsTUFBTSxFQUFFLENBQUMsRUFBRSxFQUFFLENBQUM7WUFDN0MsSUFBSSxVQUFVLEdBQUcsV0FBVyxDQUFDLENBQUMsQ0FBQyxDQUFDO1lBQ2hDLElBQUksQ0FBQyxVQUFVLENBQUMsVUFBVTtnQkFBRSxTQUFTO1lBQ3JDLElBQUksVUFBVSxDQUFDLFVBQVUsWUFBWSxjQUFjLEVBQUUsQ0FBQztnQkFDckQsVUFBVSxDQUFDLFVBQVUsR0FBRyxVQUFVLENBQUMsVUFBVSxDQUFDLGFBQWEsRUFBRSxDQUFDO2dCQUM5RCxJQUFJLENBQUMsYUFBYSxDQUFDLFVBQVUsQ0FBQyxTQUFTLEVBQUUsVUFBVSxDQUFDLElBQUksRUFBRSxVQUFVLENBQUMsVUFBVSxDQUFDLENBQUM7WUFDbEYsQ0FBQztpQkFBTSxDQUFDO2dCQUNQLFVBQVUsQ0FBQyxVQUFVLEdBQUcsVUFBVSxDQUFDLFVBQVUsQ0FBQyxJQUFJLEVBQUUsQ0FBQztnQkFDckQsSUFBSSxDQUFDLGFBQWEsQ0FBQyxVQUFVLENBQUMsU0FBUyxFQUFFLFVBQVUsQ0FBQyxJQUFJLEVBQUUsVUFBVSxDQUFDLFVBQVUsQ0FBQyxDQUFDO1lBQ2xGLENBQUM7UUFDRixDQUFDO0lBQ0YsQ0FBQztJQUVELDZFQUE2RTtJQUM3RSxhQUFhLENBQUUsU0FBaUIsRUFBRSxJQUFZO1FBQzdDLElBQUksVUFBVSxHQUFHLElBQUksQ0FBQyxXQUFXLENBQUMsU0FBUyxDQUFDLENBQUM7UUFDN0MsT0FBTyxVQUFVLENBQUMsQ0FBQyxDQUFDLFVBQVUsQ0FBQyxJQUFJLENBQUMsQ0FBQyxDQUFDLENBQUMsSUFBSSxDQUFDO0lBQzdDLENBQUM7SUFFRCx3RkFBd0Y7SUFDeEYsZ0JBQWdCLENBQUUsU0FBaUIsRUFBRSxJQUFZO1FBQ2hELElBQUksVUFBVSxHQUFHLElBQUksQ0FBQyxXQUFXLENBQUMsU0FBUyxDQUFDLENBQUM7UUFDN0MsSUFBSSxVQUFVO1lBQUUsT0FBTyxVQUFVLENBQUMsSUFBSSxDQUFDLENBQUM7SUFDekMsQ0FBQztJQUVELDRDQUE0QztJQUM1QyxjQUFjO1FBQ2IsSUFBSSxPQUFPLEdBQUcsSUFBSSxLQUFLLEVBQWEsQ0FBQztRQUNyQyxLQUFLLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsSUFBSSxDQUFDLFdBQVcsQ0FBQyxNQUFNLEVBQUUsQ0FBQyxFQUFFLEVBQUUsQ0FBQztZQUNsRCxJQUFJLGVBQWUsR0FBRyxJQUFJLENBQUMsV0FBVyxDQUFDLENBQUMsQ0FBQyxDQUFDO1lBQzFDLElBQUksZUFBZSxFQUFFLENBQUM7Z0JBQ3JCLEtBQUssSUFBSSxJQUFJLElBQUksZUFBZSxFQUFFLENBQUM7b0JBQ2xDLElBQUksVUFBVSxHQUFHLGVBQWUsQ0FBQyxJQUFJLENBQUMsQ0FBQztvQkFDdkMsSUFBSSxVQUFVO3dCQUFFLE9BQU8sQ0FBQyxJQUFJLENBQUMsSUFBSSxTQUFTLENBQUMsQ0FBQyxFQUFFLElBQUksRUFBRSxVQUFVLENBQUMsQ0FBQyxDQUFDO2dCQUNsRSxDQUFDO1lBQ0YsQ0FBQztRQUNGLENBQUM7UUFDRCxPQUFPLE9BQU8sQ0FBQztJQUNoQixDQUFDO0lBRUQseUVBQXlFO0lBQ3pFLHFCQUFxQixDQUFFLFNBQWlCLEVBQUUsV0FBNkI7UUFDdEUsSUFBSSxlQUFlLEdBQUcsSUFBSSxDQUFDLFdBQVcsQ0FBQyxTQUFTLENBQUMsQ0FBQztRQUNsRCxJQUFJLGVBQWUsRUFBRSxDQUFDO1lBQ3JCLEtBQUssSUFBSSxJQUFJLElBQUksZUFBZSxFQUFFLENBQUM7Z0JBQ2xDLElBQUksVUFBVSxHQUFHLGVBQWUsQ0FBQyxJQUFJLENBQUMsQ0FBQztnQkFDdkMsSUFBSSxVQUFVO29CQUFFLFdBQVcsQ0FBQyxJQUFJLENBQUMsSUFBSSxTQUFTLENBQUMsU0FBUyxFQUFFLElBQUksRUFBRSxVQUFVLENBQUMsQ0FBQyxDQUFDO1lBQzlFLENBQUM7UUFDRixDQUFDO0lBQ0YsQ0FBQztJQUVELHNEQUFzRDtJQUN0RCxLQUFLO1FBQ0osSUFBSSxDQUFDLFdBQVcsQ0FBQyxNQUFNLEdBQUcsQ0FBQyxDQUFDO1FBQzVCLElBQUksQ0FBQyxLQUFLLENBQUMsTUFBTSxHQUFHLENBQUMsQ0FBQztRQUN0QixJQUFJLENBQUMsV0FBVyxDQUFDLE1BQU0sR0FBRyxDQUFDLENBQUM7SUFDN0IsQ0FBQztJQUVELGlIQUFpSDtJQUNqSCxTQUFTLENBQUUsUUFBa0IsRUFBRSxPQUFhO1FBQzNDLElBQUksU0FBUyxHQUFHLENBQUMsQ0FBQztRQUNsQixLQUFLLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsUUFBUSxDQUFDLEtBQUssQ0FBQyxNQUFNLEVBQUUsQ0FBQyxFQUFFLEVBQUUsQ0FBQztZQUNoRCxJQUFJLElBQUksR0FBRyxRQUFRLENBQUMsS0FBSyxDQUFDLENBQUMsQ0FBQyxDQUFDO1lBQzdCLElBQUksY0FBYyxHQUFHLElBQUksQ0FBQyxhQUFhLEVBQUUsQ0FBQztZQUMxQyxJQUFJLGNBQWMsSUFBSSxTQUFTLEdBQUcsT0FBTyxDQUFDLFdBQVcsQ0FBQyxNQUFNLEVBQUUsQ0FBQztnQkFDOUQsSUFBSSxVQUFVLEdBQUcsT0FBTyxDQUFDLFdBQVcsQ0FBQyxTQUFTLENBQUMsQ0FBQztnQkFDaEQsS0FBSyxJQUFJLEdBQUcsSUFBSSxVQUFVLEVBQUUsQ0FBQztvQkFDNUIsSUFBSSxjQUFjLEdBQWUsVUFBVSxDQUFDLEdBQUcsQ0FBQyxDQUFDO29CQUNqRCxJQUFJLGNBQWMsSUFBSSxjQUFjLEVBQUUsQ0FBQzt3QkFDdEMsSUFBSSxVQUFVLEdBQUcsSUFBSSxDQUFDLGFBQWEsQ0FBQyxTQUFTLEVBQUUsR0FBRyxDQUFDLENBQUM7d0JBQ3BELElBQUksVUFBVTs0QkFBRSxJQUFJLENBQUMsYUFBYSxDQUFDLFVBQVUsQ0FBQyxDQUFDO3dCQUMvQyxNQUFNO29CQUNQLENBQUM7Z0JBQ0YsQ0FBQztZQUNGLENBQUM7WUFDRCxTQUFTLEVBQUUsQ0FBQztRQUNiLENBQUM7SUFDRixDQUFDO0NBQ0QiLCJzb3VyY2VzQ29udGVudCI6WyIvKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqXG4gKiBTcGluZSBSdW50aW1lcyBMaWNlbnNlIEFncmVlbWVudFxuICogTGFzdCB1cGRhdGVkIEFwcmlsIDUsIDIwMjUuIFJlcGxhY2VzIGFsbCBwcmlvciB2ZXJzaW9ucy5cbiAqXG4gKiBDb3B5cmlnaHQgKGMpIDIwMTMtMjAyNSwgRXNvdGVyaWMgU29mdHdhcmUgTExDXG4gKlxuICogSW50ZWdyYXRpb24gb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmUgb3Igb3RoZXJ3aXNlIGNyZWF0aW5nXG4gKiBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpcyBwZXJtaXR0ZWQgdW5kZXIgdGhlIHRlcm1zIGFuZFxuICogY29uZGl0aW9ucyBvZiBTZWN0aW9uIDIgb2YgdGhlIFNwaW5lIEVkaXRvciBMaWNlbnNlIEFncmVlbWVudDpcbiAqIGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1lZGl0b3ItbGljZW5zZVxuICpcbiAqIE90aGVyd2lzZSwgaXQgaXMgcGVybWl0dGVkIHRvIGludGVncmF0ZSB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZVxuICogb3Igb3RoZXJ3aXNlIGNyZWF0ZSBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyAoY29sbGVjdGl2ZWx5LFxuICogXCJQcm9kdWN0c1wiKSwgcHJvdmlkZWQgdGhhdCBlYWNoIHVzZXIgb2YgdGhlIFByb2R1Y3RzIG11c3Qgb2J0YWluIHRoZWlyIG93blxuICogU3BpbmUgRWRpdG9yIGxpY2Vuc2UgYW5kIHJlZGlzdHJpYnV0aW9uIG9mIHRoZSBQcm9kdWN0cyBpbiBhbnkgZm9ybSBtdXN0XG4gKiBpbmNsdWRlIHRoaXMgbGljZW5zZSBhbmQgY29weXJpZ2h0IG5vdGljZS5cbiAqXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMgQVJFIFBST1ZJREVEIEJZIEVTT1RFUklDIFNPRlRXQVJFIExMQyBcIkFTIElTXCIgQU5EIEFOWVxuICogRVhQUkVTUyBPUiBJTVBMSUVEIFdBUlJBTlRJRVMsIElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBUSEUgSU1QTElFRFxuICogV0FSUkFOVElFUyBPRiBNRVJDSEFOVEFCSUxJVFkgQU5EIEZJVE5FU1MgRk9SIEEgUEFSVElDVUxBUiBQVVJQT1NFIEFSRVxuICogRElTQ0xBSU1FRC4gSU4gTk8gRVZFTlQgU0hBTEwgRVNPVEVSSUMgU09GVFdBUkUgTExDIEJFIExJQUJMRSBGT1IgQU5ZXG4gKiBESVJFQ1QsIElORElSRUNULCBJTkNJREVOVEFMLCBTUEVDSUFMLCBFWEVNUExBUlksIE9SIENPTlNFUVVFTlRJQUwgREFNQUdFU1xuICogKElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBQUk9DVVJFTUVOVCBPRiBTVUJTVElUVVRFIEdPT0RTIE9SIFNFUlZJQ0VTLFxuICogQlVTSU5FU1MgSU5URVJSVVBUSU9OLCBPUiBMT1NTIE9GIFVTRSwgREFUQSwgT1IgUFJPRklUUykgSE9XRVZFUiBDQVVTRUQgQU5EXG4gKiBPTiBBTlkgVEhFT1JZIE9GIExJQUJJTElUWSwgV0hFVEhFUiBJTiBDT05UUkFDVCwgU1RSSUNUIExJQUJJTElUWSwgT1IgVE9SVFxuICogKElOQ0xVRElORyBORUdMSUdFTkNFIE9SIE9USEVSV0lTRSkgQVJJU0lORyBJTiBBTlkgV0FZIE9VVCBPRiBUSEUgVVNFIE9GXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMsIEVWRU4gSUYgQURWSVNFRCBPRiBUSEUgUE9TU0lCSUxJVFkgT0YgU1VDSCBEQU1BR0UuXG4gKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKiovXG5cbmltcG9ydCB7IEF0dGFjaG1lbnQgfSBmcm9tIFwiLi9hdHRhY2htZW50cy9BdHRhY2htZW50LmpzXCI7XG5pbXBvcnQgeyBNZXNoQXR0YWNobWVudCB9IGZyb20gXCIuL2F0dGFjaG1lbnRzL01lc2hBdHRhY2htZW50LmpzXCI7XG5pbXBvcnQgeyBCb25lRGF0YSB9IGZyb20gXCIuL0JvbmVEYXRhLmpzXCI7XG5pbXBvcnQgeyBDb25zdHJhaW50RGF0YSB9IGZyb20gXCIuL0NvbnN0cmFpbnREYXRhLmpzXCI7XG5pbXBvcnQgeyBTa2VsZXRvbiB9IGZyb20gXCIuL1NrZWxldG9uLmpzXCI7XG5pbXBvcnQgeyBDb2xvciwgU3RyaW5nTWFwIH0gZnJvbSBcIi4vVXRpbHMuanNcIjtcblxuLyoqIFN0b3JlcyBhbiBlbnRyeSBpbiB0aGUgc2tpbiBjb25zaXN0aW5nIG9mIHRoZSBzbG90IGluZGV4LCBuYW1lLCBhbmQgYXR0YWNobWVudCAqKi9cbmV4cG9ydCBjbGFzcyBTa2luRW50cnkge1xuXHRjb25zdHJ1Y3RvciAocHVibGljIHNsb3RJbmRleDogbnVtYmVyID0gMCwgcHVibGljIG5hbWU6IHN0cmluZywgcHVibGljIGF0dGFjaG1lbnQ6IEF0dGFjaG1lbnQpIHsgfVxufVxuXG4vKiogU3RvcmVzIGF0dGFjaG1lbnRzIGJ5IHNsb3QgaW5kZXggYW5kIGF0dGFjaG1lbnQgbmFtZS5cbiAqXG4gKiBTZWUgU2tlbGV0b25EYXRhIHtAbGluayBTa2VsZXRvbkRhdGEjZGVmYXVsdFNraW59LCBTa2VsZXRvbiB7QGxpbmsgU2tlbGV0b24jc2tpbn0sIGFuZFxuICogW1J1bnRpbWUgc2tpbnNdKGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1ydW50aW1lLXNraW5zKSBpbiB0aGUgU3BpbmUgUnVudGltZXMgR3VpZGUuICovXG5leHBvcnQgY2xhc3MgU2tpbiB7XG5cdC8qKiBUaGUgc2tpbidzIG5hbWUsIHdoaWNoIGlzIHVuaXF1ZSBhY3Jvc3MgYWxsIHNraW5zIGluIHRoZSBza2VsZXRvbi4gKi9cblx0bmFtZTogc3RyaW5nO1xuXG5cdGF0dGFjaG1lbnRzID0gbmV3IEFycmF5PFN0cmluZ01hcDxBdHRhY2htZW50Pj4oKTtcblx0Ym9uZXMgPSBBcnJheTxCb25lRGF0YT4oKTtcblx0Y29uc3RyYWludHMgPSBuZXcgQXJyYXk8Q29uc3RyYWludERhdGE+KCk7XG5cblx0LyoqIFRoZSBjb2xvciBvZiB0aGUgc2tpbiBhcyBpdCB3YXMgaW4gU3BpbmUsIG9yIGEgZGVmYXVsdCBjb2xvciBpZiBub25lc3NlbnRpYWwgZGF0YSB3YXMgbm90IGV4cG9ydGVkLiAqL1xuXHRjb2xvciA9IG5ldyBDb2xvcigwLjk5NjA3ODQzLCAwLjYxOTYwNzg3LCAwLjMwOTgwMzkzLCAxKTsgLy8gZmU5ZTRmZmZcblxuXHRjb25zdHJ1Y3RvciAobmFtZTogc3RyaW5nKSB7XG5cdFx0aWYgKCFuYW1lKSB0aHJvdyBuZXcgRXJyb3IoXCJuYW1lIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHR0aGlzLm5hbWUgPSBuYW1lO1xuXHR9XG5cblx0LyoqIEFkZHMgYW4gYXR0YWNobWVudCB0byB0aGUgc2tpbiBmb3IgdGhlIHNwZWNpZmllZCBzbG90IGluZGV4IGFuZCBuYW1lLiAqL1xuXHRzZXRBdHRhY2htZW50IChzbG90SW5kZXg6IG51bWJlciwgbmFtZTogc3RyaW5nLCBhdHRhY2htZW50OiBBdHRhY2htZW50KSB7XG5cdFx0aWYgKCFhdHRhY2htZW50KSB0aHJvdyBuZXcgRXJyb3IoXCJhdHRhY2htZW50IGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRsZXQgYXR0YWNobWVudHMgPSB0aGlzLmF0dGFjaG1lbnRzO1xuXHRcdGlmIChzbG90SW5kZXggPj0gYXR0YWNobWVudHMubGVuZ3RoKSBhdHRhY2htZW50cy5sZW5ndGggPSBzbG90SW5kZXggKyAxO1xuXHRcdGlmICghYXR0YWNobWVudHNbc2xvdEluZGV4XSkgYXR0YWNobWVudHNbc2xvdEluZGV4XSA9IHt9O1xuXHRcdGF0dGFjaG1lbnRzW3Nsb3RJbmRleF1bbmFtZV0gPSBhdHRhY2htZW50O1xuXHR9XG5cblx0LyoqIEFkZHMgYWxsIGF0dGFjaG1lbnRzLCBib25lcywgYW5kIGNvbnN0cmFpbnRzIGZyb20gdGhlIHNwZWNpZmllZCBza2luIHRvIHRoaXMgc2tpbi4gKi9cblx0YWRkU2tpbiAoc2tpbjogU2tpbikge1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgc2tpbi5ib25lcy5sZW5ndGg7IGkrKykge1xuXHRcdFx0bGV0IGJvbmUgPSBza2luLmJvbmVzW2ldO1xuXHRcdFx0bGV0IGNvbnRhaW5lZCA9IGZhbHNlO1xuXHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IHRoaXMuYm9uZXMubGVuZ3RoOyBpaSsrKSB7XG5cdFx0XHRcdGlmICh0aGlzLmJvbmVzW2lpXSA9PSBib25lKSB7XG5cdFx0XHRcdFx0Y29udGFpbmVkID0gdHJ1ZTtcblx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0fVxuXHRcdFx0fVxuXHRcdFx0aWYgKCFjb250YWluZWQpIHRoaXMuYm9uZXMucHVzaChib25lKTtcblx0XHR9XG5cblx0XHRmb3IgKGxldCBpID0gMDsgaSA8IHNraW4uY29uc3RyYWludHMubGVuZ3RoOyBpKyspIHtcblx0XHRcdGxldCBjb25zdHJhaW50ID0gc2tpbi5jb25zdHJhaW50c1tpXTtcblx0XHRcdGxldCBjb250YWluZWQgPSBmYWxzZTtcblx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCB0aGlzLmNvbnN0cmFpbnRzLmxlbmd0aDsgaWkrKykge1xuXHRcdFx0XHRpZiAodGhpcy5jb25zdHJhaW50c1tpaV0gPT0gY29uc3RyYWludCkge1xuXHRcdFx0XHRcdGNvbnRhaW5lZCA9IHRydWU7XG5cdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHRcdGlmICghY29udGFpbmVkKSB0aGlzLmNvbnN0cmFpbnRzLnB1c2goY29uc3RyYWludCk7XG5cdFx0fVxuXG5cdFx0bGV0IGF0dGFjaG1lbnRzID0gc2tpbi5nZXRBdHRhY2htZW50cygpO1xuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgYXR0YWNobWVudHMubGVuZ3RoOyBpKyspIHtcblx0XHRcdHZhciBhdHRhY2htZW50ID0gYXR0YWNobWVudHNbaV07XG5cdFx0XHR0aGlzLnNldEF0dGFjaG1lbnQoYXR0YWNobWVudC5zbG90SW5kZXgsIGF0dGFjaG1lbnQubmFtZSwgYXR0YWNobWVudC5hdHRhY2htZW50KTtcblx0XHR9XG5cdH1cblxuXHQvKiogQWRkcyBhbGwgYm9uZXMgYW5kIGNvbnN0cmFpbnRzIGFuZCBjb3BpZXMgb2YgYWxsIGF0dGFjaG1lbnRzIGZyb20gdGhlIHNwZWNpZmllZCBza2luIHRvIHRoaXMgc2tpbi4gTWVzaCBhdHRhY2htZW50cyBhcmUgbm90XG5cdCAqIGNvcGllZCwgaW5zdGVhZCBhIG5ldyBsaW5rZWQgbWVzaCBpcyBjcmVhdGVkLiBUaGUgYXR0YWNobWVudCBjb3BpZXMgY2FuIGJlIG1vZGlmaWVkIHdpdGhvdXQgYWZmZWN0aW5nIHRoZSBvcmlnaW5hbHMuICovXG5cdGNvcHlTa2luIChza2luOiBTa2luKSB7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBza2luLmJvbmVzLmxlbmd0aDsgaSsrKSB7XG5cdFx0XHRsZXQgYm9uZSA9IHNraW4uYm9uZXNbaV07XG5cdFx0XHRsZXQgY29udGFpbmVkID0gZmFsc2U7XG5cdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgdGhpcy5ib25lcy5sZW5ndGg7IGlpKyspIHtcblx0XHRcdFx0aWYgKHRoaXMuYm9uZXNbaWldID09IGJvbmUpIHtcblx0XHRcdFx0XHRjb250YWluZWQgPSB0cnVlO1xuXHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0XHRpZiAoIWNvbnRhaW5lZCkgdGhpcy5ib25lcy5wdXNoKGJvbmUpO1xuXHRcdH1cblxuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgc2tpbi5jb25zdHJhaW50cy5sZW5ndGg7IGkrKykge1xuXHRcdFx0bGV0IGNvbnN0cmFpbnQgPSBza2luLmNvbnN0cmFpbnRzW2ldO1xuXHRcdFx0bGV0IGNvbnRhaW5lZCA9IGZhbHNlO1xuXHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IHRoaXMuY29uc3RyYWludHMubGVuZ3RoOyBpaSsrKSB7XG5cdFx0XHRcdGlmICh0aGlzLmNvbnN0cmFpbnRzW2lpXSA9PSBjb25zdHJhaW50KSB7XG5cdFx0XHRcdFx0Y29udGFpbmVkID0gdHJ1ZTtcblx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0fVxuXHRcdFx0fVxuXHRcdFx0aWYgKCFjb250YWluZWQpIHRoaXMuY29uc3RyYWludHMucHVzaChjb25zdHJhaW50KTtcblx0XHR9XG5cblx0XHRsZXQgYXR0YWNobWVudHMgPSBza2luLmdldEF0dGFjaG1lbnRzKCk7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBhdHRhY2htZW50cy5sZW5ndGg7IGkrKykge1xuXHRcdFx0dmFyIGF0dGFjaG1lbnQgPSBhdHRhY2htZW50c1tpXTtcblx0XHRcdGlmICghYXR0YWNobWVudC5hdHRhY2htZW50KSBjb250aW51ZTtcblx0XHRcdGlmIChhdHRhY2htZW50LmF0dGFjaG1lbnQgaW5zdGFuY2VvZiBNZXNoQXR0YWNobWVudCkge1xuXHRcdFx0XHRhdHRhY2htZW50LmF0dGFjaG1lbnQgPSBhdHRhY2htZW50LmF0dGFjaG1lbnQubmV3TGlua2VkTWVzaCgpO1xuXHRcdFx0XHR0aGlzLnNldEF0dGFjaG1lbnQoYXR0YWNobWVudC5zbG90SW5kZXgsIGF0dGFjaG1lbnQubmFtZSwgYXR0YWNobWVudC5hdHRhY2htZW50KTtcblx0XHRcdH0gZWxzZSB7XG5cdFx0XHRcdGF0dGFjaG1lbnQuYXR0YWNobWVudCA9IGF0dGFjaG1lbnQuYXR0YWNobWVudC5jb3B5KCk7XG5cdFx0XHRcdHRoaXMuc2V0QXR0YWNobWVudChhdHRhY2htZW50LnNsb3RJbmRleCwgYXR0YWNobWVudC5uYW1lLCBhdHRhY2htZW50LmF0dGFjaG1lbnQpO1xuXHRcdFx0fVxuXHRcdH1cblx0fVxuXG5cdC8qKiBSZXR1cm5zIHRoZSBhdHRhY2htZW50IGZvciB0aGUgc3BlY2lmaWVkIHNsb3QgaW5kZXggYW5kIG5hbWUsIG9yIG51bGwuICovXG5cdGdldEF0dGFjaG1lbnQgKHNsb3RJbmRleDogbnVtYmVyLCBuYW1lOiBzdHJpbmcpOiBBdHRhY2htZW50IHwgbnVsbCB7XG5cdFx0bGV0IGRpY3Rpb25hcnkgPSB0aGlzLmF0dGFjaG1lbnRzW3Nsb3RJbmRleF07XG5cdFx0cmV0dXJuIGRpY3Rpb25hcnkgPyBkaWN0aW9uYXJ5W25hbWVdIDogbnVsbDtcblx0fVxuXG5cdC8qKiBSZW1vdmVzIHRoZSBhdHRhY2htZW50IGluIHRoZSBza2luIGZvciB0aGUgc3BlY2lmaWVkIHNsb3QgaW5kZXggYW5kIG5hbWUsIGlmIGFueS4gKi9cblx0cmVtb3ZlQXR0YWNobWVudCAoc2xvdEluZGV4OiBudW1iZXIsIG5hbWU6IHN0cmluZykge1xuXHRcdGxldCBkaWN0aW9uYXJ5ID0gdGhpcy5hdHRhY2htZW50c1tzbG90SW5kZXhdO1xuXHRcdGlmIChkaWN0aW9uYXJ5KSBkZWxldGUgZGljdGlvbmFyeVtuYW1lXTtcblx0fVxuXG5cdC8qKiBSZXR1cm5zIGFsbCBhdHRhY2htZW50cyBpbiB0aGlzIHNraW4uICovXG5cdGdldEF0dGFjaG1lbnRzICgpOiBBcnJheTxTa2luRW50cnk+IHtcblx0XHRsZXQgZW50cmllcyA9IG5ldyBBcnJheTxTa2luRW50cnk+KCk7XG5cdFx0Zm9yICh2YXIgaSA9IDA7IGkgPCB0aGlzLmF0dGFjaG1lbnRzLmxlbmd0aDsgaSsrKSB7XG5cdFx0XHRsZXQgc2xvdEF0dGFjaG1lbnRzID0gdGhpcy5hdHRhY2htZW50c1tpXTtcblx0XHRcdGlmIChzbG90QXR0YWNobWVudHMpIHtcblx0XHRcdFx0Zm9yIChsZXQgbmFtZSBpbiBzbG90QXR0YWNobWVudHMpIHtcblx0XHRcdFx0XHRsZXQgYXR0YWNobWVudCA9IHNsb3RBdHRhY2htZW50c1tuYW1lXTtcblx0XHRcdFx0XHRpZiAoYXR0YWNobWVudCkgZW50cmllcy5wdXNoKG5ldyBTa2luRW50cnkoaSwgbmFtZSwgYXR0YWNobWVudCkpO1xuXHRcdFx0XHR9XG5cdFx0XHR9XG5cdFx0fVxuXHRcdHJldHVybiBlbnRyaWVzO1xuXHR9XG5cblx0LyoqIFJldHVybnMgYWxsIGF0dGFjaG1lbnRzIGluIHRoaXMgc2tpbiBmb3IgdGhlIHNwZWNpZmllZCBzbG90IGluZGV4LiAqL1xuXHRnZXRBdHRhY2htZW50c0ZvclNsb3QgKHNsb3RJbmRleDogbnVtYmVyLCBhdHRhY2htZW50czogQXJyYXk8U2tpbkVudHJ5Pikge1xuXHRcdGxldCBzbG90QXR0YWNobWVudHMgPSB0aGlzLmF0dGFjaG1lbnRzW3Nsb3RJbmRleF07XG5cdFx0aWYgKHNsb3RBdHRhY2htZW50cykge1xuXHRcdFx0Zm9yIChsZXQgbmFtZSBpbiBzbG90QXR0YWNobWVudHMpIHtcblx0XHRcdFx0bGV0IGF0dGFjaG1lbnQgPSBzbG90QXR0YWNobWVudHNbbmFtZV07XG5cdFx0XHRcdGlmIChhdHRhY2htZW50KSBhdHRhY2htZW50cy5wdXNoKG5ldyBTa2luRW50cnkoc2xvdEluZGV4LCBuYW1lLCBhdHRhY2htZW50KSk7XG5cdFx0XHR9XG5cdFx0fVxuXHR9XG5cblx0LyoqIENsZWFycyBhbGwgYXR0YWNobWVudHMsIGJvbmVzLCBhbmQgY29uc3RyYWludHMuICovXG5cdGNsZWFyICgpIHtcblx0XHR0aGlzLmF0dGFjaG1lbnRzLmxlbmd0aCA9IDA7XG5cdFx0dGhpcy5ib25lcy5sZW5ndGggPSAwO1xuXHRcdHRoaXMuY29uc3RyYWludHMubGVuZ3RoID0gMDtcblx0fVxuXG5cdC8qKiBBdHRhY2ggZWFjaCBhdHRhY2htZW50IGluIHRoaXMgc2tpbiBpZiB0aGUgY29ycmVzcG9uZGluZyBhdHRhY2htZW50IGluIHRoZSBvbGQgc2tpbiBpcyBjdXJyZW50bHkgYXR0YWNoZWQuICovXG5cdGF0dGFjaEFsbCAoc2tlbGV0b246IFNrZWxldG9uLCBvbGRTa2luOiBTa2luKSB7XG5cdFx0bGV0IHNsb3RJbmRleCA9IDA7XG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBza2VsZXRvbi5zbG90cy5sZW5ndGg7IGkrKykge1xuXHRcdFx0bGV0IHNsb3QgPSBza2VsZXRvbi5zbG90c1tpXTtcblx0XHRcdGxldCBzbG90QXR0YWNobWVudCA9IHNsb3QuZ2V0QXR0YWNobWVudCgpO1xuXHRcdFx0aWYgKHNsb3RBdHRhY2htZW50ICYmIHNsb3RJbmRleCA8IG9sZFNraW4uYXR0YWNobWVudHMubGVuZ3RoKSB7XG5cdFx0XHRcdGxldCBkaWN0aW9uYXJ5ID0gb2xkU2tpbi5hdHRhY2htZW50c1tzbG90SW5kZXhdO1xuXHRcdFx0XHRmb3IgKGxldCBrZXkgaW4gZGljdGlvbmFyeSkge1xuXHRcdFx0XHRcdGxldCBza2luQXR0YWNobWVudDogQXR0YWNobWVudCA9IGRpY3Rpb25hcnlba2V5XTtcblx0XHRcdFx0XHRpZiAoc2xvdEF0dGFjaG1lbnQgPT0gc2tpbkF0dGFjaG1lbnQpIHtcblx0XHRcdFx0XHRcdGxldCBhdHRhY2htZW50ID0gdGhpcy5nZXRBdHRhY2htZW50KHNsb3RJbmRleCwga2V5KTtcblx0XHRcdFx0XHRcdGlmIChhdHRhY2htZW50KSBzbG90LnNldEF0dGFjaG1lbnQoYXR0YWNobWVudCk7XG5cdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0XHR9XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHRcdHNsb3RJbmRleCsrO1xuXHRcdH1cblx0fVxufVxuIl19