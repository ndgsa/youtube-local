import settings
from .. import util
# from youtube import util

import os
import sys
import json
import re
import shutil
import subprocess
import urllib.parse
import cachetools.func


def signature_solver(s, info):
    solvers = ['', solver1]
    return solvers[int(s)](info)


def requires_decryption(info):
    return ('formats' in info) and info['formats'] and info['formats'][0]['s']


class Popen(subprocess.Popen):
    if sys.platform == 'win32':
        _startupinfo = subprocess.STARTUPINFO()
        _startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    else:
        _startupinfo = None

    def __init__(self, args, *remaining, env=None, text=False, shell=False, **kwargs):
        if env is None:
            env = os.environ.copy()

        self.__text_mode = kwargs.get('encoding') or kwargs.get('errors') or text or kwargs.get('universal_newlines')
        if text is True:
            kwargs['universal_newlines'] = True  # For 3.6 compatibility
            kwargs.setdefault('encoding', 'utf-8')
            kwargs.setdefault('errors', 'replace')

        super().__init__(args, *remaining, env=env, shell=shell, **kwargs, startupinfo=self._startupinfo)

    def communicate_or_kill(self, *args, **kwargs):
        try:
            return self.communicate(*args, **kwargs)
        except BaseException:  # Including KeyboardInterrupt
            self.kill(timeout=None)
            raise

    def kill(self, *, timeout=0):
        print('kill')
        super().kill()
        if timeout != 0:
            self.wait(timeout=timeout)

    @classmethod
    def run(cls, *args, timeout=None, **kwargs):
        with cls(*args, **kwargs) as proc:
            default = '' if proc.__text_mode else b''
            stdout, stderr = proc.communicate_or_kill(timeout=timeout)
            return stdout or default, stderr or default, proc.returncode

def find_executable(executable_name):
    """Search for an executable in the system path"""
    # print(os.path.realpath(shutil.which('node', mode=os.F_OK | os.X_OK, path=os.environ["PATH"])))
    executable_path_list = []
    js_dir = os.path.join(settings.other_dir, 'js', '_node')
    if not os.path.isdir(js_dir): os.makedirs(js_dir)
    if os.name == "nt": executable_name = executable_name + '.EXE'
    for directory in os.get_exec_path() + [js_dir]:
        executable_path = os.path.join(directory, executable_name)
        if os.path.isfile(executable_path) and os.access(executable_path, os.X_OK):
           executable_path_list.append(executable_path)
    if len(executable_path_list) == 0: return [] # None
    executable_path_list.reverse()
    return executable_path_list # [-1] if multiple occourences

def check_executable(runtime_path, runtime_name):
    if runtime_name not in SUPPORTED_RUNTIMES_MIN_SUPPORTED_VERSION.keys():
        raise NameError(f"Unsupported js runtime: {runtime_name}")

    version_re = SUPPORTED_RUNTIMES_DETECT_VERSION_RE.get(runtime_name)
    try:
        stdout, _, ret = Popen.run(
            [runtime_path, '--version'],
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
    except OSError: return None
    if not ret:
        assert isinstance(stdout, str)
        if version_re is None: version_re = r'version\s+([-0-9._a-zA-Z]+)'
        m = re.search(version_re, stdout)
        if m:
            version = m.group(1)
            vt = []
            for x in version.split('.'):
                try: v = int(x)
                except (ValueError, TypeError, OverflowError): v = 0
                vt.append(v)
            vt = tuple(vt)
            return {
                'name': runtime_name,
                'path': runtime_path,
                'version':version,
                'version_tuple':vt,
                'supported': vt >= SUPPORTED_RUNTIMES_MIN_SUPPORTED_VERSION[runtime_name],
            }
    return None

def get_js_runtime():
    for runtime_name in SUPPORTED_RUNTIMES:
        for runtime_path in find_executable(runtime_name):
            runtime = check_executable(runtime_path, runtime_name)
            if runtime and runtime.get('supported'):
                print(f"Using js runtime: {runtime['name']} v{runtime['version']}")
                return runtime['path']
    print('No js runtime is found')
    return None

SUPPORTED_RUNTIMES = ['node','deno', 'bun']
SUPPORTED_RUNTIMES_MIN_SUPPORTED_VERSION = {'node': (18, 0, 0), 'deno': (1, 22, 1), 'bun': (1, 0, 31)}
SUPPORTED_RUNTIMES_DETECT_VERSION_RE = {'node': r'^v(\S+)', 'deno': r'^deno (\S+)', 'bun': r'^(\S+)'}
g_js_runtime = get_js_runtime()

def _run_js_runtime_bytes(js_file, requests, js_format="file"):
    if not g_js_runtime:
        raise NameError('No js runtime is found. Install supported runtime [ node, deno, bun ]')

    jscode = ""

    if js_format == "file":
        flag = 'rb'
        jscode = read_preprocessed_js_file(js_file, flag, None)
    elif js_format == "bytes":
        flag = 'r'
        jscode = read_preprocessed_js_file(js_file, flag, "utf-8")
        jscode = re.sub(r'''(\[\{"type": "n", .+\}\])''', json.dumps(requests), jscode)
        jscode = jscode.encode("utf-8")

    cmd = [g_js_runtime, '-']
    with Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        stdout, stderr = process.communicate_or_kill(jscode)
        if process.returncode == 0:
            output = json.loads(stdout)
        if process.returncode or stderr:
            msg = f"Error running {os.path.basename(g_js_runtime).replace('.EXE', '')} process"
            if stderr: msg = f'{msg}: {stderr}'
            raise Exception(msg)

    return output

def validate_json(string):
    try:
        string = json.loads(string)
    except ValueError as err:
        raise Exception(f"Bad json: {err}")
    return string

def validate_response_type(output, response_type):
    # check returned values
    if response_type == None:
        raise NotImplementedError('Request type not specified')
    elif response_type == 'pass': # in case dont require or is different
        pass
    elif response_type == "n_sig":
        if 'preprocessed_player' in output.keys(): k = ['type', 'responses', 'preprocessed_player']
        else: k = ['type', 'responses']
        k1 = ['type', 'data']
        if set(k) != set(output.keys()):
            raise ValueError(f"Invalid response type '{response_type}'")
        for i in output.get('responses'):
            if set(i.keys()) != set(k1):
                raise ValueError(f"Invalid response type '{response_type}'")

def _run_js_runtime_file(js_file, *args, js_format="file", response_format='json', response_type=None, timeout=30):
    if not g_js_runtime:
        raise NameError('No js runtime is found. Install supported runtime [ node, deno, bun ]')

    js_runtime_name_from_path = os.path.basename(g_js_runtime).replace('.EXE', '') #os.path.splitext(os.path.basename(g_js_runtime))[0]
    if 'deno' == js_runtime_name_from_path: cmd = [g_js_runtime, 'run', '--allow-run', '--allow-net', js_file, *args,]
    elif 'node' == js_runtime_name_from_path: cmd = [g_js_runtime, js_file, *args]
    elif 'bun' == js_runtime_name_from_path: raise NotImplementedError('Bun is not supported.')
    else: raise NotImplementedError(f'No js runtime with name "{js_runtime_name_from_path}" available.')

    # process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # stdout, stderr = process.communicate()
    with Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        stdout, stderr = process.communicate_or_kill(timeout=timeout)
        output = None
        if process.returncode == 0 and not stderr:
            output = stdout.decode()
        elif process.returncode or stderr:
            # output = stderr.decode()
            msg = f"Error running {os.path.basename(g_js_runtime).replace('.EXE', '')} process"
            if stderr: msg = f'{msg}: {stderr.decode()}'
            raise Exception(msg)

    # check if decoded string is json format
    if response_format == 'json':
        output = validate_json(output)
        validate_response_type(output, response_type=response_type) # check if response correspond
    else:
        print(output)
        raise NotImplementedError('Response format not implemented')

    return output


def check_requirements(info):
    client, client_params = util.get_innertube_client(client_name=settings.innertube_client_name)

    if not client_params.get('REQUIRE_JS_PLAYER'):
        print("n_sig decryption is not needed for innertube client: " + client)
        return False

    player_name = info.get('player_name')
    player_version = info.get('player_version')

    if not player_name:
        return "Could not find player name"
    elif not player_version:
        return "Unable to determine player version"

    return None

def extract_encrypted_n_s_signatures_from_info(info):
    n_sig = None
    n_sig_list = set()
    s_sig_list = set()
    for fmt in info['formats']:
        # add 'n=' to n_sig_list
        if fmt['url']:
            for member in fmt['url'].split('&'):
                if member.startswith('n='): n_sig_list.add(member.split('=')[1])
        # # add 's' to s_sig_list
        if fmt['s'] and fmt['sp'] and fmt['url']: s_sig_list.add(fmt['s'])

    return (n_sig_list, s_sig_list)

def replace_n_s_signatures(info, decrypted_nsig, decrypted_ssig):
    n_sig = None
    for fmt in info['formats']:
        if fmt['url']:
            media_url = fmt['url']
            params = media_url.split('&')
            for i, member in enumerate(params):
                if member.startswith('n='):
                    n_sig_index = i
                    n_sig = member.split('=')[1]

            if decrypted_nsig.get(n_sig):
                n_sig_result = decrypted_nsig.get(n_sig)
                params.pop(n_sig_index)
                params.insert(n_sig_index, 'n=' + n_sig_result) # replace n signature
                final_url = '&'.join(params)
                fmt['url'] = final_url
            else:
                print("n_sig_decrypt: Warning nsig not available")

        if fmt['s'] and fmt['sp'] and fmt['url']:
            if decrypted_ssig.get(fmt['s']):
                s_sig_result = decrypted_ssig.get(fmt['s'])
                fmt['url'] += '&' + fmt['sp'] + '=' + urllib.parse.quote(s_sig_result) # replace s signature
            else:
                print("n_sig_decrypt: Warning ssig not available")
    return False



@cachetools.func.lru_cache(maxsize=2)
def read_preprocessed_js_file(preprocessed_js_file, flag, encoding):
    with open(preprocessed_js_file, flag, encoding=encoding) as f:
        player = f.read()
    print("n_sig_decrypt: Using preprocessed player")
    return player

def solver1(info):
    '''return error string, or False if no errors'''

    def solve_(info):
        err = check_requirements(info)
        if err != None: return err

        n_sig_list, s_sig_list = extract_encrypted_n_s_signatures_from_info(info)

        # solve signatures using javascript runtime as 'node', 'deno', ...
        decrypted_nsig, decrypted_ssig = decrypt_nsig_ssig(info, list(n_sig_list), list(s_sig_list))
        if type(decrypted_nsig) == str and decrypted_ssig == False: return decrypted_nsig # things goes wrong

        replace_n_s_signatures(info, decrypted_nsig, decrypted_ssig)

        return False

    def decrypt_nsig_ssig(info, n_sig_list, s_sig_list):
        '''return error string, or set of 2 dict if no errors'''

        js_dir = os.path.join(settings.other_dir, 'js')
        if not os.path.isdir(js_dir): os.makedirs(js_dir)
        lib_js_file = os.path.join(js_dir, 'ejs', 'yt.solver.lib.min.js')
        core_js_file = os.path.join(js_dir, 'ejs', 'yt.solver.core.min.js')
        preprocessed_js_file = os.path.join(settings.players_cache_dir, 'iframe_api_base_' + info.get('player_version') + '_preprocessed' + '.js')

        if not os.path.exists(js_dir):
            return (f"Folder '{js_dir}\\' does not exist", False)
        elif not os.path.exists(lib_js_file):
            return (f"File '{lib_js_file}' does not exist", False)
        elif not os.path.exists(core_js_file):
            return (f"File '{core_js_file}' does not exist", False)

        requests = [{'type': 'n', 'challenges': n_sig_list}, {'type': 'sig', 'challenges': s_sig_list}]
        if not os.path.isfile(preprocessed_js_file):
            preprocessed = False
            with open(lib_js_file, 'r', encoding="utf8") as f: _lib_script_code = f.read()
            with open(core_js_file, 'r', encoding="utf8") as f: _core_script_code = f.read()
            player = util.get_player_data(client=info['__client_name'], include_basejs=True)['base_js']
            data = {
                'type': 'player',
                'player': player,
                'requests': requests,
                'output_preprocessed': True, # if True then returns preprocessed player javascript code
            }
            jscode = f'''{_lib_script_code}
Object.assign(globalThis, lib);
{_core_script_code}
var result = jsc({json.dumps(data)});
console.log(JSON.stringify(result));
'''
            with open(preprocessed_js_file, 'w', encoding="utf-8") as f: f.write(jscode)
        else:
            preprocessed = True
            # replace 'requests' in preprocessed_js_file
            with open(preprocessed_js_file, 'r+', encoding="utf-8") as f:
                js_file = f.read()
                js_file = re.sub(r'''(\[\{"type": "n", .+\}\])''', json.dumps(requests), js_file)
                f.seek(0)
                f.write(js_file)
                f.truncate()
            print("n_sig_decrypt: Using preprocessed player")

        # output = _run_js_runtime_bytes(g_js_runtime, preprocessed_js_file, requests, js_format="bytes")
        output = _run_js_runtime_file(preprocessed_js_file, response_type='n_sig')

        responses = output.get('responses', [])

        # print(f"nsig: {responses[0]}\nssig: {responses[1]}")

        if not preprocessed:
            data = {'type': 'preprocessed', 'preprocessed_player': output.get('preprocessed_player'), 'requests': requests,}
            jscode = f'''{_lib_script_code}
Object.assign(globalThis, lib);
{_core_script_code}
var result = jsc({json.dumps(data)});
console.log(JSON.stringify(result));
'''
            with open(preprocessed_js_file, 'w', encoding="utf-8") as f: f.write(jscode)
            print("n_sig_decrypt: Write preprocessed_player to file")

        output = None

        if len(responses) != 2:
            return ("nsig or ssig decryption failed", False)

        n_resp = responses[0]
        if n_resp['type'] == 'error':
            return ("nsig decryption failed", False)
        n_sig_list = n_resp['data']

        s_resp = responses[1]
        if s_resp['type'] == 'error':
            return ("ssig decryption failed", False)
        s_sig_list = s_resp['data']

        return (n_sig_list, s_sig_list)


    err = solve_(info)
    return err

