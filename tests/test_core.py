"Test diskcache.core.Cache."

import collections as co
import errno
import functools as ft
import io
import json
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
import zlib

try:
    import cPickle as pickle
except:
    import pickle

import diskcache
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


def test_init_disk():
    with dc.Cache('tmp', disk_pickle_protocol=1, disk_min_file_size=2 ** 20) as cache:
        key = (None, 0, 'abc')
        cache[key] = 0
        cache.check()
        assert cache.directory == 'tmp'
        assert cache.disk_min_file_size == 2 ** 20
        assert cache.disk_pickle_protocol == 1
    shutil.rmtree('tmp', ignore_errors=True)


def test_disk_reset():
    with dc.Cache('tmp', disk_min_file_size=0, disk_pickle_protocol=0) as cache:
        value = (None, 0, 'abc')

        cache[0] = value
        cache.check()

        assert cache.disk_min_file_size == 0
        assert cache.disk_pickle_protocol == 0
        assert cache._disk.min_file_size == 0
        assert cache._disk.pickle_protocol == 0

        cache.reset('disk_min_file_size', 2 ** 10)
        cache.reset('disk_pickle_protocol', 2)

        cache[1] = value
        cache.check()

        assert cache.disk_min_file_size == 2 ** 10
        assert cache.disk_pickle_protocol == 2
        assert cache._disk.min_file_size == 2 ** 10
        assert cache._disk.pickle_protocol == 2

    shutil.rmtree('tmp', ignore_errors=True)


@nt.raises(ValueError)
def test_disk_valueerror():
    with dc.Cache('tmp', disk=dc.Disk('tmp')) as cache:
        pass


class JSONDisk(diskcache.Disk):
    def __init__(self, directory, compress_level=1, **kwargs):
        self.compress_level = compress_level
        super(JSONDisk, self).__init__(directory, **kwargs)

    def put(self, key):
        json_bytes = json.dumps(key).encode('utf-8')
        data = zlib.compress(json_bytes, self.compress_level)
        return super(JSONDisk, self).put(data)

    def get(self, key, raw):
        data = super(JSONDisk, self).get(key, raw)
        return json.loads(zlib.decompress(data).decode('utf-8'))

    def store(self, value, read):
        if not read:
            json_bytes = json.dumps(value).encode('utf-8')
            value = zlib.compress(json_bytes, self.compress_level)
        return super(JSONDisk, self).store(value, read)

    def fetch(self, mode, filename, value, read):
        data = super(JSONDisk, self).fetch(mode, filename, value, read)
        if not read:
            data = json.loads(zlib.decompress(data).decode('utf-8'))
        return data


def test_custom_disk():
    with dc.Cache('tmp', disk=JSONDisk, disk_compress_level=6) as cache:
        values = [None, True, 0, 1.23, {}, [None] * 10000]

        for value in values:
            cache[value] = value

        for value in values:
            assert cache[value] == value

    shutil.rmtree('tmp', ignore_errors=True)


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

    size = 2 ** 28

    with mock.patch.object(cache, '_local', local):
        assert cache.reset('sqlite_mmap_size', size) == size

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
    fetchall.side_effect = [sqlite3.OperationalError] * 60000

    size = 2 ** 28

    with mock.patch('time.sleep', lambda num: 0):
        with mock.patch.object(cache, '_local', local):
            cache.reset('sqlite_mmap_size', size)


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
        ((None,) * 2 ** 20, False),
        (1234, False),
        (2 ** 512, False),
        (56.78, False),
        (u'hello', False),
        (u'hello' * 2 ** 20, False),
        (b'world', False),
        (b'world' * 2 ** 20, False),
        (io.BytesIO(b'world' * 2 ** 20), True),
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


@nt.raises(IOError, KeyError)
@setup_cache
def test_get_keyerror4(cache):
    func = mock.Mock(side_effect=IOError(errno.ENOENT, ''))

    cache.reset('statistics', True)
    cache[0] = b'abcd' * 2 ** 20

    with mock.patch('diskcache.core.open', func):
        cache[0]


@nt.raises(IOError)
@setup_cache
def test_get_keyerror5(cache):
    func = mock.Mock(side_effect=IOError(errno.EACCES, ''))

    cache[0] = b'abcd' * 2 ** 20

    with mock.patch('diskcache.core.open', func):
        cache[0]


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


@setup_cache
def test_set_twice(cache):
    large_value = b'abcd' * 2 ** 20

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
@nt.raises(dc.Timeout)
def test_set_timeout(cache):
    local = mock.Mock()
    con = mock.Mock()
    execute = mock.Mock()

    local.con = con
    con.execute = execute
    execute.side_effect = sqlite3.OperationalError

    try:
        with mock.patch.object(cache, '_local', local):
            cache.set('a', 'b' * 2 ** 20)
    finally:
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
def test_get_expired_fast_path(cache):
    assert cache.set(0, 0, expire=0.001)
    time.sleep(0.01)
    assert cache.get(0) is None


@setup_cache
def test_get_ioerror_fast_path(cache):
    assert cache.set(0, 0)

    disk = mock.Mock()
    put = mock.Mock()
    fetch = mock.Mock()

    disk.put = put
    put.side_effect = [(0, True)]
    disk.fetch = fetch
    io_error = IOError()
    io_error.errno = errno.ENOENT
    fetch.side_effect = io_error

    with mock.patch.object(cache, '_disk', disk):
        assert cache.get(0) is None


@setup_cache
def test_get_expired_slow_path(cache):
    cache.stats(enable=True)
    cache.reset('eviction_policy', 'least-recently-used')
    assert cache.set(0, 0, expire=0.001)
    time.sleep(0.01)
    assert cache.get(0) is None


@setup_cache
@nt.raises(IOError)
def test_get_ioerror_slow_path(cache):
    cache.reset('eviction_policy', 'least-recently-used')
    cache.set(0, 0)

    disk = mock.Mock()
    put = mock.Mock()
    fetch = mock.Mock()

    disk.put = put
    put.side_effect = [(0, True)]
    disk.fetch = fetch
    io_error = IOError()
    io_error.errno = errno.EACCES
    fetch.side_effect = io_error

    with mock.patch.object(cache, '_disk', disk):
        cache.get(0)


@setup_cache
def test_pop(cache):
    assert cache.incr('alpha') == 1
    assert cache.pop('alpha') == 1
    assert cache.get('alpha') is None
    assert cache.check() == []

    assert cache.set('alpha', 123, expire=1, tag='blue')
    assert cache.pop('alpha', tag=True) == (123, 'blue')

    assert cache.set('beta', 456, expire=0, tag='green')
    time.sleep(0.01)
    assert cache.pop('beta', 'dne') == 'dne'

    assert cache.set('gamma', 789, tag='red')
    assert cache.pop('gamma', expire_time=True, tag=True) == (789, None, 'red')

    assert cache.pop('dne') is None

    assert cache.set('delta', 210)
    assert cache.pop('delta', expire_time=True) == (210, None)

    assert cache.set('epsilon', '0' * 2 ** 20)
    assert cache.pop('epsilon') == '0' * 2 ** 20


@setup_cache
def test_pop_ioerror(cache):
    assert cache.set(0, 0)

    disk = mock.Mock()
    put = mock.Mock()
    fetch = mock.Mock()

    disk.put = put
    put.side_effect = [(0, True)]
    disk.fetch = fetch
    io_error = IOError()
    io_error.errno = errno.ENOENT
    fetch.side_effect = io_error

    with mock.patch.object(cache, '_disk', disk):
        assert cache.pop(0) is None


@setup_cache
@nt.raises(IOError)
def test_pop_ioerror_eacces(cache):
    assert cache.set(0, 0)

    disk = mock.Mock()
    put = mock.Mock()
    fetch = mock.Mock()

    disk.put = put
    put.side_effect = [(0, True)]
    disk.fetch = fetch
    io_error = IOError()
    io_error.errno = errno.EACCES
    fetch.side_effect = io_error

    with mock.patch.object(cache, '_disk', disk):
        cache.pop(0)


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


@nt.raises(KeyError)
@setup_cache
def test_del_expired(cache):
    cache.set(0, 0, expire=0.001)
    time.sleep(0.01)
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
    large_value = b'abc' * 2 ** 20
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
    cache.reset('cull_limit', 0)

    for value in range(10):
        assert cache.set(value, value, expire=0)

    for value in range(10, 15):
        assert cache.set(value, value)

    assert len(cache) == 15

    time.sleep(0.01)
    cache.reset('cull_limit', 10)

    assert cache.set(15, 15)

    assert len(cache) == 6
    assert len(cache.check()) == 0


@setup_cache
def test_least_recently_stored(cache):
    cache.reset('eviction_policy', u'least-recently-stored')
    cache.reset('size_limit', int(10.1e6))
    cache.reset('cull_limit', 2)

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
    cache.reset('eviction_policy', u'least-recently-used')
    cache.reset('size_limit', int(10.1e6))
    cache.reset('cull_limit', 5)

    million = b'x' * int(1e6)

    for value in range(10):
        cache[value] = million

    assert len(cache) == 10

    time.sleep(0.01)

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
    cache.reset('eviction_policy', u'least-frequently-used')
    cache.reset('size_limit', int(10.1e6))
    cache.reset('cull_limit', 5)

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
        cache._disk.filename()


@setup_cache
def test_remove_error(cache):
    func = mock.Mock(side_effect=OSError(errno.EACCES))

    try:
        with mock.patch('os.remove', func):
            cache._disk.remove('ab/cd/efg.val')
    except OSError:
        pass
    else:
        if os.name == 'nt':
            pass  # File delete errors ignored on Windows.
        else:
            raise Exception('test_remove_error failed')


@setup_cache
def test_check(cache):
    blob = b'a' * 2 ** 20
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

    cache._sql('UPDATE Cache SET size = 0 WHERE rowid > 1')
    cache.reset('count', 0)
    cache.reset('size', 0)

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
    cache.reset('cull_limit', 0)  # Disable expiring keys on `set`.
    now = time.time()
    time_time = mock.Mock(return_value=now)

    with mock.patch('time.time', time_time):
        for value in range(100):
            assert cache.set(value, value, expire=value)

    assert len(cache) == 100

    time_time = mock.Mock(return_value=now + 10)
    cache.reset('cull_limit', 10)
    with mock.patch('time.time', time_time):
        assert cache.expire() == 10

    assert len(cache) == 90
    assert len(cache.check()) == 0


def test_tag_index():
    with dc.Cache('tmp', tag_index=True) as cache:
        assert cache.tag_index == 1
    shutil.rmtree('tmp', ignore_errors=True)


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
@nt.raises(dc.Timeout)
def test_clear_timeout(cache):
    transact = mock.Mock()
    transact.side_effect = dc.Timeout
    with mock.patch.object(cache, '_transact', transact):
        cache.clear()


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


@setup_cache
def test_add(cache):
    assert cache.add(1, 1)
    assert cache.get(1) == 1
    assert not cache.add(1, 2)
    assert cache.get(1) == 1
    assert cache.delete(1)
    assert cache.add(1, 1, expire=0.001)
    time.sleep(0.01)
    assert cache.add(1, 1)
    cache.check()


@setup_cache
def test_add_large_value(cache):
    value = b'abcd' * 2 ** 20
    assert cache.add(b'test-key', value)
    assert cache.get(b'test-key') == value
    assert not cache.add(b'test-key', value * 2)
    assert cache.get(b'test-key') == value
    cache.check()


def stress_add(cache, limit, results):
    total = 0
    for num in range(limit):
        if cache.add(num, num):
            total += 1
            # Stop one thread from running ahead of others.
            time.sleep(0.001)
    results.append(total)


@setup_cache
def test_add_concurrent(cache):
    results = co.deque()
    limit = 1000

    threads = [
        threading.Thread(target=stress_add, args=(cache, limit, results))
        for _ in range(16)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert sum(results) == limit
    cache.check()


@setup_cache
@nt.raises(dc.Timeout)
def test_add_timeout(cache):
    local = mock.Mock()
    con = mock.Mock()
    execute = mock.Mock()

    local.con = con
    con.execute = execute
    execute.side_effect = sqlite3.OperationalError

    try:
        with mock.patch.object(cache, '_local', local):
            cache.add(0, 0)
    finally:
        cache.check()


@setup_cache
def test_incr(cache):
    assert cache.incr('key', default=5) == 6
    assert cache.incr('key', 2) == 8
    assert cache.get('key', expire_time=True, tag=True) == (8, None, None)
    assert cache.delete('key')
    assert cache.set('key', 100, expire=0.100)
    assert cache.get('key') == 100
    time.sleep(0.120)
    assert cache.incr('key') == 1


@setup_cache
@nt.raises(KeyError)
def test_incr_insert_keyerror(cache):
    cache.incr('key', default=None)


@setup_cache
@nt.raises(KeyError)
def test_incr_update_keyerror(cache):
    assert cache.set('key', 100, expire=0.100)
    assert cache.get('key') == 100
    time.sleep(0.120)
    cache.incr('key', default=None)


@setup_cache
def test_decr(cache):
    assert cache.decr('key', default=5) == 4
    assert cache.decr('key', 2) == 2
    assert cache.get('key', expire_time=True, tag=True) == (2, None, None)
    assert cache.delete('key')
    assert cache.set('key', 100, expire=0.100)
    assert cache.get('key') == 100
    time.sleep(0.120)
    assert cache.decr('key') == -1


@setup_cache
@nt.raises(StopIteration)
def test_iter(cache):
    sequence = list('abcdef') + [('g',)]

    for index, value in enumerate(sequence):
        cache[value] = index

    iterator = iter(cache)

    assert all(one == two for one, two in zip(sequence, iterator))

    cache['h'] = 7

    next(iterator)


@setup_cache
def test_iter_expire(cache):
    cache.reset('cull_limit', 0)
    for num in range(100):
        cache.set(num, num, expire=0)
    assert len(cache) == 100
    assert list(cache) == list(range(100))


@setup_cache
@nt.raises(StopIteration)
def test_iter_error(cache):
    next(iter(cache))


@setup_cache
def test_reversed(cache):
    sequence = 'abcdef'

    for index, value in enumerate(sequence):
        cache[value] = index

    iterator = reversed(cache)

    pairs = zip(reversed(sequence), iterator)
    assert all(one == two for one, two in pairs)

    try:
        next(iterator)
    except StopIteration:
        pass
    else:
        assert False, 'StopIteration expected'


@setup_cache
@nt.raises(StopIteration)
def test_reversed_error(cache):
    next(reversed(cache))


@setup_cache
def test_push_pull(cache):
    for value in range(10):
        cache.push(value)

    for value in range(10):
        _, pull_value = cache.pull()
        assert pull_value == value

    assert len(cache) == 0


@setup_cache
def test_push_pull_prefix(cache):
    for value in range(10):
        cache.push(value, prefix='key')

    for value in range(10):
        key, pull_value = cache.pull(prefix='key')
        assert key.startswith('key')
        assert pull_value == value

    assert len(cache) == 0
    assert len(cache.check()) == 0


@setup_cache
def test_push_pull_extras(cache):
    cache.push('test')
    assert cache.pull() == (500000000000000, 'test')
    assert len(cache) == 0

    cache.push('test', expire=10)
    (key, value), expire_time = cache.pull(expire_time=True)
    assert key == 500000000000000
    assert value == 'test'
    assert expire_time > time.time()
    assert len(cache) == 0

    cache.push('test', tag='foo')
    (key, value), tag = cache.pull(tag=True)
    assert key == 500000000000000
    assert value == 'test'
    assert tag == 'foo'
    assert len(cache) == 0

    cache.push('test')
    (key, value), expire_time, tag = cache.pull(expire_time=True, tag=True)
    assert key == 500000000000000
    assert value == 'test'
    assert expire_time is None
    assert tag is None
    assert len(cache) == 0

    assert cache.pull(default=(0, 1)) == (0, 1)

    assert len(cache.check()) == 0


@setup_cache
def test_push_pull_expire(cache):
    cache.push(0, expire=0.1)
    cache.push(0, expire=0.1)
    cache.push(0, expire=0.1)
    cache.push(1)
    time.sleep(0.2)
    assert cache.pull() == (500000000000003, 1)
    assert len(cache) == 0
    assert len(cache.check()) == 0


@setup_cache
def test_push_pull_large_value(cache):
    value = b'test' * (2 ** 20)
    cache.push(value)
    assert cache.pull() == (500000000000000, value)
    assert len(cache) == 0
    assert len(cache.check()) == 0


@setup_cache
def test_pull_ioerror(cache):
    assert cache.push(0) == 500000000000000

    disk = mock.Mock()
    put = mock.Mock()
    fetch = mock.Mock()

    disk.put = put
    put.side_effect = [(0, True)]
    disk.fetch = fetch
    io_error = IOError()
    io_error.errno = errno.ENOENT
    fetch.side_effect = io_error

    with mock.patch.object(cache, '_disk', disk):
        assert cache.pull() == (None, None)


@setup_cache
@nt.raises(IOError)
def test_pull_ioerror_eacces(cache):
    assert cache.push(0) == 500000000000000

    disk = mock.Mock()
    put = mock.Mock()
    fetch = mock.Mock()

    disk.put = put
    put.side_effect = [(0, True)]
    disk.fetch = fetch
    io_error = IOError()
    io_error.errno = errno.EACCES
    fetch.side_effect = io_error

    with mock.patch.object(cache, '_disk', disk):
        cache.pull()


@setup_cache
def test_iterkeys(cache):
    assert list(cache.iterkeys()) == []


@setup_cache
def test_pickle(cache):
    for num, val in enumerate('abcde'):
        cache[val] = num

    data = pickle.dumps(cache)
    other = pickle.loads(data)

    for key in other:
        assert other[key] == cache[key]


if __name__ == '__main__':
    import nose
    nose.runmodule()
