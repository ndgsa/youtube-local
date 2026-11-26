
// Source: https://github.com/Jaydorah/youtube-local

// Chapters on the watch page. The server reads them from the timestamps in
// the description (youtube/chapters.py) and passes them in data.chapters
// as [{start, title, time_text}]. This:
// - seeks when a chapter in the list is clicked, and marks the one playing
// - with plyr: splits the seek bar where chapters start, names the chapter
//   in the preview when hovering the bar, and shows the current chapter
//   next to the time
(function() {
'use strict';

if (typeof data === 'undefined' || !data || !data.chapters
        || !data.chapters.length)
    return;
var video = document.querySelector('video');
if (!video)
    return;
var chapters = data.chapters;

// Narrower than this, the current chapter's name would leave too little
// of the seek bar
var MIN_PLAYER_WIDTH_FOR_LABEL = 900;
// Half the seek bar's handle (13px) plus half a divider
var HANDLE_RADIUS = 8;

function videoDuration() {
    var duration = video.duration;
    if (!isFinite(duration) || duration <= 0)
        duration = data.video_duration;
    return (duration && isFinite(duration)) ? duration : 0;
}

function chapterIndexAt(time) {
    var index = 0;
    for (var i = 1; i < chapters.length && chapters[i].start <= time; i++)
        index = i;
    return index;
}


// The list next to the video
var list = document.querySelector('.chapters-list');
var links = list ? list.querySelectorAll('a[data-start]') : [];

links.forEach(function(link) {
    link.addEventListener('click', function(e) {
        // ctrl or shift click still opens it in a new tab or window
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey)
            return;
        e.preventDefault();
        video.currentTime = Number(link.dataset.start);
        var playing = video.play();
        if (playing)
            playing.catch(function() {});
    });
});

// Scrolls only the list, not the page
function scrollListTo(link) {
    if (list.matches(':hover'))
        return;
    var item = link.parentNode;
    var top = item.offsetTop;
    var bottom = top + item.offsetHeight;
    if (top < list.scrollTop)
        list.scrollTop = top;
    else if (bottom > list.scrollTop + list.clientHeight)
        list.scrollTop = bottom - list.clientHeight;
}


// plyr only: null with the browser's own player
var label = null;
var dividers = [];
var progress = null;

var currentIndex = -1;
function showCurrentChapter() {
    var index = chapterIndexAt(video.currentTime);
    if (index === currentIndex)
        return;
    currentIndex = index;
    links.forEach(function(link, i) {
        link.classList.toggle('current-chapter', i === index);
        if (i === index)
            scrollListTo(link);
    });
    if (label) {
        label.textContent = chapters[index].title;
        label.title = chapters[index].title;
    }
}

function placeDividers() {
    var duration = videoDuration();
    dividers.forEach(function(divider, i) {
        var start = chapters[i + 1].start;
        divider.hidden = !duration || start >= duration;
        if (duration)
            divider.style.left = (100*start/duration) + '%';
    });
}

// A divider would be drawn across the handle when it's on a chapter's start
function hideDividersUnderHandle(fraction) {
    var duration = videoDuration();
    if (!duration)
        return;
    var width = progress.clientWidth;
    dividers.forEach(function(divider, i) {
        var distance = Math.abs(chapters[i + 1].start/duration - fraction)*width;
        divider.classList.toggle('under-handle', distance < HANDLE_RADIUS);
    });
}

function setUpPlyr() {
    progress = player.elements.progress;
    var controls = player.elements.controls;
    if (!progress || !controls)
        return;

    var dividerBox = document.createElement('div');
    dividerBox.className = 'chapter-dividers';
    dividers = chapters.slice(1).map(function() {
        return dividerBox.appendChild(document.createElement('span'));
    });
    progress.appendChild(dividerBox);
    placeDividers();
    video.addEventListener('durationchange', placeDividers);

    function handleFollowsVideo() {
        var duration = videoDuration();
        if (duration)
            hideDividersUnderHandle(video.currentTime/duration);
    }
    video.addEventListener('timeupdate', handleFollowsVideo);
    video.addEventListener('seeking', handleFollowsVideo);
    video.addEventListener('durationchange', handleFollowsVideo);
    var seek = player.elements.inputs.seek;
    if (seek)
        // while it's being dragged
        seek.addEventListener('input', function() {
            hideDividersUnderHandle(seek.value/seek.max);
        });
    handleFollowsVideo();

    // The current chapter, after the time
    var times = controls.querySelectorAll('.plyr__time');
    if (times.length) {
        label = document.createElement('div');
        label.className = 'plyr__controls__item chapter-label';
        times[times.length - 1].insertAdjacentElement('afterend', label);
        if (window.ResizeObserver) {
            var container = player.elements.container;
            new ResizeObserver(function() {
                label.hidden = container.clientWidth < MIN_PLAYER_WIDTH_FOR_LABEL;
            }).observe(container);
        }
    }

    // The name of the chapter the pointer is over. It goes under the
    // preview picture, or into the tooltip with the time for videos that
    // have no preview pictures.
    var hoverTitle = document.createElement('div');
    hoverTitle.className = 'chapter-hover-title';
    function showHoveredChapter(e) {
        var duration = videoDuration();
        var rect = progress.getBoundingClientRect();
        if (!duration || !rect.width)
            return;
        var fraction = (e.clientX - rect.left)/rect.width;
        fraction = Math.min(1, Math.max(0, fraction));
        hoverTitle.textContent = chapters[chapterIndexAt(fraction*duration)].title;

        var preview = progress.querySelector('.plyr__preview-thumb');
        var tooltip = player.elements.display.seekTooltip;
        if (preview) {
            if (hoverTitle.parentNode !== preview) {
                preview.appendChild(hoverTitle);
                preview.classList.add('has-chapter-title');
            }
        } else if (tooltip && hoverTitle.parentNode !== tooltip) {
            // plyr writes the time into the tooltip again on every move,
            // which removes the title from it
            tooltip.insertBefore(hoverTitle, tooltip.firstChild);
        }
    }
    // plyr's own listeners were added first, so these run after them
    progress.addEventListener('mouseenter', showHoveredChapter);
    progress.addEventListener('mousemove', showHoveredChapter);
}

if (typeof player !== 'undefined' && player.elements)
    setUpPlyr();

showCurrentChapter();
video.addEventListener('timeupdate', showCurrentChapter);
video.addEventListener('seeking', showCurrentChapter);
video.addEventListener('loadedmetadata', showCurrentChapter);
})();
