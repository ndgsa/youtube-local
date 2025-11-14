import settings
from .. import util
# from youtube import util

import os
import sys
import json
import re


################################################################################ mine
def signature_solver(s, info):
    solvers = ['', solver1]
    return solvers[int(s)](info)


def requires_decryption(info):
    return ('formats' in info) and info['formats'] and info['formats'][0]['s']



# adapted from youtube-dl and invidious:
# https://github.com/omarroth/invidious/blob/master/src/invidious/helpers/signatures.cr
decrypt_function_re1 = re.compile(r'function\(a\)\{(a=a\.split\(""\)[^\}{]+)return a\.join\(""\)\}')
# gives us e.g. rt, .xK, 5 from rt.xK(a,5) or rt, ["xK"], 5 from rt["xK"](a,5)
# (var, operation, argument)
var_op_arg_re1 = re.compile(r'(\w+)(\.\w+|\["[^"]+"\])\(a,(\d+)\)')
def solver1(info):
    '''return error string, or False if no errors'''

    def save_decrypt_cache():
        try:
            f = open(os.path.join(settings.players_cache_dir, 'decrypt_function_cache.json'), 'w')
        except FileNotFoundError:
            os.makedirs(settings.players_cache_dir)
            f = open(os.path.join(settings.players_cache_dir, 'decrypt_function_cache.json'), 'w')

        f.write(json.dumps({'version': 1, 'decrypt_cache':decrypt_cache}, indent=4, sort_keys=True))
        f.close()

    def load_decrypt_cache():
        try:
            with open(os.path.join(settings.players_cache_dir, 'decrypt_function_cache.json'), 'r') as f:
                decrypt_cache = json.loads(f.read())['decrypt_cache']
        except FileNotFoundError:
            decrypt_cache = {}

        return decrypt_cache

    def extract_decryption_function(info, base_js):
        '''Insert decryption function into info. Return error string if not successful.
        Decryption function is a list of list[2] of numbers.
        It is advisable to cache the decryption function (uniquely identified by info['player_name']) so base.js (1 MB) doesn't need to be redownloaded each time'''
        info['decryption_function'] = None
        decrypt_function_match = decrypt_function_re1.search(base_js)
        if decrypt_function_match is None:
            return 'Could not find decryption function in base.js'

        function_body = decrypt_function_match.group(1).split(';')[1:-1]
        if not function_body:
            return 'Empty decryption function body'

        var_with_operation_match = var_op_arg_re1.fullmatch(function_body[0])
        if var_with_operation_match is None:
            return 'Could not find var_name'

        var_name = var_with_operation_match.group(1)
        var_body_match = re.search(r'var ' + re.escape(var_name) + r'=\{(.*?)\};', base_js, flags=re.DOTALL)
        if var_body_match is None:
            return 'Could not find var_body'

        operations = var_body_match.group(1).replace('\n', '').split('},')
        if not operations:
            return 'Did not find any definitions in var_body'
        operations[-1] = operations[-1][:-1]    # remove the trailing '}' since we split by '},' on the others
        operation_definitions = {}
        for op in operations:
            colon_index = op.find(':')
            opening_brace_index = op.find('{')

            if colon_index == -1 or opening_brace_index == -1:
                return 'Could not parse operation'
            op_name = op[:colon_index]
            op_body = op[opening_brace_index+1:]
            if op_body == 'a.reverse()':
                operation_definitions[op_name] = 0
            elif op_body == 'a.splice(0,b)':
                operation_definitions[op_name] = 1
            elif op_body.startswith('var c=a[0]'):
                operation_definitions[op_name] = 2
            else:
                return 'Unknown op_body: ' + op_body

        decryption_function = []
        for op_with_arg in function_body:
            match = var_op_arg_re1.fullmatch(op_with_arg)
            if match is None:
                return 'Could not parse operation with arg'
            op_name = match.group(2).strip('[].')
            if op_name not in operation_definitions:
                return 'Unknown op_name: ' + str(op_name)
            op_argument = match.group(3)
            decryption_function.append([operation_definitions[op_name], int(op_argument)])

        info['decryption_function'] = decryption_function
        return False

    def decrypt_signatures(info):
        '''Applies info['decryption_function'] to decrypt all the signatures. Return err.'''

        def _operation_2(a, b):
            c = a[0]
            a[0] = a[b % len(a)]
            a[b % len(a)] = c

        if not info.get('decryption_function'):
            return 'decryption_function not in info'
        for format in info['formats']:
            if not format['s'] or not format['sp'] or not format['url']:
                # print('Warning: s, sp, or url not in format')
                continue

            a = list(format['s'])
            for op, argument in info['decryption_function']:
                if op == 0:
                    a.reverse()
                elif op == 1:
                    a = a[argument:]
                else:
                    _operation_2(a, argument)

            signature = ''.join(a)
            format['url'] += '&' + format['sp'] + '=' + signature
        return False


    if not requires_decryption(info):
        return False
    if not info.get('player_name'):
        return 'Could not find player name'

    player_name = info.get('player_name')
    decrypt_cache = load_decrypt_cache()
    if player_name in decrypt_cache:
        print('Using cached decryption function for: ' + player_name)
        info['decryption_function'] = decrypt_cache[player_name]
    else:
        base_js = util.get_player_data(include_basejs=True)['base_js']
        err = extract_decryption_function(info, base_js)
        if err:
            return err
        decrypt_cache[player_name] = info['decryption_function']
        save_decrypt_cache()
    err = decrypt_signatures(info)
    return err
################################################################################

