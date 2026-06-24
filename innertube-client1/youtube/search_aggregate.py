from youtube import local_playlist, subscriptions
from youtube import search as search_module
from youtube import yt_app
import settings

import json
import time
from datetime import datetime, timedelta
import re
from threading import Thread
import traceback

import flask
from flask import request

status_aggregate = {'stop': False, 'status': None, 'is_last': None}



def normalize_approx_view_count(string):
    if string in [None, '', 'null', 'none', ' ']: return '0'
    view_count_multiplier = {'S': 1, 'K': 1000, 'M': 1000000, 'B': 1000000000}
    if string[-1].isalpha() and not string[:-1].isalpha(): multiplier = float(string[:-1]) * view_count_multiplier[string[-1]]
    elif not string.isalpha(): multiplier = int(string) * view_count_multiplier['S']
    else: multiplier = '0' # if string is None
    return multiplier

def update_approx_view_count_for_db_items(search_info):
    updating_list = {}
    '''update approx_view_count'''
    for p_n in local_playlist.get_playlist_names():
        if re.match(r"^sa_\s.+\s\-\s\d+\s(Days|Weeks|Months)$", p_n):
            for pairs in local_playlist.video_ids_in_playlist(p_n, 'id, approx_view_count'):
                for item in search_info['items']:
                    if pairs['id'] == item['id']:
                        if normalize_approx_view_count(str(pairs['approx_view_count'])) < normalize_approx_view_count(str(item['approx_view_count'])):
                            if p_n not in updating_list:
                                updating_list[p_n] = []
                            updating_list[p_n].append({pairs['id']: str(item['approx_view_count'])})

    for k,v in updating_list.items():
        local_playlist.update_video_column(k, 'approx_view_count', v)


def filter_search_items(search_info_items, sort, filters):
    '''return filtered search items'''

    # filter only video type items
    search_info_items = [item for item in search_info_items if item['type'] == 'video'][:]

    initial_length = len(search_info_items)

    # hide if in hidelist
    if settings.include_hidden_videos == False:
        search_info_items = search_module.search_hidden_channels_hide(search_info_items)
    # hide if duration
    search_info_items = search_module.filter_search_items_by_duration(search_info_items, filters['duration1'])
    # print(f" *{len(search_info_items) - len(search_info_items)}* hidden videos: {tmp_removed}")
    print(f" *{initial_length - len(search_info_items)}* hidden videos")

    # hide dublicates
    dublicates = []
    no_dublicates = []
    seen = set()
    for item in search_info_items:
        if item['id'] not in seen:
            no_dublicates.append(item)
            seen.add(item['id'])
    print(f" *{len(search_info_items) - len(no_dublicates)}* hidden dublicate videos")
    search_info_items = no_dublicates[:]

    return search_info_items


def process_search_results(playlist_name, search_info_tmp, sort, filters):
    global status_aggregate

    try:

        update_approx_view_count_for_db_items(search_info_tmp)

        search_info_tmp['items'] = filter_search_items(search_info_tmp['items'][:], sort, filters)

        tmp = []
        for item in search_info_tmp['items']:
            # Convert yt dumb timestamp to normal. Very imprecise.
            try: item['time_published'] = datetime.fromtimestamp(subscriptions.youtube_timestamp_to_posix(item['time_published'])).strftime('%Y-%m-%d')
            except: pass

            # Convert item to json
            tmp.append(json.dumps({key: item[key] for key in [
                'id', 'title', 'author', 'author_id', 'duration', 'approx_view_count', 'time_published']}))
        search_info_tmp['items'] = tmp[:]

        print(f"Add {len(search_info_tmp['items'])} items to db.")
        local_playlist.add_to_playlist(playlist_name, search_info_tmp['items'])

    except Exception as e:
        status_aggregate['stop'] = True
        status_aggregate['status'] = 'An error occurred while processing the results. Abort searching!'
        traceback.print_exc()


def generate_date_ranges(filters):
    global status_aggregate

    def chunks_days(lst, n):
        for i in range(0, len(lst), n-1): # range(0, len(lst), n):
            yield [(date_before - timedelta(days=j)).strftime('%Y-%m-%d') for j in lst[i:i + n]]

    date_step = int(filters['date_step'])
    date_step_type = filters['date_step_type']
    # Convert string to date object
    date_before = datetime.strptime(filters['date_before'], "%Y-%m-%d").date() + timedelta(days=1)
    date_after = datetime.strptime(filters['date_after'], "%Y-%m-%d").date()
    date_substracted = (date_before - date_after).days

    if date_substracted <= 1 or abs(date_step) == 0:
        status_aggregate['status'] = f'Error! Date after is newer than date before.'
        print(status_aggregate['status'])
        status_aggregate['stop'] = True
        return []

    date_ranges = []
    if date_step_type == 'Days':
        chunks = list(chunks_days(range(0, date_substracted + 1), date_step + 1))
    elif date_step_type == 'Weeks':
        chunks = list(chunks_days(range(0, date_substracted + 1), (7 * date_step) + 1))
    elif date_step_type == 'Months':
        chunks = list(chunks_days(range(0, date_substracted + 1), (31 * date_step) + 1))
    else: NotImplementedError('Unknown date step type:', date_step_type)

    for chunk in chunks:
        if chunk[0] != chunk[-1]:
            date_ranges.append([chunk[0], chunk[-1]])
        else:
            trick_date = (datetime.strptime(chunk[0], "%Y-%m-%d").date() - timedelta(days=1)).strftime('%Y-%m-%d')
            date_ranges.append([chunk[0], trick_date])

    return date_ranges


def task_aggregate(query, page, autocorrect, sort, filters):
    global status_aggregate

    orig_query = query
    page_multiplier = settings.search_request_page_multiplier
    playlist_name = f"sa_ {orig_query} {filters['date_after']} - {filters['date_before']} - {filters['date_step']} {filters['date_step_type']}"

    date_ranges = generate_date_ranges(filters)
    for d in date_ranges:
        if status_aggregate['stop']: break

        yt_search_operator = ""
        try:
            date_after = datetime.strptime(d[-1], '%Y-%m-%d').strftime('%Y-%m-%d')
            yt_search_operator = f" after:{date_after}"
        except ValueError as e: pass
        try:
            date_before = datetime.strptime(d[0], '%Y-%m-%d').strftime('%Y-%m-%d')
            yt_search_operator = yt_search_operator + f" before:{date_before}"
        except ValueError as e: pass

        if int(sort) in [1,2,100] or filters['more_precise_query']:
            query = f"intitle:{orig_query} OR description:{orig_query} {yt_search_operator}".rstrip()
        else:
            query = f"{orig_query} {yt_search_operator}".rstrip()

        estimated_pages = 1
        page = 1
        search_info_tmp = {'error': None, 'estimated_results': 0, 'estimated_pages': 0, 'corrections': {'type': None}, 'items': []}
        while estimated_pages > 0:
            if status_aggregate['stop']: break

            try:
                search_info = search_module.get_many_pages_as_one(query, page, autocorrect, 0 if int(sort) == 100 else int(sort), filters, page_multiplier)
            except Exception as e:
                status_aggregate['status'] = f"{orig_query} {date_after} - {date_before} page:{page} ERROR!"
                print(status_aggregate['status'])
                break

            if search_info['corrections']['type'] in ['did_you_mean', 'showing_results_for']:
                status_aggregate['status'] = f"{orig_query} {date_after} - {date_before} page:{page} Query corrections???"
                print(status_aggregate['status'])

            estimated_pages = search_info['estimated_pages']
            estimated_results = search_info['estimated_results']
            for item in search_info['items']: item['time_published'] = date_before
            search_info_tmp['items'].extend(search_info['items'])
            status_aggregate['status'] = f"{orig_query} {date_after} - {date_before} estimated_pages:{search_info['estimated_pages']} page:{page} items:{len(search_info['items'])}"
            print(status_aggregate['status'])

            if len(search_info['items']) == 0 or estimated_pages <= page: break
            else: page += 1
            time.sleep(1)

        process_search_results(playlist_name, search_info_tmp, sort, filters)

        time.sleep(5) # Add some delay

    # sort playlist
    if int(sort) in [0, 100]:
        status_aggregate['status'] = f'Sort playlist by newest'
        print(status_aggregate['status'])
        local_playlist.sort_database_playlist(playlist_name, '3', None, False) # sort by newest
    else:
        status_aggregate['status'] = f'Sort playlist by max view_count'
        print(status_aggregate['status'])
        local_playlist.sort_database_playlist(playlist_name, '1', None, False) # sort by max view_count

    status_aggregate['stop'] = True
    # status_aggregate['status'] = None


@yt_app.route('/search_aggregate')
def get_search_aggregate_page():
    return flask.render_template('search_aggregate.html',)

@yt_app.route('/start_searching', methods=['POST'])
def start_searching():
    global status_aggregate

    query = request.values.get("search_query", "") or request.values.get("query", "")
    page = request.values.get("page", "1")
    autocorrect = int(request.values.get("autocorrect", "1"))
    sort = int(request.values.get("sort", "0"))
    filters = search_module.HashableDict()
    filters['time'] = int(request.values.get("time", "0"))
    filters['type'] = int(request.values.get("type", "0"))
    filters['duration'] = int(request.values.get("duration", "0"))

    filters['reversed_order'] = request.values.get("reversed", None)
    filters['more_precise_query'] = request.values.get("precise", None)
    filters['duration1'] = request.values.get("duration1", "0")
    filters['date_after'] = request.values.get("date_after", "")
    filters['date_before'] = request.values.get("date_before", "")
    filters['date_step'] = request.values.get("date_step", "")
    filters['date_step_type'] = request.values.get("date_step_type", "")

    if '' in [query.strip(), filters['date_step'], filters['date_step_type'], filters['date_after'], filters['date_before']]:
        status_aggregate['stop'] = True
        return 'Invalid search params', 400

    if status_aggregate['status'] != None: return 'Wait until current task is finished!', 400

    status_aggregate['status'] = 'Starting...'
    status_aggregate['stop'] = False

    t1 = Thread(target=task_aggregate, args=[query, 1, autocorrect, sort, filters])
    t1.start()

    return 'START', 204

@yt_app.route('/terminate_searching', methods=['POST'])
def terminate_searching():
    global status_aggregate
    status_aggregate['stop'] = True
    return 'OK', 204

@yt_app.route('/status_searching', methods=['GET'])
def status_searching():
    global status_aggregate
    if status_aggregate['stop'] and status_aggregate['status']:
        statusList = {'status': status_aggregate['status']}
        status_aggregate['status'] = None
    elif status_aggregate['stop']: statusList = {'status': 'done', 'terminated': status_aggregate['stop']}
    else: statusList = {'status': status_aggregate['status']}
    return json.dumps(statusList)

