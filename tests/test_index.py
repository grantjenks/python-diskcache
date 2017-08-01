"Test diskcache.persistent.Index."

import functools as ft
import mock
import nose.tools as nt
import pickle
import shutil
import sys

import diskcache as dc


def rmdir(directory):
    try:
        shutil.rmtree(directory)
    except OSError:
        pass


def setup_index(func):
    @ft.wraps(func)
    def wrapper():
        index = dc.Index()
        try:
            func(index)
        except Exception:
            rmdir(index.directory)
            raise

    return wrapper


def test_init():
    directory = '/tmp/diskcache/index'
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


@setup_index
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


@setup_index
def test_get_timeout(index):
    cache = mock.MagicMock()
    cache.__getitem__.side_effect = [dc.Timeout, 0]

    with mock.patch.object(index, '_cache', cache):
        assert index[0] == 0


@setup_index
def test_set_timeout(index):
    cache = mock.MagicMock()
    cache.__setitem__.side_effect = [dc.Timeout, None]

    with mock.patch.object(index, '_cache', cache):
        index[0] = 0


@setup_index
def test_del_timeout(index):
    cache = mock.MagicMock()
    cache.__delitem__.side_effect = [dc.Timeout, None]

    with mock.patch.object(index, '_cache', cache):
        del index[0]


@setup_index
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


@nt.raises(KeyError)
@setup_index
def test_pop_keyerror(index):
    index.pop('a')


@setup_index
def test_pop_timeout(index):
    cache = mock.MagicMock()
    cache.pop.side_effect = [dc.Timeout, 1]

    with mock.patch.object(index, '_cache', cache):
        assert index.pop(0) == 1


@setup_index
def test_popitem(index):
    letters = 'abcde'

    for num, key in enumerate(letters):
        index[key] = num

    assert index.popitem() == ('e', 4)
    assert index.popitem(last=True) == ('d', 3)
    assert index.popitem(last=False) == ('a', 0)
    assert len(index) == 2


@nt.raises(KeyError)
@setup_index
def test_popitem_keyerror(index):
    index.popitem()


@setup_index
def test_popitem_timeout(index):
    cache = mock.MagicMock()
    cache.__reversed__ = mock.Mock()
    cache.__reversed__.side_effect = [iter([0]), iter([0])]
    cache.pop.side_effect = [dc.Timeout, 1]

    with mock.patch.object(index, '_cache', cache):
        value = index.popitem()
        assert value == (0, 1)


@setup_index
def test_iter(index):
    letters = 'abcde'

    for num, key in enumerate(letters):
        index[key] = num

    for num, key in enumerate(index):
        assert index[key] == num


@setup_index
def test_reversed(index):
    letters = 'abcde'

    for num, key in enumerate(letters):
        index[key] = num

    for num, key in enumerate(reversed(index)):
        assert index[key] == (len(letters) - num - 1)


@setup_index
def test_state(index):
    mapping = {'a': 5, 'b': 4, 'c': 3, 'd': 2, 'e': 1}
    index.update(mapping)
    assert index == mapping
    state = pickle.dumps(index)
    values = pickle.loads(state)
    assert values == mapping


@setup_index
def test_push_timeout(index):
    cache = mock.MagicMock()
    cache.push.side_effect = [dc.Timeout, None]

    with mock.patch.object(index, '_cache', cache):
        index.push(0)


@setup_index
def test_pull_timeout(index):
    cache = mock.MagicMock()
    cache.pull.side_effect = [dc.Timeout, None]

    with mock.patch.object(index, '_cache', cache):
        index.pull(0)


@setup_index
def test_clear_timeout(index):
    cache = mock.MagicMock()
    cache.clear.side_effect = [dc.Timeout, None]

    with mock.patch.object(index, '_cache', cache):
        index.clear()


if sys.hexversion < 0x03000000:
    @setup_index
    def test_itervalues_timeout(index):
        cache = mock.MagicMock()
        cache.__iter__.side_effect = [iter([0, 1, 2])]
        cache.__getitem__.side_effect = [KeyError, 1, 2]

        with mock.patch.object(index, '_cache', cache):
            assert list(index.itervalues()) == [1, 2]


    @setup_index
    def test_iteritems_timeout(index):
        cache = mock.MagicMock()
        cache.__iter__.side_effect = [iter([0, 1, 2])]
        cache.__getitem__.side_effect = [KeyError, 1, 2]

        with mock.patch.object(index, '_cache', cache):
            assert list(index.iteritems()) == [(1, 1), (2, 2)]
