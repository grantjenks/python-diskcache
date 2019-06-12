"""Disk Cache Recipes

"""

import functools
import math
import os
import random
import threading
import time

from .core import ENOVAL, args_to_key, full_name


class Averager(object):
    """Recipe for calculating a running average.

    Sometimes known as "online statistics," the running average maintains the
    total and count. The average can then be calculated at any time.

    >>> import diskcache
    >>> cache = diskcache.Cache()
    >>> ave = Averager(cache, 'latency')
    >>> ave.add(0.080)
    >>> ave.add(0.120)
    >>> ave.get()
    0.1
    >>> ave.add(0.160)
    >>> ave.get()
    0.12

    """
    def __init__(self, cache, key, expire=None, tag=None):
        self._cache = cache
        self._key = key
        self._expire = expire
        self._tag = tag

    def add(self, value):
        "Add `value` to average."
        with self._cache.transact():
            total, count = self._cache.get(self._key, default=(0.0, 0))
            total += value
            count += 1
            self._cache.set(
                self._key, (total, count), expire=self._expire, tag=self._tag,
            )

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
    >>> cache = diskcache.Cache()
    >>> lock = Lock(cache, 'report-123')
    >>> lock.acquire()
    >>> lock.release()
    >>> with lock:
    ...     pass

    """
    def __init__(self, cache, key, expire=None, tag=None):
        self._cache = cache
        self._key = key
        self._expire = expire
        self._tag = tag

    def acquire(self):
        "Acquire lock using spin-lock algorithm."
        while True:
            added = self._cache.add(
                self._key, None, expire=self._expire, tag=self._tag, retry=True,
            )
            if added:
                break
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
    >>> cache = diskcache.Cache()
    >>> rlock = RLock(cache, 'user-123')
    >>> rlock.acquire()
    >>> rlock.acquire()
    >>> rlock.release()
    >>> with rlock:
    ...     pass
    >>> rlock.release()
    >>> rlock.release()
    Traceback (most recent call last):
      ...
    AssertionError: cannot release un-acquired lock

    """
    def __init__(self, cache, key, expire=None, tag=None):
        self._cache = cache
        self._key = key
        self._expire = expire
        self._tag = tag
        pid = os.getpid()
        tid = threading.get_ident()
        self._value = '{}-{}'.format(pid, tid)

    def acquire(self):
        "Acquire lock by incrementing count using spin-lock algorithm."
        while True:
            with self._cache.transact():
                value, count = self._cache.get(self._key, default=(None, 0))
                if self._value == value or count == 0:
                    self._cache.set(
                        self._key, (self._value, count + 1),
                        expire=self._expire, tag=self._tag,
                    )
                    return
            time.sleep(0.001)

    def release(self):
        "Release lock by decrementing count."
        with self._cache.transact():
            value, count = self._cache.get(self._key, default=(None, 0))
            is_owned = self._value == value and count > 0
            assert is_owned, 'cannot release un-acquired lock'
            self._cache.set(
                self._key, (value, count - 1), expire=self._expire,
                tag=self._tag,
            )

    def __enter__(self):
        self.acquire()

    def __exit__(self, *exc_info):
        self.release()


class BoundedSemaphore(object):
    """Recipe for cross-process and cross-thread bounded semaphore.

    >>> import diskcache
    >>> cache = diskcache.Cache()
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
    def __init__(self, cache, key, value=1, expire=None, tag=None):
        self._cache = cache
        self._key = key
        self._value = value
        self._expire = expire
        self._tag = tag

    def acquire(self):
        "Acquire semaphore by decrementing value using spin-lock algorithm."
        while True:
            with self._cache.transact():
                value = self._cache.get(self._key, default=self._value)
                if value > 0:
                    self._cache.set(
                        self._key, value - 1, expire=self._expire,
                        tag=self._tag,
                    )
                    return
            time.sleep(0.001)

    def release(self):
        "Release semaphore by incrementing value."
        with self._cache.transact():
            value = self._cache.get(self._key, default=self._value)
            assert self._value > value, 'cannot release un-acquired semaphore'
            value += 1
            self._cache.set(
                self._key, value, expire=self._expire, tag=self._tag,
            )

    def __enter__(self):
        self.acquire()

    def __exit__(self, *exc_info):
        self.release()


def throttle(cache, count, seconds, name=None, expire=None, tag=None,
             time_func=time.time, sleep_func=time.sleep):
    """Decorator to throttle calls to function.

    >>> import diskcache, time
    >>> cache = diskcache.Cache()
    >>> count = 0
    >>> @throttle(cache, 5, 1)
    ... def increment():
    ...     global count
    ...     count += 1
    >>> start = time.time()
    >>> while (time.time() - start) <= 4:
    ...     increment()
    >>> count
    25

    """
    def decorator(func):
        rate = count / float(seconds)

        if name is None:
            try:
                key = func.__qualname__
            except AttributeError:
                key = func.__name__

            key = func.__module__ + '.' + key
        else:
            key = name

        now = time_func()
        cache.set(key, (now, count), expire=expire, tag=tag, retry=True)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            while True:
                with cache.transact():
                    last, tally = cache.get(key, retry=True)
                    now = time_func()
                    tally += (now - last) * rate
                    delay = 0

                    if tally > count:
                        cache.set(key, (now, count - 1), expire, retry=True)
                    elif tally >= 1:
                        cache.set(key, (now, tally - 1), expire, retry=True)
                    else:
                        delay = (1 - tally) / rate

                if delay:
                    sleep_func(delay)
                else:
                    break

            return func(*args, **kwargs)

        return wrapper

    return decorator


def barrier(cache, lock_factory, name=None, expire=None, tag=None):
    """Barrier to calling decorated function.

    Supports different kinds of locks: Lock, RLock, BoundedSemaphore.

    >>> import diskcache, time
    >>> cache = diskcache.Cache()
    >>> @barrier(cache, Lock)
    ... def work(num):
    ...     time.sleep(1)
    ...     return int(time.time())
    >>> from concurrent.futures import ThreadPoolExecutor
    >>> with ThreadPoolExecutor(4) as executor:
    ...     times = sorted(executor.map(work, range(4)))
    >>> [times[i] - times[i - 1] for i in range(1, 4)]
    [1, 1, 1]

    """
    def decorator(func):
        key = full_name(func) if name is None else name
        lock = lock_factory(cache, key, expire=expire, tag=tag)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)

        return wrapper

    return decorator


def memoize_stampede(cache, expire, name=None, typed=False, tag=None, beta=1):
    """Memoizing cache decorator with cache stampede protection.

    Cache stampedes are a type of cascading failure that can occur when
    parallel computing systems using memoization come under heavy load. This
    behaviour is sometimes also called dog-piling, cache miss storm, cache
    choking, or the thundering herd problem.

    The memoization decorator implements cache stampede protection through
    early recomputation. Early recomputation of function results will occur
    probabilistically before expiration in a background thread of
    execution. Early probabilistic recomputation is based on research by
    Vattani, A.; Chierichetti, F.; Lowenstein, K. (2015), Optimal Probabilistic
    Cache Stampede Prevention, VLDB, pp. 886?897, ISSN 2150-8097

    If name is set to None (default), the callable name will be determined
    automatically.

    If typed is set to True, function arguments of different types will be
    cached separately. For example, f(3) and f(3.0) will be treated as distinct
    calls with distinct results.

    The original underlying function is accessible through the __wrapped__
    attribute. This is useful for introspection, for bypassing the cache, or
    for rewrapping the function with a different cache.

    >>> from diskcache import Cache
    >>> cache = Cache()
    >>> @memoize_stampede(cache, expire=1)
    ... def fibonacci(number):
    ...     if number == 0:
    ...         return 0
    ...     elif number == 1:
    ...         return 1
    ...     else:
    ...         return fibonacci(number - 1) + fibonacci(number - 2)
    >>> print(fibonacci(100))
    354224848179261915075

    An additional `__cache_key__` attribute can be used to generate the cache
    key used for the given arguments.

    >>> key = fibonacci.__cache_key__(100)
    >>> del cache[key]

    Remember to call memoize when decorating a callable. If you forget, then a
    TypeError will occur.

    :param cache: cache to store callable arguments and return values
    :param float expire: seconds until arguments expire
    :param str name: name given for callable (default None, automatic)
    :param bool typed: cache different types separately (default False)
    :param str tag: text to associate with arguments (default None)
    :return: callable decorator

    """
    # Caution: Nearly identical code exists in Cache.memoize
    def decorator(func):
        "Decorator created by memoize call for callable."
        base = (full_name(func),) if name is None else (name,)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            "Wrapper for callable to cache arguments and return values."
            key = wrapper.__cache_key__(*args, **kwargs)
            pair, expire_time = cache.get(
                key, default=ENOVAL, expire_time=True, retry=True,
            )

            def recompute():
                start = time.time()
                result = func(*args, **kwargs)
                delta = time.time() - start
                pair = result, delta
                cache.set(key, pair, expire=expire, tag=tag, retry=True)
                return result

            if pair is not ENOVAL:
                result, delta = pair
                now = time.time()
                ttl = expire_time - now

                if (-delta * beta * math.log(random.random())) < ttl:
                    return result  # Cache hit.

                # Check whether a thread has started for early recomputation.

                thread_key = key + (ENOVAL,)
                thread_added = cache.add(thread_key, None, expire=delta)

                if thread_added:
                    # Start thread for early recomputation.
                    thread = threading.Thread(target=recompute)
                    thread.daemon = True
                    thread.start()

                return result

            return recompute()  # Cache miss.

        def __cache_key__(*args, **kwargs):
            "Make key for cache given function arguments."
            return args_to_key(base, args, kwargs, typed)

        wrapper.__cache_key__ = __cache_key__
        return wrapper

    return decorator
