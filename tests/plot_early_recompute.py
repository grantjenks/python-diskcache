"""Early Recomputation Measurements

"""

import functools as ft
import multiprocessing.pool
import shutil
import threading
import time

import diskcache as dc


def make_timer(times):
    """Make a decorator which accumulates (start, end) in `times` for function
    calls.

    """
    lock = threading.Lock()

    def timer(func):
        @ft.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            func(*args, **kwargs)
            pair = start, time.time()
            with lock:
                times.append(pair)

        return wrapper

    return timer


def make_worker(times, delay=0.2):
    """Make a worker which accumulates (start, end) in `times` and sleeps for
    `delay` seconds.

    """

    @make_timer(times)
    def worker():
        time.sleep(delay)

    return worker


def make_repeater(func, total=10, delay=0.01):
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


def plot(option, filename, cache_times, worker_times):
    "Plot concurrent workers and latency."
    import matplotlib.pyplot as plt

    fig, (workers, latency) = plt.subplots(2, sharex=True)

    fig.suptitle(option)

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

    workers.set_title('Concurrency')
    workers.set_ylabel('Workers')
    workers.set_ylim(0, 11)
    workers.plot(x_counts, y_counts)

    latency.set_title('Latency')
    latency.set_ylabel('Seconds')
    latency.set_ylim(0, 0.5)
    latency.set_xlabel('Time')
    x_latency = [start - min_x for start, _ in cache_times]
    y_latency = [stop - start for start, stop in cache_times]
    latency.scatter(x_latency, y_latency)

    plt.savefig(filename)


def main():
    shutil.rmtree('/tmp/cache')
    cache = dc.Cache('/tmp/cache')

    count = 10

    cache_times = []
    timer = make_timer(cache_times)

    options = {
        ('No Caching', 'no-caching.png'): [
            timer,
        ],
        ('Traditional Caching', 'traditional-caching.png'): [
            timer,
            cache.memoize(expire=1),
        ],
        ('Synchronized Locking', 'synchronized-locking.png'): [
            timer,
            cache.memoize(expire=0),
            dc.barrier(cache, dc.Lock),
            cache.memoize(expire=1),
        ],
        ('Early Recomputation', 'early-recomputation.png'): [
            timer,
            dc.memoize_stampede(cache, expire=1),
        ],
        ('Early Recomputation (beta=0.5)', 'early-recomputation-05.png'): [
            timer,
            dc.memoize_stampede(cache, expire=1, beta=0.5),
        ],
        ('Early Recomputation (beta=0.3)', 'early-recomputation-03.png'): [
            timer,
            dc.memoize_stampede(cache, expire=1, beta=0.3),
        ],
    }

    for (option, filename), decorators in options.items():
        print('Simulating:', option)
        worker_times = []
        worker = make_worker(worker_times)
        for decorator in reversed(decorators):
            worker = decorator(worker)

        worker()
        repeater = make_repeater(worker)

        with multiprocessing.pool.ThreadPool(count) as pool:
            pool.map(repeater, [worker] * count)

        plot(option, filename, cache_times, worker_times)

        cache.clear()
        cache_times.clear()


if __name__ == '__main__':
    main()
