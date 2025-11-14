from youtube import util, yt_data_extract
from youtube import yt_app
import settings

import os
import json
import html
import gevent
import urllib
import math

import flask
from flask import request

playlists_directory = os.path.join(settings.data_dir, "playlists")
thumbnails_directory = os.path.join(settings.data_dir, "playlist_thumbnails")

def video_ids_in_playlist(name):
    try:
        with open(os.path.join(playlists_directory, name + ".txt"), 'r', encoding='utf-8') as file:
            videos = file.read()
            import sys
        ## mine # gives error if History playlist is empty, to bypass error just delete History playlist
        return set(json.loads(video)['id'] for video in videos.splitlines())
    except FileNotFoundError:
        return set()

def add_to_playlist(name, video_info_list):
    if not os.path.exists(playlists_directory):
        os.makedirs(playlists_directory)
    ids = video_ids_in_playlist(name)
    missing_thumbnails = []

    ################################################################## mine
    if name in ["related_hidden_channels", "search_hidden_channels"]:
        from youtube import channel

        def video_authors_id_in_playlist(name):
            try:
                with open(os.path.join(playlists_directory, name + ".txt"), 'r', encoding='utf-8') as file:
                    videos = file.read()
                    import sys
                ## mine # gives error if History playlist is empty, to bypass error just delete History playlist
                return set(json.loads(video)['author_id'] for video in videos.splitlines())
            except FileNotFoundError:
                return set()

        authors_id = video_authors_id_in_playlist(name)

        with open(os.path.join(playlists_directory, name + ".txt"), "a", encoding='utf-8') as file:
            for info in video_info_list:

                # replace id with author_id becouse need avatar for channel not for video
                tmp = json.loads(info)
                author_id = tmp['author_id']
                tmp['id'] = tmp['author_id']

                # if video is deleted from youtube than extracted values will be null and will break the playlist
                if author_id == None:
                    continue

                # get channel metadata that includes avatar url
                tasks = (gevent.spawn(channel.get_metadata, author_id),)
                gevent.joinall(tasks)
                util.check_gevent_exceptions(*tasks)
                tmp.update(tasks[0].value)

                if author_id not in authors_id:
                    info = json.dumps(tmp)
                    file.write(info + "\n")

                url = tmp['avatar']
                save_location = os.path.join(os.path.join(thumbnails_directory, name), author_id + ".jpg")
                try:
                    thumbnail = util.fetch_url(url, report_text="Saved thumbnail: " + author_id)
                except urllib.error.HTTPError as e:
                    print("Failed to download thumbnail for " + author_id + ": " + str(e))
                    continue
                try:
                    f = open(save_location, 'wb')
                except FileNotFoundError:
                    os.makedirs(os.path.join(thumbnails_directory, name), exist_ok = True)
                    f = open(save_location, 'wb')
                f.write(thumbnail)
                f.close()

        return

    # if video exist in history playlist, move it to start, so it will look as recent video
    if name == "History":
        for info in video_info_list:
            id = json.loads(info)['id']

            # if video is deleted from youtube than extracted values will be null and will break the playlist
            if id == None:
                continue

            if id in ids:
                with open(os.path.join(playlists_directory, name + ".txt"), "r+") as f:
                    d = f.readlines()[:]
                    f.seek(0)
                    f.truncate()
                    d.append(d.pop(d.index(info + "\n") ))
                    for gg in d:
                       f.write(gg)
            break

    ##################################################################

    with open(os.path.join(playlists_directory, name + ".txt"), "a", encoding='utf-8') as file:
        for info in video_info_list:
            id = json.loads(info)['id']

            # mine
            # if video is deleted from youtube than extracted values will be null and will break the playlist
            if id == None:
                continue

            if id not in ids:
                file.write(info + "\n")
                missing_thumbnails.append(id)
    gevent.spawn(util.download_thumbnails, os.path.join(thumbnails_directory, name), missing_thumbnails)


def add_extra_info_to_videos(videos, playlist_name):
    '''Adds extra information necessary for rendering the video item HTML

    Downloads missing thumbnails'''
    try:
        thumbnails = set(os.listdir(os.path.join(thumbnails_directory,
                                                 playlist_name)))
    except FileNotFoundError:
        thumbnails = set()
    missing_thumbnails = []

    for video in videos:
        video['type'] = 'video'
        util.add_extra_html_info(video)
        if video['id'] + '.jpg' in thumbnails:
            video['thumbnail'] = (
                '/https://youtube.com/data/playlist_thumbnails/'
                + playlist_name
                + '/' + video['id'] + '.jpg')
        # mine
        elif playlist_name in ["related_hidden_channels", 'search_hidden_channels']:
                import re
                url = re.sub(r'\=s(\d{3,4})-', '=s200-', video['avatar']) # 900px is too big
                save_location = os.path.join(os.path.join(thumbnails_directory, playlist_name), video['author_id'] + ".jpg")
                try:
                    thumbnail = util.fetch_url(url, report_text="Saved thumbnail: " + video['author_id'])
                except urllib.error.HTTPError as e:
                    print("Failed to download thumbnail for " + video['author_id'] + ": " + str(e))
                    continue
                try:
                    f = open(save_location, 'wb')
                except FileNotFoundError:
                    os.makedirs(os.path.join(thumbnails_directory, playlist_name), exist_ok = True)
                    f = open(save_location, 'wb')
                f.write(thumbnail)
                f.close()
                if video['id'] + '.jpg' in thumbnails:
                    video['thumbnail'] = (
                        '/https://youtube.com/data/playlist_thumbnails/'
                        + playlist_name + '/' + video['id'] + '.jpg')
        else:
            video['thumbnail'] = util.get_thumbnail_url(video['id'])
            missing_thumbnails.append(video['id'])

    gevent.spawn(util.download_thumbnails,
                 os.path.join(thumbnails_directory, playlist_name),
                 missing_thumbnails)


def read_playlist(name):
    '''Returns a list of videos for the given playlist name'''
    playlist_path = os.path.join(playlists_directory, name + '.txt')

    # mine
    # need to create empty file if it not exist
    if not os.path.isfile(playlist_path):
        if not os.path.exists(playlists_directory):
            os.makedirs(playlists_directory)
        with open(playlist_path, 'a') as file: pass

    with open(playlist_path, 'r', encoding='utf-8') as f:
        data = f.read()

    videos = []
    videos_json = data.splitlines()
    for video_json in videos_json:
        try:
            info = json.loads(video_json)
            videos.append(info)
        except json.decoder.JSONDecodeError:
            if not video_json.strip() == '':
                print('Corrupt playlist video entry: ' + video_json)
    return videos


def get_local_playlist_videos(name, offset=0, amount=50):
    videos = read_playlist(name)

    ## mine
    # reverse list, last added will be recent
    # if name == "History":
        # videos = videos[::-1]
    if settings.sort_playlist: videos = videos[::-1]

    add_extra_info_to_videos(videos, name)
    return videos[offset:offset+amount], len(videos)


def get_playlist_names():
    try:
        items = os.listdir(playlists_directory)
    except FileNotFoundError:
        return []

    tmp = []
    for item in items:
        name, ext = os.path.splitext(item)
        ## mine
        if ext == '.txt' and (name not in ["History", "0youtube_playlist_list"]):
            # yield name
            tmp.append(name)
    return tmp

def remove_from_playlist(name, video_info_list):
    ids = [json.loads(video)['id'] for video in video_info_list]
    with open(os.path.join(playlists_directory, name + ".txt"), 'r', encoding='utf-8') as file:
        videos = file.read()
    videos_in = videos.splitlines()
    videos_out = []
    for video in videos_in:
        if json.loads(video)['id'] not in ids:
            videos_out.append(video)
    with open(os.path.join(playlists_directory, name + ".txt"), 'w', encoding='utf-8') as file:
        file.write("\n".join(videos_out) + "\n")

    try:
        thumbnails = set(os.listdir(os.path.join(thumbnails_directory, name)))
    except FileNotFoundError:
        pass
    else:
        to_delete = thumbnails & set(id + ".jpg" for id in ids)
        for file in to_delete:
            os.remove(os.path.join(thumbnails_directory, name, file))

    # mine
    # remove empty/blank lines from file becouse they cause errors
    with open(os.path.join(playlists_directory, name + ".txt")) as reader, open(os.path.join(playlists_directory, name + ".txt"), 'r+') as writer:
        for line in reader:
            if line.strip(): writer.write(line)
        writer.truncate()

    return len(videos_out)


@yt_app.route('/playlists', methods=['GET'])
@yt_app.route('/playlists/<playlist_name>', methods=['GET'])
def get_local_playlist_page(playlist_name=None):
    # mine
    if playlist_name == "hidden_videos_channels":
        playlists = [(name, util.URL_ORIGIN + '/playlists/' + name) for name in get_playlist_names() if name in ["related_hidden_channels", "search_hidden_channels", "related_hidden_videos", "search_hidden_videos"]]
        return flask.render_template('local_playlists_list.html', playlists=playlists)

    if playlist_name is None:
        playlists = [(name, util.URL_ORIGIN + '/playlists/' + name) for name in get_playlist_names() if name not in ["related_hidden_channels", "search_hidden_channels", "related_hidden_videos", "search_hidden_videos"]] + [("hidden_videos_channels", util.URL_ORIGIN + '/playlists/' + "hidden_videos_channels")] + youtube_playlists_from_local(action='get') # mine
        return flask.render_template('local_playlists_list.html', playlists=playlists)
    else:
        page = int(request.args.get('page', 1))
        offset = 50*(page - 1)
        videos, num_videos = get_local_playlist_videos(playlist_name, offset=offset, amount=50)
        return flask.render_template('local_playlist.html',
            header_playlist_names = get_playlist_names(),
            playlist_name = playlist_name,
            videos = videos,
            num_pages = math.ceil(num_videos/50),
            parameters_dictionary = request.args,
            display_as_grid = settings.display_as_grid, #mine
        )


@yt_app.route('/playlists/<playlist_name>', methods=['POST'])
def path_edit_playlist(playlist_name):
    '''Called when making changes to the playlist from that playlist's page'''
    if request.values['action'] == 'remove':
        videos_to_remove = request.values.getlist('video_info_list')
        number_of_videos_remaining = remove_from_playlist(playlist_name, videos_to_remove)
        redirect_page_number = min(int(request.values.get('page', 1)), math.ceil(number_of_videos_remaining/50))
        return flask.redirect(util.URL_ORIGIN + request.path + '?page=' + str(redirect_page_number))
    elif request.values['action'] == 'remove_playlist':
        try:
            os.remove(os.path.join(playlists_directory, playlist_name + ".txt"))
        except OSError:
            pass
        return flask.redirect(util.URL_ORIGIN + '/playlists')
    elif request.values['action'] == 'export':

        # mine
        if request.values.get('export_youtube_playlist', None) == 'true':
            videos = [json.loads(v) for v in get_all_videos_from_playlist(request.values['playlist_id'])]
        else: videos = read_playlist(playlist_name)

        fmt = request.values['export_format']
        if fmt in ('ids', 'urls'):
            prefix = ''
            if fmt == 'urls':
                prefix = 'https://www.youtube.com/watch?v=' if playlist_name not in ["related_hidden_channels", "search_hidden_channels"] else 'https://www.youtube.com/channel/' # mine
            id_list = '\n'.join(prefix + v['id'] for v in videos)
            id_list += '\n'
            resp = flask.Response(id_list, mimetype='text/plain')
            # cd = 'attachment; filename="%s.txt"' % playlist_name
            cd = 'attachment; ' + 'filename*=' + "UTF-8''%s.txt" % urllib.parse.quote(playlist_name) # mine
            resp.headers['Content-Disposition'] = cd
            return resp
        elif fmt == 'json':
            json_data = json.dumps({'videos': videos}, indent=2,
                                   sort_keys=True)
            resp = flask.Response(json_data, mimetype='text/json')
            # cd = 'attachment; filename="%s.json"' % playlist_name
            cd = 'attachment; ' + 'filename*=' + "UTF-8''%s.json" % urllib.parse.quote(playlist_name) # mine
            resp.headers['Content-Disposition'] = cd
            return resp
        elif fmt == 'key_value_dict':
            tmp = []
            for item in videos:
                video_info = {}
                kz = []
                if playlist_name not in ['related_hidden_channels', 'search_hidden_channels']: kz = ['id', 'title', 'author', 'author_id', 'duration']
                else: kz = ['id', 'title', 'author', 'author_id', 'duration', 'approx_subscriber_count', 'short_description', 'channel_name', 'avatar']
                for key in kz:
                    try: video_info[key] = item[key]
                    except KeyError: video_info[key] = None
                tmp.append(json.dumps(video_info))
            id_list = '\n'.join(f"{v}" for v in tmp)
            id_list += '\n'
            resp = flask.Response(id_list, mimetype='text/plain')
            # cd = 'attachment; filename="%s.txt"' % playlist_name
            cd = 'attachment; ' + 'filename*=' + "UTF-8''%s.txt" % urllib.parse.quote(playlist_name)
            resp.headers['Content-Disposition'] = cd
            return resp
        else:
            flask.abort(400)
    ## mine
    elif request.values['action'] == 'import':
        import_videos_to_playlist(playlist_name, request)
        return flask.redirect(util.URL_ORIGIN + '/playlists/'+ playlist_name, 303)
    else:
        flask.abort(400)


@yt_app.route('/edit_playlist', methods=['POST'])
def edit_playlist():
    '''Called when adding videos to a playlist from elsewhere'''

    #mine
    if request.values['playlist_name'] == 'History' and settings.disable_history:
        flask.abort(400)
        return

    #mine
    if request.values.get('bookmark_playlist', None) == 'true':
        if request.values['playlist_name'] == '' or request.values['playlist_url'] == '':
            print('Incorrect playlist data provided')
            return '', 204
        data = {'playlist_name': request.values['playlist_name'], 'playlist_url': request.values['playlist_url']}
        if request.values['action'] == 'add':
            youtube_playlists_from_local(action='add', data=data)
            return '', 204
        elif request.values['action'] == 'remove':
            youtube_playlists_from_local(action='remove', data=data)
            return '', 204
        else:
            flask.abort(400)

    if request.values['action'] == 'add':
        add_to_playlist(request.values['playlist_name'], request.values.getlist('video_info_list'))
        return '', 204
    else:
        flask.abort(400)

@yt_app.route('/data/playlist_thumbnails/<playlist_name>/<thumbnail>')
def serve_thumbnail(playlist_name, thumbnail):
    # .. is necessary because flask always uses the application directory at ./youtube, not the working directory
    return flask.send_from_directory(os.path.join('..', thumbnails_directory, playlist_name), thumbnail)


def import_videos_to_playlist(playlist_name, request):

    # check if the post request has the file part
    if 'videos_file' not in request.files:
        #flash('No file part')
        return flask.redirect(util.URL_ORIGIN + request.full_path)
    file = request.files['videos_file']
    # if user does not select file, browser also
    # submit an empty part without filename
    if file.filename == '':
        #flash('No selected file')
        return flask.redirect(util.URL_ORIGIN + request.full_path)

    mime_type = file.mimetype

    if mime_type == 'text/plain':
        list_video_ids = []
        list_video_url = [line.decode('utf-8').rstrip() for line in file]

        ids = video_ids_in_playlist(playlist_name) # mine

        import urllib.parse as urlparse
        import re

        # mine
        # if .txt contains dicts
        if all(x in list_video_url[0] for x in ["id", "title", "author", "author_id", "duration"]):
            add_to_playlist(playlist_name, list_video_url)
            return

        for url in list_video_url:
            try:
                query = urlparse.urlparse(url.strip())
                if 'youtube' in query.hostname:
                    if query.path == '/watch':
                        video_id = urlparse.parse_qs(query.query)['v'][0]
                    elif query.path.startswith(('/embed/', '/v/', '/channel/')): # mine
                        video_id = query.path.split('/')[2]
                elif 'youtu.be' in query.hostname:
                    video_id = query.path[1:]
                else:
                    video_id = None

                if not video_id or len(video_id) < 11:
                    print(f"Incorect videoid from url: {url.strip()}")
                    continue

                if video_id not in ids:
                    list_video_ids.append(video_id)
            except Exception as e:
                if re.match(r"^[A-Za-z0-9_\-]{11}$", url) or re.match(r"^UC[A-Za-z0-9_\-]{22}$", url):
                    video_id = url
                    if video_id not in ids: list_video_ids.append(video_id)
                else:
                    print(f"Error on importing url videos from text file: {e}")

        # import_slow(playlist_name, request, list_video_ids) # mine
        import_faster_with_ip_ban1(playlist_name, request, list_video_ids) # mine

    return


############################################################# mine

def import_faster_with_ip_ban1(playlist_name, request, list_video_ids):

    # if there are too many items to import google can ban ip
    # so import elements by chunks of 50 items with delay 10 minutes

    from youtube import channel
    from time import sleep

    def chunks(xs, n):
        n = max(1, n)
        return (xs[i:i+n] for i in range(0, len(xs), n))

    list_video_ids_chunks = list(chunks(list_video_ids, 5)) # 5 elements per chunk

    for list_chunk in list_video_ids_chunks:

        tasks = []
        for video_id in list_chunk:
            use_invidious = bool(int(request.args.get('use_invidious', '1')))
            if playlist_name in ['related_hidden_channels', 'search_hidden_channels']:
                tasks.append(gevent.spawn(channel.get_metadata, video_id))
            else:
                tasks.append(gevent.spawn(extract_info_mini2, video_id, use_invidious, playlist_id=None, index=None),)

        # only do 5 at a time
        # do the n where n is divisible by 5
        i = -1
        for i in range(0, int(len(tasks)/5) - 1 ):
            gevent.joinall([tasks[j] for j in range(i*5, i*5 + 5)])
        # do the remainders (< 5)
        gevent.joinall([tasks[j] for j in range(i*5 + 5, len(tasks))])
        try: util.check_gevent_exceptions(tasks[0])
        except: pass

        tmp = []
        for i, video_id in enumerate(list_chunk):
            if tasks[i].value == None: continue
            info = tasks[i].value
            if playlist_name in ['related_hidden_channels', 'search_hidden_channels']:
                info['id'] = video_id
                info['author_id'] = video_id
                info['error'] = None
                info['duration'] = 0
                info['title'] = None
                info['author'] = info['channel_name']

            if not info['error']:
                video_info = {
                    'duration':  util.seconds_to_timestamp(info['duration'] or 0),
                    'id':        info['id'],
                    'title':     info['title'],
                    'author':    info['author'],
                    'author_id': info['author_id'],
                }

                print(f"Add video '{video_id}' to playlist '{playlist_name}' with success.")
                tmp.append(json.dumps(video_info))
        add_to_playlist(playlist_name, tmp)

        sleep(2)


# i use methods from not innertube github fork and remove some lines to minimize amount of requests
def extract_info_mini2(video_id, use_invidious, playlist_id=None, index=None):

    def fetch_watch_page_info(video_id, playlist_id, index):
        # bpctr=9999999999 will bypass are-you-sure dialogs for controversial
        # videos
        url = 'https://m.youtube.com/embed/' + video_id + '?bpctr=9999999999'
        if playlist_id:
            url += '&list=' + playlist_id
        if index:
            url += '&index=' + index

        headers = (
            ('Accept', '*/*'),
            ('Accept-Language', 'en-US,en;q=0.5'),
            ('X-YouTube-Client-Name', '2'),
            ('X-YouTube-Client-Version', '2.20180830'),
        ) + util.mobile_ua

        watch_page = util.fetch_url(url, headers=headers,
                                    debug_name='watch')
        watch_page = watch_page.decode('utf-8')
        return yt_data_extract.extract_watch_info_from_html(watch_page)

    tasks = (gevent.spawn(fetch_watch_page_info, video_id, playlist_id, index),)
    gevent.joinall(tasks)
    util.check_gevent_exceptions(*tasks)
    info = tasks[0].value
    return info


def get_all_videos_from_playlist(playlist_id):
    if not playlist_id: return []

    from youtube.playlist import (playlist_first_page, get_videos)

    first_page_json = playlist_first_page(playlist_id)
    info = yt_data_extract.extract_playlist_info(first_page_json)
    # some playlist does not give items for first page
    if len(info.get('items', [])) == 0:
        info = yt_data_extract.extract_playlist_info(get_videos(playlist_id, 1))

    if info['error']:
        print('Error on extracting items.')
        return []

    items = info['items']
    video_count = yt_data_extract.deep_get(info, 'metadata', 'video_count')
    if video_count is None: return []
    num_pages = math.ceil(video_count/100)
    # print(video_count, num_pages)

    tasks = []
    for p in range(2, num_pages+1):
        tasks.append(gevent.spawn(get_videos, playlist_id, p))
    tasks = tuple(tasks)
    gevent.joinall(tasks)
    util.check_gevent_exceptions(*tasks)
    for t in tasks:
        info = yt_data_extract.extract_playlist_info(t.value)
        if info['error']:
            print('Error on extracting items.')
            return []
        items.extend(info['items'])

    tmp = []
    for item in items:
        video_info = {}
        for key in ('id', 'title', 'author', 'author_id', 'duration'):
            try: video_info[key] = item[key]
            except KeyError: video_info[key] = None

        tmp.append(json.dumps(video_info))

    return tmp


def youtube_playlists_from_local(playlist_name='0youtube_playlist_list', action='get', data={}):

    if not os.path.exists(playlists_directory):
        os.makedirs(playlists_directory)

    playlist_list = []
    playlist_list_formated = []

    try:
        with open(os.path.join(playlists_directory, playlist_name + ".txt"), 'r', encoding='utf-8') as file: yt_playlists = file.read()
        for yt_playlist in yt_playlists.splitlines():
            if yt_playlist.strip():
                playlist = json.loads(yt_playlist)
                playlist_list.append(playlist)
                playlist_list_formated.append(('(*) ' + playlist['playlist_name'], '/' + playlist['playlist_url']))
    except FileNotFoundError:
        with open(os.path.join(playlists_directory, playlist_name + ".txt"), 'a') as file: pass
        return []

    if action == 'get': return playlist_list_formated
    elif action == 'add' and data != {}:
        if data not in playlist_list:
            with open(os.path.join(playlists_directory, playlist_name + ".txt"), "a", encoding='utf-8') as file:
                file.write(json.dumps(data) + "\n")
    elif action == 'remove' and data != {}:
        try: playlist_list.remove(data)
        except ValueError: pass

        with open(os.path.join(playlists_directory, playlist_name + ".txt"), 'w', encoding='utf-8') as file:
            for i in playlist_list: file.write(json.dumps(i) + "\n")

        with open(os.path.join(playlists_directory, playlist_name + ".txt")) as reader, open(os.path.join(playlists_directory, playlist_name + ".txt"), 'r+') as writer:
            for line in reader:
                if line.strip(): writer.write(line)
            writer.truncate()


@yt_app.route('/playlists/History', methods=['GET'])
def get_local_history_page():
    ##return flask.render_template('error.html')

    page = int(request.args.get('page', 1))
    offset = 50*(page - 1)
    videos, num_videos = get_local_playlist_videos("History", offset=offset, amount=50)
    return flask.render_template('local_playlist.html',
        header_playlist_names = get_playlist_names(),
        playlist_name = "History",
        videos = videos,
        num_pages = math.ceil(num_videos/50),
        parameters_dictionary = request.args,
        display_as_grid = settings.display_as_grid,
        disable_history = settings.disable_history,
    )


@yt_app.route('/playlists/search_hidden_channels', methods=['GET'])
@yt_app.route('/playlists/related_hidden_channels', methods=['GET'])
def get_local_related_hidden_channels_page():
    ##return flask.render_template('error.html')

    playlist_name = request.path.replace('/playlists/', '')
    page = int(request.args.get('page', 1))
    offset = 50*(page - 1)
    videos, num_videos = get_local_playlist_videos(playlist_name, offset=offset, amount=50)
    return flask.render_template('local_playlist_related_hidden_channels.html',
        header_playlist_names = get_playlist_names(),
        playlist_name = playlist_name,
        videos = videos,
        num_pages = math.ceil(num_videos/50),
        parameters_dictionary = request.args,
        display_as_grid = False,
    )
#############################################################

