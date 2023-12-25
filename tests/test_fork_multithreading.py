"""
Test diskcache.core.Cache behaviour when process is forking.
Make sure it does not deadlock on the sqlite3 transaction lock if
forked while the lock is in use.
"""

import errno
import hashlib
import io
import os
import os.path as op
import sys
import pathlib
import pickle
import shutil
import sqlite3
import subprocess as sp
import tempfile
import threading
import time
import warnings
from threading import Thread
from unittest import mock

if sys.platform != "win32":
    import signal

import pytest

import diskcache as dc

REPEATS = 1000

@pytest.fixture
def cache():
    with dc.Cache() as cache:
        yield cache
    shutil.rmtree(cache.directory, ignore_errors=True)

def _test_thread_imp(cache):
    for i in range(REPEATS * 10):
        cache.set(i, i)

def _test_wait_pid(pid):
    _, status = os.waitpid(pid, 0)
    assert status == 0, "Child died unexpectedly"

@pytest.mark.skipif(sys.platform == "win32", reason="skips this test on Windows")
def test_fork_multithreading(cache):
    thread = Thread(target=_test_thread_imp, args=(cache,))
    thread.start()
    try:
        for i in range(REPEATS):
            pid = os.fork()
            if pid == 0:
                cache.set(i, 0)
                os._exit(0)
            else:
                thread = Thread(target=_test_wait_pid, args=(pid,))
                thread.start()                
                thread.join(timeout=10)
                if thread.is_alive():
                    os.kill(pid, signal.SIGKILL)
                    thread.join()
                    assert False, "Deadlock detected."
    except OSError as e:
        if e.errno != errno.EINTR:
            raise

    thread.join()

