from collections import namedtuple

from diskcache import EVICTION_POLICY
from .fanout import FanoutCache

from tempfile import mkdtemp

_CacheInfo = namedtuple("CacheInfo", ["hits", "misses"])

try:
    from _thread import RLock
except ImportError:
    class RLock:
        'Dummy reentrant lock for builds without threads'

        def __enter__(self): pass

        def __exit__(self, exctype, excinst, exctb): pass


WRAPPER_ASSIGNMENTS = ('__module__', '__name__', '__qualname__', '__doc__',
                       '__annotations__')
WRAPPER_UPDATES = ('__dict__',)


def update_wrapper(wrapper,
                   wrapped,
                   assigned=WRAPPER_ASSIGNMENTS,
                   updated=WRAPPER_UPDATES):
    """Update a wrapper function to look like the wrapped function

       wrapper is the function to be updated
       wrapped is the original function
       assigned is a tuple naming the attributes assigned directly
       from the wrapped function to the wrapper function (defaults to
       functools.WRAPPER_ASSIGNMENTS)
       updated is a tuple naming the attributes of the wrapper that
       are updated with the corresponding attribute from the wrapped
       function (defaults to functools.WRAPPER_UPDATES)
    """
    for attr in assigned:
        try:
            value = getattr(wrapped, attr)
        except AttributeError:
            pass
        else:
            setattr(wrapper, attr, value)
    for attr in updated:
        getattr(wrapper, attr).update(getattr(wrapped, attr, {}))
    # Issue #17482: set __wrapped__ last so we don't inadvertently copy it
    # from the wrapped function when updating __dict__
    wrapper.__wrapped__ = wrapped
    # Return the wrapper so this can be used as a decorator via partial()
    return wrapper


def _make_key(args, kwds,
              kwd_mark=(object(),),
              sorted=sorted, tuple=tuple, type=type, len=len):
    # Make a cache key from optionally typed positional and keyword arguments

    key = args
    if kwds:
        sorted_items = sorted(kwds.items())
        key += kwd_mark
        for item in sorted_items:
            key += item
    return key


def lru_cache(directory=None, use_statistics=False):
    """Least-recently-used cache decorator.

    If *maxsize* is set to None, the LRU features are disabled and the cache
    can grow without bound.

    View the cache statistics named tuple (hits, misses, maxsize, currsize)
    with f.cache_info().  Clear the cache and statistics with f.cache_clear().
    Access the underlying function with f.__wrapped__.

    See:  http://en.wikipedia.org/wiki/Cache_algorithms#Least_Recently_Used

    """

    # Users should only access the lru_cache through its public API:
    #       cache_info, cache_clear, and f.__wrapped__
    # The internals of the lru_cache are encapsulated for thread safety and
    # to allow the implementation to change (including a possible C version).

    def decorating_function(user_function):
        wrapper = _lru_cache_wrapper(user_function, directory, use_statistics)
        return update_wrapper(wrapper, user_function)

    return decorating_function


def _lru_cache_wrapper(user_function, directory=None, use_statistics=False):
    # Constants shared by all lru cache instances:
    sentinel = object()  # unique object used to signal cache misses
    make_key = _make_key  # build a key from the function arguments

    if directory is None:
        directory = mkdtemp()

    with FanoutCache(directory, statistics=use_statistics, eviction_policy='least-recently-used') as cache:
        cache_get = cache.get  # bound method to lookup a key or return None

        def wrapper(*args, **kwds):
            key = make_key(args, kwds)
            result = cache_get(key)
            if result:
                return result
            result = user_function(*args, **kwds)
            cache[key] = result
            return result

    def cache_info():
        """Report cache statistics"""
        return _CacheInfo(*cache.stats()) if use_statistics else _CacheInfo(0, 0)

    def cache_clear():
        """Clear the cache and cache statistics"""
        if use_statistics:
            cache.clear()
            cache.stats(reset=True)

    wrapper.cache_info = cache_info
    wrapper.cache_clear = cache_clear
    return wrapper

