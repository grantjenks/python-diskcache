"Test diskcache.fanout.FanoutCache."

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
        with dc.FanoutCache('tmp') as cache:
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
def test_set_get_delete(cache):
    for value in range(100):
        cache.set(value, value)

    cache.check()

    for value in range(100):
        assert cache.get(value) == value

    cache.check()

    for value in range(100):
        assert value in cache

    cache.check()

    for value in range(100):
        assert cache.delete(value)
    assert cache.delete(100) == False

    cache.check()

    for value in range(100):
        cache[value] = value

    cache.check()

    for value in range(100):
        assert cache[value] == value

    cache.check()

    cache.clear()
    assert len(cache) == 0

    cache.check()


def test_operationalerror():
    cache = dc.FanoutCache('tmp', shards=1)

    shards = mock.Mock()
    shards.__getitem__ = mock.Mock(side_effect=sqlite3.OperationalError)

    object.__setattr__(cache, '_shards', shards)

    assert cache.set(0, 0) == False
    assert cache.get(0) == None
    assert (0 in cache) == False
    assert cache.__delitem__(0) == False

    shutil.rmtree('tmp')


@nt.raises(KeyError)
@setup_cache
def test_getitem_keyerror(cache):
    cache[0]


@setup_cache
def test_expire(cache):
    cache.cull_limit = 0

    for value in range(100):
        cache.set(value, value, expire=0)

    assert len(cache) == 100

    cache.cull_limit = 10
    
    assert cache.expire() == 100


@setup_cache
def test_evict(cache):
    colors = ('red', 'blue', 'yellow')

    for value in range(90):
        assert cache.set(value, value, tag=colors[value % len(colors)])

    assert len(cache) == 90
    assert cache.evict('red') == 30
    assert len(cache) == 60
    assert len(cache.check()) == 0


@setup_cache
def test_clear(cache):
    for value in range(100):
        cache[value] = value
    assert len(cache) == 100
    assert cache.clear() == 100
    assert len(cache) == 0
    assert len(cache.check()) == 0


@setup_cache
def test_stats(cache):
    for value in range(100):
        cache[value] = value

    assert cache.stats(enable=True) == (0, 0)

    for value in range(100):
        cache[value]

    for value in range(100, 110):
        cache.get(value)

    assert cache.stats(reset=True) == (100, 10)
    assert cache.stats(enable=False) == (0, 0)

    for value in range(100):
        cache[value]

    for value in range(100, 110):
        cache.get(value)

    assert cache.stats() == (0, 0)
    assert len(cache.check()) == 0


@setup_cache
def test_volume(cache):
    volume = sum(shard.volume() for shard in cache._shards)
    assert volume == cache.volume()


if __name__ == '__main__':
    import nose
    nose.runmodule()
