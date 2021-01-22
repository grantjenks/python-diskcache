"Test diskcache.fanout.FanoutCache."

import collections as co
import hashlib
import io
import os
import os.path as op
import pickle
import shutil
import subprocess as sp
import tempfile
import threading
import time
import warnings
from unittest import mock

import pytest

import diskcache as dc

warnings.simplefilter('error')
warnings.simplefilter('ignore', category=dc.EmptyDirWarning)


@pytest.fixture
def cache():
    with dc.FanoutCache() as cache:
        yield cache
    shutil.rmtree(cache.directory, ignore_errors=True)


def test_init(cache):
    default_settings = dc.DEFAULT_SETTINGS.copy()
    del default_settings['size_limit']
    for key, value in default_settings.items():
        assert getattr(cache, key) == value
    assert cache.size_limit == 2 ** 27

    cache.check()

    for key, value in dc.DEFAULT_SETTINGS.items():
        setattr(cache, key, value)

    cache.check()


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
    assert cache.delete(100) is False

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


def test_set_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    set_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.set = set_func
    set_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert not cache.set(0, 0)


def test_touch(cache):
    assert cache.set(0, None, expire=60)
    assert cache.touch(0, expire=None)
    assert cache.touch(0, expire=0)
    assert not cache.touch(0)


def test_touch_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    touch_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.touch = touch_func
    touch_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert not cache.touch(0)


def test_add(cache):
    assert cache.add(0, 0)
    assert not cache.add(0, 1)
    assert cache.get(0) == 0


def test_add_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    add_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.add = add_func
    add_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert not cache.add(0, 0)


def stress_add(cache, limit, results):
    total = 0
    for num in range(limit):
        if cache.add(num, num, retry=True):
            total += 1
            # Stop one thread from running ahead of others.
            time.sleep(0.001)
    results.append(total)


def test_add_concurrent():
    with dc.FanoutCache(shards=1) as cache:
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
    shutil.rmtree(cache.directory, ignore_errors=True)


def test_incr(cache):
    cache.incr('key', delta=3) == 3


def test_incr_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    incr_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.incr = incr_func
    incr_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert cache.incr('key', 1) is None


def test_decr(cache):
    cache.decr('key', delta=2) == -2


def test_decr_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    decr_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.decr = decr_func
    decr_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert cache.decr('key', 1) is None


def stress_incr(cache, limit):
    for _ in range(limit):
        cache.incr(b'key', retry=True)
        time.sleep(0.001)


def test_incr_concurrent():
    with dc.FanoutCache(shards=1, timeout=0.001) as cache:
        count = 16
        limit = 50

        threads = [
            threading.Thread(target=stress_incr, args=(cache, limit))
            for _ in range(count)
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        assert cache.get(b'key') == count * limit
        cache.check()
    shutil.rmtree(cache.directory, ignore_errors=True)


def test_getsetdel(cache):
    values = [
        (None, False),
        ((None,) * 2 ** 10, False),
        (1234, False),
        (2 ** 512, False),
        (56.78, False),
        (u'hello', False),
        (u'hello' * 2 ** 10, False),
        (b'world', False),
        (b'world' * 2 ** 10, False),
        (io.BytesIO(b'world' * 2 ** 10), True),
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


def test_pop(cache):
    for num in range(100):
        cache[num] = num

    for num in range(100):
        assert cache.pop(num) == num


def test_pop_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    pop_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.pop = pop_func
    pop_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert cache.pop(0) is None


def test_delete_timeout(cache):
    shards = mock.Mock()
    shard = mock.Mock()
    delete_func = mock.Mock()

    shards.__getitem__ = mock.Mock(side_effect=lambda key: shard)
    shard.delete = delete_func
    delete_func.side_effect = dc.Timeout

    with mock.patch.object(cache, '_shards', shards):
        assert not cache.delete(0)


def test_delitem(cache):
    cache[0] = 0
    assert cache[0] == 0
    del cache[0]


def test_delitem_keyerror(cache):
    with pytest.raises(KeyError):
        del cache[0]


def test_tag_index(cache):
    assert cache.tag_index == 0
    cache.create_tag_index()
    assert cache.tag_index == 1
    cache.drop_tag_index()
    assert cache.tag_index == 0


def test_read(cache):
    cache.set(0, b'abcd' * 2 ** 20)
    with cache.read(0) as reader:
        assert reader is not None


def test_read_keyerror(cache):
    with pytest.raises(KeyError):
        with cache.read(0):
            pass


def test_getitem_keyerror(cache):
    with pytest.raises(KeyError):
        cache[0]


def test_expire(cache):
    cache.reset('cull_limit', 0)

    for value in range(100):
        cache.set(value, value, expire=1e-9)

    assert len(cache) == 100

    time.sleep(0.01)
    cache.reset('cull_limit', 10)

    assert cache.expire() == 100


def test_evict(cache):
    colors = ('red', 'blue', 'yellow')

    for value in range(90):
        assert cache.set(value, value, tag=colors[value % len(colors)])

    assert len(cache) == 90
    assert cache.evict('red') == 30
    assert len(cache) == 60
    assert len(cache.check()) == 0


def test_size_limit_with_files(cache):
    shards = 8
    cache.reset('cull_limit', 0)
    size_limit = 30 * cache.disk_min_file_size
    cache.reset('size_limit', size_limit)
    value = b'foo' * cache.disk_min_file_size

    for key in range(40 * shards):
        cache.set(key, value)

    assert (cache.volume() // shards) > size_limit
    cache.cull()
    assert (cache.volume() // shards) <= size_limit


def test_size_limit_with_database(cache):
    shards = 8
    cache.reset('cull_limit', 0)
    size_limit = 2 * cache.disk_min_file_size
    cache.reset('size_limit', size_limit)
    value = b'0123456789' * 10
    count = size_limit // (8 + len(value)) * shards

    for key in range(count):
        cache.set(key, value)

    assert (cache.volume() // shards) > size_limit
    cache.cull()
    assert (cache.volume() // shards) <= size_limit


def test_clear(cache):
    for value in range(100):
        cache[value] = value
    assert len(cache) == 100
    assert cache.clear() == 100
    assert len(cache) == 0
    assert len(cache.check()) == 0


def test_remove_timeout(cache):
    shard = mock.Mock()
    clear = mock.Mock()

    shard.clear = clear
    clear.side_effect = [dc.Timeout(2), 3]

    with mock.patch.object(cache, '_shards', [shard]):
        assert cache.clear() == 5


def test_reset_timeout(cache):
    shard = mock.Mock()
    reset = mock.Mock()

    shard.reset = reset
    reset.side_effect = [dc.Timeout, 0]

    with mock.patch.object(cache, '_shards', [shard]):
        assert cache.reset('blah', 1) == 0


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


def test_volume(cache):
    volume = sum(shard.volume() for shard in cache._shards)
    assert volume == cache.volume()


def test_iter(cache):
    for num in range(100):
        cache[num] = num
    assert set(cache) == set(range(100))


def test_iter_expire(cache):
    """Test iteration with expiration.

    Iteration does not expire keys.

    """
    cache.reset('cull_limit', 0)
    for num in range(100):
        cache.set(num, num, expire=1e-9)
    time.sleep(0.1)
    assert set(cache) == set(range(100))
    cache.expire()
    assert set(cache) == set()


def test_reversed(cache):
    for num in range(100):
        cache[num] = num
    reverse = list(reversed(cache))
    assert list(cache) == list(reversed(reverse))


def test_pickle(cache):
    for num, val in enumerate('abcde'):
        cache[val] = num

    data = pickle.dumps(cache)
    other = pickle.loads(data)

    for key in other:
        assert other[key] == cache[key]


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


def test_copy():
    cache_dir1 = tempfile.mkdtemp()

    with dc.FanoutCache(cache_dir1) as cache1:
        for count in range(10):
            cache1[count] = str(count)

        for count in range(10, 20):
            cache1[count] = str(count) * int(1e5)

    cache_dir2 = tempfile.mkdtemp()
    shutil.rmtree(cache_dir2)
    shutil.copytree(cache_dir1, cache_dir2)

    with dc.FanoutCache(cache_dir2) as cache2:
        for count in range(10):
            assert cache2[count] == str(count)

        for count in range(10, 20):
            assert cache2[count] == str(count) * int(1e5)

    shutil.rmtree(cache_dir1, ignore_errors=True)
    shutil.rmtree(cache_dir2, ignore_errors=True)


def run(command):
    print('run$ %r' % command)
    try:
        result = sp.check_output(command, stderr=sp.STDOUT)
        print(result)
    except sp.CalledProcessError as exc:
        print(exc.output)
        raise


def test_rsync():
    try:
        run(['rsync', '--version'])
    except OSError:
        return  # No rsync installed. Skip test.

    rsync_args = ['rsync', '-a', '--checksum', '--delete', '--stats']
    cache_dir1 = tempfile.mkdtemp() + os.sep
    cache_dir2 = tempfile.mkdtemp() + os.sep

    # Store some items in cache_dir1.

    with dc.FanoutCache(cache_dir1) as cache1:
        for count in range(100):
            cache1[count] = str(count)

        for count in range(100, 200):
            cache1[count] = str(count) * int(1e5)

    # Rsync cache_dir1 to cache_dir2.

    run(rsync_args + [cache_dir1, cache_dir2])

    # Validate items in cache_dir2.

    with dc.FanoutCache(cache_dir2) as cache2:
        for count in range(100):
            assert cache2[count] == str(count)

        for count in range(100, 200):
            assert cache2[count] == str(count) * int(1e5)

    # Store more items in cache_dir2.

    with dc.FanoutCache(cache_dir2) as cache2:
        for count in range(200, 300):
            cache2[count] = str(count)

        for count in range(300, 400):
            cache2[count] = str(count) * int(1e5)

    # Rsync cache_dir2 to cache_dir1.

    run(rsync_args + [cache_dir2, cache_dir1])

    # Validate items in cache_dir1.

    with dc.FanoutCache(cache_dir1) as cache1:
        for count in range(100):
            assert cache1[count] == str(count)

        for count in range(100, 200):
            assert cache1[count] == str(count) * int(1e5)

        for count in range(200, 300):
            assert cache1[count] == str(count)

        for count in range(300, 400):
            assert cache1[count] == str(count) * int(1e5)

    shutil.rmtree(cache_dir1, ignore_errors=True)
    shutil.rmtree(cache_dir2, ignore_errors=True)


class SHA256FilenameDisk(dc.Disk):
    def filename(self, key=dc.UNKNOWN, value=dc.UNKNOWN):
        filename = hashlib.sha256(key).hexdigest()[:32]
        full_path = op.join(self._directory, filename)
        return filename, full_path


def test_custom_filename_disk():
    with dc.FanoutCache(disk=SHA256FilenameDisk) as cache:
        for count in range(100, 200):
            key = str(count).encode('ascii')
            cache[key] = str(count) * int(1e5)

    disk = SHA256FilenameDisk(cache.directory)

    for count in range(100, 200):
        key = str(count).encode('ascii')
        subdir = '%03d' % (disk.hash(key) % 8)
        filename = hashlib.sha256(key).hexdigest()[:32]
        full_path = op.join(cache.directory, subdir, filename)

        with open(full_path) as reader:
            content = reader.read()
            assert content == str(count) * int(1e5)

    shutil.rmtree(cache.directory, ignore_errors=True)
