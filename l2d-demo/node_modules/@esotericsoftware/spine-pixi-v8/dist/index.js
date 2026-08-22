/******************************************************************************
 * Spine Runtimes License Agreement
 * Last updated September 24, 2021. Replaces all prior versions.
 *
 * Copyright (c) 2013-2021, Esoteric Software LLC
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
import './require-shim.js'; // Side effects add require pixi.js to global scope
import './assets/atlasLoader.js'; // Side effects install the loaders into pixi
import './assets/skeletonLoader.js'; // Side effects install the loaders into pixi
import './darktint/DarkTintBatcher.js'; // Side effects install the batcher into pixi
import './SpinePipe.js';
export * from './assets/atlasLoader.js';
export * from './assets/skeletonLoader.js';
export * from './require-shim.js';
export * from './Spine.js';
export * from './SpineDebugRenderer.js';
export * from './SpinePipe.js';
export * from './SpineTexture.js';
export * from '@esotericsoftware/spine-core';
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiaW5kZXguanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyIuLi9zcmMvaW5kZXgudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OzsrRUEyQitFO0FBRS9FLE9BQU8sbUJBQW1CLENBQUMsQ0FBQyxtREFBbUQ7QUFDL0UsT0FBTyx5QkFBeUIsQ0FBQyxDQUFDLDZDQUE2QztBQUMvRSxPQUFPLDRCQUE0QixDQUFDLENBQUMsNkNBQTZDO0FBQ2xGLE9BQU8sK0JBQStCLENBQUMsQ0FBQyw2Q0FBNkM7QUFDckYsT0FBTyxnQkFBZ0IsQ0FBQztBQUV4QixjQUFjLHlCQUF5QixDQUFDO0FBQ3hDLGNBQWMsNEJBQTRCLENBQUM7QUFDM0MsY0FBYyxtQkFBbUIsQ0FBQztBQUNsQyxjQUFjLFlBQVksQ0FBQztBQUMzQixjQUFjLHlCQUF5QixDQUFDO0FBQ3hDLGNBQWMsZ0JBQWdCLENBQUM7QUFDL0IsY0FBYyxtQkFBbUIsQ0FBQztBQUNsQyxjQUFjLDhCQUE4QixDQUFDIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBTZXB0ZW1iZXIgMjQsIDIwMjEuIFJlcGxhY2VzIGFsbCBwcmlvciB2ZXJzaW9ucy5cbiAqXG4gKiBDb3B5cmlnaHQgKGMpIDIwMTMtMjAyMSwgRXNvdGVyaWMgU29mdHdhcmUgTExDXG4gKlxuICogSW50ZWdyYXRpb24gb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmUgb3Igb3RoZXJ3aXNlIGNyZWF0aW5nXG4gKiBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpcyBwZXJtaXR0ZWQgdW5kZXIgdGhlIHRlcm1zIGFuZFxuICogY29uZGl0aW9ucyBvZiBTZWN0aW9uIDIgb2YgdGhlIFNwaW5lIEVkaXRvciBMaWNlbnNlIEFncmVlbWVudDpcbiAqIGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9zcGluZS1lZGl0b3ItbGljZW5zZVxuICpcbiAqIE90aGVyd2lzZSwgaXQgaXMgcGVybWl0dGVkIHRvIGludGVncmF0ZSB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZVxuICogb3Igb3RoZXJ3aXNlIGNyZWF0ZSBkZXJpdmF0aXZlIHdvcmtzIG9mIHRoZSBTcGluZSBSdW50aW1lcyAoY29sbGVjdGl2ZWx5LFxuICogXCJQcm9kdWN0c1wiKSwgcHJvdmlkZWQgdGhhdCBlYWNoIHVzZXIgb2YgdGhlIFByb2R1Y3RzIG11c3Qgb2J0YWluIHRoZWlyIG93blxuICogU3BpbmUgRWRpdG9yIGxpY2Vuc2UgYW5kIHJlZGlzdHJpYnV0aW9uIG9mIHRoZSBQcm9kdWN0cyBpbiBhbnkgZm9ybSBtdXN0XG4gKiBpbmNsdWRlIHRoaXMgbGljZW5zZSBhbmQgY29weXJpZ2h0IG5vdGljZS5cbiAqXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMgQVJFIFBST1ZJREVEIEJZIEVTT1RFUklDIFNPRlRXQVJFIExMQyBcIkFTIElTXCIgQU5EIEFOWVxuICogRVhQUkVTUyBPUiBJTVBMSUVEIFdBUlJBTlRJRVMsIElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBUSEUgSU1QTElFRFxuICogV0FSUkFOVElFUyBPRiBNRVJDSEFOVEFCSUxJVFkgQU5EIEZJVE5FU1MgRk9SIEEgUEFSVElDVUxBUiBQVVJQT1NFIEFSRVxuICogRElTQ0xBSU1FRC4gSU4gTk8gRVZFTlQgU0hBTEwgRVNPVEVSSUMgU09GVFdBUkUgTExDIEJFIExJQUJMRSBGT1IgQU5ZXG4gKiBESVJFQ1QsIElORElSRUNULCBJTkNJREVOVEFMLCBTUEVDSUFMLCBFWEVNUExBUlksIE9SIENPTlNFUVVFTlRJQUwgREFNQUdFU1xuICogKElOQ0xVRElORywgQlVUIE5PVCBMSU1JVEVEIFRPLCBQUk9DVVJFTUVOVCBPRiBTVUJTVElUVVRFIEdPT0RTIE9SIFNFUlZJQ0VTLFxuICogQlVTSU5FU1MgSU5URVJSVVBUSU9OLCBPUiBMT1NTIE9GIFVTRSwgREFUQSwgT1IgUFJPRklUUykgSE9XRVZFUiBDQVVTRUQgQU5EXG4gKiBPTiBBTlkgVEhFT1JZIE9GIExJQUJJTElUWSwgV0hFVEhFUiBJTiBDT05UUkFDVCwgU1RSSUNUIExJQUJJTElUWSwgT1IgVE9SVFxuICogKElOQ0xVRElORyBORUdMSUdFTkNFIE9SIE9USEVSV0lTRSkgQVJJU0lORyBJTiBBTlkgV0FZIE9VVCBPRiBUSEUgVVNFIE9GXG4gKiBUSEUgU1BJTkUgUlVOVElNRVMsIEVWRU4gSUYgQURWSVNFRCBPRiBUSEUgUE9TU0lCSUxJVFkgT0YgU1VDSCBEQU1BR0UuXG4gKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKiovXG5cbmltcG9ydCAnLi9yZXF1aXJlLXNoaW0uanMnOyAvLyBTaWRlIGVmZmVjdHMgYWRkIHJlcXVpcmUgcGl4aS5qcyB0byBnbG9iYWwgc2NvcGVcbmltcG9ydCAnLi9hc3NldHMvYXRsYXNMb2FkZXIuanMnOyAvLyBTaWRlIGVmZmVjdHMgaW5zdGFsbCB0aGUgbG9hZGVycyBpbnRvIHBpeGlcbmltcG9ydCAnLi9hc3NldHMvc2tlbGV0b25Mb2FkZXIuanMnOyAvLyBTaWRlIGVmZmVjdHMgaW5zdGFsbCB0aGUgbG9hZGVycyBpbnRvIHBpeGlcbmltcG9ydCAnLi9kYXJrdGludC9EYXJrVGludEJhdGNoZXIuanMnOyAvLyBTaWRlIGVmZmVjdHMgaW5zdGFsbCB0aGUgYmF0Y2hlciBpbnRvIHBpeGlcbmltcG9ydCAnLi9TcGluZVBpcGUuanMnO1xuXG5leHBvcnQgKiBmcm9tICcuL2Fzc2V0cy9hdGxhc0xvYWRlci5qcyc7XG5leHBvcnQgKiBmcm9tICcuL2Fzc2V0cy9za2VsZXRvbkxvYWRlci5qcyc7XG5leHBvcnQgKiBmcm9tICcuL3JlcXVpcmUtc2hpbS5qcyc7XG5leHBvcnQgKiBmcm9tICcuL1NwaW5lLmpzJztcbmV4cG9ydCAqIGZyb20gJy4vU3BpbmVEZWJ1Z1JlbmRlcmVyLmpzJztcbmV4cG9ydCAqIGZyb20gJy4vU3BpbmVQaXBlLmpzJztcbmV4cG9ydCAqIGZyb20gJy4vU3BpbmVUZXh0dXJlLmpzJztcbmV4cG9ydCAqIGZyb20gJ0Blc290ZXJpY3NvZnR3YXJlL3NwaW5lLWNvcmUnO1xuIl19