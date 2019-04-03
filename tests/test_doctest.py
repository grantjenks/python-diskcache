import doctest
import shutil
import sys

import diskcache.core
import diskcache.djangocache
import diskcache.fanout
import diskcache.memo
import diskcache.persistent
import diskcache.recipes


def test_core():
    failures, _ = doctest.testmod(diskcache.core)
    assert failures == 0


def test_djangocache():
    failures, _ = doctest.testmod(diskcache.djangocache)
    assert failures == 0


def test_fanout():
    failures, _ = doctest.testmod(diskcache.fanout)
    assert failures == 0


def test_memo():
    failures, _ = doctest.testmod(diskcache.memo)
    assert failures == 0


def test_persistent():
    failures, _ = doctest.testmod(diskcache.persistent)
    assert failures == 0


def test_tutorial():
    if sys.hexversion < 0x03000000:
        return
    failures, _ = doctest.testfile('../docs/tutorial.rst')
    assert failures == 0


def test_recipes():
    if sys.hexversion < 0x03000000:
        return
    failures, _ = doctest.testmod(diskcache.recipes)
    assert failures == 0
