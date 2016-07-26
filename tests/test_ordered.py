"Test diskcache.ordered.OrderedCache."

import errno
import functools as ft
import io
import mock
import nose.tools as nt
import os
import random
import shutil
import sqlite3
import sys
import threading
import time
import warnings

try:
    import cPickle as pickle
except:
    import pickle

import diskcache as dc

warnings.simplefilter('error')
warnings.simplefilter('ignore', category=dc.EmptyDirWarning)

if sys.hexversion < 0x03000000:
    range = xrange

def setup_cache(func):
    @ft.wraps(func)
    def wrapper():
        shutil.rmtree('tmp', ignore_errors=True)
        with dc.OrderedCache('tmp') as cache:
            func(cache)
        shutil.rmtree('tmp', ignore_errors=True)
    return wrapper


@setup_cache
def test_init(cache):
    for key, value in dc.DEFAULT_SETTINGS.items():
        assert getattr(cache, key) == value

    cache.check()

    for key, value in dc.DEFAULT_SETTINGS.items():
        setattr(cache, key, value)

    cache.check()


@setup_cache
def test_set_get(cache):
    start = 0
    end = 100

    for value in range(start, end + 1):
        cache.set(value, value)

    cache.check()

    assert cache.first() == start
    assert cache.last() == end

    assert cache.first(key=True)[0] == start
    assert cache.last(key=True)[0] == end

    cache.check()

    cache.delete(start)
    cache.delete(end)

    cache.check()

    assert cache.first() == start + 1
    assert cache.last() == end - 1

    assert cache.first(key=True)[0] == start + 1
    assert cache.last(key=True)[0] == end - 1

    cache.check()


if __name__ == '__main__':
    import nose
    nose.runmodule()
