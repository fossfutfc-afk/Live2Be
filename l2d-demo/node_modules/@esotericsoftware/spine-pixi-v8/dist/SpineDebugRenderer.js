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
import { Container, Graphics, Text } from 'pixi.js';
import { ClippingAttachment, MeshAttachment, PathAttachment, RegionAttachment, SkeletonBounds } from '@esotericsoftware/spine-core';
/**
 * This is a debug renderer that uses PixiJS Graphics under the hood.
 * @public
 */
export class SpineDebugRenderer {
    registeredSpines = new Map();
    drawMeshHull = true;
    drawMeshTriangles = true;
    drawBones = true;
    drawPaths = true;
    drawBoundingBoxes = true;
    drawClipping = true;
    drawRegionAttachments = true;
    drawEvents = true;
    lineWidth = 1;
    regionAttachmentsColor = 0x0078ff;
    meshHullColor = 0x0078ff;
    meshTrianglesColor = 0xffcc00;
    clippingPolygonColor = 0xff00ff;
    boundingBoxesRectColor = 0x00ff00;
    boundingBoxesPolygonColor = 0x00ff00;
    boundingBoxesCircleColor = 0x00ff00;
    pathsCurveColor = 0xff0000;
    pathsLineColor = 0xff00ff;
    skeletonXYColor = 0xff0000;
    bonesColor = 0x00eecc;
    eventFontSize = 24;
    eventFontColor = 0x0;
    /**
     * The debug is attached by force to each spine object.
     * So we need to create it inside the spine when we get the first update
     */
    registerSpine(spine) {
        if (this.registeredSpines.has(spine)) {
            console.warn('SpineDebugRenderer.registerSpine() - this spine is already registered!', spine);
            return;
        }
        const debugDisplayObjects = {
            parentDebugContainer: new Container(),
            bones: new Container(),
            skeletonXY: new Graphics(),
            regionAttachmentsShape: new Graphics(),
            meshTrianglesLine: new Graphics(),
            meshHullLine: new Graphics(),
            clippingPolygon: new Graphics(),
            boundingBoxesRect: new Graphics(),
            boundingBoxesCircle: new Graphics(),
            boundingBoxesPolygon: new Graphics(),
            pathsCurve: new Graphics(),
            pathsLine: new Graphics(),
            eventText: new Container(),
            eventCallback: {
                event: (_, event) => {
                    if (this.drawEvents) {
                        const scale = Math.abs(spine.scale.x || spine.scale.y || 1);
                        const text = new Text({
                            text: event.data.name,
                            style: {
                                fontSize: this.eventFontSize / scale,
                                fill: this.eventFontColor,
                                fontFamily: 'monospace'
                            }
                        });
                        text.scale.x = Math.sign(spine.scale.x);
                        text.anchor.set(0.5);
                        debugDisplayObjects.eventText.addChild(text);
                        setTimeout(() => {
                            if (!text.destroyed) {
                                text.destroy();
                            }
                        }, 250);
                    }
                },
            },
        };
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.bones);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.skeletonXY);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.regionAttachmentsShape);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.meshTrianglesLine);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.meshHullLine);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.clippingPolygon);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.boundingBoxesRect);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.boundingBoxesCircle);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.boundingBoxesPolygon);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.pathsCurve);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.pathsLine);
        debugDisplayObjects.parentDebugContainer.addChild(debugDisplayObjects.eventText);
        debugDisplayObjects.parentDebugContainer.zIndex = 9999999;
        // Disable screen reader and mouse input on debug objects.
        debugDisplayObjects.parentDebugContainer.accessibleChildren = false;
        debugDisplayObjects.parentDebugContainer.eventMode = 'none';
        debugDisplayObjects.parentDebugContainer.interactiveChildren = false;
        spine.addChild(debugDisplayObjects.parentDebugContainer);
        spine.state.addListener(debugDisplayObjects.eventCallback);
        this.registeredSpines.set(spine, debugDisplayObjects);
    }
    renderDebug(spine) {
        if (!this.registeredSpines.has(spine)) {
            // This should never happen. Spines are registered when you assign spine.debug
            this.registerSpine(spine);
        }
        const debugDisplayObjects = this.registeredSpines.get(spine);
        if (!debugDisplayObjects) {
            return;
        }
        spine.addChild(debugDisplayObjects.parentDebugContainer);
        debugDisplayObjects.skeletonXY.clear();
        debugDisplayObjects.regionAttachmentsShape.clear();
        debugDisplayObjects.meshTrianglesLine.clear();
        debugDisplayObjects.meshHullLine.clear();
        debugDisplayObjects.clippingPolygon.clear();
        debugDisplayObjects.boundingBoxesRect.clear();
        debugDisplayObjects.boundingBoxesCircle.clear();
        debugDisplayObjects.boundingBoxesPolygon.clear();
        debugDisplayObjects.pathsCurve.clear();
        debugDisplayObjects.pathsLine.clear();
        for (let len = debugDisplayObjects.bones.children.length; len > 0; len--) {
            debugDisplayObjects.bones.children[len - 1].destroy({ children: true, texture: true, textureSource: true });
        }
        const scale = Math.abs(spine.scale.x || spine.scale.y || 1);
        const lineWidth = this.lineWidth / scale;
        if (this.drawBones) {
            this.drawBonesFunc(spine, debugDisplayObjects, lineWidth, scale);
        }
        if (this.drawPaths) {
            this.drawPathsFunc(spine, debugDisplayObjects, lineWidth);
        }
        if (this.drawBoundingBoxes) {
            this.drawBoundingBoxesFunc(spine, debugDisplayObjects, lineWidth);
        }
        if (this.drawClipping) {
            this.drawClippingFunc(spine, debugDisplayObjects, lineWidth);
        }
        if (this.drawMeshHull || this.drawMeshTriangles) {
            this.drawMeshHullAndMeshTriangles(spine, debugDisplayObjects, lineWidth);
        }
        if (this.drawRegionAttachments) {
            this.drawRegionAttachmentsFunc(spine, debugDisplayObjects, lineWidth);
        }
        if (this.drawEvents) {
            for (const child of debugDisplayObjects.eventText.children) {
                child.alpha -= 0.05;
                child.y -= 2;
            }
        }
    }
    drawBonesFunc(spine, debugDisplayObjects, lineWidth, scale) {
        const skeleton = spine.skeleton;
        const skeletonX = skeleton.x;
        const skeletonY = skeleton.y;
        const bones = skeleton.bones;
        debugDisplayObjects.skeletonXY.strokeStyle = { width: lineWidth, color: this.skeletonXYColor };
        for (let i = 0, len = bones.length; i < len; i++) {
            const bone = bones[i];
            const boneLen = bone.data.length;
            const starX = skeletonX + bone.worldX;
            const starY = skeletonY + bone.worldY;
            const endX = skeletonX + (boneLen * bone.a) + bone.worldX;
            const endY = skeletonY + (boneLen * bone.b) + bone.worldY;
            if (bone.data.name === 'root' || bone.data.parent === null) {
                continue;
            }
            const w = Math.abs(starX - endX);
            const h = Math.abs(starY - endY);
            // a = w, // side length a
            const a2 = Math.pow(w, 2); // square root of side length a
            const b = h; // side length b
            const b2 = Math.pow(h, 2); // square root of side length b
            const c = Math.sqrt(a2 + b2); // side length c
            const c2 = Math.pow(c, 2); // square root of side length c
            const rad = Math.PI / 180;
            // A = Math.acos([a2 + c2 - b2] / [2 * a * c]) || 0, // Angle A
            // C = Math.acos([a2 + b2 - c2] / [2 * a * b]) || 0, // C angle
            const B = Math.acos((c2 + b2 - a2) / (2 * b * c)) || 0; // angle of corner B
            if (c === 0) {
                continue;
            }
            const gp = new Graphics();
            debugDisplayObjects.bones.addChild(gp);
            // draw bone
            const refRation = c / 50 / scale;
            gp.context
                .poly([0, 0, 0 - refRation, c - (refRation * 3), 0, c - refRation, 0 + refRation, c - (refRation * 3)])
                .fill(this.bonesColor);
            gp.x = starX;
            gp.y = starY;
            gp.pivot.y = c;
            // Calculate bone rotation angle
            let rotation = 0;
            if (starX < endX && starY < endY) {
                // bottom right
                rotation = -B + (180 * rad);
            }
            else if (starX > endX && starY < endY) {
                // bottom left
                rotation = (180 * rad) + B;
            }
            else if (starX > endX && starY > endY) {
                // top left
                rotation = -B;
            }
            else if (starX < endX && starY > endY) {
                // bottom left
                rotation = B;
            }
            else if (starY === endY && starX < endX) {
                // To the right
                rotation = 90 * rad;
            }
            else if (starY === endY && starX > endX) {
                // go left
                rotation = -90 * rad;
            }
            else if (starX === endX && starY < endY) {
                // down
                rotation = 180 * rad;
            }
            else if (starX === endX && starY > endY) {
                // up
                rotation = 0;
            }
            gp.rotation = rotation;
            // Draw the starting rotation point of the bone
            gp.circle(0, c, refRation * 1.2)
                .fill({ color: 0x000000, alpha: 0.6 })
                .stroke({ width: lineWidth + refRation / 2.4, color: this.bonesColor });
        }
        // Draw the skeleton starting point "X" form
        const startDotSize = lineWidth * 3;
        debugDisplayObjects.skeletonXY.context
            .moveTo(skeletonX - startDotSize, skeletonY - startDotSize)
            .lineTo(skeletonX + startDotSize, skeletonY + startDotSize)
            .moveTo(skeletonX + startDotSize, skeletonY - startDotSize)
            .lineTo(skeletonX - startDotSize, skeletonY + startDotSize)
            .stroke();
    }
    drawRegionAttachmentsFunc(spine, debugDisplayObjects, lineWidth) {
        const skeleton = spine.skeleton;
        const slots = skeleton.slots;
        for (let i = 0, len = slots.length; i < len; i++) {
            const slot = slots[i];
            const attachment = slot.getAttachment();
            if (attachment === null || !(attachment instanceof RegionAttachment)) {
                continue;
            }
            const regionAttachment = attachment;
            const vertices = new Float32Array(8);
            regionAttachment.computeWorldVertices(slot, vertices, 0, 2);
            debugDisplayObjects.regionAttachmentsShape.poly(Array.from(vertices.slice(0, 8)));
        }
        debugDisplayObjects.regionAttachmentsShape.stroke({
            color: this.regionAttachmentsColor,
            width: lineWidth
        });
    }
    drawMeshHullAndMeshTriangles(spine, debugDisplayObjects, lineWidth) {
        const skeleton = spine.skeleton;
        const slots = skeleton.slots;
        for (let i = 0, len = slots.length; i < len; i++) {
            const slot = slots[i];
            if (!slot.bone.active) {
                continue;
            }
            const attachment = slot.getAttachment();
            if (attachment === null || !(attachment instanceof MeshAttachment)) {
                continue;
            }
            const meshAttachment = attachment;
            const vertices = new Float32Array(meshAttachment.worldVerticesLength);
            const triangles = meshAttachment.triangles;
            let hullLength = meshAttachment.hullLength;
            meshAttachment.computeWorldVertices(slot, 0, meshAttachment.worldVerticesLength, vertices, 0, 2);
            // draw the skinned mesh (triangle)
            if (this.drawMeshTriangles) {
                for (let i = 0, len = triangles.length; i < len; i += 3) {
                    const v1 = triangles[i] * 2;
                    const v2 = triangles[i + 1] * 2;
                    const v3 = triangles[i + 2] * 2;
                    debugDisplayObjects.meshTrianglesLine.context
                        .moveTo(vertices[v1], vertices[v1 + 1])
                        .lineTo(vertices[v2], vertices[v2 + 1])
                        .lineTo(vertices[v3], vertices[v3 + 1]);
                }
            }
            // draw skin border
            if (this.drawMeshHull && hullLength > 0) {
                hullLength = (hullLength >> 1) * 2;
                let lastX = vertices[hullLength - 2];
                let lastY = vertices[hullLength - 1];
                for (let i = 0, len = hullLength; i < len; i += 2) {
                    const x = vertices[i];
                    const y = vertices[i + 1];
                    debugDisplayObjects.meshHullLine.context
                        .moveTo(x, y)
                        .lineTo(lastX, lastY);
                    lastX = x;
                    lastY = y;
                }
            }
        }
        debugDisplayObjects.meshHullLine.stroke({ width: lineWidth, color: this.meshHullColor });
        debugDisplayObjects.meshTrianglesLine.stroke({ width: lineWidth, color: this.meshTrianglesColor });
    }
    drawClippingFunc(spine, debugDisplayObjects, lineWidth) {
        const skeleton = spine.skeleton;
        const slots = skeleton.slots;
        for (let i = 0, len = slots.length; i < len; i++) {
            const slot = slots[i];
            if (!slot.bone.active) {
                continue;
            }
            const attachment = slot.getAttachment();
            if (attachment === null || !(attachment instanceof ClippingAttachment)) {
                continue;
            }
            const clippingAttachment = attachment;
            const nn = clippingAttachment.worldVerticesLength;
            const world = new Float32Array(nn);
            clippingAttachment.computeWorldVertices(slot, 0, nn, world, 0, 2);
            debugDisplayObjects.clippingPolygon.poly(Array.from(world));
        }
        debugDisplayObjects.clippingPolygon.stroke({
            width: lineWidth, color: this.clippingPolygonColor, alpha: 1
        });
    }
    drawBoundingBoxesFunc(spine, debugDisplayObjects, lineWidth) {
        // draw the total outline of the bounding box
        const bounds = new SkeletonBounds();
        bounds.update(spine.skeleton, true);
        if (bounds.minX !== Infinity) {
            debugDisplayObjects.boundingBoxesRect
                .rect(bounds.minX, bounds.minY, bounds.getWidth(), bounds.getHeight())
                .stroke({ width: lineWidth, color: this.boundingBoxesRectColor });
        }
        const polygons = bounds.polygons;
        const drawPolygon = (polygonVertices, _offset, count) => {
            if (count < 3) {
                throw new Error('Polygon must contain at least 3 vertices');
            }
            const paths = [];
            const dotSize = lineWidth * 2;
            for (let i = 0, len = polygonVertices.length; i < len; i += 2) {
                const x1 = polygonVertices[i];
                const y1 = polygonVertices[i + 1];
                // draw the bounding box node
                debugDisplayObjects.boundingBoxesCircle.beginFill(this.boundingBoxesCircleColor);
                debugDisplayObjects.boundingBoxesCircle.drawCircle(x1, y1, dotSize);
                debugDisplayObjects.boundingBoxesCircle.fill(0);
                debugDisplayObjects.boundingBoxesCircle
                    .circle(x1, y1, dotSize)
                    .fill({ color: this.boundingBoxesCircleColor });
                paths.push(x1, y1);
            }
            // draw the bounding box area
            debugDisplayObjects.boundingBoxesPolygon
                .poly(paths)
                .fill({
                color: this.boundingBoxesPolygonColor,
                alpha: 0.1
            })
                .stroke({
                width: lineWidth,
                color: this.boundingBoxesPolygonColor
            });
        };
        for (let i = 0, len = polygons.length; i < len; i++) {
            const polygon = polygons[i];
            drawPolygon(polygon, 0, polygon.length);
        }
    }
    drawPathsFunc(spine, debugDisplayObjects, lineWidth) {
        const skeleton = spine.skeleton;
        const slots = skeleton.slots;
        for (let i = 0, len = slots.length; i < len; i++) {
            const slot = slots[i];
            if (!slot.bone.active) {
                continue;
            }
            const attachment = slot.getAttachment();
            if (attachment === null || !(attachment instanceof PathAttachment)) {
                continue;
            }
            const pathAttachment = attachment;
            let nn = pathAttachment.worldVerticesLength;
            const world = new Float32Array(nn);
            pathAttachment.computeWorldVertices(slot, 0, nn, world, 0, 2);
            let x1 = world[2];
            let y1 = world[3];
            let x2 = 0;
            let y2 = 0;
            if (pathAttachment.closed) {
                const cx1 = world[0];
                const cy1 = world[1];
                const cx2 = world[nn - 2];
                const cy2 = world[nn - 1];
                x2 = world[nn - 4];
                y2 = world[nn - 3];
                // curve
                debugDisplayObjects.pathsCurve.moveTo(x1, y1);
                debugDisplayObjects.pathsCurve.bezierCurveTo(cx1, cy1, cx2, cy2, x2, y2);
                // handle
                debugDisplayObjects.pathsLine.moveTo(x1, y1);
                debugDisplayObjects.pathsLine.lineTo(cx1, cy1);
                debugDisplayObjects.pathsLine.moveTo(x2, y2);
                debugDisplayObjects.pathsLine.lineTo(cx2, cy2);
            }
            nn -= 4;
            for (let ii = 4; ii < nn; ii += 6) {
                const cx1 = world[ii];
                const cy1 = world[ii + 1];
                const cx2 = world[ii + 2];
                const cy2 = world[ii + 3];
                x2 = world[ii + 4];
                y2 = world[ii + 5];
                // curve
                debugDisplayObjects.pathsCurve.moveTo(x1, y1);
                debugDisplayObjects.pathsCurve.bezierCurveTo(cx1, cy1, cx2, cy2, x2, y2);
                // handle
                debugDisplayObjects.pathsLine.moveTo(x1, y1);
                debugDisplayObjects.pathsLine.lineTo(cx1, cy1);
                debugDisplayObjects.pathsLine.moveTo(x2, y2);
                debugDisplayObjects.pathsLine.lineTo(cx2, cy2);
                x1 = x2;
                y1 = y2;
            }
        }
        debugDisplayObjects.pathsCurve.stroke({ width: lineWidth, color: this.pathsCurveColor });
        debugDisplayObjects.pathsLine.stroke({ width: lineWidth, color: this.pathsLineColor });
    }
    unregisterSpine(spine) {
        if (!this.registeredSpines.has(spine)) {
            console.warn('SpineDebugRenderer.unregisterSpine() - spine is not registered, can\'t unregister!', spine);
        }
        const debugDisplayObjects = this.registeredSpines.get(spine);
        if (!debugDisplayObjects) {
            return;
        }
        spine.state.removeListener(debugDisplayObjects.eventCallback);
        debugDisplayObjects.parentDebugContainer.destroy({ textureSource: true, children: true, texture: true });
        this.registeredSpines.delete(spine);
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiU3BpbmVEZWJ1Z1JlbmRlcmVyLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsiLi4vc3JjL1NwaW5lRGVidWdSZW5kZXJlci50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiQUFBQTs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OytFQTJCK0U7QUFFL0UsT0FBTyxFQUFFLFNBQVMsRUFBRSxRQUFRLEVBQUUsSUFBSSxFQUFFLE1BQU0sU0FBUyxDQUFDO0FBRXBELE9BQU8sRUFDTixrQkFBa0IsRUFDbEIsY0FBYyxFQUNkLGNBQWMsRUFDZCxnQkFBZ0IsRUFDaEIsY0FBYyxFQUNkLE1BQU0sOEJBQThCLENBQUM7QUEwQ3RDOzs7R0FHRztBQUNILE1BQU0sT0FBTyxrQkFBa0I7SUFDYixnQkFBZ0IsR0FBb0MsSUFBSSxHQUFHLEVBQUUsQ0FBQztJQUV4RSxZQUFZLEdBQUcsSUFBSSxDQUFDO0lBQ3BCLGlCQUFpQixHQUFHLElBQUksQ0FBQztJQUN6QixTQUFTLEdBQUcsSUFBSSxDQUFDO0lBQ2pCLFNBQVMsR0FBRyxJQUFJLENBQUM7SUFDakIsaUJBQWlCLEdBQUcsSUFBSSxDQUFDO0lBQ3pCLFlBQVksR0FBRyxJQUFJLENBQUM7SUFDcEIscUJBQXFCLEdBQUcsSUFBSSxDQUFDO0lBQzdCLFVBQVUsR0FBRyxJQUFJLENBQUM7SUFFbEIsU0FBUyxHQUFHLENBQUMsQ0FBQztJQUNkLHNCQUFzQixHQUFHLFFBQVEsQ0FBQztJQUNsQyxhQUFhLEdBQUcsUUFBUSxDQUFDO0lBQ3pCLGtCQUFrQixHQUFHLFFBQVEsQ0FBQztJQUM5QixvQkFBb0IsR0FBRyxRQUFRLENBQUM7SUFDaEMsc0JBQXNCLEdBQUcsUUFBUSxDQUFDO0lBQ2xDLHlCQUF5QixHQUFHLFFBQVEsQ0FBQztJQUNyQyx3QkFBd0IsR0FBRyxRQUFRLENBQUM7SUFDcEMsZUFBZSxHQUFHLFFBQVEsQ0FBQztJQUMzQixjQUFjLEdBQUcsUUFBUSxDQUFDO0lBQzFCLGVBQWUsR0FBRyxRQUFRLENBQUM7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RSxDQUFDO1lBQ1QsQ0FBQztRQUNGLENBQUM7UUFFRCxtQkFBbUIsQ0FBQyxVQUFVLENBQUMsTUFBTSxDQUFDLEVBQUUsS0FBSyxFQUFFLFNBQVMsRUFBRSxLQUFLLEVBQUUsSUFBSSxDQUFDLGVBQWUsRUFBRSxDQUFDLENBQUM7UUFDekYsbUJBQW1CLENBQUMsU0FBUyxDQUFDLE1BQU0sQ0FBQyxFQUFFLEtBQUssRUFBRSxTQUFTLEVBQUUsS0FBSyxFQUFFLElBQUksQ0FBQyxjQUFjLEVBQUUsQ0FBQyxDQUFDO0lBQ3hGLENBQUM7SUFFTSxlQUFlLENBQUUsS0FBWTtRQUNuQyxJQUFJLENBQUMsSUFBSSxDQUFDLGdCQUFnQixDQUFDLEdBQUcsQ0FBQyxLQUFLLENBQUMsRUFBRSxDQUFDO1lBQ3ZDLE9BQU8sQ0FBQyxJQUFJLENBQUMsb0ZBQW9GLEVBQUUsS0FBSyxDQUFDLENBQUM7UUFDM0csQ0FBQztRQUNELE1BQU0sbUJBQW1CLEdBQUcsSUFBSSxDQUFDLGdCQUFnQixDQUFDLEdBQUcsQ0FBQyxLQUFLLENBQUMsQ0FBQztRQUU3RCxJQUFJLENBQUMsbUJBQW1CLEVBQUUsQ0FBQztZQUMxQixPQUFPO1FBQ1IsQ0FBQztRQUVELEtBQUssQ0FBQyxLQUFLLENBQUMsY0FBYyxDQUFDLG1CQUFtQixDQUFDLGFBQWEsQ0FBQyxDQUFDO1FBRTlELG1CQUFtQixDQUFDLG9CQUFvQixDQUFDLE9BQU8sQ0FBQyxFQUFFLGFBQWEsRUFBRSxJQUFJLEVBQUUsUUFBUSxFQUFFLElBQUksRUFBRSxPQUFPLEVBQUUsSUFBSSxFQUFFLENBQUMsQ0FBQztRQUN6RyxJQUFJLENBQUMsZ0JBQWdCLENBQUMsTUFBTSxDQUFDLEtBQUssQ0FBQyxDQUFDO0lBQ3JDLENBQUM7Q0FDRCIsInNvdXJjZXNDb250ZW50IjpbIi8qKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKipcbiAqIFNwaW5lIFJ1bnRpbWVzIExpY2Vuc2UgQWdyZWVtZW50XG4gKiBMYXN0IHVwZGF0ZWQgQXByaWwgNSwgMjAyNS4gUmVwbGFjZXMgYWxsIHByaW9yIHZlcnNpb25zLlxuICpcbiAqIENvcHlyaWdodCAoYykgMjAxMy0yMDI1LCBFc290ZXJpYyBTb2Z0d2FyZSBMTENcbiAqXG4gKiBJbnRlZ3JhdGlvbiBvZiB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZSBvciBvdGhlcndpc2UgY3JlYXRpbmdcbiAqIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGlzIHBlcm1pdHRlZCB1bmRlciB0aGUgdGVybXMgYW5kXG4gKiBjb25kaXRpb25zIG9mIFNlY3Rpb24gMiBvZiB0aGUgU3BpbmUgRWRpdG9yIExpY2Vuc2UgQWdyZWVtZW50OlxuICogaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLWVkaXRvci1saWNlbnNlXG4gKlxuICogT3RoZXJ3aXNlLCBpdCBpcyBwZXJtaXR0ZWQgdG8gaW50ZWdyYXRlIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlXG4gKiBvciBvdGhlcndpc2UgY3JlYXRlIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIChjb2xsZWN0aXZlbHksXG4gKiBcIlByb2R1Y3RzXCIpLCBwcm92aWRlZCB0aGF0IGVhY2ggdXNlciBvZiB0aGUgUHJvZHVjdHMgbXVzdCBvYnRhaW4gdGhlaXIgb3duXG4gKiBTcGluZSBFZGl0b3IgbGljZW5zZSBhbmQgcmVkaXN0cmlidXRpb24gb2YgdGhlIFByb2R1Y3RzIGluIGFueSBmb3JtIG11c3RcbiAqIGluY2x1ZGUgdGhpcyBsaWNlbnNlIGFuZCBjb3B5cmlnaHQgbm90aWNlLlxuICpcbiAqIFRIRSBTUElORSBSVU5USU1FUyBBUkUgUFJPVklERUQgQlkgRVNPVEVSSUMgU09GVFdBUkUgTExDIFwiQVMgSVNcIiBBTkQgQU5ZXG4gKiBFWFBSRVNTIE9SIElNUExJRUQgV0FSUkFOVElFUywgSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFRIRSBJTVBMSUVEXG4gKiBXQVJSQU5USUVTIE9GIE1FUkNIQU5UQUJJTElUWSBBTkQgRklUTkVTUyBGT1IgQSBQQVJUSUNVTEFSIFBVUlBPU0UgQVJFXG4gKiBESVNDTEFJTUVELiBJTiBOTyBFVkVOVCBTSEFMTCBFU09URVJJQyBTT0ZUV0FSRSBMTEMgQkUgTElBQkxFIEZPUiBBTllcbiAqIERJUkVDVCwgSU5ESVJFQ1QsIElOQ0lERU5UQUwsIFNQRUNJQUwsIEVYRU1QTEFSWSwgT1IgQ09OU0VRVUVOVElBTCBEQU1BR0VTXG4gKiAoSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFBST0NVUkVNRU5UIE9GIFNVQlNUSVRVVEUgR09PRFMgT1IgU0VSVklDRVMsXG4gKiBCVVNJTkVTUyBJTlRFUlJVUFRJT04sIE9SIExPU1MgT0YgVVNFLCBEQVRBLCBPUiBQUk9GSVRTKSBIT1dFVkVSIENBVVNFRCBBTkRcbiAqIE9OIEFOWSBUSEVPUlkgT0YgTElBQklMSVRZLCBXSEVUSEVSIElOIENPTlRSQUNULCBTVFJJQ1QgTElBQklMSVRZLCBPUiBUT1JUXG4gKiAoSU5DTFVESU5HIE5FR0xJR0VOQ0UgT1IgT1RIRVJXSVNFKSBBUklTSU5HIElOIEFOWSBXQVkgT1VUIE9GIFRIRSBVU0UgT0ZcbiAqIFRIRSBTUElORSBSVU5USU1FUywgRVZFTiBJRiBBRFZJU0VEIE9GIFRIRSBQT1NTSUJJTElUWSBPRiBTVUNIIERBTUFHRS5cbiAqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKi9cblxuaW1wb3J0IHsgQ29udGFpbmVyLCBHcmFwaGljcywgVGV4dCB9IGZyb20gJ3BpeGkuanMnO1xuaW1wb3J0IHsgU3BpbmUgfSBmcm9tICcuL1NwaW5lLmpzJztcbmltcG9ydCB7XG5cdENsaXBwaW5nQXR0YWNobWVudCxcblx0TWVzaEF0dGFjaG1lbnQsXG5cdFBhdGhBdHRhY2htZW50LFxuXHRSZWdpb25BdHRhY2htZW50LFxuXHRTa2VsZXRvbkJvdW5kc1xufSBmcm9tICdAZXNvdGVyaWNzb2Z0d2FyZS9zcGluZS1jb3JlJztcblxuaW1wb3J0IHR5cGUgeyBBbmltYXRpb25TdGF0ZUxpc3RlbmVyIH0gZnJvbSAnQGVzb3Rlcmljc29mdHdhcmUvc3BpbmUtY29yZSc7XG5cbi8qKlxuICogTWFrZSBhIGNsYXNzIHRoYXQgZXh0ZW5kcyBmcm9tIHRoaXMgaW50ZXJmYWNlIHRvIGNyZWF0ZSB5b3VyIG93biBkZWJ1ZyByZW5kZXJlci5cbiAqIEBwdWJsaWNcbiAqL1xuZXhwb3J0IGludGVyZmFjZSBJU3BpbmVEZWJ1Z1JlbmRlcmVyIHtcblx0LyoqXG5cdCAqIFRoaXMgd2lsbCBiZSBjYWxsZWQgZXZlcnkgZnJhbWUsIGFmdGVyIHRoZSBzcGluZSBoYXMgYmVlbiB1cGRhdGVkLlxuXHQgKi9cblx0cmVuZGVyRGVidWc6IChzcGluZTogU3BpbmUpID0+IHZvaWQ7XG5cblx0LyoqXG5cdCAqICBUaGlzIGlzIGNhbGxlZCB3aGVuIHRoZSBgc3BpbmUuZGVidWdgIG9iamVjdCBpcyBzZXQgdG8gbnVsbCBvciB3aGVuIHRoZSBzcGluZSBpcyBkZXN0cm95ZWQuXG5cdCAqL1xuXHR1bnJlZ2lzdGVyU3BpbmU6IChzcGluZTogU3BpbmUpID0+IHZvaWQ7XG5cblx0LyoqXG5cdCAqIFRoaXMgaXMgY2FsbGVkIHdoZW4gdGhlIGBzcGluZS5kZWJ1Z2Agb2JqZWN0IGlzIHNldCB0byBhIG5ldyBpbnN0YW5jZSBvZiBhIGRlYnVnIHJlbmRlcmVyLlxuXHQgKi9cblx0cmVnaXN0ZXJTcGluZTogKHNwaW5lOiBTcGluZSkgPT4gdm9pZDtcbn1cblxudHlwZSBEZWJ1Z0Rpc3BsYXlPYmplY3RzID0ge1xuXHRib25lczogQ29udGFpbmVyO1xuXHRza2VsZXRvblhZOiBHcmFwaGljcztcblx0cmVnaW9uQXR0YWNobWVudHNTaGFwZTogR3JhcGhpY3M7XG5cdG1lc2hUcmlhbmdsZXNMaW5lOiBHcmFwaGljcztcblx0bWVzaEh1bGxMaW5lOiBHcmFwaGljcztcblx0Y2xpcHBpbmdQb2x5Z29uOiBHcmFwaGljcztcblx0Ym91bmRpbmdCb3hlc1JlY3Q6IEdyYXBoaWNzO1xuXHRib3VuZGluZ0JveGVzQ2lyY2xlOiBHcmFwaGljcztcblx0Ym91bmRpbmdCb3hlc1BvbHlnb246IEdyYXBoaWNzO1xuXHRwYXRoc0N1cnZlOiBHcmFwaGljcztcblx0cGF0aHNMaW5lOiBHcmFwaGljcztcblx0cGFyZW50RGVidWdDb250YWluZXI6IENvbnRhaW5lcjtcblx0ZXZlbnRUZXh0OiBDb250YWluZXI7XG5cdGV2ZW50Q2FsbGJhY2s6IEFuaW1hdGlvblN0YXRlTGlzdGVuZXI7XG59O1xuXG4vKipcbiAqIFRoaXMgaXMgYSBkZWJ1ZyByZW5kZXJlciB0aGF0IHVzZXMgUGl4aUpTIEdyYXBoaWNzIHVuZGVyIHRoZSBob29kLlxuICogQHB1YmxpY1xuICovXG5leHBvcnQgY2xhc3MgU3BpbmVEZWJ1Z1JlbmRlcmVyIGltcGxlbWVudHMgSVNwaW5lRGVidWdSZW5kZXJlciB7XG5cdHByaXZhdGUgcmVhZG9ubHkgcmVnaXN0ZXJlZFNwaW5lczogTWFwPFNwaW5lLCBEZWJ1Z0Rpc3BsYXlPYmplY3RzPiA9IG5ldyBNYXAoKTtcblxuXHRwdWJsaWMgZHJhd01lc2hIdWxsID0gdHJ1ZTtcblx0cHVibGljIGRyYXdNZXNoVHJpYW5nbGVzID0gdHJ1ZTtcblx0cHVibGljIGRyYXdCb25lcyA9IHRydWU7XG5cdHB1YmxpYyBkcmF3UGF0aHMgPSB0cnVlO1xuXHRwdWJsaWMgZHJhd0JvdW5kaW5nQm94ZXMgPSB0cnVlO1xuXHRwdWJsaWMgZHJhd0NsaXBwaW5nID0gdHJ1ZTtcblx0cHVibGljIGRyYXdSZWdpb25BdHRhY2htZW50cyA9IHRydWU7XG5cdHB1YmxpYyBkcmF3RXZlbnRzID0gdHJ1ZTtcblxuXHRwdWJsaWMgbGluZVdpZHRoID0gMTtcblx0cHVibGljIHJlZ2lvbkF0dGFjaG1lbnRzQ29sb3IgPSAweDAwNzhmZjtcblx0cHVibGljIG1lc2hIdWxsQ29sb3IgPSAweDAwNzhmZjtcblx0cHVibGljIG1lc2hUcmlhbmdsZXNDb2xvciA9IDB4ZmZjYzAwO1xuXHRwdWJsaWMgY2xpcHBpbmdQb2x5Z29uQ29sb3IgPSAweGZmMDBmZjtcblx0cHVibGljIGJvdW5kaW5nQm94ZXNSZWN0Q29sb3IgPSAweDAwZmYwMDtcblx0cHVibGljIGJvdW5kaW5nQm94ZXNQb2x5Z29uQ29sb3IgPSAweDAwZmYwMDtcblx0cHVibGljIGJvdW5kaW5nQm94ZXNDaXJjbGVDb2xvciA9IDB4MDBmZjAwO1xuXHRwdWJsaWMgcGF0aHNDdXJ2ZUNvbG9yID0gMHhmZjAwMDA7XG5cdHB1YmxpYyBwYXRoc0xpbmVDb2xvciA9IDB4ZmYwMGZmO1xuXHRwdWJsaWMgc2tlbGV0b25YWUNvbG9yID0gMHhmZjAwMDA7XG5cdHB1YmxpYyBib25lc0NvbG9yID0gMHgwMGVlY2M7XG5cdHB1YmxpYyBldmVudEZvbnRTaXplID0gMjQ7XG5cdHB1YmxpYyBldmVudEZvbnRDb2xvciA9IDB4MDtcblxuXHQvKipcblx0ICogVGhlIGRlYnVnIGlzIGF0dGFjaGVkIGJ5IGZvcmNlIHRvIGVhY2ggc3BpbmUgb2JqZWN0LlxuXHQgKiBTbyB3ZSBuZWVkIHRvIGNyZWF0ZSBpdCBpbnNpZGUgdGhlIHNwaW5lIHdoZW4gd2UgZ2V0IHRoZSBmaXJzdCB1cGRhdGVcblx0ICovXG5cdHB1YmxpYyByZWdpc3RlclNwaW5lIChzcGluZTogU3BpbmUpOiB2b2lkIHtcblx0XHRpZiAodGhpcy5yZWdpc3RlcmVkU3BpbmVzLmhhcyhzcGluZSkpIHtcblx0XHRcdGNvbnNvbGUud2FybignU3BpbmVEZWJ1Z1JlbmRlcmVyLnJlZ2lzdGVyU3BpbmUoKSAtIHRoaXMgc3BpbmUgaXMgYWxyZWFkeSByZWdpc3RlcmVkIScsIHNwaW5lKTtcblxuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblx0XHRjb25zdCBkZWJ1Z0Rpc3BsYXlPYmplY3RzOiBEZWJ1Z0Rpc3BsYXlPYmplY3RzID0ge1xuXHRcdFx0cGFyZW50RGVidWdDb250YWluZXI6IG5ldyBDb250YWluZXIoKSxcblx0XHRcdGJvbmVzOiBuZXcgQ29udGFpbmVyKCksXG5cdFx0XHRza2VsZXRvblhZOiBuZXcgR3JhcGhpY3MoKSxcblx0XHRcdHJlZ2lvbkF0dGFjaG1lbnRzU2hhcGU6IG5ldyBHcmFwaGljcygpLFxuXHRcdFx0bWVzaFRyaWFuZ2xlc0xpbmU6IG5ldyBHcmFwaGljcygpLFxuXHRcdFx0bWVzaEh1bGxMaW5lOiBuZXcgR3JhcGhpY3MoKSxcblx0XHRcdGNsaXBwaW5nUG9seWdvbjogbmV3IEdyYXBoaWNzKCksXG5cdFx0XHRib3VuZGluZ0JveGVzUmVjdDogbmV3IEdyYXBoaWNzKCksXG5cdFx0XHRib3VuZGluZ0JveGVzQ2lyY2xlOiBuZXcgR3JhcGhpY3MoKSxcblx0XHRcdGJvdW5kaW5nQm94ZXNQb2x5Z29uOiBuZXcgR3JhcGhpY3MoKSxcblx0XHRcdHBhdGhzQ3VydmU6IG5ldyBHcmFwaGljcygpLFxuXHRcdFx0cGF0aHNMaW5lOiBuZXcgR3JhcGhpY3MoKSxcblx0XHRcdGV2ZW50VGV4dDogbmV3IENvbnRhaW5lcigpLFxuXHRcdFx0ZXZlbnRDYWxsYmFjazoge1xuXHRcdFx0XHRldmVudDogKF8sIGV2ZW50KSA9PiB7XG5cdFx0XHRcdFx0aWYgKHRoaXMuZHJhd0V2ZW50cykge1xuXHRcdFx0XHRcdFx0Y29uc3Qgc2NhbGUgPSBNYXRoLmFicyhzcGluZS5zY2FsZS54IHx8IHNwaW5lLnNjYWxlLnkgfHwgMSk7XG5cdFx0XHRcdFx0XHRjb25zdCB0ZXh0ID0gbmV3IFRleHQoe1xuXHRcdFx0XHRcdFx0XHR0ZXh0OiBldmVudC5kYXRhLm5hbWUsXG5cdFx0XHRcdFx0XHRcdHN0eWxlOiB7XG5cdFx0XHRcdFx0XHRcdFx0Zm9udFNpemU6IHRoaXMuZXZlbnRGb250U2l6ZSAvIHNjYWxlLFxuXHRcdFx0XHRcdFx0XHRcdGZpbGw6IHRoaXMuZXZlbnRGb250Q29sb3IsXG5cdFx0XHRcdFx0XHRcdFx0Zm9udEZhbWlseTogJ21vbm9zcGFjZSdcblx0XHRcdFx0XHRcdFx0fVxuXHRcdFx0XHRcdFx0fSk7XG5cblx0XHRcdFx0XHRcdHRleHQuc2NhbGUueCA9IE1hdGguc2lnbihzcGluZS5zY2FsZS54KTtcblx0XHRcdFx0XHRcdHRleHQuYW5jaG9yLnNldCgwLjUpO1xuXHRcdFx0XHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5ldmVudFRleHQuYWRkQ2hpbGQodGV4dCk7XG5cdFx0XHRcdFx0XHRzZXRUaW1lb3V0KCgpID0+IHtcblx0XHRcdFx0XHRcdFx0aWYgKCF0ZXh0LmRlc3Ryb3llZCkge1xuXHRcdFx0XHRcdFx0XHRcdHRleHQuZGVzdHJveSgpO1xuXHRcdFx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0XHR9LCAyNTApO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0fSxcblx0XHRcdH0sXG5cdFx0fTtcblxuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIuYWRkQ2hpbGQoZGVidWdEaXNwbGF5T2JqZWN0cy5ib25lcyk7XG5cdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5wYXJlbnREZWJ1Z0NvbnRhaW5lci5hZGRDaGlsZChkZWJ1Z0Rpc3BsYXlPYmplY3RzLnNrZWxldG9uWFkpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIuYWRkQ2hpbGQoZGVidWdEaXNwbGF5T2JqZWN0cy5yZWdpb25BdHRhY2htZW50c1NoYXBlKTtcblx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhcmVudERlYnVnQ29udGFpbmVyLmFkZENoaWxkKGRlYnVnRGlzcGxheU9iamVjdHMubWVzaFRyaWFuZ2xlc0xpbmUpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIuYWRkQ2hpbGQoZGVidWdEaXNwbGF5T2JqZWN0cy5tZXNoSHVsbExpbmUpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIuYWRkQ2hpbGQoZGVidWdEaXNwbGF5T2JqZWN0cy5jbGlwcGluZ1BvbHlnb24pO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIuYWRkQ2hpbGQoZGVidWdEaXNwbGF5T2JqZWN0cy5ib3VuZGluZ0JveGVzUmVjdCk7XG5cdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5wYXJlbnREZWJ1Z0NvbnRhaW5lci5hZGRDaGlsZChkZWJ1Z0Rpc3BsYXlPYmplY3RzLmJvdW5kaW5nQm94ZXNDaXJjbGUpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIuYWRkQ2hpbGQoZGVidWdEaXNwbGF5T2JqZWN0cy5ib3VuZGluZ0JveGVzUG9seWdvbik7XG5cdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5wYXJlbnREZWJ1Z0NvbnRhaW5lci5hZGRDaGlsZChkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhdGhzQ3VydmUpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIuYWRkQ2hpbGQoZGVidWdEaXNwbGF5T2JqZWN0cy5wYXRoc0xpbmUpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIuYWRkQ2hpbGQoZGVidWdEaXNwbGF5T2JqZWN0cy5ldmVudFRleHQpO1xuXG5cdFx0KGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIgYXMgYW55KS56SW5kZXggPSA5OTk5OTk5O1xuXG5cdFx0Ly8gRGlzYWJsZSBzY3JlZW4gcmVhZGVyIGFuZCBtb3VzZSBpbnB1dCBvbiBkZWJ1ZyBvYmplY3RzLlxuXHRcdChkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhcmVudERlYnVnQ29udGFpbmVyIGFzIGFueSkuYWNjZXNzaWJsZUNoaWxkcmVuID0gZmFsc2U7XG5cdFx0KGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIgYXMgYW55KS5ldmVudE1vZGUgPSAnbm9uZSc7XG5cdFx0KGRlYnVnRGlzcGxheU9iamVjdHMucGFyZW50RGVidWdDb250YWluZXIgYXMgYW55KS5pbnRlcmFjdGl2ZUNoaWxkcmVuID0gZmFsc2U7XG5cblx0XHRzcGluZS5hZGRDaGlsZChkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhcmVudERlYnVnQ29udGFpbmVyKTtcblxuXHRcdHNwaW5lLnN0YXRlLmFkZExpc3RlbmVyKGRlYnVnRGlzcGxheU9iamVjdHMuZXZlbnRDYWxsYmFjayk7XG5cblx0XHR0aGlzLnJlZ2lzdGVyZWRTcGluZXMuc2V0KHNwaW5lLCBkZWJ1Z0Rpc3BsYXlPYmplY3RzKTtcblx0fVxuXG5cdHB1YmxpYyByZW5kZXJEZWJ1ZyAoc3BpbmU6IFNwaW5lKTogdm9pZCB7XG5cdFx0aWYgKCF0aGlzLnJlZ2lzdGVyZWRTcGluZXMuaGFzKHNwaW5lKSkge1xuXHRcdFx0Ly8gVGhpcyBzaG91bGQgbmV2ZXIgaGFwcGVuLiBTcGluZXMgYXJlIHJlZ2lzdGVyZWQgd2hlbiB5b3UgYXNzaWduIHNwaW5lLmRlYnVnXG5cdFx0XHR0aGlzLnJlZ2lzdGVyU3BpbmUoc3BpbmUpO1xuXHRcdH1cblxuXHRcdGNvbnN0IGRlYnVnRGlzcGxheU9iamVjdHMgPSB0aGlzLnJlZ2lzdGVyZWRTcGluZXMuZ2V0KHNwaW5lKTtcblxuXHRcdGlmICghZGVidWdEaXNwbGF5T2JqZWN0cykge1xuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblx0XHRzcGluZS5hZGRDaGlsZChkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhcmVudERlYnVnQ29udGFpbmVyKTtcblxuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMuc2tlbGV0b25YWS5jbGVhcigpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMucmVnaW9uQXR0YWNobWVudHNTaGFwZS5jbGVhcigpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMubWVzaFRyaWFuZ2xlc0xpbmUuY2xlYXIoKTtcblx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLm1lc2hIdWxsTGluZS5jbGVhcigpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMuY2xpcHBpbmdQb2x5Z29uLmNsZWFyKCk7XG5cdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5ib3VuZGluZ0JveGVzUmVjdC5jbGVhcigpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMuYm91bmRpbmdCb3hlc0NpcmNsZS5jbGVhcigpO1xuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMuYm91bmRpbmdCb3hlc1BvbHlnb24uY2xlYXIoKTtcblx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhdGhzQ3VydmUuY2xlYXIoKTtcblx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhdGhzTGluZS5jbGVhcigpO1xuXG5cdFx0Zm9yIChsZXQgbGVuID0gZGVidWdEaXNwbGF5T2JqZWN0cy5ib25lcy5jaGlsZHJlbi5sZW5ndGg7IGxlbiA+IDA7IGxlbi0tKSB7XG5cdFx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLmJvbmVzLmNoaWxkcmVuW2xlbiAtIDFdLmRlc3Ryb3koeyBjaGlsZHJlbjogdHJ1ZSwgdGV4dHVyZTogdHJ1ZSwgdGV4dHVyZVNvdXJjZTogdHJ1ZSB9KTtcblx0XHR9XG5cblx0XHRjb25zdCBzY2FsZSA9IE1hdGguYWJzKHNwaW5lLnNjYWxlLnggfHwgc3BpbmUuc2NhbGUueSB8fCAxKTtcblx0XHRjb25zdCBsaW5lV2lkdGggPSB0aGlzLmxpbmVXaWR0aCAvIHNjYWxlO1xuXG5cdFx0aWYgKHRoaXMuZHJhd0JvbmVzKSB7XG5cdFx0XHR0aGlzLmRyYXdCb25lc0Z1bmMoc3BpbmUsIGRlYnVnRGlzcGxheU9iamVjdHMsIGxpbmVXaWR0aCwgc2NhbGUpO1xuXHRcdH1cblxuXHRcdGlmICh0aGlzLmRyYXdQYXRocykge1xuXHRcdFx0dGhpcy5kcmF3UGF0aHNGdW5jKHNwaW5lLCBkZWJ1Z0Rpc3BsYXlPYmplY3RzLCBsaW5lV2lkdGgpO1xuXHRcdH1cblxuXHRcdGlmICh0aGlzLmRyYXdCb3VuZGluZ0JveGVzKSB7XG5cdFx0XHR0aGlzLmRyYXdCb3VuZGluZ0JveGVzRnVuYyhzcGluZSwgZGVidWdEaXNwbGF5T2JqZWN0cywgbGluZVdpZHRoKTtcblx0XHR9XG5cblx0XHRpZiAodGhpcy5kcmF3Q2xpcHBpbmcpIHtcblx0XHRcdHRoaXMuZHJhd0NsaXBwaW5nRnVuYyhzcGluZSwgZGVidWdEaXNwbGF5T2JqZWN0cywgbGluZVdpZHRoKTtcblx0XHR9XG5cblx0XHRpZiAodGhpcy5kcmF3TWVzaEh1bGwgfHwgdGhpcy5kcmF3TWVzaFRyaWFuZ2xlcykge1xuXHRcdFx0dGhpcy5kcmF3TWVzaEh1bGxBbmRNZXNoVHJpYW5nbGVzKHNwaW5lLCBkZWJ1Z0Rpc3BsYXlPYmplY3RzLCBsaW5lV2lkdGgpO1xuXHRcdH1cblxuXHRcdGlmICh0aGlzLmRyYXdSZWdpb25BdHRhY2htZW50cykge1xuXHRcdFx0dGhpcy5kcmF3UmVnaW9uQXR0YWNobWVudHNGdW5jKHNwaW5lLCBkZWJ1Z0Rpc3BsYXlPYmplY3RzLCBsaW5lV2lkdGgpO1xuXHRcdH1cblxuXHRcdGlmICh0aGlzLmRyYXdFdmVudHMpIHtcblx0XHRcdGZvciAoY29uc3QgY2hpbGQgb2YgZGVidWdEaXNwbGF5T2JqZWN0cy5ldmVudFRleHQuY2hpbGRyZW4pIHtcblx0XHRcdFx0Y2hpbGQuYWxwaGEgLT0gMC4wNTtcblx0XHRcdFx0Y2hpbGQueSAtPSAyO1xuXHRcdFx0fVxuXHRcdH1cblx0fVxuXG5cdHByaXZhdGUgZHJhd0JvbmVzRnVuYyAoc3BpbmU6IFNwaW5lLCBkZWJ1Z0Rpc3BsYXlPYmplY3RzOiBEZWJ1Z0Rpc3BsYXlPYmplY3RzLCBsaW5lV2lkdGg6IG51bWJlciwgc2NhbGU6IG51bWJlcik6IHZvaWQge1xuXHRcdGNvbnN0IHNrZWxldG9uID0gc3BpbmUuc2tlbGV0b247XG5cdFx0Y29uc3Qgc2tlbGV0b25YID0gc2tlbGV0b24ueDtcblx0XHRjb25zdCBza2VsZXRvblkgPSBza2VsZXRvbi55O1xuXHRcdGNvbnN0IGJvbmVzID0gc2tlbGV0b24uYm9uZXM7XG5cblx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnNrZWxldG9uWFkuc3Ryb2tlU3R5bGUgPSB7IHdpZHRoOiBsaW5lV2lkdGgsIGNvbG9yOiB0aGlzLnNrZWxldG9uWFlDb2xvciB9O1xuXG5cdFx0Zm9yIChsZXQgaSA9IDAsIGxlbiA9IGJvbmVzLmxlbmd0aDsgaSA8IGxlbjsgaSsrKSB7XG5cdFx0XHRjb25zdCBib25lID0gYm9uZXNbaV07XG5cdFx0XHRjb25zdCBib25lTGVuID0gYm9uZS5kYXRhLmxlbmd0aDtcblx0XHRcdGNvbnN0IHN0YXJYID0gc2tlbGV0b25YICsgYm9uZS53b3JsZFg7XG5cdFx0XHRjb25zdCBzdGFyWSA9IHNrZWxldG9uWSArIGJvbmUud29ybGRZO1xuXHRcdFx0Y29uc3QgZW5kWCA9IHNrZWxldG9uWCArIChib25lTGVuICogYm9uZS5hKSArIGJvbmUud29ybGRYO1xuXHRcdFx0Y29uc3QgZW5kWSA9IHNrZWxldG9uWSArIChib25lTGVuICogYm9uZS5iKSArIGJvbmUud29ybGRZO1xuXG5cdFx0XHRpZiAoYm9uZS5kYXRhLm5hbWUgPT09ICdyb290JyB8fCBib25lLmRhdGEucGFyZW50ID09PSBudWxsKSB7XG5cdFx0XHRcdGNvbnRpbnVlO1xuXHRcdFx0fVxuXG5cdFx0XHRjb25zdCB3ID0gTWF0aC5hYnMoc3RhclggLSBlbmRYKTtcblx0XHRcdGNvbnN0IGggPSBNYXRoLmFicyhzdGFyWSAtIGVuZFkpO1xuXHRcdFx0Ly8gYSA9IHcsIC8vIHNpZGUgbGVuZ3RoIGFcblx0XHRcdGNvbnN0IGEyID0gTWF0aC5wb3codywgMik7IC8vIHNxdWFyZSByb290IG9mIHNpZGUgbGVuZ3RoIGFcblx0XHRcdGNvbnN0IGIgPSBoOyAvLyBzaWRlIGxlbmd0aCBiXG5cdFx0XHRjb25zdCBiMiA9IE1hdGgucG93KGgsIDIpOyAvLyBzcXVhcmUgcm9vdCBvZiBzaWRlIGxlbmd0aCBiXG5cdFx0XHRjb25zdCBjID0gTWF0aC5zcXJ0KGEyICsgYjIpOyAvLyBzaWRlIGxlbmd0aCBjXG5cdFx0XHRjb25zdCBjMiA9IE1hdGgucG93KGMsIDIpOyAvLyBzcXVhcmUgcm9vdCBvZiBzaWRlIGxlbmd0aCBjXG5cdFx0XHRjb25zdCByYWQgPSBNYXRoLlBJIC8gMTgwO1xuXHRcdFx0Ly8gQSA9IE1hdGguYWNvcyhbYTIgKyBjMiAtIGIyXSAvIFsyICogYSAqIGNdKSB8fCAwLCAvLyBBbmdsZSBBXG5cdFx0XHQvLyBDID0gTWF0aC5hY29zKFthMiArIGIyIC0gYzJdIC8gWzIgKiBhICogYl0pIHx8IDAsIC8vIEMgYW5nbGVcblx0XHRcdGNvbnN0IEIgPSBNYXRoLmFjb3MoKGMyICsgYjIgLSBhMikgLyAoMiAqIGIgKiBjKSkgfHwgMDsgLy8gYW5nbGUgb2YgY29ybmVyIEJcblxuXHRcdFx0aWYgKGMgPT09IDApIHtcblx0XHRcdFx0Y29udGludWU7XG5cdFx0XHR9XG5cblx0XHRcdGNvbnN0IGdwID0gbmV3IEdyYXBoaWNzKCk7XG5cblx0XHRcdGRlYnVnRGlzcGxheU9iamVjdHMuYm9uZXMuYWRkQ2hpbGQoZ3ApO1xuXG5cdFx0XHQvLyBkcmF3IGJvbmVcblx0XHRcdGNvbnN0IHJlZlJhdGlvbiA9IGMgLyA1MCAvIHNjYWxlO1xuXG5cdFx0XHRncC5jb250ZXh0XG5cdFx0XHRcdC5wb2x5KFswLCAwLCAwIC0gcmVmUmF0aW9uLCBjIC0gKHJlZlJhdGlvbiAqIDMpLCAwLCBjIC0gcmVmUmF0aW9uLCAwICsgcmVmUmF0aW9uLCBjIC0gKHJlZlJhdGlvbiAqIDMpXSlcblx0XHRcdFx0LmZpbGwodGhpcy5ib25lc0NvbG9yKTtcblx0XHRcdGdwLnggPSBzdGFyWDtcblx0XHRcdGdwLnkgPSBzdGFyWTtcblx0XHRcdGdwLnBpdm90LnkgPSBjO1xuXG5cdFx0XHQvLyBDYWxjdWxhdGUgYm9uZSByb3RhdGlvbiBhbmdsZVxuXHRcdFx0bGV0IHJvdGF0aW9uID0gMDtcblxuXHRcdFx0aWYgKHN0YXJYIDwgZW5kWCAmJiBzdGFyWSA8IGVuZFkpIHtcblx0XHRcdFx0Ly8gYm90dG9tIHJpZ2h0XG5cdFx0XHRcdHJvdGF0aW9uID0gLUIgKyAoMTgwICogcmFkKTtcblx0XHRcdH1cblx0XHRcdGVsc2UgaWYgKHN0YXJYID4gZW5kWCAmJiBzdGFyWSA8IGVuZFkpIHtcblx0XHRcdFx0Ly8gYm90dG9tIGxlZnRcblx0XHRcdFx0cm90YXRpb24gPSAoMTgwICogcmFkKSArIEI7XG5cdFx0XHR9XG5cdFx0XHRlbHNlIGlmIChzdGFyWCA+IGVuZFggJiYgc3RhclkgPiBlbmRZKSB7XG5cdFx0XHRcdC8vIHRvcCBsZWZ0XG5cdFx0XHRcdHJvdGF0aW9uID0gLUI7XG5cdFx0XHR9XG5cdFx0XHRlbHNlIGlmIChzdGFyWCA8IGVuZFggJiYgc3RhclkgPiBlbmRZKSB7XG5cdFx0XHRcdC8vIGJvdHRvbSBsZWZ0XG5cdFx0XHRcdHJvdGF0aW9uID0gQjtcblx0XHRcdH1cblx0XHRcdGVsc2UgaWYgKHN0YXJZID09PSBlbmRZICYmIHN0YXJYIDwgZW5kWCkge1xuXHRcdFx0XHQvLyBUbyB0aGUgcmlnaHRcblx0XHRcdFx0cm90YXRpb24gPSA5MCAqIHJhZDtcblx0XHRcdH1cblx0XHRcdGVsc2UgaWYgKHN0YXJZID09PSBlbmRZICYmIHN0YXJYID4gZW5kWCkge1xuXHRcdFx0XHQvLyBnbyBsZWZ0XG5cdFx0XHRcdHJvdGF0aW9uID0gLTkwICogcmFkO1xuXHRcdFx0fVxuXHRcdFx0ZWxzZSBpZiAoc3RhclggPT09IGVuZFggJiYgc3RhclkgPCBlbmRZKSB7XG5cdFx0XHRcdC8vIGRvd25cblx0XHRcdFx0cm90YXRpb24gPSAxODAgKiByYWQ7XG5cdFx0XHR9XG5cdFx0XHRlbHNlIGlmIChzdGFyWCA9PT0gZW5kWCAmJiBzdGFyWSA+IGVuZFkpIHtcblx0XHRcdFx0Ly8gdXBcblx0XHRcdFx0cm90YXRpb24gPSAwO1xuXHRcdFx0fVxuXHRcdFx0Z3Aucm90YXRpb24gPSByb3RhdGlvbjtcblxuXHRcdFx0Ly8gRHJhdyB0aGUgc3RhcnRpbmcgcm90YXRpb24gcG9pbnQgb2YgdGhlIGJvbmVcblx0XHRcdGdwLmNpcmNsZSgwLCBjLCByZWZSYXRpb24gKiAxLjIpXG5cdFx0XHRcdC5maWxsKHsgY29sb3I6IDB4MDAwMDAwLCBhbHBoYTogMC42IH0pXG5cdFx0XHRcdC5zdHJva2UoeyB3aWR0aDogbGluZVdpZHRoICsgcmVmUmF0aW9uIC8gMi40LCBjb2xvcjogdGhpcy5ib25lc0NvbG9yIH0pO1xuXHRcdH1cblxuXHRcdC8vIERyYXcgdGhlIHNrZWxldG9uIHN0YXJ0aW5nIHBvaW50IFwiWFwiIGZvcm1cblx0XHRjb25zdCBzdGFydERvdFNpemUgPSBsaW5lV2lkdGggKiAzO1xuXG5cdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5za2VsZXRvblhZLmNvbnRleHRcblx0XHRcdC5tb3ZlVG8oc2tlbGV0b25YIC0gc3RhcnREb3RTaXplLCBza2VsZXRvblkgLSBzdGFydERvdFNpemUpXG5cdFx0XHQubGluZVRvKHNrZWxldG9uWCArIHN0YXJ0RG90U2l6ZSwgc2tlbGV0b25ZICsgc3RhcnREb3RTaXplKVxuXHRcdFx0Lm1vdmVUbyhza2VsZXRvblggKyBzdGFydERvdFNpemUsIHNrZWxldG9uWSAtIHN0YXJ0RG90U2l6ZSlcblx0XHRcdC5saW5lVG8oc2tlbGV0b25YIC0gc3RhcnREb3RTaXplLCBza2VsZXRvblkgKyBzdGFydERvdFNpemUpXG5cdFx0XHQuc3Ryb2tlKCk7XG5cdH1cblxuXHRwcml2YXRlIGRyYXdSZWdpb25BdHRhY2htZW50c0Z1bmMgKHNwaW5lOiBTcGluZSwgZGVidWdEaXNwbGF5T2JqZWN0czogRGVidWdEaXNwbGF5T2JqZWN0cywgbGluZVdpZHRoOiBudW1iZXIpOiB2b2lkIHtcblx0XHRjb25zdCBza2VsZXRvbiA9IHNwaW5lLnNrZWxldG9uO1xuXHRcdGNvbnN0IHNsb3RzID0gc2tlbGV0b24uc2xvdHM7XG5cblx0XHRmb3IgKGxldCBpID0gMCwgbGVuID0gc2xvdHMubGVuZ3RoOyBpIDwgbGVuOyBpKyspIHtcblx0XHRcdGNvbnN0IHNsb3QgPSBzbG90c1tpXTtcblx0XHRcdGNvbnN0IGF0dGFjaG1lbnQgPSBzbG90LmdldEF0dGFjaG1lbnQoKTtcblxuXHRcdFx0aWYgKGF0dGFjaG1lbnQgPT09IG51bGwgfHwgIShhdHRhY2htZW50IGluc3RhbmNlb2YgUmVnaW9uQXR0YWNobWVudCkpIHtcblx0XHRcdFx0Y29udGludWU7XG5cdFx0XHR9XG5cblx0XHRcdGNvbnN0IHJlZ2lvbkF0dGFjaG1lbnQgPSBhdHRhY2htZW50O1xuXG5cdFx0XHRjb25zdCB2ZXJ0aWNlcyA9IG5ldyBGbG9hdDMyQXJyYXkoOCk7XG5cblx0XHRcdHJlZ2lvbkF0dGFjaG1lbnQuY29tcHV0ZVdvcmxkVmVydGljZXMoc2xvdCwgdmVydGljZXMsIDAsIDIpO1xuXG5cdFx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnJlZ2lvbkF0dGFjaG1lbnRzU2hhcGUucG9seShBcnJheS5mcm9tKHZlcnRpY2VzLnNsaWNlKDAsIDgpKSk7XG5cdFx0fVxuXG5cdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5yZWdpb25BdHRhY2htZW50c1NoYXBlLnN0cm9rZSh7XG5cdFx0XHRjb2xvcjogdGhpcy5yZWdpb25BdHRhY2htZW50c0NvbG9yLFxuXHRcdFx0d2lkdGg6IGxpbmVXaWR0aFxuXHRcdH0pO1xuXHR9XG5cblx0cHJpdmF0ZSBkcmF3TWVzaEh1bGxBbmRNZXNoVHJpYW5nbGVzIChzcGluZTogU3BpbmUsIGRlYnVnRGlzcGxheU9iamVjdHM6IERlYnVnRGlzcGxheU9iamVjdHMsIGxpbmVXaWR0aDogbnVtYmVyKTogdm9pZCB7XG5cdFx0Y29uc3Qgc2tlbGV0b24gPSBzcGluZS5za2VsZXRvbjtcblx0XHRjb25zdCBzbG90cyA9IHNrZWxldG9uLnNsb3RzO1xuXG5cdFx0Zm9yIChsZXQgaSA9IDAsIGxlbiA9IHNsb3RzLmxlbmd0aDsgaSA8IGxlbjsgaSsrKSB7XG5cdFx0XHRjb25zdCBzbG90ID0gc2xvdHNbaV07XG5cblx0XHRcdGlmICghc2xvdC5ib25lLmFjdGl2ZSkge1xuXHRcdFx0XHRjb250aW51ZTtcblx0XHRcdH1cblx0XHRcdGNvbnN0IGF0dGFjaG1lbnQgPSBzbG90LmdldEF0dGFjaG1lbnQoKTtcblxuXHRcdFx0aWYgKGF0dGFjaG1lbnQgPT09IG51bGwgfHwgIShhdHRhY2htZW50IGluc3RhbmNlb2YgTWVzaEF0dGFjaG1lbnQpKSB7XG5cdFx0XHRcdGNvbnRpbnVlO1xuXHRcdFx0fVxuXG5cdFx0XHRjb25zdCBtZXNoQXR0YWNobWVudCA9IGF0dGFjaG1lbnQ7XG5cblx0XHRcdGNvbnN0IHZlcnRpY2VzID0gbmV3IEZsb2F0MzJBcnJheShtZXNoQXR0YWNobWVudC53b3JsZFZlcnRpY2VzTGVuZ3RoKTtcblx0XHRcdGNvbnN0IHRyaWFuZ2xlcyA9IG1lc2hBdHRhY2htZW50LnRyaWFuZ2xlcztcblx0XHRcdGxldCBodWxsTGVuZ3RoID0gbWVzaEF0dGFjaG1lbnQuaHVsbExlbmd0aDtcblxuXHRcdFx0bWVzaEF0dGFjaG1lbnQuY29tcHV0ZVdvcmxkVmVydGljZXMoc2xvdCwgMCwgbWVzaEF0dGFjaG1lbnQud29ybGRWZXJ0aWNlc0xlbmd0aCwgdmVydGljZXMsIDAsIDIpO1xuXHRcdFx0Ly8gZHJhdyB0aGUgc2tpbm5lZCBtZXNoICh0cmlhbmdsZSlcblx0XHRcdGlmICh0aGlzLmRyYXdNZXNoVHJpYW5nbGVzKSB7XG5cdFx0XHRcdGZvciAobGV0IGkgPSAwLCBsZW4gPSB0cmlhbmdsZXMubGVuZ3RoOyBpIDwgbGVuOyBpICs9IDMpIHtcblx0XHRcdFx0XHRjb25zdCB2MSA9IHRyaWFuZ2xlc1tpXSAqIDI7XG5cdFx0XHRcdFx0Y29uc3QgdjIgPSB0cmlhbmdsZXNbaSArIDFdICogMjtcblx0XHRcdFx0XHRjb25zdCB2MyA9IHRyaWFuZ2xlc1tpICsgMl0gKiAyO1xuXG5cdFx0XHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5tZXNoVHJpYW5nbGVzTGluZS5jb250ZXh0XG5cdFx0XHRcdFx0XHQubW92ZVRvKHZlcnRpY2VzW3YxXSwgdmVydGljZXNbdjEgKyAxXSlcblx0XHRcdFx0XHRcdC5saW5lVG8odmVydGljZXNbdjJdLCB2ZXJ0aWNlc1t2MiArIDFdKVxuXHRcdFx0XHRcdFx0LmxpbmVUbyh2ZXJ0aWNlc1t2M10sIHZlcnRpY2VzW3YzICsgMV0pO1xuXHRcdFx0XHR9XG5cdFx0XHR9XG5cblx0XHRcdC8vIGRyYXcgc2tpbiBib3JkZXJcblx0XHRcdGlmICh0aGlzLmRyYXdNZXNoSHVsbCAmJiBodWxsTGVuZ3RoID4gMCkge1xuXHRcdFx0XHRodWxsTGVuZ3RoID0gKGh1bGxMZW5ndGggPj4gMSkgKiAyO1xuXHRcdFx0XHRsZXQgbGFzdFggPSB2ZXJ0aWNlc1todWxsTGVuZ3RoIC0gMl07XG5cdFx0XHRcdGxldCBsYXN0WSA9IHZlcnRpY2VzW2h1bGxMZW5ndGggLSAxXTtcblxuXHRcdFx0XHRmb3IgKGxldCBpID0gMCwgbGVuID0gaHVsbExlbmd0aDsgaSA8IGxlbjsgaSArPSAyKSB7XG5cdFx0XHRcdFx0Y29uc3QgeCA9IHZlcnRpY2VzW2ldO1xuXHRcdFx0XHRcdGNvbnN0IHkgPSB2ZXJ0aWNlc1tpICsgMV07XG5cblx0XHRcdFx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLm1lc2hIdWxsTGluZS5jb250ZXh0XG5cdFx0XHRcdFx0XHQubW92ZVRvKHgsIHkpXG5cdFx0XHRcdFx0XHQubGluZVRvKGxhc3RYLCBsYXN0WSk7XG5cdFx0XHRcdFx0bGFzdFggPSB4O1xuXHRcdFx0XHRcdGxhc3RZID0geTtcblx0XHRcdFx0fVxuXHRcdFx0fVxuXHRcdH1cblxuXHRcdGRlYnVnRGlzcGxheU9iamVjdHMubWVzaEh1bGxMaW5lLnN0cm9rZSh7IHdpZHRoOiBsaW5lV2lkdGgsIGNvbG9yOiB0aGlzLm1lc2hIdWxsQ29sb3IgfSk7XG5cdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5tZXNoVHJpYW5nbGVzTGluZS5zdHJva2UoeyB3aWR0aDogbGluZVdpZHRoLCBjb2xvcjogdGhpcy5tZXNoVHJpYW5nbGVzQ29sb3IgfSk7XG5cdH1cblxuXHRkcmF3Q2xpcHBpbmdGdW5jIChzcGluZTogU3BpbmUsIGRlYnVnRGlzcGxheU9iamVjdHM6IERlYnVnRGlzcGxheU9iamVjdHMsIGxpbmVXaWR0aDogbnVtYmVyKTogdm9pZCB7XG5cdFx0Y29uc3Qgc2tlbGV0b24gPSBzcGluZS5za2VsZXRvbjtcblx0XHRjb25zdCBzbG90cyA9IHNrZWxldG9uLnNsb3RzO1xuXG5cdFx0Zm9yIChsZXQgaSA9IDAsIGxlbiA9IHNsb3RzLmxlbmd0aDsgaSA8IGxlbjsgaSsrKSB7XG5cdFx0XHRjb25zdCBzbG90ID0gc2xvdHNbaV07XG5cblx0XHRcdGlmICghc2xvdC5ib25lLmFjdGl2ZSkge1xuXHRcdFx0XHRjb250aW51ZTtcblx0XHRcdH1cblx0XHRcdGNvbnN0IGF0dGFjaG1lbnQgPSBzbG90LmdldEF0dGFjaG1lbnQoKTtcblxuXHRcdFx0aWYgKGF0dGFjaG1lbnQgPT09IG51bGwgfHwgIShhdHRhY2htZW50IGluc3RhbmNlb2YgQ2xpcHBpbmdBdHRhY2htZW50KSkge1xuXHRcdFx0XHRjb250aW51ZTtcblx0XHRcdH1cblxuXHRcdFx0Y29uc3QgY2xpcHBpbmdBdHRhY2htZW50ID0gYXR0YWNobWVudDtcblxuXHRcdFx0Y29uc3Qgbm4gPSBjbGlwcGluZ0F0dGFjaG1lbnQud29ybGRWZXJ0aWNlc0xlbmd0aDtcblx0XHRcdGNvbnN0IHdvcmxkID0gbmV3IEZsb2F0MzJBcnJheShubik7XG5cblx0XHRcdGNsaXBwaW5nQXR0YWNobWVudC5jb21wdXRlV29ybGRWZXJ0aWNlcyhzbG90LCAwLCBubiwgd29ybGQsIDAsIDIpO1xuXHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5jbGlwcGluZ1BvbHlnb24ucG9seShBcnJheS5mcm9tKHdvcmxkKSk7XG5cdFx0fVxuXG5cdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5jbGlwcGluZ1BvbHlnb24uc3Ryb2tlKHtcblx0XHRcdHdpZHRoOiBsaW5lV2lkdGgsIGNvbG9yOiB0aGlzLmNsaXBwaW5nUG9seWdvbkNvbG9yLCBhbHBoYTogMVxuXHRcdH0pO1xuXHR9XG5cblx0ZHJhd0JvdW5kaW5nQm94ZXNGdW5jIChzcGluZTogU3BpbmUsIGRlYnVnRGlzcGxheU9iamVjdHM6IERlYnVnRGlzcGxheU9iamVjdHMsIGxpbmVXaWR0aDogbnVtYmVyKTogdm9pZCB7XG5cdFx0Ly8gZHJhdyB0aGUgdG90YWwgb3V0bGluZSBvZiB0aGUgYm91bmRpbmcgYm94XG5cdFx0Y29uc3QgYm91bmRzID0gbmV3IFNrZWxldG9uQm91bmRzKCk7XG5cdFx0Ym91bmRzLnVwZGF0ZShzcGluZS5za2VsZXRvbiwgdHJ1ZSk7XG5cblx0XHRpZiAoYm91bmRzLm1pblggIT09IEluZmluaXR5KSB7XG5cdFx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLmJvdW5kaW5nQm94ZXNSZWN0XG5cdFx0XHRcdC5yZWN0KGJvdW5kcy5taW5YLCBib3VuZHMubWluWSwgYm91bmRzLmdldFdpZHRoKCksIGJvdW5kcy5nZXRIZWlnaHQoKSlcblx0XHRcdFx0LnN0cm9rZSh7IHdpZHRoOiBsaW5lV2lkdGgsIGNvbG9yOiB0aGlzLmJvdW5kaW5nQm94ZXNSZWN0Q29sb3IgfSk7XG5cdFx0fVxuXG5cdFx0Y29uc3QgcG9seWdvbnMgPSBib3VuZHMucG9seWdvbnM7XG5cdFx0Y29uc3QgZHJhd1BvbHlnb24gPSAocG9seWdvblZlcnRpY2VzOiBBcnJheUxpa2U8bnVtYmVyPiwgX29mZnNldDogdW5rbm93biwgY291bnQ6IG51bWJlcik6IHZvaWQgPT4ge1xuXHRcdFx0aWYgKGNvdW50IDwgMykge1xuXHRcdFx0XHR0aHJvdyBuZXcgRXJyb3IoJ1BvbHlnb24gbXVzdCBjb250YWluIGF0IGxlYXN0IDMgdmVydGljZXMnKTtcblx0XHRcdH1cblx0XHRcdGNvbnN0IHBhdGhzOiBudW1iZXJbXSA9IFtdO1xuXHRcdFx0Y29uc3QgZG90U2l6ZSA9IGxpbmVXaWR0aCAqIDI7XG5cblx0XHRcdGZvciAobGV0IGkgPSAwLCBsZW4gPSBwb2x5Z29uVmVydGljZXMubGVuZ3RoOyBpIDwgbGVuOyBpICs9IDIpIHtcblx0XHRcdFx0Y29uc3QgeDEgPSBwb2x5Z29uVmVydGljZXNbaV07XG5cdFx0XHRcdGNvbnN0IHkxID0gcG9seWdvblZlcnRpY2VzW2kgKyAxXTtcblxuXHRcdFx0XHQvLyBkcmF3IHRoZSBib3VuZGluZyBib3ggbm9kZVxuXHRcdFx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLmJvdW5kaW5nQm94ZXNDaXJjbGUuYmVnaW5GaWxsKHRoaXMuYm91bmRpbmdCb3hlc0NpcmNsZUNvbG9yKTtcblx0XHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5ib3VuZGluZ0JveGVzQ2lyY2xlLmRyYXdDaXJjbGUoeDEsIHkxLCBkb3RTaXplKTtcblx0XHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5ib3VuZGluZ0JveGVzQ2lyY2xlLmZpbGwoMCk7XG5cblx0XHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5ib3VuZGluZ0JveGVzQ2lyY2xlXG5cdFx0XHRcdFx0LmNpcmNsZSh4MSwgeTEsIGRvdFNpemUpXG5cdFx0XHRcdFx0LmZpbGwoeyBjb2xvcjogdGhpcy5ib3VuZGluZ0JveGVzQ2lyY2xlQ29sb3IgfSlcblxuXHRcdFx0XHRwYXRocy5wdXNoKHgxLCB5MSk7XG5cdFx0XHR9XG5cblx0XHRcdC8vIGRyYXcgdGhlIGJvdW5kaW5nIGJveCBhcmVhXG5cdFx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLmJvdW5kaW5nQm94ZXNQb2x5Z29uXG5cdFx0XHRcdC5wb2x5KHBhdGhzKVxuXHRcdFx0XHQuZmlsbCh7XG5cdFx0XHRcdFx0Y29sb3I6IHRoaXMuYm91bmRpbmdCb3hlc1BvbHlnb25Db2xvcixcblx0XHRcdFx0XHRhbHBoYTogMC4xXG5cdFx0XHRcdH0pXG5cdFx0XHRcdC5zdHJva2Uoe1xuXHRcdFx0XHRcdHdpZHRoOiBsaW5lV2lkdGgsXG5cdFx0XHRcdFx0Y29sb3I6IHRoaXMuYm91bmRpbmdCb3hlc1BvbHlnb25Db2xvclxuXHRcdFx0XHR9KTtcblx0XHR9O1xuXG5cdFx0Zm9yIChsZXQgaSA9IDAsIGxlbiA9IHBvbHlnb25zLmxlbmd0aDsgaSA8IGxlbjsgaSsrKSB7XG5cdFx0XHRjb25zdCBwb2x5Z29uID0gcG9seWdvbnNbaV07XG5cblx0XHRcdGRyYXdQb2x5Z29uKHBvbHlnb24sIDAsIHBvbHlnb24ubGVuZ3RoKTtcblx0XHR9XG5cdH1cblxuXHRwcml2YXRlIGRyYXdQYXRoc0Z1bmMgKHNwaW5lOiBTcGluZSwgZGVidWdEaXNwbGF5T2JqZWN0czogRGVidWdEaXNwbGF5T2JqZWN0cywgbGluZVdpZHRoOiBudW1iZXIpOiB2b2lkIHtcblx0XHRjb25zdCBza2VsZXRvbiA9IHNwaW5lLnNrZWxldG9uO1xuXHRcdGNvbnN0IHNsb3RzID0gc2tlbGV0b24uc2xvdHM7XG5cblx0XHRmb3IgKGxldCBpID0gMCwgbGVuID0gc2xvdHMubGVuZ3RoOyBpIDwgbGVuOyBpKyspIHtcblx0XHRcdGNvbnN0IHNsb3QgPSBzbG90c1tpXTtcblxuXHRcdFx0aWYgKCFzbG90LmJvbmUuYWN0aXZlKSB7XG5cdFx0XHRcdGNvbnRpbnVlO1xuXHRcdFx0fVxuXHRcdFx0Y29uc3QgYXR0YWNobWVudCA9IHNsb3QuZ2V0QXR0YWNobWVudCgpO1xuXG5cdFx0XHRpZiAoYXR0YWNobWVudCA9PT0gbnVsbCB8fCAhKGF0dGFjaG1lbnQgaW5zdGFuY2VvZiBQYXRoQXR0YWNobWVudCkpIHtcblx0XHRcdFx0Y29udGludWU7XG5cdFx0XHR9XG5cblx0XHRcdGNvbnN0IHBhdGhBdHRhY2htZW50ID0gYXR0YWNobWVudDtcblx0XHRcdGxldCBubiA9IHBhdGhBdHRhY2htZW50LndvcmxkVmVydGljZXNMZW5ndGg7XG5cdFx0XHRjb25zdCB3b3JsZCA9IG5ldyBGbG9hdDMyQXJyYXkobm4pO1xuXG5cdFx0XHRwYXRoQXR0YWNobWVudC5jb21wdXRlV29ybGRWZXJ0aWNlcyhzbG90LCAwLCBubiwgd29ybGQsIDAsIDIpO1xuXHRcdFx0bGV0IHgxID0gd29ybGRbMl07XG5cdFx0XHRsZXQgeTEgPSB3b3JsZFszXTtcblx0XHRcdGxldCB4MiA9IDA7XG5cdFx0XHRsZXQgeTIgPSAwO1xuXG5cdFx0XHRpZiAocGF0aEF0dGFjaG1lbnQuY2xvc2VkKSB7XG5cdFx0XHRcdGNvbnN0IGN4MSA9IHdvcmxkWzBdO1xuXHRcdFx0XHRjb25zdCBjeTEgPSB3b3JsZFsxXTtcblx0XHRcdFx0Y29uc3QgY3gyID0gd29ybGRbbm4gLSAyXTtcblx0XHRcdFx0Y29uc3QgY3kyID0gd29ybGRbbm4gLSAxXTtcblxuXHRcdFx0XHR4MiA9IHdvcmxkW25uIC0gNF07XG5cdFx0XHRcdHkyID0gd29ybGRbbm4gLSAzXTtcblxuXHRcdFx0XHQvLyBjdXJ2ZVxuXHRcdFx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhdGhzQ3VydmUubW92ZVRvKHgxLCB5MSk7XG5cdFx0XHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGF0aHNDdXJ2ZS5iZXppZXJDdXJ2ZVRvKGN4MSwgY3kxLCBjeDIsIGN5MiwgeDIsIHkyKTtcblxuXHRcdFx0XHQvLyBoYW5kbGVcblx0XHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5wYXRoc0xpbmUubW92ZVRvKHgxLCB5MSk7XG5cdFx0XHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGF0aHNMaW5lLmxpbmVUbyhjeDEsIGN5MSk7XG5cdFx0XHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGF0aHNMaW5lLm1vdmVUbyh4MiwgeTIpO1xuXHRcdFx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhdGhzTGluZS5saW5lVG8oY3gyLCBjeTIpO1xuXHRcdFx0fVxuXHRcdFx0bm4gLT0gNDtcblx0XHRcdGZvciAobGV0IGlpID0gNDsgaWkgPCBubjsgaWkgKz0gNikge1xuXHRcdFx0XHRjb25zdCBjeDEgPSB3b3JsZFtpaV07XG5cdFx0XHRcdGNvbnN0IGN5MSA9IHdvcmxkW2lpICsgMV07XG5cdFx0XHRcdGNvbnN0IGN4MiA9IHdvcmxkW2lpICsgMl07XG5cdFx0XHRcdGNvbnN0IGN5MiA9IHdvcmxkW2lpICsgM107XG5cblx0XHRcdFx0eDIgPSB3b3JsZFtpaSArIDRdO1xuXHRcdFx0XHR5MiA9IHdvcmxkW2lpICsgNV07XG5cdFx0XHRcdC8vIGN1cnZlXG5cdFx0XHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGF0aHNDdXJ2ZS5tb3ZlVG8oeDEsIHkxKTtcblx0XHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5wYXRoc0N1cnZlLmJlemllckN1cnZlVG8oY3gxLCBjeTEsIGN4MiwgY3kyLCB4MiwgeTIpO1xuXG5cdFx0XHRcdC8vIGhhbmRsZVxuXHRcdFx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhdGhzTGluZS5tb3ZlVG8oeDEsIHkxKTtcblx0XHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5wYXRoc0xpbmUubGluZVRvKGN4MSwgY3kxKTtcblx0XHRcdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5wYXRoc0xpbmUubW92ZVRvKHgyLCB5Mik7XG5cdFx0XHRcdGRlYnVnRGlzcGxheU9iamVjdHMucGF0aHNMaW5lLmxpbmVUbyhjeDIsIGN5Mik7XG5cdFx0XHRcdHgxID0geDI7XG5cdFx0XHRcdHkxID0geTI7XG5cdFx0XHR9XG5cdFx0fVxuXG5cdFx0ZGVidWdEaXNwbGF5T2JqZWN0cy5wYXRoc0N1cnZlLnN0cm9rZSh7IHdpZHRoOiBsaW5lV2lkdGgsIGNvbG9yOiB0aGlzLnBhdGhzQ3VydmVDb2xvciB9KTtcblx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhdGhzTGluZS5zdHJva2UoeyB3aWR0aDogbGluZVdpZHRoLCBjb2xvcjogdGhpcy5wYXRoc0xpbmVDb2xvciB9KTtcblx0fVxuXG5cdHB1YmxpYyB1bnJlZ2lzdGVyU3BpbmUgKHNwaW5lOiBTcGluZSk6IHZvaWQge1xuXHRcdGlmICghdGhpcy5yZWdpc3RlcmVkU3BpbmVzLmhhcyhzcGluZSkpIHtcblx0XHRcdGNvbnNvbGUud2FybignU3BpbmVEZWJ1Z1JlbmRlcmVyLnVucmVnaXN0ZXJTcGluZSgpIC0gc3BpbmUgaXMgbm90IHJlZ2lzdGVyZWQsIGNhblxcJ3QgdW5yZWdpc3RlciEnLCBzcGluZSk7XG5cdFx0fVxuXHRcdGNvbnN0IGRlYnVnRGlzcGxheU9iamVjdHMgPSB0aGlzLnJlZ2lzdGVyZWRTcGluZXMuZ2V0KHNwaW5lKTtcblxuXHRcdGlmICghZGVidWdEaXNwbGF5T2JqZWN0cykge1xuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblxuXHRcdHNwaW5lLnN0YXRlLnJlbW92ZUxpc3RlbmVyKGRlYnVnRGlzcGxheU9iamVjdHMuZXZlbnRDYWxsYmFjayk7XG5cblx0XHRkZWJ1Z0Rpc3BsYXlPYmplY3RzLnBhcmVudERlYnVnQ29udGFpbmVyLmRlc3Ryb3koeyB0ZXh0dXJlU291cmNlOiB0cnVlLCBjaGlsZHJlbjogdHJ1ZSwgdGV4dHVyZTogdHJ1ZSB9KTtcblx0XHR0aGlzLnJlZ2lzdGVyZWRTcGluZXMuZGVsZXRlKHNwaW5lKTtcblx0fVxufVxuIl19