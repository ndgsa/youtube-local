from youtube import util, yt_data_extract, proto, local_playlist
from youtube.channel import sort_video_items
from youtube import yt_app
import settings

import json
import urllib
import base64
import mimetypes
from flask import request
import flask
import os
import re
from datetime import datetime, timedelta
import gevent
import cachetools.func
from math import ceil

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

class HashableDict(dict):
    def __hash__(self):
        return hash(frozenset(self.items()))

g_search_id_results = []
g_last_page_list = []

def page_number_to_sp_parameter(page, autocorrect, sort, filters):
    #offset = (int(page) - 1)*50    # 20 results per page
    offset = (int(page) - 1)*20    # 20 results per page
    autocorrect = proto.nested(8, proto.uint(1, 1 - int(autocorrect) ))
    filters_enc = proto.nested(2, proto.uint(1, filters['time']) + proto.uint(2, filters['type']) + proto.uint(3, filters['duration']))
    result = proto.uint(1, sort) + filters_enc + autocorrect + proto.uint(9, offset) + proto.string(61, b'')
    return base64.urlsafe_b64encode(result).decode('ascii')

def get_search_json(query, page, autocorrect, sort, filters):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    headers = util.generate_api_headers(ua_platform='desktop', additional_headers=(('Host', 'www.youtube.com'),))
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
    filters = HashableDict()
    filters['time'] = int(request.args.get("time", "0"))
    filters['type'] = int(request.args.get("type", "0"))
    filters['duration'] = int(request.args.get("duration", "0"))

    if int(sort) == 100: sort = 0
    filters['reversed_order'] = request.args.get("reversed", None)
    filters['more_precise_query'] = request.args.get("precise", None)
    filters['duration1'] = request.args.get("duration1", "0")
    filters['date_after'] = request.args.get("date_after", "")
    filters['date_before'] = request.args.get("date_before", "")

    query_orig = query
    query = use_yt_search_operators(query, request.args, sort, filters)
    page_multiplier = 1

    if True:
        if filters['reversed_order']:
            search_info = get_many_pages_as_one_reversed(query, page, autocorrect, sort, filters, page_multiplier)
        else:
            search_info = get_many_pages_as_one(query, page, autocorrect, sort, filters, page_multiplier)
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

    search_info['items'] = filter_search_items(search_info['items'][:], query, page, request.url, request.args, sort, filters)

    return flask.render_template('search.html',
        header_playlist_names = local_playlist.get_playlist_names(),
        query = query_orig,
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



def use_yt_search_operators(query, request_args, sort, filters):
    '''return query string with search operators'''
    yt_search_operator = ""
    # use search operators like before/after
    if filters['time'] == 0: # Any
        if request_args.get("time", None) == None:
            filters['time'] = 0
    # elif filters['time'] == 1: # Last hour
        # yt_search_operator = f"after:{(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')}"
    # elif filters['time'] == 2: # Today
        # yt_search_operator = f"after:{(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')}"
    # elif filters['time'] == 3: # This week
        # yt_search_operator = f"after:{(datetime.now() - timedelta(days=8)).strftime('%Y-%m-%d')}"
    # elif filters['time'] == 4: # This month
        # yt_search_operator = f"after:{(datetime.now() - timedelta(days=32)).strftime('%Y-%m-%d')}"
    # elif filters['time'] == 5: # This year
        # yt_search_operator = f"after:{(datetime.now() - timedelta(days=367)).strftime('%Y-%m-%d')}"
    elif filters['time'] == 102: # last 2 days
        filters['time'] = 3
        filters['custom_time'] = 102
        yt_search_operator = f"after:{(datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')}"
    elif filters['time'] == 103: # last 3 days
        filters['time'] = 3
        filters['custom_time'] = 103
        yt_search_operator = f"after:{(datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')}"

    try:
        date_after = datetime.strptime(filters['date_after'], '%Y-%m-%d').strftime('%Y-%m-%d')
        yt_search_operator = f" after:{date_after}"
    except ValueError as e: pass
    try:
        date_before = datetime.strptime(filters['date_before'], '%Y-%m-%d').strftime('%Y-%m-%d')
        yt_search_operator = yt_search_operator + f" before:{date_before}"
    except ValueError as e: pass

    sort = int(request_args.get("sort", "100")) # use by default more precise search
    if int(sort) in [1,2,100] or filters['more_precise_query']: # upload date,relevance,rating returns many irrelevant results
        query = f"intitle:{query} OR description:{query} {yt_search_operator}".rstrip()
    else:
        query = f"{query} {yt_search_operator}".rstrip()

    return query


def filter_search_items(search_info_items, query, page, request_url, request_args, sort, filters):
    '''return filtered search items'''

    other_type_list = [item for item in search_info_items if item['type'] != 'video']
    # filter only video type items
    search_info_items = [item for item in search_info_items if item['type'] == 'video'][:]

    initial_length = len(search_info_items)

    # hide if in hidelist
    if settings.include_hidden_videos == False:
        search_info_items = search_hidden_channels_hide(search_info_items)
    # hide if duration
    search_info_items = filter_search_items_by_duration(search_info_items, filters['duration1'])
    # print(f" *{len(search_info_items) - len(search_info_items)}* hidden videos: {tmp_removed}")
    print(f" *{initial_length - len(search_info_items)}* hidden videos")

    # hide dublicates
    dublicates = []
    no_dublicates = []
    query_url_string_no_page = request_url.replace('&page=' + page, '')
    search_result_exist = False
    for i in g_search_id_results:
        if (query, query_url_string_no_page) == (i[0], i[1]):
            search_result_exist = True
            break
    if not search_result_exist: g_search_id_results.append((query, query_url_string_no_page, {}))
    for i in g_search_id_results:
        if (query, query_url_string_no_page) == (i[0], i[1]):
            if str(int(page)+1) in i[2]: i[2].clear() # if next page request empty dict
            i[2][page] = [] # empty if page already requested becouse results are different
            pages_ids_tmp = []
            [pages_ids_tmp.extend(p1) for p1 in list(i[2].values())]
            for item in search_info_items:
                if (item not in no_dublicates) and (item['id'] not in pages_ids_tmp):
                    no_dublicates.append(item)
                    i[2][page].append(item['id'])
                else: dublicates.append({'id': item['id'], 'title': item['title']})
            break
    # print(f" *{len(dublicates)}* dublicate videos: {dublicates}")
    print(f" *{len(dublicates)}* hidden dublicate videos")
    # no_dublicates = []
    # [no_dublicates.append(x) for x in search_info_items if x not in no_dublicates]
    search_info_items = no_dublicates[:]

    sort = int(request_args.get("sort", "100")) # use by default more precise search

    # sort items
    # old to new
    if int(sort) in [1,3] and filters['reversed_order']: search_info_items = sort_video_items(search_info_items, sort_key='approx_view_count', order=2)
    # youtube sort by views badly in some cases, so sort items manualy
    elif int(sort) in [1,3]: search_info_items = sort_video_items(search_info_items, sort_key='approx_view_count', order=1)
    # youtube filter by upload date is broken so sort page result by date
    if int(sort) in [2,100]: search_info_items = sort_video_items(search_info_items, sort_key='time_published', order=2)
    # relevance by date case
    if int(sort) == 0 and filters['time'] in [1,2]: search_info_items = sort_video_items(search_info_items, sort_key='time_published', order=2)

    return [*other_type_list, *search_info_items]


def timedelta_parse(value):
    """convert input string to timedelta"""
    value = re.sub(r"[^0-9:.]", "", value)
    if not value: return None
    return timedelta(**{key:float(val) for val, key in zip(value.split(":")[::-1], ("seconds", "minutes", "hours", "days"))})

def filter_search_items_by_duration(search_info_items, duration1):
    '''return list without filtered items'''
    tmp = search_info_items[:]
    tmp_removed = []
    for item in search_info_items:
        try:
            if duration1 == '0' or item.get('duration', None) == None: continue
            elif len(duration1.split(':')) == 1: duration1 = duration1 + ":00"
            video_duration = timedelta_parse(item['duration'])
            user_duration = timedelta_parse(duration1)
            if video_duration < user_duration:
                tmp.remove(item)
                tmp_removed.append({'id': item['id'], 'title': item['title']})
            elif user_duration == None:
                print(f"Bad input value {duration1} provided")
        except Exception as e:
            print(e)
    return tmp[:]


def search_hidden_channels_hide(search_info_items):
    '''return list without filtered items'''
    tmp = search_info_items[:]
    tmp_removed = []
    hidden_videos = [z['id'] for z in local_playlist.read_playlist('search_hidden_videos')]
    hidden_channels = [z['author_id'] for z in local_playlist.read_playlist('search_hidden_channels')]
    for item in search_info_items:
        try:
            if (item['author_id'] in hidden_channels) or (item['id'] in hidden_videos):
                tmp.remove(item)
                tmp_removed.append({'id': item['id'], 'title': item['title']})
        except Exception as e:
            print(e)
    return tmp[:]


def get_search_json_and_extract(query, page, autocorrect, sort, filters):
    polymer_json = get_search_json(query, page, autocorrect, sort, filters)
    search_info = yt_data_extract.extract_search_info(polymer_json)
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

@cachetools.func.ttl_cache(maxsize=99, ttl=10*60)
def get_many_pages_as_one(query, page, autocorrect, sort, filters, page_multiplier=3):
    '''return a number of search results'''
    pages_list = list(range((int(page) * page_multiplier) - page_multiplier + 1, (int(page) * page_multiplier) + 1))
    search_info_tmp = {'error': None, 'estimated_results': 0, 'estimated_pages': 0, 'corrections': {'type': None}, 'items': []}
    estimated_results_list = []

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

        estimated_results_list.append(search_info['estimated_results'])

    # case wheen last page return 0 estimated results
    estimated_results_list = list(dict.fromkeys(estimated_results_list))
    if len(estimated_results_list) > 1 and estimated_results_list[-1] == 0 and len(search_info_tmp['items']) != 0:
        search_info_tmp['estimated_results'] = estimated_results_list[-2]

    search_info = search_info_tmp
    search_info['estimated_pages'] = ceil(search_info['estimated_results']/(page_multiplier*20))
    return search_info


@cachetools.func.ttl_cache(maxsize=99, ttl=10*60)
def get_many_pages_as_one_reversed(query, page, autocorrect, sort, filters, page_multiplier=3):
    '''return a number of search results'''
    last_page, search_info = calculate_last_page(query, page, autocorrect, sort, filters)
    search_info_tmp = {'error': None, 'estimated_results': 0, 'estimated_pages': 0, 'corrections': {'type': None}, 'items': []}
    tasks = []

    if (not last_page) or (not search_info): return search_info_tmp
    elif search_info: estimated_results = search_info['estimated_results'] # store original estimated results

    # calculate last page numbers
    t_pages_list = list(range((int(page) * page_multiplier) - page_multiplier + 1, (int(page) * page_multiplier) + 1))
    pages_list = []
    for p in t_pages_list:
        page_number = 1 + last_page - p
        if page_number > 0:
            pages_list.append(1 + last_page - p)
        else: break

    # in case search_info exist use it
    if search_info and int(page) == 1:
        try: pages_list.remove(last_page)
        except ValueError: pass

    for p in pages_list:
        tasks.append(gevent.spawn(get_search_json_and_extract, query, p, autocorrect, sort, filters))
    joinall1(tasks, raise_error=False)
    util.check_gevent_exceptions(*tasks)

    if search_info and int(page) == 1:
        tasks.insert(0, search_info)

    for t in range(len(tasks)):
        if search_info and int(page) == 1 and t == 0 and isinstance(tasks[0], dict): search_info = tasks[0]
        else: search_info = tasks[t].value

        if search_info['error']:
            return flask.render_template('error.html', error_message = search_info['error'])

        for extract_item_info in search_info['items']:
            util.prefix_urls(extract_item_info)
            util.add_extra_html_info(extract_item_info)

        for k,v in search_info.items():
            if k != 'items': search_info_tmp[k] = v
            else: search_info_tmp['items'].extend(v)

    search_info = search_info_tmp
    search_info['estimated_pages'] = ceil(last_page/page_multiplier)
    search_info['estimated_results'] = estimated_results # last_page * 20
    return search_info


def calculate_last_page(query, page, autocorrect, sort, filters):
    '''return last page number'''
    global g_last_page_list # store params
    last_page = None
    search_info = None

    # check if last_page already requested
    for i in g_last_page_list:
        if (query, sort, filters) == (i[0], i[1], i[2]):
            if i[3] != None and i[4] != None: return i[3], i[4]
            elif i[3] == None: g_last_page_list.remove(i) # remove params to make new request
            break

    search_info = get_search_json_and_extract(query, 1, autocorrect, sort, filters) # request first page
    estimated_pages = ceil(search_info['estimated_results']/(20))

    if estimated_pages == 0 or len(search_info) == 0: # stop requesting if nothing available
        return None, None
    elif estimated_pages == 1: # if 1 page available use it
        last_page = estimated_pages
    else:
        retries = 2
        while retries > 0:
            search_info = get_search_json_and_extract(query, estimated_pages, autocorrect, sort, filters)
            if len(search_info['items']) > 0:
                last_page = estimated_pages # last page
                break
            if abs(ceil(search_info['estimated_results']/(20)) - estimated_pages) != 0:
                estimated_pages = ceil(search_info['estimated_results']/(20))
            else:
                search_info = None # if same estimated_results
                break
            retries = retries - 1

    g_last_page_list.append((query, sort, filters, last_page, search_info))
    return last_page, search_info

