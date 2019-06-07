"""Memoization utilities.

"""

from functools import wraps
from math import log
from random import random
from threading import Thread
from time import time

MARK = object()


def full_name(func):
    "Return full name of `func` by adding the module and function name."
    try:
        # The __qualname__ attribute is only available in Python 3.3 and later.
        # GrantJ 2019-03-29 Remove after support for Python 2 is dropped.
        name = func.__qualname__
    except AttributeError:
        name = func.__name__
    return func.__module__ + '.' + name


def _args_to_key(base, args, kwargs, typed):
    """Create cache key out of function arguments.

    :param tuple base: base of key
    :param tuple args: function arguments
    :param dict kwargs: function keyword arguments
    :param bool typed: include types in cache key
    :return: cache key tuple

    """
    key = base + args

    if kwargs:
        key += (MARK,)
        sorted_items = sorted(kwargs.items())

        for item in sorted_items:
            key += item

    if typed:
        key += tuple(type(arg) for arg in args)

        if kwargs:
            key += tuple(type(value) for _, value in sorted_items)

    return key


def memoize(cache, name=None, typed=False, expire=None, tag=None,
            early_recompute=False, time_func=time):
    """Memoizing cache decorator.

    Decorator to wrap callable with memoizing function using cache. Repeated
    calls with the same arguments will lookup result in cache and avoid
    function evaluation.

    If name is set to None (default), the callable name will be determined
    automatically.

    If typed is set to True, function arguments of different types will be
    cached separately. For example, f(3) and f(3.0) will be treated as distinct
    calls with distinct results.

    Cache stampedes are a type of cascading failure that can occur when
    parallel computing systems using memoization come under heavy load. This
    behaviour is sometimes also called dog-piling, cache miss storm, cache
    choking, or the thundering herd problem.

    The memoization decorator includes cache stampede protection through the
    early recomputation parameter. When set to True (default False), the expire
    parameter must not be None. Early recomputation of results will occur
    probabilistically before expiration.

    Early probabilistic recomputation is based on research by Vattani, A.;
    Chierichetti, F.; Lowenstein, K. (2015), Optimal Probabilistic Cache
    Stampede Prevention, VLDB, pp. 886?897, ISSN 2150-8097

    The original underlying function is accessible through the __wrapped__
    attribute. This is useful for introspection, for bypassing the cache, or
    for rewrapping the function with a different cache.

    >>> from diskcache import FanoutCache
    >>> cache = FanoutCache()
    >>> @cache.memoize(typed=True, expire=1, tag='fib')
    ... def fibonacci(number):
    ...     if number == 0:
    ...         return 0
    ...     elif number == 1:
    ...         return 1
    ...     else:
    ...         return fibonacci(number - 1) + fibonacci(number - 2)
    >>> print(fibonacci(100))
    354224848179261915075

    An additional `__cache_key__` attribute can be used to generate the cache key
    used for the given arguments.

    >>> key = fibonacci.__cache_key__(100)
    >>> print(cache[key])
    354224848179261915075

    Remember to call memoize when decorating a callable. If you forget, then a
    TypeError will occur. Note the lack of parenthenses after memoize below:

    >>> @cache.memoize
    ... def test():
    ...     pass
    Traceback (most recent call last):
        ...
    TypeError: name cannot be callable

    :param cache: cache to store callable arguments and return values
    :param str name: name given for callable (default None, automatic)
    :param bool typed: cache different types separately (default False)
    :param float expire: seconds until arguments expire
        (default None, no expiry)
    :param str tag: text to associate with arguments (default None)
    :param bool early_recompute: probabilistic early recomputation
        (default False)
    :param time_func: callable for calculating current time
    :return: callable decorator

    """
    # Caution: Nearly identical code exists in DjangoCache.memoize
    if callable(name):
        raise TypeError('name cannot be callable')

    if early_recompute and expire is None:
        raise ValueError('expire required')

    def decorator(func):
        "Decorator created by memoize call for callable."
        base = (full_name(func),) if name is None else (name,)

        if early_recompute:
            @wraps(func)
            def wrapper(*args, **kwargs):
                "Wrapper for callable to cache arguments and return values."
                key = wrapper.__cache_key__(*args, **kwargs)
                pair, expire_time = cache.get(
                    key, default=MARK, expire_time=True, retry=True,
                )

                def recompute():
                    start = time_func()
                    result = func(*args, **kwargs)
                    delta = time_func() - start
                    pair = result, delta
                    cache.set(key, pair, expire=expire, tag=tag, retry=True)
                    return result

                if pair is not MARK:
                    result, delta = pair
                    now = time_func()
                    ttl = expire_time - now

                    if (-delta * early_recompute * log(random())) < ttl:
                        return result
                    elif True: # Background
                        # How to support asyncio?
                        thread_key = key + (MARK,)
                        if cache.add(thread_key, None, expire=delta):
                            thread = Thread(target=recompute)
                            thread.daemon = True
                            thread.start()
                        return result

                return recompute()
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                "Wrapper for callable to cache arguments and return values."
                key = wrapper.__cache_key__(*args, **kwargs)
                result = cache.get(key, default=MARK, retry=True)

                if result is MARK:
                    result = func(*args, **kwargs)
                    cache.set(key, result, expire=expire, tag=tag, retry=True)

                return result

        def __cache_key__(*args, **kwargs):
            "Make key for cache given function arguments."
            return _args_to_key(base, args, kwargs, typed)

        wrapper.__cache_key__ = __cache_key__
        return wrapper

    return decorator
