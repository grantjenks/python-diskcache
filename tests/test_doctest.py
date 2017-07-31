import doctest
import shutil

import diskcache.core
import diskcache.djangocache
import diskcache.fanout
import diskcache.persistent


def rmdir(directory):
    try:
        shutil.rmtree(directory)
    except OSError:
        pass


def test_core():
    rmdir('/tmp/diskcache')
    failures, _ = doctest.testmod(diskcache.core)
    assert failures == 0


def test_djangocache():
    rmdir('/tmp/diskcache')
    failures, _ = doctest.testmod(diskcache.djangocache)
    assert failures == 0


def test_fanout():
    rmdir('/tmp/diskcache')
    failures, _ = doctest.testmod(diskcache.fanout)
    assert failures == 0


def test_persistent():
    rmdir('/tmp/diskcache')
    failures, _ = doctest.testmod(diskcache.persistent)
    assert failures == 0
