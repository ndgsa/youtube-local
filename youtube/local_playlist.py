from youtube import util, yt_data_extract
from youtube import yt_app
import settings

import os
import json
import html
import gevent
import urllib
import math

import cachetools.func

import flask
from flask import request

import re
import sqlite3
import contextlib
from io import BytesIO
import glob

playlists_directory = os.path.join(settings.data_dir, "playlists")
thumbnails_directory = os.path.join(settings.data_dir, "playlist_thumbnails")

thumbnails_sqlite_database_path = os.path.join(settings.data_dir, 'db', "thumbnails.sqlite")
playlists_sqlite_database_path = os.path.join(settings.data_dir, 'db', "playlists.sqlite")


@cachetools.func.lru_cache(maxsize=64)
def is_custom_type_playlist_name(name, custom=None):
    if custom == 'no_hidden_channels_videos' and name in ["related_hidden_channels", "search_hidden_channels", "related_hidden_videos", "search_hidden_videos"]:
        is_custom = None
    elif custom == 'no_hidden_channels' and name in ["related_hidden_channels", "search_hidden_channels"]:
        is_custom = None
    elif name in ["related_hidden_channels", "search_hidden_channels", "related_hidden_videos", "search_hidden_videos"]:
        is_custom = True
    elif custom == 'dummy':
        is_custom = True
    else:
        is_custom = None
    return is_custom


# Whitelist accepted playlist names so user input cannot escape
# Allow letters, digits, spaces, dot, dash and underscore.
_PLAYLIST_NAME_RE = re.compile(r'^[\w .\-]{1,128}$')
def _validate_playlist_name(name):
    '''Return the stripped name if safe, otherwise abort with 400.'''
    if (name is None) or (not _PLAYLIST_NAME_RE.match(name.strip())):
        if util.to_valid_filename(name.strip()) == name.strip() and len(name) < 128:
            return name.strip()
        print("Invalid path string")
        flask.abort(400)
    return name.strip()

def _find_playlist_path(name):
    '''Find playlist file robustly, handling trailing spaces in filenames'''
    if not os.path.exists(playlists_directory):
        os.makedirs(playlists_directory)
    p_path = os.path.join(playlists_directory, name + '.txt')
    if not os.path.isfile(p_path):
        return p_path
    name = _validate_playlist_name(name)
    pattern = os.path.join(playlists_directory, name + '*.txt')
    files = glob.glob(pattern)
    return files[0] if files else p_path

def _find_thumbnails_folder_path(name):
    '''Find thumbnails folder robustly, handling trailing spaces in folder names'''
    if not os.path.exists(thumbnails_directory):
        os.makedirs(thumbnails_directory)
    name = _validate_playlist_name(name)
    pattern = os.path.join(thumbnails_directory, name)
    files = glob.glob(pattern)
    if files and not os.path.isdir(files[0]):
        raise Exception(fr"'{pattern}' is not a folder")
    return files[0] if files else os.path.join(thumbnails_directory, name)


def video_ids_in_playlist(name, column=None):

    if use_sqlite3_db_as_storage(): return video_ids_in_playlist_sqlite_db(name, column)

    try:
        playlist_path = _find_playlist_path(name)
        with open(playlist_path, 'r', encoding='utf-8') as file:
            videos = file.read()
        if column and column != '*' and column != 'id':
            columns = [s.strip() for s in column.split(',')]
            videos = [json.loads(video.strip()) for video in videos.splitlines() if video.strip()]
            return [{col: video.get(col) for col in columns} for video in videos]
        elif column == None or column == 'id':
            ## gives error if History playlist is empty, to bypass error just delete History playlist
            return [json.loads(video.strip())['id'] for video in videos.splitlines() if video.strip()]
    except FileNotFoundError:
        return set()

def add_to_playlist(name, video_info_list):

    if is_custom_type_playlist_name(name):
        name = check_playlist_name_invalid_symbols(name.strip(), '_')

    if not check_playlist_name_invalid_symbols(name.strip(), ''):
        raise Exception("Invalid playlist name provided!")

    if use_sqlite3_db_as_storage(): return add_to_playlist_sqlite_db(name, video_info_list)

    playlist_path = _find_playlist_path(name)
    thumbnails_folder_path = _find_thumbnails_folder_path(name)

    if not os.path.exists(playlists_directory):
        os.makedirs(playlists_directory)
    ids = video_ids_in_playlist(name)
    missing_thumbnails = []

    try: thumbnails_id = set(os.listdir(thumbnails_folder_path))
    except FileNotFoundError: thumbnails_id = set()

    if name in ["related_hidden_channels", "search_hidden_channels"]:
        from youtube import channel

        def video_authors_id_in_playlist(name):
            try:
                with open(_find_playlist_path(name), 'r', encoding='utf-8') as file:
                    videos = file.read()
                    import sys
                ## gives error if History playlist is empty, to bypass error just delete History playlist
                return set(json.loads(video.strip())['author_id'] for video in videos.splitlines() if video.strip())
            except FileNotFoundError:
                return set()

        authors_id = video_authors_id_in_playlist(name)

        with open(playlist_path, "a", encoding='utf-8') as file:
            for info in video_info_list:

                # replace id with author_id becouse need avatar for channel not for video
                tmp = json.loads(info.strip())
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
                    file.write(info.strip() + "\n")

                tmp['avatar'] = re.sub(r'\=s(\d{3,4})-', '=s200-', tmp['avatar']) # 900px is too big

                if author_id + '.jpg' not in thumbnails_id:
                    url = tmp['avatar']
                    save_location = os.path.join(thumbnails_folder_path, author_id + ".jpg")
                    try:
                        thumbnail = util.fetch_url(url, report_text="Saved thumbnail: " + author_id)
                    except Exception as e: # util.FetchError
                        print("Failed to download thumbnail for " + author_id + ": " + str(e))
                        continue
                    try:
                        f = open(save_location, 'wb')
                    except FileNotFoundError:
                        os.makedirs(thumbnails_folder_path, exist_ok = True)
                        f = open(save_location, 'wb')
                    f.write(thumbnail)
                    f.close()

        return

    # if video exist in history playlist, move it to start, so it will look as recent video
    if name == "History":
        for info in video_info_list:
            id = json.loads(info.strip())['id']

            # if video is deleted from youtube than extracted values will be null and will break the playlist
            if id == None:
                continue

            if id in ids:
                with open(playlist_path, "r+") as f:
                    d = f.readlines()[:]
                    f.seek(0)
                    f.truncate()
                    d.append(d.pop(d.index(info.strip() + "\n") ))
                    for gg in d:
                       f.write(gg)
            break

    with open(playlist_path, "a", encoding='utf-8') as file:
        for info in video_info_list:
            id = json.loads(info.strip())['id']

            # if video is deleted from youtube than extracted values will be null and will break the playlist
            if id == None:
                continue

            if id not in ids:
                file.write(info.strip() + "\n")
                if id + '.jpg' not in thumbnails_id: missing_thumbnails.append(id)

    if is_custom_type_playlist_name(name):
        pass
    else:
        gevent.spawn(util.download_thumbnails, thumbnails_folder_path, missing_thumbnails)


def add_extra_info_to_videos(videos, playlist_name):
    '''Adds extra information necessary for rendering the video item HTML

    Downloads missing thumbnails'''

    if use_sqlite3_db_as_storage(): return add_extra_info_to_videos_sqlite_db(videos, playlist_name)

    thumbnails_folder_path = _find_thumbnails_folder_path(playlist_name)

    try:
        thumbnails = set(os.listdir(thumbnails_folder_path))
    except FileNotFoundError:
        thumbnails = set()
    missing_thumbnails = []

    for video in videos:
        if 'first_video_id' in video and 'video_count' in video and video['id'].startswith(('PL', 'OL')) and len(video['id']) > 11:
            video['type'] = 'playlist'
            video['playlist_type'] = 'playlist'
            video['thumbnail'] = ("/https://i.ytimg.com/vi/" + video['first_video_id'] + "/mqdefault.jpg")
            video['author_url'] = util.concat_or_none(util.URL_ORIGIN, "/channel/", video['author_id'])
            video['url'] = util.concat_or_none(util.URL_ORIGIN, '/playlist?list=', video['id'])
            video['badges'] = ''
            missing_thumbnails = []
        else:
            video['type'] = 'video'
            util.add_extra_html_info(video)
            if video['id'] + '.jpg' in thumbnails:
                video['thumbnail'] = (
                    '/https://youtube.com/data/playlist_thumbnails/'
                    + playlist_name
                    + '/' + video['id'] + '.jpg')
            elif playlist_name in ["related_hidden_channels", 'search_hidden_channels']:
                    url = re.sub(r'\=s(\d{3,4})-', '=s200-', video['avatar']) # 900px is too big
                    save_location = os.path.join(thumbnails_folder_path, video['author_id'] + ".jpg")
                    try:
                        thumbnail = util.fetch_url(url, report_text="Saved thumbnail: " + video['author_id'])
                    except Exception as e:
                        print("Failed to download thumbnail for " + video['author_id'] + ": " + str(e))
                        if '404 Not Found' in e.__str__() or "403 Forbidden" in e.__str__(): thumbnail = b''
                    try:
                        f = open(save_location, 'wb')
                    except FileNotFoundError:
                        os.makedirs(thumbnails_folder_path, exist_ok = True)
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

            if is_custom_type_playlist_name(playlist_name, 'no_hidden_channels'):
                video['thumbnail'] = ("/https://i.ytimg.com/vi/" + video['id'] + "/mqdefault.jpg")
                missing_thumbnails = []

    gevent.spawn(util.download_thumbnails, thumbnails_folder_path, missing_thumbnails)


def read_playlist(name):
    '''Returns a list of videos for the given playlist name'''

    if use_sqlite3_db_as_storage(): return read_playlist_sqlite_db(name)

    playlist_path = _find_playlist_path(name)

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
        video_line = video_json.strip()
        if not video_line: continue
        try:
            info = json.loads(video_line)
            videos.append(info)
        except json.decoder.JSONDecodeError:
            print('Corrupt playlist video entry: ' + video_line)
    return videos


def get_local_playlist_videos(name, offset=0, amount=50):

    if use_sqlite3_db_as_storage(): return get_local_playlist_videos_sqlite_db(name, offset, amount)

    videos = read_playlist(name)

    # reverse list, last added will be recent
    # if name == "History":
        # videos = videos[::-1]
    if settings.sort_playlist: videos = videos[::-1]

    if is_custom_type_playlist_name(name):
        add_extra_info_to_videos(videos[offset:offset+amount], name)
    else: add_extra_info_to_videos(videos, name)
    return videos[offset:offset+amount], len(videos)


def get_playlist_names():

    if use_sqlite3_db_as_storage(): return get_playlist_names_sqlite_db()

    try:
        items = os.listdir(playlists_directory)
    except FileNotFoundError:
        return []

    tmp = []
    for item in items:
        name, ext = os.path.splitext(item)
        if ext == '.txt' and (name not in ["History", "0youtube_playlist_list"]):
            # yield name
            tmp.append(name)
    return tmp


def remove_from_playlist(name, video_info_list, action=''):

    if not check_playlist_name_invalid_symbols(name.strip(), ''):
        raise Exception("Invalid playlist name provided!")

    if use_sqlite3_db_as_storage(): return remove_from_playlist_sqlite_db(name, video_info_list)

    playlist_path = _find_playlist_path(name)
    thumbnails_folder_path = _find_thumbnails_folder_path(name)

    ids = [json.loads(video.strip())['id'] for video in video_info_list]
    with open(playlist_path, 'r', encoding='utf-8') as file:
        videos = file.read()
    videos_in = videos.splitlines()
    videos_out = []
    for video in videos_in:
        if json.loads(video.strip())['id'] not in ids:
            videos_out.append(video.strip())
    with open(playlist_path, 'w', encoding='utf-8') as file:
        file.write("\n".join(videos_out) + "\n")

    try:
        thumbnails = set(os.listdir(thumbnails_folder_path))
    except FileNotFoundError:
        pass
    else:
        if action != 'reorder':
            to_delete = thumbnails & set(id + ".jpg" for id in ids)
            for file in to_delete:
                os.remove(os.path.join(thumbnails_folder_path, file))

    # remove empty/blank lines from file becouse they cause errors
    with open(playlist_path) as reader, open(playlist_path, 'r+') as writer:
        for line in reader:
            if line.strip(): writer.write(line)
        writer.truncate()

    return len(videos_out)


@yt_app.route('/playlists', methods=['GET'])
@yt_app.route('/playlists/<playlist_name>', methods=['GET'])
def get_local_playlist_page(playlist_name=None):

    if playlist_name == "custom_playlists":
        playlists = []
        for name in get_playlist_names():
            if is_custom_type_playlist_name(name, 'no_hidden_channels_videos'):
                playlists.append([name, util.URL_ORIGIN + '/playlists/' + name])
        return flask.render_template('local_playlists_list.html', playlists=playlists)

    if playlist_name == "hidden_videos_channels":
        playlists = [(name, util.URL_ORIGIN + '/playlists/' + name) for name in get_playlist_names() if name in ["related_hidden_channels", "search_hidden_channels", "related_hidden_videos", "search_hidden_videos"]]
        return flask.render_template('local_playlists_list.html', playlists=playlists)

    if playlist_name is None:
        playlists = []
        c_p_count = 0
        for name in get_playlist_names():
            if is_custom_type_playlist_name(name, 'no_hidden_channels_videos'):
                c_p_count += 1
                continue
            if name in ["related_hidden_channels", "search_hidden_channels", "related_hidden_videos", "search_hidden_videos"]: continue
            playlists.append([name, util.URL_ORIGIN + '/playlists/' + name])
        playlists = playlists + [("hidden_videos_channels", util.URL_ORIGIN + '/playlists/' + "hidden_videos_channels")] + ([("custom_playlists", util.URL_ORIGIN + '/playlists/' + "custom_playlists")] if c_p_count > 0 else [])  + youtube_playlists_from_local(action='get')
        return flask.render_template('local_playlists_list.html', playlists=playlists)
    else:
        page = int(request.args.get('page', 1))
        if is_custom_type_playlist_name(playlist_name):
            offset = 60*(page - 1)
            videos, num_videos = get_local_playlist_videos(playlist_name, offset=offset, amount=60)
            num_pages = math.ceil(num_videos/60)
            display_as_grid = False
        else:
            offset = 50*(page - 1)
            videos, num_videos = get_local_playlist_videos(playlist_name, offset=offset, amount=50)
            num_pages = math.ceil(num_videos/50)
            display_as_grid = settings.display_as_grid

        if request.args.get('sort1'):
            from youtube.channel import sort_video_items_custom
            videos = sort_video_items_custom(videos, request.args.get('sort1'), request.args.get("sort1_reversed", "false")) # sorting

        return flask.render_template('local_playlist.html',
            header_playlist_names = get_playlist_names(),
            playlist_name = playlist_name,
            videos = videos,
            num_pages = num_pages,
            parameters_dictionary = request.args,
            display_as_grid = display_as_grid,
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

        if use_sqlite3_db_as_storage(): remove_playlist_sqlite_db('playlists', playlist_name)
        else:
            playlist_path = _find_playlist_path(playlist_name)
            if os.path.join(playlists_directory, playlist_name + '.txt') == playlist_path:
                try: os.remove(playlist_path)
                except OSError: pass
            else:
                print(f"Cannot remove playlist {playlist_name}! Do it manually.")
                flask.abort(400)

        return flask.redirect(util.URL_ORIGIN + '/playlists')
    elif request.values['action'] == 'export':

        if request.values.get('export_youtube_playlist', None) == 'true':
            videos = [json.loads(v.strip()) for v in get_all_videos_from_playlist(request.values['playlist_id'])]
            if request.values.get('playlist_name') and request.values.get('playlist_name', '').strip():
                playlist_name = check_playlist_name_invalid_symbols(request.values['playlist_name'].strip(), '_')
        else: videos = read_playlist(playlist_name)

        fmt = request.values['export_format']
        if fmt in ('ids', 'urls'):
            prefix = ''
            if fmt == 'urls':
                if playlist_name in ["related_hidden_channels", "search_hidden_channels"]:
                    prefix = 'https://www.youtube.com/channel/'
                elif videos and videos[0].get('first_video_id'):
                    prefix = 'https://www.youtube.com/playlist?list='
                else:
                    prefix = 'https://www.youtube.com/watch?v='
            id_list = '\n'.join(prefix + v['id'] for v in videos)
            id_list += '\n'
            resp = flask.Response(id_list, mimetype='text/plain')
            # cd = 'attachment; filename="%s.txt"' % playlist_name
            cd = 'attachment; ' + 'filename*=' + "UTF-8''%s.txt" % urllib.parse.quote(playlist_name)
            resp.headers['Content-Disposition'] = cd
            return resp
        elif fmt == 'json':
            json_data = json.dumps({'videos': videos}, indent=2,
                                   sort_keys=True)
            resp = flask.Response(json_data, mimetype='text/json')
            # cd = 'attachment; filename="%s.json"' % playlist_name
            cd = 'attachment; ' + 'filename*=' + "UTF-8''%s.json" % urllib.parse.quote(playlist_name)
            resp.headers['Content-Disposition'] = cd
            return resp
        elif fmt == 'key_value_dict':
            tmp = []
            for item in videos:
                video_info = {}
                kz = []
                if playlist_name in ['related_hidden_channels', 'search_hidden_channels']:
                    kz = ['id', 'title', 'author', 'author_id', 'duration', 'approx_subscriber_count', 'short_description', 'channel_name', 'avatar']
                elif item.get('approx_view_count') or item.get('time_published'):
                    kz = ['id', 'title', 'author', 'author_id', 'duration', 'approx_view_count', 'time_published']
                elif item.get('first_video_id') and item.get('video_count'):
                    kz = ['id', 'title', 'author', 'author_id', 'video_count', 'first_video_id']
                else: kz = ['id', 'title', 'author', 'author_id', 'duration']
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
    elif request.values['action'] == 'import':
        import_videos_to_playlist(playlist_name, request)
        return flask.redirect(util.URL_ORIGIN + '/playlists/'+ playlist_name, 303)
    else:
        flask.abort(400)


@yt_app.route('/edit_playlist', methods=['POST'])
def edit_playlist():
    '''Called when adding videos to a playlist from elsewhere'''

    if request.values['playlist_name'] == 'History' and settings.disable_history:
        flask.abort(400)
        return

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
        playlist_name = request.values['playlist_name']
        playlist_name = check_playlist_name_invalid_symbols(playlist_name.strip(), '_')
        if request.values.get('import_playlist', None) == 'true':
            items = get_all_videos_from_playlist(request.values['playlist_id'])
            items = items[::-1]  # items must be reversed
            if playlist_name in get_playlist_names():
                print(f'Playlist name {playlist_name} already exist, adding random value to playlist name.')
                add_to_playlist(f"{playlist_name}_{str(os.urandom(2).hex())}", items)
            else:
                add_to_playlist(playlist_name, items)
        else:
            add_to_playlist(playlist_name, request.values.getlist('video_info_list'))
        return '', 204
    else:
        flask.abort(400)

# _THUMBNAIL_RE = re.compile(r'^[A-Za-z0-9_-]{11}\.jpg$')

@yt_app.route('/data/playlist_thumbnails/<playlist_name>/<thumbnail>')
def serve_thumbnail(playlist_name, thumbnail):
    # playlist_name = _validate_playlist_name(playlist_name)
    # if not _THUMBNAIL_RE.match(thumbnail): flask.abort(400)
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

        if use_sqlite3_db_as_storage(): ids = video_ids_in_playlist_sqlite_db(playlist_name, 'id')
        else: ids = video_ids_in_playlist(playlist_name)

        import urllib.parse as urlparse

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
                    elif query.path.startswith(('/embed/', '/v/', '/channel/')):
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

        # import_slow(playlist_name, request, list_video_ids)
        import_faster_with_ip_ban1(playlist_name, request, list_video_ids)

    return



def use_sqlite3_db_as_storage():
    try: use_sqlite3_db_as_storage_value = settings.use_sqlite3_db_as_storage
    except AttributeError as e: use_sqlite3_db_as_storage_value = False
    return use_sqlite3_db_as_storage_value


def db_connect1_sqlite_db(func):
    def _db_connect(*args, **kwargs):
        if not os.path.exists(os.path.join(settings.data_dir, 'db')):
            os.makedirs(os.path.join(settings.data_dir, 'db'))

        connection = sqlite3.connect(thumbnails_sqlite_database_path, check_same_thread=False)

        try:
            cursor = connection.cursor()
            cursor.row_factory = sqlite3.Row
            cursor.execute('''PRAGMA foreign_keys = 1''')
            # Create tables if they don't exist
            cursor.execute('''CREATE TABLE IF NOT EXISTS thumbnails (
                                  id text UNIQUE,
                                  PICTURE BLOB
                              )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS db_info (
                                  version integer DEFAULT 1
                              )''')

            result = func(cursor, *args, **kwargs)

            connection.commit()
            connection.close()
        except:
            connection.rollback()
            connection.close()
            raise

        # https://stackoverflow.com/questions/19522505/using-sqlite3-in-python-with-with-keyword
        return result #contextlib.closing(connection)

    return _db_connect

def db_connect_sqlite_db(func):
    def _db_connect(*args, **kwargs):
        if not os.path.exists(os.path.join(settings.data_dir, 'db')):
            os.makedirs(os.path.join(settings.data_dir, 'db'))

        connection = sqlite3.connect(playlists_sqlite_database_path, check_same_thread=False)

        try:
            cursor = connection.cursor()
            cursor.row_factory = sqlite3.Row
            cursor.execute('''PRAGMA foreign_keys = 1''')
            # Create tables if they don't exist
            cursor.execute('''CREATE TABLE IF NOT EXISTS playlists (
                                  id integer PRIMARY KEY,
                                  playlist_name text UNIQUE NOT NULL,
                                  playlist_url text
                              )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS playlists_youtube (
                                  id integer PRIMARY KEY,
                                  playlist_name text NOT NULL,
                                  playlist_url text
                              )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS playlist_videos (
                                  video_id integer PRIMARY KEY AUTOINCREMENT,
                                  sql_playlist_id integer NOT NULL REFERENCES playlists(id) ON UPDATE CASCADE ON DELETE CASCADE,
                                  id text NOT NULL,
                                  title text,
                                  author text,
                                  author_id text NOT NULL,
                                  duration text,
                                  approx_view_count text,
                                  time_published text,
                                  approx_subscriber_count text,
                                  short_description text,
                                  channel_name text,
                                  avatar text,
                                  unique (sql_playlist_id, id)
                              )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS playlist_playlists (
                                  playlist_id integer PRIMARY KEY AUTOINCREMENT,
                                  sql_playlist_id integer NOT NULL REFERENCES playlists(id) ON UPDATE CASCADE ON DELETE CASCADE,
                                  id text NOT NULL,
                                  title text,
                                  author text,
                                  author_id text NOT NULL,
                                  video_count integer,
                                  first_video_id text NOT NULL,
                                  unique (sql_playlist_id, id)
                              )''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS db_info (
                                  version integer DEFAULT 1
                              )''')

            result = func(cursor, *args, **kwargs)

            connection.commit()
            connection.close()
        except:
            connection.rollback()
            connection.close()
            raise

        # https://stackoverflow.com/questions/19522505/using-sqlite3-in-python-with-with-keyword
        return result #contextlib.closing(connection)

    return _db_connect

@db_connect_sqlite_db
def create_column_if_not_exist_sqlite_db(cursor):
    '''add column if not exist'''
    check_column_ = {'playlist_videos': ['approx_view_count', 'time_published']}
    for t_n,c_l in check_column_.items():
        for col_name in c_l:
            row = dict(cursor.execute(f'''SELECT COUNT(*) AS CNTREC FROM pragma_table_info('{t_n}')
                                            WHERE name=?;''', [col_name]).fetchone())
            if row.get('CNTREC') == 0:
                cursor.execute(f'''ALTER TABLE {t_n} ADD COLUMN {col_name} text''')
create_column_if_not_exist_sqlite_db()

@db_connect_sqlite_db
def add_playlist_sqlite_db(cursor, table, name, url):
    cursor.execute(f'''INSERT OR IGNORE INTO {table} (
                              playlist_name,
                              playlist_url
                          )
                          VALUES (?, ?)''', [name, url])

@db_connect_sqlite_db
def remove_playlist_sqlite_db(cursor, table, name):
    cursor.execute(f'''DELETE FROM {table}
                            WHERE playlist_name=?''', [name])

@db_connect_sqlite_db
def remove_playlist_by_url_sqlite_db(cursor, table, url):
    cursor.execute(f'''DELETE FROM {table}
                            WHERE playlist_url=?''', [url])

@db_connect_sqlite_db
def get_playlist_column_sqlite_db(cursor, table, name, column):
    row = cursor.execute(f'''SELECT {column}
                                   FROM {table}
                                   WHERE playlist_name=?
                               ''', [name]).fetchone()
    if row:
        return dict(row)[column]
    return 0

@db_connect_sqlite_db
def update_playlist_name_sqlite_db(cursor, table, name, new_name):
    cursor.execute(f'''UPDATE {table}
                            SET playlist_name = ?
                            WHERE playlist_name="{name}"
                        ''', [new_name])

@db_connect_sqlite_db
def get_playlists_sqlite_db(cursor, table, column):
    rows = cursor.execute(f'''SELECT {column}
                              FROM {table}
                              ORDER BY playlist_name;
                               ''',).fetchall()

    rows = [dict(row) for row in rows]
    if column == '*': return rows
    elif column.count(",") > 0:
        # column_list = [c.strip() for c in column.split(',')]
        return rows
    elif column.count(",") == 0: return [row[column] for row in rows]

@db_connect_sqlite_db
def get_videos_column_sqlite_db(cursor, name, column):
    row_videos = []
    row_playlists = []

    v_fields_allowed = ['id', 'title','author', 'author_id', 'duration', 'approx_view_count', 'time_published', 'approx_subscriber_count', 'short_description', 'channel_name', 'avatar',]
    p_fields_allowed = ['id', 'title', 'author', 'author_id', 'video_count', 'first_video_id',]
    columns = [s.strip() for s in column.split(',')]
    sql_playlist_id = get_playlist_column_sqlite_db('playlists', name, 'id')

    if all(c in v_fields_allowed for c in columns) or column == '*':
        row_videos = cursor.execute(f'''SELECT {column}
                                 FROM playlist_videos
                                 WHERE sql_playlist_id=?
                                 ORDER BY video_id;
                                 ''', [sql_playlist_id]).fetchall()

    if all(c in p_fields_allowed for c in columns) or column == '*':
        row_playlists = cursor.execute(f'''SELECT {column}
                                 FROM playlist_playlists
                                 WHERE sql_playlist_id=?
                                 ORDER BY playlist_id;
                                 ''', [sql_playlist_id]).fetchall()

    rows = [dict(row) for row in row_videos + row_playlists]
    if column == '*':
        for r in rows:
            del r['sql_playlist_id']
            # del r['video_id']
            # del r['playlist_id']
        return rows
    elif column.count(",") > 0:
        return rows
    elif column.count(",") == 0:
        return [row[column] for row in rows]

@db_connect_sqlite_db
def insert_videos_sqlite_db(cursor, name, video_info_list):
    rows_videos = []
    rows_playlists = []
    for video_item in video_info_list:
        if 'first_video_id' in video_item and 'video_count' in video_item and video_item['id'].startswith(('PL', 'OL')) and len(video_item['id']) > 11:
            rows_playlists.append(( name,
                video_item['id'],
                video_item['title'],
                video_item['author'],
                video_item['author_id'],
                video_item['video_count'],
                video_item['first_video_id'],
            ))
        else:
            rows_videos.append(( name,
                video_item['id'],
                video_item['title'],
                video_item['author'],
                video_item['author_id'],
                video_item['duration'],
                video_item.get('approx_view_count', None),
                video_item.get('time_published', None),
                video_item.get('approx_subscriber_count', None),
                video_item.get('short_description', None),
                video_item.get('channel_name', None),
                video_item.get('avatar', None),
            ))

    add_playlist_sqlite_db('playlists', name, None)
    cursor.executemany('''INSERT OR IGNORE INTO playlist_videos (
                              sql_playlist_id,
                              id,
                              title,
                              author,
                              author_id,
                              duration,
                              approx_view_count,
                              time_published,
                              approx_subscriber_count,
                              short_description,
                              channel_name,
                              avatar
                          )
                          VALUES ((SELECT id FROM playlists WHERE playlist_name=?), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', rows_videos)

    cursor.executemany('''INSERT OR IGNORE INTO playlist_playlists (
                              sql_playlist_id,
                              id,
                              title,
                              author,
                              author_id,
                              video_count,
                              first_video_id
                          )
                          VALUES ((SELECT id FROM playlists WHERE playlist_name=?), ?, ?, ?, ?, ?, ?)''', rows_playlists)

@db_connect_sqlite_db
def remove_videos_sqlite_db(cursor, name, video_ids):
    sql_playlist_id = get_playlist_column_sqlite_db('playlists', name, 'id')
    for video_id in video_ids:
        cursor.execute("""DELETE FROM playlist_videos WHERE sql_playlist_id=? and id=?""", [sql_playlist_id, video_id])
    # cursor.execute("""DELETE FROM playlist_videos WHERE sql_playlist_id=? and id IN (?)""", [sql_playlist_id, ', '.join(video_ids)])

@db_connect_sqlite_db
def update_video_column_sqlite_db(cursor, column, data_id, new_value):
    cursor.execute(f'''UPDATE playlist_videos
                            SET {column} = ?
                            WHERE id="{data_id}"
                        ''', [new_value])

@db_connect1_sqlite_db
def add_image_sqlite_db(cursor, data_id, image):
    cursor.execute(f'''INSERT OR IGNORE INTO thumbnails (
                              id,
                              PICTURE
                          )
                          VALUES (?, ?)''', [data_id, image])

@db_connect1_sqlite_db
def get_image_sqlite_db(cursor, data_id, column='PICTURE'):
    blop = cursor.execute(f'''SELECT {column}
                        FROM thumbnails
                        WHERE id=?;''', [data_id]).fetchall()
    if blop == []: return []
    if column == "*": return [dict(b) for b in blop]
    elif column.count(",") > 0: return [dict(b) for b in blop]
    elif column.count(",") == 0: return [dict(b)[column] for b in blop][0]

@db_connect1_sqlite_db
def get_images_sqlite_db(cursor, column):
    blop = cursor.execute(f'''SELECT {column}
                        FROM thumbnails
                        WHERE id IS NOT NULL;''',).fetchall()
    if column == "*": return [dict(b) for b in blop]
    elif column.count(",") > 0: return [dict(b) for b in blop]
    elif column.count(",") == 0: return [dict(b)[column] for b in blop]

@db_connect1_sqlite_db
def remove_images_sqlite_db(cursor, data_ids):
    for data_id in data_ids:
        cursor.execute("""DELETE FROM thumbnails WHERE id=?""", [data_id])

def vacuum_database():
    for i in ["playlists.sqlite", 'thumbnails.sqlite', 'subscriptions.sqlite']:
        conn = sqlite3.connect(i)
        conn.execute("VACUUM")
        conn.close()


def video_ids_in_playlist_sqlite_db(name, column):
    return get_videos_column_sqlite_db(name, column)


def add_to_playlist_sqlite_db(name, video_info_list):

    if not check_playlist_name_invalid_symbols(name.strip(), ''):
        raise Exception("Invalid playlist name provided!")

    if not os.path.exists(playlists_directory):
        os.makedirs(playlists_directory)
    ids = video_ids_in_playlist_sqlite_db(name, 'id')
    thumbnails_id = get_images_sqlite_db('id')
    missing_thumbnails = []

    video_info_list = [json.loads(info.strip()) for info in video_info_list]

    if name in ["related_hidden_channels", 'search_hidden_channels']:
        from youtube import channel

        video_info_list_ = []
        authors_id = video_ids_in_playlist_sqlite_db(name, 'author_id')
        for video_item in video_info_list:
            # replace id with author_id becouse need avatar for channel not for video
            tmp = video_item
            author_id = tmp['author_id']
            tmp['id'] = tmp['author_id']

            # if video is deleted from youtube than extracted values will be null and will break the playlist
            if author_id == None: continue

            # get channel metadata that includes avatar url
            tasks = (gevent.spawn(channel.get_metadata, author_id),)
            gevent.joinall(tasks)
            util.check_gevent_exceptions(*tasks)
            tmp.update(tasks[0].value)

            if author_id not in authors_id:
                video_info_list_.append(video_item)

            tmp['avatar'] = re.sub(r'\=s(\d{3,4})-', '=s200-', tmp['avatar']) # 900px is too big

            if author_id not in thumbnails_id:
                download_thumbnail_sqlite_db(author_id, tmp['avatar'])

        insert_videos_sqlite_db(name, video_info_list_)
        return

    if name == "History":
        ids = video_ids_in_playlist_sqlite_db(name, 'id')
        history_ids = [v['id'] for v in video_info_list if (v['id'] in ids) and v['id'] != None]
        remove_videos_sqlite_db(name, history_ids)

    ids = video_ids_in_playlist_sqlite_db(name, 'id')
    video_info_list = [v for v in video_info_list if (v['id'] not in ids) and v['id'] != None ]
    for video_item in video_info_list:
        if video_item['id'] not in thumbnails_id: missing_thumbnails.append(video_item['id'])
    if video_info_list == []: return
    else: insert_videos_sqlite_db(name, video_info_list)

    if is_custom_type_playlist_name(name):
        pass
    else:
        gevent.spawn(download_thumbnails_sqlite_db, missing_thumbnails)


def add_extra_info_to_videos_sqlite_db(videos, playlist_name):
    '''Adds extra information necessary for rendering the video item HTML
    Downloads missing thumbnails'''

    thumbnails_id = get_images_sqlite_db('id')
    missing_thumbnails = []

    for video in videos:
        if 'first_video_id' in video and 'video_count' in video and video['id'].startswith(('PL', 'OL')) and len(video['id']) > 11:
            video['type'] = 'playlist'
            video['playlist_type'] = 'playlist'
            video['thumbnail'] = ("/https://i.ytimg.com/vi/" + video['first_video_id'] + "/mqdefault.jpg")
            video['author_url'] = util.concat_or_none(util.URL_ORIGIN, "/channel/", video['author_id'])
            video['url'] = util.concat_or_none(util.URL_ORIGIN, '/playlist?list=', video['id'])
            video['badges'] = ''
            missing_thumbnails = []
        else:
            video['type'] = 'video'
            util.add_extra_html_info(video)

            if video['id'] not in thumbnails_id and playlist_name in ["related_hidden_channels", 'search_hidden_channels']:
                video['avatar'] = re.sub(r'\=s(\d{3,4})-', '=s200-', video['avatar']) # 900px is too big
                download_thumbnail_sqlite_db(video['id'], video['avatar'])
            elif video['id'] not in thumbnails_id:
                missing_thumbnails.append(video['id'])

            if is_custom_type_playlist_name(playlist_name, 'no_hidden_channels'):
                video['thumbnail'] = ("/https://i.ytimg.com/vi/" + video['id'] + "/mqdefault.jpg")
                missing_thumbnails = []
            else: video['thumbnail'] = ('/https://youtube.com/data/playlist_thumbnails/' + video['id'])

    tasks = (gevent.spawn(download_thumbnails_sqlite_db, missing_thumbnails),)
    gevent.joinall(tasks)
    util.check_gevent_exceptions(*tasks)


def read_playlist_sqlite_db(name):
    '''Returns a list of videos for the given playlist name'''
    # videos = video_ids_in_playlist_sqlite_db(name, 'id, title, author, author_id, duration, approx_view_count, time_published, approx_subscriber_count, short_description, channel_name, avatar')
    videos = video_ids_in_playlist_sqlite_db(name, '*')
    return videos


def get_local_playlist_videos_sqlite_db(name, offset=0, amount=50):
    videos = read_playlist_sqlite_db(name)
    if settings.sort_playlist: videos = videos[::-1]
    if is_custom_type_playlist_name(name):
        add_extra_info_to_videos_sqlite_db(videos[offset:offset+amount], name)
    else: add_extra_info_to_videos_sqlite_db(videos, name)
    return videos[offset:offset+amount], len(videos)


def get_playlist_names_sqlite_db():
    items = get_playlists_sqlite_db('playlists', 'playlist_name')
    tmp = []
    for item in items:
        if item not in ["History"]:
            # yield item
            tmp.append(item)
    return tmp

def remove_from_playlist_sqlite_db(name, video_info_list):
    video_info_list = [json.loads(video.strip()) for video in video_info_list]
    ids = video_ids_in_playlist_sqlite_db(name, 'id')
    video_ids = [v['id'] for v in video_info_list if (v['id'] in ids) and v['id'] != None]
    remove_videos_sqlite_db(name, video_ids)
    # remove_images_sqlite_db(video_ids)
    return len(ids) - len(video_ids)


def youtube_playlists_from_local_sqlite_db(playlist_name='0youtube_playlist_list', action='get', data={}):

    playlist_list = []
    playlist_list_formated = []

    playlist_list = get_playlists_sqlite_db('playlists_youtube', '*')
    for playlist in playlist_list:
        playlist_list_formated.append(('(*) ' + playlist['playlist_name'], '/' + playlist['playlist_url']))

    if action == 'get': return playlist_list_formated
    elif action == 'add' and data != {}:
        add_playlist_sqlite_db('playlists_youtube', data['playlist_name'], data['playlist_url'])
    elif action == 'remove' and data != {}:
        for p in playlist_list:
            if data['playlist_url'] == p['playlist_url']:
                remove_playlist_by_url_sqlite_db('playlists_youtube', data['playlist_url'])


def update_video_column(playlist_name, column, values):

    if use_sqlite3_db_as_storage():
        for value in values:
            for k,v in value.items():
                update_video_column_sqlite_db(column, k, v)
        return

    videos = read_playlist(playlist_name)
    for video in videos:
        for value in values:
            for k,v in value.items():
                if video['id'] == k:
                    video[column] = v

    playlist_path = _find_playlist_path(playlist_name)
    with open(playlist_path, "w", encoding='utf-8') as file:
        for video in videos: file.write(json.dumps(video) + "\n")

    return


def download_thumbnail_sqlite_db(video_id, url=None):
    status = None
    if not url:
        url = "https://i.ytimg.com/vi/" + video_id + "/mqdefault.jpg"
    try:
        thumbnail = util.fetch_url(url, report_text="Saved thumbnail: " + video_id)
    except urllib.error.HTTPError as e:
        print("Failed to download thumbnail for " + video_id + ": " + str(e))
        return False
    except util.FetchError as e:
        print("Failed to download thumbnail for " + video_id + ": " + str(e))
        if '404 Not Found' in e.__str__() or "403 Forbidden" in e.__str__():
            thumbnail = b''
        status = False

    add_image_sqlite_db(video_id, thumbnail)
    return status or True


def download_thumbnails_sqlite_db(ids, url=None):
    if not isinstance(ids, (list, tuple)):
        ids = list(ids)
    # only do 5 at a time
    # do the n where n is divisible by 5
    i = -1
    for i in range(0, int(len(ids)/5) - 1 ):
        gevent.joinall([gevent.spawn(download_thumbnail_sqlite_db, ids[j]) for j in range(i*5, i*5 + 5)])
    # do the remainders (< 5)
    gevent.joinall([gevent.spawn(download_thumbnail_sqlite_db, ids[j]) for j in range(i*5 + 5, len(ids))])


def import_slow(playlist_name, request, list_video_ids):
    from youtube import channel
    # from youtube.watch import extract_info
    from time import sleep

    for video_id in list_video_ids:
        use_invidious = bool(int(request.args.get('use_invidious', '1')))
        if playlist_name in ['related_hidden_channels', 'search_hidden_channels']:
            tasks = (gevent.spawn(channel.get_metadata, video_id),)
        else:
            tasks = (gevent.spawn(extract_info_mini2, video_id, use_invidious, playlist_id=None, index=None),)
        gevent.joinall(tasks)
        util.check_gevent_exceptions(tasks[0])
        info = tasks[0].value

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

            if is_custom_type_playlist_name(playlist_name, 'no_hidden_channels'):
                for key in ('approx_view_count', 'time_published'):
                    if key in item: video_info[key] = info[key]

            print(f"Add video '{video_id}' to playlist '{playlist_name}' with success.")
            add_to_playlist(playlist_name, [json.dumps(video_info)])

        sleep(1)


def import_faster_with_ip_ban1(playlist_name, request, list_video_ids):

    # if there are too many items to import google can ban ip
    # so import elements by chunks of 50 items with delay 2-3 minutes

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

                if is_custom_type_playlist_name(playlist_name, 'no_hidden_channels'):
                    for key in ('approx_view_count', 'time_published'):
                        if key in item: video_info[key] = info[key]

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

        headers = util.generate_api_headers(ua_platform='mobile')

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

        for key in ('approx_view_count', 'time_published'):
            if key in item: video_info[key] = item[key]

        tmp.append(json.dumps(video_info))

    return tmp


def youtube_playlists_from_local(playlist_name='0youtube_playlist_list', action='get', data={}):

    if use_sqlite3_db_as_storage(): return youtube_playlists_from_local_sqlite_db(playlist_name, action, data)

    if not os.path.exists(playlists_directory):
        os.makedirs(playlists_directory)

    playlist_path = _find_playlist_path(playlist_name)

    playlist_list = []
    playlist_list_formated = []

    try:
        with open(playlist_path, 'r', encoding='utf-8') as file: yt_playlists = file.read()
        for yt_playlist in yt_playlists.splitlines():
            if yt_playlist.strip():
                playlist = json.loads(yt_playlist.strip())
                playlist_list.append(playlist)
                playlist_list_formated.append(('(*) ' + playlist['playlist_name'], '/' + playlist['playlist_url']))
    except FileNotFoundError:
        with open(playlist_path, 'a') as file: pass
        return []

    if action == 'get': return playlist_list_formated
    elif action == 'add' and data != {}:
        if data not in playlist_list:
            with open(playlist_path, "a", encoding='utf-8') as file:
                file.write(json.dumps(data) + "\n")
    elif action == 'remove' and data != {}:
        try: playlist_list.remove(data)
        except ValueError: pass

        with open(playlist_path, 'w', encoding='utf-8') as file:
            for i in playlist_list: file.write(json.dumps(i) + "\n")

        with open(playlist_path) as reader, open(playlist_path, 'r+') as writer:
            for line in reader:
                if line.strip(): writer.write(line)
            writer.truncate()


def check_playlist_name_invalid_symbols(string, replacement=None):
    if not string: raise Exception("Empty string provided!")
    if re.findall(r'[<>:/\\|?*\"\'#%]+', replacement.strip() or ''): raise Exception('Bad replacement character!')
    fail_string = util.to_valid_filename(string)
    fail_string = re.sub(r'[\'#%]+', replacement, fail_string)
    if fail_string != string:
        if replacement: return fail_string
        else: return None
    return string


def update_playlist_name(name, new_name):

    # Invalidate if no match with regex, because it will start
    # downloading all thumbnails(they can be many, 5000) when accesing playlist.
    if is_custom_type_playlist_name(name):
        if not is_custom_type_playlist_name(new_name):
            print('Invalid name for custom playlist type!')
            return ('Invalid name for custom playlist type!', 500)

    if use_sqlite3_db_as_storage():
        update_playlist_name_sqlite_db('playlists', name, new_name)
        if get_playlist_column_sqlite_db('playlists', new_name, 'playlist_name') != 0:
            return ('', 204)
        else:
            print("Updating playlist name failed.")
            return ('', 500)

    playlist_path = _find_playlist_path(name)
    playlist_path_new = _find_playlist_path(new_name)
    thumbnails_folder_path = _find_thumbnails_folder_path(name)
    thumbnails_folder_path_new = _find_thumbnails_folder_path(new_name)

    os.makedirs(thumbnails_folder_path, exist_ok = True)

    from pathlib import Path

    status = (None, None)
    if (Path(playlists_directory).is_dir()
        and Path(thumbnails_folder_path).is_dir()
        and Path(playlist_path).is_file()):
        try:
            Path(playlist_path).rename(playlist_path_new)
            Path(thumbnails_folder_path).rename(thumbnails_folder_path_new)
        except FileNotFoundError:
            print("The playlist file/folder does not exist.")
            status = ('', 500)
        except PermissionError:
            print("You do not have permission to rename the file/folder.")
            status = ('', 500)
        except:
            print('Renaming playlist failed.')
            status = ('', 500)

    if (Path(playlists_directory).is_dir()
        and Path(thumbnails_folder_path_new).is_dir()
        and Path(playlist_path_new).is_file()
        and status == (None, None)):
        status = ('', 204)

    return status


@yt_app.route('/data/playlist_thumbnails/<thumbnail>')
def serve_thumbnail_sqlite_db(thumbnail):
    # .. is necessary because flask always uses the application directory at ./youtube, not the working directory
    bytes_io = get_image_sqlite_db(thumbnail)
    if bytes_io != []:
        bytes_io = BytesIO(bytes_io)
    else:
        bytes_io = BytesIO(b'')
    # return flask.send_file(bytes_io, mimetype='image/jpeg')
    return flask.Response(bytes_io, mimetype='image/jpeg')

@yt_app.route('/playlists/History', methods=['GET'])
def get_local_history_page():
    ##return flask.render_template('error.html')

    page = int(request.args.get('page', 1))
    offset = 50*(page - 1)
    videos, num_videos = get_local_playlist_videos("History", offset=offset, amount=50)

    if request.args.get('sort1'):
        from youtube.channel import sort_video_items_custom
        videos = sort_video_items_custom(videos, request.args.get('sort1'), request.args.get("sort1_reversed", "false")) # sorting

    return flask.render_template('local_playlist.html',
        header_playlist_names = get_playlist_names(),
        playlist_name = "History",
        videos = videos,
        num_pages = math.ceil(num_videos/50),
        parameters_dictionary = request.args,
        display_as_grid = settings.display_as_grid,
        disable_history = settings.disable_history,
    )


@yt_app.route('/playlists/<playlist_name>/edit', methods=['GET'])
def get_local_playlist_page_edit(playlist_name=None):
    if playlist_name not in get_playlist_names():
        return flask.redirect(util.URL_ORIGIN + '/playlists')
    page = int(request.args.get('page', 1))
    amount = int(request.args.get('amount', 50))
    offset = amount*(page - 1)
    videos, num_videos = get_local_playlist_videos(playlist_name, offset=offset, amount=amount)
    num_pages = math.ceil(num_videos/amount)
    return flask.render_template('local_playlist_edit.html',
        header_playlist_names = get_playlist_names(),
        playlist_name = playlist_name,
        videos = videos,
        num_pages = num_pages,
        parameters_dictionary = request.args,)

_VIDEO_INFO_LIST_ID_RE = re.compile(r'''\"id\"\:\s\"([A-Za-z0-9_\-]{11})\"\,\s''')

@yt_app.route('/playlists/<playlist_name>/edit', methods=['POST'])
def path_local_playlist_page_edit(playlist_name):
    '''Called when edit playlist'''
    if request.values['action'] == 'reorder':
        video_info_list = request.values.getlist('video_info_list')
        page = int(request.values.get('page', 1))
        amount = int(request.values.get('amount', len(video_info_list)))
        offset = amount*(page - 1)
        videos = [json.dumps(item) for item in read_playlist(playlist_name)[::-1]]

        if amount > len(videos): return 'Items per page exceeded length of playlist items.', 400

        for i in video_info_list:
            match = _VIDEO_INFO_LIST_ID_RE.search(i)
            if match:
                id_founded = match.group(1)
                if any([id_founded in j for j in videos]): continue
                else: return f'video id: {id_founded} does not exist in database. Abort!', 400

        if len(videos[offset:offset+amount]) == len(video_info_list):
            videos[offset:offset+amount] = video_info_list
        else: return 'Invalid video_info_list length', 400

        if settings.sort_playlist: videos.reverse()
        remove_from_playlist(playlist_name, videos, 'reorder')
        add_to_playlist(playlist_name, videos)
        return '', 204
    elif request.values['action'] == 'rename':
        import html
        playlist_new_name = urllib.parse.unquote(html.unescape(request.values['playlist_new_name'])) or ''
        playlist_new_name = check_playlist_name_invalid_symbols(playlist_new_name.strip(), '')

        if not playlist_new_name:
            return 'Invalid playlist name!', 400
        if (len(playlist_new_name) == 0
            or playlist_new_name.lower() in ['', 'none', 'null', 'undefined', 'true', 'false']):
            return 'Invalid playlist name!', 400

        if playlist_name not in get_playlist_names():
            return f'Playlist "{playlist_name}" does not exist!', 400
        if playlist_new_name in get_playlist_names():
            return 'Playlist already exist!', 400
        if playlist_name in ['related_hidden_channels', 'search_hidden_channels', 'related_hidden_videos', 'search_hidden_videos']:
            return 'This playlist not allowed to update!', 400

        status = update_playlist_name(playlist_name, playlist_new_name)
        return status
    else:
        flask.abort(400)


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


@yt_app.route('/playlists1/<playlist_name>', methods=['GET'])
def get_local_playlist_page1(playlist_name=None):
        videos, num_videos = get_local_playlist_videos(playlist_name, offset=0, amount=1000)
        response = yt_app.response_class(
            response=json.dumps(videos),
            mimetype='application/json'
        )
        return response

    # for the request
    # response1 = urllib.request.urlopen(f'http://127.0.0.1:{settings.port_number}/https://www.youtube.com/playlists1/123')
    # data1 = json.load(response1)
    # print(data1)

def get_watch_page_local_playlist(playlist_local, video_id, amount=301):
    playlist_local_url = f'http://127.0.0.1:{settings.port_number}/https://www.youtube.com/playlists/' + playlist_local

    ids = video_ids_in_playlist(playlist_local, 'id')

    if len(ids) == 0: return None
    else: ids.reverse()
    total_ids = len(ids)
    current_video_id_index = ids.index(video_id)

    if total_ids%amount == 0: ranges = [i for i in range(0, total_ids, amount - 1)]
    else: ranges = [i for i in range(0, total_ids, amount - 1)] + [total_ids]
    index = next(c for c, r in enumerate(ranges) if r > current_video_id_index)
    start, end = ranges[index - 1], ranges[index]
    if end - start > 1 and start > 1: start = start - 1

    data1, _ = get_local_playlist_videos(playlist_local, offset=start, amount=amount)
    local_playlist = {}
    local_playlist['title'] = playlist_local
    local_playlist['author'] = ""
    local_playlist['author_id'] = ""
    local_playlist['author_url'] = playlist_local_url
    local_playlist['id'] = playlist_local
    local_playlist['url'] = playlist_local_url
    local_playlist['video_count'] = len(data1)
    local_playlist['current_index'] = 1
    local_playlist['items'] = data1[:]
    local_playlist['total_videos'] = total_ids
    local_playlist['current_video_id_index'] = current_video_id_index

    for item_index, item in enumerate(local_playlist['items']):
        item['url'] += '&playlists1=' + playlist_local
        if video_id == item['id']: local_playlist['current_index'] = item_index

    return local_playlist


@yt_app.route('/playlists/<playlist_name>/sort1/<sort1>/<sort1_reversed>', methods=['GET'])
@yt_app.route('/playlists/<playlist_name>/sort1/<sort1>', methods=['GET'])
def get_sort_database_playlist_page(playlist_name=None, sort1=None, sort1_reversed=None):
    sorted_playlist_name = sort_database_playlist(playlist_name, str(sort1), sort1_reversed, sorted_dublicate=True)
    return get_local_playlist_page(playlist_name)

def sort_database_playlist(playlist_name, sort1='1', sort1_reversed=None, sorted_dublicate=True):
    '''insert in data base dublicated playlist with sorted items'''

    if not is_custom_type_playlist_name(playlist_name, 'no_hidden_channels'):
        print('Sorting is not available for non custom playlist.')
        return

    videos = read_playlist(playlist_name)

    sort1_reversed = 'false' if sort1_reversed == '1' else 'true'

    from youtube.channel import sort_video_items_custom
    import sys
    sys.setrecursionlimit(1500)
    videos = sort_video_items_custom(videos, sort1, sort1_reversed) # sorting
    sys.setrecursionlimit(1000)

    video_info_list = [json.dumps(item) for item in videos]

    if sorted_dublicate:
        sorted_playlist_name = playlist_name + f" sort1_{sort1}"
    else:
        sorted_playlist_name = playlist_name

    if len(video_info_list) > 0:
        if use_sqlite3_db_as_storage():
            remove_playlist_sqlite_db('playlists', sorted_playlist_name)
        else:
            status = (None, None)
            from pathlib import Path
            playlist_path = _find_playlist_path(playlist_name)
            thumbnails_folder_path = _find_thumbnails_folder_path(playlist_name)
            thumbnails_folder_path_new = _find_thumbnails_folder_path(sorted_playlist_name)
            if (Path(playlists_directory).is_dir()
                and Path(thumbnails_folder_path).is_dir()
                and Path(playlist_path).is_file()):
                try:
                    Path(playlist_path).unlink()
                    if playlist_name != sorted_playlist_name:
                        Path(thumbnails_folder_path).rename(thumbnails_folder_path_new)
                except FileNotFoundError:
                    print("The playlist file/folder does not exist.")
                    status = ('', 500)
                except PermissionError:
                    print("You do not have permission to rename the file/folder.")
                    status = ('', 500)
                except:
                    print('Moving playlist failed.')
                    status = ('', 500)
                if status[1]: raise Exception('Error occurred on renaming.')

    add_to_playlist(sorted_playlist_name, video_info_list)
    print(f"Playlist '{playlist_name}' items sorted and saved into '{sorted_playlist_name}'.")

    return sorted_playlist_name


@yt_app.route('/export_from_txt_to_sqlite3', methods=['GET'])
def export_from_txt_to_sqlite3():
    export_from_txt_to_sqlite3_e()
    return get_local_playlist_page()

@yt_app.route('/export_from_sqlite3_to_txt', methods=['GET'])
def export_from_sqlite3_to_txt():
    export_from_sqlite3_to_txt_e()
    return get_local_playlist_page()

def export_from_txt_to_sqlite3_e():

    from pathlib import Path

    if not os.path.exists(os.path.join(settings.data_dir, 'export', 'db')):
        os.makedirs(os.path.join(settings.data_dir, 'export', 'db'))

    # change global variable so database path will create sqlite file in export folder
    global thumbnails_sqlite_database_path
    global playlists_sqlite_database_path
    thumbnails_sqlite_database_path = os.path.join(settings.data_dir, "export", 'db', "thumbnails.sqlite")
    playlists_sqlite_database_path = os.path.join(settings.data_dir, "export", 'db', "playlists.sqlite")

    # read txt files and add to sqlite
    if Path(playlists_directory).is_dir():
        playlist_names = Path(playlists_directory)
        for playlist_name in playlist_names.iterdir():
            if playlist_name.is_file() and playlist_name.suffix == '.txt':
                videos = playlist_name.read_text()
                video_info_list = [json.loads(video.strip()) for video in videos.splitlines()]

                if playlist_name.stem == '0youtube_playlist_list':
                    playlists_youtube = get_playlists_sqlite_db('playlists_youtube', '*') # need before change global variable
                    for yt in video_info_list:
                        founded = False
                        for z in playlists_youtube:
                            if z['playlist_url'] == yt['playlist_url']:
                                founded = True
                                break
                        if not founded: add_playlist_sqlite_db('playlists_youtube', yt['playlist_name'], yt['playlist_url'])

                    print(playlist_name.name, "data exported to 'data/export/db/playlists.sqlite'")
                    continue

                insert_videos_sqlite_db(playlist_name.stem, video_info_list)
                print(playlist_name.name, "data exported to 'data/export/db/playlists.sqlite'")

    # read thumbnails and add to sqlite
    thumbnails_ids = get_images_sqlite_db('id')
    if Path(thumbnails_directory).is_dir():
        thumbnail_folder_names = Path(thumbnails_directory)
        for playlist_path in thumbnail_folder_names.iterdir():
            if playlist_path.is_dir():
                for image_path in playlist_path.iterdir():
                    if image_path.suffix.lower() in [".jpeg", ".jpg"]:
                        if image_path.stem not in thumbnails_ids:
                            add_image_sqlite_db(image_path.stem, image_path.read_bytes())
                            print(image_path.name, "thumbnail exported to 'data/export/db/thumbnails.sqlite'")

    # restore default path for sqlite files
    thumbnails_sqlite_database_path = os.path.join(settings.data_dir, 'db', "thumbnails.sqlite")
    playlists_sqlite_database_path = os.path.join(settings.data_dir, 'db', "playlists.sqlite")

    print("Export operation finished!")

def export_from_sqlite3_to_txt_e():

    ## bad way to join data from 2 databases

    # connection = sqlite3.connect('playlists.sqlite')
    # cursor = connection.cursor()
    # cursor.row_factory = sqlite3.Row
    # blop = cursor.execute(f'''select p.playlist_name, v.id  from playlists as p inner join playlist_videos as v on p.id = v.sql_playlist_id;''',).fetchall()
    ### blop = cursor.execute(f'''Select p.playlist_name, v.id from playlists p, playlist_videos v where p.id = v.sql_playlist_id;''',).fetchall()
    # results1 = [dict(b) for b in blop]
    # connection.commit()
    # connection.close()

    # connection = sqlite3.connect('thumbnails.sqlite')
    # cursor = connection.cursor()
    # cursor.row_factory = sqlite3.Row
    # blop = cursor.execute(f'''SELECT * FROM thumbnails WHERE id IS NOT NULL;''',).fetchall()
    # results2 = [dict(b) for b in blop]
    # connection.commit()
    # connection.close()

    # tmp = []
    # for i in results2:
        # for j in results1:
            # if i['id'] == j['id']:
                # j['PICTURE'] = i['PICTURE']
                # tmp.append(j)
    # results = tmp[:]


    if not os.path.isfile(thumbnails_sqlite_database_path):
        raise Exception(f'{thumbnails_sqlite_database_path} database file does not exist!')
        return
    if not os.path.isfile(playlists_sqlite_database_path):
        raise Exception(f'{playlists_sqlite_database_path} database file does not exist!')
        return

    tmp_database_path = os.path.join(settings.data_dir, 'db', "playlists.sqlite")
    connection = sqlite3.connect(tmp_database_path)
    cursor = connection.cursor()
    cursor.row_factory = sqlite3.Row
    cursor.execute(f"ATTACH DATABASE '{os.path.join(settings.data_dir, 'db', 'thumbnails.sqlite')}' AS db2;")
    blop = cursor.execute(f'''select playlists.playlist_name, playlist_videos.id, db2.thumbnails.PICTURE
                            from db2.thumbnails
                            join playlists
                                on playlist_videos.sql_playlist_id = playlists.id
                            join playlist_videos
                                on db2.thumbnails.id = playlist_videos.id''',).fetchall()
    results = [dict(b) for b in blop]

    blop = cursor.execute(f'''SELECT *
                                FROM db2.thumbnails
                                WHERE NOT EXISTS
                                    (SELECT *
                                     FROM playlist_videos
                                     WHERE playlist_videos.id = db2.thumbnails.id)''',).fetchall()
    subscription_thumbnails = [dict(b) for b in blop]
    for b in subscription_thumbnails: b.update({'playlist_name': 'subscription_thumbnails'})

    cursor.execute("DETACH DATABASE db2;")
    connection.commit()
    connection.close()

    results = results + subscription_thumbnails

    if not os.path.exists(os.path.join(settings.data_dir, 'export')):
        os.makedirs(os.path.join(settings.data_dir, 'export'))
        os.makedirs(os.path.join(settings.data_dir, 'export', 'playlist_thumbnails'))
        os.makedirs(os.path.join(settings.data_dir, 'export', 'subscription_thumbnails'))

    for i in results:
        _validate_playlist_name(i['playlist_name'])

        if i['playlist_name'] == 'subscription_thumbnails':
            folder_path = os.path.join(settings.data_dir, 'export', 'subscription_thumbnails')
        else:
            folder_path = os.path.join(settings.data_dir, 'export', 'playlist_thumbnails', i['playlist_name'])

        file_path = os.path.join(folder_path, i['id'] + '.jpg')

        try:
            os.makedirs(folder_path, exist_ok=True)
        except FileExistsError:
            # directory already exists
            pass
            # continue

        if not os.path.isfile(file_path):
            with open(file_path, "wb") as f:
                picture = BytesIO(i['PICTURE'])
                f.write(picture.getbuffer())
                if i['playlist_name'] == 'subscription_thumbnails':
                    print(i['id'], f"thumbnail exported to 'data/export/{i['playlist_name']}/{i['id']}.jpg'")
                else:
                    print(i['id'], f"thumbnail exported to 'data/export/playlist_thumbnails/{i['playlist_name']}/{i['id']}.jpg'")

    items = get_playlists_sqlite_db('playlists', 'playlist_name')
    backup = {}
    for i in items: backup[i] = read_playlist_sqlite_db(i)
    backup['0youtube_playlist_list'] = get_playlists_sqlite_db('playlists_youtube', '*')

    if not os.path.exists(os.path.join(settings.data_dir, 'export')):
        os.makedirs(os.path.join(settings.data_dir, 'export'))
    if not os.path.exists(os.path.join(settings.data_dir, 'export', 'playlists')):
        os.makedirs(os.path.join(settings.data_dir, 'export', 'playlists'))

    folder_path = os.path.join(settings.data_dir, 'export', 'playlists')

    for playlists_name,video_info_list in backup.items():
        file_path = os.path.join(folder_path, playlists_name + ".txt")
        if not os.path.isfile(file_path):
            with open(file_path, "w", encoding='utf-8') as file:
                for info in video_info_list:
                    file.write(json.dumps(info) + "\n")
                print(f"playlist '{playlists_name}' data exported to 'data/export/playlists/{playlists_name}.txt'")

    print("Export operation finished!")


@yt_app.route('/clean_unused_thumbnails', methods=['GET'])
def clean_unused_thumbnails():
    ids = []
    thumbnails_id = get_images_sqlite_db('id')
    for playlist_name in get_playlists_sqlite_db('playlists', 'playlist_name'):
        ids.extend(video_ids_in_playlist_sqlite_db(playlist_name, 'id'))
    to_remove_ids = list(set(thumbnails_id) - set(ids))
    print(f"Total unused thumbnails: {len(to_remove_ids)}")
    remove_images_sqlite_db(to_remove_ids)

    @db_connect1_sqlite_db
    def vacuum_thumbnails_db(cursor):
        print("Wait until database vacuum finished")
        cursor.execute("VACUUM")
        print("Done!")
    vacuum_thumbnails_db()

    return get_local_playlist_page()

