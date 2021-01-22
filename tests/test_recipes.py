"Test diskcache.recipes."

import shutil
import threading
import time

import pytest

import diskcache as dc


@pytest.fixture
def cache():
    with dc.Cache() as cache:
        yield cache
    shutil.rmtree(cache.directory, ignore_errors=True)


def test_averager(cache):
    nums = dc.Averager(cache, 'nums')
    for i in range(10):
        nums.add(i)
    assert nums.get() == 4.5
    assert nums.pop() == 4.5
    for i in range(20):
        nums.add(i)
    assert nums.get() == 9.5
    assert nums.pop() == 9.5


def test_rlock(cache):
    state = {'num': 0}
    rlock = dc.RLock(cache, 'demo')

    def worker():
        state['num'] += 1
        with rlock:
            state['num'] += 1
            time.sleep(0.1)

    with rlock:
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.1)
        assert state['num'] == 1
    thread.join()
    assert state['num'] == 2


def test_semaphore(cache):
    state = {'num': 0}
    semaphore = dc.BoundedSemaphore(cache, 'demo', value=3)

    def worker():
        state['num'] += 1
        with semaphore:
            state['num'] += 1
            time.sleep(0.1)

    semaphore.acquire()
    semaphore.acquire()
    with semaphore:
        thread = threading.Thread(target=worker)
        thread.start()
        time.sleep(0.1)
        assert state['num'] == 1
    thread.join()
    assert state['num'] == 2
    semaphore.release()
    semaphore.release()


def test_memoize_stampede(cache):
    state = {'num': 0}

    @dc.memoize_stampede(cache, 0.1)
    def worker(num):
        time.sleep(0.01)
        state['num'] += 1
        return num

    start = time.time()
    while (time.time() - start) < 1:
        worker(100)
    assert state['num'] > 0
