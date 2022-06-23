from typing import Any, Callable
import re
from copy import deepcopy
from itertools import chain
from .enums import RelativeObjectLevel as ROL
from benedict import benedict
from benedict.dicts.keypath import keypath_util

def get(msg: dict, key: str, default: Any = None, then: Callable | None = None, drop_rol: ROL | None = None):
    res = nested_get(msg, key, default) \
        if '.' in key else single_get(msg, key, default)
    if res and callable(then):
        try:
            res = then(res)
        except Exception as e:
            raise RuntimeError(f'`then` callable failed when getting key: {key}, error: {e}')
    if drop_rol and res is None:
        res = drop_rol
    return res

def single_get(msg: dict, key: str, default: Any = None) -> Any:
    """
    Gets single item, supports int indexing, e.g. `someKey[0]`
    """
    res = msg
    idx = re.search(r'\[\d+\]', key)
    if idx:
        # TODO: consolidate str logic into shared functions
        #       E.g. have `_clean_idx` handle this case 
        idx_str = idx.group(0)
        i = int(idx_str[1:-1]) # Casts str->int, e.g. "[0]" -> 0
        key = key.replace(idx_str, '')
        res = res.get(key, [])
        res = res[i] if i in range(len(res)) else None
    elif key[-3:] == '[*]':
        res = res.get(key[:-3])
        res = _handle_ending_star_unwrap(res, key)
    else:
        res = res.get(key, default)
    return res


def nested_get(msg: dict, key: str, default: Any = None) -> Any:
    """
    Expects `.`-delimited string and tries to get the item in the dict.

    If the dict contains an array, the correct index is expected, e.g. for a dict d:
        d.a.b[0]
    will try d['a']['b'][0], where a should be a dict containing b which should be an array with at least 1 item

    If d[*] is passed, then that means return a list of all elements. E.g. for a dict d:
    d[*].a.b
    will try to get e['a']['b'] for e in d
    
    TODO: Add support for querying, maybe e.g. [?: thing.val==1]
    """
    if '.' not in key:
        return single_get(msg, key, default)
    stack = key.split('.')
    res = deepcopy(msg)
    while len(stack) > 0:
        k = stack.pop(0)
        # If need to unwrap, then empty stack 
        if k[-3:] == '[*]':
            k = k[:-3]
            remaining_key = '.'.join(stack)
            stack = [] # wipe stack for current run
            res = res.get(k)
            if remaining_key != '':
                res = [nested_get(v, remaining_key, None) for v in res]
        else:
            res = single_get(res, k)
        if res == None:
            break
    res = _handle_ending_star_unwrap(res, key)
    return res if res != None else default

def nested_delete(msg: benedict, key: str) -> dict:
    """
    Has same syntax as nested_get, except returns the original msg
    with the requested key set to `None`
    """
    res = deepcopy(msg)
    if type(res) == dict:
        res = benedict(res)
    nesting = keypath_util.parse_keys(key, '.')
    # Case: value has an ROL object
    v = get(res, key)
    if type(v) == ROL:
        assert v.value < 0
        nesting = nesting[:v.value]
    # Get up to the last key in nesting, then set that key to None
    #  We set to None instead of popping to preserve indices
    try:
        # TODO: Handle [*] case
        res[nesting] = None
    except Exception as e:
        raise IndexError(f'Failed to perform nested_delete on key: {key}, Error: {e}, Input: {msg}')
    return res

def _handle_ending_star_unwrap(res: dict, key: str) -> dict:
    # HACK: Handle unwrapping if specified at the end
    # TODO: Find a nicer way to do this. Works for now...
    if key[-3:] == '[*]' and type(res) == list and type(res[0]) == list:
        res = [l for l in res if l != None]
        res = list(chain(*res))
    return res