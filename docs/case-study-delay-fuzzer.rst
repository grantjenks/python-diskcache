Case Study: Delay Fuzzer
========================

Raymond keynote:
https://dl.dropboxusercontent.com/u/3967849/pybay2017_keynote/_build/html/index.html

Fuzzing technique:
https://dl.dropboxusercontent.com/u/3967849/pybay2017_keynote/_build/html/threading.html#fuzzing

Code below is simple on purpose. Not something to use in production. Ok for
testing.

// discuss sys.settrace

    >>> def delayfuzzer(function):
    ...     """Insert random delays into function.
    ...
    ...     WARNING: Not to be used in production scenarios.
    ...     The use of `sys.settrace` may affect other Python
    ...     tools like `pdb` and `coverage`.
    ...
    ...     Decorator to insert random delays into a function to
    ...     encourage race conditions in multi-threaded code.
    ...
    ...     """
    ...     from functools import wraps
    ...     from sys import settrace
    ...
    ...     try:
    ...         code = function.__code__
    ...     except AttributeError:  # Python 2 compatibility.
    ...         code = function.co_code
    ...
    ...     def tracer(frame, event, arg):
    ...         "Activate sleeper in calls to function."
    ...         if event == 'call' and frame.f_code is code:
    ...             return sleeper
    ...
    ...     @wraps(function)
    ...     def wrapper(*args, **kwargs):
    ...         """Set tracer before calling function.
    ...
    ...         Tracing is thread-local so set the tracer before
    ...         every function call.
    ...
    ...         """
    ...         settrace(tracer)
    ...         return function(*args, **kwargs)
    ...
    ...     return wrapper

Sleeper function that prints location:

    >>> from time import sleep
    >>> from random import expovariate
    >>> def sleeper(frame, event, arg):
    ...     "Sleep for random period."
    ...     lineno = frame.f_lineno
    ...     print('Tracing line %s in diskcache/core.py' % lineno)
    ...     sleep(expovariate(100))

Check that it's working:

    >>> import diskcache
    >>> diskcache.Cache.incr = delayfuzzer(diskcache.Cache.incr)
    >>> cache = diskcache.FanoutCache('tmp')
    >>> cache.incr(0)
    Tracing line 797 in diskcache/core.py
    Tracing line 798 in diskcache/core.py
    Tracing line 800 in diskcache/core.py
    Tracing line 804 in diskcache/core.py
    Tracing line 805 in diskcache/core.py
    Tracing line 807 in diskcache/core.py
    Tracing line 808 in diskcache/core.py
    Tracing line 811 in diskcache/core.py
    Tracing line 812 in diskcache/core.py
    Tracing line 813 in diskcache/core.py
    Tracing line 814 in diskcache/core.py
    Tracing line 815 in diskcache/core.py
    Tracing line 815 in diskcache/core.py
    1
    >>> cache.clear()
    1

Simple sleeper function:

    >>> def sleeper(frame, event, arg):
    ...     "Sleep for random period."
    ...     sleep(expovariate(100))

Increment all numbers in a range:

    >>> def task(cache):
    ...     for num in range(100):
    ...         cache.incr(num, retry=True)

Process worker to start many tasks in separate threads.

    >>> import threading
    >>> def worker():
    ...     cache = diskcache.FanoutCache('tmp')
    ...     threads = []
    ...
    ...     for num in range(8):
    ...         thread = threading.Thread(target=task, args=(cache,))
    ...         threads.append(thread)
    ...
    ...     for thread in threads:
    ...         thread.start()
    ...
    ...     for thread in threads:
    ...         thread.join()

Start many worker processes:

    >>> import multiprocessing
    >>> def main():
    ...     processes = []
    ...
    ...     for _ in range(8):
    ...         process = multiprocessing.Process(target=worker)
    ...         processes.append(process)
    ...
    ...     for process in processes:
    ...         process.start()
    ...
    ...     for process in processes:
    ...         process.join()

Ok, here goes:

    >>> main()
    >>> sorted(cache) == list(range(100))
    True
    >>> all(cache[key] == 64 for key in cache)
    True

Yaay! It worked.
