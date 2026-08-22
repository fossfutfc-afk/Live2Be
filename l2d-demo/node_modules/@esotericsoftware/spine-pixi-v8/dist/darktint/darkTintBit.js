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
export const darkTintBit = {
    name: 'color-bit',
    vertex: {
        header: /* wgsl */ `
            @in aDarkColor: vec4<f32>;
            @out vDarkColor: vec4<f32>;
        `,
        main: /* wgsl */ `
        vDarkColor = aDarkColor;
        `
    },
    fragment: {
        header: /* wgsl */ `
            @in vDarkColor: vec4<f32>;
        `,
        end: /* wgsl */ `

        let alpha = outColor.a * vColor.a;
        let rgb = ((outColor.a - 1.0) * vDarkColor.a + 1.0 - outColor.rgb) * vDarkColor.rgb + outColor.rgb * vColor.rgb;

        finalColor = vec4<f32>(rgb, alpha);

        `
    }
};
export const darkTintBitGl = {
    name: 'color-bit',
    vertex: {
        header: /* glsl */ `
            in vec4 aDarkColor;
            out vec4 vDarkColor;
        `,
        main: /* glsl */ `
            vDarkColor = aDarkColor;
        `
    },
    fragment: {
        header: /* glsl */ `
            in vec4 vDarkColor;
        `,
        end: /* glsl */ `

        finalColor.a = outColor.a * vColor.a;
        finalColor.rgb = ((outColor.a - 1.0) * vDarkColor.a + 1.0 - outColor.rgb) * vDarkColor.rgb + outColor.rgb * vColor.rgb;
        `
    }
};
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiZGFya1RpbnRCaXQuanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyIuLi8uLi9zcmMvZGFya3RpbnQvZGFya1RpbnRCaXQudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OzsrRUEyQitFO0FBRS9FLE1BQU0sQ0FBQyxNQUFNLFdBQVcsR0FBRztJQUMxQixJQUFJLEVBQUUsV0FBVztJQUNqQixNQUFNLEVBQUU7UUFDUCxNQUFNLEVBQUUsVUFBVSxDQUFBOzs7U0FHWDtRQUNQLElBQUksRUFBRSxVQUFVLENBQUE7O1NBRVQ7S0FDUDtJQUNELFFBQVEsRUFBRTtRQUNULE1BQU0sRUFBRSxVQUFVLENBQUE7O1NBRVg7UUFDUCxHQUFHLEVBQUUsVUFBVSxDQUFBOzs7Ozs7O1NBT1I7S0FDUDtDQUNELENBQUM7QUFFRixNQUFNLENBQUMsTUFBTSxhQUFhLEdBQUc7SUFDNUIsSUFBSSxFQUFFLFdBQVc7SUFDakIsTUFBTSxFQUFFO1FBQ1AsTUFBTSxFQUFFLFVBQVUsQ0FBQTs7O1NBR1g7UUFDUCxJQUFJLEVBQUUsVUFBVSxDQUFBOztTQUVUO0tBQ1A7SUFDRCxRQUFRLEVBQUU7UUFDVCxNQUFNLEVBQUUsVUFBVSxDQUFBOztTQUVYO1FBQ1AsR0FBRyxFQUFFLFVBQVUsQ0FBQTs7OztTQUlSO0tBQ1A7Q0FDRCxDQUFDIiwic291cmNlc0NvbnRlbnQiOlsiLyoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKlxuICogU3BpbmUgUnVudGltZXMgTGljZW5zZSBBZ3JlZW1lbnRcbiAqIExhc3QgdXBkYXRlZCBBcHJpbCA1LCAyMDI1LiBSZXBsYWNlcyBhbGwgcHJpb3IgdmVyc2lvbnMuXG4gKlxuICogQ29weXJpZ2h0IChjKSAyMDEzLTIwMjUsIEVzb3RlcmljIFNvZnR3YXJlIExMQ1xuICpcbiAqIEludGVncmF0aW9uIG9mIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlIG9yIG90aGVyd2lzZSBjcmVhdGluZ1xuICogZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgaXMgcGVybWl0dGVkIHVuZGVyIHRoZSB0ZXJtcyBhbmRcbiAqIGNvbmRpdGlvbnMgb2YgU2VjdGlvbiAyIG9mIHRoZSBTcGluZSBFZGl0b3IgTGljZW5zZSBBZ3JlZW1lbnQ6XG4gKiBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtZWRpdG9yLWxpY2Vuc2VcbiAqXG4gKiBPdGhlcndpc2UsIGl0IGlzIHBlcm1pdHRlZCB0byBpbnRlZ3JhdGUgdGhlIFNwaW5lIFJ1bnRpbWVzIGludG8gc29mdHdhcmVcbiAqIG9yIG90aGVyd2lzZSBjcmVhdGUgZGVyaXZhdGl2ZSB3b3JrcyBvZiB0aGUgU3BpbmUgUnVudGltZXMgKGNvbGxlY3RpdmVseSxcbiAqIFwiUHJvZHVjdHNcIiksIHByb3ZpZGVkIHRoYXQgZWFjaCB1c2VyIG9mIHRoZSBQcm9kdWN0cyBtdXN0IG9idGFpbiB0aGVpciBvd25cbiAqIFNwaW5lIEVkaXRvciBsaWNlbnNlIGFuZCByZWRpc3RyaWJ1dGlvbiBvZiB0aGUgUHJvZHVjdHMgaW4gYW55IGZvcm0gbXVzdFxuICogaW5jbHVkZSB0aGlzIGxpY2Vuc2UgYW5kIGNvcHlyaWdodCBub3RpY2UuXG4gKlxuICogVEhFIFNQSU5FIFJVTlRJTUVTIEFSRSBQUk9WSURFRCBCWSBFU09URVJJQyBTT0ZUV0FSRSBMTEMgXCJBUyBJU1wiIEFORCBBTllcbiAqIEVYUFJFU1MgT1IgSU1QTElFRCBXQVJSQU5USUVTLCBJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgVEhFIElNUExJRURcbiAqIFdBUlJBTlRJRVMgT0YgTUVSQ0hBTlRBQklMSVRZIEFORCBGSVRORVNTIEZPUiBBIFBBUlRJQ1VMQVIgUFVSUE9TRSBBUkVcbiAqIERJU0NMQUlNRUQuIElOIE5PIEVWRU5UIFNIQUxMIEVTT1RFUklDIFNPRlRXQVJFIExMQyBCRSBMSUFCTEUgRk9SIEFOWVxuICogRElSRUNULCBJTkRJUkVDVCwgSU5DSURFTlRBTCwgU1BFQ0lBTCwgRVhFTVBMQVJZLCBPUiBDT05TRVFVRU5USUFMIERBTUFHRVNcbiAqIChJTkNMVURJTkcsIEJVVCBOT1QgTElNSVRFRCBUTywgUFJPQ1VSRU1FTlQgT0YgU1VCU1RJVFVURSBHT09EUyBPUiBTRVJWSUNFUyxcbiAqIEJVU0lORVNTIElOVEVSUlVQVElPTiwgT1IgTE9TUyBPRiBVU0UsIERBVEEsIE9SIFBST0ZJVFMpIEhPV0VWRVIgQ0FVU0VEIEFORFxuICogT04gQU5ZIFRIRU9SWSBPRiBMSUFCSUxJVFksIFdIRVRIRVIgSU4gQ09OVFJBQ1QsIFNUUklDVCBMSUFCSUxJVFksIE9SIFRPUlRcbiAqIChJTkNMVURJTkcgTkVHTElHRU5DRSBPUiBPVEhFUldJU0UpIEFSSVNJTkcgSU4gQU5ZIFdBWSBPVVQgT0YgVEhFIFVTRSBPRlxuICogVEhFIFNQSU5FIFJVTlRJTUVTLCBFVkVOIElGIEFEVklTRUQgT0YgVEhFIFBPU1NJQklMSVRZIE9GIFNVQ0ggREFNQUdFLlxuICoqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqL1xuXG5leHBvcnQgY29uc3QgZGFya1RpbnRCaXQgPSB7XG5cdG5hbWU6ICdjb2xvci1iaXQnLFxuXHR2ZXJ0ZXg6IHtcblx0XHRoZWFkZXI6IC8qIHdnc2wgKi9gXG4gICAgICAgICAgICBAaW4gYURhcmtDb2xvcjogdmVjNDxmMzI+O1xuICAgICAgICAgICAgQG91dCB2RGFya0NvbG9yOiB2ZWM0PGYzMj47XG4gICAgICAgIGAsXG5cdFx0bWFpbjogLyogd2dzbCAqL2BcbiAgICAgICAgdkRhcmtDb2xvciA9IGFEYXJrQ29sb3I7XG4gICAgICAgIGBcblx0fSxcblx0ZnJhZ21lbnQ6IHtcblx0XHRoZWFkZXI6IC8qIHdnc2wgKi9gXG4gICAgICAgICAgICBAaW4gdkRhcmtDb2xvcjogdmVjNDxmMzI+O1xuICAgICAgICBgLFxuXHRcdGVuZDogLyogd2dzbCAqL2BcblxuICAgICAgICBsZXQgYWxwaGEgPSBvdXRDb2xvci5hICogdkNvbG9yLmE7XG4gICAgICAgIGxldCByZ2IgPSAoKG91dENvbG9yLmEgLSAxLjApICogdkRhcmtDb2xvci5hICsgMS4wIC0gb3V0Q29sb3IucmdiKSAqIHZEYXJrQ29sb3IucmdiICsgb3V0Q29sb3IucmdiICogdkNvbG9yLnJnYjtcblxuICAgICAgICBmaW5hbENvbG9yID0gdmVjNDxmMzI+KHJnYiwgYWxwaGEpO1xuXG4gICAgICAgIGBcblx0fVxufTtcblxuZXhwb3J0IGNvbnN0IGRhcmtUaW50Qml0R2wgPSB7XG5cdG5hbWU6ICdjb2xvci1iaXQnLFxuXHR2ZXJ0ZXg6IHtcblx0XHRoZWFkZXI6IC8qIGdsc2wgKi9gXG4gICAgICAgICAgICBpbiB2ZWM0IGFEYXJrQ29sb3I7XG4gICAgICAgICAgICBvdXQgdmVjNCB2RGFya0NvbG9yO1xuICAgICAgICBgLFxuXHRcdG1haW46IC8qIGdsc2wgKi9gXG4gICAgICAgICAgICB2RGFya0NvbG9yID0gYURhcmtDb2xvcjtcbiAgICAgICAgYFxuXHR9LFxuXHRmcmFnbWVudDoge1xuXHRcdGhlYWRlcjogLyogZ2xzbCAqL2BcbiAgICAgICAgICAgIGluIHZlYzQgdkRhcmtDb2xvcjtcbiAgICAgICAgYCxcblx0XHRlbmQ6IC8qIGdsc2wgKi9gXG5cbiAgICAgICAgZmluYWxDb2xvci5hID0gb3V0Q29sb3IuYSAqIHZDb2xvci5hO1xuICAgICAgICBmaW5hbENvbG9yLnJnYiA9ICgob3V0Q29sb3IuYSAtIDEuMCkgKiB2RGFya0NvbG9yLmEgKyAxLjAgLSBvdXRDb2xvci5yZ2IpICogdkRhcmtDb2xvci5yZ2IgKyBvdXRDb2xvci5yZ2IgKiB2Q29sb3IucmdiO1xuICAgICAgICBgXG5cdH1cbn07XG4iXX0=