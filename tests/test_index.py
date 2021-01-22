"Test diskcache.persistent.Index."

import pickle
import shutil
import tempfile

import pytest

import diskcache as dc


def rmdir(directory):
    try:
        shutil.rmtree(directory)
    except OSError:
        pass


@pytest.fixture
def index():
    index = dc.Index()
    yield index
    rmdir(index.directory)


def test_init():
    directory = tempfile.mkdtemp()
    mapping = {'a': 5, 'b': 4, 'c': 3, 'd': 2, 'e': 1}
    index = dc.Index(None, mapping)

    assert index == mapping

    rmdir(index.directory)
    del index

    rmdir(directory)
    index = dc.Index(directory, mapping)

    assert index.directory == directory
    assert index == mapping

    other = dc.Index(directory)

    assert other == index

    del index
    del other
    rmdir(directory)
    index = dc.Index(directory, mapping.items())

    assert index == mapping

    del index
    rmdir(directory)
    index = dc.Index(directory, a=5, b=4, c=3, d=2, e=1)

    assert index == mapping


def test_getsetdel(index):
    letters = 'abcde'
    assert len(index) == 0

    for num, key in enumerate(letters):
        index[key] = num

    for num, key in enumerate(letters):
        assert index[key] == num

    for key in letters:
        del index[key]

    assert len(index) == 0


def test_pop(index):
    letters = 'abcde'
    assert len(index) == 0

    for num, key in enumerate(letters):
        index[key] = num

    assert index.pop('a') == 0
    assert index.pop('c') == 2
    assert index.pop('e') == 4
    assert index.pop('b') == 1
    assert index.pop('d') == 3
    assert len(index) == 0


def test_pop_keyerror(index):
    with pytest.raises(KeyError):
        index.pop('a')


def test_popitem(index):
    letters = 'abcde'

    for num, key in enumerate(letters):
        index[key] = num

    assert index.popitem() == ('e', 4)
    assert index.popitem(last=True) == ('d', 3)
    assert index.popitem(last=False) == ('a', 0)
    assert len(index) == 2


def test_popitem_keyerror(index):
    with pytest.raises(KeyError):
        index.popitem()


def test_setdefault(index):
    assert index.setdefault('a', 0) == 0
    assert index.setdefault('a', 1) == 0


def test_iter(index):
    letters = 'abcde'

    for num, key in enumerate(letters):
        index[key] = num

    for num, key in enumerate(index):
        assert index[key] == num


def test_reversed(index):
    letters = 'abcde'

    for num, key in enumerate(letters):
        index[key] = num

    for num, key in enumerate(reversed(index)):
        assert index[key] == (len(letters) - num - 1)


def test_state(index):
    mapping = {'a': 5, 'b': 4, 'c': 3, 'd': 2, 'e': 1}
    index.update(mapping)
    assert index == mapping
    state = pickle.dumps(index)
    values = pickle.loads(state)
    assert values == mapping


def test_memoize(index):
    count = 1000

    def fibiter(num):
        alpha, beta = 0, 1

        for _ in range(num):
            alpha, beta = beta, alpha + beta

        return alpha

    @index.memoize()
    def fibrec(num):
        if num == 0:
            return 0
        elif num == 1:
            return 1
        else:
            return fibrec(num - 1) + fibrec(num - 2)

    index._cache.stats(enable=True)

    for value in range(count):
        assert fibrec(value) == fibiter(value)

    hits1, misses1 = index._cache.stats()

    for value in range(count):
        assert fibrec(value) == fibiter(value)

    hits2, misses2 = index._cache.stats()

    assert hits2 == (hits1 + count)
    assert misses2 == misses1


def test_repr(index):
    assert repr(index).startswith('Index(')
