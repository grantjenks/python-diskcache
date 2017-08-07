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
    assert cache.directory == 'tmp'

    default_settings = dc.DEFAULT_SETTINGS.copy()
    del default_settings['size_limit']
    for key, value in default_settings.items():
        assert getattr(cache, key) == value
    assert cache.size_limit == 2 ** 27

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


@setup_cache
def test_set_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    set_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.set = set_func
    set_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert not cache.set(0, 0)


@setup_cache
def test_set_timeout_retry(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    set_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.set = set_func
    set_func.side_effect = [dc.Timeout, True, dc.Timeout, True]

    with mock.patch.object(cache, '_shards', shards):
        assert cache.set(0, 0, retry=True)
        cache[1] = 1


@setup_cache
def test_add(cache):
    assert cache.add(0, 0)
    assert not cache.add(0, 1)
    assert cache.get(0) == 0


@setup_cache
def test_add_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    add_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.add = add_func
    add_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert not cache.add(0, 0)


@setup_cache
def test_add_timeout_retry(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    add_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.add = add_func
    add_func.side_effect = [dc.Timeout, True]

    with mock.patch.object(cache, '_shards', shards):
        assert cache.add(0, 0, retry=True)


@setup_cache
def test_incr(cache):
    cache.incr('key', delta=3) == 3


@setup_cache
def test_incr_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    incr_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.incr = incr_func
    incr_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert cache.incr('key', 1) is None


@setup_cache
def test_incr_timeout_retry(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    incr_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.incr = incr_func
    incr_func.side_effect = [dc.Timeout, 1]

    with mock.patch.object(cache, '_shards', shards):
        assert cache.incr('key', retry=True) == 1


@setup_cache
def test_decr(cache):
    cache.decr('key', delta=2) == -2


def stress_incr(cache, limit):
    for _ in range(limit):
        cache.incr(b'key', retry=True)
        time.sleep(0.001)


def test_incr_concurrent():
    count = 16
    limit = 500

    with dc.FanoutCache('tmp', timeout=0.001) as cache:
        threads = [
            threading.Thread(target=stress_incr, args=(cache, limit))
            for _ in range(count)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

    with dc.FanoutCache('tmp') as cache:
        assert cache.get(b'key') == count * limit
        cache.check()

    shutil.rmtree('tmp', ignore_errors=True)


@setup_cache
def test_get_timeout(cache):
    cache.set(0, 0)

    shards = mock.Mock()
    shard = mock.Mock()
    get_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.get = get_func
    get_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert cache.get(0) is None


@setup_cache
def test_get_timeout_retry(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    get_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.get = get_func
    get_func.side_effect = [dc.Timeout, 0]

    with mock.patch.object(cache, '_shards', shards):
        assert cache.get(0, retry=True) == 0


@setup_cache
def test_pop(cache):
    for num in range(100):
        cache[num] = num

    for num in range(100):
        assert cache.pop(num) == num


@setup_cache
def test_pop_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    pop_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.pop = pop_func
    pop_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert cache.pop(0) is None


@setup_cache
def test_pop_timeout_retry(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    pop_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.pop = pop_func
    pop_func.side_effect = [dc.Timeout, 0]

    with mock.patch.object(cache, '_shards', shards):
        assert cache.pop(0, retry=True) == 0


@setup_cache
def test_delete_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    delete_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.__delitem__ = delete_func
    delete_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert not cache.delete(0)


@setup_cache
def test_delete_timeout_retry(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    delete_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.__delitem__ = delete_func
    delete_func.side_effect = [dc.Timeout, True]

    with mock.patch.object(cache, '_shards', shards):
        assert cache.delete(0, retry=True)


@setup_cache
def test_delitem(cache):
    cache[0] = 0
    assert cache[0] == 0
    del cache[0]


@setup_cache
@nt.raises(KeyError)
def test_delitem_keyerror(cache):
    del cache[0]


@setup_cache
def test_delitem_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    delete_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.__delitem__ = delete_func
    delete_func.side_effect = [dc.Timeout, True]

    with mock.patch.object(cache, '_shards', shards):
        del cache[0]


@setup_cache
def test_tag_index(cache):
    assert cache.tag_index == 0
    cache.create_tag_index()
    assert cache.tag_index == 1
    cache.drop_tag_index()
    assert cache.tag_index == 0


@setup_cache
def test_read(cache):
    cache.set(0, b'abcd' * 2 ** 20)
    with cache.read(0) as reader:
        assert reader is not None


@nt.raises(KeyError)
@setup_cache
def test_read_keyerror(cache):
    with cache.read(0) as reader:
        pass


@nt.raises(KeyError)
@setup_cache
def test_getitem_keyerror(cache):
    cache[0]


@setup_cache
def test_expire(cache):
    cache.reset('cull_limit', 0)

    for value in range(100):
        cache.set(value, value, expire=0)

    assert len(cache) == 100

    time.sleep(0.01)
    cache.reset('cull_limit', 10)

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
def test_remove_timeout(cache):
    shard = mock.Mock()
    clear = mock.Mock()

    shard.clear = clear
    clear.side_effect = [dc.Timeout(2), 3]

    with mock.patch.object(cache, '_shards', [shard]):
        assert cache.clear() == 5


@setup_cache
def test_reset_timeout(cache):
    shard = mock.Mock()
    reset = mock.Mock()

    shard.reset = reset
    reset.side_effect = [dc.Timeout, 0]

    with mock.patch.object(cache, '_shards', [shard]):
        assert cache.reset('blah', 1) == 0


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


@setup_cache
def test_iter(cache):
    for num in range(100):
        cache[num] = num
    assert set(cache) == set(range(100))


@setup_cache
def test_iter_expire(cache):
    """Test iteration with expiration.

    Iteration does not expire keys.

    """
    cache.reset('cull_limit', 0)
    for num in range(100):
        cache.set(num, num, expire=0)
    time.sleep(0.1)
    assert set(cache) == set(range(100))
    cache.expire()
    assert set(cache) == set()


@setup_cache
def test_reversed(cache):
    for num in range(100):
        cache[num] = num
    reverse = list(reversed(cache))
    assert list(cache) == list(reversed(reverse))


@setup_cache
def test_pickle(cache):
    for num, val in enumerate('abcde'):
        cache[val] = num

    data = pickle.dumps(cache)
    other = pickle.loads(data)

    for key in other:
        assert other[key] == cache[key]


@setup_cache
def test_memoize(cache):
    count = 1000

    def fibiter(num):
        alpha, beta = 0, 1

        for _ in range(num):
            alpha, beta = beta, alpha + beta

        return alpha

    @cache.memoize(name='fib')
    def fibrec(num):
        if num == 0:
            return 0
        elif num == 1:
            return 1
        else:
            return fibrec(num - 1) + fibrec(num - 2)

    cache.stats(enable=True)

    for value in range(count):
        assert fibrec(value) == fibiter(value)

    hits1, misses1 = cache.stats()

    for value in range(count):
        assert fibrec(value) == fibiter(value)

    hits2, misses2 = cache.stats()

    assert hits2 == hits1 + count
    assert misses2 == misses1


if __name__ == '__main__':
    import nose
    nose.runmodule()
