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
import { Bone } from "./Bone.js";
import { PhysicsConstraintData } from "./PhysicsConstraintData.js";
import { Physics, Skeleton } from "./Skeleton.js";
import { Updatable } from "./Updatable.js";
/** Stores the current pose for a physics constraint. A physics constraint applies physics to bones.
 * <p>
 * See <a href="http://esotericsoftware.com/spine-physics-constraints">Physics constraints</a> in the Spine User Guide. */
export declare class PhysicsConstraint implements Updatable {
    readonly data: PhysicsConstraintData;
    private _bone;
    /** The bone constrained by this physics constraint. */
    set bone(bone: Bone);
    get bone(): Bone;
    inertia: number;
    strength: number;
    damping: number;
    massInverse: number;
    wind: number;
    gravity: number;
    mix: number;
    _reset: boolean;
    ux: number;
    uy: number;
    cx: number;
    cy: number;
    tx: number;
    ty: number;
    xOffset: number;
    xVelocity: number;
    yOffset: number;
    yVelocity: number;
    rotateOffset: number;
    rotateVelocity: number;
    scaleOffset: number;
    scaleVelocity: number;
    active: boolean;
    readonly skeleton: Skeleton;
    remaining: number;
    lastTime: number;
    constructor(data: PhysicsConstraintData, skeleton: Skeleton);
    reset(): void;
    setToSetupPose(): void;
    isActive(): boolean;
    /** Applies the constraint to the constrained bones. */
    update(physics: Physics): void;
    /** Translates the physics constraint so next {@link #update(Physics)} forces are applied as if the bone moved an additional
     * amount in world space. */
    translate(x: number, y: number): void;
    /** Rotates the physics constraint so next {@link #update(Physics)} forces are applied as if the bone rotated around the
     * specified point in world space. */
    rotate(x: number, y: number, degrees: number): void;
}
