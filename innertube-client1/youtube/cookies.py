import os
import sys
import glob
import json
import shutil
import sqlite3
import hashlib
import tempfile
import subprocess
import time
import http.cookiejar
import cachetools.func

from pathlib import Path

import settings


class BrowserCookieError(Exception):
    pass
class SignInError(Exception):
    pass


def cookies_file(c_path):
    if Path(c_path).is_file() and Path(c_path).name == 'cookies.txt':
        return c_path
    return None

def cookies_from_file(c_path):
    '''Returns cookiejar type result from cookies.txt file.'''
    if c_path is None: raise BrowserCookieError("Invalid 'cookies.txt' path location.")
    jar = http.cookiejar.MozillaCookieJar(c_path)
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except FileNotFoundError:
        raise SignInError('Cookies file doesn\'t exist: ' + c_path)
    except (http.cookiejar.LoadError, OSError) as e:
        raise SignInError('Couldn\'t read the cookies file. It '
                          'has to be a cookies.txt file (Netscape format): '
                          + str(e))
    return jar


def cookie_database(c_path):
    patterns = ('*/cookies.sqlite', 'cookies.sqlite')
    found = []
    for root in [c_path]:
        if not root or not os.path.isdir(root):
            continue
        for pattern in patterns:
            found += glob.glob(os.path.join(glob.escape(root), pattern))
    if not found:
        return None
    return max(found)

def _read_rows(database_path, query):
    '''Reads a copy, since the browser keeps the database locked while open'''
    temp_dir = tempfile.mkdtemp(prefix='ytl-cookies-')
    try:
        copy_path = os.path.join(temp_dir, 'cookies.db')
        shutil.copyfile(database_path, copy_path)
        # recent changes that the browser hasn't merged into the file yet
        for suffix in ('-wal', '-journal'):
            if os.path.exists(database_path + suffix):
                shutil.copyfile(database_path + suffix, copy_path + suffix)
        connection = sqlite3.connect(copy_path)
        try:
            rows = connection.execute(query).fetchall()
            try:
                version = connection.execute(
                    "SELECT value FROM meta WHERE key = 'version'").fetchone()
            except sqlite3.Error:
                version = None
        finally:
            connection.close()
        return rows, int(version[0]) if version else 0
    except (OSError, sqlite3.Error) as e:
        raise BrowserCookieError('Couldn\'t read the browser\'s cookies: '
                                 + str(e))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def cookies_from_database(c_path):
    '''Returns cookiejar type result from browser profile'''
    c_path = cookie_database(c_path)
    if c_path is None: raise BrowserCookieError('Invalid browser profile path.')
    db_schema_version = int(_read_rows(c_path, 'PRAGMA user_version;')[0][0][0])
    table, _ = _read_rows(c_path, 'SELECT host, name, value, path, expiry, isSecure FROM moz_cookies '
                               "WHERE host LIKE '%youtube.com'")
    jar = http.cookiejar.MozillaCookieJar()
    for i, (host, name, value, path, expiry, is_secure) in enumerate(table):
        if db_schema_version >= 16 and expiry is not None:
            expiry /= 1000
        jar.set_cookie(http.cookiejar.Cookie(
            version=0, name=name, value=value, port=None, port_specified=False,
            domain=host, domain_specified=bool(host), domain_initial_dot=host.startswith('.'),
            path=path, path_specified=bool(path), secure=is_secure, expires=expiry, discard=False,
            comment=None, comment_url=None, rest={}))
    return jar


@cachetools.func.ttl_cache(maxsize=1, ttl=60*60)
def get_cookies():
    c_path = rf'{settings.yt_cookies_path}'
    if cookies_file(c_path):
        jar = cookies_from_file(c_path)
    elif cookie_database(c_path):
        jar = cookies_from_database(c_path)
    else: return None
    cookies = {cookie.name: cookie.value for cookie in jar if cookie.domain.lstrip('.').endswith('youtube.com')}
    return cookies


def is_set_up():
    c_path = rf'{settings.yt_cookies_path}'
    if bool(cookies_file(c_path) or cookie_database(c_path)): return True
    else: return False


def try_call(*funcs, expected_type=None, args=[], kwargs={}):
    for f in funcs:
        try:
            val = f(*args, **kwargs)
        except (AttributeError, KeyError, TypeError, IndexError, ValueError, ZeroDivisionError):
            pass
        else:
            if expected_type is None or isinstance(val, expected_type):
                return val


def get_sid_cookies(cookies):
    yt_sapisid = try_call(lambda: cookies['SAPISID'])
    yt_3papisid = try_call(lambda: cookies['__Secure-3PAPISID'])
    yt_1papisid = try_call(lambda: cookies['__Secure-1PAPISID'])
    return yt_sapisid or yt_3papisid, yt_1papisid, yt_3papisid

def make_sid_authorization(scheme, sid, origin, additional_parts):
    timestamp = str(round(time.time()))
    hash_parts = []
    if additional_parts:
        hash_parts.append(':'.join(additional_parts.values()))
    hash_parts.extend([timestamp, sid, origin])
    sidhash = hashlib.sha1(' '.join(hash_parts).encode()).hexdigest()
    parts = [timestamp, sidhash]
    if additional_parts:
        parts.append(''.join(additional_parts))
    return f'{scheme} {"_".join(parts)}'

def auth_header(cookies, origin='https://www.youtube.com', user_session_id=None):
    '''Authorization header.'''
    if not cookies: return None

    authorizations = []
    additional_parts = {}
    if user_session_id:
        additional_parts['u'] = user_session_id

    yt_sapisid, yt_1psapisid, yt_3psapisid = get_sid_cookies(cookies)
    if all(s is None for s in [yt_sapisid, yt_1psapisid, yt_3psapisid]):
        raise SignInError('Cookies does not contain auth data.')

    for scheme, sid in (('SAPISIDHASH', yt_sapisid),
                        ('SAPISID1PHASH', yt_1psapisid),
                        ('SAPISID3PHASH', yt_3psapisid)):
        if sid:
            authorizations.append(make_sid_authorization(scheme, sid, origin, additional_parts))
    if not authorizations:
        return None
    return ' '.join(authorizations)

