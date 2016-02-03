"Stampede barrier implementation."

from .core import Cache
import functools as ft
import math
import random
import tempfile


class StampedeBarrier(object):
    """Stampede barrier mitigates cache stampedes.

    Cache stampedes are also known as dog-piling, cache miss storm, or cache
    choking.

    Based on research by Vattani, A.; Chierichetti, F.; Lowenstein, K. (2015),
    Optimal Probabilistic Cache Stampede Prevention,
    VLDB, pp. 886–897, ISSN 2150-8097

    Example:

    >>> stampede_barrier = StampedeBarrier('/tmp/user_data', expire=3)
    >>> @stampede_barrier
    def load_user_info(user_id):
        return database.lookup_user_info_by_id(user_id)

    """
    def __init__(self, cache=None, expire=None):
        if cache is None:
            cache = Cache(tempfile.mkdtemp())

        self._cache = cache
        self._expire = expire

    def __call__(self, func):
        cache = self._cache
        expire = self._expire

        ft.wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, kwargs)

            try:
                result, delta, expire_time = cache[key]
                now = time.time()
                ttl = expire_time - now
                
                if (-delta * math.log(random.random())) < ttl:
                    return result

            except KeyError:
                pass

            now = time.time()
            result = func(*args, **kwargs)
            delta = time.time() - start
            expire_time = now + expire
            cache.set(key, (result, delta, expire_time), expire=expire)

            return result

        return wrapper
