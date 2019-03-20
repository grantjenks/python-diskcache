"Test diskcache.persistent.Deque."

import functools as ft
import mock
import pickle
import pytest
import shutil

import diskcache as dc
from diskcache.core import ENOVAL


def rmdir(directory):
    try:
        shutil.rmtree(directory)
    except OSError:
        pass


@pytest.fixture
def deque():
    deque = dc.Deque()
    try:
        yield deque
    except Exception:
        rmdir(deque.directory)
        raise


def test_init():
    directory = '/tmp/diskcache/deque'
    sequence = list('abcde')
    deque = dc.Deque(sequence, None)

    assert deque == sequence

    rmdir(deque.directory)
    del deque

    rmdir(directory)
    deque = dc.Deque(sequence, directory)

    assert deque.directory == directory
    assert deque == sequence

    other = dc.Deque(directory=directory)

    assert other == deque

    del deque
    del other
    rmdir(directory)


def test_getsetdel(deque):
    sequence = list('abcde')
    assert len(deque) == 0

    for key in sequence:
        deque.append(key)

    assert len(deque) == len(sequence)

    for index in range(len(sequence)):
        assert deque[index] == sequence[index]

    for index in range(len(sequence)):
        deque[index] = index

    for index in range(len(sequence)):
        assert deque[index] == index

    for index in range(len(sequence)):
        if index % 2:
            del deque[-1]
        else:
            del deque[0]

    assert len(deque) == 0


def test_reversed(deque):
    sequence = list('abcde')
    deque += sequence
    assert list(reversed(deque)) == list(reversed(sequence))


def test_state(deque):
    sequence = list('abcde')
    deque.extend(sequence)
    assert deque == sequence
    state = pickle.dumps(deque)
    values = pickle.loads(state)
    assert values == sequence


def test_compare(deque):
    assert not (deque == {})
    assert not (deque == [0])
    assert deque != [1]
    deque.append(0)
    assert deque <= [0]
    assert deque <= [1]


def test_indexerror_negative(deque):
    with pytest.raises(IndexError):
        deque[-1]


def test_indexerror(deque):
    with pytest.raises(IndexError):
        deque[0]


def test_indexerror_islice(deque):
    islice = mock.Mock(side_effect=StopIteration)

    deque.append(0)

    with mock.patch('diskcache.persistent.islice', islice):
        with pytest.raises(IndexError):
            deque[0]


def test_get_timeout(deque):
    cache = mock.MagicMock()
    cache.__len__.return_value = 1
    cache.iterkeys.side_effect = [iter([0]), iter([0])]
    cache.__getitem__.side_effect = [dc.Timeout, 0]

    deque.append(0)

    with mock.patch.object(deque, '_cache', cache):
        deque[0]


def test_set_timeout(deque):
    cache = mock.MagicMock()
    cache.__len__.return_value = 1
    cache.iterkeys.side_effect = [iter([0]), iter([0])]
    cache.__setitem__.side_effect = [dc.Timeout, None]

    deque.append(0)

    with mock.patch.object(deque, '_cache', cache):
        deque[0] = 0


def test_del_timeout(deque):
    cache = mock.MagicMock()
    cache.__len__.return_value = 1
    cache.iterkeys.side_effect = [iter([0]), iter([0])]
    cache.__delitem__.side_effect = [dc.Timeout, None]

    deque.append(0)

    with mock.patch.object(deque, '_cache', cache):
        del deque[0]


def test_repr():
    directory = '/tmp/diskcache/deque'
    deque = dc.Deque(directory=directory)
    assert repr(deque) == 'Deque(directory=%r)' % directory


def test_iter_timeout(deque):
    cache = mock.MagicMock()
    cache.iterkeys.side_effect = [iter([0, 1])]
    cache.__getitem__.side_effect = [dc.Timeout, 0]

    with mock.patch.object(deque, '_cache', cache):
        assert list(deque) == [0]


def test_reversed_timeout(deque):
    cache = mock.MagicMock()
    cache.iterkeys.side_effect = [iter([0, 1])]
    cache.__getitem__.side_effect = [dc.Timeout, 0]

    with mock.patch.object(deque, '_cache', cache):
        assert list(reversed(deque)) == [0]


def test_append_timeout(deque):
    cache = mock.MagicMock()
    cache.push.side_effect = [dc.Timeout, None]

    with mock.patch.object(deque, '_cache', cache):
        deque.append(0)


def test_appendleft_timeout(deque):
    cache = mock.MagicMock()
    cache.push.side_effect = [dc.Timeout, None]

    with mock.patch.object(deque, '_cache', cache):
        deque.appendleft(0)


def test_count(deque):
    deque += 'abbcccddddeeeee'

    for index, value in enumerate('abcde', 1):
        assert deque.count(value) == index


def test_extend(deque):
    sequence = list('abcde')
    deque.extend(sequence)
    assert deque == sequence


def test_extendleft(deque):
    sequence = list('abcde')
    deque.extendleft(sequence)
    assert deque == list(reversed(sequence))


def test_pop(deque):
    sequence = list('abcde')
    deque.extend(sequence)

    while sequence:
        assert deque.pop() == sequence.pop()


def test_pop_indexerror(deque):
    with pytest.raises(IndexError):
        deque.pop()


def test_pop_timeout(deque):
    cache = mock.MagicMock()
    cache.pull.side_effect = [dc.Timeout, (None, 0)]

    with mock.patch.object(deque, '_cache', cache):
        assert deque.pop() == 0


def test_popleft(deque):
    sequence = list('abcde')
    deque.extend(sequence)

    while sequence:
        value = sequence[0]
        assert deque.popleft() == value
        del sequence[0]


def test_popleft_indexerror(deque):
    with pytest.raises(IndexError):
        deque.popleft()


def test_popleft_timeout(deque):
    cache = mock.MagicMock()
    cache.pull.side_effect = [dc.Timeout, (None, 0)]

    with mock.patch.object(deque, '_cache', cache):
        assert deque.popleft() == 0


def test_remove(deque):
    deque.extend('abaca')
    deque.remove('a')
    assert deque == 'baca'
    deque.remove('a')
    assert deque == 'bca'
    deque.remove('a')
    assert deque == 'bc'


def test_remove_timeout(deque):
    cache = mock.MagicMock()
    cache.iterkeys.side_effect = [iter([0, 1, 2, 3, 4])]
    cache.__getitem__.side_effect = [0, dc.Timeout, KeyError, 3, 3]
    cache.__delitem__.side_effect = [KeyError, dc.Timeout, None]

    with mock.patch.object(deque, '_cache', cache):
        deque.remove(3)


def test_remove_valueerror(deque):
    with pytest.raises(ValueError):
        deque.remove(0)


def test_reverse(deque):
    deque += 'abcde'
    deque.reverse()
    assert deque == 'edcba'


def test_rotate_typeerror(deque):
    with pytest.raises(TypeError):
        deque.rotate(0.5)


def test_rotate(deque):
    deque.rotate(1)
    deque.rotate(-1)
    deque += 'abcde'
    deque.rotate(3)
    assert deque == 'cdeab'


def test_rotate_negative(deque):
    deque += 'abcde'
    deque.rotate(-2)
    assert deque == 'cdeab'


def test_rotate_indexerror(deque):
    deque += 'abc'

    cache = mock.MagicMock()
    cache.__len__.return_value = 3
    cache.pull.side_effect = [(None, ENOVAL)]

    with mock.patch.object(deque, '_cache', cache):
        deque.rotate(1)


def test_rotate_indexerror_negative(deque):
    deque += 'abc'

    cache = mock.MagicMock()
    cache.__len__.return_value = 3
    cache.pull.side_effect = [(None, ENOVAL)]

    with mock.patch.object(deque, '_cache', cache):
        deque.rotate(-1)


def test_clear_timeout(deque):
    cache = mock.MagicMock()
    cache.clear.side_effect = [dc.Timeout, None]

    with mock.patch.object(deque, '_cache', cache):
        deque.clear()
