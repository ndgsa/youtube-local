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
    solvers = ['']
    return "No signature solver available"


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
SUPPORTED_RUNTIMES_MIN_SUPPORTED_VERSION = {'node': (18, 0, 0), 'deno': (1, 22, 1), 'bun': (1, 0, 31)}
SUPPORTED_RUNTIMES_DETECT_VERSION_RE = {'node': r'^v(\S+)', 'deno': r'^deno (\S+)', 'bun': r'^(\S+)'}
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
        raise NotImplementedError(f'No js runtime with name "{js_runtime_name_from_path}" available.')

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

