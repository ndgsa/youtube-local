/**
 * YouTube Storyboard Preview Thumbnails
 * Shows preview thumbnails when hovering over the progress bar
 * Works with native HTML5 video player
 *
 * Fetches the proxied WebVTT storyboard from backend and extracts image URLs
 */
(function() {
  'use strict';

  console.log('Storyboard Preview Thumbnails loaded');

  // Storyboard configuration
  let storyboardImages = []; // Array of {time, imageUrl, x, y, width, height}
  let previewElement = null;
  let tooltipElement = null;
  let video = null;
  let progressBarRect = null;

  /**
   * Fetch and parse the storyboard VTT file
   * The backend generates a VTT with proxied image URLs
   */
  function fetchStoryboardVTT(vttUrl) {
    return fetch(vttUrl)
      .then(response => {
        if (!response.ok) throw new Error('Failed to fetch storyboard VTT');
        return response.text();
      })
      .then(vttText => {
        console.log('Fetched storyboard VTT, length:', vttText.length);

        const lines = vttText.split('\n');
        const images = [];
        let currentEntry = null;

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();

          // Parse timestamp line: 00:00:00.000 --> 00:00:10.000
          if (line.includes('-->')) {
            const timeMatch = line.match(/^(\d{2}):(\d{2}):(\d{2})\.(\d{3})/);
            if (timeMatch) {
              const hours = parseInt(timeMatch[1]);
              const minutes = parseInt(timeMatch[2]);
              const seconds = parseInt(timeMatch[3]);
              const ms = parseInt(timeMatch[4]);
              currentEntry = {
                time: hours * 3600 + minutes * 60 + seconds + ms / 1000
              };
            }
          }
          // Parse image URL with crop parameters: /url#xywh=x,y,w,h
          else if (line.includes('#xywh=') && currentEntry) {
            const [urlPart, paramsPart] = line.split('#xywh=');
            const [x, y, width, height] = paramsPart.split(',').map(Number);

            currentEntry.imageUrl = urlPart;
            currentEntry.x = x;
            currentEntry.y = y;
            currentEntry.width = width;
            currentEntry.height = height;

            images.push(currentEntry);
            currentEntry = null;
          }
        }

        console.log('Parsed', images.length, 'storyboard frames');
        return images;
      });
  }

  /**
   * Format time as MM:SS or H:MM:SS
   */
  function formatTime(seconds) {
    if (isNaN(seconds)) return '0:00';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  }

  /**
   * Find the closest storyboard frame for a given time
   */
  function findFrameAtTime(time) {
    if (!storyboardImages.length) return null;

    // Binary search for efficiency
    let left = 0;
    let right = storyboardImages.length - 1;

    while (left <= right) {
      const mid = Math.floor((left + right) / 2);
      const frame = storyboardImages[mid];

      if (time >= frame.time && time < (storyboardImages[mid + 1]?.time || Infinity)) {
        return frame;
      } else if (time < frame.time) {
        right = mid - 1;
      } else {
        left = mid + 1;
      }
    }

    // Return closest frame
    return storyboardImages[Math.min(left, storyboardImages.length - 1)];
  }

  /**
   * Detect browser
   */
  function getBrowser() {
    const ua = navigator.userAgent;
    if (ua.indexOf('Firefox') > -1) return 'firefox';
    if (ua.indexOf('Chrome') > -1) return 'chrome';
    if (ua.indexOf('Safari') > -1) return 'safari';
    return 'other';
  }

  /**
   * Detect the progress bar position in native video element
   * Different browsers have different control layouts
   */
  function detectProgressBar() {
    if (!video) return null;

    const rect = video.getBoundingClientRect();
    const browser = getBrowser();

    let progressBarArea;

    switch(browser) {
      case 'firefox':
        // Firefox: La barra de progreso está en la parte inferior pero más delgada
        // Normalmente ocupa solo unos 20-25px de altura y está centrada
        progressBarArea = {
          top: rect.bottom - 30,  // Área más pequeña para Firefox
          bottom: rect.bottom - 5,  // Dejamos espacio para otros controles
          left: rect.left + 60,     // Firefox tiene botones a la izquierda (play, volumen)
          right: rect.right - 10,   // Y a la derecha (fullscreen, etc)
          height: 25
        };
        break;

      case 'chrome':
      default:
        // Chrome: La barra de progreso ocupa un área más grande
        progressBarArea = {
          top: rect.bottom - 50,
          bottom: rect.bottom,
          left: rect.left,
          right: rect.right,
          height: 50
        };
        break;
    }

    return progressBarArea;
  }

  /**
   * Check if mouse is over the progress bar area
   */
  function isOverProgressBar(mouseX, mouseY) {
    if (!progressBarRect) return false;

    return mouseX >= progressBarRect.left &&
           mouseX <= progressBarRect.right &&
           mouseY >= progressBarRect.top &&
           mouseY <= progressBarRect.bottom;
  }

  /**
   * Initialize preview elements
   */
  function initPreviewElements() {
    video = document.querySelector('video');
    if (!video) {
      console.error('Video element not found');
      return;
    }

    console.log('Video element found, browser:', getBrowser());

    // Create preview element
    previewElement = document.createElement('div');
    previewElement.className = 'storyboard-preview';
    previewElement.style.cssText = `
      position: fixed;
      display: none;
      pointer-events: none;
      z-index: 10000;
      background: #000;
      border: 2px solid #fff;
      border-radius: 4px;
      overflow: hidden;
      box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    `;

    // Create tooltip element
    tooltipElement = document.createElement('div');
    tooltipElement.className = 'storyboard-tooltip';
    tooltipElement.style.cssText = `
      position: absolute;
      bottom: -25px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(0,0,0,0.8);
      color: #fff;
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 12px;
      font-family: Arial, sans-serif;
      white-space: nowrap;
      pointer-events: none;
    `;

    previewElement.appendChild(tooltipElement);
    document.body.appendChild(previewElement);

    // Update progress bar position on mouse move
    video.addEventListener('mousemove', updateProgressBarPosition);
  }

  /**
   * Update progress bar position detection
   */
  function updateProgressBarPosition() {
    progressBarRect = detectProgressBar();
  }

  /**
   * Handle mouse move - only show preview when over progress bar area
   */
  function handleMouseMove(e) {
    if (!video || !storyboardImages.length) return;

    // Update progress bar position on each move
    progressBarRect = detectProgressBar();

    // Only show preview if mouse is over the progress bar area
    if (!isOverProgressBar(e.clientX, e.clientY)) {
      if (previewElement) previewElement.style.display = 'none';
      return;
    }

    // Calculate position within the progress bar
    const progressBarWidth = progressBarRect.right - progressBarRect.left;
    let xInProgressBar = e.clientX - progressBarRect.left;

    // Adjust for Firefox's left offset
    const browser = getBrowser();
    if (browser === 'firefox') {
      // Ajustar el rango para que coincida mejor con la barra real
      xInProgressBar = Math.max(0, Math.min(xInProgressBar, progressBarWidth));
    }

    const percentage = Math.max(0, Math.min(1, xInProgressBar / progressBarWidth));
    const time = percentage * video.duration;
    const frame = findFrameAtTime(time);

    if (!frame) return;

    // Preview dimensions
    const previewWidth = 160;
    const previewHeight = 90;
    const offsetFromCursor = 10;

    // Position above the cursor
    let previewTop = e.clientY - previewHeight - offsetFromCursor;

    // If preview would go above the video, position below the cursor
    const videoRect = video.getBoundingClientRect();
    if (previewTop < videoRect.top) {
      previewTop = e.clientY + offsetFromCursor;
    }

    // Keep preview within horizontal bounds
    let left = e.clientX - (previewWidth / 2);

    // Ajustes específicos para Firefox
    if (browser === 'firefox') {
      // En Firefox, la barra no llega hasta los extremos
      const minLeft = progressBarRect.left + 10;
      const maxLeft = progressBarRect.right - previewWidth - 10;
      left = Math.max(minLeft, Math.min(left, maxLeft));
    } else {
      left = Math.max(videoRect.left, Math.min(left, videoRect.right - previewWidth));
    }

    // Apply all styles
    previewElement.style.cssText = `
      display: block;
      position: fixed;
      left: ${left}px;
      top: ${previewTop}px;
      width: ${previewWidth}px;
      height: ${previewHeight}px;
      background-image: url('${frame.imageUrl}');
      background-position: -${frame.x}px -${frame.y}px;
      background-size: auto;
      background-repeat: no-repeat;
      border: 2px solid #fff;
      border-radius: 4px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.5);
      z-index: 10000;
      pointer-events: none;
    `;

    tooltipElement.textContent = formatTime(time);
  }

  /**
   * Handle mouse leave video
   */
  function handleMouseLeave() {
    if (previewElement) {
      previewElement.style.display = 'none';
    }
  }

  /**
   * Initialize storyboard preview
   */
  function init() {
    console.log('Initializing storyboard preview...');

    // Check if storyboard URL is available
    if (typeof storyboard_url === 'undefined' || !storyboard_url) {
      console.log('No storyboard URL available');
      return;
    }

    console.log('Storyboard URL:', storyboard_url);

    // Fetch the proxied VTT file from backend
    fetchStoryboardVTT(storyboard_url)
      .then(images => {
        storyboardImages = images;
        console.log('Loaded', images.length, 'storyboard images');

        if (images.length === 0) {
          console.log('No storyboard images parsed');
          return;
        }

        initPreviewElements();

        // Add event listeners to video
        video.addEventListener('mousemove', handleMouseMove);
        video.addEventListener('mouseleave', handleMouseLeave);

        console.log('Storyboard preview initialized for', getBrowser());
      })
      .catch(err => {
        console.error('Failed to load storyboard:', err);
      });
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
