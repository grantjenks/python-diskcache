"""Early Recomputation Measurements

TODO

* Publish graphs:
  1. Cache stampede (single memo decorator).
  2. Double-checked locking (memo, barrier, memo).
  3. Early recomputation (memo with early recomputation).
  4. Advanced usage: adjust "Beta" parameter.

"""

import concurrent.futures
import diskcache as dc
import functools
import matplotlib.pyplot as plt
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

    max_x = max(start for start, _ in cache_times)
    for step in frange(counts[-1][0], max_x):
        pair = (step, counts[-1][1])
        counts.append(pair)

    x_counts = [x for x, y in counts]
    y_counts = [y for x, y in counts]

    workers.set_title('Concurrent Workers')
    workers.set_ylabel('Workers')
    workers.plot(x_counts, y_counts)

    latency.set_title('Latency')
    latency.set_ylabel('Seconds')
    latency.set_xlabel('Time')
    x_latency = [start for start, _ in cache_times]
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
    worker_times = []

    worker = make_worker(worker_times)
    decorators = [
        make_timer(cache_times),
        cache.memoize(expire=10, early_recompute=1.5),
        # dc.barrier(cache, dc.Lock),
        # cache.memoize(expire=10),
    ]
    for decorator in reversed(decorators):
        worker = decorator(worker)

    repeater = make_repeater(worker)

    with concurrent.futures.ThreadPoolExecutor(count) as executor:
        executor.map(repeater, [worker] * count)

    plot(cache_times, worker_times)
