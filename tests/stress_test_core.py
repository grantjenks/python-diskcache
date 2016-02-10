"Stress test diskcache.core.Cache."

from __future__ import print_function

import collections as co
from diskcache import Cache
import faulthandler
import json
import multiprocessing as mp
import multiprocessing.pool as mpool
import threading
import Queue
import random
import shutil
import statistics
import sys
import threading
import time

faulthandler.enable()

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


def dispatch(num, process_queue, kind, args):
    thread_queues = [Queue.Queue() for _ in range(THREADS)]
    threads = [
        threading.Thread(
            target=worker, args=(thread_queue, kind, args)
        ) for thread_queue in thread_queues
    ]

    for thread in threads:
        thread.start()

    for index, triplet in enumerate(iter(process_queue.get, None)):
        thread_queue = thread_queues[index % THREADS]
        thread_queue.put(triplet)

    for thread_queue in thread_queues:
        thread_queue.put(None)

    for thread in threads:
        thread.join()

    timings = {'get': [], 'set': [], 'del': []}

    for thread_queue in thread_queues:
        data = thread_queue.get()
        for key in data:
            timings[key].extend(data[key])

    with open('process-%s.json' % num, 'w') as writer:
        json.dump(timings, writer)


def stress_test():
    shutil.rmtree('temp', ignore_errors=True)

    process_queues = [mp.Queue() for _ in range(PROCESSES)]
    processes = [
        mp.Process(target=dispatch, args=(num, process_queue, Cache, ('temp',)))
        for num, process_queue in enumerate(process_queues)
    ]

    for process in processes:
        process.start()

    for index, operation in enumerate(all_ops()):
        process_queue = process_queues[index % PROCESSES]
        process_queue.put(operation)

    for process_queue in process_queues:
        process_queue.put(None)

    for process in processes:
        process.join()

    timings = {'get': [], 'set': [], 'del': []}

    for num in range(len(process_queues)):
        with open('process-%s.json' % num, 'r') as reader:
            data = json.load(reader)
            for key in data:
                timings[key].extend(data[key])

    template = '%10s,%10s,%10s,%10s,%10s,%10s,%10s'

    print(template % ('op', 'len', 'min', 'max', 'std', 'mean', 'median'))

    template = '%10s,%10d' + ',%10s' * 5

    total = 0

    for action in ['get', 'set', 'del']:
        values = timings[action]
        total += sum(values)

        if len(values) == 0:
            values = (0,)

        print(template % (
            action,
            len(values),
            secs(min(values)),
            secs(max(values)),
            secs(statistics.pstdev(values)),
            secs(statistics.mean(values)),
            secs(statistics.median_high(values)),
        ))

    print('Total operations time: %.3f seconds' % total)

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
        '-g', '--get-average', type=int, default=GET_AVERAGE,
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
        '-w', '--warmup', type=int, default=WARMUP,
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
    GET_AVERAGE = args.get_average
    KEY_COUNT = int(args.key_count)
    DEL_CHANCE = args.del_chance
    WARMUP = args.warmup
    EXPIRE = args.expire
    THREADS = args.threads
    PROCESSES = args.processes

    start = time.time()
    stress_test()
    stop = time.time()

    print('Total wall clock time: %.3f seconds.' % (stop - start))
