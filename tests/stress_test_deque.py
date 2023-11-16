"""Stress test diskcache.persistent.Deque."""

import collections as co
import functools as ft
import random

import diskcache as dc

OPERATIONS = 1000
SEED = 0
SIZE = 10

functions = []


def register(function):
    functions.append(function)
    return function


def lencheck(function):
    @ft.wraps(function)
    def wrapper(sequence, deque):
        assert len(sequence) == len(deque)

        if not deque:
            return

        function(sequence, deque)

    return wrapper


@register
@lencheck
def stress_get(sequence, deque):
    index = random.randrange(len(sequence))
    assert sequence[index] == deque[index]


@register
@lencheck
def stress_set(sequence, deque):
    index = random.randrange(len(sequence))
    value = random.random()
    sequence[index] = value
    deque[index] = value


@register
@lencheck
def stress_del(sequence, deque):
    index = random.randrange(len(sequence))
    del sequence[index]
    del deque[index]


@register
def stress_iadd(sequence, deque):
    values = [random.random() for _ in range(5)]
    sequence += values
    deque += values


@register
def stress_iter(sequence, deque):
    assert all(alpha == beta for alpha, beta in zip(sequence, deque))


@register
def stress_reversed(sequence, deque):
    reversed_sequence = reversed(sequence)
    reversed_deque = reversed(deque)
    pairs = zip(reversed_sequence, reversed_deque)
    assert all(alpha == beta for alpha, beta in pairs)


@register
def stress_append(sequence, deque):
    value = random.random()
    sequence.append(value)
    deque.append(value)


@register
def stress_appendleft(sequence, deque):
    value = random.random()
    sequence.appendleft(value)
    deque.appendleft(value)


@register
@lencheck
def stress_pop(sequence, deque):
    assert sequence.pop() == deque.pop()


register(stress_pop)
register(stress_pop)


@register
@lencheck
def stress_popleft(sequence, deque):
    assert sequence.popleft() == deque.popleft()


register(stress_popleft)
register(stress_popleft)


@register
def stress_reverse(sequence, deque):
    sequence.reverse()
    deque.reverse()
    assert all(alpha == beta for alpha, beta in zip(sequence, deque))


@register
@lencheck
def stress_rotate(sequence, deque):
    assert len(sequence) == len(deque)
    steps = random.randrange(len(deque))
    sequence.rotate(steps)
    deque.rotate(steps)
    assert all(alpha == beta for alpha, beta in zip(sequence, deque))


def stress(sequence, deque):
    for count in range(OPERATIONS):
        function = random.choice(functions)
        function(sequence, deque)

        if count % 100 == 0:
            print('\r', len(sequence), ' ' * 7, end='')

    print()


def test():
    random.seed(SEED)
    sequence = co.deque(range(SIZE))
    deque = dc.Deque(range(SIZE))
    stress(sequence, deque)
    assert all(alpha == beta for alpha, beta in zip(sequence, deque))


if __name__ == '__main__':
    test()
