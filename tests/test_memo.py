import sys

from diskcache.decorators import lru_cache

if sys.hexversion < 0x03000000:
    range = xrange


def test_lru_cache_decorator_with_infinite_cache_size():
    # settings cache_size to infinite (fib function will cache every value)
    @lru_cache(use_statistics=True)
    def fib(num):
        if num <= 2:
            return 1
        return fib(num-1) + fib(num-2)

    for i in range(1000):
        fib(i)

    hist_counter = fib.cache_info().hits
    initial_miss_counter = fib.cache_info().misses

    for i in range(1000):
        fib(i)
    # ensuring that every value was cached during invoking fib function in second for loop
    assert fib.cache_info().hits == hist_counter + 1000
    # ensuring that no miss were made during second for loop
    assert fib.cache_info().misses == initial_miss_counter
