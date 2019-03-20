import doctest
import shutil
import sys

import diskcache.core
import diskcache.djangocache
import diskcache.fanout
import diskcache.memo
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


def test_memo():
    rmdir('/tmp/diskcache')
    failures, _ = doctest.testmod(diskcache.memo)
    assert failures == 0


def test_persistent():
    rmdir('/tmp/diskcache')
    failures, _ = doctest.testmod(diskcache.persistent)
    assert failures == 0


def test_tutorial():
    if sys.hexversion < 0x03000000:
        return
    rmdir('/tmp/mycachedir')
    rmdir('/tmp/mydir')
    failures, _ = doctest.testfile('../docs/tutorial.rst')
    assert failures == 0
