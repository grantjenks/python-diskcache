"""Cache Recipes


"""

import os
import threading
import time


class Averager(object):
    """Recipe for calculating a running average.

    Sometimes known as "online statistics," the running average maintains the
    total and count. The average can then be calculated at any time.

    >>> import diskcache
    >>> cache = diskcache.Cache('/tmp/diskcache/recipes')
    >>> ave = Averager(cache, 'latency')
    >>> ave.add(0.080)
    >>> ave.add(0.120)
    >>> ave.get()
    0.1
    >>> ave.add(0.160)
    >>> ave.get()
    0.12

    """
    def __init__(self, cache, key):
        self._cache = cache
        self._key = key

    def add(self, value):
        "Add `value` to average."
        with self._cache.transact():
            total, count = self._cache.get(self._key, default=(0.0, 0))
            total += value
            count += 1
            self._cache.set(self._key, (total, count))

    def get(self):
        "Get current average."
        total, count = self._cache.get(self._key, default=(0.0, 0), retry=True)
        return 0.0 if count == 0 else total / count

    def pop(self):
        "Return current average and reset average to 0.0."
        total, count = self._cache.pop(self._key, default=(0.0, 0), retry=True)
        return 0.0 if count == 0 else total / count


class Lock(object):
    """Recipe for cross-process and cross-thread lock.

    >>> import diskcache
    >>> cache = diskcache.Cache('/tmp/diskcache/recipes')
    >>> lock = Lock(cache, 'report-123')
    >>> lock.acquire()
    >>> lock.release()
    >>> with lock:
    ...     pass

    """
    def __init__(self, cache, key):
        self._cache = cache
        self._key = key

    def acquire(self):
        "Acquire lock using spin-lock algorithm."
        while True:
            if self._cache.add(self._key, None, retry=True):
                return
            time.sleep(0.001)

    def release(self):
        "Release lock by deleting key."
        self._cache.delete(self._key, retry=True)

    def __enter__(self):
        self.acquire()

    def __exit__(self, *exc_info):
        self.release()


class RLock(object):
    """Recipe for cross-process and cross-thread re-entrant lock.

    >>> import diskcache
    >>> cache = diskcache.Cache('/tmp/diskcache/recipes')
    >>> rlock = RLock(cache, 'user-123')
    >>> rlock.acquire()
    >>> rlock.acquire()
    >>> rlock.release()
    >>> rlock.release()
    >>> with rlock:
    ...     pass
    >>> rlock.release()
    Traceback (most recent call last):
      ...
    AssertionError: cannot release un-acquired lock

    """
    def __init__(self, cache, key):
        self._cache = cache
        self._key = key
        pid = os.getpid()
        tid = threading.get_ident()
        self._value = '{}-{}'.format(pid, tid)

    def acquire(self):
        "Acquire lock by incrementing count using spin-lock algorithm."
        while True:
            with self._cache.transact():
                value, count = self._cache.get(self._key, default=(None, 0))
                if self._value == value or count == 0:
                    self._cache.set(self._key, (self._value, count + 1))
                    return
            time.sleep(0.001)

    def release(self):
        "Release lock by decrementing count."
        with self._cache.transact():
            value, count = self._cache.get(self._key, default=(None, 0))
            is_owned = self._value == value and count > 0
            assert is_owned, 'cannot release un-acquired lock'
            self._cache.set(self._key, (value, count - 1))

    def __enter__(self):
        self.acquire()

    def __exit__(self, *exc_info):
        self.release()


class BoundedSemaphore(object):
    """Recipe for cross-process and cross-thread bounded semaphore.

    >>> import diskcache
    >>> cache = diskcache.Cache('/tmp/diskcache/recipes')
    >>> semaphore = BoundedSemaphore(cache, 'max-connections', value=2)
    >>> semaphore.acquire()
    >>> semaphore.acquire()
    >>> semaphore.release()
    >>> with semaphore:
    ...     pass
    >>> semaphore.release()
    >>> semaphore.release()
    Traceback (most recent call last):
      ...
    AssertionError: cannot release un-acquired semaphore

    """
    def __init__(self, cache, key, value=1):
        self._cache = cache
        self._key = key
        self._value = value

    def acquire(self):
        "Acquire semaphore by decrementing value using spin-lock algorithm."
        while True:
            with self._cache.transact():
                value = self._cache.get(self._key, default=self._value)
                if value > 0:
                    self._cache.set(self._key, value - 1)
                    return
            time.sleep(0.001)

    def release(self):
        "Release semaphore by incrementing value."
        with self._cache.transact():
            value = self._cache.get(self._key, default=self._value)
            assert self._value > value, 'cannot release un-acquired semaphore'
            value += 1
            self._cache.set(self._key, value)

    def __enter__(self):
        self.acquire()

    def __exit__(self, *exc_info):
        self.release()
