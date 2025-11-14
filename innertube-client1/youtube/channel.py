import base64
from youtube import (util, yt_data_extract, local_playlist, subscriptions,
                     playlist)
from youtube import yt_app
import settings

import urllib
import json
from string import Template
import youtube.proto as proto
import html
import math
import gevent
import re
import cachetools.func
import traceback
import calendar
from datetime import datetime, timedelta

import flask
from flask import request

# headers_desktop = util.generate_api_headers(ua_platform='desktop', update_headers_with=(('X-YouTube-Client-Version', '2.20180830'),))
headers_desktop = util.generate_api_headers(ua_platform='desktop')
headers_mobile = util.generate_api_headers(ua_platform='mobile')
real_cookie = (('Cookie', 'VISITOR_INFO1_LIVE=8XihrAcN1l4'),)
generic_cookie = (('Cookie', 'VISITOR_INFO1_LIVE=ST1Ti53r4fU'),)

# added an extra nesting under the 2nd base64 compared to v4
# added tab support
# changed offset field to uint id 1
def channel_ctoken_v5(channel_id, page, sort, tab, view=1):
    new_sort = (2 if int(sort) == 1 else 1)
    offset = 30*(int(page) - 1)
    if tab == 'videos':
        tab = 15
    elif tab == 'shorts':
        tab = 10
    elif tab == 'streams':
        tab = 14
    pointless_nest = proto.string(80226972,
        proto.string(2, channel_id)
        + proto.string(3,
            proto.percent_b64encode(
                proto.string(110,
                    proto.string(3,
                        proto.string(tab,
                            proto.string(1,
                                proto.string(1,
                                    proto.unpadded_b64encode(
                                        proto.string(1,
                                        proto.string(1,
                                            proto.unpadded_b64encode(
                                                proto.string(2,
                                                    b"ST:"
                                                    + proto.unpadded_b64encode(
                                                        proto.uint(1, offset)
                                                    )
                                                )
                                            )
                                        )
                                        )
                                    )
                                )
                                 # targetId, just needs to be present but
                                 # doesn't need to be correct
                                + proto.string(2, "63faaff0-0000-23fe-80f0-582429d11c38")
                            )
                            # 1 - newest, 2 - popular
                            + proto.uint(3, new_sort)
                        )
                    )
                )
            )
        )
    )

    return base64.urlsafe_b64encode(pointless_nest).decode('ascii')

# https://github.com/user234683/youtube-local/issues/151
def channel_ctoken_v4(channel_id, page, sort, tab, view=1):
    new_sort = (2 if int(sort) == 1 else 1)
    offset = str(30*(int(page) - 1))
    pointless_nest = proto.string(80226972,
        proto.string(2, channel_id)
        + proto.string(3,
            proto.percent_b64encode(
                proto.string(110,
                    proto.string(3,
                        proto.string(15,
                            proto.string(1,
                                proto.string(1,
                                    proto.unpadded_b64encode(
                                        proto.string(1,
                                            proto.unpadded_b64encode(
                                                proto.string(2,
                                                    b"ST:"
                                                    + proto.unpadded_b64encode(
                                                        proto.string(2, offset)
                                                    )
                                                )
                                            )
                                        )
                                    )
                                )
                                 # targetId, just needs to be present but
                                 # doesn't need to be correct
                                + proto.string(2, "63faaff0-0000-23fe-80f0-582429d11c38")
                            )
                            # 1 - newest, 2 - popular
                            + proto.uint(3, new_sort)
                        )
                    )
                )
            )
        )
    )

    return base64.urlsafe_b64encode(pointless_nest).decode('ascii')

# SORT:
# videos:
#    Popular - 1
#    Oldest - 2
#    Newest - 3
# playlists:
#    Oldest - 2
#    Newest - 3
#    Last video added - 4

# view:
# grid: 0 or 1
# list: 2
def channel_ctoken_v3(channel_id, page, sort, tab, view=1):
    # page > 1 doesn't work when sorting by oldest
    offset = 30*(int(page) - 1)
    page_token = proto.string(61, proto.unpadded_b64encode(
        proto.string(1, proto.unpadded_b64encode(proto.uint(1,offset)))
    ))

    tab = proto.string(2, tab )
    sort = proto.uint(3, int(sort))

    shelf_view = proto.uint(4, 0)
    view = proto.uint(6, int(view))
    continuation_info = proto.string(3,
        proto.percent_b64encode(tab + sort + shelf_view + view + page_token)
    )

    channel_id = proto.string(2, channel_id )
    pointless_nest = proto.string(80226972, channel_id + continuation_info)

    return base64.urlsafe_b64encode(pointless_nest).decode('ascii')

def channel_ctoken_v2(channel_id, page, sort, tab, view=1):
    # see https://github.com/iv-org/invidious/issues/1319#issuecomment-671732646
    # page > 1 doesn't work when sorting by oldest
    offset = 30*(int(page) - 1)
    schema_number = {
        3: 6307666885028338688,
        2: 17254859483345278706,
        1: 16570086088270825023,
    }[int(sort)]
    page_token = proto.string(61, proto.unpadded_b64encode(proto.string(1,
            proto.uint(1, schema_number) + proto.string(2,
                proto.string(1, proto.unpadded_b64encode(proto.uint(1,offset)))
            )
    )))

    tab = proto.string(2, tab )
    sort = proto.uint(3, int(sort))
    #page = proto.string(15, str(page) )

    shelf_view = proto.uint(4, 0)
    view = proto.uint(6, int(view))
    continuation_info = proto.string(3,
        proto.percent_b64encode(tab + sort + shelf_view + view + page_token)
    )

    channel_id = proto.string(2, channel_id )
    pointless_nest = proto.string(80226972, channel_id + continuation_info)

    return base64.urlsafe_b64encode(pointless_nest).decode('ascii')

def channel_ctoken_v1(channel_id, page, sort, tab, view=1):
    tab = proto.string(2, tab )
    sort = proto.uint(3, int(sort))
    page = proto.string(15, str(page) )
    # example with shelves in videos tab: https://www.youtube.com/channel/UCNL1ZadSjHpjm4q9j2sVtOA/videos
    shelf_view = proto.uint(4, 0)
    view = proto.uint(6, int(view))
    continuation_info = proto.string(3, proto.percent_b64encode(tab + view + sort + shelf_view + page + proto.uint(23, 0)) )

    channel_id = proto.string(2, channel_id )
    pointless_nest = proto.string(80226972, channel_id + continuation_info)

    return base64.urlsafe_b64encode(pointless_nest).decode('ascii')

def channel_about_ctoken(channel_id):
    return proto.make_protobuf(
        ('base64p',
         [
          [2, 80226972,
           [
            [2, 2, channel_id],
            [2, 3,
             ('base64p',
              [
               [2, 110,
                [
                 [2, 3,
                  [
                   [2, 19,
                    [
                     [2, 1, b'66b0e9e9-0000-2820-9589-582429a83980'],
                    ]
                   ],
                  ]
                 ],
                ]
               ],
              ]
             )
            ],
           ]
          ],
         ]
        )
    )

def get_channel_tab(channel_id, page="1", sort=3, tab='videos', view=1,
                    ctoken=None, print_status=True):
    message = 'Got channel tab' if print_status else None

    if not ctoken:
        if tab in ('videos', 'shorts', 'streams'):
            ctoken = channel_ctoken_v5(channel_id, page, sort, tab, view)
        else:
            ctoken = channel_ctoken_v3(channel_id, page, sort, tab, view)
        ctoken = ctoken.replace('=', '%3D')

    # Not sure what the purpose of the key is or whether it will change
    # For now it seems to be constant for the API endpoint, not dependent
    # on the browsing session or channel
    key = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'
    url = 'https://www.youtube.com/youtubei/v1/browse?key=' + key

    data = {
        'context': {
            'client': {
                'hl': 'en',
                'gl': 'US',
                'clientName': 'WEB',
                'clientVersion': headers_desktop['X-YouTube-Client-Version'],
            },
        },
        'continuation': ctoken,
    }

    content = util.fetch_url(
        url, util.merge_dicts(headers_desktop, {'Content-Type': 'application/json'}),
        data=json.dumps(data), debug_name='channel_tab', report_text=message)

    return content

# cache entries expire after 30 minutes
number_of_videos_cache = cachetools.TTLCache(128, 30*60)
@cachetools.cached(number_of_videos_cache)
def get_number_of_videos_channel(channel_id):
    if channel_id is None:
        return 1000
    number_of_videos = None
    try:
        pl_json = playlist.playlist_first_page(
            'UU' + channel_id[2:],    # Uploads playlist
            report_text='Requested number of videos'
        )
        pl_info = yt_data_extract.extract_playlist_info(pl_json)
        number_of_videos = yt_data_extract.num_videos_from_uploads_playlist_info(pl_info)
    except (urllib.error.HTTPError, util.FetchError) as e:
        traceback.print_exc()
    if number_of_videos is None:
        return 1000
    return number_of_videos

def set_cached_number_of_videos(channel_id, num_videos):
    @cachetools.cached(number_of_videos_cache)
    def dummy_func_using_same_cache(channel_id):
        return num_videos
    dummy_func_using_same_cache(channel_id)


channel_id_re_list = [
    re.compile(r'videos\.xml\?channel_id=([a-zA-Z0-9_-]{24})"'),
    re.compile(r'\"\/channel\/([a-zA-Z0-9_-]{24})\"'), # some have different response
]
@cachetools.func.lru_cache(maxsize=128)
def get_channel_id(base_url):
    # method that gives the smallest possible response at ~4 kb
    # needs to be as fast as possible
    base_url = base_url.replace('https://www', 'https://m') # avoid redirect
    response = util.fetch_url(base_url + '/about?pbj=1', headers_mobile,
        debug_name='get_channel_id', report_text='Got channel id').decode('utf-8')
    for channel_id_re in channel_id_re_list:
        match = channel_id_re.search(response)
        if match:
            return match.group(1)
    return None


metadata_cache = cachetools.LRUCache(128)
@cachetools.cached(metadata_cache)
def get_metadata(channel_id, if_error=None):
    base_url = 'https://www.youtube.com/channel/' + channel_id
    polymer_json = util.fetch_url(base_url + '/about?pbj=1',
                                  headers_desktop,
                                  debug_name='gen_channel_about',
                                  report_text='Retrieved channel metadata')
    info = yt_data_extract.extract_channel_info(json.loads(polymer_json),
                                                'about',
                                                continuation=False)
    if if_error != True and info.get("error") == 'Failure getting metadata':
        channel_id = get_channel_id('https://www.youtube.com/channel/' + channel_id)
        print("Failure getting metadata, retry with channel_id: " + channel_id)
        return get_metadata(channel_id, if_error=True) # infinite loop

    return extract_metadata_for_caching(info)
def set_cached_metadata(channel_id, metadata):
    @cachetools.cached(metadata_cache)
    def dummy_func_using_same_cache(channel_id):
        return metadata
    dummy_func_using_same_cache(channel_id)
def extract_metadata_for_caching(channel_info):
    metadata = {}
    for key in ('approx_subscriber_count', 'short_description', 'channel_name',
                'avatar'):
        metadata[key] = channel_info[key]
    return metadata


def get_number_of_videos_general(base_url):
    return get_number_of_videos_channel(get_channel_id(base_url))

def get_channel_search_json(channel_id, query, page):
    offset = proto.unpadded_b64encode(proto.uint(3, (page-1)*30))
    params = proto.string(2, 'search') + proto.string(15, offset)
    params = proto.percent_b64encode(params)
    ctoken = proto.string(2, channel_id) + proto.string(3, params) + proto.string(11, query)
    ctoken = base64.urlsafe_b64encode(proto.nested(80226972, ctoken)).decode('ascii')

    key = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'
    url = 'https://www.youtube.com/youtubei/v1/browse?key=' + key

    data = {
        'context': {
            'client': {
                'hl': 'en',
                'gl': 'US',
                'clientName': 'WEB',
                'clientVersion': headers_desktop['X-YouTube-Client-Version'],
            },
        },
        'continuation': ctoken,
    }

    polymer_json = util.fetch_url(
        url, util.merge_dicts(headers_desktop, {'Content-Type': 'application/json'}),
        data=json.dumps(data), debug_name='channel_search')

    return polymer_json


def post_process_channel_info(info):
    info['avatar'] = util.prefix_url(info['avatar'])
    info['channel_url'] = util.prefix_url(info['channel_url'])
    for item in info['items']:
        util.prefix_urls(item)
        util.add_extra_html_info(item)
    if info['current_tab'] == 'about':
        for i, (text, url) in enumerate(info['links']):
            if isinstance(url, str) and util.YOUTUBE_URL_RE.fullmatch(url):
                info['links'][i] = (text, util.prefix_url(url))


def get_channel_first_page(base_url=None, tab='videos', channel_id=None):
    if channel_id:
        base_url = 'https://www.youtube.com/channel/' + channel_id
    return util.fetch_url(base_url + '/' + tab + '?pbj=1&view=0',
                          headers_desktop, debug_name='gen_channel_' + tab)


playlist_sort_codes = {'2': "da", '3': "dd", '4': "lad"}

# youtube.com/[channel_id]/[tab]
# youtube.com/user/[username]/[tab]
# youtube.com/c/[custom]/[tab]
# youtube.com/[custom]/[tab]
def get_channel_page_general_url(base_url, tab, request, channel_id=None):

    page_number = int(request.args.get('page', 1))
    # sort 1: views
    # sort 2: oldest
    # sort 3: newest
    # sort 4: newest - no shorts (Just a kludge on our end, not internal to yt)
    default_sort = '3' if settings.include_shorts_in_channel else '4'
    sort = request.args.get('sort', default_sort)
    view = request.args.get('view', '1')
    query = request.args.get('query', '')
    ctoken = request.args.get('ctoken', '')
    include_shorts = (sort != '4')
    default_params = (page_number == 1 and sort in ('3', '4') and view == '1')
    continuation = bool(ctoken) # whether or not we're using a continuation
    page_size = 30
    try_channel_api = True
    polymer_json = None

    # Use the special UU playlist which contains all the channel's uploads
    if tab == 'videos' and sort in ('3', '4'):
        if not channel_id:
            channel_id = get_channel_id(base_url)
        if page_number == 1 and include_shorts:
            tasks = (
                gevent.spawn(playlist.playlist_first_page,
                             'UU' + channel_id[2:],
                             report_text='Retrieved channel videos'),
                gevent.spawn(get_metadata, channel_id),
            )
            gevent.joinall(tasks)
            util.check_gevent_exceptions(*tasks)

            # Ignore the metadata for now, it is cached and will be
            # recalled later
            pl_json = tasks[0].value
            pl_info = yt_data_extract.extract_playlist_info(pl_json)
            number_of_videos = yt_data_extract.num_videos_from_uploads_playlist_info(pl_info)
            if number_of_videos is None:
                number_of_videos = 1000
            else:
                set_cached_number_of_videos(channel_id, number_of_videos)
        else:
            tasks = (
                gevent.spawn(playlist.get_videos, 'UU' + channel_id[2:],
                             page_number, include_shorts=include_shorts),
                gevent.spawn(get_metadata, channel_id),
                gevent.spawn(get_number_of_videos_channel, channel_id),
            )
            gevent.joinall(tasks)
            util.check_gevent_exceptions(*tasks)

            pl_json = tasks[0].value
            pl_info = yt_data_extract.extract_playlist_info(pl_json)
            number_of_videos = tasks[2].value
        info = pl_info
        info['channel_id'] = channel_id
        info['current_tab'] = 'videos'
        if not info['error'] and info['items']:   # Success
            page_size = 100
            try_channel_api = False
        else:   # Try the first-page method next
            try_channel_api = True

    # Use the regular channel API
    if tab in ('shorts', 'streams') or (tab=='videos' and try_channel_api):
        if channel_id:
            num_videos_call = (get_number_of_videos_channel, channel_id)
        else:
            num_videos_call = (get_number_of_videos_general, base_url)

        # Use ctoken method, which YouTube changes all the time
        if channel_id and not default_params:
            if sort == 4:
                _sort = 3
            else:
                _sort = sort
            page_call = (get_channel_tab, channel_id, page_number, _sort,
                         tab, view, ctoken)
        # Use the first-page method, which won't break
        else:
            page_call = (get_channel_first_page, base_url, tab)

        tasks = (
            gevent.spawn(*num_videos_call),
            gevent.spawn(*page_call),
        )
        gevent.joinall(tasks)
        util.check_gevent_exceptions(*tasks)
        number_of_videos, polymer_json = tasks[0].value, tasks[1].value

    elif tab == 'about':
        #polymer_json = util.fetch_url(base_url + '/about?pbj=1', headers_desktop, debug_name='gen_channel_about')
        channel_id = get_channel_id(base_url)
        ctoken = channel_about_ctoken(channel_id)
        polymer_json = util.call_youtube_api('web', 'browse', {
            'continuation': ctoken,
        })
        continuation=True
    elif tab == 'playlists' and page_number == 1:
        polymer_json = util.fetch_url(base_url+ '/playlists?pbj=1&view=1&sort=' + playlist_sort_codes[sort], headers_desktop, debug_name='gen_channel_playlists')
    elif tab == 'playlists':
        polymer_json = get_channel_tab(channel_id, page_number, sort,
                                       'playlists', view)
        continuation = True
    elif tab == 'search' and channel_id:
        polymer_json = get_channel_search_json(channel_id, query, page_number)
    elif tab == 'search':
        url = base_url + '/search?pbj=1&query=' + urllib.parse.quote(query, safe='')
        polymer_json = util.fetch_url(url, headers_desktop, debug_name='gen_channel_search')
    elif tab == 'videos':
        pass
    else:
        flask.abort(404, 'Unknown channel tab: ' + tab)

    if polymer_json is not None:
        info = yt_data_extract.extract_channel_info(
            json.loads(polymer_json), tab, continuation=continuation
        )

    if info['error'] is not None:
        return flask.render_template('error.html', error_message=info['error'])

    if channel_id:
        info['channel_url'] = 'https://www.youtube.com/channel/' + channel_id
        info['channel_id'] = channel_id
    else:
        channel_id = info['channel_id']

    # Will have microformat present, cache metadata while we have it
    if channel_id and default_params and tab not in ('videos', 'about'):
        metadata = extract_metadata_for_caching(info)
        set_cached_metadata(channel_id, metadata)
    # Otherwise, populate with our (hopefully cached) metadata
    elif channel_id and info.get('channel_name') is None:
        metadata = get_metadata(channel_id)
        for key, value in metadata.items():
            yt_data_extract.conservative_update(info, key, value)
        # need to add this metadata to the videos/playlists
        additional_info = {
            'author': info['channel_name'],
            'author_id': info['channel_id'],
            'author_url': info['channel_url'],
        }
        for item in info['items']:
            item.update(additional_info)

    if tab in ('videos', 'shorts', 'streams'):
        info['number_of_videos'] = number_of_videos
        info['number_of_pages'] = math.ceil(number_of_videos/page_size)
        info['header_playlist_names'] = local_playlist.get_playlist_names()
    if tab in ('videos', 'shorts', 'streams', 'playlists'):
        info['current_sort'] = sort
    elif tab == 'search':
        info['search_box_value'] = query
        info['header_playlist_names'] = local_playlist.get_playlist_names()
    if tab in ('search', 'playlists'):
        info['page_number'] = page_number
    info['subscribed'] = subscriptions.is_subscribed(info['channel_id'])

    post_process_channel_info(info)

    return flask.render_template('channel.html',
        parameters_dictionary = request.args,
        **info
    )

@yt_app.route('/channel/<channel_id>/')
@yt_app.route('/channel/<channel_id>/<tab>')
def get_channel_page(channel_id, tab='videos'):
    return get_channel_page_general_url('https://www.youtube.com/channel/' + channel_id, tab, request, channel_id)

@yt_app.route('/user/<username>/')
@yt_app.route('/user/<username>/<tab>')
def get_user_page(username, tab='videos'):
    return get_channel_page_general_url('https://www.youtube.com/user/' + username, tab, request)

@yt_app.route('/c/<custom>/')
@yt_app.route('/c/<custom>/<tab>')
def get_custom_c_page(custom, tab='videos'):
    return get_channel_page_general_url('https://www.youtube.com/c/' + custom, tab, request)

@yt_app.route('/<custom>')
@yt_app.route('/<custom>/<tab>')
def get_toplevel_custom_page(custom, tab='videos'):
    return get_channel_page_general_url('https://www.youtube.com/' + custom, tab, request)



def sort_video_items_custom(items, sort1, sort1_reversed='false', sort_key=None, custom_order=None):
    if type(items) is not list: raise Exception('Only list type allowed for sorting!')
    if sort1 == None: return

    order, order1 = (2,1) if sort1_reversed == 'true' else (1,2)
    if custom_order: order, order1 = custom_order

    if sort_key: items = sort_video_items(items, sort_key=sort_key, order=order)
    elif sort1 == '1': items = sort_video_items(items, sort_key='approx_view_count', order=order) # popular
    elif sort1 == '2': items = sort_video_items(items, sort_key='time_published', order=order1) # oldest
    elif sort1 == '3': items = sort_video_items(items, sort_key='time_published', order=order) # newest
    elif sort1 == '4': items = sort_video_items(items, sort_key='title', order=order1) # video title
    elif sort1 == '5': items = sort_video_items(items, sort_key='author', order=order1) # video author
    elif sort1 == '6': items = sort_video_items(items, sort_key='duration', order=order) # video duration
    else: raise Exception('Not implemented sort1 option!')

    return items[:]

_PUBLISHED_TEXT_REGEX = re.compile(r'(\d+)\s?([a-z]+)')
@cachetools.func.lru_cache(maxsize=200)
def parse_date(d_str):
    if not d_str: return 0

    # Try parsing as a standard date string first
    try:
        dt = datetime.fromisoformat(d_str.replace('Z', '+00:00'))
        # dt = datetime.strptime(d_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        pass

    d_str = d_str.lower()
    now = datetime.now()
    match = _PUBLISHED_TEXT_REGEX.match(d_str)
    if match and len(match.groups()) == 2:
        time_frame = match.group(2)
        time_amount = int(match.group(1))
    else:
        time_frame = ''
        time_amount = 0

    if 'yesterday' in d_str: time_span = timedelta(days=1)
    elif 'just now' in d_str or 'moment ago' in d_str: time_span = timedelta(seconds=10)
    elif time_frame.startswith('second') or time_frame in ['s', 'sec']: time_span = timedelta(seconds=time_amount)
    elif time_frame.startswith('minute') or time_frame in ['m', 'min']: time_span = timedelta(minutes=time_amount)
    elif time_frame.startswith('hour') or time_frame in ['h', 'hr']: time_span = timedelta(hours=time_amount)
    elif time_frame.startswith('day') or time_frame in ['d']: time_span = timedelta(days=time_amount)
    elif time_frame.startswith('week') or time_frame in ['w', 'wk']: time_span = timedelta(weeks=time_amount)
    elif time_frame.startswith('month') or time_frame in ['mo']: time_span = timedelta(days=time_amount * 30)
    elif time_frame.startswith('year') or time_frame in ['y', 'yr']: time_span = timedelta(days=time_amount * 365)
    else: return 0

    return int((now - time_span).timestamp() * 1000)

# @cachetools.func.lru_cache(maxsize=200)
def date_to_dumbed_down(date_str):
    dumbed = ''
    totalDays = (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days
    if totalDays <= 0: return f'1 hour ago'
    current_year_total_days = 365 + calendar.isleap(datetime.now().year)
    years = totalDays//current_year_total_days
    months = (totalDays%current_year_total_days)//30
    weeks = (totalDays%current_year_total_days)//7
    # print(f'years:{years} months:{months} weeks:{weeks}')
    if 0 < years: dumbed = f'{years} year ago' if years == 1 else f'{years} years ago'
    elif months == 12: dumbed = f'1 year ago'
    else:
        if 0 < totalDays < 7: dumbed = f'{totalDays} day ago' if totalDays == 1 else f'{totalDays} days ago'
        if 0 < weeks < 3: dumbed = f'{weeks} week ago' if weeks == 1 else f'{weeks} weeks ago'
        if 0 < months < 12: dumbed = f'{months} month ago' if months == 1 else f'{months} months ago'
    return dumbed

def transform_time_string(string):
    string = re.sub(r"[^0-9:.]", "", string or '')
    if not string: return ''
    time_parts = [part.zfill(2) for part in string.split(":")]
    if len(time_parts) == 2: time_parts = ['00'] + time_parts
    return ':'.join(time_parts)

def sort_video_items_by_duration(data, sort_key):
    '''return sorted list of dicts by duration key'''
    sorted_list = data
    for i in range(len(sorted_list)):
        for j in range(i + 1, len(sorted_list)):
            i_s = transform_time_string(sorted_list[i][sort_key])
            j_s = transform_time_string(sorted_list[j][sort_key])
            if i_s > j_s:
                sorted_list[i], sorted_list[j] = sorted_list[j], sorted_list[i]
                i_s, j_s = j_s, i_s  # swapping vars in case next if is True
            if len(i_s) > len(j_s):
                sorted_list[i], sorted_list[j] = sorted_list[j], sorted_list[i]
    return sorted_list

def sort_video_items(data, sort_key='approx_view_count', order=1):
    '''return sorted list of dicts by specific key'''
    def get_multiplier(string):
        if sort_key == 'approx_view_count':
            view_count_multiplier = {'S': 1, 'K': 1000, 'M': 1000000, 'B': 1000000000}
            if string[-1].isalpha() and not string[:-1].isalpha(): multiplier = float(string[:-1]) * view_count_multiplier[string[-1]]
            elif not string.isalpha(): multiplier = int(string) * view_count_multiplier['S']
            else: multiplier = 0 # if string is None
            return multiplier
        elif sort_key == 'time_published':
            return parse_date(string)
            # date_count_multiplier = {'second': 0.00028, 'minute': 0.0167, 'hour': 1, 'day': 24, 'week': 168, 'month': 730, 'year': 8766}
            # if string == None: return date_count_multiplier['minute'] # if string is None
            # try:
                # if 'ago' not in string: string = date_to_dumbed_down(string)
            # except ValueError: pass
            # for k,v in date_count_multiplier.items():
                # if k in string:
                    # multiplier = float(string.replace(' ' + k + ' ago', '').replace(' ' + k + 's ago', '')) * v
                    # return multiplier
        elif sort_key in ['title', 'author']:
            return string
        else:
            return None

    if sort_key == 'duration':
        q = lambda l: sort_video_items_by_duration(l, sort_key)
    else:
        # quicksort oneliner
        q = lambda l: q([x for x in l[1:] if get_multiplier(x[sort_key]) <= get_multiplier(l[0][sort_key])]) + [l[0]] + q([x for x in l if get_multiplier(x[sort_key]) > get_multiplier(l[0][sort_key])]) if l else []

    if len(data) > 1:
        try:
            data1 = q(data)
        except Exception as e:
            print('Error on sorting. Return default.')
            return data

        if order == 1: data1 = list(reversed(data1)) # biggest values at start
        elif order == 2: pass # biggest values at end
        else: pass

    else: data1 = data

    return data1

def get_number_of_videos_channel_from_about_tab(channel_id):
    '''get number of videos from about channel tab'''
    response = util.fetch_url('https://m.youtube.com/channel/' + channel_id + '/about?pbj=1', headers_mobile).decode('utf-8')
    # match = re.search(r'"videoCountText".*?([,\d]+)', response)
    match = re.search(r'"videoCountText"\:"?([,\d]+)', response)
    if match: return int(match.group(1).replace(',',''))
    else: return 0

