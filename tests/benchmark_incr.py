"""Benchmark cache.incr method.

"""

from __future__ import print_function

import json
import multiprocessing as mp
import shutil
import time

import diskcache as dc

from .utils import secs

COUNT = int(1e3)
PROCS = 8


def worker(num):
    "Rapidly increment key and time operation."
    time.sleep(0.1)  # Let other workers start.

    cache = dc.Cache('tmp')
    values = []

    for _ in range(COUNT):
        start = time.time()
        cache.incr(b'key')
        end = time.time()
        values.append(end - start)

    with open('output-%s.json' % num, 'w') as writer:
        json.dump(values, writer)


def main():
    "Run workers and print percentile results."
    shutil.rmtree('tmp', ignore_errors=True)

    processes = [
        mp.Process(target=worker, args=(num,)) for num in range(PROCS)
    ]

    for process in processes:
        process.start()

    for process in processes:
        process.join()

    with dc.Cache('tmp') as cache:
        assert cache.get(b'key') == COUNT * PROCS

    for num in range(PROCS):
        values = []
        with open('output-%s.json' % num) as reader:
            values += json.load(reader)

    values.sort()
    p50 = int(len(values) * 0.50) - 1
    p90 = int(len(values) * 0.90) - 1
    p99 = int(len(values) * 0.99) - 1
    p00 = len(values) - 1
    print(['{0:9s}'.format(val) for val in 'p50 p90 p99 max'.split()])
    print([secs(values[pos]) for pos in [p50, p90, p99, p00]])


if __name__ == '__main__':
    main()
