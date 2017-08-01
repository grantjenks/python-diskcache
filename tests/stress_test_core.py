"Stress test diskcache.core.Cache."

from __future__ import print_function

import collections as co
from diskcache import Cache, UnknownFileWarning, EmptyDirWarning
import multiprocessing as mp
import os
import random
import shutil
import sys
import threading
import time
import warnings

try:
    import Queue
except ImportError:
    import queue as Queue

if sys.hexversion < 0x03000000:
    range = xrange
    import cPickle as pickle
else:
    import pickle

from .utils import display

OPERATIONS = int(1e4)
GET_AVERAGE = 100
KEY_COUNT = 10
DEL_CHANCE = 0.1
WARMUP = 10
EXPIRE = None


def make_keys():
    def make_int():
        return random.randrange(int(1e9))

    def make_long():
        value = random.randrange(int(1e9))
        return value << 64

    def make_unicode():
        word_size = random.randint(1, 26)
        word = u''.join(random.sample(u'abcdefghijklmnopqrstuvwxyz', word_size))
        size = random.randint(1, int(200 / 13))
        return word * size

    def make_bytes():
        word_size = random.randint(1, 26)
        word = u''.join(random.sample(u'abcdefghijklmnopqrstuvwxyz', word_size)).encode('utf-8')
        size = random.randint(1, int(200 / 13))
        return word * size

    def make_float():
        return random.random()

    def make_object():
        return (make_float(),) * random.randint(1, 20)

    funcs = [make_int, make_long, make_unicode, make_bytes, make_float, make_object]

    while True:
        func = random.choice(funcs)
        yield func()


def make_vals():
    def make_int():
        return random.randrange(int(1e9))

    def make_long():
        value = random.randrange(int(1e9))
        return value << 64

    def make_unicode():
        word_size = random.randint(1, 26)
        word = u''.join(random.sample(u'abcdefghijklmnopqrstuvwxyz', word_size))
        size = random.randint(1, int(2 ** 16 / 13))
        return word * size

    def make_bytes():
        word_size = random.randint(1, 26)
        word = u''.join(random.sample(u'abcdefghijklmnopqrstuvwxyz', word_size)).encode('utf-8')
        size = random.randint(1, int(2 ** 16 / 13))
        return word * size

    def make_float():
        return random.random()

    def make_object():
        return [make_float()] * random.randint(1, int(2e3))

    funcs = [make_int, make_long, make_unicode, make_bytes, make_float, make_object]

    while True:
        func = random.choice(funcs)
        yield func()


def key_ops():
    keys = make_keys()
    vals = make_vals()

    key = next(keys)

    while True:
        value = next(vals)
        yield 'set', key, value
        for _ in range(int(random.expovariate(1.0 / GET_AVERAGE))):
            yield 'get', key, value
        if random.random() < DEL_CHANCE:
            yield 'delete', key, None


def all_ops():
    keys = [key_ops() for _ in range(KEY_COUNT)]

    for _ in range(OPERATIONS):
        ops = random.choice(keys)
        yield next(ops)


def worker(queue, eviction_policy, processes, threads):
    timings = {'get': [], 'set': [], 'delete': []}
    cache = Cache('tmp', eviction_policy=eviction_policy)

    for index, (action, key, value) in enumerate(iter(queue.get, None)):
        start = time.time()

        if action == 'set':
            cache.set(key, value, expire=EXPIRE)
        elif action == 'get':
            result = cache.get(key)
        else:
            assert action == 'delete'
            cache.delete(key)

        stop = time.time()

        if action == 'get' and processes == 1 and threads == 1 and EXPIRE is None:
            assert result == value

        if index > WARMUP:
            timings[action].append(stop - start)

    queue.put(timings)

    cache.close()


def dispatch(num, eviction_policy, processes, threads):
    with open('input-%s.pkl' % num, 'rb') as reader:
        process_queue = pickle.load(reader)

    thread_queues = [Queue.Queue() for _ in range(threads)]
    subthreads = [
        threading.Thread(
            target=worker, args=(thread_queue, eviction_policy, processes, threads)
        ) for thread_queue in thread_queues
    ]

    for index, triplet in enumerate(process_queue):
        thread_queue = thread_queues[index % threads]
        thread_queue.put(triplet)

    for thread_queue in thread_queues:
        thread_queue.put(None)

    start = time.time()

    for thread in subthreads:
        thread.start()

    for thread in subthreads:
        thread.join()

    stop = time.time()

    timings = {'get': [], 'set': [], 'delete': [], 'self': (stop - start)}

    for thread_queue in thread_queues:
        data = thread_queue.get()
        for key in data:
            timings[key].extend(data[key])

    with open('output-%s.pkl' % num, 'wb') as writer:
        pickle.dump(timings, writer, protocol=2)


def percentile(sequence, percent):
    if not sequence:
        return None

    values = sorted(sequence)

    if percent == 0:
        return values[0]

    pos = int(len(values) * percent) - 1

    return values[pos]


def stress_test(create=True, delete=True,
                eviction_policy=u'least-recently-stored',
                processes=1, threads=1):
    shutil.rmtree('tmp', ignore_errors=True)

    if processes == 1:
        # Use threads.
        func = threading.Thread
    else:
        func = mp.Process

    subprocs = [
        func(target=dispatch, args=(num, eviction_policy, processes, threads))
        for num in range(processes)
    ]

    if create:
        operations = list(all_ops())
        process_queue = [[] for _ in range(processes)]

        for index, ops in enumerate(operations):
            process_queue[index % processes].append(ops)

        for num in range(processes):
            with open('input-%s.pkl' % num, 'wb') as writer:
                pickle.dump(process_queue[num], writer, protocol=2)

    for process in subprocs:
        process.start()

    for process in subprocs:
        process.join()

    with Cache('tmp') as cache:
        warnings.simplefilter('error')
        warnings.simplefilter('ignore', category=UnknownFileWarning)
        warnings.simplefilter('ignore', category=EmptyDirWarning)
        cache.check()

    timings = {'get': [], 'set': [], 'delete': [], 'self': 0.0}

    for num in range(processes):
        with open('output-%s.pkl' % num, 'rb') as reader:
            data = pickle.load(reader)
            for key in data:
                timings[key] += data[key]

    if delete:
        for num in range(processes):
            os.remove('input-%s.pkl' % num)
            os.remove('output-%s.pkl' % num)

    display(eviction_policy, timings)

    shutil.rmtree('tmp', ignore_errors=True)


def stress_test_lru():
    "Stress test least-recently-used eviction policy."
    stress_test(eviction_policy=u'least-recently-used')


def stress_test_lfu():
    "Stress test least-frequently-used eviction policy."
    stress_test(eviction_policy=u'least-frequently-used')


def stress_test_none():
    "Stress test 'none' eviction policy."
    stress_test(eviction_policy=u'none')


def stress_test_mp():
    "Stress test multiple threads and processes."
    stress_test(processes=4, threads=4)


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
        '-t', '--threads', type=int, default=1,
        help='Number of threads to start in each process',
    )
    parser.add_argument(
        '-p', '--processes', type=int, default=1,
        help='Number of processes to start',
    )
    parser.add_argument(
        '-s', '--seed', type=int, default=0,
        help='Random seed',
    )
    parser.add_argument(
        '--no-create', action='store_false', dest='create',
        help='Do not create operations data',
    )
    parser.add_argument(
        '--no-delete', action='store_false', dest='delete',
        help='Do not delete operations data',
    )
    parser.add_argument(
        '-v', '--eviction-policy', type=unicode,
        default=u'least-recently-stored',
    )

    args = parser.parse_args()

    OPERATIONS = int(args.operations)
    GET_AVERAGE = int(args.get_average)
    KEY_COUNT = int(args.key_count)
    DEL_CHANCE = args.del_chance
    WARMUP = int(args.warmup)
    EXPIRE = args.expire

    random.seed(args.seed)

    start = time.time()
    stress_test(
        create=args.create,
        delete=args.delete,
        eviction_policy=args.eviction_policy,
        processes=args.processes,
        threads=args.threads,
    )
    end = time.time()
    print('Total wall clock time: %.3f seconds' % (end - start))
