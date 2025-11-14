from youtube import util, yt_data_extract, proto, local_playlist
from youtube import yt_app
import settings

import base64
import urllib
import json
import string
import gevent
import math
from flask import request
import flask
import cachetools.func


def playlist_ctoken(playlist_id, offset, include_shorts=True):

    offset = proto.uint(1, offset)
    offset = b'PT:' + proto.unpadded_b64encode(offset)
    offset = proto.string(15, offset)
    if not include_shorts:
        offset += proto.string(104, proto.uint(2, 1))

    continuation_info = proto.string( 3, proto.percent_b64encode(offset) )

    plid = proto.string(2, "VL" + playlist_id)
    playlist_id_ = proto.string(35, playlist_id)
    pointless_nest = proto.string(80226972, plid + continuation_info + playlist_id_)

    return base64.urlsafe_b64encode(pointless_nest).decode('ascii')

def playlist_call_api(data, report_text, debug_name):
    # Use innertube API (pbj=1 no longer works for many playlists)
    headers_desktop = util.generate_api_headers(ua_platform='desktop')
    key = 'AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'
    url = 'https://www.youtube.com/youtubei/v1/browse?key=' + key
    payload = {
        'context': {
            'client': {
                'hl': 'en',
                'gl': 'US',
                'clientName': 'WEB',
                'clientVersion': headers_desktop['X-YouTube-Client-Version'],
            },
        },
        **data,
    }
    content = util.fetch_url(
        url, util.merge_dicts(headers_desktop, {'Content-Type': 'application/json'}),
        data=json.dumps(payload), report_text=report_text, debug_name=debug_name)
    content = json.loads(content.decode('utf-8'))

    # as alternative
    # content = json.loads(util.call_youtube_api('web', 'browse', data,
        # use_visitor=False, report_text=report_text, debug_name=debug_name))

    return content

@cachetools.func.ttl_cache(maxsize=20, ttl=10*120)
def playlist_first_page(playlist_id, report_text="Retrieved playlist",
                        use_mobile=False):
    return playlist_call_api({'browseId': 'VL' + playlist_id}, report_text=report_text, debug_name='playlist_first_page')


@cachetools.func.ttl_cache(maxsize=20, ttl=10*120)
def get_videos(playlist_id, page, include_shorts=True, page_size=100,
               report_text='Retrieved playlist'):
    ctoken = playlist_ctoken(playlist_id, (int(page)-1)*page_size,
                             include_shorts=include_shorts)
    return playlist_call_api({'continuation': ctoken}, report_text=report_text, debug_name='playlist_videos')


@cachetools.func.ttl_cache(maxsize=20, ttl=10*120)
def playlist_first_page_old(playlist_id, report_text="Retrieved playlist",
                        use_mobile=False):
    if use_mobile:
        url = 'https://m.youtube.com/playlist?list=' + playlist_id + '&pbj=1'
        content = util.fetch_url(
            url, util.generate_api_headers(ua_platform='mobile'),
            report_text=report_text, debug_name='playlist_first_page'
        )
        content = json.loads(content.decode('utf-8'))
    else:
        url = 'https://www.youtube.com/playlist?list=' + playlist_id + '&pbj=1'
        content = util.fetch_url(
            url, util.generate_api_headers(ua_platform='desktop'),
            report_text=report_text, debug_name='playlist_first_page'
        )
        content = json.loads(content.decode('utf-8'))

    return content


@cachetools.func.ttl_cache(maxsize=20, ttl=10*120)
def get_videos_old(playlist_id, page, include_shorts=True, use_mobile=False,
               report_text='Retrieved playlist'):
    # mobile requests return 20 videos per page
    if use_mobile:
        page_size = 20
        headers = util.generate_api_headers(ua_platform='mobile')
    # desktop requests return 100 videos per page
    else:
        page_size = 100
        headers = util.generate_api_headers(ua_platform='desktop')

    url = "https://m.youtube.com/playlist?ctoken="
    url += playlist_ctoken(playlist_id, (int(page)-1)*page_size,
                           include_shorts=include_shorts)
    url += "&pbj=1"
    content = util.fetch_url(
        url, headers, report_text=report_text,
        debug_name='playlist_videos'
    )

    info = json.loads(content.decode('utf-8'))
    return info


import random

g_playlist_items_aggregator = {}
@cachetools.func.ttl_cache(maxsize=20, ttl=10*120)
def get_videos_from_watch_page(playlist_id, index, video_id=None):
    fake_id = '{}'.format(random.randint(0, 99999999999)) if not video_id else video_id
    url = f'https://m.youtube.com/watch?v={fake_id}&list={playlist_id}&index={index}' # info["items"][0]["id"]
    headers = util.generate_api_headers(use_visitor=True)
    watch_page = util.fetch_url(url, headers=headers, report_text='Retrieved watch playlist', debug_name='Retrieved watch playlist')
    watch_page = watch_page.decode('utf-8')
    info = dict(yt_data_extract.extract_watch_info_from_html(watch_page))
    info['playlist']['metadata'] = info['playlist_metadata']
    info['playlist']['error'] = None
    return info['playlist']


@yt_app.route('/playlist')
def get_playlist_page():
    if 'list' not in request.args:
        abort(400)

    playlist_id = request.args.get('list')
    page = request.args.get('page', '1')

    # Radio/Mix playlists (RD...) only work as watch page, not playlist page
    if playlist_id.startswith('RD'):
        return flask.redirect(util.URL_ORIGIN + '/watch?v=' + playlist_id[2:] + '&list=' + playlist_id, 302)

    try_watch_list = False

    if try_watch_list:
        first_page_json = playlist_first_page(playlist_id, report_text='Retrieved playlist info', use_mobile=True)
        info = {'metadata': yt_data_extract.extract_playlist_metadata(first_page_json), 'error': None}

        global g_playlist_items_aggregator
        if not g_playlist_items_aggregator.get(playlist_id): g_playlist_items_aggregator[playlist_id] = []

        if (int(page) != 1 and len(g_playlist_items_aggregator[playlist_id]) == 0) or math.ceil(info['metadata']['video_count']/100) < int(page):
            # this_page_json = get_videos_from_watch_page(playlist_id, (int(page)-1)*100)
            return flask.redirect(f"/https://www.youtube.com/playlist?list={playlist_id}&page=1", 302)

        video_id = info['metadata']['first_video_id']
        this_page_json = None
        if int(page) == 1 or len(g_playlist_items_aggregator[playlist_id]) == 0:
            this_page_json = get_videos_from_watch_page(playlist_id, 1, video_id)
        elif int(page) > 1 and int(page)*99 > len(g_playlist_items_aggregator[playlist_id]):
            index = len(g_playlist_items_aggregator[playlist_id]) + 200
            #if 0 < info['metadata']['video_count'] < index:
            #    index = info['metadata']['video_count']
            if info['metadata']['video_count'] - index < int(page)*100:
                # index += info['metadata']['video_count'] - index
                index = (int(page)-1)*100
            this_page_json = get_videos_from_watch_page(playlist_id, index)

        if this_page_json and len(this_page_json['items']) > 0:
            for i in this_page_json['items']:
                if not any(i['id'] == j['id'] for j in g_playlist_items_aggregator[playlist_id]):
                    if i['title'] != None and i['author_id'] != None:
                        g_playlist_items_aggregator[playlist_id].append(i)

        info['items'] = g_playlist_items_aggregator[playlist_id][100*(int(page)-1):100*(int(page))]

    elif page == '1' and not try_watch_list:
        first_page_json = playlist_first_page(playlist_id)
        this_page_json = first_page_json
        info = yt_data_extract.extract_playlist_info(this_page_json)
    else:
        tasks = (
            gevent.spawn(
                playlist_first_page, playlist_id,
                report_text='Retrieved playlist info', use_mobile=True
            ),
            gevent.spawn(get_videos, playlist_id, page)
        )
        gevent.joinall(tasks)
        util.check_gevent_exceptions(*tasks)
        first_page_json, this_page_json = tasks[0].value, tasks[1].value
        info = yt_data_extract.extract_playlist_info(this_page_json)

    # some playlist does not give items for first page
    if page == '1' and len(info.get('items', [])) == 0:
        info = yt_data_extract.extract_playlist_info(get_videos(playlist_id, page))

    if info['error']:
        return flask.render_template('error.html', error_message = info['error'])

    if page != '1':
        info['metadata'] = yt_data_extract.extract_playlist_metadata(first_page_json)

    util.prefix_urls(info['metadata'])
    for item in info.get('items', ()):
        if item['error']:
            continue
        util.prefix_urls(item)
        util.add_extra_html_info(item)
        if 'id' in item and item['id']:
            item['thumbnail'] = settings.img_prefix + 'https://i.ytimg.com/vi/' + item['id'] + '/default.jpg'

        item['url'] += '&list=' + playlist_id
        if item.get('index', None):
            item['url'] += '&index=' + str(item['index'])

    video_count = yt_data_extract.deep_get(info, 'metadata', 'video_count')
    if video_count is None:
        video_count = 1000

    tmp = local_playlist.youtube_playlists_from_local()
    is_bookmarked = 'false'
    for t in tmp:
        if playlist_id in t[1]: is_bookmarked = 'true'

    if request.args.get('sort1'):
        from youtube.channel import sort_video_items_custom
        info['items'] = sort_video_items_custom(info.get('items', []), request.args.get('sort1', '0'), request.args.get("sort1_reversed", "false")) # sorting

    return flask.render_template('playlist.html',
        header_playlist_names = local_playlist.get_playlist_names(),
        video_list = info.get('items', []),
        num_pages = math.ceil(video_count/100),
        parameters_dictionary = request.args,
        is_bookmarked = is_bookmarked,
        display_as_grid = settings.display_as_grid_youtube,

        **info['metadata']
    ).encode('utf-8')
