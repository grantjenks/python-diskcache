"Benchmark diskcache.Core."

from __future__ import print_function

import collections as co
import multiprocessing as mp
import os
import random
import shutil
import sys
import time
import warnings

if sys.hexversion < 0x03000000:
    range = xrange
    import cPickle as pickle
else:
    import pickle

from utils import display

PROCS = 8
OPS = int(1e5)
RANGE = 100
WARMUP = int(1e3)

caches = []


###############################################################################
# Disk Cache Benchmarks
###############################################################################

import diskcache

caches.append(('diskcache.Cache', diskcache.Cache, ('tmp',), {},))
caches.append((
    'diskcache.FanoutCache(shards=4, timeout=1.0)',
    diskcache.FanoutCache,
    ('tmp',),
    {'shards': 4, 'timeout': 1.0}
))
caches.append((
    'diskcache.FanoutCache(shards=8, timeout=0.025)',
    diskcache.FanoutCache,
    ('tmp',),
    {'shards': 8, 'timeout': 0.025}
))


###############################################################################
# PyLibMC Benchmarks
###############################################################################

try:
    import pylibmc

    caches.append((
        'pylibmc.Client',
        pylibmc.Client,
        (['127.0.0.1'],),
        {'binary': True, 'behaviors': {'tcp_nodelay': True, 'ketama': True}},
    ))
except ImportError:
    warnings.warn('skipping pylibmc')


###############################################################################
# Redis Benchmarks
###############################################################################

try:
    import redis

    caches.append((
        'redis.StrictRedis',
        redis.StrictRedis,
        (),
        {'host': 'localhost', 'port': 6379, 'db': 0},
    ))
except ImportError:
    warnings.warn('skipping redis')


def worker(num, kind, args, kwargs):
    random.seed(num)

    time.sleep(0.01) # Let other processes start.

    obj = kind(*args, **kwargs)

    timings = co.defaultdict(list)

    for count in range(OPS):
        key = str(random.randrange(RANGE)).encode('utf-8')
        value = str(count).encode('utf-8') * random.randrange(1, 100)
        choice = random.random()

        if choice < 0.900:
            start = time.time()
            result = obj.get(key)
            end = time.time()
            miss = result is None
            action = 'get'
        elif choice < 0.990:
            start = time.time()
            result = obj.set(key, value)
            end = time.time()
            miss = result == False
            action = 'set'
        else:
            start = time.time()
            result = obj.delete(key)
            end = time.time()
            miss = result == False
            action = 'delete'

        if count > WARMUP:
            delta = end - start
            timings[action].append(delta)
            if miss:
                timings[action + '-miss'].append(delta)

    with open('output-%d.pkl' % num, 'wb') as writer:
        pickle.dump(timings, writer, protocol=pickle.HIGHEST_PROTOCOL)


def dispatch():
    for name, kind, args, kwargs in caches:
        shutil.rmtree('tmp', ignore_errors=True)

        obj = kind(*args, **kwargs)

        for key in range(RANGE):
            key = str(key).encode('utf-8')
            obj.set(key, key)

        try:
            obj.close()
        except:
            pass

        processes = [
            mp.Process(target=worker, args=(value, kind, args, kwargs))
            for value in range(PROCS)
        ]

        for process in processes:
            process.start()

        for process in processes:
            process.join()

        timings = co.defaultdict(list)

        for num in range(PROCS):
            filename = 'output-%d.pkl' % num

            with open(filename, 'rb') as reader:
                output = pickle.load(reader)

            for key in output:
                timings[key].extend(output[key])

            os.remove(filename)

        display(name, timings)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        '-p', '--processes', type=int, default=PROCS,
        help='Number of processes to start',
    )
    parser.add_argument(
        '-n', '--operations', type=float, default=OPS,
        help='Number of operations to perform',
    )
    parser.add_argument(
        '-r', '--range', type=int, default=RANGE,
        help='Range of keys',
    )
    parser.add_argument(
        '-w', '--warmup', type=float, default=WARMUP,
        help='Number of warmup operations before timings',
    )

    args = parser.parse_args()

    PROCS = int(args.processes)
    OPS = int(args.operations)
    RANGE = int(args.range)
    WARMUP = int(args.warmup)

    dispatch()
