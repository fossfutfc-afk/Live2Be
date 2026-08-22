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
import { AttachmentLoader } from "./attachments/AttachmentLoader.js";
import { BoundingBoxAttachment } from "./attachments/BoundingBoxAttachment.js";
import { ClippingAttachment } from "./attachments/ClippingAttachment.js";
import { MeshAttachment } from "./attachments/MeshAttachment.js";
import { PathAttachment } from "./attachments/PathAttachment.js";
import { PointAttachment } from "./attachments/PointAttachment.js";
import { RegionAttachment } from "./attachments/RegionAttachment.js";
import { Skin } from "./Skin.js";
import { TextureAtlas } from "./TextureAtlas.js";
import { Sequence } from "./attachments/Sequence.js";
/** An {@link AttachmentLoader} that configures attachments using texture regions from an {@link TextureAtlas}.
 *
 * See [Loading skeleton data](http://esotericsoftware.com/spine-loading-skeleton-data#JSON-and-binary-data) in the
 * Spine Runtimes Guide. */
export declare class AtlasAttachmentLoader implements AttachmentLoader {
    atlas: TextureAtlas;
    constructor(atlas: TextureAtlas);
    loadSequence(name: string, basePath: string, sequence: Sequence): void;
    newRegionAttachment(skin: Skin, name: string, path: string, sequence: Sequence): RegionAttachment;
    newMeshAttachment(skin: Skin, name: string, path: string, sequence: Sequence): MeshAttachment;
    newBoundingBoxAttachment(skin: Skin, name: string): BoundingBoxAttachment;
    newPathAttachment(skin: Skin, name: string): PathAttachment;
    newPointAttachment(skin: Skin, name: string): PointAttachment;
    newClippingAttachment(skin: Skin, name: string): ClippingAttachment;
}
