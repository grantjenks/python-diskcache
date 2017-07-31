from collections import namedtuple

from .core import Cache

import uuid

try:
    from _thread import RLock
except ImportError:
    class RLock:
        'Dummy reentrant lock for builds without threads'

        def __enter__(self): pass

        def __exit__(self, exctype, excinst, exctb): pass

_CacheInfo = namedtuple("CacheInfo", ["hits", "misses", "maxsize", "currsize"])

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


def _make_key(args, kwds, typed,
              kwd_mark=(object(),),
              fasttypes={int, str, frozenset, type(None)},
              sorted=sorted, tuple=tuple, type=type, len=len):
    """Make a cache key from optionally typed positional and keyword arguments

    The key is constructed in a way that is flat as possible rather than
    as a nested structure that would take more memory.

    If there is only a single argument and its data type is known to cache
    its hash value, then that argument is returned without a wrapper.  This
    saves space and improves lookup speed.

    """
    key = args
    if kwds:
        sorted_items = sorted(kwds.items())
        key += kwd_mark
        for item in sorted_items:
            key += item
    if typed:
        key += tuple(type(v) for v in args)
        if kwds:
            key += tuple(type(v) for k, v in sorted_items)
    return key


def lru_cache(maxsize=128, typed=False, cache_path=None):
    """Least-recently-used cache decorator.

    If *maxsize* is set to None, the LRU features are disabled and the cache
    can grow without bound.

    If *typed* is True, arguments of different types will be cached separately.
    For example, f(3.0) and f(3) will be treated as distinct calls with
    distinct results.

    Arguments to the cached function must be hashable.

    View the cache statistics named tuple (hits, misses, maxsize, currsize)
    with f.cache_info().  Clear the cache and statistics with f.cache_clear().
    Access the underlying function with f.__wrapped__.

    See:  http://en.wikipedia.org/wiki/Cache_algorithms#Least_Recently_Used

    """

    # Users should only access the lru_cache through its public API:
    #       cache_info, cache_clear, and f.__wrapped__
    # The internals of the lru_cache are encapsulated for thread safety and
    # to allow the implementation to change (including a possible C version).

    # Early detection of an erroneous call to @lru_cache without any arguments
    # resulting in the inner function being passed to maxsize instead of an
    # integer or None.
    if maxsize is not None and not isinstance(maxsize, int):
        raise TypeError('Expected maxsize to be an integer or None')

    def decorating_function(user_function):
        wrapper = _lru_cache_wrapper(user_function, maxsize, typed, _CacheInfo, cache_path)
        return update_wrapper(wrapper, user_function)

    return decorating_function


def _lru_cache_wrapper(user_function, maxsize, typed, _CacheInfo, cache_path):
    # Constants shared by all lru cache instances:
    sentinel = object()  # unique object used to signal cache misses
    make_key = _make_key  # build a key from the function arguments
    PREV, NEXT, KEY, RESULT = 0, 1, 2, 3  # names for the link fields
    if cache_path is None:
        cache_path = str(uuid.uuid4())

    with Cache(cache_path) as cache:
        cache_get = cache.get  # bound method to lookup a key or return None
        lock = RLock()  # because linkedlist updates aren't threadsafe
        root = []  # root of the circular doubly linked list
        root[:] = [root, root, None, None]  # initialize by pointing to self
        nonlocal_data = {
            'hits': 0,
            'misses': 0,
            'full': False,
            'root': root,
        }

        if maxsize == 0:
            def wrapper(*args, **kwds):
                # No caching -- just a statistics update after a successful call
                result = user_function(*args, **kwds)
                nonlocal_data['misses'] += 1
                return result

        elif maxsize is None:
            def wrapper(*args, **kwds):
                # Simple caching without ordering or size limit
                key = make_key(args, kwds, typed)
                result = cache_get(key, sentinel)
                if result is not sentinel:
                    nonlocal_data['hits'] += 1
                    return result
                result = user_function(*args, **kwds)
                cache[key] = result
                nonlocal_data['misses'] += 1
                return result

        else:
            def wrapper(*args, **kwds):
                # Size limited caching that tracks accesses by recency
                root = nonlocal_data['root']
                key = make_key(args, kwds, typed)
                with lock:
                    link = cache_get(key)
                    if link is not None:
                        # Move the link to the front of the circular queue
                        link_prev, link_next, _key, result = link
                        link_prev[NEXT] = link_next
                        link_next[PREV] = link_prev
                        last = root[PREV]
                        last[NEXT] = root[PREV] = link
                        link[PREV] = last
                        link[NEXT] = root
                        nonlocal_data['hits'] += 1
                        return result
                result = user_function(*args, **kwds)
                with lock:
                    if key in cache:
                        # Getting here means that this same key was added to the
                        # cache while the lock was released.  Since the link
                        # update is already done, we need only return the
                        # computed result and update the count of misses.
                        pass
                    elif nonlocal_data['full']:
                        # Use the old root to store the new key and result.
                        oldroot = root
                        oldroot[KEY] = key
                        oldroot[RESULT] = result
                        # Empty the oldest link and make it the new root.
                        # Keep a reference to the old key and old result to
                        # prevent their ref counts from going to zero during the
                        # update. That will prevent potentially arbitrary object
                        # clean-up code (i.e. __del__) from running while we're
                        # still adjusting the links.
                        root = oldroot[NEXT]
                        oldkey = root[KEY]
                        oldresult = root[RESULT]
                        root[KEY] = root[RESULT] = None
                        # Now update the cache dictionary.
                        del cache[oldkey]
                        # Save the potentially reentrant cache[key] assignment
                        # for last, after the root and links have been put in
                        # a consistent state.
                        cache[key] = oldroot
                        nonlocal_data['root'] = root    
                    else:
                        # Put result in a new link at the front of the queue.
                        last = root[PREV]
                        link = [last, root, key, result]
                        last[NEXT] = root[PREV] = cache[key] = link
                        # Use the __len__() method instead of the len() function
                        # which could potentially be wrapped in an lru_cache itself.
                        nonlocal_data['full'] = (cache.__len__() >= maxsize)
                    nonlocal_data['misses'] += 1
                return result

    def cache_info():
        """Report cache statistics"""
        with lock:
            return _CacheInfo(nonlocal_data['hits'], nonlocal_data['misses'], maxsize, cache.__len__())

    def cache_clear():
        """Clear the cache and cache statistics"""

        with lock:
            cache.clear()
            root[:] = [root, root, None, None]
            nonlocal_data['root'] = root
            nonlocal_data['hits'] = nonlocal_data['misses'] = 0
            nonlocal_data['full'] = False

    wrapper.cache_info = cache_info
    wrapper.cache_clear = cache_clear
    return wrapper

