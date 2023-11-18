import contextlib
import os
import shutil
import sqlite3
import stat
import tempfile

import pytest

import diskcache as dc
from diskcache.core import DBNAME, ReadOnlyError


@pytest.fixture
def cache_directory():
    with contextlib.nullcontext(
        tempfile.mkdtemp(prefix='diskcache-')
    ) as directory:
        yield directory
        shutil.rmtree(directory, ignore_errors=True)


def test_cannot_create(cache_directory):
    with pytest.raises(sqlite3.OperationalError):
        dc.Cache(directory=cache_directory, sqlite_query_only=True)


def test_can_read_only(cache_directory):
    key = 'some'
    obj1 = [5, 6, 7]

    # create the cache, must be in read write mode
    rw = dc.Cache(directory=cache_directory)
    rw[key] = obj1
    rw = None

    # make the file RO
    os.chmod(os.path.join(cache_directory, DBNAME), stat.S_IREAD)

    # with sqlite_query_only=True we can read the DB
    ro = dc.Cache(directory=cache_directory, sqlite_query_only=True)
    obj2 = ro[key]
    ro = None

    assert obj2 == obj1

    # default cache cannot read a ro file
    with pytest.raises(sqlite3.OperationalError):
        dc.Cache(directory=cache_directory)


def test_cannot_update(cache_directory):
    # create the cache, must be in read write mode
    rw = dc.Cache(directory=cache_directory)
    rw['key'] = 'old'
    rw = None

    # re-open ro: cannot update
    ro = dc.Cache(directory=cache_directory, sqlite_query_only=True)
    with pytest.raises(ReadOnlyError):
        ro['key'] = 'new'

    with pytest.raises(ReadOnlyError):
        ro.clear()
