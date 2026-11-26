
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
    if (e.ctrlKey) return;
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
    else if (c == "j") {
        e.preventDefault();
        v.currentTime = v.currentTime - 10;
    }
    else if (c == "l") {
        e.preventDefault();
        v.currentTime = v.currentTime + 10;
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
