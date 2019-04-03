"""Memoization utilities.

"""

from functools import wraps

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
    >>> cache = FanoutCache()
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
    # Caution: Nearly identical code exists in DjangoCache.memoize
    if callable(name):
        raise TypeError('name cannot be callable')

    def decorator(func):
        "Decorator created by memoize call for callable."
        base = (full_name(func),) if name is None else (name,)

        @wraps(func)
        def wrapper(*args, **kwargs):
            "Wrapper for callable to cache arguments and return values."
            key = wrapper.make_key(args, kwargs)
            result = cache.get(key, default=MARK, retry=True)

            if result is MARK:
                result = func(*args, **kwargs)
                cache.set(key, result, expire=expire, tag=tag, retry=True)

            return result

        def make_key(args, kwargs):
            return _args_to_key(base, args, kwargs, typed)

        wrapper.make_key = make_key
        return wrapper

    return decorator
