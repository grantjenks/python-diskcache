"""Stress test diskcache.persistent.Index."""

import collections as co
import itertools as it
import random

import diskcache as dc

KEYS = 100
OPERATIONS = 25000
SEED = 0

functions = []


def register(function):
    functions.append(function)
    return function


@register
def stress_get(mapping, index):
    key = random.randrange(KEYS)
    assert mapping.get(key, None) == index.get(key, None)


@register
def stress_set(mapping, index):
    key = random.randrange(KEYS)
    value = random.random()
    mapping[key] = value
    index[key] = value


register(stress_set)
register(stress_set)
register(stress_set)


@register
def stress_pop(mapping, index):
    key = random.randrange(KEYS)
    assert mapping.pop(key, None) == index.pop(key, None)


@register
def stress_popitem(mapping, index):
    if len(mapping) == len(index) == 0:
        return
    elif random.randrange(2):
        assert mapping.popitem() == index.popitem()
    else:
        assert mapping.popitem(last=False) == index.popitem(last=False)


@register
def stress_iter(mapping, index):
    iterator = it.islice(zip(mapping, index), 5)
    assert all(alpha == beta for alpha, beta in iterator)


@register
def stress_reversed(mapping, index):
    reversed_mapping = reversed(mapping)
    reversed_index = reversed(index)
    pairs = it.islice(zip(reversed_mapping, reversed_index), 5)
    assert all(alpha == beta for alpha, beta in pairs)


@register
def stress_len(mapping, index):
    assert len(mapping) == len(index)


def stress(mapping, index):
    for count in range(OPERATIONS):
        function = random.choice(functions)
        function(mapping, index)

        if count % 1000 == 0:
            print('\r', len(mapping), ' ' * 7, end='')

    print()


def test():
    random.seed(SEED)
    mapping = co.OrderedDict(enumerate(range(KEYS)))
    index = dc.Index(enumerate(range(KEYS)))
    stress(mapping, index)
    assert mapping == index


if __name__ == '__main__':
    test()
