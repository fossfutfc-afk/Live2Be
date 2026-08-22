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
import { Batcher, DefaultBatchableMeshElement, DefaultBatchableQuadElement, ExtensionType, Shader } from 'pixi.js';
import { DarkTintBatchGeometry } from './DarkTintBatchGeometry.js';
/** The default batcher is used to batch quads and meshes. */
export declare class DarkTintBatcher extends Batcher {
    /** @ignore */
    static extension: {
        readonly type: readonly [ExtensionType.Batcher];
        readonly name: "darkTint";
    };
    geometry: DarkTintBatchGeometry;
    shader: Shader;
    name: "darkTint";
    /** The size of one attribute. 1 = 32 bit. x, y, u, v, color, darkColor, textureIdAndRound -> total = 7 */
    vertexSize: number;
    packAttributes(element: DefaultBatchableMeshElement & {
        darkColor: number;
    }, float32View: Float32Array, uint32View: Uint32Array, index: number, textureId: number): void;
    packQuadAttributes(element: DefaultBatchableQuadElement & {
        darkColor: number;
    }, float32View: Float32Array, uint32View: Uint32Array, index: number, textureId: number): void;
}
