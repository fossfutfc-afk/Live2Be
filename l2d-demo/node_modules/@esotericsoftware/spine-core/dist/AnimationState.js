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
import { Animation, MixBlend, AttachmentTimeline, MixDirection, RotateTimeline, DrawOrderTimeline, Timeline, EventTimeline } from "./Animation.js";
import { StringSet, Pool, Utils, MathUtils } from "./Utils.js";
/** Applies animations over time, queues animations for later playback, mixes (crossfading) between animations, and applies
 * multiple animations on top of each other (layering).
 *
 * See [Applying Animations](http://esotericsoftware.com/spine-applying-animations/) in the Spine Runtimes Guide. */
export class AnimationState {
    static _emptyAnimation = new Animation("<empty>", [], 0);
    static emptyAnimation() {
        return AnimationState._emptyAnimation;
    }
    /** The AnimationStateData to look up mix durations. */
    data;
    /** The list of tracks that currently have animations, which may contain null entries. */
    tracks = new Array();
    /** Multiplier for the delta time when the animation state is updated, causing time for all animations and mixes to play slower
     * or faster. Defaults to 1.
     *
     * See TrackEntry {@link TrackEntry#timeScale} for affecting a single animation. */
    timeScale = 1;
    unkeyedState = 0;
    events = new Array();
    listeners = new Array();
    queue = new EventQueue(this);
    propertyIDs = new StringSet();
    animationsChanged = false;
    trackEntryPool = new Pool(() => new TrackEntry());
    constructor(data) {
        this.data = data;
    }
    /** Increments each track entry {@link TrackEntry#trackTime()}, setting queued animations as current if needed. */
    update(delta) {
        delta *= this.timeScale;
        let tracks = this.tracks;
        for (let i = 0, n = tracks.length; i < n; i++) {
            let current = tracks[i];
            if (!current)
                continue;
            current.animationLast = current.nextAnimationLast;
            current.trackLast = current.nextTrackLast;
            let currentDelta = delta * current.timeScale;
            if (current.delay > 0) {
                current.delay -= currentDelta;
                if (current.delay > 0)
                    continue;
                currentDelta = -current.delay;
                current.delay = 0;
            }
            let next = current.next;
            if (next) {
                // When the next entry's delay is passed, change to the next entry, preserving leftover time.
                let nextTime = current.trackLast - next.delay;
                if (nextTime >= 0) {
                    next.delay = 0;
                    next.trackTime += current.timeScale == 0 ? 0 : (nextTime / current.timeScale + delta) * next.timeScale;
                    current.trackTime += currentDelta;
                    this.setCurrent(i, next, true);
                    while (next.mixingFrom) {
                        next.mixTime += delta;
                        next = next.mixingFrom;
                    }
                    continue;
                }
            }
            else if (current.trackLast >= current.trackEnd && !current.mixingFrom) {
                tracks[i] = null;
                this.queue.end(current);
                this.clearNext(current);
                continue;
            }
            if (current.mixingFrom && this.updateMixingFrom(current, delta)) {
                // End mixing from entries once all have completed.
                let from = current.mixingFrom;
                current.mixingFrom = null;
                if (from)
                    from.mixingTo = null;
                while (from) {
                    this.queue.end(from);
                    from = from.mixingFrom;
                }
            }
            current.trackTime += currentDelta;
        }
        this.queue.drain();
    }
    /** Returns true when all mixing from entries are complete. */
    updateMixingFrom(to, delta) {
        let from = to.mixingFrom;
        if (!from)
            return true;
        let finished = this.updateMixingFrom(from, delta);
        from.animationLast = from.nextAnimationLast;
        from.trackLast = from.nextTrackLast;
        // The from entry was applied at least once and the mix is complete.
        if (to.nextTrackLast != -1 && to.mixTime >= to.mixDuration) {
            // Mixing is complete for all entries before the from entry or the mix is instantaneous.
            if (from.totalAlpha == 0 || to.mixDuration == 0) {
                to.mixingFrom = from.mixingFrom;
                if (from.mixingFrom != null)
                    from.mixingFrom.mixingTo = to;
                to.interruptAlpha = from.interruptAlpha;
                this.queue.end(from);
            }
            return finished;
        }
        from.trackTime += delta * from.timeScale;
        to.mixTime += delta;
        return false;
    }
    /** Poses the skeleton using the track entry animations. There are no side effects other than invoking listeners, so the
     * animation state can be applied to multiple skeletons to pose them identically.
     * @returns True if any animations were applied. */
    apply(skeleton) {
        if (!skeleton)
            throw new Error("skeleton cannot be null.");
        if (this.animationsChanged)
            this._animationsChanged();
        let events = this.events;
        let tracks = this.tracks;
        let applied = false;
        for (let i = 0, n = tracks.length; i < n; i++) {
            let current = tracks[i];
            if (!current || current.delay > 0)
                continue;
            applied = true;
            let blend = i == 0 ? MixBlend.first : current.mixBlend;
            // Apply mixing from entries first.
            let alpha = current.alpha;
            if (current.mixingFrom)
                alpha *= this.applyMixingFrom(current, skeleton, blend);
            else if (current.trackTime >= current.trackEnd && !current.next)
                alpha = 0;
            let attachments = alpha >= current.alphaAttachmentThreshold;
            // Apply current entry.
            let animationLast = current.animationLast, animationTime = current.getAnimationTime(), applyTime = animationTime;
            let applyEvents = events;
            if (current.reverse) {
                applyTime = current.animation.duration - applyTime;
                applyEvents = null;
            }
            let timelines = current.animation.timelines;
            let timelineCount = timelines.length;
            if ((i == 0 && alpha == 1) || blend == MixBlend.add) {
                if (i == 0)
                    attachments = true;
                for (let ii = 0; ii < timelineCount; ii++) {
                    // Fixes issue #302 on IOS9 where mix, blend sometimes became undefined and caused assets
                    // to sometimes stop rendering when using color correction, as their RGBA values become NaN.
                    // (https://github.com/pixijs/pixi-spine/issues/302)
                    Utils.webkit602BugfixHelper(alpha, blend);
                    var timeline = timelines[ii];
                    if (timeline instanceof AttachmentTimeline)
                        this.applyAttachmentTimeline(timeline, skeleton, applyTime, blend, attachments);
                    else
                        timeline.apply(skeleton, animationLast, applyTime, applyEvents, alpha, blend, MixDirection.mixIn);
                }
            }
            else {
                let timelineMode = current.timelineMode;
                let shortestRotation = current.shortestRotation;
                let firstFrame = !shortestRotation && current.timelinesRotation.length != timelineCount << 1;
                if (firstFrame)
                    current.timelinesRotation.length = timelineCount << 1;
                for (let ii = 0; ii < timelineCount; ii++) {
                    let timeline = timelines[ii];
                    let timelineBlend = timelineMode[ii] == SUBSEQUENT ? blend : MixBlend.setup;
                    if (!shortestRotation && timeline instanceof RotateTimeline) {
                        this.applyRotateTimeline(timeline, skeleton, applyTime, alpha, timelineBlend, current.timelinesRotation, ii << 1, firstFrame);
                    }
                    else if (timeline instanceof AttachmentTimeline) {
                        this.applyAttachmentTimeline(timeline, skeleton, applyTime, blend, attachments);
                    }
                    else {
                        // This fixes the WebKit 602 specific issue described at http://esotericsoftware.com/forum/iOS-10-disappearing-graphics-10109
                        Utils.webkit602BugfixHelper(alpha, blend);
                        timeline.apply(skeleton, animationLast, applyTime, applyEvents, alpha, timelineBlend, MixDirection.mixIn);
                    }
                }
            }
            this.queueEvents(current, animationTime);
            events.length = 0;
            current.nextAnimationLast = animationTime;
            current.nextTrackLast = current.trackTime;
        }
        // Set slots attachments to the setup pose, if needed. This occurs if an animation that is mixing out sets attachments so
        // subsequent timelines see any deform, but the subsequent timelines don't set an attachment (eg they are also mixing out or
        // the time is before the first key).
        var setupState = this.unkeyedState + SETUP;
        var slots = skeleton.slots;
        for (var i = 0, n = skeleton.slots.length; i < n; i++) {
            var slot = slots[i];
            if (slot.attachmentState == setupState) {
                var attachmentName = slot.data.attachmentName;
                slot.setAttachment(!attachmentName ? null : skeleton.getAttachment(slot.data.index, attachmentName));
            }
        }
        this.unkeyedState += 2; // Increasing after each use avoids the need to reset attachmentState for every slot.
        this.queue.drain();
        return applied;
    }
    applyMixingFrom(to, skeleton, blend) {
        let from = to.mixingFrom;
        if (from.mixingFrom)
            this.applyMixingFrom(from, skeleton, blend);
        let mix = 0;
        if (to.mixDuration == 0) { // Single frame mix to undo mixingFrom changes.
            mix = 1;
            if (blend == MixBlend.first)
                blend = MixBlend.setup;
        }
        else {
            mix = to.mixTime / to.mixDuration;
            if (mix > 1)
                mix = 1;
            if (blend != MixBlend.first)
                blend = from.mixBlend;
        }
        let attachments = mix < from.mixAttachmentThreshold, drawOrder = mix < from.mixDrawOrderThreshold;
        let timelines = from.animation.timelines;
        let timelineCount = timelines.length;
        let alphaHold = from.alpha * to.interruptAlpha, alphaMix = alphaHold * (1 - mix);
        let animationLast = from.animationLast, animationTime = from.getAnimationTime(), applyTime = animationTime;
        let events = null;
        if (from.reverse)
            applyTime = from.animation.duration - applyTime;
        else if (mix < from.eventThreshold)
            events = this.events;
        if (blend == MixBlend.add) {
            for (let i = 0; i < timelineCount; i++)
                timelines[i].apply(skeleton, animationLast, applyTime, events, alphaMix, blend, MixDirection.mixOut);
        }
        else {
            let timelineMode = from.timelineMode;
            let timelineHoldMix = from.timelineHoldMix;
            let shortestRotation = from.shortestRotation;
            let firstFrame = !shortestRotation && from.timelinesRotation.length != timelineCount << 1;
            if (firstFrame)
                from.timelinesRotation.length = timelineCount << 1;
            from.totalAlpha = 0;
            for (let i = 0; i < timelineCount; i++) {
                let timeline = timelines[i];
                let direction = MixDirection.mixOut;
                let timelineBlend;
                let alpha = 0;
                switch (timelineMode[i]) {
                    case SUBSEQUENT:
                        if (!drawOrder && timeline instanceof DrawOrderTimeline)
                            continue;
                        timelineBlend = blend;
                        alpha = alphaMix;
                        break;
                    case FIRST:
                        timelineBlend = MixBlend.setup;
                        alpha = alphaMix;
                        break;
                    case HOLD_SUBSEQUENT:
                        timelineBlend = blend;
                        alpha = alphaHold;
                        break;
                    case HOLD_FIRST:
                        timelineBlend = MixBlend.setup;
                        alpha = alphaHold;
                        break;
                    default:
                        timelineBlend = MixBlend.setup;
                        let holdMix = timelineHoldMix[i];
                        alpha = alphaHold * Math.max(0, 1 - holdMix.mixTime / holdMix.mixDuration);
                        break;
                }
                from.totalAlpha += alpha;
                if (!shortestRotation && timeline instanceof RotateTimeline)
                    this.applyRotateTimeline(timeline, skeleton, applyTime, alpha, timelineBlend, from.timelinesRotation, i << 1, firstFrame);
                else if (timeline instanceof AttachmentTimeline)
                    this.applyAttachmentTimeline(timeline, skeleton, applyTime, timelineBlend, attachments && alpha >= from.alphaAttachmentThreshold);
                else {
                    // This fixes the WebKit 602 specific issue described at http://esotericsoftware.com/forum/iOS-10-disappearing-graphics-10109
                    Utils.webkit602BugfixHelper(alpha, blend);
                    if (drawOrder && timeline instanceof DrawOrderTimeline && timelineBlend == MixBlend.setup)
                        direction = MixDirection.mixIn;
                    timeline.apply(skeleton, animationLast, applyTime, events, alpha, timelineBlend, direction);
                }
            }
        }
        if (to.mixDuration > 0)
            this.queueEvents(from, animationTime);
        this.events.length = 0;
        from.nextAnimationLast = animationTime;
        from.nextTrackLast = from.trackTime;
        return mix;
    }
    applyAttachmentTimeline(timeline, skeleton, time, blend, attachments) {
        var slot = skeleton.slots[timeline.slotIndex];
        if (!slot.bone.active)
            return;
        if (time < timeline.frames[0]) { // Time is before first frame.
            if (blend == MixBlend.setup || blend == MixBlend.first)
                this.setAttachment(skeleton, slot, slot.data.attachmentName, attachments);
        }
        else
            this.setAttachment(skeleton, slot, timeline.attachmentNames[Timeline.search1(timeline.frames, time)], attachments);
        // If an attachment wasn't set (ie before the first frame or attachments is false), set the setup attachment later.
        if (slot.attachmentState <= this.unkeyedState)
            slot.attachmentState = this.unkeyedState + SETUP;
    }
    setAttachment(skeleton, slot, attachmentName, attachments) {
        slot.setAttachment(!attachmentName ? null : skeleton.getAttachment(slot.data.index, attachmentName));
        if (attachments)
            slot.attachmentState = this.unkeyedState + CURRENT;
    }
    applyRotateTimeline(timeline, skeleton, time, alpha, blend, timelinesRotation, i, firstFrame) {
        if (firstFrame)
            timelinesRotation[i] = 0;
        if (alpha == 1) {
            timeline.apply(skeleton, 0, time, null, 1, blend, MixDirection.mixIn);
            return;
        }
        let bone = skeleton.bones[timeline.boneIndex];
        if (!bone.active)
            return;
        let frames = timeline.frames;
        let r1 = 0, r2 = 0;
        if (time < frames[0]) {
            switch (blend) {
                case MixBlend.setup:
                    bone.rotation = bone.data.rotation;
                default:
                    return;
                case MixBlend.first:
                    r1 = bone.rotation;
                    r2 = bone.data.rotation;
            }
        }
        else {
            r1 = blend == MixBlend.setup ? bone.data.rotation : bone.rotation;
            r2 = bone.data.rotation + timeline.getCurveValue(time);
        }
        // Mix between rotations using the direction of the shortest route on the first frame while detecting crosses.
        let total = 0, diff = r2 - r1;
        diff -= Math.ceil(diff / 360 - 0.5) * 360;
        if (diff == 0) {
            total = timelinesRotation[i];
        }
        else {
            let lastTotal = 0, lastDiff = 0;
            if (firstFrame) {
                lastTotal = 0;
                lastDiff = diff;
            }
            else {
                lastTotal = timelinesRotation[i];
                lastDiff = timelinesRotation[i + 1];
            }
            let loops = lastTotal - lastTotal % 360;
            total = diff + loops;
            let current = diff >= 0, dir = lastTotal >= 0;
            if (Math.abs(lastDiff) <= 90 && MathUtils.signum(lastDiff) != MathUtils.signum(diff)) {
                if (Math.abs(lastTotal - loops) > 180) {
                    total += 360 * MathUtils.signum(lastTotal);
                    dir = current;
                }
                else if (loops != 0)
                    total -= 360 * MathUtils.signum(lastTotal);
                else
                    dir = current;
            }
            if (dir != current)
                total += 360 * MathUtils.signum(lastTotal);
            timelinesRotation[i] = total;
        }
        timelinesRotation[i + 1] = diff;
        bone.rotation = r1 + total * alpha;
    }
    queueEvents(entry, animationTime) {
        let animationStart = entry.animationStart, animationEnd = entry.animationEnd;
        let duration = animationEnd - animationStart;
        let trackLastWrapped = entry.trackLast % duration;
        // Queue events before complete.
        let events = this.events;
        let i = 0, n = events.length;
        for (; i < n; i++) {
            let event = events[i];
            if (event.time < trackLastWrapped)
                break;
            if (event.time > animationEnd)
                continue; // Discard events outside animation start/end.
            this.queue.event(entry, event);
        }
        // Queue complete if completed a loop iteration or the animation.
        let complete = false;
        if (entry.loop) {
            if (duration == 0)
                complete = true;
            else {
                const cycles = Math.floor(entry.trackTime / duration);
                complete = cycles > 0 && cycles > Math.floor(entry.trackLast / duration);
            }
        }
        else
            complete = animationTime >= animationEnd && entry.animationLast < animationEnd;
        if (complete)
            this.queue.complete(entry);
        // Queue events after complete.
        for (; i < n; i++) {
            let event = events[i];
            if (event.time < animationStart)
                continue; // Discard events outside animation start/end.
            this.queue.event(entry, event);
        }
    }
    /** Removes all animations from all tracks, leaving skeletons in their current pose.
     *
     * It may be desired to use {@link AnimationState#setEmptyAnimation()} to mix the skeletons back to the setup pose,
     * rather than leaving them in their current pose. */
    clearTracks() {
        let oldDrainDisabled = this.queue.drainDisabled;
        this.queue.drainDisabled = true;
        for (let i = 0, n = this.tracks.length; i < n; i++)
            this.clearTrack(i);
        this.tracks.length = 0;
        this.queue.drainDisabled = oldDrainDisabled;
        this.queue.drain();
    }
    /** Removes all animations from the track, leaving skeletons in their current pose.
     *
     * It may be desired to use {@link AnimationState#setEmptyAnimation()} to mix the skeletons back to the setup pose,
     * rather than leaving them in their current pose. */
    clearTrack(trackIndex) {
        if (trackIndex >= this.tracks.length)
            return;
        let current = this.tracks[trackIndex];
        if (!current)
            return;
        this.queue.end(current);
        this.clearNext(current);
        let entry = current;
        while (true) {
            let from = entry.mixingFrom;
            if (!from)
                break;
            this.queue.end(from);
            entry.mixingFrom = null;
            entry.mixingTo = null;
            entry = from;
        }
        this.tracks[current.trackIndex] = null;
        this.queue.drain();
    }
    setCurrent(index, current, interrupt) {
        let from = this.expandToIndex(index);
        this.tracks[index] = current;
        current.previous = null;
        if (from) {
            if (interrupt)
                this.queue.interrupt(from);
            current.mixingFrom = from;
            from.mixingTo = current;
            current.mixTime = 0;
            // Store the interrupted mix percentage.
            if (from.mixingFrom && from.mixDuration > 0)
                current.interruptAlpha *= Math.min(1, from.mixTime / from.mixDuration);
            from.timelinesRotation.length = 0; // Reset rotation for mixing out, in case entry was mixed in.
        }
        this.queue.start(current);
    }
    /** Sets an animation by name.
      *
      * See {@link #setAnimationWith()}. */
    setAnimation(trackIndex, animationName, loop = false) {
        let animation = this.data.skeletonData.findAnimation(animationName);
        if (!animation)
            throw new Error("Animation not found: " + animationName);
        return this.setAnimationWith(trackIndex, animation, loop);
    }
    /** Sets the current animation for a track, discarding any queued animations. If the formerly current track entry was never
     * applied to a skeleton, it is replaced (not mixed from).
     * @param loop If true, the animation will repeat. If false it will not, instead its last frame is applied if played beyond its
     *           duration. In either case {@link TrackEntry#trackEnd} determines when the track is cleared.
     * @returns A track entry to allow further customization of animation playback. References to the track entry must not be kept
     *         after the {@link AnimationStateListener#dispose()} event occurs. */
    setAnimationWith(trackIndex, animation, loop = false) {
        if (!animation)
            throw new Error("animation cannot be null.");
        let interrupt = true;
        let current = this.expandToIndex(trackIndex);
        if (current) {
            if (current.nextTrackLast == -1) {
                // Don't mix from an entry that was never applied.
                this.tracks[trackIndex] = current.mixingFrom;
                this.queue.interrupt(current);
                this.queue.end(current);
                this.clearNext(current);
                current = current.mixingFrom;
                interrupt = false;
            }
            else
                this.clearNext(current);
        }
        let entry = this.trackEntry(trackIndex, animation, loop, current);
        this.setCurrent(trackIndex, entry, interrupt);
        this.queue.drain();
        return entry;
    }
    /** Queues an animation by name.
     *
     * See {@link #addAnimationWith()}. */
    addAnimation(trackIndex, animationName, loop = false, delay = 0) {
        let animation = this.data.skeletonData.findAnimation(animationName);
        if (!animation)
            throw new Error("Animation not found: " + animationName);
        return this.addAnimationWith(trackIndex, animation, loop, delay);
    }
    /** Adds an animation to be played after the current or last queued animation for a track. If the track is empty, it is
     * equivalent to calling {@link #setAnimationWith()}.
     * @param delay If > 0, sets {@link TrackEntry#delay}. If <= 0, the delay set is the duration of the previous track entry
     *           minus any mix duration (from the {@link AnimationStateData}) plus the specified `delay` (ie the mix
     *           ends at (`delay` = 0) or before (`delay` < 0) the previous track entry duration). If the
     *           previous entry is looping, its next loop completion is used instead of its duration.
     * @returns A track entry to allow further customization of animation playback. References to the track entry must not be kept
     *         after the {@link AnimationStateListener#dispose()} event occurs. */
    addAnimationWith(trackIndex, animation, loop = false, delay = 0) {
        if (!animation)
            throw new Error("animation cannot be null.");
        let last = this.expandToIndex(trackIndex);
        if (last) {
            while (last.next)
                last = last.next;
        }
        let entry = this.trackEntry(trackIndex, animation, loop, last);
        if (!last) {
            this.setCurrent(trackIndex, entry, true);
            this.queue.drain();
            if (delay < 0)
                delay = 0;
        }
        else {
            last.next = entry;
            entry.previous = last;
            if (delay <= 0)
                delay = Math.max(delay + last.getTrackComplete() - entry.mixDuration, 0);
        }
        entry.delay = delay;
        return entry;
    }
    /** Sets an empty animation for a track, discarding any queued animations, and sets the track entry's
     * {@link TrackEntry#mixduration}. An empty animation has no timelines and serves as a placeholder for mixing in or out.
     *
     * Mixing out is done by setting an empty animation with a mix duration using either {@link #setEmptyAnimation()},
     * {@link #setEmptyAnimations()}, or {@link #addEmptyAnimation()}. Mixing to an empty animation causes
     * the previous animation to be applied less and less over the mix duration. Properties keyed in the previous animation
     * transition to the value from lower tracks or to the setup pose value if no lower tracks key the property. A mix duration of
     * 0 still mixes out over one frame.
     *
     * Mixing in is done by first setting an empty animation, then adding an animation using
     * {@link #addAnimation()} and on the returned track entry, set the
     * {@link TrackEntry#setMixDuration()}. Mixing from an empty animation causes the new animation to be applied more and
     * more over the mix duration. Properties keyed in the new animation transition from the value from lower tracks or from the
     * setup pose value if no lower tracks key the property to the value keyed in the new animation. */
    setEmptyAnimation(trackIndex, mixDuration = 0) {
        let entry = this.setAnimationWith(trackIndex, AnimationState.emptyAnimation(), false);
        entry.mixDuration = mixDuration;
        entry.trackEnd = mixDuration;
        return entry;
    }
    /** Adds an empty animation to be played after the current or last queued animation for a track, and sets the track entry's
     * {@link TrackEntry#mixDuration}. If the track is empty, it is equivalent to calling
     * {@link #setEmptyAnimation()}.
     *
     * See {@link #setEmptyAnimation()}.
     * @param delay If > 0, sets {@link TrackEntry#delay}. If <= 0, the delay set is the duration of the previous track entry
     *           minus any mix duration plus the specified `delay` (ie the mix ends at (`delay` = 0) or
     *           before (`delay` < 0) the previous track entry duration). If the previous entry is looping, its next
     *           loop completion is used instead of its duration.
     * @return A track entry to allow further customization of animation playback. References to the track entry must not be kept
     *         after the {@link AnimationStateListener#dispose()} event occurs. */
    addEmptyAnimation(trackIndex, mixDuration = 0, delay = 0) {
        let entry = this.addAnimationWith(trackIndex, AnimationState.emptyAnimation(), false, delay);
        if (delay <= 0)
            entry.delay = Math.max(entry.delay + entry.mixDuration - mixDuration, 0);
        entry.mixDuration = mixDuration;
        entry.trackEnd = mixDuration;
        return entry;
    }
    /** Sets an empty animation for every track, discarding any queued animations, and mixes to it over the specified mix
      * duration. */
    setEmptyAnimations(mixDuration = 0) {
        let oldDrainDisabled = this.queue.drainDisabled;
        this.queue.drainDisabled = true;
        for (let i = 0, n = this.tracks.length; i < n; i++) {
            let current = this.tracks[i];
            if (current)
                this.setEmptyAnimation(current.trackIndex, mixDuration);
        }
        this.queue.drainDisabled = oldDrainDisabled;
        this.queue.drain();
    }
    expandToIndex(index) {
        if (index < this.tracks.length)
            return this.tracks[index];
        Utils.ensureArrayCapacity(this.tracks, index + 1, null);
        this.tracks.length = index + 1;
        return null;
    }
    /** @param last May be null. */
    trackEntry(trackIndex, animation, loop, last) {
        let entry = this.trackEntryPool.obtain();
        entry.reset();
        entry.trackIndex = trackIndex;
        entry.animation = animation;
        entry.loop = loop;
        entry.holdPrevious = false;
        entry.reverse = false;
        entry.shortestRotation = false;
        entry.eventThreshold = 0;
        entry.alphaAttachmentThreshold = 0;
        entry.mixAttachmentThreshold = 0;
        entry.mixDrawOrderThreshold = 0;
        entry.animationStart = 0;
        entry.animationEnd = animation.duration;
        entry.animationLast = -1;
        entry.nextAnimationLast = -1;
        entry.delay = 0;
        entry.trackTime = 0;
        entry.trackLast = -1;
        entry.nextTrackLast = -1;
        entry.trackEnd = Number.MAX_VALUE;
        entry.timeScale = 1;
        entry.alpha = 1;
        entry.mixTime = 0;
        entry.mixDuration = !last ? 0 : this.data.getMix(last.animation, animation);
        entry.interruptAlpha = 1;
        entry.totalAlpha = 0;
        entry.mixBlend = MixBlend.replace;
        return entry;
    }
    /** Removes the {@link TrackEntry#getNext() next entry} and all entries after it for the specified entry. */
    clearNext(entry) {
        let next = entry.next;
        while (next) {
            this.queue.dispose(next);
            next = next.next;
        }
        entry.next = null;
    }
    _animationsChanged() {
        this.animationsChanged = false;
        this.propertyIDs.clear();
        let tracks = this.tracks;
        for (let i = 0, n = tracks.length; i < n; i++) {
            let entry = tracks[i];
            if (!entry)
                continue;
            while (entry.mixingFrom)
                entry = entry.mixingFrom;
            do {
                if (!entry.mixingTo || entry.mixBlend != MixBlend.add)
                    this.computeHold(entry);
                entry = entry.mixingTo;
            } while (entry);
        }
    }
    computeHold(entry) {
        let to = entry.mixingTo;
        let timelines = entry.animation.timelines;
        let timelinesCount = entry.animation.timelines.length;
        let timelineMode = entry.timelineMode;
        timelineMode.length = timelinesCount;
        let timelineHoldMix = entry.timelineHoldMix;
        timelineHoldMix.length = 0;
        let propertyIDs = this.propertyIDs;
        if (to && to.holdPrevious) {
            for (let i = 0; i < timelinesCount; i++)
                timelineMode[i] = propertyIDs.addAll(timelines[i].getPropertyIds()) ? HOLD_FIRST : HOLD_SUBSEQUENT;
            return;
        }
        outer: for (let i = 0; i < timelinesCount; i++) {
            let timeline = timelines[i];
            let ids = timeline.getPropertyIds();
            if (!propertyIDs.addAll(ids))
                timelineMode[i] = SUBSEQUENT;
            else if (!to || timeline instanceof AttachmentTimeline || timeline instanceof DrawOrderTimeline
                || timeline instanceof EventTimeline || !to.animation.hasTimeline(ids)) {
                timelineMode[i] = FIRST;
            }
            else {
                for (let next = to.mixingTo; next; next = next.mixingTo) {
                    if (next.animation.hasTimeline(ids))
                        continue;
                    if (entry.mixDuration > 0) {
                        timelineMode[i] = HOLD_MIX;
                        timelineHoldMix[i] = next;
                        continue outer;
                    }
                    break;
                }
                timelineMode[i] = HOLD_FIRST;
            }
        }
    }
    /** Returns the track entry for the animation currently playing on the track, or null if no animation is currently playing. */
    getCurrent(trackIndex) {
        if (trackIndex >= this.tracks.length)
            return null;
        return this.tracks[trackIndex];
    }
    /** Adds a listener to receive events for all track entries. */
    addListener(listener) {
        if (!listener)
            throw new Error("listener cannot be null.");
        this.listeners.push(listener);
    }
    /** Removes the listener added with {@link #addListener()}. */
    removeListener(listener) {
        let index = this.listeners.indexOf(listener);
        if (index >= 0)
            this.listeners.splice(index, 1);
    }
    /** Removes all listeners added with {@link #addListener()}. */
    clearListeners() {
        this.listeners.length = 0;
    }
    /** Discards all listener notifications that have not yet been delivered. This can be useful to call from an
     * {@link AnimationStateListener} when it is known that further notifications that may have been already queued for delivery
     * are not wanted because new animations are being set. */
    clearListenerNotifications() {
        this.queue.clear();
    }
}
/** Stores settings and other state for the playback of an animation on an {@link AnimationState} track.
 *
 * References to a track entry must not be kept after the {@link AnimationStateListener#dispose()} event occurs. */
export class TrackEntry {
    /** The animation to apply for this track entry. */
    animation = null;
    previous = null;
    /** The animation queued to start after this animation, or null. `next` makes up a linked list. */
    next = null;
    /** The track entry for the previous animation when mixing from the previous animation to this animation, or null if no
     * mixing is currently occuring. When mixing from multiple animations, `mixingFrom` makes up a linked list. */
    mixingFrom = null;
    /** The track entry for the next animation when mixing from this animation to the next animation, or null if no mixing is
     * currently occuring. When mixing to multiple animations, `mixingTo` makes up a linked list. */
    mixingTo = null;
    /** The listener for events generated by this track entry, or null.
     *
     * A track entry returned from {@link AnimationState#setAnimation()} is already the current animation
     * for the track, so the track entry listener {@link AnimationStateListener#start()} will not be called. */
    listener = null;
    /** The index of the track where this track entry is either current or queued.
     *
     * See {@link AnimationState#getCurrent()}. */
    trackIndex = 0;
    /** If true, the animation will repeat. If false it will not, instead its last frame is applied if played beyond its
     * duration. */
    loop = false;
    /** If true, when mixing from the previous animation to this animation, the previous animation is applied as normal instead
     * of being mixed out.
     *
     * When mixing between animations that key the same property, if a lower track also keys that property then the value will
     * briefly dip toward the lower track value during the mix. This happens because the first animation mixes from 100% to 0%
     * while the second animation mixes from 0% to 100%. Setting `holdPrevious` to true applies the first animation
     * at 100% during the mix so the lower track value is overwritten. Such dipping does not occur on the lowest track which
     * keys the property, only when a higher track also keys the property.
     *
     * Snapping will occur if `holdPrevious` is true and this animation does not key all the same properties as the
     * previous animation. */
    holdPrevious = false;
    reverse = false;
    shortestRotation = false;
    /** When the mix percentage ({@link #mixTime} / {@link #mixDuration}) is less than the
     * `eventThreshold`, event timelines are applied while this animation is being mixed out. Defaults to 0, so event
     * timelines are not applied while this animation is being mixed out. */
    eventThreshold = 0;
    /** When the mix percentage ({@link #mixtime} / {@link #mixDuration}) is less than the
     * `attachmentThreshold`, attachment timelines are applied while this animation is being mixed out. Defaults to
     * 0, so attachment timelines are not applied while this animation is being mixed out. */
    mixAttachmentThreshold = 0;
    /** When {@link #getAlpha()} is greater than <code>alphaAttachmentThreshold</code>, attachment timelines are applied.
     * Defaults to 0, so attachment timelines are always applied. */
    alphaAttachmentThreshold = 0;
    /** When the mix percentage ({@link #getMixTime()} / {@link #getMixDuration()}) is less than the
     * <code>mixDrawOrderThreshold</code>, draw order timelines are applied while this animation is being mixed out. Defaults to
     * 0, so draw order timelines are not applied while this animation is being mixed out. */
    mixDrawOrderThreshold = 0;
    /** Seconds when this animation starts, both initially and after looping. Defaults to 0.
     *
     * When changing the `animationStart` time, it often makes sense to set {@link #animationLast} to the same
     * value to prevent timeline keys before the start time from triggering. */
    animationStart = 0;
    /** Seconds for the last frame of this animation. Non-looping animations won't play past this time. Looping animations will
     * loop back to {@link #animationStart} at this time. Defaults to the animation {@link Animation#duration}. */
    animationEnd = 0;
    /** The time in seconds this animation was last applied. Some timelines use this for one-time triggers. Eg, when this
     * animation is applied, event timelines will fire all events between the `animationLast` time (exclusive) and
     * `animationTime` (inclusive). Defaults to -1 to ensure triggers on frame 0 happen the first time this animation
     * is applied. */
    animationLast = 0;
    nextAnimationLast = 0;
    /** Seconds to postpone playing the animation. When this track entry is the current track entry, `delay`
     * postpones incrementing the {@link #trackTime}. When this track entry is queued, `delay` is the time from
     * the start of the previous animation to when this track entry will become the current track entry (ie when the previous
     * track entry {@link TrackEntry#trackTime} >= this track entry's `delay`).
     *
     * {@link #timeScale} affects the delay. */
    delay = 0;
    /** Current time in seconds this track entry has been the current track entry. The track time determines
     * {@link #animationTime}. The track time can be set to start the animation at a time other than 0, without affecting
     * looping. */
    trackTime = 0;
    trackLast = 0;
    nextTrackLast = 0;
    /** The track time in seconds when this animation will be removed from the track. Defaults to the highest possible float
     * value, meaning the animation will be applied until a new animation is set or the track is cleared. If the track end time
     * is reached, no other animations are queued for playback, and mixing from any previous animations is complete, then the
     * properties keyed by the animation are set to the setup pose and the track is cleared.
     *
     * It may be desired to use {@link AnimationState#addEmptyAnimation()} rather than have the animation
     * abruptly cease being applied. */
    trackEnd = 0;
    /** Multiplier for the delta time when this track entry is updated, causing time for this animation to pass slower or
     * faster. Defaults to 1.
     *
     * {@link #mixTime} is not affected by track entry time scale, so {@link #mixDuration} may need to be adjusted to
     * match the animation speed.
     *
     * When using {@link AnimationState#addAnimation()} with a `delay` <= 0, note the
     * {@link #delay} is set using the mix duration from the {@link AnimationStateData}, assuming time scale to be 1. If
     * the time scale is not 1, the delay may need to be adjusted.
     *
     * See AnimationState {@link AnimationState#timeScale} for affecting all animations. */
    timeScale = 0;
    /** Values < 1 mix this animation with the skeleton's current pose (usually the pose resulting from lower tracks). Defaults
     * to 1, which overwrites the skeleton's current pose with this animation.
     *
     * Typically track 0 is used to completely pose the skeleton, then alpha is used on higher tracks. It doesn't make sense to
     * use alpha on track 0 if the skeleton pose is from the last frame render. */
    alpha = 0;
    /** Seconds from 0 to the {@link #getMixDuration()} when mixing from the previous animation to this animation. May be
     * slightly more than `mixDuration` when the mix is complete. */
    mixTime = 0;
    /** Seconds for mixing from the previous animation to this animation. Defaults to the value provided by AnimationStateData
     * {@link AnimationStateData#getMix()} based on the animation before this animation (if any).
     *
     * A mix duration of 0 still mixes out over one frame to provide the track entry being mixed out a chance to revert the
     * properties it was animating.
     *
     * The `mixDuration` can be set manually rather than use the value from
     * {@link AnimationStateData#getMix()}. In that case, the `mixDuration` can be set for a new
     * track entry only before {@link AnimationState#update(float)} is first called.
     *
     * When using {@link AnimationState#addAnimation()} with a `delay` <= 0, note the
     * {@link #delay} is set using the mix duration from the {@link AnimationStateData}, not a mix duration set
     * afterward. */
    _mixDuration = 0;
    interruptAlpha = 0;
    totalAlpha = 0;
    get mixDuration() {
        return this._mixDuration;
    }
    set mixDuration(mixDuration) {
        this._mixDuration = mixDuration;
    }
    setMixDurationWithDelay(mixDuration, delay) {
        this._mixDuration = mixDuration;
        if (delay <= 0) {
            if (this.previous != null)
                delay = Math.max(delay + this.previous.getTrackComplete() - mixDuration, 0);
            else
                delay = 0;
        }
        this.delay = delay;
    }
    /** Controls how properties keyed in the animation are mixed with lower tracks. Defaults to {@link MixBlend#replace}, which
     * replaces the values from the lower tracks with the animation values. {@link MixBlend#add} adds the animation values to
     * the values from the lower tracks.
     *
     * The `mixBlend` can be set for a new track entry only before {@link AnimationState#apply()} is first
     * called. */
    mixBlend = MixBlend.replace;
    timelineMode = new Array();
    timelineHoldMix = new Array();
    timelinesRotation = new Array();
    reset() {
        this.next = null;
        this.previous = null;
        this.mixingFrom = null;
        this.mixingTo = null;
        this.animation = null;
        this.listener = null;
        this.timelineMode.length = 0;
        this.timelineHoldMix.length = 0;
        this.timelinesRotation.length = 0;
    }
    /** Uses {@link #trackTime} to compute the `animationTime`, which is between {@link #animationStart}
     * and {@link #animationEnd}. When the `trackTime` is 0, the `animationTime` is equal to the
     * `animationStart` time. */
    getAnimationTime() {
        if (this.loop) {
            let duration = this.animationEnd - this.animationStart;
            if (duration == 0)
                return this.animationStart;
            return (this.trackTime % duration) + this.animationStart;
        }
        return Math.min(this.trackTime + this.animationStart, this.animationEnd);
    }
    setAnimationLast(animationLast) {
        this.animationLast = animationLast;
        this.nextAnimationLast = animationLast;
    }
    /** Returns true if at least one loop has been completed.
     *
     * See {@link AnimationStateListener#complete()}. */
    isComplete() {
        return this.trackTime >= this.animationEnd - this.animationStart;
    }
    /** Resets the rotation directions for mixing this entry's rotate timelines. This can be useful to avoid bones rotating the
     * long way around when using {@link #alpha} and starting animations on other tracks.
     *
     * Mixing with {@link MixBlend#replace} involves finding a rotation between two others, which has two possible solutions:
     * the short way or the long way around. The two rotations likely change over time, so which direction is the short or long
     * way also changes. If the short way was always chosen, bones would flip to the other side when that direction became the
     * long way. TrackEntry chooses the short way the first time it is applied and remembers that direction. */
    resetRotationDirections() {
        this.timelinesRotation.length = 0;
    }
    getTrackComplete() {
        let duration = this.animationEnd - this.animationStart;
        if (duration != 0) {
            if (this.loop)
                return duration * (1 + ((this.trackTime / duration) | 0)); // Completion of next loop.
            if (this.trackTime < duration)
                return duration; // Before duration.
        }
        return this.trackTime; // Next update.
    }
    /** Returns true if this track entry has been applied at least once.
     * <p>
     * See {@link AnimationState#apply(Skeleton)}. */
    wasApplied() {
        return this.nextTrackLast != -1;
    }
    /** Returns true if there is a {@link #getNext()} track entry and it will become the current track entry during the next
     * {@link AnimationState#update(float)}. */
    isNextReady() {
        return this.next != null && this.nextTrackLast - this.next.delay >= 0;
    }
}
export class EventQueue {
    objects = [];
    drainDisabled = false;
    animState;
    constructor(animState) {
        this.animState = animState;
    }
    start(entry) {
        this.objects.push(EventType.start);
        this.objects.push(entry);
        this.animState.animationsChanged = true;
    }
    interrupt(entry) {
        this.objects.push(EventType.interrupt);
        this.objects.push(entry);
    }
    end(entry) {
        this.objects.push(EventType.end);
        this.objects.push(entry);
        this.animState.animationsChanged = true;
    }
    dispose(entry) {
        this.objects.push(EventType.dispose);
        this.objects.push(entry);
    }
    complete(entry) {
        this.objects.push(EventType.complete);
        this.objects.push(entry);
    }
    event(entry, event) {
        this.objects.push(EventType.event);
        this.objects.push(entry);
        this.objects.push(event);
    }
    drain() {
        if (this.drainDisabled)
            return;
        this.drainDisabled = true;
        let objects = this.objects;
        for (let i = 0; i < objects.length; i += 2) {
            let type = objects[i];
            let entry = objects[i + 1];
            let listeners = this.animState.listeners.slice();
            switch (type) {
                case EventType.start:
                    if (entry.listener && entry.listener.start)
                        entry.listener.start(entry);
                    for (let ii = 0; ii < listeners.length; ii++) {
                        let listener = listeners[ii];
                        if (listener.start)
                            listener.start(entry);
                    }
                    break;
                case EventType.interrupt:
                    if (entry.listener && entry.listener.interrupt)
                        entry.listener.interrupt(entry);
                    for (let ii = 0; ii < listeners.length; ii++) {
                        let listener = listeners[ii];
                        if (listener.interrupt)
                            listener.interrupt(entry);
                    }
                    break;
                case EventType.end:
                    if (entry.listener && entry.listener.end)
                        entry.listener.end(entry);
                    for (let ii = 0; ii < listeners.length; ii++) {
                        let listener = listeners[ii];
                        if (listener.end)
                            listener.end(entry);
                    }
                // Fall through.
                case EventType.dispose:
                    if (entry.listener && entry.listener.dispose)
                        entry.listener.dispose(entry);
                    for (let ii = 0; ii < listeners.length; ii++) {
                        let listener = listeners[ii];
                        if (listener.dispose)
                            listener.dispose(entry);
                    }
                    this.animState.trackEntryPool.free(entry);
                    break;
                case EventType.complete:
                    if (entry.listener && entry.listener.complete)
                        entry.listener.complete(entry);
                    for (let ii = 0; ii < listeners.length; ii++) {
                        let listener = listeners[ii];
                        if (listener.complete)
                            listener.complete(entry);
                    }
                    break;
                case EventType.event:
                    let event = objects[i++ + 2];
                    if (entry.listener && entry.listener.event)
                        entry.listener.event(entry, event);
                    for (let ii = 0; ii < listeners.length; ii++) {
                        let listener = listeners[ii];
                        if (listener.event)
                            listener.event(entry, event);
                    }
                    break;
            }
        }
        this.clear();
        this.drainDisabled = false;
    }
    clear() {
        this.objects.length = 0;
    }
}
export var EventType;
(function (EventType) {
    EventType[EventType["start"] = 0] = "start";
    EventType[EventType["interrupt"] = 1] = "interrupt";
    EventType[EventType["end"] = 2] = "end";
    EventType[EventType["dispose"] = 3] = "dispose";
    EventType[EventType["complete"] = 4] = "complete";
    EventType[EventType["event"] = 5] = "event";
})(EventType || (EventType = {}));
export class AnimationStateAdapter {
    start(entry) {
    }
    interrupt(entry) {
    }
    end(entry) {
    }
    dispose(entry) {
    }
    complete(entry) {
    }
    event(entry, event) {
    }
}
/** 1. A previously applied timeline has set this property.
 *
 * Result: Mix from the current pose to the timeline pose. */
export const SUBSEQUENT = 0;
/** 1. This is the first timeline to set this property.
 * 2. The next track entry applied after this one does not have a timeline to set this property.
 *
 * Result: Mix from the setup pose to the timeline pose. */
export const FIRST = 1;
/** 1) A previously applied timeline has set this property.<br>
 * 2) The next track entry to be applied does have a timeline to set this property.<br>
 * 3) The next track entry after that one does not have a timeline to set this property.<br>
 * Result: Mix from the current pose to the timeline pose, but do not mix out. This avoids "dipping" when crossfading
 * animations that key the same property. A subsequent timeline will set this property using a mix. */
export const HOLD_SUBSEQUENT = 2;
/** 1) This is the first timeline to set this property.<br>
 * 2) The next track entry to be applied does have a timeline to set this property.<br>
 * 3) The next track entry after that one does not have a timeline to set this property.<br>
 * Result: Mix from the setup pose to the timeline pose, but do not mix out. This avoids "dipping" when crossfading animations
 * that key the same property. A subsequent timeline will set this property using a mix. */
export const HOLD_FIRST = 3;
/** 1. This is the first timeline to set this property.
 * 2. The next track entry to be applied does have a timeline to set this property.
 * 3. The next track entry after that one does have a timeline to set this property.
 * 4. timelineHoldMix stores the first subsequent track entry that does not have a timeline to set this property.
 *
 * Result: The same as HOLD except the mix percentage from the timelineHoldMix track entry is used. This handles when more than
 * 2 track entries in a row have a timeline that sets the same property.
 *
 * Eg, A -> B -> C -> D where A, B, and C have a timeline setting same property, but D does not. When A is applied, to avoid
 * "dipping" A is not mixed out, however D (the first entry that doesn't set the property) mixing in is used to mix out A
 * (which affects B and C). Without using D to mix out, A would be applied fully until mixing completes, then snap into
 * place. */
export const HOLD_MIX = 4;
export const SETUP = 1;
export const CURRENT = 2;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiQW5pbWF0aW9uU3RhdGUuanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyIuLi9zcmMvQW5pbWF0aW9uU3RhdGUudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7OzsrRUEyQitFO0FBRS9FLE9BQU8sRUFBRSxTQUFTLEVBQUUsUUFBUSxFQUFFLGtCQUFrQixFQUFFLFlBQVksRUFBRSxjQUFjLEVBQUUsaUJBQWlCLEVBQUUsUUFBUSxFQUFFLGFBQWEsRUFBRSxNQUFNLGdCQUFnQixDQUFDO0FBSW5KLE9BQU8sRUFBRSxTQUFTLEVBQUUsSUFBSSxFQUFFLEtBQUssRUFBRSxTQUFTLEVBQUUsTUFBTSxZQUFZLENBQUM7QUFJL0Q7OztvSEFHb0g7QUFDcEgsTUFBTSxPQUFPLGNBQWM7SUFDMUIsTUFBTSxDQUFDLGVBQWUsR0FBRyxJQUFJLFNBQVMsQ0FBQyxTQUFTLEVBQUUsRUFBRSxFQUFFLENBQUMsQ0FBQyxDQUFDO0lBQ2pELE1BQU0sQ0FBQyxjQUFjO1FBQzVCLE9BQU8sY0FBYyxDQUFDLGVBQWUsQ0FBQztJQUN2QyxDQUFDO0lBRUQsdURBQXVEO0lBQ3ZELElBQUksQ0FBcUI7SUFFekIseUZBQXlGO0lBQ3pGLE1BQU0sR0FBRyxJQUFJLEtBQUssRUFBcUIsQ0FBQztJQUV4Qzs7O3VGQUdtRjtJQUNuRixTQUFTLEdBQUcsQ0FBQyxDQUFDO0lBQ2QsWUFBWSxHQUFHLENBQUMsQ0FBQztJQUVqQixNQUFNLEdBQUcsSUFBSSxLQUFLLEVBQVMsQ0FBQztJQUM1QixTQUFTLEdBQUcsSUFBSSxLQUFLLEVBQTBCLENBQUM7SUFDaEQsS0FBSyxHQUFHLElBQUksVUFBVSxDQUFDLElBQUksQ0FBQyxDQUFDO0lBQzdCLFdBQVcsR0FBRyxJQUFJLFNBQVMsRUFBRSxDQUFDO0lBQzlCLGlCQUFpQixHQUFHLEtBQUssQ0FBQztJQUUxQixjQUFjLEdBQUcsSUFBSSxJQUFJLENBQWEsR0FBRyxFQUFFLENBQUMsSUFBSSxV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SUFBRSxtREFBUyxDQUFBO0lBQUUsdUNBQUcsQ0FBQTtJQUFFLCtDQUFPLENBQUE7SUFBRSxpREFBUSxDQUFBO0lBQUUsMkNBQUssQ0FBQTtBQUNoRCxDQUFDLEVBRlcsU0FBUyxLQUFULFNBQVMsUUFFcEI7QUE2QkQsTUFBTSxPQUFnQixxQkFBcUI7SUFDMUMsS0FBSyxDQUFFLEtBQWlCO0lBQ3hCLENBQUM7SUFFRCxTQUFTLENBQUUsS0FBaUI7SUFDNUIsQ0FBQztJQUVELEdBQUcsQ0FBRSxLQUFpQjtJQUN0QixDQUFDO0lBRUQsT0FBTyxDQUFFLEtBQWlCO0lBQzFCLENBQUM7SUFFRCxRQUFRLENBQUUsS0FBaUI7SUFDM0IsQ0FBQztJQUVELEtBQUssQ0FBRSxLQUFpQixFQUFFLEtBQVk7SUFDdEMsQ0FBQztDQUNEO0FBRUQ7OzZEQUU2RDtBQUM3RCxNQUFNLENBQUMsTUFBTSxVQUFVLEdBQUcsQ0FBQyxDQUFDO0FBQzVCOzs7MkRBRzJEO0FBQzNELE1BQU0sQ0FBQyxNQUFNLEtBQUssR0FBRyxDQUFDLENBQUM7QUFDdkI7Ozs7c0dBSXNHO0FBQ3RHLE1BQU0sQ0FBQyxNQUFNLGVBQWUsR0FBRyxDQUFDLENBQUM7QUFDakM7Ozs7MkZBSTJGO0FBQzNGLE1BQU0sQ0FBQyxNQUFNLFVBQVUsR0FBRyxDQUFDLENBQUM7QUFDNUI7Ozs7Ozs7Ozs7O1lBV1k7QUFDWixNQUFNLENBQUMsTUFBTSxRQUFRLEdBQUcsQ0FBQyxDQUFDO0FBRTFCLE1BQU0sQ0FBQyxNQUFNLEtBQUssR0FBRyxDQUFDLENBQUM7QUFDdkIsTUFBTSxDQUFDLE1BQU0sT0FBTyxHQUFHLENBQUMsQ0FBQyIsInNvdXJjZXNDb250ZW50IjpbIi8qKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKipcbiAqIFNwaW5lIFJ1bnRpbWVzIExpY2Vuc2UgQWdyZWVtZW50XG4gKiBMYXN0IHVwZGF0ZWQgQXByaWwgNSwgMjAyNS4gUmVwbGFjZXMgYWxsIHByaW9yIHZlcnNpb25zLlxuICpcbiAqIENvcHlyaWdodCAoYykgMjAxMy0yMDI1LCBFc290ZXJpYyBTb2Z0d2FyZSBMTENcbiAqXG4gKiBJbnRlZ3JhdGlvbiBvZiB0aGUgU3BpbmUgUnVudGltZXMgaW50byBzb2Z0d2FyZSBvciBvdGhlcndpc2UgY3JlYXRpbmdcbiAqIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIGlzIHBlcm1pdHRlZCB1bmRlciB0aGUgdGVybXMgYW5kXG4gKiBjb25kaXRpb25zIG9mIFNlY3Rpb24gMiBvZiB0aGUgU3BpbmUgRWRpdG9yIExpY2Vuc2UgQWdyZWVtZW50OlxuICogaHR0cDovL2Vzb3Rlcmljc29mdHdhcmUuY29tL3NwaW5lLWVkaXRvci1saWNlbnNlXG4gKlxuICogT3RoZXJ3aXNlLCBpdCBpcyBwZXJtaXR0ZWQgdG8gaW50ZWdyYXRlIHRoZSBTcGluZSBSdW50aW1lcyBpbnRvIHNvZnR3YXJlXG4gKiBvciBvdGhlcndpc2UgY3JlYXRlIGRlcml2YXRpdmUgd29ya3Mgb2YgdGhlIFNwaW5lIFJ1bnRpbWVzIChjb2xsZWN0aXZlbHksXG4gKiBcIlByb2R1Y3RzXCIpLCBwcm92aWRlZCB0aGF0IGVhY2ggdXNlciBvZiB0aGUgUHJvZHVjdHMgbXVzdCBvYnRhaW4gdGhlaXIgb3duXG4gKiBTcGluZSBFZGl0b3IgbGljZW5zZSBhbmQgcmVkaXN0cmlidXRpb24gb2YgdGhlIFByb2R1Y3RzIGluIGFueSBmb3JtIG11c3RcbiAqIGluY2x1ZGUgdGhpcyBsaWNlbnNlIGFuZCBjb3B5cmlnaHQgbm90aWNlLlxuICpcbiAqIFRIRSBTUElORSBSVU5USU1FUyBBUkUgUFJPVklERUQgQlkgRVNPVEVSSUMgU09GVFdBUkUgTExDIFwiQVMgSVNcIiBBTkQgQU5ZXG4gKiBFWFBSRVNTIE9SIElNUExJRUQgV0FSUkFOVElFUywgSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFRIRSBJTVBMSUVEXG4gKiBXQVJSQU5USUVTIE9GIE1FUkNIQU5UQUJJTElUWSBBTkQgRklUTkVTUyBGT1IgQSBQQVJUSUNVTEFSIFBVUlBPU0UgQVJFXG4gKiBESVNDTEFJTUVELiBJTiBOTyBFVkVOVCBTSEFMTCBFU09URVJJQyBTT0ZUV0FSRSBMTEMgQkUgTElBQkxFIEZPUiBBTllcbiAqIERJUkVDVCwgSU5ESVJFQ1QsIElOQ0lERU5UQUwsIFNQRUNJQUwsIEVYRU1QTEFSWSwgT1IgQ09OU0VRVUVOVElBTCBEQU1BR0VTXG4gKiAoSU5DTFVESU5HLCBCVVQgTk9UIExJTUlURUQgVE8sIFBST0NVUkVNRU5UIE9GIFNVQlNUSVRVVEUgR09PRFMgT1IgU0VSVklDRVMsXG4gKiBCVVNJTkVTUyBJTlRFUlJVUFRJT04sIE9SIExPU1MgT0YgVVNFLCBEQVRBLCBPUiBQUk9GSVRTKSBIT1dFVkVSIENBVVNFRCBBTkRcbiAqIE9OIEFOWSBUSEVPUlkgT0YgTElBQklMSVRZLCBXSEVUSEVSIElOIENPTlRSQUNULCBTVFJJQ1QgTElBQklMSVRZLCBPUiBUT1JUXG4gKiAoSU5DTFVESU5HIE5FR0xJR0VOQ0UgT1IgT1RIRVJXSVNFKSBBUklTSU5HIElOIEFOWSBXQVkgT1VUIE9GIFRIRSBVU0UgT0ZcbiAqIFRIRSBTUElORSBSVU5USU1FUywgRVZFTiBJRiBBRFZJU0VEIE9GIFRIRSBQT1NTSUJJTElUWSBPRiBTVUNIIERBTUFHRS5cbiAqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKi9cblxuaW1wb3J0IHsgQW5pbWF0aW9uLCBNaXhCbGVuZCwgQXR0YWNobWVudFRpbWVsaW5lLCBNaXhEaXJlY3Rpb24sIFJvdGF0ZVRpbWVsaW5lLCBEcmF3T3JkZXJUaW1lbGluZSwgVGltZWxpbmUsIEV2ZW50VGltZWxpbmUgfSBmcm9tIFwiLi9BbmltYXRpb24uanNcIjtcbmltcG9ydCB7IEFuaW1hdGlvblN0YXRlRGF0YSB9IGZyb20gXCIuL0FuaW1hdGlvblN0YXRlRGF0YS5qc1wiO1xuaW1wb3J0IHsgU2tlbGV0b24gfSBmcm9tIFwiLi9Ta2VsZXRvbi5qc1wiO1xuaW1wb3J0IHsgU2xvdCB9IGZyb20gXCIuL1Nsb3QuanNcIjtcbmltcG9ydCB7IFN0cmluZ1NldCwgUG9vbCwgVXRpbHMsIE1hdGhVdGlscyB9IGZyb20gXCIuL1V0aWxzLmpzXCI7XG5pbXBvcnQgeyBFdmVudCB9IGZyb20gXCIuL0V2ZW50LmpzXCI7XG5cblxuLyoqIEFwcGxpZXMgYW5pbWF0aW9ucyBvdmVyIHRpbWUsIHF1ZXVlcyBhbmltYXRpb25zIGZvciBsYXRlciBwbGF5YmFjaywgbWl4ZXMgKGNyb3NzZmFkaW5nKSBiZXR3ZWVuIGFuaW1hdGlvbnMsIGFuZCBhcHBsaWVzXG4gKiBtdWx0aXBsZSBhbmltYXRpb25zIG9uIHRvcCBvZiBlYWNoIG90aGVyIChsYXllcmluZykuXG4gKlxuICogU2VlIFtBcHBseWluZyBBbmltYXRpb25zXShodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vc3BpbmUtYXBwbHlpbmctYW5pbWF0aW9ucy8pIGluIHRoZSBTcGluZSBSdW50aW1lcyBHdWlkZS4gKi9cbmV4cG9ydCBjbGFzcyBBbmltYXRpb25TdGF0ZSB7XG5cdHN0YXRpYyBfZW1wdHlBbmltYXRpb24gPSBuZXcgQW5pbWF0aW9uKFwiPGVtcHR5PlwiLCBbXSwgMCk7XG5cdHByaXZhdGUgc3RhdGljIGVtcHR5QW5pbWF0aW9uICgpOiBBbmltYXRpb24ge1xuXHRcdHJldHVybiBBbmltYXRpb25TdGF0ZS5fZW1wdHlBbmltYXRpb247XG5cdH1cblxuXHQvKiogVGhlIEFuaW1hdGlvblN0YXRlRGF0YSB0byBsb29rIHVwIG1peCBkdXJhdGlvbnMuICovXG5cdGRhdGE6IEFuaW1hdGlvblN0YXRlRGF0YTtcblxuXHQvKiogVGhlIGxpc3Qgb2YgdHJhY2tzIHRoYXQgY3VycmVudGx5IGhhdmUgYW5pbWF0aW9ucywgd2hpY2ggbWF5IGNvbnRhaW4gbnVsbCBlbnRyaWVzLiAqL1xuXHR0cmFja3MgPSBuZXcgQXJyYXk8VHJhY2tFbnRyeSB8IG51bGw+KCk7XG5cblx0LyoqIE11bHRpcGxpZXIgZm9yIHRoZSBkZWx0YSB0aW1lIHdoZW4gdGhlIGFuaW1hdGlvbiBzdGF0ZSBpcyB1cGRhdGVkLCBjYXVzaW5nIHRpbWUgZm9yIGFsbCBhbmltYXRpb25zIGFuZCBtaXhlcyB0byBwbGF5IHNsb3dlclxuXHQgKiBvciBmYXN0ZXIuIERlZmF1bHRzIHRvIDEuXG5cdCAqXG5cdCAqIFNlZSBUcmFja0VudHJ5IHtAbGluayBUcmFja0VudHJ5I3RpbWVTY2FsZX0gZm9yIGFmZmVjdGluZyBhIHNpbmdsZSBhbmltYXRpb24uICovXG5cdHRpbWVTY2FsZSA9IDE7XG5cdHVua2V5ZWRTdGF0ZSA9IDA7XG5cblx0ZXZlbnRzID0gbmV3IEFycmF5PEV2ZW50PigpO1xuXHRsaXN0ZW5lcnMgPSBuZXcgQXJyYXk8QW5pbWF0aW9uU3RhdGVMaXN0ZW5lcj4oKTtcblx0cXVldWUgPSBuZXcgRXZlbnRRdWV1ZSh0aGlzKTtcblx0cHJvcGVydHlJRHMgPSBuZXcgU3RyaW5nU2V0KCk7XG5cdGFuaW1hdGlvbnNDaGFuZ2VkID0gZmFsc2U7XG5cblx0dHJhY2tFbnRyeVBvb2wgPSBuZXcgUG9vbDxUcmFja0VudHJ5PigoKSA9PiBuZXcgVHJhY2tFbnRyeSgpKTtcblxuXHRjb25zdHJ1Y3RvciAoZGF0YTogQW5pbWF0aW9uU3RhdGVEYXRhKSB7XG5cdFx0dGhpcy5kYXRhID0gZGF0YTtcblx0fVxuXG5cdC8qKiBJbmNyZW1lbnRzIGVhY2ggdHJhY2sgZW50cnkge0BsaW5rIFRyYWNrRW50cnkjdHJhY2tUaW1lKCl9LCBzZXR0aW5nIHF1ZXVlZCBhbmltYXRpb25zIGFzIGN1cnJlbnQgaWYgbmVlZGVkLiAqL1xuXHR1cGRhdGUgKGRlbHRhOiBudW1iZXIpIHtcblx0XHRkZWx0YSAqPSB0aGlzLnRpbWVTY2FsZTtcblx0XHRsZXQgdHJhY2tzID0gdGhpcy50cmFja3M7XG5cdFx0Zm9yIChsZXQgaSA9IDAsIG4gPSB0cmFja3MubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHRsZXQgY3VycmVudCA9IHRyYWNrc1tpXTtcblx0XHRcdGlmICghY3VycmVudCkgY29udGludWU7XG5cblx0XHRcdGN1cnJlbnQuYW5pbWF0aW9uTGFzdCA9IGN1cnJlbnQubmV4dEFuaW1hdGlvbkxhc3Q7XG5cdFx0XHRjdXJyZW50LnRyYWNrTGFzdCA9IGN1cnJlbnQubmV4dFRyYWNrTGFzdDtcblxuXHRcdFx0bGV0IGN1cnJlbnREZWx0YSA9IGRlbHRhICogY3VycmVudC50aW1lU2NhbGU7XG5cblx0XHRcdGlmIChjdXJyZW50LmRlbGF5ID4gMCkge1xuXHRcdFx0XHRjdXJyZW50LmRlbGF5IC09IGN1cnJlbnREZWx0YTtcblx0XHRcdFx0aWYgKGN1cnJlbnQuZGVsYXkgPiAwKSBjb250aW51ZTtcblx0XHRcdFx0Y3VycmVudERlbHRhID0gLWN1cnJlbnQuZGVsYXk7XG5cdFx0XHRcdGN1cnJlbnQuZGVsYXkgPSAwO1xuXHRcdFx0fVxuXG5cdFx0XHRsZXQgbmV4dCA9IGN1cnJlbnQubmV4dDtcblx0XHRcdGlmIChuZXh0KSB7XG5cdFx0XHRcdC8vIFdoZW4gdGhlIG5leHQgZW50cnkncyBkZWxheSBpcyBwYXNzZWQsIGNoYW5nZSB0byB0aGUgbmV4dCBlbnRyeSwgcHJlc2VydmluZyBsZWZ0b3ZlciB0aW1lLlxuXHRcdFx0XHRsZXQgbmV4dFRpbWUgPSBjdXJyZW50LnRyYWNrTGFzdCAtIG5leHQuZGVsYXk7XG5cdFx0XHRcdGlmIChuZXh0VGltZSA+PSAwKSB7XG5cdFx0XHRcdFx0bmV4dC5kZWxheSA9IDA7XG5cdFx0XHRcdFx0bmV4dC50cmFja1RpbWUgKz0gY3VycmVudC50aW1lU2NhbGUgPT0gMCA/IDAgOiAobmV4dFRpbWUgLyBjdXJyZW50LnRpbWVTY2FsZSArIGRlbHRhKSAqIG5leHQudGltZVNjYWxlO1xuXHRcdFx0XHRcdGN1cnJlbnQudHJhY2tUaW1lICs9IGN1cnJlbnREZWx0YTtcblx0XHRcdFx0XHR0aGlzLnNldEN1cnJlbnQoaSwgbmV4dCwgdHJ1ZSk7XG5cdFx0XHRcdFx0d2hpbGUgKG5leHQubWl4aW5nRnJvbSkge1xuXHRcdFx0XHRcdFx0bmV4dC5taXhUaW1lICs9IGRlbHRhO1xuXHRcdFx0XHRcdFx0bmV4dCA9IG5leHQubWl4aW5nRnJvbTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0Y29udGludWU7XG5cdFx0XHRcdH1cblx0XHRcdH0gZWxzZSBpZiAoY3VycmVudC50cmFja0xhc3QgPj0gY3VycmVudC50cmFja0VuZCAmJiAhY3VycmVudC5taXhpbmdGcm9tKSB7XG5cdFx0XHRcdHRyYWNrc1tpXSA9IG51bGw7XG5cdFx0XHRcdHRoaXMucXVldWUuZW5kKGN1cnJlbnQpO1xuXHRcdFx0XHR0aGlzLmNsZWFyTmV4dChjdXJyZW50KTtcblx0XHRcdFx0Y29udGludWU7XG5cdFx0XHR9XG5cdFx0XHRpZiAoY3VycmVudC5taXhpbmdGcm9tICYmIHRoaXMudXBkYXRlTWl4aW5nRnJvbShjdXJyZW50LCBkZWx0YSkpIHtcblx0XHRcdFx0Ly8gRW5kIG1peGluZyBmcm9tIGVudHJpZXMgb25jZSBhbGwgaGF2ZSBjb21wbGV0ZWQuXG5cdFx0XHRcdGxldCBmcm9tOiBUcmFja0VudHJ5IHwgbnVsbCA9IGN1cnJlbnQubWl4aW5nRnJvbTtcblx0XHRcdFx0Y3VycmVudC5taXhpbmdGcm9tID0gbnVsbDtcblx0XHRcdFx0aWYgKGZyb20pIGZyb20ubWl4aW5nVG8gPSBudWxsO1xuXHRcdFx0XHR3aGlsZSAoZnJvbSkge1xuXHRcdFx0XHRcdHRoaXMucXVldWUuZW5kKGZyb20pO1xuXHRcdFx0XHRcdGZyb20gPSBmcm9tLm1peGluZ0Zyb207XG5cdFx0XHRcdH1cblx0XHRcdH1cblxuXHRcdFx0Y3VycmVudC50cmFja1RpbWUgKz0gY3VycmVudERlbHRhO1xuXHRcdH1cblxuXHRcdHRoaXMucXVldWUuZHJhaW4oKTtcblx0fVxuXG5cdC8qKiBSZXR1cm5zIHRydWUgd2hlbiBhbGwgbWl4aW5nIGZyb20gZW50cmllcyBhcmUgY29tcGxldGUuICovXG5cdHVwZGF0ZU1peGluZ0Zyb20gKHRvOiBUcmFja0VudHJ5LCBkZWx0YTogbnVtYmVyKTogYm9vbGVhbiB7XG5cdFx0bGV0IGZyb20gPSB0by5taXhpbmdGcm9tO1xuXHRcdGlmICghZnJvbSkgcmV0dXJuIHRydWU7XG5cblx0XHRsZXQgZmluaXNoZWQgPSB0aGlzLnVwZGF0ZU1peGluZ0Zyb20oZnJvbSwgZGVsdGEpO1xuXG5cdFx0ZnJvbS5hbmltYXRpb25MYXN0ID0gZnJvbS5uZXh0QW5pbWF0aW9uTGFzdDtcblx0XHRmcm9tLnRyYWNrTGFzdCA9IGZyb20ubmV4dFRyYWNrTGFzdDtcblxuXHRcdC8vIFRoZSBmcm9tIGVudHJ5IHdhcyBhcHBsaWVkIGF0IGxlYXN0IG9uY2UgYW5kIHRoZSBtaXggaXMgY29tcGxldGUuXG5cdFx0aWYgKHRvLm5leHRUcmFja0xhc3QgIT0gLTEgJiYgdG8ubWl4VGltZSA+PSB0by5taXhEdXJhdGlvbikge1xuXHRcdFx0Ly8gTWl4aW5nIGlzIGNvbXBsZXRlIGZvciBhbGwgZW50cmllcyBiZWZvcmUgdGhlIGZyb20gZW50cnkgb3IgdGhlIG1peCBpcyBpbnN0YW50YW5lb3VzLlxuXHRcdFx0aWYgKGZyb20udG90YWxBbHBoYSA9PSAwIHx8IHRvLm1peER1cmF0aW9uID09IDApIHtcblx0XHRcdFx0dG8ubWl4aW5nRnJvbSA9IGZyb20ubWl4aW5nRnJvbTtcblx0XHRcdFx0aWYgKGZyb20ubWl4aW5nRnJvbSAhPSBudWxsKSBmcm9tLm1peGluZ0Zyb20ubWl4aW5nVG8gPSB0bztcblx0XHRcdFx0dG8uaW50ZXJydXB0QWxwaGEgPSBmcm9tLmludGVycnVwdEFscGhhO1xuXHRcdFx0XHR0aGlzLnF1ZXVlLmVuZChmcm9tKTtcblx0XHRcdH1cblx0XHRcdHJldHVybiBmaW5pc2hlZDtcblx0XHR9XG5cblx0XHRmcm9tLnRyYWNrVGltZSArPSBkZWx0YSAqIGZyb20udGltZVNjYWxlO1xuXHRcdHRvLm1peFRpbWUgKz0gZGVsdGE7XG5cdFx0cmV0dXJuIGZhbHNlO1xuXHR9XG5cblx0LyoqIFBvc2VzIHRoZSBza2VsZXRvbiB1c2luZyB0aGUgdHJhY2sgZW50cnkgYW5pbWF0aW9ucy4gVGhlcmUgYXJlIG5vIHNpZGUgZWZmZWN0cyBvdGhlciB0aGFuIGludm9raW5nIGxpc3RlbmVycywgc28gdGhlXG5cdCAqIGFuaW1hdGlvbiBzdGF0ZSBjYW4gYmUgYXBwbGllZCB0byBtdWx0aXBsZSBza2VsZXRvbnMgdG8gcG9zZSB0aGVtIGlkZW50aWNhbGx5LlxuXHQgKiBAcmV0dXJucyBUcnVlIGlmIGFueSBhbmltYXRpb25zIHdlcmUgYXBwbGllZC4gKi9cblx0YXBwbHkgKHNrZWxldG9uOiBTa2VsZXRvbik6IGJvb2xlYW4ge1xuXHRcdGlmICghc2tlbGV0b24pIHRocm93IG5ldyBFcnJvcihcInNrZWxldG9uIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRpZiAodGhpcy5hbmltYXRpb25zQ2hhbmdlZCkgdGhpcy5fYW5pbWF0aW9uc0NoYW5nZWQoKTtcblxuXHRcdGxldCBldmVudHMgPSB0aGlzLmV2ZW50cztcblx0XHRsZXQgdHJhY2tzID0gdGhpcy50cmFja3M7XG5cdFx0bGV0IGFwcGxpZWQgPSBmYWxzZTtcblxuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gdHJhY2tzLmxlbmd0aDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGN1cnJlbnQgPSB0cmFja3NbaV07XG5cdFx0XHRpZiAoIWN1cnJlbnQgfHwgY3VycmVudC5kZWxheSA+IDApIGNvbnRpbnVlO1xuXHRcdFx0YXBwbGllZCA9IHRydWU7XG5cdFx0XHRsZXQgYmxlbmQ6IE1peEJsZW5kID0gaSA9PSAwID8gTWl4QmxlbmQuZmlyc3QgOiBjdXJyZW50Lm1peEJsZW5kO1xuXG5cdFx0XHQvLyBBcHBseSBtaXhpbmcgZnJvbSBlbnRyaWVzIGZpcnN0LlxuXHRcdFx0bGV0IGFscGhhID0gY3VycmVudC5hbHBoYTtcblx0XHRcdGlmIChjdXJyZW50Lm1peGluZ0Zyb20pXG5cdFx0XHRcdGFscGhhICo9IHRoaXMuYXBwbHlNaXhpbmdGcm9tKGN1cnJlbnQsIHNrZWxldG9uLCBibGVuZCk7XG5cdFx0XHRlbHNlIGlmIChjdXJyZW50LnRyYWNrVGltZSA+PSBjdXJyZW50LnRyYWNrRW5kICYmICFjdXJyZW50Lm5leHQpXG5cdFx0XHRcdGFscGhhID0gMDtcblx0XHRcdGxldCBhdHRhY2htZW50cyA9IGFscGhhID49IGN1cnJlbnQuYWxwaGFBdHRhY2htZW50VGhyZXNob2xkO1xuXG5cblx0XHRcdC8vIEFwcGx5IGN1cnJlbnQgZW50cnkuXG5cdFx0XHRsZXQgYW5pbWF0aW9uTGFzdCA9IGN1cnJlbnQuYW5pbWF0aW9uTGFzdCwgYW5pbWF0aW9uVGltZSA9IGN1cnJlbnQuZ2V0QW5pbWF0aW9uVGltZSgpLCBhcHBseVRpbWUgPSBhbmltYXRpb25UaW1lO1xuXHRcdFx0bGV0IGFwcGx5RXZlbnRzOiBFdmVudFtdIHwgbnVsbCA9IGV2ZW50cztcblx0XHRcdGlmIChjdXJyZW50LnJldmVyc2UpIHtcblx0XHRcdFx0YXBwbHlUaW1lID0gY3VycmVudC5hbmltYXRpb24hLmR1cmF0aW9uIC0gYXBwbHlUaW1lO1xuXHRcdFx0XHRhcHBseUV2ZW50cyA9IG51bGw7XG5cdFx0XHR9XG5cdFx0XHRsZXQgdGltZWxpbmVzID0gY3VycmVudC5hbmltYXRpb24hLnRpbWVsaW5lcztcblx0XHRcdGxldCB0aW1lbGluZUNvdW50ID0gdGltZWxpbmVzLmxlbmd0aDtcblx0XHRcdGlmICgoaSA9PSAwICYmIGFscGhhID09IDEpIHx8IGJsZW5kID09IE1peEJsZW5kLmFkZCkge1xuXHRcdFx0XHRpZiAoaSA9PSAwKSBhdHRhY2htZW50cyA9IHRydWU7XG5cdFx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCB0aW1lbGluZUNvdW50OyBpaSsrKSB7XG5cdFx0XHRcdFx0Ly8gRml4ZXMgaXNzdWUgIzMwMiBvbiBJT1M5IHdoZXJlIG1peCwgYmxlbmQgc29tZXRpbWVzIGJlY2FtZSB1bmRlZmluZWQgYW5kIGNhdXNlZCBhc3NldHNcblx0XHRcdFx0XHQvLyB0byBzb21ldGltZXMgc3RvcCByZW5kZXJpbmcgd2hlbiB1c2luZyBjb2xvciBjb3JyZWN0aW9uLCBhcyB0aGVpciBSR0JBIHZhbHVlcyBiZWNvbWUgTmFOLlxuXHRcdFx0XHRcdC8vIChodHRwczovL2dpdGh1Yi5jb20vcGl4aWpzL3BpeGktc3BpbmUvaXNzdWVzLzMwMilcblx0XHRcdFx0XHRVdGlscy53ZWJraXQ2MDJCdWdmaXhIZWxwZXIoYWxwaGEsIGJsZW5kKTtcblx0XHRcdFx0XHR2YXIgdGltZWxpbmUgPSB0aW1lbGluZXNbaWldO1xuXHRcdFx0XHRcdGlmICh0aW1lbGluZSBpbnN0YW5jZW9mIEF0dGFjaG1lbnRUaW1lbGluZSlcblx0XHRcdFx0XHRcdHRoaXMuYXBwbHlBdHRhY2htZW50VGltZWxpbmUodGltZWxpbmUsIHNrZWxldG9uLCBhcHBseVRpbWUsIGJsZW5kLCBhdHRhY2htZW50cyk7XG5cdFx0XHRcdFx0ZWxzZVxuXHRcdFx0XHRcdFx0dGltZWxpbmUuYXBwbHkoc2tlbGV0b24sIGFuaW1hdGlvbkxhc3QsIGFwcGx5VGltZSwgYXBwbHlFdmVudHMsIGFscGhhLCBibGVuZCwgTWl4RGlyZWN0aW9uLm1peEluKTtcblx0XHRcdFx0fVxuXHRcdFx0fSBlbHNlIHtcblx0XHRcdFx0bGV0IHRpbWVsaW5lTW9kZSA9IGN1cnJlbnQudGltZWxpbmVNb2RlO1xuXG5cdFx0XHRcdGxldCBzaG9ydGVzdFJvdGF0aW9uID0gY3VycmVudC5zaG9ydGVzdFJvdGF0aW9uO1xuXHRcdFx0XHRsZXQgZmlyc3RGcmFtZSA9ICFzaG9ydGVzdFJvdGF0aW9uICYmIGN1cnJlbnQudGltZWxpbmVzUm90YXRpb24ubGVuZ3RoICE9IHRpbWVsaW5lQ291bnQgPDwgMTtcblx0XHRcdFx0aWYgKGZpcnN0RnJhbWUpIGN1cnJlbnQudGltZWxpbmVzUm90YXRpb24ubGVuZ3RoID0gdGltZWxpbmVDb3VudCA8PCAxO1xuXG5cdFx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCB0aW1lbGluZUNvdW50OyBpaSsrKSB7XG5cdFx0XHRcdFx0bGV0IHRpbWVsaW5lID0gdGltZWxpbmVzW2lpXTtcblx0XHRcdFx0XHRsZXQgdGltZWxpbmVCbGVuZCA9IHRpbWVsaW5lTW9kZVtpaV0gPT0gU1VCU0VRVUVOVCA/IGJsZW5kIDogTWl4QmxlbmQuc2V0dXA7XG5cdFx0XHRcdFx0aWYgKCFzaG9ydGVzdFJvdGF0aW9uICYmIHRpbWVsaW5lIGluc3RhbmNlb2YgUm90YXRlVGltZWxpbmUpIHtcblx0XHRcdFx0XHRcdHRoaXMuYXBwbHlSb3RhdGVUaW1lbGluZSh0aW1lbGluZSwgc2tlbGV0b24sIGFwcGx5VGltZSwgYWxwaGEsIHRpbWVsaW5lQmxlbmQsIGN1cnJlbnQudGltZWxpbmVzUm90YXRpb24sIGlpIDw8IDEsIGZpcnN0RnJhbWUpO1xuXHRcdFx0XHRcdH0gZWxzZSBpZiAodGltZWxpbmUgaW5zdGFuY2VvZiBBdHRhY2htZW50VGltZWxpbmUpIHtcblx0XHRcdFx0XHRcdHRoaXMuYXBwbHlBdHRhY2htZW50VGltZWxpbmUodGltZWxpbmUsIHNrZWxldG9uLCBhcHBseVRpbWUsIGJsZW5kLCBhdHRhY2htZW50cyk7XG5cdFx0XHRcdFx0fSBlbHNlIHtcblx0XHRcdFx0XHRcdC8vIFRoaXMgZml4ZXMgdGhlIFdlYktpdCA2MDIgc3BlY2lmaWMgaXNzdWUgZGVzY3JpYmVkIGF0IGh0dHA6Ly9lc290ZXJpY3NvZnR3YXJlLmNvbS9mb3J1bS9pT1MtMTAtZGlzYXBwZWFyaW5nLWdyYXBoaWNzLTEwMTA5XG5cdFx0XHRcdFx0XHRVdGlscy53ZWJraXQ2MDJCdWdmaXhIZWxwZXIoYWxwaGEsIGJsZW5kKTtcblx0XHRcdFx0XHRcdHRpbWVsaW5lLmFwcGx5KHNrZWxldG9uLCBhbmltYXRpb25MYXN0LCBhcHBseVRpbWUsIGFwcGx5RXZlbnRzLCBhbHBoYSwgdGltZWxpbmVCbGVuZCwgTWl4RGlyZWN0aW9uLm1peEluKTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHRcdHRoaXMucXVldWVFdmVudHMoY3VycmVudCwgYW5pbWF0aW9uVGltZSk7XG5cdFx0XHRldmVudHMubGVuZ3RoID0gMDtcblx0XHRcdGN1cnJlbnQubmV4dEFuaW1hdGlvbkxhc3QgPSBhbmltYXRpb25UaW1lO1xuXHRcdFx0Y3VycmVudC5uZXh0VHJhY2tMYXN0ID0gY3VycmVudC50cmFja1RpbWU7XG5cdFx0fVxuXG5cdFx0Ly8gU2V0IHNsb3RzIGF0dGFjaG1lbnRzIHRvIHRoZSBzZXR1cCBwb3NlLCBpZiBuZWVkZWQuIFRoaXMgb2NjdXJzIGlmIGFuIGFuaW1hdGlvbiB0aGF0IGlzIG1peGluZyBvdXQgc2V0cyBhdHRhY2htZW50cyBzb1xuXHRcdC8vIHN1YnNlcXVlbnQgdGltZWxpbmVzIHNlZSBhbnkgZGVmb3JtLCBidXQgdGhlIHN1YnNlcXVlbnQgdGltZWxpbmVzIGRvbid0IHNldCBhbiBhdHRhY2htZW50IChlZyB0aGV5IGFyZSBhbHNvIG1peGluZyBvdXQgb3Jcblx0XHQvLyB0aGUgdGltZSBpcyBiZWZvcmUgdGhlIGZpcnN0IGtleSkuXG5cdFx0dmFyIHNldHVwU3RhdGUgPSB0aGlzLnVua2V5ZWRTdGF0ZSArIFNFVFVQO1xuXHRcdHZhciBzbG90cyA9IHNrZWxldG9uLnNsb3RzO1xuXHRcdGZvciAodmFyIGkgPSAwLCBuID0gc2tlbGV0b24uc2xvdHMubGVuZ3RoOyBpIDwgbjsgaSsrKSB7XG5cdFx0XHR2YXIgc2xvdCA9IHNsb3RzW2ldO1xuXHRcdFx0aWYgKHNsb3QuYXR0YWNobWVudFN0YXRlID09IHNldHVwU3RhdGUpIHtcblx0XHRcdFx0dmFyIGF0dGFjaG1lbnROYW1lID0gc2xvdC5kYXRhLmF0dGFjaG1lbnROYW1lO1xuXHRcdFx0XHRzbG90LnNldEF0dGFjaG1lbnQoIWF0dGFjaG1lbnROYW1lID8gbnVsbCA6IHNrZWxldG9uLmdldEF0dGFjaG1lbnQoc2xvdC5kYXRhLmluZGV4LCBhdHRhY2htZW50TmFtZSkpO1xuXHRcdFx0fVxuXHRcdH1cblx0XHR0aGlzLnVua2V5ZWRTdGF0ZSArPSAyOyAvLyBJbmNyZWFzaW5nIGFmdGVyIGVhY2ggdXNlIGF2b2lkcyB0aGUgbmVlZCB0byByZXNldCBhdHRhY2htZW50U3RhdGUgZm9yIGV2ZXJ5IHNsb3QuXG5cblx0XHR0aGlzLnF1ZXVlLmRyYWluKCk7XG5cdFx0cmV0dXJuIGFwcGxpZWQ7XG5cdH1cblxuXHRhcHBseU1peGluZ0Zyb20gKHRvOiBUcmFja0VudHJ5LCBza2VsZXRvbjogU2tlbGV0b24sIGJsZW5kOiBNaXhCbGVuZCkge1xuXHRcdGxldCBmcm9tID0gdG8ubWl4aW5nRnJvbSE7XG5cdFx0aWYgKGZyb20ubWl4aW5nRnJvbSkgdGhpcy5hcHBseU1peGluZ0Zyb20oZnJvbSwgc2tlbGV0b24sIGJsZW5kKTtcblxuXHRcdGxldCBtaXggPSAwO1xuXHRcdGlmICh0by5taXhEdXJhdGlvbiA9PSAwKSB7IC8vIFNpbmdsZSBmcmFtZSBtaXggdG8gdW5kbyBtaXhpbmdGcm9tIGNoYW5nZXMuXG5cdFx0XHRtaXggPSAxO1xuXHRcdFx0aWYgKGJsZW5kID09IE1peEJsZW5kLmZpcnN0KSBibGVuZCA9IE1peEJsZW5kLnNldHVwO1xuXHRcdH0gZWxzZSB7XG5cdFx0XHRtaXggPSB0by5taXhUaW1lIC8gdG8ubWl4RHVyYXRpb247XG5cdFx0XHRpZiAobWl4ID4gMSkgbWl4ID0gMTtcblx0XHRcdGlmIChibGVuZCAhPSBNaXhCbGVuZC5maXJzdCkgYmxlbmQgPSBmcm9tLm1peEJsZW5kO1xuXHRcdH1cblxuXHRcdGxldCBhdHRhY2htZW50cyA9IG1peCA8IGZyb20ubWl4QXR0YWNobWVudFRocmVzaG9sZCwgZHJhd09yZGVyID0gbWl4IDwgZnJvbS5taXhEcmF3T3JkZXJUaHJlc2hvbGQ7XG5cdFx0bGV0IHRpbWVsaW5lcyA9IGZyb20uYW5pbWF0aW9uIS50aW1lbGluZXM7XG5cdFx0bGV0IHRpbWVsaW5lQ291bnQgPSB0aW1lbGluZXMubGVuZ3RoO1xuXHRcdGxldCBhbHBoYUhvbGQgPSBmcm9tLmFscGhhICogdG8uaW50ZXJydXB0QWxwaGEsIGFscGhhTWl4ID0gYWxwaGFIb2xkICogKDEgLSBtaXgpO1xuXHRcdGxldCBhbmltYXRpb25MYXN0ID0gZnJvbS5hbmltYXRpb25MYXN0LCBhbmltYXRpb25UaW1lID0gZnJvbS5nZXRBbmltYXRpb25UaW1lKCksIGFwcGx5VGltZSA9IGFuaW1hdGlvblRpbWU7XG5cdFx0bGV0IGV2ZW50cyA9IG51bGw7XG5cdFx0aWYgKGZyb20ucmV2ZXJzZSlcblx0XHRcdGFwcGx5VGltZSA9IGZyb20uYW5pbWF0aW9uIS5kdXJhdGlvbiAtIGFwcGx5VGltZTtcblx0XHRlbHNlIGlmIChtaXggPCBmcm9tLmV2ZW50VGhyZXNob2xkKVxuXHRcdFx0ZXZlbnRzID0gdGhpcy5ldmVudHM7XG5cblx0XHRpZiAoYmxlbmQgPT0gTWl4QmxlbmQuYWRkKSB7XG5cdFx0XHRmb3IgKGxldCBpID0gMDsgaSA8IHRpbWVsaW5lQ291bnQ7IGkrKylcblx0XHRcdFx0dGltZWxpbmVzW2ldLmFwcGx5KHNrZWxldG9uLCBhbmltYXRpb25MYXN0LCBhcHBseVRpbWUsIGV2ZW50cywgYWxwaGFNaXgsIGJsZW5kLCBNaXhEaXJlY3Rpb24ubWl4T3V0KTtcblx0XHR9IGVsc2Uge1xuXHRcdFx0bGV0IHRpbWVsaW5lTW9kZSA9IGZyb20udGltZWxpbmVNb2RlO1xuXHRcdFx0bGV0IHRpbWVsaW5lSG9sZE1peCA9IGZyb20udGltZWxpbmVIb2xkTWl4O1xuXG5cdFx0XHRsZXQgc2hvcnRlc3RSb3RhdGlvbiA9IGZyb20uc2hvcnRlc3RSb3RhdGlvbjtcblx0XHRcdGxldCBmaXJzdEZyYW1lID0gIXNob3J0ZXN0Um90YXRpb24gJiYgZnJvbS50aW1lbGluZXNSb3RhdGlvbi5sZW5ndGggIT0gdGltZWxpbmVDb3VudCA8PCAxO1xuXHRcdFx0aWYgKGZpcnN0RnJhbWUpIGZyb20udGltZWxpbmVzUm90YXRpb24ubGVuZ3RoID0gdGltZWxpbmVDb3VudCA8PCAxO1xuXG5cdFx0XHRmcm9tLnRvdGFsQWxwaGEgPSAwO1xuXHRcdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCB0aW1lbGluZUNvdW50OyBpKyspIHtcblx0XHRcdFx0bGV0IHRpbWVsaW5lID0gdGltZWxpbmVzW2ldO1xuXHRcdFx0XHRsZXQgZGlyZWN0aW9uID0gTWl4RGlyZWN0aW9uLm1peE91dDtcblx0XHRcdFx0bGV0IHRpbWVsaW5lQmxlbmQ6IE1peEJsZW5kO1xuXHRcdFx0XHRsZXQgYWxwaGEgPSAwO1xuXHRcdFx0XHRzd2l0Y2ggKHRpbWVsaW5lTW9kZVtpXSkge1xuXHRcdFx0XHRcdGNhc2UgU1VCU0VRVUVOVDpcblx0XHRcdFx0XHRcdGlmICghZHJhd09yZGVyICYmIHRpbWVsaW5lIGluc3RhbmNlb2YgRHJhd09yZGVyVGltZWxpbmUpIGNvbnRpbnVlO1xuXHRcdFx0XHRcdFx0dGltZWxpbmVCbGVuZCA9IGJsZW5kO1xuXHRcdFx0XHRcdFx0YWxwaGEgPSBhbHBoYU1peDtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgRklSU1Q6XG5cdFx0XHRcdFx0XHR0aW1lbGluZUJsZW5kID0gTWl4QmxlbmQuc2V0dXA7XG5cdFx0XHRcdFx0XHRhbHBoYSA9IGFscGhhTWl4O1xuXHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0Y2FzZSBIT0xEX1NVQlNFUVVFTlQ6XG5cdFx0XHRcdFx0XHR0aW1lbGluZUJsZW5kID0gYmxlbmQ7XG5cdFx0XHRcdFx0XHRhbHBoYSA9IGFscGhhSG9sZDtcblx0XHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRcdGNhc2UgSE9MRF9GSVJTVDpcblx0XHRcdFx0XHRcdHRpbWVsaW5lQmxlbmQgPSBNaXhCbGVuZC5zZXR1cDtcblx0XHRcdFx0XHRcdGFscGhhID0gYWxwaGFIb2xkO1xuXHRcdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdFx0ZGVmYXVsdDpcblx0XHRcdFx0XHRcdHRpbWVsaW5lQmxlbmQgPSBNaXhCbGVuZC5zZXR1cDtcblx0XHRcdFx0XHRcdGxldCBob2xkTWl4ID0gdGltZWxpbmVIb2xkTWl4W2ldO1xuXHRcdFx0XHRcdFx0YWxwaGEgPSBhbHBoYUhvbGQgKiBNYXRoLm1heCgwLCAxIC0gaG9sZE1peC5taXhUaW1lIC8gaG9sZE1peC5taXhEdXJhdGlvbik7XG5cdFx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0fVxuXHRcdFx0XHRmcm9tLnRvdGFsQWxwaGEgKz0gYWxwaGE7XG5cblx0XHRcdFx0aWYgKCFzaG9ydGVzdFJvdGF0aW9uICYmIHRpbWVsaW5lIGluc3RhbmNlb2YgUm90YXRlVGltZWxpbmUpXG5cdFx0XHRcdFx0dGhpcy5hcHBseVJvdGF0ZVRpbWVsaW5lKHRpbWVsaW5lLCBza2VsZXRvbiwgYXBwbHlUaW1lLCBhbHBoYSwgdGltZWxpbmVCbGVuZCwgZnJvbS50aW1lbGluZXNSb3RhdGlvbiwgaSA8PCAxLCBmaXJzdEZyYW1lKTtcblx0XHRcdFx0ZWxzZSBpZiAodGltZWxpbmUgaW5zdGFuY2VvZiBBdHRhY2htZW50VGltZWxpbmUpXG5cdFx0XHRcdFx0dGhpcy5hcHBseUF0dGFjaG1lbnRUaW1lbGluZSh0aW1lbGluZSwgc2tlbGV0b24sIGFwcGx5VGltZSwgdGltZWxpbmVCbGVuZCwgYXR0YWNobWVudHMgJiYgYWxwaGEgPj0gZnJvbS5hbHBoYUF0dGFjaG1lbnRUaHJlc2hvbGQpO1xuXHRcdFx0XHRlbHNlIHtcblx0XHRcdFx0XHQvLyBUaGlzIGZpeGVzIHRoZSBXZWJLaXQgNjAyIHNwZWNpZmljIGlzc3VlIGRlc2NyaWJlZCBhdCBodHRwOi8vZXNvdGVyaWNzb2Z0d2FyZS5jb20vZm9ydW0vaU9TLTEwLWRpc2FwcGVhcmluZy1ncmFwaGljcy0xMDEwOVxuXHRcdFx0XHRcdFV0aWxzLndlYmtpdDYwMkJ1Z2ZpeEhlbHBlcihhbHBoYSwgYmxlbmQpO1xuXHRcdFx0XHRcdGlmIChkcmF3T3JkZXIgJiYgdGltZWxpbmUgaW5zdGFuY2VvZiBEcmF3T3JkZXJUaW1lbGluZSAmJiB0aW1lbGluZUJsZW5kID09IE1peEJsZW5kLnNldHVwKVxuXHRcdFx0XHRcdFx0ZGlyZWN0aW9uID0gTWl4RGlyZWN0aW9uLm1peEluO1xuXHRcdFx0XHRcdHRpbWVsaW5lLmFwcGx5KHNrZWxldG9uLCBhbmltYXRpb25MYXN0LCBhcHBseVRpbWUsIGV2ZW50cywgYWxwaGEsIHRpbWVsaW5lQmxlbmQsIGRpcmVjdGlvbik7XG5cdFx0XHRcdH1cblx0XHRcdH1cblx0XHR9XG5cblx0XHRpZiAodG8ubWl4RHVyYXRpb24gPiAwKSB0aGlzLnF1ZXVlRXZlbnRzKGZyb20sIGFuaW1hdGlvblRpbWUpO1xuXHRcdHRoaXMuZXZlbnRzLmxlbmd0aCA9IDA7XG5cdFx0ZnJvbS5uZXh0QW5pbWF0aW9uTGFzdCA9IGFuaW1hdGlvblRpbWU7XG5cdFx0ZnJvbS5uZXh0VHJhY2tMYXN0ID0gZnJvbS50cmFja1RpbWU7XG5cblx0XHRyZXR1cm4gbWl4O1xuXHR9XG5cblx0YXBwbHlBdHRhY2htZW50VGltZWxpbmUgKHRpbWVsaW5lOiBBdHRhY2htZW50VGltZWxpbmUsIHNrZWxldG9uOiBTa2VsZXRvbiwgdGltZTogbnVtYmVyLCBibGVuZDogTWl4QmxlbmQsIGF0dGFjaG1lbnRzOiBib29sZWFuKSB7XG5cdFx0dmFyIHNsb3QgPSBza2VsZXRvbi5zbG90c1t0aW1lbGluZS5zbG90SW5kZXhdO1xuXHRcdGlmICghc2xvdC5ib25lLmFjdGl2ZSkgcmV0dXJuO1xuXG5cdFx0aWYgKHRpbWUgPCB0aW1lbGluZS5mcmFtZXNbMF0pIHsgLy8gVGltZSBpcyBiZWZvcmUgZmlyc3QgZnJhbWUuXG5cdFx0XHRpZiAoYmxlbmQgPT0gTWl4QmxlbmQuc2V0dXAgfHwgYmxlbmQgPT0gTWl4QmxlbmQuZmlyc3QpXG5cdFx0XHRcdHRoaXMuc2V0QXR0YWNobWVudChza2VsZXRvbiwgc2xvdCwgc2xvdC5kYXRhLmF0dGFjaG1lbnROYW1lLCBhdHRhY2htZW50cyk7XG5cdFx0fSBlbHNlXG5cdFx0XHR0aGlzLnNldEF0dGFjaG1lbnQoc2tlbGV0b24sIHNsb3QsIHRpbWVsaW5lLmF0dGFjaG1lbnROYW1lc1tUaW1lbGluZS5zZWFyY2gxKHRpbWVsaW5lLmZyYW1lcywgdGltZSldLCBhdHRhY2htZW50cyk7XG5cblx0XHQvLyBJZiBhbiBhdHRhY2htZW50IHdhc24ndCBzZXQgKGllIGJlZm9yZSB0aGUgZmlyc3QgZnJhbWUgb3IgYXR0YWNobWVudHMgaXMgZmFsc2UpLCBzZXQgdGhlIHNldHVwIGF0dGFjaG1lbnQgbGF0ZXIuXG5cdFx0aWYgKHNsb3QuYXR0YWNobWVudFN0YXRlIDw9IHRoaXMudW5rZXllZFN0YXRlKSBzbG90LmF0dGFjaG1lbnRTdGF0ZSA9IHRoaXMudW5rZXllZFN0YXRlICsgU0VUVVA7XG5cdH1cblxuXHRzZXRBdHRhY2htZW50IChza2VsZXRvbjogU2tlbGV0b24sIHNsb3Q6IFNsb3QsIGF0dGFjaG1lbnROYW1lOiBzdHJpbmcgfCBudWxsLCBhdHRhY2htZW50czogYm9vbGVhbikge1xuXHRcdHNsb3Quc2V0QXR0YWNobWVudCghYXR0YWNobWVudE5hbWUgPyBudWxsIDogc2tlbGV0b24uZ2V0QXR0YWNobWVudChzbG90LmRhdGEuaW5kZXgsIGF0dGFjaG1lbnROYW1lKSk7XG5cdFx0aWYgKGF0dGFjaG1lbnRzKSBzbG90LmF0dGFjaG1lbnRTdGF0ZSA9IHRoaXMudW5rZXllZFN0YXRlICsgQ1VSUkVOVDtcblx0fVxuXG5cdGFwcGx5Um90YXRlVGltZWxpbmUgKHRpbWVsaW5lOiBSb3RhdGVUaW1lbGluZSwgc2tlbGV0b246IFNrZWxldG9uLCB0aW1lOiBudW1iZXIsIGFscGhhOiBudW1iZXIsIGJsZW5kOiBNaXhCbGVuZCxcblx0XHR0aW1lbGluZXNSb3RhdGlvbjogQXJyYXk8bnVtYmVyPiwgaTogbnVtYmVyLCBmaXJzdEZyYW1lOiBib29sZWFuKSB7XG5cblx0XHRpZiAoZmlyc3RGcmFtZSkgdGltZWxpbmVzUm90YXRpb25baV0gPSAwO1xuXG5cdFx0aWYgKGFscGhhID09IDEpIHtcblx0XHRcdHRpbWVsaW5lLmFwcGx5KHNrZWxldG9uLCAwLCB0aW1lLCBudWxsLCAxLCBibGVuZCwgTWl4RGlyZWN0aW9uLm1peEluKTtcblx0XHRcdHJldHVybjtcblx0XHR9XG5cblx0XHRsZXQgYm9uZSA9IHNrZWxldG9uLmJvbmVzW3RpbWVsaW5lLmJvbmVJbmRleF07XG5cdFx0aWYgKCFib25lLmFjdGl2ZSkgcmV0dXJuO1xuXHRcdGxldCBmcmFtZXMgPSB0aW1lbGluZS5mcmFtZXM7XG5cdFx0bGV0IHIxID0gMCwgcjIgPSAwO1xuXHRcdGlmICh0aW1lIDwgZnJhbWVzWzBdKSB7XG5cdFx0XHRzd2l0Y2ggKGJsZW5kKSB7XG5cdFx0XHRcdGNhc2UgTWl4QmxlbmQuc2V0dXA6XG5cdFx0XHRcdFx0Ym9uZS5yb3RhdGlvbiA9IGJvbmUuZGF0YS5yb3RhdGlvbjtcblx0XHRcdFx0ZGVmYXVsdDpcblx0XHRcdFx0XHRyZXR1cm47XG5cdFx0XHRcdGNhc2UgTWl4QmxlbmQuZmlyc3Q6XG5cdFx0XHRcdFx0cjEgPSBib25lLnJvdGF0aW9uO1xuXHRcdFx0XHRcdHIyID0gYm9uZS5kYXRhLnJvdGF0aW9uO1xuXHRcdFx0fVxuXHRcdH0gZWxzZSB7XG5cdFx0XHRyMSA9IGJsZW5kID09IE1peEJsZW5kLnNldHVwID8gYm9uZS5kYXRhLnJvdGF0aW9uIDogYm9uZS5yb3RhdGlvbjtcblx0XHRcdHIyID0gYm9uZS5kYXRhLnJvdGF0aW9uICsgdGltZWxpbmUuZ2V0Q3VydmVWYWx1ZSh0aW1lKTtcblx0XHR9XG5cblx0XHQvLyBNaXggYmV0d2VlbiByb3RhdGlvbnMgdXNpbmcgdGhlIGRpcmVjdGlvbiBvZiB0aGUgc2hvcnRlc3Qgcm91dGUgb24gdGhlIGZpcnN0IGZyYW1lIHdoaWxlIGRldGVjdGluZyBjcm9zc2VzLlxuXHRcdGxldCB0b3RhbCA9IDAsIGRpZmYgPSByMiAtIHIxO1xuXHRcdGRpZmYgLT0gTWF0aC5jZWlsKGRpZmYgLyAzNjAgLSAwLjUpICogMzYwO1xuXHRcdGlmIChkaWZmID09IDApIHtcblx0XHRcdHRvdGFsID0gdGltZWxpbmVzUm90YXRpb25baV07XG5cdFx0fSBlbHNlIHtcblx0XHRcdGxldCBsYXN0VG90YWwgPSAwLCBsYXN0RGlmZiA9IDA7XG5cdFx0XHRpZiAoZmlyc3RGcmFtZSkge1xuXHRcdFx0XHRsYXN0VG90YWwgPSAwO1xuXHRcdFx0XHRsYXN0RGlmZiA9IGRpZmY7XG5cdFx0XHR9IGVsc2Uge1xuXHRcdFx0XHRsYXN0VG90YWwgPSB0aW1lbGluZXNSb3RhdGlvbltpXTtcblx0XHRcdFx0bGFzdERpZmYgPSB0aW1lbGluZXNSb3RhdGlvbltpICsgMV07XG5cdFx0XHR9XG5cdFx0XHRsZXQgbG9vcHMgPSBsYXN0VG90YWwgLSBsYXN0VG90YWwgJSAzNjA7XG5cdFx0XHR0b3RhbCA9IGRpZmYgKyBsb29wcztcblx0XHRcdGxldCBjdXJyZW50ID0gZGlmZiA+PSAwLCBkaXIgPSBsYXN0VG90YWwgPj0gMDtcblx0XHRcdGlmIChNYXRoLmFicyhsYXN0RGlmZikgPD0gOTAgJiYgTWF0aFV0aWxzLnNpZ251bShsYXN0RGlmZikgIT0gTWF0aFV0aWxzLnNpZ251bShkaWZmKSkge1xuXHRcdFx0XHRpZiAoTWF0aC5hYnMobGFzdFRvdGFsIC0gbG9vcHMpID4gMTgwKSB7XG5cdFx0XHRcdFx0dG90YWwgKz0gMzYwICogTWF0aFV0aWxzLnNpZ251bShsYXN0VG90YWwpO1xuXHRcdFx0XHRcdGRpciA9IGN1cnJlbnQ7XG5cdFx0XHRcdH0gZWxzZSBpZiAobG9vcHMgIT0gMClcblx0XHRcdFx0XHR0b3RhbCAtPSAzNjAgKiBNYXRoVXRpbHMuc2lnbnVtKGxhc3RUb3RhbCk7XG5cdFx0XHRcdGVsc2Vcblx0XHRcdFx0XHRkaXIgPSBjdXJyZW50O1xuXHRcdFx0fVxuXHRcdFx0aWYgKGRpciAhPSBjdXJyZW50KSB0b3RhbCArPSAzNjAgKiBNYXRoVXRpbHMuc2lnbnVtKGxhc3RUb3RhbCk7XG5cdFx0XHR0aW1lbGluZXNSb3RhdGlvbltpXSA9IHRvdGFsO1xuXHRcdH1cblx0XHR0aW1lbGluZXNSb3RhdGlvbltpICsgMV0gPSBkaWZmO1xuXHRcdGJvbmUucm90YXRpb24gPSByMSArIHRvdGFsICogYWxwaGE7XG5cdH1cblxuXHRxdWV1ZUV2ZW50cyAoZW50cnk6IFRyYWNrRW50cnksIGFuaW1hdGlvblRpbWU6IG51bWJlcikge1xuXHRcdGxldCBhbmltYXRpb25TdGFydCA9IGVudHJ5LmFuaW1hdGlvblN0YXJ0LCBhbmltYXRpb25FbmQgPSBlbnRyeS5hbmltYXRpb25FbmQ7XG5cdFx0bGV0IGR1cmF0aW9uID0gYW5pbWF0aW9uRW5kIC0gYW5pbWF0aW9uU3RhcnQ7XG5cdFx0bGV0IHRyYWNrTGFzdFdyYXBwZWQgPSBlbnRyeS50cmFja0xhc3QgJSBkdXJhdGlvbjtcblxuXHRcdC8vIFF1ZXVlIGV2ZW50cyBiZWZvcmUgY29tcGxldGUuXG5cdFx0bGV0IGV2ZW50cyA9IHRoaXMuZXZlbnRzO1xuXHRcdGxldCBpID0gMCwgbiA9IGV2ZW50cy5sZW5ndGg7XG5cdFx0Zm9yICg7IGkgPCBuOyBpKyspIHtcblx0XHRcdGxldCBldmVudCA9IGV2ZW50c1tpXTtcblx0XHRcdGlmIChldmVudC50aW1lIDwgdHJhY2tMYXN0V3JhcHBlZCkgYnJlYWs7XG5cdFx0XHRpZiAoZXZlbnQudGltZSA+IGFuaW1hdGlvbkVuZCkgY29udGludWU7IC8vIERpc2NhcmQgZXZlbnRzIG91dHNpZGUgYW5pbWF0aW9uIHN0YXJ0L2VuZC5cblx0XHRcdHRoaXMucXVldWUuZXZlbnQoZW50cnksIGV2ZW50KTtcblx0XHR9XG5cblx0XHQvLyBRdWV1ZSBjb21wbGV0ZSBpZiBjb21wbGV0ZWQgYSBsb29wIGl0ZXJhdGlvbiBvciB0aGUgYW5pbWF0aW9uLlxuXHRcdGxldCBjb21wbGV0ZSA9IGZhbHNlO1xuXHRcdGlmIChlbnRyeS5sb29wKSB7XG5cdFx0XHRpZiAoZHVyYXRpb24gPT0gMClcblx0XHRcdFx0Y29tcGxldGUgPSB0cnVlO1xuXHRcdFx0ZWxzZSB7XG5cdFx0XHRcdGNvbnN0IGN5Y2xlcyA9IE1hdGguZmxvb3IoZW50cnkudHJhY2tUaW1lIC8gZHVyYXRpb24pO1xuXHRcdFx0XHRjb21wbGV0ZSA9IGN5Y2xlcyA+IDAgJiYgY3ljbGVzID4gTWF0aC5mbG9vcihlbnRyeS50cmFja0xhc3QgLyBkdXJhdGlvbik7XG5cdFx0XHR9XG5cdFx0fSBlbHNlXG5cdFx0XHRjb21wbGV0ZSA9IGFuaW1hdGlvblRpbWUgPj0gYW5pbWF0aW9uRW5kICYmIGVudHJ5LmFuaW1hdGlvbkxhc3QgPCBhbmltYXRpb25FbmQ7XG5cdFx0aWYgKGNvbXBsZXRlKSB0aGlzLnF1ZXVlLmNvbXBsZXRlKGVudHJ5KTtcblxuXHRcdC8vIFF1ZXVlIGV2ZW50cyBhZnRlciBjb21wbGV0ZS5cblx0XHRmb3IgKDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGV2ZW50ID0gZXZlbnRzW2ldO1xuXHRcdFx0aWYgKGV2ZW50LnRpbWUgPCBhbmltYXRpb25TdGFydCkgY29udGludWU7IC8vIERpc2NhcmQgZXZlbnRzIG91dHNpZGUgYW5pbWF0aW9uIHN0YXJ0L2VuZC5cblx0XHRcdHRoaXMucXVldWUuZXZlbnQoZW50cnksIGV2ZW50KTtcblx0XHR9XG5cdH1cblxuXHQvKiogUmVtb3ZlcyBhbGwgYW5pbWF0aW9ucyBmcm9tIGFsbCB0cmFja3MsIGxlYXZpbmcgc2tlbGV0b25zIGluIHRoZWlyIGN1cnJlbnQgcG9zZS5cblx0ICpcblx0ICogSXQgbWF5IGJlIGRlc2lyZWQgdG8gdXNlIHtAbGluayBBbmltYXRpb25TdGF0ZSNzZXRFbXB0eUFuaW1hdGlvbigpfSB0byBtaXggdGhlIHNrZWxldG9ucyBiYWNrIHRvIHRoZSBzZXR1cCBwb3NlLFxuXHQgKiByYXRoZXIgdGhhbiBsZWF2aW5nIHRoZW0gaW4gdGhlaXIgY3VycmVudCBwb3NlLiAqL1xuXHRjbGVhclRyYWNrcyAoKSB7XG5cdFx0bGV0IG9sZERyYWluRGlzYWJsZWQgPSB0aGlzLnF1ZXVlLmRyYWluRGlzYWJsZWQ7XG5cdFx0dGhpcy5xdWV1ZS5kcmFpbkRpc2FibGVkID0gdHJ1ZTtcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IHRoaXMudHJhY2tzLmxlbmd0aDsgaSA8IG47IGkrKylcblx0XHRcdHRoaXMuY2xlYXJUcmFjayhpKTtcblx0XHR0aGlzLnRyYWNrcy5sZW5ndGggPSAwO1xuXHRcdHRoaXMucXVldWUuZHJhaW5EaXNhYmxlZCA9IG9sZERyYWluRGlzYWJsZWQ7XG5cdFx0dGhpcy5xdWV1ZS5kcmFpbigpO1xuXHR9XG5cblx0LyoqIFJlbW92ZXMgYWxsIGFuaW1hdGlvbnMgZnJvbSB0aGUgdHJhY2ssIGxlYXZpbmcgc2tlbGV0b25zIGluIHRoZWlyIGN1cnJlbnQgcG9zZS5cblx0ICpcblx0ICogSXQgbWF5IGJlIGRlc2lyZWQgdG8gdXNlIHtAbGluayBBbmltYXRpb25TdGF0ZSNzZXRFbXB0eUFuaW1hdGlvbigpfSB0byBtaXggdGhlIHNrZWxldG9ucyBiYWNrIHRvIHRoZSBzZXR1cCBwb3NlLFxuXHQgKiByYXRoZXIgdGhhbiBsZWF2aW5nIHRoZW0gaW4gdGhlaXIgY3VycmVudCBwb3NlLiAqL1xuXHRjbGVhclRyYWNrICh0cmFja0luZGV4OiBudW1iZXIpIHtcblx0XHRpZiAodHJhY2tJbmRleCA+PSB0aGlzLnRyYWNrcy5sZW5ndGgpIHJldHVybjtcblx0XHRsZXQgY3VycmVudCA9IHRoaXMudHJhY2tzW3RyYWNrSW5kZXhdO1xuXHRcdGlmICghY3VycmVudCkgcmV0dXJuO1xuXG5cdFx0dGhpcy5xdWV1ZS5lbmQoY3VycmVudCk7XG5cblx0XHR0aGlzLmNsZWFyTmV4dChjdXJyZW50KTtcblxuXHRcdGxldCBlbnRyeSA9IGN1cnJlbnQ7XG5cdFx0d2hpbGUgKHRydWUpIHtcblx0XHRcdGxldCBmcm9tID0gZW50cnkubWl4aW5nRnJvbTtcblx0XHRcdGlmICghZnJvbSkgYnJlYWs7XG5cdFx0XHR0aGlzLnF1ZXVlLmVuZChmcm9tKTtcblx0XHRcdGVudHJ5Lm1peGluZ0Zyb20gPSBudWxsO1xuXHRcdFx0ZW50cnkubWl4aW5nVG8gPSBudWxsO1xuXHRcdFx0ZW50cnkgPSBmcm9tO1xuXHRcdH1cblxuXHRcdHRoaXMudHJhY2tzW2N1cnJlbnQudHJhY2tJbmRleF0gPSBudWxsO1xuXG5cdFx0dGhpcy5xdWV1ZS5kcmFpbigpO1xuXHR9XG5cblx0c2V0Q3VycmVudCAoaW5kZXg6IG51bWJlciwgY3VycmVudDogVHJhY2tFbnRyeSwgaW50ZXJydXB0OiBib29sZWFuKSB7XG5cdFx0bGV0IGZyb20gPSB0aGlzLmV4cGFuZFRvSW5kZXgoaW5kZXgpO1xuXHRcdHRoaXMudHJhY2tzW2luZGV4XSA9IGN1cnJlbnQ7XG5cdFx0Y3VycmVudC5wcmV2aW91cyA9IG51bGw7XG5cblx0XHRpZiAoZnJvbSkge1xuXHRcdFx0aWYgKGludGVycnVwdCkgdGhpcy5xdWV1ZS5pbnRlcnJ1cHQoZnJvbSk7XG5cdFx0XHRjdXJyZW50Lm1peGluZ0Zyb20gPSBmcm9tO1xuXHRcdFx0ZnJvbS5taXhpbmdUbyA9IGN1cnJlbnQ7XG5cdFx0XHRjdXJyZW50Lm1peFRpbWUgPSAwO1xuXG5cdFx0XHQvLyBTdG9yZSB0aGUgaW50ZXJydXB0ZWQgbWl4IHBlcmNlbnRhZ2UuXG5cdFx0XHRpZiAoZnJvbS5taXhpbmdGcm9tICYmIGZyb20ubWl4RHVyYXRpb24gPiAwKVxuXHRcdFx0XHRjdXJyZW50LmludGVycnVwdEFscGhhICo9IE1hdGgubWluKDEsIGZyb20ubWl4VGltZSAvIGZyb20ubWl4RHVyYXRpb24pO1xuXG5cdFx0XHRmcm9tLnRpbWVsaW5lc1JvdGF0aW9uLmxlbmd0aCA9IDA7IC8vIFJlc2V0IHJvdGF0aW9uIGZvciBtaXhpbmcgb3V0LCBpbiBjYXNlIGVudHJ5IHdhcyBtaXhlZCBpbi5cblx0XHR9XG5cblx0XHR0aGlzLnF1ZXVlLnN0YXJ0KGN1cnJlbnQpO1xuXHR9XG5cblx0LyoqIFNldHMgYW4gYW5pbWF0aW9uIGJ5IG5hbWUuXG5cdCAgKlxuXHQgICogU2VlIHtAbGluayAjc2V0QW5pbWF0aW9uV2l0aCgpfS4gKi9cblx0c2V0QW5pbWF0aW9uICh0cmFja0luZGV4OiBudW1iZXIsIGFuaW1hdGlvbk5hbWU6IHN0cmluZywgbG9vcDogYm9vbGVhbiA9IGZhbHNlKSB7XG5cdFx0bGV0IGFuaW1hdGlvbiA9IHRoaXMuZGF0YS5za2VsZXRvbkRhdGEuZmluZEFuaW1hdGlvbihhbmltYXRpb25OYW1lKTtcblx0XHRpZiAoIWFuaW1hdGlvbikgdGhyb3cgbmV3IEVycm9yKFwiQW5pbWF0aW9uIG5vdCBmb3VuZDogXCIgKyBhbmltYXRpb25OYW1lKTtcblx0XHRyZXR1cm4gdGhpcy5zZXRBbmltYXRpb25XaXRoKHRyYWNrSW5kZXgsIGFuaW1hdGlvbiwgbG9vcCk7XG5cdH1cblxuXHQvKiogU2V0cyB0aGUgY3VycmVudCBhbmltYXRpb24gZm9yIGEgdHJhY2ssIGRpc2NhcmRpbmcgYW55IHF1ZXVlZCBhbmltYXRpb25zLiBJZiB0aGUgZm9ybWVybHkgY3VycmVudCB0cmFjayBlbnRyeSB3YXMgbmV2ZXJcblx0ICogYXBwbGllZCB0byBhIHNrZWxldG9uLCBpdCBpcyByZXBsYWNlZCAobm90IG1peGVkIGZyb20pLlxuXHQgKiBAcGFyYW0gbG9vcCBJZiB0cnVlLCB0aGUgYW5pbWF0aW9uIHdpbGwgcmVwZWF0LiBJZiBmYWxzZSBpdCB3aWxsIG5vdCwgaW5zdGVhZCBpdHMgbGFzdCBmcmFtZSBpcyBhcHBsaWVkIGlmIHBsYXllZCBiZXlvbmQgaXRzXG5cdCAqICAgICAgICAgICBkdXJhdGlvbi4gSW4gZWl0aGVyIGNhc2Uge0BsaW5rIFRyYWNrRW50cnkjdHJhY2tFbmR9IGRldGVybWluZXMgd2hlbiB0aGUgdHJhY2sgaXMgY2xlYXJlZC5cblx0ICogQHJldHVybnMgQSB0cmFjayBlbnRyeSB0byBhbGxvdyBmdXJ0aGVyIGN1c3RvbWl6YXRpb24gb2YgYW5pbWF0aW9uIHBsYXliYWNrLiBSZWZlcmVuY2VzIHRvIHRoZSB0cmFjayBlbnRyeSBtdXN0IG5vdCBiZSBrZXB0XG5cdCAqICAgICAgICAgYWZ0ZXIgdGhlIHtAbGluayBBbmltYXRpb25TdGF0ZUxpc3RlbmVyI2Rpc3Bvc2UoKX0gZXZlbnQgb2NjdXJzLiAqL1xuXHRzZXRBbmltYXRpb25XaXRoICh0cmFja0luZGV4OiBudW1iZXIsIGFuaW1hdGlvbjogQW5pbWF0aW9uLCBsb29wOiBib29sZWFuID0gZmFsc2UpIHtcblx0XHRpZiAoIWFuaW1hdGlvbikgdGhyb3cgbmV3IEVycm9yKFwiYW5pbWF0aW9uIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHRsZXQgaW50ZXJydXB0ID0gdHJ1ZTtcblx0XHRsZXQgY3VycmVudCA9IHRoaXMuZXhwYW5kVG9JbmRleCh0cmFja0luZGV4KTtcblx0XHRpZiAoY3VycmVudCkge1xuXHRcdFx0aWYgKGN1cnJlbnQubmV4dFRyYWNrTGFzdCA9PSAtMSkge1xuXHRcdFx0XHQvLyBEb24ndCBtaXggZnJvbSBhbiBlbnRyeSB0aGF0IHdhcyBuZXZlciBhcHBsaWVkLlxuXHRcdFx0XHR0aGlzLnRyYWNrc1t0cmFja0luZGV4XSA9IGN1cnJlbnQubWl4aW5nRnJvbTtcblx0XHRcdFx0dGhpcy5xdWV1ZS5pbnRlcnJ1cHQoY3VycmVudCk7XG5cdFx0XHRcdHRoaXMucXVldWUuZW5kKGN1cnJlbnQpO1xuXHRcdFx0XHR0aGlzLmNsZWFyTmV4dChjdXJyZW50KTtcblx0XHRcdFx0Y3VycmVudCA9IGN1cnJlbnQubWl4aW5nRnJvbTtcblx0XHRcdFx0aW50ZXJydXB0ID0gZmFsc2U7XG5cdFx0XHR9IGVsc2Vcblx0XHRcdFx0dGhpcy5jbGVhck5leHQoY3VycmVudCk7XG5cdFx0fVxuXHRcdGxldCBlbnRyeSA9IHRoaXMudHJhY2tFbnRyeSh0cmFja0luZGV4LCBhbmltYXRpb24sIGxvb3AsIGN1cnJlbnQpO1xuXHRcdHRoaXMuc2V0Q3VycmVudCh0cmFja0luZGV4LCBlbnRyeSwgaW50ZXJydXB0KTtcblx0XHR0aGlzLnF1ZXVlLmRyYWluKCk7XG5cdFx0cmV0dXJuIGVudHJ5O1xuXHR9XG5cblx0LyoqIFF1ZXVlcyBhbiBhbmltYXRpb24gYnkgbmFtZS5cblx0ICpcblx0ICogU2VlIHtAbGluayAjYWRkQW5pbWF0aW9uV2l0aCgpfS4gKi9cblx0YWRkQW5pbWF0aW9uICh0cmFja0luZGV4OiBudW1iZXIsIGFuaW1hdGlvbk5hbWU6IHN0cmluZywgbG9vcDogYm9vbGVhbiA9IGZhbHNlLCBkZWxheTogbnVtYmVyID0gMCkge1xuXHRcdGxldCBhbmltYXRpb24gPSB0aGlzLmRhdGEuc2tlbGV0b25EYXRhLmZpbmRBbmltYXRpb24oYW5pbWF0aW9uTmFtZSk7XG5cdFx0aWYgKCFhbmltYXRpb24pIHRocm93IG5ldyBFcnJvcihcIkFuaW1hdGlvbiBub3QgZm91bmQ6IFwiICsgYW5pbWF0aW9uTmFtZSk7XG5cdFx0cmV0dXJuIHRoaXMuYWRkQW5pbWF0aW9uV2l0aCh0cmFja0luZGV4LCBhbmltYXRpb24sIGxvb3AsIGRlbGF5KTtcblx0fVxuXG5cdC8qKiBBZGRzIGFuIGFuaW1hdGlvbiB0byBiZSBwbGF5ZWQgYWZ0ZXIgdGhlIGN1cnJlbnQgb3IgbGFzdCBxdWV1ZWQgYW5pbWF0aW9uIGZvciBhIHRyYWNrLiBJZiB0aGUgdHJhY2sgaXMgZW1wdHksIGl0IGlzXG5cdCAqIGVxdWl2YWxlbnQgdG8gY2FsbGluZyB7QGxpbmsgI3NldEFuaW1hdGlvbldpdGgoKX0uXG5cdCAqIEBwYXJhbSBkZWxheSBJZiA+IDAsIHNldHMge0BsaW5rIFRyYWNrRW50cnkjZGVsYXl9LiBJZiA8PSAwLCB0aGUgZGVsYXkgc2V0IGlzIHRoZSBkdXJhdGlvbiBvZiB0aGUgcHJldmlvdXMgdHJhY2sgZW50cnlcblx0ICogICAgICAgICAgIG1pbnVzIGFueSBtaXggZHVyYXRpb24gKGZyb20gdGhlIHtAbGluayBBbmltYXRpb25TdGF0ZURhdGF9KSBwbHVzIHRoZSBzcGVjaWZpZWQgYGRlbGF5YCAoaWUgdGhlIG1peFxuXHQgKiAgICAgICAgICAgZW5kcyBhdCAoYGRlbGF5YCA9IDApIG9yIGJlZm9yZSAoYGRlbGF5YCA8IDApIHRoZSBwcmV2aW91cyB0cmFjayBlbnRyeSBkdXJhdGlvbikuIElmIHRoZVxuXHQgKiAgICAgICAgICAgcHJldmlvdXMgZW50cnkgaXMgbG9vcGluZywgaXRzIG5leHQgbG9vcCBjb21wbGV0aW9uIGlzIHVzZWQgaW5zdGVhZCBvZiBpdHMgZHVyYXRpb24uXG5cdCAqIEByZXR1cm5zIEEgdHJhY2sgZW50cnkgdG8gYWxsb3cgZnVydGhlciBjdXN0b21pemF0aW9uIG9mIGFuaW1hdGlvbiBwbGF5YmFjay4gUmVmZXJlbmNlcyB0byB0aGUgdHJhY2sgZW50cnkgbXVzdCBub3QgYmUga2VwdFxuXHQgKiAgICAgICAgIGFmdGVyIHRoZSB7QGxpbmsgQW5pbWF0aW9uU3RhdGVMaXN0ZW5lciNkaXNwb3NlKCl9IGV2ZW50IG9jY3Vycy4gKi9cblx0YWRkQW5pbWF0aW9uV2l0aCAodHJhY2tJbmRleDogbnVtYmVyLCBhbmltYXRpb246IEFuaW1hdGlvbiwgbG9vcDogYm9vbGVhbiA9IGZhbHNlLCBkZWxheTogbnVtYmVyID0gMCkge1xuXHRcdGlmICghYW5pbWF0aW9uKSB0aHJvdyBuZXcgRXJyb3IoXCJhbmltYXRpb24gY2Fubm90IGJlIG51bGwuXCIpO1xuXG5cdFx0bGV0IGxhc3QgPSB0aGlzLmV4cGFuZFRvSW5kZXgodHJhY2tJbmRleCk7XG5cdFx0aWYgKGxhc3QpIHtcblx0XHRcdHdoaWxlIChsYXN0Lm5leHQpXG5cdFx0XHRcdGxhc3QgPSBsYXN0Lm5leHQ7XG5cdFx0fVxuXG5cdFx0bGV0IGVudHJ5ID0gdGhpcy50cmFja0VudHJ5KHRyYWNrSW5kZXgsIGFuaW1hdGlvbiwgbG9vcCwgbGFzdCk7XG5cblx0XHRpZiAoIWxhc3QpIHtcblx0XHRcdHRoaXMuc2V0Q3VycmVudCh0cmFja0luZGV4LCBlbnRyeSwgdHJ1ZSk7XG5cdFx0XHR0aGlzLnF1ZXVlLmRyYWluKCk7XG5cdFx0XHRpZiAoZGVsYXkgPCAwKSBkZWxheSA9IDA7XG5cdFx0fSBlbHNlIHtcblx0XHRcdGxhc3QubmV4dCA9IGVudHJ5O1xuXHRcdFx0ZW50cnkucHJldmlvdXMgPSBsYXN0O1xuXHRcdFx0aWYgKGRlbGF5IDw9IDApIGRlbGF5ID0gTWF0aC5tYXgoZGVsYXkgKyBsYXN0LmdldFRyYWNrQ29tcGxldGUoKSAtIGVudHJ5Lm1peER1cmF0aW9uLCAwKTtcblx0XHR9XG5cblx0XHRlbnRyeS5kZWxheSA9IGRlbGF5O1xuXHRcdHJldHVybiBlbnRyeTtcblx0fVxuXG5cdC8qKiBTZXRzIGFuIGVtcHR5IGFuaW1hdGlvbiBmb3IgYSB0cmFjaywgZGlzY2FyZGluZyBhbnkgcXVldWVkIGFuaW1hdGlvbnMsIGFuZCBzZXRzIHRoZSB0cmFjayBlbnRyeSdzXG5cdCAqIHtAbGluayBUcmFja0VudHJ5I21peGR1cmF0aW9ufS4gQW4gZW1wdHkgYW5pbWF0aW9uIGhhcyBubyB0aW1lbGluZXMgYW5kIHNlcnZlcyBhcyBhIHBsYWNlaG9sZGVyIGZvciBtaXhpbmcgaW4gb3Igb3V0LlxuXHQgKlxuXHQgKiBNaXhpbmcgb3V0IGlzIGRvbmUgYnkgc2V0dGluZyBhbiBlbXB0eSBhbmltYXRpb24gd2l0aCBhIG1peCBkdXJhdGlvbiB1c2luZyBlaXRoZXIge0BsaW5rICNzZXRFbXB0eUFuaW1hdGlvbigpfSxcblx0ICoge0BsaW5rICNzZXRFbXB0eUFuaW1hdGlvbnMoKX0sIG9yIHtAbGluayAjYWRkRW1wdHlBbmltYXRpb24oKX0uIE1peGluZyB0byBhbiBlbXB0eSBhbmltYXRpb24gY2F1c2VzXG5cdCAqIHRoZSBwcmV2aW91cyBhbmltYXRpb24gdG8gYmUgYXBwbGllZCBsZXNzIGFuZCBsZXNzIG92ZXIgdGhlIG1peCBkdXJhdGlvbi4gUHJvcGVydGllcyBrZXllZCBpbiB0aGUgcHJldmlvdXMgYW5pbWF0aW9uXG5cdCAqIHRyYW5zaXRpb24gdG8gdGhlIHZhbHVlIGZyb20gbG93ZXIgdHJhY2tzIG9yIHRvIHRoZSBzZXR1cCBwb3NlIHZhbHVlIGlmIG5vIGxvd2VyIHRyYWNrcyBrZXkgdGhlIHByb3BlcnR5LiBBIG1peCBkdXJhdGlvbiBvZlxuXHQgKiAwIHN0aWxsIG1peGVzIG91dCBvdmVyIG9uZSBmcmFtZS5cblx0ICpcblx0ICogTWl4aW5nIGluIGlzIGRvbmUgYnkgZmlyc3Qgc2V0dGluZyBhbiBlbXB0eSBhbmltYXRpb24sIHRoZW4gYWRkaW5nIGFuIGFuaW1hdGlvbiB1c2luZ1xuXHQgKiB7QGxpbmsgI2FkZEFuaW1hdGlvbigpfSBhbmQgb24gdGhlIHJldHVybmVkIHRyYWNrIGVudHJ5LCBzZXQgdGhlXG5cdCAqIHtAbGluayBUcmFja0VudHJ5I3NldE1peER1cmF0aW9uKCl9LiBNaXhpbmcgZnJvbSBhbiBlbXB0eSBhbmltYXRpb24gY2F1c2VzIHRoZSBuZXcgYW5pbWF0aW9uIHRvIGJlIGFwcGxpZWQgbW9yZSBhbmRcblx0ICogbW9yZSBvdmVyIHRoZSBtaXggZHVyYXRpb24uIFByb3BlcnRpZXMga2V5ZWQgaW4gdGhlIG5ldyBhbmltYXRpb24gdHJhbnNpdGlvbiBmcm9tIHRoZSB2YWx1ZSBmcm9tIGxvd2VyIHRyYWNrcyBvciBmcm9tIHRoZVxuXHQgKiBzZXR1cCBwb3NlIHZhbHVlIGlmIG5vIGxvd2VyIHRyYWNrcyBrZXkgdGhlIHByb3BlcnR5IHRvIHRoZSB2YWx1ZSBrZXllZCBpbiB0aGUgbmV3IGFuaW1hdGlvbi4gKi9cblx0c2V0RW1wdHlBbmltYXRpb24gKHRyYWNrSW5kZXg6IG51bWJlciwgbWl4RHVyYXRpb246IG51bWJlciA9IDApIHtcblx0XHRsZXQgZW50cnkgPSB0aGlzLnNldEFuaW1hdGlvbldpdGgodHJhY2tJbmRleCwgQW5pbWF0aW9uU3RhdGUuZW1wdHlBbmltYXRpb24oKSwgZmFsc2UpO1xuXHRcdGVudHJ5Lm1peER1cmF0aW9uID0gbWl4RHVyYXRpb247XG5cdFx0ZW50cnkudHJhY2tFbmQgPSBtaXhEdXJhdGlvbjtcblx0XHRyZXR1cm4gZW50cnk7XG5cdH1cblxuXHQvKiogQWRkcyBhbiBlbXB0eSBhbmltYXRpb24gdG8gYmUgcGxheWVkIGFmdGVyIHRoZSBjdXJyZW50IG9yIGxhc3QgcXVldWVkIGFuaW1hdGlvbiBmb3IgYSB0cmFjaywgYW5kIHNldHMgdGhlIHRyYWNrIGVudHJ5J3Ncblx0ICoge0BsaW5rIFRyYWNrRW50cnkjbWl4RHVyYXRpb259LiBJZiB0aGUgdHJhY2sgaXMgZW1wdHksIGl0IGlzIGVxdWl2YWxlbnQgdG8gY2FsbGluZ1xuXHQgKiB7QGxpbmsgI3NldEVtcHR5QW5pbWF0aW9uKCl9LlxuXHQgKlxuXHQgKiBTZWUge0BsaW5rICNzZXRFbXB0eUFuaW1hdGlvbigpfS5cblx0ICogQHBhcmFtIGRlbGF5IElmID4gMCwgc2V0cyB7QGxpbmsgVHJhY2tFbnRyeSNkZWxheX0uIElmIDw9IDAsIHRoZSBkZWxheSBzZXQgaXMgdGhlIGR1cmF0aW9uIG9mIHRoZSBwcmV2aW91cyB0cmFjayBlbnRyeVxuXHQgKiAgICAgICAgICAgbWludXMgYW55IG1peCBkdXJhdGlvbiBwbHVzIHRoZSBzcGVjaWZpZWQgYGRlbGF5YCAoaWUgdGhlIG1peCBlbmRzIGF0IChgZGVsYXlgID0gMCkgb3Jcblx0ICogICAgICAgICAgIGJlZm9yZSAoYGRlbGF5YCA8IDApIHRoZSBwcmV2aW91cyB0cmFjayBlbnRyeSBkdXJhdGlvbikuIElmIHRoZSBwcmV2aW91cyBlbnRyeSBpcyBsb29waW5nLCBpdHMgbmV4dFxuXHQgKiAgICAgICAgICAgbG9vcCBjb21wbGV0aW9uIGlzIHVzZWQgaW5zdGVhZCBvZiBpdHMgZHVyYXRpb24uXG5cdCAqIEByZXR1cm4gQSB0cmFjayBlbnRyeSB0byBhbGxvdyBmdXJ0aGVyIGN1c3RvbWl6YXRpb24gb2YgYW5pbWF0aW9uIHBsYXliYWNrLiBSZWZlcmVuY2VzIHRvIHRoZSB0cmFjayBlbnRyeSBtdXN0IG5vdCBiZSBrZXB0XG5cdCAqICAgICAgICAgYWZ0ZXIgdGhlIHtAbGluayBBbmltYXRpb25TdGF0ZUxpc3RlbmVyI2Rpc3Bvc2UoKX0gZXZlbnQgb2NjdXJzLiAqL1xuXHRhZGRFbXB0eUFuaW1hdGlvbiAodHJhY2tJbmRleDogbnVtYmVyLCBtaXhEdXJhdGlvbjogbnVtYmVyID0gMCwgZGVsYXk6IG51bWJlciA9IDApIHtcblx0XHRsZXQgZW50cnkgPSB0aGlzLmFkZEFuaW1hdGlvbldpdGgodHJhY2tJbmRleCwgQW5pbWF0aW9uU3RhdGUuZW1wdHlBbmltYXRpb24oKSwgZmFsc2UsIGRlbGF5KTtcblx0XHRpZiAoZGVsYXkgPD0gMCkgZW50cnkuZGVsYXkgPSBNYXRoLm1heChlbnRyeS5kZWxheSArIGVudHJ5Lm1peER1cmF0aW9uIC0gbWl4RHVyYXRpb24sIDApO1xuXHRcdGVudHJ5Lm1peER1cmF0aW9uID0gbWl4RHVyYXRpb247XG5cdFx0ZW50cnkudHJhY2tFbmQgPSBtaXhEdXJhdGlvbjtcblx0XHRyZXR1cm4gZW50cnk7XG5cdH1cblxuXHQvKiogU2V0cyBhbiBlbXB0eSBhbmltYXRpb24gZm9yIGV2ZXJ5IHRyYWNrLCBkaXNjYXJkaW5nIGFueSBxdWV1ZWQgYW5pbWF0aW9ucywgYW5kIG1peGVzIHRvIGl0IG92ZXIgdGhlIHNwZWNpZmllZCBtaXhcblx0ICAqIGR1cmF0aW9uLiAqL1xuXHRzZXRFbXB0eUFuaW1hdGlvbnMgKG1peER1cmF0aW9uOiBudW1iZXIgPSAwKSB7XG5cdFx0bGV0IG9sZERyYWluRGlzYWJsZWQgPSB0aGlzLnF1ZXVlLmRyYWluRGlzYWJsZWQ7XG5cdFx0dGhpcy5xdWV1ZS5kcmFpbkRpc2FibGVkID0gdHJ1ZTtcblx0XHRmb3IgKGxldCBpID0gMCwgbiA9IHRoaXMudHJhY2tzLmxlbmd0aDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGN1cnJlbnQgPSB0aGlzLnRyYWNrc1tpXTtcblx0XHRcdGlmIChjdXJyZW50KSB0aGlzLnNldEVtcHR5QW5pbWF0aW9uKGN1cnJlbnQudHJhY2tJbmRleCwgbWl4RHVyYXRpb24pO1xuXHRcdH1cblx0XHR0aGlzLnF1ZXVlLmRyYWluRGlzYWJsZWQgPSBvbGREcmFpbkRpc2FibGVkO1xuXHRcdHRoaXMucXVldWUuZHJhaW4oKTtcblx0fVxuXG5cdGV4cGFuZFRvSW5kZXggKGluZGV4OiBudW1iZXIpIHtcblx0XHRpZiAoaW5kZXggPCB0aGlzLnRyYWNrcy5sZW5ndGgpIHJldHVybiB0aGlzLnRyYWNrc1tpbmRleF07XG5cdFx0VXRpbHMuZW5zdXJlQXJyYXlDYXBhY2l0eSh0aGlzLnRyYWNrcywgaW5kZXggKyAxLCBudWxsKTtcblx0XHR0aGlzLnRyYWNrcy5sZW5ndGggPSBpbmRleCArIDE7XG5cdFx0cmV0dXJuIG51bGw7XG5cdH1cblxuXHQvKiogQHBhcmFtIGxhc3QgTWF5IGJlIG51bGwuICovXG5cdHRyYWNrRW50cnkgKHRyYWNrSW5kZXg6IG51bWJlciwgYW5pbWF0aW9uOiBBbmltYXRpb24sIGxvb3A6IGJvb2xlYW4sIGxhc3Q6IFRyYWNrRW50cnkgfCBudWxsKSB7XG5cdFx0bGV0IGVudHJ5ID0gdGhpcy50cmFja0VudHJ5UG9vbC5vYnRhaW4oKTtcblx0XHRlbnRyeS5yZXNldCgpO1xuXHRcdGVudHJ5LnRyYWNrSW5kZXggPSB0cmFja0luZGV4O1xuXHRcdGVudHJ5LmFuaW1hdGlvbiA9IGFuaW1hdGlvbjtcblx0XHRlbnRyeS5sb29wID0gbG9vcDtcblx0XHRlbnRyeS5ob2xkUHJldmlvdXMgPSBmYWxzZTtcblxuXHRcdGVudHJ5LnJldmVyc2UgPSBmYWxzZTtcblx0XHRlbnRyeS5zaG9ydGVzdFJvdGF0aW9uID0gZmFsc2U7XG5cblx0XHRlbnRyeS5ldmVudFRocmVzaG9sZCA9IDA7XG5cdFx0ZW50cnkuYWxwaGFBdHRhY2htZW50VGhyZXNob2xkID0gMDtcblx0XHRlbnRyeS5taXhBdHRhY2htZW50VGhyZXNob2xkID0gMDtcblx0XHRlbnRyeS5taXhEcmF3T3JkZXJUaHJlc2hvbGQgPSAwO1xuXG5cdFx0ZW50cnkuYW5pbWF0aW9uU3RhcnQgPSAwO1xuXHRcdGVudHJ5LmFuaW1hdGlvbkVuZCA9IGFuaW1hdGlvbi5kdXJhdGlvbjtcblx0XHRlbnRyeS5hbmltYXRpb25MYXN0ID0gLTE7XG5cdFx0ZW50cnkubmV4dEFuaW1hdGlvbkxhc3QgPSAtMTtcblxuXHRcdGVudHJ5LmRlbGF5ID0gMDtcblx0XHRlbnRyeS50cmFja1RpbWUgPSAwO1xuXHRcdGVudHJ5LnRyYWNrTGFzdCA9IC0xO1xuXHRcdGVudHJ5Lm5leHRUcmFja0xhc3QgPSAtMTtcblx0XHRlbnRyeS50cmFja0VuZCA9IE51bWJlci5NQVhfVkFMVUU7XG5cdFx0ZW50cnkudGltZVNjYWxlID0gMTtcblxuXHRcdGVudHJ5LmFscGhhID0gMTtcblx0XHRlbnRyeS5taXhUaW1lID0gMDtcblx0XHRlbnRyeS5taXhEdXJhdGlvbiA9ICFsYXN0ID8gMCA6IHRoaXMuZGF0YS5nZXRNaXgobGFzdC5hbmltYXRpb24hLCBhbmltYXRpb24pO1xuXHRcdGVudHJ5LmludGVycnVwdEFscGhhID0gMTtcblx0XHRlbnRyeS50b3RhbEFscGhhID0gMDtcblx0XHRlbnRyeS5taXhCbGVuZCA9IE1peEJsZW5kLnJlcGxhY2U7XG5cdFx0cmV0dXJuIGVudHJ5O1xuXHR9XG5cblx0LyoqIFJlbW92ZXMgdGhlIHtAbGluayBUcmFja0VudHJ5I2dldE5leHQoKSBuZXh0IGVudHJ5fSBhbmQgYWxsIGVudHJpZXMgYWZ0ZXIgaXQgZm9yIHRoZSBzcGVjaWZpZWQgZW50cnkuICovXG5cdGNsZWFyTmV4dCAoZW50cnk6IFRyYWNrRW50cnkpIHtcblx0XHRsZXQgbmV4dCA9IGVudHJ5Lm5leHQ7XG5cdFx0d2hpbGUgKG5leHQpIHtcblx0XHRcdHRoaXMucXVldWUuZGlzcG9zZShuZXh0KTtcblx0XHRcdG5leHQgPSBuZXh0Lm5leHQ7XG5cdFx0fVxuXHRcdGVudHJ5Lm5leHQgPSBudWxsO1xuXHR9XG5cblx0X2FuaW1hdGlvbnNDaGFuZ2VkICgpIHtcblx0XHR0aGlzLmFuaW1hdGlvbnNDaGFuZ2VkID0gZmFsc2U7XG5cblx0XHR0aGlzLnByb3BlcnR5SURzLmNsZWFyKCk7XG5cdFx0bGV0IHRyYWNrcyA9IHRoaXMudHJhY2tzO1xuXHRcdGZvciAobGV0IGkgPSAwLCBuID0gdHJhY2tzLmxlbmd0aDsgaSA8IG47IGkrKykge1xuXHRcdFx0bGV0IGVudHJ5ID0gdHJhY2tzW2ldO1xuXHRcdFx0aWYgKCFlbnRyeSkgY29udGludWU7XG5cdFx0XHR3aGlsZSAoZW50cnkubWl4aW5nRnJvbSlcblx0XHRcdFx0ZW50cnkgPSBlbnRyeS5taXhpbmdGcm9tO1xuXHRcdFx0ZG8ge1xuXHRcdFx0XHRpZiAoIWVudHJ5Lm1peGluZ1RvIHx8IGVudHJ5Lm1peEJsZW5kICE9IE1peEJsZW5kLmFkZCkgdGhpcy5jb21wdXRlSG9sZChlbnRyeSk7XG5cdFx0XHRcdGVudHJ5ID0gZW50cnkubWl4aW5nVG87XG5cdFx0XHR9IHdoaWxlIChlbnRyeSk7XG5cdFx0fVxuXHR9XG5cblx0Y29tcHV0ZUhvbGQgKGVudHJ5OiBUcmFja0VudHJ5KSB7XG5cdFx0bGV0IHRvID0gZW50cnkubWl4aW5nVG87XG5cdFx0bGV0IHRpbWVsaW5lcyA9IGVudHJ5LmFuaW1hdGlvbiEudGltZWxpbmVzO1xuXHRcdGxldCB0aW1lbGluZXNDb3VudCA9IGVudHJ5LmFuaW1hdGlvbiEudGltZWxpbmVzLmxlbmd0aDtcblx0XHRsZXQgdGltZWxpbmVNb2RlID0gZW50cnkudGltZWxpbmVNb2RlO1xuXHRcdHRpbWVsaW5lTW9kZS5sZW5ndGggPSB0aW1lbGluZXNDb3VudDtcblx0XHRsZXQgdGltZWxpbmVIb2xkTWl4ID0gZW50cnkudGltZWxpbmVIb2xkTWl4O1xuXHRcdHRpbWVsaW5lSG9sZE1peC5sZW5ndGggPSAwO1xuXHRcdGxldCBwcm9wZXJ0eUlEcyA9IHRoaXMucHJvcGVydHlJRHM7XG5cblx0XHRpZiAodG8gJiYgdG8uaG9sZFByZXZpb3VzKSB7XG5cdFx0XHRmb3IgKGxldCBpID0gMDsgaSA8IHRpbWVsaW5lc0NvdW50OyBpKyspXG5cdFx0XHRcdHRpbWVsaW5lTW9kZVtpXSA9IHByb3BlcnR5SURzLmFkZEFsbCh0aW1lbGluZXNbaV0uZ2V0UHJvcGVydHlJZHMoKSkgPyBIT0xEX0ZJUlNUIDogSE9MRF9TVUJTRVFVRU5UO1xuXHRcdFx0cmV0dXJuO1xuXHRcdH1cblxuXHRcdG91dGVyOlxuXHRcdGZvciAobGV0IGkgPSAwOyBpIDwgdGltZWxpbmVzQ291bnQ7IGkrKykge1xuXHRcdFx0bGV0IHRpbWVsaW5lID0gdGltZWxpbmVzW2ldO1xuXHRcdFx0bGV0IGlkcyA9IHRpbWVsaW5lLmdldFByb3BlcnR5SWRzKCk7XG5cdFx0XHRpZiAoIXByb3BlcnR5SURzLmFkZEFsbChpZHMpKVxuXHRcdFx0XHR0aW1lbGluZU1vZGVbaV0gPSBTVUJTRVFVRU5UO1xuXHRcdFx0ZWxzZSBpZiAoIXRvIHx8IHRpbWVsaW5lIGluc3RhbmNlb2YgQXR0YWNobWVudFRpbWVsaW5lIHx8IHRpbWVsaW5lIGluc3RhbmNlb2YgRHJhd09yZGVyVGltZWxpbmVcblx0XHRcdFx0fHwgdGltZWxpbmUgaW5zdGFuY2VvZiBFdmVudFRpbWVsaW5lIHx8ICF0by5hbmltYXRpb24hLmhhc1RpbWVsaW5lKGlkcykpIHtcblx0XHRcdFx0dGltZWxpbmVNb2RlW2ldID0gRklSU1Q7XG5cdFx0XHR9IGVsc2Uge1xuXHRcdFx0XHRmb3IgKGxldCBuZXh0ID0gdG8ubWl4aW5nVG87IG5leHQ7IG5leHQgPSBuZXh0IS5taXhpbmdUbykge1xuXHRcdFx0XHRcdGlmIChuZXh0LmFuaW1hdGlvbiEuaGFzVGltZWxpbmUoaWRzKSkgY29udGludWU7XG5cdFx0XHRcdFx0aWYgKGVudHJ5Lm1peER1cmF0aW9uID4gMCkge1xuXHRcdFx0XHRcdFx0dGltZWxpbmVNb2RlW2ldID0gSE9MRF9NSVg7XG5cdFx0XHRcdFx0XHR0aW1lbGluZUhvbGRNaXhbaV0gPSBuZXh0O1xuXHRcdFx0XHRcdFx0Y29udGludWUgb3V0ZXI7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHR9XG5cdFx0XHRcdHRpbWVsaW5lTW9kZVtpXSA9IEhPTERfRklSU1Q7XG5cdFx0XHR9XG5cdFx0fVxuXHR9XG5cblx0LyoqIFJldHVybnMgdGhlIHRyYWNrIGVudHJ5IGZvciB0aGUgYW5pbWF0aW9uIGN1cnJlbnRseSBwbGF5aW5nIG9uIHRoZSB0cmFjaywgb3IgbnVsbCBpZiBubyBhbmltYXRpb24gaXMgY3VycmVudGx5IHBsYXlpbmcuICovXG5cdGdldEN1cnJlbnQgKHRyYWNrSW5kZXg6IG51bWJlcikge1xuXHRcdGlmICh0cmFja0luZGV4ID49IHRoaXMudHJhY2tzLmxlbmd0aCkgcmV0dXJuIG51bGw7XG5cdFx0cmV0dXJuIHRoaXMudHJhY2tzW3RyYWNrSW5kZXhdO1xuXHR9XG5cblx0LyoqIEFkZHMgYSBsaXN0ZW5lciB0byByZWNlaXZlIGV2ZW50cyBmb3IgYWxsIHRyYWNrIGVudHJpZXMuICovXG5cdGFkZExpc3RlbmVyIChsaXN0ZW5lcjogQW5pbWF0aW9uU3RhdGVMaXN0ZW5lcikge1xuXHRcdGlmICghbGlzdGVuZXIpIHRocm93IG5ldyBFcnJvcihcImxpc3RlbmVyIGNhbm5vdCBiZSBudWxsLlwiKTtcblx0XHR0aGlzLmxpc3RlbmVycy5wdXNoKGxpc3RlbmVyKTtcblx0fVxuXG5cdC8qKiBSZW1vdmVzIHRoZSBsaXN0ZW5lciBhZGRlZCB3aXRoIHtAbGluayAjYWRkTGlzdGVuZXIoKX0uICovXG5cdHJlbW92ZUxpc3RlbmVyIChsaXN0ZW5lcjogQW5pbWF0aW9uU3RhdGVMaXN0ZW5lcikge1xuXHRcdGxldCBpbmRleCA9IHRoaXMubGlzdGVuZXJzLmluZGV4T2YobGlzdGVuZXIpO1xuXHRcdGlmIChpbmRleCA+PSAwKSB0aGlzLmxpc3RlbmVycy5zcGxpY2UoaW5kZXgsIDEpO1xuXHR9XG5cblx0LyoqIFJlbW92ZXMgYWxsIGxpc3RlbmVycyBhZGRlZCB3aXRoIHtAbGluayAjYWRkTGlzdGVuZXIoKX0uICovXG5cdGNsZWFyTGlzdGVuZXJzICgpIHtcblx0XHR0aGlzLmxpc3RlbmVycy5sZW5ndGggPSAwO1xuXHR9XG5cblx0LyoqIERpc2NhcmRzIGFsbCBsaXN0ZW5lciBub3RpZmljYXRpb25zIHRoYXQgaGF2ZSBub3QgeWV0IGJlZW4gZGVsaXZlcmVkLiBUaGlzIGNhbiBiZSB1c2VmdWwgdG8gY2FsbCBmcm9tIGFuXG5cdCAqIHtAbGluayBBbmltYXRpb25TdGF0ZUxpc3RlbmVyfSB3aGVuIGl0IGlzIGtub3duIHRoYXQgZnVydGhlciBub3RpZmljYXRpb25zIHRoYXQgbWF5IGhhdmUgYmVlbiBhbHJlYWR5IHF1ZXVlZCBmb3IgZGVsaXZlcnlcblx0ICogYXJlIG5vdCB3YW50ZWQgYmVjYXVzZSBuZXcgYW5pbWF0aW9ucyBhcmUgYmVpbmcgc2V0LiAqL1xuXHRjbGVhckxpc3RlbmVyTm90aWZpY2F0aW9ucyAoKSB7XG5cdFx0dGhpcy5xdWV1ZS5jbGVhcigpO1xuXHR9XG59XG5cbi8qKiBTdG9yZXMgc2V0dGluZ3MgYW5kIG90aGVyIHN0YXRlIGZvciB0aGUgcGxheWJhY2sgb2YgYW4gYW5pbWF0aW9uIG9uIGFuIHtAbGluayBBbmltYXRpb25TdGF0ZX0gdHJhY2suXG4gKlxuICogUmVmZXJlbmNlcyB0byBhIHRyYWNrIGVudHJ5IG11c3Qgbm90IGJlIGtlcHQgYWZ0ZXIgdGhlIHtAbGluayBBbmltYXRpb25TdGF0ZUxpc3RlbmVyI2Rpc3Bvc2UoKX0gZXZlbnQgb2NjdXJzLiAqL1xuZXhwb3J0IGNsYXNzIFRyYWNrRW50cnkge1xuXHQvKiogVGhlIGFuaW1hdGlvbiB0byBhcHBseSBmb3IgdGhpcyB0cmFjayBlbnRyeS4gKi9cblx0YW5pbWF0aW9uOiBBbmltYXRpb24gfCBudWxsID0gbnVsbDtcblxuXHRwcmV2aW91czogVHJhY2tFbnRyeSB8IG51bGwgPSBudWxsO1xuXG5cdC8qKiBUaGUgYW5pbWF0aW9uIHF1ZXVlZCB0byBzdGFydCBhZnRlciB0aGlzIGFuaW1hdGlvbiwgb3IgbnVsbC4gYG5leHRgIG1ha2VzIHVwIGEgbGlua2VkIGxpc3QuICovXG5cdG5leHQ6IFRyYWNrRW50cnkgfCBudWxsID0gbnVsbDtcblxuXHQvKiogVGhlIHRyYWNrIGVudHJ5IGZvciB0aGUgcHJldmlvdXMgYW5pbWF0aW9uIHdoZW4gbWl4aW5nIGZyb20gdGhlIHByZXZpb3VzIGFuaW1hdGlvbiB0byB0aGlzIGFuaW1hdGlvbiwgb3IgbnVsbCBpZiBub1xuXHQgKiBtaXhpbmcgaXMgY3VycmVudGx5IG9jY3VyaW5nLiBXaGVuIG1peGluZyBmcm9tIG11bHRpcGxlIGFuaW1hdGlvbnMsIGBtaXhpbmdGcm9tYCBtYWtlcyB1cCBhIGxpbmtlZCBsaXN0LiAqL1xuXHRtaXhpbmdGcm9tOiBUcmFja0VudHJ5IHwgbnVsbCA9IG51bGw7XG5cblx0LyoqIFRoZSB0cmFjayBlbnRyeSBmb3IgdGhlIG5leHQgYW5pbWF0aW9uIHdoZW4gbWl4aW5nIGZyb20gdGhpcyBhbmltYXRpb24gdG8gdGhlIG5leHQgYW5pbWF0aW9uLCBvciBudWxsIGlmIG5vIG1peGluZyBpc1xuXHQgKiBjdXJyZW50bHkgb2NjdXJpbmcuIFdoZW4gbWl4aW5nIHRvIG11bHRpcGxlIGFuaW1hdGlvbnMsIGBtaXhpbmdUb2AgbWFrZXMgdXAgYSBsaW5rZWQgbGlzdC4gKi9cblx0bWl4aW5nVG86IFRyYWNrRW50cnkgfCBudWxsID0gbnVsbDtcblxuXHQvKiogVGhlIGxpc3RlbmVyIGZvciBldmVudHMgZ2VuZXJhdGVkIGJ5IHRoaXMgdHJhY2sgZW50cnksIG9yIG51bGwuXG5cdCAqXG5cdCAqIEEgdHJhY2sgZW50cnkgcmV0dXJuZWQgZnJvbSB7QGxpbmsgQW5pbWF0aW9uU3RhdGUjc2V0QW5pbWF0aW9uKCl9IGlzIGFscmVhZHkgdGhlIGN1cnJlbnQgYW5pbWF0aW9uXG5cdCAqIGZvciB0aGUgdHJhY2ssIHNvIHRoZSB0cmFjayBlbnRyeSBsaXN0ZW5lciB7QGxpbmsgQW5pbWF0aW9uU3RhdGVMaXN0ZW5lciNzdGFydCgpfSB3aWxsIG5vdCBiZSBjYWxsZWQuICovXG5cdGxpc3RlbmVyOiBBbmltYXRpb25TdGF0ZUxpc3RlbmVyIHwgbnVsbCA9IG51bGw7XG5cblx0LyoqIFRoZSBpbmRleCBvZiB0aGUgdHJhY2sgd2hlcmUgdGhpcyB0cmFjayBlbnRyeSBpcyBlaXRoZXIgY3VycmVudCBvciBxdWV1ZWQuXG5cdCAqXG5cdCAqIFNlZSB7QGxpbmsgQW5pbWF0aW9uU3RhdGUjZ2V0Q3VycmVudCgpfS4gKi9cblx0dHJhY2tJbmRleDogbnVtYmVyID0gMDtcblxuXHQvKiogSWYgdHJ1ZSwgdGhlIGFuaW1hdGlvbiB3aWxsIHJlcGVhdC4gSWYgZmFsc2UgaXQgd2lsbCBub3QsIGluc3RlYWQgaXRzIGxhc3QgZnJhbWUgaXMgYXBwbGllZCBpZiBwbGF5ZWQgYmV5b25kIGl0c1xuXHQgKiBkdXJhdGlvbi4gKi9cblx0bG9vcDogYm9vbGVhbiA9IGZhbHNlO1xuXG5cdC8qKiBJZiB0cnVlLCB3aGVuIG1peGluZyBmcm9tIHRoZSBwcmV2aW91cyBhbmltYXRpb24gdG8gdGhpcyBhbmltYXRpb24sIHRoZSBwcmV2aW91cyBhbmltYXRpb24gaXMgYXBwbGllZCBhcyBub3JtYWwgaW5zdGVhZFxuXHQgKiBvZiBiZWluZyBtaXhlZCBvdXQuXG5cdCAqXG5cdCAqIFdoZW4gbWl4aW5nIGJldHdlZW4gYW5pbWF0aW9ucyB0aGF0IGtleSB0aGUgc2FtZSBwcm9wZXJ0eSwgaWYgYSBsb3dlciB0cmFjayBhbHNvIGtleXMgdGhhdCBwcm9wZXJ0eSB0aGVuIHRoZSB2YWx1ZSB3aWxsXG5cdCAqIGJyaWVmbHkgZGlwIHRvd2FyZCB0aGUgbG93ZXIgdHJhY2sgdmFsdWUgZHVyaW5nIHRoZSBtaXguIFRoaXMgaGFwcGVucyBiZWNhdXNlIHRoZSBmaXJzdCBhbmltYXRpb24gbWl4ZXMgZnJvbSAxMDAlIHRvIDAlXG5cdCAqIHdoaWxlIHRoZSBzZWNvbmQgYW5pbWF0aW9uIG1peGVzIGZyb20gMCUgdG8gMTAwJS4gU2V0dGluZyBgaG9sZFByZXZpb3VzYCB0byB0cnVlIGFwcGxpZXMgdGhlIGZpcnN0IGFuaW1hdGlvblxuXHQgKiBhdCAxMDAlIGR1cmluZyB0aGUgbWl4IHNvIHRoZSBsb3dlciB0cmFjayB2YWx1ZSBpcyBvdmVyd3JpdHRlbi4gU3VjaCBkaXBwaW5nIGRvZXMgbm90IG9jY3VyIG9uIHRoZSBsb3dlc3QgdHJhY2sgd2hpY2hcblx0ICoga2V5cyB0aGUgcHJvcGVydHksIG9ubHkgd2hlbiBhIGhpZ2hlciB0cmFjayBhbHNvIGtleXMgdGhlIHByb3BlcnR5LlxuXHQgKlxuXHQgKiBTbmFwcGluZyB3aWxsIG9jY3VyIGlmIGBob2xkUHJldmlvdXNgIGlzIHRydWUgYW5kIHRoaXMgYW5pbWF0aW9uIGRvZXMgbm90IGtleSBhbGwgdGhlIHNhbWUgcHJvcGVydGllcyBhcyB0aGVcblx0ICogcHJldmlvdXMgYW5pbWF0aW9uLiAqL1xuXHRob2xkUHJldmlvdXM6IGJvb2xlYW4gPSBmYWxzZTtcblxuXHRyZXZlcnNlOiBib29sZWFuID0gZmFsc2U7XG5cblx0c2hvcnRlc3RSb3RhdGlvbjogYm9vbGVhbiA9IGZhbHNlO1xuXG5cdC8qKiBXaGVuIHRoZSBtaXggcGVyY2VudGFnZSAoe0BsaW5rICNtaXhUaW1lfSAvIHtAbGluayAjbWl4RHVyYXRpb259KSBpcyBsZXNzIHRoYW4gdGhlXG5cdCAqIGBldmVudFRocmVzaG9sZGAsIGV2ZW50IHRpbWVsaW5lcyBhcmUgYXBwbGllZCB3aGlsZSB0aGlzIGFuaW1hdGlvbiBpcyBiZWluZyBtaXhlZCBvdXQuIERlZmF1bHRzIHRvIDAsIHNvIGV2ZW50XG5cdCAqIHRpbWVsaW5lcyBhcmUgbm90IGFwcGxpZWQgd2hpbGUgdGhpcyBhbmltYXRpb24gaXMgYmVpbmcgbWl4ZWQgb3V0LiAqL1xuXHRldmVudFRocmVzaG9sZDogbnVtYmVyID0gMDtcblxuXHQvKiogV2hlbiB0aGUgbWl4IHBlcmNlbnRhZ2UgKHtAbGluayAjbWl4dGltZX0gLyB7QGxpbmsgI21peER1cmF0aW9ufSkgaXMgbGVzcyB0aGFuIHRoZVxuXHQgKiBgYXR0YWNobWVudFRocmVzaG9sZGAsIGF0dGFjaG1lbnQgdGltZWxpbmVzIGFyZSBhcHBsaWVkIHdoaWxlIHRoaXMgYW5pbWF0aW9uIGlzIGJlaW5nIG1peGVkIG91dC4gRGVmYXVsdHMgdG9cblx0ICogMCwgc28gYXR0YWNobWVudCB0aW1lbGluZXMgYXJlIG5vdCBhcHBsaWVkIHdoaWxlIHRoaXMgYW5pbWF0aW9uIGlzIGJlaW5nIG1peGVkIG91dC4gKi9cblx0bWl4QXR0YWNobWVudFRocmVzaG9sZDogbnVtYmVyID0gMDtcblxuXHQvKiogV2hlbiB7QGxpbmsgI2dldEFscGhhKCl9IGlzIGdyZWF0ZXIgdGhhbiA8Y29kZT5hbHBoYUF0dGFjaG1lbnRUaHJlc2hvbGQ8L2NvZGU+LCBhdHRhY2htZW50IHRpbWVsaW5lcyBhcmUgYXBwbGllZC5cblx0ICogRGVmYXVsdHMgdG8gMCwgc28gYXR0YWNobWVudCB0aW1lbGluZXMgYXJlIGFsd2F5cyBhcHBsaWVkLiAqL1xuXHRhbHBoYUF0dGFjaG1lbnRUaHJlc2hvbGQ6IG51bWJlciA9IDA7XG5cblx0LyoqIFdoZW4gdGhlIG1peCBwZXJjZW50YWdlICh7QGxpbmsgI2dldE1peFRpbWUoKX0gLyB7QGxpbmsgI2dldE1peER1cmF0aW9uKCl9KSBpcyBsZXNzIHRoYW4gdGhlXG5cdCAqIDxjb2RlPm1peERyYXdPcmRlclRocmVzaG9sZDwvY29kZT4sIGRyYXcgb3JkZXIgdGltZWxpbmVzIGFyZSBhcHBsaWVkIHdoaWxlIHRoaXMgYW5pbWF0aW9uIGlzIGJlaW5nIG1peGVkIG91dC4gRGVmYXVsdHMgdG9cblx0ICogMCwgc28gZHJhdyBvcmRlciB0aW1lbGluZXMgYXJlIG5vdCBhcHBsaWVkIHdoaWxlIHRoaXMgYW5pbWF0aW9uIGlzIGJlaW5nIG1peGVkIG91dC4gKi9cblx0bWl4RHJhd09yZGVyVGhyZXNob2xkOiBudW1iZXIgPSAwO1xuXG5cdC8qKiBTZWNvbmRzIHdoZW4gdGhpcyBhbmltYXRpb24gc3RhcnRzLCBib3RoIGluaXRpYWxseSBhbmQgYWZ0ZXIgbG9vcGluZy4gRGVmYXVsdHMgdG8gMC5cblx0ICpcblx0ICogV2hlbiBjaGFuZ2luZyB0aGUgYGFuaW1hdGlvblN0YXJ0YCB0aW1lLCBpdCBvZnRlbiBtYWtlcyBzZW5zZSB0byBzZXQge0BsaW5rICNhbmltYXRpb25MYXN0fSB0byB0aGUgc2FtZVxuXHQgKiB2YWx1ZSB0byBwcmV2ZW50IHRpbWVsaW5lIGtleXMgYmVmb3JlIHRoZSBzdGFydCB0aW1lIGZyb20gdHJpZ2dlcmluZy4gKi9cblx0YW5pbWF0aW9uU3RhcnQ6IG51bWJlciA9IDA7XG5cblx0LyoqIFNlY29uZHMgZm9yIHRoZSBsYXN0IGZyYW1lIG9mIHRoaXMgYW5pbWF0aW9uLiBOb24tbG9vcGluZyBhbmltYXRpb25zIHdvbid0IHBsYXkgcGFzdCB0aGlzIHRpbWUuIExvb3BpbmcgYW5pbWF0aW9ucyB3aWxsXG5cdCAqIGxvb3AgYmFjayB0byB7QGxpbmsgI2FuaW1hdGlvblN0YXJ0fSBhdCB0aGlzIHRpbWUuIERlZmF1bHRzIHRvIHRoZSBhbmltYXRpb24ge0BsaW5rIEFuaW1hdGlvbiNkdXJhdGlvbn0uICovXG5cdGFuaW1hdGlvbkVuZDogbnVtYmVyID0gMDtcblxuXG5cdC8qKiBUaGUgdGltZSBpbiBzZWNvbmRzIHRoaXMgYW5pbWF0aW9uIHdhcyBsYXN0IGFwcGxpZWQuIFNvbWUgdGltZWxpbmVzIHVzZSB0aGlzIGZvciBvbmUtdGltZSB0cmlnZ2Vycy4gRWcsIHdoZW4gdGhpc1xuXHQgKiBhbmltYXRpb24gaXMgYXBwbGllZCwgZXZlbnQgdGltZWxpbmVzIHdpbGwgZmlyZSBhbGwgZXZlbnRzIGJldHdlZW4gdGhlIGBhbmltYXRpb25MYXN0YCB0aW1lIChleGNsdXNpdmUpIGFuZFxuXHQgKiBgYW5pbWF0aW9uVGltZWAgKGluY2x1c2l2ZSkuIERlZmF1bHRzIHRvIC0xIHRvIGVuc3VyZSB0cmlnZ2VycyBvbiBmcmFtZSAwIGhhcHBlbiB0aGUgZmlyc3QgdGltZSB0aGlzIGFuaW1hdGlvblxuXHQgKiBpcyBhcHBsaWVkLiAqL1xuXHRhbmltYXRpb25MYXN0OiBudW1iZXIgPSAwO1xuXG5cdG5leHRBbmltYXRpb25MYXN0OiBudW1iZXIgPSAwO1xuXG5cdC8qKiBTZWNvbmRzIHRvIHBvc3Rwb25lIHBsYXlpbmcgdGhlIGFuaW1hdGlvbi4gV2hlbiB0aGlzIHRyYWNrIGVudHJ5IGlzIHRoZSBjdXJyZW50IHRyYWNrIGVudHJ5LCBgZGVsYXlgXG5cdCAqIHBvc3Rwb25lcyBpbmNyZW1lbnRpbmcgdGhlIHtAbGluayAjdHJhY2tUaW1lfS4gV2hlbiB0aGlzIHRyYWNrIGVudHJ5IGlzIHF1ZXVlZCwgYGRlbGF5YCBpcyB0aGUgdGltZSBmcm9tXG5cdCAqIHRoZSBzdGFydCBvZiB0aGUgcHJldmlvdXMgYW5pbWF0aW9uIHRvIHdoZW4gdGhpcyB0cmFjayBlbnRyeSB3aWxsIGJlY29tZSB0aGUgY3VycmVudCB0cmFjayBlbnRyeSAoaWUgd2hlbiB0aGUgcHJldmlvdXNcblx0ICogdHJhY2sgZW50cnkge0BsaW5rIFRyYWNrRW50cnkjdHJhY2tUaW1lfSA+PSB0aGlzIHRyYWNrIGVudHJ5J3MgYGRlbGF5YCkuXG5cdCAqXG5cdCAqIHtAbGluayAjdGltZVNjYWxlfSBhZmZlY3RzIHRoZSBkZWxheS4gKi9cblx0ZGVsYXk6IG51bWJlciA9IDA7XG5cblx0LyoqIEN1cnJlbnQgdGltZSBpbiBzZWNvbmRzIHRoaXMgdHJhY2sgZW50cnkgaGFzIGJlZW4gdGhlIGN1cnJlbnQgdHJhY2sgZW50cnkuIFRoZSB0cmFjayB0aW1lIGRldGVybWluZXNcblx0ICoge0BsaW5rICNhbmltYXRpb25UaW1lfS4gVGhlIHRyYWNrIHRpbWUgY2FuIGJlIHNldCB0byBzdGFydCB0aGUgYW5pbWF0aW9uIGF0IGEgdGltZSBvdGhlciB0aGFuIDAsIHdpdGhvdXQgYWZmZWN0aW5nXG5cdCAqIGxvb3BpbmcuICovXG5cdHRyYWNrVGltZTogbnVtYmVyID0gMDtcblxuXHR0cmFja0xhc3Q6IG51bWJlciA9IDA7IG5leHRUcmFja0xhc3Q6IG51bWJlciA9IDA7XG5cblx0LyoqIFRoZSB0cmFjayB0aW1lIGluIHNlY29uZHMgd2hlbiB0aGlzIGFuaW1hdGlvbiB3aWxsIGJlIHJlbW92ZWQgZnJvbSB0aGUgdHJhY2suIERlZmF1bHRzIHRvIHRoZSBoaWdoZXN0IHBvc3NpYmxlIGZsb2F0XG5cdCAqIHZhbHVlLCBtZWFuaW5nIHRoZSBhbmltYXRpb24gd2lsbCBiZSBhcHBsaWVkIHVudGlsIGEgbmV3IGFuaW1hdGlvbiBpcyBzZXQgb3IgdGhlIHRyYWNrIGlzIGNsZWFyZWQuIElmIHRoZSB0cmFjayBlbmQgdGltZVxuXHQgKiBpcyByZWFjaGVkLCBubyBvdGhlciBhbmltYXRpb25zIGFyZSBxdWV1ZWQgZm9yIHBsYXliYWNrLCBhbmQgbWl4aW5nIGZyb20gYW55IHByZXZpb3VzIGFuaW1hdGlvbnMgaXMgY29tcGxldGUsIHRoZW4gdGhlXG5cdCAqIHByb3BlcnRpZXMga2V5ZWQgYnkgdGhlIGFuaW1hdGlvbiBhcmUgc2V0IHRvIHRoZSBzZXR1cCBwb3NlIGFuZCB0aGUgdHJhY2sgaXMgY2xlYXJlZC5cblx0ICpcblx0ICogSXQgbWF5IGJlIGRlc2lyZWQgdG8gdXNlIHtAbGluayBBbmltYXRpb25TdGF0ZSNhZGRFbXB0eUFuaW1hdGlvbigpfSByYXRoZXIgdGhhbiBoYXZlIHRoZSBhbmltYXRpb25cblx0ICogYWJydXB0bHkgY2Vhc2UgYmVpbmcgYXBwbGllZC4gKi9cblx0dHJhY2tFbmQ6IG51bWJlciA9IDA7XG5cblx0LyoqIE11bHRpcGxpZXIgZm9yIHRoZSBkZWx0YSB0aW1lIHdoZW4gdGhpcyB0cmFjayBlbnRyeSBpcyB1cGRhdGVkLCBjYXVzaW5nIHRpbWUgZm9yIHRoaXMgYW5pbWF0aW9uIHRvIHBhc3Mgc2xvd2VyIG9yXG5cdCAqIGZhc3Rlci4gRGVmYXVsdHMgdG8gMS5cblx0ICpcblx0ICoge0BsaW5rICNtaXhUaW1lfSBpcyBub3QgYWZmZWN0ZWQgYnkgdHJhY2sgZW50cnkgdGltZSBzY2FsZSwgc28ge0BsaW5rICNtaXhEdXJhdGlvbn0gbWF5IG5lZWQgdG8gYmUgYWRqdXN0ZWQgdG9cblx0ICogbWF0Y2ggdGhlIGFuaW1hdGlvbiBzcGVlZC5cblx0ICpcblx0ICogV2hlbiB1c2luZyB7QGxpbmsgQW5pbWF0aW9uU3RhdGUjYWRkQW5pbWF0aW9uKCl9IHdpdGggYSBgZGVsYXlgIDw9IDAsIG5vdGUgdGhlXG5cdCAqIHtAbGluayAjZGVsYXl9IGlzIHNldCB1c2luZyB0aGUgbWl4IGR1cmF0aW9uIGZyb20gdGhlIHtAbGluayBBbmltYXRpb25TdGF0ZURhdGF9LCBhc3N1bWluZyB0aW1lIHNjYWxlIHRvIGJlIDEuIElmXG5cdCAqIHRoZSB0aW1lIHNjYWxlIGlzIG5vdCAxLCB0aGUgZGVsYXkgbWF5IG5lZWQgdG8gYmUgYWRqdXN0ZWQuXG5cdCAqXG5cdCAqIFNlZSBBbmltYXRpb25TdGF0ZSB7QGxpbmsgQW5pbWF0aW9uU3RhdGUjdGltZVNjYWxlfSBmb3IgYWZmZWN0aW5nIGFsbCBhbmltYXRpb25zLiAqL1xuXHR0aW1lU2NhbGU6IG51bWJlciA9IDA7XG5cblx0LyoqIFZhbHVlcyA8IDEgbWl4IHRoaXMgYW5pbWF0aW9uIHdpdGggdGhlIHNrZWxldG9uJ3MgY3VycmVudCBwb3NlICh1c3VhbGx5IHRoZSBwb3NlIHJlc3VsdGluZyBmcm9tIGxvd2VyIHRyYWNrcykuIERlZmF1bHRzXG5cdCAqIHRvIDEsIHdoaWNoIG92ZXJ3cml0ZXMgdGhlIHNrZWxldG9uJ3MgY3VycmVudCBwb3NlIHdpdGggdGhpcyBhbmltYXRpb24uXG5cdCAqXG5cdCAqIFR5cGljYWxseSB0cmFjayAwIGlzIHVzZWQgdG8gY29tcGxldGVseSBwb3NlIHRoZSBza2VsZXRvbiwgdGhlbiBhbHBoYSBpcyB1c2VkIG9uIGhpZ2hlciB0cmFja3MuIEl0IGRvZXNuJ3QgbWFrZSBzZW5zZSB0b1xuXHQgKiB1c2UgYWxwaGEgb24gdHJhY2sgMCBpZiB0aGUgc2tlbGV0b24gcG9zZSBpcyBmcm9tIHRoZSBsYXN0IGZyYW1lIHJlbmRlci4gKi9cblx0YWxwaGE6IG51bWJlciA9IDA7XG5cblx0LyoqIFNlY29uZHMgZnJvbSAwIHRvIHRoZSB7QGxpbmsgI2dldE1peER1cmF0aW9uKCl9IHdoZW4gbWl4aW5nIGZyb20gdGhlIHByZXZpb3VzIGFuaW1hdGlvbiB0byB0aGlzIGFuaW1hdGlvbi4gTWF5IGJlXG5cdCAqIHNsaWdodGx5IG1vcmUgdGhhbiBgbWl4RHVyYXRpb25gIHdoZW4gdGhlIG1peCBpcyBjb21wbGV0ZS4gKi9cblx0bWl4VGltZTogbnVtYmVyID0gMDtcblxuXHQvKiogU2Vjb25kcyBmb3IgbWl4aW5nIGZyb20gdGhlIHByZXZpb3VzIGFuaW1hdGlvbiB0byB0aGlzIGFuaW1hdGlvbi4gRGVmYXVsdHMgdG8gdGhlIHZhbHVlIHByb3ZpZGVkIGJ5IEFuaW1hdGlvblN0YXRlRGF0YVxuXHQgKiB7QGxpbmsgQW5pbWF0aW9uU3RhdGVEYXRhI2dldE1peCgpfSBiYXNlZCBvbiB0aGUgYW5pbWF0aW9uIGJlZm9yZSB0aGlzIGFuaW1hdGlvbiAoaWYgYW55KS5cblx0ICpcblx0ICogQSBtaXggZHVyYXRpb24gb2YgMCBzdGlsbCBtaXhlcyBvdXQgb3ZlciBvbmUgZnJhbWUgdG8gcHJvdmlkZSB0aGUgdHJhY2sgZW50cnkgYmVpbmcgbWl4ZWQgb3V0IGEgY2hhbmNlIHRvIHJldmVydCB0aGVcblx0ICogcHJvcGVydGllcyBpdCB3YXMgYW5pbWF0aW5nLlxuXHQgKlxuXHQgKiBUaGUgYG1peER1cmF0aW9uYCBjYW4gYmUgc2V0IG1hbnVhbGx5IHJhdGhlciB0aGFuIHVzZSB0aGUgdmFsdWUgZnJvbVxuXHQgKiB7QGxpbmsgQW5pbWF0aW9uU3RhdGVEYXRhI2dldE1peCgpfS4gSW4gdGhhdCBjYXNlLCB0aGUgYG1peER1cmF0aW9uYCBjYW4gYmUgc2V0IGZvciBhIG5ld1xuXHQgKiB0cmFjayBlbnRyeSBvbmx5IGJlZm9yZSB7QGxpbmsgQW5pbWF0aW9uU3RhdGUjdXBkYXRlKGZsb2F0KX0gaXMgZmlyc3QgY2FsbGVkLlxuXHQgKlxuXHQgKiBXaGVuIHVzaW5nIHtAbGluayBBbmltYXRpb25TdGF0ZSNhZGRBbmltYXRpb24oKX0gd2l0aCBhIGBkZWxheWAgPD0gMCwgbm90ZSB0aGVcblx0ICoge0BsaW5rICNkZWxheX0gaXMgc2V0IHVzaW5nIHRoZSBtaXggZHVyYXRpb24gZnJvbSB0aGUge0BsaW5rIEFuaW1hdGlvblN0YXRlRGF0YX0sIG5vdCBhIG1peCBkdXJhdGlvbiBzZXRcblx0ICogYWZ0ZXJ3YXJkLiAqL1xuXHRfbWl4RHVyYXRpb246IG51bWJlciA9IDA7IGludGVycnVwdEFscGhhOiBudW1iZXIgPSAwOyB0b3RhbEFscGhhOiBudW1iZXIgPSAwO1xuXG5cdGdldCBtaXhEdXJhdGlvbiAoKSB7XG5cdFx0cmV0dXJuIHRoaXMuX21peER1cmF0aW9uO1xuXHR9XG5cblx0c2V0IG1peER1cmF0aW9uIChtaXhEdXJhdGlvbjogbnVtYmVyKSB7XG5cdFx0dGhpcy5fbWl4RHVyYXRpb24gPSBtaXhEdXJhdGlvbjtcblx0fVxuXG5cdHNldE1peER1cmF0aW9uV2l0aERlbGF5IChtaXhEdXJhdGlvbjogbnVtYmVyLCBkZWxheTogbnVtYmVyKSB7XG5cdFx0dGhpcy5fbWl4RHVyYXRpb24gPSBtaXhEdXJhdGlvbjtcblx0XHRpZiAoZGVsYXkgPD0gMCkge1xuXHRcdFx0aWYgKHRoaXMucHJldmlvdXMgIT0gbnVsbClcblx0XHRcdFx0ZGVsYXkgPSBNYXRoLm1heChkZWxheSArIHRoaXMucHJldmlvdXMuZ2V0VHJhY2tDb21wbGV0ZSgpIC0gbWl4RHVyYXRpb24sIDApO1xuXHRcdFx0ZWxzZVxuXHRcdFx0XHRkZWxheSA9IDA7XG5cdFx0fVxuXHRcdHRoaXMuZGVsYXkgPSBkZWxheTtcblx0fVxuXG5cdC8qKiBDb250cm9scyBob3cgcHJvcGVydGllcyBrZXllZCBpbiB0aGUgYW5pbWF0aW9uIGFyZSBtaXhlZCB3aXRoIGxvd2VyIHRyYWNrcy4gRGVmYXVsdHMgdG8ge0BsaW5rIE1peEJsZW5kI3JlcGxhY2V9LCB3aGljaFxuXHQgKiByZXBsYWNlcyB0aGUgdmFsdWVzIGZyb20gdGhlIGxvd2VyIHRyYWNrcyB3aXRoIHRoZSBhbmltYXRpb24gdmFsdWVzLiB7QGxpbmsgTWl4QmxlbmQjYWRkfSBhZGRzIHRoZSBhbmltYXRpb24gdmFsdWVzIHRvXG5cdCAqIHRoZSB2YWx1ZXMgZnJvbSB0aGUgbG93ZXIgdHJhY2tzLlxuXHQgKlxuXHQgKiBUaGUgYG1peEJsZW5kYCBjYW4gYmUgc2V0IGZvciBhIG5ldyB0cmFjayBlbnRyeSBvbmx5IGJlZm9yZSB7QGxpbmsgQW5pbWF0aW9uU3RhdGUjYXBwbHkoKX0gaXMgZmlyc3Rcblx0ICogY2FsbGVkLiAqL1xuXHRtaXhCbGVuZCA9IE1peEJsZW5kLnJlcGxhY2U7XG5cdHRpbWVsaW5lTW9kZSA9IG5ldyBBcnJheTxudW1iZXI+KCk7XG5cdHRpbWVsaW5lSG9sZE1peCA9IG5ldyBBcnJheTxUcmFja0VudHJ5PigpO1xuXHR0aW1lbGluZXNSb3RhdGlvbiA9IG5ldyBBcnJheTxudW1iZXI+KCk7XG5cblx0cmVzZXQgKCkge1xuXHRcdHRoaXMubmV4dCA9IG51bGw7XG5cdFx0dGhpcy5wcmV2aW91cyA9IG51bGw7XG5cdFx0dGhpcy5taXhpbmdGcm9tID0gbnVsbDtcblx0XHR0aGlzLm1peGluZ1RvID0gbnVsbDtcblx0XHR0aGlzLmFuaW1hdGlvbiA9IG51bGw7XG5cdFx0dGhpcy5saXN0ZW5lciA9IG51bGw7XG5cdFx0dGhpcy50aW1lbGluZU1vZGUubGVuZ3RoID0gMDtcblx0XHR0aGlzLnRpbWVsaW5lSG9sZE1peC5sZW5ndGggPSAwO1xuXHRcdHRoaXMudGltZWxpbmVzUm90YXRpb24ubGVuZ3RoID0gMDtcblx0fVxuXG5cdC8qKiBVc2VzIHtAbGluayAjdHJhY2tUaW1lfSB0byBjb21wdXRlIHRoZSBgYW5pbWF0aW9uVGltZWAsIHdoaWNoIGlzIGJldHdlZW4ge0BsaW5rICNhbmltYXRpb25TdGFydH1cblx0ICogYW5kIHtAbGluayAjYW5pbWF0aW9uRW5kfS4gV2hlbiB0aGUgYHRyYWNrVGltZWAgaXMgMCwgdGhlIGBhbmltYXRpb25UaW1lYCBpcyBlcXVhbCB0byB0aGVcblx0ICogYGFuaW1hdGlvblN0YXJ0YCB0aW1lLiAqL1xuXHRnZXRBbmltYXRpb25UaW1lICgpIHtcblx0XHRpZiAodGhpcy5sb29wKSB7XG5cdFx0XHRsZXQgZHVyYXRpb24gPSB0aGlzLmFuaW1hdGlvbkVuZCAtIHRoaXMuYW5pbWF0aW9uU3RhcnQ7XG5cdFx0XHRpZiAoZHVyYXRpb24gPT0gMCkgcmV0dXJuIHRoaXMuYW5pbWF0aW9uU3RhcnQ7XG5cdFx0XHRyZXR1cm4gKHRoaXMudHJhY2tUaW1lICUgZHVyYXRpb24pICsgdGhpcy5hbmltYXRpb25TdGFydDtcblx0XHR9XG5cdFx0cmV0dXJuIE1hdGgubWluKHRoaXMudHJhY2tUaW1lICsgdGhpcy5hbmltYXRpb25TdGFydCwgdGhpcy5hbmltYXRpb25FbmQpO1xuXHR9XG5cblx0c2V0QW5pbWF0aW9uTGFzdCAoYW5pbWF0aW9uTGFzdDogbnVtYmVyKSB7XG5cdFx0dGhpcy5hbmltYXRpb25MYXN0ID0gYW5pbWF0aW9uTGFzdDtcblx0XHR0aGlzLm5leHRBbmltYXRpb25MYXN0ID0gYW5pbWF0aW9uTGFzdDtcblx0fVxuXG5cdC8qKiBSZXR1cm5zIHRydWUgaWYgYXQgbGVhc3Qgb25lIGxvb3AgaGFzIGJlZW4gY29tcGxldGVkLlxuXHQgKlxuXHQgKiBTZWUge0BsaW5rIEFuaW1hdGlvblN0YXRlTGlzdGVuZXIjY29tcGxldGUoKX0uICovXG5cdGlzQ29tcGxldGUgKCkge1xuXHRcdHJldHVybiB0aGlzLnRyYWNrVGltZSA+PSB0aGlzLmFuaW1hdGlvbkVuZCAtIHRoaXMuYW5pbWF0aW9uU3RhcnQ7XG5cdH1cblxuXHQvKiogUmVzZXRzIHRoZSByb3RhdGlvbiBkaXJlY3Rpb25zIGZvciBtaXhpbmcgdGhpcyBlbnRyeSdzIHJvdGF0ZSB0aW1lbGluZXMuIFRoaXMgY2FuIGJlIHVzZWZ1bCB0byBhdm9pZCBib25lcyByb3RhdGluZyB0aGVcblx0ICogbG9uZyB3YXkgYXJvdW5kIHdoZW4gdXNpbmcge0BsaW5rICNhbHBoYX0gYW5kIHN0YXJ0aW5nIGFuaW1hdGlvbnMgb24gb3RoZXIgdHJhY2tzLlxuXHQgKlxuXHQgKiBNaXhpbmcgd2l0aCB7QGxpbmsgTWl4QmxlbmQjcmVwbGFjZX0gaW52b2x2ZXMgZmluZGluZyBhIHJvdGF0aW9uIGJldHdlZW4gdHdvIG90aGVycywgd2hpY2ggaGFzIHR3byBwb3NzaWJsZSBzb2x1dGlvbnM6XG5cdCAqIHRoZSBzaG9ydCB3YXkgb3IgdGhlIGxvbmcgd2F5IGFyb3VuZC4gVGhlIHR3byByb3RhdGlvbnMgbGlrZWx5IGNoYW5nZSBvdmVyIHRpbWUsIHNvIHdoaWNoIGRpcmVjdGlvbiBpcyB0aGUgc2hvcnQgb3IgbG9uZ1xuXHQgKiB3YXkgYWxzbyBjaGFuZ2VzLiBJZiB0aGUgc2hvcnQgd2F5IHdhcyBhbHdheXMgY2hvc2VuLCBib25lcyB3b3VsZCBmbGlwIHRvIHRoZSBvdGhlciBzaWRlIHdoZW4gdGhhdCBkaXJlY3Rpb24gYmVjYW1lIHRoZVxuXHQgKiBsb25nIHdheS4gVHJhY2tFbnRyeSBjaG9vc2VzIHRoZSBzaG9ydCB3YXkgdGhlIGZpcnN0IHRpbWUgaXQgaXMgYXBwbGllZCBhbmQgcmVtZW1iZXJzIHRoYXQgZGlyZWN0aW9uLiAqL1xuXHRyZXNldFJvdGF0aW9uRGlyZWN0aW9ucyAoKSB7XG5cdFx0dGhpcy50aW1lbGluZXNSb3RhdGlvbi5sZW5ndGggPSAwO1xuXHR9XG5cblx0Z2V0VHJhY2tDb21wbGV0ZSAoKSB7XG5cdFx0bGV0IGR1cmF0aW9uID0gdGhpcy5hbmltYXRpb25FbmQgLSB0aGlzLmFuaW1hdGlvblN0YXJ0O1xuXHRcdGlmIChkdXJhdGlvbiAhPSAwKSB7XG5cdFx0XHRpZiAodGhpcy5sb29wKSByZXR1cm4gZHVyYXRpb24gKiAoMSArICgodGhpcy50cmFja1RpbWUgLyBkdXJhdGlvbikgfCAwKSk7IC8vIENvbXBsZXRpb24gb2YgbmV4dCBsb29wLlxuXHRcdFx0aWYgKHRoaXMudHJhY2tUaW1lIDwgZHVyYXRpb24pIHJldHVybiBkdXJhdGlvbjsgLy8gQmVmb3JlIGR1cmF0aW9uLlxuXHRcdH1cblx0XHRyZXR1cm4gdGhpcy50cmFja1RpbWU7IC8vIE5leHQgdXBkYXRlLlxuXHR9XG5cblx0LyoqIFJldHVybnMgdHJ1ZSBpZiB0aGlzIHRyYWNrIGVudHJ5IGhhcyBiZWVuIGFwcGxpZWQgYXQgbGVhc3Qgb25jZS5cblx0ICogPHA+XG5cdCAqIFNlZSB7QGxpbmsgQW5pbWF0aW9uU3RhdGUjYXBwbHkoU2tlbGV0b24pfS4gKi9cblx0d2FzQXBwbGllZCAoKSB7XG5cdFx0cmV0dXJuIHRoaXMubmV4dFRyYWNrTGFzdCAhPSAtMTtcblx0fVxuXG5cdC8qKiBSZXR1cm5zIHRydWUgaWYgdGhlcmUgaXMgYSB7QGxpbmsgI2dldE5leHQoKX0gdHJhY2sgZW50cnkgYW5kIGl0IHdpbGwgYmVjb21lIHRoZSBjdXJyZW50IHRyYWNrIGVudHJ5IGR1cmluZyB0aGUgbmV4dFxuXHQgKiB7QGxpbmsgQW5pbWF0aW9uU3RhdGUjdXBkYXRlKGZsb2F0KX0uICovXG5cdGlzTmV4dFJlYWR5ICgpIHtcblx0XHRyZXR1cm4gdGhpcy5uZXh0ICE9IG51bGwgJiYgdGhpcy5uZXh0VHJhY2tMYXN0IC0gdGhpcy5uZXh0LmRlbGF5ID49IDA7XG5cdH1cbn1cblxuZXhwb3J0IGNsYXNzIEV2ZW50UXVldWUge1xuXHRvYmplY3RzOiBBcnJheTxhbnk+ID0gW107XG5cdGRyYWluRGlzYWJsZWQgPSBmYWxzZTtcblx0YW5pbVN0YXRlOiBBbmltYXRpb25TdGF0ZTtcblxuXHRjb25zdHJ1Y3RvciAoYW5pbVN0YXRlOiBBbmltYXRpb25TdGF0ZSkge1xuXHRcdHRoaXMuYW5pbVN0YXRlID0gYW5pbVN0YXRlO1xuXHR9XG5cblx0c3RhcnQgKGVudHJ5OiBUcmFja0VudHJ5KSB7XG5cdFx0dGhpcy5vYmplY3RzLnB1c2goRXZlbnRUeXBlLnN0YXJ0KTtcblx0XHR0aGlzLm9iamVjdHMucHVzaChlbnRyeSk7XG5cdFx0dGhpcy5hbmltU3RhdGUuYW5pbWF0aW9uc0NoYW5nZWQgPSB0cnVlO1xuXHR9XG5cblx0aW50ZXJydXB0IChlbnRyeTogVHJhY2tFbnRyeSkge1xuXHRcdHRoaXMub2JqZWN0cy5wdXNoKEV2ZW50VHlwZS5pbnRlcnJ1cHQpO1xuXHRcdHRoaXMub2JqZWN0cy5wdXNoKGVudHJ5KTtcblx0fVxuXG5cdGVuZCAoZW50cnk6IFRyYWNrRW50cnkpIHtcblx0XHR0aGlzLm9iamVjdHMucHVzaChFdmVudFR5cGUuZW5kKTtcblx0XHR0aGlzLm9iamVjdHMucHVzaChlbnRyeSk7XG5cdFx0dGhpcy5hbmltU3RhdGUuYW5pbWF0aW9uc0NoYW5nZWQgPSB0cnVlO1xuXHR9XG5cblx0ZGlzcG9zZSAoZW50cnk6IFRyYWNrRW50cnkpIHtcblx0XHR0aGlzLm9iamVjdHMucHVzaChFdmVudFR5cGUuZGlzcG9zZSk7XG5cdFx0dGhpcy5vYmplY3RzLnB1c2goZW50cnkpO1xuXHR9XG5cblx0Y29tcGxldGUgKGVudHJ5OiBUcmFja0VudHJ5KSB7XG5cdFx0dGhpcy5vYmplY3RzLnB1c2goRXZlbnRUeXBlLmNvbXBsZXRlKTtcblx0XHR0aGlzLm9iamVjdHMucHVzaChlbnRyeSk7XG5cdH1cblxuXHRldmVudCAoZW50cnk6IFRyYWNrRW50cnksIGV2ZW50OiBFdmVudCkge1xuXHRcdHRoaXMub2JqZWN0cy5wdXNoKEV2ZW50VHlwZS5ldmVudCk7XG5cdFx0dGhpcy5vYmplY3RzLnB1c2goZW50cnkpO1xuXHRcdHRoaXMub2JqZWN0cy5wdXNoKGV2ZW50KTtcblx0fVxuXG5cdGRyYWluICgpIHtcblx0XHRpZiAodGhpcy5kcmFpbkRpc2FibGVkKSByZXR1cm47XG5cdFx0dGhpcy5kcmFpbkRpc2FibGVkID0gdHJ1ZTtcblxuXHRcdGxldCBvYmplY3RzID0gdGhpcy5vYmplY3RzO1xuXG5cdFx0Zm9yIChsZXQgaSA9IDA7IGkgPCBvYmplY3RzLmxlbmd0aDsgaSArPSAyKSB7XG5cdFx0XHRsZXQgdHlwZSA9IG9iamVjdHNbaV0gYXMgRXZlbnRUeXBlO1xuXHRcdFx0bGV0IGVudHJ5ID0gb2JqZWN0c1tpICsgMV0gYXMgVHJhY2tFbnRyeTtcblx0XHRcdGxldCBsaXN0ZW5lcnMgPSB0aGlzLmFuaW1TdGF0ZS5saXN0ZW5lcnMuc2xpY2UoKTtcblx0XHRcdHN3aXRjaCAodHlwZSkge1xuXHRcdFx0XHRjYXNlIEV2ZW50VHlwZS5zdGFydDpcblx0XHRcdFx0XHRpZiAoZW50cnkubGlzdGVuZXIgJiYgZW50cnkubGlzdGVuZXIuc3RhcnQpIGVudHJ5Lmxpc3RlbmVyLnN0YXJ0KGVudHJ5KTtcblx0XHRcdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgbGlzdGVuZXJzLmxlbmd0aDsgaWkrKykge1xuXHRcdFx0XHRcdFx0bGV0IGxpc3RlbmVyID0gbGlzdGVuZXJzW2lpXTtcblx0XHRcdFx0XHRcdGlmIChsaXN0ZW5lci5zdGFydCkgbGlzdGVuZXIuc3RhcnQoZW50cnkpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0Y2FzZSBFdmVudFR5cGUuaW50ZXJydXB0OlxuXHRcdFx0XHRcdGlmIChlbnRyeS5saXN0ZW5lciAmJiBlbnRyeS5saXN0ZW5lci5pbnRlcnJ1cHQpIGVudHJ5Lmxpc3RlbmVyLmludGVycnVwdChlbnRyeSk7XG5cdFx0XHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IGxpc3RlbmVycy5sZW5ndGg7IGlpKyspIHtcblx0XHRcdFx0XHRcdGxldCBsaXN0ZW5lciA9IGxpc3RlbmVyc1tpaV07XG5cdFx0XHRcdFx0XHRpZiAobGlzdGVuZXIuaW50ZXJydXB0KSBsaXN0ZW5lci5pbnRlcnJ1cHQoZW50cnkpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0XHRicmVhaztcblx0XHRcdFx0Y2FzZSBFdmVudFR5cGUuZW5kOlxuXHRcdFx0XHRcdGlmIChlbnRyeS5saXN0ZW5lciAmJiBlbnRyeS5saXN0ZW5lci5lbmQpIGVudHJ5Lmxpc3RlbmVyLmVuZChlbnRyeSk7XG5cdFx0XHRcdFx0Zm9yIChsZXQgaWkgPSAwOyBpaSA8IGxpc3RlbmVycy5sZW5ndGg7IGlpKyspIHtcblx0XHRcdFx0XHRcdGxldCBsaXN0ZW5lciA9IGxpc3RlbmVyc1tpaV07XG5cdFx0XHRcdFx0XHRpZiAobGlzdGVuZXIuZW5kKSBsaXN0ZW5lci5lbmQoZW50cnkpO1xuXHRcdFx0XHRcdH1cblx0XHRcdFx0Ly8gRmFsbCB0aHJvdWdoLlxuXHRcdFx0XHRjYXNlIEV2ZW50VHlwZS5kaXNwb3NlOlxuXHRcdFx0XHRcdGlmIChlbnRyeS5saXN0ZW5lciAmJiBlbnRyeS5saXN0ZW5lci5kaXNwb3NlKSBlbnRyeS5saXN0ZW5lci5kaXNwb3NlKGVudHJ5KTtcblx0XHRcdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgbGlzdGVuZXJzLmxlbmd0aDsgaWkrKykge1xuXHRcdFx0XHRcdFx0bGV0IGxpc3RlbmVyID0gbGlzdGVuZXJzW2lpXTtcblx0XHRcdFx0XHRcdGlmIChsaXN0ZW5lci5kaXNwb3NlKSBsaXN0ZW5lci5kaXNwb3NlKGVudHJ5KTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0dGhpcy5hbmltU3RhdGUudHJhY2tFbnRyeVBvb2wuZnJlZShlbnRyeSk7XG5cdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHRcdGNhc2UgRXZlbnRUeXBlLmNvbXBsZXRlOlxuXHRcdFx0XHRcdGlmIChlbnRyeS5saXN0ZW5lciAmJiBlbnRyeS5saXN0ZW5lci5jb21wbGV0ZSkgZW50cnkubGlzdGVuZXIuY29tcGxldGUoZW50cnkpO1xuXHRcdFx0XHRcdGZvciAobGV0IGlpID0gMDsgaWkgPCBsaXN0ZW5lcnMubGVuZ3RoOyBpaSsrKSB7XG5cdFx0XHRcdFx0XHRsZXQgbGlzdGVuZXIgPSBsaXN0ZW5lcnNbaWldO1xuXHRcdFx0XHRcdFx0aWYgKGxpc3RlbmVyLmNvbXBsZXRlKSBsaXN0ZW5lci5jb21wbGV0ZShlbnRyeSk7XG5cdFx0XHRcdFx0fVxuXHRcdFx0XHRcdGJyZWFrO1xuXHRcdFx0XHRjYXNlIEV2ZW50VHlwZS5ldmVudDpcblx0XHRcdFx0XHRsZXQgZXZlbnQgPSBvYmplY3RzW2krKyArIDJdIGFzIEV2ZW50O1xuXHRcdFx0XHRcdGlmIChlbnRyeS5saXN0ZW5lciAmJiBlbnRyeS5saXN0ZW5lci5ldmVudCkgZW50cnkubGlzdGVuZXIuZXZlbnQoZW50cnksIGV2ZW50KTtcblx0XHRcdFx0XHRmb3IgKGxldCBpaSA9IDA7IGlpIDwgbGlzdGVuZXJzLmxlbmd0aDsgaWkrKykge1xuXHRcdFx0XHRcdFx0bGV0IGxpc3RlbmVyID0gbGlzdGVuZXJzW2lpXTtcblx0XHRcdFx0XHRcdGlmIChsaXN0ZW5lci5ldmVudCkgbGlzdGVuZXIuZXZlbnQoZW50cnksIGV2ZW50KTtcblx0XHRcdFx0XHR9XG5cdFx0XHRcdFx0YnJlYWs7XG5cdFx0XHR9XG5cdFx0fVxuXHRcdHRoaXMuY2xlYXIoKTtcblxuXHRcdHRoaXMuZHJhaW5EaXNhYmxlZCA9IGZhbHNlO1xuXHR9XG5cblx0Y2xlYXIgKCkge1xuXHRcdHRoaXMub2JqZWN0cy5sZW5ndGggPSAwO1xuXHR9XG59XG5cbmV4cG9ydCBlbnVtIEV2ZW50VHlwZSB7XG5cdHN0YXJ0LCBpbnRlcnJ1cHQsIGVuZCwgZGlzcG9zZSwgY29tcGxldGUsIGV2ZW50XG59XG5cbi8qKiBUaGUgaW50ZXJmYWNlIHRvIGltcGxlbWVudCBmb3IgcmVjZWl2aW5nIFRyYWNrRW50cnkgZXZlbnRzLiBJdCBpcyBhbHdheXMgc2FmZSB0byBjYWxsIEFuaW1hdGlvblN0YXRlIG1ldGhvZHMgd2hlbiByZWNlaXZpbmdcbiAqIGV2ZW50cy5cbiAqXG4gKiBTZWUgVHJhY2tFbnRyeSB7QGxpbmsgVHJhY2tFbnRyeSNsaXN0ZW5lcn0gYW5kIEFuaW1hdGlvblN0YXRlXG4gKiB7QGxpbmsgQW5pbWF0aW9uU3RhdGUjYWRkTGlzdGVuZXIoKX0uICovXG5leHBvcnQgaW50ZXJmYWNlIEFuaW1hdGlvblN0YXRlTGlzdGVuZXIge1xuXHQvKiogSW52b2tlZCB3aGVuIHRoaXMgZW50cnkgaGFzIGJlZW4gc2V0IGFzIHRoZSBjdXJyZW50IGVudHJ5LiAqL1xuXHRzdGFydD86IChlbnRyeTogVHJhY2tFbnRyeSkgPT4gdm9pZDtcblxuXHQvKiogSW52b2tlZCB3aGVuIGFub3RoZXIgZW50cnkgaGFzIHJlcGxhY2VkIHRoaXMgZW50cnkgYXMgdGhlIGN1cnJlbnQgZW50cnkuIFRoaXMgZW50cnkgbWF5IGNvbnRpbnVlIGJlaW5nIGFwcGxpZWQgZm9yXG5cdCAqIG1peGluZy4gKi9cblx0aW50ZXJydXB0PzogKGVudHJ5OiBUcmFja0VudHJ5KSA9PiB2b2lkO1xuXG5cdC8qKiBJbnZva2VkIHdoZW4gdGhpcyBlbnRyeSBpcyBubyBsb25nZXIgdGhlIGN1cnJlbnQgZW50cnkgYW5kIHdpbGwgbmV2ZXIgYmUgYXBwbGllZCBhZ2Fpbi4gKi9cblx0ZW5kPzogKGVudHJ5OiBUcmFja0VudHJ5KSA9PiB2b2lkO1xuXG5cdC8qKiBJbnZva2VkIHdoZW4gdGhpcyBlbnRyeSB3aWxsIGJlIGRpc3Bvc2VkLiBUaGlzIG1heSBvY2N1ciB3aXRob3V0IHRoZSBlbnRyeSBldmVyIGJlaW5nIHNldCBhcyB0aGUgY3VycmVudCBlbnRyeS5cblx0ICogUmVmZXJlbmNlcyB0byB0aGUgZW50cnkgc2hvdWxkIG5vdCBiZSBrZXB0IGFmdGVyIGRpc3Bvc2UgaXMgY2FsbGVkLCBhcyBpdCBtYXkgYmUgZGVzdHJveWVkIG9yIHJldXNlZC4gKi9cblx0ZGlzcG9zZT86IChlbnRyeTogVHJhY2tFbnRyeSkgPT4gdm9pZDtcblxuXHQvKiogSW52b2tlZCBldmVyeSB0aW1lIHRoaXMgZW50cnkncyBhbmltYXRpb24gY29tcGxldGVzIGEgbG9vcC4gKi9cblx0Y29tcGxldGU/OiAoZW50cnk6IFRyYWNrRW50cnkpID0+IHZvaWQ7XG5cblx0LyoqIEludm9rZWQgd2hlbiB0aGlzIGVudHJ5J3MgYW5pbWF0aW9uIHRyaWdnZXJzIGFuIGV2ZW50LiAqL1xuXHRldmVudD86IChlbnRyeTogVHJhY2tFbnRyeSwgZXZlbnQ6IEV2ZW50KSA9PiB2b2lkO1xufVxuXG5leHBvcnQgYWJzdHJhY3QgY2xhc3MgQW5pbWF0aW9uU3RhdGVBZGFwdGVyIGltcGxlbWVudHMgQW5pbWF0aW9uU3RhdGVMaXN0ZW5lciB7XG5cdHN0YXJ0IChlbnRyeTogVHJhY2tFbnRyeSkge1xuXHR9XG5cblx0aW50ZXJydXB0IChlbnRyeTogVHJhY2tFbnRyeSkge1xuXHR9XG5cblx0ZW5kIChlbnRyeTogVHJhY2tFbnRyeSkge1xuXHR9XG5cblx0ZGlzcG9zZSAoZW50cnk6IFRyYWNrRW50cnkpIHtcblx0fVxuXG5cdGNvbXBsZXRlIChlbnRyeTogVHJhY2tFbnRyeSkge1xuXHR9XG5cblx0ZXZlbnQgKGVudHJ5OiBUcmFja0VudHJ5LCBldmVudDogRXZlbnQpIHtcblx0fVxufVxuXG4vKiogMS4gQSBwcmV2aW91c2x5IGFwcGxpZWQgdGltZWxpbmUgaGFzIHNldCB0aGlzIHByb3BlcnR5LlxuICpcbiAqIFJlc3VsdDogTWl4IGZyb20gdGhlIGN1cnJlbnQgcG9zZSB0byB0aGUgdGltZWxpbmUgcG9zZS4gKi9cbmV4cG9ydCBjb25zdCBTVUJTRVFVRU5UID0gMDtcbi8qKiAxLiBUaGlzIGlzIHRoZSBmaXJzdCB0aW1lbGluZSB0byBzZXQgdGhpcyBwcm9wZXJ0eS5cbiAqIDIuIFRoZSBuZXh0IHRyYWNrIGVudHJ5IGFwcGxpZWQgYWZ0ZXIgdGhpcyBvbmUgZG9lcyBub3QgaGF2ZSBhIHRpbWVsaW5lIHRvIHNldCB0aGlzIHByb3BlcnR5LlxuICpcbiAqIFJlc3VsdDogTWl4IGZyb20gdGhlIHNldHVwIHBvc2UgdG8gdGhlIHRpbWVsaW5lIHBvc2UuICovXG5leHBvcnQgY29uc3QgRklSU1QgPSAxO1xuLyoqIDEpIEEgcHJldmlvdXNseSBhcHBsaWVkIHRpbWVsaW5lIGhhcyBzZXQgdGhpcyBwcm9wZXJ0eS48YnI+XG4gKiAyKSBUaGUgbmV4dCB0cmFjayBlbnRyeSB0byBiZSBhcHBsaWVkIGRvZXMgaGF2ZSBhIHRpbWVsaW5lIHRvIHNldCB0aGlzIHByb3BlcnR5Ljxicj5cbiAqIDMpIFRoZSBuZXh0IHRyYWNrIGVudHJ5IGFmdGVyIHRoYXQgb25lIGRvZXMgbm90IGhhdmUgYSB0aW1lbGluZSB0byBzZXQgdGhpcyBwcm9wZXJ0eS48YnI+XG4gKiBSZXN1bHQ6IE1peCBmcm9tIHRoZSBjdXJyZW50IHBvc2UgdG8gdGhlIHRpbWVsaW5lIHBvc2UsIGJ1dCBkbyBub3QgbWl4IG91dC4gVGhpcyBhdm9pZHMgXCJkaXBwaW5nXCIgd2hlbiBjcm9zc2ZhZGluZ1xuICogYW5pbWF0aW9ucyB0aGF0IGtleSB0aGUgc2FtZSBwcm9wZXJ0eS4gQSBzdWJzZXF1ZW50IHRpbWVsaW5lIHdpbGwgc2V0IHRoaXMgcHJvcGVydHkgdXNpbmcgYSBtaXguICovXG5leHBvcnQgY29uc3QgSE9MRF9TVUJTRVFVRU5UID0gMjtcbi8qKiAxKSBUaGlzIGlzIHRoZSBmaXJzdCB0aW1lbGluZSB0byBzZXQgdGhpcyBwcm9wZXJ0eS48YnI+XG4gKiAyKSBUaGUgbmV4dCB0cmFjayBlbnRyeSB0byBiZSBhcHBsaWVkIGRvZXMgaGF2ZSBhIHRpbWVsaW5lIHRvIHNldCB0aGlzIHByb3BlcnR5Ljxicj5cbiAqIDMpIFRoZSBuZXh0IHRyYWNrIGVudHJ5IGFmdGVyIHRoYXQgb25lIGRvZXMgbm90IGhhdmUgYSB0aW1lbGluZSB0byBzZXQgdGhpcyBwcm9wZXJ0eS48YnI+XG4gKiBSZXN1bHQ6IE1peCBmcm9tIHRoZSBzZXR1cCBwb3NlIHRvIHRoZSB0aW1lbGluZSBwb3NlLCBidXQgZG8gbm90IG1peCBvdXQuIFRoaXMgYXZvaWRzIFwiZGlwcGluZ1wiIHdoZW4gY3Jvc3NmYWRpbmcgYW5pbWF0aW9uc1xuICogdGhhdCBrZXkgdGhlIHNhbWUgcHJvcGVydHkuIEEgc3Vic2VxdWVudCB0aW1lbGluZSB3aWxsIHNldCB0aGlzIHByb3BlcnR5IHVzaW5nIGEgbWl4LiAqL1xuZXhwb3J0IGNvbnN0IEhPTERfRklSU1QgPSAzO1xuLyoqIDEuIFRoaXMgaXMgdGhlIGZpcnN0IHRpbWVsaW5lIHRvIHNldCB0aGlzIHByb3BlcnR5LlxuICogMi4gVGhlIG5leHQgdHJhY2sgZW50cnkgdG8gYmUgYXBwbGllZCBkb2VzIGhhdmUgYSB0aW1lbGluZSB0byBzZXQgdGhpcyBwcm9wZXJ0eS5cbiAqIDMuIFRoZSBuZXh0IHRyYWNrIGVudHJ5IGFmdGVyIHRoYXQgb25lIGRvZXMgaGF2ZSBhIHRpbWVsaW5lIHRvIHNldCB0aGlzIHByb3BlcnR5LlxuICogNC4gdGltZWxpbmVIb2xkTWl4IHN0b3JlcyB0aGUgZmlyc3Qgc3Vic2VxdWVudCB0cmFjayBlbnRyeSB0aGF0IGRvZXMgbm90IGhhdmUgYSB0aW1lbGluZSB0byBzZXQgdGhpcyBwcm9wZXJ0eS5cbiAqXG4gKiBSZXN1bHQ6IFRoZSBzYW1lIGFzIEhPTEQgZXhjZXB0IHRoZSBtaXggcGVyY2VudGFnZSBmcm9tIHRoZSB0aW1lbGluZUhvbGRNaXggdHJhY2sgZW50cnkgaXMgdXNlZC4gVGhpcyBoYW5kbGVzIHdoZW4gbW9yZSB0aGFuXG4gKiAyIHRyYWNrIGVudHJpZXMgaW4gYSByb3cgaGF2ZSBhIHRpbWVsaW5lIHRoYXQgc2V0cyB0aGUgc2FtZSBwcm9wZXJ0eS5cbiAqXG4gKiBFZywgQSAtPiBCIC0+IEMgLT4gRCB3aGVyZSBBLCBCLCBhbmQgQyBoYXZlIGEgdGltZWxpbmUgc2V0dGluZyBzYW1lIHByb3BlcnR5LCBidXQgRCBkb2VzIG5vdC4gV2hlbiBBIGlzIGFwcGxpZWQsIHRvIGF2b2lkXG4gKiBcImRpcHBpbmdcIiBBIGlzIG5vdCBtaXhlZCBvdXQsIGhvd2V2ZXIgRCAodGhlIGZpcnN0IGVudHJ5IHRoYXQgZG9lc24ndCBzZXQgdGhlIHByb3BlcnR5KSBtaXhpbmcgaW4gaXMgdXNlZCB0byBtaXggb3V0IEFcbiAqICh3aGljaCBhZmZlY3RzIEIgYW5kIEMpLiBXaXRob3V0IHVzaW5nIEQgdG8gbWl4IG91dCwgQSB3b3VsZCBiZSBhcHBsaWVkIGZ1bGx5IHVudGlsIG1peGluZyBjb21wbGV0ZXMsIHRoZW4gc25hcCBpbnRvXG4gKiBwbGFjZS4gKi9cbmV4cG9ydCBjb25zdCBIT0xEX01JWCA9IDQ7XG5cbmV4cG9ydCBjb25zdCBTRVRVUCA9IDE7XG5leHBvcnQgY29uc3QgQ1VSUkVOVCA9IDI7XG4iXX0=