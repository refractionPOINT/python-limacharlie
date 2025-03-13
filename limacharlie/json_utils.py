"""
Module which contains utils for parsing JSON.

Functions exposed here are made compatible with stdlib json mode, but they utilize orjson
for better performance.
"""

import orjson

def dumps(obj, *, default=None, option=0, indent=None, sort_keys=False):
    option = 0

    if indent is not None:
        option |= orjson.OPT_INDENT_2

    if sort_keys:
        option |= orjson.OPT_SORT_KEYS

    return orjson.dumps(obj, default=default, option=option).decode('utf-8')

def loads(s):
    # Accept either str or bytes
    if isinstance(s, str):
        s = s.encode('utf-8')
    return orjson.loads(s)

def dump(obj, fp, **kwargs):
    fp.write(dumps(obj, **kwargs))

def load(fp):
    return loads(fp.read())