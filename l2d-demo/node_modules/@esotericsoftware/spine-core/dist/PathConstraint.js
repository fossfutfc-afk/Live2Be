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
import { PathAttachment } from "./attachments/PathAttachment.js";
import { RotateMode, SpacingMode, PositionMode } from "./PathConstraintData.js";
import { Utils, MathUtils } from "./Utils.js";
/** Stores the current pose for a path constraint. A path constraint adjusts the rotation, translation, and scale of the
 * constrained bones so they follow a {@link PathAttachment}.
 *
 * See [Path constraints](http://esotericsoftware.com/spine-path-constraints) in the Spine User Guide. */
export class PathConstraint {
    static NONE = -1;
    static BEFORE = -2;
    static AFTER = -3;
    static epsilon = 0.00001;
    /** The path constraint's setup pose data. */
    data;
    /** The bones that will be modified by this path constraint. */
    bones;
    /** The slot whose path attachment will be used to constrained the bones. */
    target;
    /** The position along the path. */
    position = 0;
    /** The spacing between bones. */
    spacing = 0;
    mixRotate = 0;
    mixX = 0;
    mixY = 0;
    spaces = new Array();
    positions = new Array();
    world = new Array();
    curves = new Array();
    lengths = new Array();
    segments = new Array();
    active = false;
    constructor(data, skeleton) {
        if (!data)
            throw new Error("data cannot be null.");
        if (!skeleton)
            throw new Error("skeleton cannot be null.");
        this.data = data;
        this.bones = new Array();
        for (let i = 0, n = data.bones.length; i < n; i++) {
            let bone = skeleton.findBone(data.bones[i].name);
            if (!bone)
                throw new Error(`Couldn't find bone ${data.bones[i].name}.`);
            this.bones.push(bone);
        }
        let target = skeleton.findSlot(data.target.name);
        if (!target)
            throw new Error(`Couldn't find target bone ${data.target.name}`);
        this.target = target;
        this.position = data.position;
        this.spacing = data.spacing;
        this.mixRotate = data.mixRotate;
        this.mixX = data.mixX;
        this.mixY = data.mixY;
    }
    isActive() {
        return this.active;
    }
    setToSetupPose() {
        const data = this.data;
        this.position = data.position;
        this.spacing = data.spacing;
        this.mixRotate = data.mixRotate;
        this.mixX = data.mixX;
        this.mixY = data.mixY;
    }
    update(physics) {
        let attachment = this.target.getAttachment();
        if (!(attachment instanceof PathAttachment))
            return;
        let mixRotate = this.mixRotate, mixX = this.mixX, mixY = this.mixY;
        if (mixRotate == 0 && mixX == 0 && mixY == 0)
            return;
        let data = this.data;
        let tangents = data.rotateMode == RotateMode.Tangent, scale = data.rotateMode == RotateMode.ChainScale;
        let bones = this.bones;
        let boneCount = bones.length, spacesCount = tangents ? boneCount : boneCount + 1;
        let spaces = Utils.setArraySize(this.spaces, spacesCount), lengths = scale ? this.lengths = Utils.setArraySize(this.lengths, boneCount) : [];
        let spacing = this.spacing;
        switch (data.spacingMode) {
            case SpacingMode.Percent:
                if (scale) {
                    for (let i = 0, n = spacesCount - 1; i < n; i++) {
                        let bone = bones[i];
                        let setupLength = bone.data.length;
                        let x = setupLength * bone.a, y = setupLength * bone.c;
                        lengths[i] = Math.sqrt(x * x + y * y);
                    }
                }
                Utils.arrayFill(spaces, 1, spacesCount, spacing);
                break;
            case SpacingMode.Proportional:
                let sum = 0;
                for (let i = 0, n = spacesCount - 1; i < n;) {
                    let bone = bones[i];
                    let setupLength = bone.data.length;
                    if (setupLength < PathConstraint.epsilon) {
                        if (scale)
                            lengths[i] = 0;
                        spaces[++i] = spacing;
                    }
                    else {
                        let x = setupLength * bone.a, y = setupLength * bone.c;
                        let length = Math.sqrt(x * x + y * y);
                        if (scale)
                            lengths[i] = length;
                        spaces[++i] = length;
                        sum += length;
                    }
                }
                if (sum > 0) {
                    sum = spacesCount / sum * spacing;
                    for (let i = 1; i < spacesCount; i++)
                        spaces[i] *= sum;
                }
                break;
            default:
                let lengthSpacing = data.spacingMode == SpacingMode.Length;
                for (let i = 0, n = spacesCount - 1; i < n;) {
                    let bone = bones[i];
                    let setupLength = bone.data.length;
                    if (setupLength < PathConstraint.epsilon) {
                        if (scale)
                            lengths[i] = 0;
                        spaces[++i] = spacing;
                    }
                    else {
                        let x = setupLength * bone.a, y = setupLength * bone.c;
                        let length = Math.sqrt(x * x + y * y);
                        if (scale)
                            lengths[i] = length;
                        spaces[++i] = (lengthSpacing ? setupLength + spacing : spacing) * length / setupLength;
                    }
                }
        }
        let positions = this.computeWorldPositions(attachment, spacesCount, tangents);
        let boneX = positions[0], boneY = positions[1], offsetRotation = data.offsetRotation;
        let tip = false;
        if (offsetRotation == 0)
            tip = data.rotateMode == RotateMode.Chain;
        else {
            tip = false;
            let p = this.target.bone;
            offsetRotation *= p.a * p.d - p.b * p.c > 0 ? MathUtils.degRad : -MathUtils.degRad;
        }
        for (let i = 0, p = 3; i < boneCount; i++, p += 3) {
            let bone = bones[i];
            bone.worldX += (boneX - bone.worldX) * mixX;
            bone.worldY += (boneY - bone.worldY) * mixY;
            let x = positions[p], y = positions[p + 1], dx = x - boneX, dy = y - boneY;
            if (scale) {
                let length = lengths[i];
                if (length != 0) {
                    let s = (Math.sqrt(dx * dx + dy * dy) / length - 1) * mixRotate + 1;
                    bone.a *= s;
                    bone.c *= s;
                }
            }
            boneX = x;
            boneY = y;
            if (mixRotate > 0) {
                let a = bone.a, b = bone.b, c = bone.c, d = bone.d, r = 0, cos = 0, sin = 0;
                if (tangents)
                    r = positions[p - 1];
                else if (spaces[i + 1] == 0)
                    r = positions[p + 2];
                else
                    r = Math.atan2(dy, dx);
                r -= Math.atan2(c, a);
                if (tip) {
                    cos = Math.cos(r);
                    sin = Math.sin(r);
                    let length = bone.data.length;
                    boneX += (length * (cos * a - sin * c) - dx) * mixRotate;
                    boneY += (length * (sin * a + cos * c) - dy) * mixRotate;
                }
                else {
                    r += offsetRotation;
                }
                if (r > MathUtils.PI)
                    r -= MathUtils.PI2;
                else if (r < -MathUtils.PI) //
                    r += MathUtils.PI2;
                r *= mixRotate;
                cos = Math.cos(r);
                sin = Math.sin(r);
                bone.a = cos * a - sin * c;
                bone.b = cos * b - sin * d;
                bone.c = sin * a + cos * c;
                bone.d = sin * b + cos * d;
            }
            bone.updateAppliedTransform();
        }
    }
    computeWorldPositions(path, spacesCount, tangents) {
        let target = this.target;
        let position = this.position;
        let spaces = this.spaces, out = Utils.setArraySize(this.positions, spacesCount * 3 + 2), world = this.world;
        let closed = path.closed;
        let verticesLength = path.worldVerticesLength, curveCount = verticesLength / 6, prevCurve = PathConstraint.NONE;
        if (!path.constantSpeed) {
            let lengths = path.lengths;
            curveCount -= closed ? 1 : 2;
            let pathLength = lengths[curveCount];
            if (this.data.positionMode == PositionMode.Percent)
                position *= pathLength;
            let multiplier;
            switch (this.data.spacingMode) {
                case SpacingMode.Percent:
                    multiplier = pathLength;
                    break;
                case SpacingMode.Proportional:
                    multiplier = pathLength / spacesCount;
                    break;
                default:
                    multiplier = 1;
            }
            world = Utils.setArraySize(this.world, 8);
            for (let i = 0, o = 0, curve = 0; i < spacesCount; i++, o += 3) {
                let space = spaces[i] * multiplier;
                position += space;
                let p = position;
                if (closed) {
                    p %= pathLength;
                    if (p < 0)
                        p += pathLength;
                    curve = 0;
                }
                else if (p < 0) {
                    if (prevCurve != PathConstraint.BEFORE) {
                        prevCurve = PathConstraint.BEFORE;
                        path.computeWorldVertices(target, 2, 4, world, 0, 2);
                    }
                    this.addBeforePosition(p, world, 0, out, o);
                    continue;
                }
                else if (p > pathLength) {
                    if (prevCurve != PathConstraint.AFTER) {
                        prevCurve = PathConstraint.AFTER;
                        path.computeWorldVertices(target, verticesLength - 6, 4, world, 0, 2);
                    }
                    this.addAfterPosition(p - pathLength, world, 0, out, o);
                    continue;
                }
                // Determine curve containing position.
                for (;; curve++) {
                    let length = lengths[curve];
                    if (p > length)
                        continue;
                    if (curve == 0)
                        p /= length;
                    else {
                        let prev = lengths[curve - 1];
                        p = (p - prev) / (length - prev);
                    }
                    break;
                }
                if (curve != prevCurve) {
                    prevCurve = curve;
                    if (closed && curve == curveCount) {
                        path.computeWorldVertices(target, verticesLength - 4, 4, world, 0, 2);
                        path.computeWorldVertices(target, 0, 4, world, 4, 2);
                    }
                    else
                        path.computeWorldVertices(target, curve * 6 + 2, 8, world, 0, 2);
                }
                this.addCurvePosition(p, world[0], world[1], world[2], world[3], world[4], world[5], world[6], world[7], out, o, tangents || (i > 0 && space == 0));
            }
            return out;
        }
        // World vertices.
        if (closed) {
            verticesLength += 2;
            world = Utils.setArraySize(this.world, verticesLength);
            path.computeWorldVertices(target, 2, verticesLength - 4, world, 0, 2);
            path.computeWorldVertices(target, 0, 2, world, verticesLength - 4, 2);
            world[verticesLength - 2] = world[0];
            world[verticesLength - 1] = world[1];
        }
        else {
            curveCount--;
            verticesLength -= 4;
            world = Utils.setArraySize(this.world, verticesLength);
            path.computeWorldVertices(target, 2, verticesLength, world, 0, 2);
        }
        // Curve lengths.
        let curves = Utils.setArraySize(this.curves, curveCount);
        let pathLength = 0;
        let x1 = world[0], y1 = world[1], cx1 = 0, cy1 = 0, cx2 = 0, cy2 = 0, x2 = 0, y2 = 0;
        let tmpx = 0, tmpy = 0, dddfx = 0, dddfy = 0, ddfx = 0, ddfy = 0, dfx = 0, dfy = 0;
        for (let i = 0, w = 2; i < curveCount; i++, w += 6) {
            cx1 = world[w];
            cy1 = world[w + 1];
            cx2 = world[w + 2];
            cy2 = world[w + 3];
            x2 = world[w + 4];
            y2 = world[w + 5];
            tmpx = (x1 - cx1 * 2 + cx2) * 0.1875;
            tmpy = (y1 - cy1 * 2 + cy2) * 0.1875;
            dddfx = ((cx1 - cx2) * 3 - x1 + x2) * 0.09375;
            dddfy = ((cy1 - cy2) * 3 - y1 + y2) * 0.09375;
            ddfx = tmpx * 2 + dddfx;
            ddfy = tmpy * 2 + dddfy;
            dfx = (cx1 - x1) * 0.75 + tmpx + dddfx * 0.16666667;
            dfy = (cy1 - y1) * 0.75 + tmpy + dddfy * 0.16666667;
            pathLength += Math.sqrt(dfx * dfx + dfy * dfy);
            dfx += ddfx;
            dfy += ddfy;
            ddfx += dddfx;
            ddfy += dddfy;
            pathLength += Math.sqrt(dfx * dfx + dfy * dfy);
            dfx += ddfx;
            dfy += ddfy;
            pathLength += Math.sqrt(dfx * dfx + dfy * dfy);
            dfx += ddfx + dddfx;
            dfy += ddfy + dddfy;
            pathLength += Math.sqrt(dfx * dfx + dfy * dfy);
            curves[i] = pathLength;
            x1 = x2;
            y1 = y2;
        }
        if (this.data.positionMode == PositionMode.Percent)
            position *= pathLength;
        let multiplier;
        switch (this.data.spacingMode) {
            case SpacingMode.Percent:
                multiplier = pathLength;
                break;
            case SpacingMode.Proportional:
                multiplier = pathLength / spacesCount;
                break;
            default:
                multiplier = 1;
        }
        let segments = this.segments;
        let curveLength = 0;
        for (let i = 0, o = 0, curve = 0, segment = 0; i < spacesCount; i++, o += 3) {
            let space = spaces[i] * multiplier;
            position += space;
            let p = position;
            if (closed) {
                p %= pathLength;
                if (p < 0)
                    p += pathLength;
                curve = 0;
            }
            else if (p < 0) {
                this.addBeforePosition(p, world, 0, out, o);
                continue;
            }
            else if (p > pathLength) {
                this.addAfterPosition(p - pathLength, world, verticesLength - 4, out, o);
                continue;
            }
            // Determine curve containing position.
            for (;; curve++) {
                let length = curves[curve];
                if (p > length)
                    continue;
                if (curve == 0)
                    p /= length;
                else {
                    let prev = curves[curve - 1];
                    p = (p - prev) / (length - prev);
                }
                break;
            }
            // Curve segment lengths.
            if (curve != prevCurve) {
                prevCurve = curve;
                let ii = curve * 6;
                x1 = world[ii];
                y1 = world[ii + 1];
                cx1 = world[ii + 2];
                cy1 = world[ii + 3];
                cx2 = world[ii + 4];
                cy2 = world[ii + 5];
                x2 = world[ii + 6];
                y2 = world[ii + 7];
                tmpx = (x1 - cx1 * 2 + cx2) * 0.03;
                tmpy = (y1 - cy1 * 2 + cy2) * 0.03;
                dddfx = ((cx1 - cx2) * 3 - x1 + x2) * 0.006;
                dddfy = ((cy1 - cy2) * 3 - y1 + y2) * 0.006;
                ddfx = tmpx * 2 + dddfx;
                ddfy = tmpy * 2 + dddfy;
                dfx = (cx1 - x1) * 0.3 + tmpx + dddfx * 0.16666667;
                dfy = (cy1 - y1) * 0.3 + tmpy + dddfy * 0.16666667;
                curveLength = Math.sqrt(dfx * dfx + dfy * dfy);
                segments[0] = curveLength;
                for (ii = 1; ii < 8; ii++) {
                    dfx += ddfx;
                    dfy += ddfy;
                    ddfx += dddfx;
                    ddfy += dddfy;
                    curveLength += Math.sqrt(dfx * dfx + dfy * dfy);
                    segments[ii] = curveLength;
                }
                dfx += ddfx;
                dfy += ddfy;
                curveLength += Math.sqrt(dfx * dfx + dfy * dfy);
                segments[8] = curveLength;
                dfx += ddfx + dddfx;
                dfy += ddfy + dddfy;
                curveLength += Math.sqrt(dfx * dfx + dfy * dfy);
                segments[9] = curveLength;
                segment = 0;
            }
            // Weight by segment length.
            p *= curveLength;
            for (;; segment++) {
                let length = segments[segment];
                if (p > length)
                    continue;
                if (segment == 0)
                    p /= length;
                else {
                    let prev = segments[segment - 1];
                    p = segment + (p - prev) / (length - prev);
                }
                break;
            }
            this.addCurvePosition(p * 0.1, x1, y1, cx1, cy1, cx2, cy2, x2, y2, out, o, tangents || (i > 0 && space == 0));
        }
        return out;
    }
    addBeforePosition(p, temp, i, out, o) {
        let x1 = temp[i], y1 = temp[i + 1], dx = temp[i + 2] - x1, dy = temp[i + 3] - y1, r = Math.atan2(dy, dx);
        out[o] = x1 + p * Math.cos(r);
        out[o + 1] = y1 + p * Math.sin(r);
        out[o + 2] = r;
    }
    addAfterPosition(p, temp, i, out, o) {
        let x1 = temp[i + 2], y1 = temp[i + 3], dx = x1 - temp[i], dy = y1 - temp[i + 1], r = Math.atan2(dy, dx);
        out[o] = x1 + p * Math.cos(r);
        out[o + 1] = y1 + p * Math.sin(r);
        out[o + 2] = r;
    }
    addCurvePosition(p, x1, y1, cx1, cy1, cx2, cy2, x2, y2, out, o, tangents) {
        if (p == 0 || isNaN(p)) {
            out[o] = x1;
            out[o + 1] = y1;
            out[o + 2] = Math.atan2(cy1 - y1, cx1 - x1);
            return;
        }
        let tt = p * p, ttt = tt * p, u = 1 - p, uu = u * u, uuu = uu * u;
        let ut = u * p, ut3 = ut * 3, uut3 = u * ut3, utt3 = ut3 * p;
        let x = x1 * uuu + cx1 * uut3 + cx2 * utt3 + x2 * ttt, y = y1 * uuu + cy1 * uut3 + cy2 * utt3 + y2 * ttt;
        out[o] = x;
        out[o + 1] = y;
        if (tangents) {
            if (p < 0.001)
                out[o + 2] = Math.atan2(cy1 - y1, cx1 - x1);
            else
                out[o + 2] = Math.atan2(y - (y1 * uu + cy1 * ut * 2 + cy2 * tt), x - (x1 * uu + cx1 * ut * 2 + cx2 * tt));
        }
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiUGF0aENvbnN0cmFpbnQuanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyIuLi9zcmMvUGF0aENvbnN0cmFpbnQudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OzsrRUEyQitFO0FBRS9FLE9BQU8sRUFBRSxjQUFjLEVBQUUsTUFBTSxpQ0FBaUMsQ0FBQztBQUVqRSxPQUFPLEVBQXNCLFVBQVUsRUFBRSxXQUFXLEVBQUUsWUFBWSxFQUFFLE1BQU0seUJBQXlCLENBQUM7QUFJcEcsT0FBTyxFQUFFLEtBQUssRUFBRSxTQUFTLEVBQUUsTUFBTSxZQUFZLENBQUM7QUFHOUM7Ozt5R0FHeUc7QUFDekcsTUFBTSxPQUFPLGNBQWM7SUFDMUIsTUFBTSxDQUFDLElBQUksR0FBRyxDQUFDLENBQUMsQ0FBQztJQUFDLE1BQU0sQ0FBQyxNQUFNLEdBQUcsQ0FBQyxDQUFDLENBQUM7SUFBQyxNQUFNLENBQUMsS0FBSyxHQUFHLENBQUMsQ0FBQyxDQUFDO0lBQ3hELE1BQU0sQ0FBQyxPQUFPLEdBQUcsT0FBTyxDQUFDO0lBRXpCLDZDQUE2QztJQUM3QyxJQUFJLENBQXFCO0lBRXpCLCtEQUErRDtJQUMvRCxLQUFLLENBQWM7SUFFbkIsNEVBQTRFO0lBQzVFLE1BQU0sQ0FBTztJQUViLG1DQUFtQztJQUNuQyxRQUFRLEdBQUcsQ0FBQyxDQUFDO0lBRWIsaUNBQWlDO0lBQ2pDLE9BQU8sR0FBRyxDQUFDLENBQUM7SUFFWixTQUFTLEdBQUcsQ0FBQyxDQUFDO0lBRWQsSUFBSSxHQUFHLENBQUMsQ0FBQztJQUVULElBQUksR0FBRyxDQUFDLENBQUM7SUFFVCxNQUFNLEdBQUcsSUFBSSxLQUFLLEVBQVUsQ0FBQztJQUFDLFNBQVMsR0FBRyxJQUFJLEtBQUssRUFBVSxDQUFDO0lBQzlELEtBQUssR0FBRyxJQUFJLEtBQUssRUFBVSxDQUFDO0lBQUMsTUFBTSxHQUFHLElBQUksS0FBSyxFQUFVLENBQUM7SUFBQyxPQUFPLEdB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QUUsQ0FBQyxFQUFFLENBQUMsQ0FBQyxDQUFDO1FBQ25FLENBQUM7UUFFRCxpQkFBaUI7UUFDakIsSUFBSSxNQUFNLEdBQUcsS0FBSyxDQUFDLFlBQVksQ0FBQyxJQUFJLENBQUMsTUFBTSxFQUFFLFVBQVUsQ0FBQyxDQUFDO1FBQ3pELElBQUksVUFBVSxHQUFHLENBQUMsQ0FBQztRQUNuQixJQUFJLEVBQUUsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDLEVBQUUsRUFBRSxHQUFHLEtBQUssQ0FBQyxDQUFDLENBQUMsRUFBRSxHQUFHLEdBQUcsQ0FBQyxFQUFFLEdBQUcsR0FBRyxDQUFDLEVBQUUsR0FBRyxHQUFHLENBQUMsRUFBRSxHQUFHLEdBQUcsQ0FBQyxFQUFFLEVBQUUsR0FBRyxDQUFDLEVBQUUsRUFBRSxHQUFHLENBQUMsQ0FBQztRQUNyRixJQUFJLElBQUksR0FBRyxDQUFDLEVBQUUsSUFBSSxHQUFHLENBQUMsRUFBRSxLQUFLLEdBQUcsQ0FBQyxFQUFFLEtBQUssR0FBRyxDQUFDLEVBQUUsSUFBSSxHQUFHLENBQUMsRUFBRSxJQUFJLEdBQUcsQ0FBQyxFQUFFLEdBQUcsR0FBRyxDQUFDLEVBQUUsR0FBRyxHQUFHLENBQUMsQ0FBQztRQUNuRixLQUFLLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEdBQUcsQ0FBQyxFQUFFLENBQUMsR0FBRyxVQUFVLEVBQUUsQ0FBQyxFQUFFLEVBQUUsQ0FBQyxJQUFJLENBQUMsRUFBRSxDQUFDO1lBQ3BELEdBQUcsR0FBRyxLQUFLLENBQUMsQ0FBQyxDQUFDLENBQUM7WUFDZixHQUFHLEdBQUcsS0FBSyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsQ0FBQztZQUNuQixHQUFHLEdBQUcsS0FBSyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsQ0FBQztZQUNuQixHQUFHLEdBQUcsS0FBSyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsQ0FBQztZQUNuQixFQUFFLEdBQUcsS0FBSyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsQ0FBQztZQUNsQixFQUFFLEdBQUcsS0FBSyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsQ0FBQztZQUNsQixJQUFJLEdBQUcsQ0FBQyxFQUFFLEdBQUcsR0FBRyxHQUFHLENBQUMsR0FBRyxHQUFHLENBQUMsR0FBRyxNQUFNLENBQUM7WUFDckMsSUFBSSxHQUFHLENBQUMsRUFBRSxHQUFHLEdBQUcsR0FBRyxDQUFDLEdBQUcsR0FBRyxDQUFDLEdBQUcsTUFBTSxDQUFDO1lBQ3JDLEtBQUssR0FBRyxDQUFDLENBQUMsR0FBRyxHQUFHLEdBQUcsQ0FBQyxHQUFHLENBQUMsR0FBRyxFQUFFLEdBQUcsRUFBRSxDQUFDLEdBQUcsT0FBTyxDQUFDO1lBQzlDLEtBQUssR0FBRyxDQUFDLENBQUMsR0FBRyxHQUFHLEdBQUcsQ0FBQyxHQUFHLENBQUMsR0FBRyxFQUFFLEdBQUcsRUFBRSxDQUFDLEdBQUcsT0FBTyxDQUFDO1lBQzlDLElBQUksR0FBRyxJQUFJLEdBQUcsQ0FBQyxHQUFHLEtBQUssQ0FBQztZQUN4QixJQUFJLEdBQUcsSUFBSSxHQUFHLENBQUMsR0FBRyxLQUFLLENBQUM7WUFDeEIsR0FBRyxHQUFHLENBQUMsR0FBRyxHQUFHLEVBQUUsQ0FBQyxHQUFHLElBQUksR0FBRyxJQUFJLEdBQUcsS0FBSyxHQUFHLFVBQVUsQ0FBQztZQUNwRCxHQUFHLEdBQUcsQ0FBQyxHQUFHLEdBQUcsRUFBRSxDQUFDLEdBQUcsSUFBSSxHQUFHLElBQUksR0FBRyxLQUFLLEdBQUcsVUFBVSxDQUFDO1lBQ3BELFVBQVUsSUFBSSxJQUFJLENBQUMsSUFBSSxDQUFDLEdBQUcsR0FBRyxHQUFHLEdBQUcsR0FBRyxHQUFHLEdBQUcsQ0FBQyxDQUFDO1lBQy9DLEdBQUcsSUFBSSxJQUFJLENBQUM7WUFDWixHQUFHLElBQUksSUFBSSxDQUFDO1lBQ1osSUFBSSxJQUFJLEtBQUssQ0FBQztZQUNkLElBQUksSUFBSSxLQUFLLENBQUM7WUFDZCxVQUFVLElBQUksSUFBSSxDQUFDLElBQUksQ0FBQyxHQUFHLEdBQUcsR0FBRyxHQUFHLEdBQUcsR0FBRyxHQUFH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QUVELGlCQUFpQixDQUFFLENBQVMsRUFBRSxJQUFtQixFQUFFLENBQVMsRUFBRSxHQUFrQixFQUFFLENBQVM7UUFDMUYsSUFBSSxFQUFFLEdBQUcsSUFBSSxDQUFDLENBQUMsQ0FBQyxFQUFFLEVBQUUsR0FBRyxJQUFJLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxFQUFFLEVBQUUsR0FBRyxJQUFJLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLEVBQUUsRUFBRSxFQUFFLEdBQUcsSUFBSSxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxFQUFFLEVBQUUsQ0FBQyxHQUFHLElBQUksQ0FBQyxLQUFLLENBQUMsRUFBRSxFQUFFLEVBQUUsQ0FBQyxDQUFDO1FBQ3pHLEdBQUcsQ0FBQyxDQUFDLENBQUMsR0FBRyxFQUFFLEdBQUcsQ0FBQyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsQ0FBQyxDQUFDLENBQUM7UUFDOUIsR0FBRyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxFQUFFLEdBQUcsQ0FBQyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsQ0FBQyxDQUFDLENBQUM7UUFDbEMsR0FBRyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUM7SUFDaEIsQ0FBQztJQUVELGdCQUFnQixDQUFFLENBQVMsRUFBRSxJQUFtQixFQUFFLENBQVMsRUFBRSxHQUFrQixFQUFFLENBQVM7UUFDekYsSUFBSSxFQUFFLEdBQUcsSUFBSSxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsRUFBRSxFQUFFLEdBQUcsSUFBSSxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsRUFBRSxFQUFFLEdBQUcsRUFBRSxHQUFHLElBQUksQ0FBQyxDQUFDLENBQUMsRUFBRSxFQUFFLEdBQUcsRUFBRSxHQUFHLElBQUksQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxHQUFHLElBQUksQ0FBQyxLQUFLLENBQUMsRUFBRSxFQUFFLEVBQUUsQ0FBQyxDQUFDO1FBQ3pHLEdBQUcsQ0FBQyxDQUFDLENBQUMsR0FBRyxFQUFFLEdBQUcsQ0FBQyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsQ0FBQyxDQUFDLENBQUM7UUFDOUIsR0FBRyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxFQUFFLEdBQUcsQ0FBQyxHQUFHLElBQUksQ0FBQyxHQUFHLENBQUMsQ0FBQyxDQUFDLENBQUM7UUFDbEMsR0FBRyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUM7SUFDaEIsQ0FBQztJQUVELGdCQUFnQixDQUFFLENBQVMsRUFBRSxFQUFVLEVBQUUsRUFBVSxFQUFFLEdBQVcsRUFBRSxHQUFXLEVBQUUsR0FBVyxFQUFFLEdBQVcsRUFBRSxFQUFVLEVBQUUsRUFBVSxFQUM5SCxHQUFrQixFQUFFLENBQVMsRUFBRSxRQUFpQjtRQUNoRCxJQUFJLENBQUMsSUFBSSxDQUFDLElBQUksS0FBSyxDQUFDLENBQUMsQ0FBQyxFQUFFLENBQUM7WUFDeEIsR0FBRyxDQUFDLENBQUMsQ0FBQyxHQUFHLEVBQUUsQ0FBQztZQUNaLEdBQUcsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLEdBQUcsRUFBRSxDQUFDO1lBQ2hCLEdBQUcsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxHQUFHLEdBQUcsRUFBRSxFQUFFLEdBQUcsR0FBRyxFQUFFLENBQUMsQ0FBQztZQUM1QyxPQUFPO1FBQ1IsQ0FBQztRQUNELElBQUksRUFBRSxHQUFHLENBQUMsR0FBRyxDQUFDLEVBQUUsR0FBRyxHQUFHLEVBQUUsR0FBRyxDQUFDLEVBQUUsQ0FBQyxHQUFHLENBQUMsR0FBRyxDQUFDLEVBQUUsRUFBRSxHQUFHLENBQUMsR0FBRyxDQUFDLEVBQUUsR0FBRyxHQUFHLEVBQUUsR0FBRyxDQUFDLENBQUM7UUFDbEUsSUFBSSxFQUFFLEdBQUcsQ0FBQyxHQUFHLENBQUMsRUFBRSxHQUFHLEdBQUcsRUFBRSxHQUFHLENBQUMsRUFBRSxJQUFJLEdBQUcsQ0FBQyxHQUFHLEdBQUcsRUFBRSxJQUFJLEdBQUcsR0FBRyxHQUFHLENBQUMsQ0FBQztRQUM3RCxJQUFJLENBQUMsR0FBRyxFQUFFLEdBQUcsR0FBRyxHQUFHLEdBQUcsR0FBRyxJQUFJLEdBQUcsR0FBRyxHQUFHLElBQUksR0FBRyxFQUFFLEdBQUcsR0FBRyxFQUFFLENBQUMsR0FBRyxFQUFFLEdBQUcsR0FBRyxHQUFHLEdBQUcsR0FBRyxJQUFJLEdBQUcsR0FBRyxHQUFHLElBQUksR0FBRyxFQUFFLEdBQUcsR0FBRyxDQUFDO1FBQ3pHLEdBQUcsQ0FBQyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUM7UUFDWCxHQUFHLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQztRQUNmLElBQUksUUFBUSxFQUFFLENBQUM7WUFDZCxJQUFJLENBQUMsR0FBRyxLQUFLO2dCQUNaLEdBQUcsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxHQUFHLEdBQUcsRUFBRSxFQUFFLEdBQUcsR0FBRyxFQUFFLENBQUMsQ0FBQzs7Z0JBRTVDLEdBQUcsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLEdBQUcsSUFBSSxDQUFDLEtBQUssQ0FBQyxDQUFDLEdBQUcsQ0FBQyxFQUFFLEdBQUcsRUFBRSxHQUFHLEdBQUcsR0FBRyxFQUFFLEdBQUcsQ0FBQyxHQUFHLEdBQUcsR0FBRyxFQUFFLENBQUMsRUFBRSxDQUFDLEdBQUcsQ0FBQyxFQUFFLEdBQUcsRUFBRSxHQUFHLEdBQUcsR0FBRyxFQUFFLEdBQUcsQ0FBQyxHQUFHLEdBQUcsR0FBRyxFQUFFLENBQUMsQ0FBQyxDQUFDO1FBQzVHLENBQUM7SUFDRixDQUFDIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBBcHJpbCA1LCAyMDI1LiBSZXBsYWNlcyBhbGwgcHJpb3IgdmVyc2lvbnMuXG4gKlxuICogQ29weXJpZ2h0IChjKSAyMDEzLTIwMjUsIEVzb3RlcmljIFNvZnR3YXJlIExMQ1xuICpcbiAqIEludGVncmF0aW9uIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlIG9yIG90aGVyd2lzZSBjcmVhdGluZ1xuICogZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgaXMgcGVybWl0dGVkIHVuZGVyIHRoZSB0ZXJtcyBhbmRcbiAqIGNvbmRpdGlvbnMgb2YgU2VjdGlvbiAyIG9mIHRoZSBTcGluZSBFZGl0b3IgTGljZW5zZSBBZ3JlZW1lbnQ6XG4gKiBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtZWRpdG9yLWxpY2Vuc2VcbiAqXG4gKiBPdGhlcndpc2UsIGl0IGlzIHBlcm1pdHRlZCB0byBpbnRlZ3JhdGUgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmVcbiAqIG9yIG90aGVyd2lzZSBjcmVhdGUgZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgKGNvbGxlY3RpdmVseSxcbiAqIFwiUHJvZHVjdHNcIiksIHByb3ZpZGVkIHRoYXQgZWFjaCB1c2VyIG9mIHRoZSBQcm9kdWN0cyBtdXN0IG9idGFpbiB0aGVpciBvd25cbiAqIFNwaW5lIEVkaXRvciBsaWNlbnNlIGFuZCByZWRpc3RyaWJ1dGlvbiBvZiB0aGUgUHJvZHVjdHMgaW4gYW55IGZvcm0gbXVzdFxuICogaW5jbHVkZSB0aGlzIGxpY2Vuc2UgYW5kIGNvcHlyaWdodCBub3RpY2UuXG4gKlxuICogVEhFIFNQSU5FIFJVTlRJTUVTIEFSRSBQUk9WSURFRCBCWSBFU09URVJJQyBTT0ZUV0FSRSBMTEMgXCJBUyBJU1wiIEFORCBBTllcbiAqIEVYUFJFU1MgT1IgSU1QTElFRCBXQVJSQU5USUVTLCBJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgVEhFIElNUExJRURcbiAqIFdBUlJBTlRJRVMgT0YgTUVSQ0hBTlRBQklMSVRZIEFORCBGSVRORVNTIEZPUiBBIFBBUlRJQ1VMQVIgUFVSUE9TRSBBUkVcbiAqIERJU0NMQUlNRUQuIElOIE5PIEVWRU5UIFNIQUxMIEVTT1RFUklDIFNPRlRXQVJFIExMQyBCRSBMSUFCTEUgRk9SIEFOWVxuICogRElSRUNULCBJTkRJUkVDVCwgSU5DSURFTlRBTCwgU1BFQ0lBTCwgRVhFTVBMQVJZLCBPUiBDT05TRVFVRU5USUFMIERBTUFHRVNcbiAqIChJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgUFJPQ1VSRU1FTlQgT0YgU1VCU1RJVFVURSBHT09EUyBPUiBTRVJWSUNFUyxcbiAqIEJVU0lORVNTIElOVEVSUlVQVElPTiwgT1IgTE9TUyBPRiBVU0UsIERBVEEsIE9SIFBST0ZJVFMpIEhPV0VWRVIgQ0FVU0VEIEFORFxuICogT04gQU5ZIFRIRU9SWSBPRiBMSUFCSUxJVFksIFdIRVRIRVIgSU4gQ09OVFJBQ1QsIFNUUklDVCBMSUFCSUxJVFksIE9SIFRPUlRcbiAqIChJTkNMVURJTkcgTkVHTElHRU5DRSBPUiBPVEhFUldJU0UpIEFSSVNJTkcgSU4gQU5ZIFdBWSBPVVQgT0YgVEhFIFVTRSBPRlxuICogVEhFIFNQSU5FIFJVTlRJTUVTLCBFVkVOIElGIEFEVklTRUQgT0YgVEhFIFBPU1NJQklMSVRZIE9GIFNVQ0ggREFNQUdFLlxuICoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqL1xuXG5pbXBvcnQgeyBQYXRoQXR0YWNobWVudCB9IGZyb20gXCIuL2F0dGFjaG1lbnRzL1BhdGhBdHRhY2htZW50LmpzXCI7XG5pbXBvcnQgeyBCb25lIH0gZnJvbSBcIi4vQm9uZS5qc1wiO1xuaW1wb3J0IHsgUGF0aENvbnN0cmFpbnREYXRhLCBSb3RhdGVNb2RlLCBTcGFjaW5nTW9kZSwgUG9zaXRpb25Nb2RlIH0gZnJvbSBcIi4vUGF0aENvbnN0cmFpbnREYXRhLmpzXCI7XG5pbXBvcnQgeyBQaHlzaWNzLCBTa2VsZXRvbiB9IGZyb20gXCIuL1NrZWxldG9uLmpzXCI7XG5pbXBvcnQgeyBTbG90IH0gZnJvbSBcIi4vU2xvdC5qc1wiO1xuaW1wb3J0IHsgVXBkYXRhYmxlIH0gZnJvbSBcIi4vVXBkYXRhYmxlLmpzXCI7XG5pbXBvcnQgeyBVdGlscywgTWF0aFV0aWxzIH0gZnJvbSBcIi4vVXRpbHMuanNcIjtcblxuXG4vKiogU3RvcmVzIHRoZSBjdXJyZW50IHBvc2UgZm9yIGEgcGF0aCBjb25zdHJhaW50LiBBIHBhdGggY29uc3RyYWludCBhZGp1c3RzIHRoZSByb3RhdGlvbiwgdHJhbnNsYXRpb24sIGFuZCBzY2FsZSBvZiB0aGVcbiAqIGNvbnN0cmFpbmVkIGJvbmVzIHNvIHRoZXkgZm9sbG93IGEge0BsaW5rIFBhdGhBdHRhY2htZW50fS5cbiAqXG4gKiBTZWUgW1BhdGggY29uc3RyYWludHNdKGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1wYXRoLWNvbnN0cmFpbnRzKSBpbiB0aGUgU3BpbmUgVXNlciBHdWlkZS4gKi9cbmV4cG9ydCBjbGFzcyBQYXRoQ29uc3RyYWludCBpbXBsZW1lbnRzIFVwZGF0YWJsZSB7XG5cdHN0YXRpYyBOT05FID0gLTE7IHN0YXRpYyBCRUZPUkUgPSAtMjsgc3RhdGljIEFGVEVSID0gLTM7XG5cdHN0YXRpYyBlcHNpbG9uID0gMC4wMDAwMTtcblxuXHQvKiogVGhlIHBhdGggY29uc3RyYWludCdzIHNldHVwIHBvc2UgZGF0YS4gKi9cblx0ZGF0YTogUGF0aENvbnN0cmFpbnREYXRhO1xuXG5cdC8qKiBUaGUgYm9uZXMgdGhhdCB3aWxsIGJlIG1vZGlmaWVkIGJ5IHRoaXMgcGF0aCBjb25zdHJhaW50LiAqL1xuXHRib25lczogQXJyYXk8Qm9uZT47XG5cblx0LyoqIFRoZSBzbG90IHdob3NlIHBhdGggYXR0YWNobWVudCB3aWxsIGJlIHVzZWQgdG8gY29uc3RyYWluZWQgdGhlIGJvbmVzLiAqL1xuXHR0YXJnZXQ6IFNsb3Q7XG5cblx0LyoqIFRoZSBwb3NpdGlvbiBhbG9uZyB0aGUgcGF0aC4gKi9cblx0cG9zaXRpb24gPSAwO1xuXG5cdC8qKiBUaGUgc3BhY2luZyBiZXR3ZWVuIGJvbmVzLiAqL1xuXHRzcGFjaW5nID0gMDtcblxuXHRtaXhSb3RhdGUgPSAwO1xuXG5cdG1peFggPSAwO1xuXG5cdG1peFkgPSAwO1xuXG5cdHNwYWNlcyA9IG5ldyBBcnJheTxudW1iZXI+KCk7IHBvc2l0aW9ucyA9IG5ldyBBcnJheTxudW1iZXI+KCk7XG5cdHdvcmxkID0gbmV3IEFycmF5PG51bWJlcj4oKTsgY3VydmVzID0gbmV3IEFycmF5PG51bWJlcj4oKTsgbGVuZ3RocyA9IG5ldyBBcnJheTxudW1iZXI+KCk7XG5cdHNlZ21lbnRzID0gbmV3IEFycmF5PG51bWJlcj4oKTtcblxuXHRhY3RpdmUgPSBmYWxzZTtcblxuXHRjb25zdHJ1Y3RvciAoZGF0YTogUGF0aENvbnN0cmFpbnREYXRhLCBza2VsZXRvbjogU2tlbGV0b24pIHtcblx0XHRpZiAoIWRhdGEpIHRocm93IG5ldyBFcnJvcihcImRhdGEgY2Fubm90IGJlIG51bGwuXCIpO1xuXHRcdGlmICghc2tlbGV0b24pIHRocm93IG5ldyBFcnJvcihcInNrZWxldG9uIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHR0aGlzLmRhdGEgPSBkYXRhO1xuXG5cdFx0dGhpcy5ib25lcyA9IG5ldyBBcnJheTxCb25lPigpO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gZGF0YS5ib25lcy5sZW5ndGg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBib25lID0gc2tlbGV0b24uZmluZEJvbmUoZGF0YS5ib25lc1tpXS5uYW1lKTtcblx0XHRcdGlmICghYm9uZSkgdGhyb3cgbmV3IEVycm9yKGBDb3VsZG4ndCBmaW5kIGJvbmUgJHtkYXRhLmJvbmVzW2ldLm5hbWV9LmApO1xuXHRcdFx0dGhpcy5ib25lcy5wdXNoKGJvbmUpO1xuXHRcdH1cblx0XHRsZXQgdGFyZ2V0ID0gc2tlbGV0b24uZmluZFNsb3QoZGF0YS50YXJnZXQubmFtZSk7XG5cdFx0aWYgKCF0YXJnZXQpIHRocm93IG5ldyBFcnJvcihgQ291bGRuJ3QgZmluZCB0YXJnZXQgYm9uZSAke2RhdGEudGFyZ2V0Lm5hbWV9YCk7XG5cdFx0dGhpcy50YXJnZXQgPSB0YXJnZXQ7XG5cblx0XHR0aGlzLnBvc2l0aW9uID0gZGF0YS5wb3NpdGlvbjtcblx0XHR0aGlzLnNwYWNpbmcgPSBkYXRhLnNwYWNpbmc7XG5cdFx0dGhpcy5taXhSb3RhdGUgPSBkYXRhLm1peFJvdGF0ZTtcblx0XHR0aGlzLm1peFggPSBkYXRhLm1peFg7XG5cdFx0dGhpcy5taXhZID0gZGF0YS5taXhZO1xuXHR9XG5cblx0aXNBY3RpdmUgKCkge1xuXHRcdHJldHVybiB0aGlzLmFjdGl2ZTtcblx0fVxuXG5cdHNldFRvU2V0dXBQb3NlICgpIHtcblx0XHRjb25zdCBkYXRhID0gdGhpcy5kYXRhO1xuXHRcdHRoaXMucG9zaXRpb24gPSBkYXRhLnBvc2l0aW9uO1xuXHRcdHRoaXMuc3BhY2luZyA9IGRhdGEuc3BhY2luZztcblx0XHR0aGlzLm1peFJvdGF0ZSA9IGRhdGEubWl4Um90YXRlO1xuXHRcdHRoaXMubWl4WCA9IGRhdGEubWl4WDtcblx0XHR0aGlzLm1peFkgPSBkYXRhLm1peFk7XG5cdH1cblxuXHR1cGRhdGUgKHBoeXNpY3M6IFBoeXNpY3MpIHtcblx0XHRsZXQgYXR0YWNobWVudCA9IHRoaXMudGFyZ2V0LmdldEF0dGFjaG1lbnQoKTtcblx0XHRpZiAoIShhdHRhY2htZW50IGluc3RhbmNlb2YgUGF0aEF0dGFjaG1lbnQpKSByZXR1cm47XG5cblx0XHRsZXQgbWl4Um90YXRlID0gdGhpcy5taXhSb3RhdGUsIG1peFggPSB0aGlzLm1peFgsIG1peFkgPSB0aGlzLm1peFk7XG5cdFx0aWYgKG1peFJvdGF0ZSA9PSAwICYmIG1peFggPT0gMCAmJiBtaXhZID09IDApIHJldHVybjtcblxuXHRcdGxldCBkYXRhID0gdGhpcy5kYXRhO1xuXHRcdGxldCB0YW5nZW50cyA9IGRhdGEucm90YXRlTW9kZSA9PSBSb3RhdGVNb2RlLlRhbmdlbnQsIHNjYWxlID0gZGF0YS5yb3RhdGVNb2RlID09IFJvdGF0ZU1vZGUuQ2hhaW5TY2FsZTtcblxuXHRcdGxldCBib25lcyA9IHRoaXMuYm9uZXM7XG5cdFx0bGV0IGJvbmVDb3VudCA9IGJvbmVzLmxlbmd0aCwgc3BhY2VzQ291bnQgPSB0YW5nZW50cyA/IGJvbmVDb3VudCA6IGJvbmVDb3VudCArIDE7XG5cdFx0bGV0IHNwYWNlcyA9IFV0aWxzLnNldEFycmF5U2l6ZSh0aGlzLnNwYWNlcywgc3BhY2VzQ291bnQpLCBsZW5ndGhzOiBBcnJheTxudW1iZXI+ID0gc2NhbGUgPyB0aGlzLmxlbmd0aHMgPSBVdGlscy5zZXRBcnJheVNpemUodGhpcy5sZW5ndGhzLCBib25lQ291bnQpIDogW107XG5cdFx0bGV0IHNwYWNpbmcgPSB0aGlzLnNwYWNpbmc7XG5cblx0XHRzd2l0Y2ggKGRhdGEuc3BhY2luZ01vZGUpIHtcblx0XHRcdGNhc2UgU3BhY2luZ01vZGUuUGVyY2VudDpcblx0XHRcdFx0aWYgKHNjYWxlKSB7XG5cdFx0XHRcdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBzcGFjZXNDb3VudCAtIDE7IGkgPCBuOyBpKyspIHtcblx0XHRcdFx0XHRcdGxldCBib25lID0gYm9uZXNbaV07XG5cdFx0XHRcdFx0XHRsZXQgc2V0dXBMZW5ndGggPSBib25lLmRhdGEubGVuZ3RoO1xuXHRcdFx0XHRcdFx0bGV0IHggPSBzZXR1cExlbmd0aCAqIGJvbmUuYSwgeSA9IHNldHVwTGVuZ3RoICogYm9uZS5jO1xuXHRcdFx0XHRcdFx0bGVuZ3Roc1tpXSA9IE1hdGguc3FydCh4ICogeCArIHkgKiB5KTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdH1cblx0XHRcdFx0VXRpbHMuYXJyYXlGaWxsKHNwYWNlcywgMSwgc3BhY2VzQ291bnQsIHNwYWNpbmcpO1xuXHRcdFx0XHRicmVhaztcblx0XHRcdGNhc2UgU3BhY2luZ01vZGUuUHJvcG9ydGlvbmFsOlxuXHRcdFx0XHRsZXQgc3VtID0gMDtcblx0XHRcdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBzcGFjZXNDb3VudCAtIDE7IGkgPCBuOykge1xuXHRcdFx0XHRcdGxldCBib25lID0gYm9uZXNbaV07XG5cdFx0XHRcdFx0bGV0IHNldHVwTGVuZ3RoID0gYm9uZS5kYXRhLmxlbmd0aDtcblx0XHRcdFx0XHRpZiAoc2V0dXBMZW5ndGggPCBQYXRoQ29uc3RyYWludC5lcHNpbG9uKSB7XG5cdFx0XHRcdFx0XHRpZiAoc2NhbGUpIGxlbmd0aHNbaV0gPSAwO1xuXHRcdFx0XHRcdFx0c3BhY2VzWysraV0gPSBzcGFjaW5nO1xuXHRcdFx0XHRcdH0gZWxzZSB7XG5cdFx0XHRcdFx0XHRsZXQgeCA9IHNldHVwTGVuZ3RoICogYm9uZS5hLCB5ID0gc2V0dXBMZW5ndGggKiBib25lLmM7XG5cdFx0XHRcdFx0XHRsZXQgbGVuZ3RoID0gTWF0aC5zcXJ0KHggKiB4ICsgeSAqIHkpO1xuXHRcdFx0XHRcdFx0aWYgKHNjYWxlKSBsZW5ndGhzW2ldID0gbGVuZ3RoO1xuXHRcdFx0XHRcdFx0c3BhY2VzWysraV0gPSBsZW5ndGg7XG5cdFx0XHRcdFx0XHRzdW0gKz0gbGVuZ3RoO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0fVxuXHRcdFx0XHRpZiAoc3VtID4gMCkge1xuXHRcdFx0XHRcdHN1bSA9IHNwYWNlc0NvdW50IC8gc3VtICogc3BhY2luZztcblx0XHRcdFx0XHRmb3IgKGxldCBpID0gMTsgaSA8IHNwYWNlc0NvdW50OyBpKyspXG5cdFx0XHRcdFx0XHRzcGFjZXNbaV0gKj0gc3VtO1xuXHRcdFx0XHR9XG5cdFx0XHRcdGJyZWFrO1xuXHRcdFx0ZGVmYXVsdDpcblx0XHRcdFx0bGV0IGxlbmd0aFNwYWNpbmcgPSBkYXRhLnNwYWNpbmdNb2RlID09IFNwYWNpbmdNb2RlLkxlbmd0aDtcblx0XHRcdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSBzcGFjZXNDb3VudCAtIDE7IGkgPCBuOykge1xuXHRcdFx0XHRcdGxldCBib25lID0gYm9uZXNbaV07XG5cdFx0XHRcdFx0bGV0IHNldHVwTGVuZ3RoID0gYm9uZS5kYXRhLmxlbmd0aDtcblx0XHRcdFx0XHRpZiAoc2V0dXBMZW5ndGggPCBQYXRoQ29uc3RyYWludC5lcHNpbG9uKSB7XG5cdFx0XHRcdFx0XHRpZiAoc2NhbGUpIGxlbmd0aHNbaV0gPSAwO1xuXHRcdFx0XHRcdFx0c3BhY2VzWysraV0gPSBzcGFjaW5nO1xuXHRcdFx0XHRcdH0gZWxzZSB7XG5cdFx0XHRcdFx0XHRsZXQgeCA9IHNldHVwTGVuZ3RoICogYm9uZS5hLCB5ID0gc2V0dXBMZW5ndGggKiBib25lLmM7XG5cdFx0XHRcdFx0XHRsZXQgbGVuZ3RoID0gTWF0aC5zcXJ0KHggKiB4ICsgeSAqIHkpO1xuXHRcdFx0XHRcdFx0aWYgKHNjYWxlKSBsZW5ndGhzW2ldID0gbGVuZ3RoO1xuXHRcdFx0XHRcdFx0c3BhY2VzWysraV0gPSAobGVuZ3RoU3BhY2luZyA/IHNldHVwTGVuZ3RoICsgc3BhY2luZyA6IHNwYWNpbmcpICogbGVuZ3RoIC8gc2V0dXBMZW5ndGg7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHR9XG5cdFx0fVxuXG5cdFx0bGV0IHBvc2l0aW9ucyA9IHRoaXMuY29tcHV0ZVdvcmxkUG9zaXRpb25zKDxQYXRoQXR0YWNobWVudD5hdHRhY2htZW50LCBzcGFjZXNDb3VudCwgdGFuZ2VudHMpO1xuXHRcdGxldCBib25lWCA9IHBvc2l0aW9uc1swXSwgYm9uZVkgPSBwb3NpdGlvbnNbMV0sIG9mZnNldFJvdGF0aW9uID0gZGF0YS5vZmZzZXRSb3RhdGlvbjtcblx0XHRsZXQgdGlwID0gZmFsc2U7XG5cdFx0aWYgKG9mZnNldFJvdGF0aW9uID09IDApXG5cdFx0XHR0aXAgPSBkYXRhLnJvdGF0ZU1vZGUgPT0gUm90YXRlTW9kZS5DaGFpbjtcblx0XHRlbHNlIHtcblx0XHRcdHRpcCA9IGZhbHNlO1xuXHRcdFx0bGV0IHAgPSB0aGlzLnRhcmdldC5ib25lO1xuXHRcdFx0b2Zmc2V0Um90YXRpb24gKj0gcC5hICogcC5kIC0gcC5iICogcC5jID4gMCA/IE1hdGhVdGlscy5kZWdSYWQgOiAtTWF0aFV0aWxzLmRlZ1JhZDtcblx0XHR9XG5cdFx0Zm9yIChsZXQgaSA9IDAsIHAgPSAzOyBpIDwgYm9uZUNvdW50OyBpKyssIHAgKz0gMykge1xuXHRcdFx0bGV0IGJvbmUgPSBib25lc1tpXTtcblx0XHRcdGJvbmUud29ybGRYICs9IChib25lWCAtIGJvbmUud29ybGRYKSAqIG1peFg7XG5cdFx0XHRib25lLndvcmxkWSArPSAoYm9uZVkgLSBib25lLndvcmxkWSkgKiBtaXhZO1xuXHRcdFx0bGV0IHggPSBwb3NpdGlvbnNbcF0sIHkgPSBwb3NpdGlvbnNbcCArIDFdLCBkeCA9IHggLSBib25lWCwgZHkgPSB5IC0gYm9uZVk7XG5cdFx0XHRpZiAoc2NhbGUpIHtcblx0XHRcdFx0bGV0IGxlbmd0aCA9IGxlbmd0aHNbaV07XG5cdFx0XHRcdGlmIChsZW5ndGggIT0gMCkge1xuXHRcdFx0XHRcdGxldCBzID0gKE1hdGguc3FydChkeCAqIGR4ICsgZHkgKiBkeSkgLyBsZW5ndGggLSAxKSAqIG1peFJvdGF0ZSArIDE7XG5cdFx0XHRcdFx0Ym9uZS5hICo9IHM7XG5cdFx0XHRcdFx0Ym9uZS5jICo9IHM7XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHRcdGJvbmVYID0geDtcblx0XHRcdGJvbmVZID0geTtcblx0XHRcdGlmIChtaXhSb3RhdGUgPiAwKSB7XG5cdFx0XHRcdGxldCBhID0gYm9uZS5hLCBiID0gYm9uZS5iLCBjID0gYm9uZS5jLCBkID0gYm9uZS5kLCByID0gMCwgY29zID0gMCwgc2luID0gMDtcblx0XHRcdFx0aWYgKHRhbmdlbnRzKVxuXHRcdFx0XHRcdHIgPSBwb3NpdGlvbnNbcCAtIDFdO1xuXHRcdFx0XHRlbHNlIGlmIChzcGFjZXNbaSArIDFdID09IDApXG5cdFx0XHRcdFx0ciA9IHBvc2l0aW9uc1twICsgMl07XG5cdFx0XHRcdGVsc2Vcblx0XHRcdFx0XHRyID0gTWF0aC5hdGFuMihkeSwgZHgpO1xuXHRcdFx0XHRyIC09IE1hdGguYXRhbjIoYywgYSk7XG5cdFx0XHRcdGlmICh0aXApIHtcblx0XHRcdFx0XHRjb3MgPSBNYXRoLmNvcyhyKTtcblx0XHRcdFx0XHRzaW4gPSBNYXRoLnNpbihyKTtcblx0XHRcdFx0XHRsZXQgbGVuZ3RoID0gYm9uZS5kYXRhLmxlbmd0aDtcblx0XHRcdFx0XHRib25lWCArPSAobGVuZ3RoICogKGNvcyAqIGEgLSBzaW4gKiBjKSAtIGR4KSAqIG1peFJvdGF0ZTtcblx0XHRcdFx0XHRib25lWSArPSAobGVuZ3RoICogKHNpbiAqIGEgKyBjb3MgKiBjKSAtIGR5KSAqIG1peFJvdGF0ZTtcblx0XHRcdFx0fSBlbHNlIHtcblx0XHRcdFx0XHRyICs9IG9mZnNldFJvdGF0aW9uO1xuXHRcdFx0XHR9XG5cdFx0XHRcdGlmIChyID4gTWF0aFV0aWxzLlBJKVxuXHRcdFx0XHRcdHIgLT0gTWF0aFV0aWxzLlBJMjtcblx0XHRcdFx0ZWxzZSBpZiAociA8IC1NYXRoVXRpbHMuUEkpIC8vXG5cdFx0XHRcdFx0ciArPSBNYXRoVXRpbHMuUEkyO1xuXHRcdFx0XHRyICo9IG1peFJvdGF0ZTtcblx0XHRcdFx0Y29zID0gTWF0aC5jb3Mocik7XG5cdFx0XHRcdHNpbiA9IE1hdGguc2luKHIpO1xuXHRcdFx0XHRib25lLmEgPSBjb3MgKiBhIC0gc2luICogYztcblx0XHRcdFx0Ym9uZS5iID0gY29zICogYiAtIHNpbiAqIGQ7XG5cdFx0XHRcdGJvbmUuYyA9IHNpbiAqIGEgKyBjb3MgKiBjO1xuXHRcdFx0XHRib25lLmQgPSBzaW4gKiBiICsgY29zICogZDtcblx0XHRcdH1cblx0XHRcdGJvbmUudXBkYXRlQXBwbGllZFRyYW5zZm9ybSgpO1xuXHRcdH1cblx0fVxuXG5cdGNvbXB1dGVXb3JsZFBvc2l0aW9ucyAocGF0aDogUGF0aEF0dGFjaG1lbnQsIHNwYWNlc0NvdW50OiBudW1iZXIsIHRhbmdlbnRzOiBib29sZWFuKSB7XG5cdFx0bGV0IHRhcmdldCA9IHRoaXMudGFyZ2V0O1xuXHRcdGxldCBwb3NpdGlvbiA9IHRoaXMucG9zaXRpb247XG5cdFx0bGV0IHNwYWNlcyA9IHRoaXMuc3BhY2VzLCBvdXQgPSBVdGlscy5zZXRBcnJheVNpemUodGhpcy5wb3NpdGlvbnMsIHNwYWNlc0NvdW50ICogMyArIDIpLCB3b3JsZDogQXJyYXk8bnVtYmVyPiA9IHRoaXMud29ybGQ7XG5cdFx0bGV0IGNsb3NlZCA9IHBhdGguY2xvc2VkO1xuXHRcdGxldCB2ZXJ0aWNlc0xlbmd0aCA9IHBhdGgud29ybGRWZXJ0aWNlc0xlbmd0aCwgY3VydmVDb3VudCA9IHZlcnRpY2VzTGVuZ3RoIC8gNiwgcHJldkN1cnZlID0gUGF0aENvbnN0cmFpbnQuTk9ORTtcblxuXHRcdGlmICghcGF0aC5jb25zdGFudFNwZWVkKSB7XG5cdFx0XHRsZXQgbGVuZ3RocyA9IHBhdGgubGVuZ3Rocztcblx0XHRcdGN1cnZlQ291bnQgLT0gY2xvc2VkID8gMSA6IDI7XG5cdFx0XHRsZXQgcGF0aExlbmd0aCA9IGxlbmd0aHNbY3VydmVDb3VudF07XG5cdFx0XHRpZiAodGhpcy5kYXRhLnBvc2l0aW9uTW9kZSA9PSBQb3NpdGlvbk1vZGUuUGVyY2VudCkgcG9zaXRpb24gKj0gcGF0aExlbmd0aDtcblxuXHRcdFx0bGV0IG11bHRpcGxpZXI7XG5cdFx0XHRzd2l0Y2ggKHRoaXMuZGF0YS5zcGFjaW5nTW9kZSkge1xuXHRcdFx0XHRjYXNlIFNwYWNpbmdNb2RlLlBlcmNlbnQ6XG5cdFx0XHRcdFx0bXVsdGlwbGllciA9IHBhdGhMZW5ndGg7XG5cdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdGNhc2UgU3BhY2luZ01vZGUuUHJvcG9ydGlvbmFsOlxuXHRcdFx0XHRcdG11bHRpcGxpZXIgPSBwYXRoTGVuZ3RoIC8gc3BhY2VzQ291bnQ7XG5cdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdGRlZmF1bHQ6XG5cdFx0XHRcdFx0bXVsdGlwbGllciA9IDE7XG5cdFx0XHR9XG5cdFx0XHR3b3JsZCA9IFV0aWxzLnNldEFycmF5U2l6ZSh0aGlzLndvcmxkLCA4KTtcblx0XHRcdGZvciAobGV0IGkgPSAwLCBvID0gMCwgY3VydmUgPSAwOyBpIDwgc3BhY2VzQ291bnQ7IGkrKywgbyArPSAzKSB7XG5cdFx0XHRcdGxldCBzcGFjZSA9IHNwYWNlc1tpXSAqIG11bHRpcGxpZXI7XG5cdFx0XHRcdHBvc2l0aW9uICs9IHNwYWNlO1xuXHRcdFx0XHRsZXQgcCA9IHBvc2l0aW9uO1xuXG5cdFx0XHRcdGlmIChjbG9zZWQpIHtcblx0XHRcdFx0XHRwICU9IHBhdGhMZW5ndGg7XG5cdFx0XHRcdFx0aWYgKHAgPCAwKSBwICs9IHBhdGhMZW5ndGg7XG5cdFx0XHRcdFx0Y3VydmUgPSAwO1xuXHRcdFx0XHR9IGVsc2UgaWYgKHAgPCAwKSB7XG5cdFx0XHRcdFx0aWYgKHByZXZDdXJ2ZSAhPSBQYXRoQ29uc3RyYWludC5CRUZPUkUpIHtcblx0XHRcdFx0XHRcdHByZXZDdXJ2ZSA9IFBhdGhDb25zdHJhaW50LkJFRk9SRTtcblx0XHRcdFx0XHRcdHBhdGguY29tcHV0ZVdvcmxkVmVydGljZXModGFyZ2V0LCAyLCA0LCB3b3JsZCwgMCwgMik7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHRcdHRoaXMuYWRkQmVmb3JlUG9zaXRpb24ocCwgd29ybGQsIDAsIG91dCwgbyk7XG5cdFx0XHRcdFx0Y29udGludWU7XG5cdFx0XHRcdH0gZWxzZSBpZiAocCA+IHBhdGhMZW5ndGgpIHtcblx0XHRcdFx0XHRpZiAocHJldkN1cnZlICE9IFBhdGhDb25zdHJhaW50LkFGVEVSKSB7XG5cdFx0XHRcdFx0XHRwcmV2Q3VydmUgPSBQYXRoQ29uc3RyYWludC5BRlRFUjtcblx0XHRcdFx0XHRcdHBhdGguY29tcHV0ZVdvcmxkVmVydGljZXModGFyZ2V0LCB2ZXJ0aWNlc0xlbmd0aCAtIDYsIDQsIHdvcmxkLCAwLCAyKTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0dGhpcy5hZGRBZnRlclBvc2l0aW9uKHAgLSBwYXRoTGVuZ3RoLCB3b3JsZCwgMCwgb3V0LCBvKTtcblx0XHRcdFx0XHRjb250aW51ZTtcblx0XHRcdFx0fVxuXG5cdFx0XHRcdC8vIERldGVybWluZSBjdXJ2ZSBjb250YWluaW5nIHBvc2l0aW9uLlxuXHRcdFx0XHRmb3IgKDsgOyBjdXJ2ZSsrKSB7XG5cdFx0XHRcdFx0bGV0IGxlbmd0aCA9IGxlbmd0aHNbY3VydmVdO1xuXHRcdFx0XHRcdGlmIChwID4gbGVuZ3RoKSBjb250aW51ZTtcblx0XHRcdFx0XHRpZiAoY3VydmUgPT0gMClcblx0XHRcdFx0XHRcdHAgLz0gbGVuZ3RoO1xuXHRcdFx0XHRcdGVsc2Uge1xuXHRcdFx0XHRcdFx0bGV0IHByZXYgPSBsZW5ndGhzW2N1cnZlIC0gMV07XG5cdFx0XHRcdFx0XHRwID0gKHAgLSBwcmV2KSAvIChsZW5ndGggLSBwcmV2KTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdH1cblx0XHRcdFx0aWYgKGN1cnZlICE9IHByZXZDdXJ2ZSkge1xuXHRcdFx0XHRcdHByZXZDdXJ2ZSA9IGN1cnZlO1xuXHRcdFx0XHRcdGlmIChjbG9zZWQgJiYgY3VydmUgPT0gY3VydmVDb3VudCkge1xuXHRcdFx0XHRcdFx0cGF0aC5jb21wdXRlV29ybGRWZXJ0aWNlcyh0YXJnZXQsIHZlcnRpY2VzTGVuZ3RoIC0gNCwgNCwgd29ybGQsIDAsIDIpO1xuXHRcdFx0XHRcdFx0cGF0aC5jb21wdXRlV29ybGRWZXJ0aWNlcyh0YXJnZXQsIDAsIDQsIHdvcmxkLCA0LCAyKTtcblx0XHRcdFx0XHR9IGVsc2Vcblx0XHRcdFx0XHRcdHBhdGguY29tcHV0ZVdvcmxkVmVydGljZXModGFyZ2V0LCBjdXJ2ZSAqIDYgKyAyLCA4LCB3b3JsZCwgMCwgMik7XG5cdFx0XHRcdH1cblx0XHRcdFx0dGhpcy5hZGRDdXJ2ZVBvc2l0aW9uKHAsIHdvcmxkWzBdLCB3b3JsZFsxXSwgd29ybGRbMl0sIHdvcmxkWzNdLCB3b3JsZFs0XSwgd29ybGRbNV0sIHdvcmxkWzZdLCB3b3JsZFs3XSwgb3V0LCBvLFxuXHRcdFx0XHRcdHRhbmdlbnRzIHx8IChpID4gMCAmJiBzcGFjZSA9PSAwKSk7XG5cdFx0XHR9XG5cdFx0XHRyZXR1cm4gb3V0O1xuXHRcdH1cblxuXHRcdC8vIFdvcmxkIHZlcnRpY2VzLlxuXHRcdGlmIChjbG9zZWQpIHtcblx0XHRcdHZlcnRpY2VzTGVuZ3RoICs9IDI7XG5cdFx0XHR3b3JsZCA9IFV0aWxzLnNldEFycmF5U2l6ZSh0aGlzLndvcmxkLCB2ZXJ0aWNlc0xlbmd0aCk7XG5cdFx0XHRwYXRoLmNvbXB1dGVXb3JsZFZlcnRpY2VzKHRhcmdldCwgMiwgdmVydGljZXNMZW5ndGggLSA0LCB3b3JsZCwgMCwgMik7XG5cdFx0XHRwYXRoLmNvbXB1dGVXb3JsZFZlcnRpY2VzKHRhcmdldCwgMCwgMiwgd29ybGQsIHZlcnRpY2VzTGVuZ3RoIC0gNCwgMik7XG5cdFx0XHR3b3JsZFt2ZXJ0aWNlc0xlbmd0aCAtIDJdID0gd29ybGRbMF07XG5cdFx0XHR3b3JsZFt2ZXJ0aWNlc0xlbmd0aCAtIDFdID0gd29ybGRbMV07XG5cdFx0fSBlbHNlIHtcblx0XHRcdGN1cnZlQ291bnQtLTtcblx0XHRcdHZlcnRpY2VzTGVuZ3RoIC09IDQ7XG5cdFx0XHR3b3JsZCA9IFV0aWxzLnNldEFycmF5U2l6ZSh0aGlzLndvcmxkLCB2ZXJ0aWNlc0xlbmd0aCk7XG5cdFx0XHRwYXRoLmNvbXB1dGVXb3JsZFZlcnRpY2VzKHRhcmdldCwgMiwgdmVydGljZXNMZW5ndGgsIHdvcmxkLCAwLCAyKTtcblx0XHR9XG5cblx0XHQvLyBDdXJ2ZSBsZW5ndGhzLlxuXHRcdGxldCBjdXJ2ZXMgPSBVdGlscy5zZXRBcnJheVNpemUodGhpcy5jdXJ2ZXMsIGN1cnZlQ291bnQpO1xuXHRcdGxldCBwYXRoTGVuZ3RoID0gMDtcblx0XHRsZXQgeDEgPSB3b3JsZFswXSwgeTEgPSB3b3JsZFsxXSwgY3gxID0gMCwgY3kxID0gMCwgY3gyID0gMCwgY3kyID0gMCwgeDIgPSAwLCB5MiA9IDA7XG5cdFx0bGV0IHRtcHggPSAwLCB0bXB5ID0gMCwgZGRkZnggPSAwLCBkZGRmeSA9IDAsIGRkZnggPSAwLCBkZGZ5ID0gMCwgZGZ4ID0gMCwgZGZ5ID0gMDtcblx0XHRmb3IgKGxldCBpID0gMCwgdyA9IDI7IGkgPCBjdXJ2ZUNvdW50OyBpKyssIHcgKz0gNikge1xuXHRcdFx0Y3gxID0gd29ybGRbd107XG5cdFx0XHRjeTEgPSB3b3JsZFt3ICsgMV07XG5cdFx0XHRjeDIgPSB3b3JsZFt3ICsgMl07XG5cdFx0XHRjeTIgPSB3b3JsZFt3ICsgM107XG5cdFx0XHR4MiA9IHdvcmxkW3cgKyA0XTtcblx0XHRcdHkyID0gd29ybGRbdyArIDVdO1xuXHRcdFx0dG1weCA9ICh4MSAtIGN4MSAqIDIgKyBjeDIpICogMC4xODc1O1xuXHRcdFx0dG1weSA9ICh5MSAtIGN5MSAqIDIgKyBjeTIpICogMC4xODc1O1xuXHRcdFx0ZGRkZnggPSAoKGN4MSAtIGN4MikgKiAzIC0geDEgKyB4MikgKiAwLjA5Mzc1O1xuXHRcdFx0ZGRkZnkgPSAoKGN5MSAtIGN5MikgKiAzIC0geTEgKyB5MikgKiAwLjA5Mzc1O1xuXHRcdFx0ZGRmeCA9IHRtcHggKiAyICsgZGRkZng7XG5cdFx0XHRkZGZ5ID0gdG1weSAqIDIgKyBkZGRmeTtcblx0XHRcdGRmeCA9IChjeDEgLSB4MSkgKiAwLjc1ICsgdG1weCArIGRkZGZ4ICogMC4xNjY2NjY2Nztcblx0XHRcdGRmeSA9IChjeTEgLSB5MSkgKiAwLjc1ICsgdG1weSArIGRkZGZ5ICogMC4xNjY2NjY2Nztcblx0XHRcdHBhdGhMZW5ndGggKz0gTWF0aC5zcXJ0KGRmeCAqIGRmeCArIGRmeSAqIGRmeSk7XG5cdFx0XHRkZnggKz0gZGRmeDtcblx0XHRcdGRmeSArPSBkZGZ5O1xuXHRcdFx0ZGRmeCArPSBkZGRmeDtcblx0XHRcdGRkZnkgKz0gZGRkZnk7XG5cdFx0XHRwYXRoTGVuZ3RoICs9IE1hdGguc3FydChkZnggKiBkZnggKyBkZnkgKiBkZnkpO1xuXHRcdFx0ZGZ4ICs9IGRkZng7XG5cdFx0XHRkZnkgKz0gZGRmeTtcblx0XHRcdHBhdGhMZW5ndGggKz0gTWF0aC5zcXJ0KGRmeCAqIGRmeCArIGRmeSAqIGRmeSk7XG5cdFx0XHRkZnggKz0gZGRmeCArIGRkZGZ4O1xuXHRcdFx0ZGZ5ICs9IGRkZnkgKyBkZGRmeTtcblx0XHRcdHBhdGhMZW5ndGggKz0gTWF0aC5zcXJ0KGRmeCAqIGRmeCArIGRmeSAqIGRmeSk7XG5cdFx0XHRjdXJ2ZXNbaV0gPSBwYXRoTGVuZ3RoO1xuXHRcdFx0eDEgPSB4Mjtcblx0XHRcdHkxID0geTI7XG5cdFx0fVxuXG5cdFx0aWYgKHRoaXMuZGF0YS5wb3NpdGlvbk1vZGUgPT0gUG9zaXRpb25Nb2RlLlBlcmNlbnQpIHBvc2l0aW9uICo9IHBhdGhMZW5ndGg7XG5cblx0XHRsZXQgbXVsdGlwbGllcjtcblx0XHRzd2l0Y2ggKHRoaXMuZGF0YS5zcGFjaW5nTW9kZSkge1xuXHRcdFx0Y2FzZSBTcGFjaW5nTW9kZS5QZXJjZW50OlxuXHRcdFx0XHRtdWx0aXBsaWVyID0gcGF0aExlbmd0aDtcblx0XHRcdFx0YnJlYWs7XG5cdFx0XHRjYXNlIFNwYWNpbmdNb2RlLlByb3BvcnRpb25hbDpcblx0XHRcdFx0bXVsdGlwbGllciA9IHBhdGhMZW5ndGggLyBzcGFjZXNDb3VudDtcblx0XHRcdFx0YnJlYWs7XG5cdFx0XHRkZWZhdWx0OlxuXHRcdFx0XHRtdWx0aXBsaWVyID0gMTtcblx0XHR9XG5cblx0XHRsZXQgc2VnbWVudHMgPSB0aGlzLnNlZ21lbnRzO1xuXHRcdGxldCBjdXJ2ZUxlbmd0aCA9IDA7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG8gPSAwLCBjdXJ2ZSA9IDAsIHNlZ21lbnQgPSAwOyBpIDwgc3BhY2VzQ291bnQ7IGkrKywgbyArPSAzKSB7XG5cdFx0XHRsZXQgc3BhY2UgPSBzcGFjZXNbaV0gKiBtdWx0aXBsaWVyO1xuXHRcdFx0cG9zaXRpb24gKz0gc3BhY2U7XG5cdFx0XHRsZXQgcCA9IHBvc2l0aW9uO1xuXG5cdFx0XHRpZiAoY2xvc2VkKSB7XG5cdFx0XHRcdHAgJT0gcGF0aExlbmd0aDtcblx0XHRcdFx0aWYgKHAgPCAwKSBwICs9IHBhdGhMZW5ndGg7XG5cdFx0XHRcdGN1cnZlID0gMDtcblx0XHRcdH0gZWxzZSBpZiAocCA8IDApIHtcblx0XHRcdFx0dGhpcy5hZGRCZWZvcmVQb3NpdGlvbihwLCB3b3JsZCwgMCwgb3V0LCBvKTtcblx0XHRcdFx0Y29udGludWU7XG5cdFx0XHR9IGVsc2UgaWYgKHAgPiBwYXRoTGVuZ3RoKSB7XG5cdFx0XHRcdHRoaXMuYWRkQWZ0ZXJQb3NpdGlvbihwIC0gcGF0aExlbmd0aCwgd29ybGQsIHZlcnRpY2VzTGVuZ3RoIC0gNCwgb3V0LCBvKTtcblx0XHRcdFx0Y29udGludWU7XG5cdFx0XHR9XG5cblx0XHRcdC8vIERldGVybWluZSBjdXJ2ZSBjb250YWluaW5nIHBvc2l0aW9uLlxuXHRcdFx0Zm9yICg7IDsgY3VydmUrKykge1xuXHRcdFx0XHRsZXQgbGVuZ3RoID0gY3VydmVzW2N1cnZlXTtcblx0XHRcdFx0aWYgKHAgPiBsZW5ndGgpIGNvbnRpbnVlO1xuXHRcdFx0XHRpZiAoY3VydmUgPT0gMClcblx0XHRcdFx0XHRwIC89IGxlbmd0aDtcblx0XHRcdFx0ZWxzZSB7XG5cdFx0XHRcdFx0bGV0IHByZXYgPSBjdXJ2ZXNbY3VydmUgLSAxXTtcblx0XHRcdFx0XHRwID0gKHAgLSBwcmV2KSAvIChsZW5ndGggLSBwcmV2KTtcblx0XHRcdFx0fVxuXHRcdFx0XHRicmVhaztcblx0XHRcdH1cblxuXHRcdFx0Ly8gQ3VydmUgc2VnbWVudCBsZW5ndGhzLlxuXHRcdFx0aWYgKGN1cnZlICE9IHByZXZDdXJ2ZSkge1xuXHRcdFx0XHRwcmV2Q3VydmUgPSBjdXJ2ZTtcblx0XHRcdFx0bGV0IGlpID0gY3VydmUgKiA2O1xuXHRcdFx0XHR4MSA9IHdvcmxkW2lpXTtcblx0XHRcdFx0eTEgPSB3b3JsZFtpaSArIDFdO1xuXHRcdFx0XHRjeDEgPSB3b3JsZFtpaSArIDJdO1xuXHRcdFx0XHRjeTEgPSB3b3JsZFtpaSArIDNdO1xuXHRcdFx0XHRjeDIgPSB3b3JsZFtpaSArIDRdO1xuXHRcdFx0XHRjeTIgPSB3b3JsZFtpaSArIDVdO1xuXHRcdFx0XHR4MiA9IHdvcmxkW2lpICsgNl07XG5cdFx0XHRcdHkyID0gd29ybGRbaWkgKyA3XTtcblx0XHRcdFx0dG1weCA9ICh4MSAtIGN4MSAqIDIgKyBjeDIpICogMC4wMztcblx0XHRcdFx0dG1weSA9ICh5MSAtIGN5MSAqIDIgKyBjeTIpICogMC4wMztcblx0XHRcdFx0ZGRkZnggPSAoKGN4MSAtIGN4MikgKiAzIC0geDEgKyB4MikgKiAwLjAwNjtcblx0XHRcdFx0ZGRkZnkgPSAoKGN5MSAtIGN5MikgKiAzIC0geTEgKyB5MikgKiAwLjAwNjtcblx0XHRcdFx0ZGRmeCA9IHRtcHggKiAyICsgZGRkZng7XG5cdFx0XHRcdGRkZnkgPSB0bXB5ICogMiArIGRkZGZ5O1xuXHRcdFx0XHRkZnggPSAoY3gxIC0geDEpICogMC4zICsgdG1weCArIGRkZGZ4ICogMC4xNjY2NjY2Nztcblx0XHRcdFx0ZGZ5ID0gKGN5MSAtIHkxKSAqIDAuMyArIHRtcHkgKyBkZGRmeSAqIDAuMTY2NjY2Njc7XG5cdFx0XHRcdGN1cnZlTGVuZ3RoID0gTWF0aC5zcXJ0KGRmeCAqIGRmeCArIGRmeSAqIGRmeSk7XG5cdFx0XHRcdHNlZ21lbnRzWzBdID0gY3VydmVMZW5ndGg7XG5cdFx0XHRcdGZvciAoaWkgPSAxOyBpaSA8IDg7IGlpKyspIHtcblx0XHRcdFx0XHRkZnggKz0gZGRmeDtcblx0XHRcdFx0XHRkZnkgKz0gZGRmeTtcblx0XHRcdFx0XHRkZGZ4ICs9IGRkZGZ4O1xuXHRcdFx0XHRcdGRkZnkgKz0gZGRkZnk7XG5cdFx0XHRcdFx0Y3VydmVMZW5ndGggKz0gTWF0aC5zcXJ0KGRmeCAqIGRmeCArIGRmeSAqIGRmeSk7XG5cdFx0XHRcdFx0c2VnbWVudHNbaWldID0gY3VydmVMZW5ndGg7XG5cdFx0XHRcdH1cblx0XHRcdFx0ZGZ4ICs9IGRkZng7XG5cdFx0XHRcdGRmeSArPSBkZGZ5O1xuXHRcdFx0XHRjdXJ2ZUxlbmd0aCArPSBNYXRoLnNxcnQoZGZ4ICogZGZ4ICsgZGZ5ICogZGZ5KTtcblx0XHRcdFx0c2VnbWVudHNbOF0gPSBjdXJ2ZUxlbmd0aDtcblx0XHRcdFx0ZGZ4ICs9IGRkZnggKyBkZGRmeDtcblx0XHRcdFx0ZGZ5ICs9IGRkZnkgKyBkZGRmeTtcblx0XHRcdFx0Y3VydmVMZW5ndGggKz0gTWF0aC5zcXJ0KGRmeCAqIGRmeCArIGRmeSAqIGRmeSk7XG5cdFx0XHRcdHNlZ21lbnRzWzldID0gY3VydmVMZW5ndGg7XG5cdFx0XHRcdHNlZ21lbnQgPSAwO1xuXHRcdFx0fVxuXG5cdFx0XHQvLyBXZWlnaHQgYnkgc2VnbWVudCBsZW5ndGguXG5cdFx0XHRwICo9IGN1cnZlTGVuZ3RoO1xuXHRcdFx0Zm9yICg7IDsgc2VnbWVudCsrKSB7XG5cdFx0XHRcdGxldCBsZW5ndGggPSBzZWdtZW50c1tzZWdtZW50XTtcblx0XHRcdFx0aWYgKHAgPiBsZW5ndGgpIGNvbnRpbnVlO1xuXHRcdFx0XHRpZiAoc2VnbWVudCA9PSAwKVxuXHRcdFx0XHRcdHAgLz0gbGVuZ3RoO1xuXHRcdFx0XHRlbHNlIHtcblx0XHRcdFx0XHRsZXQgcHJldiA9IHNlZ21lbnRzW3NlZ21lbnQgLSAxXTtcblx0XHRcdFx0XHRwID0gc2VnbWVudCArIChwIC0gcHJldikgLyAobGVuZ3RoIC0gcHJldik7XG5cdFx0XHRcdH1cblx0XHRcdFx0YnJlYWs7XG5cdFx0XHR9XG5cdFx0XHR0aGlzLmFkZEN1cnZlUG9zaXRpb24ocCAqIDAuMSwgeDEsIHkxLCBjeDEsIGN5MSwgY3gyLCBjeTIsIHgyLCB5Miwgb3V0LCBvLCB0YW5nZW50cyB8fCAoaSA+IDAgJiYgc3BhY2UgPT0gMCkpO1xuXHRcdH1cblx0XHRyZXR1cm4gb3V0O1xuXHR9XG5cblx0YWRkQmVmb3JlUG9zaXRpb24gKHA6IG51bWJlciwgdGVtcDogQXJyYXk8bnVtYmVyPiwgaTogbnVtYmVyLCBvdXQ6IEFycmF5PG51bWJlcj4sIG86IG51bWJlcikge1xuXHRcdGxldCB4MSA9IHRlbXBbaV0sIHkxID0gdGVtcFtpICsgMV0sIGR4ID0gdGVtcFtpICsgMl0gLSB4MSwgZHkgPSB0ZW1wW2kgKyAzXSAtIHkxLCByID0gTWF0aC5hdGFuMihkeSwgZHgpO1xuXHRcdG91dFtvXSA9IHgxICsgcCAqIE1hdGguY29zKHIpO1xuXHRcdG91dFtvICsgMV0gPSB5MSArIHAgKiBNYXRoLnNpbihyKTtcblx0XHRvdXRbbyArIDJdID0gcjtcblx0fVxuXG5cdGFkZEFmdGVyUG9zaXRpb24gKHA6IG51bWJlciwgdGVtcDogQXJyYXk8bnVtYmVyPiwgaTogbnVtYmVyLCBvdXQ6IEFycmF5PG51bWJlcj4sIG86IG51bWJlcikge1xuXHRcdGxldCB4MSA9IHRlbXBbaSArIDJdLCB5MSA9IHRlbXBbaSArIDNdLCBkeCA9IHgxIC0gdGVtcFtpXSwgZHkgPSB5MSAtIHRlbXBbaSArIDFdLCByID0gTWF0aC5hdGFuMihkeSwgZHgpO1xuXHRcdG91dFtvXSA9IHgxICsgcCAqIE1hdGguY29zKHIpO1xuXHRcdG91dFtvICsgMV0gPSB5MSArIHAgKiBNYXRoLnNpbihyKTtcblx0XHRvdXRbbyArIDJdID0gcjtcblx0fVxuXG5cdGFkZEN1cnZlUG9zaXRpb24gKHA6IG51bWJlciwgeDE6IG51bWJlciwgeTE6IG51bWJlciwgY3gxOiBudW1iZXIsIGN5MTogbnVtYmVyLCBjeDI6IG51bWJlciwgY3kyOiBudW1iZXIsIHgyOiBudW1iZXIsIHkyOiBudW1iZXIsXG5cdFx0b3V0OiBBcnJheTxudW1iZXI+LCBvOiBudW1iZXIsIHRhbmdlbnRzOiBib29sZWFuKSB7XG5cdFx0aWYgKHAgPT0gMCB8fCBpc05hTihwKSkge1xuXHRcdFx0b3V0W29dID0geDE7XG5cdFx0XHRvdXRbbyArIDFdID0geTE7XG5cdFx0XHRvdXRbbyArIDJdID0gTWF0aC5hdGFuMihjeTEgLSB5MSwgY3gxIC0geDEpO1xuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblx0XHRsZXQgdHQgPSBwICogcCwgdHR0ID0gdHQgKiBwLCB1ID0gMSAtIHAsIHV1ID0gdSAqIHUsIHV1dSA9IHV1ICogdTtcblx0XHRsZXQgdXQgPSB1ICogcCwgdXQzID0gdXQgKiAzLCB1dXQzID0gdSAqIHV0MywgdXR0MyA9IHV0MyAqIHA7XG5cdFx0bGV0IHggPSB4MSAqIHV1dSArIGN4MSAqIHV1dDMgKyBjeDIgKiB1dHQzICsgeDIgKiB0dHQsIHkgPSB5MSAqIHV1dSArIGN5MSAqIHV1dDMgKyBjeTIgKiB1dHQzICsgeTIgKiB0dHQ7XG5cdFx0b3V0W29dID0geDtcblx0XHRvdXRbbyArIDFdID0geTtcblx0XHRpZiAodGFuZ2VudHMpIHtcblx0XHRcdGlmIChwIDwgMC4wMDEpXG5cdFx0XHRcdG91dFtvICsgMl0gPSBNYXRoLmF0YW4yKGN5MSAtIHkxLCBjeDEgLSB4MSk7XG5cdFx0XHRlbHNlXG5cdFx0XHRcdG91dFtvICsgMl0gPSBNYXRoLmF0YW4yKHkgLSAoeTEgKiB1dSArIGN5MSAqIHV0ICogMiArIGN5MiAqIHR0KSwgeCAtICh4MSAqIHV1ICsgY3gxICogdXQgKiAyICsgY3gyICogdHQpKTtcblx0XHR9XG5cdH1cbn1cbiJdfQ==