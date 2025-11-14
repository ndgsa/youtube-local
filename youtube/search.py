from youtube import util, yt_data_extract, proto, local_playlist
from youtube import yt_app
import settings

import json
import urllib
import base64
import mimetypes
from flask import request
import flask
import os
import gevent # mine
from math import ceil # mine

# Sort: 1
    # Upload date: 2
    # View count: 3
    # Rating: 1
    # Relevance: 0
# Offset: 9
# Filters: 2
    # Upload date: 1
    # Type: 2
    # Duration: 3


features = {
    '4k': 14,
    'hd': 4,
    'hdr': 25,
    'subtitles': 5,
    'creative_commons': 6,
    '3d': 7,
    'live': 8,
    'purchased': 9,
    '360': 15,
    'location': 23,
}

def page_number_to_sp_parameter(page, autocorrect, sort, filters):
    #offset = (int(page) - 1)*50    # 20 results per page # mine
    offset = (int(page) - 1)*20    # 20 results per page # mine
    autocorrect = proto.nested(8, proto.uint(1, 1 - int(autocorrect) ))
    filters_enc = proto.nested(2, proto.uint(1, filters['time']) + proto.uint(2, filters['type']) + proto.uint(3, filters['duration']))
    result = proto.uint(1, sort) + filters_enc + autocorrect + proto.uint(9, offset) + proto.string(61, b'')
    return base64.urlsafe_b64encode(result).decode('ascii')

def get_search_json(query, page, autocorrect, sort, filters):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    headers = {
        'Host': 'www.youtube.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64)',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'X-YouTube-Client-Name': '1',
        'X-YouTube-Client-Version': '2.20180418',
    }
    url += "&pbj=1&sp=" + page_number_to_sp_parameter(page, autocorrect, sort, filters).replace("=", "%3D")
    content = util.fetch_url(url, headers=headers, report_text="Got search results", debug_name='search_results')
    info = json.loads(content)
    return info


@yt_app.route('/results')
@yt_app.route('/search')
def get_search_page():
    query = request.args.get('search_query') or request.args.get('query')
    if query is None:
        return flask.render_template('base.html', title='Search')
    elif query.startswith('https://www.youtube.com') or query.startswith('https://www.youtu.be'):
         return flask.redirect(f'/{query}')

    page = request.args.get("page", "1")
    autocorrect = int(request.args.get("autocorrect", "1"))
    sort = int(request.args.get("sort", "0"))
    filters = {}
    filters['time'] = int(request.args.get("time", "0"))
    filters['type'] = int(request.args.get("type", "0"))
    filters['duration'] = int(request.args.get("duration", "0"))

    # mine
    if True:
        search_info = get_many_pages_as_one(query, page, autocorrect, sort, filters, page_multiplier=3)
    else:
        polymer_json = get_search_json(query, page, autocorrect, sort, filters)
        search_info = yt_data_extract.extract_search_info(polymer_json)
        if search_info['error']:
            return flask.render_template('error.html', error_message = search_info['error'])
        for extract_item_info in search_info['items']:
            util.prefix_urls(extract_item_info)
            util.add_extra_html_info(extract_item_info)

    corrections = search_info['corrections']
    if corrections['type'] == 'did_you_mean':
        corrected_query_string = request.args.to_dict(flat=False)
        corrected_query_string['search_query'] = [corrections['corrected_query']]
        corrections['corrected_query_url'] = util.URL_ORIGIN + '/results?' + urllib.parse.urlencode(corrected_query_string, doseq=True)
    elif corrections['type'] == 'showing_results_for':
        no_autocorrect_query_string = request.args.to_dict(flat=False)
        no_autocorrect_query_string['autocorrect'] = ['0']
        no_autocorrect_query_url = util.URL_ORIGIN + '/results?' + urllib.parse.urlencode(no_autocorrect_query_string, doseq=True)
        corrections['original_query_url'] = no_autocorrect_query_url

    # mine
    search_info['items'] = search_hidden_channels_hide(search_info['items'], request.args.get("duration1", "0"), request.args.get("duration2", "0"))
    from youtube.channel import sort_video_items
    # youtube sort by views badly in some cases, so sort items manualy
    if int(sort) == 3: search_info['items'] = sort_video_items(search_info.get('items', []), sort_key='approx_view_count', order=1)

    return flask.render_template('search.html',
        header_playlist_names = local_playlist.get_playlist_names(),
        query = query,
        estimated_results = search_info['estimated_results'],
        estimated_pages = search_info['estimated_pages'],
        corrections = search_info['corrections'],
        results = search_info['items'],
        parameters_dictionary = request.args,
    )

@yt_app.route('/opensearch.xml')
def get_search_engine_xml():
    with open(os.path.join(settings.program_directory, 'youtube/opensearch.xml'), 'rb') as f:
        content = f.read().replace(b'$host_url',
                                   request.host_url.rstrip('/').encode())
        return flask.Response(content, mimetype='application/xml')


######################################################################################### mine

def timedelta_parse(value):
    """
    convert input string to timedelta
    """

    import re
    from datetime import timedelta

    value = re.sub(r"[^0-9:.]", "", value)
    if not value:
        return None

    return timedelta(**{key:float(val) for val, key in zip(value.split(":")[::-1], ("seconds", "minutes", "hours", "days"))})

def search_hidden_channels_hide(data, duration1, duration2):
    '''return list without filtered items'''
    tmp = data[:]
    tmp_removed = []
    hidden_videos = [z['id'] for z in local_playlist.read_playlist('search_hidden_videos')]
    hidden_channels = [z['author_id'] for z in local_playlist.read_playlist('search_hidden_channels')]

    for item in data:
        try:
            if (item['author_id'] in hidden_channels) or (item['id'] in hidden_videos):
                tmp.remove(item)
                tmp_removed.append({'id': item['id'], 'title': item['title']})
                continue

            if duration2 == '0' and duration1 == '0': continue
            elif len(duration2.split(':')) == 1: duration2 = duration2 + ":00"

            if duration1 != "0":
                duration2 = duration1

            video_duration = timedelta_parse(item['duration'])
            user_duration = timedelta_parse(duration2)
            if video_duration < user_duration:
                tmp.remove(item)
                tmp_removed.append({'id': item['id'], 'title': item['title']})
            elif user_duration == None:
                print(f"Bad input value {duration2} provided")
        except Exception as e:
            print(e)

    print(f" *{len(data) - len(tmp)}* hidden videos: {tmp_removed}")
    return tmp[:]


def get_search_json_and_extract(query, p, autocorrect, sort, filters):
    polymer_json = get_search_json(query, p, autocorrect, sort, filters)
    search_info = yt_data_extract.extract_search_info(polymer_json)
    if len(search_info['items']) == 0: return None
    return search_info

def joinall1(greenlets, timeout=None, raise_error=False, count=None):
    done = []
    for obj in gevent.wait(greenlets, timeout=timeout, count=count):
        if getattr(obj, 'exception', None) is not None:
            if hasattr(obj, '_raise_exception'):
                obj._raise_exception()
            else:
                raise obj.exception
        if obj.value == None: break
        done.append(obj)
    return done

def get_many_pages_as_one(query, page, autocorrect, sort, filters, page_multiplier=3):
    '''return a number of search results'''
    pages_list = list(range((int(page) * page_multiplier) - page_multiplier + 1, (int(page) * page_multiplier) + 1))
    search_info_tmp = {'error': None, 'estimated_results': 0, 'estimated_pages': 0, 'corrections': {'type': None}, 'items': []}

    # if dont want to use greenlets
    # for p in pages_list:
        # polymer_json = get_search_json(query, p, autocorrect, sort, filters)
        # search_info = yt_data_extract.extract_search_info(polymer_json)

    tasks = []
    for p in pages_list:
        tasks.append(gevent.spawn(get_search_json_and_extract, query, p, autocorrect, sort, filters))
    joinall1(tasks, raise_error=False)
    util.check_gevent_exceptions(*tasks)

    for t in tasks:
        search_info = t.value
        if search_info == None: break
        if search_info['error']:
            return flask.render_template('error.html', error_message = search_info['error'])

        for extract_item_info in search_info['items']:
            util.prefix_urls(extract_item_info)
            util.add_extra_html_info(extract_item_info)

        corrections = search_info['corrections']
        if corrections['type'] in ['did_you_mean', 'showing_results_for']:
            return search_info

        for k,v in search_info.items():
            if k != 'items': search_info_tmp[k] = v
            else: search_info_tmp['items'].extend(v)

    search_info = search_info_tmp
    search_info['estimated_pages'] = ceil(search_info['estimated_results']/(page_multiplier*20))
    return search_info

#########################################################################################
