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

import flask
from flask import request

headers_desktop = util.generate_api_headers(ua_platform='desktop', update_headers_with=(('X-YouTube-Client-Version', '2.20180830'),))
headers_mobile = util.generate_api_headers(ua_platform='mobile', update_headers_with=(('X-YouTube-Client-Version', '2.20180830'),))
real_cookie = (('Cookie', 'VISITOR_INFO1_LIVE=8XihrAcN1l4'),)
generic_cookie = (('Cookie', 'VISITOR_INFO1_LIVE=ST1Ti53r4fU'),)

# https://git.sr.ht/~heckyel/yt-local/commit/a374f90f6e6d3544d759d206a154a51d213c0574
# Sort values for YouTube API (from Invidious): 2=popular, 4=newest, 5=oldest
# include_shorts only applies to tab='videos'; tab='shorts'/'streams' always include their own content.
def channel_ctoken_v6(channel_id, page, sort, tab, view=1, include_shorts=True):
    # Tab-specific protobuf field numbers (from Invidious source)
    # Each tab uses different field numbers in the protobuf structure:
    #   videos:  110 -> 3 -> 15 -> { 2:{1:UUID}, 4:sort, 8:{1:UUID, 3:sort} }
    #   shorts:  110 -> 3 -> 10 -> { 2:{1:UUID}, 4:sort, 7:{1:UUID, 3:sort} }
    #   streams: 110 -> 3 -> 14 -> { 2:{1:UUID}, 5:sort, 8:{1:UUID, 3:sort} }
    tab_config = {
        'videos':  {'tab_field': 15, 'sort_field': 4, 'embedded_field': 8},
        'shorts':  {'tab_field': 10, 'sort_field': 4, 'embedded_field': 7},
        'streams': {'tab_field': 14, 'sort_field': 5, 'embedded_field': 8},
    }
    config = tab_config.get(tab, tab_config['videos'])
    tab_field = config['tab_field']
    sort_field = config['sort_field']
    embedded_field = config['embedded_field']

    # Map sort values to YouTube API values
    if tab == 'streams':
        sort_mapping = {'1': 14, '2': 13, '3': 12, '4': 12}
    else:
        sort_mapping = {'1': 2, '2': 5, '3': 4, '4': 4}
    new_sort = sort_mapping.get(sort, sort_mapping['3'])

    # UUID placeholder (field 1)
    uuid_str = "00000000-0000-0000-0000-000000000000"

    # Build the tab-level object matching Invidious structure exactly:
    # { 2: embedded{1: UUID}, sort_field: sort_val, embedded_field: embedded{1: UUID, 3: sort_val} }
    tab_content = (
        proto.string(2, proto.string(1, uuid_str))
        + proto.uint(sort_field, new_sort)
        + proto.string(embedded_field,
            proto.string(1, uuid_str) + proto.uint(3, new_sort))
    )

    tab_wrapper = proto.string(tab_field, tab_content)
    inner_container = proto.string(3, tab_wrapper)
    outer_container = proto.string(110, inner_container)

    # Add shorts filter when include_shorts=False (field 104, same as playlist.py)
    # This tells YouTube to exclude shorts from the results
    if not include_shorts:
        outer_container += proto.string(104, proto.uint(2, 1))

    encoded_inner = proto.percent_b64encode(outer_container)

    pointless_nest = proto.string(80226972,
        proto.string(2, channel_id)
        + proto.string(3, encoded_inner)
    )

    return base64.urlsafe_b64encode(pointless_nest).decode('ascii')

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
                    ctoken=None, print_status=True, include_shorts=True):
    message = 'Got channel tab' if print_status else None

    if not ctoken:
        if tab in ('videos', 'shorts', 'streams'):
            ctoken = channel_ctoken_v6(channel_id, page, sort, tab, view, include_shorts)
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
                'clientVersion': '2.20180830',
            },
        },
        'continuation': ctoken,
    }

    content = util.fetch_url(
        url, util.merge_dicts(headers_desktop, {'Content-Type': 'application/json'}),
        data=json.dumps(data), debug_name='channel_tab', report_text=message)

    return content

# cache for continuation tokens (videos/shorts/streams pagination)
continuation_token_cache = cachetools.TTLCache(512, 15*60)
# cache entries expire after 30 minutes
number_of_videos_cache = cachetools.TTLCache(128, 30*60)
@cachetools.cached(number_of_videos_cache)
def get_number_of_videos_channel(channel_id):
    if channel_id is None:
        return 1000

    # Uploads playlist
    playlist_id = 'UU' + channel_id[2:]
    url = 'https://m.youtube.com/playlist?list=' + playlist_id + '&pbj=1'

    try:
        response = util.fetch_url(url, headers_desktop,
            debug_name='number_of_videos', report_text='Got number of videos')
    except (urllib.error.HTTPError, util.FetchError) as e:
        traceback.print_exc()
        print("Couldn't retrieve number of videos")
        return 1000

    response = response.decode('utf-8')

    match = None
    for pattern in (
        r'"numVideosText".*?"text":\s*"([\d,]+)"',
        r'"numVideosText".*?([\d,]+)\s*videos?',
        r'"numVideosText".*?([,\d]+)',
        r'([\d,]+)\s*videos?\s*</span>',
    ):
        tmp_match = re.search(pattern, response)
        if tmp_match:
            try: match = int(tmp_match.group(1).replace(',', ''))
            except ValueError: continue

    # match = re.search(r'"numVideosText":\s*{\s*"runs":\s*\[{"text":\s*"([\d,]*) videos"', response)
    # match = re.search(r'"numVideosText".*?([,\d]+)', response)
    if match:
        return match
    else:
        return get_number_of_videos_channel_from_about_tab(channel_id)
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
    # base_url = 'https://www.youtube.com/channel/' + channel_id
    # polymer_json = util.fetch_url(base_url + '/about?pbj=1',
                                  # headers_desktop,
                                  # debug_name='gen_channel_about',
                                  # report_text='Retrieved channel metadata')
    # Use youtubei browse API to get channel metadata
    polymer_json = util.call_youtube_api('web', 'browse', {
        'browseId': channel_id,
    })
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
                'clientVersion': '2.20180830',
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


def get_channel_first_page(base_url=None, tab='videos', channel_id=None, sort=None):
    if channel_id: base_url = 'https://www.youtube.com/channel/' + channel_id
    url = base_url + '/' + tab + '?pbj=1&view=0'
    if sort: url += '&sort=' + playlist_sort_codes.get(sort, 'dd') # default by newest
    return util.fetch_url(url, headers_desktop, debug_name='gen_channel_' + tab)


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
    number_of_pages = None

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
            number_of_videos = pl_info['metadata']['video_count']
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
        if info['items']:   # Success
            page_size = 100
            try_channel_api = False
        else:   # Try the first-page method next
            try_channel_api = True

    # Use the regular channel API
    if tab in ('shorts', 'streams') or (tab=='videos' and try_channel_api):
        if int(sort) != 4 or tab in ('shorts', 'streams'):
            ctoken, continuation, number_of_pages = extract_ctoken(base_url, channel_id, tab, sort, page_number, view, polymer_json=None)
            if isinstance(ctoken, flask.Response): return ctoken

            cache_key = (channel_id, tab, sort, page_number - 1)
            cached_ctoken = continuation_token_cache.get(cache_key)

        if channel_id and not default_params:
            if not channel_id: channel_id = get_channel_id(base_url)
            if channel_id: num_videos_call = (get_number_of_videos_channel, channel_id) # only regular uploads
            else: num_videos_call = (get_number_of_videos_general, base_url)

            # Use ctoken method, which YouTube changes all the time
            page_call = (get_channel_tab, channel_id, str(page_number), sort, tab, int(view), ctoken)
            continuation = True

            # video count required only for the videos tab
            if tab == 'videos': tasks = (gevent.spawn(*num_videos_call), gevent.spawn(*page_call),)
            else: tasks = (gevent.spawn(lambda: 0), gevent.spawn(*page_call),) # number_of_videos will be changed later
            gevent.joinall(tasks)
            util.check_gevent_exceptions(*tasks)
            number_of_videos, polymer_json = tasks[0].value, tasks[1].value
        else:
            # ctoken, continuation, number_of_pages = extract_ctoken(base_url, channel_id, tab, sort, page_number, view, polymer_json=None)
            # if isinstance(ctoken, flask.Response): return ctoken

            if channel_id: num_videos_call = (get_number_of_videos_channel, channel_id)
            else: num_videos_call = (get_number_of_videos_general, base_url)

            # Use the first-page method, which won't break
            page_call = (get_channel_first_page, base_url, tab)

            tasks = (gevent.spawn(*num_videos_call), gevent.spawn(*page_call),)
            gevent.joinall(tasks)
            util.check_gevent_exceptions(*tasks)
            number_of_videos, polymer_json = tasks[0].value, tasks[1].value

        if int(sort) != 4 or tab in ('shorts', 'streams'):
            ctoken, continuation, number_of_pages = extract_ctoken(base_url, channel_id, tab, sort, page_number + 1, view, polymer_json=polymer_json)

    elif tab == 'about':
        #polymer_json = util.fetch_url(base_url + '/about?pbj=1', headers_desktop, debug_name='gen_channel_about')
        channel_id = get_channel_id(base_url)
        ctoken = channel_about_ctoken(channel_id)
        polymer_json = util.call_youtube_api('web', 'browse', {
            'continuation': ctoken,
        })
        continuation=True
    elif tab == 'playlists' and page_number == 1:
        # polymer_json = util.fetch_url(base_url+ '/playlists?pbj=1&view=1&sort=' + playlist_sort_codes[sort], headers_desktop, debug_name='gen_channel_playlists')
        if not channel_id: channel_id = get_channel_id(base_url)
        ctoken = channel_ctoken_v3(channel_id, page='1', sort=sort, tab='playlists', view=view)
        polymer_json = util.call_youtube_api('web', 'browse', {
            'continuation': ctoken,
        })
        continuation = True
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
    if (channel_id and default_params and tab not in ('videos', 'about')
            and info.get('channel_name') is not None):
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

        if info.get('ctoken'):
            cache_key = (channel_id, tab, sort, page_number)
            continuation_token_cache[cache_key] = info['ctoken']

        if tab in ('shorts', 'streams'):
            number_of_videos = len(info.get('items', [])) # use actual item count
            if number_of_videos == 0: number_of_pages = 1
            else: number_of_videos = (page_number - 1) * page_size + number_of_videos
            info['is_last_page'] = (info.get('ctoken') is None)
        if number_of_pages: info['number_of_pages'] = number_of_pages
        elif number_of_videos: info['number_of_pages'] = math.ceil(number_of_videos/page_size)
        else: info['number_of_pages'] = 1
        info['number_of_videos'] = number_of_videos
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

    if request.args.get('sort1', None) == '2': info['items'] = sort_video_items(info['items'], sort_key='approx_view_count')

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
            date_count_multiplier = {'second': 0.00028, 'minute': 0.0167, 'hour': 1, 'day': 24, 'week': 168, 'month': 730, 'year': 8766}
            if string == None: return date_count_multiplier['minute'] # if string is None
            for k,v in date_count_multiplier.items():
                if k in string:
                    multiplier = float(string.replace(' ' + k + ' ago', '').replace(' ' + k + 's ago', '')) * v
                    return multiplier
        elif sort_key in ['title', 'author']:
            return string
        else:
            return None

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

def multi_deep_get(object, *key_sequences, default=None, types=()):
    '''Like deep_get, but can try different key sequences in case one fails.
       Return default if all of them fail. key_sequences is a list of lists'''
    for key_sequence in key_sequences:
        _object = object
        try:
            for key in key_sequence: _object = _object[key]
        except (TypeError, IndexError, KeyError): pass
        else:
            if not types or isinstance(_object, types): return _object
            else: continue
    return default

def get_path_of_keys(data_dict, key_name=None):
    '''Generate all key paths that exists in nested dict (like binary tree)
       and return as [[path1], [path1]]. If key_name exist then, it will find
       and return only those paths that contains key_name with value
       [([key1, key_name, key2], {value1}), ([key1, key2, key_name], {value2}),]'''

    # https://www.reddit.com/r/learnpython/comments/9is7ve/comment/e6mbwg8/
    # i convert to be generator
    def get_paths(haystack, path=[]):
        '''return list of keys'''
        yield path
        if isinstance(haystack, dict):
            for k, v in haystack.items():
                yield from get_paths(v, path + [k])
        elif isinstance(haystack, list):
            for idx, v in enumerate(haystack):
                yield from get_paths(v, path + [idx])

    def get_paths_v2(haystack, needle=None, path=[]):
        '''return list of keys with last element needle
           or all list of keys if needle is None'''
        if (len(path) > 0 and needle == path[-1]) or needle == None: yield path
        iterator = haystack.items() if isinstance(haystack, dict) else (enumerate(haystack) if isinstance(haystack, list) else {})
        for k, v in iterator: yield from get_paths_v2(v, needle, path + [k])

    generated_paths = list(get_paths_v2(data_dict, key_name))
    # generated_paths = list(get_paths(data_dict))
    if key_name: generated_paths = [(i, multi_deep_get(data_dict, i)) for i in generated_paths if i and key_name == i[-1]]
    return generated_paths


# this works only if accesing orderly each page one by one from first
def extract_ctoken(base_url, channel_id, tab, sort, page_number, view, polymer_json=None):

    # print(sort, page_number, tab)

    # bug: if shorts is only tab, when opening second page will cause error
    # to bypass this error need to comment line below
    if sort in ['3', '4'] and tab in ["videos"]: return (None, False, None) # without sorting this works

    # if no ctoken for first page but user access other page number redirect to first page
    if page_number != 1:
        try: ctoken = get_cached_next_page_ctoken(channel_id, tab, sort, 1)
        except:
            boldtext = f'''</br></br></br><h2>Unknown channel tab page number. Go to main channel page: &nbsp; &nbsp; &nbsp;&nbsp;&nbsp;<a href="/{base_url}/{tab}">HERE</a></h2>'''
            #flask.abort(flask.Response(boldtext, 404))
            return (flask.redirect(f"/{base_url}/{tab}?sort={sort}&page=1", 302), None, None)

    page_size = 48 if tab == "shorts" else 30
    number_of_videos = page_size * page_number
    number_of_pages = math.ceil(number_of_videos/page_size)

    try: ctoken = get_cached_next_page_ctoken(channel_id, tab, sort, page_number)
    except: ctoken = None
    else: return (ctoken, True, number_of_pages)

    # request first page where is located continuation token
    if not polymer_json:
        page_call = (get_channel_first_page, base_url, tab)
        tasks = (gevent.spawn(*page_call),)
        gevent.joinall(tasks)
        util.check_gevent_exceptions(*tasks)
        polymer_json = json.loads(tasks[0].value)
        paths_list = get_path_of_keys(polymer_json)

        # chipCloudChipRenderer - contains ctokens for different sorting
        chipCloudChipRenderer = [(i, multi_deep_get(polymer_json, i)) for i in paths_list if i and 'chipCloudChipRenderer' == i[-1]]
        if chipCloudChipRenderer and tab != 'streams':
            # 0 - "Latest", 1 - "Popular", 2 - "Oldest" # this is the order when extracting from 'chipCloudChipRenderer' dict key
            if sort in ['1', '2']: ctoken = chipCloudChipRenderer[int(sort)][1]['navigationEndpoint']['continuationCommand']['token']
            elif int(sort) > 2: ctoken = chipCloudChipRenderer[0][1]['navigationEndpoint']['continuationCommand']['token']
        else: # try other
            try: chipBarViewModel = [(i, multi_deep_get(polymer_json, i)) for i in paths_list if i and 'chipBarViewModel' == i[-1]][0][1]
            except: chipBarViewModel = []
            # chipBarViewModel = multi_deep_get(yt_data_extract.extract_items(polymer_json.get('response', {}), item_types={'richGridRenderer'}), [0,0, 'richGridRenderer', 'header',  'chipBarViewModel'], default=[])
            if chipBarViewModel:
                listItems = multi_deep_get(chipBarViewModel['chips'][0], ['chipViewModel', 'tapCommand', 'innertubeCommand', 'showSheetCommand', 'panelLoadingStrategy', 'inlineContent', 'sheetViewModel', 'content', 'listViewModel', 'listItems'], default=[])
                if len(listItems) == 3 and chipBarViewModel['chips'][1]['chipViewModel']['text'] != 'Popular': # case if Members only
                    ## 0 - "Latest", 1 - "Popular", 2 - "Oldest"
                    if sort in ['1', '2']: ctoken = multi_deep_get(listItems, [int(sort), 'listItemViewModel', 'rendererContext', 'commandContext', 'onTap', 'innertubeCommand', 'commandExecutorCommand', 'commands', 1, 'continuationCommand', 'token'],)
                    elif int(sort) > 2: ctoken = multi_deep_get(listItems, [0, 'listItemViewModel', 'rendererContext', 'commandContext', 'onTap', 'innertubeCommand', 'commandExecutorCommand', 'commands', 1, 'continuationCommand', 'token'],)
                else:
                    ## 0 - "Latest", 1 - "Popular", 2 - "Oldest" # this is the order when extracting from 'chipBarViewModel' dict key
                    if sort in ['1', '2']: ctoken = chipBarViewModel['chips'][int(sort)]['chipViewModel']['tapCommand']['innertubeCommand']['continuationCommand']['token']
                    elif int(sort) > 2: ctoken = chipBarViewModel['chips'][0]['chipViewModel']['tapCommand']['innertubeCommand']['continuationCommand']['token']
        if not ctoken:
            ctoken = multi_deep_get(polymer_json,
            # if number of streams is less than 30
            ['response', 'header', 'pageHeaderRenderer', 'content', 'pageHeaderViewModel', 'description', 'descriptionPreviewViewModel', 'rendererContext', 'commandContext', 'onTap', 'innertubeCommand', 'showEngagementPanelEndpoint', 'engagementPanel', 'engagementPanelSectionListRenderer', 'content', 'sectionListRenderer', 'contents', 0, 'itemSectionRenderer', 'contents', 0, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
            # ['response', 'header', 'pageHeaderRenderer', 'content', 'pageHeaderViewModel', 'attribution', 'attributionViewModel', 'suffix', 'commandRuns', 0, 'onTap', 'innertubeCommand', 'showEngagementPanelEndpoint', 'engagementPanel', 'engagementPanelSectionListRenderer', 'content', 'sectionListRenderer', 'contents', 0, 'itemSectionRenderer', 'contents', 0, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
            )

            # if number of items on first page is less than default
            if (page_number == 1 or ctoken) and tab in ('videos', 'shorts', 'streams'):
                ctoken = channel_ctoken_v6(channel_id, page_number, sort, tab, view)

    else:
        polymer_json = json.loads(polymer_json)
        ctoken = multi_deep_get(polymer_json,

        # videos - 30 items
        ['onResponseReceivedActions', 1, 'reloadContinuationItemsCommand', 'continuationItems', 30, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
        ['onResponseReceivedActions', 0, 'appendContinuationItemsAction', 'continuationItems', 30, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
        ['response', 'contents', 'twoColumnBrowseResultsRenderer', 'tabs', 1, 'tabRenderer', 'content', 'richGridRenderer', 'contents', 30, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],

        # shorts - 48 items
        ['onResponseReceivedActions', 1, 'reloadContinuationItemsCommand', 'continuationItems', 48, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
        ['onResponseReceivedActions', 0, 'appendContinuationItemsAction', 'continuationItems', 48, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
        # if shorts are only tab
        ['response', 'contents', 'twoColumnBrowseResultsRenderer', 'tabs', 2, 'tabRenderer', 'content', 'richGridRenderer', 'contents', 48, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
        ['response', 'contents', 'twoColumnBrowseResultsRenderer', 'tabs', 0, 'tabRenderer', 'content', 'richGridRenderer', 'contents', 48, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
        ['response', 'contents', 'twoColumnBrowseResultsRenderer', 'tabs', 1, 'tabRenderer', 'content', 'richGridRenderer', 'contents', 48, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
        ['response', 'contents', 'twoColumnBrowseResultsRenderer', 'tabs', 3, 'tabRenderer', 'content', 'richGridRenderer', 'contents', 48, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],

        # streams - 30 items
        ['response', 'contents', 'twoColumnBrowseResultsRenderer', 'tabs', 3, 'tabRenderer', 'content', 'richGridRenderer', 'contents', 30, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],

        # other cases for videos and streams
        ['response', 'contents', 'twoColumnBrowseResultsRenderer', 'tabs', 0, 'tabRenderer', 'content', 'richGridRenderer', 'contents', 30, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],
        ['response', 'contents', 'twoColumnBrowseResultsRenderer', 'tabs', 2, 'tabRenderer', 'content', 'richGridRenderer', 'contents', 30, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],

        # other cases
        ['onResponseReceivedActions', 0, 'appendContinuationItemsAction', 'continuationItems', 0, 'continuationItemRenderer', 'continuationEndpoint', 'continuationCommand', 'token'],)

        # if 'response' in polymer_json:
            # ctoken = yt_data_extract.extract_items(polymer_json.get('response', {}), item_types={'null_item_type'})[1]
        # elif 'onResponseReceivedActions' in polymer_json:
            # ctoken = yt_data_extract.extract_items(polymer_json, item_types={'null_item_type'})[1]
        # else:
            # pass

        # some responses have different continuationItems size
        if not ctoken:
            continuationItemRenderer = get_path_of_keys(polymer_json, 'continuationItemRenderer')
            if len(continuationItemRenderer) == 1:
                ctoken = multi_deep_get(continuationItemRenderer[0][1], ['continuationEndpoint', 'continuationCommand', 'token'])
            elif len(continuationItemRenderer) > 1:
                print("many continuationItemRenderer", continuationItemRenderer)

    if ctoken:
        set_cached_next_page_ctoken(channel_id, tab, sort, page_number, ctoken)
    else:
        number_of_videos = page_size * (page_number - 1)

    number_of_pages = math.ceil(number_of_videos/page_size)

    try:
        ctoken = get_cached_next_page_ctoken(channel_id, tab, sort, page_number)
    except:
        ctoken = None

    # becouse there are different ctoken for sorting, they must be processed correctly
    # response, err = yt_data_extract.extract_response(polymer_json)
    # continuation = yt_data_extract.extract_items(response, item_types={'chipCloudChipRenderer'})

    # can be used 'continuationItemRenderer' in common.py but token value extracted need to be insert into cache
    # becouse there are no continuation token for previous pages. i will not use this way

    return (ctoken, True, number_of_pages)


# cache to store tokens for channel
next_page_ctoken = cachetools.TTLCache(128, 30*60)
@cachetools.cached(next_page_ctoken)
def get_cached_next_page_ctoken(channel_id, tab, sort, page_number):
    return ctoken
def set_cached_next_page_ctoken(channel_id, tab, sort, page_number, ctoken):
    @cachetools.cached(next_page_ctoken)
    def dummy_func_using_same_cache(channel_id, tab, sort, page_number):
        return ctoken
    dummy_func_using_same_cache(channel_id, tab, sort, page_number)


# remove cached value
#get_number_of_videos_channel.cache.pop(get_number_of_videos_channel.cache_key(channel_id), None)

