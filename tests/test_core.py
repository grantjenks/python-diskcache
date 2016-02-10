"Test diskcache.core.Cache."

import errno
import functools as ft
import io
import mock
import nose.tools as nt
import os
import shutil
import sys
import time
import warnings

try:
    import cPickle as pickle
except:
    import pickle

from diskcache import Cache, DEFAULT_SETTINGS, EmptyDirWarning

warnings.filterwarnings('ignore', category=EmptyDirWarning)

if sys.hexversion < 0x03000000:
    range = xrange

def setup_cache(func):
    @ft.wraps(func)
    def wrapper():
        shutil.rmtree('temp', ignore_errors=True)
        cache = Cache('temp')
        func(cache)
        cache.close()
        shutil.rmtree('temp', ignore_errors=True)
    return wrapper


@setup_cache
def test_init(cache):
    for key, value in DEFAULT_SETTINGS.items():
        assert getattr(cache, key) == value
    cache.check()
    cache.close()


@nt.raises(EnvironmentError)
def test_init_makedirs():
    func = mock.Mock(side_effect=OSError(errno.EACCES))

    try:
        with mock.patch('os.makedirs', func):
            cache = Cache('temp')
    except EnvironmentError:
        shutil.rmtree('temp')
        raise

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
        cache.set(key, value, file_like=file_like)

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
    row = (0, None, None, 0, None, 0)
    cursor = mock.Mock()
    cursor.fetchone = mock.Mock(return_value=row)
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func

    cache.statistics = True

    with mock.patch.object(cache, '_sql', con):
        cache[0]


@nt.raises(KeyError)
@setup_cache
def test_get_keyerror3(cache):
    "Test cache miss when expire_time is less than now."
    row = (0, 0, 0, 0, None, 0)
    cursor = mock.MagicMock()
    cursor.fetchone = mock.Mock(return_value=row)
    cursor.__iter__.return_value = [(0,)]
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func

    cache.statistics = True

    with mock.patch.object(cache, '_sql', con):
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
    assert cache.path(0) is not None

    cache[0] = 2

    assert cache[0] == 2
    assert cache.path(0) is None

    cache.check()


@setup_cache
def test_set_noupdate(cache):
    cursor = mock.Mock()
    cursor.fetchone = mock.Mock(return_value=None)
    cursor.rowcount = 0
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func

    del cache.large_value_threshold

    with mock.patch.object(cache, '_sql', con):
        cache[0] = b'abcd' * 2 ** 12

    cache.check()


@setup_cache
def test_raw(cache):
    cache.set(0, io.BytesIO(b'abcd'), file_like=True)
    assert cache[0] == b'abcd'


@setup_cache
def test_get(cache):
    assert cache.get(0) is None
    assert cache.get(1, 'dne') == 'dne'
    assert cache.get(2, {}) == {}


@setup_cache
def test_delete(cache):
    cache[0] = 0
    cache.delete(0)
    assert len(cache) == 0
    cache.delete(0)
    cache.check()


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
    cache.check()


@setup_cache
def test_path(cache):
    cache[0] = u'abc'
    cache[1] = io.BytesIO(b'abc' * 2 ** 12)

    assert cache.path(0) == None
    assert cache.path(1) != None

    path = cache.path(1)

    with open(path, 'rb') as reader:
        data = reader.read()

    value = pickle.loads(data)

    assert value.getvalue() == b'abc' * 2 ** 12
    cache.check()


@setup_cache
def test_expire_rows(cache):
    for value in range(10):
        cache.set(value, value, expire=0.1)

    for value in range(10, 15):
        cache.set(value, value)

    assert len(cache) == 15

    time.sleep(0.1)

    cache.set(15, 15)

    assert len(cache) == 6
    cache.check()


@setup_cache
def test_least_recently_stored(cache):
    cache = Cache(
        'temp',
        eviction_policy='least-recently-stored',
        size_limit=int(10.1e6),
        cull_limit=2,
    )

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

    cache.check()


@setup_cache
def test_least_recently_used(cache):
    cache = Cache(
        'temp',
        eviction_policy='least-recently-used',
        size_limit=int(10.1e6),
        cull_limit=5,
    )

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

    cache.check()


@setup_cache
def test_least_frequently_used(cache):
    cache = Cache(
        'temp',
        eviction_policy='least-frequently-used',
        size_limit=int(10.1e6),
        cull_limit=5,
    )

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

    cache.check()


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

    full_path = cache.path(0)
    os.rename(full_path, full_path + '_moved')
    full_path = cache.path(1)
    os.remove(full_path)
    cache._sql.execute('UPDATE Cache SET store_time = NULL WHERE rowid > 2')
    cache.count = 0
    cache.size = 0

    with warnings.catch_warnings():
        warnings.filterwarnings('ignore')
        cache.check()
        cache.check(fix=True)

    cache.check() # Should display no warnings.


@setup_cache
def test_integrity_check(cache):
    for value in range(1000):
        cache[value] = value

    cache.close()

    with io.open('temp/cache.sqlite3', 'r+b') as writer:
        writer.seek(52)
        writer.write(b'\x00\x01') # Should be 0, change it.

    cache = Cache('temp')

    with warnings.catch_warnings():
        warnings.filterwarnings('ignore')
        cache.check()
        cache.check(fix=True)

    cache.check()


@setup_cache
def test_expire(cache):
    cache.cull_limit = 0 # Disable expiring keys on `set`.
    now = time.time()
    func = mock.Mock(return_value=now)
    
    with mock.patch('time.time', func):
        for value in range(100):
            cache.set(value, value, expire=value)

    assert len(cache) == 100

    func = mock.Mock(return_value=now + 10)
    cache.cull_limit = 10
    with mock.patch('time.time', func):
        cache.expire()

    assert len(cache) == 90
    cache.check()


@setup_cache
def test_evict(cache):
    colors = ('red', 'blue', 'yellow')

    for value in range(90):
        cache.set(value, value, tag=colors[value % len(colors)])

    assert len(cache) == 90
    cache.evict('red')
    assert len(cache) == 60
    cache.check()


@setup_cache
def test_clear(cache):
    for value in range(100):
        cache[value] = value
    assert len(cache) == 100
    cache.clear()
    assert len(cache) == 0
    cache.check()


@nt.raises(KeyError)
@setup_cache
def test_path_keyerror1(cache):
    row = None
    cursor = mock.Mock()
    cursor.fetchone = mock.Mock(return_value=row)
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func

    with mock.patch.object(cache, '_sql', con):
        cache.path(0)


@nt.raises(KeyError)
@setup_cache
def test_path_keyerror2(cache):
    row = (None, None)
    cursor = mock.Mock()
    cursor.fetchone = mock.Mock(return_value=row)
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func

    with mock.patch.object(cache, '_sql', con):
        cache.path(0)
