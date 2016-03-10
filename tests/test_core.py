"Test diskcache.core.Cache."

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
        with dc.Cache('tmp') as cache:
            func(cache)
        shutil.rmtree('tmp', ignore_errors=True)
    return wrapper


@setup_cache
def test_init(cache):
    for key, value in dc.DEFAULT_SETTINGS.items():
        assert getattr(cache, key) == value
    cache.check()
    cache.close()
    cache.close()


@nt.raises(EnvironmentError)
def test_init_makedirs():
    shutil.rmtree('tmp', ignore_errors=True)
    makedirs = mock.Mock(side_effect=OSError(errno.EACCES))

    try:
        with mock.patch('os.makedirs', makedirs):
            cache = dc.Cache('tmp')
    except EnvironmentError:
        shutil.rmtree('tmp')
        raise


@setup_cache
def test_pragma(cache):
    local = mock.Mock()
    con = mock.Mock()
    execute = mock.Mock()
    cursor = mock.Mock()
    fetchall = mock.Mock()

    local.con = con
    con.execute = execute
    execute.return_value = cursor
    cursor.fetchall = fetchall
    fetchall.side_effect = [sqlite3.OperationalError, None]

    with mock.patch.object(cache, '_local', local):
        cache.sqlite_mmap_size = 2 ** 28


@setup_cache
@nt.raises(sqlite3.OperationalError)
def test_pragma_error(cache):
    local = mock.Mock()
    con = mock.Mock()
    execute = mock.Mock()
    cursor = mock.Mock()
    fetchall = mock.Mock()

    local.con = con
    con.execute = execute
    execute.return_value = cursor
    cursor.fetchall = fetchall
    fetchall.side_effect = sqlite3.OperationalError

    prev = dc.LIMITS[u'pragma_timeout']
    dc.LIMITS[u'pragma_timeout'] = 0.003

    try:
        with mock.patch.object(cache, '_local', local):
            cache.sqlite_mmap_size = 2 ** 28
    finally:
        dc.LIMITS[u'pragma_timeout'] = prev


@setup_cache
def test_close_error(cache):
    class LocalTest(object):
        def __init__(self):
            self._calls = 0
        def __getattr__(self, name):
            if self._calls:
                raise AttributeError
            else:
                self._calls += 1
                return mock.Mock()

    with mock.patch.object(cache, '_local', LocalTest()):
        cache.close()


@setup_cache
def test_getsetdel(cache):
    values = [
        (None, False),
        ((None,) * 2 ** 12, False),
        (1234, False),
        (2 ** 512, False),
        (56.78, False),
        (u'hello', False),
        (u'hello' * 2 ** 12, False),
        (b'world', False),
        (b'world' * 2 ** 12, False),
        (io.BytesIO(b'world' * 2 ** 12), True),
    ]

    for key, (value, file_like) in enumerate(values):
        assert cache.set(key, value, read=file_like)

    assert len(cache) == len(values)

    for key, (value, file_like) in enumerate(values):
        if file_like:
            assert cache[key] == value.getvalue()
        else:
            assert cache[key] == value

    for key, _ in enumerate(values):
        del cache[key]

    assert len(cache) == 0

    for value, (key, _) in enumerate(values):
        cache[key] = value

    assert len(cache) == len(values)

    for value, (key, _) in enumerate(values):
        assert cache[key] == value

    for _, (key, _) in enumerate(values):
        del cache[key]

    assert len(cache) == 0

    cache.check()


@nt.raises(KeyError)
@setup_cache
def test_get_keyerror1(cache):
    cache[0]


@nt.raises(KeyError)
@setup_cache
def test_get_keyerror2(cache):
    "Test cache miss when store_time is None."
    local = mock.Mock()
    con = mock.Mock()
    execute = mock.Mock()
    cursor = mock.Mock()
    fetchall = mock.Mock()

    local.con = con
    con.execute = execute
    execute.return_value = cursor
    cursor.fetchall = fetchall
    fetchall.return_value = [(0, None, None, None, 0, None, 0)]

    cache.statistics = True

    with mock.patch.object(cache, '_local', local):
        cache[0]


@nt.raises(KeyError)
@setup_cache
def test_get_keyerror3(cache):
    "Test cache miss when expire_time is less than now."
    local = mock.Mock()
    con = mock.Mock()
    execute = mock.Mock()
    cursor = mock.Mock()
    fetchall = mock.Mock()

    local.con = con
    con.execute = execute
    execute.return_value = cursor
    cursor.fetchall = fetchall
    fetchall.return_value = [(0, 0, 0, None, 0, None, 0)]

    cache.statistics = True

    with mock.patch.object(cache, '_local', local):
        cache[0]


@nt.raises(IOError, KeyError)
@setup_cache
def test_get_keyerror4(cache):
    func = mock.Mock(side_effect=IOError(errno.ENOENT, ''))

    cache.statistics = True
    cache[0] = b'abcd' * 2 ** 12

    with mock.patch('io.open', func):
        cache[0]


@nt.raises(IOError)
@setup_cache
def test_get_keyerror5(cache):
    func = mock.Mock(side_effect=IOError(errno.EACCES, ''))

    cache[0] = b'abcd' * 2 ** 12

    with mock.patch('io.open', func):
        cache[0]


@setup_cache
def test_set_twice(cache):
    large_value = b'abcd' * 2 ** 12

    cache[0] = 0
    cache[0] = 1

    assert cache[0] == 1

    cache[0] = large_value

    assert cache[0] == large_value
    with cache.get(0, read=True) as reader:
        assert reader.name is not None

    cache[0] = 2

    assert cache[0] == 2
    assert cache.get(0, read=True) == 2

    cache.check()


@setup_cache
def test_set_noupdate(cache):
    local = mock.Mock()
    con = mock.Mock()
    execute = mock.Mock()
    cursor = mock.Mock()
    fetchall = mock.Mock()

    local.con = con
    con.execute = execute
    execute.return_value = cursor
    cursor.rowcount = 0
    cursor.fetchall = fetchall
    fetchall.return_value = None

    del cache.large_value_threshold

    with mock.patch.object(cache, '_local', local):
        assert not cache.set(0, b'abcd' * 2 ** 12)

    cache.check()


@setup_cache
def test_raw(cache):
    assert cache.set(0, io.BytesIO(b'abcd'), read=True)
    assert cache[0] == b'abcd'


@setup_cache
def test_get(cache):
    assert cache.get(0) is None
    assert cache.get(1, 'dne') == 'dne'
    assert cache.get(2, {}) == {}
    assert cache.get(0, expire_time=True, tag=True) == (None, None, None)

    assert cache.set(0, 0, expire=None, tag=u'number')

    assert cache.get(0, expire_time=True) == (0, None)
    assert cache.get(0, tag=True) == (0, u'number')
    assert cache.get(0, expire_time=True, tag=True) == (0, None, u'number')


@setup_cache
def test_delete(cache):
    cache[0] = 0
    assert cache.delete(0)
    assert len(cache) == 0
    assert not cache.delete(0)
    assert len(cache.check()) == 0


@nt.raises(KeyError)
@setup_cache
def test_del(cache):
    del cache[0]


@setup_cache
def test_stats(cache):
    cache[0] = 0

    assert cache.stats(enable=True) == (0, 0)

    for _ in range(100):
        cache[0]

    for _ in range(10):
        cache.get(1)

    assert cache.stats(reset=True) == (100, 10)
    assert cache.stats(enable=False) == (0, 0)

    for _ in range(100):
        cache[0]

    for _ in range(10):
        cache.get(1)

    assert cache.stats() == (0, 0)
    assert len(cache.check()) == 0


@setup_cache
def test_path(cache):
    cache[0] = u'abc'
    large_value = b'abc' * 2 ** 12
    cache[1] = large_value

    assert cache.get(0, read=True) == u'abc'

    with cache.get(1, read=True) as reader:
        assert reader.name is not None
        path = reader.name

    with open(path, 'rb') as reader:
        value = reader.read()

    assert value == large_value

    assert len(cache.check()) == 0


@setup_cache
def test_expire_rows(cache):
    cache.cull_limit = 0

    for value in range(10):
        assert cache.set(value, value, expire=0)

    for value in range(10, 15):
        assert cache.set(value, value)

    assert len(cache) == 15

    cache.cull_limit = 10

    assert cache.set(15, 15)

    assert len(cache) == 6
    assert len(cache.check()) == 0


@setup_cache
def test_least_recently_stored(cache):
    cache.eviction_policy = u'least-recently-stored'
    cache.size_limit = int(10.1e6)
    cache.cull_limit = 2

    million = b'x' * int(1e6)

    for value in range(10):
        cache[value] = million

    assert len(cache) == 10

    for value in range(10):
        assert cache[value] == million

    for value in range(10, 20):
        cache[value] = million

    assert len(cache) == 10

    for value in range(10):
        cache[value] = million

    count = len(cache)

    for index, length in enumerate([1, 2, 3, 4]):
        cache[10 + index] = million * length
        assert len(cache) == count - length

    assert cache[12] == million * 3
    assert cache[13] == million * 4

    assert len(cache.check()) == 0


@setup_cache
def test_least_recently_used(cache):
    cache.eviction_policy = u'least-recently-used'
    cache.size_limit = int(10.1e6)
    cache.cull_limit = 5

    million = b'x' * int(1e6)

    for value in range(10):
        cache[value] = million

    assert len(cache) == 10

    cache[0]
    cache[1]
    cache[7]
    cache[8]
    cache[9]

    cache[10] = million

    assert len(cache) == 6

    for value in [0, 1, 7, 8, 9, 10]:
        assert cache[value] == million

    assert len(cache.check()) == 0


@setup_cache
def test_least_frequently_used(cache):
    cache.eviction_policy = u'least-frequently-used'
    cache.size_limit = int(10.1e6)
    cache.cull_limit = 5

    million = b'x' * int(1e6)

    for value in range(10):
        cache[value] = million

    assert len(cache) == 10

    cache[0], cache[0], cache[0], cache[0], cache[0]
    cache[1], cache[1], cache[1], cache[1]
    cache[7], cache[7], cache[7]
    cache[8], cache[8]
    cache[9]

    cache[10] = million

    assert len(cache) == 6

    for value in [0, 1, 7, 8, 9, 10]:
        assert cache[value] == million

    assert len(cache.check()) == 0


@nt.raises(OSError)
@setup_cache
def test_filename_error(cache):
    func = mock.Mock(side_effect=OSError(errno.EACCES))

    with mock.patch('os.makedirs', func):
        cache._prep_file()


# TODO: Add test for Windows. Attempting to remove a file that is in use
# (i.e. open for reading) causes an exception.

@nt.raises(OSError)
@setup_cache
def test_remove_error(cache):
    func = mock.Mock(side_effect=OSError(errno.EACCES))

    with mock.patch('os.remove', func):
        cache._remove('ab/cd/efg.val')


@setup_cache
def test_check(cache):
    blob = b'a' * 2 ** 14
    keys = (0, 1, 1234, 56.78, u'hello', b'world', None)

    for key in keys:
        cache[key] = blob

    # Cause mayhem.

    with cache.get(0, read=True) as reader:
        full_path = reader.name
    os.rename(full_path, full_path + '_moved')

    with cache.get(1, read=True) as reader:
        full_path = reader.name
    os.remove(full_path)

    cache._sql('UPDATE Cache SET store_time = NULL WHERE rowid > 2')
    cache.count = 0
    cache.size = 0

    with warnings.catch_warnings():
        warnings.filterwarnings('ignore')
        cache.check()
        cache.check(fix=True)

    assert len(cache.check()) == 0 # Should display no warnings.


@setup_cache
def test_integrity_check(cache):
    for value in range(1000):
        cache[value] = value

    cache.close()

    with io.open('tmp/cache.db', 'r+b') as writer:
        writer.seek(52)
        writer.write(b'\x00\x01') # Should be 0, change it.

    cache = dc.Cache('tmp')

    with warnings.catch_warnings():
        warnings.filterwarnings('ignore')
        cache.check()
        cache.check(fix=True)

    assert len(cache.check()) == 0


@setup_cache
def test_expire(cache):
    cache.cull_limit = 0 # Disable expiring keys on `set`.
    now = time.time()
    time_time = mock.Mock(return_value=now)

    with mock.patch('time.time', time_time):
        for value in range(100):
            assert cache.set(value, value, expire=value)

    assert len(cache) == 100

    time_time = mock.Mock(return_value=now + 10)
    cache.cull_limit = 10
    with mock.patch('time.time', time_time):
        assert cache.expire() == 10

    assert len(cache) == 90
    assert len(cache.check()) == 0


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
def test_tag(cache):
    assert cache.set(0, None, tag=u'zero')
    assert cache.set(1, None, tag=1234)
    assert cache.set(2, None, tag=5.67)
    assert cache.set(3, None, tag=b'three')

    assert cache.get(0, tag=True) == (None, u'zero')
    assert cache.get(1, tag=True) == (None, 1234)
    assert cache.get(2, tag=True) == (None, 5.67)
    assert cache.get(3, tag=True) == (None, b'three')


@setup_cache
def test_multiple_threads(cache):
    values = list(range(100))

    cache[0] = 0
    cache[1] = 1
    cache[2] = 2

    cache = dc.Cache('tmp')

    def worker():
        sets = list(values)
        random.shuffle(sets)

        with dc.Cache('tmp') as thread_cache:
            for value in sets:
                thread_cache[value] = value

    threads = [threading.Thread(target=worker) for _ in range(10)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    for value in values:
        assert cache[value] == value

    assert len(cache.check()) == 0


@setup_cache
def test_thread_safe(cache):
    values = list(range(100))

    def worker():
        with cache:
            sets = list(values)
            random.shuffle(sets)
            for value in sets:
                cache[value] = value

    threads = [threading.Thread(target=worker) for _ in range(10)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    for value in values:
        assert cache[value] == value

    assert len(cache.check()) == 0


@setup_cache
def test_with(cache):
    with dc.Cache('tmp') as tmp:
        tmp[u'a'] = 0
        tmp[u'b'] = 1

    assert cache[u'a'] == 0
    assert cache[u'b'] == 1


@setup_cache
def test_contains(cache):
    assert 0 not in cache
    cache[0] = 0
    assert 0 in cache
    cache._sql('UPDATE Cache SET store_time = NULL')
    assert 0 not in cache


if __name__ == '__main__':
    import nose
    nose.runmodule()
