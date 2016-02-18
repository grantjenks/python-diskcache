"Stress test diskcache.core.Cache."

from __future__ import print_function

import collections as co
from diskcache import Cache
import json
import multiprocessing as mp
import os
import random
import shutil
import statistics
import sys
import threading
import time

try:
    import Queue
except ImportError:
    import queue as Queue

if sys.hexversion < 0x03000000:
    range = xrange

OPERATIONS = int(1e4)
GET_AVERAGE = 100
KEY_COUNT = 10
DEL_CHANCE = 0.1
WARMUP = 10
EXPIRE = None
THREADS = 1
PROCESSES = 1


def secs(value):
    units = ['s ', 'ms', 'us', 'ns']
    pos = 0

    if value == 0:
        return '  0.000ns'
    else:
        for unit in units:
            if value > 1:
                return '%7.3f' % value + unit
            else:
                value *= 1000


def key_ops():
    key = random.random()

    while True:
        value = random.random()
        yield 'set', key, value
        for _ in range(int(random.expovariate(1.0 / GET_AVERAGE))):
            yield 'get', key, value
        if random.random() < DEL_CHANCE:
            yield 'del', key, None


def all_ops():
    keys = [key_ops() for _ in range(KEY_COUNT)]

    for _ in range(OPERATIONS):
        ops = random.choice(keys)
        yield next(ops)


def worker(queue, kind, args):
    timings = {'get': [], 'set': [], 'del': []}
    cache = kind(*args)

    for index, (action, key, value) in enumerate(iter(queue.get, None)):
        start = time.time()

        if action == 'set':
            cache.set(key, value, expire=EXPIRE)
        elif action == 'get':
            result = cache.get(key)
            if PROCESSES == 1 and THREADS == 1:
                assert result == value
        else:
            assert action == 'del'
            cache.delete(key)

        stop = time.time()

        if index > WARMUP:
            timings[action].append(stop - start)

    queue.put(timings)

    cache.close()


def dispatch(num, kind, args):
    with open('process-%s.json' % num, 'r') as reader:
        process_queue = json.load(reader)

    thread_queues = [Queue.Queue() for _ in range(THREADS)]
    threads = [
        threading.Thread(
            target=worker, args=(thread_queue, kind, args)
        ) for thread_queue in thread_queues
    ]

    for index, triplet in enumerate(process_queue):
        thread_queue = thread_queues[index % THREADS]
        thread_queue.put(triplet)

    for thread_queue in thread_queues:
        thread_queue.put(None)

    start = time.time()

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    stop = time.time()

    timings = {'get': [], 'set': [], 'del': [], 'self': (stop - start)}

    for thread_queue in thread_queues:
        data = thread_queue.get()
        for key in data:
            timings[key].extend(data[key])

    with open('process-%s.json' % num, 'w') as writer:
        json.dump(timings, writer)


def percentile(sequence, percent):
    if not sequence:
        return None

    values = sorted(sequence)

    if percent == 0:
        return values[0]

    pos = int(len(values) * percent) - 1

    return values[pos]


def stress_test():
    shutil.rmtree('temp', ignore_errors=True)

    if PROCESSES == 1:
        # Use threads.
        func = threading.Thread
    else:
        func = mp.Process

    processes = [
        func(target=dispatch, args=(num, Cache, ('temp',)))
        for num in range(PROCESSES)
    ]

    operations = list(all_ops())
    process_queue = [[] for _ in range(PROCESSES)]

    for index, ops in enumerate(operations):
        process_queue[index % PROCESSES].append(ops)

    for num in range(PROCESSES):
        with open('process-%s.json' % num, 'w') as writer:
            json.dump(process_queue[num], writer)

    for process in processes:
        process.start()

    for process in processes:
        process.join()

    timings = {'get': [], 'set': [], 'del': [], 'self': 0.0}

    for num in range(PROCESSES):
        with open('process-%s.json' % num, 'r') as reader:
            data = json.load(reader)
            for key in data:
                timings[key] += data[key]

    for num in range(PROCESSES):
        os.remove('process-%s.json' % num)

    template = '%10s,%10s,%10s,%10s,%10s,%10s,%10s,%10s,%10s'

    print(template % ('op', 'count', 'mean', 'std', 'min', 'p50', 'p90', 'p99', 'max'))

    total = 0

    for action in ['get', 'set', 'del']:
        values = timings[action]
        total += sum(values)

        if len(values) == 0:
            values = (0,)

        print(template % (
            action,
            len(values),
            secs(statistics.mean(values)),
            secs(statistics.pstdev(values)),
            secs(percentile(values, 0.0)),
            secs(percentile(values, 0.5)),
            secs(percentile(values, 0.9)),
            secs(percentile(values, 0.99)),
            secs(percentile(values, 1.0)),
        ))

    print('Total operations time: %.3f seconds' % total)
    print('Total wall clock time: %.3f seconds.' % timings['self'])

    shutil.rmtree('temp', ignore_errors=True)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '-n', '--operations', type=float, default=OPERATIONS,
        help='Number of operations to perform',
    )
    parser.add_argument(
        '-g', '--get-average', type=float, default=GET_AVERAGE,
        help='Expected value of exponential variate used for GET count',
    )
    parser.add_argument(
        '-k', '--key-count', type=float, default=KEY_COUNT,
        help='Number of unique keys'
    )
    parser.add_argument(
        '-d', '--del-chance', type=float, default=DEL_CHANCE,
        help='Likelihood of a key deletion',
    )
    parser.add_argument(
        '-w', '--warmup', type=float, default=WARMUP,
        help='Number of warmup operations before timings',
    )
    parser.add_argument(
        '-e', '--expire', type=float, default=EXPIRE,
        help='Number of seconds before key expires',
    )
    parser.add_argument(
        '-t', '--threads', type=int, default=THREADS,
        help='Number of threads to start in each process',
    )
    parser.add_argument(
        '-p', '--processes', type=int, default=PROCESSES,
        help='Number of processes to start',
    )

    args = parser.parse_args()

    OPERATIONS = int(args.operations)
    GET_AVERAGE = int(args.get_average)
    KEY_COUNT = int(args.key_count)
    DEL_CHANCE = args.del_chance
    WARMUP = int(args.warmup)
    EXPIRE = args.expire
    THREADS = args.threads
    PROCESSES = args.processes

    stress_test()
