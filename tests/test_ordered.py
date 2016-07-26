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
    from = 0
    to = 100

    for value in range(from, to):
        cache.set(value, value)

    cache.check()

    assert cache.first() == from
    assert cache.last() == to

    cache.delete(from)
    cache.delete(to)

    cache.check()

    assert cache.first() == from+1
    assert cache.last() == to-1


if __name__ == '__main__':
    import nose
    nose.runmodule()
