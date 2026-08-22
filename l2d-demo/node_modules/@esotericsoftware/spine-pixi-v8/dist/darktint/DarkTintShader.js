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
import { colorBit, colorBitGl, compileHighShaderGlProgram, compileHighShaderGpuProgram, generateTextureBatchBit, generateTextureBatchBitGl, getBatchSamplersUniformGroup, roundPixelsBit, roundPixelsBitGl, Shader } from 'pixi.js';
import { darkTintBit, darkTintBitGl } from './darkTintBit.js';
export class DarkTintShader extends Shader {
    constructor(maxTextures) {
        const glProgram = compileHighShaderGlProgram({
            name: 'dark-tint-batch',
            bits: [
                colorBitGl,
                darkTintBitGl,
                generateTextureBatchBitGl(maxTextures),
                roundPixelsBitGl,
            ]
        });
        const gpuProgram = compileHighShaderGpuProgram({
            name: 'dark-tint-batch',
            bits: [
                colorBit,
                darkTintBit,
                generateTextureBatchBit(maxTextures),
                roundPixelsBit,
            ]
        });
        super({
            glProgram,
            gpuProgram,
            resources: {
                batchSamplers: getBatchSamplersUniformGroup(maxTextures),
            }
        });
    }
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiRGFya1RpbnRTaGFkZXIuanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyIuLi8uLi9zcmMvZGFya3RpbnQvRGFya1RpbnRTaGFkZXIudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OzsrRUEyQitFO0FBRS9FLE9BQU8sRUFDTixRQUFRLEVBQ1IsVUFBVSxFQUNWLDBCQUEwQixFQUMxQiwyQkFBMkIsRUFDM0IsdUJBQXVCLEVBQ3ZCLHlCQUF5QixFQUN6Qiw0QkFBNEIsRUFDNUIsY0FBYyxFQUNkLGdCQUFnQixFQUNoQixNQUFNLEVBQ04sTUFBTSxTQUFTLENBQUM7QUFDakIsT0FBTyxFQUFFLFdBQVcsRUFBRSxhQUFhLEVBQUUsTUFBTSxrQkFBa0IsQ0FBQztBQUU5RCxNQUFNLE9BQU8sY0FBZSxTQUFRLE1BQU07SUFDekMsWUFBYSxXQUFtQjtRQUMvQixNQUFNLFNBQVMsR0FBRywwQkFBMEIsQ0FBQztZQUM1QyxJQUFJLEVBQUUsaUJBQWlCO1lBQ3ZCLElBQUksRUFBRTtnQkFDTCxVQUFVO2dCQUNWLGFBQWE7Z0JBQ2IseUJBQXlCLENBQUMsV0FBVyxDQUFDO2dCQUN0QyxnQkFBZ0I7YUFDaEI7U0FDRCxDQUFDLENBQUM7UUFFSCxNQUFNLFVBQVUsR0FBRywyQkFBMkIsQ0FBQztZQUM5QyxJQUFJLEVBQUUsaUJBQWlCO1lBQ3ZCLElBQUksRUFBRTtnQkFDTCxRQUFRO2dCQUNSLFdBQVc7Z0JBQ1gsdUJBQXVCLENBQUMsV0FBVyxDQUFDO2dCQUNwQyxjQUFjO2FBQ2Q7U0FDRCxDQUFDLENBQUM7UUFFSCxLQUFLLENBQUM7WUFDTCxTQUFTO1lBQ1QsVUFBVTtZQUNWLFNBQVMsRUFBRTtnQkFDVixhQUFhLEVBQUUsNEJBQTRCLENBQUMsV0FBVyxDQUFDO2FBQ3hEO1NBQ0QsQ0FBQyxDQUFDO0lBQ0osQ0FBQztDQUNEIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBBcHJpbCA1LCAyMDI1LiBSZXBsYWNlcyBhbGwgcHJpb3IgdmVyc2lvbnMuXG4gKlxuICogQ29weXJpZ2h0IChjKSAyMDEzLTIwMjUsIEVzb3RlcmljIFNvZnR3YXJlIExMQ1xuICpcbiAqIEludGVncmF0aW9uIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlIG9yIG90aGVyd2lzZSBjcmVhdGluZ1xuICogZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgaXMgcGVybWl0dGVkIHVuZGVyIHRoZSB0ZXJtcyBhbmRcbiAqIGNvbmRpdGlvbnMgb2YgU2VjdGlvbiAyIG9mIHRoZSBTcGluZSBFZGl0b3IgTGljZW5zZSBBZ3JlZW1lbnQ6XG4gKiBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtZWRpdG9yLWxpY2Vuc2VcbiAqXG4gKiBPdGhlcndpc2UsIGl0IGlzIHBlcm1pdHRlZCB0byBpbnRlZ3JhdGUgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmVcbiAqIG9yIG90aGVyd2lzZSBjcmVhdGUgZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgKGNvbGxlY3RpdmVseSxcbiAqIFwiUHJvZHVjdHNcIiksIHByb3ZpZGVkIHRoYXQgZWFjaCB1c2VyIG9mIHRoZSBQcm9kdWN0cyBtdXN0IG9idGFpbiB0aGVpciBvd25cbiAqIFNwaW5lIEVkaXRvciBsaWNlbnNlIGFuZCByZWRpc3RyaWJ1dGlvbiBvZiB0aGUgUHJvZHVjdHMgaW4gYW55IGZvcm0gbXVzdFxuICogaW5jbHVkZSB0aGlzIGxpY2Vuc2UgYW5kIGNvcHlyaWdodCBub3RpY2UuXG4gKlxuICogVEhFIFNQSU5FIFJVTlRJTUVTIEFSRSBQUk9WSURFRCBCWSBFU09URVJJQyBTT0ZUV0FSRSBMTEMgXCJBUyBJU1wiIEFORCBBTllcbiAqIEVYUFJFU1MgT1IgSU1QTElFRCBXQVJSQU5USUVTLCBJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgVEhFIElNUExJRURcbiAqIFdBUlJBTlRJRVMgT0YgTUVSQ0hBTlRBQklMSVRZIEFORCBGSVRORVNTIEZPUiBBIFBBUlRJQ1VMQVIgUFVSUE9TRSBBUkVcbiAqIERJU0NMQUlNRUQuIElOIE5PIEVWRU5UIFNIQUxMIEVTT1RFUklDIFNPRlRXQVJFIExMQyBCRSBMSUFCTEUgRk9SIEFOWVxuICogRElSRUNULCBJTkRJUkVDVCwgSU5DSURFTlRBTCwgU1BFQ0lBTCwgRVhFTVBMQVJZLCBPUiBDT05TRVFVRU5USUFMIERBTUFHRVNcbiAqIChJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgUFJPQ1VSRU1FTlQgT0YgU1VCU1RJVFVURSBHT09EUyBPUiBTRVJWSUNFUyxcbiAqIEJVU0lORVNTIElOVEVSUlVQVElPTiwgT1IgTE9TUyBPRiBVU0UsIERBVEEsIE9SIFBST0ZJVFMpIEhPV0VWRVIgQ0FVU0VEIEFORFxuICogT04gQU5ZIFRIRU9SWSBPRiBMSUFCSUxJVFksIFdIRVRIRVIgSU4gQ09OVFJBQ1QsIFNUUklDVCBMSUFCSUxJVFksIE9SIFRPUlRcbiAqIChJTkNMVURJTkcgTkVHTElHRU5DRSBPUiBPVEhFUldJU0UpIEFSSVNJTkcgSU4gQU5ZIFdBWSBPVVQgT0YgVEhFIFVTRSBPRlxuICogVEhFIFNQSU5FIFJVTlRJTUVTLCBFVkVOIElGIEFEVklTRUQgT0YgVEhFIFBPU1NJQklMSVRZIE9GIFNVQ0ggREFNQUdFLlxuICoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqL1xuXG5pbXBvcnQge1xuXHRjb2xvckJpdCxcblx0Y29sb3JCaXRHbCxcblx0Y29tcGlsZUhpZ2hTaGFkZXJHbFByb2dyYW0sXG5cdGNvbXBpbGVIaWdoU2hhZGVyR3B1UHJvZ3JhbSxcblx0Z2VuZXJhdGVUZXh0dXJlQmF0Y2hCaXQsXG5cdGdlbmVyYXRlVGV4dHVyZUJhdGNoQml0R2wsXG5cdGdldEJhdGNoU2FtcGxlcnNVbmlmb3JtR3JvdXAsXG5cdHJvdW5kUGl4ZWxzQml0LFxuXHRyb3VuZFBpeGVsc0JpdEdsLFxuXHRTaGFkZXJcbn0gZnJvbSAncGl4aS5qcyc7XG5pbXBvcnQgeyBkYXJrVGludEJpdCwgZGFya1RpbnRCaXRHbCB9IGZyb20gJy4vZGFya1RpbnRCaXQuanMnO1xuXG5leHBvcnQgY2xhc3MgRGFya1RpbnRTaGFkZXIgZXh0ZW5kcyBTaGFkZXIge1xuXHRjb25zdHJ1Y3RvciAobWF4VGV4dHVyZXM6IG51bWJlcikge1xuXHRcdGNvbnN0IGdsUHJvZ3JhbSA9IGNvbXBpbGVIaWdoU2hhZGVyR2xQcm9ncmFtKHtcblx0XHRcdG5hbWU6ICdkYXJrLXRpbnQtYmF0Y2gnLFxuXHRcdFx0Yml0czogW1xuXHRcdFx0XHRjb2xvckJpdEdsLFxuXHRcdFx0XHRkYXJrVGludEJpdEdsLFxuXHRcdFx0XHRnZW5lcmF0ZVRleHR1cmVCYXRjaEJpdEdsKG1heFRleHR1cmVzKSxcblx0XHRcdFx0cm91bmRQaXhlbHNCaXRHbCxcblx0XHRcdF1cblx0XHR9KTtcblxuXHRcdGNvbnN0IGdwdVByb2dyYW0gPSBjb21waWxlSGlnaFNoYWRlckdwdVByb2dyYW0oe1xuXHRcdFx0bmFtZTogJ2RhcmstdGludC1iYXRjaCcsXG5cdFx0XHRiaXRzOiBbXG5cdFx0XHRcdGNvbG9yQml0LFxuXHRcdFx0XHRkYXJrVGludEJpdCxcblx0XHRcdFx0Z2VuZXJhdGVUZXh0dXJlQmF0Y2hCaXQobWF4VGV4dHVyZXMpLFxuXHRcdFx0XHRyb3VuZFBpeGVsc0JpdCxcblx0XHRcdF1cblx0XHR9KTtcblxuXHRcdHN1cGVyKHtcblx0XHRcdGdsUHJvZ3JhbSxcblx0XHRcdGdwdVByb2dyYW0sXG5cdFx0XHRyZXNvdXJjZXM6IHtcblx0XHRcdFx0YmF0Y2hTYW1wbGVyczogZ2V0QmF0Y2hTYW1wbGVyc1VuaWZvcm1Hcm91cChtYXhUZXh0dXJlcyksXG5cdFx0XHR9XG5cdFx0fSk7XG5cdH1cbn1cbiJdfQ==