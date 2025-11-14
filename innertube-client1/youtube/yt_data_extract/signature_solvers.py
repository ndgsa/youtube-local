import settings
from .. import util
# from youtube import util

import os
import sys
import json
import re
import urllib.parse


def signature_solver(s, info):
    solvers = ['']
    return "No signature solver available"


def requires_decryption(info):
    return ('formats' in info) and info['formats'] and info['formats'][0]['s']

