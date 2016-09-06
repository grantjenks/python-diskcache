"Stampede barrier implementation."

import functools as ft
import math
import random
import tempfile
import time

from .core import Cache, ENOVAL


class StampedeBarrier(object):
    """Stampede barrier mitigates cache stampedes.

    Cache stampedes are also known as dog-piling, cache miss storm, cache
    choking, or the thundering herd problem.

    Based on research by Vattani, A.; Chierichetti, F.; Lowenstein, K. (2015),
    Optimal Probabilistic Cache Stampede Prevention,
    VLDB, pp. 886?897, ISSN 2150-8097

    Example:

    >>> stampede_barrier = StampedeBarrier('/tmp/user_data', expire=3)
    >>> @stampede_barrier
    def load_user_info(user_id):
        return database.lookup_user_info_by_id(user_id)

    """
    # pylint: disable=too-few-public-methods
    def __init__(self, cache=None, expire=None):
        if isinstance(cache, Cache):
            pass
        elif cache is None:
            cache = Cache(tempfile.mkdtemp())
        else:
            cache = Cache(cache)

        self._cache = cache
        self._expire = expire

    def __call__(self, func):
        cache = self._cache
        expire = self._expire

        @ft.wraps(func)
        def wrapper(*args, **kwargs):
            "Wrapper function to cache function result."
            key = (args, kwargs)

            try:
                result, expire_time, delta = cache.get(
                    key, default=ENOVAL, expire_time=True, tag=True
                )

                if result is ENOVAL:
                    raise KeyError

                now = time.time()
                ttl = expire_time - now

                if (-delta * math.log(random.random())) < ttl:
                    return result

            except KeyError:
                pass

            now = time.time()
            result = func(*args, **kwargs)
            delta = time.time() - now
            cache.set(key, result, expire=expire, tag=delta)

            return result

        return wrapper
