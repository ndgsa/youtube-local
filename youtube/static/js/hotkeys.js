// Ctrl+Right goes to the start of the next chapter. Ctrl+Left goes to the
// start of this chapter, or of the one before it when this one has only
// just started, so pressing it again and again keeps going back.
function skipChapter(v, direction) {
    let chapters = data.chapters;
    let i = 0;
    while (i + 1 < chapters.length && chapters[i + 1].start <= v.currentTime)
        i++;
    if (direction > 0) {
        if (i + 1 < chapters.length)
            v.currentTime = chapters[i + 1].start;
        return;
    }
    // 3 seconds of real time, however fast the video is playing
    let justStarted = v.currentTime - chapters[i].start < 3*v.playbackRate;
    if (justStarted && i > 0)
        i--;
    v.currentTime = chapters[i].start;
}

// Like YouTube's , and . keys: pauses and moves by one frame
function stepFrame(v, direction) {
    let fps = (typeof videoFps !== 'undefined' && videoFps) || 30;
    v.pause();
    v.currentTime = Math.max(0, v.currentTime + direction/fps);
}

// Like YouTube's 0-9 keys: 1 goes to 10% of the video, 2 to 20%, and so on
function seekToPercent(v, digit) {
    let duration = isFinite(v.duration) ? v.duration : data.video_duration;
    if (!duration) return;
    v.currentTime = duration * digit / 10;
}

// Like YouTube's up and down arrows: volume up or down by 5%
function changeVolume(v, delta) {
    // rounded so repeated presses land on 5, 10, 15...
    let volume = Math.round((v.volume + delta) * 20) / 20;
    v.volume = Math.min(1, Math.max(0, volume));
    if (delta > 0 && v.muted)
        v.muted = false;
    //showVolume(v); // hide the volume level indicator, as it obstructs the view
}

// Speaker with 0, 1 or 2 sound waves, or crossed out when silent
const volumeIcons = {
    muted: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="m16 9 6 6M22 9l-6 6"/>',
    low: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 9.5a3.5 3.5 0 0 1 0 5"/>',
    high: '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 9.5a3.5 3.5 0 0 1 0 5"/><path d="M18.5 6.5a7.5 7.5 0 0 1 0 11"/>',
};
let volumeDisplay = null;
let volumeDisplayTimer = null;

// Shows the volume over the video for a second, like YouTube does
function showVolume(v) {
    if (!volumeDisplay) {
        volumeDisplay = document.createElement('div');
        volumeDisplay.className = 'volume-display';
        volumeDisplay.setAttribute('role', 'status');
        volumeDisplay.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"></svg><span></span>';
    }
    // inside plyr's box so it stays visible in plyr's fullscreen
    let box = v.closest('.plyr') || v.parentElement;
    if (volumeDisplay.parentElement !== box) {
        if (getComputedStyle(box).position === 'static')
            box.style.position = 'relative';
        box.appendChild(volumeDisplay);
    }

    let percent = v.muted ? 0 : Math.round(v.volume * 100);
    let icon = percent == 0 ? 'muted' : (percent < 50 ? 'low' : 'high');
    volumeDisplay.querySelector('svg').innerHTML = volumeIcons[icon];
    volumeDisplay.querySelector('span').textContent = percent + '%';
    volumeDisplay.classList.add('shown');
    clearTimeout(volumeDisplayTimer);
    volumeDisplayTimer = setTimeout(function() {
        volumeDisplay.classList.remove('shown');
    }, 1000);
}

function onKeyDown(e) {
    if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return false;

    // console.log(e);
    let v = Q("video");
    if (!e.isTrusted) return;  // plyr CustomEvent
    let c = e.key.toLowerCase();
    if (e.ctrlKey) {
        let isArrow = c == "arrowleft" || c == "arrowright";
        if (isArrow && !e.shiftKey && !e.altKey
                && data.chapters && data.chapters.length) {
            if (data.settings.chapters_mode == 0) return;
            e.preventDefault();
            skipChapter(v, c == "arrowright" ? 1 : -1);
        }
        return;
    }
    else if (c == " ") {
        // Space already does something on these: presses a button or
        // link, opens a dropdown, or (on a focused video with the
        // browser's own controls) plays and pauses by itself
        let focused = document.activeElement;
        if (focused.isContentEditable || focused.closest(
                'button, a, summary, select, video, [role^="menuitem"]'))
            return;
        e.preventDefault();     // instead of scrolling the page down
        if (!e.repeat)
            v.paused ? v.play() : v.pause();
    }
    else if (c == "k") {
        v.paused ? v.play() : v.pause();
    }
    else if (c == "arrowleft") {
        e.preventDefault();
        v.currentTime = v.currentTime - 5;
    }
    else if (c == "arrowright") {
        e.preventDefault();
        v.currentTime = v.currentTime + 5;
    }
    else if (c == "arrowup" || c == "arrowdown") {
        // arrows already pick an option in a focused dropdown
        if (e.shiftKey || e.altKey || e.metaKey
                || document.activeElement.tagName == 'SELECT')
            return;
        e.preventDefault();     // instead of scrolling the page
        changeVolume(v, c == "arrowup" ? 0.05 : -0.05);
    }
    else if (c >= "0" && c <= "9" && c.length == 1) {
        if (data.settings.chapters_mode == 0) return;
        if (e.altKey || e.metaKey) return;
        e.preventDefault();
        seekToPercent(v, Number(c));
    }
    else if (c == "j") {
        e.preventDefault();
        v.currentTime = v.currentTime - 10;
    }
    else if (c == "l") {
        e.preventDefault();
        v.currentTime = v.currentTime + 10;
    }
    else if (c == ",") {
        if (data.settings.chapters_mode == 0) return;
        e.preventDefault();
        stepFrame(v, -1);
    }
    else if (c == ".") {
        if (data.settings.chapters_mode == 0) return;
        e.preventDefault();
        stepFrame(v, 1);
    }
    else if (c == "f") {
        e.preventDefault();
        if (data.settings.video_player == 1)
            player.fullscreen.toggle()
        else {
            if (document.fullscreen) document.exitFullscreen();
            else v.requestFullscreen();
        }
    }
    else if (c == "c") {
        e.preventDefault();
        if (data.settings.video_player == 1)
            player.toggleCaptions();
        else {
            let tt = getActiveTranscriptTrack();
            if (tt == null) return;
            if (tt.mode == "showing") tt.mode = "disabled";
            else tt.mode = "showing";
        }
    }
    else if (c == "t") {
        let ts = Math.floor(Q("video").currentTime);
        copyTextToClipboard(`https://youtu.be/${data.video_id}?t=${ts}`);
    }
}

window.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('keydown', onKeyDown);
});
