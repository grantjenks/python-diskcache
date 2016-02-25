"Benchmark diskcache.Core."

from __future__ import print_function

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

from utils import percentile, secs

PROCS = 1
RANGE = 100
LIMIT = int(1e5)
WARMUP = 100

caches = []

import diskcache

caches.append((
    'diskcache.Cache',
    diskcache.Cache,
    ('tmp',),
    {},
))

class Cache(object):
    def __init__(self, directory, count=1):
        self._count = count
        self._caches = [
            diskcache.Cache('%s/%03d' % (directory, num))
            for num in range(self._count)
        ]

    def set(self, key, value):
        temp = hash(key)
        index = temp % self._count
        self._caches[index].set(key, value)

    def get(self, key):
        temp = hash(key)
        index = temp % self._count
        return self._caches[index].get(key)

    def delete(self, key):
        temp = hash(key)
        index = temp % self._count
        self._caches[index].delete(key)

    def close(self):
        for cache in self._caches:
            cache.close()


caches.append(('Cache(count=1)', Cache, ('tmp',), {'count': 1},))
caches.append(('Cache(count=11)', Cache, ('tmp',), {'count': 11},))
caches.append(('Cache(count=23)', Cache, ('tmp',), {'count': 23},))
caches.append(('Cache(count=101)', Cache, ('tmp',), {'count': 101},))


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

    timings = {'get': [], 'set': [], 'del': []}

    for count in range(LIMIT):
        key = str(random.randrange(RANGE)).encode('utf-8')
        value = str(count).encode('utf-8') * random.randrange(1, 100)
        choice = random.random()

        if choice < 0.900:
            start = time.time()
            obj.get(key)
            end = time.time()
            action = 'get'
        elif choice < 0.990:
            start = time.time()
            obj.set(key, value)
            end = time.time()
            action = 'set'
        else:
            start = time.time()
            obj.delete(key)
            end = time.time()
            action = 'del'

        if count > WARMUP:
            timings[action].append(end - start)

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

        timings = {'get': [], 'set': [], 'del': []}

        for num in range(PROCS):
            filename = 'output-%d.pkl' % num

            with open(filename, 'rb') as reader:
                output = pickle.load(reader)

            for key in output:
                timings[key].extend(output[key])

            os.remove(filename)

        template = '%10s,%10s,%10s,%10s,%10s,%10s,%10s,%10s'

        print('Timings results for', name)

        print(template % ('op', 'count', 'min', 'p50', 'p90', 'p99', 'p999', 'max'))

        total = 0

        for action in ['get', 'set', 'del']:
            values = timings[action]
            total += sum(values)

            if len(values) == 0:
                values = (0,)

            print(template % (
                action,
                len(values),
                secs(percentile(values, 0.0)),
                secs(percentile(values, 0.5)),
                secs(percentile(values, 0.9)),
                secs(percentile(values, 0.99)),
                secs(percentile(values, 0.999)),
                secs(percentile(values, 1.0)),
            ))

        print('Total operations time: %.3f seconds' % total)
        print()
        time.sleep(1)


if __name__ == '__main__':
    dispatch()
