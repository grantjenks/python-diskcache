TODO
* Rename to delay-fuzzer so: case-study-delay-fuzzer
* Check the line numbers! I don't think it's working :(

Raymond keynote:
https://dl.dropboxusercontent.com/u/3967849/pybay2017_keynote/_build/html/index.html

Fuzzing technique:
https://dl.dropboxusercontent.com/u/3967849/pybay2017_keynote/_build/html/threading.html#fuzzing

Code below is simple on purpose. Not something to use in production. Ok for
testing.

// discuss sys.settrace

    >>> def fuzzdelays(function):
    ...     """Insert random delays into function using `sys.settrace`.
    ...
    ...     WARNING: The use of `sys.settrace` will affect other Python tools like
    ...     `pdb` and `coverage`. Use only in testing scenarios!
    ...
    ...     Decorator to insert random delays into a function to encourage race
    ...     conditions in multi-threaded code.
    ...
    ...     """
    ...     from functools import wraps
    ...     from sys import settrace
    ...     from time import sleep
    ...     from random import random
    ...
    ...     def sleeper(frame, event, arg):
    ...         "Sleep for random period between 0 and 100 milliseconds."
    ...         sleep(random() / 10)
    ...
    ...     try:
    ...         code = function.__code__
    ...     except AttributeError:  # Python 2 compatibility.
    ...         code = function.co_code
    ...
    ...     def tracer(frame, event, arg):
    ...         "Tracer looking for call events with matching function code."
    ...         if event == 'call' and frame.f_code is code:
    ...             sleep(random() / 10)
    ...             return sleeper
    ...
    ...     @wraps(function)
    ...     def wrapper(*args, **kwargs):
    ...         """Wrap function to set tracer before calling function.
    ...
    ...         Tracing is thread-local so set the tracer before every function
    ...         call.
    ...
    ...         """
    ...         settrace(tracer)
    ...         return function(*args, **kwargs)
    ...
    ...     return wrapper

Create a test:

    >>> import diskcache
    >>> import multiprocessing
    >>> import threading

Increment all numbers in a range:

    >>> def task(cache):
    ...     for num in range(100):
    ...         cache.incr(num, retry=True)

Process worker to start many tasks in separate threads.

    >>> def worker():
    ...     # WARNING: Monkey-patch incr method to use fuzzdelays.
    ...     diskcache.FanoutCache.incr = fuzzdelays(diskcache.FanoutCache.incr)
    ...
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

    >>> def main():
    ...     cache = diskcache.FanoutCache('tmp')
    ...     cache.clear()
    ...
    ...     processes = []
    ...
    ...     for num in range(8):
    ...         process = multiprocessing.Process(target=worker)
    ...         processes.append(process)
    ...
    ...     for process in processes:
    ...         process.start()
    ...
    ...     for process in processes:
    ...         process.join()
    ...
    ...     assert sorted(cache) == list(range(100))
    ...     assert all(cache[key] == 64 for key in cache)

Ok, here goes:

    >>> main()

Yaay! It worked.
