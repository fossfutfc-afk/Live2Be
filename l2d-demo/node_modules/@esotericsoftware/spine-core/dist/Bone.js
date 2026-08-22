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
import { Inherit } from "./BoneData.js";
import { MathUtils } from "./Utils.js";
/** Stores a bone's current pose.
 *
 * A bone has a local transform which is used to compute its world transform. A bone also has an applied transform, which is a
 * local transform that can be applied to compute the world transform. The local transform and applied transform may differ if a
 * constraint or application code modifies the world transform after it was computed from the local transform. */
export class Bone {
    /** The bone's setup pose data. */
    data;
    /** The skeleton this bone belongs to. */
    skeleton;
    /** The parent bone, or null if this is the root bone. */
    parent = null;
    /** The immediate children of this bone. */
    children = new Array();
    /** The local x translation. */
    x = 0;
    /** The local y translation. */
    y = 0;
    /** The local rotation in degrees, counter clockwise. */
    rotation = 0;
    /** The local scaleX. */
    scaleX = 0;
    /** The local scaleY. */
    scaleY = 0;
    /** The local shearX. */
    shearX = 0;
    /** The local shearY. */
    shearY = 0;
    /** The applied local x translation. */
    ax = 0;
    /** The applied local y translation. */
    ay = 0;
    /** The applied local rotation in degrees, counter clockwise. */
    arotation = 0;
    /** The applied local scaleX. */
    ascaleX = 0;
    /** The applied local scaleY. */
    ascaleY = 0;
    /** The applied local shearX. */
    ashearX = 0;
    /** The applied local shearY. */
    ashearY = 0;
    /** Part of the world transform matrix for the X axis. If changed, {@link #updateAppliedTransform()} should be called. */
    a = 0;
    /** Part of the world transform matrix for the Y axis. If changed, {@link #updateAppliedTransform()} should be called. */
    b = 0;
    /** Part of the world transform matrix for the X axis. If changed, {@link #updateAppliedTransform()} should be called. */
    c = 0;
    /** Part of the world transform matrix for the Y axis. If changed, {@link #updateAppliedTransform()} should be called. */
    d = 0;
    /** The world X position. If changed, {@link #updateAppliedTransform()} should be called. */
    worldY = 0;
    /** The world Y position. If changed, {@link #updateAppliedTransform()} should be called. */
    worldX = 0;
    inherit = Inherit.Normal;
    sorted = false;
    active = false;
    /** @param parent May be null. */
    constructor(data, skeleton, parent) {
        if (!data)
            throw new Error("data cannot be null.");
        if (!skeleton)
            throw new Error("skeleton cannot be null.");
        this.data = data;
        this.skeleton = skeleton;
        this.parent = parent;
        this.setToSetupPose();
    }
    /** Returns false when the bone has not been computed because {@link BoneData#skinRequired} is true and the
      * {@link Skeleton#skin active skin} does not {@link Skin#bones contain} this bone. */
    isActive() {
        return this.active;
    }
    /** Computes the world transform using the parent bone and this bone's local applied transform. */
    update(physics) {
        this.updateWorldTransformWith(this.ax, this.ay, this.arotation, this.ascaleX, this.ascaleY, this.ashearX, this.ashearY);
    }
    /** Computes the world transform using the parent bone and this bone's local transform.
     *
     * See {@link #updateWorldTransformWith()}. */
    updateWorldTransform() {
        this.updateWorldTransformWith(this.x, this.y, this.rotation, this.scaleX, this.scaleY, this.shearX, this.shearY);
    }
    /** Computes the world transform using the parent bone and the specified local transform. The applied transform is set to the
     * specified local transform. Child bones are not updated.
     *
     * See [World transforms](http://esotericsoftware.com/spine-runtime-skeletons#World-transforms) in the Spine
     * Runtimes Guide. */
    updateWorldTransformWith(x, y, rotation, scaleX, scaleY, shearX, shearY) {
        this.ax = x;
        this.ay = y;
        this.arotation = rotation;
        this.ascaleX = scaleX;
        this.ascaleY = scaleY;
        this.ashearX = shearX;
        this.ashearY = shearY;
        let parent = this.parent;
        if (!parent) { // Root bone.
            let skeleton = this.skeleton;
            const sx = skeleton.scaleX, sy = skeleton.scaleY;
            const rx = (rotation + shearX) * MathUtils.degRad;
            const ry = (rotation + 90 + shearY) * MathUtils.degRad;
            this.a = Math.cos(rx) * scaleX * sx;
            this.b = Math.cos(ry) * scaleY * sx;
            this.c = Math.sin(rx) * scaleX * sy;
            this.d = Math.sin(ry) * scaleY * sy;
            this.worldX = x * sx + skeleton.x;
            this.worldY = y * sy + skeleton.y;
            return;
        }
        let pa = parent.a, pb = parent.b, pc = parent.c, pd = parent.d;
        this.worldX = pa * x + pb * y + parent.worldX;
        this.worldY = pc * x + pd * y + parent.worldY;
        switch (this.inherit) {
            case Inherit.Normal: {
                const rx = (rotation + shearX) * MathUtils.degRad;
                const ry = (rotation + 90 + shearY) * MathUtils.degRad;
                const la = Math.cos(rx) * scaleX;
                const lb = Math.cos(ry) * scaleY;
                const lc = Math.sin(rx) * scaleX;
                const ld = Math.sin(ry) * scaleY;
                this.a = pa * la + pb * lc;
                this.b = pa * lb + pb * ld;
                this.c = pc * la + pd * lc;
                this.d = pc * lb + pd * ld;
                return;
            }
            case Inherit.OnlyTranslation: {
                const rx = (rotation + shearX) * MathUtils.degRad;
                const ry = (rotation + 90 + shearY) * MathUtils.degRad;
                this.a = Math.cos(rx) * scaleX;
                this.b = Math.cos(ry) * scaleY;
                this.c = Math.sin(rx) * scaleX;
                this.d = Math.sin(ry) * scaleY;
                break;
            }
            case Inherit.NoRotationOrReflection: {
                let sx = 1 / this.skeleton.scaleX, sy = 1 / this.skeleton.scaleY;
                pa *= sx;
                pc *= sy;
                let s = pa * pa + pc * pc;
                let prx = 0;
                if (s > 0.0001) {
                    s = Math.abs(pa * pd * sy - pb * sx * pc) / s;
                    pb = pc * s;
                    pd = pa * s;
                    prx = Math.atan2(pc, pa) * MathUtils.radDeg;
                }
                else {
                    pa = 0;
                    pc = 0;
                    prx = 90 - Math.atan2(pd, pb) * MathUtils.radDeg;
                }
                const rx = (rotation + shearX - prx) * MathUtils.degRad;
                const ry = (rotation + shearY - prx + 90) * MathUtils.degRad;
                const la = Math.cos(rx) * scaleX;
                const lb = Math.cos(ry) * scaleY;
                const lc = Math.sin(rx) * scaleX;
                const ld = Math.sin(ry) * scaleY;
                this.a = pa * la - pb * lc;
                this.b = pa * lb - pb * ld;
                this.c = pc * la + pd * lc;
                this.d = pc * lb + pd * ld;
                break;
            }
            case Inherit.NoScale:
            case Inherit.NoScaleOrReflection: {
                rotation *= MathUtils.degRad;
                const cos = Math.cos(rotation), sin = Math.sin(rotation);
                let za = (pa * cos + pb * sin) / this.skeleton.scaleX;
                let zc = (pc * cos + pd * sin) / this.skeleton.scaleY;
                let s = Math.sqrt(za * za + zc * zc);
                if (s > 0.00001)
                    s = 1 / s;
                za *= s;
                zc *= s;
                s = Math.sqrt(za * za + zc * zc);
                if (this.inherit == Inherit.NoScale
                    && (pa * pd - pb * pc < 0) != (this.skeleton.scaleX < 0 != this.skeleton.scaleY < 0))
                    s = -s;
                rotation = Math.PI / 2 + Math.atan2(zc, za);
                const zb = Math.cos(rotation) * s;
                const zd = Math.sin(rotation) * s;
                shearX *= MathUtils.degRad;
                shearY = (90 + shearY) * MathUtils.degRad;
                const la = Math.cos(shearX) * scaleX;
                const lb = Math.cos(shearY) * scaleY;
                const lc = Math.sin(shearX) * scaleX;
                const ld = Math.sin(shearY) * scaleY;
                this.a = za * la + zb * lc;
                this.b = za * lb + zb * ld;
                this.c = zc * la + zd * lc;
                this.d = zc * lb + zd * ld;
                break;
            }
        }
        this.a *= this.skeleton.scaleX;
        this.b *= this.skeleton.scaleX;
        this.c *= this.skeleton.scaleY;
        this.d *= this.skeleton.scaleY;
    }
    /** Sets this bone's local transform to the setup pose. */
    setToSetupPose() {
        let data = this.data;
        this.x = data.x;
        this.y = data.y;
        this.rotation = data.rotation;
        this.scaleX = data.scaleX;
        this.scaleY = data.scaleY;
        this.shearX = data.shearX;
        this.shearY = data.shearY;
        this.inherit = data.inherit;
    }
    /** Computes the applied transform values from the world transform.
     *
     * If the world transform is modified (by a constraint, {@link #rotateWorld(float)}, etc) then this method should be called so
     * the applied transform matches the world transform. The applied transform may be needed by other code (eg to apply other
     * constraints).
     *
     * Some information is ambiguous in the world transform, such as -1,-1 scale versus 180 rotation. The applied transform after
     * calling this method is equivalent to the local transform used to compute the world transform, but may not be identical. */
    updateAppliedTransform() {
        let parent = this.parent;
        if (!parent) {
            this.ax = this.worldX - this.skeleton.x;
            this.ay = this.worldY - this.skeleton.y;
            this.arotation = Math.atan2(this.c, this.a) * MathUtils.radDeg;
            this.ascaleX = Math.sqrt(this.a * this.a + this.c * this.c);
            this.ascaleY = Math.sqrt(this.b * this.b + this.d * this.d);
            this.ashearX = 0;
            this.ashearY = Math.atan2(this.a * this.b + this.c * this.d, this.a * this.d - this.b * this.c) * MathUtils.radDeg;
            return;
        }
        let pa = parent.a, pb = parent.b, pc = parent.c, pd = parent.d;
        let pid = 1 / (pa * pd - pb * pc);
        let ia = pd * pid, ib = pb * pid, ic = pc * pid, id = pa * pid;
        let dx = this.worldX - parent.worldX, dy = this.worldY - parent.worldY;
        this.ax = (dx * ia - dy * ib);
        this.ay = (dy * id - dx * ic);
        let ra, rb, rc, rd;
        if (this.inherit == Inherit.OnlyTranslation) {
            ra = this.a;
            rb = this.b;
            rc = this.c;
            rd = this.d;
        }
        else {
            switch (this.inherit) {
                case Inherit.NoRotationOrReflection: {
                    let s = Math.abs(pa * pd - pb * pc) / (pa * pa + pc * pc);
                    pb = -pc * this.skeleton.scaleX * s / this.skeleton.scaleY;
                    pd = pa * this.skeleton.scaleY * s / this.skeleton.scaleX;
                    pid = 1 / (pa * pd - pb * pc);
                    ia = pd * pid;
                    ib = pb * pid;
                    break;
                }
                case Inherit.NoScale:
                case Inherit.NoScaleOrReflection:
                    let cos = MathUtils.cosDeg(this.rotation), sin = MathUtils.sinDeg(this.rotation);
                    pa = (pa * cos + pb * sin) / this.skeleton.scaleX;
                    pc = (pc * cos + pd * sin) / this.skeleton.scaleY;
                    let s = Math.sqrt(pa * pa + pc * pc);
                    if (s > 0.00001)
                        s = 1 / s;
                    pa *= s;
                    pc *= s;
                    s = Math.sqrt(pa * pa + pc * pc);
                    if (this.inherit == Inherit.NoScale && pid < 0 != (this.skeleton.scaleX < 0 != this.skeleton.scaleY < 0))
                        s = -s;
                    let r = MathUtils.PI / 2 + Math.atan2(pc, pa);
                    pb = Math.cos(r) * s;
                    pd = Math.sin(r) * s;
                    pid = 1 / (pa * pd - pb * pc);
                    ia = pd * pid;
                    ib = pb * pid;
                    ic = pc * pid;
                    id = pa * pid;
            }
            ra = ia * this.a - ib * this.c;
            rb = ia * this.b - ib * this.d;
            rc = id * this.c - ic * this.a;
            rd = id * this.d - ic * this.b;
        }
        this.ashearX = 0;
        this.ascaleX = Math.sqrt(ra * ra + rc * rc);
        if (this.ascaleX > 0.0001) {
            let det = ra * rd - rb * rc;
            this.ascaleY = det / this.ascaleX;
            this.ashearY = -Math.atan2(ra * rb + rc * rd, det) * MathUtils.radDeg;
            this.arotation = Math.atan2(rc, ra) * MathUtils.radDeg;
        }
        else {
            this.ascaleX = 0;
            this.ascaleY = Math.sqrt(rb * rb + rd * rd);
            this.ashearY = 0;
            this.arotation = 90 - Math.atan2(rd, rb) * MathUtils.radDeg;
        }
    }
    /** The world rotation for the X axis, calculated using {@link #a} and {@link #c}. */
    getWorldRotationX() {
        return Math.atan2(this.c, this.a) * MathUtils.radDeg;
    }
    /** The world rotation for the Y axis, calculated using {@link #b} and {@link #d}. */
    getWorldRotationY() {
        return Math.atan2(this.d, this.b) * MathUtils.radDeg;
    }
    /** The magnitude (always positive) of the world scale X, calculated using {@link #a} and {@link #c}. */
    getWorldScaleX() {
        return Math.sqrt(this.a * this.a + this.c * this.c);
    }
    /** The magnitude (always positive) of the world scale Y, calculated using {@link #b} and {@link #d}. */
    getWorldScaleY() {
        return Math.sqrt(this.b * this.b + this.d * this.d);
    }
    /** Transforms a point from world coordinates to the bone's local coordinates. */
    worldToLocal(world) {
        let invDet = 1 / (this.a * this.d - this.b * this.c);
        let x = world.x - this.worldX, y = world.y - this.worldY;
        world.x = x * this.d * invDet - y * this.b * invDet;
        world.y = y * this.a * invDet - x * this.c * invDet;
        return world;
    }
    /** Transforms a point from the bone's local coordinates to world coordinates. */
    localToWorld(local) {
        let x = local.x, y = local.y;
        local.x = x * this.a + y * this.b + this.worldX;
        local.y = x * this.c + y * this.d + this.worldY;
        return local;
    }
    /** Transforms a point from world coordinates to the parent bone's local coordinates. */
    worldToParent(world) {
        if (world == null)
            throw new Error("world cannot be null.");
        return this.parent == null ? world : this.parent.worldToLocal(world);
    }
    /** Transforms a point from the parent bone's coordinates to world coordinates. */
    parentToWorld(world) {
        if (world == null)
            throw new Error("world cannot be null.");
        return this.parent == null ? world : this.parent.localToWorld(world);
    }
    /** Transforms a world rotation to a local rotation. */
    worldToLocalRotation(worldRotation) {
        let sin = MathUtils.sinDeg(worldRotation), cos = MathUtils.cosDeg(worldRotation);
        return Math.atan2(this.a * sin - this.c * cos, this.d * cos - this.b * sin) * MathUtils.radDeg + this.rotation - this.shearX;
    }
    /** Transforms a local rotation to a world rotation. */
    localToWorldRotation(localRotation) {
        localRotation -= this.rotation - this.shearX;
        let sin = MathUtils.sinDeg(localRotation), cos = MathUtils.cosDeg(localRotation);
        return Math.atan2(cos * this.c + sin * this.d, cos * this.a + sin * this.b) * MathUtils.radDeg;
    }
    /** Rotates the world transform the specified amount.
     * <p>
     * After changes are made to the world transform, {@link #updateAppliedTransform()} should be called and
     * {@link #update(Physics)} will need to be called on any child bones, recursively. */
    rotateWorld(degrees) {
        degrees *= MathUtils.degRad;
        const sin = Math.sin(degrees), cos = Math.cos(degrees);
        const ra = this.a, rb = this.b;
        this.a = cos * ra - sin * this.c;
        this.b = cos * rb - sin * this.d;
        this.c = sin * ra + cos * this.c;
        this.d = sin * rb + cos * this.d;
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiQm9uZS5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIi4uL3NyYy9Cb25lLnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiJBQUFBOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7K0VBMkIrRTtBQUUvRSxPQUFPLEVBQVksT0FBTyxFQUFFLE1BQU0sZUFBZSxDQUFDO0FBR2xELE9BQU8sRUFBRSxTQUFTLEVBQVcsTUFBTSxZQUFZLENBQUM7QUFFaEQ7Ozs7aUhBSWlIO0FBQ2pILE1BQU0sT0FBTyxJQUFJO0lBQ2hCLGtDQUFrQztJQUNsQyxJQUFJLENBQVc7SUFFZix5Q0FBeUM7SUFDekMsUUFBUSxDQUFXO0lBRW5CLHlEQUF5RDtJQUN6RCxNQUFNLEdBQWdCLElBQUksQ0FBQztJQUUzQiwyQ0FBMkM7SUFDM0MsUUFBUSxHQUFHLElBQUksS0FBSyxFQUFRLENBQUM7SUFFN0IsK0JBQStCO0lBQy9CLENBQUMsR0FBRyxDQUFDLENBQUM7SUFFTiwrQkFBK0I7SUFDL0IsQ0FBQyxHQUFHLENBQUMsQ0FBQztJQUVOLHdEQUF3RDtJQUN4RCxRQUFRLEdBQUcsQ0FBQyxDQUFDO0lBRWIsd0JBQXdCO0lBQ3hCLE1BQU0sR0FBRyxDQUFDLENBQUM7SUFFWCx3QkFBd0I7SUFDeEIsTUFBTSxHQUFHLENBQUMsQ0FBQztJQUVYLHdCQUF3QjtJQUN4QixNQUFNLEdBQUcsQ0FBQyxDQUFDO0lBRVgsd0JBQXdCO0lBQ3hCLE1BQU0sR0FBRyxDQUFDLENBQUM7SUFFWCx1Q0FBdUM7SUFDdkMsRUFBRSxHQUFHLENBQUMsQ0FBQztJQUVQLHVDQUF1QztJQUN2QyxFQUFFLEdBQUcsQ0FBQyxDQUFDO0lBRVAsZ0VBQWdFO0lBQ2hFLFNBQVMsR0FBRyxDQUFDLENBQUM7SUFFZCxnQ0FBZ0M7SUFDaEMsT0FBTyxHQUFHLENBQUMsQ0FBQztJQUVaLGdDQUFnQztJQUNoQyxPQUFPLEdBQUcsQ0FBQyxDQUFDO0lBRVosZ0NBQWdDO0lBQ2hDLE9BQU8sR0FBRyxDQUFDLENBQUM7SUFF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RyxDQUFDLFFBQVEsR0FBRyxFQUFFLEdBQUcsTUFBTSxDQUFDLEdBQUcsU0FBUyxDQUFDLE1BQU0sQ0FBQztZQUN2RCxJQUFJLENBQUMsQ0FBQyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsTUFBTSxHQUFHLEVBQUUsQ0FBQztZQUNwQyxJQUFJLENBQUMsQ0FBQyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsTUFBTSxHQUFHLEVBQUUsQ0FBQztZQUNwQyxJQUFJLENBQUMsQ0FBQyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsTUFBTSxHQUFHLEVBQUUsQ0FBQztZQUNwQyxJQUFJLENBQUMsQ0FBQyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsTUFBTSxHQUFHLEVBQUUsQ0FBQztZQUNwQyxJQUFJLENBQUMsTUFBTSxHQUFHLENBQUMsR0FBRyxFQUFFLEdBQUcsUUFBUSxDQUFDLENBQUMsQ0FBQztZQUNsQyxJQUFJLENBQUMsTUFBTSxHQUFHLENBQUMsR0FBRyxFQUFFLEdBQUcsUUFBUSxDQUFDLENBQUMsQ0FBQztZQUNsQyxPQUFPO1FBQ1IsQ0FBQztRQUVELElBQUksRUFBRSxHQUFHLE1BQU0sQ0FBQyxDQUFDLEVBQUUsRUFBRSxHQUFHLE1BQU0sQ0FBQyxDQUFDLEVBQUUsRUFBRSxHQUFHLE1BQU0sQ0FBQyxDQUFDLEVBQUUsRUFBRSxHQUFHLE1BQU0sQ0FBQyxDQUFDLENBQUM7UUFDL0QsSUFBSSxDQUFDLE1BQU0sR0FBRyxFQUFFLEdBQUcsQ0FBQyxHQUFHLEVBQUUsR0FBRyxDQUFDLEdBQUcsTUFBTSxDQUFDLE1BQU0sQ0FBQztRQUM5QyxJQUFJLENBQUMsTUFBTSxHQUFHLEVBQUUsR0FBRyxDQUFDLEdBQUcsRUFBRSxHQUFHLENBQUMsR0FBRyxNQUFNLENBQUMsTUFBTSxDQUFDO1FBRTlDLFFBQVEsSUFBSSxDQUFDLE9BQU8sRUFBRSxDQUFDO1lBQ3RCLEtBQUssT0FBTyxDQUFDLE1B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QUFJLElBQUksQ0FBQyxRQUFRLENBQUMsTUFBTSxHQUFHLENBQUMsQ0FBQztvQkFBRSxDQUFDLEdBQUcsQ0FBQyxDQUFDLENBQUM7Z0JBQzlGLFFBQVEsR0FBRyxJQUFJLENBQUMsRUFBRSxHQUFHLENBQUMsR0FBRyxJQUFJLENBQUMsS0FBSyxDQUFDLEVBQUUsRUFBRSxFQUFFLENBQUMsQ0FBQztnQkFDNUMsTUFBTSxFQUFFLEdBQUcsSUFBSSxDQUFDLEdBQUcsQ0FBQyxRQUFRLENBQUMsR0FBRyxDQUFDLENBQUM7Z0JBQ2xDLE1BQU0sRUFBRSxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsUUFBUSxDQUFDLEdBQUcsQ0FBQyxDQUFDO2dCQUNsQyxNQUFNLElBQUksU0FBUyxDQUFDLE1BQU0sQ0FBQztnQkFDM0IsTUFBTSxHQUFHLENBQUMsRUFBRSxHQUFHLE1BQU0sQ0FBQyxHQUFHLFNBQVMsQ0FBQyxNQUFNLENBQUM7Z0JBQzFDLE1BQU0sRUFBRSxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsTUFBTSxDQUFDLEdBQUcsTUFBTSxDQUFDO2dCQUNyQyxNQUFNLEVBQUUsR0FBRyxJQUFJLENBQUMsR0FBRyxDQUFDLE1BQU0sQ0FBQyxHQUFHLE1BQU0sQ0FBQztnQkFDckMsTUFBTSxFQUFFLEdBQUcsSUFBSSxDQUFDLEdBQUcsQ0FBQyxNQUFNLENBQUMsR0FBRyxNQUFNLENBQUM7Z0JBQ3JDLE1BQU0sRUFBRSxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsTUFBTSxDQUFDLEdBQUcsTUFBTSxDQUFDO2dCQUNyQyxJQUFJLENBQUMsQ0FBQyxHQUFHLEVBQUUsR0FBRyxFQUFFLEdBQUcsRUFBRSxHQUFHLEVBQUUsQ0FBQztnQkFDM0IsSUFBSSxDQUFDLENBQUMsR0FBRyxFQUFFLEdBQUcsRUFBRSxHQUFHLEVBQUUsR0FBRyxFQUFFLENBQUM7Z0JBQzNCLElBQUksQ0FBQyxDQUFDLEdBQUcsRUFBRSxHQUFHLEVBQUUsR0FBRyxFQUFFLEdBQUcsRUFBRSxDQUFDO2dCQUMzQixJQUFJLENBQUMsQ0FBQyxHQUFH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RyxHQUFHLEdBQUcsSUFBSSxDQUFDLENBQUMsQ0FBQyxHQUFHLFNBQVMsQ0FBQyxNQUFNLENBQUM7SUFDaEcsQ0FBQztJQUVEOzs7MEZBR3NGO0lBQ3RGLFdBQVcsQ0FBRSxPQUFlO1FBQzNCLE9BQU8sSUFBSSxTQUFTLENBQUMsTUFBTSxDQUFDO1FBQzVCLE1BQU0sR0FBRyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsT0FBTyxDQUFDLEVBQUUsR0FBRyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsT0FBTyxDQUFDLENBQUM7UUFDdkQsTUFBTSxFQUFFLEdBQUcsSUFBSSxDQUFDLENBQUMsRUFBRSxFQUFFLEdBQUcsSUFBSSxDQUFDLENBQUMsQ0FBQztRQUMvQixJQUFJLENBQUMsQ0FBQyxHQUFHLEdBQUcsR0FBRyxFQUFFLEdBQUcsR0FBRyxHQUFHLElBQUksQ0FBQyxDQUFDLENBQUM7UUFDakMsSUFBSSxDQUFDLENBQUMsR0FBRyxHQUFHLEdBQUcsRUFBRSxHQUFHLEdBQUcsR0FBRyxJQUFJLENBQUMsQ0FBQyxDQUFDO1FBQ2pDLElBQUksQ0FBQyxDQUFDLEdBQUcsR0FBRyxHQUFHLEVBQUUsR0FBRyxHQUFHLEdBQUcsSUFBSSxDQUFDLENBQUMsQ0FBQztRQUNqQyxJQUFJLENBQUMsQ0FBQyxHQUFHLEdBQUcsR0FBRyxFQUFFLEdBQUcsR0FBRyxHQUFHLElBQUksQ0FBQyxDQUFDLENBQUM7SUFDbEMsQ0FBQztDQUNEIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBBcHJpbCA1LCAyMDI1LiBSZXBsYWNlcyBhbGwgcHJpb3IgdmVyc2lvbnMuXG4gKlxuICogQ29weXJpZ2h0IChjKSAyMDEzLTIwMjUsIEVzb3RlcmljIFNvZnR3YXJlIExMQ1xuICpcbiAqIEludGVncmF0aW9uIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlIG9yIG90aGVyd2lzZSBjcmVhdGluZ1xuICogZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgaXMgcGVybWl0dGVkIHVuZGVyIHRoZSB0ZXJtcyBhbmRcbiAqIGNvbmRpdGlvbnMgb2YgU2VjdGlvbiAyIG9mIHRoZSBTcGluZSBFZGl0b3IgTGljZW5zZSBBZ3JlZW1lbnQ6XG4gKiBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtZWRpdG9yLWxpY2Vuc2VcbiAqXG4gKiBPdGhlcndpc2UsIGl0IGlzIHBlcm1pdHRlZCB0byBpbnRlZ3JhdGUgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmVcbiAqIG9yIG90aGVyd2lzZSBjcmVhdGUgZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgKGNvbGxlY3RpdmVseSxcbiAqIFwiUHJvZHVjdHNcIiksIHByb3ZpZGVkIHRoYXQgZWFjaCB1c2VyIG9mIHRoZSBQcm9kdWN0cyBtdXN0IG9idGFpbiB0aGVpciBvd25cbiAqIFNwaW5lIEVkaXRvciBsaWNlbnNlIGFuZCByZWRpc3RyaWJ1dGlvbiBvZiB0aGUgUHJvZHVjdHMgaW4gYW55IGZvcm0gbXVzdFxuICogaW5jbHVkZSB0aGlzIGxpY2Vuc2UgYW5kIGNvcHlyaWdodCBub3RpY2UuXG4gKlxuICogVEhFIFNQSU5FIFJVTlRJTUVTIEFSRSBQUk9WSURFRCBCWSBFU09URVJJQyBTT0ZUV0FSRSBMTEMgXCJBUyBJU1wiIEFORCBBTllcbiAqIEVYUFJFU1MgT1IgSU1QTElFRCBXQVJSQU5USUVTLCBJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgVEhFIElNUExJRURcbiAqIFdBUlJBTlRJRVMgT0YgTUVSQ0hBTlRBQklMSVRZIEFORCBGSVRORVNTIEZPUiBBIFBBUlRJQ1VMQVIgUFVSUE9TRSBBUkVcbiAqIERJU0NMQUlNRUQuIElOIE5PIEVWRU5UIFNIQUxMIEVTT1RFUklDIFNPRlRXQVJFIExMQyBCRSBMSUFCTEUgRk9SIEFOWVxuICogRElSRUNULCBJTkRJUkVDVCwgSU5DSURFTlRBTCwgU1BFQ0lBTCwgRVhFTVBMQVJZLCBPUiBDT05TRVFVRU5USUFMIERBTUFHRVNcbiAqIChJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgUFJPQ1VSRU1FTlQgT0YgU1VCU1RJVFVURSBHT09EUyBPUiBTRVJWSUNFUyxcbiAqIEJVU0lORVNTIElOVEVSUlVQVElPTiwgT1IgTE9TUyBPRiBVU0UsIERBVEEsIE9SIFBST0ZJVFMpIEhPV0VWRVIgQ0FVU0VEIEFORFxuICogT04gQU5ZIFRIRU9SWSBPRiBMSUFCSUxJVFksIFdIRVRIRVIgSU4gQ09OVFJBQ1QsIFNUUklDVCBMSUFCSUxJVFksIE9SIFRPUlRcbiAqIChJTkNMVURJTkcgTkVHTElHRU5DRSBPUiBPVEhFUldJU0UpIEFSSVNJTkcgSU4gQU5ZIFdBWSBPVVQgT0YgVEhFIFVTRSBPRlxuICogVEhFIFNQSU5FIFJVTlRJTUVTLCBFVkVOIElGIEFEVklTRUQgT0YgVEhFIFBPU1NJQklMSVRZIE9GIFNVQ0ggREFNQUdFLlxuICoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqL1xuXG5pbXBvcnQgeyBCb25lRGF0YSwgSW5oZXJpdCB9IGZyb20gXCIuL0JvbmVEYXRhLmpzXCI7XG5pbXBvcnQgeyBQaHlzaWNzLCBTa2VsZXRvbiB9IGZyb20gXCIuL1NrZWxldG9uLmpzXCI7XG5pbXBvcnQgeyBVcGRhdGFibGUgfSBmcm9tIFwiLi9VcGRhdGFibGUuanNcIjtcbmltcG9ydCB7IE1hdGhVdGlscywgVmVjdG9yMiB9IGZyb20gXCIuL1V0aWxzLmpzXCI7XG5cbi8qKiBTdG9yZXMgYSBib25lJ3MgY3VycmVudCBwb3NlLlxuICpcbiAqIEEgYm9uZSBoYXMgYSBsb2NhbCB0cmFuc2Zvcm0gd2hpY2ggaXMgdXNlZCB0byBjb21wdXRlIGl0cyB3b3JsZCB0cmFuc2Zvcm0uIEEgYm9uZSBhbHNvIGhhcyBhbiBhcHBsaWVkIHRyYW5zZm9ybSwgd2hpY2ggaXMgYVxuICogbG9jYWwgdHJhbnNmb3JtIHRoYXQgY2FuIGJlIGFwcGxpZWQgdG8gY29tcHV0ZSB0aGUgd29ybGQgdHJhbnNmb3JtLiBUaGUgbG9jYWwgdHJhbnNmb3JtIGFuZCBhcHBsaWVkIHRyYW5zZm9ybSBtYXkgZGlmZmVyIGlmIGFcbiAqIGNvbnN0cmFpbnQgb3IgYXBwbGljYXRpb24gY29kZSBtb2RpZmllcyB0aGUgd29ybGQgdHJhbnNmb3JtIGFmdGVyIGl0IHdhcyBjb21wdXRlZCBmcm9tIHRoZSBsb2NhbCB0cmFuc2Zvcm0uICovXG5leHBvcnQgY2xhc3MgQm9uZSBpbXBsZW1lbnRzIFVwZGF0YWJsZSB7XG5cdC8qKiBUaGUgYm9uZSdzIHNldHVwIHBvc2UgZGF0YS4gKi9cblx0ZGF0YTogQm9uZURhdGE7XG5cblx0LyoqIFRoZSBza2VsZXRvbiB0aGlzIGJvbmUgYmVsb25ncyB0by4gKi9cblx0c2tlbGV0b246IFNrZWxldG9uO1xuXG5cdC8qKiBUaGUgcGFyZW50IGJvbmUsIG9yIG51bGwgaWYgdGhpcyBpcyB0aGUgcm9vdCBib25lLiAqL1xuXHRwYXJlbnQ6IEJvbmUgfCBudWxsID0gbnVsbDtcblxuXHQvKiogVGhlIGltbWVkaWF0ZSBjaGlsZHJlbiBvZiB0aGlzIGJvbmUuICovXG5cdGNoaWxkcmVuID0gbmV3IEFycmF5PEJvbmU+KCk7XG5cblx0LyoqIFRoZSBsb2NhbCB4IHRyYW5zbGF0aW9uLiAqL1xuXHR4ID0gMDtcblxuXHQvKiogVGhlIGxvY2FsIHkgdHJhbnNsYXRpb24uICovXG5cdHkgPSAwO1xuXG5cdC8qKiBUaGUgbG9jYWwgcm90YXRpb24gaW4gZGVncmVlcywgY291bnRlciBjbG9ja3dpc2UuICovXG5cdHJvdGF0aW9uID0gMDtcblxuXHQvKiogVGhlIGxvY2FsIHNjYWxlWC4gKi9cblx0c2NhbGVYID0gMDtcblxuXHQvKiogVGhlIGxvY2FsIHNjYWxlWS4gKi9cblx0c2NhbGVZID0gMDtcblxuXHQvKiogVGhlIGxvY2FsIHNoZWFyWC4gKi9cblx0c2hlYXJYID0gMDtcblxuXHQvKiogVGhlIGxvY2FsIHNoZWFyWS4gKi9cblx0c2hlYXJZID0gMDtcblxuXHQvKiogVGhlIGFwcGxpZWQgbG9jYWwgeCB0cmFuc2xhdGlvbi4gKi9cblx0YXggPSAwO1xuXG5cdC8qKiBUaGUgYXBwbGllZCBsb2NhbCB5IHRyYW5zbGF0aW9uLiAqL1xuXHRheSA9IDA7XG5cblx0LyoqIFRoZSBhcHBsaWVkIGxvY2FsIHJvdGF0aW9uIGluIGRlZ3JlZXMsIGNvdW50ZXIgY2xvY2t3aXNlLiAqL1xuXHRhcm90YXRpb24gPSAwO1xuXG5cdC8qKiBUaGUgYXBwbGllZCBsb2NhbCBzY2FsZVguICovXG5cdGFzY2FsZVggPSAwO1xuXG5cdC8qKiBUaGUgYXBwbGllZCBsb2NhbCBzY2FsZVkuICovXG5cdGFzY2FsZVkgPSAwO1xuXG5cdC8qKiBUaGUgYXBwbGllZCBsb2NhbCBzaGVhclguICovXG5cdGFzaGVhclggPSAwO1xuXG5cdC8qKiBUaGUgYXBwbGllZCBsb2NhbCBzaGVhclkuICovXG5cdGFzaGVhclkgPSAwO1xuXG5cdC8qKiBQYXJ0IG9mIHRoZSB3b3JsZCB0cmFuc2Zvcm0gbWF0cml4IGZvciB0aGUgWCBheGlzLiBJZiBjaGFuZ2VkLCB7QGxpbmsgI3VwZGF0ZUFwcGxpZWRUcmFuc2Zvcm0oKX0gc2hvdWxkIGJlIGNhbGxlZC4gKi9cblx0YSA9IDA7XG5cblx0LyoqIFBhcnQgb2YgdGhlIHdvcmxkIHRyYW5zZm9ybSBtYXRyaXggZm9yIHRoZSBZIGF4aXMuIElmIGNoYW5nZWQsIHtAbGluayAjdXBkYXRlQXBwbGllZFRyYW5zZm9ybSgpfSBzaG91bGQgYmUgY2FsbGVkLiAqL1xuXHRiID0gMDtcblxuXHQvKiogUGFydCBvZiB0aGUgd29ybGQgdHJhbnNmb3JtIG1hdHJpeCBmb3IgdGhlIFggYXhpcy4gSWYgY2hhbmdlZCwge0BsaW5rICN1cGRhdGVBcHBsaWVkVHJhbnNmb3JtKCl9IHNob3VsZCBiZSBjYWxsZWQuICovXG5cdGMgPSAwO1xuXG5cdC8qKiBQYXJ0IG9mIHRoZSB3b3JsZCB0cmFuc2Zvcm0gbWF0cml4IGZvciB0aGUgWSBheGlzLiBJZiBjaGFuZ2VkLCB7QGxpbmsgI3VwZGF0ZUFwcGxpZWRUcmFuc2Zvcm0oKX0gc2hvdWxkIGJlIGNhbGxlZC4gKi9cblx0ZCA9IDA7XG5cblx0LyoqIFRoZSB3b3JsZCBYIHBvc2l0aW9uLiBJZiBjaGFuZ2VkLCB7QGxpbmsgI3VwZGF0ZUFwcGxpZWRUcmFuc2Zvcm0oKX0gc2hvdWxkIGJlIGNhbGxlZC4gKi9cblx0d29ybGRZID0gMDtcblxuXHQvKiogVGhlIHdvcmxkIFkgcG9zaXRpb24uIElmIGNoYW5nZWQsIHtAbGluayAjdXBkYXRlQXBwbGllZFRyYW5zZm9ybSgpfSBzaG91bGQgYmUgY2FsbGVkLiAqL1xuXHR3b3JsZFggPSAwO1xuXG5cdGluaGVyaXQ6IEluaGVyaXQgPSBJbmhlcml0Lk5vcm1hbDtcblxuXHRzb3J0ZWQgPSBmYWxzZTtcblx0YWN0aXZlID0gZmFsc2U7XG5cblx0LyoqIEBwYXJhbSBwYXJlbnQgTWF5IGJlIG51bGwuICovXG5cdGNvbnN0cnVjdG9yIChkYXRhOiBCb25lRGF0YSwgc2tlbGV0b246IFNrZWxldG9uLCBwYXJlbnQ6IEJvbmUgfCBudWxsKSB7XG5cdFx0aWYgKCFkYXRhKSB0aHJvdyBuZXcgRXJyb3IoXCJkYXRhIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRpZiAoIXNrZWxldG9uKSB0aHJvdyBuZXcgRXJyb3IoXCJza2VsZXRvbiBjYW5ub3QgYmUgbnVsbC5cIik7XG5cdFx0dGhpcy5kYXRhID0gZGF0YTtcblx0XHR0aGlzLnNrZWxldG9uID0gc2tlbGV0b247XG5cdFx0dGhpcy5wYXJlbnQgPSBwYXJlbnQ7XG5cdFx0dGhpcy5zZXRUb1NldHVwUG9zZSgpO1xuXHR9XG5cblx0LyoqIFJldHVybnMgZmFsc2Ugd2hlbiB0aGUgYm9uZSBoYXMgbm90IGJlZW4gY29tcHV0ZWQgYmVjYXVzZSB7QGxpbmsgQm9uZURhdGEjc2tpblJlcXVpcmVkfSBpcyB0cnVlIGFuZCB0aGVcblx0ICAqIHtAbGluayBTa2VsZXRvbiNza2luIGFjdGl2ZSBza2lufSBkb2VzIG5vdCB7QGxpbmsgU2tpbiNib25lcyBjb250YWlufSB0aGlzIGJvbmUuICovXG5cdGlzQWN0aXZlICgpIHtcblx0XHRyZXR1cm4gdGhpcy5hY3RpdmU7XG5cdH1cblxuXHQvKiogQ29tcHV0ZXMgdGhlIHdvcmxkIHRyYW5zZm9ybSB1c2luZyB0aGUgcGFyZW50IGJvbmUgYW5kIHRoaXMgYm9uZSdzIGxvY2FsIGFwcGxpZWQgdHJhbnNmb3JtLiAqL1xuXHR1cGRhdGUgKHBoeXNpY3M6IFBoeXNpY3MpIHtcblx0XHR0aGlzLnVwZGF0ZVdvcmxkVHJhbnNmb3JtV2l0aCh0aGlzLmF4LCB0aGlzLmF5LCB0aGlzLmFyb3RhdGlvbiwgdGhpcy5hc2NhbGVYLCB0aGlzLmFzY2FsZVksIHRoaXMuYXNoZWFyWCwgdGhpcy5hc2hlYXJZKTtcblx0fVxuXG5cdC8qKiBDb21wdXRlcyB0aGUgd29ybGQgdHJhbnNmb3JtIHVzaW5nIHRoZSBwYXJlbnQgYm9uZSBhbmQgdGhpcyBib25lJ3MgbG9jYWwgdHJhbnNmb3JtLlxuXHQgKlxuXHQgKiBTZWUge0BsaW5rICN1cGRhdGVXb3JsZFRyYW5zZm9ybVdpdGgoKX0uICovXG5cdHVwZGF0ZVdvcmxkVHJhbnNmb3JtICgpIHtcblx0XHR0aGlzLnVwZGF0ZVdvcmxkVHJhbnNmb3JtV2l0aCh0aGlzLngsIHRoaXMueSwgdGhpcy5yb3RhdGlvbiwgdGhpcy5zY2FsZVgsIHRoaXMuc2NhbGVZLCB0aGlzLnNoZWFyWCwgdGhpcy5zaGVhclkpO1xuXHR9XG5cblx0LyoqIENvbXB1dGVzIHRoZSB3b3JsZCB0cmFuc2Zvcm0gdXNpbmcgdGhlIHBhcmVudCBib25lIGFuZCB0aGUgc3BlY2lmaWVkIGxvY2FsIHRyYW5zZm9ybS4gVGhlIGFwcGxpZWQgdHJhbnNmb3JtIGlzIHNldCB0byB0aGVcblx0ICogc3BlY2lmaWVkIGxvY2FsIHRyYW5zZm9ybS4gQ2hpbGQgYm9uZXMgYXJlIG5vdCB1cGRhdGVkLlxuXHQgKlxuXHQgKiBTZWUgW1dvcmxkIHRyYW5zZm9ybXNdKGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1ydW50aW1lLXNrZWxldG9ucyNXb3JsZC10cmFuc2Zvcm1zKSBpbiB0aGUgU3BpbmVcblx0ICogUnVudGltZXMgR3VpZGUuICovXG5cdHVwZGF0ZVdvcmxkVHJhbnNmb3JtV2l0aCAoeDogbnVtYmVyLCB5OiBudW1iZXIsIHJvdGF0aW9uOiBudW1iZXIsIHNjYWxlWDogbnVtYmVyLCBzY2FsZVk6IG51bWJlciwgc2hlYXJYOiBudW1iZXIsIHNoZWFyWTogbnVtYmVyKSB7XG5cdFx0dGhpcy5heCA9IHg7XG5cdFx0dGhpcy5heSA9IHk7XG5cdFx0dGhpcy5hcm90YXRpb24gPSByb3RhdGlvbjtcblx0XHR0aGlzLmFzY2FsZVggPSBzY2FsZVg7XG5cdFx0dGhpcy5hc2NhbGVZID0gc2NhbGVZO1xuXHRcdHRoaXMuYXNoZWFyWCA9IHNoZWFyWDtcblx0XHR0aGlzLmFzaGVhclkgPSBzaGVhclk7XG5cblx0XHRsZXQgcGFyZW50ID0gdGhpcy5wYXJlbnQ7XG5cdFx0aWYgKCFwYXJlbnQpIHsgLy8gUm9vdCBib25lLlxuXHRcdFx0bGV0IHNrZWxldG9uID0gdGhpcy5za2VsZXRvbjtcblx0XHRcdGNvbnN0IHN4ID0gc2tlbGV0b24uc2NhbGVYLCBzeSA9IHNrZWxldG9uLnNjYWxlWTtcblx0XHRcdGNvbnN0IHJ4ID0gKHJvdGF0aW9uICsgc2hlYXJYKSAqIE1hdGhVdGlscy5kZWdSYWQ7XG5cdFx0XHRjb25zdCByeSA9IChyb3RhdGlvbiArIDkwICsgc2hlYXJZKSAqIE1hdGhVdGlscy5kZWdSYWQ7XG5cdFx0XHR0aGlzLmEgPSBNYXRoLmNvcyhyeCkgKiBzY2FsZVggKiBzeDtcblx0XHRcdHRoaXMuYiA9IE1hdGguY29zKHJ5KSAqIHNjYWxlWSAqIHN4O1xuXHRcdFx0dGhpcy5jID0gTWF0aC5zaW4ocngpICogc2NhbGVYICogc3k7XG5cdFx0XHR0aGlzLmQgPSBNYXRoLnNpbihyeSkgKiBzY2FsZVkgKiBzeTtcblx0XHRcdHRoaXMud29ybGRYID0geCAqIHN4ICsgc2tlbGV0b24ueDtcblx0XHRcdHRoaXMud29ybGRZID0geSAqIHN5ICsgc2tlbGV0b24ueTtcblx0XHRcdHJldHVybjtcblx0XHR9XG5cblx0XHRsZXQgcGEgPSBwYXJlbnQuYSwgcGIgPSBwYXJlbnQuYiwgcGMgPSBwYXJlbnQuYywgcGQgPSBwYXJlbnQuZDtcblx0XHR0aGlzLndvcmxkWCA9IHBhICogeCArIHBiICogeSArIHBhcmVudC53b3JsZFg7XG5cdFx0dGhpcy53b3JsZFkgPSBwYyAqIHggKyBwZCAqIHkgKyBwYXJlbnQud29ybGRZO1xuXG5cdFx0c3dpdGNoICh0aGlzLmluaGVyaXQpIHtcblx0XHRcdGNhc2UgSW5oZXJpdC5Ob3JtYWw6IHtcblx0XHRcdFx0Y29uc3QgcnggPSAocm90YXRpb24gKyBzaGVhclgpICogTWF0aFV0aWxzLmRlZ1JhZDtcblx0XHRcdFx0Y29uc3QgcnkgPSAocm90YXRpb24gKyA5MCArIHNoZWFyWSkgKiBNYXRoVXRpbHMuZGVnUmFkO1xuXHRcdFx0XHRjb25zdCBsYSA9IE1hdGguY29zKHJ4KSAqIHNjYWxlWDtcblx0XHRcdFx0Y29uc3QgbGIgPSBNYXRoLmNvcyhyeSkgKiBzY2FsZVk7XG5cdFx0XHRcdGNvbnN0IGxjID0gTWF0aC5zaW4ocngpICogc2NhbGVYO1xuXHRcdFx0XHRjb25zdCBsZCA9IE1hdGguc2luKHJ5KSAqIHNjYWxlWTtcblx0XHRcdFx0dGhpcy5hID0gcGEgKiBsYSArIHBiICogbGM7XG5cdFx0XHRcdHRoaXMuYiA9IHBhICogbGIgKyBwYiAqIGxkO1xuXHRcdFx0XHR0aGlzLmMgPSBwYyAqIGxhICsgcGQgKiBsYztcblx0XHRcdFx0dGhpcy5kID0gcGMgKiBsYiArIHBkICogbGQ7XG5cdFx0XHRcdHJldHVybjtcblx0XHRcdH1cblx0XHRcdGNhc2UgSW5oZXJpdC5Pbmx5VHJhbnNsYXRpb246IHtcblx0XHRcdFx0Y29uc3QgcnggPSAocm90YXRpb24gKyBzaGVhclgpICogTWF0aFV0aWxzLmRlZ1JhZDtcblx0XHRcdFx0Y29uc3QgcnkgPSAocm90YXRpb24gKyA5MCArIHNoZWFyWSkgKiBNYXRoVXRpbHMuZGVnUmFkO1xuXHRcdFx0XHR0aGlzLmEgPSBNYXRoLmNvcyhyeCkgKiBzY2FsZVg7XG5cdFx0XHRcdHRoaXMuYiA9IE1hdGguY29zKHJ5KSAqIHNjYWxlWTtcblx0XHRcdFx0dGhpcy5jID0gTWF0aC5zaW4ocngpICogc2NhbGVYO1xuXHRcdFx0XHR0aGlzLmQgPSBNYXRoLnNpbihyeSkgKiBzY2FsZVk7XG5cdFx0XHRcdGJyZWFrO1xuXHRcdFx0fVxuXHRcdFx0Y2FzZSBJbmhlcml0Lk5vUm90YXRpb25PclJlZmxlY3Rpb246IHtcblx0XHRcdFx0bGV0IHN4ID0gMSAvIHRoaXMuc2tlbGV0b24uc2NhbGVYLCBzeSA9IDEgLyB0aGlzLnNrZWxldG9uLnNjYWxlWTtcblx0XHRcdFx0cGEgKj0gc3g7XG5cdFx0XHRcdHBjICo9IHN5O1xuXHRcdFx0XHRsZXQgcyA9IHBhICogcGEgKyBwYyAqIHBjO1xuXHRcdFx0XHRsZXQgcHJ4ID0gMDtcblx0XHRcdFx0aWYgKHMgPiAwLjAwMDEpIHtcblx0XHRcdFx0XHRzID0gTWF0aC5hYnMocGEgKiBwZCAqIHN5IC0gcGIgKiBzeCAqIHBjKSAvIHM7XG5cdFx0XHRcdFx0cGIgPSBwYyAqIHM7XG5cdFx0XHRcdFx0cGQgPSBwYSAqIHM7XG5cdFx0XHRcdFx0cHJ4ID0gTWF0aC5hdGFuMihwYywgcGEpICogTWF0aFV0aWxzLnJhZERlZztcblx0XHRcdFx0fSBlbHNlIHtcblx0XHRcdFx0XHRwYSA9IDA7XG5cdFx0XHRcdFx0cGMgPSAwO1xuXHRcdFx0XHRcdHByeCA9IDkwIC0gTWF0aC5hdGFuMihwZCwgcGIpICogTWF0aFV0aWxzLnJhZERlZztcblx0XHRcdFx0fVxuXHRcdFx0XHRjb25zdCByeCA9IChyb3RhdGlvbiArIHNoZWFyWCAtIHByeCkgKiBNYXRoVXRpbHMuZGVnUmFkO1xuXHRcdFx0XHRjb25zdCByeSA9IChyb3RhdGlvbiArIHNoZWFyWSAtIHByeCArIDkwKSAqIE1hdGhVdGlscy5kZWdSYWQ7XG5cdFx0XHRcdGNvbnN0IGxhID0gTWF0aC5jb3MocngpICogc2NhbGVYO1xuXHRcdFx0XHRjb25zdCBsYiA9IE1hdGguY29zKHJ5KSAqIHNjYWxlWTtcblx0XHRcdFx0Y29uc3QgbGMgPSBNYXRoLnNpbihyeCkgKiBzY2FsZVg7XG5cdFx0XHRcdGNvbnN0IGxkID0gTWF0aC5zaW4ocnkpICogc2NhbGVZO1xuXHRcdFx0XHR0aGlzLmEgPSBwYSAqIGxhIC0gcGIgKiBsYztcblx0XHRcdFx0dGhpcy5iID0gcGEgKiBsYiAtIHBiICogbGQ7XG5cdFx0XHRcdHRoaXMuYyA9IHBjICogbGEgKyBwZCAqIGxjO1xuXHRcdFx0XHR0aGlzLmQgPSBwYyAqIGxiICsgcGQgKiBsZDtcblx0XHRcdFx0YnJlYWs7XG5cdFx0XHR9XG5cdFx0XHRjYXNlIEluaGVyaXQuTm9TY2FsZTpcblx0XHRcdGNhc2UgSW5oZXJpdC5Ob1NjYWxlT3JSZWZsZWN0aW9uOiB7XG5cdFx0XHRcdHJvdGF0aW9uICo9IE1hdGhVdGlscy5kZWdSYWQ7XG5cdFx0XHRcdGNvbnN0IGNvcyA9IE1hdGguY29zKHJvdGF0aW9uKSwgc2luID0gTWF0aC5zaW4ocm90YXRpb24pO1xuXHRcdFx0XHRsZXQgemEgPSAocGEgKiBjb3MgKyBwYiAqIHNpbikgLyB0aGlzLnNrZWxldG9uLnNjYWxlWDtcblx0XHRcdFx0bGV0IHpjID0gKHBjICogY29zICsgcGQgKiBzaW4pIC8gdGhpcy5za2VsZXRvbi5zY2FsZVk7XG5cdFx0XHRcdGxldCBzID0gTWF0aC5zcXJ0KHphICogemEgKyB6YyAqIHpjKTtcblx0XHRcdFx0aWYgKHMgPiAwLjAwMDAxKSBzID0gMSAvIHM7XG5cdFx0XHRcdHphICo9IHM7XG5cdFx0XHRcdHpjICo9IHM7XG5cdFx0XHRcdHMgPSBNYXRoLnNxcnQoemEgKiB6YSArIHpjICogemMpO1xuXHRcdFx0XHRpZiAodGhpcy5pbmhlcml0ID09IEluaGVyaXQuTm9TY2FsZVxuXHRcdFx0XHRcdCYmIChwYSAqIHBkIC0gcGIgKiBwYyA8IDApICE9ICh0aGlzLnNrZWxldG9uLnNjYWxlWCA8IDAgIT0gdGhpcy5za2VsZXRvbi5zY2FsZVkgPCAwKSkgcyA9IC1zO1xuXHRcdFx0XHRyb3RhdGlvbiA9IE1hdGguUEkgLyAyICsgTWF0aC5hdGFuMih6YywgemEpO1xuXHRcdFx0XHRjb25zdCB6YiA9IE1hdGguY29zKHJvdGF0aW9uKSAqIHM7XG5cdFx0XHRcdGNvbnN0IHpkID0gTWF0aC5zaW4ocm90YXRpb24pICogcztcblx0XHRcdFx0c2hlYXJYICo9IE1hdGhVdGlscy5kZWdSYWQ7XG5cdFx0XHRcdHNoZWFyWSA9ICg5MCArIHNoZWFyWSkgKiBNYXRoVXRpbHMuZGVnUmFkO1xuXHRcdFx0XHRjb25zdCBsYSA9IE1hdGguY29zKHNoZWFyWCkgKiBzY2FsZVg7XG5cdFx0XHRcdGNvbnN0IGxiID0gTWF0aC5jb3Moc2hlYXJZKSAqIHNjYWxlWTtcblx0XHRcdFx0Y29uc3QgbGMgPSBNYXRoLnNpbihzaGVhclgpICogc2NhbGVYO1xuXHRcdFx0XHRjb25zdCBsZCA9IE1hdGguc2luKHNoZWFyWSkgKiBzY2FsZVk7XG5cdFx0XHRcdHRoaXMuYSA9IHphICogbGEgKyB6YiAqIGxjO1xuXHRcdFx0XHR0aGlzLmIgPSB6YSAqIGxiICsgemIgKiBsZDtcblx0XHRcdFx0dGhpcy5jID0gemMgKiBsYSArIHpkICogbGM7XG5cdFx0XHRcdHRoaXMuZCA9IHpjICogbGIgKyB6ZCAqIGxkO1xuXHRcdFx0XHRicmVhaztcblx0XHRcdH1cblx0XHR9XG5cdFx0dGhpcy5hICo9IHRoaXMuc2tlbGV0b24uc2NhbGVYO1xuXHRcdHRoaXMuYiAqPSB0aGlzLnNrZWxldG9uLnNjYWxlWDtcblx0XHR0aGlzLmMgKj0gdGhpcy5za2VsZXRvbi5zY2FsZVk7XG5cdFx0dGhpcy5kICo9IHRoaXMuc2tlbGV0b24uc2NhbGVZO1xuXHR9XG5cblx0LyoqIFNldHMgdGhpcyBib25lJ3MgbG9jYWwgdHJhbnNmb3JtIHRvIHRoZSBzZXR1cCBwb3NlLiAqL1xuXHRzZXRUb1NldHVwUG9zZSAoKSB7XG5cdFx0bGV0IGRhdGEgPSB0aGlzLmRhdGE7XG5cdFx0dGhpcy54ID0gZGF0YS54O1xuXHRcdHRoaXMueSA9IGRhdGEueTtcblx0XHR0aGlzLnJvdGF0aW9uID0gZGF0YS5yb3RhdGlvbjtcblx0XHR0aGlzLnNjYWxlWCA9IGRhdGEuc2NhbGVYO1xuXHRcdHRoaXMuc2NhbGVZID0gZGF0YS5zY2FsZVk7XG5cdFx0dGhpcy5zaGVhclggPSBkYXRhLnNoZWFyWDtcblx0XHR0aGlzLnNoZWFyWSA9IGRhdGEuc2hlYXJZO1xuXHRcdHRoaXMuaW5oZXJpdCA9IGRhdGEuaW5oZXJpdDtcblx0fVxuXG5cdC8qKiBDb21wdXRlcyB0aGUgYXBwbGllZCB0cmFuc2Zvcm0gdmFsdWVzIGZyb20gdGhlIHdvcmxkIHRyYW5zZm9ybS5cblx0ICpcblx0ICogSWYgdGhlIHdvcmxkIHRyYW5zZm9ybSBpcyBtb2RpZmllZCAoYnkgYSBjb25zdHJhaW50LCB7QGxpbmsgI3JvdGF0ZVdvcmxkKGZsb2F0KX0sIGV0YykgdGhlbiB0aGlzIG1ldGhvZCBzaG91bGQgYmUgY2FsbGVkIHNvXG5cdCAqIHRoZSBhcHBsaWVkIHRyYW5zZm9ybSBtYXRjaGVzIHRoZSB3b3JsZCB0cmFuc2Zvcm0uIFRoZSBhcHBsaWVkIHRyYW5zZm9ybSBtYXkgYmUgbmVlZGVkIGJ5IG90aGVyIGNvZGUgKGVnIHRvIGFwcGx5IG90aGVyXG5cdCAqIGNvbnN0cmFpbnRzKS5cblx0ICpcblx0ICogU29tZSBpbmZvcm1hdGlvbiBpcyBhbWJpZ3VvdXMgaW4gdGhlIHdvcmxkIHRyYW5zZm9ybSwgc3VjaCBhcyAtMSwtMSBzY2FsZSB2ZXJzdXMgMTgwIHJvdGF0aW9uLiBUaGUgYXBwbGllZCB0cmFuc2Zvcm0gYWZ0ZXJcblx0ICogY2FsbGluZyB0aGlzIG1ldGhvZCBpcyBlcXVpdmFsZW50IHRvIHRoZSBsb2NhbCB0cmFuc2Zvcm0gdXNlZCB0byBjb21wdXRlIHRoZSB3b3JsZCB0cmFuc2Zvcm0sIGJ1dCBtYXkgbm90IGJlIGlkZW50aWNhbC4gKi9cblx0dXBkYXRlQXBwbGllZFRyYW5zZm9ybSAoKSB7XG5cdFx0bGV0IHBhcmVudCA9IHRoaXMucGFyZW50O1xuXHRcdGlmICghcGFyZW50KSB7XG5cdFx0XHR0aGlzLmF4ID0gdGhpcy53b3JsZFggLSB0aGlzLnNrZWxldG9uLng7XG5cdFx0XHR0aGlzLmF5ID0gdGhpcy53b3JsZFkgLSB0aGlzLnNrZWxldG9uLnk7XG5cdFx0XHR0aGlzLmFyb3RhdGlvbiA9IE1hdGguYXRhbjIodGhpcy5jLCB0aGlzLmEpICogTWF0aFV0aWxzLnJhZERlZztcblx0XHRcdHRoaXMuYXNjYWxlWCA9IE1hdGguc3FydCh0aGlzLmEgKiB0aGlzLmEgKyB0aGlzLmMgKiB0aGlzLmMpO1xuXHRcdFx0dGhpcy5hc2NhbGVZID0gTWF0aC5zcXJ0KHRoaXMuYiAqIHRoaXMuYiArIHRoaXMuZCAqIHRoaXMuZCk7XG5cdFx0XHR0aGlzLmFzaGVhclggPSAwO1xuXHRcdFx0dGhpcy5hc2hlYXJZID0gTWF0aC5hdGFuMih0aGlzLmEgKiB0aGlzLmIgKyB0aGlzLmMgKiB0aGlzLmQsIHRoaXMuYSAqIHRoaXMuZCAtIHRoaXMuYiAqIHRoaXMuYykgKiBNYXRoVXRpbHMucmFkRGVnO1xuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblx0XHRsZXQgcGEgPSBwYXJlbnQuYSwgcGIgPSBwYXJlbnQuYiwgcGMgPSBwYXJlbnQuYywgcGQgPSBwYXJlbnQuZDtcblx0XHRsZXQgcGlkID0gMSAvIChwYSAqIHBkIC0gcGIgKiBwYyk7XG5cdFx0bGV0IGlhID0gcGQgKiBwaWQsIGliID0gcGIgKiBwaWQsIGljID0gcGMgKiBwaWQsIGlkID0gcGEgKiBwaWQ7XG5cdFx0bGV0IGR4ID0gdGhpcy53b3JsZFggLSBwYXJlbnQud29ybGRYLCBkeSA9IHRoaXMud29ybGRZIC0gcGFyZW50LndvcmxkWTtcblx0XHR0aGlzLmF4ID0gKGR4ICogaWEgLSBkeSAqIGliKTtcblx0XHR0aGlzLmF5ID0gKGR5ICogaWQgLSBkeCAqIGljKTtcblxuXHRcdGxldCByYSwgcmIsIHJjLCByZDtcblx0XHRpZiAodGhpcy5pbmhlcml0ID09IEluaGVyaXQuT25seVRyYW5zbGF0aW9uKSB7XG5cdFx0XHRyYSA9IHRoaXMuYTtcblx0XHRcdHJiID0gdGhpcy5iO1xuXHRcdFx0cmMgPSB0aGlzLmM7XG5cdFx0XHRyZCA9IHRoaXMuZDtcblx0XHR9IGVsc2Uge1xuXHRcdFx0c3dpdGNoICh0aGlzLmluaGVyaXQpIHtcblx0XHRcdFx0Y2FzZSBJbmhlcml0Lk5vUm90YXRpb25PclJlZmxlY3Rpb246IHtcblx0XHRcdFx0XHRsZXQgcyA9IE1hdGguYWJzKHBhICogcGQgLSBwYiAqIHBjKSAvIChwYSAqIHBhICsgcGMgKiBwYyk7XG5cdFx0XHRcdFx0cGIgPSAtcGMgKiB0aGlzLnNrZWxldG9uLnNjYWxlWCAqIHMgLyB0aGlzLnNrZWxldG9uLnNjYWxlWTtcblx0XHRcdFx0XHRwZCA9IHBhICogdGhpcy5za2VsZXRvbi5zY2FsZVkgKiBzIC8gdGhpcy5za2VsZXRvbi5zY2FsZVg7XG5cdFx0XHRcdFx0cGlkID0gMSAvIChwYSAqIHBkIC0gcGIgKiBwYyk7XG5cdFx0XHRcdFx0aWEgPSBwZCAqIHBpZDtcblx0XHRcdFx0XHRpYiA9IHBiICogcGlkO1xuXHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHR9XG5cdFx0XHRcdGNhc2UgSW5oZXJpdC5Ob1NjYWxlOlxuXHRcdFx0XHRjYXNlIEluaGVyaXQuTm9TY2FsZU9yUmVmbGVjdGlvbjpcblx0XHRcdFx0XHRsZXQgY29zID0gTWF0aFV0aWxzLmNvc0RlZyh0aGlzLnJvdGF0aW9uKSwgc2luID0gTWF0aFV0aWxzLnNpbkRlZyh0aGlzLnJvdGF0aW9uKTtcblx0XHRcdFx0XHRwYSA9IChwYSAqIGNvcyArIHBiICogc2luKSAvIHRoaXMuc2tlbGV0b24uc2NhbGVYO1xuXHRcdFx0XHRcdHBjID0gKHBjICogY29zICsgcGQgKiBzaW4pIC8gdGhpcy5za2VsZXRvbi5zY2FsZVk7XG5cdFx0XHRcdFx0bGV0IHMgPSBNYXRoLnNxcnQocGEgKiBwYSArIHBjICogcGMpO1xuXHRcdFx0XHRcdGlmIChzID4gMC4wMDAwMSkgcyA9IDEgLyBzO1xuXHRcdFx0XHRcdHBhICo9IHM7XG5cdFx0XHRcdFx0cGMgKj0gcztcblx0XHRcdFx0XHRzID0gTWF0aC5zcXJ0KHBhICogcGEgKyBwYyAqIHBjKTtcblx0XHRcdFx0XHRpZiAodGhpcy5pbmhlcml0ID09IEluaGVyaXQuTm9TY2FsZSAmJiBwaWQgPCAwICE9ICh0aGlzLnNrZWxldG9uLnNjYWxlWCA8IDAgIT0gdGhpcy5za2VsZXRvbi5zY2FsZVkgPCAwKSkgcyA9IC1zO1xuXHRcdFx0XHRcdGxldCByID0gTWF0aFV0aWxzLlBJIC8gMiArIE1hdGguYXRhbjIocGMsIHBhKTtcblx0XHRcdFx0XHRwYiA9IE1hdGguY29zKHIpICogcztcblx0XHRcdFx0XHRwZCA9IE1hdGguc2luKHIpICogcztcblx0XHRcdFx0XHRwaWQgPSAxIC8gKHBhICogcGQgLSBwYiAqIHBjKTtcblx0XHRcdFx0XHRpYSA9IHBkICogcGlkO1xuXHRcdFx0XHRcdGliID0gcGIgKiBwaWQ7XG5cdFx0XHRcdFx0aWMgPSBwYyAqIHBpZDtcblx0XHRcdFx0XHRpZCA9IHBhICogcGlkO1xuXHRcdFx0fVxuXHRcdFx0cmEgPSBpYSAqIHRoaXMuYSAtIGliICogdGhpcy5jO1xuXHRcdFx0cmIgPSBpYSAqIHRoaXMuYiAtIGliICogdGhpcy5kO1xuXHRcdFx0cmMgPSBpZCAqIHRoaXMuYyAtIGljICogdGhpcy5hO1xuXHRcdFx0cmQgPSBpZCAqIHRoaXMuZCAtIGljICogdGhpcy5iO1xuXHRcdH1cblxuXHRcdHRoaXMuYXNoZWFyWCA9IDA7XG5cdFx0dGhpcy5hc2NhbGVYID0gTWF0aC5zcXJ0KHJhICogcmEgKyByYyAqIHJjKTtcblx0XHRpZiAodGhpcy5hc2NhbGVYID4gMC4wMDAxKSB7XG5cdFx0XHRsZXQgZGV0ID0gcmEgKiByZCAtIHJiICogcmM7XG5cdFx0XHR0aGlzLmFzY2FsZVkgPSBkZXQgLyB0aGlzLmFzY2FsZVg7XG5cdFx0XHR0aGlzLmFzaGVhclkgPSAtTWF0aC5hdGFuMihyYSAqIHJiICsgcmMgKiByZCwgZGV0KSAqIE1hdGhVdGlscy5yYWREZWc7XG5cdFx0XHR0aGlzLmFyb3RhdGlvbiA9IE1hdGguYXRhbjIocmMsIHJhKSAqIE1hdGhVdGlscy5yYWREZWc7XG5cdFx0fSBlbHNlIHtcblx0XHRcdHRoaXMuYXNjYWxlWCA9IDA7XG5cdFx0XHR0aGlzLmFzY2FsZVkgPSBNYXRoLnNxcnQocmIgKiByYiArIHJkICogcmQpO1xuXHRcdFx0dGhpcy5hc2hlYXJZID0gMDtcblx0XHRcdHRoaXMuYXJvdGF0aW9uID0gOTAgLSBNYXRoLmF0YW4yKHJkLCByYikgKiBNYXRoVXRpbHMucmFkRGVnO1xuXHRcdH1cblx0fVxuXG5cblx0LyoqIFRoZSB3b3JsZCByb3RhdGlvbiBmb3IgdGhlIFggYXhpcywgY2FsY3VsYXRlZCB1c2luZyB7QGxpbmsgI2F9IGFuZCB7QGxpbmsgI2N9LiAqL1xuXHRnZXRXb3JsZFJvdGF0aW9uWCAoKSB7XG5cdFx0cmV0dXJuIE1hdGguYXRhbjIodGhpcy5jLCB0aGlzLmEpICogTWF0aFV0aWxzLnJhZERlZztcblx0fVxuXG5cdC8qKiBUaGUgd29ybGQgcm90YXRpb24gZm9yIHRoZSBZIGF4aXMsIGNhbGN1bGF0ZWQgdXNpbmcge0BsaW5rICNifSBhbmQge0BsaW5rICNkfS4gKi9cblx0Z2V0V29ybGRSb3RhdGlvblkgKCkge1xuXHRcdHJldHVybiBNYXRoLmF0YW4yKHRoaXMuZCwgdGhpcy5iKSAqIE1hdGhVdGlscy5yYWREZWc7XG5cdH1cblxuXHQvKiogVGhlIG1hZ25pdHVkZSAoYWx3YXlzIHBvc2l0aXZlKSBvZiB0aGUgd29ybGQgc2NhbGUgWCwgY2FsY3VsYXRlZCB1c2luZyB7QGxpbmsgI2F9IGFuZCB7QGxpbmsgI2N9LiAqL1xuXHRnZXRXb3JsZFNjYWxlWCAoKSB7XG5cdFx0cmV0dXJuIE1hdGguc3FydCh0aGlzLmEgKiB0aGlzLmEgKyB0aGlzLmMgKiB0aGlzLmMpO1xuXHR9XG5cblx0LyoqIFRoZSBtYWduaXR1ZGUgKGFsd2F5cyBwb3NpdGl2ZSkgb2YgdGhlIHdvcmxkIHNjYWxlIFksIGNhbGN1bGF0ZWQgdXNpbmcge0BsaW5rICNifSBhbmQge0BsaW5rICNkfS4gKi9cblx0Z2V0V29ybGRTY2FsZVkgKCkge1xuXHRcdHJldHVybiBNYXRoLnNxcnQodGhpcy5iICogdGhpcy5iICsgdGhpcy5kICogdGhpcy5kKTtcblx0fVxuXG5cdC8qKiBUcmFuc2Zvcm1zIGEgcG9pbnQgZnJvbSB3b3JsZCBjb29yZGluYXRlcyB0byB0aGUgYm9uZSdzIGxvY2FsIGNvb3JkaW5hdGVzLiAqL1xuXHR3b3JsZFRvTG9jYWwgKHdvcmxkOiBWZWN0b3IyKSB7XG5cdFx0bGV0IGludkRldCA9IDEgLyAodGhpcy5hICogdGhpcy5kIC0gdGhpcy5iICogdGhpcy5jKTtcblx0XHRsZXQgeCA9IHdvcmxkLnggLSB0aGlzLndvcmxkWCwgeSA9IHdvcmxkLnkgLSB0aGlzLndvcmxkWTtcblx0XHR3b3JsZC54ID0geCAqIHRoaXMuZCAqIGludkRldCAtIHkgKiB0aGlzLmIgKiBpbnZEZXQ7XG5cdFx0d29ybGQueSA9IHkgKiB0aGlzLmEgKiBpbnZEZXQgLSB4ICogdGhpcy5jICogaW52RGV0O1xuXHRcdHJldHVybiB3b3JsZDtcblx0fVxuXG5cdC8qKiBUcmFuc2Zvcm1zIGEgcG9pbnQgZnJvbSB0aGUgYm9uZSdzIGxvY2FsIGNvb3JkaW5hdGVzIHRvIHdvcmxkIGNvb3JkaW5hdGVzLiAqL1xuXHRsb2NhbFRvV29ybGQgKGxvY2FsOiBWZWN0b3IyKSB7XG5cdFx0bGV0IHggPSBsb2NhbC54LCB5ID0gbG9jYWwueTtcblx0XHRsb2NhbC54ID0geCAqIHRoaXMuYSArIHkgKiB0aGlzLmIgKyB0aGlzLndvcmxkWDtcblx0XHRsb2NhbC55ID0geCAqIHRoaXMuYyArIHkgKiB0aGlzLmQgKyB0aGlzLndvcmxkWTtcblx0XHRyZXR1cm4gbG9jYWw7XG5cdH1cblxuXHQvKiogVHJhbnNmb3JtcyBhIHBvaW50IGZyb20gd29ybGQgY29vcmRpbmF0ZXMgdG8gdGhlIHBhcmVudCBib25lJ3MgbG9jYWwgY29vcmRpbmF0ZXMuICovXG5cdHdvcmxkVG9QYXJlbnQgKHdvcmxkOiBWZWN0b3IyKSB7XG5cdFx0aWYgKHdvcmxkID09IG51bGwpIHRocm93IG5ldyBFcnJvcihcIndvcmxkIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRyZXR1cm4gdGhpcy5wYXJlbnQgPT0gbnVsbCA/IHdvcmxkIDogdGhpcy5wYXJlbnQud29ybGRUb0xvY2FsKHdvcmxkKTtcblx0fVxuXG5cdC8qKiBUcmFuc2Zvcm1zIGEgcG9pbnQgZnJvbSB0aGUgcGFyZW50IGJvbmUncyBjb29yZGluYXRlcyB0byB3b3JsZCBjb29yZGluYXRlcy4gKi9cblx0cGFyZW50VG9Xb3JsZCAod29ybGQ6IFZlY3RvcjIpIHtcblx0XHRpZiAod29ybGQgPT0gbnVsbCkgdGhyb3cgbmV3IEVycm9yKFwid29ybGQgY2Fubm90IGJlIG51bGwuXCIpO1xuXHRcdHJldHVybiB0aGlzLnBhcmVudCA9PSBudWxsID8gd29ybGQgOiB0aGlzLnBhcmVudC5sb2NhbFRvV29ybGQod29ybGQpO1xuXHR9XG5cblx0LyoqIFRyYW5zZm9ybXMgYSB3b3JsZCByb3RhdGlvbiB0byBhIGxvY2FsIHJvdGF0aW9uLiAqL1xuXHR3b3JsZFRvTG9jYWxSb3RhdGlvbiAod29ybGRSb3RhdGlvbjogbnVtYmVyKSB7XG5cdFx0bGV0IHNpbiA9IE1hdGhVdGlscy5zaW5EZWcod29ybGRSb3RhdGlvbiksIGNvcyA9IE1hdGhVdGlscy5jb3NEZWcod29ybGRSb3RhdGlvbik7XG5cdFx0cmV0dXJuIE1hdGguYXRhbjIodGhpcy5hICogc2luIC0gdGhpcy5jICogY29zLCB0aGlzLmQgKiBjb3MgLSB0aGlzLmIgKiBzaW4pICogTWF0aFV0aWxzLnJhZERlZyArIHRoaXMucm90YXRpb24gLSB0aGlzLnNoZWFyWDtcblx0fVxuXG5cdC8qKiBUcmFuc2Zvcm1zIGEgbG9jYWwgcm90YXRpb24gdG8gYSB3b3JsZCByb3RhdGlvbi4gKi9cblx0bG9jYWxUb1dvcmxkUm90YXRpb24gKGxvY2FsUm90YXRpb246IG51bWJlcikge1xuXHRcdGxvY2FsUm90YXRpb24gLT0gdGhpcy5yb3RhdGlvbiAtIHRoaXMuc2hlYXJYO1xuXHRcdGxldCBzaW4gPSBNYXRoVXRpbHMuc2luRGVnKGxvY2FsUm90YXRpb24pLCBjb3MgPSBNYXRoVXRpbHMuY29zRGVnKGxvY2FsUm90YXRpb24pO1xuXHRcdHJldHVybiBNYXRoLmF0YW4yKGNvcyAqIHRoaXMuYyArIHNpbiAqIHRoaXMuZCwgY29zICogdGhpcy5hICsgc2luICogdGhpcy5iKSAqIE1hdGhVdGlscy5yYWREZWc7XG5cdH1cblxuXHQvKiogUm90YXRlcyB0aGUgd29ybGQgdHJhbnNmb3JtIHRoZSBzcGVjaWZpZWQgYW1vdW50LlxuXHQgKiA8cD5cblx0ICogQWZ0ZXIgY2hhbmdlcyBhcmUgbWFkZSB0byB0aGUgd29ybGQgdHJhbnNmb3JtLCB7QGxpbmsgI3VwZGF0ZUFwcGxpZWRUcmFuc2Zvcm0oKX0gc2hvdWxkIGJlIGNhbGxlZCBhbmRcblx0ICoge0BsaW5rICN1cGRhdGUoUGh5c2ljcyl9IHdpbGwgbmVlZCB0byBiZSBjYWxsZWQgb24gYW55IGNoaWxkIGJvbmVzLCByZWN1cnNpdmVseS4gKi9cblx0cm90YXRlV29ybGQgKGRlZ3JlZXM6IG51bWJlcikge1xuXHRcdGRlZ3JlZXMgKj0gTWF0aFV0aWxzLmRlZ1JhZDtcblx0XHRjb25zdCBzaW4gPSBNYXRoLnNpbihkZWdyZWVzKSwgY29zID0gTWF0aC5jb3MoZGVncmVlcyk7XG5cdFx0Y29uc3QgcmEgPSB0aGlzLmEsIHJiID0gdGhpcy5iO1xuXHRcdHRoaXMuYSA9IGNvcyAqIHJhIC0gc2luICogdGhpcy5jO1xuXHRcdHRoaXMuYiA9IGNvcyAqIHJiIC0gc2luICogdGhpcy5kO1xuXHRcdHRoaXMuYyA9IHNpbiAqIHJhICsgY29zICogdGhpcy5jO1xuXHRcdHRoaXMuZCA9IHNpbiAqIHJiICsgY29zICogdGhpcy5kO1xuXHR9XG59XG4iXX0=