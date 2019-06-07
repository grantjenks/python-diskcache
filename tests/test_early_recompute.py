"""Early Recomputation Measurements

TODO

* Publish graphs:
  1. Cache stampede (single memo decorator).
  2. Double-checked locking (memo, barrier, memo).
  3. Early recomputation (memo with early recomputation).
  4. Advanced usage: adjust "Beta" parameter.

"""

import diskcache as dc
import functools
import multiprocessing.pool
import shutil
import threading
import time


def make_timer(times):
    """Make a decorator which accumulates (start, end) in `times` for function
    calls.

    """
    lock = threading.Lock()
    def timer(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            pair = start, time.time()
            with lock:
                times.append(pair)
        return wrapper
    return timer


def make_worker(times, delay=1):
    """Make a worker which accumulates (start, end) in `times` and sleeps for
    `delay` seconds.

    """
    @make_timer(times)
    def worker():
        time.sleep(delay)
    return worker


def make_repeater(func, total=60, delay=0.01):
    """Make a repeater which calls `func` and sleeps for `delay` seconds
    repeatedly until `total` seconds have elapsed.

    """
    def repeat(num):
        start = time.time()
        while time.time() - start < total:
            func()
            time.sleep(delay)
    return repeat


def frange(start, stop, step=1e-3):
    "Generator for floating point values from `start` to `stop` by `step`."
    while start < stop:
        yield start
        start += step


def plot(cache_times, worker_times):
    "Plot concurrent workers and latency."
    # TODO: Update x-axis to normalize to 0
    import matplotlib.pyplot as plt
    fig, (workers, latency) = plt.subplots(2, sharex=True)

    changes = [(start, 1) for start, _ in worker_times]
    changes.extend((stop, -1) for _, stop in worker_times)
    changes.sort()
    start = (changes[0][0] - 1e-6, 0)
    counts = [start]

    for mark, diff in changes:
        # Re-sample between previous and current data point for a nicer-looking
        # line plot.

        for step in frange(counts[-1][0], mark):
            pair = (step, counts[-1][1])
            counts.append(pair)

        pair = (mark, counts[-1][1] + diff)
        counts.append(pair)

    min_x = min(start for start, _ in cache_times)
    max_x = max(start for start, _ in cache_times)
    for step in frange(counts[-1][0], max_x):
        pair = (step, counts[-1][1])
        counts.append(pair)

    x_counts = [x - min_x for x, y in counts]
    y_counts = [y for x, y in counts]

    workers.set_title('Concurrent Workers')
    workers.set_ylabel('Workers')
    workers.plot(x_counts, y_counts)

    latency.set_title('Latency')
    latency.set_ylabel('Seconds')
    latency.set_xlabel('Time')
    x_latency = [start - min_x for start, _ in cache_times]
    y_latency = [stop - start for start, stop in cache_times]
    latency.scatter(x_latency, y_latency)

    plt.show()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()

    shutil.rmtree('/tmp/cache', ignore_errors=True)
    cache = dc.Cache('/tmp/cache')

    count = 16

    cache_times = []
    timer = make_timer(cache_times)

    decorators = [
        timer,

        # Option 0: No Caching

        # Option 1: Traditional Caching
        # cache.memoize(expire=10),

        # Option 2: Synchronized Locking
        # cache.memoize(expire=0),
        # dc.barrier(cache, dc.Lock),
        # cache.memoize(expire=10),

        # Option 3: Early Recomputation
        # cache.memoize(expire=10, early_recompute=True),

        # Option 4: Early Recomputation Tuning
        # cache.memoize(expire=10, early_recompute=1.5),  # =0.5),

        # Option 5: Background Early Recomputation
        # cache.memoize(expire=10, early_recompute=True, background='threading'),
        # TODO: background parameter? or early_recompute='background'
    ]

    worker_times = []
    worker = make_worker(worker_times)
    for decorator in reversed(decorators):
        worker = decorator(worker)

    repeater = make_repeater(worker)

<<<<<<< HEAD
    with multiprocessing.pool.ThreadPool() as pool:
        pool.map(repeater, [worker] * count)
=======
    import multiprocessing.pool as mp
    with mp.ThreadPool(count) as pool:
        list(pool.map(repeater, [worker] * count))

    # with concurrent.futures.ThreadPoolExecutor(count) as executor:
    #     executor.map(repeater, [worker] * count)
>>>>>>> Add changes for threaded recomputation

    plot(cache_times, worker_times)
