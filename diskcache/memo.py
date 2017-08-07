"""Memoization utilities.

"""

from functools import wraps

from .core import ENOVAL

def memoize(cache, name=None, typed=False, expire=None, tag=None):
    """Memoizing cache decorator.

    Decorator to wrap callable with memoizing function using cache. Repeated
    calls with the same arguments will lookup result in cache and avoid
    function evaluation.

    If name is set to None (default), the callable name will be determined
    automatically.

    If typed is set to True, function arguments of different types will be
    cached separately. For example, f(3) and f(3.0) will be treated as distinct
    calls with distinct results.

    The original underlying function is accessible through the __wrapped__
    attribute. This is useful for introspection, for bypassing the cache, or
    for rewrapping the function with a different cache.

    >>> from diskcache import FanoutCache
    >>> cache = FanoutCache('/tmp/diskcache/fanoutcache')
    >>> @cache.memoize(typed=True, expire=1, tag='fib')
    ... def fibonacci(number):
    ...     if number == 0:
    ...         return 0
    ...     elif number == 1:
    ...         return 1
    ...     else:
    ...         return fibonacci(number - 1) + fibonacci(number - 2)
    >>> print(sum(fibonacci(number=value) for value in range(100)))
    573147844013817084100

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
    :return: callable decorator

    """
    if callable(name):
        raise TypeError('name cannot be callable')

    def decorator(function):
        "Decorator created by memoize call for callable."
        if name is None:
            try:
                reference = function.__qualname__
            except AttributeError:
                reference = function.__name__

            reference = function.__module__ + reference
        else:
            reference = name

        reference = (reference,)

        @wraps(function)
        def wrapper(*args, **kwargs):
            "Wrapper for callable to cache arguments and return values."

            key = reference + args

            if kwargs:
                key += (ENOVAL,)
                sorted_items = sorted(kwargs.items())

                for item in sorted_items:
                    key += item

            if typed:
                key += tuple(type(arg) for arg in args)

                if kwargs:
                    key += tuple(type(value) for _, value in sorted_items)

            result = cache.get(key, default=ENOVAL, retry=True)

            if result is ENOVAL:
                result = function(*args, **kwargs)
                cache.set(key, result, expire=expire, tag=tag, retry=True)

            return result

        return wrapper

    return decorator
