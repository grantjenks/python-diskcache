"""Stress test diskcache.persistent.Index."""

import itertools as it
import multiprocessing as mp
import os
import random
import time

import diskcache as dc

KEYS = 100
OPERATIONS = 10000
SEED = 0

functions = []


def register(function):
    functions.append(function)
    return function


@register
def stress_get(index):
    key = random.randrange(KEYS)
    index.get(key, None)


@register
def stress_set(index):
    key = random.randrange(KEYS)
    value = random.random()
    index[key] = value


register(stress_set)
register(stress_set)
register(stress_set)


@register
def stress_del(index):
    key = random.randrange(KEYS)

    try:
        del index[key]
    except KeyError:
        pass


@register
def stress_pop(index):
    key = random.randrange(KEYS)
    index.pop(key, None)


@register
def stress_popitem(index):
    try:
        if random.randrange(2):
            index.popitem()
        else:
            index.popitem(last=False)
    except KeyError:
        pass


@register
def stress_iter(index):
    iterator = it.islice(index, 5)

    for key in iterator:
        pass


@register
def stress_reversed(index):
    iterator = it.islice(reversed(index), 5)

    for key in iterator:
        pass


@register
def stress_len(index):
    len(index)


def stress(seed, index):
    random.seed(seed)
    for count in range(OPERATIONS):
        function = random.choice(functions)
        function(index)


def test(status=False):
    if os.environ.get('TRAVIS') == 'true':
        return

    if os.environ.get('APPVEYOR') == 'True':
        return

    random.seed(SEED)
    index = dc.Index(enumerate(range(KEYS)))
    processes = []

    for count in range(8):
        process = mp.Process(target=stress, args=(SEED + count, index))
        process.start()
        processes.append(process)

    for value in it.count():
        time.sleep(1)

        if status:
            print('\r', value, 's', len(index), 'keys', ' ' * 20, end='')

        if all(not process.is_alive() for process in processes):
            break

    if status:
        print('')

    assert all(process.exitcode == 0 for process in processes)


if __name__ == '__main__':
    test(status=True)
