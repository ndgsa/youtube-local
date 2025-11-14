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
    solvers = ['', solver1, solver2, solver3, solver4]
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

@cachetools.func.lru_cache(maxsize=1)
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

SUPPORTED_RUNTIMES = ['node','deno']
SUPPORTED_RUNTIMES_MIN_SUPPORTED_VERSION = {'node': (18, 0, 0), 'deno': (1, 22, 1), 'bun': (1, 0, 31), 'ejs': (0, 1, 1)}
SUPPORTED_RUNTIMES_DETECT_VERSION_RE = {'node': r'^v(\S+)', 'deno': r'^deno (\S+)', 'bun': r'^(\S+)', 'ejs': r'^ejs (\S+)'}
g_js_runtime = get_js_runtime()

def _run_js_runtime_bytes(js_file, requests, js_format="file"):
    if not g_js_runtime:
        raise NameError('No js runtime is found. Install supported runtime [ node, deno ]')

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
    elif response_type == "po_token":
        k = ['visitorData', 'placeholderPoToken', 'poToken', 'integrityTokenData']
        k1 = ['integrityToken', 'estimatedTtlSecs', 'mintRefreshThreshold']
        if set(k) != set(output.keys()) or set(k1) != set(output.get('integrityTokenData').keys()):
            raise ValueError(f"Invalid response type '{response_type}'")
    elif response_type == "po_token_2":
        k = ['visitorData', 'poToken']
        if set(k) != set(output.keys()):
            raise ValueError(f"Invalid response type '{response_type}'")
    elif response_type == "po_token_3":
        k = ['poToken', 'integrityTokenData']
        k1 = ['integrityToken', 'estimatedTtlSecs', 'mintRefreshThreshold']
        if set(k) != set(output.keys()) or set(k1) != set(output.get('integrityTokenData').keys()):
            raise ValueError(f"Invalid response type '{response_type}'")
    elif response_type == "n_sig":
        if 'preprocessed_player' in output.keys(): k = ['type', 'responses', 'preprocessed_player']
        else: k = ['type', 'responses']
        k1 = ['type', 'data']
        if set(k) != set(output.keys()):
            raise ValueError(f"Invalid response type '{response_type}'")
        for i in output.get('responses'):
            if set(i.keys()) != set(k1):
                raise ValueError(f"Invalid response type '{response_type}'")
    elif response_type == "youtubei_signature_functions":
        pass

def _run_js_runtime_file(js_file, *args, js_format="file", response_format='json', response_type=None, timeout=30, custom_runtime=None):
    if not g_js_runtime:
        raise NameError('No js runtime is found. Install supported runtime [ node, deno ]')

    if not custom_runtime:
        js_runtime_name_from_path = os.path.basename(g_js_runtime).replace('.EXE', '') #os.path.splitext(os.path.basename(g_js_runtime))[0]
        if 'deno' == js_runtime_name_from_path: cmd = [g_js_runtime, 'run', '--allow-run', '--allow-net', js_file, *args,]
        elif 'node' == js_runtime_name_from_path: cmd = [g_js_runtime, js_file, *args]
        elif 'bun' == js_runtime_name_from_path: raise NotImplementedError('Bun is not supported.')
        else: raise NotImplementedError(f'No js runtime with name "{js_runtime_name_from_path}" available.')
    else:
        js_runtime_name_from_path = os.path.basename(custom_runtime).replace('.EXE', '')
        if 'ejs' == js_runtime_name_from_path: cmd = [custom_runtime, js_file, *args]
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



ejs_version = '0.8.0'
yt_solver_lib_sha256 = 'c55987fe697e5b9ee18830163f7af85327e9bb5c3e674b969d38c8d205eaa577'
yt_solver_core_sha256 = '18da6ce0758b416e7ae645084f4f8801f9f9d59d6c477c05eaa0ff94ebd8cc00'
@cachetools.func.lru_cache(maxsize=1)
def get_ejs():
    '''return ejs libraries path'''
    import importlib.util
    import importlib.resources
    from importlib.metadata import version
    import hashlib
    if importlib.util.find_spec('yt_dlp_ejs') is not None and version('yt_dlp_ejs') == ejs_version:
        '''use yt_dlp_ejs library if exists.'''
        import yt_dlp_ejs.yt.solver
        yt_solver_lib_file = (importlib.resources.files(yt_dlp_ejs.yt.solver) / "lib.min.js")
        yt_solver_core_file = (importlib.resources.files(yt_dlp_ejs.yt.solver) / "core.min.js")
    else:
        '''Download ejs library if not exists.'''
        yt_solver_lib_url = f"https://github.com/yt-dlp/ejs/releases/download/{ejs_version}/yt.solver.lib.min.js"
        yt_solver_lib_name = 'yt.solver.lib.min_' + ejs_version.replace('.', '') + '.js'
        yt_solver_core_url = f"https://github.com/yt-dlp/ejs/releases/download/{ejs_version}/yt.solver.core.min.js"
        yt_solver_core_name = 'yt.solver.core.min_' + ejs_version.replace('.', '') + '.js'
        yt_solver_dir = os.path.join(settings.other_dir, 'js', 'ejs')
        yt_solver_lib_file = os.path.join(yt_solver_dir, yt_solver_lib_name)
        yt_solver_core_file = os.path.join(yt_solver_dir, yt_solver_core_name)
        if not os.path.isdir(yt_solver_dir):
            print(f'Creating {yt_solver_dir} directory')
            os.makedirs(yt_solver_dir)
        for yt_s in [{'file': yt_solver_lib_file, 'url': yt_solver_lib_url}, {'file': yt_solver_core_file, 'url': yt_solver_core_url}]:
            if not os.path.isfile(yt_s['file']):
                try: content = util.fetch_url(yt_s['url'], report_text=f"Downloading ejs library from url \"{yt_s['url']}\"")
                except: content = None
                if content:
                    if hashlib.sha256(content).hexdigest() not in [yt_solver_lib_sha256, yt_solver_core_sha256]:
                        raise Exception(f"Error: '{yt_s['url']}' has wrong hash: {hashlib.sha256(content).hexdigest()}")
                    with open(yt_s['file'], 'w', encoding='utf-8') as file:
                        print(f"Saving ejs library to \"{yt_s['file']}\"")
                        file.write(content.decode('utf-8'))
                else:
                    return ('', f'Unable to download ejs library', False)
    if not os.path.isfile(yt_solver_lib_file):
        return ('', f'{yt_solver_lib_name} library not available', False)
    if not os.path.isfile(yt_solver_core_file):
        return ('', f'{yt_solver_core_name} library not available', False)
    return (yt_solver_lib_file, yt_solver_core_file, True)

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

        yt_solver_lib_file, yt_solver_core_file, err = get_ejs()
        if err == False: return yt_solver_core_file

        n_sig_list, s_sig_list = extract_encrypted_n_s_signatures_from_info(info)

        # solve signatures using javascript runtime as 'node', 'deno', ...
        decrypted_nsig, decrypted_ssig = decrypt_nsig_ssig(info, yt_solver_lib_file, yt_solver_core_file, list(n_sig_list), list(s_sig_list))
        if type(decrypted_nsig) == str and decrypted_ssig == False: return decrypted_nsig # things goes wrong

        replace_n_s_signatures(info, decrypted_nsig, decrypted_ssig)

        return False

    def decrypt_nsig_ssig(info, yt_solver_lib_file, yt_solver_core_file, n_sig_list, s_sig_list):
        '''return error string, or set of 2 dict if no errors'''

        js_dir = os.path.join(settings.other_dir, 'js')
        if not os.path.isdir(js_dir): os.makedirs(js_dir)
        preprocessed_js_file = os.path.join(settings.players_cache_dir, 'iframe_api_base_' + info.get('player_version') + '_preprocessed' + '.js')

        if not os.path.exists(js_dir):
            return (f"Folder '{js_dir}\\' does not exist", False)
        elif not os.path.exists(yt_solver_lib_file):
            return (f"File '{yt_solver_lib_file}' does not exist", False)
        elif not os.path.exists(yt_solver_core_file):
            return (f"File '{yt_solver_core_file}' does not exist", False)

        requests = [{'type': 'n', 'challenges': n_sig_list}, {'type': 'sig', 'challenges': s_sig_list}]
        if not os.path.isfile(preprocessed_js_file):
            preprocessed = False
            with open(yt_solver_lib_file, 'r', encoding="utf8") as f: _lib_script_code = f.read()
            with open(yt_solver_core_file, 'r', encoding="utf8") as f: _core_script_code = f.read()
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



youtubei_version = '17.0.1'
@cachetools.func.lru_cache(maxsize=1)
def get_youtubei(use_js_runtime=False):
    '''Download youtubei.js library if not exists.'''
    youtubei_url = f"https://cdn.jsdelivr.net/npm/youtubei.js@{youtubei_version}/bundle/browser.min.js"
    if use_js_runtime: youtubei_name = 'youtubei_' + youtubei_version.replace('.', '') + '.js'
    else: youtubei_name = 'youtubei.min.js'
    youtubei_dir = os.path.join(settings.other_dir, 'js', 'youtubei')
    youtubei_file = os.path.join(youtubei_dir, youtubei_name)
    additional_js_code = '''(async function () {let args; let innertube; let player_version; if (typeof Deno !== 'undefined'){args = Deno.args;} else if (typeof Bun !== 'undefined'){args = Bun.args;} else {args = process.argv.slice(2);}; try{if (args.length === 0){innertube = await Innertube.create({'client': 'TV', 'lang': 'en'}); player_version = innertube.session.player.player_id;} else if (args.length === 1) {player_version = args[0]; if (player_version.length != 8) {throw new Error('player_version is not valid');}; innertube = await Innertube.create({'client': 'TV', 'lang': 'en', 'retrieve_player': 'true', 'player_id': player_version});};} catch (innertube_error){console.error(innertube_error);return;}; const session_info = {}; session_info.data = innertube.session.player.data; session_info.player_version = player_version; console.log(JSON.stringify(session_info));})();'''
    if not os.path.isdir(youtubei_dir):
        print(f'Creating {youtubei_dir} directory')
        os.makedirs(youtubei_dir)
    if not os.path.isfile(youtubei_file):
        try: content = util.fetch_url(youtubei_url, report_text=f'Downloading youtubei.js library from url "{youtubei_url}"')
        except: content = None
        if content:
            with open(youtubei_file, 'w', encoding='utf-8') as file:
                print(f'Saving youtubei.js library to "{youtubei_file}"')
                if youtubei_name == 'youtubei.min.js':
                    file.write(content.decode('utf-8'))
                else:
                    file.write(f"{content.decode('utf-8')}\n{additional_js_code}")
        else:
            return (f'Unable to download youtubei.js library', False)
    if not os.path.isfile(youtubei_file):
        return (f'{youtubei_name} library not available', False)
    with open(youtubei_file, 'r', encoding='utf-8') as file:
        if youtubei_name != 'youtubei.min.js' and additional_js_code not in file.read():
            with open(youtubei_file, 'a', encoding='utf-8') as file2:
                print(f'Append additional_js_code to "{youtubei_file}"')
                file2.write(f"\n{additional_js_code}")
    return (youtubei_file, True)

@cachetools.func.lru_cache(maxsize=1)
def get_decrypt_session_dukpy(decryption_function):
    import dukpy # on win7 and lower cause error, so use vxkex
    # Load decryption function into dukpy session
    decrypt_session_dukpy = dukpy.JSInterpreter()
    decrypt_session_dukpy.evaljs(decryption_function)
    return decrypt_session_dukpy

@cachetools.func.lru_cache(maxsize=1)
def load_decryption_function(decrypt_function_cache):
    if os.path.isfile(decrypt_function_cache):
        with open(decrypt_function_cache, 'r') as file:
            print(f'Loading decryption function from cache {os.path.basename(decrypt_function_cache)}')
            decrypt_function_js = file.read()
            return decrypt_function_js
    return None

def solver2(info):
    '''return error string, or False if no errors'''

    def solve_(info):
        err = check_requirements(info)
        if err != None: return err

        youtubei_file, err = get_youtubei(use_js_runtime=True)
        if err == False: return youtubei_file

        decrypt_function_cache, err = extract_decryption_function(info, youtubei_file)
        if err == False: return decrypt_function_cache

        n_sig_list, s_sig_list = extract_encrypted_n_s_signatures_from_info(info)

        # solve signatures using dukpy
        decrypted_nsig, decrypted_ssig = decrypt_nsig_ssig(info, decrypt_function_cache, list(n_sig_list), list(s_sig_list))
        if type(decrypted_nsig) == str and decrypted_ssig == False: return decrypted_nsig # things goes wrong

        replace_n_s_signatures(info, decrypted_nsig, decrypted_ssig)

        return False

    def extract_decryption_function(info, youtubei_file):
        '''Insert decryption function into info. Return error string if not successful.'''
        youtubei_signature_generator = os.path.join(os.path.dirname(youtubei_file), 'youtubei_signature.js')
        decrypt_function_cache = os.path.join(settings.players_cache_dir, f'''signature_func_{info['player_version']}.js''')
        info['decryption_function'] = None

        # additional_js_code = '''function decipher_signatures(n="",sp="",s=""){const mockStreamingURL="https://ytjs.googlevideo.com/videoplayback?expire=1234567890&"+"n="+encodeURIComponent(n); const urlCtorFunction=exportedVars.nsigFunction || (() => {throw new Error('No n/sig decipher function extracted')}); const urlCtor=urlCtorFunction(mockStreamingURL,sp,encodeURIComponent(s)); for(const prop of Object.getOwnPropertyNames(Object.getPrototypeOf(urlCtor))){if(['constructor','clone','set','get'].includes(prop)){continue;}; if(typeof urlCtor[prop] === 'function'){urlCtor[prop]();};}; const sigResult=urlCtor.get(sp); const nResult=urlCtor.get('n'); return {sig: sigResult ? decodeURIComponent(sigResult) : undefined, n: nResult ? decodeURIComponent(nResult) : undefined};};\nfunction resolve_signatures(n_sig_list, s_sig_list){var result = {}; const n_sig_result = {}; const s_sig_result={}; try {for(n_c in n_sig_list){n_sig_result[n_sig_list[n_c]]=decipher_signatures(n_sig_list[n_c]).n;}; for(sig_c in s_sig_list){s_sig_result[s_sig_list[sig_c]]=decipher_signatures('','sig',s_sig_list[sig_c]).sig;};} catch (decryption_error) {console.error(decryption_error); return;}; const n_sig_responses={'type':'result','data':n_sig_result,}; const s_sig_responses={'type':'result','data':s_sig_result,}; result['type']='result'; result['responses']=[n_sig_responses,s_sig_responses]; return result;};''' # dukpy < 0.6.0
        additional_js_code = '''function decipher_signatures(n="",sp="",s=""){const mockStreamingURL="https://ytjs.googlevideo.com/videoplayback?expire=1234567890&"+"n="+encodeURIComponent(n); const urlCtorFunction=exportedVars.nsigFunction || (() => {throw new Error('No n/sig decipher function extracted')}); const urlCtor=urlCtorFunction(mockStreamingURL,sp,encodeURIComponent(s)); for(const prop of Object.getOwnPropertyNames(Object.getPrototypeOf(urlCtor))){if(['constructor','clone','set','get'].includes(prop)){continue;}; if(typeof urlCtor[prop] === 'function'){urlCtor[prop]();};}; const sigResult=urlCtor.get(sp); const nResult=urlCtor.get('n'); return {sig: sigResult ? decodeURIComponent(sigResult) : undefined, n: nResult ? decodeURIComponent(nResult) : undefined};};\nfunction resolve_signatures(json_requests) {let challenges = []; let result = {}; result['type']='result'; result['responses'] = []; challenges = JSON.parse(json_requests); try{for(const challenge of challenges){let challenge_result = {}; if (challenge['type'] === 'n'){for(const n_c of challenge['challenges']){challenge_result[n_c]=decipher_signatures(n_c).n;};} else if (challenge['type'] === 'sig'){for(const s_c of challenge['challenges']){challenge_result[s_c]=decipher_signatures('','sig',s_c).sig;};}; result['responses'].push({'type':'result','data':challenge_result});};} catch (decryption_error){console.error(decryption_error);return;}; return result;};'''

        if not os.path.isfile(decrypt_function_cache):
            # output = _run_js_runtime_file(youtubei_signature_generator, info['player_version'], response_type='pass') # dukpy < 0.6.0
            output = _run_js_runtime_file(youtubei_file, info['player_version'], response_type='pass')
            if output.get('data'):
                if output['data'].get('output'):
                    print(f'Saving decryption function to {os.path.basename(decrypt_function_cache)}')
                    with open(decrypt_function_cache, 'w') as file: file.write(f"{output['data'].get('output')}\n{additional_js_code}")

            if output.get('player_id'):
                # If generated signature function returns another player_id
                if info['player_version'] != output.get('player_id'):
                    player_data = util.get_player_data(client=info['__client_name'], player_version=output.get('player_id'), include_basejs=True)
                    info['player_version'] = output.get('player_id')
                    info['base_js'] = player_data['player_url']
                    info['player_name'] = player_data['player_name']

        if not os.path.isfile(decrypt_function_cache):
            return (f'No decryption function file is found', False)

        info ['decryption_function'] = load_decryption_function(decrypt_function_cache)

        return (decrypt_function_cache, True)

    def decrypt_nsig_ssig(info, decrypt_function_cache, n_sig_list, s_sig_list):
        '''Applies info['decryption_function'] to decrypt all the signatures. Return err.'''
        if not info.get('decryption_function'):
            return (f"decryption_function not in info", False)

        decrypt_session_dukpy = get_decrypt_session_dukpy(info['decryption_function'])
        # dukpy < 0.6.0
        # decrypt_signature_dukpy = '''resolve_signatures(dukpy['n_sig_list'], dukpy['s_sig_list'])'''
        # output = decrypt_session_dukpy.evaljs(decrypt_signature_dukpy, n_sig_list=n_sig_list, s_sig_list=s_sig_list)
        json_requests = [
            {'type': 'n', 'challenges': n_sig_list, 'video_id': info['id'], 'player_version': info.get('player_version')},
            {'type': 'sig', 'challenges': s_sig_list, 'video_id': info['id'], 'player_version': info.get('player_version')},
        ]
        json_requests = json.dumps(json_requests)
        decrypt_signature_dukpy = '''resolve_signatures(dukpy['json_requests'])'''
        output = decrypt_session_dukpy.evaljs(decrypt_signature_dukpy, json_requests=json_requests)
        del decrypt_session_dukpy

        responses = output.get('responses', [])
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



def solver3(info):
    '''return error string, or False if no errors'''

    def solve_(info):
        err = check_requirements(info)
        if err != None: return err

        youtubei_file, err = get_youtubei(use_js_runtime=True)
        if err == False: return youtubei_file

        decrypt_function_cache, err = extract_decryption_function(info, youtubei_file)
        if err == False: return decrypt_function_cache

        n_sig_list, s_sig_list = extract_encrypted_n_s_signatures_from_info(info)

        # solve signatures using dukpy
        decrypted_nsig, decrypted_ssig = decrypt_nsig_ssig(info, decrypt_function_cache, list(n_sig_list), list(s_sig_list))
        if type(decrypted_nsig) == str and decrypted_ssig == False: return decrypted_nsig # things goes wrong

        replace_n_s_signatures(info, decrypted_nsig, decrypted_ssig)

        return False

    def extract_decryption_function(info, youtubei_file):
        '''Insert decryption function into info. Return error string if not successful.'''
        decrypt_function_cache = os.path.join(settings.players_cache_dir, f'''signature_func_{info['player_version']}_r.js''')
        info['decryption_function'] = None

        additional_js_code = '''function decipher_signatures(n="",sp="",s=""){const mockStreamingURL="https://ytjs.googlevideo.com/videoplayback?expire=1234567890&"+"n="+encodeURIComponent(n); const urlCtorFunction=exportedVars.nsigFunction || (() => {throw new Error('No n/sig decipher function extracted')}); const urlCtor=urlCtorFunction(mockStreamingURL,sp,encodeURIComponent(s)); for(const prop of Object.getOwnPropertyNames(Object.getPrototypeOf(urlCtor))){if(['constructor','clone','set','get'].includes(prop)){continue;}; if(typeof urlCtor[prop] === 'function'){urlCtor[prop]();};}; const sigResult=urlCtor.get(sp); const nResult=urlCtor.get('n'); return {sig: sigResult ? decodeURIComponent(sigResult) : undefined, n: nResult ? decodeURIComponent(nResult) : undefined};};\n(function () {let args; let challenges = []; let result = {}; result['type']='result'; result['responses'] = []; if (typeof Deno !== 'undefined'){args = Deno.args;} else if (typeof Bun !== 'undefined'){args = Bun.args;} else {args = process.argv.slice(2);}; if (args.length === 1){challenges = JSON.parse(args[0]);} else {console.log(JSON.stringify(result)); return;}; try{for(const challenge of challenges){let challenge_result = {}; if (challenge['type'] === 'n'){for(const n_c of challenge['challenges']){challenge_result[n_c]=decipher_signatures(n_c).n;};} else if (challenge['type'] === 'sig'){for(const s_c of challenge['challenges']){challenge_result[s_c]=decipher_signatures('','sig',s_c).sig;};}; result['responses'].push({'type':'result','data':challenge_result});};} catch (decryption_error){console.error(decryption_error);return;}; console.log(JSON.stringify(result));})();'''

        if not os.path.isfile(decrypt_function_cache):
            output = _run_js_runtime_file(youtubei_file, info['player_version'], response_type='pass')
            if output.get('data'):
                if output['data'].get('output'):
                    with open(decrypt_function_cache, 'w') as file:
                        print(f'Saving decryption function to {os.path.basename(decrypt_function_cache)}')
                        file.write(f"{output['data'].get('output')}\n{additional_js_code}")

            if output.get('player_id'):
                # If generated signature function returns another player_id
                if info['player_version'] != output.get('player_id'):
                    player_data = util.get_player_data(client=info['__client_name'], player_version=output.get('player_id'), include_basejs=True)
                    info['player_version'] = output.get('player_id')
                    info['base_js'] = player_data['player_url']
                    info['player_name'] = player_data['player_name']

        if not os.path.isfile(decrypt_function_cache):
            return (f'No decryption function file is found', False)

        return (decrypt_function_cache, True)

    def decrypt_nsig_ssig(info, decrypt_function_cache, n_sig_list, s_sig_list):
        '''Decrypt all the signatures. Return err.'''
        json_requests = [
            {'type': 'n', 'challenges': n_sig_list, 'video_id': info['id'], 'player_version': info.get('player_version')},
            {'type': 'sig', 'challenges': s_sig_list, 'video_id': info['id'], 'player_version': info.get('player_version')},
        ]
        json_requests = json.dumps(json_requests, separators=(',', ':'), indent=None) # crap
        output = _run_js_runtime_file(decrypt_function_cache, json_requests, response_type='n_sig')

        responses = output.get('responses', [])
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



def solver4(info):
    '''return error string, or False if no errors'''

    def solve_(info):
        err = check_requirements(info)
        if err != None: return err

        try: custom_runtime = find_executable('ejs')[0]
        except: return ("EJS runtime is not installed", False)

        n_sig_list, s_sig_list = extract_encrypted_n_s_signatures_from_info(info)

        # solve signatures using javascript runtime as 'node', 'deno', ...
        decrypted_nsig, decrypted_ssig = decrypt_nsig_ssig(info, list(n_sig_list), list(s_sig_list), custom_runtime)
        if type(decrypted_nsig) == str and decrypted_ssig == False: return decrypted_nsig # things goes wrong

        replace_n_s_signatures(info, decrypted_nsig, decrypted_ssig)

        return False

    def decrypt_nsig_ssig(info, n_sig_list, s_sig_list, custom_runtime):
        '''return error string, or set of 2 dict if no errors'''
        player_name = util.get_player_data(client=info['__client_name'], include_basejs=False)['player_name']
        requests = []
        for n in n_sig_list: requests.append(f"n:{n}")
        for sig in s_sig_list: requests.append(f"sig:{sig}")

        output = _run_js_runtime_file(player_name, *requests, response_type='n_sig', custom_runtime=custom_runtime)

        responses = output.get('responses', [])

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

