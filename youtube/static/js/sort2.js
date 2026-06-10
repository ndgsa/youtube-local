
function setScrollPositionSort2(items) {
  // let video_id = {{ video_id|tojson if video_id else '' }};
  let video_id = '';
  if (typeof data !== 'undefined') video_id = data.video_id || '';
  for (var i = 0; i < items.length; i++) {
    if (JSON.parse(items[i].children[1].value).id === String(video_id)) {
      // scroll playlist to proper position
      document.querySelector('.playlist-videos').scrollTop = 100*i;
      break;
    }
  }
}

function lazyLoadSort2() {
  // lazy load playlist images
  var observer = new IntersectionObserver(lazyLoad,{rootMargin:"100px",threshold:1.0});
  function lazyLoad(elements) { elements.forEach(item => {
    if (item.intersectionRatio > 0) {
      item.target.src = item.target.dataset.src;
      observer.unobserve(item.target);};
    });
  };
  var lazyImages = document.querySelectorAll('img.lazy');
  lazyImages.forEach(img => {observer.observe(img);});
}

function parseDate(d_str) {
  if (!d_str) return 0;

  if ((new Date(d_str) !== "Invalid Date") && !isNaN(new Date(d_str))) return Date.parse(d_str)

  const now = new Date();
  const d_str_lower = d_str.toLowerCase();
  if (d_str_lower.includes('yesterday')) {return now - 24 * 60 * 60 * 1000;}
  if (d_str_lower.includes('just now') || d_str_lower.includes('moment ago')) {return now - 10 * 1000;}
  const match = d_str_lower.match(/(\d+)/);
  let value = match ? parseInt(match[1]) : 0;

  if (!match) {
    if (d_str_lower.includes('second')) value = 1;
    else if (d_str_lower.includes('minute')) value = 1;
    else if (d_str_lower.includes('hour')) value = 1;
    else if (d_str_lower.includes('day')) value = 1;
    else if (d_str_lower.includes('week')) value = 1;
    else if (d_str_lower.includes('month')) value = 1;
    else if (d_str_lower.includes('year')) value = 1;
    else return 0; // Unknown format
  }

  if (d_str_lower.includes('second')) return now - value * 1000;
  if (d_str_lower.includes('minute')) return now - value * 60 * 1000;
  if (d_str_lower.includes('hour')) return now - value * 60 * 60 * 1000;
  if (d_str_lower.includes('day')) return now - value * 24 * 60 * 60 * 1000;
  if (d_str_lower.includes('week')) return now - value * 7 * 24 * 60 * 60 * 1000;
  if (d_str_lower.includes('month')) return now - value * 30 * 24 * 60 * 60 * 1000;
  if (d_str_lower.includes('year')) return now - value * 365 * 24 * 60 * 60 * 1000;

  return 0;
}

function transformTimeString(string) {
  string = (string || '').replace(/[^0-9:.]/g, '');
  if (!string) return '';
  let timeParts = string.split(':').map(part => part.padStart(2, '0'));
  if (timeParts.length === 2) timeParts = ['00', ...timeParts];
  return timeParts.join(':');
}

function SortData(event) {
  if (document.getElementsByClassName("playlist-videos").length > 0) wrapper = document.getElementsByClassName("playlist-videos");
  else if(document.getElementsByClassName("item-list").length > 0) wrapper = document.getElementsByClassName("item-list");
  else if(document.getElementsByClassName("item-grid").length > 0) wrapper = document.getElementsByClassName("item-grid");
  else if (document.getElementById("results")) wrapper = [document.getElementById("results")];
  else {return;}
  var items = Array.from(wrapper[0].children);
  var elements = document.createDocumentFragment();

  // remove element if author is None
  items = items.filter(function(item){
    return item.children[0].children[1].children[1].firstElementChild.textContent !== 'None';
  });

  if (event.dataset.sortName === 'author') {
      items.sort(function (a, b) {
        let t_a;
        let t_b;
        if (a.children[0].children[1].querySelector('address a') === null) t_a = '';
        else t_a = a.children[0].children[1].querySelector('address a').textContent;
        if (b.children[0].children[1].querySelector('address a') === null) t_b = '';
        else t_b = b.children[0].children[1].querySelector('address a').textContent;
        return ('' + t_a).localeCompare(t_b);
      });
  } else if (event.dataset.sortName === 'title') {
      items.sort(function (a, b) {
        let t_a;
        let t_b;
        if (a.children[0].children[1].querySelector('div.title') === null) t_a = '';
        else t_a = a.children[0].children[1].querySelector('div.title').textContent;
        if (b.children[0].children[1].querySelector('div.title') === null) t_b = '';
        else t_b = b.children[0].children[1].querySelector('div.title').textContent;
        return ('' + t_a).localeCompare(t_b);
      });
  } else if (event.dataset.sortName === 'views') {
      const MULTIPLIER = {
        k: 1000,
        m: 1000 * 1000,
        b: 1000 * 1000 * 1000
      };
      items.sort((a,b) => {
        let t_a;
        let t_b;
        if (a.children[0].children[1].querySelector('.stats.horizontal-stats .views') === null) t_a = '0';
        else t_a = a.children[0].children[1].querySelector('.stats.horizontal-stats .views').textContent;
        if (b.children[0].children[1].querySelector('.stats.horizontal-stats .views') === null) t_b = '0';
        else t_b = b.children[0].children[1].querySelector('.stats.horizontal-stats .views').textContent;
        const a_matches = t_a.match(/([0-9.]+)(K|M)?/i);
        const a_views = a_matches[2] ? MULTIPLIER[a_matches[2].toLowerCase()] * parseInt(a_matches[1], 10) : parseInt(a_matches[1], 10);
        const b_matches = t_b.match(/([0-9.]+)(K|M)?/i);
        const b_views = b_matches[2] ? MULTIPLIER[b_matches[2].toLowerCase()] * parseInt(b_matches[1], 10) : parseInt(b_matches[1], 10);
        if (a_views < b_views) return 1;
        if (a_views > b_views) return -1;
        return 0;
      });
  } else if (event.dataset.sortName === 'newest') {
      items.sort((a,b) => {
        let t_a;
        let t_b;
        if (a.children[0].children[1].querySelector('.stats.horizontal-stats time') === null) t_a = '';
        else t_a = a.children[0].children[1].querySelector('.stats.horizontal-stats time').textContent;
        if (b.children[0].children[1].querySelector('.stats.horizontal-stats time') === null) t_b = '';
        else t_b = b.children[0].children[1].querySelector('.stats.horizontal-stats time').textContent;
        const a_time = parseDate(t_a);
        const b_time = parseDate(t_b);
        return b_time - a_time;
      });
  } else if (event.dataset.sortName === 'oldest') {
      items.sort((a,b) => {
        let t_a;
        let t_b;
        if (a.children[0].children[1].querySelector('.stats.horizontal-stats time') === null) t_a = '';
        else t_a = a.children[0].children[1].querySelector('.stats.horizontal-stats time').textContent;
        if (b.children[0].children[1].querySelector('.stats.horizontal-stats time') === null) t_b = '';
        else t_b = b.children[0].children[1].querySelector('.stats.horizontal-stats time').textContent;
        const a_time = parseDate(t_a);
        const b_time = parseDate(t_b);
        return a_time - b_time;
      });
  } else if (event.dataset.sortName === 'duration') {
      items.sort((a,b) => {
        let t_a;
        let t_b;
        if (a.children[0].children[0].querySelector('div .thumbnail-info span') === null) t_a = '';
        else t_a = a.children[0].children[0].querySelector('div .thumbnail-info span').textContent;
        if (b.children[0].children[0].querySelector('div .thumbnail-info span') === null) t_b = '';
        else t_b = b.children[0].children[0].querySelector('div .thumbnail-info span').textContent;
        const a_duration = transformTimeString(t_a);
        const b_duration = transformTimeString(t_b);
        if (a_duration < b_duration) return 1;
        if (a_duration > b_duration) return -1;
        return 0;
      });
	    // alternative way to sort
      // for (let i = 0; i < items.length; i++) {
        // for (let j = i + 1; j < items.length; j++) {
          // let a_duration;
          // let b_duration;
          // if (items[i].children[0].children[0].querySelector('div .thumbnail-info span') === null) a_duration = '';
          // else a_duration = items[i].children[0].children[0].querySelector('div .thumbnail-info span').textContent;
          // if (items[j].children[0].children[0].querySelector('div .thumbnail-info span') === null) b_duration = '';
          // else b_duration = items[j].children[0].children[0].querySelector('div .thumbnail-info span').textContent;
          // if (a_duration > b_duration) {
            // [items[i], items[j]] = [items[j], items[i]];
            // [a_duration, b_duration] = [b_duration, a_duration]; // swapping vars in case next if is true
          // }
          // if (a_duration.length > b_duration.length) {
            // [items[i], items[j]] = [items[j], items[i]];
          // }
        // };
      // };
      // items = items.reverse();
  } else {return;}

  const sort1_reversed_checkbox = document.getElementById('sort1_reversed');
  if (sort1_reversed_checkbox.checked){items = items.reverse();}

  var arrayOfUrlStrings = ['youtube.com/results?search_query', 'youtube.com/playlist?list=', 'youtube.com/channel/'];
  var foundUrlSubstring = arrayOfUrlStrings.find(v => window.location.href.includes(v));
  var arrayOfNavButtons = document.querySelectorAll('nav.page-button-row a.page-button'); //next-previous-button-row
  for (var i = 0; i < arrayOfNavButtons.length; i++) {
      let href = arrayOfNavButtons[i].href;
      href = new URL(href.replace(RegExp('&sort2=[0-9]{0,1}', 'gi'), '').replace(RegExp('&sort1_reversed=(true|false){0,1}', 'gi'), ''));
      href.searchParams.set('sort2', event.dataset.sortNumber);
      href.searchParams.set('sort1_reversed', sort1_reversed_checkbox.checked);
      href = href.toString().replace('?sort2', '&sort2').replace('?sort1_reversed', '&sort1_reversed');
      arrayOfNavButtons[i].setAttribute("href", href);
  };

  for (var i = 0; i < items.length; i++) {
    if (!foundUrlSubstring) {
      let href = items[i].children[0].querySelector('a.thumbnail-box').href;
      href = new URL(href.replace(RegExp('&sort2=[0-9]{0,1}', 'gi'), '').replace(RegExp('&sort1_reversed=(true|false){0,1}', 'gi'), ''));
      href.searchParams.set('sort2', event.dataset.sortNumber);
      href.searchParams.set('sort1_reversed', sort1_reversed_checkbox.checked);
      href = href.toString().replace('?sort2', '&sort2').replace('?sort1_reversed', '&sort1_reversed');
      items[i].children[0].querySelector('a.thumbnail-box').setAttribute("href", href);
      href = null;
      href = items[i].children[0].children[1].querySelector('div.title a.title').href;
      href = new URL(href.replace(RegExp('&sort2=[0-9]{0,1}', 'gi'), '').replace(RegExp('&sort1_reversed=(true|false){0,1}', 'gi'), ''));
      href.searchParams.set('sort2', event.dataset.sortNumber);
      href.searchParams.set('sort1_reversed', sort1_reversed_checkbox.checked);
      href = href.toString().replace('?sort2', '&sort2').replace('?sort1_reversed', '&sort1_reversed');
      items[i].children[0].children[1].querySelector('div.title a.title').setAttribute("href", href);
    }
    elements.appendChild(items[i].cloneNode(true));
  };
  wrapper[0].innerHTML = null;
  wrapper[0].appendChild(elements);

  setScrollPositionSort2(items);

  lazyLoadSort2();
}
let page_current_url = new URLSearchParams(window.location.href);
if (page_current_url.has('sort2')) {
  document.getElementById('sort1_reversed').checked = (new URLSearchParams(window.location.href).get('sort1_reversed') === 'true');
  let sort_buttons = document.getElementsByClassName("sort-button-1");
  if (sort_buttons.length !== 0) {
    for (let i in sort_buttons) {
      if (sort_buttons[i].nodeName === "A" && page_current_url.get('sort2') === sort_buttons[i].dataset.sortNumber) {
        sort_buttons[i].click();
      }
    };
  }
}

function sort1_reversed_toggle() {
  const sort1_reversed_checkbox = document.getElementById('sort1_reversed');
  if (!sort1_reversed_checkbox){return;}
  let sort_buttons = document.getElementsByClassName("sort-button-1");
  let page_current_url = new URL(window.location.href);
  let page_current_url_embed = new URLSearchParams(window.location.href);
  if (window.location.href.includes('youtube.com/embed/') && page_current_url_embed.has('sort1_reversed')) {
    sort1_reversed_checkbox.checked = JSON.parse(page_current_url_embed.get('sort1_reversed'));
  } else if (page_current_url.searchParams.has('sort1_reversed')) {
    sort1_reversed_checkbox.checked = JSON.parse(page_current_url.searchParams.get('sort1_reversed'));
  }
  sort1_reversed_checkbox.addEventListener('change', (event) => {
    if (event.currentTarget.checked === true) {
      sort1_reversed_checkbox.value = 'true';
      sort1_reversed_checkbox.checked = true;
    } else if (event.currentTarget.checked === false) {
      sort1_reversed_checkbox.value = 'false';
      sort1_reversed_checkbox.checked = false;
    }
    if (sort_buttons.length !== 0 && new URLSearchParams(window.location.href).has('sort2') === false) {
      for (let i in sort_buttons) {
        if (sort_buttons[i].nodeName === "A" && sort_buttons[i].href !== 'javascript:;') {
          href = new URL(sort_buttons[i].href.replace(RegExp('[?|&]sort1_reversed=(true|false){0,1}', 'gi'), ''));
          href.searchParams.set('sort1_reversed', sort1_reversed_checkbox.value);
          sort_buttons[i].href = href.toString().replace('?sort1_reversed', '&sort1_reversed');
        }
      };
    }
  });
}
sort1_reversed_toggle();
