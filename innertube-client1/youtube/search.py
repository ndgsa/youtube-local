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

    filters['reversed_order'] = request.args.get("reversed", None)

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



def filter_search_items(search_info_items, query, page, request_url, request_args, sort, filters):
    '''return filtered search items'''
    other_type_list = [item for item in search_info_items if item['type'] != 'video']
    # filter only video type items
    search_info_items = [item for item in search_info_items if item['type'] == 'video'][:]
    initial_length = len(search_info_items)
    # hide if in hidelist
    if settings.include_hidden_videos == False:
        search_info_items = search_hidden_channels_hide(search_info_items)
    # print(f" *{len(search_info_items) - len(search_info_items)}* hidden videos: {tmp_removed}")
    print(f" *{initial_length - len(search_info_items)}* hidden videos")
    return [*other_type_list, *search_info_items]


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

