"""Test diskcache.core.Cache.

TODO
0. Setup git and commit.
1. Test eviction policies.
2. Test Python 3 (setup Tox)
3. Test under stress.

"""

import errno
import functools as ft
import mock
import nose.tools as nt
import os
import shutil
import sys
import time

try:
    import cPickle as pickle
except:
    import pickle

from .context import diskcache
from diskcache import Cache, DEFAULT_SETTINGS, DEFAULT_METADATA

if sys.hexversion < 0x03000000:
    range = xrange
    try:
        from cStringIO import StringIO as BytesIO
    except ImportError:
        from StringIO import StringIO as BytesIO
    
else:
    import io
    BytesIO = io.BytesIO

def rmdir(func):
    @ft.wraps(func)
    def wrapper(*args, **kwargs):
        shutil.rmtree('temp', ignore_errors=True)
        try:
            func(*args, **kwargs)
        finally:
            shutil.rmtree('temp', ignore_errors=True)
    return wrapper


@rmdir
def test_init():
    cache = Cache('temp')

    for key, value in DEFAULT_SETTINGS.items():
        assert getattr(cache, key) == value

    for key, value in DEFAULT_METADATA.items():
        assert getattr(cache, key) == value

    cache.close()


@nt.raises(EnvironmentError)
@rmdir
def test_init_makedirs():
    func = mock.Mock(side_effect=OSError(errno.EACCES))

    with mock.patch('os.makedirs', func):
        cache = Cache('temp')


@rmdir
def test_getsetdel():
    cache = Cache('temp')

    values = [
        None,
        0,
        2 ** 256,
        1.2345,
        u'hello world',
        u'abcd' * 2 ** 12,
        b'abcdef',
    ]

    for key, value in enumerate(values):
        cache[key] = value

    assert len(cache) == len(values)

    for key, value in enumerate(values):
        assert cache[key] == value

    for key, _ in enumerate(values):
        del cache[key]

    assert len(cache) == 0

    for value, key in enumerate(values):
        cache[key] = value

    assert len(cache) == len(values)

    for value, key in enumerate(values):
        assert cache[key] == value

    for _, key in enumerate(values):
        del cache[key]

    assert len(cache) == 0


@nt.raises(KeyError)
@rmdir
def test_get_keyerror1():
    cache = Cache('temp')
    cache[0]


@nt.raises(KeyError)
@rmdir
def test_get_keyerror2():
    row = (0, 0, None, None, 0, None, 0)
    cursor = mock.Mock()
    cursor.fetchone = mock.Mock(return_value=row)
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func

    cache = Cache('temp')
    cache.statistics = True

    with mock.patch.object(cache, '_sql', con):
        cache[0]


@nt.raises(KeyError)
@rmdir
def test_get_keyerror3():
    row = (0, 0, 0, 0, 0, None, 0)
    cursor = mock.MagicMock()
    cursor.fetchone = mock.Mock(return_value=row)
    cursor.__iter__.return_value = [(0,)]
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func

    cache = Cache('temp')
    cache.statistics = True

    with mock.patch.object(cache, '_sql', con):
        cache[0]


@nt.raises(IOError, KeyError)
@rmdir
def test_get_keyerror4():
    func = mock.Mock(side_effect=IOError(errno.ENOENT, ''))

    cache = Cache('temp')
    cache.statistics = True
    cache[0] = b'abcd' * 2 ** 12

    with mock.patch('io.open', func):
        cache[0]


@nt.raises(IOError)
@rmdir
def test_get_keyerror5():
    func = mock.Mock(side_effect=IOError(errno.EACCES, ''))

    cache = Cache('temp')
    cache[0] = b'abcd' * 2 ** 12

    with mock.patch('io.open', func):
        cache[0]


@rmdir
def test_set_twice():
    large_value = b'abcd' * 2 ** 12

    cache = Cache('temp')
    cache[0] = 0
    cache[0] = 1

    assert cache[0] == 1

    cache[0] = large_value

    assert cache[0] == large_value
    assert cache.path(0) is not None
    
    cache[0] = 2

    assert cache[0] == 2
    assert cache.path(0) is None


@rmdir
def test_set_noupdate():
    cursor = mock.Mock()
    cursor.fetchone = mock.Mock(return_value=None)
    cursor.rowcount = 0
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func
    
    cache = Cache('temp')
    del cache.large_value_threshold

    with mock.patch.object(cache, '_sql', con):
        cache[0] = b'abcd' * 2 ** 12


@rmdir
def test_raw():
    cache = Cache('temp')

    cache.set(0, BytesIO('abcd'), raw=True)
    assert cache[0] == 'abcd'


@rmdir
def test_get():
    cache = Cache('temp')

    assert cache.get(0) is None
    assert cache.get(1, 'dne') == 'dne'
    assert cache.get(2, {}) == {}


@rmdir
def test_delete():
    cache = Cache('temp')
    cache[0] = 0
    cache.delete(0)
    assert len(cache) == 0
    cache.delete(0)


@nt.raises(KeyError)
@rmdir
def test_del():
    cache = Cache('temp')
    del cache[0]


@rmdir
def test_stats():
    cache = Cache('temp')

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


@rmdir
def test_path():
    cache = Cache('temp')

    cache[0] = 'abc'
    cache[1] = b'abc' * 2 ** 12

    assert cache.path(0) == None
    assert cache.path(1) != None

    path = cache.path(1)

    with open(path, 'rb') as reader:
        data = reader.read()

    value = pickle.loads(data)

    assert value == b'abc' * 2 ** 12


@rmdir
def test_expire_rows():
    cache = Cache('temp')

    for value in range(10):
        cache.set(value, value, expire=0.1)

    for value in range(10, 15):
        cache.set(value, value)

    assert len(cache) == 15

    time.sleep(0.1)

    cache.set(15, 15)

    assert len(cache) == 6


@rmdir
def test_least_recently_stored():
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


@rmdir
def test_least_recently_used():
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


@rmdir
def test_least_frequently_used():
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


@nt.raises(OSError)
@rmdir
def test_filename_error():
    cache = Cache('temp')

    func = mock.Mock(side_effect=OSError(errno.EACCES))

    with mock.patch('os.makedirs', func):
        cache._filename()


@nt.raises(OSError)
@rmdir
def test_remove_error():
    cache = Cache('temp')

    func = mock.Mock(side_effect=OSError(errno.EACCES))

    with mock.patch('os.remove', func):
        cache._remove('ab/cd/efg.val')


@rmdir
def test_check():
    # TODO: Improve test.
    cache = Cache('temp')
    cache.check()


@rmdir
def test_evict():
    # TODO: Improve test.
    cache = Cache('temp')
    cache.evict('red')


@rmdir
def test_clear():
    # TODO: Improve test.
    cache = Cache('temp')
    cache.clear()


@nt.raises(KeyError)
@rmdir
def test_path_keyerror1():
    row = None
    cursor = mock.Mock()
    cursor.fetchone = mock.Mock(return_value=row)
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func

    cache = Cache('temp')

    with mock.patch.object(cache, '_sql', con):
        cache.path(0)


@nt.raises(KeyError)
@rmdir
def test_path_keyerror2():
    row = (None, None)
    cursor = mock.Mock()
    cursor.fetchone = mock.Mock(return_value=row)
    func = mock.Mock(return_value=cursor)
    con = mock.Mock()
    con.execute = func

    cache = Cache('temp')

    with mock.patch.object(cache, '_sql', con):
        cache.path(0)


