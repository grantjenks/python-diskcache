"""Stress test diskcache.persistent.Deque."""

from __future__ import print_function

import functools as ft
import multiprocessing as mp
import itertools as it
import random
import time

import diskcache as dc

OPERATIONS = 1000
SEED = 0
SIZE = 10

functions = []


def register(function):
    functions.append(function)
    return function


@register
def stress_get(deque):
    index = random.randrange(max(1, len(deque)))

    try:
        deque[index]
    except IndexError:
        pass


@register
def stress_set(deque):
    index = random.randrange(max(1, len(deque)))
    value = random.random()

    try:
        deque[index] = value
    except IndexError:
        pass


@register
def stress_del(deque):
    index = random.randrange(max(1, len(deque)))

    try:
        del deque[index]
    except IndexError:
        pass


@register
def stress_iadd(deque):
    values = [random.random() for _ in range(5)]
    deque += values


@register
def stress_append(deque):
    value = random.random()
    deque.append(value)


@register
def stress_appendleft(deque):
    value = random.random()
    deque.appendleft(value)


@register
def stress_pop(deque):
    try:
        deque.pop()
    except IndexError:
        pass


register(stress_pop)
register(stress_pop)
register(stress_pop)


@register
def stress_popleft(deque):
    try:
        deque.popleft()
    except IndexError:
        pass


register(stress_popleft)
register(stress_popleft)
register(stress_popleft)


@register
def stress_reverse(deque):
    deque.reverse()


@register
def stress_rotate(deque):
    steps = random.randrange(max(1, len(deque)))
    deque.rotate(steps)


def stress(seed, deque):
    random.seed(seed)
    for count in range(OPERATIONS):
        function = random.choice(functions)
        function(deque)


def test(status=False):
    random.seed(SEED)
    deque = dc.Deque(range(SIZE))
    processes = []

    for count in range(8):
        process = mp.Process(target=stress, args=(SEED + count, deque))
        process.start()
        processes.append(process)

    for value in it.count():
        time.sleep(1)

        if status:
            print('\r', value, 's', len(deque), 'items', ' ' * 20, end='')

        if all(not process.is_alive() for process in processes):
            break

    if status:
        print('')

    assert all(process.exitcode == 0 for process in processes)


if __name__ == '__main__':
    test(status=True)
